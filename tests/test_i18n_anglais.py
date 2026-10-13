"""Parcours de l'interface en anglais : aucune traduction ne doit casser un `.format()` ni laisser
du français dans les écrans principaux (issue #17)."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

import bsmb
from core import colors, i18n, orchestrator, ui
from downloaders import DownloadResult, lignes_console

ACCENTS = "àâçéèêëîïôùûüÀÉÈÊÔÙ"


def _stats_db(**kw):
    base = {"images": 2, "videos": 1, "texts": 3, "posts": 5, "dead": 0}
    return {**base, **kw}


def _state(**kw):
    base = {
        "stats": _stats_db(),
        "has_urls": True,
        "url_count": 10,
        "new_count": 3,
        "has_account": True,
        "last_sync": "",
        "advanced_mode": False,
    }
    return {**base, **kw}


@pytest.fixture(autouse=True)
def _anglais():
    i18n.init("en")
    yield
    i18n.init("fr")


def test_format_last_sync_en():
    maintenant = datetime.now()
    assert bsmb.format_last_sync((maintenant - timedelta(seconds=5)).isoformat()) == "just now"
    assert bsmb.format_last_sync((maintenant - timedelta(minutes=5)).isoformat()) == "5 min ago"
    assert bsmb.format_last_sync((maintenant - timedelta(hours=3)).isoformat()) == "3h ago"
    assert bsmb.format_last_sync((maintenant - timedelta(days=1, hours=1)).isoformat()) == "1 day ago"
    assert bsmb.format_last_sync((maintenant - timedelta(days=4)).isoformat()) == "4 days ago"


def test_format_size_en():
    assert bsmb.format_size(10) == "10.0 B"
    assert bsmb.format_size(5 * 1024**2) == "5.0 MB"
    assert orchestrator.format_size(3 * 1024**3) == "3.00 GB"


def test_marqueurs_colors_en():
    assert "[ERROR]" in colors.Colors(force_color=False).error("x")
    assert "[WARNING]" in colors.Colors(force_color=False).warning("x")
    assert "[OK]" in colors.Colors(force_color=False).success("x")


@pytest.mark.parametrize(
    "state",
    [
        _state(has_account=False),
        _state(),
        _state(new_count=0),
        _state(new_count=0, has_urls=False),
    ],
)
def test_menu_principal_sans_francais(state, capsys):
    bsmb.show_main_menu(state)
    sortie = capsys.readouterr().out
    assert "My account" in sortie
    assert not any(a in sortie for a in ACCENTS), sortie


def test_en_tete_en(capsys, tmp_config):
    bsmb.print_header(tmp_config, _state(last_sync=datetime.now().isoformat()))
    sortie = capsys.readouterr().out
    assert "Account:" in sortie
    assert "Last synchronization:" in sortie
    assert "4 files" not in sortie  # 2 images + 1 vidéo = 3 fichiers
    assert "3 files" in sortie


def test_menu_compte_et_parametres_en(capsys, tmp_config):
    with patch("bsmb.clear_screen"), patch("builtins.input", side_effect=["0", "0", "0"]):
        bsmb.menu_account(tmp_config, _state())
        bsmb.menu_local_storage(tmp_config, _state(stats=_stats_db(dead=2)))
        bsmb.menu_settings(tmp_config, _state())
    sortie = capsys.readouterr().out
    assert "MY ACCOUNT" in sortie
    assert "LOCAL STORAGE" in sortie
    assert "2 dead links detected" in sortie
    assert "SETTINGS" in sortie
    assert "Enter the number to edit" in sortie


def test_choix_invalide_en(capsys):
    print(bsmb._choix_invalide("zz"))
    assert 'Invalid choice: "zz"' in capsys.readouterr().out


def test_resume_et_rapport_orchestrateur_en(capsys, tmp_path):
    url = "https://bsky.app/profile/alice.bsky.social/post/3abc"
    assert "2 images, 1 video" in orchestrator._format_job_summary(1, 5, url, "success", 2, 1, 0)
    assert "post deleted (400)" in orchestrator._format_job_summary(1, 5, url, "error_400", 0, 0, 0)
    assert "failed" in orchestrator._format_job_summary(1, 5, url, "failed", 0, 0, 0)

    stats = {
        "total": 4,
        "success": 3,
        "images": 2,
        "videos": 1,
        "texts": 3,
        "sidecars": 3,
        "error_500": ["u1"],
        "error_429": ["u2"],
        "error_400": ["u3"],
        "quotes_unresolved": ["u4"],
        "unknown": ["u5"],
        "failed": ["u6"],
    }
    orchestrator.print_report(stats, 75, 4096, True, tmp_path / "x.log", 4, [("a.txt", "1 failures")])
    sortie = capsys.readouterr().out
    for attendu in ("DOWNLOAD REPORT", "RESULTS", "PROBLEMS", "METRICS", "GENERATED FILES", "Detailed log"):
        assert attendu in sortie
    assert not any(a in sortie for a in ACCENTS), sortie


def test_lignes_console_en():
    res = [
        DownloadResult("a.jpg", Path("a.jpg"), "image", 1),
        DownloadResult("b.mp4", Path("b.mp4"), "video", 1),
        DownloadResult("c.jpg", Path("c.jpg"), "image", 0, cid="bafk", skipped=True),
    ]
    lignes = lignes_console(res)
    assert lignes[0] == "   [DL] Downloaded -> a.jpg"
    assert lignes[1] == "   [OK] File saved: b.mp4"
    assert lignes[2] == "   [SKIP] bafk already present: c.jpg"


def test_confirm_en(monkeypatch):
    invites = []
    monkeypatch.setattr("builtins.input", lambda p: invites.append(p) or "yes")
    assert ui.confirm("Go?", default=True) is True
    assert "[Y/n]" in invites[0]
    assert ui.confirm("Go?", default=False) is True
    assert "[y/N]" in invites[1]
    ui.pause()
    assert "Press Enter..." in invites[2]
