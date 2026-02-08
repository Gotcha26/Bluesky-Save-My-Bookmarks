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
| `deleted` | Post supprimé (erreur HTTP 400) |
| `error_500` | Erreur serveur temporaire (HTTP 500) |

Les liens morts sont visibles dans **Stockage local** et peuvent être nettoyés.

Le nettoyage :
- Supprime les entrées `deleted` de la base de données
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
│   ├── colors.py               # Couleurs ANSI cross-platform
│   ├── config.py               # Configuration JSON + migration
│   ├── database.py             # SQLite (posts + media tracking)
│   └── orchestrator.py         # Orchestrateur (ThreadPoolExecutor)
│
├── api/                         # Interactions API Bluesky
│   ├── export_bookmarks.py     # fetch_bookmarks() + mode standalone
│   ├── post_analyzer.py        # Détection type post (image/vidéo/repost)
│   └── repost_resolver.py      # Résolution DID → handle
│
├── downloaders/                 # Téléchargeurs (subprocess)
│   ├── images.py               # Images avec EXIF
│   ├── videos.py               # Vidéos avec ffmpeg
│   └── text.py                 # Texte seul
│
├── tests/                       # Tests unitaires (pytest)
└── logs/                        # Fichiers de log (auto-créé)
```

### Flux de données

```
bsmb.py (menu)
  → core/auth.py (createSession → Bearer token)
  → core/bookmarks.py (sync: API → urls.txt → compare DB)
  → core/orchestrator.py (ThreadPoolExecutor)
    → api/post_analyzer.py (détecte type)
    → api/repost_resolver.py (résout reposts)
    → downloaders/*.py (subprocess: télécharge)
    → core/database.py (tracking SQLite)
```

### Parallélisation

L'orchestrateur utilise `concurrent.futures.ThreadPoolExecutor` avec un nombre configurable de workers (1-16, défaut 4).

**Pourquoi ThreadPool plutôt que ProcessPool :**
- Le travail est I/O-bound (réseau + subprocess), pas CPU-bound
- Mémoire partagée pour les compteurs et la DB
- Le GIL est relâché pendant les opérations I/O

**Thread-safety :**
- `Database` : `threading.Lock` sur chaque méthode + `check_same_thread=False`
- Console : `_print_lock` empêche l'entrelacement des lignes
- Logs : `log_lock` protège l'écriture fichier
- Stats : `stats_lock` protège les compteurs

---

## Configuration avancée (config.json)

```json
{
  "download_dir": "C:/Users/xxx/Downloads/BSMB",
  "token_file": "Token-Bearer.txt",
  "urls_file": "urls.txt",
  "db_file": "bsmb.db",
  "logs_dir": "logs",
  "max_logs": 5,
  "max_filename_len": 64,
  "min_postid_short": 4,
  "index_digits": 1,
  "bsky_handle": "monpseudo.bsky.social",
  "bsky_app_password": "xxxx-xxxx-xxxx-xxxx",
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
| `db_file` | Base de données SQLite | `bsmb.db` |
| `logs_dir` | Dossier des logs | `logs` |
| `max_workers` | Workers parallèles | `4` |
| `last_sync` | Date de dernière synchronisation | `""` |
| `advanced_mode` | Mode avancé activé | `false` |
| `max_filename_len` | Longueur max des noms de fichiers | `64` |

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
| `status` | TEXT | `ok`, `deleted`, `error_500`, `unknown` |

### Table `media`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | INTEGER (PK) | Auto-incrémenté |
| `post_url` | TEXT (FK) | Référence vers posts.url |
| `media_type` | TEXT | `image`, `video`, `text` |
| `filename` | TEXT | Nom du fichier téléchargé |
| `downloaded_at` | TEXT | Date de téléchargement (ISO) |

### Migration automatique

Lors du premier lancement après une mise à jour, BSMB ajoute automatiquement la colonne `status` aux bases existantes via `ALTER TABLE`.

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

154 tests couvrent : config, database, auth, colors, post_analyzer, repost_resolver, images, parallélisation, bookmarks, export_bookmarks.

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
