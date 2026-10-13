# 📜 Changelog - BSMB

Tous les changements notables du projet seront documentés dans ce fichier.

Format: [Semantic Versioning](https://semver.org/) (MAJOR.MINOR.PATCH)

---

## [3.1] - 2026-10-13 - Audit d'octobre 2026 : fiabilité, archive fidèle, installation

Chantier issu de l'audit d'octobre 2026 (issues #1 à #18). Un point par issue.

### ✨ Nouvelles fonctionnalités

- **Archive fidèle d'un post** (#7) : chaque post archivé produit un `.txt` lisible (facettes résolues, liens avec leur URL réelle, texte alternatif des médias, carte de lien, `Cite:`, `Réponse à:`) et une fiche JSON (record brut + `postView`), désactivable par `save_sidecar`. Le texte alternatif des images va aussi dans l'EXIF `ImageDescription`. Voir [ADVANCED.md](ADVANCED.md#archive-dun-post-fichiers-texte-et-fiche-json).
- **Citations (quote posts)** (#5) : le texte et les médias du post citant sont archivés, puis ceux du post cité (fichiers `…_quote…`, deux niveaux au plus). Les cités supprimés, bloqués ou qui ne sont pas des posts sont ignorés avec une note.
- **Cartes de lien et GIF** (#4) : les embeds `external` ne sont plus « type inconnu » ; texte, lien, titre, description et vignette sont archivés, ainsi que les GIF Tenor et les fichiers `.gif` / `.mp4` / `.webp` directs.
- **Vidéos** (#6) : vidéos de 10 minutes et 300 Mo, GIF du client (suffixe `_gif` ou dossier `videos/gifs/`), sous-titres `.vtt`, texte alternatif, extension d'après le `mimeType`, écriture en `.part` et repli HLS par ffmpeg.
- **Images en qualité d'origine** (#18) : téléchargement du blob d'origine (`getBlob`) avec repli sur le CDN, saut des images déjà archivées (`skip_existing_cid`), option `image_quality`.
- **Cache des bookmarks** (#3) : la réponse complète de `getBookmarks` est conservée dans `bookmarks.json`. Les posts supprimés ou bloqués sont repérés dès la synchronisation et l'analyse se fait sans `getRecord` par post.
- **Ligne de commande** (#13) : `bsmb sync`, `download [--force]`, `run`, `status [--json]`, `--version` et `--yes`, codes de retour 0 à 4, mode non interactif automatique quand l'entrée n'est pas un terminal (planification Windows et cron documentées).
- **Robustesse réseau** (#11) : session HTTP partagée (User-Agent BSMB, reprises avec délai croissant sur 429 et 5xx, limiteur de débit), statut `error_429`, renouvellement automatique du token expiré (`refreshSession`).
- **Version affichée** (#15) : `core/version.py` est la source unique ; l'en-tête du menu affiche `BSMB v3.1.0`, `bsmb --version` et les fiches JSON la reprennent.

### 🐛 Corrections de bugs

- **Hôte PDS** (#1) : le PDS du compte est détecté à la connexion (`pds_url`) au lieu d'un hôte codé en dur qui ne fonctionnait que pour un seul compte ; il est résolu avant `createSession` (handle → DID → document DID), ce qui ouvre la connexion aux comptes hébergés hors de bsky.social (eurosky.social, PDS auto-hébergé).
- **Identité des posts** (#2) : un post est identifié par son AT-URI (DID + clé) et non par l'URL avec handle, à la synchronisation comme au téléchargement et dans le compteur « Nouveaux » (dès que le cache `bookmarks.json` existe) ; `handle.invalid` n'est plus marqué « supprimé » et un changement de handle ne crée plus de doublon ni de retéléchargement.
- **Textes** (#8) : `text.py` respecte `download_dir` et les textes sont comptés en base.
- **Base de données** (#9) : le statut d'un post n'est plus écrasé, les médias portent leur vrai nom de fichier sans doublon, les erreurs 500, 429 et inconnues ainsi que les téléchargements en échec (nouveau statut `failed`, échec total ou partiel) sont retentés après `retry_after_days` (7) jours.

### 🔐 Sécurité

- **App Password** (#12) : stocké dans le trousseau du système (`keyring`, optionnel) avec repli sur `config.json`, jamais journalisé ; droits `600` sur `config.json` et `bookmarks.json` (POSIX) ; option « Déconnecter mon compte » ; migration automatique d'un secret en clair.

### 🔧 Infrastructure

- **Plus de sous-processus** (#10) : les téléchargeurs sont des fonctions importables appelées directement par l'orchestrateur ; seuls `exiftool` et `ffmpeg` sont exécutés en externe. Les chemins relatifs sont ancrés sur le dossier d'installation (`PROJECT_ROOT`), `max_logs` est appliqué.
- **Installation** (#14) : `Start.bat` réécrit (détection réelle de Python, `winget` puis Chocolatey, ffmpeg et exiftool facultatifs, plus de `yt-dlp`), `start.sh` pour Linux et macOS, `pyproject.toml` (installation par `pipx`, commande `bsmb`), `requirements-optional.txt`.
- **CI et tests** (#16) : ruff (analyse et formatage), couverture minimale de 70 %, matrice Python 3.11 à 3.14 sur Ubuntu et Windows, Dependabot, fixtures d'API réelles et tests de `process_post` et des téléchargeurs (plus de 770 tests contre 154).
- **Internationalisation** (#17) : interface en français et en anglais (`gettext`, `core/i18n.py`). Catalogues `lang/fr` et `lang/en` (`.mo` compilés au démarrage), clé de config `language` (`""` = langue du système), option **L. Langue** du menu Paramètres, option globale `--lang {fr,en,auto}`, `README.en.md`. Procédure de traduction : `lang/README.md`. Le log fichier reste en français.
- **Documentation et code mort** (#15) : `FAQ.md` et `Instructions-token.md` fusionnés dans `README.md` et `ADVANCED.md` ; `DEVELOPMENT.md` et `CONTRIBUTING.md` réécrits, un seul schéma d'architecture (`ADVANCED.md`) ; ce changelog complété ; `core/logger.py`, `tools/debug_post.py` et `get_token_from_clipboard()` supprimés.

### ⚠️ Breaking changes

- **Python 3.11 ou plus récent** est requis (la 3.10 n'est plus prise en charge).
- **`index_digits` vaut 2 par défaut** : les nouvelles images sont nommées `…_01.jpg` (au lieu de `…_1.jpg`). Les fichiers déjà téléchargés ne sont pas renommés ; pour garder l'ancien format, mettez `index_digits` à `1` dans `config.json`.
- **Nouveau statut `blocked`** (post bloqué, jamais retenté, nettoyable avec les liens morts) et statuts `error_429` et `failed` (téléchargement en échec, retenté). `repost` n'est plus écrit (ancien statut des citations, encore retenté pour les anciennes lignes).
- **Schéma de la base en version 2** : migration automatique au premier lancement (table `media` recréée sans doublons, table `meta`). Sauvegardez `bsmb.db` avant de mettre à jour : le retour à une version antérieure n'est pas prévu.
- **`requests` reste la seule dépendance obligatoire** ; `keyring` est facultatif.
- `tools/debug_post.py`, `core/logger.py` et `FAQ.md` / `Instructions-token.md` sont supprimés ; le token n'est plus transmis par la variable `BSMB_TOKEN` à un sous-processus (le script `api/export_bookmarks.py` reste utilisable seul). `api/repost_resolver.py` n'est plus qu'un alias déprécié de `api/quote_resolver.py`.

---

## [3.0] - 2026-02-08 - Refonte « novice d'abord »

### ✨ Nouvelles fonctionnalités

- **Menu à quatre entrées** : **Mon compte** (connexion, synchronisation, compteurs en ligne et local), **Stockage local** (statistiques, taille du dossier, nettoyage), **Paramètres** (identifiants, dossier, workers, mode avancé) et **Télécharger**, qui n'est proposé qu'une fois le compte connecté et les bookmarks synchronisés.
- **`BookmarkSync`** (`core/bookmarks.py`) : pont entre l'API et la base, qui compte les bookmarks en ligne, déjà traités et nouveaux.
- **Détection des liens morts** : les posts supprimés (400) sont identifiés, listés dans `logs/deleted_posts_*.txt` et nettoyables depuis **Stockage local**, sans jamais supprimer les fichiers déjà téléchargés.
- **Mode avancé** (Paramètres) : fichier token de secours, fichier d'URLs, suppression des logs, **Mode dev** (traitement de `urls.txt` sans token ni base) et **Force DL**.
- Suite de **154 tests** et documentation utilisateur réorganisée (`README.md`, `ADVANCED.md`).

### 🔧 Changements internes

- Le menu a été simplifié par rapport à la 2.x (disparition des « Option 1 : Export » et « Option 2 : Orchestrator »).

---

## [2.2] - 2026-02-08 - Parallélisation, tests et CI

### ✨ Nouvelles fonctionnalités

- **Téléchargements parallèles** : l'orchestrateur utilise un `ThreadPoolExecutor` à nombre de workers configurable (`max_workers`, 1 à 16, 4 par défaut), avec une base partagée protégée par un verrou et des écritures console et log sérialisées.
- **Tests unitaires** (120 à la livraison) et `requirements.txt`.
- **Intégration continue** GitHub Actions.

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
- Guide de récupération du token (5 min de mise en place ; fusionné dans ADVANCED.md en 3.1)
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

### Prochaine version (3.2)
- [ ] Dossier de données utilisateur (`platformdirs`) : `config.json`, `bsmb.db` et `logs/` survivraient à `pipx upgrade` au lieu d'être stockés dans le dossier d'installation
- [ ] Contexte de fil : archiver le post parent d'une réponse (aujourd'hui seule la ligne `Réponse à:` est écrite)
- [ ] Incrustation des sous-titres dans le MP4 (aujourd'hui des fichiers `.vtt` à côté de la vidéo)

### Plus tard
- [ ] GUI Qt/Tkinter alternative
- [ ] Export de la liste dans d'autres formats (CSV, RSS)
- [ ] Webhook pour intégrations
- [ ] Support d'autres réseaux (Mastodon, Pixelfed ?)
- [ ] Architecture plugin (téléchargeurs personnalisés)
- [ ] Stockage cloud (S3, OneDrive, Google Drive)

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

Aucun tag Git n'a été posé à ce jour : le mainteneur taguera les versions (`v3.1.0`…). Une fois les tags publiés, les versions archivées seront consultables ainsi :

```bash
git tag -l                    # Lister tous les tags
git checkout v3.1.0           # Se placer sur une version
git show v3.1.0:README.md     # Voir le README à cette version
```

En attendant, `git log` retrouve chaque version par sa date.

---

**Dernière mise à jour:** 2026-10-13
