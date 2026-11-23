"""Pruebas de los estilos de capa (``motor/estilos.py``): sombra, trazo, resplandor y
superposiciones, sus datos (validación e ida y vuelta) y cuánto crece el resultado.

Las imágenes se generan acá (cuadrados y discos RGBA).
"""

from __future__ import annotations

import importlib
import pickle
import sys
import time
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from celular_natural.motor import estilos as m_estilos  # noqa: E402
from celular_natural.motor.estilos import (  # noqa: E402
    EstilosCapa, Resplandor, Sombra, SuperposicionColor, SuperposicionDegradado, Trazo, aplicar_estilos,
    aplicar_premultiplicado, margenes,
)


def cuadrado(w=20, h=20, color=(255, 255, 255)) -> np.ndarray:
    img = np.zeros((h, w, 4), np.uint8)
    img[..., :3] = color
    img[..., 3] = 255
    return img


def disco(lado=41, radio=14.0, color=(250, 250, 250)) -> np.ndarray:
    yy, xx = np.mgrid[0:lado, 0:lado].astype(np.float32) + 0.5
    a = np.clip(radio + 0.5 - np.hypot(xx - lado / 2, yy - lado / 2), 0, 1)
    img = np.zeros((lado, lado, 4), np.uint8)
    img[..., :3] = color
    img[..., 3] = (a * 255).round()
    return img


def modulo_formas():
    try:
        return importlib.import_module("celular_natural.motor.formas")
    except ImportError:
        return None


class TestDatos(unittest.TestCase):

    def test_por_defecto_vacio(self):
        e = EstilosCapa()
        self.assertTrue(e.vacio)
        self.assertEqual(e.activos, ())
        self.assertFalse(EstilosCapa(sombra=Sombra()).vacio)
        self.assertTrue(EstilosCapa(sombra=Sombra(activo=False)).vacio)   # apagada: no cuenta
        self.assertEqual(EstilosCapa(trazo=Trazo(), color=SuperposicionColor()).activos, ("trazo", "color"))

    def test_validacion(self):
        with self.assertRaises(ValueError):
            Sombra(color=(0, 0, 300))
        with self.assertRaises(ValueError):
            Sombra(color="negro")
        with self.assertRaises(ValueError):
            Sombra(distancia=-1)
        with self.assertRaises(ValueError):
            Sombra(tamano=float("nan"))
        with self.assertRaises(ValueError):
            Trazo(posicion="arriba")
        with self.assertRaises(ValueError):
            Trazo(grosor=-2)
        with self.assertRaises(ValueError):
            Resplandor(activo=1)
        with self.assertRaises(ValueError):
            EstilosCapa(sombra=Trazo())
        with self.assertRaises(ValueError):
            Sombra(distancia=10 ** 9)   # tope: no se piden márgenes gigantes
        self.assertEqual(Sombra(color=(1, 2, 3)).color, (1, 2, 3, 255))
        self.assertEqual(Sombra(color=[1, 2, 3, 4]).color, (1, 2, 3, 4))
        self.assertEqual(Sombra(opacidad=3).opacidad, 1.0)
        self.assertEqual(SuperposicionColor(opacidad=-1).opacidad, 0.0)

    def test_dict_ida_y_vuelta_y_pickle(self):
        e = EstilosCapa(sombra=Sombra((10, 20, 30, 200), 0.5, 45, 7, 3), trazo=Trazo((255, 0, 0), 4, "centro"),
                        resplandor=Resplandor(activo=False), color=SuperposicionColor((0, 0, 255), 0.3))
        d = e.como_dict()
        self.assertEqual(EstilosCapa.desde_dict(d), e)
        self.assertEqual(EstilosCapa.desde_dict({}), EstilosCapa())
        self.assertEqual(EstilosCapa.desde_dict({"sombra": {"distancia": 3}, "raro": 1}),
                         EstilosCapa(sombra=Sombra(distancia=3)))
        import json
        json.dumps(d)   # solo tipos de JSON
        self.assertEqual(pickle.loads(pickle.dumps(e)), e)
        self.assertEqual(hash(e), hash(EstilosCapa.desde_dict(d)))
        with self.assertRaises(ValueError):
            EstilosCapa.desde_dict({"sombra": {"distancia": "mucho"}})
        with self.assertRaises(ValueError):
            EstilosCapa.desde_dict([1])

    def test_escalados_y_girados(self):
        e = EstilosCapa(sombra=Sombra(angulo=120, distancia=10, tamano=4), trazo=Trazo(grosor=3),
                        resplandor=Resplandor(tamano=6))
        d = e.escalados(2.0)
        self.assertEqual((d.sombra.distancia, d.sombra.tamano, d.trazo.grosor, d.resplandor.tamano), (20, 8, 6, 12))
        self.assertEqual(e.girados(90).sombra.angulo, 30.0)          # horario: el ángulo (antihorario) baja
        self.assertEqual(e.espejados("h").sombra.angulo, 60.0)       # 180 - a
        self.assertEqual(e.espejados("v").sombra.angulo, 240.0)      # -a
        self.assertEqual(EstilosCapa().escalados(3), EstilosCapa())


class TestAplicar(unittest.TestCase):

    def test_sin_estilos_es_lo_mismo(self):
        img = disco()
        salida, desp = aplicar_estilos(img, EstilosCapa())
        np.testing.assert_array_equal(salida, img)
        self.assertEqual(desp, (0, 0))
        salida, desp = aplicar_estilos(img, EstilosCapa(sombra=Sombra(activo=False)))
        np.testing.assert_array_equal(salida, img)

    def test_sombra_desplazada(self):
        img = cuadrado()
        # 120°: la luz viene de arriba a la izquierda, la sombra cae abajo a la derecha (como Photoshop).
        e = EstilosCapa(sombra=Sombra((0, 0, 0, 255), 1.0, 120, 10, 0))
        salida, desp = aplicar_estilos(img, e)
        dx, dy = round(-np.cos(np.radians(120)) * 10), round(np.sin(np.radians(120)) * 10)
        self.assertEqual((dx, dy), (5, 9))
        self.assertEqual(desp, (0, 0))   # crece a la derecha y abajo: el origen no se mueve
        self.assertEqual(salida.shape, (20 + dy, 20 + dx, 4))
        np.testing.assert_array_equal(salida[:20, :20], img)          # el cuadrado, intacto, arriba
        np.testing.assert_array_equal(salida[20:, dx:dx + 20, :3], 0)  # abajo: sombra negra y opaca
        self.assertTrue((salida[20:, dx:dx + 20, 3] == 255).all())
        np.testing.assert_array_equal(salida[dy:20, 20:, :3], 0)      # a la derecha, también
        self.assertTrue((salida[dy:20, 20:, 3] == 255).all())
        self.assertTrue((salida[:dy, 20:, 3] == 0).all())             # arriba a la derecha: nada
        self.assertTrue((salida[20:, :dx, 3] == 0).all())             # abajo a la izquierda: nada
        # 0°: la luz viene de la derecha, la sombra va a la izquierda: el origen se corre.
        salida, desp = aplicar_estilos(img, EstilosCapa(sombra=Sombra(angulo=0, distancia=6, tamano=0)))
        self.assertEqual(desp, (-6, 0))
        self.assertEqual(salida.shape, (20, 26, 4))
        self.assertTrue((salida[:, :6, 3] > 0).all())

    def test_sombra_suave(self):
        e = EstilosCapa(sombra=Sombra((0, 0, 0, 255), 0.8, 90, 8, 6))
        salida, desp = aplicar_estilos(disco(), e)
        izq, arr, der, aba = margenes(e)
        self.assertEqual(salida.shape[:2], (41 + arr + aba, 41 + izq + der))
        self.assertEqual(desp, (-izq, -arr))
        a = salida[..., 3].astype(int)
        valores = set(np.unique(a[a > 0]).tolist())
        self.assertGreater(len(valores), 20)                 # degradada
        self.assertLessEqual(a[-1].max(), 40)                # se apaga hacia el borde
        self.assertLessEqual(int(a.max()), 255)

    def test_trazo_afuera_agranda_el_contorno(self):
        img = disco()
        e = EstilosCapa(trazo=Trazo((255, 0, 0), 4, "afuera"))
        salida, desp = aplicar_estilos(img, e)
        izq, arr, der, aba = margenes(e)
        self.assertEqual(desp, (-izq, -arr))
        self.assertGreaterEqual(izq, 4)
        a0 = int((img[..., 3] > 127).sum())
        a1 = int((salida[..., 3] > 127).sum())
        esperado = np.pi * (14 + 4) ** 2
        self.assertAlmostEqual(a1, esperado, delta=esperado * 0.06)   # el disco más el trazo
        self.assertGreater(a1, a0)
        cy, cx = 20 + arr, 20 + izq
        self.assertEqual(tuple(salida[cy, cx, :3]), (250, 250, 250))  # adentro, el contenido
        anillo = salida[cy, cx + 16]                                     # en el trazo: rojo opaco
        self.assertEqual(tuple(anillo), (255, 0, 0, 255))

    def test_trazo_adentro_no_crece(self):
        img = disco()
        e = EstilosCapa(trazo=Trazo((0, 0, 255), 3, "adentro"))
        self.assertEqual(margenes(e), (0, 0, 0, 0))
        salida, desp = aplicar_estilos(img, e)
        self.assertEqual((salida.shape, desp), (img.shape, (0, 0)))
        np.testing.assert_array_equal(salida[..., 3], img[..., 3])   # el alfa no cambia
        self.assertEqual(tuple(salida[20, 20, :3]), (250, 250, 250))
        self.assertEqual(tuple(salida[20, 20 + 12, :3]), (0, 0, 255))

    def test_trazo_centro(self):
        e = EstilosCapa(trazo=Trazo((0, 255, 0), 6, "centro"))
        izq, arr, der, aba = margenes(e)
        self.assertEqual(izq, 4)   # la mitad afuera (3) más uno
        salida, _ = aplicar_estilos(disco(), e)
        cy, cx = 20 + arr, 20 + izq
        self.assertEqual(tuple(salida[cy, cx + 14, :3]), (0, 255, 0))   # justo en el borde

    def test_resplandor(self):
        e = EstilosCapa(resplandor=Resplandor((255, 255, 0), 1.0, 8))
        salida, desp = aplicar_estilos(disco(), e)
        izq, arr, der, aba = margenes(e)
        self.assertEqual(desp, (-izq, -arr))
        cy, cx = 20 + arr, 20 + izq
        fila = salida[cy, cx + 15:cx + 15 + 8, 3].astype(int)
        self.assertTrue((np.diff(fila) <= 0).all())   # se apaga hacia afuera
        self.assertGreater(fila[0], 0)
        self.assertGreater(int(salida[cy, cx + 16, 0]), 200)   # amarillo

    def test_superposicion_de_color(self):
        img = disco()
        salida, desp = aplicar_estilos(img, EstilosCapa(color=SuperposicionColor((255, 0, 0), 1.0)))
        self.assertEqual(desp, (0, 0))
        np.testing.assert_array_equal(salida[..., 3], img[..., 3])
        dentro = img[..., 3] == 255
        self.assertTrue((salida[dentro][:, :3] == (255, 0, 0)).all())
        medio, _ = aplicar_estilos(img, EstilosCapa(color=SuperposicionColor((0, 0, 0), 0.5)))
        self.assertAlmostEqual(int(medio[20, 20, 0]), 125, delta=1)

    def test_superposicion_de_degradado(self):
        formas = modulo_formas()
        if formas is None:
            self.skipTest("todavía no está motor/formas.py (M2)")
        rel = formas.Relleno("lineal", ((255, 0, 0, 255), (0, 0, 255, 255)), (), 0.0)   # izquierda → derecha
        img = cuadrado(40, 10)
        salida, _ = aplicar_estilos(img, EstilosCapa(degradado=SuperposicionDegradado(rel, 1.0)))
        self.assertGreater(int(salida[5, 1, 0]), 200)
        self.assertGreater(int(salida[5, 38, 2]), 200)
        np.testing.assert_array_equal(salida[..., 3], img[..., 3])
        # Sin relleno: negro a blanco.
        salida, _ = aplicar_estilos(img, EstilosCapa(degradado=SuperposicionDegradado()))
        self.assertNotEqual(int(salida[0, 20, 0]), int(salida[9, 20, 0]))

    def test_escala(self):
        e = EstilosCapa(sombra=Sombra(distancia=10, tamano=4), trazo=Trazo(grosor=3))
        m1, m2 = margenes(e, 1.0), margenes(e, 0.5)
        self.assertTrue(all(b <= a for a, b in zip(m1, m2)))
        self.assertLess(sum(m2), sum(m1))

    def test_premultiplicado_igual_que_aplicar(self):
        import cv2
        img = disco(color=(200, 120, 40))
        e = EstilosCapa(sombra=Sombra(tamano=3), trazo=Trazo((10, 200, 10), 2), color=SuperposicionColor(opacidad=0.4))
        salida, desp = aplicar_estilos(img, e)
        planos = np.ascontiguousarray(np.moveaxis(cv2.cvtColor(img, cv2.COLOR_RGBA2mRGBA), -1, 0))
        p2, desp2 = aplicar_premultiplicado(planos, e)
        self.assertEqual(desp, desp2)
        prem = np.moveaxis(p2, 0, -1)
        np.testing.assert_array_equal(prem[..., 3], salida[..., 3])
        self.assertTrue((prem[..., :3] <= prem[..., 3:]).all())   # premultiplicado de verdad

    def test_velocidad(self):
        # Un texto grande (1000×300, con bordes suaves) con sombra y trazo, como en un flyer.
        img = np.zeros((300, 1000, 4), np.uint8)
        img[..., :3] = 255
        yy, xx = np.mgrid[0:300, 0:1000]
        img[..., 3] = (((xx // 40) % 2 == 0) & (yy > 40) & (yy < 260)) * 255
        e = EstilosCapa(sombra=Sombra(distancia=12, tamano=10), trazo=Trazo(grosor=4))
        aplicar_estilos(img, e)
        tiempos = []
        for _ in range(3):
            t0 = time.perf_counter()
            aplicar_estilos(img, e)
            tiempos.append(time.perf_counter() - t0)
        print(f"\n  estilos (sombra + trazo) en 1000x300: {min(tiempos) * 1000:.1f} ms")
        self.assertLess(min(tiempos), 0.040)

    def test_no_toca_la_entrada(self):
        img = disco()
        antes = img.copy()
        aplicar_estilos(img, EstilosCapa(sombra=Sombra(), trazo=Trazo(), color=SuperposicionColor()))
        np.testing.assert_array_equal(img, antes)
        with self.assertRaises(ValueError):
            aplicar_estilos(img[..., :3], EstilosCapa())
        self.assertTrue(hasattr(m_estilos, "TOPE_PIXELES"))


if __name__ == "__main__":
    unittest.main()
