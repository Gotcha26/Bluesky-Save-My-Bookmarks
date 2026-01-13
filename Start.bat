@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal enabledelayedexpansion

cls
echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║          🔖 BSMB - Bsky Save My Bookmarks                  ║
echo ║              Initialisation des prérequis                  ║
echo ╚════════════════════════════════════════════════════════════╝
echo.
echo 📋 BSMB nécessite les outils suivants :
echo    • Python 3.8+
echo    • pip install requests yt-dlp
echo    • ffmpeg (traitement vidéo)
echo    • exiftool (métadonnées EXIF)
echo.
echo ⏳ Vérification et installation automatique en cours...
echo.

:: ============================================================
:: PYTHON
:: ============================================================
where python >nul 2>nul
if errorlevel 1 (
    echo [1/4] ❌ Python non détecté
    echo       📦 Installation automatique...
    
    :: Téléchargement Python installer
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe' -OutFile '%TEMP%\python_installer.exe'"
    
    :: Installation silencieuse
    "%TEMP%\python_installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    
    if errorlevel 1 (
        echo       ⚠️ Échec installation Python
        echo       👉 Installez manuellement depuis https://www.python.org/downloads/
        pause
        exit /b 1
    )
    
    :: Rafraîchir PATH
    call refreshenv 2>nul
    
    echo       ✅ Python installé
) else (
    echo [1/4] ✅ Python détecté
)

:: ============================================================
:: REQUESTS
:: ============================================================
python -c "import requests" 2>nul
if errorlevel 1 (
    echo [2/4] ❌ Package requests manquant
    echo       📦 Installation...
    python -m pip install --user --quiet --disable-pip-version-check requests
    if errorlevel 1 (
        echo       ⚠️ Échec installation requests
        pause
        exit /b 1
    )
    echo       ✅ requests installé
) else (
    echo [2/4] ✅ requests détecté
)

:: ============================================================
:: YT-DLP
:: ============================================================
python -c "import yt_dlp" 2>nul
if errorlevel 1 (
    echo [3/4] ❌ Package yt-dlp manquant
    echo       📦 Installation...
    python -m pip install --user --quiet --disable-pip-version-check yt-dlp
    if errorlevel 1 (
        echo       ⚠️ Échec installation yt-dlp
        pause
        exit /b 1
    )
    echo       ✅ yt-dlp installé
) else (
    echo [3/4] ✅ yt-dlp détecté
    :: Mise à jour silencieuse
    python -m pip install --user --quiet --disable-pip-version-check --upgrade yt-dlp 2>nul
)

:: ============================================================
:: FFMPEG
:: ============================================================
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [4/4] ❌ ffmpeg manquant
    echo       📦 Installation via Chocolatey...
    
    where choco >nul 2>nul
    if errorlevel 1 (
        echo       ⚠️ Chocolatey non installé
        echo       👉 Installation de Chocolatey...
        powershell -NoProfile -ExecutionPolicy Bypass -Command "iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))"
    )
    
    choco install ffmpeg -y --no-progress
    if errorlevel 1 (
        echo       ⚠️ Échec installation ffmpeg
        echo       👉 Installez manuellement depuis https://ffmpeg.org/download.html
        pause
        exit /b 1
    )
    
    :: Rafraîchir PATH
    call refreshenv 2>nul
    
    echo       ✅ ffmpeg installé
) else (
    echo [4/4] ✅ ffmpeg détecté
)

:: ============================================================
:: EXIFTOOL
:: ============================================================
where exiftool >nul 2>nul
if errorlevel 1 (
    echo [5/5] ❌ exiftool manquant
    echo       📦 Installation via Chocolatey...
    
    choco install exiftool -y --no-progress
    if errorlevel 1 (
        echo       ⚠️ Échec installation exiftool
        echo       👉 Installez manuellement depuis https://exiftool.org/
        pause
        exit /b 1
    )
    
    :: Rafraîchir PATH
    call refreshenv 2>nul
    
    echo       ✅ exiftool installé
) else (
    echo [5/5] ✅ exiftool détecté
)

echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║              ✅ Tous les prérequis sont OK                 ║
echo ╚════════════════════════════════════════════════════════════╝
echo.
timeout /t 1 >nul

cls
python bsmb.py

timeout /t 2 >nul