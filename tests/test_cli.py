"""Tests de la CLI non interactive (core/cli.py, core/ui.py, bsmb.main)."""
import json
from unittest.mock import patch, MagicMock

import pytest

import bsmb
from core import cli, ui
from core.auth import AuthError

SESSION = {"token": "Bearer x", "refresh_jwt": None, "did": None, "pds_url": "https://pds.example"}


def _sync_ok(**kw):
    base = {"error": None, "expired": False, "online_count": 3, "local_count": 1,
            "new_count": 2, "new_urls": ["u1", "u2"], "dead_count": 0}
    base.update(kw)
    return base


def _stats(**kw):
    base = {"total": 2, "success": 2, "images": 2, "videos": 0, "texts": 0,
            "error_500": [], "error_400": [], "reposts": [], "unknown": [], "failed": []}
    base.update(kw)
    return base


@pytest.fixture
def cfg(tmp_config):
    """Config injectée dans la CLI sans toucher à config.json."""
    with patch("core.cli._preparer_config", return_value=tmp_config), \
         patch("core.cli.save_config"):
        yield tmp_config


@pytest.fixture
def non_interactif(monkeypatch):
    monkeypatch.setattr(ui, "is_interactive", lambda: False)


class TestUi:
    def test_pause_ne_lit_rien_en_non_interactif(self, non_interactif):
        with patch("builtins.input", side_effect=AssertionError("input appelé")):
            ui.pause()

    def test_pause_lit_entree_en_interactif(self):
        with patch("builtins.input", return_value="") as inp:
            ui.pause()
        inp.assert_called_once()

    def test_confirm_renvoie_defaut_en_non_interactif(self, non_interactif):
        with patch("builtins.input", side_effect=AssertionError("input appelé")):
            assert ui.confirm("Q ?", default=True) is True
            assert ui.confirm("Q ?", default=False) is False

    @pytest.mark.parametrize("reponse,attendu", [("", True), ("o", True), ("OUI", True), ("n", False)])
    def test_confirm_interactif(self, reponse, attendu):
        with patch("builtins.input", return_value=reponse):
            assert ui.confirm("Q ?") is attendu

    def test_confirm_defaut_false(self):
        with patch("builtins.input", return_value=""):
            assert ui.confirm("Q ?", default=False) is False

    def test_yes_force_non_interactif(self):
        ui.set_yes(True)
        try:
            assert ui.is_interactive() is False
        finally:
            ui.set_yes(False)

    def test_cli_is_interactive_suit_ui(self, non_interactif):
        assert cli.is_interactive() is False


class TestParser:
    def test_yes_accepte_apres_la_sous_commande(self):
        args = cli.build_parser().parse_args(["run", "--yes"])
        assert args.command == "run" and args.yes is True

    def test_yes_global(self):
        args = cli.build_parser().parse_args(["--yes", "sync"])
        assert args.yes is True and args.command == "sync"

    def test_sans_sous_commande(self):
        assert cli.build_parser().parse_args([]).command is None

    def test_download_force_et_status_json(self):
        p = cli.build_parser()
        assert p.parse_args(["download", "--force"]).force is True
        assert p.parse_args(["status", "--json"]).json is True


class TestStatus:
    def test_json_valide(self, cfg, tmp_db, capsys):
        cfg["bsky_handle"] = "alice.bsky.social"
        cfg["last_sync"] = "2026-10-01T10:00:00"
        with patch("core.cli.has_credentials", return_value=True):
            code = cli.main(["status", "--json"])
        assert code == 0
        data = json.loads(capsys.readouterr().out)
        assert data["account"] == "alice.bsky.social"
        assert data["last_sync"] == "2026-10-01T10:00:00"
        assert data["media"] == {"images": 0, "videos": 0, "texts": 0}
        assert data["download_dir"] == cfg["download_dir"]
        for cle in ("pds_url", "online_count", "local_count", "new_count", "dead_count"):
            assert cle in data

    def test_json_sans_compte(self, cfg, capsys):
        assert cli.main(["status", "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["account"] is None

    def test_texte(self, cfg, capsys):
        assert cli.main(["status"]) == 0
        assert "Compte" in capsys.readouterr().out


class TestSync:
    def test_ok(self, cfg):
        with patch("core.cli.get_session", return_value=SESSION), \
             patch("core.cli.BookmarkSync") as sync_cls:
            sync_cls.return_value.sync.return_value = _sync_ok()
            assert cli.main(["sync", "--yes"]) == 0
        sync_cls.return_value.sync.assert_called_once()
        assert sync_cls.return_value.sync.call_args[0][0] == "Bearer x"

    def test_pas_de_session_code_1(self, cfg):
        with patch("core.cli.get_session", return_value=None):
            assert cli.main(["sync"]) == 1

    def test_auth_error_code_1(self, cfg):
        with patch("core.cli.get_session", side_effect=AuthError("non")):
            assert cli.main(["sync"]) == 1

    def test_token_expire_code_1(self, cfg):
        with patch("core.cli.get_session", return_value=SESSION), \
             patch("core.cli.BookmarkSync") as sync_cls:
            sync_cls.return_value.sync.return_value = _sync_ok(error="expired", expired=True)
            assert cli.main(["sync"]) == 1

    def test_echec_reseau_a_l_authentification_code_2(self, cfg):
        from core.auth import NetworkError
        with patch("core.cli.get_session", side_effect=NetworkError("hors ligne")):
            assert cli.main(["sync"]) == 2

    def test_erreur_reseau_code_2(self, cfg):
        with patch("core.cli.get_session", return_value=SESSION), \
             patch("core.cli.BookmarkSync") as sync_cls:
            sync_cls.return_value.sync.return_value = _sync_ok(error="timeout")
            assert cli.main(["sync"]) == 2


class TestDownload:
    def _urls(self, cfg, urls=("https://bsky.app/profile/a/post/1",)):
        from core.config import resolve_path
        resolve_path(cfg, "urls_file").write_text("\n".join(urls), encoding="utf-8")

    def test_ok_ne_demande_rien(self, cfg, non_interactif):
        self._urls(cfg)
        with patch("core.cli.orchestrator.run", return_value=_stats()) as run, \
             patch("builtins.input", side_effect=AssertionError("input appelé")):
            assert cli.main(["download"]) == 0
        assert run.call_args[0][0] == ["https://bsky.app/profile/a/post/1"]

    def test_post_views_du_cache_passes_a_run(self, cfg, non_interactif):
        from core.bookmarks_cache import save_cache
        url = "https://bsky.app/profile/a/post/1"
        vue = {"uri": "at://did:plc:t/app.bsky.feed.post/1", "record": {}}
        save_cache(cfg["bookmarks_cache"], [{"at_uri": vue["uri"], "url": url, "item_type": "postView",
                                              "post_view": vue}])
        self._urls(cfg, (url,))
        with patch("core.cli.orchestrator.run", return_value=_stats()) as run:
            assert cli.main(["download"]) == 0
        assert run.call_args.kwargs["post_views"][url] == vue

    def test_sans_cache_run_sans_post_views(self, cfg, non_interactif):
        self._urls(cfg)
        with patch("core.cli.orchestrator.run", return_value=_stats()) as run:
            cli.main(["download"])
        assert "post_views" not in run.call_args.kwargs

    def test_echecs_code_3(self, cfg, non_interactif):
        self._urls(cfg)
        with patch("core.cli.orchestrator.run", return_value=_stats(failed=["u"])):
            assert cli.main(["download"]) == 3

    def test_erreurs_500_code_3(self, cfg, non_interactif):
        self._urls(cfg)
        with patch("core.cli.orchestrator.run", return_value=_stats(error_500=["u"])):
            assert cli.main(["download"]) == 3

    def test_force_retraite_tout(self, cfg, tmp_db, non_interactif):
        urls = ["https://bsky.app/profile/a/post/1", "https://bsky.app/profile/a/post/2"]
        self._urls(cfg, urls)
        with patch("core.cli.orchestrator.run", return_value=_stats()) as run:
            assert cli.main(["download", "--force"]) == 0
        assert run.call_args[0][0] == urls

    def test_rien_a_faire(self, cfg, non_interactif):
        with patch("core.cli.orchestrator.run") as run:
            assert cli.main(["download"]) == 0
        run.assert_not_called()


class TestRun:
    def test_enchaine_sync_puis_download(self, cfg):
        ordre = []
        with patch("core.cli.cmd_sync", side_effect=lambda *a, **k: ordre.append("sync") or 0), \
             patch("core.cli.cmd_download", side_effect=lambda *a, **k: ordre.append("dl") or 0):
            assert cli.main(["run", "--yes"]) == 0
        assert ordre == ["sync", "dl"]

    def test_s_arrete_au_premier_code_non_nul(self, cfg):
        with patch("core.cli.cmd_sync", return_value=1), \
             patch("core.cli.cmd_download") as dl:
            assert cli.main(["run", "--yes"]) == 1
        dl.assert_not_called()

    def test_code_du_download_propage(self, cfg):
        with patch("core.cli.cmd_sync", return_value=0), \
             patch("core.cli.cmd_download", return_value=3):
            assert cli.main(["run"]) == 3

    def test_run_bout_en_bout_mocke(self, cfg):
        with patch("core.cli.get_session", return_value=SESSION), \
             patch("core.cli.BookmarkSync") as sync_cls, \
             patch("core.cli.orchestrator.run", return_value=_stats()) as run:
            def fake_sync(token, on_progress=None):
                from core.config import resolve_path
                resolve_path(cfg, "urls_file").write_text("https://bsky.app/profile/a/post/9",
                                                          encoding="utf-8")
                return _sync_ok()
            sync_cls.return_value.sync.side_effect = fake_sync
            assert cli.main(["run", "--yes"]) == 0
        assert run.call_args[0][0] == ["https://bsky.app/profile/a/post/9"]


class TestBsmbMain:
    def test_sans_argument_appelle_le_menu(self, tmp_config):
        with patch("bsmb.load_config", return_value=tmp_config), \
             patch("bsmb.migrate_secret_to_keyring"), patch("bsmb.ensure_dirs"), \
             patch("core.config.cleanup_old_logs"), \
             patch("bsmb.run_menu") as menu, patch("core.cli.main") as cli_main:
            assert bsmb.main([]) == 0
        menu.assert_called_once_with(tmp_config)
        cli_main.assert_not_called()

    def test_sous_commande_deleguee_a_la_cli(self):
        with patch("bsmb.run_menu") as menu, patch("core.cli.main", return_value=3) as cli_main:
            assert bsmb.main(["run", "--yes"]) == 3
        cli_main.assert_called_once_with(["run", "--yes"])
        menu.assert_not_called()


class TestOrchestratorOuverture:
    def _lancer(self, tmp_config, interactif, flag):
        from core import orchestrator
        tmp_config["open_folder_after_download"] = flag
        with patch("core.orchestrator.load_config", return_value=tmp_config), \
             patch("core.orchestrator._run", return_value={"success": 1}), \
             patch("core.orchestrator.ui.is_interactive", return_value=interactif), \
             patch("core.orchestrator.os.startfile", create=True) as sf, \
             patch("core.orchestrator.subprocess.run") as sp, \
             patch("builtins.input", side_effect=AssertionError("input appelé")):
            orchestrator.main(["a", "b", "c", "u"])
        return sf.called or sp.called

    def test_ouvre_si_interactif_et_option_vraie(self, tmp_config):
        assert self._lancer(tmp_config, True, True) is True

    def test_n_ouvre_pas_en_non_interactif(self, tmp_config):
        assert self._lancer(tmp_config, False, True) is False

    def test_n_ouvre_pas_si_option_fausse(self, tmp_config):
        assert self._lancer(tmp_config, True, False) is False
