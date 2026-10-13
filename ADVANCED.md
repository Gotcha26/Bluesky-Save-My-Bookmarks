# BSMB - Guide avancé

Ce document couvre les fonctionnalités avancées, l'architecture technique et le mode développeur de BSMB.

---

## Mode avancé

Le mode avancé est accessible dans **Paramètres** > **4. Mode avancé** (toggle on/off).

Une fois activé, des options supplémentaires apparaissent dans les Paramètres :

| Option | Description |
|--------|-------------|
| **Fichier token** | Chemin vers `Token-Bearer.txt` (fallback si createSession échoue) |
| **Fichier URLs** | Chemin vers `urls.txt` (liste des bookmarks exportés) |
| **Supprimer les logs** | Efface tous les fichiers de log |
| **Mode dev** | Traite urls.txt sans token ni mise à jour de la base |
| **Force DL** | Re-télécharge tous les médias (ignore l'historique) |

---

## Authentification avancée

### Méthode 1 : App Password (recommandé)

C'est la méthode par défaut. BSMB appelle `com.atproto.server.createSession` avec votre handle et App Password pour obtenir un token Bearer automatiquement à chaque lancement.

**Avantages :**
- Token renouvelé automatiquement
- Pas d'expiration tant que l'App Password existe
- Configuration unique

**Stockage :** `config.json` (champs `bsky_handle` et `bsky_app_password`)

### Méthode 2 : Token Bearer manuel (fallback)

Si createSession échoue, BSMB tente de lire le fichier `Token-Bearer.txt`.

**Comment obtenir un Token Bearer :**
1. Connectez-vous sur [bsky.app](https://bsky.app)
2. Ouvrez les DevTools du navigateur (F12)
3. Onglet Network > filtrez par `getBookmarks`
4. Copiez le header `Authorization: Bearer ...`
5. Collez-le dans `Token-Bearer.txt`

**Limitations :**
- Le token expire après quelques jours
- Doit être renouvelé manuellement
- Plus complexe à obtenir

Consultez [Instructions-token.md](Instructions-token.md) pour un guide détaillé.

### Comparaison

| Aspect | App Password | Token Bearer |
|--------|-------------|-------------|
| Configuration | Une seule fois | À chaque expiration |
| Renouvellement | Automatique | Manuel |
| Facilité | Simple | Complexe (DevTools) |
| Sécurité | Local dans config.json | Local dans Token-Bearer.txt |

---

## Mode développeur

Accessible via **Paramètres** > **Mode avancé** > **Mode dev**.

Le mode dev traite les URLs depuis `urls.txt` **sans vérification de token** et **sans mise à jour de la base de données**. Utile pour :

- Tester avec une liste restreinte d'URLs
- Retraiter des posts spécifiques
- Déboguer des problèmes de téléchargement

**Comment l'utiliser :**
1. Éditez `urls.txt` et ne gardez que les URLs à tester
2. Activez le mode avancé dans Paramètres
3. Choisissez **Mode dev**
4. Les médias sont téléchargés mais la DB n'est pas mise à jour

---

## Force DL

Accessible via **Paramètres** > **Mode avancé** > **Force DL**.

Re-télécharge **tous** les posts de `urls.txt`, même ceux déjà traités. Utile après :
- Une réinitialisation de la base
- Un changement de dossier de destination
- Des erreurs de téléchargement à corriger

---

## Détection des liens morts

Pendant le téléchargement, BSMB détecte les posts problématiques :

| Status | Signification |
|--------|---------------|
| `ok` | Post normal, traité avec succès |
| `deleted` | Post supprimé (erreur HTTP 400, ou `notFoundPost` renvoyé par `getBookmarks` dès la synchronisation) |
| `blocked` | Post bloqué (`blockedPost` renvoyé par `getBookmarks`) ; jamais retenté |
| `error_500` | Erreur serveur temporaire (HTTP 500) |

Les liens morts sont visibles dans **Stockage local** et peuvent être nettoyés.

Le nettoyage :
- Supprime les entrées `deleted` et `blocked` de la base de données
- Conserve les entrées `error_500` (potentiellement temporaires)
- Ne supprime **jamais** les fichiers déjà téléchargés

---

## Architecture technique

```
bsmb/
├── bsmb.py                      # Interface principale (menu TUI)
├── Start.bat                    # Lanceur Windows automatique
│
├── core/                        # Logique métier
│   ├── auth.py                 # createSession + get_token
│   ├── bookmarks.py            # BookmarkSync (pont API ↔ DB)
│   ├── bookmarks_cache.py      # Cache bookmarks.json (postView bruts)
│   ├── colors.py               # Couleurs ANSI cross-platform
│   ├── config.py               # Configuration JSON + migration
│   ├── database.py             # SQLite (posts + media tracking)
│   ├── paths.py                # PROJECT_ROOT (racine des chemins relatifs)
│   └── orchestrator.py         # Orchestrateur : run() (ThreadPoolExecutor)
│
├── api/                         # Interactions API Bluesky
│   ├── export_bookmarks.py     # fetch_bookmarks() + mode standalone
│   ├── post_analyzer.py        # Détection type post (image/vidéo/texte/citation)
│   ├── quote_resolver.py       # QuoteResolver : record cité par une citation (DID → handle)
│   └── repost_resolver.py      # Alias déprécié de quote_resolver
│
├── downloaders/                 # Téléchargeurs (fonctions importables)
│   ├── __init__.py             # DownloadResult, DownloadError
│   ├── images.py               # download_images() : images avec EXIF
│   ├── videos.py               # download_video() : vidéos avec ffmpeg
│   ├── text.py                 # save_text() : texte seul
│   └── external.py             # download_external() : cartes de lien, GIF Tenor
│
├── tests/                       # Tests unitaires (pytest)
└── logs/                        # Fichiers de log (auto-créé)
```

### Flux de données

```
bsmb.py (menu)
  → core/auth.py (createSession → Bearer token)
  → core/bookmarks.py (sync: API → urls.txt + bookmarks.json → compare DB)
  → core/orchestrator.run() (appel direct, ThreadPoolExecutor)
    → api/post_analyzer.py (détecte type)
    → api/quote_resolver.py (résout le post cité d'une citation, profondeur max 2)
    → downloaders/*.py (fonctions appelées dans les threads : télécharge,
                        renvoie des DownloadResult)
    → core/database.py (tracking SQLite)
```

Aucun sous-processus Python n'est lancé : seuls `exiftool` et `ffmpeg` sont exécutés en externe. Les downloaders restent utilisables seuls pour déboguer un post : `python downloaders/images.py <dossier> <url>`.

### Parallélisation

L'orchestrateur utilise `concurrent.futures.ThreadPoolExecutor` avec un nombre configurable de workers (1-16, défaut 4).

**Pourquoi ThreadPool plutôt que ProcessPool :**
- Le travail est I/O-bound (réseau, exiftool/ffmpeg), pas CPU-bound
- Mémoire partagée pour les compteurs et la DB
- Le GIL est relâché pendant les opérations I/O

**Thread-safety :**
- `Database` : `threading.Lock` sur chaque méthode + `check_same_thread=False`
- Console : `_print_lock` empêche l'entrelacement des lignes
- Logs : `log_lock` protège l'écriture fichier
- Stats : compteurs mis à jour par le seul thread principal (`as_completed`)

---

## Planification

BSMB s'utilise sans menu, pour une tâche planifiée ou un script :

```
python bsmb.py sync                 # synchronise les bookmarks
python bsmb.py download [--force]   # télécharge les nouveaux posts
python bsmb.py run --yes            # sync puis download, sans aucune question
python bsmb.py status [--json]      # état du compte et compteurs
```

Sans sous-commande, le menu interactif s'ouvre. Quand l'entrée standard n'est pas un terminal (tâche planifiée, cron, pipe) ou avec `--yes`, BSMB ne pose aucune question : les confirmations prennent leur valeur par défaut, « Appuyez sur Entrée » disparaît, et la sortie est sans couleur si elle est redirigée. `--yes` s'écrit avant ou après la sous-commande.

Codes de retour :

| Code | Signification |
|------|---------------|
| `0` | Succès |
| `1` | Erreur d'authentification (aucun identifiant, identifiants refusés, token expiré) |
| `2` | Erreur réseau (connexion, timeout, HTTP 5xx) à l'authentification ou pendant la synchronisation. C'est aussi le code d'`argparse` pour un argument invalide |
| `3` | Au moins un téléchargement en échec (ou erreur 500) |

`run` s'arrête au premier code non nul. Prérequis : un compte déjà configuré via le menu (App Password).

### Windows (Planificateur de tâches)

```
schtasks /Create /SC DAILY /TN BSMB /TR "\"C:\chemin\bsmb\.venv\Scripts\python.exe\" \"C:\chemin\bsmb\bsmb.py\" run --yes"
```

### Linux / macOS (cron)

```
0 3 * * * cd /chemin/bsmb && .venv/bin/python bsmb.py run --yes >> logs/cron.log 2>&1
```

---

## Configuration avancée (config.json)

```json
{
  "download_dir": "C:/Users/xxx/Downloads/BSMB",
  "token_file": "Token-Bearer.txt",
  "urls_file": "urls.txt",
  "bookmarks_cache": "bookmarks.json",
  "db_file": "bsmb.db",
  "logs_dir": "logs",
  "max_logs": 5,
  "max_filename_len": 64,
  "min_postid_short": 4,
  "index_digits": 1,
  "bsky_handle": "monpseudo.bsky.social",
  "bsky_app_password": "xxxx-xxxx-xxxx-xxxx",
  "pds_url": "https://morel.us-east.host.bsky.network",
  "max_workers": 4,
  "last_sync": "2026-02-08T14:30:00",
  "advanced_mode": false
}
```

| Clé | Description | Défaut |
|-----|-------------|--------|
| `download_dir` | Dossier racine des téléchargements | `~/Downloads/BSMB` |
| `token_file` | Fichier token Bearer (fallback) | `Token-Bearer.txt` |
| `urls_file` | Liste des bookmarks exportés | `urls.txt` |
| `bookmarks_cache` | Dernière réponse `getBookmarks` (`postView` bruts, évite un `getRecord` par post ; absent en mode dev) | `bookmarks.json` |
| `db_file` | Base de données SQLite | `bsmb.db` |
| `logs_dir` | Dossier des logs | `logs` |
| `pds_url` | PDS du compte, détecté à la connexion (`""` = inconnu, `https://bsky.social` utilisé) | `""` |
| `max_workers` | Workers parallèles | `4` |
| `retry_after_days` | Délai avant de retenter un post en erreur (`error_500`, `unknown`, `repost` hérité) | `7` |
| `last_sync` | Date de dernière synchronisation | `""` |
| `advanced_mode` | Mode avancé activé | `false` |
| `open_folder_after_download` | Propose d'ouvrir le dossier après un téléchargement (ignoré en non interactif) | `true` |
| `max_filename_len` | Longueur max des noms de fichiers | `64` |
| `min_postid_short` | Longueur min de l'ID du post dans un nom d'image tronqué | `4` |
| `index_digits` | Nombre de chiffres de l'index d'image (`_1`, `_01`…) | `1` |
| `max_logs` | Nombre max de logs `download_*.log` conservés | `5` |
| `image_quality` | `"original"` : blob d'origine (`com.atproto.sync.getBlob` via `https://bsky.social`, qui redirige vers le PDS de l'auteur ; repli automatique sur le CDN en cas d'échec) ; `"cdn"` : image `fullsize` du CDN Bluesky (recompressée) | `"original"` |
| `skip_existing_cid` | Ne pas retélécharger une image dont le `cid` est déjà en base avec un fichier présent sur disque (ligne `[SKIP]`) | `true` |

Les chemins relatifs (`token_file`, `urls_file`, `db_file`, `logs_dir`) sont résolus depuis le dossier d'installation de BSMB (celui de `bsmb.py`), pas depuis le dossier courant.

---

## Base de données (SQLite)

### Table `posts`

| Colonne | Type | Description |
|---------|------|-------------|
| `url` | TEXT (PK) | URL complète du post |
| `post_id` | TEXT | ID court du post |
| `handle` | TEXT | Handle de l'auteur |
| `added_at` | TEXT | Date d'ajout (ISO) |
| `last_check` | TEXT | Dernière vérification (ISO) |
| `status` | TEXT | `ok`, `deleted`, `blocked`, `error_500`, `unknown` (`repost` : ancien statut des citations non résolues, plus écrit, encore retenté) |
| `at_uri` | TEXT (UNIQUE) | Identité canonique `at://<did>/app.bsky.feed.post/<rkey>` (NULL pour les anciennes lignes, complété au prochain traitement) |
| `did` | TEXT | DID de l'auteur |
| `rkey` | TEXT | Clé du post |

### Table `media`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | INTEGER (PK) | Auto-incrémenté |
| `post_url` | TEXT (FK) | Référence vers posts.url (`ON DELETE CASCADE`) |
| `media_type` | TEXT | `image`, `video`, `text` |
| `filename` | TEXT | Nom réel du fichier téléchargé (unique par post) |
| `downloaded_at` | TEXT | Date de téléchargement (ISO) |
| `cid` | TEXT | CID du blob AT Protocol (NULL si inconnu) |

### Table `meta`

Paires `key` / `value`. La clé `schema_version` porte la version du schéma (actuellement `2`).

### Migration automatique

Au lancement, BSMB applique les migrations numérotées manquantes aux bases existantes (v1 : colonnes `status` et AT-URI ; v2 : table `media` recréée avec contrainte d'unicité, doublons retirés, table `meta`).

---

## Métadonnées

### Images (EXIF via exiftool)

| Tag | Contenu |
|-----|---------|
| `Title` | ID du post Bluesky |
| `XPComment` | Texte du post + URL complète |
| `Artist` | Handle de l'auteur |
| `DateTimeOriginal` | Date de création du post |
| `Copyright` | URL complète du post |

### Vidéos (ffmpeg)

| Tag | Contenu |
|-----|---------|
| `title` | ID du post Bluesky |
| `comment` | Texte du post + URL complète |
| `artist` | Handle de l'auteur |
| `creation_time` | Date de création du post |

---

## Tests

```bash
# Lancer tous les tests
python -m pytest tests/ -v

# Lancer un fichier spécifique
python -m pytest tests/test_database.py -v
```

154 tests couvrent : config, database, auth, colors, post_analyzer, quote_resolver, images, parallélisation, bookmarks, export_bookmarks.

---

## Dépannage avancé

### Erreurs d'authentification

**"Identifiants invalides"** — Vérifiez handle et App Password. Recréez l'App Password si nécessaire.

**"Trop de tentatives"** — Rate limit atteint. Attendez quelques minutes.

**"Impossible de se connecter"** — Vérifiez votre connexion Internet et que bsky.social est accessible.

### Erreurs de téléchargement

**"ffmpeg/exiftool introuvable"** — Les médias seront téléchargés sans métadonnées. Installez-les pour les avoir.

**"Erreur SQLite"** — Réinitialisez la DB via Stockage local > Réinitialiser, ou supprimez `bsmb.db` manuellement.

### Couleurs

**Les couleurs ne s'affichent pas** — Essayez Windows Terminal au lieu de CMD. Variables : `NO_COLOR=1` (désactiver) ou `FORCE_COLOR=1` (forcer).

---

## Contribuer

Consultez [CONTRIBUTING.md](CONTRIBUTING.md) pour les guidelines de développement.

Consultez [DEVELOPMENT.md](DEVELOPMENT.md) pour l'architecture détaillée et les diagrammes.
