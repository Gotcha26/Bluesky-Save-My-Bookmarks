#!/usr/bin/env python3
"""
Synchronisation des bookmarks Bluesky.
Pont entre l'API (export_bookmarks) et la base de données locale.
"""

from datetime import datetime

from api.export_bookmarks import DEFAULT_PDS_URL, fetch_bookmarks
from core.auth import AuthError, NetworkError, refresh_session
from core.bookmarks_cache import load_cache, post_views_index, save_cache
from core.config import resolve_path, save_config

# Statut posé d'emblée selon la forme de l'item renvoyé par getBookmarks
_STATUT_PAR_TYPE = {"notFoundPost": "deleted", "blockedPost": "blocked"}


def read_urls(config):
    """URLs de urls.txt (liste vide si le fichier est absent)."""
    urls_file = resolve_path(config, "urls_file")
    if not urls_file.exists():
        return []
    with open(urls_file, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def pending_downloads(config, db):
    """
    Posts à télécharger (nouveaux ou à retenter) : source unique du téléchargement
    (menu, CLI) et du compteur « Nouveaux ».

    Avec le cache des bookmarks (`bookmarks.json`), les posts sont comparés à la base
    par AT-URI (`get_pending_refs`) : un changement de handle ne déclenche aucun
    retéléchargement ; les `notFoundPost` / `blockedPost` sont exclus. Sans cache, repli
    sur urls.txt comparé par URL (`get_pending_posts`).

    Returns:
        tuple: (URLs à traiter, {URL ou AT-URI: postView} du cache, {} sans cache)
    """
    retry_after_days = config.get("retry_after_days", 7)
    cache = load_cache(resolve_path(config, "bookmarks_cache"))
    if cache:
        vivants = [p for p in cache.values() if p.get("item_type") not in _STATUT_PAR_TYPE and p.get("url")]
        urls = [p["url"] for p in db.get_pending_refs(vivants, retry_after_days)]
        return urls, post_views_index(cache)
    return db.get_pending_posts(read_urls(config), retry_after_days), {}


def run_sync(config, db, session_info, on_progress=None):
    """
    Synchronisation commune au menu et à la CLI (les appelants ne gardent que l'affichage) :
    mémorise le PDS du compte dans la config s'il a changé, puis lance BookmarkSync.sync.

    Args:
        session_info: dict de core.auth.get_session() ({"token", "refresh_jwt", "did", "pds_url"})
        on_progress: callback(page, count) optionnel

    Returns:
        dict: résultat de BookmarkSync.sync()
    """
    pds_url = session_info.get("pds_url")
    if pds_url and config.get("pds_url") != pds_url:
        config["pds_url"] = pds_url
        save_config(config)
    return BookmarkSync(config, db).sync(
        session_info["token"], on_progress=on_progress, session_info=session_info
    )


class BookmarkSync:
    """Gère la synchronisation entre les bookmarks en ligne et la DB locale."""

    def __init__(self, config, db):
        self.config = config
        self.db = db
        self._online_urls = None

    def sync(self, token, on_progress=None, session_info=None):
        """
        Synchronise : récupère les bookmarks en ligne et compare avec la DB.

        Args:
            token: "Bearer xxx"
            on_progress: callback(page, count) optionnel
            session_info: dict de core.auth.get_session() (optionnel). Si l'export renvoie
                `expired` et qu'il porte un `refresh_jwt`, le token est renouvelé UNE fois
                (refreshSession) et l'export relancé depuis la page 1 (la progression
                repart de zéro) ; le dict est mis à jour en place. Un échec réseau du
                renouvellement donne `expired=False` et une erreur réseau.

        Returns:
            dict: {
                "error": str|None,
                "expired": bool,
                "online_count": int,
                "local_count": int,
                "new_count": int,
                "new_urls": list[str],
                "dead_count": int,
                "cache_error": str|None,   # échec d'écriture de bookmarks.json
            }

        Les bookmarks `notFoundPost` / `blockedPost` sont enregistrés tout de suite
        (statuts `deleted` / `blocked`) et ne comptent pas dans `new_count`.
        """
        pds_url = self.config.get("pds_url") or DEFAULT_PDS_URL
        result = fetch_bookmarks(token, on_progress, pds_url=pds_url)

        # Token d'accès expiré (~2 h) pendant une longue synchro : un seul renouvellement
        if result["error"] and result["expired"] and (session_info or {}).get("refresh_jwt"):
            try:
                nouvelle = refresh_session(session_info["refresh_jwt"], pds_url)
            except NetworkError as e:
                # Panne réseau pendant le renouvellement : erreur réseau, pas « token expiré »
                result = {
                    **result,
                    "error": f"Erreur réseau pendant le renouvellement de la session : {e}",
                    "expired": False,
                }
            except AuthError:
                pass  # jeton de rafraîchissement refusé : on rend le résultat « expiré » d'origine
            else:
                session_info.update(nouvelle)
                result = fetch_bookmarks(nouvelle["token"], on_progress, pds_url=pds_url)

        if result["error"]:
            return {
                "error": result["error"],
                "expired": result["expired"],
                "online_count": 0,
                "local_count": self.db.get_stats()["posts"],
                "new_count": 0,
                "new_urls": [],
                "dead_count": self.db.get_dead_count(),
                "cache_error": None,
            }

        self._online_urls = result["urls"]

        # Cache de la réponse complète (postView bruts) : un échec ne bloque pas la synchro
        cache_error = None
        try:
            save_cache(resolve_path(self.config, "bookmarks_cache"), result["posts"], pds_url=pds_url)
        except OSError as e:
            cache_error = str(e)

        # L'API dit elle-même qu'un post est supprimé ou bloqué : inutile de le re-télécharger
        morts = [p for p in result["posts"] if p.get("item_type") in _STATUT_PAR_TYPE]
        for post in morts:
            self.db.mark_unavailable(post, _STATUT_PAR_TYPE[post["item_type"]])

        retry_after_days = self.config.get("retry_after_days", 7)
        vivants = [p for p in result["posts"] if p.get("item_type") not in _STATUT_PAR_TYPE]
        new_urls = [p["url"] for p in self.db.get_pending_refs(vivants, retry_after_days)]

        # Sauvegarder dans urls.txt (rétrocompatibilité)
        urls_file = resolve_path(self.config, "urls_file")
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
            "cache_error": cache_error,
        }

    def get_cached_state(self):
        """
        Retourne l'état actuel sans refaire d'appel API.
        Lit depuis bookmarks.json s'il existe (online_count et new_count décrivent alors la même
        liste), sinon depuis urls.txt.

        Returns:
            dict: {
                "online_count": int (depuis le cache ou urls.txt) ou 0,
                "local_count": int,
                "new_count": int,
                "dead_count": int,
                "last_sync": str (ISO datetime) ou "",
                "has_cache": bool,
            }
        """
        stats = self.db.get_stats()

        online_count = 0
        has_cache = False
        cache = load_cache(resolve_path(self.config, "bookmarks_cache"))

        if cache:
            # Même liste pour les deux chiffres : celle de la dernière synchro
            online_count = len(cache)
            has_cache = True
        else:
            online_count = len(read_urls(self.config))
            has_cache = online_count > 0
        # « Nouveaux » : exactement ce que le téléchargement traitera
        new_count = len(pending_downloads(self.config, self.db)[0])

        return {
            "online_count": online_count,
            "local_count": stats["posts"],
            "new_count": new_count,
            "dead_count": stats["dead"],
            "last_sync": self.config.get("last_sync", ""),
            "has_cache": has_cache,
        }
