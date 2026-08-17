# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""E2E-only fixtures for the GARM end-to-end test.

Reuses everything credential-agnostic from the integration conftest (imported
and re-registered under their marker names):
``juju``, ``garm_charm_file``, ``garm_app_image``, ``garm_configurator_charm_file``,
``postgresql``, ``garm_app_deployed``, ``garm_app``.

New fixtures here:
- ``openstack_credentials`` — reads real ProdStack credentials from env.
- ``traefik`` — deploys traefik-k8s for ingress.
- ``garm_with_ingress`` — integrates GARM with traefik, asserts routable controller URLs.
- ``real_image_builder`` — any-charm publishing a real image name instead of fake UUID.
- ``e2e_scaleset`` — deploys configurator with real tenant values and unique run label.
"""

import json
import logging
import os
import re
import textwrap
import uuid

import jubilant
import pytest
import requests

# ── Reuse credential-agnostic fixtures from integration conftest ────────────
# These are imported as fixture functions; pytest re-registers them under their
# marker names (``name=`` in the decorator) so the conftest attribute name is
# irrelevant as long as the attribute exists in the module.
from tests.integration.conftest import (  # noqa: F401
    _collect_debug_info as _collect_debug_info,
    _pre_pull_garm_image as _pre_pull_garm_image,
    deploy_garm_app_no_integration_fixture,
    deploy_postgresql_server_fixture,
    garm_app_image_fixture,
    garm_charm_file_fixture,
    garm_configurator_charm_file_fixture,
    integrate_garm_with_postgresql_fixture,
    juju,
)
from tests.integration.helpers import create_github_app_client, required_env

# Re-register imported fixtures under their marker names so both pytest and
# pyright can resolve them.  The marker name is what matters for pytest, but
# the explicit alias keeps pyright happy.
garm_app_image = garm_app_image_fixture
garm_charm_file = garm_charm_file_fixture
garm_configurator_charm_file = garm_configurator_charm_file_fixture
garm_app_deployed = deploy_garm_app_no_integration_fixture
garm_app = integrate_garm_with_postgresql_fixture
postgresql = deploy_postgresql_server_fixture

logger = logging.getLogger(__name__)

GARM_API_PORT = 8080


# ── New E2E fixtures ───────────────────────────────────────────────────────


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
    """Deploy traefik-k8s with trust and wait for active."""
    app_name = "traefik-k8s"
    juju.deploy(app_name, channel="latest/stable", trust=True)
    juju.wait(
        lambda status: jubilant.all_active(status, app_name),
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
        lambda status: jubilant.all_agents_idle(status, app_name),
        timeout=10 * 60,
        delay=10,
    )

    # Assert GARM's controller info reports a metadata_url on the LB IP
    status = juju.status()
    unit_address = status.apps[app_name].units[f"{app_name}/0"].address
    resp = requests.get(
        f"http://{unit_address}:{GARM_API_PORT}/api/v1/controller", timeout=10
    )
    resp.raise_for_status()
    controller = resp.json()
    metadata_url = controller.get("metadata_url", "")
    logger.info("GARM controller metadata_url: %s", metadata_url)
    assert re.search(r"^\d+\.\d+\.\d+\.\d+", metadata_url), (
        f"Expected metadata_url to contain an IP address, got: {metadata_url}"
    )
    assert not re.search(r"\.svc\.", metadata_url), (
        f"Expected metadata_url to be routable (not .svc), got: {metadata_url}"
    )
    return app_name


@pytest.fixture(scope="module", name="real_image_builder")
def deploy_real_image_builder_fixture(juju: jubilant.Juju) -> str:
    """Deploy any-charm as an image builder publishing a real image name.

    The image name comes from the ``E2E_RUNNER_IMAGE_NAME`` env variable.
    """
    app_name = "image-builder"
    image_name = required_env("E2E_RUNNER_IMAGE_NAME")

    any_charm_src_overwrite = {
        "any_charm.py": textwrap.dedent(f"""\
            from any_charm_base import AnyCharmBase

            class AnyCharm(AnyCharmBase):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.framework.observe(
                        self.on['provide-github-runner-image-v0'].relation_joined,
                        self._on_image_relation_joined,
                    )

                def _on_image_relation_joined(self, event):
                    event.relation.data[self.unit]["id"] = "{image_name}"
                    event.relation.data[self.unit]["tags"] = "x64,noble"
        """),
    }
    juju.deploy(
        "any-charm",
        app=app_name,
        channel="latest/beta",
        config={"src-overwrite": json.dumps(any_charm_src_overwrite)},
    )
    juju.wait(
        lambda status: jubilant.all_active(status, app_name),
        timeout=10 * 60,
        delay=10,
    )
    return app_name


@pytest.fixture(scope="module", name="e2e_scaleset")
def deploy_e2e_scaleset_fixture(
    juju: jubilant.Juju,
    garm_with_ingress: str,
    openstack_credentials: dict[str, str],
    real_image_builder: str,
    garm_configurator_charm_file: str,
) -> str:
    """Deploy garm-configurator with real tenant values and a unique run label.

    Creates Juju secrets for the password and private key, deploys the configurator,
    integrates with the image builder and GARM, and waits for the scaleset to register.
    """
    app_name = "garm-configurator"
    run_id = os.environ.get("GITHUB_RUN_ID", uuid.uuid4().hex[:8])
    label = f"garm-e2e-{run_id}"
    garm_app = garm_with_ingress
    creds = openstack_credentials
    org = required_env("TEST_GITHUB_PATH").split("/")[0]

    # Build the runner-http-proxy URL from env if set
    runner_http_proxy = os.environ.get("E2E_RUNNER_HTTP_PROXY", "")

    # Create secrets
    password_secret = juju.add_secret(
        name="e2e-os-password",
        content={"value": creds["password"]},
    )
    private_key_secret = juju.add_secret(
        name="e2e-github-private-key",
        content={"value": required_env("TEST_GITHUB_APP_PRIVATE_KEY")},
    )

    juju.deploy(charm=garm_configurator_charm_file, app=app_name)
    juju.wait(
        lambda status: jubilant.all_blocked(status, app_name),
        timeout=6 * 60,
        delay=10,
    )

    juju.grant_secret(password_secret, app_name)
    juju.grant_secret(private_key_secret, app_name)

    config_values = {
        "openstack-auth-url": creds["auth_url"],
        "openstack-username": creds["username"],
        "openstack-password": password_secret,
        "openstack-project-name": creds["project_name"],
        "openstack-user-domain-name": creds["user_domain_name"],
        "openstack-project-domain-name": creds["project_domain_name"],
        "openstack-region-name": creds["region_name"],
        "openstack-network": creds["network"],
        "github-app-id": required_env("TEST_GITHUB_APP_ID"),
        "github-app-installation-id": required_env("TEST_GITHUB_APP_INSTALLATION_ID"),
        "github-app-private-key": private_key_secret,
        "name": label,
        "flavor": os.environ.get("E2E_OPENSTACK_FLAVOR", "m1.small"),
        "os-arch": "amd64",
        "min-idle-runner": "1",
        "max-runner": "1",
        "org": org,
    }
    if runner_http_proxy:
        config_values["runner-http-proxy"] = runner_http_proxy

    juju.config(app_name, values=config_values)

    # Integrate with image builder first
    juju.integrate(app_name, real_image_builder)
    juju.wait(
        lambda status: jubilant.all_active(status, app_name),
        timeout=6 * 60,
        delay=10,
    )

    # Then integrate with GARM
    juju.integrate(app_name, garm_app)
    juju.wait(
        lambda status: jubilant.all_agents_idle(status, garm_app)
        and jubilant.all_active(status, app_name),
        timeout=10 * 60,
        delay=10,
    )

    return app_name