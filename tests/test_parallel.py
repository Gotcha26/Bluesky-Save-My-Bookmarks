"""Tests pour la parallélisation (thread-safety DB, orchestrator helpers)."""
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.database import Database
from core.orchestrator import (
    format_size,
    format_duration,
    _format_job_summary,
)


class TestDatabaseThreadSafety:
    def test_concurrent_add_posts(self, tmp_path):
        """Plusieurs threads ajoutent des posts simultanément."""
        db = Database(str(tmp_path / "test.db"))
        errors = []

        def add_posts(start, count):
            try:
                for i in range(start, start + count):
                    db.add_post(f"https://bsky.app/profile/user/post/{i}", str(i), "user")
            except Exception as e:
                errors.append(e)

        threads = []
        for t in range(4):
            th = threading.Thread(target=add_posts, args=(t * 25, 25))
            threads.append(th)
            th.start()

        for th in threads:
            th.join()

        db_stats = db.get_stats()
        db.close()

        assert not errors, f"Erreurs thread-safety : {errors}"
        assert db_stats["posts"] == 100

    def test_concurrent_add_media(self, tmp_path):
        """Plusieurs threads ajoutent des médias simultanément."""
        db = Database(str(tmp_path / "test.db"))
        url = "https://bsky.app/profile/user/post/1"
        db.add_post(url, "1", "user")
        errors = []

        def add_media(start, count):
            try:
                for i in range(start, start + count):
                    db.add_media(url, "image", f"img_{i}.jpg")
            except Exception as e:
                errors.append(e)

        threads = []
        for t in range(4):
            th = threading.Thread(target=add_media, args=(t * 10, 10))
            threads.append(th)
            th.start()

        for th in threads:
            th.join()

        stats = db.get_stats()
        db.close()

        assert not errors
        assert stats["images"] == 40

    def test_concurrent_mixed_operations(self, tmp_path):
        """Mélange de lectures et écritures concurrentes."""
        db = Database(str(tmp_path / "test.db"))
        errors = []

        def writer(thread_id):
            try:
                for i in range(20):
                    url = f"https://bsky.app/profile/user/post/t{thread_id}_{i}"
                    db.add_post(url, f"t{thread_id}_{i}", "user")
                    db.add_media(url, "image", f"img_t{thread_id}_{i}.jpg")
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(20):
                    db.get_stats()
                    db.get_new_posts(["https://bsky.app/profile/user/post/nonexistent"])
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = []
            for t in range(4):
                futures.append(executor.submit(writer, t))
            for _ in range(2):
                futures.append(executor.submit(reader))

            for f in as_completed(futures):
                f.result()

        stats = db.get_stats()
        db.close()

        assert not errors
        assert stats["posts"] == 80
        assert stats["images"] == 80


class TestFormatSize:
    def test_bytes(self):
        assert format_size(500) == "500.00 o"

    def test_kilobytes(self):
        assert format_size(2048) == "2.00 Ko"

    def test_megabytes(self):
        assert format_size(5 * 1024 * 1024) == "5.00 Mo"

    def test_gigabytes(self):
        assert format_size(2 * 1024 ** 3) == "2.00 Go"

    def test_zero(self):
        assert format_size(0) == "0.00 o"


class TestFormatDuration:
    def test_seconds(self):
        assert format_duration(45) == "45s"

    def test_minutes(self):
        assert format_duration(125) == "2m 5s"

    def test_hours(self):
        assert format_duration(3661) == "1h 1m 1s"

    def test_zero(self):
        assert format_duration(0) == "0s"


class TestFormatJobSummary:
    def test_success_images(self):
        result = _format_job_summary(1, 10, "https://bsky.app/profile/user.bsky.social/post/abc123", "success", 3, 0, 0)
        assert "OK" in result
        assert "3 images" in result

    def test_success_video(self):
        result = _format_job_summary(2, 10, "https://bsky.app/profile/user/post/vid1", "success", 0, 1, 0)
        assert "OK" in result
        assert "1 vidéo" in result

    def test_success_text(self):
        result = _format_job_summary(3, 10, "https://bsky.app/profile/user/post/txt1", "success", 0, 0, 1)
        assert "1 texte" in result

    def test_error_400(self):
        result = _format_job_summary(4, 10, "https://bsky.app/profile/user/post/del1", "error_400", 0, 0, 0)
        assert "supprimé" in result

    def test_error_500(self):
        result = _format_job_summary(5, 10, "https://bsky.app/profile/user/post/err1", "error_500", 0, 0, 0)
        assert "serveur" in result

    def test_repost(self):
        result = _format_job_summary(6, 10, "https://bsky.app/profile/user/post/rp1", "repost", 0, 0, 0)
        assert "repost" in result

    def test_unknown(self):
        result = _format_job_summary(7, 10, "https://bsky.app/profile/user/post/unk1", "unknown", 0, 0, 0)
        assert "inconnu" in result

    def test_failed(self):
        result = _format_job_summary(8, 10, "https://bsky.app/profile/user/post/fail1", "failed", 0, 0, 0)
        assert "échec" in result or "!!" in result
