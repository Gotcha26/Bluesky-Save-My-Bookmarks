"""Tests pour les utilitaires de downloaders/images.py"""
import sys
from pathlib import Path

# Simuler les arguments avant l'import du module
sys.argv = ["images.py", str(Path.home() / "Downloads" / "BSMB" / "images"), "https://bsky.app/profile/test/post/123"]

from downloaders.images import (
    safe_part,
    guess_ext_from_ct,
    build_filename,
)


class TestSafePart:
    def test_normal_string(self):
        assert safe_part("hello_world") == "hello_world"

    def test_special_characters(self):
        result = safe_part('file<>:"/name')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result

    def test_whitespace(self):
        assert safe_part("hello   world") == "hello_world"

    def test_empty_string(self):
        assert safe_part("") == "_"

    def test_none(self):
        assert safe_part(None) == "_"

    def test_strips_dots_and_underscores(self):
        result = safe_part("..._test_...")
        assert not result.startswith(".")
        assert not result.endswith(".")

    def test_newlines_and_tabs(self):
        result = safe_part("hello\nworld\ttab")
        assert "\n" not in result
        assert "\t" not in result


class TestGuessExtFromCT:
    def test_jpeg(self):
        assert guess_ext_from_ct("image/jpeg") == ".jpg"

    def test_png(self):
        assert guess_ext_from_ct("image/png") == ".png"

    def test_webp(self):
        assert guess_ext_from_ct("image/webp") == ".webp"

    def test_gif(self):
        assert guess_ext_from_ct("image/gif") == ".gif"

    def test_bmp(self):
        assert guess_ext_from_ct("image/bmp") == ".bmp"

    def test_tiff(self):
        assert guess_ext_from_ct("image/tiff") == ".tif"

    def test_with_charset(self):
        assert guess_ext_from_ct("image/jpeg; charset=utf-8") == ".jpg"

    def test_empty(self):
        assert guess_ext_from_ct("") == ""

    def test_none_safe(self):
        assert guess_ext_from_ct(None) == ""


class TestBuildFilename:
    def test_basic_filename(self):
        result = build_filename("user", "20260207", "abc123", 1, ".jpg")
        assert result == "user_20260207_abc123_1.jpg"
        assert len(result) <= 64

    def test_respects_max_length(self):
        result = build_filename(
            "very_long_handle_name",
            "20260207",
            "very_long_post_identifier_that_goes_on",
            1,
            ".jpg",
            max_len=40,
        )
        assert len(result) <= 40
        assert result.endswith(".jpg")

    def test_index_formatting(self):
        result = build_filename("user", "20260207", "abc", 1, ".jpg")
        assert "_1.jpg" in result

    def test_preserves_extension(self):
        for ext in [".jpg", ".png", ".webp", ".gif"]:
            result = build_filename("user", "20260207", "abc", 1, ext)
            assert result.endswith(ext)

    def test_long_handle_truncated(self):
        result = build_filename(
            "a" * 100,
            "20260207",
            "post123",
            1,
            ".jpg",
            max_len=64,
        )
        assert len(result) <= 64
        assert result.endswith(".jpg")
