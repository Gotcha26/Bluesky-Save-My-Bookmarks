"""Vraie fonction core.ui.is_interactive (la fixture autouse de conftest la remplace)."""

import pytest

from core import ui
from tests.conftest import IS_INTERACTIVE_REEL


class _Stdin:
    def __init__(self, tty=True, erreur=None):
        self._tty = tty
        self._erreur = erreur

    def isatty(self):
        if self._erreur:
            raise self._erreur
        return self._tty


@pytest.fixture(autouse=True)
def _reset_yes():
    ui.set_yes(False)
    yield
    ui.set_yes(False)


def test_tty_sans_yes(monkeypatch):
    monkeypatch.setattr("sys.stdin", _Stdin(True))
    assert IS_INTERACTIVE_REEL() is True


def test_tty_avec_yes(monkeypatch):
    monkeypatch.setattr("sys.stdin", _Stdin(True))
    ui.set_yes(True)
    assert IS_INTERACTIVE_REEL() is False


def test_non_tty(monkeypatch):
    monkeypatch.setattr("sys.stdin", _Stdin(False))
    assert IS_INTERACTIVE_REEL() is False


def test_stdin_none(monkeypatch):
    monkeypatch.setattr("sys.stdin", None)
    assert IS_INTERACTIVE_REEL() is False


@pytest.mark.parametrize("erreur", [ValueError("closed"), OSError("bad")])
def test_isatty_qui_leve(monkeypatch, erreur):
    monkeypatch.setattr("sys.stdin", _Stdin(erreur=erreur))
    assert IS_INTERACTIVE_REEL() is False
