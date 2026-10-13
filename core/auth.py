#!/usr/bin/env python3
"""
Authentification Bluesky via createSession
Obtient un token Bearer automatiquement à partir du handle + App Password.
"""
import requests

from core import http as bsmb_http
from core.config import resolve_path
from core.secret_store import load_app_password

ENDPOINT = "https://bsky.social/xrpc/com.atproto.server.createSession"


DEFAULT_PDS_URL = "https://bsky.social"


class AuthError(Exception):
    """Erreur d'authentification Bluesky."""
    pass


class NetworkError(AuthError):
    """Échec réseau (connexion, timeout, HTTP 5xx) pendant l'authentification.

    Sous-classe d'AuthError : le code existant qui attrape AuthError reste valable."""
    pass


def _extract_pds_url(did_doc):
    """Lit le PDS du compte dans le didDoc (service #atproto_pds), sinon bsky.social."""
    if isinstance(did_doc, dict):
        for service in did_doc.get("service") or []:
            if isinstance(service, dict) and service.get("id") == "#atproto_pds":
                endpoint = service.get("serviceEndpoint")
                if isinstance(endpoint, str) and endpoint:
                    return endpoint
    return DEFAULT_PDS_URL


def create_session(handle, app_password, session=None):
    """
    Authentification via com.atproto.server.createSession.

    Args:
        handle: Handle Bluesky (ex: "user.bsky.social")
        app_password: App Password (format xxxx-xxxx-xxxx-xxxx)
        session: session HTTP (défaut : session partagée de core.http)

    Returns:
        dict: {
            "token": str,        # Token complet "Bearer xxx" prêt à l'emploi
            "refresh_jwt": str|None,
            "did": str|None,
            "pds_url": str,      # PDS réel du compte (didDoc), sinon bsky.social
        }

    Raises:
        AuthError: En cas d'echec d'authentification
    """
    try:
        resp = (session or bsmb_http.get_session()).post(
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

        return {
            "token": f"Bearer {access_jwt}",
            "refresh_jwt": data.get("refreshJwt"),
            "did": data.get("did"),
            "pds_url": _extract_pds_url(data.get("didDoc")),
        }

    except requests.exceptions.ConnectionError:
        raise NetworkError("Impossible de se connecter à bsky.social. Vérifiez votre connexion.")
    except requests.exceptions.Timeout:
        raise NetworkError("Timeout lors de la connexion à bsky.social.")
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code
        if status >= 500:
            raise NetworkError(f"Erreur HTTP {status}")
        raise AuthError(f"Erreur HTTP {status}")


def refresh_session(refresh_jwt, pds_url, session=None):
    """
    Renouvelle le token d'accès via com.atproto.server.refreshSession.

    Le jeton de rafraîchissement (`refreshJwt` de createSession) est envoyé en
    `Authorization: Bearer` au PDS du compte ; la réponse apporte un nouvel accessJwt
    ET un nouveau refreshJwt (l'ancien est alors invalide).

    Args:
        refresh_jwt: jeton de rafraîchissement (sans préfixe "Bearer")
        pds_url: PDS du compte (le jeton n'est valable que sur celui-ci)
        session: session HTTP (défaut : session partagée de core.http)

    Returns:
        dict: même forme que create_session() ({"token", "refresh_jwt", "did", "pds_url"})

    Raises:
        AuthError: jeton de rafraîchissement refusé ou expiré
        NetworkError: échec réseau (connexion, timeout, HTTP 5xx)
    """
    base = (pds_url or DEFAULT_PDS_URL).rstrip("/")
    try:
        resp = (session or bsmb_http.get_session()).post(
            f"{base}/xrpc/com.atproto.server.refreshSession",
            headers={"Authorization": f"Bearer {refresh_jwt}"},
            timeout=15,
        )

        if resp.status_code in (400, 401):
            raise AuthError("Jeton de rafraîchissement refusé ou expiré : reconnectez votre compte.")
        if resp.status_code == 429:
            raise AuthError("Trop de tentatives. Réessayez dans quelques minutes.")

        resp.raise_for_status()
        data = resp.json()

        access_jwt = data.get("accessJwt")
        if not access_jwt:
            raise AuthError("Réponse inattendue du serveur (pas de accessJwt).")

        did_doc = data.get("didDoc")
        return {
            "token": f"Bearer {access_jwt}",
            "refresh_jwt": data.get("refreshJwt"),
            "did": data.get("did"),
            "pds_url": _extract_pds_url(did_doc) if did_doc else base,
        }

    except requests.exceptions.ConnectionError:
        raise NetworkError("Impossible de se connecter au serveur Bluesky. Vérifiez votre connexion.")
    except requests.exceptions.Timeout:
        raise NetworkError("Timeout lors du renouvellement de la session.")
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code
        if status >= 500:
            raise NetworkError(f"Erreur HTTP {status}")
        raise AuthError(f"Erreur HTTP {status}")


def get_session(config):
    """
    Obtient une session complète, par ordre de priorité :
    1. createSession si handle + app_password sont configurés
    2. Lecture de Token-Bearer.txt (fallback) ; le PDS vient alors de
       config["pds_url"] (bsky.social si inconnu), did et refresh_jwt valent None.

    Returns:
        dict: {"token", "refresh_jwt", "did", "pds_url"} ou None si aucun moyen
        d'authentification
    """
    handle = config.get("bsky_handle", "")
    app_password = load_app_password(config, handle)

    # Mode 1 : createSession
    if handle and app_password:
        return create_session(handle, app_password)

    # Mode 2 : Fichier Token-Bearer.txt (fallback)
    token_file = resolve_path(config, "token_file")
    if token_file.exists():
        content = token_file.read_text(encoding="utf-8").strip()
        if content.startswith("Bearer "):
            return {
                "token": content,
                "refresh_jwt": None,
                "did": None,
                "pds_url": config.get("pds_url") or DEFAULT_PDS_URL,
            }

    return None


def get_token(config):
    """
    Obtient un token Bearer (voir get_session).

    Returns:
        str: Token "Bearer xxx" ou None si aucun moyen d'authentification
    """
    session = get_session(config)
    return session["token"] if session else None


def has_credentials(config):
    """Vérifie si des credentials sont configurés."""
    handle = config.get("bsky_handle", "")
    return bool(handle) and bool(load_app_password(config, handle))
