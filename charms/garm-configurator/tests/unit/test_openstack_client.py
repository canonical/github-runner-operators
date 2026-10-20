# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the minimal OpenStack networking client."""

import io
import json
import urllib.error

import pytest

from charm_state import ProviderConfig
from openstack_client import (
    MAX_DETAIL_LENGTH,
    NetworkClient,
    OpenStackClientError,
    _urlopen_transport,
)

CATALOG = {
    "token": {
        "catalog": [
            {
                "type": "identity",
                "endpoints": [
                    {
                        "interface": "public",
                        "region": "RegionOne",
                        "url": "https://keystone.example.com:5000/v3",
                    }
                ],
            },
            {
                "type": "network",
                "endpoints": [
                    {
                        "interface": "internal",
                        "region": "RegionOne",
                        "url": "http://neutron.internal:9696",
                    },
                    {
                        "interface": "public",
                        "region": "RegionTwo",
                        "url": "https://neutron.two:9696",
                    },
                    {
                        "interface": "public",
                        "region": "RegionOne",
                        "url": "https://neutron.example.com:9696/",
                    },
                ],
            },
        ]
    }
}


class FakeTransport:
    """A transport that answers from a recorded queue of responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, method, url, headers, body):
        self.requests.append({"method": method, "url": url, "headers": headers, "body": body})
        return self.responses.pop(0)


def _response(status=200, payload=None, headers=None):
    """Build a transport response, JSON-encoding the payload."""
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    return status, headers or {}, body


def _provider_config(region="RegionOne"):
    """Build the OpenStack credentials the client authenticates with."""
    return ProviderConfig(
        auth_url="https://keystone.example.com:5000/v3",
        username="admin",
        password="s3cr3t",
        project_name="myproject",
        user_domain_name="Default",
        project_domain_name="Default",
        region_name=region,
        network="external-net",
        provider_name="garm-configurator-0",
    )


def _client(responses, region="RegionOne"):
    """Build a client whose transport answers with *responses*."""
    transport = FakeTransport(responses)
    return NetworkClient(_provider_config(region), transport=transport), transport


def _auth_response():
    """Return a successful Keystone token response."""
    return _response(201, CATALOG, {"X-Subject-Token": "token-1"})


def test_authentication_scopes_a_password_token_to_the_project():
    """
    arrange: A Keystone that issues a token, and a project to scope it to.
    act: List the project's security groups.
    assert: The token request carries the password grant, the user and project domains, and
        the project scope, so the token cannot act outside the configured project.
    """
    client, transport = _client([_auth_response(), _response(200, {"security_groups": []})])

    client.security_groups()

    auth = json.loads(transport.requests[0]["body"])
    assert transport.requests[0]["method"] == "POST"
    assert transport.requests[0]["url"] == "https://keystone.example.com:5000/v3/auth/tokens"
    assert auth == {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {
                    "user": {
                        "name": "admin",
                        "domain": {"name": "Default"},
                        "password": "s3cr3t",
                    }
                },
            },
            "scope": {"project": {"name": "myproject", "domain": {"name": "Default"}}},
        }
    }


def test_requests_use_the_public_endpoint_of_the_configured_region():
    """
    arrange: A catalog listing an internal endpoint and two public ones in different regions.
    act: List the project's security groups.
    assert: The request goes to the public endpoint of the configured region, without a
        doubled slash.
    """
    client, transport = _client([_auth_response(), _response(200, {"security_groups": []})])

    client.security_groups()

    assert transport.requests[1]["url"] == "https://neutron.example.com:9696/security-groups"


def test_requests_carry_the_token():
    """
    arrange: A Keystone that issues a token.
    act: List the project's security groups.
    assert: The Neutron request authenticates with that token, so it acts as the configured
        user rather than anonymously.
    """
    client, transport = _client([_auth_response(), _response(200, {"security_groups": []})])

    client.security_groups()

    assert transport.requests[1]["headers"]["X-Auth-Token"] == "token-1"


def test_token_is_reused_across_requests():
    """
    arrange: A client that has already authenticated.
    act: Make two Neutron requests.
    assert: Only one token is requested, so a reconcile does not re-authenticate per call.
    """
    client, transport = _client(
        [
            _auth_response(),
            _response(200, {"security_groups": []}),
            _response(200, {"security_group_rules": []}),
        ]
    )

    client.security_groups()
    client.security_group_rules("sg-1")

    assert [request["method"] for request in transport.requests] == ["POST", "GET", "GET"]


def test_expired_token_is_refreshed_once():
    """
    arrange: A Neutron that rejects the cached token as expired.
    act: List the project's security groups.
    assert: The client authenticates again and retries, so a token expiring between hooks
        does not fail the reconcile.
    """
    client, transport = _client(
        [
            _auth_response(),
            _response(401, {"error": {"message": "token expired"}}),
            _auth_response(),
            _response(200, {"security_groups": [{"id": "sg-1", "name": "garm-runner"}]}),
        ]
    )

    groups = client.security_groups()

    assert groups == [{"id": "sg-1", "name": "garm-runner"}]
    assert [request["method"] for request in transport.requests] == ["POST", "GET", "POST", "GET"]
    assert transport.requests[3]["headers"]["X-Auth-Token"] == "token-1"


def test_rejected_credentials_are_reported_once_not_retried():
    """
    arrange: A Keystone that rejects the password.
    act: List the project's security groups.
    assert: The failure reports Keystone's own message, and no request is retried — bad
        credentials do not resolve within a reconcile.
    """
    client, transport = _client(
        [
            _response(
                401, {"error": {"message": "The request you have made requires authentication"}}
            )
        ]
    )

    with pytest.raises(OpenStackClientError) as exc_info:
        client.security_groups()

    assert "Keystone rejected the credentials (401)" in str(exc_info.value)
    assert "requires authentication" in str(exc_info.value)
    assert len(transport.requests) == 1


def test_missing_token_header_is_reported():
    """
    arrange: A Keystone that answers 201 but omits the token header.
    act: List the project's security groups.
    assert: The failure is reported rather than the client sending an empty token.
    """
    client, _ = _client([_response(201, CATALOG)])

    with pytest.raises(OpenStackClientError) as exc_info:
        client.security_groups()

    assert str(exc_info.value) == "Keystone returned no token"


def test_missing_networking_endpoint_is_reported():
    """
    arrange: A catalog with no public networking endpoint for the configured region.
    act: List the project's security groups.
    assert: The failure names the region, so an operator can see which catalog entry is
        missing.
    """
    client, _ = _client([_auth_response()], region="RegionThree")

    with pytest.raises(OpenStackClientError) as exc_info:
        client.security_groups()

    assert str(exc_info.value) == (
        "the Keystone catalog has no public networking endpoint for region RegionThree"
    )


def test_neutron_error_message_is_reported():
    """
    arrange: A Neutron that rejects a rule.
    act: Create a rule.
    assert: The failure carries Neutron's own explanation, which names the invalid field.
    """
    client, _ = _client(
        [
            _auth_response(),
            _response(400, {"NeutronError": {"message": "Security group rule already exists"}}),
        ]
    )

    with pytest.raises(OpenStackClientError) as exc_info:
        client.create_security_group_rule("sg-1", {"direction": "ingress"})

    assert "POST /security-group-rules failed with 400" in str(exc_info.value)
    assert "Security group rule already exists" in str(exc_info.value)


def test_non_json_error_body_is_truncated():
    """
    arrange: A proxy answering with an HTML error page instead of JSON.
    act: List the project's security groups.
    assert: The reported detail is bounded, so a page of HTML cannot fill the status message.
    """
    client, _ = _client(
        [
            _auth_response(),
            (502, {}, b"<html>" + b"x" * (MAX_DETAIL_LENGTH * 2) + b"</html>"),
        ]
    )

    with pytest.raises(OpenStackClientError) as exc_info:
        client.security_groups()

    detail = str(exc_info.value).split(": ", 1)[1]
    assert len(detail) == MAX_DETAIL_LENGTH


def test_rule_creation_sends_the_group_and_fields():
    """
    arrange: A group to add a rule to.
    act: Create one rule.
    assert: The body nests the fields under the Neutron resource name, with the group id.
    """
    client, transport = _client(
        [_auth_response(), _response(201, {"security_group_rule": {"id": "rule-1"}})]
    )

    client.create_security_group_rule("sg-1", {"direction": "ingress", "protocol": "tcp"})

    assert json.loads(transport.requests[1]["body"]) == {
        "security_group_rule": {
            "security_group_id": "sg-1",
            "direction": "ingress",
            "protocol": "tcp",
        }
    }


def test_rule_listing_filters_by_group():
    """
    arrange: A group whose rules are wanted.
    act: List the rules.
    assert: The request filters by group id, so the reconcile never considers another group's
        rules.
    """
    client, transport = _client([_auth_response(), _response(200, {"security_group_rules": []})])

    client.security_group_rules("sg 1")

    assert transport.requests[1]["url"] == (
        "https://neutron.example.com:9696/security-group-rules?security_group_id=sg+1"
    )


def test_rule_deletion_sends_no_body():
    """
    arrange: A rule to delete.
    act: Delete it.
    assert: The request is a bodyless DELETE, which Neutron accepts without a JSON body.
    """
    client, transport = _client([_auth_response(), (204, {}, b"")])

    client.delete_security_group_rule("rule-1")

    assert transport.requests[1]["method"] == "DELETE"
    assert transport.requests[1]["url"] == (
        "https://neutron.example.com:9696/security-group-rules/rule-1"
    )
    assert transport.requests[1]["body"] is None


def test_missing_response_key_is_reported():
    """
    arrange: A Neutron answering 200 with a body that lacks the expected key.
    act: List the project's security groups.
    assert: The failure is reported as a client error, so a malformed response blocks the unit
        instead of crashing the hook with a KeyError.
    """
    client, _ = _client([_auth_response(), _response(200, {"unexpected": []})])

    with pytest.raises(OpenStackClientError) as exc_info:
        client.security_groups()

    assert str(exc_info.value) == ("GET /security-groups returned no 'security_groups' list")


def test_group_creation_sends_the_name_and_description():
    """
    arrange: A project without the managed group.
    act: Create the group.
    assert: The body names it and marks it charm-managed, so an operator reading the OpenStack
        console knows not to edit it by hand.
    """
    client, transport = _client(
        [_auth_response(), _response(201, {"security_group": {"id": "sg-1"}})]
    )

    client.create_security_group("garm-my-scaleset", "Managed by the charm")

    assert json.loads(transport.requests[1]["body"]) == {
        "security_group": {"name": "garm-my-scaleset", "description": "Managed by the charm"}
    }


class _FakeResponse:
    """A response, as urlopen returns one."""

    status = 200
    headers = {"Content-Type": "application/json"}

    def read(self):
        return b'{"ok": true}'

    def __enter__(self):
        return self

    def __exit__(self, *_exception):
        return False


def test_transport_returns_the_response(monkeypatch):
    """
    arrange: A server answering successfully.
    act: Send a request through the default transport.
    assert: The status, headers, and body reach the caller, so the client can decode them.
    """
    sent = {}

    def urlopen(request, timeout=None):
        sent["url"] = request.full_url
        sent["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    status, headers, body = _urlopen_transport(
        "GET", "https://neutron.example.com:9696/security-groups", {"Accept": "x"}, None
    )

    assert (status, headers, body) == (200, {"Content-Type": "application/json"}, b'{"ok": true}')
    assert sent["url"] == "https://neutron.example.com:9696/security-groups"


def test_transport_returns_http_errors_as_responses(monkeypatch):
    """
    arrange: A server rejecting the request.
    act: Send it through the default transport.
    assert: The error is returned rather than raised, so the client can report OpenStack's own
        explanation instead of a bare traceback.
    """

    def urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url,
            403,
            "Forbidden",
            {"X-Test": "1"},
            io.BytesIO(b'{"error": {"message": "Policy does not allow this request"}}'),
        )

    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    status, headers, body = _urlopen_transport(
        "POST", "https://neutron.example.com:9696/security-groups", {}, b"{}"
    )

    assert status == 403
    assert headers["X-Test"] == "1"
    assert b"Policy does not allow" in body


def test_transport_reports_an_unreachable_server(monkeypatch):
    """
    arrange: A server that cannot be reached at all.
    act: Send a request through the default transport.
    assert: The failure names the URL and the reason, so the blocked status tells an operator
        what to check.
    """

    def urlopen(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    with pytest.raises(OpenStackClientError) as exc_info:
        _urlopen_transport("GET", "https://neutron.example.com:9696/security-groups", {}, None)

    assert str(exc_info.value) == (
        "cannot reach https://neutron.example.com:9696/security-groups: connection refused"
    )


def test_transport_refuses_a_non_http_url():
    """
    arrange: A URL whose scheme is not http or https.
    act: Send a request through the default transport.
    assert: The transport refuses, so a malformed catalog endpoint cannot read a local file.
    """
    with pytest.raises(OpenStackClientError) as exc_info:
        _urlopen_transport("GET", "file:///etc/passwd", {}, None)

    assert str(exc_info.value) == "refusing to call a non-HTTP URL: file:///etc/passwd"
