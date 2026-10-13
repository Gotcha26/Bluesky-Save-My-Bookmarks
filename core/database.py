#!/usr/bin/env python3
"""
Gestion de la base de données SQLite pour BSMB
"""

import sqlite3
import threading
from datetime import datetime, timedelta

# Version courante du schéma (table `meta`, clé `schema_version`).
# Chaque version N > 0 correspond à une méthode `_migrate_vN`.
SCHEMA_VERSION = 2

# Statuts d'un post qui méritent une nouvelle tentative après un délai
STATUTS_A_RETENTER = ("error_500", "error_429", "unknown", "repost")


class Database:
    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        # Sans ce PRAGMA, SQLite ignore les clés étrangères (désactivé par défaut)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.Lock()
        self._init_db()

    # ------------------------------------------------------------------
    # Schéma et migrations
    # ------------------------------------------------------------------

    def _init_db(self):
        """Crée le schéma d'une base neuve ou applique les migrations manquantes."""
        cursor = self.conn.cursor()
        existe = (
            cursor.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'posts'").fetchone()
            is not None
        )

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        if not existe:
            self._create_schema()
            self._set_version(SCHEMA_VERSION)
            return

        for version in range(self._get_version() + 1, SCHEMA_VERSION + 1):
            getattr(self, f"_migrate_v{version}")()
            self._set_version(version)

    def _create_schema(self):
        """Crée directement le schéma courant (base neuve)."""
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE posts (
                url TEXT PRIMARY KEY,
                post_id TEXT,
                handle TEXT,
                added_at TEXT,
                last_check TEXT,
                status TEXT DEFAULT 'ok',
                at_uri TEXT,
                did TEXT,
                rkey TEXT
            )
        """)
        cursor.execute("CREATE UNIQUE INDEX idx_posts_at_uri ON posts(at_uri)")
        cursor.execute(self._sql_table_media("media"))
        self.conn.commit()

    @staticmethod
    def _sql_table_media(nom):
        return f"""
            CREATE TABLE {nom} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_url TEXT,
                media_type TEXT,
                filename TEXT,
                downloaded_at TEXT,
                cid TEXT,
                UNIQUE(post_url, filename),
                FOREIGN KEY(post_url) REFERENCES posts(url)
                    ON DELETE CASCADE ON UPDATE CASCADE
            )
        """

    def _get_version(self):
        """Version du schéma : table `meta`, sinon déduite des colonnes (bases d'avant `meta`)."""
        row = self.conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        if row:
            return int(row[0])
        colonnes = {r[1] for r in self.conn.execute("PRAGMA table_info(posts)")}
        if {"status", "at_uri", "did", "rkey"} <= colonnes:
            return 1
        return 0

    def _set_version(self, version):
        self.conn.execute(
            """
            INSERT INTO meta (key, value) VALUES ('schema_version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
            (str(version),),
        )
        self.conn.commit()

    def _migrate_v1(self):
        """v1 : colonne `status` et identité par AT-URI (`at_uri`, `did`, `rkey`)."""
        cursor = self.conn.cursor()
        colonnes = [row[1] for row in cursor.execute("PRAGMA table_info(posts)").fetchall()]
        if "status" not in colonnes:
            cursor.execute("ALTER TABLE posts ADD COLUMN status TEXT DEFAULT 'ok'")
        # Les anciennes lignes gardent NULL, complétées lors de leur prochain
        # traitement, sans appel réseau
        for colonne in ("at_uri", "did", "rkey"):
            if colonne not in colonnes:
                cursor.execute(f"ALTER TABLE posts ADD COLUMN {colonne} TEXT")
        # SQLite n'accepte pas ADD COLUMN ... UNIQUE : l'unicité passe par un index
        # (plusieurs NULL restent autorisés)
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_posts_at_uri ON posts(at_uri)")
        self.conn.commit()

    def _migrate_v2(self):
        """v2 : `media` recréée avec UNIQUE(post_url, filename), ON DELETE CASCADE et `cid`.

        Les doublons sont dédoublonnés (le plus ancien est conservé) et les
        médias orphelins (sans post) sont écartés. Opération atomique.
        """
        cursor = self.conn.cursor()
        cursor.execute("BEGIN")
        try:
            cursor.execute("DROP TABLE IF EXISTS media_v2")
            cursor.execute(self._sql_table_media("media_v2"))
            ancienne = cursor.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'media'"
            ).fetchone()
            if ancienne:
                orphelins = cursor.execute(
                    "SELECT COUNT(*) FROM media WHERE post_url IS NULL "
                    "OR post_url NOT IN (SELECT url FROM posts)"
                ).fetchone()[0]
                if orphelins:
                    print(f"Migration v2 : {orphelins} média(s) orphelin(s) écarté(s) (post absent).")
                cursor.execute("""
                    INSERT OR IGNORE INTO media_v2 (post_url, media_type, filename, downloaded_at)
                    SELECT post_url, media_type, filename, downloaded_at FROM media
                    WHERE post_url IN (SELECT url FROM posts)
                    ORDER BY id
                """)
                cursor.execute("DROP TABLE media")
            cursor.execute("ALTER TABLE media_v2 RENAME TO media")
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # ------------------------------------------------------------------
    # Posts
    # ------------------------------------------------------------------

    def add_post(self, url, post_id=None, handle=None, at_uri=None, did=None):
        """Ajoute un post à la DB ou rafraîchit sa ligne (thread-safe).

        `added_at` et `status` ne sont jamais écrasés ; les valeurs absentes
        (None) ne remplacent pas les valeurs déjà connues.

        `at_uri` est l'identité canonique : si une ligne existe déjà avec le même
        `at_uri` sous une autre URL (handle changé), cette ligne est mise à jour
        (nouvelle URL, statut et médias conservés) au lieu de créer un doublon.
        """
        rkey = at_uri.rsplit("/", 1)[-1] if at_uri else None
        with self._lock:
            cursor = self.conn.cursor()
            now = datetime.now().isoformat()

            if at_uri:
                existante = cursor.execute("SELECT url FROM posts WHERE at_uri = ?", (at_uri,)).fetchone()
                if existante and existante[0] != url:
                    ancienne_url = existante[0]
                    # La nouvelle URL est peut-être déjà prise par une ancienne ligne
                    # sans at_uri : on ne renomme pas (pas de fusion), on rafraîchit seulement
                    occupee = cursor.execute("SELECT 1 FROM posts WHERE url = ?", (url,)).fetchone()
                    nouvelle_url = ancienne_url if occupee else url
                    # Les médias suivent via ON UPDATE CASCADE
                    try:
                        cursor.execute(
                            """
                            UPDATE posts SET url = ?, last_check = ?,
                                post_id = COALESCE(?, post_id),
                                handle = COALESCE(?, handle),
                                did = COALESCE(?, did)
                            WHERE at_uri = ?
                        """,
                            (nouvelle_url, now, post_id, handle, did, at_uri),
                        )
                        self.conn.commit()
                    except Exception:
                        self.conn.rollback()
                        raise
                    return

            cursor.execute(
                """
                INSERT INTO posts (url, post_id, handle, added_at, last_check, at_uri, did, rkey)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    last_check = excluded.last_check,
                    post_id = COALESCE(excluded.post_id, post_id),
                    handle = COALESCE(excluded.handle, handle),
                    at_uri = COALESCE(excluded.at_uri, at_uri),
                    did = COALESCE(excluded.did, did),
                    rkey = COALESCE(excluded.rkey, rkey)
            """,
                (url, post_id, handle, now, now, at_uri, did, rkey),
            )
            self.conn.commit()

    def add_media(self, post_url, media_type, filename, cid=None):
        """Ajoute un média téléchargé à la DB (thread-safe).

        Un même fichier pour un même post n'est enregistré qu'une fois
        (re-téléchargement en mode Force sans doublon).

        Args:
            post_url: URL du post
            media_type: 'image', 'video' ou 'text'
            filename: Nom du fichier téléchargé
            cid: CID du blob AT Protocol (optionnel)
        """
        with self._lock:
            cursor = self.conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute(
                """
                INSERT OR IGNORE INTO media (post_url, media_type, filename, downloaded_at, cid)
                VALUES (?, ?, ?, ?, ?)
            """,
                (post_url, media_type, filename, now, cid),
            )
            self.conn.commit()

    def find_media_by_cid(self, cid):
        """Nom du fichier déjà enregistré pour ce CID de blob, ou None (thread-safe)."""
        if not cid:
            return None
        with self._lock:
            row = self.conn.execute(
                "SELECT filename FROM media WHERE cid = ? ORDER BY id LIMIT 1", (cid,)
            ).fetchone()
        return row[0] if row else None

    def update_last_check(self, url):
        """Met à jour la date de dernière vérification d'un post (thread-safe)."""
        with self._lock:
            cursor = self.conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute(
                """
                UPDATE posts SET last_check = ? WHERE url = ?
            """,
                (now, url),
            )
            self.conn.commit()

    def get_new_posts(self, urls):
        """Retourne les URLs non trackées (thread-safe)."""
        with self._lock:
            cursor = self.conn.cursor()
            new_posts = []
            for url in urls:
                cursor.execute("SELECT url FROM posts WHERE url = ?", (url,))
                if not cursor.fetchone():
                    new_posts.append(url)
            return new_posts

    @staticmethod
    def _ligne_de_ref(cursor, ref):
        """Ligne (status, last_check) d'un post, ou None s'il n'est pas tracké.

        Comparaison sur `at_uri` ; repli sur `url` pour les anciennes lignes
        dont `at_uri` est encore NULL.
        """
        return cursor.execute(
            "SELECT status, last_check FROM posts WHERE at_uri = ? OR (at_uri IS NULL AND url = ?)",
            (ref.get("at_uri"), ref["url"]),
        ).fetchone()

    @staticmethod
    def _est_a_retenter(ligne, limite):
        """Vrai si le statut est retentable et la dernière vérification antérieure à `limite`."""
        status, last_check = ligne
        return status in STATUTS_A_RETENTER and (last_check is None or last_check < limite)

    @staticmethod
    def _limite_retry(retry_after_days):
        return (datetime.now() - timedelta(days=retry_after_days)).isoformat()

    def get_new_refs(self, refs):
        """Retourne les posts (dicts avec `at_uri` et `url`) non trackés (thread-safe)."""
        with self._lock:
            cursor = self.conn.cursor()
            return [ref for ref in refs if not self._ligne_de_ref(cursor, ref)]

    def get_pending_posts(self, urls, retry_after_days=7):
        """Retourne les URLs à traiter : non trackées, ou en erreur à retenter (thread-safe).

        Un post est à retenter si son statut est `error_500`, `error_429`, `unknown` ou `repost`
        et que sa dernière vérification date de plus de `retry_after_days` jours.
        `ok` et `deleted` ne sont jamais retentés.
        """
        limite = self._limite_retry(retry_after_days)
        with self._lock:
            cursor = self.conn.cursor()
            pending = []
            for url in urls:
                ligne = cursor.execute(
                    "SELECT status, last_check FROM posts WHERE url = ?", (url,)
                ).fetchone()
                if ligne is None or self._est_a_retenter(ligne, limite):
                    pending.append(url)
            return pending

    def get_pending_refs(self, refs, retry_after_days=7):
        """Comme `get_pending_posts`, pour des dicts avec `at_uri` et `url` (thread-safe)."""
        limite = self._limite_retry(retry_after_days)
        with self._lock:
            cursor = self.conn.cursor()
            pending = []
            for ref in refs:
                ligne = self._ligne_de_ref(cursor, ref)
                if ligne is None or self._est_a_retenter(ligne, limite):
                    pending.append(ref)
            return pending

    def get_stats(self):
        """Retourne les statistiques (thread-safe).

        Returns:
            dict: {
                'posts': nombre de posts trackés,
                'images': nombre d'images téléchargées,
                'videos': nombre de vidéos téléchargées,
                'texts': nombre de textes sauvegardés,
                'dead': nombre de liens morts (status != 'ok')
            }
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM posts")
            posts_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM media WHERE media_type = 'image'")
            images_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM media WHERE media_type = 'video'")
            videos_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM media WHERE media_type = 'text'")
            texts_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM posts WHERE status != 'ok'")
            dead_count = cursor.fetchone()[0]
            return {
                "posts": posts_count,
                "images": images_count,
                "videos": videos_count,
                "texts": texts_count,
                "dead": dead_count,
            }

    def mark_post_status(self, url, status):
        """Met à jour le statut d'un post (thread-safe).

        Args:
            url: URL du post
            status: 'ok', 'deleted', 'blocked', 'error_500', 'error_429', 'unknown'
                ('repost' n'est plus écrit, hérité)
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("UPDATE posts SET status = ? WHERE url = ?", (status, url))
            self.conn.commit()

    def mark_unavailable(self, ref, status):
        """Enregistre un post que l'API déclare supprimé ou bloqué (thread-safe).

        Args:
            ref: dict avec `url` et, si connus, `at_uri`, `did`, `rkey`, `handle`
            status: 'deleted' ou 'blocked'

        Un post déjà archivé (`ok`) garde son statut : son contenu est sur le disque
        et `cleanup_dead_posts()` effacerait sinon sa trace en base.

        Returns:
            bool: True si le statut a été posé, False si le post était déjà `ok`.
        """
        url = ref["url"]
        at_uri = ref.get("at_uri")
        with self._lock:
            cursor = self.conn.cursor()
            # La ligne est identifiée par at_uri d'abord (l'URL a pu changer), puis par url
            ligne = None
            if at_uri:
                ligne = cursor.execute("SELECT url, status FROM posts WHERE at_uri = ?", (at_uri,)).fetchone()
            if ligne is None:
                ligne = cursor.execute("SELECT url, status FROM posts WHERE url = ?", (url,)).fetchone()
            if ligne is not None:
                if ligne[1] == "ok":
                    return False
                cursor.execute("UPDATE posts SET status = ? WHERE url = ?", (status, ligne[0]))
            else:
                now = datetime.now().isoformat()
                rkey = ref.get("rkey") or url.rstrip("/").rsplit("/", 1)[-1]
                cursor.execute(
                    "INSERT INTO posts "
                    "(url, post_id, handle, added_at, last_check, status, at_uri, did, rkey) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        url,
                        rkey,
                        ref.get("handle"),
                        now,
                        now,
                        status,
                        at_uri,
                        ref.get("did"),
                        rkey if at_uri else None,
                    ),
                )
            self.conn.commit()
        return True

    def get_dead_count(self):
        """Retourne le nombre de liens morts (thread-safe)."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM posts WHERE status != 'ok'")
            return cursor.fetchone()[0]

    def get_dead_posts(self):
        """Retourne la liste des URLs avec un statut non-ok (thread-safe)."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT url, status FROM posts WHERE status != 'ok'")
            return cursor.fetchall()

    def cleanup_dead_posts(self):
        """Supprime les posts marqués 'deleted' ou 'blocked' de la DB (thread-safe).

        Les médias associés sont supprimés par ON DELETE CASCADE.

        Returns:
            int: nombre de posts supprimés
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM posts WHERE status IN ('deleted', 'blocked')")
            count = cursor.fetchone()[0]
            cursor.execute("DELETE FROM posts WHERE status IN ('deleted', 'blocked')")
            self.conn.commit()
            return count

    def close(self):
        """Ferme la connexion."""
        self.conn.close()
