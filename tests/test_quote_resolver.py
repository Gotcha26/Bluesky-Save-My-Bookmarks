"""Tests de api/quote_resolver.py : record cité d'une citation (issue #5)."""
import importlib
import json
import sys
import warnings
from pathlib import Path
from unittest.mock import MagicMock

import requests

from api.quote_resolver import QuoteResolver, QuoteTarget

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://bsky.app/profile/citant.example.com/post/3kquote0001"
D2 = "did:plc:test2000000000000000000000"


def charger(nom):
    return json.loads((FIXTURES / nom).read_text(encoding="utf-8"))


def _reponse(status=200, data=None):
    resp = MagicMock(status_code=status)
    resp.json.return_value = data or {}
    if status >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status} Error")
    else:
        resp.raise_for_status.return_value = None
    return resp


def _routeur(record_citant, cite_status=200, handle="cite.example.com", profil_status=200):
    """requests.get factice : getRecord du citant, getRecord du cité, getProfile."""
    appels = []

    def get(url, params=None, **kwargs):
        appels.append((url, dict(params or {})))
        if url.endswith("getProfile"):
            return _reponse(profil_status, {"handle": handle} if handle else {})
        if params["rkey"] == record_citant["uri"].split("/")[-1]:
            return _reponse(200, record_citant)
        return _reponse(cite_status, {"value": {"text": "cité"}})

    get.appels = appels
    return get


class TestResolveCitation:
    def setup_method(self):
        self.resolver = QuoteResolver()

    def test_url_invalide(self):
        assert self.resolver.resolve("https://bsky.app/bad") is None

    def test_cible_de_type_post(self, mock_get):
        mock_get.side_effect = _routeur(charger("quote_text.json"))
        cible = self.resolver.resolve(URL)
        assert cible == QuoteTarget(
            url="https://bsky.app/profile/cite.example.com/post/3kcited0001",
            did=D2, rkey="3kcited0001", handle="cite.example.com",
            collection="app.bsky.feed.post", state="post",
        )

    def test_recordwithmedia_lit_le_record_imbrique(self, mock_get):
        mock_get.side_effect = _routeur(charger("quote_with_media.json"))
        cible = self.resolver.resolve("https://bsky.app/profile/citant.example.com/post/3kquote0002")
        assert cible.state == "post"
        assert cible.rkey == "3kcited0001"

    def test_handle_inconnu_garde_le_did_dans_l_url(self, mock_get):
        mock_get.side_effect = _routeur(charger("quote_text.json"), profil_status=404)
        cible = self.resolver.resolve(URL)
        assert cible.handle is None
        assert cible.url == f"https://bsky.app/profile/{D2}/post/3kcited0001"

    def test_handle_invalid_remplace_par_le_did(self, mock_get):
        mock_get.side_effect = _routeur(charger("quote_text.json"), handle="handle.invalid")
        cible = self.resolver.resolve(URL)
        assert cible.url == f"https://bsky.app/profile/{D2}/post/3kcited0001"

    def test_repo_est_le_did_quand_l_url_en_contient_un(self, mock_get):
        mock_get.side_effect = _routeur(charger("quote_text.json"))
        self.resolver.resolve("https://bsky.app/profile/did:plc:test1000000000000000000000/post/3kquote0001")
        assert mock_get.side_effect.appels[0][1]["repo"] == "did:plc:test1000000000000000000000"

    def test_post_sans_citation(self, mock_get):
        mock_get.return_value = _reponse(200, {"uri": "at://did:plc:x/app.bsky.feed.post/n1", "value": {
            "embed": {"$type": "app.bsky.embed.images", "images": []}}})
        assert self.resolver.resolve("https://bsky.app/profile/u.example.com/post/n1") is None

    def test_erreur_reseau(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError()
        assert self.resolver.resolve(URL) is None


class TestEtatsDuRecordCite:
    def setup_method(self):
        self.resolver = QuoteResolver()

    def test_collection_generator_n_est_pas_un_post(self, mock_get):
        mock_get.side_effect = _routeur(charger("quote_of_generator.json"))
        cible = self.resolver.resolve("https://bsky.app/profile/citant.example.com/post/3kquote0003")
        assert cible.state == "not_post"
        assert cible.collection == "app.bsky.feed.generator"
        assert cible.url is None
        # ni getRecord du cité, ni getProfile : une seule requête (le citant)
        assert len(mock_get.side_effect.appels) == 1

    def test_record_cite_introuvable(self, mock_get):
        mock_get.side_effect = _routeur(charger("quote_text.json"), cite_status=400)
        cible = self.resolver.resolve(URL)
        assert cible.state == "not_found"
        assert cible.rkey == "3kcited0001"

    def test_erreur_serveur_sur_le_cite_n_est_pas_une_suppression(self, mock_get):
        mock_get.side_effect = _routeur(charger("quote_text.json"), cite_status=500)
        assert self.resolver.resolve(URL) is None

    def _vue(self, type_record, imbrique=False):
        record = {"$type": type_record, "uri": f"at://{D2}/app.bsky.feed.post/3kcited0001"}
        if imbrique:
            return {"embed": {"$type": "app.bsky.embed.recordWithMedia#view", "record": {"record": record}}}
        return {"embed": {"$type": "app.bsky.embed.record#view", "record": record}}

    def test_etats_de_la_vue_hydratee(self, mock_get):
        mock_get.return_value = _reponse(200, {"handle": "cite.example.com"})
        for suffixe, etat in (("viewNotFound", "not_found"), ("viewBlocked", "blocked"),
                              ("viewDetached", "detached")):
            vue = self._vue(f"app.bsky.embed.record#{suffixe}")
            cible = self.resolver.resolve(URL, post_view=vue)
            assert cible.state == etat
            assert cible.did == D2
        # l'état est connu par la vue : aucune requête
        assert not mock_get.called

    def test_etat_dans_recordwithmedia_vue(self, mock_get):
        cible = self.resolver.resolve(URL, post_view=self._vue("app.bsky.embed.record#viewBlocked", imbrique=True))
        assert cible.state == "blocked"
        assert not mock_get.called

    def test_vue_avec_record_normal_continue_normalement(self, mock_get):
        mock_get.side_effect = _routeur(charger("quote_text.json"))
        vue = self._vue("app.bsky.embed.record#viewRecord")
        assert self.resolver.resolve(URL, post_view=vue).state == "post"


class TestResolveDIDToHandle:
    def setup_method(self):
        self.resolver = QuoteResolver()

    def test_successful_resolution(self, mock_get):
        mock_get.return_value = _reponse(200, {"handle": "resolved.bsky.social"})
        assert self.resolver._resolve_did_to_handle("did:plc:abc123") == "resolved.bsky.social"

    def test_failed_resolution(self, mock_get):
        mock_get.return_value = _reponse(404)
        assert self.resolver._resolve_did_to_handle("did:plc:nonexistent") is None


class TestShimDeprecie:
    def test_repost_resolver_reexporte_quote_resolver_avec_avertissement(self):
        sys.modules.pop("api.repost_resolver", None)
        with warnings.catch_warnings(record=True) as avertissements:
            warnings.simplefilter("always")
            module = importlib.import_module("api.repost_resolver")
        assert module.RepostResolver is QuoteResolver
        assert any(issubclass(a.category, DeprecationWarning) for a in avertissements)
