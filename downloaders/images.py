#!/usr/bin/env python3
"""
Téléchargement des images d'un post Bluesky, renommées :
  <handle>_<YYYYMMDD>_<postid_short>_<n>.<ext>
Ajoute les métadonnées EXIF suivantes (si exiftool est installé) :
  - Titre : ID du post
  - Commentaire : texte du post
  - Auteur : identifiant du compte Bluesky
  - Date d'acquisition : date du post
  - Copyright : URL du post
Ne télécharge QUE les images (pas les thumbs de vidéo).

Usage manuel : python downloaders/images.py <dossier> <url_post | fichier_urls>
Codes de sortie : 0 = au moins une image, 1 = erreur technique, 2 = aucune image.
"""
import os
import re
import sys
import mimetypes
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

if __package__ in (None, ""):
    # Exécution directe (python downloaders/images.py) : rendre la racine importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import DEFAULT_CONFIG, get_default_paths, load_config  # noqa: E402
from downloaders import DownloadError, DownloadResult, lignes_console  # noqa: E402

SPACER = " - "


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

def get_extension_for_url(url: str, http=requests) -> str:
    if not url: return '.jpg'
    path_ext = os.path.splitext(urlparse(url).path)[1]
    if path_ext and len(path_ext) <= 8:
        return path_ext.lower()
    try:
        h = http.head(url, allow_redirects=True, timeout=10)
        ext = guess_ext_from_ct(h.headers.get('content-type',''))
        if ext: return ext
    except Exception: pass
    try:
        r = http.get(url, stream=True, timeout=10)
        ext = guess_ext_from_ct(r.headers.get('content-type',''))
        r.close()
        if ext: return ext
    except Exception: pass
    return '.jpg'

def build_filename(handle: str, date_str: str, post_id: str, index: int, ext: str,
                   max_len=DEFAULT_CONFIG["max_filename_len"],
                   min_postid=DEFAULT_CONFIG["min_postid_short"],
                   index_digits=DEFAULT_CONFIG["index_digits"],
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

# -------------------- Bluesky API / Extraction --------------------
def fetch_post_json(handle: str, post_id: str, http=requests):
    api_url = f"https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri=at://{handle}/app.bsky.feed.post/{post_id}"
    resp = http.get(api_url, timeout=15)
    resp.raise_for_status()
    return resp.json()

def extract_images_from_bsky(post_url: str, http=requests):
    """
    Lit le post via getPostThread et extrait les URLs des images.
    Lève DownloadError si l'API échoue.
    """
    parsed = urlparse(post_url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 3 or parts[0] != "profile":
        return "_unknown_", datetime.now().strftime("%Y%m%d"), "_unknown_", [], "", "", False

    handle_from_url = parts[1]
    post_id = parts[-1]

    try:
        data = fetch_post_json(handle_from_url, post_id, http)
    except Exception as e:
        error_msg = str(e)
        if "400 Client Error: Bad Request" in error_msg:
            raise DownloadError("Post supprimé ou inaccessible") from e
        elif "500 Server Error" in error_msg:
            raise DownloadError("Erreur serveur (lien invalide)") from e
        raise DownloadError(f"Erreur API : {e}") from e

    post = data.get("thread", {}).get("post", {})
    author = post.get("author", {})
    handle = author.get("handle", handle_from_url)
    created_at = post.get("record", {}).get("createdAt", "")

    date_str = datetime.now().strftime("%Y%m%d")
    if created_at:
        try:
            date_str = datetime.fromisoformat(created_at.replace("Z", "")).strftime("%Y%m%d")
        except ValueError:
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

# -------------------- Téléchargement --------------------
def download_image(url, filepath, handle, post_id, post_url, post_text, created_at, http=requests):
    """Télécharge une image dans filepath puis ajoute les métadonnées EXIF (best effort)."""
    r = http.get(url, timeout=30)
    r.raise_for_status()
    with open(filepath, "wb") as f:
        f.write(r.content)
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
            str(filepath)
        ]
        subprocess.run(exif_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def build_prefixed_filename(prefix: str, index: int, ext: str, max_len, index_digits) -> str:
    """<prefix>_<n><ext>, le préfixe étant tronqué pour tenir dans max_len."""
    suffix = f"_{index:0{index_digits}d}{ext}"
    return prefix[:max(1, max_len - len(suffix))] + suffix


def download_images(post_url, dest_dir, config, session=None, name_prefix=None):
    """
    Télécharge les images d'un post dans dest_dir.

    name_prefix : si fourni, remplace la base <handle>_<date>_<postid> du nom
    (images d'un post cité : <prefix>_<n>.<ext>).

    Returns:
        list[DownloadResult] : une entrée par image écrite ; liste vide si le
        post ne contient aucune image.
    Raises:
        DownloadError : API inaccessible, ou aucune image n'a pu être téléchargée.
    """
    http = session or requests
    handle, date_str, post_id, image_urls, post_text, created_at, _ = extract_images_from_bsky(post_url, http)
    if not image_urls:
        return []

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    max_len = config.get("max_filename_len", DEFAULT_CONFIG["max_filename_len"])
    min_postid = config.get("min_postid_short", DEFAULT_CONFIG["min_postid_short"])
    index_digits = config.get("index_digits", DEFAULT_CONFIG["index_digits"])

    results = []
    erreurs = []
    for idx, img_url in enumerate(image_urls, start=1):
        ext = get_extension_for_url(img_url, http) or ".jpg"
        if name_prefix:
            filename = build_prefixed_filename(name_prefix, idx, ext, max_len, index_digits)
        else:
            filename = build_filename(handle, date_str, post_id, idx, ext,
                                      max_len=max_len, min_postid=min_postid, index_digits=index_digits)
        filepath = dest_dir / filename
        try:
            download_image(img_url, filepath, handle, post_id, post_url, post_text, created_at, http)
        except Exception as e:
            erreurs.append(f"Impossible de télécharger {img_url} : {e}")
            continue
        results.append(DownloadResult(filename, filepath, "image", filepath.stat().st_size))

    if erreurs and not results:
        raise DownloadError(" ; ".join(erreurs))
    return results

# -------------------- Usage manuel --------------------
def main(argv=None):
    """python downloaders/images.py <dossier> <url_post | fichier_urls>"""
    argv = sys.argv[1:] if argv is None else argv
    dest_dir = argv[0] if argv else get_default_paths()["img_dir"]
    url_input = argv[1] if len(argv) > 1 else input("👉 Collez une URL : ").strip()

    if os.path.isfile(url_input):
        with open(url_input, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]
    else:
        urls = [url_input] if url_input else []
    if not urls:
        return 2

    config = load_config()
    code = 2
    for post_url in urls:
        try:
            results = download_images(post_url, dest_dir, config)
        except DownloadError as e:
            print(f"   [ERR] {e}")
            code = 1 if code == 2 else code
            continue
        if not results:
            print("   [!] Aucune image trouvée")
            continue
        print(f"   [OK] {len(results)} image(s) téléchargée(s)")
        for ligne in lignes_console(results):
            print(ligne)
        code = 0
    return code

if __name__ == "__main__":
    sys.exit(main())
