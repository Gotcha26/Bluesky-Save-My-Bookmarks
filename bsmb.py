#!/usr/bin/env python3
"""
BSMB - Bsky Save My Bookmarks
Interface novice-first pour sauvegarder vos bookmarks Bluesky
"""
import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime

from core.config import load_config, save_config, ensure_dirs, get_media_dirs
from core.database import Database
from core.colors import c


def clear_screen():
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
    db = Database(config["db_file"])
    stats = db.get_stats()

    urls_file = Path(config["urls_file"])
    has_urls = urls_file.exists() and urls_file.stat().st_size > 0
    url_count = 0
    new_count = 0

    if has_urls:
        with open(urls_file, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]
        url_count = len(urls)
        new_urls = db.get_new_posts(urls)
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
    print(c.box_header("BSMB - BSKY SAVE MY BOOKMARKS"))

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


def get_token(config):
    """
    Obtient un token Bearer valide silencieusement.
    Returns: str (token) ou None si échec.
    """
    from core.auth import get_token as auth_get_token, has_credentials, AuthError

    if has_credentials(config):
        try:
            token = auth_get_token(config)
            if token:
                return token
        except AuthError:
            return None

    # Fallback fichier token
    token_file = Path(config.get("token_file", "Token-Bearer.txt"))
    if token_file.exists():
        content = token_file.read_text(encoding="utf-8").strip()
        if content.startswith("Bearer "):
            return content

    return None


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
        print(c.menu_option("0", f"{c.DIM}Retour{c.RESET}"))
        print()

        choice = input(c.prompt("  Votre choix: ")).strip()

        if choice == "0":
            return
        elif choice == "1":
            do_sync(config)
            state = get_app_state(config)


def do_sync(config):
    """Lance la synchronisation des bookmarks."""
    print()
    print(c.info("Connexion à Bluesky..."))

    token = get_token(config)
    if not token:
        print(c.error("Impossible d'obtenir un token d'authentification"))
        print(f"  {c.DIM}Vérifiez vos identifiants dans Paramètres{c.RESET}")
        input(f"\n{c.DIM}  Appuyez sur Entrée...{c.RESET}")
        return

    print(c.success("Authentification réussie"))
    print(c.info("Récupération des bookmarks..."))

    db = Database(config["db_file"])
    from core.bookmarks import BookmarkSync
    sync = BookmarkSync(config, db)

    def progress(page, count):
        print(f"  {c.DIM}Page {page}... {count} bookmarks{c.RESET}")

    result = sync.sync(token, on_progress=progress)
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

    input(f"\n{c.DIM}  Appuyez sur Entrée...{c.RESET}")


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
            input(f"\n{c.DIM}  Appuyez sur Entrée...{c.RESET}")


def cleanup_dead_links(config):
    """Supprime les liens morts de la base de données."""
    db = Database(config["db_file"])
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

    confirm = input(c.prompt("  Confirmer le nettoyage ? [O/n]: ")).strip().lower()
    if not confirm or confirm in ("o", "oui", "y", "yes"):
        count = db.cleanup_dead_posts()
        print(c.success(f"{count} entrée(s) supprimée(s)"))
    else:
        print(f"\n  {c.DIM}Nettoyage annulé{c.RESET}")

    db.close()
    input(f"\n{c.DIM}  Appuyez sur Entrée...{c.RESET}")


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

    confirm = input(c.prompt("  Confirmer ? (tapez 'RESET'): ")).strip()
    if confirm == "RESET":
        db_file = Path(config["db_file"])
        if db_file.exists():
            db_file.unlink()
            print(c.success("Base de données réinitialisée"))
        else:
            print(c.warning("Aucune base de données à réinitialiser"))
    else:
        print(f"\n  {c.DIM}Réinitialisation annulée{c.RESET}")

    input(f"\n{c.DIM}  Appuyez sur Entrée...{c.RESET}")


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
            input(f"\n{c.DIM}  Appuyez sur Entrée...{c.RESET}")
        elif choice == "5" and advanced:
            _edit_config_value(config, "token_file", "Fichier token")
        elif choice == "6" and advanced:
            _edit_config_value(config, "urls_file", "Fichier URLs")
        elif choice == "7" and advanced:
            from core.config import cleanup_logs
            deleted = cleanup_logs(config)
            print(c.success(f"{deleted} fichier(s) log supprimé(s)"))
            input(f"\n{c.DIM}  Appuyez sur Entrée...{c.RESET}")
        elif choice == "8" and advanced:
            download_media_dev(config)
            input(f"\n{c.DIM}  Appuyez sur Entrée...{c.RESET}")
        elif choice == "9" and advanced:
            download_media(config, force=True)
            input(f"\n{c.DIM}  Appuyez sur Entrée...{c.RESET}")
        else:
            print(c.error(f"Choix invalide : \"{choice}\""))
            input(f"\n{c.DIM}  Appuyez sur Entrée...{c.RESET}")


def configure_credentials(config):
    """Menu de configuration des identifiants Bluesky."""
    clear_screen()
    print(c.box_header("IDENTIFIANTS BLUESKY"))
    print()

    current_handle = config.get("bsky_handle", "")
    has_pwd = bool(config.get("bsky_app_password", ""))

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
    print(f"  {c.DIM}L'App Password sera stocké dans config.json (fichier local, hors Git){c.RESET}")
    print()
    print(c.separator())
    print()

    handle = input(c.prompt("  Handle Bluesky (ENTRÉE pour garder): ")).strip()
    if not handle and not current_handle:
        print(f"\n  {c.DIM}Configuration annulée{c.RESET}")
        input(f"\n{c.DIM}  Appuyez sur Entrée...{c.RESET}")
        return
    if not handle:
        handle = current_handle

    app_password = input(c.prompt("  App Password (xxxx-xxxx-xxxx-xxxx): ")).strip()
    if not app_password:
        print(f"\n  {c.DIM}Configuration annulée{c.RESET}")
        input(f"\n{c.DIM}  Appuyez sur Entrée...{c.RESET}")
        return

    # Test immédiat
    print()
    print(c.info("Test de connexion..."))

    from core.auth import create_session, AuthError
    try:
        create_session(handle, app_password)
        print(c.success("Connexion réussie !"))

        config["bsky_handle"] = handle
        config["bsky_app_password"] = app_password
        save_config(config)
        print(c.success("Identifiants sauvegardés"))

    except AuthError as e:
        print(c.error(f"Échec : {e}"))
        print(f"  {c.DIM}Identifiants non sauvegardés{c.RESET}")

    input(f"\n{c.DIM}  Appuyez sur Entrée...{c.RESET}")


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

    input(f"\n{c.DIM}  Appuyez sur Entrée...{c.RESET}")


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

    input(f"\n{c.DIM}  Appuyez sur Entrée...{c.RESET}")


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
        input(f"\n{c.DIM}  Appuyez sur Entrée...{c.RESET}")
        return

    # Si pas de sync récente, proposer d'en faire une
    if not state["has_urls"]:
        clear_screen()
        print(c.box_header("TÉLÉCHARGER"))
        print()
        print(c.info("Aucune synchronisation effectuée"))
        print()
        confirm = input(c.prompt("  Synchroniser les bookmarks maintenant ? [O/n]: ")).strip().lower()
        if confirm and confirm not in ("o", "oui", "y", "yes"):
            return
        do_sync(config)
        state = get_app_state(config)

    if state["new_count"] == 0:
        print()
        print(c.success("Tout est à jour — aucun nouveau bookmark à télécharger"))
        input(f"\n{c.DIM}  Appuyez sur Entrée...{c.RESET}")
        return

    download_media(config, force=False)
    input(f"\n{c.DIM}  Appuyez sur Entrée...{c.RESET}")


def download_media(config, force=False):
    """Télécharge les médias via l'orchestrateur."""
    urls_file = Path(config["urls_file"])
    if not urls_file.exists():
        print(c.error(f"Fichier {config['urls_file']} introuvable"))
        return False

    with open(urls_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print(c.warning("Aucune URL à traiter"))
        return False

    media_dirs = get_media_dirs(config)
    db = Database(config["db_file"])

    if force:
        urls_to_process = urls
        print()
        print(c.warning(f"Mode FORCE : {len(urls)} posts seront tous traités"))
    else:
        urls_to_process = db.get_new_posts(urls)
        new = len(urls_to_process)
        total = len(urls)
        print()
        print(c.info(f"{total} URLs au total, {c.VALUE}{new}{c.RESET} nouvelles"))

    if not urls_to_process:
        print(c.success("Tous les posts sont déjà traités"))
        db.close()
        return True

    print()
    confirm = input(c.prompt(f"  Traiter {len(urls_to_process)} posts ? [O/n]: ")).strip().lower()
    if confirm and confirm not in ("o", "oui", "y", "yes"):
        db.close()
        return False

    print()
    print(c.info("Lancement du téléchargement..."))
    print()

    result = subprocess.run(
        ["python", "core/orchestrator.py", media_dirs["img_dir"], media_dirs["vid_dir"]] + urls_to_process,
        encoding="utf-8",
        errors="replace",
    )

    db.close()
    return result.returncode == 0


def download_media_dev(config):
    """Mode dev : télécharge depuis urls.txt sans token ni DB."""
    urls_file = Path(config["urls_file"])
    if not urls_file.exists() or urls_file.stat().st_size == 0:
        print(c.warning("Aucune URL disponible dans urls.txt"))
        return False

    with open(urls_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print(c.warning("Aucune URL à traiter"))
        return False

    media_dirs = get_media_dirs(config)

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

    confirm = input(c.prompt(f"  Traiter {len(urls)} posts en mode dev ? [O/n]: ")).strip().lower()
    if confirm and confirm not in ("o", "oui", "y", "yes"):
        return False

    result = subprocess.run(
        ["python", "core/orchestrator.py", media_dirs["img_dir"], media_dirs["vid_dir"], "--no-db"] + urls
    )
    return result.returncode == 0


# ─── Utilitaires ─────────────────────────────────────────────

def open_download_folder(config):
    """Ouvre le dossier de téléchargements."""
    download_dir = config["download_dir"]
    if sys.platform == "win32":
        os.startfile(download_dir)
    else:
        subprocess.run(["xdg-open", download_dir])


# ─── Boucle principale ──────────────────────────────────────

def main():
    config = load_config()
    ensure_dirs(config)
    from core.config import cleanup_old_logs
    cleanup_old_logs(config)

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
            input(f"\n{c.DIM}  Appuyez sur Entrée...{c.RESET}")


if __name__ == "__main__":
    main()
