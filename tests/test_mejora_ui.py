"""Pruebas de "Mejorar calidad" (sin IA) en el modo Video: motor de video, piezas y ventana real.

* **Motor** (``motor/video.py``): ``tamano_salida(..., agrandar=True)``, ``tamano_lectura``,
  ``tiempos_vecinos`` y ``VentanaVecinos`` (cuadro por cuadro igual a ``MejoradorVideo``);
  exportar con cortes y la mejora a 1080p (1920×1080, los cuadros que quedan, en orden, con el
  audio y la duración del resultado), sin que los vecinos crucen el corte; con ``mejora=None`` o
  apagada, el camino de siempre; cancelar.
* **Ventana real** (modo sin pantalla): la tarjeta y el acordeón, las resoluciones que agrandan, el
  resumen de la exportación, deshacer y rehacer, "Antes / Después" (el antes agrandado simple y el
  después igual a la exportación), la mejora que espera a que el cursor se quede quieto, y exportar
  a 1080p desde la ventana.
* **Arreglos de la revisión** del sonido y los cortes: juntar pasos de deshacer sin pegarlos a uno
  anterior, la entrada y la salida que dejan justo un cuadro, los arrastres cuyo soltar se pierde,
  el tramo elegido al deshacer y las mediciones del pico que ya no hacen falta.

Los videos se generan en una carpeta temporal (``tests/test_video.py``). Para esperar se usa
``time.sleep`` y ``processEvents`` (``QTest.qWait`` no suelta el GIL).
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

try:
    import av
except ImportError:  # pragma: no cover
    av = None

from celular_natural.motor import Cancelado  # noqa: E402
from celular_natural.motor import mejora_video as M  # noqa: E402

if av is not None:
    from test_video import FPS, generar_video, leer_codigo, leer_video  # noqa: E402
    from celular_natural.motor import video as V  # noqa: E402

PRENDIDA = M.AjustesMejora(activa=True)


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


def qimage_a_rgb(img) -> np.ndarray:
    from PySide6.QtGui import QImage
    img = img.convertToFormat(QImage.Format_RGB888)
    w, h = img.width(), img.height()
    datos = np.frombuffer(img.constBits(), np.uint8, count=img.sizeInBytes()).reshape(h, img.bytesPerLine())
    return datos[:, :3 * w].reshape(h, w, 3).copy()


def codigo_grande(rgb: np.ndarray, ancho: int = 640, alto: int = 360) -> int:
    """El número de cuadro de un cuadro agrandado (se achica al tamaño en que se escribió)."""
    return leer_codigo(cv2.resize(rgb, (ancho, alto), interpolation=cv2.INTER_AREA))


def raton(widget, tipo: str, x: float, y: float, botones=None) -> None:
    """Un evento del mouse: "apretar", "mover" (con ``botones`` apretados, por defecto el izquierdo) o
    "soltar"."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    tipos = {"apretar": QEvent.MouseButtonPress, "mover": QEvent.MouseMove, "soltar": QEvent.MouseButtonRelease}
    if botones is None:
        botones = Qt.NoButton if tipo == "soltar" else Qt.LeftButton
    boton = Qt.NoButton if tipo == "mover" else Qt.LeftButton
    pos = QPointF(x, y)
    QApplication.sendEvent(widget, QMouseEvent(tipos[tipo], pos, widget.mapToGlobal(pos), boton, botones,
                                               Qt.NoModifier))


# ---------------------------------------------------------------------------
# Motor
# ---------------------------------------------------------------------------

class PruebasPiezasMotor(unittest.TestCase):
    def test_tamano_salida_agranda_solo_con_la_mejora(self):
        if av is None:
            self.skipTest("Falta PyAV")
        # Sin la mejora, como siempre: nunca agranda.
        self.assertEqual(V.tamano_salida(640, 360, "1080p"), (640, 360))
        self.assertEqual(V.tamano_salida(1920, 1080, "720p"), (1280, 720))
        # Con la mejora, 720p y 1080p agrandan (conservando la proporción y la orientación).
        self.assertEqual(V.tamano_salida(640, 360, "1080p", agrandar=True), (1920, 1080))
        self.assertEqual(V.tamano_salida(640, 360, "720p", agrandar=True), (1280, 720))
        self.assertEqual(V.tamano_salida(854, 480, "1080p", agrandar=True), (1920, 1080))
        self.assertEqual(V.tamano_salida(360, 640, "720p", agrandar=True), (720, 1280))
        self.assertEqual(V.tamano_salida(320, 240, "1080p", agrandar=True), (1440, 1080))
        # Lo que se achica (o queda igual) sale igual que sin la mejora, y "Original" no cambia.
        for ancho, alto, resoluciones in (((1920, 1080, ("720p", "1080p", "Original", None))),
                                          (3840, 2160, ("720p", "1080p", "Original")),
                                          (1366, 768, ("720p", "Original")), (1280, 720, ("720p", "Original")),
                                          (1080, 1920, ("720p", "1080p"))):
            for resolucion in resoluciones:
                self.assertEqual(V.tamano_salida(ancho, alto, resolucion, agrandar=True),
                                 V.tamano_salida(ancho, alto, resolucion), (ancho, alto, resolucion))
        self.assertEqual(V.tamano_salida(640, 360, "Original", agrandar=True), (640, 360))
        self.assertEqual(V.tamano_salida(1366, 768, "1080p", agrandar=True), (1920, 1080))  # más chico: agranda
        # Se lee al tamaño del original si la salida es más grande, y al de salida si es más chica.
        self.assertEqual(V.tamano_lectura(640, 360, 1920, 1080), (640, 360))
        self.assertEqual(V.tamano_lectura(640, 360, 640, 360), (640, 360))
        self.assertEqual(V.tamano_lectura(3840, 2160, 1920, 1080), (1920, 1080))
        self.assertEqual(V.tamano_lectura(641, 361, 640, 360), (640, 360))

    def test_ventana_de_vecinos_igual_a_mejorador_video(self):
        if av is None:
            self.skipTest("Falta PyAV")
        rng = np.random.default_rng(3)
        cuadros = [rng.integers(0, 255, (36, 44, 3), dtype=np.uint8) for _ in range(12)]
        tramos = [cuadros[:4], cuadros[4:5], cuadros[5:7], cuadros[7:]]  # incluye tramos de 1 y 2 cuadros
        ajustes = M.AjustesMejora(activa=True, cuadraditos=0.7, nitidez=0.6, vecinos=1.0)
        referencia = []
        mejorador = M.MejoradorVideo(ajustes, 88, 72)
        for tramo in tramos:
            mejorador.reiniciar()
            for c in tramo:
                referencia += mejorador.agregar(c)
        referencia += mejorador.terminar()
        ventana = V.VentanaVecinos()
        salida, datos = [], []
        for k, tramo in enumerate(tramos):
            listos = ventana.cortar()
            for j, c in enumerate(tramo):
                listos += ventana.agregar(c, (k, j))
                for actual, vecinos, dato in listos:
                    salida.append(M.mejorar_cuadro(actual, vecinos, 88, 72, ajustes))
                    datos.append(dato)
                listos = []
            for actual, vecinos, dato in listos:
                salida.append(M.mejorar_cuadro(actual, vecinos, 88, 72, ajustes))
                datos.append(dato)
        for actual, vecinos, dato in ventana.cortar():
            salida.append(M.mejorar_cuadro(actual, vecinos, 88, 72, ajustes))
            datos.append(dato)
        self.assertEqual(len(salida), 12)
        self.assertEqual(datos, [(k, j) for k, t in enumerate(tramos) for j in range(len(t))])  # en orden
        for i, (a, b) in enumerate(zip(referencia, salida)):
            np.testing.assert_array_equal(a, b, f"cuadro {i}")

    def test_tiempos_vecinos_dentro_del_tramo(self):
        if av is None:
            self.skipTest("Falta PyAV")
        tramos = [(0.0, 1.0), (2.0, 3.0)]
        c = 1 / 24

        def indices(t, ultimo=None):
            return [None if s is None else round(s * 24) for s in V.tiempos_vecinos(tramos, t, 24, ultimo)]

        self.assertEqual(indices(0.0), [None, None, 1, 2])
        self.assertEqual(indices(12 * c), [10, 11, 13, 14])
        self.assertEqual(indices(23 * c), [21, 22, None, None])  # el borrado (1 a 2 s) no cuenta
        self.assertEqual(indices(48 * c), [None, None, 49, 50])
        self.assertEqual(indices(70 * c, ultimo=71 * c), [68, 69, 71, None])
        self.assertEqual(indices(71 * c, ultimo=71 * c), [69, 70, None, None])

    def test_entrada_y_salida_que_dejan_justo_un_cuadro(self):
        """Arreglo de la revisión: arrastrar un corchete hasta dejar un solo cuadro no se rechaza."""
        if av is None:
            self.skipTest("Falta PyAV")
        for fps in (24, 25, 30000 / 1001, 30, 60):
            e = V.EdicionVideo.nueva(10.0, fps)
            for k in range(0, 200, 7):
                entrada, salida = k / fps, (k + 1) / fps
                nueva = e.con_limites(entrada, salida)
                self.assertIsNot(nueva, e, (fps, k))
                self.assertAlmostEqual(nueva.duracion_resultante(), 1 / fps, places=9)
            self.assertIs(e.con_limites(1.0, 1.0), e)  # sin ningún cuadro, sí se rechaza


@unittest.skipIf(av is None, "Falta PyAV (pip install av==19.0.1)")
class PruebasExportarConMejora(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="naturalshot_mejora_"))
        cls.video = generar_video(cls.dir / "chico.mp4", segundos=3.0, w=640, h=360)  # 72 cuadros, con audio
        cls.corto = generar_video(cls.dir / "corto.mp4", segundos=1.0, w=320, h=240)

    @classmethod
    def tearDownClass(cls):
        V.cerrar_lectores()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_exportar_con_cortes_a_1080p_sin_cruzar_el_corte(self):
        tramos = V.EdicionVideo.nueva(3.0, FPS).cortar(1.0).cortar(2.0).con_borrado(1).tramos_conservados()
        llamadas = []
        original = V.mejorar_cuadro

        def espia(actual, vecinos, ancho, alto, ajustes):
            llamadas.append((leer_codigo(actual), [None if v is None else leer_codigo(v) for v in vecinos]))
            return original(actual, vecinos, ancho, alto, ajustes)

        destino = self.dir / "mejorado_1080p.mp4"
        avances = []
        with mock.patch.object(V, "mejorar_cuadro", espia):
            r = V.exportar_video(self.video, destino, (), tramos, resolucion="1080p", calidad="Alta",
                                 progreso=lambda h, n, s: avances.append((h, n)), mejora=PRENDIDA)
        self.assertEqual((r.ancho, r.alto), (1920, 1080))
        self.assertTrue(r.mejorado)
        self.assertTrue(r.con_audio)
        self.assertEqual(r.cuadros, 48)
        self.assertEqual(avances[-1], (48, 48))
        cuadros, audio, datos = leer_video(destino)
        self.assertEqual((datos["ancho"], datos["alto"]), (1920, 1080))
        # Los cuadros que quedan, en orden (el número de cada uno se lee achicándolo de vuelta).
        self.assertEqual([codigo_grande(c) for c in cuadros], list(range(24)) + list(range(48, 72)))
        self.assertAlmostEqual(datos["duracion"], 2.0, delta=0.5 / FPS)
        self.assertIsNotNone(audio)
        self.assertAlmostEqual(audio.shape[1] / datos["frecuencia"], 2.0, delta=0.03)  # audio = video
        # Cada cuadro se mejoró una vez, con vecinos de su mismo tramo: nunca del otro lado del corte.
        self.assertEqual(sorted(c for c, _v in llamadas), list(range(24)) + list(range(48, 72)))
        for codigo, vecinos in llamadas:
            mismo = range(0, 24) if codigo < 24 else range(48, 72)
            esperados = [codigo + d if codigo + d in mismo else None for d in (-2, -1, 1, 2)]
            self.assertEqual(vecinos, esperados, f"cuadro {codigo}")
            # La vista previa elige los mismos (tiempos_vecinos).
            previa = [None if s is None else round(s * FPS)
                      for s in V.tiempos_vecinos(tramos, codigo / FPS, FPS, 71 / FPS)]
            self.assertEqual(previa, esperados, f"vista previa, cuadro {codigo}")

    def test_vista_previa_lee_igual_que_la_exportacion_al_achicar(self):
        """Arreglo de la revisión: con la salida más chica que el original, la exportación lee cada
        cuadro directo a ``tamano_lectura`` (1918×1078 a 720p: 1280×720) y la vista previa lo leía
        reducido a un lado máximo (1280×719) y lo estiraba. Ahora lee exactamente lo mismo."""
        from celular_natural.ui import editor_video as E
        video = generar_video(self.dir / "casi_1080.mp4", segundos=0.5, w=1918, h=1078, audio=False)
        info = V.info_video(video)
        ancho, alto = V.tamano_salida(info.ancho, info.alto, "720p", agrandar=True)
        lectura = V.tamano_lectura(info.ancho, info.alto, ancho, alto)
        self.assertEqual(lectura, (1280, 720))
        self.assertEqual(V._tamano_reducido(info.ancho, info.alto, max(lectura)), (1280, 719))  # lo de antes
        leidos = {}
        original = V.mejorar_cuadro

        def espia(actual, vecinos, w, h, ajustes):
            copia = (actual.copy(), [None if v is None else v.copy() for v in vecinos])
            leidos[codigo_grande(actual, info.ancho, info.alto)] = copia
            return original(actual, vecinos, w, h, ajustes)

        with mock.patch.object(V, "mejorar_cuadro", espia):
            V.exportar_video(video, self.dir / "casi_1080_a_720p.mp4", (), None, resolucion="720p", mejora=PRENDIDA)
        n = round(0.5 * FPS)
        self.assertEqual(sorted(leidos), list(range(n)))
        datos = E.DatosMejora(PRENDIDA, ((0.0, n / FPS),), info.fps, (n - 1) / FPS, lectura,
                              (info.ancho, info.alto))
        for k in range(n):
            with self.subTest(cuadro=k):
                np.testing.assert_array_equal(E.leer_para_mejora(str(video), k / FPS, datos), leidos[k][0])
        # Y el cuadro mejorado de la vista previa es el mismo que mejora la exportación.
        k = n // 2
        _actual, mejorado, _s = E.cuadro_mejorado(str(video), k / FPS, ancho, alto, datos, E.CacheMejora())
        np.testing.assert_array_equal(mejorado, original(*leidos[k], ancho, alto, PRENDIDA))

    def test_mejora_apagada_es_el_camino_de_siempre(self):
        llamadas = []
        original = V.mejorar_cuadro

        def espia(*args, **kw):
            llamadas.append(1)
            return original(*args, **kw)

        sin, apagada = self.dir / "sin_mejora.mp4", self.dir / "mejora_apagada.mp4"
        with mock.patch.object(V, "mejorar_cuadro", espia):
            r1 = V.exportar_video(self.corto, sin, (), [(0.0, 0.5)], resolucion="1080p")
            r2 = V.exportar_video(self.corto, apagada, (), [(0.0, 0.5)], resolucion="1080p",
                                  mejora=M.AjustesMejora(activa=False, nitidez=1.0))
        self.assertEqual(llamadas, [])
        self.assertEqual((r1.ancho, r1.alto), (320, 240))  # nunca agranda
        self.assertEqual((r2.ancho, r2.alto), (320, 240))
        self.assertFalse(r1.mejorado or r2.mejorado)
        a, audio_a, _ = leer_video(sin)
        b, audio_b, _ = leer_video(apagada)
        self.assertEqual(len(a), 12)
        for x, y in zip(a, b):
            np.testing.assert_array_equal(x, y)
        np.testing.assert_array_equal(audio_a, audio_b)

    def test_de_a_uno_o_de_a_varios_segun_el_filtro(self):
        from celular_natural.motor import PRESET_PRINCIPAL, PRESETS
        tramos = [(0.0, 0.5)]
        # Sin filtro la mejora es lo lento: se reparte. Con el filtro de la app, de a un cuadro.
        varios = V.exportar_video(self.corto, self.dir / "varios.mp4", (), tramos, resolucion="720p",
                                  calidad=10, mejora=PRENDIDA)
        con_filtro = V.exportar_video(self.corto, self.dir / "con_filtro.mp4", (PRESETS[PRESET_PRINCIPAL],), tramos,
                                      resolucion="720p", mejora=PRENDIDA)
        self.assertEqual(varios.hilos_mejora, V.HILOS_MEJORA)
        self.assertEqual(con_filtro.hilos_mejora, 1)
        self.assertEqual((con_filtro.ancho, con_filtro.alto), (960, 720))
        # El resultado no depende de eso: de a uno da los mismos cuadros.
        with mock.patch.object(V, "HILOS_MEJORA", 1):
            uno = V.exportar_video(self.corto, self.dir / "uno.mp4", (), tramos, resolucion="720p", calidad=10,
                                   mejora=PRENDIDA)
        self.assertEqual(uno.hilos_mejora, 1)
        a, _, _ = leer_video(self.dir / "varios.mp4")
        b, _, _ = leer_video(self.dir / "uno.mp4")
        self.assertEqual(len(a), 12)
        for x, y in zip(a, b):
            np.testing.assert_array_equal(x, y)

    def test_cancelar_con_mejora_no_deja_archivos(self):
        carpeta = self.dir / "cancelado"
        carpeta.mkdir()
        estado = {"n": 0}
        with self.assertRaises(Cancelado):
            V.exportar_video(self.video, carpeta / "no.mp4", (), resolucion="720p", mejora=PRENDIDA,
                             progreso=lambda h, n, s: estado.update(n=h), cancelado=lambda: estado["n"] >= 4)
        self.assertEqual(list(carpeta.iterdir()), [])


# ---------------------------------------------------------------------------
# Piezas sueltas: arrastres cuyo soltar se pierde (arreglo de la revisión)
# ---------------------------------------------------------------------------

@unittest.skipIf(av is None, "Falta PyAV (pip install av==19.0.1)")
class PruebasArrastrePerdido(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_linea_de_tiempo(self):
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QFocusEvent
        from PySide6.QtWidgets import QApplication
        from celular_natural.ui.linea_tiempo import LineaTiempo
        linea = LineaTiempo()
        linea.resize(600, 140)
        linea.establecer_edicion(V.EdicionVideo.nueva(3.0, FPS))
        pedidos, limites = [], []
        linea.tiempoPedido.connect(lambda t, arrastrando: pedidos.append((round(t, 3), arrastrando)))
        linea.limitesPedidos.connect(lambda a, b: limites.append((a, b)))
        y = linea._pista().center().y()
        x0 = linea.x_de(1.0)
        raton(linea, "apretar", x0, y)
        raton(linea, "mover", linea.x_de(1.5), y)
        self.assertEqual(pedidos[-1][1], True)
        # Un cuadro de diálogo se comió el soltar: el próximo movimiento llega sin el botón apretado.
        raton(linea, "mover", linea.x_de(2.0), y, botones=Qt.NoButton)
        self.assertIsNone(linea._arrastre)
        self.assertEqual(pedidos[-1][1], False)  # se pidió el cuadro final donde iba
        self.assertAlmostEqual(pedidos[-1][0], 1.5, delta=0.05)
        cuantos = len(pedidos)
        raton(linea, "mover", linea.x_de(2.5), y, botones=Qt.NoButton)  # pasar por encima ya no mueve nada
        self.assertEqual(len(pedidos), cuantos)
        # Un corchete arrastrado y Alt+Tab: vuelve a su lugar sin recortar.
        raton(linea, "apretar", linea.x_de(0.0), y)
        self.assertEqual(linea._arrastre, "entrada")
        raton(linea, "mover", linea.x_de(1.0), y)
        QApplication.sendEvent(linea, QFocusEvent(QEvent.FocusOut, Qt.ActiveWindowFocusReason))
        self.assertIsNone(linea._arrastre)
        self.assertIsNone(linea._limite)
        raton(linea, "soltar", linea.x_de(1.0), y)
        self.assertEqual(limites, [])
        # Y un arrastre normal sigue andando.
        raton(linea, "apretar", x0, y)
        raton(linea, "mover", linea.x_de(2.0), y)
        raton(linea, "soltar", linea.x_de(2.0), y)
        self.assertFalse(pedidos[-1][1])
        self.assertAlmostEqual(pedidos[-1][0], 2.0, delta=0.05)
        self.assertIsNone(linea._arrastre)
        linea.deleteLater()

    def test_pista_de_sonido(self):
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QFocusEvent
        from PySide6.QtWidgets import QApplication
        from celular_natural.ui.forma_onda import PistaOnda
        pista = PistaOnda()
        pista.resize(600, 60)
        pista.sin_sonido(3.0)
        pedidos = []
        pista.tiempoPedido.connect(lambda t, arrastrando: pedidos.append((round(t, 2), arrastrando)))
        # La pista no sigue al mouse sin botón (Qt ni le manda esos movimientos): el arrastre colgado
        # se corta al salir sin el botón apretado o al perder el foco.
        raton(pista, "apretar", 100, 30)
        raton(pista, "mover", 300, 30)
        self.assertTrue(pista._arrastrando)
        QApplication.sendEvent(pista, QEvent(QEvent.Leave))
        self.assertFalse(pista._arrastrando)
        self.assertFalse(pedidos[-1][1])
        cuantos = len(pedidos)
        raton(pista, "mover", 500, 30, botones=Qt.NoButton)
        self.assertEqual(len(pedidos), cuantos)
        raton(pista, "apretar", 100, 30)
        QApplication.sendEvent(pista, QFocusEvent(QEvent.FocusOut, Qt.ActiveWindowFocusReason))
        self.assertFalse(pista._arrastrando)
        # Si llega un movimiento sin el botón (con el seguimiento del mouse prendido), también se corta.
        pista.setMouseTracking(True)
        raton(pista, "apretar", 100, 30)
        raton(pista, "mover", 400, 30, botones=Qt.NoButton)
        self.assertFalse(pista._arrastrando)
        pista.deleteLater()


# ---------------------------------------------------------------------------
# La ventana real
# ---------------------------------------------------------------------------

@unittest.skipIf(av is None, "Falta PyAV (pip install av==19.0.1)")
class PruebasVentanaMejora(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        cls.dir = Path(tempfile.mkdtemp(prefix="naturalshot_mejora_ventana_"))
        cls._entorno = {k: os.environ.get(k) for k in ("APPDATA", "NATURALSHOT_CONFIG")}
        os.environ["APPDATA"] = str(cls.dir / "appdata")
        cls.config = cls.dir / "config.ini"
        os.environ["NATURALSHOT_CONFIG"] = str(cls.config)
        cls.video = generar_video(cls.dir / "chico.mp4", segundos=2.0, w=640, h=360)  # 48 cuadros, con audio

    @classmethod
    def tearDownClass(cls):
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

    def abrir(self):
        from celular_natural.ui.ventana import VentanaPrincipal
        v = VentanaPrincipal()
        self.ventanas.append(v)
        v.resize(1366, 768)
        v.show()
        v.activateWindow()  # los atajos (Ctrl+Z) andan en la ventana activa
        v.abrir_rutas([str(self.video)])
        e = v.editor_video
        self.assertTrue(esperar(self.app, lambda: e.info is not None and e.cuadro_procesado_listo()))
        return v, e

    # ------------------------------------------------------------ pruebas
    def test_tarjeta_acordeon_y_resoluciones(self):
        v, e = self.abrir()
        pm = e.panel_mejora
        # En la columna de ajustes, cerrada al empezar y en el mismo acordeón que Sonido y las secciones.
        self.assertTrue(e._derecho.isAncestorOf(pm))
        self.assertTrue(pm.isVisible())
        self.assertEqual(pm.titulo.text(), "Mejorar calidad")
        self.assertFalse(pm.boton.isChecked())
        self.assertTrue(e.panel_sonido.boton.isChecked())
        pm.boton.setChecked(True)
        self.assertFalse(e.panel_sonido.boton.isChecked())
        sensor = e.panel_ajustes._secciones["Sensor"]
        sensor.boton.setChecked(True)
        self.assertFalse(pm.boton.isChecked())
        e.panel_sonido.boton.setChecked(True)
        self.assertFalse(sensor.boton.isChecked())
        pm.boton.setChecked(True)
        # Apagada: las barras no andan, el video no se agranda y la ayuda dice que no es IA.
        self.assertIn("No es IA", pm.ayuda.text())
        self.assertIn("720p", pm.ayuda.text())
        self.assertFalse(pm.cuadraditos.isEnabled())
        self.assertEqual([b.text() for b in e.botones_resolucion.values()],
                         ["Original\n640 × 360", "1080p\ncon la mejora", "720p\ncon la mejora"])
        self.assertFalse(e.botones_resolucion["1080p"].isEnabled())
        # Apagados no muestran el tamaño del original (confundía): la ayuda dice cómo agrandar.
        self.assertIn("Prendé Mejorar calidad para agrandar a 1920 × 1080", e.botones_resolucion["1080p"].toolTip())
        self.assertNotIn("tarda más", e.etiqueta_estimacion.text())
        # Prendida: 720p y 1080p agrandan (y se sugiere 720p, lo acordado para un video chico).
        pm.interruptor.setChecked(True)
        self.assertTrue(e.mejora.activa)
        self.assertTrue(pm.cuadraditos.isEnabled())
        self.assertEqual([b.text() for b in e.botones_resolucion.values()],
                         ["Original\n640 × 360", "1080p\n1920 × 1080", "720p\n1280 × 720"])
        self.assertTrue(all(b.isEnabled() for b in e.botones_resolucion.values()))
        self.assertEqual(e._resolucion(), "720p")
        self.assertIn("1280 × 720", e.etiqueta_estado.text())
        self.assertIn("tarda más", e.etiqueta_estimacion.text())
        self.assertIn("1280 × 720", pm.nota.text())
        # Las barras, de 0 a 100 %.
        self.assertEqual((pm.nitidez.slider.minimum(), pm.nitidez.slider.maximum()), (0, 100))
        pm.nitidez.slider.setValue(80)
        pm.vecinos.slider.setValue(0)
        pm.cuadraditos.numero.setValue(30)
        self.assertEqual(e.mejora, M.AjustesMejora(activa=True, cuadraditos=0.3, nitidez=0.8, vecinos=0.0))
        # Elegir 1080p y apagar: vuelve a "Original" (no se puede agrandar) y al prenderla, 1080p otra vez.
        e.botones_resolucion["1080p"].click()
        self.assertEqual(e._tam_salida(), (1920, 1080))
        pm.interruptor.setChecked(False)
        self.assertFalse(e.mejora.activa)
        self.assertEqual(e._resolucion(), "Original")
        self.assertEqual(e._tam_salida(), (640, 360))
        e._ultimo_cambio_sonido = ("", 0.0)  # otro gesto
        pm.interruptor.setChecked(True)
        self.assertEqual(e._resolucion(), "1080p")
        # Con la estimación medida, el resumen dice cuánto tarda.
        self.assertTrue(esperar(self.app, lambda: e.cuadro_procesado_listo(), 60))
        self.assertIsNotNone(e.estimacion_exportacion())
        self.assertRegex(e.etiqueta_estimacion.text(), r"mejorado a 1920\s×\s1080: tarda más, (menos|alrededor|unos)")  # espacios duros

    def test_deshacer_y_rehacer_la_mejora(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        v, e = self.abrir()
        pm = e.panel_mejora
        inicial = (e.edicion, e.audio, e.mejora)
        e.ir_a(1.0)
        e.cortar()
        paso1 = (e.edicion, e.audio, e.mejora)
        pm.interruptor.setChecked(True)
        paso2 = (e.edicion, e.audio, e.mejora)
        e._ultimo_cambio_sonido = ("", 0.0)
        for valor in (60, 70, 80):  # varios movimientos seguidos de la misma barra: un solo paso
            pm.nitidez.slider.setValue(valor)
        paso3 = (e.edicion, e.audio, e.mejora)
        self.assertEqual(len(e._deshacer), 3)
        for esperado in (paso2, paso1, inicial):
            QTest.keyClick(e, Qt.Key_Z, Qt.ControlModifier)
            self.assertEqual((e.edicion, e.audio, e.mejora), esperado)
        self.assertFalse(pm.interruptor.isChecked())
        self.assertEqual(pm.nitidez.valor(), 50)
        for esperado in (paso1, paso2, paso3):
            QTest.keyClick(e, Qt.Key_Y, Qt.ControlModifier)
            self.assertEqual((e.edicion, e.audio, e.mejora), esperado)
        self.assertTrue(pm.interruptor.isChecked())
        self.assertEqual(pm.nitidez.valor(), 80)
        self.assertEqual(e._resolucion(), "720p")

    def test_juntar_pasos_no_se_pega_al_anterior(self):
        """Arreglo de la revisión: mover un control y volverlo al valor de antes no deja que lo
        siguiente se junte con el paso anterior (que es de otra cosa)."""
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        v, e = self.abrir()
        ps, pm = e.panel_sonido, e.panel_mejora
        # Cortar y después quitar el sonido sí-no-sí, rápido: Ctrl+Z deshace solo el quitar.
        e.ir_a(1.0)
        QTest.keyClick(e, Qt.Key_S)
        cortada = e.edicion
        for valor in (True, False, True):
            ps.interruptor_quitar.setChecked(valor)
        QTest.keyClick(e, Qt.Key_Z, Qt.ControlModifier)
        self.assertIs(e.edicion, cortada)
        self.assertFalse(e.audio.quitar)
        # Volumen 100 -> 110 -> 100 -> 120: Ctrl+Z vuelve a 100 y el corte sigue.
        for valor in (110, 100, 120):
            ps.volumen.slider.setValue(valor)
        QTest.keyClick(e, Qt.Key_Z, Qt.ControlModifier)
        self.assertAlmostEqual(e.audio.volumen, 1.0)
        self.assertIs(e.edicion, cortada)
        # Lo mismo con una barra de la mejora.
        pm.interruptor.setChecked(True)
        e._ultimo_cambio_sonido = ("", 0.0)
        for valor in (60, 50, 70):
            pm.cuadraditos.slider.setValue(valor)
        QTest.keyClick(e, Qt.Key_Z, Qt.ControlModifier)
        self.assertEqual(e.mejora, PRENDIDA)
        QTest.keyClick(e, Qt.Key_Z, Qt.ControlModifier)
        self.assertFalse(e.mejora.activa)
        self.assertIs(e.edicion, cortada)
        QTest.keyClick(e, Qt.Key_Z, Qt.ControlModifier)
        self.assertEqual(e.edicion.tramos_conservados(), [(0.0, 2.0)])
        self.assertEqual(len(e.edicion.segmentos), 1)

    def test_antes_y_despues_con_la_mejora(self):
        from celular_natural.ui.vista_comparacion import VistaComparacion
        v, e = self.abrir()
        e.panel_mejora.interruptor.setChecked(True)
        e.botones_resolucion["1080p"].click()
        e.ir_a(12 / FPS)
        self.assertTrue(esperar(self.app, lambda: e.cuadro_procesado_listo(), 90))
        self.assertEqual(e.vista._tam, (1920, 1080))
        antes, despues = qimage_a_rgb(e.vista._antes), qimage_a_rgb(e.vista._despues)
        self.assertEqual(antes.shape, (1080, 1920, 3))
        self.assertEqual(despues.shape, (1080, 1920, 3))
        # "Antes": el original agrandado simple (bicúbico).
        actual = V.cuadro_en(self.video, 12 / FPS)
        np.testing.assert_array_equal(antes, cv2.resize(actual, (1920, 1080), interpolation=cv2.INTER_CUBIC))
        # "Después": exactamente lo que sale en la exportación (mejora con los vecinos del tramo y filtro).
        vecinos = [V.cuadro_en(self.video, k / FPS) for k in (10, 11, 13, 14)]
        mejorado = M.mejorar_cuadro(actual, vecinos, 1920, 1080, e.mejora)
        esperado = V.procesar_cuadro_seguro(mejorado, e.panel_ajustes.pila(), 12)
        np.testing.assert_array_equal(despues, esperado)
        # Antes y Después se ven distintos (y Lado a lado muestra los dos).
        imagenes = {}
        for modo in (VistaComparacion.MODO_ANTES, VistaComparacion.MODO_DESPUES, VistaComparacion.MODO_LADO):
            e.vista.establecer_modo(modo)
            pausa(self.app, 0.05)
            imagenes[modo] = qimage_a_rgb(e.vista.grab().toImage()).astype(np.float32)
        # (Promedio de toda la vista, con el cuadro achicado al ancho de la ventana: da unos 2 niveles.)
        antes_vs_despues = np.abs(imagenes[VistaComparacion.MODO_ANTES] - imagenes[VistaComparacion.MODO_DESPUES])
        self.assertGreater(float(antes_vs_despues.mean()), 0.8)
        self.assertGreater(float(np.percentile(antes_vs_despues, 99)), 10.0)  # en los bordes, bastante más
        for modo in (VistaComparacion.MODO_ANTES, VistaComparacion.MODO_DESPUES):
            self.assertGreater(float(np.abs(imagenes[modo] - imagenes[VistaComparacion.MODO_LADO]).mean()), 0.8)
        self.assertIn("agrandado simple", [b for b in e.grupo_modo.buttons()
                                           if b.property("modo") == VistaComparacion.MODO_ANTES][0].toolTip())
        # Al reproducir se ve sin la mejora (aparece al pausar).
        e.reproducir()
        self.assertIn("se ve al pausar", e.etiqueta_estado.text())
        e.pausar()

    def test_la_mejora_espera_a_que_el_cursor_se_quede_quieto(self):
        v, e = self.abrir()
        e.panel_mejora.interruptor.setChecked(True)
        self.assertTrue(esperar(self.app, lambda: e.cuadro_procesado_listo(), 60))
        llamadas = []
        original = M.mejorar_cuadro

        def espia(*args, **kw):
            llamadas.append(1)
            return original(*args, **kw)

        with mock.patch.object(M, "mejorar_cuadro", espia):
            # Arrastrando el cursor: solo la vista rápida, sin mejorar (ni se acumulan pedidos).
            for k in range(20, 40, 2):
                e.ir_a(k / FPS, arrastrando=True)
                pausa(self.app, 0.03)
            pausa(self.app, 0.8)
            self.assertEqual(llamadas, [])
            self.assertFalse(e.cuadro_procesado_listo())
            # Al soltar, una sola mejora, después de que se queda quieto.
            e.ir_a(38 / FPS)
            self.assertTrue(esperar(self.app, lambda: e.cuadro_procesado_listo(), 60))
            self.assertEqual(len(llamadas), 1)
            # Volver al mismo cuadro o cambiar el filtro no repite la mejora (caché).
            e.ir_a(20 / FPS)
            self.assertTrue(esperar(self.app, lambda: e.cuadro_procesado_listo(), 60))
            e.ir_a(38 / FPS)
            self.assertTrue(esperar(self.app, lambda: e.cuadro_procesado_listo(), 60))
            self.assertEqual(len(llamadas), 2)

    def test_exportar_a_1080p_con_la_mejora(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from celular_natural.ui import editor_video as E
        v, e = self.abrir()
        e.panel_mejora.interruptor.setChecked(True)
        e.botones_resolucion["1080p"].click()
        e.ir_a(0.5)
        e.cortar()
        e.ir_a(1.0)
        e.cortar()
        e.linea.seleccionar(1)
        e.borrar_tramo()  # quedan de 0 a 0,5 y de 1 a 2 s
        llamadas = []
        original = E.mv.exportar_video

        def espia(*args, **kw):
            llamadas.append(kw.get("mejora"))
            return original(*args, **kw)

        destino = self.dir / "desde_la_ventana.mp4"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "")), \
                mock.patch.object(QMessageBox, "information") as aviso, \
                mock.patch.object(E.mv, "exportar_video", espia):
            e.exportar()
            self.assertTrue(esperar(self.app, lambda: not e.exportando, 300))
        self.assertEqual(llamadas, [PRENDIDA])
        self.assertIn("calidad mejorada", aviso.call_args.args[2])
        r = e.ultima_exportacion
        self.assertEqual((r.ancho, r.alto), (1920, 1080))
        self.assertTrue(r.con_audio)
        cuadros, audio, datos = leer_video(destino)
        self.assertEqual((datos["ancho"], datos["alto"]), (1920, 1080))
        self.assertEqual([codigo_grande(c) for c in cuadros], list(range(12)) + list(range(24, 48)))
        self.assertAlmostEqual(audio.shape[1] / datos["frecuencia"], 1.5, delta=0.03)

    def test_el_tramo_elegido_al_deshacer(self):
        """Arreglo de la revisión: al deshacer un corte, lo elegido no pasa a ser otro tramo."""
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        v, e = self.abrir()
        e.ir_a(1.5)
        e.cortar()
        e.ir_a(0.5)
        e.cortar()  # queda elegido el tramo de 0,5 a 1,5
        s = e.edicion.segmentos[e.linea.seleccion]
        self.assertEqual((s.inicio, s.fin), (0.5, 1.5))
        QTest.keyClick(e, Qt.Key_Z, Qt.ControlModifier)
        self.assertEqual(e.linea.seleccion, -1)  # antes quedaba elegido el de 1,5 a 2 (el mismo índice)
        QTest.keyClick(e, Qt.Key_Y, Qt.ControlModifier)
        e.linea.seleccionar(2)  # de 1,5 a 2: también existe sin el corte de 0,5
        QTest.keyClick(e, Qt.Key_Z, Qt.ControlModifier)
        s = e.edicion.segmentos[e.linea.seleccion]
        self.assertEqual((s.inicio, s.fin), (1.5, 2.0))

    def test_el_pico_viejo_no_se_mide(self):
        """Arreglo de la revisión: con Normalizar, los cambios seguidos no encolan mediciones del
        pico que ya no sirven; la clave lleva la ruta."""
        from celular_natural.ui import editor_video as E
        v, e = self.abrir()
        for t in (0.4, 0.8, 1.2, 1.6):
            e.ir_a(t)
            e.cortar()
        llamadas = []

        def lenta(_ruta, _tramos, silencios, cancelado=None):
            llamadas.append(("empieza", silencios))
            fin = time.monotonic() + 0.4
            while time.monotonic() < fin:
                if cancelado is not None and cancelado():
                    raise Cancelado()
                time.sleep(0.01)
            llamadas.append(("termina", silencios))
            return 0.3

        with mock.patch.object(E.ma, "medir_pico", lenta):
            e.panel_sonido.check_normalizar.setChecked(True)
            for i in range(4):
                e.linea.seleccionar(i)
                e.silenciar_tramo()
            self.assertTrue(esperar(self.app, lambda: e._clave_pico() in e._picos and not e._midiendo_pico, 30))
        clave = e._clave_pico()
        self.assertEqual(clave[0], e.ruta)
        terminadas = [s for tipo, s in llamadas if tipo == "termina"]
        self.assertEqual(terminadas, [clave[2]])  # solo la que hace falta
        self.assertLessEqual(len([1 for tipo, _s in llamadas if tipo == "empieza"]), 2)


if __name__ == "__main__":
    unittest.main()
