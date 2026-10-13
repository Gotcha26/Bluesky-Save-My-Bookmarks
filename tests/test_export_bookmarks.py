"""Tests pour api/export_bookmarks.py — fonction fetch_bookmarks()"""
from unittest.mock import MagicMock, patch

from api.export_bookmarks import fetch_bookmarks


class TestFetchBookmarksValidation:
    def test_invalid_token_none(self):
        result = fetch_bookmarks(None)
        assert result["error"] is not None
        assert result["expired"] is False
        assert result["urls"] == []

    def test_invalid_token_empty(self):
        result = fetch_bookmarks("")
        assert result["error"] is not None
        assert result["urls"] == []

    def test_invalid_token_no_bearer_prefix(self):
        result = fetch_bookmarks("just-a-token")
        assert result["error"] is not None
        assert "Bearer" in result["error"]


class TestFetchBookmarksSuccess:
    def test_single_page(self, fake_session):
        session = fake_session

        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "bookmarks": [
                {
                    "item": {
                        "uri": "at://did:plc:abc/app.bsky.feed.post/123",
                        "author": {"handle": "user.bsky.social"},
                    }
                }
            ],
            "cursor": None,
        }
        response.raise_for_status = MagicMock()
        session.get.return_value = response

        result = fetch_bookmarks("Bearer test123")
        assert result["error"] is None
        assert result["count"] == 1
        assert result["pages"] == 1
        assert "user.bsky.social" in result["urls"][0]
        assert "123" in result["urls"][0]

    def test_empty_bookmarks(self, fake_session):
        session = fake_session

        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"bookmarks": []}
        response.raise_for_status = MagicMock()
        session.get.return_value = response

        result = fetch_bookmarks("Bearer test123")
        assert result["error"] is None
        assert result["count"] == 0
        assert result["urls"] == []

    def test_multiple_pages(self, fake_session):
        session = fake_session

        page1 = MagicMock()
        page1.status_code = 200
        page1.json.return_value = {
            "bookmarks": [
                {"item": {"uri": "at://did:plc:abc/app.bsky.feed.post/1", "author": {"handle": "user1"}}}
            ],
            "cursor": "next-page",
        }
        page1.raise_for_status = MagicMock()

        page2 = MagicMock()
        page2.status_code = 200
        page2.json.return_value = {
            "bookmarks": [
                {"item": {"uri": "at://did:plc:abc/app.bsky.feed.post/2", "author": {"handle": "user2"}}}
            ],
            "cursor": None,
        }
        page2.raise_for_status = MagicMock()

        session.get.side_effect = [page1, page2]

        result = fetch_bookmarks("Bearer test123")
        assert result["count"] == 2
        assert result["pages"] == 2
        assert len(result["urls"]) == 2

    def test_progress_callback(self, fake_session):
        session = fake_session

        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "bookmarks": [
                {"item": {"uri": "at://did:plc:abc/app.bsky.feed.post/1", "author": {"handle": "u"}}}
            ],
            "cursor": None,
        }
        response.raise_for_status = MagicMock()
        session.get.return_value = response

        calls = []
        result = fetch_bookmarks("Bearer test", on_progress=lambda p, c: calls.append((p, c)))
        assert len(calls) == 1
        assert calls[0] == (1, 1)

    def test_fallback_to_did_when_no_handle(self, fake_session):
        session = fake_session

        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "bookmarks": [
                {"item": {"uri": "at://did:plc:xyz/app.bsky.feed.post/456"}}
            ],
            "cursor": None,
        }
        response.raise_for_status = MagicMock()
        session.get.return_value = response

        result = fetch_bookmarks("Bearer test123")
        assert "did:plc:xyz" in result["urls"][0]


class TestFetchBookmarksPdsUrl:
    def _setup(self, fake_session):
        session = fake_session
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"bookmarks": [], "cursor": None}
        response.raise_for_status = MagicMock()
        session.get.return_value = response
        return session

    def test_uses_provided_pds_url(self, fake_session):
        session = self._setup(fake_session)
        fetch_bookmarks("Bearer t", pds_url="https://morel.us-east.host.bsky.network/")
        assert session.get.call_args[0][0] == (
            "https://morel.us-east.host.bsky.network/xrpc/app.bsky.bookmark.getBookmarks"
        )

    def test_default_pds_url_is_bsky_social(self, fake_session):
        session = self._setup(fake_session)
        fetch_bookmarks("Bearer t")
        assert session.get.call_args[0][0] == (
            "https://bsky.social/xrpc/app.bsky.bookmark.getBookmarks"
        )

    def test_keeps_appview_proxy_header(self, fake_session):
        session = self._setup(fake_session)
        fetch_bookmarks("Bearer t", pds_url="https://eurosky.social")
        headers = session.get.call_args.kwargs["headers"]
        assert headers["atproto-proxy"] == "did:web:api.bsky.app#bsky_appview"


class TestFetchBookmarksErrors:
    def test_expired_token(self, fake_session):
        session = fake_session

        response = MagicMock()
        response.status_code = 400
        response.json.return_value = {
            "error": "ExpiredToken",
            "message": "Token has expired",
        }
        session.get.return_value = response

        result = fetch_bookmarks("Bearer expired-token")
        assert result["expired"] is True
        assert result["error"] is not None

    def test_api_error_400(self, fake_session):
        session = fake_session

        response = MagicMock()
        response.status_code = 400
        response.json.return_value = {
            "error": "SomeError",
            "message": "Something went wrong",
        }
        session.get.return_value = response

        result = fetch_bookmarks("Bearer test")
        assert result["expired"] is False
        assert result["error"] is not None
        assert "Something went wrong" in result["error"]

    def test_network_error(self, fake_session):
        import requests
        session = fake_session
        session.get.side_effect = requests.exceptions.ConnectionError("Network error")

        result = fetch_bookmarks("Bearer test")
        assert result["error"] is not None
        assert result["expired"] is False


class TestFetchBookmarksItemTypes:
    """Les trois formes de `item` (issue #3) : postView, notFoundPost, blockedPost."""

    def test_item_type_post_view_et_created_at(self, fake_session):
        import json
        from pathlib import Path
        page = json.loads((Path(__file__).parent / "fixtures" / "bookmarks_page.json").read_text(encoding="utf-8"))
        session = fake_session
        response = MagicMock(status_code=200)
        response.json.return_value = page
        session.get.return_value = response

        result = fetch_bookmarks("Bearer test")

        assert result["error"] is None
        assert result["count"] == 3
        par_type = {p["item_type"]: p for p in result["posts"]}
        assert set(par_type) == {"postView", "notFoundPost", "blockedPost"}
        vue = par_type["postView"]
        assert vue["post_view"] == page["bookmarks"][0]["item"]
        assert vue["created_at"] == "2026-03-01T10:00:00.000Z"
        assert vue["handle"] == "alice.example.com"
        assert vue["url"] == "https://bsky.app/profile/alice.example.com/post/3kpost00001"
        assert par_type["notFoundPost"]["post_view"] is None
        assert par_type["blockedPost"]["post_view"] is None
        # Sans handle connu, l'URL retombe sur le DID ; les trois restent dans `urls`
        assert par_type["notFoundPost"]["url"].startswith("https://bsky.app/profile/did:plc:test2")
        assert len(result["urls"]) == 3

    def test_item_sans_type_reste_post_view_si_record(self, fake_session):
        session = fake_session
        response = MagicMock(status_code=200)
        response.json.return_value = {"bookmarks": [{"item": {
            "uri": "at://did:plc:abc/app.bsky.feed.post/123",
            "author": {"handle": "u.example.com"}, "record": {"text": "x"}}}], "cursor": None}
        session.get.return_value = response

        post = fetch_bookmarks("Bearer test")["posts"][0]
        assert post["item_type"] == "postView"
        assert post["post_view"]["record"] == {"text": "x"}
        assert post["created_at"] is None
