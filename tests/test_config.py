"""Tests pour core/config.py"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.config import (
    DEFAULT_CONFIG,
    load_config,
    save_config,
    ensure_dirs,
    get_default_paths,
    get_media_dirs,
    cleanup_logs,
    cleanup_old_logs,
    resolve_path,
    CONFIG_FILE,
)
from core.paths import PROJECT_ROOT


class TestCheminsAncres:
    def test_project_root_est_la_racine_du_depot(self):
        assert (PROJECT_ROOT / "bsmb.py").is_file()
        assert (PROJECT_ROOT / "core" / "paths.py").is_file()

    def test_config_file_ancre_sur_project_root(self):
        assert CONFIG_FILE == PROJECT_ROOT / "config.json"

    def test_resolve_path_relatif_ancre_sur_project_root(self):
        assert resolve_path({"db_file": "bsmb.db"}, "db_file") == PROJECT_ROOT / "bsmb.db"

    def test_resolve_path_absolu_inchange(self, tmp_path):
        chemin = tmp_path / "base.db"
        assert resolve_path({"db_file": str(chemin)}, "db_file") == chemin

    def test_resolve_path_independant_du_dossier_courant(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert resolve_path({"logs_dir": "logs"}, "logs_dir") == PROJECT_ROOT / "logs"

    def test_load_config_ne_modifie_pas_les_chemins_relatifs(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"db_file": "autre.db"}), encoding="utf-8")
        monkeypatch.setattr("core.config.CONFIG_FILE", config_file)
        config = load_config()
        assert config["db_file"] == "autre.db"
        assert config["logs_dir"] == "logs"


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

    @staticmethod
    def _logs_dates(logs_dir, noms):
        """Crée les fichiers dans l'ordre donné, du plus ancien au plus récent."""
        import os
        import time

        maintenant = time.time()
        for i, nom in enumerate(noms):
            fichier = logs_dir / nom
            fichier.write_text("x")
            horodatage = maintenant - (len(noms) - i) * 60
            os.utime(fichier, (horodatage, horodatage))

    def test_garde_au_plus_max_logs_logs_de_telechargement(self, tmp_path):
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        noms = [f"download_2026010{i}_000000.log" for i in range(1, 8)]
        self._logs_dates(logs_dir, noms)

        cleanup_old_logs({"logs_dir": str(logs_dir), "max_logs": 3})

        restants = sorted(p.name for p in logs_dir.iterdir())
        assert restants == noms[-3:]

    def test_max_logs_ne_touche_pas_aux_autres_fichiers(self, tmp_path):
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        self._logs_dates(logs_dir, ["failed_downloads_1.txt", "debug_x.json",
                                    "download_1.log", "download_2.log"])

        cleanup_old_logs({"logs_dir": str(logs_dir), "max_logs": 1})

        restants = sorted(p.name for p in logs_dir.iterdir())
        assert restants == ["debug_x.json", "download_2.log", "failed_downloads_1.txt"]

    def test_max_logs_par_defaut(self, tmp_path):
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        self._logs_dates(logs_dir, [f"download_{i}.log" for i in range(8)])

        cleanup_old_logs({"logs_dir": str(logs_dir)})

        assert len(list(logs_dir.iterdir())) == DEFAULT_CONFIG["max_logs"]


class TestConsommateursAncres:
    """Les chemins relatifs de la config sont résolus depuis PROJECT_ROOT, pas depuis le cwd."""

    def test_ensure_dirs_logs_relatif(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.config.PROJECT_ROOT", tmp_path / "racine")
        monkeypatch.chdir(tmp_path)
        ensure_dirs({"download_dir": str(tmp_path / "dl"), "logs_dir": "logs"})
        assert (tmp_path / "racine" / "logs").is_dir()
        assert not (tmp_path / "logs").exists()

    def test_cleanup_logs_relatif(self, tmp_path, monkeypatch):
        racine = tmp_path / "racine"
        (racine / "logs").mkdir(parents=True)
        (racine / "logs" / "a.log").write_text("x")
        monkeypatch.setattr("core.config.PROJECT_ROOT", racine)
        monkeypatch.chdir(tmp_path)
        assert cleanup_logs({"logs_dir": "logs"}) == 1

    def test_token_file_relatif(self, tmp_path, monkeypatch):
        from core.auth import get_session

        (tmp_path / "Token-Bearer.txt").write_text("Bearer abc", encoding="utf-8")
        monkeypatch.setattr("core.config.PROJECT_ROOT", tmp_path)
        monkeypatch.chdir(tmp_path.parent)
        session = get_session({"token_file": "Token-Bearer.txt"})
        assert session["token"] == "Bearer abc"

    def test_urls_file_relatif(self, tmp_path, monkeypatch):
        from core.bookmarks import BookmarkSync

        (tmp_path / "urls.txt").write_text("https://bsky.app/profile/a/post/1", encoding="utf-8")
        monkeypatch.setattr("core.config.PROJECT_ROOT", tmp_path)
        monkeypatch.chdir(tmp_path.parent)
        etat = BookmarkSync({"urls_file": "urls.txt"}, MagicMock()).get_cached_state()
        assert etat["online_count"] == 1
