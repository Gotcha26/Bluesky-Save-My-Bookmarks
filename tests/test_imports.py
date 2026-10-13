"""Chaque module du projet s'importe sans effet de bord (issue #10).

L'import se fait dans un interpréteur neuf, avec sys.argv vide, une entrée
standard fermée, un dossier courant et un dossier utilisateur temporaires :
aucun input(), aucune sortie console, aucun fichier ni dossier créé.
"""

import os
import subprocess
import sys

import pytest

from core.paths import PROJECT_ROOT

MODULES = [
    "bsmb",
    "core.paths",
    "core.config",
    "core.colors",
    "core.database",
    "core.post_ref",
    "core.auth",
    "core.bookmarks",
    "core.bookmarks_cache",
    "core.cli",
    "core.http",
    "core.orchestrator",
    "core.secret_store",
    "core.ui",
    "core.version",
    "api.export_bookmarks",
    "api.post_analyzer",
    "api.quote_resolver",
    "api.repost_resolver",
    "downloaders",
    "downloaders.archive",
    "downloaders.external",
    "downloaders.images",
    "downloaders.videos",
    "downloaders.text",
]

SCRIPT = (
    "import builtins, importlib, sys\n"
    "sys.argv = ['']\n"
    "def _interdit(*a, **k):\n"
    "    raise AssertionError('input() appelé à l import')\n"
    "builtins.input = _interdit\n"
    "importlib.import_module(sys.argv_module)\n"
)


@pytest.mark.parametrize("module", MODULES)
def test_import_sans_effet_de_bord(module, tmp_path):
    cwd = tmp_path / "cwd"
    home = tmp_path / "home"
    cwd.mkdir()
    home.mkdir()
    env = {
        **os.environ,
        "PYTHONPATH": str(PROJECT_ROOT),
        "PYTHONIOENCODING": "utf-8",
        "HOME": str(home),
        "USERPROFILE": str(home),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    code = SCRIPT.replace("sys.argv_module", repr(module))
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""
    assert list(cwd.iterdir()) == []
    assert list(home.iterdir()) == []


def _modules_du_depot():
    """Noms importables de tous les .py de bsmb.py, core/, api/ et downloaders/."""
    noms = {"bsmb"}
    for dossier in ("core", "api", "downloaders"):
        for fichier in sorted((PROJECT_ROOT / dossier).glob("*.py")):
            noms.add(dossier if fichier.stem == "__init__" else f"{dossier}.{fichier.stem}")
    return noms


def test_modules_listes_couvrent_tout_le_depot():
    """Un nouveau module doit être ajouté à MODULES (et donc vérifié sans effet de bord)."""
    # les paquets core et api n'ont pas de code à l'import : seul downloaders est listé comme paquet
    attendus = _modules_du_depot() - {"core", "api"}
    assert attendus == set(MODULES)
