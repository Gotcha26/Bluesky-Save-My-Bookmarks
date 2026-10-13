"""Version unique de BSMB (core/version.py)."""
import re
from pathlib import Path

import pytest

from core.version import __version__

RACINE = Path(__file__).parent.parent


def test_version_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_archive_lit_la_version_unique():
    from downloaders.archive import bsmb_version
    assert bsmb_version() == __version__


def test_pyproject_version_dynamique():
    # Lecture textuelle : tomllib n'existe pas en Python 3.10 (CI)
    texte = (RACINE / "pyproject.toml").read_text(encoding="utf-8")
    assert 'dynamic = ["version"]' in texte
    assert not re.search(r'^version\s*=\s*"', texte, re.MULTILINE)
    assert 'version = {attr = "core.version.__version__"}' in texte


def test_cli_version(capsys):
    from core import cli
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["--version"])
    assert exc.value.code == 0
    assert f"BSMB {__version__}" in capsys.readouterr().out


def test_entete_du_menu_affiche_la_version(capsys, tmp_config):
    import bsmb
    state = {"has_account": False, "stats": {"images": 0, "videos": 0, "posts": 0, "dead": 0},
             "has_urls": False, "url_count": 0, "new_count": 0, "last_sync": "", "advanced_mode": False}
    try:
        bsmb.print_header(tmp_config, state)
    except Exception:
        pass
    assert f"v{__version__}" in capsys.readouterr().out
