"""Échec partiel d'un lot d'images (revue finale, I2).

Avec 2 images sur 3 téléchargées, download_images lève DownloadError en portant les
résultats obtenus (`partial`) : l'orchestrateur les enregistre et le post passe `failed`.
Au réessai, le saut par cid ne retélécharge que l'image manquante.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from api.post_analyzer import PostType
from core.config import DEFAULT_CONFIG
from core.orchestrator import process_post
from downloaders import DownloadError
from downloaders.images import download_images
from tests.test_images import _reponse

URL = "https://bsky.app/profile/user.bsky.social/post/3abc"
DID = "did:plc:x"
CIDS = ["bafkreicid1", "bafkreicid2", "bafkreicid3"]


def _cdn(cid):
    return f"https://cdn.bsky.app/img/feed_fullsize/plain/{DID}/{cid}@jpeg"


def _blob(cid):
    return f"https://bsky.social/xrpc/com.atproto.sync.getBlob?did={DID}&cid={cid}"


RECORD = {
    "text": "Bonjour",
    "createdAt": "2026-01-02T10:00:00.000Z",
    "embed": {
        "$type": "app.bsky.embed.images",
        "images": [
            {"alt": "", "image": {"$type": "blob", "ref": {"$link": c}, "mimeType": "image/jpeg", "size": 1}}
            for c in CIDS
        ],
    },
}
THREAD = {
    "thread": {
        "post": {
            "author": {"handle": "user.bsky.social", "did": DID},
            "record": RECORD,
            "embed": {
                "$type": "app.bsky.embed.images#view",
                "images": [{"fullsize": _cdn(c)} for c in CIDS],
            },
        }
    }
}


def _session(en_echec=()):
    """getPostThread renvoie THREAD ; les images dont le cid est dans `en_echec` échouent (blob et CDN)."""
    session = MagicMock()

    def get(url, **kwargs):
        if "getPostThread" in url:
            return _reponse(THREAD)
        if any(c in url for c in en_echec):
            raise requests.ConnectionError("connexion refusée")
        return _reponse(content=b"img", headers={"content-type": "image/jpeg"})

    session.get.side_effect = get
    return session


def _urls_images(session):
    return [c.args[0] for c in session.get.call_args_list if "getPostThread" not in c.args[0]]


@pytest.fixture(autouse=True)
def _exiftool():
    with patch("downloaders.images.subprocess.run"):
        yield


def test_download_images_leve_avec_les_resultats_partiels(tmp_path):
    with pytest.raises(DownloadError) as exc:
        download_images(URL, tmp_path, DEFAULT_CONFIG, session=_session({CIDS[2]}), record=RECORD)
    partiels = exc.value.partial
    assert [r.cid for r in partiels] == CIDS[:2]
    assert all(r.path.is_file() for r in partiels)
    assert "Impossible de télécharger" in str(exc.value)


def test_download_error_sans_partiel_par_defaut():
    assert DownloadError("x").partial == []


def _traiter(db, tmp_path, session):
    analyzer = MagicMock()
    data = {"handle": "user.bsky.social", "did": DID, "at_uri": f"at://{DID}/app.bsky.feed.post/3abc"}
    data["image_count"] = 3
    analyzer.analyze.return_value = (PostType.IMAGES, data, {"full_data": {"value": RECORD}})
    return process_post(
        URL,
        str(tmp_path / "IMG"),
        str(tmp_path / "VID"),
        str(tmp_path / "TXT"),
        db,
        analyzer,
        MagicMock(),
        tmp_path,
        lambda *a, **k: None,
        config=dict(DEFAULT_CONFIG),
        session=session,
    )


def _images_en_base(db):
    return [r[0] for r in db.conn.execute("SELECT cid FROM media WHERE media_type = 'image' ORDER BY id")]


def test_orchestrateur_enregistre_les_partiels_et_marque_failed(tmp_db, tmp_path):
    resultat = _traiter(tmp_db, tmp_path, _session({CIDS[2]}))
    assert resultat[4] == "failed"
    assert _images_en_base(tmp_db) == CIDS[:2]
    statut = tmp_db.conn.execute("SELECT status FROM posts WHERE url = ?", (URL,)).fetchone()[0]
    assert statut == "failed"


def test_reessai_ne_telecharge_que_l_image_manquante(tmp_db, tmp_path):
    _traiter(tmp_db, tmp_path, _session({CIDS[2]}))
    session = _session()
    resultat = _traiter(tmp_db, tmp_path, session)
    assert resultat[4] == "success"
    assert resultat[1] == 1  # une seule image comptée (les deux autres sont sautées)
    assert _urls_images(session) == [_blob(CIDS[2])]
    assert _images_en_base(tmp_db) == CIDS
    statut = tmp_db.conn.execute("SELECT status FROM posts WHERE url = ?", (URL,)).fetchone()[0]
    assert statut == "ok"
