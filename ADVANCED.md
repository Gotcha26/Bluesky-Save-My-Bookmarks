# BSMB - Guide avancé

Ce document couvre les fonctionnalités avancées, l'architecture technique et le mode développeur de BSMB.

---

## Mode avancé

Le mode avancé est accessible dans **Paramètres** > **4. Mode avancé** (toggle on/off).

Une fois activé, des options supplémentaires apparaissent dans les Paramètres :

| Option | Description |
|--------|-------------|
| **Fichier token** | Chemin vers `Token-Bearer.txt` (secours, voir « Méthode 2 ») |
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

**Stockage :** le handle est dans `config.json` (`bsky_handle`). L'App Password va dans le trousseau du système (Credential Manager, Keychain, Secret Service) si la bibliothèque optionnelle `keyring` est installée (`pip install -r requirements-optional.txt`) ; sinon il reste **en clair** dans `config.json` (`bsky_app_password`, fichier local ignoré par Git, droits `600` sous Linux et macOS), et BSMB l'affiche une fois. Un App Password déjà présent dans `config.json` est déplacé vers le trousseau au lancement suivant l'installation de `keyring`. Conseil : créez un App Password dédié à BSMB et révoquez-le en cas de doute (menu **Mon compte** > **D** le supprime de cet ordinateur).

### Méthode 2 : Token Bearer manuel (secours)

À n'utiliser que si vous ne voulez pas confier d'App Password à BSMB. BSMB lit alors le fichier `Token-Bearer.txt` (chemin réglable dans les options avancées), **mais seulement si aucun handle + App Password n'est configuré** : un App Password refusé ne fait pas basculer sur ce fichier. Le menu interactif exige un compte connecté pour proposer la synchronisation ; avec un token manuel, utilisez donc la ligne de commande : `python bsmb.py sync`, puis `python bsmb.py download` (ou `python bsmb.py run --yes`).

**Récupérer le token :**

1. Connectez-vous sur [bsky.app](https://bsky.app) et ouvrez vos éléments enregistrés (bookmarks).
2. Ouvrez les outils de développement du navigateur (F12), onglet **Réseau** (Network).
3. Rafraîchissez la page (F5) et filtrez par `getBookmarks`.
4. Cliquez sur la requête GET, cherchez dans les **en-têtes de la requête** la ligne `Authorization`, puis copiez sa valeur.
5. Collez-la dans `Token-Bearer.txt` (à la racine de BSMB), sans retour à la ligne ni espace superflu.

Sous Safari, activez d'abord les fonctionnalités pour développeurs dans les réglages avancés, puis suivez les mêmes étapes.

La valeur doit **commencer par `Bearer `** (avec l'espace) suivi du jeton :

```
Bearer eyJ0eXAiOiJKV1QiLCJhbGciOi...
```

BSMB ignore le fichier si le contenu ne commence pas par `Bearer `. Si vous avez copié seulement le jeton, ajoutez `Bearer ` devant.

**Limites :**
- Le token d'accès expire vite (environ 2 h) et BSMB ne peut pas le renouveler (pas de jeton de rafraîchissement) : recopiez-en un nouveau quand la synchronisation répond « Token expiré », après une déconnexion de Bluesky ou un changement de mot de passe.
- Seule la synchronisation a besoin du token : les posts sont ensuite téléchargés sans authentification.

**Sécurité :** le token donne accès à votre compte, ne le partagez ni ne le publiez. `Token-Bearer.txt` est ignoré par Git ; sous Linux et macOS, BSMB le passe en lecture réservée (`chmod 600`) quand le menu le lit.

### Comparaison

| Aspect | App Password | Token Bearer |
|--------|-------------|-------------|
| Configuration | Une seule fois | À chaque expiration |
| Renouvellement | Automatique | Manuel |
| Facilité | Simple | Complexe (outils du navigateur) |
| Stockage | Trousseau du système (si `keyring` est installé) ou `config.json` | `Token-Bearer.txt` |
| Interface | Menu et ligne de commande | Ligne de commande seulement |

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
| `error_500` | Erreur serveur temporaire (HTTP 5xx) |
| `error_429` | Limite de débit (HTTP 429) encore atteinte après les reprises automatiques ; retentée comme `error_500` |
| `failed` | Téléchargement en échec, total ou partiel (les fichiers obtenus sont gardés) ; retenté comme `error_500`, après `retry_after_days` jours |

Les liens morts sont visibles dans **Stockage local** et peuvent être nettoyés.

Le nettoyage :
- Supprime les entrées `deleted` et `blocked` de la base de données
- Conserve les entrées `error_500`, `error_429` et `failed` (potentiellement temporaires)
- Ne supprime **jamais** les fichiers déjà téléchargés

---

## Archive d'un post (fichiers texte et fiche JSON)

Chaque post archivé avec succès (images, vidéo, texte, lien externe, citation, et le post cité d'une citation) donne, dans le dossier `texts/`, deux fichiers de même nom de base (`<handle>_<AAAAMMJJ>_<postid>`, ou `<base>_quote` pour un post cité) :

**`<base>.txt`** : version lisible. Les liens du texte affichent leur URL réelle (`libellé (https://url)`, au lieu du libellé tronqué par Bluesky), les mentions restent en `@handle` et les tags en `#tag` :

```
Post: https://bsky.app/profile/auteur.example.com/post/3kabc
Date: 2026-02-03T09:08:07.123Z
Auteur: auteur.example.com
Langue: fr, en

Voir libidex.example/article-tres-lo... (https://libidex.example/article-tres-long-titre) avec @alice.example.com

[Image 1 : texte alternatif de la première image]
[Image 2 : …]

Lien: https://exemple.org/page        (carte de lien, si le post en a une)
Titre: …
Description: …

Cite: at://did:plc:…/app.bsky.feed.post/3kcite
Réponse à: at://did:plc:…/app.bsky.feed.post/3kparent
```

Les lignes `Langue`, `[Image N : …]` / `[Vidéo : …]` (seulement si le texte alternatif n'est pas vide), `Lien/Titre/Description`, `Cite` et `Réponse à` n'apparaissent que lorsqu'elles s'appliquent. Un fichier déjà présent au même contenu n'est pas réécrit. Si tous les médias propres d'un post échouent, son texte n'est pas archivé tant que le post (statut `failed`) n'est pas retenté avec succès. Le texte alternatif des images est aussi écrit dans le champ EXIF `ImageDescription` (si `exiftool` est installé).

**`<base>.json`** : la fiche (« sidecar »), archive fidèle du post, désactivable avec `save_sidecar: false` :

```json
{
  "url": "https://bsky.app/profile/auteur.example.com/post/3kabc",
  "at_uri": "at://did:plc:…/app.bsky.feed.post/3kabc",
  "archived_at": "2026-10-13T20:15:00+00:00",
  "bsmb_version": "3.1.0",
  "record": { "…": "record brut du post : text, facets, langs, embed, reply, createdAt…" },
  "post_view": { "…": "postView hydraté (auteur, labels, embed) ou null" }
}
```

`post_view` n'est renseigné que lorsque la vue vient du cache `bookmarks.json` (synchronisation récente) ; en mode dev il vaut `null`. La fiche est réécrite à chaque retraitement. Elle est enregistrée en base avec le type `sidecar` et comptée à part (ligne « Fiches JSON » du rapport). Les index `byteStart` / `byteEnd` des facets sont des octets UTF-8, pas des caractères.

---

## Architecture technique

Ce schéma est **le seul** du dépôt : `DEVELOPMENT.md` et `CONTRIBUTING.md` y renvoient. Toute modification de structure doit être répercutée ici.

```
bsmb/
├── bsmb.py                      # Point d'entrée : menu TUI + sous-commandes (--version, sync, download, run, status)
├── Start.bat / start.sh         # Lanceurs Windows / Linux-macOS (venv + dépendances + ffmpeg/exiftool)
├── pyproject.toml               # Paquet installable (pipx) : commande `bsmb`, dépendance requests
├── requirements*.txt            # Exécution / optionnel (keyring) / développement (pytest, ruff)
│
├── core/                        # Logique métier
│   ├── auth.py                 # createSession + refreshSession + get_session / get_token
│   ├── bookmarks.py            # BookmarkSync (pont API ↔ DB, renouvellement du token)
│   ├── bookmarks_cache.py      # Cache bookmarks.json (postView bruts)
│   ├── cli.py                  # Sous-commandes non interactives et codes de retour
│   ├── colors.py               # Couleurs ANSI cross-platform
│   ├── config.py               # Configuration JSON + migration + resolve_path
│   ├── database.py             # SQLite (posts + media + meta, migrations)
│   ├── http.py                 # Session HTTP partagée (reprises, limiteur de débit)
│   ├── i18n.py                 # _(), _n(), init() : traductions gettext (catalogues dans lang/)
│   ├── orchestrator.py         # run() : ThreadPoolExecutor, logs, rapport
│   ├── paths.py                # PROJECT_ROOT (racine des chemins relatifs)
│   ├── post_ref.py             # Identité d'un post : AT-URI (DID + rkey)
│   ├── secret_store.py         # App Password : keyring, repli config.json
│   ├── ui.py                   # Mode (non) interactif : confirm(), pause(), --yes
│   └── version.py              # __version__ (source unique)
│
├── api/                         # Interactions API Bluesky
│   ├── export_bookmarks.py     # fetch_bookmarks() + mode autonome
│   ├── post_analyzer.py        # Détection du type de post (image/vidéo/texte/lien/citation)
│   └── quote_resolver.py       # QuoteResolver : record cité par une citation
│
├── downloaders/                 # Téléchargeurs (fonctions importables)
│   ├── __init__.py             # DownloadResult, DownloadError
│   ├── images.py               # download_images() : images avec EXIF
│   ├── videos.py               # download_video() : vidéos avec ffmpeg, sous-titres
│   ├── text.py                 # save_text() : texte seul
│   ├── archive.py              # write_text() / write_sidecar() : .txt lisible et fiche JSON
│   └── external.py             # download_external() : cartes de lien, GIF Tenor
│
├── tests/                       # Tests (pytest, aucun accès réseau) ; fixtures/ : réponses d'API réelles
├── .github/                     # CI (ruff, tests 3.11-3.14, couverture), Dependabot, modèles d'issues
└── logs/                        # Fichiers de log (créé automatiquement, ignoré par Git)
```

### Flux de données

```
bsmb.py (menu ou sous-commande → core/cli.py)
  → core/auth.py (createSession → Bearer token)
  → core/bookmarks.py (sync: API → urls.txt + bookmarks.json → compare DB)
  → core/orchestrator.run() (appel direct, ThreadPoolExecutor)
    → api/post_analyzer.py (détecte le type ; sans requête si le postView est en cache)
    → api/quote_resolver.py (résout le post cité d'une citation, profondeur max 2)
    → downloaders/*.py (fonctions appelées dans les threads : téléchargent,
                        renvoient des DownloadResult)
    → core/database.py (suivi SQLite)
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

## Réseau

Tous les appels HTTP passent par une session unique (`core/http.py`, `get_session()`), partagée par les workers :

- **User-Agent** : `BSMB/<version> (+https://github.com/Gotcha26/Bluesky-Save-My-Bookmarks)`, pour que Bluesky puisse identifier l'outil.
- **Reprises automatiques** : jusqu'à 4 reprises, avec délai croissant (backoff exponentiel), sur les erreurs de connexion et les réponses 429, 500, 502, 503, 504. L'en-tête `Retry-After` est respecté, borné à 300 s.
- **Limiteur de débit** : au plus 8 requêtes en vol en même temps, quel que soit `max_workers`. Quand `RateLimit-Remaining` passe sous 50, les appels suivants attendent `RateLimit-Reset` (pause de 300 s maximum, une ligne est écrite dans le journal `bsmb.http`).
- **`error_429`** : si la limite de débit est encore atteinte après les reprises, le post reçoit le statut `error_429` (rapport « Limite de débit (429) », fichier `logs/rate_limited_*.txt`, code de sortie 3 en ligne de commande). Il est retenté comme `error_500`, après `retry_after_days` jours.
- **Token expiré** : si `getBookmarks` répond `ExpiredToken` pendant la synchronisation (le token d'accès dure environ 2 h) et que la connexion se fait par App Password, BSMB le renouvelle une fois (`refreshSession`) et reprend. Avec un `Token-Bearer.txt` manuel, il n'y a pas de jeton de rafraîchissement : il faut un nouveau token.
- **Version** : `python bsmb.py --version` ; la valeur vient de `core/version.py`.

---

## Planification

BSMB s'utilise sans menu, pour une tâche planifiée ou un script :

```
python bsmb.py sync                 # synchronise les bookmarks
python bsmb.py download [--force]   # télécharge les nouveaux posts
python bsmb.py run --yes            # sync puis download, sans aucune question
python bsmb.py status [--json]      # état du compte et compteurs
```

Sans sous-commande, le menu interactif s'ouvre. Quand l'entrée standard n'est pas un terminal (tâche planifiée, cron, pipe) ou avec `--yes`, BSMB ne pose aucune question : les confirmations prennent leur valeur par défaut, « Appuyez sur Entrée » disparaît, et la sortie est sans couleur si elle est redirigée. `--yes` s'écrit avant ou après la sous-commande. `--lang {fr,en,auto}` (aussi avant ou après) choisit la langue de l'interface et l'emporte sur `language` de `config.json`.

Codes de retour :

| Code | Signification |
|------|---------------|
| `0` | Succès |
| `1` | Erreur d'authentification (aucun identifiant, identifiants refusés, token expiré) |
| `2` | Erreur réseau (connexion, timeout, HTTP 5xx) à l'authentification ou pendant la synchronisation. C'est aussi le code d'`argparse` pour un argument invalide |
| `3` | Au moins un téléchargement en échec (ou erreur 500) |
| `4` | Erreur interne (exception inattendue) : message en console, trace complète sur la sortie d'erreur |

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
  "index_digits": 2,
  "save_sidecar": true,
  "bsky_handle": "monpseudo.bsky.social",
  "bsky_app_password": "xxxx-xxxx-xxxx-xxxx",
  "pds_url": "https://morel.us-east.host.bsky.network",
  "max_workers": 4,
  "last_sync": "2026-02-08T14:30:00",
  "advanced_mode": false,
  "language": ""
}
```

| Clé | Description | Défaut |
|-----|-------------|--------|
| `download_dir` | Dossier racine des téléchargements | `~/Downloads/BSMB` |
| `token_file` | Fichier token Bearer (fallback) | `Token-Bearer.txt` |
| `urls_file` | Liste des bookmarks exportés | `urls.txt` |
| `bookmarks_cache` | Dernière réponse `getBookmarks` (`postView` bruts, évite un `getRecord` par post ; absent en mode dev). Il contient le **texte complet** de vos posts en favori (donnée personnelle) : `bookmarks.json` est ignoré par Git, mais un autre nom doit être ajouté au `.gitignore` par vos soins | `bookmarks.json` |
| `db_file` | Base de données SQLite | `bsmb.db` |
| `logs_dir` | Dossier des logs | `logs` |
| `pds_url` | PDS du compte, détecté à la connexion (`""` = inconnu, `https://bsky.social` utilisé) | `""` |
| `max_workers` | Workers parallèles | `4` |
| `retry_after_days` | Délai avant de retenter un post en erreur (`error_500`, `error_429`, `unknown`, `failed`, `repost` hérité) | `7` |
| `last_sync` | Date de dernière synchronisation | `""` |
| `advanced_mode` | Mode avancé activé | `false` |
| `open_folder_after_download` | Propose d'ouvrir le dossier après un téléchargement (ignoré en non interactif) | `true` |
| `max_filename_len` | Longueur max des noms de fichiers | `64` |
| `min_postid_short` | Longueur min de l'ID du post dans un nom d'image tronqué | `4` |
| `index_digits` | Nombre de chiffres de l'index d'image (`_1`, `_01`…). Les fichiers déjà téléchargés ne sont pas renommés | `2` |
| `save_sidecar` | Écrit `texts/<nom>.json` (fiche JSON, voir « Archive d'un post ») pour chaque post archivé | `true` |
| `language` | Langue de l'interface : `"fr"`, `"en"` ou `""` (automatique, d'après la locale du système). Modifiable dans **Paramètres** > **L. Langue** ; l'option `--lang` de la ligne de commande l'emporte. Voir `lang/README.md` | `""` |
| `max_logs` | Nombre max de logs `download_*.log` conservés | `5` |
| `image_quality` | `"original"` : blob d'origine (`com.atproto.sync.getBlob` via `https://bsky.social`, qui redirige vers le PDS de l'auteur ; repli automatique sur le CDN en cas d'échec) ; `"cdn"` : image `fullsize` du CDN Bluesky (recompressée) | `"original"` |
| `skip_existing_cid` | Ne pas retélécharger une image dont le `cid` est déjà en base avec un fichier présent sur disque (ligne `[SKIP]`) | `true` |
| `gif_subfolder` | Les GIF publiés depuis le client (vidéos `presentation: "gif"`) reçoivent par défaut le suffixe `_gif` (`..._01_gif.mp4`) ; à `true`, ils sont rangés dans `videos/gifs/` (sans suffixe) | `false` |
| `download_video_thumbnail` | Télécharge aussi la miniature de la vidéo (`..._01_thumb.jpg`, comptée comme image) quand la vue hydratée du post est connue (cache `bookmarks.json`) | `false` |

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
| `status` | TEXT | `ok`, `deleted`, `blocked`, `error_500`, `error_429`, `unknown`, `failed` (`repost` : ancien statut des citations non résolues, plus écrit, encore retenté) |
| `at_uri` | TEXT (UNIQUE) | Identité canonique `at://<did>/app.bsky.feed.post/<rkey>` (NULL pour les anciennes lignes, complété au prochain traitement) |
| `did` | TEXT | DID de l'auteur |
| `rkey` | TEXT | Clé du post |

### Table `media`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | INTEGER (PK) | Auto-incrémenté |
| `post_url` | TEXT (FK) | Référence vers posts.url (`ON DELETE CASCADE`) |
| `media_type` | TEXT | `image`, `video`, `subtitle`, `text`, `sidecar` (fiche JSON) |
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
| `ImageDescription` | Texte alternatif de l'image (si le post en fournit un) |

### Vidéos (ffmpeg)

| Tag | Contenu |
|-----|---------|
| `title` | ID du post Bluesky |
| `comment` | Texte du post + URL complète |
| `artist` | Handle de l'auteur |
| `creation_time` | Date de création du post |
| `description` | Texte alternatif (`alt`) de la vidéo, s'il existe |

**Vidéos : limites et comportements.** Bluesky accepte désormais des vidéos de 10 minutes et 300 Mo : le téléchargement utilise un délai de connexion de 10 s et de lecture de 300 s, et écrit dans un fichier `.part` renommé seulement une fois la réponse complète et valide (jamais de `.mp4` tronqué). L'extension suit le `mimeType` du blob (`.mp4`, `.webm`, `.mov`).

- **Sous-titres** : chaque fichier de `captions` est enregistré à côté de la vidéo en `<nom_video>.<lang>.vtt` (ex. `..._01.fr.vtt`). Un sous-titre en échec est journalisé sans faire échouer la vidéo. Ils ne sont pas incrustés dans le MP4.
- **Repli HLS** : si `getBlob` échoue (blob purgé, PDS indisponible) et que la playlist HLS est connue (vue hydratée du post, cache `bookmarks.json`), la vidéo est reconstruite avec `ffmpeg -i <playlist> -c copy` (résultat en `.mp4`). Sans ffmpeg ou sans playlist, le téléchargement échoue.

---

## Tests

```bash
# Lancer tous les tests
python -m pytest tests/ -v

# Lancer un fichier spécifique
python -m pytest tests/test_database.py -v
```

Les tests n'effectuent jamais d'appel réseau (la session HTTP est remplacée par un faux, les réponses d'API réelles sont dans `tests/fixtures/`). Ils couvrent l'ensemble des modules : configuration, base de données et migrations, authentification, réseau, analyse des posts, citations, téléchargeurs, orchestrateur, CLI, stockage du secret. La CI (`.github/workflows/ci.yml`) exécute ruff puis la suite sur Python 3.11 à 3.14 (Ubuntu et Windows) avec un seuil de couverture de 70 %. Voir [CONTRIBUTING.md](CONTRIBUTING.md) pour le détail.

---

## Dépannage avancé

### Erreurs d'authentification

**"Identifiants invalides"** — Vérifiez handle et App Password. Recréez l'App Password si nécessaire.

**"Trop de tentatives"** — Rate limit atteint. Attendez quelques minutes.

**"Impossible de se connecter"** — Vérifiez votre connexion Internet et que bsky.social est accessible.

### Erreurs de téléchargement

**"ffmpeg/exiftool introuvable"** — Les médias seront téléchargés sans métadonnées. Installez-les pour les avoir.

**"Erreur SQLite"** — Réinitialisez la DB via Stockage local > Réinitialiser, ou supprimez `bsmb.db` manuellement.

**"Aucun média trouvé" alors que le post en contient** — Consultez `logs/quotes_unresolved_*.txt` (citation dont le post cité n'a pas pu être archivé), `logs/unknown_types_*.txt` (type d'embed non géré : ouvrez une issue) et `logs/download_*.log` (détail de la session).

**Beaucoup de posts « trackés » mais peu de médias** — Normal : un post est enregistré dès qu'il est traité, même sans média (texte seul, supprimé, bloqué, erreur). Les fichiers `logs/deleted_posts_*.txt`, `failed_downloads_*.txt`, `error_500_*.txt` et `rate_limited_*.txt` expliquent chaque cas.

### Couleurs

**Les couleurs ne s'affichent pas** — Essayez Windows Terminal au lieu de CMD. Variables : `NO_COLOR=1` (désactiver) ou `FORCE_COLOR=1` (forcer).

---

## Contribuer

Consultez [CONTRIBUTING.md](CONTRIBUTING.md) pour les guidelines de développement.

Consultez [DEVELOPMENT.md](DEVELOPMENT.md) pour le détail des modules (le schéma d'architecture reste celui de ce guide).
