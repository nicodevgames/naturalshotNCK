@echo off
REM Ejecuta NaturalShot Lite (solo fotos) desde el codigo fuente.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Primero instala las dependencias: ver README.md
    pause
    exit /b 1
)
set "NATURALSHOT_EDICION=lite"
start "" ".venv\Scripts\pythonw.exe" main.py %*
