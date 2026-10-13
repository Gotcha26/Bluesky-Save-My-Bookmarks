"""Tests de downloaders/videos.py : fonctions pures et download_video() (réseau et ffmpeg mockés)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from core.config import DEFAULT_CONFIG
from downloaders import DownloadError, DownloadResult
from downloaders import videos
from downloaders.videos import download_video, extract_video_info, safe_filename_part

URL = "https://bsky.app/profile/user.bsky.social/post/3abc"
DID = "did:plc:abc"
CID = "bafkreividcid"


def _record(embed, text="Ma vidéo", created_at="2026-01-02T10:00:00.000Z"):
    return {
        "uri": f"at://{DID}/app.bsky.feed.post/3abc",
        "value": {"text": text, "createdAt": created_at, "embed": embed},
    }


EMBED_VIDEO = {"$type": "app.bsky.embed.video", "video": {"ref": {"$link": CID}}}


def _session(record=None, erreur_api=None, erreur_blob=None, contenu=b"video!"):
    session = MagicMock()

    def get(url, **kwargs):
        if "getRecord" in url:
            if erreur_api:
                raise erreur_api
            rep = MagicMock()
            rep.json.return_value = record
            return rep
        if erreur_blob:
            raise erreur_blob
        rep = MagicMock()
        rep.status_code = 200
        rep.headers = {"content-type": "video/mp4"}
        rep.iter_content.return_value = [contenu[:3], contenu[3:]]
        return rep

    session.get.side_effect = get
    return session


def _ffmpeg_ok(cmd, **kwargs):
    """Simule ffmpeg : écrit le fichier temporaire de sortie (dernier argument)."""
    Path(cmd[-1]).write_bytes(Path(cmd[3]).read_bytes() + b"+meta")


@pytest.fixture
def ffmpeg():
    with patch("downloaders.videos.subprocess.run", side_effect=_ffmpeg_ok) as run:
        yield run


class TestFonctionsPures:
    def test_safe_filename_part(self):
        assert safe_filename_part('a<b>:c d') == "a_b__c_d"
        assert len(safe_filename_part("x" * 80)) == 50

    def test_extract_video_info(self):
        info, is_repost = extract_video_info(_record(EMBED_VIDEO))
        assert is_repost is False
        assert info == {
            "url": f"https://bsky.social/xrpc/com.atproto.sync.getBlob?did={DID}&cid={CID}",
            "text": "Ma vidéo",
            "created_at": "2026-01-02T10:00:00.000Z",
            "cid": CID,
            "did": DID,
            "mime": "",
            "alt": "",
            "presentation": "",
            "captions": [],
        }

    def test_extract_video_info_post_cite(self):
        embed = {"$type": "app.bsky.embed.record", "record": {"embeds": [EMBED_VIDEO]}}
        info, is_repost = extract_video_info(_record(embed))
        assert is_repost is True
        assert info["cid"] == CID

    def test_extract_video_info_citation_avec_video(self):
        embed = {"$type": "app.bsky.embed.recordWithMedia",
                 "record": {"$type": "app.bsky.embed.record", "record": {"uri": "at://did:plc:x/app.bsky.feed.post/y"}},
                 "media": EMBED_VIDEO}
        info, _ = extract_video_info(_record(embed))
        assert info["cid"] == CID

    def test_extract_video_info_sans_video(self):
        assert extract_video_info(_record({"$type": "app.bsky.embed.images"})) == (None, False)
        assert extract_video_info(None) == (None, False)


class TestDownloadVideo:
    def test_video_ecrite_et_decrite(self, tmp_path, ffmpeg):
        session = _session(_record(EMBED_VIDEO))
        res = download_video(URL, tmp_path / "vid", DEFAULT_CONFIG, session=session)

        assert len(res) == 1
        r = res[0]
        assert isinstance(r, DownloadResult)
        assert r.filename == "user.bsky.social_20260102_3abc_01.mp4"
        assert r.media_type == "video"
        assert r.cid == CID
        assert r.path == tmp_path / "vid" / r.filename
        assert r.path.read_bytes() == b"video!+meta"
        assert r.size == len(b"video!+meta")

    def test_name_prefix_remplace_la_base_du_nom(self, tmp_path, ffmpeg):
        session = _session(_record(EMBED_VIDEO))
        res = download_video(URL, tmp_path, DEFAULT_CONFIG, session=session,
                             name_prefix="citant_20260210_3kq_quote")
        assert [r.filename for r in res] == ["citant_20260210_3kq_quote_01.mp4"]
        assert res[0].path == tmp_path / "citant_20260210_3kq_quote_01.mp4"

    def test_appels_api_inchanges(self, tmp_path, ffmpeg):
        session = _session(_record(EMBED_VIDEO))
        download_video(URL, tmp_path, DEFAULT_CONFIG, session=session)
        premier, second = session.get.call_args_list
        assert premier.args[0] == "https://bsky.social/xrpc/com.atproto.repo.getRecord"
        assert premier.kwargs["params"] == {
            "repo": "user.bsky.social", "collection": "app.bsky.feed.post", "rkey": "3abc"}
        assert second.args[0] == f"https://bsky.social/xrpc/com.atproto.sync.getBlob?did={DID}&cid={CID}"

    def test_metadonnees_ffmpeg_inchangees(self, tmp_path, ffmpeg):
        res = download_video(URL, tmp_path, DEFAULT_CONFIG, session=_session(_record(EMBED_VIDEO)))
        chemin = str(res[0].path)
        assert ffmpeg.call_args.args[0] == [
            "ffmpeg", "-y", "-i", chemin,
            "-metadata", "title=3abc",
            "-metadata", f"comment=Ma vidéo\n\nLien du post : {URL}",
            "-metadata", "creation_time=2026-01-02T10:00:00.000Z",
            "-metadata", "artist=user.bsky.social",
            "-codec", "copy", chemin + ".tmp.mp4",
        ]

    def test_ffmpeg_absent_garde_la_video(self, tmp_path):
        with patch("downloaders.videos.subprocess.run", side_effect=FileNotFoundError):
            res = download_video(URL, tmp_path, DEFAULT_CONFIG, session=_session(_record(EMBED_VIDEO)))
        assert res[0].path.read_bytes() == b"video!"

    def test_sans_video_renvoie_liste_vide(self, tmp_path, ffmpeg):
        res = download_video(URL, tmp_path, DEFAULT_CONFIG, session=_session(_record({})))
        assert res == []

    def test_url_invalide_leve_download_error(self, tmp_path, ffmpeg):
        with pytest.raises(DownloadError, match="URL invalide"):
            download_video("https://bsky.app/x", tmp_path, DEFAULT_CONFIG, session=_session())

    def test_api_en_erreur_leve_download_error(self, tmp_path, ffmpeg):
        session = _session(erreur_api=requests.HTTPError("400 Client Error"))
        with pytest.raises(DownloadError, match="supprimé ou inaccessible"):
            download_video(URL, tmp_path, DEFAULT_CONFIG, session=session)

    def test_telechargement_en_erreur_leve_download_error(self, tmp_path, ffmpeg):
        session = _session(_record(EMBED_VIDEO), erreur_blob=requests.ConnectionError("coupé"))
        with pytest.raises(DownloadError, match="coupé"):
            download_video(URL, tmp_path, DEFAULT_CONFIG, session=session)

    def test_longueur_max_lue_dans_la_config(self, tmp_path, ffmpeg):
        config = {**DEFAULT_CONFIG, "max_filename_len": 20}
        res = download_video(URL, tmp_path, config, session=_session(_record(EMBED_VIDEO)))
        assert len(res[0].filename) == 20
        assert res[0].filename.endswith(".mp4")

    def test_sans_session_utilise_la_session_partagee(self, tmp_path, ffmpeg, fake_session):
        fake_session.get.side_effect = _session(_record(EMBED_VIDEO)).get.side_effect
        assert len(download_video(URL, tmp_path, DEFAULT_CONFIG)) == 1


class TestModeManuel:
    def test_affiche_la_ligne_ok(self, tmp_path, capsys):
        res = [DownloadResult("v.mp4", tmp_path / "v.mp4", "video", 1, CID)]
        with patch("downloaders.videos.download_video", return_value=res):
            assert videos.main([str(tmp_path), URL]) == 0
        assert "[OK] Fichier enregistré : v.mp4" in capsys.readouterr().out

    def test_aucune_video_code_2(self, tmp_path, capsys):
        with patch("downloaders.videos.download_video", return_value=[]):
            assert videos.main([str(tmp_path), URL]) == 2
        assert "Aucune vidéo trouvée" in capsys.readouterr().out

    def test_erreur_code_1(self, tmp_path, capsys):
        with patch("downloaders.videos.download_video", side_effect=DownloadError("URL invalide")):
            assert videos.main([str(tmp_path), URL]) == 1
        assert "[ERR] URL invalide" in capsys.readouterr().out
