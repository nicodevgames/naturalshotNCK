"""Pruebas de rotar, voltear y enderezar (motor sin interfaz)."""

from __future__ import annotations

import itertools
import sys
import time
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from celular_natural.motor.geometria import (  # noqa: E402
    Geometria, aplicar_geometria, destransformar_puntos, detectar_horizonte, matriz_geometria,
    tamano_resultante, transformar_puntos,
)

COMBINACIONES_EXACTAS = [Geometria(k, h, v) for k, h, v in itertools.product(range(4), (False, True), (False, True))]


def imagen(w=320, h=240, semilla=0, minimo=60, maximo=200):
    """Foto de prueba sin negro: degradé + textura, valores entre ``minimo`` y ``maximo``."""
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.dstack([0.2 + 0.6 * xx / w, 0.3 + 0.4 * yy / h, 0.7 - 0.4 * xx / w])
    img += 0.1 * rng.random((h, w, 3), dtype=np.float32)
    img = np.clip(img / 0.9, 0, 1)
    return (minimo + img * (maximo - minimo)).astype(np.uint8)


def escena_con_lineas(w=1600, h=1000, semilla=0, horizontales=True, verticales=False):
    """Cielo claro, suelo más oscuro y varias líneas rectas (suavizadas)."""
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.dstack([90 + 60 * xx / w, 100 + 40 * yy / h, 140 - 40 * xx / w]) + rng.normal(0, 4, (h, w, 1))
    img[: int(h * 0.45)] += 50  # cielo
    img = np.clip(img, 0, 255).astype(np.uint8)
    if horizontales:
        for i, y in enumerate((150, 300, 600, 720, 850)):
            cv2.line(img, (0, y), (w, y), (30 + 20 * i, 40, 60), 3, cv2.LINE_AA)
    if verticales:
        for x in (200, 500, 1100, 1400):
            cv2.line(img, (x, 0), (x, h), (40, 40, 40), 3, cv2.LINE_AA)
    return img


def esperado_numpy(img, g: Geometria):
    salida = img
    if g.voltear_h:
        salida = np.fliplr(salida)
    if g.voltear_v:
        salida = np.flipud(salida)
    return np.rot90(salida, -g.giro90)  # horario


class PruebasGirosYVolteos(unittest.TestCase):
    def test_identidad(self):
        img = imagen()
        for g in (Geometria(), Geometria(giro90=4), Geometria(enderezar=1e-6),
                  Geometria(giro90=2, voltear_h=True, voltear_v=True)):
            with self.subTest(g=g):
                self.assertTrue(g.es_identidad())
                salida = aplicar_geometria(img, g)
                self.assertTrue(np.array_equal(salida, img))
                self.assertFalse(np.shares_memory(salida, img), "debe devolver una copia")
        self.assertFalse(Geometria(giro90=1).es_identidad())
        self.assertFalse(Geometria(voltear_v=True).es_identidad())
        self.assertFalse(Geometria(enderezar=0.5).es_identidad())

    def test_giros_y_volteos_exactos(self):
        rgb = imagen(37, 23)
        alfa = rgb[..., 0].copy()
        mascara = rgb[..., 1].astype(np.float32) / 255.0
        no_contiguo = rgb[:, ::2]  # pasa por el camino de NumPy
        for g in COMBINACIONES_EXACTAS:
            for nombre, img in (("rgb", rgb), ("alfa", alfa), ("mascara", mascara), ("vista", no_contiguo)):
                with self.subTest(g=g, img=nombre):
                    salida = aplicar_geometria(img, g)
                    self.assertTrue(np.array_equal(salida, esperado_numpy(img, g)))
                    self.assertEqual(salida.dtype, img.dtype)
                    self.assertTrue(salida.flags.c_contiguous)

    def test_giro_horario(self):
        img = imagen(5, 3)
        h = img.shape[0]
        salida = aplicar_geometria(img, Geometria(giro90=1))
        self.assertEqual(salida.shape[:2], (5, 3))
        for r, c in itertools.product(range(5), range(3)):
            self.assertTrue(np.array_equal(salida[r, c], img[h - 1 - c, r]))
        # La esquina superior izquierda pasa a la superior derecha.
        self.assertTrue(np.array_equal(salida[0, -1], img[0, 0]))

    def test_cuatro_giros_son_identidad(self):
        img = imagen(41, 29)
        g = Geometria()
        salida = img
        for _ in range(4):
            salida = aplicar_geometria(salida, Geometria(giro90=1))
            g = g.girada(1)
        self.assertTrue(np.array_equal(salida, img))
        self.assertTrue(g.es_identidad())
        self.assertTrue(np.array_equal(aplicar_geometria(img, Geometria(giro90=-1)),
                                       aplicar_geometria(img, Geometria(giro90=3))))

    def test_tamano_resultante(self):
        img = imagen(64, 40)
        geometrias = COMBINACIONES_EXACTAS + [
            Geometria(1, enderezar=4.0), Geometria(0, True, enderezar=-7.5),
            Geometria(3, enderezar=12.0, recortar_bordes=False), Geometria(2, enderezar=-15.0),
        ]
        for g in geometrias:
            with self.subTest(g=g):
                salida = aplicar_geometria(img, g)
                self.assertEqual(tamano_resultante(64, 40, g), (salida.shape[1], salida.shape[0]))
        self.assertEqual(tamano_resultante(4032, 3024, Geometria(giro90=1)), (3024, 4032))
        self.assertEqual(tamano_resultante(4032, 3024, Geometria(enderezar=4, recortar_bordes=False)), (4032, 3024))

    def test_no_modifica_la_entrada_y_es_determinista(self):
        img = imagen(90, 60)
        mascara = img[..., 0].astype(np.float32) / 255.0
        copia, copia_m = img.copy(), mascara.copy()
        for g in (Geometria(1, True), Geometria(enderezar=3.3), Geometria(2, False, True, -6.0, False)):
            with self.subTest(g=g):
                a = aplicar_geometria(img, g)
                b = aplicar_geometria(img, g)
                self.assertTrue(np.array_equal(a, b))
                self.assertTrue(np.array_equal(aplicar_geometria(mascara, g), aplicar_geometria(mascara, g)))
                self.assertTrue(np.array_equal(img, copia))
                self.assertTrue(np.array_equal(mascara, copia_m))

    def test_botones_de_pantalla(self):
        """``volteada`` y ``girada`` actúan sobre lo que se ve, con cualquier giro previo."""
        img = imagen(48, 30)
        for g in COMBINACIONES_EXACTAS:
            with self.subTest(g=g):
                base = aplicar_geometria(img, g)
                self.assertTrue(np.array_equal(aplicar_geometria(img, g.volteada(True)), base[:, ::-1]))
                self.assertTrue(np.array_equal(aplicar_geometria(img, g.volteada(False)), base[::-1]))
                self.assertTrue(np.array_equal(aplicar_geometria(img, g.girada(1)), np.rot90(base, -1)))
                self.assertTrue(np.array_equal(aplicar_geometria(img, g.girada(-1)), np.rot90(base, 1)))
        # Con enderezado: el espejo invierte el sentido del giro fino.
        img = imagen(300, 200)
        for g in (Geometria(enderezar=5.0), Geometria(giro90=1, enderezar=-3.0)):
            with self.subTest(g=g):
                base = aplicar_geometria(img, g).astype(np.float32)
                espejo = aplicar_geometria(img, g.volteada(True)).astype(np.float32)
                girada = aplicar_geometria(img, g.girada(1)).astype(np.float32)
                self.assertEqual(espejo.shape, base.shape)
                self.assertLess(float(np.abs(espejo - base[:, ::-1]).mean()), 0.5)
                self.assertLess(float(np.abs(girada - np.rot90(base, -1)).mean()), 0.5)

    def test_borde_invalido(self):
        with self.assertRaises(ValueError):
            aplicar_geometria(imagen(10, 10), Geometria(enderezar=3), borde="negro")


class PruebasEnderezar(unittest.TestCase):
    ANGULOS = (0.3, 4.0, -7.3, 15.0, -15.0, 33.0)
    TAMANOS = ((320, 240), (240, 320), (257, 257), (500, 120))

    def test_recorte_sin_esquinas_vacias(self):
        for (w, h), angulo in itertools.product(self.TAMANOS, self.ANGULOS):
            with self.subTest(w=w, h=h, angulo=angulo):
                img = imagen(w, h, minimo=60, maximo=200)
                g = Geometria(enderezar=angulo)
                # 1) Las cuatro esquinas del resultado caen dentro de la original.
                esquinas = destransformar_puntos([(0, 0), (1, 0), (0, 1), (1, 1)], g, w, h)
                self.assertTrue(np.all(esquinas >= -1e-9) and np.all(esquinas <= 1 + 1e-9), esquinas)
                # 2) Píxel a píxel: con relleno negro y vecino más cercano, ningún
                #    píxel del resultado sale del relleno.
                m = matriz_geometria(g, w, h)
                a_cv = np.array([[1, 0, -0.5], [0, 1, -0.5], [0, 0, 1.0]])
                inversa = a_cv @ np.linalg.inv(m) @ np.linalg.inv(a_cv)
                w2, h2 = tamano_resultante(w, h, g)
                control = cv2.warpAffine(img, inversa[:2], (w2, h2), flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP,
                                         borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
                self.assertGreaterEqual(int(control.min()), 60)
                # 3) La salida real (Lanczos) tampoco tiene relleno ni esquinas negras.
                salida = aplicar_geometria(img, g)
                self.assertEqual(salida.shape, (h2, w2, 3))
                self.assertGreaterEqual(int(salida.min()), 50)
                for esquina in (salida[:3, :3], salida[:3, -3:], salida[-3:, :3], salida[-3:, -3:]):
                    self.assertGreaterEqual(int(esquina.min()), 50)

    def test_sin_recorte_si_deja_relleno(self):
        """Control de la prueba anterior: sin recorte y con borde transparente, las esquinas quedan en 0."""
        img = imagen(320, 240)
        g = Geometria(enderezar=6.0, recortar_bordes=False)
        transparente = aplicar_geometria(img, g, borde="transparente")
        self.assertEqual(transparente.shape, img.shape)
        self.assertEqual(int(transparente[0, 0].max()), 0)
        self.assertEqual(int(transparente[-1, -1].max()), 0)
        reflejo = aplicar_geometria(img, g)  # por defecto, reflejo
        self.assertGreaterEqual(int(reflejo.min()), 50)
        # Receta para la transparencia: pasar un alfa lleno por la misma geometría.
        alfa = aplicar_geometria(np.full((240, 320), 255, np.uint8), g, borde="transparente")
        self.assertEqual(int(alfa[0, 0]), 0)
        self.assertEqual(int(alfa[120, 160]), 255)

    def test_recorte_mantiene_la_proporcion_y_es_el_mayor(self):
        for (w, h), angulo, giro in itertools.product(self.TAMANOS + ((4032, 3024),), self.ANGULOS, (0, 1)):
            with self.subTest(w=w, h=h, angulo=angulo, giro=giro):
                a, b = (h, w) if giro % 2 else (w, h)
                w2, h2 = tamano_resultante(w, h, Geometria(giro90=giro, enderezar=angulo))
                self.assertLessEqual(w2, a)
                self.assertLessEqual(h2, b)
                # Misma proporción con error menor a un píxel.
                self.assertLess(abs(w2 * b - h2 * a), max(a, b))
                # El mayor posible: el factor teórico, menos el redondeo.
                t = np.radians(angulo)
                c, s = abs(np.cos(t)), abs(np.sin(t))
                k = min(a / (a * c + b * s), b / (a * s + b * c))
                self.assertGreaterEqual(max(w2, h2), int(k * max(a, b)) - 1)
                self.assertGreaterEqual(min(w2, h2), int(k * min(a, b)) - 1)

    def test_angulo_positivo_es_horario(self):
        # Una línea horizontal que pasa por el centro, girada en sentido horario,
        # baja hacia la derecha.
        img = np.full((201, 401, 3), 200, np.uint8)
        img[99:102] = 0
        salida = aplicar_geometria(img, Geometria(enderezar=5.0))
        h2, w2 = salida.shape[:2]
        filas = [int(np.argmin(salida[:, x, 0])) for x in (w2 // 4, 3 * w2 // 4)]
        self.assertGreater(filas[1], filas[0])
        self.assertAlmostEqual(np.degrees(np.arctan2(filas[1] - filas[0], w2 // 2)), 5.0, delta=0.5)

    def test_alfa_y_mascaras_con_la_misma_forma(self):
        rgb = imagen(160, 100)
        alfa = rgb[..., 0].copy()
        mascara = np.zeros((100, 160), np.float32)
        mascara[30:70, 40:120] = 1.0  # bordes duros: Lanczos rebota
        un_canal = mascara[..., None].copy()
        for g in (Geometria(1, True, enderezar=4.0), Geometria(enderezar=-9.0, recortar_bordes=False),
                  Geometria(3, False, True)):
            with self.subTest(g=g):
                r = aplicar_geometria(rgb, g)
                a = aplicar_geometria(alfa, g)
                m = aplicar_geometria(mascara, g)
                u = aplicar_geometria(un_canal, g)
                self.assertEqual(a.shape, r.shape[:2])
                self.assertEqual(m.shape, r.shape[:2])
                self.assertEqual(u.shape, r.shape[:2] + (1,))
                self.assertEqual((a.dtype, m.dtype, u.dtype), (np.uint8, np.float32, np.float32))
                self.assertGreaterEqual(float(m.min()), 0.0)
                self.assertLessEqual(float(m.max()), 1.0)
                m_lineal = aplicar_geometria(mascara, g, interpolacion=cv2.INTER_LINEAR)
                self.assertEqual(m_lineal.shape, m.shape)

    def test_tiempo_12_mp(self):
        img = imagen(4032, 3024)
        alfa = img[..., 0].copy()
        tiempos = {}
        for nombre, f in (
            ("enderezar 4 grados RGB (Lanczos)", lambda: aplicar_geometria(img, Geometria(enderezar=4.0))),
            ("enderezar 4 grados RGB (cubica)", lambda: aplicar_geometria(img, Geometria(enderezar=4.0), cv2.INTER_CUBIC)),
            ("enderezar 4 grados alfa (Lanczos)", lambda: aplicar_geometria(alfa, Geometria(enderezar=4.0))),
            ("girar 90 + voltear RGB", lambda: aplicar_geometria(img, Geometria(1, True))),
            ("detectar_horizonte", lambda: detectar_horizonte(img)),
        ):
            f()  # calentamiento
            inicio = time.perf_counter()
            f()
            tiempos[nombre] = time.perf_counter() - inicio
        print("\n" + "\n".join(f"    12 MP, {k}: {v * 1000:.0f} ms" for k, v in tiempos.items()), file=sys.stderr)
        self.assertLess(tiempos["enderezar 4 grados RGB (Lanczos)"], 3.0)


class PruebasPuntos(unittest.TestCase):
    def test_ida_y_vuelta(self):
        rng = np.random.default_rng(3)
        puntos = rng.uniform(-0.2, 1.2, (200, 2))
        geometrias = COMBINACIONES_EXACTAS + [
            Geometria(k, h, v, ang, rec)
            for k, h, v, ang, rec in itertools.product(range(4), (False, True), (False, True), (-13.7, 2.5), (True, False))
        ]
        for (w, h), g in itertools.product(((4032, 3024), (333, 500), (64, 64)), geometrias):
            with self.subTest(w=w, h=h, g=g):
                ida = transformar_puntos(puntos, g, w, h)
                self.assertEqual(ida.shape, puntos.shape)
                self.assertTrue(np.allclose(destransformar_puntos(ida, g, w, h), puntos, rtol=0, atol=1e-6))
                self.assertTrue(np.allclose(transformar_puntos(destransformar_puntos(puntos, g, w, h), g, w, h),
                                            puntos, rtol=0, atol=1e-6))
        # Un punto suelto y una tupla de tuplas (como guarda ``Zona``) también sirven.
        self.assertEqual(transformar_puntos((0.25, 0.5), Geometria(giro90=1), 100, 50).shape, (2,))
        self.assertTrue(np.allclose(transformar_puntos(((0.25, 0.5),), Geometria(giro90=1), 100, 50), [[0.5, 0.25]]))

    def test_puntos_caen_en_el_mismo_pixel_sin_interpolar(self):
        w, h = 37, 23
        marcas = ((0, 0), (5, 30), (22, 36), (11, 17), (22, 0))  # (fila, columna)
        for g in COMBINACIONES_EXACTAS:
            with self.subTest(g=g):
                img = np.full((h, w, 3), 128, np.uint8)
                for n, (r, c) in enumerate(marcas):
                    img[r, c] = (255, 10 * n, 0)
                salida = aplicar_geometria(img, g)
                h2, w2 = salida.shape[:2]
                for n, (r, c) in enumerate(marcas):
                    u, v = transformar_puntos(((c + 0.5) / w, (r + 0.5) / h), g, w, h)
                    x, y = int(np.floor(u * w2)), int(np.floor(v * h2))
                    self.assertTrue(np.array_equal(salida[y, x], (255, 10 * n, 0)), (n, x, y))

    def test_puntos_coinciden_con_el_enderezado(self):
        """Un bloque rojo marcado en la original cae donde dice ``transformar_puntos``
        (centroide con precisión de una décima de píxel)."""
        w, h = 300, 200
        centros = ((60, 50), (150, 100), (230, 140))  # (x, y) en píxeles, centro de un bloque 9x9
        geometrias = [Geometria(k, hh, vv, ang, rec)
                      for k, hh, vv in ((0, False, False), (1, True, False), (2, False, True), (3, False, False))
                      for ang, rec in ((4.0, True), (-11.0, True), (7.0, False))]
        for g in geometrias:
            for cx, cy in centros:
                with self.subTest(g=g, centro=(cx, cy)):
                    img = np.full((h, w, 3), 100, np.uint8)
                    img[cy - 4:cy + 5, cx - 4:cx + 5] = (250, 100, 100)
                    salida = aplicar_geometria(img, g).astype(np.float64)
                    h2, w2 = salida.shape[:2]
                    u, v = transformar_puntos(((cx + 0.5) / w, (cy + 0.5) / h), g, w, h)
                    px, py = u * w2, v * h2
                    if not (6 < px < w2 - 6 and 6 < py < h2 - 6):
                        continue  # el bloque quedó en la parte recortada
                    rojo = np.clip(salida[..., 0] - 100.0, 0, None)
                    yy, xx = np.mgrid[0:h2, 0:w2] + 0.5
                    cerca = (np.abs(xx - px) < 12) & (np.abs(yy - py) < 12)
                    peso = rojo * cerca
                    self.assertGreater(float(peso.sum()), 0)
                    self.assertAlmostEqual(float((peso * xx).sum() / peso.sum()), px, delta=0.1)
                    self.assertAlmostEqual(float((peso * yy).sum() / peso.sum()), py, delta=0.1)
                    # Y el píxel donde cae el punto es rojo.
                    self.assertGreater(float(salida[int(py), int(px), 0]), 220)

    def test_matriz_igual_a_puntos(self):
        g = Geometria(1, True, False, 3.0)
        m = matriz_geometria(g, 400, 300)
        w2, h2 = tamano_resultante(400, 300, g)
        p = np.array([123.25, 77.5])
        esperado = transformar_puntos(p / (400, 300), g, 400, 300) * (w2, h2)
        self.assertTrue(np.allclose(m[:2, :2] @ p + m[:2, 2], esperado, atol=1e-9))


class PruebasHorizonte(unittest.TestCase):
    def test_recupera_un_angulo_conocido(self):
        """Convención: escena girada a grados en sentido horario -> devuelve -a (lo que hay que enderezar)."""
        for angulo, semilla in itertools.product((4.0, -4.0, 1.3, -9.0), (0, 1)):
            with self.subTest(angulo=angulo, semilla=semilla):
                torcida = aplicar_geometria(escena_con_lineas(semilla=semilla), Geometria(enderezar=angulo))
                estimado = detectar_horizonte(torcida)
                self.assertIsNotNone(estimado)
                self.assertAlmostEqual(estimado, -angulo, delta=0.5)
                # Aplicar lo que propone deja la foto nivelada.
                nivelada = aplicar_geometria(torcida, Geometria(enderezar=estimado))
                self.assertAlmostEqual(detectar_horizonte(nivelada), 0.0, delta=0.5)

    def test_rotacion_de_opencv(self):
        # cv2.getRotationMatrix2D con +4° gira en sentido antihorario: hay que enderezar +4°.
        grande = escena_con_lineas(2000, 1400)
        rot = cv2.getRotationMatrix2D((1000, 700), 4.0, 1.0)
        girada = cv2.warpAffine(grande, rot, (2000, 1400), flags=cv2.INTER_CUBIC)
        centro = girada[300:1100, 300:1700]  # sin las esquinas vacías
        self.assertAlmostEqual(detectar_horizonte(centro), 4.0, delta=0.5)

    def test_nivelada(self):
        self.assertAlmostEqual(detectar_horizonte(escena_con_lineas()), 0.0, delta=0.2)

    def test_solo_verticales(self):
        escena = escena_con_lineas(horizontales=False, verticales=True)
        escena[:] = 150  # sin el horizonte del cielo
        for x in (200, 500, 1100, 1400):
            cv2.line(escena, (x, 0), (x, 1000), (40, 40, 40), 3, cv2.LINE_AA)
        torcida = aplicar_geometria(escena, Geometria(enderezar=-5.0))
        self.assertAlmostEqual(detectar_horizonte(torcida), 5.0, delta=0.5)

    def test_ruido_sin_lineas(self):
        for semilla in range(3):
            rng = np.random.default_rng(semilla)
            uniforme = rng.integers(0, 256, (900, 1200, 3), dtype=np.uint8)
            gaussiano = np.clip(rng.normal(128, 30, (900, 1200, 3)), 0, 255).astype(np.uint8)
            manchas = cv2.resize(rng.integers(0, 256, (30, 40, 3), dtype=np.uint8), (1200, 900),
                                 interpolation=cv2.INTER_CUBIC)
            for nombre, img in (("uniforme", uniforme), ("gaussiano", gaussiano), ("manchas", manchas)):
                with self.subTest(semilla=semilla, ruido=nombre):
                    self.assertIsNone(detectar_horizonte(img))
        self.assertIsNone(detectar_horizonte(np.full((600, 800, 3), 128, np.uint8)))  # lisa
        self.assertIsNone(detectar_horizonte(np.zeros((20, 30, 3), np.uint8)))  # diminuta

    def test_limite_y_tipos(self):
        torcida = aplicar_geometria(escena_con_lineas(), Geometria(enderezar=25.0))
        estimado = detectar_horizonte(torcida)
        self.assertTrue(estimado is None or abs(estimado) <= 15.0, estimado)
        # Acepta flotantes 0..1 y escala de grises.
        torcida = aplicar_geometria(escena_con_lineas(), Geometria(enderezar=3.0))
        self.assertAlmostEqual(detectar_horizonte(torcida.astype(np.float32) / 255.0), -3.0, delta=0.5)
        gris = cv2.cvtColor(torcida, cv2.COLOR_RGB2GRAY)
        self.assertAlmostEqual(detectar_horizonte(gris), -3.0, delta=0.5)


if __name__ == "__main__":
    unittest.main()
