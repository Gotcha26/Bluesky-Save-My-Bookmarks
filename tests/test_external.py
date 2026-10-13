"""Tests de download_external() (downloaders/external.py) : requests mocké, fichiers réels (issue #4)."""
from unittest.mock import MagicMock

import pytest
import requests

from core.config import DEFAULT_CONFIG
from downloaders import DownloadError, DownloadResult
from downloaders.external import (
    download_external,
    est_media_direct,
    extension_media_direct,
)

URL = "https://bsky.app/profile/auteur.test/post/3ktest000001"
DID = "did:plc:test000000000000000000000"
CID = "bafkreitest"
BASE = "auteur_test_20260105_3ktest000001"


def _data(uri="https://example.com/article", thumb_cid=CID, title="Titre", description="Desc", **extra):
    return {
        "handle": "auteur.test", "post_id": "3ktest000001", "did": DID,
        "created_at": "2026-01-05T17:24:26.493Z", "text": "Un texte à archiver",
        "embed_type": "app.bsky.embed.external",
        "external": {"uri": uri, "title": title, "description": description, "thumb_cid": thumb_cid},
        **extra,
    }


@pytest.fixture
def dirs(tmp_path):
    return {"img_dir": str(tmp_path / "images"), "vid_dir": str(tmp_path / "videos"),
            "text_dir": str(tmp_path / "texts")}


def _reponse(contenu=b"DONNEES", content_type="image/jpeg", erreur=None):
    resp = MagicMock()
    resp.headers = {"content-type": content_type}
    resp.iter_content.return_value = [contenu[:3], contenu[3:]]
    if erreur:
        resp.raise_for_status.side_effect = erreur
    return resp


def _session(reponses=None, erreur=None):
    """Session dont get() renvoie une réponse par URL (défaut : une réponse JPEG)."""
    session = MagicMock()
    if erreur:
        session.get.side_effect = erreur
    else:
        session.get.side_effect = lambda url, **kw: (reponses or {}).get(url, _reponse())
    return session


class TestNomDuTexteExternal:
    def test_meme_base_que_la_fiche_json_et_auteur_du_data(self, dirs):
        """Le .txt prend sa base de l'URL, comme write_sidecar ; « Auteur: » reste le handle de data."""
        from downloaders.archive import write_sidecar
        url_did = "https://bsky.app/profile/did:plc:abcdefghijklmnopqrstuvwx/post/3ktest000001"
        res = download_external(url_did, _data(thumb_cid=None), dirs, DEFAULT_CONFIG, session=_session())
        fiche = write_sidecar(url_did, {"createdAt": "2026-01-05T17:24:26.493Z"}, None, dirs["text_dir"],
                              DEFAULT_CONFIG)[0]
        assert res[0].path.stem == fiche.path.stem
        assert "Auteur: auteur.test\n" in res[0].path.read_text(encoding="utf-8")


class TestTexteDuRecord:
    def test_le_record_fourni_prime_sur_data(self, dirs):
        record = {"text": "Voir ici", "createdAt": "2026-01-05T17:24:26.493Z", "langs": ["fr"],
                  "facets": [{"index": {"byteStart": 5, "byteEnd": 8},
                              "features": [{"$type": "app.bsky.richtext.facet#link", "uri": "https://x.test"}]}]}
        res = download_external(URL, _data(record=record), dirs, DEFAULT_CONFIG, session=_session())
        contenu = res[0].path.read_text(encoding="utf-8")
        assert "Langue: fr\n" in contenu and "Voir ici (https://x.test)" in contenu


class TestDetectionMediaDirect:
    @pytest.mark.parametrize("uri", [
        "https://media.tenor.com/abc/tenor.gif",
        "https://media.tenor.com/abc/tenor",
        "https://exemple.org/a/b.GIF",
        "https://exemple.org/a/b.mp4?x=1",
        "https://exemple.org/a/b.webp#frag",
    ])
    def test_media_direct(self, uri):
        assert est_media_direct(uri)

    @pytest.mark.parametrize("uri", [
        "https://tenor.com/view/chat-gif-123",
        "https://example.com/article",
        "https://example.com/page.html?f=a.gif",
        "https://example.com/",
        "",
        "ftp://exemple.org/a.gif",
        "https://media.tenor.com.evil.org/a",
    ])
    def test_pas_un_media_direct(self, uri):
        assert not est_media_direct(uri)

    def test_extension(self):
        assert extension_media_direct("https://exemple.org/a.MP4?x=1", "") == ".mp4"
        assert extension_media_direct("https://media.tenor.com/abc/tenor", "image/gif") == ".gif"
        assert extension_media_direct("https://media.tenor.com/abc/tenor", "video/mp4") == ".mp4"
        assert extension_media_direct("https://media.tenor.com/abc/tenor", "image/webp") == ".webp"
        assert extension_media_direct("https://media.tenor.com/abc/tenor", "") == ".gif"


class TestTexte:
    def test_fichier_texte(self, dirs):
        res = download_external(URL, _data(thumb_cid=None), dirs, DEFAULT_CONFIG, session=_session())
        assert len(res) == 1
        r = res[0]
        assert isinstance(r, DownloadResult)
        assert (r.filename, r.media_type) == (f"{BASE}.txt", "text")
        assert r.path.parent.name == "texts"
        contenu = r.path.read_text(encoding="utf-8")
        assert contenu.startswith(f"Post: {URL}\nDate: 2026-01-05T17:24:26.493Z\nAuteur: auteur.test\n")
        assert "\nUn texte à archiver\n" in contenu
        assert "Lien: https://example.com/article\n" in contenu
        assert "Titre: Titre\n" in contenu
        assert "Description: Desc\n" in contenu
        assert r.size == r.path.stat().st_size

    def test_meme_nom_que_save_text(self, dirs):
        from downloaders.text import nom_fichier_texte
        assert nom_fichier_texte("auteur.test", "3ktest000001", "2026-01-05T17:24:26.493Z") == f"{BASE}.txt"

    def test_sans_vignette_ni_media_aucun_appel_reseau(self, dirs):
        session = _session()
        res = download_external(URL, _data(thumb_cid=None), dirs, DEFAULT_CONFIG, session=session)
        assert [r.media_type for r in res] == ["text"]
        session.get.assert_not_called()

    def test_pas_d_embed_exploitable(self, dirs):
        data = _data()
        data["external"] = {}
        assert download_external(URL, data, dirs, DEFAULT_CONFIG, session=_session()) == []

    def test_erreur_ecriture(self, dirs, tmp_path):
        (tmp_path / "texts").write_text("je suis un fichier")
        with pytest.raises(DownloadError):
            download_external(URL, _data(thumb_cid=None), dirs, DEFAULT_CONFIG, session=_session())


class TestVignette:
    def test_vignette_telechargee(self, dirs):
        session = _session()
        res = download_external(URL, _data(), dirs, DEFAULT_CONFIG, session=session)
        thumb = [r for r in res if r.media_type == "image"]
        assert len(thumb) == 1
        assert thumb[0].filename == f"{BASE}_thumb.jpg"
        assert thumb[0].cid == CID
        assert thumb[0].path.parent.name == "images"
        assert thumb[0].path.read_bytes() == b"DONNEES"
        assert thumb[0].size == 7
        appel = session.get.call_args
        assert appel.args[0] == f"https://cdn.bsky.app/img/feed_thumbnail/plain/{DID}/{CID}@jpeg"
        assert appel.kwargs["timeout"] == (10, 120)
        assert not list((thumb[0].path.parent).glob("*.part"))

    def test_sans_did_pas_de_vignette(self, dirs):
        data = _data()
        data["did"] = None
        res = download_external(URL, data, dirs, DEFAULT_CONFIG, session=_session())
        assert [r.media_type for r in res] == ["text"]

    def test_echec_vignette_conserve_le_texte(self, dirs):
        session = _session(erreur=requests.ConnectionError("réseau"))
        res = download_external(URL, _data(), dirs, DEFAULT_CONFIG, session=session)
        assert [r.media_type for r in res] == ["text"]

    def test_echec_ne_laisse_pas_de_part(self, dirs, tmp_path):
        reponse = _reponse(erreur=requests.HTTPError("404"))
        download_external(URL, _data(), dirs, DEFAULT_CONFIG, session=_session({
            f"https://cdn.bsky.app/img/feed_thumbnail/plain/{DID}/{CID}@jpeg": reponse}))
        assert not list(tmp_path.rglob("*.part"))
        assert not list(tmp_path.rglob("*_thumb.jpg"))


class TestMediaDirect:
    def test_gif_tenor_dans_images(self, dirs):
        uri = "https://media.tenor.com/abc/tenor.gif"
        session = _session({uri: _reponse(b"GIF89a-xyz", "image/gif")})
        res = download_external(URL, _data(uri=uri, thumb_cid=None), dirs, DEFAULT_CONFIG, session=session)
        assert [(r.filename, r.media_type) for r in res] == [(f"{BASE}.txt", "text"), (f"{BASE}_01.gif", "image")]
        gif = res[1]
        assert gif.path.parent.name == "images"
        assert gif.path.read_bytes() == b"GIF89a-xyz"
        assert gif.cid is None
        assert session.get.call_args.kwargs["timeout"] == (10, 120)

    def test_mp4_dans_videos(self, dirs):
        uri = "https://exemple.org/clip.mp4?token=1"
        session = _session({uri: _reponse(b"MP4DATA", "video/mp4")})
        res = download_external(URL, _data(uri=uri, thumb_cid=None), dirs, DEFAULT_CONFIG, session=session)
        assert res[1].filename == f"{BASE}_01.mp4"
        assert res[1].media_type == "video"
        assert res[1].path.parent.name == "videos"

    def test_webp_dans_images(self, dirs):
        uri = "https://exemple.org/a.webp"
        res = download_external(URL, _data(uri=uri, thumb_cid=None), dirs, DEFAULT_CONFIG, session=_session())
        assert res[1].filename == f"{BASE}_01.webp"
        assert res[1].media_type == "image"

    def test_tenor_sans_extension_utilise_le_content_type(self, dirs):
        uri = "https://media.tenor.com/abc/tenor"
        session = _session({uri: _reponse(b"MP4DATA", "video/mp4")})
        res = download_external(URL, _data(uri=uri, thumb_cid=None), dirs, DEFAULT_CONFIG, session=session)
        assert res[1].filename == f"{BASE}_01.mp4"
        assert res[1].media_type == "video"

    def test_page_tenor_html_vignette_seulement(self, dirs):
        session = _session()
        res = download_external(URL, _data(uri="https://tenor.com/view/chat-gif-123"), dirs,
                                DEFAULT_CONFIG, session=session)
        assert [r.media_type for r in res] == ["text", "image"]
        assert session.get.call_count == 1  # la vignette seule

    def test_lien_tiers_non_telecharge(self, dirs):
        session = _session()
        res = download_external(URL, _data(uri="https://x.com/u/status/1", thumb_cid=None), dirs,
                                DEFAULT_CONFIG, session=session)
        assert [r.media_type for r in res] == ["text"]
        session.get.assert_not_called()

    def test_echec_media_conserve_texte_et_vignette(self, dirs):
        uri = "https://media.tenor.com/abc/tenor.gif"
        session = _session({uri: _reponse(erreur=requests.HTTPError("404"))})
        res = download_external(URL, _data(uri=uri), dirs, DEFAULT_CONFIG, session=session)
        assert [r.media_type for r in res] == ["text", "image"]
        assert res[1].filename.endswith("_thumb.jpg")

    def test_session_par_defaut_est_la_session_partagee(self, dirs, fake_session):
        fake_session.get.return_value = _reponse()
        res = download_external(URL, _data(), dirs, DEFAULT_CONFIG)
        assert len(res) == 2
        fake_session.get.assert_called_once()
