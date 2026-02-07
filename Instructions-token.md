# 🔑 Authentification Bluesky - Deux méthodes

BSMB supporte **deux méthodes** pour accéder à vos bookmarks Bluesky. Choisissez celle qui vous convient!

---

## ⭐ Méthode 1 : Authentification automatique via createSession (RECOMMANDÉ)

**Avantages:**
- ✅ Token généré **automatiquement** à chaque lancement
- ✅ **Pas besoin** de le recopier manuellement
- ✅ **Très sécurisé** : stocké localement dans config.json
- ✅ **Rapide** : une configuration, c'est tout!

### Procédure

#### Étape 1 : Créer un App Password sur Bluesky
1. Allez sur **https://bsky.app → Settings → App Passwords**
2. Cliquez sur **"Add App Password"**
3. Nommez-le (ex: "BSMB")
4. **Copiez** le mot de passe généré : `xxxx-xxxx-xxxx-xxxx`

#### Étape 2 : Configurer dans BSMB
1. Lancez **BSMB**
2. **Menu Configuration → Option 1 : Identifiants Bluesky**
3. Entrez votre handle : `@user.bsky.social`
4. Entrez votre App Password : `xxxx-xxxx-xxxx-xxxx`
5. BSMB teste la connexion automatiquement
6. **C'est fait!** ✨

À partir de maintenant, BSMB générera un nouveau token **automatiquement** à chaque lancement!

---

## 🔄 Méthode 2 : Token Bearer manuel (FALLBACK)

**Quand l'utiliser:**
- ⚠️ Si createSession ne fonctionne pas
- ⚠️ Si vous préférez ne pas stocker votre App Password
- ⚠️ Utilisation legacy (mode rétrocompatible)

**Inconvénients:**
- ❌ Token **expire** après quelques jours
- ❌ Besoin de le **recopier manuellement**
- ❌ Plus de manipulations (DevTools)

### Procédure

#### Étape 1 : Récupérer le Token Bearer

**Sur Firefox / Chrome / Edge:**
1. Connectez-vous sur **https://bsky.app**
2. Allez dans vos **Conservés** (https://bsky.app/saved)
3. Appuyez sur **F12** (DevTools)
4. Cliquez sur l'onglet **"Réseau"** (Network)
5. **Rafraîchissez** la page (F5)
6. **Filtrez** par : `getBookmarks`
7. Cliquez sur la ligne **GET**
8. Cherchez **"En-têtes de la requête"** (Request Headers)
9. Trouvez la ligne **"Authorization"**
10. **Clic droit → Copier la valeur**

La valeur copiée ressemble à :
```
Bearer did:plc:xxxxxxxxxxxxxxxxxx~xxxxxxxxxxxxxxxxxxxxxx
```

**Sur Safari:**
1. Activez le menu Développement : Préférences → Avancées → "Afficher le menu Développement"
2. Menu Développement → "Afficher l'inspecteur Web"
3. Onglet "Réseau"
4. Suivez les mêmes étapes que Chrome/Firefox

#### Étape 2 : Enregistrer le Token

**Option A : Depuis BSMB (presse-papier)**
1. Lancez **BSMB**
2. Quand le token est demandé, choisissez **"Option 2 : Coller depuis le presse-papier"**
3. Le token est automatiquement enregistré

**Option B : Fichier Token-Bearer.txt**
1. Ouvrez **`Token-Bearer.txt`** avec un éditeur de texte
2. Collez la valeur copiée
3. **Sauvegardez**

---

## 🔄 Quand renouveler le Token Bearer?

Vous devrez récupérer un nouveau token si :

- ❌ BSMB affiche **"Token invalide"** ou **"401 Unauthorized"**
- 🔓 Vous vous êtes **déconnecté** de Bluesky
- ⏱️ **Plusieurs jours/semaines** se sont écoulés
- 🔐 Vous avez **changé votre mot de passe**

➡️ **Solution** : Répétez simplement la **Procédure Étape 1 + 2** ci-dessus

---

## ⚠️ Sécurité et confidentialité

### Token Bearer (méthode 2)
- ❌ **NE JAMAIS** partager avec qui que ce soit
- ❌ **NE JAMAIS** publier en ligne
- 🔒 Expire après quelques jours ou à la déconnexion
- ♻️ Se régénère automatiquement à chaque connexion Bluesky

### App Password (méthode 1)
- ❌ **NE JAMAIS** partager avec qui que ce soit
- 🔒 Stocké **localement** dans `config.json` (fichier local, hors Git)
- ✅ Jamais transmis en HTTP non-sécurisé
- ✅ Rarement (1x/lancement) envoyé à bsky.social via HTTPS
- ✅ Jamais uploadé ailleurs

---

## ❓ Dépannage

### "Je ne vois pas la ligne Authorization (méthode 2)"
```
→ Vérifiez que vous avez bien rafraîchi la page (F5)
→ Assurez-vous d'être sur la page des Conservés
→ Vérifiez que le filtre `getBookmarks` est bien appliqué
→ Vérifiez que le filtre "Tout" est sélectionné
```

### "Le token commence par 'did:plc:' et non 'Bearer' (méthode 2)"
```
⚠️ Vous avez copié seulement la valeur APRÈS "Bearer "
Il faut copier : "Bearer " + la valeur complète
```

### "BSMB dit que le token est invalide (méthode 2)"
```
→ Vérifiez qu'il commence bien par 'Bearer ' (avec l'espace)
→ Pas d'espaces superflus au début ou à la fin
→ Pas de retours à la ligne
→ Token peut être expiré → recréez un nouveau
```

### "Échec de l'authentification : Identifiants invalides (méthode 1)"
```
→ Vérifiez votre handle (@user.bsky.social)
→ Vérifiez que l'App Password est au format xxxx-xxxx-xxxx-xxxx
→ L'App Password peut avoir expiré → recréez un nouveau sur bsky.app
→ Vérifiez votre connexion Internet
```

### "Impossible de se connecter à bsky.social (méthode 1)"
```
→ Vérifiez votre connexion Internet
→ Vérifiez que bsky.social est accessible
→ Essayez de relancer BSMB
→ Si le problème persiste, essayez la méthode 2 (Token Bearer manuel)
```

---

## 📊 Récapitulatif

| Aspect | **Méthode 1 (createSession)** | **Méthode 2 (Token Bearer)** |
|--------|-------|--------|
| **Configuration** | Handle + App Password (une seule fois) | Token Bearer (à chaque fois) |
| **Renouvellement** | ✅ Automatique à chaque lancement | ❌ Manuel (token expire) |
| **Sécurité** | ✅ Excellent (App Password local) | ⚠️ Moyen (Token stocké fichier) |
| **Facilité** | ✅⭐⭐⭐⭐⭐ Très facile | ⚠️⭐⭐⭐ Moyen |
| **Recommandation** | ✅ À préférer | ❌ Fallback uniquement |

---

**Besoin d'aide?** Consultez [README.md](README.md) ou ouvrez une [GitHub Issue](https://github.com/Gotcha26/Bluesky-Save-My-Bookmarks/issues)