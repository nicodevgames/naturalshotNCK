"""Pruebas de la interfaz del sonido en el modo Video.

* Piezas sueltas (``ui/forma_onda.py``, ``ui/reproductor_audio.py``): la pista
  dibuja la onda, los silencios y lo que no se exporta; el cargador entrega
  partes mientras lee; el reproductor sigue al sonido, termina, se recupera si el
  dispositivo falla y, sin salida de sonido o sin QtMultimedia, no hace nada.
* La ventana real (modo sin pantalla): pista con forma de onda (y "Sin sonido"),
  Silenciar tramo (M) que alterna, tarjeta Sonido (volumen, normalizar,
  fundidos limitados a la mitad del resultado, quitar), deshacer y rehacer de
  cortes y sonido juntos, exportar sin sonido o con un silencio, guardar solo el
  audio (WAV, M4A y cancelar), la vista previa que suena (con un QtMultimedia de
  mentira: la imagen sigue al sonido) y su botón de silenciar que se recuerda.

En modo sin pantalla el reproductor no usa la salida de sonido (así las pruebas no
suenan). Para probar la salida de verdad hay una prueba con el volumen del
dispositivo en 0, que se saltea si la PC no tiene salida de sonido. Los medios se
generan en una carpeta temporal; para esperar se usa ``time.sleep`` y
``processEvents`` (``QTest.qWait`` no suelta el GIL).
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import types
import unittest
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

if av is not None:
    from test_audio import generar, leer_audio, tono  # noqa: E402
    from test_video import generar_video  # noqa: E402
    from celular_natural.motor import audio as A  # noqa: E402

SR = 48000


def _app():
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication
    from celular_natural.ui.estilo import HOJA_ESTILO
    app = QApplication.instance() or QApplication([])
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    if app.styleSheet() != HOJA_ESTILO:
        app.setStyleSheet(HOJA_ESTILO)
    return app


def esperar(app, condicion, segundos: float = 60.0) -> bool:
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        app.processEvents()
        if condicion():
            return True
        time.sleep(0.01)
    return condicion()


def pausa(app, segundos: float) -> None:
    esperar(app, lambda: False, segundos)


# ---------------------------------------------------------------------------
# Un QtMultimedia de mentira: un sink que "toma" lo escrito cuando la prueba avanza el reloj
# ---------------------------------------------------------------------------

class _Nombre:
    def __init__(self, nombre: str):
        self.name = nombre


class _Dispositivo:
    def isNull(self):
        return False

    def id(self):
        return b"falso"

    def description(self):
        return "Parlantes de prueba"

    def isFormatSupported(self, _formato):
        return True


class _Formato:
    class SampleFormat:
        Int16 = "Int16"

    def setSampleRate(self, _v):
        pass

    def setChannelCount(self, _v):
        pass

    def setSampleFormat(self, _v):
        pass


class _Salida:
    """El QIODevice que devuelve ``start()``: acepta hasta lo que hay libre en el búfer."""

    def __init__(self, sink):
        self._sink = sink

    def write(self, datos) -> int:
        n = min(len(datos), self._sink.bytesFree())
        self._sink.en_bufer += n
        self._sink.escritos += n
        if n:
            self._sink.estado = "ActiveState"
        return n


class _Sink:
    creados: list = []

    def __init__(self, _dispositivo, _formato, _padre=None):
        self.tam = 0
        self.en_bufer = 0
        self.escritos = 0
        self.procesado = 0.0  # segundos que "tomó el dispositivo" desde start()
        self.estado = "StoppedState"
        self.falla = "NoError"
        self.volumen = 1.0
        self.arranques = 0
        _Sink.creados.append(self)

    # API que usa el reproductor
    def setBufferSize(self, n):
        self.tam = n

    def bufferSize(self):
        return self.tam

    def setVolume(self, v):
        self.volumen = v

    def start(self):
        self.en_bufer, self.procesado, self.estado = 0, 0.0, "ActiveState"
        self.arranques += 1
        return _Salida(self)

    def stop(self):
        self.estado = "StoppedState"

    def bytesFree(self):
        return self.tam - self.en_bufer

    def processedUSecs(self):
        return int(self.procesado * 1e6)

    def state(self):
        return _Nombre(self.estado)

    def error(self):
        return _Nombre(self.falla)

    def deleteLater(self):
        pass

    # para la prueba: el dispositivo consume ``segundos`` de lo escrito
    def avanzar(self, segundos: float) -> None:
        n = min(self.en_bufer, int(round(segundos * SR)) * 4)
        self.en_bufer -= n
        self.procesado += n / 4 / SR
        if self.en_bufer == 0:
            self.estado = "IdleState"


def qtmultimedia_falso():
    _Sink.creados = []
    return types.SimpleNamespace(
        QAudioFormat=_Formato,
        QMediaDevices=types.SimpleNamespace(defaultAudioOutput=lambda: _Dispositivo()),
        QAudioSink=_Sink,
    )


def con_salida_falsa():
    """Contexto: el reproductor usa el QtMultimedia de mentira (también en modo sin pantalla)."""
    from celular_natural.ui import reproductor_audio as R
    falso = qtmultimedia_falso()
    return falso, (mock.patch.object(R, "_cargar_qtmultimedia", return_value=falso),
                   mock.patch.dict(os.environ, {R.VARIABLE_OFFSCREEN: "1"}))


# ---------------------------------------------------------------------------
# Piezas sueltas
# ---------------------------------------------------------------------------

@unittest.skipIf(av is None, "Falta PyAV (pip install av==19.0.1)")
class PruebasPiezas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        cls.dir = Path(tempfile.mkdtemp(prefix="naturalshot_sonido_ui_"))
        # 1 s de 440 Hz, 1 s de silencio y 1 s de 880 Hz (al 0,3).
        cls.video = generar_video(cls.dir / "clip.mp4")

    @classmethod
    def tearDownClass(cls):
        from celular_natural.motor import video as V
        V.cerrar_lectores()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_pico_aproximado(self):
        from celular_natural.ui.forma_onda import pico_aproximado
        forma = A.forma_de_onda(self.video, 4000)
        exacto = A.medir_pico(self.video)
        self.assertAlmostEqual(pico_aproximado(forma), exacto, delta=0.01)
        # Solo el segundo silencioso del original: casi nada.
        self.assertLess(pico_aproximado(forma, [(1.05, 1.95)]), 0.02)
        # Un silencio sobre el tono de 440: queda el de 880 (los dos al 0,3).
        self.assertAlmostEqual(pico_aproximado(forma, None, [(0.0, 1.0)]), 0.3, delta=0.02)
        # Incompleta: todavía no se puede estimar.
        parcial = A.FormaOnda(forma.duracion, forma.minimos, forma.maximos, 10)
        self.assertIsNone(pico_aproximado(parcial))

    def test_pista_dibuja_onda_silencios_y_lo_que_no_se_exporta(self):
        from PySide6.QtGui import QColor
        from celular_natural.ui.forma_onda import PistaOnda
        n = 4000
        forma = A.FormaOnda(4.0, np.full(n, -0.6, np.float32), np.full(n, 0.6, np.float32), n)
        pista = PistaOnda()
        pista.resize(14 * 2 + 400, 46)  # 100 px por segundo
        pista.establecer_forma(forma)
        self.assertEqual(pista.estado, "lista")
        ajustes = A.AjustesAudio(silencios=((1.0, 2.0),))
        pista.establecer_edicion([(0.0, 3.0)], ajustes)  # de 3 a 4 s no se exporta
        img = pista.grab().toImage()

        def color(x, y=23):
            return QColor(img.pixel(14 + x, y))

        # Carril de 38 px (medio en y = 23): la onda al 0,6 va de y = 12,8 a 33,2.
        activa, silencio, fuera = color(50, 18), color(108, 18), color(350, 18)
        # Activa: la onda en el degradado de la app (más roja/violeta que verde).
        self.assertGreater(activa.red() + activa.blue(), 2 * activa.green() + 120)
        # Silencio: sin onda (la franja rosa tenue) y la onda apagada fuera de lo que se exporta.
        self.assertLess(silencio.red() + silencio.blue(), activa.red() + activa.blue() - 150)
        self.assertGreater(silencio.red(), silencio.green())
        self.assertLess(fuera.red() + fuera.blue(), activa.red() + activa.blue() - 150)
        # Volumen al 50 %: la onda se achica.
        pista.establecer_edicion(None, A.AjustesAudio(volumen=0.5))
        img = pista.grab().toImage()
        self.assertLess(QColor(img.pixel(14 + 50, 15)).red(), 120)   # al 0,3 va de y = 17,9 a 28,1
        self.assertGreater(QColor(img.pixel(14 + 50, 20)).red(), 120)
        # Sin sonido y vacía: no rompe.
        pista.sin_sonido(4.0)
        self.assertEqual(pista.estado, "sin_sonido")
        pista.grab()
        pista.vaciar()
        pista.grab()
        # Tocar la pista pide ese instante.
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication
        pista.establecer_forma(forma)
        pedidos = []
        pista.tiempoPedido.connect(lambda t, arrastrando: pedidos.append((round(t, 2), arrastrando)))
        for tipo in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            QApplication.sendEvent(pista, QMouseEvent(tipo, QPointF(14 + 250, 20), QPointF(14 + 250, 20),
                                                      Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
        self.assertEqual(pedidos, [(2.5, True), (2.5, False)])

    def test_cargador_entrega_partes_mientras_lee(self):
        from celular_natural.ui import forma_onda as F
        ruta = generar(self.dir / "largo.mkv", tono(6.0, 440.0, 0.25))
        cargador = F.CargadorOnda()
        parciales, listas = [], []
        cargador.parcial.connect(parciales.append)
        cargador.lista.connect(listas.append)
        with mock.patch.object(F, "INTERVALO_PARCIAL", 0.0):  # una entrega por cada paquete leído
            cargador.cargar(str(ruta))
            self.assertTrue(esperar(self.app, lambda: bool(listas), 30))
        self.assertTrue(parciales)
        self.assertTrue(all(not p.completa for p in parciales))
        self.assertEqual(sorted(p.listas for p in parciales), [p.listas for p in parciales])
        forma = listas[0]
        self.assertTrue(forma.completa)
        self.assertEqual(forma.columnas, F.COLUMNAS_ONDA)
        self.assertAlmostEqual(float(forma.picos().max()), 0.25, delta=0.02)
        self.assertIs(cargador.forma, forma)
        # Sin sonido: lista con None.
        mudo = generar(self.dir / "mudo.mp4", None, segundos=0.5)
        listas.clear()
        cargador.cargar(str(mudo))
        self.assertTrue(esperar(self.app, lambda: bool(listas), 30))
        self.assertIsNone(listas[0])
        cargador.detener()

    def test_reproductor_sin_salida_no_hace_nada(self):
        from celular_natural.ui import reproductor_audio as R
        # Sin pantalla (las pruebas): no usa el dispositivo.
        r = R.ReproductorAudio()
        self.assertFalse(r.disponible)
        self.assertIn("Sin pantalla", r.motivo)
        self.assertFalse(r.reproducir(str(self.video), None, A.AjustesAudio(), 0.0))
        self.assertIsNone(r.posicion())
        r.cambiar_ajustes(A.AjustesAudio(volumen=0.5))
        self.assertFalse(r.ir_a(1.0))
        r.cerrar()
        # QtMultimedia que no carga.
        with mock.patch.object(R, "_cargar_qtmultimedia", side_effect=ImportError("sin QtMultimedia")), \
                mock.patch.dict(os.environ, {R.VARIABLE_OFFSCREEN: "1"}):
            r = R.ReproductorAudio()
        self.assertFalse(r.disponible)
        self.assertIn("No se pudo usar el sonido de Qt", r.motivo)
        self.assertFalse(r.reproducir(str(self.video), None, A.AjustesAudio(), 0.0))
        r.cerrar()
        # Sin dispositivo de salida.
        falso = qtmultimedia_falso()
        nulo = types.SimpleNamespace(isNull=lambda: True)
        falso.QMediaDevices = types.SimpleNamespace(defaultAudioOutput=lambda: nulo)
        with mock.patch.object(R, "_cargar_qtmultimedia", return_value=falso), \
                mock.patch.dict(os.environ, {R.VARIABLE_OFFSCREEN: "1"}):
            r = R.ReproductorAudio()
            self.assertFalse(r.disponible)
            self.assertIn("No hay ninguna salida de sonido", r.motivo)
            self.assertFalse(r.reproducir(str(self.video), None, A.AjustesAudio(), 0.0))
            r.cerrar()

    def test_reproductor_sigue_al_sonido(self):
        from celular_natural.ui import reproductor_audio as R
        falso, parches = con_salida_falsa()
        with parches[0], parches[1]:
            r = R.ReproductorAudio()
            self.assertTrue(r.disponible)
            terminado, fallas = [], []
            r.terminado.connect(lambda: terminado.append(True))
            r.fallo.connect(fallas.append)
            # Se conserva de 0 a 1 y de 2 a 3: desde 0,5 suena 0,5 s y salta a 2.
            self.assertTrue(r.reproducir(str(self.video), [(0.0, 1.0), (2.0, 3.0)], A.AjustesAudio(), 0.5))
            sink = _Sink.creados[-1]
            self.assertEqual(sink.tam, int(R.BUFER * SR) * 4)
            self.assertEqual(sink.escritos, sink.tam)  # el búfer se llena al arrancar
            self.assertAlmostEqual(r.posicion(), 0.5, places=3)
            sink.avanzar(0.3)
            self.assertAlmostEqual(r.posicion(), 0.8, places=3)
            r._alimentar()  # vuelve a llenar el búfer
            sink.avanzar(0.29)
            self.assertAlmostEqual(r.posicion(), 2.09, places=3)  # lo borrado no suena
            # Saltar descarta el búfer y arranca de nuevo desde ahí.
            self.assertTrue(r.ir_a(2.5))
            self.assertEqual(sink.arranques, 2)
            self.assertAlmostEqual(r.posicion(), 2.5, places=3)
            # Hasta el final: se vacía el búfer, termina y se detiene.
            for _ in range(10):
                sink.avanzar(0.1)
                r._alimentar()
            self.assertEqual(terminado, [True])
            self.assertFalse(r.sonando)
            self.assertIsNone(r.posicion())
            # Silenciado: no suena.
            r.establecer_silenciado(True)
            self.assertFalse(r.reproducir(str(self.video), None, A.AjustesAudio(), 0.0))
            r.establecer_silenciado(False)
            # Sonido quitado: tampoco.
            self.assertFalse(r.reproducir(str(self.video), None, A.AjustesAudio(quitar=True), 0.0))
            # El dispositivo falla a mitad: se detiene, avisa y en el próximo arranca otro sink.
            self.assertTrue(r.reproducir(str(self.video), None, A.AjustesAudio(), 0.0))
            sink = _Sink.creados[-1]
            sink.estado, sink.falla = "StoppedState", "FatalError"
            r._alimentar()
            self.assertEqual(len(fallas), 1)
            self.assertFalse(r.sonando)
            self.assertTrue(r.reproducir(str(self.video), None, A.AjustesAudio(), 0.0))
            self.assertIsNot(_Sink.creados[-1], sink)
            # Normalizar sin el pico: suena igual (no se traba midiendo).
            r.cambiar_ajustes(A.AjustesAudio(normalizar=True))
            self.assertTrue(r.sonando)
            r.cerrar()

    def test_reproductor_con_la_salida_de_verdad(self):
        """La salida de sonido de la PC, con el volumen del dispositivo en 0 (no se oye nada)."""
        from celular_natural.ui import reproductor_audio as R
        with mock.patch.dict(os.environ, {R.VARIABLE_OFFSCREEN: "1"}):
            r = R.ReproductorAudio()
        if not r.disponible:
            r.cerrar()
            self.skipTest(f"sin salida de sonido: {r.motivo}")
        r.establecer_volumen_salida(0.0)
        try:
            self.assertTrue(r.reproducir(str(self.video), [(0.0, 1.0), (2.0, 3.0)], A.AjustesAudio(), 0.5))
            inicio = time.monotonic()
            pausa(self.app, 0.4)
            transcurrido = time.monotonic() - inicio
            posicion = r.posicion()
            self.assertIsNotNone(posicion)
            self.assertGreater(posicion, 0.6)
            self.assertLess(posicion, 0.5 + transcurrido + 0.05)
            pausa(self.app, 0.3)
            self.assertGreaterEqual(r.posicion(), 2.0)  # saltó lo borrado
        finally:
            r.cerrar()


# ---------------------------------------------------------------------------
# La ventana real
# ---------------------------------------------------------------------------

@unittest.skipIf(av is None, "Falta PyAV (pip install av==19.0.1)")
class PruebasVentanaSonido(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        cls.dir = Path(tempfile.mkdtemp(prefix="naturalshot_sonido_ventana_"))
        cls._entorno = {k: os.environ.get(k) for k in ("APPDATA", "NATURALSHOT_CONFIG")}
        os.environ["APPDATA"] = str(cls.dir / "appdata")
        cls.config = cls.dir / "config.ini"
        os.environ["NATURALSHOT_CONFIG"] = str(cls.config)
        cls.video = generar_video(cls.dir / "clip.mp4")  # 3 s: 440 Hz, silencio, 880 Hz
        cls.mudo = generar_video(cls.dir / "mudo.mp4", segundos=1.0, audio=False)

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
        if self.config.exists():
            self.config.unlink()
        self.ventanas = []

    def tearDown(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication, QMessageBox
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            for v in self.ventanas:
                v.close()
                v.deleteLater()
        self.app.processEvents()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def abrir(self, ruta=None):
        """Una ventana nueva en el modo Video, con ``ruta`` abierto y la forma de onda leída."""
        from celular_natural.ui.ventana import VentanaPrincipal
        v = VentanaPrincipal()
        self.ventanas.append(v)
        v.resize(1366, 768)
        v.show()
        v.activateWindow()  # los atajos (M, Ctrl+Z) andan en la ventana activa
        v.abrir_rutas([str(ruta or self.video)])
        e = v.editor_video
        e.establecer_simple(False)  # estas pruebas son del editor completo (línea de tiempo y pista de sonido)
        self.assertTrue(esperar(self.app, lambda: e.info is not None and e.cuadro_procesado_listo()))
        self.assertTrue(esperar(self.app, lambda: e.pista_sonido.estado in ("lista", "sin_sonido")))
        return v, e

    # ------------------------------------------------------------ pruebas
    def test_pista_con_forma_de_onda_y_sin_sonido(self):
        v, e = self.abrir()
        pista = e.pista_sonido
        self.assertTrue(pista.isVisible())
        self.assertEqual(pista.estado, "lista")
        self.assertEqual(pista.forma.columnas, 4000)
        self.assertAlmostEqual(float(pista.forma.picos().max()), 0.3, delta=0.02)
        # Alineada con la línea de tiempo: mismo ancho y lugar.
        self.assertEqual(pista.width(), e.linea.width())
        self.assertEqual(pista.x(), e.linea.x())
        self.assertGreater(pista.y(), e.linea.y())
        # Tocar la pista mueve el cursor y elige el tramo de ese instante.
        e.ir_a(1.0)
        e.cortar()
        e.linea.seleccionar(-1)
        pista.presionada.emit(1.5)
        pista.tiempoPedido.emit(1.5, False)
        self.assertEqual(e.linea.seleccion, 1)
        self.assertAlmostEqual(e.tiempo, 1.5, delta=1 / 24)
        # Sin texto viejo: la vista previa ya suena.
        self.assertNotIn("no reproduce", e.nota_video.text())
        # Un video sin sonido: la franja lo dice y lo de sonido queda apagado.
        e.abrir(str(self.mudo), confirmar=False)
        self.assertTrue(esperar(self.app, lambda: e.info is not None and e.info.ruta.endswith("mudo.mp4")))
        self.assertTrue(esperar(self.app, lambda: pista.estado == "sin_sonido"))
        self.assertFalse(e.boton_silenciar.isEnabled())
        self.assertFalse(e.boton_sonido.isEnabled())
        self.assertFalse(e.panel_sonido.volumen.isEnabled())
        self.assertFalse(e.panel_sonido.boton_guardar.isEnabled())
        self.assertIn("no tiene sonido", e.panel_sonido.nota_sin_audio.text())
        self.assertIn("sin sonido", e.etiqueta_estimacion.text())
        # Al cerrar el video la pista se va.
        e.cerrar_video(confirmar=False)
        self.assertFalse(pista.isVisible())

    def test_silenciar_tramo_alterna_y_va_en_tiempo_original(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        v, e = self.abrir()
        e.ir_a(1.0)
        e.cortar()
        e.ir_a(2.0)
        e.cortar()
        e.linea.seleccionar(1)
        # A 1366 px el nombre va corto ("Silenciar", "Devolver sonido"); a más ancho, completo.
        self.assertTrue(e.boton_silenciar.text().strip().startswith("Silenciar"))
        QTest.keyClick(e, Qt.Key_M)
        self.assertEqual(e.audio.silencios, ((1.0, 2.0),))
        self.assertTrue(e.boton_silenciar.text().strip().startswith("Devolver"))
        self.assertIn("Devolverle el sonido", e.boton_silenciar.toolTip())
        self.assertEqual(e.pista_sonido._ajustes.silencios, ((1.0, 2.0),))
        self.assertIn("1 tramo silenciado", e.panel_sonido.nota_silencios.text())
        # Cortar dentro del silencio no lo mueve (tiempo original).
        e.ir_a(1.5)
        e.cortar()
        self.assertEqual(e.audio.silencios, ((1.0, 2.0),))
        # Sin tramo elegido: actúa sobre el del cursor (de 1,5 a 2: ya en silencio -> devuelve el sonido).
        e.linea.seleccionar(-1)
        e.ir_a(1.7)
        e.boton_silenciar.click()
        self.assertEqual(e.audio.silencios, ((1.0, 1.5),))
        # Un tramo borrado no se silencia (no se exporta): desaparece de la línea de tiempo, no se puede
        # elegir y M actúa sobre lo que se ve (el tramo del cursor, de 1,5 a 2).
        e.linea.seleccionar(0)
        e.borrar_tramo()
        self.assertEqual(e.linea.seleccion, -1)
        e.linea.seleccionar(0)
        self.assertEqual(e.linea.seleccion, -1)
        self.assertTrue(e.boton_silenciar.isEnabled())
        e.silenciar_tramo()
        self.assertEqual(e.audio.silencios, ((1.0, 2.0),))
        self.assertTrue(all(a >= 1.0 for a, _b in e.audio.silencios))  # nada sobre lo borrado (de 0 a 1)
        # "Devolver todo" en la tarjeta.
        e.panel_sonido.boton_devolver_todo.click()
        self.assertEqual(e.audio.silencios, ())
        self.assertTrue(e.tiene_cambios())

    def test_tarjeta_sonido(self):
        v, e = self.abrir()
        ps = e.panel_sonido
        # En la columna de ajustes, abierta al empezar y en el mismo acordeón que las demás.
        self.assertTrue(ps.isVisible())
        self.assertTrue(ps.boton.isChecked())
        self.assertTrue(e._derecho.isAncestorOf(ps))
        sensor = e.panel_ajustes._secciones["Sensor"]
        self.assertFalse(sensor.boton.isChecked())
        sensor.boton.setChecked(True)
        self.assertFalse(ps.boton.isChecked())
        ps.boton.setChecked(True)
        self.assertFalse(sensor.boton.isChecked())
        # Volumen de 0 a 200 %.
        self.assertEqual((ps.volumen.slider.minimum(), ps.volumen.slider.maximum()), (0, 200))
        ps.volumen.slider.setValue(150)
        self.assertAlmostEqual(e.audio.volumen, 1.5)
        ps.check_normalizar.setChecked(True)
        self.assertTrue(e.audio.normalizar)
        # El pico exacto se mide en segundo plano (para escuchar con Normalizar).
        self.assertTrue(esperar(self.app, lambda: e._clave_pico() in e._picos, 30))
        self.assertAlmostEqual(e._picos[e._clave_pico()], A.medir_pico(self.video), delta=1e-6)
        # Fundidos: como mucho la mitad de lo que se exporta (3 s -> 1,5 s).
        self.assertAlmostEqual(ps.fundido_entrada.maximo(), 1.5)
        ps.fundido_entrada.slider.setValue(15)
        ps.fundido_salida.numero.setValue(0.7)
        self.assertEqual((e.audio.fundido_entrada, e.audio.fundido_salida), (1.5, 0.7))
        # Borrar un segundo achica el resultado a 2 s: los fundidos quedan en 1 s como mucho.
        e.ir_a(1.0)
        e.cortar()
        e.ir_a(2.0)
        e.cortar()
        e.linea.seleccionar(1)
        e.borrar_tramo()
        self.assertAlmostEqual(e.audio.fundido_entrada, 1.0)
        self.assertAlmostEqual(e.audio.fundido_salida, 0.7)
        self.assertAlmostEqual(ps.fundido_entrada.maximo(), 1.0)
        self.assertAlmostEqual(ps.fundido_entrada.valor(), 1.0)
        e.deshacer()  # deshacer el borrado devuelve también el fundido
        self.assertAlmostEqual(e.audio.fundido_entrada, 1.5)
        # Quitar el sonido: lo demás se apaga y el resumen de la exportación lo dice.
        self.assertIn("H.264 + AAC", e.etiqueta_estimacion.text())
        ps.interruptor_quitar.setChecked(True)
        self.assertTrue(e.audio.quitar)
        self.assertFalse(ps.volumen.isEnabled())
        self.assertFalse(ps.boton_guardar.isEnabled())
        self.assertFalse(e.boton_silenciar.isEnabled())
        self.assertIn("sin sonido", e.etiqueta_estimacion.text())
        self.assertNotIn("AAC", e.etiqueta_estimacion.text())
        ps.interruptor_quitar.setChecked(False)
        self.assertIn("H.264 + AAC", e.etiqueta_estimacion.text())

    def test_deshacer_y_rehacer_cortes_y_sonido(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        v, e = self.abrir()
        ps = e.panel_sonido
        inicial = (e.edicion, e.audio)
        e.ir_a(1.0)
        e.cortar()
        paso1 = (e.edicion, e.audio)
        e.linea.seleccionar(0)
        e.silenciar_tramo()
        paso2 = (e.edicion, e.audio)
        # Varios movimientos seguidos del volumen: un solo paso.
        for valor in (110, 120, 130, 140):
            ps.volumen.slider.setValue(valor)
        paso3 = (e.edicion, e.audio)
        self.assertAlmostEqual(e.audio.volumen, 1.4)
        ps.check_normalizar.setChecked(True)
        paso4 = (e.edicion, e.audio)
        self.assertEqual(len(e._deshacer), 4)
        for esperado in (paso3, paso2, paso1, inicial):
            QTest.keyClick(e, Qt.Key_Z, Qt.ControlModifier)
            self.assertEqual((e.edicion, e.audio), esperado)
        # La tarjeta y la pista muestran lo deshecho.
        self.assertEqual(ps.volumen.valor(), 100)
        self.assertFalse(ps.check_normalizar.isChecked())
        self.assertEqual(e.pista_sonido._ajustes, A.AjustesAudio())
        self.assertFalse(e.boton_deshacer.isEnabled())
        for esperado in (paso1, paso2, paso3, paso4):
            QTest.keyClick(e, Qt.Key_Y, Qt.ControlModifier)
            self.assertEqual((e.edicion, e.audio), esperado)
        self.assertEqual(ps.volumen.valor(), 140)
        self.assertTrue(ps.check_normalizar.isChecked())
        # Pasado un rato, el mismo deslizador es otro paso.
        e._ultimo_cambio_sonido = ("volumen", time.monotonic() - 10)
        ps.check_normalizar.setChecked(False)
        ps.volumen.slider.setValue(90)
        ps.volumen.slider.setValue(80)
        e.deshacer()
        self.assertAlmostEqual(e.audio.volumen, 1.4)
        # Mover y volver al valor de antes no deja un paso vacío.
        cuantos = len(e._deshacer)
        ps.volumen.slider.setValue(150)
        ps.volumen.slider.setValue(140)
        self.assertEqual(len(e._deshacer), cuantos)

    def test_exportar_sin_sonido_y_con_un_silencio(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from celular_natural.ui import editor_video as E
        v, e = self.abrir()
        # Sin sonido: el MP4 sale sin pista de audio.
        e.panel_sonido.interruptor_quitar.setChecked(True)
        destino = self.dir / "sin_sonido.mp4"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "")), \
                mock.patch.object(QMessageBox, "information") as aviso:
            e.exportar()
            self.assertTrue(esperar(self.app, lambda: not e.exportando, 120))
        self.assertIn("sin sonido", aviso.call_args.args[2])
        self.assertFalse(e.ultima_exportacion.con_audio)
        with av.open(str(destino)) as c:
            self.assertEqual(len(c.streams.audio), 0)
            self.assertEqual(len(c.streams.video), 1)
        # Con un silencio sobre el tono de 440 y el volumen a la mitad: los ajustes llegan al archivo.
        e.panel_sonido.interruptor_quitar.setChecked(False)
        e.ir_a(1.0)
        e.cortar()
        e.linea.seleccionar(0)
        e.silenciar_tramo()
        e.panel_sonido.volumen.slider.setValue(50)
        llamadas = []
        original = E.mv.exportar_video

        def espia(*args, **kw):
            llamadas.append(kw.get("audio"))
            return original(*args, **kw)

        destino = self.dir / "con_silencio.mp4"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "")), \
                mock.patch.object(QMessageBox, "information"), mock.patch.object(E.mv, "exportar_video", espia):
            e.exportar()
            self.assertTrue(esperar(self.app, lambda: not e.exportando, 120))
        self.assertEqual(llamadas, [A.AjustesAudio(volumen=0.5, silencios=((0.0, 1.0),))])
        audio, sr = leer_audio(destino)
        self.assertLess(np.abs(audio[:, int(0.1 * sr):int(0.9 * sr)]).max(), 0.01)
        self.assertAlmostEqual(np.abs(audio[:, int(2.2 * sr):int(2.8 * sr)]).max(), 0.15, delta=0.02)

    def test_guardar_solo_el_audio(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from celular_natural.motor import Cancelado
        from celular_natural.ui import editor_video as E
        v, e = self.abrir()
        e.ir_a(1.0)
        e.cortar()
        e.ir_a(2.0)
        e.cortar()
        e.linea.seleccionar(1)
        e.borrar_tramo()  # quedan 2 s
        dialogos = []

        def dialogo(*args, **_kw):
            dialogos.append(args)
            return respuestas.pop(0)

        # WAV: el diálogo ofrece los formatos que hay y sugiere nombre_celular.m4a.
        wav = self.dir / "solo.wav"
        respuestas = [(str(wav), "WAV (sin compresión) (*.wav)")]
        with mock.patch.object(QFileDialog, "getSaveFileName", side_effect=dialogo), \
                mock.patch.object(QMessageBox, "information") as aviso:
            e.panel_sonido.boton_guardar.click()
            self.assertTrue(e.panel_sonido.guardando)
            self.assertTrue(e.panel_sonido.caja_progreso.isVisible())
            self.assertTrue(esperar(self.app, lambda: not e.panel_sonido.guardando, 60))
        titulo, sugerida, filtros = dialogos[0][1], dialogos[0][2], dialogos[0][3]
        self.assertEqual(titulo, "Guardar solo el audio")
        self.assertTrue(sugerida.endswith("clip_celular.m4a"))
        for nombre in ("M4A", "WAV", "MP3"):
            if nombre.lower() in [f.nombre for f in A.formatos_audio_disponibles()]:
                self.assertIn(nombre, filtros)
        self.assertIn(str(wav), aviso.call_args.args[2])
        self.assertFalse(e.panel_sonido.caja_progreso.isVisible())
        audio, sr = leer_audio(wav)
        self.assertAlmostEqual(audio.shape[1] / sr, 2.0, delta=0.01)
        self.assertEqual(e.ultimo_audio.formato, "wav")
        # Sin extensión: la del tipo elegido en el diálogo.
        respuestas = [(str(self.dir / "sin_extension"), "M4A (AAC) (*.m4a)")]
        with mock.patch.object(QFileDialog, "getSaveFileName", side_effect=dialogo), \
                mock.patch.object(QMessageBox, "information"):
            e.guardar_audio()
            self.assertTrue(esperar(self.app, lambda: not e.panel_sonido.guardando, 60))
        self.assertTrue((self.dir / "sin_extension.m4a").exists())
        # Cancelar: no queda nada y la tarjeta vuelve a estar lista.
        def lenta(_entrada, _salida, _tramos, _ajustes, _formato, avance, cancelado, _pico):
            while not cancelado():
                avance(1, 10, None)
                time.sleep(0.02)
            raise Cancelado()

        respuestas = [(str(self.dir / "cancelado.wav"), "WAV (sin compresión) (*.wav)")]
        with mock.patch.object(QFileDialog, "getSaveFileName", side_effect=dialogo), \
                mock.patch.object(E.ma, "exportar_audio", side_effect=lenta):
            e.guardar_audio()
            self.assertTrue(esperar(self.app, lambda: e.panel_sonido.barra.value() > 0, 10))
            # Mientras guarda no se puede cerrar el video.
            with mock.patch.object(QMessageBox, "information") as aviso:
                self.assertFalse(e.cerrar_video(confirmar=False))
                aviso.assert_called_once()
            e.panel_sonido.boton_cancelar.click()
            self.assertTrue(esperar(self.app, lambda: not e.panel_sonido.guardando, 10))
        self.assertFalse((self.dir / "cancelado.wav").exists())
        self.assertIn("Se canceló", e.etiqueta_estado.text())
        # Con el sonido quitado no se puede.
        e.panel_sonido.interruptor_quitar.setChecked(True)
        self.assertFalse(e.panel_sonido.boton_guardar.isEnabled())

    def test_reproducir_sin_salida_de_sonido(self):
        """En modo sin pantalla no hay salida (como en una PC sin parlantes): se ve igual, sin errores."""
        from celular_natural.ui import reproductor_audio as R
        v, e = self.abrir()
        self.assertFalse(e.reproductor.disponible)
        self.assertFalse(e.boton_sonido.isEnabled())
        self.assertIn("Sin sonido en la vista previa", e.boton_sonido.toolTip())
        e.reproducir()
        self.assertFalse(e._con_sonido)
        pausa(self.app, 0.4)
        self.assertGreater(e.tiempo, 0.2)  # avanza con su propio reloj
        e.ir_a(2.0)
        pausa(self.app, 0.2)
        e.pausar()
        self.assertFalse(e.reproduciendo)
        # Y si QtMultimedia no carga: lo mismo.
        from celular_natural.ui.ventana import VentanaPrincipal
        with mock.patch.object(R, "_cargar_qtmultimedia", side_effect=OSError("falta una DLL")), \
                mock.patch.dict(os.environ, {R.VARIABLE_OFFSCREEN: "1"}):
            otra = VentanaPrincipal()
            self.ventanas.append(otra)
            otra.resize(1366, 768)
            otra.show()
            otra.abrir_rutas([str(self.video)])
            e2 = otra.editor_video
        self.assertTrue(esperar(self.app, lambda: e2.info is not None))
        self.assertIn("No se pudo usar el sonido de Qt", e2.reproductor.motivo)
        e2.reproducir()
        pausa(self.app, 0.3)
        self.assertGreater(e2.tiempo, 0.1)
        e2.pausar()

    def test_la_imagen_sigue_al_sonido_y_silenciar_la_vista_previa(self):
        from celular_natural.ui.modo_facil import configuracion
        from celular_natural.ui.ventana import VentanaPrincipal
        from celular_natural.ui import editor_video as E
        falso, parches = con_salida_falsa()
        with parches[0], parches[1]:
            v, e = self.abrir()
            self.assertTrue(e.reproductor.disponible)
            self.assertTrue(e.boton_sonido.isEnabled())
            self.assertTrue(e.boton_sonido.isChecked())  # la primera vez, con sonido
            e.ir_a(1.0)
            e.cortar()
            e.ir_a(2.0)
            e.cortar()
            e.linea.seleccionar(1)
            e.borrar_tramo()
            e.ir_a(0.5)
            e.reproducir()
            self.assertTrue(e._con_sonido)
            sink = _Sink.creados[-1]
            # Mientras el sonido no avanza, la imagen espera.
            pausa(self.app, 0.15)
            self.assertAlmostEqual(e.tiempo, 0.5, delta=1 / 24)
            sink.avanzar(0.25)
            pausa(self.app, 0.05)
            self.assertAlmostEqual(e.tiempo, 0.75, delta=1 / 24)
            sink.avanzar(0.3)  # 0,5 s después de 0,5: cruza lo borrado y sigue en 2,05
            pausa(self.app, 0.05)
            self.assertAlmostEqual(e.tiempo, 2.05, delta=1 / 24)
            # Un cambio de volumen mientras suena llega al lector, sin cortar.
            arranques = sink.arranques
            e.panel_sonido.volumen.slider.setValue(60)
            self.assertAlmostEqual(e.reproductor.lector.ajustes.volumen, 0.6)
            self.assertEqual(sink.arranques, arranques)
            # Mover el cursor mientras suena: el sonido vuelve desde ahí cuando se queda quieto.
            e.ir_a(2.5)
            self.assertFalse(e._con_sonido)
            self.assertTrue(esperar(self.app, lambda: e._con_sonido, 2))
            self.assertAlmostEqual(e.reproductor.posicion(), 2.5, delta=0.2)  # desde donde iba la imagen
            # Silenciar la vista previa: sigue reproduciendo con su reloj, y se recuerda.
            e.boton_sonido.click()
            self.assertFalse(e._con_sonido)
            self.assertTrue(e.reproduciendo)
            self.assertIn("silenciada", e.boton_sonido.toolTip())
            self.assertEqual(str(configuracion().value(E.CLAVE_SONIDO_VISTA)).lower(), "false")
            e.pausar()
            otra = VentanaPrincipal()
            self.ventanas.append(otra)
            otra.establecer_modo("video")
            e2 = otra.editor_video
            self.assertFalse(e2.boton_sonido.isChecked())
            self.assertTrue(e2.reproductor.silenciado)
            # Volver a activarlo también se recuerda.
            e2.boton_sonido.setChecked(True)
            self.assertFalse(e2.reproductor.silenciado)
            self.assertEqual(str(configuracion().value(E.CLAVE_SONIDO_VISTA)).lower(), "true")


if __name__ == "__main__":
    unittest.main()
