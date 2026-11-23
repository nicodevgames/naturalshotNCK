"""Pruebas del montaje de fotos (pegar partes de otra foto, alinear, igualar color)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from celular_natural.motor.montaje import (  # noqa: E402
    CapaFoto, alinear_foto, componer, estimar_alineacion, igualar_color, limpiar_cache,
)
from celular_natural.motor.zonas import Zona  # noqa: E402


def escena(w=800, h=600, semilla=3):
    """Escena con textura y formas (para que haya puntos que alinear)."""
    rng = np.random.default_rng(semilla)
    img = (rng.random((h // 8, w // 8, 3)) * 255).astype(np.uint8)
    img = cv2.resize(img, (w, h), interpolation=cv2.INTER_CUBIC)
    for _ in range(40):
        c = tuple(int(v) for v in rng.integers(0, 255, 3))
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
        cv2.circle(img, (x, y), int(rng.integers(10, 60)), c, -1)
        cv2.rectangle(img, (x, y), (x + int(rng.integers(10, 80)), y + int(rng.integers(10, 80))), c[::-1], 3)
    return img


def desplazar(img, dx, dy, ang=0.0):
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
    M[:, 2] += (dx, dy)
    return cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)


class PruebasMontaje(unittest.TestCase):
    def setUp(self):
        limpiar_cache()

    def test_mitad_inferior_de_otra_foto(self):
        base = np.full((200, 300, 3), 50, np.uint8)
        otra = np.full((200, 300, 3), 200, np.uint8)
        capa = CapaFoto("otra.png", Zona("rect", 0, 0.5, 1, 1, pluma=0), alinear=False, igualar=False)
        out, avisos = componer(base, [capa], lambda r: otra, "base")
        self.assertEqual(out.shape, base.shape)
        self.assertEqual(int(out[20, 150, 0]), 50)    # arriba: foto base
        self.assertEqual(int(out[180, 150, 0]), 200)  # abajo: la otra
        self.assertEqual(avisos, [])

    def test_opacidad_y_sin_capas(self):
        base = np.full((50, 50, 3), 0, np.uint8)
        otra = np.full((50, 50, 3), 200, np.uint8)
        out, _ = componer(base, [CapaFoto("o", None, opacidad=50, alinear=False, igualar=False)], lambda r: otra)
        self.assertAlmostEqual(float(out.mean()), 100, delta=1)
        self.assertIs(componer(base, [], lambda r: otra)[0], base)

    def test_tamano_distinto_se_adapta(self):
        base = np.zeros((300, 400, 3), np.uint8)
        otra = np.full((600, 800, 3), 120, np.uint8)
        out, _ = componer(base, [CapaFoto("o", None, alinear=False, igualar=False)], lambda r: otra)
        self.assertEqual(out.shape, base.shape)
        self.assertAlmostEqual(float(out.mean()), 120, delta=1)

    def test_alineacion_corrige_movimiento(self):
        base = escena()
        movida = desplazar(base, 14, -9, ang=1.5)
        H = estimar_alineacion(base, movida)
        self.assertIsNotNone(H)
        alineada, valida, ok = alinear_foto(base, movida, True)
        self.assertTrue(ok)
        centro = (slice(100, 500), slice(100, 700))
        error_alineada = np.abs(alineada[centro].astype(int) - base[centro]).mean()
        error_sin = np.abs(movida[centro].astype(int) - base[centro]).mean()
        self.assertLess(error_alineada, error_sin * 0.25)
        self.assertLess(error_alineada, 8)
        self.assertGreater(float(valida.mean()), 0.85)

    def test_sin_coincidencias_no_rompe(self):
        base = np.full((200, 200, 3), 90, np.uint8)  # imagen lisa: no hay puntos
        out, avisos = componer(base, [CapaFoto("lisa.png", None, alinear=True, igualar=False)],
                               lambda r: np.full((200, 200, 3), 30, np.uint8))
        self.assertEqual(out.shape, base.shape)
        self.assertEqual(len(avisos), 1)

    def test_igualar_color(self):
        base = escena()
        oscura = np.clip(base.astype(int) * 0.7 + 10, 0, 255).astype(np.uint8)
        igualada = igualar_color(base, oscura, np.ones(base.shape[:2], np.float32))
        self.assertLess(abs(float(igualada.mean()) - float(base.mean())), 2)
        self.assertLess(np.abs(igualada.astype(int) - base).mean(), np.abs(oscura.astype(int) - base).mean())

    def test_base_intacta(self):
        base = escena(200, 150)
        copia = base.copy()
        componer(base, [CapaFoto("o", Zona("elipse", 0.2, 0.2, 0.8, 0.8), alinear=False)],
                 lambda r: np.zeros_like(base))
        self.assertTrue(np.array_equal(base, copia))


if __name__ == "__main__":
    unittest.main()
