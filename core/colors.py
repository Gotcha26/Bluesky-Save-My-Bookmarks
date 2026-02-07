#!/usr/bin/env python3
"""
Classe Colors - Gestion des couleurs ANSI cross-platform pour BSMB
Pattern menu-generator : classe centralisée, détection auto du terminal
"""
import os
import sys


class Colors:
    """Gestion centralisée des couleurs ANSI avec détection automatique du terminal."""

    def __init__(self, force_color=None):
        self._enabled = self._detect_color_support(force_color)
        self._setup_codes()

    def _detect_color_support(self, force_color):
        if force_color is not None:
            return force_color

        # Variables d'environnement
        if os.environ.get("NO_COLOR"):
            return False
        if os.environ.get("FORCE_COLOR"):
            return True

        # Windows Terminal, ConEmu
        if os.environ.get("WT_SESSION"):
            return True
        if os.environ.get("ConEmuANSI") == "ON":
            return True

        # Windows 10+ : activer le mode ANSI via kernel32
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                # STD_OUTPUT_HANDLE = -11
                handle = kernel32.GetStdHandle(-11)
                mode = ctypes.c_ulong()
                kernel32.GetConsoleMode(handle, ctypes.byref(mode))
                # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
                return True
            except Exception:
                return False

        # Unix : vérifier isatty
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

    def _setup_codes(self):
        if self._enabled:
            # Couleurs de base
            self.RED = "\033[31m"
            self.GREEN = "\033[32m"
            self.YELLOW = "\033[33m"
            self.BLUE = "\033[34m"
            self.MAGENTA = "\033[35m"
            self.CYAN = "\033[36m"
            self.WHITE = "\033[37m"

            # Couleurs claires
            self.LIGHT_RED = "\033[91m"
            self.LIGHT_GREEN = "\033[92m"
            self.LIGHT_YELLOW = "\033[93m"
            self.LIGHT_BLUE = "\033[94m"
            self.LIGHT_MAGENTA = "\033[95m"
            self.LIGHT_CYAN = "\033[96m"

            # Styles
            self.BOLD = "\033[1m"
            self.DIM = "\033[2m"
            self.UNDERLINE = "\033[4m"
            self.RESET = "\033[0m"
        else:
            # Tout vide si pas de support couleur
            for attr in [
                "RED", "GREEN", "YELLOW", "BLUE", "MAGENTA", "CYAN", "WHITE",
                "LIGHT_RED", "LIGHT_GREEN", "LIGHT_YELLOW", "LIGHT_BLUE",
                "LIGHT_MAGENTA", "LIGHT_CYAN",
                "BOLD", "DIM", "UNDERLINE", "RESET",
            ]:
                setattr(self, attr, "")

        # Alias sémantiques
        self.OK = self.GREEN
        self.SUCCESS = self.GREEN
        self.ERROR = self.RED
        self.WARNING = self.YELLOW
        self.INFO = self.BLUE
        self.VALUE = self.CYAN
        self.KEY = self.WHITE
        self.PROMPT = self.YELLOW
        self.HEADER = self.CYAN + self.BOLD
        self.TITLE = self.WHITE + self.BOLD

    # --- Méthodes de formatage avec préfixe ---

    def success(self, text):
        return f"  {self.GREEN}[OK]{self.RESET} {text}"

    def error(self, text):
        return f"  {self.RED}[ERREUR]{self.RESET} {text}"

    def warning(self, text):
        return f"  {self.YELLOW}[ATTENTION]{self.RESET} {text}"

    def info(self, text):
        return f"  {self.BLUE}[INFO]{self.RESET} {text}"

    # --- Marqueurs isolés ---

    def ok_marker(self):
        return f"{self.GREEN}[OK]{self.RESET}"

    def error_marker(self):
        return f"{self.RED}[ERREUR]{self.RESET}"

    def warn_marker(self):
        return f"{self.YELLOW}[ATTENTION]{self.RESET}"

    # --- Formatage inline ---

    def header(self, text):
        return f"{self.HEADER}{text}{self.RESET}"

    def title(self, text):
        return f"{self.TITLE}{text}{self.RESET}"

    def value(self, text):
        return f"{self.VALUE}{text}{self.RESET}"

    def key(self, text):
        return f"{self.KEY}{text}{self.RESET}"

    def prompt(self, text):
        return f"{self.PROMPT}{text}{self.RESET}"

    # --- Éléments d'interface ---

    def separator(self, char="-", width=60):
        return f"  {self.DIM}{char * width}{self.RESET}"

    def box_header(self, text, width=70):
        border = "=" * width
        padding = width - 4
        centered = text.center(padding)
        return (
            f"\n  {self.HEADER}{border}{self.RESET}\n"
            f"  {self.HEADER}= {centered} ={self.RESET}\n"
            f"  {self.HEADER}{border}{self.RESET}"
        )

    def menu_option(self, number, text):
        return f"  {self.YELLOW}{number}{self.RESET}. {text}"

    def config_line(self, label, val, key_width=25):
        return f"  {self.KEY}{label:<{key_width}}{self.RESET} : {self.VALUE}{val}{self.RESET}"


# Instance globale
c = Colors()
