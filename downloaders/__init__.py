# downloaders/__init__.py
"""
Downloaders : fonctions de téléchargement des médias d'un post Bluesky.

Chaque downloader renvoie une liste de DownloadResult (liste vide = aucun
média trouvé) et lève DownloadError en cas d'erreur technique. Aucun
n'imprime : l'affichage est produit par l'appelant via lignes_console().
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DownloadResult:
    """Un fichier écrit sur le disque par un downloader."""
    filename: str
    path: Path
    media_type: str  # "image", "video" ou "text"
    size: int        # taille en octets
    cid: str | None = None
    skipped: bool = False  # image déjà présente (même cid) : rien n'a été écrit


class DownloadError(Exception):
    """Erreur technique d'un downloader (API, réseau, écriture)."""


_MARQUEURS = {
    "image": "[DL] Téléchargé -> ",
    "video": "[OK] Fichier enregistré : ",
    "text": "[TXT] ",
}


def lignes_console(results):
    """Lignes d'affichage historiques ([DL] / [OK] / [TXT]) pour des résultats."""
    lignes = []
    for r in results:
        if r.skipped:
            lignes.append(f"   [SKIP] {r.cid} déjà présent : {r.filename}")
        else:
            lignes.append(f"   {_MARQUEURS[r.media_type]}{r.filename}")
    return lignes
