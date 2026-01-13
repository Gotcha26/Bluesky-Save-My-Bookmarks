import requests
import json
import re
import sys

def extract_post_info(url):
    """Extrait le handle et le postId depuis une URL Bsky"""
    m = re.match(r"https?://bsky\.app/profile/([^/]+)/post/([^/]+)", url)
    if not m:
        print("URL invalide. Format attendu : https://bsky.app/profile/<handle>/post/<postId>")
        sys.exit(1)
    return m.groups()

def get_post_json(handle, post_id):
    """Récupère le JSON d’un post via l’API Bsky"""
    api_url = "https://bsky.social/xrpc/com.atproto.repo.getRecord"
    params = {
        "repo": handle,
        "collection": "app.bsky.feed.post",
        "rkey": post_id
    }
    resp = requests.get(api_url, params=params)
    if resp.status_code != 200:
        print(f"Erreur {resp.status_code} : {resp.text}")
        sys.exit(1)
    return resp.json()

def display_media(post_json):
    """Analyse le JSON et affiche les médias disponibles"""
    embed = post_json.get("value", {}).get("embed", {})
    if not embed:
        print("\nAucun média trouvé dans ce post.")
        return

    print("\n=== Médias trouvés ===")

    # --- Cas 1 : Vidéo ---
    if embed.get("$type") == "app.bsky.embed.video":
        video = embed.get("video", {})
        print("\n🎥 Vidéo :")
        print(f"   URL      : {video.get('ref', {}).get('$link', 'inconnu')}")
        print(f"   MIME     : {video.get('mimeType', 'inconnu')}")
        print(f"   Taille   : {video.get('size', 'inconnue')} octets")

    # --- Cas 2 : Images ---
    elif embed.get("$type") == "app.bsky.embed.images":
        images = embed.get("images", [])
        print("\n🖼️ Images :")
        for idx, img in enumerate(images, 1):
            full = None

            # Cas A : schéma avec fullsize (classique)
            if "fullsize" in img:
                full = img.get("fullsize", {}).get("$link")

            # Cas B : schéma avec image.ref (CID)
            if not full:
                ref = img.get("image", {}).get("ref", {}).get("$link")
                if ref:
                    # On reconstruit l’URL CDN Bluesky pour l’image
                    full = f"https://cdn.bsky.app/img/feed_fullsize/plain/{ref}@jpeg"

            alt = img.get("alt", "")
            print(f"{idx}. Full : {full or 'inconnu'}")
            print(f"   Alt  : {alt}")

    else:
        print("\n⚠️ Type d’embed non encore géré :", embed.get("$type"))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        url = input("Collez l'URL du post Bsky : ").strip()
    else:
        url = sys.argv[1]

    handle, post_id = extract_post_info(url)
    post_json = get_post_json(handle, post_id)

    # Pour référence : affichage JSON complet
    print("\n=== JSON brut (pour debug) ===")
    print(json.dumps(post_json, indent=4, ensure_ascii=False))

    # Et affichage des médias filtrés
    display_media(post_json)

    input("\nAppuyez sur Entrée pour quitter...")
