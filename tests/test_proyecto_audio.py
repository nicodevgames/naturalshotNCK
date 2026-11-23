"""Pruebas del proyecto de audio (``motor/proyecto_audio.py``): proyecto, mezcla y exportación.

Los audios se generan acá mismo con PyAV, en una carpeta temporal: una "voz"
sintética (armónicos en sílabas, con alguna "s"), una voz callada (para ver solo
el ambiente) y un sonido propio para "Mis sonidos". Nada de archivos del usuario.

Usan un APPDATA y un .ini temporales: "Mis sonidos" y las escenas propias van ahí,
no en los del usuario.

Para comparar muestra a muestra se usa ``compresion=False`` (el códec, después de
un salto, suena igual pero no da la misma forma de onda) y se exporta a WAV.
"""

from __future__ import annotations

import gc
import json
import math
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import av
except ImportError:  # pragma: no cover
    av = None

from celular_natural.motor import Cancelado  # noqa: E402
from celular_natural.motor.audio import AjustesAudio  # noqa: E402
from celular_natural.motor.voz_natural import AjustesVoz  # noqa: E402
from celular_natural.motor import proyecto_audio as PA  # noqa: E402
from celular_natural.motor.proyecto_audio import (  # noqa: E402
    ESCENAS, FORMATOS_PROYECTO, Escena, FondoProyecto, MezcladorAudio, ProyectoAudio, SonidoSuelto,
)

SR = 48000
OBJETIVO = 10 ** (-1 / 20)   # -1 dBFS
_ENTORNO: dict = {}
_CARPETA = None


def setUpModule():
    global _CARPETA
    _CARPETA = Path(tempfile.mkdtemp(prefix="naturalshot_proyecto_audio_"))
    for clave in ("APPDATA", "NATURALSHOT_CONFIG"):
        _ENTORNO[clave] = os.environ.get(clave)
    os.environ["APPDATA"] = str(_CARPETA / "appdata")
    os.environ["NATURALSHOT_CONFIG"] = str(_CARPETA / "preferencias.ini")


def tearDownModule():
    for clave, valor in _ENTORNO.items():
        if valor is None:
            os.environ.pop(clave, None)
        else:
            os.environ[clave] = valor
    shutil.rmtree(_CARPETA, ignore_errors=True)


# ---------------------------------------------------------------------------
# Medios de prueba
# ---------------------------------------------------------------------------

def voz_sintetica(segundos: float, nivel: float = 0.3, semilla: int = 0) -> np.ndarray:
    """(n, 2): armónicos de una fundamental que va y viene, en "sílabas" de 4 Hz, con una "s" por segundo."""
    n = int(round(SR * segundos))
    t = np.arange(n) / SR
    f0 = 150 + 40 * np.sin(2 * np.pi * 0.7 * t)
    fase = 2 * np.pi * np.cumsum(f0) / SR
    m = sum(np.sin(k * fase) / k for k in range(1, 25))
    silabas = np.clip(np.sin(2 * np.pi * 4 * t), 0, None) ** 0.5
    rng = np.random.default_rng(semilla)
    ese = np.fft.irfft(np.fft.rfft(rng.standard_normal(n)) * (np.fft.rfftfreq(n, 1 / SR) > 4500), n)
    ese *= (t % 1.0) > 0.85
    m = m * silabas + 2.0 * ese
    m = (nivel * m / np.abs(m).max()).astype(np.float32)
    return np.stack([m, m], axis=1)


def sonido_propio(segundos: float, semilla: int = 5) -> np.ndarray:
    """(n, 2): ruido de banda media que sube y baja (como unos pájaros lejos), distinto en cada canal."""
    n = int(round(SR * segundos))
    rng = np.random.default_rng(semilla)
    x = rng.standard_normal((n, 2))
    f = np.fft.rfftfreq(n, 1 / SR)
    x = np.fft.irfft(np.fft.rfft(x, axis=0) * ((f > 1500) & (f < 5000))[:, None], n, axis=0)
    t = np.arange(n) / SR
    x *= (0.6 + 0.4 * np.sin(2 * np.pi * 0.9 * t))[:, None]
    return (0.2 * x / np.abs(x).max()).astype(np.float32)


def escribir_audio(ruta: Path, senal: np.ndarray, codec: str = "pcm_s16le", contenedor: str | None = None) -> Path:
    """Archivo de solo audio con ``senal`` ((n, canales) a 48 kHz)."""
    with av.open(str(ruta), "w", format=contenedor) as c:
        a = c.add_stream(codec, rate=SR)
        a.layout = "stereo" if senal.shape[1] == 2 else "mono"
        formato = {"libopus": "flt", "pcm_s16le": "s16"}.get(codec, "fltp")
        a.codec_context.format = formato
        for k in range(0, senal.shape[0], 1152):
            datos = senal[k:k + 1152]
            if formato == "s16":
                entero = np.clip(np.round(datos * 32768), -32768, 32767).astype(np.int16)
                cuadro = av.AudioFrame.from_ndarray(np.ascontiguousarray(entero).reshape(1, -1), format="s16",
                                                    layout=a.layout.name)
            elif formato == "flt":
                cuadro = av.AudioFrame.from_ndarray(np.ascontiguousarray(datos).reshape(1, -1), format="flt",
                                                    layout=a.layout.name)
            else:
                cuadro = av.AudioFrame.from_ndarray(np.ascontiguousarray(datos.T), format="fltp",
                                                    layout=a.layout.name)
            cuadro.sample_rate = SR
            cuadro.pts = k
            for p in a.encode(cuadro):
                c.mux(p)
        for p in a.encode():
            c.mux(p)
    return ruta


def video_mudo(ruta: Path, segundos: float = 1.0) -> Path:
    with av.open(str(ruta), "w") as c:
        v = c.add_stream("libx264", rate=24)
        v.width, v.height, v.pix_fmt = 64, 48, "yuv420p"
        v.options = {"preset": "ultrafast"}
        for i in range(int(segundos * 24)):
            cuadro = av.VideoFrame.from_ndarray(np.full((48, 64, 3), i * 9 % 256, np.uint8), format="rgb24")
            cuadro.pts = i
            for p in v.encode(cuadro.reformat(format="yuv420p")):
                c.mux(p)
        for p in v.encode():
            c.mux(p)
    return ruta


def leer_todo(ruta: Path) -> tuple[np.ndarray, int, int, str]:
    """(muestras float32 (n, canales), frecuencia, canales, códec) de un archivo, con PyAV directo."""
    with av.open(str(ruta)) as c:
        sa = c.streams.audio[0]
        canales = sa.codec_context.channels
        codec = sa.codec_context.name
        bloques = []
        for f in c.decode(sa):
            d = f.to_ndarray()
            if not f.format.is_planar:
                d = d.reshape(-1, canales).T
            bloques.append(d.astype(np.float32) / (32768.0 if d.dtype == np.int16 else 1.0))
        return np.concatenate(bloques, axis=1).T, sa.codec_context.sample_rate, canales, codec


def leer_wav16(ruta: Path) -> np.ndarray:
    with av.open(str(ruta)) as c:
        sa = c.streams.audio[0]
        return np.concatenate([f.to_ndarray().reshape(-1, sa.codec_context.channels) for f in c.decode(sa)])


def leer_mezclador(m: MezcladorAudio, tamanos=(4800,)) -> np.ndarray:
    partes, i = [], 0
    while not m.terminado:
        partes.append(m.leer_array(tamanos[i % len(tamanos)]))
        i += 1
    return np.concatenate(partes) if partes else np.zeros((0, 2), np.float32)


def juntar(m: MezcladorAudio, n: int, limite: float = 20.0) -> np.ndarray:
    """Lee de un mezclador adelantado hasta juntar ``n`` muestras (o hasta el final)."""
    partes, juntas, hasta = [], 0, time.perf_counter() + limite
    while juntas < n and not m.terminado and time.perf_counter() < hasta:
        x = m.leer_array(min(4800, n - juntas))
        if len(x):
            partes.append(x)
            juntas += len(x)
        else:
            time.sleep(0.002)
    return np.concatenate(partes) if partes else np.zeros((0, 2), np.float32)


def esperar_bufer(m: MezcladorAudio, limite: float = 10.0) -> None:
    """Hasta que el búfer esté lleno (o tenga todo lo que falta)."""
    hasta = time.perf_counter() + limite
    while time.perf_counter() < hasta:
        if m.adelantado >= min(PA.ADELANTO_VISTA_PREVIA, m.duracion_resultado - m.posicion_resultado) - 1e-3:
            return
        time.sleep(0.005)


def a_int16(x: np.ndarray) -> np.ndarray:
    return np.clip(np.round(x * 32768.0), -32768, 32767).astype(np.int16)


def proyecto(ruta, tramos=None, **cambios) -> ProyectoAudio:
    p = PA.abrir_proyecto(ruta)
    if tramos is not None:
        p = p.con(tramos=tuple(tramos))
    return p.con(**cambios) if cambios else p


def rms(x) -> float:
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))


# ---------------------------------------------------------------------------
# Datos (sin PyAV)
# ---------------------------------------------------------------------------

class PruebasDatos(unittest.TestCase):
    def test_curva_de_volumen(self):
        self.assertEqual(PA.ganancia_volumen(0.5), 1.0)
        self.assertAlmostEqual(20 * math.log10(PA.ganancia_volumen(1.0)), 12.0, delta=0.1)
        self.assertAlmostEqual(20 * math.log10(PA.ganancia_volumen(0.25)), -12.0, delta=0.1)
        self.assertEqual(PA.ganancia_volumen(0.0), 0.0)
        self.assertEqual(PA.ganancia_volumen(float("nan")), 1.0)
        valores = [PA.ganancia_volumen(v) for v in np.linspace(0, 1, 101)]
        self.assertTrue(all(b > a for a, b in zip(valores, valores[1:])))

    def test_validacion(self):
        f = FondoProyecto("generado", "lluvia", volumen=7, intensidad=float("nan"), semilla="3")
        self.assertEqual((f.volumen, f.intensidad, f.semilla), (1.0, 0.5, 3))
        with self.assertRaises(ValueError):
            FondoProyecto("internet", "lluvia")
        with self.assertRaises(ValueError):
            FondoProyecto("generado", "")
        s = SonidoSuelto("generado", "bocina", ancla=-3)
        self.assertEqual((s.ancla, s.volumen), (0.0, 0.7))
        tres = tuple(FondoProyecto("generado", c) for c in ("lluvia", "viento", "olas"))
        p = ProyectoAudio("voz.wav", [(2, 3), (0, 1), (0.5, 1.5)], AjustesAudio(), AjustesVoz(), list(tres), [s])
        self.assertEqual(p.tramos, ((0.0, 1.5), (2.0, 3.0)))
        self.assertEqual(p.fondos, tres)
        self.assertIsInstance(p.sonidos, tuple)
        with self.assertRaises(ValueError):
            p.con(fondos=tres + (FondoProyecto("generado", "calle"),))   # 4 capas
        with self.assertRaises(TypeError):
            p.con(voz=AjustesAudio())
        with self.assertRaises(Exception):
            p.ruta = "otra.wav"   # inmutable

    def test_pickle_y_rearmado_de_la_sesion(self):
        p = ProyectoAudio("C:/voz.wav", ((0.0, 1.0), (2.0, 5.0)),
                          AjustesAudio(volumen=0.8, normalizar=True, silencios=((3.0, 3.5),)),
                          AjustesVoz(destino="whatsapp", lugar="calle", anti_ia=0.4, semilla=2),
                          (FondoProyecto("generado", "calle", 0.6, 0.3, 1), FondoProyecto("archivo", "pájaros.wav")),
                          (SonidoSuelto("generado", "bocina", 2.5, 0.4, 7),), video_origen="C:/video.mp4")
        for objeto in (p, ESCENAS["nota_calle"], p.fondos[0], p.sonidos[0]):
            copia = pickle.loads(pickle.dumps(objeto, protocol=pickle.HIGHEST_PROTOCOL))
            self.assertEqual(copia, objeto)
            self.assertEqual(hash(copia), hash(objeto))
            self.assertEqual(type(objeto)(**vars(copia)), objeto)   # como sesion._reconstruir

    def test_las_diez_escenas(self):
        from celular_natural.motor import ambientes
        self.assertEqual(len(ESCENAS), 10)
        nombres = {e.nombre for e in ESCENAS.values()}
        for nombre in ("Nota de voz en la oficina", "Nota de voz caminando por la calle",
                       "Nota de voz arriba del colectivo", "Nota de voz bajo la lluvia", "Video en la playa",
                       "Video en la ciudad", "Video en casa", "Manos libres en el auto", "Auriculares en la calle",
                       "Solo bajarle lo de IA"):
            self.assertIn(nombre, nombres)
        for clave, e in ESCENAS.items():
            with self.subTest(escena=clave):
                self.assertEqual(e.clave, clave)
                self.assertFalse(e.propia)
                self.assertTrue(e.descripcion)
                self.assertLessEqual(len(e.fondos), 3)
                for f in e.fondos:
                    self.assertEqual(f.origen, "generado")
                    self.assertIn(f.clave, ambientes.FONDOS)
                for s in e.sonidos:
                    self.assertIn(s[0], ambientes.SONIDOS)
                    self.assertTrue(0 <= s[1] <= 1 and 0 <= s[2] <= 1)
        calle = ESCENAS["nota_calle"]
        self.assertEqual((calle.voz.destino, calle.voz.lugar), ("whatsapp", "calle"))
        self.assertEqual([f.clave for f in calle.fondos], ["calle"])
        self.assertEqual(calle.sonidos[0][:2], ("colectivo_pasa", 0.4))
        self.assertEqual([f.clave for f in ESCENAS["video_playa"].fondos], ["olas", "viento"])
        self.assertEqual([f.clave for f in ESCENAS["auriculares_calle"].fondos], ["calle", "viento_mic"])
        solo = ESCENAS["solo_anti_ia"]
        self.assertEqual((solo.voz.destino, solo.voz.lugar, solo.fondos, solo.sonidos), ("ninguno", "ninguno", (), ()))
        self.assertGreater(solo.voz.anti_ia, 0)
        self.assertEqual(FORMATOS_PROYECTO, ("whatsapp", "m4a", "mp3", "wav"))

    def test_importar_no_carga_pyav(self):
        codigo = ("import sys; from celular_natural.motor.proyecto_audio import ProyectoAudio, ESCENAS; "
                  "from celular_natural import sesion; print('av' in sys.modules)")
        salida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                                cwd=str(Path(__file__).resolve().parent.parent), timeout=60)
        self.assertEqual(salida.stdout.strip(), "False", salida.stderr)


# ---------------------------------------------------------------------------
# Con audios generados
# ---------------------------------------------------------------------------

@unittest.skipIf(av is None, "Falta PyAV (pip install av==19.0.1)")
class _ConMedios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="medios_", dir=_CARPETA))
        cls.senal = voz_sintetica(8.0)
        cls.voz = escribir_audio(cls.dir / "voz.wav", cls.senal)
        cls.callada = escribir_audio(cls.dir / "callada.wav", np.zeros((8 * SR, 2), np.float32))
        cls.pajaros = escribir_audio(cls.dir / "pajaros.wav", sonido_propio(5.0))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        shutil.rmtree(PA.carpeta_sonidos(), ignore_errors=True)
        for extra in Path(os.environ["APPDATA"]).glob("NaturalShot PRO/escenas*"):
            extra.unlink()

    def salida(self, nombre: str) -> Path:
        return self.dir / nombre


class PruebasAbrir(_ConMedios):
    def test_abrir_cada_formato(self):
        formatos = {"wav": ("pcm_s16le", "wav", self.senal), "m4a": ("aac", "ipod", self.senal),
                    "ogg": ("libopus", "ogg", self.senal[:, :1])}
        try:
            av.Codec("libmp3lame", "w")
            formatos["mp3"] = ("libmp3lame", "mp3", self.senal)
        except Exception:  # pragma: no cover
            pass
        for extension, (codec, contenedor, senal) in formatos.items():
            with self.subTest(formato=extension):
                ruta = escribir_audio(self.salida(f"abrir.{extension}"), senal, codec, contenedor)
                p = PA.abrir_proyecto(ruta)
                self.assertEqual(p.ruta, str(ruta))
                self.assertEqual(len(p.tramos), 1)
                self.assertEqual(p.tramos[0][0], 0.0)
                self.assertAlmostEqual(PA.duracion_resultado(p), 8.0, delta=0.05)
                self.assertEqual((p.sonido, p.voz, p.fondos, p.sonidos), (AjustesAudio(), AjustesVoz(), (), ()))
                with MezcladorAudio(p, formato="f32") as m:
                    self.assertAlmostEqual(m.duracion_resultado, PA.duracion_resultado(p), delta=1e-3)
                    self.assertGreater(rms(m.leer_array(SR)), 0.01)

    def test_errores_al_abrir(self):
        with self.assertRaisesRegex(ValueError, "sonido"):
            PA.abrir_proyecto(video_mudo(self.salida("mudo.mp4")))
        basura = self.salida("basura.mp3")
        basura.write_bytes(b"esto no es un audio" * 200)
        with self.assertRaises(ValueError):
            PA.abrir_proyecto(basura)
        with self.assertRaises(FileNotFoundError):
            PA.abrir_proyecto(self.salida("no_existe.wav"))


class PruebasMezcla(_ConMedios):
    def completo(self, **voz) -> ProyectoAudio:
        """Un proyecto con todo: cortes, silencio, fundidos, volumen, cadena, dos fondos y un sonido."""
        ajustes = dict(destino="whatsapp", lugar="calle", anti_ia=0.5, compresion=False, semilla=3)
        ajustes.update(voz)
        return proyecto(self.voz, [(0.0, 3.0), (4.0, 8.0)],
                        sonido=AjustesAudio(volumen=0.8, fundido_entrada=0.5, fundido_salida=0.7,
                                            silencios=((5.0, 5.5),)),
                        voz=AjustesVoz(**ajustes),
                        fondos=(FondoProyecto("generado", "calle", 0.5, 0.6, 1),
                                FondoProyecto("generado", "viento", 0.3)),
                        sonidos=(SonidoSuelto("generado", "bocina", 2.0, 0.6),))

    def test_mezclador_igual_a_exportar_wav(self):
        p = self.completo()
        r = PA.exportar_proyecto(p, self.salida("mezcla.wav"))
        archivo = leer_wav16(r.ruta)
        with MezcladorAudio(p, formato="f32") as m:
            self.assertAlmostEqual(m.duracion_resultado, 7.0, delta=1e-3)
            vista = leer_mezclador(m, (1000, 4801, 333, 48000, 7))
        self.assertEqual(vista.shape, archivo.shape)
        np.testing.assert_array_equal(a_int16(vista), archivo)
        with MezcladorAudio(p) as m:   # s16, como lo pide QAudioSink
            self.assertEqual(m.bytes_por_muestra, 4)
            crudo = b"".join(iter(lambda: m.leer(9600), b""))
        np.testing.assert_array_equal(np.frombuffer(crudo, "<i2").reshape(-1, 2), archivo)
        self.assertLessEqual(float(np.abs(vista).max()), 1.0)

    def test_saltar_y_seguir(self):
        p = self.completo()
        with MezcladorAudio(p, formato="f32") as m:
            corrido = leer_mezclador(m)
            m.ir_a_resultado(2.0)
            self.assertFalse(m.terminado)
            self.assertAlmostEqual(m.posicion_resultado, 2.0)
            np.testing.assert_allclose(m.leer_array(SR), corrido[2 * SR:3 * SR], atol=2e-3)
            self.assertAlmostEqual(m.posicion_resultado, 3.0)
            m.ir_a_resultado(0.5)   # para atrás
            np.testing.assert_allclose(m.leer_array(SR // 2), corrido[SR // 2:SR], atol=2e-3)
            # En tiempo original: 4,5 s del original es 3,5 s del resultado (se borró de 3 a 4).
            m.ir_a(4.5)
            self.assertAlmostEqual(m.posicion_resultado, 3.5)
            self.assertAlmostEqual(m.posicion, 4.5)
            np.testing.assert_allclose(m.leer_array(SR // 2), corrido[int(3.5 * SR):4 * SR], atol=2e-3)
            self.assertAlmostEqual(m.original_de_resultado(3.25), 4.25)
            self.assertAlmostEqual(m.resultado_de_original(3.5), 3.0)   # borrado: el tramo siguiente
            m.ir_a_resultado(99)
            self.assertTrue(m.terminado)
            self.assertEqual(m.leer(100), b"")
        with MezcladorAudio(p, desde=4.5, formato="f32") as m:   # desde: tiempo original, como LectorPCM
            self.assertAlmostEqual(m.posicion_resultado, 3.5)
            np.testing.assert_allclose(m.leer_array(SR // 4), corrido[int(3.5 * SR):int(3.75 * SR)], atol=2e-3)

    def test_con_codec_saltar_suena_igual(self):
        # Con compresión, después de un salto la forma de onda cambia, pero el nivel es el mismo.
        p = self.completo(compresion=True)
        with MezcladorAudio(p, formato="f32") as m:
            corrido = leer_mezclador(m)
            self.assertEqual(len(corrido), 7 * SR)
            m.ir_a_resultado(2.0)
            parte = m.leer_array(SR)
        self.assertAlmostEqual(20 * math.log10(rms(parte) / rms(corrido[2 * SR:3 * SR])), 0.0, delta=1.0)

    def test_cambiar_proyecto_sin_moverse(self):
        p = self.completo()
        p_sin_fundidos = p.con(sonido=p.sonido.con(fundido_entrada=0.0, fundido_salida=0.0))
        with MezcladorAudio(p_sin_fundidos, formato="f32") as m:
            corrido = leer_mezclador(m)
            m.ir_a_resultado(1.0)
            m.leer_array(SR)
            # Solo el volumen: sigue de corrido, sin volver a armar nada.
            m.cambiar_proyecto(p_sin_fundidos.con(sonido=p_sin_fundidos.sonido.con(volumen=0.4)))
            self.assertAlmostEqual(m.posicion_resultado, 2.0)
            np.testing.assert_allclose(m.leer_array(SR // 2), corrido[2 * SR:int(2.5 * SR)] * 0.5, atol=1e-6)
            # Otro fondo: se queda en el mismo lugar y suena como el proyecto nuevo.
            otro = p_sin_fundidos.con(fondos=(FondoProyecto("generado", "lluvia"),))
            m.cambiar_proyecto(otro)
            self.assertAlmostEqual(m.posicion_resultado, 2.5)
            parte = m.leer_array(SR // 2)
        with MezcladorAudio(otro, formato="f32") as nuevo:
            nuevo.ir_a_resultado(2.5)
            np.testing.assert_allclose(parte, nuevo.leer_array(SR // 2), atol=1e-6)

    def test_anclas_siguen_a_la_voz(self):
        p = proyecto(self.callada, [(0.0, 1.0), (2.0, 8.0)])
        self.assertAlmostEqual(PA.ancla_en_resultado(p, 5.0), 4.0)
        self.assertAlmostEqual(PA.ancla_en_resultado(p, 1.5), 1.0)   # en lo borrado: el tramo siguiente
        self.assertAlmostEqual(PA.ancla_en_resultado(p, 0.5), 0.5)
        self.assertAlmostEqual(PA.duracion_resultado(p), 7.0)
        from celular_natural.motor.ambientes import generar_sonido
        bocina = generar_sonido("bocina", 0)
        for ancla, esperado in ((5.0, 4.0), (1.5, 1.0)):
            with self.subTest(ancla=ancla):
                q = p.con(sonidos=(SonidoSuelto("generado", "bocina", ancla, 0.5),))
                with MezcladorAudio(q, formato="f32") as m:
                    y = leer_mezclador(m)
                primera = int(np.flatnonzero(np.abs(y).max(axis=1) > 0)[0])
                silencio_inicial = int(np.flatnonzero(np.abs(bocina).max(axis=1))[0])
                self.assertLessEqual(abs(primera - esperado * SR), 1 + silencio_inicial)
        # Suena entero: el corte de 1 a 2 s no lo recorta.
        q = p.con(sonidos=(SonidoSuelto("generado", "bocina", 0.5, 0.5),))
        with MezcladorAudio(q, formato="f32") as m:
            y = leer_mezclador(m)
        np.testing.assert_allclose(y[SR // 2:SR // 2 + len(bocina)], bocina, atol=1e-6)
        self.assertEqual(float(np.abs(y[SR // 2 + len(bocina):]).max()), 0.0)
        # Pasa el final del resultado: se apaga en 15 ms, no se corta en seco.
        T = 7 * SR
        ancla = 8.0 - len(bocina) / SR / 2   # la mitad queda afuera
        q = p.con(sonidos=(SonidoSuelto("generado", "bocina", ancla, 0.5),))
        with MezcladorAudio(q, formato="f32") as m:
            y = leer_mezclador(m)
        inicio = T - len(bocina) // 2
        self.assertEqual(len(y), T)
        F = round(PA.FUNDIDO_SUELTO * SR)
        np.testing.assert_allclose(y[inicio:T - F], bocina[:T - F - inicio], atol=1e-6)
        self.assertLess(float(np.abs(y[-1]).max()), 1e-3 * float(np.abs(bocina).max()))

    def test_fondos_cubren_todo_con_fundidos(self):
        p = proyecto(self.callada, [(0.0, 3.0), (5.0, 8.0)],
                     fondos=(FondoProyecto("generado", "lluvia", 0.5),))
        with MezcladorAudio(p, formato="f32") as m:
            y = leer_mezclador(m)
        self.assertEqual(len(y), 6 * SR)
        medio = rms(y[SR:5 * SR])
        self.assertAlmostEqual(20 * math.log10(medio), -30.0, delta=3.0)
        self.assertLess(float(np.abs(y[0]).max()), 1e-3)
        self.assertLess(float(np.abs(y[-1]).max()), 1e-3)
        self.assertLess(rms(y[:SR // 100]), 0.1 * medio)            # primeros 10 ms
        self.assertGreater(rms(y[int(0.3 * SR):int(0.6 * SR)]), 0.5 * medio)
        # Sin hueco en el corte (el fondo va en el tiempo del resultado).
        ventanas = [rms(y[i:i + SR // 10]) for i in range(int(0.4 * SR), int(5.5 * SR), SR // 10)]
        self.assertGreater(min(ventanas), 0.4 * medio)
        # Volumen: 1 = +12 dB sobre 0,5; 0 = nada.
        for volumen, db in ((1.0, 12.0), (0.25, -12.0)):
            q = p.con(fondos=(FondoProyecto("generado", "lluvia", volumen),))
            with MezcladorAudio(q, formato="f32") as m:
                otro = leer_mezclador(m)
            self.assertAlmostEqual(20 * math.log10(rms(otro[SR:5 * SR]) / medio), db, delta=0.5)
        with MezcladorAudio(p.con(fondos=(FondoProyecto("generado", "lluvia", 0.0),)), formato="f32") as m:
            self.assertEqual(float(np.abs(leer_mezclador(m)).max()), 0.0)

    def test_normalizar(self):
        p = proyecto(self.voz, [(0.0, 3.0), (4.0, 8.0)], sonido=AjustesAudio(normalizar=True),
                     voz=AjustesVoz(destino="video", lugar="oficina", compresion=False),
                     fondos=(FondoProyecto("generado", "oficina", 0.5),))
        t0 = time.perf_counter()
        pico = PA.medir_pico_proyecto(p)
        primera = time.perf_counter() - t0
        t0 = time.perf_counter()
        self.assertEqual(PA.medir_pico_proyecto(p.con(sonido=AjustesAudio(normalizar=True, volumen=0.3))), pico)
        self.assertLess(time.perf_counter() - t0, max(0.05, primera / 10))   # en caché
        r = PA.exportar_proyecto(p, self.salida("normalizado.wav"))
        y = leer_wav16(r.ruta).astype(np.float64) / 32768
        self.assertAlmostEqual(float(np.abs(y).max()), OBJETIVO, delta=2e-3)
        with MezcladorAudio(p, formato="f32", pico=pico) as m:
            np.testing.assert_array_equal(a_int16(leer_mezclador(m)), leer_wav16(r.ruta))
        with self.assertRaises(Cancelado):
            PA.medir_pico_proyecto(p.con(voz=p.voz.con(semilla=9)), cancelado=lambda: True)

    def test_limitador(self):
        fuerte = escribir_audio(self.salida("fuerte.wav"), voz_sintetica(3.0, nivel=0.95))
        p = proyecto(fuerte, sonido=AjustesAudio(volumen=2.0), fondos=(FondoProyecto("generado", "calle", 1.0),))
        with MezcladorAudio(p, formato="f32") as m:
            y = leer_mezclador(m)
        self.assertLessEqual(float(np.abs(y).max()), 1.0)
        self.assertGreater(float(np.abs(y).max()), 0.95)
        # Lo que está por debajo del umbral no se toca.
        p = proyecto(fuerte, sonido=AjustesAudio(volumen=0.5))
        with MezcladorAudio(p, formato="f32") as m:
            np.testing.assert_allclose(leer_mezclador(m)[:len(y)], voz_sintetica(3.0, nivel=0.95) * 0.5,
                                       atol=2.0 / 32768)

    # ------------------------------------------------------------ lectura adelantada (vista previa)
    def test_adelantada_da_lo_mismo_que_la_directa(self):
        p = self.completo(compresion=True)
        with MezcladorAudio(p, formato="f32") as m:
            directo = leer_mezclador(m)
        with MezcladorAudio(p, formato="f32", adelanto=PA.ADELANTO_VISTA_PREVIA) as m:
            todo = juntar(m, len(directo) + 1)
            self.assertTrue(m.terminado)
            self.assertIsNone(m.error)
            self.assertEqual(m.leer(100), b"")
        np.testing.assert_array_equal(todo, directo)   # nada perdido ni agregado (sin rellenar con silencio)

    def test_adelantada_saltar_y_cambiar(self):
        p = self.completo()
        p = p.con(sonido=p.sonido.con(fundido_entrada=0.0, fundido_salida=0.0))
        with MezcladorAudio(p, formato="f32", adelanto=1.0) as m:
            esperar_bufer(m)
            t0 = time.perf_counter()
            m.ir_a_resultado(2.0)
            self.assertLess(time.perf_counter() - t0, 0.02)   # no espera al hilo
            self.assertAlmostEqual(m.posicion_resultado, 2.0)
            parte = juntar(m, SR)
            # Solo el volumen: no se vacía el búfer y se oye enseguida.
            esperar_bufer(m)
            antes = m.adelantado
            m.cambiar_proyecto(p.con(sonido=p.sonido.con(volumen=0.4)))
            self.assertGreaterEqual(m.adelantado, antes - 0.01)
            a_mitad = juntar(m, SR // 2)
            # Otro fondo: se vacía, se rellena y sigue desde el mismo punto.
            otro = p.con(fondos=(FondoProyecto("generado", "lluvia"),))
            m.cambiar_proyecto(otro)
            self.assertEqual(m.adelantado, 0.0)
            self.assertAlmostEqual(m.posicion_resultado, 3.5)
            con_lluvia = juntar(m, SR // 2)
        with MezcladorAudio(p, formato="f32") as d:
            d.ir_a_resultado(2.0)
            np.testing.assert_array_equal(parte, d.leer_array(SR))
            np.testing.assert_allclose(a_mitad, d.leer_array(SR // 2) * 0.5, atol=1e-6)
            viejo = d.leer_array(480)   # lo que iba a sonar si no se cambiaba
        with MezcladorAudio(otro, formato="f32") as d:
            d.ir_a_resultado(3.5)
            nuevo = d.leer_array(SR // 2)
        # Sin clic: los primeros 10 ms se funden de lo viejo a lo nuevo; después, lo nuevo tal cual.
        w = (0.5 - 0.5 * np.cos(np.pi * (np.arange(480) + 0.5) / 480))[:, None]
        np.testing.assert_allclose(con_lluvia[:480], viejo * (1 - w) + nuevo[:480] * w, atol=1e-5)
        np.testing.assert_array_equal(con_lluvia[480:], nuevo[480:])

    def test_adelantada_cambiar_con_el_bufer_vacio(self):
        # Si el cambio llega con el búfer vacío (no hay 10 ms de lo viejo para fundir), lo nuevo
        # arranca desde la última muestra que sonó y la diferencia se va en 10 ms: sin clic.
        p = self.completo()
        p = p.con(sonido=p.sonido.con(fundido_entrada=0.0, fundido_salida=0.0))
        otro = p.con(fondos=(FondoProyecto("generado", "lluvia"),))
        with MezcladorAudio(p, formato="f32", adelanto=1.0) as m:
            esperar_bufer(m)
            with m._cond:   # el hilo no puede llenar mientras tanto: el búfer queda vacío de verdad
                antes = m.leer_array(10 * SR)
                self.assertEqual(m.adelantado, 0.0)
                pos = m.posicion_resultado
                m.cambiar_proyecto(otro)
            despues = juntar(m, SR // 2)
        with MezcladorAudio(otro, formato="f32") as d:
            d.ir_a_resultado(pos)
            nuevo = d.leer_array(SR // 2)
        w = (0.5 - 0.5 * np.cos(np.pi * (np.arange(480) + 0.5) / 480))[:, None]
        esperado = nuevo[:480] + (antes[-1] - nuevo[0]) * (1 - w)
        np.testing.assert_allclose(despues[:480], esperado, atol=1e-5)
        np.testing.assert_array_equal(despues[480:], nuevo[480:])
        self.assertLess(float(np.abs(despues[0] - antes[-1]).max()), 1e-3)   # sigue desde donde estaba

    def test_adelantada_no_traba_la_interfaz(self):
        # Un fondo de calle a intensidad 1 sintetiza pasadas enteras de autos (hasta 200 ms de golpe):
        # con el búfer, leer de a 50 ms nunca tarda más de 20 ms después del arranque.
        p = proyecto(self.voz, voz=AjustesVoz(destino="whatsapp", lugar="calle"),
                     fondos=(FondoProyecto("generado", "calle", 0.5, 1.0, 4),))
        with MezcladorAudio(p, adelanto=PA.ADELANTO_VISTA_PREVIA) as m:
            esperar_bufer(m)
            tiempos = []
            while not m.terminado:
                t0 = time.perf_counter()
                m.leer(2400)
                tiempos.append(time.perf_counter() - t0)
                time.sleep(0.025)   # el doble de rápido que el tiempo real
            self.assertEqual(m.faltaron, 0)
        self.assertLess(max(tiempos), 0.020, f"la lectura más lenta tardó {max(tiempos) * 1000:.1f} ms")

    def test_adelantada_cerrar_no_espera(self):
        copia = self.salida("para_cerrar.wav")
        shutil.copyfile(self.voz, copia)
        p = proyecto(copia, voz=AjustesVoz(destino="video", lugar="oficina"),
                     fondos=(FondoProyecto("generado", "calle", 0.5, 1.0),))
        m = MezcladorAudio(p, adelanto=1.0)
        time.sleep(0.05)   # con el hilo calculando
        t0 = time.perf_counter()
        m.cerrar()
        self.assertLess(time.perf_counter() - t0, 0.05)
        m.cerrar()   # dos veces: nada
        m._hilo.join(5)
        self.assertFalse(m._hilo.is_alive())
        os.remove(copia)   # soltó el archivo (en Windows no se puede borrar uno abierto)
        # cerrar(esperar): vuelve con el archivo ya suelto (para borrar un temporal enseguida).
        shutil.copyfile(self.voz, copia)
        m = MezcladorAudio(p, adelanto=1.0)
        time.sleep(0.05)
        m.cerrar(esperar=5.0)
        self.assertFalse(m._hilo.is_alive())
        os.remove(copia)

    def test_adelantada_sin_cerrar_no_queda_viva(self):
        copia = self.salida("sin_cerrar.wav")
        shutil.copyfile(self.voz, copia)
        m = MezcladorAudio(proyecto(copia, fondos=(FondoProyecto("generado", "lluvia"),)), adelanto=1.0)
        esperar_bufer(m)
        hilo = m._hilo
        del m   # nadie lo cerró: el hilo no lo retiene
        gc.collect()
        hilo.join(5)
        self.assertFalse(hilo.is_alive())
        os.remove(copia)   # y soltó el archivo

    def test_adelantada_un_error_llega_a_quien_lee(self):
        p = proyecto(self.voz, voz=AjustesVoz(destino="video", lugar="oficina"))
        m = MezcladorAudio(p, formato="f32", adelanto=1.0)
        try:
            esperar_bufer(m)
            original = m._motor.leer

            def roto(n):
                raise OSError("disco desconectado (simulado)")

            m._motor.leer = roto
            leidas = 0
            with self.assertRaises(OSError):   # primero da lo que había en el búfer; después, el error
                for _ in range(10000):
                    x = m.leer_array(2400)
                    leidas += len(x)
                    if not len(x):
                        time.sleep(0.002)
            self.assertGreaterEqual(leidas, SR - 1)
            self.assertFalse(m.terminado)   # no es un final normal
            self.assertIsInstance(m.error, OSError)
            with self.assertRaises(OSError):
                m.leer(100)
            # Un salto lo vuelve a intentar.
            m._motor.leer = original
            m.ir_a_resultado(1.0)
            self.assertIsNone(m.error)
            self.assertEqual(len(juntar(m, SR)), SR)
        finally:
            m.cerrar(esperar=5.0)

    def test_muchos_sonidos_no_se_regeneran_en_cada_cambio(self):
        # Con más sonidos generados que la caché de ambientes (8), cambiar el proyecto no los vuelve a sintetizar.
        sueltos = tuple(SonidoSuelto("generado", "auto_pasa", 0.5 * i, 0.3, semilla=i) for i in range(12))
        p = proyecto(self.voz, sonidos=sueltos)
        with MezcladorAudio(p, formato="f32", adelanto=1.0) as m:
            for vuelta in range(2):
                q = p.con(sonidos=sueltos[:5] + (sueltos[5].con(volumen=0.4 + 0.1 * vuelta),) + sueltos[6:])
                t0 = time.perf_counter()
                m.cambiar_proyecto(q)
                tardo = time.perf_counter() - t0
            self.assertLess(tardo, 0.05, f"el segundo cambio tardó {tardo * 1000:.0f} ms")
            m.ir_a_resultado(1.0)
            obtenido = juntar(m, SR)
        with MezcladorAudio(q, formato="f32") as d:
            d.ir_a_resultado(1.0)
            np.testing.assert_array_equal(obtenido, d.leer_array(SR))   # la misma mezcla

    def test_velocidad_con_una_escena_completa(self):
        larga = escribir_audio(self.salida("larga.wav"), voz_sintetica(20.0))
        for clave in ("nota_calle", "video_playa"):
            p = PA.aplicar_escena(PA.abrir_proyecto(larga), ESCENAS[clave])
            veces = 0.0
            for _ in range(2):   # la mejor de dos: que un pico de carga de la PC no la haga fallar
                t0 = time.perf_counter()
                with MezcladorAudio(p) as m:
                    while not m.terminado:
                        m.leer(2400)   # de a 50 ms, como la vista previa
                veces = max(veces, 20.0 / (time.perf_counter() - t0))
            with self.subTest(escena=clave):
                self.assertGreaterEqual(veces, 5.0, f"{clave}: {veces:.1f} veces el tiempo real")


class PruebasExportar(_ConMedios):
    def test_cada_formato(self):
        p = PA.aplicar_escena(PA.abrir_proyecto(self.voz), ESCENAS["nota_oficina"])
        p = p.con(tramos=((0.0, 2.0), (3.0, 6.0)))
        disponibles = [f.nombre for f in PA.formatos_proyecto_disponibles()]
        self.assertEqual(disponibles[:2], ["whatsapp", "m4a"])
        esperado = {"whatsapp": ("opus", 1, ".ogg"), "m4a": ("aac", 2, ".m4a"), "mp3": ("mp3", 2, ".mp3"),
                    "wav": ("pcm_s16le", 2, ".wav")}
        for nombre in disponibles:
            with self.subTest(formato=nombre):
                codec, canales, extension = esperado[nombre]
                destino = self.salida(f"exportado{extension}")
                avances = []
                r = PA.exportar_proyecto(p, destino, progreso=lambda h, n, s: avances.append((h, n)))
                self.assertEqual((r.ruta, r.formato, r.canales, r.frecuencia), (destino, nombre, canales, SR))
                self.assertAlmostEqual(r.duracion, 5.0, delta=1e-3)
                self.assertEqual(avances[-1][0], avances[-1][1])
                datos, sr, ch, cod = leer_todo(destino)
                self.assertTrue(cod.startswith(codec), cod)   # el decodificador de MP3 de FFmpeg es "mp3float"
                self.assertEqual((ch, sr), (canales, SR))
                self.assertAlmostEqual(len(datos) / sr, 5.0, delta=0.06)
                self.assertGreater(rms(datos), 0.005)
        self.assertEqual([x.name for x in self.dir.glob(".*parcial*")], [])
        # El formato también se puede pedir aparte de la extensión.
        r = PA.exportar_proyecto(p, self.salida("nota.opus"), formato="whatsapp")
        self.assertEqual(leer_todo(r.ruta)[3], "opus")
        self.assertEqual(PA.ruta_salida_proyecto(p, "whatsapp").name, "voz_celular.ogg")
        with self.assertRaises(ValueError):
            PA.exportar_proyecto(p, self.salida("x.flac"))
        with self.assertRaises(ValueError):
            PA.exportar_proyecto(p, self.voz, formato="wav")   # nunca sobre la voz
        with self.assertRaises(ValueError):
            PA.exportar_proyecto(p.con(tramos=()), self.salida("vacio.wav"))

    def test_whatsapp_no_comprime_dos_veces(self):
        registro = []
        original = PA.CadenaVoz

        class Espia(original):
            def __init__(self, ajustes, frecuencia=48000, codec=True):
                registro.append((ajustes.destino, codec))
                super().__init__(ajustes, frecuencia, codec)

        q = proyecto(self.voz, [(0.0, 3.0)], voz=AjustesVoz(destino="whatsapp", lugar="calle"))
        PA.CadenaVoz = Espia
        try:
            PA.exportar_proyecto(q, self.salida("w.ogg"))
            PA.exportar_proyecto(q, self.salida("w.m4a"))
            PA.exportar_proyecto(q.con(voz=AjustesVoz(destino="auriculares")), self.salida("a.ogg"))
        finally:
            PA.CadenaVoz = original
        self.assertEqual(registro, [("whatsapp", False), ("whatsapp", True), ("auriculares", True)])

    def test_whatsapp_suena_como_la_vista_previa(self):
        # Sin la etapa 7 de la cadena, el Opus del archivo tiene que cortar los agudos como el de 16 kHz.
        p = PA.aplicar_escena(PA.abrir_proyecto(self.voz), ESCENAS["nota_calle"])

        def agudos(y):
            m = y.mean(axis=1) if y.ndim == 2 else y
            f = np.fft.rfftfreq(len(m), 1 / SR)
            e = np.abs(np.fft.rfft(m)) ** 2
            return 10 * np.log10(e[(f >= 8000) & (f < 12000)].sum() / e.sum() + 1e-20)

        with MezcladorAudio(p, formato="f32") as m:
            vista = leer_mezclador(m)
        r = PA.exportar_proyecto(p, self.salida("banda.ogg"))
        exportado = leer_todo(r.ruta)[0]
        self.assertAlmostEqual(agudos(exportado), agudos(vista), delta=6.0)

    def test_cancelar_no_deja_archivos(self):
        carpeta = self.salida("cancelado")
        carpeta.mkdir()
        p = PA.aplicar_escena(PA.abrir_proyecto(self.voz), ESCENAS["nota_calle"])
        avances = []
        with self.assertRaises(Cancelado):
            PA.exportar_proyecto(p, carpeta / "a.m4a", progreso=lambda h, n, s: avances.append(h),
                                 cancelado=lambda: len(avances) >= 2)
        self.assertEqual(list(carpeta.iterdir()), [])
        with self.assertRaises(Cancelado):   # en la pasada que mide el pico
            PA.exportar_proyecto(p.con(sonido=AjustesAudio(normalizar=True)), carpeta / "b.ogg",
                                 cancelado=lambda: True)
        self.assertEqual(list(carpeta.iterdir()), [])


class PruebasEscenas(_ConMedios):
    def test_aplicar(self):
        p = proyecto(self.voz, [(0.0, 2.0), (4.0, 8.0)])
        e = ESCENAS["nota_calle"]
        q = PA.aplicar_escena(p, e)
        self.assertEqual((q.voz, q.fondos), (e.voz, e.fondos))
        self.assertEqual(len(q.sonidos), 1)
        s = q.sonidos[0]
        self.assertEqual((s.origen, s.clave), ("generado", "colectivo_pasa"))
        self.assertAlmostEqual(PA.ancla_en_resultado(q, s.ancla), 0.4 * 6.0, places=6)   # 40 % del resultado
        self.assertAlmostEqual(s.ancla, 4.4, places=6)                                    # en tiempo original
        self.assertEqual((q.ruta, q.tramos, q.sonido), (p.ruta, p.tramos, p.sonido))
        sin = PA.aplicar_escena(q, ESCENAS["solo_anti_ia"])
        self.assertEqual((sin.fondos, sin.sonidos), ((), ()))

    def test_escenas_propias(self):
        self.assertEqual(PA.escenas_propias(), {})
        agregado = PA.agregar_a_mis_sonidos(self.pajaros)
        p = PA.aplicar_escena(proyecto(self.voz, [(0.0, 2.0), (4.0, 8.0)]), ESCENAS["video_playa"])
        p = p.con(sonidos=(SonidoSuelto("generado", "bocina", 5.0, 0.3),
                           SonidoSuelto("archivo", agregado.name, 1.0, 0.6),
                           SonidoSuelto("generado", "auto_pasa", 1.0, 0.5, semilla=7)))
        e = PA.guardar_escena("  Mi playa  ", p)
        self.assertEqual((e.nombre, e.clave, e.propia), ("Mi playa", "Mi playa", True))
        self.assertEqual((e.voz, e.fondos), (p.voz, p.fondos))
        self.assertTrue(e.descripcion)
        archivo = Path(os.environ["APPDATA"]) / "NaturalShot PRO" / "escenas.json"
        self.assertTrue(archivo.is_file())
        self.assertEqual([x.name for x in archivo.parent.glob("*.tmp")], [])
        json.loads(archivo.read_text(encoding="utf-8"))
        leidas = PA.escenas_propias()
        self.assertEqual(list(leidas), ["Mi playa"])
        self.assertEqual(leidas["Mi playa"], e)
        # Aplicada a otro proyecto, los sonidos caen en la misma fracción del resultado.
        otro = PA.aplicar_escena(PA.abrir_proyecto(self.voz), leidas["Mi playa"])
        self.assertEqual([(s.origen, s.clave, s.semilla) for s in otro.sonidos],
                         [("generado", "bocina", 0), ("archivo", agregado.name, 0), ("generado", "auto_pasa", 7)])
        self.assertEqual(len(e.sonidos[0]), 3)   # la forma más corta: sin semilla ni origen
        self.assertEqual(e.sonidos[1][3:], ("archivo",))
        self.assertEqual(e.sonidos[2][3:], ("generado", 7))
        self.assertAlmostEqual(otro.sonidos[0].ancla, 3.0 / 6.0 * 8.0, places=3)
        self.assertAlmostEqual(otro.sonidos[1].ancla, 1.0 / 6.0 * 8.0, places=3)
        # Guardar con el mismo nombre la reemplaza; otra se agrega.
        PA.guardar_escena("Mi playa", p.con(fondos=()))
        PA.guardar_escena("Otra", p)
        leidas = PA.escenas_propias()
        self.assertEqual(list(leidas), ["Mi playa", "Otra"])
        self.assertEqual(leidas["Mi playa"].fondos, ())
        PA.borrar_escena("Mi playa")
        PA.borrar_escena("No existe")
        self.assertEqual(list(PA.escenas_propias()), ["Otra"])
        with self.assertRaises(ValueError):
            PA.guardar_escena("   ", p)
        # Un archivo dañado no rompe nada: no hay escenas propias.
        archivo.write_text("{esto no es json", encoding="utf-8")
        self.assertEqual(PA.escenas_propias(), {})
        PA.guardar_escena("Nueva", p)
        self.assertEqual(list(PA.escenas_propias()), ["Nueva"])
        # Bytes que no son UTF-8: tampoco traban nada (queda como .bak y se arranca limpio).
        archivo.write_bytes(b'{"escenas": [], "x": "\xff\xfe malo"}')
        self.assertEqual(PA.escenas_propias(), {})
        PA.guardar_escena("Otra más", p)
        self.assertEqual(list(PA.escenas_propias()), ["Otra más"])
        self.assertTrue(archivo.with_name("escenas.json.bak").is_file())
        PA.borrar_escena("Otra más")


class PruebasMisSonidos(_ConMedios):
    def test_agregar_renombrar_y_borrar(self):
        carpeta = PA.carpeta_sonidos()
        self.assertEqual(carpeta, Path(os.environ["APPDATA"]) / "NaturalShot PRO" / "sonidos")
        self.assertEqual(PA.mis_sonidos(), [])
        a = PA.agregar_a_mis_sonidos(self.pajaros)
        b = PA.agregar_a_mis_sonidos(self.pajaros)
        self.assertEqual((a.name, b.name), ("pajaros.wav", "pajaros (2).wav"))
        self.assertEqual(a.read_bytes(), self.pajaros.read_bytes())
        self.assertEqual(PA.mis_sonidos(), [a, b])
        c = PA.renombrar_sonido("pajaros (2).wav", "Pájaros del patio")
        self.assertEqual(c, carpeta / "Pájaros del patio.wav")
        self.assertFalse(b.exists())
        self.assertEqual(PA.renombrar_sonido(c.name, "Pájaros del patio.wav"), c)   # el mismo nombre: nada
        with self.assertRaises(ValueError):
            PA.renombrar_sonido(c.name, "pajaros")   # ya hay uno
        for malo in ("", "a/b", "..", "con:", "NUL", "COM0", "LPT0", "CONIN$", "CONOUT$", "COM¹", " .", "tab\tx",
                     "a" * 121, "a" * 118):   # 118 + ".wav" se pasa de 120
            with self.assertRaises(ValueError, msg=malo):
                PA.renombrar_sonido(c.name, malo)
        with self.assertRaises(FileNotFoundError):
            PA.renombrar_sonido("no_esta.wav", "x")
        PA.borrar_sonido(c.name)
        PA.borrar_sonido("no_esta.wav")
        self.assertEqual(PA.mis_sonidos(), [a])
        with self.assertRaises(ValueError):
            PA.borrar_sonido("../afuera.wav")

    def test_lo_que_no_sirve(self):
        texto = self.salida("notas.txt")
        texto.write_text("hola")
        with self.assertRaises(ValueError):
            PA.agregar_a_mis_sonidos(texto)
        basura = self.salida("roto.mp3")
        basura.write_bytes(b"\x00" * 5000)
        with self.assertRaises(ValueError):
            PA.agregar_a_mis_sonidos(basura)
        anterior = PA.DURACION_MAX_SONIDO
        PA.DURACION_MAX_SONIDO = 2.0   # en vez de generar un audio de más de 10 minutos
        try:
            with self.assertRaisesRegex(ValueError, "minuto"):
                PA.agregar_a_mis_sonidos(self.pajaros)
        finally:
            PA.DURACION_MAX_SONIDO = anterior
        self.assertEqual(PA.mis_sonidos(), [])

    def test_de_fondo_se_repite_con_fundido_cruzado(self):
        nombre = PA.agregar_a_mis_sonidos(self.pajaros).name
        p = proyecto(self.callada, fondos=(FondoProyecto("archivo", nombre, 0.5),))
        with MezcladorAudio(p, formato="f32") as m:
            self.assertEqual(m.faltan, ())
            y = leer_mezclador(m, (3000, 48000))
        self.assertEqual(len(y), 8 * SR)
        # Lo esperado, según lo documentado: el archivo calibrado a -30 dBFS RMS, después cada
        # P = largo - 2 s se repite su principio con un fundido cruzado de 2 s (igual potencia).
        x = PA.cargar_sonido(nombre).astype(np.float64)
        x = x * (10 ** (-30 / 20) / rms(x))
        X, P = 2 * SR, len(x) - 2 * SR
        t = np.arange(len(y))
        i = np.where(t < P, t, t % P)
        esperado = x[i]
        cruce = (t >= P) & (i < X)
        u = (i[cruce] + 0.5) / X
        esperado[cruce] = (x[i[cruce]] * np.sin(np.pi / 2 * u)[:, None]
                           + x[P + i[cruce]] * np.cos(np.pi / 2 * u)[:, None])
        f = round(0.3 * SR)
        rampa = 0.5 - 0.5 * np.cos(np.pi * (np.arange(f) + 0.5) / f)
        esperado[:f] *= rampa[:, None]
        esperado[-f:] *= rampa[::-1, None]
        np.testing.assert_allclose(y, esperado, atol=1e-5)
        ventanas = [rms(y[k:k + SR // 10]) for k in range(int(0.4 * SR), int(7.5 * SR), SR // 10)]
        # Sin huecos al repetir (el sonido de prueba sube y baja hasta 5 veces: un hueco sería ~0).
        self.assertGreater(min(ventanas), 0.12 * np.median(ventanas))

    def test_lo_que_falta_se_saltea(self):
        base = proyecto(self.voz, voz=AjustesVoz(destino="video", compresion=False),
                        fondos=(FondoProyecto("generado", "lluvia"),))
        con_faltas = base.con(fondos=base.fondos + (FondoProyecto("archivo", "no_esta.wav"),
                                                    FondoProyecto("generado", "fondo_que_no_existe")),
                              sonidos=(SonidoSuelto("archivo", "tampoco.mp3", 1.0),))
        with MezcladorAudio(base, formato="f32") as m:
            esperado = leer_mezclador(m)
        with MezcladorAudio(con_faltas, formato="f32") as m:
            self.assertEqual(m.faltan, ("no_esta.wav", "fondo_que_no_existe", "tampoco.mp3"))
            obtenido = leer_mezclador(m)
        np.testing.assert_array_equal(obtenido, esperado)
        self.assertIsNone(PA.cargar_sonido("no_esta.wav"))
        # Uno que estaba en la caché y se borró por fuera (desde el Explorador): falta.
        nombre = PA.agregar_a_mis_sonidos(self.pajaros).name
        self.assertIsNotNone(PA.cargar_sonido(nombre))
        os.remove(PA.carpeta_sonidos() / nombre)
        self.assertIsNone(PA.cargar_sonido(nombre))
        with MezcladorAudio(base.con(fondos=(FondoProyecto("archivo", nombre),)), formato="f32") as m:
            self.assertEqual(m.faltan, (nombre,))


# ---------------------------------------------------------------------------
# Sesión
# ---------------------------------------------------------------------------

class PruebasSesion(unittest.TestCase):
    def setUp(self):
        from celular_natural import sesion
        self.sesion = sesion
        sesion.borrar()

    def proyecto(self, volumen=1.0):
        return ProyectoAudio("C:/no/importa/voz.m4a", ((0.0, 2.0), (3.0, 9.0)), AjustesAudio(volumen=volumen),
                             AjustesVoz(destino="video", lugar="habitacion", anti_ia=0.3),
                             (FondoProyecto("generado", "habitacion", 0.25), FondoProyecto("archivo", "pájaros.mp3")),
                             (SonidoSuelto("generado", "sirena_lejos", 4.0, 0.4),))

    def test_guardar_y_leer_el_proyecto_de_audio(self):
        s = self.sesion
        for clase in ("ProyectoAudio", "FondoProyecto", "SonidoSuelto", "AjustesVoz", "AjustesAudio", "Escena"):
            self.assertIn(clase, s.CLASES)
        inicio = {"proyecto": self.proyecto(), "escena": ESCENAS["video_casa"]}
        despues = {"proyecto": self.proyecto(0.5), "escena": ESCENAS["video_casa"], "zoom": 2.5}
        guardada = s.SesionGuardada([], -1, s.AudioGuardado(despues, [("Inicio", inicio), ("Volumen", despues)], 1))
        s.guardar(guardada)
        self.assertTrue(s.archivo_sesion().is_file())   # sin fotos, pero con audio: se guarda
        leida, problema = s.cargar()
        self.assertIsNone(problema)
        self.assertEqual(leida.fotos, [])
        self.assertEqual(leida.audio, guardada.audio)
        self.assertIsInstance(leida.audio.estado["proyecto"], ProyectoAudio)
        # Sin fotos ni audio: se borra, como siempre.
        s.guardar(s.SesionGuardada())
        self.assertFalse(s.archivo_sesion().exists())

    def test_sesion_vieja_sin_audio(self):
        s = self.sesion
        datos = {"version": s.VERSION_FORMATO, "app": "1.0", "guardada": 0.0, "actual": 0,
                 "fotos": [{"ruta": "C:/foto.jpg", "estado": None, "historial": None, "pos": 0}]}
        contenido = pickle.dumps(datos, protocol=pickle.HIGHEST_PROTOCOL)
        leida = s.leer(s.MARCA + s._CABECERA.pack(zlib.crc32(contenido)) + contenido)
        self.assertIsNone(leida.audio)
        self.assertEqual([f.ruta for f in leida.fotos], ["C:/foto.jpg"])

    def escribir(self, datos) -> None:
        s = self.sesion
        contenido = pickle.dumps(datos, protocol=pickle.HIGHEST_PROTOCOL)
        s.escribir_atomico(s.archivo_sesion(), s.MARCA + s._CABECERA.pack(zlib.crc32(contenido)) + contenido)

    def test_audio_roto_no_se_lleva_las_fotos(self):
        s = self.sesion
        from fractions import Fraction
        bien = {"estado": {"proyecto": self.proyecto()}, "historial": None, "pos": 0}
        lugar_renombrado = pickle.dumps(bien, protocol=pickle.HIGHEST_PROTOCOL).replace(b"habitacion", b"habitacioN")
        rotos = [
            {"estado": {"sin": "proyecto"}, "historial": None, "pos": 0},
            "cualquier cosa",
            {"estado": {"proyecto": self.proyecto()}, "historial": [("x", {"proyecto": 3})], "pos": 0},
            # Como lo escribe esta versión (un pickle aparte): un lugar que una versión futura renombró…
            lugar_renombrado,
            # … o una clase que esta versión no permite.
            pickle.dumps({"estado": {"proyecto": self.proyecto(), "x": Fraction(1, 3)}}),
            b"no es un pickle",
        ]
        for audio in rotos:
            with self.subTest(audio=repr(audio)[:40]):
                log = s.carpeta_sesion() / s.ARCHIVO_LOG
                if log.exists():
                    log.unlink()
                self.escribir({"version": s.VERSION_FORMATO, "app": "1.0", "guardada": 0.0, "actual": 0,
                               "fotos": [{"ruta": "C:/foto.jpg", "estado": None, "historial": None, "pos": 0}],
                               "audio": audio})
                leida, problema = s.cargar()
                self.assertIsNone(problema)
                self.assertEqual([f.ruta for f in leida.fotos], ["C:/foto.jpg"])   # las fotos siguen
                self.assertIsNone(leida.audio)
                self.assertFalse(s.archivo_respaldo().exists())
                self.assertIn("proyecto de audio", log.read_text(encoding="utf-8"))
        # Y el mismo proyecto sin romper se lee bien (en los dos formatos).
        for audio in (bien, pickle.dumps(bien, protocol=pickle.HIGHEST_PROTOCOL)):
            self.escribir({"version": s.VERSION_FORMATO, "app": "1.0", "guardada": 0.0, "actual": -1, "fotos": [],
                           "audio": audio})
            self.assertEqual(s.cargar()[0].audio.estado["proyecto"], self.proyecto())


if __name__ == "__main__":
    unittest.main()
