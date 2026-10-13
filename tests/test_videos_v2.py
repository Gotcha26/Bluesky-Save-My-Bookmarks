"""Tests de downloaders/videos.py (issue #6) : .part, sous-titres, GIF, mimeType, repli HLS, miniature."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from core.config import DEFAULT_CONFIG
from downloaders import DownloadError, lignes_console
from downloaders.videos import download_video

URL = "https://bsky.app/profile/user.bsky.social/post/3abc"
DID = "did:plc:abc"
CID = "bafkreividcid"
CID_VTT = "bafkreivttcid"
PLAYLIST = "https://video.bsky.app/watch/did%3Aplc%3Aabc/bafkreividcid/playlist.m3u8"
THUMB = "https://video.bsky.app/watch/did%3Aplc%3Aabc/bafkreividcid/thumbnail.jpg"


def _embed(**extra):
    return {
        "$type": "app.bsky.embed.video",
        "video": {"$type": "blob", "ref": {"$link": CID}, "mimeType": "video/mp4", "size": 6},
        **extra,
    }


def _value(embed=None, **extra):
    return {
        "text": "Ma vidéo",
        "createdAt": "2026-01-02T10:00:00.000Z",
        "embed": embed if embed is not None else _embed(),
        **extra,
    }


def _record(embed=None):
    return {"uri": f"at://{DID}/app.bsky.feed.post/3abc", "value": _value(embed)}


def _rep(chunks=(b"vid", b"eo!"), status=200, ctype="video/mp4", boom=None):
    rep = MagicMock()
    rep.status_code = status
    rep.headers = {"content-type": ctype} if ctype is not None else {}
    rep.iter_content.side_effect = lambda chunk_size=8192: _chunks(chunks, boom)
    if status >= 400:
        rep.raise_for_status.side_effect = requests.HTTPError(f"{status} Error")
    return rep


def _chunks(chunks, boom):
    yield from chunks
    if boom:
        raise boom


def _session(record=None, blobs=None, thumb=None):
    """blobs : {cid: réponse | exception}. Le reste (getRecord) renvoie `record`."""
    blobs = {CID: _rep(), **(blobs or {})}
    session = MagicMock()

    def get(url, **kwargs):
        if "getRecord" in url:
            rep = MagicMock()
            rep.json.return_value = record
            return rep
        if "getBlob" in url:
            res = blobs[url.split("cid=")[1]]
            if isinstance(res, Exception):
                raise res
            return res
        if url == THUMB:
            return thumb if thumb is not None else _rep((b"jpg",), ctype="image/jpeg")
        raise AssertionError(f"URL inattendue : {url}")

    session.get.side_effect = get
    return session


def _fake_run(cmd, **kwargs):
    """ffmpeg simulé : métadonnées = copie vers le dernier argument ; HLS = écrit b'hls'."""
    if "-metadata" in cmd:
        Path(cmd[-1]).write_bytes(Path(cmd[3]).read_bytes() + b"+meta")
    else:
        Path(cmd[-1]).write_bytes(b"hls")


@pytest.fixture
def ffmpeg():
    with patch("downloaders.videos.subprocess.run", side_effect=_fake_run) as run:
        yield run


def _dl(tmp_path, session, config=None, **kw):
    return download_video(URL, tmp_path, {**DEFAULT_CONFIG, **(config or {})}, session=session, **kw)


class TestPart:
    def test_part_renomme_seulement_apres_succes(self, tmp_path, ffmpeg):
        vus = []
        base = ffmpeg.side_effect

        def espion(cmd, **kw):  # au moment des métadonnées, le .part a déjà disparu
            vus.append(sorted(p.name for p in tmp_path.iterdir()))
            return base(cmd, **kw)

        ffmpeg.side_effect = espion
        res = _dl(tmp_path, _session(_record()))
        assert vus[0] == ["user.bsky.social_20260102_3abc_01.mp4"]
        assert [p.name for p in tmp_path.iterdir()] == [res[0].filename]

    def test_part_supprime_sur_echec_en_cours_de_route(self, tmp_path, ffmpeg):
        session = _session(_record(), blobs={CID: _rep(boom=requests.ConnectionError("coupé"))})
        with pytest.raises(DownloadError, match="coupé"):
            _dl(tmp_path, session)
        assert list(tmp_path.iterdir()) == []

    def test_timeout_connexion_lecture_et_hote(self, tmp_path, ffmpeg):
        session = _session(_record())
        _dl(tmp_path, session)
        appel = session.get.call_args_list[-1]
        assert appel.args[0] == f"https://bsky.social/xrpc/com.atproto.sync.getBlob?did={DID}&cid={CID}"
        assert appel.kwargs["timeout"] == (10, 300)
        assert appel.kwargs["stream"] is True
        assert appel.kwargs["allow_redirects"] is True

    @pytest.mark.parametrize(
        "rep",
        [
            _rep(chunks=()),
            _rep(chunks=(b"",)),
            _rep(ctype="text/html"),
            _rep(status=404),
        ],
    )
    def test_reponse_invalide_est_un_echec_sans_fichier(self, tmp_path, ffmpeg, rep):
        with pytest.raises(DownloadError):
            _dl(tmp_path, _session(_record(), blobs={CID: rep}))
        assert list(tmp_path.iterdir()) == []

    def test_octet_stream_et_sans_content_type_acceptes(self, tmp_path, ffmpeg):
        for ctype in ("application/octet-stream", None):
            dest = tmp_path / str(ctype).replace("/", "_")
            res = download_video(
                URL, dest, DEFAULT_CONFIG, session=_session(_record(), blobs={CID: _rep(ctype=ctype)})
            )
            assert len(res) == 1


class TestSousTitres:
    def _embed_vtt(self, *langs):
        caps = [
            {
                "lang": lang,
                "file": {
                    "$type": "blob",
                    "ref": {"$link": f"{CID_VTT}{i}"},
                    "mimeType": "text/vtt",
                    "size": 9,
                },
            }
            for i, lang in enumerate(langs)
        ]
        return _embed(captions=caps)

    def test_vtt_ecrit_a_cote_de_la_video(self, tmp_path, ffmpeg):
        blobs = {
            f"{CID_VTT}0": _rep((b"WEBVTT\n",), ctype="text/vtt"),
            f"{CID_VTT}1": _rep((b"WEBVTT\nfr",), ctype="text/vtt; charset=utf-8"),
        }
        res = _dl(tmp_path, _session(_record(self._embed_vtt("en", "fr")), blobs=blobs))
        assert [r.media_type for r in res] == ["video", "subtitle", "subtitle"]
        assert res[1].filename == "user.bsky.social_20260102_3abc_01.en.vtt"
        assert res[1].path.read_bytes() == b"WEBVTT\n"
        assert res[1].cid == f"{CID_VTT}0"
        assert (tmp_path / "user.bsky.social_20260102_3abc_01.fr.vtt").read_bytes() == b"WEBVTT\nfr"
        assert not list(tmp_path.glob("*.part"))

    def test_echec_d_un_sous_titre_n_echoue_pas_la_video(self, tmp_path, ffmpeg, caplog):
        blobs = {
            f"{CID_VTT}0": requests.ConnectionError("vtt coupé"),
            f"{CID_VTT}1": _rep((b"WEBVTT",), ctype="text/vtt"),
        }
        with caplog.at_level("WARNING"):
            res = _dl(tmp_path, _session(_record(self._embed_vtt("en", "fr")), blobs=blobs))
        assert [r.filename.rsplit(".", 2)[-2] for r in res if r.media_type == "subtitle"] == ["fr"]
        assert res[0].media_type == "video"
        assert "vtt coupé" in caplog.text

    def test_ligne_console_du_sous_titre(self, tmp_path, ffmpeg):
        blobs = {f"{CID_VTT}0": _rep((b"WEBVTT",), ctype="text/vtt")}
        res = _dl(tmp_path, _session(_record(self._embed_vtt("en")), blobs=blobs))
        assert lignes_console(res)[1].endswith("_01.en.vtt")


class TestGif:
    GIF = _embed(presentation="gif")

    def test_suffixe_gif(self, tmp_path, ffmpeg):
        res = _dl(tmp_path, _session(_record(self.GIF)))
        assert res[0].filename == "user.bsky.social_20260102_3abc_01_gif.mp4"

    def test_sous_dossier_gifs(self, tmp_path, ffmpeg):
        res = _dl(tmp_path, _session(_record(self.GIF)), config={"gif_subfolder": True})
        assert res[0].filename == "user.bsky.social_20260102_3abc_01.mp4"
        assert res[0].path == tmp_path / "gifs" / res[0].filename
        assert res[0].path.exists()

    def test_video_normale_n_est_pas_un_gif(self, tmp_path, ffmpeg):
        res = _dl(tmp_path, _session(_record(_embed(presentation="default"))), config={"gif_subfolder": True})
        assert res[0].path.parent == tmp_path

    def test_gif_avec_name_prefix(self, tmp_path, ffmpeg):
        res = _dl(tmp_path, _session(_record(self.GIF)), name_prefix="c_20260210_3kq_quote")
        assert res[0].filename == "c_20260210_3kq_quote_01_gif.mp4"

    def test_defauts_de_config(self):
        assert DEFAULT_CONFIG["gif_subfolder"] is False
        assert DEFAULT_CONFIG["download_video_thumbnail"] is False


class TestExtension:
    @pytest.mark.parametrize(
        "mime, ext",
        [
            ("video/mp4", ".mp4"),
            ("video/webm", ".webm"),
            ("video/quicktime", ".mov"),
            ("", ".mp4"),
            ("x/inconnu", ".mp4"),
        ],
    )
    def test_extension_depuis_mimetype(self, tmp_path, ffmpeg, mime, ext):
        embed = _embed()
        embed["video"]["mimeType"] = mime
        res = _dl(tmp_path, _session(_record(embed)))
        assert res[0].filename.endswith(ext)
        assert Path(res[0].path).exists()

    def test_webm_metadonnees_gardent_l_extension(self, tmp_path, ffmpeg):
        embed = _embed()
        embed["video"]["mimeType"] = "video/webm"
        res = _dl(tmp_path, _session(_record(embed)))
        assert ffmpeg.call_args.args[0][-1] == str(res[0].path) + ".tmp.webm"


class TestRecordFourni:
    def test_record_fourni_evite_getrecord(self, tmp_path, ffmpeg):
        session = _session(record=None)
        res = _dl(tmp_path, session, record=_value(), did=DID)
        assert len(res) == 1
        assert not any("getRecord" in c.args[0] for c in session.get.call_args_list)

    def test_record_sans_did_retombe_sur_getrecord(self, tmp_path, ffmpeg):
        session = _session(_record())
        _dl(tmp_path, session, record=_value())
        assert "getRecord" in session.get.call_args_list[0].args[0]

    def test_did_dans_l_url_suffit(self, tmp_path, ffmpeg):
        session = _session(record=None)
        url = f"https://bsky.app/profile/{DID}/post/3abc"
        res = download_video(url, tmp_path, DEFAULT_CONFIG, session=session, record=_value())
        assert len(res) == 1
        assert not any("getRecord" in c.args[0] for c in session.get.call_args_list)

    def test_record_sans_video_renvoie_liste_vide(self, tmp_path, ffmpeg):
        assert _dl(tmp_path, _session(None), record=_value({}), did=DID) == []


class TestAlt:
    def test_description_dans_la_commande_ffmpeg(self, tmp_path, ffmpeg):
        res = _dl(tmp_path, _session(_record(_embed(alt="Un chat qui saute"))))
        cmd = ffmpeg.call_args.args[0]
        assert "description=Un chat qui saute" in cmd
        assert cmd[cmd.index("description=Un chat qui saute") - 1] == "-metadata"
        assert res[0].alt == "Un chat qui saute"

    def test_alt_vide_pas_de_description(self, tmp_path, ffmpeg):
        res = _dl(tmp_path, _session(_record(_embed(alt=""))))
        assert not any(str(a).startswith("description=") for a in ffmpeg.call_args.args[0])
        assert res[0].alt in (None, "")

    def test_alt_dans_un_post_cite_avec_media(self, tmp_path, ffmpeg):
        embed = {
            "$type": "app.bsky.embed.recordWithMedia",
            "record": {"$type": "app.bsky.embed.record", "record": {"uri": "at://x/y/z"}},
            "media": _embed(alt="alt média"),
        }
        assert _dl(tmp_path, _session(_record(embed)))[0].alt == "alt média"


class TestRepliHls:
    VIEW = {"$type": "app.bsky.embed.video#view", "playlist": PLAYLIST, "thumbnail": THUMB}

    def _echec(self):
        return _session(_record(), blobs={CID: requests.ConnectionError("blob purgé")})

    def test_hls_appele_avec_la_bonne_commande(self, tmp_path, ffmpeg):
        res = _dl(tmp_path, self._echec(), view_embed=self.VIEW)
        cible = tmp_path / "user.bsky.social_20260102_3abc_01.mp4"
        premier = ffmpeg.call_args_list[0]
        part = str(cible) + ".part"  # écrit à côté puis renommé (revue finale I6)
        assert premier.args[0] == ["ffmpeg", "-y", "-i", PLAYLIST, "-c", "copy", "-f", "mp4", part]
        assert premier.kwargs["check"] is True
        assert premier.kwargs["timeout"] == 600
        assert res[0].cid == CID
        assert res[0].path == cible and cible.exists()

    def test_hls_si_reponse_invalide(self, tmp_path, ffmpeg):
        session = _session(_record(), blobs={CID: _rep(ctype="text/html")})
        res = _dl(tmp_path, session, view_embed=self.VIEW)
        assert ffmpeg.call_args_list[0].args[0][3] == PLAYLIST
        assert res[0].media_type == "video"

    def test_pas_de_hls_si_blob_ok(self, tmp_path, ffmpeg):
        _dl(tmp_path, _session(_record()), view_embed=self.VIEW)
        assert all(PLAYLIST not in c.args[0] for c in ffmpeg.call_args_list)

    def test_sans_playlist_echec_normal(self, tmp_path, ffmpeg):
        with pytest.raises(DownloadError, match="blob purgé"):
            _dl(tmp_path, self._echec(), view_embed={"thumbnail": THUMB})
        with pytest.raises(DownloadError, match="blob purgé"):
            _dl(tmp_path, self._echec(), view_embed=None)
        ffmpeg.assert_not_called()

    def test_ffmpeg_absent_leve_download_error_explicite(self, tmp_path):
        with patch("downloaders.videos.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(DownloadError, match="ffmpeg"):
                _dl(tmp_path, self._echec(), view_embed=self.VIEW)
        assert list(tmp_path.iterdir()) == []

    def test_ffmpeg_en_echec_leve_download_error_sans_fichier(self, tmp_path):
        def boom(cmd, **kw):
            Path(cmd[-1]).write_bytes(b"tronque")
            raise subprocess.CalledProcessError(1, cmd)

        with patch("downloaders.videos.subprocess.run", side_effect=boom):
            with pytest.raises(DownloadError, match="blob purgé"):
                _dl(tmp_path, self._echec(), view_embed=self.VIEW)
        assert list(tmp_path.iterdir()) == []

    def test_echec_hls_ne_supprime_pas_une_video_deja_archivee(self, tmp_path):
        """Revue finale I6 : ffmpeg écrit dans un .part, jamais sur le fichier final."""
        cible = tmp_path / "user.bsky.social_20260102_3abc_01.mp4"
        cible.write_bytes(b"video archivee")

        def boom(cmd, **kw):
            Path(cmd[-1]).write_bytes(b"tronque")
            raise subprocess.CalledProcessError(1, cmd)

        with patch("downloaders.videos.subprocess.run", side_effect=boom):
            with pytest.raises(DownloadError):
                _dl(tmp_path, self._echec(), view_embed=self.VIEW)
        assert cible.read_bytes() == b"video archivee"
        assert sorted(p.name for p in tmp_path.iterdir()) == [cible.name]

    def test_ffmpeg_timeout_leve_download_error(self, tmp_path):
        with patch("downloaders.videos.subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 600)):
            with pytest.raises(DownloadError):
                _dl(tmp_path, self._echec(), view_embed=self.VIEW)

    def test_hls_webm_sort_en_mp4(self, tmp_path, ffmpeg):
        embed = _embed()
        embed["video"]["mimeType"] = "video/webm"
        session = _session(_record(embed), blobs={CID: requests.ConnectionError("x")})
        res = _dl(tmp_path, session, view_embed=self.VIEW)
        assert res[0].filename.endswith(".mp4")


class TestMiniature:
    VIEW = {"playlist": PLAYLIST, "thumbnail": THUMB}

    def test_desactivee_par_defaut(self, tmp_path, ffmpeg):
        session = _session(_record())
        res = _dl(tmp_path, session, view_embed=self.VIEW)
        assert [r.media_type for r in res] == ["video"]
        assert all(c.args[0] != THUMB for c in session.get.call_args_list)

    def test_telechargee_si_activee(self, tmp_path, ffmpeg):
        res = _dl(
            tmp_path, _session(_record()), config={"download_video_thumbnail": True}, view_embed=self.VIEW
        )
        thumb = res[-1]
        assert thumb.media_type == "image"
        assert thumb.filename == "user.bsky.social_20260102_3abc_01_thumb.jpg"
        assert thumb.path.read_bytes() == b"jpg"
        assert not list(tmp_path.glob("*.part"))

    def test_sans_view_embed_rien_a_telecharger(self, tmp_path, ffmpeg):
        res = _dl(tmp_path, _session(_record()), config={"download_video_thumbnail": True})
        assert [r.media_type for r in res] == ["video"]

    def test_echec_de_la_miniature_n_echoue_pas_la_video(self, tmp_path, ffmpeg, caplog):
        thumb = _rep((b"<html>",), ctype="text/html")
        with caplog.at_level("WARNING"):
            res = _dl(
                tmp_path,
                _session(_record(), thumb=thumb),
                config={"download_video_thumbnail": True},
                view_embed=self.VIEW,
            )
        assert [r.media_type for r in res] == ["video"]
        assert not list(tmp_path.glob("*thumb*"))
        assert "miniature" in caplog.text.lower()
