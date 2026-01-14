#!/usr/bin/env python3
"""
Gestion de la base de données SQLite pour BSMB
"""
import sqlite3
from pathlib import Path
from datetime import datetime

class Database:
    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = sqlite3.connect(db_file)
        self._init_db()
    
    def _init_db(self):
        """Initialise les tables"""
        cursor = self.conn.cursor()
        
        # Table des posts trackés
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                url TEXT PRIMARY KEY,
                post_id TEXT,
                handle TEXT,
                added_at TEXT,
                last_check TEXT
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
    
    def add_post(self, url, post_id=None, handle=None):
        """Ajoute un post à la DB"""
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT OR REPLACE INTO posts (url, post_id, handle, added_at, last_check)
            VALUES (?, ?, ?, ?, ?)
        ''', (url, post_id, handle, now, now))
        
        self.conn.commit()
    
    def add_media(self, post_url, media_type, filename):
        """Ajoute un média téléchargé à la DB
        
        Args:
            post_url: URL du post
            media_type: 'image' ou 'video'
            filename: Nom du fichier téléchargé
        """
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO media (post_url, media_type, filename, downloaded_at)
            VALUES (?, ?, ?, ?)
        ''', (post_url, media_type, filename, now))
        
        self.conn.commit()

    def update_last_check(self, url):
        """Met à jour la date de dernière vérification d'un post"""
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        
        cursor.execute('''
            UPDATE posts SET last_check = ? WHERE url = ?
        ''', (now, url))
        
        self.conn.commit()
    
    def get_new_posts(self, urls):
        """Retourne les URLs non trackées"""
        cursor = self.conn.cursor()
        new_posts = []
        
        for url in urls:
            cursor.execute('SELECT url FROM posts WHERE url = ?', (url,))
            if not cursor.fetchone():
                new_posts.append(url)
        
        return new_posts
    
    def get_stats(self):
        """Retourne les statistiques
        
        Returns:
            dict: {
                'posts': nombre de posts trackés,
                'images': nombre d'images téléchargées,
                'videos': nombre de vidéos téléchargées
            }
        """
        cursor = self.conn.cursor()
        
        # Nombre de posts trackés
        cursor.execute('SELECT COUNT(*) FROM posts')
        posts_count = cursor.fetchone()[0]
        
        # Nombre d'images téléchargées
        cursor.execute("SELECT COUNT(*) FROM media WHERE media_type = 'image'")
        images_count = cursor.fetchone()[0]
        
        # Nombre de vidéos téléchargées
        cursor.execute("SELECT COUNT(*) FROM media WHERE media_type = 'video'")
        videos_count = cursor.fetchone()[0]
        
        return {
            'posts': posts_count,
            'images': images_count,
            'videos': videos_count
        }
    
    def close(self):
        """Ferme la connexion"""
        self.conn.close()