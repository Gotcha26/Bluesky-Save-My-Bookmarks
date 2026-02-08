#!/usr/bin/env python3
"""
Gestion de la base de données SQLite pour BSMB
"""
import sqlite3
import threading
from pathlib import Path
from datetime import datetime

class Database:
    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self._lock = threading.Lock()
        self._init_db()
    
    def _init_db(self):
        """Initialise les tables et applique les migrations."""
        cursor = self.conn.cursor()

        # Table des posts trackés
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                url TEXT PRIMARY KEY,
                post_id TEXT,
                handle TEXT,
                added_at TEXT,
                last_check TEXT,
                status TEXT DEFAULT 'ok'
            )
        ''')

        # Table des médias téléchargés
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_url TEXT,
                media_type TEXT,
                filename TEXT,
                downloaded_at TEXT,
                FOREIGN KEY(post_url) REFERENCES posts(url)
            )
        ''')

        self.conn.commit()

        # Migration : ajouter colonne status si absente (DB existantes)
        columns = [row[1] for row in cursor.execute('PRAGMA table_info(posts)').fetchall()]
        if 'status' not in columns:
            cursor.execute("ALTER TABLE posts ADD COLUMN status TEXT DEFAULT 'ok'")
            self.conn.commit()
    
    def add_post(self, url, post_id=None, handle=None):
        """Ajoute un post à la DB (thread-safe)."""
        with self._lock:
            cursor = self.conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute('''
                INSERT OR REPLACE INTO posts (url, post_id, handle, added_at, last_check)
                VALUES (?, ?, ?, ?, ?)
            ''', (url, post_id, handle, now, now))
            self.conn.commit()

    def add_media(self, post_url, media_type, filename):
        """Ajoute un média téléchargé à la DB (thread-safe).

        Args:
            post_url: URL du post
            media_type: 'image' ou 'video'
            filename: Nom du fichier téléchargé
        """
        with self._lock:
            cursor = self.conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute('''
                INSERT INTO media (post_url, media_type, filename, downloaded_at)
                VALUES (?, ?, ?, ?)
            ''', (post_url, media_type, filename, now))
            self.conn.commit()

    def update_last_check(self, url):
        """Met à jour la date de dernière vérification d'un post (thread-safe)."""
        with self._lock:
            cursor = self.conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute('''
                UPDATE posts SET last_check = ? WHERE url = ?
            ''', (now, url))
            self.conn.commit()

    def get_new_posts(self, urls):
        """Retourne les URLs non trackées (thread-safe)."""
        with self._lock:
            cursor = self.conn.cursor()
            new_posts = []
            for url in urls:
                cursor.execute('SELECT url FROM posts WHERE url = ?', (url,))
                if not cursor.fetchone():
                    new_posts.append(url)
            return new_posts

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
            cursor.execute('SELECT COUNT(*) FROM posts')
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
                'posts': posts_count,
                'images': images_count,
                'videos': videos_count,
                'texts': texts_count,
                'dead': dead_count,
            }

    def mark_post_status(self, url, status):
        """Met à jour le statut d'un post (thread-safe).

        Args:
            url: URL du post
            status: 'ok', 'deleted', 'error_500', 'unknown'
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('UPDATE posts SET status = ? WHERE url = ?', (status, url))
            self.conn.commit()

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
        """Supprime les posts marqués 'deleted' de la DB (thread-safe).

        Returns:
            int: nombre de posts supprimés
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM posts WHERE status = 'deleted'")
            count = cursor.fetchone()[0]
            cursor.execute("DELETE FROM media WHERE post_url IN (SELECT url FROM posts WHERE status = 'deleted')")
            cursor.execute("DELETE FROM posts WHERE status = 'deleted'")
            self.conn.commit()
            return count

    def close(self):
        """Ferme la connexion."""
        self.conn.close()