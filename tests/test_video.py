"""Pruebas del editor de video: lectura, cortes, filtro por cuadro y exportación.

Los videos de prueba se generan acá mismo con PyAV, en una carpeta temporal:
cada cuadro lleva su número escrito en binario con 8 bloques blancos y negros,
y el audio cambia por segundo (440 Hz, silencio, 880 Hz) para comprobar que los
cortes del audio coinciden con los del video.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import av
except ImportError:  # pragma: no cover
    av = None

from celular_natural.motor import PRESET_PRINCIPAL, PRESETS, Ajustes, Cancelado, procesar_pila  # noqa: E402

if av is not None:
    from celular_natural.motor import video as V  # noqa: E402

FPS = 24
BLOQUES = 8  # bits del número de cuadro
FILA_CODIGO = (40, 80)  # filas de la banda con el código (en la orientación guardada)


def escena(w: int, h: int, semilla: int = 5) -> np.ndarray:
    """Fondo con degradado, formas y textura fina (para que el filtro tenga qué cambiar)."""
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.stack([60 + 120 * xx / w, 80 + 100 * yy / h, 150 - 60 * xx / w], -1)
    img += cv2.GaussianBlur(rng.normal(0, 12, (h, w, 3)).astype(np.float32), (0, 0), 1.2)
    img = np.clip(img, 0, 255).astype(np.uint8)
    for _ in range(12):
        c = tuple(int(v) for v in rng.integers(30, 230, 3))
        cv2.circle(img, (int(rng.integers(0, w)), int(rng.integers(0, h))), int(rng.integers(8, max(9, h // 5))), c, -1)
    return img


def con_codigo(img: np.ndarray, numero: int) -> np.ndarray:
    out = img.copy()
    w = out.shape[1]
    ancho = w // BLOQUES
    y0, y1 = FILA_CODIGO
    for b in range(BLOQUES):
        out[y0:y1, b * ancho:(b + 1) * ancho] = 255 if (numero >> b) & 1 else 0
    return out


def leer_codigo(rgb: np.ndarray, rotacion: int = 0) -> int:
    """Número de cuadro de un cuadro mostrado (``rotacion``: la del video de origen, para desrotarlo)."""
    if rotacion:
        rgb = np.rot90(rgb, k=-(rotacion // 90))
    w = rgb.shape[1]
    ancho = w // BLOQUES
    y0, y1 = FILA_CODIGO
    m = (y1 - y0) // 4
    numero = 0
    for b in range(BLOQUES):
        bloque = rgb[y0 + m:y1 - m, b * ancho + ancho // 4:(b + 1) * ancho - ancho // 4]
        if float(bloque.mean()) > 128:
            numero |= 1 << b
    return numero


def generar_video(ruta: Path, segundos: float = 3.0, w: int = 320, h: int = 240, fps: int = FPS,
                  rotacion: int = 0, audio: bool = True, estatico: bool = False) -> Path:
    """Video H.264 + AAC. ``rotacion``: matriz de visualización (antihoraria, como ``VideoFrame.rotation``)."""
    n = int(round(segundos * fps))
    base = escena(w, h)
    with av.open(str(ruta), "w") as c:
        v = c.add_stream("libx264", rate=fps)
        v.width, v.height, v.pix_fmt = w, h, "yuv420p"
        cc = v.codec_context
        cc.color_primaries, cc.color_trc, cc.colorspace, cc.color_range = 1, 1, 1, 1
        v.options = {"crf": "10", "preset": "veryfast"}
        if rotacion:
            v.set_display_rotation(rotacion)
        a = None
        if audio:
            a = c.add_stream("aac", rate=48000)
            a.layout = "stereo"
        for i in range(n):
            img = base if estatico else con_codigo(base, i)
            cuadro = av.VideoFrame.from_ndarray(img, format="rgb24").reformat(
                format="yuv420p", dst_colorspace="ITU709", dst_color_range="MPEG")
            cuadro.pts = i
            for p in v.encode(cuadro):
                c.mux(p)
        for p in v.encode():
            c.mux(p)
        if a is not None:
            sr = 48000
            total = int(segundos * sr)
            t = np.arange(total) / sr
            frecuencia = np.where(t < 1, 440.0, np.where(t < 2, 0.0, 880.0))
            senal = (0.3 * np.sin(2 * np.pi * frecuencia * t)).astype(np.float32)
            for k in range(0, total, 1024):
                trozo = np.ascontiguousarray(np.stack([senal[k:k + 1024]] * 2))
                fa = av.AudioFrame.from_ndarray(trozo, format="fltp", layout="stereo")
                fa.sample_rate = sr
                fa.pts = k
                for p in a.encode(fa):
                    c.mux(p)
            for p in a.encode():
                c.mux(p)
    return ruta


def leer_video(ruta: Path) -> tuple[list[np.ndarray], np.ndarray | None, dict]:
    """Cuadros RGB, audio (canales × muestras) y datos del archivo, leídos con PyAV directo."""
    cuadros, bloques, datos = [], [], {}
    with av.open(str(ruta)) as c:
        vs = c.streams.video[0]
        datos["fps"] = float(vs.average_rate)
        datos["duracion"] = float(vs.duration * vs.time_base) if vs.duration else c.duration / 1e6
        datos["rotacion_matriz"] = bool((vs.codec_context.coded_side_data or {}).get("display_matrix"))
        for f in c.decode(vs):
            cuadros.append(f.to_ndarray(format="rgb24"))
        datos["ancho"], datos["alto"] = cuadros[0].shape[1], cuadros[0].shape[0]
    with av.open(str(ruta)) as c:
        if c.streams.audio:
            sa = c.streams.audio[0]
            datos["frecuencia"] = sa.codec_context.sample_rate
            for f in c.decode(sa):
                bloques.append(f.to_ndarray())
    audio = np.concatenate(bloques, axis=1) if bloques else None
    return cuadros, audio, datos


def frecuencia_dominante(senal: np.ndarray, sr: int) -> float:
    espectro = np.abs(np.fft.rfft(senal * np.hanning(len(senal))))
    return float(np.fft.rfftfreq(len(senal), 1 / sr)[int(np.argmax(espectro))])


def huella(ruta: Path) -> tuple[str, int]:
    return hashlib.sha256(ruta.read_bytes()).hexdigest(), ruta.stat().st_mtime_ns


@unittest.skipIf(av is None, "Falta PyAV (pip install av==19.0.1)")
class PruebasVideo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="naturalshot_video_"))
        cls.base = generar_video(cls.dir / "base.mp4")
        cls.estatico = generar_video(cls.dir / "estatico.mp4", segundos=2.0, estatico=True, audio=False)
        cls.rotado = generar_video(cls.dir / "rotado.mp4", segundos=1.0, rotacion=-90)  # vertical, como un celular
        cls.pila = (PRESETS[PRESET_PRINCIPAL],)

    @classmethod
    def tearDownClass(cls):
        V.cerrar_lectores()
        shutil.rmtree(cls.dir, ignore_errors=True)

    # ------------------------------------------------------------ lectura
    def test_info(self):
        info = V.info_video(self.base)
        self.assertAlmostEqual(info.duracion, 3.0, delta=0.05)
        self.assertEqual(info.fps, 24.0)
        self.assertEqual((info.ancho, info.alto), (320, 240))
        self.assertAlmostEqual(info.cuadros, 72, delta=1)
        self.assertEqual(info.codec, "h264")
        self.assertTrue(info.tiene_audio)
        self.assertEqual(info.rotacion, 0)
        self.assertEqual(info.frecuencia_audio, 48000)
        self.assertFalse(V.info_video(self.estatico).tiene_audio)

    def test_cuadro_en_devuelve_el_cuadro_correcto(self):
        # En desorden, hacia atrás, entre cuadros, y seguidos (avance sin volver a buscar).
        for t in (0.0, 1.0, 1.0 + 0.5 / FPS, 2.5, 0.5, 2.95, 1.0 / FPS, 2 / FPS, 3 / FPS, 1.75, 0.0):
            rgb = V.cuadro_en(self.base, t)
            self.assertEqual(rgb.shape, (240, 320, 3))
            self.assertEqual(rgb.dtype, np.uint8)
            self.assertEqual(leer_codigo(rgb), V.indice_en(t, FPS), f"t={t}")
        # Más allá del final: el último cuadro.
        self.assertEqual(leer_codigo(V.cuadro_en(self.base, 99.0)), 71)
        chico = V.cuadro_en(self.base, 1.0, lado_max=160)
        self.assertEqual(chico.shape, (120, 160, 3))

    def test_miniaturas(self):
        tira = V.miniaturas(self.base, 6, 40)
        self.assertEqual(len(tira), 6)
        for t, img in tira:
            self.assertEqual(img.shape[0], 40)
            self.assertAlmostEqual(img.shape[1], 53, delta=1)
        self.assertEqual([round(t, 2) for t, _ in tira], [round((k + 0.5) * 0.5, 2) for k in range(6)])

    # ------------------------------------------------------------ edición
    def test_edicion_cortar_borrar_y_limites(self):
        e = V.EdicionVideo.nueva(3.0, FPS)
        self.assertEqual(e.tramos_conservados(), [(0.0, 3.0)])
        e = e.cortar(1.0).cortar(2.0)
        self.assertEqual(len(e.segmentos), 3)
        self.assertIs(e.cortar(1.0 + 0.2 / FPS), e)  # pegado a un corte: no cambia
        e = e.con_borrado(1)
        self.assertEqual(e.tramos_conservados(), [(0.0, 1.0), (2.0, 3.0)])
        self.assertAlmostEqual(e.duracion_resultante(), 2.0)
        self.assertEqual(e.proximo_visible(1.3), 2.0)
        self.assertFalse(e.se_exporta(1.5))
        self.assertEqual(e.con_borrado(1, False).tramos_conservados(), [(0.0, 3.0)])  # contiguos: se unen
        # Entrada en el cursor (primer cuadro) y salida en el cursor (último cuadro, incluido).
        e2 = e.con_entrada(0.5).con_salida(2.5)
        self.assertEqual(e2.tramos_conservados(), [(0.5, 1.0), (2.0, 2.5 + 1 / FPS)])
        self.assertEqual(e.unir_con_siguiente(0).segmentos[0], V.Segmento(0.0, 2.0, False))
        self.assertEqual(V.normalizar_tramos([(2, 3), (0, 1.2), (1, 1.5), (5, 9)], 3.0), [(0.0, 1.5), (2.0, 3.0)])

    # ------------------------------------------------------------ filtro por cuadro
    def test_filtro_cuadro_cero_igual_a_foto(self):
        img = escena(320, 240)
        np.testing.assert_array_equal(V.procesar_cuadro(img, self.pila, 0), procesar_pila(img, self.pila))

    def test_ruido_cambia_por_cuadro_y_el_resto_queda_quieto(self):
        img = escena(320, 240)
        # Con todo lo que tiene semilla: ruido, grano, variación de balance, nitidez variable y piel.
        capa = Ajustes(ruido=60, grano=50, variacion_balance=80, nitidez_variable=80, piel=60, suavizado=30, tono=40)
        a = V.procesar_cuadro(img, (capa,), 0).astype(np.float32)
        b = V.procesar_cuadro(img, (capa,), 1).astype(np.float32)
        diferencia = a - b
        self.assertGreater(float(diferencia.std()), 1.0)             # el ruido cambia
        self.assertLess(abs(float(diferencia.mean())), 0.2)           # sin cambio de brillo
        # Lo de baja frecuencia (variación de balance, nitidez variable) no cambia: si cambiara toda la
        # semilla, la diferencia suavizada llegaría a 5-6 niveles; con la de cada cuadro queda en ruido.
        baja = cv2.GaussianBlur(diferencia, (0, 0), 10)
        self.assertLess(float(np.abs(baja).max()), 2.5)
        otra = V.procesar_cuadro(img, (replace(capa, semilla=1),), 0).astype(np.float32)
        self.assertGreater(float(np.abs(cv2.GaussianBlur(a - otra, (0, 0), 10)).max()), 4.0)
        # Sin ruido ni grano, todos los cuadros son idénticos.
        sin_ruido = PRESETS["Solo color y tono (sin textura)"]
        np.testing.assert_array_equal(V.procesar_cuadro(img, (sin_ruido,), 0), V.procesar_cuadro(img, (sin_ruido,), 7))

    # ------------------------------------------------------------ exportación
    def test_exportar_sin_cortes(self):
        destino = self.dir / "sin_cortes.mp4"
        avances = []
        r = V.exportar_video(self.base, destino, self.pila, progreso=lambda h, n, s: avances.append((h, n, s)))
        self.assertTrue(destino.exists())
        self.assertEqual(r.cuadros, 72)
        self.assertEqual(avances[-1][0], avances[-1][1])
        cuadros, audio, datos = leer_video(destino)
        self.assertEqual(len(cuadros), 72)
        self.assertEqual(datos["fps"], 24.0)
        self.assertAlmostEqual(datos["duracion"], 3.0, delta=0.5 / FPS)
        self.assertEqual((datos["ancho"], datos["alto"]), (320, 240))
        self.assertEqual([leer_codigo(c) for c in cuadros], list(range(72)))
        self.assertIsNotNone(audio)
        self.assertAlmostEqual(audio.shape[1] / datos["frecuencia"], 3.0, delta=0.03)
        sr = datos["frecuencia"]
        self.assertAlmostEqual(frecuencia_dominante(audio[0, int(0.2 * sr):int(0.8 * sr)], sr), 440, delta=5)
        self.assertLess(float(np.abs(audio[0, int(1.2 * sr):int(1.8 * sr)]).max()), 0.02)  # el segundo de silencio
        self.assertAlmostEqual(frecuencia_dominante(audio[0, int(2.2 * sr):int(2.8 * sr)], sr), 880, delta=5)

    def test_exportar_con_tramos_borra_lo_del_medio(self):
        e = V.EdicionVideo.nueva(3.0, FPS).cortar(1.0).cortar(2.0).con_borrado(1)
        destino = self.dir / "con_tramos.mp4"
        V.exportar_video(self.base, destino, self.pila, e.tramos_conservados())
        cuadros, audio, datos = leer_video(destino)
        self.assertEqual([leer_codigo(c) for c in cuadros], list(range(24)) + list(range(48, 72)))
        self.assertAlmostEqual(datos["duracion"], 2.0, delta=0.5 / FPS)
        sr = datos["frecuencia"]
        duracion_audio = audio.shape[1] / sr
        self.assertAlmostEqual(duracion_audio, datos["duracion"], delta=0.03)  # audio = video
        # El silencio (segundo 1) se fue con el video: primero 440 Hz y enseguida 880 Hz.
        self.assertAlmostEqual(frecuencia_dominante(audio[0, int(0.2 * sr):int(0.8 * sr)], sr), 440, delta=5)
        self.assertAlmostEqual(frecuencia_dominante(audio[0, int(1.2 * sr):int(1.8 * sr)], sr), 880, delta=5)
        # El cambio de tono cae justo en el corte (1,0 s): sincronizado con el cuadro 48.
        energia = np.abs(audio[0])
        self.assertGreater(float(energia[int(0.95 * sr):int(1.05 * sr)].max()), 0.2)

    def test_exportar_recorte_de_principio_y_final(self):
        e = V.EdicionVideo.nueva(3.0, FPS).con_entrada(0.5).con_salida(2.0)
        destino = self.dir / "recortado.mp4"
        V.exportar_video(self.base, destino, (), e.tramos_conservados())
        cuadros, audio, datos = leer_video(destino)
        codigos = [leer_codigo(c) for c in cuadros]
        self.assertEqual(codigos, list(range(12, 49)))  # del cuadro 12 al 48 incluido
        self.assertAlmostEqual(audio.shape[1] / datos["frecuencia"], 37 / FPS, delta=0.03)

    def test_el_filtro_modifica_los_cuadros(self):
        sin = self.dir / "sin_filtro.mp4"
        con = self.dir / "con_filtro.mp4"
        V.exportar_video(self.base, sin, (), [(0, 0.5)])
        V.exportar_video(self.base, con, self.pila, [(0, 0.5)])
        a, _, _ = leer_video(sin)
        b, _, _ = leer_video(con)
        self.assertEqual(len(a), len(b))
        diferencia = np.mean([np.abs(x.astype(np.float32) - y).mean() for x, y in zip(a, b)])
        self.assertGreater(diferencia, 2.0)

    def test_video_estatico_ruido_vivo_sin_parpadeo(self):
        destino = self.dir / "estatico_filtrado.mp4"
        V.exportar_video(self.estatico, destino, self.pila)
        cuadros, _, _ = leer_video(destino)
        medias = np.array([c.astype(np.float32).mean() for c in cuadros])
        self.assertLess(float(medias.max() - medias.min()), 0.5)  # el brillo medio no parpadea
        cambios = [float((cuadros[i].astype(np.float32) - cuadros[i + 1]).std()) for i in range(0, len(cuadros) - 1, 6)]
        self.assertGreater(min(cambios), 0.8)  # pero el ruido cambia en cada cuadro

    def test_gpu_sin_placa_sale_igual_y_si_falla_vuelve_a_x264(self):
        """NS-101.2: pedir la placa de video nunca rompe la exportación."""
        destino = self.dir / "gpu.mp4"
        r = V.exportar_video(self.base, destino, self.pila, [(0, 0.5)], gpu=True)
        self.assertTrue(destino.exists())
        self.assertIn(r.codec, V.CODIFICADORES_GPU + V.CODIFICADORES_H264)
        # Una placa que "abre" en la prueba pero falla con el video real: se repite con x264.
        original = V._exportar
        llamadas = []

        def falla_con_gpu(entrada, temporal, info, pila, tramos, ancho, alto, codec, *resto):
            llamadas.append(codec)
            if codec == "h264_nvenc":
                raise RuntimeError("nvenc: no se pudo abrir la sesión")
            return original(entrada, temporal, info, pila, tramos, ancho, alto, codec, *resto)

        with mock.patch.object(V, "elegir_codificador", side_effect=lambda gpu=False: "h264_nvenc" if gpu else "libx264"), \
                mock.patch.object(V, "_exportar", side_effect=falla_con_gpu):
            r = V.exportar_video(self.base, self.dir / "gpu2.mp4", self.pila, [(0, 0.5)], gpu=True)
        self.assertEqual(llamadas, ["h264_nvenc", "libx264"])
        self.assertEqual(r.codec, "libx264")
        self.assertTrue((self.dir / "gpu2.mp4").exists())

    def test_cancelar_no_deja_archivos(self):
        destino = self.dir / "cancelado" / "no_existe.mp4"
        destino.parent.mkdir()
        estado = {"n": 0}

        def avance(h, n, s):
            estado["n"] = h

        with self.assertRaises(Cancelado):
            V.exportar_video(self.base, destino, self.pila, progreso=avance, cancelado=lambda: estado["n"] >= 5)
        self.assertFalse(destino.exists())
        self.assertEqual(list(destino.parent.iterdir()), [])

    def test_el_original_queda_intacto_y_no_se_sobrescribe(self):
        antes = huella(self.base)
        V.exportar_video(self.base, self.dir / "copia.mp4", self.pila, [(0, 0.3)])
        self.assertEqual(huella(self.base), antes)
        with self.assertRaises(ValueError):
            V.exportar_video(self.base, self.base, self.pila)
        self.assertEqual(huella(self.base), antes)
        self.assertEqual(V.ruta_salida_video(self.base).name, "base_celular.mp4")

    def test_resoluciones(self):
        self.assertEqual(V.tamano_salida(1920, 1080, "720p"), (1280, 720))
        self.assertEqual(V.tamano_salida(1080, 1920, "720p"), (720, 1280))
        self.assertEqual(V.tamano_salida(3840, 2160, "1080p"), (1920, 1080))
        self.assertEqual(V.tamano_salida(1280, 720, "1080p"), (1280, 720))  # nunca agranda
        grande = generar_video(self.dir / "grande.mp4", segundos=0.25, w=2560, h=1440, audio=False)
        for resolucion, esperado in (("Original", (2560, 1440)), ("1080p", (1920, 1080)), ("720p", (1280, 720))):
            destino = self.dir / f"res_{resolucion}.mp4"
            r = V.exportar_video(grande, destino, (), resolucion=resolucion, calidad="Liviana")
            cuadros, _, datos = leer_video(destino)
            self.assertEqual((datos["ancho"], datos["alto"]), esperado, resolucion)
            self.assertEqual((r.ancho, r.alto), esperado)
            self.assertEqual(len(cuadros), 6)

    def test_video_con_rotacion(self):
        info = V.info_video(self.rotado)
        self.assertEqual(info.rotacion, 270)  # -90: girar 90° en sentido horario
        self.assertEqual((info.ancho, info.alto), (240, 320))
        rgb = V.cuadro_en(self.rotado, 0.5)
        self.assertEqual(rgb.shape, (320, 240, 3))
        self.assertEqual(leer_codigo(rgb, info.rotacion), 12)
        # La banda del código (arriba en el archivo) se ve a la derecha, como en el celular.
        self.assertGreater(abs(float(rgb[:, 200:220].std()) - float(rgb[:, 20:40].std())), 1.0)
        destino = self.dir / "rotado_exportado.mp4"
        V.exportar_video(self.rotado, destino, self.pila, [(0.25, 0.75)], resolucion="720p")
        cuadros, audio, datos = leer_video(destino)
        self.assertEqual((datos["ancho"], datos["alto"]), (240, 320))  # ya derecho
        self.assertFalse(datos["rotacion_matriz"])  # sin metadata de rotación: no se gira dos veces
        self.assertEqual([leer_codigo(c, info.rotacion) for c in cuadros], list(range(6, 18)))
        self.assertAlmostEqual(audio.shape[1] / datos["frecuencia"], 0.5, delta=0.03)

    def test_miniaturas_con_un_solo_keyframe(self):
        # Algunos videos traen un único keyframe al principio: las miniaturas no
        # pueden salir todas iguales (ni ninguna).

        ruta = Path(tempfile.mkdtemp()) / "un_keyframe.mp4"
        c = av.open(str(ruta), "w")
        v = c.add_stream("libx264", rate=24, options={"g": "1000", "keyint_min": "1000", "sc_threshold": "0"})
        v.width, v.height, v.pix_fmt = 160, 120, "yuv420p"
        for i in range(72):
            f = np.zeros((120, 160, 3), np.uint8)
            f[:, :, 1] = i * 3
            for p in v.encode(av.VideoFrame.from_ndarray(f, format="rgb24")):
                c.mux(p)
        for p in v.encode():
            c.mux(p)
        c.close()
        m = V.miniaturas(ruta, 6, 30)
        self.assertEqual(len(m), 6)
        verdes = [float(a[..., 1].mean()) for _, a in m]
        self.assertEqual(len({round(x) for x in verdes}), 6, "cada miniatura tiene que ser de su momento")
        self.assertEqual(verdes, sorted(verdes))


@unittest.skipIf(av is None, "Falta PyAV (pip install av==19.0.1)")
class PruebasVentanaVideo(unittest.TestCase):
    """El modo Video de la ventana real, en modo sin pantalla (QT_QPA_PLATFORM=offscreen).

    El editor de video va adentro de la ventana principal (ya no es una ventana aparte):
    la prueba abre el video desde la ventana y maneja el editor con el teclado."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        from celular_natural.ui.estilo import HOJA_ESTILO
        cls.app = QApplication.instance() or QApplication([])
        # Las pruebas de interfaz anteriores cierran sus ventanas con deleteLater(), pero sin un
        # bucle de eventos corriendo nunca se borran: corriendo toda la suite quedaban 34 ventanas
        # (30 mil widgets, cada una con sus filtros de eventos en toda la app) y volver a poner la
        # hoja de estilo las re-pulía todas durante más de 15 minutos. Se completa ese borrado.
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        if cls.app.styleSheet() != HOJA_ESTILO:
            cls.app.setStyleSheet(HOJA_ESTILO)
        cls.dir = Path(tempfile.mkdtemp(prefix="naturalshot_ventana_"))
        # La ventana lee el modo y los presets propios: que use un .ini y un APPDATA de prueba.
        cls._entorno = {k: os.environ.get(k) for k in ("APPDATA", "NATURALSHOT_CONFIG")}
        os.environ["APPDATA"] = str(cls.dir / "appdata")
        os.environ["NATURALSHOT_CONFIG"] = str(cls.dir / "config.ini")
        cls.video = generar_video(cls.dir / "clip.mp4")

    @classmethod
    def tearDownClass(cls):
        V.cerrar_lectores()
        for clave, valor in cls._entorno.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
        shutil.rmtree(cls.dir, ignore_errors=True)

    def esperar(self, condicion, limite: float = 30.0) -> bool:
        # time.sleep suelta el GIL; QTest.qWait no, y frenaría los hilos que procesan los cuadros.
        fin = time.monotonic() + limite
        while time.monotonic() < fin:
            self.app.processEvents()
            if condicion():
                return True
            time.sleep(0.01)
        return condicion()

    def test_abrir_cortar_borrar_y_exportar(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from celular_natural.ui import editor_video as E
        from celular_natural.ui.ventana import VentanaPrincipal

        principal = VentanaPrincipal()
        principal.resize(1366, 768)
        principal.show()
        principal.activateWindow()
        # El filtro de las fotos pasa al video la primera vez que se entra a Video.
        principal.panel_ajustes.combo_preset.setCurrentText("Celular natural — sutil")
        principal.abrir_editor_video(str(self.video))
        ventana = principal.editor_video  # el editor, adentro de la ventana principal
        try:
            self.assertEqual(principal.modo, "video")
            self.assertIs(ventana.window(), principal)
            self.assertTrue(self.esperar(lambda: ventana.info is not None))
            self.assertEqual(ventana.panel_ajustes.pila()[0], PRESETS["Celular natural — sutil"])
            self.assertTrue(self.esperar(lambda: ventana.cuadro_procesado_listo()))
            # Cursor a 1 s y cortar (S); a 2 s y cortar; seleccionar el del medio y borrarlo (Supr).
            ventana.ir_a(1.0)
            QTest.keyClick(ventana, Qt.Key_S)
            ventana.ir_a(2.0)
            QTest.keyClick(ventana, Qt.Key_S)
            self.assertEqual(len(ventana.edicion.segmentos), 3)
            ventana.linea.seleccionar(1)
            QTest.keyClick(ventana, Qt.Key_Delete)
            self.assertEqual(ventana.edicion.tramos_conservados(), [(0.0, 1.0), (2.0, 3.0)])
            self.assertIn("0:02", ventana.etiqueta_resultado.text())
            # Deshacer y rehacer.
            QTest.keyClick(ventana, Qt.Key_Z, Qt.ControlModifier)
            self.assertEqual(ventana.edicion.tramos_conservados(), [(0.0, 3.0)])
            QTest.keyClick(ventana, Qt.Key_Y, Qt.ControlModifier)
            self.assertEqual(ventana.edicion.tramos_conservados(), [(0.0, 1.0), (2.0, 3.0)])
            # Cuadro a cuadro y saltos de un segundo.
            ventana.ir_a(0.0)
            QTest.keyClick(ventana, Qt.Key_Right)
            self.assertAlmostEqual(ventana.tiempo, 1 / FPS, places=6)
            QTest.keyClick(ventana, Qt.Key_L)
            # Un segundo adelante en lo que se ve: lo borrado (de 1 a 2 s) ya no está en la línea de tiempo.
            self.assertAlmostEqual(ventana.tiempo_resultado, 1 + 1 / FPS, places=6)
            self.assertAlmostEqual(ventana.tiempo, 2 + 1 / FPS, places=6)
            QTest.keyClick(ventana, Qt.Key_J)
            QTest.keyClick(ventana, Qt.Key_Left)
            self.assertAlmostEqual(ventana.tiempo, 0.0, places=6)
            # Exportar con un diálogo falso.
            destino = self.dir / "clip_exportado.mp4"
            with mock.patch.object(E.QFileDialog, "getSaveFileName", return_value=(str(destino), "MP4 (*.mp4)")), \
                    mock.patch.object(E.QMessageBox, "information") as aviso:
                ventana.exportar()
                self.assertTrue(ventana.exportando)
                self.assertTrue(self.esperar(lambda: not ventana.exportando, 120))
                self.assertTrue(destino.exists())
                aviso.assert_called_once()
                self.assertIn(str(destino), aviso.call_args.args[2])  # el aviso muestra la ruta
            cuadros, audio, datos = leer_video(destino)
            self.assertEqual([leer_codigo(c) for c in cuadros], list(range(24)) + list(range(48, 72)))
            self.assertAlmostEqual(audio.shape[1] / datos["frecuencia"], 2.0, delta=0.03)
        finally:
            from PySide6.QtCore import QEvent
            from PySide6.QtWidgets import QApplication
            principal.close()
            principal.deleteLater()
            self.app.processEvents()
            QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
