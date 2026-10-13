"""Tests de bsmb.py : le téléchargement appelle orchestrator.run() directement (issue #10)."""
from pathlib import Path
from unittest.mock import patch

import bsmb
from core.database import Database

URL = "https://bsky.app/profile/user.bsky.social/post/3k1"
URL2 = "https://bsky.app/profile/user.bsky.social/post/3k2"


def _stats(success=1):
    return {"total": 1, "success": success, "images": 0, "videos": 0, "texts": success,
            "error_500": [], "error_400": [], "quotes_unresolved": [], "reposts": [],
            "unknown": [], "failed": []}


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


# ─── Identifiants et déconnexion (issue #12) ─────────────────

class _FauxKeyring:
    def __init__(self):
        self.store = {}

    def set_password(self, service, user, pwd):
        self.store[(service, user)] = pwd

    def get_password(self, service, user):
        return self.store.get((service, user))

    def delete_password(self, service, user):
        self.store.pop((service, user), None)


def _session():
    return {"token": "Bearer x", "refresh_jwt": None, "did": "did:plc:x", "pds_url": "https://pds.example"}


class TestConfigureCredentials:
    def _run(self, config, handle="user.bsky.social", pwd="abcd-efgh-ijkl-mnop"):
        with patch("bsmb.clear_screen"), \
             patch("builtins.input", side_effect=[handle, pwd, ""]), \
             patch("core.auth.create_session", return_value=_session()), \
             patch("bsmb.save_config") as save:
            bsmb.configure_credentials(config)
        return save

    def test_secret_en_keyring_pas_dans_config(self, tmp_config, monkeypatch):
        import sys
        kr = _FauxKeyring()
        monkeypatch.setitem(sys.modules, "keyring", kr)
        save = self._run(tmp_config)
        assert kr.store[("bsmb", "user.bsky.social")] == "abcd-efgh-ijkl-mnop"
        assert tmp_config["bsky_app_password"] == ""
        assert tmp_config["bsky_handle"] == "user.bsky.social"
        assert tmp_config["pds_url"] == "https://pds.example"
        save.assert_called()

    def test_avertissement_affiche_une_seule_fois_sans_keyring(self, tmp_config, capsys):
        self._run(tmp_config)
        assert "en clair" in capsys.readouterr().out
        assert tmp_config["bsky_app_password"] == "abcd-efgh-ijkl-mnop"
        assert tmp_config["warned_plaintext_secret"] is True
        self._run(tmp_config)
        assert "AVERTISSEMENT" not in capsys.readouterr().out

    def test_pas_d_avertissement_avec_keyring(self, tmp_config, monkeypatch, capsys):
        import sys
        monkeypatch.setitem(sys.modules, "keyring", _FauxKeyring())
        self._run(tmp_config)
        assert tmp_config.get("warned_plaintext_secret", False) is False
        assert "AVERTISSEMENT" not in capsys.readouterr().out

    def test_le_mot_de_passe_n_est_jamais_affiche(self, tmp_config, capsys):
        self._run(tmp_config)
        assert "abcd-efgh-ijkl-mnop" not in capsys.readouterr().out

    def test_echec_de_connexion_ne_stocke_rien(self, tmp_config):
        from core.auth import AuthError
        with patch("bsmb.clear_screen"), \
             patch("builtins.input", side_effect=["user.bsky.social", "mauvais", ""]), \
             patch("core.auth.create_session", side_effect=AuthError("non")), \
             patch("bsmb.save_config") as save:
            bsmb.configure_credentials(tmp_config)
        assert tmp_config["bsky_app_password"] == ""
        save.assert_not_called()


class TestDisconnectAccount:
    def _config(self, tmp_config):
        tmp_config.update(bsky_handle="user.bsky.social", pds_url="https://pds.example",
                          bsky_app_password="en-clair")
        return tmp_config

    def test_confirmation_supprime_secret_handle_et_pds(self, tmp_config, monkeypatch):
        import sys
        kr = _FauxKeyring()
        kr.store[("bsmb", "user.bsky.social")] = "secret"
        monkeypatch.setitem(sys.modules, "keyring", kr)
        config = self._config(tmp_config)
        with patch("builtins.input", side_effect=["o", ""]), patch("bsmb.save_config") as save:
            assert bsmb.disconnect_account(config) is True
        assert kr.store == {}
        assert config["bsky_handle"] == "" and config["pds_url"] == ""
        assert config["bsky_app_password"] == ""
        save.assert_called_once_with(config)

    def test_refus_ne_change_rien(self, tmp_config):
        config = self._config(tmp_config)
        for reponse in ("", "n", "N", "x"):
            with patch("builtins.input", side_effect=[reponse]), patch("bsmb.save_config") as save:
                assert bsmb.disconnect_account(config) is False
            save.assert_not_called()
        assert config["bsky_handle"] == "user.bsky.social"
        assert config["bsky_app_password"] == "en-clair"

    def test_fichiers_telecharges_et_base_intacts(self, tmp_config):
        config = self._config(tmp_config)
        Database(config["db_file"]).close()
        dossier = Path(config["download_dir"])
        dossier.mkdir(parents=True)
        (dossier / "a.txt").write_text("x", encoding="utf-8")
        with patch("builtins.input", side_effect=["o", ""]), patch("bsmb.save_config"):
            bsmb.disconnect_account(config)
        assert (dossier / "a.txt").exists() and Path(config["db_file"]).exists()

    def test_option_d_du_menu_compte(self, tmp_config):
        config = self._config(tmp_config)
        state = {"has_account": True, "last_sync": "", "has_urls": False,
                 "stats": {"posts": 0, "dead": 0}}
        with patch("bsmb.clear_screen"), \
             patch("bsmb.disconnect_account", return_value=True) as disc, \
             patch("bsmb.get_app_state", return_value={**state, "has_account": False}), \
             patch("builtins.input", side_effect=["D", "0"]):
            bsmb.menu_account(config, state)
        disc.assert_called_once_with(config)

    def test_option_d_absente_sans_compte(self, tmp_config, capsys):
        state = {"has_account": False, "last_sync": "", "has_urls": False,
                 "stats": {"posts": 0, "dead": 0}}
        with patch("bsmb.clear_screen"), patch("builtins.input", side_effect=["0"]):
            bsmb.menu_account(tmp_config, state)
        assert "Déconnecter" not in capsys.readouterr().out


class TestGetSessionPermissions:
    def test_chmod_sur_le_fichier_token_existant(self, tmp_config):
        token = Path(tmp_config["token_file"])
        token.write_text("Bearer abc", encoding="utf-8")
        with patch("bsmb.restrict_permissions") as restrict:
            session = bsmb.get_session(tmp_config)
        assert session["token"] == "Bearer abc"
        restrict.assert_called_once_with(token)


class TestMigrationAuDemarrage:
    def test_main_appelle_la_migration_apres_load_config(self, tmp_config):
        ordre = []
        with patch("bsmb.load_config", side_effect=lambda: ordre.append("load") or tmp_config), \
             patch("bsmb.migrate_secret_to_keyring", side_effect=lambda c: ordre.append("migrate")), \
             patch("bsmb.ensure_dirs"), patch("core.config.cleanup_old_logs"), \
             patch("bsmb.clear_screen"), patch("bsmb.get_app_state", return_value={}), \
             patch("bsmb.print_header"), patch("bsmb.show_main_menu"), \
             patch("builtins.input", side_effect=["0"]):
            bsmb.main([])
        assert ordre == ["load", "migrate"]


class TestDisconnectKeyringEnEchec:
    def test_avertissement_si_le_trousseau_n_a_pas_pu_etre_nettoye(self, tmp_config, capsys):
        tmp_config.update(bsky_handle="user.bsky.social")
        with patch("builtins.input", side_effect=["o", ""]), patch("bsmb.save_config"), \
             patch("bsmb.delete_app_password", return_value=False):
            assert bsmb.disconnect_account(tmp_config) is True
        sortie = capsys.readouterr().out
        assert "trousseau n'a pas pu être nettoyé" in sortie
        assert "[OK]" not in sortie and "[ATTENTION]" in sortie

    def test_succes_normal_sans_avertissement(self, tmp_config, capsys):
        tmp_config.update(bsky_handle="user.bsky.social")
        with patch("builtins.input", side_effect=["o", ""]), patch("bsmb.save_config"):
            bsmb.disconnect_account(tmp_config)
        sortie = capsys.readouterr().out
        assert "Compte déconnecté" in sortie
        assert "pas pu être nettoyé" not in sortie


class TestDownloadMediaCache:
    def test_post_views_du_cache_passes_a_run(self, tmp_config):
        from core.bookmarks_cache import save_cache
        at_uri = "at://did:plc:test/app.bsky.feed.post/3k2"
        vue = {"uri": at_uri, "record": {"text": "x"}}
        save_cache(tmp_config["bookmarks_cache"], [
            {"at_uri": at_uri, "url": URL2, "item_type": "postView", "post_view": vue},
            {"at_uri": "at://did:plc:test/app.bsky.feed.post/3k9", "url": "u9",
             "item_type": "notFoundPost", "post_view": None},
        ])
        _urls(tmp_config, URL2)
        with patch("bsmb.run", return_value=_stats()) as run, \
             patch("builtins.input", side_effect=["", "n"]):
            bsmb.download_media(tmp_config)
        assert run.call_args.kwargs["post_views"] == {at_uri: vue, URL2: vue}

    def test_sans_cache_run_inchange(self, tmp_config):
        _urls(tmp_config, URL2)
        with patch("bsmb.run", return_value=_stats()) as run, \
             patch("builtins.input", side_effect=["", "n"]):
            bsmb.download_media(tmp_config)
        run.assert_called_once_with([URL2], tmp_config)
