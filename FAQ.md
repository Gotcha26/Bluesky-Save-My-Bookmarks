## ❓ FAQ

### 🔐 Token et sécurité

**Q : À quoi sert le token Bearer ?**  
**R :** Le token Bearer est une **clé d'authentification temporaire** qui permet à BSMB d'accéder à vos bookmarks Bluesky via l'API officielle.

**Pourquoi est-il nécessaire ?**
- Bluesky ne propose pas (encore) d'API publique pour les bookmarks
- Le token prouve que vous êtes le propriétaire du compte
- Il permet de récupérer vos bookmarks privés

**Sécurité :**
- ⚠️ Ne partagez JAMAIS ce token (= accès complet à votre compte)
- ⏱️ Il expire après quelques jours ou à la déconnexion
- 🔄 Vous devrez le récupérer régulièrement

### 📥 Téléchargement

**Q : Puis-je télécharger tous mes bookmarks d'un seul coup ?**  
**R :** Oui ! Menu > Options avancées > Option 2 (Forcer le re-téléchargement) traite tous les posts de `urls.txt` sans limite. Pour de gros volumes (1000+ bookmarks), prévoyez du temps et de l'espace disque.

**Q : Comment est géré l'ajout de nouveaux posts dans mes bookmarks ?**  
**R :** Workflow simple :
1. Relancez l'export (Option 1) → `urls.txt` est mis à jour
2. Lancez le téléchargement incrémental (Option 2)
3. Seuls les **nouveaux** posts sont traités
4. Aucun re-téléchargement des anciens posts

**Q : Comment télécharger une liste restreinte d'URLs ?**  
**R :** Utilisez le **mode développement** :
1. Éditez `urls.txt` et gardez seulement les URLs voulues
2. Menu > Options avancées > Option 1 : Mode développement
3. Les médias sont téléchargés sans modifier la base de données
4. Pratique pour tester ou retraiter des posts spécifiques

**Q : Que se passe-t-il si un post est supprimé par son auteur ?**  
**R :** Le post est détecté comme **supprimé (400)** et :
- ✅ Signalé dans le résumé final
- ✅ Enregistré dans `logs/deleted_posts_*.txt`
- ✅ Marqué comme traité (pas de re-tentative)
- ❌ Aucun média téléchargé (post inaccessible)

**Q : Les reposts sont-ils gérés ?**  
**R :** Oui ! Quand un repost est détecté :
1. BSMB extrait l'URL du post original
2. Le post original est téléchargé automatiquement
3. Si le repost ne peut pas être résolu, il est listé dans `logs/reposts_unresolved_*.txt`

**Q : J'ai X posts trackés mais 0 médias téléchargés, pourquoi ?**  
**R :** C'est **normal** ! Un post est "tracké" dès qu'il est analysé, même s'il ne contient aucun média téléchargeable.

**Raisons fréquentes :**

1. **Posts texte uniquement** (pas d'image ni vidéo)
   - Le post est tracké pour éviter de le re-analyser
   - Comptabilisé dans "Posts trackés"
   - Aucun média à télécharger

2. **Posts supprimés (400)**
   - Détectés comme inaccessibles
   - Trackés pour ne pas les re-tenter
   - Listés dans `logs/deleted_posts_*.txt`

3. **Reposts non résolus**
   - BSMB n'a pas pu extraire le post original
   - Trackés comme "traités"
   - Listés dans `logs/reposts_unresolved_*.txt`

4. **Erreurs serveur (500)**
   - Erreur temporaire de l'API Bluesky
   - Trackés pour éviter les tentatives répétées
   - Listés dans `logs/error_500_*.txt`

5. **Types de médias non reconnus**
   - Format non géré (rare)
   - Listés dans `logs/unknown_types_*.txt`

**Pour vérifier :**
```
Menu > Option 4 : Statistiques
```

**Pour comprendre pourquoi :**
Consultez les fichiers dans le dossier `logs/` :
- `failed_downloads_*.txt` : Échecs de téléchargement
- `deleted_posts_*.txt` : Posts supprimés
- `reposts_unresolved_*.txt` : Reposts non traités
- `download_*.log` : Log détaillé de la session

### 💾 Stockage et données

**Q : Où sont stockées mes données ?**  
**R :** Par défaut (multi-OS) :
- **Windows** : `C:\Users\VotreNom\Downloads\BSMB\`
- **macOS** : `/Users/votrenom/Downloads/BSMB/`
- **Linux** : `/home/votrenom/Downloads/BSMB/`

**Sous-dossiers automatiques :**
- Images : `images/`
- Vidéos : `videos/`
- Textes : `texts/`

**Autres fichiers :**
- **Base de données** : `bsmb.db` (racine du projet)
- **Logs** : `logs/` (racine du projet)
- **Configuration** : `config.json` (modifiable via Option 6)

**Q : Je veux changer le répertoire des téléchargements**  
**R :** Menu principal > Option 6 : Configuration > Option 1

Vous pouvez définir n'importe quel dossier (exemple : `D:\Mes Bookmarks\`).
Les sous-dossiers `images/`, `videos/`, et `texts/` seront créés automatiquement.

⚠️ **Important** : Si vous avez déjà téléchargé des médias, ils ne seront **pas déplacés** automatiquement. Vous devrez les déplacer manuellement si vous le souhaitez.

**Q : J'ai X posts trackés, comment les extraire/réutiliser/re-télécharger ?**  
**R :** Plusieurs méthodes selon votre besoin :

### 📋 Méthode 1 : Consulter la base de données (avancé)

Utilisez un explorateur SQLite gratuit comme [DB Browser for SQLite](https://sqlitebrowser.org/) :

1. Ouvrez le fichier `bsmb.db`
2. Table `posts` → Contient toutes les URLs trackées
3. Exportez en CSV si besoin

**Colonnes disponibles :**
- `url` : URL complète du post
- `post_id` : Identifiant du post
- `handle` : Auteur (@username)
- `added_at` : Date d'ajout dans la DB
- `last_check` : Dernière vérification

### 🔄 Méthode 2 : Re-télécharger les posts trackés

**Si les URLs sont toujours dans vos bookmarks :**
```
1. Menu > Option 1 : Export (met à jour urls.txt)
2. Menu > Options avancées > Option 2 : Forcer le re-téléchargement
```
Force le re-traitement de TOUT `urls.txt`, y compris les posts déjà trackés.

**Si les URLs ne sont plus dans vos bookmarks :**
1. Extrayez les URLs de `bsmb.db` (voir Méthode 1)
2. Créez un fichier `urls_custom.txt` avec ces URLs
3. Copiez ce contenu dans `urls.txt`
4. Lancez Menu > Options avancées > Option 2

### 📁 Méthode 3 : Utiliser la sauvegarde

Le fichier `urls.txt.bak` contient votre **dernier export précédent** :
```bash
# Remplacer urls.txt par la sauvegarde
cp urls.txt.bak urls.txt

# Puis re-télécharger
Menu > Options avancées > Option 2
```

### 🎯 Méthode 4 : Mode développement (test)

Pour re-télécharger une **liste restreinte** :
1. Éditez `urls.txt` manuellement (gardez seulement les URLs voulues)
2. Menu > Options avancées > Option 1 : Mode développement
3. Les médias sont téléchargés mais la DB n'est pas mise à jour

⚠️ **Note :** Le mode "Force" (Option 2 avancées) ignore l'historique de la DB et tente de tout re-télécharger. Les posts sans média (texte seul, supprimés, etc.) resteront sans média même après un re-téléchargement forcé.

### 💡 Comprendre la base de données

La base de données `bsmb.db` a un rôle **cumulatif et historique**. Elle conserve la trace de **tous** les posts que vous avez tenté de traiter, même ceux qui :
- N'ont plus de médias téléchargeables
- Ont été supprimés par leur auteur
- Sont des reposts non résolus
- Contiennent uniquement du texte
- Ont échoué au téléchargement

**Important :** La DB n'est **pas** une copie exacte de `urls.txt` :
- ✅ `urls.txt` = Votre liste **actuelle** de bookmarks Bluesky
- ✅ `bsmb.db` = L'**historique complet** de tout ce qui a été traité

**Exemple concret :**
1. Vous avez 500 bookmarks → Export → 500 URLs dans `urls.txt`
2. Vous téléchargez → 450 médias récupérés, 50 posts sans média
3. La DB contient 500 posts trackés, même si seulement 450 ont des médias
4. Plus tard, vous supprimez 100 bookmarks sur Bluesky
5. Nouvel export → `urls.txt` contient 400 URLs
6. **Mais la DB contient toujours 500 posts** (historique conservé)

Cette approche évite de re-tenter sans cesse des posts problématiques lors des mises à jour incrémentales.

**Q : Puis-je déplacer les médias une fois téléchargés sans risques pour la suite ?**  
**R :** **Oui, sans aucun risque** pour le fonctionnement de BSMB !

La base de données (`bsmb.db`) ne stocke **que les métadonnées** :
- URL du post
- Nom du fichier téléchargé
- Type de média (image/vidéo)

Elle ne stocke **pas le chemin complet** des fichiers.

**Ce que vous pouvez faire :**
- ✅ Déplacer les médias où vous voulez
- ✅ Renommer les fichiers
- ✅ Graver sur DVD, cloud, NAS...
- ✅ Supprimer les médias

**Impact :**
- ❌ BSMB ne "voit" plus les fichiers déplacés
- ✅ Les posts sont toujours marqués comme "traités" dans la DB
- ✅ Pas de re-téléchargement automatique (sauf si vous utilisez l'option "Force")

**Q : Que contient la base de données ?**  
**R :** La DB (`bsmb.db`) contient :
- Liste des posts traités (URL, handle, date)
- Liste des médias téléchargés (type, nom de fichier)
- **Elle ne stocke PAS les médias eux-mêmes**, juste le tracking

**Q : Dois-je supprimer mes bookmarks Bluesky après le téléchargement ?**  
**R :** **Non, pas du tout !** Vos bookmarks Bluesky sont indépendants de BSMB.

**Utilisation recommandée :**
1. Gardez vos bookmarks Bluesky actifs
2. Ajoutez de nouveaux posts régulièrement
3. Relancez BSMB périodiquement :
   - Export (Option 1) → met à jour `urls.txt`
   - Téléchargement (Option 2) → récupère seulement les nouveaux

**Avantages de garder les bookmarks :**
- 🔄 Synchronisation facile
- 📱 Accès mobile via l'app Bluesky
- 🔗 Liens toujours actifs
- 💾 BSMB devient votre "sauvegarde locale"

**Si vous supprimez un bookmark par erreur :**
- Le post reste marqué comme traité dans `bsmb.db`
- Le fichier `urls.txt.bak` conserve l'historique précédent
- Vous pouvez retrouver l'URL et re-bookmark

### 🖥️ Compatibilité et installation

**Q : Je suis nul en informatique, que dois-je installer ?**  
**R :** Sur **Windows**, double-cliquez sur `Start.bat`. Tout s'installe automatiquement :
- Python
- Bibliothèques nécessaires
- FFmpeg (traitement vidéo)
- ExifTool (métadonnées images)

Durée totale : ~5-10 minutes. Une connexion internet est requise.

**Q : Est-ce compatible macOS / Linux ?**  
**R :** Oui ! BSMB est **100% compatible multi-OS**. Mais l'installation n'est pas automatique. Vous devez installer manuellement :
```bash
# macOS (via Homebrew)
brew install python ffmpeg exiftool
pip install requests yt-dlp

# Linux (Debian/Ubuntu)
sudo apt install python3 python3-pip ffmpeg libimage-exiftool-perl
pip install requests yt-dlp
```

Puis lancez : `python bsmb.py`

**Q : Puis-je utiliser BSMB sans ffmpeg ou exiftool ?**  
**R :** Oui, BSMB fonctionne sans ces outils mais :
- ❌ Pas de métadonnées dans les vidéos (titre, auteur, date)
- ❌ Pas de métadonnées EXIF dans les images
- ✅ Les médias sont quand même téléchargés et nommés correctement

### 🎨 Interface et menu

**Q : Je ne vois pas toutes les options du menu, pourquoi ?**  
**R :** Le menu est **dynamique** et s'adapte à votre situation :

**Option 2** (Télécharger médias) :
- ❌ **Cachée** si `urls.txt` est vide ou absent
- ✅ **Visible** après avoir fait un export (Option 1)
- 💡 Lancez d'abord l'export des bookmarks !

**Option 5** (Ouvrir dossier) :
- ❌ **Cachée** si aucun média n'a été téléchargé
- ✅ **Visible** dès qu'au moins 1 image ou vidéo existe
- 💡 Téléchargez d'abord des médias (Option 2)

**En résumé :**
```
Première utilisation : Options 1, 4, 6, 9, 0
Après export         : Options 1, 2, 4, 6, 9, 0
Après téléchargement : Options 1, 2, 4, 5, 6, 9, 0
```

Ce système évite les erreurs en masquant les actions impossibles.

### 🔧 Problèmes courants

**Q : "Token invalide" après quelques jours**  
**R :** Le token Bearer expire. Récupérez-en un nouveau (voir `Instructions-token.md`) et relancez l'export.

**Q : "Aucun média trouvé" alors que le post en contient**  
**R :** Vérifiez :
1. Le post est peut-être un **repost non résolu** (listé dans les logs)
2. Le post contient peut-être un type de média non géré (créez une issue GitHub)
3. Utilisez `tools/debug_post.py` pour analyser la structure du post

**Q : Certains posts sont marqués "Échec"**  
**R :** Consultez `logs/failed_downloads_*.txt` pour la liste, et `logs/download_*.log` pour les détails. Causes fréquentes :
- Post supprimé entre l'export et le téléchargement
- Erreur réseau temporaire
- Format de média non reconnu

**Q : "Erreur 500" lors de l'export ou du téléchargement**  
**R :** Erreur serveur Bluesky (temporaire). Attendez quelques minutes et réessayez.

---