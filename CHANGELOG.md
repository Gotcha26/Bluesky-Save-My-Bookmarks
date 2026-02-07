# 📜 Changelog - BSMB

Tous les changements notables du projet seront documentés dans ce fichier.

Format: [Semantic Versioning](https://semver.org/) (MAJOR.MINOR.PATCH)

---

## [2.1] - 2026-02-07 - Authentification & Refonte UI

### ✨ Nouvelles fonctionnalités

#### Authentification automatique via createSession
- Nouveau module `core/auth.py` avec authentification AT Protocol
- `create_session(handle, app_password)` → génère Bearer token automatiquement
- `get_token(config)` → mode auto ou fallback Token-Bearer.txt
- `has_credentials(config)` → vérification pour UI
- Menu interactif d'authentification avec 3 options
- Test de connexion automatique lors de la configuration
- **Avantage** : Plus besoin de copier token manuellement!

#### Refonte UI avec menu-generator pattern
- Nouvelle classe `Colors` centralisée dans `core/colors.py`
- Détection automatique du support couleur ANSI
- Windows 10+ : activation ANSI mode via kernel32 VTP
- Support ConEmu, Windows Terminal, Linux, macOS
- Menus catégorisés avec sections (BOOKMARKS, OUTILS, CONFIGURATION)
- Header amélioré avec ligne de statut (Auth/Bookmarks/Médias)
- Formatage cohérent : `success()`, `error()`, `warning()`, `info()`
- Éléments UI : `separator()`, `box_header()`, `menu_option()`, `config_line()`
- **Avantage** : Interface professionnelle et cross-platform

### 🐛 Corrections de bugs

- ✅ `orchestrator.py:274` : Import fixé (`from config import` → `from core.config import`)
- ✅ Accents français corrigés dans 70+ instances (UTF-8 full support)
  - Télécharger, Récupérer, détecté, Vérifiez, etc.

### 📚 Documentation

- README.md modernisé (321 → 640 lignes)
  - 4 diagrammes Mermaid (flowchart, graph, sequence)
  - Tableau comparatif auth modes (createSession vs Bearer token)
  - FAQ restructuré (11 cas couverts)
  - Guide démarrage rapide 2 min
  - Section sécurité/confidentialité détaillée

- CONTRIBUTING.md (nouveau)
  - Configuration dev, guidelines code
  - Structure tests, processus PR
  - Architecture modules clés

- DEVELOPMENT.md (nouveau)
  - Diagrammes d'architecture Mermaid
  - Deep-dive: auth, config, database, analysis
  - Patterns de test avec examples
  - Performance et debugging

### 🔧 Configuration

- Ajout `bsky_handle` et `bsky_app_password` dans DEFAULT_CONFIG
- Stockage sécurisé dans `config.json` (local, hors Git)
- Migration auto conservée (img_dir → download_dir)

### 🔐 Sécurité

- Token passé via env var `BSMB_TOKEN` (invisible process list)
- Fallback rétrocompatible Token-Bearer.txt si échec createSession
- Identifiants 401/429/timeout gérés spécifiquement

### 📋 Commits

- 833af6c: "feat: Authentification automatique via createSession et refonte UI"
- e1ae8ae: "docs: Documentation moderne avec diagrammes Mermaid"
- f28c842: "docs: Guides complets pour contribution et développement"

---

## [2.0] - 2025-01-25 - Architecture modulaire & Résolution reposts

### ✨ Nouvelles fonctionnalités

#### Architecture complètement refactorisée
- **core/** : Logique métier centralisée
  - `config.py` : Configuration multi-OS (JSON)
  - `database.py` : Tracking SQLite (posts + médias)
  - `orchestrator.py` : Orchestrateur subprocess

- **api/** : API Bluesky
  - `export_bookmarks.py` : Export via getBookmarks (paginated)
  - `post_analyzer.py` : Détection type post (image/vidéo/repost/erreur)
  - `repost_resolver.py` : Résolution automatique des reposts

- **downloaders/** : Téléchargement modulaire
  - `images.py` : Images avec EXIF metadata
  - `videos.py` : Vidéos avec ffmpeg metadata
  - `text.py` : Texte seul (posts sans média)

#### Résolution des reposts
- Détection automatique quand post = repost
- Résolution vers post original via AT Protocol
- Téléchargement du post original (récursif)
- Tracking séparé repost vs original

#### Métadonnées complètes
- **Images** : EXIF avec titre, auteur, date, copyright
- **Vidéos** : Métadonnées ffmpeg (titre, commentaire, date, artiste)
- **Format fichier** : `handle_YYYYMMDD_postid_N.ext`
- **Traçabilité** : Chaque fichier remontre à son post Bluesky

#### Mode développement
- Menu Avancé > Option 1 : Traitement sans token validation
- Parfait pour tester/déboguer avec liste restreinte
- DB non mise à jour (permet re-traitement)

#### Réinitialisation granulaire
- Menu Statistiques > R : Réinitialiser DB
- Supprime l'historique, **pas** les fichiers
- Permet re-téléchargement complet

### 🐛 Corrections vs version 1.x

- Gestion d'erreurs par post (pas de crash global)
- Posts supprimés (400) trackés séparément
- Erreurs serveur (500) loggées
- Types inconnus debuggables
- DB lockups évités (close() systématique)

### 📊 Base de données

- SQLite simple (2 tables : posts + media)
- Tracking : url, post_id, handle, timestamps
- Stats : nombre posts/images/vidéos
- Migration de zéro (pas d'upgrade path)

### 📁 Structure fichiers

```
├── bsmb.py                    # Menu principal TUI
├── config.json               # Config utilisateur
├── bsmb.db                   # DB SQLite
├── urls.txt / urls.txt.bak  # Bookmarks
├── core/                     # Logique métier
├── api/                      # API Bluesky
├── downloaders/              # Téléchargeurs
├── logs/                     # Logs détaillés
└── Downloads/BSMB/           # Fichiers téléchargés
    ├── images/
    ├── videos/
    └── texts/
```

### 💻 Déploiement Windows

- `Start.bat` : Lanceur automatique
  - Détecte Python 3.12
  - Installe pip packages
  - Installe ffmpeg/exiftool via Chocolatey
  - Lance BSMB

### 📚 Documentation initiale

- README.md complet (321 lignes)
- Instructions-token.md (5 min setup)
- Workflow diagrams en ASCII

---

## [1.0] - 2024-XX-XX - Première version

### ⚠️ Note historique

Version 1.0 n'est plus maintenue. Les utilisateurs doivent upgrader à 2.0+.

Fonctionnalités de base :
- Export bookmarks via getBookmarks
- Téléchargement images/vidéos yt-dlp
- Token Bearer manual (DevTools)
- Pas de tracking DB
- Interface simple CLI

---

## 🔮 Roadmap future

### 2.2 (Q1 2026)
- [ ] Parallelization téléchargements (threading/asyncio)
- [ ] Cache détection posts
- [ ] Compression images avant sauvegarde
- [ ] Batch DB inserts

### 2.3 (Q2 2026)
- [ ] GUI Qt/Tkinter alternative
- [ ] Scheduling (téléchargements automatiques)
- [ ] Export formats (JSON, CSV, RSS)
- [ ] Webhook pour intégrations

### 3.0 (Future)
- [ ] Support d'autres réseaux (Mastodon, Pixelfed?)
- [ ] Architecture plugin (downloaders custom)
- [ ] Cloud storage integration (S3, OneDrive, Google Drive)

---

## 📋 Template pour futures releases

```markdown
## [X.X] - YYYY-MM-DD - Titre

### ✨ Nouvelles fonctionnalités
- Feature 1
- Feature 2

### 🐛 Corrections de bugs
- Bug fix 1
- Bug fix 2

### 📚 Documentation
- Doc improvement 1

### 🔧 Changements internes
- Refactor 1
- Performance 1

### ⚠️ Breaking changes
- Breaking change 1 (migration nécessaire)

### 🙏 Remerciements
- Contributor 1
- Contributor 2
```

---

## 🏷️ Glossaire des labels

- **feat** : Nouvelle fonctionnalité
- **fix** : Correction de bug
- **docs** : Documentation
- **refactor** : Restructuring sans changement fonctionnel
- **perf** : Amélioration performance
- **test** : Tests
- **chore** : Maintenance, dépendances
- **breaking** : Change incompatible (majeure)

---

## 💾 Archives anciennes

Les versions archivées sont disponibles via Git tags :

```bash
git tag -l                    # Lister tous les tags
git checkout v2.0             # Checkout version 2.0
git show v2.0:README.md       # Voir README à cette version
```

---

**Dernière mise à jour:** 2026-02-07
