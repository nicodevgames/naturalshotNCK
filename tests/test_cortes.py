"""Pruebas de los cortes que desaparecen de la línea de tiempo del modo Video.

* Motor (``motor/video.py``, sin Qt): ``MapaTiempo`` (tiempo original ↔ tiempo del
  resultado, con números y con arreglos), ``huecos``, ``segmentos_visibles`` y
  ``recuperar_hueco``.
* Piezas sueltas: la ``LineaTiempo`` dibuja el resultado (lo que sigue a un borrado
  se corre, sus miniaturas también, una marquita por unión con su menú "Recuperar lo
  borrado", y los corchetes recortan) y la ``PistaOnda`` con ``solo_resultado``.
* La ventana real (modo sin pantalla): borrar achica la duración y la línea de
  tiempo; la miniatura que estaba después de lo borrado queda donde empezaba; la
  marquita y "Recuperar lo borrado" (tocándola, con el menú contextual y con R);
  Ctrl+Z y Ctrl+Y; recortar el principio con la entrada y con el corchete; Silenciar
  tramo después de un borrado (en tiempo original); el cursor nunca queda en algo
  borrado; y al reproducir el cursor avanza en el tiempo del resultado.

Los videos se generan en una carpeta temporal (``test_video.generar_video``: 3 s a
24 cuadros por segundo, con el número de cada cuadro y sonido por segundo). Para
esperar se usa ``time.sleep`` y ``processEvents`` (``QTest.qWait`` no suelta el GIL).
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

from celular_natural.motor import video as V  # noqa: E402

FPS = 24


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


def raton(widget, tipo: str, x: float, y: float, boton=None) -> None:
    """Un evento del mouse sobre ``widget``: "apretar", "mover" o "soltar"."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    boton = Qt.LeftButton if boton is None else boton
    tipos = {"apretar": QEvent.MouseButtonPress, "mover": QEvent.MouseMove, "soltar": QEvent.MouseButtonRelease}
    botones = Qt.NoButton if tipo == "soltar" else boton
    pos = QPointF(x, y)
    QApplication.sendEvent(widget, QMouseEvent(tipos[tipo], pos, widget.mapToGlobal(pos), boton if tipo != "mover"
                                               else Qt.NoButton, botones, Qt.NoModifier))


def tocar(widget, x: float, y: float) -> None:
    raton(widget, "apretar", x, y)
    raton(widget, "soltar", x, y)


def borrado_en_el_medio() -> "V.EdicionVideo":
    """3 s cortados en 1 y en 2, con el del medio borrado: quedan de 0 a 1 y de 2 a 3."""
    return V.EdicionVideo.nueva(3.0, FPS).cortar(1.0).cortar(2.0).con_borrado(1)


# ---------------------------------------------------------------------------
# Motor
# ---------------------------------------------------------------------------

class PruebasMapa(unittest.TestCase):
    def test_original_y_resultado_ida_y_vuelta(self):
        m = V.MapaTiempo.de_edicion(borrado_en_el_medio())
        self.assertEqual(m.tramos, ((0.0, 1.0), (2.0, 3.0)))
        self.assertAlmostEqual(m.duracion, 2.0)
        self.assertEqual(m.inicios_resultado, (0.0, 1.0))
        # Del original al resultado: lo borrado va a la unión; después del final, al final.
        for t, r in ((0.0, 0.0), (0.5, 0.5), (0.99, 0.99), (1.0, 1.0), (1.5, 1.0), (2.0, 1.0), (2.5, 1.5),
                     (3.0, 2.0), (9.0, 2.0)):
            self.assertAlmostEqual(m.a_resultado(t), r, msg=f"t={t}")
        # Del resultado al original: justo en la unión, el comienzo de lo que sigue.
        for r, t in ((0.0, 0.0), (0.5, 0.5), (1.0, 2.0), (1.5, 2.5), (2.0, 3.0), (5.0, 3.0)):
            self.assertAlmostEqual(m.a_original(r), t, msg=f"r={r}")
        # Con arreglos, lo mismo (para convertir columnas de una vez).
        np.testing.assert_allclose(m.a_resultado(np.array([0.25, 1.5, 2.75])), [0.25, 1.0, 1.75])
        np.testing.assert_allclose(m.a_original(np.array([0.25, 1.0, 1.75])), [0.25, 2.0, 2.75])
        self.assertIsInstance(m.a_resultado(0.3), float)
        # Ida y vuelta en cada cuadro que se ve.
        for k in list(range(0, 24)) + list(range(48, 72)):
            t = k / FPS
            self.assertAlmostEqual(m.a_original(m.a_resultado(t)), t, places=9)
        self.assertTrue(m.visible(0.5) and m.visible(2.0))
        self.assertFalse(m.visible(1.0) or m.visible(1.99) or m.visible(3.0))
        # Las partes de un rango que se ven, en el resultado.
        self.assertEqual(m.rangos_resultado(0.5, 2.5), [(0.5, 1.0), (1.0, 1.5)])
        self.assertEqual(m.rangos_resultado(1.2, 1.8), [])
        # Inmutable y comparable (sirve de clave de caché).
        self.assertEqual(m, V.MapaTiempo.de_edicion(borrado_en_el_medio()))
        self.assertEqual(hash(m), hash(V.MapaTiempo.de_edicion(borrado_en_el_medio())))

    def test_identidad_y_sin_nada(self):
        m = V.MapaTiempo.identidad(3.0)
        self.assertAlmostEqual(m.a_resultado(1.7), 1.7)
        self.assertAlmostEqual(m.a_original(1.7), 1.7)
        self.assertEqual(m.huecos(), [])
        vacio = V.MapaTiempo((), 3.0)
        self.assertEqual((vacio.duracion, vacio.a_resultado(1.0), vacio.a_original(1.0)), (0.0, 0.0, 0.0))
        self.assertEqual(vacio.huecos(), [V.Hueco(0.0, 3.0, 0.0, principio=True, final=True)])

    def test_huecos_y_recuperar(self):
        e = borrado_en_el_medio().con_entrada(0.5).con_salida(2.5)
        fin = 2.5 + 1 / FPS  # la salida incluye el cuadro del cursor
        m = V.MapaTiempo.de_edicion(e)
        huecos = m.huecos()
        self.assertEqual(len(huecos), 3)
        principio, medio, final = huecos
        self.assertEqual((principio.inicio, principio.fin, principio.en), (0.0, 0.5, 0.0))
        self.assertTrue(principio.principio and not principio.final)
        self.assertEqual((medio.inicio, medio.fin), (1.0, 2.0))
        self.assertAlmostEqual(medio.en, 0.5)
        self.assertFalse(medio.principio or medio.final)
        self.assertAlmostEqual(final.inicio, fin)
        self.assertAlmostEqual(final.en, m.duracion)
        self.assertTrue(final.final)
        self.assertAlmostEqual(medio.duracion, 1.0)
        # Recuperar cada uno vuelve a poner solo lo suyo (y los cortes quedan).
        self.assertEqual(V.recuperar_hueco(e, principio).tramos_conservados(), [(0.0, 1.0), (2.0, fin)])
        self.assertEqual(V.recuperar_hueco(e, medio).tramos_conservados(), [(0.5, fin)])
        self.assertEqual(V.recuperar_hueco(e, final).tramos_conservados(), [(0.5, 1.0), (2.0, 3.0)])
        self.assertEqual(len(V.recuperar_hueco(e, medio).segmentos), 3)
        # Sin nada que recuperar ahí: la misma edición.
        sin_cortes = V.EdicionVideo.nueva(3.0, FPS)
        self.assertIs(V.recuperar_hueco(sin_cortes, V.Hueco(1.0, 2.0, 1.0)), sin_cortes)
        # Todo borrado: un solo hueco que lo recupera todo.
        todo = V.EdicionVideo.nueva(3.0, FPS).cortar(1.0).con_borrado(0).con_borrado(1).con_entrada(0.5)
        unico = V.MapaTiempo.de_edicion(todo).huecos()
        self.assertEqual(len(unico), 1)
        self.assertEqual(V.recuperar_hueco(todo, unico[0]).tramos_conservados(), [(0.0, 3.0)])

    def test_segmentos_visibles(self):
        e = borrado_en_el_medio().con_entrada(0.5)
        self.assertEqual(V.segmentos_visibles(e), [(0, 0.5, 1.0), (2, 2.0, 3.0)])
        self.assertEqual(V.segmentos_visibles(V.EdicionVideo.nueva(3.0, FPS)), [(0, 0.0, 3.0)])


# ---------------------------------------------------------------------------
# Piezas sueltas
# ---------------------------------------------------------------------------

class PruebasPiezas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def miniaturas(self):
        """Seis miniaturas de un color cada una, en 0,25, 0,75, … 2,75 s."""
        from PySide6.QtGui import QColor, QImage
        colores = ["#ff0000", "#00ff00", "#0000ff", "#ffff00", "#00ffff", "#ff00ff"]
        lista = []
        for k, color in enumerate(colores):
            img = QImage(96, 72, QImage.Format_RGB888)
            img.fill(QColor(color))
            lista.append(((k + 0.5) * 0.5, img))
        return lista, colores

    def test_linea_muestra_el_resultado(self):
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QColor
        from celular_natural.ui import estilo
        from celular_natural.ui.linea_tiempo import MARGEN, LineaTiempo
        linea = LineaTiempo()
        linea.resize(2 * MARGEN + 600, linea.sizeHint().height())
        miniaturas, colores = self.miniaturas()
        linea.establecer_miniaturas(miniaturas)
        linea.establecer_edicion(V.EdicionVideo.nueva(3.0, FPS).cortar(1.0).cortar(2.0))
        self.assertEqual(linea.huecos, [])
        x_borrado = linea.x_de(1.0)  # donde empieza lo que se va a borrar
        self.assertAlmostEqual(x_borrado, MARGEN + 200)
        linea.establecer_edicion(borrado_en_el_medio())
        # La línea mide el resultado (2 s): 300 px por segundo y lo borrado ya no ocupa lugar.
        self.assertAlmostEqual(linea.mapa.duracion, 2.0)
        self.assertAlmostEqual(linea.x_de(2.0), MARGEN + 300)
        self.assertAlmostEqual(linea.x_de(1.5), linea.x_de(2.0))
        self.assertAlmostEqual(linea.tiempo_en(MARGEN + 450), 2.5)
        # Ninguna miniatura de lo borrado (1,25 y 1,75 s), y la primera de después (2,25 s) arranca en
        # la unión: donde empezaba lo borrado en el resultado.
        celdas = linea.celdas()
        usadas = {miniaturas[j][0] for _r, j in celdas}
        self.assertFalse(usadas & {1.25, 1.75})
        despues = [r for r, j in celdas if miniaturas[j][0] == 2.25]
        self.assertAlmostEqual(despues[0].left(), linea.x_de_resultado(1.0))
        img = linea.grab().toImage()
        y = linea._pista().center().y()
        self.assertEqual(QColor(img.pixel(round(linea.x_de_resultado(1.0)) + 8, round(y))).name(), colores[4])
        self.assertEqual(QColor(img.pixel(round(linea.x_de_resultado(1.0)) - 8, round(y))).name(), colores[1])
        # La marquita: una costura rosa en la unión.
        rosa = QColor(img.pixel(round(linea.x_de_resultado(1.0)), round(y)))
        self.assertGreater(rosa.red(), 200)
        self.assertLess(rosa.green(), 120)
        self.assertEqual(rosa.name(), QColor(estilo.ROSA).name())
        # Tocar la línea: pide el instante del original y elige el segmento que se ve ahí.
        pedidos = []
        linea.tiempoPedido.connect(lambda t, arrastrando: pedidos.append((round(t, 3), arrastrando)))
        tocar(linea, MARGEN + 450, y)
        self.assertEqual(pedidos, [(2.5, True), (2.5, False)])
        self.assertEqual(linea.seleccion, 2)
        linea.seleccionar(1)  # el borrado no se elige
        self.assertEqual(linea.seleccion, -1)
        # La marquita: tocar su pestaña abre el menú y "Recuperar lo borrado" pide ese hueco.
        pedidos_recuperar = []
        linea.recuperarPedido.connect(pedidos_recuperar.append)
        pestana = linea.pestana(0)
        self.assertEqual(linea.union_en(pestana.center()), 0)
        self.assertEqual(linea.union_en(QPointF(MARGEN + 100, y)), -1)
        tocar(linea, pestana.center().x(), pestana.center().y())
        self.assertTrue(linea.menu_union.isVisible())
        textos = [a.text() for a in linea.menu_union.actions()]
        self.assertIn("Recuperar lo borrado", textos)
        self.assertIn("Borrado acá: 1,0 s", textos)
        self.assertEqual(pedidos, [(2.5, True), (2.5, False)])  # tocar la marquita no mueve el cursor
        next(a for a in linea.menu_union.actions() if a.text() == "Recuperar lo borrado").trigger()
        self.assertEqual(pedidos_recuperar, [V.Hueco(1.0, 2.0, 1.0)])
        linea.menu_union.close()

    def test_corchetes_recortan_lo_que_se_ve(self):
        from celular_natural.ui.linea_tiempo import MARGEN, LineaTiempo
        linea = LineaTiempo()
        linea.resize(2 * MARGEN + 600, linea.sizeHint().height())
        linea.establecer_edicion(borrado_en_el_medio())
        pedidos = []
        linea.limitesPedidos.connect(lambda entrada, salida: pedidos.append((round(entrada, 4), salida)))
        y = linea._pista().center().y()
        # La entrada, arrastrada hasta el segundo 1,5 del resultado (2,5 del original, pasando lo borrado).
        raton(linea, "apretar", MARGEN, y)
        raton(linea, "mover", linea.x_de_resultado(1.5), y)
        raton(linea, "soltar", linea.x_de_resultado(1.5), y)
        self.assertEqual(pedidos, [(2.5, None)])
        # La salida, hasta el segundo 0,5 del resultado.
        raton(linea, "apretar", MARGEN + 600, y)
        raton(linea, "mover", linea.x_de_resultado(0.5), y)
        raton(linea, "soltar", linea.x_de_resultado(0.5), y)
        self.assertEqual(pedidos[-1][0], 0.0)
        self.assertAlmostEqual(pedidos[-1][1], 0.5)
        # Soltar donde estaba no pide nada.
        raton(linea, "apretar", MARGEN, y)
        raton(linea, "soltar", MARGEN, y)
        self.assertEqual(len(pedidos), 2)

    def test_pista_solo_con_lo_que_se_exporta(self):
        from PySide6.QtCore import QPointF
        from celular_natural.motor import audio as A
        from celular_natural.ui.forma_onda import PistaOnda, onda_en_resultado
        # 4 s con un volumen por segundo: 0,2, 0,9 (el que se borra), 0,6 y 0,4.
        n = 4000
        niveles = np.repeat([0.2, 0.9, 0.6, 0.4], n // 4).astype(np.float32)
        forma = A.FormaOnda(4.0, -niveles, niveles, n)
        mapa = V.MapaTiempo(((0.0, 1.0), (2.0, 4.0)), 4.0)
        minimos, maximos = onda_en_resultado(forma, mapa, 300)
        np.testing.assert_allclose(maximos[:100], 0.2)
        np.testing.assert_allclose(maximos[100:200], 0.6)
        np.testing.assert_allclose(maximos[200:], 0.4)
        np.testing.assert_allclose(minimos, -maximos)
        # Una columna que cruza la unión toma los dos lados, nunca lo de en medio (el 0,9).
        _mi, ma = onda_en_resultado(forma, mapa, 2)
        np.testing.assert_allclose(ma, [0.6, 0.6])
        # La pista: mide el resultado (3 s, 100 px por segundo) y habla en tiempo original.
        pista = PistaOnda(solo_resultado=True)
        pista.resize(14 * 2 + 300, 46)
        pista.establecer_forma(forma)
        pista.establecer_edicion(list(mapa.tramos), A.AjustesAudio(silencios=((2.5, 3.0),)))
        self.assertAlmostEqual(pista._x(2.5), 14 + 150)
        self.assertAlmostEqual(pista._x(1.5), pista._x(2.0))  # lo borrado no ocupa lugar
        self.assertAlmostEqual(pista.tiempo_en(14 + 150), 2.5)
        self.assertEqual([(round(a), round(b)) for a, b in pista._franjas(pista._ajustes.silencios)],
                         [(14 + 150, 14 + 200)])
        pista.grab()
        pedidos = []
        pista.presionada.connect(lambda t: pedidos.append(round(t, 2)))
        tocar(pista, 14 + 250, 20)
        self.assertEqual(pedidos, [3.5])
        # Sin solo_resultado (otros usos de la pieza): todo el original, como siempre.
        otra = PistaOnda()
        otra.resize(14 * 2 + 400, 46)
        otra.establecer_forma(forma)
        otra.establecer_edicion(list(mapa.tramos), A.AjustesAudio())
        self.assertAlmostEqual(otra._x(2.5), 14 + 250)


# ---------------------------------------------------------------------------
# La ventana real
# ---------------------------------------------------------------------------

@unittest.skipIf(av is None, "Falta PyAV (pip install av==19.0.1)")
class PruebasVentanaCortes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_video import generar_video
        cls.app = _app()
        cls.dir = Path(tempfile.mkdtemp(prefix="naturalshot_cortes_"))
        cls._entorno = {k: os.environ.get(k) for k in ("APPDATA", "NATURALSHOT_CONFIG")}
        os.environ["APPDATA"] = str(cls.dir / "appdata")
        cls.config = cls.dir / "config.ini"
        os.environ["NATURALSHOT_CONFIG"] = str(cls.config)
        cls.video = generar_video(cls.dir / "clip.mp4")  # 3 s: 440 Hz, silencio, 880 Hz

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
        """Una ventana nueva en el modo Video con el clip abierto, las miniaturas y la forma de onda."""
        from celular_natural.ui.ventana import VentanaPrincipal
        v = VentanaPrincipal()
        self.ventanas.append(v)
        v.resize(1366, 768)
        v.show()
        v.activateWindow()  # los atajos (Supr, Ctrl+Z) andan en la ventana activa
        v.abrir_rutas([str(self.video)])
        e = v.editor_video
        self.assertTrue(esperar(self.app, lambda: e.info is not None and e.cuadro_procesado_listo()))
        self.assertTrue(esperar(self.app, lambda: bool(e.linea._miniaturas)
                                and e.pista_sonido.estado in ("lista", "sin_sonido")))
        return v, e

    def cortar_y_borrar_el_medio(self, e):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        e.ir_a(1.0)
        e.cortar()
        e.ir_a(2.0)
        e.cortar()
        e.linea.seleccionar(1)
        QTest.keyClick(e, Qt.Key_Delete)
        self.assertEqual(e.edicion.tramos_conservados(), [(0.0, 1.0), (2.0, 3.0)])

    # ------------------------------------------------------------ pruebas
    def test_borrar_achica_la_linea_y_corre_las_miniaturas(self):
        v, e = self.abrir()
        linea = e.linea
        self.assertIn("/ 0:03,00", e.etiqueta_tiempo.text())
        e.ir_a(1.0)
        e.cortar()
        e.ir_a(2.0)
        e.cortar()
        primera_despues = min(j for j, (t, _img) in enumerate(linea._miniaturas) if t >= 2.0)
        x_antes = linea.x_de(1.0)
        self.assertAlmostEqual(x_antes, linea._pista().left() + linea._pista().width() / 3)
        e.linea.seleccionar(1)
        e.borrar_tramo()
        # La duración que se muestra y la línea: 2 s.
        self.assertAlmostEqual(e.mapa.duracion, 2.0)
        self.assertAlmostEqual(linea.mapa.duracion, 2.0)
        self.assertIn("/ 0:02,00", e.etiqueta_tiempo.text())
        self.assertIn("de 48", e.etiqueta_cuadro.text())
        self.assertIn("0:02,00", e.etiqueta_resultado.text())
        self.assertIn("de 0:03,00", e.etiqueta_resultado.text())
        self.assertIn("Tramo borrado", e.etiqueta_estado.text())
        self.assertNotIn("Restaurar", e.boton_borrar.text())
        # Lo borrado no ocupa lugar y lo que seguía empieza en la unión, a la mitad de la línea.
        self.assertAlmostEqual(linea.x_de(1.0), linea.x_de(2.0))
        mitad = linea._pista().left() + linea._pista().width() / 2
        self.assertAlmostEqual(linea.x_de_resultado(1.0), mitad)
        celdas = linea.celdas()
        self.assertFalse(any(1.0 <= linea._miniaturas[j][0] < 2.0 for _r, j in celdas))
        rect = next(r for r, j in celdas if j == primera_despues)
        self.assertAlmostEqual(rect.left(), mitad)
        # La pista de sonido, igual: solo lo que se exporta.
        self.assertTrue(e.pista_sonido.solo_resultado)
        self.assertAlmostEqual(e.pista_sonido.mapa.duracion, 2.0)
        self.assertAlmostEqual(e.pista_sonido._x(2.0), e.pista_sonido._x(1.0))
        # El cursor estaba en 2 s (se ve): en el resultado queda en la unión.
        self.assertAlmostEqual(e.tiempo, 2.0)
        self.assertAlmostEqual(e.tiempo_resultado, 1.0)
        self.assertIn("Tocá una marquita", e.ayuda_linea.text())

    def test_marquita_recuperar_y_deshacer(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtGui import QContextMenuEvent
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        v, e = self.abrir()
        self.cortar_y_borrar_el_medio(e)
        linea = e.linea
        self.assertEqual(len(linea.huecos), 1)
        # Tocar la marquita: menú con "Recuperar lo borrado".
        pestana = linea.pestana(0)
        tocar(linea, pestana.center().x(), pestana.center().y())
        menu = linea.menu_union
        self.assertTrue(menu.isVisible())
        accion = next(a for a in menu.actions() if a.text() == "Recuperar lo borrado")
        accion.trigger()
        menu.close()
        self.assertEqual(e.edicion.tramos_conservados(), [(0.0, 3.0)])
        self.assertEqual(linea.huecos, [])
        self.assertAlmostEqual(e.mapa.duracion, 3.0)
        self.assertAlmostEqual(e.tiempo, 1.0)  # el cursor, al comienzo de lo recuperado
        self.assertIn("Se recuperó", e.etiqueta_estado.text())
        self.assertEqual(len(e.edicion.segmentos), 3)  # los cortes quedan
        # Ctrl+Z vuelve a sacarlo, otro Ctrl+Z deshace el borrado de siempre, y Ctrl+Y rehace los dos.
        QTest.keyClick(e, Qt.Key_Z, Qt.ControlModifier)
        self.assertEqual(e.edicion.tramos_conservados(), [(0.0, 1.0), (2.0, 3.0)])
        self.assertAlmostEqual(e.tiempo, 2.0)  # el cursor no queda en lo borrado
        self.assertEqual(len(linea.huecos), 1)
        QTest.keyClick(e, Qt.Key_Z, Qt.ControlModifier)
        self.assertEqual(e.edicion.tramos_conservados(), [(0.0, 3.0)])
        self.assertEqual(linea.huecos, [])
        QTest.keyClick(e, Qt.Key_Y, Qt.ControlModifier)
        self.assertEqual(e.edicion.tramos_conservados(), [(0.0, 1.0), (2.0, 3.0)])
        QTest.keyClick(e, Qt.Key_Y, Qt.ControlModifier)
        self.assertEqual(e.edicion.tramos_conservados(), [(0.0, 3.0)])
        QTest.keyClick(e, Qt.Key_Z, Qt.ControlModifier)
        # Con el menú contextual (botón derecho cerca de la unión).
        x = round(linea.x_de_resultado(1.0)) + 3
        y = round(linea._pista().center().y())
        QApplication.sendEvent(linea, QContextMenuEvent(QContextMenuEvent.Mouse, QPoint(x, y),
                                                        linea.mapToGlobal(QPoint(x, y))))
        self.assertTrue(linea.menu_union.isVisible())
        self.assertIn("Recuperar lo borrado", [a.text() for a in linea.menu_union.actions()])
        linea.menu_union.close()
        # Con el teclado: R recupera lo borrado más cerca del cursor.
        QTest.keyClick(e, Qt.Key_R)
        self.assertEqual(e.edicion.tramos_conservados(), [(0.0, 3.0)])
        QTest.keyClick(e, Qt.Key_R)
        self.assertIn("No hay nada borrado", e.etiqueta_estado.text())

    def test_recortar_el_principio_con_la_entrada(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        v, e = self.abrir()
        linea = e.linea
        e.ir_a(0.5)
        QTest.keyClick(e, Qt.Key_I)
        self.assertEqual(e.edicion.entrada, 0.5)
        self.assertAlmostEqual(e.mapa.duracion, 2.5)
        self.assertAlmostEqual(e.tiempo_resultado, 0.0)  # el cursor queda al principio de lo que se ve
        self.assertIn("Principio recortado", e.etiqueta_estado.text())
        huecos = linea.huecos
        self.assertEqual(len(huecos), 1)
        self.assertTrue(huecos[0].principio)
        self.assertAlmostEqual(linea.x_de_resultado(huecos[0].en), linea._pista().left())
        # Ir al principio (Inicio) o pedir algo de antes lleva a lo primero que se ve.
        e.ir_a(0.1)
        self.assertAlmostEqual(e.tiempo, 0.5)
        QTest.keyClick(e, Qt.Key_End)
        QTest.keyClick(e, Qt.Key_Home)
        self.assertAlmostEqual(e.tiempo, 0.5)
        # Recuperarlo con su marquita.
        pestana = linea.pestana(0)
        tocar(linea, pestana.center().x(), pestana.center().y())
        self.assertTrue(linea.menu_union.isVisible())
        self.assertIn("Recortado del principio: 0,5 s", [a.text() for a in linea.menu_union.actions()])
        next(a for a in linea.menu_union.actions() if a.text() == "Recuperar lo borrado").trigger()
        linea.menu_union.close()
        self.assertEqual(e.edicion.entrada, 0.0)
        self.assertAlmostEqual(e.tiempo, 0.0)
        # Arrastrando el corchete de la entrada hasta el segundo 1 (lo de antes desaparece al soltar).
        y = linea._pista().center().y()
        raton(linea, "apretar", linea.x_de_resultado(0.0), y)
        raton(linea, "mover", linea.x_de_resultado(1.0), y)
        self.assertEqual(e.edicion.entrada, 0.0)  # mientras se arrastra, todavía no
        raton(linea, "soltar", linea.x_de_resultado(1.0), y)
        self.assertAlmostEqual(e.edicion.entrada, 1.0)
        self.assertAlmostEqual(e.mapa.duracion, 2.0)
        self.assertAlmostEqual(e.tiempo, 1.0)  # el cursor estaba en lo recortado: pasa a lo primero
        # Y la salida (O) también desaparece, con su marquita al final.
        e.ir_a(2.0)
        QTest.keyClick(e, Qt.Key_O)
        self.assertAlmostEqual(e.mapa.duracion, 1.0 + 1 / FPS)
        self.assertTrue(linea.huecos[-1].final)
        QTest.keyClick(e, Qt.Key_Z, Qt.ControlModifier)
        QTest.keyClick(e, Qt.Key_Z, Qt.ControlModifier)
        self.assertEqual(e.edicion.entrada, 0.0)

    def test_silenciar_despues_de_borrar_va_en_tiempo_original(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        v, e = self.abrir()
        self.cortar_y_borrar_el_medio(e)
        linea = e.linea
        # Tocar la línea en el segundo 1,5 del resultado: es el 2,5 del original (el último tramo).
        tocar(linea, linea.x_de_resultado(1.5), linea._pista().center().y())
        self.assertAlmostEqual(e.tiempo, 2.5)
        self.assertEqual(linea.seleccion, 2)
        QTest.keyClick(e, Qt.Key_M)
        self.assertEqual(e.audio.silencios, ((2.0, 3.0),))
        self.assertIn("de 0:01,00 a 0:02,00", e.etiqueta_estado.text())  # lo que se ve en la regla
        # La pista lo dibuja en el resultado: de la mitad al final.
        pista = e.pista_sonido
        (x0, x1), = pista._franjas(e.audio.silencios)
        self.assertAlmostEqual(x0, pista._xd(1.0))
        self.assertAlmostEqual(x1, pista._xd(2.0))
        # Recuperar lo borrado no mueve el silencio (va en tiempo original).
        e.recuperar(linea.huecos[0])
        self.assertEqual(e.audio.silencios, ((2.0, 3.0),))

    def test_el_cursor_nunca_cae_en_lo_borrado(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        v, e = self.abrir()
        self.cortar_y_borrar_el_medio(e)
        e.ir_a(1.5)
        self.assertAlmostEqual(e.tiempo, 2.0)
        QTest.keyClick(e, Qt.Key_Left)  # un cuadro atrás: el último antes de la unión
        self.assertAlmostEqual(e.tiempo, 1 - 1 / FPS)
        QTest.keyClick(e, Qt.Key_Right)
        self.assertAlmostEqual(e.tiempo, 2.0)
        QTest.keyClick(e, Qt.Key_J)
        self.assertAlmostEqual(e.tiempo, 0.0)
        QTest.keyClick(e, Qt.Key_End)
        self.assertAlmostEqual(e.tiempo, 3 - 1 / FPS)
        # Borrar el tramo donde está el cursor (sin elegir ninguno): el cursor pasa a la unión.
        e.ir_a(0.5)
        e.linea.seleccionar(-1)
        QTest.keyClick(e, Qt.Key_Delete)
        self.assertEqual(e.edicion.tramos_conservados(), [(2.0, 3.0)])
        self.assertAlmostEqual(e.tiempo, 2.0)
        # No se puede borrar todo: queda lo último y el botón lo dice.
        self.assertFalse(e.boton_borrar.isEnabled())
        self.assertIn("lo único que queda", e.boton_borrar.toolTip())
        antes = e.edicion
        QTest.keyClick(e, Qt.Key_Delete)
        self.assertIs(e.edicion, antes)
        self.assertIn("no se puede borrar todo", e.etiqueta_estado.text())
        self.assertTrue(esperar(self.app, e.cuadro_procesado_listo))  # y la vista previa muestra lo que se ve

    def test_reproducir_avanza_en_tiempo_del_resultado(self):
        from celular_natural.ui import editor_video as E
        v, e = self.abrir()
        self.cortar_y_borrar_el_medio(e)
        e.ir_a(0.5)
        reloj = [1000.0]
        falso = types.SimpleNamespace(monotonic=lambda: reloj[0], perf_counter=time.perf_counter)
        with mock.patch.object(E, "time", falso):
            e.reproducir()
            self.assertTrue(e.reproduciendo)
            self.assertFalse(e._con_sonido)  # sin pantalla no suena: el reloj es el propio
            vistos = []
            for paso in (0.2, 0.2, 0.2, 0.2, 0.2):  # cruza la unión (segundo 1 del resultado)
                reloj[0] += paso
                e._tick()
                self.app.processEvents()
                vistos.append((round(e.linea.tiempo_resultado, 4), round(e.tiempo, 4)))
            # El cursor de la línea avanza de corrido en el resultado (al cuadro): 0,7 0,9 1,1 1,3 1,5.
            for (r, t), esperado in zip(vistos, (0.7, 0.9, 1.1, 1.3, 1.5)):
                self.assertAlmostEqual(r, int(esperado * FPS + 1e-6) / FPS, places=4)
                self.assertTrue(e.mapa.visible(t), f"el cursor quedó en lo borrado: {t}")
            # Y en el original salta lo borrado: de 0,875 a 2,083.
            self.assertAlmostEqual(vistos[1][1], 0.875, places=4)
            self.assertAlmostEqual(vistos[2][1], 2 + 2 / FPS, places=4)
            self.assertIn("0:01,50 / 0:02,00", e.etiqueta_tiempo.text())
            # Al llegar al final de lo que se ve, pausa en el último cuadro.
            reloj[0] += 1.0
            e._tick()
            self.assertFalse(e.reproduciendo)
            self.assertAlmostEqual(e.tiempo, 3 - 1 / FPS)


if __name__ == "__main__":
    unittest.main()
