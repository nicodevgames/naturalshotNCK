"""Pruebas de las formas y los rellenos (``motor/formas.py``).

Áreas contra la fórmula, antialias (hay alfas intermedios en los bordes), centrado,
simetría de la estrella, trazo centrado en el borde, degradados, el contrato con M1
(``como_dict`` / ``desde_dict``) y la velocidad.
"""

from __future__ import annotations

import json
import math
import sys
import time
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from celular_natural.motor.formas import (  # noqa: E402
    ParamsForma, Relleno, renderizar_forma, renderizar_relleno)

ROJO = (255, 0, 0, 255)
AZUL = (0, 0, 255, 255)
NEGRO = (0, 0, 0, 255)
BLANCO = (255, 255, 255, 255)


def area(rgba: np.ndarray) -> float:
    """Área cubierta en píxeles (suma del alfa)."""
    return float(rgba[..., 3].astype(np.float64).sum() / 255.0)


def centroide(rgba: np.ndarray) -> tuple[float, float]:
    a = rgba[..., 3].astype(np.float64)
    ys, xs = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    return float((a * (xs + 0.5)).sum() / a.sum()), float((a * (ys + 0.5)).sum() / a.sum())


def intermedios(rgba: np.ndarray) -> int:
    a = rgba[..., 3]
    return int(((a > 0) & (a < 255)).sum())


class TestRelleno(unittest.TestCase):
    def test_valores_por_defecto(self):
        r = Relleno()
        self.assertEqual(r.tipo, "color")
        self.assertEqual(r.colores, ((255, 255, 255, 255),))
        self.assertEqual(r.paradas, ())
        self.assertEqual(r.angulo, 90.0)

    def test_ida_y_vuelta_json(self):
        r = Relleno("lineal", (ROJO, (0, 255, 0, 128), AZUL), (0.0, 0.3, 1.0), 45.0)
        d = json.loads(json.dumps(r.como_dict()))
        self.assertEqual(Relleno.desde_dict(d), r)
        self.assertEqual(hash(Relleno.desde_dict(d)), hash(r))

    def test_listas_se_vuelven_tuplas_y_rgb_suma_alfa(self):
        r = Relleno("color", [[10, 20, 30]])
        self.assertEqual(r.colores, ((10, 20, 30, 255),))
        hash(r)

    def test_desde_dict_ignora_desconocidos_y_completa(self):
        self.assertEqual(Relleno.desde_dict({"tipo": "radial", "otra_cosa": 1}), Relleno("radial"))

    def test_invalidos(self):
        for mal in (dict(tipo="raro"), dict(colores=()), dict(colores=((300, 0, 0, 255),)),
                    dict(colores=(ROJO, AZUL), paradas=(0.5,)),
                    dict(colores=(ROJO, AZUL), paradas=(0.8, 0.2)),
                    dict(colores=(ROJO, AZUL), paradas=(0.0, 1.5)), dict(angulo=float("nan")),
                    dict(colores=(("a", 0, 0, 0),))):
            with self.subTest(mal=mal), self.assertRaises(ValueError):
                Relleno(**mal)
        with self.assertRaises(ValueError):
            Relleno.desde_dict("no es un dict")


class TestParamsForma(unittest.TestCase):
    def test_valores_por_defecto(self):
        p = ParamsForma()
        self.assertEqual((p.tipo, p.ancho, p.alto, p.radio, p.lados, p.puntas, p.radio_interno),
                         ("rectangulo", 400.0, 300.0, 0.0, 6, 5, 0.45))
        self.assertEqual(p.relleno, Relleno())
        self.assertEqual((p.trazo, p.grosor), ((0, 0, 0, 255), 0.0))

    def test_ida_y_vuelta_json(self):
        p = ParamsForma("estrella", 300, 280, 0, 6, 7, 0.5,
                        Relleno("radial", (ROJO, AZUL)), (1, 2, 3, 200), 4.5)
        d = json.loads(json.dumps(p.como_dict()))
        q = ParamsForma.desde_dict(d)
        self.assertEqual(q, p)
        self.assertIsInstance(q.relleno, Relleno)
        self.assertEqual({p: 1}[q], 1)       # se puede usar de clave de caché

    def test_invalidos(self):
        for mal in (dict(tipo="hexagono"), dict(ancho=0), dict(alto=-1), dict(radio=-1),
                    dict(lados=2), dict(puntas=2), dict(radio_interno=0), dict(radio_interno=1.5),
                    dict(grosor=-1), dict(relleno="rojo"), dict(trazo=(0, 0)), dict(lados=4.5)):
            with self.subTest(mal=mal), self.assertRaises(ValueError):
                ParamsForma(**mal)


class TestFormas(unittest.TestCase):
    def test_rectangulo_exacto(self):
        im = renderizar_forma(ParamsForma("rectangulo", 400, 300, relleno=Relleno("color", (ROJO,))))
        self.assertEqual(im.dtype, np.uint8)
        self.assertEqual(im.shape, (300, 400, 4))
        self.assertTrue((im[..., 3] == 255).all())
        self.assertTrue((im[..., :3] == (255, 0, 0)).all())

    def test_rectangulo_impar_tiene_medio_pixel_en_los_bordes(self):
        im = renderizar_forma(ParamsForma("rectangulo", 101, 51))
        self.assertEqual(im.shape[:2], (52, 102))
        self.assertAlmostEqual(area(im), 101 * 51, delta=101 * 51 * 0.002)
        self.assertGreater(intermedios(im), 0)
        self.assertTrue(np.all(np.abs(im[26, [0, -1], 3].astype(int) - 128) <= 2))

    def test_elipse_area_antialias_y_centro(self):
        im = renderizar_forma(ParamsForma("elipse", 400, 300))
        self.assertEqual(im.shape[:2], (300, 400))
        self.assertAlmostEqual(area(im), math.pi * 200 * 150, delta=math.pi * 200 * 150 * 0.003)
        self.assertGreater(intermedios(im), 500)
        cx, cy = centroide(im)
        self.assertAlmostEqual(cx, 200, delta=0.05)
        self.assertAlmostEqual(cy, 150, delta=0.05)
        # simétrica en los dos ejes
        a = im[..., 3].astype(int)
        self.assertLessEqual(np.abs(a - a[:, ::-1]).max(), 20)
        self.assertLessEqual(np.abs(a - a[::-1, :]).max(), 20)

    def test_rectangulo_redondeado(self):
        im = renderizar_forma(ParamsForma("rectangulo", 400, 300, radio=60))
        esperado = 400 * 300 - (4 - math.pi) * 60 ** 2
        self.assertAlmostEqual(area(im), esperado, delta=esperado * 0.003)
        self.assertEqual(im[0, 0, 3], 0)
        self.assertEqual(im[150, 0, 3], 255)
        # el radio se limita a la mitad del lado corto
        im2 = renderizar_forma(ParamsForma("rectangulo", 200, 100, radio=999))
        esperado = 100 * 100 + math.pi * 50 ** 2
        self.assertAlmostEqual(area(im2), esperado, delta=esperado * 0.004)

    def test_poligono_regular(self):
        for lados in (3, 5, 6, 8):
            with self.subTest(lados=lados):
                im = renderizar_forma(ParamsForma("poligono", 400, 400, lados=lados))
                esperado = lados / 2 * 200 ** 2 * math.sin(2 * math.pi / lados)
                self.assertAlmostEqual(area(im), esperado, delta=esperado * 0.004)
                a = im[..., 3].astype(int)
                self.assertLessEqual(np.abs(a - a[:, ::-1]).max(), 20)   # vértice arriba: simétrico

    def test_estrella_simetrica_y_area(self):
        p = ParamsForma("estrella", 400, 400, puntas=5, radio_interno=0.45)
        im = renderizar_forma(p)
        esperado = 5 * 200 * 90 * math.sin(math.pi / 5)
        self.assertAlmostEqual(area(im), esperado, delta=esperado * 0.004)
        a = im[..., 3].astype(int)
        self.assertLessEqual(np.abs(a - a[:, ::-1]).max(), 20)
        self.assertLess(np.abs(a - a[:, ::-1]).mean(), 0.2)
        self.assertGreater(a[2, a.shape[1] // 2], 0)      # punta arriba
        self.assertEqual(a[a.shape[0] // 2, 2], 0)        # sin punta en el medio a la izquierda

    def test_linea_es_una_barra(self):
        im = renderizar_forma(ParamsForma("linea", 300, 10))
        self.assertEqual(im.shape[:2], (10, 300))
        self.assertAlmostEqual(area(im), 3000, delta=3)

    def test_flecha_apunta_a_la_derecha(self):
        im = renderizar_forma(ParamsForma("flecha", 400, 100))
        a = im[..., 3]
        alto_cuerpo = (a[:, 40] > 127).sum()
        alto_cabeza = (a[:, 330] > 127).sum()
        self.assertGreater(alto_cabeza, alto_cuerpo * 1.5)
        self.assertGreater(a[50, 398], 0)       # la punta llega a la derecha
        self.assertEqual(a[2, 398], 0)
        self.assertGreater(a[50, 1], 0)         # el cuerpo arranca a la izquierda
        self.assertEqual(a[2, 1], 0)

    def test_trazo_centrado_en_el_borde(self):
        p = ParamsForma("rectangulo", 200, 200, relleno=Relleno("ninguno"), trazo=AZUL, grosor=20)
        im = renderizar_forma(p)
        self.assertEqual(im.shape[:2], (220, 220))
        self.assertAlmostEqual(area(im), 220 ** 2 - 180 ** 2, delta=40)
        self.assertEqual(im[110, 110, 3], 0)
        self.assertEqual(tuple(im[110, 5]), AZUL)
        self.assertEqual(tuple(im[0, 0]), AZUL)       # esquina en inglete (no redondeada)

    def test_trazo_sobre_relleno(self):
        p = ParamsForma("elipse", 300, 200, relleno=Relleno("color", (ROJO,)), trazo=AZUL, grosor=10)
        im = renderizar_forma(p)
        self.assertEqual(im.shape[:2], (210, 310))
        self.assertEqual(tuple(im[105, 155]), ROJO)
        self.assertEqual(tuple(im[105, 5]), AZUL)
        self.assertGreater(intermedios(im), 300)
        # la cobertura total es la de la elipse agrandada en la mitad del grosor
        esperado = math.pi * 155 * 105
        self.assertAlmostEqual(area(im), esperado, delta=esperado * 0.004)

    def test_trazo_de_estrella_y_flecha(self):
        for tipo in ("estrella", "flecha", "poligono", "linea"):
            with self.subTest(tipo=tipo):
                p = ParamsForma(tipo, 300, 300 if tipo != "linea" else 20,
                                relleno=Relleno("color", (ROJO,)), trazo=AZUL, grosor=8)
                im = renderizar_forma(p)
                sin = renderizar_forma(ParamsForma(tipo, 300, 300 if tipo != "linea" else 20))
                self.assertGreater(area(im), area(sin))
                azul = (im[..., 2] > 200) & (im[..., 0] < 50) & (im[..., 3] > 200)
                self.assertGreater(int(azul.sum()), 500)

    def test_trazo_muy_grueso_no_rompe(self):
        for tipo in ("rectangulo", "elipse", "estrella", "flecha", "poligono"):
            with self.subTest(tipo=tipo):
                p = ParamsForma(tipo, 120, 60, relleno=Relleno("ninguno"), trazo=AZUL, grosor=100)
                im = renderizar_forma(p)
                a = im[..., 3]
                h, w = a.shape
                self.assertEqual(a[h // 2, w // 2], 255)      # el trazo tapa el medio
                self.assertGreater(area(im), 120 * 60)

    def test_escala(self):
        p = ParamsForma("elipse", 200, 100, trazo=NEGRO, grosor=4)
        a1 = area(renderizar_forma(p, 1.0))
        im2 = renderizar_forma(p, 2.0)
        self.assertEqual(im2.shape[:2], (208, 408))
        self.assertAlmostEqual(area(im2), 4 * a1, delta=4 * a1 * 0.003)
        with self.assertRaises(ValueError):
            renderizar_forma(p, 0)

    def test_sin_relleno_ni_trazo_es_transparente(self):
        im = renderizar_forma(ParamsForma(relleno=Relleno("ninguno")))
        self.assertEqual(int(im[..., 3].max()), 0)

    def test_relleno_degradado_en_la_forma(self):
        p = ParamsForma("rectangulo", 200, 100, relleno=Relleno("lineal", (NEGRO, BLANCO), angulo=0))
        im = renderizar_forma(p)
        self.assertLessEqual(int(im[50, 0, 0]), 2)
        self.assertGreaterEqual(int(im[50, -1, 0]), 253)
        self.assertTrue((np.diff(im[50, :, 0].astype(int)) >= 0).all())
        self.assertTrue((im[..., 3] == 255).all())

    def test_color_con_alfa(self):
        im = renderizar_forma(ParamsForma("rectangulo", 50, 50, relleno=Relleno("color", ((0, 255, 0, 100),))))
        self.assertTrue((im[..., 3] == 100).all())


class TestRellenoLienzo(unittest.TestCase):
    def test_tipos(self):
        self.assertEqual(int(renderizar_relleno(Relleno("ninguno"), 10, 5)[..., 3].max()), 0)
        im = renderizar_relleno(Relleno("color", ((1, 2, 3, 4),)), 10, 5)
        self.assertEqual(im.shape, (5, 10, 4))
        self.assertTrue((im == (1, 2, 3, 4)).all())

    def test_lineal_90_va_de_arriba_hacia_abajo(self):
        im = renderizar_relleno(Relleno("lineal", (NEGRO, BLANCO)), 30, 256)
        col = im[:, 7, 0].astype(int)
        self.assertLessEqual(col[0], 1)
        self.assertGreaterEqual(col[-1], 254)
        self.assertTrue((np.diff(col) >= 0).all())
        self.assertTrue((im[:, 0] == im[:, -1]).all())         # parejo en horizontal

    def test_lineal_angulo_cero_y_180(self):
        a = renderizar_relleno(Relleno("lineal", (NEGRO, BLANCO), angulo=0), 256, 4)
        b = renderizar_relleno(Relleno("lineal", (NEGRO, BLANCO), angulo=180), 256, 4)
        self.assertLessEqual(int(a[0, 0, 0]), 1)
        self.assertGreaterEqual(int(a[0, -1, 0]), 254)
        self.assertTrue(np.array_equal(a[:, ::-1], b))

    def test_lineal_45_cubre_las_esquinas(self):
        im = renderizar_relleno(Relleno("lineal", (NEGRO, BLANCO), angulo=45), 200, 100)
        self.assertLessEqual(int(im[0, 0, 0]), 3)
        self.assertGreaterEqual(int(im[-1, -1, 0]), 252)

    def test_radial(self):
        im = renderizar_relleno(Relleno("radial", (BLANCO, NEGRO)), 201, 101)
        self.assertGreaterEqual(int(im[50, 100, 0]), 254)
        self.assertLessEqual(int(im[0, 0, 0]), 3)
        self.assertLessEqual(int(im[-1, -1, 0]), 3)

    def test_paradas(self):
        r = Relleno("lineal", (NEGRO, ROJO, BLANCO), (0.0, 0.25, 1.0), angulo=0)
        im = renderizar_relleno(r, 401, 2)
        self.assertEqual(tuple(im[0, 100]), ROJO)          # x = 100,5 ≈ 0,25
        self.assertLessEqual(int(im[0, 0, 0]), 2)          # x = 0,5: casi negro
        self.assertEqual(tuple(im[0, 0, 1:]), (0, 0, 255))

    def test_degradado_con_transparente_no_se_ensucia(self):
        r = Relleno("lineal", ((255, 0, 0, 255), (0, 0, 255, 0)), angulo=0)
        im = renderizar_relleno(r, 101, 1)
        medio = im[0, 50]
        self.assertGreater(int(medio[0]), 250)          # sigue rojo (no se mezcla con el azul transparente)
        self.assertAlmostEqual(int(medio[3]), 127, delta=3)

    def test_invalidos(self):
        with self.assertRaises(ValueError):
            renderizar_relleno(Relleno(), 0, 10)
        with self.assertRaises(ValueError):
            renderizar_relleno("color", 10, 10)


class TestVelocidad(unittest.TestCase):
    def test_forma_de_1000(self):
        p = ParamsForma("estrella", 1000, 1000, relleno=Relleno("radial", (ROJO, AZUL)),
                        trazo=NEGRO, grosor=12)
        renderizar_forma(p)
        tiempos = []
        for _ in range(5):
            t = time.perf_counter()
            renderizar_forma(p)
            tiempos.append(time.perf_counter() - t)
        ms = sorted(tiempos)[2] * 1000
        print(f"\n  forma 1000×1000 con degradado y trazo: {ms:.1f} ms")
        self.assertLess(ms, 60)        # objetivo 30 ms (margen para máquinas lentas)


if __name__ == "__main__":
    unittest.main()
