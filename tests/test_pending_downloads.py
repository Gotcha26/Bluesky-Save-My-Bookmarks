"""Téléchargement identifié par AT-URI (revue finale, I4).

`core.bookmarks.pending_downloads` est la source unique des posts à télécharger : avec le
cache des bookmarks, la comparaison se fait par AT-URI (un changement de handle ne
déclenche aucun retéléchargement) ; sans cache, par URL depuis urls.txt.
`core.bookmarks.run_sync` est la synchronisation commune au menu et à la CLI.
"""

from unittest.mock import MagicMock, patch

import pytest

import bsmb
from core import cli
from core.bookmarks import pending_downloads, run_sync
from core.bookmarks_cache import save_cache
from core.config import resolve_path

AT_URI = "at://did:plc:auteur/app.bsky.feed.post/3kpost"
ANCIENNE_URL = "https://bsky.app/profile/old.bsky.social/post/3kpost"
NOUVELLE_URL = "https://bsky.app/profile/new.example/post/3kpost"
AT_URI_NEUF = "at://did:plc:autre/app.bsky.feed.post/3kneuf"
URL_NEUVE = "https://bsky.app/profile/autre.bsky.social/post/3kneuf"
AT_URI_MORT = "at://did:plc:mort/app.bsky.feed.post/3kmort"
URL_MORTE = "https://bsky.app/profile/mort.bsky.social/post/3kmort"


def _entree(at_uri, url, item_type="postView"):
    vue = {"uri": at_uri, "record": {"text": "x"}} if item_type == "postView" else None
    return {"at_uri": at_uri, "url": url, "item_type": item_type, "post_view": vue}


@pytest.fixture
def config(tmp_config):
    """Config isolée : save_config n'écrit jamais le vrai config.json."""
    with patch("core.bookmarks.save_config"), patch("bsmb.save_config"):
        yield tmp_config


@pytest.fixture
def non_interactif(monkeypatch):
    from core import ui

    monkeypatch.setattr(ui, "is_interactive", lambda: False)


@pytest.fixture
def db(config):
    from core.database import Database

    base = Database(resolve_path(config, "db_file"))
    yield base
    base.close()


def _changement_de_handle(config, db, avec_neuf=False):
    """Ligne `ok` en base sous l'ancien handle ; cache et urls.txt sous le nouveau."""
    db.add_post(ANCIENNE_URL, "3kpost", "old.bsky.social", at_uri=AT_URI, did="did:plc:auteur")
    entrees = [_entree(AT_URI, NOUVELLE_URL), _entree(AT_URI_MORT, URL_MORTE, "notFoundPost")]
    if avec_neuf:
        entrees.append(_entree(AT_URI_NEUF, URL_NEUVE))
    save_cache(resolve_path(config, "bookmarks_cache"), entrees)
    resolve_path(config, "urls_file").write_text("\n".join(e["url"] for e in entrees), encoding="utf-8")


class TestPendingDownloads:
    def test_changement_de_handle_rien_a_telecharger(self, config, db):
        _changement_de_handle(config, db)
        urls, vues = pending_downloads(config, db)
        assert urls == []
        assert vues[NOUVELLE_URL]["uri"] == AT_URI

    def test_post_neuf_avec_sa_vue_et_morts_exclus(self, config, db):
        _changement_de_handle(config, db, avec_neuf=True)
        urls, vues = pending_downloads(config, db)
        assert urls == [URL_NEUVE]
        assert vues[URL_NEUVE]["uri"] == AT_URI_NEUF

    def test_sans_cache_comparaison_par_url(self, config, db):
        db.add_post(ANCIENNE_URL, "3kpost", "old.bsky.social", at_uri=AT_URI)
        resolve_path(config, "urls_file").write_text(f"{NOUVELLE_URL}\n{ANCIENNE_URL}", encoding="utf-8")
        urls, vues = pending_downloads(config, db)
        assert urls == [NOUVELLE_URL]  # sans AT-URI connu, seule l'URL compte
        assert vues == {}

    def test_ni_cache_ni_urls(self, config, db):
        assert pending_downloads(config, db) == ([], {})


class TestAppelants:
    def test_cmd_download_ne_retelecharge_pas_apres_changement_de_handle(self, config, db, non_interactif):
        _changement_de_handle(config, db)
        with (
            patch("core.cli._preparer_config", return_value=config),
            patch("core.cli.orchestrator.run") as run,
        ):
            assert cli.main(["download"]) == 0
        run.assert_not_called()

    def test_cmd_download_transmet_les_vues(self, config, db, non_interactif):
        _changement_de_handle(config, db, avec_neuf=True)
        stats = {"success": 1, "failed": [], "error_500": [], "error_429": []}
        with (
            patch("core.cli._preparer_config", return_value=config),
            patch("core.cli.orchestrator.run", return_value=stats) as run,
        ):
            assert cli.main(["download"]) == 0
        assert run.call_args.args[0] == [URL_NEUVE]
        assert run.call_args.kwargs["post_views"][URL_NEUVE]["uri"] == AT_URI_NEUF

    def test_download_media_ne_retelecharge_pas_apres_changement_de_handle(self, config, db):
        _changement_de_handle(config, db)
        with patch("bsmb.run") as run, patch("bsmb.confirm", return_value=True):
            assert bsmb.download_media(config) is True
        run.assert_not_called()

    def test_app_state_coherent_avec_status(self, config, db):
        _changement_de_handle(config, db, avec_neuf=True)
        assert bsmb.get_app_state(config)["new_count"] == 1
        assert cli.collect_status(config)["new_count"] == 1


class TestRunSync:
    SESSION = {
        "token": "Bearer t",
        "refresh_jwt": "r",
        "did": "did:plc:moi",
        "pds_url": "https://pds.example",
    }

    def test_memorise_le_pds_puis_synchronise(self, config, db):
        resultat = {"error": None}
        with patch("core.bookmarks.BookmarkSync") as sync_cls:
            sync_cls.return_value.sync.return_value = resultat
            progression = MagicMock()
            assert run_sync(config, db, self.SESSION, progression) is resultat
        assert config["pds_url"] == "https://pds.example"
        sync_cls.assert_called_once_with(config, db)
        sync_cls.return_value.sync.assert_called_once_with(
            "Bearer t", on_progress=progression, session_info=self.SESSION
        )

    def test_cmd_sync_et_do_sync_passent_par_run_sync(self, config):
        resultat = {
            "error": None,
            "expired": False,
            "online_count": 1,
            "local_count": 1,
            "new_count": 0,
            "new_urls": [],
            "dead_count": 0,
        }
        with (
            patch("core.cli._preparer_config", return_value=config),
            patch("core.cli.get_session", return_value=self.SESSION),
            patch("core.cli.run_sync", return_value=resultat) as cli_sync,
        ):
            assert cli.main(["sync"]) == 0
        cli_sync.assert_called_once()
        with (
            patch("bsmb.get_session", return_value=self.SESSION),
            patch("bsmb.run_sync", return_value=resultat) as menu_sync,
            patch("bsmb.pause"),
        ):
            bsmb.do_sync(config)
        menu_sync.assert_called_once()
