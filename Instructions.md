# BMB - Bsky My Bookmarks
Utilitaire en ligne de commandes pour télécharger ses "Conservés" (Singets / Bookmarks).

#### Sémantique

Dans la suite de cette procédure, je désigne sous le terme "_Bookmarks_" ce qui est affiché en français dans l'interface de Bluesky comme étant les "_Conservés_".

## Les pré-requis

## 1- Récupérer les URLs

#### Contexte / explications

Il n'y a pas d'autres moyens que d'intercépter une requette à l'API via la console de développement de votre navigateur, pour récupérer un "Token Bearer".  
C'est grâce à cette clé **unique et personnelle** (périmable) que le lien va pouvoir être fait et que le script va pouvoir se faire passer par vous le temps de parcourir vos _Bookmarks_ et ainsi collecter la liste de vos posts mis de cotés ("_Conservés_").

### Vous devez faire

IMPORTANT !
Ne divulgez JAMAIS à personne le token que nous allons rechercher.  
Même si sa durée de vie est limité et qu'une simple déconnection de votre compte permet de révoquer ce token, le risque encouru est que n'importe qui pourrait se faire pour vous avec cette information.

#### Firefox

1. Ouvrez votre navigateur avec la page de bsky.app (votre murs).
2. Partagez votre écran en deux pour être plus à l'aise pour la suite (non obligatoire).
3. Ouvrez la page de vos _Bookmarks_. (bsky.app/saved)
4. Appuyez sur **F12** afin de faire apparaitre la fenêtre des **Outils de développement**.
5. Cliquez sur l'onglet "Réseau".
6. Appuyez sur **F5** afin de rafraichir la page _Bookmarks_ pour remplir la fenêtre des **Outils de développement** avec des informations à jour.
7. Filtrez les URL avec le terme **_getBookmarks_**.
8. Normalement, seuls 2 lignes devrez apparaître.
   1. Si ce n'est pas le cas, regardez d'avoir appliqué le filtre précédent tout en aillant "**Tout**" de séléctionné comme filtre actif.
9. Cliquez sur la ligne qui fait mention de la méthode "**GET**" (la première ligne généralement).
10. Une nouvelle section apparait dévoilant les détails, notement la partie "**En-tête**".
11. Dans la portion nommée "_En-têtes de la requête_" repérez la ligne "**Authorization**"
12. Faites un clic droit dessus pour "**Copier la valeur**".

Vous venez de récupérer le **TOKEN BAERER** qui va permettre au script de se faire passer pour vous car il va utiliser cette clé telle une carte d'identité.

#### Enregistre le token

Inscrivez tout simplement le token ainsi obenu dans le fichier **_`Token-Baerer.txt`_**  
Le format doit être du style :
```
Baerer vqrg4865...
```

### Lancer le script

Vous pouvez à présent lancer le script **_`1_export_bsky_bookmarks.bat`_** 

* Un nouveau fichier _URLS.txt_ apparaît. Il contient tout vos _Bookmarks_.
* Le script est conçu pour s'arrêter après 5 pages (tentitaves) vides 
* Les liens sont lisibles et traduits au format "humain", comme les URL qui nous _parlent_.

A la fin, vous pouvez fermer la fenêtre.