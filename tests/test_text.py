"""Tests de save_text() (downloaders/text.py) : réseau mocké."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from core.config import DEFAULT_CONFIG
from downloaders import DownloadError, DownloadResult, text
from downloaders.text import save_text

URL = "https://bsky.app/profile/user.bsky.social/post/3abc"


def _session(texte="Bonjour le monde", created_at="2026-01-02T10:00:00.000Z", erreur=None):
    session = MagicMock()
    if erreur:
        session.get.side_effect = erreur
    else:
        session.get.return_value.json.return_value = {
            "thread": {"post": {"record": {"text": texte, "createdAt": created_at}}}
        }
    return session


class TestSaveText:
    def test_texte_ecrit_et_decrit(self, tmp_path):
        res = save_text(URL, tmp_path / "txt", DEFAULT_CONFIG, session=_session())

        assert len(res) == 1
        r = res[0]
        assert isinstance(r, DownloadResult)
        assert r.filename == "user_bsky_social_20260102_3abc.txt"
        assert r.media_type == "text"
        assert r.cid is None
        assert r.path == tmp_path / "txt" / r.filename
        assert r.path.read_text(encoding="utf-8") == (
            f"Post: {URL}\nDate: 2026-01-02T10:00:00.000Z\nAuteur: user.bsky.social\n\nBonjour le monde\n"
        )
        assert r.size == r.path.stat().st_size

    def test_format_commun_facets_resolues_et_langue(self, tmp_path):
        record = {
            "text": "Voir ici",
            "createdAt": "2026-01-02T10:00:00.000Z",
            "langs": ["fr"],
            "facets": [
                {
                    "index": {"byteStart": 5, "byteEnd": 8},
                    "features": [{"$type": "app.bsky.richtext.facet#link", "uri": "https://x.test"}],
                }
            ],
        }
        session = MagicMock()
        session.get.return_value.json.return_value = {"thread": {"post": {"record": record}}}
        res = save_text(URL, tmp_path, DEFAULT_CONFIG, session=session)
        assert res[0].path.read_text(encoding="utf-8") == (
            f"Post: {URL}\nDate: 2026-01-02T10:00:00.000Z\nAuteur: user.bsky.social\nLangue: fr\n\n"
            "Voir ici (https://x.test)\n"
        )

    def test_name_prefix_remplace_la_base_du_nom(self, tmp_path):
        res = save_text(
            URL, tmp_path, DEFAULT_CONFIG, session=_session(), name_prefix="citant_20260210_3kq_quote"
        )
        assert [r.filename for r in res] == ["citant_20260210_3kq_quote.txt"]
        assert res[0].path.read_text(encoding="utf-8").startswith(f"Post: {URL}\n")

    def test_appel_getpostthread(self, tmp_path):
        session = _session()
        save_text(URL, tmp_path, DEFAULT_CONFIG, session=session)
        assert session.get.call_args.args[0] == (
            "https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread"
            "?uri=at://user.bsky.social/app.bsky.feed.post/3abc"
        )

    def test_sans_texte_renvoie_liste_vide(self, tmp_path):
        assert save_text(URL, tmp_path / "txt", DEFAULT_CONFIG, session=_session(texte="")) == []
        assert not (tmp_path / "txt").exists()

    def test_url_invalide_renvoie_liste_vide(self, tmp_path):
        session = _session()
        assert save_text("https://bsky.app/x", tmp_path, DEFAULT_CONFIG, session=session) == []
        session.get.assert_not_called()

    def test_api_en_erreur_leve_download_error(self, tmp_path):
        with pytest.raises(DownloadError):
            save_text(URL, tmp_path, DEFAULT_CONFIG, session=_session(erreur=requests.ConnectionError("x")))

    def test_sans_session_utilise_la_session_partagee(self, tmp_path, fake_session):
        fake_session.get.return_value = _session().get.return_value
        assert len(save_text(URL, tmp_path, DEFAULT_CONFIG)) == 1
        fake_session.get.assert_called_once()


class TestModeManuel:
    def test_affiche_la_ligne_txt(self, tmp_path, capsys):
        res = [DownloadResult("t.txt", tmp_path / "t.txt", "text", 1)]
        with patch("downloaders.text.save_text", return_value=res) as st:
            assert text.main([str(tmp_path), URL]) == 0
        assert st.call_args.args[:2] == (URL, str(tmp_path))
        assert "[TXT] t.txt" in capsys.readouterr().out

    def test_url_seule_dossier_par_defaut(self, tmp_path):
        with patch("downloaders.text.save_text", return_value=[]) as st:
            assert text.main([URL]) == 2
        assert st.call_args.args[0] == URL
        assert str(st.call_args.args[1]).endswith("texts")

    def test_erreur_code_1(self, tmp_path, capsys):
        with patch("downloaders.text.save_text", side_effect=DownloadError("API")):
            assert text.main([str(tmp_path), URL]) == 1
        assert "[ERR] API" in capsys.readouterr().out
