#!/usr/bin/env python3
"""
Cache de la dernière réponse complète de getBookmarks (`bookmarks.json`).

Chaque entrée garde le `postView` brut renvoyé par l'API : l'analyse d'un post peut
alors se faire sans requête (issue #3) et la réponse reste exploitable hors ligne.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def save_cache(path, posts, pds_url=""):
    """
    Écrit le cache (remplacement atomique : fichier temporaire puis renommage).

    Args:
        path: chemin du fichier (str ou Path)
        posts: entrées {at_uri, did, rkey, handle, url, item_type, post_view, created_at}
        pds_url: PDS du compte au moment de la synchronisation

    Raises:
        OSError: écriture impossible
    """
    chemin = Path(path)
    contenu = {
        "saved_at": datetime.now().isoformat(),
        "pds_url": pds_url or "",
        "posts": list(posts),
    }
    temporaire = chemin.with_name(chemin.name + ".tmp")
    try:
        temporaire.write_text(json.dumps(contenu, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temporaire, chemin)
    finally:
        temporaire.unlink(missing_ok=True)


def post_views_index(cache):
    """
    Index des `postView` d'un cache chargé : {url: post_view} et {at_uri: post_view}
    (les deux clés pointent vers la même vue). Les entrées sans `postView` sont omises.
    """
    index = {}
    for at_uri, entree in cache.items():
        vue = entree.get("post_view")
        if not vue:
            continue
        index[at_uri] = vue
        if entree.get("url"):
            index[entree["url"]] = vue
    return index


def load_cache(path):
    """
    Lit le cache.

    Returns:
        dict: {at_uri: entrée}. Vide si le fichier est absent, illisible ou de
        structure inattendue (ce dernier cas est signalé sur stderr).
    """
    chemin = Path(path)
    if not chemin.exists():
        return {}
    try:
        contenu = json.loads(chemin.read_text(encoding="utf-8"))
        posts = contenu["posts"]
        if not isinstance(posts, list):
            raise ValueError("« posts » n'est pas une liste")
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"[CACHE] {chemin.name} illisible, ignoré : {e}", file=sys.stderr)
        return {}
    return {p["at_uri"]: p for p in posts if isinstance(p, dict) and p.get("at_uri")}
