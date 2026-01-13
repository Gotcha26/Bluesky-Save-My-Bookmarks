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
        # Utiliser l'API getRecord comme bsky_post_media.py pour avoir la structure brute
        self.api_base = "https://bsky.social/xrpc/com.atproto.repo.getRecord"
    
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
        
        # Appel API avec paramètres getRecord
        try:
            params = {
                "repo": handle,
                "collection": "app.bsky.feed.post",
                "rkey": post_id
            }
            resp = requests.get(self.api_base, params=params, timeout=15)
            
            # Gestion erreurs HTTP
            if resp.status_code == 400:
                return PostType.ERROR_400, {"handle": handle, "post_id": post_id}, {"status": 400}
            elif resp.status_code == 500:
                return PostType.ERROR_500, {"handle": handle, "post_id": post_id}, {"status": 500}
            
            resp.raise_for_status()
            data = resp.json()
            
        except Exception as e:
            return PostType.UNKNOWN, {"handle": handle, "post_id": post_id}, {"error": str(e)}
        
        # Analyse du contenu (structure brute)
        value = data.get("value", {})
        embed = value.get("embed", {})
        embed_type = embed.get("$type", "")
        
        result_data = {
            "handle": handle,
            "post_id": post_id,
            "created_at": value.get("createdAt", ""),
            "text": value.get("text", ""),
            "embed_type": embed_type
        }
        
        debug_info = {
            "embed_type": embed_type,
            "has_embed": bool(embed),
            "full_data": data
        }
        
        # Détection type - ORDRE IMPORTANT
        
        # 1. Vidéo (structure brute : app.bsky.embed.video)
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
        
        # 2. Images directes (structure brute : app.bsky.embed.images)
        if embed_type == "app.bsky.embed.images":
            images_list = embed.get("images", [])
            # Dans la structure brute, les images ont "image.ref.$link" comme CID
            images = []
            for img in images_list:
                img_ref = img.get("image", {}).get("ref", {}).get("$link")
                if img_ref:
                    # Reconstruction URL fullsize à partir du CID
                    images.append(f"https://cdn.bsky.app/img/feed_fullsize/plain/{img_ref}@jpeg")
            
            if images:
                result_data["images"] = images
                result_data["image_count"] = len(images)
                return PostType.IMAGES, result_data, debug_info
        
        # 3. Repost (structure brute : app.bsky.embed.record)
        if embed_type == "app.bsky.embed.record":
            # Dans la structure brute, on ne peut pas facilement accéder au contenu du repost
            # Il faudrait faire une autre requête API
            result_data["is_repost"] = True
            return PostType.REPOST, result_data, debug_info
        
        # 4. Quote post avec média (structure brute : app.bsky.embed.recordWithMedia)
        if embed_type == "app.bsky.embed.recordWithMedia":
            media = embed.get("media", {})
            media_type = media.get("$type", "")
            
            # Vidéo dans recordWithMedia
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
            
            # Images dans recordWithMedia
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
        
        # 5. Texte seul
        if result_data["text"] and not embed:
            return PostType.TEXT_ONLY, result_data, debug_info
        
        # 6. Inconnu (cas edge)
        return PostType.UNKNOWN, result_data, debug_info