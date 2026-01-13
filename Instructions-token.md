# 🔑 Récupération du Token Bearer Bluesky

## ⚠️ IMPORTANT - Confidentialité

Le **Token Bearer** est une clé d'accès **personnelle et confidentielle** à votre compte Bluesky.

- ❌ **NE JAMAIS** le partager avec qui que ce soit
- ❌ **NE JAMAIS** le publier en ligne
- 🔒 Sa durée de vie est limitée (expire après quelques jours ou à la déconnexion)
- ♻️ Il se régénère automatiquement à chaque connexion

---

## 📋 Procédure complète

### Étape 1 : Ouvrir Bluesky dans votre navigateur

1. Connectez-vous sur **https://bsky.app**
2. Assurez-vous d'être connecté à votre compte

### Étape 2 : Accéder à vos Conservés

1. Cliquez sur votre profil (en haut à droite)
2. Sélectionnez **"Conservés"** (ou directement sur **https://bsky.app/saved**)

### Étape 3 : Ouvrir les Outils de développement

#### Sur Firefox
1. Appuyez sur **F12**
2. Cliquez sur l'onglet **"Réseau"** (ou "Network")

#### Sur Chrome/Edge
1. Appuyez sur **F12**
2. Cliquez sur l'onglet **"Network"**

#### Sur Safari
1. Activez le menu Développement : Préférences → Avancées → "Afficher le menu Développement"
2. Menu Développement → "Afficher l'inspecteur Web"
3. Onglet "Réseau"

### Étape 4 : Capturer la requête

1. **Rafraîchissez** la page des Conservés en appuyant sur **F5**
2. Dans l'onglet Réseau, **filtrez** par le terme : `getBookmarks`
3. Deux lignes devraient apparaître (si ce n'est pas le cas, vérifiez que le filtre "Tout" est actif)

### Étape 5 : Copier le Token

1. **Cliquez** sur la ligne avec la méthode **GET** (généralement la première)
2. Dans le panneau de droite, cherchez la section **"En-têtes de la requête"** (ou "Request Headers")
3. Repérez la ligne **"Authorization"**
4. **Clic droit** sur cette ligne → **"Copier la valeur"**

La valeur copiée doit ressembler à :
```
Bearer did:plc:xxxxxxxxxxxxxxxxxx~xxxxxxxxxxxxxxxxxxxxxx
```

### Étape 6 : Enregistrer le Token dans BSMB

Vous avez **deux options** :

#### Option A : Depuis le presse-papier (recommandé)
1. Lancez BSMB
2. Si le token est demandé, choisissez l'option **"1. Coller depuis le presse-papier"**
3. Le token sera automatiquement enregistré

#### Option B : Manuellement
1. Ouvrez le fichier **`Token-Bearer.txt`** avec un éditeur de texte
2. Collez la valeur copiée
3. Sauvegardez le fichier

---

## 🔄 Quand renouveler le Token ?

Vous devrez récupérer un nouveau token si :

- ❌ BSMB affiche "Token invalide" ou "401 Unauthorized"
- 🔓 Vous vous êtes déconnecté de Bluesky
- ⏱️ Plusieurs jours/semaines se sont écoulés
- 🔐 Vous avez changé votre mot de passe

➡️ **Solution** : Répétez simplement la procédure ci-dessus

---

## ❓ Dépannage

### "Je ne vois pas la ligne Authorization"
- Vérifiez que vous avez bien rafraîchi la page (F5)
- Assurez-vous d'être sur la page des Conservés
- Vérifiez que le filtre `getBookmarks` est bien appliqué

### "Le token commence par 'did:plc:' et non 'Bearer'"
- ⚠️ Vous avez copié seulement la valeur après "Bearer "
- Il faut copier **"Bearer "** + la valeur complète

### "BSMB dit que le token est invalide"
- Vérifiez qu'il commence bien par `Bearer ` (avec l'espace)
- Pas d'espaces superflus au début ou à la fin
- Pas de retours à la ligne

---

## 📞 Support

En cas de problème, vérifiez :
1. ✅ Que vous êtes bien connecté sur bsky.app
2. ✅ Que vous avez des Conservés (bookmarks)
3. ✅ Que le token commence par `Bearer `
4. ✅ Qu'il n'y a pas d'espaces superflus