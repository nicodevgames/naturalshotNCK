@echo off
REM Ejecuta la aplicación desde el código fuente.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Primero instala las dependencias: ver README.md
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" main.py %*
