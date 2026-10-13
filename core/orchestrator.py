#!/usr/bin/env python3
"""
Orchestrateur principal de téléchargement
Analyse, résout et télécharge les médias des posts Bluesky.

Point d'entrée : run(urls, config, …), appelé directement par bsmb.py. Les
downloaders sont des fonctions appelées dans les threads d'un
ThreadPoolExecutor ; aucun sous-processus Python n'est lancé.

Usage manuel : python core/orchestrator.py <IMG_DIR> <VID_DIR> <TEXT_DIR> [--no-db] <URL1> [URL2] ...
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

if __package__ in (None, ""):
    # Exécution directe (python core/orchestrator.py) : rendre la racine importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import (  # noqa: E402
    DEFAULT_CONFIG, cleanup_old_logs, get_media_dirs, load_config, resolve_path,
)
from core.database import Database  # noqa: E402
from core.colors import c  # noqa: E402
from api.post_analyzer import PostAnalyzer, PostType  # noqa: E402
from api.repost_resolver import RepostResolver  # noqa: E402
from downloaders import DownloadError, lignes_console  # noqa: E402
from downloaders.images import download_images  # noqa: E402
from downloaders.videos import download_video  # noqa: E402
from downloaders.text import save_text  # noqa: E402

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


def _telecharger(downloader, url, dest_dir, config, buf_print):
    """
    Appelle un downloader et affiche ses résultats.
    Returns: la liste de DownloadResult (vide en cas d'erreur ou sans média).
    """
    try:
        results = downloader(url, dest_dir, config)
    except DownloadError as e:
        buf_print(f"       [ERR] {e}")
        return []
    if not results:
        buf_print("       [!] Aucun média trouvé")
    for ligne in lignes_console(results):
        buf_print(f"    {ligne}")
    return results


def process_post(url, IMG_DIR, VID_DIR, TEXT_DIR, db, analyzer, resolver, logs_dir, log_func, config=None):
    """
    Traite un post unique et retourne les stats.
    Returns: (has_success, img_count, vid_count, text_count, status, output_lines)

    output_lines contient les lignes à afficher (buffered pour le mode parallèle).
    config : transmise aux downloaders (DEFAULT_CONFIG si None).
    """
    config = DEFAULT_CONFIG if config is None else config
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
        db.add_post(url, post_id, handle, at_uri=data.get("at_uri"), did=data.get("did"))

    results = []
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
            resultat = process_post(original_url, IMG_DIR, VID_DIR, TEXT_DIR, db, analyzer, resolver,
                                    logs_dir, log_func, config)

            # Le citant n'est « ok » que si l'original a réussi ; sinon il garde un
            # statut retentable (l'original n'est pas dans les bookmarks, seul le
            # citant peut être relancé)
            if db:
                statut_original = resultat[4]
                if resultat[0]:
                    statut = 'ok'
                elif statut_original == 'error_400':
                    statut = 'deleted'
                elif statut_original in ('error_500', 'unknown', 'repost'):
                    statut = statut_original
                else:
                    statut = 'unknown'
                db.mark_post_status(url, statut)
            return resultat
        else:
            buf_print(c.warning("Impossible de résoudre le repost"))
            log_func(f"   REPOST NON RÉSOLU: {url}", to_console=False)
            if db:
                db.mark_post_status(url, 'repost')
            return False, 0, 0, 0, 'repost', output

    # Images
    if post_type == PostType.IMAGES:
        buf_print(c.info(f"{data['image_count']} image(s) détectée(s)"))
        results = _telecharger(download_images, url, IMG_DIR, config, buf_print)
        img_count = len(results)

    # Vidéo
    elif post_type == PostType.VIDEO:
        buf_print(c.info("Vidéo détectée"))
        results = _telecharger(download_video, url, VID_DIR, config, buf_print)
        vid_count = len(results)

    # Texte seul
    elif post_type == PostType.TEXT_ONLY:
        buf_print(c.info("Texte seul détecté"))
        results = _telecharger(save_text, url, TEXT_DIR, config, buf_print)
        text_count = len(results)

    # Cas inconnu - MODE DEBUG
    elif post_type == PostType.UNKNOWN:
        buf_print(c.warning("Type de post non reconnu"))
        debug_file = save_debug_info(post_id, debug_info, logs_dir)
        buf_print(f"  {c.DIM}Debug sauvegardé : {debug_file.name}{c.RESET}")
        buf_print(c.config_line("Embed type", debug_info.get('embed_type', 'N/A')))
        buf_print(c.config_line("Has embed", str(debug_info.get('has_embed', False))))
        buf_print(c.config_line("Texte", data.get('text', '')[:80] + "..."))

        log_func(f"   TYPE INCONNU: {url} - Debug: {debug_file.name}", to_console=False)
        if db:
            db.mark_post_status(url, 'unknown')
        return False, 0, 0, 0, 'unknown', output

    # Bilan
    if results:
        if db:
            for r in results:
                db.add_media(url, r.media_type, r.filename, cid=r.cid)
            db.update_last_check(url)
            # Un post retenté avec succès ne doit plus rester en erreur
            db.mark_post_status(url, 'ok')
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


def print_report(stats, duration, total_size, no_db_mode, log_file, max_workers, generated_files=()):
    """Affiche le rapport final structuré (generated_files : sortie de _save_problem_logs)."""
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
    if generated_files:
        print()
        print(c.title("  FICHIERS GÉNÉRÉS"))
        print(c.separator(width=78))
        for name, detail in generated_files:
            print(f"  {c.YELLOW}>{c.RESET} {c.VALUE}{name}{c.RESET}  ({detail})")

    print(f"\n  {c.DIM}Log détaillé : {log_file}{c.RESET}")


def _save_problem_logs(stats, logs_dir):
    """Écrit un fichier par catégorie de problème ; renvoie [(nom, détail), …]."""
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

    return generated


def run(urls, config, no_db=False, on_progress=None, quiet=False) -> dict:
    """
    Télécharge les médias des posts `urls` dans les sous-dossiers de config["download_dir"].

    Args:
        urls: URLs de posts bsky.app
        config: configuration chargée (load_config())
        no_db: ne pas lire ni écrire la base (mode dev)
        on_progress: callback(termines, total) appelé après chaque post
        quiet: aucune sortie console (ni progression ni rapport)

    Returns:
        dict: {"total", "success", "images", "videos", "texts",
               "error_500", "error_400", "reposts", "unknown", "failed"}
        (les cinq dernières clés sont des listes d'URLs)
    """
    return _run(urls, config, media_dirs=get_media_dirs(config), no_db=no_db,
                on_progress=on_progress, quiet=quiet)


def _run(urls, config, media_dirs, no_db=False, on_progress=None, quiet=False):
    """run() avec des dossiers médias explicites (utilisé par la CLI)."""
    start_time = time.time()
    IMG_DIR = media_dirs["img_dir"]
    VID_DIR = media_dirs["vid_dir"]
    TEXT_DIR = media_dirs["text_dir"]

    cleanup_old_logs(config)

    max_workers = max(1, int(config.get("max_workers", 4)))
    analyzer = PostAnalyzer()
    resolver = RepostResolver()

    # Compteurs (mis à jour dans le thread principal, au fil de as_completed)
    total_jobs = len(urls)
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
    logs_dir = resolve_path(config, "logs_dir")
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_lock = threading.Lock()

    def log(msg, to_console=True):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {msg}\n"
        with log_lock:
            with open(str(log_file), "a", encoding="utf-8") as f:
                f.write(log_line)
        if to_console and not quiet:
            with _print_lock:
                print(msg)

    log(f"=== Début du téléchargement : {total_jobs} posts à traiter ({max_workers} workers) ===")
    if no_db:
        log("MODE DEV: Base de données désactivée", to_console=False)

    # En-tête
    if not quiet:
        print()
        print(f"  {c.HEADER}{'─' * 78}{c.RESET}")
        print(f"  {c.BOLD}{total_jobs} posts à traiter{c.RESET} {c.DIM}({max_workers} workers parallèles){c.RESET}")
        print(f"  {c.HEADER}{'─' * 78}{c.RESET}")
        print()

    db = None if no_db else Database(resolve_path(config, "db_file"))

    def worker(idx, url):
        """Worker qui traite un post et retourne le résultat."""
        log(f"Job {idx}/{total_jobs}: {url}", to_console=False)
        has_success, imgs, vids, texts, status, output_lines = process_post(
            url, IMG_DIR, VID_DIR, TEXT_DIR, db, analyzer, resolver, logs_dir, log, config
        )
        return idx, url, has_success, imgs, vids, texts, status, output_lines

    # === EXÉCUTION PARALLÈLE ===
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(worker, idx, url): (idx, url)
                for idx, url in enumerate(urls, start=1)
            }

            for future in as_completed(futures):
                idx, url, has_success, imgs, vids, texts, status, output_lines = future.result()

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

                if not quiet:
                    with _print_lock:
                        summary = _format_job_summary(idx, total_jobs, url, status, imgs, vids, texts)
                        print(summary)
                        _print_progress_bar(completed_count, total_jobs, img_count, vid_count, text_count)
                if on_progress:
                    on_progress(completed_count, total_jobs)
    finally:
        if db:
            db.close()

    if not quiet:
        # Effacer la barre de progression
        sys.stdout.write("\r" + " " * 100 + "\r")
        sys.stdout.flush()

    stats = {
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

    generated = _save_problem_logs(stats, logs_dir)

    if not quiet:
        duration = time.time() - start_time
        total_size = get_folder_size(IMG_DIR) + get_folder_size(VID_DIR)
        print_report(stats, duration, total_size, no_db, log_file, max_workers, generated)

    return stats


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    no_db_mode = "--no-db" in argv
    if no_db_mode:
        argv.remove("--no-db")

    if len(argv) < 4:
        print("Usage: python orchestrator.py <IMG_DIR> <VID_DIR> <TEXT_DIR> [--no-db] <URL1> [URL2] ...")
        sys.exit(1)

    media_dirs = {"img_dir": argv[0], "vid_dir": argv[1], "text_dir": argv[2]}
    config = load_config()
    stats = _run(argv[3:], config, media_dirs=media_dirs, no_db=no_db_mode)

    if stats["success"] > 0:
        print()
        confirm = input(c.prompt("  Ouvrir le dossier de téléchargements ? [O/n]: ")).strip().lower()
        if not confirm or confirm in ("o", "oui", "y", "yes"):
            download_dir = config["download_dir"]
            if sys.platform == "win32":
                os.startfile(download_dir)
            else:
                subprocess.run(["xdg-open", download_dir])


if __name__ == "__main__":
    # Forcer l'encodage UTF-8 pour la console Windows (exécution directe uniquement)
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    main()
