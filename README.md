# 🔖 BSMB - Bsky Save My Bookmarks

Utilitaire pour exporter et télécharger vos bookmarks Bluesky avec suivi automatique.

## 🚀 Installation rapide

### Windows
1. **Double-cliquez sur `Start.bat`**
2. L'installation automatique des prérequis se lance :
   - Python 3.12 (si absent)
   - pip install requests yt-dlp
   - ffmpeg via Chocolatey
   - exiftool via Chocolatey
3. **Patientez** pendant l'installation (peut prendre quelques minutes)
4. BSMB se lance automatiquement

### Linux/Mac
```bash
# Installer Python 3.8+ et pip si nécessaire
sudo apt install python3 python3-pip ffmpeg exiftool  # Debian/Ubuntu
# ou
brew install python ffmpeg exiftool  # macOS

# Installer les dépendances Python
pip install requests yt-dlp

# Lancer BSMB
python bsmb.py
```

## 📋 Prérequis

- **Python 3.8+** (obligatoire)
- **requests** (bibliothèque HTTP Python)
- **yt-dlp** (téléchargeur vidéo universel - [GitHub](https://github.com/yt-dlp/yt-dlp))
- **ffmpeg** (pour vidéos avec métadonnées)
- **exiftool** (pour métadonnées EXIF images)

> **Note** : BSMB utilise yt-dlp comme fallback pour certains formats vidéo complexes, 
> mais privilégie l'API native Bluesky pour des téléchargements plus rapides et fiables.

## 🎯 Utilisation

### Première utilisation

1. **Récupérer votre token Bearer**
   - Consultez **`Instructions-token.md`** pour la procédure détaillée
   - Ou lors du premier lancement, BSMB vous guidera :
     - Option 1 : Coller depuis le presse-papier (recommandé)
     - Option 2 : Lire depuis Token-Bearer.txt

2. **Lancer BSMB**
   ```bash
   python bsmb.py
   ```
   ou double-clic sur `Start.bat` (Windows)

3. **Menu principal**
   - Option 1 : Exporter bookmarks → crée `urls.txt` (sauvegarde liens uniquement)
   - Options 2-3 apparaissent après l'export
   - Option 2 : Télécharger nouveaux médias uniquement
   - Option 3 : Tout re-télécharger (force)
   - Option 4 : Voir les statistiques
   - Option 5 : Configurer les chemins
   - Option 6 : Ouvrir le dossier de téléchargements (si médias présents)
   - Option 7 : Réinitialiser la base de données (en cas de problème)

> **Important** : L'export des bookmarks (option 1) crée seulement un fichier texte.
> Vous pouvez utiliser ce fichier `urls.txt` dans d'autres outils sans télécharger les médias.

### Workflow recommandé

```
1. Export bookmarks (option 1)
   → Crée urls.txt avec vos liens
   → Utilisable tel quel dans d'autres outils
   ↓
2. Télécharger nouveaux médias (option 2)
   → Seuls les nouveaux posts sont traités
   ↓
3. Vérifier stats (option 4)
```

## 🗂️ Structure des fichiers

```
bsmb/
├── bsmb.py                  # Interface principale ⭐
├── config.py                # Configuration
├── database.py              # Tracking SQLite
├── export_bsky_bookmarks.py # Export bookmarks
├── bsky_img_downloader.py   # Téléchargement images
├── bsky_vid_downloader.py   # Téléchargement vidéos
├── what.py                  # Orchestrateur
├── Start.bat                # Lanceur Windows
├── Instructions-token.md    # Guide token Bearer 📖
├── config.json              # Config utilisateur (auto-créé)
├── bsmb.db                  # Base de données (auto-créé)
└── Token-Bearer.txt         # Votre token (à créer)
```

## ⚙️ Configuration

Fichier `config.json` (créé automatiquement) :
```json
{
  "img_dir": "%USERPROFILE%\\Downloads\\BSMB\\images",
  "vid_dir": "%USERPROFILE%\\Downloads\\BSMB\\videos",
  "token_file": "Token-Bearer.txt",
  "urls_file": "urls.txt"
}
```

Modifiable via Option 5 du menu ou directement dans le fichier.

## 🔍 Fonctionnalités

### ✅ Export flexible
- **urls.txt seul** : Option 1 crée seulement la liste des liens
- **Réutilisable** : Fichier compatible avec yt-dlp, wget, curl, etc.
- **Pas de doublon** : Détection automatique des pages vides
- **Interruptible** : Arrêt dès qu'il n'y a plus de nouveaux bookmarks

### ✅ Téléchargement intelligent
- **Pas de doublons** : Base SQLite track tous les téléchargements
- **Nouveaux uniquement** : Mode incrémental par défaut
- **Force mode** : Option pour tout re-télécharger si besoin
- **Statistiques** : Vue d'ensemble de votre collection

### 📦 Métadonnées complètes
- **Images** : EXIF avec titre, auteur, date, copyright
- **Vidéos** : Métadonnées ffmpeg (titre, commentaire, date)
- **Nommage** : `handle_YYYYMMDD_postid_N.ext`

### 🛡️ Robustesse
- Gestion d'erreurs par post
- Confirmation avant gros téléchargements
- Logs des échecs
- Reprise possible à tout moment
- API native Bluesky + fallback yt-dlp si nécessaire

## 🐛 Dépannage

**"Token invalide"**
→ Consultez `Instructions-token.md` pour la procédure complète
→ Utilisez l'option "Coller depuis presse-papier" dans BSMB

**"Aucun média trouvé"**
→ Le post ne contient peut-être que du texte
→ Vérifiez l'URL dans votre navigateur

**"Erreur téléchargement vidéo"**
→ L'API Bluesky a peut-être changé
→ Ouvrez une issue sur GitHub avec l'URL problématique

**"ffmpeg/exiftool introuvable"**
→ Les médias seront téléchargés sans métadonnées

**"Erreur SQLite"**
→ Utilisez l'option 7 du menu pour réinitialiser la base
→ Ou supprimez manuellement `bsmb.db`, il sera recréé

**"Post marqué comme traité mais erreur"**
→ La DB ne marque un post comme traité que si AU MOINS un média a été téléchargé avec succès
→ Si erreur partielle (ex: image OK, vidéo KO), le post est considéré traité
→ Utilisez l'option 3 (force) pour re-télécharger

## 🔐 Éthique et Traçabilité

**BSMB n'est pas un outil de piratage.** Il respecte scrupuleusement les créateurs de contenu :

### Métadonnées préservées

**Pour les images** (via EXIF) :
- `Title` : ID du post Bluesky
- `XPComment` : Texte du post + URL complète
- `Artist` : Handle de l'auteur (@username)
- `DateTimeOriginal` : Date de création du post
- `Copyright` : URL complète du post

**Pour les vidéos** (via ffmpeg) :
- `title` : ID du post Bluesky
- `comment` : Texte du post + URL complète
- `artist` : Handle de l'auteur (@username)
- `creation_time` : Date de création du post

### Nommage transparent

Format : `handle_YYYYMMDD_postid_N.ext`

Exemple : `artiste_20260110_3abc123xyz_01.jpg`

Chaque fichier est **traçable** vers son post d'origine. L'ID du post permet de retrouver la source exacte sur Bluesky.

### Respect des droits

- ✅ Sauvegarde personnelle de vos bookmarks (usage privé)
- ✅ Conservation des attributions d'auteur
- ✅ Liens vers les posts originaux
- ❌ Pas de suppression de watermarks
- ❌ Pas de redistribution encouragée

Si vous partagez un média téléchargé, **citez toujours l'auteur original** et incluez le lien du post Bluesky.

---

- Le token Bearer expire après quelques jours/déconnexion
- Les URLs sont au format `bsky.app/profile/handle/post/id`
- La base de données ne stocke PAS les médias, juste le tracking
- Les anciens scripts `BSMB_*.bat` peuvent être supprimés
- **urls.txt** peut être utilisé directement avec yt-dlp :
  ```bash
  yt-dlp -a urls.txt
  ```

## 🔐 Sécurité

⚠️ **NE PARTAGEZ JAMAIS votre token Bearer**
Il permet un accès complet à votre compte Bluesky.

## 📄 Licence

Projet personnel - Utilisation libre