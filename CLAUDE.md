# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projet

BSMB (Bsky Save My Bookmarks) : outil Python en ligne de commande (menu TUI) qui récupère les bookmarks d'un compte Bluesky via l'API AT Protocol et archive localement images, vidéos et textes des posts. Seule dépendance externe : `requests`. Outils optionnels : `exiftool` (EXIF images) et `ffmpeg` (métadonnées vidéo). Toute l'interface, la documentation et les commits sont en **français** (voir « Conventions »).

## Commandes

```bash
pip install -r requirements.txt          # dépendances
python bsmb.py                           # lance le menu (depuis la racine du dépôt, obligatoire)
python -m pytest tests/ -q               # suite complète (aucun accès réseau)
python -m pytest tests/test_database.py -v
python -m pytest tests/test_auth.py -k "expired"   # un test / un motif
python -m compileall -q -x '[/\\]\.git[/\\]' .     # syntaxe (job `lint` de la CI, .github/workflows/ci.yml)
ruff check . && ruff format --check .    # lint + formatage (job `lint` ; `ruff format .` pour corriger)
python -m pytest tests/ --cov=core --cov=api --cov=downloaders --cov-report=term-missing --cov-fail-under=70  # couverture (CI)
```

`pytest` et `ruff` sont dans `requirements-dev.txt` : `pip install -r requirements-dev.txt` au préalable. Sur ce poste, `python` est la 3.14 ; la CI tourne sur 3.11 à 3.14 (Ubuntu + Windows).

Scripts utilisables seuls pour déboguer un post :

```bash
python downloaders/images.py <dossier> <url_post>
python downloaders/videos.py <dossier> <url_post>
python downloaders/text.py <dossier> <url_post>
python core/orchestrator.py <img_dir> <vid_dir> <text_dir> [--no-db] <url1> [url2...]
python api/export_bookmarks.py           # lit BSMB_TOKEN ou Token-Bearer.txt, écrit urls.txt
```

## Architecture

Le flux est en deux temps, piloté par le menu de `bsmb.py` :

1. **Synchronisation** (`core/bookmarks.py` → `api/export_bookmarks.py`) : `createSession` donne un token (`core/auth.py` ; envoyé au PDS du compte trouvé par `resolve_pds` : handle → DID → document DID, repli `bsky.social`), `getBookmarks` est paginé, les URLs `https://bsky.app/profile/<handle>/post/<rkey>` sont écrites dans `urls.txt` (et la réponse complète, `postView` bruts compris, dans `bookmarks.json` via `core/bookmarks_cache.py`) et comparées à la table `posts` pour compter les « nouveaux ». `core/bookmarks.run_sync` est la synchronisation commune au menu et à la CLI ; `core/bookmarks.pending_downloads(config, db)` est la source unique des posts à télécharger (par AT-URI depuis le cache, sinon par URL depuis `urls.txt`), utilisée par le téléchargement et les compteurs « Nouveaux ».
2. **Téléchargement** : `bsmb.py` appelle directement `core.orchestrator.run(urls, config, no_db=False, on_progress=None, quiet=False)`, qui renvoie un dict de statistiques et écrit les logs. L'orchestrateur utilise un `ThreadPoolExecutor` (`max_workers` de la config) ; chaque worker appelle `PostAnalyzer.analyze(url, post_view=None)` (`api/post_analyzer.py` ; un `getRecord` par post, sauf si `run(..., post_views=)` fournit le `postView` du cache : aucune requête, `data["view_embed"]` porte alors l'embed `#view`) qui renvoie un `PostType`, puis la fonction du downloader : `download_images()`, `download_video()` ou `save_text()` (signature `(post_url, dest_dir, config, session=None, name_prefix=None)`). Chacune renvoie une `list[DownloadResult]` (`downloaders/__init__.py` : `filename`, `path`, `media_type`, `size`, `cid`) ; liste vide = aucun média, `DownloadError` = erreur technique (statut `failed` ; `partial` porte les résultats d'un échec partiel, enregistrés en base). Comptage et `add_media` viennent de ces résultats ; les downloaders n'impriment rien, les lignes `[DL]`/`[OK]`/`[TXT]` sont produites par `lignes_console()`.

Points qui ne se voient pas en lisant un seul fichier :

- **Archive fidèle** (`downloaders/archive.py`) : `write_text(post_url, record, dest_dir, config, name_prefix=None, alts=None)` écrit le `.txt` lisible de **tout** post (facets résolues via `resolve_facets`, index en octets UTF-8 ; alt, carte de lien, `Cite:`, `Réponse à:`) et `write_sidecar(...)` la fiche `.json` (record brut + `postView` ou null ; désactivable par `save_sidecar`). `save_text` et `download_external` y délèguent ; l'orchestrateur (`_archiver_post`, depuis le record de `debug_info["full_data"]`) les appelle pour les autres types. Résultats `media_type` `text` / `sidecar`.

- **Réseau** (`core/http.py`, issue #11) : tous les appels passent par `get_session()` (session partagée : User-Agent BSMB, `Retry` sur 429/5xx, `RateLimiter` : 8 requêtes simultanées max et pause jusqu'à `RateLimit-Reset` sous 50 restantes). Les modules font `from core import http as bsmb_http` et appellent `bsmb_http.get_session()` à l'usage (jamais `from core.http import get_session`, sinon les tests ne peuvent plus le patcher) ; `session=None` reste accepté partout. Ne jamais appeler `requests.get/post/Session` ailleurs (`tests/test_session_partagee.py` le vérifie). La fixture **autouse** `fake_session` de `tests/conftest.py` remplace `get_session()` par un `MagicMock` : aucun test ne touche le réseau (raccourcis `mock_get` / `mock_post` ; `GET_SESSION_REEL` pour la vraie fonction). Une 429 finale donne `PostType.ERROR_429` → statut `error_429` (retenté). `core/auth.refresh_session` + `BookmarkSync.sync(..., session_info=)` renouvellent le token une fois sur `ExpiredToken`. La version vit dans `core/version.py` (`pyproject.toml` la lit en dynamique).
- **Chemins ancrés sur `PROJECT_ROOT`** (`core/paths.py`, dossier de `bsmb.py`) : `CONFIG_FILE` y est fixé, et `resolve_path(config, key)` résout `db_file`, `urls_file`, `logs_dir`, `token_file` quand ils sont relatifs. Toujours passer par `resolve_path`, jamais `Path(config["…"])`. `config.json` garde les valeurs relatives. Les dossiers médias viennent de `get_media_dirs(config)` (`download_dir`).
- **Aucun code au niveau module** dans les downloaders et l'orchestrateur : `tests/test_imports.py` importe chaque module dans un interpréteur neuf et échoue sur toute sortie, `input()` ou fichier créé. Le `sys.path.insert` des scripts n'a lieu qu'en exécution directe (`__package__` vide). Seuls `exiftool` et `ffmpeg` sont lancés en sous-processus.
- **Le token ne sert qu'à `getBookmarks`**. `BookmarkSync.sync` le passe directement à `fetch_bookmarks()` (la variable `BSMB_TOKEN` ne sert qu'au script `api/export_bookmarks.py` lancé seul). Tous les autres appels (`getRecord`, `getPostThread`, `getBlob`, `getProfile`) sont publics, sans authentification.
- **Deux lectures API par post** : l'analyseur lit `com.atproto.repo.getRecord` sur `bsky.social` (record brut, embeds `app.bsky.embed.*`), les downloaders relisent `app.bsky.feed.getPostThread` sur `public.api.bsky.app` (vue hydratée, embeds `*#view`). Les deux formats d'embed coexistent donc dans le code ; ne pas les confondre.
- **`PostType.QUOTE` = citation (quote post, `app.bsky.embed.record`)** ; `REPOST` n'en est qu'un alias déprécié (un vrai repost n'est jamais bookmarké). Une citation avec média (`recordWithMedia`) garde son type média (`IMAGES`/`VIDEO`/`EXTERNAL`) et `data["is_quote"] = True`. `process_post()` archive d'abord le post citant selon son propre contenu (texte, média), puis, via `api/quote_resolver.py` (`QuoteResolver.resolve() -> QuoteTarget | None`), le post cité, avec les downloaders et `name_prefix` : fichiers `<citant>_<date>_<rkey>_quote_<n>` (`_quote2` au second niveau). Profondeur max 2 (`PROFONDEUR_MAX`), pas de récursion de `process_post`. Tout est enregistré en base sous l'URL du bookmark. Un record cité qui n'est pas un post, ou supprimé/bloqué/détaché, est ignoré avec une note (statut `ok`) ; un échec réseau du cité donne `CITATION NON ARCHIVÉE` dans le log et `quotes_unresolved_*.txt`. `api/repost_resolver.py` n'est qu'un shim déprécié.
- **Base SQLite** (`core/database.py`) : `posts.url` est la clé primaire, `posts.status` vaut `ok` / `deleted` (HTTP 400 ou `notFoundPost`) / `blocked` (`blockedPost`, jamais retenté) / `error_500` / `error_429` / `unknown` / `failed` (téléchargement en échec, total ou partiel ; `repost` n'est plus écrit : ancien statut des citations, encore retenté pour les anciennes lignes). `get_pending_posts()` / `get_pending_refs()` retournent les nouvelles URLs plus les posts `error_500` / `error_429` / `unknown` / `failed` / `repost` vérifiés il y a plus de `retry_after_days` jours (config, défaut 7) ; `add_post()` conserve `added_at` et `status`. `media.filename` est le vrai nom de fichier (unique par post, `INSERT OR IGNORE`). Schéma versionné (`meta.schema_version`, migrations `_migrate_vN`), clés étrangères activées. La connexion est partagée entre threads (`check_same_thread=False` + `threading.Lock`).
- **Deux modes « avancés »** dans `bsmb.py` : `download_media_dev()` appelle `run(…, no_db=True)` (traite `urls.txt` sans écrire en base) ; `download_media(force=True)` retraite toutes les URLs de `urls.txt`.
- **Console Windows** : `bsmb.py` (et `core/orchestrator.py` en usage CLI) ré-encapsule stdout en UTF-8 uniquement sous `__name__ == "__main__"` (sinon conflit avec la capture pytest). `core/colors.py` expose l'instance globale `c` (détection ANSI, `NO_COLOR` / `FORCE_COLOR`).
- **Logs** : `cleanup_old_logs()` supprime les logs de plus de 10 jours et ne garde que `max_logs` fichiers `download_*.log`.
- **Internationalisation** (`core/i18n.py`, issue #17) : `from core.i18n import _, _n` ; le `msgid` est le texte français source, les catalogues sont `lang/{fr,en}/LC_MESSAGES/bsmb.po` (`.mo` compilés au démarrage par `core/_msgfmt.py`, non versionnés). `init(language)` est appelé par `bsmb.main()` et `cli.main()` après `load_config()` (`--lang` > `config["language"]` > locale du système). Pas de `_()` au niveau module. Après toute modification de texte visible : `python tools/extract_strings.py --update`, traduire les `msgstr` vides de `en`, puis `pytest tests/test_catalogues.py`. Détails : `lang/README.md`. Le log fichier n'est pas traduit.

## Conventions

- **Accents obligatoires** dans tout texte français (code, UI, docs, commits) : « téléchargement », jamais « telechargement ». Les fichiers sont en UTF-8.
- Style d'interface « menu-generator » : `c.box_header()`, `c.menu_option()`, `c.config_line()`, `c.success()/error()/warning()/info()` ; `0` = retour, ENTRÉE = garder la valeur courante ; confirmations `[O/n]`.
- Commits : préfixe conventionnel (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`) suivi d'une description en français. Branche de travail `dev`, PR vers `main`.
- Tests : fixtures communes dans `tests/conftest.py` (`tmp_config`, `tmp_db`, `sample_post_url`) ; les appels réseau sont mockés, jamais réels.
- Fichiers locaux ignorés par Git et contenant des données personnelles : `config.json` (App Password en clair), `Token-Bearer.txt`, `bsmb.db`, `urls*.txt`, `logs/`. Ne jamais les citer dans un commit ou une issue.

## Documentation de référence

Toute la documentation est à jour de la version 3.1 (issue #15). Quand le comportement change, mettre à jour les fichiers concernés dans le même commit.

- `README.md` : usage grand public, installation, FAQ, signalement de bug.
- `ADVANCED.md` : mode avancé, token manuel, **schéma d'architecture (le seul du dépôt)**, planification, configuration, schéma de la base, métadonnées. Ne pas recopier le schéma ailleurs.
- `DEVELOPMENT.md` : guide module par module pour développer.
- `CONTRIBUTING.md` : environnement, règles de code, tests et CI, PR, release.
- `CHANGELOG.md` : historique et roadmap ; la version vit dans `core/version.py`.

## Chantier en cours

L'audit d'octobre 2026 a ouvert les issues #1 à #18, avec dépendances déclarées sur GitHub (« blocked by »). Hors #17 (internationalisation, en cours), elles sont toutes traitées : voir `CHANGELOG.md` [3.1]. Les suites prévues (dossier de données utilisateur, statut `failed` persistant, contexte de fil, sous-titres incrustés) sont dans la roadmap du changelog. Consulter `gh issue list` avant toute modification structurelle.
