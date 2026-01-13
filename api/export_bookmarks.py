#!/usr/bin/env python3
"""Export des bookmarks Bluesky"""
import requests
import time
import sys
import traceback
from pathlib import Path

print("=== [API] Export des bookmarks Bluesky ===")

API = "https://shiitake.us-east.host.bsky.network/xrpc/app.bsky.bookmark.getBookmarks"
TOKEN_FILE = Path("Token-Bearer.txt")

# --- Lecture du token ---
if not TOKEN_FILE.exists():
    print("❌ Fichier Token-Bearer.txt introuvable")
    sys.exit(1)

TOKEN = TOKEN_FILE.read_text(encoding="utf-8").strip()

if not TOKEN.startswith("Bearer "):
    print("❌ Le token doit commencer par 'Bearer '")
    sys.exit(1)

cursor = None
urls = []
exit_code = 0

try:
    session = requests.Session()
    session.headers.update({
        "Authorization": TOKEN,
        "Accept": "application/json",
        "atproto-proxy": "did:web:api.bsky.app#bsky_appview"
    })

    page = 1

    while True:
        print(f"\n→ Requête page {page}...")

        params = {"limit": 100}
        if cursor:
            params["cursor"] = cursor

        try:
            r = session.get(API, params=params, timeout=20)
            print(f"  HTTP {r.status_code}")

            if r.status_code == 400:
                error_data = r.json()
                error_type = error_data.get("error", "")
                error_msg = error_data.get("message", "")
                
                if error_type == "ExpiredToken" or "expired" in error_msg.lower():
                    print("\n❌ TOKEN EXPIRÉ")
                    print("   Le token Bearer a expiré ou est invalide.")
                    print("👉 Récupérez un nouveau token (voir Instructions-token.md) : \nhttps://github.com/Gotcha26/Bluesky-Save-My-Bookmarks/Instructions-token.md")
                    exit_code = 1
                    break
                else:
                    print(f"⚠️ Erreur API : {error_msg}")
                    r.raise_for_status()
            
            r.raise_for_status()
            
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Erreur réseau : {e}")
            exit_code = 1
            break

        data = r.json()
        bookmarks = data.get("bookmarks", [])

        print(f"  {len(bookmarks)} bookmarks reçus")

        if len(bookmarks) == 0:
            print("✓ Page vide détectée, fin de l'export")
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

        cursor = data.get("cursor")
        if not cursor:
            print("\n✓ Fin de la pagination (pas de cursor)")
            break

        page += 1
        time.sleep(0.2)

except Exception as e:
    print("\n❌ ERREUR CRITIQUE")
    print(str(e))
    print("\n--- Détails techniques ---")
    traceback.print_exc()
    exit_code = 1

finally:
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
        f.write("\n".join(urls))

    print(f"\n✔  Export terminé : {len(urls)} liens écrits dans urls.txt")
    print("\n=== Fin du script API ===")
    
    sys.exit(exit_code)