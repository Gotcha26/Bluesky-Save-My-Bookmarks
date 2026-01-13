#!/usr/bin/env python3
"""
what.py - Version avec analyse préalable
"""
import os
import sys
import subprocess
import time
import threading
import json
from datetime import datetime
from pathlib import Path
from config import load_config
from database import Database
from post_analyzer import PostAnalyzer, PostType

class Spinner:
    def __init__(self, message="Traitement"):
        self.message = message
        self.running = False
        self.thread = None
    
    def _spin(self):
        chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        idx = 0
        while self.running:
            sys.stdout.write(f"\r{self.message} {chars[idx % len(chars)]}")
            sys.stdout.flush()
            time.sleep(0.1)
            idx += 1
        sys.stdout.write("\r" + " " * (len(self.message) + 3) + "\r")
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
    except:
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
    """Sauvegarde les infos de debug pour analyse"""
    debug_file = logs_dir / f"debug_{post_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(debug_file, "w", encoding="utf-8") as f:
        json.dump(debug_info, f, indent=2, ensure_ascii=False)
    return debug_file

def main():
    if len(sys.argv) < 4:
        print("Usage: python what.py <IMG_DIR> <VID_DIR> [--no-db] <URL1> [URL2] ...")
        sys.exit(1)
    
    start_time = time.time()
    
    IMG_DIR = sys.argv[1]
    VID_DIR = sys.argv[2]
    
    no_db_mode = "--no-db" in sys.argv
    if no_db_mode:
        sys.argv.remove("--no-db")
    
    urls = sys.argv[3:]
    
    config = load_config()
    from config import cleanup_old_logs
    cleanup_old_logs(config)
    
    db = None if no_db_mode else Database(config["db_file"])
    analyzer = PostAnalyzer()
    
    # Compteurs
    total_jobs = len(urls)
    success_count = 0
    img_count = 0
    vid_count = 0
    text_count = 0
    failed_urls = []
    deleted_urls = []
    repost_urls = []
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
        print("\n" + "="*80)
        print(f"🔹 Job {idx} / {total_jobs} : {post_id}")
        print(f"🔗 URL : {url}")
        print("="*80 + "\n")
        
        log(f"Job {idx}/{total_jobs}: {url}", to_console=False)
        
        # === ANALYSE PRÉALABLE ===
        spinner = Spinner("🔍 Analyse du post")
        spinner.start()
        post_type, data, debug_info = analyzer.analyze(url)
        spinner.stop()
        
        print(f"   📋 Type détecté : {post_type.value}")
        
        # Tracking DB
        if db:
            handle = data.get("handle")
            db.add_post(url, post_id, handle)
        
        has_success = False
        
        # === TRAITEMENT PAR TYPE ===
        
        # Erreur 500
        if post_type == PostType.ERROR_500:
            print("   ⚠️ Erreur serveur (500)")
            error_500_urls.append(url)
            log(f"   ERREUR 500: {url}", to_console=False)
            if db:
                db.update_last_check(url)
            continue
        
        # Post supprimé
        if post_type == PostType.ERROR_400:
            print("   [!] Post supprimé ou inaccessible (400)")
            deleted_urls.append(url)
            log(f"   POST SUPPRIMÉ: {url}", to_console=False)
            continue
        
        # Repost
        if post_type == PostType.REPOST:
            print("   [REPOST] Post cité détecté - non traité")
            repost_urls.append(url)
            log(f"   REPOST: {url}", to_console=False)
            continue
        
        # Images
        if post_type == PostType.IMAGES:
            print(f"   📸 {data['image_count']} image(s) détectée(s)")
            img_proc = subprocess.run(
                ["python", "bsky_img_downloader.py", IMG_DIR, url],
                capture_output=True,
                text=True
            )
            if img_proc.returncode == 0:
                has_success = True
                img_count += img_proc.stdout.count("[DL]")
            
            if img_proc.stdout:
                for line in img_proc.stdout.strip().split("\n"):
                    if line and not line.startswith("SCRIPT") and not line.startswith("DEBUG"):
                        print(f"   {line}")
        
        # Vidéo
        elif post_type == PostType.VIDEO:
            print("   🎬 Vidéo détectée")
            vid_proc = subprocess.run(
                ["python", "bsky_vid_downloader.py", VID_DIR, url],
                capture_output=True,
                text=True
            )
            if vid_proc.returncode == 0:
                has_success = True
                vid_count += vid_proc.stdout.count("[DL]")
            
            if vid_proc.stdout:
                for line in vid_proc.stdout.strip().split("\n"):
                    if line and not line.startswith("SCRIPT") and not line.startswith("DEBUG"):
                        print(f"   {line}")
        
        # Texte seul
        elif post_type == PostType.TEXT_ONLY:
            print("   📝 Texte seul détecté")
            text_proc = subprocess.run(
                ["python", "bsky_text_downloader.py", url],
                capture_output=True,
                text=True
            )
            if text_proc.returncode == 0:
                has_success = True
                text_count += text_proc.stdout.count("[TXT]")
            
            if text_proc.stdout:
                for line in text_proc.stdout.strip().split("\n"):
                    if line:
                        print(f"   {line}")
        
        # Cas inconnu - MODE DEBUG
        elif post_type == PostType.UNKNOWN:
            print("   ⚠️ Type de post non reconnu - MODE DEBUG activé")
            debug_file = save_debug_info(post_id, debug_info, logs_dir)
            print(f"   🐛 Debug sauvegardé : {debug_file.name}")
            print("\n   === INFORMATIONS DE DEBUG ===")
            print(f"   Embed type : {debug_info.get('embed_type', 'N/A')}")
            print(f"   Has embed  : {debug_info.get('has_embed', False)}")
            print(f"   Texte      : {data.get('text', '')[:100]}...")
            print("   =============================\n")
            
            unknown_urls.append(url)
            log(f"   TYPE INCONNU: {url} - Debug: {debug_file.name}", to_console=False)
            continue
        
        # Bilan
        if has_success:
            if db:
                db.update_last_check(url)
            success_count += 1
            log(f"   SUCCÈS: {url}", to_console=False)
        else:
            failed_urls.append(url)
            log(f"   ÉCHEC: {url}", to_console=False)
    
    if db:
        db.close()
    
    # Rapport final
    duration = time.time() - start_time
    total_size = get_folder_size(IMG_DIR) + get_folder_size(VID_DIR)
    
    print("\n" + "="*80)
    print("✅ TRAITEMENT TERMINÉ")
    print("="*80)
    print(f"Posts traités avec succès : {success_count}/{total_jobs}")
    print(f"Images téléchargées       : {img_count}")
    print(f"Vidéos téléchargées       : {vid_count}")
    print(f"Textes sauvegardés        : {text_count}")
    print(f"Reposts détectés          : {len(repost_urls)}")
    print(f"Posts supprimés (400)     : {len(deleted_urls)}")
    print(f"Erreurs serveur (500)     : {len(error_500_urls)}")
    print(f"Types inconnus            : {len(unknown_urls)}")
    print(f"Échecs                    : {len(failed_urls)}")
    print(f"Durée totale              : {format_duration(duration)}")
    print(f"Poids total du dossier    : {format_size(total_size)}")
    if no_db_mode:
        print("\n⚠️ Mode dev : Base de données non mise à jour")
    print("="*80)
    
    # Sauvegarde listes
    if deleted_urls:
        deleted_file = logs_dir / f"deleted_posts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(deleted_file, "w", encoding="utf-8") as f:
            f.write("\n".join(deleted_urls))
        print(f"\n⚠️ {len(deleted_urls)} posts supprimés → {deleted_file}")
    
    if repost_urls:
        repost_file = logs_dir / f"reposts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(repost_file, "w", encoding="utf-8") as f:
            f.write("\n".join(repost_urls))
        print(f"\n📌 {len(repost_urls)} reposts → {repost_file}")
    
    if error_500_urls:
        error_file = logs_dir / f"error_500_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(error_file, "w", encoding="utf-8") as f:
            f.write("\n".join(error_500_urls))
        print(f"\n⚠️ {len(error_500_urls)} erreurs 500 → {error_file}")
    
    if unknown_urls:
        unknown_file = logs_dir / f"unknown_types_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(unknown_file, "w", encoding="utf-8") as f:
            f.write("\n".join(unknown_urls))
        print(f"\n🐛 {len(unknown_urls)} types inconnus → {unknown_file}")
    
    if failed_urls:
        failed_file = logs_dir / f"failed_downloads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(failed_file, "w", encoding="utf-8") as f:
            f.write("\n".join(failed_urls))
        print(f"\n❌ {len(failed_urls)} échecs → {failed_file}")
    
    print(f"\n📋 Log détaillé : {log_file}")
    
    if success_count > 0:
        print()
        choice = input("📂 Ouvrir le dossier de téléchargements ? (O/n) : ").strip().lower()
        if not choice or choice == "o":
            download_dir = os.path.expandvars(r"%USERPROFILE%\Downloads\BSMB")
            if sys.platform == "win32":
                os.startfile(download_dir)
            else:
                subprocess.run(["xdg-open", download_dir])

if __name__ == "__main__":
    main()