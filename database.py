#!/usr/bin/env python3
"""Gestion de la base de données SQLite pour tracking"""
import sqlite3
from datetime import datetime

class Database:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
    
    def _init_schema(self):
        """Création des tables"""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS posts (
                url TEXT PRIMARY KEY,
                post_id TEXT NOT NULL,
                handle TEXT,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_check TEXT
            );
            
            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_url TEXT NOT NULL,
                media_type TEXT NOT NULL,
                filename TEXT NOT NULL,
                downloaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_url) REFERENCES posts(url),
                UNIQUE(post_url, filename)
            );
            
            CREATE INDEX IF NOT EXISTS idx_posts_handle ON posts(handle);
            CREATE INDEX IF NOT EXISTS idx_media_post ON media(post_url);
        """)
        self.conn.commit()
    
    def add_post(self, url, post_id, handle=None):
        """Ajoute un post (ignore si existe)"""
        self.conn.execute(
            "INSERT OR IGNORE INTO posts (url, post_id, handle) VALUES (?, ?, ?)",
            (url, post_id, handle)
        )
        self.conn.commit()
    
    def get_new_posts(self, urls):
        """Retourne les URLs non présentes en DB"""
        placeholders = ",".join("?" * len(urls))
        cursor = self.conn.execute(
            f"SELECT url FROM posts WHERE url IN ({placeholders})",
            urls
        )
        existing = {row["url"] for row in cursor}
        return [u for u in urls if u not in existing]
    
    def mark_media_downloaded(self, post_url, media_type, filename):
        """Marque un média comme téléchargé"""
        self.conn.execute(
            "INSERT OR IGNORE INTO media (post_url, media_type, filename) VALUES (?, ?, ?)",
            (post_url, media_type, filename)
        )
        self.conn.commit()
    
    def is_media_downloaded(self, post_url, filename):
        """Vérifie si un média a déjà été téléchargé"""
        cursor = self.conn.execute(
            "SELECT 1 FROM media WHERE post_url = ? AND filename = ?",
            (post_url, filename)
        )
        return cursor.fetchone() is not None
    
    def update_last_check(self, url):
        """Met à jour la date de dernière vérification"""
        self.conn.execute(
            "UPDATE posts SET last_check = ? WHERE url = ?",
            (datetime.now().isoformat(), url)
        )
        self.conn.commit()
    
    def get_stats(self):
        """Statistiques de la base"""
        posts = self.conn.execute("SELECT COUNT(*) as c FROM posts").fetchone()["c"]
        images = self.conn.execute("SELECT COUNT(*) as c FROM media WHERE media_type='image'").fetchone()["c"]
        videos = self.conn.execute("SELECT COUNT(*) as c FROM media WHERE media_type='video'").fetchone()["c"]
        return {"posts": posts, "images": images, "videos": videos}
    
    def close(self):
        self.conn.close()