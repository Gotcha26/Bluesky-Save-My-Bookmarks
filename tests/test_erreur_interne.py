"""Une exception hors downloader n'interrompt plus le lot (revue finale, I3)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from api.post_analyzer import PostAnalyzer, PostType
from core import cli
from core.database import Database
from core.orchestrator import run

URL = "https://bsky.app/profile/a.bsky.social/post/3aaa"
URL2 = "https://bsky.app/profile/b.bsky.social/post/3bbb"


def _vue(record, embed=None):
    return {
        "uri": "at://did:plc:b/app.bsky.feed.post/3bbb",
        "author": {"did": "did:plc:b", "handle": "b.bsky.social"},
        "record": record,
        "embed": embed,
    }


class TestClassifyRobusteAuxNull:
    @pytest.mark.parametrize(
        "record",
        [
            {"text": "x", "embed": None},
            {"text": "x", "embed": {"$type": "app.bsky.embed.video", "video": None}},
            {"text": "x", "embed": {"$type": "app.bsky.embed.video", "video": {"ref": None}}},
            {"text": "x", "embed": {"$type": "app.bsky.embed.images", "images": None}},
            {"text": "x", "embed": {"$type": "app.bsky.embed.images", "images": [{"image": None}]}},
            {"text": "x", "embed": {"$type": "app.bsky.embed.external", "external": None}},
            {
                "text": "x",
                "embed": {
                    "$type": "app.bsky.embed.external",
                    "external": {"uri": "https://e.x", "thumb": None},
                },
            },
            {
                "text": "x",
                "embed": {
                    "$type": "app.bsky.embed.external",
                    "external": {"uri": "https://e.x", "thumb": {"ref": None}},
                },
            },
            {"text": "x", "embed": {"$type": "app.bsky.embed.record", "record": None}},
            {
                "text": "x",
                "embed": {"$type": "app.bsky.embed.recordWithMedia", "record": None, "media": None},
            },
            {
                "text": "x",
                "embed": {"$type": "app.bsky.embed.recordWithMedia", "record": {"record": None}, "media": {}},
            },
        ],
    )
    def test_aucune_exception(self, record):
        post_type, _data, _debug = PostAnalyzer(MagicMock()).analyze(URL2, post_view=_vue(record))
        assert isinstance(post_type, PostType)

    def test_embed_null_texte_seul(self):
        post_type, data, _ = PostAnalyzer(MagicMock()).analyze(
            URL2, post_view=_vue({"text": "x", "embed": None})
        )
        assert post_type == PostType.TEXT_ONLY
        assert data["text"] == "x"

    def test_thumb_null_carte_de_lien(self):
        record = {
            "text": "x",
            "embed": {"$type": "app.bsky.embed.external", "external": {"uri": "https://e.x", "thumb": None}},
        }
        post_type, data, _ = PostAnalyzer(MagicMock()).analyze(URL2, post_view=_vue(record))
        assert post_type == PostType.EXTERNAL
        assert data["external"]["thumb_cid"] is None

    def test_record_inattendu_donne_unknown_avec_erreur(self):
        record = {"text": "x", "embed": {"$type": "app.bsky.embed.images", "images": ["pas un dict"]}}
        post_type, _data, debug = PostAnalyzer(MagicMock()).analyze(URL2, post_view=_vue(record))
        assert post_type == PostType.UNKNOWN
        assert "error" in debug

    def test_getrecord_value_null(self, fake_session):
        rep = MagicMock(status_code=200)
        rep.json.return_value = {"uri": "at://did:plc:b/app.bsky.feed.post/3bbb", "value": None}
        fake_session.get.return_value = rep
        post_type, _data, _debug = PostAnalyzer().analyze(URL2)
        assert post_type == PostType.UNKNOWN


class TestLotNonInterrompu:
    def test_analyseur_qui_leve_n_interrompt_pas_le_lot(self, tmp_config, capsys):
        analyzer = MagicMock()

        def analyze(url, **kwargs):
            if url == URL2:
                raise RuntimeError("bogue interne")
            return PostType.TEXT_ONLY, {"handle": "a.bsky.social"}, {}

        analyzer.analyze.side_effect = analyze
        texte = MagicMock(return_value=[])
        with patch.multiple(
            "core.orchestrator",
            PostAnalyzer=MagicMock(return_value=analyzer),
            QuoteResolver=MagicMock(),
            save_text=texte,
        ):
            stats = run([URL, URL2], tmp_config)

        assert URL2 in stats["failed"]
        assert stats["total"] == 2
        logs = Path(tmp_config["logs_dir"])
        (log,) = logs.glob("download_*.log")
        contenu = log.read_text(encoding="utf-8")
        assert "ERREUR INTERNE" in contenu and "RuntimeError: bogue interne" in contenu
        assert "Traceback" in contenu
        (echecs,) = logs.glob("failed_downloads_*.txt")
        assert URL2 in echecs.read_text(encoding="utf-8")
        sortie = capsys.readouterr().out
        assert "[ERR]" in sortie and "erreur interne" in sortie
        assert "RAPPORT DE TÉLÉCHARGEMENT" in sortie

    def test_post_deja_en_base_passe_failed(self, tmp_config):
        db = Database(tmp_config["db_file"])
        db.add_post(URL2)
        db.close()
        analyzer = MagicMock()
        analyzer.analyze.side_effect = RuntimeError("bogue interne")
        with patch.multiple(
            "core.orchestrator", PostAnalyzer=MagicMock(return_value=analyzer), QuoteResolver=MagicMock()
        ):
            stats = run([URL2], tmp_config, quiet=True)
        assert stats["failed"] == [URL2]
        db = Database(tmp_config["db_file"])
        statut = db.conn.execute("SELECT status FROM posts WHERE url = ?", (URL2,)).fetchone()[0]
        db.close()
        assert statut == "failed"


class TestCliErreurInterne:
    def test_exception_donne_le_code_4(self, tmp_config, capsys):
        with (
            patch("core.cli._preparer_config", return_value=tmp_config),
            patch("core.cli.cmd_status", side_effect=RuntimeError("bogue")),
        ):
            code = cli.main(["status"])
        assert code == cli.EXIT_INTERNAL == 4
        assert "bogue" in capsys.readouterr().out
