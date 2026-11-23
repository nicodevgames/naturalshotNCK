"""Pruebas de la biblioteca generada del modo Audio (``motor/ambientes.py``).

Todo se sintetiza acá mismo: fondos continuos (lluvia, calle, colectivo…) y
sonidos sueltos (colectivo que pasa, bocina…). Se mide lo que se puede medir
de un sonido sin escucharlo: acceso aleatorio exacto, determinismo (también
entre procesos y con varios hilos), nivel, espectro, que no haya loop, el
Doppler, la memoria y la velocidad.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import threading
import time
import tracemalloc
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from celular_natural.motor import ambientes as am  # noqa: E402


def rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(np.square(x, dtype=np.float64))) + 1e-12)


def energia_banda(x, lo, hi, sr=48000):
    m = x.mean(axis=1)
    e = np.abs(np.fft.rfft(m)) ** 2
    f = np.fft.rfftfreq(len(m), 1 / sr)
    return e[(f >= lo) & (f < hi)].sum() / e.sum()


def log_espectro(s, f):
    e = np.abs(np.fft.rfft(s * np.hanning(len(s))))
    l = np.log(np.interp(f, np.fft.rfftfreq(len(s), 1 / 48000), e) + 1e-12)
    return l - l.mean()


def corrimiento(a, d):
    """Factor de frecuencia que mejor alinea el espectro de ``d`` con el de ``a`` (escala log, 50 Hz a 1,5 kHz)."""
    f = np.geomspace(50.0, 1500.0, 800)
    la, ld = log_espectro(a, f), log_espectro(d, f)

    def parecido(k):
        u, v = (la[k:], ld[:len(ld) - k]) if k >= 0 else (la[:k], ld[-k:])
        u, v = u - u.mean(), v - v.mean()
        return np.dot(u, v) / np.sqrt(np.dot(u, u) * np.dot(v, v))

    return float((f[1] / f[0]) ** max(range(-60, 61), key=parecido))


def pasada_del_colectivo(semilla):
    """(señal mono, envolvente, índice del pico, corrimiento de frecuencia antes/después del pico)."""
    x = am.generar_sonido("colectivo_pasa", semilla=semilla).mean(axis=1)
    env = np.sqrt(np.convolve(x ** 2, np.ones(4800) / 4800, mode="same"))
    i = int(np.argmax(env))
    return x, env, i, corrimiento(x[max(0, i - 48000):i - 12000], x[i + 12000:i + 48000])


def huella(clave, semilla):
    """Hash del audio de un fondo y de un sonido suelto (para comparar entre procesos)."""
    h = hashlib.sha256()
    h.update(am.GeneradorFondo(clave, 0.7, semilla=semilla).leer(48000 * 2, 48000).tobytes())
    h.update(am.generar_sonido("bocina", semilla).tobytes())
    return h.hexdigest()


class PruebasFondos(unittest.TestCase):
    def test_catalogo(self):
        for clave in ("ciudad", "calle", "lluvia", "agua", "olas", "viento", "oficina", "habitacion",
                      "auto", "colectivo", "viento_mic"):
            self.assertIn(clave, am.FONDOS)
            self.assertTrue(am.FONDOS[clave].nombre)

    def test_acceso_aleatorio_exacto(self):
        for clave in am.FONDOS:
            g = am.GeneradorFondo(clave, 0.5, semilla=7)
            todo = g.leer(0, 48000 * 6)
            for inicio, n in ((0, 1000), (47_999, 2), (48000 * 2 + 123, 30_000), (48000 * 5, 48000)):
                np.testing.assert_allclose(am.GeneradorFondo(clave, 0.5, semilla=7).leer(inicio, n),
                                           todo[inicio:inicio + n], atol=1e-6, err_msg=clave)

    def test_forma_y_tipo(self):
        x = am.GeneradorFondo("lluvia").leer(0, 4800)
        self.assertEqual(x.shape, (4800, 2))
        self.assertEqual(x.dtype, np.float32)

    def test_semillas_distintas_dan_distinto(self):
        a = am.GeneradorFondo("calle", semilla=1).leer(0, 48000)
        b = am.GeneradorFondo("calle", semilla=2).leer(0, 48000)
        self.assertGreater(np.abs(a - b).mean(), 1e-4)

    def test_nivel_calibrado_y_sin_saturar(self):
        for clave in am.FONDOS:
            x = am.GeneradorFondo(clave, 0.5, semilla=3).leer(0, 48000 * 10)
            self.assertTrue(np.isfinite(x).all(), clave)
            self.assertLess(np.abs(x).max(), 0.99, clave)
            self.assertAlmostEqual(rms_db(x), am.NIVEL_FONDO_DBFS, delta=4.0, msg=clave)

    def test_intensidad_cambia_el_nivel(self):
        for clave, info in am.FONDOS.items():
            if info.intensidad:
                poco = rms_db(am.GeneradorFondo(clave, 0.1).leer(0, 48000 * 8))
                mucho = rms_db(am.GeneradorFondo(clave, 0.9).leer(0, 48000 * 8))
                self.assertGreater(mucho, poco + 3, clave)

    def test_espectros_esperables(self):
        lluvia = am.GeneradorFondo("lluvia", 0.6).leer(0, 48000 * 4)
        colectivo = am.GeneradorFondo("colectivo", 0.6).leer(0, 48000 * 4)
        self.assertGreater(energia_banda(lluvia, 2000, 12000), 0.3)
        self.assertGreater(energia_banda(colectivo, 20, 300), 0.4)

    def test_sin_loop_audible(self):
        # Dos ventanas de 2 s separadas 30 s no se parecen (correlación baja).
        x = am.GeneradorFondo("agua", semilla=5).leer(0, 48000 * 34)[:, 0]
        a, b = x[:96000], x[48000 * 30:48000 * 32]
        c = np.corrcoef(a, b)[0, 1]
        self.assertLess(abs(c), 0.2)

    def test_velocidad(self):
        # Al menos 20 veces el tiempo real: 10 s en menos de 0,5 s, también a intensidad 1 (más
        # tránsito, más olas) y con otra semilla. Para cada caso vale la mejor de 2 corridas, cada
        # una con un generador nuevo: una sola mide también la carga que tenga la compu en ese
        # momento (otras pruebas, otros programas), y eso no es del generador.
        def medir(clave, intensidad, semilla):
            g = am.GeneradorFondo(clave, intensidad, semilla=semilla)
            t = time.perf_counter()
            g.leer(48000 * 3, 48000 * 10)
            return time.perf_counter() - t

        for clave in am.FONDOS:
            for intensidad, semilla in ((0.5, 0), (1.0, 0), (1.0, 1)):
                mejor = min(medir(clave, intensidad, semilla) for _ in range(2))
                self.assertLess(mejor, 0.5, f"{clave}, intensidad {intensidad}, semilla {semilla}")

    def test_memoria(self):
        # Los vehículos que pasan se guardan en float32 a 24 kHz (menos de 1 MB cada uno) en una
        # caché chica que olvida los que ya pasaron: leyendo de corrido, un generador no crece.
        for clave in ("calle", "ciudad"):
            tracemalloc.start()
            try:
                g = am.GeneradorFondo(clave, 1.0, semilla=1)
                for inicio in range(0, 48000 * 60, 4800):
                    g.leer(inicio, 4800)
                retenida = tracemalloc.get_traced_memory()[0]
            finally:
                tracemalloc.stop()
            self.assertLess(retenida / 1e6, 16.0, clave)


class PruebasSonidos(unittest.TestCase):
    def test_catalogo_y_pico(self):
        for clave in ("colectivo_pasa", "auto_pasa", "moto_pasa", "frenada_colectivo", "bocina", "sirena_lejos"):
            x = am.generar_sonido(clave, semilla=1)
            self.assertEqual(x.ndim, 2)
            self.assertEqual(x.shape[1], 2)
            pico = 20 * np.log10(np.abs(x).max())
            self.assertAlmostEqual(pico, am.PICO_SONIDO_DBFS, delta=1.0, msg=clave)
            self.assertAlmostEqual(len(x) / 48000, am.SONIDOS[clave].duracion,
                                   delta=am.SONIDOS[clave].duracion * 0.5)

    def test_determinista(self):
        np.testing.assert_array_equal(am.generar_sonido("auto_pasa", 4), am.generar_sonido("auto_pasa", 4))

    def test_colectivo_sube_y_baja_con_doppler(self):
        x, env, i, con = pasada_del_colectivo(2)
        self.assertTrue(0.2 * len(x) < i < 0.8 * len(x))
        self.assertGreater(env[i], 4 * env[2400])
        self.assertGreater(env[i], 4 * env[-2400])

        # Doppler: la frecuencia baja después del pico.
        #
        # El plan medía el centroide espectral (en magnitud, hasta 1,5 kHz). Con un colectivo
        # bien hecho no sirve: el ruido de los neumáticos y el golpeteo del diésel son de banda
        # ancha y, cortados en 1,5 kHz y pesados por magnitud, su centroide casi no cambia
        # cuando el espectro se corre (medido en 16 pasadas: 0,994 con Doppler y 0,996 sin
        # Doppler; en 20 semillas daba entre 0,83 y 1,14, según la suerte). Ese ruido tapa el
        # corrimiento de los armónicos del motor (en la semilla 2, de 94 a 83 Hz). Se mide
        # entonces el corrimiento de frecuencia mismo, que es lo que pide el diseño ("la
        # frecuencia dominante baja"): el factor que mejor alinea los dos espectros en una escala
        # logarítmica de frecuencia, de 50 Hz a 1,5 kHz.
        #
        # Este colectivo además frena para la parada, y eso solo ya baja las rpm un 5 o 6 %. Para
        # aislar el Doppler, la misma pasada se arma también con el sonido casi instantáneo
        # (velocidad del sonido enorme: sin Doppler) y se pide que con Doppler baje al menos un
        # 3 % más (en la semilla 2: 1,08; en 30 semillas, con solo el Doppler, 1,05 o más).
        self.assertGreater(con, 1.05)
        am.generar_sonido.cache_clear()
        try:
            with mock.patch.object(am, "_C", 1e7):
                sin = pasada_del_colectivo(2)[3]
        finally:
            am.generar_sonido.cache_clear()
        self.assertGreater(con / sin, 1.03)

    def test_velocidad(self):
        am.generar_sonido.cache_clear()
        for clave in am.SONIDOS:
            t = time.perf_counter()
            am.generar_sonido(clave, semilla=99)
            self.assertLess(time.perf_counter() - t, 0.5, clave)

    def test_de_solo_lectura_y_una_sola_entrada(self):
        x = am.generar_sonido("bocina", 2)
        self.assertFalse(x.flags.writeable)
        with self.assertRaises(ValueError):
            x[0, 0] = 1.0
        # Con nombre o sin nombre, el mismo sonido sale de la misma entrada de la caché.
        self.assertIs(am.generar_sonido("bocina", 2), am.generar_sonido("bocina", semilla=2))


class PruebasRobustez(unittest.TestCase):
    def test_determinismo_entre_procesos(self):
        # El azar sale de un hash estable: otro proceso, con otro PYTHONHASHSEED, da los mismos bytes.
        esperado = huella("calle", 5)
        codigo = (f"import sys; sys.path.insert(0, {str(RAIZ)!r}); "
                  "from tests.test_ambientes import huella; print(huella('calle', 5))")
        for semilla_hash in ("1", "987654"):
            entorno = dict(os.environ, PYTHONHASHSEED=semilla_hash)
            r = subprocess.run([sys.executable, "-c", codigo], env=entorno, cwd=str(RAIZ), capture_output=True,
                               text=True, timeout=300)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip().splitlines()[-1], esperado)

    def test_un_generador_desde_dos_hilos(self):
        referencia = am.GeneradorFondo("lluvia", 0.5, semilla=4).leer(0, 48000 * 3)
        g = am.GeneradorFondo("lluvia", 0.5, semilla=4)
        bloque = 9000
        partes = {}

        def leer(pares):
            for i in range(pares, 16, 2):
                partes[i] = g.leer(i * bloque, bloque)

        hilos = [threading.Thread(target=leer, args=(j,)) for j in (0, 1)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        np.testing.assert_array_equal(np.concatenate([partes[i] for i in range(16)]), referencia)

    def test_otra_frecuencia(self):
        fr = 44100
        for clave in ("calle", "olas", "oficina"):
            todo = am.GeneradorFondo(clave, 0.5, semilla=2, frecuencia=fr).leer(0, fr * 3)
            self.assertEqual(todo.shape, (fr * 3, 2))
            self.assertTrue(np.isfinite(todo).all(), clave)
            parte = am.GeneradorFondo(clave, 0.5, semilla=2, frecuencia=fr).leer(fr + 77, 5000)
            np.testing.assert_array_equal(parte, todo[fr + 77:fr + 5077], err_msg=clave)
        x = am.generar_sonido("auto_pasa", 1, fr)
        self.assertAlmostEqual(len(x) / fr, am.SONIDOS["auto_pasa"].duracion, delta=0.5)
        self.assertAlmostEqual(20 * np.log10(np.abs(x).max()), am.PICO_SONIDO_DBFS, delta=0.1)

    def test_errores_claros(self):
        with self.assertRaises(ValueError):
            am.GeneradorFondo("nada")
        with self.assertRaises(ValueError):
            am.GeneradorFondo("calle", frecuencia=4000)
        with self.assertRaises(ValueError):
            am.generar_sonido("nada")
        with self.assertRaises(ValueError):
            am.generar_sonido("bocina", frecuencia=4000)


if __name__ == "__main__":
    unittest.main()
