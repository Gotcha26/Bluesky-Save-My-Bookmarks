#!/usr/bin/env python3
"""Configuration centralisée pour BSMB"""
import os
import json
from pathlib import Path
from datetime import datetime, timedelta

from core.paths import PROJECT_ROOT

CONFIG_FILE = PROJECT_ROOT / "config.json"

DEFAULT_CONFIG = {
    "download_dir": str(Path.home() / "Downloads" / "BSMB"),
    "token_file": "Token-Bearer.txt",
    "urls_file": "urls.txt",
    "db_file": "bsmb.db",
    "logs_dir": "logs",
    "max_logs": 5,  # nombre maximal de logs download_*.log conservés
    "max_filename_len": 64,
    "min_postid_short": 4,
    "index_digits": 1,
    "bsky_handle": "",
    "bsky_app_password": "",
    "pds_url": "",  # PDS du compte ("" = inconnu, bsky.social utilisé)
    "max_workers": 4,
    "retry_after_days": 7,  # délai avant de retenter un post en erreur (500, inconnu, repost)
    "last_sync": "",
    "advanced_mode": False,
    "open_folder_after_download": True,  # propose d'ouvrir le dossier après un téléchargement (ignoré en non interactif)
    "warned_plaintext_secret": False,  # avertissement « App Password en clair » déjà affiché
    "image_quality": "original",  # "original" (blob getBlob, repli CDN) ou "cdn" (image fullsize du CDN)
    "skip_existing_cid": True,  # ne pas retélécharger un blob dont le cid est en base avec un fichier présent
    "bookmarks_cache": "bookmarks.json",  # dernière réponse getBookmarks (postView bruts)
    "gif_subfolder": False,  # GIF (vidéo presentation=gif) rangés dans videos/gifs/ au lieu du suffixe _gif
    "download_video_thumbnail": False  # télécharge aussi la miniature de la vidéo (_01_thumb.jpg)
}

def get_default_paths():
    """Retourne les chemins par défaut (utile pour les scripts)"""
    base = Path.home() / "Downloads" / "BSMB"
    return {
        "img_dir": str(base / "images"),
        "vid_dir": str(base / "videos"),
        "text_dir": str(base / "texts")
    }

def load_config():
    """Charge la config ou crée celle par défaut"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = {**DEFAULT_CONFIG, **json.load(f)}
    else:
        config = DEFAULT_CONFIG.copy()

    # Rétrocompatibilité : si img_dir/vid_dir existent, migrer vers download_dir
    if "img_dir" in config and "vid_dir" in config:
        # Extraire le dossier parent commun
        img_parent = str(Path(config["img_dir"]).parent)
        config["download_dir"] = img_parent
        # Supprimer les anciens paramètres
        config.pop("img_dir", None)
        config.pop("vid_dir", None)
        # Sauvegarder la migration
        save_config(config)

    return config

def restrict_permissions(path):
    """chmod 600 sur le fichier (POSIX uniquement ; un échec est ignoré)."""
    if os.name != "posix":
        return
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass

def save_config(config):
    """Sauvegarde la configuration (lisible par le seul propriétaire sur POSIX)"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    restrict_permissions(CONFIG_FILE)

def resolve_path(config, key):
    """
    Chemin de config[key] : une valeur relative est ancrée sur PROJECT_ROOT,
    jamais sur le dossier courant. La config elle-même n'est pas modifiée.
    Une clé absente prend sa valeur de DEFAULT_CONFIG.
    """
    chemin = Path(config.get(key, DEFAULT_CONFIG[key]))
    return chemin if chemin.is_absolute() else Path(PROJECT_ROOT) / chemin

def ensure_dirs(config):
    """Crée les répertoires nécessaires"""
    base = Path(config["download_dir"])
    (base / "images").mkdir(parents=True, exist_ok=True)
    (base / "videos").mkdir(parents=True, exist_ok=True)
    (base / "texts").mkdir(parents=True, exist_ok=True)
    resolve_path(config, "logs_dir").mkdir(parents=True, exist_ok=True)

def cleanup_logs(config):
    """Supprime TOUS les logs"""
    logs_dir = resolve_path(config, "logs_dir")
    if not logs_dir.exists():
        return 0

    deleted_count = 0
    for log_file in logs_dir.glob("*"):
        if log_file.is_file():
            log_file.unlink()
            deleted_count += 1

    return deleted_count

def cleanup_old_logs(config, max_age_days=10):
    """
    Supprime les logs > max_age_days jours, puis ne garde que les
    config["max_logs"] fichiers download_*.log les plus récents.
    """
    logs_dir = resolve_path(config, "logs_dir")
    if not logs_dir.exists():
        return

    cutoff_date = datetime.now() - timedelta(days=max_age_days)

    for log_file in logs_dir.glob("*"):
        if log_file.is_file():
            file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
            if file_time < cutoff_date:
                log_file.unlink()

    max_logs = max(0, int(config.get("max_logs", DEFAULT_CONFIG["max_logs"])))
    download_logs = sorted(
        (f for f in logs_dir.glob("download_*.log") if f.is_file()),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    for log_file in download_logs[max_logs:]:
        log_file.unlink()

def get_media_dirs(config):
    """Retourne les chemins complets des sous-dossiers médias"""
    base = Path(config["download_dir"])
    return {
        "img_dir": str(base / "images"),
        "vid_dir": str(base / "videos"),
        "text_dir": str(base / "texts")
    }
