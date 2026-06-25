# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
import io
import json
import logging
import pathlib
import secrets
import string
import subprocess
import tempfile
import textwrap
import yaml
import zipfile
from typing import Iterator

import jubilant
import pytest
import requests

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def juju() -> Iterator[jubilant.Juju]:
    """Provide a temporary Juju model for the duration of the module.

    Creates a temporary model and yields a `jubilant.Juju` handle for
    deployments, relations, and config operations. The model is cleaned
    up automatically at the end of the module.
    """
    with jubilant.temp_model() as juju:
        yield juju


@pytest.fixture(name="garm_charm_file", scope="module")
def garm_charm_file_fixture(charm_paths) -> str:
    """Return the path to the built GARM charm file."""
    return charm_paths["garm"].path


@pytest.fixture(name="garm_app_image", scope="module")
def garm_app_image_fixture(charm_resource_images) -> str:
    """Return the GARM OCI image reference for the app-image resource."""
    image = charm_resource_images["garm"]["app-image"]
    logger.info("GARM app image: %s", image)
    return image


@pytest.fixture(name="planner_charm_file", scope="module")
def planner_charm_file_fixture(charm_paths) -> str:
    """Return the path to the built planner charm file."""
    return charm_paths["github-runner-planner"].path


@pytest.fixture(name="planner_app_image", scope="module")
def planner_app_image_fixture(charm_resource_images) -> str:
    """Return the OCI image reference for the planner app-image resource."""
    return charm_resource_images["github-runner-planner"]["app-image"]


@pytest.fixture(name="webhook_gateway_charm_file", scope="module")
def webhook_gateway_charm_file_fixture(charm_paths) -> str:
    """Return the path to the built webhook gateway charm file."""
    return charm_paths["github-runner-webhook-gateway"].path


@pytest.fixture(name="webhook_gateway_app_image", scope="module")
def webhook_gateway_app_image_fixture(charm_resource_images) -> str:
    """Return the OCI image reference for the webhook gateway app-image resource."""
    return charm_resource_images["github-runner-webhook-gateway"]["app-image"]


@pytest.fixture(name="garm_configurator_charm_file", scope="module")
def garm_configurator_charm_file_fixture(charm_paths) -> str:
    """Return the path to the built garm-configurator charm file."""
    return charm_paths["garm-configurator"].path


def _generate_admin_token() -> str:
    alphabet = string.ascii_letters + string.digits + "_-"
    suffix = "".join(secrets.choice(alphabet) for _ in range(20))
    return f"planner_v0_{suffix}"


@pytest.fixture(scope="module", name="planner_admin_token_value")
def planner_admin_token_value_fixture() -> str:
    """Generate and return the planner admin token value for this test module."""
    return _generate_admin_token()


@pytest.fixture(scope="module", name="planner_admin_token_uri")
def create_planner_admin_token_uri_fixture(
    juju: jubilant.Juju, planner_admin_token_value: str
) -> str:
    """Create a Juju secret for the planner admin token and return its URI.

    Secret is created before the app is deployed so it can be referenced in config.
    Granting to the app is done after deploy in the planner_app fixture.
    """
    secret_uri = juju.add_secret(
        name="planner-admin-token", content={"value": planner_admin_token_value}
    )
    return secret_uri


@pytest.fixture(scope="module", name="planner_app")
def deploy_planner_app_fixture(
    juju: jubilant.Juju,
    planner_charm_file: str,
    planner_app_image: str,
    planner_admin_token_uri: str,
) -> str:
    """Deploy the planner application with its OCI image and admin token secret.

    - Deploys the planner charm with the provided image resource.
    - Waits for the application to block pending configuration.
    - Grants the pre-created admin token secret to the application.
    - Sets required configuration including the secret reference and metrics port.

    Returns the application name once initial configuration is applied.
    """
    app_name = "github-runner-planner"

    resources = {
        "app-image": planner_app_image,
    }
    juju.deploy(charm=planner_charm_file, app=app_name, resources=resources)
    juju.wait(
        lambda status: jubilant.all_blocked(status, app_name),
        timeout=6 * 60,
        delay=10,
    )
    juju.grant_secret(planner_admin_token_uri, app_name)
    juju.config(
        app_name, values={"metrics-port": 9464, "admin-token": planner_admin_token_uri}
    )
    return app_name


@pytest.fixture(scope="module", name="user_token")
def user_token_fixture(
    juju: jubilant.Juju,
    planner_app: str,
    planner_admin_token_value: str,
) -> str:
    """Create a regular user token from the planner app using the admin token and return it."""
    status = juju.status()
    unit = f"{planner_app}/0"
    planner_ip = status.apps[planner_app].units[unit].address
    url = f"http://{planner_ip}:8080/api/v1/auth/token/github-runner"
    headers = {"Authorization": f"Bearer {planner_admin_token_value}"}
    resp = requests.post(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    token = data.get("token", "")
    assert token, "expected non-empty user token from planner"
    return token


@pytest.fixture(scope="module", name="webhook_gateway_app")
def deploy_webhook_gateway_app_fixture(
    juju: jubilant.Juju, webhook_gateway_charm_file: str, webhook_gateway_app_image: str
) -> str:
    """Deploy the webhook gateway application with its OCI image and secret.

    - Deploys the webhook gateway charm with the provided image resource.
    - Waits for the application to block pending configuration.
    - Creates and grants a placeholder webhook secret to the application.
    - Configures the application with the secret and metrics port.

    Returns the application name once initial configuration is applied.
    """
    app_name = "github-runner-webhook-gateway"

    resources = {
        "app-image": webhook_gateway_app_image,
    }
    juju.deploy(charm=webhook_gateway_charm_file, app=app_name, resources=resources)
    juju.wait(
        lambda status: jubilant.all_blocked(status, app_name),
        timeout=6 * 60,
        delay=10,
    )
    secret_uri = juju.add_secret(name="webhook", content={"value": "fake-secret"})
    juju.grant_secret(secret_uri, app_name)
    juju.config(app_name, values={"webhook-secret": secret_uri, "metrics-port": 9464})
    return app_name


@pytest.fixture(scope="module", name="rabbitmq")
def deploy_rabbitmq_server_fixture(juju: jubilant.Juju) -> str:
    """Deploy rabbitmq charm (without integrations)."""
    rabbitmq_app = "rabbitmq-k8s"
    juju.deploy(rabbitmq_app, channel="3.12/edge", trust=True)
    juju.wait(
        lambda status: jubilant.all_active(status, rabbitmq_app),
        timeout=(10 * 60),
        delay=30,
    )
    return rabbitmq_app


@pytest.fixture(scope="module", name="webhook_gateway_with_rabbitmq")
def integrate_webhook_gateway_rabbitmq_fixture(
    juju: jubilant.Juju, webhook_gateway_app: str, rabbitmq: str
) -> str:
    """Integrate webhook gateway with rabbitmq.

    Returns the webhook gateway app name after ensuring integration is active.
    """
    juju.integrate(webhook_gateway_app, rabbitmq)
    juju.wait(
        lambda status: jubilant.all_active(status, webhook_gateway_app),
        timeout=(10 * 60),
        delay=30,
    )
    return webhook_gateway_app


@pytest.fixture(scope="module", name="postgresql")
def deploy_postgresql_server_fixture(juju: jubilant.Juju) -> str:
    """Deploy postgresql charm (without integrations)."""
    postgresql_app = "postgresql-k8s"
    juju.deploy(postgresql_app, channel="16/edge", trust=True)
    juju.wait(
        lambda status: jubilant.all_active(status, postgresql_app),
        timeout=(10 * 60),
        delay=30,
    )
    return postgresql_app


@pytest.fixture(scope="module", name="planner_with_integrations")
def integrate_planner_rabbitmq_postgresql_fixture(
    juju: jubilant.Juju, planner_app: str, rabbitmq: str, postgresql: str
) -> str:
    """Integrate planner with rabbitmq and postgresql.

    Returns the planner app name after ensuring all integrations are active.
    """
    juju.integrate(planner_app, rabbitmq)
    juju.integrate(planner_app, postgresql)

    juju.wait(
        lambda status: jubilant.all_active(status, planner_app),
        timeout=(10 * 60),
        delay=30,
    )
    return planner_app


@pytest.fixture(scope="module", name="any_charm_grafana_consumer_app")
def deploy_any_charm_grafana_consumer_app_fixture(juju: jubilant.Juju) -> str:
    """Deploy any charm to act as a grafana-dashboard consumer."""
    app_name = "grafana-consumer"

    juju.deploy(
        "any-charm",
        app=app_name,
        channel="latest/beta",
    )
    juju.wait(
        lambda status: jubilant.all_active(status, app_name),
        timeout=10 * 60,
        delay=10,
    )
    return app_name


@pytest.fixture(scope="module", name="any_charm_github_runner_app")
def deploy_any_charm_github_runner_app_fixture(juju: jubilant.Juju) -> str:
    """Deploy any charm to act as a GitHub runner application."""
    app_name = "github-runner"

    any_charm_src_overwrite = {
        "any_charm.py": textwrap.dedent("""\
            from any_charm_base import AnyCharmBase

            class AnyCharm(AnyCharmBase):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.framework.observe(
                        self.on['require-github-runner-planner-v0'].relation_joined,
                        self._on_planner_relation_joined,
                    )

                def _on_planner_relation_joined(self, event):
                    if self.unit.is_leader():
                        event.relation.data[self.app]["flavor"] = "test-relation-flavor"
                        event.relation.data[self.app]["platform"] = "github"
                        event.relation.data[self.app]["labels"] = '["self-hosted","linux"]'
                        event.relation.data[self.app]["priority"] = "75"
                        event.relation.data[self.app]["minimum-pressure"] = "0"
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


def _pre_pull_garm_image(image: str) -> None:
    """Pre-pull the GARM ROCK image into microk8s containerd.

    The GARM ROCK contains two large statically-linked Go binaries, making it
    significantly larger than other charm images. Pre-pulling into the local
    containerd cache before deploying prevents the 600s juju.wait() from
    expiring while the pod is still downloading the image.
    """
    logger.info("Pre-pulling GARM ROCK image into microk8s containerd: %s", image)
    try:
        result = subprocess.run(
            ["sudo", "microk8s.ctr", "images", "pull", image],
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
        logger.info("GARM image pre-pull complete.\n%s", result.stdout)
    except subprocess.CalledProcessError as e:
        logger.warning(
            "GARM image pre-pull failed (deploy will retry): stderr=%s", e.stderr
        )
    except subprocess.TimeoutExpired:
        logger.warning("GARM image pre-pull timed out after 600s; proceeding anyway")


def _collect_debug_info(app_name: str) -> None:
    """Collect k8s and Juju debug information after a deployment failure."""
    logger.error("=== Debug info for failed GARM deployment ===")
    for cmd in [
        ["sudo", "microk8s.kubectl", "get", "pods", "-A", "-o", "wide"],
        [
            "sudo",
            "microk8s.kubectl",
            "describe",
            "pods",
            "-A",
            "-l",
            f"app.kubernetes.io/name={app_name}",
        ],
        ["sudo", "microk8s.kubectl", "get", "events", "-A", "--sort-by=.lastTimestamp"],
    ]:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            logger.error("$ %s\n%s%s", " ".join(cmd), out.stdout, out.stderr)
        except Exception as exc:
            logger.error("Failed to run %s: %s", cmd, exc)


@pytest.fixture(scope="module", name="garm_app_deployed")
def deploy_garm_app_no_integration_fixture(
    juju: jubilant.Juju,
    garm_charm_file: str,
    garm_app_image: str,
) -> str:
    """Deploy the GARM application WITHOUT integrations (blocked state).

    - Pre-pulls the ROCK image into microk8s containerd to avoid image-pull
      timeouts during juju.wait() (the GARM ROCK is large: two static Go binaries).
    - Deploys the GARM charm with the provided ROCK image as the app-image resource.
    - Waits for the application to block (missing postgresql integration).

    Returns the application name once it reaches blocked status.
    Tests that assert blocked behavior should use this fixture directly.
    """
    app_name = "github-runner-garm"

    if garm_app_image:
        _pre_pull_garm_image(garm_app_image)

    logger.info(
        "Deploying GARM charm: charm_file=%s image=%s app=%s",
        garm_charm_file,
        garm_app_image,
        app_name,
    )
    juju.deploy(
        charm=garm_charm_file,
        app=app_name,
        resources={"app-image": garm_app_image},
    )

    logger.info("Waiting for GARM app '%s' to block (missing postgresql)", app_name)
    try:
        juju.wait(
            lambda status: jubilant.all_blocked(status, app_name),
            timeout=10 * 60,
            delay=10,
        )
    except TimeoutError:
        logger.error("GARM app '%s' did not reach blocked status within 600s", app_name)
        _collect_debug_info(app_name)
        raise

    logger.info("GARM app '%s' is blocked as expected (no postgresql)", app_name)
    return app_name


@pytest.fixture(scope="module", name="garm_app")
def integrate_garm_with_postgresql_fixture(
    juju: jubilant.Juju,
    garm_app_deployed: str,
    postgresql: str,
) -> str:
    """Integrate the deployed GARM application with PostgreSQL and wait for active.

    Depends on garm_app_deployed (which confirms blocked state first), then
    integrates with postgresql-k8s and waits for active status.

    Returns the application name once active.
    """
    app_name = garm_app_deployed

    logger.info("Integrating GARM with PostgreSQL")
    juju.integrate(app_name, postgresql)

    logger.info("Waiting up to 600s for GARM app '%s' to reach active status", app_name)
    try:
        juju.wait(
            lambda status: jubilant.all_agents_idle(status, app_name),
            timeout=10 * 60,
            delay=10,
        )
    except TimeoutError:
        logger.error("GARM app '%s' did not reach active status within 600s", app_name)
        _collect_debug_info(app_name)
        raise

    logger.info("GARM app '%s' is active", app_name)
    return app_name


@pytest.fixture(scope="module", name="any_charm_image_builder_app")
def deploy_any_charm_image_builder_app_fixture(juju: jubilant.Juju) -> str:
    """Deploy any-charm as a fake image builder providing github_runner_image_v0.

    On relation joined, the fake builder immediately writes a synthetic image UUID
    to its unit relation data, allowing the configurator to transition to Active.
    """
    app_name = "fake-image-builder"

    any_charm_src_overwrite = {
        "any_charm.py": textwrap.dedent("""\
            from any_charm_base import AnyCharmBase

            FAKE_IMAGE_ID = "fake-openstack-image-uuid"
            FAKE_IMAGE_TAGS = "x64,noble"

            class AnyCharm(AnyCharmBase):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.framework.observe(
                        self.on['provide-github-runner-image-v0'].relation_joined,
                        self._on_image_relation_joined,
                    )

                def _on_image_relation_joined(self, event):
                    event.relation.data[self.unit]["id"] = FAKE_IMAGE_ID
                    event.relation.data[self.unit]["tags"] = FAKE_IMAGE_TAGS
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


_ANY_CHARM_DEBUG_SSH_CACHE = pathlib.Path(tempfile.gettempdir()) / "any-charm-debug-ssh.charm"


def _get_any_charm_with_debug_ssh() -> str:
    """Download any-charm and inject provide-debug-ssh; return path to the patched .charm.

    Downloads any-charm (latest/beta) from Charmhub, adds the provide-debug-ssh
    endpoint to metadata.yaml, and caches the result so repeated test runs skip
    the download.
    """
    if _ANY_CHARM_DEBUG_SSH_CACHE.exists():
        return str(_ANY_CHARM_DEBUG_SSH_CACHE)

    info = requests.get(
        "https://api.charmhub.io/v2/charms/info/any-charm",
        params={"fields": "default-release.revision.download"},
        timeout=30,
    )
    info.raise_for_status()
    download_url = info.json()["default-release"]["revision"]["download"]["url"]

    logger.info("Downloading any-charm from %s", download_url)
    dl = requests.get(download_url, timeout=120)
    dl.raise_for_status()

    out_buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(dl.content), "r") as src, zipfile.ZipFile(
        out_buf, "w", zipfile.ZIP_DEFLATED
    ) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "metadata.yaml":
                meta = yaml.safe_load(data)
                meta.setdefault("provides", {})["provide-debug-ssh"] = {"interface": "debug-ssh"}
                data = yaml.dump(meta).encode("utf-8")
            out_info = zipfile.ZipInfo(item.filename)
            out_info.compress_type = item.compress_type
            out_info.external_attr = item.external_attr
            dst.writestr(out_info, data)

    _ANY_CHARM_DEBUG_SSH_CACHE.write_bytes(out_buf.getvalue())
    logger.info("Cached patched any-charm at %s", _ANY_CHARM_DEBUG_SSH_CACHE)
    return str(_ANY_CHARM_DEBUG_SSH_CACHE)


@pytest.fixture(scope="module", name="any_charm_debug_ssh_app")
def deploy_any_charm_debug_ssh_app_fixture(juju: jubilant.Juju) -> str:
    """Deploy any-charm as a fake tmate server providing the debug-ssh relation."""
    app_name = "fake-tmate"

    any_charm_src_overwrite = {
        "any_charm.py": textwrap.dedent("""\
            from any_charm_base import AnyCharmBase

            class AnyCharm(AnyCharmBase):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.framework.observe(
                        self.on.provide_debug_ssh_relation_joined,
                        self._on_debug_ssh_joined,
                    )

                def _on_debug_ssh_joined(self, event):
                    event.relation.data[self.unit]["host"] = "tmate.example.com"
                    event.relation.data[self.unit]["port"] = "2200"
                    event.relation.data[self.unit]["rsa_fingerprint"] = "SHA256:fakefingerprint1234"
                    event.relation.data[self.unit]["ed25519_fingerprint"] = "SHA256:fakeed25519abcd"
            """),
    }
    charm_file = _get_any_charm_with_debug_ssh()
    juju.deploy(
        charm=charm_file,
        app=app_name,
        config={"src-overwrite": json.dumps(any_charm_src_overwrite)},
    )
    juju.wait(
        lambda status: jubilant.all_active(status, app_name),
        timeout=10 * 60,
        delay=10,
    )
    return app_name


@pytest.fixture(scope="module", name="garm_configurator_charm_file")
def garm_configurator_charm_file_fixture(charm_paths) -> str:
    """Return the path to the built garm-configurator charm file."""
    return charm_paths["garm-configurator"].path


@pytest.fixture(scope="module", name="configurator_with_image")
def deploy_configurator_with_image_fixture(
    juju: jubilant.Juju,
    garm_configurator_charm_file: str,
    any_charm_image_builder_app: str,
) -> str:
    """Deploy the configurator with fake-image-builder integrated and valid config.

    Creates Juju secrets for the password and private key fields, deploys the
    configurator charm, sets all required config, integrates with the fake image
    builder, and waits for the configurator to become active (image UUID received).
    """
    app_name = "garm-configurator"

    # Create secrets first so we can reference them in config
    password_secret = juju.add_secret(
        name="configurator-os-password",
        content={"value": "test-openstack-password"},
    )
    private_key_secret = juju.add_secret(
        name="configurator-github-private-key",
        content={"value": "test-github-private-key"},
    )

    juju.deploy(charm=garm_configurator_charm_file, app=app_name)
    juju.wait(
        lambda status: jubilant.all_blocked(status, app_name),
        timeout=6 * 60,
        delay=10,
    )

    juju.grant_secret(password_secret, app_name)
    juju.grant_secret(private_key_secret, app_name)

    juju.config(
        app_name,
        values={
            "openstack-auth-url": "https://keystone.example.com:5000/v3",
            "openstack-username": "admin",
            "openstack-password": password_secret,
            "openstack-project-name": "test-project",
            "openstack-user-domain-name": "Default",
            "openstack-project-domain-name": "Default",
            "openstack-region-name": "RegionOne",
            "openstack-network": "external-net",
            "github-app-client-id": "test-client-id",
            "github-app-installation-id": "test-installation-id",
            "github-app-private-key": private_key_secret,
            "name": "test-scaleset",
            "flavor": "m1.large",
            "os-arch": "amd64",
            "min-idle-runner": "0",
            "max-runner": "5",
            "repo": "testorg/testrepo",
        },
    )

    juju.integrate(app_name, any_charm_image_builder_app)
    juju.wait(
        lambda status: jubilant.all_active(status, app_name),
        timeout=6 * 60,
        delay=10,
    )

    return app_name


@pytest.fixture(scope="module", name="configurator_garm")
def integrate_configurator_with_garm_fixture(
    juju: jubilant.Juju,
    configurator_with_image: str,
    garm_app: str,
) -> str:
    """Integrate the configurator with GARM and wait for both to be active.

    The configurator should remain Active after integration. GARM may
    restart when it receives the relation data (TOML change detection),
    so we wait for GARM to settle back to active.

    Returns the garm app name.
    """
    juju.integrate(configurator_with_image, garm_app)
    # Wait for both apps to settle. GARM may restart (TOML hash change).
    juju.wait(
        lambda status: jubilant.all_active(status, garm_app)
        and jubilant.all_active(status, configurator_with_image),
        timeout=10 * 60,
        delay=10,
    )
    return garm_app
