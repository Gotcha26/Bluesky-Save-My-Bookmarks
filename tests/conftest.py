"""Fixtures partagées pour les tests BSMB."""
import sys
from pathlib import Path

import pytest

# Ajouter la racine du projet au path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def tmp_config(tmp_path):
    """Config temporaire pour les tests."""
    return {
        "download_dir": str(tmp_path / "downloads"),
        "token_file": str(tmp_path / "Token-Bearer.txt"),
        "urls_file": str(tmp_path / "urls.txt"),
        "db_file": str(tmp_path / "test.db"),
        "logs_dir": str(tmp_path / "logs"),
        "max_logs": 5,
        "max_filename_len": 64,
        "min_postid_short": 4,
        "index_digits": 1,
        "bsky_handle": "",
        "bsky_app_password": "",
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
