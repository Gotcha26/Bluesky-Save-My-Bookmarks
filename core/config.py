#!/usr/bin/env python3
"""Configuration centralisée pour BSMB"""
import os
import json
from pathlib import Path
from datetime import datetime, timedelta

CONFIG_FILE = Path("config.json")

DEFAULT_CONFIG = {
    "download_dir": str(Path.home() / "Downloads" / "BSMB"),
    "token_file": "Token-Bearer.txt",
    "urls_file": "urls.txt",
    "db_file": "bsmb.db",
    "logs_dir": "logs",
    "max_logs": 5,
    "max_filename_len": 64,
    "min_postid_short": 4,
    "index_digits": 1,
    "bsky_handle": "",
    "bsky_app_password": ""
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
        config = {**DEFAULT_CONFIG, **json.load(open(CONFIG_FILE, "r", encoding="utf-8"))}
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

def save_config(config):
    """Sauvegarde la configuration"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def ensure_dirs(config):
    """Crée les répertoires nécessaires"""
    base = Path(config["download_dir"])
    (base / "images").mkdir(parents=True, exist_ok=True)
    (base / "videos").mkdir(parents=True, exist_ok=True)
    (base / "texts").mkdir(parents=True, exist_ok=True)
    Path(config["logs_dir"]).mkdir(parents=True, exist_ok=True)

def cleanup_logs(config):
    """Supprime TOUS les logs"""
    logs_dir = Path(config["logs_dir"])
    if not logs_dir.exists():
        return 0
    
    deleted_count = 0
    for log_file in logs_dir.glob("*"):
        if log_file.is_file():
            log_file.unlink()
            deleted_count += 1
    
    return deleted_count

def cleanup_old_logs(config, max_age_days=10):
    """Supprime les logs > max_age_days jours"""
    logs_dir = Path(config["logs_dir"])
    if not logs_dir.exists():
        return
    
    cutoff_date = datetime.now() - timedelta(days=max_age_days)
    
    for log_file in logs_dir.glob("*"):
        if log_file.is_file():
            file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
            if file_time < cutoff_date:
                log_file.unlink()

def get_media_dirs(config):
    """Retourne les chemins complets des sous-dossiers médias"""
    base = Path(config["download_dir"])
    return {
        "img_dir": str(base / "images"),
        "vid_dir": str(base / "videos"),
        "text_dir": str(base / "texts")
    }