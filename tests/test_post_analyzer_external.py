"""Analyse des embeds app.bsky.embed.external (issue #4) avec des fixtures getRecord."""
import copy
import json
from pathlib import Path
from unittest.mock import MagicMock

from api.post_analyzer import PostAnalyzer, PostType

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://bsky.app/profile/auteur.test/post/3ktest000001"
DID = "did:plc:test000000000000000000000"


def _charger(nom):
    return json.loads((FIXTURES / nom).read_text(encoding="utf-8"))


def _analyser(reponse):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    resp.json.return_value = reponse
    session = MagicMock()
    session.get.return_value = resp
    return PostAnalyzer(session).analyze(URL)


class TestExternalSimple:
    def test_carte_de_lien_avec_vignette(self):
        post_type, data, debug = _analyser(_charger("external_link.json"))
        assert post_type == PostType.EXTERNAL
        assert data["external"] == {
            "uri": "https://example.com/article",
            "title": "Titre de la carte",
            "description": "Description de la carte.",
            "thumb_cid": "bafkreitest0000000000000000000000000000000000000000000000",
        }
        assert data["did"] == DID
        assert data["handle"] == "auteur.test"
        assert data["created_at"] == "2026-01-05T17:24:26.493Z"
        assert "is_quote" not in data
        assert debug["embed_type"] == "app.bsky.embed.external"

    def test_carte_sans_vignette(self):
        post_type, data, _ = _analyser(_charger("external_gif.json"))
        assert post_type == PostType.EXTERNAL
        assert data["external"]["thumb_cid"] is None

    def test_gif_tenor(self):
        _, data, _ = _analyser(_charger("external_gif.json"))
        assert data["external"]["uri"] == "https://media.tenor.com/abc/tenor.gif"

    def test_champs_manquants_tolérés(self):
        rep = _charger("external_link.json")
        rep["value"]["embed"]["external"] = {"uri": "https://example.com/x"}
        post_type, data, _ = _analyser(rep)
        assert post_type == PostType.EXTERNAL
        assert data["external"]["title"] == ""
        assert data["external"]["description"] == ""

    def test_external_vide_reste_inconnu(self):
        rep = _charger("external_link.json")
        rep["value"]["embed"]["external"] = {}
        post_type, _, _ = _analyser(rep)
        assert post_type == PostType.UNKNOWN


class TestRecordWithMediaExternal:
    def _rep(self):
        rep = copy.deepcopy(_charger("external_link.json"))
        ext = rep["value"]["embed"]
        rep["value"]["embed"] = {
            "$type": "app.bsky.embed.recordWithMedia",
            "record": {"$type": "app.bsky.embed.record",
                       "record": {"uri": f"at://{DID}/app.bsky.feed.post/3kcite", "cid": "bafy"}},
            "media": ext,
        }
        return rep

    def test_external_dans_record_with_media(self):
        post_type, data, _ = _analyser(self._rep())
        assert post_type == PostType.EXTERNAL
        assert data["is_quote"] is True
        assert data["external"]["uri"] == "https://example.com/article"
        assert data["external"]["thumb_cid"].startswith("bafkrei")
        assert data["embed_type"] == "app.bsky.embed.recordWithMedia"
        assert data["did"] == DID
