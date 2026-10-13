"""Tests de l'orchestrateur : process_post() et run() avec downloaders mockés (issues #8, #10)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from api.post_analyzer import PostType
from core import orchestrator
from core.database import Database
from core.orchestrator import process_post, run
from downloaders import DownloadError, DownloadResult

URL = "https://bsky.app/profile/user.bsky.social/post/3k1"
URL2 = "https://bsky.app/profile/user.bsky.social/post/3k2"


def _res(nom, media_type, cid=None):
    return DownloadResult(nom, Path(nom), media_type, 10, cid)


def _analyseur(post_type, data=None, debug_info=None):
    analyzer = MagicMock()
    analyzer.analyze.return_value = (post_type, data or {"handle": "user.bsky.social"}, debug_info or {})
    return analyzer


def _lancer(db, tmp_path, post_type, data=None, *, images=None, video=None, texte=None, erreur=None,
            debug_info=None):
    """process_post() avec les trois downloaders mockés ; renvoie (résultat, mocks)."""
    mocks = {
        "download_images": MagicMock(return_value=images or [], side_effect=erreur),
        "download_video": MagicMock(return_value=video or [], side_effect=erreur),
        "save_text": MagicMock(return_value=texte or [], side_effect=erreur),
    }
    with patch.multiple("core.orchestrator", **mocks):
        resultat = process_post(
            URL, "IMG", "VID", "TXT", db, _analyseur(post_type, data, debug_info), MagicMock(),
            tmp_path, lambda *a, **k: None, config={"max_filename_len": 64},
        )
    return resultat, mocks


def _medias(db):
    return [tuple(m) for m in db.conn.execute("SELECT media_type, filename, cid FROM media ORDER BY id")]


class TestProcessPostTexte:
    def test_text_dir_et_config_transmis_a_save_text(self, tmp_db, tmp_path):
        _, mocks = _lancer(tmp_db, tmp_path, PostType.TEXT_ONLY, texte=[_res("f.txt", "text")])
        mocks["save_text"].assert_called_once_with(URL, "TXT", {"max_filename_len": 64})

    def test_texte_enregistre_en_base_avec_le_vrai_nom(self, tmp_db, tmp_path):
        resultat, _ = _lancer(tmp_db, tmp_path, PostType.TEXT_ONLY, texte=[_res("fichier.txt", "text")])
        assert resultat[3] == 1  # text_count
        assert tmp_db.get_stats()["texts"] == 1
        assert _medias(tmp_db) == [("text", "fichier.txt", None)]

    def test_aucun_texte_n_enregistre_rien(self, tmp_db, tmp_path):
        resultat, _ = _lancer(tmp_db, tmp_path, PostType.TEXT_ONLY)
        assert resultat[0] is False
        assert resultat[4] == "failed"
        assert tmp_db.get_stats()["texts"] == 0


class TestProcessPostExternal:
    DATA = {"handle": "user.bsky.social", "external": {"uri": "https://example.com"}}

    def _lancer(self, db, tmp_path, resultats=None, erreur=None):
        dl = MagicMock(return_value=resultats or [], side_effect=erreur)
        with patch("core.orchestrator.download_external", dl):
            resultat = process_post(
                URL, "IMG", "VID", "TXT", db, _analyseur(PostType.EXTERNAL, self.DATA), MagicMock(),
                tmp_path, lambda *a, **k: None, config={"max_filename_len": 64},
            )
        return resultat, dl

    def test_arguments_transmis_au_downloader(self, tmp_db, tmp_path):
        _, dl = self._lancer(tmp_db, tmp_path, [_res("t.txt", "text")])
        dl.assert_called_once_with(
            URL, self.DATA, {"img_dir": "IMG", "vid_dir": "VID", "text_dir": "TXT"}, {"max_filename_len": 64})

    def test_comptage_par_type_et_base(self, tmp_db, tmp_path):
        res = [_res("t.txt", "text"), _res("t_thumb.jpg", "image", "bafkrei"), _res("t_01.mp4", "video")]
        resultat, _ = self._lancer(tmp_db, tmp_path, res)
        assert resultat[:5] == (True, 1, 1, 1, "success")
        assert _medias(tmp_db) == [("text", "t.txt", None), ("image", "t_thumb.jpg", "bafkrei"),
                                   ("video", "t_01.mp4", None)]

    def test_lignes_console(self, tmp_db, tmp_path):
        res = [_res("t.txt", "text"), _res("t_thumb.jpg", "image")]
        resultat, _ = self._lancer(tmp_db, tmp_path, res)
        assert any("[TXT] t.txt" in ligne for ligne in resultat[5])
        assert any("[DL] Téléchargé -> t_thumb.jpg" in ligne for ligne in resultat[5])

    def test_texte_seul_suffit(self, tmp_db, tmp_path):
        resultat, _ = self._lancer(tmp_db, tmp_path, [_res("t.txt", "text")])
        assert resultat[:5] == (True, 0, 0, 1, "success")

    def test_download_error_donne_failed(self, tmp_db, tmp_path):
        resultat, _ = self._lancer(tmp_db, tmp_path, erreur=DownloadError("disque plein"))
        assert resultat[:5] == (False, 0, 0, 0, "failed")
        assert _medias(tmp_db) == []


class TestProcessPostMedias:
    def test_images_comptees_depuis_les_resultats(self, tmp_db, tmp_path):
        res = [_res("a_1.jpg", "image"), _res("a_2.png", "image")]
        resultat, mocks = _lancer(tmp_db, tmp_path, PostType.IMAGES, {"image_count": 2}, images=res)
        mocks["download_images"].assert_called_once_with(
            URL, "IMG", {"max_filename_len": 64}, record=None, existing_cid=mocks["download_images"].call_args.kwargs["existing_cid"])
        assert resultat[:5] == (True, 2, 0, 0, "success")
        assert _medias(tmp_db) == [("image", "a_1.jpg", None), ("image", "a_2.png", None)]

    def test_record_brut_et_cid_transmis_a_download_images(self, tmp_db, tmp_path):
        record = {"embed": {"images": []}}
        res = [_res("a_1.png", "image", "bafy1")]
        _, mocks = _lancer(tmp_db, tmp_path, PostType.IMAGES, {"image_count": 1}, images=res,
                           debug_info={"full_data": {"uri": "at://x", "value": record}})
        kwargs = mocks["download_images"].call_args.kwargs
        assert kwargs["record"] is record
        assert _medias(tmp_db) == [("image", "a_1.png", "bafy1")]

    def test_callback_existing_cid_resout_le_chemin_via_la_base(self, tmp_db, tmp_path):
        tmp_db.add_post(URL, "3k1", "user.bsky.social")
        tmp_db.add_media(URL, "image", "deja.png", cid="bafy1")
        _, mocks = _lancer(tmp_db, tmp_path, PostType.IMAGES, {"image_count": 1}, images=[_res("a.jpg", "image")])
        existing = mocks["download_images"].call_args.kwargs["existing_cid"]
        assert existing("bafy1") == str(Path("IMG") / "deja.png")
        assert existing("inconnu") is None

    def test_image_sautee_affichee_mais_ni_comptee_ni_enregistree(self, tmp_db, tmp_path):
        res = [DownloadResult("deja.png", Path("deja.png"), "image", 5, "bafy1", skipped=True),
               _res("b_2.jpg", "image", "bafy2")]
        resultat, _ = _lancer(tmp_db, tmp_path, PostType.IMAGES, {"image_count": 2}, images=res)
        assert resultat[:5] == (True, 1, 0, 0, "success")
        assert _medias(tmp_db) == [("image", "b_2.jpg", "bafy2")]
        assert any("[SKIP] bafy1 déjà présent : deja.png" in ligne for ligne in resultat[5])

    def test_toutes_images_sautees_reste_un_succes(self, tmp_db, tmp_path):
        res = [DownloadResult("deja.png", Path("deja.png"), "image", 5, "bafy1", skipped=True)]
        resultat, _ = _lancer(tmp_db, tmp_path, PostType.IMAGES, {"image_count": 1}, images=res)
        assert resultat[:5] == (True, 0, 0, 0, "success")
        assert _medias(tmp_db) == []

    def test_sans_base_pas_de_callback(self, tmp_path):
        _, mocks = _lancer(None, tmp_path, PostType.IMAGES, {"image_count": 1}, images=[_res("a.jpg", "image")])
        assert mocks["download_images"].call_args.kwargs["existing_cid"] is None

    def test_lignes_console_produites_par_l_orchestrateur(self, tmp_db, tmp_path):
        res = [_res("a_1.jpg", "image")]
        resultat, _ = _lancer(tmp_db, tmp_path, PostType.IMAGES, {"image_count": 1}, images=res)
        assert any("[DL] Téléchargé -> a_1.jpg" in ligne for ligne in resultat[5])

    def test_video_avec_cid(self, tmp_db, tmp_path):
        resultat, mocks = _lancer(tmp_db, tmp_path, PostType.VIDEO, video=[_res("v.mp4", "video", "bafy")])
        mocks["download_video"].assert_called_once_with(URL, "VID", {"max_filename_len": 64})
        assert resultat[:5] == (True, 0, 1, 0, "success")
        assert _medias(tmp_db) == [("video", "v.mp4", "bafy")]
        assert any("[OK] Fichier enregistré : v.mp4" in ligne for ligne in resultat[5])

    def test_download_error_donne_failed(self, tmp_db, tmp_path):
        resultat, _ = _lancer(tmp_db, tmp_path, PostType.IMAGES, {"image_count": 1},
                              erreur=DownloadError("Post supprimé ou inaccessible"))
        assert resultat[:5] == (False, 0, 0, 0, "failed")
        assert _medias(tmp_db) == []
        assert any("[ERR] Post supprimé ou inaccessible" in ligne for ligne in resultat[5])

    def test_aucun_subprocess_python(self, tmp_db, tmp_path):
        with patch("subprocess.run") as run_:
            _lancer(tmp_db, tmp_path, PostType.TEXT_ONLY, texte=[_res("f.txt", "text")])
        run_.assert_not_called()

    def test_config_par_defaut(self, tmp_db, tmp_path):
        with patch("core.orchestrator.save_text", return_value=[]) as st:
            process_post(URL, "IMG", "VID", "TXT", tmp_db, _analyseur(PostType.TEXT_ONLY),
                         MagicMock(), tmp_path, lambda *a, **k: None)
        assert st.call_args.args[2]["max_filename_len"] == 64


# --------------------------------------------------------------------- run()

@pytest.fixture
def env_run(tmp_config):
    """Analyse et downloaders mockés pour run() ; renvoie (config, analyzer, mocks)."""
    analyzer = MagicMock()
    mocks = {
        "download_images": MagicMock(return_value=[_res("i.jpg", "image")]),
        "download_video": MagicMock(return_value=[_res("v.mp4", "video", "cidv")]),
        "save_text": MagicMock(return_value=[_res("t.txt", "text")]),
    }
    with patch.multiple("core.orchestrator", PostAnalyzer=MagicMock(return_value=analyzer),
                        QuoteResolver=MagicMock(), **mocks):
        yield tmp_config, analyzer, mocks


def _types(analyzer, par_url):
    analyzer.analyze.side_effect = lambda url: (par_url[url], {"handle": "user.bsky.social", "image_count": 1}, {})


class TestRun:
    def test_statistiques_retournees(self, env_run, capsys):
        config, analyzer, _ = env_run
        _types(analyzer, {URL: PostType.IMAGES, URL2: PostType.ERROR_400})
        stats = run([URL, URL2], config, quiet=True)
        assert stats == {
            "total": 2, "success": 1, "images": 1, "videos": 0, "texts": 0,
            "error_500": [], "error_400": [URL2], "quotes_unresolved": [], "reposts": [],
            "unknown": [], "failed": [],
        }
        assert capsys.readouterr().out == ""

    def test_dossiers_medias_derives_de_download_dir(self, env_run):
        config, analyzer, mocks = env_run
        _types(analyzer, {URL: PostType.IMAGES, URL2: PostType.TEXT_ONLY})
        run([URL, URL2], config, quiet=True)
        base = Path(config["download_dir"])
        assert mocks["download_images"].call_args.args[1] == str(base / "images")
        assert mocks["save_text"].call_args.args[1] == str(base / "texts")
        assert mocks["save_text"].call_args.args[2] is config

    def test_base_mise_a_jour(self, env_run):
        config, analyzer, _ = env_run
        _types(analyzer, {URL: PostType.VIDEO})
        run([URL], config, quiet=True)
        db = Database(config["db_file"])
        try:
            assert db.get_stats()["videos"] == 1
            assert db.conn.execute("SELECT status FROM posts WHERE url = ?", (URL,)).fetchone()[0] == "ok"
        finally:
            db.close()

    def test_no_db_ne_cree_pas_de_base(self, env_run):
        config, analyzer, _ = env_run
        _types(analyzer, {URL: PostType.TEXT_ONLY})
        stats = run([URL], config, no_db=True, quiet=True)
        assert stats["texts"] == 1
        assert not Path(config["db_file"]).exists()

    def test_logs_ecrits(self, env_run):
        config, analyzer, _ = env_run
        _types(analyzer, {URL: PostType.ERROR_500})
        run([URL], config, quiet=True)
        logs = Path(config["logs_dir"])
        assert len(list(logs.glob("download_*.log"))) == 1
        (fichier,) = logs.glob("error_500_*.txt")
        assert fichier.read_text(encoding="utf-8") == URL

    def test_on_progress(self, env_run):
        config, analyzer, _ = env_run
        _types(analyzer, {URL: PostType.TEXT_ONLY, URL2: PostType.TEXT_ONLY})
        appels = []
        run([URL, URL2], config, quiet=True, on_progress=lambda fait, total: appels.append((fait, total)))
        assert appels == [(1, 2), (2, 2)]

    def test_rapport_affiche_sauf_quiet(self, env_run, capsys):
        config, analyzer, _ = env_run
        _types(analyzer, {URL: PostType.TEXT_ONLY})
        run([URL], config)
        sortie = capsys.readouterr().out
        assert "RAPPORT DE TÉLÉCHARGEMENT" in sortie
        assert "1 posts à traiter" in sortie

    def test_pas_d_input(self, env_run):
        config, analyzer, _ = env_run
        _types(analyzer, {URL: PostType.TEXT_ONLY})
        with patch("builtins.input", side_effect=AssertionError("input() dans run()")):
            run([URL], config)

    def test_exception_inattendue_d_un_downloader_n_interrompt_pas_le_lot(self, env_run):
        config, analyzer, mocks = env_run
        _types(analyzer, {URL: PostType.IMAGES, URL2: PostType.TEXT_ONLY})
        mocks["download_images"].side_effect = OSError("disque plein")
        stats = run([URL, URL2], config, quiet=True)
        assert stats["failed"] == [URL]
        assert stats["success"] == 1
        assert stats["texts"] == 1
        logs = Path(config["logs_dir"])
        (log,) = logs.glob("download_*.log")
        assert "disque plein" in log.read_text(encoding="utf-8")
        (echecs,) = logs.glob("failed_downloads_*.txt")
        assert echecs.read_text(encoding="utf-8") == URL

    def test_message_download_error_journalise(self, env_run):
        config, analyzer, mocks = env_run
        _types(analyzer, {URL: PostType.VIDEO})
        mocks["download_video"].side_effect = DownloadError("Post supprimé ou inaccessible")
        stats = run([URL], config, quiet=True)
        assert stats["failed"] == [URL]
        (log,) = Path(config["logs_dir"]).glob("download_*.log")
        assert "Post supprimé ou inaccessible" in log.read_text(encoding="utf-8")

    def test_max_logs_au_total_apres_un_lot(self, env_run):
        import os
        import time

        config, analyzer, _ = env_run
        _types(analyzer, {URL: PostType.TEXT_ONLY})
        logs = Path(config["logs_dir"])
        logs.mkdir(parents=True)
        for i in range(5):
            ancien = logs / f"download_2026010{i}_000000.log"
            ancien.write_text("x")
            t = time.time() - (10 - i) * 60
            os.utime(ancien, (t, t))
        run([URL], {**config, "max_logs": 3}, quiet=True)
        restants = sorted(p.name for p in logs.glob("download_*.log"))
        assert len(restants) == 3
        assert restants[:2] == ["download_20260103_000000.log", "download_20260104_000000.log"]

    def test_logs_relatifs_ancres_sur_project_root(self, env_run, tmp_path, monkeypatch):
        config, analyzer, _ = env_run
        _types(analyzer, {URL: PostType.TEXT_ONLY})
        monkeypatch.setattr("core.config.PROJECT_ROOT", tmp_path / "racine")
        monkeypatch.chdir(tmp_path)
        run([URL], {**config, "logs_dir": "logs"}, quiet=True)
        assert list((tmp_path / "racine" / "logs").glob("download_*.log"))


class TestMainCli:
    def test_main_appelle_run_avec_les_dossiers_et_no_db(self, tmp_config):
        with patch.object(orchestrator, "load_config", return_value=tmp_config), \
             patch.object(orchestrator, "_run", return_value={"success": 0}) as run_:
            orchestrator.main(["I", "V", "T", "--no-db", URL, URL2])
        args, kwargs = run_.call_args
        assert args[0] == [URL, URL2]
        assert args[1] is tmp_config
        assert kwargs["media_dirs"] == {"img_dir": "I", "vid_dir": "V", "text_dir": "T"}
        assert kwargs["no_db"] is True

    def test_usage_si_arguments_manquants(self, capsys):
        with pytest.raises(SystemExit) as exc:
            orchestrator.main(["I", "V"])
        assert exc.value.code == 1
        assert "Usage" in capsys.readouterr().out


class TestPostViews:
    """run(..., post_views=...) transmet la vue hydratée à l'analyseur et au résolveur (issue #3)."""

    def test_run_transmet_le_post_view_a_analyze(self, env_run):
        config, analyzer, _ = env_run
        vue = {"uri": "at://did:plc:test/app.bsky.feed.post/3k1", "record": {}}
        analyzer.analyze.side_effect = None
        analyzer.analyze.return_value = (PostType.TEXT_ONLY, {"handle": "user.bsky.social"}, {})

        run([URL, URL2], config, quiet=True, post_views={URL: vue})

        appels = {c.args[0]: c.kwargs for c in analyzer.analyze.call_args_list}
        assert appels[URL] == {"post_view": vue}
        assert appels[URL2] == {}  # pas de vue : appel inchangé (getRecord)

    def test_run_sans_post_views_appel_inchange(self, env_run):
        config, analyzer, _ = env_run
        _types(analyzer, {URL: PostType.TEXT_ONLY})
        run([URL], config, quiet=True)
        analyzer.analyze.assert_called_once_with(URL)

    def test_resolveur_recoit_le_post_view_du_citant(self, tmp_db, tmp_path):
        vue = {"uri": "at://did:plc:test/app.bsky.feed.post/3k1", "record": {}}
        resolveur = MagicMock()
        resolveur.resolve.return_value = None
        analyseur = _analyseur(PostType.QUOTE, {"handle": "user.bsky.social", "is_quote": True,
                                                "quote_uri": "at://did:plc:x/app.bsky.feed.post/3kc"})
        with patch.multiple("core.orchestrator", save_text=MagicMock(return_value=[_res("t.txt", "text")])):
            process_post(URL, "IMG", "VID", "TXT", tmp_db, analyseur, resolveur,
                         tmp_path, lambda *a, **k: None, config={"max_filename_len": 64}, post_view=vue)
        analyseur.analyze.assert_called_once_with(URL, post_view=vue)
        resolveur.resolve.assert_called_once_with(URL, post_view=vue)
