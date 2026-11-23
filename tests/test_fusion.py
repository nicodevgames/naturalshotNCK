"""Pruebas de los modos de fusión (``motor/fusion.py``).

Cada modo se compara contra valores calculados a mano en píxeles sueltos (con las
fórmulas de W3C Compositing and Blending Level 1) y contra una implementación de
referencia escrita píxel por píxel, en Python puro, directamente de la especificación.
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from celular_natural.motor.fusion import MODOS_FUSION, fusionar  # noqa: E402


def px(modo: str, cb, cs, opacidad: float = 1.0) -> tuple:
    """Un píxel: fondo ``cb`` opaco, capa ``cs`` opaca. Devuelve el RGB como tupla de floats."""
    fondo = np.array(cb, np.float32).reshape(1, 1, 3)
    capa = np.array(cs, np.float32).reshape(1, 1, 3)
    uno = np.ones((1, 1), np.float32)
    rgb, alfa = fusionar(fondo, uno, capa, uno, modo, opacidad)
    return tuple(float(v) for v in rgb[0, 0])


def gris(v: float) -> tuple:
    return (v, v, v)


# ---------------------------------------------------------------------------
# Referencia escalar, línea por línea de la especificación W3C
# ---------------------------------------------------------------------------

def _ref_separable(modo: str, cb: float, cs: float) -> float:
    if modo == "normal":
        return cs
    if modo == "multiplicar":
        return cb * cs
    if modo == "pantalla":
        return cb + cs - cb * cs
    if modo == "luz_fuerte":
        return _ref_separable("multiplicar", cb, 2 * cs) if cs <= 0.5 else _ref_separable("pantalla", cb, 2 * cs - 1)
    if modo == "superponer":
        return _ref_separable("luz_fuerte", cs, cb)
    if modo == "oscurecer":
        return min(cb, cs)
    if modo == "aclarar":
        return max(cb, cs)
    if modo == "sobreexponer":
        if cb == 0:
            return 0.0
        if cs == 1:
            return 1.0
        return min(1.0, cb / (1 - cs))
    if modo == "subexponer":
        if cb == 1:
            return 1.0
        if cs == 0:
            return 0.0
        return 1 - min(1.0, (1 - cb) / cs)
    if modo == "luz_suave":
        if cs <= 0.5:
            return cb - (1 - 2 * cs) * cb * (1 - cb)
        d = ((16 * cb - 12) * cb + 4) * cb if cb <= 0.25 else math.sqrt(cb)
        return cb + (2 * cs - 1) * (d - cb)
    if modo == "diferencia":
        return abs(cb - cs)
    if modo == "exclusion":
        return cb + cs - 2 * cb * cs
    raise KeyError(modo)


def _lum(c):
    return 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]


def _clip_color(c):
    l = _lum(c)
    n, x = min(c), max(c)
    if n < 0:
        c = [l + (v - l) * l / (l - n) for v in c]
    if x > 1:
        c = [l + (v - l) * (1 - l) / (x - l) for v in c]
    return c


def _set_lum(c, l):
    d = l - _lum(c)
    return _clip_color([v + d for v in c])


def _sat(c):
    return max(c) - min(c)


def _set_sat(c, s):
    c = list(c)
    orden = sorted(range(3), key=lambda i: c[i])
    i_min, i_mid, i_max = orden
    if c[i_max] > c[i_min]:
        c[i_mid] = (c[i_mid] - c[i_min]) * s / (c[i_max] - c[i_min])
        c[i_max] = s
    else:
        c[i_mid] = c[i_max] = 0.0
    c[i_min] = 0.0
    return c


def _ref_mezcla(modo, cb, cs):
    if modo == "tono":
        return _set_lum(_set_sat(cs, _sat(cb)), _lum(cb))
    if modo == "saturacion":
        return _set_lum(_set_sat(cb, _sat(cs)), _lum(cb))
    if modo == "color":
        return _set_lum(cs, _lum(cb))
    if modo == "luminosidad":
        return _set_lum(cb, _lum(cs))
    return [_ref_separable(modo, b, s) for b, s in zip(cb, cs)]


def _ref_fusionar(modo, cb, ab, cs, as_):
    """Source-over con mezcla (W3C §5.8 y §10): devuelve (rgb sin premultiplicar, alfa)."""
    b = _ref_mezcla(modo, cb, cs)
    cs2 = [(1 - ab) * s + ab * m for s, m in zip(cs, b)]
    co = [as_ * s + ab * c * (1 - as_) for s, c in zip(cs2, cb)]
    ao = as_ + ab * (1 - as_)
    return ([v / ao for v in co] if ao > 0 else [0.0, 0.0, 0.0]), ao


# ---------------------------------------------------------------------------

class TestModos(unittest.TestCase):

    def test_lista_de_modos(self):
        self.assertEqual(list(MODOS_FUSION), [
            "normal", "multiplicar", "pantalla", "superponer", "luz_suave", "luz_fuerte", "oscurecer", "aclarar",
            "sobreexponer", "subexponer", "diferencia", "exclusion", "tono", "saturacion", "color", "luminosidad"])
        self.assertEqual(MODOS_FUSION["normal"], "Normal")
        self.assertEqual(MODOS_FUSION["multiplicar"], "Multiplicar")
        self.assertEqual(MODOS_FUSION["pantalla"], "Trama")
        for nombre in MODOS_FUSION.values():
            self.assertTrue(nombre and nombre[0].isupper())

    def test_modo_desconocido(self):
        with self.assertRaises(ValueError):
            px("disolver", gris(0.5), gris(0.5))

    def test_normal(self):
        self.assertEqual(px("normal", (0.1, 0.2, 0.3), (0.7, 0.8, 0.9)), px("normal", gris(0), (0.7, 0.8, 0.9)))
        np.testing.assert_allclose(px("normal", (0.1, 0.2, 0.3), (0.7, 0.8, 0.9)), (0.7, 0.8, 0.9), atol=1e-6)

    def test_multiplicar(self):
        np.testing.assert_allclose(px("multiplicar", gris(0.5), gris(0.5)), gris(0.25), atol=1e-6)
        np.testing.assert_allclose(px("multiplicar", (1, 0.5, 0), (0.4, 0.4, 0.4)), (0.4, 0.2, 0), atol=1e-6)

    def test_pantalla(self):
        # 1 - (1 - a)(1 - b)
        np.testing.assert_allclose(px("pantalla", gris(0.2), gris(0.6)), gris(1 - 0.8 * 0.4), atol=1e-6)

    def test_superponer_a_los_dos_lados_de_medio(self):
        # Fondo oscuro (<= 0,5): multiplicar(capa, 2·fondo); claro: pantalla(capa, 2·fondo - 1).
        np.testing.assert_allclose(px("superponer", gris(0.25), gris(0.6)), gris(0.3), atol=1e-6)
        np.testing.assert_allclose(px("superponer", gris(0.75), gris(0.6)), gris(0.8), atol=1e-6)
        np.testing.assert_allclose(px("superponer", gris(0.5), gris(0.6)), gris(0.6), atol=1e-6)

    def test_luz_fuerte(self):
        np.testing.assert_allclose(px("luz_fuerte", gris(0.6), gris(0.25)), gris(0.3), atol=1e-6)
        np.testing.assert_allclose(px("luz_fuerte", gris(0.6), gris(0.75)), gris(0.8), atol=1e-6)

    def test_luz_suave(self):
        np.testing.assert_allclose(px("luz_suave", gris(0.5), gris(0.25)), gris(0.375), atol=1e-6)
        # Fondo <= 0,25: D(cb) = ((16·cb - 12)·cb + 4)·cb; si no, raíz.
        np.testing.assert_allclose(px("luz_suave", gris(0.16), gris(0.75)), gris(0.279168), atol=1e-6)
        np.testing.assert_allclose(px("luz_suave", gris(0.64), gris(0.75)), gris(0.72), atol=1e-6)

    def test_oscurecer_y_aclarar(self):
        np.testing.assert_allclose(px("oscurecer", (0.2, 0.8, 0.5), (0.6, 0.3, 0.5)), (0.2, 0.3, 0.5), atol=1e-6)
        np.testing.assert_allclose(px("aclarar", (0.2, 0.8, 0.5), (0.6, 0.3, 0.5)), (0.6, 0.8, 0.5), atol=1e-6)

    def test_sobreexponer(self):
        np.testing.assert_allclose(px("sobreexponer", (0.3, 0.6, 0.0), gris(0.5)), (0.6, 1.0, 0.0), atol=1e-6)
        np.testing.assert_allclose(px("sobreexponer", (0.2, 0.0, 0.7), gris(1.0)), (1.0, 0.0, 1.0), atol=1e-6)

    def test_subexponer(self):
        np.testing.assert_allclose(px("subexponer", (0.6, 0.2, 1.0), gris(0.5)), (0.2, 0.0, 1.0), atol=1e-6)
        np.testing.assert_allclose(px("subexponer", (0.5, 1.0, 0.0), gris(0.0)), (0.0, 1.0, 0.0), atol=1e-6)

    def test_diferencia_y_exclusion(self):
        np.testing.assert_allclose(px("diferencia", gris(0.3), gris(0.8)), gris(0.5), atol=1e-6)
        np.testing.assert_allclose(px("diferencia", gris(0.8), gris(0.3)), gris(0.5), atol=1e-6)
        np.testing.assert_allclose(px("exclusion", gris(0.3), gris(0.8)), gris(0.62), atol=1e-6)

    def test_color(self):
        # Rojo puro sobre gris medio: SetLum(rojo, 0,5) = (1,2; 0,2; 0,2) y ClipColor lo lleva a (1; 2/7; 2/7).
        np.testing.assert_allclose(px("color", gris(0.5), (1, 0, 0)), (1.0, 2 / 7, 2 / 7), atol=1e-5)

    def test_luminosidad(self):
        np.testing.assert_allclose(px("luminosidad", (1, 0, 0), gris(0.5)), (1.0, 2 / 7, 2 / 7), atol=1e-5)
        # Un gris toma la luminosidad de la capa tal cual.
        np.testing.assert_allclose(px("luminosidad", gris(0.2), (0.8, 0.4, 0.2)), gris(0.498), atol=1e-5)

    def test_saturacion(self):
        # Capa gris (saturación 0): el fondo queda gris con su misma luminosidad.
        np.testing.assert_allclose(px("saturacion", (0.8, 0.4, 0.2), gris(0.5)), gris(0.498), atol=1e-5)
        # Fondo gris: SetSat da negro y SetLum lo vuelve al gris del fondo.
        np.testing.assert_allclose(px("saturacion", gris(0.5), (1, 0, 0)), gris(0.5), atol=1e-5)

    def test_tono(self):
        # Fondo (0,8; 0,4; 0,2): saturación 0,6 y luminosidad 0,498. Capa azul puro.
        # SetSat(azul, 0,6) = (0; 0; 0,6); SetLum(·, 0,498) = (0,432; 0,432; 1,032) → ClipColor.
        r = 0.498 - 0.066 * 0.502 / 0.534
        np.testing.assert_allclose(px("tono", (0.8, 0.4, 0.2), (0, 0, 1)), (r, r, 1.0), atol=1e-5)


class TestContraReferencia(unittest.TestCase):

    def test_todos_los_modos_contra_la_referencia(self):
        rng = np.random.default_rng(7)
        n = 300
        cb = rng.random((1, n, 3)).astype(np.float32)
        cs = rng.random((1, n, 3)).astype(np.float32)
        # Bordes: ceros, unos y medios exactos.
        cb[0, :12] = np.array([0, 1, 0.5, 0.25], np.float32)[np.arange(36) % 4].reshape(12, 3)
        cs[0, :12] = np.array([1, 0, 0.5, 0.75], np.float32)[np.arange(36) % 3].reshape(12, 3)
        ab = rng.random((1, n)).astype(np.float32)
        as_ = rng.random((1, n)).astype(np.float32)
        ab[0, :20] = 1.0
        as_[0, 20:30] = 0.0
        ab[0, 30:40] = 0.0
        for modo in MODOS_FUSION:
            rgb, alfa = fusionar(cb, ab, cs, as_, modo)
            self.assertEqual(rgb.dtype, np.float32)
            self.assertEqual(rgb.shape, cb.shape)
            self.assertEqual(alfa.shape, ab.shape)
            for i in range(n):
                esperado, a_esp = _ref_fusionar(modo, [float(v) for v in cb[0, i]], float(ab[0, i]),
                                                [float(v) for v in cs[0, i]], float(as_[0, i]))
                self.assertAlmostEqual(float(alfa[0, i]), a_esp, places=5, msg=modo)
                if a_esp > 1e-3:
                    np.testing.assert_allclose(rgb[0, i], esperado, atol=2e-4, err_msg=f"{modo} píxel {i}")

    def test_resultado_dentro_de_rango(self):
        rng = np.random.default_rng(3)
        cb = rng.random((16, 16, 3)).astype(np.float32)
        cs = rng.random((16, 16, 3)).astype(np.float32)
        a = rng.random((16, 16)).astype(np.float32)
        for modo in MODOS_FUSION:
            rgb, alfa = fusionar(cb, a, cs, a, modo)
            self.assertTrue(np.isfinite(rgb).all(), modo)
            self.assertGreaterEqual(float(rgb.min()), -1e-6, modo)
            self.assertLessEqual(float(rgb.max()), 1 + 1e-6, modo)
            self.assertTrue(((alfa >= 0) & (alfa <= 1 + 1e-6)).all(), modo)


class TestAlfaOpacidadMascara(unittest.TestCase):

    def setUp(self):
        rng = np.random.default_rng(11)
        self.fondo = rng.random((8, 10, 3)).astype(np.float32)
        self.capa = rng.random((8, 10, 3)).astype(np.float32)
        self.uno = np.ones((8, 10), np.float32)
        self.cero = np.zeros((8, 10), np.float32)

    def test_opacidad_cero_es_el_fondo(self):
        for modo in MODOS_FUSION:
            rgb, alfa = fusionar(self.fondo, self.uno, self.capa, self.uno, modo, opacidad=0.0)
            np.testing.assert_allclose(rgb, self.fondo, atol=1e-6, err_msg=modo)
            np.testing.assert_allclose(alfa, 1.0)

    def test_alfa_cero_es_el_fondo(self):
        for modo in MODOS_FUSION:
            rgb, alfa = fusionar(self.fondo, self.uno, self.capa, self.cero, modo)
            np.testing.assert_allclose(rgb, self.fondo, atol=1e-6, err_msg=modo)

    def test_opacidad_media_en_normal(self):
        rgb, _ = fusionar(self.fondo, self.uno, self.capa, self.uno, "normal", opacidad=0.5)
        np.testing.assert_allclose(rgb, (self.fondo + self.capa) / 2, atol=1e-6)

    def test_mascara(self):
        mascara = np.zeros((8, 10), np.float32)
        mascara[:, 5:] = 1.0
        mascara[0, :] = 0.5
        rgb, _ = fusionar(self.fondo, self.uno, self.capa, self.uno, "multiplicar", mascara=mascara)
        mult = self.fondo * self.capa
        np.testing.assert_allclose(rgb[1:, :5], self.fondo[1:, :5], atol=1e-6)
        np.testing.assert_allclose(rgb[1:, 5:], mult[1:, 5:], atol=1e-6)
        np.testing.assert_allclose(rgb[0], (self.fondo[0] + mult[0]) / 2, atol=1e-6)
        # La máscara también puede venir en gris uint8 (0 a 255).
        rgb8, _ = fusionar(self.fondo, self.uno, self.capa, self.uno, "multiplicar",
                           mascara=(mascara * 255).astype(np.uint8))
        np.testing.assert_allclose(rgb8, rgb, atol=3e-3)

    def test_alfa_compuesto_source_over(self):
        # Fondo con alfa 0,5 y capa multiplicar con alfa 0,5 (cálculo a mano):
        # B = 0,16; Cs' = 0,5·0,8 + 0,5·0,16 = 0,48; co = 0,5·0,48 + 0,5·0,2·0,5 = 0,29; αo = 0,75.
        fondo = np.full((1, 1, 3), 0.2, np.float32)
        capa = np.full((1, 1, 3), 0.8, np.float32)
        medio = np.full((1, 1), 0.5, np.float32)
        rgb, alfa = fusionar(fondo, medio, capa, medio, "multiplicar")
        self.assertAlmostEqual(float(alfa[0, 0]), 0.75, places=6)
        np.testing.assert_allclose(rgb[0, 0], 0.29 / 0.75, atol=1e-6)

    def test_fondo_transparente_da_la_capa(self):
        for modo in MODOS_FUSION:
            rgb, alfa = fusionar(self.fondo, self.cero, self.capa, self.uno * 0.4, modo)
            np.testing.assert_allclose(rgb, self.capa, atol=1e-5, err_msg=modo)
            np.testing.assert_allclose(alfa, 0.4, atol=1e-6)

    def test_alfa_none_es_opaco(self):
        rgb, alfa = fusionar(self.fondo, None, self.capa, None, "pantalla", opacidad=0.3)
        rgb2, _ = fusionar(self.fondo, self.uno, self.capa, self.uno, "pantalla", opacidad=0.3)
        np.testing.assert_allclose(rgb, rgb2, atol=1e-7)
        np.testing.assert_allclose(alfa, 1.0)

    def test_no_modifica_las_entradas(self):
        fondo = self.fondo.copy()
        capa = self.capa.copy()
        fusionar(fondo, self.uno, capa, self.uno, "luz_suave", 0.7)
        np.testing.assert_array_equal(fondo, self.fondo)
        np.testing.assert_array_equal(capa, self.capa)

    def test_tipos_de_entrada(self):
        ref, _ = fusionar(self.fondo, None, self.capa, None, "superponer", 0.6)
        u16 = lambda x: (x * 65535).round().astype(np.uint16)   # noqa: E731
        rgb16, _ = fusionar(u16(self.fondo), None, u16(self.capa), None, "superponer", 0.6)
        np.testing.assert_allclose(rgb16, ref, atol=1e-4)   # uint16: se divide por 65535, no queda 0..65535
        for malo in (self.fondo.astype(np.int32), self.fondo > 0.5):
            with self.assertRaises(ValueError):
                fusionar(malo, None, self.capa, None)
        # Un float fuera de rango se recorta a [0, 1] (y no se toca la entrada).
        capa = self.capa.copy()
        capa[0, 0] = (1.7, -0.4, 0.5)
        rgb, _ = fusionar(self.fondo, None, capa, None, "normal")
        np.testing.assert_allclose(rgb[0, 0], (1.0, 0.0, 0.5), atol=1e-7)
        self.assertEqual(float(capa[0, 0, 0]), np.float32(1.7))
        rgb, _ = fusionar(self.fondo, None, self.capa, self.uno * 3, "normal")   # alfa 3 → 1
        np.testing.assert_allclose(rgb, self.capa, atol=1e-6)

    def test_formas_distintas(self):
        with self.assertRaises(ValueError):
            fusionar(self.fondo, self.uno, self.capa[:4], self.uno[:4])
        with self.assertRaises(ValueError):
            fusionar(self.fondo, self.uno[:, :3], self.capa, self.uno)


if __name__ == "__main__":
    unittest.main()
