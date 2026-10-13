"""Tests de downloaders/archive.py : facets, fichier texte et sidecar JSON (issue #7)."""
import json
import os
from pathlib import Path

import pytest

from core.config import DEFAULT_CONFIG
from downloaders import DownloadError, DownloadResult
from downloaders.archive import resolve_facets, write_sidecar, write_text

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://bsky.app/profile/auteur.example.com/post/3ktestfacets"
AT_URI = "at://did:plc:testauteur0000000000000/app.bsky.feed.post/3ktestfacets"
BASE = "auteur_example_com_20260203_3ktestfacets"


@pytest.fixture
def post():
    return json.loads((FIXTURES / "post_with_facets.json").read_text(encoding="utf-8"))


@pytest.fixture
def record(post):
    return post["value"]


def _lien(texte, sous, uri):
    """Facet de lien sur la première occurrence de `sous` (index en octets UTF-8)."""
    debut = texte.encode("utf-8").index(sous.encode("utf-8"))
    return {"index": {"byteStart": debut, "byteEnd": debut + len(sous.encode("utf-8"))},
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": uri}]}


class TestResolveFacets:
    def test_lien_apres_des_emojis_index_en_octets(self, record):
        # Les index sont des octets UTF-8 : « 🎉🔥 » pèse 8 octets pour 2 caractères
        resultat = resolve_facets(record["text"], record["facets"])
        assert resultat == ("🎉🔥 Voir libidex.example/article-tres-lo... (https://libidex.example/article-tres-long-titre)"
                            " avec @alice.example.com et #bluesky é")

    def test_les_index_ne_sont_pas_des_caracteres(self):
        texte = "😀😀😀 site.test"
        facet = _lien(texte, "site.test", "https://site.test/page")
        assert facet["index"]["byteStart"] == 13  # et non 4
        assert resolve_facets(texte, [facet]) == "😀😀😀 site.test (https://site.test/page)"

    def test_libelle_deja_l_url_n_est_pas_duplique(self):
        texte = "Voir https://site.test/a"
        assert resolve_facets(texte, [_lien(texte, "https://site.test/a", "https://site.test/a")]) == texte

    def test_mention_et_tag_inchanges(self, record):
        mention_tag = [f for f in record["facets"] if "link" not in f["features"][0]["$type"]]
        assert resolve_facets(record["text"], mention_tag) == record["text"]

    def test_sans_facets(self):
        assert resolve_facets("Bonjour", None) == "Bonjour"
        assert resolve_facets("Bonjour", []) == "Bonjour"
        assert resolve_facets("", [{"index": {"byteStart": 0, "byteEnd": 1}, "features": []}]) == ""

    def test_facet_hors_bornes_ignoree(self):
        texte = "Voir site.test"
        bonne = _lien(texte, "site.test", "https://site.test")
        hors = {"index": {"byteStart": 3, "byteEnd": 400},
                "features": [{"$type": "app.bsky.richtext.facet#link", "uri": "https://x.test"}]}
        negative = {"index": {"byteStart": -2, "byteEnd": 3},
                    "features": [{"$type": "app.bsky.richtext.facet#link", "uri": "https://y.test"}]}
        inversee = {"index": {"byteStart": 8, "byteEnd": 4},
                    "features": [{"$type": "app.bsky.richtext.facet#link", "uri": "https://z.test"}]}
        assert resolve_facets(texte, [hors, negative, inversee, bonne]) == "Voir site.test (https://site.test)"

    def test_facet_chevauchante_ignoree(self):
        texte = "abc def ghi"
        premiere = _lien(texte, "abc def", "https://un.test")
        chevauche = _lien(texte, "def ghi", "https://deux.test")
        assert resolve_facets(texte, [premiere, chevauche]) == "abc def (https://un.test) ghi"

    def test_facet_coupant_un_caractere_ignoree(self):
        texte = "é site.test"  # « é » pèse 2 octets : byteStart 1 coupe le caractère
        coupee = {"index": {"byteStart": 1, "byteEnd": 5},
                  "features": [{"$type": "app.bsky.richtext.facet#link", "uri": "https://x.test"}]}
        assert resolve_facets(texte, [coupee]) == texte

    def test_facets_malformees_sans_exception(self):
        texte = "Voir site.test"
        for facet in ({}, {"index": None}, {"index": {"byteStart": "a", "byteEnd": 3}, "features": []},
                      {"index": {"byteStart": 0, "byteEnd": 3}, "features": None},
                      {"index": {"byteStart": 0, "byteEnd": 3}, "features": [{"$type": "autre"}]}, "x", None):
            assert resolve_facets(texte, [facet]) == texte

    def test_facets_desordonnees(self):
        texte = "un deux"
        a = _lien(texte, "un", "https://un.test")
        b = _lien(texte, "deux", "https://deux.test")
        assert resolve_facets(texte, [b, a]) == "un (https://un.test) deux (https://deux.test)"


class TestWriteText:
    def test_post_image_avec_alt(self, tmp_path, record):
        res = write_text(URL, record, tmp_path / "texts", DEFAULT_CONFIG)

        assert len(res) == 1
        r = res[0]
        assert isinstance(r, DownloadResult)
        assert (r.filename, r.media_type, r.cid) == (f"{BASE}.txt", "text", None)
        assert r.path == tmp_path / "texts" / r.filename and r.size == r.path.stat().st_size
        assert r.path.read_text(encoding="utf-8") == (
            f"Post: {URL}\n"
            "Date: 2026-02-03T09:08:07.123Z\n"
            "Auteur: auteur.example.com\n"
            "Langue: fr, en\n"
            "\n"
            "🎉🔥 Voir libidex.example/article-tres-lo... (https://libidex.example/article-tres-long-titre)"
            " avec @alice.example.com et #bluesky é\n"
            "\n"
            "[Image 1 : Un chat noir sur un canapé]\n"
            "\n"
            "Réponse à: at://did:plc:testauteur0000000000000/app.bsky.feed.post/3ktestparent\n"
        )

    def test_alt_vide_omis_et_numerotation_conservee(self, tmp_path, record):
        record["embed"]["images"][0]["alt"] = ""
        record["embed"]["images"][1]["alt"] = "Deuxième"
        texte = write_text(URL, record, tmp_path, DEFAULT_CONFIG)[0].path.read_text(encoding="utf-8")
        assert "[Image 1" not in texte
        assert "[Image 2 : Deuxième]" in texte

    def test_alts_fournis_prioritaires(self, tmp_path, record):
        texte = write_text(URL, record, tmp_path, DEFAULT_CONFIG,
                           alts=["Autre alt", ""])[0].path.read_text(encoding="utf-8")
        assert "[Image 1 : Autre alt]" in texte
        assert "Un chat noir" not in texte

    def test_video(self, tmp_path):
        record = {"text": "Clip", "createdAt": "2026-02-03T09:08:07.123Z",
                  "embed": {"$type": "app.bsky.embed.video", "alt": "Un chien qui court", "video": {}}}
        texte = write_text(URL, record, tmp_path, DEFAULT_CONFIG)[0].path.read_text(encoding="utf-8")
        assert texte.endswith("Clip\n\n[Vidéo : Un chien qui court]\n")
        assert "Langue" not in texte

    def test_media_d_un_recordwithmedia(self, tmp_path):
        record = {"text": "Cité", "createdAt": "2026-02-03T09:08:07.123Z",
                  "embed": {"$type": "app.bsky.embed.recordWithMedia",
                            "record": {"$type": "app.bsky.embed.record",
                                       "record": {"uri": "at://did:plc:x/app.bsky.feed.post/3kcite", "cid": "c"}},
                            "media": {"$type": "app.bsky.embed.images",
                                      "images": [{"alt": "Dessin", "image": {}}]}}}
        texte = write_text(URL, record, tmp_path, DEFAULT_CONFIG)[0].path.read_text(encoding="utf-8")
        assert texte.endswith("Cité\n\n[Image 1 : Dessin]\n\nCite: at://did:plc:x/app.bsky.feed.post/3kcite\n")

    def test_citation_simple(self, tmp_path):
        record = {"text": "Je cite", "createdAt": "2026-02-03T09:08:07.123Z",
                  "embed": {"$type": "app.bsky.embed.record",
                            "record": {"uri": "at://did:plc:x/app.bsky.feed.post/3kcite", "cid": "c"}}}
        texte = write_text(URL, record, tmp_path, DEFAULT_CONFIG)[0].path.read_text(encoding="utf-8")
        assert texte.endswith("Je cite\n\nCite: at://did:plc:x/app.bsky.feed.post/3kcite\n")

    def test_external(self, tmp_path):
        record = {"text": "Un lien", "createdAt": "2026-02-03T09:08:07.123Z",
                  "embed": {"$type": "app.bsky.embed.external",
                            "external": {"uri": "https://exemple.org/a", "title": "Titre", "description": "Desc"}}}
        texte = write_text(URL, record, tmp_path, DEFAULT_CONFIG)[0].path.read_text(encoding="utf-8")
        assert texte.endswith("Un lien\n\nLien: https://exemple.org/a\nTitre: Titre\nDescription: Desc\n")

    def test_name_prefix_remplace_la_base(self, tmp_path, record):
        res = write_text(URL, record, tmp_path, DEFAULT_CONFIG, name_prefix="citant_20260210_3kq_quote")
        assert res[0].filename == "citant_20260210_3kq_quote.txt"

    def test_pas_de_reecriture_si_identique(self, tmp_path, record):
        premier = write_text(URL, record, tmp_path, DEFAULT_CONFIG)[0]
        os.utime(premier.path, ns=(1_000_000_000, 1_000_000_000))  # date ancienne : une réécriture se verrait
        second = write_text(URL, record, tmp_path, DEFAULT_CONFIG)[0]
        assert second.path.stat().st_mtime_ns == 1_000_000_000
        assert (second.filename, second.size) == (premier.filename, premier.size)

    def test_reecriture_si_contenu_different(self, tmp_path, record):
        premier = write_text(URL, record, tmp_path, DEFAULT_CONFIG)[0]
        record["text"] = "Texte modifié"
        write_text(URL, record, tmp_path, DEFAULT_CONFIG)
        assert "Texte modifié" in premier.path.read_text(encoding="utf-8")

    def test_url_invalide(self, tmp_path, record):
        with pytest.raises(DownloadError):
            write_text("https://bsky.app/", record, tmp_path, DEFAULT_CONFIG)


class TestWriteSidecar:
    def test_sidecar_ecrit_et_relisible(self, tmp_path, post, record):
        vue = {"uri": post["uri"], "author": {"handle": "auteur.example.com"}, "labels": []}
        res = write_sidecar(URL, record, vue, tmp_path / "texts", DEFAULT_CONFIG, at_uri=post["uri"])

        assert len(res) == 1
        r = res[0]
        assert (r.filename, r.media_type) == (f"{BASE}.json", "sidecar")
        assert r.path == tmp_path / "texts" / r.filename and r.size == r.path.stat().st_size
        contenu = json.loads(r.path.read_text(encoding="utf-8"))
        assert set(contenu) == {"url", "at_uri", "archived_at", "bsmb_version", "record", "post_view"}
        assert contenu["url"] == URL
        assert contenu["at_uri"] == AT_URI
        assert contenu["record"] == record  # record brut, facets comprises
        assert contenu["post_view"] == vue
        assert contenu["bsmb_version"]
        assert contenu["archived_at"].startswith("20")

    def test_post_view_absent_donne_null(self, tmp_path, record):
        r = write_sidecar(URL, record, None, tmp_path, DEFAULT_CONFIG)[0]
        assert json.loads(r.path.read_text(encoding="utf-8"))["post_view"] is None

    def test_at_uri_deduit_de_la_vue_puis_de_l_url(self, tmp_path, post, record):
        r = write_sidecar(URL, record, {"uri": AT_URI}, tmp_path, DEFAULT_CONFIG)[0]
        assert json.loads(r.path.read_text(encoding="utf-8"))["at_uri"] == AT_URI
        r = write_sidecar(URL, record, None, tmp_path, DEFAULT_CONFIG)[0]
        assert json.loads(r.path.read_text(encoding="utf-8"))["at_uri"] == (
            "at://auteur.example.com/app.bsky.feed.post/3ktestfacets")

    def test_name_prefix(self, tmp_path, record):
        r = write_sidecar(URL, record, None, tmp_path, DEFAULT_CONFIG, name_prefix="citant_20260210_3kq_quote2")[0]
        assert r.filename == "citant_20260210_3kq_quote2.json"

    def test_aucun_fichier_temporaire_ne_subsiste(self, tmp_path, record):
        write_sidecar(URL, record, None, tmp_path, DEFAULT_CONFIG)
        assert [p.name for p in tmp_path.iterdir()] == [f"{BASE}.json"]
