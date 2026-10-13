#!/usr/bin/env python3
"""
Interactions utilisateur de BSMB : mode (non) interactif, pause et confirmation.

En mode non interactif (entrée standard redirigée ou option --yes), plus aucun
input() n'est émis : pause() ne fait rien et confirm() renvoie la valeur par défaut.
"""

import sys

from core.colors import c
from core.i18n import _

_etat = {"yes": False}


def set_yes(valeur=True):
    """Active (ou désactive) l'option globale --yes."""
    _etat["yes"] = bool(valeur)


def is_interactive():
    """True si on peut interroger l'utilisateur : terminal réel et pas de --yes."""
    if _etat["yes"]:
        return False
    try:
        return bool(sys.stdin and sys.stdin.isatty())
    except (ValueError, OSError):
        return False


def pause(message=None):
    """Attend la touche Entrée ; ne fait rien en mode non interactif."""
    if not is_interactive():
        return
    input(f"\n{c.DIM}  {message or _('Appuyez sur Entrée...')}{c.RESET}")


def confirm(question, default=True):
    """Pose une question oui/non ; renvoie `default` en mode non interactif.

    Une réponse vide donne `default`. Réponses oui : o, oui, y, yes (dans toutes les langues).
    """
    if not is_interactive():
        return default
    suffixe = _("[O/n]") if default else _("[o/N]")
    reponse = input(c.prompt(f"  {question} {suffixe}: ")).strip().lower()
    if not reponse:
        return default
    return reponse in ("o", "oui", "y", "yes")
