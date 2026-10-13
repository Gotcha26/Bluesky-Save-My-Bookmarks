"""Tests de l'identité des posts par AT-URI (issue #2) : base, export, analyse, synchronisation."""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

from api.export_bookmarks import fetch_bookmarks
from api.post_analyzer import PostAnalyzer, PostType
from api.quote_resolver import QuoteResolver
from core.bookmarks import BookmarkSync
from core.database import Database
from core.orchestrator import process_post
from downloaders import DownloadResult

DID = "did:plc:abc"
URI = f"at://{DID}/app.bsky.feed.post/3k1"
URL = "https://bsky.app/profile/user.bsky.social/post/3k1"


def _colonnes(db):
    return {row[1] for row in db.conn.execute("PRAGMA table_info(posts)")}


def _post(at_uri=URI, url=URL, did=DID, rkey="3k1", handle="user.bsky.social"):
    return {
        "at_uri": at_uri,
        "did": did,
        "rkey": rkey,
        "handle": handle,
        "url": url,
        "item_type": "unknown",
        "post_view": None,
        "created_at": None,
    }


class TestMigration:
    def test_nouvelle_base_a_les_colonnes(self, tmp_db):
        assert {"at_uri", "did", "rkey"} <= _colonnes(tmp_db)

    def test_migration_base_ancienne(self, tmp_path):
        chemin = str(tmp_path / "ancienne.db")
        conn = sqlite3.connect(chemin)
        conn.execute(
            "CREATE TABLE posts (url TEXT PRIMARY KEY, post_id TEXT, handle TEXT, "
            "added_at TEXT, last_check TEXT, status TEXT DEFAULT 'ok')"
        )
        conn.execute("INSERT INTO posts (url, post_id, handle) VALUES (?, '3k1', 'user.bsky.social')", (URL,))
        conn.commit()
        conn.close()

        db = Database(chemin)
        try:
            assert {"at_uri", "did", "rkey"} <= _colonnes(db)
            ligne = db.conn.execute("SELECT url, at_uri, did, rkey FROM posts").fetchone()
            assert tuple(ligne) == (URL, None, None, None)
            # L'unicité d'at_uri est effective après migration
            db.add_post("https://bsky.app/profile/a/post/1", "1", "a", at_uri=URI, did=DID)
            db.add_post("https://bsky.app/profile/b/post/1", "1", "b", at_uri=URI, did=DID)
            assert db.conn.execute("SELECT COUNT(*) FROM posts WHERE at_uri = ?", (URI,)).fetchone()[0] == 1
        finally:
            db.close()

    def test_migration_idempotente(self, tmp_path):
        chemin = str(tmp_path / "x.db")
        Database(chemin).close()
        db = Database(chemin)
        assert {"at_uri", "did", "rkey"} <= _colonnes(db)
        db.close()


class TestAddPostAtUri:
    def test_enregistre_at_uri_did_et_rkey(self, tmp_db):
        tmp_db.add_post(URL, "3k1", "user.bsky.social", at_uri=URI, did=DID)
        ligne = tmp_db.conn.execute("SELECT at_uri, did, rkey FROM posts WHERE url = ?", (URL,)).fetchone()
        assert tuple(ligne) == (URI, DID, "3k1")

    def test_sans_at_uri_reste_compatible(self, tmp_db):
        tmp_db.add_post(URL, "3k1", "user")
        ligne = tmp_db.conn.execute("SELECT at_uri, did, rkey FROM posts WHERE url = ?", (URL,)).fetchone()
        assert tuple(ligne) == (None, None, None)

    def test_changement_de_handle_ne_cree_pas_de_doublon(self, tmp_db):
        tmp_db.add_post(URL, "3k1", "ancien", at_uri=URI, did=DID)
        tmp_db.add_post(
            "https://bsky.app/profile/nouveau.bsky.social/post/3k1", "3k1", "nouveau", at_uri=URI, did=DID
        )
        assert tmp_db.get_stats()["posts"] == 1


class TestGetNewRefs:
    def test_post_inconnu_est_nouveau(self, tmp_db):
        assert tmp_db.get_new_refs([_post()]) == [_post()]

    def test_reconnu_par_at_uri_malgre_un_autre_handle(self, tmp_db):
        tmp_db.add_post(URL, "3k1", "ancien", at_uri=URI, did=DID)
        autre = _post(url="https://bsky.app/profile/nouveau.bsky.social/post/3k1")
        assert tmp_db.get_new_refs([autre]) == []

    def test_repli_sur_url_quand_at_uri_est_null(self, tmp_db):
        tmp_db.add_post(URL, "3k1", "user.bsky.social")  # ancienne ligne, at_uri NULL
        assert tmp_db.get_new_refs([_post()]) == []

    def test_url_connue_mais_at_uri_different_est_nouveau(self, tmp_db):
        tmp_db.add_post(
            URL, "3k1", "user", at_uri="at://did:plc:autre/app.bsky.feed.post/3k1", did="did:plc:autre"
        )
        assert tmp_db.get_new_refs([_post()]) == [_post()]

    def test_get_new_posts_inchange(self, tmp_db):
        tmp_db.add_post(URL, "3k1", "user")
        assert tmp_db.get_new_posts([URL, "https://bsky.app/profile/x/post/2"]) == [
            "https://bsky.app/profile/x/post/2"
        ]

    def test_liste_vide(self, tmp_db):
        assert tmp_db.get_new_refs([]) == []


def _session_avec(session, bookmarks):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"bookmarks": bookmarks, "cursor": None}
    session.get.return_value = response
    return session


class TestExportPosts:
    def test_posts_et_urls(self, fake_session):
        _session_avec(
            fake_session,
            [
                {
                    "subject": {"uri": URI},
                    "item": {"author": {"did": DID, "handle": "user.bsky.social"}},
                }
            ],
        )
        result = fetch_bookmarks("Bearer t")
        assert result["posts"] == [_post()]
        assert result["urls"] == [URL]

    def test_handle_invalid_remplace_par_le_did(self, fake_session):
        _session_avec(
            fake_session,
            [
                {
                    "subject": {"uri": URI},
                    "item": {"author": {"did": DID, "handle": "handle.invalid"}},
                }
            ],
        )
        result = fetch_bookmarks("Bearer t")
        attendu = f"https://bsky.app/profile/{DID}/post/3k1"
        assert result["urls"] == [attendu]
        assert "handle.invalid" not in result["urls"][0]
        assert result["posts"][0]["url"] == attendu
        assert result["posts"][0]["at_uri"] == URI

    def test_aucune_resolution_reseau(self, fake_session):
        _session_avec(
            fake_session,
            [
                {
                    "subject": {"uri": URI},
                    "item": {"author": {"handle": "handle.invalid"}},
                }
            ],
        )
        with patch("core.post_ref.resolve_handle") as resolve:
            fetch_bookmarks("Bearer t")
        resolve.assert_not_called()

    def test_uri_invalide_ignoree(self, fake_session):
        _session_avec(
            fake_session,
            [
                {"subject": {"uri": "at://did:plc:abc"}, "item": {}},
                {"subject": {"uri": URI}, "item": {"author": {"handle": "user.bsky.social"}}},
            ],
        )
        assert len(fetch_bookmarks("Bearer t")["posts"]) == 1

    def test_token_invalide_renvoie_posts_vide(self):
        assert fetch_bookmarks("x")["posts"] == []


def _reponse_get_record(uri=URI):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"uri": uri, "value": {"text": "bonjour"}}
    return resp


class TestAnalyzerRepo:
    def test_repo_est_le_did_quand_l_url_en_contient_un(self, mock_get):
        mock_get.return_value = _reponse_get_record()
        _, data, _ = PostAnalyzer().analyze(f"https://bsky.app/profile/{DID}/post/3k1")
        assert mock_get.call_args.kwargs["params"]["repo"] == DID
        assert mock_get.call_count == 1
        assert data["did"] == DID
        assert data["at_uri"] == URI

    def test_repo_reste_le_handle_sinon(self, mock_get):
        mock_get.return_value = _reponse_get_record()
        _, data, _ = PostAnalyzer().analyze(URL)
        assert mock_get.call_args.kwargs["params"]["repo"] == "user.bsky.social"
        # Le DID est déduit de la réponse du getRecord, sans appel supplémentaire
        assert mock_get.call_count == 1
        assert data["did"] == DID
        assert data["at_uri"] == URI

    def test_erreur_400_avec_did_dans_l_url_garde_l_identite(self, mock_get):
        mock_get.return_value = MagicMock(status_code=400)
        post_type, data, _ = PostAnalyzer().analyze(f"https://bsky.app/profile/{DID}/post/3k1")
        assert post_type == PostType.ERROR_400
        assert data["at_uri"] == URI


class TestResolverRepo:
    def test_repo_est_le_did_quand_l_url_en_contient_un(self, mock_get):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"value": {"embed": {"$type": "app.bsky.embed.text"}}}
        mock_get.return_value = resp
        QuoteResolver().resolve(f"https://bsky.app/profile/{DID}/post/3k1")
        assert mock_get.call_args.kwargs["params"]["repo"] == DID

    def test_repo_reste_le_handle_sinon(self, mock_get):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"value": {"embed": {"$type": "app.bsky.embed.text"}}}
        mock_get.return_value = resp
        QuoteResolver().resolve(URL)
        assert mock_get.call_args.kwargs["params"]["repo"] == "user.bsky.social"

    def test_handle_invalid_du_post_cite_remplace_par_le_did(self, mock_get):
        record = MagicMock(status_code=200)
        record.raise_for_status.return_value = None
        record.json.return_value = {
            "value": {
                "embed": {
                    "$type": "app.bsky.embed.record",
                    "record": {"uri": "at://did:plc:cite/app.bsky.feed.post/orig"},
                }
            }
        }
        existe = MagicMock(status_code=200)
        existe.raise_for_status.return_value = None
        profil = MagicMock(status_code=200)
        profil.json.return_value = {"handle": "handle.invalid"}
        mock_get.side_effect = [record, existe, profil]

        cible = QuoteResolver().resolve(URL)
        assert cible.url == "https://bsky.app/profile/did:plc:cite/post/orig"
        assert cible.did == "did:plc:cite"
        assert cible.rkey == "orig"


class TestBookmarkSyncPosts:
    @patch("core.bookmarks.fetch_bookmarks")
    @patch("core.bookmarks.save_config")
    def test_sync_utilise_at_uri_pour_les_nouveaux(self, _save, mock_fetch, tmp_config, tmp_path):
        db = Database(str(tmp_path / "test.db"))
        tmp_config["urls_file"] = str(tmp_path / "urls.txt")
        # Déjà en base sous un ancien handle
        db.add_post(
            "https://bsky.app/profile/ancien.bsky.social/post/3k1", "3k1", "ancien", at_uri=URI, did=DID
        )
        autre = _post(
            at_uri="at://did:plc:z/app.bsky.feed.post/9",
            did="did:plc:z",
            rkey="9",
            url="https://bsky.app/profile/z.bsky.social/post/9",
            handle="z.bsky.social",
        )
        mock_fetch.return_value = {
            "urls": [URL, autre["url"]],
            "posts": [_post(), autre],
            "count": 2,
            "pages": 1,
            "error": None,
            "expired": False,
        }
        result = BookmarkSync(tmp_config, db).sync("Bearer t")
        assert result["new_count"] == 1
        assert result["new_urls"] == [autre["url"]]
        db.close()


class TestOrchestratorIdentite:
    def test_add_post_recoit_at_uri_et_did(self, tmp_db, tmp_path):
        analyzer = MagicMock()
        analyzer.analyze.return_value = (
            PostType.TEXT_ONLY,
            {"handle": "user.bsky.social", "did": DID, "at_uri": URI},
            {},
        )
        resultat = [DownloadResult("f.txt", Path("f.txt"), "text", 1)]
        with patch("core.orchestrator.save_text", return_value=resultat):
            process_post(URL, "I", "V", "T", tmp_db, analyzer, MagicMock(), tmp_path, lambda *a, **k: None)
        ligne = tmp_db.conn.execute("SELECT at_uri, did, rkey FROM posts WHERE url = ?", (URL,)).fetchone()
        assert tuple(ligne) == (URI, DID, "3k1")
