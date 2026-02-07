# 🤝 Guide de contribution

Merci de l'intérêt pour BSMB! Ce guide explique comment contribuer au projet.

---

## 📋 Types de contributions

### 🐛 Signaler un bug
1. Vérifiez que le bug n'existe pas déjà dans [GitHub Issues](https://github.com/Gotcha26/Bluesky-Save-My-Bookmarks/issues)
2. Créez une nouvelle issue avec :
   - **Titre clair** : ex. "Erreur 500 sur posts avec vidéos"
   - **Description** : Contexte et étapes pour reproduire
   - **Environnement** : OS, version Python, version BSMB
   - **Message d'erreur** : Copiez la stacktrace complète
   - **Screenshots** : Si applicable

### 💡 Proposer une fonctionnalité
1. Ouvrez une issue avec le label `enhancement`
2. Décrivez :
   - **Problème** : Quel besoin cela résout?
   - **Solution** : Comment ca devrait fonctionner?
   - **Alternatives** : Y a-t-il d'autres solutions?
3. Attendez les retours avant de coder

### 📚 Améliorer la documentation
- Corrigez les typos
- Clarifiez les explications
- Ajoutez des examples
- Traduisez (FR/EN)

### 💻 Soumettre du code

---

## 🔧 Configuration de développement

### Cloner le dépôt
```bash
git clone https://github.com/Gotcha26/Bluesky-Save-My-Bookmarks.git
cd Bluesky-Save-My-Bookmarks
git checkout dev
```

### Installer les dépendances dev
```bash
pip install -r requirements.txt  # À créer
pip install -e .                 # Mode éditable
```

### Structure de branche
```
main              ← Production (releases)
└── dev           ← Développement (PRs ici)
    ├── feature/* ← Nouvelles fonctionnalités
    └── bugfix/*  ← Corrections de bugs
```

### Créer une branche de feature
```bash
git checkout -b feature/ma-fonctionnalite
git checkout -b bugfix/ma-correction
```

---

## 📝 Guidelines de code

### Style Python
```python
# ✅ BON
def obtenir_token(config):
    """Récupère un token Bearer valide."""
    if not config.get("bsky_handle"):
        return None
    return create_session(config["bsky_handle"], config["bsky_app_password"])

# ❌ MAUVAIS
def getToken(cfg):
    if not cfg['bsky_handle']: return None
    return create_session(cfg['bsky_handle'],cfg['bsky_app_password'])
```

**Règles:**
- Noms de fonction en snake_case
- Variables explicites (pas `x`, `tmp`, etc.)
- Docstrings sur toutes les fonctions
- Commentaires pour la logique complexe
- 4 espaces d'indentation (jamais de tabs)
- Ligne max 100 caractères

### French text (UTF-8)
- ✅ Texte français avec accents complets
- ✅ "Télécharger", "Récupérer", "Vérifiez"
- ❌ Jamais "Telecharger", "Recuperer"
- ✅ UTF-8 encoding déclaré en header

### Commits
```bash
# ✅ BON
git commit -m "feat: Ajouter support pour App Passwords

Description détaillée du changement."

# ❌ MAUVAIS
git commit -m "fix stuff"
git commit -m "blabla"
```

Format:
- `feat:` - Nouvelle fonctionnalité
- `fix:` - Correction de bug
- `docs:` - Documentation
- `refactor:` - Refactorisation sans changement fonctionnel
- `test:` - Tests
- `perf:` - Performance
- `chore:` - Maintenance

---

## 🧪 Tests

### Structure de tests
```
tests/
├── test_auth.py           # Tests authentication
├── test_config.py         # Tests configuration
├── test_database.py       # Tests database
├── test_post_analyzer.py  # Tests analysis
└── conftest.py            # Fixtures communes
```

### Écrire un test
```python
import pytest
from core.auth import has_credentials, AuthError

def test_has_credentials_with_valid_config():
    """Vérifie que has_credentials() retourne True avec config valide."""
    config = {
        "bsky_handle": "user.bsky.social",
        "bsky_app_password": "xxxx-xxxx-xxxx-xxxx"
    }
    assert has_credentials(config) is True

def test_has_credentials_empty():
    """Vérifie que has_credentials() retourne False avec config vide."""
    config = {"bsky_handle": "", "bsky_app_password": ""}
    assert has_credentials(config) is False

@pytest.mark.asyncio
async def test_create_session_invalid_credentials():
    """Vérifie que create_session() lève AuthError avec identifiants invalides."""
    with pytest.raises(AuthError) as exc_info:
        create_session("invalid.handle", "invalid-password")
    assert "invalides" in str(exc_info.value).lower()
```

### Lancer les tests
```bash
pytest                    # Tous les tests
pytest -v                 # Verbose
pytest tests/test_auth.py # Un fichier spécifique
pytest -k "create_session"# Tests matching
```

---

## 🏗️ Architecture à connaître

### Modules clés

**core/auth.py** - Authentification
```python
create_session(handle, app_password)  # API createSession
get_token(config)                      # Mode auto ou fallback
has_credentials(config)                # Vérification
```

**core/config.py** - Configuration
```python
load_config()        # Charge JSON
save_config(config)  # Sauvegarde
ensure_dirs(config)  # Crée répertoires
get_media_dirs(config)  # Chemins médias
```

**core/database.py** - Tracking
```python
db.add_post(url, post_id, handle)
db.get_new_posts(urls)              # Nouveaux uniquement
db.add_media(url, type, filename)
db.get_stats()
```

**api/export_bookmarks.py** - Export
- Lit token depuis env var `BSMB_TOKEN`
- Fallback sur `Token-Bearer.txt`
- Pagine via getBookmarks

**api/post_analyzer.py** - Analyse
```python
analyzer.analyze(url)  # Retourne (PostType, data, debug_info)
```

**downloaders/** - Téléchargement
- `images.py` - Images avec EXIF
- `videos.py` - Vidéos avec ffmpeg
- `text.py` - Texte seul

### Flux principal
```
bsmb.py (menu TUI)
  ↓ Option 1: export_bookmarks.py (subprocess)
  ↓ Option 2: orchestrator.py (subprocess)
      ├→ post_analyzer.py (analyse type)
      ├→ repost_resolver.py (résout reposts)
      └→ downloaders/* (télécharge média)
```

---

## 🔍 Points d'attention

### Développement Windows
- Forcer UTF-8 : `chcp 65001` en cmd
- ColorS ANSI : Auto-détecté via kernel32 VTP
- Chemins : Utiliser `Path()` de pathlib, pas strings

### Appels subprocess
- Toujours utiliser `subprocess.run()` avec `capture_output=True`
- Passer `encoding="utf-8", errors="replace"`
- Pour export_bookmarks.py, passer token via env var

### Base de données
- SQLite verrouille pendant écriture
- Appeler `db.close()` à la fin
- Pas de migrations (créer schema à fresh)

### Métadonnées
- **Images** : EXIF via PIL.Image
- **Vidéos** : ffmpeg metadata
- **Fallback** : Continuer même si EXIF/ffmpeg absent

### Colors
- Importer : `from core.colors import c`
- Instance globale (singleton)
- Supporté sur Windows/Mac/Linux

---

## 📤 Soumettre une Pull Request

### Checklist
- [ ] Branche créée depuis `dev`
- [ ] Tests ajoutés/passent (`pytest`)
- [ ] Documentation mise à jour
- [ ] Accents français ✓
- [ ] Pas de fichiers non-nécessaires (config.json, .db, logs/)
- [ ] Message de commit clair

### Processus
1. **Push votre branche** :
   ```bash
   git push origin feature/ma-fonctionnalite
   ```

2. **Ouvrir une PR** sur GitHub
   - Titre clair
   - Description du changement
   - Lien vers issue si applicable
   - Screenshots si UI change

3. **Révision** :
   - Code review
   - Tests
   - Documentation

4. **Merge** sur dev (puis main via release)

---

## 🚀 Processus de release

### Version scheme
```
Version X.Y (ex: 2.1)
  X = Major (architecture break)
  Y = Minor (features/fixes)
```

### Créer une release
```bash
# Sur main
git tag -a v2.1 -m "Version 2.1 - February 2026"
git push origin v2.1
```

---

## ❓ Questions?

- Ouvrez une issue avec label `question`
- Consultez [README.md](README.md) et [MEMORY.md](.claude/memory/MEMORY.md)
- Regardez les issues existantes

---

**Merci de contribuer! 🙏**
