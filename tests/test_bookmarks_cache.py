"""Tests de core/bookmarks_cache.py : cache JSON de la dernière réponse getBookmarks (issue #3)."""
import json
from pathlib import Path

from core.bookmarks_cache import load_cache, save_cache

URI1 = "at://did:plc:test1000000000000000000000/app.bsky.feed.post/3kpost00001"
URI2 = "at://did:plc:test2000000000000000000000/app.bsky.feed.post/3kgone000001"


def _posts():
    return [
        {"at_uri": URI1, "did": "did:plc:test1000000000000000000000", "rkey": "3kpost00001",
         "handle": "alice.example.com", "url": "https://bsky.app/profile/alice.example.com/post/3kpost00001",
         "item_type": "postView", "post_view": {"uri": URI1, "record": {"text": "été"}},
         "created_at": "2026-03-01T10:00:00.000Z"},
        {"at_uri": URI2, "did": "did:plc:test2000000000000000000000", "rkey": "3kgone000001",
         "handle": None, "url": "https://bsky.app/profile/did:plc:test2000000000000000000000/post/3kgone000001",
         "item_type": "notFoundPost", "post_view": None, "created_at": None},
    ]


class TestCache:
    def test_aller_retour(self, tmp_path):
        chemin = tmp_path / "bookmarks.json"
        save_cache(chemin, _posts(), pds_url="https://pds.example.com")
        cache = load_cache(chemin)
        assert list(cache) == [URI1, URI2]
        assert cache[URI1]["post_view"]["record"]["text"] == "été"
        assert cache[URI2]["item_type"] == "notFoundPost"

    def test_format_du_fichier(self, tmp_path):
        chemin = tmp_path / "bookmarks.json"
        save_cache(chemin, _posts(), pds_url="https://pds.example.com")
        brut = json.loads(chemin.read_text(encoding="utf-8"))
        assert set(brut) == {"saved_at", "pds_url", "posts"}
        assert brut["pds_url"] == "https://pds.example.com"
        assert len(brut["posts"]) == 2
        assert "été" in chemin.read_text(encoding="utf-8")  # UTF-8 lisible, pas d'échappement

    def test_fichier_absent(self, tmp_path):
        assert load_cache(tmp_path / "absent.json") == {}

    def test_json_corrompu(self, tmp_path, capsys):
        chemin = tmp_path / "bookmarks.json"
        chemin.write_text("{pas du json", encoding="utf-8")
        assert load_cache(chemin) == {}
        assert "bookmarks.json" in capsys.readouterr().err

    def test_structure_inattendue(self, tmp_path):
        chemin = tmp_path / "bookmarks.json"
        chemin.write_text('["liste"]', encoding="utf-8")
        assert load_cache(chemin) == {}
        chemin.write_text('{"posts": [1, {"url": "x"}]}', encoding="utf-8")
        assert load_cache(chemin) == {}  # aucune entrée avec at_uri

    def test_ecriture_remplace_le_fichier(self, tmp_path):
        chemin = tmp_path / "bookmarks.json"
        save_cache(chemin, _posts())
        save_cache(chemin, _posts()[:1])
        assert list(load_cache(chemin)) == [URI1]
        assert not list(tmp_path.glob("*.tmp"))

    def test_permissions_restreintes(self, tmp_path, monkeypatch):
        appels = []
        monkeypatch.setattr("core.bookmarks_cache.restrict_permissions", appels.append)
        chemin = tmp_path / "bookmarks.json"
        save_cache(chemin, _posts())
        assert appels == [chemin]

    def test_chemin_str_accepte(self, tmp_path):
        save_cache(str(tmp_path / "c.json"), _posts())
        assert URI1 in load_cache(str(tmp_path / "c.json"))
