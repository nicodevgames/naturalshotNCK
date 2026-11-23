@echo off
REM Genera NaturalShot Lite (solo fotos): dist_lite\NaturalShot Lite\NaturalShot Lite.exe,
REM el zip "NaturalShot Lite - para otra PC.zip" y el acceso directo "NaturalShot Lite.lnk".
REM No toca dist\, build\ ni el zip de la PRO. No instala nada: usa el .venv como esta.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Falta el entorno virtual .venv: ver README.md
    goto :error
)

echo Ejecutando las pruebas de la edicion Lite...
set "QT_QPA_PLATFORM=offscreen"
".venv\Scripts\python.exe" -m unittest tests.test_edicion_lite || goto :error
set "QT_QPA_PLATFORM="

echo Construyendo NaturalShot Lite...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --distpath dist_lite --workpath build_lite "NaturalShot Lite.spec" || goto :error
if not exist "dist_lite\NaturalShot Lite\NaturalShot Lite.exe" goto :error

echo Armando el zip para otra PC...
".venv\Scripts\python.exe" -c "import sys; sys.path.insert(0, '.'); from herramientas.publicar import RAIZ, armar_zip; armar_zip(RAIZ / 'dist_lite' / 'NaturalShot Lite', RAIZ / 'NaturalShot Lite - para otra PC.zip', 'NaturalShot Lite', RAIZ / 'herramientas' / 'LEEME_lite.txt')" || goto :error

echo Creando el acceso directo...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%~dp0NaturalShot Lite.lnk'); $s.TargetPath = '%~dp0dist_lite\NaturalShot Lite\NaturalShot Lite.exe'; $s.WorkingDirectory = '%~dp0dist_lite\NaturalShot Lite'; $s.IconLocation = '%~dp0dist_lite\NaturalShot Lite\NaturalShot Lite.exe,0'; $s.Description = 'NaturalShot Lite: editor de fotos realistas'; $s.Save()" || goto :error

echo.
echo Listo: dist_lite\NaturalShot Lite\NaturalShot Lite.exe
echo Zip: NaturalShot Lite - para otra PC.zip
echo Acceso directo: NaturalShot Lite.lnk
exit /b 0

:error
echo.
echo Hubo un error. Revisa los mensajes anteriores.
exit /b 1
