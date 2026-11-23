"""Pruebas del modo Video: el editor de video adentro de la ventana principal.

* Una sola ventana con tres modos (Fácil | Editor | Video). Ir a Video y volver
  conserva la foto, la tira y el historial, y el video abierto con sus cortes.
* Abrir o arrastrar un video en Fácil o Editor pasa solo a Video (con un aviso);
  una foto en Video vuelve al último modo de fotos; fotos y videos juntos van cada
  cosa a su lugar.
* El diálogo de Abrir acepta fotos y videos y rutea cada cosa.
* Nunca se crea una ventana aparte para el video: hay un solo editor, adentro.
* Una exportación de video sigue al volver a las fotos (con su progreso junto al
  selector y un aviso al terminar); al cerrar la app con una en curso, se pregunta.
* El modo que se guarda es siempre de fotos; Ctrl+E y Ctrl+Shift+V; el filtro del
  video se copia de las fotos la primera vez.

Usan la ventana real en modo sin pantalla, un .ini propio (``NATURALSHOT_CONFIG``)
y un APPDATA temporal: no leen ni cambian las preferencias del usuario. Para esperar
usan ``time.sleep`` y ``processEvents`` (``QTest.qWait`` no suelta el GIL y frena
los hilos que procesan el video).
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import unittest
import warnings
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")  # si esta prueba crea la aplicación

try:
    import av
except ImportError:  # pragma: no cover
    av = None

if av is not None:
    from test_video import generar_video, leer_codigo, leer_video  # noqa: E402


def foto(ruta: Path, semilla: int, w: int = 480, h: int = 360) -> Path:
    """Una foto de prueba: degradado con ruido y un rectángulo."""
    from PIL import Image
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.dstack([80 + 120 * xx / w, 140 - 60 * yy / h, 90 + 80 * yy / h]) + rng.normal(0, 6, (h, w, 3))
    img[h // 3:h // 2, w // 4:w // 2] = (200, 40 + 30 * semilla, 60)
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


@unittest.skipIf(av is None, "Falta PyAV (pip install av==19.0.1)")
class PruebasModoVideo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        from celular_natural.ui.estilo import HOJA_ESTILO
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(HOJA_ESTILO)
        cls.dir = Path(tempfile.mkdtemp(prefix="naturalshot_modo_video_"))
        cls._entorno = {k: os.environ.get(k) for k in ("APPDATA", "NATURALSHOT_CONFIG")}
        os.environ["APPDATA"] = str(cls.dir / "appdata")  # sin los presets propios del usuario
        cls.config = cls.dir / "config.ini"
        os.environ["NATURALSHOT_CONFIG"] = str(cls.config)  # sin tocar el registro del usuario
        cls.foto1 = foto(cls.dir / "playa.png", 1)
        cls.foto2 = foto(cls.dir / "ciudad.jpg", 2)
        cls.video1 = generar_video(cls.dir / "clip.mp4")
        cls.video2 = generar_video(cls.dir / "otro.mov", segundos=1.0, audio=False)
        cls.video3 = generar_video(cls.dir / "tercero.mkv", segundos=0.5, audio=False)

    @classmethod
    def tearDownClass(cls):
        from celular_natural.motor import video as V
        V.cerrar_lectores()
        for clave, valor in cls._entorno.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        from celular_natural.ui.ventana import VentanaPrincipal
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
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            self.v.close()
        self.v.deleteLater()
        self.app.processEvents()
        # deleteLater() sin un bucle de eventos corriendo no borra nada: se completa el borrado acá.
        # Si no, cada ventana cerrada queda viva hasta el final de la suite (con sus miles de widgets).
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    # ------------------------------------------------------------ ayudas
    def esperar(self, condicion, segundos: float = 60.0) -> None:
        fin = time.monotonic() + segundos
        while time.monotonic() < fin:
            self.app.processEvents()
            if condicion():
                for _ in range(3):
                    self.app.processEvents()
                if condicion():
                    return
            time.sleep(0.01)
        self.fail("no se cumplió la condición a tiempo")

    def pausa(self, segundos: float = 0.2) -> None:
        fin = time.monotonic() + segundos
        while time.monotonic() < fin:
            self.app.processEvents()
            time.sleep(0.01)

    def foto_lista(self, nombre: str):
        v = self.v
        return lambda: (v._imagen is not None and v._imagen.ruta.name == nombre and not v._fuentes_pendientes
                        and v._generacion_completa_mostrada == v._generacion)

    def video_listo(self, ruta: Path):
        def listo():
            e = self.v.editor_video
            return e is not None and e.info is not None and Path(e.ruta) == ruta and e.cuadro_procesado_listo()
        return listo

    def visibles(self, clase, nombre: str) -> list:
        return [w for w in self.v.findChildren(clase, nombre) if w.isVisible()]

    # ------------------------------------------------------------ pruebas
    def test_cambiar_a_video_y_volver_conserva_foto_tira_y_video(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QFrame, QLabel
        from celular_natural.ui.modo_facil import EDITOR, FACIL, VIDEO
        v = self.v
        v.establecer_modo(EDITOR)
        v.abrir_rutas([str(self.foto1), str(self.foto2)])
        self.esperar(self.foto_lista("playa.png"))
        v.panel_ajustes.combo_preset.setCurrentText("Noche urbana")
        v.girar(1)
        self.esperar(self.foto_lista("playa.png"))
        v._timer_historial.stop()
        v._registrar_historial()
        estado, historial, pos = v._estado_completo(), list(v._historial), v._pos_historial
        fotos, actual = [f.ruta for f in v._fotos], v._actual
        vista = v._resultado_completo[1].copy()
        selector = self.visibles(QFrame, "selectorModo")[0]
        lugar_selector = selector.mapTo(v, QPoint(0, 0))
        lugar_marca = self.visibles(QLabel, "tituloApp")[0].mapTo(v, QPoint(0, 0))

        # A Video con el selector: el editor ocupa el lugar de las columnas de fotos.
        v.boton_modo_video.click()
        self.assertEqual(v.modo, VIDEO)
        editor = v.editor_video
        self.assertTrue(editor.isVisible() and editor.lateral.isVisible())
        self.assertFalse(v._pagina_fotos.isVisible() or v._lateral_fotos.isVisible())
        self.assertFalse(v.tira.isVisible())
        # Marca y selector: uno solo de cada uno, a la vista y en el mismo lugar.
        self.assertEqual(len(self.visibles(QFrame, "selectorModo")), 1)
        self.assertEqual(len(self.visibles(QLabel, "tituloApp")), 1)
        self.assertEqual(selector.mapTo(v, QPoint(0, 0)), lugar_selector)
        self.assertEqual(self.visibles(QLabel, "tituloApp")[0].mapTo(v, QPoint(0, 0)), lugar_marca)
        self.assertTrue(v.boton_modo_video.isChecked())

        # Un video con cortes.
        v.abrir_rutas([str(self.video1)])
        self.esperar(self.video_listo(self.video1))
        editor.ir_a(1.0)
        editor.cortar()
        editor.ir_a(2.0)
        editor.cortar()
        editor.linea.seleccionar(1)
        editor.borrar_tramo()
        edicion, ruta = editor.edicion, editor.ruta
        self.assertEqual(edicion.tramos_conservados(), [(0.0, 1.0), (2.0, 3.0)])
        self.assertIn("clip.mp4", v.windowTitle())

        # De vuelta a las fotos: todo como estaba.
        v.establecer_modo(EDITOR)
        self.esperar(self.foto_lista("playa.png"))
        self.assertEqual(v.modo, EDITOR)
        self.assertTrue(v._pagina_fotos.isVisible() and v.panel_derecho.isVisible())
        self.assertTrue(editor.isHidden())
        self.assertEqual(v._estado_completo(), estado)
        self.assertEqual(v._historial, historial)
        self.assertEqual(v._pos_historial, pos)
        self.assertEqual([f.ruta for f in v._fotos], fotos)
        self.assertEqual(v._actual, actual)
        self.assertTrue(v.tira.isVisible())
        self.assertEqual(v.tira.lista.count(), 2)
        self.assertTrue(np.array_equal(v._resultado_completo[1], vista))
        self.assertIn("playa.png", v.windowTitle())
        self.assertEqual(selector.mapTo(v, QPoint(0, 0)), lugar_selector)
        # El video sigue abierto (el botón Video lo indica con un punto) y con sus cortes.
        self.assertTrue(v.boton_modo_video.punto)
        self.assertIn("clip.mp4", v.boton_modo_video.toolTip())
        self.assertEqual((editor.ruta, editor.edicion), (ruta, edicion))

        # Fácil -> Video -> Fácil, con el botón de la barra de fotos y Ctrl+E.
        v.establecer_modo(FACIL)
        v.boton_video.click()
        self.assertEqual(v.modo, VIDEO)
        self.assertIs(v.editor_video, editor)
        self.assertEqual((editor.ruta, editor.edicion), (ruta, edicion))
        self.assertFalse(v.boton_modo_video.punto)
        v.alternar_modo()  # Ctrl+E desde Video: al último modo de fotos
        self.assertEqual(v.modo, FACIL)
        self.assertEqual(v._estado_completo(), estado)

    def test_abrir_un_video_en_facil_pasa_a_video(self):
        from celular_natural.ui.modo_facil import FACIL, VIDEO, modo_guardado
        v = self.v
        self.assertEqual(v.modo, FACIL)
        self.assertIsNone(v.editor_video)  # el editor (y PyAV) recién se arma al entrar a Video
        v.panel_ajustes.combo_preset.setCurrentText("Noche urbana")
        v.abrir_archivo(str(self.video1))
        self.assertEqual(v.modo, VIDEO)
        editor = v.editor_video
        self.assertTrue(editor.isVisible())
        # Aviso claro, sobre la vista del video.
        self.assertTrue(v.aviso.mostrado)
        self.assertIn("Esto es un video: lo abrimos en el modo Video", v.aviso.texto.text())
        self.assertIs(v.aviso.parentWidget(), editor.vista)
        self.assertIn("clip.mp4", v.aviso.toolTip())
        self.esperar(self.video_listo(self.video1))
        self.assertTrue(v.aviso.isVisible())
        # La primera vez, el video usa el filtro de las fotos.
        self.assertEqual(editor.panel_ajustes.estado()["preset"], "Noche urbana")
        self.assertEqual(editor.panel_ajustes.pila(), v.panel_ajustes.pila())
        self.assertIn("clip.mp4", v.windowTitle())
        self.assertEqual(modo_guardado(), FACIL)  # Video nunca se guarda como modo
        # Un video arrastrado sobre la vista de fotos, en Editor, también pasa a Video.
        v.establecer_modo("editor")
        self.assertTrue(soltar(v.vista, [self.video2]))
        self.assertEqual(v.modo, VIDEO)
        self.esperar(self.video_listo(self.video2))
        self.assertIn("Esto es un video", v.aviso.texto.text())

    def test_soltar_una_foto_en_video_vuelve_a_fotos(self):
        from celular_natural.ui.modo_facil import EDITOR, VIDEO
        v = self.v
        v.establecer_modo(EDITOR)
        v.abrir_rutas([str(self.video1)])
        editor = v.editor_video
        self.esperar(self.video_listo(self.video1))
        v.aviso.ocultar()
        # La foto soltada en la vista del video va a la tira, en el último modo de fotos (Editor).
        self.assertTrue(soltar(editor.vista, [self.foto1]))
        self.assertEqual(v.modo, EDITOR)
        self.esperar(self.foto_lista("playa.png"))
        self.assertEqual([Path(f.ruta).name for f in v._fotos], ["playa.png"])
        self.assertTrue(v.aviso.isVisible())
        self.assertIn("Esto es una foto: la abrimos en el modo de fotos.", v.aviso.texto.text())
        self.assertIn("Tu video sigue abierto", v.aviso.texto.text())
        self.assertIs(v.aviso.parentWidget(), v._tarjeta_vista_fotos)
        self.assertEqual(Path(editor.ruta), self.video1)  # el video no se cerró
        # Ese aviso explicaba el cambio de modo: al volver a Video, se cierra (no queda viejo).
        v.establecer_modo(VIDEO)
        self.assertFalse(v.aviso.mostrado)
        # Varias fotos soltadas en cualquier parte del modo Video (la columna izquierda, por ejemplo).
        soltar(v, [self.foto2, self.foto1])
        self.assertEqual(v.modo, EDITOR)
        self.assertIn("Estas son fotos", v.aviso.texto.text())
        self.assertEqual(sorted(Path(f.ruta).name for f in v._fotos), ["ciudad.jpg", "playa.png"])
        # Otros archivos no se aceptan al arrastrar.
        texto = self.dir / "notas.txt"
        texto.write_text("hola", encoding="utf-8")
        self.assertFalse(soltar(editor.vista, [texto]))

    def test_soltar_fotos_y_videos_juntos(self):
        from PySide6.QtWidgets import QMessageBox
        from celular_natural.ui.modo_facil import FACIL, VIDEO
        v = self.v
        self.assertEqual(v.modo, FACIL)
        self.assertTrue(soltar(v.vista, [self.foto1, self.video1, self.foto2, self.video2]))
        # Las fotos a la tira y el primer video al modo Video; el otro video se ignora.
        self.assertEqual(v.modo, VIDEO)
        self.assertEqual([Path(f.ruta).name for f in v._fotos], ["playa.png", "ciudad.jpg"])
        self.esperar(self.video_listo(self.video1))
        texto = v.aviso.texto.text()
        self.assertIn("Las 2 fotos van a la tira de fotos y el video lo abrimos en el modo Video.", texto)
        self.assertIn("El otro video no se abrió: se edita uno a la vez.", texto)
        self.assertIn("otro.mov", v.aviso.toolTip())
        self.assertIn("clip.mp4", v.aviso.toolTip())
        self.esperar(self.foto_lista("playa.png"))  # la foto se abrió aunque no se vea
        # Desde Video: una foto y dos videos. La foto a la tira, el primer video acá (el abierto
        # no tiene cortes: no se pregunta) y el aviso cuenta el ignorado.
        with mock.patch("celular_natural.ui.editor_video.QMessageBox.question") as pregunta:
            soltar(v.editor_video.vista, [self.video2, self.video3, self.foto2])
            pregunta.assert_not_called()
        self.assertEqual(v.modo, VIDEO)
        self.esperar(self.video_listo(self.video2))
        self.assertIn("La foto va a la tira de fotos", v.aviso.texto.text())
        self.assertIn("El otro video no se abrió", v.aviso.texto.text())
        self.assertEqual(len(v._fotos), 2)  # ciudad.jpg ya estaba en la tira
        # Con cortes, reemplazar el video pregunta; si se elige seguir, nada cambia.
        editor = v.editor_video
        editor.ir_a(0.5)
        editor.cortar()
        edicion = editor.edicion
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.No) as p:
            v.abrir_rutas([str(self.video1)])
            p.assert_called_once()
        self.pausa(0.2)
        self.assertEqual((Path(editor.ruta), editor.edicion), (self.video2, edicion))

    def test_el_dialogo_de_abrir_rutea(self):
        from PySide6.QtGui import QKeySequence
        from PySide6.QtWidgets import QFileDialog
        from celular_natural.ui.modo_facil import FACIL, VIDEO
        v = self.v
        llamadas = []
        respuestas = []

        def dialogo(*args, **_kw):
            llamadas.append(args)
            return respuestas.pop(0), "Fotos y videos"

        with mock.patch.object(QFileDialog, "getOpenFileNames", side_effect=dialogo):
            # Fácil: el botón Abrir acepta fotos y videos; una foto va a la tira y no cambia el modo.
            respuestas.append([str(self.foto1)])
            v.boton_abrir.click()
            filtro = llamadas[-1][3]
            self.assertTrue(filtro.startswith("Fotos y videos ("), filtro)
            for extension in ("*.jpg", "*.png", "*.tif", "*.mp4", "*.mov", "*.mkv", "*.webm"):
                self.assertIn(extension, filtro.split(";;")[0])
            self.assertEqual(v.modo, FACIL)
            self.esperar(self.foto_lista("playa.png"))
            # Un video elegido en el mismo diálogo (Ctrl+O) va al modo Video.
            respuestas.append([str(self.video1)])
            next(a for a in v._pagina_fotos.actions() if a.shortcut() == QKeySequence(QKeySequence.StandardKey.Open)).trigger()
            self.assertEqual(v.modo, VIDEO)
            self.assertIn("Esto es un video", v.aviso.texto.text())
            self.esperar(self.video_listo(self.video1))
            # En Video, "Abrir video" usa el mismo diálogo: una foto vuelve a las fotos.
            respuestas.append([str(self.foto2)])
            v.editor_video.boton_abrir.click()
            self.assertIn("Abrir un video", llamadas[-1][1])
            self.assertTrue(llamadas[-1][3].startswith("Fotos y videos ("))
            self.assertEqual(v.modo, FACIL)
            self.esperar(self.foto_lista("ciudad.jpg"))
            self.assertIn("Esto es una foto", v.aviso.texto.text())
            # Fotos y video juntos, con Ctrl+O desde Video (el atajo es el del editor de video).
            v.establecer_modo(VIDEO)
            respuestas.append([str(self.video2), str(self.foto1)])
            next(a for a in v.editor_video.actions() if a.shortcut() == QKeySequence(QKeySequence.StandardKey.Open)).trigger()
            self.assertEqual(v.modo, VIDEO)
            self.esperar(self.video_listo(self.video2))
            self.assertEqual(len(v._fotos), 2)
            self.assertIn("va a la tira", v.aviso.texto.text())
            # Cancelar el diálogo no cambia nada.
            respuestas.append([])
            v.elegir_archivo()
            self.assertEqual(v.modo, VIDEO)

    def test_nunca_hay_una_ventana_aparte_para_el_video(self):
        from PySide6.QtGui import QKeySequence
        from PySide6.QtWidgets import QApplication, QMainWindow
        from celular_natural.ui import editor_video as E
        from celular_natural.ui.modo_facil import EDITOR, VIDEO
        v = self.v

        def ventanas():
            return [w for w in QApplication.topLevelWidgets() if w.isVisible()]

        self.assertEqual(ventanas(), [v])
        self.assertFalse(issubclass(E.EditorVideo, QMainWindow))
        self.assertFalse(hasattr(E, "abrir_editor_video"))
        atajo = next(a for a in v.actions() if a.shortcut() == QKeySequence("Ctrl+Shift+V"))
        editores = set()
        # Todas las formas de llegar a Video: selector, botón de la barra, atajo, abrir y main.py.
        for paso in (lambda: v.boton_modo_video.click(), lambda: v.establecer_modo(EDITOR),
                     lambda: v.boton_video.click(), atajo.trigger, atajo.trigger,
                     lambda: v.abrir_rutas([str(self.video1)]), lambda: v.establecer_modo(EDITOR),
                     lambda: v.abrir_editor_video(str(self.video2)), lambda: v.abrir_editor_video()):
            paso()
            self.pausa(0.05)
            if v.editor_video is not None:
                editores.add(id(v.editor_video))
                self.assertFalse(v.editor_video.isWindow())
                self.assertIs(v.editor_video.window(), v)
                self.assertIs(v.editor_video.lateral.window(), v)
            self.assertEqual(ventanas(), [v])
        self.assertEqual(len(editores), 1)
        self.assertEqual(len(v.findChildren(E.EditorVideo)), 1)
        self.assertEqual(v.modo, VIDEO)
        self.esperar(self.video_listo(self.video2))
        self.assertEqual(ventanas(), [v])

    def test_la_exportacion_sigue_al_cambiar_de_modo(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from celular_natural.motor import Cancelado
        from celular_natural.ui import editor_video as E
        from celular_natural.ui.modo_facil import EDITOR, FACIL, VIDEO
        v = self.v
        v.abrir_rutas([str(self.foto1)])
        self.esperar(self.foto_lista("playa.png"))
        v.panel_ajustes.combo_preset.setCurrentText("Celular natural — sutil")  # pasa al video
        v.abrir_rutas([str(self.video1)])
        editor = v.editor_video
        self.esperar(self.video_listo(self.video1))
        destino = self.dir / "exportado_en_fotos.mp4"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "MP4 (*.mp4)")), \
                mock.patch.object(QMessageBox, "information") as cuadro:
            editor.exportar()
            self.assertTrue(editor.exportando)
            self.assertFalse(v.chip_video.isVisible())  # en Video se ve el progreso del editor
            v.establecer_modo(FACIL)  # se sigue trabajando en las fotos
            self.assertTrue(editor.exportando)
            self.assertTrue(v.chip_video.isVisible())
            self.assertTrue(v.exportando_algo())
            self.esperar(lambda: v.chip_video.porcentaje > 0 or not editor.exportando)
            if editor.exportando:
                self.assertIn("Exportando video", v.chip_video.texto.text())
                self.assertRegex(v.chip_video.texto.text(), r"\d+ %")
            v.establecer_modo(EDITOR)
            self.esperar(lambda: not editor.exportando, 120)
            cuadro.assert_not_called()  # en las fotos no interrumpe con un cuadro de diálogo
        self.assertFalse(v.chip_video.isVisible())
        self.assertTrue(destino.exists())
        self.assertTrue(v.aviso.isVisible())
        self.assertIn("Listo: se exportó el video exportado_en_fotos.mp4", v.aviso.texto.text())
        self.assertIn(str(destino), v.aviso.toolTip())
        cuadros, _audio, _datos = leer_video(destino)
        self.assertEqual([leer_codigo(c) for c in cuadros], list(range(72)))
        self.assertEqual(v._fotos[0].ruta, str(self.foto1))  # las fotos, como estaban

        # Al cerrar la app con una exportación en curso, se pregunta. Una exportación falsa que
        # solo termina si la cancelan (así no depende de la velocidad de la PC).
        def exportacion_lenta(_origen, _destino, _pila, _tramos, _resolucion, _calidad, avance, cancelado, **_kw):
            hechos = 0
            while not cancelado():
                hechos = min(hechos + 1, 99)
                avance(hechos, 100, None)
                time.sleep(0.02)
            raise Cancelado()

        otro = self.dir / "sin_terminar.mp4"
        with mock.patch.object(E.mv, "exportar_video", side_effect=exportacion_lenta), \
                mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(otro), "MP4 (*.mp4)")):
            v.establecer_modo(VIDEO)
            editor.exportar()
            v.establecer_modo(FACIL)
            self.esperar(lambda: v.chip_video.porcentaje > 0)
            with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.No) as pregunta:
                v.close()
                pregunta.assert_called_once()
            self.assertTrue(v.isVisible())  # eligió no cerrar: la exportación sigue
            self.assertTrue(editor.exportando)
            with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
                v.close()
            self.assertFalse(v.isVisible())
            self.app.processEvents()
            self.assertFalse(editor.exportando)
        self.assertFalse(otro.exists())

    def test_modo_guardado_atajos_filtro_y_cerrar_video(self):
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QKeyEvent, QKeySequence
        from PySide6.QtWidgets import QMessageBox
        from celular_natural.ui.modo_facil import CLAVE_MODO, EDITOR, FACIL, VIDEO, configuracion
        from celular_natural.ui.ventana import VentanaPrincipal
        v = self.v
        v.establecer_modo(EDITOR)
        atajo_video = next(a for a in v.actions() if a.shortcut() == QKeySequence("Ctrl+Shift+V"))
        atajo_e = next(a for a in v.actions() if a.shortcut() == QKeySequence("Ctrl+E"))
        atajo_video.trigger()
        self.assertEqual(v.modo, VIDEO)
        self.assertEqual(configuracion().value(CLAVE_MODO), EDITOR)  # se guarda el de fotos
        atajo_video.trigger()
        self.assertEqual(v.modo, EDITOR)
        atajo_video.trigger()
        atajo_e.trigger()
        self.assertEqual(v.modo, EDITOR)
        atajo_e.trigger()
        self.assertEqual(v.modo, FACIL)
        # Cerrar estando en Video: la próxima vez arranca en el último modo de fotos.
        v.establecer_modo(VIDEO)
        otra = VentanaPrincipal()
        try:
            self.assertEqual(otra.modo, FACIL)
        finally:
            otra.close()
            otra.deleteLater()
        # En Video, la barra espaciadora es de la reproducción (no muestra la foto original).
        v.abrir_rutas([str(self.foto1)])
        self.esperar(self.foto_lista("playa.png"))
        v.establecer_modo(VIDEO)
        espacio = QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier, " ")
        self.assertFalse(v._filtro_espacio.eventFilter(v.editor_video.vista, espacio))
        v.establecer_modo(FACIL)
        v.activateWindow()
        self.pausa(0.05)
        self.assertTrue(v._filtro_espacio.eventFilter(v.vista, espacio))  # en fotos, muestra el original
        v._filtro_espacio.eventFilter(v.vista, QKeyEvent(QEvent.KeyRelease, Qt.Key_Space, Qt.NoModifier, " "))

        # El filtro: la primera vez se copió el de las fotos (Celular natural); después el video
        # tiene el suyo y "Usar el de las fotos" lo vuelve a copiar.
        editor = v.editor_video
        self.assertEqual(editor.panel_ajustes.estado()["preset"], v.panel_ajustes.estado()["preset"])
        v.panel_ajustes.combo_preset.setCurrentText("Día nublado")
        v.establecer_modo(VIDEO)
        self.assertNotEqual(editor.panel_ajustes.estado()["preset"], "Día nublado")
        editor.boton_filtro_fotos.click()
        self.assertEqual(editor.panel_ajustes.estado()["preset"], "Día nublado")
        self.assertEqual(editor.panel_ajustes.pila(), v.panel_ajustes.pila())

        # Cerrar el video: con cortes pregunta; después vuelve la invitación y se va el punto.
        v.abrir_rutas([str(self.video1)])
        self.esperar(self.video_listo(self.video1))
        self.assertTrue(editor.boton_cerrar_video.isVisible())
        editor.ir_a(1.0)
        editor.cortar()
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.No):
            self.assertFalse(editor.cerrar_video())
        self.assertIsNotNone(editor.info)
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            editor.boton_cerrar_video.click()
        self.assertIsNone(editor.info)
        self.assertFalse(editor.vista.tiene_imagen())
        self.assertFalse(editor.boton_cerrar_video.isVisible())
        self.assertEqual(v.windowTitle(), "NaturalShot PRO · Video")
        v.establecer_modo(FACIL)
        self.assertFalse(v.boton_modo_video.punto)


if __name__ == "__main__":
    unittest.main()
