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
    """Integrate GARM with traefik and assert controller URLs resolve to the LB IP.

    This is the guard that the callback path is actually live before a VM is spawned.
    """
    app_name = garm_app
    juju.integrate(f"{app_name}:ingress", traefik)
    juju.wait(
        lambda status: jubilant.all_active(status, app_name, traefik),
        error=lambda status: jubilant.any_error(status, app_name, traefik),
        timeout=10 * 60,
        delay=10,
    )

    address = _get_garm_address(juju, app_name)
    token = _garm_login(juju, address)
    headers = {"Authorization": f"Bearer {token}"}

    traefik_status = juju.status()
    traefik_unit = f"{traefik}/0"
    traefik_ip = traefik_status.apps[traefik].units[traefik_unit].address

    # Assert GARM's controller-info reports metadata_url with the Traefik LB IP
    resp = requests.get(
        f"http://{address}:{GARM_API_PORT}/api/v1/controller-info",
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    controller = resp.json()
    metadata_url = controller.get("metadata_url", "")
    logger.info("GARM controller metadata_url: %s (expected host: %s)", metadata_url, traefik_ip)
    assert traefik_ip in metadata_url, (
        f"Expected metadata_url to contain Traefik LB IP {traefik_ip}, got: {metadata_url}"
    )
    assert not re.search(r"\.svc\.", metadata_url), (
        f"Expected metadata_url to be routable (not .svc), got: {metadata_url}"
    )
    return app_name


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
    run_id = os.environ.get("GITHUB_RUN_ID", uuid.uuid4().hex[:8])
    label = f"garm-e2e-{run_id}"
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

    # Then integrate with GARM
    juju.integrate(app_name, garm_app)
    try:
        juju.wait(
            lambda status: jubilant.all_active(status, app_name)
            and jubilant.all_agents_idle(status, garm_app),
            error=lambda status: jubilant.any_error(status, app_name),
            timeout=10 * 60,
            delay=10,
        )
    except (TimeoutError, jubilant.WaitError):
        _collect_debug_info(juju, garm_app)
        raise

    yield label

    # Best effort only: the workflow's own sweep is what guarantees no VM is left
    # behind, since a fixture cannot run if the model or the runner dies mid-test.
    try:
        address = _get_garm_address(juju, garm_app)
        headers = {"Authorization": f"Bearer {_garm_login(juju, address)}"}
        base_url = f"http://{address}:{GARM_API_PORT}/api/v1"

        response = requests.get(f"{base_url}/scalesets", headers=headers, timeout=30)
        response.raise_for_status()
        scaleset = next((s for s in response.json() or [] if s.get("name") == label), None)
        if scaleset is not None:
            scaleset_id = scaleset["id"]
            logger.info("Draining E2E scale set %s (%s)", scaleset_id, label)
            # Disabling stops replacement; min_idle_runners=0 lets the existing ones go.
            requests.patch(
                f"{base_url}/scalesets/{scaleset_id}",
                json={"enabled": False, "min_idle_runners": 0},
                headers=headers,
                timeout=30,
            ).raise_for_status()

            # GARM rejects the delete while the scale set still owns instances, so wait
            # for the drain rather than racing it -- a failed delete here is a VM left
            # running on the tenant.
            deadline = time.time() + SCALESET_DRAIN_TIMEOUT
            while time.time() < deadline:
                instances = requests.get(
                    f"{base_url}/scalesets/{scaleset_id}/instances", headers=headers, timeout=30
                )
                instances.raise_for_status()
                remaining = instances.json() or []
                if not remaining:
                    break
                logger.info("Waiting for %d instance(s) to drain", len(remaining))
                time.sleep(10)
            else:
                logger.warning(
                    "Scale set %s still had instances after %ds; deleting anyway",
                    scaleset_id,
                    SCALESET_DRAIN_TIMEOUT,
                )

            requests.delete(
                f"{base_url}/scalesets/{scaleset_id}", headers=headers, timeout=30
            ).raise_for_status()
            logger.info("Deleted E2E scale set %s", scaleset_id)
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning("Best-effort scale set teardown did not complete: %s", exc)
