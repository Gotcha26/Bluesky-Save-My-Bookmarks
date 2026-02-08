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
            "urls": [],
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
            "urls": [],
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
            "urls": [],
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
