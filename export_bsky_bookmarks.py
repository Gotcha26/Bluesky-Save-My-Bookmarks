import requests
import time
import sys
import traceback
from pathlib import Path

print("=== Export des bookmarks Bluesky ===")

API = "https://shiitake.us-east.host.bsky.network/xrpc/app.bsky.bookmark.getBookmarks"
TOKEN_FILE = Path("Token-Bearer.txt")

# --- Lecture du token ---
if not TOKEN_FILE.exists():
    print("❌ Fichier Token-Bearer.txt introuvable")
    input("Appuie sur Entrée pour quitter...")
    sys.exit(1)

TOKEN = TOKEN_FILE.read_text(encoding="utf-8").strip()

if not TOKEN.startswith("Bearer "):
    print("❌ Le token doit commencer par 'Bearer '")
    input("Appuie sur Entrée pour quitter...")
    sys.exit(1)

cursor = None
urls = []

# --- Limite pages vides ---
MAX_EMPTY_PAGES = 5
empty_pages = 0

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

        r = session.get(API, params=params, timeout=20)
        print(f"  HTTP {r.status_code}")

        if r.status_code != 200:
            print("⚠️ Contenu brut serveur :")
            print(r.text)
            r.raise_for_status()

        data = r.json()
        bookmarks = data.get("bookmarks", [])

        print(f"  {len(bookmarks)} bookmarks reçus")

        if len(bookmarks) == 0:
            empty_pages += 1
            if empty_pages >= MAX_EMPTY_PAGES:
                print(f"⚠️ {MAX_EMPTY_PAGES} pages consécutives sans bookmark. Arrêt.")
                break
        else:
            empty_pages = 0  # reset compteur

        for bm in bookmarks:
            item = bm.get("item", {})
            uri = item.get("uri") or bm.get("subject", {}).get("uri")
            if not uri:
                continue

            parts = uri.split("/")
            if len(parts) < 5:
                continue

            rkey = parts[4]

            # --- Utilisation du handle si disponible ---
            author_handle = item.get("author", {}).get("handle")
            if author_handle:
                urls.append(f"https://bsky.app/profile/{author_handle}/post/{rkey}")
            else:
                # fallback DID si handle manquant
                did = parts[2]
                urls.append(f"https://bsky.app/profile/{did}/post/{rkey}")

        cursor = data.get("cursor")
        if not cursor:
            print("\n✓ Fin de la pagination")
            break

        page += 1
        time.sleep(0.2)

except Exception as e:
    print("\n❌ ERREUR CRITIQUE")
    print(str(e))
    print("\n--- Détails techniques ---")
    traceback.print_exc()

finally:
    with open("urls.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(urls))

    print(f"\n✔ Export terminé : {len(urls)} liens écrits dans urls.txt")
    print("\n=== Fin du script ===")
    input("Appuie sur Entrée pour fermer la fenêtre...")
