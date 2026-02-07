#!/usr/bin/env python3
"""
BSMB - Bsky Save My Bookmarks
Interface unifiée pour exporter et télécharger vos bookmarks Bluesky
"""
import sys
import os
import subprocess
from pathlib import Path
from core.config import load_config, save_config, ensure_dirs, get_media_dirs
from core.database import Database
from core.colors import c


def clear_screen():
    subprocess.run("cls" if sys.platform == "win32" else "clear", shell=True)


def get_app_state(config):
    """Récupère l'état complet de l'application pour l'affichage."""
    db = Database(config["db_file"])
    stats = db.get_stats()
    db.close()

    urls_file = Path(config["urls_file"])
    has_urls = urls_file.exists() and urls_file.stat().st_size > 0
    url_count = 0
    if has_urls:
        with open(urls_file, "r", encoding="utf-8") as f:
            url_count = sum(1 for line in f if line.strip())

    has_downloads = stats["images"] > 0 or stats["videos"] > 0

    token_file = Path(config["token_file"])
    token_ok = False
    if token_file.exists():
        content = token_file.read_text(encoding="utf-8").strip()
        token_ok = content.startswith("Bearer ")

    return {
        "stats": stats,
        "has_urls": has_urls,
        "url_count": url_count,
        "has_downloads": has_downloads,
        "token_ok": token_ok,
    }


def print_header(config, state):
    """Affiche l'en-tête avec ligne de statut."""
    print(c.box_header("BSMB - BSKY SAVE MY BOOKMARKS"))

    # Ligne de statut
    token_status = f"{c.OK}OK{c.RESET}" if state["token_ok"] else f"{c.WARNING}manquant{c.RESET}"
    urls_status = (
        f"{c.VALUE}{state['url_count']}{c.RESET} liens"
        if state["has_urls"]
        else f"{c.DIM}aucun{c.RESET}"
    )
    media_total = state["stats"]["images"] + state["stats"]["videos"]
    media_status = (
        f"{c.VALUE}{media_total}{c.RESET} fichiers"
        if media_total > 0
        else f"{c.DIM}aucun{c.RESET}"
    )

    print(
        f"  Token: [{token_status}] | "
        f"Bookmarks: {urls_status} | "
        f"Medias: {media_status}"
    )
    print(f"  Destination: {c.VALUE}{config['download_dir']}{c.RESET}")
    print()


def show_main_menu(state):
    """Affiche le menu principal catégorisé."""
    print(c.title("BOOKMARKS"))
    print(c.separator())
    print(c.menu_option("1", "Exporter       - Sauvegarder les liens depuis Bluesky"))

    if state["has_urls"]:
        print(c.menu_option("2", "Telecharger    - Recuperer les nouveaux medias"))
    else:
        print(
            f"  {c.DIM}2. Telecharger    - "
            f"(exportez d'abord vos bookmarks){c.RESET}"
        )

    print()
    print(c.title("OUTILS"))
    print(c.separator())
    print(c.menu_option("3", "Statistiques   - Voir l'etat de la base"))

    if state["has_downloads"]:
        print(c.menu_option("4", "Ouvrir dossier - Explorer les telechargements"))

    print()
    print(c.title("CONFIGURATION"))
    print(c.separator())
    print(c.menu_option("5", "Configuration  - Modifier les parametres"))
    print(c.menu_option("9", "Avance         - Options developpeur"))
    print()
    print(c.menu_option("0", f"{c.DIM}Quitter{c.RESET}"))
    print()


# ─── Token ────────────────────────────────────────────────────

def get_token_from_clipboard():
    """Récupère le token depuis le presse-papier."""
    try:
        import win32clipboard  # type: ignore
        win32clipboard.OpenClipboard()
        token = win32clipboard.GetClipboardData()
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


def check_token(config):
    """Vérifie la présence du token Bearer."""
    token_file = Path(config["token_file"])

    if token_file.exists():
        content = token_file.read_text(encoding="utf-8").strip()
        if content and content.startswith("Bearer "):
            return True

    clear_screen()
    print(c.box_header("TOKEN BEARER"))
    print()
    print(c.warning("Token manquant ou invalide"))
    print()
    print(
        f"  {c.KEY}Pour recuperer votre token :{c.RESET}\n"
        f"  Consultez {c.VALUE}Instructions-token.md{c.RESET}"
    )
    print()
    print(c.separator())
    print(c.menu_option("1", "Coller depuis le presse-papier"))
    print(c.menu_option("2", "Lire depuis Token-Bearer.txt"))
    print(c.menu_option("0", f"{c.DIM}Annuler{c.RESET}"))
    print()

    choice = input(c.prompt("  Votre choix (0-2): ")).strip()

    if choice == "1":
        token = get_token_from_clipboard()
        if token and token.startswith("Bearer "):
            token_file.write_text(token, encoding="utf-8")
            print(c.success("Token enregistre depuis le presse-papier"))
            return True
        else:
            print(c.error("Token invalide (doit commencer par 'Bearer ')"))
            return False
    elif choice == "2":
        if token_file.exists():
            content = token_file.read_text(encoding="utf-8").strip()
            if content.startswith("Bearer "):
                print(c.success("Token valide trouve dans Token-Bearer.txt"))
                return True
        print(c.error("Token invalide dans Token-Bearer.txt"))
        return False

    return False


# ─── Actions principales ──────────────────────────────────────

def export_bookmarks(config):
    """Exporte les bookmarks."""
    if not check_token(config):
        return False

    clear_screen()
    print(c.box_header("EXPORT DES BOOKMARKS"))
    print()
    print(f"  {c.KEY}Cette operation va :{c.RESET}")
    print(f"    {c.DIM}-{c.RESET} Recuperer la liste complete de vos bookmarks Bluesky")
    print(f"    {c.DIM}-{c.RESET} Creer/mettre a jour le fichier urls.txt")
    print(f"    {c.DIM}-{c.RESET} Sauvegarder l'ancien urls.txt en urls.txt.bak")
    print()
    print(c.separator())
    print()

    confirm = input(c.prompt("  Lancer l'export ? [O/n]: ")).strip().lower()
    if confirm and confirm not in ("o", "oui", "y", "yes"):
        return False

    print()
    result = subprocess.run(
        ["python", "api/export_bookmarks.py"],
        capture_output=False,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode == 0:
        print(c.success("Export termine"))
    return result.returncode == 0


def download_media(config, force=False, skip_token_check=False):
    """Télécharge les médias."""
    urls_file = Path(config["urls_file"])
    if not urls_file.exists():
        print(c.error(f"Fichier {config['urls_file']} introuvable"))
        print(f"  {c.DIM}Lancez d'abord l'export des bookmarks (option 1){c.RESET}")
        return False

    with open(urls_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print(c.warning("Aucune URL a traiter"))
        return False

    media_dirs = get_media_dirs(config)

    if skip_token_check:
        clear_screen()
        print(c.box_header("MODE DEVELOPPEMENT"))
        print()
        print(c.warning("Traitement direct depuis urls.txt"))
        print(c.config_line("Token", f"{c.DIM}non verifie{c.RESET}"))
        print(c.config_line("Base de donnees", f"{c.DIM}non mise a jour{c.RESET}"))
        print(c.config_line("Posts a traiter", f"{c.VALUE}{len(urls)}{c.RESET}"))
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

    db = Database(config["db_file"])

    if force:
        urls_to_process = urls
        print()
        print(c.warning(f"Mode FORCE : {len(urls)} posts seront tous traites"))
    else:
        urls_to_process = db.get_new_posts(urls)
        new = len(urls_to_process)
        total = len(urls)
        print()
        print(c.info(f"{total} URLs au total, {c.VALUE}{new}{c.RESET} nouvelles"))

    if not urls_to_process:
        print(c.success("Tous les posts sont deja traites"))
        db.close()
        return True

    print()
    confirm = input(c.prompt(f"  Traiter {len(urls_to_process)} posts ? [O/n]: ")).strip().lower()
    if confirm and confirm not in ("o", "oui", "y", "yes"):
        db.close()
        return False

    print()
    print(c.info("Lancement du telechargement..."))
    print()

    result = subprocess.run(
        ["python", "core/orchestrator.py", media_dirs["img_dir"], media_dirs["vid_dir"]] + urls_to_process,
        encoding="utf-8",
        errors="replace",
    )

    db.close()
    return result.returncode == 0


# ─── Statistiques ─────────────────────────────────────────────

def show_stats(config):
    """Affiche les statistiques avec option de reset."""
    db = Database(config["db_file"])
    stats = db.get_stats()
    db.close()

    while True:
        clear_screen()
        print(c.box_header("STATISTIQUES"))
        print()

        total_media = stats["images"] + stats["videos"]
        print(c.config_line("Posts trackes", str(stats["posts"])))
        print(c.config_line("Images telechargees", str(stats["images"])))
        print(c.config_line("Videos telechargees", str(stats["videos"])))
        print(c.config_line("Total medias", str(total_media)))
        print()
        print(c.separator())
        print()
        print(c.menu_option("R", f"{c.WARNING}Reinitialiser la base de donnees{c.RESET}"))
        print(c.menu_option("0", f"{c.DIM}Retour{c.RESET}"))
        print()

        choice = input(c.prompt("  Votre choix: ")).strip().upper()

        if choice == "0":
            return
        elif choice == "R":
            reset_database(config)
            # Rafraîchir les stats
            db = Database(config["db_file"])
            stats = db.get_stats()
            db.close()
        else:
            print(c.error(f"Choix invalide : \"{choice}\""))
            input(f"\n{c.DIM}  Appuyez sur Entree...{c.RESET}")


def reset_database(config):
    """Réinitialisation de la base de données avec confirmation."""
    clear_screen()
    print(c.box_header("REINITIALISATION"))
    print()
    print(c.warning("Cette action va :"))
    print(f"    {c.DIM}-{c.RESET} Supprimer l'historique des posts traites")
    print(f"    {c.DIM}-{c.RESET} Supprimer l'historique des medias telecharges")
    print(f"    {c.DIM}-{c.RESET} {c.OK}NE PAS{c.RESET} supprimer les fichiers deja telecharges")
    print()
    print(c.separator())
    print()

    confirm = input(c.prompt("  Confirmer ? (tapez 'RESET'): ")).strip()
    if confirm == "RESET":
        db_file = Path(config["db_file"])
        if db_file.exists():
            db_file.unlink()
            print(c.success("Base de donnees reinitialisee"))
        else:
            print(c.warning("Aucune base de donnees a reinitialiser"))
    else:
        print(f"\n  {c.DIM}Reinitialisation annulee{c.RESET}")

    input(f"\n{c.DIM}  Appuyez sur Entree...{c.RESET}")


# ─── Configuration ────────────────────────────────────────────

def configure(config):
    """Menu de configuration avec paramètres éditables."""
    while True:
        clear_screen()
        print(c.box_header("CONFIGURATION"))
        print()
        print(c.title("Parametres actuels:"))
        print()
        print(c.config_line("1. Dossier telechargements", config["download_dir"]))
        print(c.config_line("2. Fichier token", config["token_file"]))
        print(c.config_line("3. Fichier URLs", config["urls_file"]))
        print()
        print(c.separator())
        print(
            f"  {c.DIM}Entrez le numero d'un parametre pour le modifier, "
            f"ou 0 pour revenir{c.RESET}"
        )
        print()
        print(c.menu_option("0", f"{c.DIM}Retour{c.RESET}"))
        print()

        choice = input(c.prompt("  Votre choix (0-3): ")).strip()

        if choice == "0":
            break
        elif choice == "1":
            _edit_config_value(
                config,
                "download_dir",
                "Dossier de telechargements",
                after_save=lambda: ensure_dirs(config),
            )
        elif choice == "2":
            _edit_config_value(config, "token_file", "Fichier token")
        elif choice == "3":
            _edit_config_value(config, "urls_file", "Fichier URLs")
        else:
            print(c.error(f"Choix invalide : \"{choice}\""))
            input(f"\n{c.DIM}  Appuyez sur Entree...{c.RESET}")


def _edit_config_value(config, key, label, after_save=None):
    """Édite une valeur de configuration."""
    print()
    print(f"  {c.KEY}Actuel:{c.RESET} {c.VALUE}{config[key]}{c.RESET}")
    new_val = input(c.prompt(f"  Nouveau {label} (ENTREE pour garder): ")).strip()

    if new_val:
        config[key] = new_val
        save_config(config)
        if after_save:
            after_save()
        print(c.success("Sauvegarde"))
    else:
        print(c.success("Valeur inchangee"))

    input(f"\n{c.DIM}  Appuyez sur Entree...{c.RESET}")


# ─── Options avancées ─────────────────────────────────────────

def advanced_menu(config):
    """Menu options avancées."""
    while True:
        clear_screen()

        urls_file = Path(config["urls_file"])
        has_urls = urls_file.exists() and urls_file.stat().st_size > 0

        print(c.box_header("OPTIONS AVANCEES"))
        print()

        if has_urls:
            print(c.title("DEVELOPPEMENT"))
            print(c.separator())
            print(c.menu_option("1", "Mode dev       - Depuis urls.txt, sans token"))
            print(c.menu_option("2", f"{c.WARNING}Force DL{c.RESET}       - Re-telecharger tous les medias"))
            print()

        print(c.title("MAINTENANCE"))
        print(c.separator())
        print(c.menu_option("3", "Supprimer logs - Nettoyer les fichiers log"))
        print(c.menu_option("4", "Ouvrir dossier - Explorer les telechargements"))
        print()
        print(c.menu_option("0", f"{c.DIM}Retour{c.RESET}"))
        print()

        choice = input(c.prompt("  Votre choix (0-4): ")).strip()

        if choice == "0":
            break
        elif choice == "1":
            if not has_urls:
                print(c.warning("Aucune URL disponible dans urls.txt"))
                input(f"\n{c.DIM}  Appuyez sur Entree...{c.RESET}")
            else:
                download_media(config, force=True, skip_token_check=True)
                input(f"\n{c.DIM}  Appuyez sur Entree...{c.RESET}")
        elif choice == "2":
            if not has_urls:
                print(c.warning("Aucune URL disponible dans urls.txt"))
                input(f"\n{c.DIM}  Appuyez sur Entree...{c.RESET}")
            else:
                download_media(config, force=True)
                input(f"\n{c.DIM}  Appuyez sur Entree...{c.RESET}")
        elif choice == "3":
            from core.config import cleanup_logs
            deleted = cleanup_logs(config)
            print(c.success(f"{deleted} fichier(s) log supprime(s)"))
            input(f"\n{c.DIM}  Appuyez sur Entree...{c.RESET}")
        elif choice == "4":
            download_dir = config["download_dir"]
            if sys.platform == "win32":
                os.startfile(download_dir)
            else:
                subprocess.run(["xdg-open", download_dir])
        else:
            print(c.error(f"Choix invalide : \"{choice}\""))
            input(f"\n{c.DIM}  Appuyez sur Entree...{c.RESET}")


# ─── Boucle principale ───────────────────────────────────────

def open_download_folder(config):
    """Ouvre le dossier de téléchargements."""
    download_dir = config["download_dir"]
    if sys.platform == "win32":
        os.startfile(download_dir)
    else:
        subprocess.run(["xdg-open", download_dir])


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
            export_bookmarks(config)
            input(f"\n{c.DIM}  Appuyez sur Entree...{c.RESET}")
        elif choice == "2":
            if not state["has_urls"]:
                print(c.warning("Aucune URL disponible"))
                print(f"  {c.DIM}Lancez d'abord l'export des bookmarks (option 1){c.RESET}")
                input(f"\n{c.DIM}  Appuyez sur Entree...{c.RESET}")
            else:
                download_media(config, force=False)
                input(f"\n{c.DIM}  Appuyez sur Entree...{c.RESET}")
        elif choice == "3":
            show_stats(config)
        elif choice == "4":
            if state["has_downloads"]:
                open_download_folder(config)
            else:
                print(c.warning("Aucun media telecharge"))
                input(f"\n{c.DIM}  Appuyez sur Entree...{c.RESET}")
        elif choice == "5":
            configure(config)
        elif choice == "9":
            advanced_menu(config)
        else:
            print(c.error(f"Choix invalide : \"{choice}\""))
            input(f"\n{c.DIM}  Appuyez sur Entree...{c.RESET}")


if __name__ == "__main__":
    main()
