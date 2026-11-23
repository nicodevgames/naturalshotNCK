"""Pruebas de la Etapa 2 del documento de capas (``motor/documento.py``): tipos nuevos
(píxeles, texto, forma, relleno y grupo), escala X/Y y volteo vertical, estilos en la
composición, grupos, operaciones de lienzo, rasterizar, combinar, acoplar, cajas, alinear y
distribuir, y la velocidad de un flyer.

Las formas y los rellenos usan ``motor/formas.py`` y el texto ``motor/texto.py`` (de M2): si
todavía no están, esas pruebas se saltean.
"""

from __future__ import annotations

import importlib
import io
import pickle
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from celular_natural.motor import documento as m_documento  # noqa: E402
from celular_natural.motor.documento import (  # noqa: E402
    ID_FONDO, AlmacenImagenes, CacheComposicion, Capa, Documento, Transformacion, acoplar, alinear, caja_capa,
    combinar_abajo, componer, convertir_foto_en_capa, distribuir, esquinas, escalar_imagen, rasterizar, recortar,
    rotar_lienzo, tamano_lienzo, trasladar, voltear_lienzo,
)
from celular_natural.motor.estilos import EstilosCapa, Sombra, Trazo  # noqa: E402


def modulo(nombre: str):
    try:
        return importlib.import_module(f"celular_natural.motor.{nombre}")
    except ImportError:
        return None


formas = modulo("formas")
texto = modulo("texto")


def requiere(mod, nombre):
    if mod is None:
        raise unittest.SkipTest(f"todavía no está motor/{nombre}.py (M2)")


def foto_sintetica(w=160, h=120, semilla=0) -> np.ndarray:
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.stack([xx / max(1, w - 1), yy / max(1, h - 1), 0.5 + 0.3 * np.sin(xx / 7.0) * np.cos(yy / 5.0)], -1)
    img += rng.normal(0, 0.02, img.shape).astype(np.float32)
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def bloque(w, h, color, alfa=255) -> np.ndarray:
    img = np.zeros((h, w, 4), np.uint8)
    img[..., :3] = color
    img[..., 3] = alfa
    return img


def logo(w, h, semilla=1) -> np.ndarray:
    """RGBA con textura y un disco de borde suave."""
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rgb = np.clip(np.stack([100 + 80 * np.sin(xx / 5), 120 + 60 * np.cos(yy / 7), rng.normal(128, 20, (h, w))], -1),
                  0, 255)
    r = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2))
    alfa = np.clip((1.0 - r) * 4.0, 0, 1) * 255
    return np.dstack([rgb, alfa]).round().astype(np.uint8)


def lienzo(alm=None, w=200, h=100, color=(255, 255, 255, 255)) -> Documento:
    requiere(formas, "formas")
    return Documento.nuevo_lienzo(w, h, formas.Relleno("color", (color,)))


def con_imagen(doc, alm, img, id_capa, t=None, **cambios):
    doc = doc.agregar_imagen(alm.guardar(img), id_capa, transform=t, id_capa=id_capa)
    return doc.con_capa(id_capa, **cambios) if cambios else doc


class Lector(pickle.Unpickler):
    """Como el de la sesión: solo Documento, Capa y Transformacion."""

    def find_class(self, modulo_, nombre):
        if modulo_.startswith("celular_natural.") and nombre in ("Documento", "Capa", "Transformacion"):
            return getattr(m_documento, nombre)
        raise pickle.UnpicklingError(f"clase no permitida: {modulo_}.{nombre}")


# ---------------------------------------------------------------------------
# Transformación y capas
# ---------------------------------------------------------------------------

class TestTransformacion(unittest.TestCase):

    def test_compatible(self):
        t = Transformacion(1, 2, 3, 4, True)   # posicional, como la Etapa 1
        self.assertEqual((t.escala_y, t.voltear_v, t.escala_vertical), (None, False, 3.0))
        self.assertNotEqual(Transformacion(escala=2, escala_y=2), Transformacion(escala=2))
        with self.assertRaises(ValueError):
            Transformacion(escala_y=0)
        with self.assertRaises(ValueError):
            Transformacion(voltear_v=1)

    def test_escala_xy_y_volteo_vertical_en_las_esquinas(self):
        e = esquinas(Transformacion(100, 50, 2.0, 0, escala_y=0.5), 40, 20)
        np.testing.assert_allclose(e, [[60, 45], [140, 45], [140, 55], [60, 55]])
        e = esquinas(Transformacion(0, 0, 1.0, 0, voltear_v=True), 40, 20)
        np.testing.assert_allclose(e[0], [-20, 10])   # la esquina de arriba pasa abajo


class TestCapasNuevas(unittest.TestCase):

    def test_validacion(self):
        with self.assertRaises(ValueError):
            Capa("p", "pixeles", "P")                     # sin imagen
        Capa("p", "pixeles", "P", imagen="abc")
        Capa("g", "grupo", "G")
        with self.assertRaises(ValueError):
            Capa("g", "grupo", "G", imagen="abc")
        with self.assertRaises(ValueError):
            Capa("t", "texto", "T")                       # sin params
        with self.assertRaises(ValueError):
            Capa("f", "foto", "F", estilos=EstilosCapa(sombra=Sombra()))
        with self.assertRaises(ValueError):
            Capa("f", "foto", "F", padre="g")
        with self.assertRaises(ValueError):
            Capa("g", "grupo", "G", padre="g")
        with self.assertRaises(ValueError):
            Capa("i", "imagen", "I", imagen="a", params={"tipo": "color"})
        c = Capa("i", "imagen", "I", imagen="a", estilos={"sombra": {"distancia": 4}})
        self.assertEqual(c.estilos, EstilosCapa(sombra=Sombra(distancia=4)))

    def test_la_sesion_rearma_un_documento_de_la_etapa_1(self):
        # sesion._reconstruir rearma cada dataclass con vars() y rechaza los tipos que no conoce: sin
        # estilos, una capa no tiene que llevar un EstilosCapa en su __dict__.
        from celular_natural import sesion
        doc = Documento.nuevo(50, 40).agregar_imagen("abc", "Logo", id_capa="l",
                                                     transform=Transformacion(1, 2, 0.5, 30, True))
        doc = doc.con_capa("l", opacidad=0.6, mascara="m")
        self.assertNotIn("estilos", vars(doc.capa("l")))
        self.assertEqual(doc.capa("l").estilos, EstilosCapa())
        self.assertEqual(sesion._reconstruir({"documento": doc}, {})["documento"], doc)
        con = doc.con_capa("l", estilos=EstilosCapa(sombra=Sombra()))
        self.assertEqual(con.capa("l").estilos.sombra, Sombra())
        self.assertNotIn("estilos", vars(con.con_capa("l", estilos=EstilosCapa()).capa("l")))

    def test_params_de_formas(self):
        requiere(formas, "formas")
        c = Capa("r", "relleno", "R", params={"tipo": "color", "colores": [[1, 2, 3, 255]]})
        self.assertIsInstance(c.params, formas.Relleno)
        Capa("f", "forma", "F", params=formas.ParamsForma())
        with self.assertRaises(ValueError):
            Capa("f", "forma", "F", params=formas.Relleno())   # otro tipo de params
        with self.assertRaises(ValueError):
            Capa("r", "relleno", "R", params={"tipo": "rarísimo"})

    def test_pickle_con_las_clases_de_la_sesion(self):
        requiere(formas, "formas")
        alm = AlmacenImagenes()
        doc = lienzo(alm)
        doc = doc.agregar(Capa("f", "forma", "F", params=formas.ParamsForma("estrella", 50, 50),
                               estilos=EstilosCapa(trazo=Trazo())))
        doc = con_imagen(doc, alm, logo(20, 20), "a", Transformacion(50, 50, 1.0, 0, False, 2.0, True))
        doc = doc.agrupar(["a"], id_grupo="g")
        datos = pickle.dumps(doc, protocol=pickle.HIGHEST_PROTOCOL)
        vuelta = Lector(io.BytesIO(datos)).load()
        self.assertEqual(vuelta, doc)
        self.assertEqual(hash(vuelta), hash(doc))


# ---------------------------------------------------------------------------
# Documento: lienzo y reglas
# ---------------------------------------------------------------------------

class TestLienzo(unittest.TestCase):

    def test_nuevo_lienzo(self):
        requiere(formas, "formas")
        doc = Documento.nuevo_lienzo(300, 200, formas.Relleno("color", ((10, 20, 30, 255),)))
        self.assertEqual([c.tipo for c in doc.capas], ["relleno", "ajuste_natural"])
        self.assertEqual(doc.base.id, ID_FONDO)
        self.assertIs(doc.foto, doc.base)   # compatible: la de abajo
        self.assertFalse(doc.tiene_foto)
        salida = componer(doc, AlmacenImagenes(), None)
        self.assertEqual(salida.shape, (200, 300, 3))
        self.assertTrue((salida == (10, 20, 30)).all())
        # Transparente: se aplana sobre blanco.
        vacio = Documento.nuevo_lienzo(30, 20)
        self.assertEqual(vacio.base.params.tipo, "ninguno")
        self.assertTrue((componer(vacio, AlmacenImagenes(), None) == 255).all())
        # Con el filtro, también (la composición es la "foto" del filtro).
        filtrada = componer(doc, AlmacenImagenes(), None, filtro=lambda x: 255 - x)
        self.assertTrue((filtrada == (245, 235, 225)).all())
        with self.assertRaises(ValueError):
            doc.quitar(ID_FONDO)
        with self.assertRaises(ValueError):
            doc.mover(ID_FONDO, 1)

    def test_fondo_degradado(self):
        requiere(formas, "formas")
        rel = formas.Relleno("lineal", ((0, 0, 0, 255), (255, 255, 255, 255)), (), 0.0)
        doc = Documento.nuevo_lienzo(200, 50, rel)
        salida = componer(doc, AlmacenImagenes(), None).astype(int)
        self.assertLess(salida[25, 2, 0], 20)
        self.assertGreater(salida[25, 197, 0], 235)
        mitad = componer(doc, AlmacenImagenes(), None, escala=0.5, cache=CacheComposicion())
        self.assertEqual(mitad.shape, (25, 100, 3))
        # Con opacidad, sobre blanco.
        medio = componer(doc.con_capa(ID_FONDO, opacidad=0.5), AlmacenImagenes(), None).astype(int)
        self.assertAlmostEqual(medio[25, 0, 0], 128, delta=12)

    def test_foto_con_lienzo_documento_de_foto(self):
        doc = Documento.nuevo(40, 30)
        self.assertTrue(doc.tiene_foto)
        with self.assertRaises(ValueError):
            componer(doc, AlmacenImagenes(), None)   # el de foto sigue pidiendo la foto


# ---------------------------------------------------------------------------
# Grupos
# ---------------------------------------------------------------------------

class TestGrupos(unittest.TestCase):

    def setUp(self):
        self.alm = AlmacenImagenes()
        doc = Documento.nuevo(100, 80)
        for n in "abcd":
            doc = doc.agregar_imagen(n, n.upper(), id_capa=n)
        self.doc = doc

    def orden(self, doc):
        return [(c.id, c.padre) for c in doc.capas[1:-1]]

    def test_estructura_invalida(self):
        foto, ajuste = Capa("f", "foto", "F"), Capa("aj", "ajuste_natural", "A")
        g = Capa("g", "grupo", "G")
        hijo = Capa("h", "imagen", "H", imagen="x", padre="g")
        Documento(10, 10, (foto, hijo, g, ajuste))
        with self.assertRaises(ValueError):
            Documento(10, 10, (foto, g, hijo, ajuste))                 # el hijo va debajo del grupo
        with self.assertRaises(ValueError):
            Documento(10, 10, (foto, hijo, Capa("i", "imagen", "I", imagen="y"), g, ajuste))   # no contiguo
        with self.assertRaises(ValueError):
            Documento(10, 10, (foto, Capa("h", "imagen", "H", imagen="x", padre="nada"), ajuste))
        with self.assertRaises(ValueError):
            Documento(10, 10, (foto, Capa("h", "imagen", "H", imagen="x", padre="i"),
                               Capa("i", "imagen", "I", imagen="y"), ajuste))   # el padre no es un grupo
        # Anidados, hasta el tope: g0 arriba de todo, g1 adentro de g0, etc. (los de adentro, más abajo).
        prof = m_documento.PROFUNDIDAD_MAX

        def anidados(n):
            return (foto,) + tuple(Capa(f"g{k}", "grupo", "G", padre=f"g{k - 1}" if k else None)
                                   for k in reversed(range(n))) + (ajuste,)
        Documento(10, 10, anidados(prof))
        with self.assertRaises(ValueError):
            Documento(10, 10, anidados(prof + 1))

    def test_agrupar_y_desagrupar(self):
        doc = self.doc.agrupar(["b", "c"], nombre="Grupo", id_grupo="g")
        self.assertEqual(self.orden(doc), [("a", None), ("b", "g"), ("c", "g"), ("g", None), ("d", None)])
        self.assertEqual([c.id for c in doc.hijos("g")], ["b", "c"])
        self.assertEqual(doc.ancestros("b"), ("g",))
        # Agrupar capas separadas: el grupo queda donde estaba la de más arriba.
        d2 = self.doc.agrupar(["a", "c"], id_grupo="g")
        self.assertEqual(self.orden(d2), [("b", None), ("a", "g"), ("c", "g"), ("g", None), ("d", None)])
        # Un grupo dentro de otro.
        d3 = doc.agrupar(["g", "d"], id_grupo="g2")
        self.assertEqual(self.orden(d3), [("a", None), ("b", "g"), ("c", "g"), ("g", "g2"), ("d", "g2"), ("g2", None)])
        self.assertEqual(d3.ancestros("b"), ("g", "g2"))
        # Si eligen un grupo y uno de sus hijos, va el grupo (con todo).
        self.assertEqual(self.orden(doc.agrupar(["g", "b"], id_grupo="x")),
                         [("a", None), ("b", "g"), ("c", "g"), ("g", "x"), ("x", None), ("d", None)])
        self.assertEqual(self.orden(doc.desagrupar("g")), [("a", None), ("b", None), ("c", None), ("d", None)])
        self.assertEqual(self.orden(d3.desagrupar("g2")), self.orden(doc))
        with self.assertRaises(ValueError):
            doc.desagrupar("a")
        with self.assertRaises(ValueError):
            self.doc.agrupar([])
        with self.assertRaises(ValueError):
            self.doc.agrupar([self.doc.base.id])

    def test_mover_respeta_los_grupos(self):
        doc = self.doc.agrupar(["b", "c"], id_grupo="g")
        # El grupo se mueve con sus hijos, entre sus hermanos.
        self.assertEqual(self.orden(doc.mover("g", 1)), [("a", None), ("d", None), ("b", "g"), ("c", "g"), ("g", None)])
        self.assertEqual(self.orden(doc.mover("g", -1))[:3], [("b", "g"), ("c", "g"), ("g", None)])
        # Un hijo se mueve dentro de su grupo, sin salirse.
        self.assertEqual(self.orden(doc.mover("b", 5))[:4], [("a", None), ("c", "g"), ("b", "g"), ("g", None)])
        self.assertEqual(doc.mover("b", -5), doc)
        self.assertEqual(self.orden(doc.mover("d", -1)), [("a", None), ("d", None), ("b", "g"), ("c", "g"), ("g", None)])
        self.assertEqual(self.orden(doc.mover("a", 1)), [("b", "g"), ("c", "g"), ("g", None), ("a", None), ("d", None)])

    def test_reubicar(self):
        doc = self.doc.agrupar(["b", "c"], id_grupo="g")
        self.assertEqual(self.orden(doc.reubicar("d", "g", "dentro")),
                         [("a", None), ("b", "g"), ("c", "g"), ("d", "g"), ("g", None)])
        self.assertEqual(self.orden(doc.reubicar("a", "c", "encima")),
                         [("b", "g"), ("c", "g"), ("a", "g"), ("g", None), ("d", None)])
        self.assertEqual(self.orden(doc.reubicar("d", "b", "debajo")),
                         [("a", None), ("d", "g"), ("b", "g"), ("c", "g"), ("g", None)])
        self.assertEqual(self.orden(doc.reubicar("b", "d", "encima")),
                         [("a", None), ("c", "g"), ("g", None), ("d", None), ("b", None)])
        self.assertEqual(self.orden(doc.reubicar("g", doc.base.id, "encima")),
                         [("b", "g"), ("c", "g"), ("g", None), ("a", None), ("d", None)])
        with self.assertRaises(ValueError):
            doc.reubicar("g", "b", "encima")    # adentro de sí mismo
        with self.assertRaises(ValueError):
            doc.reubicar("a", "d", "dentro")    # d no es un grupo
        with self.assertRaises(ValueError):
            doc.reubicar("a", doc.base.id, "debajo")

    def test_quitar_y_duplicar_grupo(self):
        doc = self.doc.agrupar(["b", "c"], id_grupo="g")
        self.assertEqual(self.orden(doc.quitar("g")), [("a", None), ("d", None)])
        self.assertEqual(self.orden(doc.quitar("b")), [("a", None), ("c", "g"), ("g", None), ("d", None)])
        dup = doc.duplicar("g", id_capa="g2")
        orden = self.orden(dup)
        self.assertEqual(len(orden), 8)
        self.assertEqual(orden[3:7], [("g", None), (orden[4][0], "g2"), (orden[5][0], "g2"), ("g2", None)])
        hijos = dup.hijos("g2")
        self.assertEqual([c.imagen for c in hijos], ["b", "c"])
        self.assertTrue(all(c.id not in "bc" for c in hijos))
        self.assertEqual(dup.capa("g2").nombre, doc.capa("g").nombre + " copia")

    def test_agregar_dentro_y_encima(self):
        doc = self.doc.agrupar(["b", "c"], id_grupo="g")
        d1 = doc.agregar(Capa("n", "grupo", "N"), dentro="g")
        self.assertEqual(self.orden(d1)[:4], [("a", None), ("b", "g"), ("c", "g"), ("n", "g")])
        d2 = doc.agregar_imagen("x", "X", encima_de="b", id_capa="x")
        self.assertEqual(self.orden(d2)[:4], [("a", None), ("b", "g"), ("x", "g"), ("c", "g")])
        d3 = doc.agregar_imagen("x", "X", encima_de="g", id_capa="x")
        self.assertEqual(self.orden(d3)[3:5], [("g", None), ("x", None)])
        with self.assertRaises(ValueError):
            doc.agregar(Capa("a", "grupo", "repetido"))
        with self.assertRaises(ValueError):
            doc.agregar(Capa("z", "foto", "Otra foto"))

    def test_opacidad_del_grupo_no_es_la_de_cada_hijo(self):
        alm = AlmacenImagenes()
        blanco = np.full((60, 80, 3), 255, np.uint8)
        doc = Documento.nuevo(80, 60)
        doc = con_imagen(doc, alm, bloque(40, 40, (255, 0, 0)), "roja", Transformacion(30, 30))
        doc = con_imagen(doc, alm, bloque(40, 40, (0, 0, 255)), "azul", Transformacion(50, 30))
        agrupado = doc.agrupar(["roja", "azul"], id_grupo="g").con_capa("g", opacidad=0.5)
        salida = componer(agrupado, alm, blanco).astype(int)
        # En la parte que se pisan, el grupo es azul al 50 % sobre blanco (el rojo no se ve).
        np.testing.assert_allclose(salida[30, 40], (128, 128, 255), atol=1)
        np.testing.assert_allclose(salida[30, 15], (255, 128, 128), atol=1)
        # Con la opacidad en cada hijo, el rojo se trasluce.
        cada = doc.con_capa("roja", opacidad=0.5).con_capa("azul", opacidad=0.5)
        otra = componer(cada, alm, blanco).astype(int)
        self.assertGreater(salida[30, 40, 2] - otra[30, 40, 2], 20)   # (128, 64, 191) en vez de (128, 128, 255)
        # Grupo al 100 %, normal: igual que sin grupo (casi; el grupo se cuantiza a 8 bits).
        np.testing.assert_allclose(componer(doc.agrupar(["roja", "azul"]), alm, blanco).astype(int),
                                   componer(doc, alm, blanco).astype(int), atol=1)
        # Grupo oculto: no se ve nada de adentro.
        np.testing.assert_array_equal(componer(agrupado.con_capa("g", visible=False), alm, blanco), blanco)

    def test_mascara_y_fusion_del_grupo(self):
        alm = AlmacenImagenes()
        foto = foto_sintetica(80, 60)
        doc = con_imagen(Documento.nuevo(80, 60), alm, bloque(80, 60, (200, 200, 200)), "gris", Transformacion(40, 30))
        mascara = np.zeros((60, 80), np.uint8)
        mascara[:, 40:] = 255
        doc = doc.agrupar(["gris"], id_grupo="g").con_capa("g", mascara=alm.guardar(mascara), fusion="multiplicar")
        salida = componer(doc, alm, foto).astype(np.float32)
        np.testing.assert_array_equal(salida[:, :39], foto[:, :39])
        np.testing.assert_allclose(salida[:, 41:], foto[:, 41:].astype(np.float32) * 200 / 255.0, atol=1)

    def test_cache_del_grupo(self):
        alm = AlmacenImagenes()
        foto = foto_sintetica()
        doc = Documento.nuevo(160, 120)
        doc = con_imagen(doc, alm, logo(60, 40, 1), "a", Transformacion(50, 50))
        doc = con_imagen(doc, alm, logo(60, 40, 2), "b", Transformacion(70, 60, 1.0, 20))
        doc = con_imagen(doc, alm, logo(30, 30, 3), "c", Transformacion(120, 30))
        doc = doc.agrupar(["a", "b"], id_grupo="g").con_capa("g", opacidad=0.7)
        cache = CacheComposicion()
        componer(doc, alm, foto, cache=cache)
        grupos = lambda: sum(1 for k in cache._entradas if k[0] == "grupo")   # noqa: E731
        self.assertEqual(grupos(), 1)
        movida = doc.con_capa("c", transform=Transformacion(100, 90))
        np.testing.assert_array_equal(componer(movida, alm, foto, cache=cache), componer(movida, alm, foto))
        componer(doc.con_capa("g", opacidad=0.3), alm, foto, cache=cache)
        self.assertEqual(grupos(), 1)   # mover otra capa o cambiar la opacidad del grupo: no se recompone
        componer(doc.con_capa("a", transform=Transformacion(40, 40)), alm, foto, cache=cache)
        self.assertEqual(grupos(), 2)


# ---------------------------------------------------------------------------
# Tipos nuevos en la composición
# ---------------------------------------------------------------------------

class TestComponerTipos(unittest.TestCase):

    def setUp(self):
        self.alm = AlmacenImagenes()
        self.foto = foto_sintetica()

    def test_pixeles_como_imagen(self):
        img = logo(50, 30)
        t = Transformacion(70, 50, 1.3, 25)
        como_imagen = con_imagen(Documento.nuevo(160, 120), self.alm, img, "i", t)
        como_pixeles = Documento.nuevo(160, 120).agregar(Capa("p", "pixeles", "P", imagen=self.alm.guardar(img),
                                                              transform=t))
        np.testing.assert_array_equal(componer(como_pixeles, self.alm, self.foto),
                                      componer(como_imagen, self.alm, self.foto))

    def test_escala_xy_y_volteo_vertical(self):
        img = np.zeros((20, 20, 4), np.uint8)
        img[..., 1:] = 255        # cian opaco…
        img[0:4, 8:12] = (255, 0, 0, 255)   # …con rojo arriba
        base = np.zeros((100, 100, 3), np.uint8)

        def rojo(t):
            doc = Documento.nuevo(100, 100).agregar_imagen(self.alm.guardar(img), "I", transform=t)
            s = componer(doc, self.alm, base)
            ys, xs = np.nonzero(s[..., 0] > 128)
            return xs, ys, s

        xs, ys, _ = rojo(Transformacion(50, 50, voltear_v=True))
        self.assertGreater(ys.mean(), 55)   # el rojo pasó abajo
        xs, ys, _ = rojo(Transformacion(50, 50, 1.0, escala_y=3.0))
        self.assertLess(ys.min(), 25)       # estirado en vertical: el rojo sube
        self.assertEqual(xs.max() - xs.min() + 1, 4)
        doc = Documento.nuevo(100, 100).agregar_imagen(self.alm.guardar(img), "I",
                                                       transform=Transformacion(50, 50, 2.0, escala_y=0.5))
        s = componer(doc, self.alm, base)
        ys, xs = np.nonzero(s.max(-1) > 0)
        self.assertAlmostEqual(xs.max() - xs.min(), 40, delta=2)
        self.assertAlmostEqual(ys.max() - ys.min(), 10, delta=2)

    def test_forma_y_su_rerender(self):
        requiere(formas, "formas")
        p = formas.ParamsForma("rectangulo", 40, 20, relleno=formas.Relleno("color", ((255, 0, 0, 255),)))
        doc = Documento.nuevo(160, 120).agregar(Capa("f", "forma", "F", params=p, transform=Transformacion(80, 60)))
        s = componer(doc, self.alm, self.foto)
        self.assertEqual(tuple(s[60, 80]), (255, 0, 0))
        ys, xs = np.nonzero((s == (255, 0, 0)).all(-1))
        self.assertEqual((xs.min(), xs.max(), ys.min(), ys.max()), (60, 99, 50, 69))
        # Agrandada al triple: se vuelve a dibujar a esa escala (no se pixela).
        espia = mock.Mock(wraps=formas.renderizar_forma)
        with mock.patch.object(formas, "renderizar_forma", espia):
            m_documento._limpiar_generados()
            componer(doc.con_capa("f", transform=Transformacion(80, 60, 3.0)), self.alm, self.foto)
        escalas = sorted({round(c.args[1] if len(c.args) > 1 else c.kwargs.get("escala", 1.0), 3)
                          for c in espia.call_args_list})
        self.assertTrue(any(3.0 <= e < 3.3 for e in escalas), escalas)   # hacia arriba, a pasos de 2^(1/8)
        # En la vista previa a la mitad, a escala 0,5 × 2 = 1.
        espia.reset_mock()
        with mock.patch.object(formas, "renderizar_forma", espia):
            m_documento._limpiar_generados()
            componer(doc.con_capa("f", transform=Transformacion(80, 60, 2.0)), self.alm,
                     cv2.resize(self.foto, (80, 60)), 0.5)
        self.assertTrue(all(abs((c.args[1] if len(c.args) > 1 else 1.0) - 1.0) < 1e-9 for c in espia.call_args_list))

    def test_relleno_como_capa_con_mascara(self):
        requiere(formas, "formas")
        mascara = np.zeros((120, 160), np.uint8)
        mascara[:60] = 255
        doc = Documento.nuevo(160, 120).agregar(Capa("r", "relleno", "R", params=formas.Relleno(
            "color", ((0, 255, 0, 255),)), mascara=self.alm.guardar(mascara)))
        s = componer(doc, self.alm, self.foto)
        self.assertTrue((s[:59] == (0, 255, 0)).all())
        np.testing.assert_array_equal(s[61:], self.foto[61:])

    def test_estilos_en_la_composicion(self):
        img = bloque(20, 20, (255, 255, 255))
        base = np.full((100, 100, 3), 128, np.uint8)
        e = EstilosCapa(sombra=Sombra((0, 0, 0, 255), 1.0, 0, 15, 0))   # luz desde la derecha: sombra a la izquierda
        doc = con_imagen(Documento.nuevo(100, 100), self.alm, img, "b", Transformacion(50, 50), estilos=e)
        s = componer(doc, self.alm, base)
        self.assertTrue((s[45, 26:39] == 0).all())       # la sombra, a la izquierda del cuadro
        self.assertTrue((s[45, 41:59] == 255).all())     # el cuadro, encima
        self.assertTrue((s[45, 61:] == 128).all())
        # Girada la capa, la sombra sigue yendo a la izquierda (el ángulo es del documento).
        girada = doc.con_capa("b", transform=Transformacion(50, 50, 1.0, 90))
        s2 = componer(girada, self.alm, base)
        self.assertTrue((s2[45, 26:39] == 0).all())
        # A la mitad de escala, la sombra se corre la mitad.
        s3 = componer(doc, self.alm, cv2.resize(base, (50, 50)), 0.5)
        self.assertTrue((s3[22, 13:19] == 0).all())
        self.assertTrue((s3[22, 21:29] == 255).all())
        # Con caché, lo mismo; y la sombra que cae fuera del documento no rompe nada.
        cache = CacheComposicion()
        for d in (doc, girada, doc.con_capa("b", transform=Transformacion(3, 50))):
            np.testing.assert_array_equal(componer(d, self.alm, base, cache=cache), componer(d, self.alm, base))

    def test_estilos_de_una_capa_afuera_que_entra(self):
        # La capa está afuera, a la derecha, pero su sombra cae adentro.
        e = EstilosCapa(sombra=Sombra((0, 0, 0, 255), 1.0, 0, 30, 0))
        doc = con_imagen(Documento.nuevo(100, 100), self.alm, bloque(20, 20, (255, 255, 255)), "b",
                         Transformacion(110, 50), estilos=e)
        s = componer(doc, self.alm, np.full((100, 100, 3), 128, np.uint8))
        self.assertTrue((s[45, 72:79] == 0).all())

    def test_capa_por_capa_igual_que_por_franjas(self):
        requiere(formas, "formas")
        doc = Documento.nuevo_lienzo(160, 120, formas.Relleno("lineal", ((20, 40, 200, 255), (250, 200, 10, 255))))
        doc = con_imagen(doc, self.alm, logo(60, 50, 1), "a", Transformacion(40, 40, 1.2, 15), fusion="multiplicar")
        doc = con_imagen(doc, self.alm, logo(60, 50, 2), "b", Transformacion(90, 70, 0.9, -30, True, 1.4),
                         estilos=EstilosCapa(sombra=Sombra(tamano=4), trazo=Trazo((255, 0, 0), 2)))
        doc = doc.agregar(Capa("f", "forma", "F", params=formas.ParamsForma("estrella", 50, 50), opacidad=0.8,
                               transform=Transformacion(120, 40, 1.0, 10), estilos=EstilosCapa(trazo=Trazo())))
        doc = doc.agrupar(["a", "b"], id_grupo="g").con_capa("g", opacidad=0.8, fusion="pantalla",
                                                               estilos=EstilosCapa(sombra=Sombra(distancia=5)))
        for d in (doc, doc.con_capa(ID_FONDO, opacidad=0.6)):
            franjas = componer(d, self.alm, None)
            with mock.patch.object(m_documento, "_MEMORIA_CAPAS", 0):
                capa_por_capa = componer(d, self.alm, None)
            np.testing.assert_array_equal(capa_por_capa, franjas)
            np.testing.assert_array_equal(componer(d, self.alm, None, cache=CacheComposicion()), franjas)

    def test_texto_con_un_modulo_de_prueba(self):
        # El camino del texto en M1 (validar, dibujar a escala, caja, rasterizar, pickle), con un
        # texto.py de mentira que cumple el contrato: un bloque de color de len × 0,6·tamaño.
        import dataclasses
        import types

        @dataclasses.dataclass(frozen=True)
        class ParamsTexto:
            contenido: str = "Texto"
            tamano: float = 72.0
            color: tuple = (255, 255, 255, 255)

            def como_dict(self):
                return {"contenido": self.contenido, "tamano": self.tamano, "color": list(self.color)}

            @staticmethod
            def desde_dict(d):
                return ParamsTexto(d.get("contenido", "Texto"), d.get("tamano", 72.0), tuple(d.get("color", (255,) * 4)))

        def renderizar_texto(p, escala=1.0):
            w, h = round(len(p.contenido) * p.tamano * 0.6 * escala), round(p.tamano * escala)
            img = np.zeros((h + 4, w + 4, 4), np.uint8)
            img[2:-2, 2:-2] = p.color
            return img

        falso = types.ModuleType("celular_natural.motor.texto")
        falso.ParamsTexto, falso.renderizar_texto = ParamsTexto, mock.Mock(wraps=renderizar_texto)
        import celular_natural.motor as paquete
        with mock.patch.dict(sys.modules, {"celular_natural.motor.texto": falso}), \
                mock.patch.object(paquete, "texto", falso, create=True):
            m_documento._limpiar_generados()
            try:
                p = ParamsTexto("Hola", 20, (255, 0, 0, 255))
                doc = Documento.nuevo(160, 120).agregar(Capa("t", "texto", "Hola", params=p.como_dict(),
                                                             transform=Transformacion(80, 60)))
                self.assertEqual(doc.capa("t").params, p)
                s = componer(doc, self.alm, self.foto)
                ys, xs = np.nonzero((s == (255, 0, 0)).all(-1))
                self.assertEqual((xs.min(), xs.max() + 1, ys.min(), ys.max() + 1), (56, 104, 50, 70))
                self.assertEqual(caja_capa(doc, "t", self.alm), (56.0, 50.0, 104.0, 70.0))
                falso.renderizar_texto.reset_mock()
                componer(doc.con_capa("t", transform=Transformacion(80, 60, 2.0)), self.alm, self.foto)
                self.assertEqual([c.args[1] for c in falso.renderizar_texto.call_args_list], [2.0])
                r = rasterizar(doc, self.alm, "t")
                np.testing.assert_array_equal(componer(r, self.alm, self.foto), s)
                self.assertEqual(Lector(io.BytesIO(pickle.dumps(doc))).load(), doc)
                self.assertEqual(Documento.desde_dict(doc.como_dict()), doc)
                self.assertTrue(doc.usa_etapa2())
            finally:
                m_documento._limpiar_generados()

    def test_texto(self):
        requiere(texto, "texto")
        p = texto.ParamsTexto("Hola", tamano=40, color=(255, 0, 0, 255))
        doc = Documento.nuevo(200, 100).agregar(Capa("t", "texto", "Hola", params=p,
                                                     transform=Transformacion(100, 50)))
        s = componer(doc, self.alm, np.zeros((100, 200, 3), np.uint8))
        rojo = (s[..., 0] > 128) & (s[..., 1] < 60)
        self.assertGreater(int(rojo.sum()), 100)
        ys, xs = np.nonzero(rojo)
        self.assertAlmostEqual(float(xs.mean()), 100, delta=25)
        caja = caja_capa(doc, "t", self.alm)
        self.assertLess(caja[0], xs.min() + 1)
        self.assertGreater(caja[2], xs.max())
        r = rasterizar(doc, self.alm, "t")
        self.assertEqual(r.capa("t").tipo, "pixeles")
        np.testing.assert_array_equal(componer(r, self.alm, np.zeros((100, 200, 3), np.uint8)), s)


# ---------------------------------------------------------------------------
# Operaciones
# ---------------------------------------------------------------------------

class TestOperaciones(unittest.TestCase):

    def setUp(self):
        requiere(formas, "formas")
        self.alm = AlmacenImagenes()
        doc = Documento.nuevo_lienzo(120, 80, formas.Relleno("color", ((240, 240, 240, 255),)))
        doc = con_imagen(doc, self.alm, logo(40, 30, 1), "a", Transformacion(30, 25))
        doc = con_imagen(doc, self.alm, bloque(20, 10, (200, 30, 30)), "b", Transformacion(80, 50))
        mascara = np.zeros((80, 120), np.uint8)
        mascara[:, :70] = 255
        self.doc = doc.con_capa("a", mascara=self.alm.guardar(mascara))

    def comp(self, doc):
        return componer(doc, self.alm, None)

    def test_tamano_lienzo_y_recortar(self):
        antes = self.comp(self.doc)
        grande = tamano_lienzo(self.doc, self.alm, 160, 100, "abajo_derecha")
        self.assertEqual((grande.ancho, grande.alto), (160, 100))
        self.assertEqual(grande.capa("a").transform.x, 70)
        np.testing.assert_array_equal(self.comp(grande)[20:, 40:], antes)
        self.assertEqual(self.alm.obtener(grande.capa("a").mascara).shape, (100, 160))
        centro = tamano_lienzo(self.doc, self.alm, 140, 100)
        np.testing.assert_array_equal(self.comp(centro)[10:90, 10:130], antes)
        chico = recortar(self.doc, self.alm, 10, 5, 60, 50)
        self.assertEqual((chico.ancho, chico.alto), (60, 50))
        np.testing.assert_array_equal(self.comp(chico), antes[5:55, 10:70])
        with self.assertRaises(ValueError):
            tamano_lienzo(self.doc, self.alm, 10, 10, "nada")
        with self.assertRaises(ValueError):
            recortar(self.doc, self.alm, 0, 0, 0, 10)

    def test_rotar_y_voltear(self):
        antes = self.comp(self.doc)
        for grados, k in ((90, -1), (180, 2), (270, 1)):
            r = rotar_lienzo(self.doc, self.alm, grados)
            np.testing.assert_array_equal(self.comp(r), np.rot90(antes, k))
        np.testing.assert_array_equal(self.comp(voltear_lienzo(self.doc, self.alm, "h")), antes[:, ::-1])
        np.testing.assert_array_equal(self.comp(voltear_lienzo(self.doc, self.alm, "v")), antes[::-1])
        with self.assertRaises(ValueError):
            rotar_lienzo(self.doc, self.alm, 45)
        # Con estilos: la sombra y el trazo giran y se espejan con el lienzo.
        con_estilos = self.doc.con_capa("b", estilos=EstilosCapa(sombra=Sombra((0, 0, 0, 255), 1.0, 0, 8, 2),
                                                                 trazo=Trazo((0, 0, 255), 2)))
        antes = self.comp(con_estilos).astype(int)
        np.testing.assert_allclose(self.comp(rotar_lienzo(con_estilos, self.alm, 90)), np.rot90(antes, -1), atol=1)
        np.testing.assert_allclose(self.comp(voltear_lienzo(con_estilos, self.alm, "v")), antes[::-1], atol=1)

    def test_escalar_imagen(self):
        antes = self.comp(self.doc)
        doble = escalar_imagen(self.doc, self.alm, 240, 160)
        self.assertEqual(doble.capa("b").transform, Transformacion(160, 100, 2.0))
        reducida = cv2.resize(self.comp(doble), (120, 80), interpolation=cv2.INTER_AREA)
        self.assertLess(float(np.abs(reducida.astype(int) - antes).mean()), 3.0)
        ancha = escalar_imagen(self.doc, self.alm, 240, 80)
        t = ancha.capa("b").transform
        self.assertEqual((t.escala, t.escala_vertical), (2.0, 1.0))

    def test_documento_de_foto(self):
        foto = foto_sintetica(120, 80)
        doc = con_imagen(Documento.nuevo(120, 80), self.alm, logo(30, 30), "a", Transformacion(60, 40))
        with self.assertRaises(ValueError):
            tamano_lienzo(doc, self.alm, 200, 100)   # hace falta la foto para pasarla a capa
        convertido = convertir_foto_en_capa(doc, self.alm, foto)
        self.assertEqual(convertido.base.tipo, "relleno")
        self.assertEqual(convertido.capas[1].tipo, "pixeles")
        np.testing.assert_array_equal(componer(convertido, self.alm, None), componer(doc, self.alm, foto))
        grande = tamano_lienzo(doc, self.alm, 140, 100, foto_rgb=foto)
        np.testing.assert_array_equal(componer(grande, self.alm, None)[10:90, 10:130], componer(doc, self.alm, foto))

    def test_rasterizar(self):
        p = formas.ParamsForma("elipse", 50, 30, relleno=formas.Relleno("color", ((0, 0, 255, 255),)), grosor=2)
        doc = self.doc.agregar(Capa("f", "forma", "F", params=p, transform=Transformacion(60, 40, 1.0, 30)))
        r = rasterizar(doc, self.alm, "f")
        self.assertEqual((r.capa("f").tipo, r.capa("f").params), ("pixeles", None))
        np.testing.assert_array_equal(self.comp(r), self.comp(doc))
        relleno = doc.agregar(Capa("r", "relleno", "R", params=formas.Relleno("color", ((0, 255, 0, 128),))))
        np.testing.assert_array_equal(self.comp(rasterizar(relleno, self.alm, "r")), self.comp(relleno))
        with self.assertRaises(ValueError):
            rasterizar(doc, self.alm, ID_FONDO)

    def test_combinar_abajo_y_acoplar(self):
        antes = self.comp(self.doc)
        combinado = combinar_abajo(self.doc, self.alm, "b")
        self.assertEqual([c.id for c in combinado.capas[1:-1]], ["a"])
        self.assertEqual(combinado.capa("a").tipo, "pixeles")
        self.assertIsNone(combinado.capa("a").mascara)
        np.testing.assert_allclose(self.comp(combinado).astype(int), antes.astype(int), atol=1)
        with self.assertRaises(ValueError):
            combinar_abajo(self.doc, self.alm, "a")   # abajo está el fondo
        agrupado = self.doc.agrupar(["a", "b"], id_grupo="g").con_capa("g", opacidad=0.6)
        g = combinar_abajo(agrupado, self.alm, "g")
        self.assertEqual((g.capa("g").tipo, g.capa("g").opacidad), ("pixeles", 0.6))
        np.testing.assert_allclose(self.comp(g).astype(int), self.comp(agrupado).astype(int), atol=1)
        plano = acoplar(self.doc, self.alm)
        self.assertEqual([c.tipo for c in plano.capas], ["relleno", "pixeles", "ajuste_natural"])
        np.testing.assert_array_equal(self.comp(plano), antes)

    def test_cajas_alinear_y_distribuir(self):
        # Logo de 40×30 con margen transparente: la caja es la de lo que se ve.
        img = np.zeros((30, 40, 4), np.uint8)
        img[5:25, 10:30] = (255, 0, 0, 255)
        doc = con_imagen(self.doc, self.alm, img, "c", Transformacion(60, 40))
        np.testing.assert_allclose(caja_capa(doc, "c", self.alm), (50, 30, 70, 50))
        np.testing.assert_allclose(caja_capa(doc.con_capa("c", transform=Transformacion(60, 40, 2.0, 90)), "c", self.alm),
                                   (40, 20, 80, 60))
        self.assertEqual(caja_capa(doc, ID_FONDO, self.alm), (0, 0, 120, 80))
        izq = alinear(doc, ["c"], "izquierda", almacen=self.alm)
        np.testing.assert_allclose(caja_capa(izq, "c", self.alm)[0], 0)
        abajo = alinear(doc, ["c"], "abajo", almacen=self.alm)
        np.testing.assert_allclose(caja_capa(abajo, "c", self.alm)[3], 80)
        sel = alinear(doc, ["b", "c"], "derecha", "seleccion", almacen=self.alm)
        self.assertAlmostEqual(caja_capa(sel, "c", self.alm)[2], caja_capa(sel, "b", self.alm)[2])
        grupo = doc.agrupar(["b", "c"], id_grupo="g")
        caja_g = caja_capa(grupo, "g", self.alm)
        self.assertEqual(caja_g[2], max(caja_capa(grupo, "b", self.alm)[2], 70))
        centrado = alinear(grupo, ["g"], "centro_h", almacen=self.alm)
        c2 = caja_capa(centrado, "g", self.alm)
        self.assertAlmostEqual((c2[0] + c2[2]) / 2, 60)
        tres = trasladar(doc, ["a"], -10, 0)
        self.assertEqual(tres.capa("a").transform.x, 20)
        dist = distribuir(doc, ["a", "c", "b"], "h", almacen=self.alm)
        centros = sorted((caja_capa(dist, i, self.alm)[0] + caja_capa(dist, i, self.alm)[2]) / 2 for i in "abc")
        self.assertAlmostEqual(centros[1] - centros[0], centros[2] - centros[1])


# ---------------------------------------------------------------------------
# Velocidad: un flyer
# ---------------------------------------------------------------------------

class TestVelocidadFlyer(unittest.TestCase):
    """1080×1920, sin filtro: fondo con degradado, 4 imágenes (2 en un grupo), 2 textos (o 2
    formas si no está texto.py), 1 forma con sombra y trazo."""

    def setUp(self):
        requiere(formas, "formas")
        self.alm = AlmacenImagenes()
        doc = Documento.nuevo_lienzo(1080, 1920, formas.Relleno(
            "lineal", ((30, 20, 90, 255), (240, 120, 60, 255), (250, 230, 200, 255)), (), 90.0))
        posiciones = ((280, 600), (800, 600), (280, 1150), (800, 1150))
        for k, (x, y) in enumerate(posiciones):
            doc = con_imagen(doc, self.alm, logo(480, 480, k), f"img{k}", Transformacion(x, y, 1.0, (k - 1.5) * 3))
        doc = doc.agrupar(["img2", "img3"], id_grupo="grupo").con_capa("grupo", opacidad=0.9)
        banda = formas.ParamsForma("rectangulo", 1000, 220, radio=40,
                                   relleno=formas.Relleno("color", ((250, 250, 250, 255),)))
        doc = doc.agregar(Capa("banda", "forma", "Banda", params=banda, transform=Transformacion(540, 1600),
                               estilos=EstilosCapa(sombra=Sombra(distancia=12, tamano=14), trazo=Trazo(grosor=4))))
        if texto is not None:
            t1 = texto.ParamsTexto("GRAN TÍTULO", tamano=120, negrita=True)
            t2 = texto.ParamsTexto("Sábado 21 · 20 h\nEntrada libre", tamano=64, color=(20, 20, 20, 255),
                                   alineacion="centro")
            doc = doc.agregar(Capa("t1", "texto", "Título", params=t1, transform=Transformacion(540, 220)))
            doc = doc.agregar(Capa("t2", "texto", "Datos", params=t2, transform=Transformacion(540, 1600)))
            self.con = "textos"
        else:
            for i, (y, w) in enumerate(((220, 900), (1600, 700))):
                p = formas.ParamsForma("estrella", w, 150, relleno=formas.Relleno("color", ((20, 20, 20, 255),)))
                doc = doc.agregar(Capa(f"t{i + 1}", "forma", "F", params=p, transform=Transformacion(540, y)))
            self.con = "formas en lugar de textos (falta texto.py)"
        self.doc = doc

    def test_componer_y_mover(self):
        # Con los textos ya dibujados (en la caché de generados), sin caché de composición.
        componer(self.doc, self.alm, None)
        tiempos = []
        for _ in range(5):
            t0 = time.perf_counter()
            componer(self.doc, self.alm, None)
            tiempos.append(time.perf_counter() - t0)
        print(f"\n  flyer 1080x1920 ({self.con}), sin caché: {min(tiempos) * 1000:.1f} ms")
        self.assertLess(min(tiempos), 0.120)
        cache = CacheComposicion()
        componer(self.doc, self.alm, None, cache=cache)
        for capa in ("img0", "banda", "img2"):
            tiempos = []
            for k in range(6):
                t = self.doc.capa(capa).transform
                doc = self.doc.con_capa(capa, transform=Transformacion(t.x + 7 * k + 1, t.y + 3 * k, t.escala,
                                                                       t.rotacion))
                t0 = time.perf_counter()
                componer(doc, self.alm, None, cache=cache)
                tiempos.append(time.perf_counter() - t0)
            print(f"  con caché, moviendo «{capa}»: {min(tiempos) * 1000:.1f} ms")
            self.assertLess(min(tiempos), 0.060)


if __name__ == "__main__":
    unittest.main()
