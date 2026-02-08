"""Tests pour core/config.py"""
import json
from pathlib import Path
from unittest.mock import patch

from core.config import (
    DEFAULT_CONFIG,
    load_config,
    save_config,
    ensure_dirs,
    get_default_paths,
    get_media_dirs,
    cleanup_logs,
    cleanup_old_logs,
)


class TestDefaultConfig:
    def test_default_config_has_required_keys(self):
        required = [
            "download_dir", "token_file", "urls_file", "db_file",
            "logs_dir", "bsky_handle", "bsky_app_password",
        ]
        for key in required:
            assert key in DEFAULT_CONFIG, f"Clé manquante : {key}"

    def test_default_credentials_empty(self):
        assert DEFAULT_CONFIG["bsky_handle"] == ""
        assert DEFAULT_CONFIG["bsky_app_password"] == ""

    def test_default_max_workers(self):
        assert DEFAULT_CONFIG["max_workers"] == 4


class TestGetDefaultPaths:
    def test_returns_three_dirs(self):
        paths = get_default_paths()
        assert "img_dir" in paths
        assert "vid_dir" in paths
        assert "text_dir" in paths

    def test_paths_under_bsmb(self):
        paths = get_default_paths()
        assert "BSMB" in paths["img_dir"]
        assert paths["img_dir"].endswith("images")
        assert paths["vid_dir"].endswith("videos")
        assert paths["text_dir"].endswith("texts")


class TestLoadSaveConfig:
    def test_load_creates_default_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.config.CONFIG_FILE", tmp_path / "config.json")
        config = load_config()
        assert config["urls_file"] == DEFAULT_CONFIG["urls_file"]

    def test_save_and_reload(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.json"
        monkeypatch.setattr("core.config.CONFIG_FILE", config_file)

        config = load_config()
        config["bsky_handle"] = "test.bsky.social"
        save_config(config)

        raw = json.loads(config_file.read_text(encoding="utf-8"))
        assert raw["bsky_handle"] == "test.bsky.social"

    def test_migration_img_dir_to_download_dir(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.json"
        old_config = {
            "img_dir": str(tmp_path / "media" / "images"),
            "vid_dir": str(tmp_path / "media" / "videos"),
            "urls_file": "urls.txt",
        }
        config_file.write_text(json.dumps(old_config), encoding="utf-8")
        monkeypatch.setattr("core.config.CONFIG_FILE", config_file)

        config = load_config()
        assert "img_dir" not in config
        assert "vid_dir" not in config
        assert config["download_dir"] == str(tmp_path / "media")


class TestEnsureDirs:
    def test_creates_subdirectories(self, tmp_path):
        config = {"download_dir": str(tmp_path / "dl"), "logs_dir": str(tmp_path / "logs")}
        ensure_dirs(config)
        assert (tmp_path / "dl" / "images").is_dir()
        assert (tmp_path / "dl" / "videos").is_dir()
        assert (tmp_path / "dl" / "texts").is_dir()
        assert (tmp_path / "logs").is_dir()


class TestGetMediaDirs:
    def test_returns_correct_paths(self, tmp_path):
        config = {"download_dir": str(tmp_path / "dl")}
        dirs = get_media_dirs(config)
        assert dirs["img_dir"].endswith("images")
        assert dirs["vid_dir"].endswith("videos")
        assert dirs["text_dir"].endswith("texts")


class TestCleanupLogs:
    def test_cleanup_deletes_all_logs(self, tmp_path):
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (logs_dir / "file1.log").write_text("test")
        (logs_dir / "file2.txt").write_text("test")

        config = {"logs_dir": str(logs_dir)}
        deleted = cleanup_logs(config)
        assert deleted == 2
        assert list(logs_dir.iterdir()) == []

    def test_cleanup_empty_dir(self, tmp_path):
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        config = {"logs_dir": str(logs_dir)}
        assert cleanup_logs(config) == 0

    def test_cleanup_nonexistent_dir(self, tmp_path):
        config = {"logs_dir": str(tmp_path / "nope")}
        assert cleanup_logs(config) == 0


class TestCleanupOldLogs:
    def test_removes_old_files(self, tmp_path):
        import os
        import time

        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        old_file = logs_dir / "old.log"
        old_file.write_text("old")
        # Forcer une date ancienne
        old_time = time.time() - (15 * 86400)  # 15 jours
        os.utime(old_file, (old_time, old_time))

        new_file = logs_dir / "new.log"
        new_file.write_text("new")

        config = {"logs_dir": str(logs_dir)}
        cleanup_old_logs(config, max_age_days=10)

        assert not old_file.exists()
        assert new_file.exists()
