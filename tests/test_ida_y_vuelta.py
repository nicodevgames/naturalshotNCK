"""Pruebas de la ida y vuelta Video ↔ Audio (Tarea E, lado del video).

* **Motor** (``motor/video.py``): ``AudioExterno`` (validación y pickle);
  ``exportar_video(..., audio_externo=)`` alineado con el original (los mismos
  cortes y ajustes) y desde el 0 del resultado (cortado al largo, completado con
  silencio, con los silencios pasados al resultado); otra frecuencia y canales;
  "Quitar el sonido"; un externo que no existe o sin sonido; ``LectorDesdeCero``
  igual a lo exportado; "Guardar solo el audio" con externo y los temporales.
* **Editor de video** (ventana real, modo sin pantalla): los tres botones de la
  tarjeta Sonido, ``editarSonidoPedido`` con un WAV del largo del original,
  ``usar_sonido_externo``, deshacer y rehacer del sonido externo, la pista y la
  vista previa con el externo, y exportar con "original" y con "resultado".

Los medios se generan con PyAV en una carpeta temporal (tonos distintos por
segundo, así se sabe de qué instante viene cada parte). ``APPDATA`` apunta a una
carpeta temporal: los WAV de "temporal" no tocan los datos de la app.
"""

from __future__ import annotations

import os
import pickle
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

try:
    import av
except ImportError:  # pragma: no cover
    av = None

from celular_natural.motor.audio import AjustesAudio  # noqa: E402  (no carga PyAV)

if av is not None:
    from test_audio import generar, leer_audio, leer_wav, tono  # noqa: E402
    from celular_natural.motor import Cancelado  # noqa: E402
    from celular_natural.motor import audio as A  # noqa: E402
    from celular_natural.motor import video as V  # noqa: E402

SR = 48000
FRECUENCIAS_EXTERNO = (300.0, 500.0, 700.0, 900.0, 1100.0, 1300.0, 1500.0, 1700.0)


# ---------------------------------------------------------------------------
# Medios
# ---------------------------------------------------------------------------

def escalera_externa(segundos: float, sr: int = SR, canales: int = 2, amplitud: float = 0.3) -> np.ndarray:
    """Un tono distinto por segundo (300, 500, 700… Hz): dice de qué segundo del externo viene cada parte."""
    n = int(round(segundos * sr))
    t = np.arange(n) / sr
    f = np.array(FRECUENCIAS_EXTERNO)[np.minimum((t // 1).astype(int), len(FRECUENCIAS_EXTERNO) - 1)]
    fase = 2 * np.pi * np.cumsum(f) / sr
    return np.repeat((amplitud * np.sin(fase)).astype(np.float32)[None, :], canales, 0)


def escribir_wav(ruta: Path, senal: np.ndarray, sr: int = SR) -> Path:
    """WAV de 16 bits con ``senal`` (canales × muestras) a ``sr``."""
    with av.open(str(ruta), "w", format="wav") as c:
        a = c.add_stream("pcm_s16le", rate=sr)
        a.layout = "stereo" if senal.shape[0] == 2 else "mono"
        for k in range(0, senal.shape[1], 4096):
            entero = np.clip(np.round(senal[:, k:k + 4096] * 32768), -32768, 32767).astype(np.int16)
            cuadro = av.AudioFrame.from_ndarray(np.ascontiguousarray(entero.T).reshape(1, -1), format="s16",
                                                layout=a.layout.name)
            cuadro.sample_rate = sr
            cuadro.pts = k
            for p in a.encode(cuadro):
                c.mux(p)
        for p in a.encode():
            c.mux(p)
    return ruta


def esperado_original(senal: np.ndarray, tramos, sr: int = SR) -> np.ndarray:
    """Los tramos de ``senal`` uno detrás de otro (lo que debe sonar con "original")."""
    return np.concatenate([senal[:, round(a * sr):round(b * sr)] for a, b in tramos], axis=1)


def correlacion(a: np.ndarray, b: np.ndarray) -> float:
    """Correlación normalizada del primer canal, en el largo común."""
    n = min(a.shape[-1], b.shape[-1])
    x, y = a[0, :n].astype(np.float64), b[0, :n].astype(np.float64)
    den = np.sqrt((x * x).sum() * (y * y).sum())
    return float((x * y).sum() / den) if den > 0 else 0.0


def frecuencia_dominante(x: np.ndarray, sr: int) -> float:
    ventana = x * np.hanning(len(x))
    espectro = np.abs(np.fft.rfft(ventana))
    return float(np.argmax(espectro) * sr / len(x))


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x.astype(np.float64))))) if x.size else 0.0


# ---------------------------------------------------------------------------
# Motor
# ---------------------------------------------------------------------------

@unittest.skipIf(av is None, "Falta PyAV (pip install av==19.0.1)")
class PruebasMotorAudioExterno(unittest.TestCase):
    """``AudioExterno`` y ``exportar_video(..., audio_externo=)``."""

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="ida_vuelta_"))
        # El video: 6 s con un tono de 440 Hz propio (el externo tiene que reemplazarlo).
        cls.video = generar(cls.dir / "video.mp4", tono(6.0, 440.0))
        cls.mudo = generar(cls.dir / "mudo.mp4", None, segundos=6.0)
        cls.senal6 = escalera_externa(6.0)
        cls.externo6 = escribir_wav(cls.dir / "externo6.wav", cls.senal6)
        cls.senal8 = escalera_externa(8.0)
        cls.externo8 = escribir_wav(cls.dir / "externo8.wav", cls.senal8)
        cls.senal2 = escalera_externa(2.0)
        cls.externo2 = escribir_wav(cls.dir / "externo2.wav", cls.senal2)
        cls.senal_mono = escalera_externa(8.0, sr=22050, canales=1)
        cls.externo_mono = escribir_wav(cls.dir / "mono22.wav", cls.senal_mono, sr=22050)

    @classmethod
    def tearDownClass(cls):
        V.cerrar_lectores()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def _exportar(self, nombre: str, tramos, externo, audio=None, video=None):
        salida = self.dir / nombre
        r = V.exportar_video(video or self.video, salida, (), tramos, audio=audio, audio_externo=externo)
        return r, salida

    # ------------------------------------------------------------ AudioExterno
    def test_audio_externo_valida_y_se_guarda_con_pickle(self):
        e = V.AudioExterno(Path(self.externo6), "resultado")
        self.assertEqual(e.ruta, str(self.externo6))
        self.assertTrue(e.desde_cero)
        self.assertEqual(e.nombre, "externo6.wav")
        self.assertEqual(V.AudioExterno(str(self.externo6)).alineado, "original")
        self.assertEqual(pickle.loads(pickle.dumps(e)), e)
        self.assertEqual(hash(pickle.loads(pickle.dumps(e))), hash(e))
        with self.assertRaises(ValueError):
            V.AudioExterno("x.wav", "al revés")
        with self.assertRaises(ValueError):
            V.AudioExterno("", "original")
        with self.assertRaises(ValueError):
            V.AudioExterno(None)  # type: ignore[arg-type]
        info = V.validar_audio_externo(e)
        self.assertAlmostEqual(info.duracion, 6.0, delta=0.01)

    def test_silencios_en_resultado(self):
        mapa = V.MapaTiempo(((0.0, 1.0), (2.0, 6.0)), 6.0)
        # Un silencio que cruza el borrado queda de un solo trozo; uno dentro de lo borrado desaparece.
        self.assertEqual(V.silencios_en_resultado(((0.5, 2.5), (1.2, 1.8), (4.0, 5.0)), mapa),
                         ((0.5, 1.5), (3.0, 4.0)))
        ruta, tramos, silencios = V.sonido_a_medir(self.video, [(0, 1), (2, 6)], 6.0, ((4.0, 5.0),),
                                                   V.AudioExterno(str(self.externo8), "resultado"))
        self.assertEqual((ruta, tramos, silencios), (str(self.externo8), ((0.0, 5.0),), ((3.0, 4.0),)))
        ruta, tramos, _ = V.sonido_a_medir(self.video, [(0, 1), (2, 6)], 6.0, (), V.AudioExterno(str(self.externo6)))
        self.assertEqual((ruta, tramos), (str(self.externo6), ((0.0, 1.0), (2.0, 6.0))))
        self.assertEqual(V.sonido_a_medir(self.video, None, 6.0)[:2], (str(self.video), ((0.0, 6.0),)))

    # ------------------------------------------------------------ "original"
    def test_original_con_cortes_es_el_externo_con_los_mismos_cortes(self):
        tramos = [(0.0, 1.5), (3.0, 6.0)]
        r, salida = self._exportar("original.mp4", tramos, V.AudioExterno(str(self.externo6), "original"))
        self.assertTrue(r.con_audio)
        audio, sr = leer_audio(salida)
        self.assertEqual(sr, SR)
        esperado = esperado_original(self.senal6, tramos)
        self.assertAlmostEqual(audio.shape[1] / sr, 4.5, delta=0.05)
        self.assertGreater(correlacion(audio, esperado), 0.95)
        # Y nada del sonido del video (440 Hz): en el segundo 2 del resultado suena el 3,5 del externo (900 Hz).
        trozo = audio[0, round(2.2 * sr):round(2.4 * sr)]
        self.assertAlmostEqual(frecuencia_dominante(trozo, sr), 900.0, delta=15)

    def test_original_con_los_mismos_ajustes(self):
        tramos = [(0.0, 1.5), (3.0, 6.0)]
        ajustes = AjustesAudio(volumen=0.5, silencios=((3.5, 4.5),), fundido_entrada=0.5)
        externo = V.AudioExterno(str(self.externo6), "original")
        r, salida = self._exportar("original_ajustes.mp4", tramos, externo, ajustes)
        audio, sr = leer_audio(salida)
        # El silencio está en tiempo original: 3,5 a 4,5 s es 2,0 a 3,0 s del resultado.
        self.assertLess(rms(audio[0, round(2.1 * sr):round(2.9 * sr)]), 0.003)
        self.assertAlmostEqual(rms(audio[0, round(3.2 * sr):round(4.2 * sr)]), 0.3 / np.sqrt(2) * 0.5, delta=0.01)
        self.assertLess(rms(audio[0, :round(0.05 * sr)]), 0.02)  # el fundido de entrada
        # Exacto en WAV: lo mismo que el sonido del video con esos ajustes, pero del externo.
        wav = V.exportar_sonido(self.video, self.dir / "original_ajustes.wav", tramos, ajustes, externo)
        del wav
        muestras = leer_wav(self.dir / "original_ajustes.wav").astype(np.float32) / 32768
        directo = self.dir / "directo.wav"
        A.exportar_audio(self.externo6, directo, tramos, ajustes)
        self.assertTrue(np.array_equal(muestras, leer_wav(directo).astype(np.float32) / 32768))

    def test_original_con_otra_frecuencia_y_canales(self):
        tramos = [(0.0, 2.0), (4.0, 6.0)]
        r, salida = self._exportar("mono22.mp4", tramos, V.AudioExterno(str(self.externo_mono), "original"))
        audio, sr = leer_audio(salida)
        self.assertEqual(sr, SR)            # la frecuencia del sonido del video
        self.assertEqual(audio.shape[0], 2)  # estéreo, como el video
        self.assertAlmostEqual(audio.shape[1] / sr, 4.0, delta=0.05)
        # En el segundo 2,5 del resultado suena el 4,5 del externo (1100 Hz).
        trozo = audio[0, round(2.3 * sr):round(2.7 * sr)]
        self.assertAlmostEqual(frecuencia_dominante(trozo, sr), 1100.0, delta=15)

    # ------------------------------------------------------------ "resultado"
    def test_resultado_empieza_en_cero_y_se_corta_al_largo(self):
        tramos = [(0.0, 1.0), (2.0, 6.0)]  # 5 s de resultado; el externo dura 8
        r, salida = self._exportar("resultado.mp4", tramos, V.AudioExterno(str(self.externo8), "resultado"))
        self.assertTrue(r.con_audio)
        audio, sr = leer_audio(salida)
        self.assertAlmostEqual(audio.shape[1] / sr, 5.0, delta=0.05)
        esperado = self.senal8[:, :round(5.0 * sr)]
        self.assertGreater(correlacion(audio, esperado), 0.95)
        # El segundo 1,5 del resultado es el 1,5 del externo (500 Hz): los cortes del video no lo mueven.
        self.assertAlmostEqual(frecuencia_dominante(audio[0, round(1.3 * sr):round(1.7 * sr)], sr), 500.0, delta=15)

    def test_resultado_mas_corto_sigue_en_silencio(self):
        tramos = [(0.0, 1.0), (2.0, 6.0)]
        externo = V.AudioExterno(str(self.externo2), "resultado")
        r, salida = self._exportar("corto.mp4", tramos, externo)
        audio, sr = leer_audio(salida)
        self.assertAlmostEqual(audio.shape[1] / sr, 5.0, delta=0.05)
        self.assertGreater(correlacion(audio[:, :round(1.9 * sr)], self.senal2[:, :round(1.9 * sr)]), 0.95)
        self.assertLess(rms(audio[:, round(2.1 * sr):]), 0.002)
        # En WAV, exacto: el externo y después ceros.
        V.exportar_sonido(self.video, self.dir / "corto.wav", tramos, None, externo)
        wav = leer_wav(self.dir / "corto.wav")
        self.assertEqual(wav.shape[1], 5 * sr)
        self.assertTrue(np.array_equal(wav[:, :2 * sr], np.clip(np.round(self.senal2 * 32768), -32768, 32767)))
        self.assertFalse(wav[:, 2 * sr:].any())

    def test_resultado_con_ajustes_y_silencios_mapeados(self):
        tramos = [(0.0, 1.0), (2.0, 6.0)]
        ajustes = AjustesAudio(volumen=0.5, silencios=((3.0, 4.0),), fundido_salida=1.0)
        externo = V.AudioExterno(str(self.externo8), "resultado")
        V.exportar_sonido(self.video, self.dir / "res_ajustes.wav", tramos, ajustes, externo)
        x = leer_wav(self.dir / "res_ajustes.wav").astype(np.float32) / 32768
        self.assertEqual(x.shape[1], 5 * SR)
        # Silencio de 3 a 4 s del original = 2 a 3 s del resultado.
        self.assertLess(rms(x[:, round(2.05 * SR):round(2.95 * SR)]), 1e-4)
        self.assertAlmostEqual(rms(x[0, round(1.1 * SR):round(1.9 * SR)]), 0.3 / np.sqrt(2) * 0.5, delta=0.005)
        # El fundido de salida en el último segundo del resultado (cuadrático: a la mitad, 1/4).
        medio = x[0, round(4.45 * SR):round(4.55 * SR)]
        self.assertAlmostEqual(rms(medio), 0.3 / np.sqrt(2) * 0.5 * 0.25, delta=0.01)
        self.assertLess(np.abs(x[:, -100:]).max(), 0.001)
        # El lector de la vista previa da lo mismo (en float).
        with V.LectorDesdeCero(self.externo8, tramos, 6.0, ajustes, formato="f32") as lector:
            self.assertAlmostEqual(lector.duracion_resultado, 5.0)
            todo = []
            while not lector.terminado:
                todo.append(lector.leer_array(7000))
            leido = np.concatenate(todo).T
        self.assertEqual(leido.shape[1], 5 * SR)
        self.assertLess(np.abs(leido - x).max(), 2 / 32768)

    def test_resultado_con_otra_frecuencia_y_video_mudo(self):
        externo = V.AudioExterno(str(self.externo_mono), "resultado")
        r, salida = self._exportar("mudo_con_voz.mp4", [(0.0, 6.0)], externo, video=self.mudo)
        self.assertTrue(r.con_audio)  # el video no tenía sonido: ahora tiene el externo
        audio, sr = leer_audio(salida)
        self.assertEqual(sr, 22050)      # sin sonido propio, la frecuencia del externo
        self.assertEqual(audio.shape[0], 1)
        self.assertAlmostEqual(audio.shape[1] / sr, 6.0, delta=0.05)
        self.assertAlmostEqual(frecuencia_dominante(audio[0, round(3.3 * sr):round(3.7 * sr)], sr), 900.0, delta=15)

    def test_lector_desde_cero_sigue_a_la_imagen(self):
        with V.LectorDesdeCero(self.externo8, [(0.0, 1.0), (2.0, 6.0)], 6.0, desde=2.5) as lector:
            self.assertAlmostEqual(lector.posicion_resultado, 1.5)
            self.assertAlmostEqual(lector.posicion, 2.5)
            self.assertAlmostEqual(lector.original_de_resultado(0.5), 0.5)
            self.assertAlmostEqual(lector.original_de_resultado(1.0), 2.0)  # la unión: lo que sigue
            lector.ir_a(1.5)  # borrado: va a la unión
            self.assertAlmostEqual(lector.posicion_resultado, 1.0)
            self.assertEqual(lector.bytes_por_muestra, 4)
            self.assertTrue(lector.tiene_audio)
            datos = lector.leer(4800)
            self.assertEqual(len(datos), 4800 * 4)
            lector.ir_a_resultado(10.0)
            self.assertTrue(lector.terminado)
            self.assertEqual(lector.leer(100), b"")

    # ------------------------------------------------------------ sin sonido y errores
    def test_quitar_no_deja_pista_de_audio(self):
        r, salida = self._exportar("quitado.mp4", None, V.AudioExterno(str(self.externo6), "original"),
                                   AjustesAudio(quitar=True))
        self.assertFalse(r.con_audio)
        self.assertIsNone(leer_audio(salida)[0])
        # Con "quitar", ni hace falta que el externo exista.
        r, _ = self._exportar("quitado2.mp4", None, V.AudioExterno(str(self.dir / "no_esta.wav"), "resultado"),
                              AjustesAudio(quitar=True))
        self.assertFalse(r.con_audio)

    def test_externo_que_no_existe_da_error_antes_de_empezar(self):
        carpeta = self.dir / "errores"
        carpeta.mkdir(exist_ok=True)
        llamadas = []
        for externo in (V.AudioExterno(str(self.dir / "no_esta.wav"), "original"),
                        V.AudioExterno(str(self.mudo), "resultado")):  # un video sin sonido
            with self.assertRaises(ValueError) as error:
                V.exportar_video(self.video, carpeta / "x.mp4", (), None, progreso=lambda *a: llamadas.append(a),
                                 audio_externo=externo)
            self.assertTrue("No se encuentra" in str(error.exception) or "no tiene sonido" in str(error.exception),
                            str(error.exception))
        self.assertEqual(llamadas, [])          # ni empezó
        self.assertEqual(list(carpeta.iterdir()), [])  # ni un temporal

    def test_sin_externo_igual_que_siempre(self):
        tramos = [(0.0, 1.5), (3.0, 6.0)]
        _, a = self._exportar("sin_externo.mp4", tramos, None)
        b = self.dir / "sin_externo_b.mp4"
        V.exportar_video(self.video, b, (), tramos)
        audio_a, _ = leer_audio(a)
        audio_b, _ = leer_audio(b)
        self.assertTrue(np.array_equal(audio_a, audio_b))

    def test_cancelar_con_externo_no_deja_archivos(self):
        carpeta = self.dir / "cancelado"
        carpeta.mkdir(exist_ok=True)
        with self.assertRaises(Cancelado):
            V.exportar_video(self.video, carpeta / "c.mp4", (), None, cancelado=lambda: True,
                             audio_externo=V.AudioExterno(str(self.externo8), "resultado"))
        self.assertEqual(list(carpeta.iterdir()), [])


@unittest.skipIf(av is None, "Falta PyAV (pip install av==19.0.1)")
class PruebasTemporales(unittest.TestCase):
    """``carpeta_temporal``, ``ruta_temporal_sonido`` y ``limpiar_temporales`` en un APPDATA de prueba."""

    def setUp(self):
        self.appdata = Path(tempfile.mkdtemp(prefix="appdata_"))
        self._parche = mock.patch.dict(os.environ, {"APPDATA": str(self.appdata)})
        self._parche.start()

    def tearDown(self):
        self._parche.stop()
        shutil.rmtree(self.appdata, ignore_errors=True)

    def test_nombres_y_limpieza(self):
        self.assertEqual(V.carpeta_temporal(), self.appdata / "NaturalShot PRO" / "temporal")
        a = V.ruta_temporal_sonido(r"C:\videos\charla en la plaza.mp4")
        self.assertTrue(a.parent.is_dir())
        self.assertTrue(a.name.startswith("charla en la plaza_sonido_") and a.suffix == ".wav", a.name)
        a.write_bytes(b"x")
        b = V.ruta_temporal_sonido(r"C:\videos\charla en la plaza.mp4")
        self.assertNotEqual(a, b)  # nombre único
        viejo, en_uso, nuevo = (V.carpeta_temporal() / n for n in ("viejo.wav", "en_uso.wav", "nuevo.wav"))
        for p in (viejo, en_uso, nuevo):
            p.write_bytes(b"x")
        hace = time.time() - 8 * 86400
        for p in (viejo, en_uso, a):
            os.utime(p, (hace, hace))
        avisados = []
        borrados = V.limpiar_temporales(conservar=[en_uso], antes_de_borrar=avisados.append)
        self.assertEqual(sorted(p.name for p in borrados), sorted([viejo.name, a.name]))
        self.assertEqual(sorted(p.name for p in avisados), sorted([viejo.name, a.name]))
        self.assertTrue(en_uso.exists() and nuevo.exists())
        self.assertFalse(viejo.exists() or a.exists())

    def test_sin_carpeta_no_hace_nada(self):
        self.assertEqual(V.limpiar_temporales(), [])


# ---------------------------------------------------------------------------
# El editor de video
# ---------------------------------------------------------------------------

def _app():
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication
    from celular_natural.ui.estilo import HOJA_ESTILO
    app = QApplication.instance() or QApplication([])
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    if app.styleSheet() != HOJA_ESTILO:
        app.setStyleSheet(HOJA_ESTILO)
    return app


def esperar(app, condicion, segundos: float = 60.0) -> bool:
    """Espera con ``time.sleep`` y ``processEvents`` (``QTest.qWait`` no suelta el GIL)."""
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        app.processEvents()
        if condicion():
            return True
        time.sleep(0.01)
    return condicion()


@unittest.skipIf(av is None, "Falta PyAV (pip install av==19.0.1)")
class PruebasEditorIdaYVuelta(unittest.TestCase):
    """El lado del video: los botones de la tarjeta Sonido, ``usar_sonido_externo``,
    ``editarSonidoPedido``, el historial, la pista, la vista previa y exportar."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        cls.dir = Path(tempfile.mkdtemp(prefix="ida_vuelta_editor_"))
        cls._entorno = {k: os.environ.get(k) for k in ("APPDATA", "NATURALSHOT_CONFIG")}
        os.environ["APPDATA"] = str(cls.dir / "appdata")
        os.environ["NATURALSHOT_CONFIG"] = str(cls.dir / "config.ini")
        cls.video = generar(cls.dir / "charla.mp4", tono(6.0, 440.0))
        cls.mudo = generar(cls.dir / "mudo.mp4", None, segundos=3.0)
        cls.senal8 = escalera_externa(8.0)
        cls.externo8 = escribir_wav(cls.dir / "voz.wav", cls.senal8)
        cls.senal2 = escalera_externa(2.0)
        cls.externo2 = escribir_wav(cls.dir / "corta.wav", cls.senal2)
        cls.senal6 = escalera_externa(6.0)
        cls.editado = escribir_wav(cls.dir / "editado.wav", cls.senal6)

    @classmethod
    def tearDownClass(cls):
        V.cerrar_lectores()
        for clave, valor in cls._entorno.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        self.editores = []

    def tearDown(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        for e in self.editores:
            e.detener()
            e.close()
            e.deleteLater()
        self.app.processEvents()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def abrir(self, ruta=None):
        """Un editor de video (sin la ventana) con ``ruta`` abierto y su forma de onda leída."""
        from celular_natural.ui.editor_video import EditorVideo
        e = EditorVideo()
        self.editores.append(e)
        e.resize(1366, 768)
        e.show()
        e.abrir(str(ruta or self.video), confirmar=False)
        self.assertTrue(esperar(self.app, lambda: e.info is not None and e.cuadro_procesado_listo()))
        self.assertTrue(esperar(self.app, lambda: e.pista_sonido.estado in ("lista", "sin_sonido")))
        return e

    def exportar(self, e, nombre: str):
        """Exporta con los diálogos simulados; devuelve (ruta, texto del aviso final)."""
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        destino = self.dir / nombre
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "")), \
                mock.patch.object(QMessageBox, "information") as aviso:
            e.exportar()
            self.assertTrue(esperar(self.app, lambda: not e.exportando, 180))
        self.assertTrue(destino.is_file())
        return destino, aviso.call_args.args[2]

    # ------------------------------------------------------------ los botones
    def test_tres_botones_y_renglon(self):
        from PySide6.QtWidgets import QFileDialog
        e = self.abrir()
        p = e.panel_sonido
        self.assertEqual(p.etiqueta_origen.text(), "Sonido: el del video")
        self.assertTrue(p.boton_editar_audio.isVisible() and p.boton_editar_audio.isEnabled())
        self.assertTrue(p.boton_cambiar.isVisible() and p.boton_cambiar.isEnabled())
        self.assertFalse(p.boton_volver_original.isVisible())
        # "Cambiar el sonido por…": el diálogo ofrece los audios del modo Audio y queda "desde el principio".
        with mock.patch.object(QFileDialog, "getOpenFileName", return_value=(str(self.externo8), "")) as dialogo:
            p.boton_cambiar.click()
        filtro = dialogo.call_args.args[3]
        for ext in ("*.mp3", "*.m4a", "*.aac", "*.wav", "*.ogg", "*.opus", "*.flac"):
            self.assertIn(ext, filtro)
        self.assertEqual(e.audio_externo, V.AudioExterno(str(self.externo8), "resultado"))
        self.assertEqual(p.etiqueta_origen.text(), "Sonido: voz.wav (desde el principio)")
        self.assertTrue(p.boton_volver_original.isVisible())
        self.assertTrue(e.tiene_cambios())
        self.assertIn("con el sonido de voz.wav", e.etiqueta_estimacion.text())
        # La pista muestra el externo (8 s, cortado a los 6 del video).
        self.assertTrue(esperar(self.app, lambda: e.pista_sonido.estado == "lista"
                                and e.cargador_onda.ruta == str(self.externo8)))
        self.assertAlmostEqual(e.pista_sonido.forma.duracion, 6.0, delta=0.01)
        # Cancelar el diálogo no cambia nada.
        with mock.patch.object(QFileDialog, "getOpenFileName", return_value=("", "")):
            p.boton_cambiar.click()
        self.assertEqual(e.audio_externo.ruta, str(self.externo8))
        # "Volver al sonido original".
        p.boton_volver_original.click()
        self.assertIsNone(e.audio_externo)
        self.assertEqual(p.etiqueta_origen.text(), "Sonido: el del video")
        self.assertFalse(p.boton_volver_original.isVisible())
        self.assertTrue(esperar(self.app, lambda: e.pista_sonido.estado == "lista"
                                and e.cargador_onda.ruta == str(self.video)))
        # El modo Audio: "editado en el modo Audio".
        self.assertTrue(e.usar_sonido_externo(str(self.editado), "original"))
        self.assertEqual(p.etiqueta_origen.text(), "Sonido: editado en el modo Audio")
        self.assertIn("con el sonido editado", e.etiqueta_estimacion.text())

    def test_video_sin_sonido(self):
        e = self.abrir(self.mudo)
        p = e.panel_sonido
        self.assertEqual(p.etiqueta_origen.text(), "Sonido: ninguno")
        self.assertFalse(p.boton_editar_audio.isEnabled())
        self.assertIn("no tiene sonido", p.boton_editar_audio.toolTip())
        self.assertTrue(p.boton_cambiar.isEnabled())
        self.assertFalse(p.volumen.isEnabled())
        # Con una voz en off, el video mudo pasa a tener sonido: se ajusta, se silencia y se exporta.
        self.assertTrue(e.usar_sonido_externo(str(self.externo8), "resultado"))
        self.assertTrue(p.volumen.isEnabled())
        self.assertTrue(e.boton_silenciar.isEnabled())
        self.assertFalse(p.boton_editar_audio.isEnabled())  # el sonido del video sigue sin existir
        self.assertTrue(esperar(self.app, lambda: e.pista_sonido.estado == "lista"))
        self.assertIn("+ AAC", e.etiqueta_estimacion.text())
        destino, aviso = self.exportar(e, "mudo_con_voz.mp4")
        self.assertIn("con el sonido de voz.wav", aviso)
        audio, sr = leer_audio(destino)
        self.assertAlmostEqual(audio.shape[1] / sr, 3.0, delta=0.05)
        self.assertGreater(correlacion(audio, self.senal8[:, :3 * SR]), 0.95)

    def test_un_sonido_que_no_sirve_avisa_y_no_cambia_nada(self):
        from PySide6.QtWidgets import QMessageBox
        e = self.abrir()
        with mock.patch.object(QMessageBox, "warning") as aviso:
            self.assertFalse(e.usar_sonido_externo(str(self.dir / "no_esta.wav"), "original"))
            self.assertFalse(e.usar_sonido_externo(str(self.mudo), "resultado"))
        self.assertEqual(aviso.call_count, 2)
        self.assertIsNone(e.audio_externo)
        self.assertEqual(e._deshacer, [])

    # ------------------------------------------------------------ historial
    def test_deshacer_y_rehacer_el_sonido_externo(self):
        e = self.abrir()
        e.ir_a(1.0)
        e.cortar()
        self.assertTrue(e.usar_sonido_externo(str(self.editado), "original"))
        e.panel_sonido.volumen.slider.setValue(50)
        self.assertEqual(len(e._deshacer), 3)
        self.assertEqual(e._deshacer[-1].externo, V.AudioExterno(str(self.editado), "original"))
        e.volver_al_sonido_original()
        self.assertIsNone(e.audio_externo)
        self.assertAlmostEqual(e.audio.volumen, 0.5)  # el volumen queda: solo cambia de dónde sale
        e.deshacer()
        self.assertEqual(e.audio_externo, V.AudioExterno(str(self.editado), "original"))
        e.deshacer()  # el volumen
        self.assertAlmostEqual(e.audio.volumen, 1.0)
        self.assertIsNotNone(e.audio_externo)
        e.deshacer()  # el sonido externo
        self.assertIsNone(e.audio_externo)
        self.assertEqual(len(e.edicion.segmentos), 2)  # el corte sigue
        self.assertEqual(e.panel_sonido.etiqueta_origen.text(), "Sonido: el del video")
        e.rehacer()
        self.assertEqual(e.audio_externo, V.AudioExterno(str(self.editado), "original"))
        self.assertEqual(e.panel_sonido.etiqueta_origen.text(), "Sonido: editado en el modo Audio")
        self.assertTrue(esperar(self.app, lambda: e.cargador_onda.ruta == str(self.editado)
                                and e.pista_sonido.estado == "lista"))
        # Poner el mismo sonido otra vez no agrega un paso.
        largo = len(e._deshacer)
        e.usar_sonido_externo(str(self.editado), "original")
        self.assertEqual(len(e._deshacer), largo)
        # Con el sonido quitado, poner uno lo devuelve (en el mismo paso).
        e.panel_sonido.interruptor_quitar.setChecked(True)
        e.usar_sonido_externo(str(self.externo8), "resultado")
        self.assertFalse(e.audio.quitar)
        e.deshacer()
        self.assertTrue(e.audio.quitar)
        self.assertEqual(e.audio_externo.ruta, str(self.editado))

    # ------------------------------------------------------------ "Editar el sonido en el modo Audio"
    def test_editar_en_el_modo_audio_emite_un_wav_del_largo_del_original(self):
        e = self.abrir()
        e.ir_a(1.0)
        e.cortar()
        e.linea.seleccionar(0)
        e.borrar_tramo()  # los cortes y los ajustes no van al WAV
        e.panel_sonido.volumen.slider.setValue(30)
        pedidos = []
        e.editarSonidoPedido.connect(lambda wav, video: pedidos.append((wav, video)))
        e.panel_sonido.boton_editar_audio.click()
        self.assertTrue(e.panel_sonido.guardando)
        self.assertTrue(esperar(self.app, lambda: bool(pedidos), 60))
        wav, video = pedidos[0]
        self.assertEqual(video, str(self.video))
        self.assertEqual(Path(wav).parent, Path(os.environ["APPDATA"]) / "NaturalShot PRO" / "temporal")
        self.assertTrue(Path(wav).name.startswith("charla_sonido_") and wav.endswith(".wav"))
        info = A.info_medio(wav)
        self.assertAlmostEqual(info.duracion, 6.0, delta=0.01)
        muestras = leer_wav(Path(wav)).astype(np.float32) / 32768
        original, _ = leer_audio(self.video)
        self.assertEqual(muestras.shape[1], 6 * SR)
        self.assertGreater(correlacion(muestras, original), 0.999)  # sin volumen ni cortes
        self.assertAlmostEqual(rms(muestras[0, SR:2 * SR]), 0.3 / np.sqrt(2), delta=0.01)
        self.assertFalse(e.panel_sonido.guardando)
        self.assertEqual(e.ultimo_sonido_para_audio, wav)
        # Y de vuelta, con los cortes del video: lo que suena es el WAV con el tramo borrado.
        self.assertTrue(e.usar_sonido_externo(wav, "original"))
        self.assertEqual(e.audio_externo.alineado, "original")

    def test_editar_en_el_modo_audio_se_cancela(self):
        e = self.abrir()
        pedidos = []
        e.editarSonidoPedido.connect(lambda wav, video: pedidos.append(wav))
        original = A.exportar_audio

        def lento(*args, **kw):  # cancela apenas empieza a escribir
            e.cancelar_guardado_audio()
            return original(*args, **kw)

        with mock.patch.object(A, "exportar_audio", lento):
            e.editar_sonido_en_audio()
            self.assertTrue(esperar(self.app, lambda: not e.panel_sonido.guardando, 60))
        self.assertEqual(pedidos, [])
        self.assertIn("cancel", e.etiqueta_estado.text().lower())
        carpeta = Path(os.environ["APPDATA"]) / "NaturalShot PRO" / "temporal"
        self.assertFalse([p for p in carpeta.glob("*parcial*")])

    # ------------------------------------------------------------ vista previa
    def test_vista_previa_toca_el_externo(self):
        e = self.abrir()
        e.ir_a(1.0)
        e.cortar()
        e.linea.seleccionar(0)
        e.borrar_tramo()  # queda de 1 a 6 s
        llamadas = {"ruta": [], "lector": []}
        e.reproductor.reproducir = lambda ruta, tramos, ajustes, desde, pico=None: (
            llamadas["ruta"].append((ruta, tramos, desde)) or False)
        e.reproductor.reproducir_lector = lambda lector: llamadas["lector"].append(lector) or False
        e.reproducir()
        e.pausar()
        self.assertEqual(llamadas["ruta"][-1][0], str(self.video))
        e.usar_sonido_externo(str(self.editado), "original")
        e.ir_a(2.0)
        e.reproducir()
        e.pausar()
        ruta, tramos, desde = llamadas["ruta"][-1]
        self.assertEqual(ruta, str(self.editado))       # el externo, con los tramos del video
        self.assertEqual(tramos, [(1.0, 6.0)])
        self.assertAlmostEqual(desde, 2.0, delta=1 / 24)
        e.usar_sonido_externo(str(self.externo8), "resultado")
        e.ir_a(3.0)
        e.reproducir()
        e.pausar()
        self.assertEqual(len(llamadas["lector"]), 1)
        with llamadas["lector"][0]() as lector:  # la función arma el lector de la voz en off
            self.assertIsInstance(lector, V.LectorDesdeCero)
            self.assertEqual(lector.ruta, str(self.externo8))
            self.assertAlmostEqual(lector.duracion_resultado, 5.0, delta=1e-3)
            self.assertAlmostEqual(lector.posicion_resultado, 2.0, delta=1 / 24)  # el 3 del original
            self.assertAlmostEqual(lector.posicion, 3.0, delta=1 / 24)

    def test_pista_con_la_voz_en_off_sigue_a_los_cortes(self):
        e = self.abrir()
        e.usar_sonido_externo(str(self.externo2), "resultado")  # 2 s de voz en un video de 6
        self.assertTrue(esperar(self.app, lambda: e.cargador_onda.ruta == str(self.externo2)
                                and e.pista_sonido.estado == "lista"))
        forma = e.pista_sonido.forma
        self.assertAlmostEqual(forma.duracion, 6.0, delta=0.01)
        n = forma.columnas
        picos = forma.picos()
        self.assertGreater(picos[: int(n * 1.9 / 6)].min(), 0.2)  # la voz, de 0 a 2 s
        self.assertEqual(float(picos[int(n * 2.1 / 6):].max()), 0.0)  # después, silencio
        # Borrar de 0 a 1 s: la voz sigue empezando en el 0 del resultado, que ahora es el 1 del original.
        e.ir_a(1.0)
        e.cortar()
        e.linea.seleccionar(0)
        e.borrar_tramo()
        forma = e.pista_sonido.forma
        picos = forma.picos()
        self.assertEqual(float(picos[: int(n * 0.9 / 6)].max()), 0.0)   # lo borrado
        self.assertGreater(picos[int(n * 1.1 / 6):int(n * 2.9 / 6)].min(), 0.2)
        self.assertEqual(float(picos[int(n * 3.1 / 6):].max()), 0.0)

    # ------------------------------------------------------------ exportar
    def test_exportar_con_original_desde_el_editor(self):
        e = self.abrir()
        e.ir_a(1.5)
        e.cortar()
        e.ir_a(3.0)
        e.cortar()
        e.linea.seleccionar(1)
        e.borrar_tramo()  # quedan 0-1,5 y 3-6
        self.assertTrue(e.usar_sonido_externo(str(self.editado), "original"))
        destino, aviso = self.exportar(e, "editado_original.mp4")
        self.assertIn("con el sonido editado", aviso)
        audio, sr = leer_audio(destino)
        self.assertAlmostEqual(audio.shape[1] / sr, 4.5, delta=0.05)
        esperado = esperado_original(self.senal6, [(0.0, 1.5), (3.0, 6.0)])
        self.assertGreater(correlacion(audio, esperado), 0.95)

    def test_exportar_con_resultado_desde_el_editor(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        e = self.abrir()
        e.ir_a(1.0)
        e.cortar()
        e.ir_a(2.0)
        e.cortar()
        e.linea.seleccionar(1)
        e.borrar_tramo()  # quedan 0-1 y 2-6: 5 s
        with mock.patch.object(QFileDialog, "getOpenFileName", return_value=(str(self.externo8), "")):
            e.cambiar_sonido()
        llamadas = []
        original = V.exportar_video

        def espia(*args, **kw):
            llamadas.append(kw.get("audio_externo"))
            return original(*args, **kw)

        with mock.patch.object(V, "exportar_video", espia):
            destino, aviso = self.exportar(e, "voz_en_off.mp4")
        self.assertEqual(llamadas, [V.AudioExterno(str(self.externo8), "resultado")])
        self.assertIn("con el sonido de voz.wav", aviso)
        audio, sr = leer_audio(destino)
        self.assertAlmostEqual(audio.shape[1] / sr, 5.0, delta=0.05)
        self.assertGreater(correlacion(audio, self.senal8[:, :5 * SR]), 0.95)
        # "Guardar solo el audio" también guarda la voz en off (exacto, en WAV).
        destino_wav = self.dir / "voz_en_off.wav"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino_wav), "WAV")), \
                mock.patch.object(QMessageBox, "information"):
            e.guardar_audio()
            self.assertTrue(esperar(self.app, lambda: not e.panel_sonido.guardando, 60))
        wav = leer_wav(destino_wav)
        self.assertEqual(wav.shape[1], 5 * SR)
        esperado = np.clip(np.round(self.senal8[:, :5 * SR] * 32768), -32768, 32767)
        self.assertLessEqual(int(np.abs(wav[:, :-SR // 100].astype(np.int32) - esperado[:, :-SR // 100]).max()), 1)

    def test_exportar_sin_el_sonido_externo_avisa(self):
        from PySide6.QtWidgets import QMessageBox
        e = self.abrir()
        copia = self.dir / "se_va.wav"
        shutil.copy(self.externo2, copia)
        self.assertTrue(e.usar_sonido_externo(str(copia), "resultado"))
        self.assertTrue(esperar(self.app, lambda: e.pista_sonido.estado == "lista"))
        V.cerrar_lectores()
        copia.unlink()  # borrado por fuera
        with mock.patch.object(QMessageBox, "warning") as aviso:
            e.exportar()
        self.assertFalse(e.exportando)
        self.assertIn("No se encuentra", aviso.call_args.args[2])

    # ------------------------------------------------------------ temporales
    def test_al_abrir_el_editor_se_borran_los_temporales_viejos(self):
        from celular_natural.ui.editor_video import EditorVideo
        carpeta = V.carpeta_temporal()
        carpeta.mkdir(parents=True, exist_ok=True)
        viejo, nuevo = carpeta / "viejo_sonido.wav", carpeta / "nuevo_sonido.wav"
        shutil.copy(self.externo2, viejo)
        shutil.copy(self.externo2, nuevo)
        hace = time.time() - 10 * 86400
        os.utime(viejo, (hace, hace))
        e = EditorVideo()
        self.editores.append(e)
        self.assertFalse(viejo.exists())
        self.assertTrue(nuevo.exists())
        # Uno en uso (sonando) no se borra; si sonara uno que se borra, antes se cierra su lector.
        e2 = self.abrir()
        e2.usar_sonido_externo(str(nuevo), "original")
        os.utime(nuevo, (hace, hace))
        otro = carpeta / "otro_sonido.wav"
        shutil.copy(self.externo2, otro)
        os.utime(otro, (hace, hace))
        lector = mock.Mock(ruta=str(otro))
        e2.reproductor._lector = lector
        e2.reproductor.detener = mock.Mock(side_effect=lambda: setattr(e2.reproductor, "_lector", None))
        borrados = e2.limpiar_temporales()
        self.assertEqual([p.name for p in borrados], ["otro_sonido.wav"])
        e2.reproductor.detener.assert_called_once()
        self.assertTrue(nuevo.exists())


# ---------------------------------------------------------------------------
# La ventana: Video -> Audio -> Video
# ---------------------------------------------------------------------------

@unittest.skipIf(av is None, "Falta PyAV (pip install av==19.0.1)")
class PruebasVentanaIdaYVuelta(unittest.TestCase):
    """El pegamento de ``ventana.py``: "Editar el sonido en el modo Audio" abre el sonido en Audio
    (con los cortes bloqueados) y "Volver al video con este sonido" lo pone en el video."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        cls.dir = Path(tempfile.mkdtemp(prefix="ida_vuelta_ventana_"))
        cls._entorno = {k: os.environ.get(k) for k in ("APPDATA", "NATURALSHOT_CONFIG")}
        os.environ["APPDATA"] = str(cls.dir / "appdata")
        os.environ["NATURALSHOT_CONFIG"] = str(cls.dir / "config.ini")
        cls.video = generar(cls.dir / "charla.mp4", tono(4.0, 440.0))

    @classmethod
    def tearDownClass(cls):
        V.cerrar_lectores()
        for clave, valor in cls._entorno.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_de_video_a_audio_y_de_vuelta(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication, QMessageBox
        from celular_natural.ui.modo_facil import AUDIO, VIDEO
        from celular_natural.ui.ventana import VentanaPrincipal
        v = VentanaPrincipal()
        try:
            v.resize(1366, 768)
            v.show()
            v.abrir_rutas([str(self.video)])
            self.assertEqual(v.modo, VIDEO)
            ev = v.editor_video
            self.assertTrue(esperar(self.app, lambda: ev.info is not None and ev.cuadro_procesado_listo()))
            self.assertTrue(esperar(self.app, lambda: ev.pista_sonido.estado == "lista"))
            # Video -> Audio: el sonido completo del video, con los cortes bloqueados.
            ev.panel_sonido.boton_editar_audio.click()
            self.assertTrue(esperar(self.app, lambda: v.modo == AUDIO, 60))
            ea = v.editor_audio
            self.assertTrue(esperar(self.app, lambda: ea.proyecto is not None))
            self.assertEqual(ea.proyecto.video_origen, str(self.video))
            self.assertTrue(ea.cortes_bloqueados)
            # Audio -> Video: el WAV exportado pasa a ser el sonido del video.
            ea.volver_al_video()
            self.assertTrue(esperar(self.app, lambda: v.modo == VIDEO and ev.audio_externo is not None, 120))
            self.assertEqual(ev.audio_externo.alineado, "original")
            self.assertTrue(Path(ev.audio_externo.ruta).is_file())
            self.assertEqual(Path(ev.audio_externo.ruta).parent,
                             Path(os.environ["APPDATA"]) / "NaturalShot PRO" / "temporal")
        finally:
            with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
                v.close()
            v.deleteLater()
            self.app.processEvents()
            QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_volver_con_otro_video_abierto_no_cambia_nada(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication, QMessageBox
        from celular_natural.ui.modo_facil import VIDEO
        from celular_natural.ui.ventana import VentanaPrincipal
        v = VentanaPrincipal()
        try:
            v.resize(1366, 768)
            v.show()
            v.abrir_rutas([str(self.video)])
            ev = v.editor_video
            self.assertTrue(esperar(self.app, lambda: ev.info is not None))
            v._volver_al_video_con_sonido(str(self.video), str(self.dir / "otro.mp4"))
            self.assertEqual(v.modo, VIDEO)
            self.assertIsNone(ev.audio_externo)
        finally:
            with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
                v.close()
            v.deleteLater()
            self.app.processEvents()
            QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
