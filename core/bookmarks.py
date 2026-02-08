#!/usr/bin/env python3
"""
Synchronisation des bookmarks Bluesky.
Pont entre l'API (export_bookmarks) et la base de données locale.
"""
from datetime import datetime
from pathlib import Path

from api.export_bookmarks import fetch_bookmarks
from core.config import save_config


class BookmarkSync:
    """Gère la synchronisation entre les bookmarks en ligne et la DB locale."""

    def __init__(self, config, db):
        self.config = config
        self.db = db
        self._online_urls = None

    def sync(self, token, on_progress=None):
        """
        Synchronise : récupère les bookmarks en ligne et compare avec la DB.

        Args:
            token: "Bearer xxx"
            on_progress: callback(page, count) optionnel

        Returns:
            dict: {
                "error": str|None,
                "expired": bool,
                "online_count": int,
                "local_count": int,
                "new_count": int,
                "new_urls": list[str],
                "dead_count": int,
            }
        """
        result = fetch_bookmarks(token, on_progress)

        if result["error"]:
            return {
                "error": result["error"],
                "expired": result["expired"],
                "online_count": 0,
                "local_count": self.db.get_stats()["posts"],
                "new_count": 0,
                "new_urls": [],
                "dead_count": self.db.get_dead_count(),
            }

        self._online_urls = result["urls"]
        new_urls = self.db.get_new_posts(result["urls"])

        # Sauvegarder dans urls.txt (rétrocompatibilité)
        urls_file = Path(self.config["urls_file"])
        urls_file.write_text("\n".join(result["urls"]), encoding="utf-8")

        # Mettre à jour last_sync
        self.config["last_sync"] = datetime.now().isoformat()
        save_config(self.config)

        stats = self.db.get_stats()

        return {
            "error": None,
            "expired": False,
            "online_count": result["count"],
            "local_count": stats["posts"],
            "new_count": len(new_urls),
            "new_urls": new_urls,
            "dead_count": stats["dead"],
        }

    def get_cached_state(self):
        """
        Retourne l'état actuel sans refaire d'appel API.
        Lit depuis urls.txt si disponible.

        Returns:
            dict: {
                "online_count": int (depuis urls.txt) ou 0,
                "local_count": int,
                "new_count": int,
                "dead_count": int,
                "last_sync": str (ISO datetime) ou "",
                "has_cache": bool,
            }
        """
        stats = self.db.get_stats()

        urls_file = Path(self.config["urls_file"])
        online_count = 0
        new_count = 0
        has_cache = False

        if urls_file.exists() and urls_file.stat().st_size > 0:
            with open(urls_file, "r", encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip()]
            online_count = len(urls)
            new_urls = self.db.get_new_posts(urls)
            new_count = len(new_urls)
            has_cache = True

        return {
            "online_count": online_count,
            "local_count": stats["posts"],
            "new_count": new_count,
            "dead_count": stats["dead"],
            "last_sync": self.config.get("last_sync", ""),
            "has_cache": has_cache,
        }
