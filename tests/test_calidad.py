"""Evaluación de calidad de TODOS los presets sobre escenas de distinto tipo.

Los umbrales marcan "defecto evidente", no un gusto: un preset puede ablandar,
agregar ruido o correr el color a propósito, pero no debe dejar halos, banding,
destruir la resolución o cambiar el color de forma grosera.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from celular_natural.motor import PRESETS, procesar  # noqa: E402
import evaluacion as ev  # noqa: E402

UMBRALES = {
    "detalle_min": 0.80,      # el borde conserva ≥ 80 % de su contraste
    "halo_max": 6.0,          # ≤ 6 niveles de sobreimpulso
    "delta_e_max": 12.0,      # corrimiento de color medio moderado
    "banding_factor": 3.0,    # tramos planos ≤ 3× los del original
    "ruido_max": 9.0,         # desvío en gris plano ≤ 9 niveles
    "resolucion_min": 0.25,   # sobrevive ≥ 25 % del detalle fino
    "brillo_max": 14.0,
    # De noche el HDR del celular levanta las sombras a propósito: se tolera más.
    "brillo_max_noche": 22.0,
}


class CalidadDePresets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.escenas = {n: f() for n, f in ev.ESCENAS.items()}

    def test_cada_preset_en_cada_escena(self):
        for nombre, ajustes in PRESETS.items():
            with self.subTest(preset=nombre):
                e = self.escenas
                ac = procesar(e["alto contraste"], ajustes)
                self.assertGreater(ev.detalle_borde(e["alto contraste"], ac), UMBRALES["detalle_min"])
                self.assertLess(ev.halo(e["alto contraste"], ac), UMBRALES["halo_max"])
                self.assertLess(ev.delta_e(e["carta"], procesar(e["carta"], ajustes)), UMBRALES["delta_e_max"])
                deg = procesar(e["degradado"], ajustes)
                self.assertLessEqual(ev.banding(deg), ev.banding(e["degradado"]) * UMBRALES["banding_factor"])
                gris = np.full((400, 400, 3), 128, np.uint8)
                self.assertLess(ev.ruido_plano(procesar(gris, ajustes)), UMBRALES["ruido_max"])
                self.assertGreater(ev.resolucion(e["textil"], procesar(e["textil"], ajustes)),
                                   UMBRALES["resolucion_min"])
                for escena in ("retrato", "interior", "exterior", "noche"):
                    out = procesar(e[escena], ajustes)
                    self.assertEqual(out.shape, e[escena].shape)
                    limite = UMBRALES["brillo_max_noche" if escena == "noche" else "brillo_max"]
                    self.assertLess(ev.brillo(e[escena], out), limite, escena)

    def test_mascaras_sin_escalones_en_el_limite(self):
        """Con regiones muy distintas, el límite piel/fondo no debe dejar un escalón."""
        from dataclasses import replace
        img = self.escenas["retrato"]
        base = replace(PRESETS["Celular natural — inspirado en iPhone 13"], regiones_activas=True,
                       reg_piel_suavizado=200, reg_piel_ruido=0, reg_baja_suavizado=0)
        out = procesar(img, base).astype(np.float32).mean(-1)
        orig = img.astype(np.float32).mean(-1)
        # El salto entre píxeles vecinos no crece más que en el original + ruido.
        salto = lambda x: np.abs(np.diff(x, axis=1)).max()
        self.assertLess(salto(out), salto(orig) + 40)


if __name__ == "__main__":
    unittest.main()
