#!/usr/bin/env python3
print("SCRIPT IMG DEMARRE")
"""
bsky_img_downloader.py
Télécharge les images d'un post Bluesky et les renomme:
  <handle>_<YYYYMMDD>_<postid_short>_<nnn>.<ext>
Ajoute les métadonnées EXIF suivantes :
  - Titre : ID du post
  - Commentaire : texte du post
  - Auteur : identifiant du compte Bluesky
  - Date d'acquisition : date du post
  - Copyright : URL du post
Ne télécharge QUE les images (pas les thumbs de vidéo).
Codes de sortie:
  0 = succès (au moins une image téléchargée)
  1 = erreur technique
  2 = aucun média image trouvé / aucun post fourni
"""
import os
import re
import requests
import mimetypes
import subprocess
from urllib.parse import urlparse
from datetime import datetime
import sys
import json
from pathlib import Path

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# --- Récupère les arguments ---
DEBUG_MODE = "--debug" in sys.argv

# Charger config si disponible
from core.config import get_default_paths

default_paths = get_default_paths()
default_img = default_paths["img_dir"]

IMG_DIR = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else default_img

if len(sys.argv) > 2:
    url_input = sys.argv[2]
else:
    url_input = input("👉 Collez une URL : ").strip()

MAX_FILENAME_LEN = 64
MIN_POSTID_SHORT = 4
INDEX_DIGITS = 1
SPACER = " - "

os.makedirs(IMG_DIR, exist_ok=True)

def print_debug(data):
    if DEBUG_MODE:
        print("--- Réponse complète de l'API ---")
        print(json.dumps(data, indent=2))
        print("--- Fin de la réponse ---")

def safe_part(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', s)
    s = re.sub(r'\s+', '_', s)
    s = re.sub(r'_+', '_', s)
    s = s.strip(' ._')
    return s or "_"

def guess_ext_from_ct(ct: str) -> str:
    if not ct: return ''
    ct = ct.split(';',1)[0].strip().lower()
    if 'jpeg' in ct or 'jpg' in ct: return '.jpg'
    if 'png' in ct: return '.png'
    if 'webp' in ct: return '.webp'
    if 'gif' in ct: return '.gif'
    if 'bmp' in ct: return '.bmp'
    if 'tiff' in ct: return '.tif'
    return mimetypes.guess_extension(ct) or ''

def get_extension_for_url(url: str) -> str:
    if not url: return '.jpg'
    path_ext = os.path.splitext(urlparse(url).path)[1]
    if path_ext and len(path_ext) <= 8:
        return path_ext.lower()
    try:
        h = requests.head(url, allow_redirects=True, timeout=10)
        ext = guess_ext_from_ct(h.headers.get('content-type',''))
        if ext: return ext
    except: pass
    try:
        r = requests.get(url, stream=True, timeout=10)
        ext = guess_ext_from_ct(r.headers.get('content-type',''))
        r.close()
        if ext: return ext
    except: pass
    return '.jpg'

def build_filename(handle: str, date_str: str, post_id: str, index: int, ext: str,
                   max_len=MAX_FILENAME_LEN,
                   min_postid=MIN_POSTID_SHORT,
                   index_digits=INDEX_DIGITS,
                   spacer=SPACER) -> str:
    handle = safe_part(handle)
    post_id = safe_part(post_id)
    date_str = safe_part(date_str)
    ext_len = len(ext)
    idx_len = 1 + index_digits
    allowed_hp = max_len - (len(date_str) + 2 + idx_len + ext_len)
    min_postid = max(1, allowed_hp//3) if allowed_hp < (1 + min_postid) else min_postid
    if len(handle) + len(post_id) <= allowed_hp:
        handle_short, postid_short = handle, post_id
    else:
        space_for_postid = allowed_hp - len(handle)
        if space_for_postid >= min_postid:
            handle_short, postid_short = handle, post_id[:space_for_postid]
        else:
            handle_max = max(1, allowed_hp - min_postid)
            handle_short = handle[:handle_max]
            postid_short = post_id[:max(1, allowed_hp-len(handle_short))]
    base = f"{handle_short}_{date_str}_{postid_short}"
    idx_str = f"_{index:0{index_digits}d}"
    filename = f"{base}{idx_str}{ext}"
    if len(filename) > max_len:
        filename = filename[:max_len - ext_len] + ext
    return filename

def next_index_for_base(idx: int) -> int:
    return idx + 1

# -------------------- Bluesky API / Extraction --------------------
def fetch_post_json(handle: str, post_id: str):
    api_url = f"https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri=at://{handle}/app.bsky.feed.post/{post_id}"
    resp = requests.get(api_url, timeout=15)
    resp.raise_for_status()
    return resp.json()

def extract_images_from_bsky(post_url: str):
    parsed = urlparse(post_url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 3 or parts[0] != "profile":
        return "_unknown_", datetime.now().strftime("%Y%m%d"), "_unknown_", [], "", "", False
    
    handle_from_url = parts[1]
    post_id = parts[-1]
    
    try:
        data = fetch_post_json(handle_from_url, post_id)
    except Exception as e:
        error_msg = str(e)
        if "400 Client Error: Bad Request" in error_msg:
            print("   [!] Post supprimé ou inaccessible")
        elif "500 Server Error" in error_msg:
            print("   [!] Erreur serveur (lien invalide)")
        else:
            print(f"   [!] Erreur API : {e}")
        return handle_from_url, datetime.now().strftime("%Y%m%d"), post_id, [], "", "", False

    post = data.get("thread", {}).get("post", {})
    author = post.get("author", {})
    handle = author.get("handle", handle_from_url)
    created_at = post.get("record", {}).get("createdAt", "")
    
    date_str = datetime.now().strftime("%Y%m%d")
    if created_at:
        try:
            date_str = datetime.fromisoformat(created_at.replace("Z", "")).strftime("%Y%m%d")
        except:
            date_str = created_at[:10].replace("-", "")

    post_text = post.get("record", {}).get("text", "")
    embed = post.get("embed", {})
    embed_type = embed.get("$type", "")
    
    images = []
    is_repost = False
    
    # ORDRE : 1. Images directes, 2. RecordWithMedia, 3. Repost
    
    # 1. Images directes
    if embed_type == "app.bsky.embed.images#view":
        for img in embed.get("images", []):
            full_url = img.get("fullsize")
            if full_url:
                images.append(full_url)
    
    # 2. Record avec média (quote post + image)
    elif embed_type == "app.bsky.embed.recordWithMedia#view":
        media = embed.get("media", {})
        if media.get("$type") == "app.bsky.embed.images#view":
            for img in media.get("images", []):
                full_url = img.get("fullsize")
                if full_url:
                    images.append(full_url)
    
    # 3. Repost pur (dernier recours)
    elif embed_type == "app.bsky.embed.record#view":
        is_repost = True
        record = embed.get("record", {})
        embeds = record.get("embeds", [])
        for emb in embeds:
            if emb.get("$type") == "app.bsky.embed.images#view":
                for img in emb.get("images", []):
                    full_url = img.get("fullsize")
                    if full_url:
                        images.append(full_url)

    return handle, date_str, post_id, images, post_text, created_at, is_repost
    parsed = urlparse(post_url)
    parts = parsed.path.strip("/").split("/")
    
    if len(parts) < 3 or parts[0] != "profile":
        return "_unknown_", datetime.now().strftime("%Y%m%d"), "_unknown_", [], "", "", False
    
    handle_from_url = parts[1]
    post_id = parts[-1]
    
    try:
        data = fetch_post_json(handle_from_url, post_id)
        print_debug(data)
    except Exception as e:
        error_msg = str(e)
        if "400 Client Error: Bad Request" in error_msg:
            print("   [!] Post supprimé ou inaccessible")
            return handle_from_url, datetime.now().strftime("%Y%m%d"), post_id, [], "", "", False
        print(f"   [!] Impossible de récupérer le post via API : {e}")
        return handle_from_url, datetime.now().strftime("%Y%m%d"), post_id, [], "", "", False

    post = data.get("thread", {}).get("post", {})
    
    author = post.get("author", {})
    handle = author.get("handle", handle_from_url)
    created_at = post.get("record", {}).get("createdAt", "")
    date_str = datetime.now().strftime("%Y%m%d")
    if created_at:
        try:
            date_str = datetime.fromisoformat(created_at.replace("Z", "")).strftime("%Y%m%d")
        except:
            date_str = created_at[:10].replace("-", "")

    # Texte du post
    post_text = post.get("record", {}).get("text", "")

    # Récupère les images du post principal
    images = []
    embed = post.get("embed", {})
    embed_type = embed.get("$type", "None")
    
    # Vérifier si c'est un repost
    is_repost = False
    if embed.get("$type") == "app.bsky.embed.record#view":
        is_repost = True
        record = embed.get("record", {})
        # Tenter de récupérer les médias du post cité
        embeds = record.get("embeds", [])
        for emb in embeds:
            if emb.get("$type") == "app.bsky.embed.images#view":
                for img in emb.get("images", []):
                    full_url = img.get("fullsize")
                    if full_url and full_url not in images:
                        images.append(full_url)
    
    if embed.get("$type") == "app.bsky.embed.images#view":
        for img in embed.get("images", []):
            full_url = img.get("fullsize")
            if full_url and full_url not in images:
                images.append(full_url)
    elif embed.get("$type") == "app.bsky.embed.recordWithMedia#view":
        media = embed.get("media", {})
        if media.get("$type") == "app.bsky.embed.images#view":
            for img in media.get("images", []):
                full_url = img.get("fullsize")
                if full_url and full_url not in images:
                    images.append(full_url)

    return handle, date_str, post_id, images, post_text, created_at, is_repost

# -------------------- Téléchargement --------------------
def download_image(url, handle, date_str, post_id, post_url, post_text, created_at, idx):
    ext = get_extension_for_url(url) or ".jpg"
    filename = build_filename(handle, date_str, post_id, idx, ext)
    filepath = os.path.join(IMG_DIR, filename)
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        with open(filepath, "wb") as f:
            f.write(r.content)
        print(f"   [DL] Téléchargé -> {filename}")
        # --- Ajout des métadonnées EXIF ---
        try:
            full_comment = f"{post_text}\n\nLien du post : {url}"
            
            exif_cmd = [
                "exiftool",
                f"-Title={post_id}",
                f"-XPComment={full_comment}",
                f"-Artist={handle}",
                f"-DateTimeOriginal={created_at.replace('Z','') if created_at else ''}",
                f"-Copyright={post_url}",
                "-overwrite_original",
                filepath
            ]
            subprocess.run(exif_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"   [ERR] Impossible de télécharger {url} : {e}")
        return False

# -------------------- Main --------------------
def main():
    urls = []
    if os.path.isfile(url_input):
        with open(url_input, "r", encoding="utf-8") as f:
            for line in f:
                u = line.strip()
                if u: urls.append(u)
    else:
        urls = [url_input]  # ← FIX : simplifier, toujours une liste
    
    
    if not urls:
        sys.exit(2)
    
    success = False
    for post_url in urls:
        try:
            result = extract_images_from_bsky(post_url)
            handle, date_str, post_id, images, post_text, created_at, is_repost = result
        except Exception as e:
            print(f"   [!] Erreur API : {e}")
            import traceback
            traceback.print_exc()
            continue
        
        if is_repost and not images:
            print("   [REPOST] Post sans média directement accessible")
            continue
        
        if not images:
            print("   [!] Aucune image trouvée")
            continue
        
        if is_repost:
            print(f"   [REPOST] {len(images)} image(s) du post cité")
        else:
            print(f"   [OK] {len(images)} image(s) trouvée(s)")
        
        idx = 1
        for img_url in images:
            try:
                if download_image(img_url, handle, date_str, post_id, post_url, post_text, created_at, idx):
                    success = True
            except Exception as e:
                import traceback
                traceback.print_exc()
            idx = next_index_for_base(idx)
    
    sys.exit(0 if success else 2)

if __name__ == "__main__":
    main()
