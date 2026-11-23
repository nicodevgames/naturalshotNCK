@echo off
REM Genera dist\NaturalShot\NaturalShot.exe con PyInstaller.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual...
    python -m venv .venv || goto :error
)

echo Instalando dependencias...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error

echo Ejecutando pruebas...
".venv\Scripts\python.exe" -m unittest discover -s tests || goto :error

echo Construyendo el ejecutable...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean NaturalShot.spec || goto :error

echo.
echo Listo: dist\NaturalShot\NaturalShot.exe
echo Para distribuirla, comprimi la carpeta dist\NaturalShot completa.
exit /b 0

:error
echo.
echo Hubo un error. Revisa los mensajes anteriores.
exit /b 1
