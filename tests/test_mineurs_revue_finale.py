"""Mineurs de la revue finale inclus dans la vague de correction (M2, M5)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from api.post_analyzer import PostType
from core.orchestrator import process_post
from downloaders.images import download_image

URL = "https://bsky.app/profile/user.bsky.social/post/3k1"
PLAYLIST = "https://video.bsky.app/watch/did/cid/playlist.m3u8"
MEDIA_VUE = {"$type": "app.bsky.embed.video#view", "playlist": PLAYLIST, "thumbnail": "https://t/x.jpg"}


@pytest.fixture(autouse=True)
def _dossier_courant_isole(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


class TestCitationAvecVideo:
    """M2 : pour un recordWithMedia#view, le downloader vidéo reçoit l'embed `media`."""

    def _view_embed_transmis(self, tmp_path, view_embed):
        analyzer = MagicMock()
        data = {"handle": "user.bsky.social", "view_embed": view_embed}
        analyzer.analyze.return_value = (PostType.VIDEO, data, {})
        video = MagicMock(return_value=[])
        with patch.multiple("core.orchestrator", download_video=video):
            process_post(
                URL, "IMG", "VID", "TXT", None, analyzer, MagicMock(), tmp_path, lambda *a, **k: None
            )
        return video.call_args.kwargs["view_embed"]

    def test_record_with_media_passe_le_media(self, tmp_path):
        vue = {
            "$type": "app.bsky.embed.recordWithMedia#view",
            "record": {"record": {"uri": "at://x/app.bsky.feed.post/1"}},
            "media": MEDIA_VUE,
        }
        assert self._view_embed_transmis(tmp_path, vue) == MEDIA_VUE

    def test_video_simple_inchangee(self, tmp_path):
        assert self._view_embed_transmis(tmp_path, MEDIA_VUE) == MEDIA_VUE

    def test_sans_vue(self, tmp_path):
        assert self._view_embed_transmis(tmp_path, None) is None


class TestImagePart:
    """M5 : l'image est écrite dans un .part renommé à la fin, comme les vidéos."""

    def _http(self):
        rep = MagicMock()
        rep.content = b"nouvelle"
        rep.headers = {"content-type": "image/jpeg"}
        http = MagicMock()
        http.get.return_value = rep
        return http

    def _telecharger(self, chemin):
        with patch("downloaders.images.subprocess.run"):
            download_image("https://cdn/x@jpeg", chemin, "h", "p", URL, "t", "", http=self._http())

    def test_succes_sans_part_residuel(self, tmp_path):
        chemin = tmp_path / "a.jpg"
        self._telecharger(chemin)
        assert chemin.read_bytes() == b"nouvelle"
        assert [p.name for p in tmp_path.iterdir()] == ["a.jpg"]

    def test_echec_d_ecriture_laisse_le_fichier_existant(self, tmp_path):
        chemin = tmp_path / "a.jpg"
        chemin.write_bytes(b"ancienne")
        with patch("downloaders.images.os.replace", side_effect=OSError("disque plein")):
            with pytest.raises(OSError):
                self._telecharger(chemin)
        assert chemin.read_bytes() == b"ancienne"
        assert [p.name for p in tmp_path.iterdir()] == ["a.jpg"]

    def test_exif_ecrit_sur_le_fichier_final(self, tmp_path):
        chemin = tmp_path / "a.jpg"
        with patch("downloaders.images.subprocess.run") as run:
            download_image("https://cdn/x@jpeg", chemin, "h", "p", URL, "t", "", http=self._http())
        assert run.call_args.args[0][-1] == str(Path(chemin))
