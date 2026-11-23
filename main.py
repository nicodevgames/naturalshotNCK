"""Punto de entrada de NaturalShot PRO (y de NaturalShot Lite).

El arranque va por etapas para que se vea algo enseguida:

1. Se crea la ``QApplication`` y se muestra la pantalla de carga (``ui/carga.py``,
   que solo necesita PySide6).
2. NumPy, OpenCV, Pillow y el motor se importan en otro hilo mientras la animación
   sigue; después, en el hilo principal, la interfaz y la ventana.
3. Se recupera la sesión anterior (las fotos de la tira y sus ediciones) y se espera
   a que se vea la foto que estaba abierta (con un máximo de ``ESPERA_FOTOS`` s).
4. La pantalla de carga se desvanece y la ventana aparece maximizada con un fundido
   y una leve subida. Recién ahí se buscan actualizaciones y, si corresponde, se
   muestra el tutorial (cuando la sesión ya terminó de recuperarse).

Con la variable ``NATURALSHOT_REGISTRO_ARRANQUE`` (ruta de un archivo) se anotan los
tiempos de cada etapa, medidos desde que arrancó el proceso.

El mismo punto de entrada arranca **NaturalShot Lite** (solo fotos) cuando la edición es
"lite" (``celular_natural/edicion.py``: la variable ``NATURALSHOT_EDICION``, que pone
``ejecutar_lite.bat``, o el ``edicion.txt`` del .exe de la Lite): otro nombre, su ícono y
su logo, y su propio identificador en la barra de tareas.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ESPERA_FOTOS = 4.0  # s: lo máximo que la pantalla de carga espera a la foto de la sesión
_tiempos: list[tuple[str, float]] = []


def ruta_recurso(relativa: str) -> Path:
    """Ubicación de recursos tanto en desarrollo como dentro del .exe de PyInstaller (en la
    Lite, su ícono y su logo, si están)."""
    from celular_natural.edicion import ruta_recurso as ruta_de_la_edicion
    return ruta_de_la_edicion(relativa)


def _inicio_del_proceso() -> float:
    """``time.time()`` del momento en que Windows creó el proceso (si no se puede, ahora)."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.WinDLL("kernel32")
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
            creado, salida, kernel, usuario = (wintypes.FILETIME() for _ in range(4))
            if kernel32.GetProcessTimes(kernel32.GetCurrentProcess(), ctypes.byref(creado), ctypes.byref(salida),
                                        ctypes.byref(kernel), ctypes.byref(usuario)):
                ticks = (creado.dwHighDateTime << 32) | creado.dwLowDateTime  # 100 ns desde 1601
                return ticks / 1e7 - 11644473600.0
        except Exception:
            pass
    return time.time()


def _traducir_qt(app) -> bool:
    """Los textos propios de Qt en español: los botones de los diálogos ("Sí", "No", "Cancelar")
    y los menús de los campos de texto ("Copiar", "Pegar"). Usa ``qtbase_es.qm`` de PySide6,
    que PyInstaller ya mete en el paquete. Si no está, todo sigue en inglés sin error."""
    import PySide6
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    traductor = QTranslator(app)
    carpetas = (QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath),
                str(Path(PySide6.__file__).resolve().parent / "translations"))
    for carpeta in carpetas:
        if traductor.load(QLocale(QLocale.Language.Spanish), "qtbase", "_", carpeta):
            return app.installTranslator(traductor)
    return False


def _marcar(etapa: str) -> None:
    if os.environ.get("NATURALSHOT_REGISTRO_ARRANQUE"):
        _tiempos.append((etapa, time.time()))


def _escribir_tiempos() -> None:
    ruta = os.environ.get("NATURALSHOT_REGISTRO_ARRANQUE")
    if not ruta or not _tiempos:
        return
    inicio = _inicio_del_proceso()
    try:
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(" | ".join(f"{etapa} {round((t - inicio) * 1000)} ms" for etapa, t in _tiempos) + "\n")
    except OSError:
        pass


def _importar_motor() -> None:
    """Lo pesado que no es interfaz (no crea nada de Qt): se importa en otro hilo
    mientras la animación sigue. Lo de la interfaz se importa después, en el principal."""
    import numpy  # noqa: F401
    import cv2  # noqa: F401
    from PIL import Image  # noqa: F401
    import celular_natural.motor  # noqa: F401
    import celular_natural.sesion  # noqa: F401
    import celular_natural.actualizador  # noqa: F401  (http, ssl y json de las actualizaciones)


def main() -> int:
    _marcar("python")
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtWidgets import QApplication

    from celular_natural import NOMBRE_APP, __version__, edicion
    from celular_natural.ui.carga import PantallaCarga, revelar
    from celular_natural.ui.estilo import HOJA_ESTILO

    lite = edicion.es_lite()
    if sys.platform == "win32":
        try:  # ícono propio en la barra de tareas (la Lite, aparte: no se agrupa con la PRO)
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "CelularNatural.Lite" if lite else "CelularNatural.App")
        except Exception:
            pass

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(edicion.nombre_app() if lite else NOMBRE_APP)  # la PRO, como siempre
    _traducir_qt(app)
    app.setStyle("Fusion")
    app.setStyleSheet(HOJA_ESTILO)
    icono_ruta = edicion.ruta_icono()  # en la Lite, icono_lite.ico
    icono = QIcon(str(icono_ruta)) if icono_ruta.exists() else None
    if icono is not None:
        app.setWindowIcon(icono)

    # 1. La pantalla de carga, antes de cualquier cosa pesada.
    carga = PantallaCarga(edicion.ruta_logo(), __version__)  # en la Lite, logo_lite.png
    carga.etapa("Preparando el motor…", 0.06, hasta=0.5)
    carga.mostrar()
    _marcar("pantalla de carga")

    # 2. Motor en otro hilo; interfaz y ventana en el principal.
    carga.en_segundo_plano(_importar_motor)
    _marcar("motor")
    carga.etapa("Cargando la interfaz…", 0.55, hasta=0.7)
    from celular_natural.ui.ventana import VentanaPrincipal
    _marcar("interfaz")
    carga.etapa("Armando la ventana…", 0.72, hasta=0.82)
    ventana = VentanaPrincipal(icono, al_avanzar=carga.respirar)
    _marcar("ventana")

    # 3. La sesión anterior: la foto que estaba abierta se carga mientras sigue la animación.
    carga.etapa("Abriendo tus fotos…", 0.84, hasta=0.97)
    ventana.activar_sesion()
    archivos = [a for a in sys.argv[1:] if Path(a).is_file()]
    if archivos:
        # "Abrir con…" o arrastrar sobre el .exe: las fotos se suman a la tira recuperada y un
        # video se abre en el modo Video, en la misma ventana (``abrir_rutas`` lleva cada cosa
        # a su modo y avisa). Así la ventana ya aparece en el modo que corresponde.
        ventana.cuando_sesion_lista(lambda: ventana.abrir_rutas(archivos))
    carga.esperar(lambda: ventana.sesion_restaurada, ESPERA_FOTOS)  # termina cuando ya se ve la foto
    _marcar("sesión")
    carga.etapa("¡Listo!", 1.0)
    carga.esperar_minimo()
    carga.esperar(lambda: False, 0.12)  # que se vea la barra llena

    # 4. El pase a la ventana y, cuando ya se ve entera, lo demás.
    def al_mostrar() -> None:
        _marcar("ventana visible")
        _escribir_tiempos()
        # Busca una versión nueva en segundo plano, cuando la ventana ya está a la vista.
        QTimer.singleShot(1500, ventana.actualizaciones.al_iniciar)
        # El tutorial aparece al abrir (hasta que se tilde "No volver a mostrar"), después
        # de que la ventana terminó de aparecer y de recuperar la sesión.
        ventana.cuando_sesion_lista(lambda: QTimer.singleShot(250, ventana.mostrar_tutorial_si_corresponde))

    revelar(ventana, carga, al_mostrar)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
