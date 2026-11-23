"""Pruebas de la edición NaturalShot Lite (solo fotos) y de que la PRO no cambió.

* ``celular_natural/edicion.py``: cómo se decide la edición (la variable
  ``NATURALSHOT_EDICION``; en el .exe, ``edicion.txt``; si no, "pro"), el nombre, la
  insignia, la carpeta de datos y los QSettings de cada una.
* La ventana en Lite: el selector tiene Fácil | Editor | Photoshop (sin Video ni Audio); no hay botón de Video, ni
  Ctrl+Shift+V ni Ctrl+Shift+A, ni chips de exportación; un video o un audio que se
  suelta o se abre no cambia de modo, avisa "NaturalShot Lite es solo para fotos" y no
  arma ningún editor; el diálogo de Abrir ofrece solo imágenes; el título, la
  insignia y la pantalla de carga dicen Lite; las actualizaciones están apagadas.
* El camino de fotos de la Lite no importa PyAV, QtMultimedia ni los editores de video
  o audio (en un proceso aparte, con ``sys.modules`` limpio).
* En PRO (sin la variable), todo como siempre.

Usan la ventana real sin pantalla, un .ini propio (``NATURALSHOT_CONFIG``) y un APPDATA
temporal: no leen ni cambian las preferencias del usuario. La edición se cambia con
``mock.patch.dict(os.environ)``: las funciones de ``edicion`` vuelven a mirar la variable
cada vez, así que no hace falta recargar nada.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import warnings
from pathlib import Path
from unittest import mock

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")  # si esta prueba crea la aplicación

VARIABLE = "NATURALSHOT_EDICION"


def foto(ruta: Path, semilla: int = 1, w: int = 320, h: int = 240) -> Path:
    """Una foto de prueba: degradado con ruido."""
    from PIL import Image
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.dstack([80 + 120 * xx / w, 140 - 60 * yy / h, 90 + 80 * yy / h]) + rng.normal(0, 6, (h, w, 3))
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(ruta)
    return ruta


def soltar(widget, rutas) -> bool:
    """Arrastra y suelta archivos sobre ``widget`` (como desde el Explorador). Devuelve si
    el arrastre fue aceptado al entrar."""
    from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent
    from PySide6.QtWidgets import QApplication
    datos = QMimeData()
    datos.setUrls([QUrl.fromLocalFile(str(r)) for r in rutas])
    centro = widget.rect().center()
    with warnings.catch_warnings():  # PySide marca este constructor (el único de Qt 6) como obsoleto
        warnings.simplefilter("ignore", DeprecationWarning)
        entrar = QDragEnterEvent(centro, Qt.CopyAction, datos, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(widget, entrar)
    aceptado = entrar.isAccepted()
    QApplication.sendEvent(widget, QDropEvent(QPointF(centro), Qt.CopyAction, datos, Qt.LeftButton, Qt.NoModifier))
    return aceptado


# ====================================================================== edicion.py (sin Qt)
class PruebasEdicion(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="naturalshot_edicion_"))
        self._entorno = mock.patch.dict(os.environ, {"APPDATA": str(self.dir / "appdata")})
        self._entorno.start()
        os.environ.pop(VARIABLE, None)

    def tearDown(self):
        self._entorno.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_por_defecto_es_pro(self):
        from celular_natural import edicion
        self.assertEqual(edicion.edicion_actual(), "pro")
        self.assertFalse(edicion.es_lite())
        self.assertEqual(edicion.nombre_app(), "NaturalShot PRO")
        self.assertEqual(edicion.insignia(), "PRO")
        self.assertEqual(edicion.carpeta_datos(), self.dir / "appdata" / "NaturalShot PRO")
        self.assertEqual(edicion.organizacion_qsettings(), ("NaturalShot", "NaturalShot PRO"))
        self.assertIn(edicion.EDICION, ("pro", "lite"))

    def test_la_variable_elige_lite(self):
        from celular_natural import edicion
        for valor in ("lite", "LITE", " Lite \n"):
            with mock.patch.dict(os.environ, {VARIABLE: valor}):
                self.assertTrue(edicion.es_lite(), valor)
                self.assertEqual(edicion.nombre_app(), "NaturalShot Lite")
                self.assertEqual(edicion.insignia(), "LITE")
                self.assertEqual(edicion.carpeta_datos().name, "NaturalShot Lite")
                self.assertEqual(edicion.carpeta_datos(), self.dir / "appdata" / "NaturalShot Lite")
                self.assertEqual(edicion.organizacion_qsettings(), ("NaturalShot", "NaturalShot Lite"))
        with mock.patch.dict(os.environ, {VARIABLE: "pro"}):
            self.assertFalse(edicion.es_lite())
        with mock.patch.dict(os.environ, {VARIABLE: "otra cosa"}):  # un valor raro no cuenta
            self.assertEqual(edicion.edicion_actual(), "pro")

    def test_en_el_exe_manda_edicion_txt(self):
        from celular_natural import edicion
        exe = self.dir / "app" / "NaturalShot Lite.exe"
        interna = self.dir / "app" / "_internal"
        interna.mkdir(parents=True)
        exe.write_bytes(b"MZ")
        # Desde el código, un edicion.txt suelto no cuenta (solo la variable).
        (interna / "edicion.txt").write_text("lite\n", encoding="utf-8")
        self.assertFalse(edicion.es_lite())
        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "executable", str(exe)), \
                mock.patch.object(sys, "_MEIPASS", str(interna), create=True):
            self.assertTrue(edicion.es_lite())  # el que pone el .spec, en _internal
            (interna / "edicion.txt").unlink()
            self.assertFalse(edicion.es_lite())
            (exe.parent / "edicion.txt").write_text("\ufeffLite", encoding="utf-8")  # junto al .exe, con BOM
            self.assertTrue(edicion.es_lite())
            with mock.patch.dict(os.environ, {VARIABLE: "pro"}):  # la variable gana
                self.assertFalse(edicion.es_lite())
            (exe.parent / "edicion.txt").write_text("cualquier cosa", encoding="utf-8")
            self.assertFalse(edicion.es_lite())

    def test_recursos_de_cada_edicion(self):
        """En la Lite, el ícono, el logo y el tutorial salen de su versión Lite si existe; si no, los de siempre."""
        from celular_natural import edicion
        from celular_natural.ui import tutorial
        interna = self.dir / "_internal"
        (interna / "assets").mkdir(parents=True)
        for nombre in ("icono.ico", "logo.png", "tutorial.pdf", "icono_lite.ico", "logo_lite.png"):
            (interna / "assets" / nombre).write_bytes(b"x")
        with mock.patch.object(sys, "_MEIPASS", str(interna), create=True):
            # PRO: los de siempre.
            for relativa in ("assets/icono.ico", "assets/logo.png", "assets/tutorial.pdf"):
                self.assertEqual(edicion.ruta_recurso(relativa), interna / relativa)
            self.assertEqual(tutorial.ruta_tutorial(), interna / "assets" / "tutorial.pdf")
            self.assertEqual(edicion.ruta_icono(), interna / "assets" / "icono.ico")
            self.assertEqual(edicion.ruta_logo(), interna / "assets" / "logo.png")
            with mock.patch.dict(os.environ, {VARIABLE: "lite"}):
                self.assertEqual(edicion.ruta_recurso("assets/icono.ico"), interna / "assets" / "icono_lite.ico")
                self.assertEqual(edicion.ruta_recurso("assets/logo.png"), interna / "assets" / "logo_lite.png")
                self.assertEqual(edicion.ruta_icono(), interna / "assets" / "icono_lite.ico")
                self.assertEqual(edicion.ruta_logo(), interna / "assets" / "logo_lite.png")
                (interna / "assets" / "logo_lite.png").unlink()  # si falta el Lite, el de siempre
                self.assertEqual(edicion.ruta_logo(), interna / "assets" / "logo.png")
                # Sin tutorial_lite.pdf, el de siempre; con él, el suyo.
                self.assertEqual(tutorial.ruta_tutorial(), interna / "assets" / "tutorial.pdf")
                (interna / "assets" / "tutorial_lite.pdf").write_bytes(b"x")
                self.assertEqual(tutorial.ruta_tutorial(), interna / "assets" / "tutorial_lite.pdf")
                # Lo demás no cambia.
                self.assertEqual(edicion.ruta_recurso("assets/iconos/x.svg"), interna / "assets" / "iconos" / "x.svg")
        # Desde el código, con los recursos del proyecto (icono_lite.ico y logo_lite.png ya están).
        import main
        with mock.patch.dict(os.environ, {VARIABLE: "lite"}):
            self.assertEqual(main.ruta_recurso("assets/icono.ico"), RAIZ / "assets" / "icono_lite.ico")
            self.assertEqual(main.ruta_recurso("assets/logo.png"), RAIZ / "assets" / "logo_lite.png")
        self.assertEqual(main.ruta_recurso("assets/icono.ico"), RAIZ / "assets" / "icono.ico")
        self.assertEqual(main.ruta_recurso("assets/logo.png"), RAIZ / "assets" / "logo.png")

    def test_carpetas_de_datos_de_cada_edicion(self):
        from celular_natural import sesion
        from celular_natural.ui import presets_usuario
        appdata = self.dir / "appdata"
        # PRO: como siempre.
        self.assertEqual(sesion.carpeta_sesion(), appdata / "NaturalShot PRO" / "sesion")
        self.assertEqual(presets_usuario._archivo(), appdata / "NaturalShot" / "presets.json")
        with mock.patch.dict(os.environ, {VARIABLE: "lite"}):
            self.assertEqual(sesion.carpeta_sesion(), appdata / "NaturalShot Lite" / "sesion")
            self.assertEqual(presets_usuario._archivo(), appdata / "NaturalShot Lite" / "presets.json")

    def test_qsettings_de_cada_edicion(self):
        from celular_natural.ui.modo_facil import VARIABLE_CONFIG, configuracion
        with mock.patch.dict(os.environ):
            os.environ.pop(VARIABLE_CONFIG, None)
            real = configuracion()  # solo se mira, no se escribe nada
            self.assertEqual((real.organizationName(), real.applicationName()), ("NaturalShot", "NaturalShot PRO"))
            os.environ[VARIABLE] = "lite"
            real = configuracion()
            self.assertEqual((real.organizationName(), real.applicationName()), ("NaturalShot", "NaturalShot Lite"))
            # NATURALSHOT_CONFIG sigue mandando (las pruebas no tocan el registro).
            os.environ[VARIABLE_CONFIG] = str(self.dir / "config.ini")
            self.assertEqual(Path(configuracion().fileName()), self.dir / "config.ini")

    def test_ruteo_solo_fotos(self):
        from celular_natural.ui.modo_video import FILTRO_ABRIR_FOTOS, mensaje_solo_fotos
        self.assertNotIn(".mp4", FILTRO_ABRIR_FOTOS)
        self.assertNotIn(".mp3", FILTRO_ABRIR_FOTOS)
        self.assertIn("*.jpg", FILTRO_ABRIR_FOTOS)
        texto, detalle = mensaje_solo_fotos(["C:/a/clip.mp4"], ["C:/a/voz.mp3"], [])
        self.assertIn("NaturalShot Lite es solo para fotos", texto)
        self.assertIn("clip.mp4", detalle)
        self.assertIn("voz.mp3", detalle)
        texto, _ = mensaje_solo_fotos(["C:/a/clip.mp4"], [], ["C:/a/foto.jpg"])
        self.assertIn("NaturalShot Lite es solo para fotos", texto)
        self.assertIn("foto", texto)  # la foto sí se abrió
        self.assertEqual(mensaje_solo_fotos([], [], ["C:/a/foto.jpg"]), ("", ""))


# ====================================================================== la ventana
class _BaseVentana(unittest.TestCase):
    LITE = True

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        from celular_natural.ui.estilo import HOJA_ESTILO
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(HOJA_ESTILO)
        cls.dir = Path(tempfile.mkdtemp(prefix="naturalshot_lite_"))
        cls.config = cls.dir / "config.ini"
        cls.foto1 = foto(cls.dir / "playa.png", 1)
        # Para las pruebas de ruteo alcanza con la extensión: nunca se abren.
        cls.video = cls.dir / "clip.mp4"
        cls.video.write_bytes(b"no es un video de verdad")
        cls.audio = cls.dir / "voz.mp3"
        cls.audio.write_bytes(b"no es un audio de verdad")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        from celular_natural.ui.ventana import VentanaPrincipal
        entorno = {"APPDATA": str(self.dir / "appdata"), "NATURALSHOT_CONFIG": str(self.config)}
        self._entorno = mock.patch.dict(os.environ, entorno)
        self._entorno.start()
        if self.LITE:
            os.environ[VARIABLE] = "lite"
        else:
            os.environ.pop(VARIABLE, None)
        if self.config.exists():
            self.config.unlink()  # cada prueba arranca como la primera vez (en Fácil)
        self.v = VentanaPrincipal()
        self.v.resize(1366, 768)
        self.v.show()
        self.v.activateWindow()
        self.pausa(0.05)

    def tearDown(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication, QMessageBox
        try:
            with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
                self.v.close()
            self.v.deleteLater()
            self.app.processEvents()
            # deleteLater() sin un bucle de eventos corriendo no borra nada: se completa el borrado acá.
            QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        finally:
            self._entorno.stop()

    def pausa(self, segundos: float = 0.2) -> None:
        fin = time.monotonic() + segundos
        while time.monotonic() < fin:
            self.app.processEvents()
            time.sleep(0.01)

    def esperar(self, condicion, segundos: float = 30.0) -> None:
        fin = time.monotonic() + segundos
        while time.monotonic() < fin:
            self.app.processEvents()
            if condicion():
                return
            time.sleep(0.01)
        self.fail("no se cumplió la condición a tiempo")

    def atajos(self) -> set:
        return {a.shortcut().toString() for a in self.v.actions()}

    def textos_visibles(self) -> list:
        from PySide6.QtWidgets import QAbstractButton
        return [b.text().strip() for b in self.v.findChildren(QAbstractButton) if b.isVisible()]


class PruebasVentanaLite(_BaseVentana):
    LITE = True

    def test_selector_solo_facil_y_editor(self):
        from celular_natural.ui.modo_facil import EDITOR, FACIL, PHOTOSHOP
        v = self.v
        modos = [b.property("modo") for b in v.grupo_interfaz.buttons()]
        self.assertEqual(modos, [FACIL, EDITOR, PHOTOSHOP])  # Photoshop: las capas (etapa 1)
        self.assertIsNone(v.boton_modo_video)
        self.assertIsNone(v.boton_modo_audio)
        self.assertIsNone(v.boton_video)
        self.assertIsNone(v.chip_video)
        self.assertIsNone(v.chip_audio)
        for modo in (FACIL, EDITOR):
            v.establecer_modo(modo)
            self.pausa(0.05)
            textos = self.textos_visibles()
            self.assertNotIn("Video", textos)
            self.assertNotIn("Audio", textos)

    def test_sin_atajos_de_video_ni_audio(self):
        from PySide6.QtGui import QKeySequence
        from celular_natural.ui.modo_facil import AUDIO, EDITOR, VIDEO
        v = self.v
        atajos = self.atajos()
        self.assertNotIn(QKeySequence("Ctrl+Shift+V").toString(), atajos)
        self.assertNotIn(QKeySequence("Ctrl+Shift+A").toString(), atajos)
        self.assertIn(QKeySequence("Ctrl+E").toString(), atajos)  # Fácil <-> Editor sigue
        v.establecer_modo(EDITOR)
        # Ni por código se llega a Video o Audio.
        v.alternar_video()
        v.alternar_audio()
        v.establecer_modo(VIDEO)
        v.establecer_modo(AUDIO)
        v.abrir_editor_video()
        self.assertEqual(v.modo, EDITOR)
        self.assertIsNone(v.editor_video)
        self.assertIsNone(v.editor_audio)

    def test_soltar_video_o_audio_avisa_y_no_cambia_de_modo(self):
        from celular_natural.ui.modo_facil import EDITOR, FACIL
        v = self.v
        for modo in (FACIL, EDITOR):
            v.establecer_modo(modo)
            for ruta in (self.video, self.audio):
                v.aviso.ocultar()
                for destino in (v, v.vista):
                    soltar(destino, [ruta])
                    self.pausa(0.05)
                    self.assertEqual(v.modo, modo)
                    self.assertTrue(v.aviso.isVisible())
                    self.assertIn("NaturalShot Lite es solo para fotos", v.aviso.texto.text())
                    self.assertIsNone(v.editor_video)
                    self.assertIsNone(v.editor_audio)
        # Abrir con... (main.py) o abrir_archivo: lo mismo.
        v.abrir_rutas([str(self.video), str(self.audio)])
        v.abrir_archivo(str(self.video))
        self.assertIsNone(v.editor_video)
        self.assertIsNone(v.editor_audio)
        self.assertEqual(v._fotos, [])

    def test_fotos_y_video_juntos_la_foto_entra(self):
        v = self.v
        soltar(v, [self.video, self.foto1])
        self.esperar(lambda: v._imagen is not None and v._imagen.ruta.name == "playa.png")
        self.assertEqual(len(v._fotos), 1)
        self.assertIn("NaturalShot Lite es solo para fotos", v.aviso.texto.text())
        self.assertIsNone(v.editor_video)

    def test_abrir_ofrece_solo_imagenes(self):
        from PySide6.QtWidgets import QFileDialog
        with mock.patch.object(QFileDialog, "getOpenFileNames", return_value=([], "")) as dialogo:
            self.v.elegir_archivo()
        titulo, filtro = dialogo.call_args[0][1], dialogo.call_args[0][3]
        for cosa in ("video", "Video", "audio", "Audio", ".mp4", ".mp3"):
            self.assertNotIn(cosa, titulo + filtro)
        self.assertIn("*.png", filtro)
        self.assertNotIn("video", self.v.boton_abrir.toolTip().lower())

    def test_nombre_insignia_y_carga_dicen_lite(self):
        from PySide6.QtWidgets import QLabel
        from celular_natural.ui.carga import PantallaCarga
        v = self.v
        self.assertEqual(v.windowTitle(), "NaturalShot Lite")
        insignias = [e.text() for e in v.findChildren(QLabel) if e.objectName().startswith("insignia")]
        self.assertEqual(insignias, ["LITE"])
        carga = PantallaCarga(None, "1.0.0")
        try:
            self.assertEqual(carga.windowTitle(), "NaturalShot Lite")
            self.assertEqual(carga.insignia, "LITE")
        finally:
            carga.deleteLater()
        self.assertIn("NaturalShot Lite", v.actualizaciones.boton_version.toolTip())
        self.assertEqual(v.ruta_logo, RAIZ / "assets" / "logo_lite.png")  # el logo de la cabecera
        from celular_natural.ui.tutorial import DialogoTutorial
        dialogo = DialogoTutorial()
        try:
            self.assertEqual(dialogo.windowTitle(), "Tutorial · NaturalShot Lite")
        finally:
            dialogo.deleteLater()
        v.abrir_rutas([str(self.foto1)])
        self.esperar(lambda: v._imagen is not None)
        self.assertEqual(v.windowTitle(), "playa.png — NaturalShot Lite")

    def test_actualizaciones_apagadas(self):
        from PySide6.QtWidgets import QMenu
        from celular_natural import actualizador as act
        c = self.v.actualizaciones
        self.assertFalse(c.activas)
        with mock.patch.object(act, "buscar_actualizacion") as buscar, \
                mock.patch.object(act, "registrar") as registrar, \
                mock.patch.object(act, "configurado", return_value=True):
            c.al_iniciar()
            c.buscar(manual=True)
            c.conectar()
            self.pausa(0.1)
        buscar.assert_not_called()
        registrar.assert_not_called()  # ni siquiera escribe en la carpeta de la PRO
        self.assertFalse(c.banner.isVisible())
        # El menú de la versión: solo "Acerca de" (nada de GitHub).
        from PySide6.QtCore import QTimer
        textos = []

        def leer_y_cerrar():  # QMenu.exec es de C++ (no se puede reemplazar): se lee el menú abierto y se cierra
            for menu in c.boton_version.findChildren(QMenu, "menuVersion"):
                if menu.isVisible():
                    textos.extend(x.text() for x in menu.actions())
                    menu.close()

        QTimer.singleShot(150, leer_y_cerrar)
        c.mostrar_menu()
        self.assertTrue(any("NaturalShot Lite" in t for t in textos))
        self.assertFalse(any("GitHub" in t or "Buscar" in t or "versiones" in t for t in textos))
        self.assertFalse((self.dir / "appdata" / "NaturalShot PRO").exists())

    def test_la_sesion_va_a_la_carpeta_de_lite(self):
        from celular_natural import sesion
        v = self.v
        v.activar_sesion()
        self.esperar(lambda: v.sesion_restaurada)
        v.abrir_rutas([str(self.foto1)])
        self.esperar(lambda: v._imagen is not None)
        v.guardar_sesion(esperar=True)
        self.assertTrue((self.dir / "appdata" / "NaturalShot Lite" / "sesion" / sesion.ARCHIVO_SESION).is_file())
        self.assertFalse((self.dir / "appdata" / "NaturalShot PRO").exists())
        v.quitar_todas_las_fotos(confirmar=False)


class PruebasVentanaPro(_BaseVentana):
    """Sin la variable: la PRO de siempre."""
    LITE = False

    def test_pro_igual_que_siempre(self):
        from PySide6.QtGui import QKeySequence
        from PySide6.QtWidgets import QLabel
        from celular_natural.ui.modo_facil import AUDIO, EDITOR, FACIL, VIDEO
        v = self.v
        self.assertEqual([b.property("modo") for b in v.grupo_interfaz.buttons()], [FACIL, EDITOR, VIDEO, AUDIO])
        self.assertIsNotNone(v.boton_modo_video)
        self.assertIsNotNone(v.boton_video)
        self.assertIsNotNone(v.chip_video)
        atajos = self.atajos()
        self.assertIn(QKeySequence("Ctrl+Shift+V").toString(), atajos)
        self.assertIn(QKeySequence("Ctrl+Shift+A").toString(), atajos)
        self.assertEqual(v.windowTitle(), "NaturalShot PRO")
        insignias = [e.text() for e in v.findChildren(QLabel) if e.objectName().startswith("insignia")]
        self.assertEqual(insignias, ["PRO"])
        self.assertTrue(v.actualizaciones.activas)
        self.assertIn("Tocá para buscar actualizaciones", v.actualizaciones.boton_version.toolTip())
        self.assertIn("Video", v.boton_abrir.toolTip())
        self.assertEqual(v.ruta_logo, RAIZ / "assets" / "logo.png")


# ====================================================================== sin PyAV ni video/audio
_SONDA = r"""
import os, sys, time
sys.path.insert(0, sys.argv[1])
from PySide6.QtWidgets import QApplication
app = QApplication([])
from celular_natural.ui.ventana import VentanaPrincipal
v = VentanaPrincipal()
v.resize(1366, 768)
v.show()
v.activar_sesion()
for _ in range(50):
    app.processEvents(); time.sleep(0.01)
from celular_natural.ui.modo_facil import AUDIO, EDITOR, FACIL, VIDEO
v.establecer_modo(EDITOR); v.establecer_modo(VIDEO); v.establecer_modo(AUDIO); v.alternar_video()
v.abrir_rutas([sys.argv[2], sys.argv[3], sys.argv[4]])
fin = time.time() + 20
while time.time() < fin and v._imagen is None:
    app.processEvents(); time.sleep(0.01)
v.establecer_modo(FACIL)
for _ in range(30):
    app.processEvents(); time.sleep(0.01)
ok =v._imagen is not None
v.close()
prohibidos = ["av", "PySide6.QtMultimedia", "celular_natural.motor.video", "celular_natural.motor.ambientes",
              "celular_natural.motor.mejora_video", "celular_natural.ui.editor_video", "celular_natural.ui.modo_audio",
              "celular_natural.ui.paneles_audio", "celular_natural.ui.pistas_audio",
              "celular_natural.ui.reproductor_audio", "celular_natural.ui.linea_tiempo",
              "celular_natural.ui.forma_onda", "celular_natural.ui.panel_sonido", "celular_natural.ui.panel_mejora"]
print("FOTO", ok)
print("CARGADOS", ",".join(m for m in prohibidos if m in sys.modules))
"""


class PruebasSinVideoNiAudio(unittest.TestCase):
    def test_el_camino_de_fotos_de_la_lite_no_importa_video_ni_audio(self):
        """En un proceso aparte (``sys.modules`` limpio): ventana, sesión, cambios de modo, soltar
        un video, un audio y una foto. No se carga PyAV, QtMultimedia ni nada de video o audio."""
        dir_ = Path(tempfile.mkdtemp(prefix="naturalshot_lite_sonda_"))
        try:
            sonda = dir_ / "sonda.py"
            sonda.write_text(_SONDA, encoding="utf-8")
            imagen = foto(dir_ / "foto.png")
            video, audio = dir_ / "clip.mp4", dir_ / "voz.mp3"
            video.write_bytes(b"x")
            audio.write_bytes(b"x")
            entorno = dict(os.environ, QT_QPA_PLATFORM="offscreen", APPDATA=str(dir_ / "appdata"),
                           NATURALSHOT_CONFIG=str(dir_ / "config.ini"), **{VARIABLE: "lite"})
            r = subprocess.run([sys.executable, str(sonda), str(RAIZ), str(video), str(audio), str(imagen)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", env=entorno,
                               timeout=180, cwd=str(dir_))
            self.assertEqual(r.returncode, 0, r.stderr[-3000:])
            lineas = dict(l.split(" ", 1) for l in r.stdout.splitlines() if l.startswith(("FOTO", "CARGADOS")))
            self.assertEqual(lineas.get("FOTO"), "True", r.stdout + r.stderr[-2000:])
            self.assertEqual(lineas.get("CARGADOS", "?").strip(), "", r.stdout)
        finally:
            shutil.rmtree(dir_, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
