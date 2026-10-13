#!/usr/bin/env python3
"""
Sauvegarde du texte d'un post Bluesky sans média, dans :
  <handle>_<YYYYMMDD>_<postid>.txt

Usage manuel : python downloaders/text.py [<dossier>] <url_post>
Codes de sortie : 0 = texte sauvegardé, 1 = erreur technique, 2 = pas de texte.
"""
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

if __package__ in (None, ""):
    # Exécution directe (python downloaders/text.py) : rendre la racine importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import http as bsmb_http  # noqa: E402
from core.config import get_default_paths, load_config  # noqa: E402
from downloaders import DownloadError, lignes_console  # noqa: E402


def fetch_post(handle, post_id, http=None):
    http = http or bsmb_http.get_session()
    api_url = f"https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri=at://{handle}/app.bsky.feed.post/{post_id}"
    resp = http.get(api_url, timeout=15)
    resp.raise_for_status()
    return resp.json()

def nom_base_texte(handle, post_id, created_at):
    """Nom sans extension : <handle>_<YYYYMMDD>_<postid> (date du jour si createdAt est illisible)."""
    date_str = datetime.now().strftime("%Y%m%d")
    if created_at:
        try:
            date_str = datetime.fromisoformat(created_at.replace("Z", "")).strftime("%Y%m%d")
        except ValueError:
            pass
    handle_safe = handle.replace(":", "_").replace(".", "_")[:20]
    return f"{handle_safe}_{date_str}_{post_id}"


def nom_fichier_texte(handle, post_id, created_at):
    """Nom du fichier texte d'un post : <handle>_<YYYYMMDD>_<postid>.txt"""
    return f"{nom_base_texte(handle, post_id, created_at)}.txt"


def save_text(post_url, dest_dir, config, session=None, name_prefix=None):
    """
    Sauvegarde le texte d'un post dans dest_dir.

    name_prefix : si fourni, remplace la base <handle>_<date>_<postid> du nom
    (texte d'un post cité : <prefix>.txt).

    Returns:
        list[DownloadResult] : le fichier texte écrit ; liste vide si l'URL
        n'est pas celle d'un post ou si le post n'a pas de texte.
    Raises:
        DownloadError : API inaccessible.
    """
    http = session or bsmb_http.get_session()
    parts = urlparse(post_url).path.strip("/").split("/")
    if len(parts) < 4:
        return []

    handle = parts[1]
    post_id = parts[-1]

    try:
        data = fetch_post(handle, post_id, http)
    except Exception as e:
        raise DownloadError(f"Erreur API : {e}") from e

    post = data.get("thread", {}).get("post", {})
    record = post.get("record", {})
    text = record.get("text", "")
    created_at = record.get("createdAt", "")

    if not text:
        return []

    # Format commun à tous les posts (facets résolues, alt, citation…) : voir downloaders/archive.py
    from downloaders.archive import write_text  # import tardif : archive importe nom_base_texte d'ici
    return write_text(post_url, record, dest_dir, config, name_prefix=name_prefix)

# -------------------- Usage manuel --------------------
def main(argv=None):
    """python downloaders/text.py [<dossier>] <url_post>"""
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) > 1:
        dest_dir, url = argv[0], argv[1]
    else:
        dest_dir = get_default_paths()["text_dir"]
        url = argv[0] if argv else input("👉 URL : ").strip()

    try:
        results = save_text(url, dest_dir, load_config())
    except DownloadError as e:
        print(f"   [ERR] {e}")
        return 1

    if not results:
        print("   [!] Aucun texte trouvé")
        return 2

    for ligne in lignes_console(results):
        print(ligne)
    return 0

if __name__ == "__main__":
    sys.exit(main())
