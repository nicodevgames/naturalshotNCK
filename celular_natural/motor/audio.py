"""Sonido del video: ajustes, forma de onda, escucha y exportación del audio.

No depende de la interfaz gráfica. PyAV y ``motor/video.py`` se importan recién
al usarlos, así ``AjustesAudio`` se puede importar (por ejemplo, desde la
sesión) sin cargar FFmpeg.

Tiempos
-------
* **Original:** el del video abierto (0 = su primer cuadro, como en ``video.py``).
  Los tramos conservados (``EdicionVideo.tramos_conservados()``) y los silencios
  van en este tiempo: un silencio no se mueve al cortar.
* **Resultado:** el de lo que se exporta, con lo borrado ya sacado. Los fundidos
  de entrada y de salida van en este tiempo: el principio y el final de lo que
  queda después de los cortes.

La cadena, muestra por muestra
------------------------------
1. Se toma el audio de los tramos conservados, uno detrás de otro.
2. **Silencios:** ganancia 0 adentro de cada tramo silenciado, con rampas de
   5 ms afuera de sus bordes (lo silenciado queda en silencio exacto, sin clics).
3. **Uniones:** en cada borde de tramo que viene de un corte (incluidos la
   entrada y la salida recortadas), un fundido de 5 ms: sin clics.
4. **Fundidos de entrada y de salida** del resultado, con curva cuadrática (se
   oye más pareja que una lineal).
5. **Ganancia:** el volumen. Con **normalizar**, primero va la ganancia que lleva
   el pico de lo que se exporta (lo de los pasos 1 a 3) a -1 dBFS, y después el
   volumen, que ahí solo puede bajar: 1 o más deja el pico en -1 dBFS, 0,5 lo
   deja 6 dB más abajo. Así normalizar nunca se pasa de -1 dBFS.
6. Si la ganancia es mayor que 1 (volumen alto sin normalizar), se recorta a ±1.

Con los ajustes por defecto y sin cortes, las muestras salen idénticas a las del
original (solo cambia lo que cambie el códec al comprimir).

Lectura
-------
* Todo abre también **archivos de solo audio** (MP3, M4A, OGG, WAV, FLAC, para el
  modo Audio): ``info_medio`` es ``video.info_video`` para un video y, sin pista de
  video, arma los datos con la pista de audio (``inicio`` donde empieza esa pista).
* Las marcas de tiempo de MKV y WebM vienen redondeadas al milisegundo:
  ``video.RelojAudio`` pega cada bloque al anterior cuando la marca cae dentro
  de esa resolución (si no, quedaba un clic en cada cuadro de audio).
* ``forma_de_onda`` lee el archivo de corrido, de a un cuadro, sin cargarlo
  entero: en esta PC, unos 2 s para 10 min de AAC estéreo.
* ``LectorPCM`` entrega el resultado listo para escuchar (48 kHz, estéreo,
  int16 intercalado por defecto: lo que espera ``QAudioSink``).
* ``exportar_audio`` guarda solo el audio en M4A (AAC), WAV o MP3, con el mismo
  cuidado que ``exportar_video``: temporal en la misma carpeta y renombrado al
  final, nada a medias si se cancela o falla.
"""

from __future__ import annotations

import math
import os
import tempfile
import threading
import time
from bisect import bisect_right
from collections import OrderedDict, deque
from dataclasses import dataclass, replace
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional, Sequence, Union

import numpy as np

from .procesado import Cancelado

# Objetivo de normalizar: el pico de lo que se exporta queda en -1 dBFS (deja
# margen para lo que agrega el AAC o el MP3 al comprimir).
OBJETIVO_NORMALIZAR_DB = -1.0
_OBJETIVO = 10.0 ** (OBJETIVO_NORMALIZAR_DB / 20.0)
# Normalizar no sube más de +30 dB: un audio casi mudo no se convierte en puro ruido de fondo.
GANANCIA_MAX_NORMALIZAR = 10.0 ** (30.0 / 20.0)
VOLUMEN_MAX = 2.0
FUNDIDO_CORTE = 0.005  # s: fundido en cada unión y en los bordes de los silencios
FRECUENCIA_PCM = 48000  # formato por defecto de LectorPCM
CANALES_PCM = 2
_BLOQUE = 8192  # muestras por vuelta al exportar o medir
_TOLERANCIA_TRAMO = 1e-4  # s: tramos más cortos que esto no cuentan

Tramos = Optional[Sequence[tuple[float, float]]]
Progreso = Callable[[int, int, Optional[float]], None]


def _video():
    """``motor/video.py`` (y con él PyAV), recién cuando hace falta."""
    from . import video
    video._verificar_av()
    return video


# ---------------------------------------------------------------------------
# Ajustes
# ---------------------------------------------------------------------------

def _numero(valor, defecto: float) -> float:
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return defecto
    return v if math.isfinite(v) else defecto


def _unir_tramos(tramos) -> tuple[tuple[float, float], ...]:
    """Ordena, descarta los vacíos o al revés y une los que se pisan o se tocan."""
    limpios = []
    for tramo in tramos or ():
        a, b = (_numero(x, -1.0) for x in tramo)
        a = max(0.0, a)
        if b - a >= _TOLERANCIA_TRAMO:
            limpios.append((a, b))
    limpios.sort()
    unidos: list[tuple[float, float]] = []
    for a, b in limpios:
        if unidos and a <= unidos[-1][1] + 1e-6:
            unidos[-1] = (unidos[-1][0], max(unidos[-1][1], b))
        else:
            unidos.append((a, b))
    return tuple(unidos)


@dataclass(frozen=True)
class AjustesAudio:
    """Cómo sale el sonido. Los valores por defecto no cambian nada.

    quitar           el video sale sin pista de audio (y no hay audio para guardar).
    volumen          de 0 a 2 (1 = igual). Por encima de 1 puede saturar: se recorta a ±1.
    normalizar       lleva el pico de lo que se exporta a -1 dBFS. Va antes del volumen,
                     que con normalizar solo puede bajar (ver ``ganancia``).
    fundido_entrada  segundos que tarda en aparecer el sonido al principio del resultado.
    fundido_salida   segundos que tarda en irse al final del resultado.
    silencios        tramos (inicio, fin) en segundos del tiempo ORIGINAL que quedan en
                     silencio. Siempre ordenados y sin pisarse: los que se tocan se unen.

    Inmutable y con los valores ya acomodados (volumen entre 0 y 2, fundidos no
    negativos, silencios unidos): cada cambio devuelve otro, así deshacer es guardar
    estados. Se puede guardar con pickle, como las demás dataclasses del motor.
    """

    quitar: bool = False
    volumen: float = 1.0
    normalizar: bool = False
    fundido_entrada: float = 0.0
    fundido_salida: float = 0.0
    silencios: tuple[tuple[float, float], ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "quitar", bool(self.quitar))
        object.__setattr__(self, "volumen", min(VOLUMEN_MAX, max(0.0, _numero(self.volumen, 1.0))))
        object.__setattr__(self, "normalizar", bool(self.normalizar))
        object.__setattr__(self, "fundido_entrada", max(0.0, _numero(self.fundido_entrada, 0.0)))
        object.__setattr__(self, "fundido_salida", max(0.0, _numero(self.fundido_salida, 0.0)))
        object.__setattr__(self, "silencios", _unir_tramos(self.silencios))

    def sin_cambios(self) -> bool:
        """True si el sonido sale igual que el original."""
        return self == AjustesAudio()

    def con(self, **cambios) -> "AjustesAudio":
        """Otro con esos campos cambiados (acomodados igual que al crearlo)."""
        return replace(self, **cambios)

    # ------------------------------------------------------------ silencios
    def con_silencio(self, inicio: float, fin: float) -> "AjustesAudio":
        """Silencia de ``inicio`` a ``fin`` (tiempo original). Se une con los que pisa o toca."""
        return replace(self, silencios=self.silencios + ((inicio, fin),))

    def sin_silencio(self, i: int) -> "AjustesAudio":
        """Quita el silencio número ``i`` (si no existe, no cambia nada)."""
        if not 0 <= i < len(self.silencios):
            return self
        return replace(self, silencios=self.silencios[:i] + self.silencios[i + 1:])

    def con_sonido(self, inicio: float, fin: float) -> "AjustesAudio":
        """Devuelve el sonido de ``inicio`` a ``fin``: recorta o parte los silencios que lo tapan."""
        quedan = []
        for a, b in self.silencios:
            if b <= inicio or a >= fin:
                quedan.append((a, b))
                continue
            if a < inicio:
                quedan.append((a, inicio))
            if b > fin:
                quedan.append((fin, b))
        nuevos = _unir_tramos(quedan)
        return self if nuevos == self.silencios else replace(self, silencios=nuevos)

    def sin_silencios(self) -> "AjustesAudio":
        return replace(self, silencios=())

    def silencio_en(self, t: float) -> Optional[int]:
        """Índice del silencio que contiene el instante ``t`` (tiempo original), o None."""
        for i, (a, b) in enumerate(self.silencios):
            if a <= t < b:
                return i
        return None

    def silenciado(self, inicio: float, fin: float) -> bool:
        """True si todo el tramo de ``inicio`` a ``fin`` ya está en silencio (para alternar el botón)."""
        return any(a <= inicio + 1e-6 and fin <= b + 1e-6 for a, b in self.silencios)

    # ------------------------------------------------------------ ganancia
    def ganancia(self, pico: Optional[float] = None) -> float:
        """Factor final por el que se multiplica el sonido (paso 5 de la cadena).

        ``pico``: el de lo que se exporta (``medir_pico``); solo hace falta con
        normalizar. Con normalizar, el volumen va después y solo puede bajar.
        """
        if self.quitar:
            return 0.0
        if not self.normalizar:
            return self.volumen
        if pico is None:
            raise ValueError("Para normalizar hace falta medir el pico antes (medir_pico).")
        base = _OBJETIVO / pico if pico > 1e-9 else 1.0
        return min(base, GANANCIA_MAX_NORMALIZAR) * min(self.volumen, 1.0)


# ---------------------------------------------------------------------------
# Lectura del audio del archivo
# ---------------------------------------------------------------------------

class RelojAudio:
    """Dónde empieza cada bloque de audio decodificado, en muestras desde el inicio del video.

    Matroska y WebM guardan las marcas de tiempo en milisegundos (time_base 1/1000):
    un cuadro AAC de 1024 muestras a 48 kHz dura 21,33 ms y su marca llega
    redondeada, corrida hasta ±24 muestras. Creerle a cada marca deja un hueco o
    un salto (un clic) en cada cuadro: eran unos 390 en 3 s de un tono. Por eso,
    si la marca cae dentro de la resolución del time_base respecto de donde
    terminó el bloque anterior, el bloque va pegado a ese; si no, es un hueco o un
    pisado de verdad (audio cortado, cuadros perdidos) y se respeta la marca.
    """

    def __init__(self, frecuencia: int, time_base, inicio: float = 0.0):
        self.frecuencia = int(frecuencia)
        resolucion = math.ceil(self.frecuencia * float(time_base)) if time_base else 0
        self.tolerancia = 2 + resolucion  # muestras
        self.inicio = float(inicio)
        self.siguiente: Optional[int] = None  # donde terminó el bloque anterior

    def ubicar(self, cuadro) -> int:
        """Primera muestra del bloque (puede ser negativa si el audio empieza antes que el video)."""
        if cuadro.pts is not None and cuadro.time_base is not None:
            k = round((float(cuadro.pts * cuadro.time_base) - self.inicio) * self.frecuencia)
            if self.siguiente is not None and abs(k - self.siguiente) <= self.tolerancia:
                k = self.siguiente
        else:  # sin marca: va pegado al anterior
            k = self.siguiente if self.siguiente is not None else 0
        self.siguiente = k + cuadro.samples
        return k

    def reiniciar(self) -> None:
        """Después de buscar: el próximo bloque se ubica por su marca."""
        self.siguiente = None


def _solo_audio(contenedor, stream) -> None:
    """Que el demuxer ni lea los otros streams (el video pesa cien veces más que el audio)."""
    av = _video().av
    for s in contenedor.streams:
        if s.index != stream.index:
            try:
                s.discard = av.stream.Discard.all
            except Exception:
                pass


def _a_flotante(cuadro) -> np.ndarray:
    """Muestras de un cuadro decodificado como float32 (canales × n) entre -1 y 1, sin remuestrear."""
    datos = cuadro.to_ndarray()
    canales = cuadro.layout.nb_channels or 1
    if not cuadro.format.is_planar:  # intercalado: (1, n × canales)
        datos = datos.reshape(-1, canales).T
    elif datos.ndim == 1:
        datos = datos[None, :]
    if datos.dtype.kind == "f":
        return datos.astype(np.float32, copy=False)
    if datos.dtype == np.uint8:
        return (datos.astype(np.float32) - 128.0) / 128.0
    return datos.astype(np.float32) / float(2 ** (8 * datos.dtype.itemsize - 1))


class _FuenteAudio:
    """El audio del archivo como una tira continua de muestras float32 (canales × n).

    La muestra k es la del instante k / frecuencia del tiempo original. Donde no
    hay audio (antes de que empiece, en un hueco o después del final) da ceros.
    Lee de corrido; para volver atrás o adelantar mucho, busca en el archivo.
    """

    PREVIO = 0.5  # s: se busca un poco antes (la búsqueda puede caer pasada) y se descarta hasta el punto
    SALTO = 4.0   # s: para adelantar más que esto conviene buscar que decodificar y tirar

    def __init__(self, ruta: Union[str, os.PathLike], info, frecuencia: int, canales: int):
        mv = _video()
        self._av = mv.av
        self._contenedor = mv.av.open(str(ruta))
        try:
            if not self._contenedor.streams.audio:
                raise ValueError("El video no tiene sonido.")
            self._stream = self._contenedor.streams.audio[0]
            _solo_audio(self._contenedor, self._stream)
            self._tb = self._stream.time_base
        except BaseException:
            self._contenedor.close()
            raise
        self.frecuencia = int(frecuencia)
        self.canales = 1 if int(canales) == 1 else 2
        self._layout = "mono" if self.canales == 1 else "stereo"
        self._inicio = float(info.inicio)
        self._reloj = RelojAudio(self.frecuencia, self._tb, self._inicio)
        self._paquetes = None
        self._remuestreo = None
        self._trozos: deque = deque()  # (primera muestra, datos), en orden y sin pisarse
        self._fin: Optional[int] = None  # una después de la última muestra decodificada
        self._agotado = False
        self._desde = 0  # antes de esta muestra ya se descartó todo (para volver, hay que buscar)

    def cerrar(self) -> None:
        self._cerrar_paquetes()
        try:
            self._contenedor.close()
        except Exception:
            pass

    def _cerrar_paquetes(self) -> None:
        if self._paquetes is not None:
            try:
                self._paquetes.close()
            except Exception:
                pass
            self._paquetes = None

    def _buscar(self, muestra: int) -> None:
        t = max(0.0, muestra / self.frecuencia - self.PREVIO)
        self._cerrar_paquetes()
        destino = self._inicio + t
        if self._tb:
            self._contenedor.seek(int(destino / self._tb), stream=self._stream, backward=True, any_frame=False)
        else:
            self._contenedor.seek(int(destino * 1_000_000), backward=True, any_frame=False)
        self._remuestreo = None
        self._reloj.reiniciar()
        self._trozos.clear()
        self._fin = None
        self._agotado = False
        self._desde = muestra

    def _remuestrear(self, cuadro) -> list:
        if self._remuestreo is None:
            if cuadro is None:
                return []
            self._remuestreo = self._av.AudioResampler(format="fltp", layout=self._layout, rate=self.frecuencia)
        try:
            salida = self._remuestreo.resample(cuadro)
        except ValueError:
            # Cambió el formato a mitad del archivo (pasa en algunas transmisiones): se arranca otro.
            if cuadro is None:
                return []
            self._remuestreo = self._av.AudioResampler(format="fltp", layout=self._layout, rate=self.frecuencia)
            salida = self._remuestreo.resample(cuadro)
        return [c for c in salida if c is not None]

    def _agregar(self, cuadro) -> None:
        n = cuadro.samples
        if not n:
            return
        k = self._reloj.ubicar(cuadro)
        if k + n <= self._desde:  # todavía antes de lo pedido (después de buscar)
            self._fin = k + n if self._fin is None else max(self._fin, k + n)
            return
        datos = cuadro.to_ndarray()
        if datos.ndim == 1:
            datos = datos[None, :]
        if self._fin is not None and k < self._fin:  # se pisa con lo anterior: se descarta lo repetido
            datos = datos[:, self._fin - k:]
            k = self._fin
            if not datos.shape[1]:
                return
        self._trozos.append((k, datos))
        self._fin = k + datos.shape[1]

    def _decodificar(self) -> None:
        av = self._av
        if self._paquetes is None:
            self._paquetes = self._contenedor.demux(self._stream)
        try:
            paquete = next(self._paquetes)
        except StopIteration:
            for c in self._remuestrear(None):
                self._agregar(c)
            self._agotado = True
            return
        except av.error.FFmpegError:  # el archivo se corta o está dañado: lo que sigue es silencio
            self._agotado = True
            return
        try:
            cuadros = paquete.decode()
        except av.error.FFmpegError:
            return  # un paquete dañado: queda un hueco de silencio
        for cuadro in cuadros:
            for c in self._remuestrear(cuadro):
                self._agregar(c)

    def _podar(self, muestra: int) -> None:
        """Descarta lo decodificado antes de ``muestra``."""
        while self._trozos:
            k, datos = self._trozos[0]
            fin = k + datos.shape[1]
            if fin <= muestra:
                self._trozos.popleft()
            elif k < muestra:
                self._trozos[0] = (muestra, datos[:, muestra - k:])
                break
            else:
                break

    def leer(self, desde: int, n: int) -> np.ndarray:
        """Exactamente ``n`` muestras desde la muestra ``desde`` (float32, canales × n)."""
        salida = np.zeros((self.canales, max(0, n)), np.float32)
        if n <= 0:
            return salida
        hasta = desde + n
        salto = int(self.SALTO * self.frecuencia)
        leido = self._fin if self._fin is not None else self._desde
        if desde < self._desde or desde > leido + salto:
            self._buscar(desde)
        self._desde = max(self._desde, desde)
        self._podar(desde)
        while not self._agotado and (self._fin is None or self._fin < hasta):
            self._decodificar()
        for k, datos in self._trozos:
            if k >= hasta:
                break
            a, b = max(k, desde), min(k + datos.shape[1], hasta)
            if b > a:
                salida[:, a - desde:b - desde] = datos[:, a - k:b - k]
        self._podar(hasta)
        self._desde = hasta
        return salida


def _a_int16(datos: np.ndarray) -> np.ndarray:
    """Float -> int16 como lo hace FFmpeg (×32768 y recorte): un PCM de 16 bits vuelve idéntico."""
    return np.clip(np.round(datos * 32768.0), -32768, 32767).astype(np.int16)


def _formato_natural(info) -> tuple[int, int]:
    """Frecuencia y canales con los que se mide y se exporta: los del original (más de 2 canales -> estéreo)."""
    frecuencia = int(info.frecuencia_audio or 48000)
    canales = 1 if int(info.canales_audio or 2) == 1 else 2
    return frecuencia, canales


# ---------------------------------------------------------------------------
# El resultado: tramos uno detrás de otro, con los ajustes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Tramo:
    a: int               # primera muestra (tiempo original)
    b: int               # una después de la última
    o: int               # dónde empieza en el resultado
    corte_inicio: bool   # empieza en un corte: fundido corto al entrar
    corte_fin: bool      # termina en un corte: fundido corto al salir


def _rampa(x: np.ndarray) -> np.ndarray:
    """Coseno elevado de 0 a 1 (más suave que una recta: no deja clics)."""
    return 0.5 - 0.5 * np.cos(np.pi * np.clip(x, 0.0, 1.0))


class _Plan:
    """Los tramos en muestras y las ganancias de cada muestra del resultado."""

    def __init__(self, tramos: Sequence[tuple[float, float]], duracion: float, ajustes: AjustesAudio,
                 frecuencia: int, canales: int, ganancia: float):
        fr = int(frecuencia)
        self.frecuencia, self.canales, self.ganancia = fr, int(canales), float(ganancia)
        natural = round(duracion * fr) - max(1, round(0.001 * fr))  # terminar acá no es un corte
        self.tramos: list[_Tramo] = []
        o = 0
        for a, b in tramos:
            ia, ib = round(a * fr), round(b * fr)
            if ib <= ia:
                continue
            self.tramos.append(_Tramo(ia, ib, o, ia > 0, ib < natural))
            o += ib - ia
        self.total = o
        self._inicios = [t.o for t in self.tramos]
        self.rampa = max(1, round(FUNDIDO_CORTE * fr))
        self.silencios = [(round(a * fr), round(b * fr)) for a, b in ajustes.silencios
                          if round(b * fr) > round(a * fr)]
        self.entrada = round(ajustes.fundido_entrada * fr)
        self.salida = round(ajustes.fundido_salida * fr)

    def tramo_en(self, o: int) -> int:
        """Índice del tramo que tiene la muestra ``o`` del resultado."""
        return max(0, bisect_right(self._inicios, o) - 1)

    def resultado_de(self, muestra: int) -> int:
        """Muestra del resultado para una del original (si cae en lo borrado: el comienzo del siguiente tramo)."""
        for t in self.tramos:
            if muestra < t.b:
                return t.o + max(0, muestra - t.a)
        return self.total

    def original_de(self, o: int) -> int:
        if not self.tramos:
            return 0
        if o >= self.total:
            return self.tramos[-1].b
        t = self.tramos[self.tramo_en(o)]
        return t.a + (o - t.o)

    def envolvente(self, i: int, s0: int, o0: int, n: int) -> Optional[np.ndarray]:
        """Ganancia de cada muestra (pasos 2 a 4), o None si es 1 en todo el bloque.

        ``i``: tramo; ``s0``: primera muestra en el tiempo original; ``o0``: en el resultado.
        """
        g: Optional[np.ndarray] = None
        r = self.rampa
        t = self.tramos[i]

        def por(factor: np.ndarray) -> None:
            nonlocal g
            g = factor if g is None else g * factor

        if t.corte_inicio and s0 < t.a + r:  # entra después de un corte
            por(_rampa((np.arange(s0 - t.a, s0 - t.a + n) + 0.5) / r))
        if t.corte_fin and s0 + n > t.b - r:  # sale hacia un corte
            por(_rampa((t.b - np.arange(s0, s0 + n) - 0.5) / r))
        for p, q in self.silencios:
            if q + r <= s0 or p - r >= s0 + n:
                continue
            s = np.arange(s0, s0 + n)
            distancia = np.maximum(p - s, s - q + 1)  # muestras hasta el silencio (<= 0: adentro)
            por(_rampa((distancia - 0.5) / r))
        if self.entrada and o0 < self.entrada:
            por(np.clip((np.arange(o0, o0 + n) + 0.5) / self.entrada, 0.0, 1.0) ** 2)
        if self.salida and o0 + n > self.total - self.salida:
            por(np.clip((self.total - np.arange(o0, o0 + n) - 0.5) / self.salida, 0.0, 1.0) ** 2)
        return None if g is None else g.astype(np.float32)


class _Mezcla:
    """El audio del resultado, de a bloques: los tramos conservados con los ajustes aplicados."""

    def __init__(self, fuente: Optional[_FuenteAudio], plan: _Plan):
        self.fuente = fuente
        self.plan = plan
        self.pos = 0  # próxima muestra del resultado

    @property
    def total(self) -> int:
        return self.plan.total

    def leer(self, n: int) -> np.ndarray:
        """Hasta ``n`` muestras (canales × m, float32); m = 0 al terminar."""
        plan = self.plan
        n = max(0, min(int(n), plan.total - self.pos))
        partes = []
        while n > 0:
            i = plan.tramo_en(self.pos)
            t = plan.tramos[i]
            dentro = self.pos - t.o
            m = min(n, (t.b - t.a) - dentro)
            s0 = t.a + dentro
            if self.fuente is None or plan.ganancia == 0.0:
                datos = np.zeros((plan.canales, m), np.float32)
            else:
                datos = self.fuente.leer(s0, m)
                envolvente = plan.envolvente(i, s0, self.pos, m)
                if envolvente is not None:
                    datos *= envolvente
                if plan.ganancia != 1.0:
                    datos *= np.float32(plan.ganancia)
                    if plan.ganancia > 1.0:
                        np.clip(datos, -1.0, 1.0, out=datos)
            partes.append(datos)
            self.pos += m
            n -= m
        if not partes:
            return np.zeros((plan.canales, 0), np.float32)
        return partes[0] if len(partes) == 1 else np.concatenate(partes, axis=1)

    def cerrar(self) -> None:
        if self.fuente is not None:
            self.fuente.cerrar()


# ---------------------------------------------------------------------------
# Archivos de solo audio
# ---------------------------------------------------------------------------

FPS_SOLO_AUDIO = 1000.0  # la "grilla de cuadros" de un audio: 1 ms (para los cortes de EdicionVideo)

# Demuxers de flujos crudos: sin índice ni cabecera, FFmpeg estima la duración por la tasa de bits.
_FLUJOS_CRUDOS = frozenset({"aac", "ac3", "eac3", "dts", "truehd", "mp2"})

_CACHE_INFO_AUDIO: dict[tuple, object] = {}
_CANDADO_INFO_AUDIO = threading.Lock()


def _es_tapa(stream) -> bool:
    """Una "pista de video" que en realidad es la tapa del disco (MP3 o M4A con imagen)."""
    av = _video().av
    try:
        return bool(stream.disposition & av.stream.Disposition.attached_pic)
    except Exception:
        return False


def info_medio(ruta: Union[str, os.PathLike]):
    """Como ``video.info_video``, pero también abre archivos de solo audio (MP3, M4A, OGG, WAV, FLAC…).

    Con video, es exactamente ``info_video``. Sin video (o si el único "video" es la
    tapa del disco), los datos salen de la pista de audio:

    * ``inicio``: donde empieza la pista. Así la primera muestra que se decodifica es
      el instante 0 (en un MP3, FFmpeg ya descartó el retardo del codificador y la
      pista empieza unos 23 ms "tarde": sin esto, todo quedaba corrido).
    * ``duracion``: la de la pista. Si no la dice, o si es un flujo crudo (AAC en ADTS, AC-3…:
      FFmpeg la estima por la tasa de bits y erraba casi un segundo en 20 s), la suma de las
      duraciones de sus paquetes, leyéndolos sin decodificar (unos ms por minuto).
    * ``fps`` = ``FPS_SOLO_AUDIO`` (los cortes se ajustan al milisegundo), tamaño 0 × 0,
      ``codec`` vacío y ``cuadros`` 0.

    Queda en caché por archivo (ruta, fecha y tamaño), como ``info_video``.
    """
    mv = _video()
    clave = mv._clave_archivo(ruta)
    with _CANDADO_INFO_AUDIO:
        guardada = _CACHE_INFO_AUDIO.get(clave)
    if guardada is not None:
        return guardada
    info = None
    with mv.av.open(str(ruta)) as c:
        if not any(not _es_tapa(s) for s in c.streams.video):
            info = _info_solo_audio(mv, ruta, c)
    if info is None:
        info = mv.info_video(ruta)
    with _CANDADO_INFO_AUDIO:
        _CACHE_INFO_AUDIO[clave] = info
        while len(_CACHE_INFO_AUDIO) > 64:
            _CACHE_INFO_AUDIO.pop(next(iter(_CACHE_INFO_AUDIO)))
    return info


def _info_solo_audio(mv, ruta, contenedor):
    if not contenedor.streams.audio:
        raise ValueError("El archivo no tiene sonido ni video.")
    sa = contenedor.streams.audio[0]
    tb = sa.time_base
    inicio = float(sa.start_time * tb) if sa.start_time is not None and tb else 0.0
    if sa.duration is not None and tb and contenedor.format.name not in _FLUJOS_CRUDOS:
        duracion = float(sa.duration * tb)
    else:
        duracion = _duracion_por_paquetes(contenedor, sa)
        if duracion <= 0 and contenedor.duration is not None:
            duracion = max(0.0, contenedor.duration / 1_000_000 - inicio)
    ca = sa.codec_context
    canales = int(getattr(ca, "channels", 0) or (ca.layout.nb_channels if ca.layout else 0))
    return mv.InfoVideo(
        ruta=str(ruta), duracion=duracion, fps=FPS_SOLO_AUDIO, ancho=0, alto=0, cuadros=0, codec="",
        tiene_audio=True, rotacion=0, tasa=Fraction(int(FPS_SOLO_AUDIO)), inicio=inicio, codec_audio=ca.name or "",
        frecuencia_audio=int(ca.sample_rate or 0), canales_audio=canales,
    )


def _duracion_por_paquetes(contenedor, sa) -> float:
    """Suma de las duraciones de los paquetes de la pista (sin decodificar: unos ms por minuto)."""
    total = 0
    try:
        for paquete in contenedor.demux(sa):
            if paquete.duration:
                total += paquete.duration
    except Exception:   # el final dañado de un archivo: alcanza con lo leído
        pass
    return float(total * sa.time_base) if sa.time_base else 0.0


def _tramos_y_info(ruta, tramos: Tramos):
    mv = _video()
    info = info_medio(ruta)
    return info, mv.normalizar_tramos(tramos, info.duracion)


def preparar_mezcla(ruta: Union[str, os.PathLike], tramos: Tramos, ajustes: Optional[AjustesAudio],
                    frecuencia: int, canales: int, pico: Optional[float] = None,
                    cancelado: Optional[Callable[[], bool]] = None) -> _Mezcla:
    """La mezcla del resultado para exportar (la usa ``video.exportar_video``).

    Con normalizar y sin ``pico``, lo mide antes (``medir_pico``, con caché).
    """
    ajustes = ajustes or AjustesAudio()
    info, tramos_ok = _tramos_y_info(ruta, tramos)
    if ajustes.normalizar and pico is None and info.tiene_audio:
        pico = medir_pico(ruta, tramos_ok, ajustes.silencios, cancelado)
    ganancia = ajustes.ganancia(pico if pico is not None else 1.0)
    plan = _Plan(tramos_ok, info.duracion, ajustes, frecuencia, canales, ganancia)
    fuente = _FuenteAudio(ruta, info, frecuencia, canales) if info.tiene_audio and ganancia > 0 else None
    return _Mezcla(fuente, plan)


# ---------------------------------------------------------------------------
# Pico (para normalizar)
# ---------------------------------------------------------------------------

_CACHE_PICOS: "OrderedDict[tuple, float]" = OrderedDict()
_CANDADO_PICOS = threading.Lock()


def medir_pico(ruta: Union[str, os.PathLike], tramos: Tramos = None, silencios: Sequence[tuple[float, float]] = (),
               cancelado: Optional[Callable[[], bool]] = None) -> float:
    """Pico (valor absoluto, 0 a 1 o algo más) de lo que se exportaría con esos tramos y silencios.

    Es una pasada rápida solo de audio (unos segundos para un video de varios
    minutos), con la frecuencia y los canales del original. Incluye los
    silencios y los fundidos cortos de las uniones, pero no el volumen ni los
    fundidos de entrada y salida (que solo bajan). Queda en caché por archivo
    (ruta, fecha y tamaño), tramos y silencios. Sin audio, 0.
    """
    mv = _video()
    info, tramos_ok = _tramos_y_info(ruta, tramos)
    silencios = _unir_tramos(silencios)
    clave = (mv._clave_archivo(ruta), tuple(tramos_ok), silencios)
    with _CANDADO_PICOS:
        if clave in _CACHE_PICOS:
            _CACHE_PICOS.move_to_end(clave)
            return _CACHE_PICOS[clave]
    pico = 0.0
    if info.tiene_audio and tramos_ok:
        cancelado = cancelado or (lambda: False)
        frecuencia, canales = _formato_natural(info)
        plan = _Plan(tramos_ok, info.duracion, AjustesAudio(silencios=silencios), frecuencia, canales, 1.0)
        mezcla = _Mezcla(_FuenteAudio(ruta, info, frecuencia, canales), plan)
        try:
            while True:
                if cancelado():
                    raise Cancelado()
                bloque = mezcla.leer(_BLOQUE * 4)
                if not bloque.shape[1]:
                    break
                pico = max(pico, float(np.abs(bloque).max()))
        finally:
            mezcla.cerrar()
    with _CANDADO_PICOS:
        _CACHE_PICOS[clave] = pico
        while len(_CACHE_PICOS) > 32:
            _CACHE_PICOS.popitem(last=False)
    return pico


# ---------------------------------------------------------------------------
# Forma de onda
# ---------------------------------------------------------------------------

@dataclass(frozen=True, eq=False)
class FormaOnda:
    """Picos del audio por columna, para dibujar debajo de la línea de tiempo.

    La columna k cubre de ``k · duracion / columnas`` a ``(k + 1) · duracion /
    columnas`` del tiempo original (el mismo de la línea de tiempo). ``minimos``
    y ``maximos`` (float32, entre -1 y 1) son el menor y el mayor valor de todos
    los canales en esa columna; donde no hay audio, 0. Mientras se calcula,
    solo valen las primeras ``listas`` columnas (las demás están en 0).
    """

    duracion: float
    minimos: np.ndarray
    maximos: np.ndarray
    listas: int

    @property
    def columnas(self) -> int:
        return int(self.minimos.shape[0])

    @property
    def completa(self) -> bool:
        return self.listas >= self.columnas

    def picos(self) -> np.ndarray:
        """Pico absoluto por columna (0 a 1), para dibujar una forma simétrica."""
        return np.maximum(-self.minimos, self.maximos)

    def columna_en(self, t: float) -> int:
        if self.duracion <= 0:
            return 0
        return min(self.columnas - 1, max(0, int(t / self.duracion * self.columnas)))

    def reducida(self, columnas: int) -> "FormaOnda":
        """La misma forma en otra cantidad de columnas, sin volver a leer el archivo.

        Conviene pedir la forma una vez con muchas columnas (por ejemplo 4000) y
        reducirla al ancho en píxeles cada vez que se dibuja o cambia el tamaño:
        cada columna nueva toma el mínimo y el máximo de las que cubre. Con más
        columnas que las calculadas, se repiten.
        """
        columnas = max(1, int(columnas))
        if columnas == self.columnas:
            return self
        bordes = (np.arange(columnas, dtype=np.int64) * self.columnas) // columnas
        return FormaOnda(self.duracion, np.minimum.reduceat(self.minimos, bordes),
                         np.maximum.reduceat(self.maximos, bordes), self.listas * columnas // self.columnas)


_CACHE_ONDAS: "OrderedDict[tuple, FormaOnda]" = OrderedDict()
_CANDADO_ONDAS = threading.Lock()


class _Columnas:
    """Acumula mínimos y máximos por columna a medida que llegan las muestras."""

    def __init__(self, columnas: int, muestras_totales: float):
        self.n = columnas
        self.por_columna = muestras_totales / columnas  # muestras por columna (no entero)
        self.total = int(math.ceil(muestras_totales))
        self.minimos = np.full(columnas, np.inf, np.float32)
        self.maximos = np.full(columnas, -np.inf, np.float32)
        self.hasta = 0  # una después de la última muestra vista

    def agregar(self, k: int, bajo: np.ndarray, alto: np.ndarray) -> None:
        """Muestras contiguas desde la ``k`` (ya reducidas a un valor por muestra)."""
        a, b = max(0, -k), min(bajo.shape[0], self.total - k)
        if b <= a:
            return
        bajo, alto, inicio = bajo[a:b], alto[a:b], k + a
        c0 = int(inicio / self.por_columna)
        c1 = min(self.n - 1, int((inicio + bajo.shape[0] - 1) / self.por_columna))
        if c1 <= c0:
            c0 = min(c0, self.n - 1)
            self.minimos[c0] = min(self.minimos[c0], bajo.min())
            self.maximos[c0] = max(self.maximos[c0], alto.max())
        else:
            # Dónde empieza cada columna dentro del bloque: la muestra s es de la columna floor(s / por_columna).
            bordes = np.ceil(np.arange(c0 + 1, c1 + 1) * self.por_columna).astype(np.int64) - inicio
            bordes = np.concatenate(([0], np.clip(bordes, 0, bajo.shape[0] - 1)))
            self.minimos[c0:c1 + 1] = np.minimum(self.minimos[c0:c1 + 1], np.minimum.reduceat(bajo, bordes))
            self.maximos[c0:c1 + 1] = np.maximum(self.maximos[c0:c1 + 1], np.maximum.reduceat(alto, bordes))
        self.hasta = max(self.hasta, inicio + bajo.shape[0])

    def foto(self, duracion: float, final: bool) -> FormaOnda:
        minimos = np.where(np.isfinite(self.minimos), self.minimos, 0.0).astype(np.float32)
        maximos = np.where(np.isfinite(self.maximos), self.maximos, 0.0).astype(np.float32)
        listas = self.n if final else min(self.n, int(self.hasta / self.por_columna))
        return FormaOnda(duracion, minimos, maximos, listas)


def forma_de_onda(
    ruta: Union[str, os.PathLike],
    columnas: int,
    progreso: Optional[Callable[[FormaOnda], None]] = None,
    cancelado: Optional[Callable[[], bool]] = None,
    intervalo: float = 0.25,
) -> Optional[FormaOnda]:
    """Forma de onda de todo el video en ``columnas`` columnas (ver ``FormaOnda``).

    Lee el archivo de corrido, de a un cuadro de audio: nunca lo carga entero.
    Pensada para correr en un hilo:

    progreso    progreso(parcial): cada ``intervalo`` segundos, con lo calculado
                hasta ahí (una copia: ``parcial.listas`` dice hasta qué columna vale).
    cancelado   cancelado() -> True para abandonar: se lanza ``Cancelado``.

    Devuelve None si el video no tiene sonido. El resultado queda en caché por
    archivo y cantidad de columnas. Para dibujar, conviene pedirla una vez con
    muchas columnas y achicarla con ``FormaOnda.reducida(ancho)``.
    """
    mv = _video()
    av = mv.av
    info = info_medio(ruta)
    columnas = max(1, int(columnas))
    if not info.tiene_audio or info.duracion <= 0:
        return None
    clave = (mv._clave_archivo(ruta), columnas)
    with _CANDADO_ONDAS:
        if clave in _CACHE_ONDAS:
            _CACHE_ONDAS.move_to_end(clave)
            return _CACHE_ONDAS[clave]
    cancelado = cancelado or (lambda: False)
    with av.open(str(ruta)) as contenedor:
        stream = contenedor.streams.audio[0]
        _solo_audio(contenedor, stream)
        frecuencia = int(stream.codec_context.sample_rate or info.frecuencia_audio or 48000)
        reloj = RelojAudio(frecuencia, stream.time_base, info.inicio)
        acumulado = _Columnas(columnas, info.duracion * frecuencia)
        # Se juntan varios cuadros contiguos antes de repartirlos: menos vueltas de Python.
        corrida_k, bajos, altos, en_corrida = 0, [], [], 0
        proximo_aviso = time.perf_counter() + intervalo

        def volcar() -> None:
            nonlocal bajos, altos, en_corrida
            if en_corrida:
                bajo = bajos[0] if len(bajos) == 1 else np.concatenate(bajos)
                alto = altos[0] if len(altos) == 1 else np.concatenate(altos)
                acumulado.agregar(corrida_k, bajo, alto)
            bajos, altos, en_corrida = [], [], 0

        for paquete in contenedor.demux(stream):
            if cancelado():
                raise Cancelado()
            try:
                cuadros = paquete.decode()
            except av.error.FFmpegError:
                continue  # paquete dañado: esa parte queda vacía
            for cuadro in cuadros:
                if not cuadro.samples:
                    continue
                k = reloj.ubicar(cuadro)
                datos = _a_flotante(cuadro)
                if datos.shape[0] > 1:
                    bajo, alto = datos.min(axis=0), datos.max(axis=0)
                else:
                    bajo = alto = datos[0]
                if en_corrida and k != corrida_k + en_corrida:
                    volcar()
                if not en_corrida:
                    corrida_k = k
                bajos.append(bajo)
                altos.append(alto)
                en_corrida += bajo.shape[0]
                if en_corrida >= 65536:
                    volcar()
            if reloj.siguiente is not None and reloj.siguiente >= acumulado.total + frecuencia:
                break  # ya pasó el final del video
            if progreso is not None and time.perf_counter() >= proximo_aviso:
                volcar()
                progreso(acumulado.foto(info.duracion, final=False))
                proximo_aviso = time.perf_counter() + intervalo
        volcar()
    forma = acumulado.foto(info.duracion, final=True)
    with _CANDADO_ONDAS:
        _CACHE_ONDAS[clave] = forma
        while len(_CACHE_ONDAS) > 8:
            _CACHE_ONDAS.popitem(last=False)
    if progreso is not None:
        progreso(forma)
    return forma


# ---------------------------------------------------------------------------
# Escuchar (vista previa)
# ---------------------------------------------------------------------------

class LectorPCM:
    """El sonido del resultado, listo para escuchar, desde cualquier instante.

    Entrega bloques de PCM intercalado (L R L R…) en un formato fijo, con los
    ajustes aplicados (volumen, normalizar, silencios, fundidos según la
    posición en el resultado y los fundidos cortos de las uniones) y salteando
    lo borrado. No usa Qt: la interfaz lo conecta a ``QAudioSink``.

    ruta        el video.
    tramos      los que se conservan (``EdicionVideo.tramos_conservados()``); None = todo.
    ajustes     ``AjustesAudio`` (None = sin cambios).
    desde       instante del tiempo ORIGINAL donde empezar (si cae en lo borrado,
                arranca en el tramo siguiente).
    frecuencia  muestras por segundo (48000 por defecto).
    canales     1 o 2.
    formato     "s16" (int16, ``QAudioFormat.Int16``) o "f32" (float32, ``QAudioFormat.Float``).
    pico        el de ``medir_pico``, si se normaliza. Si falta, se mide al crearlo
                (con caché: la segunda vez es inmediato).

    Sin audio en el video, entrega silencio del largo del resultado (``tiene_audio`` es False).
    Se puede usar desde varios hilos (un pedido a la vez): por ejemplo, ``leer``
    desde el del audio e ``ir_a`` desde el de la interfaz.
    """

    FORMATOS = {"s16": np.int16, "f32": np.float32}

    def __init__(self, ruta: Union[str, os.PathLike], tramos: Tramos = None, ajustes: Optional[AjustesAudio] = None,
                 desde: float = 0.0, frecuencia: int = FRECUENCIA_PCM, canales: int = CANALES_PCM,
                 formato: str = "s16", pico: Optional[float] = None):
        if formato not in self.FORMATOS:
            raise ValueError(f"Formato desconocido: {formato!r} (usá 's16' o 'f32').")
        self.ruta = str(ruta)
        self.info, self.tramos = _tramos_y_info(ruta, tramos)
        self.frecuencia = int(frecuencia)
        self.canales = 1 if int(canales) == 1 else 2
        self.formato = formato
        self.tiene_audio = bool(self.info.tiene_audio)
        self._candado = threading.Lock()
        self._fuente: Optional[_FuenteAudio] = None
        if self.tiene_audio:
            self._fuente = _FuenteAudio(ruta, self.info, self.frecuencia, self.canales)
        self._mezcla = _Mezcla(self._fuente, self._plan(ajustes or AjustesAudio(), pico))
        self.ir_a(desde)

    def _plan(self, ajustes: AjustesAudio, pico: Optional[float]) -> _Plan:
        if ajustes.normalizar and pico is None and self.tiene_audio:
            pico = medir_pico(self.ruta, self.tramos, ajustes.silencios)
        self.ajustes = ajustes
        ganancia = ajustes.ganancia(pico if pico is not None else 1.0)
        return _Plan(self.tramos, self.info.duracion, ajustes, self.frecuencia, self.canales, ganancia)

    # ------------------------------------------------------------ datos
    @property
    def bytes_por_muestra(self) -> int:
        """Bytes de una muestra con todos sus canales (lo que QAudioFormat llama bytesPerFrame)."""
        return self.canales * np.dtype(self.FORMATOS[self.formato]).itemsize

    @property
    def duracion_resultado(self) -> float:
        return self._mezcla.total / self.frecuencia

    @property
    def posicion_resultado(self) -> float:
        """Segundos del resultado de la próxima muestra que se va a entregar."""
        return self._mezcla.pos / self.frecuencia

    @property
    def posicion(self) -> float:
        """Instante del tiempo original de la próxima muestra (para mover el cursor del video)."""
        return self._mezcla.plan.original_de(self._mezcla.pos) / self.frecuencia

    @property
    def terminado(self) -> bool:
        return self._mezcla.pos >= self._mezcla.total

    def original_de_resultado(self, t: float) -> float:
        """Instante del original que suena en el segundo ``t`` del resultado.

        Para mover el cursor con lo que de verdad ya sonó: por ejemplo, con el
        segundo del resultado donde empezó a sonar más ``QAudioSink.processedUSecs()``.
        """
        plan = self._mezcla.plan
        return plan.original_de(min(plan.total, max(0, round(float(t) * self.frecuencia)))) / self.frecuencia

    def resultado_de_original(self, t: float) -> float:
        """Segundo del resultado donde suena el instante ``t`` del original (si está borrado, el siguiente tramo)."""
        return self._mezcla.plan.resultado_de(round(max(0.0, float(t)) * self.frecuencia)) / self.frecuencia

    # ------------------------------------------------------------ control
    def ir_a(self, t: float) -> None:
        """Salta al instante ``t`` del tiempo original (si está borrado, al tramo siguiente)."""
        with self._candado:
            muestra = round(max(0.0, float(t)) * self.frecuencia)
            self._mezcla.pos = self._mezcla.plan.resultado_de(muestra)

    def ir_a_resultado(self, t: float) -> None:
        """Salta al segundo ``t`` del resultado."""
        with self._candado:
            self._mezcla.pos = min(self._mezcla.total, max(0, round(float(t) * self.frecuencia)))

    def cambiar_ajustes(self, ajustes: AjustesAudio, pico: Optional[float] = None) -> None:
        """Cambia los ajustes sin moverse de lugar (por ejemplo, al mover el volumen mientras suena)."""
        plan = self._plan(ajustes, pico)
        with self._candado:
            self._mezcla.plan = plan

    def leer_array(self, muestras: int) -> np.ndarray:
        """Hasta ``muestras`` muestras como float32 (n × canales); vacío al terminar."""
        with self._candado:
            return np.ascontiguousarray(self._mezcla.leer(muestras).T)

    def leer(self, muestras: int) -> bytes:
        """Hasta ``muestras`` muestras en el formato del lector, intercaladas; b"" al terminar."""
        datos = self.leer_array(muestras)
        if self.formato == "s16":
            datos = _a_int16(datos)
        return datos.astype("<" + np.dtype(self.FORMATOS[self.formato]).str[1:], copy=False).tobytes()

    def cerrar(self) -> None:
        with self._candado:
            self._mezcla.cerrar()

    def __enter__(self) -> "LectorPCM":
        return self

    def __exit__(self, *_exc) -> None:
        self.cerrar()


# ---------------------------------------------------------------------------
# Exportar solo el audio
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FormatoAudio:
    nombre: str        # "m4a", "wav" o "mp3"
    extension: str     # ".m4a"
    descripcion: str   # para el diálogo de guardar
    codec: str         # codificador de FFmpeg
    contenedor: str    # formato de salida de FFmpeg
    muestra: str       # formato de muestra que recibe el codificador


FORMATOS_AUDIO: dict[str, FormatoAudio] = {
    "m4a": FormatoAudio("m4a", ".m4a", "M4A (AAC)", "aac", "ipod", "fltp"),
    "wav": FormatoAudio("wav", ".wav", "WAV (sin compresión)", "pcm_s16le", "wav", "s16"),
    "mp3": FormatoAudio("mp3", ".mp3", "MP3", "libmp3lame", "mp3", "fltp"),
}


@lru_cache(maxsize=1)
def _disponibles() -> tuple[str, ...]:
    av = _video().av
    nombres = []
    for nombre, f in FORMATOS_AUDIO.items():
        try:
            cc = av.CodecContext.create(f.codec, "w")
            cc.sample_rate = 48000
            cc.layout = "stereo"
            cc.format = f.muestra
            if nombre != "wav":
                cc.bit_rate = 192_000
            cc.open()
            nombres.append(nombre)
        except Exception:
            continue
    return tuple(nombres)


def formatos_audio_disponibles() -> list[FormatoAudio]:
    """Los formatos que este PyAV puede escribir, en orden de preferencia (MP3 solo si trae libmp3lame)."""
    return [FORMATOS_AUDIO[n] for n in _disponibles()]


def ruta_salida_audio(original: Union[str, os.PathLike], formato: str = "m4a") -> Path:
    """``nombre_celular.m4a`` (o .wav, .mp3) junto al video, sin pisar nada que ya exista."""
    from .imagen_io import ruta_salida_sugerida
    return ruta_salida_sugerida(original, FORMATOS_AUDIO[formato].extension)


@dataclass(frozen=True)
class ResultadoAudio:
    ruta: Path
    formato: str
    duracion: float    # segundos del archivo escrito
    frecuencia: int
    canales: int
    segundos: float    # lo que tardó


def _frecuencia_para(codec: str, frecuencia: int) -> int:
    """La del original si el códec la admite; si no, 48 kHz."""
    av = _video().av
    try:
        admitidas = av.Codec(codec, "w").audio_rates
    except Exception:
        admitidas = None
    return frecuencia if not admitidas or frecuencia in admitidas else 48000


def _cuadro_audio(datos: np.ndarray, formato: str, layout: str, frecuencia: int, pts: int):
    """Bloque float32 (canales × n) -> ``av.AudioFrame`` en el formato del codificador."""
    av = _video().av
    if formato == "s16":
        entero = _a_int16(datos)
        cuadro = av.AudioFrame.from_ndarray(np.ascontiguousarray(entero.T).reshape(1, -1), format="s16",
                                            layout=layout)
    else:
        cuadro = av.AudioFrame.from_ndarray(np.ascontiguousarray(datos, dtype=np.float32), format="fltp",
                                            layout=layout)
    cuadro.sample_rate = frecuencia
    cuadro.pts = pts
    cuadro.time_base = Fraction(1, frecuencia)
    return cuadro


def exportar_audio(
    ruta_entrada: Union[str, os.PathLike],
    ruta_salida: Union[str, os.PathLike],
    tramos: Tramos = None,
    ajustes: Optional[AjustesAudio] = None,
    formato: Optional[str] = None,
    progreso: Optional[Progreso] = None,
    cancelado: Optional[Callable[[], bool]] = None,
    pico: Optional[float] = None,
) -> ResultadoAudio:
    """Guarda solo el audio de lo que se conserva, con los ajustes.

    tramos      [(inicio, fin)] en segundos que se CONSERVAN (tiempo original); None = todo.
    formato     "m4a", "wav" o "mp3" (``formatos_audio_disponibles``); None = según la extensión.
    progreso    progreso(hechas, total, segundos_restantes o None), en muestras del resultado.
    cancelado   cancelado() -> True para abandonar: se lanza ``Cancelado`` y no queda archivo.
    pico        el de ``medir_pico`` si se normaliza (si falta, se mide antes).

    M4A: AAC a 192 kbit/s en estéreo y 128 en mono. MP3: 192 o 128 kbit/s. WAV:
    PCM de 16 bits. Frecuencia y canales, los del original (más de dos canales
    se mezclan a estéreo). Se escribe a un temporal en la misma carpeta y se
    renombra al final; el original nunca se toca.
    """
    mv = _video()
    inicio_reloj = time.perf_counter()
    entrada, salida = Path(ruta_entrada), Path(ruta_salida)
    if not entrada.is_file():
        raise FileNotFoundError(f"No existe el video: {entrada}")
    if mv._misma_ruta(entrada, salida):
        raise ValueError("Ese es el video original. Para no sobrescribirlo, elegí otro nombre.")
    nombre = (formato or salida.suffix.lstrip(".")).lower()
    if nombre not in FORMATOS_AUDIO:
        raise ValueError(f"Formato de audio desconocido: {nombre!r}. Usá M4A, WAV o MP3.")
    if nombre not in _disponibles():
        raise ValueError(f"Esta instalación no puede guardar {FORMATOS_AUDIO[nombre].descripcion}.")
    fmt = FORMATOS_AUDIO[nombre]
    ajustes = ajustes or AjustesAudio()
    if ajustes.quitar:
        raise ValueError("El sonido está quitado: no hay audio para guardar.")
    info, tramos_ok = _tramos_y_info(entrada, tramos)
    if not info.tiene_audio:
        raise ValueError("El video no tiene sonido.")
    if not tramos_ok:
        raise ValueError("No queda ningún tramo para exportar: están todos borrados.")
    frecuencia, canales = _formato_natural(info)
    frecuencia = _frecuencia_para(fmt.codec, frecuencia)
    cancelado = cancelado or (lambda: False)

    salida.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(prefix=f".{salida.stem}.", suffix=".parcial" + fmt.extension,
                                    dir=str(salida.parent))
    os.close(fd)
    try:
        if ajustes.normalizar and pico is None:
            pico = medir_pico(entrada, tramos_ok, ajustes.silencios, cancelado)
        mezcla = preparar_mezcla(entrada, tramos_ok, ajustes, frecuencia, canales, pico, cancelado)
        try:
            escritas = _codificar(mezcla, temporal, fmt, frecuencia, canales, progreso, cancelado)
        finally:
            mezcla.cerrar()
        if cancelado():
            raise Cancelado()
        os.replace(temporal, salida)
    except BaseException:
        try:
            os.remove(temporal)
        except OSError:
            pass
        raise
    return ResultadoAudio(salida, nombre, escritas / frecuencia, frecuencia, canales,
                          time.perf_counter() - inicio_reloj)


def _codificar(mezcla: _Mezcla, temporal: str, fmt: FormatoAudio, frecuencia: int, canales: int,
               progreso: Optional[Progreso], cancelado: Callable[[], bool]) -> int:
    av = _video().av
    layout = "mono" if canales == 1 else "stereo"
    opciones = {"movflags": "+faststart"} if fmt.contenedor == "ipod" else {}
    destino = av.open(temporal, "w", format=fmt.contenedor, container_options=opciones)
    try:
        stream = destino.add_stream(fmt.codec, rate=frecuencia)
        stream.layout = layout
        stream.codec_context.format = fmt.muestra
        if fmt.nombre != "wav":
            stream.bit_rate = 192_000 if canales == 2 else 128_000
        if fmt.codec == "aac":
            # Sin "intensity stereo" ni PNS: a 192 kbit/s no ahorran nada y, en un golpe fuerte, el AAC de
            # FFmpeg se pasaba hasta +2,6 dB de 0 dBFS (medido en el modo Audio).
            stream.codec_context.options = {"aac_is": "0", "aac_pns": "0"}
        # AAC y MP3 piden cuadros de un tamaño fijo (el último puede ser más corto).
        tamano = {"aac": 1024, "libmp3lame": 1152}.get(fmt.codec, 4096)
        total = mezcla.total
        escritas, pendiente = 0, np.zeros((canales, 0), np.float32)
        t0 = time.perf_counter()
        while True:
            if cancelado():
                raise Cancelado()
            bloque = mezcla.leer(_BLOQUE)
            final = not bloque.shape[1]
            pendiente = np.concatenate((pendiente, bloque), axis=1) if pendiente.shape[1] else bloque
            usar = pendiente.shape[1] if final else pendiente.shape[1] - pendiente.shape[1] % tamano
            for pos in range(0, usar, tamano):
                trozo = pendiente[:, pos:min(pos + tamano, usar)]
                for paquete in stream.encode(_cuadro_audio(trozo, fmt.muestra, layout, frecuencia, escritas)):
                    destino.mux(paquete)
                escritas += trozo.shape[1]
            pendiente = pendiente[:, usar:]
            if progreso is not None and total:
                hechas = min(escritas, total)
                pasado = time.perf_counter() - t0
                restante = pasado * (total - hechas) / hechas if hechas and pasado > 0.05 else None
                progreso(hechas, total, restante)
            if final:
                break
        for paquete in stream.encode(None):
            destino.mux(paquete)
        destino.close()
        destino = None
        return escritas
    finally:
        if destino is not None:
            try:
                destino.close()
            except Exception:
                pass


__all__ = [
    "OBJETIVO_NORMALIZAR_DB", "GANANCIA_MAX_NORMALIZAR", "VOLUMEN_MAX", "FUNDIDO_CORTE", "FRECUENCIA_PCM",
    "CANALES_PCM", "FPS_SOLO_AUDIO", "AjustesAudio", "info_medio", "medir_pico", "FormaOnda", "forma_de_onda",
    "LectorPCM", "FormatoAudio", "FORMATOS_AUDIO", "formatos_audio_disponibles", "ruta_salida_audio",
    "ResultadoAudio", "exportar_audio",
]
