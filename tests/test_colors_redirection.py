"""Détection des couleurs quand la sortie est redirigée (core/colors.py)."""

import pytest

from core.colors import Colors


class _Sortie:
    def __init__(self, tty):
        self._tty = tty

    def isatty(self):
        return self._tty


@pytest.fixture(autouse=True)
def _env_propre(monkeypatch):
    for var in ("NO_COLOR", "FORCE_COLOR", "WT_SESSION", "ConEmuANSI"):
        monkeypatch.delenv(var, raising=False)


def test_stdout_non_tty_pas_de_couleurs(monkeypatch):
    monkeypatch.setattr("sys.stdout", _Sortie(False))
    assert Colors().RED == ""


def test_wt_session_ne_force_pas_une_sortie_redirigee(monkeypatch):
    monkeypatch.setenv("WT_SESSION", "1")
    monkeypatch.setattr("sys.stdout", _Sortie(False))
    assert Colors().RED == ""


def test_force_color_prioritaire(monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setattr("sys.stdout", _Sortie(False))
    assert Colors().RED != ""


def test_no_color_prioritaire(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setattr("sys.stdout", _Sortie(True))
    assert Colors().RED == ""
