"""NS-104: política de metadatos de salida (motor/metadatos.py) en todo lo que exporta la app.

Fotos (foto única y lote, JPEG y PNG), video (MP4) y audio (M4A y WAV), con originales que
traen GPS, seriales, rutas, orientación girada y miniatura. Ningún archivo exportado puede
violar la política (``metadatos.auditar_imagen`` y las reglas de video/audio de acá).
"""

from __future__ import annotations

import io
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from celular_natural.motor import PRESET_PRINCIPAL, PRESETS, metadatos as M  # noqa: E402
from celular_natural.motor.imagen_io import cargar_imagen, exportar_imagen  # noqa: E402
from celular_natural.motor.lote import procesar_lote  # noqa: E402

try:
    import av
except ImportError:  # pragma: no cover
    av = None

UBICACION_MP4 = "+34.0522-118.2437/"


def exif_completo(orientacion: int = 6, con_miniatura: bool = True) -> bytes:
    """EXIF de una cámara con todo lo que no tiene que salir."""
    e = Image.Exif()
    e[0x010F] = "Canon"
    e[0x0110] = "EOS R6"
    e[0x0131] = "Firmware 1.2"
    e[M.TAG_ORIENTACION] = orientacion
    e[M.TAG_PC] = "PC-DE-JUAN"
    e[M.TAG_DOCUMENTO] = "IMG_0001.CR3"
    e[M.TAG_DESCRIPCION] = "C:\\Users\\juan\\Fotos\\IMG_0001.jpg"
    gps = e.get_ifd(M.IFD_GPS)
    gps[1], gps[2], gps[3], gps[4] = "S", (34.0, 36.0, 0.0), "W", (58.0, 22.0, 0.0)
    sub = e.get_ifd(M.IFD_EXIF)
    sub[0x9003] = "2026:01:02 10:00:00"
    sub[0x829A] = 0.01  # tiempo de exposición
    sub[M.TAG_SERIE_CUERPO] = "032024001234"
    sub[M.TAG_SERIE_LENTE] = "0000c1a2b3"
    sub[M.TAG_DUENO] = "Juan Pérez"
    sub[M.TAG_ID_UNICO] = "A1B2C3D4E5F6"
    sub[M.TAG_ANCHO], sub[M.TAG_ALTO] = 6000, 4000
    datos = e.tobytes()
    if con_miniatura:
        datos = _con_ifd1(datos)
    return datos


def _con_ifd1(exif: bytes) -> bytes:
    """Agrega un IFD1 mínimo (una miniatura) al final del EXIF, como hacen las cámaras."""
    cab = exif[:6] if exif[:6] == b"Exif\x00\x00" else b""
    t = bytearray(exif[len(cab):])
    orden = "little" if t[:2] == b"II" else "big"
    ifd0 = int.from_bytes(t[4:8], orden)
    n = int.from_bytes(t[ifd0:ifd0 + 2], orden)
    puntero = ifd0 + 2 + 12 * n
    ifd1 = len(t)
    t[puntero:puntero + 4] = ifd1.to_bytes(4, orden)
    # IFD1 con una entrada (Compression = 6, JPEG) y sin siguiente IFD.
    t += (1).to_bytes(2, orden) + (0x0103).to_bytes(2, orden) + (3).to_bytes(2, orden) \
        + (1).to_bytes(4, orden) + (6).to_bytes(2, orden) + b"\x00\x00" + (0).to_bytes(4, orden)
    return cab + bytes(t)


class FotosTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="ns_meta_"))
        rng = np.random.default_rng(3)
        self.rgb = rng.integers(0, 255, (300, 400, 3), dtype=np.uint8)
        self.original = self.dir / "original.jpg"
        icc = Image.new("RGB", (1, 1)).info.get("icc_profile")  # noqa: F841 (sin perfil propio)
        Image.fromarray(self.rgb).save(self.original, "JPEG", exif=exif_completo())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_el_original_de_prueba_tiene_todo_lo_que_no_tiene_que_salir(self):
        problemas = M.auditar_imagen(self.original)
        for esperado in ("Orientation", "GPS", "HostComputer", "BodySerialNumber", "Dimensiones", "miniatura"):
            self.assertTrue(any(esperado in p for p in problemas), (esperado, problemas))

    def test_foto_unica_jpeg_y_png_cumplen_la_politica(self):
        img = cargar_imagen(self.original)
        self.assertEqual(img.rgb.shape[:2], (400, 300))  # orientación 6: los píxeles se giraron
        for formato, ext in (("JPEG", ".jpg"), ("PNG", ".png")):
            destino = exportar_imagen(self.dir / f"salida{ext}", img.rgb, original=self.original, icc=img.icc,
                                      exif=img.exif, formato=formato)
            self.assertEqual(M.auditar_imagen(destino), [], formato)
            with Image.open(destino) as out:
                e = out.getexif()
                self.assertEqual(out.size, (300, 400))
                # Lo que no es privado se conserva: cámara, fecha y exposición.
                self.assertEqual((e.get(0x010F), e.get(0x0110)), ("Canon", "EOS R6"))
                self.assertEqual(e.get_ifd(M.IFD_EXIF).get(0x9003), "2026:01:02 10:00:00")
                self.assertEqual(e.get_ifd(M.IFD_EXIF).get(M.TAG_ANCHO), 300)
                self.assertFalse(e.get_ifd(M.IFD_GPS))
                self.assertTrue(out.info.get("icc_profile"), "el perfil ICC se conserva")

    def test_sin_conservar_exif_no_sale_nada(self):
        img = cargar_imagen(self.original)
        destino = exportar_imagen(self.dir / "sin.jpg", img.rgb, original=self.original, icc=img.icc, exif=None)
        with Image.open(destino) as out:
            self.assertEqual(len(out.getexif()), 0)

    def test_lote_cumple_la_politica(self):
        resultados = procesar_lote([self.original], (PRESETS[PRESET_PRINCIPAL],), self.dir / "lote", "JPEG", 90, True)
        self.assertEqual(len(resultados), 1)
        salidas = list((self.dir / "lote").glob("*.jpg"))
        self.assertEqual(len(salidas), 1)
        self.assertEqual(M.auditar_imagen(salidas[0]), [])

    def test_exif_sin_nada_que_conservar_no_escribe_exif(self):
        e = Image.Exif()
        e[M.TAG_ORIENTACION] = 1
        e.get_ifd(M.IFD_GPS)[1] = "N"
        self.assertIsNone(M.limpiar_exif(e.tobytes(), 10, 10))
        self.assertIsNone(M.limpiar_exif(None, 10, 10))

    def test_herramienta_de_auditoria(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "herramientas"))
        import auditar_metadatos as H
        img = cargar_imagen(self.original)
        bien = self.dir / "exportadas"
        bien.mkdir()
        exportar_imagen(bien / "ok.jpg", img.rgb, original=self.original, icc=img.icc, exif=img.exif)
        reporte = self.dir / "reporte.csv"
        self.assertEqual(H.main([str(bien), "--reporte", str(reporte)]), 0)
        self.assertIn("OK", reporte.read_text(encoding="utf-8"))
        # El original (con GPS, seriales...) no pasa: código 1 y el motivo en el reporte.
        self.assertEqual(H.main([str(self.original), "--reporte", str(reporte)]), 1)
        self.assertIn("GPS", reporte.read_text(encoding="utf-8"))

    def test_rutas(self):
        for ruta in ("C:\\Users\\a\\b.jpg", "D:/fotos/x.png", "\\\\servidor\\carpeta", "/home/nico/a.jpg"):
            self.assertTrue(M.es_ruta(ruta), ruta)
        for texto in ("Atardecer en la playa", "", None, b"Foto de producto"):
            self.assertFalse(M.es_ruta(texto), texto)


@unittest.skipIf(av is None, "Falta PyAV")
class VideoYAudioTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_video  # noqa: E402 (generador de videos de prueba)
        from celular_natural.motor import video as V
        cls.V = V
        cls.dir = Path(tempfile.mkdtemp(prefix="ns_meta_video_"))
        base = test_video.generar_video(cls.dir / "base.mp4", segundos=1.0)
        cls.con_gps = cls.dir / "con_gps.mp4"
        # El mismo video, remuxado con la ubicación y la fecha que pone un celular.
        with av.open(str(base)) as entrada, av.open(str(cls.con_gps), "w") as salida:
            salida.metadata["location"] = UBICACION_MP4
            salida.metadata["com.apple.quicktime.location.ISO6709"] = UBICACION_MP4
            salida.metadata["creation_time"] = "2026-01-02T10:00:00.000000Z"
            mapa = {s.index: salida.add_stream_from_template(s) for s in entrada.streams}
            for paquete in entrada.demux():
                if paquete.dts is None:
                    continue
                paquete.stream = mapa[paquete.stream.index]
                salida.mux(paquete)
        with av.open(str(cls.con_gps)) as c:
            assert c.metadata.get("location") == UBICACION_MP4, c.metadata

    @classmethod
    def tearDownClass(cls):
        cls.V.cerrar_lectores()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def auditar(self, ruta: Path) -> list[str]:
        problemas = []
        ahora = datetime.now(timezone.utc)
        with av.open(str(ruta)) as c:
            todos = [dict(c.metadata)] + [dict(s.metadata) for s in c.streams]
            for meta in todos:
                for clave, valor in meta.items():
                    if "location" in clave.lower() or "xyz" in clave.lower() or UBICACION_MP4 in str(valor):
                        problemas.append(f"ubicación: {clave}={valor}")
                    if clave == "creation_time":
                        cuando = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
                        if cuando > ahora:
                            problemas.append(f"creation_time en el futuro: {valor}")
        return problemas

    def test_el_original_tiene_ubicacion(self):
        self.assertTrue(self.auditar(self.con_gps))

    def test_video_exportado_sin_ubicacion(self):
        destino = self.dir / "salida.mp4"
        self.V.exportar_video(self.con_gps, destino, (PRESETS[PRESET_PRINCIPAL],))
        self.assertEqual(self.auditar(destino), [])

    def test_audio_exportado_sin_ubicacion(self):
        from celular_natural.motor import audio as A
        for ext in ("m4a", "wav"):
            destino = self.dir / f"salida.{ext}"
            A.exportar_audio(self.con_gps, destino)
            self.assertEqual(self.auditar(destino), [], ext)


if __name__ == "__main__":
    unittest.main()
