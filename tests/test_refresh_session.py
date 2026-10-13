"""refreshSession (issue #11) : core.auth.refresh_session et son usage par BookmarkSync.sync()."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from core.auth import AuthError, NetworkError, refresh_session
from core.bookmarks import BookmarkSync

PDS = "https://morel.us-east.host.bsky.network"


def _reponse_ok(**extra):
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"accessJwt": "nouveau.access", "refreshJwt": "nouveau.refresh",
                              "did": "did:plc:abc", **extra}
    resp.raise_for_status.return_value = None
    return resp


class TestRefreshSession:
    def test_succes(self, mock_post):
        mock_post.return_value = _reponse_ok()
        assert refresh_session("ancien.refresh", PDS) == {
            "token": "Bearer nouveau.access",
            "refresh_jwt": "nouveau.refresh",
            "did": "did:plc:abc",
            "pds_url": PDS,
        }

    def test_requete_sur_le_pds_avec_le_jeton_de_rafraichissement(self, mock_post):
        mock_post.return_value = _reponse_ok()
        refresh_session("ancien.refresh", PDS + "/")
        assert mock_post.call_args.args[0] == f"{PDS}/xrpc/com.atproto.server.refreshSession"
        assert mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer ancien.refresh"

    def test_pds_du_didDoc_prioritaire(self, mock_post):
        doc = {"service": [{"id": "#atproto_pds", "serviceEndpoint": "https://autre.example"}]}
        mock_post.return_value = _reponse_ok(didDoc=doc)
        assert refresh_session("r", PDS)["pds_url"] == "https://autre.example"

    def test_session_fournie(self, mock_post):
        perso = MagicMock()
        perso.post.return_value = _reponse_ok()
        refresh_session("r", PDS, session=perso)
        perso.post.assert_called_once()
        mock_post.assert_not_called()

    @pytest.mark.parametrize("statut", [400, 401])
    def test_jeton_refuse_est_une_auth_error(self, mock_post, statut):
        mock_post.return_value = MagicMock(status_code=statut)
        with pytest.raises(AuthError) as exc:
            refresh_session("r", PDS)
        assert not isinstance(exc.value, NetworkError)

    def test_reponse_sans_access_jwt(self, mock_post):
        resp = _reponse_ok()
        resp.json.return_value = {}
        mock_post.return_value = resp
        with pytest.raises(AuthError):
            refresh_session("r", PDS)

    @pytest.mark.parametrize("erreur", [requests.exceptions.ConnectionError(), requests.exceptions.Timeout()])
    def test_erreur_reseau(self, mock_post, erreur):
        mock_post.side_effect = erreur
        with pytest.raises(NetworkError):
            refresh_session("r", PDS)

    def test_5xx_est_une_network_error(self, mock_post):
        resp = MagicMock(status_code=503)
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=resp)
        mock_post.return_value = resp
        with pytest.raises(NetworkError):
            refresh_session("r", PDS)


def _resultat(expired=False, error=None):
    return {"urls": [], "posts": [], "count": 0, "pages": 1,
            "error": error or ("Token expiré" if expired else None), "expired": expired}


@pytest.fixture
def sync(tmp_config, tmp_db):
    tmp_config["pds_url"] = PDS
    return BookmarkSync(tmp_config, tmp_db)


class TestSyncRefresh:
    @patch("core.bookmarks.save_config")
    @patch("core.bookmarks.refresh_session")
    @patch("core.bookmarks.fetch_bookmarks")
    def test_rafraichit_une_fois_puis_relance(self, fetch, refresh, _save, sync):
        fetch.side_effect = [_resultat(expired=True), _resultat()]
        refresh.return_value = {"token": "Bearer neuf", "refresh_jwt": "r2", "did": "d", "pds_url": PDS}
        info = {"token": "Bearer vieux", "refresh_jwt": "r1", "did": "d", "pds_url": PDS}

        resultat = sync.sync("Bearer vieux", session_info=info)

        refresh.assert_called_once_with("r1", PDS)
        assert fetch.call_count == 2
        assert fetch.call_args_list[0].args[0] == "Bearer vieux"
        assert fetch.call_args_list[1].args[0] == "Bearer neuf"
        assert resultat["error"] is None and resultat["expired"] is False
        assert info["token"] == "Bearer neuf" and info["refresh_jwt"] == "r2"

    @patch("core.bookmarks.refresh_session")
    @patch("core.bookmarks.fetch_bookmarks")
    def test_pas_de_deuxieme_rafraichissement(self, fetch, refresh, sync):
        fetch.side_effect = [_resultat(expired=True), _resultat(expired=True)]
        refresh.return_value = {"token": "Bearer neuf", "refresh_jwt": "r2", "did": "d", "pds_url": PDS}

        resultat = sync.sync("Bearer vieux", session_info={"refresh_jwt": "r1"})

        refresh.assert_called_once()
        assert fetch.call_count == 2
        assert resultat["expired"] is True

    @patch("core.bookmarks.refresh_session")
    @patch("core.bookmarks.fetch_bookmarks")
    def test_echec_du_rafraichissement_garde_expired(self, fetch, refresh, sync):
        fetch.return_value = _resultat(expired=True)
        refresh.side_effect = AuthError("refus")

        resultat = sync.sync("Bearer vieux", session_info={"refresh_jwt": "r1"})

        assert fetch.call_count == 1
        assert resultat["expired"] is True and resultat["error"]

    @patch("core.bookmarks.refresh_session")
    @patch("core.bookmarks.fetch_bookmarks")
    def test_panne_reseau_du_rafraichissement_est_une_erreur_reseau(self, fetch, refresh, sync):
        fetch.return_value = _resultat(expired=True)
        refresh.side_effect = NetworkError("timeout")

        resultat = sync.sync("Bearer vieux", session_info={"refresh_jwt": "r1"})

        assert fetch.call_count == 1
        assert resultat["expired"] is False
        assert "timeout" in resultat["error"] and "réseau" in resultat["error"]
        assert resultat["new_urls"] == []

    @patch("core.bookmarks.refresh_session")
    @patch("core.bookmarks.fetch_bookmarks")
    def test_sans_refresh_jwt_aucun_appel(self, fetch, refresh, sync):
        fetch.return_value = _resultat(expired=True)
        for info in (None, {}, {"refresh_jwt": None}):
            resultat = sync.sync("Bearer t", session_info=info)
            assert resultat["expired"] is True
        refresh.assert_not_called()
        assert fetch.call_count == 3

    @patch("core.bookmarks.refresh_session")
    @patch("core.bookmarks.fetch_bookmarks")
    def test_erreur_non_expiree_ne_rafraichit_pas(self, fetch, refresh, sync):
        fetch.return_value = _resultat(error="Erreur réseau")
        sync.sync("Bearer t", session_info={"refresh_jwt": "r1"})
        refresh.assert_not_called()
