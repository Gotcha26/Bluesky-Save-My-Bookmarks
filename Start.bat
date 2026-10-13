@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal enabledelayedexpansion

cls
echo.
echo ============================================================
echo    BSMB - Bsky Save My Bookmarks
echo    Initialisation des prérequis
echo ============================================================
echo.
echo BSMB utilise :
echo    - Python 3.11 ou plus récent  ^(obligatoire^)
echo    - le paquet Python requests   ^(obligatoire, installé dans .venv^)
echo    - ffmpeg et exiftool          ^(facultatifs : métadonnées vidéo et images^)
echo.

:: ============================================================
:: [1/5] PYTHON
:: Le simple test "where python" ne suffit pas : sous Windows neuf, il trouve
:: l'alias du Microsoft Store qui n'est pas un vrai Python. On exécute donc
:: réellement l'interpréteur et on vérifie le code retour.
:: ============================================================
set "PYEXE="
call :detect_python
if defined PYEXE goto :python_ok

echo [1/5] Python introuvable ^(ou alias du Microsoft Store uniquement^).
where winget >nul 2>nul
if not errorlevel 1 (
    echo       Installation de Python 3.13 via winget...
    winget install --id Python.Python.3.13 -e --silent --accept-package-agreements --accept-source-agreements
) else (
    where choco >nul 2>nul
    if not errorlevel 1 (
        echo       winget absent : installation de Python via Chocolatey ^(console administrateur requise^)...
        choco install python -y --no-progress
    ) else (
        echo [ERREUR] Ni winget ni Chocolatey ne sont disponibles.
        echo          Installez Python 3.11+ depuis https://www.python.org/downloads/
        echo          en cochant "Add python.exe to PATH", puis relancez Start.bat.
        pause
        exit /b 1
    )
)

:: Le PATH de cette fenêtre n'est pas mis à jour par l'installation :
:: on cherche Python aux emplacements habituels avant de demander de relancer.
call :detect_python
if not defined PYEXE (
    for %%D in ("%LOCALAPPDATA%\Programs\Python\Python313" "%LOCALAPPDATA%\Programs\Python\Python312" "%ProgramFiles%\Python313" "C:\Python313") do (
        if not defined PYEXE if exist "%%~D\python.exe" set PYEXE="%%~D\python.exe"
    )
)
if not defined PYEXE (
    echo.
    echo [INFO] Python vient d'être installé, mais cette fenêtre ne le voit pas encore.
    echo        Fermez cette fenêtre puis relancez Start.bat.
    pause
    exit /b 1
)

:python_ok
%PYEXE% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 (
    echo [ERREUR] Python trop ancien : BSMB demande Python 3.11 ou plus récent.
    %PYEXE% -c "import sys; print('         Version détectée :', sys.version.split()[0])"
    echo          Installez une version récente : winget install --id Python.Python.3.13
    pause
    exit /b 1
)
%PYEXE% -c "import sys; print('[1/5] OK - Python', sys.version.split()[0], 'détecté')"

:: ============================================================
:: [2/5] ENVIRONNEMENT VIRTUEL .venv
:: ============================================================
if not exist ".venv\Scripts\activate.bat" (
    echo [2/5] Création de l'environnement virtuel .venv ...
    %PYEXE% -m venv .venv
    if errorlevel 1 (
        echo [ERREUR] Impossible de créer l'environnement virtuel .venv.
        pause
        exit /b 1
    )
    echo [2/5] OK - environnement virtuel créé
) else (
    echo [2/5] OK - environnement virtuel .venv présent
)
call ".venv\Scripts\activate.bat"

:: ============================================================
:: [3/5] DÉPENDANCES PYTHON
:: ============================================================
echo [3/5] Installation des dépendances Python ^(requirements.txt^)...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo [ERREUR] Échec de l'installation des dépendances Python.
    echo          Vérifiez votre connexion Internet puis relancez Start.bat.
    pause
    exit /b 1
)
echo [3/5] OK - dépendances Python installées

:: ============================================================
:: [4/5] FFMPEG  [5/5] EXIFTOOL  ^(facultatifs : un échec n'est pas bloquant^)
:: ============================================================
set "NEED_RESTART=0"
call :ensure_tool ffmpeg Gyan.FFmpeg ffmpeg "[4/5]"
call :ensure_tool exiftool OliverBetz.ExifTool exiftool "[5/5]"

echo.
echo ============================================================
echo    Prérequis vérifiés
echo ============================================================
if "%NEED_RESTART%"=="1" (
    echo.
    echo [INFO] ffmpeg ou exiftool vient d'être installé : il ne sera visible
    echo        qu'après avoir fermé puis relancé Start.bat.
    echo        BSMB peut démarrer sans, mais sans ces métadonnées pour l'instant.
)
echo.
timeout /t 2 >nul

cls
python bsmb.py

timeout /t 2 >nul
endlocal
exit /b 0


:: ============================================================
:: SOUS-ROUTINES
:: ============================================================

:detect_python
:: Positionne PYEXE sur un interpréteur Python qui fonctionne réellement.
set "PYEXE="
python -c "import sys; print(sys.version)" >nul 2>nul
if not errorlevel 1 (
    set "PYEXE=python"
    exit /b 0
)
py -3 -c "import sys; print(sys.version)" >nul 2>nul
if not errorlevel 1 (
    set "PYEXE=py -3"
    exit /b 0
)
exit /b 0

:ensure_tool
:: %1 = commande, %2 = identifiant winget, %3 = paquet Chocolatey, %4 = étiquette d'étape
where %~1 >nul 2>nul
if not errorlevel 1 (
    echo %~4 OK - %~1 détecté
    exit /b 0
)
echo %~4 %~1 absent : installation en cours...
where winget >nul 2>nul
if not errorlevel 1 (
    winget install --id %~2 -e --silent --accept-package-agreements --accept-source-agreements
    if not errorlevel 1 (
        echo %~4 OK - %~1 installé via winget
        set "NEED_RESTART=1"
        exit /b 0
    )
    echo %~4 [AVERTISSEMENT] Échec de winget pour %~1.
)
where choco >nul 2>nul
if not errorlevel 1 (
    choco install %~3 -y --no-progress
    if not errorlevel 1 (
        echo %~4 OK - %~1 installé via Chocolatey
        set "NEED_RESTART=1"
        exit /b 0
    )
    echo %~4 [AVERTISSEMENT] Échec de Chocolatey pour %~1 ^(console administrateur requise^).
)
echo %~4 [AVERTISSEMENT] %~1 n'a pas pu être installé automatiquement.
echo       BSMB fonctionnera sans lui ^(fonctions de métadonnées désactivées^).
echo       Installation manuelle : winget install %~2
exit /b 0
