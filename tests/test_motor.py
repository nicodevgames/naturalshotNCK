"""Pruebas del motor. Ejecutar con:  python -m unittest discover -s tests -v"""

from __future__ import annotations

import hashlib
import io
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from celular_natural.motor import (  # noqa: E402
    NEUTRO, PRESET_ANTI_IA, PRESET_PRINCIPAL, PRESETS, cargar_imagen, exportar_imagen, procesar, procesar_pila,
    reducir_para_vista, ruta_salida_sugerida,
)
from celular_natural.motor.imagen_io import bytes_perfil_srgb  # noqa: E402

PRESET = PRESETS[PRESET_PRINCIPAL]


def imagen_render(w: int = 1201, h: int = 857, semilla: int = 0) -> np.ndarray:
    """Imagen sintética "demasiado perfecta": degradados limpios, bordes duros y textura nítida."""
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.empty((h, w, 3), np.float32)
    img[..., 0] = 0.2 + 0.6 * xx / w
    img[..., 1] = 0.3 + 0.5 * yy / h
    img[..., 2] = 0.8 - 0.4 * xx / w
    textura = rng.random((h, w)).astype(np.float32)
    zona = (yy > h * 0.55)
    img[zona] = img[zona] * 0.7 + 0.25 * textura[zona][:, None]
    img[int(h * .2):int(h * .45), int(w * .55):int(w * .8)] = 0.06  # sombra profunda
    img[int(h * .1):int(h * .15), int(w * .1):int(w * .5)] = 0.98  # luz alta
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def mad(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())


class PruebasProcesado(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rgb = imagen_render()

    def test_conserva_dimensiones_y_tipo(self):
        for forma in ((857, 1201), (1, 1), (3, 7), (640, 480), (31, 2000)):
            rgb = imagen_render(forma[1], forma[0])
            salida = procesar(rgb, PRESET)
            self.assertEqual(salida.shape, rgb.shape)
            self.assertEqual(salida.dtype, np.uint8)

    def test_intensidad_cero_es_identidad(self):
        salida = procesar(self.rgb, replace(PRESET, intensidad=0))
        self.assertTrue(np.array_equal(salida, self.rgb))
        self.assertTrue(np.array_equal(procesar(self.rgb, NEUTRO), self.rgb))

    def test_no_modifica_el_arreglo_de_entrada(self):
        copia = self.rgb.copy()
        procesar(self.rgb, PRESET)
        self.assertTrue(np.array_equal(copia, self.rgb))

    def test_preset_es_moderado(self):
        salida = procesar(self.rgb, PRESET)
        diferencia = mad(salida, self.rgb)
        self.assertGreater(diferencia, 1.0, "el preset debe producir un cambio visible")
        self.assertLess(diferencia, 12.0, "el preset no debe destruir la imagen")
        # El brillo medio casi no cambia y la imagen no se vuelve gris.
        self.assertLess(abs(salida.mean() - self.rgb.mean()), 8.0)
        self.assertGreater(salida.std(), self.rgb.std() * 0.8)

    def test_todos_los_presets_son_moderados_y_distintos(self):
        resultados = {}
        for nombre, ajustes in PRESETS.items():
            with self.subTest(preset=nombre):
                salida = procesar(self.rgb, ajustes)
                self.assertEqual(salida.shape, self.rgb.shape)
                d = mad(salida, self.rgb)
                self.assertGreater(d, 0.5, f"{nombre} casi no cambia la imagen")
                self.assertLess(d, 15.0, f"{nombre} es excesivo")
                self.assertLess(abs(salida.mean() - self.rgb.mean()), 12.0)
                resultados[nombre] = salida
        self.assertEqual(len(set(PRESETS.values())), len(PRESETS), "hay presets duplicados")

    def test_capas_apiladas(self):
        base = PRESET
        capa = replace(PRESETS["Noche urbana"], intensidad=50)
        una = procesar_pila(self.rgb, [base])
        self.assertTrue(np.array_equal(una, procesar(self.rgb, base)))
        dos = procesar_pila(self.rgb, [base, capa])
        self.assertEqual(dos.shape, self.rgb.shape)
        self.assertGreater(mad(dos, una), 0.3, "la capa extra debe sumar un cambio visible")
        self.assertLess(mad(dos, self.rgb), 20.0, "dos capas siguen siendo moderadas")
        # Capas en cero no cambian nada.
        nula = procesar_pila(self.rgb, [replace(base, intensidad=0), replace(capa, intensidad=0)])
        self.assertTrue(np.array_equal(nula, self.rgb))
        self.assertIsNot(nula, self.rgb)

    def test_determinista(self):
        self.assertTrue(np.array_equal(procesar(self.rgb, PRESET), procesar(self.rgb, PRESET)))

    def test_cada_control_cambia_la_imagen_de_forma_moderada(self):
        controles = {
            "nitidez": 100, "microcontraste": 100, "suavizado": 100, "piel": 100, "ruido": 100, "tono": 100,
            "exposicion": 100, "contraste": 100, "temperatura": 100, "tinte": 100,
            "saturacion": -100, "aberracion": 100, "bordes": 100, "vineteo": 100,
            # Módulos nuevos
            "desenfoque": 100, "distorsion": 100, "claridad": -100, "nitidez_variable": 100,
            "luces": 100, "sombras": 100, "zona_sombras": 100, "zona_medios": -100, "zona_luces": -100,
            "variacion_balance": 100, "desat_luces": 100, "respuesta_camara": 100,
            "grano": 100, "reescalado": 100, "jpeg": 100,
        }
        for campo, valor in controles.items():
            with self.subTest(control=campo):
                salida = procesar(self.rgb, replace(NEUTRO, **{campo: valor}))
                d = mad(salida, self.rgb)
                self.assertGreater(d, 0.15, f"{campo} al máximo no produce cambios visibles")
                self.assertLess(d, 25.0, f"{campo} al máximo es excesivo")

    def test_intensidad_escala_el_efecto(self):
        d50 = mad(procesar(self.rgb, replace(PRESET, intensidad=50)), self.rgb)
        d100 = mad(procesar(self.rgb, PRESET), self.rgb)
        self.assertLess(d50, d100)

    def test_ruido_mayor_en_sombras(self):
        plano = np.zeros((400, 800, 3), np.uint8)
        plano[:, :400] = 40   # sombra
        plano[:, 400:] = 215  # luz
        salida = procesar(plano, replace(NEUTRO, ruido=100)).astype(np.float32)
        ruido_sombra = salida[:, 20:380].std()
        ruido_luz = salida[:, 420:780].std()
        self.assertGreater(ruido_sombra, ruido_luz * 1.5)
        self.assertLess(ruido_sombra, 10.0, "el ruido debe ser fino, no un grano exagerado")

    def test_reduce_microdetalle_sin_aplanar_bordes(self):
        salida = procesar(self.rgb, replace(NEUTRO, nitidez=100, microcontraste=100, suavizado=100))
        lap = lambda x: np.abs(np.diff(x.astype(np.float32).mean(2), axis=1))
        zona_textura = (slice(600, 850), slice(0, 600))
        self.assertLess(lap(salida)[zona_textura].mean(), lap(self.rgb)[zona_textura].mean())
        # El borde fuerte de la sombra se mantiene.
        fila = 250
        x = int(1201 * .55)
        salto_antes = abs(int(self.rgb[fila, x - 3].mean()) - int(self.rgb[fila, x + 3].mean()))
        salto_despues = abs(int(salida[fila, x - 3].mean()) - int(salida[fila, x + 3].mean()))
        self.assertGreater(salto_despues, salto_antes * 0.8)

    def test_piel_real_texturiza_lo_liso_y_no_lo_que_ya_tiene_textura(self):
        # Mitad izquierda: "piel de IA", un tono medio perfectamente liso.
        # Mitad derecha: misma luz pero con textura propia.
        rng = np.random.default_rng(3)
        img = np.full((400, 800, 3), (190, 140, 120), np.uint8)
        textura = rng.normal(0, 12, (400, 400, 1))
        img[:, 400:] = np.clip(img[:, 400:] + textura, 0, 255).astype(np.uint8)
        salida = procesar(img, replace(NEUTRO, piel=100))
        variacion = lambda x: float(x.astype(np.float32).std(axis=(0, 1)).mean())  # por canal
        lisa_antes, lisa_despues = variacion(img[:, 20:380]), variacion(salida[:, 20:380])
        self.assertGreater(lisa_despues, lisa_antes + 1.5, "la piel lisa debe ganar textura")
        self.assertLess(lisa_despues, 10.0, "la textura debe ser fina, no un grano exagerado")
        cambio_texturada = mad(salida[:, 420:780], img[:, 420:780])
        cambio_lisa = mad(salida[:, 20:380], img[:, 20:380])
        self.assertLess(cambio_texturada, cambio_lisa * 0.5, "lo que ya tiene textura casi no se toca")

    def test_anti_ia_vista_previa_equivalente(self):
        ajustes = PRESETS[PRESET_ANTI_IA]
        self.assertEqual(ajustes.suavizado, 0, "anti IA no debe alisar más la piel")
        grande = imagen_render(2400, 1600)
        chica, escala = reducir_para_vista(grande, 800)
        completa_reducida, _ = reducir_para_vista(procesar(grande, ajustes), 800)
        self.assertLess(mad(procesar(chica, ajustes, escala_vista=escala), completa_reducida), 2.5)

    def test_vista_previa_equivalente_a_completa(self):
        grande = imagen_render(2400, 1600)
        chica, escala = reducir_para_vista(grande, 800)
        self.assertLess(escala, 1.0)
        completa = procesar(grande, PRESET)
        previa = procesar(chica, PRESET, escala_vista=escala)
        completa_reducida, _ = reducir_para_vista(completa, 800)
        self.assertLess(mad(previa, completa_reducida), 2.5)


class PruebasArchivos(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.dir = Path(self._dir.name)

    def tearDown(self):
        self._dir.cleanup()

    def _flujo_completo(self, original: Path, formato: str, **kw) -> tuple[Path, ImagenCargada]:  # noqa: F821
        img = cargar_imagen(original)
        salida = procesar(img.rgb, PRESET)
        ext = ".png" if formato == "PNG" else ".jpg"
        destino = ruta_salida_sugerida(original, ext)
        exportar_imagen(destino, salida, original=original, alpha=img.alpha, icc=img.icc,
                        exif=img.exif, formato=formato, **kw)
        return destino, img

    def test_exportacion_conserva_dimensiones_y_original_intacto(self):
        for formato_original in ("PNG", "JPEG"):
            for formato in ("PNG", "JPEG"):
                with self.subTest(original=formato_original, exportado=formato):
                    original = self.dir / f"foto_{formato_original}_{formato}.{'png' if formato_original == 'PNG' else 'jpg'}"
                    Image.fromarray(imagen_render(1203, 803)).save(original, formato_original)
                    huella, mtime = sha256(original), original.stat().st_mtime_ns
                    destino, _ = self._flujo_completo(original, formato, calidad_jpeg=90)
                    self.assertNotEqual(destino.resolve(), original.resolve())
                    self.assertTrue(destino.exists())
                    with Image.open(destino) as resultado:
                        self.assertEqual(resultado.size, (1203, 803))
                        self.assertEqual(resultado.format, formato)
                    self.assertEqual(sha256(original), huella)
                    self.assertEqual(original.stat().st_mtime_ns, mtime)

    def test_no_permite_sobrescribir_el_original(self):
        original = self.dir / "foto.png"
        Image.fromarray(imagen_render(100, 80)).save(original)
        huella = sha256(original)
        img = cargar_imagen(original)
        with self.assertRaises(ValueError):
            exportar_imagen(original, img.rgb, original=original, formato="PNG")
        with self.assertRaises(ValueError):  # misma ruta escrita de otra forma
            exportar_imagen(self.dir / "." / "FOTO.png", img.rgb, original=original, formato="PNG")
        self.assertEqual(sha256(original), huella)

    def test_ruta_sugerida_no_pisa_archivos(self):
        original = self.dir / "foto.jpg"
        original.write_bytes(b"x")
        primera = ruta_salida_sugerida(original, ".png")
        self.assertEqual(primera.name, "foto_celular.png")
        primera.write_bytes(b"x")
        self.assertEqual(ruta_salida_sugerida(original, ".png").name, "foto_celular_2.png")

    def test_lote_procesa_todo_y_sigue_ante_errores(self):
        from celular_natural.motor import procesar_lote
        from PIL import Image
        rutas = []
        for i in range(3):
            r = self.dir / f"foto{i}.png"
            Image.fromarray(imagen_render(300, 200, semilla=i)).save(r)
            rutas.append(r)
        roto = self.dir / "rota.jpg"
        roto.write_bytes(b"no es una imagen")
        antes = [sha256(r) for r in rutas]
        salida = self.dir / "salida"
        avances = []
        res = procesar_lote(rutas + [roto], [PRESET], carpeta=salida, formato="PNG",
                            progreso=lambda i, n, _nombre: avances.append((i, n)))
        self.assertEqual([r.error is None for r in res], [True, True, True, False])
        for r in res[:3]:
            self.assertTrue(r.destino.exists())
            self.assertEqual(Image.open(r.destino).size, (300, 200))
        self.assertEqual([sha256(r) for r in rutas], antes, "los originales no se tocan")
        self.assertEqual(avances[-1], (4, 4))

    def test_orientacion_exif(self):
        # Foto guardada "acostada" (800x600) con orientación 6: debe verse 600x800.
        rgb = imagen_render(800, 600)
        rgb[:50, :50] = (255, 0, 0)  # marca en la esquina superior izquierda del sensor
        exif = Image.Exif()
        exif[0x0112] = 6
        exif[0x010F] = "Prueba"
        original = self.dir / "girada.jpg"
        Image.fromarray(rgb).save(original, "JPEG", exif=exif.tobytes(), quality=95)
        img = cargar_imagen(original)
        self.assertEqual((img.ancho, img.alto), (600, 800))
        # Rotación 90° horaria: la marca pasa a la esquina superior derecha.
        self.assertGreater(img.rgb[:40, -40:, 0].mean(), 200)
        self.assertLess(img.rgb[:40, -40:, 1].mean(), 60)
        destino, _ = self._flujo_completo(original, "JPEG")
        with Image.open(destino) as resultado:
            self.assertEqual(resultado.size, (600, 800))
            orient = resultado.getexif().get(0x0112, 1)
            self.assertEqual(orient, 1, "la exportación no debe volver a rotarse")
            self.assertEqual(resultado.getexif().get(0x010F), "Prueba")

    def test_perfil_icc_se_conserva(self):
        # Se usa un perfil distinto de sRGB generado por LittleCMS para comprobar que se
        # procesa en el espacio original y se reincrusta igual (sin convertir colores).
        perfil = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
        icc = perfil.tobytes()
        original = self.dir / "con_perfil.png"
        Image.fromarray(imagen_render(300, 200)).save(original, icc_profile=icc)
        destino, img = self._flujo_completo(original, "PNG")
        self.assertEqual(img.icc, icc)
        with Image.open(destino) as resultado:
            self.assertEqual(resultado.info.get("icc_profile"), icc)

    def test_sin_perfil_se_incrusta_srgb(self):
        original = self.dir / "sin_perfil.png"
        Image.fromarray(imagen_render(300, 200)).save(original)
        destino, img = self._flujo_completo(original, "JPEG")
        self.assertIsNone(img.icc)
        with Image.open(destino) as resultado:
            self.assertEqual(resultado.info.get("icc_profile"), bytes_perfil_srgb())

    def test_cmyk_se_convierte(self):
        original = self.dir / "cmyk.jpg"
        Image.fromarray(imagen_render(200, 100)).convert("CMYK").save(original, "JPEG")
        img = cargar_imagen(original)
        self.assertEqual(img.rgb.shape, (100, 200, 3))
        self.assertIsNone(img.icc)

    def test_transparencia(self):
        rgba = np.dstack([imagen_render(320, 240), np.full((240, 320), 255, np.uint8)])
        rgba[:120, :, 3] = 0
        original = self.dir / "alpha.png"
        Image.fromarray(rgba, "RGBA").save(original)
        destino, img = self._flujo_completo(original, "PNG")
        self.assertIsNotNone(img.alpha)
        with Image.open(destino) as resultado:
            self.assertEqual(resultado.mode, "RGBA")
            self.assertEqual(resultado.size, (320, 240))
            self.assertTrue(np.array_equal(np.asarray(resultado)[..., 3], rgba[..., 3]))
        destino_jpg, _ = self._flujo_completo(original, "JPEG")
        with Image.open(destino_jpg) as resultado:
            self.assertEqual(resultado.mode, "RGB")

    def test_calidad_jpeg_configurable(self):
        original = self.dir / "q.png"
        Image.fromarray(imagen_render(600, 400)).save(original)
        img = cargar_imagen(original)
        a = exportar_imagen(self.dir / "q60.jpg", img.rgb, original=original, formato="JPEG", calidad_jpeg=60)
        b = exportar_imagen(self.dir / "q98.jpg", img.rgb, original=original, formato="JPEG", calidad_jpeg=98)
        self.assertLess(a.stat().st_size, b.stat().st_size)

    def test_escala_de_grises_16_bits(self):
        gris = (np.linspace(0, 65535, 200 * 100).reshape(100, 200)).astype(np.uint16)
        original = self.dir / "g16.png"
        Image.fromarray(gris).save(original)
        img = cargar_imagen(original)
        self.assertEqual(img.rgb.shape, (100, 200, 3))
        self.assertGreater(int(img.rgb.max()), 250)


if __name__ == "__main__":
    unittest.main()
