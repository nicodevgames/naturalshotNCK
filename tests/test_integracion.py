"""Pruebas de la integración de geometría, selección automática y borrado de objetos.

* Zonas "mascara" (raster): congeladas, comparables, al tamaño pedido, con
  recorte, trazos encima y matriz de geometría.
* Conversión de zonas, recorte y borrados al girar, voltear y enderezar: lo
  marcado sigue sobre el mismo objeto.
* Borrar objetos (rellenar y clonar) con caché.
* Historial: textos nuevos y estados viejos que se siguen pudiendo abrir.
* Ventana real (sin pantalla): la exportación es idéntica a la vista y el
  resultado coincide con el orden documentado del motor.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from celular_natural.motor import (  # noqa: E402
    PRESET_PRINCIPAL, PRESETS, Geometria, Recorte, Zona, ZonaBorrado, aplicar_borrados, aplicar_geometria,
    aplicar_recorte, convertir_borrado, convertir_recorte, convertir_zona, mascara_zona, procesar_pila,
    tamano_resultante,
)
from celular_natural.motor.zonas import mascara_registrada, raster_zona  # noqa: E402

GEOMETRIAS = (Geometria(1), Geometria(3), Geometria(2), Geometria(0, True), Geometria(0, False, True),
              Geometria(1, True), Geometria(enderezar=6.0), Geometria(3, False, True, -4.5))


def escena(w=480, h=360, semilla=0):
    """Cielo arriba, pasto con textura abajo, un cuadrado rojo y una franja azul."""
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cielo = np.dstack([90 + 60 * yy / h, 150 + 50 * yy / h, 230 + 0 * yy])
    grano = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), 1.5)
    pasto = np.dstack([60 + 0 * xx, 120 + 0 * xx, 50 + 0 * xx]) + 30 * grano[..., None]
    img = np.where((yy > h * 0.5)[..., None], pasto, cielo)
    img[int(h * 0.60):int(h * 0.80), int(w * 0.30):int(w * 0.40)] = (210, 30, 30)
    img[int(h * 0.15):int(h * 0.30), int(w * 0.65):int(w * 0.90)] = (30, 40, 160)
    img += rng.normal(0, 2, (h, w, 1))
    return np.clip(img + 0.5, 0, 255).astype(np.uint8)


def rojez(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0].astype(np.int16) - rgb[..., 1]


class PruebasZonaMascara(unittest.TestCase):
    def setUp(self):
        self.m = np.zeros((300, 400), np.float32)
        cv2.circle(self.m, (120, 90), 50, 1.0, -1)
        self.m = cv2.GaussianBlur(self.m, (0, 0), 2)

    def test_congelada_comparable_y_recuadro(self):
        z = Zona.desde_mascara(self.m, "cielo")
        self.assertTrue(z.es_mascara and z.es_raster and not z.es_pincel)
        self.assertEqual(z, Zona.desde_mascara(self.m, "cielo"))  # el historial compara con ==
        self.assertNotEqual(z, Zona.desde_mascara(self.m, "piel"))
        self.assertIsInstance(hash(z), int)
        with self.assertRaises(Exception):
            z.forma = "rect"
        self.assertAlmostEqual(z.x0, 70 / 400, delta=0.01)
        self.assertAlmostEqual(z.y1, 140 / 300, delta=0.01)
        self.assertLess(len(z.datos), 20_000)

    def test_al_tamano_pedido_con_recorte_e_invertir(self):
        z = Zona.desde_mascara(self.m)
        self.assertLess(float(np.abs(mascara_zona(z, 300, 400) - self.m).max()), 1 / 255 + 1e-6)
        chica = mascara_zona(z, 150, 200)
        self.assertEqual(chica.shape, (150, 200))
        esperado = cv2.resize(self.m, (200, 150), interpolation=cv2.INTER_AREA)
        self.assertLess(float(np.abs(chica - esperado).mean()), 0.01)
        r = Recorte(0.1, 0.1, 0.6, 0.7)
        recortada = mascara_zona(z, 180, 200, r)
        self.assertLess(float(np.abs(recortada - aplicar_recorte(self.m, r)).mean()), 0.01)
        invertida = mascara_zona(replace(z, invertir=True), 300, 400)
        self.assertTrue(np.allclose(invertida + mascara_zona(z, 300, 400), 1.0, atol=1e-5))

    def test_sin_version_completa_usa_la_guardada(self):
        grande = cv2.resize(self.m, (2400, 1800), interpolation=cv2.INTER_LINEAR)
        z = Zona.desde_mascara(grande)
        self.assertIsNotNone(mascara_registrada(z.datos))
        con = mascara_zona(z, 1800, 2400)
        from celular_natural.motor import zonas
        with zonas._CANDADO_ALTA:
            guardada = zonas._ALTA.pop(z.datos)
        try:
            sin = mascara_zona(z, 1800, 2400)  # sale del PNG compacto (lado 1024) ampliado
        finally:
            zonas.registrar_mascara(z.datos, guardada)
        self.assertLess(float(np.abs(con - grande).max()), 1 / 255 + 1e-6)
        self.assertLess(float(np.abs(sin - grande).mean()), 0.01)

    def test_pincel_encima_suma_y_resta(self):
        z = Zona.desde_mascara(self.m)
        resta = (((0.2, 0.3), (0.4, 0.3)), 0.03, 100, True)  # cruza el disco
        suma = (((0.8, 0.8), (0.9, 0.8)), 0.03, 100, False)  # lejos del disco
        corregida = replace(z, trazos=(resta, suma))
        m = mascara_zona(corregida, 300, 400)
        self.assertAlmostEqual(float(m[90, 120]), 0.0, places=3)   # borrado
        self.assertAlmostEqual(float(m[60, 120]), 1.0, places=2)   # el resto del disco sigue
        self.assertAlmostEqual(float(m[240, 340]), 1.0, places=3)  # pintado nuevo

    def test_matriz_de_geometria_sin_remuestrear(self):
        z = Zona.desde_mascara(self.m)
        h, w = self.m.shape
        for geo in GEOMETRIAS:
            with self.subTest(geo=geo):
                z2 = convertir_zona(z, Geometria(), geo, w, h)
                self.assertEqual(z2.datos, z.datos)  # la máscara guardada no cambia
                w2, h2 = tamano_resultante(w, h, geo)
                esperado = aplicar_geometria(self.m, geo, interpolacion=cv2.INTER_LINEAR)
                self.assertLess(float(np.abs(mascara_zona(z2, h2, w2) - esperado).mean()), 0.003)
                vuelta = convertir_zona(z2, geo, Geometria(), w, h)
                self.assertLess(float(np.abs(mascara_zona(vuelta, h, w) - self.m).mean()), 1e-4)

    def test_raster_zona_lleva_al_encuadre(self):
        z = Zona.desde_mascara(self.m)
        r = Recorte(0.0, 0.0, 0.5, 0.5)
        m = raster_zona(z, 150, 200, r)
        self.assertLess(float(np.abs(m - self.m[:150, :200]).mean()), 0.005)


class PruebasConversionGeometria(unittest.TestCase):
    """Una zona marcada sobre un objeto sigue sobre él después de girar o enderezar."""

    def setUp(self):
        self.rgb = escena()
        self.h, self.w = self.rgb.shape[:2]
        # Zonas sobre el cuadrado rojo (0.30..0.40 x 0.60..0.80), de cada forma.
        self.zonas = [
            Zona("rect", 0.31, 0.62, 0.39, 0.78, pluma=0),
            Zona("elipse", 0.31, 0.62, 0.39, 0.78, pluma=0),
            Zona.desde_puntos("poligono", [(0.31, 0.62), (0.39, 0.62), (0.39, 0.78), (0.31, 0.78)], pluma=0),
            Zona.desde_trazos([(((0.35, 0.64), (0.35, 0.76)), 0.02, 100, False)], aspecto=self.w / self.h),
        ]

    def test_la_zona_sigue_sobre_el_objeto(self):
        for geo in GEOMETRIAS:
            base = aplicar_geometria(self.rgb, geo)
            h2, w2 = base.shape[:2]
            for zona in self.zonas:
                with self.subTest(geo=geo, forma=zona.forma):
                    z2 = convertir_zona(zona, Geometria(), geo, self.w, self.h)
                    m = mascara_zona(z2, h2, w2) > 0.5
                    self.assertGreater(int(m.sum()), 50)
                    self.assertGreater(float(rojez(base)[m].mean()), 150, "la zona quedó fuera del objeto")

    def test_rectangulo_torcido_pasa_a_poligono(self):
        rect, elipse = self.zonas[0], self.zonas[1]
        self.assertEqual(convertir_zona(rect, Geometria(), Geometria(1), self.w, self.h).forma, "rect")
        self.assertEqual(convertir_zona(elipse, Geometria(), Geometria(0, True), self.w, self.h).forma, "elipse")
        self.assertEqual(convertir_zona(rect, Geometria(), Geometria(enderezar=3.0), self.w, self.h).forma, "poligono")
        self.assertEqual(convertir_zona(elipse, Geometria(), Geometria(enderezar=3.0), self.w, self.h).forma,
                         "poligono")
        # Ida y vuelta con giros: exacta.
        ida = convertir_zona(rect, Geometria(), Geometria(1, True), self.w, self.h)
        vuelta = convertir_zona(ida, Geometria(1, True), Geometria(), self.w, self.h)
        for a, b in zip((rect.x0, rect.y0, rect.x1, rect.y1), (vuelta.x0, vuelta.y0, vuelta.x1, vuelta.y1)):
            self.assertAlmostEqual(a, b, places=9)

    def test_radio_del_pincel_en_pixeles_no_cambia(self):
        pincel = self.zonas[3]
        geo = Geometria(enderezar=8.0)
        z2 = convertir_zona(pincel, Geometria(), geo, self.w, self.h)
        w2, h2 = tamano_resultante(self.w, self.h, geo)
        self.assertAlmostEqual(z2.trazos[0][1] * max(w2, h2), pincel.trazos[0][1] * max(self.w, self.h), places=6)

    def test_recorte(self):
        r = Recorte(0.1, 0.2, 0.5, 0.6)
        girado = convertir_recorte(r, Geometria(), Geometria(1), self.w, self.h)
        self.assertEqual(girado, Recorte(0.4, 0.1, 0.8, 0.5))
        espejo = convertir_recorte(r, Geometria(), Geometria(0, True), self.w, self.h)
        self.assertAlmostEqual(espejo.x0, 0.5)
        self.assertAlmostEqual(espejo.x1, 0.9)
        # Enderezar: mismo tamaño en píxeles y el centro sobre el mismo punto de la foto.
        geo = Geometria(enderezar=5.0)
        e = convertir_recorte(r, Geometria(), geo, self.w, self.h)
        w2, h2 = tamano_resultante(self.w, self.h, geo)
        self.assertAlmostEqual((e.x1 - e.x0) * w2, (r.x1 - r.x0) * self.w, places=6)
        self.assertAlmostEqual((e.y1 - e.y0) * h2, (r.y1 - r.y0) * self.h, places=6)
        from celular_natural.motor.geometria import transformar_puntos
        cx, cy = transformar_puntos(((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2), geo, self.w, self.h)
        self.assertAlmostEqual((e.x0 + e.x1) / 2, cx, places=6)
        self.assertAlmostEqual((e.y0 + e.y1) / 2, cy, places=6)
        # Un recorte grande que ya no entra se achica parejo, sin salirse.
        casi = convertir_recorte(Recorte(0.0, 0.0, 0.99, 1.0), Geometria(), geo, self.w, self.h)
        self.assertTrue(casi is None or (casi.x0 >= 0 and casi.x1 <= 1 and casi.y0 >= 0 and casi.y1 <= 1))
        self.assertIsNone(convertir_recorte(None, Geometria(), geo, self.w, self.h))


class PruebasBorrado(unittest.TestCase):
    def setUp(self):
        self.rgb = escena()
        self.h, self.w = self.rgb.shape[:2]
        self.rojo = Zona("rect", 0.28, 0.58, 0.42, 0.82, pluma=10)

    def test_rellenar_quita_el_objeto(self):
        salida = aplicar_borrados(self.rgb, (ZonaBorrado(self.rojo),), clave=("prueba", "rellenar"))
        self.assertEqual(salida.shape, self.rgb.shape)
        self.assertLess(float((rojez(salida) > 100).mean()), 0.001)
        lejos = mascara_zona(replace(self.rojo, x0=0.2, y0=0.5, x1=0.5, y1=0.9), self.h, self.w) < 0.01
        self.assertTrue(np.array_equal(salida[lejos], self.rgb[lejos]), "fuera de la zona no cambia nada")
        self.assertFalse(salida.flags.writeable)
        # Caché: la misma clave devuelve el mismo arreglo, sin recalcular.
        self.assertIs(aplicar_borrados(self.rgb, (ZonaBorrado(self.rojo),), clave=("prueba", "rellenar")), salida)

    def test_clonar_copia_desde_la_fuente(self):
        b = ZonaBorrado(self.rojo, "clonar", dx=0.3, dy=0.0, sin_costuras=False)
        salida = aplicar_borrados(self.rgb, (b,))
        self.assertLess(float((rojez(salida) > 100).mean()), 0.001)
        # Clonar sin fuente elegida todavía no hace nada.
        self.assertIs(aplicar_borrados(self.rgb, (ZonaBorrado(self.rojo, "clonar"),)), self.rgb)
        self.assertIs(aplicar_borrados(self.rgb, ()), self.rgb)

    def test_varias_zonas_en_orden(self):
        azul = Zona("rect", 0.63, 0.13, 0.92, 0.32, pluma=10)
        uno = aplicar_borrados(self.rgb, (ZonaBorrado(self.rojo),), clave="varias")
        dos = aplicar_borrados(self.rgb, (ZonaBorrado(self.rojo), ZonaBorrado(azul)), clave="varias")
        self.assertLess(float((rojez(dos) > 100).mean()), 0.001)
        def franja_azul(img):
            return float(((img[..., 0] < 60) & (img[..., 2] > 120)).mean())

        self.assertGreater(franja_azul(self.rgb), 0.02)
        self.assertLess(franja_azul(dos), 0.001)
        self.assertGreater(franja_azul(uno), 0.02)  # el primero solo borra el rojo
        self.assertTrue(np.array_equal(uno[self.h // 2:], dos[self.h // 2:]))

    def test_convertir_borrado_con_la_geometria(self):
        b = ZonaBorrado(self.rojo, "clonar", dx=0.25, dy=0.0)
        geo = Geometria(1)
        b2 = convertir_borrado(b, Geometria(), geo, self.w, self.h)
        # Girada 90° horario: lo que estaba a la derecha queda abajo (en píxeles, el mismo largo).
        w2, h2 = tamano_resultante(self.w, self.h, geo)
        self.assertAlmostEqual(b2.dx * w2, 0.0, places=6)
        self.assertAlmostEqual(b2.dy * h2, 0.25 * self.w, places=6)
        base = aplicar_geometria(self.rgb, geo)
        salida = aplicar_borrados(base, (b2,))
        self.assertLess(float((rojez(salida) > 100).mean()), 0.001)


class PruebasHistorial(unittest.TestCase):
    def test_textos(self):
        from celular_natural.ui.historial import describir_cambio
        base = {"preset": PRESET_PRINCIPAL, "ajustes": PRESETS[PRESET_PRINCIPAL], "capas": [], "recorte": None,
                "montaje": (), "fondo": None}
        g = Geometria()
        casos = [
            ({"geometria": g.girada(1)}, "Girar 90° a la derecha"),
            ({"geometria": g.girada(-1)}, "Girar 90° a la izquierda"),
            ({"geometria": g.volteada(True)}, "Voltear horizontal"),
            ({"geometria": g.volteada(False)}, "Voltear vertical"),
            ({"geometria": Geometria(enderezar=2.5)}, "Enderezar: 0° → +2,5°"),
            ({"borrado": (ZonaBorrado(Zona("rect", 0, 0, 0.1, 0.1)),)}, "Objeto borrado (relleno automático)"),
            ({"borrado": (ZonaBorrado(Zona("rect", 0, 0, 0.1, 0.1), "clonar", 0.1),)}, "Objeto borrado (clonado)"),
        ]
        for cambio, texto in casos:
            with self.subTest(texto=texto):
                self.assertEqual(describir_cambio(base, {**base, **cambio}), texto)
        cielo = Zona.desde_mascara(np.eye(8, dtype=np.float32), "cielo")
        con = {**base, "capas": [("Noche urbana", 50, cielo)]}
        sin = {**base, "capas": [("Noche urbana", 50, None)]}
        self.assertEqual(describir_cambio(sin, con), "Capa 1: zona Cielo (automático)")
        retocada = {**base, "capas": [("Noche urbana", 50, replace(cielo, trazos=((((0.1, 0.1),), 0.1, 50, True),)))]}
        self.assertEqual(describir_cambio(con, retocada), "Capa 1: zona retocada con el pincel")
        contorno = Zona.desde_mascara(np.eye(8, dtype=np.float32), "contorno")
        self.assertEqual(describir_cambio(base, {**base, "fondo": (contorno, True)}),
                         "Fondo quitado (contorno ajustado)")

    def test_estados_viejos(self):
        from celular_natural.ui.historial import describir_cambio
        viejo = {"preset": PRESET_PRINCIPAL, "ajustes": PRESETS[PRESET_PRINCIPAL],
                 "capas": [("Noche urbana", 50)], "recorte": None, "fondo": (None, True)}
        nuevo = {**viejo, "capas": [("Noche urbana", 50, None)], "geometria": Geometria(), "borrado": (),
                 "montaje": ()}
        self.assertIsInstance(describir_cambio(viejo, nuevo), str)
        self.assertIsInstance(describir_cambio(nuevo, viejo), str)
        self.assertEqual(describir_cambio(viejo, {**nuevo, "geometria": Geometria(1)}), "Girar 90° a la derecha")
        self.assertEqual(describir_cambio({**viejo, "geometria": Geometria(1)}, viejo), "Girar 90° a la izquierda")


# ---------------------------------------------------------------------------
# Ventana real, sin pantalla
# ---------------------------------------------------------------------------

def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class PruebasVentana(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PIL import Image
        cls.app = _app()
        cls.carpeta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.ruta = Path(cls.carpeta.name) / "escena.png"
        Image.fromarray(escena(640, 480)).save(cls.ruta)
        # La misma escena torcida 3° en sentido horario (el horizonte baja hacia la derecha).
        cls.ruta_torcida = Path(cls.carpeta.name) / "torcida.png"
        Image.fromarray(aplicar_geometria(escena(760, 570), Geometria(enderezar=3.0))[45:525, 60:700]).save(
            cls.ruta_torcida)

    @classmethod
    def tearDownClass(cls):
        cls.carpeta.cleanup()

    def setUp(self):
        from celular_natural.ui.ventana import VentanaPrincipal
        self.v = VentanaPrincipal()
        self.v.resize(1366, 768)
        self.v.abrir_archivo(str(self.ruta))
        self.esperar()

    def tearDown(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        self.v.close()
        self.v.deleteLater()
        self.app.processEvents()
        # deleteLater() sin un bucle de eventos corriendo no borra nada: se completa el borrado acá.
        # Si no, cada ventana cerrada queda viva hasta el final de la suite (con sus miles de widgets).
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def quieto(self) -> bool:
        v = self.v
        return (v._imagen is not None and not v._fuentes_pendientes and v._deteccion is None
                and v._generacion_completa_mostrada == v._generacion and not v._exportando)

    def esperar(self, condicion=None, segundos=60.0):
        condicion = condicion or self.quieto
        fin = time.monotonic() + segundos
        while time.monotonic() < fin:
            self.app.processEvents()
            if condicion():
                for _ in range(5):
                    self.app.processEvents()
                if condicion():
                    return
            time.sleep(0.01)
        self.fail("la ventana no terminó de procesar")

    def test_girar_convierte_zonas_y_registra_un_paso(self):
        v = self.v
        v.panel_ajustes.agregar_capa("Noche urbana", 60, zona=Zona("rect", 0.31, 0.62, 0.39, 0.78, pluma=0))
        self.esperar()
        v._timer_historial.stop()
        v._registrar_historial()
        pasos = len(v._historial)
        v.girar(1)
        self.esperar()
        self.assertEqual(len(v._historial), pasos + 1)
        self.assertEqual(v._historial[-1][0], "Girar 90° a la derecha")
        self.assertEqual(v._fuente.shape[:2], (640, 480))
        zona = v.panel_ajustes.capas()[0].zona
        m = mascara_zona(zona, *v._base_completa.shape[:2]) > 0.5
        self.assertGreater(float(rojez(v._base_completa)[m].mean()), 150)
        v.deshacer()
        self.esperar()
        self.assertTrue(v._geometria.es_identidad())
        self.assertEqual(v.panel_ajustes.capas()[0].zona, Zona("rect", 0.31, 0.62, 0.39, 0.78, pluma=0))
        v.rehacer()
        self.esperar()
        self.assertEqual(v._geometria, Geometria().girada(1))

    def test_exportacion_identica_a_la_vista(self):
        from PIL import Image
        from PySide6.QtWidgets import QFileDialog
        from celular_natural.ui.ventana import con_desenfoque
        v = self.v
        v._cambiar_geometria(Geometria(1, False, False, 4.0))
        self.esperar()
        w, h = v._tam_base()
        mascara = np.zeros((h, w), np.float32)
        cv2.circle(mascara, (w // 2, h // 3), min(w, h) // 5, 1.0, -1)
        v.panel_ajustes.agregar_capa("Noche urbana", 70, zona=Zona.desde_mascara(mascara, "cielo"))
        rojo = convertir_zona(Zona("rect", 0.28, 0.58, 0.42, 0.82, pluma=10), Geometria(),
                              v._geometria, v._imagen.ancho, v._imagen.alto)
        v.panel_borrar.agregar(ZonaBorrado(rojo))
        self.esperar()
        v._recorte = Recorte(0.05, 0.05, 0.95, 0.9)
        v._recalcular_fuentes()
        self.esperar()
        self.assertLess(float((rojez(v._fuente) > 100).mean()), 0.001, "el borrado entra al filtro")
        vista = v._resultado_completo[1].copy()
        destino = Path(self.carpeta.name) / "exportada.png"
        original = QFileDialog.getSaveFileName
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(destino), "PNG (*.png)"))
        try:
            v.exportar()
            self.esperar(lambda: not v._exportando and destino.exists())
        finally:
            QFileDialog.getSaveFileName = original
        exportada = np.asarray(Image.open(destino).convert("RGB"))
        self.assertTrue(np.array_equal(exportada, vista), "la exportación tiene que ser idéntica a la vista")
        # Y es el orden documentado: geometría → borrado → recorte → filtro.
        base = aplicar_geometria(v._imagen.rgb, v._geometria)
        base = aplicar_borrados(base, v.panel_borrar.estado())
        fuente = np.ascontiguousarray(aplicar_recorte(base, v._recorte))
        esperado = procesar_pila(con_desenfoque(fuente, None, v._recorte), v.panel_ajustes.pila(),
                                 zonas=v.panel_ajustes.zonas(), recorte=v._recorte)
        self.assertTrue(np.array_equal(esperado, vista))

    def test_estado_viejo_del_historial(self):
        """Un paso guardado por una versión anterior (sin geometría ni borrados, fondo de
        dos elementos, capas sin zona) se sigue pudiendo abrir."""
        v = self.v
        v.girar(1)
        v.panel_borrar.agregar(ZonaBorrado(Zona("rect", 0.1, 0.1, 0.2, 0.2)))
        self.esperar()
        v._timer_historial.stop()
        v._registrar_historial()
        viejo = {"preset": PRESET_PRINCIPAL, "ajustes": PRESETS[PRESET_PRINCIPAL],
                 "capas": [("Noche urbana", 40)], "recorte": None, "fondo": (None, True)}
        v._historial.append(("Paso viejo", viejo))
        v.ir_al_historial(len(v._historial) - 1)
        self.esperar()
        self.assertTrue(v._geometria.es_identidad())
        self.assertEqual(v.panel_borrar.estado(), ())
        self.assertEqual(len(v.panel_ajustes.capas()), 1)
        self.assertEqual(v._fuente.shape[:2], (480, 640))
        estado = v._estado_completo()
        self.assertEqual(estado["geometria"], Geometria())
        self.assertEqual(estado["fondo"][0], None)

    def test_enderezar_y_nivelar(self):
        v = self.v
        v.boton_enderezar.setChecked(True)
        self.app.processEvents()
        self.assertTrue(v._modo_enderezar and v.barra_enderezar.isVisible() or not v.isVisible())
        v.slider_angulo.setValue(-25)  # -2,5°
        self.assertAlmostEqual(v.numero_angulo.value(), -2.5)
        v._salir_enderezar("cancelar")
        self.esperar()
        self.assertTrue(v._geometria.es_identidad())
        v.boton_enderezar.setChecked(True)
        v.slider_angulo.setValue(-25)
        v._confirmar_herramienta()  # Enter
        self.esperar()
        self.assertAlmostEqual(v._geometria.enderezar, -2.5)
        self.assertEqual(v._historial[-1][0], "Enderezar: 0° → -2,5°")
        self.assertEqual(v._fuente.shape[:2][::-1], tamano_resultante(640, 480, v._geometria))
        # Nivelar automático sobre una foto torcida 3°: propone enderezarla -3°.
        v.agregar_fotos([str(self.ruta_torcida)])
        self.esperar(lambda: self.quieto() and v._imagen.ruta.name == "torcida.png")
        v.boton_enderezar.setChecked(True)
        v.nivelar_automatico()
        self.assertAlmostEqual(v._angulo_enderezar(), -3.0, delta=0.3)
        v._salir_enderezar("aplicar")
        self.esperar()
        self.assertAlmostEqual(v._geometria.enderezar, -3.0, delta=0.3)

    def test_ajustar_al_contorno_desde_un_lazo(self):
        v = self.v
        # Lazo aproximado y holgado alrededor del cuadrado rojo (0.30..0.40 x 0.60..0.80).
        lazo = Zona.desde_puntos("poligono", [(0.26, 0.56), (0.44, 0.55), (0.45, 0.84), (0.25, 0.85)], pluma=3)
        v.panel_fondo.establecer_zona(lazo)
        self.esperar()
        v._timer_historial.stop()
        v._registrar_historial()
        v.ajustar_al_contorno()
        self.assertIsNotNone(v._deteccion)
        self.assertFalse(v.panel_fondo.boton_ajustar.isEnabled())  # "Ajustando…"
        self.esperar()
        zona = v.panel_fondo.zona
        self.assertTrue(zona.es_mascara and zona.origen == "contorno")
        m = mascara_zona(zona, 480, 640)
        rojo = rojez(v._base_completa) > 100
        self.assertGreater(float(m[rojo].mean()), 0.95)
        self.assertLess(float(m[~rojo].mean()), 0.01, "el contorno se pega al objeto, sin el pasto")
        v._timer_historial.stop()
        v._registrar_historial()
        self.assertEqual(v._historial[-1][0], "Objeto ajustado al contorno")
        # Corregir con el pincel encima: la máscara queda como base.
        v._pedir_zona(v.panel_fondo, "pincel")
        self.assertTrue(v.vista.pintando and v.vista._base_pincel is not None)
        v._trazos_terminados([(((0.1, 0.1), (0.2, 0.1)), 0.02, 100, False)])
        self.assertTrue(v.panel_fondo.zona.es_mascara and len(v.panel_fondo.zona.trazos) == 1)

    def test_cielo_automatico_y_cache(self):
        v = self.v
        v.panel_ajustes.agregar_capa("Noche urbana", 50)
        self.esperar()
        fila = v.panel_ajustes.capas()[0]
        fila.combo_zona.setCurrentIndex([f for _t, f in fila.FORMAS_ZONA].index("cielo"))
        self.assertIsNotNone(v._deteccion)
        self.esperar()
        zona = v.panel_ajustes.capas()[0].zona
        self.assertTrue(zona.es_mascara and zona.origen == "cielo")
        m = mascara_zona(zona, 480, 640)
        self.assertGreater(float(m[:200].mean()), 0.8)
        self.assertLess(float(m[260:].mean()), 0.05)
        # Segunda vez: sale de la caché, sin detectar de nuevo.
        v.panel_ajustes.capas()[0].combo_zona.setCurrentIndex(0)
        self.esperar()
        fila = v.panel_ajustes.capas()[0]
        fila.combo_zona.setCurrentIndex([f for _t, f in fila.FORMAS_ZONA].index("cielo"))
        self.assertIsNone(v._deteccion)
        self.assertEqual(v.panel_ajustes.capas()[0].zona.datos, zona.datos)


class PruebasVistaClonar(unittest.TestCase):
    def test_arrastrar_elige_el_desplazamiento(self):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QImage
        from PySide6.QtTest import QTest
        from celular_natural.ui.vista_comparacion import VistaComparacion
        _app()
        vista = VistaComparacion()
        vista.resize(820, 620)
        img = QImage(800, 600, QImage.Format_RGB888)
        img.fill(0x808080)
        vista.establecer_imagenes(img, None, (800, 600))
        cuadrado = ((0.4, 0.4), (0.5, 0.4), (0.5, 0.5), (0.4, 0.5))
        vista.establecer_herramienta("clonar", contornos=(cuadrado,))
        recibidos = []
        vista.clonCambiado.connect(lambda dx, dy: recibidos.append((dx, dy)))

        def punto(x, y):
            p = vista._origen + QPointF(x * 800, y * 600) * vista.zoom
            return QPoint(round(p.x()), round(p.y()))

        QTest.mousePress(vista, Qt.LeftButton, Qt.NoModifier, punto(0.45, 0.45))
        for k in range(1, 11):
            QTest.mouseMove(vista, punto(0.45 + 0.02 * k, 0.45))
        QTest.mouseRelease(vista, Qt.LeftButton, Qt.NoModifier, punto(0.65, 0.45))
        self.assertEqual(len(recibidos), 1)
        self.assertAlmostEqual(recibidos[0][0], 160, delta=3)  # 0,2 del ancho de 800 px
        self.assertAlmostEqual(recibidos[0][1], 0, delta=3)
        vista.grab()  # dibuja la vista previa sin errores
        # Agarrar la fuente ya elegida la corre (no empieza de cero).
        QTest.mousePress(vista, Qt.LeftButton, Qt.NoModifier, punto(0.65, 0.45))
        QTest.mouseMove(vista, punto(0.65, 0.55))
        QTest.mouseRelease(vista, Qt.LeftButton, Qt.NoModifier, punto(0.65, 0.55))
        self.assertAlmostEqual(recibidos[-1][0], 160, delta=3)
        self.assertAlmostEqual(recibidos[-1][1], 60, delta=3)
        vista.establecer_herramienta("enderezar")
        vista.grab()  # cuadrícula


if __name__ == "__main__":
    unittest.main()
