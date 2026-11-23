"""Pruebas del documento de capas (``motor/documento.py``): reglas, funciones puras,
``AlmacenImagenes``, ``componer`` y su caché.

Las imágenes se generan acá mismo (degradados, bloques de color y logos RGBA). La
regresión clave: sin capas extra, ``componer`` da exactamente ``filtro(foto)``, con el
procesado "celular natural" de verdad (``procesar_pila`` con el preset principal).
"""

from __future__ import annotations

import gc
import pickle
import sys
import threading
import time
import tracemalloc
import unittest
import weakref
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from celular_natural.motor import PRESET_PRINCIPAL, PRESETS, procesar_pila  # noqa: E402
from celular_natural.motor import documento as m_documento  # noqa: E402
from celular_natural.motor.documento import (  # noqa: E402
    AlmacenImagenes, CacheComposicion, Capa, Documento, Transformacion, capas_faltantes, componer, esquinas,
    tamano_salida, transformacion_ajustada,
)

PRESET = PRESETS[PRESET_PRINCIPAL]


def foto_sintetica(w: int = 160, h: int = 120, semilla: int = 0) -> np.ndarray:
    """Degradado con bloques y algo de textura: RGB uint8."""
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.stack([xx / max(1, w - 1), yy / max(1, h - 1), 0.5 + 0.3 * np.sin(xx / 7.0) * np.cos(yy / 5.0)], -1)
    img[h // 4:h // 2, w // 4:w // 2] = (0.9, 0.2, 0.1)
    img += rng.normal(0, 0.02, img.shape).astype(np.float32)
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def logo(w: int, h: int, color=(20, 200, 60), semilla: int = 1, opaco: bool = False) -> np.ndarray:
    """RGBA uint8: un disco de color con borde suave y textura (alfa 255 adentro si ``opaco``)."""
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rgb = np.empty((h, w, 3), np.float32)
    for c in range(3):
        rgb[..., c] = color[c] + 40 * np.sin(xx / (3 + c)) + rng.normal(0, 5, (h, w))
    if opaco:
        alfa = np.full((h, w), 255.0, np.float32)
    else:
        r = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2))
        alfa = np.clip((1.0 - r) * 4.0, 0, 1) * 255
    return np.dstack([np.clip(rgb, 0, 255), alfa]).round().astype(np.uint8)


def filtro_real(rgb: np.ndarray) -> np.ndarray:
    return procesar_pila(rgb, [PRESET])


class ContadorFiltro:
    """Un filtro simple (invierte y oscurece) que cuenta cuántas veces lo llaman."""

    def __init__(self):
        self.llamadas = 0
        self.candado = threading.Lock()

    def __call__(self, rgb: np.ndarray) -> np.ndarray:
        with self.candado:
            self.llamadas += 1
        return (255 - rgb) // 2


def doc_con_imagen(almacen: AlmacenImagenes, w=160, h=120, img=None, **cambios):
    """Documento nuevo con una capa imagen (centrada, escala 1) y la capa nueva."""
    if img is None:
        img = logo(60, 40)
    doc = Documento.nuevo(w, h)
    doc = doc.agregar_imagen(almacen.guardar(img), "Logo", id_capa="logo")
    if cambios:
        doc = doc.con_capa("logo", **cambios)
    return doc


# ---------------------------------------------------------------------------
# Reglas y funciones puras
# ---------------------------------------------------------------------------

class TestReglas(unittest.TestCase):

    def test_nuevo(self):
        doc = Documento.nuevo(800, 600)
        self.assertEqual((doc.ancho, doc.alto), (800, 600))
        self.assertEqual([c.tipo for c in doc.capas], ["foto", "ajuste_natural"])
        self.assertEqual(len({c.id for c in doc.capas}), 2)
        self.assertTrue(all(c.visible and c.opacidad == 1.0 and c.fusion == "normal" for c in doc.capas))

    def test_inmutable_y_pickle(self):
        alm = AlmacenImagenes()
        doc = doc_con_imagen(alm, opacidad=0.4, fusion="pantalla",
                             transform=Transformacion(10.5, 20, 1.5, 30, True))
        with self.assertRaises(FrozenInstanceError):
            doc.ancho = 5
        with self.assertRaises(FrozenInstanceError):
            doc.capas[1].opacidad = 0.2
        self.assertEqual(pickle.loads(pickle.dumps(doc)), doc)
        self.assertEqual(hash(doc), hash(pickle.loads(pickle.dumps(doc))))

    def test_documento_invalido(self):
        foto = Capa("f", "foto", "Foto")
        ajuste = Capa("a", "ajuste_natural", "Celular natural")
        img = Capa("i", "imagen", "Logo", imagen="abc")
        Documento(10, 10, (foto, img, ajuste))
        Documento(10, 10, (foto,))   # sin ajuste también vale
        Documento(10, 10, [foto, img])   # una lista pasa a tupla
        with self.assertRaises(ValueError):
            Documento(10, 10, (img, foto, ajuste))     # la foto va abajo
        with self.assertRaises(ValueError):
            Documento(10, 10, ())
        with self.assertRaises(ValueError):
            Documento(10, 10, (foto, ajuste, img))     # el ajuste va arriba de todo
        with self.assertRaises(ValueError):
            Documento(10, 10, (foto, Capa("a2", "ajuste_natural", "Otro"), ajuste))
        with self.assertRaises(ValueError):
            Documento(10, 10, (foto, Capa("f2", "foto", "Otra foto"), ajuste))
        with self.assertRaises(ValueError):
            Documento(10, 10, (foto, Capa("f", "imagen", "Repetida", imagen="x"), ajuste))   # id repetido
        with self.assertRaises(ValueError):
            Documento(0, 10, (foto, ajuste))
        with self.assertRaises(ValueError):
            Documento(10, -3, (foto, ajuste))

    def test_capa_invalida(self):
        with self.assertRaises(ValueError):
            Capa("x", "texto", "Texto")
        with self.assertRaises(ValueError):
            Capa("x", "imagen", "Sin imagen")
        with self.assertRaises(ValueError):
            Capa("x", "foto", "Foto", imagen="abc")
        with self.assertRaises(ValueError):
            Capa("x", "foto", "Foto", fusion="disolver")
        with self.assertRaises(ValueError):
            Capa("", "foto", "Foto")
        with self.assertRaises(ValueError):
            Capa("x", "foto", "Foto", opacidad=float("nan"))
        self.assertEqual(Capa("x", "foto", "F", opacidad=1.7).opacidad, 1.0)
        self.assertEqual(Capa("x", "foto", "F", opacidad=-2).opacidad, 0.0)
        with self.assertRaises(ValueError):
            Transformacion(escala=0)
        with self.assertRaises(ValueError):
            Transformacion(x=float("inf"))

    def test_agregar_imagen(self):
        doc = Documento.nuevo(200, 100)
        d1 = doc.agregar_imagen("img1", "Uno", id_capa="uno")
        self.assertEqual(len(doc.capas), 2)   # el original no cambia
        self.assertEqual([c.id for c in d1.capas][1], "uno")
        self.assertEqual(d1.capas[-1].tipo, "ajuste_natural")
        uno = d1.capa("uno")
        self.assertEqual((uno.tipo, uno.nombre, uno.imagen), ("imagen", "Uno", "img1"))
        self.assertEqual((uno.transform.x, uno.transform.y, uno.transform.escala), (100.0, 50.0, 1.0))
        # Sin encima_de: arriba de todas las imágenes (debajo del ajuste).
        d2 = d1.agregar_imagen("img2", "Dos", id_capa="dos")
        self.assertEqual([c.id for c in d2.capas][1:3], ["uno", "dos"])
        # encima_de: justo arriba de esa capa.
        d3 = d2.agregar_imagen("img3", "Tres", encima_de=d2.capas[0].id, id_capa="tres")
        self.assertEqual([c.id for c in d3.capas][1:4], ["tres", "uno", "dos"])
        d4 = d3.agregar_imagen("img4", "Cuatro", encima_de=d3.capas[-1].id, id_capa="cuatro")
        self.assertEqual(d4.capas[-1].tipo, "ajuste_natural")   # arriba del ajuste no se puede: queda debajo
        self.assertEqual(d4.capas[-2].id, "cuatro")
        # id automático, único.
        d5 = d4.agregar_imagen("img1", "Otra")
        self.assertEqual(len({c.id for c in d5.capas}), len(d5.capas))
        with self.assertRaises(ValueError):
            d4.agregar_imagen("img5", "Repetida", id_capa="uno")
        with self.assertRaises(KeyError):
            d4.agregar_imagen("img5", "X", encima_de="no-existe")
        t = Transformacion(3, 4, 0.5, 10)
        self.assertEqual(doc.agregar_imagen("i", "T", transform=t, id_capa="t").capa("t").transform, t)

    def test_quitar(self):
        doc = Documento.nuevo(50, 50).agregar_imagen("a", "A", id_capa="a")
        self.assertEqual(len(doc.quitar("a").capas), 2)
        with self.assertRaises(ValueError):
            doc.quitar(doc.capas[0].id)    # la foto no se borra
        with self.assertRaises(ValueError):
            doc.quitar(doc.capas[-1].id)   # el ajuste tampoco (se oculta)
        with self.assertRaises(KeyError):
            doc.quitar("nada")

    def test_mover(self):
        doc = Documento.nuevo(50, 50)
        for n in "abc":
            doc = doc.agregar_imagen(n, n.upper(), id_capa=n)
        orden = lambda d: [c.id for c in d.capas[1:-1]]   # noqa: E731
        self.assertEqual(orden(doc), ["a", "b", "c"])
        self.assertEqual(orden(doc.mover("a", 1)), ["b", "a", "c"])
        self.assertEqual(orden(doc.mover("c", -2)), ["c", "a", "b"])
        self.assertEqual(orden(doc.mover("a", 10)), ["b", "c", "a"])    # no pasa arriba del ajuste
        self.assertEqual(orden(doc.mover("c", -10)), ["c", "a", "b"])   # ni abajo de la foto
        self.assertEqual(doc.mover("a", 10).capas[-1].tipo, "ajuste_natural")
        self.assertEqual(doc.mover("b", 0), doc)
        with self.assertRaises(ValueError):
            doc.mover(doc.capas[0].id, 1)
        with self.assertRaises(ValueError):
            doc.mover(doc.capas[-1].id, -1)

    def test_duplicar(self):
        doc = Documento.nuevo(50, 50).agregar_imagen("a", "A", id_capa="a")
        doc = doc.con_capa("a", opacidad=0.3, fusion="color", transform=Transformacion(1, 2, 3, 4, True))
        d2 = doc.duplicar("a", id_capa="a2")
        self.assertEqual([c.id for c in d2.capas][1:3], ["a", "a2"])
        copia = d2.capa("a2")
        self.assertEqual((copia.imagen, copia.opacidad, copia.fusion, copia.transform),
                         ("a", 0.3, "color", Transformacion(1, 2, 3, 4, True)))
        self.assertNotEqual(copia.nombre, "")
        d3 = doc.duplicar("a")
        self.assertEqual(len({c.id for c in d3.capas}), 4)
        with self.assertRaises(ValueError):
            doc.duplicar(doc.capas[0].id)
        with self.assertRaises(ValueError):
            doc.duplicar(doc.capas[-1].id)

    def test_con_capa_capa_e_indice(self):
        doc = Documento.nuevo(50, 50).agregar_imagen("a", "A", id_capa="a")
        foto, ajuste = doc.capas[0].id, doc.capas[-1].id
        d2 = doc.con_capa("a", nombre="Logo", visible=False, bloqueada=True, mascara="m")
        c = d2.capa("a")
        self.assertEqual((c.nombre, c.visible, c.bloqueada, c.mascara), ("Logo", False, True, "m"))
        self.assertEqual(doc.capa("a").nombre, "A")
        d3 = doc.con_capa(ajuste, opacidad=0.5, fusion="luminosidad")
        self.assertEqual(d3.capa(ajuste).opacidad, 0.5)
        self.assertEqual(d3.con_capa(foto, visible=False).capa(foto).visible, False)
        self.assertEqual(doc.indice("a"), 1)
        self.assertEqual(doc.indice(ajuste), 2)
        with self.assertRaises(KeyError):
            doc.capa("nada")
        with self.assertRaises(KeyError):
            doc.indice("nada")
        with self.assertRaises(ValueError):
            doc.con_capa("a", id="b")
        with self.assertRaises(ValueError):
            doc.con_capa("a", tipo="foto")
        with self.assertRaises(ValueError):
            doc.con_capa("a", fusion="nada")
        with self.assertRaises(TypeError):
            doc.con_capa("a", color="rojo")

    def test_tope_de_tamano(self):
        Documento.nuevo(65535, 1)
        Documento.nuevo(20000, 20000)   # 400 MP
        for ancho, alto in ((10 ** 6, 10 ** 6), (65536, 10), (10, 65536), (30000, 20000)):
            with self.assertRaises(ValueError):
                Documento.nuevo(ancho, alto)
        d = Documento.nuevo(10, 10).como_dict()
        d["ancho"] = 10 ** 6
        with self.assertRaises(ValueError):
            Documento.desde_dict(d)

    def test_tipos_estrictos(self):
        with self.assertRaises(ValueError):
            Capa("x", "foto", "F", visible=1)          # verdadero o falso, no 0/1
        with self.assertRaises(ValueError):
            Capa("x", "foto", "F", bloqueada="false")
        with self.assertRaises(ValueError):
            Capa("x", "foto", "F", opacidad=True)      # un booleano no es un número
        with self.assertRaises(ValueError):
            Transformacion(escala=True)
        d = Documento.nuevo(10, 10).como_dict()
        d["capas"][0]["visible"] = 1
        with self.assertRaises(ValueError):
            Documento.desde_dict(d)
        self.assertFalse(Capa("x", "foto", "F", visible=np.bool_(False)).visible)

    def test_ids_usados(self):
        doc = Documento.nuevo(50, 50).agregar_imagen("a", "A", id_capa="a").agregar_imagen("b", "B")
        doc = doc.con_capa("a", mascara="m1").con_capa(doc.capas[-1].id, mascara="m2")
        self.assertEqual(doc.ids_usados(), {"a", "b", "m1", "m2"})

    def test_como_dict_ida_y_vuelta(self):
        doc = Documento.nuevo(64, 48).agregar_imagen("a", "Á ñ", id_capa="a")
        doc = doc.con_capa("a", opacidad=0.37, fusion="tono", mascara="m", bloqueada=True,
                           transform=Transformacion(1.25, -3, 0.75, -45.5, True))
        self.assertEqual(Documento.desde_dict(doc.como_dict()), doc)
        with self.assertRaises(ValueError):
            Documento.desde_dict({"ancho": 5})
        with self.assertRaises(ValueError):
            Documento.desde_dict("nada")

    def test_transformacion_ajustada_y_esquinas(self):
        t = transformacion_ajustada(400, 200, 200, 100)   # más grande: se achica para entrar
        self.assertEqual((t.x, t.y), (100.0, 50.0))
        self.assertAlmostEqual(t.escala, 0.5)
        t = transformacion_ajustada(40, 20, 200, 100)     # más chica: queda a tamaño real
        self.assertEqual(t.escala, 1.0)
        e = esquinas(Transformacion(100, 50, 2.0, 0), 40, 20)
        np.testing.assert_allclose(e, [[60, 30], [140, 30], [140, 70], [60, 70]])
        # 90° horario: la esquina de arriba a la izquierda queda arriba a la derecha.
        e = esquinas(Transformacion(0, 0, 1.0, 90), 40, 20)
        np.testing.assert_allclose(e[0], [10, -20], atol=1e-9)


# ---------------------------------------------------------------------------
# Almacén
# ---------------------------------------------------------------------------

class TestAlmacen(unittest.TestCase):

    def test_por_contenido(self):
        alm = AlmacenImagenes()
        a = logo(30, 20)
        i1 = alm.guardar(a)
        self.assertEqual(alm.guardar(a.copy()), i1)
        self.assertNotEqual(alm.guardar(logo(30, 20, semilla=9)), i1)
        self.assertNotEqual(alm.guardar(a[..., :3].copy()), i1)            # otra forma, otro id
        self.assertNotEqual(alm.guardar(a.reshape(20, 30 * 4).copy()), i1)  # mismos bytes, otra forma
        self.assertEqual(len(alm.ids()), 4)
        self.assertIn(i1, alm)
        guardada = alm.obtener(i1)
        np.testing.assert_array_equal(guardada, a)
        self.assertFalse(guardada.flags.writeable)
        a[0, 0] = 0   # cambiar el original no cambia lo guardado
        self.assertFalse(np.array_equal(alm.obtener(i1), a))
        with self.assertRaises(KeyError):
            alm.obtener("nada")
        with self.assertRaises(ValueError):
            alm.guardar(np.zeros((4, 4, 3), np.float32))
        with self.assertRaises(ValueError):
            alm.guardar(np.zeros((4, 4, 2), np.uint8))

    def test_varios_hilos(self):
        alm = AlmacenImagenes()
        imagenes = [logo(16, 12, semilla=s) for s in range(20)]
        ids_esperados = {AlmacenImagenes().guardar(i) for i in imagenes}
        errores, ids_vistos = [], []

        def trabajo(k):
            try:
                for j in range(60):
                    img = imagenes[(k * 7 + j) % len(imagenes)]
                    i = alm.guardar(img)
                    np.testing.assert_array_equal(alm.obtener(i), img)
                    ids_vistos.append(i)
                    alm.ids()
            except Exception as e:  # pragma: no cover
                errores.append(e)

        hilos = [threading.Thread(target=trabajo, args=(k,)) for k in range(8)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual(errores, [])
        self.assertEqual(alm.ids(), ids_esperados)
        self.assertEqual(set(ids_vistos), ids_esperados)


# ---------------------------------------------------------------------------
# componer
# ---------------------------------------------------------------------------

class TestComponer(unittest.TestCase):

    def setUp(self):
        self.foto = foto_sintetica()
        self.alm = AlmacenImagenes()

    def test_regresion_sin_capas_es_el_filtro_bit_a_bit(self):
        doc = Documento.nuevo(160, 120)
        esperado = filtro_real(self.foto)
        salida = componer(doc, self.alm, self.foto, filtro=filtro_real)
        self.assertEqual(salida.dtype, np.uint8)
        np.testing.assert_array_equal(salida, esperado)
        # Con caché, igual (y también la segunda vez, ya desde la caché).
        cache = CacheComposicion()
        np.testing.assert_array_equal(componer(doc, self.alm, self.foto, filtro=filtro_real, cache=cache), esperado)
        np.testing.assert_array_equal(componer(doc, self.alm, self.foto, filtro=filtro_real, cache=cache), esperado)
        # Una capa oculta o con opacidad 0 tampoco cambia nada.
        d2 = doc_con_imagen(self.alm, visible=False)
        np.testing.assert_array_equal(componer(d2, self.alm, self.foto, filtro=filtro_real), esperado)
        d3 = doc_con_imagen(self.alm, opacidad=0.0)
        np.testing.assert_array_equal(componer(d3, self.alm, self.foto, filtro=filtro_real), esperado)

    def test_sin_filtro_es_la_foto(self):
        doc = Documento.nuevo(160, 120)
        salida = componer(doc, self.alm, self.foto)
        np.testing.assert_array_equal(salida, self.foto)
        self.assertIsNot(salida, self.foto)
        antes = self.foto.copy()
        salida[0, 0] = 1   # es una copia: no toca la foto
        np.testing.assert_array_equal(self.foto, antes)

    def test_tamano_y_foto_equivocada(self):
        doc = Documento.nuevo(160, 120)
        self.assertEqual(tamano_salida(doc, 1.0), (120, 160))
        self.assertEqual(tamano_salida(doc, 0.25), (30, 40))
        self.assertEqual(tamano_salida(doc, 0.333), (40, 53))
        with self.assertRaises(ValueError):
            componer(doc, self.alm, self.foto[:60])
        with self.assertRaises(ValueError):
            componer(doc, self.alm, self.foto.astype(np.float32))
        with self.assertRaises(ValueError):
            componer(doc, self.alm, self.foto, escala=0)

    def test_imagen_opaca_normal_tapa(self):
        tapa = logo(160, 120, opaco=True)
        doc = doc_con_imagen(self.alm, img=tapa)
        salida = componer(doc, self.alm, self.foto)
        np.testing.assert_array_equal(salida, tapa[..., :3])
        # Una imagen RGB (sin alfa) también vale y tapa igual.
        doc = doc_con_imagen(self.alm, img=np.ascontiguousarray(tapa[..., :3]))
        np.testing.assert_array_equal(componer(doc, self.alm, self.foto), tapa[..., :3])

    def test_el_orden_importa(self):
        roja = np.zeros((120, 160, 4), np.uint8)
        roja[..., 0] = 255
        roja[..., 3] = 255
        azul = roja.copy()
        azul[..., 0], azul[..., 2] = 0, 255
        doc = Documento.nuevo(160, 120)
        doc = doc.agregar_imagen(self.alm.guardar(roja), "Roja", id_capa="r")
        doc = doc.agregar_imagen(self.alm.guardar(azul), "Azul", id_capa="a")
        self.assertEqual(tuple(componer(doc, self.alm, self.foto)[60, 80]), (0, 0, 255))
        self.assertEqual(tuple(componer(doc.mover("r", 1), self.alm, self.foto)[60, 80]), (255, 0, 0))

    def test_ocultar(self):
        doc = doc_con_imagen(self.alm, img=logo(160, 120, opaco=True))
        self.assertFalse(np.array_equal(componer(doc, self.alm, self.foto), self.foto))
        oculta = doc.con_capa("logo", visible=False)
        np.testing.assert_array_equal(componer(oculta, self.alm, self.foto), self.foto)

    def test_opacidad(self):
        tapa = logo(160, 120, opaco=True)
        doc = doc_con_imagen(self.alm, img=tapa, opacidad=0.5)
        salida = componer(doc, self.alm, self.foto).astype(np.int16)
        esperado = (self.foto.astype(np.float32) + tapa[..., :3]) / 2
        self.assertLessEqual(float(np.abs(salida - esperado).max()), 0.51)

    def test_fusion_en_la_capa(self):
        tapa = logo(160, 120, opaco=True)
        doc = doc_con_imagen(self.alm, img=tapa, fusion="multiplicar")
        salida = componer(doc, self.alm, self.foto).astype(np.float32)
        esperado = self.foto.astype(np.float32) * tapa[..., :3] / 255.0
        self.assertLessEqual(float(np.abs(salida - esperado).max()), 0.51)

    def test_cada_modo_contra_fusionar(self):
        # Capa semitransparente del tamaño del documento, con opacidad y máscara: lo que da
        # componer (con sus atajos por modo) contra fusionar directo sobre la foto.
        from celular_natural.motor.fusion import MODOS_FUSION, fusionar
        capa = logo(160, 120, (180, 90, 200), semilla=6)
        capa[..., 3] = np.clip(capa[..., 3].astype(int) + 60, 0, 255).astype(np.uint8)   # que haya de todo
        mascara = np.tile(np.linspace(0, 255, 160).astype(np.uint8), (120, 1))
        id_mascara = self.alm.guardar(mascara)
        for modo in MODOS_FUSION:
            doc = doc_con_imagen(self.alm, img=capa, fusion=modo, opacidad=0.7, mascara=id_mascara)
            salida = componer(doc, self.alm, self.foto).astype(np.float32)
            rgb, _ = fusionar(self.foto, None, capa[..., :3], capa[..., 3], modo, 0.7, mascara)
            dif = np.abs(salida - rgb * 255)
            self.assertLessEqual(float(dif.max()), 2.0, modo)
            self.assertLess(float(dif.mean()), 0.3, modo)

    def test_mascara_de_la_capa(self):
        tapa = logo(160, 120, opaco=True)
        mascara = np.zeros((120, 160), np.uint8)
        mascara[:, 80:] = 255
        doc = doc_con_imagen(self.alm, img=tapa, mascara=self.alm.guardar(mascara))
        salida = componer(doc, self.alm, self.foto)
        np.testing.assert_array_equal(salida[:, :79], self.foto[:, :79])
        np.testing.assert_array_equal(salida[:, 81:], tapa[:, 81:, :3])

    def test_foto_con_opacidad_y_oculta(self):
        doc = Documento.nuevo(160, 120)
        foto_id = doc.capas[0].id
        media = componer(doc.con_capa(foto_id, opacidad=0.5), self.alm, self.foto).astype(np.float32)
        esperado = (self.foto.astype(np.float32) + 255) / 2   # lo transparente se aplana sobre blanco
        self.assertLessEqual(float(np.abs(media - esperado).max()), 0.51)
        oculta = componer(doc.con_capa(foto_id, visible=False), self.alm, self.foto)
        self.assertTrue((oculta == 255).all())

    def test_transformacion_contra_warpaffine(self):
        img = logo(40, 30, opaco=True, semilla=4)
        t = Transformacion(x=70.25, y=55.5, escala=1.5, rotacion=30.0)
        doc = doc_con_imagen(self.alm, img=img, transform=t)
        salida = componer(doc, self.alm, self.foto)
        # Lo mismo, directo con OpenCV: centro de la imagen en (x, y) del documento, en coordenadas de
        # píxel de OpenCV (el centro del píxel 0 es 0, así que se resta 0,5); getRotationMatrix2D gira
        # antihorario con ángulo positivo, así que va con -rotación.
        m = cv2.getRotationMatrix2D((40 / 2 - 0.5, 30 / 2 - 0.5), -t.rotacion, t.escala)
        m[0, 2] += (t.x - 0.5) - (40 / 2 - 0.5)
        m[1, 2] += (t.y - 0.5) - (30 / 2 - 0.5)
        warp = cv2.warpAffine(img, m, (160, 120), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                              borderValue=(0, 0, 0, 0)).astype(np.float32)
        # La imagen es opaca y el borde, negro transparente: en el contorno, el RGB interpolado ya
        # queda premultiplicado por el alfa interpolado (fondo·(1 - a) + rgb, sin multiplicar de nuevo).
        a = warp[..., 3:] / 255.0
        esperado = self.foto * (1 - a) + warp[..., :3]
        dif = np.abs(salida.astype(np.float32) - esperado)
        self.assertLessEqual(float(dif.max()), 3.0)
        self.assertLess(float(dif.mean()), 0.1)
        self.assertGreater(float((a > 0.99).mean()), 0.1)   # la capa se ve, y bastante

    def test_rotacion_horaria_y_volteo(self):
        img = np.zeros((20, 20, 4), np.uint8)
        img[..., 3] = 255
        img[8:12, 16:20, 0] = 255    # rojo a la derecha
        base = np.zeros((100, 100, 3), np.uint8)

        def donde_rojo(t):
            doc = Documento.nuevo(100, 100).agregar_imagen(self.alm.guardar(img), "I", transform=t)
            salida = componer(doc, self.alm, base)
            ys, xs = np.nonzero(salida[..., 0] > 128)
            return float(xs.mean()), float(ys.mean())

        x, y = donde_rojo(Transformacion(50, 50))
        self.assertGreater(x, 55)
        self.assertAlmostEqual(y, 50, delta=1)
        x, y = donde_rojo(Transformacion(50, 50, rotacion=90))   # horario: la derecha pasa abajo
        self.assertAlmostEqual(x, 50, delta=1)
        self.assertGreater(y, 55)
        x, y = donde_rojo(Transformacion(50, 50, voltear_h=True))
        self.assertLess(x, 45)
        x, y = donde_rojo(Transformacion(50, 50, escala=2.0))
        self.assertGreater(x, 65)

    def test_escala_de_vista_previa(self):
        foto = foto_sintetica(400, 300)
        img = logo(120, 80, opaco=True)
        doc = doc_con_imagen(self.alm, 400, 300, img=img, transform=Transformacion(130, 100, 1.0, 15))
        completa = componer(doc, self.alm, foto)
        vista_foto = cv2.resize(foto, (100, 75), interpolation=cv2.INTER_AREA)
        vista = componer(doc, self.alm, vista_foto, escala=0.25)
        self.assertEqual(completa.shape, (300, 400, 3))
        self.assertEqual(vista.shape, (75, 100, 3))
        reducida = cv2.resize(completa, (100, 75), interpolation=cv2.INTER_AREA)
        dif = np.abs(vista.astype(np.float32) - reducida)
        self.assertLess(float(dif.mean()), 4.0)

    def test_achicar_mucho_promedia(self):
        # Un damero de cuadros de 4 píxeles achicado al 10 %: con INTER_AREA da casi gris; muestreado
        # con bilineal solo (un punto cada 10 píxeles), daría manchas negras y blancas (moiré).
        damero = (((np.indices((400, 400)) // 4).sum(0) % 2) * 255).astype(np.uint8)
        img = np.dstack([damero, damero, damero, np.full_like(damero, 255)])
        doc = doc_con_imagen(self.alm, img=img, transform=Transformacion(80, 60, 0.1))
        salida = componer(doc, self.alm, self.foto).astype(np.float32)
        centro = salida[60 - 15:60 + 15, 80 - 15:80 + 15]
        self.assertLess(float(np.abs(centro - 127.5).max()), 40)

    def test_borde_transparente_sin_halo_oscuro(self):
        # Disco rojo con borde suave y el RGB de lo transparente en negro, girado y escalado sobre
        # blanco: premultiplicado, el rojo nunca baja (sin premultiplicar, el borde se oscurecería).
        h = w = 60
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        alfa = np.clip((25 - np.hypot(xx - 30, yy - 30)) / 3, 0, 1)
        img = np.zeros((h, w, 4), np.uint8)
        img[..., 0] = np.where(alfa > 0, 255, 0)
        img[..., 3] = (alfa * 255).round()
        blanco = np.full((120, 160, 3), 255, np.uint8)
        doc = doc_con_imagen(self.alm, img=img, transform=Transformacion(80, 60, 1.37, 17))
        salida = componer(doc, self.alm, blanco)
        self.assertGreaterEqual(int(salida[..., 0].min()), 254)
        self.assertLess(int(salida[..., 1].min()), 10)   # y el disco se ve

    def test_capa_por_capa_igual_que_por_franjas(self):
        # Los dos recorridos de _componer_abajo dan lo mismo, bit a bit (con fondo opaco y con alfa).
        mascara = np.tile(np.linspace(0, 255, 160).astype(np.uint8), (120, 1))
        id_m = self.alm.guardar(mascara)
        doc = Documento.nuevo(160, 120)
        modos = ("normal", "multiplicar", "pantalla", "luz_suave", "color", "diferencia")
        for k, modo in enumerate(modos):
            doc = doc.agregar_imagen(self.alm.guardar(logo(70, 50, semilla=k)), modo, id_capa=modo,
                                     transform=Transformacion(30 + 20 * k, 40 + 8 * k, 1.2, 15 * k, k % 2 == 1))
            doc = doc.con_capa(modo, fusion=modo, opacidad=0.8, mascara=id_m if k % 2 else None)
        for d in (doc, doc.con_capa(doc.foto.id, opacidad=0.6, mascara=id_m)):
            por_franjas = componer(d, self.alm, self.foto)
            with mock.patch.object(m_documento, "_MEMORIA_CAPAS", 0):
                capa_por_capa = componer(d, self.alm, self.foto)
            np.testing.assert_array_equal(capa_por_capa, por_franjas)

    def test_memoria_sin_cache(self):
        # 6 capas del tamaño del documento, con máscara, sin caché: va capa por capa y la memoria
        # extra queda acotada (antes: todas las capas transformadas y las máscaras en float a la vez).
        ancho, alto = 1200, 900
        foto = foto_sintetica(ancho, alto)
        mascara = self.alm.guardar(np.tile(np.linspace(0, 255, ancho).astype(np.uint8), (alto, 1)))
        doc = Documento.nuevo(ancho, alto)
        for k in range(6):
            doc = doc.agregar_imagen(self.alm.guardar(logo(ancho, alto, semilla=k, opaco=True)), str(k),
                                     id_capa=f"c{k}", transform=Transformacion(ancho / 2 + k, alto / 2, 1.0, k))
            doc = doc.con_capa(f"c{k}", mascara=mascara)
        with mock.patch.object(m_documento, "_MEMORIA_CAPAS", 0):
            componer(doc, self.alm, foto)
            tracemalloc.start()
            try:
                base, _ = tracemalloc.get_traced_memory()
                tracemalloc.reset_peak()
                componer(doc, self.alm, foto)
                _, pico = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
        por_pixel = (pico - base) / (ancho * alto)
        # Lienzo float (12 B/px), salida (3), una capa transformada y su copia en planos (8), la
        # preparada (4) y su máscara (1): unos 28 B/px. Con todas a la vez eran más de 100.
        self.assertLess(por_pixel, 40, f"{por_pixel:.1f} bytes por píxel")

    def test_mascara_queda_en_uint8_en_la_cache(self):
        mascara = np.full((120, 160), 200, np.uint8)
        doc = doc_con_imagen(self.alm, mascara=self.alm.guardar(mascara))
        cache = CacheComposicion()
        componer(doc, self.alm, cv2.resize(self.foto, (80, 60)), 0.5, cache=cache)
        mascaras = [v[0] for k, v in cache._entradas.items() if k[0] == "mascara"]
        self.assertEqual(len(mascaras), 1)
        self.assertEqual((mascaras[0].dtype, mascaras[0].shape), (np.uint8, (60, 80)))

    def test_imagen_que_falta(self):
        doc = Documento.nuevo(160, 120).agregar_imagen("no-esta", "Perdida", id_capa="p")
        self.assertEqual(capas_faltantes(doc, self.alm), ("p",))
        np.testing.assert_array_equal(componer(doc, self.alm, self.foto), self.foto)
        doc = doc.con_capa("p", mascara="tampoco")
        np.testing.assert_array_equal(componer(doc, self.alm, self.foto), self.foto)
        self.assertEqual(capas_faltantes(Documento.nuevo(5, 5), self.alm), ())

    def test_capa_fuera_del_documento(self):
        doc = doc_con_imagen(self.alm, transform=Transformacion(-500, -500))
        np.testing.assert_array_equal(componer(doc, self.alm, self.foto), self.foto)


class TestAjusteNatural(unittest.TestCase):

    def setUp(self):
        self.foto = foto_sintetica()
        self.alm = AlmacenImagenes()
        self.doc = doc_con_imagen(self.alm)
        self.ajuste = self.doc.capas[-1].id

    def test_el_filtro_va_sobre_la_composicion(self):
        sin = componer(self.doc, self.alm, self.foto)
        con = componer(self.doc, self.alm, self.foto, filtro=filtro_real)
        np.testing.assert_array_equal(con, filtro_real(sin))

    def test_ajuste_oculto_es_sin_filtro(self):
        oculto = self.doc.con_capa(self.ajuste, visible=False)
        np.testing.assert_array_equal(componer(oculto, self.alm, self.foto, filtro=filtro_real),
                                      componer(self.doc, self.alm, self.foto))

    def test_ajuste_a_la_mitad(self):
        sin = componer(self.doc, self.alm, self.foto).astype(np.float32)
        con = componer(self.doc, self.alm, self.foto, filtro=filtro_real).astype(np.float32)
        medio = componer(self.doc.con_capa(self.ajuste, opacidad=0.5), self.alm, self.foto, filtro=filtro_real)
        self.assertLessEqual(float(np.abs(medio - (sin + con) / 2).max()), 0.51)

    def test_ajuste_con_mascara_y_fusion(self):
        mascara = np.zeros((120, 160), np.uint8)
        mascara[60:] = 255
        doc = self.doc.con_capa(self.ajuste, mascara=self.alm.guardar(mascara))
        sin = componer(self.doc, self.alm, self.foto)
        con = componer(self.doc, self.alm, self.foto, filtro=filtro_real)
        salida = componer(doc, self.alm, self.foto, filtro=filtro_real)
        np.testing.assert_array_equal(salida[:59], sin[:59])
        np.testing.assert_array_equal(salida[61:], con[61:])
        lum = componer(self.doc.con_capa(self.ajuste, fusion="luminosidad"), self.alm, self.foto, filtro=filtro_real)
        self.assertFalse(np.array_equal(lum, con))

    def test_filtro_que_devuelve_lo_mismo(self):
        doc = Documento.nuevo(160, 120)
        salida = componer(doc, self.alm, self.foto, filtro=lambda x: x, cache=CacheComposicion())
        np.testing.assert_array_equal(salida, self.foto)
        self.assertTrue(self.foto.flags.writeable)   # la foto de la interfaz no queda de solo lectura
        self.assertIsNot(salida, self.foto)

    def test_cache_no_retiene_la_foto_y_respeta_el_tope(self):
        doc = Documento.nuevo(160, 120)
        tope = 3 * self.foto.nbytes + 1000
        cache = CacheComposicion(max_bytes=tope)
        foto = self.foto.copy()
        ref = weakref.ref(foto)
        for k in range(8):   # un filtro nuevo en cada llamada: nunca acierta, pero no crece
            componer(doc, self.alm, foto, filtro=lambda x, k=k: (x // 2 + k).astype(np.uint8), cache=cache)
            self.assertLessEqual(cache.bytes_usados, tope)
        del foto
        gc.collect()
        self.assertIsNone(ref())   # la caché no se quedó con la foto

    def test_cache_nota_la_foto_cambiada_en_su_lugar(self):
        doc = Documento.nuevo(160, 120)
        filtro = ContadorFiltro()
        cache = CacheComposicion()
        foto = self.foto.copy()
        primera = componer(doc, self.alm, foto, filtro=filtro, cache=cache)
        foto[:] = 255 - foto   # el mismo arreglo, cambiado en su lugar
        segunda = componer(doc, self.alm, foto, filtro=filtro, cache=cache)
        self.assertEqual(filtro.llamadas, 2)
        np.testing.assert_array_equal(segunda, filtro(foto))
        self.assertFalse(np.array_equal(primera, segunda))

    def test_cache_cuenta_un_minimo_por_entrada(self):
        cache = CacheComposicion(max_bytes=64 * 10)
        transparente = np.zeros((20, 20, 4), np.uint8)
        for k in range(40):   # capas toda transparentes: no ocupan nada, pero cuentan 64 bytes
            componer(doc_con_imagen(self.alm, img=transparente, transform=Transformacion(80 + k / 10, 60)),
                     self.alm, self.foto, cache=cache)
        self.assertLessEqual(len(cache._entradas), 10)
        self.assertLessEqual(cache.bytes_usados, 64 * 10)

    def test_documento_sin_ajuste(self):
        doc = Documento(160, 120, self.doc.capas[:-1])
        np.testing.assert_array_equal(componer(doc, self.alm, self.foto, filtro=filtro_real),
                                      componer(self.doc, self.alm, self.foto))

    def test_cache_cuenta_llamadas_al_filtro(self):
        filtro = ContadorFiltro()
        cache = CacheComposicion()
        doc = self.doc

        def comp(d):
            return componer(d, self.alm, self.foto, filtro=filtro, cache=cache)

        primera = comp(doc)
        self.assertEqual(filtro.llamadas, 1)
        np.testing.assert_array_equal(comp(doc), primera)
        self.assertEqual(filtro.llamadas, 1)
        # Lo que no cambia los píxeles de abajo no recalcula el filtro.
        comp(doc.con_capa("logo", nombre="Otro nombre", bloqueada=True))
        comp(doc.con_capa(self.ajuste, opacidad=0.4))
        comp(doc.con_capa(self.ajuste, fusion="color"))
        self.assertEqual(filtro.llamadas, 1)
        # "Subir" la capa todo lo posible: el ajuste sigue arriba, nada cambia abajo.
        subida = doc.mover("logo", 5)
        self.assertEqual(subida.capas[-1].id, self.ajuste)
        comp(subida)
        self.assertEqual(filtro.llamadas, 1)
        # Mover la capa en la vista: cambia lo de abajo, una llamada más.
        movida = doc.con_capa("logo", transform=Transformacion(30, 30))
        comp(movida)
        self.assertEqual(filtro.llamadas, 2)
        # Ocultarla: otra; volver a mostrarla usa la caché.
        oculta = doc.con_capa("logo", visible=False)
        comp(oculta)
        self.assertEqual(filtro.llamadas, 3)
        np.testing.assert_array_equal(comp(doc), primera)
        self.assertEqual(filtro.llamadas, 3)
        # Otro filtro (otros ajustes): se recalcula.
        otro = ContadorFiltro()
        componer(doc, self.alm, self.foto, filtro=otro, cache=cache)
        self.assertEqual(otro.llamadas, 1)
        # Otra foto (otro arreglo): también.
        componer(doc, self.alm, self.foto.copy(), filtro=filtro, cache=cache)
        self.assertEqual(filtro.llamadas, 4)
        # clave_foto: la interfaz puede decir que es la misma foto aunque sea otro arreglo.
        componer(doc, self.alm, self.foto.copy(), filtro=filtro, cache=cache, clave_foto="foto1")
        componer(doc, self.alm, self.foto.copy(), filtro=filtro, cache=cache, clave_foto="foto1")
        self.assertEqual(filtro.llamadas, 5)
        cache.limpiar()
        comp(doc)
        self.assertEqual(filtro.llamadas, 6)

    def test_cache_da_lo_mismo_que_sin_cache(self):
        cache = CacheComposicion()
        mascara = np.full((120, 160), 128, np.uint8)
        for doc in (self.doc,
                    self.doc.con_capa("logo", transform=Transformacion(40, 70, 0.8, -20, True)),
                    self.doc.con_capa("logo", mascara=self.alm.guardar(mascara), fusion="superponer"),
                    self.doc.con_capa(self.ajuste, opacidad=0.3)):
            mitad = cv2.resize(self.foto, (80, 60), interpolation=cv2.INTER_AREA)
            for escala, foto in ((1.0, self.foto), (0.5, mitad)):
                np.testing.assert_array_equal(
                    componer(doc, self.alm, foto, escala, filtro=filtro_real, cache=cache),
                    componer(doc, self.alm, foto, escala, filtro=filtro_real))

    def test_cache_desde_varios_hilos(self):
        cache = CacheComposicion()
        docs = [self.doc.con_capa("logo", transform=Transformacion(20 + 10 * k, 60)) for k in range(4)]
        esperados = [componer(d, self.alm, self.foto, filtro=filtro_real) for d in docs]
        errores = []

        def trabajo(k):
            try:
                for j in range(6):
                    i = (k + j) % len(docs)
                    np.testing.assert_array_equal(
                        componer(docs[i], self.alm, self.foto, filtro=filtro_real, cache=cache), esperados[i])
            except Exception as e:  # pragma: no cover
                errores.append(e)

        hilos = [threading.Thread(target=trabajo, args=(k,)) for k in range(4)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual(errores, [])


class TestVelocidad(unittest.TestCase):
    """1920×1080: foto + 3 capas imagen + ajuste, sin filtro. Se toma el mejor de varias vueltas."""

    def setUp(self):
        self.alm = AlmacenImagenes()
        self.foto = foto_sintetica(1920, 1080)
        doc = Documento.nuevo(1920, 1080)
        doc = doc.agregar_imagen(self.alm.guardar(logo(1200, 800, semilla=1)), "Uno", id_capa="uno",
                                 transform=Transformacion(700, 500, 1.0, 0))
        doc = doc.agregar_imagen(self.alm.guardar(logo(900, 700, (200, 60, 20), semilla=2)), "Dos", id_capa="dos",
                                 transform=Transformacion(1200, 600, 0.9, 25))
        doc = doc.agregar_imagen(self.alm.guardar(logo(600, 600, (40, 40, 220), semilla=3)), "Tres",
                                 id_capa="tres", transform=Transformacion(900, 400, 1.2, -10, True))
        doc = doc.con_capa("dos", fusion="multiplicar", opacidad=0.8)
        self.doc = doc.con_capa("tres", fusion="pantalla")

    def test_sin_cache(self):
        componer(self.doc, self.alm, self.foto)
        tiempos = []
        for _ in range(5):
            t0 = time.perf_counter()
            componer(self.doc, self.alm, self.foto)
            tiempos.append(time.perf_counter() - t0)
        print(f"\n  componer 1920x1080, 3 capas + ajuste, sin caché: {min(tiempos) * 1000:.1f} ms")
        self.assertLess(min(tiempos), 0.060)

    def test_con_cache_moviendo_una_capa(self):
        cache = CacheComposicion()
        componer(self.doc, self.alm, self.foto, cache=cache)
        for capa in ("tres", "uno"):
            tiempos = []
            for k in range(6):
                doc = self.doc.con_capa(capa, transform=Transformacion(800 + 7 * k, 450 + 3 * k, 1.1, 5))
                t0 = time.perf_counter()
                componer(doc, self.alm, self.foto, cache=cache)
                tiempos.append(time.perf_counter() - t0)
            print(f"\n  con caché, moviendo «{capa}»: {min(tiempos) * 1000:.1f} ms")
            self.assertLess(min(tiempos), 0.040)


if __name__ == "__main__":
    unittest.main()
