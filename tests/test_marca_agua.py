"""Pruebas de quitar marcas de agua visibles y de la perturbación de firmas."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image, ImageDraw

from celular_natural.motor.edicion import aplicar_borrados
from celular_natural.motor.imagen_io import _desmarcar_pixeles, exportar_imagen
from celular_natural.motor.marca_agua import (POSICIONES, borrado_de_marca, caja_de_preset,
                                              detectar_marca)
from celular_natural.motor.metadatos import auditar_imagen, tiene_c2pa


def _foto(h=600, w=800):
    """Degradé vertical con algo de textura, como un fondo real."""
    y = np.linspace(40, 200, h, dtype=np.float32)[:, None]
    x = np.linspace(0, 15, w, dtype=np.float32)[None, :]
    base = np.clip(y + x, 0, 255)
    rgb = np.repeat(base[..., None], 3, axis=2)
    rgb += np.random.default_rng(1).normal(0, 3, rgb.shape)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def _liso(h=600, w=800):
    y = np.linspace(40, 200, h, dtype=np.float32)[:, None]
    return np.repeat(np.repeat(y, w, axis=1)[..., None], 3, axis=2).astype(np.uint8)


def _con_marca(rgb):
    """Tres barras blancas abajo a la derecha, como un logo."""
    im = Image.fromarray(rgb, "RGB")
    d = ImageDraw.Draw(im)
    h, w = rgb.shape[:2]
    x0, y0 = w - 90, h - 45
    for i in range(3):
        d.rectangle([x0 + i * 26, y0, x0 + i * 26 + 9, y0 + 29], fill=(255, 255, 255))
    return np.asarray(im).copy(), (x0, y0, x0 + 62, y0 + 30)


def _con_chunk_c2pa(entrada: Path, salida: Path) -> None:
    datos = entrada.read_bytes()
    carga = b"\x00\x00\x00\x00"
    trozo = len(carga).to_bytes(4, "big") + b"caBX" + carga + b"\x00\x00\x00\x00"
    pos = datos.index(b"IDAT") - 4
    salida.write_bytes(datos[:pos] + trozo + datos[pos:])


class CajaDePreset(unittest.TestCase):
    def test_queda_dentro_en_vertical_y_horizontal(self):
        for aspecto in (4 / 3, 3 / 4, 1.0, 16 / 9):
            for posicion in POSICIONES:
                x0, y0, x1, y1 = caja_de_preset(posicion, aspecto)
                self.assertGreater(x1, x0)
                self.assertGreater(y1, y0)
                self.assertGreaterEqual(x0, 0.0)
                self.assertGreaterEqual(y0, 0.0)
                self.assertLessEqual(x1, 1.0)
                self.assertLessEqual(y1, 1.0)

    def test_proporcional_al_lado_corto(self):
        # Con el mismo lado corto (300 px), la caja mide lo mismo en píxeles.
        _, y0_v, _, y1_v = caja_de_preset("abajo-derecha", 3 / 4)
        _, y0_h, _, y1_h = caja_de_preset("abajo-derecha", 4 / 3)
        self.assertAlmostEqual((y1_v - y0_v) * 400, (y1_h - y0_h) * 300, places=6)

    def test_escala_agranda(self):
        _, y0, _, y1 = caja_de_preset("abajo-derecha", 4 / 3, 1.0)
        _, y0_doble, _, y1_doble = caja_de_preset("abajo-derecha", 4 / 3, 2.0)
        self.assertGreater(y1_doble - y0_doble, y1 - y0)

    def test_posicion_desconocida(self):
        with self.assertRaises(ValueError):
            caja_de_preset("al-medio", 1.0)


class BorradoDeMarca(unittest.TestCase):
    def test_rellena_por_defecto_y_agranda(self):
        b = borrado_de_marca((0.5, 0.5, 0.7, 0.6))
        self.assertEqual(b.modo, "rellenar")
        z = b.zona
        self.assertLess(z.x0, 0.5)
        self.assertGreater(z.x1, 0.7)
        self.assertLessEqual(z.pluma, 20)

    def test_acepta_clonar(self):
        self.assertEqual(borrado_de_marca((0.1, 0.1, 0.2, 0.2), modo="clonar").modo, "clonar")

    def test_modo_desconocido(self):
        with self.assertRaises(ValueError):
            borrado_de_marca((0.1, 0.1, 0.2, 0.2), modo="difuminar")


class QuitarLaMarca(unittest.TestCase):
    def test_borra_los_glifos_y_no_toca_el_resto(self):
        rgb, (x0, y0, x1, y1) = _con_marca(_foto())
        caja = (x0 / rgb.shape[1], y0 / rgb.shape[0], x1 / rgb.shape[1], y1 / rgb.shape[0])
        salida = aplicar_borrados(rgb, (borrado_de_marca(caja),))
        dentro = salida[y0:y1, x0:x1]
        self.assertFalse((dentro.min(axis=2) > 235).any(), "quedaron glifos blancos")
        self.assertTrue(np.array_equal(salida[:300], rgb[:300]), "se tocó fuera de la zona")

    def test_detecta_la_marca(self):
        rgb, (x0, y0, x1, y1) = _con_marca(_foto())
        caja = detectar_marca(rgb)
        self.assertIsNotNone(caja)
        cx0, cy0, cx1, cy1 = caja[0] * 800, caja[1] * 600, caja[2] * 800, caja[3] * 600
        self.assertLess(cx0, x1)
        self.assertGreater(cx1, x0)
        self.assertLess(cy0, y1)
        self.assertGreater(cy1, y0)

    def test_sin_marca_no_detecta(self):
        self.assertIsNone(detectar_marca(_liso()))


class PerturbarFirma(unittest.TestCase):
    def test_conserva_tamano_y_brillo(self):
        rgb = _foto()
        salida = _desmarcar_pixeles(rgb, 0)
        self.assertEqual(salida.shape, rgb.shape)
        self.assertLess(abs(float(salida.mean()) - float(rgb.mean())), 1.0)
        rms = float(np.sqrt(((salida.astype(np.float32) - rgb.astype(np.float32)) ** 2).mean()))
        self.assertGreater(rms, 1.0)


class Exportar(unittest.TestCase):
    def test_desmarcar_conserva_dimensiones_y_politica(self):
        with TemporaryDirectory() as carpeta:
            origen = Path(carpeta) / "origen.jpg"
            destino = Path(carpeta) / "salida.jpg"
            rgb = _foto()
            exif = Image.Exif()
            gps = exif.get_ifd(0x8825)
            gps[1] = "S"
            gps[2] = (34.0, 36.0, 0.0)
            Image.fromarray(rgb, "RGB").save(origen, quality=95, exif=exif.tobytes())
            with Image.open(origen) as im:
                crudo = im.info.get("exif")
            exportar_imagen(destino, rgb, original=origen, exif=crudo, desmarcar=True)
            with Image.open(destino) as im:
                self.assertEqual(im.size, (800, 600))
            self.assertEqual(auditar_imagen(destino), [])

    def test_tiene_c2pa(self):
        with TemporaryDirectory() as carpeta:
            limpio = Path(carpeta) / "limpio.png"
            sucio = Path(carpeta) / "sucio.png"
            Image.fromarray(_foto(), "RGB").save(limpio)
            self.assertFalse(tiene_c2pa(limpio))
            _con_chunk_c2pa(limpio, sucio)
            self.assertTrue(tiene_c2pa(sucio))


if __name__ == "__main__":
    unittest.main()
