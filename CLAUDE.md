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
python -m compileall -q -x '[/\\]\.git[/\\]' .     # « lint » de la CI (.github/workflows/ci.yml)
```

`pytest` n'est pas dans `requirements.txt` : `pip install pytest` au préalable. Sur ce poste, `python` est la 3.14 ; la CI tourne sur 3.10 / 3.12 / 3.13 (Ubuntu + Windows).

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

1. **Synchronisation** (`core/bookmarks.py` → `api/export_bookmarks.py`) : `createSession` donne un token (`core/auth.py`), `getBookmarks` est paginé, les URLs `https://bsky.app/profile/<handle>/post/<rkey>` sont écrites dans `urls.txt` et comparées à la table `posts` pour compter les « nouveaux ».
2. **Téléchargement** : `bsmb.py` appelle directement `core.orchestrator.run(urls, config, no_db=False, on_progress=None, quiet=False)`, qui renvoie un dict de statistiques et écrit les logs. L'orchestrateur utilise un `ThreadPoolExecutor` (`max_workers` de la config) ; chaque worker appelle `PostAnalyzer.analyze()` (`api/post_analyzer.py`, un `getRecord` par post) qui renvoie un `PostType`, puis la fonction du downloader : `download_images()`, `download_video()` ou `save_text()` (signature `(post_url, dest_dir, config, session=None, name_prefix=None)`). Chacune renvoie une `list[DownloadResult]` (`downloaders/__init__.py` : `filename`, `path`, `media_type`, `size`, `cid`) ; liste vide = aucun média, `DownloadError` = erreur technique (statut `failed`). Comptage et `add_media` viennent de ces résultats ; les downloaders n'impriment rien, les lignes `[DL]`/`[OK]`/`[TXT]` sont produites par `lignes_console()`.

Points qui ne se voient pas en lisant un seul fichier :

- **Chemins ancrés sur `PROJECT_ROOT`** (`core/paths.py`, dossier de `bsmb.py`) : `CONFIG_FILE` y est fixé, et `resolve_path(config, key)` résout `db_file`, `urls_file`, `logs_dir`, `token_file` quand ils sont relatifs. Toujours passer par `resolve_path`, jamais `Path(config["…"])`. `config.json` garde les valeurs relatives. Les dossiers médias viennent de `get_media_dirs(config)` (`download_dir`).
- **Aucun code au niveau module** dans les downloaders et l'orchestrateur : `tests/test_imports.py` importe chaque module dans un interpréteur neuf et échoue sur toute sortie, `input()` ou fichier créé. Le `sys.path.insert` des scripts n'a lieu qu'en exécution directe (`__package__` vide). Seuls `exiftool` et `ffmpeg` sont lancés en sous-processus.
- **Le token ne sert qu'à `getBookmarks`**. Il est passé à `export_bookmarks.py` par la variable d'environnement `BSMB_TOKEN`. Tous les autres appels (`getRecord`, `getPostThread`, `getBlob`, `getProfile`) sont publics, sans authentification.
- **Deux lectures API par post** : l'analyseur lit `com.atproto.repo.getRecord` sur `bsky.social` (record brut, embeds `app.bsky.embed.*`), les downloaders relisent `app.bsky.feed.getPostThread` sur `public.api.bsky.app` (vue hydratée, embeds `*#view`). Les deux formats d'embed coexistent donc dans le code ; ne pas les confondre.
- **`PostType.QUOTE` = citation (quote post, `app.bsky.embed.record`)** ; `REPOST` n'en est qu'un alias déprécié (un vrai repost n'est jamais bookmarké). Une citation avec média (`recordWithMedia`) garde son type média (`IMAGES`/`VIDEO`/`EXTERNAL`) et `data["is_quote"] = True`. `process_post()` archive d'abord le post citant selon son propre contenu (texte, média), puis, via `api/quote_resolver.py` (`QuoteResolver.resolve() -> QuoteTarget | None`), le post cité, avec les downloaders et `name_prefix` : fichiers `<citant>_<date>_<rkey>_quote_<n>` (`_quote2` au second niveau). Profondeur max 2 (`PROFONDEUR_MAX`), pas de récursion de `process_post`. Tout est enregistré en base sous l'URL du bookmark. Un record cité qui n'est pas un post, ou supprimé/bloqué/détaché, est ignoré avec une note (statut `ok`) ; un échec réseau du cité donne `CITATION NON ARCHIVÉE` dans le log et `quotes_unresolved_*.txt`. `api/repost_resolver.py` n'est qu'un shim déprécié.
- **Base SQLite** (`core/database.py`) : `posts.url` est la clé primaire, `posts.status` vaut `ok` / `deleted` (HTTP 400) / `error_500` / `unknown` (`repost` n'est plus écrit : ancien statut des citations, encore retenté pour les anciennes lignes). `get_pending_posts()` / `get_pending_refs()` retournent les nouvelles URLs plus les posts `error_500` / `unknown` / `repost` vérifiés il y a plus de `retry_after_days` jours (config, défaut 7) ; `add_post()` conserve `added_at` et `status`. `media.filename` est le vrai nom de fichier (unique par post, `INSERT OR IGNORE`). Schéma versionné (`meta.schema_version`, migrations `_migrate_vN`), clés étrangères activées. La connexion est partagée entre threads (`check_same_thread=False` + `threading.Lock`).
- **Deux modes « avancés »** dans `bsmb.py` : `download_media_dev()` appelle `run(…, no_db=True)` (traite `urls.txt` sans écrire en base) ; `download_media(force=True)` retraite toutes les URLs de `urls.txt`.
- **Console Windows** : `bsmb.py` (et `core/orchestrator.py` en usage CLI) ré-encapsule stdout en UTF-8 uniquement sous `__name__ == "__main__"` (sinon conflit avec la capture pytest). `core/colors.py` expose l'instance globale `c` (détection ANSI, `NO_COLOR` / `FORCE_COLOR`).
- **Logs** : `cleanup_old_logs()` supprime les logs de plus de 10 jours et ne garde que `max_logs` fichiers `download_*.log`.
- `core/logger.py` est vide, `lang/` est vide, `tools/debug_post.py` est un vestige : ne pas s'y appuyer.

## Conventions

- **Accents obligatoires** dans tout texte français (code, UI, docs, commits) : « téléchargement », jamais « telechargement ». Les fichiers sont en UTF-8.
- Style d'interface « menu-generator » : `c.box_header()`, `c.menu_option()`, `c.config_line()`, `c.success()/error()/warning()/info()` ; `0` = retour, ENTRÉE = garder la valeur courante ; confirmations `[O/n]`.
- Commits : préfixe conventionnel (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`) suivi d'une description en français. Branche de travail `dev`, PR vers `main`.
- Tests : fixtures communes dans `tests/conftest.py` (`tmp_config`, `tmp_db`, `sample_post_url`) ; les appels réseau sont mockés, jamais réels.
- Fichiers locaux ignorés par Git et contenant des données personnelles : `config.json` (App Password en clair), `Token-Bearer.txt`, `bsmb.db`, `urls*.txt`, `logs/`. Ne jamais les citer dans un commit ou une issue.

## Documentation de référence

- `README.md` : usage grand public (à jour).
- `ADVANCED.md` : mode avancé, schéma de la base, métadonnées, architecture (à jour).
- `FAQ.md`, `Instructions-token.md`, `DEVELOPMENT.md`, `CONTRIBUTING.md`, `CHANGELOG.md` : partiellement obsolètes (menus v2, yt-dlp, changelog arrêté à 2.1). Voir l'issue #15 avant de s'en servir.

## Chantier en cours

L'audit d'octobre 2026 a ouvert les issues #1 à #18, avec dépendances déclarées sur GitHub (« blocked by »). Les fondations sont #1 (hôte PDS codé en dur), #2 (identité par AT-URI) et #10 (suppression des sous-processus) ; la plupart des autres en dépendent. Consulter `gh issue list` avant toute modification structurelle.
