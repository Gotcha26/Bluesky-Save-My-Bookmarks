"""Galeries d'images (`app.bsky.embed.gallery`, jusqu'à 20 images) : analyse, téléchargement, texte, flux."""

import copy
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from api.post_analyzer import PostAnalyzer, PostType
from core import orchestrator
from core.config import DEFAULT_CONFIG, get_media_dirs, resolve_path
from core.database import Database
from downloaders.archive import write_text
from downloaders.images import download_images
from tests.test_images import _reponse
from tests.test_post_analyzer import FIXTURES, _reponse_fixture

DID = "did:plc:test000000000000000000000"
URL = "https://bsky.app/profile/alice.example.com/post/3ktest000020"
CIDS = [f"bafkreitestgallery{n:041d}" for n in range(1, 6)]
ALTS = ["Page 1 : introduction", "Page 2 : matériaux", "Page 3 : épaisseur", "", "Page 5 : conclusion"]
GETBLOB = "https://bsky.social/xrpc/com.atproto.sync.getBlob?did={did}&cid={cid}"


def _charger(nom):
    return json.loads((FIXTURES / nom).read_text(encoding="utf-8"))


@pytest.fixture
def exiftool():
    with patch("downloaders.images.subprocess.run") as run:
        yield run


class TestAnalyseur:
    def test_galerie_donne_images(self, fake_session):
        fake_session.get.return_value = _reponse_fixture("post_gallery.json")
        post_type, data, _ = PostAnalyzer().analyze(URL)

        assert post_type == PostType.IMAGES
        assert data["gallery"] is True
        assert data["image_count"] == 5
        assert data["images"] == [f"https://cdn.bsky.app/img/feed_fullsize/plain/{c}@jpeg" for c in CIDS]
        assert data["alts"] == ALTS

    def test_record_with_media_galerie(self, fake_session):
        brut = _charger("post_gallery.json")
        media = brut["value"]["embed"]
        brut["value"]["embed"] = {
            "$type": "app.bsky.embed.recordWithMedia",
            "media": media,
            "record": {
                "$type": "app.bsky.embed.record",
                "record": {"uri": f"at://{DID}/app.bsky.feed.post/3ktest000031", "cid": "bafyreitest"},
            },
        }
        reponse = MagicMock(status_code=200)
        reponse.json.return_value = brut
        fake_session.get.return_value = reponse

        post_type, data, _ = PostAnalyzer().analyze(URL)
        assert post_type == PostType.IMAGES
        assert data["gallery"] is True and data["image_count"] == 5
        assert data["is_quote"] is True
        assert data["quote_uri"].endswith("/3ktest000031")

    def test_galerie_vide_reste_inconnue(self, fake_session):
        brut = _charger("post_gallery.json")
        brut["value"]["embed"]["items"] = []
        reponse = MagicMock(status_code=200)
        reponse.json.return_value = brut
        fake_session.get.return_value = reponse
        assert PostAnalyzer().analyze(URL)[0] == PostType.UNKNOWN


def _session_galerie(blobs_indisponibles=()):
    """Session mockée : getPostThread renvoie la fixture ; chaque image a un contenu propre."""
    session = MagicMock()
    record = _charger("post_gallery.json")["value"]

    def get(url, **kwargs):
        if "getPostThread" in url:
            return _reponse(_charger("post_gallery_view.json"))
        if "repo.getRecord" in url:
            return _reponse({"value": record})
        cid = url.rsplit("cid=", 1)[-1].split("@")[0].rsplit("/", 1)[-1]
        if cid in blobs_indisponibles:
            return _reponse(status=404)
        return _reponse(content=b"img-" + cid.encode(), headers={"content-type": "image/jpeg"})

    session.get.side_effect = get
    session.head.return_value = _reponse(headers={"content-type": "image/jpeg"})
    return session


class TestTelechargement:
    def test_cinq_fichiers_cid_et_alt(self, tmp_path, exiftool):
        record = _charger("post_gallery.json")["value"]
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=_session_galerie(), record=record)

        assert [r.filename for r in res] == [
            f"alice.example.com_20260914_3ktest000020_{n:02d}.jpg" for n in range(1, 6)
        ]
        assert [r.cid for r in res] == CIDS
        assert [r.alt for r in res] == [a or None for a in ALTS]
        for r, cid in zip(res, CIDS, strict=True):
            assert r.path.read_bytes() == b"img-" + cid.encode()

    def test_blob_d_origine_utilise(self, tmp_path, exiftool):
        session = _session_galerie()
        download_images(URL, tmp_path, DEFAULT_CONFIG, session=session)  # record lu via getRecord
        urls = [c.args[0] for c in session.get.call_args_list]
        assert GETBLOB.format(did=DID, cid=CIDS[0]) in urls
        assert GETBLOB.format(did=DID, cid=CIDS[4]) in urls

    def test_exif_image_description(self, tmp_path, exiftool):
        download_images(URL, tmp_path, DEFAULT_CONFIG, session=_session_galerie())
        commandes = [c.args[0] for c in exiftool.call_args_list]
        descriptions = [
            next((a for a in cmd if a.startswith("-ImageDescription=")), None) for cmd in commandes
        ]
        assert descriptions == [f"-ImageDescription={a}" if a else None for a in ALTS]

    def test_saut_par_cid(self, tmp_path, exiftool):
        deja = tmp_path / "deja.jpg"
        deja.write_bytes(b"x")
        config = {**DEFAULT_CONFIG, "skip_existing_cid": True}
        res = download_images(
            URL,
            tmp_path / "img",
            config,
            session=_session_galerie(),
            existing_cid=lambda cid: deja if cid == CIDS[1] else None,
        )
        assert [r.skipped for r in res] == [False, True, False, False, False]
        assert res[1].cid == CIDS[1]

    def test_vingt_images_numerotees(self, tmp_path, exiftool):
        vue = _charger("post_gallery_view.json")
        modele = vue["thread"]["post"]["embed"]["items"][0]
        items = []
        for n in range(20):
            item = copy.deepcopy(modele)
            item["fullsize"] = f"https://cdn.bsky.app/img/feed_fullsize/plain/{DID}/bafkreinum{n:02d}"
            items.append(item)
        vue["thread"]["post"]["embed"]["items"] = items
        session = MagicMock()
        session.get.side_effect = lambda url, **kw: (
            _reponse(vue) if "getPostThread" in url else _reponse(content=b"i", headers={})
        )
        session.head.return_value = _reponse(headers={"content-type": "image/jpeg"})
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=session, record={})
        assert len(res) == 20
        assert res[-1].filename.endswith("_20.jpg")

    def test_record_with_media_vue(self, tmp_path, exiftool):
        vue = _charger("post_gallery_view.json")
        post = vue["thread"]["post"]
        post["embed"] = {
            "$type": "app.bsky.embed.recordWithMedia#view",
            "media": post["embed"],
            "record": {"record": {}},
        }
        session = _session_galerie()
        session.get.side_effect = lambda url, **kw: (
            _reponse(vue) if "getPostThread" in url else _reponse(content=b"i", headers={})
        )
        record = _charger("post_gallery.json")["value"]
        record["embed"] = {"$type": "app.bsky.embed.recordWithMedia", "media": record["embed"]}
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=session, record=record)
        assert [r.cid for r in res] == CIDS


class TestTexte:
    def test_cinq_alts_dans_le_txt(self, tmp_path):
        record = _charger("post_gallery.json")["value"]
        texte = write_text(URL, record, tmp_path, DEFAULT_CONFIG)[0].path.read_text(encoding="utf-8")

        assert "[Image 1 : Page 1 : introduction]" in texte
        assert "[Image 2 : Page 2 : matériaux]" in texte
        assert "[Image 3 : Page 3 : épaisseur]" in texte
        assert "[Image 4" not in texte  # alt vide : pas de ligne
        assert "[Image 5 : Page 5 : conclusion]" in texte


class TestFluxComplet:
    def test_post_galerie_de_bout_en_bout(self, tmp_config, fake_session):
        vue = _charger("post_gallery_view.json")["thread"]["post"]

        def routeur(url, params=None, **kwargs):
            if "getPostThread" in url:
                return _reponse({"thread": {"post": vue}})
            if "getBlob" in url:
                return _reponse(content=b"jpeg", headers={"content-type": "image/jpeg"})
            raise AssertionError(f"requête inattendue : {url}")

        fake_session.get.side_effect = routeur
        with patch("downloaders.images.subprocess.run"):
            stats = orchestrator.run([URL], tmp_config, quiet=True, post_views={URL: vue})

        assert stats["success"] == 1 and stats["images"] == 5
        dirs = get_media_dirs(tmp_config)
        assert len(list(Path(dirs["img_dir"]).iterdir())) == 5
        assert sorted(p.suffix for p in Path(dirs["text_dir"]).iterdir()) == [
            ".json",
            ".txt",
        ]
        db = Database(resolve_path(tmp_config, "db_file"))
        try:
            medias = db.conn.execute(
                "SELECT media_type, cid FROM media ORDER BY media_type, filename"
            ).fetchall()
            assert db.conn.execute("SELECT status FROM posts").fetchall() == [("ok",)]
        finally:
            db.close()
        assert sorted(cid for t, cid in medias if t == "image") == sorted(CIDS)
        assert [t for t, _ in medias].count("text") == 1
        assert [t for t, _ in medias].count("sidecar") == 1
