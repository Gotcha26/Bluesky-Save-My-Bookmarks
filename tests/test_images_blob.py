"""Tests du blob original des images (issue #18) : getBlob, repli CDN, saut par cid."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from core.config import DEFAULT_CONFIG
from downloaders import DownloadError, DownloadResult, lignes_console
from downloaders.images import download_images
from tests.test_images import IMG1, IMG2, URL, _reponse, _thread

DID = "did:plc:x"
CID1, CID2 = "bafkreicid1", "bafkreicid2"
BLOB1 = f"https://bsky.social/xrpc/com.atproto.sync.getBlob?did={DID}&cid={CID1}"
BLOB2 = f"https://bsky.social/xrpc/com.atproto.sync.getBlob?did={DID}&cid={CID2}"
GET_RECORD = "https://bsky.social/xrpc/com.atproto.repo.getRecord"


def _img(cid, mime="image/png", alt=""):
    return {"alt": alt, "image": {"$type": "blob", "ref": {"$link": cid}, "mimeType": mime, "size": 1}}


RECORD = {
    "embed": {"$type": "app.bsky.embed.images", "images": [_img(CID1, "image/png"), _img(CID2, "image/jpeg")]}
}
EMBED = {"$type": "app.bsky.embed.images#view", "images": [{"fullsize": IMG1}, {"fullsize": IMG2}]}


def _thread_did(embed):
    t = _thread(embed)
    t["thread"]["post"]["author"]["did"] = DID
    return t


def _session(embed=EMBED, blobs=None, indisponibles=(), erreurs=(), record=None):
    """Session mockée. blobs : url -> contenu ; indisponibles : urls en 404 ; erreurs : urls en exception."""
    blobs = blobs or {}
    session = MagicMock()

    def get(url, **kwargs):
        if "getPostThread" in url:
            return _reponse(_thread_did(embed))
        if url == GET_RECORD:
            return _reponse({"value": record}) if record is not None else _reponse(status=400)
        if url in erreurs:
            raise requests.ConnectionError("connexion refusée")
        if url in indisponibles:
            return _reponse(status=404)
        return _reponse(content=blobs.get(url, b"img"))

    session.get.side_effect = get
    session.head.return_value = _reponse(headers={"content-type": "image/jpeg"})
    return session


def _urls(session):
    return [c.args[0] for c in session.get.call_args_list]


@pytest.fixture(autouse=True)
def _exiftool():
    with patch("downloaders.images.subprocess.run") as run:
        yield run


class TestModeOriginal:
    def test_getblob_extension_mime_sans_head(self, tmp_path):
        session = _session(record=RECORD, blobs={BLOB1: b"png!", BLOB2: b"jpg!"})
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=session, record=RECORD)

        assert [r.filename for r in res] == [
            "user.bsky.social_20260102_3abc_01.png",
            "user.bsky.social_20260102_3abc_02.jpg",
        ]
        assert res[0].path.read_bytes() == b"png!"
        assert [r.cid for r in res] == [CID1, CID2]
        assert BLOB1 in _urls(session) and BLOB2 in _urls(session)
        assert IMG1 not in _urls(session)
        session.head.assert_not_called()

    def test_record_fourni_pas_de_getrecord(self, tmp_path):
        session = _session()
        download_images(URL, tmp_path, DEFAULT_CONFIG, session=session, record=RECORD)
        assert GET_RECORD not in _urls(session)

    def test_getblob_toujours_sur_bsky_social_avec_redirections(self, tmp_path):
        session = _session()
        config = {**DEFAULT_CONFIG, "pds_url": "https://morel.us-east.host.bsky.network"}
        download_images(URL, tmp_path, config, session=session, record=RECORD)
        assert BLOB1 in _urls(session)
        assert not any("morel" in u for u in _urls(session))
        appel = next(c for c in session.get.call_args_list if c.args[0] == BLOB1)
        assert appel.kwargs["allow_redirects"] is True

    def test_blob_200_vide_repli_cdn(self, tmp_path):
        session = _session(blobs={BLOB1: b""})
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=session, record=RECORD)
        assert IMG1 in _urls(session)
        assert res[0].path.read_bytes() == b"img"

    def test_blob_200_text_html_repli_cdn(self, tmp_path):
        session = _session()
        get = session.get.side_effect

        def get_html(url, **kw):
            if url == BLOB1:
                return _reponse(content=b"<html>", headers={"content-type": "text/html"})
            return get(url, **kw)

        session.get.side_effect = get_html
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=session, record=RECORD)
        assert IMG1 in _urls(session)
        assert res[0].path.read_bytes() == b"img"

    def test_blob_et_cdn_invalides_donnent_une_erreur(self, tmp_path):
        session = _session(blobs={BLOB1: b"", IMG1: b""})
        embed = {"$type": "app.bsky.embed.images#view", "images": [{"fullsize": IMG1}]}
        session = _session(embed=embed, blobs={BLOB1: b"", IMG1: b""})
        with pytest.raises(DownloadError):
            download_images(
                URL, tmp_path, DEFAULT_CONFIG, session=session, record={"embed": {"images": [_img(CID1)]}}
            )

    def test_exif_lien_du_post_est_l_url_du_post(self, tmp_path, _exiftool):
        download_images(URL, tmp_path, DEFAULT_CONFIG, session=_session(), record=RECORD)
        cmd = _exiftool.call_args_list[0].args[0]
        assert f"-XPComment=Bonjour\n\nLien du post : {URL}" in cmd
        assert f"-Copyright={URL}" in cmd

    def test_vue_a_2_images_pour_un_record_a_3_apparie_par_cid(self, tmp_path):
        def cdn(cid):
            return f"https://cdn.bsky.app/img/feed_fullsize/plain/{DID}/{cid}@jpeg"

        record = {
            "embed": {
                "images": [
                    _img(CID1, "image/png"),
                    _img("bafkreicid3", "image/webp"),
                    _img(CID2, "image/jpeg"),
                ]
            }
        }
        embed = {
            "$type": "app.bsky.embed.images#view",
            "images": [{"fullsize": cdn(CID1)}, {"fullsize": cdn(CID2)}],
        }
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=_session(embed=embed), record=record)
        assert [r.cid for r in res] == [CID1, CID2]
        assert [r.filename[-4:] for r in res] == [".png", ".jpg"]

    def test_longueurs_differentes_sans_cid_dans_l_url_pas_de_blob(self, tmp_path):
        record = {"embed": {"images": [_img(CID1), _img(CID2), _img("bafkreicid3")]}}
        session = _session()
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=session, record=record)
        assert [r.cid for r in res] == [None, None]
        assert not any("getBlob" in u for u in _urls(session))

    def test_repli_cdn_sur_404_du_blob(self, tmp_path):
        session = _session(indisponibles=(BLOB1,))
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=session, record=RECORD)

        assert IMG1 in _urls(session)
        # repli : extension par l'ancien chemin (HEAD sur l'URL CDN)
        session.head.assert_called_once_with(IMG1, allow_redirects=True, timeout=10)
        assert res[0].filename.endswith("_01.jpg")
        assert res[0].cid == CID1
        # la 2e image n'est pas concernée
        assert res[1].filename.endswith("_02.jpg") and IMG2 not in _urls(session)

    def test_repli_cdn_sur_exception_du_blob(self, tmp_path):
        session = _session(erreurs=(BLOB2,))
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=session, record=RECORD)
        assert len(res) == 2 and IMG2 in _urls(session)

    def test_record_absent_appelle_getrecord(self, tmp_path):
        session = _session(record=RECORD)
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=session)

        appel = next(c for c in session.get.call_args_list if c.args[0] == GET_RECORD)
        assert appel.kwargs["params"] == {
            "repo": "user.bsky.social",
            "collection": "app.bsky.feed.post",
            "rkey": "3abc",
        }
        assert [r.cid for r in res] == [CID1, CID2]
        assert BLOB1 in _urls(session)

    def test_getrecord_en_echec_repli_cdn_sans_cid(self, tmp_path):
        session = _session(record=None)
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=session)
        assert [r.cid for r in res] == [None, None]
        assert IMG1 in _urls(session)

    def test_record_with_media(self, tmp_path):
        embed = {
            "$type": "app.bsky.embed.recordWithMedia#view",
            "media": {"$type": "app.bsky.embed.images#view", "images": [{"fullsize": IMG1}]},
        }
        record = {
            "embed": {
                "$type": "app.bsky.embed.recordWithMedia",
                "media": {"$type": "app.bsky.embed.images", "images": [_img(CID1, "image/webp")]},
            }
        }
        session = _session(embed=embed)
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=session, record=record)
        assert res[0].filename.endswith("_01.webp") and res[0].cid == CID1

    def test_mime_inconnu_extension_jpg(self, tmp_path):
        record = {"embed": {"images": [_img(CID1, "application/x-inconnu")]}}
        embed = {"$type": "app.bsky.embed.images#view", "images": [{"fullsize": IMG1}]}
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=_session(embed=embed), record=record)
        assert res[0].filename.endswith("_01.jpg")

    def test_images_du_post_cite_gardent_le_cdn(self, tmp_path):
        embed = {
            "$type": "app.bsky.embed.record#view",
            "record": {"embeds": [{"$type": "app.bsky.embed.images#view", "images": [{"fullsize": IMG2}]}]},
        }
        session = _session(embed=embed)
        res = download_images(
            URL,
            tmp_path,
            DEFAULT_CONFIG,
            session=session,
            record={"embed": {"$type": "app.bsky.embed.record"}},
        )
        assert len(res) == 1 and res[0].cid is None
        assert IMG2 in _urls(session)
        assert not any("getBlob" in u for u in _urls(session))


class TestModeCdn:
    CONFIG = {**DEFAULT_CONFIG, "image_quality": "cdn"}

    def test_cdn_extension_depuis_le_mime_sans_head(self, tmp_path):
        session = _session()
        res = download_images(URL, tmp_path, self.CONFIG, session=session, record=RECORD)
        assert not any("getBlob" in u for u in _urls(session))
        assert IMG1 in _urls(session)
        assert [r.filename[-4:] for r in res] == [".png", ".jpg"]
        assert [r.cid for r in res] == [CID1, CID2]
        session.head.assert_not_called()

    def test_cdn_mime_inconnu_garde_le_head(self, tmp_path):
        session = _session()
        res = download_images(URL, tmp_path, self.CONFIG, session=session, record=None)
        assert res[0].cid is None
        session.head.assert_called()


class TestSautParCid:
    def _existant(self, tmp_path):
        fichier = tmp_path / "ancien.png"
        fichier.write_bytes(b"12345")
        return fichier

    def test_cid_deja_present_est_saute(self, tmp_path):
        fichier = self._existant(tmp_path)
        session = _session()
        appels = []

        def existing(cid):
            appels.append(cid)
            return str(fichier) if cid == CID1 else None

        res = download_images(
            URL, tmp_path, DEFAULT_CONFIG, session=session, record=RECORD, existing_cid=existing
        )

        assert appels == [CID1, CID2]
        assert res[0].skipped is True
        assert (res[0].filename, res[0].path, res[0].size, res[0].cid) == ("ancien.png", fichier, 5, CID1)
        assert res[1].skipped is False and res[1].cid == CID2
        assert BLOB1 not in _urls(session) and BLOB2 in _urls(session)
        assert fichier.read_bytes() == b"12345"

    def test_fichier_disparu_est_retelecharge(self, tmp_path):
        session = _session()
        res = download_images(
            URL,
            tmp_path,
            DEFAULT_CONFIG,
            session=session,
            record=RECORD,
            existing_cid=lambda cid: str(tmp_path / "disparu.png"),
        )
        assert not any(r.skipped for r in res)
        assert BLOB1 in _urls(session)

    def test_skip_existing_cid_desactive(self, tmp_path):
        fichier = self._existant(tmp_path)
        existing = MagicMock(return_value=str(fichier))
        config = {**DEFAULT_CONFIG, "skip_existing_cid": False}
        res = download_images(URL, tmp_path, config, session=_session(), record=RECORD, existing_cid=existing)
        existing.assert_not_called()
        assert not any(r.skipped for r in res)

    def test_toutes_sautees_pas_d_erreur(self, tmp_path):
        fichier = self._existant(tmp_path)
        session = _session()
        res = download_images(
            URL,
            tmp_path,
            DEFAULT_CONFIG,
            session=session,
            record=RECORD,
            existing_cid=lambda cid: str(fichier),
        )
        assert [r.skipped for r in res] == [True, True]

    def test_ligne_console_skip(self, tmp_path):
        res = [DownloadResult("a.png", Path("a.png"), "image", 1, cid="bafy", skipped=True)]
        assert lignes_console(res) == ["   [SKIP] bafy déjà présent : a.png"]


class TestAlt:
    """Le texte alternatif du record va dans EXIF ImageDescription et dans DownloadResult.alt (issue #7)."""

    RECORD_ALT = {
        "embed": {
            "$type": "app.bsky.embed.images",
            "images": [_img(CID1, "image/png", alt="Un chat noir"), _img(CID2, "image/jpeg")],
        }
    }

    def test_alt_dans_la_commande_exiftool_et_le_resultat(self, tmp_path, _exiftool):
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=_session(), record=self.RECORD_ALT)

        assert [r.alt for r in res] == ["Un chat noir", None]
        cmd = _exiftool.call_args_list[0].args[0]
        assert "-ImageDescription=Un chat noir" in cmd
        assert cmd.index("-ImageDescription=Un chat noir") < cmd.index("-overwrite_original")

    def test_alt_vide_n_ajoute_pas_imagedescription(self, tmp_path, _exiftool):
        download_images(URL, tmp_path, DEFAULT_CONFIG, session=_session(), record=self.RECORD_ALT)
        cmd_sans_alt = _exiftool.call_args_list[1].args[0]
        assert not any(arg.startswith("-ImageDescription") for arg in cmd_sans_alt)

    def test_alt_conserve_sur_le_repli_cdn(self, tmp_path, _exiftool):
        session = _session(indisponibles=(BLOB1, BLOB2))
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=session, record=self.RECORD_ALT)
        assert res[0].alt == "Un chat noir"
        assert "-ImageDescription=Un chat noir" in _exiftool.call_args_list[0].args[0]

    def test_alt_d_une_image_sautee(self, tmp_path):
        fichier = tmp_path / "deja.png"
        fichier.write_bytes(b"x")
        res = download_images(
            URL,
            tmp_path,
            DEFAULT_CONFIG,
            session=_session(),
            record=self.RECORD_ALT,
            existing_cid=lambda cid: str(fichier),
        )
        assert res[0].skipped and res[0].alt == "Un chat noir"


class TestFindMediaByCid:
    def test_retrouve_le_fichier(self, tmp_db):
        tmp_db.add_post(URL, "3abc", "user.bsky.social")
        tmp_db.add_media(URL, "image", "a.png", cid=CID1)
        assert tmp_db.find_media_by_cid(CID1) == "a.png"

    def test_cid_inconnu_ou_vide(self, tmp_db):
        tmp_db.add_post(URL, "3abc", "user.bsky.social")
        tmp_db.add_media(URL, "image", "a.png")
        assert tmp_db.find_media_by_cid("inconnu") is None
        assert tmp_db.find_media_by_cid("") is None
        assert tmp_db.find_media_by_cid(None) is None
