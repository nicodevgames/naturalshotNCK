"""Pruebas del motor de sonido (``motor/audio.py``) y del audio al exportar video.

Los videos se generan acá mismo con PyAV, en una carpeta temporal: cuadros chicos
de color y audio sintético (tonos, silencios y una "escalera" de 440, 660 y
880 Hz, una por segundo, para saber de qué instante del original viene cada
parte). Nada de archivos del usuario.

Para medir con exactitud se exporta a WAV (sin compresión): con los ajustes por
defecto, las muestras salen idénticas a las del original.
"""

from __future__ import annotations

import pickle
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import av
except ImportError:  # pragma: no cover
    av = None

from celular_natural.motor import Cancelado  # noqa: E402
from celular_natural.motor.audio import GANANCIA_MAX_NORMALIZAR, AjustesAudio  # noqa: E402  (no carga PyAV)

if av is not None:
    from celular_natural.motor import audio as A  # noqa: E402
    from celular_natural.motor import video as V  # noqa: E402

SR = 48000
FPS = 24
OBJETIVO = 10 ** (-1 / 20)  # -1 dBFS


# ---------------------------------------------------------------------------
# Medios de prueba
# ---------------------------------------------------------------------------

def tono(segundos: float, frecuencia: float = 440.0, amplitud: float = 0.3, canales: int = 2) -> np.ndarray:
    t = np.arange(int(round(segundos * SR))) / SR
    return np.repeat((amplitud * np.sin(2 * np.pi * frecuencia * t)).astype(np.float32)[None, :], canales, 0)


def escalera(segundos: int = 3, amplitud: float = 0.3) -> np.ndarray:
    """440, 660 y 880 Hz (y así), un segundo cada uno: dice de qué segundo del original viene el audio."""
    partes = [tono(1.0, 440.0 + 220.0 * (k % 3), amplitud) for k in range(segundos)]
    return np.concatenate(partes, axis=1)


def generar(ruta: Path, senal: np.ndarray | None, segundos: float | None = None, fps: int = FPS,
            vcodec: str = "libx264", acodec: str = "aac", trozo: int = 1024) -> Path:
    """Video de cuadros de color (96×64) con ``senal`` (canales × muestras, a 48 kHz) como audio."""
    if segundos is None:
        segundos = senal.shape[1] / SR
    with av.open(str(ruta), "w") as c:
        v = c.add_stream(vcodec, rate=fps)
        v.width, v.height, v.pix_fmt = 96, 64, "yuv420p"
        if vcodec == "libx264":
            v.options = {"preset": "ultrafast"}
        a = None
        if senal is not None:
            a = c.add_stream(acodec, rate=SR)
            a.layout = "stereo" if senal.shape[0] == 2 else "mono"
        for i in range(int(round(segundos * fps))):
            img = np.full((64, 96, 3), (i * 7) % 256, np.uint8)
            cuadro = av.VideoFrame.from_ndarray(img, format="rgb24").reformat(format="yuv420p")
            cuadro.pts = i
            for p in v.encode(cuadro):
                c.mux(p)
        for p in v.encode():
            c.mux(p)
        if a is not None:
            formato = a.codec_context.format.name if a.codec_context.format else "fltp"
            layout = a.layout.name
            for k in range(0, senal.shape[1], trozo):
                datos = senal[:, k:k + trozo]
                if formato == "s16":
                    entero = np.clip(np.round(datos * 32768), -32768, 32767).astype(np.int16)
                    fa = av.AudioFrame.from_ndarray(np.ascontiguousarray(entero.T).reshape(1, -1), format="s16",
                                                    layout=layout)
                elif formato == "flt":
                    fa = av.AudioFrame.from_ndarray(np.ascontiguousarray(datos.T).reshape(1, -1), format="flt",
                                                    layout=layout)
                else:
                    fa = av.AudioFrame.from_ndarray(np.ascontiguousarray(datos), format="fltp", layout=layout)
                fa.sample_rate = SR
                fa.pts = k
                for p in a.encode(fa):
                    c.mux(p)
            for p in a.encode():
                c.mux(p)
    return ruta


def leer_audio(ruta: Path) -> tuple[np.ndarray | None, int]:
    """Todo el audio del archivo como float32 (canales × muestras), decodificado con PyAV directo."""
    bloques = []
    with av.open(str(ruta)) as c:
        if not c.streams.audio:
            return None, 0
        sa = c.streams.audio[0]
        sr = sa.codec_context.sample_rate
        rs = av.AudioResampler(format="fltp", layout=sa.codec_context.layout.name, rate=sr)
        for f in c.decode(sa):
            for g in rs.resample(f):
                bloques.append(g.to_ndarray())
    return np.concatenate(bloques, axis=1), sr


def leer_wav(ruta: Path) -> np.ndarray:
    """Muestras int16 (canales × muestras) de un audio PCM de 16 bits (WAV, o la pista de un MKV), sin convertir."""
    bloques = []
    with av.open(str(ruta)) as c:
        sa = c.streams.audio[0]
        canales = sa.codec_context.layout.nb_channels
        for f in c.decode(sa):
            bloques.append(f.to_ndarray().reshape(-1, canales).T)
    return np.concatenate(bloques, axis=1)


def saltos(x: np.ndarray, frecuencia: float = 440.0, amplitud: float = 0.3, desde: int = 0,
           hasta: int | None = None) -> tuple[int, int]:
    """(saltos, huecos): diferencias de muestra a muestra mucho mayores que las de un seno, y
    corridas de 4 o más muestras casi en cero (un seno no se queda en cero)."""
    x = x[desde:hasta]
    esperado = amplitud * 2 * np.pi * frecuencia / SR
    grandes = int(np.count_nonzero(np.abs(np.diff(x)) > 2.0 * esperado))
    cero = np.concatenate(([0], (np.abs(x) < 1e-3).astype(np.int8), [0]))
    bordes = np.diff(cero)
    largos = np.flatnonzero(bordes == -1) - np.flatnonzero(bordes == 1)
    return grandes, int(np.count_nonzero(largos >= 4))


def pico_en(x: np.ndarray, t0: float, t1: float) -> float:
    return float(np.abs(x[..., int(t0 * SR):int(t1 * SR)]).max())


def frecuencia_dominante(senal: np.ndarray, sr: int = SR) -> float:
    espectro = np.abs(np.fft.rfft(senal * np.hanning(len(senal))))
    return float(np.fft.rfftfreq(len(senal), 1 / sr)[int(np.argmax(espectro))])


# ---------------------------------------------------------------------------
# AjustesAudio (sin PyAV)
# ---------------------------------------------------------------------------

class PruebasAjustes(unittest.TestCase):
    def test_por_defecto_no_cambian_nada(self):
        a = AjustesAudio()
        self.assertTrue(a.sin_cambios())
        self.assertEqual(a.ganancia(), 1.0)
        self.assertFalse(AjustesAudio(volumen=0.9).sin_cambios())
        self.assertFalse(AjustesAudio(silencios=((1, 2),)).sin_cambios())

    def test_valores_acomodados(self):
        a = AjustesAudio(volumen=5, fundido_entrada=-1, fundido_salida=float("nan"),
                         silencios=((3, 4), (0.5, 1.0), (0.9, 1.5), (2, 2), (-1, 0.2), (5, 4)))
        self.assertEqual(a.volumen, 2.0)
        self.assertEqual(a.fundido_entrada, 0.0)
        self.assertEqual(a.fundido_salida, 0.0)
        self.assertEqual(a.silencios, ((0.0, 0.2), (0.5, 1.5), (3.0, 4.0)))
        self.assertEqual(AjustesAudio(volumen=-3).volumen, 0.0)
        with self.assertRaises(Exception):
            a.volumen = 1.0  # inmutable

    def test_silencios(self):
        a = AjustesAudio().con_silencio(1.0, 2.0).con_silencio(4.0, 5.0)
        self.assertEqual(a.silencios, ((1.0, 2.0), (4.0, 5.0)))
        self.assertEqual(a.con_silencio(1.5, 4.2).silencios, ((1.0, 5.0),))  # se une con los que pisa
        self.assertEqual(a.con_silencio(2.0, 3.0).silencios, ((1.0, 3.0), (4.0, 5.0)))  # y con los que toca
        self.assertEqual(a.sin_silencio(0).silencios, ((4.0, 5.0),))
        self.assertIs(a.sin_silencio(7), a)
        self.assertEqual(a.con_sonido(1.2, 1.5).silencios, ((1.0, 1.2), (1.5, 2.0), (4.0, 5.0)))  # lo parte
        self.assertEqual(a.con_sonido(0.0, 4.5).silencios, ((4.5, 5.0),))
        self.assertEqual(a.silencio_en(1.5), 0)
        self.assertEqual(a.silencio_en(4.0), 1)
        self.assertIsNone(a.silencio_en(3.0))
        self.assertTrue(a.silenciado(1.2, 1.8))
        self.assertFalse(a.silenciado(1.5, 2.5))
        self.assertEqual(a.sin_silencios().silencios, ())
        self.assertEqual(a.con(volumen=0.5).silencios, a.silencios)

    def test_ganancia_y_orden_con_normalizar(self):
        self.assertEqual(AjustesAudio(volumen=0.5).ganancia(), 0.5)
        self.assertEqual(AjustesAudio(quitar=True, volumen=2).ganancia(), 0.0)
        n = AjustesAudio(normalizar=True)
        self.assertAlmostEqual(n.ganancia(0.5), OBJETIVO / 0.5)
        self.assertAlmostEqual(n.con(volumen=0.5).ganancia(0.5), OBJETIVO)        # el volumen va después y baja
        self.assertAlmostEqual(n.con(volumen=2.0).ganancia(0.5), OBJETIVO / 0.5)  # pero nunca se pasa de -1 dBFS
        self.assertAlmostEqual(n.ganancia(0.0), 1.0)                              # silencio: no se toca
        self.assertAlmostEqual(n.ganancia(1e-6), GANANCIA_MAX_NORMALIZAR)                 # como mucho +30 dB
        with self.assertRaises(ValueError):
            n.ganancia()

    def test_pickle(self):
        a = AjustesAudio(quitar=False, volumen=1.3, normalizar=True, fundido_entrada=0.5, fundido_salida=1.0,
                         silencios=((1.0, 2.0), (3.5, 4.0)))
        b = pickle.loads(pickle.dumps(a, protocol=pickle.HIGHEST_PROTOCOL))
        self.assertEqual(a, b)
        self.assertIsInstance(b, AjustesAudio)
        # La sesión rearma cada dataclass con sus campos (sesion._reconstruir): tiene que dar lo mismo.
        self.assertEqual(AjustesAudio(**vars(b)), a)
        self.assertEqual(hash(a), hash(b))

    def test_importar_ajustes_no_carga_pyav(self):
        import subprocess
        codigo = ("import sys; from celular_natural.motor.audio import AjustesAudio; "
                  "AjustesAudio().con_silencio(1, 2); print('av' in sys.modules)")
        salida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                                cwd=str(Path(__file__).resolve().parent.parent), timeout=60)
        self.assertEqual(salida.stdout.strip(), "False", salida.stderr)


# ---------------------------------------------------------------------------
# Motor de sonido con PyAV
# ---------------------------------------------------------------------------

@unittest.skipIf(av is None, "Falta PyAV (pip install av==19.0.1)")
class PruebasAudio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="naturalshot_audio_"))
        cls.tono = generar(cls.dir / "tono.mp4", tono(3.0))
        cls.tono4 = generar(cls.dir / "tono4.mp4", tono(4.0))
        cls.escalera = generar(cls.dir / "escalera.mp4", escalera(3))
        senal = np.concatenate([tono(1.0, 440, 0.5), np.zeros((2, SR), np.float32), tono(1.0, 440, 0.25)], axis=1)
        cls.onda = generar(cls.dir / "onda.mp4", senal)
        cls.mudo = generar(cls.dir / "mudo.mp4", None, segundos=1.0)
        cls.pcm_mkv = generar(cls.dir / "pcm.mkv", escalera(3), acodec="pcm_s16le")
        # El tono ya pasó por el AAC al generarlo: su pico real es un poco más que 0,3.
        cls.pico_tono = pico_en(leer_audio(cls.tono)[0], 0.1, 2.9)

    @classmethod
    def tearDownClass(cls):
        V.cerrar_lectores()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def salida(self, nombre: str) -> Path:
        return self.dir / nombre

    def _exportar_wav(self, origen: Path, nombre: str, tramos=None, ajustes=None) -> Path:
        destino = self.salida(nombre)
        A.exportar_audio(origen, destino, tramos, ajustes)
        return destino

    def wav(self, nombre: str, origen: Path, tramos=None, ajustes=None) -> np.ndarray:
        """Exporta a WAV y devuelve las muestras (sin compresión: se mide exacto)."""
        return leer_wav(self._exportar_wav(origen, nombre, tramos, ajustes)).astype(np.float64) / 32768.0

    # ------------------------------------------------------------ el bug de MKV
    def test_reloj_pega_marcas_redondeadas_al_milisegundo(self):
        class Cuadro:  # lo que importa de un av.AudioFrame
            def __init__(self, pts, tb, n):
                self.pts, self.time_base, self.samples = pts, tb, n

        from fractions import Fraction
        reloj = A.RelojAudio(SR, Fraction(1, 1000))
        posiciones = [reloj.ubicar(Cuadro(round(k * 1024 / SR * 1000), Fraction(1, 1000), 1024)) for k in range(50)]
        self.assertEqual(posiciones, [k * 1024 for k in range(50)])
        # Un hueco de verdad (100 ms sin audio) se respeta.
        self.assertEqual(reloj.ubicar(Cuadro(round(50 * 1024 / SR * 1000) + 100, Fraction(1, 1000), 1024)),
                         round((round(50 * 1024 / SR * 1000) + 100) / 1000 * SR))

    def _sin_saltos_al_exportar(self, origen: Path, nombre: str, tramos=None):
        destino = self.salida(nombre)
        V.exportar_video(origen, destino, (), tramos)
        audio, sr = leer_audio(destino)
        self.assertEqual(sr, SR)
        fin = audio.shape[1] - int(0.05 * SR)
        grandes, _ = saltos(audio[0], desde=int(0.05 * SR), hasta=fin)
        self.assertEqual(grandes, 0, f"{origen.name}: saltos")
        # Huecos de silencio: fuera de las uniones, donde el fundido corto baja a cero a propósito.
        uniones = np.cumsum([b - a for a, b in (tramos or [(0.0, 3.0)])])[:-1]
        bordes = [int(0.05 * SR)] + [x for u in uniones for x in (int((u - 0.01) * SR), int((u + 0.01) * SR))] + [fin]
        huecos = sum(saltos(audio[0], desde=a, hasta=b)[1] for a, b in zip(bordes[::2], bordes[1::2]))
        self.assertEqual(huecos, 0, f"{origen.name}: huecos")
        return audio

    def test_mkv_sin_saltos(self):
        # Antes del arreglo: 388 saltos y 5 huecos en 3 s de un tono (AAC en MKV, marcas al milisegundo).
        mkv = generar(self.salida("tono.mkv"), tono(3.0))
        audio = self._sin_saltos_al_exportar(mkv, "desde_mkv.mp4")
        self.assertAlmostEqual(audio.shape[1] / SR, 3.0, delta=0.03)
        # Con cortes, y con PCM en cuadros de 1024 muestras (antes: 387 saltos).
        self._sin_saltos_al_exportar(mkv, "desde_mkv_cortado.mp4", [(0.0, 1.0), (2.0, 3.0)])
        pcm = generar(self.salida("tono_pcm.mkv"), tono(3.0), acodec="pcm_s16le")
        self._sin_saltos_al_exportar(pcm, "desde_pcm_mkv.mp4")

    def test_webm_sin_saltos(self):
        try:
            webm = generar(self.salida("tono.webm"), tono(3.0), vcodec="libvpx", acodec="libopus")
        except Exception as error:  # pragma: no cover - depende de la instalación
            self.skipTest(f"Este PyAV no puede escribir WebM (VP8 + Opus): {error}")
        self._sin_saltos_al_exportar(webm, "desde_webm.mp4")
        self._sin_saltos_al_exportar(webm, "desde_webm_cortado.mp4", [(0.0, 1.0), (2.0, 3.0)])

    def test_mp4_sin_saltos(self):
        self._sin_saltos_al_exportar(self.tono, "desde_mp4.mp4")

    # ------------------------------------------------------------ por defecto = idéntico
    def test_por_defecto_la_salida_es_identica(self):
        # PCM de 16 bits -> WAV sin tocar nada: las mismas muestras, una por una.
        original = leer_wav(self.pcm_mkv)
        np.testing.assert_array_equal(leer_wav(self._exportar_wav(self.pcm_mkv, "identico.wav")), original)
        # El lector de la vista previa, con el formato del original, da lo mismo que decodificar directo.
        directo, _ = leer_audio(self.tono)
        with A.LectorPCM(self.tono, formato="f32") as lector:
            escuchado = lector.leer_array(10 * SR).T
        np.testing.assert_array_equal(escuchado, directo[:, :escuchado.shape[1]])
        self.assertAlmostEqual(escuchado.shape[1] / SR, 3.0, delta=1 / FPS)
        # exportar_video sin ajustes y con AjustesAudio(): el mismo audio.
        V.exportar_video(self.tono, self.salida("sin_ajustes.mp4"), (), [(0.0, 1.5)])
        V.exportar_video(self.tono, self.salida("ajustes_vacios.mp4"), (), [(0.0, 1.5)], audio=AjustesAudio())
        a, _ = leer_audio(self.salida("sin_ajustes.mp4"))
        b, _ = leer_audio(self.salida("ajustes_vacios.mp4"))
        np.testing.assert_array_equal(a, b)
        # Y parecido al original (lo que cambia el AAC al recomprimir).
        n = min(a.shape[1], int(1.4 * SR))
        self.assertLess(float(np.abs(a[:, int(0.1 * SR):n] - directo[:, int(0.1 * SR):n]).max()), 0.02)

    # ------------------------------------------------------------ ajustes
    def test_quitar(self):
        r = V.exportar_video(self.tono, self.salida("sin_sonido.mp4"), (), [(0.0, 1.0)],
                             audio=AjustesAudio(quitar=True, volumen=2))
        self.assertFalse(r.con_audio)
        with av.open(str(r.ruta)) as c:
            self.assertEqual(len(c.streams.audio), 0)
            self.assertEqual(len(c.streams.video), 1)
        with self.assertRaises(ValueError):
            A.exportar_audio(self.tono, self.salida("nada.wav"), ajustes=AjustesAudio(quitar=True))
        self.assertFalse(self.salida("nada.wav").exists())
        with A.LectorPCM(self.tono, ajustes=AjustesAudio(quitar=True), formato="f32") as lector:
            self.assertEqual(float(np.abs(lector.leer_array(SR)).max()), 0.0)

    def test_volumen(self):
        base = self.wav("vol_1.wav", self.tono)
        medio = self.wav("vol_05.wav", self.tono, ajustes=AjustesAudio(volumen=0.5))
        np.testing.assert_allclose(medio, base * 0.5, atol=1.5 / 32768)
        doble = self.wav("vol_2.wav", self.tono, ajustes=AjustesAudio(volumen=2.0))
        self.assertAlmostEqual(float(np.abs(doble).max()), 2 * float(np.abs(base).max()), delta=0.001)
        cero = self.wav("vol_0.wav", self.tono, ajustes=AjustesAudio(volumen=0.0))
        self.assertEqual(float(np.abs(cero).max()), 0.0)
        # Con volumen 2, un tono fuerte satura: se recorta a ±1 en vez de dar la vuelta.
        fuerte = generar(self.salida("fuerte.mp4"), tono(1.0, amplitud=0.8))
        saturado = self.wav("vol_saturado.wav", fuerte, ajustes=AjustesAudio(volumen=2.0))
        self.assertGreater(float(saturado.max()), 0.99)
        self.assertLessEqual(float(np.abs(saturado).max()), 1.0)
        # Exportando video (AAC): la mitad de la amplitud.
        V.exportar_video(self.tono, self.salida("vol_video.mp4"), (), audio=AjustesAudio(volumen=0.5))
        audio, _ = leer_audio(self.salida("vol_video.mp4"))
        self.assertAlmostEqual(pico_en(audio, 0.5, 2.5), self.pico_tono / 2, delta=0.01)

    def test_normalizar(self):
        directo, _ = leer_audio(self.tono)
        self.assertAlmostEqual(A.medir_pico(self.tono), pico_en(directo, 0.0, 3.0), delta=1e-6)
        normal = self.wav("norm.wav", self.tono, ajustes=AjustesAudio(normalizar=True))
        self.assertAlmostEqual(float(np.abs(normal).max()), OBJETIVO, delta=0.001)
        # El volumen va después: solo baja.
        medio = self.wav("norm_05.wav", self.tono, ajustes=AjustesAudio(normalizar=True, volumen=0.5))
        self.assertAlmostEqual(float(np.abs(medio).max()), OBJETIVO / 2, delta=0.001)
        doble = self.wav("norm_2.wav", self.tono, ajustes=AjustesAudio(normalizar=True, volumen=2.0))
        self.assertAlmostEqual(float(np.abs(doble).max()), OBJETIVO, delta=0.001)
        # El pico es el de lo que se exporta: un golpe fuerte en un tramo borrado o silenciado no cuenta.
        senal = tono(3.0, amplitud=0.2)
        senal[:, int(1.0 * SR):int(1.5 * SR)] = tono(0.5, amplitud=0.95)
        golpe = generar(self.salida("golpe.mp4"), senal)
        decodificado, _ = leer_audio(golpe)
        pico_tono = max(pico_en(decodificado, 0.0, 0.9), pico_en(decodificado, 1.6, 3.0))
        self.assertAlmostEqual(pico_tono, 0.2, delta=0.01)
        self.assertAlmostEqual(A.medir_pico(golpe), pico_en(decodificado, 0.0, 3.0), delta=1e-6)
        self.assertGreater(A.medir_pico(golpe), 0.9)
        self.assertAlmostEqual(A.medir_pico(golpe, [(0.0, 0.9), (1.6, 3.0)]), pico_tono, delta=0.003)
        ajustes = AjustesAudio(normalizar=True, silencios=((0.95, 1.55),))
        self.assertAlmostEqual(A.medir_pico(golpe, None, ajustes.silencios), pico_tono, delta=0.003)
        resultado = self.wav("norm_golpe.wav", golpe, ajustes=ajustes)
        self.assertAlmostEqual(float(np.abs(resultado).max()), OBJETIVO, delta=0.001)
        self.assertEqual(pico_en(resultado, 1.0, 1.5), 0.0)
        # Caché: la segunda vez es inmediata.
        t0 = time.perf_counter()
        A.medir_pico(golpe, None, ajustes.silencios)
        self.assertLess(time.perf_counter() - t0, 0.05)
        # Exportando video (AAC): cerca de -1 dBFS (el AAC puede pasarse un poco del original).
        V.exportar_video(self.tono, self.salida("norm_video.mp4"), (), audio=AjustesAudio(normalizar=True))
        audio, _ = leer_audio(self.salida("norm_video.mp4"))
        self.assertAlmostEqual(float(np.abs(audio).max()), OBJETIVO, delta=0.04)

    def test_fundidos_en_el_tiempo_del_resultado(self):
        tramos = [(0.0, 1.0), (2.0, 3.0)]  # queda 2 s
        base = self.wav("fund_base.wav", self.tono, tramos)
        ajustes = AjustesAudio(fundido_entrada=0.5, fundido_salida=0.5)
        fundido = self.wav("fund.wav", self.tono, tramos, ajustes)
        self.assertEqual(base.shape, fundido.shape)
        self.assertAlmostEqual(base.shape[1] / SR, 2.0, delta=1e-3)
        # Ganancia en cada instante del resultado = fundido / base (donde la base no está cerca de cero).
        def ganancia(t: float) -> float:
            i = int(t * SR)
            ventana = slice(i - 60, i + 60)
            b, f = base[0, ventana], fundido[0, ventana]
            k = int(np.argmax(np.abs(b)))
            return float(f[k] / b[k])
        self.assertAlmostEqual(ganancia(0.25), 0.25, delta=0.01)   # (0,25 / 0,5)² en la entrada
        self.assertAlmostEqual(ganancia(1.75), 0.25, delta=0.01)   # y en la salida, al final de lo que queda
        self.assertAlmostEqual(ganancia(0.75), 1.0, delta=0.002)
        self.assertAlmostEqual(ganancia(1.25), 1.0, delta=0.002)   # el corte no reinicia los fundidos
        self.assertLess(pico_en(fundido, 0.0, 0.01), 0.002)
        self.assertLess(pico_en(fundido, 1.99, 2.0), 0.002)

    def test_silencios_en_tiempo_original_con_cortes(self):
        tramos = [(0.0, 1.0), (2.0, 4.0)]  # se borra del segundo 1 al 2: queda 3 s
        ajustes = AjustesAudio(silencios=((2.5, 3.0), (0.8, 2.2)))
        r = self.wav("silencios.wav", self.tono4, tramos, ajustes)
        base = self.wav("silencios_base.wav", self.tono4, tramos)
        self.assertAlmostEqual(r.shape[1] / SR, 3.0, delta=1e-3)
        # (2,5 - 3,0) original -> (1,5 - 2,0) del resultado; (0,8 - 2,2) -> (0,8 - 1,2) atravesando el corte.
        self.assertEqual(pico_en(r, 1.5, 2.0), 0.0)
        self.assertEqual(pico_en(r, 0.8, 1.2), 0.0)
        # Fuera de los silencios (y de sus rampas de 5 ms), idéntico a no silenciar nada.
        for t0, t1 in ((0.0, 0.794), (1.206, 1.494), (2.006, 3.0)):
            np.testing.assert_array_equal(r[:, int(t0 * SR):int(t1 * SR)], base[:, int(t0 * SR):int(t1 * SR)])
        self.assertGreater(pico_en(r, 2.01, 2.99), 0.29)
        # Las rampas de 5 ms quedan afuera del silencio: entran sin clic.
        self.assertEqual(saltos(r[0], hasta=int(2.9 * SR))[0], 0)
        # La vista previa da exactamente lo mismo que el archivo.
        with A.LectorPCM(self.tono4, tramos, ajustes, formato="s16") as lector:
            crudo = lector.leer(10 * SR)
        escuchado = np.frombuffer(crudo, "<i2").reshape(-1, 2).T.astype(np.float64) / 32768.0
        np.testing.assert_array_equal(escuchado, r)
        # Exportando video (AAC) también.
        V.exportar_video(self.tono4, self.salida("silencios.mp4"), (), tramos, audio=ajustes)
        audio, _ = leer_audio(self.salida("silencios.mp4"))
        self.assertLess(pico_en(audio, 1.52, 1.98), 0.01)
        self.assertLess(pico_en(audio, 0.82, 1.18), 0.01)
        self.assertGreater(pico_en(audio, 2.1, 2.9), 0.25)

    def test_sin_clics_en_las_uniones(self):
        # Corte a mitad de onda: a 1,0007 s el tono vale 0,28 y a 1,5 s vale 0; pegados sin más, un salto de 0,28.
        tramos = [(0.0, 1.0007), (1.5, 3.0)]
        directo, _ = leer_audio(self.tono)
        crudo = np.concatenate([directo[0, :round(1.0007 * SR)], directo[0, round(1.5 * SR):]])
        self.assertGreater(saltos(crudo)[0], 0)  # la prueba tiene sentido: sin fundidos hay clic
        r = self.wav("union.wav", self.tono, tramos)
        self.assertEqual(saltos(r[0], hasta=r.shape[1] - 10)[0], 0)
        self.assertLess(pico_en(r, 1.0007 - 0.0002, 1.0007 + 0.0002), 0.02)  # pasa por silencio en la unión
        # Y nada más se toca: lejos de la unión, las mismas muestras que el original.
        np.testing.assert_allclose(r[0, :int(0.99 * SR)], directo[0, :int(0.99 * SR)], atol=1 / 32768)
        V.exportar_video(self.tono, self.salida("union.mp4"), (), tramos)
        audio, _ = leer_audio(self.salida("union.mp4"))
        self.assertEqual(saltos(audio[0], desde=int(0.05 * SR), hasta=audio.shape[1] - int(0.05 * SR))[0], 0)

    def test_exportar_video_con_todo(self):
        ajustes = AjustesAudio(volumen=0.5, fundido_entrada=0.3, fundido_salida=0.3, silencios=((2.2, 2.6),))
        r = V.exportar_video(self.escalera, self.salida("todo.mp4"), (), [(0.0, 1.0), (2.0, 3.0)], audio=ajustes)
        self.assertTrue(r.con_audio)
        audio, _ = leer_audio(r.ruta)
        self.assertAlmostEqual(audio.shape[1] / SR, 2.0, delta=0.03)
        self.assertAlmostEqual(frecuencia_dominante(audio[0, int(0.4 * SR):int(0.9 * SR)]), 440, delta=5)
        self.assertAlmostEqual(pico_en(audio, 0.4, 0.9), self.pico_tono / 2, delta=0.01)
        self.assertLess(pico_en(audio, 0.0, 0.03), 0.01)           # fundido de entrada
        self.assertLess(pico_en(audio, 1.22, 1.58), 0.01)          # silencio (2,2 a 2,6 del original)
        self.assertAlmostEqual(frecuencia_dominante(audio[0, int(1.0 * SR):int(1.2 * SR)]), 880, delta=10)
        self.assertLess(pico_en(audio, 1.97, 2.0), 0.01)           # fundido de salida

    # ------------------------------------------------------------ forma de onda
    def test_forma_de_onda(self):
        parciales = []
        forma = A.forma_de_onda(self.onda, 30, progreso=parciales.append, intervalo=0.0)
        self.assertEqual(forma.columnas, 30)
        self.assertTrue(forma.completa)
        self.assertAlmostEqual(forma.duracion, 3.0, delta=0.05)
        picos = forma.picos()
        np.testing.assert_allclose(picos[1:9], 0.5, atol=0.02)
        self.assertLess(float(picos[11:19].max()), 0.01)
        np.testing.assert_allclose(picos[21:29], 0.25, atol=0.02)
        self.assertTrue(np.all(forma.minimos <= 0) and np.all(forma.maximos >= 0))
        self.assertAlmostEqual(float(forma.minimos[5]), -0.5, delta=0.02)
        self.assertEqual(forma.columna_en(1.5), 15)
        # Achicarla al ancho en píxeles, sin volver a leer: mínimos y máximos de las columnas que cubre.
        chica = forma.reducida(3)
        np.testing.assert_allclose(chica.picos(), [picos[:10].max(), picos[10:20].max(), picos[20:].max()])
        self.assertEqual(chica.listas, 3)
        self.assertEqual(forma.reducida(60).columnas, 60)
        self.assertIs(forma.reducida(30), forma)
        # Entregas parciales: crecen y la última es la completa.
        self.assertGreater(len(parciales), 2)
        listas = [p.listas for p in parciales]
        self.assertEqual(listas, sorted(listas))
        self.assertLess(listas[0], 30)
        self.assertTrue(parciales[-1].completa)
        # Caché: la segunda vez es inmediata.
        t0 = time.perf_counter()
        self.assertIs(A.forma_de_onda(self.onda, 30), forma)
        self.assertLess(time.perf_counter() - t0, 0.05)
        # Video sin audio: None. MKV (marcas al milisegundo): igual.
        self.assertIsNone(A.forma_de_onda(self.mudo, 100))
        escalones = A.forma_de_onda(self.pcm_mkv, 12)
        np.testing.assert_allclose(escalones.picos(), 0.3, atol=0.01)

    def test_forma_de_onda_se_cancela(self):
        largo = generar(self.salida("onda_larga.mp4"), tono(6.0), fps=5)
        vistas = []
        with self.assertRaises(Cancelado):
            A.forma_de_onda(largo, 500, progreso=vistas.append, cancelado=lambda: len(vistas) >= 1, intervalo=0.0)
        self.assertEqual(len(vistas), 1)
        self.assertIsNotNone(A.forma_de_onda(largo, 500))  # lo cancelado no quedó en la caché a medias

    def test_forma_de_onda_rapida(self):
        largo = generar(self.salida("minuto.mp4"), tono(60.0), fps=2)
        t0 = time.perf_counter()
        forma = A.forma_de_onda(largo, 1500)
        segundos = time.perf_counter() - t0
        self.assertEqual(forma.columnas, 1500)
        np.testing.assert_allclose(forma.picos()[5:-5], 0.3, atol=0.01)
        self.assertLess(segundos, 2.0, f"forma de onda de 1 min: {segundos:.2f} s")

    # ------------------------------------------------------------ vista previa
    def test_lector_pcm_bloques_continuos_y_salteando_lo_borrado(self):
        tramos = [(0.0, 1.0), (2.0, 3.0)]
        referencia = self.wav("lector_ref.wav", self.escalera, tramos)
        with A.LectorPCM(self.escalera, tramos, formato="f32") as lector:
            self.assertEqual(lector.bytes_por_muestra, 8)
            self.assertAlmostEqual(lector.duracion_resultado, 2.0, delta=1e-3)
            partes, tamanos = [], [1000, 4801, 333, 48000, 7]
            while not lector.terminado:
                crudo = lector.leer(tamanos[len(partes) % len(tamanos)])
                self.assertEqual(len(crudo) % lector.bytes_por_muestra, 0)
                partes.append(np.frombuffer(crudo, "<f4").reshape(-1, 2))
            self.assertEqual(lector.leer(100), b"")
        todo = np.concatenate(partes).T
        self.assertEqual(todo.shape, referencia.shape)
        np.testing.assert_allclose(todo, referencia, atol=1.0 / 32768)
        # Salteó el segundo 1 (660 Hz): queda 440 y enseguida 880.
        self.assertAlmostEqual(frecuencia_dominante(todo[0, int(0.2 * SR):int(0.8 * SR)]), 440, delta=5)
        self.assertAlmostEqual(frecuencia_dominante(todo[0, int(1.2 * SR):int(1.8 * SR)]), 880, delta=5)

    def test_lector_pcm_ir_a_y_posiciones(self):
        tramos = [(0.0, 1.0), (2.0, 3.0)]
        with A.LectorPCM(self.escalera, tramos, formato="f32") as lector:
            completo = lector.leer_array(3 * SR)
            lector.ir_a(1.5)  # cae en lo borrado: va al tramo siguiente
            self.assertAlmostEqual(lector.posicion, 2.0, places=6)
            self.assertAlmostEqual(lector.posicion_resultado, 1.0, places=6)
            lector.ir_a(2.5)
            self.assertAlmostEqual(lector.posicion_resultado, 1.5, places=6)
            despues = lector.leer_array(SR // 4)
            np.testing.assert_allclose(despues, completo[int(1.5 * SR):int(1.75 * SR)], atol=1e-5)
            self.assertAlmostEqual(lector.posicion, 2.75, places=6)
            lector.ir_a(0.25)  # para atrás
            np.testing.assert_allclose(lector.leer_array(SR // 4), completo[int(0.25 * SR):int(0.5 * SR)],
                                       atol=1e-5)
            lector.ir_a_resultado(1.9)
            self.assertAlmostEqual(lector.posicion, 2.9, places=6)
            # Conversión entre el tiempo del resultado y el original (para seguir lo que ya sonó).
            self.assertAlmostEqual(lector.original_de_resultado(0.5), 0.5, places=6)
            self.assertAlmostEqual(lector.original_de_resultado(1.25), 2.25, places=6)
            self.assertAlmostEqual(lector.resultado_de_original(2.25), 1.25, places=6)
            self.assertAlmostEqual(lector.resultado_de_original(1.4), 1.0, places=6)  # borrado: el tramo siguiente
            lector.ir_a(99.0)
            self.assertTrue(lector.terminado)
            # Cambiar el volumen mientras suena, sin moverse.
            lector.ir_a(0.5)
            lector.cambiar_ajustes(AjustesAudio(volumen=0.5))
            np.testing.assert_allclose(lector.leer_array(1000), completo[SR // 2:SR // 2 + 1000] * 0.5, atol=1e-6)
        # MKV (marcas al milisegundo): ir a un punto da el mismo audio, corrido como mucho medio milisegundo.
        with A.LectorPCM(self.pcm_mkv, formato="f32") as lector:
            completo = lector.leer_array(3 * SR)[:, 0]
            lector.ir_a(2.3)
            trozo = lector.leer_array(4800)[:, 0]
        i = int(2.3 * SR)
        corrimientos = range(-30, 31)
        errores = [float(np.abs(completo[i + c:i + c + 4800] - trozo).max()) for c in corrimientos]
        self.assertLess(min(errores), 1e-4)

    def test_lector_pcm_s16_y_formato(self):
        with A.LectorPCM(self.tono, formato="s16", frecuencia=44100, canales=1) as lector:
            self.assertEqual(lector.bytes_por_muestra, 2)
            crudo = lector.leer(4410)
            self.assertEqual(len(crudo), 4410 * 2)
            muestras = np.frombuffer(crudo, "<i2").astype(np.float64) / 32768
            # A mono, FFmpeg suma los dos canales a -3 dB cada uno: un tono igual en ambos sube √2.
            self.assertAlmostEqual(float(np.abs(muestras[441:]).max()), self.pico_tono * 2 ** 0.5, delta=0.01)
            self.assertAlmostEqual(frecuencia_dominante(muestras, 44100), 440, delta=12)
        with self.assertRaises(ValueError):
            A.LectorPCM(self.tono, formato="u8")

    def test_lector_pcm_sin_audio(self):
        with A.LectorPCM(self.mudo, [(0.0, 0.5)]) as lector:
            self.assertFalse(lector.tiene_audio)
            crudo = lector.leer(10 * SR)
            self.assertEqual(len(crudo), round(0.5 * SR) * lector.bytes_por_muestra)
            self.assertFalse(any(crudo))
            self.assertTrue(lector.terminado)

    # ------------------------------------------------------------ exportar solo el audio
    def test_exportar_cada_formato(self):
        disponibles = [f.nombre for f in A.formatos_audio_disponibles()]
        self.assertEqual(disponibles[:2], ["m4a", "wav"])
        tiene_lame = True
        try:
            av.Codec("libmp3lame", "w")
        except Exception:
            tiene_lame = False
        self.assertEqual("mp3" in disponibles, tiene_lame)
        tramos = [(0.0, 1.0), (2.0, 3.0)]
        for formato in A.formatos_audio_disponibles():
            with self.subTest(formato=formato.nombre):
                destino = self.salida(f"solo_audio{formato.extension}")
                avances = []
                r = A.exportar_audio(self.escalera, destino, tramos, progreso=lambda h, n, s: avances.append((h, n)))
                self.assertEqual(r.ruta, destino)
                self.assertEqual(r.formato, formato.nombre)
                self.assertEqual((r.frecuencia, r.canales), (SR, 2))
                self.assertAlmostEqual(r.duracion, 2.0, delta=1e-3)
                self.assertEqual(avances[-1][0], avances[-1][1])
                audio, sr = leer_audio(destino)
                self.assertEqual(sr, SR)
                self.assertEqual(audio.shape[0], 2)
                self.assertAlmostEqual(audio.shape[1] / sr, 2.0, delta=0.05)
                self.assertAlmostEqual(frecuencia_dominante(audio[0, int(0.2 * SR):int(0.8 * SR)]), 440, delta=5)
                self.assertAlmostEqual(frecuencia_dominante(audio[0, int(1.2 * SR):int(1.8 * SR)]), 880, delta=5)
                with av.open(str(destino)) as c:
                    self.assertEqual(len(c.streams.video), 0)
        self.assertEqual([p.name for p in self.dir.glob(".*parcial*")], [])
        self.assertEqual(A.ruta_salida_audio(self.tono, "wav").name, "tono_celular.wav")
        with self.assertRaises(ValueError):
            A.exportar_audio(self.tono, self.salida("x.ogg"))
        with self.assertRaises(ValueError):
            A.exportar_audio(self.tono, self.tono, formato="m4a")  # nunca sobre el original
        with self.assertRaises(ValueError):
            A.exportar_audio(self.mudo, self.salida("mudo.wav"))  # sin sonido
        with self.assertRaises(ValueError):
            A.exportar_audio(self.tono, self.salida("vacio.wav"), [])

    def test_cancelar_no_deja_archivos(self):
        carpeta = self.salida("cancelado")
        carpeta.mkdir()
        avances = []
        with self.assertRaises(Cancelado):
            A.exportar_audio(self.tono4, carpeta / "a.m4a", progreso=lambda h, n, s: avances.append(h),
                             cancelado=lambda: len(avances) >= 2)
        self.assertEqual(list(carpeta.iterdir()), [])
        # Cancelado en la pasada que mide el pico (normalizar), antes de escribir nada.
        with self.assertRaises(Cancelado):
            A.exportar_audio(self.tono4, carpeta / "b.wav", ajustes=AjustesAudio(normalizar=True, volumen=0.7),
                             cancelado=lambda: True)
        with self.assertRaises(Cancelado):
            V.exportar_video(self.tono4, carpeta / "c.mp4", (), audio=AjustesAudio(normalizar=True, volumen=0.9),
                             cancelado=lambda: True)
        self.assertEqual(list(carpeta.iterdir()), [])
        # Y exportando video, a mitad de camino.
        hechos = []
        with self.assertRaises(Cancelado):
            V.exportar_video(self.tono4, carpeta / "d.mp4", (), audio=AjustesAudio(volumen=0.5),
                             progreso=lambda h, n, s: hechos.append(h), cancelado=lambda: len(hechos) >= 10)
        self.assertEqual(list(carpeta.iterdir()), [])


# ---------------------------------------------------------------------------
# Archivos de solo audio (el modo Audio): MP3, M4A, OGG Opus, WAV y FLAC
# ---------------------------------------------------------------------------

def generar_audio(ruta: Path, senal: np.ndarray, codec: str, contenedor: str | None = None) -> Path:
    """Un archivo de solo audio (sin pista de video) con ``senal`` (canales × muestras, a 48 kHz)."""
    with av.open(str(ruta), "w", format=contenedor) as c:
        a = c.add_stream(codec, rate=SR)
        a.layout = "stereo" if senal.shape[0] == 2 else "mono"
        formato = {"libopus": "flt", "pcm_s16le": "s16", "flac": "s16"}.get(codec, "fltp")
        a.codec_context.format = formato
        for k in range(0, senal.shape[1], 1152):
            datos = senal[:, k:k + 1152]
            if formato == "s16":
                entero = np.clip(np.round(datos * 32768), -32768, 32767).astype(np.int16)
                cuadro = av.AudioFrame.from_ndarray(np.ascontiguousarray(entero.T).reshape(1, -1), format="s16",
                                                    layout=a.layout.name)
            elif formato == "flt":
                cuadro = av.AudioFrame.from_ndarray(np.ascontiguousarray(datos.T).reshape(1, -1), format="flt",
                                                    layout=a.layout.name)
            else:
                cuadro = av.AudioFrame.from_ndarray(np.ascontiguousarray(datos), format="fltp", layout=a.layout.name)
            cuadro.sample_rate = SR
            cuadro.pts = k
            for p in a.encode(cuadro):
                c.mux(p)
        for p in a.encode():
            c.mux(p)
    return ruta


@unittest.skipIf(av is None, "Falta PyAV (pip install av==19.0.1)")
class PruebasSoloAudio(unittest.TestCase):
    """``info_medio``, ``LectorPCM``, ``forma_de_onda`` y ``exportar_audio`` con archivos sin video."""

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="naturalshot_solo_audio_"))
        cls.senal = escalera(3)
        cls.archivos = {
            "wav": generar_audio(cls.dir / "a.wav", cls.senal, "pcm_s16le", "wav"),
            "flac": generar_audio(cls.dir / "a.flac", cls.senal, "flac", "flac"),
            "m4a": generar_audio(cls.dir / "a.m4a", cls.senal, "aac", "ipod"),
            "ogg": generar_audio(cls.dir / "a.ogg", cls.senal[:1], "libopus", "ogg"),
            # AAC crudo (ADTS): la pista no dice su duración (se suman los paquetes).
            "aac": generar_audio(cls.dir / "a.aac", cls.senal, "aac", "adts"),
        }
        try:
            av.Codec("libmp3lame", "w")
            cls.archivos["mp3"] = generar_audio(cls.dir / "a.mp3", cls.senal, "libmp3lame", "mp3")
        except Exception:  # pragma: no cover - depende de la instalación
            pass

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_info_lector_y_forma_de_onda(self):
        for nombre, ruta in self.archivos.items():
            with self.subTest(formato=nombre):
                info = A.info_medio(ruta)
                self.assertTrue(info.tiene_audio)
                self.assertAlmostEqual(info.duracion, 3.0, delta=0.05)
                self.assertEqual(info.canales_audio, 1 if nombre == "ogg" else 2)
                with A.LectorPCM(ruta, formato="f32") as lector:
                    self.assertAlmostEqual(lector.duracion_resultado, info.duracion, delta=1e-3)
                    todo = lector.leer_array(10 * SR).T
                self.assertTrue(lector.terminado)
                # Alineado: cada segundo tiene su tono (en el MP3, FFmpeg ya sacó el retardo del codificador).
                for segundo, f in enumerate((440, 660, 880)):
                    trozo = todo[0, int((segundo + 0.2) * SR):int((segundo + 0.8) * SR)]
                    self.assertAlmostEqual(frecuencia_dominante(trozo), f, delta=5)
                if nombre in ("wav", "flac"):  # sin pérdida: idéntico al original
                    np.testing.assert_allclose(todo[:, :self.senal.shape[1]], self.senal, atol=1.0 / 32768)
                if nombre == "mp3":  # el principio no queda corrido: el seno arranca en la muestra 0
                    corr = [float(np.dot(todo[0, 4800:9600], self.senal[0, 4800 + c:9600 + c])) for c in range(-40, 41)]
                    self.assertLessEqual(abs(int(np.argmax(corr)) - 40), 2)
                forma = A.forma_de_onda(ruta, 300)
                self.assertIsNotNone(forma)
                self.assertTrue(forma.completa)
                np.testing.assert_allclose(forma.picos()[10:-10], 0.3, atol=0.03)

    def test_exportar_desde_un_audio(self):
        destino = self.dir / "salida.wav"
        r = A.exportar_audio(self.archivos["m4a"], destino, [(0.0, 1.0), (2.0, 3.0)])
        self.assertAlmostEqual(r.duracion, 2.0, delta=1e-3)
        audio, sr = leer_audio(destino)
        self.assertAlmostEqual(frecuencia_dominante(audio[0, int(1.2 * SR):int(1.8 * SR)]), 880, delta=5)

    def test_sin_audio_ni_video(self):
        # Un MP4 sin audio sigue siendo un video: info_medio da lo mismo que info_video.
        mudo = generar(self.dir / "mudo.mp4", None, segundos=1.0)
        self.assertEqual(A.info_medio(mudo), V.info_video(mudo))
        self.assertFalse(A.info_medio(mudo).tiene_audio)
        basura = self.dir / "basura.mp3"
        basura.write_bytes(b"esto no es un audio" * 100)
        with self.assertRaises(Exception):
            A.info_medio(basura)


if __name__ == "__main__":
    unittest.main()
