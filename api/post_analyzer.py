#!/usr/bin/env python3
"""
Analyse préalable d'un post Bluesky pour déterminer son type et sa disponibilité
"""
import requests
from urllib.parse import urlparse
from enum import Enum

from core.post_ref import PostRef

class PostType(Enum):
    ERROR_500 = "error_500"
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
    def __init__(self):
        self.api_base = "https://bsky.social/xrpc/com.atproto.repo.getRecord"
    
    def analyze(self, post_url):
        """
        Analyse un post et retourne son type + données associées
        Returns: (PostType, data_dict, debug_info)
        """
        parts = urlparse(post_url).path.strip("/").split("/")
        if len(parts) < 4:
            return PostType.UNKNOWN, {}, {"error": "URL invalide"}
        
        # Le segment de l'URL est un handle ou un DID ; getRecord accepte les deux.
        handle = parts[1]
        post_id = parts[-1]
        url_did = handle if handle.startswith("did:") else None
        identity = _identity(url_did, post_id)

        try:
            params = {
                "repo": url_did or handle,
                "collection": "app.bsky.feed.post",
                "rkey": post_id
            }
            resp = requests.get(self.api_base, params=params, timeout=15)

            if resp.status_code == 400:
                return PostType.ERROR_400, {"handle": handle, "post_id": post_id, **identity}, {"status": 400}
            elif resp.status_code == 500:
                return PostType.ERROR_500, {"handle": handle, "post_id": post_id, **identity}, {"status": 500}

            resp.raise_for_status()
            data = resp.json()

        except Exception as e:
            return PostType.UNKNOWN, {"handle": handle, "post_id": post_id, **identity}, {"error": str(e)}

        value = data.get("value", {})
        embed = value.get("embed", {})
        embed_type = embed.get("$type", "")

        # Le DID figure dans l'`uri` de la réponse : aucun appel supplémentaire
        if not identity:
            uri_parts = data.get("uri", "").split("/")
            identity = _identity(uri_parts[2] if len(uri_parts) > 2 else None, post_id)

        result_data = {
            "handle": handle,
            "post_id": post_id,
            **identity,
            "created_at": value.get("createdAt", ""),
            "text": value.get("text", ""),
            "embed_type": embed_type
        }
        
        debug_info = {
            "embed_type": embed_type,
            "has_embed": bool(embed),
            "full_data": data
        }
        
        # 1. Vidéo
        if embed_type == "app.bsky.embed.video":
            video_blob = embed.get("video", {})
            cid = video_blob.get("ref", {}).get("$link")
            if cid:
                uri = data.get("uri", "")
                did = uri.split("/")[2] if "/" in uri else None
                if did:
                    result_data["video_url"] = f"https://bsky.social/xrpc/com.atproto.sync.getBlob?did={did}&cid={cid}"
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
                    uri = data.get("uri", "")
                    did = uri.split("/")[2] if "/" in uri else None
                    if did:
                        result_data["video_url"] = f"https://bsky.social/xrpc/com.atproto.sync.getBlob?did={did}&cid={cid}"
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