#!/usr/bin/env python3
"""
Internationalisation de BSMB (issue #17) : gettext de la bibliothèque standard.

    from core.i18n import _, _n

    print(_("Compte déconnecté"))
    print(_n("{n} image", "{n} images", nb).format(n=nb))

Les msgid sont les textes français source : sans catalogue (ou pour la langue `fr`),
le texte français est affiché tel quel. Les catalogues vivent dans
`lang/<code>/LC_MESSAGES/bsmb.po` ; le `.mo` binaire est compilé au besoin par
`core/_msgfmt.py` (Python pur) quand il manque ou qu'il est plus vieux que le `.po`.

`init(language)` choisit la langue (`None` ou « auto » : détection d'après la locale du
système). Appelé sans `init()` préalable, `_` initialise la langue détectée au premier
usage. Aucun code ne s'exécute à l'import de ce module.
"""

import contextlib
import gettext
import importlib.util
import io
import locale
import logging
import os
import shutil
import tempfile
import threading
from pathlib import Path

from core.paths import PROJECT_ROOT

DOMAIN = "bsmb"
LANG_DIR = PROJECT_ROOT / "lang"  # catalogues ; installé, le paquet `lang` est à côté de `core` (patchable)
SUPPORTED = ("fr", "en")
DEFAULT_LANGUAGE = "en"  # repli quand la locale n'est pas française

log = logging.getLogger(__name__)  # niveau DEBUG : un échec de compilation ne doit rien afficher
_lock = threading.Lock()
_translation = None  # gettext.NullTranslations / GNUTranslations ; None tant que init() n'a pas eu lieu
_current = DEFAULT_LANGUAGE


def detect_language():
    """Langue d'après la locale du système : « fr » si elle commence par fr, sinon « en ».

    Ordre : locale.getlocale(), puis les variables LC_ALL, LC_MESSAGES, LANG, LANGUAGE.
    Les locales « C » / « POSIX » sont ignorées.
    """
    candidats = []
    try:
        candidats.append(locale.getlocale()[0])
    except (ValueError, TypeError):
        pass
    candidats.extend(os.environ.get(v) for v in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"))
    for candidat in candidats:
        if not candidat:
            continue
        valeur = candidat.strip().lower()
        if not valeur or valeur.split(".")[0] in ("c", "posix"):
            continue
        return "fr" if valeur.startswith("fr") else "en"
    return DEFAULT_LANGUAGE


def _normaliser(language):
    """« fr_FR.UTF-8 » -> « fr » ; langue inconnue -> « en » ; vide / « auto » -> détection."""
    valeur = (language or "").strip().lower()
    if not valeur or valeur == "auto":
        return detect_language()
    code = valeur.replace("-", "_").split("_")[0].split(".")[0]
    return code if code in SUPPORTED else DEFAULT_LANGUAGE


def _compiler(po, mo):
    """Compile `po` en `mo` avec core/_msgfmt.py. Renvoie True si un `.mo` à jour existe ensuite.

    La compilation se fait dans un dossier temporaire, puis le `.mo` est posé par `os.replace`
    (atomique : jamais de fichier tronqué visible). Les messages d'erreur de msgfmt, qui
    n'affiche que sur stderr, sont journalisés seulement en cas d'échec.
    """
    # Contournements du msgfmt.py de CPython, laissé tel quel :
    # - son dictionnaire MESSAGES est global : on en charge une instance neuve à chaque appel ;
    # - il décode en latin-1 le premier msgid qui suit l'en-tête (mojibake si non ASCII) :
    #   on glisse une entrée ASCII sans traduction (ignorée à la compilation) après l'en-tête.
    erreurs = io.StringIO()
    temporaire = None
    try:
        spec = importlib.util.spec_from_file_location("bsmb_msgfmt", Path(__file__).with_name("_msgfmt.py"))
        msgfmt = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(msgfmt)

        texte = po.read_text(encoding="utf-8")
        entete, sep, reste = texte.partition("\n\n")
        texte = f'{entete}{sep}msgid "bsmb-sentinelle"\nmsgstr ""\n\n{reste}'
        mo.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            copie = Path(tmp) / "bsmb.po"
            copie.write_text(texte, encoding="utf-8", newline="\n")
            compile_tmp = Path(tmp) / "bsmb.mo"
            with contextlib.redirect_stderr(erreurs):
                msgfmt.make(str(copie), str(compile_tmp))
            if not compile_tmp.is_file():
                raise OSError("msgfmt n'a produit aucun fichier")
            temporaire = mo.with_name(f"{mo.name}.{os.getpid()}.tmp")
            shutil.copyfile(compile_tmp, temporaire)
            os.replace(temporaire, mo)
            temporaire = None
        return _a_jour(po, mo)
    except (OSError, SystemExit, ImportError, SyntaxError, ValueError) as e:
        log.debug("Compilation de %s impossible : %s %s", po, e, erreurs.getvalue().strip())
        return False
    finally:
        if temporaire is not None:
            with contextlib.suppress(OSError):
                temporaire.unlink()


def _a_jour(po, mo):
    """Vrai si `mo` est un fichier au moins aussi récent que `po`."""
    try:
        return mo.is_file() and mo.stat().st_mtime >= po.stat().st_mtime
    except OSError:
        return False


def _trouver_mo(code, forcer=False):
    """Chemin d'un `.mo` à jour pour `code` (compilé si besoin), ou None sans catalogue.

    `forcer` : recompile même si le `.mo` semble à jour (fichier reconnu comme corrompu).
    """
    po = LANG_DIR / code / "LC_MESSAGES" / f"{DOMAIN}.po"
    mo = po.with_suffix(".mo")
    if not po.is_file():
        return mo if mo.is_file() else None
    if (not forcer and _a_jour(po, mo)) or _compiler(po, mo):
        return mo
    # Dossier du dépôt en lecture seule : repli sur le dossier temporaire
    secours = Path(tempfile.gettempdir()) / "bsmb-i18n" / code / f"{DOMAIN}.mo"
    if (not forcer and _a_jour(po, secours)) or _compiler(po, secours):
        return secours
    return None


def _lire_mo(mo):
    with open(mo, "rb") as f:
        return gettext.GNUTranslations(f)


def _charger(code):
    """Catalogue de `code`. Un `.mo` illisible (tronqué…) est supprimé et recompilé une fois ;
    en dernier recours, le texte source est affiché."""
    forcer = False
    for _essai in range(2):
        mo = _trouver_mo(code, forcer)
        if mo is None:
            break
        try:
            return _lire_mo(mo)
        except Exception as e:  # struct.error, EOFError, OSError, ValueError… selon la corruption
            log.debug("Catalogue %s illisible (%s), recompilation", mo, e)
            with contextlib.suppress(OSError):
                mo.unlink()
            forcer = True
    return gettext.NullTranslations()


def init(language=None):
    """Choisit la langue d'affichage. `None`, « » ou « auto » : détection d'après la locale."""
    global _translation, _current
    code = _normaliser(language)
    traduction = _charger(code)
    with _lock:
        _translation = traduction
        _current = code
    return code


def current_language():
    """Code de la langue active (« fr » ou « en »)."""
    if _translation is None:
        init(None)
    return _current


def _actif():
    if _translation is None:
        init(None)
    return _translation


def _(message):
    """Traduit `message` (texte français source) ; le renvoie tel quel sans traduction."""
    return _actif().gettext(message)


def _n(singulier, pluriel, n):
    """Traduit selon le nombre `n` (règle de pluriel du catalogue de la langue active)."""
    return _actif().ngettext(singulier, pluriel, n)
