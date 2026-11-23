"""Pruebas de la Etapa 2, U3, del modo Photoshop de NaturalShot Lite (ventana real, sin pantalla).

* **Pincel (B):** con el mouse simulado deja píxeles del color de frente y es **un solo paso**; mientras
  se arrastra se ve en una superposición (sin pasos ni recomponer); sobre la base crea una capa de
  píxeles nueva (en el mismo paso); afuera de la capa, la capa crece.
* **Borrador (E):** baja el alfa.
* **Pintar sobre un texto** pregunta "¿Rasterizar la capa?": con No, nada; con Sí, lo rasteriza.
* **Bote (G):** contiguo y global, y "Todas las capas" (la zona sale de la composición).
* **Degradado (Mayús+G):** sobre la base crea una capa de relleno (lineal, con esos puntos) o de píxeles
  (radial); sobre una capa de píxeles, la pinta.
* **Recortar (C):** las manijas cambian el tamaño del documento con Enter; con Esc, no. En una foto,
  con su recorte no destructivo. El botón del kit elige la herramienta.
* **Teclas:** ``[`` y ``]``, B, E, G, Mayús+G y C; Esc durante un trazo lo descarta.
* **Pegar** una imagen copiada de otra app (con transparencia, en formato PNG) y sin documento.
* **Sesión y proyecto** con una capa pintada; deshacer un trazo vuelve la imagen de antes (aunque esté
  comprimida en la memoria del historial).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_modo_photoshop import _Base  # noqa: E402  (también arma el entorno: offscreen, Lite…)

from celular_natural.motor.documento import componer  # noqa: E402


class _BaseU3(_Base):
    def accion(self, atajo: str):
        from PySide6.QtGui import QKeySequence
        return next(a for a in self.v._pagina_fotos.actions() if a.shortcut() == QKeySequence(atajo))

    def capa_pixeles(self) -> str:
        """Capa › Nueva › Capa de píxeles: devuelve su id (queda elegida)."""
        v = self.v
        antes = {c.id for c in v._documento.capas}
        v.photoshop.nueva_capa_pixeles()
        self.esperar()
        return next(c.id for c in v._documento.capas if c.id not in antes)

    def imagen(self, id_capa) -> np.ndarray:
        v = self.v
        return v._arreglo(v._documento.capa(id_capa).imagen)

    def poner_imagen(self, id_capa, arr) -> None:
        v = self.v
        doc = v._documento.con_capa(id_capa, imagen=v._almacen.guardar(arr))
        v._cambiar_documento(doc, refrescar_panel=True, descripcion="Imagen de prueba")
        self.esperar()

    def composicion(self) -> np.ndarray:
        v = self.v
        return componer(v._documento, v._almacen, None)


# ====================================================================== Pincel y Borrador
class PruebasPincel(_BaseU3):
    def test_pincel_con_el_mouse_es_un_paso_con_el_color_de_frente(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        v = self.v
        ps = v.photoshop
        self.documento(400, 300, (255, 255, 255))
        id_capa = self.capa_pixeles()
        ps.colores.establecer(frente=(220, 20, 30))
        self.accion("B").trigger()
        self.assertEqual(ps.herramienta, "pintar")
        self.assertTrue(v.botones_herramienta_ps["pintar"].isChecked())
        self.assertEqual(ps.paginas_opciones.currentIndex(), ps._paginas["pintar"])
        ps.opciones_pintura.numero_tamano.setValue(24)
        ps.opciones_pintura.numero_dureza.setValue(100)
        self.assertEqual(ps.pinceles["pintar"]["tamano"], 24.0)
        pasos = v._pos_historial
        vista = v.vista
        a, b = self.a_pantalla(100, 150), self.a_pantalla(300, 150)
        QTest.mousePress(vista, Qt.LeftButton, Qt.NoModifier, a)
        for i in range(1, 9):
            QTest.mouseMove(vista, QPoint(round(a.x() + (b.x() - a.x()) * i / 8), a.y()))
        # Mientras se arrastra: la superposición tiene el trazo, y todavía no es un paso.
        g = ps.controlador._gesto
        self.assertEqual(g["tipo"], "trazo")
        self.assertIsNotNone(g["trazo"].caja)
        self.assertGreater(int(g["trazo"].cobertura.max()), 200)
        self.assertEqual(v._pos_historial, pasos)
        self.assertIsNone(v._doc_provisorio, "no se recompone el documento mientras se pinta")
        captura = vista.grab().toImage()
        p = vista.a_pantalla(self._qp(200, 150))
        color = captura.pixelColor(round(p.x()), round(p.y()))
        self.assertGreater(color.red(), 150)
        self.assertLess(color.green(), 90)
        QTest.mouseRelease(vista, Qt.LeftButton, Qt.NoModifier, b)
        self.esperar()
        self.assertEqual(v._pos_historial, pasos + 1)
        self.assertEqual(self.paso(), "Pincel en «Capa 1»")
        img = self.imagen(id_capa)
        self.assertEqual(tuple(img[150, 200]), (220, 20, 30, 255))
        self.assertEqual(int(img[150, 40, 3]), 0)
        self.assertEqual(int(img[100, 200, 3]), 0)
        self.assertEqual(tuple(self.vista()[150, 200]), (220, 20, 30))
        # Deshacer vuelve a la capa vacía (aunque la imagen de antes ya esté comprimida).
        v.deshacer()
        self.esperar()
        self.assertEqual(int(self.imagen(id_capa)[..., 3].max()), 0)
        v.rehacer()
        self.esperar()
        self.assertEqual(tuple(self.imagen(id_capa)[150, 200]), (220, 20, 30, 255))

    @staticmethod
    def _qp(x, y):
        from PySide6.QtCore import QPointF
        return QPointF(x, y)

    def test_sobre_la_base_crea_una_capa_nueva_en_el_mismo_paso(self):
        v = self.v
        ps = v.photoshop
        self.documento(300, 200, (255, 255, 255))
        v.panel_capas.elegir(v._documento.capas[0].id)  # el fondo
        ps.elegir_herramienta("pintar")
        pasos = v._pos_historial
        capas = len(v._documento.capas)
        self.arrastrar((50, 100), (250, 100), pasos=6)
        self.esperar()
        self.assertEqual(v._pos_historial, pasos + 1)
        self.assertEqual(len(v._documento.capas), capas + 1)
        nueva = v._documento.capa(v.panel_capas.capa_elegida)
        self.assertEqual(nueva.tipo, "pixeles")
        self.assertEqual(self.paso(), f"Pincel: capa nueva «{nueva.nombre}»")
        self.assertEqual(tuple(self.imagen(nueva.id)[100, 150][:3]), (0, 0, 0))
        # El fondo no cambió.
        self.assertEqual(v._documento.capas[0].tipo, "relleno")

    def test_afuera_de_la_capa_la_capa_crece(self):
        from celular_natural.motor.documento import caja_capa
        v = self.v
        ps = v.photoshop
        self.documento(400, 300, (255, 255, 255))
        (id_logo,) = self.agregar(0)  # 160 × 100, centrado
        # El logo pasa a píxeles (Rasterizar) y se pinta afuera, a la izquierda.
        ps.rasterizar()
        self.esperar()
        self.assertEqual(v._documento.capa(id_logo).tipo, "pixeles")
        caja0 = caja_capa(v._documento, id_logo, v._almacen)
        ps.elegir_herramienta("pintar")
        ps.colores.establecer(frente=(0, 0, 255))
        self.arrastrar((40, 150), (200, 150), pasos=6)
        self.esperar()
        caja1 = caja_capa(v._documento, id_logo, v._almacen)
        self.assertLess(caja1[0], caja0[0] - 50, "la capa creció hacia la izquierda")
        self.assertAlmostEqual(caja1[2], caja0[2], delta=1.0)
        comp = self.vista()
        self.assertEqual(tuple(comp[150, 50]), (0, 0, 255))
        self.assertEqual(tuple(comp[150, 260]), (240, 60, 150), "lo de antes quedó en su lugar")
        self.assertEqual(tuple(comp[110, 140]), (240, 60, 150))

    def test_borrador_baja_el_alfa(self):
        v = self.v
        ps = v.photoshop
        self.documento(400, 300, (255, 255, 255))
        (id_logo,) = self.agregar(0)
        self.accion("E").trigger()
        self.assertEqual(ps.herramienta, "borrador")
        ps.opciones_pintura.numero_tamano.setValue(30)
        self.arrastrar((150, 150), (250, 150), pasos=5)
        self.esperar()
        self.assertEqual(self.paso(), "Borrador en «logo1»")
        img = self.imagen(id_logo)
        self.assertEqual(img.shape[:2], (100, 160), "el borrador no agranda la capa")
        self.assertLess(int(img[50, 80, 3]), 20)
        self.assertEqual(int(img[5, 80, 3]), 255)
        self.assertEqual(tuple(self.vista()[150, 200]), (255, 255, 255), "se ve el fondo")
        # El borrador sobre la base no hace nada (avisa).
        pasos = v._pos_historial
        v.panel_capas.elegir(v._documento.capas[0].id)
        self.arrastrar((20, 20), (80, 20))
        self.esperar()
        self.assertEqual(v._pos_historial, pasos)

    def test_pintar_un_texto_pregunta_y_rasteriza(self):
        from PySide6.QtWidgets import QMessageBox
        v = self.v
        ps = v.photoshop
        self.documento(500, 300, (255, 255, 255))
        ps.agregar_texto({"texto": "Hola", "tamano": 80, "color": (0, 0, 0)})
        self.esperar()
        id_texto = v.panel_capas.capa_elegida
        self.assertEqual(v._documento.capa(id_texto).tipo, "texto")
        ps.elegir_herramienta("pintar")
        pasos = v._pos_historial
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.No) as pregunta:
            self.arrastrar((200, 150), (300, 150))
        self.esperar()
        self.assertEqual(pregunta.call_count, 1)
        self.assertEqual(pregunta.call_args[0][1], "¿Rasterizar la capa?")
        self.assertEqual(v._documento.capa(id_texto).tipo, "texto")
        self.assertEqual(v._pos_historial, pasos)
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            self.arrastrar((200, 150), (300, 150))
        self.esperar()
        self.assertEqual(v._documento.capa(id_texto).tipo, "pixeles")
        self.assertEqual(self.paso(), "Capa «Hola» rasterizada")
        # Ahora sí pinta (sin preguntar).
        with mock.patch.object(QMessageBox, "question") as pregunta:
            self.arrastrar((200, 150), (300, 150))
            self.esperar()
        pregunta.assert_not_called()
        self.assertEqual(self.paso(), "Pincel en «Hola»")

    def test_corchetes_teclas_y_esc(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        v = self.v
        ps = v.photoshop
        self.documento(300, 200)
        self.accion("B").trigger()
        self.assertEqual(ps.pinceles["pintar"]["tamano"], 20.0)
        self.accion("]").trigger()
        self.assertEqual(ps.pinceles["pintar"]["tamano"], 25.0)
        self.assertEqual(ps.opciones_pintura.numero_tamano.value(), 25)
        self.accion("[").trigger()
        self.accion("[").trigger()
        self.assertEqual(ps.pinceles["pintar"]["tamano"], 15.0)
        # El Borrador tiene su propio tamaño.
        self.accion("E").trigger()
        self.assertEqual(ps.opciones_pintura.numero_tamano.value(), 40)
        self.accion("G").trigger()
        self.assertEqual(ps.herramienta, "bote")
        self.accion("Shift+G").trigger()
        self.assertEqual(ps.herramienta, "degradado")
        self.assertTrue(v.botones_herramienta_ps["bote"].isChecked(), "el Degradado comparte el botón del Bote")
        self.accion("Shift+G").trigger()
        self.assertEqual(ps.herramienta, "bote")
        self.accion("C").trigger()
        self.assertEqual(ps.herramienta, "recortar")
        # Esc durante un trazo: se descarta (no es un paso).
        self.accion("B").trigger()
        pasos = v._pos_historial
        a, b = self.a_pantalla(50, 100), self.a_pantalla(250, 100)
        QTest.mousePress(v.vista, Qt.LeftButton, Qt.NoModifier, a)
        QTest.mouseMove(v.vista, QPoint((a.x() + b.x()) // 2, a.y()))
        v.cancelar_herramienta()  # lo que hace Esc
        QTest.mouseRelease(v.vista, Qt.LeftButton, Qt.NoModifier, b)
        self.esperar()
        self.assertEqual(v._pos_historial, pasos)
        # Fuera del modo Photoshop las letras no eligen herramientas.
        v.establecer_modo("editor", guardar=False)
        self.accion("G").trigger()
        self.assertEqual(ps.herramienta, "pintar")


# ====================================================================== Bote
class PruebasBote(_BaseU3):
    def _tres_franjas(self, id_capa):
        arr = np.zeros((90, 300, 4), np.uint8)
        arr[:, :100] = (255, 0, 0, 255)
        arr[:, 100:200] = (0, 0, 255, 255)
        arr[:, 200:] = (255, 0, 0, 255)
        self.poner_imagen(id_capa, arr)

    def test_bote_contiguo_y_global(self):
        v = self.v
        ps = v.photoshop
        self.documento(300, 90, (255, 255, 255))
        id_capa = self.capa_pixeles()
        self._tres_franjas(id_capa)
        ps.colores.establecer(frente=(0, 200, 0))
        self.accion("G").trigger()
        self.assertTrue(ps.opciones_bote_ui.check_contiguo.isChecked())
        pasos = v._pos_historial
        self.clic(50, 45)
        self.esperar()
        self.assertEqual(v._pos_historial, pasos + 1)
        self.assertEqual(self.paso(), "Bote de pintura en «Capa 1»")
        img = self.imagen(id_capa)
        self.assertEqual(tuple(img[45, 50]), (0, 200, 0, 255))
        self.assertEqual(tuple(img[45, 150]), (0, 0, 255, 255))
        self.assertEqual(tuple(img[45, 250]), (255, 0, 0, 255), "contiguo: la otra franja roja no")
        v.deshacer()
        self.esperar()
        ps.opciones_bote_ui.check_contiguo.setChecked(False)
        self.assertFalse(ps.opciones_bote["contiguo"])
        self.clic(50, 45)
        self.esperar()
        img = self.imagen(id_capa)
        self.assertEqual(tuple(img[45, 250]), (0, 200, 0, 255), "global: las dos franjas rojas")
        self.assertEqual(tuple(img[45, 150]), (0, 0, 255, 255))
        # Tolerancia: con 255, todo.
        v.deshacer()
        self.esperar()
        ps.opciones_bote_ui.numero_tolerancia.setValue(255)
        self.clic(50, 45)
        self.esperar()
        self.assertEqual(tuple(self.imagen(id_capa)[45, 150]), (0, 200, 0, 255))

    def clic(self, x, y):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        QTest.mouseClick(self.v.vista, Qt.LeftButton, Qt.NoModifier, self.a_pantalla(x, y))
        self.app.processEvents()

    def test_todas_las_capas_y_sobre_la_base(self):
        v = self.v
        ps = v.photoshop
        self.documento(400, 300, (255, 255, 255))
        self.agregar(0)  # el logo rosa, 160 × 100 centrado: x 120..280, y 100..200
        id_capa = self.capa_pixeles()  # vacía, arriba
        ps.colores.establecer(frente=(0, 0, 0))
        ps.elegir_herramienta("bote")
        # Sin "Todas las capas", la capa vacía es toda igual: se llena entera.
        self.clic(200, 150)
        self.esperar()
        self.assertEqual(int(self.imagen(id_capa)[10, 10, 3]), 255)
        v.deshacer()
        self.esperar()
        # Con "Todas las capas", la zona es la del logo (lo que se ve).
        ps.opciones_bote_ui.check_todas.setChecked(True)
        self.clic(200, 150)
        self.esperar()
        img = self.imagen(id_capa)
        self.assertEqual(int(img[150, 200, 3]), 255)
        self.assertEqual(int(img[10, 10, 3]), 0)
        self.assertEqual(int(img[150, 100, 3]), 0)
        # Sobre la base (el fondo blanco): una capa nueva, con la zona de lo que se ve.
        v.panel_capas.elegir(v._documento.capas[0].id)
        capas = len(v._documento.capas)
        ps.opciones_bote_ui.check_todas.setChecked(False)
        self.clic(20, 20)
        self.esperar()
        self.assertEqual(len(v._documento.capas), capas + 1)
        nueva = v._documento.capa(v.panel_capas.capa_elegida)
        self.assertTrue(self.paso().startswith("Bote de pintura: capa nueva"))
        img = self.imagen(nueva.id)
        self.assertEqual(int(img[20, 20, 3]), 255)
        self.assertEqual(int(img[150, 200, 3]), 0, "el logo no es parte de la zona blanca")


# ====================================================================== Degradado
class PruebasDegradado(_BaseU3):
    def test_crea_una_capa_de_relleno_con_esos_puntos(self):
        v = self.v
        ps = v.photoshop
        self.documento(400, 300, (255, 255, 255))
        v.panel_capas.elegir(v._documento.capas[0].id)
        ps.colores.establecer(frente=(255, 0, 0), fondo=(0, 0, 255))
        self.accion("Shift+G").trigger()
        self.assertEqual(ps.herramienta, "degradado")
        capas = len(v._documento.capas)
        pasos = v._pos_historial
        self.arrastrar((100, 150), (300, 150))
        self.esperar()
        self.assertEqual(v._pos_historial, pasos + 1)
        self.assertEqual(len(v._documento.capas), capas + 1)
        capa = v._documento.capa(v.panel_capas.capa_elegida)
        self.assertEqual(capa.tipo, "relleno")
        self.assertEqual(capa.params.tipo, "lineal")
        self.assertEqual(self.paso(), f"Capa nueva: {capa.nombre}")
        comp = self.vista()
        self.assertEqual(tuple(comp[150, 50]), (255, 0, 0), "antes de p0, el color de frente")
        self.assertEqual(tuple(comp[150, 350]), (0, 0, 255), "después de p1, el de fondo")
        r, _g, b = (int(x) for x in comp[150, 200])
        self.assertTrue(100 < r < 160 and 100 < b < 160, comp[150, 200])
        # Es un relleno de verdad: se edita en Propiedades (sus colores siguen ahí).
        self.assertEqual(capa.params.colores[0][:3], (255, 0, 0))

    def test_radial_y_sobre_una_capa_de_pixeles(self):
        v = self.v
        ps = v.photoshop
        self.documento(400, 300, (255, 255, 255))
        ps.colores.establecer(frente=(0, 0, 0), fondo=(255, 255, 255))
        ps.elegir_herramienta("degradado")
        ps.opciones_degradado.boton_radial.click()
        self.assertTrue(ps.degradado_radial)
        v.panel_capas.elegir(v._documento.capas[0].id)
        self.arrastrar((200, 150), (300, 150))
        self.esperar()
        capa = v._documento.capa(v.panel_capas.capa_elegida)
        self.assertEqual(capa.tipo, "pixeles", "un radial con su centro va a una capa de píxeles")
        comp = self.vista()
        self.assertLess(int(comp[150, 200].max()), 10)
        self.assertGreater(int(comp[10, 10].min()), 245)
        # Con una capa de píxeles elegida, el degradado se pinta en ella (no hay capa nueva).
        id_capa = self.capa_pixeles()
        ps.opciones_degradado.boton_lineal.click()
        ps.colores.establecer(frente=(0, 255, 0), fondo=(0, 255, 0))
        capas = len(v._documento.capas)
        self.arrastrar((0, 150), (400, 150))
        self.esperar()
        self.assertEqual(len(v._documento.capas), capas)
        self.assertEqual(self.paso(), "Degradado en «Capa 2»")
        self.assertEqual(tuple(self.imagen(id_capa)[150, 200]), (0, 255, 0, 255))

    def test_colores_del_editor_de_degradado(self):
        from celular_natural.motor.formas import Relleno
        v = self.v
        ps = v.photoshop
        self.documento(400, 300, (255, 255, 255))
        ps.elegir_herramienta("degradado")
        rel = Relleno("lineal", ((255, 255, 0, 255), (0, 255, 255, 255), (255, 0, 255, 255)), (0.0, 0.5, 1.0))
        ps.opciones_degradado.boton_relleno.rellenoCambiado.emit(rel)
        self.assertFalse(ps.opciones_degradado.boton_frente_fondo.isChecked())
        self.assertEqual(ps.relleno_degradado_efectivo().colores, rel.colores)
        v.panel_capas.elegir(v._documento.capas[0].id)
        self.arrastrar((0, 100), (400, 100))
        self.esperar()
        comp = self.vista()
        self.assertLessEqual(np.abs(comp[100, 0].astype(int) - (255, 255, 0)).max(), 3)
        self.assertLessEqual(np.abs(comp[100, 200].astype(int) - (0, 255, 255)).max(), 3)
        self.assertLessEqual(np.abs(comp[100, 399].astype(int) - (255, 0, 255)).max(), 3)
        # "Frente → fondo" vuelve a los colores de frente y fondo.
        ps.opciones_degradado.boton_frente_fondo.click()
        self.assertIsNone(ps.relleno_degradado)


# ====================================================================== Recortar
class PruebasRecortar(_BaseU3):
    def cerca(self, valores, esperados, margen=2):
        """Iguales con un margen: el mouse cae en el píxel más cercano al zoom de la vista."""
        for a, b in zip(valores, esperados):
            self.assertLessEqual(abs(a - b), margen, (valores, esperados))

    def test_recortar_con_las_manijas_enter_y_esc(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        v = self.v
        ps = v.photoshop
        self.documento(400, 300, (90, 160, 30))
        self.accion("C").trigger()
        self.assertEqual(ps.herramienta, "recortar")
        self.assertEqual(v.vista.herramienta, "ps")
        caja = ps.caja_recorte_actual()
        self.assertEqual(caja.pixeles(), (0, 0, 400, 300))
        pasos = v._pos_historial
        # La manija de abajo a la derecha, hasta (200, 150); Esc: no cambia nada.
        self.arrastrar((400, 300), (200, 150))
        self.cerca(ps.caja_recorte_actual().pixeles(), (0, 0, 200, 150))
        v.cancelar_herramienta()  # Esc
        self.esperar()
        self.assertEqual((v._documento.ancho, v._documento.alto), (400, 300))
        self.assertEqual(v._pos_historial, pasos)
        self.assertEqual(ps.caja_recorte_actual().pixeles(), (0, 0, 400, 300))
        # De nuevo, más la de arriba a la izquierda, y Enter (en la vista): recorta.
        self.arrastrar((400, 300), (300, 250))
        self.arrastrar((0, 0), (100, 50))
        self.arrastrar((200, 150), (210, 160))  # adentro: lo mueve
        # (el mouse cae en el píxel más cercano al zoom de la vista: un píxel de diferencia vale)
        x0, y0, x1, y1 = ps.caja_recorte_actual().pixeles()
        for valor, esperado in zip((x0, y0, x1, y1), (110, 60, 310, 260)):
            self.assertLessEqual(abs(valor - esperado), 2)
        w, h = x1 - x0, y1 - y0
        v.vista.setFocus()
        QTest.keyClick(v.vista, Qt.Key_Return)
        self.esperar(lambda: self.quieto() and v._documento.ancho == w)
        self.assertEqual((v._documento.ancho, v._documento.alto), (w, h))
        self.assertEqual(v._fuente.shape[:2], (h, w))
        self.assertEqual(self.paso(), f"Lienzo recortado: {w} × {h} px")
        self.assertEqual(ps.herramienta, "recortar", "la herramienta sigue elegida")
        self.assertEqual(ps.caja_recorte_actual().pixeles(), (0, 0, w, h))
        v.deshacer()
        self.esperar(lambda: self.quieto() and v._documento.ancho == 400)

    def test_proporcion_y_el_boton_del_kit(self):
        v = self.v
        ps = v.photoshop
        self.documento(400, 300)
        v.boton_recortar_ps.click()
        self.assertEqual(ps.herramienta, "recortar")
        self.assertEqual(v.modo, "photoshop", "ya no lleva al Editor")
        ps.combo_aspecto.setCurrentIndex(ps.combo_aspecto.findText("1:1 cuadrado"))
        self.assertEqual(ps.caja_recorte_actual().pixeles(), (50, 0, 350, 300))
        # Una esquina mantiene la proporción.
        self.arrastrar((350, 300), (250, 280))
        x0, y0, x1, y1 = ps.caja_recorte_actual().pixeles()
        self.assertEqual(x1 - x0, y1 - y0)
        # Doble clic adentro también aplica.
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        QTest.mouseDClick(v.vista, Qt.LeftButton, Qt.NoModifier, self.a_pantalla((x0 + x1) / 2, (y0 + y1) / 2))
        self.esperar(lambda: self.quieto() and v._documento.ancho == x1 - x0)
        self.assertEqual(v._documento.alto, y1 - y0)

    def test_recortar_una_foto_es_no_destructivo(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        v = self.v
        ps = v.photoshop
        v.agregar_fotos([str(self.fotos[0])])  # 320 × 240
        self.esperar()
        (id_logo,) = self.agregar(0)
        ps.elegir_herramienta("recortar")
        caja = ps.caja_recorte_actual()
        self.assertTrue(caja.limitar, "en una foto, no se sale de ella")
        self.arrastrar((320, 240), (400, 180))  # la manija no saca el recuadro de la foto
        self.cerca(ps.caja_recorte_actual().pixeles(), (0, 0, 320, 180))
        self.arrastrar((320, 180), (200, 180))
        self.arrastrar((100, 90), (-50, -50))  # mover: tampoco
        self.cerca(ps.caja_recorte_actual().pixeles(), (0, 0, 200, 180))
        self.assertEqual(ps.caja_recorte_actual().pixeles()[:2], (0, 0))
        self.arrastrar((100, 90), (400, 400))
        x0, y0, x1, y1 = ps.caja_recorte_actual().pixeles()
        self.assertEqual((x1, y1), (320, 240))
        primero = (x1 - x0, y1 - y0)
        self.cerca(primero, (200, 180))
        v.vista.setFocus()
        QTest.keyClick(v.vista, Qt.Key_Return)
        self.esperar(lambda: self.quieto() and v._tam_mostrado() == primero)
        self.assertTrue(v._documento.tiene_foto, "la foto sigue siendo la foto")
        self.assertIsNotNone(v._recorte)
        self.assertEqual(len(v._fotos), 1, "no arma un documento nuevo")
        # Un segundo recorte se suma al primero; deshacer vuelve.
        self.arrastrar((0, 0), (100, 80))
        QTest.keyClick(v.vista, Qt.Key_Return)
        self.esperar(lambda: self.quieto() and v._tam_mostrado() != primero)
        wb, hb = v._tam_base()
        self.cerca(v._recorte.pixeles(wb, hb), (220, 140, 320, 240))
        v.deshacer()
        self.esperar(lambda: self.quieto() and v._tam_mostrado() == primero)
        self.assertIn(id_logo, [c.id for c in v._documento.capas])


# ====================================================================== Pegar
class PruebasPegar(_BaseU3):
    def test_pegar_png_de_otra_app_y_sin_documento(self):
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMimeData
        from PySide6.QtGui import QImage
        from PySide6.QtWidgets import QApplication
        v = self.v
        ps = v.photoshop
        # Lo que deja un navegador: los bytes de un PNG con transparencia (sin la "imagen" de Qt).
        arr = np.zeros((40, 60, 4), np.uint8)
        arr[:, :30] = (10, 200, 30, 255)
        qimg = QImage(arr.data, 60, 40, 240, QImage.Format_RGBA8888).copy()
        datos_png = QByteArray()
        buf = QBuffer(datos_png)
        buf.open(QIODevice.WriteOnly)
        qimg.save(buf, "PNG")
        buf.close()
        mime = QMimeData()
        mime.setData("image/png", datos_png)
        QApplication.clipboard().setMimeData(mime)
        # Sin documento: abre uno nuevo del tamaño de la imagen.
        self.accion("Ctrl+V").trigger()
        self.esperar(lambda: len(v._fotos) == 1 and self.quieto())
        doc = v._documento
        self.assertEqual((doc.ancho, doc.alto), (60, 40))
        capa = next(c for c in doc.capas if c.tipo == "imagen")
        img = self.imagen(capa.id)
        self.assertEqual(tuple(img[20, 10]), (10, 200, 30, 255))
        self.assertEqual(int(img[20, 50, 3]), 0, "con su transparencia")
        # Con documento: entra como capa.
        capas = len(v._documento.capas)
        ps.pegar()
        self.esperar()
        self.assertEqual(len(v._documento.capas), capas + 1)
        # La "imagen" de Qt (la de una captura de pantalla, Paint…) también.
        QApplication.clipboard().setImage(qimg)
        ps.pegar()
        self.esperar()
        self.assertEqual(len(v._documento.capas), capas + 2)


# ====================================================================== sesión y proyecto
class PruebasGuardar(_BaseU3):
    def _pintar(self, v):
        ps = v.photoshop
        self.documento(300, 200, (255, 255, 255), v=v)
        v.panel_capas.elegir(v._documento.capas[0].id)
        ps.colores.establecer(frente=(200, 0, 100))
        ps.elegir_herramienta("pintar")
        self.arrastrar((40, 100), (260, 100), pasos=6, v=v)
        self.esperar(v=v)
        capa = v._documento.capa(v.panel_capas.capa_elegida)
        self.assertEqual(capa.tipo, "pixeles")
        return capa.id

    def test_proyecto_con_una_capa_pintada(self):
        from PySide6.QtWidgets import QFileDialog
        v = self.v
        id_capa = self._pintar(v)
        doc = v._documento
        img = self.imagen(id_capa).copy()
        ruta = self.base / "pintado.nslite"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(ruta), "")):
            v.guardar_proyecto()
        self.esperar(lambda: not v._guardando_proyecto and ruta.exists())
        otra = self.ventana()
        otra.abrir_proyecto(str(ruta))
        self.esperar(lambda: self.quieto(otra) and otra._documento is not None, otra)
        self.assertEqual(otra._documento, doc)
        self.assertTrue(np.array_equal(otra._arreglo(otra._documento.capa(id_capa).imagen), img))

    def test_sesion_con_una_capa_pintada(self):
        v = self.ventana(sesion=True)
        id_capa = self._pintar(v)
        doc = v._documento
        img = v._arreglo(doc.capa(id_capa).imagen).copy()
        v.close()
        self.ventanas.remove(v)
        v.deleteLater()
        self.app.processEvents()
        otra = self.ventana(sesion=True)
        self.esperar(lambda: self.quieto(otra) and otra._documento is not None, otra)
        self.assertEqual(otra._documento, doc)
        self.assertTrue(np.array_equal(otra._arreglo(otra._documento.capa(id_capa).imagen), img))
        # Se sigue pintando encima.
        otra.panel_capas.elegir(id_capa)
        otra.photoshop.elegir_herramienta("pintar")
        self.arrastrar((150, 20), (150, 180), v=otra)
        self.esperar(v=otra)
        self.assertEqual(otra._historial[otra._pos_historial][0], f"Pincel en «{otra._documento.capa(id_capa).nombre}»")


if __name__ == "__main__":
    unittest.main()
