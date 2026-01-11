@echo off
REM --- Ouvre PowerShell et lance le script Python ---
powershell -NoExit -Command "python .\export_bsky_bookmarks.py"
pause
exit