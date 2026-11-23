"""Pruebas de la selección automática: cielo, piel, recorte con GrabCut e historial."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from celular_natural.motor.seleccion_auto import (  # noqa: E402
    codificar_mascara, decodificar_mascara, mascara_cielo, mascara_piel, recortar_objeto,
)


# ---------------------------------------------------------------------------
# Escenas sintéticas
# ---------------------------------------------------------------------------

def _textura(h, w, rng, desvio=35.0, color=10.0):
    """Textura fuerte (suelo, follaje): ruido de luminancia + algo de color, apenas suavizado."""
    t = rng.normal(0, desvio, (h, w, 1)) + rng.normal(0, color, (h, w, 3))
    return cv2.GaussianBlur(t.astype(np.float32), (0, 0), 0.8)


def escena_cielo(w=640, h=480, semilla=0, nublado=False):
    """Cielo degradado arriba, suelo con textura, un edificio que entra en el cielo y
    un objeto azul liso abajo (no toca el borde superior).

    Devuelve (imagen uint8, cielo verdadero, objeto azul).
    """
    rng = np.random.default_rng(semilla)
    hz = int(0.45 * h)
    if nublado:
        arriba, abajo = np.array([200, 204, 210.0]), np.array([236, 237, 239.0])
    else:
        arriba, abajo = np.array([55, 105, 195.0]), np.array([165, 200, 235.0])
    t = np.linspace(0, 1, h)[:, None, None] / 0.45
    img = np.broadcast_to(arriba * (1 - t) + abajo * t, (h, w, 3)).copy()
    verdad = np.zeros((h, w), bool)
    verdad[:hz] = True
    tex = _textura(h, w, rng)
    img[hz:] = np.array([105, 95, 65.0]) + tex[hz:]
    bx0, bx1, by0 = int(0.62 * w), int(0.75 * w), int(0.2 * h)
    img[by0:hz, bx0:bx1] = np.array([90, 85, 80.0]) + 0.8 * tex[by0:hz, bx0:bx1]
    verdad[by0:hz, bx0:bx1] = False
    azul = np.zeros((h, w), np.uint8)
    cv2.ellipse(azul, (int(0.3 * w), int(0.78 * h)), (int(0.1 * w), int(0.06 * h)), 0, 0, 360, 1, -1)
    img[azul > 0] = np.array([50, 95, 200.0])
    img += rng.normal(0, 1.5, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8), verdad, azul > 0


def escena_follaje(w=640, h=480, semilla=1):
    """Sin cielo: todo follaje con textura."""
    rng = np.random.default_rng(semilla)
    img = np.array([60, 120, 50.0]) + _textura(h, w, rng, desvio=40.0, color=12.0)
    return np.clip(img, 0, 255).astype(np.uint8)


def escena_pared(w=640, h=480, semilla=2):
    """Sin cielo: pared lisa marrón arriba (toca el borde) y suelo con textura abajo."""
    rng = np.random.default_rng(semilla)
    img = np.empty((h, w, 3))
    img[:] = (150, 105, 70)
    img[h // 2:] += _textura(h, w, rng)[h // 2:]
    img += rng.normal(0, 1.5, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


TONOS_PIEL = [(224, 172, 140), (198, 134, 94), (141, 85, 60), (250, 205, 180), (95, 60, 42)]


def escena_piel(fondo, w=640, h=480, semilla=3, piel=True):
    """Manchas elípticas de distintos tonos de piel (o grises si ``piel=False``) sobre un fondo liso."""
    rng = np.random.default_rng(semilla)
    img = np.empty((h, w, 3))
    img[:] = fondo
    img += rng.normal(0, 4, img.shape)
    verdad = np.zeros((h, w), np.uint8)
    for i, (cx, tono) in enumerate(zip(np.linspace(0.12, 0.88, len(TONOS_PIEL)), TONOS_PIEL)):
        m = np.zeros((h, w), np.uint8)
        centro = (int(cx * w), int((0.35 + 0.3 * (i % 2)) * h))
        cv2.ellipse(m, centro, (int(0.06 * w), int(0.12 * h)), 15 * i, 0, 360, 1, -1)
        color = np.array(tono, float) if piel else np.full(3, float(np.mean(tono)))
        img[m > 0] = color + rng.normal(0, 3, (int(m.sum()), 3))
        verdad |= m
    return np.clip(img, 0, 255).astype(np.uint8), verdad > 0


def escena_objeto(w=640, h=480, semilla=4):
    """Objeto naranja (elipse + cabeza + brazo) sobre un fondo de bloques fríos con textura."""
    rng = np.random.default_rng(semilla)
    paleta = np.array([[70, 110, 80], [60, 90, 120], [120, 125, 130], [40, 70, 60],
                       [90, 140, 150], [150, 150, 140]], np.float32)
    bloque = max(4, round(16 * w / 640))
    bloques = paleta[rng.integers(0, len(paleta), (h // bloque + 1, w // bloque + 1))]
    fondo = cv2.resize(bloques, (w, h), interpolation=cv2.INTER_NEAREST)
    fondo += cv2.GaussianBlur(rng.normal(0, 18, (h, w)).astype(np.float32), (0, 0), 1.0)[..., None]
    verdad = np.zeros((h, w), np.uint8)
    cx, cy = int(0.5 * w), int(0.52 * h)
    cv2.ellipse(verdad, (cx, cy), (int(0.16 * w), int(0.22 * h)), 10, 0, 360, 1, -1)
    cv2.circle(verdad, (cx + int(0.08 * w), cy - int(0.2 * h)), int(0.09 * h), 1, -1)
    cv2.rectangle(verdad, (cx - int(0.2 * w), cy + int(0.05 * h)), (cx - int(0.1 * w), cy + int(0.12 * h)), 1, -1)
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    objeto = np.array([215, 90, 40], np.float32) * (0.85 + 0.25 * (1 - yy))
    objeto = objeto + rng.normal(0, 5, (h, w, 3)).astype(np.float32)
    img = np.where(verdad[..., None] > 0, objeto, fondo)
    img = cv2.GaussianBlur(img, (0, 0), 0.6)  # borde antialias, como en una foto
    return np.clip(img, 0, 255).astype(np.uint8), verdad > 0


def rect_holgado(verdad, margen=0.1):
    ys, xs = np.nonzero(verdad)
    h, w = verdad.shape
    x0, x1, y0, y1 = xs.min() / w, (xs.max() + 1) / w, ys.min() / h, (ys.max() + 1) / h
    mx, my = margen * (x1 - x0), margen * (y1 - y0)
    return (x0 - mx, y0 - my, x1 + mx, y1 + my)


def lazo_aproximado(verdad):
    """Simula un lazo dibujado a mano: polígono grosero alrededor del objeto (IoU ≈ 0,84)."""
    v8 = verdad.astype(np.uint8)
    k = max(3, round(25 * verdad.shape[1] / 640)) | 1
    contornos, _ = cv2.findContours(cv2.dilate(v8, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))),
                                    cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    poligono = cv2.approxPolyDP(max(contornos, key=cv2.contourArea), 12 * verdad.shape[1] / 640, True)
    lazo = np.zeros_like(v8)
    cv2.fillPoly(lazo, [poligono], 1)
    return lazo


def iou(m, verdad):
    b = m >= 0.5
    return float((b & verdad).sum()) / max(1, int((b | verdad).sum()))


def erosion(binaria, r):
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    return cv2.erode(binaria.astype(np.uint8), k) > 0


def reducir(img, w, h):
    return cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)


# ---------------------------------------------------------------------------
# Pruebas
# ---------------------------------------------------------------------------

class PruebasCielo(unittest.TestCase):
    def test_cielo_arriba_suelo_y_objeto_azul_no(self):
        for nublado in (False, True):
            with self.subTest(nublado=nublado):
                img, verdad, azul = escena_cielo(nublado=nublado)
                m = mascara_cielo(img)
                self.assertEqual(m.shape, verdad.shape)
                self.assertEqual(m.dtype, np.float32)
                self.assertGreaterEqual(float(m.min()), 0.0)
                self.assertLessEqual(float(m.max()), 1.0)
                self.assertGreater(float(m[erosion(verdad, 4)].mean()), 0.97, "el cielo tiene que detectarse")
                self.assertLess(float(m[erosion(~verdad, 4)].mean()), 0.01, "el suelo y el edificio no son cielo")
                self.assertLess(float(m[azul].max()), 0.05, "un objeto azul que no toca arriba no es cielo")
                self.assertGreater(iou(m, verdad), 0.95)

    def test_borde_suave_pegado_al_contorno(self):
        img, verdad, _ = escena_cielo(1280, 960)
        m = mascara_cielo(img)
        v8 = verdad.astype(np.uint8)
        k = np.ones((13, 13), np.uint8)
        banda = (cv2.dilate(v8, k) - cv2.erode(v8, k)) > 0  # ±6 px alrededor del contorno real
        self.assertLess(float(np.abs(m - verdad)[banda].mean()), 0.08)
        # Suave: hay valores intermedios en el borde, no un escalón binario.
        intermedios = (m[banda] > 0.05) & (m[banda] < 0.95)
        self.assertGreater(int(intermedios.sum()), 0)

    def test_sin_cielo_mascara_casi_vacia(self):
        for nombre, img in (("follaje", escena_follaje()), ("pared lisa marrón", escena_pared())):
            with self.subTest(escena=nombre):
                m = mascara_cielo(img)
                self.assertLess(float(m.mean()), 0.005)
                self.assertLess(float(m.max()), 0.1)

    def test_solo_objeto_azul_abajo(self):
        rng = np.random.default_rng(5)
        img = np.clip(np.array([110, 100, 70.0]) + _textura(480, 640, rng), 0, 255)
        img[250:400, 150:450] = (60, 110, 200)  # azul liso, lejos del borde superior
        m = mascara_cielo(img.astype(np.uint8))
        self.assertLess(float(m.max()), 0.05)


class PruebasPiel(unittest.TestCase):
    def test_piel_sobre_verde_azul_y_gris(self):
        for fondo in ((50, 140, 70), (40, 80, 170), (128, 128, 128)):
            with self.subTest(fondo=fondo):
                img, verdad = escena_piel(fondo)
                m = mascara_piel(img)
                self.assertEqual(m.shape, verdad.shape)
                self.assertEqual(m.dtype, np.float32)
                self.assertGreater(float(m[erosion(verdad, 3)].mean()), 0.9, "las manchas de piel se detectan")
                self.assertLess(float(m[erosion(~verdad, 6)].mean()), 0.01, "el fondo no es piel")
                self.assertGreater(iou(m, verdad), 0.9)

    def test_gris_sin_piel(self):
        img, _ = escena_piel((128, 128, 128), piel=False)
        m = mascara_piel(img)
        self.assertLess(float(m.max()), 0.05)

    def test_fondos_lisos_no_son_piel(self):
        for fondo in ((50, 140, 70), (40, 80, 170), (128, 128, 128), (235, 235, 235), (20, 20, 20)):
            with self.subTest(fondo=fondo):
                img = np.full((240, 320, 3), fondo, np.uint8)
                self.assertLess(float(mascara_piel(img).max()), 0.01)


class PruebasRecorte(unittest.TestCase):
    def setUp(self):
        self.img, self.verdad = escena_objeto()

    def test_rectangulo_holgado(self):
        m = recortar_objeto(self.img, rect_holgado(self.verdad))
        self.assertEqual(m.shape, self.verdad.shape)
        self.assertEqual(m.dtype, np.float32)
        self.assertGreater(iou(m, self.verdad), 0.85)
        # Fuera del rectángulo (con su margen) no hay nada.
        self.assertEqual(float(m[:5].max()), 0.0)

    def test_mascara_inicial_aproximada(self):
        lazo = lazo_aproximado(self.verdad)
        self.assertLess(iou(lazo.astype(np.float32), self.verdad), 0.9)  # de verdad es grosero
        casos = {
            "lazo uint8": lazo,
            "lazo 0..255": lazo * 255,
            "lazo bool a otra resolución": cv2.resize(lazo, (160, 120), interpolation=cv2.INTER_NEAREST) > 0,
            # Lazo corrido que corta el objeto de un lado: la banda indecisa lo recupera.
            "lazo corrido": np.roll(cv2.dilate(self.verdad.astype(np.uint8), np.ones((9, 9), np.uint8)), 12, axis=1),
        }
        for nombre, inicial in casos.items():
            with self.subTest(caso=nombre):
                self.assertGreater(iou(recortar_objeto(self.img, inicial), self.verdad), 0.85)

    def test_repetible(self):
        rect = rect_holgado(self.verdad)
        self.assertTrue(np.array_equal(recortar_objeto(self.img, rect), recortar_objeto(self.img, rect)))

    def test_casos_limite(self):
        h, w = self.verdad.shape
        self.assertEqual(float(recortar_objeto(self.img, np.zeros((10, 10))).max()), 0.0)
        self.assertEqual(float(recortar_objeto(self.img, (0.3, 0.3, 0.3, 0.6)).max()), 0.0)
        for inicial in ((0.0, 0.0, 1.0, 1.0), (0.5, 0.5, 0.502, 0.503), [0.9, 0.9, 0.1, 0.1]):
            with self.subTest(inicial=inicial):
                m = recortar_objeto(self.img, inicial)
                self.assertEqual(m.shape, (h, w))
                self.assertTrue(np.isfinite(m).all())
                self.assertGreaterEqual(float(m.min()), 0.0)
                self.assertLessEqual(float(m.max()), 1.0)


class PruebasHistorial(unittest.TestCase):
    def mascara_prueba(self, h, w):
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        suave = np.exp(-(((xx - 0.4 * w) / (0.2 * w)) ** 2 + ((yy - 0.5 * h) / (0.25 * h)) ** 2))
        dura = np.zeros((h, w), np.float32)
        cv2.circle(dura, (int(0.75 * w), int(0.4 * h)), int(0.15 * h), 1.0, -1)
        return np.clip(np.maximum(suave, dura), 0, 1).astype(np.float32)

    def test_ida_y_vuelta(self):
        for h, w in ((600, 800), (3024, 4032), (1200, 900)):
            with self.subTest(tamano=(h, w)):
                m = self.mascara_prueba(h, w)
                datos = codificar_mascara(m)
                self.assertIsInstance(datos, bytes)
                r = decodificar_mascara(datos, h, w)
                self.assertEqual(r.shape, (h, w))
                self.assertEqual(r.dtype, np.float32)
                self.assertLess(float(np.abs(r - m).mean()), 0.01)

    def test_compacta_y_comparable(self):
        m = self.mascara_prueba(3024, 4032)
        datos = codificar_mascara(m)
        self.assertLess(len(datos), 200_000, "a lo sumo unos KB, no 12 MP")
        self.assertEqual(datos, codificar_mascara(m.copy()), "la misma máscara da los mismos bytes")
        self.assertNotEqual(datos, codificar_mascara(1.0 - m))
        img = cv2.imdecode(np.frombuffer(datos, np.uint8), cv2.IMREAD_UNCHANGED)
        self.assertLessEqual(max(img.shape), 1024)
        # A otra resolución y aspecto: reescala con interpolación lineal.
        r = decodificar_mascara(datos, 300, 400)
        self.assertLess(float(np.abs(r - reducir(m, 400, 300)).mean()), 0.01)

    def test_datos_invalidos(self):
        with self.assertRaises(ValueError):
            decodificar_mascara(b"no es un png", 10, 10)
        with self.assertRaises(ValueError):
            codificar_mascara(np.zeros((4, 4, 3), np.float32))


class PruebasGenerales(unittest.TestCase):
    def test_independiente_de_la_resolucion(self):
        grande_cielo, _, _ = escena_cielo(1600, 1200)
        grande_piel, _ = escena_piel((50, 140, 70), 1600, 1200)
        grande_obj, verdad = escena_objeto(1600, 1200)
        rect = rect_holgado(verdad)
        casos = {
            "cielo": (grande_cielo, mascara_cielo),
            "piel": (grande_piel, mascara_piel),
            "recorte": (grande_obj, lambda img: recortar_objeto(img, rect)),
        }
        for nombre, (img, fn) in casos.items():
            with self.subTest(funcion=nombre):
                m_grande = fn(img)
                m_chica = fn(reducir(img, 800, 600))
                diferencia = np.abs(reducir(m_grande, 800, 600) - m_chica).mean()
                self.assertLess(float(diferencia), 0.02)

    def test_entrada_no_modificada(self):
        cielo, _, _ = escena_cielo(320, 240)
        piel, _ = escena_piel((40, 80, 170), 320, 240)
        obj, verdad = escena_objeto(320, 240)
        lazo = lazo_aproximado(verdad).astype(np.float32)
        for img, fn in ((cielo, mascara_cielo), (piel, mascara_piel),
                        (obj, lambda x: recortar_objeto(x, rect_holgado(verdad))),
                        (obj, lambda x: recortar_objeto(x, lazo))):
            for entrada in (img, img.astype(np.float32) / 255.0):
                copia = entrada.copy()
                copia_lazo = lazo.copy()
                fn(entrada)
                self.assertTrue(np.array_equal(entrada, copia))
                self.assertTrue(np.array_equal(lazo, copia_lazo))

    def test_tiempos_12mp(self):
        w, h = 4032, 3024
        cielo, verdad_cielo, _ = escena_cielo(w, h)
        obj, verdad = escena_objeto(w, h)
        lazo = lazo_aproximado(verdad)
        rect = rect_holgado(verdad)
        tiempos = {}

        def medir(nombre, fn):
            t0 = time.perf_counter()
            r = fn()
            tiempos[nombre] = time.perf_counter() - t0
            return r

        m = medir("cielo", lambda: mascara_cielo(cielo))
        self.assertGreater(iou(m, verdad_cielo), 0.95)
        medir("piel", lambda: mascara_piel(cielo))
        m = medir("recorte (rectangulo)", lambda: recortar_objeto(obj, rect))
        iou_rect = iou(m, verdad)
        m = medir("recorte (lazo)", lambda: recortar_objeto(obj, lazo))
        iou_lazo = iou(m, verdad)
        datos = medir("codificar", lambda: codificar_mascara(m))
        medir("decodificar", lambda: decodificar_mascara(datos, h, w))
        print("\n  12 MP: " + ", ".join(f"{k} {v:.2f} s" for k, v in tiempos.items())
              + f" | IoU rect {iou_rect:.3f}, lazo {iou_lazo:.3f}, PNG {len(datos) / 1024:.1f} KB")
        self.assertGreater(iou_rect, 0.85)
        self.assertGreater(iou_lazo, 0.85)
        # Objetivo < ~2 s para el recorte; margen amplio por si la CPU está ocupada.
        self.assertLess(tiempos["recorte (rectangulo)"], 4.0)
        self.assertLess(tiempos["cielo"], 3.0)
        self.assertLess(tiempos["piel"], 3.0)


if __name__ == "__main__":
    unittest.main()
