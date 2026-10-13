"""Tests pour core/bookmarks.py — classe BookmarkSync"""
from unittest.mock import patch, MagicMock
from pathlib import Path

from core.database import Database
from core.bookmarks import BookmarkSync


class TestBookmarkSyncInit:
    def test_creates_instance(self, tmp_config, tmp_db):
        sync = BookmarkSync(tmp_config, tmp_db)
        assert sync.config is tmp_config
        assert sync.db is tmp_db
        assert sync._online_urls is None


class TestBookmarkSyncSync:
    @patch("core.bookmarks.fetch_bookmarks")
    @patch("core.bookmarks.save_config")
    def test_sync_success(self, mock_save, mock_fetch, tmp_config, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        tmp_config["urls_file"] = str(tmp_path / "urls.txt")
        tmp_config["db_file"] = str(tmp_path / "test.db")

        mock_fetch.return_value = {
            "urls": [
                "https://bsky.app/profile/user/post/1",
                "https://bsky.app/profile/user/post/2",
            ],
            "posts": [
                {"at_uri": None, "url": "https://bsky.app/profile/user/post/1"},
                {"at_uri": None, "url": "https://bsky.app/profile/user/post/2"},
            ],
            "count": 2,
            "pages": 1,
            "error": None,
            "expired": False,
        }

        sync = BookmarkSync(tmp_config, db)
        result = sync.sync("Bearer test")

        assert result["error"] is None
        assert result["online_count"] == 2
        assert result["new_count"] == 2
        assert result["local_count"] == 0
        assert len(result["new_urls"]) == 2

        # Vérifie que urls.txt a été écrit
        urls_file = Path(tmp_config["urls_file"])
        assert urls_file.exists()
        content = urls_file.read_text(encoding="utf-8")
        assert "user/post/1" in content
        assert "user/post/2" in content

        # Vérifie que last_sync a été mis à jour
        assert tmp_config["last_sync"] != ""
        mock_save.assert_called_once()

        db.close()

    @patch("core.bookmarks.fetch_bookmarks")
    @patch("core.bookmarks.save_config")
    def test_sync_with_existing_posts(self, mock_save, mock_fetch, tmp_config, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        tmp_config["urls_file"] = str(tmp_path / "urls.txt")
        tmp_config["db_file"] = str(tmp_path / "test.db")

        # Ajouter un post existant
        db.add_post("https://bsky.app/profile/user/post/1", "1", "user")

        mock_fetch.return_value = {
            "urls": [
                "https://bsky.app/profile/user/post/1",
                "https://bsky.app/profile/user/post/2",
            ],
            "posts": [
                {"at_uri": None, "url": "https://bsky.app/profile/user/post/1"},
                {"at_uri": None, "url": "https://bsky.app/profile/user/post/2"},
            ],
            "count": 2,
            "pages": 1,
            "error": None,
            "expired": False,
        }

        sync = BookmarkSync(tmp_config, db)
        result = sync.sync("Bearer test")

        assert result["online_count"] == 2
        assert result["local_count"] == 1
        assert result["new_count"] == 1
        assert result["new_urls"] == ["https://bsky.app/profile/user/post/2"]

        db.close()

    @patch("core.bookmarks.fetch_bookmarks")
    def test_sync_api_error(self, mock_fetch, tmp_config, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        tmp_config["db_file"] = str(tmp_path / "test.db")

        mock_fetch.return_value = {
            "urls": [], "posts": [],
            "count": 0,
            "pages": 0,
            "error": "Erreur réseau",
            "expired": False,
        }

        sync = BookmarkSync(tmp_config, db)
        result = sync.sync("Bearer test")

        assert result["error"] == "Erreur réseau"
        assert result["expired"] is False

        db.close()

    @patch("core.bookmarks.fetch_bookmarks")
    def test_sync_expired_token(self, mock_fetch, tmp_config, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        tmp_config["db_file"] = str(tmp_path / "test.db")

        mock_fetch.return_value = {
            "urls": [], "posts": [],
            "count": 0,
            "pages": 1,
            "error": "Token expiré",
            "expired": True,
        }

        sync = BookmarkSync(tmp_config, db)
        result = sync.sync("Bearer expired")

        assert result["error"] == "Token expiré"
        assert result["expired"] is True

        db.close()

    @patch("core.bookmarks.fetch_bookmarks")
    @patch("core.bookmarks.save_config")
    def test_sync_progress_callback(self, mock_save, mock_fetch, tmp_config, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        tmp_config["urls_file"] = str(tmp_path / "urls.txt")
        tmp_config["db_file"] = str(tmp_path / "test.db")

        mock_fetch.return_value = {
            "urls": [], "posts": [],
            "count": 0,
            "pages": 1,
            "error": None,
            "expired": False,
        }

        progress_calls = []
        sync = BookmarkSync(tmp_config, db)
        sync.sync("Bearer test", on_progress=lambda p, c: progress_calls.append((p, c)))

        # Vérifie que on_progress a été passé à fetch_bookmarks
        mock_fetch.assert_called_once()
        assert mock_fetch.call_args[1].get("on_progress") is not None or mock_fetch.call_args[0][1] is not None

        db.close()


class TestBookmarkSyncPdsUrl:
    @patch("core.bookmarks.fetch_bookmarks")
    @patch("core.bookmarks.save_config")
    def test_sync_passes_configured_pds_url(self, mock_save, mock_fetch, tmp_config, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        tmp_config["pds_url"] = "https://eurosky.social"
        mock_fetch.return_value = {
            "urls": [], "posts": [], "count": 0, "pages": 1, "error": None, "expired": False,
        }
        BookmarkSync(tmp_config, db).sync("Bearer test")
        assert mock_fetch.call_args[1]["pds_url"] == "https://eurosky.social"
        db.close()

    @patch("core.bookmarks.fetch_bookmarks")
    @patch("core.bookmarks.save_config")
    def test_sync_defaults_when_pds_url_unknown(self, mock_save, mock_fetch, tmp_config, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        tmp_config["pds_url"] = ""
        mock_fetch.return_value = {
            "urls": [], "posts": [], "count": 0, "pages": 1, "error": None, "expired": False,
        }
        BookmarkSync(tmp_config, db).sync("Bearer test")
        assert mock_fetch.call_args[1]["pds_url"] == "https://bsky.social"
        db.close()


class TestBookmarkSyncGetCachedState:
    def test_no_cache(self, tmp_config, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        tmp_config["urls_file"] = str(tmp_path / "urls.txt")
        tmp_config["db_file"] = str(tmp_path / "test.db")

        sync = BookmarkSync(tmp_config, db)
        state = sync.get_cached_state()

        assert state["online_count"] == 0
        assert state["local_count"] == 0
        assert state["new_count"] == 0
        assert state["has_cache"] is False
        assert state["last_sync"] == ""

        db.close()

    def test_with_cache(self, tmp_config, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text(
            "https://bsky.app/profile/user/post/1\nhttps://bsky.app/profile/user/post/2\n",
            encoding="utf-8",
        )
        tmp_config["urls_file"] = str(urls_file)
        tmp_config["db_file"] = str(tmp_path / "test.db")
        tmp_config["last_sync"] = "2025-01-15T10:00:00"

        # Un post déjà traité
        db.add_post("https://bsky.app/profile/user/post/1", "1", "user")

        sync = BookmarkSync(tmp_config, db)
        state = sync.get_cached_state()

        assert state["online_count"] == 2
        assert state["local_count"] == 1
        assert state["new_count"] == 1
        assert state["has_cache"] is True
        assert state["last_sync"] == "2025-01-15T10:00:00"

        db.close()

    def test_with_dead_posts(self, tmp_config, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        tmp_config["urls_file"] = str(tmp_path / "urls.txt")
        tmp_config["db_file"] = str(tmp_path / "test.db")

        db.add_post("https://bsky.app/profile/user/post/1", "1", "user")
        db.mark_post_status("https://bsky.app/profile/user/post/1", "deleted")

        sync = BookmarkSync(tmp_config, db)
        state = sync.get_cached_state()

        assert state["dead_count"] == 1

        db.close()


# --------------------------------------------------- postView, notFoundPost, blockedPost (issue #3)

def _page_fixture():
    import json
    chemin = Path(__file__).parent / "fixtures" / "bookmarks_page.json"
    return json.loads(chemin.read_text(encoding="utf-8"))


def _posts_de_la_page():
    """Sortie de fetch_bookmarks() pour la page de la fixture (construite à la main)."""
    posts = []
    for bm in _page_fixture()["bookmarks"]:
        item = bm["item"]
        type_item = item["$type"].split("#")[1]
        did = item["uri"].split("/")[2]
        rkey = item["uri"].rsplit("/", 1)[1]
        handle = item.get("author", {}).get("handle")
        posts.append({
            "at_uri": item["uri"], "did": did, "rkey": rkey, "handle": handle,
            "url": f"https://bsky.app/profile/{handle or did}/post/{rkey}",
            "item_type": type_item, "post_view": item if type_item == "postView" else None,
            "created_at": bm["createdAt"],
        })
    return posts


def _fetch_de_la_page():
    posts = _posts_de_la_page()
    return {"urls": [p["url"] for p in posts], "posts": posts, "count": len(posts),
            "pages": 1, "error": None, "expired": False}


def _statut(db, url):
    ligne = db.conn.execute("SELECT status FROM posts WHERE url = ?", (url,)).fetchone()
    return ligne[0] if ligne else None


class TestSyncPostViews:
    @patch("core.bookmarks.fetch_bookmarks")
    @patch("core.bookmarks.save_config")
    def test_statuts_et_compte(self, mock_save, mock_fetch, tmp_config, tmp_db):
        mock_fetch.return_value = _fetch_de_la_page()
        posts = {p["item_type"]: p for p in mock_fetch.return_value["posts"]}

        result = BookmarkSync(tmp_config, tmp_db).sync("Bearer t")

        assert result["error"] is None
        assert result["online_count"] == 3
        assert result["new_urls"] == [posts["postView"]["url"]]
        assert result["new_count"] == 1
        assert _statut(tmp_db, posts["notFoundPost"]["url"]) == "deleted"
        assert _statut(tmp_db, posts["blockedPost"]["url"]) == "blocked"
        assert _statut(tmp_db, posts["postView"]["url"]) is None  # sera traité par run()
        assert result["dead_count"] == 2

    @patch("core.bookmarks.fetch_bookmarks")
    @patch("core.bookmarks.save_config")
    def test_identite_enregistree_pour_les_posts_morts(self, mock_save, mock_fetch, tmp_config, tmp_db):
        mock_fetch.return_value = _fetch_de_la_page()
        gone = next(p for p in mock_fetch.return_value["posts"] if p["item_type"] == "notFoundPost")
        BookmarkSync(tmp_config, tmp_db).sync("Bearer t")
        ligne = tmp_db.conn.execute("SELECT at_uri, did, rkey FROM posts WHERE url = ?", (gone["url"],)).fetchone()
        assert tuple(ligne) == (gone["at_uri"], gone["did"], gone["rkey"])

    @patch("core.bookmarks.fetch_bookmarks")
    @patch("core.bookmarks.save_config")
    def test_cache_ecrit_et_urls_txt_conserve(self, mock_save, mock_fetch, tmp_config, tmp_db):
        from core.bookmarks_cache import load_cache
        mock_fetch.return_value = _fetch_de_la_page()
        BookmarkSync(tmp_config, tmp_db).sync("Bearer t")

        cache = load_cache(tmp_config["bookmarks_cache"])
        assert set(cache) == {p["at_uri"] for p in mock_fetch.return_value["posts"]}
        vue = next(e for e in cache.values() if e["item_type"] == "postView")
        assert vue["post_view"]["record"]["text"] == "Voici une photo"
        urls = Path(tmp_config["urls_file"]).read_text(encoding="utf-8").splitlines()
        assert urls == mock_fetch.return_value["urls"]

    @patch("core.bookmarks.fetch_bookmarks")
    @patch("core.bookmarks.save_config")
    def test_post_deja_archive_garde_son_statut_ok(self, mock_save, mock_fetch, tmp_config, tmp_db):
        mock_fetch.return_value = _fetch_de_la_page()
        gone = next(p for p in mock_fetch.return_value["posts"] if p["item_type"] == "notFoundPost")
        tmp_db.add_post(gone["url"], gone["rkey"], None, at_uri=gone["at_uri"], did=gone["did"])
        tmp_db.mark_post_status(gone["url"], "ok")

        BookmarkSync(tmp_config, tmp_db).sync("Bearer t")

        assert _statut(tmp_db, gone["url"]) == "ok"  # contenu déjà archivé : on le conserve

    @patch("core.bookmarks.fetch_bookmarks")
    @patch("core.bookmarks.save_config")
    def test_blocked_jamais_retente(self, mock_save, mock_fetch, tmp_config, tmp_db):
        mock_fetch.return_value = _fetch_de_la_page()
        blocked = next(p for p in mock_fetch.return_value["posts"] if p["item_type"] == "blockedPost")
        BookmarkSync(tmp_config, tmp_db).sync("Bearer t")
        tmp_db.conn.execute("UPDATE posts SET last_check = '2000-01-01T00:00:00'")
        tmp_db.conn.commit()
        assert tmp_db.get_pending_refs([blocked], 7) == []

    @patch("core.bookmarks.fetch_bookmarks")
    @patch("core.bookmarks.save_config")
    def test_echec_d_ecriture_du_cache_ne_bloque_pas(self, mock_save, mock_fetch, tmp_config, tmp_db, tmp_path):
        mock_fetch.return_value = _fetch_de_la_page()
        tmp_config["bookmarks_cache"] = str(tmp_path / "absent" / "dossier" / "bookmarks.json")
        result = BookmarkSync(tmp_config, tmp_db).sync("Bearer t")
        assert result["error"] is None
        assert result["cache_error"]
        assert result["new_count"] == 1

    @patch("core.bookmarks.fetch_bookmarks")
    @patch("core.bookmarks.save_config")
    def test_erreur_api_n_ecrase_pas_le_cache(self, mock_save, mock_fetch, tmp_config, tmp_db):
        from core.bookmarks_cache import load_cache
        mock_fetch.return_value = _fetch_de_la_page()
        BookmarkSync(tmp_config, tmp_db).sync("Bearer t")
        mock_fetch.return_value = {"urls": [], "posts": [], "count": 0, "pages": 1,
                                   "error": "Erreur réseau", "expired": False}
        BookmarkSync(tmp_config, tmp_db).sync("Bearer t")
        assert len(load_cache(tmp_config["bookmarks_cache"])) == 3


class TestEtatEnCache:
    def test_online_count_vient_du_cache(self, tmp_config, tmp_db):
        from core.bookmarks_cache import save_cache
        save_cache(tmp_config["bookmarks_cache"], _posts_de_la_page())
        Path(tmp_config["urls_file"]).write_text("https://bsky.app/profile/u/post/1", encoding="utf-8")
        assert BookmarkSync(tmp_config, tmp_db).get_cached_state()["online_count"] == 3

    def test_sans_cache_urls_txt(self, tmp_config, tmp_db):
        Path(tmp_config["urls_file"]).write_text("https://bsky.app/profile/u/post/1", encoding="utf-8")
        etat = BookmarkSync(tmp_config, tmp_db).get_cached_state()
        assert etat["online_count"] == 1
        assert etat["has_cache"] is True
