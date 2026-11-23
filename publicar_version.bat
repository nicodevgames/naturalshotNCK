@echo off
REM Prepara una version nueva de NaturalShot PRO (pruebas, .exe, zip y version.json en publicar\vX.Y.Z).
REM Uso:  publicar_version.bat 1.1.0 "Novedad 1" "Novedad 2"   [--subir para subirla a GitHub]
REM Sin argumentos, pregunta la version y las novedades. Ver README: "Actualizaciones automaticas".
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" (
    echo Falta el entorno .venv: ver README.md
    exit /b 1
)
".venv\Scripts\python.exe" herramientas\publicar.py %*
set CODIGO=%ERRORLEVEL%
if "%~1"=="" pause
exit /b %CODIGO%
