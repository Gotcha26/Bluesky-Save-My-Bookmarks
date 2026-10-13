"""Tests de download_images() (downloaders/images.py) : réseau et exiftool mockés."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from core.config import DEFAULT_CONFIG
from downloaders import DownloadError, DownloadResult, lignes_console
from downloaders import images
from downloaders.images import download_images

URL = "https://bsky.app/profile/user.bsky.social/post/3abc"
IMG1 = "https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:x/cid1@jpeg"
IMG2 = "https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:x/cid2.png"


def _reponse(json_data=None, content=b"", status=200, headers=None):
    rep = MagicMock()
    rep.json.return_value = json_data
    rep.content = content
    rep.headers = headers or {}
    if status >= 400:
        rep.raise_for_status.side_effect = requests.HTTPError(f"{status} Client Error: Bad Request for url")
    return rep


def _thread(embed, text="Bonjour", created_at="2026-01-02T10:00:00.000Z"):
    return {"thread": {"post": {
        "author": {"handle": "user.bsky.social"},
        "record": {"text": text, "createdAt": created_at},
        "embed": embed,
    }}}


def _session(thread, contenus=None, echecs=()):
    """Session mockée : getPostThread renvoie `thread`, chaque image son contenu."""
    contenus = contenus or {}
    session = MagicMock()

    def get(url, **kwargs):
        if "getPostThread" in url:
            return thread if isinstance(thread, MagicMock) else _reponse(thread)
        if url in echecs:
            raise requests.ConnectionError("connexion refusée")
        return _reponse(content=contenus.get(url, b"img"))

    session.get.side_effect = get
    session.head.return_value = _reponse(headers={"content-type": "image/jpeg"})
    return session


EMBED_2_IMAGES = {"$type": "app.bsky.embed.images#view",
                  "images": [{"fullsize": IMG1}, {"fullsize": IMG2}]}


@pytest.fixture
def exiftool():
    with patch("downloaders.images.subprocess.run") as run:
        yield run


class TestDownloadImages:
    def test_deux_images_ecrites_et_decrites(self, tmp_path, exiftool):
        session = _session(_thread(EMBED_2_IMAGES), {IMG1: b"aaaa", IMG2: b"bb"})
        res = download_images(URL, tmp_path / "img", DEFAULT_CONFIG, session=session)

        assert [r.filename for r in res] == [
            "user.bsky.social_20260102_3abc_1.jpg",
            "user.bsky.social_20260102_3abc_2.png",
        ]
        assert all(isinstance(r, DownloadResult) and r.media_type == "image" for r in res)
        assert [r.size for r in res] == [4, 2]
        assert res[0].path == tmp_path / "img" / res[0].filename
        assert res[0].path.read_bytes() == b"aaaa"
        assert res[0].cid is None

    def test_name_prefix_remplace_la_base_du_nom(self, tmp_path, exiftool):
        session = _session(_thread(EMBED_2_IMAGES))
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=session,
                              name_prefix="citant_20260210_3kq_quote")
        assert [r.filename for r in res] == ["citant_20260210_3kq_quote_1.jpg", "citant_20260210_3kq_quote_2.png"]
        assert all((tmp_path / r.filename).exists() for r in res)

    def test_name_prefix_tronque_a_max_filename_len(self, tmp_path, exiftool):
        session = _session(_thread(EMBED_2_IMAGES))
        res = download_images(URL, tmp_path, {**DEFAULT_CONFIG, "max_filename_len": 20}, session=session,
                              name_prefix="a" * 50 + "_quote")
        assert all(len(r.filename) <= 20 for r in res)
        assert res[0].filename.endswith(".jpg") and res[1].filename.endswith(".png")
        assert len({r.filename for r in res}) == 2

    def test_metadonnees_exif_inchangees(self, tmp_path, exiftool):
        session = _session(_thread(EMBED_2_IMAGES))
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=session)
        cmd = exiftool.call_args_list[0].args[0]
        assert cmd == [
            "exiftool",
            "-Title=3abc",
            f"-XPComment=Bonjour\n\nLien du post : {URL}",
            "-Artist=user.bsky.social",
            "-DateTimeOriginal=2026-01-02T10:00:00.000",
            f"-Copyright={URL}",
            "-overwrite_original",
            str(res[0].path),
        ]

    def test_appel_getpostthread(self, tmp_path, exiftool):
        session = _session(_thread(EMBED_2_IMAGES))
        download_images(URL, tmp_path, DEFAULT_CONFIG, session=session)
        assert session.get.call_args_list[0].args[0] == (
            "https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread"
            "?uri=at://user.bsky.social/app.bsky.feed.post/3abc"
        )

    def test_extension_par_head_si_absente_de_l_url(self, tmp_path, exiftool):
        session = _session(_thread(EMBED_2_IMAGES))
        download_images(URL, tmp_path, DEFAULT_CONFIG, session=session)
        session.head.assert_called_once_with(IMG1, allow_redirects=True, timeout=10)

    def test_record_with_media(self, tmp_path, exiftool):
        embed = {"$type": "app.bsky.embed.recordWithMedia#view",
                 "media": {"$type": "app.bsky.embed.images#view", "images": [{"fullsize": IMG2}]}}
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=_session(_thread(embed)))
        assert len(res) == 1

    def test_images_du_post_cite(self, tmp_path, exiftool):
        embed = {"$type": "app.bsky.embed.record#view",
                 "record": {"embeds": [{"$type": "app.bsky.embed.images#view",
                                        "images": [{"fullsize": IMG2}]}]}}
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=_session(_thread(embed)))
        assert len(res) == 1

    def test_aucune_image_renvoie_liste_vide(self, tmp_path, exiftool):
        res = download_images(URL, tmp_path / "img", DEFAULT_CONFIG, session=_session(_thread({})))
        assert res == []
        assert not (tmp_path / "img").exists()

    def test_url_invalide_renvoie_liste_vide(self, tmp_path, exiftool):
        session = _session(_thread(EMBED_2_IMAGES))
        assert download_images("https://bsky.app/x", tmp_path, DEFAULT_CONFIG, session=session) == []
        session.get.assert_not_called()

    def test_post_supprime_leve_download_error(self, tmp_path, exiftool):
        session = _session(_reponse(status=400))
        with pytest.raises(DownloadError, match="supprimé"):
            download_images(URL, tmp_path, DEFAULT_CONFIG, session=session)

    def test_toutes_les_images_en_echec_leve_download_error(self, tmp_path, exiftool):
        session = _session(_thread(EMBED_2_IMAGES), echecs=(IMG1, IMG2))
        with pytest.raises(DownloadError, match="Impossible de télécharger"):
            download_images(URL, tmp_path, DEFAULT_CONFIG, session=session)

    def test_echec_partiel_garde_les_reussies(self, tmp_path, exiftool):
        session = _session(_thread(EMBED_2_IMAGES), echecs=(IMG1,))
        res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=session)
        assert [r.filename for r in res] == ["user.bsky.social_20260102_3abc_2.png"]

    def test_exiftool_absent_ne_bloque_pas(self, tmp_path):
        session = _session(_thread(EMBED_2_IMAGES))
        with patch("downloaders.images.subprocess.run", side_effect=FileNotFoundError):
            res = download_images(URL, tmp_path, DEFAULT_CONFIG, session=session)
        assert len(res) == 2

    def test_reglages_de_nommage_lus_dans_la_config(self, tmp_path, exiftool):
        config = {**DEFAULT_CONFIG, "max_filename_len": 30, "index_digits": 3}
        res = download_images(URL, tmp_path, config, session=_session(_thread(EMBED_2_IMAGES)))
        assert all(len(r.filename) <= 30 for r in res)
        assert res[0].filename.endswith("_001.jpg")

    def test_sans_session_utilise_requests(self, tmp_path, exiftool):
        session = _session(_thread(EMBED_2_IMAGES))
        with patch("downloaders.images.requests.get", side_effect=session.get.side_effect), \
             patch("downloaders.images.requests.head", return_value=session.head.return_value):
            res = download_images(URL, tmp_path, DEFAULT_CONFIG)
        assert len(res) == 2


class TestModeManuel:
    def test_affiche_les_lignes_dl(self, tmp_path, capsys):
        res = [DownloadResult("a.jpg", tmp_path / "a.jpg", "image", 1)]
        with patch("downloaders.images.download_images", return_value=res) as dl:
            code = images.main([str(tmp_path), URL])
        assert code == 0
        assert dl.call_args.args[:2] == (URL, str(tmp_path))
        assert "[DL] Téléchargé -> a.jpg" in capsys.readouterr().out

    def test_aucune_image_code_2(self, tmp_path, capsys):
        with patch("downloaders.images.download_images", return_value=[]):
            assert images.main([str(tmp_path), URL]) == 2
        assert "Aucune image trouvée" in capsys.readouterr().out

    def test_erreur_code_1(self, tmp_path, capsys):
        with patch("downloaders.images.download_images", side_effect=DownloadError("Post supprimé")):
            assert images.main([str(tmp_path), URL]) == 1
        assert "[ERR] Post supprimé" in capsys.readouterr().out

    def test_fichier_d_urls(self, tmp_path, capsys):
        liste = tmp_path / "urls.txt"
        liste.write_text(f"{URL}\n\n{URL}2\n", encoding="utf-8")
        with patch("downloaders.images.download_images", return_value=[]) as dl:
            images.main([str(tmp_path), str(liste)])
        assert [c.args[0] for c in dl.call_args_list] == [URL, URL + "2"]


def test_lignes_console():
    res = [
        DownloadResult("a.jpg", Path("a.jpg"), "image", 1),
        DownloadResult("v.mp4", Path("v.mp4"), "video", 1),
        DownloadResult("t.txt", Path("t.txt"), "text", 1),
    ]
    assert lignes_console(res) == [
        "   [DL] Téléchargé -> a.jpg",
        "   [OK] Fichier enregistré : v.mp4",
        "   [TXT] t.txt",
    ]
