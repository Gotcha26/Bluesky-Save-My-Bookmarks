"""Archivage des citations (quote posts, issue #5) : analyseur et résolveur réels, réseau et downloaders mockés."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from api.post_analyzer import PostAnalyzer, PostType
from api.quote_resolver import QuoteResolver
from core import orchestrator
from core.orchestrator import process_post
from downloaders import DownloadError, DownloadResult

FIXTURES = Path(__file__).parent / "fixtures"
D1, D2, D3, D4 = (f"did:plc:test{i}000000000000000000000" for i in (1, 2, 3, 4))
HANDLES = {D1: "citant.example.com", D2: "cite.example.com", D3: "troisieme.example.com", D4: "quatrieme.example.com"}
BASE = "citant_example_com_20260210"  # <handle>_<date> du citant (handle sans points)


def charger(nom):
    return json.loads((FIXTURES / nom).read_text(encoding="utf-8"))


def post_texte(did, rkey, texte="Le post cité", embed=None):
    valeur = {"$type": "app.bsky.feed.post", "text": texte, "createdAt": "2026-01-03T08:00:00.000Z"}
    if embed:
        valeur["embed"] = embed
    return {"uri": f"at://{did}/app.bsky.feed.post/{rkey}", "value": valeur}


class Reseau:
    """requests.get factice : getRecord par rkey, getProfile par DID."""

    def __init__(self, records, statuts=None):
        self.records = {r["uri"].split("/")[-1]: r for r in records}
        self.statuts = statuts or {}
        self.rkeys_lus = []

    def __call__(self, url, params=None, **kwargs):
        resp = MagicMock()
        if url.endswith("getProfile"):
            resp.status_code = 200
            resp.json.return_value = {"handle": HANDLES.get(params["actor"], "inconnu.example.com")}
            return resp
        rkey = params["rkey"]
        self.rkeys_lus.append(rkey)
        statut = self.statuts.get(rkey, 200 if rkey in self.records else 400)
        resp.status_code = statut
        resp.json.return_value = self.records.get(rkey, {})
        if statut >= 400:
            resp.raise_for_status.side_effect = requests.HTTPError(f"{statut} Error")
        return resp


class Downloaders:
    """Trois downloaders factices qui nomment les fichiers comme les vrais."""

    def __init__(self, texte_vide=False, erreur=None):
        self.appels = []
        self.texte_vide = texte_vide
        self.erreur = erreur or {}

    def _fabriquer(self, nom, media_type, ext):
        def telecharger(url, dest, config, session=None, name_prefix=None):
            self.appels.append((nom, url, name_prefix))
            cle = (nom, url) if (nom, url) in self.erreur else url
            if cle in self.erreur:
                raise DownloadError(self.erreur[cle])
            if nom == "save_text" and self.texte_vide:
                return []
            base = name_prefix or f"propre_{url.rsplit('/', 1)[-1]}"
            suffixe = "" if media_type == "text" else "_1"
            return [DownloadResult(f"{base}{suffixe}.{ext}", Path(f"{base}{suffixe}.{ext}"), media_type, 3)]
        return telecharger

    def patch(self):
        return patch.multiple(
            "core.orchestrator",
            download_images=self._fabriquer("download_images", "image", "jpg"),
            download_video=self._fabriquer("download_video", "video", "mp4"),
            save_text=self._fabriquer("save_text", "text", "txt"),
        )

    def noms(self):
        return [(nom, prefixe) for nom, _, prefixe in self.appels]


def lancer(url, records, tmp_db, tmp_path, statuts=None, downloaders=None, non_resolues=None):
    reseau = Reseau(records, statuts)
    downloaders = downloaders or Downloaders()
    journal = []
    with patch("requests.get", side_effect=reseau), downloaders.patch():
        resultat = process_post(
            url, "IMG", "VID", "TXT", tmp_db, PostAnalyzer(), QuoteResolver(), tmp_path,
            lambda msg, **k: journal.append(msg), config={"max_filename_len": 120},
            quotes_unresolved=non_resolues,
        )
    return resultat, downloaders, journal, reseau


def url_citant(nom_fixture):
    record = charger(nom_fixture)
    return f"https://bsky.app/profile/{HANDLES[D1]}/post/{record['uri'].rsplit('/', 1)[-1]}"


def medias(db):
    return [r[0] for r in db.conn.execute("SELECT filename FROM media ORDER BY id")]


def statut(db, url):
    return db.conn.execute("SELECT status FROM posts WHERE url = ?", (url,)).fetchone()[0]


class TestCitationDeTexte:
    def test_le_citant_est_archive_puis_le_cite_avec_le_prefixe(self, tmp_db, tmp_path):
        url = url_citant("quote_text.json")
        res, dl, _, _ = lancer(url, [charger("quote_text.json"), post_texte(D2, "3kcited0001")], tmp_db, tmp_path)

        assert res[0] is True and res[4] == "success"
        assert res[3] == 2  # deux textes
        assert dl.noms() == [("save_text", None), ("save_text", f"{BASE}_3kquote0001_quote")]
        assert dl.appels[0][1] == url
        assert dl.appels[1][1] == f"https://bsky.app/profile/{HANDLES[D2]}/post/3kcited0001"

    def test_tout_est_enregistre_sous_l_url_du_bookmark(self, tmp_db, tmp_path):
        url = url_citant("quote_text.json")
        lancer(url, [charger("quote_text.json"), post_texte(D2, "3kcited0001")], tmp_db, tmp_path)
        assert medias(tmp_db) == ["propre_3kquote0001.txt", f"{BASE}_3kquote0001_quote.txt"]
        assert statut(tmp_db, url) == "ok"
        assert tmp_db.conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 1

    def test_cite_avec_images_utilise_le_downloader_d_images(self, tmp_db, tmp_path):
        images = {"$type": "app.bsky.embed.images", "images": [{"image": {"ref": {"$link": "bafkreitestimage"}}}]}
        url = url_citant("quote_text.json")
        res, dl, _, _ = lancer(url, [charger("quote_text.json"), post_texte(D2, "3kcited0001", embed=images)],
                               tmp_db, tmp_path)
        assert ("download_images", f"{BASE}_3kquote0001_quote") in dl.noms()
        assert res[1] == 1 and res[3] == 1  # une image citée, le texte du citant

    def test_cite_avec_video(self, tmp_db, tmp_path):
        video = {"$type": "app.bsky.embed.video", "video": {"ref": {"$link": "bafkreitestvideo"}}}
        url = url_citant("quote_text.json")
        res, dl, _, _ = lancer(url, [charger("quote_text.json"), post_texte(D2, "3kcited0001", embed=video)],
                               tmp_db, tmp_path)
        assert ("download_video", f"{BASE}_3kquote0001_quote") in dl.noms()
        assert res[2] == 1


class TestCitationAvecMedia:
    def test_media_du_citant_texte_puis_cite(self, tmp_db, tmp_path):
        url = url_citant("quote_with_media.json")
        res, dl, _, _ = lancer(url, [charger("quote_with_media.json"), post_texte(D2, "3kcited0001")],
                               tmp_db, tmp_path)
        assert res[4] == "success"
        assert dl.noms() == [
            ("download_images", None),
            ("save_text", None),
            ("save_text", f"{BASE}_3kquote0002_quote"),
        ]
        assert res[1] == 1 and res[3] == 2
        assert len(medias(tmp_db)) == 3


class TestEchecDuContenuPropre:
    """Une erreur sur le contenu du citant n'est pas masquée par un autre résultat."""

    def test_images_en_erreur_texte_ok_est_failed(self, tmp_db, tmp_path):
        url = url_citant("quote_with_media.json")
        dl = Downloaders(erreur={("download_images", url): "API"})
        res, _, _, _ = lancer(url, [charger("quote_with_media.json"), post_texte(D2, "3kcited0001")],
                              tmp_db, tmp_path, downloaders=dl)
        assert res[0] is False and res[4] == "failed"
        # ce qui a été obtenu est conservé en base
        assert len(medias(tmp_db)) == 2
        assert statut(tmp_db, url) != "deleted"

    def test_texte_du_citant_en_erreur_cite_archive_est_failed(self, tmp_db, tmp_path):
        url = url_citant("quote_text.json")
        tmp_db.add_post(url)
        tmp_db.mark_post_status(url, "unknown")
        dl = Downloaders(erreur={("save_text", url): "API"})
        res, _, _, _ = lancer(url, [charger("quote_text.json"), post_texte(D2, "3kcited0001")],
                              tmp_db, tmp_path, downloaders=dl)
        assert res[0] is False and res[4] == "failed"
        assert statut(tmp_db, url) == "unknown"  # reste retentable
        assert len(medias(tmp_db)) == 1

    def test_cite_externe_archive_par_son_texte_avec_note(self, tmp_db, tmp_path):
        externe = {"$type": "app.bsky.embed.external",
                   "external": {"uri": "https://example.com/x", "title": "t", "description": "d"}}
        url = url_citant("quote_text.json")
        res, dl, journal, _ = lancer(url, [charger("quote_text.json"),
                                           post_texte(D2, "3kcited0001", embed=externe)], tmp_db, tmp_path)
        assert res[4] == "success"
        assert ("save_text", f"{BASE}_3kquote0001_quote") in dl.noms()
        assert any("carte de lien non archivée (texte seul)" in m for m in journal)


class TestRecordCiteNonArchivable:
    def test_generateur_ignore_avec_note_et_statut_ok(self, tmp_db, tmp_path):
        url = url_citant("quote_of_generator.json")
        res, dl, journal, _ = lancer(url, [charger("quote_of_generator.json")], tmp_db, tmp_path)
        assert res[4] == "success"
        assert dl.noms() == [("save_text", None)]
        assert statut(tmp_db, url) == "ok"
        assert any("n'est pas un post" in m and "app.bsky.feed.generator" in m for m in journal)

    def test_post_cite_supprime_statut_ok_avec_note(self, tmp_db, tmp_path):
        url = url_citant("quote_text.json")
        res, dl, journal, _ = lancer(url, [charger("quote_text.json")], tmp_db, tmp_path)  # cité absent : 400
        assert res[4] == "success"
        assert dl.noms() == [("save_text", None)]
        assert statut(tmp_db, url) == "ok"
        assert any("post cité supprimé" in m for m in journal)
        assert not any("CITATION NON ARCHIVÉE" in m for m in journal)

    def test_cite_en_erreur_serveur_le_citant_reste_ok_et_la_citation_est_notee(self, tmp_db, tmp_path):
        url = url_citant("quote_text.json")
        non_resolues = []
        res, dl, journal, _ = lancer(url, [charger("quote_text.json"), post_texte(D2, "3kcited0001")],
                                     tmp_db, tmp_path, statuts={"3kcited0001": 500}, non_resolues=non_resolues)
        assert res[4] == "success"
        assert statut(tmp_db, url) == "ok"
        assert non_resolues == [url]
        assert any(f"CITATION NON ARCHIVÉE: at://{D2}/app.bsky.feed.post/3kcited0001" in m for m in journal)

    def test_echec_de_telechargement_du_cite(self, tmp_db, tmp_path):
        url = url_citant("quote_text.json")
        cite = f"https://bsky.app/profile/{HANDLES[D2]}/post/3kcited0001"
        non_resolues = []
        res, _, journal, _ = lancer(url, [charger("quote_text.json"), post_texte(D2, "3kcited0001")],
                                    tmp_db, tmp_path, downloaders=Downloaders(erreur={cite: "API"}),
                                    non_resolues=non_resolues)
        assert res[4] == "success" and statut(tmp_db, url) == "ok"
        assert non_resolues == [url]
        assert any(f"CITATION NON ARCHIVÉE: {cite}" in m for m in journal)

    def test_citant_sans_contenu_et_cite_en_echec_est_failed(self, tmp_db, tmp_path):
        url = url_citant("quote_text.json")
        res, _, _, _ = lancer(url, [charger("quote_text.json"), post_texte(D2, "3kcited0001")], tmp_db, tmp_path,
                              statuts={"3kcited0001": 500},
                              downloaders=Downloaders(erreur={url: "API"}))
        assert res[0] is False and res[4] == "failed"
        assert tmp_db.conn.execute("SELECT COUNT(*) FROM media").fetchone()[0] == 0

    def test_citant_sans_texte_et_cite_supprime_est_deleted(self, tmp_db, tmp_path):
        url = url_citant("quote_text.json")
        res, _, _, _ = lancer(url, [charger("quote_text.json")], tmp_db, tmp_path,
                              downloaders=Downloaders(texte_vide=True))
        assert res[0] is False and res[4] == "error_400"
        assert statut(tmp_db, url) == "deleted"

    def test_citant_sans_texte_et_cite_archive_est_ok(self, tmp_db, tmp_path):
        url = url_citant("quote_text.json")
        dl = Downloaders()
        # save_text du citant vide, celui du cité plein
        original = dl._fabriquer("save_text", "text", "txt")

        def save_text(u, d, c, session=None, name_prefix=None):
            return [] if name_prefix is None else original(u, d, c, session, name_prefix)

        reseau = Reseau([charger("quote_text.json"), post_texte(D2, "3kcited0001")])
        with patch("requests.get", side_effect=reseau), dl.patch(), patch.object(orchestrator, "save_text", save_text):
            res = process_post(url, "IMG", "VID", "TXT", tmp_db, PostAnalyzer(), QuoteResolver(), tmp_path,
                               lambda *a, **k: None, config={})
        assert res[4] == "success" and statut(tmp_db, url) == "ok"


class TestProfondeur:
    RECORDS = ["quote_chain_a.json", "quote_chain_b.json", "quote_chain_c.json", "quote_chain_d.json"]

    def test_chaine_de_quatre_maillons_s_arrete_a_deux(self, tmp_db, tmp_path):
        url = url_citant("quote_chain_a.json")
        res, dl, _, reseau = lancer(url, [charger(n) for n in self.RECORDS], tmp_db, tmp_path)

        base = f"{BASE}_3kchain000a"
        assert dl.noms() == [
            ("save_text", None),                  # A
            ("save_text", f"{base}_quote"),       # B
            ("save_text", f"{base}_quote2"),      # C (cité de B, préfixé par A)
        ]
        assert not any("3kchain000d" in u for _, u, _ in dl.appels)  # rien pour D
        assert "3kchain000d" not in reseau.rkeys_lus
        assert res[4] == "success" and res[3] == 3
        assert medias(tmp_db) == ["propre_3kchain000a.txt", f"{base}_quote.txt", f"{base}_quote2.txt"]
        assert statut(tmp_db, url) == "ok"

    def test_noms_distincts_a_chaque_niveau(self, tmp_db, tmp_path):
        url = url_citant("quote_chain_a.json")
        lancer(url, [charger(n) for n in self.RECORDS], tmp_db, tmp_path)
        noms = medias(tmp_db)
        assert len(set(noms)) == len(noms) == 3

    def test_echec_du_maillon_c_n_invalide_pas_a_et_b(self, tmp_db, tmp_path):
        url = url_citant("quote_chain_a.json")
        non_resolues = []
        res, dl, _, _ = lancer(url, [charger(n) for n in self.RECORDS], tmp_db, tmp_path,
                               statuts={"3kchain000c": 500}, non_resolues=non_resolues)
        assert res[4] == "success" and res[3] == 2
        assert non_resolues == [url]
