#!/usr/bin/env python3
"""
Résolution du record cité par une citation (quote post, `app.bsky.embed.record`).

Une citation n'est pas un repost : le post bookmarké garde son propre contenu et
cite un autre record, qui peut être un post, mais aussi un feed generator, une
liste, un starter pack… ou un post supprimé, bloqué ou détaché.
"""
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from core import http as bsmb_http
from core.post_ref import INVALID_HANDLE, POST_COLLECTION, PostRef

# `$type` de la vue hydratée -> état du record cité
_ETATS_VUE = {
    "app.bsky.embed.record#viewNotFound": "not_found",
    "app.bsky.embed.record#viewBlocked": "blocked",
    "app.bsky.embed.record#viewDetached": "detached",
}


@dataclass(frozen=True)
class QuoteTarget:
    """Record cité par une citation.

    state : "post" (post accessible), "not_post" (autre collection : feed
    generator, liste…), "not_found", "blocked" ou "detached".
    url   : URL bsky.app du post cité (handle, ou DID à défaut) ; None si le
    record cité n'est pas un post.
    """

    url: str | None
    did: str
    rkey: str
    handle: str | None
    collection: str
    state: str

    @property
    def at_uri(self):
        return f"at://{self.did}/{self.collection}/{self.rkey}"


def _uri_depuis_embed(embed):
    """`uri` du record cité dans un embed brut (record ou recordWithMedia)."""
    record = embed.get("record", {})
    if embed.get("$type") == "app.bsky.embed.recordWithMedia":
        record = record.get("record", {})
    return record.get("uri", "")


def _record_de_la_vue(post_view):
    """Record cité (dict) dans la vue hydratée d'un post, {} s'il n'y en a pas."""
    embed = (post_view or {}).get("embed") or {}
    record = embed.get("record") or {}
    if str(embed.get("$type", "")).startswith("app.bsky.embed.recordWithMedia"):
        record = record.get("record") or {}
    return record


class QuoteResolver:
    def __init__(self, session=None):
        self.api_base = "https://bsky.social/xrpc/com.atproto.repo.getRecord"
        self.session = session

    def _http(self):
        """Session fournie, sinon session partagée de core.http."""
        return self.session or bsmb_http.get_session()

    def resolve(self, post_url, post_view=None):
        """
        Identifie le record cité par la citation `post_url`.

        post_view : vue hydratée (`postView`) du citant, si l'appelant l'a ; elle
        révèle les états `not_found` / `blocked` / `detached` sans requête.

        Returns: QuoteTarget, ou None si le record cité n'a pas pu être
        déterminé (URL invalide, pas de citation, erreur réseau ou serveur).
        """
        parts = urlparse(post_url).path.strip("/").split("/")
        if len(parts) < 4:
            return None

        etat = None
        cited_uri = ""
        record_vue = _record_de_la_vue(post_view)
        etat = _ETATS_VUE.get(str(record_vue.get("$type", "")))
        if etat:
            cited_uri = record_vue.get("uri", "")

        try:
            if not cited_uri:
                etat = None
                cited_uri = self._uri_du_record_cite(parts[1], parts[-1])
            uri_parts = cited_uri.split("/")
            if len(uri_parts) != 5 or uri_parts[0] != "at:" or not uri_parts[2] or not uri_parts[4]:
                return None
            did, collection, rkey = uri_parts[2], uri_parts[3], uri_parts[4]

            if collection != POST_COLLECTION:
                return QuoteTarget(None, did, rkey, None, collection, "not_post")

            if etat is None:
                etat = self._etat_du_post(did, rkey)
                if etat is None:
                    return None

            handle = None
            if etat == "post":
                handle = self._resolve_did_to_handle(did)
                if handle == INVALID_HANDLE:
                    handle = None
            url = PostRef(did, rkey, handle).web_url
            return QuoteTarget(url, did, rkey, handle, collection, etat)
        except Exception:
            return None

    def _uri_du_record_cite(self, actor, rkey):
        """Lit le record du citant (getRecord) et renvoie l'URI qu'il cite ('' si aucune)."""
        params = {"repo": actor, "collection": POST_COLLECTION, "rkey": rkey}
        resp = self._http().get(self.api_base, params=params, timeout=15)
        resp.raise_for_status()
        embed = resp.json().get("value", {}).get("embed", {})
        if embed.get("$type") not in ("app.bsky.embed.record", "app.bsky.embed.recordWithMedia"):
            return ""
        return _uri_depuis_embed(embed)

    def _etat_du_post(self, did, rkey):
        """'post' si le post cité existe, 'not_found' si getRecord répond 400, None sinon."""
        params = {"repo": did, "collection": POST_COLLECTION, "rkey": rkey}
        resp = self._http().get(self.api_base, params=params, timeout=15)
        if resp.status_code == 400:
            return "not_found"
        resp.raise_for_status()
        return "post"

    def _resolve_did_to_handle(self, did):
        """Résout un DID en handle via l'API"""
        try:
            profile_api = "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile"
            resp = self._http().get(profile_api, params={"actor": did}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("handle")
        except Exception:
            pass
        return None
