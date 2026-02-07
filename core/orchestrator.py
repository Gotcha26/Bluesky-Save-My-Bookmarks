#!/usr/bin/env python3
"""
Orchestrateur principal de téléchargement
Analyse, résout et télécharge les médias des posts Bluesky
"""
import os
import sys
import subprocess
import time
import threading
import json
from datetime import datetime
from pathlib import Path

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Forcer l'encodage UTF-8 pour la console Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from core.config import load_config, cleanup_old_logs
from core.database import Database
from core.colors import c
from api.post_analyzer import PostAnalyzer, PostType
from api.repost_resolver import RepostResolver


class Spinner:
    def __init__(self, message="Traitement"):
        self.message = message
        self.running = False
        self.thread = None

    def _spin(self):
        chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        idx = 0
        while self.running:
            sys.stdout.write(f"\r  {c.DIM}{self.message} {chars[idx % len(chars)]}{c.RESET}")
            sys.stdout.flush()
            time.sleep(0.1)
            idx += 1
        sys.stdout.write("\r" + " " * (len(self.message) + 5) + "\r")
        sys.stdout.flush()

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()


def get_folder_size(path):
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
    for unit in ['o', 'Ko', 'Mo', 'Go']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} To"


def format_duration(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


def save_debug_info(post_id, debug_info, logs_dir):
    """Sauvegarde les infos de debug pour analyse."""
    debug_file = logs_dir / f"debug_{post_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(debug_file, "w", encoding="utf-8") as f:
        json.dump(debug_info, f, indent=2, ensure_ascii=False)
    return debug_file


def process_post(url, IMG_DIR, VID_DIR, db, analyzer, resolver, logs_dir, log_func):
    """
    Traite un post unique et retourne les stats.
    Returns: (has_success, img_count, vid_count, text_count, status)
    """
    post_id = url.rstrip("/").split("/")[-1]

    # === ANALYSE PRÉALABLE ===
    spinner = Spinner("Analyse du post")
    spinner.start()
    post_type, data, debug_info = analyzer.analyze(url)
    spinner.stop()

    print(f"  {c.KEY}Type détecté :{c.RESET} {c.VALUE}{post_type.value}{c.RESET}")

    # Tracking DB
    if db:
        handle = data.get("handle")
        db.add_post(url, post_id, handle)

    has_success = False
    img_count = 0
    vid_count = 0
    text_count = 0

    # === TRAITEMENT PAR TYPE ===

    # Erreur 500
    if post_type == PostType.ERROR_500:
        print(c.warning("Erreur serveur (500)"))
        log_func(f"   ERREUR 500: {url}", to_console=False)
        if db:
            db.update_last_check(url)
        return False, 0, 0, 0, 'error_500'

    # Post supprimé
    if post_type == PostType.ERROR_400:
        print(c.error("Post supprimé ou inaccessible (400)"))
        log_func(f"   POST SUPPRIMÉ: {url}", to_console=False)
        return False, 0, 0, 0, 'error_400'

    # Repost - RÉSOLUTION
    if post_type == PostType.REPOST:
        print(c.info("Repost détecté, résolution du post d'origine..."))
        spinner = Spinner("Résolution du repost")
        spinner.start()
        original_url, original_handle, original_post_id = resolver.resolve(url)
        spinner.stop()

        if original_url:
            print(f"  {c.OK}>{c.RESET} Post original : {c.VALUE}{original_handle}/post/{original_post_id}{c.RESET}")
            print(f"  {c.DIM}{original_url}{c.RESET}")
            print()

            # Traiter récursivement le post original
            return process_post(original_url, IMG_DIR, VID_DIR, db, analyzer, resolver, logs_dir, log_func)
        else:
            print(c.warning("Impossible de résoudre le repost"))
            log_func(f"   REPOST NON RÉSOLU: {url}", to_console=False)
            return False, 0, 0, 0, 'repost'

    # Images
    if post_type == PostType.IMAGES:
        print(c.info(f"{data['image_count']} image(s) détectée(s)"))
        spinner = Spinner("Téléchargement des images")
        spinner.start()

        img_proc = subprocess.run(
            ["python", "downloaders/images.py", IMG_DIR, url],
            capture_output=True,
            text=True
        )

        spinner.stop()

        if img_proc.returncode == 0:
            has_success = True
            img_count = img_proc.stdout.count("[DL]")

        if img_proc.stdout:
            for line in img_proc.stdout.strip().split("\n"):
                if line and not line.startswith("SCRIPT") and not line.startswith("DEBUG"):
                    print(f"    {line}")

        if db and img_count > 0:
            for i in range(img_count):
                db.add_media(url, 'image', f'image_{i}')

    # Vidéo
    elif post_type == PostType.VIDEO:
        print(c.info("Vidéo détectée"))
        spinner = Spinner("Téléchargement de la vidéo")
        spinner.start()

        vid_proc = subprocess.run(
            ["python", "downloaders/videos.py", VID_DIR, url],
            capture_output=True,
            text=True
        )

        spinner.stop()

        if vid_proc.returncode == 0:
            has_success = True
            vid_count = vid_proc.stdout.count("[DL]")

        if vid_proc.stdout:
            for line in vid_proc.stdout.strip().split("\n"):
                if line and not line.startswith("SCRIPT") and not line.startswith("DEBUG"):
                    print(f"    {line}")

        if db and vid_count > 0:
            for i in range(vid_count):
                db.add_media(url, 'video', f'video_{i}')

    # Texte seul
    elif post_type == PostType.TEXT_ONLY:
        print(c.info("Texte seul détecté"))
        spinner = Spinner("Sauvegarde du texte")
        spinner.start()

        text_proc = subprocess.run(
            ["python", "downloaders/text.py", url],
            capture_output=True,
            text=True
        )

        spinner.stop()

        if text_proc.returncode == 0:
            has_success = True
            text_count = text_proc.stdout.count("[TXT]")

        if text_proc.stdout:
            for line in text_proc.stdout.strip().split("\n"):
                if line:
                    print(f"    {line}")

    # Cas inconnu - MODE DEBUG
    elif post_type == PostType.UNKNOWN:
        print(c.warning("Type de post non reconnu"))
        debug_file = save_debug_info(post_id, debug_info, logs_dir)
        print(f"  {c.DIM}Debug sauvegardé : {debug_file.name}{c.RESET}")
        print()
        print(c.config_line("Embed type", debug_info.get('embed_type', 'N/A')))
        print(c.config_line("Has embed", str(debug_info.get('has_embed', False))))
        print(c.config_line("Texte", data.get('text', '')[:80] + "..."))
        print()

        log_func(f"   TYPE INCONNU: {url} - Debug: {debug_file.name}", to_console=False)
        return False, 0, 0, 0, 'unknown'

    # Bilan
    if has_success:
        if db:
            db.update_last_check(url)
        log_func(f"   SUCCÈS: {url}", to_console=False)
        return True, img_count, vid_count, text_count, 'success'
    else:
        log_func(f"   ÉCHEC: {url}", to_console=False)
        return False, 0, 0, 0, 'failed'


def print_report(stats, duration, total_size, no_db_mode, logs_dir, log_file):
    """Affiche le rapport final structuré."""
    border = "=" * 80
    print(f"\n  {c.HEADER}{border}{c.RESET}")
    print(f"  {c.HEADER}{'RAPPORT DE TÉLÉCHARGEMENT':^80}{c.RESET}")
    print(f"  {c.HEADER}{border}{c.RESET}")
    print()

    # Résultats
    print(c.title("  RÉSULTATS"))
    print(c.separator(width=78))
    print(c.config_line("Posts traités", f"{stats['success']}/{stats['total']}", 28))
    print(c.config_line("Images téléchargées", str(stats['images']), 28))
    print(c.config_line("Vidéos téléchargées", str(stats['videos']), 28))
    print(c.config_line("Textes sauvegardes", str(stats['texts']), 28))
    print()

    # Problèmes (seulement si présents)
    has_problems = any([
        stats['error_500'], stats['error_400'],
        stats['reposts'], stats['unknown'], stats['failed']
    ])

    if has_problems:
        print(c.title("  PROBLÈMES"))
        print(c.separator(width=78))
        if stats['error_400']:
            print(c.config_line("Posts supprimés (400)", str(len(stats['error_400'])), 28))
        if stats['error_500']:
            print(c.config_line("Erreurs serveur (500)", str(len(stats['error_500'])), 28))
        if stats['reposts']:
            print(c.config_line("Reposts non résolus", str(len(stats['reposts'])), 28))
        if stats['unknown']:
            print(c.config_line("Types inconnus", str(len(stats['unknown'])), 28))
        if stats['failed']:
            print(c.config_line("Échecs", str(len(stats['failed'])), 28))
        print()

    # Métriques
    print(c.title("  MÉTRIQUES"))
    print(c.separator(width=78))
    print(c.config_line("Durée totale", format_duration(duration), 28))
    print(c.config_line("Poids total du dossier", format_size(total_size), 28))

    if no_db_mode:
        print()
        print(c.warning("Mode dev : Base de données non mise à jour"))

    print()
    print(f"  {c.HEADER}{border}{c.RESET}")

    # Fichiers de log générés
    _save_and_report_logs(stats, logs_dir, log_file)


def _save_and_report_logs(stats, logs_dir, log_file):
    """Sauvegarde les fichiers de problèmes et affiche les liens."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    generated = []

    entries = [
        ("error_400", "deleted_posts", "posts supprimés"),
        ("reposts", "reposts_unresolved", "reposts non résolus"),
        ("error_500", "error_500", "erreurs 500"),
        ("unknown", "unknown_types", "types inconnus"),
        ("failed", "failed_downloads", "échecs"),
    ]

    for key, prefix, label in entries:
        urls = stats.get(key, [])
        if urls:
            filepath = logs_dir / f"{prefix}_{timestamp}.txt"
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(urls))
            generated.append((filepath.name, f"{len(urls)} {label}"))

    if generated:
        print()
        print(c.title("  FICHIERS GÉNÉRÉS"))
        print(c.separator(width=78))
        for name, detail in generated:
            print(f"  {c.YELLOW}>{c.RESET} {c.VALUE}{name}{c.RESET}  ({detail})")

    print(f"\n  {c.DIM}Log détaillé : {log_file}{c.RESET}")


def main():
    if len(sys.argv) < 4:
        print("Usage: python orchestrator.py <IMG_DIR> <VID_DIR> [--no-db] <URL1> [URL2] ...")
        sys.exit(1)

    start_time = time.time()

    IMG_DIR = sys.argv[1]
    VID_DIR = sys.argv[2]

    no_db_mode = "--no-db" in sys.argv
    if no_db_mode:
        sys.argv.remove("--no-db")

    urls = sys.argv[3:]

    config = load_config()
    cleanup_old_logs(config)

    db = None if no_db_mode else Database(config["db_file"])
    analyzer = PostAnalyzer()
    resolver = RepostResolver()

    # Compteurs
    total_jobs = len(urls)
    success_count = 0
    img_count = 0
    vid_count = 0
    text_count = 0
    failed_urls = []
    deleted_urls = []
    repost_unresolved_urls = []
    error_500_urls = []
    unknown_urls = []

    # Logs
    logs_dir = Path(config["logs_dir"])
    logs_dir.mkdir(exist_ok=True)
    log_file = logs_dir / f"download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    def log(msg, to_console=True):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {msg}\n"
        with open(str(log_file), "a", encoding="utf-8") as f:
            f.write(log_line)
        if to_console:
            print(msg)

    log(f"=== Début du téléchargement : {total_jobs} posts à traiter ===")
    if no_db_mode:
        log("MODE DEV: Base de données désactivée", to_console=False)

    for idx, url in enumerate(urls, start=1):
        post_id = url.rstrip("/").split("/")[-1]

        # En-tête de job
        print()
        print(f"  {c.HEADER}{'─' * 78}{c.RESET}")
        print(f"  {c.BOLD}Job {idx}/{total_jobs}{c.RESET} : {c.VALUE}{post_id}{c.RESET}")
        print(f"  {c.DIM}{url}{c.RESET}")
        print(f"  {c.HEADER}{'─' * 78}{c.RESET}")
        print()

        log(f"Job {idx}/{total_jobs}: {url}", to_console=False)

        # Traiter le post
        has_success, imgs, vids, texts, status = process_post(
            url, IMG_DIR, VID_DIR, db, analyzer, resolver, logs_dir, log
        )

        # Mise à jour compteurs
        if has_success:
            success_count += 1
            img_count += imgs
            vid_count += vids
            text_count += texts

        # Catégorisation
        if status == 'error_500':
            error_500_urls.append(url)
        elif status == 'error_400':
            deleted_urls.append(url)
        elif status == 'repost':
            repost_unresolved_urls.append(url)
        elif status == 'unknown':
            unknown_urls.append(url)
        elif status == 'failed':
            failed_urls.append(url)

    if db:
        db.close()

    # Rapport final
    duration = time.time() - start_time
    total_size = get_folder_size(IMG_DIR) + get_folder_size(VID_DIR)

    report_stats = {
        'total': total_jobs,
        'success': success_count,
        'images': img_count,
        'videos': vid_count,
        'texts': text_count,
        'error_500': error_500_urls,
        'error_400': deleted_urls,
        'reposts': repost_unresolved_urls,
        'unknown': unknown_urls,
        'failed': failed_urls,
    }

    print_report(report_stats, duration, total_size, no_db_mode, logs_dir, log_file)

    if success_count > 0:
        print()
        confirm = input(c.prompt("  Ouvrir le dossier de telechargements ? [O/n]: ")).strip().lower()
        if not confirm or confirm in ("o", "oui", "y", "yes"):
            download_dir = config.get("download_dir", os.path.expandvars(r"%USERPROFILE%\Downloads\BSMB"))
            if sys.platform == "win32":
                os.startfile(download_dir)
            else:
                subprocess.run(["xdg-open", download_dir])


if __name__ == "__main__":
    main()
