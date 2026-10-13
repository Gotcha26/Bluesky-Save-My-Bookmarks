"""Chemins de référence de BSMB, indépendants du dossier courant."""

from pathlib import Path

# Racine du dépôt (dossier contenant bsmb.py)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
