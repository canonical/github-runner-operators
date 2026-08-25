# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""E2E-only fixtures for the GARM end-to-end test.

Reuses credential-agnostic fixtures from integration conftest:
``juju``, ``garm_charm_file``, ``garm_app_image``, ``garm_configurator_charm_file``,
``postgresql``, ``garm_app_deployed``, ``garm_app``.
"""

import logging
import os
import re
import time
import uuid
from typing import Iterator

import jubilant
import pytest
import requests

# Registers these fixtures with pytest: importing a function decorated with
# @pytest.fixture is enough for pytest to pick it up under its own name.
# `pytest_plugins` would do the same but hard-errors as soon as a sibling
# suite (e.g. charms/tests/integration) is collected in the same session.
from tests.integration.conftest import (  # noqa: F401
    _collect_debug_info,
    _deploy_configurator,
    _deploy_image_builder,
    _garm_login,
    _get_garm_address,
    deploy_garm_app_no_integration_fixture,
    deploy_postgresql_server_fixture,
    garm_app_image_fixture,
    garm_charm_file_fixture,
    garm_configurator_charm_file_fixture,
    integrate_garm_with_postgresql_fixture,
    juju,
)
from tests.integration.helpers import (
    E2E_APP_ENV,
    GITHUB_REPOSITORY_ENV_VAR,
    github_app_private_key,
    required_env,
    required_int_env,
)

logger = logging.getLogger(__name__)

GARM_API_PORT = 8080
SCALESET_DRAIN_TIMEOUT = 10 * 60
TRAEFIK_CHANNEL = "latest/stable"


@pytest.fixture(scope="module", name="openstack_credentials")
def openstack_credentials_fixture() -> dict[str, str]:
    """Read real ProdStack OpenStack credentials from the environment.

    Never a pytest CLI option — argv shows up in logs and in ``ps``.
    """
    return {
        "auth_url": required_env("OS_AUTH_URL"),
        "username": required_env("OS_USERNAME"),
        "password": required_env("OS_PASSWORD"),
        "project_name": required_env("OS_PROJECT_NAME"),
        "user_domain_name": required_env("OS_USER_DOMAIN_NAME"),
        "project_domain_name": required_env("OS_PROJECT_DOMAIN_NAME"),
        "region_name": required_env("OS_REGION_NAME"),
        "network": required_env("OS_NETWORK"),
    }


@pytest.fixture(scope="module", name="traefik")
def deploy_traefik_fixture(juju: jubilant.Juju) -> str:
    """Deploy traefik-k8s with trust and wait for active.

    The E2E needs ingress at all because a runner VM on the tenant has to reach GARM's
    callback and metadata URLs, which the in-cluster service address cannot serve.

    ``ingress`` is a standard charm relation interface with several providers; the charm
    requires it via the ``charms.traefik_k8s.v2.ingress`` library the go-framework
    extension vendors. traefik-k8s is picked here as the usual provider on microk8s, not
    because it is the only one that would satisfy the relation.
    """
    app_name = "traefik-k8s"
    juju.deploy(app_name, channel=TRAEFIK_CHANNEL, trust=True)
    juju.wait(
        lambda status: jubilant.all_active(status, app_name),
        error=lambda status: jubilant.any_error(status, app_name),
        timeout=10 * 60,
        delay=10,
    )
    return app_name


@pytest.fixture(scope="module", name="garm_with_ingress")
def integrate_garm_ingress_fixture(
    juju: jubilant.Juju,
    garm_app: str,
    traefik: str,
) -> str:
    """Relate GARM to traefik so its controller URLs become routable.

    Args:
        juju: Juju client for the model GARM is deployed in.
        garm_app: Name of the deployed GARM application.
        traefik: Name of the deployed traefik application.

    Returns:
        The GARM application name.
    """
    juju.integrate(f"{garm_app}:ingress", traefik)
    # GARM cannot reach active here, and its API is not up either: the charm's restart()
    # returns before starting the workload while no configurator has supplied provider
    # configs. So this waits for traefik to serve and for GARM's hook to settle, and the
    # controller URLs are checked once the configurator has brought the workload up.
    juju.wait(
        lambda status: jubilant.all_active(status, traefik)
        and jubilant.all_agents_idle(status, garm_app),
        error=lambda status: jubilant.any_error(status, garm_app, traefik),
        timeout=10 * 60,
        delay=10,
    )
    return garm_app


def assert_controller_urls_routable(juju: jubilant.Juju, garm_app: str, traefik: str) -> None:
    """Assert GARM advertises callback URLs a runner VM on the tenant can reach.

    Args:
        juju: Juju client for the model GARM is deployed in.
        garm_app: Name of the deployed GARM application.
        traefik: Name of the deployed traefik application.
    """
    address = _get_garm_address(juju, garm_app)
    headers = {"Authorization": f"Bearer {_garm_login(juju, address)}"}

    # traefik reports the address it serves on, which is the one MetalLB handed it. Its
    # unit address is the pod IP, which is not reachable from outside the cluster and so
    # is not what GARM should be advertising.
    message = juju.status().apps[traefik].app_status.message
    serving = re.search(r"https?://(?P<host>[^/\s]+)", message)
    if serving is None:
        pytest.fail(f"Could not read traefik's serving address from its status: {message!r}")
    traefik_ip = serving.group("host")

    response = requests.get(
        f"http://{address}:{GARM_API_PORT}/api/v1/controller-info", headers=headers, timeout=30
    )
    response.raise_for_status()
    metadata_url = response.json().get("metadata_url", "")
    logger.info("GARM metadata_url: %s (expecting host %s)", metadata_url, traefik_ip)

    # A spawned VM reaches GARM over the load balancer; the in-cluster service name it
    # would otherwise advertise does not resolve outside the cluster, so a runner would
    # boot and then never call back.
    assert traefik_ip in metadata_url, (
        f"Expected metadata_url on the traefik LB address {traefik_ip}, got: {metadata_url}"
    )
    assert not re.search(r"\.svc\.", metadata_url), (
        f"Expected a routable metadata_url, got the in-cluster address: {metadata_url}"
    )


@pytest.fixture(scope="module", name="real_image_builder")
def deploy_real_image_builder_fixture(juju: jubilant.Juju) -> str:
    """Deploy any-charm as an image builder publishing a real image name."""
    image_name = required_env("E2E_RUNNER_IMAGE_NAME")
    return _deploy_image_builder(
        juju=juju,
        app_name="image-builder",
        image_id=image_name,
        tags="x64,noble",
    )


@pytest.fixture(scope="module", name="e2e_scaleset")
def deploy_e2e_scaleset_fixture(
    juju: jubilant.Juju,
    garm_with_ingress: str,
    traefik: str,
    openstack_credentials: dict[str, str],
    real_image_builder: str,
    garm_configurator_charm_file: str,
) -> Iterator[str]:
    """Deploy garm-configurator with real tenant values and a unique run label.

    Creates Juju secrets for the password and private key, deploys the configurator,
    integrates with the image builder and GARM, and waits for the scaleset to register.
    Returns the unique runner label that runners will register with.
    """
    app_name = "garm-configurator"
    # The scale set name caps at 10 characters: the OpenStack provider tags every
    # runner VM with the Nova server tag "garm-pool-id=<name>-<entity uuid>",
    # which is 50 fixed characters before the name starts, and Nova rejects tags
    # longer than 60. The last six digits of the run id keep the label unique;
    # the workflow's per-ref concurrency group already serialises runs on the
    # same branch.
    run_id = os.environ.get("GITHUB_RUN_ID", uuid.uuid4().hex)
    label = f"e2e-{run_id[-6:]}"
    garm_app = garm_with_ingress
    creds = openstack_credentials
    repo = required_env(GITHUB_REPOSITORY_ENV_VAR)

    private_key_decoded = github_app_private_key(E2E_APP_ENV)
    runner_http_proxy = os.environ.get("E2E_RUNNER_HTTP_PROXY", "")

    # Create secrets
    password_secret = juju.add_secret(
        name="e2e-os-password",
        content={"value": creds["password"]},
    )
    private_key_secret = juju.add_secret(
        name="e2e-github-private-key",
        content={"value": private_key_decoded},
    )

    config_values = {
        "openstack-auth-url": creds["auth_url"],
        "openstack-username": creds["username"],
        "openstack-password": password_secret,
        "openstack-project-name": creds["project_name"],
        "openstack-user-domain-name": creds["user_domain_name"],
        "openstack-project-domain-name": creds["project_domain_name"],
        "openstack-region-name": creds["region_name"],
        "openstack-network": creds["network"],
        "github-app-id": str(required_int_env(E2E_APP_ENV.app_id)),
        "github-app-installation-id": str(required_int_env(E2E_APP_ENV.installation_id)),
        "github-app-private-key": private_key_secret,
        "name": label,
        "labels": label,
        "flavor": os.environ.get("E2E_OPENSTACK_FLAVOR", "m1.small"),
        "os-arch": "amd64",
        "min-idle-runner": "1",
        "max-runner": "1",
        "repo": repo,
    }
    if runner_http_proxy:
        config_values["runner-http-proxy"] = runner_http_proxy

    _deploy_configurator(
        juju,
        garm_configurator_charm_file,
        app_name,
        config_values,
        secret_uris=[password_secret, private_key_secret],
    )

    # Integrate with image builder first
    juju.integrate(app_name, real_image_builder)
    try:
        juju.wait(
            lambda status: jubilant.all_active(status, app_name),
            error=lambda status: jubilant.any_error(status, app_name),
            timeout=6 * 60,
            delay=10,
        )
    except (TimeoutError, jubilant.WaitError):
        _collect_debug_info(juju, app_name)
        raise

    # Then integrate with GARM. This is what starts the workload: until provider configs
    # arrive from the configurator, the charm's restart() returns before starting it.
    juju.integrate(app_name, garm_app)
    try:
        juju.wait(
            lambda status: jubilant.all_active(status, app_name, garm_app),
            error=lambda status: jubilant.any_error(status, app_name),
            timeout=10 * 60,
            delay=10,
        )
    except (TimeoutError, jubilant.WaitError):
        _collect_debug_info(juju, garm_app)
        raise

    # Checked here rather than when the ingress relation is made, which is the first
    # moment GARM is serving and still before any runner has been asked for: a VM that
    # boots against an unroutable callback URL never reports back, and the failure
    # surfaces much later as a runner that simply never registers.
    assert_controller_urls_routable(juju, garm_app, traefik)

    yield label

    # Best effort only: the workflow's own sweep is what guarantees no VM is left
    # behind, since a fixture cannot run if the model or the runner dies mid-test.
    try:
        _drain_and_delete_scaleset(juju, garm_app, label)
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning("Best-effort scale set teardown did not complete: %s", exc)


def _drain_and_delete_scaleset(juju: jubilant.Juju, garm_app: str, label: str) -> None:
    """Drain and delete the E2E scale set, on GARM and on GitHub.

    Args:
        juju: Juju client for the model GARM is deployed in.
        garm_app: Name of the deployed GARM application.
        label: Name of the scale set to drain and delete.
    """
    address = _get_garm_address(juju, garm_app)
    headers = {"Authorization": f"Bearer {_garm_login(juju, address)}"}
    base_url = f"http://{address}:{GARM_API_PORT}/api/v1"

    response = requests.get(f"{base_url}/scalesets", headers=headers, timeout=30)
    response.raise_for_status()
    scaleset = next((s for s in response.json() or [] if s.get("name") == label), None)
    if scaleset is None:
        return
    scaleset_id = scaleset["id"]
    logger.info("Draining E2E scale set %s (%s)", scaleset_id, label)

    # Disabling stops replacement; min_idle_runners=0 lets the existing ones go.
    # PUT, not PATCH: GARM routes only PUT to the scale set update handler, so a
    # PATCH is answered with a 405 -- which used to abort the whole teardown here,
    # leaving the scale set, its instances and their GitHub runners behind when
    # the model was destroyed.
    requests.put(
        f"{base_url}/scalesets/{scaleset_id}",
        json={"enabled": False, "min_idle_runners": 0},
        headers=headers,
        timeout=30,
    ).raise_for_status()

    # GARM rejects the delete while the scale set still owns instances, so wait
    # for the drain rather than racing it -- a failed delete here is a VM left
    # running on the tenant.
    deadline = time.time() + SCALESET_DRAIN_TIMEOUT
    force_removed: set[str] = set()
    while time.time() < deadline:
        instances = requests.get(
            f"{base_url}/scalesets/{scaleset_id}/instances", headers=headers, timeout=30
        )
        instances.raise_for_status()
        remaining = instances.json() or []
        if not remaining:
            break
        # The post-disable scale-down only reclaims *running* idle runners, so
        # force-remove anything else once: that covers instances a failed spawn
        # left in error, and deleting an instance also removes its JIT runner
        # from GitHub -- the source of the offline garm-* leftovers this suite
        # used to leave behind.
        for instance in remaining:
            _force_remove_instance(base_url, headers, instance, force_removed)
        logger.info("Waiting for %d instance(s) to drain", len(remaining))
        time.sleep(10)
    else:
        logger.warning(
            "Scale set %s still had instances after %ds; deleting anyway",
            scaleset_id,
            SCALESET_DRAIN_TIMEOUT,
        )

    # Deletes the scale set on GitHub too, not just in GARM's database.
    requests.delete(
        f"{base_url}/scalesets/{scaleset_id}", headers=headers, timeout=30
    ).raise_for_status()
    logger.info("Deleted E2E scale set %s", scaleset_id)


def _force_remove_instance(
    base_url: str,
    headers: dict[str, str],
    instance: dict,
    force_removed: set[str],
) -> None:
    """Force-remove one scale set instance, at most once, best-effort.

    Args:
        base_url: GARM API base URL, ending in ``/api/v1``.
        headers: Authorization headers for the GARM API.
        instance: Instance payload as returned by the GARM API.
        force_removed: Instance names already attempted, so a still-draining
            instance is not re-attempted on every poll.
    """
    name = instance.get("name")
    if not name or name in force_removed:
        return
    force_removed.add(name)
    response = requests.delete(
        f"{base_url}/instances/{name}",
        params={"forceRemove": "true"},
        headers=headers,
        timeout=30,
    )
    if response.ok:
        logger.info("Force-removing leftover instance %s", name)
    else:
        # Expected for states GARM refuses to delete (e.g. pending_create);
        # the drain timeout below is what bounds those.
        logger.warning(
            "Could not force-remove instance %s (status=%s): HTTP %d",
            name,
            instance.get("status"),
            response.status_code,
        )
