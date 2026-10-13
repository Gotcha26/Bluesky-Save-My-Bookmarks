# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projet

BSMB (Bsky Save My Bookmarks) : outil Python en ligne de commande (menu TUI) qui récupère les bookmarks d'un compte Bluesky via l'API AT Protocol et archive localement images, vidéos et textes des posts. Seule dépendance externe : `requests`. Outils optionnels : `exiftool` (EXIF images) et `ffmpeg` (métadonnées vidéo). Toute l'interface, la documentation et les commits sont en **français** (voir « Conventions »).

## Commandes

```bash
pip install -r requirements.txt          # dépendances
python bsmb.py                           # lance le menu (depuis la racine du dépôt, obligatoire)
python -m pytest tests/ -q               # suite complète (154 tests, aucun accès réseau)
python -m pytest tests/test_database.py -v
python -m pytest tests/test_auth.py -k "expired"   # un test / un motif
python -m py_compile bsmb.py             # seul « lint » de la CI (.github/workflows/ci.yml)
```

`pytest` n'est pas dans `requirements.txt` : `pip install pytest` au préalable. Sur ce poste, `python` est la 3.14 ; la CI tourne sur 3.10 / 3.12 / 3.13 (Ubuntu + Windows).

Scripts utilisables seuls pour déboguer un post :

```bash
python downloaders/images.py <dossier> <url_post>
python downloaders/videos.py <dossier> <url_post>
python core/orchestrator.py <img_dir> <vid_dir> <text_dir> [--no-db] <url1> [url2...]
python api/export_bookmarks.py           # lit BSMB_TOKEN ou Token-Bearer.txt, écrit urls.txt
```

## Architecture

Le flux est en deux temps, piloté par le menu de `bsmb.py` :

1. **Synchronisation** (`core/bookmarks.py` → `api/export_bookmarks.py`) : `createSession` donne un token (`core/auth.py`), `getBookmarks` est paginé, les URLs `https://bsky.app/profile/<handle>/post/<rkey>` sont écrites dans `urls.txt` et comparées à la table `posts` pour compter les « nouveaux ».
2. **Téléchargement** : `bsmb.py` lance `core/orchestrator.py` **en sous-processus** avec les URLs nouvelles en arguments. L'orchestrateur utilise un `ThreadPoolExecutor` (`max_workers` de la config) ; chaque worker appelle `PostAnalyzer.analyze()` (`api/post_analyzer.py`, un `getRecord` par post) qui renvoie un `PostType`, puis lance **un nouveau sous-processus** `python downloaders/{images,videos,text}.py`. Le résultat est déduit du code retour et du comptage de `[DL]` / `[TXT]` dans stdout.

Points qui ne se voient pas en lisant un seul fichier :

- **Tout est relatif au répertoire courant** : `config.json`, `bsmb.db`, `urls.txt`, `logs/` et les chemins `downloaders/x.py` passés à `subprocess`. Lancer depuis un autre dossier casse l'application. Les sous-processus sont lancés avec la chaîne `"python"`, pas `sys.executable`.
- **Les downloaders exécutent du code au niveau module** (lecture de `sys.argv`, `input()` si argument manquant, `os.makedirs`). Les importer dans un test exige de patcher `sys.argv` avant l'import (voir `tests/test_images_utils.py`). `videos.py` et `text.py` ne sont pas importables tels quels.
- **Le token ne sert qu'à `getBookmarks`**. Il est passé à `export_bookmarks.py` par la variable d'environnement `BSMB_TOKEN`. Tous les autres appels (`getRecord`, `getPostThread`, `getBlob`, `getProfile`) sont publics, sans authentification.
- **Deux lectures API par post** : l'analyseur lit `com.atproto.repo.getRecord` sur `bsky.social` (record brut, embeds `app.bsky.embed.*`), les downloaders relisent `app.bsky.feed.getPostThread` sur `public.api.bsky.app` (vue hydratée, embeds `*#view`). Les deux formats d'embed coexistent donc dans le code ; ne pas les confondre.
- **`PostType.REPOST` désigne en réalité un quote post** (`app.bsky.embed.record`). `process_post()` résout alors le post cité via `api/repost_resolver.py` et **s'appelle récursivement** sur lui ; le post citant n'est pas archivé.
- **Base SQLite** (`core/database.py`) : `posts.url` est la clé primaire, `posts.status` vaut `ok` / `deleted` (HTTP 400) / `error_500` / `unknown` / `repost`. `get_pending_posts()` / `get_pending_refs()` retournent les nouvelles URLs plus les posts `error_500` / `unknown` / `repost` vérifiés il y a plus de `retry_after_days` jours (config, défaut 7) ; `add_post()` conserve `added_at` et `status`. `media.filename` est le vrai nom de fichier (unique par post, `INSERT OR IGNORE`). Schéma versionné (`meta.schema_version`, migrations `_migrate_vN`), clés étrangères activées. La connexion est partagée entre threads (`check_same_thread=False` + `threading.Lock`).
- **Deux modes « avancés »** dans `bsmb.py` : `download_media_dev()` passe `--no-db` à l'orchestrateur (traite `urls.txt` sans écrire en base) ; `download_media(force=True)` retraite toutes les URLs de `urls.txt`.
- **Console Windows** : `core/orchestrator.py` ré-encapsule stdout en UTF-8 uniquement sous `__name__ == "__main__"` (sinon conflit avec la capture pytest). `core/colors.py` expose l'instance globale `c` (détection ANSI, `NO_COLOR` / `FORCE_COLOR`).
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
