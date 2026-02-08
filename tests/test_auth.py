"""Tests pour core/auth.py"""
from unittest.mock import patch, MagicMock

import pytest

from core.auth import create_session, get_token, has_credentials, AuthError


class TestCreateSession:
    @patch("core.auth.requests.post")
    def test_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"accessJwt": "eyJ.token.xyz"}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        result = create_session("user.bsky.social", "xxxx-xxxx-xxxx-xxxx")
        assert result == "Bearer eyJ.token.xyz"
        mock_post.assert_called_once()

    @patch("core.auth.requests.post")
    def test_invalid_credentials(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_post.return_value = mock_resp

        with pytest.raises(AuthError, match="Identifiants invalides"):
            create_session("bad", "wrong")

    @patch("core.auth.requests.post")
    def test_rate_limit(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_post.return_value = mock_resp

        with pytest.raises(AuthError, match="Trop de tentatives"):
            create_session("user", "pass")

    @patch("core.auth.requests.post")
    def test_missing_jwt(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"did": "did:plc:xxx"}  # Pas de accessJwt
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        with pytest.raises(AuthError, match="accessJwt"):
            create_session("user", "pass")

    @patch("core.auth.requests.post")
    def test_connection_error(self, mock_post):
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError()

        with pytest.raises(AuthError, match="Impossible de se connecter"):
            create_session("user", "pass")

    @patch("core.auth.requests.post")
    def test_timeout(self, mock_post):
        import requests
        mock_post.side_effect = requests.exceptions.Timeout()

        with pytest.raises(AuthError, match="Timeout"):
            create_session("user", "pass")


class TestGetToken:
    @patch("core.auth.create_session")
    def test_with_credentials(self, mock_session):
        mock_session.return_value = "Bearer abc123"
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
