"""Tests pour api/repost_resolver.py"""
from unittest.mock import patch, MagicMock

from api.repost_resolver import RepostResolver


class TestResolve:
    def setup_method(self):
        self.resolver = RepostResolver()

    def test_invalid_url(self):
        url, handle, post_id = self.resolver.resolve("https://bsky.app/bad")
        assert url is None
        assert handle is None
        assert post_id is None

    @patch("api.repost_resolver.requests.get")
    def test_resolve_repost(self, mock_get):
        # Premier appel : getRecord (récupère le repost)
        record_resp = MagicMock()
        record_resp.status_code = 200
        record_resp.raise_for_status.return_value = None
        record_resp.json.return_value = {
            "value": {
                "embed": {
                    "$type": "app.bsky.embed.record",
                    "record": {
                        "uri": "at://did:plc:original_user/app.bsky.feed.post/orig123",
                    },
                },
            },
        }

        # Deuxième appel : getProfile (résout le DID)
        profile_resp = MagicMock()
        profile_resp.status_code = 200
        profile_resp.json.return_value = {"handle": "original.bsky.social"}

        mock_get.side_effect = [record_resp, profile_resp]

        url, handle, post_id = self.resolver.resolve(
            "https://bsky.app/profile/reposter.bsky.social/post/repost456"
        )
        assert url == "https://bsky.app/profile/original.bsky.social/post/orig123"
        assert handle == "original.bsky.social"
        assert post_id == "orig123"

    @patch("api.repost_resolver.requests.get")
    def test_not_a_repost(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "value": {
                "embed": {
                    "$type": "app.bsky.embed.images",
                    "images": [],
                },
            },
        }
        mock_get.return_value = mock_resp

        url, handle, post_id = self.resolver.resolve(
            "https://bsky.app/profile/user.bsky.social/post/normal123"
        )
        assert url is None

    @patch("api.repost_resolver.requests.get")
    def test_network_error(self, mock_get):
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError()

        url, handle, post_id = self.resolver.resolve(
            "https://bsky.app/profile/user.bsky.social/post/net_err"
        )
        assert url is None

    @patch("api.repost_resolver.requests.get")
    def test_fallback_did_as_handle(self, mock_get):
        """Si le profil ne peut pas être résolu, utilise le DID brut."""
        record_resp = MagicMock()
        record_resp.status_code = 200
        record_resp.raise_for_status.return_value = None
        record_resp.json.return_value = {
            "value": {
                "embed": {
                    "$type": "app.bsky.embed.record",
                    "record": {
                        "uri": "at://did:plc:unknown_did/app.bsky.feed.post/orig789",
                    },
                },
            },
        }

        profile_resp = MagicMock()
        profile_resp.status_code = 404

        mock_get.side_effect = [record_resp, profile_resp]

        url, handle, post_id = self.resolver.resolve(
            "https://bsky.app/profile/user.bsky.social/post/repost999"
        )
        assert handle == "did:plc:unknown_did"
        assert post_id == "orig789"


class TestResolveDIDToHandle:
    def setup_method(self):
        self.resolver = RepostResolver()

    @patch("api.repost_resolver.requests.get")
    def test_successful_resolution(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"handle": "resolved.bsky.social"}
        mock_get.return_value = mock_resp

        result = self.resolver._resolve_did_to_handle("did:plc:abc123")
        assert result == "resolved.bsky.social"

    @patch("api.repost_resolver.requests.get")
    def test_failed_resolution(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        result = self.resolver._resolve_did_to_handle("did:plc:nonexistent")
        assert result is None
