"""Fixtures partagées pour les tests BSMB."""
import socket
import sys
from pathlib import Path

import pytest

# Ajouter la racine du projet au path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from unittest.mock import MagicMock  # noqa: E402

from core import http as _http  # noqa: E402
from core import ui as _ui  # noqa: E402

# Vraies fonctions, conservées avant que les fixtures autouse ne les remplacent
IS_INTERACTIVE_REEL = _ui.is_interactive
GET_SESSION_REEL = _http.get_session


@pytest.fixture(autouse=True)
def fake_session(monkeypatch):
    """La suite ne touche jamais au réseau : `core.http.get_session()` renvoie une session
    factice (MagicMock). Les tests règlent `fake_session.get.return_value` (ou `.post`).
    Les modules appellent `bsmb_http.get_session()` à chaque usage, donc ce patch suffit."""
    session = MagicMock(name="session_factice")
    monkeypatch.setattr(_http, "get_session", lambda: session)
    return session


@pytest.fixture(autouse=True)
def _barriere_reseau(monkeypatch):
    """Dernier rempart : toute connexion TCP vers un hôte autre que la boucle locale échoue
    (même si un test contourne `fake_session`). Les tests de core/http.py parlent à 127.0.0.1."""
    reel = socket.create_connection

    def create_connection(address, *args, **kwargs):
        if address[0] not in ("127.0.0.1", "localhost", "::1"):
            raise AssertionError(f"accès réseau réel interdit pendant les tests : {address!r}")
        return reel(address, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", create_connection)


@pytest.fixture
def mock_get(fake_session):
    """Raccourci : `fake_session.get`."""
    return fake_session.get


@pytest.fixture
def mock_post(fake_session):
    """Raccourci : `fake_session.post`."""
    return fake_session.post


@pytest.fixture(autouse=True)
def _sans_keyring_reel(monkeypatch):
    """Les tests ne touchent jamais au trousseau de l'OS : keyring est absent par défaut
    (les tests de core/secret_store.py injectent un module factice)."""
    monkeypatch.setitem(sys.modules, "keyring", None)


@pytest.fixture(autouse=True)
def _terminal_interactif(monkeypatch):
    """Sous pytest l'entrée standard n'est pas un terminal : on simule une session
    interactive par défaut (les tests du menu mockent input()). Les tests du mode
    non interactif surchargent `core.ui.is_interactive`."""
    from core import ui
    ui.set_yes(False)
    monkeypatch.setattr(ui, "is_interactive", lambda: not ui._etat["yes"])


@pytest.fixture
def tmp_config(tmp_path):
    """Config temporaire pour les tests."""
    return {
        "download_dir": str(tmp_path / "downloads"),
        "token_file": str(tmp_path / "Token-Bearer.txt"),
        "urls_file": str(tmp_path / "urls.txt"),
        "bookmarks_cache": str(tmp_path / "bookmarks.json"),
        "db_file": str(tmp_path / "test.db"),
        "logs_dir": str(tmp_path / "logs"),
        "max_logs": 5,
        "max_filename_len": 64,
        "min_postid_short": 4,
        "index_digits": 1,
        "bsky_handle": "",
        "bsky_app_password": "",
        "max_workers": 4,
        "last_sync": "",
        "advanced_mode": False,
    }


@pytest.fixture
def tmp_db(tmp_path):
    """Base de données temporaire."""
    from core.database import Database

    db = Database(str(tmp_path / "test.db"))
    yield db
    db.close()


@pytest.fixture
def sample_post_url():
    """URL de post Bluesky type."""
    return "https://bsky.app/profile/user.bsky.social/post/3abc123def"
