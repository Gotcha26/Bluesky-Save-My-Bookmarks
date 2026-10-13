#!/usr/bin/env python3
"""
Interface en ligne de commande non interactive de BSMB.

    python bsmb.py                     # menu interactif (inchangé)
    python bsmb.py sync                # synchronise les bookmarks
    python bsmb.py download [--force]  # télécharge les nouveaux posts
    python bsmb.py run                 # sync puis download
    python bsmb.py status [--json]     # état du compte et des compteurs
    python bsmb.py --yes ...           # répond par défaut à toutes les confirmations

Codes de retour : 0 succès, 1 erreur d'authentification, 2 erreur réseau,
3 téléchargements en échec.
"""
import argparse
import json

from core import orchestrator, ui
from core.auth import AuthError, get_session, has_credentials
from core.bookmarks import BookmarkSync
from core.colors import c
from core.config import (
    cleanup_old_logs, ensure_dirs, load_config, resolve_path, save_config,
)
from core.database import Database
from core.secret_store import migrate_secret_to_keyring

EXIT_OK = 0
EXIT_AUTH = 1
EXIT_NETWORK = 2
EXIT_DOWNLOAD = 3


def is_interactive():
    """True si le programme peut poser des questions (terminal réel, pas de --yes)."""
    return ui.is_interactive()


def build_parser():
    """Construit l'analyseur d'arguments (--yes accepté avant ou après la sous-commande)."""
    parser = argparse.ArgumentParser(
        prog="bsmb",
        description="BSMB - Bsky Save My Bookmarks. Sans sous-commande : menu interactif.",
    )
    parser.add_argument("--yes", action="store_true",
                        help="mode non interactif : accepte les valeurs par défaut")
    sub = parser.add_subparsers(dest="command", metavar="{sync,download,run,status}")

    def ajouter(nom, aide):
        p = sub.add_parser(nom, help=aide, description=aide)
        p.add_argument("--yes", action="store_true", default=argparse.SUPPRESS,
                       help="mode non interactif : accepte les valeurs par défaut")
        return p

    ajouter("sync", "synchronise les bookmarks en ligne")
    p_dl = ajouter("download", "télécharge les posts pas encore traités")
    p_dl.add_argument("--force", action="store_true",
                      help="retraite tous les posts de urls.txt")
    ajouter("run", "synchronise puis télécharge (pour la planification)")
    p_st = ajouter("status", "affiche l'état du compte et les compteurs")
    p_st.add_argument("--json", action="store_true", help="sortie JSON")
    return parser


def _preparer_config():
    """Charge la config et prépare l'environnement (secret, dossiers, logs)."""
    config = load_config()
    migrate_secret_to_keyring(config)
    ensure_dirs(config)
    cleanup_old_logs(config)
    return config


def _lire_urls(config):
    urls_file = resolve_path(config, "urls_file")
    if not urls_file.exists():
        return []
    with open(urls_file, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


# ─── Sous-commandes ──────────────────────────────────────────

def cmd_sync(config, args=None):
    """Synchronise les bookmarks. Retourne un code de retour."""
    print(c.info("Connexion à Bluesky..."))
    try:
        session = get_session(config)
    except AuthError as e:
        print(c.error(f"Authentification impossible : {e}"))
        return EXIT_AUTH
    if not session:
        print(c.error("Aucun moyen d'authentification : configurez un compte (menu > Mon compte)"))
        return EXIT_AUTH

    pds_url = session.get("pds_url")
    if pds_url and config.get("pds_url") != pds_url:
        config["pds_url"] = pds_url
        save_config(config)

    db = Database(resolve_path(config, "db_file"))
    try:
        result = BookmarkSync(config, db).sync(
            session["token"],
            on_progress=lambda page, count: print(f"  Page {page}... {count} bookmarks"),
        )
    finally:
        db.close()

    if result["error"]:
        if result.get("expired"):
            print(c.error("Token expiré — reconnectez votre compte"))
            return EXIT_AUTH
        print(c.error(f"Erreur réseau : {result['error']}"))
        return EXIT_NETWORK

    print(c.success("Synchronisation terminée"))
    print(c.config_line("Bookmarks en ligne", str(result["online_count"])))
    print(c.config_line("Déjà traités", str(result["local_count"])))
    print(c.config_line("Nouveaux", str(result["new_count"])))
    return EXIT_OK


def cmd_download(config, args=None):
    """Télécharge les posts en attente (ou tous avec --force). Retourne un code de retour."""
    force = bool(getattr(args, "force", False))
    urls = _lire_urls(config)
    if not urls:
        print(c.warning("Aucune URL à traiter (lancez d'abord « sync »)"))
        return EXIT_OK

    if force:
        a_traiter = urls
    else:
        db = Database(resolve_path(config, "db_file"))
        try:
            a_traiter = db.get_pending_posts(urls, config.get("retry_after_days", 7))
        finally:
            db.close()

    if not a_traiter:
        print(c.success("Tous les posts sont déjà traités"))
        return EXIT_OK

    if not ui.confirm(f"Traiter {len(a_traiter)} posts ?", default=True):
        return EXIT_OK

    stats = orchestrator.run(a_traiter, config)
    if stats.get("failed") or stats.get("error_500"):
        return EXIT_DOWNLOAD
    return EXIT_OK


def cmd_run(config, args=None):
    """Synchronise puis télécharge ; s'arrête au premier code non nul."""
    code = cmd_sync(config, args)
    if code != EXIT_OK:
        return code
    return cmd_download(config, args)


def collect_status(config):
    """Rassemble l'état de l'application (sans appel réseau)."""
    db = Database(resolve_path(config, "db_file"))
    try:
        cache = BookmarkSync(config, db).get_cached_state()
        stats = db.get_stats()
    finally:
        db.close()
    handle = config.get("bsky_handle", "")
    return {
        "account": handle if handle and has_credentials(config) else None,
        "pds_url": config.get("pds_url", ""),
        "last_sync": cache["last_sync"],
        "online_count": cache["online_count"],
        "local_count": cache["local_count"],
        "new_count": cache["new_count"],
        "dead_count": cache["dead_count"],
        "media": {"images": stats["images"], "videos": stats["videos"], "texts": stats["texts"]},
        "download_dir": config["download_dir"],
    }


def cmd_status(config, args=None):
    """Affiche l'état en texte ou en JSON."""
    etat = collect_status(config)
    if getattr(args, "json", False):
        print(json.dumps(etat, ensure_ascii=False, indent=2))
        return EXIT_OK

    print(c.config_line("Compte", etat["account"] or "non connecté"))
    print(c.config_line("Dernière synchronisation", etat["last_sync"] or "jamais"))
    print(c.config_line("Bookmarks en ligne", str(etat["online_count"])))
    print(c.config_line("Posts traités", str(etat["local_count"])))
    print(c.config_line("Nouveaux", str(etat["new_count"])))
    print(c.config_line("Liens morts", str(etat["dead_count"])))
    media = etat["media"]
    print(c.config_line("Images / vidéos / textes",
                        f"{media['images']} / {media['videos']} / {media['texts']}"))
    print(c.config_line("Destination", etat["download_dir"]))
    return EXIT_OK


def main(argv=None):
    """Point d'entrée de la CLI. Retourne le code de retour du processus."""
    args = build_parser().parse_args(argv)
    if args.yes:
        ui.set_yes(True)
    if args.command is None:
        build_parser().print_help()
        return EXIT_OK
    config = _preparer_config()
    # Résolution à l'appel (et non au chargement du module) pour rester mockable
    return globals()["cmd_" + args.command](config, args)
