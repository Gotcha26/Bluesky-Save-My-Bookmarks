#!/usr/bin/env bash
# BSMB - lanceur Linux / macOS
# Crée .venv, installe les dépendances Python, vérifie ffmpeg/exiftool puis lance BSMB.
# Option : --check  -> vérifie l'environnement sans lancer l'application.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

CHECK_ONLY=0
if [ "${1:-}" = "--check" ]; then
    CHECK_ONLY=1
fi

echo
echo "============================================================"
echo "   BSMB - Bsky Save My Bookmarks"
echo "   Initialisation des prérequis"
echo "============================================================"
echo

# --- [1/4] Python 3.11+ ---------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERREUR] python3 est introuvable."
    echo "         Debian/Ubuntu : sudo apt install python3 python3-venv python3-pip"
    echo "         macOS         : brew install python"
    exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo "[ERREUR] Python trop ancien : BSMB demande Python 3.11 ou plus récent."
    python3 -c 'import sys; print("         Version détectée :", sys.version.split()[0])'
    exit 1
fi
python3 -c 'import sys; print("[1/4] OK - Python", sys.version.split()[0], "détecté")'

# --- [2/4] Environnement virtuel ------------------------------
if [ ! -f ".venv/bin/activate" ] && [ ! -f ".venv/Scripts/activate" ]; then
    echo "[2/4] Création de l'environnement virtuel .venv ..."
    if ! python3 -m venv .venv; then
        echo "[ERREUR] Impossible de créer .venv."
        echo "         Debian/Ubuntu : sudo apt install python3-venv"
        exit 1
    fi
    echo "[2/4] OK - environnement virtuel créé"
else
    echo "[2/4] OK - environnement virtuel .venv présent"
fi
# shellcheck disable=SC1091
if [ -f ".venv/bin/activate" ]; then source .venv/bin/activate; else source .venv/Scripts/activate; fi  # Scripts/ : Git Bash sous Windows

# --- [3/4] Dépendances Python ---------------------------------
echo "[3/4] Installation des dépendances Python (requirements.txt)..."
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
echo "[3/4] OK - dépendances Python installées"

# --- [4/4] Outils facultatifs ---------------------------------
missing=()
for tool in ffmpeg exiftool; do
    if command -v "$tool" >/dev/null 2>&1; then
        echo "[4/4] OK - $tool détecté"
    else
        echo "[4/4] [AVERTISSEMENT] $tool absent (facultatif : métadonnées désactivées)"
        missing+=("$tool")
    fi
done
if [ "${#missing[@]}" -gt 0 ]; then
    echo
    echo "      Pour les installer :"
    echo "        Debian/Ubuntu : sudo apt install ffmpeg libimage-exiftool-perl"
    echo "        macOS         : brew install ffmpeg exiftool"
fi

echo
echo "============================================================"
echo "   Prérequis vérifiés"
echo "============================================================"

if [ "$CHECK_ONLY" -eq 1 ]; then
    echo "Mode --check : l'application n'est pas lancée."
    exit 0
fi

exec python bsmb.py
