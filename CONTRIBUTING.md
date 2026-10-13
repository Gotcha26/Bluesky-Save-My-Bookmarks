# Guide de contribution

Merci de l'intérêt pour BSMB ! Ce guide explique comment contribuer au projet. Pour comprendre le code, lisez d'abord le schéma d'architecture d'[ADVANCED.md](ADVANCED.md#architecture-technique) (le seul du dépôt), puis [DEVELOPMENT.md](DEVELOPMENT.md).

---

## Types de contributions

### Signaler un bug

1. Vérifiez que le bug n'existe pas déjà dans les [issues GitHub](https://github.com/Gotcha26/Bluesky-Save-My-Bookmarks/issues).
2. Créez une issue (le modèle « Signaler un bug » est proposé) avec :
   - un **titre clair** (ex. « Erreur 500 sur posts avec vidéos ») ;
   - le **contexte** et les étapes pour reproduire ;
   - la sortie de `python bsmb.py --version` (ou `bsmb --version`) et de `python bsmb.py status --json` (état du compte et compteurs, sans appel réseau ; vérifiez qu'elle ne contient rien de personnel que vous ne voulez pas publier) ;
   - la **version de Python** et votre système (Windows, macOS, Linux) ;
   - le **message d'erreur** complet et, si possible, les extraits utiles de `logs/` ;
   - une capture d'écran si cela aide.

Ne publiez jamais votre App Password, un token, `config.json` ni vos fichiers `urls*.txt` / `bookmarks.json`.

### Proposer une fonctionnalité

1. Ouvrez une issue avec le label `enhancement`.
2. Décrivez le **problème** résolu, la **solution** envisagée et les **alternatives**.
3. Attendez les retours avant de coder.

### Améliorer la documentation

Corrigez, clarifiez, ajoutez des exemples. Toute modification qui change le comportement doit mettre à jour `README.md`, `ADVANCED.md` et `CHANGELOG.md`. Le schéma d'architecture ne vit que dans `ADVANCED.md` : ne le recopiez pas ailleurs, faites-y un renvoi.

### Soumettre du code

Voir les sections suivantes.

---

## Configuration de développement

### Cloner le dépôt

```bash
git clone https://github.com/Gotcha26/Bluesky-Save-My-Bookmarks.git
cd Bluesky-Save-My-Bookmarks
git checkout dev
```

### Installer les dépendances

Python 3.11 ou plus récent est requis.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt   # requests + pytest, pytest-cov, ruff
pip install -r requirements-optional.txt   # facultatif : keyring
```

`python bsmb.py` se lance depuis la racine du dépôt. `pip install -e .` installe aussi la commande `bsmb` (paquet défini dans `pyproject.toml`).

### Branches

```
main              <- production (releases)
└── dev           <- développement (PR ici)
    ├── feature/* <- nouvelles fonctionnalités
    └── bugfix/*  <- corrections
```

```bash
git checkout -b feature/ma-fonctionnalite
git checkout -b bugfix/ma-correction
```

### Fichiers locaux à ne pas commiter

`.gitignore` écarte les données personnelles et les fichiers de travail ; ne les ajoutez pas de force (`git add -f`) :

- `config.json` (peut contenir l'App Password), `Token-Bearer.txt`, `bsmb.db`, `bookmarks.json`, `urls*.txt`, `logs/` ;
- les sauvegardes et notes locales à la racine : `urls.bak`, `urls.txt.bak`, `ToDo.md`, les raccourcis `*.lnk` (ex. `Téléchargements.lnk`) et les fichiers `*.code-workspace` de votre éditeur.

Vérifiez `git status` avant chaque commit.

---

## Guidelines de code

### Style Python

```python
# BON
def obtenir_token(config):
    """Récupère un token Bearer valide."""
    return get_token(config)


# MAUVAIS
def getToken(cfg):
    return get_token(cfg)
```

- Noms de fonctions en `snake_case`, variables explicites (pas `x`, `tmp`).
- Docstrings sur les fonctions publiques ; commentaires pour la logique non évidente.
- 4 espaces d'indentation, **110 colonnes** au maximum (`ruff` : règles E, F, W, I, B, UP).
- Chemins avec `pathlib.Path` ; les chemins relatifs de la config passent par `resolve_path(config, clé)`.
- Tout appel HTTP passe par la session partagée : `from core import http as bsmb_http`, puis `bsmb_http.get_session()` (jamais `requests.get/post` directement).
- Pas de code exécuté à l'import dans `core/`, `api/` et `downloaders/` (pas d'affichage, d'`input()` ni de fichier créé) ; un nouveau module s'ajoute à `MODULES` dans `tests/test_imports.py`.
- Les confirmations passent par `core.ui.confirm()` et les pauses par `core.ui.pause()`, pour rester utilisables en mode non interactif.

### Texte français (UTF-8)

Tous les textes (interface, docstrings, commentaires, documentation, commits) sont en français **avec accents** : « Télécharger », « Récupérer », « Vérifiez », jamais « Telecharger ». Les fichiers sont en UTF-8.

### Commits

Un préfixe conventionnel suivi d'une description en français :

```bash
git commit -m "feat: Ajouter la prise en charge des sous-titres"
```

- `feat:` nouvelle fonctionnalité
- `fix:` correction de bug
- `docs:` documentation
- `refactor:` refactorisation sans changement fonctionnel
- `test:` tests
- `perf:` performance
- `chore:` maintenance (CI, dépendances)

Mentionnez l'issue traitée dans le corps du message (`Fixes #N`).

---

## Tests

Aucun test ne fait d'appel réseau : `tests/conftest.py` remplace la session HTTP par un faux et une barrière réseau fait échouer toute connexion externe. Les réponses d'API réelles se trouvent dans `tests/fixtures/`. Écrivez les nouveaux tests dans le même esprit (fixtures `tmp_config`, `tmp_db`, `fake_session` ; voir l'exemple dans [DEVELOPMENT.md](DEVELOPMENT.md#tests)).

```bash
python -m pytest tests/ -q                        # tous les tests
python -m pytest tests/test_database.py -v        # un fichier
python -m pytest tests/test_auth.py -k "expired"  # un motif
```

### Qualité

La CI (`.github/workflows/ci.yml`, job `lint` puis `test`) refuse tout ce qui ne passe pas ces commandes ; lancez-les avant de pousser :

```bash
ruff check .                          # analyse statique
ruff format .                         # formatage (ruff format --check . en CI)
python -m pytest tests/ --cov=core --cov=api --cov=downloaders --cov-report=term-missing --cov-fail-under=70
```

La CI teste Python 3.11 à 3.14 sur Ubuntu et Windows. Dependabot propose chaque semaine les mises à jour de `pip` et de `github-actions`.

---

## Points d'attention

### Windows

- Console en UTF-8 : `chcp 65001` en `cmd` (`Start.bat` le fait).
- Couleurs ANSI : détectées automatiquement (`NO_COLOR` / `FORCE_COLOR` pour forcer).
- Chemins : `Path()` de `pathlib`, jamais de chaînes concaténées.

### Programmes externes

Seuls `exiftool` et `ffmpeg` sont lancés en sous-processus (`subprocess.run` avec `capture_output=True, encoding="utf-8", errors="replace"`). Leur absence ne doit jamais faire échouer un téléchargement : le média est enregistré sans métadonnées.

### Base de données

- Le schéma est versionné (`meta.schema_version`) : une évolution du schéma s'écrit comme une migration `_migrate_vN`, avec son test, jamais comme une recréation de la base.
- La connexion est partagée entre threads, protégée par un verrou ; fermez-la avec `db.close()`.

### Secrets

L'App Password ne doit jamais apparaître dans un log, un message d'erreur ou un test ; `core/secret_store.py` est le seul module qui le lit ou l'écrit.

---

## Soumettre une Pull Request

### Checklist

- [ ] Branche créée depuis `dev`
- [ ] Tests ajoutés, `python -m pytest tests/ -q` passe
- [ ] `ruff check .` et `ruff format --check .` propres
- [ ] Documentation mise à jour (`README.md`, `ADVANCED.md`, `CHANGELOG.md` si le comportement change)
- [ ] Accents français respectés
- [ ] Aucun fichier personnel ajouté (`config.json`, `*.db`, `urls*.txt`, `logs/`…)
- [ ] Message de commit clair, avec `Fixes #N`

### Processus

1. Poussez votre branche : `git push origin feature/ma-fonctionnalite`.
2. Ouvrez une PR vers `dev` : titre clair, description du changement, lien vers l'issue, capture d'écran si l'interface change.
3. Révision : relecture du code, tests et documentation.
4. Merge sur `dev`, puis sur `main` lors d'une release.

---

## Processus de release

La version vit à **un seul endroit** : `core/version.py` (`__version__`). `pyproject.toml` la lit en dynamique, le menu l'affiche dans son en-tête (`BSMB v3.1.0`), `bsmb --version` et les fiches JSON (`bsmb_version`) la reprennent.

```
X.Y.Z
  X = majeur (rupture : architecture, format de données)
  Y = mineur (fonctionnalités)
  Z = correctif
```

Pour publier : mettre à jour `core/version.py` et `CHANGELOG.md`, fusionner dans `main`, puis poser le tag (opération réservée au mainteneur) :

```bash
git tag -a v3.1.0 -m "Version 3.1.0"
git push origin v3.1.0
```

---

## Questions ?

- Ouvrez une issue avec le label `question`.
- Consultez le [README](README.md), [ADVANCED.md](ADVANCED.md) et [DEVELOPMENT.md](DEVELOPMENT.md).
- Regardez les issues existantes.

Merci de contribuer !
