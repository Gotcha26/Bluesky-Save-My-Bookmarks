#!/usr/bin/env python3
"""Export des bookmarks Bluesky — module importable et script standalone."""

import json
import os
import sys
import time
from pathlib import Path

import requests

# Permet `python api/export_bookmarks.py` (le dossier du script est alors seul dans sys.path)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import http as bsmb_http  # noqa: E402
from core.post_ref import PostRef  # noqa: E402

DEFAULT_PDS_URL = "https://bsky.social"


def _item_type(item):
    """
    Forme de l'`item` d'un bookmarkView : "postView", "notFoundPost" ou "blockedPost"
    (suffixe de `$type` après `#`). Sans `$type`, un item portant un `record` est un
    postView ; sinon la forme est "unknown" (traitée comme un post ordinaire).
    """
    suffixe = str(item.get("$type", "")).rpartition("#")[2]
    if suffixe:
        return suffixe
    return "postView" if item.get("record") else "unknown"


def fetch_bookmarks(token, on_progress=None, pds_url=DEFAULT_PDS_URL, session=None):
    """
    Récupère tous les bookmarks depuis l'API Bluesky.

    Args:
        token: Token complet "Bearer xxx"
        on_progress: callback(page, count) optionnel pour suivre la progression
        pds_url: PDS du compte (le token n'est valable que sur celui-ci)
        session: session HTTP (défaut : session partagée de core.http)

    Returns:
        dict: {
            "urls": list[str],   # URLs de bookmarks (handle valide, sinon DID)
            "posts": list[dict], # par bookmark : {"at_uri", "did", "rkey", "handle", "url",
                                 #   "item_type" ("postView"/"notFoundPost"/"blockedPost"),
                                 #   "post_view" (dict brut, None si pas postView), "created_at"}
            "count": int,        # Nombre total de bookmarks
            "pages": int,        # Nombre de pages parcourues
            "error": str|None,   # Message d'erreur si échec
            "expired": bool      # True si le token a expiré
        }
    """
    if not token or not token.startswith("Bearer "):
        return {
            "urls": [],
            "posts": [],
            "count": 0,
            "pages": 0,
            "error": "Token invalide (doit commencer par 'Bearer ')",
            "expired": False,
        }

    api_url = f"{(pds_url or DEFAULT_PDS_URL).rstrip('/')}/xrpc/app.bsky.bookmark.getBookmarks"
    cursor = None
    urls = []
    posts = []
    page = 0

    try:
        # Session partagée (reprises, limiteur) : les en-têtes d'authentification sont
        # passés par requête, jamais posés sur la session commune.
        session = session or bsmb_http.get_session()
        en_tetes = {
            "Authorization": token,
            "Accept": "application/json",
            "atproto-proxy": "did:web:api.bsky.app#bsky_appview",
        }

        while True:
            page += 1

            params = {"limit": 100}
            if cursor:
                params["cursor"] = cursor

            try:
                r = session.get(api_url, params=params, headers=en_tetes, timeout=20)

                if r.status_code == 400:
                    error_data = r.json()
                    error_type = error_data.get("error", "")
                    error_msg = error_data.get("message", "")

                    if error_type == "ExpiredToken" or "expired" in error_msg.lower():
                        return {
                            "urls": urls,
                            "posts": posts,
                            "count": len(urls),
                            "pages": page,
                            "error": "Token expiré",
                            "expired": True,
                        }
                    else:
                        return {
                            "urls": urls,
                            "posts": posts,
                            "count": len(urls),
                            "pages": page,
                            "error": f"Erreur API : {error_msg}",
                            "expired": False,
                        }

                r.raise_for_status()

            except requests.exceptions.RequestException as e:
                return {
                    "urls": urls,
                    "posts": posts,
                    "count": len(urls),
                    "pages": page,
                    "error": f"Erreur réseau : {e}",
                    "expired": False,
                }

            data = r.json()
            bookmarks = data.get("bookmarks", [])

            if len(bookmarks) == 0:
                break

            for bm in bookmarks:
                item = bm.get("item", {})
                uri = bm.get("subject", {}).get("uri") or item.get("uri")
                if not uri:
                    continue

                handle = item.get("author", {}).get("handle")
                try:
                    ref = PostRef.from_at_uri(uri, handle=handle)
                except ValueError:
                    continue

                item_type = _item_type(item)
                urls.append(ref.web_url)
                posts.append(
                    {
                        "at_uri": ref.at_uri,
                        "did": ref.did,
                        "rkey": ref.rkey,
                        "handle": handle,
                        "url": ref.web_url,
                        "item_type": item_type,
                        "post_view": item if item_type == "postView" else None,
                        "created_at": bm.get("createdAt"),
                    }
                )

            if on_progress:
                on_progress(page, len(urls))

            cursor = data.get("cursor")
            if not cursor:
                break

            time.sleep(0.2)

    except Exception as e:
        return {
            "urls": urls,
            "posts": posts,
            "count": len(urls),
            "pages": page,
            "error": f"Erreur critique : {e}",
            "expired": False,
        }

    return {
        "urls": urls,
        "posts": posts,
        "count": len(urls),
        "pages": page,
        "error": None,
        "expired": False,
    }


# === Mode standalone (rétrocompatibilité subprocess) ===

if __name__ == "__main__":
    print("=== [API] Export des bookmarks Bluesky ===")

    # --- Lecture du token ---
    TOKEN = os.environ.get("BSMB_TOKEN", "").strip()

    if not TOKEN:
        TOKEN_FILE = Path("Token-Bearer.txt")
        if TOKEN_FILE.exists():
            TOKEN = TOKEN_FILE.read_text(encoding="utf-8").strip()
        else:
            print("[ERREUR] Aucun token disponible")
            print("  Variable BSMB_TOKEN non définie et Token-Bearer.txt introuvable")
            sys.exit(1)

    if not TOKEN.startswith("Bearer "):
        print("[ERREUR] Le token doit commencer par 'Bearer '")
        sys.exit(1)

    # --- PDS : BSMB_PDS_URL, sinon config.json (pds_url), sinon bsky.social ---
    PDS_URL = os.environ.get("BSMB_PDS_URL", "").strip()
    if not PDS_URL and Path("config.json").exists():
        try:
            PDS_URL = str(
                json.loads(Path("config.json").read_text(encoding="utf-8")).get("pds_url") or ""
            ).strip()
        except (OSError, ValueError):
            PDS_URL = ""
    PDS_URL = PDS_URL or DEFAULT_PDS_URL

    def progress_callback(page, count):
        print(f"\n→ Page {page}... ({count} bookmarks récupérés)")

    result = fetch_bookmarks(TOKEN, on_progress=progress_callback, pds_url=PDS_URL)

    if result["error"]:
        if result["expired"]:
            print("\n❌ TOKEN EXPIRÉ")
            print("   Le token Bearer a expiré ou est invalide.")
            print("👉 Récupérez un nouveau token (voir ADVANCED.md, « Token Bearer manuel »)")
        else:
            print(f"\n❌ {result['error']}")

    # Sauvegarder l'ancien urls.txt si existant
    urls_file = Path("urls.txt")
    if urls_file.exists():
        backup_file = Path("urls.txt.bak")
        try:
            backup_file.write_text(urls_file.read_text(encoding="utf-8"), encoding="utf-8")
            print("\n✅ Sauvegarde créée : urls.txt.bak")
        except Exception as e:
            print(f"  ⚠️ Impossible de créer la sauvegarde : {e}")

    # Écrire le nouveau fichier
    with open("urls.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(result["urls"]))

    print(f"\n✔  Export terminé : {result['count']} liens écrits dans urls.txt")
    print("\n=== Fin du script API ===")

    sys.exit(1 if result["error"] else 0)
