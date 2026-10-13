#!/usr/bin/env python3
"""
Archivage d'un post dont l'embed est `app.bsky.embed.external` (carte de lien,
GIF Tenor, lien tiers). Écrit, dans les dossiers médias :
  texts/<handle>_<YYYYMMDD>_<postid>.txt         texte du post + lien, titre, description
  images/<handle>_<YYYYMMDD>_<postid>_thumb.jpg  vignette de la carte (si elle existe)
  images|videos/<…>_01.<ext>                     média lui-même, si l'URI cible
                                                 media.tenor.com ou un .gif / .mp4 / .webp

Les liens vers des plateformes tierces (x.com, YouTube…) ne sont pas téléchargés.
Pas d'usage manuel : la fonction reçoit le dict de PostAnalyzer.analyze().
"""
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

import requests

from downloaders import DownloadError, DownloadResult
from downloaders.text import nom_base_texte

log = logging.getLogger(__name__)

HOTE_TENOR = "media.tenor.com"
EXTENSIONS_IMAGES = {".gif", ".webp"}
EXTENSIONS_VIDEOS = {".mp4"}
TIMEOUT = (10, 120)
URL_VIGNETTE = "https://cdn.bsky.app/img/feed_thumbnail/plain/{did}/{cid}@jpeg"


def _extension_url(uri):
    """Extension (minuscules) du chemin de l'URL, sans la query ni le fragment."""
    return os.path.splitext(urlparse(uri or "").path)[1].lower()


def est_media_direct(uri):
    """True si l'URI pointe directement sur un fichier média téléchargeable."""
    parsed = urlparse(uri or "")
    if parsed.scheme not in ("http", "https"):
        return False
    if (parsed.hostname or "").lower() == HOTE_TENOR:
        return True
    return _extension_url(uri) in EXTENSIONS_IMAGES | EXTENSIONS_VIDEOS


def extension_media_direct(uri, content_type):
    """Extension du média : celle de l'URL si connue, sinon déduite du Content-Type (défaut .gif)."""
    ext = _extension_url(uri)
    if ext in EXTENSIONS_IMAGES | EXTENSIONS_VIDEOS:
        return ext
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    if "mp4" in ct:
        return ".mp4"
    if "webp" in ct:
        return ".webp"
    return ".gif"


def _telecharger_fichier(http, url, choisir_cible):
    """
    Télécharge url dans le fichier renvoyé par choisir_cible(content_type), écrit en
    .part puis os.replace. Lève en cas d'échec (aucun .part ne subsiste).
    """
    resp = http.get(url, stream=True, timeout=TIMEOUT)
    part = None
    try:
        resp.raise_for_status()
        cible = Path(choisir_cible(resp.headers.get("content-type", "")))
        cible.parent.mkdir(parents=True, exist_ok=True)
        part = Path(f"{cible}.part")
        with open(part, "wb") as f:
            for morceau in resp.iter_content(chunk_size=64 * 1024):
                f.write(morceau)
        os.replace(part, cible)
        part = None
        return cible
    finally:
        resp.close()
        if part is not None and part.exists():
            part.unlink()


def _ecrire_texte(post_url, data, external, filepath):
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"Post: {post_url}\n")
        f.write(f"Date: {data.get('created_at', '')}\n")
        f.write(f"Auteur: {data.get('handle', '')}\n")
        f.write(f"\n{data.get('text', '')}\n")
        f.write(f"\nLien: {external.get('uri', '')}\n")
        f.write(f"Titre: {external.get('title', '')}\n")
        f.write(f"Description: {external.get('description', '')}\n")


def _resultat(filepath, media_type, cid=None):
    return DownloadResult(filepath.name, filepath, media_type, filepath.stat().st_size, cid)


def download_external(post_url, data, dirs, config, session=None):
    """
    Archive un post à embed externe.

    Args:
        data: dict renvoyé par PostAnalyzer.analyze() (handle, post_id, did, created_at,
              text, external={uri, title, description, thumb_cid})
        dirs: get_media_dirs(config) (clés img_dir, vid_dir, text_dir)
    Returns:
        list[DownloadResult] : le .txt en premier, puis la vignette, puis le média direct.
        Liste vide si `data` ne contient pas d'embed externe.
    Raises:
        DownloadError : écriture du fichier texte impossible. Un échec réseau sur la
        vignette ou le média direct est journalisé mais n'invalide pas le texte.
    """
    http = session or requests
    external = data.get("external") or {}
    if not external:
        return []

    base = nom_base_texte(data.get("handle", ""), data.get("post_id", ""), data.get("created_at", ""))
    resultats = []

    try:
        text_dir = Path(dirs["text_dir"])
        text_dir.mkdir(parents=True, exist_ok=True)
        txt = text_dir / f"{base}.txt"
        _ecrire_texte(post_url, data, external, txt)
        resultats.append(_resultat(txt, "text"))
    except OSError as e:
        raise DownloadError(f"Écriture du texte impossible : {e}") from e

    # Vignette : blob Bluesky servi par le CDN
    cid, did = external.get("thumb_cid"), data.get("did")
    if cid and did:
        try:
            thumb = _telecharger_fichier(http, URL_VIGNETTE.format(did=did, cid=cid),
                                         lambda ct: Path(dirs["img_dir"]) / f"{base}_thumb.jpg")
            resultats.append(_resultat(thumb, "image", cid))
        except Exception as e:
            log.warning("Vignette non téléchargée pour %s : %s", post_url, e)

    # Média direct (GIF Tenor, .gif / .mp4 / .webp)
    uri = external.get("uri", "")
    if est_media_direct(uri):
        try:
            def choisir(content_type):
                ext = extension_media_direct(uri, content_type)
                dossier = dirs["vid_dir"] if ext in EXTENSIONS_VIDEOS else dirs["img_dir"]
                return Path(dossier) / f"{base}_01{ext}"

            media = _telecharger_fichier(http, uri, choisir)
            resultats.append(_resultat(media, "video" if media.suffix in EXTENSIONS_VIDEOS else "image"))
        except Exception as e:
            log.warning("Média direct non téléchargé pour %s : %s", post_url, e)

    return resultats
