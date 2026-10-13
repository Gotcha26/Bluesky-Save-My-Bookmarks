"""Tests pour core/post_ref.py (identité des posts par AT-URI)."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from core.post_ref import PostRef, resolve_handle


class TestPostRefProperties:
    def test_at_uri(self):
        ref = PostRef("did:plc:abc", "3k1", "user.bsky.social")
        assert ref.at_uri == "at://did:plc:abc/app.bsky.feed.post/3k1"

    def test_at_uri_inconnu_sans_did(self):
        assert PostRef(None, "3k1", "user.bsky.social").at_uri is None

    def test_web_url_avec_handle(self):
        ref = PostRef("did:plc:abc", "3k1", "user.bsky.social")
        assert ref.web_url == "https://bsky.app/profile/user.bsky.social/post/3k1"

    def test_web_url_handle_invalid_utilise_did(self):
        ref = PostRef("did:plc:abc", "3k1", "handle.invalid")
        assert ref.web_url == "https://bsky.app/profile/did:plc:abc/post/3k1"

    def test_web_url_sans_handle_utilise_did(self):
        ref = PostRef("did:plc:abc", "3k1")
        assert ref.web_url == "https://bsky.app/profile/did:plc:abc/post/3k1"

    def test_web_url_handle_vide_utilise_did(self):
        assert PostRef("did:plc:abc", "3k1", "").web_url.endswith("/did:plc:abc/post/3k1")


class TestFromBskyUrl:
    def test_url_avec_handle(self):
        ref = PostRef.from_bsky_url("https://bsky.app/profile/user.bsky.social/post/3k1")
        assert ref.handle == "user.bsky.social"
        assert ref.did is None
        assert ref.rkey == "3k1"
        assert ref.at_uri is None

    def test_url_avec_did(self):
        ref = PostRef.from_bsky_url("https://bsky.app/profile/did:plc:abc/post/3k1")
        assert ref.did == "did:plc:abc"
        assert ref.handle is None
        assert ref.at_uri == "at://did:plc:abc/app.bsky.feed.post/3k1"

    def test_url_avec_handle_invalid_n_est_pas_un_handle(self):
        ref = PostRef.from_bsky_url("https://bsky.app/profile/handle.invalid/post/3k1")
        assert ref.handle is None
        assert ref.did is None

    def test_slash_final_toleré(self):
        assert PostRef.from_bsky_url("https://bsky.app/profile/a.b/post/3k1/").rkey == "3k1"

    @pytest.mark.parametrize("url", [
        "https://bsky.app/bad",
        "https://bsky.app/profile/a.b",
        "https://bsky.app/profile/a.b/feed/3k1",
        "",
    ])
    def test_url_invalide(self, url):
        with pytest.raises(ValueError):
            PostRef.from_bsky_url(url)


class TestFromAtUri:
    def test_at_uri_valide(self):
        ref = PostRef.from_at_uri("at://did:plc:abc/app.bsky.feed.post/3k1")
        assert (ref.did, ref.rkey, ref.handle) == ("did:plc:abc", "3k1", None)

    def test_avec_handle_fourni(self):
        ref = PostRef.from_at_uri("at://did:plc:abc/app.bsky.feed.post/3k1", handle="u.bsky.social")
        assert ref.web_url == "https://bsky.app/profile/u.bsky.social/post/3k1"

    @pytest.mark.parametrize("uri", [
        "",
        "https://bsky.app/profile/a/post/b",
        "at://did:plc:abc",
        "at://did:plc:abc/app.bsky.feed.like/3k1",
    ])
    def test_at_uri_invalide(self, uri):
        with pytest.raises(ValueError):
            PostRef.from_at_uri(uri)


class TestResolveHandle:
    def test_resolution(self, mock_get):
        resp = MagicMock()
        resp.json.return_value = {"did": "did:plc:abc"}
        mock_get.return_value = resp

        assert resolve_handle("user.bsky.social") == "did:plc:abc"
        args, kwargs = mock_get.call_args
        assert args[0] == "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle"
        assert kwargs["params"] == {"handle": "user.bsky.social"}

    def test_erreur_http_propagee(self, mock_get):
        resp = MagicMock()
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError("400")
        mock_get.return_value = resp

        with pytest.raises(requests.exceptions.HTTPError):
            resolve_handle("inconnu.example")
