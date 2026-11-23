"""Pruebas de la voz natural (``motor/voz_natural.py``).

Todas las señales se generan acá (tonos, ruido, pulsos, armónicos y una "voz"
sintética de armónicos que suben y bajan): nada de archivos del usuario. Casi todas corren
sin la etapa del códec (``codec=False``), así se puede comparar muestra a
muestra; las del códec miden alineación, largo y que no rompa nada.
"""

from __future__ import annotations

import pickle
import sys
import time
import tracemalloc
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from celular_natural.motor.voz_natural import AjustesVoz, CadenaVoz, DESTINOS, LUGARES, PRELECTURA

SR = 48000


def tono(f, s, nivel=0.3):
    t = np.arange(int(SR * s)) / SR
    m = (nivel * np.sin(2 * np.pi * f * t)).astype(np.float32)
    return np.stack([m, m], axis=1)


def ruido(s, nivel=0.1, semilla=0):
    r = np.random.default_rng(semilla).standard_normal(int(SR * s)).astype(np.float32) * nivel
    return np.stack([r, r], axis=1)


F0 = 200            # Hz: fundamental de ``armonicos``
PERIODO = SR // F0  # 240 muestras


def armonicos(s, semilla=0):
    """Armónicos 5 a 25 de 200 Hz (de 1 a 5 kHz), con fases al azar: para medir el retardo de grupo."""
    t = np.arange(int(SR * s)) / SR
    fases = np.random.default_rng(semilla).uniform(0, 2 * np.pi, 26)
    m = sum(np.sin(2 * np.pi * h * F0 * t + fases[h]) for h in range(5, 26))
    m = (0.3 * m / np.abs(m).max()).astype(np.float32)
    return np.stack([m, m], axis=1)


def retardo_de_grupo(a, b):
    """Atraso de ``a`` respecto de ``b`` en muestras (fraccionario): la pendiente de la fase entre armónicos.

    Para ``armonicos``: se ajusta una recta a la diferencia de fase de cada armónico contra la
    frecuencia. La pendiente es el retardo de grupo y la ordenada, una fase constante. Así no
    lo confunde que el códec cambie la fase: SILK (Opus) adelanta la de los tonos entre 5 y 35°,
    unos 7° constantes de 1 a 5 kHz, y eso corría el pico de una correlación de tonos 1 o 2
    muestras sin que hubiera retardo. Tampoco le importa la ganancia (el AGC).
    """
    n = len(a) // PERIODO * PERIODO
    A, B = np.fft.rfft(np.asarray(a[:n], np.float64)), np.fft.rfft(np.asarray(b[:n], np.float64))
    h = np.arange(5, 26)
    cruz = A[h * n // PERIODO] * np.conj(B[h * n // PERIODO])
    fase, peso = np.unwrap(np.angle(cruz)), np.sqrt(np.abs(cruz))
    omega = 2 * np.pi * h * F0 / SR   # radianes por muestra
    _, pendiente = np.linalg.lstsq(np.stack([np.ones_like(omega), omega], 1) * peso[:, None], fase * peso,
                                   rcond=None)[0]
    return -pendiente


def rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(np.asarray(x, np.float64) ** 2)) + 1e-12)


def voz_sintetica(s, nivel=0.3, semilla=0):
    """Armónicos de una fundamental que va y viene (110-190 Hz), en "sílabas" de 4 Hz, con alguna "s" de ruido agudo."""
    n = int(SR * s)
    t = np.arange(n) / SR
    f0 = 150 + 40 * np.sin(2 * np.pi * 0.7 * t)
    fase = 2 * np.pi * np.cumsum(f0) / SR
    m = sum(np.sin(k * fase) / k for k in range(1, 25))
    silabas = np.clip(np.sin(2 * np.pi * 4 * t), 0, None) ** 0.5
    rng = np.random.default_rng(semilla)
    ese = np.fft.irfft(np.fft.rfft(rng.standard_normal(n)) * (np.fft.rfftfreq(n, 1 / SR) > 4500), n)
    ese *= ((t % 1.0) > 0.85)  # una "s" al final de cada segundo
    m = m * silabas + 2.0 * ese
    m = (nivel * m / np.abs(m).max()).astype(np.float32)
    return np.stack([m, m], axis=1)


def procesar_por_bloques(cad, voz, amb, bloque, desde=0):
    partes = [cad.procesar(voz[i:i + bloque], amb[i:i + bloque], i) for i in range(desde, len(voz), bloque)]
    return np.concatenate(partes)


def con_cola(cad, voz, amb, bloque):
    """Bloques + ``vaciar()``: la salida entera, alineada y del mismo largo que la entrada."""
    return np.concatenate([procesar_por_bloques(cad, voz, amb, bloque), cad.vaciar()])


def receta_mezclador(cad, voz, amb, p, bloque):
    """Lo que hace el mezclador al saltar a ``p``: pre-lectura, descartar lo anterior a p y ``vaciar()``."""
    desde = max(0, p - round(PRELECTURA * SR))
    cad.reiniciar(desde)
    partes = []
    for i in range(desde, len(voz), bloque):
        pos = cad.posicion_salida
        partes.append(cad.procesar(voz[i:i + bloque], amb[i:i + bloque], i)[max(0, p - pos):])
    pos = cad.posicion_salida
    partes.append(cad.vaciar()[max(0, p - pos):])
    return np.concatenate(partes)


def banda(x, lo, hi):
    e = np.abs(np.fft.rfft(x[:, 0])) ** 2
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return e[(f >= lo) & (f < hi)].sum() / e.sum()


def energia(x, lo, hi):
    """Energía absoluta (no la fracción) entre ``lo`` y ``hi`` Hz del canal izquierdo."""
    e = np.abs(np.fft.rfft(x[:, 0].astype(np.float64))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return e[(f >= lo) & (f < hi)].sum()


class PruebasVozNatural(unittest.TestCase):
    def test_por_defecto_no_toca(self):
        voz, amb = ruido(2, 0.1, 1), ruido(2, 0.01, 2)
        sal = CadenaVoz(AjustesVoz()).procesar(voz, amb, 0)
        np.testing.assert_allclose(sal, voz + amb, atol=1e-6)

    def test_ajustes_se_acomodan(self):
        a = AjustesVoz().con(cuanto=7, anti_ia=-1, destino="whatsapp")
        self.assertEqual((a.cuanto, a.anti_ia), (1.0, 0.0))
        with self.assertRaises(ValueError):
            AjustesVoz(destino="radio")

    def test_ajustes_nan_lugar_y_sin_cambios(self):
        a = AjustesVoz(cuanto=float("nan"), eco=float("inf"), tapa="mucho", semilla=-3)
        self.assertEqual((a.cuanto, a.eco, a.tapa), (0.6, 0.5, 0.5))
        with self.assertRaises(ValueError):
            AjustesVoz(lugar="playa")
        self.assertTrue(AjustesVoz().sin_cambios())
        self.assertTrue(AjustesVoz(cuanto=1.0, eco=1.0).sin_cambios())
        self.assertFalse(AjustesVoz(anti_ia=0.1).sin_cambios())
        self.assertFalse(AjustesVoz(lugar="auto").sin_cambios())
        self.assertFalse(AjustesVoz(destino="video").sin_cambios())
        # A 0,01: un deslizador no llena las cachés de filtros.
        b = AjustesVoz(cuanto=0.123, anti_ia=0.456, eco=0.789, ruido_propio=0.111, tapa=0.999)
        self.assertEqual((b.cuanto, b.anti_ia, b.eco, b.ruido_propio, b.tapa), (0.12, 0.46, 0.79, 0.11, 1.0))

    def test_pickle(self):
        a = AjustesVoz(destino="auriculares", cuanto=0.9, anti_ia=0.4, lugar="colectivo", eco=0.2,
                       ruido_propio=0.7, compresion=False, tapa=0.8, semilla=12)
        b = pickle.loads(pickle.dumps(a))
        self.assertEqual(a, b)
        self.assertIsInstance(b, AjustesVoz)

    def test_bloques_igual_que_todo(self):
        aj = AjustesVoz(destino="video", lugar="oficina", anti_ia=0.7, cuanto=0.8)
        voz, amb = ruido(3, 0.1, 3), ruido(3, 0.02, 4)
        a = procesar_por_bloques(CadenaVoz(aj, codec=False), voz, amb, len(voz))
        b = procesar_por_bloques(CadenaVoz(aj, codec=False), voz, amb, 2400)
        np.testing.assert_allclose(a, b, atol=1e-5)

    def test_bloques_de_cualquier_tamano(self):
        # Bloques de tamaños raros (que no caen en la grilla de 1 ms ni en las particiones del eco).
        aj = AjustesVoz(destino="auriculares", lugar="calle", anti_ia=1.0, cuanto=1.0, semilla=5)
        voz, amb = voz_sintetica(2, 0.3, 1), ruido(2, 0.02, 2)
        a = CadenaVoz(aj, codec=False).procesar(voz, amb, 0)
        cad = CadenaVoz(aj, codec=False)
        partes, i, rng = [], 0, np.random.default_rng(0)
        while i < len(voz):
            k = int(rng.integers(1, 3000))
            partes.append(cad.procesar(voz[i:i + k], amb[i:i + k], i))
            i += k
        np.testing.assert_allclose(np.concatenate(partes), a, atol=1e-5)

    def test_banda_de_cada_destino(self):
        voz, amb = ruido(4, 0.1, 5), np.zeros((SR * 4, 2), np.float32)
        wa = CadenaVoz(AjustesVoz(destino="whatsapp", cuanto=1.0), codec=False).procesar(voz, amb, 0)
        au = CadenaVoz(AjustesVoz(destino="auriculares", cuanto=1.0), codec=False).procesar(voz, amb, 0)
        vi = CadenaVoz(AjustesVoz(destino="video", cuanto=1.0), codec=False).procesar(voz, amb, 0)
        self.assertLess(banda(wa, 9000, 24000), 0.02)
        self.assertLess(banda(au, 8000, 24000), 0.01)
        self.assertLess(banda(au, 0, 150), 0.02)
        self.assertGreater(banda(vi, 9000, 13000), banda(wa, 9000, 13000))

    def test_cuanto_escala(self):
        # Con menos "cuánto", el micrófono recorta menos la banda: más agudos que con "Fuerte".
        voz, amb = ruido(2, 0.1, 5), np.zeros((SR * 2, 2), np.float32)
        def agudos(cuanto):
            s = CadenaVoz(AjustesVoz(destino="whatsapp", cuanto=cuanto), codec=False).procesar(voz, amb, 0)
            return banda(s, 9000, 24000)
        self.assertGreater(agudos(0.3), agudos(0.6))
        self.assertGreater(agudos(0.6), agudos(0.9))
        # Con cuánto 0 no se graba nada: sale la voz más el ambiente, sin micrófono ni códec.
        s = CadenaVoz(AjustesVoz(destino="whatsapp", cuanto=0.0)).procesar(voz, amb, 0)
        np.testing.assert_allclose(s, voz, atol=1e-6)

    def test_agc_tapa_la_voz(self):
        voz = tono(300, 6, 0.2)
        amb = np.zeros_like(voz)
        amb[SR * 2:SR * 4] = ruido(2, 0.5, 6)   # pasa el colectivo
        def nivel_voz(tapa):
            s = CadenaVoz(AjustesVoz(destino="whatsapp", tapa=tapa, cuanto=1.0), codec=False).procesar(voz, amb, 0)
            seg = slice(SR * 3, SR * 3 + SR // 2)
            ref = voz[seg, 0]
            return abs(np.dot(s[seg, 0], ref) / np.dot(ref, ref))
        self.assertLess(nivel_voz(1.0), nivel_voz(0.0) * 0.7)
        # Con más "tapa", más se tapa.
        self.assertLess(nivel_voz(1.0), nivel_voz(0.5))

    def test_auriculares_bombea_en_las_pausas(self):
        # Voz a ráfagas (0,6 s sí, 0,6 s no) sobre un fondo constante. En auriculares, la reducción de ruido del
        # Bluetooth baja el fondo al rato de cada pausa; en WhatsApp (sin compuerta) el fondo de la pausa no baja
        # (el AGC hasta lo sube un poco).
        n = SR * 6
        t = np.arange(n) / SR
        m = (0.2 * np.sin(2 * np.pi * 1000 * t) * ((t % 1.2) < 0.6)).astype(np.float32)
        voz = np.stack([m, m], axis=1)
        r = np.random.default_rng(3).standard_normal(n)
        f = np.fft.rfftfreq(n, 1 / SR)
        r = np.fft.irfft(np.fft.rfft(r) * ((f > 500) & (f < 3000)), n)
        r = (0.01 * r / r.std()).astype(np.float32)
        amb = np.stack([r, r], axis=1)
        def caida(destino):
            s = CadenaVoz(AjustesVoz(destino=destino, cuanto=1.0), codec=False).procesar(voz, amb, 0)[:, 0]
            def rms(a, b):
                return np.sqrt(np.mean(np.concatenate([s[int((c + a) * SR):int((c + b) * SR)]
                                                       for c in (1.2, 2.4, 3.6, 4.8)]) ** 2))
            return rms(1.05, 1.15) / rms(0.62, 0.66)   # final de la pausa / recién empezada
        self.assertLess(caida("auriculares"), 0.5)
        self.assertGreater(caida("whatsapp"), 0.8)

    def test_eco_alarga_la_cola(self):
        voz = np.zeros((SR * 2, 2), np.float32)
        voz[1000:1100] = 0.5
        amb = np.zeros_like(voz)
        seco = CadenaVoz(AjustesVoz(lugar="ninguno", destino="video"), codec=False).procesar(voz, amb, 0)
        mojado = CadenaVoz(AjustesVoz(lugar="habitacion", destino="video", eco=1.0, cuanto=1.0), codec=False).procesar(voz, amb, 0)
        cola = slice(1100 + int(0.05 * SR), 1100 + int(0.3 * SR))
        self.assertGreater(np.abs(mojado[cola]).mean(), 5 * np.abs(seco[cola]).mean() + 1e-6)

    def test_cada_lugar_tiene_su_cola(self):
        # Cada lugar deja una cola que decae; el auto y el exterior, la más corta o la más baja.
        voz = np.zeros((SR, 2), np.float32)
        voz[1000:1100] = 0.5
        amb = np.zeros_like(voz)
        colas = {}
        for lugar in LUGARES[1:]:
            s = CadenaVoz(AjustesVoz(lugar=lugar, eco=1.0, cuanto=1.0), codec=False).procesar(voz, amb, 0)
            self.assertTrue(np.isfinite(s).all(), lugar)
            colas[lugar] = np.abs(s[1100 + int(0.03 * SR):1100 + int(0.2 * SR), 0]).mean()
            tarde = np.abs(s[1100 + int(0.45 * SR):, 0]).max()
            self.assertLess(tarde, 1e-6, lugar)   # la respuesta dura menos que la pre-lectura de 0,5 s
        self.assertGreater(colas["oficina"], colas["auto"])
        self.assertGreater(colas["habitacion"], colas["exterior"])
        self.assertGreater(colas["calle"], colas["exterior"])

    def test_anti_ia_no_cambia_el_tono(self):
        voz = tono(220, 3)
        s = CadenaVoz(AjustesVoz(anti_ia=1.0), codec=False).procesar(voz, np.zeros_like(voz), 0)
        f = np.fft.rfftfreq(len(s), 1 / SR)
        self.assertAlmostEqual(f[np.argmax(np.abs(np.fft.rfft(s[:, 0])))], 220, delta=1.0)
        env = np.sqrt(np.convolve(s[:, 0] ** 2, np.ones(4800) / 4800, mode="valid"))
        variacion = 20 * np.log10(env.max() / env.min())
        self.assertTrue(0.5 < variacion < 4.5, variacion)

    def test_anti_ia_suaviza_las_eses(self):
        # Una "s" fuerte (ruido de 5 a 9 kHz) sobre una vocal: el de-esser le baja la banda.
        n = SR * 2
        f = np.fft.rfftfreq(n, 1 / SR)
        r = np.random.default_rng(4).standard_normal(n)
        ese = np.fft.irfft(np.fft.rfft(r) * ((f > 5500) & (f < 8500)), n)
        ese = 0.2 * ese / ese.std()
        vocal = 0.05 * np.sin(2 * np.pi * 200 * np.arange(n) / SR)
        m = (vocal + ese).astype(np.float32)
        voz = np.stack([m, m], axis=1)
        s = CadenaVoz(AjustesVoz(anti_ia=1.0), codec=False).procesar(voz, np.zeros_like(voz), 0)
        # Energía absoluta: la "s" es casi toda la señal, así que su fracción del total casi no cambia.
        self.assertLess(energia(s, 5500, 8500) / energia(voz, 5500, 8500), 0.6)   # unos -2 dB o más
        # La vocal (200 Hz) no se toca: el de-esser solo actúa sobre la banda (y el volumen lento, ±1,5 dB).
        self.assertGreater(energia(s, 150, 250) / energia(voz, 150, 250), 10 ** (-3.5 / 10))

    def test_salto_es_determinista(self):
        aj = AjustesVoz(destino="whatsapp", anti_ia=0.8, lugar="calle")
        voz, amb = ruido(4, 0.1, 7), ruido(4, 0.02, 8)
        todo = CadenaVoz(aj, codec=False).procesar(voz, amb, 0)
        cad = CadenaVoz(aj, codec=False)
        cad.reiniciar(SR * 2 - SR // 2)   # pre-lectura de 0,5 s
        cad.procesar(voz[SR * 2 - SR // 2:SR * 2], amb[SR * 2 - SR // 2:SR * 2], SR * 2 - SR // 2)
        parte = cad.procesar(voz[SR * 2:SR * 3], amb[SR * 2:SR * 3], SR * 2)
        np.testing.assert_allclose(parte, todo[SR * 2:SR * 3], atol=2e-3)

    def test_inicio_salteado_reinicia_solo(self):
        # Si el bloque no sigue al anterior, la cadena se reinicia sola en ese punto (como reiniciar a mano).
        aj = AjustesVoz(destino="video", lugar="oficina", anti_ia=0.5)
        voz, amb = ruido(2, 0.1, 1), ruido(2, 0.02, 2)
        a = CadenaVoz(aj, codec=False)
        a.procesar(voz[:SR // 2], amb[:SR // 2], 0)
        sola = a.procesar(voz[SR:], amb[SR:], SR)
        b = CadenaVoz(aj, codec=False)
        b.reiniciar(SR)
        np.testing.assert_allclose(sola, b.procesar(voz[SR:], amb[SR:], SR), atol=1e-6)

    def test_bloque_vacio_y_entradas_invalidas(self):
        aj = AjustesVoz(destino="whatsapp", anti_ia=0.5, lugar="auto")
        cad = CadenaVoz(aj)
        vacio = np.zeros((0, 2), np.float32)
        self.assertEqual(cad.procesar(vacio, vacio, 0).shape, (0, 2))
        voz = ruido(0.5, 0.1, 1)
        self.assertEqual(len(cad.procesar(voz, voz, 0)), len(voz) - cad.latencia)   # sigue de corrido
        with self.assertRaises(ValueError):
            cad.procesar(voz, voz, -10)
        with self.assertRaises(ValueError):
            cad.procesar(voz[:, 0], voz[:, 0], 0)   # mono: tiene que ser (n, 2)
        with self.assertRaises(ValueError):
            cad.procesar(voz, voz[:100], 0)
        with self.assertRaises(ValueError):   # tiene que ser float
            cad.procesar((voz * 32767).astype(np.int16), (voz * 32767).astype(np.int16), 0)

    def test_codec_solo_a_48_khz(self):
        # Las latencias del códec están medidas a 48 kHz: con otra frecuencia, el códec no se arma.
        with self.assertRaises(ValueError):
            CadenaVoz(AjustesVoz(destino="whatsapp"), frecuencia=44100)
        sin_codec = CadenaVoz(AjustesVoz(destino="whatsapp"), frecuencia=44100, codec=False)
        self.assertEqual(sin_codec.latencia, 0)
        voz = ruido(0.2, 0.1, 1)
        self.assertEqual(sin_codec.procesar(voz, voz, 0).shape, voz.shape)
        CadenaVoz(AjustesVoz(destino="whatsapp", compresion=False), frecuencia=44100)   # sin compresión, sí

    def test_entrada_con_nan_e_infinito(self):
        # Una sola muestra NaN o infinita envenenaba la cadena para siempre (el AGC quedaba en NaN, Opus en
        # silencio y AAC fallaba). Ahora se limpia: la salida sigue finita y con el nivel de siempre.
        voz, amb = voz_sintetica(2, 0.3, 1), ruido(2, 0.01, 2)
        sucia, amb_sucio = voz.copy(), amb.copy()
        sucia[SR // 2, 0] = np.nan
        sucia[SR // 2 + 100, 1] = np.inf
        amb_sucio[SR, 0] = -np.inf
        for destino in DESTINOS:
            for codec in (False, True):
                with self.subTest(destino=destino, codec=codec):
                    aj = AjustesVoz(destino=destino, anti_ia=0.5, lugar="habitacion")
                    limpia = con_cola(CadenaVoz(aj, codec=codec), voz, amb, 2400)
                    s = con_cola(CadenaVoz(aj, codec=codec), sucia, amb_sucio, 2400)
                    self.assertEqual(s.shape, voz.shape)
                    self.assertTrue(np.isfinite(s).all())
                    self.assertAlmostEqual(rms_db(s[-SR // 2:]), rms_db(limpia[-SR // 2:]), delta=1.0)
        s = CadenaVoz(AjustesVoz()).procesar(sucia, amb_sucio, 0)   # también sin cambios
        self.assertTrue(np.isfinite(s).all())

    def test_bloque_enorme_no_explota_la_memoria(self):
        # 20 s en una sola llamada: por dentro va de a trozos, así que da lo mismo que en bloques y la memoria no
        # crece con el bloque (antes, una sola FFT del bloque entero: unos 270 MB para 20 s y 834 MB para 60 s).
        aj = AjustesVoz(destino="video", lugar="oficina", anti_ia=0.5, cuanto=0.8)
        voz, amb = ruido(20, 0.1, 3), ruido(20, 0.02, 4)
        tracemalloc.start()
        try:
            entero = CadenaVoz(aj, codec=False).procesar(voz, amb, 0)
            _, pico = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(pico, 150 * 2 ** 20)   # la salida (8 MB) y los trozos, no cientos de MB
        np.testing.assert_allclose(entero, procesar_por_bloques(CadenaVoz(aj, codec=False), voz, amb, 2400),
                                   atol=1e-5)

    def test_excepcion_a_mitad_reinicia(self):
        # Si algo falla a mitad de procesar, las etapas anteriores ya avanzaron: la próxima llamada tiene que
        # arrancar de cero aunque repita el mismo inicio.
        aj = AjustesVoz(destino="whatsapp", anti_ia=0.7, lugar="oficina")
        voz, amb = ruido(1, 0.1, 1), ruido(1, 0.02, 2)
        cad = CadenaVoz(aj, codec=False)
        def falla(x, inicio):
            raise RuntimeError("falla de prueba")
        cad._volumen.procesar = falla
        with self.assertRaises(RuntimeError):
            cad.procesar(voz, amb, 0)
        del cad._volumen.procesar   # vuelve el método de la clase
        np.testing.assert_array_equal(cad.procesar(voz, amb, 0), CadenaVoz(aj, codec=False).procesar(voz, amb, 0))
        # Y si después del error sigue con el bloque siguiente, también arranca de cero ahí.
        cad._volumen.procesar = falla
        with self.assertRaises(RuntimeError):
            cad.procesar(voz[:2400], amb[:2400], len(voz))
        del cad._volumen.procesar
        nueva = CadenaVoz(aj, codec=False)
        nueva.reiniciar(len(voz) + 2400)
        np.testing.assert_array_equal(cad.procesar(voz, amb, len(voz) + 2400), nueva.procesar(voz, amb, len(voz) + 2400))

    def test_nivel_del_ruido_propio(self):
        # Sobre silencio sale solo el ruido del micrófono: -62 dBFS × ruido_propio × cuanto; con 0, nada.
        cero = np.zeros((SR * 2, 2), np.float32)
        for destino in DESTINOS[1:]:
            with self.subTest(destino=destino):
                s = CadenaVoz(AjustesVoz(destino=destino, cuanto=0.8, ruido_propio=0.5), codec=False).procesar(cero, cero, 0)
                esperado = -62 + 20 * np.log10(0.5 * 0.8)
                self.assertAlmostEqual(rms_db(s[:, 0]), esperado, delta=1.0)
                s = CadenaVoz(AjustesVoz(destino=destino, ruido_propio=0.0), codec=False).procesar(cero, cero, 0)
                self.assertFalse(np.any(s))

    def test_estereo_segun_el_destino(self):
        # El video graba con dos micrófonos (izquierda y derecha distintas); WhatsApp y auriculares, con uno.
        r = np.random.default_rng(5).standard_normal((SR, 2)).astype(np.float32) * 0.1   # L y R distintos
        amb = np.zeros_like(r)
        for destino in DESTINOS[1:]:
            for codec in (False, True):
                with self.subTest(destino=destino, codec=codec):
                    s = con_cola(CadenaVoz(AjustesVoz(destino=destino), codec=codec), r, amb, 2400)
                    if destino == "video":
                        self.assertGreater(np.abs(s[:, 0] - s[:, 1]).max(), 1e-3)
                    else:
                        np.testing.assert_array_equal(s[:, 0], s[:, 1])

    def test_codec_redondea_y_compensa_latencia(self):
        aj = AjustesVoz(destino="whatsapp", cuanto=1.0)
        voz, amb = tono(440, 3), np.zeros((SR * 3, 2), np.float32)
        # Con el códec, el primer bloque sale ``latencia`` muestras más corto y ``vaciar()`` entrega las últimas:
        # sin ``vaciar()`` las dos salidas no tendrían el mismo largo (ver "Latencia" en voz_natural.py).
        con = con_cola(CadenaVoz(aj, codec=True), voz, amb, 2400)
        sin = procesar_por_bloques(CadenaVoz(aj, codec=False), voz, amb, 2400)
        self.assertEqual(con.shape, sin.shape)
        # Alineados (latencia compensada): alta correlación, pero no idénticos.
        c = np.corrcoef(con[SR // 2:-SR // 2, 0], sin[SR // 2:-SR // 2, 0])[0, 1]
        self.assertGreater(c, 0.9)
        self.assertGreater(np.abs(con - sin).max(), 1e-3)

    def test_codec_cada_destino(self):
        # Fuerte a propósito (picos cerca de 1 más un fondo que pasa): que no rompa ni sature, y que siga
        # pareciéndose a la versión sin códec.
        voz = voz_sintetica(3, 0.9, 2)
        amb = ruido(3, 0.05, 3)
        amb[SR:SR * 2] *= 8
        for destino in DESTINOS[1:]:
            with self.subTest(destino=destino):
                aj = AjustesVoz(destino=destino, cuanto=1.0, lugar="habitacion", anti_ia=0.5)
                cad = CadenaVoz(aj, codec=True)
                self.assertGreater(cad.latencia, 0)
                con = con_cola(cad, voz, amb, 1999)
                self.assertEqual(con.shape, voz.shape)
                self.assertEqual(con.dtype, np.float32)
                self.assertTrue(np.isfinite(con).all())
                self.assertLessEqual(np.abs(con).max(), 1.0)
                # La alineación la miden test_receta_del_mezclador_con_codec y test_codec_bloques_de_1_a_7_muestras,
                # con el retardo de grupo: con esta voz, el pico de la correlación lo corre la fase que SILK le
                # cambia a los tonos (entre 5 y 35°), no un retardo.
                sin = CadenaVoz(aj, codec=False).procesar(voz, amb, 0)
                self.assertGreater(np.corrcoef(con[SR // 10:, 0], sin[SR // 10:, 0])[0, 1], 0.5)

    def test_vaciar_da_el_largo_exacto(self):
        aj = AjustesVoz(destino="video", cuanto=0.6)
        cad = CadenaVoz(aj)
        voz, amb = ruido(1, 0.1, 1), ruido(1, 0.01, 2)
        primero = cad.procesar(voz[:777], amb[:777], 0)
        self.assertEqual(len(primero), max(0, 777 - cad.latencia))
        self.assertEqual(cad.posicion_salida, len(primero))
        resto = procesar_por_bloques(cad, voz, amb, 1234, desde=777)
        cola = cad.vaciar()
        self.assertEqual(len(cola), cad.latencia)
        self.assertEqual(len(primero) + len(resto) + len(cola), len(voz))
        self.assertEqual(cad.posicion_salida, len(voz))
        # Sin códec no hay latencia ni cola.
        sin = CadenaVoz(aj, codec=False)
        self.assertEqual(sin.latencia, 0)
        self.assertEqual(len(sin.procesar(voz, amb, 0)), len(voz))
        self.assertEqual(sin.vaciar().shape, (0, 2))

    def test_seguir_despues_de_vaciar(self):
        # Después de vaciar(), la cadena queda como recién reiniciada al final: se puede seguir.
        aj = AjustesVoz(destino="whatsapp", anti_ia=0.5, lugar="auto")
        voz, amb = voz_sintetica(2, 0.3, 1), ruido(2, 0.01, 2)
        corte = SR - 333
        for codec in (False, True):
            with self.subTest(codec=codec):
                cad = CadenaVoz(aj, codec=codec)
                primera = con_cola(cad, voz[:corte], amb[:corte], 2400)
                self.assertEqual(len(primera), corte)
                self.assertEqual(cad.posicion_salida, corte)
                segunda = np.concatenate([procesar_por_bloques(cad, voz, amb, 2400, desde=corte), cad.vaciar()])
                self.assertEqual(len(segunda), len(voz) - corte)
                nueva = CadenaVoz(aj, codec=codec)
                nueva.reiniciar(corte)
                esperada = np.concatenate([procesar_por_bloques(nueva, voz, amb, 2400, desde=corte), nueva.vaciar()])
                np.testing.assert_array_equal(segunda, esperada)

    def test_receta_del_mezclador_con_codec(self):
        # Saltar a p: reiniciar(p - pre), pre-lectura, descartar según posicion_salida y vaciar() al final.
        # Sale exactamente de p al final y alineado con la versión sin códec: retardo de grupo de ±0,5 muestras
        # como mucho (medido: Opus entre -0,13 y +0,22 en 16 variantes, AAC ±0,003; un error de latencia daría
        # cientos o miles de muestras).
        voz, amb = armonicos(3), ruido(3, 0.005, 2)
        p = SR + 7777
        for destino in DESTINOS[1:]:
            with self.subTest(destino=destino):
                aj = AjustesVoz(destino=destino, cuanto=1.0, lugar="habitacion")
                s = receta_mezclador(CadenaVoz(aj), voz, amb, p, 2400)
                self.assertEqual(s.shape, (len(voz) - p, 2))
                sin = CadenaVoz(aj, codec=False).procesar(voz, amb, 0)[p:]
                self.assertLess(abs(retardo_de_grupo(s[SR // 10:, 0], sin[SR // 10:, 0])), 0.5)
                self.assertGreater(np.corrcoef(s[SR // 10:, 0], sin[SR // 10:, 0])[0, 1], 0.8)

    def test_codec_bloques_de_1_a_7_muestras(self):
        # Bloques diminutos: el peor caso para la cola del códec. Si una versión nueva de PyAV o de libopus
        # entregara más tarde que la latencia medida, esta prueba avisa (faltaron > 0). Los primeros 0,3 s van de
        # a 1 a 7 muestras (más de 10 cuadros del códec: el patrón se repite); el resto, en bloques de 50 ms (el
        # códec es determinista: la salida es la misma), así se mide la alineación sobre 1,4 s.
        voz = armonicos(1.5)
        amb = np.zeros_like(voz)
        for destino in DESTINOS[1:]:
            with self.subTest(destino=destino):
                aj = AjustesVoz(destino=destino, cuanto=1.0, ruido_propio=0.0)
                cad = CadenaVoz(aj)
                partes, i, k = [], 0, 0
                while i < len(voz):
                    b = 1 + k % 7 if i < int(0.3 * SR) else 2400
                    partes.append(cad.procesar(voz[i:i + b], amb[i:i + b], i))
                    i, k = i + b, k + 1
                partes.append(cad.vaciar())
                s = np.concatenate(partes)
                self.assertEqual(s.shape, voz.shape)
                self.assertEqual(cad._codec.faltaron, 0)   # la latencia alcanzó siempre
                sin = CadenaVoz(aj, codec=False).procesar(voz, amb, 0)
                self.assertLess(abs(retardo_de_grupo(s[SR // 10:, 0], sin[SR // 10:, 0])), 0.5)

    def test_codec_bloques_igual_que_todo(self):
        # El códec ve los mismos cuadros sea cual sea el tamaño de los bloques: la diferencia queda debajo de -60 dB.
        voz, amb = voz_sintetica(5, 0.5, 4), ruido(5, 0.02, 5)
        for destino in DESTINOS[1:]:
            with self.subTest(destino=destino):
                aj = AjustesVoz(destino=destino, cuanto=0.8, anti_ia=0.5, lugar="oficina")
                a = con_cola(CadenaVoz(aj), voz, amb, len(voz))
                b = con_cola(CadenaVoz(aj), voz, amb, 1111)
                self.assertLess(np.sqrt(np.mean((a - b) ** 2)), 1e-3 * np.sqrt(np.mean(a ** 2)))

    def test_velocidad(self):
        aj = AjustesVoz(destino="whatsapp", lugar="calle", anti_ia=1.0, cuanto=1.0)
        voz, amb = ruido(10, 0.1, 9), ruido(10, 0.02, 10)
        cad = CadenaVoz(aj)
        t = time.perf_counter()
        procesar_por_bloques(cad, voz, amb, 2400)
        self.assertLess(time.perf_counter() - t, 10 / 8)   # >= 8 veces el tiempo real


if __name__ == "__main__":
    unittest.main()
