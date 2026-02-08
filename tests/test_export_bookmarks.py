"""Tests pour api/export_bookmarks.py — fonction fetch_bookmarks()"""
from unittest.mock import patch, MagicMock

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
    @patch("api.export_bookmarks.requests.Session")
    def test_single_page(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session

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

    @patch("api.export_bookmarks.requests.Session")
    def test_empty_bookmarks(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session

        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"bookmarks": []}
        response.raise_for_status = MagicMock()
        session.get.return_value = response

        result = fetch_bookmarks("Bearer test123")
        assert result["error"] is None
        assert result["count"] == 0
        assert result["urls"] == []

    @patch("api.export_bookmarks.requests.Session")
    def test_multiple_pages(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session

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

    @patch("api.export_bookmarks.requests.Session")
    def test_progress_callback(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session

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

    @patch("api.export_bookmarks.requests.Session")
    def test_fallback_to_did_when_no_handle(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session

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


class TestFetchBookmarksErrors:
    @patch("api.export_bookmarks.requests.Session")
    def test_expired_token(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session

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

    @patch("api.export_bookmarks.requests.Session")
    def test_api_error_400(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session

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

    @patch("api.export_bookmarks.requests.Session")
    def test_network_error(self, mock_session_cls):
        import requests
        session = MagicMock()
        mock_session_cls.return_value = session
        session.get.side_effect = requests.exceptions.ConnectionError("Network error")

        result = fetch_bookmarks("Bearer test")
        assert result["error"] is not None
        assert result["expired"] is False
