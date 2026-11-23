"""Pruebas de zonas por capa y recorte no destructivo."""

from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from celular_natural.motor import (  # noqa: E402
    PRESET_PRINCIPAL, PRESETS, Recorte, Zona, aplicar_recorte, mascara_zona, procesar_pila,
)


def imagen(w=320, h=240, semilla=0):
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.dstack([0.2 + 0.6 * xx / w, 0.3 + 0.4 * yy / h, 0.6 - 0.3 * xx / w])
    img += 0.08 * rng.random((h, w, 1))
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


class PruebasMascara(unittest.TestCase):
    def test_rectangulo_y_elipse(self):
        for forma in ("rect", "elipse"):
            with self.subTest(forma=forma):
                m = mascara_zona(Zona(forma, 0.25, 0.25, 0.75, 0.75, pluma=30), 200, 400)
                self.assertEqual(m.shape, (200, 400))
                self.assertEqual(m.dtype, np.float32)
                self.assertAlmostEqual(float(m[100, 200]), 1.0, places=4)
                self.assertAlmostEqual(float(m[2, 2]), 0.0, places=4)
                self.assertGreaterEqual(float(m.min()), 0.0)
                self.assertLessEqual(float(m.max()), 1.0)

    def test_borde_suave_sin_saltos(self):
        # Zona de 400x400 px: el borde suave mide ~84 px.
        m = mascara_zona(Zona("rect", 0.3, 0.0, 0.7, 1.0, pluma=60), 400, 1000)
        fila = m[200]
        self.assertLess(float(np.abs(np.diff(fila)).max()), 0.05, "el borde debe fundirse, sin corte duro")
        duro = mascara_zona(Zona("rect", 0.3, 0.0, 0.7, 1.0, pluma=0), 400, 1000)[200]
        self.assertGreater(float(np.abs(np.diff(duro)).max()), 0.5)

    def test_invertir(self):
        z = Zona("elipse", 0.2, 0.2, 0.8, 0.8, pluma=20)
        m = mascara_zona(z, 120, 160)
        mi = mascara_zona(replace(z, invertir=True), 120, 160)
        self.assertTrue(np.allclose(m + mi, 1.0, atol=1e-5))

    def test_independiente_de_la_resolucion(self):
        z = Zona("elipse", 0.1, 0.2, 0.6, 0.9, pluma=40)
        grande = mascara_zona(z, 600, 800)
        chica = mascara_zona(z, 150, 200)
        import cv2
        reducida = cv2.resize(grande, (200, 150), interpolation=cv2.INTER_AREA)
        self.assertLess(float(np.abs(reducida - chica).mean()), 0.02)

    def test_zona_sigue_a_la_foto_al_recortar(self):
        # Zona en el cuadrante superior izquierdo de la foto original.
        z = Zona("rect", 0.0, 0.0, 0.5, 0.5, pluma=0)
        r = Recorte(0.25, 0.25, 1.0, 1.0)
        m = mascara_zona(z, 300, 300, r)
        # En el encuadre recortado la zona ocupa solo el primer tercio.
        self.assertAlmostEqual(float(m[10, 10]), 1.0, places=4)
        self.assertAlmostEqual(float(m[200, 200]), 0.0, places=4)
        # Ocupa el primer tercio en ancho y en alto: 1/3 de la franja izquierda.
        self.assertAlmostEqual(float(m[:, :100].mean()), 1.0 / 3, delta=0.02)


class PruebasLazo(unittest.TestCase):
    TRIANGULO = [(0.2, 0.8), (0.5, 0.1), (0.8, 0.8)]

    def test_lazo_rellena_la_forma(self):
        for forma in ("lazo", "poligono"):
            with self.subTest(forma=forma):
                z = Zona.desde_puntos(forma, self.TRIANGULO, pluma=0)
                self.assertTrue(z.es_libre)
                m = mascara_zona(z, 400, 400)
                self.assertAlmostEqual(float(m[260, 200]), 1.0, places=3)  # adentro
                self.assertAlmostEqual(float(m[40, 40]), 0.0, places=3)    # afuera
                # Área del triángulo = 0.5 * 0.6 * 0.7 = 0.21 de la foto
                self.assertAlmostEqual(float(m.mean()), 0.21, delta=0.01)

    def test_lazo_borde_suave(self):
        m = mascara_zona(Zona.desde_puntos("lazo", self.TRIANGULO, pluma=60), 400, 400)
        self.assertLess(float(np.abs(np.diff(m, axis=1)).max()), 0.06)

    def test_lazo_con_recorte_y_resolucion(self):
        z = Zona.desde_puntos("poligono", [(0.1, 0.1), (0.5, 0.1), (0.5, 0.5), (0.1, 0.5)], pluma=0)
        r = Recorte(0.1, 0.1, 0.9, 0.9)
        m = mascara_zona(z, 400, 400, r)
        # En el encuadre recortado el cuadrado ocupa la mitad superior izquierda.
        self.assertAlmostEqual(float(m[50, 50]), 1.0, places=3)
        self.assertAlmostEqual(float(m[300, 300]), 0.0, places=3)
        import cv2
        grande = mascara_zona(Zona.desde_puntos("lazo", self.TRIANGULO, pluma=40), 800, 800)
        chica = mascara_zona(Zona.desde_puntos("lazo", self.TRIANGULO, pluma=40), 200, 200)
        self.assertLess(float(np.abs(cv2.resize(grande, (200, 200), interpolation=cv2.INTER_AREA) - chica).mean()), 0.02)

    def test_capa_con_lazo(self):
        rgb = imagen(400, 300)
        base = PRESETS[PRESET_PRINCIPAL]
        z = Zona.desde_puntos("lazo", [(0.05, 0.05), (0.35, 0.05), (0.35, 0.95), (0.05, 0.95)], pluma=0)
        solo = procesar_pila(rgb, [base])
        con = procesar_pila(rgb, [base, PRESETS["Noche urbana"]], zonas=[None, z])
        dif = np.abs(con.astype(np.int16) - solo.astype(np.int16)).mean(axis=(0, 2))
        self.assertGreater(float(dif[40:120].mean()), 2.0)
        self.assertLess(float(dif[200:].mean()), 0.01)


class PruebasPincel(unittest.TestCase):
    """Zona pintada a mano: trazos (puntos, radio relativo al lado largo, dureza, borrar)."""

    LINEA = (((0.2, 0.5), (0.8, 0.5)), 0.05, 100, False)  # trazo horizontal, radio 5 %

    def test_pinta_donde_corresponde(self):
        z = Zona.desde_trazos([self.LINEA])
        self.assertTrue(z.es_pincel)
        self.assertFalse(z.es_libre)
        m = mascara_zona(z, 400, 400)
        self.assertEqual(m.dtype, np.float32)
        self.assertAlmostEqual(float(m[200, 200]), 1.0, places=4)  # sobre el trazo
        self.assertAlmostEqual(float(m[200, 40]), 0.0, places=4)   # antes del comienzo
        self.assertAlmostEqual(float(m[100, 200]), 0.0, places=4)  # lejos de la línea
        # Área = rectángulo 240x40 + los dos medios círculos de las puntas (radio 20 px).
        self.assertAlmostEqual(float(m.sum()), 240 * 40 + np.pi * 20 ** 2, delta=60)
        # El recuadro abarca lo pintado (para ubicar la etiqueta).
        self.assertAlmostEqual(z.x0, 0.15)
        self.assertAlmostEqual(z.x1, 0.85)
        # En una foto apaisada 3:2 el radio (relativo al lado largo) ocupa más en y.
        apaisada = Zona.desde_trazos([self.LINEA], aspecto=1.5)
        self.assertAlmostEqual(apaisada.y0, 0.5 - 0.075)
        m = mascara_zona(apaisada, 400, 600)
        filas = np.where(m.max(axis=1) > 0.5)[0]
        self.assertAlmostEqual(filas[0] / 400, apaisada.y0, delta=0.005)

    def test_un_clic_pinta_un_punto(self):
        m = mascara_zona(Zona.desde_trazos([(((0.5, 0.5),), 0.1, 100, False)]), 400, 400)
        self.assertAlmostEqual(float(m.sum()), np.pi * 40 ** 2, delta=40)

    def test_trazo_desde_afuera_del_borde(self):
        # El centro del trazo pasa 8 px afuera de la foto, pero el radio (20 px) entra.
        m = mascara_zona(Zona.desde_trazos([(((-0.02, 0.2), (-0.02, 0.8)), 0.05, 100, False)]), 400, 400)
        self.assertAlmostEqual(float(m[200, 5]), 1.0, places=4)
        self.assertAlmostEqual(float(m[200, 20]), 0.0, places=4)
        self.assertAlmostEqual(float(m[:, :12].mean()) / 0.6, 1.0, delta=0.12)  # franja de ~12 px

    def test_goma_borra(self):
        goma = (((0.5, 0.2), (0.5, 0.8)), 0.05, 100, True)  # trazo vertical que borra
        m = mascara_zona(Zona.desde_trazos([self.LINEA, goma]), 400, 400)
        self.assertAlmostEqual(float(m[200, 200]), 0.0, places=4)  # cruce: borrado
        self.assertAlmostEqual(float(m[200, 120]), 1.0, places=4)  # el resto sigue pintado
        # Pintar de nuevo encima de lo borrado lo recupera (el orden importa).
        repinta = (((0.45, 0.5), (0.55, 0.5)), 0.05, 100, False)
        m2 = mascara_zona(Zona.desde_trazos([self.LINEA, goma, repinta]), 400, 400)
        self.assertAlmostEqual(float(m2[200, 200]), 1.0, places=4)
        # Solo goma: no queda nada pintado.
        self.assertEqual(float(mascara_zona(Zona.desde_trazos([goma]), 100, 100).max()), 0.0)

    def test_dureza_suaviza_el_borde(self):
        duro = mascara_zona(Zona.desde_trazos([self.LINEA]), 400, 400)
        suave = mascara_zona(Zona.desde_trazos([(self.LINEA[0], 0.05, 0, False)]), 400, 400)
        columna_dura, columna_suave = duro[:, 200], suave[:, 200]
        self.assertGreater(float(np.abs(np.diff(columna_dura)).max()), 0.45, "duro: corte neto")
        self.assertLess(float(np.abs(np.diff(columna_suave)).max()), 0.1, "suave: se funde")
        self.assertAlmostEqual(float(suave[200, 200]), 1.0, places=3)  # el centro pinta completo
        self.assertTrue(np.all(suave <= duro + 1e-6))  # lo suave nunca pasa el radio
        # A media dureza el centro queda firme y solo el borde se funde.
        medio = mascara_zona(Zona.desde_trazos([(self.LINEA[0], 0.05, 50, False)]), 400, 400)
        self.assertAlmostEqual(float(medio[208, 200]), 1.0, places=3)
        self.assertTrue(0.0 < float(medio[216, 200]) < 1.0)

    def test_independiente_de_la_resolucion(self):
        import cv2
        z = Zona.desde_trazos([(((0.1, 0.2), (0.4, 0.7), (0.8, 0.3)), 0.04, 40, False),
                               (((0.3, 0.1), (0.3, 0.9)), 0.02, 100, True)])
        grande = mascara_zona(z, 600, 800)
        chica = mascara_zona(z, 150, 200)
        reducida = cv2.resize(grande, (200, 150), interpolation=cv2.INTER_AREA)
        self.assertLess(float(np.abs(reducida - chica).mean()), 0.02)
        self.assertAlmostEqual(float(grande.mean()), float(chica.mean()), delta=0.01)

    def test_respeta_el_recorte(self):
        # Punto en el centro de la foto original con radio 10 % del lado largo.
        z = Zona.desde_trazos([(((0.5, 0.5),), 0.1, 100, False)])
        completa = mascara_zona(z, 400, 400)
        # Recorte a la mitad central, con la misma escala de píxeles (200x200).
        r = Recorte(0.25, 0.25, 0.75, 0.75)
        recortada = mascara_zona(z, 200, 200, r)
        self.assertAlmostEqual(float(recortada[100, 100]), 1.0, places=4)
        self.assertAlmostEqual(float(recortada.sum()), float(completa.sum()), delta=30)  # mismo radio en px
        # Trazo en la esquina superior izquierda de la original: fuera del encuadre recortado.
        afuera = Zona.desde_trazos([(((0.05, 0.05), (0.15, 0.05)), 0.03, 100, False)])
        self.assertEqual(float(mascara_zona(afuera, 200, 200, r).max()), 0.0)
        # Recorte que deja la mitad izquierda: el punto queda en el borde derecho.
        mitad = mascara_zona(z, 400, 200, Recorte(0.0, 0.0, 0.5, 1.0))
        self.assertAlmostEqual(float(mitad[200, 199]), 1.0, places=4)
        self.assertAlmostEqual(float(mitad.sum()), float(completa.sum()) / 2, delta=40)

    def test_invertir_congelada_y_comparable(self):
        trazos = [self.LINEA, (((0.5, 0.3), (0.5, 0.7)), 0.03, 20, True)]
        z = Zona.desde_trazos(trazos, pluma=10)
        self.assertEqual(z, Zona.desde_trazos(trazos, pluma=10))  # el historial compara con ==
        self.assertNotEqual(z, Zona.desde_trazos(trazos[:1], pluma=10))
        self.assertIsInstance(hash(z), int)
        with self.assertRaises(Exception):
            z.forma = "rect"  # congelada
        m = mascara_zona(z, 120, 160)
        mi = mascara_zona(replace(z, invertir=True), 120, 160)
        self.assertTrue(np.allclose(m + mi, 1.0, atol=1e-5))
        # El borde suave de las otras zonas no cambia lo pintado.
        self.assertTrue(np.array_equal(m, mascara_zona(replace(z, pluma=90), 120, 160)))

    def test_capa_con_pincel(self):
        rgb = imagen(400, 300)
        base = PRESETS[PRESET_PRINCIPAL]
        z = Zona.desde_trazos([(((0.1, 0.2), (0.1, 0.8)), 0.08, 100, False)])
        solo = procesar_pila(rgb, [base])
        con = procesar_pila(rgb, [base, PRESETS["Noche urbana"]], zonas=[None, z])
        dif = np.abs(con.astype(np.int16) - solo.astype(np.int16)).mean(axis=(0, 2))
        self.assertGreater(float(dif[25:55].mean()), 2.0)   # columna pintada (x ≈ 40 px)
        self.assertLess(float(dif[150:].mean()), 0.01)       # lejos de lo pintado, igual


class PruebasVistaPincel(unittest.TestCase):
    """Pintar con el mouse sobre la vista previa (Qt sin ventana visible)."""

    def test_pintar_borrar_y_terminar(self):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QImage
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from celular_natural.motor.zonas import mascara_trazos
        from celular_natural.ui.vista_comparacion import VistaComparacion

        app = QApplication.instance() or QApplication([])  # noqa: F841
        vista = VistaComparacion()
        vista.resize(820, 620)
        img = QImage(800, 600, QImage.Format_RGB888)
        img.fill(0x808080)
        vista.establecer_imagenes(img, None, (800, 600))
        vista.establecer_herramienta("zona", forma="pincel")
        self.assertTrue(vista.pintando)
        recibidos = []
        vista.trazosTerminados.connect(recibidos.append)

        def punto(x, y):
            p = vista._origen + QPointF(x * 800, y * 600) * vista.zoom
            return QPoint(round(p.x()), round(p.y()))

        def arrastrar(boton, a, b):
            QTest.mousePress(vista, boton, Qt.NoModifier, punto(*a))
            for k in range(1, 11):
                QTest.mouseMove(vista, punto(a[0] + (b[0] - a[0]) * k / 10, a[1] + (b[1] - a[1]) * k / 10))
            QTest.mouseRelease(vista, boton, Qt.NoModifier, punto(*b))

        arrastrar(Qt.LeftButton, (0.2, 0.5), (0.8, 0.5))
        arrastrar(Qt.RightButton, (0.5, 0.3), (0.5, 0.7))  # el clic derecho borra
        QTest.keyClick(vista, Qt.Key_Return)
        self.assertEqual(len(recibidos), 1)
        trazos = recibidos[0]
        self.assertEqual([t[3] for t in trazos], [False, True])
        (x0, y0), (x1, y1) = trazos[0][0][0], trazos[0][0][-1]
        self.assertAlmostEqual(x0, 0.2, delta=0.01)
        self.assertAlmostEqual(x1, 0.8, delta=0.01)
        self.assertAlmostEqual(y0, 0.5, delta=0.01)
        # Lo que se vio en rosa es lo mismo que después rasteriza el motor.
        lh, lw = vista._lienzo.shape
        m = mascara_trazos(trazos, lh, lw, max(lh, lw))
        self.assertLess(float(np.abs(m - vista._lienzo).mean()), 0.005)
        self.assertAlmostEqual(float(vista._lienzo[lh // 2, lw // 2]), 0.0, places=3)  # borrado
        self.assertAlmostEqual(float(vista._lienzo[lh // 2, lw // 3]), 1.0, places=3)  # pintado
        # Retroceso quita el último trazo (la goma) y vuelve a quedar pintado el cruce.
        QTest.keyClick(vista, Qt.Key_Backspace)
        self.assertAlmostEqual(float(vista._lienzo[lh // 2, lw // 2]), 1.0, places=3)
        vista.establecer_herramienta(None)
        self.assertFalse(vista.pintando)


class PruebasRecorte(unittest.TestCase):
    def test_recorte_basico(self):
        rgb = imagen(400, 300)
        r = Recorte(0.1, 0.2, 0.6, 0.9)
        out = aplicar_recorte(rgb, r)
        self.assertEqual(out.shape, (210, 200, 3))
        self.assertTrue(np.array_equal(out, rgb[60:270, 40:240]))

    def test_sin_recorte_no_copia(self):
        rgb = imagen()
        self.assertIs(aplicar_recorte(rgb, None), rgb)
        self.assertIs(aplicar_recorte(rgb, Recorte(0, 0, 1, 1)), rgb)

    def test_recorte_invertido_y_fuera_de_rango(self):
        rgb = imagen(100, 100)
        out = aplicar_recorte(rgb, Recorte(1.2, 0.9, -0.1, 0.1))
        self.assertEqual(out.shape[:2], (80, 100))
        self.assertGreaterEqual(aplicar_recorte(rgb, Recorte(0.5, 0.5, 0.5, 0.5)).size, 3)

    def test_original_intacto(self):
        rgb = imagen()
        copia = rgb.copy()
        procesar_pila(aplicar_recorte(rgb, Recorte(0.1, 0.1, 0.9, 0.9)), [PRESETS[PRESET_PRINCIPAL]])
        self.assertTrue(np.array_equal(rgb, copia))


class PruebasCapaConZona(unittest.TestCase):
    def test_capa_solo_afecta_su_zona(self):
        rgb = imagen(400, 300)
        base = PRESETS[PRESET_PRINCIPAL]
        capa = PRESETS["Noche urbana"]
        solo_base = procesar_pila(rgb, [base])
        con_zona = procesar_pila(rgb, [base, capa], zonas=[None, Zona("rect", 0.0, 0.0, 0.4, 1.0, pluma=0)])
        dif = np.abs(con_zona.astype(np.int16) - solo_base.astype(np.int16)).mean(axis=(0, 2))
        self.assertGreater(float(dif[:140].mean()), 2.0, "dentro de la zona la capa debe notarse")
        self.assertLess(float(dif[180:].mean()), 0.01, "fuera de la zona no debe cambiar nada")
        self.assertEqual(con_zona.shape, rgb.shape)

    def test_sin_zonas_igual_que_antes(self):
        rgb = imagen()
        pila = [PRESETS[PRESET_PRINCIPAL], PRESETS["Día nublado"]]
        self.assertTrue(np.array_equal(procesar_pila(rgb, pila), procesar_pila(rgb, pila, zonas=[None, None])))


if __name__ == "__main__":
    unittest.main()


class PruebasQuitarFondo(unittest.TestCase):
    def test_alfa_y_recorte_al_objeto(self):
        from celular_natural.ui.ventana import alpha_con_fondo, recortar_a_objeto
        z = Zona.desde_puntos("poligono", [(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)], pluma=0)
        a = alpha_con_fondo(None, z, None, 200, 400)
        self.assertEqual(a.dtype, np.uint8)
        self.assertEqual(int(a[100, 200]), 255)
        self.assertEqual(int(a[5, 5]), 0)
        self.assertIsNone(alpha_con_fondo(None, None, None, 10, 10))
        rgb = imagen(400, 200)
        r2, a2 = recortar_a_objeto(rgb, a, margen=0.0)
        self.assertEqual(r2.shape[:2], a2.shape)
        self.assertAlmostEqual(a2.shape[1], 200, delta=3)
        self.assertAlmostEqual(a2.shape[0], 100, delta=3)

    def test_combina_con_transparencia_existente(self):
        from celular_natural.ui.ventana import alpha_con_fondo
        z = Zona("rect", -0.1, -0.1, 1.1, 1.1, pluma=0)
        previa = np.full((50, 50), 128, np.uint8)
        a = alpha_con_fondo(previa, z, None, 50, 50)
        self.assertAlmostEqual(float(a.mean()), 128, delta=1)
