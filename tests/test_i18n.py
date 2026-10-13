"""Internationalisation (issue #17) : core/i18n.py, compilation des .mo à la volée."""

import locale
import os
import time

import pytest

from core import i18n

PO_EN = """\
msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=2; plural=(n != 1);\\n"

msgid "Compte déconnecté"
msgstr "Account disconnected"

msgid "Retour"
msgstr "Back"

msgid "{n} jour"
msgid_plural "{n} jours"
msgstr[0] "{n} day"
msgstr[1] "{n} days"
"""

PO_FR = """\
msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=2; plural=(n > 1);\\n"

msgid "Compte déconnecté"
msgstr "Compte déconnecté"

msgid "{n} jour"
msgid_plural "{n} jours"
msgstr[0] "{n} jour"
msgstr[1] "{n} jours"
"""


def _ecrire_catalogue(racine, code, contenu):
    dossier = racine / code / "LC_MESSAGES"
    dossier.mkdir(parents=True)
    po = dossier / "bsmb.po"
    po.write_text(contenu, encoding="utf-8")
    return po


@pytest.fixture
def lang_dir(tmp_path, monkeypatch):
    """Dossier `lang` factice avec un catalogue en et un catalogue fr."""
    racine = tmp_path / "lang"
    _ecrire_catalogue(racine, "en", PO_EN)
    _ecrire_catalogue(racine, "fr", PO_FR)
    monkeypatch.setattr(i18n, "LANG_DIR", racine)
    return racine


@pytest.fixture
def locale_neutre(monkeypatch):
    """Aucune information de locale : ni getlocale() ni variables d'environnement."""
    monkeypatch.setattr(locale, "getlocale", lambda *a, **k: (None, None))
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        monkeypatch.delenv(var, raising=False)


# ─── Traduction ──────────────────────────────────────────────


def test_anglais_renvoie_la_traduction(lang_dir):
    assert i18n.init("en") == "en"
    assert i18n._("Compte déconnecté") == "Account disconnected"
    assert i18n.current_language() == "en"


def test_francais_renvoie_le_texte_source(lang_dir):
    assert i18n.init("fr") == "fr"
    assert i18n._("Compte déconnecté") == "Compte déconnecté"
    assert i18n.current_language() == "fr"


def test_chaine_absente_du_catalogue_renvoie_la_source(lang_dir):
    i18n.init("en")
    assert i18n._("Texte inconnu du catalogue") == "Texte inconnu du catalogue"


def test_catalogue_absent_renvoie_la_source(tmp_path, monkeypatch):
    vide = tmp_path / "lang_vide"
    vide.mkdir()
    monkeypatch.setattr(i18n, "LANG_DIR", vide)
    assert i18n.init("en") == "en"
    assert i18n._("Compte déconnecté") == "Compte déconnecté"


def test_dossier_lang_inexistant_renvoie_la_source(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "LANG_DIR", tmp_path / "n_existe_pas")
    i18n.init("en")
    assert i18n._("Compte déconnecté") == "Compte déconnecté"


def test_pluriel_anglais(lang_dir):
    i18n.init("en")
    assert i18n._n("{n} jour", "{n} jours", 1) == "{n} day"
    assert i18n._n("{n} jour", "{n} jours", 0) == "{n} days"
    assert i18n._n("{n} jour", "{n} jours", 5) == "{n} days"


def test_pluriel_francais_zero_est_singulier(lang_dir):
    i18n.init("fr")
    assert i18n._n("{n} jour", "{n} jours", 0) == "{n} jour"
    assert i18n._n("{n} jour", "{n} jours", 1) == "{n} jour"
    assert i18n._n("{n} jour", "{n} jours", 2) == "{n} jours"


def test_pluriel_sans_catalogue_regle_par_defaut(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "LANG_DIR", tmp_path)
    i18n.init("en")
    assert i18n._n("{n} jour", "{n} jours", 1) == "{n} jour"
    assert i18n._n("{n} jour", "{n} jours", 3) == "{n} jours"


def test_changement_de_langue_a_chaud(lang_dir):
    i18n.init("en")
    assert i18n._("Compte déconnecté") == "Account disconnected"
    i18n.init("fr")
    assert i18n._("Compte déconnecté") == "Compte déconnecté"


# ─── Choix de la langue ──────────────────────────────────────


@pytest.mark.parametrize(
    ("demande", "attendu"),
    [("fr", "fr"), ("en", "en"), ("FR", "fr"), ("fr_FR.UTF-8", "fr"), ("en-US", "en"), ("de", "en")],
)
def test_langue_explicite_normalisee(lang_dir, demande, attendu):
    assert i18n.init(demande) == attendu


@pytest.mark.parametrize("vide", [None, "", "auto", "  "])
def test_langue_vide_ou_auto_detecte(lang_dir, locale_neutre, monkeypatch, vide):
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")
    assert i18n.init(vide) == "fr"


# ─── Détection de la locale ──────────────────────────────────


@pytest.mark.parametrize(
    ("variable", "valeur", "attendu"),
    [
        ("LANG", "fr_FR.UTF-8", "fr"),
        ("LANG", "fr_CA", "fr"),
        ("LC_ALL", "fr_BE.UTF-8", "fr"),
        ("LC_MESSAGES", "fr_FR", "fr"),
        ("LANGUAGE", "fr:en", "fr"),
        ("LANG", "en_US.UTF-8", "en"),
        ("LANG", "de_DE.UTF-8", "en"),
        ("LANG", "C.UTF-8", "en"),
        ("LANG", "C", "en"),
        ("LANG", "POSIX", "en"),
    ],
)
def test_detection_par_variables_d_environnement(locale_neutre, monkeypatch, variable, valeur, attendu):
    monkeypatch.setenv(variable, valeur)
    assert i18n.detect_language() == attendu


def test_detection_sans_aucune_information_donne_anglais(locale_neutre):
    assert i18n.detect_language() == "en"


def test_detection_locale_c_ignoree_au_profit_de_l_environnement(locale_neutre, monkeypatch):
    monkeypatch.setenv("LC_ALL", "C")
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")
    assert i18n.detect_language() == "fr"


def test_detection_getlocale_prioritaire(monkeypatch):
    monkeypatch.setattr(locale, "getlocale", lambda *a, **k: ("fr_FR", "UTF-8"))
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert i18n.detect_language() == "fr"


def test_detection_locale_windows(monkeypatch):
    monkeypatch.setattr(locale, "getlocale", lambda *a, **k: ("French_France", "1252"))
    assert i18n.detect_language() == "fr"
    monkeypatch.setattr(locale, "getlocale", lambda *a, **k: ("English_United States", "1252"))
    assert i18n.detect_language() == "en"


def test_detection_getlocale_en_erreur(monkeypatch):
    def echec(*a, **k):
        raise ValueError("locale invalide")

    monkeypatch.setattr(locale, "getlocale", echec)
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    monkeypatch.delenv("LANGUAGE", raising=False)
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")
    assert i18n.detect_language() == "fr"


def test_usage_sans_init_detecte_la_langue(lang_dir, locale_neutre, monkeypatch):
    monkeypatch.setattr(i18n, "_translation", None)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert i18n._("Compte déconnecté") == "Account disconnected"
    assert i18n.current_language() == "en"


# ─── Compilation des .mo à la volée ──────────────────────────


def test_mo_compile_si_absent(lang_dir):
    mo = lang_dir / "en" / "LC_MESSAGES" / "bsmb.mo"
    assert not mo.exists()
    i18n.init("en")
    assert mo.is_file()
    assert i18n._("Compte déconnecté") == "Account disconnected"


def test_mo_recompile_s_il_est_plus_vieux_que_le_po(lang_dir):
    po = lang_dir / "en" / "LC_MESSAGES" / "bsmb.po"
    mo = po.with_suffix(".mo")
    i18n.init("en")
    # le .po est modifié après la compilation
    po.write_text(PO_EN.replace("Account disconnected", "Account signed out"), encoding="utf-8")
    passe = time.time() - 100
    os.utime(mo, (passe, passe))
    assert mo.stat().st_mtime < po.stat().st_mtime
    i18n.init("en")
    assert i18n._("Compte déconnecté") == "Account signed out"


def test_mo_a_jour_n_est_pas_recompile(lang_dir, monkeypatch):
    i18n.init("en")
    appels = []
    monkeypatch.setattr(i18n, "_compiler", lambda po, mo: appels.append(po) or True)
    i18n.init("en")
    assert appels == []
    assert i18n._("Compte déconnecté") == "Account disconnected"


def test_po_invalide_repli_sur_la_source(tmp_path, monkeypatch):
    racine = tmp_path / "lang"
    _ecrire_catalogue(racine, "en", 'msgid "a"\nmsgstr "b"\nmsgstr "c" garbage\n')
    monkeypatch.setattr(i18n, "LANG_DIR", racine)
    monkeypatch.setattr(i18n.tempfile, "gettempdir", lambda: str(tmp_path / "tmp"))
    i18n.init("en")
    assert i18n._("Compte déconnecté") == "Compte déconnecté"


def test_cible_impossible_a_ecrire_repli_temporaire_reel(lang_dir, tmp_path, monkeypatch, capsys):
    """Vrai échec d'écriture (la cible du .mo est un dossier) : repli effectif sur <tmp>/bsmb-i18n,
    traduction anglaise active, rien d'affiché."""
    (lang_dir / "en" / "LC_MESSAGES" / "bsmb.mo").mkdir()
    monkeypatch.setattr(i18n.tempfile, "gettempdir", lambda: str(tmp_path / "tmp"))
    i18n.init("en")
    secours = tmp_path / "tmp" / "bsmb-i18n" / "en" / "bsmb.mo"
    assert secours.is_file()
    assert i18n._("Retour") == "Back"
    assert i18n._("Compte déconnecté") == "Account disconnected"
    sortie = capsys.readouterr()
    assert sortie.out == "" and sortie.err == ""
    assert list((lang_dir / "en" / "LC_MESSAGES").glob("*.tmp")) == []


def test_compiler_renvoie_faux_si_la_cible_est_un_dossier(lang_dir):
    po = lang_dir / "en" / "LC_MESSAGES" / "bsmb.po"
    mo = po.with_suffix(".mo")
    mo.mkdir()
    assert i18n._compiler(po, mo) is False
    assert mo.is_dir()


def test_ecriture_atomique_pas_de_fichier_temporaire_restant(lang_dir):
    i18n.init("en")
    assert [p.name for p in (lang_dir / "en" / "LC_MESSAGES").iterdir() if p.suffix == ".tmp"] == []


# ─── .mo corrompu ────────────────────────────────────────────


@pytest.mark.parametrize(
    "contenu",
    [b"", b"\xde\x12\x04\x95\x00\x00", b"\xde\x12\x04\x95" + b"\x00" * 4 + b"\xff" * 8, b"pas un mo du tout"],
    ids=["vide", "entete-partiel", "decalages-invalides", "texte"],
)
def test_mo_corrompu_est_recompile(lang_dir, contenu):
    mo = lang_dir / "en" / "LC_MESSAGES" / "bsmb.mo"
    mo.write_bytes(contenu)
    futur = time.time() + 100  # plus récent que le .po : pas recompilé « à jour » sans la détection
    os.utime(mo, (futur, futur))
    i18n.init("en")
    assert i18n._("Compte déconnecté") == "Account disconnected"
    assert mo.stat().st_size > len(contenu)


def test_mo_corrompu_et_po_absent_repli_source(tmp_path, monkeypatch):
    racine = tmp_path / "lang"
    dossier = racine / "en" / "LC_MESSAGES"
    dossier.mkdir(parents=True)
    (dossier / "bsmb.mo").write_bytes(b"")
    monkeypatch.setattr(i18n, "LANG_DIR", racine)
    i18n.init("en")
    assert i18n._("Compte déconnecté") == "Compte déconnecté"
