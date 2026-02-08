# BSMB - Bsky Save My Bookmarks

Sauvegardez automatiquement les images, vidéos et textes de vos bookmarks Bluesky.

---

## Comment ça marche ?

1. Vous connectez votre compte Bluesky (une seule fois)
2. BSMB récupère la liste de vos bookmarks
3. Il télécharge les médias (images, vidéos, textes) dans un dossier local
4. À chaque lancement, seuls les **nouveaux** bookmarks sont traités

Tout est automatique. Aucun copier-coller de token, aucun fichier à éditer manuellement.

---

## Installation

### Windows

1. Téléchargez le projet (bouton vert **Code** > **Download ZIP**)
2. Décompressez le dossier
3. Double-cliquez sur `Start.bat`

Le script installe automatiquement Python, ffmpeg et exiftool si besoin.

### Linux / macOS

```bash
git clone https://github.com/Gotcha26/Bluesky-Save-My-Bookmarks.git
cd Bluesky-Save-My-Bookmarks
pip install -r requirements.txt
python bsmb.py
```

Optionnel (pour les métadonnées) : `sudo apt install ffmpeg exiftool` ou `brew install ffmpeg exiftool`

---

## Première utilisation

Au lancement, BSMB affiche un menu simple :

```
======================================================================
=                    BSMB - BSKY SAVE MY BOOKMARKS                   =
======================================================================
  Compte: non connecté | Médias: aucun

  1. Mon compte     - Connexion et bookmarks en ligne
  2. Stockage local - Dossier et statistiques
  3. Paramètres     - Configuration de l'application
  4. Télécharger    - (connectez d'abord votre compte)

  0. Quitter
```

### Étape 1 — Connecter votre compte

Choisissez **1. Mon compte** puis **1. Connecter mon compte Bluesky**.

Vous aurez besoin de :
- Votre **handle** Bluesky (ex: `monpseudo.bsky.social`)
- Un **App Password** (mot de passe d'application)

**Créer un App Password :**
1. Allez sur [bsky.app](https://bsky.app) > **Settings** > **App Passwords**
2. Cliquez sur **Add App Password**
3. Nommez-le (ex: « BSMB ») et copiez le mot de passe généré (`xxxx-xxxx-xxxx-xxxx`)

BSMB teste immédiatement la connexion. Si ça marche, vos identifiants sont sauvegardés localement.

### Étape 2 — Synchroniser

Toujours dans **Mon compte**, choisissez **1. Synchroniser les bookmarks**.

BSMB récupère la liste complète de vos bookmarks depuis Bluesky et vous indique combien sont nouveaux.

### Étape 3 — Télécharger

Revenez au menu principal et choisissez **4. Télécharger X nouveaux bookmarks**.

BSMB analyse chaque post et télécharge automatiquement :
- Les **images** (avec métadonnées EXIF : auteur, date, lien)
- Les **vidéos** (avec métadonnées ffmpeg)
- Les **textes** seuls

Les fichiers sont enregistrés dans `~/Downloads/BSMB/` par défaut.

---

## Utilisation régulière

À chaque lancement :

1. **Mon compte** > **Synchroniser** — récupère les nouveaux bookmarks
2. **Télécharger X nouveaux bookmarks** — télécharge uniquement ce qui est nouveau

BSMB se souvient de ce qui a déjà été traité grâce à sa base de données locale.

---

## Menu principal

| Option | Description |
|--------|-------------|
| **1. Mon compte** | Connexion Bluesky, synchronisation, compteurs en ligne vs local |
| **2. Stockage local** | Statistiques, taille du dossier, nettoyage des liens morts |
| **3. Paramètres** | Identifiants, dossier de destination, workers parallèles, mode avancé |
| **4. Télécharger** | Lance le téléchargement des nouveaux bookmarks |

---

## Fonctionnalités

- **Téléchargement incrémental** — seuls les nouveaux bookmarks sont traités
- **Résolution des reposts** — si vous avez bookmarké un repost, BSMB retrouve le post original
- **Métadonnées** — chaque fichier contient l'auteur, la date et le lien vers le post original
- **Détection des liens morts** — les posts supprimés (erreur 400/500) sont identifiés et nettoyables
- **Téléchargement parallèle** — configurable de 1 à 16 workers (défaut : 4)
- **Multi-plateforme** — Windows, macOS, Linux

---

## Nommage des fichiers

Format : `handle_YYYYMMDD_postid_N.ext`

Exemple : `artiste_20260110_3abc123xyz_01.jpg`

Chaque fichier est traçable vers son post d'origine sur Bluesky.

---

## FAQ

**Mon App Password fonctionne-t-il après un redémarrage ?**
Oui. BSMB stocke vos identifiants dans `config.json` et génère un nouveau token à chaque lancement. L'App Password ne change pas.

**Mes fichiers déjà téléchargés sont-ils en sécurité ?**
Oui. La réinitialisation de la base de données ne supprime jamais les fichiers téléchargés. Elle efface uniquement l'historique de suivi.

**Puis-je changer le dossier de téléchargement ?**
Oui, dans **Paramètres** > **Dossier téléchargements**.

**Que se passe-t-il si un post est supprimé ?**
BSMB le marque comme « lien mort ». Vous pouvez nettoyer ces entrées dans **Stockage local** > **Nettoyer les liens morts**.

**ffmpeg ou exiftool ne sont pas installés ?**
Les médias seront téléchargés normalement, mais sans métadonnées intégrées (auteur, date, etc.).

**Puis-je utiliser la liste de bookmarks avec d'autres outils ?**
Oui. Le fichier `urls.txt` est compatible avec `yt-dlp -a urls.txt`, `wget -i urls.txt`, etc.

---

## Sécurité et confidentialité

- Vos données restent **100% locales** (aucun upload, aucun tracking)
- L'App Password est stocké dans `config.json` (fichier local, ignoré par Git)
- Seules des requêtes HTTPS vers l'API Bluesky sont effectuées
- Ne partagez jamais votre App Password

---

## Utilisateurs avancés

Si vous souhaitez utiliser le mode développeur, le token Bearer manuel, ou comprendre l'architecture technique, consultez le [guide avancé](ADVANCED.md).

---

## Signaler un bug

Trouvez un problème ? Signalez-le sur [GitHub Issues](https://github.com/Gotcha26/Bluesky-Save-My-Bookmarks/issues)

Incluez :
- Votre plateforme (Windows/Mac/Linux)
- L'erreur exacte (message, logs si disponibles)
- Les étapes pour reproduire le problème

---

## Licence

Projet personnel — Utilisation libre.
Respectez les droits des créateurs de contenu.
