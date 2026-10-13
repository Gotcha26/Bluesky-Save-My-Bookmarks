#!/usr/bin/env python3
"""
Téléchargement de la vidéo d'un post Bluesky via l'API, renommée :
  <handle>_<YYYYMMDD>_<postid>_01.mp4
Ajoute titre, commentaire, date et auteur (si ffmpeg est installé).

Usage manuel : python downloaders/videos.py <dossier> <url_post>
Codes de sortie : 0 = vidéo téléchargée, 1 = erreur technique, 2 = aucune vidéo.
"""
import os
import re
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

if __package__ in (None, ""):
    # Exécution directe (python downloaders/videos.py) : rendre la racine importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import DEFAULT_CONFIG, get_default_paths, load_config  # noqa: E402
from downloaders import DownloadError, DownloadResult, lignes_console  # noqa: E402


def get_post_data(post_url, http=requests):
    """Récupère le record brut du post via l'API ; lève DownloadError en cas d'échec."""
    parts = urlparse(post_url).path.strip("/").split("/")
    handle_from_url = parts[-3] if len(parts) >= 3 else parts[-2]
    post_id = parts[-1]

    api_url = "https://bsky.social/xrpc/com.atproto.repo.getRecord"
    params = {
        "repo": handle_from_url,
        "collection": "app.bsky.feed.post",
        "rkey": post_id
    }

    try:
        resp = http.get(api_url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise DownloadError(f"Post supprimé ou inaccessible ({e})") from e

def extract_video_info(data):
    """Extrait les infos vidéo du JSON"""
    if not data:
        return None, False

    value = data.get("value", {})
    embed = value.get("embed", {})

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

def _video_filename(handle, post_id, created_at, max_len):
    try:
        date_str = datetime.fromisoformat(created_at.replace("Z", "")).strftime("%Y%m%d")
    except ValueError:
        date_str = datetime.now().strftime("%Y%m%d")

    filename = f"{safe_filename_part(handle)}_{date_str}_{safe_filename_part(post_id)}_01.mp4"
    if len(filename) > max_len:
        filename = filename[:max_len-4] + ".mp4"
    return filename

def _add_metadata(filepath, video_info, handle, post_id, post_url):
    """Ajoute les métadonnées avec ffmpeg (best effort : la vidéo reste valable sans)."""
    try:
        temp_file = str(filepath) + ".tmp.mp4"
        full_comment = f"{video_info['text']}\n\nLien du post : {post_url}"

        subprocess.run([
            "ffmpeg", "-y", "-i", str(filepath),
            "-metadata", f"title={post_id}",
            "-metadata", f"comment={full_comment}",
            "-metadata", f"creation_time={video_info['created_at']}",
            "-metadata", f"artist={handle}",
            "-codec", "copy", temp_file
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        os.replace(temp_file, filepath)
    except Exception:
        pass

def download_video(post_url, dest_dir, config, session=None):
    """
    Télécharge la vidéo d'un post dans dest_dir.

    Returns:
        list[DownloadResult] : la vidéo écrite (avec son CID) ; liste vide si le
        post ne contient pas de vidéo.
    Raises:
        DownloadError : URL invalide, API inaccessible ou téléchargement en échec.
    """
    http = session or requests
    parts = urlparse(post_url).path.strip("/").split("/")
    if len(parts) < 4:
        raise DownloadError("URL invalide")

    handle = parts[-3]
    post_id = parts[-1]

    video_info, _ = extract_video_info(get_post_data(post_url, http))
    if not video_info:
        return []

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    max_len = config.get("max_filename_len", DEFAULT_CONFIG["max_filename_len"])
    filename = _video_filename(handle, post_id, video_info["created_at"], max_len)
    filepath = dest_dir / filename

    try:
        r = http.get(video_info["url"], stream=True, timeout=60)
        r.raise_for_status()

        with open(filepath, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    except Exception as e:
        raise DownloadError(f"Erreur : {e}") from e

    _add_metadata(filepath, video_info, handle, post_id, post_url)

    return [DownloadResult(filename, filepath, "video", filepath.stat().st_size, video_info["cid"])]

# -------------------- Usage manuel --------------------
def main(argv=None):
    """python downloaders/videos.py <dossier> <url_post>"""
    argv = sys.argv[1:] if argv is None else argv
    dest_dir = argv[0] if argv else get_default_paths()["vid_dir"]
    url = argv[1] if len(argv) > 1 else input("👉 Collez une URL vidéo : ").strip()

    try:
        results = download_video(url, dest_dir, load_config())
    except DownloadError as e:
        print(f"   [ERR] {e}")
        return 1

    if not results:
        print("   [!] Aucune vidéo trouvée")
        return 2

    for ligne in lignes_console(results):
        print(ligne)
    return 0

if __name__ == "__main__":
    sys.exit(main())
