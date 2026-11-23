"""Pruebas de la pintura (``motor/pintura.py``): pincel (centro opaco, borde según la
dureza, opacidad sin acumular dentro del trazo), borrador, bote (contiguo, global,
tolerancia y muestra de la composición), degradado (extremos exactos), cuentagotas y velocidad.
"""

from __future__ import annotations

import math
import sys
import time
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from celular_natural.motor.formas import Relleno  # noqa: E402
from celular_natural.motor.pintura import bote, cuentagotas, degradado, trazo  # noqa: E402

ROJO = (255, 0, 0, 255)
AZUL = (0, 0, 255, 255)
NEGRO = (0, 0, 0, 255)
BLANCO = (255, 255, 255, 255)


def vacia(w=64, h=64) -> np.ndarray:
    return np.zeros((h, w, 4), np.uint8)


def llena(color, w=64, h=64) -> np.ndarray:
    im = np.empty((h, w, 4), np.uint8)
    im[:] = color
    return im


class TestTrazo(unittest.TestCase):
    def test_copia_nueva(self):
        im = vacia()
        r = trazo(im, [(32, 32)], 20, color=ROJO)
        self.assertIsNot(r, im)
        self.assertEqual(int(im.max()), 0)
        self.assertEqual(r.shape, im.shape)
        self.assertEqual(r.dtype, np.uint8)

    def test_punto_duro(self):
        r = trazo(vacia(), [(32, 32)], 20, dureza=1.0, color=ROJO)
        self.assertEqual(tuple(r[31, 31]), ROJO)
        self.assertEqual(tuple(r[32, 32]), ROJO)
        a = r[..., 3]
        self.assertEqual(int(a[32, 32 + 11]), 0)
        self.assertEqual(int(a[32, 32 + 8]), 255)
        # antialias: borde de 1 px (hay intermedios, pocos)
        inter = int(((a > 0) & (a < 255)).sum())
        self.assertGreater(inter, 20)
        self.assertLess(inter, 2 * math.pi * 10 * 2)
        area = a.astype(float).sum() / 255
        self.assertAlmostEqual(area, math.pi * 100, delta=math.pi * 100 * 0.03)

    def test_dureza_cero_es_suave(self):
        r = trazo(vacia(), [(32, 32)], 40, dureza=0.0, color=NEGRO)
        a = r[..., 3].astype(int)
        self.assertGreaterEqual(a[31, 31], 250)
        self.assertTrue(60 <= a[31, 31 + 10] <= 220, a[31, 31 + 10])       # a medio radio, a mitad de camino
        self.assertLessEqual(a[31, 31 + 19], 10)
        perfil = a[31, 31:31 + 21]
        self.assertTrue((np.diff(perfil) <= 0).all())

    def test_dureza_cambia_el_borde(self):
        anchos = []
        for d in (1.0, 0.5, 0.0):
            a = trazo(vacia(), [(32, 32)], 40, dureza=d)[..., 3]
            anchos.append(int(((a > 0) & (a < 255)).sum()))
        self.assertLess(anchos[0], anchos[1])
        self.assertLess(anchos[1], anchos[2])

    def test_opacidad_no_se_acumula_dentro_del_trazo(self):
        ida_y_vuelta = [(10, 32), (54, 32), (10, 32), (54, 32)]
        r = trazo(vacia(), ida_y_vuelta, 10, dureza=1.0, opacidad=0.5, color=ROJO)
        self.assertAlmostEqual(int(r[32, 32, 3]), 128, delta=1)
        self.assertEqual(tuple(r[32, 32, :3]), (255, 0, 0))
        # dos trazos sí se acumulan
        r2 = trazo(r, ida_y_vuelta, 10, dureza=1.0, opacidad=0.5, color=ROJO)
        self.assertAlmostEqual(int(r2[32, 32, 3]), 191, delta=2)

    def test_interpola_entre_puntos(self):
        r = trazo(vacia(128, 64), [(10, 32), (110, 32)], 6, dureza=1.0, color=AZUL)
        self.assertTrue((r[31:33, 12:108, 3] == 255).all())
        self.assertEqual(int(r[10, 60, 3]), 0)

    def test_sobre_opaco_mezcla(self):
        r = trazo(llena(BLANCO), [(32, 32)], 20, dureza=1.0, opacidad=0.5, color=NEGRO)
        px = r[32, 32]
        self.assertEqual(int(px[3]), 255)
        self.assertAlmostEqual(int(px[0]), 128, delta=1)
        self.assertEqual(tuple(r[0, 0]), BLANCO)

    def test_color_con_alfa(self):
        r = trazo(vacia(), [(32, 32)], 20, dureza=1.0, color=(0, 255, 0, 100))
        self.assertAlmostEqual(int(r[32, 32, 3]), 100, delta=1)

    def test_borrar(self):
        im = llena(ROJO)
        r = trazo(im, [(32, 32)], 20, dureza=1.0, borrar=True)
        self.assertEqual(int(r[32, 32, 3]), 0)
        self.assertEqual(tuple(r[0, 0]), ROJO)
        r2 = trazo(im, [(32, 32)], 20, dureza=1.0, opacidad=0.25, borrar=True)
        self.assertAlmostEqual(int(r2[32, 32, 3]), 191, delta=1)
        self.assertEqual(tuple(r2[32, 32, :3]), (255, 0, 0))

    def test_fuera_de_la_imagen_y_sin_puntos(self):
        im = llena(ROJO)
        self.assertTrue(np.array_equal(trazo(im, [], 10), im))
        self.assertTrue(np.array_equal(trazo(im, [(-100, -100)], 10, borrar=True), im))
        r = trazo(vacia(), [(-3, 32), (70, 32)], 10, dureza=1.0)
        self.assertEqual(int(r[32, 0, 3]), 255)
        self.assertEqual(int(r[32, 63, 3]), 255)

    def test_invalidos(self):
        with self.assertRaises(ValueError):
            trazo(np.zeros((10, 10, 3), np.uint8), [(1, 1)], 5)
        with self.assertRaises(ValueError):
            trazo(vacia(), [(1, 1)], 0)
        with self.assertRaises(ValueError):
            trazo(vacia(), [(1, float("nan"))], 5)


class TestBote(unittest.TestCase):
    def dos_zonas(self):
        im = llena(BLANCO)
        im[:, 30:34] = NEGRO
        return im

    def test_contiguo(self):
        im = self.dos_zonas()
        r = bote(im, 5, 5, ROJO)
        self.assertEqual(tuple(r[60, 0]), ROJO)
        self.assertEqual(tuple(r[0, 29]), ROJO)
        self.assertEqual(tuple(r[5, 31]), NEGRO)
        self.assertEqual(tuple(r[5, 50]), BLANCO)
        self.assertEqual(tuple(im[5, 5]), BLANCO)     # no toca la entrada

    def test_global(self):
        r = bote(self.dos_zonas(), 5, 5, ROJO, contiguo=False)
        self.assertEqual(tuple(r[5, 50]), ROJO)
        self.assertEqual(tuple(r[5, 31]), NEGRO)

    def test_tolerancia(self):
        im = llena(BLANCO)
        im[:, 32:] = (230, 230, 230, 255)
        self.assertEqual(tuple(bote(im, 1, 1, ROJO, tolerancia=10)[5, 50]), (230, 230, 230, 255))
        self.assertEqual(tuple(bote(im, 1, 1, ROJO, tolerancia=30)[5, 50]), ROJO)
        self.assertEqual(tuple(bote(im, 1, 1, ROJO, tolerancia=0)[5, 5]), ROJO)

    def test_capa_transparente(self):
        im = vacia()
        im[20:40, 20:40] = AZUL
        r = bote(im, 2, 2, ROJO)
        self.assertEqual(tuple(r[0, 0]), ROJO)
        self.assertEqual(tuple(r[30, 30]), AZUL)

    def test_muestra_de_la_composicion(self):
        capa = vacia()
        muestra = np.full((64, 64, 3), 255, np.uint8)
        muestra[:, 30:34] = 0
        r = bote(capa, 5, 5, ROJO, muestra=muestra)
        self.assertEqual(tuple(r[5, 5]), ROJO)
        self.assertEqual(int(r[5, 31, 3]), 0)
        self.assertEqual(int(r[5, 50, 3]), 0)
        with self.assertRaises(ValueError):
            bote(capa, 5, 5, ROJO, muestra=np.zeros((10, 10, 3), np.uint8))

    def test_color_semitransparente_se_mezcla(self):
        r = bote(llena(BLANCO), 1, 1, (0, 0, 0, 128))
        self.assertEqual(int(r[3, 3, 3]), 255)
        self.assertAlmostEqual(int(r[3, 3, 0]), 127, delta=1)

    def test_fuera(self):
        im = llena(BLANCO)
        self.assertTrue(np.array_equal(bote(im, -1, 5, ROJO), im))
        self.assertTrue(np.array_equal(bote(im, 5, 64, ROJO), im))


class TestDegradado(unittest.TestCase):
    def test_lineal_extremos_exactos(self):
        r = Relleno("lineal", ((10, 20, 30, 255), (200, 100, 50, 255)))
        im = degradado(100, 10, (20.5, 5.5), (80.5, 5.5), r)
        self.assertEqual(im.shape, (10, 100, 4))
        self.assertEqual(im.dtype, np.uint8)
        self.assertTrue((im[:, :21] == (10, 20, 30, 255)).all())
        self.assertTrue((im[:, 80:] == (200, 100, 50, 255)).all())
        medio = im[5, 50]
        self.assertTrue(np.all(np.abs(medio.astype(int) - (105, 60, 40, 255)) <= 1))
        self.assertTrue((np.diff(im[5, :, 0].astype(int)) >= 0).all())

    def test_lineal_vertical_y_diagonal(self):
        r = Relleno("lineal", (NEGRO, BLANCO))
        im = degradado(50, 100, (25, 0), (25, 100), r)
        self.assertTrue((im[:, 0] == im[:, -1]).all())
        self.assertLess(int(im[0, 0, 0]), 3)
        self.assertGreater(int(im[-1, 0, 0]), 252)
        im2 = degradado(100, 100, (0, 0), (100, 100), r)
        self.assertAlmostEqual(int(im2[49, 50, 0]), 128, delta=2)

    def test_radial(self):
        r = Relleno("radial", (BLANCO, NEGRO))
        im = degradado(101, 101, (50.5, 50.5), (90.5, 50.5), r, radial=True)
        self.assertEqual(tuple(im[50, 50]), BLANCO)
        self.assertEqual(tuple(im[0, 0]), NEGRO)
        self.assertEqual(tuple(im[50, 90]), NEGRO)
        self.assertAlmostEqual(int(im[50, 70, 0]), 128, delta=2)
        self.assertEqual(int(im[30, 50, 0]), int(im[50, 30, 0]))

    def test_paradas_y_puntos_iguales(self):
        r = Relleno("lineal", (NEGRO, ROJO, BLANCO), (0.0, 0.5, 1.0))
        im = degradado(101, 1, (0.5, 0.5), (100.5, 0.5), r)
        self.assertEqual(tuple(im[0, 50]), ROJO)
        igual = degradado(10, 10, (5, 5), (5, 5), r)
        self.assertTrue((igual == BLANCO).all())


class TestCuentagotas(unittest.TestCase):
    def test_pixel_y_promedio(self):
        im = np.zeros((10, 10, 3), np.uint8)
        im[5, 5] = (90, 180, 45)
        self.assertEqual(cuentagotas(im, 5.7, 5.2), (90, 180, 45))
        self.assertEqual(cuentagotas(im, 5, 5, radio=1), (10, 20, 5))
        self.assertEqual(cuentagotas(im, 0, 0), (0, 0, 0))

    def test_bordes_y_rgba(self):
        im = np.zeros((10, 10, 4), np.uint8)
        im[..., 0] = 200
        self.assertEqual(cuentagotas(im, -5, 50), (200, 0, 0))
        self.assertEqual(cuentagotas(im, 0, 0, radio=3), (200, 0, 0))
        self.assertIsInstance(cuentagotas(im, 1, 1)[0], int)


class TestVelocidad(unittest.TestCase):
    def test_trazo_de_200_puntos(self):
        im = np.zeros((2000, 2000, 4), np.uint8)
        t = np.linspace(0, 1, 200)
        puntos = np.stack([200 + 1600 * t, 1000 + 700 * np.sin(t * 9)], 1)
        trazo(im, puntos, 50, dureza=0.6, opacidad=0.8, color=ROJO)
        tiempos = []
        for _ in range(5):
            t0 = time.perf_counter()
            trazo(im, puntos, 50, dureza=0.6, opacidad=0.8, color=ROJO)
            tiempos.append(time.perf_counter() - t0)
        ms = sorted(tiempos)[2] * 1000
        print(f"\n  trazo de 200 puntos, pincel de 50 px en 2000×2000: {ms:.1f} ms")
        self.assertLess(ms, 160)       # objetivo 80 ms (margen para máquinas lentas)


if __name__ == "__main__":
    unittest.main()
