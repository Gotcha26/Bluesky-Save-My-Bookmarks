"""Choix de la langue : clé `language`, option « Langue » des Paramètres, `--lang` (issue #17)."""

from unittest.mock import patch

import pytest

import bsmb
from core import cli, i18n
from core.config import DEFAULT_CONFIG


def test_config_par_defaut_langue_auto():
    assert DEFAULT_CONFIG["language"] == ""


# ─── Option « Langue » du menu Paramètres ────────────────────


@pytest.mark.parametrize(
    ("saisie", "attendu_config", "attendu_langue"),
    [("1", "fr", "fr"), ("2", "en", "en")],
)
def test_menu_langue_choix_explicite(tmp_config, saisie, attendu_config, attendu_langue):
    with patch("builtins.input", side_effect=[saisie, ""]), patch("bsmb.save_config") as save:
        bsmb._edit_language(tmp_config)
    assert tmp_config["language"] == attendu_config
    assert i18n.current_language() == attendu_langue  # prise en compte immédiate
    save.assert_called_once_with(tmp_config)


def test_menu_langue_auto_utilise_la_locale(tmp_config, monkeypatch):
    tmp_config["language"] = "en"
    monkeypatch.setattr(i18n, "detect_language", lambda: "en")
    with patch("builtins.input", side_effect=["3", ""]), patch("bsmb.save_config"):
        bsmb._edit_language(tmp_config)
    assert tmp_config["language"] == ""
    assert i18n.current_language() == "en"


def test_menu_langue_entree_garde_la_valeur(tmp_config, capsys):
    with patch("builtins.input", side_effect=["", ""]), patch("bsmb.save_config") as save:
        bsmb._edit_language(tmp_config)
    save.assert_not_called()
    assert tmp_config["language"] == "fr"
    assert "Valeur inchangée" in capsys.readouterr().out


def test_menu_langue_choix_invalide(tmp_config, capsys):
    with patch("builtins.input", side_effect=["9", ""]), patch("bsmb.save_config") as save:
        bsmb._edit_language(tmp_config)
    save.assert_not_called()
    assert 'Choix invalide : "9"' in capsys.readouterr().out


def test_menu_langue_message_dans_la_nouvelle_langue(tmp_config, capsys):
    with patch("builtins.input", side_effect=["2", ""]), patch("bsmb.save_config"):
        bsmb._edit_language(tmp_config)
    assert "Language updated: English" in capsys.readouterr().out


def test_parametres_affichent_et_ouvrent_l_option_langue(tmp_config, capsys):
    state = {"stats": {}, "advanced_mode": False}
    with (
        patch("bsmb.clear_screen"),
        patch("builtins.input", side_effect=["L", "2", "", "0"]),
        patch("bsmb.save_config"),
    ):
        bsmb.menu_settings(tmp_config, state)
    sortie = capsys.readouterr().out
    assert "L. Langue" in sortie
    assert "Français" in sortie
    assert tmp_config["language"] == "en"
    assert "L. Language" in sortie  # second affichage du menu, déjà en anglais


# ─── --lang ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("argv", "attendu"),
    [
        (["--lang", "en", "status"], "en"),
        (["status", "--lang=fr"], "fr"),
        (["status"], None),
        (["--lang"], None),
    ],
)
def test_langue_demandee(argv, attendu):
    assert cli.langue_demandee(argv) == attendu


def test_cli_lang_l_emporte_sur_la_config(tmp_config, capsys):
    with patch("core.cli._preparer_config", return_value=tmp_config):
        assert cli.main(["--lang", "en", "status"]) == 0
    sortie = capsys.readouterr().out
    assert "Last synchronization" in sortie
    assert i18n.current_language() == "en"


def test_cli_lang_apres_la_sous_commande(tmp_config, capsys):
    with patch("core.cli._preparer_config", return_value=tmp_config):
        assert cli.main(["status", "--lang", "en"]) == 0
    assert "Last synchronization" in capsys.readouterr().out


def test_cli_langue_de_la_config(tmp_config, capsys):
    tmp_config["language"] = "en"
    with patch("core.cli._preparer_config", return_value=tmp_config):
        assert cli.main(["status"]) == 0
    assert "Last synchronization" in capsys.readouterr().out


def test_cli_sans_option_langue_de_la_config_fr(tmp_config, capsys):
    with patch("core.cli._preparer_config", return_value=tmp_config):
        assert cli.main(["status"]) == 0
    assert "Dernière synchronisation" in capsys.readouterr().out


def test_cli_lang_auto_detecte(tmp_config, capsys, monkeypatch):
    monkeypatch.setattr(i18n, "detect_language", lambda: "en")
    with patch("core.cli._preparer_config", return_value=tmp_config):
        assert cli.main(["--lang", "auto", "status"]) == 0
    assert "Last synchronization" in capsys.readouterr().out


def test_cli_lang_inconnue_est_refusee(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--lang", "de", "status"])
    assert exc.value.code == 2


def test_aide_dans_la_langue_demandee(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--lang", "en", "--help"])
    assert exc.value.code == 0
    sortie = capsys.readouterr().out
    assert "Without a subcommand: interactive menu" in sortie
    assert "--lang" in sortie


def test_bsmb_main_lang_l_emporte_sur_la_config(tmp_config):
    with (
        patch("bsmb.load_config", return_value=tmp_config),
        patch("bsmb.migrate_secret_to_keyring"),
        patch("bsmb.ensure_dirs"),
        patch("core.config.cleanup_old_logs"),
        patch("bsmb.run_menu") as menu,
    ):
        assert bsmb.main(["--lang", "en"]) == 0
    menu.assert_called_once()
    assert i18n.current_language() == "en"


def test_bsmb_main_langue_de_la_config(tmp_config):
    tmp_config["language"] = "en"
    with (
        patch("bsmb.load_config", return_value=tmp_config),
        patch("bsmb.migrate_secret_to_keyring"),
        patch("bsmb.ensure_dirs"),
        patch("core.config.cleanup_old_logs"),
        patch("bsmb.run_menu"),
    ):
        bsmb.main([])
    assert i18n.current_language() == "en"
