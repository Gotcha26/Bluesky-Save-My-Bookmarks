#!/usr/bin/env python3
"""Export des bookmarks Bluesky — module importable et script standalone."""
import os
import requests
import time
import sys
import traceback
from pathlib import Path

API = "https://shiitake.us-east.host.bsky.network/xrpc/app.bsky.bookmark.getBookmarks"


def fetch_bookmarks(token, on_progress=None):
    """
    Récupère tous les bookmarks depuis l'API Bluesky.

    Args:
        token: Token complet "Bearer xxx"
        on_progress: callback(page, count) optionnel pour suivre la progression

    Returns:
        dict: {
            "urls": list[str],   # Liste des URLs de bookmarks
            "count": int,        # Nombre total de bookmarks
            "pages": int,        # Nombre de pages parcourues
            "error": str|None,   # Message d'erreur si échec
            "expired": bool      # True si le token a expiré
        }
    """
    if not token or not token.startswith("Bearer "):
        return {
            "urls": [],
            "count": 0,
            "pages": 0,
            "error": "Token invalide (doit commencer par 'Bearer ')",
            "expired": False,
        }

    cursor = None
    urls = []
    page = 0

    try:
        session = requests.Session()
        session.headers.update({
            "Authorization": token,
            "Accept": "application/json",
            "atproto-proxy": "did:web:api.bsky.app#bsky_appview",
        })

        while True:
            page += 1

            params = {"limit": 100}
            if cursor:
                params["cursor"] = cursor

            try:
                r = session.get(API, params=params, timeout=20)

                if r.status_code == 400:
                    error_data = r.json()
                    error_type = error_data.get("error", "")
                    error_msg = error_data.get("message", "")

                    if error_type == "ExpiredToken" or "expired" in error_msg.lower():
                        return {
                            "urls": urls,
                            "count": len(urls),
                            "pages": page,
                            "error": "Token expiré",
                            "expired": True,
                        }
                    else:
                        return {
                            "urls": urls,
                            "count": len(urls),
                            "pages": page,
                            "error": f"Erreur API : {error_msg}",
                            "expired": False,
                        }

                r.raise_for_status()

            except requests.exceptions.RequestException as e:
                return {
                    "urls": urls,
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
                uri = item.get("uri") or bm.get("subject", {}).get("uri")
                if not uri:
                    continue

                parts = uri.split("/")
                if len(parts) < 5:
                    continue

                rkey = parts[4]
                author_handle = item.get("author", {}).get("handle")
                if author_handle:
                    urls.append(f"https://bsky.app/profile/{author_handle}/post/{rkey}")
                else:
                    did = parts[2]
                    urls.append(f"https://bsky.app/profile/{did}/post/{rkey}")

            if on_progress:
                on_progress(page, len(urls))

            cursor = data.get("cursor")
            if not cursor:
                break

            time.sleep(0.2)

    except Exception as e:
        return {
            "urls": urls,
            "count": len(urls),
            "pages": page,
            "error": f"Erreur critique : {e}",
            "expired": False,
        }

    return {
        "urls": urls,
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

    def progress_callback(page, count):
        print(f"\n→ Page {page}... ({count} bookmarks récupérés)")

    result = fetch_bookmarks(TOKEN, on_progress=progress_callback)

    if result["error"]:
        if result["expired"]:
            print(f"\n❌ TOKEN EXPIRÉ")
            print("   Le token Bearer a expiré ou est invalide.")
            print("👉 Récupérez un nouveau token (voir Instructions-token.md)")
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
