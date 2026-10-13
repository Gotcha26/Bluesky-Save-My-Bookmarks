"""Fixtures partagées pour les tests BSMB."""
import sys
from pathlib import Path

import pytest

# Ajouter la racine du projet au path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core import ui as _ui  # noqa: E402

# Vraie fonction, conservée avant que la fixture autouse ne la remplace
IS_INTERACTIVE_REEL = _ui.is_interactive


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
