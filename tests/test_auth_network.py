"""Distinction erreur réseau / erreur d'authentification dans core/auth.py."""

from unittest.mock import MagicMock

import pytest
import requests

from core.auth import AuthError, NetworkError, create_session


class TestNetworkError:
    def test_est_une_auth_error(self):
        assert issubclass(NetworkError, AuthError)

    def test_connection_error(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError()
        with pytest.raises(NetworkError):
            create_session("user", "pass")

    def test_timeout(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout()
        with pytest.raises(NetworkError):
            create_session("user", "pass")

    @pytest.mark.parametrize("statut,reseau", [(500, True), (503, True), (400, False)])
    def test_statut_http(self, mock_post, statut, reseau):
        resp = MagicMock(status_code=statut)
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=resp)
        mock_post.return_value = resp
        with pytest.raises(AuthError) as exc:
            create_session("user", "pass")
        assert isinstance(exc.value, NetworkError) is reseau

    @pytest.mark.parametrize("statut", [401, 429])
    def test_401_et_429_restent_auth_error(self, mock_post, statut):
        mock_post.return_value = MagicMock(status_code=statut)
        with pytest.raises(AuthError) as exc:
            create_session("user", "pass")
        assert not isinstance(exc.value, NetworkError)
