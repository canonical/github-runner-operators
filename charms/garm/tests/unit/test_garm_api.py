# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for garm_api.py."""

from unittest.mock import MagicMock, patch

import pytest

from garm_api import (
    GarmApiClient,
    GarmApiError,
    GarmAuthenticatedClient,
    GarmConnectionError,
)


BASE_URL = "http://127.0.0.1:9997/api/v1"


class TestGarmApiClientLogin:
    """Tests for GarmApiClient.login()."""

    def test_login_returns_token(self):
        client = GarmApiClient(BASE_URL)
        mock_result = MagicMock()
        mock_result.token = "test-jwt-token"
        with patch("garm_api.LoginApi") as MockLoginApi:
            MockLoginApi.return_value.login.return_value = mock_result
            with patch.object(client, "_api_client") as mock_api_client:
                mock_api_client.return_value.__enter__ = MagicMock(return_value=MagicMock())
                mock_api_client.return_value.__exit__ = MagicMock(return_value=False)
                token = client.login("admin", "password")
        assert token == "test-jwt-token"

    def test_login_raises_on_api_exception(self):
        from garm_client.exceptions import ApiException

        client = GarmApiClient(BASE_URL)
        with patch("garm_api.LoginApi") as MockLoginApi:
            MockLoginApi.return_value.login.side_effect = ApiException(status=401, reason="Unauthorized")
            with patch.object(client, "_api_client") as mock_api_client:
                mock_api_client.return_value.__enter__ = MagicMock(return_value=MagicMock())
                mock_api_client.return_value.__exit__ = MagicMock(return_value=False)
                with pytest.raises(GarmApiError):
                    client.login("admin", "wrong")

    def test_login_raises_when_token_empty(self):
        client = GarmApiClient(BASE_URL)
        mock_result = MagicMock()
        mock_result.token = ""
        with patch("garm_api.LoginApi") as MockLoginApi:
            MockLoginApi.return_value.login.return_value = mock_result
            with patch.object(client, "_api_client") as mock_api_client:
                mock_api_client.return_value.__enter__ = MagicMock(return_value=MagicMock())
                mock_api_client.return_value.__exit__ = MagicMock(return_value=False)
                with pytest.raises(GarmApiError, match="token"):
                    client.login("admin", "password")


class TestGarmApiClientIsInitialized:
    """Tests for GarmApiClient.is_initialized()."""

    def test_returns_true_on_200(self):
        from garm_client.exceptions import ApiException

        client = GarmApiClient(BASE_URL)
        with patch("garm_api.ControllerInfoApi") as MockApi:
            MockApi.return_value.controller_info.return_value = MagicMock()
            with patch.object(client, "_api_client") as mock_api_client:
                mock_api_client.return_value.__enter__ = MagicMock(return_value=MagicMock())
                mock_api_client.return_value.__exit__ = MagicMock(return_value=False)
                result = client.is_initialized()
        assert result is True

    def test_returns_false_on_409(self):
        from garm_client.exceptions import ApiException

        client = GarmApiClient(BASE_URL)
        with patch("garm_api.ControllerInfoApi") as MockApi:
            MockApi.return_value.controller_info.side_effect = ApiException(status=409)
            with patch.object(client, "_api_client") as mock_api_client:
                mock_api_client.return_value.__enter__ = MagicMock(return_value=MagicMock())
                mock_api_client.return_value.__exit__ = MagicMock(return_value=False)
                result = client.is_initialized()
        assert result is False

    def test_raises_on_unexpected_status(self):
        from garm_client.exceptions import ApiException

        client = GarmApiClient(BASE_URL)
        with patch("garm_api.ControllerInfoApi") as MockApi:
            MockApi.return_value.controller_info.side_effect = ApiException(status=500)
            with patch.object(client, "_api_client") as mock_api_client:
                mock_api_client.return_value.__enter__ = MagicMock(return_value=MagicMock())
                mock_api_client.return_value.__exit__ = MagicMock(return_value=False)
                with pytest.raises(GarmApiError):
                    client.is_initialized()


class TestGarmApiClientWaitForReady:
    """Tests for GarmApiClient.wait_for_ready()."""

    def test_returns_immediately_when_ready(self):
        client = GarmApiClient(BASE_URL)
        with patch.object(client, "is_initialized", return_value=True):
            client.wait_for_ready(timeout=5)

    def test_raises_after_timeout(self):
        client = GarmApiClient(BASE_URL)
        with patch.object(client, "is_initialized", side_effect=GarmConnectionError("refused")):
            with patch("garm_api.time.sleep"):
                with patch("garm_api.time.monotonic", side_effect=[0, 0, 100]):
                    with pytest.raises(GarmConnectionError, match="ready"):
                        client.wait_for_ready(timeout=30)


class TestGarmApiClientFirstRun:
    """Tests for GarmApiClient.first_run()."""

    def test_first_run_success(self):
        client = GarmApiClient(BASE_URL)
        with patch("garm_api.FirstRunApi") as MockApi:
            MockApi.return_value.first_run.return_value = MagicMock()
            with patch.object(client, "_api_client") as mock_api_client:
                mock_api_client.return_value.__enter__ = MagicMock(return_value=MagicMock())
                mock_api_client.return_value.__exit__ = MagicMock(return_value=False)
                client.first_run("admin", "pass", "email@example.com", "Admin")

    def test_first_run_raises_on_api_error(self):
        from garm_client.exceptions import ApiException

        client = GarmApiClient(BASE_URL)
        with patch("garm_api.FirstRunApi") as MockApi:
            MockApi.return_value.first_run.side_effect = ApiException(status=400)
            with patch.object(client, "_api_client") as mock_api_client:
                mock_api_client.return_value.__enter__ = MagicMock(return_value=MagicMock())
                mock_api_client.return_value.__exit__ = MagicMock(return_value=False)
                with pytest.raises(GarmApiError):
                    client.first_run("admin", "pass", "email@example.com", "Admin")


class TestGarmAuthenticatedClientListProviders:
    """Tests for GarmAuthenticatedClient.list_providers()."""

    def test_returns_provider_list(self):
        client = GarmAuthenticatedClient(BASE_URL, "token")
        mock_provider = MagicMock()
        mock_provider.name = "openstack"
        with patch("garm_api.ProvidersApi") as MockApi:
            MockApi.return_value.list_providers.return_value = [mock_provider]
            with patch.object(client, "_api_client") as mock_api_client:
                mock_api_client.return_value.__enter__ = MagicMock(return_value=MagicMock())
                mock_api_client.return_value.__exit__ = MagicMock(return_value=False)
                result = client.list_providers()
        assert len(result) == 1
        assert result[0].name == "openstack"

    def test_returns_empty_on_none(self):
        client = GarmAuthenticatedClient(BASE_URL, "token")
        with patch("garm_api.ProvidersApi") as MockApi:
            MockApi.return_value.list_providers.return_value = None
            with patch.object(client, "_api_client") as mock_api_client:
                mock_api_client.return_value.__enter__ = MagicMock(return_value=MagicMock())
                mock_api_client.return_value.__exit__ = MagicMock(return_value=False)
                result = client.list_providers()
        assert result == []


class TestGarmAuthenticatedClientListScalesets:
    """Tests for GarmAuthenticatedClient.list_scalesets()."""

    def test_returns_scaleset_list(self):
        client = GarmAuthenticatedClient(BASE_URL, "token")
        mock_ss = MagicMock()
        mock_ss.name = "test-scaleset"
        mock_ss.id = 1
        with patch("garm_api.ScalesetsApi") as MockApi:
            MockApi.return_value.list_scalesets.return_value = [mock_ss]
            with patch.object(client, "_api_client") as mock_api_client:
                mock_api_client.return_value.__enter__ = MagicMock(return_value=MagicMock())
                mock_api_client.return_value.__exit__ = MagicMock(return_value=False)
                result = client.list_scalesets()
        assert len(result) == 1
        assert result[0].name == "test-scaleset"


class TestGarmAuthenticatedClientFindOrgId:
    """Tests for GarmAuthenticatedClient.find_org_id()."""

    def test_returns_org_id_when_found(self):
        client = GarmAuthenticatedClient(BASE_URL, "token")
        mock_org = MagicMock()
        mock_org.name = "my-org"
        mock_org.id = "org-uuid-123"
        with patch("garm_api.OrganizationsApi") as MockApi:
            MockApi.return_value.list_orgs.return_value = [mock_org]
            with patch.object(client, "_api_client") as mock_api_client:
                mock_api_client.return_value.__enter__ = MagicMock(return_value=MagicMock())
                mock_api_client.return_value.__exit__ = MagicMock(return_value=False)
                result = client.find_org_id("my-org")
        assert result == "org-uuid-123"

    def test_returns_none_when_not_found(self):
        client = GarmAuthenticatedClient(BASE_URL, "token")
        with patch("garm_api.OrganizationsApi") as MockApi:
            MockApi.return_value.list_orgs.return_value = []
            with patch.object(client, "_api_client") as mock_api_client:
                mock_api_client.return_value.__enter__ = MagicMock(return_value=MagicMock())
                mock_api_client.return_value.__exit__ = MagicMock(return_value=False)
                result = client.find_org_id("nonexistent")
        assert result is None


class TestGarmAuthenticatedClientDeleteScaleset:
    """Tests for GarmAuthenticatedClient.delete_scaleset()."""

    def test_delete_calls_api(self):
        client = GarmAuthenticatedClient(BASE_URL, "token")
        with patch("garm_api.ScalesetsApi") as MockApi:
            with patch.object(client, "_api_client") as mock_api_client:
                mock_api_client.return_value.__enter__ = MagicMock(return_value=MagicMock())
                mock_api_client.return_value.__exit__ = MagicMock(return_value=False)
                client.delete_scaleset(42)
            MockApi.return_value.delete_scale_set.assert_called_once()

    def test_delete_raises_on_api_error(self):
        from garm_client.exceptions import ApiException

        client = GarmAuthenticatedClient(BASE_URL, "token")
        with patch("garm_api.ScalesetsApi") as MockApi:
            MockApi.return_value.delete_scale_set.side_effect = ApiException(status=404)
            with patch.object(client, "_api_client") as mock_api_client:
                mock_api_client.return_value.__enter__ = MagicMock(return_value=MagicMock())
                mock_api_client.return_value.__exit__ = MagicMock(return_value=False)
                with pytest.raises(GarmApiError):
                    client.delete_scaleset(99)
