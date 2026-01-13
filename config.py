#!/usr/bin/env python3
"""Configuration centralisée pour BSMB"""
import os
import json
from pathlib import Path
from datetime import datetime, timedelta

CONFIG_FILE = Path("config.json")

DEFAULT_CONFIG = {
    "img_dir": os.path.expandvars(r"%USERPROFILE%\Downloads\BSMB\images"),
    "vid_dir": os.path.expandvars(r"%USERPROFILE%\Downloads\BSMB\videos"),
    "token_file": "Token-Bearer.txt",
    "urls_file": "urls.txt",
    "db_file": "bsmb.db",
    "logs_dir": "logs",
    "max_logs": 5,
    "max_filename_len": 64,
    "min_postid_short": 4,
    "index_digits": 1
}

def get_default_paths():
    """Retourne les chemins par défaut (utile pour les scripts)"""
    return {
        "img_dir": os.path.expandvars(r"%USERPROFILE%\Downloads\BSMB\images"),
        "vid_dir": os.path.expandvars(r"%USERPROFILE%\Downloads\BSMB\videos")
    }

def load_config():
    """Charge la config ou crée celle par défaut"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return DEFAULT_CONFIG.copy()

def save_config(config):
    """Sauvegarde la configuration"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def ensure_dirs(config):
    """Crée les répertoires nécessaires"""
    Path(config["img_dir"]).mkdir(parents=True, exist_ok=True)
    Path(config["vid_dir"]).mkdir(parents=True, exist_ok=True)
    Path(config["logs_dir"]).mkdir(parents=True, exist_ok=True)

def cleanup_old_logs(config):
    """Supprime les anciens logs en gardant les N plus récents"""
    logs_dir = Path(config["logs_dir"])
    if not logs_dir.exists():
        return
    
    # Lister tous les fichiers .log et .txt dans logs/
    log_files = sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    txt_files = sorted(logs_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    max_logs = config.get("max_logs", 5)
    
    # Supprimer les anciens logs
    for old_log in log_files[max_logs:]:
        old_log.unlink()
    
    # Supprimer les anciens txt (failed_downloads, etc.)
    for old_txt in txt_files[max_logs:]:
        old_txt.unlink()

def cleanup_logs(config):
    """Supprime TOUS les logs"""
    logs_dir = Path(config["logs_dir"])
    if not logs_dir.exists():
        return
    
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