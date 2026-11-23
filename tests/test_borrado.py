"""Pruebas del borrado de objetos (relleno automático y tampón de clonar)."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from celular_natural.motor.borrado import clonar, rellenar  # noqa: E402

MAGENTA = (230, 30, 200)


def ruido_suave(h, w, rng, celdas):
    """Ruido de una escala: grilla aleatoria chica ampliada (nubes, manchas)."""
    lado = max(h, w)
    base = rng.standard_normal((max(2, celdas * h // lado) + 1, celdas + 1)).astype(np.float32)
    return cv2.resize(base, (w, h), interpolation=cv2.INTER_CUBIC)


def textura(h, w, rng, octavas=5, celdas=6):
    t = np.zeros((h, w), np.float32)
    for o in range(octavas):
        t += 0.6 ** o * ruido_suave(h, w, rng, celdas * 2 ** o)
    return t / (t.std() + 1e-6)


def paisaje(h=480, w=640, semilla=1, horizonte=0.6):
    """Cielo con degradé y nubes arriba, pasto con textura abajo, ruido fino en todo."""
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cielo = np.stack([70 + 110 * xx / w, 90 + 70 * yy / h, 150 - 70 * xx / w], -1) + textura(h, w, rng)[..., None] * 12
    pasto = np.stack([60 + 30 * xx / w, 115 + 0 * yy, 50 + 0 * xx], -1) + textura(h, w, rng, 6, 12)[..., None] * 20
    img = np.where((yy < h * horizonte)[..., None], cielo, pasto) + rng.normal(0, 6, (h, w, 1))
    return np.clip(img, 0, 255).astype(np.uint8)


def ladrillos(h=360, w=480, semilla=3):
    rng = np.random.default_rng(semilla)
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (150, 70, 50)
    for fila, y in enumerate(range(0, h, 40)):
        img[y:y + 4] = (200, 200, 190)
        for x in range(-40 if fila % 2 else 0, w, 80):
            img[y:y + 40, max(0, x):max(0, x + 4)] = (200, 200, 190)
    img += rng.normal(0, 8, (h, w, 1))
    return np.clip(cv2.GaussianBlur(img, (0, 0), 0.8), 0, 255).astype(np.uint8)


def con_circulo(img, centro, radio, color=MAGENTA):
    """Dibuja un "objeto" de color sólido y devuelve (imagen, máscara float32)."""
    obj = img.copy()
    mascara = np.zeros(img.shape[:2], np.float32)
    cv2.circle(obj, centro, radio, color, -1)
    cv2.circle(mascara, centro, radio, 1.0, -1)
    return obj, mascara


def detalle(img):
    """Desvío local de la luma sin las bajas frecuencias (cuánta textura hay)."""
    y = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32)
    return y - cv2.GaussianBlur(y, (0, 0), 2.0)


def interior(mascara, margen):
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * margen + 1, 2 * margen + 1))
    return cv2.erode((mascara > 0.5).astype(np.uint8), k) > 0


def anillo(mascara, desde, hasta):
    def dil(r):
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
        return cv2.dilate((mascara > 0).astype(np.uint8), k) > 0
    return dil(hasta) & ~dil(desde)


def es_pasto(img):
    f = cv2.GaussianBlur(img.astype(np.float32), (0, 0), 2)
    return (f[..., 1] - np.maximum(f[..., 0], f[..., 2])) > 15


class PruebasRellenar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fondo = paisaje()

    def test_objeto_desaparece(self):
        obj, m = con_circulo(self.fondo, (330, 200), 60)  # todo en el cielo
        out = rellenar(obj, m)
        adentro = interior(m, 3)
        media = out[adentro].astype(np.float32).mean(0)
        real = self.fondo[adentro].astype(np.float32).mean(0)
        self.assertLess(np.abs(media - real).max(), 12, f"{media} vs fondo {real}")
        self.assertGreater(np.linalg.norm(media - np.array(MAGENTA)), 100)
        # Ningún píxel del interior conserva el color del objeto.
        dist = np.linalg.norm(out[adentro].astype(np.float32) - np.array(MAGENTA, np.float32), axis=1)
        self.assertGreater(float(dist.min()), 60)

    def test_fuera_de_la_mascara_identico(self):
        obj, m = con_circulo(self.fondo, (300, 300), 70)
        out = rellenar(obj, m, dilatar=4)
        lejos = ~anillo(m, 0, 4 + 2) & (m == 0)
        self.assertTrue(np.array_equal(out[lejos], obj[lejos]))
        self.assertGreater(int((out != obj).any(-1).sum()), int((m > 0).sum()) * 0.9)

    def test_relleno_con_textura(self):
        obj, m = con_circulo(self.fondo, (300, 330), 80)  # en el pasto
        out = rellenar(obj, m)
        adentro = interior(m, 6)
        alrededor = anillo(m, 10, 40)
        d_out, d_fondo = detalle(out), detalle(self.fondo)
        relleno = float(d_out[adentro].std())
        entorno = float(d_fondo[alrededor].std())
        self.assertGreater(relleno, 0.6 * entorno, f"relleno {relleno:.2f} vs entorno {entorno:.2f}")
        self.assertLess(relleno, 1.6 * entorno)
        # Telea solo deja una mancha lisa: el relleno tiene que tener bastante más textura.
        telea = cv2.inpaint(obj, (m > 0).astype(np.uint8) * 255, 5, cv2.INPAINT_TELEA)
        self.assertGreater(relleno, 2.0 * float(detalle(telea)[adentro].std()))
        # Con textura=0 queda más liso.
        liso = rellenar(obj, m, textura=0)
        self.assertLess(float(detalle(liso)[adentro].std()), 0.8 * relleno)

    def test_continua_el_horizonte(self):
        h = self.fondo.shape[0]
        obj, m = con_circulo(self.fondo, (320, int(h * 0.6)), 90)  # centrado en el horizonte
        out = rellenar(obj, m)
        equivocados = float((es_pasto(out) != es_pasto(self.fondo))[m > 0].mean() * 100)
        telea = cv2.inpaint(obj, (m > 0).astype(np.uint8) * 255, 5, cv2.INPAINT_TELEA)
        equivocados_telea = float((es_pasto(telea) != es_pasto(self.fondo))[m > 0].mean() * 100)
        self.assertLess(equivocados, 6.0, f"{equivocados:.1f} % (Telea {equivocados_telea:.1f} %)")

    def test_patron_regular(self):
        fondo = ladrillos()
        obj, m = con_circulo(fondo, (240, 180), 70, (40, 160, 230))
        out = rellenar(obj, m)
        adentro = interior(m, 3)
        error = float(np.abs(out.astype(np.int16) - fondo)[adentro].mean())
        error_telea = float(np.abs(cv2.inpaint(obj, (m > 0).astype(np.uint8) * 255, 5, cv2.INPAINT_TELEA)
                                   .astype(np.int16) - fondo)[adentro].mean())
        # El ruido solo ya da ≈ 9 de error medio; Telea, que no sigue las juntas, bastante más.
        self.assertLess(error, 16, f"error {error:.1f} (Telea {error_telea:.1f})")

    def test_mascara_vacia(self):
        m = np.zeros(self.fondo.shape[:2], np.float32)
        out = rellenar(self.fondo, m)
        self.assertTrue(np.array_equal(out, self.fondo))
        self.assertIsNot(out, self.fondo)
        self.assertFalse(np.shares_memory(out, self.fondo))
        # Valores por debajo del umbral (≤ 0,01) tampoco tocan nada.
        self.assertTrue(np.array_equal(rellenar(self.fondo, m + 0.005), self.fondo))

    def test_entrada_no_modificada(self):
        obj, m = con_circulo(self.fondo, (200, 200), 50)
        copia_img, copia_m = obj.copy(), m.copy()
        rellenar(obj, m)
        clonar(obj, m, (150, 0))
        clonar(obj, m, (150, 0), sin_costuras=False)
        self.assertTrue(np.array_equal(obj, copia_img))
        self.assertTrue(np.array_equal(m, copia_m))

    def test_tipos_de_mascara(self):
        obj, m = con_circulo(self.fondo, (200, 200), 40)
        ref = rellenar(obj, m)
        for otra in (m > 0.5, (m * 255).astype(np.uint8), m.astype(np.float64), m[..., None]):
            out = rellenar(obj, otra)
            self.assertEqual(out.shape, obj.shape)
            self.assertTrue(np.array_equal(out, ref))
        con_nan = m.copy()
        con_nan[0, 0] = np.nan
        self.assertTrue(np.array_equal(rellenar(obj, con_nan), ref))

    def test_mascara_suave(self):
        obj, m = con_circulo(self.fondo, (320, 180), 50)
        suave = cv2.GaussianBlur(m, (0, 0), 8)
        out = rellenar(obj, suave)
        self.assertEqual(out.dtype, np.uint8)
        nada = suave <= 0.01
        self.assertTrue(np.array_equal(out[nada], obj[nada]))
        adentro = suave > 0.9
        dist = np.linalg.norm(out[adentro].astype(np.float32) - np.array(MAGENTA, np.float32), axis=1)
        self.assertGreater(float(dist.mean()), 100)

    def test_tamanos_impares_y_bordes(self):
        for h, w in ((101, 157), (37, 23), (9, 7), (1, 1), (2, 300)):
            img = paisaje(max(h, 8), max(w, 8), semilla=h)[:h, :w].copy()
            for centro in ((w // 2, h // 2), (0, 0), (w - 1, h - 1)):
                m = np.zeros((h, w), np.float32)
                cv2.circle(m, centro, max(1, min(h, w) // 3), 1.0, -1)
                out = rellenar(img, m)
                self.assertEqual(out.shape, img.shape)
                self.assertEqual(out.dtype, np.uint8)
        # Máscara que cubre toda la foto: no hay de dónde sacar, queda igual.
        img = paisaje(40, 60)
        self.assertTrue(np.array_equal(rellenar(img, np.ones((40, 60), np.float32)), img))

    def test_objeto_en_la_esquina(self):
        obj, m = con_circulo(self.fondo, (630, 5), 70)
        out = rellenar(obj, m)
        adentro = interior(m, 3)
        dist = np.linalg.norm(out[adentro].astype(np.float32) - np.array(MAGENTA, np.float32), axis=1)
        self.assertGreater(float(dist.min()), 60)

    def test_varias_manchas_y_cable(self):
        obj = self.fondo.copy()
        m = np.zeros(obj.shape[:2], np.float32)
        rng = np.random.default_rng(4)
        for _ in range(12):
            c = (int(rng.integers(10, 630)), int(rng.integers(10, 470)))
            r = int(rng.integers(2, 12))
            cv2.circle(obj, c, r, MAGENTA, -1)
            cv2.circle(m, c, r, 1.0, -1)
        cv2.line(obj, (0, 40), (639, 420), (20, 20, 20), 3)
        cv2.line(m, (0, 40), (639, 420), 1.0, 3)
        out = rellenar(obj, m)
        marcado = m > 0
        dist = np.linalg.norm(out[marcado].astype(np.float32) - np.array(MAGENTA, np.float32), axis=1)
        self.assertGreater(float(dist.min()), 60)
        self.assertGreater(float(out[marcado].astype(np.float32).mean()), 60)  # sin restos del cable negro

    def test_repetible(self):
        obj, m = con_circulo(self.fondo, (300, 300), 60)
        self.assertTrue(np.array_equal(rellenar(obj, m, semilla=7), rellenar(obj, m, semilla=7)))

    def test_validacion(self):
        m = np.zeros((10, 10), np.float32)
        img = np.zeros((10, 10, 3), np.uint8)
        with self.assertRaises(TypeError):
            rellenar(img.tolist(), m)
        with self.assertRaises(TypeError):
            rellenar(img.astype(np.float32), m)
        with self.assertRaises(ValueError):
            rellenar(img[..., 0], m)
        with self.assertRaises(ValueError):
            rellenar(img, np.zeros((10, 11), np.float32))
        with self.assertRaises(TypeError):
            rellenar(img, m.astype(np.int16))
        with self.assertRaises(ValueError):
            rellenar(img, m, textura=-1)
        with self.assertRaises(ValueError):
            rellenar(img, m, dilatar=-2)
        with self.assertRaises(ValueError):
            rellenar(img, m, dilatar=float("inf"))
        for malo in ("ab", (1,), (1, 2, 3), None):
            with self.assertRaises(TypeError):
                clonar(img, m, malo)
        with self.assertRaises(ValueError):
            clonar(img, m, (float("nan"), 0))


class PruebasClonar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fondo = paisaje()

    def test_copia_desde_el_desplazamiento(self):
        m = np.zeros(self.fondo.shape[:2], np.float32)
        m[300:340, 200:250] = 1.0
        out = clonar(self.fondo, m, (60, -30), sin_costuras=False, dilatar=0)
        self.assertTrue(np.array_equal(out[300:340, 200:250], self.fondo[270:310, 260:310]))
        fuera = m == 0
        self.assertTrue(np.array_equal(out[fuera], self.fondo[fuera]))

    def test_sin_costuras_toma_la_textura_de_la_fuente(self):
        obj, m = con_circulo(self.fondo, (200, 380), 45, (15, 15, 15))  # objeto oscuro en el pasto
        out = clonar(obj, m, (250, 20))
        adentro = interior(m, 4)
        fuente = np.roll(np.roll(self.fondo, -20, axis=0), -250, axis=1)
        # La textura (alta frecuencia) es la de la fuente...
        a, b = detalle(out)[adentro], detalle(fuente)[adentro]
        self.assertGreater(float(np.corrcoef(a, b)[0, 1]), 0.9)
        # ...y el objeto oscuro no reaparece (seamlessClone erosiona la máscara: regresión).
        self.assertGreater(float(out[adentro].astype(np.float32).mean()), 50)
        lejos = ~anillo(m, 0, 10) & (m == 0)
        self.assertTrue(np.array_equal(out[lejos], obj[lejos]))

    def test_desplazamiento_fuera_de_rango(self):
        obj, m = con_circulo(self.fondo, (600, 240), 30)
        h, w = obj.shape[:2]
        for desp in ((10_000, 0), (0, -10_000), (w, 0), (0, h)):
            self.assertTrue(np.array_equal(clonar(obj, m, desp), obj))
        self.assertTrue(np.array_equal(clonar(obj, m, (0, 0)), obj))
        # Parcialmente afuera (a la derecha; y abajo para no copiar el mismo objeto):
        # lo que tiene fuente válida cambia; lo que no, queda igual.
        for sin_costuras in (True, False):
            out = clonar(obj, m, (25, 100), sin_costuras=sin_costuras, dilatar=0)
            self.assertEqual(out.shape, obj.shape)
            sin_fuente = (m > 0) & (np.arange(w)[None, :] + 25 >= w)
            self.assertTrue(np.array_equal(out[sin_fuente], obj[sin_fuente]))
            con_fuente = (m > 0) & (np.arange(w)[None, :] + 25 < w - 6)
            self.assertGreater(float((out[con_fuente] != obj[con_fuente]).any(-1).mean()), 0.9)

    def test_borde_de_la_foto_y_tamanos_impares(self):
        for h, w in ((101, 157), (9, 7), (1, 1)):
            img = paisaje(max(h, 8), max(w, 8), semilla=w)[:h, :w].copy()
            m = np.zeros((h, w), np.float32)
            m[: max(1, h // 3), : max(1, w // 3)] = 1.0  # pegada a la esquina
            for desp in ((w // 2, h // 2), (-3, 1)):
                for sin_costuras in (True, False):
                    out = clonar(img, m, desp, sin_costuras=sin_costuras)
                    self.assertEqual(out.shape, img.shape)
                    self.assertEqual(out.dtype, np.uint8)

    def test_mascara_vacia(self):
        m = np.zeros(self.fondo.shape[:2], np.float32)
        out = clonar(self.fondo, m, (10, 10))
        self.assertTrue(np.array_equal(out, self.fondo))
        self.assertFalse(np.shares_memory(out, self.fondo))


class PruebaTiempo(unittest.TestCase):
    def test_tiempo_12mp(self):
        """Máscara circular del 5 % de una foto de 12 MP (4032x3024)."""
        h, w = 3024, 4032
        rng = np.random.default_rng(0)
        chico = paisaje(756, 1008)
        img = cv2.resize(chico, (w, h), interpolation=cv2.INTER_CUBIC)
        img = np.clip(img.astype(np.int16) + rng.integers(-6, 7, (h, w, 1), dtype=np.int16), 0, 255).astype(np.uint8)
        radio = int(round(np.sqrt(0.05 * h * w / np.pi)))
        obj, m = con_circulo(img, (2000, 1800), radio)
        t0 = time.perf_counter()
        out = rellenar(obj, m)
        t_rellenar = time.perf_counter() - t0
        t0 = time.perf_counter()
        clonar(obj, m, (-1000, 0))
        t_clonar = time.perf_counter() - t0
        print(f"\n  12 MP, máscara del 5 %: rellenar {t_rellenar:.2f} s, clonar {t_clonar:.2f} s",
              file=sys.stderr)
        self.assertEqual(out.shape, obj.shape)
        # Objetivo ≈ 2 s en una PC de escritorio; margen para máquinas más lentas.
        self.assertLess(t_rellenar, 6.0)


if __name__ == "__main__":
    unittest.main()
