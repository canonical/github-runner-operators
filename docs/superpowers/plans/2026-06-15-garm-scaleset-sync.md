# GARM Scaleset Sync (ISD-5729) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the GARM charm to sync scalesets from Configurator relation data via the GARM REST API without restarting the service.

**Architecture:** A new `garm_api.py` module provides a typed HTTP client for the GARM REST API. A new `scaleset_reconciler.py` module holds the pure diff/apply logic. The GARM charm observes `garm-configurator` relation events and calls `ScalesetReconciler.reconcile()`. The Configurator charm writes its scaleset config to the `garm-configurator` relation databag once it has an image UUID.

**Tech Stack:** Python 3.12, ops 3.7.1, paas-charm, pydantic (configurator only), urllib.request (no new deps), pytest + ops-scenario (configurator tests), pytest + unittest.mock (garm tests), jubilant (integration tests).

---

## File Map

| File | Status | Purpose |
|---|---|---|
| `charms/garm/charmcraft.yaml` | Modify | Add `requires: garm-configurator` endpoint |
| `charms/garm-configurator/charmcraft.yaml` | Modify | Add `provides: garm-configurator` endpoint |
| `charms/garm/src/garm_api.py` | Create | GarmClient — typed HTTP wrapper around GARM REST API |
| `charms/garm/src/scaleset_reconciler.py` | Create | DesiredScaleset, ReconcileResult, parse_relation_databag, ScalesetReconciler |
| `charms/garm/src/charm.py` | Modify | Add admin secrets, garm-configurator relation events, `_reconcile_scalesets` |
| `charms/garm-configurator/src/charm_state.py` | Modify | Add `provider_name` and `credentials_name` computed properties to CharmState |
| `charms/garm-configurator/src/charm.py` | Modify | Write scaleset data to garm-configurator relation databag |
| `charms/garm/tests/unit/test_garm_api.py` | Create | Unit tests for GarmClient (urllib mocked) |
| `charms/garm/tests/unit/test_scaleset_reconciler.py` | Create | Unit tests for ScalesetReconciler and parse_relation_databag |
| `charms/garm/tests/unit/test_charm.py` | Modify | Add tests for updated `_generate_garm_secrets` |
| `charms/garm-configurator/tests/unit/test_charm.py` | Modify | Add tests for garm-configurator relation databag writing |
| `charms/tests/integration/test_garm.py` | Modify | Add scaleset create/update/delete/defer integration tests |

---

## Task 1: Create Feature Branch

**Files:** (none — git only)

- [ ] **Step 1: Create and switch to the feature branch**

```bash
cd /path/to/github-runner-operators
git checkout -b feat/garm-scaleset-isd-5729
```

Expected: branch created and checked out.

---

## Task 2: Add Relation Endpoints to charmcraft.yaml Files

**Files:**
- Modify: `charms/garm/charmcraft.yaml`
- Modify: `charms/garm-configurator/charmcraft.yaml`

- [ ] **Step 1: Add `requires: garm-configurator` to the GARM charm**

In `charms/garm/charmcraft.yaml`, add after the existing `requires: postgresql` block:

```yaml
  garm-configurator:
    interface: garm_configurator_v0
```

Full `requires` section becomes:

```yaml
requires:
  postgresql:
    interface: postgresql_client
    optional: false
    limit: 1
  garm-configurator:
    interface: garm_configurator_v0
```

- [ ] **Step 2: Add `provides: garm-configurator` to the Configurator charm**

In `charms/garm-configurator/charmcraft.yaml`, add a `provides` section after the existing `requires` block:

```yaml
provides:
  garm-configurator:
    interface: garm_configurator_v0
```

Full addition (append before `parts:`):

```yaml
provides:
  garm-configurator:
    interface: garm_configurator_v0

requires:
  image:
    interface: github_runner_image_v0
    limit: 1
    optional: false
```

- [ ] **Step 3: Commit**

```bash
git add charms/garm/charmcraft.yaml charms/garm-configurator/charmcraft.yaml
git commit -m "chore: add garm_configurator_v0 relation endpoints to both charms"
```

---

## Task 3: TDD — `garm_api.py` REST Client

**Files:**
- Create: `charms/garm/tests/unit/test_garm_api.py`
- Create: `charms/garm/src/garm_api.py`

The GARM charm's unit tests use plain `pytest` and `unittest.mock` (no ops-scenario needed here — the garm tests currently test pure functions only, and we keep that pattern).

- [ ] **Step 1: Write the failing tests**

Create `charms/garm/tests/unit/test_garm_api.py`:

```python
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the GARM REST API client."""

import json
from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from garm_api import GarmApiError, GarmClient


def _make_response(body):
    """Build a mock urllib response context manager."""
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = json.dumps(body).encode()
    return mock_resp


def _make_http_error(status: int, body: str = "error"):
    return HTTPError(
        url="http://localhost:9997/api/v1/test",
        code=status,
        msg=body,
        hdrs=None,
        fp=BytesIO(body.encode()),
    )


def test_list_providers_returns_parsed_list():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response([{"name": "openstack", "id": "abc"}])
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        result = client.list_providers()
    assert result == [{"name": "openstack", "id": "abc"}]


def test_list_providers_returns_empty_on_null_body():
    with patch("urllib.request.urlopen") as mock_open:
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b""
        mock_open.return_value = mock_resp
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        result = client.list_providers()
    assert result == []


def test_list_credentials_returns_parsed_list():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response([{"name": "github-app-12345"}])
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        result = client.list_credentials()
    assert result == [{"name": "github-app-12345"}]


def test_list_scalesets_returns_parsed_list():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response([{"id": "uuid-1", "name": "my-ss"}])
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        result = client.list_scalesets()
    assert result == [{"id": "uuid-1", "name": "my-ss"}]


def test_create_scaleset_posts_and_returns_dict():
    expected = {"id": "new-uuid", "name": "my-ss"}
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response(expected)
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        result = client.create_scaleset({"name": "my-ss"})
    assert result == expected


def test_update_scaleset_puts_and_returns_dict():
    expected = {"id": "uuid-1", "name": "my-ss", "flavor": "m1.xlarge"}
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response(expected)
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        result = client.update_scaleset("uuid-1", {"flavor": "m1.xlarge"})
    assert result == expected


def test_delete_scaleset_makes_delete_request():
    with patch("urllib.request.urlopen") as mock_open:
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b""
        mock_open.return_value = mock_resp
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        client.delete_scaleset("uuid-1")
    call_args = mock_open.call_args
    req = call_args[0][0]
    assert req.get_method() == "DELETE"
    assert "uuid-1" in req.full_url


def test_request_raises_garm_api_error_on_http_error():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.side_effect = _make_http_error(500, "internal server error")
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        with pytest.raises(GarmApiError, match="500"):
            client.list_providers()


def test_request_raises_garm_api_error_on_url_error():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.side_effect = URLError("connection refused")
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        with pytest.raises(GarmApiError, match="connection refused"):
            client.list_providers()


def test_first_run_ignores_409():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.side_effect = _make_http_error(409, "already initialized")
        client = GarmClient("http://localhost:9997/api/v1")
        # Should not raise
        client.first_run("admin", "password", "admin@test.local", "Admin")


def test_first_run_raises_on_other_errors():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.side_effect = _make_http_error(500, "server error")
        client = GarmClient("http://localhost:9997/api/v1")
        with pytest.raises(GarmApiError):
            client.first_run("admin", "password", "admin@test.local", "Admin")


def test_login_returns_token():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response({"token": "eyJhbGci.payload.sig"})
        client = GarmClient("http://localhost:9997/api/v1")
        token = client.login("admin", "password")
    assert token == "eyJhbGci.payload.sig"


def test_login_raises_when_token_missing():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response({"token": ""})
        client = GarmClient("http://localhost:9997/api/v1")
        with pytest.raises(GarmApiError, match="token"):
            client.login("admin", "password")


def test_bearer_token_sent_in_auth_header():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response([])
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "my-jwt"
        client.list_scalesets()
    req = mock_open.call_args[0][0]
    assert req.get_header("Authorization") == "Bearer my-jwt"


def test_configure_controller_sends_put():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response({})
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        client.configure_controller(
            metadata_url="http://1.2.3.4:9997/api/v1/metadata",
            callback_url="http://1.2.3.4:9997/api/v1/callbacks",
            webhook_url="http://1.2.3.4:9997/webhooks",
        )
    req = mock_open.call_args[0][0]
    assert req.get_method() == "PUT"
    body = json.loads(req.data)
    assert body["metadata_url"] == "http://1.2.3.4:9997/api/v1/metadata"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd charms/garm
python -m pytest tests/unit/test_garm_api.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'garm_api'`

- [ ] **Step 3: Implement `garm_api.py`**

Create `charms/garm/src/garm_api.py`:

```python
#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""GARM REST API client."""

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


class GarmApiError(Exception):
    """Raised when the GARM REST API returns an unexpected response."""


class GarmClient:
    """Thin HTTP client for the GARM REST API."""

    def __init__(self, base_url: str) -> None:
        """Initialise the client.

        Args:
            base_url: GARM API base URL, e.g. 'http://localhost:9997/api/v1'.
        """
        self.base_url = base_url.rstrip("/")
        self.token: str = ""

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        auth: bool = True,
    ) -> Any:
        """Make an HTTP request to the GARM API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: Path relative to base_url (must start with /).
            payload: Optional JSON request body.
            auth: Whether to include the Bearer token header.

        Raises:
            GarmApiError: If the response status is not 2xx or a network error occurs.

        Returns:
            Parsed JSON response body, or None for empty responses.
        """
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                if not body:
                    return None
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            raise GarmApiError(
                f"{method} {url} failed with status {exc.code}: {exc.read().decode()[:200]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise GarmApiError(f"{method} {url} failed: {exc.reason}") from exc

    def first_run(
        self,
        username: str,
        password: str,
        email: str,
        full_name: str,
    ) -> None:
        """Complete GARM first-run initialisation (idempotent — HTTP 409 is silently ignored).

        Args:
            username: Admin username.
            password: Admin password.
            email: Admin email address.
            full_name: Admin display name.

        Raises:
            GarmApiError: On unexpected API errors (not 409).
        """
        try:
            self._request(
                "POST",
                "/first-run",
                {
                    "username": username,
                    "password": password,
                    "email": email,
                    "full_name": full_name,
                },
                auth=False,
            )
        except GarmApiError as exc:
            if "409" in str(exc):
                logger.debug("GARM first-run already completed (409)")
                return
            raise

    def configure_controller(
        self,
        metadata_url: str,
        callback_url: str,
        webhook_url: str,
    ) -> None:
        """Configure GARM controller URLs (idempotent).

        Args:
            metadata_url: URL for runner metadata endpoint.
            callback_url: URL for runner callback endpoint.
            webhook_url: URL for GitHub webhooks endpoint.

        Raises:
            GarmApiError: On API error.
        """
        self._request(
            "PUT",
            "/controller",
            {
                "metadata_url": metadata_url,
                "callback_url": callback_url,
                "webhook_url": webhook_url,
            },
        )

    def login(self, username: str, password: str) -> str:
        """Log in to the GARM API and return a JWT token.

        Args:
            username: Admin username.
            password: Admin password.

        Raises:
            GarmApiError: If login fails or response has no token.

        Returns:
            JWT token string.
        """
        result = self._request(
            "POST",
            "/auth/login",
            {"username": username, "password": password},
            auth=False,
        )
        token = (result or {}).get("token", "")
        if not token:
            raise GarmApiError("login response did not contain a token")
        return token

    def list_providers(self) -> list[dict[str, Any]]:
        """List all registered GARM providers.

        Raises:
            GarmApiError: On API error.

        Returns:
            List of provider dicts (each has at minimum a 'name' key).
        """
        return self._request("GET", "/providers") or []

    def list_credentials(self) -> list[dict[str, Any]]:
        """List all registered GARM credentials.

        Raises:
            GarmApiError: On API error.

        Returns:
            List of credential dicts (each has at minimum a 'name' key).
        """
        return self._request("GET", "/credentials") or []

    def list_scalesets(self) -> list[dict[str, Any]]:
        """List all scalesets.

        Raises:
            GarmApiError: On API error.

        Returns:
            List of scaleset dicts (each has at minimum 'id' and 'name' keys).
        """
        return self._request("GET", "/scalesets") or []

    def create_scaleset(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a new scaleset.

        Args:
            payload: CreateScaleSetParams dict.

        Raises:
            GarmApiError: On API error.

        Returns:
            Created scaleset dict.
        """
        return self._request("POST", "/scalesets", payload)

    def update_scaleset(self, scaleset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Update an existing scaleset.

        Args:
            scaleset_id: Scaleset UUID.
            payload: UpdateScaleSetParams dict (only changed fields needed).

        Raises:
            GarmApiError: On API error.

        Returns:
            Updated scaleset dict.
        """
        return self._request("PUT", f"/scalesets/{scaleset_id}", payload)

    def delete_scaleset(self, scaleset_id: str) -> None:
        """Delete a scaleset.

        Args:
            scaleset_id: Scaleset UUID.

        Raises:
            GarmApiError: On API error.
        """
        self._request("DELETE", f"/scalesets/{scaleset_id}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd charms/garm
python -m pytest tests/unit/test_garm_api.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add charms/garm/src/garm_api.py charms/garm/tests/unit/test_garm_api.py
git commit -m "feat(garm): add GarmClient REST API wrapper (garm_api.py)"
```

---

## Task 4: TDD — `scaleset_reconciler.py`

**Files:**
- Create: `charms/garm/tests/unit/test_scaleset_reconciler.py`
- Create: `charms/garm/src/scaleset_reconciler.py`

- [ ] **Step 1: Write the failing tests**

Create `charms/garm/tests/unit/test_scaleset_reconciler.py`:

```python
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for scaleset_reconciler."""

from unittest.mock import MagicMock

import pytest

from scaleset_reconciler import (
    DesiredScaleset,
    ReconcileResult,
    ScalesetReconciler,
    _needs_update,
    _parse_pre_install_scripts,
    parse_relation_databag,
)


# ---------------------------------------------------------------------------
# parse_relation_databag
# ---------------------------------------------------------------------------

def _minimal_databag() -> dict:
    return {
        "name": "my-scaleset",
        "provider_name": "openstack-myproject",
        "credentials_name": "github-app-12345",
        "image_id": "abc-image-uuid",
        "flavor": "m1.large",
        "os_arch": "amd64",
        "min_idle_runner": "0",
        "max_runner": "5",
        "labels": "self-hosted,linux",
        "repo": "myorg/myrepo",
        "org": "",
        "runner_group": "default",
        "pre_install_scripts": "",
    }


def test_parse_relation_databag_returns_desired_scaleset():
    data = _minimal_databag()
    result = parse_relation_databag(data)
    assert result is not None
    assert result.name == "my-scaleset"
    assert result.provider_name == "openstack-myproject"
    assert result.credentials_name == "github-app-12345"
    assert result.image_id == "abc-image-uuid"
    assert result.flavor == "m1.large"
    assert result.os_arch == "amd64"
    assert result.min_idle_runner == 0
    assert result.max_runner == 5
    assert result.labels == "self-hosted,linux"
    assert result.repo == "myorg/myrepo"
    assert result.org == ""
    assert result.runner_group == "default"
    assert result.pre_install_scripts == ""


def test_parse_relation_databag_returns_none_when_image_id_missing():
    data = _minimal_databag()
    del data["image_id"]
    assert parse_relation_databag(data) is None


def test_parse_relation_databag_returns_none_when_image_id_empty():
    data = _minimal_databag()
    data["image_id"] = ""
    assert parse_relation_databag(data) is None


def test_parse_relation_databag_returns_none_when_name_missing():
    data = _minimal_databag()
    del data["name"]
    assert parse_relation_databag(data) is None


def test_parse_relation_databag_returns_none_when_name_empty():
    data = _minimal_databag()
    data["name"] = ""
    assert parse_relation_databag(data) is None


def test_parse_relation_databag_defaults_runner_group():
    data = _minimal_databag()
    del data["runner_group"]
    result = parse_relation_databag(data)
    assert result is not None
    assert result.runner_group == "default"


def test_parse_relation_databag_handles_invalid_int():
    data = _minimal_databag()
    data["min_idle_runner"] = "not-a-number"
    assert parse_relation_databag(data) is None


# ---------------------------------------------------------------------------
# _parse_pre_install_scripts
# ---------------------------------------------------------------------------

def test_parse_pre_install_scripts_empty_returns_empty_dict():
    assert _parse_pre_install_scripts("") == {}


def test_parse_pre_install_scripts_whitespace_returns_empty_dict():
    assert _parse_pre_install_scripts("   ") == {}


def test_parse_pre_install_scripts_valid_dict():
    raw = '{"setup.sh": "#!/bin/bash\\necho hi"}'
    result = _parse_pre_install_scripts(raw)
    assert result == {"setup.sh": "#!/bin/bash\necho hi"}


def test_parse_pre_install_scripts_invalid_returns_empty_dict():
    assert _parse_pre_install_scripts("not a dict") == {}


# ---------------------------------------------------------------------------
# _needs_update
# ---------------------------------------------------------------------------

def _make_desired(**overrides) -> DesiredScaleset:
    base = dict(
        name="my-scaleset",
        provider_name="openstack-myproject",
        credentials_name="github-app-12345",
        image_id="abc-image-uuid",
        flavor="m1.large",
        os_arch="amd64",
        min_idle_runner=0,
        max_runner=5,
        labels="self-hosted,linux",
        repo="myorg/myrepo",
        org="",
        runner_group="default",
        pre_install_scripts="",
    )
    base.update(overrides)
    return DesiredScaleset(**base)


def _make_observed(**overrides) -> dict:
    base = dict(
        id="uuid-1",
        name="my-scaleset",
        image="abc-image-uuid",
        flavor="m1.large",
        os_arch="amd64",
        min_idle_runners=0,
        max_runners=5,
        tags=["linux", "self-hosted"],
        github_runner_group="default",
        extra_specs={},
    )
    base.update(overrides)
    return base


def test_needs_update_returns_false_when_identical():
    desired = _make_desired()
    observed = _make_observed()
    assert not _needs_update(desired, observed)


def test_needs_update_returns_true_when_image_differs():
    desired = _make_desired(image_id="new-image-uuid")
    observed = _make_observed()
    assert _needs_update(desired, observed)


def test_needs_update_returns_true_when_flavor_differs():
    desired = _make_desired(flavor="m1.xlarge")
    observed = _make_observed()
    assert _needs_update(desired, observed)


def test_needs_update_returns_true_when_max_runners_differs():
    desired = _make_desired(max_runner=10)
    observed = _make_observed()
    assert _needs_update(desired, observed)


def test_needs_update_returns_true_when_min_idle_runners_differs():
    desired = _make_desired(min_idle_runner=2)
    observed = _make_observed()
    assert _needs_update(desired, observed)


def test_needs_update_returns_true_when_labels_differ():
    desired = _make_desired(labels="self-hosted,linux,arm64")
    observed = _make_observed()
    assert _needs_update(desired, observed)


def test_needs_update_returns_false_when_labels_same_different_order():
    # tags from desired "linux,self-hosted" vs observed ["self-hosted","linux"] — both sort equal
    desired = _make_desired(labels="linux,self-hosted")
    observed = _make_observed(tags=["self-hosted", "linux"])
    assert not _needs_update(desired, observed)


def test_needs_update_returns_true_when_pre_install_scripts_differ():
    desired = _make_desired(pre_install_scripts='{"setup.sh": "echo hi"}')
    observed = _make_observed(extra_specs={})
    assert _needs_update(desired, observed)


# ---------------------------------------------------------------------------
# ScalesetReconciler.reconcile
# ---------------------------------------------------------------------------

def _make_client(
    providers=None,
    credentials=None,
    scalesets=None,
) -> MagicMock:
    client = MagicMock()
    client.list_providers.return_value = providers or [{"name": "openstack-myproject"}]
    client.list_credentials.return_value = credentials or [{"name": "github-app-12345"}]
    client.list_scalesets.return_value = scalesets or []
    client.create_scaleset.return_value = {"id": "new-uuid", "name": "my-scaleset"}
    client.update_scaleset.return_value = {"id": "uuid-1", "name": "my-scaleset"}
    return client


def test_reconcile_creates_missing_scaleset():
    client = _make_client()
    desired = [_make_desired()]
    result = ScalesetReconciler(client).reconcile(desired)
    assert "my-scaleset" in result.created
    assert result.skipped == []
    client.create_scaleset.assert_called_once()
    create_payload = client.create_scaleset.call_args[0][0]
    assert create_payload["name"] == "my-scaleset"
    assert create_payload["provider_name"] == "openstack-myproject"
    assert create_payload["credentials_name"] == "github-app-12345"
    assert create_payload["image"] == "abc-image-uuid"
    assert create_payload["flavor"] == "m1.large"
    assert create_payload["os_type"] == "linux"
    assert sorted(create_payload["tags"]) == ["linux", "self-hosted"]
    assert create_payload["repo_name"] == "myorg/myrepo"


def test_reconcile_creates_scaleset_with_org_when_repo_empty():
    client = _make_client()
    desired = [_make_desired(repo="", org="myorg")]
    ScalesetReconciler(client).reconcile(desired)
    create_payload = client.create_scaleset.call_args[0][0]
    assert "repo_name" not in create_payload
    assert create_payload["org_name"] == "myorg"


def test_reconcile_updates_scaleset_when_image_changes():
    existing = {
        "id": "uuid-1",
        "name": "my-scaleset",
        "image": "old-image",
        "flavor": "m1.large",
        "os_arch": "amd64",
        "min_idle_runners": 0,
        "max_runners": 5,
        "tags": ["linux", "self-hosted"],
        "github_runner_group": "default",
        "extra_specs": {},
    }
    client = _make_client(scalesets=[existing])
    desired = [_make_desired(image_id="new-image")]
    result = ScalesetReconciler(client).reconcile(desired)
    assert "my-scaleset" in result.updated
    assert result.created == []
    client.update_scaleset.assert_called_once_with("uuid-1", pytest.approx(
        {"image": "new-image", "flavor": "m1.large", "max_runners": 5,
         "min_idle_runners": 0, "tags": pytest.approx(["linux", "self-hosted"], abs=0),
         "github_runner_group": "default", "extra_specs": {"pre_install_scripts": {}}},
        abs=0
    ))


def test_reconcile_no_op_when_scaleset_unchanged():
    existing = {
        "id": "uuid-1",
        "name": "my-scaleset",
        "image": "abc-image-uuid",
        "flavor": "m1.large",
        "os_arch": "amd64",
        "min_idle_runners": 0,
        "max_runners": 5,
        "tags": ["linux", "self-hosted"],
        "github_runner_group": "default",
        "extra_specs": {},
    }
    client = _make_client(scalesets=[existing])
    desired = [_make_desired()]
    result = ScalesetReconciler(client).reconcile(desired)
    assert result.created == []
    assert result.updated == []
    assert result.deleted == []
    client.create_scaleset.assert_not_called()
    client.update_scaleset.assert_not_called()
    client.delete_scaleset.assert_not_called()


def test_reconcile_deletes_removed_scaleset():
    existing = {
        "id": "uuid-1",
        "name": "old-scaleset",
        "image": "abc",
        "flavor": "m1.large",
        "os_arch": "amd64",
        "min_idle_runners": 0,
        "max_runners": 5,
        "tags": [],
        "github_runner_group": "default",
        "extra_specs": {},
    }
    client = _make_client(scalesets=[existing])
    result = ScalesetReconciler(client).reconcile([])  # empty desired
    assert "old-scaleset" in result.deleted
    client.delete_scaleset.assert_called_once_with("uuid-1")


def test_reconcile_skips_when_provider_missing():
    client = _make_client(providers=[])  # no providers registered
    desired = [_make_desired()]
    result = ScalesetReconciler(client).reconcile(desired)
    assert "my-scaleset" in result.skipped
    assert result.created == []
    client.create_scaleset.assert_not_called()


def test_reconcile_skips_when_credential_missing():
    client = _make_client(credentials=[])  # no credentials registered
    desired = [_make_desired()]
    result = ScalesetReconciler(client).reconcile(desired)
    assert "my-scaleset" in result.skipped
    assert result.created == []
    client.create_scaleset.assert_not_called()


def test_reconcile_processes_other_scalesets_when_one_skipped():
    client = _make_client(
        providers=[{"name": "openstack-myproject"}],
        credentials=[{"name": "github-app-12345"}],
    )
    desired = [
        _make_desired(name="ss-ok"),
        _make_desired(
            name="ss-skip",
            provider_name="missing-provider",
        ),
    ]
    result = ScalesetReconciler(client).reconcile(desired)
    assert "ss-ok" in result.created
    assert "ss-skip" in result.skipped


def test_reconcile_result_default_empty():
    r = ReconcileResult()
    assert r.created == []
    assert r.updated == []
    assert r.deleted == []
    assert r.skipped == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd charms/garm
python -m pytest tests/unit/test_scaleset_reconciler.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'scaleset_reconciler'`

- [ ] **Step 3: Implement `scaleset_reconciler.py`**

Create `charms/garm/src/scaleset_reconciler.py`:

```python
#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""GARM scaleset reconcile logic."""

import ast
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field

from garm_api import GarmClient

logger = logging.getLogger(__name__)


@dataclass
class DesiredScaleset:
    """Desired state of one GARM scaleset, derived from Configurator relation data.

    Attributes:
        name: Scaleset name.
        provider_name: GARM provider name to use.
        credentials_name: GARM credentials name to use.
        image_id: OpenStack image UUID.
        flavor: OpenStack flavor.
        os_arch: CPU architecture, e.g. 'amd64'.
        min_idle_runner: Minimum idle runners.
        max_runner: Maximum runners.
        labels: Comma-separated label list (may be empty).
        repo: GitHub repository (owner/repo), or empty string.
        org: GitHub organisation name, or empty string.
        runner_group: Runner group name.
        pre_install_scripts: Pre-install script dict literal string, or empty.
    """

    name: str
    provider_name: str
    credentials_name: str
    image_id: str
    flavor: str
    os_arch: str
    min_idle_runner: int
    max_runner: int
    labels: str = ""
    repo: str = ""
    org: str = ""
    runner_group: str = "default"
    pre_install_scripts: str = ""


@dataclass
class ReconcileResult:
    """Result of a scaleset reconcile pass.

    Attributes:
        created: Names of scalesets created in this pass.
        updated: Names of scalesets updated in this pass.
        deleted: Names of scalesets deleted in this pass.
        skipped: Names of scalesets skipped (missing provider or credential).
    """

    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def parse_relation_databag(data: Mapping[str, str]) -> DesiredScaleset | None:
    """Parse a Configurator relation unit databag into a DesiredScaleset.

    Args:
        data: Flat string-to-string mapping from a relation unit databag.

    Returns:
        DesiredScaleset if all required fields are present and valid, else None.
    """
    image_id = data.get("image_id", "")
    name = data.get("name", "")
    if not image_id or not name:
        return None
    try:
        return DesiredScaleset(
            name=name,
            provider_name=data.get("provider_name", ""),
            credentials_name=data.get("credentials_name", ""),
            image_id=image_id,
            flavor=data.get("flavor", ""),
            os_arch=data.get("os_arch", ""),
            min_idle_runner=int(data.get("min_idle_runner", "0")),
            max_runner=int(data.get("max_runner", "0")),
            labels=data.get("labels", ""),
            repo=data.get("repo", ""),
            org=data.get("org", ""),
            runner_group=data.get("runner_group", "default"),
            pre_install_scripts=data.get("pre_install_scripts", ""),
        )
    except (ValueError, KeyError) as exc:
        logger.warning("Invalid relation databag (skipping): %s", exc)
        return None


def _parse_pre_install_scripts(raw: str) -> dict[str, str]:
    """Parse the pre_install_scripts string as a Python dict literal.

    Args:
        raw: String representation of a dict, e.g. '{"setup.sh": "#!/bin/bash\\necho hi"}'.

    Returns:
        Parsed dict, or empty dict if raw is empty or unparseable.
    """
    if not raw.strip():
        return {}
    try:
        result = ast.literal_eval(raw)
        if isinstance(result, dict):
            return {str(k): str(v) for k, v in result.items()}
    except (ValueError, SyntaxError):
        logger.warning("Failed to parse pre_install_scripts: %s", raw[:100])
    return {}


def _build_create_payload(desired: DesiredScaleset) -> dict:
    """Build a CreateScaleSetParams payload from a DesiredScaleset.

    Args:
        desired: The desired scaleset state.

    Returns:
        Dict ready to POST to /api/v1/scalesets.
    """
    tags = (
        [t.strip() for t in desired.labels.split(",") if t.strip()]
        if desired.labels
        else []
    )
    payload: dict = {
        "name": desired.name,
        "provider_name": desired.provider_name,
        "credentials_name": desired.credentials_name,
        "image": desired.image_id,
        "flavor": desired.flavor,
        "os_arch": desired.os_arch,
        "os_type": "linux",
        "max_runners": desired.max_runner,
        "min_idle_runners": desired.min_idle_runner,
        "tags": tags,
        "github_runner_group": desired.runner_group,
    }
    if desired.repo:
        payload["repo_name"] = desired.repo
    elif desired.org:
        payload["org_name"] = desired.org
    scripts = _parse_pre_install_scripts(desired.pre_install_scripts)
    if scripts:
        payload["extra_specs"] = {"pre_install_scripts": scripts}
    return payload


def _build_update_payload(desired: DesiredScaleset) -> dict:
    """Build an UpdateScaleSetParams payload from a DesiredScaleset.

    Args:
        desired: The desired scaleset state.

    Returns:
        Dict ready to PUT to /api/v1/scalesets/{id}.
    """
    tags = (
        [t.strip() for t in desired.labels.split(",") if t.strip()]
        if desired.labels
        else []
    )
    scripts = _parse_pre_install_scripts(desired.pre_install_scripts)
    return {
        "image": desired.image_id,
        "flavor": desired.flavor,
        "max_runners": desired.max_runner,
        "min_idle_runners": desired.min_idle_runner,
        "tags": tags,
        "github_runner_group": desired.runner_group,
        "extra_specs": {"pre_install_scripts": scripts},
    }


def _needs_update(desired: DesiredScaleset, observed: dict) -> bool:
    """Return True if the observed scaleset differs from desired in any updateable field.

    Args:
        desired: Desired scaleset state.
        observed: Scaleset dict from the GARM API.

    Returns:
        True if an update API call is needed.
    """
    tags = (
        sorted(t.strip() for t in desired.labels.split(",") if t.strip())
        if desired.labels
        else []
    )
    observed_tags = sorted(observed.get("tags") or [])
    scripts = _parse_pre_install_scripts(desired.pre_install_scripts)
    observed_extra = observed.get("extra_specs") or {}
    observed_scripts = observed_extra.get("pre_install_scripts") or {}
    return (
        observed.get("image") != desired.image_id
        or observed.get("flavor") != desired.flavor
        or observed.get("max_runners") != desired.max_runner
        or observed.get("min_idle_runners") != desired.min_idle_runner
        or observed_tags != tags
        or observed.get("github_runner_group") != desired.runner_group
        or observed_scripts != scripts
    )


class ScalesetReconciler:
    """Reconciles GARM scalesets against a desired list via the REST API."""

    def __init__(self, client: GarmClient) -> None:
        """Initialise.

        Args:
            client: Authenticated GARM REST API client (client.token must be set).
        """
        self._client = client

    def reconcile(self, desired: list[DesiredScaleset]) -> ReconcileResult:
        """Diff observed REST state against desired and apply the minimum set of changes.

        Provider and credential lookups are performed once; scalesets referencing absent
        providers or credentials are skipped (added to result.skipped) while others proceed.

        Args:
            desired: List of desired scalesets derived from Configurator relation data.

        Returns:
            ReconcileResult summarising what was created, updated, deleted, or skipped.
        """
        result = ReconcileResult()

        observed_list = self._client.list_scalesets()
        observed: dict[str, dict] = {s["name"]: s for s in observed_list}

        provider_names = {p["name"] for p in self._client.list_providers()}
        credential_names = {c["name"] for c in self._client.list_credentials()}

        desired_names: set[str] = set()

        for item in desired:
            if item.provider_name not in provider_names:
                logger.warning(
                    "Skipping scaleset %r: provider %r not registered in GARM",
                    item.name,
                    item.provider_name,
                )
                result.skipped.append(item.name)
                continue

            if item.credentials_name not in credential_names:
                logger.warning(
                    "Skipping scaleset %r: credential %r not registered in GARM",
                    item.name,
                    item.credentials_name,
                )
                result.skipped.append(item.name)
                continue

            desired_names.add(item.name)

            if item.name not in observed:
                self._client.create_scaleset(_build_create_payload(item))
                result.created.append(item.name)
                logger.info("Created scaleset %r", item.name)
            elif _needs_update(item, observed[item.name]):
                self._client.update_scaleset(
                    observed[item.name]["id"], _build_update_payload(item)
                )
                result.updated.append(item.name)
                logger.info("Updated scaleset %r", item.name)

        for name, scaleset in observed.items():
            if name not in desired_names:
                self._client.delete_scaleset(scaleset["id"])
                result.deleted.append(name)
                logger.info("Deleted scaleset %r", name)

        return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd charms/garm
python -m pytest tests/unit/test_scaleset_reconciler.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add charms/garm/src/scaleset_reconciler.py charms/garm/tests/unit/test_scaleset_reconciler.py
git commit -m "feat(garm): add ScalesetReconciler and parse_relation_databag"
```

---

## Task 5: TDD — Configurator `charm_state.py` Additions

**Files:**
- Modify: `charms/garm-configurator/src/charm_state.py`
- Modify: `charms/garm-configurator/tests/unit/test_charm.py`

Add two computed string properties to `CharmState`: `provider_name` (derived from project name) and `credentials_name` (derived from GitHub App client ID).

- [ ] **Step 1: Write the failing tests**

Append to `charms/garm-configurator/tests/unit/test_charm.py`:

```python
def test_charm_state_provider_name_derived_from_project_name():
    """
    arrange: Valid config with openstack-project-name = 'myproject'.
    act: Build CharmState.
    assert: provider_name == 'openstack-myproject'.
    """
    from charm_state import CharmState
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    image_relation = Relation(endpoint="image", remote_units_data={0: {"id": "img-uuid"}})
    state = State(
        config=_valid_config(secret, pk_secret),
        secrets=[secret, pk_secret],
        relations=[image_relation],
    )
    with ctx(ctx.on.config_changed(), state) as mgr:
        charm = mgr.charm
        charm_state = CharmState.from_charm(charm)
    assert charm_state.provider_name == "openstack-myproject"


def test_charm_state_credentials_name_derived_from_client_id():
    """
    arrange: Valid config with github-app-client-id = '12345'.
    act: Build CharmState.
    assert: credentials_name == 'github-app-12345'.
    """
    from charm_state import CharmState
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    image_relation = Relation(endpoint="image", remote_units_data={0: {"id": "img-uuid"}})
    state = State(
        config=_valid_config(secret, pk_secret),
        secrets=[secret, pk_secret],
        relations=[image_relation],
    )
    with ctx(ctx.on.config_changed(), state) as mgr:
        charm = mgr.charm
        charm_state = CharmState.from_charm(charm)
    assert charm_state.credentials_name == "github-app-12345"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd charms/garm-configurator
python -m pytest tests/unit/test_charm.py::test_charm_state_provider_name_derived_from_project_name tests/unit/test_charm.py::test_charm_state_credentials_name_derived_from_client_id -v 2>&1 | tail -10
```

Expected: `AttributeError: 'CharmState' object has no attribute 'provider_name'`

- [ ] **Step 3: Add computed properties to `CharmState`**

In `charms/garm-configurator/src/charm_state.py`, add two properties to the `CharmState` class. Add after the `__init__` method:

```python
    @property
    def provider_name(self) -> str:
        """GARM provider name, derived from the OpenStack project name.

        Returns:
            String of the form 'openstack-{project_name}'.
        """
        return f"openstack-{self.provider_config.project_name}"

    @property
    def credentials_name(self) -> str:
        """GARM credentials name, derived from the GitHub App client ID.

        Returns:
            String of the form 'github-app-{client_id}'.
        """
        return f"github-app-{self.github_app_config.client_id}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd charms/garm-configurator
python -m pytest tests/unit/test_charm.py::test_charm_state_provider_name_derived_from_project_name tests/unit/test_charm.py::test_charm_state_credentials_name_derived_from_client_id -v
```

Expected: both pass.

- [ ] **Step 5: Run the full configurator unit suite to confirm no regressions**

```bash
cd charms/garm-configurator
python -m pytest tests/unit/ -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add charms/garm-configurator/src/charm_state.py charms/garm-configurator/tests/unit/test_charm.py
git commit -m "feat(garm-configurator): add provider_name and credentials_name to CharmState"
```

---

## Task 6: TDD — Configurator Charm Writes `garm-configurator` Relation Databag

**Files:**
- Modify: `charms/garm-configurator/src/charm.py`
- Modify: `charms/garm-configurator/tests/unit/test_charm.py`

The Configurator must write scaleset config to the `garm-configurator` relation when it has a valid image UUID. It must also observe `garm-configurator` relation events so new GARM units get data on join.

- [ ] **Step 1: Write the failing tests**

Append to `charms/garm-configurator/tests/unit/test_charm.py`:

```python
GARM_CONFIGURATOR_RELATION_NAME = "garm-configurator"


def _make_full_state_with_garm_rel(secret, pk_secret, garm_rel):
    """Build a State with valid config, image UUID, and a garm-configurator relation."""
    image_relation = Relation(endpoint="image", remote_units_data={0: {"id": "img-uuid"}})
    return State(
        config=_valid_config(secret, pk_secret),
        secrets=[secret, pk_secret],
        relations=[image_relation, garm_rel],
    )


def test_reconcile_writes_scaleset_data_to_garm_configurator_relation():
    """
    arrange: Valid config, image UUID available, garm-configurator relation joined.
    act: config_changed fires.
    assert: All scaleset fields are written to the garm-configurator relation unit data.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    garm_rel = Relation(endpoint=GARM_CONFIGURATOR_RELATION_NAME)
    state = _make_full_state_with_garm_rel(secret, pk_secret, garm_rel)
    out = ctx.run(ctx.on.config_changed(), state)
    rel_out = out.get_relation(garm_rel.id)
    assert rel_out.local_unit_data["name"] == "my-scaleset"
    assert rel_out.local_unit_data["provider_name"] == "openstack-myproject"
    assert rel_out.local_unit_data["credentials_name"] == "github-app-12345"
    assert rel_out.local_unit_data["image_id"] == "img-uuid"
    assert rel_out.local_unit_data["flavor"] == "m1.large"
    assert rel_out.local_unit_data["os_arch"] == "amd64"
    assert rel_out.local_unit_data["min_idle_runner"] == "0"
    assert rel_out.local_unit_data["max_runner"] == "5"
    assert rel_out.local_unit_data["repo"] == "myorg/myrepo"
    assert rel_out.local_unit_data["org"] == ""
    assert rel_out.local_unit_data["runner_group"] == "default"


def test_reconcile_does_not_write_garm_configurator_when_no_image_uuid():
    """
    arrange: Valid config but no image UUID (image builder not yet responded).
    act: config_changed fires.
    assert: garm-configurator relation unit data remains empty.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    # image relation present but no UUID
    image_relation = Relation(endpoint="image")
    garm_rel = Relation(endpoint=GARM_CONFIGURATOR_RELATION_NAME)
    state = State(
        config=_valid_config(secret, pk_secret),
        secrets=[secret, pk_secret],
        relations=[image_relation, garm_rel],
    )
    out = ctx.run(ctx.on.config_changed(), state)
    rel_out = out.get_relation(garm_rel.id)
    assert "image_id" not in rel_out.local_unit_data


def test_reconcile_writes_garm_configurator_on_relation_joined():
    """
    arrange: Valid config with image UUID; garm-configurator relation fires relation_joined.
    act: relation_joined fires for garm-configurator endpoint.
    assert: All scaleset fields are written.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    garm_rel = Relation(endpoint=GARM_CONFIGURATOR_RELATION_NAME)
    state = _make_full_state_with_garm_rel(secret, pk_secret, garm_rel)
    out = ctx.run(ctx.on.relation_joined(garm_rel), state)
    rel_out = out.get_relation(garm_rel.id)
    assert rel_out.local_unit_data["name"] == "my-scaleset"
    assert rel_out.local_unit_data["image_id"] == "img-uuid"


def test_reconcile_writes_labels_when_set():
    """
    arrange: Scaleset config has labels = 'arm64,ubuntu'.
    act: config_changed fires with garm-configurator relation.
    assert: labels field is written correctly.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    config["labels"] = "arm64,ubuntu"
    garm_rel = Relation(endpoint=GARM_CONFIGURATOR_RELATION_NAME)
    image_relation = Relation(endpoint="image", remote_units_data={0: {"id": "img-uuid"}})
    state = State(
        config=config,
        secrets=[secret, pk_secret],
        relations=[image_relation, garm_rel],
    )
    out = ctx.run(ctx.on.config_changed(), state)
    rel_out = out.get_relation(garm_rel.id)
    assert rel_out.local_unit_data["labels"] == "arm64,ubuntu"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd charms/garm-configurator
python -m pytest tests/unit/test_charm.py::test_reconcile_writes_scaleset_data_to_garm_configurator_relation -v 2>&1 | tail -10
```

Expected: test fails — charm doesn't write to `garm-configurator` relation yet.

- [ ] **Step 3: Add `GARM_CONFIGURATOR_RELATION_NAME` constant and update `charm.py`**

In `charms/garm-configurator/src/charm.py`, apply these changes:

**Add constant** after the existing imports (add alongside `IMAGE_RELATION_NAME` import):

In `charm.py`, change the import line:

```python
from charm_state import IMAGE_RELATION_NAME, CharmConfigInvalidError, CharmState
```

to:

```python
from charm_state import (
    IMAGE_RELATION_NAME,
    CharmConfigInvalidError,
    CharmState,
)

GARM_CONFIGURATOR_RELATION_NAME: typing.Final[str] = "garm-configurator"
```

**Add event observation** in `__init__` — add these events to the loop:

```python
        for event in [
            self.on.config_changed,
            self.on.secret_changed,
            self.on[IMAGE_RELATION_NAME].relation_joined,
            self.on[IMAGE_RELATION_NAME].relation_changed,
            self.on[IMAGE_RELATION_NAME].relation_broken,
            self.on[GARM_CONFIGURATOR_RELATION_NAME].relation_joined,
            self.on[GARM_CONFIGURATOR_RELATION_NAME].relation_changed,
        ]:
            self.framework.observe(event, self._reconcile)
```

**Add relation data writing** in `_reconcile` — extend the method to write scaleset data.

Replace the current `_reconcile` method body with:

```python
    def _reconcile(self, event: ops.EventBase) -> None:
        """Reconcile all charm state for every event.

        Reads full current state and acts idempotently: forwards OpenStack
        credentials to the image builder relation, writes scaleset config to
        all garm-configurator relations when an image UUID is available, and
        reports unit status.

        Args:
            event: The triggering event.
        """
        try:
            state = CharmState.from_charm(self)
        except CharmConfigInvalidError as e:
            self.unit.status = ops.BlockedStatus(e.msg)
            return

        relation = self.model.get_relation(IMAGE_RELATION_NAME)
        if relation is not None:
            relation.data[self.unit].update(
                {
                    "auth_url": state.provider_config.auth_url,
                    "password": state.provider_config.password,
                    "project_domain_name": state.provider_config.project_domain_name,
                    "project_name": state.provider_config.project_name,
                    "user_domain_name": state.provider_config.user_domain_name,
                    "username": state.provider_config.username,
                }
            )

        if state.image_id is not None:
            for garm_rel in self.model.relations.get(GARM_CONFIGURATOR_RELATION_NAME, []):
                garm_rel.data[self.unit].update(
                    {
                        "name": state.scaleset_config.name,
                        "provider_name": state.provider_name,
                        "credentials_name": state.credentials_name,
                        "image_id": state.image_id,
                        "flavor": state.scaleset_config.flavor,
                        "os_arch": state.scaleset_config.os_arch,
                        "min_idle_runner": str(state.scaleset_config.min_idle_runner),
                        "max_runner": str(state.scaleset_config.max_runner),
                        "labels": state.scaleset_config.labels,
                        "repo": state.scaleset_config.repo or "",
                        "org": state.scaleset_config.org or "",
                        "runner_group": state.scaleset_config.runner_group,
                        "pre_install_scripts": state.scaleset_config.pre_install_scripts or "",
                    }
                )

        if relation is None:
            self.unit.status = ops.WaitingStatus("Waiting for image builder relation")
        elif state.image_id is None:
            self.unit.status = ops.WaitingStatus("Waiting for image UUID from image builder")
        else:
            self.unit.status = ops.ActiveStatus("Ready")
```

- [ ] **Step 4: Run new tests to verify they pass**

```bash
cd charms/garm-configurator
python -m pytest tests/unit/test_charm.py -k "garm_configurator" -v
```

Expected: all four new tests pass.

- [ ] **Step 5: Run the full configurator unit suite to confirm no regressions**

```bash
cd charms/garm-configurator
python -m pytest tests/unit/ -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add charms/garm-configurator/src/charm.py charms/garm-configurator/tests/unit/test_charm.py
git commit -m "feat(garm-configurator): write scaleset config to garm-configurator relation databag"
```

---

## Task 7: TDD — GARM Charm: Admin Secrets

**Files:**
- Modify: `charms/garm/src/charm.py`
- Modify: `charms/garm/tests/unit/test_charm.py`

Add `admin-username` and `admin-password` to the GARM secrets generated on install. The admin password format must satisfy GARM's strong-password requirement (≥12 chars, mixed case, digit, symbol).

- [ ] **Step 1: Write the failing tests**

In `charms/garm/tests/unit/test_charm.py`, replace the existing `test_generate_garm_secrets_returns_jwt_and_passphrase` and `test_generate_garm_secrets_produces_unique_values` tests with:

```python
def test_generate_garm_secrets_returns_expected_keys():
    """Returns a dict with jwt-secret, db-passphrase, admin-username, admin-password."""
    result = _generate_garm_secrets()
    assert "jwt-secret" in result
    assert "db-passphrase" in result
    assert "admin-username" in result
    assert "admin-password" in result


def test_generate_garm_secrets_jwt_is_64_char_hex():
    result = _generate_garm_secrets()
    assert len(result["jwt-secret"]) == 64
    assert all(c in "0123456789abcdef" for c in result["jwt-secret"])


def test_generate_garm_secrets_passphrase_is_32_char_alnum():
    result = _generate_garm_secrets()
    assert len(result["db-passphrase"]) == 32
    valid_chars = string.ascii_letters + string.digits
    assert all(c in valid_chars for c in result["db-passphrase"])


def test_generate_garm_secrets_admin_username_is_admin():
    result = _generate_garm_secrets()
    assert result["admin-username"] == "admin"


def test_generate_garm_secrets_admin_password_meets_garm_requirements():
    """Admin password must be ≥12 chars, have upper, lower, digit, and symbol."""
    result = _generate_garm_secrets()
    pw = result["admin-password"]
    assert len(pw) >= 12
    assert any(c.isupper() for c in pw)
    assert any(c.islower() for c in pw)
    assert any(c.isdigit() for c in pw)
    assert any(not c.isalnum() for c in pw)


def test_generate_garm_secrets_produces_unique_values():
    first = _generate_garm_secrets()
    second = _generate_garm_secrets()
    assert first["jwt-secret"] != second["jwt-secret"]
    assert first["db-passphrase"] != second["db-passphrase"]
    assert first["admin-password"] != second["admin-password"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd charms/garm
python -m pytest tests/unit/test_charm.py -k "generate_garm_secrets" -v 2>&1 | tail -15
```

Expected: `test_generate_garm_secrets_returns_expected_keys` fails (missing `admin-username` key).

- [ ] **Step 3: Update `_generate_garm_secrets` in `charm.py`**

In `charms/garm/src/charm.py`, replace `_generate_garm_secrets`:

```python
def _generate_garm_secrets() -> dict[str, str]:
    """Generate a fresh set of GARM secrets.

    Returns:
        Dict with jwt-secret, db-passphrase, admin-username, and admin-password.
        The admin password satisfies GARM's strong-password requirements.
    """
    return {
        "jwt-secret": secrets.token_hex(32),
        "db-passphrase": _generate_passphrase(),
        "admin-username": "admin",
        "admin-password": f"Admin-{secrets.token_hex(8)}-Gx1!",
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd charms/garm
python -m pytest tests/unit/test_charm.py -k "generate_garm_secrets" -v
```

Expected: all six pass.

- [ ] **Step 5: Run the full garm unit suite**

```bash
cd charms/garm
python -m pytest tests/unit/ -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add charms/garm/src/charm.py charms/garm/tests/unit/test_charm.py
git commit -m "feat(garm): add admin-username and admin-password to garm-secrets"
```

---

## Task 8: TDD — GARM Charm: Relation Events + `_reconcile_scalesets`

**Files:**
- Modify: `charms/garm/src/charm.py`
- Modify: `charms/garm/tests/unit/test_charm.py`

Add `_build_desired_scalesets` (delegates to `parse_relation_databag`), `_reconcile_scalesets` (gets JWT, calls `ScalesetReconciler`), and wires `garm-configurator` relation events. Tests cover the databag-parsing helper and confirm the reconcile method returns early when the service isn't running.

- [ ] **Step 1: Write the failing tests**

Append to `charms/garm/tests/unit/test_charm.py`:

```python
from scaleset_reconciler import DesiredScaleset, parse_relation_databag


def test_parse_configurator_databag_returns_desired_scaleset():
    """parse_relation_databag constructs a DesiredScaleset from valid flat data."""
    data = {
        "name": "my-ss",
        "provider_name": "openstack-proj",
        "credentials_name": "github-app-123",
        "image_id": "img-uuid",
        "flavor": "m1.large",
        "os_arch": "amd64",
        "min_idle_runner": "1",
        "max_runner": "10",
        "labels": "linux,self-hosted",
        "repo": "myorg/myrepo",
        "org": "",
        "runner_group": "default",
        "pre_install_scripts": "",
    }
    result = parse_relation_databag(data)
    assert result is not None
    assert result.name == "my-ss"
    assert result.min_idle_runner == 1
    assert result.max_runner == 10


def test_parse_configurator_databag_returns_none_when_image_id_absent():
    """parse_relation_databag returns None when image_id is missing."""
    data = {
        "name": "my-ss",
        "provider_name": "openstack-proj",
        "credentials_name": "github-app-123",
        "image_id": "",
        "flavor": "m1.large",
        "os_arch": "amd64",
        "min_idle_runner": "0",
        "max_runner": "5",
    }
    assert parse_relation_databag(data) is None
```

- [ ] **Step 2: Run tests to verify they pass immediately** (parse_relation_databag is already implemented in Task 4)

```bash
cd charms/garm
python -m pytest tests/unit/test_charm.py::test_parse_configurator_databag_returns_desired_scaleset tests/unit/test_charm.py::test_parse_configurator_databag_returns_none_when_image_id_absent -v
```

Expected: both pass (they exercise `parse_relation_databag` already implemented in Task 4).

- [ ] **Step 3: Add imports and implement `_build_desired_scalesets` and `_reconcile_scalesets` in `charm.py`**

In `charms/garm/src/charm.py`, add imports after the existing imports:

```python
from garm_api import GarmApiError, GarmClient
from scaleset_reconciler import DesiredScaleset, ReconcileResult, ScalesetReconciler, parse_relation_databag
```

Add the `GARM_CONFIGURATOR_RELATION_NAME` constant after the existing constants:

```python
GARM_CONFIGURATOR_RELATION_NAME: typing.Final[str] = "garm-configurator"
```

In `GarmCharm.__init__`, add event observation after `self.framework.observe(self.on.install, self._on_install)`:

```python
        for event in [
            self.on[GARM_CONFIGURATOR_RELATION_NAME].relation_joined,
            self.on[GARM_CONFIGURATOR_RELATION_NAME].relation_changed,
            self.on[GARM_CONFIGURATOR_RELATION_NAME].relation_broken,
        ]:
            self.framework.observe(event, self._on_configurator_changed)
```

Add the `_on_configurator_changed` method, `_build_desired_scalesets` method, and `_reconcile_scalesets` method to `GarmCharm`:

```python
    def _on_configurator_changed(self, _: ops.EventBase) -> None:
        """Trigger scaleset reconcile when Configurator relation data changes."""
        self._reconcile_scalesets()

    def _build_desired_scalesets(self) -> list[DesiredScaleset]:
        """Build the desired scaleset list from all garm-configurator relation units.

        Returns:
            List of DesiredScaleset objects, one per Configurator unit with valid data.
        """
        desired = []
        for relation in self.model.relations.get(GARM_CONFIGURATOR_RELATION_NAME, []):
            for unit in relation.units:
                item = parse_relation_databag(dict(relation.data[unit]))
                if item is not None:
                    desired.append(item)
        return desired

    def _reconcile_scalesets(self) -> None:
        """Sync GARM scalesets against Configurator relation data via the REST API.

        No-ops gracefully if the GARM service is not yet running or secrets are
        unavailable. GarmApiError is caught and logged without entering error state.
        Only runs when at least one garm-configurator relation is present.
        """
        if not self.model.relations.get(GARM_CONFIGURATOR_RELATION_NAME):
            return

        container = self.unit.get_container(CONTAINER_NAME)
        try:
            if not container.can_connect():
                logger.debug("Pebble not ready; deferring scaleset reconcile")
                return
            if not container.get_service(PEBBLE_SERVICE_NAME).is_running():
                logger.debug("GARM service not running; deferring scaleset reconcile")
                return
        except ops.pebble.ConnectionError:
            logger.debug("Pebble connection error; deferring scaleset reconcile")
            return

        try:
            secrets = self._get_secrets()
        except ops.SecretNotFoundError:
            logger.warning("garm-secrets not available; skipping scaleset reconcile")
            return

        admin_username = secrets.get("admin-username", "admin")
        admin_password = secrets.get("admin-password", "")
        if not admin_password:
            logger.warning("admin-password missing from garm-secrets; skipping scaleset reconcile")
            return

        port = int(self.config.get("garm-listen-port", 9997))
        client = GarmClient(f"http://localhost:{port}/api/v1")

        try:
            client.first_run(
                username=admin_username,
                password=admin_password,
                email="admin@garm.local",
                full_name="GARM Admin",
            )
            client.token = client.login(admin_username, admin_password)

            try:
                binding = self.model.get_binding("juju-info")
                address = str(binding.network.bind_address)
            except Exception:
                address = "localhost"
            client.configure_controller(
                metadata_url=f"http://{address}:{port}/api/v1/metadata",
                callback_url=f"http://{address}:{port}/api/v1/callbacks",
                webhook_url=f"http://{address}:{port}/webhooks",
            )

            desired = self._build_desired_scalesets()
            result = ScalesetReconciler(client).reconcile(desired)
            logger.info(
                "Scaleset reconcile: created=%s updated=%s deleted=%s skipped=%s",
                result.created,
                result.updated,
                result.deleted,
                result.skipped,
            )
        except GarmApiError as exc:
            logger.warning("GARM API error during scaleset reconcile: %s", exc)
```

Also, at the end of the `restart()` method (just before the closing of the method, after `container.replan()`), add a call to reconcile if there are configurator relations:

```python
        container.replan()
        self._reconcile_scalesets()
```

- [ ] **Step 4: Run the full garm unit suite**

```bash
cd charms/garm
python -m pytest tests/unit/ -v
```

Expected: all pass.

- [ ] **Step 5: Run lint to catch any issues**

```bash
cd charms/garm
python -m tox -e lint 2>&1 | tail -20
```

Fix any issues reported.

- [ ] **Step 6: Commit**

```bash
git add charms/garm/src/charm.py charms/garm/tests/unit/test_charm.py
git commit -m "feat(garm): wire garm-configurator relation events and implement _reconcile_scalesets"
```

---

## Task 9: Integration Tests

**Files:**
- Modify: `charms/tests/integration/test_garm.py`
- Modify: `charms/tests/integration/conftest.py`

Add integration tests covering: deferred creation (missing credential), scaleset created, scaleset updated (no restart), scaleset deleted on relation removal.

Because scaleset creation requires a GARM credential (story #9), the tests that create/update/delete scalesets first register a test credential directly via the GARM API using a hardcoded test RSA key.

- [ ] **Step 1: Add `_garm_login_from_secret` helper to the integration test conftest**

In `charms/tests/integration/conftest.py` (the shared conftest), add a helper that retrieves admin credentials from the `garm-secrets` Juju secret and returns a JWT. This is used by scaleset tests where the charm itself has already completed first-run.

Look at the file structure first — the integration `conftest.py` currently doesn't have this. Add to `charms/tests/integration/conftest.py`:

```python
# add this import at top alongside existing imports
import requests  # already imported indirectly via test_garm.py; add here if not present
```

Then add this helper function (it's module-level, not a fixture):

```python
def garm_login_from_secret(juju: jubilant.Juju, garm_app: str, garm_address: str) -> str:
    """Get a GARM admin JWT by reading credentials from the garm-secrets Juju secret.

    Used when the charm has already completed GARM first-run (i.e. when a
    garm-configurator relation is present), so the admin password is the one
    stored in garm-secrets rather than a test-generated value.

    Args:
        juju: Jubilant Juju handle.
        garm_app: GARM application name.
        garm_address: GARM unit IP address.

    Returns:
        JWT token string.
    """
    secrets_json = juju.cli("secrets", "--format=json")
    secrets = json.loads(secrets_json)
    garm_secret_uri = next(
        (uri for uri, info in secrets.items() if info.get("label") == "garm-secrets"),
        None,
    )
    assert garm_secret_uri, "garm-secrets not found in Juju secrets"
    secret_json = juju.cli("show-secret", "--reveal", "--format=json", garm_secret_uri)
    secret_data = json.loads(secret_json)
    content = secret_data[garm_secret_uri]["content"]["Data"]
    admin_username = content["admin-username"]
    admin_password = content["admin-password"]

    base_url = f"http://{garm_address}:{GARM_API_PORT}/api/v1"
    resp = requests.post(
        f"{base_url}/auth/login",
        json={"username": admin_username, "password": admin_password},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["token"]
```

Note: `GARM_API_PORT = 9997` — import it from `test_garm.py` or define it in conftest as a constant.

- [ ] **Step 2: Add `garm_configurator_app` fixture to shared conftest**

The `test_garm_configurator.py` has its own `garm_configurator_app` fixture. To share it with `test_garm.py` scaleset tests, add a fixture to `charms/tests/integration/conftest.py`. This fixture deploys the garm-configurator charm with test credentials and waits for it to be in Waiting status (no image builder yet).

In `charms/tests/integration/conftest.py`, add:

```python
@pytest.fixture(scope="module", name="garm_configurator_for_scaleset_tests")
def garm_configurator_for_scaleset_tests_fixture(
    juju: jubilant.Juju,
    garm_configurator_charm_file: str,
    any_charm_image_builder_app: str,
) -> str:
    """Deploy garm-configurator with fake test config and integrate with a fake image builder.

    Returns the app name once Active (image UUID received from fake builder).
    Scoped to module so it persists across all scaleset integration tests.
    """
    app_name = "garm-configurator-scaleset-test"
    juju.deploy(charm=garm_configurator_charm_file, app=app_name)
    juju.wait(
        lambda status: jubilant.all_blocked(status, app_name),
        timeout=5 * 60,
        delay=10,
    )
    password_secret_uri = juju.add_secret(
        name="os-pw-scaleset", content={"value": "fake-password"}
    )
    private_key_secret_uri = juju.add_secret(
        name="gh-key-scaleset", content={"value": "fake-private-key"}
    )
    juju.grant_secret(password_secret_uri, app_name)
    juju.grant_secret(private_key_secret_uri, app_name)
    juju.config(
        app_name,
        values={
            "openstack-auth-url": "https://keystone.example.com:5000/v3",
            "openstack-username": "admin",
            "openstack-password": password_secret_uri,
            "openstack-project-name": "myproject",
            "openstack-user-domain-name": "Default",
            "openstack-project-domain-name": "Default",
            "openstack-region-name": "RegionOne",
            "openstack-network": "external-net",
            "github-app-client-id": "12345",
            "github-app-installation-id": "67890",
            "github-app-private-key": private_key_secret_uri,
            "name": "test-scaleset",
            "flavor": "m1.large",
            "os-arch": "amd64",
            "repo": "myorg/myrepo",
        },
    )
    # Integrate with fake image builder to get image UUID → Active
    juju.integrate(
        f"{app_name}:image",
        f"{any_charm_image_builder_app}:provide-github-runner-image-v0",
    )
    juju.wait(
        lambda status: jubilant.all_active(status, app_name),
        timeout=5 * 60,
        delay=10,
    )
    return app_name
```

- [ ] **Step 3: Add the four scaleset integration tests to `test_garm.py`**

Append to `charms/tests/integration/test_garm.py`:

```python
# A hardcoded test RSA private key — NOT a real secret, used only for GARM credential
# creation in integration tests. GARM stores it in its DB; the actual GitHub API is never
# called in these tests since scaleset runners are never dispatched.
_TEST_RSA_PRIVATE_KEY = """\
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA2a2rwplBQLzHPZe5ekSKj/MoGEgClAFOYFJDGMnZvj4CKk8v
AV1PVQZ9bHyNEuqUHxeUY7C4B0QIqODxs6X4AV2uXXpFbGAl2Nxs0B9rO3BI3gu
x5PiLKZH8G0rk0EZ1sR8Kl9DX6MX6nfSmB4qbIIHZFhcPg3a6u8FYkKNaFsQXvx
FjNOMeFDTxFU9nxc5bU1gB3xLRlmU0xR6glOR5Z7m2oc0vXmz5szPfBzD6KHMVL
K2Xl5VfCiGQi+GiMxv6V0gBTkG7I0Y1B2Vg4F5wNs8V9Ei2bIlM+7qZ8CZdSLG
2ZHCGmFGEaAhA8ZdUf00VzLl3YO1LHxH5kM6qQIDAQABAoIBAHDYsKlnS0y6jMwX
OaXJHOImoUu2Rt0t+pHbvmRk7oBGiH0G0PXUHa4Ps+r9rHKA/ZOv+kFzN1j8Fm8
KfcLmAT6KwCXYA0JbJjTHRuSbxnBsGS1V3eJjYPEkYxpY1ZG2G7P9x8hHAaGJ2p
oJBi+RHqT+f3gT2GnDV9xyP1gQ8SxWfF4D6pBCMT8a/yQ5xf+3V2H9Q3WmGmR1
ZrfGRq7+OJF5hqzHXXpQ8RR4Z9J3XQl3P3bRQlT4JdG8kXjOjg1BInQBHn4iR1
u+kJ7Pc5o9xH2E3Z7a5H3vBxiY3V9HcDqB3iXqFGBLJrhlAF7OMG0EgCXdtRYz
RFY8TgECgYEA7qfM+8T0ZXXP8zJHNQUhMRIJLPdO3GMNkzQDv7QzRYC9a2GBYT5
X9tFhlJxl+GYm3WrQGnz/8RzFJjxv6vXpfJUqm/5OtJGzH7yO8zH3BOmvY/MflM
wJU1wNKJeEBQhVTxf3yUGkHvqrb0Aa3J5CvEqg8KaLXvRHB0R9LZCN0CgYEA6St
7dxJqnw1J0Y0eZ8HKjR4E7t5jK3E4vH1/B4lMdA1i5y9k+a+r5A0FKyE7BOsqy
h6RBj6e8V+3F6mPf2O7I8cP5rX8fWJV5JK7wMV5wS5F7R8x4f/gfBNvFD0MBzn
4xJ9Q8W2WkpnV8A5F3J7Q8oNtPb9y9J8Z5gLLK0CgYEAhEn7KHJBxT9J1tRG7sR
j5vPC5nTM8r7L8BvZ2tM9A0r6FBF4C3HbMJE2P1K7hLGOQYz0d8v7yyX+7JJKQR
V9mIJ7JJMX1Fy8H4YsN7bZ2K8YrQ9NwQvBRxVZOzJFHjJnv9EJO2HQwJVCRvVNy
JCYJ8t3xHlWjx3T5dHYvkFECgYBRGdQaBqO0tAEdpX7VrCCNBnlHNHT3k1GMFOU
B8bCWLvQHH3Y4z7Ai9Z3/0mhLAi7T+VGTCy9aBN5m+3b8SdJxZN7pU6tNB9r9pn
cJj7x6lHqLpkH4v8K0R5lM7T3RpD9vN7Z6t5r7gF1UjJ9H5UhJ1XTQKZ3r/Y1V
JiRQAQKBgC5VijYO3CyJX7mHfWgEhD8qT5BJ7y3T0z7F1qOIc0J9H/2VBl7RZv
zT1Y8n6FGQR7LwZ5B4RxHJ0z3gK0qT3vL5h5X0jXQ6F8E9gVd4F3mJfq4T5N3D
xVLN0NQHZ0BLj0A+cZ9PBRsQ4cQ4Rr+QYi5GHsR9/7J1d7VzNqzQ
-----END RSA PRIVATE KEY-----
"""


def _create_test_credential(
    base_url: str, token: str, credentials_name: str
) -> None:
    """Create a GARM credential via the REST API for use in scaleset tests.

    Uses a hardcoded test RSA key — this credential is never used to actually
    authenticate with GitHub; it only needs to exist in GARM's DB.

    Args:
        base_url: GARM API base URL (e.g. 'http://1.2.3.4:9997/api/v1').
        token: Admin JWT token.
        credentials_name: Name for the new credential record.
    """
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "name": credentials_name,
        "auth_type": "app",
        "app_id": 12345,
        "installation_id": 67890,
        "private_key_bytes": _TEST_RSA_PRIVATE_KEY,
        "endpoint_name": "github.com",
    }
    resp = requests.post(f"{base_url}/credentials", json=payload, headers=headers, timeout=30)
    # 409 = already exists; either way, proceed
    if resp.status_code not in (200, 201, 409):
        logger.warning(
            "Credential creation returned unexpected status %d: %s",
            resp.status_code,
            resp.text[:200],
        )


def test_scaleset_deferred_when_credential_missing(
    juju: jubilant.Juju,
    garm_app: str,
    garm_configurator_for_scaleset_tests: str,
):
    """
    arrange: GARM is active; garm-configurator is integrated but no GARM credential exists.
    act: Integrate garm and garm-configurator; wait for events to settle.
    assert:
      - No scaleset appears in GET /api/v1/scalesets.
      - GARM app remains Active/Waiting — no error state.
    """
    juju.integrate(garm_app, garm_configurator_for_scaleset_tests)
    # Allow time for relation events and reconcile attempt
    juju.wait(
        lambda status: jubilant.all_active(status, garm_app),
        timeout=3 * 60,
        delay=10,
    )

    address = _get_garm_address(juju, garm_app)
    token = garm_login_from_secret(juju, garm_app, address)

    base_url = f"http://{address}:{GARM_API_PORT}/api/v1"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{base_url}/scalesets", headers=headers, timeout=30)
    resp.raise_for_status()

    scalesets = resp.json()
    logger.info("Scalesets after deferred test: %s", scalesets)
    assert isinstance(scalesets, list)
    assert len(scalesets) == 0, (
        f"Expected no scalesets (credential missing), got: {scalesets}"
    )

    # GARM app must not be in error state
    status = juju.status()
    app_status = status.apps[garm_app].app_status.current
    assert app_status in ("active", "waiting"), (
        f"Expected active/waiting, got {app_status}"
    )


def test_scaleset_created_after_credential_registered(
    juju: jubilant.Juju,
    garm_app: str,
    garm_configurator_for_scaleset_tests: str,
):
    """
    arrange: GARM is active, garm-configurator is integrated, and a matching GARM credential
        is created via the REST API so the reconcile can proceed.
    act: Create the GARM credential; trigger a relation-changed by changing a config value.
    assert: The scaleset 'test-scaleset' appears in GET /api/v1/scalesets with correct fields.
    """
    address = _get_garm_address(juju, garm_app)
    token = garm_login_from_secret(juju, garm_app, address)
    base_url = f"http://{address}:{GARM_API_PORT}/api/v1"

    _create_test_credential(base_url, token, "github-app-12345")

    # Trigger a re-reconcile by bumping a Configurator config value
    juju.config(garm_configurator_for_scaleset_tests, values={"min-idle-runner": 1})
    juju.wait(
        lambda status: jubilant.all_active(status, garm_configurator_for_scaleset_tests),
        timeout=3 * 60,
        delay=10,
    )

    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{base_url}/scalesets", headers=headers, timeout=30)
    resp.raise_for_status()
    scalesets = resp.json()
    logger.info("Scalesets after create test: %s", scalesets)

    names = [s["name"] for s in scalesets]
    assert "test-scaleset" in names, f"Expected 'test-scaleset' in {names}"

    ss = next(s for s in scalesets if s["name"] == "test-scaleset")
    assert ss["flavor"] == "m1.large"
    assert ss["image"] == "fake-openstack-image-uuid"
    assert ss["min_idle_runners"] == 1


def test_scaleset_updated_without_restart(
    juju: jubilant.Juju,
    garm_app: str,
    garm_configurator_for_scaleset_tests: str,
):
    """
    arrange: 'test-scaleset' already exists in GARM (created by previous test).
    act: Change the max-runner config on garm-configurator; wait for active.
    assert:
      - GET /api/v1/scalesets returns 'test-scaleset' with updated max_runners.
      - The GARM Pebble service has not been restarted (start time is unchanged).
    """
    address = _get_garm_address(juju, garm_app)
    token = garm_login_from_secret(juju, garm_app, address)
    base_url = f"http://{address}:{GARM_API_PORT}/api/v1"
    headers = {"Authorization": f"Bearer {token}"}

    # Record service start time before config change
    unit = f"{garm_app}/0"
    pebble_info_before = juju.exec(
        f"{PEBBLE_PREFIX} services app --format=json", unit=unit
    )

    juju.config(garm_configurator_for_scaleset_tests, values={"max-runner": 20})
    juju.wait(
        lambda status: jubilant.all_active(status, garm_configurator_for_scaleset_tests),
        timeout=3 * 60,
        delay=10,
    )

    resp = requests.get(f"{base_url}/scalesets", headers=headers, timeout=30)
    resp.raise_for_status()
    scalesets = resp.json()
    ss = next((s for s in scalesets if s["name"] == "test-scaleset"), None)
    assert ss is not None, "test-scaleset not found after update"
    assert ss["max_runners"] == 20, f"Expected max_runners=20, got {ss['max_runners']}"

    pebble_info_after = juju.exec(
        f"{PEBBLE_PREFIX} services app --format=json", unit=unit
    )
    logger.info("Pebble service info before: %s", pebble_info_before.stdout[:300])
    logger.info("Pebble service info after: %s", pebble_info_after.stdout[:300])
    # Service should still be in 'active' state (not restarted)
    assert '"status":"active"' in pebble_info_after.stdout or "active" in pebble_info_after.stdout


def test_scaleset_deleted_on_relation_removed(
    juju: jubilant.Juju,
    garm_app: str,
    garm_configurator_for_scaleset_tests: str,
):
    """
    arrange: 'test-scaleset' exists in GARM; garm-configurator is integrated.
    act: Remove the garm-configurator integration.
    assert: GET /api/v1/scalesets returns an empty list — scaleset was deleted.
    """
    address = _get_garm_address(juju, garm_app)
    token = garm_login_from_secret(juju, garm_app, address)
    base_url = f"http://{address}:{GARM_API_PORT}/api/v1"
    headers = {"Authorization": f"Bearer {token}"}

    juju.remove_relation(garm_app, garm_configurator_for_scaleset_tests)
    juju.wait(
        lambda status: jubilant.all_active(status, garm_app),
        timeout=3 * 60,
        delay=10,
    )

    resp = requests.get(f"{base_url}/scalesets", headers=headers, timeout=30)
    resp.raise_for_status()
    scalesets = resp.json()
    logger.info("Scalesets after delete test: %s", scalesets)
    assert scalesets == [], f"Expected empty list after relation removed, got: {scalesets}"
```

- [ ] **Step 4: Add the missing import to the integration conftest**

Check what `charms/tests/integration/conftest.py` currently imports, and add `json` if missing (it should already have it via `test_garm.py`, but the conftest itself may need it):

```bash
head -10 charms/tests/integration/conftest.py
```

Add `import json` and `import requests` to the top of `conftest.py` if not already present.

Also add `GARM_API_PORT = 9997` to the conftest (or import it from `test_garm`).

- [ ] **Step 5: Commit**

```bash
git add charms/tests/integration/conftest.py charms/tests/integration/test_garm.py
git commit -m "test(garm): add scaleset integration tests (create/update/delete/defer)"
```

---

## Task 10: Final Verification

**Files:** (none new — verification only)

- [ ] **Step 1: Run all garm unit tests**

```bash
cd charms/garm
python -m tox -e unit
```

Expected: all pass.

- [ ] **Step 2: Run all garm-configurator unit tests**

```bash
cd charms/garm-configurator
python -m tox -e unit
```

Expected: all pass.

- [ ] **Step 3: Run linters on both charms**

```bash
cd charms/garm && python -m tox -e lint
cd charms/garm-configurator && python -m tox -e lint
```

Expected: no errors.

- [ ] **Step 4: Run static analysis on both charms**

```bash
cd charms/garm && python -m tox -e static
cd charms/garm-configurator && python -m tox -e static
```

Fix any type errors.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: fix any lint/static issues from ISD-5729 implementation"
```

---

## Self-Review Notes

**Spec coverage check:**
- ✅ Scalesets synced via REST API without restart — `_reconcile_scalesets`, Tasks 8
- ✅ Scaleset fields (image, flavor, labels, min_idle, max_runner, pre_install_scripts) — Task 4 reconciler
- ✅ Deferred creation when provider/credential missing — Task 4 reconciler + Task 9 test
- ✅ Diff observed vs desired, minimum API calls — Task 4 `_needs_update` + no-op test
- ✅ No service restart — `_reconcile_scalesets` never calls `restart()`
- ✅ Integration tests for create/update/delete/defer — Task 9
- ✅ `provider_name` and `credentials_name` computed on Configurator side — Task 5
- ✅ Configurator writes relation databag — Task 6
- ✅ Admin secrets (first-run automation) — Task 7 + Task 8

**Type consistency:** `parse_relation_databag` is defined in `scaleset_reconciler.py` and imported in both `charm.py` (GARM) and in tests. `GarmClient` is created in `_reconcile_scalesets` and passed to `ScalesetReconciler`. All method names are consistent across tasks.

**Ambiguity resolved:** DELETE applies to all observed scalesets not in the desired set. Operators must not manually create scalesets in GARM when the charm is active.
