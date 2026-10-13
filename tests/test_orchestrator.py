"""Tests de process_post() : branche TEXT_ONLY (issue #8)."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from api.post_analyzer import PostType
from core.orchestrator import process_post


def _analyseur_texte_seul():
    analyzer = MagicMock()
    analyzer.analyze.return_value = (PostType.TEXT_ONLY, {"handle": "user.bsky.social"}, {})
    return analyzer


def _lancer(tmp_db, tmp_path, url, stdout, returncode=0):
    proc = SimpleNamespace(returncode=returncode, stdout=stdout)
    with patch("core.orchestrator.subprocess.run", return_value=proc) as run:
        resultat = process_post(
            url, "IMG", "VID", "TXT", tmp_db,
            _analyseur_texte_seul(), MagicMock(), tmp_path, lambda *a, **k: None,
        )
    return resultat, run


class TestProcessPostTexte:
    def test_text_dir_transmis_a_text_py(self, tmp_db, tmp_path, sample_post_url):
        _, run = _lancer(tmp_db, tmp_path, sample_post_url, "   [TXT] fichier.txt\n")
        assert run.call_args.args[0] == ["python", "downloaders/text.py", "TXT", sample_post_url]

    def test_texte_enregistre_en_base_avec_le_vrai_nom(self, tmp_db, tmp_path, sample_post_url):
        resultat, _ = _lancer(tmp_db, tmp_path, sample_post_url, "   [TXT] fichier.txt\n")
        assert resultat[3] == 1  # text_count
        assert tmp_db.get_stats()["texts"] == 1
        lignes = tmp_db.conn.execute(
            "SELECT media_type, filename FROM media WHERE post_url = ?", (sample_post_url,)
        ).fetchall()
        assert [tuple(l) for l in lignes] == [("text", "fichier.txt")]

    def test_echec_du_sous_processus_n_enregistre_rien(self, tmp_db, tmp_path, sample_post_url):
        resultat, _ = _lancer(tmp_db, tmp_path, sample_post_url, "", returncode=2)
        assert resultat[0] is False
        assert tmp_db.get_stats()["texts"] == 0
