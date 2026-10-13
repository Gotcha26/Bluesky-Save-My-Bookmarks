# downloaders/__init__.py
"""
Downloaders : fonctions de téléchargement des médias d'un post Bluesky.

Chaque downloader renvoie une liste de DownloadResult (liste vide = aucun
média trouvé) et lève DownloadError en cas d'erreur technique. Aucun
n'imprime : l'affichage est produit par l'appelant via lignes_console().
"""

from dataclasses import dataclass
from pathlib import Path

from core.i18n import _


@dataclass
class DownloadResult:
    """Un fichier écrit sur le disque par un downloader."""

    filename: str
    path: Path
    media_type: str  # "image", "video", "subtitle", "text" ou "sidecar" (fiche JSON)
    size: int  # taille en octets
    cid: str | None = None
    skipped: bool = False  # image déjà présente (même cid) : rien n'a été écrit
    alt: str | None = None  # texte alternatif du média (None si absent)


class DownloadError(Exception):
    """Erreur technique d'un downloader (API, réseau, écriture).

    partial : résultats déjà écrits sur le disque avant l'échec (échec partiel d'un
    lot, par exemple 2 images sur 3) ; liste vide par défaut.
    """

    def __init__(self, *args, partial=None):
        super().__init__(*args)
        self.partial = list(partial or [])


def _marqueurs():
    """Préfixes d'affichage par type de média (traduits au moment de l'appel, pas à l'import)."""
    return {
        "image": _("[DL] Téléchargé ->"),
        "video": _("[OK] Fichier enregistré :"),
        "text": _("[TXT]"),
        "subtitle": _("[SUB] Sous-titres ->"),
        "sidecar": _("[JSON]"),
    }


def lignes_console(results):
    """Lignes d'affichage historiques ([DL] / [OK] / [TXT]) pour des résultats."""
    lignes = []
    marqueurs = _marqueurs()
    for r in results:
        if r.skipped:
            lignes.append(
                "   " + _("[SKIP] {cid} déjà présent : {filename}").format(cid=r.cid, filename=r.filename)
            )
        else:
            lignes.append(f"   {marqueurs[r.media_type]} {r.filename}")
    return lignes
