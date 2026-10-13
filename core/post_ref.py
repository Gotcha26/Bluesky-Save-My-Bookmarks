#!/usr/bin/env python3
"""
Identité d'un post Bluesky : AT-URI canonique (DID + rkey).

Le handle n'est qu'un alias d'affichage, susceptible de changer ou de valoir
`handle.invalid` quand l'AppView ne peut pas le vérifier.
"""

from dataclasses import dataclass
from urllib.parse import urlparse

from core import http as bsmb_http

INVALID_HANDLE = "handle.invalid"
PUBLIC_API = "https://public.api.bsky.app"
POST_COLLECTION = "app.bsky.feed.post"


def _is_valid_handle(handle):
    return bool(handle) and handle != INVALID_HANDLE


@dataclass(frozen=True)
class PostRef:
    """Référence à un post. `did` vaut None si seul le handle est connu."""

    did: str | None
    rkey: str
    handle: str | None = None

    @property
    def at_uri(self):
        """AT-URI canonique, ou None tant que le DID n'est pas connu."""
        if not self.did:
            return None
        return f"at://{self.did}/{POST_COLLECTION}/{self.rkey}"

    @property
    def web_url(self):
        """URL bsky.app : handle si valide, sinon DID."""
        actor = self.handle if _is_valid_handle(self.handle) else self.did
        return f"https://bsky.app/profile/{actor}/post/{self.rkey}"

    @classmethod
    def from_bsky_url(cls, url):
        """Parse `https://bsky.app/profile/<handle|did>/post/<rkey>`."""
        parts = urlparse(url or "").path.strip("/").split("/")
        if len(parts) != 4 or parts[0] != "profile" or parts[2] != "post" or not parts[1] or not parts[3]:
            raise ValueError(f"URL de post invalide : {url!r}")
        actor, rkey = parts[1], parts[3]
        if actor.startswith("did:"):
            return cls(did=actor, rkey=rkey)
        return cls(did=None, rkey=rkey, handle=actor if _is_valid_handle(actor) else None)

    @classmethod
    def from_at_uri(cls, uri, handle=None):
        """Parse `at://<did>/app.bsky.feed.post/<rkey>`."""
        parts = (uri or "").split("/")
        if (
            len(parts) != 5
            or parts[0] != "at:"
            or parts[1] != ""
            or not parts[2]
            or parts[3] != POST_COLLECTION
            or not parts[4]
        ):
            raise ValueError(f"AT-URI de post invalide : {uri!r}")
        return cls(did=parts[2], rkey=parts[4], handle=handle)


def resolve_handle(handle, session=None):
    """Résout un handle en DID (com.atproto.identity.resolveHandle).

    Utilitaire : à ne pas appeler post par post. Lève une exception `requests`
    en cas d'échec réseau ou HTTP.
    """
    resp = (session or bsmb_http.get_session()).get(
        f"{PUBLIC_API}/xrpc/com.atproto.identity.resolveHandle",
        params={"handle": handle},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["did"]
