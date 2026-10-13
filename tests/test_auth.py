"""Tests pour core/auth.py"""

from unittest.mock import MagicMock, patch

import pytest

from core.auth import DEFAULT_PDS_URL, AuthError, create_session, get_session, get_token, has_credentials


class TestCreateSession:
    def test_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "accessJwt": "eyJ.token.xyz",
            "refreshJwt": "eyJ.refresh.xyz",
            "did": "did:plc:abc",
            "didDoc": {
                "service": [
                    {
                        "id": "#atproto_pds",
                        "type": "AtprotoPersonalDataServer",
                        "serviceEndpoint": "https://morel.us-east.host.bsky.network",
                    }
                ]
            },
        }
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        result = create_session("user.bsky.social", "xxxx-xxxx-xxxx-xxxx")
        assert result == {
            "token": "Bearer eyJ.token.xyz",
            "refresh_jwt": "eyJ.refresh.xyz",
            "did": "did:plc:abc",
            "pds_url": "https://morel.us-east.host.bsky.network",
        }
        mock_post.assert_called_once()

    def test_pds_url_fallback_without_service(self, mock_post):
        """didDoc sans service #atproto_pds → bsky.social."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "accessJwt": "eyJ.token.xyz",
            "didDoc": {"service": [{"id": "#autre", "serviceEndpoint": "https://x.example"}]},
        }
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        assert create_session("user", "pass")["pds_url"] == "https://bsky.social"

    def test_pds_url_fallback_without_didDoc(self, mock_post):
        """Réponse sans didDoc du tout → bsky.social."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"accessJwt": "eyJ.token.xyz"}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        session = create_session("user", "pass")
        assert session["pds_url"] == DEFAULT_PDS_URL == "https://bsky.social"
        assert session["token"] == "Bearer eyJ.token.xyz"

    def test_invalid_credentials(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_post.return_value = mock_resp

        with pytest.raises(AuthError, match="Identifiants invalides"):
            create_session("bad", "wrong")

    def test_rate_limit(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_post.return_value = mock_resp

        with pytest.raises(AuthError, match="Trop de tentatives"):
            create_session("user", "pass")

    def test_missing_jwt(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"did": "did:plc:xxx"}  # Pas de accessJwt
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        with pytest.raises(AuthError, match="accessJwt"):
            create_session("user", "pass")

    def test_connection_error(self, mock_post):
        import requests

        mock_post.side_effect = requests.exceptions.ConnectionError()

        with pytest.raises(AuthError, match="Impossible de se connecter"):
            create_session("user", "pass")

    def test_timeout(self, mock_post):
        import requests

        mock_post.side_effect = requests.exceptions.Timeout()

        with pytest.raises(AuthError, match="Timeout"):
            create_session("user", "pass")


class TestGetToken:
    @patch("core.auth.create_session")
    def test_with_credentials(self, mock_session):
        mock_session.return_value = {
            "token": "Bearer abc123",
            "refresh_jwt": "r",
            "did": "did:plc:x",
            "pds_url": "https://bsky.social",
        }
        config = {"bsky_handle": "user.bsky.social", "bsky_app_password": "xxxx-xxxx-xxxx-xxxx"}
        assert get_token(config) == "Bearer abc123"

    def test_fallback_to_file(self, tmp_path):
        token_file = tmp_path / "Token-Bearer.txt"
        token_file.write_text("Bearer file_token_123", encoding="utf-8")
        config = {
            "bsky_handle": "",
            "bsky_app_password": "",
            "token_file": str(token_file),
        }
        assert get_token(config) == "Bearer file_token_123"

    def test_invalid_file_token(self, tmp_path):
        token_file = tmp_path / "Token-Bearer.txt"
        token_file.write_text("not_a_bearer_token", encoding="utf-8")
        config = {
            "bsky_handle": "",
            "bsky_app_password": "",
            "token_file": str(token_file),
        }
        assert get_token(config) is None

    def test_no_credentials_no_file(self, tmp_path):
        config = {
            "bsky_handle": "",
            "bsky_app_password": "",
            "token_file": str(tmp_path / "nonexistent.txt"),
        }
        assert get_token(config) is None


class TestGetSession:
    @patch("core.auth.create_session")
    def test_with_credentials_returns_full_dict(self, mock_session):
        session = {
            "token": "Bearer abc123",
            "refresh_jwt": "r",
            "did": "did:plc:x",
            "pds_url": "https://morel.us-east.host.bsky.network",
        }
        mock_session.return_value = session
        config = {"bsky_handle": "user.bsky.social", "bsky_app_password": "xxxx-xxxx-xxxx-xxxx"}
        assert get_session(config) == session

    def test_file_fallback_uses_configured_pds_url(self, tmp_path):
        token_file = tmp_path / "Token-Bearer.txt"
        token_file.write_text("Bearer file_token_123", encoding="utf-8")
        config = {"token_file": str(token_file), "pds_url": "https://eurosky.social"}
        session = get_session(config)
        assert session["token"] == "Bearer file_token_123"
        assert session["pds_url"] == "https://eurosky.social"
        assert session["did"] is None and session["refresh_jwt"] is None

    def test_file_fallback_unknown_pds_url_defaults(self, tmp_path):
        token_file = tmp_path / "Token-Bearer.txt"
        token_file.write_text("Bearer file_token_123", encoding="utf-8")
        config = {"token_file": str(token_file), "pds_url": ""}
        assert get_session(config)["pds_url"] == "https://bsky.social"

    def test_nothing_available(self, tmp_path):
        assert get_session({"token_file": str(tmp_path / "nope.txt")}) is None


class TestHasCredentials:
    def test_has_both(self):
        config = {"bsky_handle": "user", "bsky_app_password": "pass"}
        assert has_credentials(config) is True

    def test_missing_handle(self):
        config = {"bsky_handle": "", "bsky_app_password": "pass"}
        assert has_credentials(config) is False

    def test_missing_password(self):
        config = {"bsky_handle": "user", "bsky_app_password": ""}
        assert has_credentials(config) is False

    def test_missing_both(self):
        config = {"bsky_handle": "", "bsky_app_password": ""}
        assert has_credentials(config) is False

    def test_missing_keys(self):
        assert has_credentials({}) is False


class TestSecretDansKeyring:
    """L'App Password peut être dans keyring, la clé de config vide (issue #12)."""

    @staticmethod
    def _keyring(monkeypatch, pwd="kr-pass"):
        import sys
        import types

        kr = types.ModuleType("keyring")
        kr.get_password = lambda service, user: pwd if (service, user) == ("bsmb", "user") else None
        monkeypatch.setitem(sys.modules, "keyring", kr)

    def test_has_credentials_avec_secret_en_keyring(self, monkeypatch):
        self._keyring(monkeypatch)
        assert has_credentials({"bsky_handle": "user", "bsky_app_password": ""}) is True

    def test_has_credentials_sans_secret_nulle_part(self):
        assert has_credentials({"bsky_handle": "user", "bsky_app_password": ""}) is False

    @patch("core.auth.create_session")
    def test_get_session_utilise_le_secret_keyring(self, mock_session, monkeypatch):
        self._keyring(monkeypatch)
        mock_session.return_value = {
            "token": "Bearer k",
            "refresh_jwt": None,
            "did": None,
            "pds_url": "https://bsky.social",
        }
        get_session({"bsky_handle": "user", "bsky_app_password": "", "token_file": "absent.txt"})
        mock_session.assert_called_once_with("user", "kr-pass")
