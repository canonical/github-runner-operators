# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for GarmCharm, driven through Scenario.

Each test runs the real charm against a State and asserts on the resulting State: the Juju
secrets it created, the files it pushed, the Pebble plan it left behind, and the status it
reported. Only GARM's HTTP surface is stubbed (the ``garm_api`` fixture) — no GARM process
listens in a unit test — so the charm's own logic always runs for real.

The pure config-rendering helpers in charm.py are tested in test_garm_toml.py.
"""

import dataclasses
import os
import typing
from unittest.mock import MagicMock, PropertyMock, patch

import ops
import pytest
import yaml
from ops import pebble
from scenario import ActionFailed, Container, Context, Model, PeerRelation, Relation, Secret, State
from scenario.errors import UncaughtCharmError

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

import garm_template
from charm import GARM_ADMIN_CREDENTIALS_LABEL, GARM_PORT, GARM_SECRETS_LABEL, GarmCharm
from charm_state import DEBUG_SSH_INTEGRATION_NAME, GARM_CONFIGURATOR_RELATION_NAME
from garm_api import GarmConnectionError
from github_reconciler import (
    DEFAULT_GITHUB_ENDPOINT,
    MANAGED_CREDENTIAL_DESCRIPTION,
    CredentialSpec,
)

MODEL_NAME = "garm-model"
CONTAINER_NAME = "app"
SERVICE_NAME = "app"

# The rock ships a `go` service that the go-framework's layer overrides; without it in the
# container's base layer paas_charm's restart() fails to find the service to replace.
_ROCK_LAYER = pebble.Layer(
    {
        "services": {
            "go": {
                "override": "replace",
                "summary": "GARM GitHub Actions Runner Manager",
                "startup": "disabled",
                "command": "/usr/local/bin/garm",
            }
        }
    }
)

# The key paas_charm's KeySecretStorage keeps in the peer databag; is_ready() gates on it.
_SECRET_STORAGE_KEY = "go_secret_key"

_GARM_SECRETS_CONTENT = {"jwt-secret": "test-jwt-secret", "db-passphrase": "a" * 32}
_ADMIN_CREDENTIALS_CONTENT = {
    "username": "admin",
    "password": "TestPass-123!",
    "email": "admin@garm.local",
    "full-name": "GARM Admin",
}

_POSTGRESQL_DATA = {
    "endpoints": "10.0.0.5:5432",
    "username": "garm",
    "password": "pw",
    "database": "garm",
}

_PROVIDER_UNIT_DATA = {
    "openstack_auth_url": "https://ks1.example.com:5000/v3",
    "openstack_username": "admin1",
    "openstack_password": "pass1",
    "openstack_project_name": "proj1",
    "openstack_user_domain_name": "Default",
    "openstack_project_domain_name": "Default",
    "openstack_region_name": "RegionOne",
    "openstack_network": "net1",
}

_SCALESET_UNIT_DATA = {
    "name": "my-scaleset",
    "provider_name": "garm-configurator-0",
    "image_id": "img-1",
    "flavor": "m1.large",
    "os_arch": "amd64",
    "max_runner": "5",
    "min_idle_runner": "1",
    "repo": "myorg/myrepo",
}

_TEMPLATE_ID = 99


@pytest.fixture(name="ctx")
def ctx_fixture() -> Context:
    return Context(GarmCharm)


@dataclasses.dataclass
class _GarmApiMocks:
    """The stubbed GARM HTTP surface.

    Attributes:
        client: charm.GarmApiClient — the unauthenticated client used for first-run.
        auth: charm.GarmAuthenticatedClient.
        auth_client: The authenticated client instance every reconciler is built against.
        github: charm.GithubReconciler.
        entity: charm.EntityReconciler.
        scaleset: charm.ScalesetReconciler.
        apply_template: charm._apply_garm_template, returning _TEMPLATE_ID.
        calls: Parent mock recording the reconcile steps in the order they run.
    """

    client: MagicMock
    auth: MagicMock
    auth_client: MagicMock
    github: MagicMock
    entity: MagicMock
    scaleset: MagicMock
    apply_template: MagicMock
    calls: MagicMock


@pytest.fixture(name="garm_api")
def garm_api_fixture() -> typing.Iterator[_GarmApiMocks]:
    """Stub GARM's HTTP surface, recording the reconcile steps in call order."""
    with (
        patch("charm.GarmApiClient") as client_cls,
        patch("charm.GarmAuthenticatedClient") as auth_cls,
        patch("charm.GithubReconciler") as github_cls,
        patch("charm.EntityReconciler") as entity_cls,
        patch("charm.ScalesetReconciler") as scaleset_cls,
        patch("charm._apply_garm_template", return_value=_TEMPLATE_ID) as apply_template,
    ):
        auth_client = auth_cls.from_login.return_value
        calls = MagicMock()
        calls.attach_mock(auth_client.update_controller, "controller")
        calls.attach_mock(github_cls.return_value.reconcile, "github")
        calls.attach_mock(entity_cls.return_value.reconcile, "entity")
        calls.attach_mock(scaleset_cls.return_value.reconcile, "scaleset")
        yield _GarmApiMocks(
            client=client_cls,
            auth=auth_cls,
            auth_client=auth_client,
            github=github_cls,
            entity=entity_cls,
            scaleset=scaleset_cls,
            apply_template=apply_template,
            calls=calls,
        )


def _owned_secrets(admin_content: dict | None = None) -> list[Secret]:
    """The two labelled secrets a leader creates, as they exist on later reconciles."""
    return [
        Secret(label=GARM_SECRETS_LABEL, owner="app", tracked_content=_GARM_SECRETS_CONTENT),
        Secret(
            label=GARM_ADMIN_CREDENTIALS_LABEL,
            owner="app",
            tracked_content=_ADMIN_CREDENTIALS_CONTENT if admin_content is None else admin_content,
        ),
    ]


def _state(
    *,
    leader: bool = True,
    can_connect: bool = True,
    postgresql_data: dict | None = None,
    configurator_related: bool = True,
    configurator_units_data: dict[int, dict] | None = None,
    debug_ssh_related: bool = False,
    secrets: typing.Sequence[Secret] = (),
    unit_status: ops.StatusBase | None = None,
    app_status: ops.StatusBase | None = None,
) -> State:
    """Build a GARM charm State that is ready to serve unless a caller opts out.

    Defaults to a leader whose workload is reachable, whose postgresql relation carries
    connection data, and whose single configurator unit publishes a full OpenStack provider
    and scaleset spec — the state in which restart() runs end to end.
    """
    relations: list[Relation | PeerRelation] = [
        Relation(
            endpoint="postgresql",
            remote_app_name="postgresql",
            remote_app_data=_POSTGRESQL_DATA if postgresql_data is None else postgresql_data,
        ),
        PeerRelation(
            endpoint="secret-storage", local_app_data={_SECRET_STORAGE_KEY: "peer-secret-key"}
        ),
    ]
    if configurator_related:
        relations.append(
            Relation(
                endpoint=GARM_CONFIGURATOR_RELATION_NAME,
                remote_app_name="garm-configurator",
                remote_units_data=(
                    {0: {**_PROVIDER_UNIT_DATA, **_SCALESET_UNIT_DATA}}
                    if configurator_units_data is None
                    else configurator_units_data
                ),
            )
        )
    if debug_ssh_related:
        relations.append(
            Relation(
                endpoint=DEBUG_SSH_INTEGRATION_NAME,
                remote_app_name="tmate-ssh-server",
                remote_units_data={0: {}},
            )
        )
    statuses = {}
    if unit_status is not None:
        statuses["unit_status"] = unit_status
    if app_status is not None:
        statuses["app_status"] = app_status
    return State(
        leader=leader,
        model=Model(name=MODEL_NAME),
        containers=[
            Container(name=CONTAINER_NAME, can_connect=can_connect, layers={"garm": _ROCK_LAYER})
        ],
        relations=relations,
        secrets=list(secrets),
        **statuses,
    )


def _secret_content(state: State, label: str) -> dict[str, str]:
    """Return the content of the state's secret with the given label."""
    return next(secret for secret in state.secrets if secret.label == label).tracked_content


def _service_environment(state: State) -> dict[str, str]:
    """Return the app service's environment from the state's effective Pebble plan."""
    return state.get_container(CONTAINER_NAME).plan.services[SERVICE_NAME].environment


def _stop_workload(state: State) -> State:
    """Stop the app service, so that a subsequent replan is observable as a restart."""
    container = state.get_container(CONTAINER_NAME)
    stopped = dataclasses.replace(
        container,
        service_statuses={
            **container.service_statuses,
            SERVICE_NAME: pebble.ServiceStatus.INACTIVE,
        },
    )
    return dataclasses.replace(state, containers={stopped})


def _workload_status(state: State) -> pebble.ServiceStatus:
    """Return the app service's status in the given state."""
    return state.get_container(CONTAINER_NAME).service_statuses[SERVICE_NAME]


# --- Secrets -------------------------------------------------------------------------------


def test_leader_creates_garm_secrets(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: A leader unit with no GARM secrets yet.
    act: Run install.
    assert: Both labelled secrets are created, so other units can fetch them by label.
    """
    out = ctx.run(ctx.on.install(), _state())

    assert {secret.label for secret in out.secrets} == {
        GARM_SECRETS_LABEL,
        GARM_ADMIN_CREDENTIALS_LABEL,
    }


def test_non_leader_creates_no_secrets(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: A unit that is not the Juju leader.
    act: Run install.
    assert: No secrets are created — only the leader may create them.
    """
    out = ctx.run(ctx.on.install(), _state(leader=False))

    assert not out.secrets


def test_existing_secrets_are_not_regenerated(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: A leader whose GARM secrets already exist.
    act: Run install.
    assert: Their contents are untouched — regenerating them would invalidate every
        JWT GARM has issued and orphan its encrypted database rows.
    """
    out = ctx.run(ctx.on.install(), _state(secrets=_owned_secrets()))

    assert _secret_content(out, GARM_SECRETS_LABEL) == _GARM_SECRETS_CONTENT
    assert _secret_content(out, GARM_ADMIN_CREDENTIALS_LABEL) == _ADMIN_CREDENTIALS_CONTENT


def test_secrets_are_created_before_the_workload_is_ready(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: A leader whose workload container is not reachable yet.
    act: Run install.
    assert: The secrets exist even though the charm stops at the readiness gate, so they are
        in place on install/leader-elected before pebble comes up.
    """
    out = ctx.run(ctx.on.install(), _state(can_connect=False))

    assert {secret.label for secret in out.secrets} == {
        GARM_SECRETS_LABEL,
        GARM_ADMIN_CREDENTIALS_LABEL,
    }
    assert out.unit_status == ops.WaitingStatus("Waiting for pebble ready")


def test_non_leader_waits_for_the_leader_to_create_secrets(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: A non-leader unit before the leader has created the GARM secrets.
    act: Run update-status.
    assert: The unit waits rather than rendering a config without a JWT secret.
    """
    out = ctx.run(ctx.on.update_status(), _state(leader=False))

    assert out.unit_status == ops.WaitingStatus("Waiting for GARM secrets")


# --- Workload configuration ---------------------------------------------------------------


def test_workload_is_configured_from_relation_data(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: A ready charm whose configurator unit publishes OpenStack credentials.
    act: Run update-status.
    assert: GARM's config.toml carries the postgresql connection and names the provider, the
        provider's clouds.yaml is pushed alongside it, and the service runs GARM against
        that config.
    """
    with patch.dict(os.environ, {}, clear=True):
        out = ctx.run(ctx.on.update_status(), _state())

    container = out.get_container(CONTAINER_NAME)
    root = container.get_filesystem(ctx)
    config = tomllib.loads((root / "etc/garm/config.toml").read_text())
    assert config["database"]["postgresql"]["hostname"] == "10.0.0.5"
    assert config["database"]["postgresql"]["port"] == 5432
    assert config["database"]["postgresql"]["username"] == "garm"
    assert config["provider"][0]["name"] == "garm-configurator-0"

    clouds = yaml.safe_load((root / "etc/garm/clouds-garm-configurator-0.yaml").read_text())
    assert clouds["clouds"]["garm-configurator-0"]["auth"]["password"] == "pass1"

    assert (
        container.plan.services[SERVICE_NAME].command
        == "/usr/local/bin/garm -config /etc/garm/config.toml"
    )
    assert out.unit_status == ops.ActiveStatus()


def test_workload_is_not_configured_without_postgresql_data(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: A postgresql relation that has not published connection data yet.
    act: Run update-status.
    assert: The workload is left unconfigured — GARM cannot start without a database — and the
        unit reports the missing integration.
    """
    out = ctx.run(ctx.on.update_status(), _state(postgresql_data={}))

    assert SERVICE_NAME not in out.get_container(CONTAINER_NAME).plan.services
    assert out.unit_status == ops.BlockedStatus("missing integrations: postgresql")


def test_proxy_vars_reach_the_workload(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: Juju model proxy config for HTTP and HTTPS.
    act: Run update-status.
    assert: Both case variants land in the service environment, where GARM and the provider
        executables it forks read them.
    """
    proxy = {
        "JUJU_CHARM_HTTP_PROXY": "http://proxy.example.com:3128",
        "JUJU_CHARM_HTTPS_PROXY": "https://proxy.example.com:3129",
    }
    with patch.dict(os.environ, proxy, clear=True):
        out = ctx.run(ctx.on.update_status(), _state())

    environment = _service_environment(out)
    assert environment["http_proxy"] == "http://proxy.example.com:3128"
    assert environment["HTTP_PROXY"] == "http://proxy.example.com:3128"
    assert environment["https_proxy"] == "https://proxy.example.com:3129"
    assert environment["HTTPS_PROXY"] == "https://proxy.example.com:3129"


def test_unchanged_config_does_not_restart_the_workload(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: A charm that has already configured the workload, with the service since stopped.
    act: Run update-status again against the same config.
    assert: The service is left stopped — an unchanged config must not replan — while the
        GARM-side reconcile still runs.
    """
    with patch.dict(os.environ, {}, clear=True):
        configured = ctx.run(ctx.on.update_status(), _state())
        out = ctx.run(ctx.on.update_status(), _stop_workload(configured))

    assert _workload_status(out) == pebble.ServiceStatus.INACTIVE
    assert out.unit_status == ops.ActiveStatus()


def test_proxy_value_change_restarts_the_workload(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: A configured workload whose model proxy then changes value only — the same
        variable stays set, so the variable names embedded in the TOML do not change.
    act: Run update-status.
    assert: The service is replanned with the new value, i.e. a value-only change is detected
        rather than being missed as an unchanged config.
    """
    with patch.dict(os.environ, {"JUJU_CHARM_HTTP_PROXY": "http://proxy-a:3128"}, clear=True):
        configured = ctx.run(ctx.on.update_status(), _state())
    with patch.dict(os.environ, {"JUJU_CHARM_HTTP_PROXY": "http://proxy-b:3128"}, clear=True):
        out = ctx.run(ctx.on.update_status(), _stop_workload(configured))

    environment = _service_environment(out)
    assert environment["http_proxy"] == "http://proxy-b:3128"
    assert environment["HTTP_PROXY"] == "http://proxy-b:3128"
    assert _workload_status(out) == pebble.ServiceStatus.ACTIVE


def test_clearing_the_proxy_removes_it_from_the_workload(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: A configured workload whose model proxy is then cleared.
    act: Run update-status.
    assert: The proxy variables are gone from the running service's environment rather than
        lingering from the previous layer.
    """
    with patch.dict(os.environ, {"JUJU_CHARM_HTTP_PROXY": "http://proxy-a:3128"}, clear=True):
        configured = ctx.run(ctx.on.update_status(), _state())
    with patch.dict(os.environ, {}, clear=True):
        out = ctx.run(ctx.on.update_status(), configured)

    environment = _service_environment(out)
    assert "http_proxy" not in environment
    assert "HTTP_PROXY" not in environment


# --- garm-configurator relation gating ----------------------------------------------------


def test_missing_configurator_relation_prunes_orphaned_scalesets(
    ctx: Context, garm_api: _GarmApiMocks
):
    """
    arrange: A ready charm whose garm-configurator relation has been removed.
    act: Run update-status.
    assert: Scalesets are reconciled against an empty desired state, deleting the ones the
        removed relation orphaned, while the workload is left unconfigured and the unit
        reports what it is waiting for.
    """
    out = ctx.run(ctx.on.update_status(), _state(configurator_related=False))

    garm_api.scaleset.return_value.reconcile.assert_called_once_with([])
    assert SERVICE_NAME not in out.get_container(CONTAINER_NAME).plan.services
    assert out.unit_status == ops.WaitingStatus("Waiting for garm-configurator relation")


def test_unpopulated_configurator_relation_does_not_prune(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: A garm-configurator relation that is present but has not published its
        secret-dependent fields yet.
    act: Run update-status.
    assert: Scalesets are NOT reconciled — pruning against the empty desired state would
        delete live scalesets — and the unit waits for the relation to finish publishing.
    """
    out = ctx.run(ctx.on.update_status(), _state(configurator_units_data={0: {}}))

    garm_api.scaleset.assert_not_called()
    assert out.unit_status == ops.WaitingStatus("Waiting for garm-configurator relation")


def test_missing_configurator_relation_refreshes_stale_app_status(
    ctx: Context, garm_api: _GarmApiMocks
):
    """
    arrange: A stale app status and no garm-configurator relation.
    act: Run update-status.
    assert: Both unit and app status report the wait, so the app status cannot freeze stale.
    """
    stale = ops.WaitingStatus("Waiting for pebble ready")
    out = ctx.run(
        ctx.on.update_status(),
        _state(configurator_related=False, unit_status=stale, app_status=stale),
    )

    assert out.unit_status == ops.WaitingStatus("Waiting for garm-configurator relation")
    assert out.app_status == ops.WaitingStatus("Waiting for garm-configurator relation")


# --- First-run initialisation -------------------------------------------------------------


def test_first_run_initialises_garm_with_the_stored_credentials(
    ctx: Context, garm_api: _GarmApiMocks
):
    """
    arrange: A leader whose GARM reports itself uninitialised.
    act: Run update-status.
    assert: first-run is called with the credentials the charm actually stored in the secret,
        so the operator can log in with what `juju secret-get` returns.
    """
    garm_api.client.return_value.is_initialized.return_value = False

    out = ctx.run(ctx.on.update_status(), _state())

    credentials = _secret_content(out, GARM_ADMIN_CREDENTIALS_LABEL)
    garm_api.client.return_value.first_run.assert_called_once_with(
        username=credentials["username"],
        password=credentials["password"],
        email=credentials["email"],
        full_name=credentials["full-name"],
    )


def test_first_run_skipped_when_garm_is_already_initialised(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: A leader whose GARM reports itself initialised.
    act: Run update-status.
    assert: first-run is not called again.
    """
    garm_api.client.return_value.is_initialized.return_value = True

    ctx.run(ctx.on.update_status(), _state())

    garm_api.client.return_value.first_run.assert_not_called()


def test_first_run_skipped_when_not_leader(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: A non-leader unit that can already read the GARM secrets.
    act: Run update-status.
    assert: No GARM API call is made — only the leader initialises the shared controller.
    """
    ctx.run(ctx.on.update_status(), _state(leader=False, secrets=_owned_secrets()))

    garm_api.client.assert_not_called()


def test_first_run_skipped_when_credentials_are_incomplete(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: A leader whose existing admin-credentials secret is missing the password. Secret
        creation skips labels that already exist, so an incomplete secret survives.
    act: Run update-status.
    assert: GARM is never contacted — a half-built admin account would lock the operator out.
    """
    secrets = _owned_secrets(admin_content={"username": "admin"})

    with patch.object(GarmCharm, "_reconcile_runners"):
        ctx.run(ctx.on.update_status(), _state(secrets=secrets))

    garm_api.client.assert_not_called()


@pytest.mark.parametrize(
    "error_message",
    ["refused", "GARM did not become ready within 30s"],
    ids=["connection-refused", "timeout"],
)
def test_first_run_connection_error_errors_out_for_retry(
    ctx: Context, garm_api: _GarmApiMocks, error_message: str
):
    """
    arrange: A GARM that never becomes reachable.
    act: Run update-status.
    assert: The error propagates so Juju retries the hook, and initialisation is not attempted
        against an unreachable GARM.
    """
    garm_api.client.return_value.wait_for_ready.side_effect = GarmConnectionError(error_message)

    with pytest.raises(UncaughtCharmError) as exc_info:
        ctx.run(ctx.on.update_status(), _state())

    assert isinstance(exc_info.value.__cause__, GarmConnectionError)
    garm_api.client.return_value.is_initialized.assert_not_called()


# --- The get-credentials action -----------------------------------------------------------


def test_get_credentials_action_returns_the_stored_credentials(
    ctx: Context, garm_api: _GarmApiMocks
):
    """
    arrange: A leader whose admin-credentials secret exists.
    act: Run the get-credentials action.
    assert: The results carry the credentials an operator needs to log into GARM, read from
        the secret rather than regenerated.
    """
    ctx.run(ctx.on.action("get-credentials"), _state(secrets=_owned_secrets()))

    assert ctx.action_results == _ADMIN_CREDENTIALS_CONTENT


def test_get_credentials_action_fails_before_the_credentials_exist(
    ctx: Context, garm_api: _GarmApiMocks
):
    """
    arrange: A charm that cannot read its admin-credentials secret.
    act: Run the get-credentials action.
    assert: The action fails rather than returning an empty result, so the operator can tell
        the credentials are not ready yet from a partial answer.
    """
    with patch.object(GarmCharm, "_get_admin_credentials", return_value=None):
        with pytest.raises(ActionFailed) as exc_info:
            ctx.run(ctx.on.action("get-credentials"), _state())

    assert "not yet available" in exc_info.value.message
    assert ctx.action_results is None


# --- Reconciling GARM ---------------------------------------------------------------------


def test_reconcilers_run_in_dependency_order(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: A ready charm.
    act: Run update-status.
    assert: Controller URLs are configured first — GARM 409s every operational call until they
        are set — then credentials, entities and scalesets reconcile in that order, since
        entities reference a credential and scalesets are created under an entity. All of them
        run against the one authenticated client.
    """
    ctx.run(ctx.on.update_status(), _state())

    assert [name for name, _, _ in garm_api.calls.mock_calls] == [
        "controller",
        "github",
        "entity",
        "scaleset",
    ]
    garm_api.github.assert_called_once_with(garm_api.auth_client)
    garm_api.entity.assert_called_once_with(garm_api.auth_client)
    garm_api.scaleset.assert_called_once_with(garm_api.auth_client)


def test_reconcile_authenticates_against_the_local_garm_listener(
    ctx: Context, garm_api: _GarmApiMocks
):
    """
    arrange: A ready charm.
    act: Run update-status.
    assert: The charm logs in over GARM's fixed local listener with the stored admin
        credentials, rather than a config-derived URL that is unset for the local API.
    """
    out = ctx.run(ctx.on.update_status(), _state())

    credentials = _secret_content(out, GARM_ADMIN_CREDENTIALS_LABEL)
    garm_api.auth.from_login.assert_called_once_with(
        f"http://127.0.0.1:{GARM_PORT}/api/v1",
        credentials["username"],
        credentials["password"],
    )


def test_reconcile_skipped_when_admin_credentials_are_unavailable(
    ctx: Context, garm_api: _GarmApiMocks
):
    """
    arrange: A charm that cannot read its admin-credentials secret. A leader recreates that
        secret on every reconcile, so this models the secret store failing rather than a state
        the charm reaches on its own — hence the patch.
    act: Run update-status.
    assert: No GARM connection is attempted with credentials the charm does not have.
    """
    with patch.object(GarmCharm, "_get_admin_credentials", return_value=None):
        ctx.run(ctx.on.update_status(), _state())

    garm_api.auth.from_login.assert_not_called()


def test_successful_reconcile_refreshes_stale_app_status(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: A stale unit and app status, and a reconcile that will succeed.
    act: Run update-status.
    assert: Both refresh to active, so the app status cannot freeze stale.
    """
    stale = ops.WaitingStatus("Waiting for pebble ready")

    out = ctx.run(ctx.on.update_status(), _state(unit_status=stale, app_status=stale))

    assert out.unit_status == ops.ActiveStatus()
    assert out.app_status == ops.ActiveStatus()


def test_charmed_template_error_degrades_to_waiting(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: A charm whose charmed runner template cannot be applied, on the reconcile that
        also rewrites the workload config — the path where the framework's restart reports
        active unconditionally.
    act: Run update-status.
    assert: Unit and app wait carrying the error message rather than erroring or reporting a
        spurious active, and scalesets are not reconciled — each one references the template.
    """
    garm_api.apply_template.side_effect = garm_template.CharmedTemplateError(
        "base template missing"
    )

    out = ctx.run(ctx.on.update_status(), _state())

    assert SERVICE_NAME in out.get_container(CONTAINER_NAME).plan.services
    assert out.unit_status == ops.WaitingStatus("base template missing")
    assert out.app_status == ops.WaitingStatus("base template missing")
    garm_api.scaleset.return_value.reconcile.assert_not_called()


# --- Desired state from relation data -----------------------------------------------------


def _github_unit_data(secret_id: str, app_id: str = "12345", installation_id: str = "67890"):
    """Build the GitHub App fields a configurator unit publishes."""
    return {
        "github_app_id": app_id,
        "github_installation_id": installation_id,
        "github_private_key_secret_uri": secret_id,
    }


def test_github_credential_is_built_from_relation_data(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: A configurator unit publishing a GitHub App id, installation id and a secret URI
        for the private key.
    act: Run update-status.
    assert: One credential is reconciled on GARM's built-in github.com endpoint, with the
        private key resolved from the Juju secret rather than the databag.
    """
    key_secret = Secret(tracked_content={"value": "PEMDATA"})
    state = _state(
        configurator_units_data={0: {**_PROVIDER_UNIT_DATA, **_github_unit_data(key_secret.id)}},
        secrets=[key_secret],
    )

    ctx.run(ctx.on.update_status(), state)

    garm_api.github.return_value.reconcile.assert_called_once_with(
        [
            CredentialSpec(
                name="app-12345-67890",
                endpoint=DEFAULT_GITHUB_ENDPOINT,
                app_id=12345,
                installation_id=67890,
                private_key="PEMDATA",
                description=MANAGED_CREDENTIAL_DESCRIPTION,
            )
        ]
    )


def test_units_sharing_a_github_app_yield_one_credential(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: Two configurator units sharing one GitHub App and installation.
    act: Run update-status.
    assert: They collapse to a single credential.
    """
    key_secret = Secret(tracked_content={"value": "PEMDATA"})
    unit_data = {**_PROVIDER_UNIT_DATA, **_github_unit_data(key_secret.id, "1", "2")}
    state = _state(
        configurator_units_data={0: dict(unit_data), 1: dict(unit_data)},
        secrets=[key_secret],
    )

    ctx.run(ctx.on.update_status(), state)

    (credentials,) = garm_api.github.return_value.reconcile.call_args.args
    assert len(credentials) == 1


@pytest.mark.parametrize(
    "github_data",
    [
        pytest.param({"github_app_id": "1"}, id="missing-fields"),
        pytest.param(
            _github_unit_data("secret:unavailable", app_id="not-a-number"), id="non-numeric-ids"
        ),
        pytest.param(_github_unit_data("secret:unavailable"), id="unreadable-key-secret"),
    ],
)
def test_incomplete_github_config_yields_no_credential(
    ctx: Context, garm_api: _GarmApiMocks, github_data: dict
):
    """
    arrange: A configurator unit whose GitHub App fields are incomplete, non-numeric, or name
        a private-key secret this unit cannot read.
    act: Run update-status.
    assert: No credential is built — GARM rejects a partial one.
    """
    state = _state(configurator_units_data={0: {**_PROVIDER_UNIT_DATA, **github_data}})

    ctx.run(ctx.on.update_status(), state)

    garm_api.github.return_value.reconcile.assert_called_once_with([])


def test_scaleset_is_built_from_relation_data(ctx: Context, garm_api: _GarmApiMocks):
    """
    arrange: A configurator unit publishing a full scaleset spec naming a repo.
    act: Run update-status.
    assert: The scaleset is reconciled against the repository entity and references the
        charmed template that was ensured before it.
    """
    ctx.run(ctx.on.update_status(), _state())

    (scalesets,) = garm_api.scaleset.return_value.reconcile.call_args.args
    assert len(scalesets) == 1
    scaleset = scalesets[0]
    assert scaleset.name == "my-scaleset"
    assert scaleset.entity_type == "repository"
    assert scaleset.entity_name == "myorg/myrepo"
    assert scaleset.max_runners == 5
    assert scaleset.min_idle_runners == 1
    assert scaleset.template_id == _TEMPLATE_ID


# --- Controller URLs ----------------------------------------------------------------------


def test_controller_urls_default_to_the_kubernetes_service_url(
    ctx: Context, garm_api: _GarmApiMocks
):
    """
    arrange: A ready charm with no ingress.
    act: Run update-status.
    assert: The controller URLs point at the in-cluster service, which runners reach for
        metadata and callbacks.
    """
    ctx.run(ctx.on.update_status(), _state())

    base = f"http://garm.{MODEL_NAME}:{GARM_PORT}"
    garm_api.auth_client.update_controller.assert_called_once_with(
        metadata_url=f"{base}/api/v1/metadata",
        callback_url=f"{base}/api/v1/callbacks",
        webhook_url=f"{base}/webhooks",
    )


@pytest.mark.parametrize(
    "base_url",
    ["https://garm.example.com", "https://garm.example.com/"],
    ids=["plain", "trailing-slash"],
)
def test_controller_urls_derive_from_the_ingress_url(
    ctx: Context, garm_api: _GarmApiMocks, base_url: str
):
    """
    arrange: Ingress supplies the application's base URL, with and without a trailing slash.
    act: Run update-status.
    assert: The pushed URLs are the same either way, with no double slashes in their paths.
    """
    with patch.object(GarmCharm, "_base_url", new_callable=PropertyMock, return_value=base_url):
        ctx.run(ctx.on.update_status(), _state())

    garm_api.auth_client.update_controller.assert_called_once_with(
        metadata_url="https://garm.example.com/api/v1/metadata",
        callback_url="https://garm.example.com/api/v1/callbacks",
        webhook_url="https://garm.example.com/webhooks",
    )


# --- Event wiring -------------------------------------------------------------------------


def _relation(state: State, endpoint: str) -> Relation:
    """Return the state's relation on the given endpoint."""
    return next(relation for relation in state.relations if relation.endpoint == endpoint)  # type: ignore[return-value]


_OBSERVED_EVENTS = [
    pytest.param(lambda ctx, _: ctx.on.install(), id="install"),
    pytest.param(lambda ctx, _: ctx.on.leader_elected(), id="leader-elected"),
    pytest.param(lambda ctx, _: ctx.on.update_status(), id="update-status"),
]
for _endpoint, _id in (
    (GARM_CONFIGURATOR_RELATION_NAME, "configurator"),
    (DEBUG_SSH_INTEGRATION_NAME, "debug-ssh"),
):
    _OBSERVED_EVENTS += [
        pytest.param(
            lambda ctx, state, endpoint=_endpoint: ctx.on.relation_joined(
                _relation(state, endpoint)
            ),
            id=f"{_id}-relation-joined",
        ),
        pytest.param(
            lambda ctx, state, endpoint=_endpoint: ctx.on.relation_changed(
                _relation(state, endpoint)
            ),
            id=f"{_id}-relation-changed",
        ),
        pytest.param(
            lambda ctx, state, endpoint=_endpoint: ctx.on.relation_departed(
                _relation(state, endpoint), remote_unit=0
            ),
            id=f"{_id}-relation-departed",
        ),
        pytest.param(
            lambda ctx, state, endpoint=_endpoint: ctx.on.relation_broken(
                _relation(state, endpoint)
            ),
            id=f"{_id}-relation-broken",
        ),
    ]


@pytest.mark.parametrize("event", _OBSERVED_EVENTS)
def test_every_observed_event_reconciles(
    ctx: Context, garm_api: _GarmApiMocks, event: typing.Callable
):
    """
    arrange: A ready charm related to garm-configurator and debug-ssh.
    act: Run each event the charm observes.
    assert: Every one drives a full reconcile. The charm holds no per-event delta logic, so an
        observer that is missed leaves GARM unsynced until the next hook happens to fire.
    """
    state = _state(debug_ssh_related=True)

    ctx.run(event(ctx, state), state)

    garm_api.auth.from_login.assert_called_once()
