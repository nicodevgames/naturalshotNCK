"""Pruebas del texto (``motor/texto.py``): familias, antialias, color, alineaciones,
interlineado, espaciado, corte de líneas, negrita y cursiva (de archivo o sintetizadas),
una familia que no existe (vuelve a Arial), escala, contrato con M1 y velocidad.
"""

from __future__ import annotations

import json
import sys
import time
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from celular_natural.motor import texto as modulo_texto  # noqa: E402
from celular_natural.motor.texto import ParamsTexto, familias_disponibles, renderizar_texto  # noqa: E402

HAY_ARIAL = "Arial" in familias_disponibles()


def tinta(rgba: np.ndarray) -> tuple[int, int, int, int]:
    """Caja de la tinta (x0, y0, x1, y1), con x1 e y1 exclusivos."""
    a = rgba[..., 3] > 0
    ys = np.nonzero(a.any(axis=1))[0]
    xs = np.nonzero(a.any(axis=0))[0]
    return int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1


def centro_x_filas(rgba: np.ndarray, y0: int, y1: int) -> float:
    a = rgba[y0:y1, :, 3].astype(np.float64)
    xs = np.arange(a.shape[1]) + 0.5
    return float((a.sum(axis=0) * xs).sum() / a.sum())


class TestFamilias(unittest.TestCase):
    def test_lista_ordenada_de_textos(self):
        fam = familias_disponibles()
        self.assertIsInstance(fam, list)
        self.assertTrue(fam)
        self.assertTrue(all(isinstance(f, str) and f for f in fam))
        self.assertEqual(fam, sorted(fam, key=str.casefold))
        self.assertEqual(len(fam), len({f.casefold() for f in fam}))

    @unittest.skipUnless(HAY_ARIAL, "sin Arial (no es Windows)")
    def test_familias_comunes_de_windows(self):
        fam = familias_disponibles()
        for nombre in ("Arial", "Times New Roman", "Segoe UI"):
            self.assertIn(nombre, fam)


class TestParamsTexto(unittest.TestCase):
    def test_valores_por_defecto(self):
        p = ParamsTexto()
        self.assertEqual((p.contenido, p.fuente, p.tamano, p.color), ("Texto", "Arial", 72.0, (255, 255, 255, 255)))
        self.assertEqual((p.negrita, p.cursiva, p.alineacion), (False, False, "izquierda"))
        self.assertEqual((p.interlineado, p.espaciado, p.ancho_caja), (1.2, 0.0, None))

    def test_ida_y_vuelta_json(self):
        p = ParamsTexto("Hola\nmundo", "Georgia", 40, (10, 20, 30, 200), True, True, "derecha", 1.5, 2.0, 300.0)
        d = json.loads(json.dumps(p.como_dict()))
        q = ParamsTexto.desde_dict(d)
        self.assertEqual(q, p)
        self.assertEqual({p: 1}[q], 1)
        self.assertEqual(ParamsTexto.desde_dict({"contenido": "x", "raro": 1}), ParamsTexto("x"))

    def test_invalidos(self):
        for mal in (dict(contenido=3), dict(fuente=""), dict(tamano=0), dict(color=(1, 2)),
                    dict(negrita=1), dict(alineacion="justificado"), dict(interlineado=0),
                    dict(espaciado=float("inf")), dict(ancho_caja=0), dict(tamano="12")):
            with self.subTest(mal=mal), self.assertRaises(ValueError):
                ParamsTexto(**mal)
        with self.assertRaises(ValueError):
            ParamsTexto.desde_dict([])


@unittest.skipUnless(HAY_ARIAL, "sin Arial (no es Windows)")
class TestRender(unittest.TestCase):
    def test_rgba_antialias_y_color(self):
        im = renderizar_texto(ParamsTexto("Hola", color=(200, 30, 40, 255)))
        self.assertEqual(im.dtype, np.uint8)
        self.assertEqual(im.ndim, 3)
        self.assertEqual(im.shape[2], 4)
        a = im[..., 3]
        self.assertEqual(int(a.max()), 255)
        self.assertGreater(int(((a > 0) & (a < 255)).sum()), 50)
        self.assertTrue((im[a > 0][:, :3] == (200, 30, 40)).all())

    def test_la_tinta_no_toca_el_borde(self):
        for contenido in ("Hola", "jfgyQ|", "Wj\nfgy", "W"):
            for cursiva in (False, True):
                with self.subTest(contenido=contenido, cursiva=cursiva):
                    im = renderizar_texto(ParamsTexto(contenido, cursiva=cursiva, fuente="Impact" if cursiva else "Arial"))
                    x0, y0, x1, y1 = tinta(im)
                    h, w = im.shape[:2]
                    self.assertGreaterEqual(x0, 1)
                    self.assertGreaterEqual(y0, 1)
                    self.assertLessEqual(x1, w - 1)
                    self.assertLessEqual(y1, h - 1)

    def test_la_caja_es_la_del_texto(self):
        im = renderizar_texto(ParamsTexto("Hola mundo", tamano=72))
        x0, y0, x1, y1 = tinta(im)
        h, w = im.shape[:2]
        self.assertLess(w - (x1 - x0), 20)            # margen chico a los costados
        self.assertLess(h, 72 * 1.4)                  # una línea: alto de la fuente, no más

    def test_lineas_e_interlineado(self):
        una = renderizar_texto(ParamsTexto("Hola"))
        tres = renderizar_texto(ParamsTexto("Hola\nHola\nHola"))
        self.assertAlmostEqual(tres.shape[0] - una.shape[0], 2 * 72 * 1.2, delta=3)
        doble = renderizar_texto(ParamsTexto("Hola\nHola\nHola", interlineado=2.0))
        self.assertAlmostEqual(doble.shape[0] - una.shape[0], 2 * 72 * 2.0, delta=3)

    def test_alineaciones(self):
        centros = {}
        for al in ("izquierda", "centro", "derecha"):
            im = renderizar_texto(ParamsTexto("MMMMMMMM\nI", alineacion=al))
            h, w = im.shape[:2]
            centros[al] = centro_x_filas(im, h // 2 + 5, h) / w
            # la línea larga ocupa el ancho: igual en las tres
            self.assertAlmostEqual(centro_x_filas(im, 0, h // 2 - 5) / w, 0.5, delta=0.02)
        self.assertLess(centros["izquierda"], 0.15)
        self.assertAlmostEqual(centros["centro"], 0.5, delta=0.02)
        self.assertGreater(centros["derecha"], 0.85)

    def test_corte_por_ancho_de_caja(self):
        contenido = "Esto es un texto bastante largo que no entra en una sola línea de la caja"
        sin = renderizar_texto(ParamsTexto(contenido, tamano=40))
        con = renderizar_texto(ParamsTexto(contenido, tamano=40, ancho_caja=300))
        self.assertGreater(sin.shape[1], 1000)
        self.assertLessEqual(con.shape[1], 300 + 12)
        self.assertGreaterEqual(con.shape[0], 40 * 1.2 * 4)
        x0, _, x1, _ = tinta(con)
        self.assertLessEqual(x1 - x0, 300 + 4)

    def test_palabra_mas_larga_que_la_caja_se_parte(self):
        im = renderizar_texto(ParamsTexto("Supercalifragilisticoespialidoso", tamano=40, ancho_caja=150))
        self.assertLessEqual(im.shape[1], 150 + 12)
        self.assertGreater(im.shape[0], 40 * 1.2 * 3)

    def test_caja_alinea_dentro_de_la_caja(self):
        im = renderizar_texto(ParamsTexto("Hi", tamano=40, ancho_caja=400, alineacion="derecha"))
        self.assertGreaterEqual(im.shape[1], 400)
        x0, _, x1, _ = tinta(im)
        self.assertGreater(x0, 300)

    def test_familia_que_no_existe_vuelve_a_arial(self):
        a = renderizar_texto(ParamsTexto("Hola", fuente="Arial"))
        b = renderizar_texto(ParamsTexto("Hola", fuente="FuenteQueNoExiste 123"))
        self.assertTrue(np.array_equal(a, b))
        c = renderizar_texto(ParamsTexto("Hola", fuente="arial"))     # sin importar mayúsculas
        self.assertTrue(np.array_equal(a, c))

    def test_negrita_y_cursiva_de_archivo(self):
        base = renderizar_texto(ParamsTexto("Hola mundo", fuente="Arial"))
        negrita = renderizar_texto(ParamsTexto("Hola mundo", fuente="Arial", negrita=True))
        cursiva = renderizar_texto(ParamsTexto("Hola mundo", fuente="Arial", cursiva=True))
        self.assertGreater(negrita[..., 3].sum(), base[..., 3].sum() * 1.2)
        self.assertFalse(np.array_equal(base.shape, cursiva.shape) and np.array_equal(base, cursiva))

    def test_negrita_y_cursiva_sintetizadas(self):
        # Impact tiene un solo archivo (sin negrita ni cursiva)
        if "Impact" not in familias_disponibles():
            self.skipTest("sin Impact")
        base = renderizar_texto(ParamsTexto("Hola", fuente="Impact"))
        negrita = renderizar_texto(ParamsTexto("Hola", fuente="Impact", negrita=True))
        cursiva = renderizar_texto(ParamsTexto("Hola", fuente="Impact", cursiva=True))
        self.assertGreater(negrita[..., 3].sum(), base[..., 3].sum() * 1.05)
        # inclinada: arriba la tinta se corre a la derecha respecto de abajo (contra la normal)
        def corrimiento(im):
            _, y0, _, y1 = tinta(im)
            cuarto = (y1 - y0) // 4
            return centro_x_filas(im, y0, y0 + cuarto) - centro_x_filas(im, y1 - cuarto, y1)
        self.assertGreater(corrimiento(cursiva) - corrimiento(base), 5)
        self.assertEqual(cursiva.shape[0], base.shape[0])

    def test_espaciado(self):
        a = renderizar_texto(ParamsTexto("Hola mundo"))
        b = renderizar_texto(ParamsTexto("Hola mundo", espaciado=10))
        self.assertAlmostEqual(b.shape[1] - a.shape[1], 9 * 10, delta=4)
        c = renderizar_texto(ParamsTexto("Hola mundo", espaciado=-5))
        self.assertLess(c.shape[1], a.shape[1])

    def test_escala(self):
        p = ParamsTexto("Hola\nmundo", tamano=40)
        a = renderizar_texto(p, 1.0)
        b = renderizar_texto(p, 2.0)
        self.assertAlmostEqual(b.shape[0] / a.shape[0], 2.0, delta=0.06)
        self.assertAlmostEqual(b.shape[1] / a.shape[1], 2.0, delta=0.06)
        with self.assertRaises(ValueError):
            renderizar_texto(p, -1)

    def test_color_semitransparente(self):
        im = renderizar_texto(ParamsTexto("Hola", color=(0, 0, 0, 128)))
        self.assertAlmostEqual(int(im[..., 3].max()), 128, delta=1)

    def test_vacio(self):
        for contenido in ("", "\n", "   "):
            with self.subTest(contenido=contenido):
                im = renderizar_texto(ParamsTexto(contenido))
                self.assertEqual(im.dtype, np.uint8)
                self.assertGreater(im.shape[0], 10)
                self.assertGreaterEqual(im.shape[1], 2)
                self.assertEqual(int(im[..., 3].max()), 0)

    def test_tamano_par_y_centro_estable(self):
        # al alinear a la izquierda, agregar texto no mueve el centro vertical
        a = renderizar_texto(ParamsTexto("ace"))
        b = renderizar_texto(ParamsTexto("ace jgy"))
        self.assertEqual(a.shape[0], b.shape[0])
        self.assertEqual(a.shape[0] % 2, 0)
        self.assertEqual(a.shape[1] % 2, 0)


@unittest.skipUnless(HAY_ARIAL, "sin Arial (no es Windows)")
class TestVelocidad(unittest.TestCase):
    def test_tres_lineas_a_72(self):
        p = ParamsTexto("NaturalShot Lite\nUn flyer de prueba\ncon tres líneas", tamano=72, negrita=True)
        renderizar_texto(p)
        tiempos = []
        for i in range(5):
            q = replace(p, contenido=p.contenido + " " * i)   # sin caché de por medio
            t = time.perf_counter()
            renderizar_texto(q)
            tiempos.append(time.perf_counter() - t)
        ms = sorted(tiempos)[2] * 1000
        print(f"\n  texto de 3 líneas a 72 px: {ms:.1f} ms")
        self.assertLess(ms, 60)        # objetivo 30 ms (margen para máquinas lentas)


class TestRespaldoQt(unittest.TestCase):
    """El camino sin FreeType (QPainter sobre QImage), forzado."""

    def test_render_con_qt(self):
        try:
            from PySide6.QtGui import QGuiApplication  # noqa: F401
        except ImportError:
            self.skipTest("sin PySide6")
        im = modulo_texto._renderizar_qt(ParamsTexto("Hola\nmundo", tamano=40, alineacion="centro"), 1.0)
        self.assertEqual(im.dtype, np.uint8)
        self.assertEqual(im.shape[2], 4)
        a = im[..., 3]
        self.assertEqual(int(a.max()), 255)
        self.assertGreater(int(((a > 0) & (a < 255)).sum()), 20)
        self.assertGreater(im.shape[0], 40 * 1.2 * 1.5)

    def test_motor_elegido(self):
        from PIL import features
        esperado = "pillow" if features.check("freetype2") else "qt"
        self.assertEqual(modulo_texto.MOTOR_TEXTO, esperado)


if __name__ == "__main__":
    unittest.main()
