"""Tous les appels réseau passent par la session partagée de core/http.py (issue #11)."""

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from api.export_bookmarks import fetch_bookmarks
from api.post_analyzer import PostAnalyzer, PostType
from api.quote_resolver import QuoteResolver
from core import http as bsmb_http
from core.auth import create_session
from core.post_ref import resolve_handle

RACINE = Path(__file__).parent.parent
URL = "https://bsky.app/profile/user.bsky.social/post/3abc123def"


def test_aucun_appel_direct_a_requests():
    """Hors core/http.py, plus de requests.get / post / head / Session dans le code livré."""
    motif = re.compile(r"\brequests\.(get|post|head|put|delete|request|Session)\s*\(")
    fautifs = []
    for dossier in ("api", "core", "downloaders", "bsmb.py"):
        chemin = RACINE / dossier
        fichiers = [chemin] if chemin.is_file() else sorted(chemin.glob("*.py"))
        for fichier in fichiers:
            if fichier.name == "http.py":
                continue
            for n, ligne in enumerate(fichier.read_text(encoding="utf-8").splitlines(), 1):
                if motif.search(ligne):
                    fautifs.append(f"{fichier.relative_to(RACINE)}:{n}")
    assert fautifs == []


def test_aucun_import_direct_de_get_session():
    """`from core.http import get_session` lierait le nom au module et échapperait au patch des
    tests : les modules de production passent par `bsmb_http.get_session()`."""
    motif = re.compile(r"^\s*from\s+core\.http\s+import\s+.*\bget_session\b", re.MULTILINE)
    fautifs = []
    for dossier in ("api", "core", "downloaders", "tools", "bsmb.py"):
        chemin = RACINE / dossier
        fichiers = [chemin] if chemin.is_file() else sorted(chemin.glob("*.py"))
        for fichier in fichiers:
            if motif.search(fichier.read_text(encoding="utf-8")):
                fautifs.append(str(fichier.relative_to(RACINE)))
    assert fautifs == []


def test_la_barriere_reseau_bloque_les_hotes_externes():
    import socket

    with pytest.raises(AssertionError, match="interdit"):
        socket.create_connection(("bsky.social", 443), timeout=1)


def test_analyseur_utilise_la_session_partagee_par_defaut(fake_session):
    fake_session.get.return_value = MagicMock(status_code=400)
    assert PostAnalyzer().analyze(URL)[0] == PostType.ERROR_400
    fake_session.get.assert_called_once()


def test_analyseur_prefere_la_session_fournie(fake_session):
    perso = MagicMock()
    perso.get.return_value = MagicMock(status_code=400)
    PostAnalyzer(perso).analyze(URL)
    perso.get.assert_called_once()
    fake_session.get.assert_not_called()


def test_resolveur_de_citation_utilise_la_session_fournie(fake_session):
    perso = MagicMock()
    perso.get.return_value = MagicMock(status_code=200, json=lambda: {"handle": "h.example.com"})
    assert QuoteResolver(perso)._resolve_did_to_handle("did:plc:x") == "h.example.com"
    fake_session.get.assert_not_called()


def test_resolve_handle_session_fournie(fake_session):
    perso = MagicMock()
    perso.get.return_value.json.return_value = {"did": "did:plc:abc"}
    assert resolve_handle("a.example.com", session=perso) == "did:plc:abc"
    fake_session.get.assert_not_called()


def test_create_session_poste_sur_la_session_partagee(fake_session):
    fake_session.post.return_value = MagicMock(status_code=200, json=lambda: {"accessJwt": "jwt"})
    assert create_session("h", "p")["token"] == "Bearer jwt"
    fake_session.post.assert_called_once()


def test_export_passe_les_en_tetes_par_requete(fake_session):
    fake_session.get.return_value = MagicMock(status_code=200, json=lambda: {"bookmarks": []})
    fetch_bookmarks("Bearer t")
    en_tetes = fake_session.get.call_args.kwargs["headers"]
    assert en_tetes["Authorization"] == "Bearer t"
    assert en_tetes["atproto-proxy"] == "did:web:api.bsky.app#bsky_appview"
    # la session commune ne porte jamais le jeton
    fake_session.headers.update.assert_not_called()
    fake_session.headers.__setitem__.assert_not_called()


def test_la_vraie_session_ne_garde_pas_le_jeton():
    session = bsmb_http.build_session()
    assert "Authorization" not in session.headers


def test_orchestrateur_cree_une_seule_session(tmp_config, fake_session, monkeypatch):
    from core import orchestrator

    vus = []
    monkeypatch.setattr(orchestrator, "PostAnalyzer", lambda s=None: vus.append(("a", s)) or MagicMock())
    monkeypatch.setattr(orchestrator, "QuoteResolver", lambda s=None: vus.append(("q", s)) or MagicMock())
    orchestrator.run([], tmp_config, no_db=True, quiet=True)
    assert vus == [("a", fake_session), ("q", fake_session)]
