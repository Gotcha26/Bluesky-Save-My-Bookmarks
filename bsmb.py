#!/usr/bin/env python3
"""
BSMB - Bsky Save My Bookmarks
Interface novice-first pour sauvegarder vos bookmarks Bluesky
"""
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from core import cli
from core.bookmarks_cache import post_views_from_config
from core.colors import c
from core.config import ensure_dirs, load_config, resolve_path, restrict_permissions, save_config
from core.database import Database
from core.orchestrator import run
from core.secret_store import (
    backend_name,
    delete_app_password,
    load_app_password,
    migrate_secret_to_keyring,
    store_app_password,
)
from core.ui import confirm, is_interactive, pause, set_yes
from core.version import __version__


def clear_screen():
    if not is_interactive():
        return  # sortie non interactive : pas de séquence d'effacement dans les logs
    subprocess.run("cls" if sys.platform == "win32" else "clear", shell=True)


def get_folder_size(path):
    """Calcule la taille d'un dossier récursivement."""
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file():
                total += entry.stat().st_size
            elif entry.is_dir():
                total += get_folder_size(entry.path)
    except Exception:
        pass
    return total


def format_size(size_bytes):
    """Formate une taille en octets lisible."""
    for unit in ['o', 'Ko', 'Mo', 'Go']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} To"


def format_last_sync(iso_str):
    """Formate une date ISO en texte relatif lisible."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
        delta = datetime.now() - dt
        if delta.total_seconds() < 60:
            return "à l'instant"
        elif delta.total_seconds() < 3600:
            mins = int(delta.total_seconds() // 60)
            return f"il y a {mins} min"
        elif delta.total_seconds() < 86400:
            hours = int(delta.total_seconds() // 3600)
            return f"il y a {hours}h"
        else:
            days = delta.days
            return f"il y a {days} jour{'s' if days > 1 else ''}"
    except Exception:
        return iso_str[:16]


# ─── État de l'application ───────────────────────────────────

def get_app_state(config):
    """Récupère l'état complet de l'application."""
    db = Database(resolve_path(config, "db_file"))
    stats = db.get_stats()

    urls_file = resolve_path(config, "urls_file")
    has_urls = urls_file.exists() and urls_file.stat().st_size > 0
    url_count = 0
    new_count = 0

    if has_urls:
        with open(urls_file, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]
        url_count = len(urls)
        new_urls = db.get_pending_posts(urls, config.get("retry_after_days", 7))
        new_count = len(new_urls)

    from core.auth import has_credentials
    has_account = has_credentials(config)

    db.close()

    return {
        "stats": stats,
        "has_urls": has_urls,
        "url_count": url_count,
        "new_count": new_count,
        "has_account": has_account,
        "last_sync": config.get("last_sync", ""),
        "advanced_mode": config.get("advanced_mode", False),
    }


# ─── En-tête ─────────────────────────────────────────────────

def print_header(config, state):
    """Affiche l'en-tête avec ligne de statut."""
    print(c.box_header(f"BSMB v{__version__} - BSKY SAVE MY BOOKMARKS"))

    # Ligne de statut
    if state["has_account"]:
        handle = config.get("bsky_handle", "")
        account_status = f"{c.OK}{handle}{c.RESET}"
    else:
        account_status = f"{c.WARNING}non connecté{c.RESET}"

    media_total = state["stats"]["images"] + state["stats"]["videos"]
    media_status = (
        f"{c.VALUE}{media_total}{c.RESET} fichiers"
        if media_total > 0
        else f"{c.DIM}aucun{c.RESET}"
    )

    print(f"  Compte: {account_status} | Médias: {media_status}")

    last_sync_str = format_last_sync(state["last_sync"])
    if last_sync_str:
        print(f"  Dernière synchronisation: {c.DIM}{last_sync_str}{c.RESET}")

    print()


# ─── Menu principal ──────────────────────────────────────────

def show_main_menu(state):
    """Affiche le menu principal novice-first."""
    print(c.menu_option("1", "Mon compte     - Connexion et bookmarks en ligne"))
    print(c.menu_option("2", "Stockage local - Dossier et statistiques"))
    print(c.menu_option("3", "Paramètres     - Configuration de l'application"))
    print()

    # Option 4 : conditionnelle
    if not state["has_account"]:
        print(f"  {c.DIM}4. Télécharger    - (connectez d'abord votre compte){c.RESET}")
    elif state["new_count"] > 0:
        label = f"Télécharger {c.VALUE}{state['new_count']}{c.RESET} nouveaux bookmarks"
        print(c.menu_option("4", label))
    elif state["has_urls"]:
        print(f"  {c.DIM}4. Tout est à jour{c.RESET}")
    else:
        print(f"  {c.DIM}4. Télécharger    - (synchronisez d'abord via Mon compte){c.RESET}")

    print()
    print(c.menu_option("0", f"{c.DIM}Quitter{c.RESET}"))
    print()


# ─── Token ───────────────────────────────────────────────────

def get_token_from_clipboard():
    """Récupère le token depuis le presse-papier."""
    try:
        import win32clipboard  # type: ignore
        win32clipboard.OpenClipboard()
        token = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        return token.strip() if token else None
    except Exception:
        try:
            result = subprocess.run(
                ["powershell", "-command", "Get-Clipboard"],
                capture_output=True, text=True,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None


def get_session(config):
    """
    Obtient une session Bluesky valide silencieusement.
    Returns: dict {"token", "refresh_jwt", "did", "pds_url"} ou None si échec.
    """
    from core.auth import AuthError, has_credentials
    from core.auth import get_session as auth_get_session

    if has_credentials(config):
        try:
            session = auth_get_session(config)
            if session:
                return session
        except AuthError:
            return None

    # Fallback fichier token
    token_file = resolve_path(config, "token_file")
    if token_file.exists():
        restrict_permissions(token_file)  # le token est un secret : chmod 600 (POSIX)
        content = token_file.read_text(encoding="utf-8").strip()
        if content.startswith("Bearer "):
            return {
                "token": content,
                "refresh_jwt": None,
                "did": None,
                "pds_url": config.get("pds_url") or "https://bsky.social",
            }

    return None


def _remember_pds_url(config, pds_url):
    """Sauvegarde le PDS du compte dans la config s'il a changé."""
    if pds_url and config.get("pds_url") != pds_url:
        config["pds_url"] = pds_url
        save_config(config)


# ─── Mon compte ──────────────────────────────────────────────

def menu_account(config, state):
    """Menu Mon compte : connexion et synchronisation."""
    while True:
        clear_screen()
        print(c.box_header("MON COMPTE"))
        print()

        if not state["has_account"]:
            # Pas de compte configuré → guidage
            print(c.warning("Aucun compte Bluesky connecté"))
            print()
            print(f"  {c.KEY}Pour sauvegarder vos bookmarks, connectez votre compte :{c.RESET}")
            print()
            print(c.menu_option("1", "Connecter mon compte Bluesky"))
            print()
            print(c.menu_option("0", f"{c.DIM}Retour{c.RESET}"))
            print()

            choice = input(c.prompt("  Votre choix: ")).strip()
            if choice == "1":
                configure_credentials(config)
                state = get_app_state(config)
                continue
            else:
                return

        # Compte configuré → affichage + sync
        handle = config.get("bsky_handle", "")
        print(c.config_line("Compte", f"{c.OK}{handle}{c.RESET}"))

        last_sync_str = format_last_sync(state["last_sync"])
        if last_sync_str:
            print(c.config_line("Dernière sync", last_sync_str))

        # Statistiques en ligne vs local
        if state["has_urls"]:
            print()
            print(c.config_line("Bookmarks en ligne", str(state["url_count"])))
            print(c.config_line("Posts traités", str(state["stats"]["posts"])))
            if state["new_count"] > 0:
                print(c.config_line("Nouveaux", f"{c.OK}{state['new_count']}{c.RESET}"))
            else:
                print(c.config_line("Nouveaux", f"{c.DIM}0 - tout est à jour{c.RESET}"))
        else:
            print()
            print(f"  {c.DIM}Aucune synchronisation effectuée{c.RESET}")

        if state["stats"]["dead"] > 0:
            print(c.config_line("Liens morts", f"{c.WARNING}{state['stats']['dead']}{c.RESET}"))

        print()
        print(c.separator())
        print()
        print(c.menu_option("1", "Synchroniser les bookmarks"))
        print(c.menu_option("D", "Déconnecter mon compte"))
        print(c.menu_option("0", f"{c.DIM}Retour{c.RESET}"))
        print()

        choice = input(c.prompt("  Votre choix: ")).strip()

        if choice == "0":
            return
        elif choice == "1":
            do_sync(config)
            state = get_app_state(config)
        elif choice.upper() == "D":
            disconnect_account(config)
            state = get_app_state(config)


def disconnect_account(config):
    """
    Déconnecte le compte après confirmation : supprime l'App Password (keyring et
    config.json), le handle et le PDS. Les fichiers téléchargés et la base restent.

    Returns:
        bool: True si le compte a été déconnecté
    """
    handle = config.get("bsky_handle", "")
    print()
    print(c.warning(f"Le compte {handle} sera déconnecté (App Password supprimé de cet ordinateur)."))
    print(f"  {c.DIM}Vos fichiers téléchargés et la base ne sont pas touchés.{c.RESET}")
    if not confirm("Confirmer ?", default=False):
        return False

    nettoye = delete_app_password(config, handle)
    config["bsky_handle"] = ""
    config["pds_url"] = ""
    save_config(config)
    if nettoye:
        print(c.success("Compte déconnecté"))
    else:
        print(c.warning("Compte déconnecté, mais le trousseau n'a pas pu être nettoyé : "
                        "supprimez l'entrée « bsmb » à la main."))
    pause()
    return True


def do_sync(config):
    """Lance la synchronisation des bookmarks."""
    print()
    print(c.info("Connexion à Bluesky..."))

    session = get_session(config)
    if not session:
        print(c.error("Impossible d'obtenir un token d'authentification"))
        print(f"  {c.DIM}Vérifiez vos identifiants dans Paramètres{c.RESET}")
        pause()
        return

    token = session["token"]
    _remember_pds_url(config, session["pds_url"])

    print(c.success("Authentification réussie"))
    print(c.info("Récupération des bookmarks..."))

    db = Database(resolve_path(config, "db_file"))
    from core.bookmarks import BookmarkSync
    sync = BookmarkSync(config, db)

    def progress(page, count):
        print(f"  {c.DIM}Page {page}... {count} bookmarks{c.RESET}")

    result = sync.sync(token, on_progress=progress, session_info=session)
    db.close()

    if result["error"]:
        if result.get("expired"):
            print(c.error("Token expiré — reconnectez votre compte"))
        else:
            print(c.error(f"Erreur : {result['error']}"))
    else:
        print()
        print(c.success(f"Synchronisation terminée"))
        print(c.config_line("Bookmarks en ligne", str(result["online_count"])))
        print(c.config_line("Déjà traités", str(result["local_count"])))
        if result["new_count"] > 0:
            print(c.config_line("Nouveaux", f"{c.OK}{result['new_count']}{c.RESET}"))
        else:
            print(c.config_line("Nouveaux", f"{c.DIM}0 - tout est à jour{c.RESET}"))
        if result.get("cache_error"):
            print(c.warning(f"Cache des bookmarks non écrit : {result['cache_error']}"))

    pause()


# ─── Stockage local ──────────────────────────────────────────

def menu_local_storage(config, state):
    """Menu Stockage local : stats, dossier, nettoyage."""
    while True:
        clear_screen()
        print(c.box_header("STOCKAGE LOCAL"))
        print()

        stats = state["stats"]
        total_media = stats["images"] + stats["videos"]

        print(c.config_line("Posts traités", str(stats["posts"])))
        print(c.config_line("Images téléchargées", str(stats["images"])))
        print(c.config_line("Vidéos téléchargées", str(stats["videos"])))
        print(c.config_line("Textes sauvegardés", str(stats["texts"])))
        print(c.config_line("Total médias", str(total_media)))

        # Taille du dossier
        download_dir = config["download_dir"]
        if Path(download_dir).exists():
            size = get_folder_size(download_dir)
            print(c.config_line("Taille du dossier", format_size(size)))

        print(c.config_line("Destination", f"{c.VALUE}{download_dir}{c.RESET}"))

        # Liens morts
        if stats["dead"] > 0:
            print()
            print(c.warning(f"{stats['dead']} lien(s) mort(s) détecté(s)"))

        print()
        print(c.separator())
        print()

        options = []
        print(c.menu_option("1", "Ouvrir le dossier de téléchargements"))
        options.append("1")

        if stats["dead"] > 0:
            print(c.menu_option("2", f"Nettoyer les liens morts ({stats['dead']})"))
            options.append("2")

        print(c.menu_option("R", f"{c.WARNING}Réinitialiser la base de données{c.RESET}"))
        print(c.menu_option("0", f"{c.DIM}Retour{c.RESET}"))
        print()

        choice = input(c.prompt("  Votre choix: ")).strip().upper()

        if choice == "0":
            return
        elif choice == "1":
            open_download_folder(config)
        elif choice == "2" and "2" in options:
            cleanup_dead_links(config)
            state = get_app_state(config)
        elif choice == "R":
            reset_database(config)
            state = get_app_state(config)
        else:
            print(c.error(f"Choix invalide : \"{choice}\""))
            pause()


def cleanup_dead_links(config):
    """Supprime les liens morts de la base de données."""
    db = Database(resolve_path(config, "db_file"))
    dead_posts = db.get_dead_posts()

    clear_screen()
    print(c.box_header("NETTOYAGE DES LIENS MORTS"))
    print()
    print(c.warning(f"{len(dead_posts)} lien(s) mort(s) détecté(s) :"))
    print()

    for url, status in dead_posts[:10]:
        label = "supprimé" if status == "deleted" else status
        print(f"  {c.DIM}-{c.RESET} {c.DIM}{label}{c.RESET} : {url}")

    if len(dead_posts) > 10:
        print(f"  {c.DIM}... et {len(dead_posts) - 10} autres{c.RESET}")

    print()
    print(c.separator())
    print()
    print(f"  {c.KEY}Cette action va supprimer ces entrées de la base.{c.RESET}")
    print(f"  {c.DIM}Les fichiers déjà téléchargés ne seront pas supprimés.{c.RESET}")
    print()

    if confirm("Confirmer le nettoyage ?"):
        count = db.cleanup_dead_posts()
        print(c.success(f"{count} entrée(s) supprimée(s)"))
    else:
        print(f"\n  {c.DIM}Nettoyage annulé{c.RESET}")

    db.close()
    pause()


def reset_database(config):
    """Réinitialisation de la base de données avec confirmation."""
    clear_screen()
    print(c.box_header("RÉINITIALISATION"))
    print()
    print(c.warning("Cette action va :"))
    print(f"    {c.DIM}-{c.RESET} Supprimer l'historique des posts traités")
    print(f"    {c.DIM}-{c.RESET} Supprimer l'historique des médias téléchargés")
    print(f"    {c.DIM}-{c.RESET} {c.OK}NE PAS{c.RESET} supprimer les fichiers déjà téléchargés")
    print()
    print(c.separator())
    print()

    saisie = input(c.prompt("  Confirmer ? (tapez 'RESET'): ")).strip()
    if saisie == "RESET":
        db_file = resolve_path(config, "db_file")
        if db_file.exists():
            db_file.unlink()
            print(c.success("Base de données réinitialisée"))
        else:
            print(c.warning("Aucune base de données à réinitialiser"))
    else:
        print(f"\n  {c.DIM}Réinitialisation annulée{c.RESET}")

    pause()


# ─── Paramètres ──────────────────────────────────────────────

def menu_settings(config, state):
    """Menu Paramètres : configuration de l'application."""
    while True:
        clear_screen()
        print(c.box_header("PARAMÈTRES"))
        print()

        from core.auth import has_credentials
        auth_status = f"{c.OK}connecté{c.RESET}" if has_credentials(config) else f"{c.DIM}non connecté{c.RESET}"
        advanced = config.get("advanced_mode", False)

        print(c.config_line("1. Identifiants Bluesky", auth_status))
        print(c.config_line("2. Dossier téléchargements", config["download_dir"]))
        print(c.config_line("3. Workers parallèles", str(config.get("max_workers", 4))))

        if advanced:
            print(c.config_line("4. Mode avancé", f"{c.OK}activé{c.RESET}"))
        else:
            print(c.config_line("4. Mode avancé", f"{c.DIM}désactivé{c.RESET}"))

        if advanced:
            print()
            print(c.title("  OPTIONS AVANCÉES"))
            print(c.separator())
            print(c.config_line("5. Fichier token (fallback)", config["token_file"]))
            print(c.config_line("6. Fichier URLs", config["urls_file"]))
            print(c.menu_option("7", "Supprimer les logs"))
            print(c.menu_option("8", "Mode dev - Depuis urls.txt, sans token"))
            print(c.menu_option("9", f"{c.WARNING}Force DL{c.RESET} - Re-télécharger tous les médias"))

        print()
        print(c.separator())
        print(f"  {c.DIM}Entrez le numéro pour modifier, ou 0 pour revenir{c.RESET}")
        print()
        print(c.menu_option("0", f"{c.DIM}Retour{c.RESET}"))
        print()

        max_choice = "9" if advanced else "4"
        choice = input(c.prompt(f"  Votre choix (0-{max_choice}): ")).strip()

        if choice == "0":
            break
        elif choice == "1":
            configure_credentials(config)
            state = get_app_state(config)
        elif choice == "2":
            _edit_config_value(
                config, "download_dir", "Dossier de téléchargements",
                after_save=lambda: ensure_dirs(config),
            )
        elif choice == "3":
            _edit_workers(config)
        elif choice == "4":
            config["advanced_mode"] = not config.get("advanced_mode", False)
            save_config(config)
            mode_str = "activé" if config["advanced_mode"] else "désactivé"
            print(c.success(f"Mode avancé {mode_str}"))
            pause()
        elif choice == "5" and advanced:
            _edit_config_value(config, "token_file", "Fichier token")
        elif choice == "6" and advanced:
            _edit_config_value(config, "urls_file", "Fichier URLs")
        elif choice == "7" and advanced:
            from core.config import cleanup_logs
            deleted = cleanup_logs(config)
            print(c.success(f"{deleted} fichier(s) log supprimé(s)"))
            pause()
        elif choice == "8" and advanced:
            download_media_dev(config)
            pause()
        elif choice == "9" and advanced:
            download_media(config, force=True)
            pause()
        else:
            print(c.error(f"Choix invalide : \"{choice}\""))
            pause()


def configure_credentials(config):
    """Menu de configuration des identifiants Bluesky."""
    clear_screen()
    print(c.box_header("IDENTIFIANTS BLUESKY"))
    print()

    current_handle = config.get("bsky_handle", "")
    has_pwd = bool(current_handle) and bool(load_app_password(config, current_handle))

    print(c.config_line("Handle actuel", current_handle or f"{c.DIM}non configuré{c.RESET}"))
    print(c.config_line("App Password", f"{c.OK}configuré{c.RESET}" if has_pwd else f"{c.DIM}non configuré{c.RESET}"))
    print()
    print(c.separator())
    print()
    print(f"  {c.KEY}Pour créer un App Password :{c.RESET}")
    print(f"    {c.DIM}1.{c.RESET} Allez sur {c.VALUE}bsky.app > Settings > App Passwords{c.RESET}")
    print(f"    {c.DIM}2.{c.RESET} Cliquez sur {c.VALUE}Add App Password{c.RESET}")
    print(f"    {c.DIM}3.{c.RESET} Nommez-le (ex: 'BSMB') et copiez le mot de passe généré")
    print()
    if backend_name() == "keyring":
        print(f"  {c.DIM}L'App Password sera stocké dans le trousseau du système (keyring){c.RESET}")
    else:
        print(f"  {c.DIM}L'App Password sera stocké dans config.json (fichier local, hors Git){c.RESET}")
    print(f"  {c.DIM}Conseil : créez un App Password dédié à BSMB et révoquez-le en cas de doute.{c.RESET}")
    print()
    print(c.separator())
    print()

    handle = input(c.prompt("  Handle Bluesky (ENTRÉE pour garder): ")).strip()
    if not handle and not current_handle:
        print(f"\n  {c.DIM}Configuration annulée{c.RESET}")
        pause()
        return
    if not handle:
        handle = current_handle

    app_password = input(c.prompt("  App Password (xxxx-xxxx-xxxx-xxxx): ")).strip()
    if not app_password:
        print(f"\n  {c.DIM}Configuration annulée{c.RESET}")
        pause()
        return

    # Test immédiat
    print()
    print(c.info("Test de connexion..."))

    from core.auth import AuthError, create_session
    try:
        session = create_session(handle, app_password)
        print(c.success("Connexion réussie !"))

        if current_handle and current_handle != handle:
            delete_app_password(config, current_handle)  # ne pas laisser l'ancien secret
        backend = store_app_password(config, handle, app_password)
        config["bsky_handle"] = handle
        config["pds_url"] = session["pds_url"]
        if backend == "config.json" and not config.get("warned_plaintext_secret", False):
            print(c.warning("AVERTISSEMENT : l'App Password est stocké en clair dans config.json."))
            print(f"  {c.DIM}Installez keyring (pip install keyring) pour le placer dans le "
                  f"trousseau du système.{c.RESET}")
            config["warned_plaintext_secret"] = True
        save_config(config)
        print(c.success("Identifiants sauvegardés"
                        + (" (trousseau du système)" if backend == "keyring" else "")))

    except AuthError as e:
        print(c.error(f"Échec : {e}"))
        print(f"  {c.DIM}Identifiants non sauvegardés{c.RESET}")

    pause()


def _edit_config_value(config, key, label, after_save=None):
    """Édite une valeur de configuration."""
    print()
    print(f"  {c.KEY}Actuel:{c.RESET} {c.VALUE}{config[key]}{c.RESET}")
    new_val = input(c.prompt(f"  Nouveau {label} (ENTRÉE pour garder): ")).strip()

    if new_val:
        config[key] = new_val
        save_config(config)
        if after_save:
            after_save()
        print(c.success("Sauvegardé"))
    else:
        print(c.success("Valeur inchangée"))

    pause()


def _edit_workers(config):
    """Édite le nombre de workers parallèles."""
    current = config.get("max_workers", 4)
    print()
    print(f"  {c.KEY}Actuel:{c.RESET} {c.VALUE}{current}{c.RESET} workers")
    print(f"  {c.DIM}Plage recommandée : 1 (séquentiel) à 8 (rapide){c.RESET}")
    new_val = input(c.prompt("  Nombre de workers (ENTRÉE pour garder): ")).strip()

    if new_val:
        try:
            n = int(new_val)
            if n < 1:
                n = 1
            elif n > 16:
                n = 16
                print(c.warning(f"Limité à {n} workers maximum"))
            config["max_workers"] = n
            save_config(config)
            print(c.success(f"Workers mis à jour : {n}"))
        except ValueError:
            print(c.error("Valeur invalide (nombre entier attendu)"))
    else:
        print(c.success("Valeur inchangée"))

    pause()


# ─── Téléchargement ──────────────────────────────────────────

def menu_download_new(config, state):
    """Menu Télécharger : synchronise si besoin, puis télécharge les nouveaux."""
    if not state["has_account"]:
        clear_screen()
        print(c.box_header("TÉLÉCHARGER"))
        print()
        print(c.warning("Aucun compte Bluesky connecté"))
        print()
        print(f"  {c.KEY}Connectez d'abord votre compte :{c.RESET}")
        print(f"    {c.DIM}Menu principal > 1. Mon compte{c.RESET}")
        pause()
        return

    # Si pas de sync récente, proposer d'en faire une
    if not state["has_urls"]:
        clear_screen()
        print(c.box_header("TÉLÉCHARGER"))
        print()
        print(c.info("Aucune synchronisation effectuée"))
        print()
        if not confirm("Synchroniser les bookmarks maintenant ?"):
            return
        do_sync(config)
        state = get_app_state(config)

    if state["new_count"] == 0:
        print()
        print(c.success("Tout est à jour — aucun nouveau bookmark à télécharger"))
        pause()
        return

    download_media(config, force=False)
    pause()


def download_media(config, force=False):
    """Télécharge les médias via l'orchestrateur."""
    urls_file = resolve_path(config, "urls_file")
    if not urls_file.exists():
        print(c.error(f"Fichier {config['urls_file']} introuvable"))
        return False

    with open(urls_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print(c.warning("Aucune URL à traiter"))
        return False

    db = Database(resolve_path(config, "db_file"))

    if force:
        urls_to_process = urls
        print()
        print(c.warning(f"Mode FORCE : {len(urls)} posts seront tous traités"))
    else:
        urls_to_process = db.get_pending_posts(urls, config.get("retry_after_days", 7))
        new = len(urls_to_process)
        total = len(urls)
        print()
        print(c.info(f"{total} URLs au total, {c.VALUE}{new}{c.RESET} nouvelles"))

    if not urls_to_process:
        print(c.success("Tous les posts sont déjà traités"))
        db.close()
        return True

    print()
    if not confirm(f"Traiter {len(urls_to_process)} posts ?"):
        db.close()
        return False

    db.close()

    print()
    print(c.info("Lancement du téléchargement..."))
    print()

    # Vues hydratées de la dernière synchro : évitent un getRecord par post
    post_views = post_views_from_config(config)
    if post_views:
        stats = run(urls_to_process, config, post_views=post_views)
    else:
        stats = run(urls_to_process, config)
    _proposer_ouverture(config, stats)
    return stats["success"] > 0


def download_media_dev(config):
    """Mode dev : télécharge depuis urls.txt sans token ni DB."""
    urls_file = resolve_path(config, "urls_file")
    if not urls_file.exists() or urls_file.stat().st_size == 0:
        print(c.warning("Aucune URL disponible dans urls.txt"))
        return False

    with open(urls_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print(c.warning("Aucune URL à traiter"))
        return False

    clear_screen()
    print(c.box_header("MODE DÉVELOPPEMENT"))
    print()
    print(c.warning("Traitement direct depuis urls.txt"))
    print(c.config_line("Token", f"{c.DIM}non vérifié{c.RESET}"))
    print(c.config_line("Base de données", f"{c.DIM}non mise à jour{c.RESET}"))
    print(c.config_line("Posts à traiter", f"{c.VALUE}{len(urls)}{c.RESET}"))
    print()
    print(c.separator())
    print()

    if not confirm(f"Traiter {len(urls)} posts en mode dev ?"):
        return False

    stats = run(urls, config, no_db=True)
    _proposer_ouverture(config, stats)
    return stats["success"] > 0


def _proposer_ouverture(config, stats):
    """Propose d'ouvrir le dossier de téléchargements si au moins un post a réussi."""
    if stats["success"] > 0 and config.get("open_folder_after_download", True):
        print()
        if confirm("Ouvrir le dossier de téléchargements ?"):
            open_download_folder(config)


# ─── Utilitaires ─────────────────────────────────────────────

def open_download_folder(config):
    """Ouvre le dossier de téléchargements."""
    download_dir = config["download_dir"]
    if sys.platform == "win32":
        os.startfile(download_dir)
    else:
        subprocess.run(["xdg-open", download_dir])


# ─── Boucle principale ──────────────────────────────────────

def main(argv=None):
    """Point d'entrée : sous-commande -> CLI non interactive, sinon menu interactif.

    Retourne le code de retour du processus (voir core/cli.py).
    """
    argv = sys.argv[1:] if argv is None else list(argv)
    args = cli.build_parser().parse_args(argv)
    if args.command is not None:
        return cli.main(argv)

    if args.yes:
        set_yes(True)
    config = load_config()
    migrate_secret_to_keyring(config)  # App Password en clair -> keyring si disponible
    ensure_dirs(config)
    from core.config import cleanup_old_logs
    cleanup_old_logs(config)

    try:
        run_menu(config)
    except (EOFError, KeyboardInterrupt):
        print(f"\n  {c.DIM}Entrée interrompue — fin du programme{c.RESET}")
    return 0


def run_menu(config):
    """Boucle du menu interactif."""
    while True:
        clear_screen()
        state = get_app_state(config)
        print_header(config, state)
        show_main_menu(state)

        choice = input(c.prompt("  Votre choix: ")).strip()

        if choice == "0":
            print(f"\n  {c.DIM}Au revoir !{c.RESET}")
            break
        elif choice == "1":
            menu_account(config, state)
        elif choice == "2":
            menu_local_storage(config, state)
        elif choice == "3":
            menu_settings(config, state)
        elif choice == "4":
            menu_download_new(config, state)
        else:
            print(c.error(f"Choix invalide : \"{choice}\""))
            pause()


if __name__ == "__main__":
    # Forcer l'encodage UTF-8 pour la console Windows (exécution directe uniquement,
    # sinon conflit avec la capture de sortie de pytest)
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    sys.exit(main())
