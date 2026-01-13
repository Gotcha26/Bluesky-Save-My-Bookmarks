#!/usr/bin/env python3
"""
post_analyzer.py
Analyse préalable d'un post Bluesky pour déterminer son type et sa disponibilité
"""
import requests
from urllib.parse import urlparse
from enum import Enum

class PostType(Enum):
    ERROR_500 = "error_500"
    ERROR_400 = "error_400"
    REPOST = "repost"
    IMAGES = "images"
    VIDEO = "video"
    TEXT_ONLY = "text_only"
    UNKNOWN = "unknown"

class PostAnalyzer:
    def __init__(self):
        self.api_base = "https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread"
    
    def analyze(self, post_url):
        """
        Analyse un post et retourne son type + données associées
        Returns: (PostType, data_dict, debug_info)
        """
        parts = urlparse(post_url).path.strip("/").split("/")
        if len(parts) < 4:
            return PostType.UNKNOWN, {}, {"error": "URL invalide"}
        
        handle = parts[1]
        post_id = parts[-1]
        
        # Appel API
        try:
            api_url = f"{self.api_base}?uri=at://{handle}/app.bsky.feed.post/{post_id}"
            resp = requests.get(api_url, timeout=15)
            
            # Gestion erreurs HTTP
            if resp.status_code == 400:
                return PostType.ERROR_400, {"handle": handle, "post_id": post_id}, {"status": 400}
            elif resp.status_code == 500:
                return PostType.ERROR_500, {"handle": handle, "post_id": post_id}, {"status": 500}
            
            resp.raise_for_status()
            data = resp.json()
            
        except Exception as e:
            return PostType.UNKNOWN, {"handle": handle, "post_id": post_id}, {"error": str(e)}
        
        # Analyse du contenu
        post = data.get("thread", {}).get("post", {})
        author = post.get("author", {})
        record = post.get("record", {})
        embed = post.get("embed", {})
        embed_type = embed.get("$type", "")
        
        result_data = {
            "handle": author.get("handle", handle),
            "post_id": post_id,
            "created_at": record.get("createdAt", ""),
            "text": record.get("text", ""),
            "embed_type": embed_type
        }
        
        debug_info = {
            "embed_type": embed_type,
            "has_embed": bool(embed),
            "full_data": data
        }
        
        # Détection type - ORDRE IMPORTANT
        
        # 1. Vidéo (vérifier AVANT images car prioritaire)
        if "video" in embed_type.lower():
            video_blob = embed.get("video", {})
            cid = video_blob.get("ref", {}).get("$link")
            if cid:
                uri = post.get("uri", "")
                did = uri.split("/")[2] if "/" in uri else None
                if did:
                    result_data["video_url"] = f"https://bsky.social/xrpc/com.atproto.sync.getBlob?did={did}&cid={cid}"
                    result_data["video_cid"] = cid
                    return PostType.VIDEO, result_data, debug_info
        
        # 2. Repost
        if embed_type == "app.bsky.embed.record#view":
            cited_record = embed.get("record", {})
            cited_embeds = cited_record.get("embeds", [])
            
            # Repost avec média cité
            for emb in cited_embeds:
                emb_type = emb.get("$type", "")
                if "images" in emb_type.lower():
                    result_data["repost_has_images"] = True
                    return PostType.REPOST, result_data, debug_info
                elif "video" in emb_type.lower():
                    result_data["repost_has_video"] = True
                    return PostType.REPOST, result_data, debug_info
            
            # Repost sans média accessible
            return PostType.REPOST, result_data, debug_info
        
        # 3. Images directes
        if embed_type == "app.bsky.embed.images#view":
            images = [img.get("fullsize") for img in embed.get("images", []) if img.get("fullsize")]
            result_data["images"] = images
            result_data["image_count"] = len(images)
            return PostType.IMAGES, result_data, debug_info
        
        # 4. Quote post avec média
        if embed_type == "app.bsky.embed.recordWithMedia#view":
            media = embed.get("media", {})
            media_type = media.get("$type", "")
            
            # Vidéo dans recordWithMedia
            if "video" in media_type.lower():
                video_blob = media.get("video", {})
                cid = video_blob.get("ref", {}).get("$link")
                if cid:
                    uri = post.get("uri", "")
                    did = uri.split("/")[2] if "/" in uri else None
                    if did:
                        result_data["video_url"] = f"https://bsky.social/xrpc/com.atproto.sync.getBlob?did={did}&cid={cid}"
                        result_data["video_cid"] = cid
                        return PostType.VIDEO, result_data, debug_info
            
            # Images dans recordWithMedia
            if media_type == "app.bsky.embed.images#view":
                images = [img.get("fullsize") for img in media.get("images", []) if img.get("fullsize")]
                result_data["images"] = images
                result_data["image_count"] = len(images)
                return PostType.IMAGES, result_data, debug_info
        
        # 5. Texte seul
        if result_data["text"]:
            return PostType.TEXT_ONLY, result_data, debug_info
        
        # 6. Inconnu (cas edge)
        return PostType.UNKNOWN, result_data, debug_info