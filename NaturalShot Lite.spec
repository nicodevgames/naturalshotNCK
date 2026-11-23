# -*- mode: python ; coding: utf-8 -*-
# Especificación de PyInstaller para NaturalShot Lite (solo fotos). Es una copia de NaturalShot.spec
# (la PRO, que no cambia) sin lo de video ni audio.
# Uso:  construir_lite.bat   (o: pyinstaller --noconfirm --clean --distpath dist_lite --workpath build_lite "NaturalShot Lite.spec")
#
# * Deja un edicion.txt con "lite" en _internal: así el .exe sabe que es la Lite
#   (celular_natural/edicion.py), sin depender de ninguna variable de entorno.
# * Ícono, logo y tutorial propios (assets\icono_lite.ico, logo_lite.png y tutorial_lite.pdf);
#   si el tutorial Lite todavía no está, va el de siempre.
# * Excluye PyAV, QtMultimedia y los módulos de video y audio. La Lite no los importa nunca (lo
#   verifica tests/test_edicion_lite.py). Quedan motor/audio.py, motor/proyecto_audio.py y
#   motor/voz_natural.py: los importa celular_natural/sesion.py (las clases que acepta el archivo
#   de la sesión) y modo_video.py (EXTENSIONES_AUDIO), y ninguno carga PyAV al importarse.
# * QtNetwork queda: Qt6Pdf.dll (el visor del tutorial) depende de Qt6Network.dll.

import os

EXCLUIR = [
    "tkinter", "matplotlib", "scipy", "pandas", "IPython", "pytest",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.Qt3DCore",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtSql",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtTest",
    "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtWebSockets", "PySide6.QtWebChannel",
    # Lo de video y audio (solo la PRO):
    "av", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "celular_natural.ui.editor_video", "celular_natural.ui.modo_audio",
    "celular_natural.ui.paneles_audio", "celular_natural.ui.pistas_audio",
    "celular_natural.ui.linea_tiempo", "celular_natural.ui.forma_onda",
    "celular_natural.ui.panel_sonido", "celular_natural.ui.panel_mejora",
    "celular_natural.ui.reproductor_audio",
    "celular_natural.motor.video", "celular_natural.motor.mejora_video",
    "celular_natural.motor.ambientes",
]

# edicion.txt con "lite": se arma en la carpeta de trabajo de la compilación.
_carpeta_edicion = os.path.join(workpath, "edicion")
os.makedirs(_carpeta_edicion, exist_ok=True)
_edicion_txt = os.path.join(_carpeta_edicion, "edicion.txt")
with open(_edicion_txt, "w", encoding="utf-8") as _f:
    _f.write("lite\n")

_tutorial = "assets/tutorial_lite.pdf" if os.path.isfile(os.path.join(SPECPATH, "assets", "tutorial_lite.pdf")) \
    else "assets/tutorial.pdf"
print(f"NaturalShot Lite: tutorial = {_tutorial}")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("assets/icono_lite.ico", "assets"), ("assets/logo_lite.png", "assets"), (_tutorial, "assets"),
           ("assets/iconos", "assets/iconos"), (_edicion_txt, ".")],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUIR,
    noarchive=False,
)
# Binarios grandes innecesarios: FFmpeg de OpenCV (video) y OpenGL por software de Qt. Y, por las
# dudas, cualquier resto de QtMultimedia o del FFmpeg de PySide6 (la Lite no tiene sonido).
SIN_USO = ("opencv_videoio_ffmpeg", "opengl32sw", "qt6multimedia")
FFMPEG_DE_QT = ("ffmpegmediaplugin", "windowsmediaplugin", "avcodec-", "avformat-", "avutil-", "swresample-",
                "swscale-")


# Plugins de imagen de Qt que tienen que quedar siempre: GIF (la guía rápida con GIFs animados del
# tutorial, con QMovie), JPEG e ICO. Si se agrega un filtro para achicar, estos no se tocan.
MANTENER = ("imageformats\\qgif", "imageformats\\qjpeg", "imageformats\\qico")


def _sin_uso(destino):
    nombre = destino.replace("/", "\\").lower()
    if any(n in nombre for n in MANTENER):
        return False
    if any(n in nombre for n in SIN_USO):
        return True
    if nombre.startswith("av\\") or nombre.startswith("av.libs\\"):
        return True
    return nombre.startswith("pyside6\\") and any(n in nombre.rsplit("\\", 1)[-1] for n in FFMPEG_DE_QT)


a.binaries = [b for b in a.binaries if not _sin_uso(b[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NaturalShot Lite",
    icon="assets/icono_lite.ico",
    console=False,  # aplicación de ventana, sin consola
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="NaturalShot Lite",
    upx=False,
)
