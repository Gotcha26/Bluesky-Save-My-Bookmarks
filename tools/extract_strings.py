#!/usr/bin/env python3
"""
Extraction des chaînes traduisibles de BSMB vers les catalogues gettext (issue #17).

Parcourt bsmb.py, core/, api/ et downloaders/ à la recherche des appels `_("…")` et
`_n("singulier", "pluriel", n)` (arguments littéraux uniquement) et tient à jour
`lang/<code>/LC_MESSAGES/bsmb.po` :

    python tools/extract_strings.py            # résumé, sans rien écrire
    python tools/extract_strings.py --check    # code 1 si un catalogue n'est pas à jour
    python tools/extract_strings.py --update   # réécrit les catalogues

- `fr` est la langue source : msgstr = msgid (régénéré à chaque mise à jour).
- Pour les autres langues, les traductions existantes sont conservées ; les nouveaux msgid
  reçoivent un msgstr vide à traduire, et les msgid qui ne sont plus dans le code sont supprimés.

Aucune dépendance (ni xgettext, ni Babel).
"""

import argparse
import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
LANG_DIR = RACINE / "lang"
SOURCES = ("bsmb.py", "core", "api", "downloaders")
LANGUES = {
    "fr": ("français", "(n > 1)"),
    "en": ("anglais", "(n != 1)"),
}
SOURCE_LANGUE = "fr"


@dataclass
class Entree:
    """Une entrée de catalogue : msgid, pluriel éventuel, traduction(s) et références."""

    msgid: str
    plural: str | None = None
    msgstr: list[str] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)


def fichiers_sources(racine=RACINE):
    """Les .py à parcourir, dans un ordre stable."""
    resultat = []
    for nom in SOURCES:
        chemin = racine / nom
        if chemin.is_file():
            resultat.append(chemin)
        elif chemin.is_dir():
            resultat.extend(sorted(chemin.glob("*.py")))
    return resultat


def _texte(noeud):
    """Valeur d'un littéral chaîne, ou None si le nœud n'en est pas un."""
    if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
        return noeud.value
    return None


def extraire(racine=RACINE):
    """Renvoie (entrées par msgid, problèmes) pour tout le code source.

    Un problème est un appel `_()` / `_n()` dont les arguments ne sont pas des littéraux
    (l'extraction ne pourrait pas les voir).
    """
    entrees = {}
    problemes = []
    for fichier in fichiers_sources(racine):
        rel = fichier.relative_to(racine).as_posix()
        arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=rel)
        for noeud in ast.walk(arbre):
            if not (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Name)):
                continue
            nom = noeud.func.id
            if nom == "_":
                attendu = 1
            elif nom == "_n":
                attendu = 3
            else:
                continue
            ref = f"{rel}:{noeud.lineno}"
            if len(noeud.args) != attendu or noeud.keywords:
                problemes.append(f"{ref} : {nom}() attend {attendu} argument(s) positionnel(s)")
                continue
            msgid = _texte(noeud.args[0])
            plural = _texte(noeud.args[1]) if nom == "_n" else None
            if msgid is None or (nom == "_n" and plural is None):
                problemes.append(f"{ref} : argument de {nom}() non littéral")
                continue
            entree = entrees.setdefault(msgid, Entree(msgid, plural))
            if entree.plural != plural:
                problemes.append(f"{ref} : « {msgid} » utilisé avec et sans pluriel (ou pluriels différents)")
            entree.refs.append(ref)
    for entree in entrees.values():
        entree.refs.sort(key=_cle_ref)
    return dict(sorted(entrees.items(), key=lambda kv: _cle_ref(kv[1].refs[0]))), problemes


def _cle_ref(ref):
    fichier, _sep, ligne = ref.rpartition(":")
    return (fichier, int(ligne))


# ─── Lecture / écriture des .po ──────────────────────────────


def _echapper(texte):
    return (
        texte.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )


def _citer(texte):
    return f'"{_echapper(texte)}"'


def lire_po(chemin):
    """Lit un .po : renvoie {msgid: Entree} (l'en-tête, msgid vide, est ignoré)."""
    entrees = {}
    courant = None  # (champ, index) en cours de lecture
    brut = {"msgid": "", "plural": None, "msgstr": {}}

    def clore():
        if brut["msgid"] or brut["plural"] is not None:
            nb = max(brut["msgstr"]) + 1 if brut["msgstr"] else 0
            msgstr = [brut["msgstr"].get(i, "") for i in range(nb)]
            entrees[brut["msgid"]] = Entree(brut["msgid"], brut["plural"], msgstr)
        brut.update(msgid="", plural=None, msgstr={})

    if not Path(chemin).is_file():
        return entrees
    for ligne in Path(chemin).read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#"):
            if not ligne and courant is not None:
                clore()
                courant = None
            continue
        if ligne.startswith("msgid_plural"):
            courant = ("plural", 0)
            brut["plural"] = ast.literal_eval(ligne[len("msgid_plural") :].strip())
        elif ligne.startswith("msgid"):
            if courant is not None and courant[0] == "msgstr":
                clore()
            courant = ("msgid", 0)
            brut["msgid"] = ast.literal_eval(ligne[5:].strip())
        elif ligne.startswith("msgstr"):
            reste = ligne[6:]
            index = 0
            if reste.startswith("["):
                index = int(reste[1 : reste.index("]")])
                reste = reste[reste.index("]") + 1 :]
            courant = ("msgstr", index)
            brut["msgstr"][index] = ast.literal_eval(reste.strip())
        elif ligne.startswith('"') and courant is not None:
            suite = ast.literal_eval(ligne)
            champ, index = courant
            if champ == "msgstr":
                brut["msgstr"][index] += suite
            elif champ == "plural":
                brut["plural"] += suite
            else:
                brut["msgid"] += suite
    clore()
    return entrees


def _entete(code):
    nom, regle = LANGUES[code]
    return (
        f"# Catalogue de BSMB ({nom}). Généré par tools/extract_strings.py.\n"
        'msgid ""\n'
        'msgstr ""\n'
        '"Project-Id-Version: BSMB\\n"\n'
        f'"Language: {code}\\n"\n'
        '"MIME-Version: 1.0\\n"\n'
        '"Content-Type: text/plain; charset=UTF-8\\n"\n'
        '"Content-Transfer-Encoding: 8bit\\n"\n'
        f'"Plural-Forms: nplurals=2; plural={regle};\\n"\n'
    )


def ecrire_po(chemin, code, entrees):
    """Écrit le catalogue `code` avec les entrées données (msgstr déjà renseignés)."""
    blocs = [_entete(code)]
    for e in entrees:
        lignes = [f"#: {' '.join(e.refs)}"] if e.refs else []
        lignes.append(f"msgid {_citer(e.msgid)}")
        if e.plural is None:
            lignes.append(f"msgstr {_citer(e.msgstr[0] if e.msgstr else '')}")
        else:
            lignes.append(f"msgid_plural {_citer(e.plural)}")
            for i in range(2):
                valeur = e.msgstr[i] if i < len(e.msgstr) else ""
                lignes.append(f"msgstr[{i}] {_citer(valeur)}")
        blocs.append("\n".join(lignes) + "\n")
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text("\n".join(blocs), encoding="utf-8", newline="\n")


def chemin_po(code, lang_dir=None):
    return (lang_dir or LANG_DIR) / code / "LC_MESSAGES" / "bsmb.po"


def construire(code, trouvees, existantes):
    """Entrées à écrire pour `code` : source identique en `fr`, traductions conservées sinon."""
    resultat = []
    for msgid, trouvee in trouvees.items():
        if code == SOURCE_LANGUE:
            msgstr = [msgid] if trouvee.plural is None else [msgid, trouvee.plural]
        else:
            ancienne = existantes.get(msgid)
            msgstr = list(ancienne.msgstr) if ancienne and ancienne.plural == trouvee.plural else []
        resultat.append(Entree(msgid, trouvee.plural, msgstr, list(trouvee.refs)))
    return resultat


def ecarts(code, trouvees, lang_dir=None):
    """(manquants, orphelins) : msgid du code absents du catalogue, et l'inverse."""
    existantes = lire_po(chemin_po(code, lang_dir))
    manquants = [m for m in trouvees if m not in existantes]
    orphelins = [m for m in existantes if m not in trouvees]
    return manquants, orphelins


def main(argv=None):
    parser = argparse.ArgumentParser(description="Extrait les chaînes traduisibles de BSMB.")
    groupe = parser.add_mutually_exclusive_group()
    groupe.add_argument("--update", action="store_true", help="réécrit les catalogues")
    groupe.add_argument("--check", action="store_true", help="échoue si un catalogue n'est pas à jour")
    args = parser.parse_args(argv)

    trouvees, problemes = extraire()
    for p in problemes:
        print(f"ATTENTION {p}", file=sys.stderr)
    print(f"{len(trouvees)} chaînes dans le code")

    code_retour = 1 if problemes else 0
    for code in LANGUES:
        po = chemin_po(code)
        manquants, orphelins = ecarts(code, trouvees)
        existantes = lire_po(po)
        vides = sum(1 for e in existantes.values() if e.msgid in trouvees and not any(e.msgstr))
        print(
            f"{po.relative_to(RACINE).as_posix()} : {len(manquants)} à ajouter, "
            f"{len(orphelins)} orpheline(s), {vides} sans traduction"
        )
        if args.update:
            ecrire_po(po, code, construire(code, trouvees, existantes))
        elif args.check and (manquants or orphelins):
            code_retour = 1
    return code_retour


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
