"""Pruebas del proyecto ``.nslite`` (``motor/proyecto_lite.py``): ida y vuelta, archivos
rotos, versión futura, imágenes que faltan, escritura atómica y que no se use pickle.

Todo se genera acá, en una carpeta temporal.
"""

from __future__ import annotations

import builtins
import io
import json
import os
import pickle
import struct
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from celular_natural.motor.documento import (  # noqa: E402
    AlmacenImagenes, Documento, Transformacion, capas_faltantes, componer,
)
from celular_natural.motor import proyecto_lite  # noqa: E402
from celular_natural.motor.proyecto_lite import FORMATO, abrir_proyecto, guardar_proyecto  # noqa: E402


def png_falso(ancho: int, alto: int, tipo_color: int = 6) -> bytes:
    """Un PNG chico (unos 60 bytes) que en el encabezado dice medir ``ancho`` × ``alto``."""
    def trozo(tipo: bytes, datos: bytes) -> bytes:
        return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos))
    ihdr = struct.pack(">IIBBBBB", ancho, alto, 8, tipo_color, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", ihdr) + trozo(b"IDAT", zlib.compress(bytes(64)))
            + trozo(b"IEND", b""))


def imagen_rgba(w=50, h=40, semilla=0) -> np.ndarray:
    rng = np.random.default_rng(semilla)
    return rng.integers(0, 256, (h, w, 4), dtype=np.uint8)


class _Trampa:
    """Al despicklearse crea un archivo: si aparece, alguien usó pickle."""

    def __init__(self, ruta):
        self.ruta = ruta

    def __reduce__(self):
        return (builtins.open, (self.ruta, "w"))


class TestProyecto(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.ruta = self.dir / "proyecto.nslite"
        self.alm = AlmacenImagenes()
        uno = self.alm.guardar(imagen_rgba(semilla=1))
        dos = self.alm.guardar(np.ascontiguousarray(imagen_rgba(30, 20, semilla=2)[..., :3]))
        mascara = self.alm.guardar(np.random.default_rng(3).integers(0, 256, (48, 64), dtype=np.uint8))
        self.alm.guardar(imagen_rgba(10, 10, semilla=9))   # en el almacén pero sin usar
        doc = Documento.nuevo(64, 48)
        doc = doc.agregar_imagen(uno, "Logo «uno»", id_capa="a", transform=Transformacion(20.5, 10, 0.75, 33.3, True))
        doc = doc.agregar_imagen(dos, "Foto dos", id_capa="b")
        doc = doc.con_capa("a", opacidad=0.37, fusion="luz_suave", mascara=mascara, bloqueada=True)
        doc = doc.con_capa("b", visible=False)
        self.doc = doc.con_capa(doc.capas[-1].id, opacidad=0.6, mascara=mascara)
        self.extra = {"foto": "C:/fotos/ñandú.jpg", "editor": {"preset": "Celular natural", "valores": [1, 2.5]}}

    def tearDown(self):
        self._tmp.cleanup()

    def _zip(self, archivos: dict) -> Path:
        ruta = self.dir / "a_mano.nslite"
        with zipfile.ZipFile(ruta, "w") as z:
            for nombre, datos in archivos.items():
                z.writestr(nombre, datos)
        return ruta

    def _json_valido(self, **cambios) -> bytes:
        datos = {"formato": FORMATO, "documento": Documento.nuevo(10, 10).como_dict(), "extra": {}}
        datos.update(cambios)
        return json.dumps(datos).encode("utf-8")

    def test_ida_y_vuelta(self):
        guardar_proyecto(self.ruta, self.doc, self.alm, self.extra)
        doc, alm, extra = abrir_proyecto(self.ruta)
        self.assertEqual(doc, self.doc)
        self.assertEqual(extra, self.extra)
        self.assertEqual(alm.ids(), self.doc.ids_usados())   # solo lo que se usa
        for i in self.doc.ids_usados():
            original = self.alm.obtener(i)
            np.testing.assert_array_equal(alm.obtener(i), original)
            self.assertEqual(alm.obtener(i).shape, original.shape)
        self.assertEqual(capas_faltantes(doc, alm), ())
        foto = np.random.default_rng(5).integers(0, 256, (48, 64, 3), dtype=np.uint8)
        np.testing.assert_array_equal(componer(doc, alm, foto), componer(self.doc, self.alm, foto))
        # Lo de adentro: documento.json con el formato, las imágenes y las máscaras en PNG.
        with zipfile.ZipFile(self.ruta) as z:
            nombres = set(z.namelist())
            datos = json.loads(z.read("documento.json"))
        self.assertEqual(datos["formato"], 1)
        self.assertIn(f"imagenes/{self.doc.capa('a').imagen}.png", nombres)
        self.assertIn(f"mascaras/{self.doc.capa('a').mascara}.png", nombres)
        self.assertTrue(all(n == "documento.json" or n.endswith(".png") for n in nombres))
        self.assertEqual([p.name for p in self.dir.iterdir()], ["proyecto.nslite"])   # sin temporales

    def test_sin_extra_y_sobrescribir(self):
        guardar_proyecto(self.ruta, self.doc, self.alm)
        self.assertEqual(abrir_proyecto(self.ruta)[2], {})
        otro = Documento.nuevo(8, 8)
        guardar_proyecto(str(self.ruta), otro, self.alm, {"x": 1})
        doc, alm, extra = abrir_proyecto(str(self.ruta))
        self.assertEqual((doc, extra, alm.ids()), (otro, {"x": 1}, set()))

    def test_extra_que_no_es_json(self):
        guardar_proyecto(self.ruta, self.doc, self.alm, {"a": 1})
        antes = self.ruta.read_bytes()
        with self.assertRaises((TypeError, ValueError)):
            guardar_proyecto(self.ruta, self.doc, self.alm, {"a": object()})
        self.assertEqual(self.ruta.read_bytes(), antes)
        self.assertEqual(len(list(self.dir.iterdir())), 1)

    def test_error_al_escribir_no_deja_nada(self):
        guardar_proyecto(self.ruta, self.doc, self.alm, self.extra)
        antes = self.ruta.read_bytes()
        with mock.patch("celular_natural.motor.proyecto_lite._png", side_effect=OSError("disco lleno")):
            with self.assertRaises(OSError):
                guardar_proyecto(self.ruta, Documento.nuevo(5, 5).agregar_imagen(
                    self.doc.capa("a").imagen, "x"), self.alm, {})
        self.assertEqual(self.ruta.read_bytes(), antes)
        self.assertEqual([p.name for p in self.dir.iterdir()], ["proyecto.nslite"])

    def test_imagen_que_no_esta_en_el_almacen(self):
        doc = self.doc.agregar_imagen("no-esta", "Perdida", id_capa="p")
        guardar_proyecto(self.ruta, doc, self.alm, {})
        doc2, alm2, _ = abrir_proyecto(self.ruta)
        self.assertEqual(doc2, doc)
        self.assertEqual(capas_faltantes(doc2, alm2), ("p",))

    def test_falta_una_imagen_en_el_zip(self):
        guardar_proyecto(self.ruta, self.doc, self.alm, {})
        falta = self.doc.capa("a").imagen
        incompleto = self.dir / "incompleto.nslite"
        with zipfile.ZipFile(self.ruta) as z, zipfile.ZipFile(incompleto, "w") as w:
            for info in z.infolist():
                if info.filename != f"imagenes/{falta}.png":
                    w.writestr(info, z.read(info.filename))
        doc, alm, _ = abrir_proyecto(incompleto)
        self.assertEqual(doc, self.doc)
        self.assertEqual(capas_faltantes(doc, alm), ("a",))

    def test_png_danado_es_imagen_que_falta(self):
        doc = Documento.nuevo(10, 10).agregar_imagen("abc", "Rota", id_capa="r")
        ruta = self._zip({"documento.json": self._json_valido(documento=doc.como_dict()),
                          "imagenes/abc.png": b"esto no es un png"})
        doc2, alm, _ = abrir_proyecto(ruta)
        self.assertEqual(capas_faltantes(doc2, alm), ("r",))

    def test_bomba_de_descompresion(self):
        # PNG chicos que dicen medir muchísimo: no se decodifican (ni se reserva nada) y la capa "falta".
        doc = Documento.nuevo(100, 80).agregar_imagen("grande", "Grande", id_capa="g")
        doc = doc.agregar_imagen("enorme", "Enorme", id_capa="e").agregar_imagen("ok", "Ok", id_capa="o")
        doc = doc.con_capa("o", mascara="mascara_grande")
        archivos = {"documento.json": self._json_valido(documento=doc.como_dict()),
                    "imagenes/grande.png": png_falso(12000, 12000),     # 144 MP > 100 MP
                    "imagenes/enorme.png": png_falso(30000, 30000),
                    "imagenes/ok.png": png_falso(70000, 10),           # más de 65535 por lado
                    "mascaras/mascara_grande.png": png_falso(101, 80, 0)}   # más que el documento
        ruta = self._zip(archivos)
        with mock.patch.object(proyecto_lite.cv2, "imdecode", side_effect=AssertionError("decodificó")) as dec:
            doc2, alm, _ = abrir_proyecto(ruta)
        dec.assert_not_called()
        self.assertEqual(capas_faltantes(doc2, alm), ("g", "e", "o"))
        self.assertEqual(alm.ids(), set())
        self.assertLessEqual(proyecto_lite._MAX_PNG, 512 * 2 ** 20)

    def test_png_que_no_es_de_los_nuestros(self):
        doc = Documento.nuevo(10, 10).agregar_imagen("a", "A", id_capa="a").agregar_imagen("b", "B", id_capa="b")
        ruta = self._zip({"documento.json": self._json_valido(documento=doc.como_dict()),
                          "imagenes/a.png": png_falso(5, 5, tipo_color=3),     # con paleta: no lo escribimos nunca
                          "imagenes/b.png": b"GIF89a" + bytes(40)})
        doc2, alm, _ = abrir_proyecto(ruta)
        self.assertEqual(capas_faltantes(doc2, alm), ("a", "b"))

    def test_error_o_falta_de_memoria_al_decodificar(self):
        guardar_proyecto(self.ruta, self.doc, self.alm, {})
        import cv2
        for error in (cv2.error("roto"), MemoryError()):
            with self.subTest(type(error).__name__):
                with mock.patch.object(proyecto_lite.cv2, "imdecode", side_effect=error):
                    doc, alm, _ = abrir_proyecto(self.ruta)
                self.assertEqual(doc, self.doc)
                self.assertEqual(set(capas_faltantes(doc, alm)), {"a", "b", doc.capas[-1].id})

    def test_no_existe(self):
        with self.assertRaises(FileNotFoundError):
            abrir_proyecto(self.dir / "no_existe.nslite")

    def test_zip_roto(self):
        basura = self.dir / "basura.nslite"
        basura.write_bytes(b"PK\x03\x04 esto no es un zip de verdad" * 10)
        with self.assertRaises(ValueError) as cm:
            abrir_proyecto(basura)
        self.assertIn("basura.nslite", str(cm.exception))
        guardar_proyecto(self.ruta, self.doc, self.alm, self.extra)
        cortado = self.dir / "cortado.nslite"
        cortado.write_bytes(self.ruta.read_bytes()[: len(self.ruta.read_bytes()) // 2])
        with self.assertRaises(ValueError):
            abrir_proyecto(cortado)
        vacio = self.dir / "vacio.nslite"
        vacio.write_bytes(b"")
        with self.assertRaises(ValueError):
            abrir_proyecto(vacio)

    def test_contenido_roto(self):
        casos = {
            "sin documento.json": {"otro.txt": b"hola"},
            "json roto": {"documento.json": b"{no es json"},
            "no utf-8": {"documento.json": b"\xff\xfe\x00"},
            "no es un objeto": {"documento.json": b"[1, 2]"},
            "sin formato": {"documento.json": json.dumps({"documento": {}}).encode()},
            "formato raro": {"documento.json": self._json_valido(formato="uno")},
            "formato cero": {"documento.json": self._json_valido(formato=0)},
            "documento roto": {"documento.json": self._json_valido(documento={"ancho": 3})},
            "capas inválidas": {"documento.json": self._json_valido(documento={
                "ancho": 3, "alto": 3, "capas": [{"id": "x", "tipo": "imagen", "nombre": "x"}]})},
            "extra no es objeto": {"documento.json": self._json_valido(extra=[1])},
        }
        for caso, archivos in casos.items():
            with self.subTest(caso):
                with self.assertRaises(ValueError):
                    abrir_proyecto(self._zip(archivos))

    def test_formato_futuro(self):
        ruta = self._zip({"documento.json": self._json_valido(formato=FORMATO + 1)})
        with self.assertRaises(ValueError) as cm:
            abrir_proyecto(ruta)
        self.assertIn("más nueva", str(cm.exception))

    def test_formato_2_ida_y_vuelta(self):
        try:
            from celular_natural.motor import formas
        except ImportError:
            self.skipTest("todavía no está motor/formas.py (M2)")
        from celular_natural.motor.documento import Capa
        from celular_natural.motor.estilos import EstilosCapa, Sombra, SuperposicionDegradado, Trazo
        rel = formas.Relleno("lineal", ((10, 20, 30, 255), (200, 100, 0, 255)), (0.0, 1.0), 45.0)
        doc = Documento.nuevo_lienzo(64, 48, rel)
        pix = self.alm.guardar(imagen_rgba(30, 20, semilla=4))
        doc = doc.agregar(Capa("p", "pixeles", "Píxeles", imagen=pix,
                               transform=Transformacion(30, 20, 1.5, 10, True, 0.5, True),
                               estilos=EstilosCapa(sombra=Sombra(angulo=45), trazo=Trazo(posicion="centro"),
                                                   degradado=SuperposicionDegradado(rel, 0.4))))
        doc = doc.agregar(Capa("f", "forma", "Estrella", params=formas.ParamsForma("estrella", 30, 30, puntas=7),
                               transform=Transformacion(40, 30)))
        doc = doc.agregar(Capa("r", "relleno", "Relleno", params=formas.Relleno("color", ((0, 0, 255, 128),)),
                               mascara=self.doc.capa("a").mascara))
        doc = doc.agrupar(["p", "f"], nombre="Grupo «uno»", id_grupo="g").con_capa("g", opacidad=0.5)
        guardar_proyecto(self.ruta, doc, self.alm, {"modo": "photoshop"})
        with zipfile.ZipFile(self.ruta) as z:
            datos = json.loads(z.read("documento.json"))
            self.assertIn(f"imagenes/{pix}.png", z.namelist())
        self.assertEqual(datos["formato"], 2)
        doc2, alm2, extra = abrir_proyecto(self.ruta)
        self.assertEqual(doc2, doc)
        self.assertEqual(extra, {"modo": "photoshop"})
        self.assertEqual(capas_faltantes(doc2, alm2), ())
        np.testing.assert_array_equal(componer(doc2, alm2, None), componer(doc, self.alm, None))
        # Lo nuevo que no vale da un proyecto roto (ValueError), no otra cosa.
        dd = doc.como_dict()
        malos = {
            "estilos": lambda d: d["capas"][1].__setitem__("estilos", {"sombra": {"distancia": "lejos"}}),
            "padre": lambda d: d["capas"][1].__setitem__("padre", "no-existe"),
            "params": lambda d: d["capas"][0].__setitem__("params", {"tipo": "raro"}),
            "sin params": lambda d: d["capas"][0].pop("params"),
            "escala_y": lambda d: d["capas"][1]["transform"].__setitem__("escala_y", -1),
        }
        for caso, romper in malos.items():
            with self.subTest(caso):
                d = json.loads(json.dumps(dd))
                romper(d)
                ruta = self._zip({"documento.json": self._json_valido(formato=2, documento=d)})
                with self.assertRaises(ValueError):
                    abrir_proyecto(ruta)

    def test_etapa_1_sigue_en_formato_1(self):
        guardar_proyecto(self.ruta, self.doc, self.alm, {})
        with zipfile.ZipFile(self.ruta) as z:
            datos = json.loads(z.read("documento.json"))
        self.assertEqual(datos["formato"], 1)   # lo abre también una versión anterior
        self.assertTrue(all(set(c) == {"id", "tipo", "nombre", "visible", "bloqueada", "opacidad", "fusion",
                                       "imagen", "mascara", "transform"} for c in datos["documento"]["capas"]))
        self.assertEqual(FORMATO, 2)

    def test_no_usa_pickle(self):
        marca = self.dir / "se_ejecuto.txt"
        trampa = pickle.dumps(_Trampa(str(marca)))
        # Un proyecto válido con un .pkl adentro: se abre y el .pkl se ignora.
        ruta = self._zip({"documento.json": self._json_valido(), "documento.pkl": trampa,
                          "imagenes/x.pkl": trampa})
        with mock.patch("pickle.loads", side_effect=AssertionError("pickle.loads")), \
                mock.patch("pickle.load", side_effect=AssertionError("pickle.load")), \
                mock.patch("pickle.Unpickler", side_effect=AssertionError("pickle.Unpickler")):
            doc, _alm, _extra = abrir_proyecto(ruta)
        self.assertEqual(doc, Documento.nuevo(10, 10))
        self.assertFalse(marca.exists())
        # Solo un .pkl: es un proyecto roto, no se ejecuta nada.
        ruta = self._zip({"documento.pkl": trampa})
        with self.assertRaises(ValueError):
            abrir_proyecto(ruta)
        self.assertFalse(marca.exists())
        # Y el módulo ni siquiera importa pickle.
        import celular_natural.motor.proyecto_lite as m
        self.assertNotIn("pickle", m.__dict__)
        self.assertNotIn("import pickle", Path(m.__file__).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
