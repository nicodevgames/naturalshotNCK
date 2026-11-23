"""Voz natural: que una voz limpia (o hecha con IA) suene grabada de verdad con un celular.

No depende de la interfaz gráfica. PyAV se importa recién al comprimir (etapa 7),
así ``AjustesVoz`` se puede importar (por ejemplo, desde la sesión) sin cargar
FFmpeg. Todo entra y sale a 48 kHz, estéreo y float32, en bloques ``(n, 2)``;
adentro se calcula en float64.

La cadena, en el orden en que pasa en la vida real
--------------------------------------------------
1. **Bajarle lo de IA** (solo a la voz, si ``anti_ia`` > 0):
   * recorte suave de los extremos que un celular no capta (debajo de 60 Hz y arriba de 15 kHz);
   * de-esser: la banda de 5 a 9 kHz se comprime cuando domina (las "s" demasiado perfectas);
   * el brillo (un estante de agudos) se mueve ±1 dB, despacio;
   * el volumen se mueve ±1,5 dB, despacio (unos 0,3 Hz), como si se moviera la cabeza.
   Las dos variaciones lentas salen de valores al azar por segundo (semilla y número de
   segundo) interpolados: dependen del tiempo absoluto, así que un salto da lo mismo. No
   cambia el tono ni el tiempo (eso suena raro).
2. **El lugar** (si ``lugar`` no es "ninguno"): una respuesta al impulso sintética, con
   reflexiones tempranas y una cola de ruido que decae (más rápido en los agudos), por
   convolución FFT por particiones. Nivel húmedo: ``eco × cuanto × distancia del destino``
   (el video se graba a un brazo y suma más lugar; WhatsApp, pegado a la boca, menos).
3. **Voz y ambiente juntos:** acá se suma ``ambiente`` (fondo y sonidos, ya con su volumen),
   así pasa por el mismo micrófono y la misma compresión que la voz y no suena "pegado".
4. **Micrófono del destino:** un FIR de fase mínima (como un micrófono de verdad: sin el
   retardo de un filtro de fase lineal) y una saturación suave con tanh, sobremuestreada ×2.
5. **AGC del celular:** envolvente RMS cada 1 ms del total, objetivo -20 dBFS, ataque de
   30 ms y liberación de 400 ms, de -15 a +6 dB. Cuando pasa algo fuerte, baja todo y la
   voz "se tapa" (cuánto baja lo regula ``tapa``). En auriculares, además, una compuerta
   que baja el fondo en las pausas y lo devuelve al hablar: el "bombeo" de la reducción de
   ruido del Bluetooth.
6. **Ruido propio del micrófono:** rosa, a -62 dBFS × ``ruido_propio`` × ``cuanto``, por
   trozos con semilla por tiempo absoluto (igual que las variaciones lentas).
7. **Compresión del destino** (si ``compresion`` y ``codec=True``): se codifica y se
   decodifica de verdad con PyAV. WhatsApp: Opus mono a 16 kHz y 24 kbit/s. Video: AAC
   estéreo de 128 kbit/s. Auriculares: Opus mono a 16 kHz y 32 kbit/s (como mSBC).

Los pasos 4 a 7 son "cómo se grabó": solo corren con un destino y ``cuanto`` > 0. WhatsApp y
auriculares graban con un solo micrófono: desde el paso 4 van en mono (sale igual en los dos
canales); el video, en estéreo. Al final, con destino, la salida se recorta a ±1 (un celular
graba en 16 bits: no hay nada más allá). **Sin destino no se recorta:** voz + ambiente + eco
puede pasar de ±1 (se midió 1,93); el volumen y la normalización van después, en el mezclador.

Entradas sucias: un NaN o un infinito en la voz o el ambiente se cambia por 0 o ±1 antes de
procesar (si no, envenenaba el AGC para siempre y el códec dejaba de sonar).

Cuánto
------
``cuanto`` escala todo lo de la grabación: el lugar (nivel húmedo), el micrófono (la
respuesta en dB se multiplica por ``cuanto``, así que 0 es plano y 1 es la banda completa
del destino), la saturación, el AGC, la compuerta y el ruido propio. Con 0 no se graba nada
(ni siquiera se comprime). ``anti_ia`` es aparte: tiene su propio control en la interfaz y
no depende de ``cuanto``.

Bloques, saltos y latencia
--------------------------
* **Bloques:** procesar de corrido en bloques de cualquier tamaño da lo mismo que en uno solo
  (salvo redondeos de 1e-6). Los filtros guardan su historia (solapar y guardar), el eco va en
  particiones fijas desde el arranque y los controles (de-esser, AGC, compuerta) se deciden en
  una grilla absoluta de 1 ms: el cuadro m son las muestras ``[m·48, (m+1)·48)`` del resultado.
  Con el códec también da lo mismo: el codificador ve los mismos cuadros.
* **Saltos:** ``reiniciar(inicio)`` deja todo en cero en ``inicio``. Si un ``procesar`` llega con un
  ``inicio`` que no sigue al bloque anterior (o si el anterior se cortó con una excepción), la
  cadena se reinicia sola ahí. Lo que depende del tiempo absoluto (variaciones lentas, ruido
  propio) da lo mismo después de un salto. Con ``PRELECTURA`` (0,5 s) de señal anterior:
  - el eco y los filtros quedan exactos (la respuesta del lugar dura como mucho 0,4 s y los FIR, 21 ms);
  - el AGC queda casi igual: su liberación es de 400 ms, así que puede diferir en 0,1 dB durante un
    segundo más (sobre todo con anti IA, cuyo volumen lento persigue con atraso). No se oye;
  - el códec no: arranca con otro estado. Con compresión, después de un salto suena igual pero la
    forma de onda no es la de corrido (medido: -15 dB de diferencia en Opus con voz, -23 dB en AAC).
* **Latencia:** con el códec (solo a 48 kHz: las latencias están medidas ahí), la cadena atrasa
  ``latencia`` muestras (Opus: 1368 = 28,5 ms; AAC: 3120 = 65 ms) y la salida ya viene
  **compensada**: la muestra i de lo que sale es la muestra i de lo que entró. Para eso se
  guarda adentro lo que el códec todavía no devolvió, y el primer tramo después de arrancar sale
  más corto. La regla exacta: después de entregarle F muestras desde el arranque (crear o
  ``reiniciar``), ``procesar`` devolvió en total ``max(0, F - latencia)``, empezando en el
  ``inicio`` del arranque. ``vaciar()`` entrega las que faltan para llegar a F (``latencia`` si F
  alcanza) y deja la cadena como recién reiniciada al final (con o sin códec: se puede seguir
  procesando desde ahí). ``posicion_salida`` dice en qué muestra del resultado cae la próxima
  que sale. Sin códec, ``latencia`` es 0 y ``procesar`` siempre devuelve n muestras.

Cómo la usa el mezclador (Tarea C)
----------------------------------
* **De corrido desde 0** (exportar): ``procesar`` cada bloque y escribir lo que devuelve; al
  terminar, escribir ``vaciar()``. Sale exactamente el largo de la entrada, alineado.
* **Desde un punto p** (vista previa, después de un salto): ``reiniciar(max(0, p - pre))`` con
  ``pre = round(PRELECTURA · 48000)``, procesar la señal de ``[p - pre, p)`` y seguir de corrido;
  descartar todo lo que salga mientras ``posicion_salida`` sea menor que p (lo de la
  pre-lectura más las primeras ``latencia`` del arranque). Al llegar al final, ``vaciar()``.

Velocidad, con todo prendido y en bloques de 50 ms, en esta PC: unas 18 veces el tiempo real con
WhatsApp o auriculares y unas 12 con video (el codificador AAC es lo más lento). Armar una cadena
nueva tarda de 15 a 40 ms (los filtros y el eco quedan en caché: la segunda vez, 2 a 4 ms). Los
bloques grandes se procesan por dentro de a ``_TROZO_MAX`` muestras: la memoria no crece con el bloque.
"""

from __future__ import annotations

import math
from collections import OrderedDict, deque
from dataclasses import dataclass, fields, replace
from fractions import Fraction
from functools import lru_cache
from typing import Callable

import numpy as np

DESTINOS = ("ninguno", "whatsapp", "video", "auriculares")
LUGARES = ("ninguno", "habitacion", "oficina", "auto", "colectivo", "calle", "exterior")

FRECUENCIA = 48000
PRELECTURA = 0.5   # s de señal anterior que necesita la cadena después de un salto

# Anti IA
VOLUMEN_LENTO_DB = 1.5   # ± del volumen que se mueve despacio (× anti_ia)
BRILLO_LENTO_DB = 1.0    # ± del estante de agudos (× anti_ia)
PERIODO_LENTO = 1.0      # s entre valores al azar de las variaciones lentas (da unos 0,3 Hz)
DE_ESSER_MAX_DB = 8.0
# Lugar: cuánto lugar suma cada destino (a qué distancia de la boca está el micrófono)
DISTANCIA = {"ninguno": 1.0, "whatsapp": 0.7, "video": 1.3, "auriculares": 0.8}
ECO_MAX = 0.4            # s: la respuesta al impulso nunca dura más (entra en la pre-lectura)
# Micrófono: cuánta saturación suave (× cuanto) y con qué empuje; cuáles graban con un solo micrófono
SATURACION = {"whatsapp": 0.7, "video": 0.3, "auriculares": 0.5}
MONO = ("whatsapp", "auriculares")
EMPUJE = 2.0
# AGC
OBJETIVO_AGC_DB = -20.0
AGC_BAJA_DB = 15.0
AGC_SUBE_DB = 6.0
AGC_ATAQUE = 0.030       # s
AGC_LIBERACION = 0.400   # s
SILENCIO_DB = -60.0      # debajo de esto el AGC no sube (no levanta el silencio digital)
COMPUERTA_DB = 12.0      # cuánto baja el fondo la reducción de ruido de los auriculares (× cuanto)
# Ruido propio
RUIDO_PROPIO_DB = -62.0

_LARGO_FIR = 1024        # coeficientes de los FIR del micrófono y del anti IA (21 ms: error < 0,3 dB a 20 Hz)
_PARTICION = 1024        # muestras por partición del eco


# ---------------------------------------------------------------------------
# Ajustes
# ---------------------------------------------------------------------------

def _acomodar(valor, defecto: float) -> float:
    """Entre 0 y 1. NaN, infinito o algo que no es un número: el valor por defecto."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return defecto
    return min(1.0, max(0.0, v)) if math.isfinite(v) else defecto


@dataclass(frozen=True)
class AjustesVoz:
    """Cómo suena la voz. Los valores por defecto no cambian nada.

    destino       cómo se grabó: "ninguno", "whatsapp" (nota de voz), "video" (video de
                  celular) o "auriculares" (auriculares o manos libres).
    cuanto        de 0 a 1 (Sutil 0,3 · Normal 0,6 · Fuerte 0,9): escala todo lo de la grabación.
    anti_ia       de 0 a 1: "bajarle lo de IA" (no depende de ``cuanto``).
    lugar         "ninguno", "habitacion", "oficina", "auto", "colectivo", "calle" o "exterior".
    eco           de 0 a 1: cuánto lugar.
    ruido_propio  de 0 a 1: el piso de ruido del micrófono.
    compresion    comprimir con el códec del destino (Opus o AAC).
    tapa          de 0 a 1: cuánto baja el AGC cuando hay un sonido fuerte ("que tape la voz").
    semilla       para las variaciones al azar (el mismo proyecto suena siempre igual).

    Un destino o un lugar desconocido lanza ``ValueError``. Los números se acomodan entre 0 y 1
    (NaN vuelve al valor por defecto), como ``AjustesAudio``, y se redondean a 0,01. Inmutable y se
    puede guardar con pickle.
    """

    destino: str = "ninguno"
    cuanto: float = 0.6
    anti_ia: float = 0.0
    lugar: str = "ninguno"
    eco: float = 0.5
    ruido_propio: float = 0.5
    compresion: bool = True
    tapa: float = 0.5
    semilla: int = 0

    def __post_init__(self):
        if self.destino not in DESTINOS:
            raise ValueError(f"Destino desconocido: {self.destino!r}. Usá uno de {', '.join(DESTINOS)}.")
        if self.lugar not in LUGARES:
            raise ValueError(f"Lugar desconocido: {self.lugar!r}. Usá uno de {', '.join(LUGARES)}.")
        for campo in fields(self):
            if campo.type in ("float", float):
                # A 0,01: un deslizador no llena las cachés de diseño de filtros con valores casi iguales.
                object.__setattr__(self, campo.name, round(_acomodar(getattr(self, campo.name), campo.default), 2))
        object.__setattr__(self, "compresion", bool(self.compresion))
        try:
            semilla = int(self.semilla)
        except (TypeError, ValueError, OverflowError):
            semilla = 0
        object.__setattr__(self, "semilla", semilla)

    def sin_cambios(self) -> bool:
        """True si la voz sale igual (más el ambiente): sin destino, sin lugar y sin anti IA."""
        return self.destino == "ninguno" and self.lugar == "ninguno" and self.anti_ia == 0.0

    def con(self, **cambios) -> "AjustesVoz":
        """Otro con esos campos cambiados (acomodados igual que al crearlo)."""
        return replace(self, **cambios)


# ---------------------------------------------------------------------------
# Herramientas de DSP (todo vectorizado: nada de bucles muestra por muestra)
# ---------------------------------------------------------------------------

def _paso(frecuencia: int) -> int:
    """Muestras de un cuadro de control (1 ms)."""
    return max(1, round(frecuencia / 1000))


def _tamano_fft(m: int) -> int:
    """El menor 2^a · {1, 3, 5, 9, 15} que alcanza para ``m`` (tamaños rápidos para la FFT)."""
    mejor = 1 << max(0, (m - 1).bit_length())
    for impar in (3, 5, 9, 15):
        c = impar
        while c < m:
            c <<= 1
        mejor = min(mejor, c)
    return mejor


def _semilla(*partes: int) -> np.random.Generator:
    return np.random.default_rng([int(p) % 2 ** 32 for p in partes])


class _Cache:
    """Caché chica que, al llenarse, descarta lo que se usó hace más tiempo (LRU)."""

    def __init__(self, maximo: int):
        self._datos: OrderedDict = OrderedDict()
        self._maximo = maximo

    def obtener(self, clave, crear: Callable[[], object]):
        if clave in self._datos:
            self._datos.move_to_end(clave)
            return self._datos[clave]
        valor = self._datos[clave] = crear()
        if len(self._datos) > self._maximo:
            self._datos.popitem(last=False)
        return valor


def _congelar(a: np.ndarray) -> np.ndarray:
    """Para lo que queda en caché: que nadie lo cambie sin querer."""
    a.flags.writeable = False
    return a


class _FIR:
    """Uno o varios filtros FIR sobre la misma señal, de a bloques de cualquier tamaño.

    Solapar y guardar: se guardan las últimas ``largo - 1`` muestras de la entrada,
    así procesar de a bloques da lo mismo que todo junto. La convolución va por FFT
    (una sola transformada de la entrada para todos los filtros).
    """

    def __init__(self, filtros: np.ndarray, canales: int):
        self._h = np.atleast_2d(np.asarray(filtros, np.float64))
        self._largo = self._h.shape[1]
        self._canales = canales
        self._espectros = _Cache(8)   # rfft de los filtros, por tamaño de FFT
        self.reiniciar()

    def reiniciar(self) -> None:
        self._historia = np.zeros((self._largo - 1, self._canales))

    def _espectro(self, nfft: int) -> np.ndarray:
        return self._espectros.obtener(nfft, lambda: np.fft.rfft(self._h, nfft, axis=1))

    def procesar(self, x: np.ndarray) -> np.ndarray:
        """``x`` (n, canales) -> (filtros, n, canales)."""
        n, largo = x.shape[0], self._largo
        if not n:
            return np.zeros((self._h.shape[0], 0, self._canales))
        z = np.concatenate((self._historia, x))
        nfft = _tamano_fft(z.shape[0])
        espectro = np.fft.rfft(z, nfft, axis=0)
        y = np.fft.irfft(self._espectro(nfft)[:, :, None] * espectro[None], nfft, axis=1)[:, largo - 1:largo - 1 + n]
        if largo > 1:
            self._historia = z[z.shape[0] - (largo - 1):].copy()
        return y


class _Convolucion:
    """Convolución larga (el eco), mono, de a bloques de cualquier tamaño y sin latencia.

    La respuesta se parte en una cabeza (las primeras ``P`` muestras), que va con
    ``_FIR`` sobre cada bloque, y una cola en particiones de ``P`` que va en el
    dominio de la frecuencia con una línea de demora de espectros (solapar y guardar
    de 2P). La cola que suena en la partición j solo usa entrada de particiones
    anteriores: se calcula una vez por partición, cuando arranca, y no depende de
    cómo vengan cortados los bloques.
    """

    def __init__(self, h: np.ndarray, particion: int = _PARTICION):
        self.P = P = particion
        self._cabeza = _FIR(h[:P], 1)
        cola = h[P:]
        self._K = K = -(-cola.size // P)
        if K:
            partes = np.zeros((K, 2 * P))
            for k in range(K):
                trozo = cola[k * P:(k + 1) * P]
                partes[k, :trozo.size] = trozo
            # La más lejana primero: así se multiplica directo con la ventana de la línea de demora.
            self._espectros = np.fft.rfft(partes, axis=1)[::-1].copy()
        self.reiniciar()

    def reiniciar(self) -> None:
        self._cabeza.reiniciar()
        if self._K:
            # Línea de demora doble: cada espectro va en s y en s + K, así la ventana es una vista contigua.
            self._demora = np.zeros((2 * self._K, self.P + 1), np.complex128)
            self._ultimo = -1
            self._entrada = np.zeros(2 * self.P)   # partición anterior + la que se está llenando
            self._llenas = 0
            self._cola = np.zeros(self.P)          # lo que suma la cola en la partición actual

    def procesar(self, x: np.ndarray) -> np.ndarray:
        y = self._cabeza.procesar(x[:, None])[0, :, 0]
        if not self._K:
            return y
        P, i, n = self.P, 0, x.shape[0]
        while i < n:   # una vuelta por partición (cada 21 ms), no por muestra
            a = self._llenas
            m = min(P - a, n - i)
            y[i:i + m] += self._cola[a:a + m]
            self._entrada[P + a:P + a + m] = x[i:i + m]
            self._llenas += m
            i += m
            if self._llenas == P:
                self._avanzar()
        return y

    def _avanzar(self) -> None:
        K, P = self._K, self.P
        s = self._ultimo = (self._ultimo + 1) % K
        espectro = np.fft.rfft(self._entrada)
        self._demora[s] = espectro
        self._demora[s + K] = espectro
        ventana = self._demora[s + 1:s + 1 + K]   # de la partición más vieja a la recién terminada
        self._cola = np.fft.irfft(np.einsum("ij,ij->j", ventana, self._espectros), 2 * P)[P:]
        self._entrada[:P] = self._entrada[P:]
        self._llenas = 0


class _Control:
    """Una ganancia que se decide cada 1 ms y se aplica muestra a muestra, interpolada.

    La grilla es absoluta: el cuadro m son las muestras ``[m·paso, (m+1)·paso)`` del
    resultado, así da lo mismo cómo vengan cortados los bloques y, después de un
    salto, los cuadros caen donde caían de corrido. ``decidir(potencias)`` recibe la
    potencia media de cada cuadro que se completa (k × señales) y devuelve un valor
    por cuadro: es el único bucle de Python, a 1 kHz. Lo que se decide con el cuadro
    m se alcanza al final del cuadro m + 1 (la ganancia llega 1 o 2 ms tarde, sin
    mirar adelante), en una rampa lineal: no hay escalones.
    """

    def __init__(self, paso: int, decidir: Callable[[np.ndarray], np.ndarray]):
        self.paso = paso
        self._decidir = decidir
        self.reiniciar(0, 1.0)

    def reiniciar(self, inicio: int, inicial: float) -> None:
        self._suma = None   # potencia acumulada del cuadro a medio llenar
        self._cuenta = 0
        self._base = inicio // self.paso - 2   # cuadro del primer valor guardado
        self._valores = [inicial, inicial]

    def ganancia(self, potencias: np.ndarray, inicio: int) -> np.ndarray:
        """Ganancia de cada muestra del bloque que empieza en ``inicio`` (potencias: n × señales)."""
        P = self.paso
        n = potencias.shape[0]
        fin = inicio + n
        cortes = np.arange((inicio // P + 1) * P, fin + 1, P) - inicio   # dónde termina cada cuadro completo
        if cortes.size:
            acumulada = np.concatenate((np.zeros((1, potencias.shape[1])), np.cumsum(potencias, axis=0)))
            desde = np.concatenate(([0], cortes[:-1]))
            sumas = acumulada[cortes] - acumulada[desde]
            cuentas = (cortes - desde).astype(np.float64)
            if self._cuenta:
                sumas[0] += self._suma
                cuentas[0] += self._cuenta
            self._valores.extend(self._decidir(sumas / cuentas[:, None]))
            resto = potencias[cortes[-1]:]
            self._suma, self._cuenta = resto.sum(axis=0), resto.shape[0]
        elif n:
            parcial = potencias.sum(axis=0)
            self._suma = parcial if not self._cuenta else self._suma + parcial
            self._cuenta += n
        t = np.arange(inicio, fin)
        m = t // P
        j = m - 2 - self._base
        valores = np.asarray(self._valores)
        a = valores[j]
        g = a + (valores[j + 1] - a) * ((t - m * P + 1) / P)
        sobran = fin // P - 2 - self._base
        if sobran > 0:
            del self._valores[:sobran]
            self._base += sobran
        return g


def _lento(t: np.ndarray, nudo: Callable[[int], float]) -> np.ndarray:
    """Ruido lento: valores al azar cada ``PERIODO_LENTO`` s (``nudo(k)``), con interpolación coseno.

    Coseno: sin sobrepasarse de los valores y sin quiebres. Depende solo de ``t``
    (segundos del resultado): un salto da lo mismo.
    """
    if not t.size:
        return np.zeros(0)
    u = t / PERIODO_LENTO
    k = np.floor(u).astype(np.int64)
    k0 = int(k[0])
    valores = np.array([nudo(i) for i in range(k0, int(k[-1]) + 2)])
    a, b = valores[k - k0], valores[k - k0 + 1]
    return a + (b - a) * (0.5 - 0.5 * np.cos(np.pi * (u - k)))


# ---------------------------------------------------------------------------
# Diseño de filtros: respuestas en dB -> FIR de fase mínima
# ---------------------------------------------------------------------------

def _frecuencias(frecuencia: int) -> np.ndarray:
    """Grilla de diseño: 32768 puntos (1,5 Hz a 48 kHz), de sobra para un paso alto de 60 Hz."""
    return np.fft.rfftfreq(32768, 1.0 / frecuencia)


def _paso_alto(f, fc, orden):
    with np.errstate(divide="ignore", over="ignore"):
        return -10 * np.log10(1 + (fc / np.maximum(f, 1e-3)) ** (2 * orden))


def _paso_bajo(f, fc, orden):
    with np.errstate(over="ignore"):
        return -10 * np.log10(1 + (f / fc) ** (2 * orden))


def _campana(f, fc, db, octavas):
    return db * np.exp(-0.5 * (np.log2(np.maximum(f, 1e-3) / fc) / octavas) ** 2)


def _estante_bajo(f, fc, db):
    return db / (1 + (f / fc) ** 2)


def _fase_minima(db: np.ndarray, largo: int) -> np.ndarray:
    """FIR de fase mínima con esa magnitud (en dB sobre ``_frecuencias``), por el cepstro real.

    Fase mínima: toda la energía lo antes posible, sin el retardo de un filtro de
    fase lineal (como un micrófono o un filtro analógico), así la salida no se corre.
    Se recorta a ``largo`` con un fundido corto al final.
    """
    nfft = 2 * (db.size - 1)
    log_mag = np.maximum(db, -120.0) * (np.log(10.0) / 20.0)
    cepstro = np.fft.irfft(log_mag, nfft)
    pliegue = np.zeros(nfft)
    pliegue[0] = pliegue[nfft // 2] = 1.0
    pliegue[1:nfft // 2] = 2.0
    h = np.fft.irfft(np.exp(np.fft.rfft(cepstro * pliegue)), nfft)[:largo].copy()
    fundido = max(1, largo // 16)
    h[-fundido:] *= 0.5 + 0.5 * np.cos(np.pi * (np.arange(fundido) + 1) / fundido)
    return h


def _respuesta_microfono(destino: str, f: np.ndarray) -> np.ndarray:
    """La respuesta completa (``cuanto`` = 1) del micrófono de cada destino, en dB."""
    if destino == "whatsapp":   # pegado a la boca: proximidad +3 dB a 150 Hz, de 80 Hz a 7,5 kHz
        return _paso_alto(f, 80, 2) + _campana(f, 150, 3.0, 1.0) + _paso_bajo(f, 7500, 10)
    if destino == "video":      # a un brazo: menos graves (-2 dB), de 100 Hz a 12 kHz
        return _paso_alto(f, 100, 2) + _estante_bajo(f, 250, -2.0) + _paso_bajo(f, 12000, 8)
    # auriculares o manos libres: banda angosta de 200 Hz a 7 kHz, con un pico de presencia a 2,5 kHz
    return _paso_alto(f, 200, 3) + _campana(f, 2500, 4.0, 0.7) + _paso_bajo(f, 7000, 10)


@lru_cache(maxsize=32)
def _filtro_microfono(destino: str, cuanto: float, frecuencia: int) -> np.ndarray:
    """FIR del micrófono: la respuesta del destino × ``cuanto`` en dB (0 = plano)."""
    return _congelar(_fase_minima(_respuesta_microfono(destino, _frecuencias(frecuencia)) * cuanto, _LARGO_FIR))


@lru_cache(maxsize=16)
def _filtros_anti_ia(cantidad: float, frecuencia: int) -> np.ndarray:
    """Cuatro FIR sobre la voz: recortada, sus agudos, su banda de "s" y la misma banda, angosta.

    * El recorte (paso alto suave a 60 Hz y paso bajo suave a 15 kHz) va × ``cantidad`` en dB.
    * Los demás son el recorte por otra banda: como la fase mínima de un producto es el
      producto de las fases mínimas, son exactamente esas bandas de la voz recortada.
    * El brillo y el de-esser se aplican como ``voz + (g - 1) · banda``. Eso solo funciona si la
      banda tiene fase casi 0 donde actúa: por eso van de orden 1 (un paso alto de 3 kHz para el
      brillo; un paso alto de 5 kHz por un paso bajo de 9 kHz, normalizado a 1 en el centro, para
      el de-esser: fase de ±13° entre 5,5 y 8,5 kHz). Con órdenes altos la fase gira y casi no baja.
    * La detección de las "s" va con la banda angosta (orden 4): no se confunde con los formantes.
    """
    f = _frecuencias(frecuencia)
    recorte = (_paso_alto(f, 60, 2) + _paso_bajo(f, 15000, 2)) * cantidad
    agudos = recorte + _paso_alto(f, 3000, 1)
    centro = math.sqrt(5000.0 * 9000.0)
    eses = recorte + _paso_alto(f, 5000, 1) + _paso_bajo(f, 9000, 1) - float(
        _paso_alto(np.array([centro]), 5000, 1)[0] + _paso_bajo(np.array([centro]), 9000, 1)[0])
    deteccion = recorte + _paso_alto(f, 5000, 4) + _paso_bajo(f, 9000, 4)
    return _congelar(np.stack([_fase_minima(r, _LARGO_FIR) for r in (recorte, agudos, eses, deteccion)]))


@lru_cache(maxsize=4)
def _filtro_sobremuestreo(frecuencia: int) -> np.ndarray:
    """Paso bajo a 0,42 × ``frecuencia`` (20 kHz), al doble de frecuencia: interpola al subir y filtra al bajar."""
    f = np.fft.rfftfreq(32768, 1.0 / (2 * frecuencia))
    return _congelar(_fase_minima(_paso_bajo(f, 0.42 * frecuencia, 8), 96))


# ---------------------------------------------------------------------------
# Lugares: respuestas al impulso sintéticas
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Sala:
    rt60: float          # s: lo que tarda la cola en bajar 60 dB (en los medios)
    nivel_db: float      # energía de la respuesta respecto del sonido directo (con eco y cuánto al máximo)
    tempranas: tuple     # ((ms, ganancia relativa), ...): las primeras reflexiones (paredes, techo, vidrios)
    parte_temprana: float  # qué parte de la energía va en las reflexiones tempranas (el resto, en la cola)
    cola_desde: float    # ms: dónde arranca la cola difusa
    semilla: int         # fija por sala (no su lugar en LUGARES): agregar un lugar no cambia cómo suenan los demás


# Las reflexiones tempranas tienen retardos que no son múltiplos entre sí y poco nivel: si no, el filtro peine
# que arman suena a "lata". Las de la calle son ecos sueltos de las fachadas, con muy poco nivel.
_SALAS = {
    "habitacion": _Sala(0.35, -7.0, ((2.9, .55), (4.7, .45), (6.8, .38), (9.3, .3), (12.6, .22), (16.1, .17)), 0.4, 6.0, 1),
    "oficina": _Sala(0.50, -8.0, ((4.3, .5), (7.1, .4), (10.6, .32), (14.9, .25), (20.3, .2), (27.0, .14)), 0.35, 9.0, 2),
    "auto": _Sala(0.12, -9.0, ((1.3, .6), (2.2, .5), (3.4, .4), (4.7, .3), (6.5, .22)), 0.45, 2.5, 3),
    "colectivo": _Sala(0.25, -9.0, ((2.1, .5), (3.9, .42), (6.6, .35), (9.8, .26), (14.1, .2)), 0.4, 4.0, 4),
    "calle": _Sala(0.80, -17.0, ((11.0, .35), (23.0, .5), (41.0, .4), (67.0, .3), (96.0, .2)), 0.6, 15.0, 5),
    "exterior": _Sala(0.10, -28.0, ((5.5, 1.0),), 0.9, 8.0, 6),
}
# Bandas de la cola (cortes en Hz) y cómo decae y cuánto devuelve cada una: los agudos se apagan antes.
_BANDAS_COLA = (300.0, 1500.0, 5000.0)
_RT60_BANDA = (1.1, 1.0, 0.8, 0.55)
_NIVEL_BANDA = (1.0, 1.0, 0.8, 0.5)


@lru_cache(maxsize=16)
def _respuesta_lugar(lugar: str, semilla: int, frecuencia: int) -> np.ndarray:
    """Respuesta al impulso del lugar, sin el sonido directo (solo lo que suma el lugar)."""
    sala = _SALAS[lugar]
    fr = frecuencia
    largo = min(round(ECO_MAX * fr), round((sala.cola_desde / 1000 + 1.2 * sala.rt60) * fr))
    t = np.arange(largo) / fr
    temprana = np.zeros(largo)
    for ms, g in sala.tempranas:
        i = round(ms / 1000 * fr)
        temprana[i:i + 3] += g * np.array([0.25, 0.5, 0.25])[:max(0, min(3, largo - i))]   # algo opaca: sin agudos de lata
    ruido = np.fft.rfft(_semilla(31, semilla, sala.semilla).standard_normal(largo))
    f = np.maximum(np.fft.rfftfreq(largo, 1.0 / fr), 1e-3)
    escalones = [1 / (1 + (c / f) ** 4) for c in _BANDAS_COLA]   # pasos altos suaves: las máscaras suman 1
    mascaras = [1 - escalones[0]] + [escalones[i] - escalones[i + 1] for i in range(len(escalones) - 1)] + [escalones[-1]]
    t0 = sala.cola_desde / 1000
    tc = np.maximum(t - t0, 0.0)
    subida = np.where(t >= t0, 1 - np.exp(-tc / 0.003), 0.0)   # la cola entra suave, en unos ms
    cola = np.zeros(largo)
    for mascara, rt, nivel in zip(mascaras, _RT60_BANDA, _NIVEL_BANDA):
        banda = np.fft.irfft(ruido * mascara, largo)
        cola += nivel * banda * subida * np.exp(-6.91 * tc / (sala.rt60 * rt))
    energia = 10 ** (sala.nivel_db / 10)
    h = (temprana * math.sqrt(energia * sala.parte_temprana / max(np.sum(temprana ** 2), 1e-12))
         + cola * math.sqrt(energia * (1 - sala.parte_temprana) / max(np.sum(cola ** 2), 1e-12)))
    fundido = min(largo, round(0.03 * fr))
    h[largo - fundido:] *= 0.5 + 0.5 * np.cos(np.pi * (np.arange(fundido) + 1) / fundido)
    return _congelar(h)


# ---------------------------------------------------------------------------
# Las etapas
# ---------------------------------------------------------------------------

class _AntiIA:
    """Etapa 1: recorte de extremos, de-esser, brillo y volumen que se mueven despacio."""

    def __init__(self, cantidad: float, semilla: int, frecuencia: int):
        self.cantidad = cantidad
        self.semilla = semilla
        self.frecuencia = frecuencia
        self._fir = _FIR(_filtros_anti_ia(cantidad, frecuencia), 2)
        paso = _paso(frecuencia)
        self._k_nivel = 1 - math.exp(-paso / (0.005 * frecuencia))
        self._ataque = 1 - math.exp(-paso / (0.001 * frecuencia))
        self._liberacion = 1 - math.exp(-paso / (0.050 * frecuencia))
        self._control = _Control(paso, self._decidir)
        self._nudos = _Cache(64)

    def reiniciar(self, inicio: int) -> None:
        self._fir.reiniciar()
        self._control.reiniciar(inicio, 1.0)
        self._banda = self._todo = self._reduccion = None

    def _decidir(self, potencias: np.ndarray) -> np.ndarray:
        """De-esser: cuánto se baja la banda de "s" en cada cuadro (factor lineal).

        La banda y el total se miden con el mismo suavizado corto (5 ms), así se compara el
        balance de ese momento (con uno lento, la vocal anterior tapaba el arranque de la "s").
        La banda "manda" si está a menos de 10 dB del total: en una vocal queda 15 a 35 dB abajo
        y en una "s", a 1-4 dB. Lo que pasa de ese umbral se baja a razón de 0,6 dB por dB (hasta
        8 dB, × ``anti_ia``), con ataque de 1 ms y liberación de 50 ms.
        """
        salida = np.empty(potencias.shape[0])
        banda, todo, reduccion = self._banda, self._todo, self._reduccion
        k, ataque, liberacion, cantidad = self._k_nivel, self._ataque, self._liberacion, self.cantidad
        for i, (pb, pt) in enumerate(potencias.tolist()):
            if banda is None:
                banda, todo = pb, pt
            else:
                banda += k * (pb - banda)
                todo += k * (pt - todo)
            exceso = 10 * math.log10(banda + 1e-12) - max(10 * math.log10(todo + 1e-12) - 10.0, -50.0)
            objetivo = min(DE_ESSER_MAX_DB, 0.6 * exceso) * cantidad if exceso > 0 else 0.0
            if reduccion is None:
                reduccion = objetivo
            else:
                reduccion += (ataque if objetivo > reduccion else liberacion) * (objetivo - reduccion)
            salida[i] = reduccion
        self._banda, self._todo, self._reduccion = banda, todo, reduccion
        return 10 ** (-salida / 20)

    def _nudo(self, sal: int, k: int) -> float:
        return self._nudos.obtener((sal, k), lambda: float(_semilla(sal, self.semilla, k).uniform(-1.0, 1.0)))

    def procesar(self, x: np.ndarray, inicio: int) -> np.ndarray:
        limpia, agudos, eses, deteccion = self._fir.procesar(x)
        potencias = np.stack((np.mean(deteccion * deteccion, axis=1), np.mean(limpia * limpia, axis=1)), axis=1)
        de_esser = self._control.ganancia(potencias, inicio)
        t = np.arange(inicio, inicio + x.shape[0]) / self.frecuencia
        brillo = 10 ** (BRILLO_LENTO_DB * self.cantidad * _lento(t, lambda k: self._nudo(2, k)) / 20)
        volumen = 10 ** (VOLUMEN_LENTO_DB * self.cantidad * _lento(t, lambda k: self._nudo(1, k)) / 20)
        y = limpia + (brillo - 1)[:, None] * agudos + (de_esser - 1)[:, None] * eses
        return y * volumen[:, None]


class _Lugar:
    """Etapa 2: suma a la voz lo que devuelve el lugar (mono: un celular tiene el micrófono en un solo punto)."""

    def __init__(self, lugar: str, ganancia: float, semilla: int, frecuencia: int):
        self._eco = _Convolucion(_respuesta_lugar(lugar, semilla, frecuencia) * ganancia)

    def reiniciar(self, inicio: int) -> None:
        self._eco.reiniciar()

    def procesar(self, x: np.ndarray) -> np.ndarray:
        return x + self._eco.procesar(x.mean(axis=1))[:, None]


class _Microfono:
    """Etapa 4: la respuesta del micrófono del destino y una saturación suave (tanh, sobremuestreada ×2)."""

    def __init__(self, destino: str, cuanto: float, canales: int, frecuencia: int):
        self._fir = _FIR(_filtro_microfono(destino, cuanto, frecuencia), canales)
        self._saturacion = cuanto * SATURACION[destino]
        h = _filtro_sobremuestreo(frecuencia)
        self._sube = _FIR(h, canales)
        self._baja = _FIR(h, canales)

    def reiniciar(self, inicio: int) -> None:
        for fir in (self._fir, self._sube, self._baja):
            fir.reiniciar()

    def procesar(self, x: np.ndarray) -> np.ndarray:
        y = self._fir.procesar(x)[0]
        s = self._saturacion
        if s <= 0:
            return y
        doble = np.zeros((2 * y.shape[0], y.shape[1]))
        doble[0::2] = 2.0 * y
        doble = self._sube.procesar(doble)[0]
        # Mezcla entre lo limpio y lo saturado: con poco "cuánto" casi no se nota; tanh(e·x)/e no cambia el nivel bajo.
        doble = (1 - s) * doble + (s / EMPUJE) * np.tanh(EMPUJE * doble)
        return self._baja.procesar(doble)[0][0::2]


class _Volumen:
    """Etapa 5: el AGC del celular (y, en auriculares, la compuerta de la reducción de ruido)."""

    def __init__(self, cuanto: float, tapa: float, compuerta: bool, frecuencia: int):
        paso = _paso(frecuencia)
        def k(segundos: float) -> float:
            return 1 - math.exp(-paso / (segundos * frecuencia))
        self._k_nivel, self._k_ataque, self._k_liberacion = k(0.010), k(AGC_ATAQUE), k(AGC_LIBERACION)
        self._k_piso, self._k_abre, self._k_cierra = k(0.030), k(0.005), k(0.150)
        self._sube_piso = 3.0 * paso / frecuencia   # dB por cuadro: el piso de ruido sube a 3 dB/s
        self._baja = tapa * cuanto
        self._sube = cuanto
        self._compuerta = COMPUERTA_DB * cuanto if compuerta else 0.0
        self._control = _Control(paso, self._decidir)

    def reiniciar(self, inicio: int) -> None:
        self._control.reiniciar(inicio, 1.0)
        self._nivel = self._g = self._piso = self._puerta = None

    def _decidir(self, potencias: np.ndarray) -> np.ndarray:
        """Ganancia (dB) de cada cuadro: AGC más compuerta."""
        salida = np.empty(potencias.shape[0])
        nivel, g, piso, puerta = self._nivel, self._g, self._piso, self._puerta
        baja, sube, rango = self._baja, self._sube, self._compuerta
        for i, p in enumerate(potencias[:, 0].tolist()):
            # Nivel: RMS de 1 ms suavizado unos 10 ms (si no, sigue cada ciclo de la voz).
            nivel = p if nivel is None else nivel + self._k_nivel * (p - nivel)
            db = 10 * math.log10(nivel + 1e-10)
            falta = OBJETIVO_AGC_DB - db
            if falta < 0:   # fuerte: baja (y tapa la voz) según "tapa"
                objetivo = max(falta, -AGC_BAJA_DB) * baja
            else:           # bajo: sube un poco, pero nunca el silencio
                objetivo = min(falta, AGC_SUBE_DB) * sube * min(1.0, max(0.0, (db - SILENCIO_DB) / 10.0))
            if g is None:
                g = objetivo
            else:
                g += (self._k_ataque if objetivo < g else self._k_liberacion) * (objetivo - g)
            total = g
            if rango:
                # Piso de ruido: baja enseguida y sube despacio. Por encima del piso + 10 dB, la compuerta abre.
                if piso is None:
                    piso = db
                elif db < piso:
                    piso += self._k_piso * (db - piso)
                else:
                    piso = min(db, piso + self._sube_piso)
                apertura = min(1.0, max(0.0, (db - piso - 4.0) / 6.0))
                objetivo = -rango * (1.0 - apertura)
                if puerta is None:
                    puerta = objetivo
                else:   # abre rápido (5 ms) y cierra despacio (150 ms): el fondo "respira" en las pausas
                    puerta += (self._k_abre if objetivo > puerta else self._k_cierra) * (objetivo - puerta)
                total += puerta
            salida[i] = total
        self._nivel, self._g, self._piso, self._puerta = nivel, g, piso, puerta
        return 10 ** (salida / 20)

    def procesar(self, x: np.ndarray, inicio: int) -> np.ndarray:
        return x * self._control.ganancia(np.mean(x * x, axis=1, keepdims=True), inicio)[:, None]


class _RuidoPropio:
    """Etapa 6: ruido rosa del micrófono, con acceso aleatorio exacto.

    Trozos de 1 s (``2T``) que arrancan cada 0,5 s (``T``), cada uno con su semilla
    (semilla, número de trozo) y una ventana seno: dos trozos que se pisan suman
    potencia constante (sen² + cos² = 1). Leer desde cualquier punto da lo mismo
    que leer de corrido.
    """

    def __init__(self, nivel: float, semilla: int, canales: int, frecuencia: int):
        self.nivel = nivel
        self.semilla = semilla
        self.canales = canales
        self.T = T = frecuencia // 2
        f = np.fft.rfftfreq(2 * T, 1.0 / frecuencia)
        forma = 1.0 / np.sqrt(np.maximum(f, 20.0))   # rosa: -3 dB por octava
        forma[0] = 0.0
        # Que salga con RMS 1 (Parseval sobre el espectro completo de 2T puntos).
        forma /= math.sqrt((forma[0] ** 2 + 2 * np.sum(forma[1:-1] ** 2) + forma[-1] ** 2) / (2 * T))
        self._forma = forma[:, None].astype(np.float32)
        self._ventana = np.sin(np.pi * (np.arange(2 * T) + 0.5) / (2 * T))[:, None].astype(np.float32)
        self._trozos = _Cache(4)

    def reiniciar(self, inicio: int) -> None:
        pass   # no tiene estado: todo depende del tiempo absoluto

    def _trozo(self, k: int) -> np.ndarray:
        return self._trozos.obtener(k, lambda: self._crear_trozo(k))

    def _crear_trozo(self, k: int) -> np.ndarray:
        n = 2 * self.T
        # En float32: para un ruido a -62 dBFS sobra, y genera y transforma el doble de rápido.
        blanco = _semilla(7, self.semilla, k + 1).standard_normal((n, self.canales), dtype=np.float32)
        rosa = np.fft.irfft(np.fft.rfft(blanco, axis=0) * self._forma, n, axis=0)
        return rosa * self._ventana

    def leer(self, inicio: int, n: int) -> np.ndarray:
        salida = np.zeros((n, self.canales))
        T = self.T
        for k in range(inicio // T - 1, (inicio + n - 1) // T + 1):   # el trozo k cubre [kT, kT + 2T)
            a, b = max(inicio, k * T), min(inicio + n, k * T + 2 * T)
            if b > a:
                salida[a - inicio:b - inicio] += self._trozo(k)[a - k * T:b - k * T]
        return salida * self.nivel


# ---------------------------------------------------------------------------
# Etapa 7: el códec, de verdad
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Compresion:
    codec: str            # codificador y decodificador de FFmpeg
    frecuencia: int       # a la que trabaja el códec
    canales: int          # 1 = mono
    bits: int             # bit/s
    muestra: str          # formato de muestra que recibe el codificador
    opciones: tuple       # opciones del codificador
    latencia: float       # s: el peor atraso entre lo que entra y lo que ya salió alineado
    saca_relleno: bool    # el decodificador ya descarta el relleno inicial del codificador


# Latencias medidas alimentando de a una muestra (peor caso), más 1 ms de margen:
# * Opus a 16 kHz: 1319 muestras a 48 kHz = cuadro de 20 ms + 6,5 ms de adelanto + ~1 ms del remuestreo.
#   El decodificador de Opus ya saca el "pre-skip" (viene en el extradata): lo que sale está alineado. El
#   retardo de grupo (la pendiente de la fase entre 1 y 5 kHz) da menos de 0,15 muestras y, aun en el arranque
#   del codificador, menos de 0,25. Lo que sí cambia es la fase: SILK adelanta la de los tonos entre 5 y 35°
#   (unos 7° constantes de 1 a 5 kHz). Eso no es un retardo, pero corre el pico de una correlación de tonos.
# * AAC: 3071 = dos cuadros de 1024 (el codificador entrega cada paquete un cuadro después) + los 1024 de
#   relleno inicial, que el decodificador no saca (sin contenedor no hay quién le avise): los saca la cadena.
#   Va con el codificador por defecto de FFmpeg ("twoloop"). El "fast" tarda la mitad, pero deja agujeros en el
#   espectro (entre 8 y 10 kHz, al arrancar cada sílaba: los "pajaritos" metálicos de un AAC malo).
_COMPRESIONES = {
    "whatsapp": _Compresion("libopus", 16000, 1, 24000, "flt", (("application", "voip"),), 0.0285, True),
    # Sin "intensity stereo" (aac_is): con un golpe distinto en cada canal, el AAC de FFmpeg se pasaba
    # hasta +2,6 dB de 0 dBFS. La latencia no cambia (3120 muestras).
    "video": _Compresion("aac", 48000, 2, 128000, "fltp", (("aac_is", "0"),), 0.065, False),
    "auriculares": _Compresion("libopus", 16000, 1, 32000, "flt", (("application", "voip"),), 0.0285, True),
}


def _av():
    """PyAV (vía ``motor/video.py``, que avisa si falta), recién cuando hace falta comprimir."""
    from . import video
    video._verificar_av()
    return video.av


class _Codec:
    """Codifica y decodifica de a bloques, con una cola que devuelve lo ya alineado.

    Entrada: float (n, canales) a 48 kHz. Se baja a mono si el destino es mono, se lleva a
    16 bits, se remuestrea con ``av.AudioResampler`` a la frecuencia del códec, se codifica y
    se decodifica. Los dos decodificadores (Opus y AAC) entregan a 48 kHz: lo decodificado
    solo se pasa a estéreo. Las marcas de tiempo las pone la cadena (contadores de muestras,
    sin huecos) y lo decodificado se pega en orden: nunca se ubica un bloque por su marca,
    así que no hay clics entre bloques.

    Si el códec entregara más tarde que ``latencia`` (por ejemplo, con otra versión de PyAV
    o de libopus), lo que falta sale como silencio una sola vez, al arrancar: el largo no cambia
    y la salida se corre, como mucho, lo que faltó (unas decenas de muestras, alrededor de 1 ms:
    no se oye). No se descarta lo atrasado cuando llega: el códec es determinista, así que el
    faltante se repetiría en cada bloque y el silencio de relleno reaparecería todo el tiempo
    (clics). ``faltaron`` cuenta esas muestras, solo para diagnóstico (0 mientras la latencia
    alcance: la prueba de bloques de 1 a 7 muestras lo vigila). Se arranca con ``reiniciar()``.
    """

    def __init__(self, compresion: _Compresion):
        self.compresion = compresion
        self.latencia = math.ceil(compresion.latencia * FRECUENCIA)
        self.faltaron = 0
        self._av_mod = _av()
        from .audio import _a_flotante
        self._a_flotante = _a_flotante

    def reiniciar(self) -> None:
        av, c = self._av_mod, self.compresion
        self._layout = "mono" if c.canales == 1 else "stereo"
        self._remuestreo = av.AudioResampler(format=c.muestra, layout=self._layout, rate=c.frecuencia)
        cod = av.CodecContext.create(c.codec, "w")
        cod.sample_rate = c.frecuencia
        cod.layout = self._layout
        cod.format = c.muestra
        cod.bit_rate = c.bits
        cod.time_base = Fraction(1, c.frecuencia)
        if c.opciones:
            cod.options = dict(c.opciones)
        cod.open()
        dec = av.CodecContext.create(c.codec, "r")
        dec.extradata = cod.extradata
        dec.open()
        self._codificador, self._decodificador = cod, dec
        self._pts = 0
        self._cola: deque = deque()
        self._alimentadas = self._entregadas = 0
        relleno = 0 if c.saca_relleno else int(cod.initial_padding or 0)
        self._descartar = round(relleno * FRECUENCIA / c.frecuencia)   # se tira del principio de lo decodificado

    def _empujar(self, x: np.ndarray) -> None:
        av = self._av_mod
        datos = x.mean(axis=1, keepdims=True) if self.compresion.canales == 1 else x
        # A 16 bits, como le llega al codificador de un celular. Además, así las diferencias de redondeo de
        # 1e-10 entre procesar de a bloques o todo junto desaparecen: el codificador de Opus las amplificaba
        # (una decisión distinta en un cuadro y ya no vuelve al mismo camino).
        datos = np.clip(np.round(datos * 32768.0), -32768.0, 32767.0) / 32768.0
        cuadro = av.AudioFrame.from_ndarray(np.ascontiguousarray(datos.T, dtype=np.float32), format="fltp",
                                            layout=self._layout)
        cuadro.sample_rate = FRECUENCIA
        cuadro.pts = self._pts
        cuadro.time_base = Fraction(1, FRECUENCIA)
        self._pts += x.shape[0]
        for parte in self._remuestreo.resample(cuadro):
            for paquete in self._codificador.encode(parte):
                for decodificado in self._decodificador.decode(paquete):
                    self._guardar(decodificado)

    def _guardar(self, cuadro) -> None:
        if cuadro.sample_rate != FRECUENCIA:
            raise RuntimeError(f"El decodificador de {self.compresion.codec} entregó a {cuadro.sample_rate} Hz "
                               f"(se esperaba {FRECUENCIA}).")
        datos = self._a_flotante(cuadro).T.astype(np.float64)
        if datos.shape[1] == 1:
            datos = np.repeat(datos, 2, axis=1)
        if self._descartar:
            q = min(self._descartar, datos.shape[0])
            datos = datos[q:]
            self._descartar -= q
        if datos.shape[0]:
            self._cola.append(datos)

    def _sacar(self, m: int) -> np.ndarray:
        salida = np.zeros((m, 2))
        i = 0
        while i < m and self._cola:
            datos = self._cola[0]
            k = min(m - i, datos.shape[0])
            salida[i:i + k] = datos[:k]
            if k == datos.shape[0]:
                self._cola.popleft()
            else:
                self._cola[0] = datos[k:]
            i += k
        if i < m:   # el códec vino tarde: sale silencio y lo que sigue queda corrido eso (solo se cuenta)
            self.faltaron += m - i
        self._entregadas += m
        return salida

    def procesar(self, x: np.ndarray) -> np.ndarray:
        if x.shape[0]:
            self._empujar(x)
            self._alimentadas += x.shape[0]
        return self._sacar(max(0, self._alimentadas - self.latencia) - self._entregadas)

    def vaciar(self) -> np.ndarray:
        """Lo que falta devolver: se empuja silencio hasta que sale todo (lo que siguió fue silencio)."""
        falta = self._alimentadas - self._entregadas
        if falta <= 0:
            return np.zeros((0, 2))
        self._empujar(np.zeros((self.latencia, 2)))
        return self._sacar(falta)


# ---------------------------------------------------------------------------
# La cadena
# ---------------------------------------------------------------------------

_TROZO_MAX = 16384   # muestras por vuelta adentro de procesar: un bloque de 10 minutos no se come la memoria


def _posicion(inicio) -> int:
    inicio = int(inicio)
    if inicio < 0:
        raise ValueError(f"inicio es una muestra del resultado: 0 o más (llegó {inicio}).")
    return inicio


def _bloque(x, nombre: str) -> np.ndarray:
    """Valida un bloque (n, 2) float y cambia NaN e infinitos por 0 y ±1."""
    x = np.asarray(x)
    if x.ndim != 2 or x.shape[1] != 2:
        raise ValueError(f"{nombre} tiene que ser un bloque (n, 2) a 48 kHz; llegó {x.shape}.")
    if x.dtype.kind != "f":
        raise ValueError(f"{nombre} tiene que ser float (float32, entre -1 y 1); llegó {x.dtype}.")
    if not np.isfinite(x).all():   # una sola muestra así envenenaba el AGC para siempre y callaba el códec
        x = np.nan_to_num(x, nan=0.0, posinf=1.0, neginf=-1.0)
    return x


class CadenaVoz:
    """La voz (y el ambiente) como si se hubieran grabado con un celular, de a bloques.

    ajustes     ``AjustesVoz``.
    frecuencia  muestras por segundo de la entrada y de la salida (48000). Con códec tiene que
                ser 48000 (``ValueError`` si no): sus latencias están medidas a esa frecuencia.
    codec       False deja la cadena sin la etapa 7 aunque ``ajustes.compresion`` sea True
                (las pruebas, y el exportador en formato WhatsApp, que ya comprime en Opus).

    ``latencia``: muestras de retardo fijo del códec (0 sin códec), ya compensadas.
    Ver "Bloques, saltos y latencia" y "Cómo la usa el mezclador" al principio del módulo.
    No es para usar desde varios hilos a la vez.
    """

    def __init__(self, ajustes: AjustesVoz, frecuencia: int = FRECUENCIA, codec: bool = True):
        if not isinstance(ajustes, AjustesVoz):
            raise TypeError("ajustes tiene que ser un AjustesVoz.")
        self.ajustes = a = ajustes
        self.frecuencia = fr = int(frecuencia)
        self._igual = a.sin_cambios()
        self._anti_ia = _AntiIA(a.anti_ia, a.semilla, fr) if a.anti_ia > 0 else None
        humedo = a.eco * a.cuanto * DISTANCIA[a.destino]
        self._lugar = _Lugar(a.lugar, humedo, a.semilla, fr) if a.lugar != "ninguno" and humedo > 0 else None
        self._grabar = a.destino != "ninguno" and a.cuanto > 0
        self._microfono = self._volumen = self._ruido = self._codec = None
        self._mono = a.destino in MONO
        if self._grabar:
            canales = 1 if self._mono else 2
            self._microfono = _Microfono(a.destino, a.cuanto, canales, fr)
            self._volumen = _Volumen(a.cuanto, a.tapa, a.destino == "auriculares", fr)
            nivel = 10 ** (RUIDO_PROPIO_DB / 20) * a.ruido_propio * a.cuanto
            if nivel > 0:
                self._ruido = _RuidoPropio(nivel, a.semilla, canales, fr)
            if a.compresion and codec:
                if fr != FRECUENCIA:
                    raise ValueError(f"Con compresión, la cadena trabaja a {FRECUENCIA} Hz (las latencias del códec "
                                     f"están medidas ahí); llegó {fr}. Usá {FRECUENCIA} Hz o codec=False.")
                self._codec = _Codec(_COMPRESIONES[a.destino])
        self.latencia: int = self._codec.latencia if self._codec else 0
        self.reiniciar(0)   # arranca todas las etapas (el códec se arma acá, una sola vez)

    @property
    def posicion_salida(self) -> int:
        """Muestra del resultado donde cae la primera que va a devolver el próximo ``procesar`` (o ``vaciar``)."""
        return self._salida

    def reiniciar(self, inicio: int) -> None:
        """Arranca de cero en la muestra ``inicio`` (0 o más) del resultado (al saltar). Ver ``PRELECTURA``."""
        inicio = _posicion(inicio)
        self._entrada = self._salida = inicio
        self._roto = False
        for etapa in (self._anti_ia, self._lugar, self._microfono, self._volumen, self._ruido):
            if etapa is not None:
                etapa.reiniciar(inicio)
        if self._codec is not None:
            self._codec.reiniciar()

    def procesar(self, voz: np.ndarray, ambiente: np.ndarray, inicio: int) -> np.ndarray:
        """Procesa ``voz`` y ``ambiente`` ((n, 2) float) desde la muestra ``inicio`` del resultado.

        Devuelve float32 (m, 2), alineado con la entrada: m = n sin códec; con códec, m
        es lo que el códec ya devolvió (ver "Latencia" al principio del módulo). Con
        destino, la salida queda entre -1 y 1; **sin destino no se recorta** y puede pasar
        de ±1 (voz + ambiente + eco: se midió 1,93). NaN e infinitos de la entrada se cambian
        por 0 y ±1. Los bloques grandes van por dentro de a ``_TROZO_MAX`` muestras (da lo
        mismo: la cadena ya da igual en bloques).
        """
        voz, ambiente = _bloque(voz, "voz"), _bloque(ambiente, "ambiente")
        if voz.shape != ambiente.shape:
            raise ValueError(f"voz {voz.shape} y ambiente {ambiente.shape} tienen que ser del mismo largo.")
        inicio = _posicion(inicio)
        if self._roto or inicio != self._entrada:
            self.reiniciar(inicio)
        n = voz.shape[0]
        if self._igual:
            salida = (voz + ambiente).astype(np.float32, copy=False)
        elif not n:
            salida = np.zeros((0, 2), np.float32)
        else:
            self._roto = True   # si algo falla a mitad de camino, la próxima llamada arranca de cero
            partes = [self._procesar_trozo(voz[i:i + _TROZO_MAX], ambiente[i:i + _TROZO_MAX], inicio + i)
                      for i in range(0, n, _TROZO_MAX)]
            salida = partes[0] if len(partes) == 1 else np.concatenate(partes)
            self._roto = False
        self._entrada = inicio + n
        self._salida += salida.shape[0]
        return salida

    def _procesar_trozo(self, voz: np.ndarray, ambiente: np.ndarray, inicio: int) -> np.ndarray:
        x = voz.astype(np.float64)
        if self._anti_ia is not None:
            x = self._anti_ia.procesar(x, inicio)
        if self._lugar is not None:
            x = self._lugar.procesar(x)
        x = x + ambiente
        if self._grabar:
            if self._mono:
                x = x.mean(axis=1, keepdims=True)   # un solo micrófono
            x = self._microfono.procesar(x)
            x = self._volumen.procesar(x, inicio)
            if self._ruido is not None:
                x += self._ruido.leer(inicio, voz.shape[0])
            np.clip(x, -1.0, 1.0, out=x)   # el conversor del celular no pasa de 0 dBFS
            if self._codec is not None:
                x = self._codec.procesar(x)   # devuelve estéreo
                np.clip(x, -1.0, 1.0, out=x)
            elif self._mono:
                x = np.repeat(x, 2, axis=1)
        return x.astype(np.float32)

    def vaciar(self) -> np.ndarray:
        """Las últimas muestras que guardaba el códec (``latencia``, o menos si entró menos).

        Se llama una vez, al terminar: bloques + ``vaciar()`` dan exactamente el largo de la
        entrada. Sin códec devuelve un bloque vacío. Con o sin códec, después la cadena queda
        como recién reiniciada al final: se puede seguir procesando desde ahí.
        """
        cola = np.zeros((0, 2), np.float32)
        if self._codec is not None and not self._roto:
            cola = np.clip(self._codec.vaciar(), -1.0, 1.0).astype(np.float32)
        self.reiniciar(self._entrada)
        return cola


__all__ = [
    "DESTINOS", "LUGARES", "FRECUENCIA", "PRELECTURA", "AjustesVoz", "CadenaVoz",
]
