"""Tests de bsmb.py : le téléchargement appelle orchestrator.run() directement (issue #10)."""
from unittest.mock import patch

import bsmb
from core.database import Database

URL = "https://bsky.app/profile/user.bsky.social/post/3k1"
URL2 = "https://bsky.app/profile/user.bsky.social/post/3k2"


def _stats(success=1):
    return {"total": 1, "success": success, "images": 0, "videos": 0, "texts": success,
            "error_500": [], "error_400": [], "reposts": [], "unknown": [], "failed": []}


def _urls(tmp_config, *urls):
    with open(tmp_config["urls_file"], "w", encoding="utf-8") as f:
        f.write("\n".join(urls))


class TestDownloadMedia:
    def test_run_appele_avec_les_urls_en_attente(self, tmp_config):
        _urls(tmp_config, URL, URL2)
        db = Database(tmp_config["db_file"])
        db.add_post(URL)
        db.mark_post_status(URL, "ok")
        db.close()
        with patch("bsmb.run", return_value=_stats()) as run, \
             patch("builtins.input", side_effect=["", "n"]), \
             patch("subprocess.run") as sous_processus:
            assert bsmb.download_media(tmp_config) is True
        run.assert_called_once_with([URL2], tmp_config)
        sous_processus.assert_not_called()

    def test_force_traite_toutes_les_urls(self, tmp_config):
        _urls(tmp_config, URL, URL2)
        with patch("bsmb.run", return_value=_stats()) as run, \
             patch("builtins.input", side_effect=["", "n"]):
            bsmb.download_media(tmp_config, force=True)
        assert run.call_args.args[0] == [URL, URL2]

    def test_ouverture_du_dossier_proposee_apres_succes(self, tmp_config):
        _urls(tmp_config, URL)
        with patch("bsmb.run", return_value=_stats()), \
             patch("builtins.input", side_effect=["", "o"]), \
             patch("bsmb.open_download_folder") as ouvrir:
            bsmb.download_media(tmp_config)
        ouvrir.assert_called_once_with(tmp_config)

    def test_pas_de_proposition_sans_succes(self, tmp_config):
        _urls(tmp_config, URL)
        with patch("bsmb.run", return_value=_stats(success=0)), \
             patch("builtins.input", side_effect=[""]), \
             patch("bsmb.open_download_folder") as ouvrir:
            assert bsmb.download_media(tmp_config) is False
        ouvrir.assert_not_called()


class TestDownloadMediaDev:
    def test_run_sans_base(self, tmp_config):
        _urls(tmp_config, URL, URL2)
        with patch("bsmb.run", return_value=_stats()) as run, \
             patch("bsmb.clear_screen"), \
             patch("builtins.input", side_effect=["", "n"]):
            bsmb.download_media_dev(tmp_config)
        run.assert_called_once_with([URL, URL2], tmp_config, no_db=True)
