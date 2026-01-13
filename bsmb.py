#!/usr/bin/env python3
"""
BSMB - Bsky Save My Bookmarks
Interface unifiée pour exporter et télécharger vos bookmarks Bluesky
"""
import sys
import os
import subprocess
from pathlib import Path
from config import load_config, save_config, ensure_dirs
from database import Database

def clear_screen():
    subprocess.run("cls" if sys.platform == "win32" else "clear", shell=True)

def show_menu():
    config = load_config()
    db = Database(config["db_file"])
    stats = db.get_stats()
    db.close()
    
    urls_file = Path(config["urls_file"])
    has_urls = urls_file.exists() and urls_file.stat().st_size > 0
    has_downloads = stats["images"] > 0 or stats["videos"] > 0
    
    dest_path = os.path.expandvars(config["img_dir"])
    dest_base = os.path.dirname(dest_path)
    
    print("\n" + "="*60)
    print("🔖 BSMB - Bsky Save My Bookmarks")
    print("="*60)
    print(f"\n📂 Destination : {dest_base}")
    print("\n1. Exporter les bookmarks (sauvegarde liens uniquement)")
    
    if has_urls:
        print("2. Télécharger les médias (nouveaux uniquement)")
        print("3. Télécharger les médias (tout re-télécharger)")
    
    print("4. Afficher les statistiques")
    
    if has_downloads:
        print("5. Ouvrir le dossier de téléchargements")
    
    print("6. Configuration")
    print("9. Options avancées")
    print("0. Quitter")
    print()

def get_token_from_clipboard():
    """Récupère le token depuis le presse-papier"""
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        token = win32clipboard.GetClipboardData()
        win32clipboard.CloseClipboard()
        return token.strip() if token else None
    except:
        # Fallback cross-platform
        try:
            import subprocess
            result = subprocess.run(['powershell', '-command', 'Get-Clipboard'], 
                                  capture_output=True, text=True)
            return result.stdout.strip() if result.returncode == 0 else None
        except:
            return None

def check_token(config):
    """Vérifie la présence du token Bearer"""
    token_file = Path(config["token_file"])
    
    if token_file.exists():
        content = token_file.read_text(encoding="utf-8").strip()
        if content and content.startswith("Bearer "):
            return True
    
    print("\n" + "="*60)
    print("⚠️ Token Bearer manquant ou invalide")
    print("="*60)
    print("\n📖 Pour récupérer votre token :")
    print("   Consultez le fichier Instructions-token.md")
    print()
    print("1. Coller depuis le presse-papier")
    print("2. Lire depuis Token-Bearer.txt")
    print("0. Annuler")
    
    choice = input("\n👉 Choix : ").strip()
    
    if choice == "1":
        token = get_token_from_clipboard()
        if token and token.startswith("Bearer "):
            token_file.write_text(token, encoding="utf-8")
            print("✅ Token enregistré depuis le presse-papier")
            return True
        else:
            print("❌ Token invalide dans le presse-papier (doit commencer par 'Bearer ')")
            return False
    elif choice == "2":
        if token_file.exists():
            content = token_file.read_text(encoding="utf-8").strip()
            if content.startswith("Bearer "):
                print("✅ Token valide trouvé dans Token-Bearer.txt")
                return True
        print("❌ Token invalide dans Token-Bearer.txt")
        return False
    
    return False

def export_bookmarks(config):
    """Exporte les bookmarks"""
    if not check_token(config):
        return False
    
    print("\n🔄 Export des bookmarks...")
    result = subprocess.run(
        ["python", "export_bsky_bookmarks.py"],
        capture_output=False
    )
    if result.returncode == 0:
        print("✅ Export terminé")
    return result.returncode == 0

def download_media(config, force=False, skip_token_check=False):
    """Télécharge les médias"""
    urls_file = Path(config["urls_file"])
    if not urls_file.exists():
        print(f"❌ Fichier {config['urls_file']} introuvable")
        print("   Lancez d'abord l'export des bookmarks (option 1)")
        return False
    
    with open(urls_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]
    
    if not urls:
        print("⚠️ Aucune URL à traiter")
        return False
    
    # Mode dev sans token
    if skip_token_check:
        print("\n" + "="*60)
        print("⚠️ MODE DÉVELOPPEMENT")
        print("="*60)
        print("Traitement direct depuis urls.txt")
        print("• Token non vérifié")
        print("• Base de données non mise à jour")
        print("• Téléchargements uniquement")
        print("="*60)
        confirm = input(f"\n▶️ Traiter {len(urls)} posts en mode dev ? (O/n) : ").strip().lower()
        if confirm and confirm != "o":
            return False
        
        # Appel direct à what.py sans DB
        result = subprocess.run(
            ["python", "what.py", config["img_dir"], config["vid_dir"], "--no-db"] + urls
        )
        return result.returncode == 0
    
    db = Database(config["db_file"])
    
    if force:
        print(f"\n⚠️ Mode FORCE : {len(urls)} posts seront traités")
        urls_to_process = urls
    else:
        urls_to_process = db.get_new_posts(urls)
        print(f"\n📊 {len(urls)} URLs au total, {len(urls_to_process)} nouvelles")
    
    if not urls_to_process:
        print("✅ Tous les posts sont déjà traités")
        db.close()
        return True
    
    confirm = input(f"\n▶️ Traiter {len(urls_to_process)} posts ? (O/n) : ").strip().lower()
    if confirm and confirm != "o":
        db.close()
        return False
    
    print("\n🚀 Lancement du téléchargement...\n")
    
    result = subprocess.run(
        ["python", "what.py", config["img_dir"], config["vid_dir"]] + urls_to_process
    )
    
    db.close()
    return result.returncode == 0

def show_stats(config):
    """Affiche les statistiques"""
    db = Database(config["db_file"])
    stats = db.get_stats()
    db.close()
    
    print("\n" + "="*40)
    print("📊 Statistiques")
    print("="*40)
    print(f"Posts trackés    : {stats['posts']}")
    print(f"Images téléchargées : {stats['images']}")
    print(f"Vidéos téléchargées : {stats['videos']}")
    print(f"Total médias     : {stats['images'] + stats['videos']}")
    print("="*40)

def configure(config):
    """Menu de configuration"""
    while True:
        clear_screen()
        print("\n" + "="*60)
        print("⚙️ Configuration")
        print("="*60)
        print(f"\n1. Dossier images : {config['img_dir']}")
        print(f"2. Dossier vidéos : {config['vid_dir']}")
        print(f"3. Fichier token  : {config['token_file']}")
        print(f"4. Fichier URLs   : {config['urls_file']}")
        print("0. Retour")
        
        choice = input("\n👉 Choix : ").strip()
        
        if choice == "0":
            break
        elif choice == "1":
            new_val = input(f"Nouveau dossier images [{config['img_dir']}] : ").strip()
            if new_val:
                config["img_dir"] = new_val
                save_config(config)
                print("✅ Sauvegardé")
        elif choice == "2":
            new_val = input(f"Nouveau dossier vidéos [{config['vid_dir']}] : ").strip()
            if new_val:
                config["vid_dir"] = new_val
                save_config(config)
                print("✅ Sauvegardé")
        elif choice == "3":
            new_val = input(f"Nouveau fichier token [{config['token_file']}] : ").strip()
            if new_val:
                config["token_file"] = new_val
                save_config(config)
                print("✅ Sauvegardé")
        elif choice == "4":
            new_val = input(f"Nouveau fichier URLs [{config['urls_file']}] : ").strip()
            if new_val:
                config["urls_file"] = new_val
                save_config(config)
                print("✅ Sauvegardé")
        
        input("\nAppuyez sur Entrée...")

def advanced_menu(config):
    """Menu options avancées"""
    while True:
        clear_screen()
        print("\n" + "="*60)
        print("⚙️ Options avancées")
        print("="*60)
        
        urls_file = Path(config["urls_file"])
        has_urls = urls_file.exists() and urls_file.stat().st_size > 0
        
        print("\n1. Réinitialiser la base de données")
        
        if has_urls:
            print("2. Mode développement (depuis urls.txt, sans token)")
        
        print("3. Supprimer les logs")
        print("4. Ouvrir le dossier de téléchargements")
        print("0. Retour")
        
        choice = input("\n👉 Choix : ").strip()
        
        if choice == "0":
            break
        elif choice == "1":
            print("\n" + "="*60)
            print("⚠️ RÉINITIALISATION DE LA BASE DE DONNÉES")
            print("="*60)
            print("\nCette action va :")
            print("  • Supprimer l'historique des posts traités")
            print("  • Supprimer l'historique des médias téléchargés")
            print("  • NE PAS supprimer les fichiers déjà téléchargés")
            print()
            confirm = input("Confirmer la réinitialisation ? (tapez 'RESET') : ").strip()
            if confirm == "RESET":
                db_file = Path(config["db_file"])
                if db_file.exists():
                    db_file.unlink()
                    print("✅ Base de données réinitialisée")
                else:
                    print("⚠️ Aucune base de données à réinitialiser")
            else:
                print("❌ Réinitialisation annulée")
            input("\nAppuyez sur Entrée...")
        
        elif choice == "2":
            if not has_urls:
                print("\n⚠️ Aucune URL disponible dans urls.txt")
                input("\nAppuyez sur Entrée...")
            else:
                download_media(config, force=True, skip_token_check=True)
        
        elif choice == "3":
            from config import cleanup_logs
            deleted = cleanup_logs(config)
            print(f"\n✅ {deleted} fichier(s) log supprimé(s)")
            input("\nAppuyez sur Entrée...")

        elif choice == "4":
            download_dir = os.path.expandvars(r"%USERPROFILE%\Downloads\BSMB")
            if sys.platform == "win32":
                os.startfile(download_dir)
            else:
                subprocess.run(["xdg-open", download_dir])

def main():
    config = load_config()
    ensure_dirs(config)
    from config import cleanup_old_logs
    cleanup_old_logs(config)
    
    while True:
        clear_screen()
        show_menu()
        
        choice = input("👉 Choix : ").strip()
        
        # Vérifier disponibilité options 2 et 3
        urls_file = Path(config["urls_file"])
        has_urls = urls_file.exists() and urls_file.stat().st_size > 0
        
        if choice == "0":
            print("\n👋 Au revoir !")
            break
        elif choice == "1":
            export_bookmarks(config)
            input("\nAppuyez sur Entrée...")
        elif choice == "2":
            if not has_urls:
                print("\n⚠️ Aucune URL disponible")
                print("   Lancez d'abord l'export des bookmarks (option 1)")
            else:
                download_media(config, force=False)
        elif choice == "3":
            if not has_urls:
                print("\n⚠️ Aucune URL disponible")
                print("   Lancez d'abord l'export des bookmarks (option 1)")
            else:
                download_media(config, force=True)
        elif choice == "4":
            show_stats(config)
            input("\nAppuyez sur Entrée...")
        elif choice == "5":
            if not has_downloads:
                print("\n⚠️ Aucun média téléchargé")
                input("\nAppuyez sur Entrée...")
            else:
                download_dir = os.path.expandvars(r"%USERPROFILE%\Downloads\BSMB")
                if sys.platform == "win32":
                    os.startfile(download_dir)
                else:
                    subprocess.run(["xdg-open", download_dir])
        elif choice == "6":
            configure(config)
        elif choice == "9":
            advanced_menu(config)
        elif choice == "0":
            print("\n👋 Au revoir !")
            import time
            time.sleep(2)
            sys.exit(0)
        else:
            print("❌ Choix invalide")
            input("\nAppuyez sur Entrée...")

if __name__ == "__main__":
    main()