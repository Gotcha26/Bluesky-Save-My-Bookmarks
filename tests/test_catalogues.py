"""Catalogues de traduction réels (lang/*/LC_MESSAGES/bsmb.po) : ils protègent contre les oublis.

- toutes les chaînes marquées dans le code sont dans les catalogues, et inversement ;
- le catalogue anglais est complet (aucun msgstr vide) ;
- les marqueurs `{nom}` de chaque traduction sont ceux du texte source ;
- le catalogue français est la source (msgstr identique au msgid) ;
- une traduction réelle s'affiche bien dans l'interface.
"""

import importlib.util
import re

import pytest

from core import cli, i18n
from core.paths import PROJECT_ROOT


def _charger_outil(nom, dossier="tools"):
    spec = importlib.util.spec_from_file_location(nom, PROJECT_ROOT / dossier / f"{nom}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extract_strings = _charger_outil("extract_strings")

LANGUES = ["fr", "en"]
MARQUEURS = re.compile(r"\{(\w+)(?:[:!][^}]*)?\}")


@pytest.fixture(scope="module")
def trouvees():
    entrees, problemes = extract_strings.extraire(PROJECT_ROOT)
    assert problemes == []
    return entrees


def _po(code):
    chemin = PROJECT_ROOT / "lang" / code / "LC_MESSAGES" / "bsmb.po"
    assert chemin.is_file(), f"catalogue manquant : {chemin}"
    return extract_strings.lire_po(chemin)


@pytest.mark.parametrize("code", LANGUES)
def test_catalogue_a_jour_avec_le_code(code, trouvees):
    """Pas de chaîne oubliée (python tools/extract_strings.py --update) ni d'entrée orpheline."""
    catalogue = _po(code)
    assert [m for m in trouvees if m not in catalogue] == []
    assert [m for m in catalogue if m not in trouvees] == []


@pytest.mark.parametrize("code", LANGUES)
def test_les_pluriels_du_catalogue_suivent_le_code(code, trouvees):
    catalogue = _po(code)
    for msgid, entree in trouvees.items():
        assert catalogue[msgid].plural == entree.plural, msgid


def test_catalogue_anglais_complet():
    """Chaque chaîne du catalogue anglais est traduite (toutes les formes de pluriel)."""
    vides = []
    for msgid, entree in _po("en").items():
        formes = 1 if entree.plural is None else 2
        if len(entree.msgstr) < formes or not all(entree.msgstr[:formes]):
            vides.append(msgid)
    assert vides == []


def test_catalogue_francais_est_la_source():
    for msgid, entree in _po("fr").items():
        attendu = [msgid] if entree.plural is None else [msgid, entree.plural]
        assert entree.msgstr == attendu, msgid


@pytest.mark.parametrize("code", LANGUES)
def test_marqueurs_identiques_a_la_source(code):
    """`{n}`, `{erreur}`… doivent se retrouver à l'identique dans la traduction (sinon .format() plante)."""
    fautes = []
    for msgid, entree in _po(code).items():
        sources = [msgid] if entree.plural is None else [msgid, entree.plural]
        for i, traduction in enumerate(entree.msgstr):
            source = sources[min(i, len(sources) - 1)]
            if sorted(MARQUEURS.findall(traduction)) != sorted(MARQUEURS.findall(source)):
                fautes.append((msgid, traduction))
    assert fautes == []


@pytest.mark.parametrize("code", LANGUES)
def test_le_po_se_compile(code, tmp_path):
    msgfmt = _charger_outil("_msgfmt", "core")
    po = PROJECT_ROOT / "lang" / code / "LC_MESSAGES" / "bsmb.po"
    mo = tmp_path / "bsmb.mo"
    msgfmt.make(str(po), str(mo))
    assert mo.stat().st_size > 0


def test_traductions_reelles_dans_l_interface(capsys, tmp_config):
    i18n.init("en")
    assert i18n._("Compte déconnecté") == "Account disconnected"
    assert i18n._n("{n} image", "{n} images", 1) == "{n} image"
    assert i18n._n("{n} image", "{n} images", 3) == "{n} images"
    assert i18n._n("il y a {n} jour", "il y a {n} jours", 2) == "{n} days ago"

    cli.cmd_status(tmp_config)
    sortie = capsys.readouterr().out
    assert "Last synchronization" in sortie
    assert "never" in sortie
    assert "Dernière synchronisation" not in sortie

    i18n.init("fr")
    cli.cmd_status(tmp_config)
    sortie = capsys.readouterr().out
    assert "Dernière synchronisation" in sortie
    assert "jamais" in sortie


def test_plusieurs_pluriels_francais_reels():
    i18n.init("fr")
    assert i18n._n("il y a {n} jour", "il y a {n} jours", 0) == "il y a {n} jour"
    assert i18n._n("il y a {n} jour", "il y a {n} jours", 2) == "il y a {n} jours"
