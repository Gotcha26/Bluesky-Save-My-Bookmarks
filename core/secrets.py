#!/usr/bin/env python3
"""
Stockage de l'App Password Bluesky.

Backend préféré : la bibliothèque optionnelle `keyring` (Credential Manager Windows,
Keychain macOS, Secret Service Linux), sous le service « bsmb » et le handle comme
nom d'utilisateur. Repli : la clé `bsky_app_password` de config.json (en clair).

Le mot de passe n'est jamais affiché ni journalisé par ce module.
"""
from core.config import save_config

SERVICE = "bsmb"
BACKEND_KEYRING = "keyring"
BACKEND_CONFIG = "config.json"


def _get_keyring():
    """Retourne le module keyring, ou None s'il n'est pas installé."""
    try:
        import keyring
    except ImportError:
        return None
    return keyring


def _probe(kr):
    """Vrai si le backend keyring répond (un backend absent lève une exception)."""
    try:
        kr.get_password(SERVICE, "__bsmb_probe__")
        return True
    except Exception:
        return False


def backend_name():
    """Backend utilisé pour stocker le secret : "keyring" ou "config.json"."""
    kr = _get_keyring()
    return BACKEND_KEYRING if kr is not None and _probe(kr) else BACKEND_CONFIG


def store_app_password(config, handle, pwd):
    """
    Enregistre l'App Password. Dans keyring si possible (la clé de config est alors
    vidée), sinon dans config["bsky_app_password"]. Ne sauvegarde pas config.json.

    Returns:
        str: backend effectivement utilisé ("keyring" ou "config.json")
    """
    kr = _get_keyring()
    if kr is not None:
        try:
            kr.set_password(SERVICE, handle, pwd)
            config["bsky_app_password"] = ""
            return BACKEND_KEYRING
        except Exception:
            pass
    config["bsky_app_password"] = pwd
    return BACKEND_CONFIG


def load_app_password(config, handle):
    """App Password depuis keyring, sinon depuis config.json ; "" si absent."""
    kr = _get_keyring()
    if kr is not None and handle:
        try:
            pwd = kr.get_password(SERVICE, handle)
            if pwd:
                return pwd
        except Exception:
            pass
    return config.get("bsky_app_password", "") or ""


def delete_app_password(config, handle):
    """Supprime le secret de keyring (s'il y est) et de config.json. Ne lève jamais."""
    kr = _get_keyring()
    if kr is not None and handle:
        try:
            kr.delete_password(SERVICE, handle)
        except Exception:
            pass
    config["bsky_app_password"] = ""


def migrate_secret_to_keyring(config):
    """
    Déplace un App Password présent en clair dans config.json vers keyring, puis
    vide la clé et sauvegarde la config. Sans effet si keyring est absent ou défaillant.

    Returns:
        bool: True si le secret a été migré
    """
    handle = config.get("bsky_handle", "")
    pwd = config.get("bsky_app_password", "")
    if not handle or not pwd:
        return False
    kr = _get_keyring()
    if kr is None:
        return False
    try:
        kr.set_password(SERVICE, handle, pwd)
    except Exception:
        return False
    config["bsky_app_password"] = ""
    save_config(config)
    return True
