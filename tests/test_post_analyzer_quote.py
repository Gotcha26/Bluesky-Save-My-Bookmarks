"""Analyse des citations (quote posts, issue #5) avec des fixtures getRecord."""
import copy
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from api.post_analyzer import PostAnalyzer, PostType

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://bsky.app/profile/citant.example.com/post/3kquote0001"


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


class TestCitation:
    def test_citation_de_texte(self):
        post_type, data, _ = _analyser(_charger("quote_text.json"))
        assert post_type == PostType.QUOTE
        assert data["is_quote"] is True
        assert data["text"] == "Regardez ça, incroyable !"
        assert data["created_at"] == "2026-02-10T09:30:00.000Z"
        assert data["handle"] == "citant.example.com"

    def test_quote_uri_expose_le_record_cite(self):
        uri = "at://did:plc:test2000000000000000000000/app.bsky.feed.post/3kcited0001"
        assert _analyser(_charger("quote_text.json"))[1]["quote_uri"] == uri
        assert _analyser(_charger("quote_with_media.json"))[1]["quote_uri"] == uri

    def test_citation_d_un_generateur_reste_une_citation(self):
        post_type, data, _ = _analyser(_charger("quote_of_generator.json"))
        assert post_type == PostType.QUOTE
        assert data["is_quote"] is True

    def test_recordwithmedia_images_pose_is_quote(self):
        post_type, data, _ = _analyser(_charger("quote_with_media.json"))
        assert post_type == PostType.IMAGES
        assert data["is_quote"] is True
        assert data["image_count"] == 1

    def test_recordwithmedia_video_pose_is_quote(self):
        fixture = _charger("quote_with_media.json")
        fixture["value"]["embed"]["media"] = {
            "$type": "app.bsky.embed.video",
            "video": {"ref": {"$link": "bafkreitestvideo"}, "mimeType": "video/mp4", "size": 10},
        }
        post_type, data, _ = _analyser(fixture)
        assert post_type == PostType.VIDEO
        assert data["is_quote"] is True

    def test_recordwithmedia_media_inconnu_devient_une_citation(self):
        fixture = copy.deepcopy(_charger("quote_with_media.json"))
        fixture["value"]["embed"]["media"] = {"$type": "app.bsky.embed.autre"}
        post_type, data, _ = _analyser(fixture)
        assert post_type == PostType.QUOTE
        assert data["is_quote"] is True

    def test_images_simples_ne_sont_pas_une_citation(self):
        fixture = _charger("quote_with_media.json")
        fixture["value"]["embed"] = fixture["value"]["embed"]["media"]
        post_type, data, _ = _analyser(fixture)
        assert post_type == PostType.IMAGES
        assert "is_quote" not in data
