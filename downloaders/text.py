#!/usr/bin/env python3
"""
bsky_text_downloader.py
Sauvegarde le texte des posts sans média
Exit codes: 0=succès, 1=erreur, 2=pas de texte
"""
import os
import sys
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path
import requests

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Charger config si disponible
from core.config import get_default_paths

default_paths = get_default_paths()

TEXT_DIR = os.path.join(os.path.dirname(default_paths["img_dir"]), "texts")
os.makedirs(TEXT_DIR, exist_ok=True)

if len(sys.argv) > 1:
    url = sys.argv[1]
else:
    url = input("👉 URL : ").strip()

def fetch_post(handle, post_id):
    api_url = f"https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri=at://{handle}/app.bsky.feed.post/{post_id}"
    resp = requests.get(api_url, timeout=15)
    resp.raise_for_status()
    return resp.json()

def save_text(post_url):
    parts = urlparse(post_url).path.strip("/").split("/")
    if len(parts) < 4:
        return False
    
    handle = parts[1]
    post_id = parts[-1]
    
    try:
        data = fetch_post(handle, post_id)
    except:
        return False
    
    post = data.get("thread", {}).get("post", {})
    record = post.get("record", {})
    text = record.get("text", "")
    created_at = record.get("createdAt", "")
    
    if not text:
        return False
    
    # Date
    date_str = datetime.now().strftime("%Y%m%d")
    if created_at:
        try:
            date_str = datetime.fromisoformat(created_at.replace("Z", "")).strftime("%Y%m%d")
        except:
            pass
    
    # Nom fichier
    handle_safe = handle.replace(":", "_").replace(".", "_")[:20]
    filename = f"{handle_safe}_{date_str}_{post_id}.txt"
    filepath = os.path.join(TEXT_DIR, filename)
    
    # Sauvegarde
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"Post: {post_url}\n")
        f.write(f"Date: {created_at}\n")
        f.write(f"Auteur: {handle}\n")
        f.write(f"\n{text}\n")
    
    print(f"   [TXT] {filename}")
    return True

if __name__ == "__main__":
    success = save_text(url)
    sys.exit(0 if success else 2)