#!/usr/bin/env python3
"""
Résout un repost pour extraire l'URL du post original
"""
import requests
from urllib.parse import urlparse

class RepostResolver:
    def __init__(self):
        self.api_base = "https://bsky.social/xrpc/com.atproto.repo.getRecord"
    
    def resolve(self, post_url):
        """
        Résout un repost et retourne l'URL du post original
        Returns: (original_url, original_handle, original_post_id) ou (None, None, None)
        """
        parts = urlparse(post_url).path.strip("/").split("/")
        if len(parts) < 4:
            return None, None, None
        
        handle = parts[1]
        post_id = parts[-1]
        
        try:
            params = {
                "repo": handle,
                "collection": "app.bsky.feed.post",
                "rkey": post_id
            }
            resp = requests.get(self.api_base, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            
            embed = data.get("value", {}).get("embed", {})
            if embed.get("$type") != "app.bsky.embed.record":
                return None, None, None
            
            record = embed.get("record", {})
            cited_uri = record.get("uri", "")
            
            if not cited_uri:
                return None, None, None
            
            uri_parts = cited_uri.split("/")
            if len(uri_parts) < 5:
                return None, None, None
            
            cited_did = uri_parts[2]
            cited_post_id = uri_parts[-1]
            
            cited_handle = self._resolve_did_to_handle(cited_did)
            
            if not cited_handle:
                cited_handle = cited_did
            
            original_url = f"https://bsky.app/profile/{cited_handle}/post/{cited_post_id}"
            
            return original_url, cited_handle, cited_post_id
            
        except Exception as e:
            return None, None, None
    
    def _resolve_did_to_handle(self, did):
        """Résout un DID en handle via l'API"""
        try:
            profile_api = f"https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile"
            resp = requests.get(profile_api, params={"actor": did}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("handle")
        except:
            pass
        return None