"""Tests pour api/post_analyzer.py"""
import pytest
from unittest.mock import patch, MagicMock

from api.post_analyzer import PostAnalyzer, PostType


class TestPostTypeEnum:
    def test_all_types_exist(self):
        assert PostType.ERROR_500.value == "error_500"
        assert PostType.ERROR_400.value == "error_400"
        assert PostType.QUOTE.value == "quote"
        assert PostType.REPOST is PostType.QUOTE  # alias déprécié
        assert PostType.IMAGES.value == "images"
        assert PostType.VIDEO.value == "video"
        assert PostType.TEXT_ONLY.value == "text_only"
        assert PostType.EXTERNAL.value == "external"
        assert PostType.UNKNOWN.value == "unknown"


class TestAnalyzeURLParsing:
    def setup_method(self):
        self.analyzer = PostAnalyzer()

    def test_invalid_url(self):
        post_type, data, debug = self.analyzer.analyze("https://bsky.app/bad")
        assert post_type == PostType.UNKNOWN

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

    def test_detect_quote(self, mock_get):
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
        assert post_type == PostType.QUOTE
        assert data["is_quote"] is True

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

    def test_network_error(self, mock_get):
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError()

        post_type, data, debug = self.analyzer.analyze(
            "https://bsky.app/profile/user.bsky.social/post/net_err"
        )
        assert post_type == PostType.UNKNOWN


# ----------------------------------------------- analyze(post_url, post_view) sans réseau (issue #3)

DID = "did:plc:test1000000000000000000000"
URL_PV = "https://bsky.app/profile/alice.example.com/post/3kpv00000001"


def _post_view(embed_record=None, embed_view=None, text="Bonjour"):
    record = {"$type": "app.bsky.feed.post", "text": text, "createdAt": "2026-02-10T09:30:00.000Z"}
    if embed_record is not None:
        record["embed"] = embed_record
    vue = {
        "uri": f"at://{DID}/app.bsky.feed.post/3kpv00000001",
        "cid": "bafyreitest",
        "author": {"did": DID, "handle": "alice.example.com"},
        "record": record,
        "labels": [{"val": "ignore-moi"}],
        "viewer": {"bookmarked": True},
    }
    if embed_view is not None:
        vue["embed"] = embed_view
    return vue


@pytest.fixture
def sans_reseau(fake_session):
    """Toute requête réseau fait échouer le test."""

    def interdit(*args, **kwargs):
        raise AssertionError("la session ne doit pas être appelée avec un post_view")
    fake_session.get.side_effect = interdit


class TestAnalyzeAvecPostView:
    def setup_method(self):
        self.analyzer = PostAnalyzer()

    def test_texte_seul(self, sans_reseau):
        t, data, _ = self.analyzer.analyze(URL_PV, post_view=_post_view())
        assert t == PostType.TEXT_ONLY
        assert data["text"] == "Bonjour"
        assert data["did"] == DID
        assert data["at_uri"] == f"at://{DID}/app.bsky.feed.post/3kpv00000001"
        assert data["handle"] == "alice.example.com"
        assert data["post_id"] == "3kpv00000001"
        assert data["created_at"] == "2026-02-10T09:30:00.000Z"
        assert data["embed_type"] == ""

    def test_images(self, sans_reseau):
        embed = {"$type": "app.bsky.embed.images", "images": [
            {"image": {"ref": {"$link": "bafkrei_a"}}}, {"image": {"ref": {"$link": "bafkrei_b"}}}]}
        vue_embed = {"$type": "app.bsky.embed.images#view", "images": [{"fullsize": "https://cdn/x.jpg"}]}
        t, data, _ = self.analyzer.analyze(URL_PV, post_view=_post_view(embed, vue_embed))
        assert t == PostType.IMAGES
        assert data["image_count"] == 2
        assert data["images"][0].endswith("bafkrei_a@jpeg")
        assert data["view_embed"] == vue_embed

    def test_video(self, sans_reseau):
        embed = {"$type": "app.bsky.embed.video",
                 "video": {"ref": {"$link": "bafkrei_v"}, "mimeType": "video/mp4", "size": 99}}
        vue_embed = {"$type": "app.bsky.embed.video#view", "playlist": "https://video.bsky.app/p.m3u8"}
        t, data, _ = self.analyzer.analyze(URL_PV, post_view=_post_view(embed, vue_embed))
        assert t == PostType.VIDEO
        assert data["video_cid"] == "bafkrei_v"
        assert f"did={DID}" in data["video_url"]
        assert data["view_embed"]["playlist"] == "https://video.bsky.app/p.m3u8"

    def test_external(self, sans_reseau):
        embed = {"$type": "app.bsky.embed.external",
                 "external": {"uri": "https://example.com/a", "title": "T", "description": "D"}}
        t, data, _ = self.analyzer.analyze(URL_PV, post_view=_post_view(embed))
        assert t == PostType.EXTERNAL
        assert data["external"]["uri"] == "https://example.com/a"

    def test_citation(self, sans_reseau):
        cite = f"at://did:plc:test2000000000000000000000/app.bsky.feed.post/3kcited0001"
        embed = {"$type": "app.bsky.embed.record", "record": {"uri": cite, "cid": "c"}}
        t, data, _ = self.analyzer.analyze(URL_PV, post_view=_post_view(embed))
        assert t == PostType.QUOTE
        assert data["is_quote"] is True
        assert data["quote_uri"] == cite

    def test_citation_avec_media(self, sans_reseau):
        cite = "at://did:plc:test2000000000000000000000/app.bsky.feed.post/3kcited0001"
        embed = {"$type": "app.bsky.embed.recordWithMedia",
                 "record": {"record": {"uri": cite, "cid": "c"}},
                 "media": {"$type": "app.bsky.embed.images",
                           "images": [{"image": {"ref": {"$link": "bafkrei_a"}}}]}}
        t, data, _ = self.analyzer.analyze(URL_PV, post_view=_post_view(embed))
        assert t == PostType.IMAGES
        assert data["is_quote"] is True
        assert data["quote_uri"] == cite

    def test_embed_inconnu(self, sans_reseau):
        t, data, debug = self.analyzer.analyze(URL_PV, post_view=_post_view({"$type": "app.bsky.embed.autre"}))
        assert t == PostType.UNKNOWN
        assert debug["embed_type"] == "app.bsky.embed.autre"

    def test_post_view_sans_record_repli_sur_get_record(self, mock_get):
        mock_get.return_value = MagicMock(status_code=400)
        t, _, _ = self.analyzer.analyze(URL_PV, post_view={"uri": "at://x/app.bsky.feed.post/3k"})
        assert t == PostType.ERROR_400
        mock_get.assert_called_once()

    def test_url_invalide_sans_reseau(self, sans_reseau):
        t, _, _ = self.analyzer.analyze("https://bsky.app/bad", post_view=_post_view())
        assert t == PostType.UNKNOWN

    def test_labels_et_viewer_ignores(self, sans_reseau):
        _, data, _ = self.analyzer.analyze(URL_PV, post_view=_post_view())
        assert "labels" not in data and "viewer" not in data

    def test_meme_resultat_que_get_record(self, sans_reseau, fake_session):
        """Un même record donne les mêmes champs de classification par les deux chemins."""
        embed = {"$type": "app.bsky.embed.images", "images": [{"image": {"ref": {"$link": "bafkrei_a"}}}]}
        vue = _post_view(embed)
        t_vue, d_vue, _ = self.analyzer.analyze(URL_PV, post_view=vue)

        reponse = MagicMock(status_code=200)
        reponse.json.return_value = {"uri": vue["uri"], "value": vue["record"]}
        fake_session.get.side_effect = None
        fake_session.get.return_value = reponse
        t_rec, d_rec, _ = self.analyzer.analyze(URL_PV)

        assert t_vue == t_rec
        for cle in ("images", "image_count", "text", "created_at", "did", "at_uri", "embed_type"):
            assert d_vue[cle] == d_rec[cle]

    def test_sans_post_view_get_record_comme_avant(self, mock_get):
        mock_get.return_value = MagicMock(status_code=400)
        t, _, _ = self.analyzer.analyze(URL_PV)
        assert t == PostType.ERROR_400
        mock_get.assert_called_once()


class TestHandleInvalide:
    def test_handle_invalid_equivalent_a_get_record(self, fake_session):
        """Un author.handle = handle.invalid donne le même handle (le DID de l'URL) par les deux chemins."""
        analyzer = PostAnalyzer()
        url = f"https://bsky.app/profile/{DID}/post/3kpv00000001"
        vue = _post_view()
        vue["author"]["handle"] = "handle.invalid"
        t_vue, d_vue, _ = analyzer.analyze(url, post_view=vue)

        reponse = MagicMock(status_code=200)
        reponse.json.return_value = {"uri": vue["uri"], "value": vue["record"]}
        fake_session.get.side_effect = None
        fake_session.get.return_value = reponse
        t_rec, d_rec, _ = analyzer.analyze(url)

        assert d_vue["handle"] == d_rec["handle"] == DID
        assert t_vue == t_rec
        assert d_vue["did"] == d_rec["did"]
