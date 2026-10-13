# Guide de développement

Ce document explique les mécanismes internes de BSMB : ce qu'il faut savoir avant de modifier le code. Pour l'**arborescence et le flux de données**, voir [ADVANCED.md](ADVANCED.md#architecture-technique) : c'est le seul schéma d'architecture du dépôt, il n'est pas répété ici. Pour les règles de contribution (branches, commits, PR), voir [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Vue d'ensemble

Le flux a deux temps, pilotés par le menu de `bsmb.py` ou par les sous-commandes de `core/cli.py` :

1. **Synchronisation** : `core/bookmarks.py` (`BookmarkSync.sync`) appelle `api/export_bookmarks.fetch_bookmarks()` (importé, aucun sous-processus). Les URLs vont dans `urls.txt`, la réponse complète (`postView` bruts) dans `bookmarks.json` (`core/bookmarks_cache.py`), et les posts inconnus de la base sont comptés comme « nouveaux ».
2. **Téléchargement** : `core.orchestrator.run(urls, config, no_db=False, on_progress=None, quiet=False, post_views=None)` traite les posts dans un `ThreadPoolExecutor` et renvoie un dict de statistiques. Chaque worker exécute `process_post()` : analyse du type par `PostAnalyzer`, puis appel direct de la fonction du téléchargeur adapté.

Seuls `exiftool` et `ffmpeg` sont lancés en sous-processus.

---

## Authentification (`core/auth.py`)

| Fonction | Rôle |
|----------|------|
| `create_session(handle, app_password, session=None)` | `com.atproto.server.createSession` ; renvoie `{"token": "Bearer …", "refresh_jwt", "did", "pds_url"}` |
| `refresh_session(refresh_jwt, pds_url, session=None)` | `refreshSession` : nouveau token (et nouveau jeton de rafraîchissement) |
| `get_session(config)` | `createSession` si handle + App Password, sinon lecture de `Token-Bearer.txt` (doit commencer par `Bearer `), sinon `None` |
| `get_token(config)` | `get_session(config)["token"]` ou `None` |
| `has_credentials(config)` | handle et App Password présents |

Erreurs : `AuthError` (identifiants refusés, trop de tentatives) et sa sous-classe `NetworkError` (connexion, délai, HTTP 5xx). `core/cli.py` les traduit en codes de retour 1 et 2.

Le **token ne sert qu'à `getBookmarks`**. Tous les autres appels (`getRecord`, `getPostThread`, `getBlob`, `getProfile`) sont publics. Quand `getBookmarks` répond `ExpiredToken`, `BookmarkSync.sync(..., session_info=)` renouvelle le token une fois par `refresh_session`.

L'App Password est géré par `core/secret_store.py` : `keyring` (service `bsmb`, handle comme nom d'utilisateur) si la bibliothèque optionnelle est installée, sinon `config.json`. Il n'est jamais journalisé ni affiché.

---

## Configuration et chemins (`core/config.py`, `core/paths.py`)

- `DEFAULT_CONFIG` est fusionné avec `config.json` par `load_config()` (clés inconnues conservées, ancienne paire `img_dir`/`vid_dir` migrée vers `download_dir`). Les clés et leurs défauts sont documentés dans [ADVANCED.md](ADVANCED.md#configuration-avancée-configjson).
- Les chemins relatifs sont **ancrés sur `PROJECT_ROOT`** (le dossier de `bsmb.py`, `core/paths.py`), pas sur le dossier courant. Toujours passer par `resolve_path(config, "db_file")` (idem `urls_file`, `logs_dir`, `token_file`), jamais `Path(config["…"])`.
- `get_media_dirs(config)` donne `img_dir`, `vid_dir`, `text_dir` sous `download_dir`.
- `save_config()` restreint les droits de `config.json` (`chmod 600` sous POSIX).
- `cleanup_old_logs()` supprime les logs de plus de 10 jours et ne garde que `max_logs` fichiers `download_*.log`.

---

## Base de données (`core/database.py`)

Le schéma (tables `posts`, `media`, `meta`) et les migrations sont décrits dans [ADVANCED.md](ADVANCED.md#base-de-données-sqlite). Points à connaître :

- `posts.url` est la clé primaire ; l'identité canonique est `at_uri` (UNIQUE) : un changement de handle met la ligne à jour au lieu de créer un doublon.
- `status` : `ok`, `deleted`, `blocked` (jamais retenté), `error_500`, `error_429`, `unknown` ; `repost` est un ancien statut, plus écrit mais encore retenté.
- `get_pending_posts(urls, retry_after_days=7)` renvoie les URLs jamais vues plus les posts `error_500` / `error_429` / `unknown` / `repost` vérifiés il y a plus de `retry_after_days` jours.
- `add_post()` rafraîchit sans écraser `added_at` ni `status` ; `add_media()` ignore les doublons (`INSERT OR IGNORE`, `media.filename` unique par post).
- Les migrations sont des méthodes `_migrate_vN` numérotées, appliquées dans l'ordre d'après `meta.schema_version`.
- Une seule connexion est partagée entre les threads (`check_same_thread=False` + `threading.Lock` sur chaque méthode) ; appeler `db.close()` à la fin.

---

## Analyse des posts (`api/post_analyzer.py`)

```python
analyzer = PostAnalyzer(session=None)
post_type, data, debug_info = analyzer.analyze(url, post_view=None)
```

`PostType` : `IMAGES`, `VIDEO`, `TEXT_ONLY`, `EXTERNAL` (carte de lien, GIF), `QUOTE`, `ERROR_400` (post supprimé), `ERROR_429`, `ERROR_500`, `UNKNOWN` (`REPOST` n'est qu'un alias déprécié de `QUOTE`).

Sans `post_view`, un `getRecord` par post (sur `bsky.social`, record brut, embeds `app.bsky.embed.*`). Avec le `postView` du cache `bookmarks.json`, aucune requête : `data["view_embed"]` porte alors l'embed au format `#view`.

Piège : **deux formats d'embed coexistent**. L'analyseur lit le record brut (`app.bsky.embed.images`), les téléchargeurs relisent la vue hydratée via `getPostThread` sur `public.api.bsky.app` (`app.bsky.embed.images#view`). Ne pas les confondre.

**Citations.** Une citation (`app.bsky.embed.record`) garde le type de son média éventuel (`recordWithMedia`) avec `data["is_quote"] = True`. `process_post()` archive d'abord le post citant selon son propre contenu, puis, via `QuoteResolver.resolve()` (`api/quote_resolver.py`), le post cité avec les mêmes téléchargeurs et un `name_prefix` (`<citant>_<date>_<rkey>_quote_<n>`). Profondeur maximale `PROFONDEUR_MAX` = 2. Un cité supprimé, bloqué ou qui n'est pas un post est ignoré avec une note ; une erreur réseau donne `CITATION NON ARCHIVÉE` dans le log et `quotes_unresolved_*.txt`.

---

## Orchestrateur (`core/orchestrator.py`)

`run()` accepte aussi une utilisation en script : `python core/orchestrator.py <img_dir> <vid_dir> <text_dir> [--no-db] <url1> [url2...]`.

Il renvoie un dict : `total`, `success`, `images`, `videos`, `texts`, `sidecars` et des listes d'URLs `error_500`, `error_429`, `error_400`, `quotes_unresolved`, `unknown`, `failed`. À la fin, il écrit un fichier par catégorie non vide dans `logs/` (`deleted_posts_*.txt`, `quotes_unresolved_*.txt`, `error_500_*.txt`, `rate_limited_*.txt`, `unknown_types_*.txt`, `failed_downloads_*.txt`) et un `download_*.log` détaillé.

`process_post()` suit cet ordre pour un post :

1. `analyze()` puis `db.add_post()` ;
2. statuts d'erreur (400 → `deleted`, 500, 429, inconnu) : enregistrés et retournés ;
3. contenu propre du post (`_contenu_propre`) : images, vidéo, lien externe ou texte, puis `.txt` lisible et fiche JSON de tout post (`_archiver_post`, `downloaders/archive.py`) ;
4. post cité si c'est une citation (`_archiver_citation`) ;
5. `add_media()` pour chaque `DownloadResult`, puis statut `ok`.

Règles :
- Une exception est isolée au post (journalisée, statut `failed`) : un post en échec n'arrête jamais le lot.
- Les compteurs sont mis à jour par le seul thread principal (`as_completed`).
- Un échec technique (`DownloadError`) donne `failed`. Le post reçoit le statut `failed` en base et est retenté automatiquement après `retry_after_days` jours ; les fichiers déjà obtenus (échec partiel, `DownloadError.partial`) sont enregistrés.

---

## Téléchargeurs (`downloaders/`)

Fonctions importables. Les trois principales partagent le même début de signature (le reste est facultatif : `record`, `existing_cid`, `view_embed`, `did`…) :

```python
download_images(post_url, dest_dir, config, session=None, name_prefix=None, ...)  # images.py
download_video(post_url, dest_dir, config, session=None, name_prefix=None, ...)   # videos.py
save_text(post_url, dest_dir, config, session=None, name_prefix=None)             # text.py
```

`download_external(post_url, data, dirs, config, session=None)` (`external.py`) reçoit en plus le dict `data` de l'analyseur et les trois dossiers médias.

Chacune renvoie une `list[DownloadResult]` (`filename`, `path`, `media_type`, `size`, `cid`, `skipped`, `alt`) ; liste vide = aucun média ; `DownloadError` = erreur technique (son attribut `partial` porte les résultats déjà écrits en cas d'échec partiel, par exemple 2 images sur 3). Les téléchargeurs **n'impriment rien** : les lignes `[DL]` / `[OK]` / `[TXT]` viennent de `lignes_console()`. Chaque module reste utilisable seul pour déboguer un post :

```bash
python downloaders/images.py <dossier> <url_post>
python downloaders/videos.py <dossier> <url_post>
python downloaders/text.py <dossier> <url_post>
```

Les métadonnées (EXIF via `exiftool`, tags ffmpeg) sont décrites dans [ADVANCED.md](ADVANCED.md#métadonnées) ; leur absence ne fait jamais échouer un téléchargement. L'archive fidèle (`write_text`, `write_sidecar`) est dans `downloaders/archive.py`.

**Aucun code au niveau module** dans les téléchargeurs et l'orchestrateur : `tests/test_imports.py` importe chaque module dans un interpréteur neuf et échoue sur toute sortie, `input()` ou fichier créé. Le `sys.path.insert` des scripts n'a lieu qu'en exécution directe (`__package__` vide). Tout nouveau module doit être ajouté à la liste `MODULES` de ce test.

---

## Réseau (`core/http.py`)

Tous les appels HTTP passent par `get_session()` : une session partagée (User-Agent BSMB, reprises sur 429/5xx, limiteur de débit). Les modules font :

```python
from core import http as bsmb_http

session = bsmb_http.get_session()
```

jamais `from core.http import get_session` (les tests ne pourraient plus le remplacer). `session=None` reste accepté partout. Ne jamais appeler `requests.get/post/Session` ailleurs : `tests/test_session_partagee.py` le vérifie. Détails du comportement dans [ADVANCED.md](ADVANCED.md#réseau).

---

## Interface (`bsmb.py`, `core/colors.py`, `core/ui.py`, `core/cli.py`)

- `bsmb.py` contient les menus (Mon compte, Stockage local, Paramètres, Télécharger) ; `main()` renvoie un code de retour, dirige les sous-commandes vers `core/cli.py` et ouvre le menu sinon. L'en-tête affiche la version (`core/version.py`, source unique lue aussi par `pyproject.toml`).
- `core/colors.py` expose l'instance globale `c` (détection ANSI, variables `NO_COLOR` et `FORCE_COLOR`). Style « menu-generator » : `c.box_header()`, `c.menu_option()`, `c.config_line()`, `c.success()` / `error()` / `warning()` / `info()`.
- `core/ui.py` : `confirm(question, default)` et `pause()`. En mode non interactif (entrée standard redirigée ou `--yes`), `confirm` renvoie sa valeur par défaut et `pause` ne fait rien. Ne jamais appeler `input()` directement pour une confirmation.
- Sous Windows, `bsmb.py` ré-encapsule stdout en UTF-8 uniquement sous `__name__ == "__main__"` (sinon conflit avec la capture de pytest).
- Convention d'interface : `0` = retour, ENTRÉE = garder la valeur courante, confirmations `[O/n]`.

---

## Tests

Les tests ne font **aucun accès réseau** : la fixture autouse `fake_session` de `tests/conftest.py` remplace `get_session()` par un `MagicMock` (raccourcis `mock_get` / `mock_post` ; `GET_SESSION_REEL` pour la vraie fonction), et une barrière réseau fait échouer toute connexion vers un hôte externe. `keyring` est neutralisé et le terminal simulé interactif. Fixtures utiles : `tmp_config`, `tmp_db`, `sample_post_url`. Les réponses d'API réelles sont dans `tests/fixtures/` (JSON).

```python
from api.post_analyzer import PostAnalyzer, PostType


def test_post_supprime(fake_session):
    fake_session.get.return_value.status_code = 400
    url = "https://bsky.app/profile/a.example.com/post/3kabc"
    assert PostAnalyzer().analyze(url)[0] == PostType.ERROR_400
```

Commandes et exigences de la CI : voir [CONTRIBUTING.md](CONTRIBUTING.md#tests).

---

## Gestion d'erreurs

- Par post, jamais globale : un échec est journalisé et le lot continue.
- Statuts distincts pour ce qui est définitif (`deleted`, `blocked`) et ce qui est temporaire (`error_500`, `error_429`).
- Un média ou un sous-titre secondaire en échec est journalisé sans faire échouer le post.
- Les fichiers de `logs/` sont décrits dans la section Orchestrateur ci-dessus.

---

## Débogage

- Un post isolé : `python downloaders/images.py <dossier> <url>` (idem `videos.py`, `text.py`), ou `python core/orchestrator.py … --no-db <url>` pour le traitement complet sans écrire en base.
- Le **Mode dev** (Paramètres > Mode avancé) traite `urls.txt` sans token ni base.
- Un type de post non reconnu écrit un fichier de débogage dans `logs/` (nom indiqué dans le log) et la liste `unknown_types_*.txt`.
- `python bsmb.py status --json` donne l'état du compte et des compteurs sans appel réseau ; à joindre aux rapports de bug avec `python bsmb.py --version`.

---

## Ressources

- [Bluesky AT Protocol](https://atproto.com)
- [Python requests](https://requests.readthedocs.io/)
- [SQLite](https://www.sqlite.org/)
- [ExifTool](https://exiftool.org/)
- [ffmpeg](https://ffmpeg.org/)
