"""Statut `failed` persistant et retenté (revue finale, I1).

Un post dont le téléchargement échoue est enregistré `failed` en base, puis retenté
automatiquement après `retry_after_days`, comme `error_500`.
"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from api.post_analyzer import PostType
from core.database import STATUTS_A_RETENTER
from core.orchestrator import process_post
from downloaders import DownloadError, DownloadResult

URL = "https://bsky.app/profile/user.bsky.social/post/3kf1"
AT_URI = "at://did:plc:user/app.bsky.feed.post/3kf1"
DATA = {"handle": "user.bsky.social", "at_uri": AT_URI, "did": "did:plc:user", "image_count": 1}


@pytest.fixture(autouse=True)
def _dossier_courant_isole(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _traiter(db, tmp_path, post_type=PostType.VIDEO, debug_info=None, **downloaders):
    mocks = {
        "download_images": MagicMock(return_value=[]),
        "download_video": MagicMock(return_value=[]),
        "save_text": MagicMock(return_value=[]),
    }
    mocks.update(downloaders)
    analyzer = MagicMock()
    analyzer.analyze.return_value = (post_type, dict(DATA), debug_info or {})
    with patch.multiple("core.orchestrator", **mocks):
        return process_post(
            URL,
            "IMG",
            "VID",
            "TXT",
            db,
            analyzer,
            MagicMock(),
            tmp_path,
            lambda *a, **k: None,
            config={"max_filename_len": 64},
        )


def _statut(db):
    return db.conn.execute("SELECT status FROM posts WHERE url = ?", (URL,)).fetchone()[0]


def _vieillir(db, jours=30):
    ancien = (datetime.now() - timedelta(days=jours)).isoformat()
    db.conn.execute("UPDATE posts SET last_check = ? WHERE url = ?", (ancien, URL))
    db.conn.commit()


def test_failed_est_un_statut_a_retenter():
    assert "failed" in STATUTS_A_RETENTER


def test_echec_total_pose_failed_en_base(tmp_db, tmp_path):
    resultat = _traiter(tmp_db, tmp_path, download_video=MagicMock(side_effect=DownloadError("503")))
    assert resultat[4] == "failed"
    assert _statut(tmp_db) == "failed"


def test_echec_partiel_pose_failed_en_base(tmp_db, tmp_path):
    """Contenu propre incomplet (vidéo obtenue, .txt en échec) : média gardé, statut failed."""
    video = MagicMock(return_value=[DownloadResult("v.mp4", Path("v.mp4"), "video", 10, "cidv")])
    texte = MagicMock(side_effect=DownloadError("écriture impossible"))
    debug_info = {"full_data": {"value": {"text": "x", "createdAt": "2026-01-01T00:00:00Z"}}}
    with patch("core.orchestrator.write_text", texte):
        resultat = _traiter(tmp_db, tmp_path, debug_info=debug_info, download_video=video)
    assert resultat[4] == "failed"
    assert _statut(tmp_db) == "failed"
    medias = tmp_db.conn.execute("SELECT filename FROM media WHERE post_url = ?", (URL,)).fetchall()
    assert ("v.mp4",) in medias  # la vidéo obtenue est gardée (avec la fiche JSON)


def test_aucun_media_pose_failed_en_base(tmp_db, tmp_path):
    resultat = _traiter(tmp_db, tmp_path, post_type=PostType.TEXT_ONLY)
    assert resultat[4] == "failed"
    assert _statut(tmp_db) == "failed"


def test_failed_recent_non_retente_puis_retente_apres_vieillissement(tmp_db, tmp_path):
    _traiter(tmp_db, tmp_path, download_video=MagicMock(side_effect=DownloadError("503")))
    ref = {"url": URL, "at_uri": AT_URI}
    assert tmp_db.get_pending_posts([URL], 7) == []
    assert tmp_db.get_pending_refs([ref], 7) == []
    _vieillir(tmp_db)
    assert tmp_db.get_pending_posts([URL], 7) == [URL]
    assert tmp_db.get_pending_refs([ref], 7) == [ref]


def test_retente_avec_succes_repasse_ok(tmp_db, tmp_path):
    _traiter(tmp_db, tmp_path, download_video=MagicMock(side_effect=DownloadError("503")))
    _vieillir(tmp_db)
    video = MagicMock(return_value=[DownloadResult("v.mp4", Path("v.mp4"), "video", 10, "cidv")])
    resultat = _traiter(tmp_db, tmp_path, download_video=video)
    assert resultat[4] == "success"
    assert _statut(tmp_db) == "ok"
    assert tmp_db.get_pending_posts([URL], 7) == []
