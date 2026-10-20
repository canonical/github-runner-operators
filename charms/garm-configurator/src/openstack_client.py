# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Minimal Keystone-authenticated client for the OpenStack networking API.

The charm needs six calls — list, create, and delete security group rules, plus the group
itself — so it talks to Neutron's REST API directly rather than depending on a full OpenStack
SDK. charmcraft builds this charm's Python dependencies from source, and the SDK's
``cryptography`` dependency does not build without OpenSSL development headers, which the charm
build environment does not carry.

Only the public interface and a project-scoped Keystone v3 password token are supported.
"""

import dataclasses
import json
import typing
import urllib.error
import urllib.parse
import urllib.request

from charm_state import ProviderConfig

DEFAULT_TIMEOUT_SECONDS = 30
_NETWORK_SERVICE_TYPE = "network"
_PUBLIC_INTERFACE = "public"
# Longest error detail copied into a status or log line.
MAX_DETAIL_LENGTH = 200


class OpenStackClientError(Exception):
    """Raised when OpenStack rejects a request or cannot be reached."""


@dataclasses.dataclass(frozen=True)
class _Session:
    """A Keystone token and the networking endpoint it authorises."""

    token: str
    endpoint: str


def _urlopen_transport(
    method: str, url: str, headers: dict[str, str], body: bytes | None
) -> tuple[int, dict[str, str], bytes]:
    """Send one request with the standard library, reporting HTTP errors as responses.

    Args:
        method: The HTTP method.
        url: The absolute URL to call.
        headers: The request headers.
        body: The request body, if any.

    Returns:
        The status, response headers, and response body. A 4xx or 5xx from the server is
        returned rather than raised, so the caller can report OpenStack's own message.

    Raises:
        OpenStackClientError: If the server cannot be reached at all.
    """
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise OpenStackClientError(f"refusing to call a non-HTTP URL: {url}")
    # The scheme is checked immediately above, so urlopen cannot be pointed at a file: URL.
    request = urllib.request.Request(  # noqa: S310
        url, data=body, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(  # noqa: S310  # nosec B310
            request, timeout=DEFAULT_TIMEOUT_SECONDS
        ) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read()
    except urllib.error.URLError as exc:
        raise OpenStackClientError(f"cannot reach {url}: {exc.reason}") from exc


class NetworkClient:
    """Talks to the Neutron API of the configured OpenStack project."""

    def __init__(
        self,
        provider_config: ProviderConfig,
        transport: typing.Callable[..., tuple[int, dict[str, str], bytes]] | None = None,
    ) -> None:
        """Initialise the client.

        Args:
            provider_config: The OpenStack credentials and region to authenticate with.
            transport: The HTTP transport, overridden by tests.
        """
        self._config = provider_config
        self._transport = transport or _urlopen_transport
        self._session: _Session | None = None

    def security_groups(self) -> list[dict[str, typing.Any]]:
        """Return every security group of the project."""
        return self._json_list("GET", "/security-groups", "security_groups")

    def create_security_group(self, name: str, description: str) -> dict[str, typing.Any]:
        """Create a security group and return it, as Neutron reports it."""
        return self._json_object(
            "POST",
            "/security-groups",
            "security_group",
            {"security_group": {"name": name, "description": description}},
        )

    def security_group_rules(self, security_group_id: str) -> list[dict[str, typing.Any]]:
        """Return the rules of one security group."""
        query = urllib.parse.urlencode({"security_group_id": security_group_id})
        return self._json_list("GET", f"/security-group-rules?{query}", "security_group_rules")

    def create_security_group_rule(
        self, security_group_id: str, fields: dict[str, object]
    ) -> dict[str, typing.Any]:
        """Create one rule of a security group and return it."""
        return self._json_object(
            "POST",
            "/security-group-rules",
            "security_group_rule",
            {"security_group_rule": {"security_group_id": security_group_id, **fields}},
        )

    def delete_security_group_rule(self, rule_id: str) -> None:
        """Delete one security group rule."""
        self._json("DELETE", f"/security-group-rules/{rule_id}")

    def _json(
        self, method: str, path: str, body: dict[str, object] | None = None
    ) -> dict[str, typing.Any]:
        """Send a Neutron request and decode its JSON response."""
        payload = self._request(method, path, body)
        return _decode(payload) if payload else {}

    def _json_list(
        self, method: str, path: str, key: str, body: dict[str, object] | None = None
    ) -> list[dict[str, typing.Any]]:
        """Send a Neutron request and return the list it nests under *key*."""
        value = self._json(method, path, body).get(key)
        if not isinstance(value, list):
            raise OpenStackClientError(f"{method} {path} returned no {key!r} list")
        return value

    def _json_object(
        self, method: str, path: str, key: str, body: dict[str, object] | None = None
    ) -> dict[str, typing.Any]:
        """Send a Neutron request and return the object it nests under *key*."""
        value = self._json(method, path, body).get(key)
        if not isinstance(value, dict):
            raise OpenStackClientError(f"{method} {path} returned no {key!r} object")
        return value

    def _request(self, method: str, path: str, body: dict[str, object] | None = None) -> bytes:
        """Send one request to Neutron, authenticating first and once more on a 401."""
        data = None if body is None else json.dumps(body).encode("utf-8")
        status, _, payload = self._send(method, path, data)
        if status == 401:
            # Keystone tokens expire, and the charm may hold one across a long reconcile.
            self._session = None
            status, _, payload = self._send(method, path, data)
        if status >= 400:
            raise OpenStackClientError(
                f"{method} {path} failed with {status}: {_error_detail(payload)}"
            )
        return payload

    def _send(
        self, method: str, path: str, data: bytes | None
    ) -> tuple[int, dict[str, str], bytes]:
        """Send one request authenticated with the current session."""
        session = self._current_session()
        headers = {"Accept": "application/json", "X-Auth-Token": session.token}
        if data is not None:
            headers["Content-Type"] = "application/json"
        return self._transport(method, f"{session.endpoint}{path}", headers, data)

    def _current_session(self) -> _Session:
        """Return the Keystone session, authenticating on first use."""
        session = self._session
        if session is None:
            session = self._authenticate()
        return session

    def _authenticate(self) -> _Session:
        """Request a Keystone token scoped to the configured project.

        Returns:
            The session the token authorises.

        Raises:
            OpenStackClientError: If Keystone rejects the credentials or returns no token or
                no networking endpoint.
        """
        config = self._config
        body = {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": config.username,
                            "domain": {"name": config.user_domain_name},
                            "password": config.password,
                        }
                    },
                },
                "scope": {
                    "project": {
                        "name": config.project_name,
                        "domain": {"name": config.project_domain_name},
                    }
                },
            }
        }
        url = f"{config.auth_url.rstrip('/')}/auth/tokens"
        status, headers, payload = self._transport(
            "POST", url, {"Content-Type": "application/json"}, json.dumps(body).encode("utf-8")
        )
        if status >= 400:
            raise OpenStackClientError(
                f"Keystone rejected the credentials ({status}): {_error_detail(payload)}"
            )
        token = _header(headers, "X-Subject-Token")
        if not token:
            raise OpenStackClientError("Keystone returned no token")
        session = _Session(token=token, endpoint=_network_endpoint(payload, config.region_name))
        self._session = session
        return session


def _header(headers: dict[str, str], name: str) -> str:
    """Return a response header, matched case-insensitively."""
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return ""


def _network_endpoint(payload: bytes, region_name: str) -> str:
    """Return the public networking endpoint of the token's service catalog.

    Args:
        payload: The Keystone token document.
        region_name: The region to use, or an empty string for the first one listed.

    Returns:
        The endpoint URL, without a trailing slash.

    Raises:
        OpenStackClientError: If the catalog lists no matching endpoint.
    """
    for endpoint in _network_endpoints(_decode(payload)):
        url = _endpoint_url(endpoint, region_name)
        if url:
            return url
    raise OpenStackClientError(
        f"the Keystone catalog has no public networking endpoint for region {region_name or 'any'}"
    )


def _network_endpoints(document: dict[str, typing.Any]) -> list[dict[str, typing.Any]]:
    """Return the endpoints the catalog lists for the networking service."""
    return [
        endpoint
        for service in document.get("token", {}).get("catalog", [])
        if service.get("type") == _NETWORK_SERVICE_TYPE
        for endpoint in service.get("endpoints", [])
    ]


def _endpoint_url(endpoint: dict[str, typing.Any], region_name: str) -> str:
    """Return an endpoint's URL when it is the public one of the configured region."""
    if endpoint.get("interface") != _PUBLIC_INTERFACE:
        return ""
    if region_name and endpoint.get("region") != region_name:
        return ""
    return str(endpoint.get("url") or "").rstrip("/")


def _decode(payload: bytes) -> dict[str, typing.Any]:
    """Decode a JSON object, or report that the response was not one."""
    try:
        document = json.loads(payload)
    except ValueError as exc:
        raise OpenStackClientError("OpenStack returned a response that is not JSON") from exc
    if not isinstance(document, dict):
        raise OpenStackClientError("OpenStack returned a response that is not a JSON object")
    return document


def _error_detail(payload: bytes) -> str:
    """Return OpenStack's explanation of a failed request, bounded to one short line."""
    detail = " ".join(_error_message(payload).split())
    return detail[:MAX_DETAIL_LENGTH] or "no detail"


def _error_message(payload: bytes) -> str:
    """Return the message inside a failed response, or the response itself."""
    try:
        document = json.loads(payload)
    except ValueError:
        return payload.decode("utf-8", "replace")
    if not isinstance(document, dict):
        return str(document)
    return _document_message(document)


def _document_message(document: dict[str, typing.Any]) -> str:
    """Return the message of an error document, whatever it nests it under."""
    # Neutron nests its message under NeutronError; Keystone under error.
    error = document.get("NeutronError") or document.get("error") or document
    if isinstance(error, dict):
        return str(error.get("message", error))
    return str(error)
