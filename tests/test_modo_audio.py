"""Pruebas del modo Audio: el editor de audio adentro de la ventana principal.

* El selector tiene Audio; Ctrl+Shift+A va y vuelve; el editor se arma recién al
  entrar; el modo Audio se recuerda.
* Ruteo: un audio soltado en Fácil pasa a Audio (con aviso); una foto soltada en
  Audio vuelve a las fotos; un archivo sin sonido (o que no se lee) avisa y no
  cambia nada.
* Escenas, cortes (cortar, borrar, recuperar), sonidos sueltos que se arrastran,
  hasta 3 capas de fondo, deshacer y rehacer (un deslizador movido seguido es un
  solo paso, y el arreglo de "volvió al valor de antes").
* Exportar a WhatsApp (.ogg, Opus mono) con un diálogo simulado, y que la
  exportación siga al cambiar de modo (chip junto al selector).
* Escuchar: sin salida de sonido anda igual (con su reloj); con un QtMultimedia de
  mentira suena el mezclador y un cambio mientras suena no corta.
* La sesión recuerda el proyecto de audio (otra ventana con el mismo APPDATA).

Ventana real en modo sin pantalla, con un .ini propio (``NATURALSHOT_CONFIG``) y un
APPDATA temporal. Los audios se generan acá con PyAV (tonos con sílabas). Para
esperar se usa ``time.sleep`` y ``processEvents`` (``QTest.qWait`` no suelta el GIL).
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
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

try:
    import av
except ImportError:  # pragma: no cover
    av = None

SR = 48000


# ---------------------------------------------------------------------------
# Medios de prueba (todos generados)
# ---------------------------------------------------------------------------

def senal_voz(segundos: float, nivel: float = 0.3) -> np.ndarray:
    """Una "voz": un tono que sube y baja, en sílabas de unos 330 ms."""
    t = np.arange(int(SR * segundos)) / SR
    silabas = (0.5 + 0.5 * np.sin(2 * np.pi * 3.0 * t)) ** 2
    return (nivel * silabas * np.sin(2 * np.pi * (180 + 40 * np.sin(2 * np.pi * 0.5 * t)) * t)).astype(np.float32)


def escribir_audio(ruta: Path, senal: np.ndarray, codec: str = "pcm_s16le") -> Path:
    """Un archivo de solo audio, mono, a 48 kHz."""
    with av.open(str(ruta), "w") as c:
        s = c.add_stream(codec, rate=SR)
        s.layout = "mono"
        formato = s.codec_context.format.name if s.codec_context.format else "s16"
        tam = {"aac": 1024, "libmp3lame": 1152, "libopus": 960}.get(codec, 4096)
        pts = 0
        for i in range(0, len(senal), tam):
            trozo = senal[i:i + tam]
            if formato == "s16":
                cuadro = av.AudioFrame.from_ndarray((np.clip(trozo, -1, 1) * 32767).astype(np.int16)[None, :],
                                                    format="s16", layout="mono")
            elif formato == "flt":
                cuadro = av.AudioFrame.from_ndarray(trozo[None, :].astype(np.float32), format="flt", layout="mono")
            else:
                cuadro = av.AudioFrame.from_ndarray(trozo[None, :].astype(np.float32), format="fltp", layout="mono")
            cuadro.sample_rate = SR
            cuadro.pts = pts
            pts += len(trozo)
            for paquete in s.encode(cuadro):
                c.mux(paquete)
        for paquete in s.encode(None):
            c.mux(paquete)
    return ruta


def video_sin_audio_como_m4a(ruta: Path) -> Path:
    """Un .m4a que en realidad tiene solo video (sin pista de sonido)."""
    with av.open(str(ruta), "w", format="mp4") as c:
        s = c.add_stream("mpeg4", rate=10)
        s.width, s.height, s.pix_fmt = 64, 48, "yuv420p"
        for i in range(5):
            cuadro = av.VideoFrame.from_ndarray(np.full((48, 64, 3), 40 * i, np.uint8), format="rgb24")
            for paquete in s.encode(cuadro):
                c.mux(paquete)
        for paquete in s.encode(None):
            c.mux(paquete)
    return ruta


def foto(ruta: Path, semilla: int = 1, w: int = 320, h: int = 240) -> Path:
    from PIL import Image
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.dstack([80 + 120 * xx / w, 140 - 60 * yy / h, 90 + 80 * yy / h]) + rng.normal(0, 6, (h, w, 3))
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(ruta)
    return ruta


def soltar(widget, rutas) -> bool:
    """Arrastra y suelta archivos sobre ``widget``. Devuelve si el arrastre fue aceptado."""
    from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent
    from PySide6.QtWidgets import QApplication
    datos = QMimeData()
    datos.setUrls([QUrl.fromLocalFile(str(r)) for r in rutas])
    centro = widget.rect().center()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        entrar = QDragEnterEvent(centro, Qt.CopyAction, datos, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(widget, entrar)
    aceptado = entrar.isAccepted()
    QApplication.sendEvent(widget, QDropEvent(QPointF(centro), Qt.CopyAction, datos, Qt.LeftButton, Qt.NoModifier))
    return aceptado


def raton(widget, tipo, x: float, y: float, apretado: bool) -> None:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    pos = QPointF(x, y)
    evento = QMouseEvent(tipo, pos, widget.mapToGlobal(pos), Qt.LeftButton,
                         Qt.LeftButton if apretado else Qt.NoButton, Qt.NoModifier)
    QApplication.sendEvent(widget, evento)


@unittest.skipIf(av is None, "Falta PyAV (pip install av==19.0.1)")
class PruebasModoAudio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        from celular_natural.ui.estilo import HOJA_ESTILO
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(HOJA_ESTILO)
        cls.dir = Path(tempfile.mkdtemp(prefix="naturalshot_modo_audio_"))
        cls._entorno = {k: os.environ.get(k) for k in ("APPDATA", "NATURALSHOT_CONFIG")}
        os.environ["APPDATA"] = str(cls.dir / "appdata")
        cls.config = cls.dir / "config.ini"
        os.environ["NATURALSHOT_CONFIG"] = str(cls.config)
        cls.voz = escribir_audio(cls.dir / "voz.wav", senal_voz(4.0))
        cls.voz2 = escribir_audio(cls.dir / "otra voz.m4a", senal_voz(3.0, 0.2), "aac")
        cls.sin_sonido = video_sin_audio_como_m4a(cls.dir / "sin sonido.m4a")
        cls.roto = cls.dir / "roto.mp3"
        cls.roto.write_bytes(np.random.default_rng(3).integers(0, 255, 4000, dtype=np.uint8).tobytes())
        cls.foto = foto(cls.dir / "playa.png")

    @classmethod
    def tearDownClass(cls):
        for clave, valor in cls._entorno.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        from PySide6.QtWidgets import QMessageBox
        if self.config.exists():
            self.config.unlink()  # cada prueba arranca como la primera vez (en Fácil)
        # Un cuadro de diálogo que nadie esperaba no cuelga la prueba: se anota y la prueba falla.
        self.cuadros_inesperados = []
        for nombre in ("warning", "critical"):
            parche = mock.patch.object(QMessageBox, nombre, side_effect=lambda *a, **_k: (
                self.cuadros_inesperados.append(a[1:3]), QMessageBox.Ok)[1])
            parche.start()
            self.addCleanup(parche.stop)
        # Los que una prueba no simula a propósito: "No" a las preguntas y "Aceptar" a los avisos.
        for nombre, respuesta in (("question", QMessageBox.No), ("information", QMessageBox.Ok)):
            parche = mock.patch.object(QMessageBox, nombre, return_value=respuesta)
            parche.start()
            self.addCleanup(parche.stop)
        self.ventanas = []
        self.v = self.nueva_ventana()

    def nueva_ventana(self):
        from celular_natural.ui.ventana import VentanaPrincipal
        v = VentanaPrincipal()
        v.resize(1366, 768)
        v.show()
        v.activateWindow()
        self.ventanas.append(v)
        self.pausa(0.05)
        return v

    def cerrar(self, v) -> None:
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication, QMessageBox
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            v.close()
        v.deleteLater()
        self.app.processEvents()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def tearDown(self):
        for v in self.ventanas:
            try:
                visible = v.isVisible()
            except RuntimeError:  # ya cerrada y borrada por la prueba
                continue
            if visible:
                self.cerrar(v)
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        self.app.processEvents()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertEqual(self.cuadros_inesperados, [], "apareció un cuadro de error que no se esperaba")

    # ------------------------------------------------------------ ayudas
    def esperar(self, condicion, segundos: float = 60.0) -> None:
        fin = time.monotonic() + segundos
        while time.monotonic() < fin:
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

    def abrir_voz(self, v=None, ruta=None):
        """Abre una voz en el modo Audio y espera a que esté su forma de onda."""
        from celular_natural.ui.modo_facil import AUDIO
        v = v or self.v
        v.abrir_rutas([str(ruta or self.voz)])
        self.assertEqual(v.modo, AUDIO)
        e = v.editor_audio
        self.esperar(lambda: e.proyecto is not None and not e.cargador_onda.cargando)
        return e

    def atajo(self, widget, secuencia):
        from PySide6.QtGui import QKeySequence
        return next(a for a in widget.actions() if a.shortcut() == QKeySequence(secuencia))

    # ------------------------------------------------------------ selector y ruteo
    def test_selector_y_atajo_van_y_vuelven(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QFrame
        from celular_natural.ui.modo_facil import AUDIO, CLAVE_MODO, EDITOR, FACIL, VIDEO, configuracion
        v = self.v
        modos = [b.property("modo") for b in v.grupo_interfaz.buttons()]
        self.assertEqual(modos, [FACIL, EDITOR, VIDEO, AUDIO])
        self.assertIsNone(v.editor_audio)  # se arma recién al entrar (con PyAV)
        selector = [w for w in v.findChildren(QFrame, "selectorModo") if w.isVisible()][0]
        lugar = selector.mapTo(v, QPoint(0, 0))
        atajo = self.atajo(v, "Ctrl+Shift+A")
        atajo.trigger()
        self.assertEqual(v.modo, AUDIO)
        e = v.editor_audio
        self.assertIsNotNone(e)
        self.assertTrue(e.isVisible() and e.lateral.isVisible())
        self.assertFalse(v._pagina_fotos.isVisible() or v._lateral_fotos.isVisible())
        self.assertTrue(v.boton_modo_audio.isChecked())
        self.assertEqual(selector.mapTo(v, QPoint(0, 0)), lugar)
        self.assertEqual(v.windowTitle(), "NaturalShot PRO · Audio")
        self.assertEqual(configuracion().value(CLAVE_MODO), AUDIO)  # Audio se recuerda
        atajo.trigger()  # y vuelve al modo de antes
        self.assertEqual(v.modo, FACIL)
        self.assertTrue(e.isHidden())
        self.assertEqual(configuracion().value(CLAVE_MODO), FACIL)
        # Desde Video, Ctrl+Shift+A va a Audio y vuelve a Video; Ctrl+E desde Audio, a las fotos.
        v.establecer_modo(VIDEO)
        atajo.trigger()
        self.assertEqual(v.modo, AUDIO)
        self.assertTrue(v.editor_video.isHidden())
        atajo.trigger()
        self.assertEqual(v.modo, VIDEO)
        atajo.trigger()
        self.atajo(v, "Ctrl+E").trigger()
        self.assertEqual(v.modo, FACIL)
        # Cerrar en Audio: la próxima vez abre en Audio (y desde ahí vuelve a Editor, el último de fotos).
        v.establecer_modo(EDITOR)
        v.boton_modo_audio.click()
        self.assertEqual(v.modo, AUDIO)
        otra = self.nueva_ventana()
        self.assertEqual(otra.modo, AUDIO)
        self.assertIsNotNone(otra.editor_audio)
        self.atajo(otra, "Ctrl+E").trigger()
        self.assertEqual(otra.modo, EDITOR)

    def test_soltar_un_audio_en_facil_y_una_foto_en_audio(self):
        from celular_natural.ui.modo_facil import AUDIO, FACIL
        v = self.v
        self.assertEqual(v.modo, FACIL)
        self.assertTrue(soltar(v.vista, [self.voz]))
        self.assertEqual(v.modo, AUDIO)
        e = v.editor_audio
        self.assertEqual(Path(e.ruta), self.voz)
        self.assertTrue(v.aviso.mostrado)
        self.assertIn("Esto es un audio: lo abrimos en el modo Audio", v.aviso.texto.text())
        self.assertIs(v.aviso.parentWidget(), e.vista)
        self.assertIn("voz.wav", v.aviso.toolTip())
        self.assertIn("voz.wav", v.windowTitle())
        self.esperar(lambda: not e.cargador_onda.cargando)
        self.assertEqual(e.onda.pista.estado, "lista")
        # Una foto soltada en Audio va a la tira (en el último modo de fotos) y el audio sigue abierto.
        self.assertTrue(soltar(e.vista, [self.foto]))
        self.assertEqual(v.modo, FACIL)
        self.assertEqual([Path(f.ruta).name for f in v._fotos], ["playa.png"])
        self.assertIn("Esto es una foto: la abrimos en el modo de fotos.", v.aviso.texto.text())
        self.assertIn("Tu audio sigue abierto", v.aviso.texto.text())
        self.assertTrue(v.boton_modo_audio.punto)  # el punto avisa que hay un audio abierto
        self.assertIn("voz.wav", v.boton_modo_audio.toolTip())
        self.assertEqual(Path(e.ruta), self.voz)
        # Un M4A se abre igual (y, si el abierto no tiene cambios, sin preguntar).
        with mock.patch("celular_natural.ui.modo_audio.QMessageBox.question") as pregunta:
            self.abrir_voz(ruta=self.voz2)
            pregunta.assert_not_called()
        self.assertEqual(Path(e.ruta), self.voz2)
        self.assertAlmostEqual(e.mapa.duracion, 3.0, delta=0.05)
        # El diálogo de Abrir ofrece los audios.
        from PySide6.QtWidgets import QFileDialog
        with mock.patch.object(QFileDialog, "getOpenFileNames", return_value=([], "")) as dialogo:
            e.boton_abrir.click()
            filtro = dialogo.call_args[0][3]
        self.assertTrue(filtro.startswith("Audios ("), filtro)
        for extension in ("*.mp3", "*.m4a", "*.wav", "*.ogg", "*.opus", "*.aac", "*.flac"):
            self.assertIn(extension, filtro.split(";;")[0])
        v.establecer_modo(FACIL)
        with mock.patch.object(QFileDialog, "getOpenFileNames", return_value=([], "")) as dialogo:
            v.boton_abrir.click()
            filtro = dialogo.call_args[0][3]
        self.assertTrue(filtro.startswith("Fotos y videos ("), filtro)
        self.assertIn("*.mp3", filtro.split(";;")[0])

    def test_archivo_sin_sonido_avisa_y_no_cambia_nada(self):
        from celular_natural.ui.modo_facil import AUDIO, FACIL
        v = self.v
        for ruta, texto in ((self.sin_sonido, "no tiene sonido"), (self.roto, "No se pudo abrir")):
            v.aviso.ocultar()
            v.abrir_rutas([str(ruta)])
            self.assertEqual(v.modo, FACIL)
            self.assertTrue(v.aviso.mostrado)
            self.assertIn(texto, v.aviso.texto.text())
            self.assertIn(ruta.name, v.aviso.texto.text())
            self.assertTrue(v.editor_audio is None or v.editor_audio.ruta is None)
        # Con un audio abierto en Audio, uno que no sirve tampoco lo cambia.
        e = self.abrir_voz()
        proyecto = e.proyecto
        self.assertTrue(soltar(e.vista, [self.sin_sonido]))
        self.assertEqual(v.modo, AUDIO)
        self.assertIs(e.proyecto, proyecto)
        self.assertIn("no tiene sonido", v.aviso.texto.text())

    # ------------------------------------------------------------ edición
    def test_guardar_igual_a_una_de_la_app_marca_la_propia(self):
        # Guardar sin cambios después de aplicar una escena de la app: queda marcada la recién
        # guardada (no la de la app, aunque sean iguales). Al volver a elegir la de la app, esa.
        e = self.abrir_voz()
        app = e.galeria_escenas.tarjeta("nota_calle")
        app.elegida.emit("nota_calle")
        self.assertTrue(app.seleccionada)
        self.assertTrue(e.guardar_como_escena("Mi vereda"))
        propia = e.galeria_escenas.tarjeta("Mi vereda", propia=True)
        self.assertTrue(propia.seleccionada)
        self.assertFalse(e.galeria_escenas.tarjeta("nota_calle").seleccionada)
        # Un cambio que sigue coincidiendo (deshacer y rehacer) mantiene la marca en la propia.
        e.control_cuanto.botones[90].click()
        e.deshacer()
        self.assertTrue(e.galeria_escenas.tarjeta("Mi vereda", propia=True).seleccionada)
        e.galeria_escenas.tarjeta("nota_calle").elegida.emit("nota_calle")
        self.assertTrue(e.galeria_escenas.tarjeta("nota_calle").seleccionada)
        self.assertFalse(e.galeria_escenas.tarjeta("Mi vereda", propia=True).seleccionada)
        self.assertTrue(e.borrar_escena_propia("Mi vereda", confirmar=False))  # el APPDATA es de la clase

    def test_escena_entra_al_historial(self):
        from celular_natural.motor.proyecto_audio import ESCENAS
        e = self.abrir_voz()
        inicial = e.proyecto
        self.assertEqual(len(e.historial), 1)
        tarjeta = e.galeria_escenas.tarjeta("nota_calle")
        tarjeta.elegida.emit("nota_calle")  # como tocar la tarjeta
        escena = ESCENAS["nota_calle"]
        self.assertEqual(e.proyecto.voz, escena.voz)
        self.assertEqual(e.proyecto.fondos, escena.fondos)
        self.assertEqual(len(e.proyecto.sonidos), 1)
        self.assertEqual(e.proyecto.sonidos[0].clave, "colectivo_pasa")
        self.assertAlmostEqual(e.proyecto.sonidos[0].ancla, 0.4 * 4.0, delta=0.01)
        self.assertTrue(tarjeta.seleccionada)
        self.assertTrue(e.selector_destino.tarjetas["whatsapp"].seleccionada)
        self.assertEqual(len(e.historial), 2)
        self.assertIn("Nota de voz caminando por la calle", e.historial[1][0])
        self.assertTrue(e.tiene_cambios())
        # La pista Fondo y la de Sonidos lo muestran.
        self.assertEqual([c.nombre for c in e.pista_fondo.capas], ["Calle con tránsito"])
        self.assertEqual(len(e.pista_sonidos.bloques), 1)
        # Deshacer vuelve; rehacer la vuelve a poner.
        self.atajo(e, "Ctrl+Z").trigger()
        self.assertEqual(e.proyecto, inicial)
        self.assertFalse(tarjeta.seleccionada)
        self.assertEqual(e.pista_sonidos.bloques, [])
        self.atajo(e, "Ctrl+Y").trigger()
        self.assertEqual(e.proyecto.voz, escena.voz)
        # Elegir otro destino y "Cuánto".
        e.selector_destino.tarjetas["auriculares"].elegida.emit("auriculares")
        self.assertEqual(e.proyecto.voz.destino, "auriculares")
        e.control_cuanto.botones[90].click()
        self.assertEqual(e.proyecto.voz.cuanto, 0.9)
        self.assertFalse(tarjeta.seleccionada)
        # Guardar como escena y volver a aplicarla.
        self.assertTrue(e.guardar_como_escena("Mi oficina"))
        propia = e.galeria_escenas.tarjeta("Mi oficina", propia=True)
        self.assertIsNotNone(propia)
        self.assertTrue(propia.seleccionada)
        e.deshacer()
        e.deshacer()
        self.assertTrue(e.aplicar_escena("Mi oficina", propia=True))
        self.assertEqual((e.proyecto.voz.destino, e.proyecto.voz.cuanto), ("auriculares", 0.9))
        self.assertTrue(e.borrar_escena_propia("Mi oficina", confirmar=False))
        self.assertIsNone(e.galeria_escenas.tarjeta("Mi oficina", propia=True))

    def test_cortar_borrar_y_recuperar(self):
        e = self.abrir_voz()
        e.ir_a(1.0)
        self.atajo(e, "S").trigger()
        e.ir_a(2.0)
        self.atajo(e, "S").trigger()
        e.linea.seleccionar(1)
        self.atajo(e, "Del").trigger()
        self.assertEqual(e.proyecto.tramos, ((0.0, 1.0), (2.0, 4.0)))
        self.assertEqual(e.edicion.tramos_conservados(), [(0.0, 1.0), (2.0, 4.0)])
        self.assertAlmostEqual(e.mapa.duracion, 3.0, places=6)
        self.assertIn("3,00 de 0:04,00", e.etiqueta_resultado.text())
        self.assertEqual(len(e.linea.huecos), 1)
        # Silenciar el tramo del cursor (M) y devolverle el sonido.
        e.ir_a(0.5)
        e.linea.seleccionar(-1)
        self.atajo(e, "M").trigger()
        self.assertEqual(e.proyecto.sonido.silencios, ((0.0, 1.0),))
        self.atajo(e, "M").trigger()
        self.assertEqual(e.proyecto.sonido.silencios, ())
        # Recuperar lo borrado (R, la marquita más cercana) y deshacerlo.
        self.atajo(e, "R").trigger()
        self.assertEqual(e.proyecto.tramos, ((0.0, 4.0),))
        self.assertEqual(e.linea.huecos, [])
        e.deshacer()
        self.assertEqual(e.proyecto.tramos, ((0.0, 1.0), (2.0, 4.0)))
        # Entrada y salida.
        e.ir_a(0.5)
        self.atajo(e, "I").trigger()
        self.assertAlmostEqual(e.proyecto.tramos[0][0], 0.5, places=6)
        self.assertAlmostEqual(e.mapa.duracion, 2.5, places=6)

    def test_sonido_en_el_cursor_y_arrastrarlo(self):
        from PySide6.QtCore import QEvent
        e = self.abrir_voz()
        e.ir_a(1.0)
        self.assertTrue(e.agregar_sonido("generado", "bocina"))
        s = e.proyecto.sonidos[0]
        self.assertEqual((s.origen, s.clave), ("generado", "bocina"))
        self.assertAlmostEqual(s.ancla, 1.0, places=6)
        self.assertEqual(len(e.filas_sonidos), 1)
        self.assertEqual(e.filas_sonidos[0].boton_ir.text(), "0:01,00")
        pasos = len(e.historial)
        pista = e.pista_sonidos
        self.pausa(0.1)
        rect = pista.rect_bloque(0)
        self.assertGreater(rect.width(), 8)
        x0, y = rect.left() + 6, rect.center().y()
        dx = 90.0
        raton(pista, QEvent.MouseButtonPress, x0, y, True)
        for paso in range(1, 7):
            raton(pista, QEvent.MouseMove, x0 + dx * paso / 6, y, True)
        raton(pista, QEvent.MouseButtonRelease, x0 + dx, y, False)
        esperado = 1.0 + dx * e.mapa.duracion / pista._carril().width()
        self.assertAlmostEqual(e.proyecto.sonidos[0].ancla, esperado, delta=0.01)
        self.assertEqual(len(e.historial), pasos + 1)
        self.assertIn("movido", e.historial[-1][0])
        # El ancla va en tiempo original: si se borra algo antes, el sonido sigue a la voz.
        ancla = e.proyecto.sonidos[0].ancla
        e.ir_a(0.2)
        e.cortar()
        e.ir_a(0.6)
        e.cortar()
        e.linea.seleccionar(1)
        e.borrar_tramo()
        self.assertAlmostEqual(e.proyecto.sonidos[0].ancla, ancla, places=9)
        self.assertAlmostEqual(pista.bloques[0].inicio, ancla - 0.4, delta=0.002)
        # Deshacer el arrastre lo vuelve a 1,0.
        e.deshacer()
        e.deshacer()
        e.deshacer()
        e.deshacer()
        self.assertAlmostEqual(e.proyecto.sonidos[0].ancla, 1.0, places=6)
        # Un sonido de Mis sonidos también se agrega; si se borra el archivo, queda como "falta".
        antes = len(e.filas_mis_sonidos)  # el APPDATA es de toda la clase: otras pruebas también agregan
        copias = e.agregar_a_mis_sonidos([str(self.voz2)])
        self.assertEqual(len(copias), 1)
        self.assertEqual(len(e.filas_mis_sonidos), antes + 1)
        self.assertTrue(e.agregar_sonido("archivo", copias[0].name))
        self.assertFalse(e.filas_sonidos[1].falta.isVisibleTo(e.filas_sonidos[1]))
        self.assertTrue(e.renombrar_mi_sonido(copias[0].name, "gente"))
        self.assertEqual(e.proyecto.sonidos[1].clave, "gente.m4a")  # el proyecto sigue al nombre nuevo
        self.assertTrue(e.borrar_mi_sonido("gente.m4a", confirmar=False))
        self.assertTrue(e.filas_sonidos[1].falta.isVisibleTo(e.filas_sonidos[1]))
        self.assertTrue(e.pista_sonidos.bloques[1].falta)

    def test_hasta_tres_capas_de_fondo(self):
        e = self.abrir_voz()
        e.boton_agregar_fondo.setChecked(True)
        self.assertTrue(e.galeria_fondos.isVisible())
        for clave in ("olas", "viento", "lluvia"):
            self.assertTrue(e.boton_agregar_fondo.isEnabled())
            e.tarjetas_fondo[("generado", clave)].elegida.emit(clave)  # como tocar la tarjeta
        self.assertEqual([f.clave for f in e.proyecto.fondos], ["olas", "viento", "lluvia"])
        self.assertEqual(len(e.filas_capas), 3)
        # La cuarta: deshabilitada.
        self.assertFalse(e.boton_agregar_fondo.isEnabled())
        self.assertFalse(e.galeria_fondos.isVisible())
        self.assertTrue(all(not t.isEnabled() for t in e.tarjetas_fondo.values()))
        self.assertFalse(e.agregar_fondo("generado", "agua"))
        self.assertEqual(len(e.proyecto.fondos), 3)
        self.assertEqual(len(e.pista_fondo.capas), 3)
        # Volumen e intensidad de una capa (un solo paso aunque se mueva varias veces).
        pasos = len(e.historial)
        for valor in (60, 70, 80):
            e.filas_capas[0].volumen.slider.setValue(valor)
        self.assertEqual(e.proyecto.fondos[0].volumen, 0.8)
        self.assertEqual(len(e.historial), pasos + 1)
        e.filas_capas[2].intensidad.slider.setValue(90)
        self.assertEqual(e.proyecto.fondos[2].intensidad, 0.9)
        # Quitar una vuelve a habilitar agregar.
        e.filas_capas[1].boton_quitar.click()
        self.pausa(0.05)
        self.assertEqual([f.clave for f in e.proyecto.fondos], ["olas", "lluvia"])
        from celular_natural.ui.paneles_audio import FilaCapaFondo
        visibles = [f for f in e.findChildren(FilaCapaFondo) if f.isVisible()]
        self.assertEqual(len(visibles), 2)  # las filas de antes no quedan a la vista (encima de las nuevas)
        self.assertTrue(e.boton_agregar_fondo.isEnabled())
        self.assertTrue(all(t.isEnabled() for t in e.tarjetas_fondo.values()))
        # "Escuchar 3 s" sin salida de sonido: avisa, sin errores.
        e.filas_capas[0].boton_escuchar.click()
        self.assertIn("Sin salida de sonido", e.etiqueta_estado.text())

    def test_deslizador_seguido_es_un_solo_paso(self):
        e = self.abrir_voz()
        e.aplicar_escena("nota_oficina")
        self.assertEqual(len(e.historial), 2)
        anti = e.control_anti_ia.slider
        for valor in (45, 50, 55, 60):
            anti.setValue(valor)
        self.assertEqual(e.proyecto.voz.anti_ia, 0.6)
        self.assertEqual(len(e.historial), 3)
        # El arreglo de Video: el volumen va de 100 a 110, vuelve a 100 (el paso se saca) y sigue a
        # 120. Ese último es un paso nuevo: no se pega al de "Bajarle lo de IA".
        volumen = e.panel_volumen.volumen.slider
        volumen.setValue(110)
        self.assertEqual(len(e.historial), 4)
        volumen.setValue(100)
        self.assertEqual(len(e.historial), 3)
        self.assertEqual(e.proyecto.sonido.volumen, 1.0)
        volumen.setValue(120)
        self.assertEqual(len(e.historial), 4)
        self.assertEqual(e.historial[2][1].voz.anti_ia, 0.6)
        self.assertEqual(e.historial[2][1].sonido.volumen, 1.0)
        e.deshacer()
        self.assertEqual((e.proyecto.voz.anti_ia, e.proyecto.sonido.volumen), (0.6, 1.0))
        e.deshacer()
        self.assertEqual(e.proyecto.voz.anti_ia, 0.4)
        # Lo mismo con "Bajarle lo de IA" que vuelve a su valor: el próximo es otro paso.
        e.rehacer()
        e.rehacer()
        self.assertEqual(len(e.historial), 4)
        anti.setValue(70)
        anti.setValue(60)
        self.assertEqual(len(e.historial), 4)
        anti.setValue(65)
        self.assertEqual(len(e.historial), 5)
        self.assertEqual(e.historial[3][1].sonido.volumen, 1.2)
        # Pasado el tiempo de juntar, el mismo control es otro paso.
        from celular_natural.ui import modo_audio as M
        with mock.patch.object(M.time, "monotonic", return_value=time.monotonic() + 10):
            anti.setValue(66)
        self.assertEqual(len(e.historial), 6)

    # ------------------------------------------------------------ arreglos de la revisión
    def mi_sonido(self, e, nombre: str) -> Path:
        """Agrega a Mis sonidos una copia de la voz 2 con ese nombre (único en la prueba)."""
        fuente = self.dir / nombre
        shutil.copy(self.voz2, fuente)
        return e.agregar_a_mis_sonidos([str(fuente)])[0]

    def test_no_se_toca_un_archivo_de_mis_sonidos_mientras_se_exporta(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from celular_natural.motor import Cancelado
        from celular_natural.ui import modo_audio as M
        e = self.abrir_voz()
        copia = self.mi_sonido(e, "gente charlando.m4a")
        e.agregar_fondo("archivo", copia.name)

        def lenta(_p, _ruta, _formato, progreso, cancelado):
            while not cancelado():
                progreso(1, 2, None)
                time.sleep(0.02)
            raise Cancelado()

        with mock.patch.object(M.pa, "exportar_proyecto", side_effect=lenta), \
                mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(self.dir / "y.m4a"), "")), \
                mock.patch.object(QMessageBox, "information") as aviso:
            e.exportar()
            self.assertTrue(e.exportando)
            self.assertFalse(e.renombrar_mi_sonido(copia.name, "otro nombre"))
            self.assertFalse(e.borrar_mi_sonido(copia.name, confirmar=False))
            self.assertEqual(aviso.call_count, 2)
            self.assertEqual(aviso.call_args[0][1], "Esperá a que termine de exportar")
            self.assertTrue(copia.exists())
            self.assertEqual(e.proyecto.fondos[0].clave, copia.name)
            e.cancelar_exportacion()
            self.esperar(lambda: not e.exportando)
        self.assertTrue(e.renombrar_mi_sonido(copia.name, "gente en la plaza"))  # terminada, sí
        self.assertEqual(e.proyecto.fondos[0].clave, "gente en la plaza.m4a")

    def test_los_corchetes_no_borran_todo(self):
        e = self.abrir_voz()
        e.ir_a(1.0)
        e.cortar()
        e.ir_a(2.0)
        e.cortar()
        e.linea.seleccionar(0)
        e.borrar_tramo()
        e.linea.seleccionar(2)
        e.borrar_tramo()
        self.assertEqual(e.proyecto.tramos, ((1.0, 2.0),))
        pasos = len(e.historial)
        e.linea.limitesPedidos.emit(2.5, None)  # una entrada después de lo único que queda
        self.assertEqual(e.proyecto.tramos, ((1.0, 2.0),))
        self.assertEqual(len(e.historial), pasos)
        self.assertIn("no se puede borrar todo", e.etiqueta_estado.text())

    def test_semilla_libre_al_quitar_y_volver_a_sumar(self):
        e = self.abrir_voz()
        for _ in range(3):
            e.agregar_fondo("generado", "viento")
        self.assertEqual([f.semilla for f in e.proyecto.fondos], [0, 1, 2])
        e.quitar_fondo(0)
        e.agregar_fondo("generado", "viento")
        self.assertEqual(sorted(f.semilla for f in e.proyecto.fondos), [0, 1, 2])  # nunca dos iguales
        e.ir_a(1.0)
        e.agregar_sonido("generado", "bocina")
        e.agregar_sonido("generado", "bocina")
        e.borrar_sonido(0)
        e.agregar_sonido("generado", "bocina")
        self.assertEqual(sorted(s.semilla for s in e.proyecto.sonidos), [0, 1])

    def test_renombrar_valida_antes_y_actualiza_las_escenas(self):
        from PySide6.QtWidgets import QMessageBox
        from celular_natural.motor import proyecto_audio as PA
        e = self.abrir_voz()
        copia = self.mi_sonido(e, "pajaros.m4a")
        e.agregar_fondo("archivo", copia.name)
        e.ir_a(1.0)
        e.agregar_sonido("archivo", copia.name)
        self.assertTrue(e.guardar_como_escena("Con mis pájaros"))
        try:
            # Un nombre que no sirve: avisa sin cortar lo que suena (ni soltar los archivos).
            with mock.patch.object(e, "_soltar_archivos") as soltar, \
                    mock.patch.object(QMessageBox, "warning") as aviso:
                self.assertFalse(e.renombrar_mi_sonido(copia.name, "a/b"))
                soltar.assert_not_called()
                aviso.assert_called_once()
            self.assertTrue(e.renombrar_mi_sonido(copia.name, "pajaros en el patio"))
            escena = PA.escenas_propias()["Con mis pájaros"]
            self.assertEqual(escena.fondos[0].clave, "pajaros en el patio.m4a")
            self.assertEqual(escena.sonidos[0][0], "pajaros en el patio.m4a")
            self.assertEqual(escena.sonidos[0][3], "archivo")
            self.assertEqual(e.proyecto.sonidos[0].clave, "pajaros en el patio.m4a")
        finally:
            PA.borrar_escena("Con mis pájaros")

    def test_falta_se_actualiza_cuando_vuelve_el_archivo(self):
        from celular_natural.motor import proyecto_audio as PA
        e = self.abrir_voz()
        copia = self.mi_sonido(e, "perro ladrando.m4a")
        e.ir_a(1.0)
        e.agregar_sonido("archivo", copia.name)
        e._poner_faltan_mezcla((copia.name,))  # como si el mezclador no lo hubiera podido usar
        self.assertTrue(e.pista_sonidos.bloques[0].falta)
        copia.unlink()  # se borró por fuera…
        self.mi_sonido(e, "perro ladrando.m4a")  # …y se vuelve a agregar, con el mismo nombre
        self.assertTrue((PA.carpeta_sonidos() / copia.name).exists())
        self.assertFalse(e.pista_sonidos.bloques[0].falta)
        self.assertFalse(e.filas_sonidos[0].falta.isVisibleTo(e.filas_sonidos[0]))

    def test_volver_no_avisa_si_mientras_tanto_se_abrio_otro_audio(self):
        import threading
        from celular_natural.ui import modo_audio as M
        e = self.abrir_voz()
        self.assertTrue(e.abrir_desde_video(str(self.voz), str(self.dir / "clip de antes.mp4")))
        liberar = threading.Event()

        def lenta(_p, ruta, _formato, _progreso, _cancelado):
            while not liberar.is_set():
                time.sleep(0.01)
            Path(ruta).write_bytes(b"RIFF")

        pedidos = []
        e.volverAlVideoPedido.connect(lambda wav, vid: pedidos.append((wav, vid)))
        with mock.patch.object(M.pa, "exportar_proyecto", side_effect=lenta):
            self.assertTrue(e.volver_al_video())
            self.assertTrue(e.abrir(str(self.voz2)))
            liberar.set()
            self.esperar(lambda: not e.volviendo)
        self.assertEqual(pedidos, [])
        carpeta = Path(os.environ["APPDATA"]) / "NaturalShot PRO" / "temporal"
        self.assertEqual(list(carpeta.glob("clip de antes*")), [])  # el WAV que ya no iba a ningún lado, no queda
        self.assertIn("abriste otro audio", e.etiqueta_estado.text())

    # ------------------------------------------------------------ exportar
    def test_exportar_a_whatsapp(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        e = self.abrir_voz()
        e.aplicar_escena("nota_calle")
        e.botones_formato["whatsapp"].click()
        destino = self.dir / "nota de voz.ogg"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "")) as dialogo, \
                mock.patch.object(QMessageBox, "information") as cuadro:
            e.boton_exportar.click()
            self.assertTrue(e.exportando)
            self.assertTrue(dialogo.call_args[0][2].endswith(".ogg"))
            self.esperar(lambda: not e.exportando, 120)
            cuadro.assert_called_once()  # en Audio, el aviso es un cuadro
        self.assertTrue(destino.exists())
        with av.open(str(destino)) as c:
            self.assertEqual(c.format.name, "ogg")
            sa = c.streams.audio[0]
            self.assertEqual(sa.codec_context.name, "opus")
            self.assertEqual(sa.codec_context.channels, 1)
            # Opus se puede codificar a 16 kHz y decodificar a 48: se mide con la frecuencia de cada cuadro.
            segundos = sum(cuadro.samples / cuadro.sample_rate for cuadro in c.decode(sa))
        self.assertAlmostEqual(segundos, 4.0, delta=0.1)
        self.assertEqual(e.ultima_exportacion.canales, 1)
        self.assertFalse([p for p in self.dir.iterdir() if ".parcial" in p.name])

    def test_la_exportacion_sigue_al_cambiar_de_modo(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from celular_natural.motor import Cancelado
        from celular_natural.ui import modo_audio as M
        from celular_natural.ui.modo_facil import AUDIO, EDITOR, FACIL
        v = self.v
        e = self.abrir_voz()
        e.botones_formato["m4a"].click()
        destino = self.dir / "en fotos.m4a"
        # Una exportación que solo termina si la cancelan (no depende de la velocidad de la PC).
        def lenta(_p, _ruta, _formato, progreso, cancelado):
            hechas = 0
            while not cancelado():
                hechas = min(hechas + 1000, 99_000)
                progreso(hechas, 100_000, None)
                time.sleep(0.02)
            raise Cancelado()

        with mock.patch.object(M.pa, "exportar_proyecto", side_effect=lenta), \
                mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "")):
            e.exportar()
            self.assertTrue(e.exportando)
            self.assertFalse(v.chip_audio.isVisible())  # en Audio se ve el progreso del editor
            v.establecer_modo(FACIL)
            self.assertTrue(e.exportando)
            self.assertTrue(v.chip_audio.isVisible())
            self.assertTrue(v.exportando_algo())
            self.esperar(lambda: v.chip_audio.porcentaje > 0)
            self.assertRegex(v.chip_audio.texto.text(), r"Exportando audio · \d+ %")
            v.chip_audio.clicked.emit()  # tocar el chip lleva a Audio
            self.assertEqual(v.modo, AUDIO)
            self.assertFalse(v.chip_audio.isVisible())
            e.boton_cancelar.click()
            self.esperar(lambda: not e.exportando)
        self.assertFalse(destino.exists())
        self.assertIn("cancelada", e.etiqueta_estado.text())
        # Una de verdad, terminando mientras se está en las fotos: un aviso que no interrumpe.
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "")), \
                mock.patch.object(QMessageBox, "information") as cuadro:
            e.exportar()
            v.establecer_modo(EDITOR)
            self.esperar(lambda: not e.exportando, 120)
            cuadro.assert_not_called()
        self.assertTrue(destino.exists())
        self.assertFalse(v.chip_audio.isVisible())
        self.assertIn("Listo: se exportó el audio en fotos.m4a", v.aviso.texto.text())
        # Cerrar con una exportación de audio en curso pregunta.
        with mock.patch.object(M.pa, "exportar_proyecto", side_effect=lenta), \
                mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(self.dir / "x.m4a"), "")):
            v.establecer_modo(AUDIO)
            e.exportar()
            with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.No) as pregunta:
                v.close()
                pregunta.assert_called_once()
            self.assertTrue(v.isVisible())
            self.cerrar(v)
            self.assertFalse(e.exportando)
        self.assertFalse((self.dir / "x.m4a").exists())

    # ------------------------------------------------------------ escuchar
    def test_sin_salida_de_sonido_anda_igual(self):
        e = self.abrir_voz()
        self.assertFalse(e.reproductor.disponible)
        self.assertFalse(e.boton_sonido.isEnabled())
        e.aplicar_escena("video_playa")
        e.ir_a(1.0)
        self.atajo(e, "Space").trigger()
        self.assertTrue(e.reproduciendo)
        self.pausa(0.3)
        self.assertGreater(e.tiempo, 1.1)
        # Cambiar cosas mientras "suena" no rompe nada.
        e.panel_volumen.volumen.slider.setValue(80)
        e.cortar()
        e.ir_a(0.5)
        self.pausa(0.15)
        self.atajo(e, "Space").trigger()
        self.assertFalse(e.reproduciendo)
        # Hasta el final: se detiene solo.
        e.ir_a(3.8)
        e.reproducir()
        self.esperar(lambda: not e.reproduciendo, 5)
        self.assertAlmostEqual(e.tiempo_resultado, e.mapa.duracion, delta=0.01)

    def test_con_salida_falsa_suena_el_mezclador(self):
        from test_sonido_ui import con_salida_falsa
        from celular_natural.motor.proyecto_audio import MezcladorAudio
        falso, parches = con_salida_falsa()
        with parches[0], parches[1]:
            v = self.nueva_ventana()
            e = self.abrir_voz(v)
            self.assertTrue(e.reproductor.disponible)
            e.aplicar_escena("nota_calle")
            e.ir_a(0.5)
            e.reproducir()
            # El mezclador se arma en otro hilo; cuando está, suena desde el cursor de ese momento.
            self.esperar(lambda: isinstance(e.reproductor.lector, MezcladorAudio), 20)
            lector = e.reproductor.lector
            e.pausar()
            e.ir_a(0.5)
            e.reproducir()
            self.esperar(lambda: isinstance(e.reproductor.lector, MezcladorAudio)
                         and e.reproductor.lector is not lector, 20)
            lector = e.reproductor.lector
            sink = falso.QAudioSink.creados[-1]
            # Que el hilo del mezclador haya llenado al menos 0,25 s del búfer del sink (con la PC cargada tarda más).
            self.esperar(lambda: sink.en_bufer >= int(0.25 * SR) * 4, 20)
            inicio = e.reproductor.posicion()
            sink.avanzar(0.25)
            self.pausa(0.05)
            self.assertAlmostEqual(e.tiempo, inicio + 0.25, delta=0.03)  # el cursor sigue al sonido
            arranques = sink.arranques
            # Un cambio que no toca los tramos: el mismo mezclador, sin cortar (se aplica en otro hilo).
            e.panel_volumen.volumen.slider.setValue(70)
            e.agregar_fondo("generado", "viento")
            self.assertIs(e.reproductor.lector, lector)
            self.esperar(lambda: lector.proyecto == e.proyecto, 20)
            self.assertEqual(sink.arranques, arranques)
            # Comparar "Antes": la voz sola, también sin cortar.
            e.boton_antes.click()
            self.esperar(lambda: lector.proyecto.fondos == (), 20)
            e.boton_despues.click()
            self.esperar(lambda: lector.proyecto == e.proyecto, 20)
            # Un corte solo (sin borrar nada) no cambia lo que suena; recortar el principio (I), sí: se
            # arma de nuevo desde el cursor (y mientras se arma sigue sonando lo de antes).
            e.cortar()
            self.pausa(0.1)
            self.assertEqual(sink.arranques, arranques)
            self.assertIs(e.reproductor.lector, lector)
            e.marcar_entrada()
            self.esperar(lambda: sink.arranques == arranques + 1, 20)
            self.assertIsNot(e.reproductor.lector, lector)
            e.pausar()
            self.assertIsNone(e.reproductor.lector)

    def test_cambiar_mientras_suena_no_traba_la_interfaz(self):
        """Sumar un sonido que tarda en prepararse mientras suena: la interfaz responde enseguida y
        lo de antes sigue sonando hasta que lo nuevo está (sin cortar)."""
        from test_sonido_ui import con_salida_falsa
        from celular_natural.motor import ambientes
        from celular_natural.motor.proyecto_audio import MezcladorAudio
        falso, parches = con_salida_falsa()
        original = ambientes.generar_sonido

        def lento(*a, **k):  # como un sonido que no está en la caché y tarda en sintetizarse
            time.sleep(0.6)
            return original(*a, **k)

        with parches[0], parches[1]:
            v = self.nueva_ventana()
            e = self.abrir_voz(v)
            e.reproducir()
            self.esperar(lambda: isinstance(e.reproductor.lector, MezcladorAudio), 20)
            lector, sink = e.reproductor.lector, falso.QAudioSink.creados[-1]
            arranques = sink.arranques
            with mock.patch.object(ambientes, "generar_sonido", side_effect=lento):
                antes = time.perf_counter()
                self.assertTrue(e.agregar_sonido("generado", "sirena_lejos", ancla=0.2))
                tardo = time.perf_counter() - antes
                self.assertLess(tardo, 0.3, f"la interfaz se trabó {tardo:.2f} s")
                self.assertIs(e.reproductor.lector, lector)   # sigue sonando lo de antes
                self.esperar(lambda: lector.proyecto == e.proyecto, 30)
            self.assertEqual(sink.arranques, arranques)       # sin cortar
            e.pausar()

    def test_si_no_se_puede_armar_lo_que_suena_avisa(self):
        """Con salida de sonido, si la voz ya no está: se pausa y se avisa (no sigue como si sonara)."""
        from test_sonido_ui import con_salida_falsa
        falso, parches = con_salida_falsa()
        copia = self.dir / "voz que se va.wav"
        shutil.copy(self.voz, copia)
        with parches[0], parches[1]:
            v = self.nueva_ventana()
            e = self.abrir_voz(v, copia)
            copia.unlink()
            e.reproducir()
            self.esperar(lambda: not e.reproduciendo, 20)
            self.assertIn("No se pudo escuchar", e.etiqueta_estado.text())
            self.assertIsNone(e.reproductor.lector)

    def test_escuchar_3_s_se_corta_al_cambiar_de_modo(self):
        from test_sonido_ui import con_salida_falsa
        from celular_natural.motor.proyecto_audio import FondoProyecto
        from celular_natural.ui.modo_audio import LectorArreglo
        from celular_natural.ui.modo_facil import AUDIO, FACIL
        falso, parches = con_salida_falsa()
        with parches[0], parches[1]:
            v = self.nueva_ventana()
            e = self.abrir_voz(v)
            e.escuchar_fondo(FondoProyecto("generado", "lluvia"))
            self.esperar(lambda: isinstance(e.reproductor.lector, LectorArreglo), 20)
            v.establecer_modo(FACIL)  # cambiar de modo lo corta
            self.assertIsNone(e.reproductor.lector)
            v.establecer_modo(AUDIO)
            e.escuchar_fondo(FondoProyecto("generado", "olas"))
            self.esperar(lambda: isinstance(e.reproductor.lector, LectorArreglo), 20)
            e.cargar_proyecto(e.proyecto)  # abrir otro audio (o el mismo de nuevo), también
            self.assertIsNone(e.reproductor.lector)

    # ------------------------------------------------------------ ida y vuelta con Video
    def test_abrir_desde_video_bloquea_los_cortes(self):
        from celular_natural.ui.modo_facil import AUDIO
        v = self.v
        v.establecer_modo(AUDIO)
        e = v.editor_audio
        self.assertFalse(e.franja_video.isVisible())
        video = self.dir / "charla.mp4"   # solo el nombre: el video no hace falta para esto
        self.assertTrue(e.abrir_desde_video(str(self.voz), str(video)))
        self.esperar(lambda: not e.cargador_onda.cargando)
        self.assertEqual(e.proyecto.video_origen, str(video))
        self.assertTrue(e.cortes_bloqueados)
        self.assertTrue(e.franja_video.isVisible())
        self.assertIn("Sonido del video charla.mp4", e.texto_franja_video.text())
        # Ni los botones ni los atajos cortan.
        for b in (e.boton_entrada, e.boton_salida, e.boton_cortar, e.boton_borrar):
            self.assertFalse(b.isEnabled())
        self.assertIn("hacelo en el video", e.boton_cortar.toolTip())
        e.ir_a(1.0)
        for tecla in ("S", "I", "O", "Del", "R"):
            self.atajo(e, tecla).trigger()
        e.linea.limitesPedidos.emit(0.5, None)  # el corchete arrastrado, tampoco
        self.assertEqual(e.proyecto.tramos, ((0.0, 4.0),))
        self.assertEqual(len(e.historial), 1)
        self.assertIn("hacelo en el video", e.etiqueta_estado.text())
        # Lo demás sí: escena, fondo, silenciar tramo (M).
        e.aplicar_escena("video_casa")
        e.agregar_fondo("generado", "viento")
        self.atajo(e, "M").trigger()
        self.assertEqual(e.proyecto.sonido.silencios, ((0.0, 4.0),))
        self.assertEqual(e.proyecto.video_origen, str(video))
        # Deshacer y rehacer (y el historial) siguen con el bloqueo.
        e.deshacer()
        self.assertTrue(e.cortes_bloqueados)
        e.rehacer()
        # Abrir un audio común saca el bloqueo y la franja.
        from PySide6.QtWidgets import QMessageBox
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes) as pregunta:
            self.assertTrue(e.abrir(str(self.voz2)))  # tenía cambios: pregunta
            pregunta.assert_called_once()
        self.assertFalse(e.cortes_bloqueados)
        self.assertFalse(e.franja_video.isVisible())
        self.assertTrue(e.boton_cortar.isEnabled())
        e.ir_a(1.0)
        self.atajo(e, "S").trigger()
        self.assertEqual(len(e.edicion.segmentos), 2)

    def test_volver_al_video_exporta_un_wav(self):
        import celular_natural.motor.audio as A
        e = self.abrir_voz()
        video = self.dir / "paseo.mp4"
        self.assertTrue(e.abrir_desde_video(str(self.voz), str(video)))
        e.aplicar_escena("video_playa")
        pedidos = []
        e.volverAlVideoPedido.connect(lambda wav, vid: pedidos.append((wav, vid)))
        e.boton_volver_al_video.click()
        self.assertTrue(e.volviendo)
        self.assertTrue(e.barra_volver.isVisible())
        self.esperar(lambda: not e.volviendo, 60)
        self.assertEqual(len(pedidos), 1)
        wav, vid = pedidos[0]
        self.assertEqual(vid, str(video))
        carpeta = Path(os.environ["APPDATA"]) / "NaturalShot PRO" / "temporal"
        self.assertEqual(Path(wav).parent, carpeta)
        self.assertEqual(Path(wav).suffix, ".wav")
        info = A.info_medio(wav)
        self.assertTrue(info.tiene_audio)
        self.assertAlmostEqual(info.duracion, 4.0, delta=0.05)
        # Otra vez: otro nombre (no pisa el anterior). Cancelada: no emite ni deja archivo.
        from celular_natural.motor import Cancelado
        from celular_natural.ui import modo_audio as M
        antes = set(carpeta.iterdir())

        def lenta(_p, ruta, _formato, progreso, cancelado):
            while not cancelado():
                progreso(1, 2, None)
                time.sleep(0.02)
            raise Cancelado()

        with mock.patch.object(M.pa, "exportar_proyecto", side_effect=lenta):
            self.assertTrue(e.volver_al_video())
            self.pausa(0.1)
            e.boton_cancelar_volver.click()
            self.esperar(lambda: not e.volviendo)
        self.assertEqual(len(pedidos), 1)
        self.assertEqual(set(carpeta.iterdir()), antes)
        self.assertIn("Se canceló", e.etiqueta_estado.text())
        # Sin video de origen no hay nada que volver.
        e.cerrar_audio(confirmar=False)
        self.abrir_voz()
        self.assertFalse(e.volver_al_video())

    # ------------------------------------------------------------ sesión
    def test_quitar_todas_mientras_se_lee_la_sesion_no_pierde_el_audio(self):
        """"Quitar todas las fotos" mientras la sesión todavía se lee: las fotos de antes no vuelven,
        pero el proyecto del modo Audio no es una foto y no se pierde (ni del disco)."""
        from celular_natural import sesion
        from celular_natural.motor.proyecto_audio import abrir_proyecto
        sesion.borrar()
        try:
            p = abrir_proyecto(str(self.voz))
            sesion.guardar(sesion.SesionGuardada(
                [sesion.FotoGuardada(str(self.foto))], 0,
                sesion.AudioGuardado({"proyecto": p, "tiempo": 0.0}, None, 0)))
            v = self.nueva_ventana()
            v.agregar_fotos([str(foto(self.dir / "otra.png", 2))])  # una foto abierta antes de que llegue la sesión
            v.activar_sesion()
            self.assertTrue(v.quitar_todas_las_fotos(confirmar=False))  # la lectura todavía no se procesó
            self.esperar(lambda: v._audio_pendiente is not None)
            self.assertEqual(v._fotos, [])
            self.assertTrue(v.boton_modo_audio.punto)
            v.guardar_sesion(esperar=True)
            guardada, _problema = sesion.cargar()
            self.assertEqual(guardada.fotos, [])
            self.assertEqual(guardada.audio.estado["proyecto"], p)
        finally:
            sesion.borrar()

    def test_la_sesion_recuerda_el_proyecto(self):
        from celular_natural import sesion
        from celular_natural.ui.modo_facil import AUDIO, FACIL
        sesion.borrar()
        v = self.v
        v.activar_sesion()
        self.esperar(lambda: v.sesion_restaurada)
        e = self.abrir_voz()
        e.aplicar_escena("nota_lluvia")
        e.ir_a(1.0)
        e.cortar()
        e.ir_a(1.5)
        historial, pos, proyecto, edicion = e.historial, e.posicion_historial, e.proyecto, e.edicion
        e.deshacer()  # que la posición no sea el final
        pos -= 1
        proyecto, edicion = e.proyecto, e.edicion
        v.establecer_modo(FACIL)
        self.cerrar(v)
        self.assertTrue(sesion.archivo_sesion().exists())
        # Otra ventana: el audio espera a que se entre a Audio (sin cargar nada antes).
        otra = self.nueva_ventana()
        otra.activar_sesion()
        self.esperar(lambda: otra.sesion_restaurada)
        self.assertEqual(otra.modo, FACIL)
        self.assertIsNone(otra.editor_audio)
        self.assertTrue(otra.boton_modo_audio.punto)
        otra.establecer_modo(AUDIO)
        e2 = otra.editor_audio
        self.assertEqual(e2.proyecto, proyecto)
        self.assertEqual(e2.edicion, edicion)
        self.assertEqual(len(e2.historial), len(historial))
        self.assertEqual(e2.posicion_historial, pos)
        self.assertEqual([d for d, _p, _e in e2.historial], [d for d, _p, _e in historial])
        self.assertAlmostEqual(e2.tiempo, 1.5, places=6)
        e2.rehacer()
        self.assertEqual(len(e2.edicion.segmentos), 2)  # el corte volvió con rehacer
        otra.establecer_modo(FACIL)  # si se cerrara en Audio, la próxima abriría en Audio (sin el punto)
        self.cerrar(otra)
        # Si la voz ya no está: el aviso de siempre y no hay proyecto.
        try:
            tercera = self.nueva_ventana()
            tercera.activar_sesion()
            self.esperar(lambda: tercera.sesion_restaurada)
            self.assertTrue(tercera.boton_modo_audio.punto)
            self.cerrar(tercera)
            guardada, _ = sesion.cargar()
            estado = dict(guardada.audio.estado)
            estado["proyecto"] = estado["proyecto"].con(ruta=str(self.dir / "no existe.wav"))
            sesion.guardar(sesion.SesionGuardada([], -1, sesion.AudioGuardado(estado, None, 0)))
            cuarta = self.nueva_ventana()
            cuarta.activar_sesion()
            self.esperar(lambda: cuarta.sesion_restaurada)
            self.assertTrue(cuarta.aviso.mostrado)
            self.assertIn("El audio de la sesión anterior ya no está", cuarta.aviso.texto.text())
            self.assertFalse(cuarta.boton_modo_audio.punto)
            cuarta.establecer_modo(AUDIO)
            self.assertIsNone(cuarta.editor_audio.proyecto)
        finally:
            sesion.borrar()


if __name__ == "__main__":
    unittest.main()
