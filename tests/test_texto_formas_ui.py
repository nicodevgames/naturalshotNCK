"""Pruebas de la Etapa 2, U2, del modo Photoshop de NaturalShot Lite (ventana real, sin pantalla).

* **Texto (T):** un clic crea una capa de texto y se escribe ahí mismo (Enter: otro renglón; Esc,
  Ctrl+Enter o un clic afuera: listo, un paso); doble clic sobre el texto (o en su miniatura) lo
  vuelve a editar; la barra de opciones (fuente, tamaño, color…) cambia sus ``params``; arrastrar
  crea una caja que corta las líneas.
* **Formas (U):** cada forma arrastrando (Mayús: 1:1); el relleno con degradado.
* **Estilo de capa:** sombra y trazo con vista previa; Cancelar vuelve y Aceptar es un paso.
* **Selector de color** (hexadecimal, alfa, recientes y cuentagotas).
* **El flyer de aceptación:** Nuevo 1080 × 1920 con fondo degradado, 4 imágenes, un título con
  sombra y trazo, una banda redondeada con texto encima y una estrella; se exporta y se mira con los
  píxeles que cada cosa esté donde va.
* **Sesión y ``.nslite``** con texto y formas: siguen siendo editables al reabrir.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_modo_photoshop import _Base, leer_png  # noqa: E402  (también arma el entorno: offscreen, Lite…)

from celular_natural.motor.formas import Relleno  # noqa: E402


class _BaseU2(_Base):
    def pantalla(self, x, y):
        return self.a_pantalla(x, y)

    def clic(self, x, y, mods=None):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        QTest.mouseClick(self.v.vista, Qt.LeftButton, Qt.NoModifier if mods is None else mods, self.pantalla(x, y))
        self.app.processEvents()

    def escribir_texto(self, x, y, texto, confirmar=True):
        """Con la herramienta Texto: clic en (x, y), escribe y confirma (Ctrl+Enter). Devuelve el id."""
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        ps = self.v.photoshop
        ps.elegir_herramienta("texto")
        self.clic(x, y)
        ed = ps.edicion_texto
        self.assertIsNotNone(ed, "un clic con Texto empieza a escribir")
        for i, renglon in enumerate(texto.split("\n")):
            if i:
                QTest.keyClick(ed.editor, Qt.Key_Return)
            QTest.keyClicks(ed.editor, renglon)
        if confirmar:
            QTest.keyClick(ed.editor, Qt.Key_Return, Qt.ControlModifier)
            self.esperar()
        return ed.id


# ====================================================================== Texto
class PruebasTexto(_BaseU2):
    def test_clic_y_escribir_y_editar_con_doble_clic(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from celular_natural.ui.texto_ps import medidas_texto, punto_ancla
        v = self.v
        ps = v.photoshop
        self.documento(800, 600, (20, 40, 200))
        pasos = v._pos_historial
        ps.elegir_herramienta("texto")
        self.assertTrue(v.botones_herramienta_ps["texto"].isChecked())
        self.clic(100, 200)
        ed = ps.edicion_texto
        self.assertIsNotNone(ed)
        self.assertTrue(ed.editor.isVisible())
        QTest.keyClicks(ed.editor, "Hola mundo")  # con un espacio (el de la Mano no se lo come)
        QTest.keyClicks(ed.editor, "V")  # una letra que es atajo (Mover): es del texto
        self.assertEqual(ps.herramienta, "texto")
        QTest.keyClick(ed.editor, Qt.Key_Return)
        QTest.keyClicks(ed.editor, "chau")
        self.app.processEvents()
        # Mientras se escribe: la capa se ve (documento provisorio) y todavía no es un paso.
        self.assertEqual(v._pos_historial, pasos)
        prov = v._documento_vista().capa(ed.id)
        self.assertEqual(prov.params.contenido, "Hola mundoV\nchau")
        QTest.keyClick(ed.editor, Qt.Key_Return, Qt.ControlModifier)
        self.esperar()
        self.assertIsNone(ps.edicion_texto)
        capa = v._documento.capa(ed.id)
        self.assertEqual(capa.tipo, "texto")
        self.assertEqual(capa.params.contenido, "Hola mundoV\nchau")
        self.assertEqual(capa.nombre, "Hola mundoV")
        self.assertEqual(v._pos_historial, pasos + 1)
        self.assertEqual(self.paso(), "Texto nuevo: «Hola mundoV»")
        # La línea base del primer renglón quedó donde se hizo clic.
        _w, _h, ascenso = medidas_texto(capa.params)
        ax, ay = punto_ancla(capa.params, capa.transform)
        self.assertAlmostEqual(ax, 100, delta=1.0)
        self.assertAlmostEqual(ay + ascenso, 200, delta=1.0)
        # Se ve: hay letras (negras, el color de frente) a la derecha del clic.
        x0, y0, x1, y1 = self.caja(capa.id)
        self.assertGreater(x0, 95)
        self.assertLess(x0, 115)
        vista = self.vista()
        h, w = vista.shape[:2]
        trozo = vista[int(y0 * h / 600):int(y1 * h / 600), int(x0 * w / 800):int(x1 * w / 800)]
        self.assertGreater(int((trozo.sum(axis=2) < 60).sum()), 50)
        # Doble clic con Mover sobre el texto: se edita de nuevo, sin correr su ancla.
        ps.elegir_herramienta("mover")
        cx, cy = (x0 + x1) / 2, y0 + 20
        QTest.mouseDClick(v.vista, Qt.LeftButton, Qt.NoModifier, self.pantalla(cx, cy))
        self.app.processEvents()
        ed = ps.edicion_texto
        self.assertIsNotNone(ed)
        self.assertEqual(ed.id, capa.id)
        self.assertEqual(ps.herramienta, "texto")
        ed.editor.selectAll()
        QTest.keyClicks(ed.editor, "Otro")
        QTest.keyClick(ed.editor, Qt.Key_Escape)  # Esc confirma
        self.esperar()
        nueva = v._documento.capa(capa.id)
        self.assertEqual(nueva.params.contenido, "Otro")
        self.assertEqual(self.paso(), "Texto cambiado: «Otro»")
        self.assertEqual(v._pos_historial, pasos + 2)
        bx, by = punto_ancla(nueva.params, nueva.transform)
        self.assertAlmostEqual(bx, ax, places=6)
        self.assertAlmostEqual(by, ay, places=6)
        # Deshacer vuelve al texto de antes.
        v.deshacer()
        self.esperar()
        self.assertEqual(v._documento.capa(capa.id).params.contenido, "Hola mundoV\nchau")

    def test_clic_afuera_confirma_y_vacio_no_crea_nada(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        v = self.v
        ps = v.photoshop
        self.documento(800, 600)
        pasos = v._pos_historial
        capas = len(v._documento.capas)
        ps.elegir_herramienta("texto")
        self.clic(100, 100)
        QTest.keyClick(ps.edicion_texto.editor, Qt.Key_Escape)  # sin escribir nada
        self.esperar()
        self.assertEqual(len(v._documento.capas), capas)
        self.assertEqual(v._pos_historial, pasos)
        # Un clic afuera confirma (y no empieza otro texto).
        self.clic(100, 100)
        QTest.keyClicks(ps.edicion_texto.editor, "Uno")
        self.clic(600, 500)
        self.esperar()
        self.assertIsNone(ps.edicion_texto)
        self.assertEqual([c.params.contenido for c in v._documento.capas if c.tipo == "texto"], ["Uno"])
        # Borrar todo el texto de uno que ya estaba lo borra (un paso).
        id_texto = next(c.id for c in v._documento.capas if c.tipo == "texto")
        ed = ps.editar_texto(id_texto)
        ed.editor.selectAll()
        QTest.keyClick(ed.editor, Qt.Key_Delete)
        QTest.keyClick(ed.editor, Qt.Key_Return, Qt.ControlModifier)
        self.esperar()
        self.assertFalse(any(c.tipo == "texto" for c in v._documento.capas))
        self.assertEqual(self.paso(), "Texto borrado: «Uno»")

    def test_doble_clic_en_la_miniatura_edita(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        v = self.v
        ps = v.photoshop
        self.documento(800, 600)
        id_texto = self.escribir_texto(200, 300, "Mini")
        ps.elegir_herramienta("mover")
        self.esperar(lambda: v.panel_capas.fila(id_texto) is not None)
        fila = v.panel_capas.fila(id_texto)
        QTest.mouseDClick(fila.mini, Qt.LeftButton)
        self.esperar(lambda: ps.edicion_texto is not None)
        self.assertEqual(ps.edicion_texto.id, id_texto)
        ps.terminar_texto(True)

    def test_barra_de_opciones_cambia_los_params(self):
        from celular_natural.ui import selector_color
        from celular_natural.ui.texto_ps import punto_ancla
        v = self.v
        ps = v.photoshop
        self.documento(800, 600)
        id_texto = self.escribir_texto(100, 300, "Opciones")
        ps.elegir_herramienta("texto")
        op = ps.opciones_texto
        self.assertTrue(op.isVisible())
        antes = v._documento.capa(id_texto)
        ancla = punto_ancla(antes.params, antes.transform)
        # Fuente (el combo busca).
        op.combo_familia.llenar()
        op.combo_familia.setEditText("times new")
        op.combo_familia.lineEdit().editingFinished.emit()
        self.esperar()
        capa = v._documento.capa(id_texto)
        self.assertEqual(capa.params.fuente, "Times New Roman")
        self.assertEqual(self.paso(), "Texto «Opciones» cambiado")
        # Tamaño.
        op.numero_tamano.setValue(120)
        self.esperar()
        capa = v._documento.capa(id_texto)
        self.assertEqual(capa.params.tamano, 120.0)
        # Color (con el selector propio).
        with mock.patch.object(selector_color, "elegir_color", return_value=(200, 30, 60, 255)):
            op.boton_color.click()
        self.esperar()
        capa = v._documento.capa(id_texto)
        self.assertEqual(capa.params.color, (200, 30, 60, 255))
        # Negrita, cursiva, alineación, interlineado y espaciado.
        op.boton_negrita.click()
        op.boton_cursiva.click()
        op.numero_interlineado.setValue(1.5)
        op.numero_espaciado.setValue(4)
        self.esperar()
        capa = v._documento.capa(id_texto)
        self.assertTrue(capa.params.negrita and capa.params.cursiva)
        self.assertEqual((capa.params.interlineado, capa.params.espaciado), (1.5, 4.0))
        op.botones_alineacion["centro"].click()
        self.esperar()
        capa = v._documento.capa(id_texto)
        self.assertEqual(capa.params.alineacion, "centro")
        # Cada cambio es un paso, y el texto no se corrió (con la alineación izquierda).
        self.assertEqual(self.paso(), "Texto «Opciones» cambiado")
        capa_izq = v._historial[v._pos_historial - 1][1]["documento"].capa(id_texto)
        bx, by = punto_ancla(capa_izq.params, capa_izq.transform)
        self.assertAlmostEqual(bx, ancla[0], places=6)
        self.assertAlmostEqual(by, ancla[1], places=6)
        # Lo próximo sale con esos valores.
        self.assertEqual(ps.params_texto.fuente, "Times New Roman")
        # Propiedades muestra lo mismo y también lo cambia.
        prop = ps.propiedades
        self.assertTrue(prop.controles_texto.isVisible())
        self.assertEqual(prop.controles_texto.numero_tamano.value(), 120.0)
        prop.controles_texto.numero_tamano.setValue(60)
        self.esperar()
        self.assertEqual(v._documento.capa(id_texto).params.tamano, 60.0)

    def test_texto_con_caja_corta_las_lineas(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from celular_natural.ui.propiedades_ps import dibujo_natural
        from celular_natural.ui.texto_ps import medidas_texto
        v = self.v
        ps = v.photoshop
        self.documento(800, 600)
        ps.elegir_herramienta("texto")
        ps.opciones_texto.numero_tamano.setValue(40)
        self.arrastrar((100, 100), (340, 160))
        ed = ps.edicion_texto
        self.assertIsNotNone(ed)
        self.assertAlmostEqual(ed.params.ancho_caja, 240, delta=1.0)
        QTest.keyClicks(ed.editor, "uno dos tres cuatro cinco seis siete ocho nueve diez")
        QTest.keyClick(ed.editor, Qt.Key_Return, Qt.ControlModifier)
        self.esperar()
        capa = v._documento.capa(ed.id)
        ancho, alto, _a = medidas_texto(capa.params)
        self.assertAlmostEqual(ancho, 240, delta=1.0)
        self.assertGreater(alto, 3 * 40)  # varios renglones
        img = dibujo_natural("texto", capa.params)
        self.assertLess(img.shape[1], 240 + 2 * 40)
        x0, y0, x1, y1 = self.caja(capa.id)
        self.assertGreater(x0, 99)
        self.assertLess(x1, 341)
        self.assertGreater(y0, 99)


# ====================================================================== Formas
class PruebasFormas(_BaseU2):
    def test_cada_forma_arrastrando_y_mayus_1_a_1(self):
        from PySide6.QtCore import Qt
        v = self.v
        ps = v.photoshop
        self.documento(800, 600)
        ps.elegir_herramienta("formas")
        self.assertTrue(ps.opciones_forma.isVisible())
        for i, tipo in enumerate(("rectangulo", "elipse", "poligono", "estrella")):
            ps.elegir_forma(tipo)
            antes = {c.id for c in v._documento.capas}
            self.arrastrar((50 + 180 * i, 100), (190 + 180 * i, 180))
            self.esperar()
            nueva = [c for c in v._documento.capas if c.id not in antes]
            self.assertEqual(len(nueva), 1, tipo)
            capa = nueva[0]
            self.assertEqual((capa.tipo, capa.params.tipo), ("forma", tipo))
            self.assertAlmostEqual(capa.params.ancho, 140, delta=1.5)
            self.assertAlmostEqual(capa.params.alto, 80, delta=1.5)
            self.assertAlmostEqual(capa.transform.x, 120 + 180 * i, delta=1.5)
            self.assertAlmostEqual(capa.transform.y, 140, delta=1.5)
            self.assertTrue(self.paso().startswith("Forma nueva: "), self.paso())
            self.assertEqual(v.panel_capas.capa_elegida, capa.id)
            # Con Mayús: 1:1.
            antes = {c.id for c in v._documento.capas}
            self.arrastrar((50 + 180 * i, 300), (190 + 180 * i, 380), mods=Qt.ShiftModifier)
            self.esperar()
            capa = next(c for c in v._documento.capas if c.id not in antes)
            self.assertAlmostEqual(capa.params.ancho, capa.params.alto, places=6)
            self.assertAlmostEqual(capa.params.ancho, 140, delta=1.5)
        # Línea y flecha: el largo y el ángulo del arrastre (Mayús: de a 45°).
        for tipo in ("linea", "flecha"):
            ps.elegir_forma(tipo)
            antes = {c.id for c in v._documento.capas}
            self.arrastrar((100, 500), (300, 500))
            self.esperar()
            capa = next(c for c in v._documento.capas if c.id not in antes)
            self.assertEqual(capa.params.tipo, tipo)
            self.assertAlmostEqual(capa.params.ancho, 200, delta=1.5)
            self.assertAlmostEqual(capa.transform.rotacion, 0, delta=1.0)
            self.assertEqual(capa.params.alto, ps.alto_forma[tipo])
            antes = {c.id for c in v._documento.capas}
            self.arrastrar((500, 450), (600, 540), mods=Qt.ShiftModifier)
            self.esperar()
            capa = next(c for c in v._documento.capas if c.id not in antes)
            self.assertAlmostEqual(capa.transform.rotacion, 45, places=6)
        # Se ven: la vista tiene el negro del relleno donde están.
        vista = self.vista()
        h, w = vista.shape[:2]
        self.assertLess(int(vista[int(140 * h / 600), int(120 * w / 800)].sum()), 60)
        # Los pasos de deshacer: uno por forma.
        n = sum(1 for c in v._documento.capas if c.tipo == "forma")
        v.deshacer()
        self.esperar()
        self.assertEqual(sum(1 for c in v._documento.capas if c.tipo == "forma"), n - 1)

    def test_opciones_y_relleno_con_degradado(self):
        from celular_natural.ui import selector_color
        v = self.v
        ps = v.photoshop
        self.documento(800, 600, (255, 255, 255))
        id_forma = ps.nueva_forma(100, 100, 700, 500)
        self.esperar()
        ps.elegir_herramienta("formas")
        op = ps.opciones_forma
        # Degradado lineal en el relleno de la forma elegida (un paso).
        op.combo_relleno.setCurrentIndex(op.combo_relleno.findData("lineal"))
        self.esperar()
        rel = v._documento.capa(id_forma).params.relleno
        self.assertEqual(rel.tipo, "lineal")
        self.assertEqual(self.paso(), f"Forma «{v._documento.capa(id_forma).nombre}» cambiada")
        # Sus colores, con el editor de degradado: de rojo a azul, de izquierda a derecha.
        from celular_natural.ui.opciones_ps import DialogoDegradado
        nuevo = Relleno("lineal", ((255, 0, 0, 255), (0, 0, 255, 255)), (0.0, 1.0), 0.0)
        with mock.patch.object(DialogoDegradado, "exec", return_value=1), \
                mock.patch.object(DialogoDegradado, "relleno", return_value=nuevo):
            op.boton_relleno.click()
        self.esperar()
        self.assertEqual(v._documento.capa(id_forma).params.relleno, nuevo)
        vista = self.vista()
        h, w = vista.shape[:2]
        izq = vista[int(300 * h / 600), int(110 * w / 800)].astype(int)
        der = vista[int(300 * h / 600), int(690 * w / 800)].astype(int)
        self.assertGreater(izq[0], 200)
        self.assertLess(izq[2], 60)
        self.assertGreater(der[2], 200)
        self.assertLess(der[0], 60)
        # Trazo y radio.
        with mock.patch.object(selector_color, "elegir_color", return_value=(0, 255, 0, 255)):
            op.boton_trazo.click()
        op.numero_grosor.setValue(10)
        op.numero_radio.setValue(50)
        self.esperar()
        p = v._documento.capa(id_forma).params
        self.assertEqual((p.trazo, p.grosor, p.radio), ((0, 255, 0, 255), 10.0, 50.0))
        # El tipo de la barra es de la herramienta: no cambia la forma elegida.
        op.establecer_tipo("estrella")
        self.assertEqual(ps.params_forma.tipo, "estrella")
        self.assertEqual(v._documento.capa(id_forma).params.tipo, "rectangulo")
        # En Propiedades, el tipo sí cambia la forma (un paso).
        prop = ps.propiedades
        self.assertTrue(prop.controles_forma.isVisible())
        prop.controles_forma.establecer_tipo("elipse")
        self.esperar()
        self.assertEqual(v._documento.capa(id_forma).params.tipo, "elipse")

    def test_capa_de_relleno_con_degradado_de_varios_colores(self):
        v = self.v
        ps = v.photoshop
        self.documento(400, 300)
        ps.nueva_capa_relleno()
        self.esperar()
        prop = ps.propiedades
        id_rel = v.panel_capas.capa_elegida
        self.assertEqual(v._documento.capa(id_rel).tipo, "relleno")
        prop.combo_relleno.setCurrentIndex(prop.combo_relleno.findData("radial"))
        self.esperar()
        self.assertEqual(v._documento.capa(id_rel).params.tipo, "radial")
        ed = prop.editor_degradado
        self.assertTrue(ed.isVisible())
        ed.agregar_color()
        self.esperar()
        rel = v._documento.capa(id_rel).params
        self.assertEqual(len(rel.colores), 3)
        self.assertEqual(rel.paradas, (0.0, 0.5, 1.0))
        ed.filas[1][1].setValue(30)  # la posición del color del medio
        self.esperar()
        self.assertEqual(v._documento.capa(id_rel).params.paradas, (0.0, 0.3, 1.0))
        ed.agregar_color()
        self.esperar()
        self.assertEqual(len(v._documento.capa(id_rel).params.colores), 4)
        self.assertFalse(ed.boton_mas.isEnabled(), "hasta 4 colores")
        ed.quitar_color(0)
        self.esperar()
        self.assertEqual(len(v._documento.capa(id_rel).params.colores), 3)


# ====================================================================== Estilo de capa
class PruebasEstilos(_BaseU2):
    def test_dialogo_vista_previa_cancelar_y_aceptar(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        v = self.v
        ps = v.photoshop
        self.documento(800, 600, (255, 255, 255))
        ps.colores.establecer(frente=(0, 0, 255))
        id_forma = ps.nueva_forma(300, 200, 500, 400)
        self.esperar()
        doc = v._documento
        pasos = v._pos_historial
        # Doble clic en la fila del panel: el diálogo.
        self.esperar(lambda: v.panel_capas.fila(id_forma) is not None)
        QTest.mouseDClick(v.panel_capas.fila(id_forma).nombre, Qt.LeftButton)
        self.esperar(lambda: ps.dialogo_estilos is not None)
        dlg = ps.dialogo_estilos
        self.assertTrue(dlg.isVisible())
        # Sombra: vista previa en vivo, sin ser un paso.
        dlg.elegir("sombra")
        dlg.establecer("sombra", color=(255, 0, 0, 255), opacidad=1.0, angulo=90.0, distancia=40.0, tamano=0.0)
        self.esperar()
        self.assertIs(v._documento, doc)
        self.assertIsNotNone(v._documento_vista().capa(id_forma).estilos.sombra)
        vista = self.vista()
        h, w = vista.shape[:2]
        debajo = vista[int(420 * h / 600), int(400 * w / 800)].astype(int)  # 20 px abajo de la forma
        self.assertGreater(debajo[0], 200)
        self.assertLess(debajo[1], 60)
        # Cancelar: todo como estaba.
        dlg.reject()
        self.esperar()
        self.assertIsNone(ps.dialogo_estilos)
        self.assertIs(v._documento, doc)
        self.assertIsNone(v._doc_provisorio)
        self.assertEqual(v._pos_historial, pasos)
        vista = self.vista()
        self.assertGreater(int(vista[int(420 * h / 600), int(400 * w / 800)].min()), 240)
        # Otra vez, con el menú: sombra y trazo, Aceptar es un paso.
        v.panel_capas.elegir(id_forma)
        ps.acciones["estilo"].trigger()
        dlg = ps.dialogo_estilos
        self.assertIsNotNone(dlg)
        dlg.establecer("sombra", opacidad=1.0, distancia=30.0, tamano=0.0)
        dlg.establecer("trazo", color=(0, 255, 0, 255), grosor=8.0, posicion="afuera")
        dlg.accept()
        self.esperar()
        self.assertEqual(v._pos_historial, pasos + 1)
        self.assertEqual(self.paso(), f"Estilo de capa: «{v._documento.capa(id_forma).nombre}»")
        estilos = v._documento.capa(id_forma).estilos
        self.assertEqual(estilos.activos, ("sombra", "trazo"))
        vista = self.vista()
        borde = vista[int(300 * h / 600), int(504 * w / 800)].astype(int)  # 4 px afuera de la forma
        self.assertGreater(borde[1], 200)
        self.assertLess(borde[0], 60)
        # "fx" en el panel; el botón fx y apagar un estilo con su tilde.
        self.esperar(lambda: v.panel_capas.fila(id_forma) is not None and v.panel_capas.fila(id_forma).fx is not None)
        v.panel_capas.boton_fx.click()
        dlg = ps.dialogo_estilos
        dlg.prender("trazo", False)
        dlg.accept()
        self.esperar()
        estilos = v._documento.capa(id_forma).estilos
        self.assertEqual(estilos.activos, ("sombra",))
        self.assertIsNotNone(estilos.trazo, "apagado, con sus valores")

    def test_renombrar_es_f2_y_el_doble_clic_no_renombra(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeySequence
        from PySide6.QtTest import QTest
        v = self.v
        ps = v.photoshop
        self.documento(400, 300)
        ids = self.agregar(0)
        self.esperar(lambda: v.panel_capas.fila(ids[0]) is not None)
        fila = v.panel_capas.fila(ids[0])
        QTest.mouseDClick(fila.nombre, Qt.LeftButton)
        self.esperar(lambda: ps.dialogo_estilos is not None)
        self.assertFalse(fila.editor.isVisible())
        ps.dialogo_estilos.reject()
        self.esperar()
        f2 = next(a for a in v._pagina_fotos.actions() if a.shortcut() == QKeySequence("F2"))
        f2.trigger()
        fila = v.panel_capas.fila(ids[0])
        self.assertTrue(fila.editor.isVisible())


# ====================================================================== Selector de color
class PruebasSelectorColor(_BaseU2):
    def test_hexadecimal_alfa_recientes_y_cuentagotas(self):
        from celular_natural.ui.selector_color import SelectorColor, desde_hex, recientes
        self.assertEqual(desde_hex("#ff8000"), (255, 128, 0, 255))
        self.assertEqual(desde_hex("f80"), (255, 136, 0, 255))
        self.assertEqual(desde_hex("ff800080"), (255, 128, 0, 128))
        self.assertIsNone(desde_hex("hola"))
        d = SelectorColor((10, 20, 30, 255), "Prueba", True, self.v)
        self.assertEqual(d.color(), (10, 20, 30, 255))
        self.assertTrue(d.establecer_hex("#ff8000"))
        self.assertEqual(d.color(), (255, 128, 0, 255))
        self.assertEqual((d.numeros["r"].value(), d.numeros["g"].value(), d.numeros["b"].value()), (255, 128, 0))
        # El cuadro y la barra de tono siguen al color.
        self.assertAlmostEqual(d.barra_tono.tono, 30.1 / 360, places=2)
        self.assertAlmostEqual(d.cuadro.sat, 1.0, places=6)
        # Alfa: por el hexadecimal y por el número (en %).
        d.campo_hex.setText("ff800080")
        d.campo_hex.editingFinished.emit()
        self.assertEqual(d.color(), (255, 128, 0, 128))
        self.assertAlmostEqual(d.barra_alfa.alfa, 128 / 255, places=6)
        d.numeros["a"].setValue(25)
        self.assertEqual(d.color()[3], round(25 * 2.55))
        # Un hexadecimal que no vale deja el color como estaba.
        antes = d.color()
        self.assertFalse(d.establecer_hex("zzz"))
        self.assertEqual(d.color(), antes)
        # Mover el tono cambia el color (el rojo pasa al verde a 120°).
        d.establecer_color((255, 0, 0, 255))
        d.barra_tono.tono = 1 / 3
        d.barra_tono.cambiado.emit()
        self.assertEqual(d.color()[:3], (0, 255, 0))
        # Aceptar lo suma a los recientes (se recuerdan).
        d.accept()
        self.assertEqual(recientes()[0], (0, 255, 0, 255))
        d2 = SelectorColor((0, 0, 0, 255), "Prueba", False, self.v)
        self.assertEqual(d2.muestras_recientes[0].color, (0, 255, 0, 255))
        d2.establecer_hex("11223344")
        self.assertEqual(d2.color(), (0x11, 0x22, 0x33, 255), "sin alfa")
        d2.reject()
        # Cuentagotas: toma el color de lo que se ve en la vista.
        v = self.v
        self.documento(400, 300, (30, 200, 90))
        d3 = SelectorColor((0, 0, 0, 255), "Prueba", True, v)
        pos = v.vista.mapToGlobal(self.pantalla(200, 150))
        tomado = d3.tomar_de(pos)
        self.assertIsNotNone(tomado)
        self.assertEqual(tomado[:3], (30, 200, 90))
        d3.reject()

    def test_colores_de_frente_y_de_propiedades_usan_el_selector(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        from celular_natural.ui import selector_color
        v = self.v
        ps = v.photoshop
        with mock.patch.object(selector_color, "elegir_color", return_value=(9, 8, 7, 255)) as elegir:
            QTest.mouseClick(ps.colores, Qt.LeftButton, Qt.NoModifier, QPoint(10, 10))
        self.assertEqual(ps.frente, (9, 8, 7))
        self.assertFalse(elegir.call_args.kwargs.get("alfa", True))
        # El color de frente queda para el próximo texto y la próxima forma.
        self.assertEqual(ps.params_texto.color, (9, 8, 7, 255))
        self.assertEqual(ps.params_forma.relleno.colores[0], (9, 8, 7, 255))


# ====================================================================== El flyer
class PruebasFlyer(_BaseU2):
    def test_flyer_de_aceptacion(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QFileDialog
        v = self.v
        ps = v.photoshop
        p = v.panel_capas
        prop = ps.propiedades
        violeta, rosa = (124, 58, 237, 255), (236, 72, 153, 255)
        # 1. Nuevo, historia 1080 × 1920, con fondo degradado.
        self.documento(1080, 1920, fondo=Relleno("lineal", (violeta, rosa), (), 90.0))
        # 2. Cuatro imágenes generadas como capas.
        v.agregar_imagenes_como_capa([str(r) for r in self.fotos])
        self.esperar(lambda: self.quieto() and sum(c.tipo == "imagen" for c in v._documento.capas) == 4)
        imagenes = [c.id for c in v._documento.capas if c.tipo == "imagen"]
        # 3. En una grilla de 2 × 2 (con Propiedades: ancho 460 en proporción, X e Y).
        centros = [(290, 650), (790, 650), (290, 1050), (790, 1050)]
        for id_img, (cx, cy) in zip(imagenes, centros):
            p.elegir(id_img)
            prop.numero_ancho.setValue(460)
            self.esperar()
            x0, y0, x1, y1 = self.caja(id_img)
            prop.numero_x.setValue(cx - (x1 - x0) / 2)
            self.esperar()
            prop.numero_y.setValue(cy - (y1 - y0) / 2)
            self.esperar()
        # 4. El título: blanco, centrado, negrita, con sombra y trazo.
        ps.colores.establecer(frente=(255, 255, 255))
        ps.elegir_herramienta("texto")
        op = ps.opciones_texto
        op.numero_tamano.setValue(110)
        op.botones_alineacion["centro"].click()
        op.boton_negrita.click()
        titulo = self.escribir_texto(540, 300, "GRAN APERTURA")
        dlg = ps.estilo_de_capa(titulo)
        dlg.establecer("sombra", color=(0, 0, 0, 255), opacidad=0.8, angulo=90.0, distancia=14.0, tamano=4.0)
        dlg.establecer("trazo", color=(0, 0, 0, 255), grosor=6.0, posicion="afuera")
        dlg.accept()
        self.esperar()
        # 5. Una banda redondeada amarilla con un texto negro encima.
        ps.colores.establecer(frente=(255, 210, 0))
        ps.elegir_forma("rectangulo")
        ps.opciones_forma.numero_radio.setValue(40)
        self.arrastrar((90, 1450), (990, 1650))
        self.esperar()
        banda = p.capa_elegida
        self.assertEqual(v._documento.capa(banda).params.radio, 40.0)
        ps.colores.establecer(frente=(0, 0, 0))
        ps.elegir_herramienta("texto")
        op.numero_tamano.setValue(90)
        self.assertEqual(ps.params_texto.alineacion, "centro")
        texto_banda = self.escribir_texto(540, 1585, "SABADO 10 HS")
        # 6. Una estrella blanca (1:1).
        ps.colores.establecer(frente=(255, 255, 255))
        ps.elegir_forma("estrella")
        self.arrastrar((860, 1700), (1020, 1860), mods=Qt.ShiftModifier)
        self.esperar()
        estrella = p.capa_elegida
        self.assertEqual(v._documento.capa(estrella).params.tipo, "estrella")
        tipos = [c.tipo for c in v._documento.capas]
        self.assertEqual(tipos, ["relleno", "imagen", "imagen", "imagen", "imagen", "texto", "forma", "texto", "forma",
                                 "ajuste_natural"])
        # 7. Exportar (sin el filtro) y mirar los píxeles.
        destino = self.base / "flyer_u2.png"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "PNG (*.png)")):
            v.exportar(con_filtro=False)
        self.esperar(lambda: not v._exportando and destino.exists())
        out = leer_png(destino).astype(int)
        self.assertEqual(out.shape, (1920, 1080, 3))

        def cerca(px, color, tol=14):
            return all(abs(int(a) - int(b)) <= tol for a, b in zip(px, color))

        # Fondo: violeta arriba, rosa abajo.
        self.assertTrue(cerca(out[3, 540], violeta[:3]), out[3, 540])
        self.assertTrue(cerca(out[1916, 30], rosa[:3]), out[1916, 30])
        # Las cuatro imágenes, cada una en su lugar (su color dominante en el centro).
        r, g, b = (out[650, 290], out[650, 790], out[1050, 290])
        self.assertTrue(r[0] > r[1] + 60 and r[0] > r[2] + 60, r)
        self.assertTrue(g[1] > g[0] + 40 and g[1] > g[2] + 40, g)
        self.assertTrue(b[2] > b[0] + 60 and b[2] > b[1] + 40, b)
        y = out[1050, 790]
        self.assertTrue(y[0] > 150 and y[1] > 120 and y[2] < 110, y)
        # Entre las imágenes, el fondo.
        self.assertTrue(out[850, 540][2] > 150, out[850, 540])
        # El título: letras blancas y su trazo negro, arriba al centro.
        zona = out[170:340, 40:1040]
        blancos = int((zona.min(axis=2) > 235).sum())
        negros = int((zona.max(axis=2) < 40).sum())
        self.assertGreater(blancos, 2000)
        self.assertGreater(negros, 2000)
        x0, y0, x1, y1 = self.caja(titulo)
        self.assertAlmostEqual((x0 + x1) / 2, 540, delta=12)  # centrado donde se hizo clic
        # La sombra: 14 px hacia abajo, más allá del trazo (6 px): oscuro debajo de las letras.
        self.assertEqual(v._documento.capa(titulo).estilos.activos, ("sombra", "trazo"))
        franja = out[int(y1) + 9:int(y1) + 15, int(x0):int(x1)]
        self.assertGreater(int((franja.sum(axis=2) < 200).sum()), 300)
        arriba = out[int(y0) - 15:int(y0) - 9, int(x0):int(x1)]  # arriba no hay sombra
        self.assertLess(int((arriba.sum(axis=2) < 200).sum()), 20)
        # La banda: amarilla, con las esquinas redondeadas.
        self.assertTrue(cerca(out[1470, 150], (255, 210, 0), 6), out[1470, 150])
        self.assertTrue(cerca(out[1640, 900], (255, 210, 0), 6), out[1640, 900])
        self.assertFalse(cerca(out[1451, 91], (255, 210, 0), 40), "la esquina es redonda")
        # El texto de la banda: negro, adentro de la banda.
        bx0, by0, bx1, by1 = self.caja(texto_banda)
        self.assertGreater(by0, 1450)
        self.assertLess(by1, 1650)
        trozo = out[int(by0):int(by1), int(bx0):int(bx1)]
        self.assertGreater(int((trozo.max(axis=2) < 50).sum()), 1500)
        # La estrella: blanca en el centro, y no en la esquina de su caja.
        self.assertTrue(cerca(out[1785, 940], (255, 255, 255), 8), out[1785, 940])
        self.assertFalse(cerca(out[1704, 864], (255, 255, 255), 40))


# ====================================================================== Sesión y proyecto
class PruebasGuardar(_BaseU2):
    def _armar(self, v):
        ps = v.photoshop
        id_texto = None
        ps.elegir_herramienta("texto")
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        QTest.mouseClick(v.vista, Qt.LeftButton, Qt.NoModifier, self.a_pantalla(80, 120, v=v))
        ed = ps.edicion_texto
        QTest.keyClicks(ed.editor, "Guardado")
        QTest.keyClick(ed.editor, Qt.Key_Return, Qt.ControlModifier)
        self.esperar(v=v)
        id_texto = ed.id
        ps.elegir_forma("estrella")
        id_forma = ps.nueva_forma(200, 200, 320, 320)
        self.esperar(v=v)
        dlg = ps.estilo_de_capa(id_forma)
        dlg.establecer("trazo", grosor=4.0)
        dlg.accept()
        self.esperar(v=v)
        return id_texto, id_forma

    def _sigue_editable(self, otra, id_texto, id_forma):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        ps = otra.photoshop
        capa = otra._documento.capa(id_texto)
        self.assertEqual((capa.tipo, capa.params.contenido), ("texto", "Guardado"))
        self.assertEqual(otra._documento.capa(id_forma).params.tipo, "estrella")
        self.assertEqual(otra._documento.capa(id_forma).estilos.activos, ("trazo",))
        ed = ps.editar_texto(id_texto)
        self.assertIsNotNone(ed)
        ed.editor.selectAll()
        QTest.keyClicks(ed.editor, "Editable")
        QTest.keyClick(ed.editor, Qt.Key_Return, Qt.ControlModifier)
        self.esperar(v=otra)
        self.assertEqual(otra._documento.capa(id_texto).params.contenido, "Editable")
        otra.panel_capas.elegir(id_forma)
        ps.elegir_herramienta("formas")
        ps.opciones_forma.numero_puntas.setValue(7)
        self.esperar(v=otra)
        self.assertEqual(otra._documento.capa(id_forma).params.puntas, 7)

    def test_proyecto_nslite(self):
        from PySide6.QtWidgets import QFileDialog
        v = self.v
        self.documento(500, 400, (10, 120, 60))
        id_texto, id_forma = self._armar(v)
        doc = v._documento
        ruta = self.base / "texto_formas.nslite"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(ruta), "")):
            v.guardar_proyecto()
        self.esperar(lambda: not v._guardando_proyecto and ruta.exists())
        otra = self.ventana()
        otra.abrir_proyecto(str(ruta))
        self.esperar(lambda: self.quieto(otra) and otra._documento is not None and not otra._documento.tiene_foto,
                     otra)
        self.assertEqual(otra._documento, doc)
        self._sigue_editable(otra, id_texto, id_forma)

    def test_sesion(self):
        v = self.ventana(sesion=True)
        self.documento(600, 400, (90, 20, 20), v=v)
        id_texto, id_forma = self._armar(v)
        doc = v._documento
        v.close()
        self.ventanas.remove(v)
        v.deleteLater()
        self.app.processEvents()
        otra = self.ventana(sesion=True)
        self.esperar(lambda: self.quieto(otra) and otra._documento is not None, otra)
        self.assertEqual(otra._documento, doc)
        self._sigue_editable(otra, id_texto, id_forma)


if __name__ == "__main__":
    unittest.main()
