"""Résolution du PDS avant createSession (revue finale, I5).

handle -> DID (resolveHandle sur public.api.bsky.app) -> document DID (plc.directory ou
did:web) -> service #atproto_pds ; repli sur https://bsky.social si une étape échoue.
"""

from unittest.mock import MagicMock

import pytest
import requests

from core.auth import DEFAULT_PDS_URL, create_session, resolve_pds

RESOLVE = "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle"
PDS = "https://pds.eurosky.example"


def _rep(json_data=None, status=200):
    rep = MagicMock(status_code=status)
    rep.json.return_value = json_data
    if status >= 400:
        rep.raise_for_status.side_effect = requests.HTTPError(f"{status}", response=rep)
    return rep


def _doc(did, endpoint=PDS):
    return {
        "id": did,
        "service": [
            {"id": "#bsky_notif", "type": "X", "serviceEndpoint": "https://autre.example"},
            {"id": "#atproto_pds", "type": "AtprotoPersonalDataServer", "serviceEndpoint": endpoint},
        ],
    }


def _session(reponses):
    """Session factice : GET selon l'URL (dict url -> réponse ou exception)."""
    session = MagicMock()

    def get(url, params=None, **kwargs):
        cle = url if params is None else f"{url}?handle={params.get('handle')}"
        rep = reponses.get(cle)
        if rep is None:
            return _rep(status=404)
        if isinstance(rep, Exception):
            raise rep
        return rep

    session.get.side_effect = get
    return session


class TestResolvePds:
    def test_did_plc(self):
        did = "did:plc:abc123"
        session = _session(
            {
                f"{RESOLVE}?handle=moi.eurosky.social": _rep({"did": did}),
                f"https://plc.directory/{did}": _rep(_doc(did, PDS + "/")),
            }
        )
        assert resolve_pds("moi.eurosky.social", session=session) == PDS

    def test_did_web(self):
        did = "did:web:moi.example.org"
        session = _session(
            {
                f"{RESOLVE}?handle=moi.example.org": _rep({"did": did}),
                "https://moi.example.org/.well-known/did.json": _rep(_doc(did)),
            }
        )
        assert resolve_pds("moi.example.org", session=session) == PDS

    def test_identifiant_deja_un_did(self):
        did = "did:plc:abc123"
        session = _session({f"https://plc.directory/{did}": _rep(_doc(did))})
        assert resolve_pds(did, session=session) == PDS

    def test_handle_avec_arobase_initial(self):
        did = "did:plc:abc123"
        session = _session(
            {
                f"{RESOLVE}?handle=moi.eurosky.social": _rep({"did": did}),
                f"https://plc.directory/{did}": _rep(_doc(did)),
            }
        )
        assert resolve_pds("@moi.eurosky.social", session=session) == PDS

    @pytest.mark.parametrize(
        "reponses",
        [
            {},  # resolveHandle en 404
            {f"{RESOLVE}?handle=moi.eurosky.social": requests.ConnectionError("hors ligne")},
            {f"{RESOLVE}?handle=moi.eurosky.social": _rep({"did": "did:plc:x"})},  # plc.directory 404
            {
                f"{RESOLVE}?handle=moi.eurosky.social": _rep({"did": "did:plc:x"}),
                "https://plc.directory/did:plc:x": _rep({"service": []}),  # pas de #atproto_pds
            },
            {f"{RESOLVE}?handle=moi.eurosky.social": _rep({"did": "did:key:zzz"})},  # méthode inconnue
            {f"{RESOLVE}?handle=moi.eurosky.social": _rep(None)},  # corps inattendu
        ],
    )
    def test_echec_repli_bsky_social(self, reponses):
        assert resolve_pds("moi.eurosky.social", session=_session(reponses)) == DEFAULT_PDS_URL

    def test_adresse_mail_repli_sans_requete(self):
        session = _session({})
        assert resolve_pds("moi@example.org", session=session) == DEFAULT_PDS_URL
        session.get.assert_not_called()


class TestCreateSessionSurLePdsResolu:
    def _post_ok(self, session):
        rep = _rep({"accessJwt": "a", "refreshJwt": "r", "did": "did:plc:abc123"})
        session.post.return_value = rep

    def test_createsession_sur_le_pds_resolu(self):
        did = "did:plc:abc123"
        session = _session(
            {
                f"{RESOLVE}?handle=moi.eurosky.social": _rep({"did": did}),
                f"https://plc.directory/{did}": _rep(_doc(did)),
            }
        )
        self._post_ok(session)
        resultat = create_session("moi.eurosky.social", "xxxx", session=session)
        assert session.post.call_args.args[0] == f"{PDS}/xrpc/com.atproto.server.createSession"
        assert resultat["pds_url"] == PDS

    def test_repli_sur_bsky_social(self):
        session = _session({})
        self._post_ok(session)
        resultat = create_session("moi.bsky.social", "xxxx", session=session)
        assert session.post.call_args.args[0] == "https://bsky.social/xrpc/com.atproto.server.createSession"
        assert resultat["pds_url"] == DEFAULT_PDS_URL
