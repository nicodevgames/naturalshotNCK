"""Pruebas de cada módulo del motor: que hagan lo que dicen, fotográficamente."""

from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from celular_natural.motor import NEUTRO, PRESETS, Ajustes, procesar, procesar_pila  # noqa: E402
from celular_natural.motor.comun import codificar, decodificar  # noqa: E402
from celular_natural.motor.mascaras import calcular_regiones  # noqa: E402
from test_motor import imagen_render, mad  # noqa: E402


def plano(valor, h=300, w=400) -> np.ndarray:
    return np.full((h, w, 3), valor, np.uint8)


def f32(x: np.ndarray) -> np.ndarray:
    return x.astype(np.float32)


class Sensor(unittest.TestCase):
    def test_ruido_sigue_a_la_luz_en_lineal(self):
        """Poisson-Gaussiano: en luz lineal, más señal → más ruido absoluto."""
        desvios = []
        for v in (60, 140, 220):
            out = procesar(plano(v), replace(NEUTRO, ruido=100, ruido_lectura=0))
            lin = decodificar(out)
            desvios.append(float(lin[20:-20, 20:-20, 1].std()))
        self.assertLess(desvios[0], desvios[1])
        self.assertLess(desvios[1], desvios[2])

    def test_ruido_de_lectura_pesa_en_sombras(self):
        sombra = plano(35)
        poco = f32(procesar(sombra, replace(NEUTRO, ruido=100, ruido_lectura=0))).std()
        mucho = f32(procesar(sombra, replace(NEUTRO, ruido=100, ruido_lectura=100))).std()
        self.assertGreater(mucho, poco * 1.3)

    def test_ruido_sin_croma_no_tiene_color(self):
        out = f32(procesar(plano(128), replace(NEUTRO, ruido=100, ruido_croma=0)))
        self.assertLess(np.abs(out[..., 0] - out[..., 1]).mean(), 0.6)
        con = f32(procesar(plano(128), replace(NEUTRO, ruido=100, ruido_croma=100)))
        self.assertGreater(np.abs(con[..., 0] - con[..., 1]).mean(), 0.6)

    def test_bayer_respeta_lo_liso_y_toca_lo_fino(self):
        liso = plano((150, 110, 90))
        self.assertLess(mad(procesar(liso, replace(NEUTRO, bayer=True)), liso), 0.6)
        rayas = plano(40)
        rayas[:, ::2] = 220  # detalle de 1 px
        self.assertGreater(mad(procesar(rayas, replace(NEUTRO, bayer=True)), rayas), 2.0)

    def test_semilla_reproducible_y_variable(self):
        img = imagen_render(400, 300)
        a = replace(NEUTRO, ruido=80, grano=60)
        self.assertTrue(np.array_equal(procesar(img, a), procesar(img, a)))
        self.assertFalse(np.array_equal(procesar(img, a), procesar(img, replace(a, semilla=7))))


class Optica(unittest.TestCase):
    def test_vineteo_oscurece_esquinas_y_no_el_centro(self):
        img = plano(180, 400, 600)
        out = f32(procesar(img, replace(NEUTRO, vineteo=100)))
        self.assertLess(abs(out[200, 300].mean() - 180), 1.5)
        self.assertLess(out[5, 5].mean(), 180 - 20)

    def test_distorsion_curva_las_rectas(self):
        """Barril: una recta horizontal cerca del borde se arquea hacia afuera en el
        medio respecto de sus extremos; cojín, al revés. El centro no se mueve."""
        img = plano(0, 401, 601)
        img[40:43, :] = 255
        img[199:202, 299:302] = 255

        def fila_de_la_recta(out, x):
            col = f32(out)[:120, x].mean(-1)
            return float((col * np.arange(120)).sum() / max(col.sum(), 1e-6))

        barril = procesar(img, replace(NEUTRO, distorsion=100))
        cojin = procesar(img, replace(NEUTRO, distorsion=-100))
        self.assertLess(fila_de_la_recta(barril, 300), fila_de_la_recta(barril, 40) - 0.5)
        self.assertGreater(fila_de_la_recta(cojin, 300), fila_de_la_recta(cojin, 40) + 0.5)
        self.assertGreater(f32(barril)[198:203, 298:303].max(), 150, "el centro no se mueve")

    def test_aberracion_separa_rojo_y_azul_en_los_bordes(self):
        img = plano(30, 400, 600)
        img[:, 560:] = 230  # borde vertical cerca del lateral
        out = f32(procesar(img, replace(NEUTRO, aberracion=100)))
        fila = out[200, 540:580]
        self.assertGreater(np.abs(fila[:, 0] - fila[:, 2]).max(), 3.0)

    def test_desenfoque_baja_las_frecuencias_altas(self):
        img = imagen_render()
        out = procesar(img, replace(NEUTRO, desenfoque=100))
        hf = lambda x: np.abs(np.diff(f32(x).mean(2), axis=1)).mean()
        self.assertLess(hf(out), hf(img) * 0.9)

    def test_interruptor_de_seccion_apaga_todo(self):
        img = imagen_render(400, 300)
        a = replace(NEUTRO, vineteo=100, distorsion=50, aberracion=100, desenfoque=100, bordes=100,
                    optica_activa=False)
        self.assertTrue(np.array_equal(procesar(img, a), img))


class Tono(unittest.TestCase):
    def test_caida_de_luces_comprime_lo_que_pasa_del_blanco(self):
        rampa = np.tile(np.linspace(0, 255, 512).astype(np.uint8), (64, 1))
        img = np.repeat(rampa[..., None], 3, axis=2)
        dura = f32(procesar(img, replace(NEUTRO, exposicion=100)))[..., 1]
        suave = f32(procesar(img, replace(NEUTRO, exposicion=100, luces=100)))[..., 1]
        quemados_dura = (dura[0] >= 254.5).sum()
        quemados_suave = (suave[0] >= 254.5).sum()
        self.assertLess(quemados_suave, quemados_dura, "menos blancos quemados con roll-off")

    def test_pie_de_sombras_levanta_el_negro(self):
        out = f32(procesar(plano(0), replace(NEUTRO, sombras=100)))
        self.assertGreater(out.mean(), 4.0)
        self.assertLess(out.mean(), 14.0)

    def test_zonas_independientes(self):
        rampa = np.tile(np.linspace(0, 255, 256).astype(np.uint8), (8, 1))
        img = np.repeat(rampa[..., None], 3, axis=2)
        out = f32(procesar(img, replace(NEUTRO, zona_sombras=100)))[..., 1]
        diferencia = out[0] - f32(img)[0, :, 1]
        self.assertGreater(diferencia[40:90].mean(), 3.0, "suben las sombras")
        self.assertLess(np.abs(diferencia[200:250]).mean(), 1.0, "las luces casi no cambian")

    def test_desaturar_luces_solo_en_luces(self):
        img = plano((240, 200, 170))
        img[:150] = (120, 70, 40)
        out = f32(procesar(img, replace(NEUTRO, desat_luces=100)))
        croma = lambda x: x.max(-1) - x.min(-1)
        self.assertLess(croma(out[200:, :]).mean(), croma(f32(img)[200:, :]).mean() - 10)
        self.assertLess(abs(croma(out[:100]).mean() - croma(f32(img)[:100]).mean()), 1.5)

    def test_respuesta_de_camara_conserva_luminancia(self):
        img = imagen_render(400, 300)
        out = f32(procesar(img, replace(NEUTRO, respuesta_camara=100)))
        luma = lambda x: x @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        self.assertLess(np.abs(luma(out) - luma(f32(img))).mean(), 1.5)
        self.assertGreater(mad(out.astype(np.uint8), img), 0.3)

    def test_codificar_conserva_margen_sobre_el_blanco(self):
        self.assertGreater(float(codificar(np.array([1.5], np.float32))[0]), 1.0)


class GranoYCompresion(unittest.TestCase):
    def test_grano_monocromo_y_por_zonas(self):
        img = plano(128)
        img[:, 200:] = 235
        a = replace(NEUTRO, grano=100, grano_luces=0)
        out = f32(procesar(img, a))
        self.assertLess(np.abs(out[..., 0] - out[..., 2]).mean(), 0.6, "monocromo")
        self.assertGreater(out[:, 20:180, 1].std(), 2.0, "hay grano en medios")
        self.assertLess(out[:, 220:380, 1].std(), 0.8, "sin grano en luces")

    def test_tamano_del_grano(self):
        fino = f32(procesar(plano(128, 600, 800), replace(NEUTRO, grano=100, grano_tam=0)))[..., 1]
        grueso = f32(procesar(plano(128, 600, 800), replace(NEUTRO, grano=100, grano_tam=100)))[..., 1]
        corr = lambda x: np.corrcoef((x[:, :-1] - x.mean()).ravel(), (x[:, 1:] - x.mean()).ravel())[0, 1]
        self.assertGreater(corr(grueso), corr(fino) + 0.1)

    def test_jpeg_no_se_acumula_en_la_pila(self):
        img = imagen_render(400, 300)
        solo_jpeg = replace(NEUTRO, jpeg=100)
        una = procesar_pila(img, [solo_jpeg])
        dos = procesar_pila(img, [solo_jpeg, solo_jpeg, solo_jpeg])
        self.assertTrue(np.array_equal(una, dos))
        self.assertGreater(mad(una, img), 0.5)

    def test_reescalado_pierde_resolucion_y_conserva_tamano(self):
        img = imagen_render(400, 300)
        for alg in range(4):
            out = procesar(img, replace(NEUTRO, reescalado=100, reescalado_algoritmo=alg))
            self.assertEqual(out.shape, img.shape)
            self.assertGreater(mad(out, img), 0.5)


class Regiones(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        img = plano((70, 90, 110), 400, 600)            # fondo liso (no piel)
        img[100:300, 100:280] = (205, 150, 125)          # parche de piel
        rng = np.random.default_rng(1)
        tela = rng.integers(40, 200, (200, 200, 1)).astype(np.uint8)
        img[100:300, 360:560] = np.repeat(tela, 3, axis=2)  # textura alta
        cls.img = img
        cls.reg = calcular_regiones(img, max(img.shape[:2]) / 4032)

    def test_particion_suave(self):
        r = self.reg
        total = r.piel + r.bordes + r.alta + r.baja
        self.assertLessEqual(float(total.max()), 1.0 + 1e-4)
        self.assertGreaterEqual(float(r.resto().min()), 0.0)

    def test_detecta_cada_zona(self):
        r = self.reg
        self.assertGreater(r.piel[180:220, 160:220].mean(), 0.5)
        self.assertLess(r.piel[20:60, 20:60].mean(), 0.1)
        self.assertGreater(r.alta[180:220, 430:490].mean(), 0.5)
        self.assertGreater(r.baja[20:60, 300:340].mean(), 0.5)

    def test_neutro_no_cambia_nada(self):
        a = replace(PRESETS["Celular natural — inspirado en iPhone 13"], regiones_activas=False)
        b = replace(a, regiones_activas=True)
        self.assertLess(mad(procesar(self.img, a), procesar(self.img, b)), 0.05)

    def test_multiplicador_por_region(self):
        base = replace(NEUTRO, ruido=100, regiones_activas=True)
        sin_ruido_en_piel = replace(base, reg_piel_ruido=0)
        con = f32(procesar(self.img, base))[170:230, 150:230, 1].std()
        sin = f32(procesar(self.img, sin_ruido_en_piel))[170:230, 150:230, 1].std()
        self.assertLess(sin, con * 0.5)


class Parametros(unittest.TestCase):
    def test_desde_dict_tolera_campos_viejos_y_nuevos(self):
        a = Ajustes.desde_dict({"nitidez": 40, "optica": 30, "campo_futuro": 1, "bayer": 1})
        self.assertEqual(a.nitidez, 40)
        self.assertIs(a.bayer, True)
        self.assertEqual(Ajustes.desde_dict(a.como_dict()), a)

    def test_cada_control_existe_en_ajustes(self):
        from celular_natural.motor import CONTROLES
        nombres = set(Ajustes.nombres())
        for campo in CONTROLES:
            self.assertIn(campo, nombres)


if __name__ == "__main__":
    unittest.main()
