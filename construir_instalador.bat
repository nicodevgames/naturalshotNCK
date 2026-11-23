@echo off
REM NS-102.1: arma dist\instalador\NaturalShot-Setup-X.Y.Z.exe con Inno Setup 6.
REM Antes construye el .exe (construir_exe.bat). La version sale de celular_natural\__init__.py.
setlocal
cd /d "%~dp0"
chcp 65001 >nul

call construir_exe.bat || exit /b 1

set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" (
    echo Falta Inno Setup 6: bajalo de https://jrsoftware.org/isdl.php e instalalo.
    exit /b 1
)

for /f "usebackq delims=" %%v in (`".venv\Scripts\python.exe" -c "from celular_natural import __version__; print(__version__)"`) do set VERSION=%%v
if "%VERSION%"=="" (
    echo No se pudo leer la version de celular_natural\__init__.py
    exit /b 1
)

echo Armando el instalador de NaturalShot PRO %VERSION%...
"%ISCC%" /DVersion=%VERSION% instalador\NaturalShot.iss || exit /b 1
echo.
echo Listo: dist\instalador\NaturalShot-Setup-%VERSION%.exe
exit /b 0
