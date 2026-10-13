"""tools/extract_strings.py : extraction des chaînes et lecture / écriture des .po (issue #17)."""

import importlib.util

import pytest

from core.paths import PROJECT_ROOT


def _charger(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extract_strings = _charger("extract_strings", PROJECT_ROOT / "tools" / "extract_strings.py")
msgfmt = _charger("msgfmt", PROJECT_ROOT / "core" / "_msgfmt.py")

SOURCE = """\
from core.i18n import _, _n


def f(nb, x):
    print(_("Bonjour"))
    print(_("Texte " "coupé"))
    print(_n("{n} jour", "{n} jours", nb).format(n=nb))
    print(_("Bonjour"))
    print(_(x))
    print(_("avec \\"guillemets\\" et\\nretour"))
"""


@pytest.fixture
def depot(tmp_path):
    (tmp_path / "core").mkdir()
    (tmp_path / "bsmb.py").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "core" / "autre.py").write_text('print(_("Ailleurs"))\n', encoding="utf-8")
    return tmp_path


def test_extraction_des_litteraux(depot):
    entrees, problemes = extract_strings.extraire(depot)
    assert list(entrees) == ["Bonjour", "Texte coupé", "{n} jour", 'avec "guillemets" et\nretour', "Ailleurs"]
    assert entrees["{n} jour"].plural == "{n} jours"
    assert entrees["Bonjour"].refs == ["bsmb.py:5", "bsmb.py:8"]
    assert len(problemes) == 1
    assert "bsmb.py:9" in problemes[0]


def test_ecriture_puis_lecture_identique(depot, tmp_path):
    entrees, _problemes = extract_strings.extraire(depot)
    po = tmp_path / "x" / "bsmb.po"
    a_ecrire = extract_strings.construire("en", entrees, {})
    a_ecrire[0].msgstr = ["Hello"]
    a_ecrire[2].msgstr = ["{n} day", "{n} days"]
    extract_strings.ecrire_po(po, "en", a_ecrire)
    relu = extract_strings.lire_po(po)
    assert list(relu) == list(entrees)
    assert relu["Bonjour"].msgstr == ["Hello"]
    assert relu["{n} jour"].msgstr == ["{n} day", "{n} days"]
    assert relu['avec "guillemets" et\nretour'].msgstr == [""]


def test_fr_est_la_source_identique(depot):
    entrees, _problemes = extract_strings.extraire(depot)
    fr = {e.msgid: e for e in extract_strings.construire("fr", entrees, {})}
    assert fr["Bonjour"].msgstr == ["Bonjour"]
    assert fr["{n} jour"].msgstr == ["{n} jour", "{n} jours"]


def test_mise_a_jour_conserve_les_traductions_et_retire_les_orphelins(depot, tmp_path):
    entrees, _problemes = extract_strings.extraire(depot)
    existantes = {
        "Bonjour": extract_strings.Entree("Bonjour", None, ["Hello"]),
        "Disparue": extract_strings.Entree("Disparue", None, ["Gone"]),
    }
    en = {e.msgid: e for e in extract_strings.construire("en", entrees, existantes)}
    assert en["Bonjour"].msgstr == ["Hello"]
    assert en["Ailleurs"].msgstr == []
    assert "Disparue" not in en


def test_ecarts(depot, tmp_path):
    entrees, _problemes = extract_strings.extraire(depot)
    lang = tmp_path / "lang"
    extract_strings.ecrire_po(
        extract_strings.chemin_po("en", lang),
        "en",
        [
            extract_strings.Entree("Bonjour", None, ["Hello"]),
            extract_strings.Entree("Vieille", None, ["Old"]),
        ],
    )
    manquants, orphelins = extract_strings.ecarts("en", entrees, lang)
    assert "Ailleurs" in manquants
    assert "Bonjour" not in manquants
    assert orphelins == ["Vieille"]


def test_po_genere_compilable_par_msgfmt(depot, tmp_path):
    import gettext

    entrees, _problemes = extract_strings.extraire(depot)
    en = extract_strings.construire("en", entrees, {})
    for e in en:
        e.msgstr = [f"EN {e.msgid}"] if e.plural is None else ["EN un", "EN plusieurs"]
    po = tmp_path / "bsmb.po"
    extract_strings.ecrire_po(po, "en", en)
    mo = tmp_path / "bsmb.mo"
    msgfmt.make(str(po), str(mo))
    with open(mo, "rb") as f:
        t = gettext.GNUTranslations(f)
    assert t.gettext("Bonjour") == "EN Bonjour"
    assert t.gettext("Texte coupé") == "EN Texte coupé"
    assert t.ngettext("{n} jour", "{n} jours", 1) == "EN un"
    assert t.ngettext("{n} jour", "{n} jours", 2) == "EN plusieurs"
    assert t.gettext('avec "guillemets" et\nretour') == 'EN avec "guillemets" et\nretour'
