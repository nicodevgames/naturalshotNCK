# -*- mode: python ; coding: utf-8 -*-
# Especificación de PyInstaller para NaturalShot PRO.
# Uso:  pyinstaller --noconfirm --clean NaturalShot.spec

# Módulos de Qt que la app no usa: se excluyen para achicar el ejecutable.
# QtMultimedia sí va (el sonido de la vista previa del video, con QAudioSink), y con él
# QtNetwork, que PySide6.QtMultimedia importa al cargarse.
EXCLUIR = [
    "tkinter", "matplotlib", "scipy", "pandas", "IPython", "pytest",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.Qt3DCore",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtSql",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtTest",
    "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtWebSockets", "PySide6.QtWebChannel",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("assets/icono.ico", "assets"), ("assets/logo.png", "assets"), ("assets/tutorial.pdf", "assets"), ("assets/iconos", "assets/iconos")],
    hiddenimports=["celular_natural.ui.editor_video", "celular_natural.ui.linea_tiempo",
                   "celular_natural.motor.video", "celular_natural.motor.audio",
                   "celular_natural.ui.forma_onda", "celular_natural.ui.reproductor_audio",
                   "celular_natural.ui.panel_sonido", "celular_natural.ui.panel_mejora",
                   "celular_natural.motor.mejora_video",
                   # Modo Audio (se importa recién al entrar)
                   "celular_natural.ui.modo_audio", "celular_natural.ui.paneles_audio",
                   "celular_natural.ui.pistas_audio", "celular_natural.motor.proyecto_audio",
                   "celular_natural.motor.ambientes", "celular_natural.motor.voz_natural",
                   "PySide6.QtMultimedia", "av",
                   # Tutorial adentro de la app (visor de PDF de Qt, paquete PySide6_Pdf)
                   "celular_natural.ui.tutorial", "PySide6.QtPdf", "PySide6.QtPdfWidgets"],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUIR,
    noarchive=False,
)
# Binarios grandes innecesarios: FFmpeg de OpenCV (video) y OpenGL por software de Qt.
SIN_USO = ("opencv_videoio_ffmpeg", "opengl32sw")
# QtMultimedia: para QAudioSink alcanza con el plugin de Windows (Media Foundation y WASAPI). El de
# FFmpeg y el FFmpeg propio de PySide6 (unos 20 MB) no hacen falta: los videos los lee PyAV, que trae
# el suyo (en av.libs, con otros nombres).
FFMPEG_DE_QT = ("ffmpegmediaplugin", "avcodec-", "avformat-", "avutil-", "swresample-", "swscale-")


def _sin_uso(destino):
    nombre = destino.replace("/", "\\").lower()
    if any(n in nombre for n in SIN_USO):
        return True
    return nombre.startswith("pyside6\\") and any(n in nombre.rsplit("\\", 1)[-1] for n in FFMPEG_DE_QT)


a.binaries = [b for b in a.binaries if not _sin_uso(b[0])]

pyz = PYZ(a.pure)

# NS-102.4: la versión del .exe (Propiedades > Detalles en Windows) sale de la fuente única,
# celular_natural/__init__.py, la misma que muestra la app y lee el actualizador.
import pathlib
import re
import sys

VERSION = re.search(r'__version__ = "([^"]+)"',
                    pathlib.Path("celular_natural/__init__.py").read_text(encoding="utf-8")).group(1)
_PARTES = tuple(int(x) for x in VERSION.split(".")) + (0,)
_ARCHIVO_VERSION = pathlib.Path("build") / "version_naturalshot.txt"
_ARCHIVO_VERSION.parent.mkdir(parents=True, exist_ok=True)
_ARCHIVO_VERSION.write_text(
    f"VSVersionInfo(ffi=FixedFileInfo(filevers={_PARTES}, prodvers={_PARTES}, mask=0x3f, flags=0x0, "
    f"OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)), kids=[StringFileInfo([StringTable('040a04b0', ["
    f"StringStruct('CompanyName', 'NaturalShot'), StringStruct('FileDescription', 'NaturalShot PRO'), "
    f"StringStruct('FileVersion', '{VERSION}'), StringStruct('InternalName', 'NaturalShot'), "
    f"StringStruct('OriginalFilename', 'NaturalShot.exe'), StringStruct('ProductName', 'NaturalShot PRO'), "
    f"StringStruct('ProductVersion', '{VERSION}')])]), VarFileInfo([VarStruct('Translation', [1034, 1200])])])",
    encoding="utf-8")

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NaturalShot",
    icon="assets/icono.ico",
    console=False,  # aplicación de ventana, sin consola
    upx=False,
    # La información de versión es un recurso de Windows; en Mac la lleva el Info.plist (BUNDLE).
    version=str(_ARCHIVO_VERSION) if sys.platform == "win32" else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="NaturalShot",
    upx=False,
)

# Mac: NaturalShot.app (dist/NaturalShot.app), que .github/workflows/compilar.yml mete en un .dmg.
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="NaturalShot.app",
        icon="assets/logo.png",  # PyInstaller lo convierte a .icns (con Pillow)
        bundle_identifier="com.naturalshot.pro",
        info_plist={
            "CFBundleName": "NaturalShot PRO",
            "CFBundleDisplayName": "NaturalShot PRO",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
