#!/usr/bin/env python3
"""
Orchestrateur principal de téléchargement
Analyse, résout et télécharge les médias des posts Bluesky
Supporte l'exécution parallèle via ThreadPoolExecutor
"""
import os
import sys
import subprocess
import time
import threading
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Forcer l'encodage UTF-8 pour la console Windows (seulement en exécution directe)
if sys.platform == "win32" and __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from core.config import load_config, cleanup_old_logs
from core.database import Database
from core.colors import c
from api.post_analyzer import PostAnalyzer, PostType
from api.repost_resolver import RepostResolver

# Lock global pour l'affichage console (évite les lignes entrelacées)
_print_lock = threading.Lock()


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
    Returns: (has_success, img_count, vid_count, text_count, status, output_lines)

    output_lines contient les lignes à afficher (buffered pour le mode parallèle).
    """
    output = []

    def buf_print(msg):
        output.append(msg)

    post_id = url.rstrip("/").split("/")[-1]

    # === ANALYSE PRÉALABLE ===
    post_type, data, debug_info = analyzer.analyze(url)
    buf_print(f"  {c.KEY}Type détecté :{c.RESET} {c.VALUE}{post_type.value}{c.RESET}")

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
        buf_print(c.warning("Erreur serveur (500)"))
        log_func(f"   ERREUR 500: {url}", to_console=False)
        if db:
            db.update_last_check(url)
            db.mark_post_status(url, 'error_500')
        return False, 0, 0, 0, 'error_500', output

    # Post supprimé
    if post_type == PostType.ERROR_400:
        buf_print(c.error("Post supprimé ou inaccessible (400)"))
        log_func(f"   POST SUPPRIMÉ: {url}", to_console=False)
        if db:
            db.mark_post_status(url, 'deleted')
        return False, 0, 0, 0, 'error_400', output

    # Repost - RÉSOLUTION
    if post_type == PostType.REPOST:
        buf_print(c.info("Repost détecté, résolution du post d'origine..."))
        original_url, original_handle, original_post_id = resolver.resolve(url)

        if original_url:
            buf_print(f"  {c.OK}>{c.RESET} Post original : {c.VALUE}{original_handle}/post/{original_post_id}{c.RESET}")
            buf_print(f"  {c.DIM}{original_url}{c.RESET}")

            # Traiter récursivement le post original
            return process_post(original_url, IMG_DIR, VID_DIR, db, analyzer, resolver, logs_dir, log_func)
        else:
            buf_print(c.warning("Impossible de résoudre le repost"))
            log_func(f"   REPOST NON RÉSOLU: {url}", to_console=False)
            return False, 0, 0, 0, 'repost', output

    # Images
    if post_type == PostType.IMAGES:
        buf_print(c.info(f"{data['image_count']} image(s) détectée(s)"))

        img_proc = subprocess.run(
            ["python", "downloaders/images.py", IMG_DIR, url],
            capture_output=True,
            text=True
        )

        if img_proc.returncode == 0:
            has_success = True
            img_count = img_proc.stdout.count("[DL]")

        if img_proc.stdout:
            for line in img_proc.stdout.strip().split("\n"):
                if line and not line.startswith("SCRIPT") and not line.startswith("DEBUG"):
                    buf_print(f"    {line}")

        if db and img_count > 0:
            for i in range(img_count):
                db.add_media(url, 'image', f'image_{i}')

    # Vidéo
    elif post_type == PostType.VIDEO:
        buf_print(c.info("Vidéo détectée"))

        vid_proc = subprocess.run(
            ["python", "downloaders/videos.py", VID_DIR, url],
            capture_output=True,
            text=True
        )

        if vid_proc.returncode == 0:
            has_success = True
            vid_count = vid_proc.stdout.count("[DL]")

        if vid_proc.stdout:
            for line in vid_proc.stdout.strip().split("\n"):
                if line and not line.startswith("SCRIPT") and not line.startswith("DEBUG"):
                    buf_print(f"    {line}")

        if db and vid_count > 0:
            for i in range(vid_count):
                db.add_media(url, 'video', f'video_{i}')

    # Texte seul
    elif post_type == PostType.TEXT_ONLY:
        buf_print(c.info("Texte seul détecté"))

        text_proc = subprocess.run(
            ["python", "downloaders/text.py", url],
            capture_output=True,
            text=True
        )

        if text_proc.returncode == 0:
            has_success = True
            text_count = text_proc.stdout.count("[TXT]")

        if text_proc.stdout:
            for line in text_proc.stdout.strip().split("\n"):
                if line:
                    buf_print(f"    {line}")

    # Cas inconnu - MODE DEBUG
    elif post_type == PostType.UNKNOWN:
        buf_print(c.warning("Type de post non reconnu"))
        debug_file = save_debug_info(post_id, debug_info, logs_dir)
        buf_print(f"  {c.DIM}Debug sauvegardé : {debug_file.name}{c.RESET}")
        buf_print(c.config_line("Embed type", debug_info.get('embed_type', 'N/A')))
        buf_print(c.config_line("Has embed", str(debug_info.get('has_embed', False))))
        buf_print(c.config_line("Texte", data.get('text', '')[:80] + "..."))

        log_func(f"   TYPE INCONNU: {url} - Debug: {debug_file.name}", to_console=False)
        return False, 0, 0, 0, 'unknown', output

    # Bilan
    if has_success:
        if db:
            db.update_last_check(url)
        log_func(f"   SUCCÈS: {url}", to_console=False)
        return True, img_count, vid_count, text_count, 'success', output
    else:
        log_func(f"   ÉCHEC: {url}", to_console=False)
        return False, 0, 0, 0, 'failed', output


def _format_job_summary(idx, total, url, status, img_count, vid_count, text_count):
    """Formate le résumé compact d'un job sur une ligne."""
    post_id = url.rstrip("/").split("/")[-1]
    parts = url.split("/")
    handle = parts[4] if len(parts) > 4 else "?"

    counter = f"[{idx}/{total}]"

    if status == 'success':
        details = []
        if img_count:
            details.append(f"{img_count} image{'s' if img_count > 1 else ''}")
        if vid_count:
            details.append(f"{vid_count} vidéo{'s' if vid_count > 1 else ''}")
        if text_count:
            details.append(f"{text_count} texte{'s' if text_count > 1 else ''}")
        detail_str = ", ".join(details) if details else "OK"
        return f"  {c.DIM}{counter}{c.RESET} {c.GREEN}OK{c.RESET} {c.VALUE}{handle}/{post_id}{c.RESET} {c.DIM}{detail_str}{c.RESET}"
    elif status == 'error_400':
        return f"  {c.DIM}{counter}{c.RESET} {c.RED}--{c.RESET} {c.DIM}post supprimé (400){c.RESET}"
    elif status == 'error_500':
        return f"  {c.DIM}{counter}{c.RESET} {c.RED}--{c.RESET} {c.DIM}erreur serveur (500){c.RESET}"
    elif status == 'repost':
        return f"  {c.DIM}{counter}{c.RESET} {c.YELLOW}~~{c.RESET} {c.DIM}repost non résolu{c.RESET}"
    elif status == 'unknown':
        return f"  {c.DIM}{counter}{c.RESET} {c.YELLOW}??{c.RESET} {c.DIM}type inconnu{c.RESET}"
    else:
        return f"  {c.DIM}{counter}{c.RESET} {c.RED}!!{c.RESET} {c.DIM}échec{c.RESET}"


def _print_progress_bar(completed, total, img_total, vid_total, text_total):
    """Affiche une barre de progression mise à jour."""
    bar_width = 30
    filled = int(bar_width * completed / total) if total > 0 else 0
    bar = "█" * filled + "░" * (bar_width - filled)
    pct = int(100 * completed / total) if total > 0 else 0

    details = []
    if img_total:
        details.append(f"{img_total} img")
    if vid_total:
        details.append(f"{vid_total} vid")
    if text_total:
        details.append(f"{text_total} txt")
    detail_str = f" ({', '.join(details)})" if details else ""

    line = f"  {c.DIM}Progression :{c.RESET} [{c.CYAN}{bar}{c.RESET}] {completed}/{total} {pct}%{detail_str}"
    sys.stdout.write(f"\r{line}  ")
    sys.stdout.flush()


def print_report(stats, duration, total_size, no_db_mode, logs_dir, log_file, max_workers):
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
    print(c.config_line("Textes sauvegardés", str(stats['texts']), 28))
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
    print(c.config_line("Workers parallèles", str(max_workers), 28))
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

    max_workers = max(1, int(config.get("max_workers", 4)))
    db = None if no_db_mode else Database(config["db_file"])
    analyzer = PostAnalyzer()
    resolver = RepostResolver()

    # Compteurs thread-safe
    total_jobs = len(urls)
    stats_lock = threading.Lock()
    success_count = 0
    img_count = 0
    vid_count = 0
    text_count = 0
    completed_count = 0
    failed_urls = []
    deleted_urls = []
    repost_unresolved_urls = []
    error_500_urls = []
    unknown_urls = []

    # Logs
    logs_dir = Path(config["logs_dir"])
    logs_dir.mkdir(exist_ok=True)
    log_file = logs_dir / f"download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_lock = threading.Lock()

    def log(msg, to_console=True):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {msg}\n"
        with log_lock:
            with open(str(log_file), "a", encoding="utf-8") as f:
                f.write(log_line)
        if to_console:
            with _print_lock:
                print(msg)

    log(f"=== Début du téléchargement : {total_jobs} posts à traiter ({max_workers} workers) ===")
    if no_db_mode:
        log("MODE DEV: Base de données désactivée", to_console=False)

    # En-tête
    print()
    print(f"  {c.HEADER}{'─' * 78}{c.RESET}")
    print(f"  {c.BOLD}{total_jobs} posts à traiter{c.RESET} {c.DIM}({max_workers} workers parallèles){c.RESET}")
    print(f"  {c.HEADER}{'─' * 78}{c.RESET}")
    print()

    def worker(idx, url):
        """Worker qui traite un post et retourne le résultat."""
        log(f"Job {idx}/{total_jobs}: {url}", to_console=False)
        has_success, imgs, vids, texts, status, output_lines = process_post(
            url, IMG_DIR, VID_DIR, db, analyzer, resolver, logs_dir, log
        )
        return idx, url, has_success, imgs, vids, texts, status, output_lines

    # === EXÉCUTION PARALLÈLE ===
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(worker, idx, url): (idx, url)
            for idx, url in enumerate(urls, start=1)
        }

        for future in as_completed(futures):
            idx, url, has_success, imgs, vids, texts, status, output_lines = future.result()

            with stats_lock:
                completed_count += 1
                if has_success:
                    success_count += 1
                    img_count += imgs
                    vid_count += vids
                    text_count += texts

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

                current_completed = completed_count
                current_imgs = img_count
                current_vids = vid_count
                current_texts = text_count

            # Affichage thread-safe
            with _print_lock:
                summary = _format_job_summary(idx, total_jobs, url, status, imgs, vids, texts)
                print(summary)
                _print_progress_bar(current_completed, total_jobs, current_imgs, current_vids, current_texts)

    # Effacer la barre de progression
    sys.stdout.write("\r" + " " * 100 + "\r")
    sys.stdout.flush()

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

    print_report(report_stats, duration, total_size, no_db_mode, logs_dir, log_file, max_workers)

    if success_count > 0:
        print()
        confirm = input(c.prompt("  Ouvrir le dossier de téléchargements ? [O/n]: ")).strip().lower()
        if not confirm or confirm in ("o", "oui", "y", "yes"):
            download_dir = config.get("download_dir", os.path.expandvars(r"%USERPROFILE%\Downloads\BSMB"))
            if sys.platform == "win32":
                os.startfile(download_dir)
            else:
                subprocess.run(["xdg-open", download_dir])


if __name__ == "__main__":
    main()
