#!/usr/bin/env python3
"""
Analyse préalable d'un post Bluesky pour déterminer son type et sa disponibilité
"""

from enum import Enum
from urllib.parse import urlparse

from core import http as bsmb_http
from core.post_ref import PostRef, _is_valid_handle


class PostType(Enum):
    ERROR_500 = "error_500"
    ERROR_429 = "error_429"
    ERROR_400 = "error_400"
    QUOTE = "quote"
    REPOST = "quote"  # alias déprécié : un repost n'est jamais bookmarké, c'est une citation
    IMAGES = "images"
    VIDEO = "video"
    TEXT_ONLY = "text_only"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


def _external_info(embed_external):
    """Champs utiles d'un `external` brut ({} s'il n'a pas d'URI)."""
    uri = embed_external.get("uri")
    if not uri:
        return {}
    return {
        "uri": uri,
        "title": embed_external.get("title", ""),
        "description": embed_external.get("description", ""),
        "thumb_cid": embed_external.get("thumb", {}).get("ref", {}).get("$link"),
    }


def _identity(did, rkey):
    """Champs d'identité canonique ({} tant que le DID est inconnu)."""
    if not did:
        return {}
    return {"did": did, "at_uri": PostRef(did, rkey).at_uri}


class PostAnalyzer:
    def __init__(self, session=None):
        self.api_base = "https://bsky.social/xrpc/com.atproto.repo.getRecord"
        self.session = session

    def _http(self):
        """Session fournie, sinon session partagée de core.http."""
        return self.session or bsmb_http.get_session()

    def analyze(self, post_url, post_view=None):
        """
        Analyse un post et retourne son type + données associées
        Returns: (PostType, data_dict, debug_info)

        post_view : vue hydratée du post (`postView` de getBookmarks). Si elle porte un
        `record`, l'analyse se fait sans aucune requête (le record y est au même format
        que la réponse de getRecord) et `data["view_embed"]` reçoit l'embed au format
        `#view` (`playlist`, `fullsize`, `thumbnail`…). Sinon, repli sur getRecord.
        `labels` et `viewer` sont ignorés.
        """
        parts = urlparse(post_url).path.strip("/").split("/")
        if len(parts) < 4:
            return PostType.UNKNOWN, {}, {"error": "URL invalide"}

        if post_view and isinstance(post_view.get("record"), dict):
            return self._analyze_view(post_url, post_view)

        # Le segment de l'URL est un handle ou un DID ; getRecord accepte les deux.
        handle = parts[1]
        post_id = parts[-1]
        url_did = handle if handle.startswith("did:") else None
        identity = _identity(url_did, post_id)

        try:
            params = {"repo": url_did or handle, "collection": "app.bsky.feed.post", "rkey": post_id}
            resp = self._http().get(self.api_base, params=params, timeout=15)

            if resp.status_code == 400:
                return PostType.ERROR_400, {"handle": handle, "post_id": post_id, **identity}, {"status": 400}
            elif resp.status_code == 429:
                # Encore limité après les reprises de core.http : à retenter plus tard
                return PostType.ERROR_429, {"handle": handle, "post_id": post_id, **identity}, {"status": 429}
            elif resp.status_code >= 500:
                # 5xx encore là après les reprises (502/503/504 comprises)
                return (
                    PostType.ERROR_500,
                    {"handle": handle, "post_id": post_id, **identity},
                    {"status": resp.status_code},
                )

            resp.raise_for_status()
            data = resp.json()

        except Exception as e:
            return PostType.UNKNOWN, {"handle": handle, "post_id": post_id, **identity}, {"error": str(e)}

        return self._classify(data.get("value", {}), data.get("uri", ""), handle, post_id, identity, data)

    def _analyze_view(self, post_url, post_view):
        """Classe un post à partir de sa vue hydratée (`postView` de getBookmarks), sans requête."""
        parts = urlparse(post_url).path.strip("/").split("/")
        uri = post_view.get("uri", "")
        uri_parts = uri.split("/")
        author = post_view.get("author") or {}
        did = author.get("did") or (uri_parts[2] if len(uri_parts) > 2 else None)
        handle = author.get("handle")
        if not _is_valid_handle(handle):
            handle = parts[1]  # handle.invalid : comme getRecord, retombe sur le segment d'URL (DID)
        post_id = uri_parts[-1] if len(uri_parts) > 4 else parts[-1]
        return self._classify(
            post_view["record"],
            uri,
            handle,
            post_id,
            _identity(did, post_id),
            post_view,
            view_embed=post_view.get("embed"),
        )

    def _classify(self, value, uri, handle, post_id, identity, full_data, view_embed=None):
        """
        Classe un record `app.bsky.feed.post` (format record : `app.bsky.embed.*`).
        Commun au chemin getRecord (`value`) et au chemin postView (`post_view["record"]`).

        uri: AT-URI du post ; identity: champs d'identité déjà connus ({} si le DID est inconnu) ;
        full_data: réponse brute, conservée dans debug_info ;
        view_embed: embed au format `#view` (playlist, fullsize…), si la vue hydratée est connue.
        """
        embed = value.get("embed", {})
        embed_type = embed.get("$type", "")

        # Le DID figure dans l'`uri` de la réponse : aucun appel supplémentaire
        if not identity:
            uri_parts = uri.split("/")
            identity = _identity(uri_parts[2] if len(uri_parts) > 2 else None, post_id)

        result_data = {
            "handle": handle,
            "post_id": post_id,
            **identity,
            "created_at": value.get("createdAt", ""),
            "text": value.get("text", ""),
            "embed_type": embed_type,
        }
        if view_embed is not None:
            result_data["view_embed"] = view_embed

        debug_info = {"embed_type": embed_type, "has_embed": bool(embed), "full_data": full_data}

        # 1. Vidéo
        if embed_type == "app.bsky.embed.video":
            video_blob = embed.get("video", {})
            cid = video_blob.get("ref", {}).get("$link")
            if cid:
                did = uri.split("/")[2] if "/" in uri else None
                if did:
                    result_data["video_url"] = (
                        f"https://bsky.social/xrpc/com.atproto.sync.getBlob?did={did}&cid={cid}"
                    )
                    result_data["video_cid"] = cid
                    result_data["video_mime"] = video_blob.get("mimeType", "video/mp4")
                    result_data["video_size"] = video_blob.get("size", 0)
                    return PostType.VIDEO, result_data, debug_info

        # 2. Images directes
        if embed_type == "app.bsky.embed.images":
            images_list = embed.get("images", [])
            images = []
            for img in images_list:
                img_ref = img.get("image", {}).get("ref", {}).get("$link")
                if img_ref:
                    images.append(f"https://cdn.bsky.app/img/feed_fullsize/plain/{img_ref}@jpeg")

            if images:
                result_data["images"] = images
                result_data["image_count"] = len(images)
                return PostType.IMAGES, result_data, debug_info

        # 2 bis. Carte de lien / GIF (external)
        if embed_type == "app.bsky.embed.external":
            external = _external_info(embed.get("external", {}))
            if external:
                result_data["external"] = external
                return PostType.EXTERNAL, result_data, debug_info

        # 3. Citation (quote post) sans média : le post citant a son propre texte
        if embed_type == "app.bsky.embed.record":
            result_data["is_quote"] = True
            result_data["quote_uri"] = embed.get("record", {}).get("uri", "")
            return PostType.QUOTE, result_data, debug_info

        # 4. Citation avec média : le média du citant prime, `is_quote` signale le record cité
        if embed_type == "app.bsky.embed.recordWithMedia":
            media = embed.get("media", {})
            result_data["is_quote"] = True
            result_data["quote_uri"] = embed.get("record", {}).get("record", {}).get("uri", "")
            media_type = media.get("$type", "")

            if media_type == "app.bsky.embed.video":
                video_blob = media.get("video", {})
                cid = video_blob.get("ref", {}).get("$link")
                if cid:
                    did = uri.split("/")[2] if "/" in uri else None
                    if did:
                        result_data["video_url"] = (
                            f"https://bsky.social/xrpc/com.atproto.sync.getBlob?did={did}&cid={cid}"
                        )
                        result_data["video_cid"] = cid
                        return PostType.VIDEO, result_data, debug_info

            if media_type == "app.bsky.embed.images":
                images_list = media.get("images", [])
                images = []
                for img in images_list:
                    img_ref = img.get("image", {}).get("ref", {}).get("$link")
                    if img_ref:
                        images.append(f"https://cdn.bsky.app/img/feed_fullsize/plain/{img_ref}@jpeg")

                if images:
                    result_data["images"] = images
                    result_data["image_count"] = len(images)
                    return PostType.IMAGES, result_data, debug_info

            if media_type == "app.bsky.embed.external":
                external = _external_info(media.get("external", {}))
                if external:
                    result_data["external"] = external
                    return PostType.EXTERNAL, result_data, debug_info

            # Média absent ou non pris en charge : le post reste une citation
            return PostType.QUOTE, result_data, debug_info

        # 5. Texte seul
        if result_data["text"] and not embed:
            return PostType.TEXT_ONLY, result_data, debug_info

        # 6. Inconnu
        return PostType.UNKNOWN, result_data, debug_info
