# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""E2E-only fixtures for the GARM end-to-end test.

Reuses credential-agnostic fixtures from integration conftest:
``juju``, ``garm_charm_file``, ``garm_app_image``, ``garm_configurator_charm_file``,
``postgresql``, ``garm_app_deployed``, ``garm_app``.
"""

import base64
import hashlib
import io
import logging
import os
import pathlib
import re
import tarfile
import time
import uuid
from dataclasses import dataclass
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
CA_APP_NAME = "self-signed-certificates"
# Not latest/stable: that revision is a 2025 leftover still on the v3
# tls-certificates library, whose provider only reads CSRs from the *unit*
# databag. traefik publishes to the *app* databag over v4, so the pair relates
# cleanly, reports no error, and simply never issues a certificate.
CA_CHANNEL = "1/stable"
E2E_TUNNEL_LOCAL_PORT = 18080
E2E_TUNNEL_LOCAL_TLS_PORT = 18443

# The rock ships the GARM server only, so the client comes from an upstream
# release. Pinned, with its published digest, so a new release cannot change the
# test underneath it. The tag need not match the commit garm-rockcraft.yaml pins:
# the shell wire protocol (GARM's workers/websocket/agent/messaging) is identical
# between the two, so this client drives that server.
GARM_CLI_VERSION = "v0.2.1"
GARM_CLI_URL = (
    f"https://github.com/cloudbase/garm/releases/download/{GARM_CLI_VERSION}"
    "/garm-cli-linux-amd64.tgz"
)
GARM_CLI_SHA256 = "983fa54557f3f5ce3aa1eeb2387499f5f823d14512a0559ba888667bc3b3e88e"


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
    extension vendors. traefik-k8s is picked here as the usual provider in a
    single-node test cluster, not because it is the only one that would satisfy it.
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


@pytest.fixture(scope="module", name="certificate_authority")
def deploy_certificate_authority_fixture(juju: jubilant.Juju) -> str:
    """Deploy a self-signed CA to put the ingress -- and so the agent -- on TLS.

    garm-agent disables its own remote shell whenever the agent URL is not https
    (``config.Validate()`` in garm-agent v0.1.1), silently rather than by failing.
    A plain-http ingress therefore yields a deployment where agent mode works and
    ``has_shell`` is false forever, which no test can distinguish from a bug. The
    CA is what makes the shell reachable at all.

    Returns:
        The CA application name.
    """
    juju.deploy(CA_APP_NAME, channel=CA_CHANNEL)
    juju.wait(
        lambda status: jubilant.all_active(status, CA_APP_NAME),
        error=lambda status: jubilant.any_error(status, CA_APP_NAME),
        timeout=10 * 60,
        delay=10,
    )
    return CA_APP_NAME


@pytest.fixture(scope="module", name="garm_with_ingress")
def integrate_garm_ingress_fixture(
    juju: jubilant.Juju,
    garm_app: str,
    traefik: str,
    certificate_authority: str,
) -> str:
    """Relate GARM to traefik, on TLS, so its controller URLs become routable.

    Args:
        juju: Juju client for the model GARM is deployed in.
        garm_app: Name of the deployed GARM application.
        traefik: Name of the deployed traefik application.
        certificate_authority: Name of the deployed CA application.

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

    # Related only now, never before the ingress relation: traefik derives its
    # certificate requests from the endpoints it currently proxies, so with
    # nothing behind it there is no CSR to sign and the relation settles idle.
    juju.integrate(f"{traefik}:certificates", certificate_authority)
    # Waiting for `active` alone would race: traefik goes active, and advertises
    # https URLs, while its status still reads "Certificate not available yet".
    # GARM would then derive https URLs no VM can complete a handshake against.
    juju.wait(
        lambda status: _traefik_serving_scheme(status, traefik) == "https",
        error=lambda status: jubilant.any_error(status, traefik, certificate_authority),
        timeout=10 * 60,
        delay=10,
    )
    return garm_app


def _traefik_serving_scheme(status: jubilant.Status, traefik: str) -> str | None:
    """Read the scheme traefik reports serving on, once it has a certificate.

    Args:
        status: Juju status for the model traefik is deployed in.
        traefik: Name of the deployed traefik application.

    Returns:
        The scheme of the advertised address, or None if it advertises none yet.
    """
    serving = re.search(r"(?P<scheme>https?)://", status.apps[traefik].app_status.message)
    return serving.group("scheme") if serving else None


def _trust_ingress_ca(juju: jubilant.Juju, garm_app: str, certificate_authority: str) -> None:
    """Hand the ingress CA to GARM so runner VMs trust the callback URLs.

    GARM writes ``ca_cert_bundle`` into every instance's cloud-init as a trusted
    CA, which is what lets a VM complete the handshake against the self-signed
    ingress. The charm does not manage this yet, so the suite sets it directly;
    when the charm learns to feed its ingress CA to the controller this becomes
    redundant and should be deleted.

    Args:
        juju: Juju client for the model GARM is deployed in.
        garm_app: Name of the deployed GARM application.
        certificate_authority: Name of the deployed CA application.
    """
    ca_certificate = juju.run(f"{certificate_authority}/0", "get-ca-certificate").results[
        "ca-certificate"
    ]
    address = _get_garm_address(juju, garm_app)
    response = requests.put(
        f"http://{address}:{GARM_API_PORT}/api/v1/controller",
        headers={"Authorization": f"Bearer {_garm_login(juju, address)}"},
        json={"ca_cert_bundle": base64.b64encode(ca_certificate.encode()).decode()},
        timeout=30,
    )
    response.raise_for_status()


def assert_controller_urls_routable(juju: jubilant.Juju, garm_app: str, traefik: str) -> None:
    """Assert GARM advertises callback URLs a runner VM on the tenant can reach.

    Args:
        juju: Juju client for the model GARM is deployed in.
        garm_app: Name of the deployed GARM application.
        traefik: Name of the deployed traefik application.
    """
    address = _get_garm_address(juju, garm_app)
    headers = {"Authorization": f"Bearer {_garm_login(juju, address)}"}

    # traefik reports the address it serves on, the one the load-balancer handed it. Its
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


@pytest.fixture(scope="module", name="image_builder_stub")
def deploy_image_builder_stub_fixture(juju: jubilant.Juju) -> str:
    """Deploy any-charm as a stub image builder publishing the tenant's real image.

    The same stub the integration suite deploys; what differs is the image name it
    publishes over the relation -- one that exists on the tenant, so the provider
    can actually boot it.
    """
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
    certificate_authority: str,
    openstack_credentials: dict[str, str],
    image_builder_stub: str,
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
    # longer than 60. Reported upstream at
    # https://github.com/cloudbase/garm-provider-openstack/issues/34; until it is
    # fixed the name has to fit. The last six digits of the run id keep the label
    # unique across reruns, and the workflow serialises the suite repository-wide,
    # so no two scale sets are ever live at once.
    # The promotion pipeline unsets GITHUB_RUN_ID to stop opcli's spread prepare
    # waiting on build artifacts it never produces, so the label needs a fallback
    # for when it is absent.
    run_id = os.environ.get("GITHUB_RUN_ID") or uuid.uuid4().hex
    label = f"e2e-{run_id[-6:]}"
    garm_app = garm_with_ingress
    creds = openstack_credentials
    repo = required_env(GITHUB_REPOSITORY_ENV_VAR)

    private_key_decoded = github_app_private_key(E2E_APP_ENV)
    runner_http_proxy = os.environ.get("E2E_RUNNER_HTTP_PROXY", "")
    tunnel_key_b64 = os.environ.get("E2E_TUNNEL_PRIVATE_KEY", "").strip()
    tunnel_target = os.environ.get("E2E_TUNNEL_TARGET", "").strip()
    tunnel_user = os.environ.get("E2E_TUNNEL_USER", "").strip()

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
        # Held at zero so that no runner can be created before _trust_ingress_ca has set
        # the controller's ca_cert_bundle; raised to 1 below once it has. GARM bakes the
        # bundle into each instance's cloud-init at render time, so a runner created
        # first can never verify the self-signed ingress certificate.
        "min-idle-runner": "0",
        "max-runner": "1",
        "repo": repo,
        # Exercised by test_garm_agent_shell, and harmless to the workflow run:
        # the agent runs whenever the entity has agent mode on, and this only
        # decides whether GARM will relay a PTY over the websocket it opens.
        "enable-shell": "true",
    }
    if runner_http_proxy:
        config_values["runner-http-proxy"] = runner_http_proxy
        # The aproxy bootstrap DNATs all :80/:443 egress to aproxy, which forwards
        # to the upstream squid -- and squid denies private destinations with a
        # 403. The GARM metadata and callback URLs point at the load-balancer address
        # (the CI host's own IP, observed in 10.151.128.0/24), so those must
        # bypass the redirect or the runner bootstrap's first curl -- the one
        # fetching the install script -- dies in squid before GARM ever sees it.
        # 10.150.0.0/15 covers both that subnet and the tenant-internal
        # 10.150/16; E2E_APROXY_EXCLUDE_ADDRESSES overrides when ranges shift.
        # Blank means unset: the workflow exports the variable unconditionally,
        # and an empty string would otherwise win over the default here.
        exclude_addresses = os.environ.get("E2E_APROXY_EXCLUDE_ADDRESSES", "").strip() or (
            "10.150.0.0/15"
        )
        config_values["aproxy-exclude-addresses"] = exclude_addresses

    # The private-endpoint host's security group (github-runner-v1, managed by the
    # legacy github-runner-operator charm) admits only ingress tcp/22, so the
    # runner VM cannot reach traefik's :80 that the GARM metadata and callback
    # URLs point at. A pre-install script opens an SSH connection back to the
    # host on the one open port and tunnels those URLs through it. The workflow
    # provides the ephemeral key; when it does not (local runs, other hosts with
    # open networks), the tunnel is skipped and traffic goes direct.
    if any((tunnel_key_b64, tunnel_target, tunnel_user)):
        if not all((tunnel_key_b64, tunnel_target, tunnel_user)):
            logger.warning(
                "Incomplete E2E tunnel configuration: E2E_TUNNEL_PRIVATE_KEY, "
                "E2E_TUNNEL_TARGET and E2E_TUNNEL_USER must all be set; skipping the tunnel"
            )
        else:
            config_values["pre-install-scripts"] = _tunnel_pre_install_script(
                target=tunnel_target, user=tunnel_user, private_key_b64=tunnel_key_b64
            )

    _deploy_configurator(
        juju,
        garm_configurator_charm_file,
        app_name,
        config_values,
        secret_uris=[password_secret, private_key_secret],
    )

    # Integrate with image builder first
    juju.integrate(app_name, image_builder_stub)
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

    # Trust the ingress CA before any runner can exist -- which is why the scale set is
    # deployed with min-idle-runner at zero. GARM bakes ca_cert_bundle into each
    # instance's cloud-init at render time, so a runner created before this lands cannot
    # verify the self-signed ingress certificate: its very first call, fetching the
    # install script, fails the TLS handshake (curl exit 60). Such an instance reaches
    # status=running but never leaves runner_status=pending, and is replaced only once
    # GARM's bootstrap timeout reaps it -- long enough on its own to exhaust the budget
    # test_garm_e2e allows for a runner to come online.
    _trust_ingress_ca(juju, garm_app, certificate_authority)

    # Checked here rather than when the ingress relation is made, which is the first
    # moment GARM is serving and still before any runner has been asked for: a VM that
    # boots against an unroutable callback URL never reports back, and the failure
    # surfaces much later as a runner that simply never registers.
    assert_controller_urls_routable(juju, garm_app, traefik)

    # Only now ask for a runner, with both the CA and the controller URLs known good.
    juju.config(app_name, {"min-idle-runner": "1"})
    try:
        juju.wait(
            lambda status: jubilant.all_active(status, app_name, garm_app),
            error=lambda status: jubilant.any_error(status, app_name),
            timeout=6 * 60,
            delay=10,
        )
    except (TimeoutError, jubilant.WaitError):
        _collect_debug_info(juju, garm_app)
        raise

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
        label: Unique runner label identifying the scale sets to drain and delete.
    """
    address = _get_garm_address(juju, garm_app)
    headers = {"Authorization": f"Bearer {_garm_login(juju, address)}"}
    base_url = f"http://{address}:{GARM_API_PORT}/api/v1"

    response = requests.get(f"{base_url}/scalesets", headers=headers, timeout=30)
    response.raise_for_status()
    # Include disabled generations: they may still own runners or GitHub state.
    for scaleset in response.json() or []:
        if any(tag.get("name") == label for tag in scaleset.get("tags") or []):
            _drain_and_delete_scaleset_id(base_url, headers, scaleset["id"], label)


def _drain_and_delete_scaleset_id(
    base_url: str, headers: dict[str, str], scaleset_id: int, label: str
) -> None:
    """Drain and delete one scale set belonging to the E2E run.

    Args:
        base_url: GARM API base URL.
        headers: Authentication headers for GARM.
        scaleset_id: ID of the scale set to remove.
        label: Runner label used in diagnostic messages.
    """
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


def _tunnel_pre_install_script(target: str, user: str, private_key_b64: str) -> str:
    """Render the pre-install script that tunnels GARM traffic back over SSH.

    The runner VM cannot reach the host's :443 (the security group on the
    private-endpoint host admits only tcp/22), yet GARM bakes its metadata and
    callback URLs -- pointing at the host -- into the user data it hands the
    provider. Pre-install scripts run before GARM's install wrapper, so this
    script opens an SSH connection back to the host on the one open port, binds
    local forwards to the host's :80 and :443, and installs an nftables redirect
    that steers locally-generated traffic for that host into the tunnel. The URLs
    GARM generated then work verbatim, with no controller reconfiguration.

    Both ports are forwarded because the scheme is not the script's to know:
    the ingress serves https once it has a certificate, and the agent websocket
    requires it, but a deployment without a CA still uses :80.

    Args:
        target: The host serving GARM (the load-balancer/traefik address).
        user: The user the tunnel authenticates as on that host.
        private_key_b64: Base64-encoded private key authorised for that user.

    Returns:
        A bash script for the configurator's pre-install-scripts config.
    """
    return f"""#!/bin/bash

groupadd --non-unique --gid 1000 runner

# GARM E2E callback tunnel. Delivered as a pre-install script so it runs before
# GARM's install wrapper, whose first action is fetching the install script
# from the metadata URL on the host this tunnel reaches.
log() {{ echo "[e2e-tunnel] $*"; }}

TARGET='{target}'
SSH_USER='{user}'
LOCAL_PORT={E2E_TUNNEL_LOCAL_PORT}
LOCAL_TLS_PORT={E2E_TUNNEL_LOCAL_TLS_PORT}
KEY_FILE=/root/.ssh/garm-e2e-tunnel
# The nft ruleset below needs the VM's own primary address as the DNAT target,
# resolved the same way the aproxy bootstrap does it.
DEFAULT_IPV4=$(ip route get $(ip route show 0.0.0.0/0 | grep -oP 'via \\K\\S+') \\
    | grep -oP 'src \\K\\S+')

if ! command -v ssh >/dev/null 2>&1; then
    log "ERROR: no ssh client on the image; GARM traffic to ${{TARGET}} will fail"
    exit 0
fi

umask 077
mkdir -p /root/.ssh
printf '%s' '{private_key_b64}' | base64 -d > "$KEY_FILE"

# The host key is not pinned: the keypair this tunnel uses is ephemeral,
# per CI run, and restricted to port forwarding, so a hijacked tunnel gives
# an attacker nothing but the ability to reach the host's :80 and :443.
for attempt in $(seq 1 30); do
    if ssh -f -N \\
        -o StrictHostKeyChecking=no \\
        -o UserKnownHostsFile=/dev/null \\
        -o GlobalKnownHostsFile=/dev/null \\
        -o ServerAliveInterval=30 \\
        -o ExitOnForwardFailure=yes \\
        -o ConnectTimeout=10 \\
        -i "$KEY_FILE" \\
        -L "${{DEFAULT_IPV4}}:$LOCAL_PORT:$TARGET:80" \\
        -L "${{DEFAULT_IPV4}}:$LOCAL_TLS_PORT:$TARGET:443" \\
        "$SSH_USER@$TARGET"; then
        log "tunnel up on $DEFAULT_IPV4:$LOCAL_PORT,$LOCAL_TLS_PORT after $attempt attempt(s)"
        break
    fi
    if [ "$attempt" -eq 30 ]; then
        log "ERROR: tunnel never came up; GARM traffic to $TARGET will fail"
        exit 0
    fi
    sleep 5
done

# Steer locally-generated GARM traffic (metadata, callback and the agent
# websocket) into the tunnel. The aproxy ruleset excludes this address, so its
# DNAT does not claim these packets first. Redirecting to a different local
# port is transparent to TLS: the certificate is checked against the host in
# the URL, which is unchanged, and traefik still terminates it.
nft -f - <<NFT
table ip garm-e2e-tunnel {{
    chain output {{
        type nat hook output priority -100; policy accept;
        ip daddr $TARGET tcp dport 80 counter dnat to $DEFAULT_IPV4:$LOCAL_PORT
        ip daddr $TARGET tcp dport 443 counter dnat to $DEFAULT_IPV4:$LOCAL_TLS_PORT
    }}
}}
NFT
log "redirecting $TARGET:80 to $DEFAULT_IPV4:$LOCAL_PORT and :443 to $DEFAULT_IPV4:$LOCAL_TLS_PORT"
"""


@dataclass(frozen=True)
class GarmCli:
    """A garm-cli already pointed at the deployed GARM as an administrator.

    Attributes:
        binary: Path to the extracted executable.
        env: Environment selecting its isolated profile, for subprocess or exec.
    """

    binary: pathlib.Path
    env: dict[str, str]


@pytest.fixture(scope="module", name="garm_cli")
def garm_cli_fixture(
    tmp_path_factory: pytest.TempPathFactory,
    juju: jubilant.Juju,
    garm_with_ingress: str,
) -> GarmCli:
    """Fetch the pinned garm-cli and give it an admin profile for the deployed GARM.

    Args:
        tmp_path_factory: pytest factory for the directory holding the binary and profile.
        juju: Juju client for the model GARM is deployed in.
        garm_with_ingress: Name of the deployed GARM application.

    Returns:
        The client and the environment that selects its profile.
    """
    root = tmp_path_factory.mktemp("garm-cli")
    binary = _download_garm_cli(root)
    address = _get_garm_address(juju, garm_with_ingress)

    # Written directly rather than through `garm-cli profile add`, whose only
    # password option on this release is -p, and argv is readable by every
    # process on the host. Reusing the JWT the suite already mints keeps the
    # admin password off the command line; `bearer_token` is the pinned
    # release's own on-disk field name.
    home = root / "home"
    config_dir = home / ".local" / "share" / "garm-cli"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text(
        'active_manager = "e2e"\n'
        "\n"
        "[[manager]]\n"
        '  name = "e2e"\n'
        f'  base_url = "http://{address}:{GARM_API_PORT}"\n'
        f'  bearer_token = "{_garm_login(juju, address)}"\n',
        encoding="utf-8",
    )
    return GarmCli(binary=binary, env={**os.environ, "HOME": str(home)})


def _download_garm_cli(root: pathlib.Path) -> pathlib.Path:
    """Download the pinned garm-cli release and extract its single executable.

    Args:
        root: Directory to extract into.

    Returns:
        Path to the extracted executable.
    """
    logger.info("Downloading garm-cli %s from %s", GARM_CLI_VERSION, GARM_CLI_URL)
    response = requests.get(GARM_CLI_URL, timeout=300)
    response.raise_for_status()
    digest = hashlib.sha256(response.content).hexdigest()
    assert digest == GARM_CLI_SHA256, (
        f"Expected garm-cli {GARM_CLI_VERSION} to have sha256 {GARM_CLI_SHA256}, "
        f"got {digest}"
    )

    binary = root / "garm-cli"
    with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as archive:
        # Named member rather than extractall: the archive holds exactly this one
        # file, and reading it explicitly sidesteps the tarfile extraction filters.
        member = archive.extractfile("garm-cli")
        assert member is not None, f"{GARM_CLI_URL} does not contain a garm-cli file"
        binary.write_bytes(member.read())
    binary.chmod(0o755)
    return binary
