"""Biblioteca generada del modo Audio: fondos continuos y sonidos sueltos, por síntesis.

Solo usa numpy: ninguna grabación de terceros, ningún archivo. Todo sale en
bloques ``(n, 2)`` float32, estéreo, a 48 kHz (o a la ``frecuencia`` pedida).

* ``FONDOS``: ambientes continuos. ``GeneradorFondo(tipo, intensidad, semilla)``
  y después ``leer(inicio, n)``, desde cualquier muestra y de cualquier largo.
* ``SONIDOS``: sonidos sueltos (un colectivo que pasa, una bocina…).
  ``generar_sonido(tipo, semilla)`` los da enteros, con caché.

Niveles: un fondo a intensidad 0,5 sale con un RMS de ``NIVEL_FONDO_DBFS`` y un
sonido suelto con el pico en ``PICO_SONIDO_DBFS``. El volumen lo pone quien mezcla.

Determinismo y acceso aleatorio
-------------------------------
La misma semilla da siempre lo mismo, en cualquier proceso: el azar sale de un
hash estable (``hash()`` de Python cambia en cada proceso). Así, la vista previa
suena igual que la exportación. ``leer(inicio, n)`` da exactamente lo mismo que
leer desde 0 de corrido y cortar:

* **Trozos fijos de 1 s.** El trozo ``k`` se arma siempre igual, sin importar qué
  se leyó antes. El azar sale de bloques de 0,25 s, cada uno con su propia
  semilla ``(semilla, tipo, bloque)``.
* **Pre-lectura.** Cada trozo se filtra junto con los bloques anteriores
  (regenerados con sus semillas) y esa parte se descarta: 0,25 s para el ruido
  de color y 0,5 s para los golpes y los eventos, que traen la cola del lugar.
  Con filtros FIR que entran en la pre-lectura, el resultado es el de filtrar la
  señal continua: no hay uniones entre trozos y no hace falta ningún fundido. Es
  exacto salvo en el canal derecho del ruido "difuso": la coherencia entre
  micrófonos se aplica en frecuencia sobre el marco (circular) y ahí la
  diferencia con la señal continua queda entre -107 y -148 dB. Lo que sí es
  exacto bit a bit es el acceso aleatorio: cada trozo se calcula siempre igual.
* **Variaciones lentas y envolventes:** dependen del tiempo absoluto (un valor al
  azar cada tanto, sacado de un hash del índice, unidos con curvas suaves). Se
  calculan a 1 ms y se interpolan.
* **Osciladores** (zumbido de la red, motores, silbidos): la fase se integra por
  ranuras de varios segundos con un número entero de ciclos cada una (ver
  ``_Fondo.fase``). Así se calcula en cualquier instante sin sumar desde el principio.
* **Eventos** (autos que pasan, olas, ráfagas, puertas del colectivo): un
  calendario por ventana de tiempo, con su propia semilla. Cada evento se
  sintetiza entero (con caché) y se suma donde cae; uno que empezó en una
  ventana anterior también suena.

Realismo
--------
* Nada de tonos puros quietos ni de ruido "de radio sin señal": todo varía despacio
  (la lluvia sube y baja, el tránsito va y viene) y los tonos tienen armónicos y temblor.
* **Estéreo de celular:** dos micrófonos a unos 14 cm. En un campo difuso, la
  coherencia entre los canales es sin(kd)/(kd): casi igual en los graves y
  distinta en los agudos. Los ruidos de fondo se arman así, no como mono duplicado.
* **Vehículos:** el motor es la forma de onda de un ciclo (un pulso por cilindro,
  algo desparejos), más el ruido de los neumáticos. El Doppler sale exacto de la
  geometría, para el camino directo y para el rebote en el piso, con amplitud
  1/r, la diferencia de tiempo entre los micrófonos y un pasabajos que se abre
  cuando el vehículo está cerca. El rebote en el piso hace el "filtro de peine"
  que barre, típico de un auto que pasa.
* Los eventos de los fondos se sintetizan a la mitad de la frecuencia (24 kHz; los
  vehículos a media cuadra de la ciudad, a 16 kHz) y suben a 48 kHz dentro del
  mismo filtro que les pone el lugar (la reverberación de la calle o del
  colectivo): es rápido y no deja imágenes.

Velocidad: cada fondo, más de 20 veces el tiempo real (las capas de ruido que
cambian juntas se filtran juntas, en una sola FFT; los vehículos se sintetizan
en paralelo cuando se piden varios trozos); cada sonido suelto, en menos de
medio segundo.
"""

from __future__ import annotations

import hashlib
import math
import os
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from types import SimpleNamespace
from typing import Callable, Optional

import numpy as np

FRECUENCIA = 48000
NIVEL_FONDO_DBFS = -30.0   # RMS de un fondo a intensidad 0,5
PICO_SONIDO_DBFS = -6.0    # pico de un sonido suelto

_C = 343.0                 # m/s: velocidad del sonido
_SEPARACION_MICS = 0.14    # m entre los dos micrófonos del celular (apaisado)
_ALTURA_MIC = 1.4          # m: el celular en la mano
_DOS_PI = 2.0 * np.pi


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InfoAmbiente:
    """Lo que la interfaz muestra de un fondo o de un sonido suelto.

    clave        id estable (va en los proyectos y en las escenas).
    nombre       para la interfaz, en español: "Calle con tránsito".
    descripcion  una línea: "Autos y motos que pasan cerca".
    icono        nombre de un ícono de Lucide sugerido ("car", "cloud-rain"…).
    intensidad   si el parámetro intensidad cambia algo (si no, la interfaz puede esconderlo).
    duracion     solo sonidos sueltos: duración típica en segundos.
    """

    clave: str
    nombre: str
    descripcion: str
    icono: str
    intensidad: bool
    duracion: float = 0.0


def _catalogo(*infos: InfoAmbiente) -> dict[str, InfoAmbiente]:
    return {i.clave: i for i in infos}


FONDOS: dict[str, InfoAmbiente] = _catalogo(
    InfoAmbiente("ciudad", "Ciudad", "Rumor grave de la ciudad y autos lejanos", "building-2", True),
    InfoAmbiente("calle", "Calle con tránsito", "Autos, motos y colectivos que pasan cerca", "car", True),
    InfoAmbiente("lluvia", "Lluvia", "De llovizna a lluvia fuerte", "cloud-rain", True),
    InfoAmbiente("agua", "Agua o río", "Un arroyo que corre; con más intensidad, un río", "droplets", True),
    InfoAmbiente("olas", "Olas", "Olas que rompen en la orilla", "waves", True),
    InfoAmbiente("viento", "Viento", "Viento con ráfagas entre los árboles", "wind", True),
    InfoAmbiente("oficina", "Oficina", "Aire acondicionado, zumbido eléctrico y un teclado lejos", "air-vent", True),
    InfoAmbiente("habitacion", "Habitación", "El aire quieto de una habitación", "house", False),
    InfoAmbiente("auto", "Adentro de un auto", "Ruido de ruta desde adentro; con más intensidad, más rápido",
                 "car-front", True),
    InfoAmbiente("colectivo", "Motor del colectivo", "Desde adentro: arranca, acelera, frena y abre las puertas",
                 "bus", True),
    InfoAmbiente("viento_mic", "Viento en el micrófono", "Golpes graves del viento sobre el celular", "mic", True),
)

SONIDOS: dict[str, InfoAmbiente] = _catalogo(
    InfoAmbiente("colectivo_pasa", "Colectivo pasando", "Motor diésel que pasa cerca, con el silbido del freno",
                 "bus", False, 10.0),
    InfoAmbiente("auto_pasa", "Auto pasando", "Un auto que pasa cerca", "car", False, 6.4),
    InfoAmbiente("moto_pasa", "Moto pasando", "Una moto que pasa acelerando", "bike", False, 6.0),
    InfoAmbiente("frenada_colectivo", "Frenada de colectivo", "El «pssst» del freno de aire", "bus-front", False,
                 2.2),
    InfoAmbiente("bocina", "Bocina", "Un auto toca bocina", "megaphone", False, 2.0),
    InfoAmbiente("sirena_lejos", "Sirena lejos", "Una sirena a varias cuadras", "siren", False, 8.0),
)


# ---------------------------------------------------------------------------
# Azar determinista
# ---------------------------------------------------------------------------

_MASCARA = (1 << 64) - 1
_SM_A = np.uint64(0x9E3779B97F4A7C15)
_SM_B = np.uint64(0xBF58476D1CE4E5B9)
_SM_C = np.uint64(0x94D049BB133111EB)
_OTRA = 0x2545F4914F6CDD1D


def _clave(*partes) -> int:
    """Un entero de 64 bits para esas partes, igual en todos los procesos.

    ``hash()`` de Python cambia en cada proceso (para los textos): no sirve para
    que el mismo proyecto suene igual mañana.
    """
    texto = "\x1f".join(map(str, partes)).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(texto, digest_size=8).digest(), "little")


def _azar(*partes) -> np.random.Generator:
    return np.random.default_rng(_clave(*partes))


def _hash(clave: int, indices) -> np.ndarray:
    """splitmix64 de cada índice con la clave: bits al azar por índice, sin recorrer los anteriores."""
    x = np.atleast_1d(np.asarray(indices, dtype=np.int64)).view(np.uint64)
    x = x * _SM_A + np.uint64(clave & _MASCARA)
    x = (x ^ (x >> np.uint64(30))) * _SM_B
    x = (x ^ (x >> np.uint64(27))) * _SM_C
    return x ^ (x >> np.uint64(31))


def _uniformes(clave: int, indices) -> np.ndarray:
    """Una uniforme en (0, 1) por índice."""
    return ((_hash(clave, indices) >> np.uint64(11)).astype(np.float64) + 0.5) * 2.0 ** -53


def _normales(clave: int, indices) -> np.ndarray:
    """Una normal (0, 1) por índice (Box-Muller con dos hashes)."""
    u1 = _uniformes(clave, indices)
    u2 = _uniformes(clave ^ _OTRA, indices)
    return np.sqrt(-2.0 * np.log(u1)) * np.cos(_DOS_PI * u2)


def _suave(clave: int, t, paso: float) -> np.ndarray:
    """Ruido suave en los instantes ``t``: una normal cada ``paso`` unidades, unidas con Catmull-Rom.

    El mismo instante da siempre el mismo valor, se lo calcule cuando se lo
    calcule (acceso aleatorio). El desvío anda entre 0,8 y 1.
    """
    x = np.asarray(t, np.float64) / paso
    i = np.floor(x)
    f = x - i
    i = i.astype(np.int64)
    i0 = int(i.min()) - 1
    nudos = _normales(clave, np.arange(i0, int(i.max()) + 3))
    j = i - i0
    p0, p1, p2, p3 = nudos[j - 1], nudos[j], nudos[j + 1], nudos[j + 2]
    return p1 + 0.5 * f * (p2 - p0 + f * (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3 + f * (3.0 * (p1 - p2) + p3 - p0)))


def _suave_denso(clave: int, x: np.ndarray, paso: float, cada: int = 16) -> np.ndarray:
    """``_suave`` sobre una señal de muchas muestras con ``x`` creciente: se calcula cada ``cada``
    muestras y se interpola (los nudos están mucho más separados que eso)."""
    i = np.arange(0, x.size, cada)
    if i[-1] != x.size - 1:
        i = np.append(i, x.size - 1)
    return np.interp(np.arange(x.size), i, _suave(clave, x[i], paso))


def _fraccion(x: np.ndarray) -> np.ndarray:
    """Parte fraccionaria (x - piso(x)): lo mismo que ``x % 1.0``, tres veces más rápido."""
    return x - np.floor(x)


def _recordar(cache: OrderedDict, clave, valor, tope: int):
    """Guarda en una caché LRU chica y devuelve el valor."""
    cache[clave] = valor
    cache.move_to_end(clave)
    while len(cache) > tope:
        cache.popitem(last=False)
    return valor


# ---------------------------------------------------------------------------
# Filtros (respuestas en amplitud en función de la frecuencia en Hz)
# ---------------------------------------------------------------------------

def _db(x):
    return 10.0 ** (np.asarray(x, np.float64) / 20.0)


def _pa(f, corte: float, orden: int = 2):
    """Pasaaltos de Butterworth (amplitud)."""
    x = (np.maximum(f, 1e-6) / corte) ** (2 * orden)
    return np.sqrt(x / (1.0 + x))


def _pb(f, corte: float, orden: int = 2):
    """Pasabajos de Butterworth (amplitud)."""
    return 1.0 / np.sqrt(1.0 + (np.asarray(f) / corte) ** (2 * orden))


def _campana(f, centro: float, octavas: float, db: float):
    """Realce suave (o corte, con db negativo) alrededor de ``centro``, de unas ``octavas`` de ancho."""
    o = np.log2(np.maximum(f, 1e-3) / centro) / octavas
    return 10.0 ** (db / 20.0 * np.exp(-0.5 * o * o))


def _inclinacion(f, db_octava: float, referencia: float = 1000.0):
    """Pendiente de ``db_octava`` dB por octava (ruido rosa: -3; marrón: -6)."""
    return (np.maximum(f, 1.0) / referencia) ** (db_octava / 6.0206)


def _fir(amplitud: Callable, fr: int, largo: int) -> np.ndarray:
    """FIR de fase lineal con esa respuesta en amplitud y energía 1.

    Con energía 1, un ruido blanco de varianza 1 sale con varianza 1: las capas
    quedan calibradas y los niveles de cada fondo se dan en dB relativos.
    """
    largo = int(largo) // 2 * 2
    f = np.fft.rfftfreq(largo, 1.0 / fr)
    a = np.array(amplitud(f), np.float64)
    a[0] = 0.0
    h = np.roll(np.fft.irfft(a, largo), largo // 2) * np.hanning(largo)
    return h / np.sqrt(np.sum(h * h))


def _tamano_fft(n: int) -> int:
    """El menor tamaño >= n de la forma 2^a·3^b·5^c (rápido para la FFT)."""
    mejor = 1 << max(1, n - 1).bit_length()
    p5 = 1
    while p5 < mejor:
        p35 = p5
        while p35 < mejor:
            p = p35
            while p < n:
                p *= 2
            mejor = min(mejor, p)
            p35 *= 3
        p5 *= 5
    return mejor


def _convolucion(x: np.ndarray, h: np.ndarray) -> np.ndarray:
    """Convolución lineal por FFT sobre el último eje: (..., n) con (..., m) -> (..., n + m - 1)."""
    largo = x.shape[-1] + h.shape[-1] - 1
    tam = _tamano_fft(largo)
    return np.fft.irfft(np.fft.rfft(x, tam) * np.fft.rfft(h, tam), tam)[..., :largo]


def _curva_en(amplitud: Callable, f: np.ndarray) -> np.ndarray:
    """Una curva de amplitud suave evaluada en muchas frecuencias: se calcula en ~600 puntos
    logarítmicos y se interpola (evaluarla en cientos de miles de bins es tiempo perdido)."""
    if f.size <= 2048:
        return np.asarray(amplitud(f), np.float64)
    g = np.geomspace(max(f[1], 1.0), f[-1], 600)
    return np.interp(np.log(np.maximum(f, g[0])), np.log(g), np.asarray(amplitud(g), np.float64))


def _ruido_espectral(rng: np.random.Generator, n: int, fr: int, amplitud: Callable) -> np.ndarray:
    """Ruido de ``n`` muestras con esa respuesta en amplitud (función de f en Hz), armado en frecuencia, RMS 1."""
    tam = _tamano_fft(n)
    curva = _curva_en(amplitud, np.fft.rfftfreq(tam, 1.0 / fr))
    curva[0] = 0.0
    z = np.empty(curva.size, np.complex128)
    z.real = rng.standard_normal(curva.size)
    z.imag = rng.standard_normal(curva.size)
    z *= curva
    x = np.fft.irfft(z, tam)[:n]
    x *= 1.0 / (math.sqrt(np.dot(x, x) / n) + 1e-12)
    return x


def _filtrar_fft(x: np.ndarray, fr: int, amplitud: Callable) -> np.ndarray:
    """Filtra con esa respuesta en amplitud (fase cero), por FFT, con un margen para que no se doble."""
    n = x.shape[-1]
    tam = _tamano_fft(n + fr // 10)
    curva = _curva_en(amplitud, np.fft.rfftfreq(tam, 1.0 / fr))
    return np.fft.irfft(np.fft.rfft(x, tam) * curva, tam)[..., :n]


def _promedio_centrado(x: np.ndarray, largo: int) -> np.ndarray:
    """Promedio móvil centrado (sin retardo) sobre el último eje; ``largo`` impar."""
    if x.ndim > 1:
        return np.stack([_promedio_centrado(fila, largo) for fila in x])
    h, n = largo // 2, x.shape[-1]
    c = np.empty(n + largo)  # suma acumulada con h + 1 ceros adelante y la última repetida h veces atrás
    c[:h + 1] = 0.0
    np.cumsum(x, out=c[h + 1:h + 1 + n])
    c[h + 1 + n:] = c[h + n]
    salida = c[largo:] - c[:-largo]
    salida *= 1.0 / largo
    return salida


def _opacar(x: np.ndarray, fr: int) -> np.ndarray:
    """Pasabajos barato (un promedio móvil, unos 1,5 kHz): cómo se oye lo que está lejos."""
    return _promedio_centrado(x, max(3, int(round(fr / 3400)) | 1))


def _rampa(n: int) -> np.ndarray:
    """De 0 a 1 en ``n`` muestras, con coseno elevado (sin clics)."""
    return 0.5 - 0.5 * np.cos(np.pi * (np.arange(n) + 0.5) / max(1, n))


def _fundir(x: np.ndarray, entrada: int, salida: int) -> np.ndarray:
    """Fundidos de entrada y de salida (en muestras), en el lugar, sobre el último eje."""
    entrada, salida = min(entrada, x.shape[-1]), min(salida, x.shape[-1])
    if entrada:
        x[..., :entrada] *= _rampa(entrada)
    if salida:
        x[..., x.shape[-1] - salida:] *= _rampa(salida)[::-1]
    return x


def _paneo(pan):
    """Ganancias (izquierda, derecha) de igual potencia; pan de -1 a 1, 0 = al medio (1 y 1)."""
    th = (np.asarray(pan, np.float64) + 1.0) * (np.pi / 4.0)
    return np.sqrt(2.0) * np.cos(th), np.sqrt(2.0) * np.sin(th)


# ---------------------------------------------------------------------------
# Piezas de síntesis
# ---------------------------------------------------------------------------

def _reverberacion(rng: np.random.Generator, fr: int, rt60: float, largo: float, directo_reverb_db: float,
                   ecos: int = 0, eco_retardo=(0.02, 0.08), eco_nivel=(0.2, 0.45)) -> np.ndarray:
    """Respuesta al impulso estéreo (2, m) de un lugar: el directo, algunos ecos tempranos y una cola difusa.

    La cola es ruido que decae, distinto en cada canal, y se apaga antes en los
    agudos que en los graves, como en un lugar real. ``directo_reverb_db``: cuánta
    más energía tiene el directo que la cola (negativo = lejos, mucho lugar).
    """
    m = int(round(largo * fr))
    tam = _tamano_fft(m)
    t = np.arange(m) / fr
    f = np.fft.rfftfreq(tam, 1.0 / fr)
    graves = _pb(f, 500.0, 2) ** 2
    agudos = _pa(f, 4000.0, 2) ** 2
    medios = np.clip(1.0 - graves - agudos, 0.0, None)
    X = np.fft.rfft(rng.standard_normal((2, tam)), axis=1)
    cola = np.zeros((2, m))
    for peso, factor in ((graves, 1.25), (medios, 1.0), (agudos, 0.55)):
        cola += np.fft.irfft(X * np.sqrt(peso), tam, axis=1)[:, :m] * np.exp(-6.9078 * t / (rt60 * factor))
    cola *= 1.0 - np.exp(-t / 0.006)  # la cola llega un poco después del directo
    cola *= _db(-directo_reverb_db) / np.sqrt(np.sum(cola * cola, axis=1, keepdims=True))
    cola[:, 0] += 1.0
    for _ in range(ecos):
        d = int(rng.uniform(*eco_retardo) * fr)
        g = rng.uniform(*eco_nivel)
        lado = rng.uniform(-0.4, 0.4)
        if d < m:
            cola[0, d] += g * (1.0 - lado)
            cola[1, d] += g * (1.0 + lado)
    return _fundir(cola, 0, m // 8)


def _interpolador(fr: int, m: int) -> np.ndarray:
    """Pasabajos para subir de fr/m a fr después de intercalar ceros: ganancia m, corte en 0,45·fr/m."""
    if m == 1:
        return np.ones(1)
    n = 64 * m + 1
    x = np.arange(n) - (n - 1) / 2
    corte = 0.45 / m
    h = 2.0 * corte * np.sinc(2.0 * corte * x) * np.blackman(n)
    return h * (m / h.sum())


def _golpe(rng: np.random.Generator, fr: int, largo: float, modos: int = 0, banda=(1000.0, 4000.0),
           tau=(0.001, 0.004), ruido: float = 0.0, ruido_tau: float = 0.002, ruido_curva: Optional[Callable] = None,
           sala_rt60: float = 0.0, sala_db: float = -20.0, ataque: float = 0.0002) -> np.ndarray:
    """Respuesta (2, m) de un golpe corto: resonancias que se apagan, un soplo de ruido y la cola de la sala.

    modos         cuántas resonancias (frecuencias al azar en ``banda``, caídas en ``tau``).
    ruido         fracción de la energía que es ruido (``ruido_curva``), con caída ``ruido_tau``.
    sala_rt60     si no es 0, suma la cola de la sala, ``sala_db`` dB por debajo del golpe.
    ataque        s que tarda en arrancar: un golpe grave necesita unos ms, si no hace clic.
    Cada canal tiene sus propias fases: no es mono duplicado. Energía 1 por canal (sin la sala).
    """
    m = int(round(largo * fr))
    t = np.arange(m) / fr
    h = np.zeros((2, m))
    if modos:
        fm = np.exp(rng.uniform(np.log(banda[0]), np.log(banda[1]), modos))
        tm = rng.uniform(tau[0], tau[1], modos)
        am = rng.uniform(0.4, 1.0, modos)
        for c in range(2):
            fase = rng.uniform(0.0, _DOS_PI, modos)
            h[c] = (am[:, None] * np.sin(_DOS_PI * fm[:, None] * t + fase[:, None])
                    * np.exp(-t / tm[:, None])).sum(axis=0)
        h /= np.sqrt(np.sum(h * h, axis=1, keepdims=True)) + 1e-12
    if ruido > 0.0:
        curva = ruido_curva if ruido_curva is not None else np.ones_like
        r = np.stack([_ruido_espectral(rng, m, fr, curva) for _ in range(2)]) * np.exp(-t / ruido_tau)
        r /= np.sqrt(np.sum(r * r, axis=1, keepdims=True)) + 1e-12
        h = np.sqrt(1.0 - ruido) * h + np.sqrt(ruido) * r
    h *= 1.0 - np.exp(-t / ataque)  # sin escalón al principio
    h /= np.sqrt(np.sum(h * h, axis=1, keepdims=True)) + 1e-12
    if sala_rt60 > 0.0:
        cola = rng.standard_normal((2, m)) * np.exp(-6.9078 * t / sala_rt60) * (1.0 - np.exp(-t / 0.004))
        cola = _opacar(cola, fr)
        h += cola * (_db(sala_db) / (np.sqrt(np.sum(cola * cola, axis=1, keepdims=True)) + 1e-12))
    return _fundir(h, 0, max(1, m // 10))


def _tabla_motor(rng: np.random.Generator, cilindros: int, nitidez: float, desparejo: float, corte: float,
                 maximo: int, largo: int = 4096) -> np.ndarray:
    """Un ciclo del motor (dos vueltas de un 4 tiempos) como tabla de onda, con un pulso por cilindro.

    nitidez    ancho del pulso de cada explosión, en fracción del intervalo (chico = más armónicos).
    desparejo  cuánto difieren los cilindros entre sí en fuerza y en momento: es la "aspereza" de un diésel
               (aparecen los medios órdenes, la frecuencia del ciclo entero).
    corte      desde qué armónico del ciclo el escape los va apagando.
    maximo     último armónico que queda (para no pasar de la mitad de la frecuencia de muestreo).
    RMS 1; tiene una muestra más al final (la primera repetida) para interpolar sin saltos.
    """
    th = np.arange(largo) / largo
    onda = np.zeros(largo)
    for z in range(cilindros):
        centro = (z + rng.normal(0.0, 0.015 * desparejo)) / cilindros
        amp = max(0.3, 1.0 + rng.normal(0.0, 0.15 * desparejo))
        x = ((th - centro) % 1.0) * cilindros  # intervalos desde la explosión de este cilindro
        a = nitidez * rng.uniform(0.85, 1.15)
        resonancia = rng.uniform(2.5, 4.5)  # el caño de escape suena unas veces por intervalo
        onda += amp * ((x / a) * np.exp(1.0 - x / a) + 0.3 * np.sin(_DOS_PI * resonancia * x) * np.exp(-x / 0.3))
    espectro = np.fft.rfft(onda)
    k = np.arange(espectro.size)
    espectro *= 1.0 / np.sqrt(1.0 + (k / max(corte, 1.0)) ** 4)
    # Lo que irradia es la variación de la presión, no la presión: por debajo de la frecuencia de
    # las explosiones (los medios órdenes del desparejo) suena bastante menos que el pulso en sí.
    x = (k / (0.8 * cilindros)) ** 2
    espectro *= x / np.sqrt(1.0 + x * x)
    espectro[0] = 0.0
    espectro[max(1, int(maximo)) + 1:] = 0.0
    tabla = np.fft.irfft(espectro, largo)
    tabla /= np.sqrt(np.mean(tabla * tabla))
    return np.append(tabla, tabla[0])


def _tabla_red(rng: np.random.Generator, amplitudes, largo: int = 4096) -> np.ndarray:
    """Tabla de onda de un zumbido de la red: armónicos de 50 Hz con esas amplitudes y fases al azar."""
    th = np.arange(largo) / largo
    onda = sum(a * np.sin(_DOS_PI * (h + 1) * th + rng.uniform(0.0, _DOS_PI)) for h, a in enumerate(amplitudes))
    onda /= np.sqrt(np.mean(onda * onda))
    return np.append(onda, onda[0])


def _leer_tabla(tabla: np.ndarray, fase: np.ndarray) -> np.ndarray:
    """Valor de la tabla de onda en cada fase (en ciclos), con interpolación lineal."""
    largo = tabla.size - 1
    return np.interp(_fraccion(fase) * largo, np.arange(largo + 1, dtype=np.float64), tabla)


def _psst(rng: np.random.Generator, fr: int, largo: float = 1.8, sosten: Optional[float] = None) -> np.ndarray:
    """El "pssst" del aire de un colectivo (frenos o puertas), mono, pico 1.

    Un golpe de la válvula y un siseo de 1 a 9 kHz que arranca de golpe, se
    sostiene un momento y se apaga en ``largo`` segundos. Mientras cae la presión
    se apagan primero los agudos: el siseo "baja". Con temblor rápido, como el aire de verdad.
    """
    n = int(round(largo * fr))
    t = np.arange(n) / fr
    sosten = rng.uniform(0.12, 0.3) if sosten is None else sosten
    u = np.clip((t - sosten) / max(0.05, largo - sosten - 0.03), 0.0, 1.0)
    bandas = (
        (lambda f: _pa(f, 4200.0, 2) * _pb(f, 11000.0, 2), 3.4, 0.9),
        (lambda f: _campana(f, 3300.0, 0.7, 12.0) * _pa(f, 1800.0, 2) * _pb(f, 7000.0, 2), 2.3, 1.0),
        (lambda f: _campana(f, 1700.0, 0.8, 10.0) * _pa(f, 800.0, 2) * _pb(f, 3500.0, 2), 1.5, 0.55),
    )
    s = np.zeros(n)
    for curva, potencia, nivel in bandas:
        s += nivel * _ruido_espectral(rng, n, fr, curva) * (1.0 - u) ** potencia
    s *= (1.0 - np.exp(-t / 0.006)) * (1.0 + 0.12 * _suave_denso(int(rng.integers(1 << 62)), t, 0.012, 8))
    golpe = _ruido_espectral(rng, n, fr, lambda f: _pb(f, 2500.0, 2)) * np.exp(-t / 0.002)
    soplo = np.sin(_DOS_PI * rng.uniform(70.0, 110.0) * t) * np.exp(-t / 0.035) * (1.0 - np.exp(-t / 0.002))
    s += 0.7 * golpe + 0.15 * soplo
    _fundir(s, 0, int(0.03 * fr))
    return s / (np.abs(s).max() + 1e-12)


# ---------------------------------------------------------------------------
# Vehículos que pasan
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Perfil:
    """Cómo suena cada clase de vehículo."""

    cilindros: int
    nitidez: float         # ancho del pulso de cada explosión (fracción del intervalo)
    desparejo: float       # diferencias entre cilindros
    aspereza: float        # variación de una explosión a otra
    corte_escape: float    # Hz: arriba de esto el escape apaga los armónicos
    altura: float          # m: de dónde sale el sonido
    rebote: float          # cuánto vuelve del piso (amplitud): menos en uno largo, que suena desde varios lados
    motor_db: float
    golpeteo_db: float     # ruido que sale con cada explosión (traqueteo del diésel, raspado de la moto)
    golpeteo: tuple        # (centro en Hz, ancho en octavas)
    rodado_db: float       # neumáticos y aire
    rodado_centro: float   # Hz
    nivel_db: float        # nivel de la fuente, relativo entre clases


_PERFILES = {
    "colectivo": _Perfil(6, 0.10, 1.0, 0.2, 700.0, 0.8, 0.35, 0.0, -10.0, (1800.0, 1.0), -7.0, 550.0, 6.0),
    "auto": _Perfil(4, 0.20, 0.4, 0.06, 350.0, 0.35, 0.6, -9.0, -28.0, (2500.0, 1.0), 0.0, 900.0, 0.0),
    "moto": _Perfil(1, 0.07, 0.3, 0.18, 1800.0, 0.6, 0.6, 0.0, -5.0, (1500.0, 1.3), -12.0, 900.0, 3.0),
}


@dataclass(frozen=True)
class _Pasada:
    """Un vehículo que pasa por delante del celular, en línea recta."""

    clase: str            # "colectivo", "auto" o "moto"
    velocidad: float      # m/s
    distancia: float      # m, en el punto más cercano
    sentido: int          # +1: de izquierda a derecha; -1: al revés
    rpm: float            # en el punto más cercano
    aceleracion: float    # cambio relativo de las rpm por segundo (+ acelera, - afloja)
    antes: float          # s de audio antes del punto más cercano
    despues: float        # s después
    semilla: int
    cilindros: int = 0    # 0 = los del perfil
    cambio: Optional[float] = None  # s (desde el punto más cercano) de un cambio de marcha
    freno: Optional[float] = None   # s del "pssst" del freno de aire


def _nueva_pasada(rng: np.random.Generator, clase: str, distancia, x_max: float) -> _Pasada:
    """Una pasada con parámetros creíbles al azar (velocidad, régimen, de qué lado viene)."""
    cilindros = 0
    if clase == "colectivo":
        v, rpm, acel = rng.uniform(7.0, 11.5), rng.uniform(1300.0, 1800.0), rng.uniform(-0.04, 0.05)
    elif clase == "auto":
        v, rpm, acel = rng.uniform(8.0, 14.5), rng.uniform(1800.0, 2700.0), rng.uniform(-0.03, 0.06)
    else:
        cilindros = 1 if rng.random() < 0.65 else 2
        v, acel = rng.uniform(9.0, 16.0), rng.uniform(0.0, 0.1)
        rpm = rng.uniform(6000.0, 8500.0) if cilindros == 1 else rng.uniform(5000.0, 7000.0)
    d = rng.uniform(*distancia)
    sentido = 1 if rng.random() < 0.5 else -1
    lado = min(x_max, 8.0 * d + 12.0) / v  # hasta dónde se oye antes de que lo tape el resto
    return _Pasada(clase, v, d, sentido, rpm, acel, lado, lado, int(rng.integers(1 << 62)), cilindros)


_PASO_GRUESO = 16  # muestras: lo que cambia suave en una pasada se calcula cada 16 y se interpola


_ESCALON = np.arange(_PASO_GRUESO) / _PASO_GRUESO
_ESCALON32 = _ESCALON.astype(np.float32)


def _a_fino(v: np.ndarray, n: int, ganancia: bool = False) -> np.ndarray:
    """De una grilla gruesa (un valor cada ``_PASO_GRUESO`` muestras, desde la 0) a ``n`` muestras, lineal.

    Más rápido que ``np.interp`` porque la grilla es pareja; ``v`` tiene que cubrir las n muestras.
    ``ganancia``: el resultado va en float32 (cuatro veces más rápido; sirve para ganancias, no
    para posiciones en muestras, que necesitan float64).
    """
    if ganancia:
        v = np.asarray(v, np.float32)
    v0 = v[:-1]
    salida = (v[1:] - v0)[:, None] * (_ESCALON32 if ganancia else _ESCALON)
    salida += v0[:, None]
    return salida.ravel()[:n]


def _colocar_mono(n: int, pos: np.ndarray, amp: np.ndarray, forma: np.ndarray) -> np.ndarray:
    """Suma ``forma`` (escalada por cada ``amp``) desde cada posición, en una señal de ``n`` muestras."""
    indices = pos[:, None] + np.arange(forma.size)
    sirve = indices < n
    return np.bincount(indices[sirve], (amp[:, None] * forma)[sirve], n)


def _fuente_vehiculo(p: _Pasada, perfil: _Perfil, tau0: float, m: int, fr: int,
                     rng: np.random.Generator) -> np.ndarray:
    """Lo que sale del vehículo: ``m`` muestras desde la emisión ``tau0`` (s; 0 = el punto más cercano)."""
    cilindros = p.cilindros or perfil.cilindros
    clave = _clave("pasada", p.semilla)
    tau = tau0 + np.arange(m // _PASO_GRUESO + 2) * (_PASO_GRUESO / fr)  # grilla gruesa
    rpm = p.rpm * (1.0 + p.aceleracion * tau)
    carga = np.ones_like(tau)
    if p.cambio is not None:  # sube un cambio: las rpm caen en un instante y el motor afloja un momento
        x = np.clip((tau - p.cambio) / 0.14, 0.0, 1.0)
        rpm *= 1.0 - 0.26 * x * x * (3.0 - 2.0 * x)
        carga -= 0.75 * np.exp(-((tau - p.cambio - 0.05) / 0.08) ** 2)
    rpm *= 1.0 + 0.006 * _suave(clave, tau, 0.35)
    f_ciclo = rpm / 120.0
    fase_gruesa = np.concatenate(([0.0], np.cumsum(f_ciclo[1:] + f_ciclo[:-1]) * (0.5 * _PASO_GRUESO / fr)))
    fase = _a_fino(fase_gruesa, m)
    tabla = _tabla_motor(rng, cilindros, perfil.nitidez, perfil.desparejo, perfil.corte_escape / (p.rpm / 120.0),
                         int(0.45 * fr / f_ciclo.max()))
    explosiones = fase_gruesa * cilindros
    nivel = (1.0 + perfil.aspereza * _suave(clave + 1, explosiones, 1.0)) * (0.4 + 0.6 * carga)
    s = _leer_tabla(tabla, fase)
    s *= _a_fino(_db(perfil.motor_db) * nivel, m, ganancia=True)
    if perfil.golpeteo_db > -24.0:  # en un auto, el golpeteo no se oye: ni se calcula
        centro, ancho = perfil.golpeteo
        # El traqueteo es un ruido de 1 a 4 kHz: casi nada por debajo de la mitad de su centro.
        golpeteo = _ruido_espectral(rng, m, fr, lambda f: _pa(f, 0.5 * centro, 2) * _campana(f, centro, ancho, 9.0)
                                    * _pb(f, 7000.0, 2))
        nivel = (1.0 + 0.5 * _suave(clave + 2, explosiones, 1.0)) * (0.3 + 0.7 * carga) * _db(perfil.golpeteo_db)
        golpe = _fraccion(fase * cilindros)  # cada explosión, un estallido de ruido que se apaga
        golpe *= -1.0 / 0.18
        np.exp(golpe, out=golpe)
        golpeteo *= golpe
        golpeteo *= _a_fino(nivel, m, ganancia=True)
        s += golpeteo
    rodado = _ruido_espectral(rng, m, fr, lambda f: _pa(f, 120.0, 2) * _campana(f, perfil.rodado_centro, 1.3, 8.0)
                              * _pb(f, 4500.0, 2) * _inclinacion(f, -2.0, 1000.0))
    rodado *= _db(perfil.rodado_db) * (p.velocidad / 12.0) ** 1.6
    s += rodado

    if p.clase == "colectivo":
        # Chapas y vidrios que traquetean con cada pozo.
        cant = int(rng.poisson(14.0 * m / fr))
        pos = rng.integers(0, m, cant)
        amp = np.exp(0.7 * rng.standard_normal(cant)) * np.where(rng.random(cant) < 0.5, -1.0, 1.0)
        chapa = _golpe(rng, fr, 0.03, modos=8, banda=(700.0, 3500.0), tau=(0.002, 0.009), ruido=0.3,
                       ruido_tau=0.004, ruido_curva=lambda f: _pa(f, 800.0) * _pb(f, 5000.0))[0]
        s += _colocar_mono(m, pos, amp * (_db(-14.0) / np.sqrt(14.0 / fr * np.exp(0.98))), chapa)
    if p.freno is not None:
        psst = _psst(rng, fr, largo=0.9, sosten=0.08) * (_db(-3.0) * 3.0 * np.sqrt(np.mean(s * s)))
        i0 = int(round((p.freno - tau0) * fr))
        if 0 <= i0 < m:
            s[i0:i0 + psst.size] += psst[:m - i0]
    return s * _db(perfil.nivel_db)


def _pasada(p: _Pasada, fr: int) -> np.ndarray:
    """Un vehículo que pasa: (2, n) a ``fr``, sin normalizar (amplitud 1/r, con r en metros).

    El tiempo 0 es cuando llega el sonido del punto más cercano. Para cada camino
    (directo y rebote en el piso) se calcula el instante de emisión exacto, con
    una fórmula cerrada, y se lee la fuente ahí: eso es el Doppler. Se arma en
    el micrófono izquierdo y el derecho sale corrido por la diferencia de tiempo
    entre los dos (que cambia mientras pasa). Lo que cambia suave (instantes de
    emisión, distancias, paneo) va en una grilla de 16 muestras.
    """
    perfil = _PERFILES[p.clase]
    rng = np.random.default_rng(p.semilla)
    n = int(round((p.antes + p.despues) * fr))
    v, c2 = p.velocidad, _C * _C
    v2 = v * v
    t = np.arange(n // _PASO_GRUESO + 2) * (_PASO_GRUESO / fr) - p.antes  # grilla gruesa de recepción

    def emision(altura: float, x_mic: float) -> np.ndarray:
        # El vehículo está en x = sentido·v·τ; el micrófono, en x_mic. Despejando
        # t = τ + r(τ)/c queda una cuadrática en τ: se toma la raíz del pasado.
        d2 = p.distancia ** 2 + altura ** 2
        tm = p.sentido * x_mic / v
        tp = t - tm
        return tm + (c2 * tp - np.sqrt(c2 * v2 * tp * tp + (c2 - v2) * d2)) / (c2 - v2)

    izquierdo = -_SEPARACION_MICS / 2
    directo = emision(_ALTURA_MIC - perfil.altura, izquierdo)
    rebote = emision(_ALTURA_MIC + perfil.altura, izquierdo)
    derecho = emision(_ALTURA_MIC - perfil.altura, -izquierdo)
    tau0 = min(directo[0], rebote[0]) - 4.0 / fr
    m = int(np.ceil((max(directo[-1], rebote[-1]) - tau0) * fr)) + 4
    fuente = _fuente_vehiculo(p, perfil, tau0, m, fr, rng)
    eje = np.arange(m, dtype=np.float64)

    r = _C * (t - directo)
    salida = np.empty((2, n))
    y = salida[0]
    y[:] = np.interp(_a_fino((directo - tau0) * fr, n), eje, fuente)
    y *= _a_fino(1.0 / r, n, ganancia=True)
    rebotado = np.interp(_a_fino((rebote - tau0) * fr, n), eje, fuente)
    rebotado *= _a_fino(perfil.rebote / (_C * (t - rebote)), n, ganancia=True)
    y += rebotado
    lejos = _a_fino(1.0 - 1.0 / (1.0 + (r / 25.0) ** 2), n, ganancia=True)  # el pasabajos se abre cuando está cerca
    opaco = _opacar(y, fr)
    opaco -= y
    opaco *= lejos
    y += opaco
    muestras = np.arange(n, dtype=np.float64)
    y_der = salida[1]
    y_der[:] = np.interp(muestras + _a_fino((derecho - directo) * fr, n), muestras, y)
    lado = np.clip(p.sentido * v * directo / r, -1.0, 1.0)  # seno del ángulo: -1 a la izquierda
    # Aparece y se va de a poco, tapado por lo demás: el fundido es suave en dB (de -40 dB a 0, sin
    # quiebre al final), con una rampa corta al principio para llegar a cero sin escalón. Va en la
    # grilla gruesa, junto con el paneo (dura más de un segundo: 16 muestras no se notan).
    fundido = min(3.0, 0.4 * (p.antes + p.despues))
    u = np.clip(np.minimum(t + p.antes, p.despues - t) / fundido, 0.0, 1.0)
    rampa = 10.0 ** (-2.0 * (1.0 - u) ** 2) * np.clip(u / 0.05, 0.0, 1.0)
    y *= _a_fino(rampa * (1.0 - 0.2 * lado), n, ganancia=True)
    y_der *= _a_fino(rampa * (1.0 + 0.2 * lado), n, ganancia=True)
    return salida


# ---------------------------------------------------------------------------
# Fondos: el marco común
# ---------------------------------------------------------------------------

class _Fondo:
    """Base de cada fondo: arma el trozo ``k`` (1 s) con capas de ruido, golpes, granos, osciladores y eventos.

    Las subclases definen ``preparar`` (filtros y parámetros, una vez) y
    ``trozo(k)`` -> (2, L) float64. El trozo k depende solo de k (y del tipo, la
    intensidad y la semilla): eso hace exacto el acceso aleatorio.

    Tamaños, en muestras: ``B`` bloque de azar (0,25 s), ``L`` trozo (1 s), ``P``
    pre-lectura de golpes y eventos (0,5 s), ``N = P + L`` su marco, ``Nr = B + L``
    el marco del ruido de color, ``M`` puntos de la grilla de envolventes por trozo (1 ms).
    """

    PENDIENTE_DB = 0.0  # dB que sube el nivel por cada unidad de intensidad
    SUBMUESTREO = 2     # los eventos se sintetizan a fr/SUBMUESTREO (si queda en 16 kHz o más)
    # Calibración (dB): con esto, a intensidad 0,5 el RMS de largo plazo queda en NIVEL_FONDO_DBFS.
    # Se mide (6 semillas de 60 s cada una) y hay que volver a medirlo si cambia la receta.
    AJUSTE_DB = 0.0

    def __init__(self, tipo: str, intensidad: float, semilla: int, fr: int):
        self.tipo, self.intensidad, self.semilla, self.fr = tipo, intensidad, semilla, fr
        self.B = fr // 4
        self.L = 4 * self.B
        self.P = 2 * self.B
        self.N = self.L + self.P
        self.Nr = self.L + self.B
        self.M = 1000
        sub = self.SUBMUESTREO
        self.m = sub if self.B % sub == 0 and fr // sub >= 16000 else 1  # los eventos, a fr/m
        self._x_grilla = np.arange(self.M + 1) * (self.L / self.M)
        self._x_muestras = np.arange(self.L, dtype=np.float64)
        paso = self.L // self.M
        self._fraccion = np.arange(paso) / paso if paso * self.M == self.L else None
        f = np.fft.rfftfreq(self.Nr, 1.0 / fr)
        c = np.sinc(2.0 * f * _SEPARACION_MICS / _C)
        self._coherencia = (c, np.sqrt(np.clip(1.0 - c * c, 0.0, None)))
        self._espectros: dict[str, np.ndarray] = {}
        self._H_lugar: Optional[np.ndarray] = None
        self._espectro_trozo = None  # (k, espectro del ruido blanco del marco del trozo k)
        self._blancos: OrderedDict = OrderedDict()
        self._fases: OrderedDict = OrderedDict()
        self._calendarios: OrderedDict = OrderedDict()
        self._eventos: OrderedDict = OrderedDict()
        self._repeticion = None  # índices para repetir el espectro de los eventos (ver marco_eventos)
        self._sorteos: OrderedDict = OrderedDict()
        self.preparar()

    def preparar(self) -> None:
        """Filtros y parámetros del fondo (una vez, al crearlo)."""

    def trozo(self, k: int) -> np.ndarray:
        raise NotImplementedError

    def anticipar(self, k0: int, k1: int) -> None:
        """Aviso de que se van a pedir los trozos k0 a k1 (para preparar trabajo en paralelo)."""

    # ------------------------------------------------------------ azar y tiempo
    def azar(self, *partes) -> np.random.Generator:
        return _azar(self.semilla, self.tipo, *partes)

    def clave(self, *partes) -> int:
        return _clave(self.semilla, self.tipo, *partes)

    def suave(self, nombre, t, paso: float) -> np.ndarray:
        return _suave(self.clave("suave", nombre), t, paso)

    def deriva(self, nombre, t, db: float, pasos=(2.3, 7.1, 19.0)) -> np.ndarray:
        """Ganancia que sube y baja despacio, unos ±``db`` dB, mezclando varias escalas de tiempo."""
        x = sum(self.suave((nombre, i), t, p) for i, p in enumerate(pasos)) / math.sqrt(len(pasos))
        return _db(db * x)

    def tiempos(self, k: int) -> np.ndarray:
        """Instantes (s) de la grilla de 1 ms del trozo k: M + 1 puntos, con el final incluido."""
        return (k * self.L + self._x_grilla) / self.fr

    def a_muestras(self, valores: np.ndarray) -> np.ndarray:
        """De la grilla de 1 ms a cada muestra del trozo (interpolación lineal)."""
        if self._fraccion is not None:
            v0 = valores[:-1]
            return (v0[:, None] + (valores[1:] - v0)[:, None] * self._fraccion).ravel()
        return np.interp(self._x_muestras, self._x_grilla, valores)

    def estereo(self, izquierda: np.ndarray, derecha: np.ndarray) -> np.ndarray:
        """Dos envolventes de la grilla, llevadas a (2, L)."""
        return np.stack((self.a_muestras(izquierda), self.a_muestras(derecha)))

    # ------------------------------------------------------------ ruido de color
    def capa(self, nombre: str, *componentes, largo: int = 8192) -> None:
        """Una capa de ruido de color, con su filtro.

        componentes: una respuesta en amplitud (función de f en Hz), con potencia
        1; o varios pares (dB, amplitud), cada uno con potencia 10^(dB/10), que
        suenan como ruidos independientes. Las que cambian de volumen juntas van
        en una sola capa: se filtran en una sola FFT.
        """
        if len(componentes) == 1 and callable(componentes[0]):
            componentes = ((0.0, componentes[0]),)
        largo = min(largo, self.B)
        f = np.fft.rfftfreq(largo // 2 * 2, 1.0 / self.fr)
        potencia = np.zeros_like(f)
        for db, amplitud in componentes:
            a = np.asarray(amplitud(f), np.float64) ** 2
            potencia += _db(2.0 * db) * a / (a[1:].mean() + 1e-30)
        h = _fir(lambda _f: np.sqrt(potencia), self.fr, largo)
        self._espectros[nombre] = np.fft.rfft(h, self.Nr) * math.sqrt(sum(_db(2.0 * db) for db, _ in componentes))

    def _blanco(self, bloque: int) -> np.ndarray:
        x = self._blancos.get(bloque)
        if x is None:
            x = self.azar("blanco", bloque).standard_normal((2, self.B))
        return _recordar(self._blancos, bloque, x, 8)

    def _espectro_blanco(self, k: int):
        """Espectro de los dos ruidos blancos del marco del trozo k (con su pre-lectura de un bloque)."""
        if self._espectro_trozo is None or self._espectro_trozo[0] != k:
            marco = np.concatenate([self._blanco(b) for b in range(4 * k - 1, 4 * k + 4)], axis=1)
            self._espectro_trozo = (k, np.fft.rfft(marco, axis=1))
        return self._espectro_trozo[1]

    def ruido(self, k: int, nombres, modo: str = "difuso") -> dict[str, np.ndarray]:
        """Capas de ruido de color del trozo k: cada una (2, L), con la potencia de su capa por canal.

        Todas salen del mismo ruido blanco con distintos filtros (como una fuente
        que cambia de color) y se filtran en una sola FFT. modo: "difuso" (la
        coherencia de un campo difuso entre los dos micrófonos), "mono" (igual en
        los dos) o "independiente" (sin relación).
        """
        X1, X2 = self._espectro_blanco(k)
        if modo == "difuso":
            XR = self._coherencia[0] * X1 + self._coherencia[1] * X2
        elif modo == "mono":
            XR = X1
        else:
            XR = X2
        H = np.stack([self._espectros[n] for n in nombres])
        Y = np.empty((2 * len(nombres), H.shape[1]), np.complex128)
        Y[0::2] = H * X1
        Y[1::2] = H * XR
        y = np.fft.irfft(Y, self.Nr, axis=1)[:, self.B:]
        return {n: y[2 * i:2 * i + 2] for i, n in enumerate(nombres)}

    # ------------------------------------------------------------ golpes y granos
    def _sorteo(self, k: int, nombre, tasa: float, sigma: float, aceptar: Optional[Callable], extra=None):
        """Momentos al azar en el marco (de largo N) del trozo k, por bloques de 0,25 s con su semilla.

        Devuelve (posiciones en el marco, amplitudes lognormales de desvío
        ``sigma`` con signo al azar, paneos de -1 a 1, parámetros extra), ya
        filtrados por ``aceptar``. ``extra(rng, cant)`` sortea los parámetros
        propios (siempre en el mismo orden, así el resto del azar no cambia).
        Cada bloque se sortea una vez y queda en caché (los de la pre-lectura son
        los últimos del trozo anterior), con la clave (nombre, bloque, tasa,
        sigma). Ojo: ``aceptar`` y ``extra`` no van en la clave (son funciones que
        se arman de nuevo en cada trozo); para un mismo ``nombre`` tienen que dar
        siempre lo mismo. Lo cumplen todas las recetas: dependen solo del tiempo
        y de parámetros que se fijan al crear el fondo.
        """
        b0 = 4 * k - 2
        partes = [self._sorteo_bloque(nombre, b, tasa, sigma, aceptar, extra) for b in range(b0, b0 + 6)]
        pos = np.concatenate([parte[0] + j * self.B for j, parte in enumerate(partes)])
        amp = np.concatenate([parte[1] for parte in partes])
        pan = np.concatenate([parte[2] for parte in partes])
        datos = None
        if extra is not None:
            datos = tuple(np.concatenate(columna) for columna in zip(*(parte[3] for parte in partes)))
        return pos, amp, pan, datos

    def _sorteo_bloque(self, nombre, bloque: int, tasa: float, sigma: float, aceptar: Optional[Callable], extra):
        clave = (nombre, bloque, tasa, sigma)
        r = self._sorteos.get(clave)
        if r is None:
            rng = self.azar("sorteo", nombre, bloque)
            cant = int(rng.poisson(tasa * self.B / self.fr))
            pos = rng.integers(0, self.B, cant)
            amp = np.exp(sigma * rng.standard_normal(cant)) * np.where(rng.random(cant) < 0.5, -1.0, 1.0)
            pan = rng.uniform(-1.0, 1.0, cant)
            sorteo = rng.random(cant)
            datos = extra(rng, cant) if extra is not None else None
            if aceptar is not None and cant:
                quedan = sorteo < aceptar((bloque * self.B + pos) / self.fr)
                pos, amp, pan = pos[quedan], amp[quedan], pan[quedan]
                if datos is not None:
                    datos = tuple(d[quedan] for d in datos)
            r = (pos, amp, pan, datos)
        return _recordar(self._sorteos, clave, r, 64)

    def _colocar(self, pos: np.ndarray, izquierda: np.ndarray, derecha: np.ndarray) -> np.ndarray:
        """Suma formas de onda (una fila por momento) desde cada posición del marco: (2, L), sin la pre-lectura."""
        indices = pos[:, None] + np.arange(izquierda.shape[1]) - self.P
        sirve = (indices >= 0) & (indices < self.L)
        indices = indices[sirve]
        return np.stack((np.bincount(indices, izquierda[sirve], self.L),
                         np.bincount(indices, derecha[sirve], self.L)))

    def golpe(self, h: np.ndarray) -> SimpleNamespace:
        """Un golpe (respuesta (2, G) de ``_golpe``) listo para ``sonar``; tiene que entrar en la pre-lectura."""
        h = np.asarray(h, np.float64)
        if h.shape[-1] > self.P:
            raise ValueError("Un golpe de fondo no puede ser más largo que la pre-lectura.")
        return SimpleNamespace(h=h, H=np.fft.rfft(h, self.N, axis=-1))

    def sonar(self, k: int, nombre, golpe: SimpleNamespace, tasa: float, sigma: float = 0.7, abrir: float = 0.8,
              aceptar: Optional[Callable] = None, segundo=None) -> np.ndarray:
        """Golpes al azar (gotas, teclas, chapas) en el trozo k: (2, L), potencia media 1 por canal.

        tasa     golpes por segundo (la máxima, si hay ``aceptar``).
        sigma    desvío de la amplitud (lognormal, en neperios); el signo, al azar.
        abrir    cuánto se reparten entre izquierda y derecha (0 = al centro).
        aceptar  aceptar(t) -> probabilidad (0 a 1) de que suene un golpe en el instante t (s).
        segundo  (retardo(t) -> s, nivel): cada golpe trae otro más suave atrás (la tecla al
                 soltarse, la rueda de atrás en una junta). Retardo + golpe <= 0,5 s.
        Si son pocos se ponen uno por uno; si son muchos, se filtran por FFT.
        """
        pos, amp, pan, _ = self._sorteo(k, nombre, tasa, sigma, aceptar)
        if segundo is not None and pos.size:
            retardo, nivel = segundo
            pos2 = pos + np.round(retardo((k * self.L - self.P + pos) / self.fr) * self.fr).astype(np.int64)
            pos, amp, pan = np.concatenate((pos, pos2)), np.concatenate((amp, amp * nivel)), np.concatenate((pan, pan))
            dentro = pos < self.N
            pos, amp, pan = pos[dentro], amp[dentro], pan[dentro]
        amp = amp / math.sqrt(max(tasa, 1e-9) / self.fr * math.exp(2.0 * sigma * sigma))
        g_izq, g_der = _paneo(pan * abrir)
        h = golpe.h
        if pos.size * h.shape[1] <= 120_000:  # pocos: uno por uno sale más barato que la FFT
            sirven = pos + h.shape[1] > self.P
            pos, a_izq, a_der = pos[sirven], (amp * g_izq)[sirven], (amp * g_der)[sirven]
            return self._colocar(pos, a_izq[:, None] * h[0], a_der[:, None] * h[1])
        marco = np.stack((np.bincount(pos, amp * g_izq, self.N), np.bincount(pos, amp * g_der, self.N)))
        return self.filtrar((marco, golpe.H))

    def filtrar(self, *pares) -> np.ndarray:
        """Suma de marcos (2, N) filtrados con su respuesta (rfft de tamaño N): (2, L), sin la pre-lectura."""
        total = None
        for marco, H in pares:
            Y = np.fft.rfft(marco, axis=1) * H
            total = Y if total is None else total + Y
        return np.fft.irfft(total, self.N, axis=1)[:, self.P:]

    def granos(self, k: int, nombre, tasa: float, banda, tau, subida, sigma: float = 0.6, abrir: float = 0.9,
               aceptar: Optional[Callable] = None) -> np.ndarray:
        """Burbujas o gotas en el agua: senos que se apagan y suben de tono, en el trozo k: (2, L).

        banda   (mínima, máxima) frecuencia inicial en Hz (al azar, pareja en escala logarítmica).
        tau     (mínima, máxima) caída en s.
        subida  (mínima, máxima) cuánto sube el tono en una caída (0,2 = 20 %): una burbuja que sube.
        Potencia media 1 por canal, aproximada.
        """
        lf0, lf1 = math.log(banda[0]), math.log(banda[1])

        def parametros(rng, cant):
            return (np.exp(rng.uniform(lf0, lf1, cant)), rng.uniform(tau[0], tau[1], cant),
                    rng.uniform(subida[0], subida[1], cant))

        pos, amp, pan, (f0, ta, su) = self._sorteo(k, ("granos", nombre), tasa, sigma, aceptar, parametros)
        G = int(math.ceil(5.0 * tau[1] * self.fr))
        sirven = pos + G > self.P  # los que suenan dentro del trozo
        if not sirven.any():
            return np.zeros((2, self.L))
        pos, amp, pan, f0, ta, su = pos[sirven], amp[sirven], pan[sirven], f0[sirven], ta[sirven], su[sirven]
        t = np.arange(G) / self.fr
        fase = f0[:, None] * (t + su[:, None] * t * t / (2.0 * ta[:, None]))
        onda = np.sin(_DOS_PI * fase) * np.exp(-t / ta[:, None]) * (1.0 - np.exp(-t / 0.0003))
        escala = 1.0 / math.sqrt(tasa * math.exp(2.0 * sigma * sigma) * 0.25 * (tau[0] + tau[1]) / 2.0)
        g_izq, g_der = _paneo(pan * abrir)
        onda *= (amp * escala)[:, None]
        return self._colocar(pos, onda * g_izq[:, None], onda * g_der[:, None])

    # ------------------------------------------------------------ osciladores
    def fase(self, k: int, nombre, frecuencia: Callable, ranura: float) -> np.ndarray:
        """Fase (en ciclos) de un oscilador de frecuencia ``frecuencia(t)`` Hz en cada muestra del trozo k.

        Se integra por ranuras de ``ranura`` segundos (un número entero de
        trozos), cada una con un número entero de ciclos: la fase empieza en 0 en
        cada ranura, así que se calcula en cualquier instante sin sumar desde el
        principio, y sigue continua de una ranura a la otra. Para llegar al
        entero se suma una lomada suave de frecuencia, nula en los bordes: medio
        ciclo, a lo sumo, repartido en toda la ranura (con 40 s y un motor de 6
        Hz de ciclo, menos de 0,2 %: no se oye).
        """
        trozos = max(1, int(round(ranura * self.fr / self.L)))
        s = k // trozos
        clave = (nombre, s)
        g = self._fases.get(clave)
        if g is None:
            puntos = trozos * self.M
            tg = (s * trozos * self.L + np.arange(puntos + 1) * (self.L / self.M)) / self.fr
            f = np.asarray(frecuencia(tg), np.float64)
            dt = self.L / self.M / self.fr
            acumulada = np.concatenate(([0.0], np.cumsum((f[1:] + f[:-1]) * (0.5 * dt))))
            delta = np.round(acumulada[-1]) - acumulada[-1]
            u = np.arange(puntos + 1) / puntos
            g = acumulada + delta * (u - np.sin(_DOS_PI * u) / _DOS_PI)
        _recordar(self._fases, clave, g, 8)
        j = k - s * trozos
        return self.a_muestras(g[j * self.M:(j + 1) * self.M + 1])

    def onda_red(self, k: int, tabla: np.ndarray) -> np.ndarray:
        """Una tabla de onda a 50 Hz exactos (la red eléctrica no se desafina) en cada muestra del trozo k."""
        periodo = self.fr // 50
        if self.fr % 50 == 0 and self.L % periodo == 0:  # cada trozo empieza en un ciclo entero
            return np.tile(_leer_tabla(tabla, np.arange(periodo) / periodo), self.L // periodo)
        return _leer_tabla(tabla, self.fase(k, "red", lambda t: np.full_like(t, 50.0), 1.0))

    # ------------------------------------------------------------ eventos
    def eventos_en(self, nombre, desde: float, hasta: float, ventana: float, antes: float, despues: float,
                   generar: Callable) -> list:
        """Eventos que suenan entre ``desde`` y ``hasta`` (s).

        Cada ventana de ``ventana`` s tiene los suyos, de ``generar(rng, t0)`` con
        su propia semilla: empiezan, a lo sumo, ``antes`` s antes de la ventana y
        terminan, a lo sumo, ``despues`` s después de que termina. Cada evento
        tiene ``inicio`` y ``fin`` (s) y lo que haga falta para sintetizarlo.
        """
        w0 = math.floor((desde - despues) / ventana) - 1
        w1 = math.floor((hasta + antes) / ventana)
        salida = []
        for w in range(w0, w1 + 1):
            clave = (nombre, w)
            eventos = self._calendarios.get(clave)
            if eventos is None:
                eventos = generar(self.azar("calendario", nombre, w), w * ventana)
                for i, e in enumerate(eventos):
                    e.clave = (nombre, w, i)
            _recordar(self._calendarios, clave, eventos, 96)
            salida.extend(e for e in eventos if e.fin > desde and e.inicio < hasta)
        return salida

    def audio_evento(self, evento, sintetizar: Callable):
        """(primera muestra a fr/m, audio (2, n) a fr/m) del evento, con caché: se sintetiza una vez.

        Se guarda en float32 (un auto que pasa ocupa menos de 1 MB) y la caché es
        chica: a lo sumo 12 eventos, y los que ya terminaron se olvidan (ver
        ``marco_eventos``). Si se vuelve atrás, se sintetizan de nuevo, iguales.
        """
        par = self._eventos.get(evento.clave)
        if par is None:
            audio = np.asarray(sintetizar(evento, self.fr // self.m), np.float32)
            par = (int(round(evento.inicio * self.fr / self.m)), audio)
        return _recordar(self._eventos, evento.clave, par, 12)

    def preparar_lugar(self, rt60: float, largo: float, directo_reverb_db: float, ecos: int = 0,
                       eco_retardo=(0.02, 0.08), eco_nivel=(0.2, 0.45)) -> None:
        """El lugar donde suenan los eventos: reverberación más el filtro que sube de fr/m a fr."""
        h = _reverberacion(self.azar("lugar"), self.fr, rt60, largo, directo_reverb_db, ecos, eco_retardo, eco_nivel)
        self._H_lugar = self.golpe(_convolucion(h, _interpolador(self.fr, self.m))).H

    def marco_eventos(self, k: int, piezas) -> np.ndarray:
        """Suma las piezas (inicio a fr/m, audio (2, n) a fr/m) en el trozo k, con el lugar: (2, L).

        Se suman en todo el marco (con la pre-lectura) y se filtran juntas: la
        cola de un evento de justo antes del trozo también entra, exacta.
        """
        m, n = self.m, self.N // self.m
        a0 = (k * self.L - self.P) // m
        for clave in [c for c, (inicio, audio) in self._eventos.items() if inicio + audio.shape[1] <= a0]:
            del self._eventos[clave]  # ya terminó: leyendo para adelante no vuelve a hacer falta
        marco = np.zeros((2, n))
        hay = False
        for inicio, audio in piezas:
            i0, i1 = max(inicio, a0), min(inicio + audio.shape[1], a0 + n)
            if i1 > i0:
                marco[:, i0 - a0:i1 - a0] += audio[:, i0 - inicio:i1 - inicio]
                hay = True
        if not hay:
            return np.zeros((2, self.L))
        X = np.fft.rfft(marco, axis=1)
        if m > 1:
            # Intercalar ceros (subir de fr/m a fr) repite el espectro: el de N muestras es el de
            # N/m repetido. Sale de la FFT chica, sin hacer la grande (y da lo mismo).
            if self._repeticion is None:
                j = np.arange(self.N // 2 + 1) % n
                espejo = j > n // 2
                self._repeticion = (np.where(espejo, n - j, j), espejo)
            indices, espejo = self._repeticion
            X = X[:, indices]
            X[:, espejo] = np.conj(X[:, espejo])
        return np.fft.irfft(X * self._H_lugar, self.N, axis=1)[:, self.P:]


_RECETAS: dict[str, type] = {}


def _receta(tipo: str):
    def registrar(clase):
        _RECETAS[tipo] = clase
        return clase
    return registrar


def _evento(**datos) -> SimpleNamespace:
    return SimpleNamespace(**datos)


def _oleadas(fondo: _Fondo, nombre: str, t: np.ndarray, tasa: float, duracion, piso: float):
    """Envolventes (izquierda, derecha) de autos lejanos: subidas y bajadas que cruzan de un lado al otro."""

    def generar(rng, t0):
        eventos = []
        for _ in range(int(rng.poisson(tasa * 4.0))):
            d = rng.uniform(*duracion)
            centro = t0 + rng.uniform(0.0, 4.0)
            p0 = rng.uniform(-0.9, 0.9)
            eventos.append(_evento(inicio=centro - d / 2, fin=centro + d / 2, amp=math.exp(0.4 * rng.standard_normal()),
                                   p0=p0, p1=float(np.clip(p0 + rng.uniform(-0.9, 0.9), -1.0, 1.0))))
        return eventos

    izq = np.full_like(t, piso * piso)
    der = izq.copy()
    for e in fondo.eventos_en(nombre, t[0], t[-1], 4.0, duracion[1] / 2, duracion[1] / 2, generar):
        u = np.clip((t - e.inicio) / (e.fin - e.inicio), 0.0, 1.0)
        forma = e.amp * np.sin(np.pi * u) ** 2
        g_izq, g_der = _paneo(e.p0 + (e.p1 - e.p0) * u)
        izq += (forma * g_izq) ** 2
        der += (forma * g_der) ** 2
    return np.sqrt(izq), np.sqrt(der)


def _rafagas(fondo: _Fondo, t: np.ndarray, tasa: float, fuerza: float) -> np.ndarray:
    """Velocidad del viento (relativa, alrededor de 1) en los instantes t: deriva lenta más ráfagas."""

    def generar(rng, t0):
        eventos = []
        for _ in range(min(3, int(rng.poisson(tasa * 4.0)))):
            inicio = t0 + rng.uniform(0.0, 4.0)
            subida, meseta, bajada = rng.uniform(1.0, 2.5), rng.uniform(0.0, 1.5), rng.uniform(1.2, 4.0)
            eventos.append(_evento(inicio=inicio, fin=inicio + subida + meseta + bajada, subida=subida,
                                   bajada=bajada, fuerza=fuerza * rng.uniform(0.3, 1.0)))
        return eventos

    u = 1.0 + 0.15 * fondo.suave("viento_lento", t, 9.0) + 0.08 * fondo.suave("viento_medio", t, 2.3)
    for e in fondo.eventos_en("rafagas", float(np.min(t)), float(np.max(t)), 4.0, 0.0, 8.1, generar):
        sube = np.clip((t - e.inicio) / e.subida, 0.0, 1.0)
        baja = np.clip((e.fin - t) / e.bajada, 0.0, 1.0)
        u = u + e.fuerza * (0.5 - 0.5 * np.cos(np.pi * sube)) * (0.5 - 0.5 * np.cos(np.pi * baja))
    return np.maximum(u, 0.05)


_HILOS: Optional[ThreadPoolExecutor] = None
_CANDADO_HILOS = threading.Lock()


def _hilos() -> ThreadPoolExecutor:
    """Unos pocos hilos para sintetizar pasadas en paralelo (numpy suelta el GIL en las cuentas grandes)."""
    global _HILOS
    with _CANDADO_HILOS:
        if _HILOS is None:
            _HILOS = ThreadPoolExecutor(max_workers=max(1, min(4, os.cpu_count() or 1)),
                                        thread_name_prefix="ambientes")
        return _HILOS


def _sintetizar_pasada(evento, fr: int) -> np.ndarray:
    return _pasada(evento.pasada, fr)


class _ConVehiculos(_Fondo):
    """Fondos con vehículos que pasan (calle y ciudad): calendario por ventana de 4 s.

    Cada pasada es una función pura de sus parámetros: cuando se van a leer
    varios trozos (``anticipar``), las que faltan se sintetizan en paralelo, en
    unos pocos hilos. El resultado es idéntico; solo cambia cuánto se tarda.
    """

    ADELANTE = 8   # trozos que se anticipan, a lo sumo
    MAX_JUNTOS = 10  # pasadas que se sintetizan de una vez, a lo sumo (la caché guarda 12)

    def trafico(self, nombre: str, tasa: float, distancia, x_max: float, clases) -> None:
        """Define los vehículos del fondo (en ``preparar``): por segundo, a qué distancia, de qué clase."""
        nombres = [c for c, _ in clases]
        pesos = np.array([p for _, p in clases], np.float64)
        pesos = pesos / pesos.sum()
        lado_max = x_max / 7.0  # 7 m/s: el más lento

        def generar(rng, t0):
            eventos = []
            for _ in range(int(tasa * 4.0 + rng.random())):
                cerca = t0 + rng.uniform(0.0, 4.0)
                p = _nueva_pasada(rng, nombres[int(rng.choice(len(nombres), p=pesos))], distancia, x_max)
                eventos.append(_evento(inicio=cerca - p.antes, fin=cerca + p.despues, pasada=p))
            return eventos

        self._trafico = (nombre, lado_max, generar)

    def _pasadas(self, k0: int, k1: int) -> list:
        """Las pasadas que suenan en los marcos de los trozos k0 a k1."""
        nombre, lado_max, generar = self._trafico
        return self.eventos_en(nombre, (k0 * self.L - self.P) / self.fr, (k1 + 1) * self.L / self.fr, 4.0,
                               lado_max, lado_max, generar)

    def anticipar(self, k0: int, k1: int) -> None:
        faltan = [e for e in self._pasadas(k0, min(k1, k0 + self.ADELANTE)) if e.clave not in self._eventos]
        faltan = faltan[:self.MAX_JUNTOS]
        if len(faltan) < 2:
            return  # una sola: no vale la pena (la sintetiza ``vehiculos`` cuando haga falta)
        fr = self.fr // self.m
        for e, audio in zip(faltan, _hilos().map(lambda ev: _sintetizar_pasada(ev, fr), faltan)):
            self.audio_evento(e, lambda _e, _fr, audio=audio: audio)

    def vehiculos(self, k: int) -> np.ndarray:
        return self.marco_eventos(k, [self.audio_evento(e, _sintetizar_pasada) for e in self._pasadas(k, k)])


# ---------------------------------------------------------------------------
# Fondos
# ---------------------------------------------------------------------------

@_receta("ciudad")
class _Ciudad(_ConVehiculos):
    """Rumor grave de muchas calles, autos lejanos que van y vienen y, cada tanto, uno a media cuadra."""

    PENDIENTE_DB = 12.0
    AJUSTE_DB = -5.5
    SUBMUESTREO = 3  # los vehículos a media cuadra ya llegan opacos: alcanza con 16 kHz

    def preparar(self):
        i = self.intensidad
        self.capa("rumor",
                  (0.0, lambda f: _pa(f, 28.0) * _inclinacion(f, -4.5, 100.0) * _campana(f, 75.0, 1.0, 3.0)
                   * _pb(f, 1300.0)),
                  (-20.0, lambda f: _pa(f, 2500.0) * _pb(f, 9000.0)))
        self.capa("autos", lambda f: _pa(f, 150.0) * _campana(f, 750.0, 1.3, 6.0) * _pb(f, 2800.0, 3))
        self.preparar_lugar(1.6, 0.45, -1.0, ecos=4, eco_retardo=(0.05, 0.3), eco_nivel=(0.15, 0.35))
        self.tasa_lejanos = 0.5 + 0.6 * i  # autos lejanos por segundo
        self.trafico("media_cuadra", 0.03 + 0.07 * i, (18.0, 45.0), 32.0,
                     (("auto", 0.6), ("colectivo", 0.25), ("moto", 0.15)))

    def trozo(self, k):
        t = self.tiempos(k)
        r = self.ruido(k, ("rumor", "autos"))
        rumor = r["rumor"] * self.a_muestras(self.deriva("rumor", t, 1.8, (7.3, 19.0)))
        autos = r["autos"] * self.estereo(*_oleadas(self, "lejanos", t, self.tasa_lejanos, (3.0, 8.0), 0.15))
        cerca = self.vehiculos(k)
        return rumor + _db(-2.0) * autos + _db(18.0) * cerca


@_receta("calle")
class _Calle(_ConVehiculos):
    """Vereda de una calle con tránsito: autos, motos y colectivos que pasan cerca, con Doppler."""

    PENDIENTE_DB = 8.0
    AJUSTE_DB = 10.7

    def preparar(self):
        i = self.intensidad
        self.capa("rumor", lambda f: _pa(f, 30.0) * _inclinacion(f, -3.5, 100.0) * _campana(f, 90.0, 1.0, 3.0)
                  * _pb(f, 2200.0))
        self.capa("autos", lambda f: _pa(f, 150.0) * _campana(f, 800.0, 1.3, 6.0) * _pb(f, 3500.0, 3))
        self.preparar_lugar(1.1, 0.45, 4.0, ecos=3, eco_retardo=(0.025, 0.07), eco_nivel=(0.25, 0.45))
        # Uno cada 3 s a intensidad 0,5; uno cada 2 s a intensidad 1.
        self.trafico("pasan", 0.1 + 0.4 * i, (2.5, 9.0), 24.0, (("auto", 0.58), ("moto", 0.27), ("colectivo", 0.15)))

    def trozo(self, k):
        t = self.tiempos(k)
        r = self.ruido(k, ("rumor", "autos"))
        rumor = r["rumor"] * self.a_muestras(self.deriva("rumor", t, 1.5, (5.3, 17.0)))
        autos = r["autos"] * self.estereo(*_oleadas(self, "lejanos", t, 0.5, (3.0, 7.0), 0.35))
        cerca = self.vehiculos(k)
        # Un auto a 3-4 m sobresale unos 12 a 15 dB del tránsito de fondo.
        return _db(-22.0) * rumor + _db(-24.0) * autos + cerca


@_receta("lluvia")
class _Lluvia(_Fondo):
    """Lluvia: siseo de millones de gotas, gotitas que crepitan cerca, algunas grandes y "plinks" en los charcos."""

    PENDIENTE_DB = 20.0
    AJUSTE_DB = -1.6

    def preparar(self):
        i = self.intensidad
        rng = self.azar("gotas")
        self.capa("lluvia",  # el siseo de las gotas y, cuanto más fuerte, más rumor grave
                  (6.0 * (i - 0.5), lambda f: _pa(f, 450.0) * _campana(f, 4200.0, 1.4, 7.0) * _pb(f, 12000.0)
                   * _inclinacion(f, -1.5, 1000.0)),
                  (-9.0 + 12.0 * (i - 0.5), lambda f: _pa(f, 60.0) * _campana(f, 300.0, 1.3, 5.0) * _pb(f, 2000.0)))
        self.gota = self.golpe(_golpe(rng, self.fr, 0.012, modos=10, banda=(1800.0, 9000.0), tau=(0.0001, 0.0004),
                                      ruido=0.6, ruido_tau=0.0008, ruido_curva=lambda f: _pa(f, 2000.0)))
        self.grande = self.golpe(_golpe(rng, self.fr, 0.06, modos=8, banda=(500.0, 3000.0), tau=(0.002, 0.008),
                                        ruido=0.5, ruido_tau=0.004,
                                        ruido_curva=lambda f: _pa(f, 1000.0) * _pb(f, 5000.0)))
        self.tasa_gotas = 250.0 + 2600.0 * i ** 1.3
        self.tasa_grandes = 1.5 + 10.0 * i
        self.tasa_plinks = 1.0 + 6.0 * i
        self.niveles = {"gotas": _db(-3.0 - 4.0 * (i - 0.5)), "grandes": _db(-15.0), "plinks": _db(-17.0)}

    def _cuanta(self, t):
        return self.deriva("lluvia", t, 2.0, (2.9, 8.3, 23.0))  # la lluvia sube y baja

    def trozo(self, k):
        n = self.niveles
        lluvia = self.ruido(k, ("lluvia",))["lluvia"] * self.a_muestras(self._cuanta(self.tiempos(k)))
        gotas = self.sonar(k, "gotas", self.gota, 2.5 * self.tasa_gotas, 0.6, 0.9,
                           lambda tt: np.clip(self._cuanta(tt) ** 2 / 2.5, 0.0, 1.0))
        grandes = self.sonar(k, "grandes", self.grande, self.tasa_grandes, 0.4, 0.9)
        plinks = self.granos(k, "plinks", self.tasa_plinks, (1100.0, 4200.0), (0.004, 0.012), (0.15, 0.6))
        return lluvia + n["gotas"] * gotas + n["grandes"] * grandes + n["plinks"] * plinks


@_receta("agua")
class _Agua(_Fondo):
    """Agua que corre: burbujas que suben de tono, gorgoteo, salpicaduras; con intensidad, el rugido de un río."""

    PENDIENTE_DB = 12.0
    AJUSTE_DB = -3.4

    def preparar(self):
        i = self.intensidad
        rng = self.azar("agua")
        centro = 650.0 - 250.0 * i
        self.capa("corriente", lambda f: _pa(f, 100.0) * _campana(f, centro, 1.4, 7.0) * _pb(f, 4500.0)
                  * _inclinacion(f, -2.0, 500.0))
        self.capa("rugido", lambda f: _pa(f, 35.0) * _campana(f, 150.0, 1.0, 6.0) * _pb(f, 800.0))
        self.salpicadura = self.golpe(_golpe(rng, self.fr, 0.08, modos=6, banda=(600.0, 2500.0), tau=(0.005, 0.015),
                                             ruido=0.6, ruido_tau=0.02,
                                             ruido_curva=lambda f: _pa(f, 1000.0) * _pb(f, 6000.0)))
        self.tasa_burbujas = 110.0
        self.banda_burbujas = (500.0 - 200.0 * i, 2800.0 - 1200.0 * i)
        self.niveles = {"rugido": _db(-14.0 + 22.0 * (i - 0.5)), "burbujas": _db(1.0 - 8.0 * (i - 0.5)),
                        "salpicaduras": _db(-12.0)}

    def trozo(self, k):
        n = self.niveles
        t = self.tiempos(k)
        r = self.ruido(k, ("corriente", "rugido"))
        lento = self.deriva("caudal", t, 1.5, (4.3, 13.0))
        gorgoteo = np.exp(0.3 * self.suave("gorgoteo", t, 0.07))  # sube y baja rápido, sin cortarse nunca
        borboteo = lambda tt: np.clip(0.55 + 0.5 * self.suave("borboteo", tt, 0.25), 0.0, 1.0)
        burbujas = self.granos(k, "burbujas", self.tasa_burbujas, self.banda_burbujas, (0.0015, 0.007), (0.1, 0.5),
                               aceptar=borboteo)
        salpica = self.sonar(k, "salpicaduras", self.salpicadura, 5.0, 0.6, 0.9)
        return (r["corriente"] * self.a_muestras(lento * gorgoteo) + n["rugido"] * r["rugido"] * self.a_muestras(lento)
                + n["burbujas"] * burbujas + n["salpicaduras"] * salpica)


def _forma_ola(x: np.ndarray, o) -> dict:
    """Envolventes de una ola por banda, ``x`` s después de que empieza a crecer.

    Crece (rumor que sube), rompe (golpe grave y estallido) y lava la orilla (un
    siseo largo de espuma, con la resaca que vuelve un par de segundos después).
    """
    d = x - o.crece
    dd = np.maximum(d, 0.0)
    crece = np.where(d < 0.0, np.clip(x / o.crece, 0.0, 1.0) ** 2.5, np.exp(-dd / 0.4))  # sigue mientras rompe
    rompe = np.clip(dd / 0.3, 0.0, 1.0)
    golpe = rompe * rompe * (3.0 - 2.0 * rompe)
    estalla = np.clip((dd - 0.05) / 0.4, 0.0, 1.0)
    espuma = estalla * estalla * (3.0 - 2.0 * estalla)
    resaca = np.exp(-0.5 * ((d - 0.8 * o.lavado) / 0.8) ** 2) * (d > 0.0)  # la resaca viene después de romper
    # En los últimos 2 s la ola se apaga del todo (ya está unos 30 dB abajo): en ``fin`` vale 0,
    # así no hay salto cuando un trozo deja de contarla.
    apagar = np.clip((o.fin - o.inicio - x) / 2.0, 0.0, 1.0)
    apagar = apagar * apagar * (3.0 - 2.0 * apagar)
    return {
        "bajo": (0.45 * crece + golpe * np.exp(-dd / 0.9)) * apagar,
        "medio": (0.35 * crece + golpe * 0.9 * np.exp(-dd / 1.4)) * apagar,
        "alto": (0.12 * crece + espuma * (0.55 * np.exp(-dd / 0.7) + 0.45 * np.exp(-dd / (o.lavado / 2.2)))
                 + 0.25 * resaca) * apagar,
        "espuma": (espuma * np.exp(-dd / (o.lavado / 2.0)) + 0.4 * resaca) * apagar,
    }


@_receta("olas")
class _Olas(_Fondo):
    """La orilla del mar: olas que crecen, rompen y lavan, sobre el rumor de las que rompen más lejos."""

    PENDIENTE_DB = 10.0
    AJUSTE_DB = 5.4

    def preparar(self):
        i = self.intensidad
        rng = self.azar("olas")
        self.capa("bajo", lambda f: _pa(f, 30.0) * _campana(f, 80.0, 1.0, 4.0) * _pb(f, 280.0))
        self.capa("medio", lambda f: _pa(f, 150.0) * _campana(f, 700.0, 1.5, 4.0) * _pb(f, 3000.0))
        self.capa("alto", lambda f: _pa(f, 1500.0) * _campana(f, 5000.0, 1.2, 4.0) * _pb(f, 12000.0))
        self.espuma = self.golpe(_golpe(rng, self.fr, 0.006, ruido=1.0, ruido_tau=0.0005,
                                        ruido_curva=lambda f: _pa(f, 3000.0)))
        self.periodo = 10.0 - 3.0 * i
        self.fuerza = 0.7 + 0.6 * i
        self.piso = {"bajo": 0.22, "medio": 0.18, "alto": 0.06, "espuma": 0.05}  # las que rompen más lejos
        self.niveles = {"bajo": _db(-1.0), "medio": _db(-3.0), "alto": _db(-6.0), "espuma": _db(-12.0)}

    def _nuevas(self, rng, t0):
        # Una ola por ventana, cerca del medio: llegan cada 0,5 a 1,5 períodos, como en una playa.
        crece, lavado = rng.uniform(1.2, 2.5), rng.uniform(3.0, 6.0)
        inicio = t0 + rng.uniform(0.25, 0.75) * self.periodo
        return [_evento(inicio=inicio, fin=inicio + crece + lavado + 5.0, crece=crece, lavado=lavado,
                        amp=self.fuerza * math.exp(0.25 * rng.standard_normal()), pan=rng.uniform(-0.4, 0.4))]

    def trozo(self, k):
        t = self.tiempos(k)
        bandas = ("bajo", "medio", "alto", "espuma")
        lejos = self.deriva("lejos", t, 2.0, (3.7, 11.0)) ** 2
        izq = {b: self.piso[b] ** 2 * lejos for b in bandas}
        der = {b: v.copy() for b, v in izq.items()}
        for o in self.eventos_en("olas", t[0], t[-1], self.periodo, 0.0, 14.0, self._nuevas):
            formas = _forma_ola(t - o.inicio, o)
            g_izq, g_der = _paneo(o.pan)
            for b in bandas:
                izq[b] += (o.amp * g_izq * formas[b]) ** 2
                der[b] += (o.amp * g_der * formas[b]) ** 2
        capas = self.ruido(k, ("bajo", "medio", "alto"))
        capas["espuma"] = self.sonar(k, "espuma", self.espuma, 1500.0, 0.5, 0.9)
        salida = np.zeros((2, self.L))
        for b in bandas:
            salida += self.niveles[b] * capas[b] * self.estereo(np.sqrt(izq[b]), np.sqrt(der[b]))
        return salida


@_receta("viento")
class _Viento(_Fondo):
    """Viento afuera: soplido con ráfagas que suben y aclaran el sonido, hojas y un silbido en las ráfagas fuertes."""

    PENDIENTE_DB = 14.0
    AJUSTE_DB = -10.8

    def preparar(self):
        i = self.intensidad
        rng = self.azar("viento")
        self.capa("soplido",
                  (-4.0, lambda f: _pa(f, 35.0) * _campana(f, 120.0, 1.2, 4.0) * _pb(f, 350.0)),
                  (0.0, lambda f: _pa(f, 180.0) * _campana(f, 650.0, 1.4, 6.0) * _pb(f, 2600.0)))
        self.capa("agudo", lambda f: _pa(f, 1400.0) * _campana(f, 3500.0, 1.2, 4.0) * _pb(f, 9000.0))
        self.hoja = self.golpe(_golpe(rng, self.fr, 0.008, modos=6, banda=(2000.0, 7000.0), tau=(0.00015, 0.0005),
                                      ruido=0.8, ruido_tau=0.001, ruido_curva=lambda f: _pa(f, 1500.0)))
        self.tasa_rafagas = 0.3 + 0.2 * i
        self.f_silbido = rng.uniform(380.0, 700.0)

    def _u(self, t):
        return _rafagas(self, t, self.tasa_rafagas, 0.7)

    def trozo(self, k):
        t = self.tiempos(k)
        u = self._u(t)
        r = self.ruido(k, ("soplido", "agudo"))
        hojas = self.sonar(k, "hojas", self.hoja, 900.0, 0.7, 0.9,
                           lambda tt: np.clip((self._u(tt) - 0.6) / 1.4, 0.0, 1.0) ** 1.5)
        fase = self.fase(k, "silbido", lambda tt: self.f_silbido * (0.75 + 0.35 * self._u(tt))
                         * (1.0 + 0.02 * self.suave("silbido_f", tt, 0.05)), 4.0)
        silbido = np.sin(_DOS_PI * fase) + 0.3 * np.sin(2.0 * _DOS_PI * fase + 1.3)
        silbido *= self.a_muestras(np.clip(u - 1.1, 0.0, None) ** 1.5
                                   * np.maximum(0.0, 1.0 + 0.5 * self.suave("silbido_a", t, 0.03)))
        return (r["soplido"] * self.a_muestras(u ** 1.5)
                + _db(-6.0) * r["agudo"] * self.a_muestras(u ** 2.2) + _db(-9.0) * hojas
                + _db(-24.0) * silbido * np.array([[1.0], [0.8]]))


@_receta("oficina")
class _Oficina(_Fondo):
    """Oficina: el soplido del aire acondicionado, el zumbido de la red y el ventilador, y alguien que escribe lejos."""

    PENDIENTE_DB = 8.0
    AJUSTE_DB = -0.8

    def preparar(self):
        i = self.intensidad
        rng = self.azar("equipos")
        self.capa("aire",  # el soplido del equipo y el de la rejilla
                  (0.0, lambda f: _pa(f, 55.0) * _campana(f, 250.0, 1.3, 7.0) * _inclinacion(f, -3.0, 500.0)
                   * _pb(f, 6000.0)),
                  (-8.0, lambda f: _pa(f, 800.0) * _campana(f, 2500.0, 1.0, 4.0) * _pb(f, 7000.0)))
        self.f_aspas = rng.uniform(110.0, 170.0)  # paso de las aspas del ventilador
        # Sobre todo el segundo armónico (100 Hz), que es el que hacen los transformadores y los balastos.
        base = np.array([0.25, 1.0, 0.35, 0.3, 0.12, 0.15, 0.06, 0.05])
        self.tablas_red = [_tabla_red(rng, base * rng.uniform(0.6, 1.4, 8)) for _ in range(2)]
        # Un teclado a unos metros: el clic llega redondeado y con bastante sala.
        self.tecla = self.golpe(_golpe(rng, self.fr, 0.3, modos=8, banda=(1200.0, 4500.0), tau=(0.002, 0.005),
                                       ruido=0.3, ruido_tau=0.003, ruido_curva=lambda f: _pa(f, 800.0) * _pb(f, 5000.0),
                                       sala_rt60=0.45, sala_db=-5.0))
        self.barra = self.golpe(_golpe(rng, self.fr, 0.3, modos=8, banda=(500.0, 2500.0), tau=(0.004, 0.01),
                                       ruido=0.3, ruido_tau=0.004, ruido_curva=lambda f: _pa(f, 400.0) * _pb(f, 3000.0),
                                       sala_rt60=0.45, sala_db=-5.0))
        self.umbral = 1.0 - 1.3 * i  # cuánto escriben: más intensidad, más seguido

    def _tecleando(self, t):
        """Si alguien está escribiendo en ese momento (rachas de varios segundos y pausas)."""
        racha = self.suave("rachas", t, 4.0) + 0.5 * self.suave("rachas_largas", t, 13.0)
        pausa = self.suave("pausas", t, 0.6) > -0.7
        return ((racha > self.umbral) & pausa).astype(np.float64)

    def trozo(self, k):
        t = self.tiempos(k)
        aire = self.ruido(k, ("aire",))["aire"] * self.a_muestras(self.deriva("aire", t, 0.8, (3.1, 11.0)))
        mezcla = self.a_muestras(0.5 + 0.5 * np.tanh(self.suave("red_mezcla", t, 5.0)))
        zumbido = (1.0 - mezcla) * self.onda_red(k, self.tablas_red[0]) + mezcla * self.onda_red(k, self.tablas_red[1])
        zumbido *= self.a_muestras(self.deriva("red_nivel", t, 1.0, (2.9, 9.0)))
        aspas = self.fase(k, "aspas", lambda tt: self.f_aspas * (1.0 + 0.004 * self.suave("aspas_f", tt, 1.7)), 8.0)
        ventilador = np.sin(_DOS_PI * aspas) + 0.35 * np.sin(2.0 * _DOS_PI * aspas + 1.1)
        ventilador *= self.a_muestras(np.maximum(0.0, 1.0 + 0.25 * self.suave("aspas_a", t, 0.4)))
        # Al soltar la tecla, un clic más suave, entre 70 y 130 ms después.
        suelta = (lambda tt: 0.1 + 0.025 * np.clip(self.suave("suelta", tt, 0.05), -1.2, 1.2), 0.45)
        teclado = (self.sonar(k, "teclas", self.tecla, 7.0, 0.45, 0.4, self._tecleando, suelta)
                   # La barra se toca 10 veces menos: a igual potencia media, cada golpe saldría 10 dB más
                   # fuerte. Queda unos 3 dB arriba de una tecla, como en un teclado de verdad.
                   + _db(-7.0) * self.sonar(k, "barra", self.barra, 0.7, 0.3, 0.4, self._tecleando, suelta))
        return (aire + _db(-18.0) * zumbido * np.array([[1.0], [0.9]])
                + _db(-22.0) * ventilador * np.array([[0.85], [1.0]]) + _db(-13.0) * teclado)


@_receta("habitacion")
class _Habitacion(_Fondo):
    """El aire de una habitación: rumor grave del edificio, un soplo apenas y el tránsito lejos, tras la ventana."""

    AJUSTE_DB = -1.4

    def preparar(self):
        rng = self.azar("habitacion")
        self.capa("aire",
                  (0.0, lambda f: _pa(f, 22.0) * _inclinacion(f, -4.5, 100.0) * _campana(f, 60.0, 1.2, 4.0)
                   * _pb(f, 900.0)),
                  (-14.0, lambda f: _pa(f, 1500.0, 1) * _pb(f, 8000.0)))
        self.capa("afuera", lambda f: _pa(f, 70.0) * _campana(f, 300.0, 1.2, 4.0) * _pb(f, 1200.0, 3))
        self.tabla_red = _tabla_red(rng, (0.3, 1.0, 0.2, 0.25, 0.0, 0.1))

    def trozo(self, k):
        t = self.tiempos(k)
        r = self.ruido(k, ("aire", "afuera"))
        afuera = r["afuera"] * self.estereo(*_oleadas(self, "afuera", t, 0.12, (4.0, 9.0), 0.3))
        zumbido = self.onda_red(k, self.tabla_red) * self.a_muestras(self.deriva("red", t, 1.5, (4.1, 13.0)))
        return (r["aire"] * self.a_muestras(self.deriva("aire", t, 1.0, (5.3, 17.0))) + _db(-8.0) * afuera
                + _db(-20.0) * zumbido)


@_receta("auto")
class _Auto(_Fondo):
    """Adentro de un auto en la ruta: rodar grave, neumáticos, viento en las puertas, motor y juntas del pavimento.

    La intensidad es la velocidad: de 40 km/h (0) a 130 km/h (1). El nivel sube con
    la velocidad como en un auto de verdad (el rodar y, más rápido, el viento).
    """

    AJUSTE_DB = -1.9

    def preparar(self):
        i = self.intensidad
        rng = self.azar("auto")
        self.kmh = 40.0 + 90.0 * i
        v = self.kmh / 85.0
        # Rodar, neumáticos y viento cambian juntos (la velocidad varía poco): una sola capa.
        self.capa("ruta",
                  (20.0 * math.log10(v) * 1.6, lambda f: _pa(f, 18.0) * _campana(f, 42.0, 0.5, 9.0)
                   * _campana(f, 115.0, 0.45, 6.0) * _pb(f, 250.0)),
                  (-5.0 + 20.0 * math.log10(v) * 1.9, lambda f: _pa(f, 120.0) * _campana(f, 450.0, 1.1, 5.0)
                   * _pb(f, 1500.0, 3)),
                  (-9.0 + 20.0 * math.log10(v) * 2.9, lambda f: _pa(f, 350.0) * _campana(f, 1300.0, 1.5, 3.0)
                   * _pb(f, 5500.0)))
        self.capa("paso", lambda f: _pa(f, 70.0) * _campana(f, 250.0, 1.2, 4.0) * _pb(f, 2000.0))
        rpm_ref = 85.0 * 30.0
        self.tabla_motor = _tabla_motor(rng, 4, 0.22, 0.3, 280.0 / (rpm_ref / 120.0),
                                        int(0.45 * self.fr / (140.0 * 30.0 / 120.0)))
        # Golpe sordo de la rueda en la junta; con la rueda de atrás (hasta 0,26 s después) entra en la pre-lectura.
        golpe = _golpe(rng, self.fr, 0.22, modos=6, banda=(28.0, 70.0), tau=(0.04, 0.09), ataque=0.006)
        golpe += 0.6 * _golpe(rng, self.fr, 0.22, modos=6, banda=(90.0, 300.0), tau=(0.01, 0.025), ataque=0.002)
        golpe += 0.4 * _golpe(rng, self.fr, 0.22, ruido=1.0, ruido_tau=0.006, ataque=0.0008,
                              ruido_curva=lambda f: _pa(f, 600.0) * _pb(f, 2500.0))
        self.junta = self.golpe(golpe / np.sqrt(np.sum(golpe * golpe, axis=1, keepdims=True)))
        self.motor_db = -14.0 + 20.0 * math.log10(v) * 0.8

    def _kmh(self, t):
        return self.kmh * (1.0 + 0.05 * self.suave("velocidad", t, 11.0) + 0.02 * self.suave("velocidad_c", t, 3.7))

    def _camiones(self, t):
        """Envolventes (izquierda, derecha) de camiones que pasan por el otro carril: un "fuuu" de un par de s."""

        def generar(rng, t0):
            if rng.random() > 0.15:
                return []
            inicio = t0 + rng.uniform(0.0, 4.0)
            return [_evento(inicio=inicio, fin=inicio + rng.uniform(2.0, 3.5), pan=rng.choice((-0.6, 0.6)))]

        izq = np.zeros_like(t)
        der = np.zeros_like(t)
        for e in self.eventos_en("camiones", t[0], t[-1], 4.0, 0.0, 3.5, generar):
            u = np.clip((t - e.inicio) / (e.fin - e.inicio), 0.0, 1.0)
            forma = np.sin(np.pi * u ** 0.7) ** 2
            g_izq, g_der = _paneo(e.pan)
            izq += forma * g_izq
            der += forma * g_der
        return izq, der

    def trozo(self, k):
        t = self.tiempos(k)
        v = self._kmh(t) / self.kmh
        r = self.ruido(k, ("ruta", "paso"))
        ruta = r["ruta"] * self.a_muestras(v ** 2.0 * self.deriva("pavimento", t, 1.5, (13.0, 31.0)))
        paso = r["paso"] * self.estereo(*self._camiones(t))
        fase = self.fase(k, "motor", lambda tt: self._kmh(tt) * 30.0 / 120.0, 16.0)
        motor = _leer_tabla(self.tabla_motor, fase) * self.a_muestras(v ** 0.8)
        juntas = self.sonar(k, "juntas", self.junta, 0.12, 0.25, 0.1,
                            segundo=(lambda tt: np.minimum(2.65 / (self._kmh(tt) / 3.6), 0.27), 0.8))
        return ruta + _db(self.motor_db) * motor + _db(-10.0) * paso + _db(-20.0) * juntas


@_receta("colectivo")
class _Colectivo(_Fondo):
    """Arriba de un colectivo: el diésel en ralentí, arranca, estira cada cambio, va, frena, para y abre las puertas.

    El manejo sale de un ciclo de 40 s por ranura (parada, arranque con 3 o 4
    cambios, un tramo parejo y la frenada), con su semilla. La fase del motor se
    integra en esas mismas ranuras, así que el "entero de ciclos" no se nota.
    """

    PENDIENTE_DB = 8.0
    CICLO = 40.0
    RELACIONES = (6.0, 10.5, 16.0, 22.0)  # km/h cada 1000 rpm, por cambio

    def preparar(self):
        i = self.intensidad
        rng = self.azar("colectivo")
        self.ralenti = rng.uniform(640.0, 720.0)
        self.capa("golpeteo", lambda f: _pa(f, 600.0) * _campana(f, 1600.0, 1.0, 6.0) * _pb(f, 4000.0))
        self.capa("andar",  # el rodar grave y el aire de las ventanillas, que crecen con la velocidad
                  (0.0, lambda f: _pa(f, 25.0) * _campana(f, 60.0, 0.7, 6.0) * _pb(f, 300.0)),
                  (-12.0, lambda f: _pa(f, 300.0) * _campana(f, 1000.0, 1.5, 3.0) * _pb(f, 5000.0)))
        self.tabla_motor = _tabla_motor(rng, 6, 0.11, 1.0, 350.0 / (1500.0 / 120.0),
                                        int(0.45 * self.fr / (2400.0 / 120.0)))
        self.chapa = self.golpe(_golpe(rng, self.fr, 0.05, modos=10, banda=(700.0, 3500.0), tau=(0.002, 0.012),
                                       ruido=0.3, ruido_tau=0.004,
                                       ruido_curva=lambda f: _pa(f, 800.0) * _pb(f, 5000.0)))
        self.preparar_lugar(0.4, 0.3, 0.0)
        self.empuje = 0.8 + 0.4 * i  # cuánto le exige el chofer
        self._ciclos: OrderedDict = OrderedDict()

    def _ciclo(self, s: int):
        """Del ciclo ``s``: (puntos (tiempo desde el principio de la ranura, rpm, carga, km/h), puertas (s))."""
        c = self._ciclos.get(s)
        if c is not None:
            return _recordar(self._ciclos, s, c, 4)
        rng = self.azar("ciclo", s)
        r0 = self.ralenti
        parada = rng.uniform(2.5, 7.0)
        puntos = [(0.0, r0, 0.25, 0.0), (parada, r0, 0.25, 0.0)]
        t = parada + 0.7
        puntos.append((t, 1000.0, 0.9, 3.0))
        marchas = 3 if rng.random() < 0.6 else 4
        tope = rng.uniform(1700.0, 1950.0) * self.empuje
        kmh, rpm = 3.0, 1000.0
        for g in range(marchas):
            ultima = g == marchas - 1
            rpm = rng.uniform(1450.0, 1700.0) * self.empuje if ultima else tope * rng.uniform(0.95, 1.05)
            t += rng.uniform(2.0, 3.0) * (1.0 + 0.3 * g)
            kmh = rpm / 1000.0 * self.RELACIONES[g]
            puntos.append((t, rpm, 1.0, kmh))
            if not ultima:  # el cambio: suelta, las rpm caen, vuelve a acelerar
                nueva = kmh / self.RELACIONES[g + 1] * 1000.0
                puntos += [(t + 0.15, rpm * 0.97, 0.1, kmh), (t + 0.65, nueva, 0.15, kmh),
                           (t + 0.85, nueva * 1.02, 1.0, kmh)]
                t += 0.85
        frenada = rng.uniform(5.0, 7.0)
        t_freno = self.CICLO - 1.0 - frenada
        puntos += [(t_freno, rpm, 0.45, kmh), (t_freno + 0.7 * frenada, 950.0, 0.05, 0.2 * kmh),
                   (self.CICLO - 1.0, r0, 0.25, 0.0), (self.CICLO, r0, 0.25, 0.0)]
        puertas = []
        if rng.random() < 0.75:
            puertas.append(rng.uniform(0.4, 1.0))
        if rng.random() < 0.6 and parada > 4.0:
            puertas.append(parada - rng.uniform(1.0, 1.8))
        return _recordar(self._ciclos, s, (np.array(puntos).T, puertas), 4)

    def _manejo(self, t: np.ndarray, campo: int) -> np.ndarray:
        """rpm (1), carga (2) o km/h (3) en los instantes t."""
        ranura = np.floor(t / self.CICLO).astype(np.int64)
        salida = np.empty_like(t)
        for s in np.unique(ranura):
            sel = ranura == s
            tabla = self._ciclo(int(s))[0]
            salida[sel] = np.interp(t[sel] - s * self.CICLO, tabla[0], tabla[campo])
        return salida

    def _rpm(self, t):
        return self._manejo(t, 1) * (1.0 + 0.012 * self.suave("rpm", t, 1.3) + 0.005 * self.suave("rpm_c", t, 0.21))

    def _puertas(self, k):
        def generar(rng, t0):
            s = int(round(t0 / self.CICLO))
            return [_evento(inicio=t0 + p, fin=t0 + p + 1.8, semilla=_clave(self.semilla, "puerta", s, j))
                    for j, p in enumerate(self._ciclo(s)[1])]

        def sintetizar(e, fr):
            # Adentro, asientos y gente se comen los agudos: un "pssst" más opaco que en la calle.
            psst = _filtrar_fft(_psst(np.random.default_rng(e.semilla), fr, largo=1.8), fr, lambda f: _pb(f, 6500.0))
            return np.stack((psst, psst)) * _db(-4.0)

        desde = (k * self.L - self.P) / self.fr
        eventos = self.eventos_en("puertas", desde, (k + 1) * self.L / self.fr, self.CICLO, 0.0, 1.0, generar)
        return self.marco_eventos(k, [self.audio_evento(e, sintetizar) for e in eventos])

    def trozo(self, k):
        t = self.tiempos(k)
        rpm = self._rpm(t)
        carga = self._manejo(t, 2)
        andar = self._manejo(t, 3) / 30.0
        fase = self.fase(k, "motor", lambda tt: self._rpm(tt) / 120.0, self.CICLO)
        explosion = rpm / 20.0  # Hz: 6 cilindros, 3 explosiones por vuelta
        retumbo = 1.0 + 0.8 * np.exp(-0.5 * ((explosion - 58.0) / 6.0) ** 2)  # la carrocería retumba en algunas rpm
        # En ralentí el diésel igual se oye fuerte adentro (vibra todo): unos 8 dB menos que acelerando.
        nivel = (0.5 + 0.5 * carga) * (rpm / 1500.0) ** 0.5 * retumbo
        motor = _leer_tabla(self.tabla_motor, fase) * self.a_muestras(nivel)
        r = self.ruido(k, ("golpeteo", "andar"))
        golpeteo = r["golpeteo"] * np.exp(-_fraccion(fase * 6.0) / 0.12) * self.a_muestras(0.2 + 0.8 * carga)
        chapas = self.sonar(k, "chapas", self.chapa, 30.0, 0.7, 0.9,
                            lambda tt: np.clip(0.12 + self._manejo(tt, 3) / 35.0, 0.0, 1.0))
        return (motor * np.array([[1.0], [0.92]]) + _db(-12.0) * golpeteo
                + _db(-4.0) * r["andar"] * self.a_muestras(0.05 + andar ** 1.6)
                + _db(-14.0) * chapas + self._puertas(k))


@_receta("viento_mic")
class _VientoMic(_Fondo):
    """Viento que le pega al micrófono: golpes graves, a ráfagas, distintos en cada micrófono."""

    PENDIENTE_DB = 12.0
    AJUSTE_DB = -15.7

    def preparar(self):
        self.capa("golpes",
                  (0.0, lambda f: _pa(f, 12.0) * _inclinacion(f, -6.0, 50.0) * _pb(f, 140.0)),
                  (-10.0, lambda f: _pa(f, 100.0) * _inclinacion(f, -4.0, 300.0) * _pb(f, 1800.0)))
        self.tasa_rafagas = 0.35 + 0.25 * self.intensidad

    def trozo(self, k):
        t = self.tiempos(k)
        u = _rafagas(self, t, self.tasa_rafagas, 1.0)
        golpes = self.ruido(k, ("golpes",), modo="independiente")["golpes"]
        salida = np.empty((2, self.L))
        for c in range(2):  # cada micrófono tiene su propia turbulencia
            turbulencia = np.exp(0.65 * self.suave(("turbulencia", c), t, 0.06)
                                 + 0.4 * self.suave(("turbulencia_lenta", c), t, 0.22))
            salida[c] = golpes[c] * self.a_muestras(u ** 1.8 * turbulencia)
        return salida


# ---------------------------------------------------------------------------
# Fondo continuo (lo público)
# ---------------------------------------------------------------------------

def _limitar(x: np.ndarray) -> np.ndarray:
    """Seguro contra picos: deja igual todo lo que está por debajo de 0,8 y nunca pasa de 0,99."""
    a = np.abs(x)
    if a.max() <= 0.8:
        return x
    return np.where(a > 0.8, np.sign(x) * (0.8 + 0.19 * np.tanh((a - 0.8) / 0.19)), x)


class GeneradorFondo:
    """Un fondo continuo de cualquier largo, con acceso aleatorio exacto.

    tipo        clave de ``FONDOS``.
    intensidad  de 0 a 1 (más lluvia, más tránsito, más velocidad…); 0,5 es el nivel de referencia.
    semilla     cambia la realización (otra lluvia, otros autos), siempre igual para la misma semilla.
    frecuencia  muestras por segundo (48000).

    ``leer(inicio, n)`` da lo mismo que leer de corrido desde 0 y cortar. Guarda
    los últimos trozos: leer de corrido en bloques chicos cuesta lo mismo que
    leer todo junto (al menos 20 veces más rápido que el tiempo real). Al pedir
    varios trozos de una vez, los vehículos de la calle y la ciudad se
    sintetizan en paralelo, en unos pocos hilos internos (da exactamente lo
    mismo). Se puede usar desde varios hilos (un pedido a la vez). Memoria: unos
    10 MB por generador, leyendo de corrido.
    """

    def __init__(self, tipo: str, intensidad: float = 0.5, semilla: int = 0, frecuencia: int = FRECUENCIA):
        if tipo not in FONDOS:
            raise ValueError(f"Fondo desconocido: {tipo!r}. Los que hay: {', '.join(FONDOS)}.")
        try:
            intensidad = float(intensidad)
        except (TypeError, ValueError):
            intensidad = 0.5
        if not math.isfinite(intensidad):
            intensidad = 0.5
        frecuencia = int(frecuencia)
        if frecuencia < 8000:
            raise ValueError("La frecuencia tiene que ser de al menos 8000 Hz.")
        self.tipo = tipo
        self.intensidad = min(1.0, max(0.0, intensidad))
        self.semilla = int(semilla)
        self.frecuencia = frecuencia
        self._receta: _Fondo = _RECETAS[tipo](tipo, self.intensidad, self.semilla, frecuencia)
        nivel = NIVEL_FONDO_DBFS + self._receta.AJUSTE_DB + self._receta.PENDIENTE_DB * (self.intensidad - 0.5)
        self._ganancia = float(_db(nivel))
        self._trozos: OrderedDict = OrderedDict()
        self._candado = threading.Lock()

    def _trozo(self, k: int) -> np.ndarray:
        x = self._trozos.get(k)
        if x is None:
            x = np.ascontiguousarray(_limitar(self._receta.trozo(k) * self._ganancia).T, dtype=np.float32)
        return _recordar(self._trozos, k, x, 4)

    def leer(self, inicio: int, n: int) -> np.ndarray:
        """``n`` muestras desde la muestra ``inicio``: (n, 2) float32."""
        inicio, n = int(inicio), max(0, int(n))
        salida = np.empty((n, 2), np.float32)
        largo = self._receta.L
        with self._candado:
            if n:
                self._receta.anticipar(inicio // largo, (inicio + n - 1) // largo)
            pos = inicio
            while pos < inicio + n:
                k = pos // largo
                a = pos - k * largo
                b = min(largo, inicio + n - k * largo)
                salida[pos - inicio:pos - inicio + (b - a)] = self._trozo(k)[a:b]
                pos += b - a
        return salida


# ---------------------------------------------------------------------------
# Sonidos sueltos
# ---------------------------------------------------------------------------

def _divisor(fr: int, sub: int) -> int:
    """``sub`` si se puede sintetizar a fr/sub (exacto y sin perder lo que importa); si no, 1."""
    return sub if fr % sub == 0 and fr // sub >= 12000 else 1


def _en_la_calle(rng: np.random.Generator, fr: int, x: np.ndarray, sub: int = 1, rt60: float = 1.1,
                 directo_reverb_db: float = 5.0, ecos: int = 3, largo: float = 1.2, cola: float = 0.4) -> np.ndarray:
    """Le pone la calle a un sonido (ecos de las fachadas y la cola) y lo deja con ``cola`` s de más.

    ``x`` (mono o (2, n)) puede venir a fr/sub: sube a fr dentro de la misma
    convolución, rellenando el espectro con ceros. Es exacto porque el sonido
    empieza y termina en silencio (no hay saltos en los bordes).
    """
    h = _reverberacion(rng, fr, rt60, largo, directo_reverb_db, ecos, (0.025, 0.09), (0.2, 0.4))
    n = x.shape[-1] * sub
    tam = 2 * sub * _tamano_fft(-(-(n + h.shape[-1]) // (2 * sub)))
    X = np.fft.rfft(x, tam // sub)
    relleno = np.zeros(X.shape[:-1] + (tam // 2 + 1,), np.complex128)
    relleno[..., :X.shape[-1]] = X * sub
    y = np.fft.irfft(relleno * np.fft.rfft(h, tam), tam)[..., :n + int(cola * fr)]
    return _fundir(y, 0, int(min(cola, 0.3) * fr))


def _colectivo_pasa(rng, fr):
    # Por una avenida a 40-50 km/h, frenando para la parada (las rpm caen con la velocidad, en cambio):
    # después de pasar, el "pssst" del freno.
    p = _Pasada("colectivo", rng.uniform(11.0, 13.5), rng.uniform(2.6, 3.6), 1 if rng.random() < 0.5 else -1,
                rng.uniform(1500.0, 1800.0), rng.uniform(-0.06, -0.03), 4.8, 4.8, int(rng.integers(1 << 62)),
                freno=rng.uniform(1.3, 2.4))
    sub = _divisor(fr, 2)  # a 24 kHz: arriba de 12 kHz un vehículo casi no tiene nada
    return _en_la_calle(rng, fr, _pasada(p, fr // sub), sub)


def _auto_pasa(rng, fr):
    p = _Pasada("auto", rng.uniform(11.0, 16.0), rng.uniform(2.5, 4.0), 1 if rng.random() < 0.5 else -1,
                rng.uniform(2000.0, 2800.0), rng.uniform(-0.02, 0.06), 3.0, 3.0, int(rng.integers(1 << 62)))
    sub = _divisor(fr, 2)
    return _en_la_calle(rng, fr, _pasada(p, fr // sub), sub)


def _moto_pasa(rng, fr):
    # Una moto que pasa acelerando y sube un cambio justo después.
    cilindros = 1 if rng.random() < 0.65 else 2
    rpm = rng.uniform(6500.0, 8000.0) if cilindros == 1 else rng.uniform(5200.0, 6500.0)
    p = _Pasada("moto", rng.uniform(12.0, 17.0), rng.uniform(2.5, 4.0), 1 if rng.random() < 0.5 else -1, rpm,
                rng.uniform(0.08, 0.15), 2.8, 2.8, int(rng.integers(1 << 62)), cilindros,
                cambio=rng.uniform(0.5, 1.5))
    sub = _divisor(fr, 2)
    return _en_la_calle(rng, fr, _pasada(p, fr // sub), sub)


def _frenada_colectivo(rng, fr):
    psst = _psst(rng, fr, largo=rng.uniform(1.5, 1.9))
    return _en_la_calle(rng, fr, np.stack((psst, psst)), rt60=1.0, directo_reverb_db=6.0)


def _bocina(rng, fr):
    """Una bocina de auto: dos tonos (una tercera), ricos en armónicos, de un toque largo o dos cortos."""
    sub = _divisor(fr, 2)
    fr //= sub
    f1 = rng.uniform(395.0, 430.0)
    f2 = f1 * rng.choice((1.19, 1.26))
    if rng.random() < 0.5:
        toques = [(0.0, rng.uniform(0.45, 0.9))]
    else:
        primero = rng.uniform(0.16, 0.24)
        hueco = rng.uniform(0.08, 0.14)
        toques = [(0.0, primero), (primero + hueco, rng.uniform(0.2, 0.4))]
    fin = toques[-1][0] + toques[-1][1]
    n = int(round((fin + 0.05) * fr))
    t = np.arange(n) / fr
    puerta = np.zeros(n)
    arranque = np.zeros(n)  # el tono sube un poco al arrancar cada toque, mientras la membrana toma vuelo
    for inicio, largo in toques:
        x = t - inicio
        dentro = (x >= 0.0) & (x <= largo + 0.04)
        puerta[dentro] = np.maximum(puerta[dentro], np.clip(x[dentro] / 0.012, 0.0, 1.0)
                                    * np.clip((largo + 0.03 - x[dentro]) / 0.03, 0.0, 1.0))
        arranque[dentro] = np.minimum(1.0, x[dentro] / 0.025)
    clave = int(rng.integers(1 << 62))
    s = np.zeros(n)
    for j, (f0, nivel) in enumerate(((f1, 1.0), (f2, 0.8))):
        f = f0 * (0.97 + 0.03 * arranque) * (1.0 + 0.002 * _suave(clave + j, t, 0.03))
        fase = np.cumsum(f) / fr + rng.random()
        s += nivel * np.tanh(3.5 * np.sin(_DOS_PI * fase) + 0.25)
    s = _filtrar_fft(s * puerta, fr, lambda f: _campana(f, 2500.0, 0.8, 6.0) * _pa(f, 250.0) * _pb(f, 7000.0))
    return _en_la_calle(rng, fr * sub, s, sub, rt60=1.0, directo_reverb_db=3.0, cola=2.0 - fin - 0.05)


def _sirena_lejos(rng, fr):
    """Una sirena a varias cuadras: barridos de 600 a 1200 Hz, casi solo el tono, mucho eco de la ciudad."""
    sub = _divisor(fr, 2)
    fr_final, fr = fr, fr // sub
    n = int(8.0 * fr)
    t = np.arange(n) / fr
    periodo = rng.uniform(3.2, 4.4)
    ciclo = (t / periodo + rng.random()) % 1.0
    sube = 0.55
    forma = np.where(ciclo < sube, 1.0 - (1.0 - ciclo / sube) ** 2, ((1.0 - ciclo) / (1.0 - sube)) ** 1.6)
    f = 600.0 + 600.0 * forma
    fase = np.cumsum(f) / fr
    # Un parlante con onda casi cuadrada: armónicos impares, puestos uno por uno (sin aliasing).
    s = np.sin(_DOS_PI * fase) + 0.3 * np.sin(3.0 * _DOS_PI * fase) + 0.1 * np.sin(5.0 * _DOS_PI * fase)
    s = _filtrar_fft(s, fr, lambda f: _pb(f, 1600.0, 3) * _pa(f, 200.0))
    clave = int(rng.integers(1 << 62))
    s *= _db(3.0 * _suave(clave, t, 1.3))  # se tapa y se destapa detrás de los edificios
    _fundir(s, int(1.5 * fr), int(1.5 * fr))  # se acerca y se aleja
    y = _en_la_calle(rng, fr_final, s, sub, rt60=2.0, directo_reverb_db=-4.0, ecos=5, largo=2.5, cola=0.0)
    return _fundir(y, 0, int(0.8 * fr_final))


_SINTESIS = {
    "colectivo_pasa": _colectivo_pasa,
    "auto_pasa": _auto_pasa,
    "moto_pasa": _moto_pasa,
    "frenada_colectivo": _frenada_colectivo,
    "bocina": _bocina,
    "sirena_lejos": _sirena_lejos,
}


def generar_sonido(tipo: str, semilla: int = 0, frecuencia: int = FRECUENCIA) -> np.ndarray:
    """Un sonido suelto entero: (n, 2) float32 con el pico en ``PICO_SONIDO_DBFS``.

    La misma semilla da siempre el mismo sonido; otra semilla, otra variante
    (otra velocidad, otro lado, otro toque de bocina). Queda en caché (LRU, los
    últimos 8): el array devuelto es de solo lectura, para que nadie lo cambie
    sin querer (para modificarlo, hacé una copia). ``generar_sonido.cache_clear()``
    vacía la caché.
    """
    if tipo not in SONIDOS:
        raise ValueError(f"Sonido desconocido: {tipo!r}. Los que hay: {', '.join(SONIDOS)}.")
    frecuencia = int(frecuencia)
    if frecuencia < 8000:
        raise ValueError("La frecuencia tiene que ser de al menos 8000 Hz.")
    return _sonido(tipo, int(semilla), frecuencia)  # argumentos normalizados: una sola entrada por sonido


@lru_cache(maxsize=8)
def _sonido(tipo: str, semilla: int, frecuencia: int) -> np.ndarray:
    x = _SINTESIS[tipo](_azar("sonido", tipo, semilla), frecuencia)
    x = x * (_db(PICO_SONIDO_DBFS) / (np.abs(x).max() + 1e-12))
    salida = np.ascontiguousarray(x.T, dtype=np.float32)
    salida.flags.writeable = False
    return salida


generar_sonido.cache_clear = _sonido.cache_clear


__all__ = [
    "FRECUENCIA", "NIVEL_FONDO_DBFS", "PICO_SONIDO_DBFS", "InfoAmbiente", "FONDOS", "SONIDOS", "GeneradorFondo",
    "generar_sonido",
]
