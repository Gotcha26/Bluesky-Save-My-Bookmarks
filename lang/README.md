# Traductions de BSMB

L'interface utilise `gettext` (bibliothèque standard, aucune dépendance). Le texte source, en
français, sert de `msgid` : `_("Compte déconnecté")`. Le module `core/i18n.py` expose :

| Nom | Rôle |
|-----|------|
| `_(texte)` | traduit un texte (le renvoie tel quel s'il n'a pas de traduction) |
| `_n(singulier, pluriel, n)` | choisit la forme selon le nombre (`ngettext`) |
| `init(language)` | choisit la langue (`None` ou `"auto"` : d'après la locale du système) |
| `current_language()` | code de la langue active |

La langue vient, par ordre de priorité, de `--lang` (CLI), de `config["language"]` (menu
**Paramètres > L. Langue**), puis de la locale du système (`fr` si elle commence par `fr`, sinon `en`).

## Arborescence

```
lang/
  fr/LC_MESSAGES/bsmb.po    # langue source : msgstr identique au msgid
  en/LC_MESSAGES/bsmb.po    # traduction anglaise
```

Les `.mo` (binaires) ne sont pas versionnés : `core/i18n.py` les compile au démarrage, avec
`core/_msgfmt.py` (copie inchangée de `Tools/i18n/msgfmt.py` de CPython 3.13, licence PSF ;
`core/i18n.py` contourne ses défauts connus), quand ils manquent ou sont plus
vieux que le `.po`. Pour les compiler à la main (même résultat avec `msgfmt` de GNU gettext) :

```bash
python core/_msgfmt.py -o lang/en/LC_MESSAGES/bsmb.mo lang/en/LC_MESSAGES/bsmb.po
```

## Écrire une chaîne dans le code

- Texte visible : `_("Synchronisation terminée")`. Les arguments doivent être des littéraux
  (pas de f-string dans `_()`).
- Valeurs variables : marqueurs nommés puis `.format()` :
  `_("Page {page}... {count} bookmarks").format(page=p, count=n)`.
- Pluriels : `_n("{n} image", "{n} images", n).format(n=n)`.
- Les codes couleur restent **hors** des `msgid` : `f"{c.DIM}{_('Retour')}{c.RESET}"`. Si un
  marqueur doit être coloré, passez-le déjà coloré à `.format()`.
- Pas de `_()` à l'import d'un module (le texte serait figé avant `init()`) : traduisez dans une
  fonction.
- Pas de backslash ni de guillemets identiques dans une f-string (Python 3.11) : calculez le
  texte avant.
- Ne se traduisent pas : messages du log fichier (`log_func(..., to_console=False)`), noms de
  fichiers, clés de configuration, messages d'exception internes.

## Mettre à jour les catalogues

```bash
python tools/extract_strings.py            # résumé : à ajouter / orphelines / sans traduction
python tools/extract_strings.py --update   # réécrit les .po (fr = source, en = traductions conservées)
python tools/extract_strings.py --check    # code 1 si un catalogue n'est pas à jour
```

Les nouveaux `msgid` arrivent avec un `msgstr` vide dans les langues autres que `fr` : il reste à
les traduire à la main. Les entrées qui ne sont plus dans le code sont supprimées.

`tests/test_catalogues.py` protège les catalogues : toutes les chaînes du code sont présentes (et
aucune n'est orpheline), aucun `msgstr` anglais n'est vide, les marqueurs `{nom}` sont ceux du
texte source.

## Ajouter une langue

1. Déclarer le code dans `tools/extract_strings.py` (dictionnaire `LANGUES`, avec sa règle de
   pluriel gettext) et dans `core/i18n.py` (`SUPPORTED`), puis dans `core/cli.py` (`LANGUES_CLI`),
   `bsmb.py` (`LANGUES_NOMS` et les choix de `_edit_language`) et `tests/test_catalogues.py`
   (`LANGUES`).
2. `python tools/extract_strings.py --update` crée `lang/<code>/LC_MESSAGES/bsmb.po`.
3. Traduire tous les `msgstr` (en conservant les marqueurs `{nom}` et les espaces d'alignement des
   menus), puis lancer `python -m pytest tests/test_catalogues.py`.
