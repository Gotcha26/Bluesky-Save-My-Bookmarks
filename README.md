# 🔖 BSMB - Bsky Save My Bookmarks

Utilitaire pour exporter et télécharger vos bookmarks Bluesky avec suivi automatique et résolution des reposts.

---

## 📖 Table des matières

- [Installation rapide](#-installation-rapide)
- [Guide d'utilisation](#-guide-dutilisation)
- [Structure du projet](#-structure-du-projet)
- [Fonctionnalités](#-fonctionnalités)
- [FAQ](#-faq)
- [Dépannage](#-dépannage)
- [Éthique et Traçabilité](#-éthique-et-traçabilité)

---

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

---

## 🎯 Guide d'utilisation

### 📋 Première utilisation

#### 1. Récupérer votre token Bearer

BSMB a besoin de votre token Bearer Bluesky pour accéder à vos bookmarks.

📖 **Consultez `Instructions-token.md`** pour la procédure détaillée (5 minutes).

**Résumé rapide :**
1. Connectez-vous sur https://bsky.app
2. Allez dans vos Conservés
3. Ouvrez les outils de développement (F12)
4. Onglet Réseau > Filtrez `getBookmarks`
5. Copiez la valeur `Authorization: Bearer ...`
6. Collez-la dans BSMB (option 1 au premier lancement)

#### 2. Exporter vos bookmarks

```
Menu principal > Option 1 : Exporter les bookmarks
```

Cette opération :
- ✅ Récupère **tous** vos bookmarks via l'API Bluesky
- ✅ Crée/met à jour le fichier `urls.txt` avec la liste des liens
- ✅ Sauvegarde l'ancien fichier en `urls.txt.bak`
- ✅ Ne télécharge **aucun média** (juste la liste)
- ⏱️ Durée : ~5 secondes pour 100 bookmarks

> **Note :** Le fichier `urls.txt` peut être utilisé tel quel dans d'autres outils (yt-dlp, wget, etc.)

#### 3. Télécharger les médias

```
Menu principal > Option 2 : Télécharger les médias (nouveaux uniquement)
```
- Ne télécharge que les posts **non traités**
- Utilise la base de données pour tracker
- Idéal pour les mises à jour régulières

**Pour tout re-télécharger :**
```
Menu > Option 9 (Options avancées) > Option 2 : Forcer le re-téléchargement
```
- Force le téléchargement de **tous** les posts
- Ignore l'historique de la base de données
- Utile après une réinitialisation ou pour corriger des erreurs

---

### 🔄 Workflow recommandé

```
┌─────────────────────────────────────────────┐
│  1. Export bookmarks (Option 1)            │
│     → Crée/met à jour urls.txt             │
│     → Sauvegarde urls.txt.bak              │
│     → ~5 secondes                           │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│  2. Télécharger nouveaux médias (Option 2) │
│     → Seuls les nouveaux posts traités     │
│     → Durée variable selon le volume        │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│  3. Vérifier stats (Option 4)              │
│     → Voir le nombre de médias téléchargés │
│     → Réinitialiser DB si besoin           │
└─────────────────────────────────────────────┘
```

**Mises à jour régulières :**
1. Relancez l'export (Option 1) → met à jour `urls.txt`
2. Téléchargez les nouveaux (Option 2) → seuls les nouveaux posts sont traités
3. Profit ! 🎉

---

### ⚙️ Fonctionnalités avancées

#### Mode Développement
```
Menu principal > Option 9 > Option 1 : Mode développement
```

**Utilité :** Tester avec une liste restreinte d'URLs sans modifier la base de données.

**Comment faire :**
1. Éditez `urls.txt` et ne gardez que quelques URLs de test
2. Lancez le mode développement
3. Les médias seront téléchargés mais la DB ne sera pas mise à jour
4. Parfait pour tester ou retraiter des posts spécifiques

#### Réinitialiser la base de données
```
Menu principal > Option 4 : Statistiques > R : Réinitialiser
```

**Quand l'utiliser :**
- Vous voulez tout re-télécharger depuis zéro
- La base de données est corrompue
- Vous avez changé de configuration

⚠️ **Attention :** Cette action ne supprime **pas** les fichiers déjà téléchargés.

---

## 🗂️ Structure du projet

```
bsmb/
├── bsmb.py                      # Interface principale ⭐
├── Start.bat                    # Lanceur Windows
├── Instructions-token.md        # Guide token Bearer 📖
├── config.json                  # Config utilisateur (auto-créé)
├── bsmb.db                      # Base de données (auto-créé)
├── Token-Bearer.txt             # Votre token (à créer)
├── urls.txt                     # Liste bookmarks (auto-créé)
├── urls.txt.bak                 # Sauvegarde auto (auto-créé)
│
├── core/                        # 🎯 Logique métier
│   ├── config.py               # Configuration multi-OS
│   ├── database.py             # Tracking SQLite
│   └── orchestrator.py         # Orchestrateur principal
│
├── api/                         # 🌐 API Bluesky
│   ├── export_bookmarks.py     # Export bookmarks
│   ├── post_analyzer.py        # Analyse posts
│   └── repost_resolver.py      # Résolution reposts
│
├── downloaders/                 # ⬇️ Téléchargeurs
│   ├── images.py               # Images
│   ├── videos.py               # Vidéos
│   └── text.py                 # Textes
│
└── tools/                       # 🛠️ Utilitaires
    └── debug_post.py           # Debug posts
```

---

## 🌟 Fonctionnalités

### ✅ Export flexible
- **urls.txt seul** : Option 1 crée seulement la liste des liens
- **Sauvegarde auto** : `urls.txt.bak` créé avant chaque export
- **Réutilisable** : Fichier compatible avec yt-dlp, wget, curl, etc.
- **Pas de doublon** : Détection automatique des pages vides
- **Interruptible** : Arrêt dès qu'il n'y a plus de nouveaux bookmarks

### ✅ Téléchargement intelligent
- **Pas de doublons** : Base SQLite track tous les téléchargements
- **Nouveaux uniquement** : Mode incrémental par défaut
- **Force mode** : Option pour tout re-télécharger si besoin
- **Résolution des reposts** : Détecte et télécharge le post original
- **Gestion des erreurs** : Posts supprimés, erreurs serveur, types inconnus

### 📦 Métadonnées complètes
- **Images** : EXIF avec titre, auteur, date, copyright
- **Vidéos** : Métadonnées ffmpeg (titre, commentaire, date)
- **Nommage** : `handle_YYYYMMDD_postid_N.ext`

### 🛡️ Robustesse
- Gestion d'erreurs par post
- Confirmation avant gros téléchargements
- Logs des échecs
- Reprise possible à tout moment
- Multi-OS (Windows, macOS, Linux)

---

## 🐛 Dépannage

**"Token invalide"**  
→ Consultez `Instructions-token.md` pour récupérer un nouveau token

**"Aucun média trouvé"**  
→ Le post ne contient peut-être que du texte  
→ Vérifiez l'URL dans votre navigateur

**"Erreur téléchargement vidéo"**  
→ L'API Bluesky a peut-être changé  
→ Ouvrez une issue sur GitHub avec l'URL problématique

**"ffmpeg/exiftool introuvable"**  
→ Les médias seront téléchargés sans métadonnées  
→ Installez-les pour bénéficier des métadonnées complètes

**"Erreur SQLite"**  
→ Menu > Option 4 (Statistiques) > R (Réinitialiser)  
→ Ou supprimez manuellement `bsmb.db`, il sera recréé

**"Post marqué comme traité mais erreur"**  
→ La DB ne marque un post comme traité que si AU MOINS un média a été téléchargé avec succès  
→ Si erreur partielle (ex: image OK, vidéo KO), le post est considéré traité  
→ Utilisez Menu > Options avancées > Option 2 (Force) pour re-télécharger

---

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

## 📝 Notes importantes

- Le token Bearer expire après quelques jours/déconnexion
- Les URLs sont au format `bsky.app/profile/handle/post/id`
- La base de données ne stocke PAS les médias, juste le tracking
- **urls.txt** peut être utilisé directement avec yt-dlp :
  ```bash
  yt-dlp -a urls.txt
  ```
- **urls.txt.bak** est créé automatiquement à chaque export

---

## 🔐 Sécurité

⚠️ **NE PARTAGEZ JAMAIS votre token Bearer**  
Il permet un accès complet à votre compte Bluesky.

---

## 📄 Licence

Projet personnel - Utilisation libre

---

## 🤝 Contribution

Rapportez les bugs et suggestions sur le [dépôt GitHub](https://github.com/Gotcha26/Bluesky-Save-My-Bookmarks)

---

**Version 2.0** - Janvier 2025