"""Tests pour core/database.py"""
from core.database import Database


class TestDatabaseInit:
    def test_creates_tables(self, tmp_db):
        cursor = tmp_db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert "posts" in tables
        assert "media" in tables

    def test_creates_file(self, tmp_path):
        db_path = str(tmp_path / "new.db")
        db = Database(db_path)
        assert (tmp_path / "new.db").exists()
        db.close()


class TestAddPost:
    def test_add_and_retrieve(self, tmp_db):
        tmp_db.add_post("https://bsky.app/profile/user/post/123", "123", "user")
        cursor = tmp_db.conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE url = ?", ("https://bsky.app/profile/user/post/123",))
        row = cursor.fetchone()
        assert row is not None
        assert row[1] == "123"  # post_id
        assert row[2] == "user"  # handle

    def test_add_duplicate_replaces(self, tmp_db):
        tmp_db.add_post("https://bsky.app/profile/user/post/123", "123", "user1")
        tmp_db.add_post("https://bsky.app/profile/user/post/123", "123", "user2")
        cursor = tmp_db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM posts WHERE url = ?",
                        ("https://bsky.app/profile/user/post/123",))
        assert cursor.fetchone()[0] == 1


class TestAddMedia:
    def test_add_image(self, tmp_db):
        url = "https://bsky.app/profile/user/post/123"
        tmp_db.add_post(url, "123", "user")
        tmp_db.add_media(url, "image", "user_20260207_123_01.jpg")

        cursor = tmp_db.conn.cursor()
        cursor.execute("SELECT * FROM media WHERE post_url = ?", (url,))
        row = cursor.fetchone()
        assert row is not None
        assert row[2] == "image"
        assert row[3] == "user_20260207_123_01.jpg"

    def test_add_multiple_media(self, tmp_db):
        url = "https://bsky.app/profile/user/post/456"
        tmp_db.add_post(url, "456", "user")
        tmp_db.add_media(url, "image", "img1.jpg")
        tmp_db.add_media(url, "image", "img2.jpg")
        tmp_db.add_media(url, "video", "vid1.mp4")

        cursor = tmp_db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM media WHERE post_url = ?", (url,))
        assert cursor.fetchone()[0] == 3


class TestGetNewPosts:
    def test_all_new(self, tmp_db):
        urls = [
            "https://bsky.app/profile/user/post/1",
            "https://bsky.app/profile/user/post/2",
        ]
        result = tmp_db.get_new_posts(urls)
        assert result == urls

    def test_some_already_tracked(self, tmp_db):
        tmp_db.add_post("https://bsky.app/profile/user/post/1", "1", "user")
        urls = [
            "https://bsky.app/profile/user/post/1",
            "https://bsky.app/profile/user/post/2",
        ]
        result = tmp_db.get_new_posts(urls)
        assert result == ["https://bsky.app/profile/user/post/2"]

    def test_all_tracked(self, tmp_db):
        tmp_db.add_post("https://bsky.app/profile/user/post/1", "1", "user")
        result = tmp_db.get_new_posts(["https://bsky.app/profile/user/post/1"])
        assert result == []

    def test_empty_list(self, tmp_db):
        assert tmp_db.get_new_posts([]) == []


class TestGetStats:
    def test_empty_stats(self, tmp_db):
        stats = tmp_db.get_stats()
        assert stats == {"posts": 0, "images": 0, "videos": 0, "texts": 0, "dead": 0}

    def test_stats_with_data(self, tmp_db):
        url1 = "https://bsky.app/profile/user/post/1"
        url2 = "https://bsky.app/profile/user/post/2"
        tmp_db.add_post(url1, "1", "user")
        tmp_db.add_post(url2, "2", "user")
        tmp_db.add_media(url1, "image", "img1.jpg")
        tmp_db.add_media(url1, "image", "img2.jpg")
        tmp_db.add_media(url2, "video", "vid1.mp4")

        stats = tmp_db.get_stats()
        assert stats["posts"] == 2
        assert stats["images"] == 2
        assert stats["videos"] == 1
        assert stats["texts"] == 0
        assert stats["dead"] == 0

    def test_stats_with_texts(self, tmp_db):
        url = "https://bsky.app/profile/user/post/1"
        tmp_db.add_post(url, "1", "user")
        tmp_db.add_media(url, "text", "text1.txt")

        stats = tmp_db.get_stats()
        assert stats["texts"] == 1

    def test_stats_with_dead(self, tmp_db):
        url1 = "https://bsky.app/profile/user/post/1"
        url2 = "https://bsky.app/profile/user/post/2"
        tmp_db.add_post(url1, "1", "user")
        tmp_db.add_post(url2, "2", "user")
        tmp_db.mark_post_status(url1, "deleted")

        stats = tmp_db.get_stats()
        assert stats["dead"] == 1


class TestUpdateLastCheck:
    def test_updates_timestamp(self, tmp_db):
        url = "https://bsky.app/profile/user/post/1"
        tmp_db.add_post(url, "1", "user")

        cursor = tmp_db.conn.cursor()
        cursor.execute("SELECT last_check FROM posts WHERE url = ?", (url,))
        first_check = cursor.fetchone()[0]

        import time
        time.sleep(0.01)
        tmp_db.update_last_check(url)

        cursor.execute("SELECT last_check FROM posts WHERE url = ?", (url,))
        second_check = cursor.fetchone()[0]
        assert second_check > first_check


class TestMarkPostStatus:
    def test_mark_deleted(self, tmp_db):
        url = "https://bsky.app/profile/user/post/1"
        tmp_db.add_post(url, "1", "user")
        tmp_db.mark_post_status(url, "deleted")

        cursor = tmp_db.conn.cursor()
        cursor.execute("SELECT status FROM posts WHERE url = ?", (url,))
        assert cursor.fetchone()[0] == "deleted"

    def test_mark_error_500(self, tmp_db):
        url = "https://bsky.app/profile/user/post/1"
        tmp_db.add_post(url, "1", "user")
        tmp_db.mark_post_status(url, "error_500")

        cursor = tmp_db.conn.cursor()
        cursor.execute("SELECT status FROM posts WHERE url = ?", (url,))
        assert cursor.fetchone()[0] == "error_500"

    def test_default_status_is_ok(self, tmp_db):
        url = "https://bsky.app/profile/user/post/1"
        tmp_db.add_post(url, "1", "user")

        cursor = tmp_db.conn.cursor()
        cursor.execute("SELECT status FROM posts WHERE url = ?", (url,))
        assert cursor.fetchone()[0] == "ok"


class TestGetDeadCount:
    def test_no_dead(self, tmp_db):
        tmp_db.add_post("https://bsky.app/profile/user/post/1", "1", "user")
        assert tmp_db.get_dead_count() == 0

    def test_with_dead(self, tmp_db):
        url1 = "https://bsky.app/profile/user/post/1"
        url2 = "https://bsky.app/profile/user/post/2"
        url3 = "https://bsky.app/profile/user/post/3"
        tmp_db.add_post(url1, "1", "user")
        tmp_db.add_post(url2, "2", "user")
        tmp_db.add_post(url3, "3", "user")
        tmp_db.mark_post_status(url1, "deleted")
        tmp_db.mark_post_status(url2, "error_500")
        assert tmp_db.get_dead_count() == 2

    def test_empty_db(self, tmp_db):
        assert tmp_db.get_dead_count() == 0


class TestGetDeadPosts:
    def test_returns_dead_posts(self, tmp_db):
        url1 = "https://bsky.app/profile/user/post/1"
        url2 = "https://bsky.app/profile/user/post/2"
        tmp_db.add_post(url1, "1", "user")
        tmp_db.add_post(url2, "2", "user")
        tmp_db.mark_post_status(url1, "deleted")

        dead = tmp_db.get_dead_posts()
        assert len(dead) == 1
        assert dead[0] == (url1, "deleted")

    def test_no_dead_returns_empty(self, tmp_db):
        tmp_db.add_post("https://bsky.app/profile/user/post/1", "1", "user")
        assert tmp_db.get_dead_posts() == []


class TestCleanupDeadPosts:
    def test_cleanup_removes_deleted(self, tmp_db):
        url1 = "https://bsky.app/profile/user/post/1"
        url2 = "https://bsky.app/profile/user/post/2"
        tmp_db.add_post(url1, "1", "user")
        tmp_db.add_post(url2, "2", "user")
        tmp_db.add_media(url1, "image", "img.jpg")
        tmp_db.mark_post_status(url1, "deleted")

        count = tmp_db.cleanup_dead_posts()
        assert count == 1
        assert tmp_db.get_stats()["posts"] == 1
        assert tmp_db.get_stats()["images"] == 0

    def test_cleanup_keeps_error_500(self, tmp_db):
        url = "https://bsky.app/profile/user/post/1"
        tmp_db.add_post(url, "1", "user")
        tmp_db.mark_post_status(url, "error_500")

        count = tmp_db.cleanup_dead_posts()
        assert count == 0
        assert tmp_db.get_stats()["posts"] == 1

    def test_cleanup_empty_db(self, tmp_db):
        assert tmp_db.cleanup_dead_posts() == 0


class TestMigration:
    def test_status_column_exists(self, tmp_db):
        cursor = tmp_db.conn.cursor()
        columns = [row[1] for row in cursor.execute('PRAGMA table_info(posts)').fetchall()]
        assert 'status' in columns
