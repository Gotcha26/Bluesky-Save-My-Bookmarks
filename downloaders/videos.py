#!/usr/bin/env python3
"""
Téléchargement de la vidéo d'un post Bluesky via l'API, renommée :
  <handle>_<YYYYMMDD>_<postid>_01.mp4
Ajoute titre, commentaire, date et auteur (si ffmpeg est installé).

Usage manuel : python downloaders/videos.py <dossier> <url_post>
Codes de sortie : 0 = vidéo téléchargée, 1 = erreur technique, 2 = aucune vidéo.
"""
import logging
import mimetypes
import os
import re
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


if __package__ in (None, ""):
    # Exécution directe (python downloaders/videos.py) : rendre la racine importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import DEFAULT_CONFIG, get_default_paths, load_config  # noqa: E402
from core import http as bsmb_http  # noqa: E402
from downloaders import DownloadError, DownloadResult, lignes_console  # noqa: E402


BLOB_HOST = "https://bsky.social"  # relaie (302) vers le PDS de l'auteur, quel qu'il soit
TIMEOUT = (10, 300)  # (connexion, lecture) : jusqu'à 300 Mo
MAX_CAPTIONS = 20
MIME_EXT = {"video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}

log = logging.getLogger(__name__)


def _blob_url(did, cid):
    return f"{BLOB_HOST}/xrpc/com.atproto.sync.getBlob?did={did}&cid={cid}"


def get_post_data(post_url, http=None):
    """Récupère le record brut du post via l'API ; lève DownloadError en cas d'échec."""
    http = http or bsmb_http.get_session()
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

    # Citation avec média : la vidéo est dans `media`
    if embed.get("$type") == "app.bsky.embed.recordWithMedia":
        embed = embed.get("media", {})

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

    video_url = _blob_url(did, cid)

    captions = []
    for cap in embed.get("captions") or []:
        cap_cid = ((cap.get("file") or {}).get("ref") or {}).get("$link")
        if cap_cid:
            captions.append({"lang": cap.get("lang") or "", "cid": cap_cid})

    return {
        "url": video_url,
        "text": value.get("text", ""),
        "created_at": value.get("createdAt", ""),
        "cid": cid,
        "did": did,
        "mime": video_blob.get("mimeType") or "",
        "alt": embed.get("alt") or "",
        "presentation": embed.get("presentation") or "",
        "captions": captions,
    }, is_repost

def safe_filename_part(s):
    """Nettoie une chaîne pour nom de fichier"""
    s = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', s)
    s = re.sub(r'\s+', '_', s)
    return s.strip(' ._')[:50]

def ext_from_mime(mime):
    """Extension d'un mimeType vidéo ; .mp4 par défaut."""
    mime = (mime or "").split(";", 1)[0].strip().lower()
    if not mime:
        return ".mp4"
    return MIME_EXT.get(mime) or mimetypes.guess_extension(mime) or ".mp4"

def _video_base(handle, post_id, created_at):
    """<handle>_<YYYYMMDD>_<postid> : base de nom des fichiers d'une vidéo."""
    try:
        date_str = datetime.fromisoformat(created_at.replace("Z", "")).strftime("%Y%m%d")
    except ValueError:
        date_str = datetime.now().strftime("%Y%m%d")
    return f"{safe_filename_part(handle)}_{date_str}_{safe_filename_part(post_id)}"

def _nom(base, suffixe, ext, max_len):
    """base + suffixe + ext, la base étant tronquée pour tenir dans max_len."""
    return base[:max(1, max_len - len(suffixe) - len(ext))] + suffixe + ext

def _ecrire_blob(http, url, dest, types):
    """
    Télécharge `url` dans `dest` en passant par `dest.part`, renommé seulement une fois la
    réponse validée et entièrement reçue (le .part est supprimé en cas d'échec).
    types : préfixes de Content-Type acceptés (application/octet-stream l'est toujours ;
    un Content-Type absent n'est pas bloquant). Lève une exception en cas d'échec.
    """
    part = dest.with_name(dest.name + ".part")
    r = None
    try:
        r = http.get(url, stream=True, timeout=TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        if r.status_code != 200:
            raise ValueError(f"statut inattendu ({r.status_code})")
        ctype = ((r.headers.get("content-type") or "").split(";", 1)[0]).strip().lower()
        if ctype and ctype != "application/octet-stream" and not ctype.startswith(types):
            raise ValueError(f"contenu inattendu ({ctype})")
        ecrit = 0
        with open(part, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    ecrit += len(chunk)
        if not ecrit:
            raise ValueError("réponse vide")
        os.replace(part, dest)
    finally:
        if r is not None and hasattr(r, "close"):
            r.close()
        part.unlink(missing_ok=True)

def _repli_hls(playlist, dest):
    """Reconstruit la vidéo depuis la playlist HLS avec ffmpeg ; lève DownloadError."""
    ok = False
    try:
        subprocess.run(["ffmpeg", "-y", "-i", playlist, "-c", "copy", str(dest)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=True, timeout=600)
        ok = True
    except FileNotFoundError as e:
        raise DownloadError("ffmpeg introuvable : repli HLS impossible") from e
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        raise DownloadError(f"repli HLS en échec ({e})") from e
    finally:
        if not ok:
            dest.unlink(missing_ok=True)

def _add_metadata(filepath, video_info, handle, post_id, post_url):
    """Ajoute les métadonnées avec ffmpeg (best effort : la vidéo reste valable sans)."""
    temp_file = str(filepath) + ".tmp" + filepath.suffix
    try:
        full_comment = f"{video_info['text']}\n\nLien du post : {post_url}"
        alt = ["-metadata", f"description={video_info['alt']}"] if video_info.get("alt") else []

        subprocess.run([
            "ffmpeg", "-y", "-i", str(filepath),
            "-metadata", f"title={post_id}",
            "-metadata", f"comment={full_comment}",
            "-metadata", f"creation_time={video_info['created_at']}",
            "-metadata", f"artist={handle}",
            *alt,
            "-codec", "copy", temp_file
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        os.replace(temp_file, filepath)
    except Exception:
        try:
            os.remove(temp_file)
        except OSError:
            pass

def _sous_titres(http, video_info, filepath, max_len):
    """Télécharge les captions en <video>.<lang>.vtt ; un échec n'est qu'un avertissement."""
    resultats = []
    utilises = set()
    for cap in video_info["captions"][:MAX_CAPTIONS]:
        lang = safe_filename_part(cap["lang"]) or "und"
        nom = f"{filepath.stem}.{lang}.vtt"
        n = 1
        while nom in utilises:
            n += 1
            nom = f"{filepath.stem}.{lang}-{n}.vtt"
        utilises.add(nom)
        chemin = filepath.with_name(nom)
        try:
            _ecrire_blob(http, _blob_url(video_info["did"], cap["cid"]), chemin, ("text/",))
        except Exception as e:
            log.warning("Sous-titres %s non téléchargés (%s) : %s", cap["lang"] or "?", filepath.name, e)
            continue
        resultats.append(DownloadResult(nom, chemin, "subtitle", chemin.stat().st_size, cap["cid"]))
    return resultats

def _miniature(http, view_embed, dest_dir, base, max_len, video_name):
    """Télécharge la miniature de la vue hydratée ; None (avertissement) en cas d'échec."""
    url = (view_embed or {}).get("thumbnail")
    if not url:
        return None
    nom = _nom(base, "_01_thumb", ".jpg", max_len)
    chemin = dest_dir / nom
    try:
        _ecrire_blob(http, url, chemin, ("image/",))
    except Exception as e:
        log.warning("Miniature non téléchargée (%s) : %s", video_name, e)
        return None
    return DownloadResult(nom, chemin, "image", chemin.stat().st_size)

def download_video(post_url, dest_dir, config, session=None, name_prefix=None,
                   record=None, view_embed=None, did=None):
    """
    Télécharge la vidéo d'un post dans dest_dir.

    name_prefix : si fourni, remplace la base <handle>_<date>_<postid> du nom
    (vidéo d'un post cité : <prefix>_01.<ext>).
    record : record brut du post (`value` de getRecord) ; avec le DID de l'auteur (`did`,
    ou l'URL du post s'il y figure), évite le getRecord.
    view_embed : embed hydraté (`app.bsky.embed.video#view`, ou None) : sa `playlist` HLS
    sert de repli si getBlob échoue, sa `thumbnail` est téléchargée si
    config["download_video_thumbnail"].

    Le blob d'origine est lu sur bsky.social (timeout (10, 300)) dans un .part renommé
    à la fin. L'extension vient du mimeType ; un GIF (presentation == "gif") reçoit le
    suffixe _gif, ou le sous-dossier gifs/ si config["gif_subfolder"]. L'alt est écrit
    dans la métadonnée ffmpeg `description`. Les sous-titres sont écrits en
    <nom>.<lang>.vtt (leur échec n'est qu'un avertissement).

    Returns:
        list[DownloadResult] : la vidéo (avec son CID et son alt), puis ses sous-titres
        (media_type "subtitle") et sa miniature ("image") ; liste vide si le post ne
        contient pas de vidéo.
    Raises:
        DownloadError : URL invalide, API inaccessible ou téléchargement en échec
        (blob et repli HLS compris).
    """
    http = session or bsmb_http.get_session()
    parts = urlparse(post_url).path.strip("/").split("/")
    if len(parts) < 4:
        raise DownloadError("URL invalide")

    handle = parts[-3]
    post_id = parts[-1]
    did = did or (handle if handle.startswith("did:") else None)

    if record is not None and did:
        data = {"uri": f"at://{did}/app.bsky.feed.post/{post_id}", "value": record}
    else:
        data = get_post_data(post_url, http)
    video_info, _ = extract_video_info(data)
    if not video_info:
        return []

    dest_dir = Path(dest_dir)
    max_len = config.get("max_filename_len", DEFAULT_CONFIG["max_filename_len"])
    gif = video_info["presentation"] == "gif"
    sous_dossier = gif and config.get("gif_subfolder", DEFAULT_CONFIG["gif_subfolder"])
    out_dir = dest_dir / "gifs" if sous_dossier else dest_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    suffixe = "_01_gif" if gif and not sous_dossier else "_01"
    base = name_prefix or _video_base(handle, post_id, video_info["created_at"])
    filepath = out_dir / _nom(base, suffixe, ext_from_mime(video_info["mime"]), max_len)

    try:
        _ecrire_blob(http, video_info["url"], filepath, ("video/",))
    except Exception as e:
        playlist = (view_embed or {}).get("playlist")
        if not playlist:
            raise DownloadError(f"Erreur : {e}") from e
        log.warning("getBlob en échec (%s), repli sur la playlist HLS : %s", filepath.name, e)
        filepath = out_dir / _nom(base, suffixe, ".mp4", max_len)  # la copie HLS est du MP4
        try:
            _repli_hls(playlist, filepath)
        except DownloadError as e2:
            raise DownloadError(f"Erreur : {e} ; {e2}") from e2

    _add_metadata(filepath, video_info, handle, post_id, post_url)

    resultats = [DownloadResult(filepath.name, filepath, "video", filepath.stat().st_size,
                                video_info["cid"], alt=video_info["alt"] or None)]
    resultats += _sous_titres(http, video_info, filepath, max_len)
    if config.get("download_video_thumbnail", DEFAULT_CONFIG["download_video_thumbnail"]):
        miniature = _miniature(http, view_embed, dest_dir, base, max_len, filepath.name)
        if miniature:
            resultats.append(miniature)
    return resultats

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
