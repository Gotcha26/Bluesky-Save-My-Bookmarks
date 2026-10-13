"""Tests de la base de données : statut conservé, doublons, relance des erreurs, migrations (issue #9)."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from api.post_analyzer import PostType
from api.quote_resolver import QuoteTarget
from core.bookmarks import BookmarkSync
from core.config import DEFAULT_CONFIG
from core.database import Database
from core.orchestrator import process_post
from downloaders import DownloadError, DownloadResult

URL = "https://bsky.app/profile/user.bsky.social/post/3k1"
URL2 = "https://bsky.app/profile/user.bsky.social/post/3k2"
DID = "did:plc:abc"
URI = f"at://{DID}/app.bsky.feed.post/3k1"


def _ligne(db, url):
    curseur = db.conn.cursor()
    curseur.row_factory = sqlite3.Row
    return curseur.execute("SELECT * FROM posts WHERE url = ?", (url,)).fetchone()


def _vieillir(db, url, jours):
    ancien = (datetime.now() - timedelta(days=jours)).isoformat()
    db.conn.execute("UPDATE posts SET last_check = ? WHERE url = ?", (ancien, url))
    db.conn.commit()


class TestAddPostConserveLeStatut:
    def test_statut_et_added_at_conserves_apres_add_post_repete(self, tmp_db):
        tmp_db.add_post(URL, "3k1", "user")
        tmp_db.mark_post_status(URL, "deleted")
        avant = _ligne(tmp_db, URL)
        tmp_db.add_post(URL, "3k1", "user")
        apres = _ligne(tmp_db, URL)
        assert apres["status"] == "deleted"
        assert apres["added_at"] == avant["added_at"]
        assert apres["last_check"] >= avant["last_check"]

    def test_valeurs_absentes_ne_ecrasent_pas_les_existantes(self, tmp_db):
        tmp_db.add_post(URL, "3k1", "user", at_uri=URI, did=DID)
        tmp_db.add_post(URL)
        ligne = _ligne(tmp_db, URL)
        assert (ligne["post_id"], ligne["handle"], ligne["at_uri"], ligne["did"]) == ("3k1", "user", URI, DID)

    def test_at_uri_complete_une_ancienne_ligne(self, tmp_db):
        tmp_db.add_post(URL, "3k1", "user")
        tmp_db.add_post(URL, "3k1", "user", at_uri=URI, did=DID)
        ligne = _ligne(tmp_db, URL)
        assert (ligne["at_uri"], ligne["did"], ligne["rkey"]) == (URI, DID, "3k1")

    def test_changement_de_handle_met_a_jour_la_ligne_et_garde_statut_et_medias(self, tmp_db):
        tmp_db.add_post(URL, "3k1", "ancien", at_uri=URI, did=DID)
        tmp_db.mark_post_status(URL, "error_500")
        tmp_db.add_media(URL, "image", "a.jpg")
        added_at = _ligne(tmp_db, URL)["added_at"]

        nouvelle = "https://bsky.app/profile/nouveau.bsky.social/post/3k1"
        tmp_db.add_post(nouvelle, "3k1", "nouveau.bsky.social", at_uri=URI, did=DID)

        assert tmp_db.get_stats()["posts"] == 1
        assert _ligne(tmp_db, URL) is None
        ligne = _ligne(tmp_db, nouvelle)
        assert (ligne["handle"], ligne["status"], ligne["added_at"]) == (
            "nouveau.bsky.social",
            "error_500",
            added_at,
        )
        medias = tmp_db.conn.execute("SELECT post_url, filename FROM media").fetchall()
        assert [tuple(m) for m in medias] == [(nouvelle, "a.jpg")]

    def test_plus_aucun_insert_or_replace(self):
        import inspect

        import core.database

        assert "INSERT OR REPLACE" not in inspect.getsource(core.database).upper()


class TestAddMediaSansDoublon:
    def test_doublon_ignore(self, tmp_db):
        tmp_db.add_post(URL)
        tmp_db.add_media(URL, "image", "a.jpg")
        tmp_db.add_media(URL, "image", "a.jpg")
        assert tmp_db.get_stats()["images"] == 1

    def test_meme_nom_sur_deux_posts_autorise(self, tmp_db):
        tmp_db.add_post(URL)
        tmp_db.add_post(URL2)
        tmp_db.add_media(URL, "image", "a.jpg")
        tmp_db.add_media(URL2, "image", "a.jpg")
        assert tmp_db.get_stats()["images"] == 2

    def test_cid_enregistre(self, tmp_db):
        tmp_db.add_post(URL)
        tmp_db.add_media(URL, "image", "a.jpg", cid="bafkrei")
        tmp_db.add_media(URL, "image", "b.jpg")
        cids = dict(tmp_db.conn.execute("SELECT filename, cid FROM media").fetchall())
        assert cids == {"a.jpg": "bafkrei", "b.jpg": None}


class TestClesEtrangeres:
    def test_pragma_actif(self, tmp_db):
        assert tmp_db.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    def test_media_orphelin_refuse(self, tmp_db):
        with pytest.raises(sqlite3.IntegrityError):
            tmp_db.add_media("https://inconnu", "image", "a.jpg")

    def test_suppression_du_post_supprime_ses_medias(self, tmp_db):
        tmp_db.add_post(URL)
        tmp_db.add_media(URL, "image", "a.jpg")
        tmp_db.conn.execute("DELETE FROM posts WHERE url = ?", (URL,))
        tmp_db.conn.commit()
        assert tmp_db.get_stats()["images"] == 0


class TestGetPendingPosts:
    def test_nouvelles_urls_incluses(self, tmp_db):
        assert tmp_db.get_pending_posts([URL]) == [URL]

    @pytest.mark.parametrize("statut", ["error_500", "error_429", "unknown", "repost"])
    def test_statut_en_erreur_ancien_est_retente(self, tmp_db, statut):
        tmp_db.add_post(URL)
        tmp_db.mark_post_status(URL, statut)
        _vieillir(tmp_db, URL, 8)
        assert tmp_db.get_pending_posts([URL]) == [URL]

    def test_statut_en_erreur_recent_n_est_pas_retente(self, tmp_db):
        tmp_db.add_post(URL)
        tmp_db.mark_post_status(URL, "error_500")
        _vieillir(tmp_db, URL, 2)
        assert tmp_db.get_pending_posts([URL]) == []

    def test_seuil_configurable(self, tmp_db):
        tmp_db.add_post(URL)
        tmp_db.mark_post_status(URL, "unknown")
        _vieillir(tmp_db, URL, 2)
        assert tmp_db.get_pending_posts([URL], retry_after_days=1) == [URL]
        assert tmp_db.get_pending_posts([URL], retry_after_days=3) == []

    @pytest.mark.parametrize("statut", ["ok", "deleted"])
    def test_ok_et_deleted_jamais_retentes(self, tmp_db, statut):
        tmp_db.add_post(URL)
        tmp_db.mark_post_status(URL, statut)
        _vieillir(tmp_db, URL, 100)
        assert tmp_db.get_pending_posts([URL]) == []

    def test_ordre_conserve(self, tmp_db):
        tmp_db.add_post(URL2)
        tmp_db.mark_post_status(URL2, "error_500")
        _vieillir(tmp_db, URL2, 30)
        assert tmp_db.get_pending_posts([URL2, URL]) == [URL2, URL]

    def test_refs_nouvelles_et_a_retenter(self, tmp_db):
        tmp_db.add_post(URL, "3k1", "user", at_uri=URI, did=DID)
        tmp_db.mark_post_status(URL, "error_500")
        _vieillir(tmp_db, URL, 10)
        a_retenter = {"at_uri": URI, "url": "https://bsky.app/profile/autre/post/3k1"}
        nouvelle = {"at_uri": None, "url": URL2}
        assert tmp_db.get_pending_refs([a_retenter, nouvelle]) == [a_retenter, nouvelle]

    def test_refs_recentes_exclues(self, tmp_db):
        tmp_db.add_post(URL, "3k1", "user", at_uri=URI, did=DID)
        tmp_db.mark_post_status(URL, "error_500")
        assert tmp_db.get_pending_refs([{"at_uri": URI, "url": URL}]) == []


class TestMigrations:
    def _base_v0(self, chemin):
        conn = sqlite3.connect(chemin)
        conn.execute(
            "CREATE TABLE posts (url TEXT PRIMARY KEY, post_id TEXT, handle TEXT, "
            "added_at TEXT, last_check TEXT)"
        )
        conn.execute(
            "CREATE TABLE media (id INTEGER PRIMARY KEY AUTOINCREMENT, post_url TEXT, "
            "media_type TEXT, filename TEXT, downloaded_at TEXT, "
            "FOREIGN KEY(post_url) REFERENCES posts(url))"
        )
        conn.execute(
            "INSERT INTO posts VALUES (?, '3k1', 'user', '2025-01-01T00:00:00', '2025-01-02T00:00:00')",
            (URL,),
        )
        conn.execute(
            "INSERT INTO media (post_url, media_type, filename, downloaded_at) "
            "VALUES (?, 'image', 'image_0', 't1')",
            (URL,),
        )
        conn.execute(
            "INSERT INTO media (post_url, media_type, filename, downloaded_at) "
            "VALUES (?, 'image', 'image_0', 't2')",
            (URL,),
        )
        conn.execute(
            "INSERT INTO media (post_url, media_type, filename, downloaded_at) "
            "VALUES (?, 'video', 'v.mp4', 't3')",
            (URL,),
        )
        conn.execute(
            "INSERT INTO media (post_url, media_type, filename, downloaded_at) "
            "VALUES ('https://orphelin', 'image', 'x.jpg', 't4')"
        )
        conn.commit()
        conn.close()

    def _version(self, db):
        return db.conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0]

    def test_base_neuve_en_version_2(self, tmp_db):
        assert self._version(tmp_db) == "2"

    def test_message_de_migration_sur_stderr(self, tmp_path, capsys):
        """Revue finale M4 : stdout reste propre (status --json)."""
        chemin = str(tmp_path / "v0.db")
        self._base_v0(chemin)
        Database(chemin).close()
        sortie = capsys.readouterr()
        assert sortie.out == ""
        assert "orphelin" in sortie.err

    def test_migration_depuis_v0(self, tmp_path):
        chemin = str(tmp_path / "v0.db")
        self._base_v0(chemin)
        db = Database(chemin)
        try:
            assert self._version(db) == "2"
            colonnes = {r[1] for r in db.conn.execute("PRAGMA table_info(posts)")}
            assert {"status", "at_uri", "did", "rkey"} <= colonnes
            ligne = _ligne(db, URL)
            assert (ligne["status"], ligne["added_at"]) == ("ok", "2025-01-01T00:00:00")
            medias = [
                tuple(m) for m in db.conn.execute("SELECT filename, downloaded_at FROM media ORDER BY id")
            ]
            assert medias == [("image_0", "t1"), ("v.mp4", "t3")]  # doublon et orphelin retirés
            assert "cid" in {r[1] for r in db.conn.execute("PRAGMA table_info(media)")}
            db.add_media(URL, "image", "v.mp4")
            assert db.conn.execute("SELECT COUNT(*) FROM media").fetchone()[0] == 2
            db.conn.execute("DELETE FROM posts WHERE url = ?", (URL,))
            assert db.conn.execute("SELECT COUNT(*) FROM media").fetchone()[0] == 0
        finally:
            db.close()

    def test_migration_depuis_v1_sans_table_meta(self, tmp_path):
        chemin = str(tmp_path / "v1.db")
        self._base_v0(chemin)
        conn = sqlite3.connect(chemin)
        conn.execute("ALTER TABLE posts ADD COLUMN status TEXT DEFAULT 'ok'")
        for col in ("at_uri", "did", "rkey"):
            conn.execute(f"ALTER TABLE posts ADD COLUMN {col} TEXT")
        conn.execute("CREATE UNIQUE INDEX idx_posts_at_uri ON posts(at_uri)")
        conn.execute("UPDATE posts SET status = 'error_500', at_uri = ?", (URI,))
        conn.commit()
        conn.close()
        db = Database(chemin)
        try:
            assert self._version(db) == "2"
            assert _ligne(db, URL)["status"] == "error_500"
            assert db.conn.execute("SELECT COUNT(*) FROM media").fetchone()[0] == 2
        finally:
            db.close()

    def test_reouverture_idempotente(self, tmp_path):
        chemin = str(tmp_path / "x.db")
        db = Database(chemin)
        db.add_post(URL)
        db.add_media(URL, "image", "a.jpg")
        db.close()
        db = Database(chemin)
        assert self._version(db) == "2"
        assert db.get_stats()["images"] == 1
        db.close()


def _res(nom, media_type):
    return DownloadResult(nom, Path(nom), media_type, 1)


def _downloaders(resultats=(), erreur=None):
    """Les trois downloaders mockés, renvoyant tous `resultats` (ou levant `erreur`)."""
    return patch.multiple(
        "core.orchestrator",
        **{
            nom: MagicMock(return_value=list(resultats), side_effect=erreur)
            for nom in ("download_images", "download_video", "save_text")
        },
    )


def _lancer(db, tmp_path, post_type, data, resultats=(), erreur=None, resolver=None, url=URL):
    analyzer = MagicMock()
    analyzer.analyze.return_value = (post_type, data, {"embed_type": "x"})
    with _downloaders(resultats, erreur):
        return process_post(
            url, "IMG", "VID", "TXT", db, analyzer, resolver or MagicMock(), tmp_path, lambda *a, **k: None
        )


def _medias(db):
    return [tuple(m) for m in db.conn.execute("SELECT media_type, filename FROM media ORDER BY id")]


class TestOrchestrateurNomsReels:
    def test_images_enregistrees_avec_leur_nom(self, tmp_db, tmp_path):
        sortie = [_res("u_1_01.jpg", "image"), _res("u_1_02.png", "image")]
        res = _lancer(tmp_db, tmp_path, PostType.IMAGES, {"image_count": 2}, sortie)
        assert res[1] == 2
        assert _medias(tmp_db) == [("image", "u_1_01.jpg"), ("image", "u_1_02.png")]

    def test_video_enregistree_avec_son_nom(self, tmp_db, tmp_path):
        sortie = [_res("u_1_01.mp4", "video")]
        res = _lancer(tmp_db, tmp_path, PostType.VIDEO, {}, sortie)
        assert res[2] == 1
        assert _medias(tmp_db) == [("video", "u_1_01.mp4")]

    def test_retraitement_ne_cree_pas_de_doublon(self, tmp_db, tmp_path):
        sortie = [_res("u_1_01.jpg", "image")]
        _lancer(tmp_db, tmp_path, PostType.IMAGES, {"image_count": 1}, sortie)
        _lancer(tmp_db, tmp_path, PostType.IMAGES, {"image_count": 1}, sortie)
        assert _medias(tmp_db) == [("image", "u_1_01.jpg")]


class TestOrchestrateurStatuts:
    def _statut(self, db):
        return _ligne(db, URL)["status"]

    def test_unknown_marque(self, tmp_db, tmp_path):
        _lancer(tmp_db, tmp_path, PostType.UNKNOWN, {}, "")
        assert self._statut(tmp_db) == "unknown"

    def test_citation_non_resolue_sans_contenu_propre_est_failed(self, tmp_db, tmp_path):
        tmp_db.add_post(URL)
        tmp_db.mark_post_status(URL, "unknown")
        resolver = MagicMock()
        resolver.resolve.return_value = None
        res = _lancer(tmp_db, tmp_path, PostType.QUOTE, {}, "", resolver=resolver)
        assert res[4] == "failed"
        assert self._statut(tmp_db) == "failed"  # un échec est retenté plus tard (statut failed)

    def test_succes_remet_le_statut_a_ok_apres_une_erreur(self, tmp_db, tmp_path):
        tmp_db.add_post(URL)
        tmp_db.mark_post_status(URL, "error_500")
        res = _lancer(tmp_db, tmp_path, PostType.TEXT_ONLY, {}, [_res("t.txt", "text")])
        assert res[0] is True
        assert self._statut(tmp_db) == "ok"

    def test_echec_pose_le_statut_failed(self, tmp_db, tmp_path):
        tmp_db.add_post(URL)
        tmp_db.mark_post_status(URL, "error_500")
        _lancer(tmp_db, tmp_path, PostType.TEXT_ONLY, {}, erreur=DownloadError("API"))
        assert self._statut(tmp_db) == "failed"

    def test_citation_archivee_remet_le_citant_a_ok(self, tmp_db, tmp_path):
        tmp_db.add_post(URL)
        tmp_db.mark_post_status(URL, "unknown")
        resolver = MagicMock()
        resolver.resolve.return_value = _cible()
        analyzer = MagicMock()
        analyzer.analyze.side_effect = [
            (PostType.QUOTE, {}, {}),
            (PostType.TEXT_ONLY, {}, {}),
        ]
        with _downloaders([_res("t.txt", "text")]):
            process_post(URL, "IMG", "VID", "TXT", tmp_db, analyzer, resolver, tmp_path, lambda *a, **k: None)
        assert self._statut(tmp_db) == "ok"


def _cible():
    return QuoteTarget(URL2, DID, "3k2", "user.bsky.social", "app.bsky.feed.post", "post")


class TestCitationEnEchec:
    """Le citant garde son propre contenu : son statut ne dépend pas de l'issue du post cité."""

    def _citant_dont_le_cite(self, db, tmp_path, type_cite, erreur_cite=None):
        db.add_post(URL)
        resolver = MagicMock()
        resolver.resolve.return_value = _cible()
        analyzer = MagicMock()
        analyzer.analyze.side_effect = [(PostType.QUOTE, {}, {}), (type_cite, {}, {"embed_type": "x"})]

        def save_text(url, dest, config, session=None, name_prefix=None):
            if name_prefix and erreur_cite:
                raise erreur_cite
            return [_res("citant.txt" if not name_prefix else "cite.txt", "text")]

        non_resolues = []
        with patch.multiple("core.orchestrator", save_text=save_text):
            res = process_post(
                URL,
                "IMG",
                "VID",
                "TXT",
                db,
                analyzer,
                resolver,
                tmp_path,
                lambda *a, **k: None,
                quotes_unresolved=non_resolues,
            )
        return res, non_resolues

    def test_cite_en_erreur_500_le_citant_reste_ok(self, tmp_db, tmp_path):
        res, non_resolues = self._citant_dont_le_cite(tmp_db, tmp_path, PostType.ERROR_500)
        assert res[4] == "success"
        assert _ligne(tmp_db, URL)["status"] == "ok"
        assert non_resolues == [URL]
        assert _medias(tmp_db) == [("text", "citant.txt")]

    def test_echec_de_telechargement_du_cite_le_citant_reste_ok(self, tmp_db, tmp_path):
        res, non_resolues = self._citant_dont_le_cite(
            tmp_db, tmp_path, PostType.TEXT_ONLY, erreur_cite=DownloadError("API")
        )
        assert res[4] == "success"
        assert _ligne(tmp_db, URL)["status"] == "ok"
        assert non_resolues == [URL]

    def test_cite_supprime_le_citant_reste_ok_sans_citation_non_resolue(self, tmp_db, tmp_path):
        res, non_resolues = self._citant_dont_le_cite(tmp_db, tmp_path, PostType.ERROR_400)
        assert res[4] == "success"
        assert _ligne(tmp_db, URL)["status"] == "ok"
        assert non_resolues == []


class TestSynchronisation:
    def test_config_par_defaut(self):
        assert DEFAULT_CONFIG["retry_after_days"] == 7

    @patch("core.bookmarks.save_config")
    @patch("core.bookmarks.fetch_bookmarks")
    def test_sync_compte_les_posts_a_retenter(self, mock_fetch, _save, tmp_config, tmp_db):
        tmp_db.add_post(URL)
        tmp_db.mark_post_status(URL, "error_500")
        _vieillir(tmp_db, URL, 9)
        mock_fetch.return_value = {
            "urls": [URL],
            "posts": [{"at_uri": None, "url": URL}],
            "count": 1,
            "pages": 1,
            "error": None,
            "expired": False,
        }
        result = BookmarkSync(tmp_config, tmp_db).sync("Bearer t")
        assert result["new_urls"] == [URL]

    def test_etat_en_cache_compte_les_posts_a_retenter(self, tmp_config, tmp_db, tmp_path):
        tmp_db.add_post(URL)
        tmp_db.mark_post_status(URL, "unknown")
        _vieillir(tmp_db, URL, 9)
        (tmp_path / "urls.txt").write_text(URL, encoding="utf-8")
        assert BookmarkSync(tmp_config, tmp_db).get_cached_state()["new_count"] == 1
        tmp_config["retry_after_days"] = 30
        assert BookmarkSync(tmp_config, tmp_db).get_cached_state()["new_count"] == 0
