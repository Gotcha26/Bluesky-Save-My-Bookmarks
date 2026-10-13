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

from core import cli, i18n
from core.bookmarks import pending_downloads, read_urls, run_sync
from core.bookmarks_cache import post_views_from_config
from core.colors import c
from core.config import ensure_dirs, load_config, resolve_path, restrict_permissions, save_config
from core.database import Database
from core.i18n import _, _n
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
        # Meilleur effort : la taille affichée est approximative si un fichier disparaît.
        pass
    return total


def format_size(size_bytes):
    """Formate une taille en octets lisible."""
    for unit in [_("o"), _("Ko"), _("Mo"), _("Go")]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} {_('To')}"


def format_last_sync(iso_str):
    """Formate une date ISO en texte relatif lisible."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
        delta = datetime.now() - dt
        if delta.total_seconds() < 60:
            return _("à l'instant")
        elif delta.total_seconds() < 3600:
            mins = int(delta.total_seconds() // 60)
            return _("il y a {n} min").format(n=mins)
        elif delta.total_seconds() < 86400:
            hours = int(delta.total_seconds() // 3600)
            return _("il y a {n}h").format(n=hours)
        else:
            days = delta.days
            return _n("il y a {n} jour", "il y a {n} jours", days).format(n=days)
    except Exception:
        return iso_str[:16]


# ─── État de l'application ───────────────────────────────────


def get_app_state(config):
    """Récupère l'état complet de l'application."""
    db = Database(resolve_path(config, "db_file"))
    stats = db.get_stats()

    urls_file = resolve_path(config, "urls_file")
    has_urls = urls_file.exists() and urls_file.stat().st_size > 0
    url_count = len(read_urls(config)) if has_urls else 0
    # Même calcul que le téléchargement et « status » (AT-URI quand le cache existe)
    new_count = len(pending_downloads(config, db)[0])

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
        account_status = f"{c.WARNING}{_('non connecté')}{c.RESET}"

    media_total = state["stats"]["images"] + state["stats"]["videos"]
    if media_total > 0:
        media_status = _("{n} fichiers").format(n=f"{c.VALUE}{media_total}{c.RESET}")
    else:
        media_status = f"{c.DIM}{_('aucun')}{c.RESET}"

    print("  " + _("Compte: {compte} | Médias: {medias}").format(compte=account_status, medias=media_status))

    last_sync_str = format_last_sync(state["last_sync"])
    if last_sync_str:
        date = f"{c.DIM}{last_sync_str}{c.RESET}"
        print("  " + _("Dernière synchronisation: {date}").format(date=date))

    print()


# ─── Menu principal ──────────────────────────────────────────


def show_main_menu(state):
    """Affiche le menu principal novice-first."""
    print(c.menu_option("1", _("Mon compte     - Connexion et bookmarks en ligne")))
    print(c.menu_option("2", _("Stockage local - Dossier et statistiques")))
    print(c.menu_option("3", _("Paramètres     - Configuration de l'application")))
    print()

    # Option 4 : conditionnelle
    if not state["has_account"]:
        texte = _("4. Télécharger    - (connectez d'abord votre compte)")
        print(f"  {c.DIM}{texte}{c.RESET}")
    elif state["new_count"] > 0:
        label = _("Télécharger {n} nouveaux bookmarks").format(n=f"{c.VALUE}{state['new_count']}{c.RESET}")
        print(c.menu_option("4", label))
    elif state["has_urls"]:
        print(f"  {c.DIM}{_('4. Tout est à jour')}{c.RESET}")
    else:
        texte = _("4. Télécharger    - (synchronisez d'abord via Mon compte)")
        print(f"  {c.DIM}{texte}{c.RESET}")

    print()
    print(c.menu_option("0", f"{c.DIM}{_('Quitter')}{c.RESET}"))
    print()


# ─── Token ───────────────────────────────────────────────────


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


def _invite_choix(suffixe=""):
    """Invite « Votre choix » commune aux menus (suffixe : plage éventuelle, ex. « (0-9) »)."""
    return c.prompt(f"  {_('Votre choix')}{suffixe}: ")


def _choix_invalide(choice):
    """Message d'erreur d'un choix de menu inconnu."""
    return c.error(_('Choix invalide : "{choix}"').format(choix=choice))


# ─── Mon compte ──────────────────────────────────────────────


def menu_account(config, state):
    """Menu Mon compte : connexion et synchronisation."""
    while True:
        clear_screen()
        print(c.box_header(_("MON COMPTE")))
        print()

        if not state["has_account"]:
            # Pas de compte configuré → guidage
            print(c.warning(_("Aucun compte Bluesky connecté")))
            print()
            print(f"  {c.KEY}{_('Pour sauvegarder vos bookmarks, connectez votre compte :')}{c.RESET}")
            print()
            print(c.menu_option("1", _("Connecter mon compte Bluesky")))
            print()
            print(c.menu_option("0", f"{c.DIM}{_('Retour')}{c.RESET}"))
            print()

            choice = input(_invite_choix()).strip()
            if choice == "1":
                configure_credentials(config)
                state = get_app_state(config)
                continue
            else:
                return

        # Compte configuré → affichage + sync
        handle = config.get("bsky_handle", "")
        print(c.config_line(_("Compte"), f"{c.OK}{handle}{c.RESET}"))

        last_sync_str = format_last_sync(state["last_sync"])
        if last_sync_str:
            print(c.config_line(_("Dernière sync"), last_sync_str))

        # Statistiques en ligne vs local
        if state["has_urls"]:
            print()
            print(c.config_line(_("Bookmarks en ligne"), str(state["url_count"])))
            print(c.config_line(_("Posts traités"), str(state["stats"]["posts"])))
            if state["new_count"] > 0:
                print(c.config_line(_("Nouveaux"), f"{c.OK}{state['new_count']}{c.RESET}"))
            else:
                print(c.config_line(_("Nouveaux"), f"{c.DIM}{_('0 - tout est à jour')}{c.RESET}"))
        else:
            print()
            print(f"  {c.DIM}{_('Aucune synchronisation effectuée')}{c.RESET}")

        if state["stats"]["dead"] > 0:
            print(c.config_line(_("Liens morts"), f"{c.WARNING}{state['stats']['dead']}{c.RESET}"))

        print()
        print(c.separator())
        print()
        print(c.menu_option("1", _("Synchroniser les bookmarks")))
        print(c.menu_option("D", _("Déconnecter mon compte")))
        print(c.menu_option("0", f"{c.DIM}{_('Retour')}{c.RESET}"))
        print()

        choice = input(_invite_choix()).strip()

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
    print(
        c.warning(
            _("Le compte {handle} sera déconnecté (App Password supprimé de cet ordinateur).").format(
                handle=handle
            )
        )
    )
    print(f"  {c.DIM}{_('Vos fichiers téléchargés et la base ne sont pas touchés.')}{c.RESET}")
    if not confirm(_("Confirmer ?"), default=False):
        return False

    nettoye = delete_app_password(config, handle)
    config["bsky_handle"] = ""
    config["pds_url"] = ""
    save_config(config)
    if nettoye:
        print(c.success(_("Compte déconnecté")))
    else:
        print(
            c.warning(
                _(
                    "Compte déconnecté, mais le trousseau n'a pas pu être nettoyé : "
                    "supprimez l'entrée « bsmb » à la main."
                )
            )
        )
    pause()
    return True


def do_sync(config):
    """Lance la synchronisation des bookmarks."""
    print()
    print(c.info(_("Connexion à Bluesky...")))

    session = get_session(config)
    if not session:
        print(c.error(_("Impossible d'obtenir un token d'authentification")))
        print(f"  {c.DIM}{_('Vérifiez vos identifiants dans Paramètres')}{c.RESET}")
        pause()
        return

    print(c.success(_("Authentification réussie")))
    print(c.info(_("Récupération des bookmarks...")))

    def progress(page, count):
        ligne = _("Page {page}... {count} bookmarks").format(page=page, count=count)
        print(f"  {c.DIM}{ligne}{c.RESET}")

    db = Database(resolve_path(config, "db_file"))
    try:
        result = run_sync(config, db, session, on_progress=progress)
    finally:
        db.close()

    if result["error"]:
        if result.get("expired"):
            print(c.error(_("Token expiré — reconnectez votre compte")))
        else:
            print(c.error(_("Erreur : {erreur}").format(erreur=result["error"])))
    else:
        print()
        print(c.success(_("Synchronisation terminée")))
        print(c.config_line(_("Bookmarks en ligne"), str(result["online_count"])))
        print(c.config_line(_("Déjà traités"), str(result["local_count"])))
        if result["new_count"] > 0:
            print(c.config_line(_("Nouveaux"), f"{c.OK}{result['new_count']}{c.RESET}"))
        else:
            print(c.config_line(_("Nouveaux"), f"{c.DIM}{_('0 - tout est à jour')}{c.RESET}"))
        if result.get("cache_error"):
            print(
                c.warning(_("Cache des bookmarks non écrit : {erreur}").format(erreur=result["cache_error"]))
            )

    pause()


# ─── Stockage local ──────────────────────────────────────────


def menu_local_storage(config, state):
    """Menu Stockage local : stats, dossier, nettoyage."""
    while True:
        clear_screen()
        print(c.box_header(_("STOCKAGE LOCAL")))
        print()

        stats = state["stats"]
        total_media = stats["images"] + stats["videos"]

        print(c.config_line(_("Posts traités"), str(stats["posts"])))
        print(c.config_line(_("Images téléchargées"), str(stats["images"])))
        print(c.config_line(_("Vidéos téléchargées"), str(stats["videos"])))
        print(c.config_line(_("Textes sauvegardés"), str(stats["texts"])))
        print(c.config_line(_("Total médias"), str(total_media)))

        # Taille du dossier
        download_dir = config["download_dir"]
        if Path(download_dir).exists():
            size = get_folder_size(download_dir)
            print(c.config_line(_("Taille du dossier"), format_size(size)))

        print(c.config_line(_("Destination"), f"{c.VALUE}{download_dir}{c.RESET}"))

        # Liens morts
        if stats["dead"] > 0:
            print()
            print(c.warning(_dead_links_label(stats["dead"])))

        print()
        print(c.separator())
        print()

        options = []
        print(c.menu_option("1", _("Ouvrir le dossier de téléchargements")))
        options.append("1")

        if stats["dead"] > 0:
            print(c.menu_option("2", _("Nettoyer les liens morts ({n})").format(n=stats["dead"])))
            options.append("2")

        print(c.menu_option("R", f"{c.WARNING}{_('Réinitialiser la base de données')}{c.RESET}"))
        print(c.menu_option("0", f"{c.DIM}{_('Retour')}{c.RESET}"))
        print()

        choice = input(_invite_choix()).strip().upper()

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
            print(_choix_invalide(choice))
            pause()


def _dead_links_label(n):
    """« N lien(s) mort(s) détecté(s) » accordé en nombre."""
    return _n("{n} lien mort détecté", "{n} liens morts détectés", n).format(n=n)


def cleanup_dead_links(config):
    """Supprime les liens morts de la base de données."""
    db = Database(resolve_path(config, "db_file"))
    dead_posts = db.get_dead_posts()

    clear_screen()
    print(c.box_header(_("NETTOYAGE DES LIENS MORTS")))
    print()
    nb_morts = len(dead_posts)
    print(c.warning(_n("{n} lien mort détecté :", "{n} liens morts détectés :", nb_morts).format(n=nb_morts)))
    print()

    for url, status in dead_posts[:10]:
        label = _("supprimé") if status == "deleted" else status
        print(f"  {c.DIM}-{c.RESET} {c.DIM}{label}{c.RESET} : {url}")

    if len(dead_posts) > 10:
        autres = _("... et {n} autres").format(n=len(dead_posts) - 10)
        print(f"  {c.DIM}{autres}{c.RESET}")

    print()
    print(c.separator())
    print()
    print(f"  {c.KEY}{_('Cette action va supprimer ces entrées de la base.')}{c.RESET}")
    print(f"  {c.DIM}{_('Les fichiers déjà téléchargés ne seront pas supprimés.')}{c.RESET}")
    print()

    if confirm(_("Confirmer le nettoyage ?")):
        count = db.cleanup_dead_posts()
        print(c.success(_n("{n} entrée supprimée", "{n} entrées supprimées", count).format(n=count)))
    else:
        print(f"\n  {c.DIM}{_('Nettoyage annulé')}{c.RESET}")

    db.close()
    pause()


def reset_database(config):
    """Réinitialisation de la base de données avec confirmation."""
    clear_screen()
    print(c.box_header(_("RÉINITIALISATION")))
    print()
    print(c.warning(_("Cette action va :")))
    print(f"    {c.DIM}-{c.RESET} " + _("Supprimer l'historique des posts traités"))
    print(f"    {c.DIM}-{c.RESET} " + _("Supprimer l'historique des médias téléchargés"))
    print(
        "    "
        + f"{c.DIM}-{c.RESET} "
        + _("{ne_pas} supprimer les fichiers déjà téléchargés").format(ne_pas=f"{c.OK}{_('NE PAS')}{c.RESET}")
    )
    print()
    print(c.separator())
    print()

    saisie = input(c.prompt("  " + _("Confirmer ? (tapez 'RESET'):") + " ")).strip()
    if saisie == "RESET":
        db_file = resolve_path(config, "db_file")
        if db_file.exists():
            db_file.unlink()
            print(c.success(_("Base de données réinitialisée")))
        else:
            print(c.warning(_("Aucune base de données à réinitialiser")))
    else:
        print(f"\n  {c.DIM}{_('Réinitialisation annulée')}{c.RESET}")

    pause()


# ─── Paramètres ──────────────────────────────────────────────


def menu_settings(config, state):
    """Menu Paramètres : configuration de l'application."""
    while True:
        clear_screen()
        print(c.box_header(_("PARAMÈTRES")))
        print()

        from core.auth import has_credentials

        if has_credentials(config):
            auth_status = f"{c.OK}{_('connecté')}{c.RESET}"
        else:
            auth_status = f"{c.DIM}{_('non connecté')}{c.RESET}"
        advanced = config.get("advanced_mode", False)

        print(c.config_line(_("1. Identifiants Bluesky"), auth_status))
        print(c.config_line(_("2. Dossier téléchargements"), config["download_dir"]))
        print(c.config_line(_("3. Workers parallèles"), str(config.get("max_workers", 4))))

        if advanced:
            print(c.config_line(_("4. Mode avancé"), f"{c.OK}{_('activé')}{c.RESET}"))
        else:
            print(c.config_line(_("4. Mode avancé"), f"{c.DIM}{_('désactivé')}{c.RESET}"))
        print(c.config_line(_("L. Langue"), _langue_libelle(config)))

        if advanced:
            print()
            print(c.title("  " + _("OPTIONS AVANCÉES")))
            print(c.separator())
            print(c.config_line(_("5. Fichier token (fallback)"), config["token_file"]))
            print(c.config_line(_("6. Fichier URLs"), config["urls_file"]))
            print(c.menu_option("7", _("Supprimer les logs")))
            print(c.menu_option("8", _("Mode dev - Depuis urls.txt, sans token")))
            force = _("{force_dl} - Re-télécharger tous les médias").format(
                force_dl=f"{c.WARNING}Force DL{c.RESET}"
            )
            print(c.menu_option("9", force))

        print()
        print(c.separator())
        print(f"  {c.DIM}{_('Entrez le numéro pour modifier, ou 0 pour revenir')}{c.RESET}")
        print()
        print(c.menu_option("0", f"{c.DIM}{_('Retour')}{c.RESET}"))
        print()

        max_choice = "9" if advanced else "4"
        choice = input(_invite_choix(f" (0-{max_choice}, L)")).strip()

        if choice == "0":
            break
        elif choice.upper() == "L":
            _edit_language(config)
        elif choice == "1":
            configure_credentials(config)
            get_app_state(config)
        elif choice == "2":
            _edit_config_value(
                config,
                "download_dir",
                _("Dossier de téléchargements"),
                after_save=lambda: ensure_dirs(config),
            )
        elif choice == "3":
            _edit_workers(config)
        elif choice == "4":
            config["advanced_mode"] = not config.get("advanced_mode", False)
            save_config(config)
            if config["advanced_mode"]:
                print(c.success(_("Mode avancé activé")))
            else:
                print(c.success(_("Mode avancé désactivé")))
            pause()
        elif choice == "5" and advanced:
            _edit_config_value(config, "token_file", _("Fichier token"))
        elif choice == "6" and advanced:
            _edit_config_value(config, "urls_file", _("Fichier URLs"))
        elif choice == "7" and advanced:
            from core.config import cleanup_logs

            deleted = cleanup_logs(config)
            print(
                c.success(
                    _n("{n} fichier log supprimé", "{n} fichiers log supprimés", deleted).format(n=deleted)
                )
            )
            pause()
        elif choice == "8" and advanced:
            download_media_dev(config)
            pause()
        elif choice == "9" and advanced:
            download_media(config, force=True)
            pause()
        else:
            print(_choix_invalide(choice))
            pause()


def configure_credentials(config):
    """Menu de configuration des identifiants Bluesky."""
    clear_screen()
    print(c.box_header(_("IDENTIFIANTS BLUESKY")))
    print()

    current_handle = config.get("bsky_handle", "")
    has_pwd = bool(current_handle) and bool(load_app_password(config, current_handle))

    non_configure = f"{c.DIM}{_('non configuré')}{c.RESET}"
    print(c.config_line(_("Handle actuel"), current_handle or non_configure))
    print(c.config_line(_("App Password"), f"{c.OK}{_('configuré')}{c.RESET}" if has_pwd else non_configure))
    print()
    print(c.separator())
    print()
    print(f"  {c.KEY}{_('Pour créer un App Password :')}{c.RESET}")
    chemin_bsky = f"{c.VALUE}bsky.app > Settings > App Passwords{c.RESET}"
    print(f"    {c.DIM}1.{c.RESET} " + _("Allez sur {chemin}").format(chemin=chemin_bsky))
    bouton = f"{c.VALUE}Add App Password{c.RESET}"
    print(f"    {c.DIM}2.{c.RESET} " + _("Cliquez sur {bouton}").format(bouton=bouton))
    print(f"    {c.DIM}3.{c.RESET} " + _("Nommez-le (ex: 'BSMB') et copiez le mot de passe généré"))
    print()
    if backend_name() == "keyring":
        stockage = _("L'App Password sera stocké dans le trousseau du système (keyring)")
    else:
        stockage = _("L'App Password sera stocké dans config.json (fichier local, hors Git)")
    print(f"  {c.DIM}{stockage}{c.RESET}")
    conseil = _("Conseil : créez un App Password dédié à BSMB et révoquez-le en cas de doute.")
    print(f"  {c.DIM}{conseil}{c.RESET}")
    print()
    print(c.separator())
    print()

    handle = input(c.prompt(f"  {_('Handle Bluesky (ENTRÉE pour garder):')} ")).strip()
    if not handle and not current_handle:
        print(f"\n  {c.DIM}{_('Configuration annulée')}{c.RESET}")
        pause()
        return
    if not handle:
        handle = current_handle

    app_password = input(c.prompt(f"  {_('App Password (xxxx-xxxx-xxxx-xxxx):')} ")).strip()
    if not app_password:
        print(f"\n  {c.DIM}{_('Configuration annulée')}{c.RESET}")
        pause()
        return

    # Test immédiat
    print()
    print(c.info(_("Test de connexion...")))

    from core.auth import AuthError, create_session

    try:
        session = create_session(handle, app_password)
        print(c.success(_("Connexion réussie !")))

        if current_handle and current_handle != handle:
            delete_app_password(config, current_handle)  # ne pas laisser l'ancien secret
        backend = store_app_password(config, handle, app_password)
        config["bsky_handle"] = handle
        config["pds_url"] = session["pds_url"]
        if backend == "config.json" and not config.get("warned_plaintext_secret", False):
            print(c.warning(_("AVERTISSEMENT : l'App Password est stocké en clair dans config.json.")))
            installer = _(
                "Installez keyring (pip install keyring) pour le placer dans le trousseau du système."
            )
            print(f"  {c.DIM}{installer}{c.RESET}")
            config["warned_plaintext_secret"] = True
        save_config(config)
        if backend == "keyring":
            print(c.success(_("Identifiants sauvegardés (trousseau du système)")))
        else:
            print(c.success(_("Identifiants sauvegardés")))

    except AuthError as e:
        print(c.error(_("Échec : {erreur}").format(erreur=e)))
        print(f"  {c.DIM}{_('Identifiants non sauvegardés')}{c.RESET}")

    pause()


def _edit_config_value(config, key, label, after_save=None):
    """Édite une valeur de configuration."""
    print()
    print(f"  {c.KEY}{_('Actuel:')}{c.RESET} {c.VALUE}{config[key]}{c.RESET}")
    invite = _("Nouveau {label} (ENTRÉE pour garder):").format(label=label)
    new_val = input(c.prompt(f"  {invite} ")).strip()

    if new_val:
        config[key] = new_val
        save_config(config)
        if after_save:
            after_save()
        print(c.success(_("Sauvegardé")))
    else:
        print(c.success(_("Valeur inchangée")))

    pause()


LANGUES_NOMS = {"fr": "Français", "en": "English"}  # noms dans leur propre langue : jamais traduits


def _langue_libelle(config):
    """Langue choisie dans la config, pour l'affichage (« auto » : la langue détectée est indiquée)."""
    code = config.get("language") or ""
    if code in LANGUES_NOMS:
        return LANGUES_NOMS[code]
    return _("Automatique ({langue})").format(langue=LANGUES_NOMS.get(i18n.detect_language(), "?"))


def _edit_language(config):
    """Choix de la langue de l'interface ; prise en compte immédiate (config["language"] : fr, en ou "")."""
    print()
    print(f"  {c.KEY}{_('Actuel:')}{c.RESET} {c.VALUE}{_langue_libelle(config)}{c.RESET}")
    print()
    print(c.menu_option("1", LANGUES_NOMS["fr"]))
    print(c.menu_option("2", LANGUES_NOMS["en"]))
    print(c.menu_option("3", _("Automatique (langue du système)")))
    print()
    choice = input(c.prompt(f"  {_('Votre choix (ENTRÉE pour garder):')} ")).strip()

    if not choice:
        print(c.success(_("Valeur inchangée")))
    elif choice in ("1", "2", "3"):
        config["language"] = {"1": "fr", "2": "en", "3": ""}[choice]
        save_config(config)
        i18n.init(config["language"] or None)  # prise en compte immédiate
        print(c.success(_("Langue mise à jour : {langue}").format(langue=_langue_libelle(config))))
    else:
        print(_choix_invalide(choice))

    pause()


def _edit_workers(config):
    """Édite le nombre de workers parallèles."""
    current = config.get("max_workers", 4)
    print()
    print(f"  {c.KEY}{_('Actuel:')}{c.RESET} " + _("{n} workers").format(n=f"{c.VALUE}{current}{c.RESET}"))
    print(f"  {c.DIM}{_('Plage recommandée : 1 (séquentiel) à 8 (rapide)')}{c.RESET}")
    new_val = input(c.prompt(f"  {_('Nombre de workers (ENTRÉE pour garder):')} ")).strip()

    if new_val:
        try:
            n = int(new_val)
            if n < 1:
                n = 1
            elif n > 16:
                n = 16
                print(c.warning(_("Limité à {n} workers maximum").format(n=n)))
            config["max_workers"] = n
            save_config(config)
            print(c.success(_("Workers mis à jour : {n}").format(n=n)))
        except ValueError:
            print(c.error(_("Valeur invalide (nombre entier attendu)")))
    else:
        print(c.success(_("Valeur inchangée")))

    pause()


# ─── Téléchargement ──────────────────────────────────────────


def menu_download_new(config, state):
    """Menu Télécharger : synchronise si besoin, puis télécharge les nouveaux."""
    if not state["has_account"]:
        clear_screen()
        print(c.box_header(_("TÉLÉCHARGER")))
        print()
        print(c.warning(_("Aucun compte Bluesky connecté")))
        print()
        print(f"  {c.KEY}" + _("Connectez d'abord votre compte :") + f"{c.RESET}")
        print(f"    {c.DIM}{_('Menu principal > 1. Mon compte')}{c.RESET}")
        pause()
        return

    # Si pas de sync récente, proposer d'en faire une
    if not state["has_urls"]:
        clear_screen()
        print(c.box_header(_("TÉLÉCHARGER")))
        print()
        print(c.info(_("Aucune synchronisation effectuée")))
        print()
        if not confirm(_("Synchroniser les bookmarks maintenant ?")):
            return
        do_sync(config)
        state = get_app_state(config)

    if state["new_count"] == 0:
        print()
        print(c.success(_("Tout est à jour — aucun nouveau bookmark à télécharger")))
        pause()
        return

    download_media(config, force=False)
    pause()


def download_media(config, force=False):
    """Télécharge les médias via l'orchestrateur."""
    urls_file = resolve_path(config, "urls_file")
    if not urls_file.exists():
        print(c.error(_("Fichier {fichier} introuvable").format(fichier=config["urls_file"])))
        return False

    urls = read_urls(config)

    if not urls:
        print(c.warning(_("Aucune URL à traiter")))
        return False

    db = Database(resolve_path(config, "db_file"))

    if force:
        urls_to_process = urls
        post_views = post_views_from_config(config)
        print()
        print(c.warning(_("Mode FORCE : {n} posts seront tous traités").format(n=len(urls))))
    else:
        # Comparaison par AT-URI quand le cache existe (un changement de handle ne retélécharge rien)
        urls_to_process, post_views = pending_downloads(config, db)
        new = len(urls_to_process)
        total = len(urls)
        print()
        print(
            c.info(
                _("{total} URLs au total, {new} nouvelles").format(
                    total=total, new=f"{c.VALUE}{new}{c.RESET}"
                )
            )
        )

    if not urls_to_process:
        print(c.success(_("Tous les posts sont déjà traités")))
        db.close()
        return True

    print()
    if not confirm(_("Traiter {n} posts ?").format(n=len(urls_to_process))):
        db.close()
        return False

    db.close()

    print()
    print(c.info(_("Lancement du téléchargement...")))
    print()

    # Vues hydratées de la dernière synchro : évitent un getRecord par post
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
        print(c.warning(_("Aucune URL disponible dans urls.txt")))
        return False

    with open(urls_file, encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print(c.warning(_("Aucune URL à traiter")))
        return False

    clear_screen()
    print(c.box_header(_("MODE DÉVELOPPEMENT")))
    print()
    print(c.warning(_("Traitement direct depuis urls.txt")))
    print(c.config_line("Token", f"{c.DIM}{_('non vérifié')}{c.RESET}"))
    print(c.config_line(_("Base de données"), f"{c.DIM}{_('non mise à jour')}{c.RESET}"))
    print(c.config_line(_("Posts à traiter"), f"{c.VALUE}{len(urls)}{c.RESET}"))
    print()
    print(c.separator())
    print()

    if not confirm(_("Traiter {n} posts en mode dev ?").format(n=len(urls))):
        return False

    stats = run(urls, config, no_db=True)
    _proposer_ouverture(config, stats)
    return stats["success"] > 0


def _proposer_ouverture(config, stats):
    """Propose d'ouvrir le dossier de téléchargements si au moins un post a réussi."""
    if stats["success"] > 0 and config.get("open_folder_after_download", True):
        print()
        if confirm(_("Ouvrir le dossier de téléchargements ?")):
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
    demandee = cli.langue_demandee(argv)
    if demandee in cli.LANGUES_CLI:
        i18n.init(demandee)  # aide et erreurs d'argparse dans la langue demandée
    args = cli.build_parser().parse_args(argv)
    if args.command is not None:
        return cli.main(argv)

    if args.yes:
        set_yes(True)
    config = load_config()
    i18n.init(args.lang or config.get("language") or None)  # --lang l'emporte sur la configuration
    migrate_secret_to_keyring(config)  # App Password en clair -> keyring si disponible
    ensure_dirs(config)
    from core.config import cleanup_old_logs

    cleanup_old_logs(config)

    try:
        run_menu(config)
    except (EOFError, KeyboardInterrupt):
        print(f"\n  {c.DIM}{_('Entrée interrompue — fin du programme')}{c.RESET}")
    return 0


def run_menu(config):
    """Boucle du menu interactif."""
    while True:
        clear_screen()
        state = get_app_state(config)
        print_header(config, state)
        show_main_menu(state)

        choice = input(_invite_choix()).strip()

        if choice == "0":
            print(f"\n  {c.DIM}{_('Au revoir !')}{c.RESET}")
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
            print(_choix_invalide(choice))
            pause()


if __name__ == "__main__":
    # Forcer l'encodage UTF-8 pour la console Windows (exécution directe uniquement,
    # sinon conflit avec la capture de sortie de pytest)
    if sys.platform == "win32":
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    sys.exit(main())
