#!/usr/bin/env python3
"""
Orchestrateur principal de téléchargement
Analyse, résout et télécharge les médias des posts Bluesky.

Point d'entrée : run(urls, config, …), appelé directement par bsmb.py. Les
downloaders sont des fonctions appelées dans les threads d'un
ThreadPoolExecutor ; aucun sous-processus Python n'est lancé.

Usage manuel : python core/orchestrator.py <IMG_DIR> <VID_DIR> <TEXT_DIR> [--no-db] <URL1> [URL2] ...
"""
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    # Exécution directe (python core/orchestrator.py) : rendre la racine importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.post_analyzer import PostAnalyzer, PostType  # noqa: E402
from api.quote_resolver import QuoteResolver  # noqa: E402
from core import http as bsmb_http  # noqa: E402
from core import ui  # noqa: E402
from core.colors import c  # noqa: E402
from core.config import (  # noqa: E402
    DEFAULT_CONFIG,
    cleanup_old_logs,
    get_media_dirs,
    load_config,
    resolve_path,
)
from core.database import Database  # noqa: E402
from downloaders import DownloadError, lignes_console  # noqa: E402
from downloaders.archive import write_sidecar, write_text  # noqa: E402
from downloaders.external import download_external  # noqa: E402
from downloaders.images import download_images  # noqa: E402
from downloaders.text import nom_base_texte, save_text  # noqa: E402
from downloaders.videos import download_video  # noqa: E402

# Lock global pour l'affichage console (évite les lignes entrelacées)
_print_lock = threading.Lock()

# Profondeur maximale d'une chaîne de citations : le post bookmarké est à 0, le post
# qu'il cite à 1, celui que ce dernier cite à 2 ; au-delà, rien n'est archivé.
PROFONDEUR_MAX = 2


def get_folder_size(path):
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file():
                total += entry.stat().st_size
            elif entry.is_dir():
                total += get_folder_size(entry.path)
    except Exception:
        pass
    return total


def format_size(size_bytes):
    for unit in ['o', 'Ko', 'Mo', 'Go']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} To"


def format_duration(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


def save_debug_info(post_id, debug_info, logs_dir):
    """Sauvegarde les infos de debug pour analyse."""
    debug_file = logs_dir / f"debug_{post_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(debug_file, "w", encoding="utf-8") as f:
        json.dump(debug_info, f, indent=2, ensure_ascii=False)
    return debug_file


def _telecharger(downloader, url, dest_dir, config, buf_print, log_func, erreurs=None, **options):
    """
    Appelle un downloader et affiche ses résultats.
    Toute exception est isolée au post (journalisée, statut « failed ») pour
    ne jamais interrompre le lot.
    options : paramètres nommés transmis au downloader (name_prefix).
    erreurs : liste (optionnelle) à laquelle l'exception est ajoutée.
    Returns: la liste de DownloadResult (vide en cas d'erreur ou sans média).
    """
    try:
        results = downloader(url, dest_dir, config, **options)
    except DownloadError as e:
        buf_print(f"       [ERR] {e}")
        log_func(f"   ERREUR DE TÉLÉCHARGEMENT: {url} - {e}", to_console=False)
        if erreurs is not None:
            erreurs.append(e)
        return []
    except Exception as e:
        buf_print(f"       [ERR] Erreur inattendue : {e}")
        log_func(f"   ERREUR INATTENDUE: {url} - {type(e).__name__}: {e}", to_console=False)
        if erreurs is not None:
            erreurs.append(e)
        return []
    if not results:
        buf_print("       [!] Aucun média trouvé")
    for ligne in lignes_console(results):
        buf_print(f"    {ligne}")
    return results


@dataclass
class _Contexte:
    """Ce dont l'archivage d'un post (et de ses citations) a besoin."""
    dirs: dict
    config: dict
    analyzer: object
    resolver: object
    buf_print: object
    log_func: object
    db: object = None
    session: object = None   # session HTTP partagée (None : les downloaders prennent core.http.get_session())


def _session(ctx):
    """Option `session=` à transmettre aux downloaders (rien si aucune session n'est fournie)."""
    return {"session": ctx.session} if ctx.session is not None else {}


# Libellés des états d'un record cité qui n'est plus lisible
_ETATS_CITE_ABSENT = {"not_found": "supprimé", "blocked": "bloqué", "detached": "détaché"}


def _chemin_par_cid(ctx):
    """Callback cid -> chemin du fichier image déjà enregistré en base (None sans base ou si inconnu)."""
    if not ctx.db:
        return None

    def chemin(cid):
        nom = ctx.db.find_media_by_cid(cid)
        return str(Path(ctx.dirs["img_dir"]) / nom) if nom else None
    return chemin


def _contenu_propre(post_type, data, url, ctx, name_prefix=None, erreurs=None, debug_info=None, post_view=None):
    """
    Télécharge le contenu propre d'un post selon son type (sans suivre sa citation), puis
    écrit son texte lisible (.txt) et sa fiche JSON.

    name_prefix : base de nom des fichiers d'un post cité (None pour le post bookmarké).
    erreurs : liste complétée avec les erreurs de téléchargement rencontrées.
    debug_info : informations de l'analyseur ; son record brut donne les CID et l'alt des
        images, le texte et la fiche JSON.
    post_view : vue hydratée du post (cache des bookmarks), conservée dans la fiche JSON.
    Returns: la liste de DownloadResult.
    """
    cite = name_prefix is not None
    options = {"name_prefix": name_prefix} if cite else {}
    dirs = ctx.dirs
    args = (ctx.config, ctx.buf_print, ctx.log_func)
    results = []
    record = _record_brut(debug_info)
    nb_erreurs = len(erreurs) if erreurs is not None else 0

    if post_type == PostType.IMAGES:
        ctx.buf_print(c.info(f"{data.get('image_count', 1)} image(s) détectée(s)"))
        results = _telecharger(download_images, url, dirs["img_dir"], *args, erreurs=erreurs,
                               record=record, existing_cid=_chemin_par_cid(ctx), **_session(ctx), **options)
    elif post_type == PostType.VIDEO:
        ctx.buf_print(c.info("Vidéo détectée"))
        full = (debug_info or {}).get("full_data") or {}
        results = _telecharger(download_video, url, dirs["vid_dir"], *args, erreurs=erreurs,
                               record=full.get("value") or full.get("record"), did=data.get("did"),
                               view_embed=data.get("view_embed"), **_session(ctx), **options)
    elif post_type == PostType.EXTERNAL and not cite:
        # Embed externe : carte de lien, GIF, lien tiers
        ctx.buf_print(c.info("Lien externe détecté"))
        donnees = {**data, "record": record} if record else data  # le record donne facets et langue au .txt
        results = _telecharger(
            lambda u, _dest, cfg: download_external(u, donnees, dirs, cfg, **_session(ctx)),
            url, dirs["text_dir"], *args, erreurs=erreurs)
    elif post_type in (PostType.TEXT_ONLY, PostType.QUOTE, PostType.EXTERNAL):
        if cite and post_type == PostType.EXTERNAL:
            # Un lien externe cité n'est archivé que par son texte
            ctx.buf_print(f"  {c.DIM}Citation : carte de lien non archivée (texte seul){c.RESET}")
            ctx.log_func(f"   NOTE: citation : carte de lien non archivée (texte seul) ({url})", to_console=False)
        ctx.buf_print(c.info("Texte seul détecté" if post_type == PostType.TEXT_ONLY else "Texte du post détecté"))
        results = _telecharger(save_text, url, dirs["text_dir"], *args, erreurs=erreurs, **_session(ctx), **options)

    # Archive fidèle : texte lisible (hors types dont le downloader l'a déjà écrit) et fiche JSON
    if results and not (erreurs is not None and len(erreurs) > nb_erreurs):
        results = results + _archiver_post(results, url, data, ctx, record, post_view, name_prefix, erreurs)
    return results


def _record_brut(debug_info):
    """Record brut du post dans les informations de l'analyseur (getRecord ou postView), ou None."""
    full = (debug_info or {}).get("full_data")
    if not isinstance(full, dict):
        return None
    record = full.get("value") or full.get("record")
    return record if isinstance(record, dict) and record else None


def _archiver_citant_sans_contenu(propres, cites, url, data, debug_info, ctx, post_view, name_prefix, erreurs):
    """
    Un citant sans contenu propre (save_text n'a rien renvoyé) dont le cité est archivé garde
    quand même son .txt (avec « Cite: ») et sa fiche JSON.
    Returns: la liste des DownloadResult ajoutés (vide si le citant a un contenu propre).
    """
    if propres or not cites or (erreurs is not None and erreurs):
        return []
    return _archiver_post([], url, data, ctx, _record_brut(debug_info), post_view, name_prefix, erreurs)


def _archiver_post(results, url, data, ctx, record, post_view, name_prefix, erreurs):
    """
    Écrit le .txt lisible (sauf si `results` en contient déjà un) puis, avec
    config["save_sidecar"], la fiche JSON du post. Sans record, rien n'est écrit.
    Returns: la liste des DownloadResult ajoutés.
    """
    if record is None:
        return []
    text_dir = ctx.dirs["text_dir"]
    args = (ctx.config, ctx.buf_print, ctx.log_func)
    ajoutes = []
    if not any(r.media_type == "text" for r in results):
        ajoutes += _telecharger(
            lambda u, d, cfg: write_text(u, record, d, cfg, name_prefix=name_prefix),
            url, text_dir, *args, erreurs=erreurs)
    if ctx.config.get("save_sidecar", DEFAULT_CONFIG["save_sidecar"]):
        ajoutes += _telecharger(
            lambda u, d, cfg: write_sidecar(u, record, post_view, d, cfg, name_prefix=name_prefix,
                                            at_uri=data.get("at_uri")),
            url, text_dir, *args, erreurs=erreurs)
    return ajoutes


def _base_de_nom(url, data):
    """<handle>_<YYYYMMDD>_<postid> du post citant : base commune des fichiers de ses citations."""
    post_id = url.rstrip("/").split("/")[-1]
    parts = url.split("/")
    handle = data.get("handle") or (parts[4] if len(parts) > 4 else "")
    return nom_base_texte(handle, post_id, data.get("created_at", ""))


def _archiver_citation(url, quote_uri, depth, base, ctx, post_view=None):
    """
    Archive le post cité par la citation `url` (de profondeur `depth`), puis, tant que
    la profondeur le permet, les citations de ce post cité.

    Les fichiers du post cité de profondeur n sont préfixés par `base` (identifiant du
    post bookmarké) : <base>_quote (n=1), <base>_quote2 (n=2).

    Returns: (results, problemes) où problemes est une liste de (genre, référence),
    genre valant "failed" (erreur réseau/serveur) ou un état de QuoteTarget
    ("not_found", "blocked", "detached").
    """
    # `post_view` (vue hydratée du citant) n'existe que pour le bookmark lui-même
    cible = ctx.resolver.resolve(url) if post_view is None else ctx.resolver.resolve(url, post_view=post_view)
    if cible is None:
        ref = quote_uri or url
        ctx.buf_print(c.warning("Citation non résolue"))
        ctx.log_func(f"   CITATION NON ARCHIVÉE: {ref}", to_console=False)
        return [], [("failed", ref)]

    if cible.state == "not_post":
        ctx.buf_print(f"  {c.DIM}Le record cité n'est pas un post ({cible.collection}) : ignoré{c.RESET}")
        ctx.log_func(f"   CITATION IGNORÉE: {url} - le record cité n'est pas un post ({cible.collection})",
                     to_console=False)
        return [], []

    if cible.state != "post":
        etat = _ETATS_CITE_ABSENT.get(cible.state, cible.state)
        ctx.buf_print(f"  {c.DIM}Post cité {etat}{c.RESET}")
        ctx.log_func(f"   NOTE: post cité {etat} ({cible.url or cible.at_uri}) pour {url}", to_console=False)
        return [], [(cible.state, cible.url or cible.at_uri)]

    profondeur = depth + 1
    ctx.buf_print(f"  {c.OK}>{c.RESET} Post cité : {c.VALUE}{cible.url}{c.RESET}")
    post_type, data, debug_info = ctx.analyzer.analyze(cible.url)

    if post_type == PostType.ERROR_400:
        ctx.buf_print(f"  {c.DIM}Post cité supprimé{c.RESET}")
        ctx.log_func(f"   NOTE: post cité supprimé ({cible.url}) pour {url}", to_console=False)
        return [], [("not_found", cible.url)]
    if post_type in (PostType.ERROR_500, PostType.ERROR_429) or (
            post_type == PostType.UNKNOWN and "error" in debug_info):
        ctx.buf_print(c.warning("Post cité inaccessible"))
        ctx.log_func(f"   CITATION NON ARCHIVÉE: {cible.url}", to_console=False)
        return [], [("failed", cible.url)]
    if post_type == PostType.UNKNOWN:
        ctx.buf_print(f"  {c.DIM}Contenu du post cité non reconnu : ignoré{c.RESET}")
        ctx.log_func(f"   NOTE: contenu du post cité non reconnu ({cible.url})", to_console=False)
        return [], []

    suffixe = "quote" if profondeur == 1 else f"quote{profondeur}"
    erreurs = []
    results = _contenu_propre(post_type, data, cible.url, ctx, name_prefix=f"{base}_{suffixe}", erreurs=erreurs,
                              debug_info=debug_info)
    problemes = []
    if erreurs:
        ctx.log_func(f"   CITATION NON ARCHIVÉE: {cible.url}", to_console=False)
        problemes.append(("failed", cible.url))

    est_citation = post_type == PostType.QUOTE or data.get("is_quote")
    if est_citation and profondeur < PROFONDEUR_MAX:
        suite, suite_problemes = _archiver_citation(cible.url, data.get("quote_uri"), profondeur, base, ctx)
        results = (_archiver_citant_sans_contenu(results, suite, cible.url, data, debug_info, ctx, None,
                                                 f"{base}_{suffixe}", erreurs) + results + suite)
        problemes += suite_problemes
    return results, problemes


def process_post(url, IMG_DIR, VID_DIR, TEXT_DIR, db, analyzer, resolver, logs_dir, log_func, config=None,
                 depth=0, quotes_unresolved=None, post_view=None, compteurs=None, session=None):
    """
    Traite un post unique et retourne les stats.
    Returns: (has_success, img_count, vid_count, text_count, status, output_lines)
    compteurs : dict (optionnel) complété avec « sidecars », le nombre de fiches JSON écrites.

    output_lines contient les lignes à afficher (buffered pour le mode parallèle).
    config : transmise aux downloaders (DEFAULT_CONFIG si None).
    depth : profondeur du post dans une chaîne de citations (0 pour un bookmark) ;
        les citations ne sont suivies que tant que depth < PROFONDEUR_MAX.
    quotes_unresolved : liste complétée avec `url` quand le post est archivé mais
        que le post qu'il cite n'a pas pu l'être (erreur réseau ou serveur).
    post_view : vue hydratée du post (getBookmarks) ; l'analyse se fait alors sans
        getRecord, et le résolveur y lit l'état du post cité.
    session : session HTTP transmise aux downloaders (défaut : core.http.get_session()).

    Une citation est archivée comme un post normal (texte, média d'un recordWithMedia),
    puis le post cité l'est à son tour ; tous les fichiers sont enregistrés sous `url`.
    """
    config = DEFAULT_CONFIG if config is None else config
    if compteurs is not None:
        compteurs["sidecars"] = 0
    output = []

    def buf_print(msg):
        output.append(msg)

    post_id = url.rstrip("/").split("/")[-1]

    # === ANALYSE PRÉALABLE ===
    if post_view is None:
        post_type, data, debug_info = analyzer.analyze(url)
    else:
        post_type, data, debug_info = analyzer.analyze(url, post_view=post_view)
    buf_print(f"  {c.KEY}Type détecté :{c.RESET} {c.VALUE}{post_type.value}{c.RESET}")

    # Tracking DB
    if db:
        handle = data.get("handle")
        db.add_post(url, post_id, handle, at_uri=data.get("at_uri"), did=data.get("did"))

    # === TRAITEMENT PAR TYPE ===

    # Erreur 500
    if post_type == PostType.ERROR_500:
        buf_print(c.warning("Erreur serveur (500)"))
        log_func(f"   ERREUR 500: {url}", to_console=False)
        if db:
            db.update_last_check(url)
            db.mark_post_status(url, 'error_500')
        return False, 0, 0, 0, 'error_500', output

    # Limite de débit (429) persistante après les reprises : retenté à la prochaine exécution
    if post_type == PostType.ERROR_429:
        buf_print(c.warning("Limite de débit (429)"))
        log_func(f"   LIMITE DE DÉBIT 429: {url}", to_console=False)
        if db:
            db.update_last_check(url)
            db.mark_post_status(url, 'error_429')
        return False, 0, 0, 0, 'error_429', output

    # Post supprimé
    if post_type == PostType.ERROR_400:
        buf_print(c.error("Post supprimé ou inaccessible (400)"))
        log_func(f"   POST SUPPRIMÉ: {url}", to_console=False)
        if db:
            db.mark_post_status(url, 'deleted')
        return False, 0, 0, 0, 'error_400', output

    # Cas inconnu - MODE DEBUG
    if post_type == PostType.UNKNOWN:
        buf_print(c.warning("Type de post non reconnu"))
        debug_file = save_debug_info(post_id, debug_info, logs_dir)
        buf_print(f"  {c.DIM}Debug sauvegardé : {debug_file.name}{c.RESET}")
        buf_print(c.config_line("Embed type", debug_info.get('embed_type', 'N/A')))
        buf_print(c.config_line("Has embed", str(debug_info.get('has_embed', False))))
        buf_print(c.config_line("Texte", data.get('text', '')[:80] + "..."))

        log_func(f"   TYPE INCONNU: {url} - Debug: {debug_file.name}", to_console=False)
        if db:
            db.mark_post_status(url, 'unknown')
        return False, 0, 0, 0, 'unknown', output

    ctx = _Contexte(
        dirs={"img_dir": IMG_DIR, "vid_dir": VID_DIR, "text_dir": TEXT_DIR},
        config=config, analyzer=analyzer, resolver=resolver, buf_print=buf_print, log_func=log_func, db=db,
        session=session,
    )
    est_citation = post_type == PostType.QUOTE or bool(data.get("is_quote"))

    # 1. Le post bookmarké, d'après son propre contenu
    if est_citation:
        buf_print(c.info("Citation détectée, résolution du post cité..."))
    erreurs = []
    results = _contenu_propre(post_type, data, url, ctx, erreurs=erreurs, debug_info=debug_info,
                              post_view=post_view)

    # 2. Le post qu'il cite (profondeur max PROFONDEUR_MAX)
    problemes = []
    if est_citation and depth < PROFONDEUR_MAX:
        cites, problemes = _archiver_citation(url, data.get("quote_uri"), depth, _base_de_nom(url, data), ctx,
                                              post_view=post_view)
        results = (_archiver_citant_sans_contenu(results, cites, url, data, debug_info, ctx, post_view, None,
                                                 erreurs) + results + cites)

    # Une image sautée (cid déjà archivé) est affichée mais ni comptée ni enregistrée
    a_enregistrer = [r for r in results if not r.skipped]
    img_count = sum(r.media_type == "image" for r in a_enregistrer)
    vid_count = sum(r.media_type == "video" for r in a_enregistrer)
    text_count = sum(r.media_type == "text" for r in a_enregistrer)
    if compteurs is not None:
        compteurs["sidecars"] = sum(r.media_type == "sidecar" for r in a_enregistrer)
    echec_citation = any(genre == "failed" for genre, _ in problemes)

    # Bilan
    if erreurs:
        # Le contenu propre du post n'est pas complet : on garde ce qui a été obtenu,
        # mais le post reste retentable (comme un post simple en échec)
        if db and results:
            for r in a_enregistrer:
                db.add_media(url, r.media_type, r.filename, cid=r.cid)
            db.update_last_check(url)
        log_func(f"   ÉCHEC: {url}", to_console=False)
        return False, 0, 0, 0, 'failed', output

    if results:
        if db:
            for r in a_enregistrer:
                db.add_media(url, r.media_type, r.filename, cid=r.cid)
            db.update_last_check(url)
            # Un post retenté avec succès ne doit plus rester en erreur
            db.mark_post_status(url, 'ok')
        if echec_citation and quotes_unresolved is not None:
            quotes_unresolved.append(url)
        log_func(f"   SUCCÈS: {url}", to_console=False)
        return True, img_count, vid_count, text_count, 'success', output

    # Rien d'archivé : le citant n'a pas de contenu propre et son cité est supprimé,
    # bloqué ou détaché -> rien à conserver, comme un post supprimé
    if est_citation and not erreurs and problemes and not echec_citation:
        buf_print(c.error("Post cité supprimé ou inaccessible"))
        log_func(f"   POST SUPPRIMÉ: {url}", to_console=False)
        if db:
            db.mark_post_status(url, 'deleted')
        return False, 0, 0, 0, 'error_400', output

    log_func(f"   ÉCHEC: {url}", to_console=False)
    return False, 0, 0, 0, 'failed', output


def _format_job_summary(idx, total, url, status, img_count, vid_count, text_count):
    """Formate le résumé compact d'un job sur une ligne."""
    post_id = url.rstrip("/").split("/")[-1]
    parts = url.split("/")
    handle = parts[4] if len(parts) > 4 else "?"

    counter = f"[{idx}/{total}]"

    if status == 'success':
        details = []
        if img_count:
            details.append(f"{img_count} image{'s' if img_count > 1 else ''}")
        if vid_count:
            details.append(f"{vid_count} vidéo{'s' if vid_count > 1 else ''}")
        if text_count:
            details.append(f"{text_count} texte{'s' if text_count > 1 else ''}")
        detail_str = ", ".join(details) if details else "OK"
        return f"  {c.DIM}{counter}{c.RESET} {c.GREEN}OK{c.RESET} {c.VALUE}{handle}/{post_id}{c.RESET} {c.DIM}{detail_str}{c.RESET}"
    elif status == 'error_400':
        return f"  {c.DIM}{counter}{c.RESET} {c.RED}--{c.RESET} {c.DIM}post supprimé (400){c.RESET}"
    elif status == 'error_500':
        return f"  {c.DIM}{counter}{c.RESET} {c.RED}--{c.RESET} {c.DIM}erreur serveur (500){c.RESET}"
    elif status == 'error_429':
        return f"  {c.DIM}{counter}{c.RESET} {c.YELLOW}--{c.RESET} {c.DIM}limite de débit (429){c.RESET}"
    elif status == 'unknown':
        return f"  {c.DIM}{counter}{c.RESET} {c.YELLOW}??{c.RESET} {c.DIM}type inconnu{c.RESET}"
    else:
        return f"  {c.DIM}{counter}{c.RESET} {c.RED}!!{c.RESET} {c.DIM}échec{c.RESET}"


def _print_progress_bar(completed, total, img_total, vid_total, text_total):
    """Affiche une barre de progression mise à jour."""
    bar_width = 30
    filled = int(bar_width * completed / total) if total > 0 else 0
    bar = "█" * filled + "░" * (bar_width - filled)
    pct = int(100 * completed / total) if total > 0 else 0

    details = []
    if img_total:
        details.append(f"{img_total} img")
    if vid_total:
        details.append(f"{vid_total} vid")
    if text_total:
        details.append(f"{text_total} txt")
    detail_str = f" ({', '.join(details)})" if details else ""

    line = f"  {c.DIM}Progression :{c.RESET} [{c.CYAN}{bar}{c.RESET}] {completed}/{total} {pct}%{detail_str}"
    sys.stdout.write(f"\r{line}  ")
    sys.stdout.flush()


def print_report(stats, duration, total_size, no_db_mode, log_file, max_workers, generated_files=()):
    """Affiche le rapport final structuré (generated_files : sortie de _save_problem_logs)."""
    border = "=" * 80
    print(f"\n  {c.HEADER}{border}{c.RESET}")
    print(f"  {c.HEADER}{'RAPPORT DE TÉLÉCHARGEMENT':^80}{c.RESET}")
    print(f"  {c.HEADER}{border}{c.RESET}")
    print()

    # Résultats
    print(c.title("  RÉSULTATS"))
    print(c.separator(width=78))
    print(c.config_line("Posts traités", f"{stats['success']}/{stats['total']}", 28))
    print(c.config_line("Images téléchargées", str(stats['images']), 28))
    print(c.config_line("Vidéos téléchargées", str(stats['videos']), 28))
    print(c.config_line("Textes sauvegardés", str(stats['texts']), 28))
    print(c.config_line("Fiches JSON", str(stats.get('sidecars', 0)), 28))
    print()

    # Problèmes (seulement si présents)
    non_resolues = stats.get('quotes_unresolved', stats.get('reposts', []))
    has_problems = any([
        stats['error_500'], stats.get('error_429', []), stats['error_400'],
        non_resolues, stats['unknown'], stats['failed']
    ])

    if has_problems:
        print(c.title("  PROBLÈMES"))
        print(c.separator(width=78))
        if stats['error_400']:
            print(c.config_line("Posts supprimés (400)", str(len(stats['error_400'])), 28))
        if stats['error_500']:
            print(c.config_line("Erreurs serveur (500)", str(len(stats['error_500'])), 28))
        if stats.get('error_429'):
            print(c.config_line("Limite de débit (429)", str(len(stats['error_429'])), 28))
        if non_resolues:
            print(c.config_line("Citations non archivées", str(len(non_resolues)), 28))
        if stats['unknown']:
            print(c.config_line("Types inconnus", str(len(stats['unknown'])), 28))
        if stats['failed']:
            print(c.config_line("Échecs", str(len(stats['failed'])), 28))
        print()

    # Métriques
    print(c.title("  MÉTRIQUES"))
    print(c.separator(width=78))
    print(c.config_line("Durée totale", format_duration(duration), 28))
    print(c.config_line("Workers parallèles", str(max_workers), 28))
    print(c.config_line("Poids total du dossier", format_size(total_size), 28))

    if no_db_mode:
        print()
        print(c.warning("Mode dev : Base de données non mise à jour"))

    print()
    print(f"  {c.HEADER}{border}{c.RESET}")

    # Fichiers de log générés
    if generated_files:
        print()
        print(c.title("  FICHIERS GÉNÉRÉS"))
        print(c.separator(width=78))
        for name, detail in generated_files:
            print(f"  {c.YELLOW}>{c.RESET} {c.VALUE}{name}{c.RESET}  ({detail})")

    print(f"\n  {c.DIM}Log détaillé : {log_file}{c.RESET}")


def _save_problem_logs(stats, logs_dir):
    """Écrit un fichier par catégorie de problème ; renvoie [(nom, détail), …]."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    generated = []

    entries = [
        ("error_400", "deleted_posts", "posts supprimés"),
        ("quotes_unresolved", "quotes_unresolved", "citations non archivées"),
        ("error_500", "error_500", "erreurs 500"),
        ("error_429", "rate_limited", "limites de débit (429)"),
        ("unknown", "unknown_types", "types inconnus"),
        ("failed", "failed_downloads", "échecs"),
    ]

    for key, prefix, label in entries:
        urls = stats.get(key, [])
        if urls:
            filepath = logs_dir / f"{prefix}_{timestamp}.txt"
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(urls))
            generated.append((filepath.name, f"{len(urls)} {label}"))

    return generated


def run(urls, config, no_db=False, on_progress=None, quiet=False, post_views=None) -> dict:
    """
    Télécharge les médias des posts `urls` dans les sous-dossiers de config["download_dir"].

    Args:
        urls: URLs de posts bsky.app
        config: configuration chargée (load_config())
        no_db: ne pas lire ni écrire la base (mode dev)
        on_progress: callback(termines, total) appelé après chaque post
        quiet: aucune sortie console (ni progression ni rapport)
        post_views: {URL du post: postView brut} issu du cache des bookmarks ; les posts
            qui y figurent sont analysés sans getRecord (None = mode dev, getRecord partout)

    Returns:
        dict: {"total", "success", "images", "videos", "texts", "sidecars",
               "error_500", "error_429", "error_400", "quotes_unresolved", "reposts", "unknown",
               "failed"}
        (les sept dernières clés sont des listes d'URLs ; "error_429" : limite de débit encore
        atteinte après les reprises, post retenté à la prochaine exécution ; "quotes_unresolved" liste les
        bookmarks archivés dont le post cité ne l'a pas été, "reposts" est son ancien nom)
    """
    return _run(urls, config, media_dirs=get_media_dirs(config), no_db=no_db,
                on_progress=on_progress, quiet=quiet, post_views=post_views)


def _run(urls, config, media_dirs, no_db=False, on_progress=None, quiet=False, post_views=None):
    """run() avec des dossiers médias explicites (utilisé par la CLI)."""
    post_views = post_views or {}
    start_time = time.time()
    IMG_DIR = media_dirs["img_dir"]
    VID_DIR = media_dirs["vid_dir"]
    TEXT_DIR = media_dirs["text_dir"]

    max_workers = max(1, int(config.get("max_workers", 4)))
    session = bsmb_http.get_session()  # une seule session pour tous les workers
    analyzer = PostAnalyzer(session)
    resolver = QuoteResolver(session)

    # Compteurs (mis à jour dans le thread principal, au fil de as_completed)
    total_jobs = len(urls)
    success_count = 0
    img_count = 0
    vid_count = 0
    text_count = 0
    sidecar_count = 0
    completed_count = 0
    failed_urls = []
    deleted_urls = []
    quotes_unresolved_urls = []  # alimentée par les workers (list.append est atomique)
    error_500_urls = []
    error_429_urls = []
    unknown_urls = []

    # Logs
    logs_dir = resolve_path(config, "logs_dir")
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_lock = threading.Lock()

    def log(msg, to_console=True):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {msg}\n"
        with log_lock:
            with open(str(log_file), "a", encoding="utf-8") as f:
                f.write(log_line)
        if to_console and not quiet:
            with _print_lock:
                print(msg)

    log(f"=== Début du téléchargement : {total_jobs} posts à traiter ({max_workers} workers) ===")
    # Nettoyage après création du nouveau log : max_logs fichiers au total, celui-ci compris
    cleanup_old_logs(config)
    if no_db:
        log("MODE DEV: Base de données désactivée", to_console=False)

    # En-tête
    if not quiet:
        print()
        print(f"  {c.HEADER}{'─' * 78}{c.RESET}")
        print(f"  {c.BOLD}{total_jobs} posts à traiter{c.RESET} {c.DIM}({max_workers} workers parallèles){c.RESET}")
        print(f"  {c.HEADER}{'─' * 78}{c.RESET}")
        print()

    db = None if no_db else Database(resolve_path(config, "db_file"))

    def worker(idx, url):
        """Worker qui traite un post et retourne le résultat."""
        log(f"Job {idx}/{total_jobs}: {url}", to_console=False)
        compteurs = {}
        has_success, imgs, vids, texts, status, output_lines = process_post(
            url, IMG_DIR, VID_DIR, TEXT_DIR, db, analyzer, resolver, logs_dir, log, config,
            quotes_unresolved=quotes_unresolved_urls, post_view=post_views.get(url), compteurs=compteurs,
            session=session,
        )
        return idx, url, has_success, imgs, vids, texts, status, output_lines, compteurs["sidecars"]

    # === EXÉCUTION PARALLÈLE ===
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(worker, idx, url): (idx, url)
                for idx, url in enumerate(urls, start=1)
            }

            for future in as_completed(futures):
                idx, url, has_success, imgs, vids, texts, status, output_lines, sidecars = future.result()

                completed_count += 1
                if has_success:
                    success_count += 1
                    img_count += imgs
                    vid_count += vids
                    text_count += texts
                    sidecar_count += sidecars

                if status == 'error_500':
                    error_500_urls.append(url)
                elif status == 'error_429':
                    error_429_urls.append(url)
                elif status == 'error_400':
                    deleted_urls.append(url)
                elif status == 'unknown':
                    unknown_urls.append(url)
                elif status == 'failed':
                    failed_urls.append(url)

                if not quiet:
                    with _print_lock:
                        summary = _format_job_summary(idx, total_jobs, url, status, imgs, vids, texts)
                        print(summary)
                        _print_progress_bar(completed_count, total_jobs, img_count, vid_count, text_count)
                if on_progress:
                    on_progress(completed_count, total_jobs)
    finally:
        if db:
            db.close()

    if not quiet:
        # Effacer la barre de progression
        sys.stdout.write("\r" + " " * 100 + "\r")
        sys.stdout.flush()

    stats = {
        'total': total_jobs,
        'success': success_count,
        'images': img_count,
        'videos': vid_count,
        'texts': text_count,
        'sidecars': sidecar_count,
        'error_500': error_500_urls,
        'error_429': error_429_urls,
        'error_400': deleted_urls,
        'quotes_unresolved': quotes_unresolved_urls,
        'reposts': quotes_unresolved_urls,  # ancien nom, même liste
        'unknown': unknown_urls,
        'failed': failed_urls,
    }

    generated = _save_problem_logs(stats, logs_dir)

    if not quiet:
        duration = time.time() - start_time
        total_size = get_folder_size(IMG_DIR) + get_folder_size(VID_DIR)
        print_report(stats, duration, total_size, no_db, log_file, max_workers, generated)

    return stats


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    no_db_mode = "--no-db" in argv
    if no_db_mode:
        argv.remove("--no-db")

    if len(argv) < 4:
        print("Usage: python orchestrator.py <IMG_DIR> <VID_DIR> <TEXT_DIR> [--no-db] <URL1> [URL2] ...")
        sys.exit(1)

    media_dirs = {"img_dir": argv[0], "vid_dir": argv[1], "text_dir": argv[2]}
    config = load_config()
    stats = _run(argv[3:], config, media_dirs=media_dirs, no_db=no_db_mode)

    # Option « open_folder_after_download » (défaut vrai), ignorée en non interactif
    if (stats["success"] > 0 and config.get("open_folder_after_download", True)
            and ui.is_interactive()):
        download_dir = config["download_dir"]
        if sys.platform == "win32":
            os.startfile(download_dir)
        else:
            subprocess.run(["xdg-open", download_dir])


if __name__ == "__main__":
    # Forcer l'encodage UTF-8 pour la console Windows (exécution directe uniquement)
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    main()
