#!/usr/bin/env python3
"""
Authentification Bluesky via createSession
Obtient un token Bearer automatiquement à partir du handle + App Password.
"""
import requests
from pathlib import Path

ENDPOINT = "https://bsky.social/xrpc/com.atproto.server.createSession"


class AuthError(Exception):
    """Erreur d'authentification Bluesky."""
    pass


def create_session(handle, app_password):
    """
    Authentification via com.atproto.server.createSession.

    Args:
        handle: Handle Bluesky (ex: "user.bsky.social")
        app_password: App Password (format xxxx-xxxx-xxxx-xxxx)

    Returns:
        str: Token complet "Bearer xxx" pret a l'emploi

    Raises:
        AuthError: En cas d'echec d'authentification
    """
    try:
        resp = requests.post(
            ENDPOINT,
            json={"identifier": handle, "password": app_password},
            timeout=15,
        )

        if resp.status_code == 401:
            raise AuthError("Identifiants invalides. Vérifiez votre handle et App Password.")

        if resp.status_code == 429:
            raise AuthError("Trop de tentatives. Réessayez dans quelques minutes.")

        resp.raise_for_status()
        data = resp.json()

        access_jwt = data.get("accessJwt")
        if not access_jwt:
            raise AuthError("Réponse inattendue du serveur (pas de accessJwt).")

        return f"Bearer {access_jwt}"

    except requests.exceptions.ConnectionError:
        raise AuthError("Impossible de se connecter à bsky.social. Vérifiez votre connexion.")
    except requests.exceptions.Timeout:
        raise AuthError("Timeout lors de la connexion à bsky.social.")
    except requests.exceptions.HTTPError as e:
        raise AuthError(f"Erreur HTTP {e.response.status_code}")


def get_token(config):
    """
    Obtient un token Bearer, par ordre de priorité :
    1. createSession si handle + app_password sont configurés
    2. Lecture de Token-Bearer.txt (fallback)

    Returns:
        str: Token "Bearer xxx" ou None si aucun moyen d'authentification
    """
    handle = config.get("bsky_handle", "")
    app_password = config.get("bsky_app_password", "")

    # Mode 1 : createSession
    if handle and app_password:
        return create_session(handle, app_password)

    # Mode 2 : Fichier Token-Bearer.txt (fallback)
    token_file = Path(config.get("token_file", "Token-Bearer.txt"))
    if token_file.exists():
        content = token_file.read_text(encoding="utf-8").strip()
        if content.startswith("Bearer "):
            return content

    return None


def has_credentials(config):
    """Vérifie si des credentials sont configurés."""
    return bool(config.get("bsky_handle")) and bool(config.get("bsky_app_password"))
