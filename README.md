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

Le script installe automatiquement Python (via `winget`, ou Chocolatey à défaut), ffmpeg et exiftool si besoin, crée un environnement virtuel `.venv`, puis lance BSMB. Si Python vient d'être installé, fermez la fenêtre et relancez `Start.bat`.

### Linux / macOS

```bash
git clone https://github.com/Gotcha26/Bluesky-Save-My-Bookmarks.git
cd Bluesky-Save-My-Bookmarks
./start.sh
```

Le script crée `.venv`, installe les dépendances et vérifie la présence de ffmpeg et exiftool (facultatifs, pour les métadonnées) : `sudo apt install ffmpeg libimage-exiftool-perl` ou `brew install ffmpeg exiftool`.

### Alternative : pipx

```bash
pipx install .
bsmb
```

BSMB lit et écrit `config.json`, `bsmb.db` et `logs/` dans son dossier d'installation (celui de `bsmb.py`), quel que soit le dossier courant. **Avec pipx, ce dossier est interne à l'environnement pipx : ces fichiers (identifiants, historique, logs) sont perdus à `pipx upgrade` ou `pipx reinstall`.** Sauvegardez-les avant, ou préférez l'installation par `git clone` ci-dessus.

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

### Ligne de commande

Sans menu, par exemple pour une tâche planifiée (voir [ADVANCED.md](ADVANCED.md#planification)) :

- `python bsmb.py sync` — synchronise les bookmarks ; `python bsmb.py download [--force]` — télécharge les nouveaux
- `python bsmb.py run --yes` — synchronise puis télécharge, sans aucune question
- `python bsmb.py status [--json]` — affiche l'état du compte et des compteurs

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
- **Citations (quote posts)** — le texte et les médias du post bookmarké sont archivés, puis ceux du post qu'il cite (fichiers `…_quote…`, deux niveaux au plus)
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

### Compte et sécurité

**Mon App Password fonctionne-t-il après un redémarrage ?**
Oui. BSMB conserve vos identifiants (trousseau du système si `keyring` est installé, sinon `config.json`) et génère un nouveau token à chaque lancement. L'App Password ne change pas.

**À quoi sert le token ?**
Seule la synchronisation des bookmarks (`getBookmarks`) demande une authentification : BSMB obtient un token temporaire à partir de votre App Password et le garde en mémoire. Le téléchargement des posts, lui, n'utilise que des requêtes publiques. Vous n'avez jamais à copier de token à la main (sauf secours : voir [ADVANCED.md](ADVANCED.md#méthode-2--token-bearer-manuel-secours)).

**Message « Token expiré » ou « Identifiants invalides » ?**
Avec un App Password, BSMB renouvelle lui-même le token ; si le message persiste, vérifiez le handle et l'App Password dans **Paramètres** > **1. Identifiants Bluesky**, et recréez l'App Password sur bsky.app si besoin. Avec un `Token-Bearer.txt` manuel, il faut en recopier un nouveau.

### Téléchargement

**Comment sont gérés les nouveaux bookmarks ?**
**Mon compte** > **Synchroniser**, puis **Télécharger**. Seuls les nouveaux posts (et ceux en erreur temporaire depuis plus de 7 jours) sont traités ; les autres ne sont pas retéléchargés.

**Puis-je tout retélécharger, ou seulement une liste restreinte ?**
Oui, dans les options avancées (**Paramètres** > **4. Mode avancé**) : **Force DL** retraite toutes les URLs de `urls.txt`, **Mode dev** les traite sans toucher à la base. Pour une liste restreinte, éditez d'abord `urls.txt`. En ligne de commande : `python bsmb.py download --force`. Détails dans [ADVANCED.md](ADVANCED.md#mode-développeur).

**Que se passe-t-il si un post est supprimé par son auteur ?**
BSMB le marque comme « lien mort », le signale dans le rapport final et dans `logs/deleted_posts_*.txt`, et ne le retente pas. Un post bloqué est traité de même. Vous pouvez nettoyer ces entrées dans **Stockage local** > **Nettoyer les liens morts**.

**Les citations (quote posts) sont-elles gérées ?**
Oui. Un post qui en cite un autre est archivé comme n'importe quel post, puis le post cité l'est à son tour (fichiers `…_quote…`, deux niveaux au plus). Si le post cité est supprimé ou bloqué, une note est ajoutée au log et le bookmark reste « ok » ; si une erreur réseau l'empêche d'être archivé, il est listé dans `logs/quotes_unresolved_*.txt`.

**J'ai des posts « traités » mais peu de médias, pourquoi ?**
C'est normal : un post est enregistré dès qu'il a été traité, même sans média (texte seul, supprimé, bloqué, erreur). Les raisons se lisent dans le dossier `logs/` : `failed_downloads_*.txt`, `deleted_posts_*.txt`, `quotes_unresolved_*.txt`, `error_500_*.txt`, `rate_limited_*.txt`, `unknown_types_*.txt`, et `download_*.log` pour le détail de la session.

**Certains posts sont en « Échec » ou en « Erreur 500 ».**
Souvent une erreur réseau ou serveur temporaire (Bluesky). Une erreur 500 ou une limite de débit (429) du serveur est retentée automatiquement après 7 jours. Un échec de téléchargement (liste dans `logs/failed_downloads_*.txt`) n'est en revanche pas retenté tout seul : le post reste marqué comme traité. Pour le retenter, utilisez **Force DL** (ou `python bsmb.py download --force`).

**Que devient un post qui partage un lien (article, YouTube, x.com…) ?**
BSMB archive le texte du post, le lien, son titre, sa description et la vignette de la carte. Le contenu du site lié n'est pas téléchargé (sauf un GIF Tenor ou un fichier `.gif` / `.mp4` / `.webp` direct) ; pour ces cas, un outil externe comme `yt-dlp -a urls.txt` reste utilisable.

**Puis-je utiliser la liste de bookmarks avec d'autres outils ?**
Oui. Le fichier `urls.txt` contient une URL par ligne : il est compatible avec `wget -i urls.txt` ou `yt-dlp -a urls.txt` (outils externes, facultatifs). `bookmarks.json` garde la réponse complète de Bluesky.

### Stockage et données

**Où sont mes données ?**
Par défaut dans `~/Downloads/BSMB/` (`images/`, `videos/`, `texts/`). La base `bsmb.db`, `config.json`, `urls.txt`, `bookmarks.json` et `logs/` sont dans le dossier d'installation de BSMB.

**Puis-je changer le dossier de téléchargement ?**
Oui, dans **Paramètres** > **2. Dossier téléchargements**. Les fichiers déjà téléchargés ne sont pas déplacés : faites-le à la main si vous le souhaitez.

**Puis-je déplacer ou renommer mes médias sans risque ?**
Oui. La base ne mémorise que les noms de fichiers, pas leur emplacement. BSMB ne « voit » plus les fichiers déplacés, mais les posts restent marqués comme traités : rien n'est retéléchargé automatiquement (sauf avec Force DL).

**Que contient la base de données ?**
`bsmb.db` (SQLite) garde l'historique de tous les posts traités (URL, auteur, statut) et des médias téléchargés (type, nom de fichier). Elle ne contient pas les médias eux-mêmes. Elle est **cumulative** : `urls.txt` reflète vos bookmarks actuels, la base tout ce qui a été traité, même si vous avez retiré le bookmark depuis. Pour la consulter, ouvrez-la avec [DB Browser for SQLite](https://sqlitebrowser.org/) (schéma dans [ADVANCED.md](ADVANCED.md#base-de-données-sqlite)).

**Mes fichiers déjà téléchargés sont-ils en sécurité ?**
Oui. La réinitialisation de la base de données ne supprime jamais les fichiers téléchargés, elle efface uniquement l'historique de suivi.

**Dois-je supprimer mes bookmarks Bluesky après le téléchargement ?**
Non. Ils sont indépendants de BSMB : gardez-les, ajoutez-en de nouveaux, relancez BSMB de temps en temps, il ne récupère que les nouveaux. BSMB est votre sauvegarde locale.

### Installation et compatibilité

**Je ne connais rien à l'informatique, que dois-je installer ?**
Sous Windows, double-cliquez sur `Start.bat` : il installe Python, les bibliothèques, ffmpeg et exiftool (5 à 10 minutes, connexion Internet requise). Sous Linux et macOS, lancez `./start.sh`.

**BSMB fonctionne-t-il sans ffmpeg ou exiftool ?**
Oui, mais sans métadonnées intégrées (auteur, date, texte alternatif) dans les vidéos et les images. Les médias sont téléchargés et nommés normalement.

**Quelle version de Python ?**
Python 3.11 ou plus récent.

**Je ne vois pas toutes les options du menu.**
Le menu s'adapte à votre situation : **4. Télécharger** n'est actif qu'une fois le compte connecté et les bookmarks synchronisés, et indique « Tout est à jour » quand il n'y a rien de nouveau. Les options avancées n'apparaissent dans **Paramètres** qu'avec le mode avancé activé.

---

## Sécurité et confidentialité

- Vos données restent **100% locales** (aucun upload, aucun tracking)
- L'App Password est stocké dans le trousseau du système si `keyring` est installé (`pip install -r requirements-optional.txt`), sinon dans `config.json` (fichier local, ignoré par Git). Créez un App Password **dédié** à BSMB et révoquez-le en cas de doute ; « Mon compte > D » le supprime de cet ordinateur.
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
