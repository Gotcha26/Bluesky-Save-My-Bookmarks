#!/usr/bin/env python3
"""
bsky_vid_downloader.py
Télécharge vidéos depuis Bluesky via l'API
"""

import sys
import os
import re
import subprocess
import requests
from datetime import datetime
from urllib.parse import urlparse
import json
from pathlib import Path

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Charger config si disponible
from core.config import get_default_paths

default_paths = get_default_paths()
default_vid = default_paths["vid_dir"]

VID_DIR = sys.argv[1] if len(sys.argv) > 1 else default_vid

if len(sys.argv) > 2:
    url = sys.argv[2]
else:
    url = input("👉 Collez une URL vidéo : ").strip()
    
MAX_FILENAME_LEN = 64
os.makedirs(VID_DIR, exist_ok=True)

def get_post_data(post_url):
    """Récupère les données complètes du post via l'API"""
    parts = urlparse(post_url).path.strip("/").split("/")
    if len(parts) < 2:
        return None
    
    handle_from_url = parts[-3] if len(parts) >= 3 else parts[-2]
    post_id = parts[-1]
    
    api_url = "https://bsky.social/xrpc/com.atproto.repo.getRecord"
    params = {
        "repo": handle_from_url,
        "collection": "app.bsky.feed.post",
        "rkey": post_id
    }
    
    try:
        resp = requests.get(api_url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"   ⚠️ Erreur API : {e}")
        return None

def extract_video_info(data):
    """Extrait les infos vidéo du JSON"""
    if not data:
        return None, False
    
    value = data.get("value", {})
    embed = value.get("embed", {})
    embed_type = embed.get("$type", "None")
    
    # Vérifier si c'est un repost
    is_repost = False
    if embed.get("$type") == "app.bsky.embed.record":
        is_repost = True
        record = embed.get("record", {})
        # Tenter de récupérer la vidéo du post cité
        embeds = record.get("embeds", [])
        for emb in embeds:
            if emb.get("$type") == "app.bsky.embed.video":
                embed = emb
                break
    
    # Vérifier si c'est une vidéo
    if embed.get("$type") != "app.bsky.embed.video":
        return None, is_repost
    
    video_blob = embed.get("video", {})
    
    cid = video_blob.get("ref", {}).get("$link")
    
    if not cid:
        return None, is_repost
    
    uri = data.get("uri", "")
    did = uri.split("/")[2] if "/" in uri else None
    
    if not did:
        return None, is_repost
    
    video_url = f"https://bsky.social/xrpc/com.atproto.sync.getBlob?did={did}&cid={cid}"
    
    text = value.get("text", "")
    created_at = value.get("createdAt", "")
    
    return {
        "url": video_url,
        "text": text,
        "created_at": created_at,
        "cid": cid
    }, is_repost

def safe_filename_part(s):
    """Nettoie une chaîne pour nom de fichier"""
    s = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', s)
    s = re.sub(r'\s+', '_', s)
    return s.strip(' ._')[:50]

def download_video(video_info, handle, post_id):
    """Télécharge la vidéo"""
    created_at = video_info["created_at"]
    try:
        date_str = datetime.fromisoformat(created_at.replace("Z", "")).strftime("%Y%m%d")
    except:
        date_str = datetime.now().strftime("%Y%m%d")
    
    handle_safe = safe_filename_part(handle)
    post_id_safe = safe_filename_part(post_id)
    filename = f"{handle_safe}_{date_str}_{post_id_safe}_01.mp4"
    
    if len(filename) > MAX_FILENAME_LEN:
        filename = filename[:MAX_FILENAME_LEN-4] + ".mp4"
    
    filepath = os.path.join(VID_DIR, filename)
    
    print(f"   [DL] Téléchargement en cours...")
    try:
        r = requests.get(video_info["url"], stream=True, timeout=60)
        r.raise_for_status()
        
        with open(filepath, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"   [OK] Fichier enregistré : {filename}")
        
        try:
            temp_file = filepath + ".tmp.mp4"
            full_comment = f"{video_info['text']}\n\nLien du post : {url}"
            
            subprocess.run([
                "ffmpeg", "-y", "-i", filepath,
                "-metadata", f"title={post_id}",
                "-metadata", f"comment={full_comment}",
                "-metadata", f"creation_time={created_at}",
                "-metadata", f"artist={handle}",
                "-codec", "copy", temp_file
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            
            os.replace(temp_file, filepath)
            print("   [OK] Métadonnées ajoutées")
        except Exception as e:
            print(f"   [!] Métadonnées non ajoutées : {e}")
        
        return True
    
    except Exception as e:
        print(f"   [ERR] Erreur : {e}")
        return False

def main():
    parts = urlparse(url).path.strip("/").split("/")
    if len(parts) < 4:
        print("   [ERR] URL invalide")
        sys.exit(1)
    
    handle = parts[-3]
    post_id = parts[-1]
    
    print("   [...] Récupération des informations...")
    
    try:
        data = get_post_data(url)
        
        if not data:
            error_msg = "400 Client Error: Bad Request"
            print(f"   [!] Post supprimé ou inaccessible")
            sys.exit(1)
        
        video_info, is_repost = extract_video_info(data)
        
        if not video_info:
            if is_repost:
                print("   [REPOST] Post sans vidéo directement accessible")
            else:
                print("   [!] Aucune vidéo trouvée")
            sys.exit(2)
        
        if is_repost:
            print("   [REPOST] Vidéo du post cité détectée")
        
        success = download_video(video_info, handle, post_id)
        
        sys.exit(0 if success else 1)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()