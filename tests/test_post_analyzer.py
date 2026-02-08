"""Tests pour api/post_analyzer.py"""
from unittest.mock import patch, MagicMock

from api.post_analyzer import PostAnalyzer, PostType


class TestPostTypeEnum:
    def test_all_types_exist(self):
        assert PostType.ERROR_500.value == "error_500"
        assert PostType.ERROR_400.value == "error_400"
        assert PostType.REPOST.value == "repost"
        assert PostType.IMAGES.value == "images"
        assert PostType.VIDEO.value == "video"
        assert PostType.TEXT_ONLY.value == "text_only"
        assert PostType.UNKNOWN.value == "unknown"


class TestAnalyzeURLParsing:
    def setup_method(self):
        self.analyzer = PostAnalyzer()

    def test_invalid_url(self):
        post_type, data, debug = self.analyzer.analyze("https://bsky.app/bad")
        assert post_type == PostType.UNKNOWN

    @patch("api.post_analyzer.requests.get")
    def test_error_400(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_get.return_value = mock_resp

        post_type, data, debug = self.analyzer.analyze(
            "https://bsky.app/profile/user.bsky.social/post/deleted123"
        )
        assert post_type == PostType.ERROR_400
        assert data["handle"] == "user.bsky.social"
        assert data["post_id"] == "deleted123"

    @patch("api.post_analyzer.requests.get")
    def test_error_500(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp

        post_type, data, debug = self.analyzer.analyze(
            "https://bsky.app/profile/user.bsky.social/post/err500"
        )
        assert post_type == PostType.ERROR_500


class TestAnalyzePostTypes:
    def setup_method(self):
        self.analyzer = PostAnalyzer()

    @patch("api.post_analyzer.requests.get")
    def test_detect_images(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "uri": "at://did:plc:abc/app.bsky.feed.post/123",
            "value": {
                "createdAt": "2026-01-15T10:00:00Z",
                "text": "Voici mes photos",
                "embed": {
                    "$type": "app.bsky.embed.images",
                    "images": [
                        {"image": {"ref": {"$link": "bafkrei_img1"}}},
                        {"image": {"ref": {"$link": "bafkrei_img2"}}},
                    ],
                },
            },
        }
        mock_get.return_value = mock_resp

        post_type, data, _ = self.analyzer.analyze(
            "https://bsky.app/profile/user.bsky.social/post/123"
        )
        assert post_type == PostType.IMAGES
        assert data["image_count"] == 2
        assert len(data["images"]) == 2

    @patch("api.post_analyzer.requests.get")
    def test_detect_video(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "uri": "at://did:plc:abc/app.bsky.feed.post/456",
            "value": {
                "createdAt": "2026-01-15T10:00:00Z",
                "text": "Ma vidéo",
                "embed": {
                    "$type": "app.bsky.embed.video",
                    "video": {
                        "ref": {"$link": "bafkrei_vid1"},
                        "mimeType": "video/mp4",
                        "size": 1024000,
                    },
                },
            },
        }
        mock_get.return_value = mock_resp

        post_type, data, _ = self.analyzer.analyze(
            "https://bsky.app/profile/user.bsky.social/post/456"
        )
        assert post_type == PostType.VIDEO
        assert "video_url" in data
        assert data["video_cid"] == "bafkrei_vid1"

    @patch("api.post_analyzer.requests.get")
    def test_detect_repost(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "uri": "at://did:plc:abc/app.bsky.feed.post/789",
            "value": {
                "createdAt": "2026-01-15T10:00:00Z",
                "text": "Regardez ça",
                "embed": {
                    "$type": "app.bsky.embed.record",
                    "record": {"uri": "at://did:plc:other/app.bsky.feed.post/orig1"},
                },
            },
        }
        mock_get.return_value = mock_resp

        post_type, data, _ = self.analyzer.analyze(
            "https://bsky.app/profile/user.bsky.social/post/789"
        )
        assert post_type == PostType.REPOST
        assert data["is_repost"] is True

    @patch("api.post_analyzer.requests.get")
    def test_detect_text_only(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "uri": "at://did:plc:abc/app.bsky.feed.post/txt1",
            "value": {
                "createdAt": "2026-01-15T10:00:00Z",
                "text": "Juste du texte sans média",
            },
        }
        mock_get.return_value = mock_resp

        post_type, data, _ = self.analyzer.analyze(
            "https://bsky.app/profile/user.bsky.social/post/txt1"
        )
        assert post_type == PostType.TEXT_ONLY

    @patch("api.post_analyzer.requests.get")
    def test_detect_record_with_media_images(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "uri": "at://did:plc:abc/app.bsky.feed.post/qp1",
            "value": {
                "createdAt": "2026-01-15T10:00:00Z",
                "text": "Quote post avec image",
                "embed": {
                    "$type": "app.bsky.embed.recordWithMedia",
                    "record": {"record": {"uri": "at://did:plc:other/app.bsky.feed.post/orig"}},
                    "media": {
                        "$type": "app.bsky.embed.images",
                        "images": [{"image": {"ref": {"$link": "bafkrei_qp1"}}}],
                    },
                },
            },
        }
        mock_get.return_value = mock_resp

        post_type, data, _ = self.analyzer.analyze(
            "https://bsky.app/profile/user.bsky.social/post/qp1"
        )
        assert post_type == PostType.IMAGES
        assert data["image_count"] == 1

    @patch("api.post_analyzer.requests.get")
    def test_network_error(self, mock_get):
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError()

        post_type, data, debug = self.analyzer.analyze(
            "https://bsky.app/profile/user.bsky.social/post/net_err"
        )
        assert post_type == PostType.UNKNOWN
