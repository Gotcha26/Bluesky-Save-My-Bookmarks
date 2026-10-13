"""Test d'intégration du flux complet (revue finale).

Vraie base SQLite temporaire, vrais modules ; seul le HTTP est simulé par la session
factice. Flux : run_sync -> pending_downloads -> orchestrator.run(post_views) sur trois
bookmarks : une image (archivée), une vidéo (getBlob en erreur 503) et un post supprimé
(notFoundPost).
"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

from core import orchestrator
from core.bookmarks import pending_downloads, run_sync
from core.config import get_media_dirs, resolve_path
from core.database import Database

DID_IMG, DID_VID, DID_MORT = "did:plc:image", "did:plc:video", "did:plc:mort"
CID_IMG, CID_VID = "bafkreiimagecid", "bafkreivideocid"
URI_IMG = f"at://{DID_IMG}/app.bsky.feed.post/3kimg"
URI_VID = f"at://{DID_VID}/app.bsky.feed.post/3kvid"
URI_MORT = f"at://{DID_MORT}/app.bsky.feed.post/3kmort"
URL_IMG = "https://bsky.app/profile/img.bsky.social/post/3kimg"
URL_VID = "https://bsky.app/profile/vid.bsky.social/post/3kvid"
URL_MORT = "https://bsky.app/profile/did:plc:mort/post/3kmort"
CDN_IMG = f"https://cdn.bsky.app/img/feed_fullsize/plain/{DID_IMG}/{CID_IMG}@jpeg"
CREE = "2026-01-02T10:00:00.000Z"

VUE_IMG = {
    "$type": "app.bsky.feed.defs#postView",
    "uri": URI_IMG,
    "author": {"did": DID_IMG, "handle": "img.bsky.social"},
    "record": {
        "$type": "app.bsky.feed.post",
        "text": "Une image",
        "createdAt": CREE,
        "embed": {
            "$type": "app.bsky.embed.images",
            "images": [
                {
                    "alt": "un chat",
                    "image": {
                        "$type": "blob",
                        "ref": {"$link": CID_IMG},
                        "mimeType": "image/jpeg",
                        "size": 4,
                    },
                }
            ],
        },
    },
    "embed": {"$type": "app.bsky.embed.images#view", "images": [{"fullsize": CDN_IMG, "alt": "un chat"}]},
}
VUE_VID = {
    "$type": "app.bsky.feed.defs#postView",
    "uri": URI_VID,
    "author": {"did": DID_VID, "handle": "vid.bsky.social"},
    "record": {
        "$type": "app.bsky.feed.post",
        "text": "Une vidéo",
        "createdAt": CREE,
        "embed": {
            "$type": "app.bsky.embed.video",
            "video": {"$type": "blob", "ref": {"$link": CID_VID}, "mimeType": "video/mp4", "size": 6},
        },
    },
    # Pas de playlist : aucun repli HLS possible, l'erreur serveur est un échec du post
    "embed": {"$type": "app.bsky.embed.video#view", "cid": CID_VID},
}
ITEM_MORT = {"$type": "app.bsky.feed.defs#notFoundPost", "uri": URI_MORT, "notFound": True}


class _Reponse:
    def __init__(self, json_data=None, content=b"", status=200, ctype="application/json"):
        self._json = json_data
        self.content = content
        self.status_code = status
        self.headers = {"content-type": ctype}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Server Error", response=self)

    def iter_content(self, chunk_size=65536):
        yield self.content

    def close(self):
        pass


def _routeur(url, params=None, **kwargs):
    """Serveur Bluesky simulé (lectures GET uniquement)."""
    if url.endswith("/xrpc/app.bsky.bookmark.getBookmarks"):
        return _Reponse(
            {
                "bookmarks": [
                    {"subject": {"uri": URI_IMG}, "createdAt": CREE, "item": VUE_IMG},
                    {"subject": {"uri": URI_VID}, "createdAt": CREE, "item": VUE_VID},
                    {"subject": {"uri": URI_MORT}, "createdAt": CREE, "item": ITEM_MORT},
                ]
            }
        )
    if "app.bsky.feed.getPostThread" in url and "3kimg" in url:
        return _Reponse({"thread": {"post": VUE_IMG}})
    if "com.atproto.sync.getBlob" in url and CID_IMG in url:
        return _Reponse(content=b"jpeg", ctype="image/jpeg")
    if "com.atproto.sync.getBlob" in url and CID_VID in url:
        return _Reponse(status=503, ctype="text/plain")  # panne serveur persistante
    raise AssertionError(f"requête inattendue : {url}")


@pytest.fixture
def env(tmp_config, fake_session):
    fake_session.get.side_effect = _routeur
    with (
        patch("core.bookmarks.save_config"),  # jamais le vrai config.json
        patch("downloaders.images.subprocess.run"),  # exiftool
        patch("downloaders.videos.subprocess.run"),  # ffmpeg
    ):
        db = Database(resolve_path(tmp_config, "db_file"))
        yield tmp_config, db
        db.close()


SESSION = {
    "token": "Bearer jeton",
    "refresh_jwt": None,
    "did": "did:plc:moi",
    "pds_url": "https://pds.example",
}


def _statuts(db):
    return dict(db.conn.execute("SELECT url, status FROM posts").fetchall())


def _vieillir(db, jours=30):
    ancien = (datetime.now() - timedelta(days=jours)).isoformat()
    db.conn.execute("UPDATE posts SET last_check = ?", (ancien,))
    db.conn.commit()


def test_flux_complet(env):
    config, db = env

    # 1. Synchronisation : le supprimé est repéré tout de suite
    resultat = run_sync(config, db, SESSION)
    assert resultat["error"] is None
    assert resultat["online_count"] == 3
    assert resultat["new_count"] == 2
    assert config["pds_url"] == "https://pds.example"
    assert _statuts(db) == {URL_MORT: "deleted"}

    # 2. Posts à télécharger, avec leurs vues
    urls, vues = pending_downloads(config, db)
    assert urls == [URL_IMG, URL_VID]
    assert vues[URL_VID]["uri"] == URI_VID

    # 3. Téléchargement (sa propre connexion à la base, comme en production)
    stats = orchestrator.run(urls, config, quiet=True, post_views=vues)
    assert stats["success"] == 1 and stats["images"] == 1
    assert stats["failed"] == [URL_VID]
    assert _statuts(db) == {URL_IMG: "ok", URL_VID: "failed", URL_MORT: "deleted"}

    # Fichiers écrits : l'image, son texte lisible et sa fiche JSON ; rien pour la vidéo
    dirs = get_media_dirs(config)
    images = [p.name for p in Path(dirs["img_dir"]).iterdir()]
    assert len(images) == 1 and images[0].endswith(".jpg")
    assert (Path(dirs["img_dir"]) / images[0]).read_bytes() == b"jpeg"
    textes = sorted(p.suffix for p in Path(dirs["text_dir"]).iterdir())
    assert textes == [".json", ".txt"]
    assert not Path(dirs["vid_dir"]).exists() or not any(Path(dirs["vid_dir"]).iterdir())
    medias = db.conn.execute(
        "SELECT post_url, media_type, cid FROM media WHERE media_type = 'image'"
    ).fetchall()
    assert medias == [(URL_IMG, "image", CID_IMG)]

    # 4. Juste après : rien à retenter (vérification récente)
    assert pending_downloads(config, db)[0] == []

    # 5. Après retry_after_days : seule la vidéo revient
    _vieillir(db)
    assert pending_downloads(config, db)[0] == [URL_VID]
