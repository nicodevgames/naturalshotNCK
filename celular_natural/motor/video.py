"""Video: abrir, recorrer y exportar con el mismo filtro que las fotos.

Usa PyAV (FFmpeg) para leer y escribir. No depende de la interfaz gráfica.

Lectura
-------
* ``info_video``: duración, fps, tamaño tal como se ve (con la rotación de los
  videos de celular ya aplicada), cantidad aproximada de cuadros, códec y audio.
* ``cuadro_en``: el cuadro que se ve en un instante, en RGB. Busca el keyframe
  anterior y decodifica hasta el tiempo pedido; si el pedido es un poco más
  adelante del último (reproducir o avanzar cuadro a cuadro) sigue decodificando
  sin volver a buscar. Los cuadros ya pedidos quedan en caché.
* ``miniaturas``: tira de cuadros chicos para la línea de tiempo (solo keyframes).

Exportación
-----------
``exportar_video`` decodifica, aplica la pila de capas a cada cuadro y codifica
en MP4 H.264 (yuv420p, BT.709) con el audio de los tramos conservados en AAC.
El audio lo arma ``motor/audio.py`` (con los ``AjustesAudio``: quitar, volumen,
normalizar, fundidos y silencios) y se codifica a la par del video. Con
``audio_externo`` (``AudioExterno``) el sonido sale de otro archivo: alineado con
el original (el modo Audio, con los mismos cortes) o desde el 0 del resultado
(voz en off; ``LectorDesdeCero``). Ver la sección "Sonido de otro archivo".

* **Ruido y grano cambian en cada cuadro**, como el ruido real de un sensor: si
  quedaran fijos se vería una textura "pegada" a la pantalla. El resto del
  filtro es idéntico en todos los cuadros (sin parpadeo). Por eso cada capa se
  aplica en dos pasos: primero todo menos ruido y grano, con la semilla fija
  (así la variación de balance, la nitidez variable y la piel real quedan
  quietas), y después solo el ruido y el grano con la semilla ``semilla +
  número de cuadro``. El resultado del cuadro 0 es exactamente el de una foto.
* Varios cuadros se procesan en paralelo con hilos (NumPy y OpenCV sueltan el
  GIL) y se escriben en orden.
* Los tiempos se conservan: cada cuadro y cada muestra de audio se corren lo
  mismo (lo borrado antes de ellos), así el audio sigue sincronizado aunque el
  video sea de cuadros por segundo variables, como los de celular.
* Se escribe a un archivo temporal en la misma carpeta y se renombra al final:
  nunca queda un archivo a medias. El original nunca se toca.
* **Mejorar calidad** (``mejora``, ``motor/mejora_video.py``, sin IA): va antes
  del filtro, ya a la resolución de salida (decodificar → mejorar → filtro →
  codificar). Con la mejora prendida, 720p y 1080p también agrandan un video
  más chico (``tamano_salida(..., agrandar=True)``). Cada cuadro usa de vecinos
  los dos de antes y los dos de después **de su mismo tramo conservado**
  (``VentanaVecinos``, la misma ventana de ``MejoradorVideo`` con su
  ``reiniciar`` en cada tramo): nunca cruzan un borrado. Cada cuadro mejorado
  pasa al filtro, que sigue en paralelo. La mejora empieza de a un cuadro y,
  si con los primeros cuadros resulta ser lo lento (filtro liviano o sin
  filtro), pasa a ``HILOS_MEJORA`` (3) a la vez. Medido con el video de prueba
  de 10 s a 1080p: sin filtro, 32 s de a tres contra 49 de a uno; con el filtro
  de la app, 158 s de a uno contra 183 de a tres (ahí repartirla le saca CPU
  al filtro). Se escriben en orden y con las mismas marcas de tiempo: el audio
  sigue sincronizado.

Rendimiento (esta PC, 16 hilos, preset principal, exportación completa con
audio): ≈ 2,8 cuadros/s a 1080p y ≈ 6 a 720p (pico de memoria ≈ 1,1 GB y
0,6 GB). El filtro es el mismo que el de las fotos y domina el tiempo:
decodificar y codificar cuestan unos pocos milisegundos por cuadro. Con
procesos en vez de hilos no rinde más: el límite es el acceso a memoria.
"""

from __future__ import annotations

import math
import os
import struct
import tempfile
import threading
import time
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional, Sequence, Union

import numpy as np

from .imagen_io import EXTENSIONES_VIDEO, ruta_salida_sugerida
from .mascaras import REGIONES
from .mejora_video import RADIO_VECINOS, AjustesMejora, mejorar_cuadro, tamano_mejorado
from .mejora_video import vaciar_memoria as vaciar_memoria_mejora
from .parametros import SECCIONES
from .procesado import NEUTRO, Ajustes, Cancelado, _finalizar, procesar_flotante

if TYPE_CHECKING:  # solo para las anotaciones: audio.py importa este módulo
    from .audio import AjustesAudio

try:  # PyAV es opcional para el resto de la app: sin él solo falla el video.
    import av
    from av.video.reformatter import Interpolation as _Interp
except ImportError as _error:  # pragma: no cover - depende de la instalación
    av = None
    _ERROR_AV: Optional[ImportError] = _error
else:
    _ERROR_AV = None

# EXTENSIONES_VIDEO (".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm") viene de imagen_io: así la
# interfaz reconoce los videos sin importar PyAV.
# Resolución de salida: lado corto en píxeles (None = la del original). Nunca se agranda, salvo con
# "Mejorar calidad" prendida (``tamano_salida(..., agrandar=True)``).
RESOLUCIONES: dict[str, Optional[int]] = {"Original": None, "1080p": 1080, "720p": 720}
# Calidad: CRF de x264 (más bajo = mejor calidad y archivo más pesado) y "tune".
# x264 borra buena parte del ruido que cambia en cada cuadro (a CRF 18 queda un
# 30-40 %); con tune=grain conserva un 45-55 %, a cambio de ~1,6× de tamaño.
CALIDADES: dict[str, tuple[int, Optional[str]]] = {
    "Alta": (17, "grain"),
    "Normal": (20, "grain"),
    "Liviana": (24, None),
}
# Preferencia de codificadores H.264. libx264 viene en las ruedas de PyAV.
CODIFICADORES_H264 = ("libx264", "h264_mf", "libopenh264", "mpeg4")
# NS-101.2: codificadores de la placa de video (NVIDIA, Intel, AMD; Apple en Mac), solo si se pide "Usar la placa de
# video". Van por tasa de bits (como h264_mf): más rápidos, pero sin el ajuste para grano de x264, así
# que conservan algo menos del ruido del filtro. Si fallan a mitad de la exportación, se vuelve a x264.
CODIFICADORES_GPU = ("h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox")  # el último es el de Mac
_FORMATO_PIXEL = {"h264_mf": "nv12", "h264_qsv": "nv12"}
MUESTRAS_AAC = 1024  # muestras por cuadro de AAC-LC
_FRECUENCIAS_AAC = (8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000, 64000, 88200, 96000)
_LIMITE_CACHE = 160 * 1024 * 1024  # bytes de cuadros guardados para recorrer la línea de tiempo
# "Mejorar calidad" al exportar. Ver las mediciones en VIDEO.md (sección "Mejorar calidad"):
# * se empieza mejorando de a un cuadro; si con los primeros CUADROS_PARA_DECIDIR resulta que la mejora es
#   lo lento (el filtro es liviano o no hay filtro), se pasa a HILOS_MEJORA cuadros a la vez;
# * EN_VUELO_MEJORA cuadros más esperan su turno ya decodificados.
HILOS_MEJORA = 3
EN_VUELO_MEJORA = 2
CUADROS_PARA_DECIDIR = 3
ACELERACION_FILTRO = 2.2  # cuánto más rinde el filtro en sus hilos que un cuadro solo (medido: 2,1 a 2,6)

Resolucion = Union[None, str, int]
Progreso = Callable[[int, int, Optional[float]], None]


def _verificar_av() -> None:
    if av is None:
        raise RuntimeError("Falta PyAV para trabajar con video. Instalalo con: pip install av==19.0.1") from _ERROR_AV


def _flags(escalar: bool = False):
    """Conversión YUV <-> RGB precisa: con estos flags el color va y vuelve con ±1 nivel."""
    base = _Interp.AREA if escalar else _Interp.BILINEAR
    return base | _Interp.ACCURATE_RND | _Interp.FULL_CHR_H_INT | _Interp.FULL_CHR_H_INP


# ---------------------------------------------------------------------------
# Información
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InfoVideo:
    ruta: str
    duracion: float          # segundos
    fps: float
    ancho: int               # tal como se ve (con la rotación aplicada)
    alto: int
    cuadros: int             # aproximada
    codec: str
    tiene_audio: bool
    rotacion: int = 0        # grados antihorarios a girar el cuadro decodificado: 0, 90, 180 o 270
    tasa: Fraction = Fraction(30)  # fps exacto (por ejemplo 30000/1001)
    inicio: float = 0.0      # tiempo del primer cuadro en el archivo: el origen de todos los tiempos
    codec_audio: str = ""
    frecuencia_audio: int = 0
    canales_audio: int = 0
    hdr: bool = False        # HLG o PQ: se pasa a SDR sin mapeo de tonos

    @property
    def duracion_cuadro(self) -> float:
        return 1.0 / self.fps


def _clave_archivo(ruta: Union[str, os.PathLike]) -> tuple:
    p = Path(ruta).resolve()
    st = p.stat()
    return (os.path.normcase(str(p)), st.st_mtime_ns, st.st_size)


def _rotacion_de_matriz(datos: bytes) -> Optional[float]:
    """Ángulo antihorario de una matriz de visualización de FFmpeg (como ``av_display_rotation_get``)."""
    if not datos or len(datos) < 36:
        return None
    m = struct.unpack("<9i", datos[:36])
    a, b, c, d = (v / 65536.0 for v in (m[0], m[1], m[3], m[4]))
    escala0, escala1 = math.hypot(a, c), math.hypot(b, d)
    if escala0 == 0 or escala1 == 0:
        return None
    return -math.degrees(math.atan2(b / escala1, a / escala0))


def _normalizar_rotacion(grados: Optional[float]) -> Optional[int]:
    if grados is None or not math.isfinite(grados):
        return None
    return int(round(grados / 90.0)) % 4 * 90


def _rotacion_stream(vs) -> Optional[int]:
    """Rotación declarada por el stream: matriz de visualización o, en archivos viejos, el tag ``rotate``."""
    try:
        datos = vs.codec_context.coded_side_data
        matriz = datos.get("display_matrix") if isinstance(datos, dict) else None
        if matriz:
            return _normalizar_rotacion(_rotacion_de_matriz(bytes(matriz)))
    except Exception:
        pass
    rotate = (vs.metadata or {}).get("rotate")
    if rotate:
        try:  # el tag es en sentido horario
            return _normalizar_rotacion(-float(rotate))
        except ValueError:
            return None
    return None


def _primer_cuadro(contenedor, vs, max_paquetes: int = 400):
    n = 0
    for paquete in contenedor.demux(vs):
        for cuadro in paquete.decode():
            return cuadro
        n += 1
        if n >= max_paquetes:
            break
    return None


def _tiempo_cuadro(cuadro) -> Optional[float]:
    if cuadro.pts is not None and cuadro.time_base is not None:
        return float(cuadro.pts * cuadro.time_base)
    if cuadro.dts is not None and cuadro.time_base is not None:
        return float(cuadro.dts * cuadro.time_base)
    return None


_CACHE_INFO: dict[tuple, InfoVideo] = {}
_CANDADO_INFO = threading.Lock()


def info_video(ruta: Union[str, os.PathLike]) -> InfoVideo:
    """Datos del video. Se cachean por archivo (ruta, fecha y tamaño)."""
    _verificar_av()
    clave = _clave_archivo(ruta)
    with _CANDADO_INFO:
        guardada = _CACHE_INFO.get(clave)
    if guardada is not None:
        return guardada
    with av.open(str(ruta)) as c:
        if not c.streams.video:
            raise ValueError("El archivo no tiene una pista de video.")
        vs = c.streams.video[0]
        tb = vs.time_base
        tasa = vs.average_rate or vs.guessed_rate or vs.base_rate or Fraction(30)
        if not (0 < tasa <= 1000):
            tasa = Fraction(30)
        fps = float(tasa)
        if vs.duration is not None and tb is not None:
            duracion = float(vs.duration * tb)
        elif c.duration is not None:
            duracion = c.duration / 1_000_000
        else:
            duracion = 0.0
        hdr = getattr(vs.codec_context, "color_trc", 0) in (16, 18)
        rotacion = _rotacion_stream(vs)
        inicio_stream = float(vs.start_time * tb) if vs.start_time is not None and tb is not None else None
        primero = _primer_cuadro(c, vs)
        if primero is not None:
            ancho_c, alto_c = primero.width, primero.height
            if rotacion is None:
                rotacion = _normalizar_rotacion(primero.rotation)
            t0 = _tiempo_cuadro(primero)
            inicio = t0 if t0 is not None else (inicio_stream or 0.0)
            hdr = hdr or primero.color_trc in (16, 18)
        else:
            ancho_c, alto_c = vs.codec_context.width, vs.codec_context.height
            inicio = inicio_stream or 0.0
        if inicio_stream is not None and inicio > inicio_stream:
            duracion = max(0.0, duracion - (inicio - inicio_stream))
        rotacion = rotacion or 0
        ancho, alto = (alto_c, ancho_c) if rotacion in (90, 270) else (ancho_c, alto_c)
        cuadros = int(vs.frames or 0) or int(round(duracion * fps))
        if duracion <= 0 and cuadros:
            duracion = cuadros / fps
        codec_audio, frecuencia, canales = "", 0, 0
        if c.streams.audio:
            ca = c.streams.audio[0].codec_context
            codec_audio = ca.name or ""
            frecuencia = int(ca.sample_rate or 0)
            canales = int(getattr(ca, "channels", 0) or (ca.layout.nb_channels if ca.layout else 0))
        info = InfoVideo(
            ruta=str(ruta), duracion=duracion, fps=fps, ancho=int(ancho), alto=int(alto), cuadros=cuadros,
            codec=vs.codec_context.name or "", tiene_audio=bool(c.streams.audio), rotacion=rotacion,
            tasa=Fraction(tasa), inicio=inicio, codec_audio=codec_audio, frecuencia_audio=frecuencia,
            canales_audio=canales, hdr=bool(hdr),
        )
    with _CANDADO_INFO:
        _CACHE_INFO[clave] = info
    return info


def _tolerancia(fps: float) -> float:
    """Margen al comparar tiempos: absorbe marcas redondeadas al milisegundo (MKV, WebM)."""
    return min(0.25 / fps, 1e-3)


def indice_en(segundos: float, fps: float) -> int:
    """Número del cuadro que se ve en ``segundos`` (el último que empezó)."""
    return max(0, int(math.floor((segundos + _tolerancia(fps)) * fps)))


def tiempo_de(indice: int, fps: float) -> float:
    return indice / fps


# ---------------------------------------------------------------------------
# Conversión de cuadros
# ---------------------------------------------------------------------------

def _espacio_color(cuadro) -> tuple[str, str]:
    """Matriz y rango de un cuadro YUV. Sin dato: BT.709 en HD y BT.601 en SD, como los reproductores."""
    cs = cuadro.colorspace
    if cs == 1:
        matriz = "ITU709"
    elif cs in (5, 6):
        matriz = "ITU601"
    elif cs in (9, 10):
        matriz = "BT2020"
    elif cs == 7:
        matriz = "SMPTE240M"
    else:
        matriz = "ITU709" if min(cuadro.width, cuadro.height) >= 720 else "ITU601"
    nombre = cuadro.format.name if cuadro.format is not None else ""
    rango = "JPEG" if cuadro.color_range == 2 or nombre.startswith("yuvj") else "MPEG"
    return matriz, rango


def _a_rgb(cuadro, rotacion: int, ancho: Optional[int] = None, alto: Optional[int] = None) -> np.ndarray:
    """Cuadro decodificado -> RGB uint8 derecho (rotación aplicada), opcionalmente reducido.

    ``ancho`` y ``alto`` son los de la imagen tal como se ve.
    """
    girado = rotacion in (90, 270)
    if ancho is None or alto is None:
        w, h = cuadro.width, cuadro.height
    else:
        w, h = (alto, ancho) if girado else (ancho, alto)
    escalar = (w, h) != (cuadro.width, cuadro.height)
    nombre = cuadro.format.name if cuadro.format is not None else ""
    if nombre.startswith(("rgb", "bgr", "gbr")):
        rgb = cuadro.to_ndarray(width=w, height=h, format="rgb24", interpolation=_flags(escalar))
    else:
        matriz, rango = _espacio_color(cuadro)
        rgb = cuadro.to_ndarray(width=w, height=h, format="rgb24", src_colorspace=matriz,
                                src_color_range=rango, interpolation=_flags(escalar))
    if rotacion:
        rgb = np.rot90(rgb, k=rotacion // 90)
    return np.ascontiguousarray(rgb)


def _tamano_reducido(ancho: int, alto: int, lado_max: Optional[int]) -> tuple[int, int]:
    if not lado_max or max(ancho, alto) <= lado_max:
        return ancho, alto
    f = lado_max / max(ancho, alto)
    return max(2, round(ancho * f)), max(2, round(alto * f))


# ---------------------------------------------------------------------------
# Lectura cuadro a cuadro
# ---------------------------------------------------------------------------

class LectorVideo:
    """Lector con el archivo abierto para pedir cuadros por tiempo.

    Si el pedido está un poco más adelante que el último cuadro (reproducción o
    cuadro a cuadro) sigue decodificando; si no, busca el keyframe anterior.
    Se puede usar desde varios hilos (un pedido a la vez).
    """

    SALTO_MAX = 2.5  # segundos: más adelante que esto conviene buscar

    def __init__(self, ruta: Union[str, os.PathLike]):
        _verificar_av()
        self.ruta = str(ruta)
        self.info = info_video(ruta)
        self._contenedor = av.open(self.ruta)
        self._vs = self._contenedor.streams.video[0]
        # Hilos por porciones: con hilos por cuadro, después de cada búsqueda el decodificador
        # tiene que llenar su cola. Medido (búsquedas al azar): 1080p H.264 a 25 Mbps, 39 ms
        # contra 114; 4K HEVC, 90 contra 340. Para exportar (lectura seguida) se usa AUTO.
        self._vs.thread_type = "SLICE"
        self._tb = self._vs.time_base
        self._paquetes = None
        self._pendientes: deque = deque()
        self._actual = None
        self._t_actual = 0.0
        self._ultimo_t: Optional[float] = None
        self._candado = threading.Lock()

    def cerrar(self) -> None:
        with self._candado:
            try:
                self._contenedor.close()
            except Exception:
                pass

    def _tiempo(self, cuadro) -> float:
        t = _tiempo_cuadro(cuadro)
        if t is None:  # sin marca de tiempo: el siguiente al anterior
            t = (self._ultimo_t + self.info.duracion_cuadro) if self._ultimo_t is not None else self.info.inicio
        self._ultimo_t = t
        return t - self.info.inicio

    def _siguiente(self):
        while not self._pendientes:
            if self._paquetes is None:
                self._paquetes = self._contenedor.demux(self._vs)
            try:
                paquete = next(self._paquetes)
            except StopIteration:
                return None
            for cuadro in paquete.decode():
                self._pendientes.append((self._tiempo(cuadro), cuadro))
        return self._pendientes.popleft()

    def _buscar(self, t: float) -> None:
        # Un margen de unos cuadros: con cuadros B el keyframe puede mostrarse un poco después de su marca.
        margen = max(0.1, 4.0 * self.info.duracion_cuadro)
        destino = self.info.inicio + max(0.0, t - margen)
        self._contenedor.seek(int(destino / self._tb) if self._tb else int(destino * 1_000_000),
                              stream=self._vs if self._tb else None, backward=True, any_frame=False)
        self._paquetes = self._contenedor.demux(self._vs)
        self._pendientes.clear()
        self._actual = None
        self._ultimo_t = None

    def cuadro_av(self, segundos: float):
        """El cuadro (``av.VideoFrame``) que se ve en ``segundos``, y su tiempo."""
        with self._candado:
            eps = _tolerancia(self.info.fps)
            t = max(0.0, float(segundos))
            if (self._actual is None or t < self._t_actual - eps or t - self._t_actual > self.SALTO_MAX):
                self._buscar(t)
            for intento in range(2):
                while True:
                    siguiente = self._siguiente()
                    if siguiente is None:
                        break
                    ts, cuadro = siguiente
                    if self._actual is not None and ts > t + eps:
                        self._pendientes.appendleft(siguiente)
                        break
                    self._actual, self._t_actual = cuadro, ts
                if self._actual is not None:
                    break
                # Se buscó más allá del final: se vuelve un poco atrás.
                self._buscar(max(0.0, t - 5.0))
            if self._actual is None:
                raise ValueError("No se pudo leer ningún cuadro del video.")
            return self._actual, self._t_actual

    def cuadro(self, segundos: float, lado_max: Optional[int] = None,
               tamano: Optional[tuple[int, int]] = None) -> np.ndarray:
        """RGB derecho del cuadro que se ve en ``segundos``: reducido para que el lado largo no pase
        de ``lado_max`` o, con ``tamano`` (ancho, alto tal como se ve), exactamente a ese tamaño."""
        cuadro, _t = self.cuadro_av(segundos)
        if tamano is not None:
            ancho, alto = tamano
        else:
            ancho, alto = _tamano_reducido(self.info.ancho, self.info.alto, lado_max)
        return _a_rgb(cuadro, self.info.rotacion, ancho, alto)


_LECTORES: "OrderedDict[tuple, LectorVideo]" = OrderedDict()
_CANDADO_LECTORES = threading.Lock()
_CACHE_CUADROS: "OrderedDict[tuple, np.ndarray]" = OrderedDict()
_BYTES_CACHE = 0
_CANDADO_CACHE = threading.Lock()


def _lector(ruta: Union[str, os.PathLike]) -> LectorVideo:
    clave = _clave_archivo(ruta)
    with _CANDADO_LECTORES:
        lector = _LECTORES.get(clave)
        if lector is not None:
            _LECTORES.move_to_end(clave)
            return lector
        lector = LectorVideo(ruta)
        _LECTORES[clave] = lector
        while len(_LECTORES) > 2:
            _clave, viejo = _LECTORES.popitem(last=False)
            viejo.cerrar()
        return lector


def cerrar_lectores() -> None:
    """Cierra los archivos abiertos y vacía las cachés (por ejemplo, al cerrar el editor o el video),
    también la de cuadros preparados de "Mejorar calidad"."""
    global _BYTES_CACHE
    with _CANDADO_LECTORES:
        while _LECTORES:
            _clave, lector = _LECTORES.popitem()
            lector.cerrar()
    with _CANDADO_CACHE:
        _CACHE_CUADROS.clear()
        _BYTES_CACHE = 0
    vaciar_memoria_mejora()


def cuadro_en(ruta: Union[str, os.PathLike], segundos: float, lado_max: Optional[int] = None,
              guardar: bool = True, tamano: Optional[tuple[int, int]] = None) -> np.ndarray:
    """Cuadro RGB uint8 (alto × ancho × 3, ya derecho) que se ve en ``segundos``.

    ``lado_max`` reduce el cuadro para la vista previa. ``tamano`` (ancho, alto tal
    como se ve) lo lee exactamente a ese tamaño, con la misma conversión que la
    exportación (``_a_rgb``): la vista previa de "Mejorar calidad" lo usa para leer
    igual que ``exportar_video`` lee a ``tamano_lectura``. Los cuadros pedidos se
    guardan en caché (hasta ~160 MB): volver sobre la línea de tiempo es inmediato.
    ``guardar=False`` no los guarda (al reproducir, para no desalojar los útiles).
    """
    global _BYTES_CACHE
    _verificar_av()
    lector = _lector(ruta)
    info = lector.info
    if tamano is not None:
        tamano = (int(tamano[0]), int(tamano[1]))
        if tamano == (info.ancho, info.alto):
            tamano, lado_max = None, None  # es el original: misma clave que sin reducir
    clave = (_clave_archivo(ruta), indice_en(max(0.0, segundos), info.fps), tamano or lado_max)
    with _CANDADO_CACHE:
        guardado = _CACHE_CUADROS.get(clave)
        if guardado is not None:
            _CACHE_CUADROS.move_to_end(clave)
            return guardado.copy()
    rgb = lector.cuadro(segundos, lado_max, tamano)
    if not guardar:
        return rgb
    with _CANDADO_CACHE:
        if clave not in _CACHE_CUADROS:
            _CACHE_CUADROS[clave] = rgb
            _BYTES_CACHE += rgb.nbytes
            while _BYTES_CACHE > _LIMITE_CACHE and len(_CACHE_CUADROS) > 1:
                _c, viejo = _CACHE_CUADROS.popitem(last=False)
                _BYTES_CACHE -= viejo.nbytes
    return rgb.copy()


_CACHE_MINIATURAS: "OrderedDict[tuple, list]" = OrderedDict()


def _miniaturas_secuenciales(ruta, info: "InfoVideo", tiempos: list[float], ancho: int, alto: int
                             ) -> list[tuple[float, np.ndarray]]:
    """Miniaturas decodificando el video de corrido (más lento, pero sirve sin keyframes)."""
    salida: list[tuple[float, np.ndarray]] = []
    medio_cuadro = 0.5 / max(1.0, float(info.fps or 30.0))
    i = 0
    with av.open(str(ruta)) as c:
        vs = c.streams.video[0]
        vs.thread_type = "AUTO"
        try:
            for cuadro in c.decode(vs):
                t = _tiempo_cuadro(cuadro)
                if t is None:
                    continue
                t -= info.inicio
                if i < len(tiempos) and t >= tiempos[i] - medio_cuadro:
                    rgb = _a_rgb(cuadro, info.rotacion, ancho, alto)
                    while i < len(tiempos) and t >= tiempos[i] - medio_cuadro:
                        salida.append((tiempos[i], rgb))
                        i += 1
                if i >= len(tiempos):
                    break
        except av.error.FFmpegError:
            pass
    if salida:  # los que falten (final cortado) repiten el último
        while len(salida) < len(tiempos):
            salida.append((tiempos[len(salida)], salida[-1][1]))
    return salida


def miniaturas(ruta: Union[str, os.PathLike], n: int, alto: int) -> list[tuple[float, np.ndarray]]:
    """``n`` miniaturas repartidas en todo el video, de ``alto`` píxeles: [(segundos, rgb)].

    Para que sea rápido solo se decodifican keyframes: cada miniatura es el
    keyframe más cercano antes de su tiempo.
    """
    _verificar_av()
    info = info_video(ruta)
    n = max(1, int(n))
    clave = (_clave_archivo(ruta), n, int(alto))
    with _CANDADO_CACHE:
        guardada = _CACHE_MINIATURAS.get(clave)
    if guardada is not None:
        return [(t, a.copy()) for t, a in guardada]
    ancho = max(2, round(info.ancho * alto / max(1, info.alto)))
    salida: list[tuple[float, np.ndarray]] = []
    with av.open(str(ruta)) as c:
        vs = c.streams.video[0]
        vs.thread_type = "SLICE"
        try:
            vs.codec_context.skip_frame = "NONKEY"
        except Exception:
            pass
        tb = vs.time_base
        previo = None
        distintos = set()  # keyframes realmente usados
        for k in range(n):
            t = (k + 0.5) * info.duracion / n
            try:
                c.seek(int((info.inicio + t) / tb), stream=vs, backward=True, any_frame=False)
                cuadro = _primer_cuadro(c, vs, max_paquetes=200)
            except av.error.FFmpegError:
                cuadro = None
            if cuadro is not None:
                previo = _a_rgb(cuadro, info.rotacion, ancho, alto)
                distintos.add(cuadro.pts)
            if previo is not None:
                salida.append((t, previo))
    # Videos con muy pocos keyframes (por ejemplo uno solo al principio): todas las
    # miniaturas saldrían iguales o ninguna. Ahí se recorre el video una vez.
    if n > 1 and len(distintos) < max(2, n // 2) and info.duracion <= 900:
        secuenciales = _miniaturas_secuenciales(ruta, info, [(k + 0.5) * info.duracion / n for k in range(n)],
                                                ancho, alto)
        if secuenciales:
            salida = secuenciales
    with _CANDADO_CACHE:
        _CACHE_MINIATURAS[clave] = salida
        while len(_CACHE_MINIATURAS) > 6:
            _CACHE_MINIATURAS.popitem(last=False)
    return [(t, a.copy()) for t, a in salida]


# ---------------------------------------------------------------------------
# Edición de la línea de tiempo (sin interfaz: se puede probar sola)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Segmento:
    inicio: float
    fin: float
    borrado: bool = False

    @property
    def duracion(self) -> float:
        return self.fin - self.inicio


@dataclass(frozen=True)
class EdicionVideo:
    """Cortes, tramos borrados y entrada/salida. Inmutable: cada edición devuelve
    una nueva, así deshacer y rehacer es guardar la lista de estados.

    Los segmentos cubren todo el video, uno detrás de otro. Se exportan los no
    borrados, recortados a [entrada, salida). Los tiempos van en la grilla de
    cuadros (el cuadro k empieza en k / fps).
    """

    duracion: float
    fps: float
    segmentos: tuple[Segmento, ...]
    entrada: float = 0.0
    salida: Optional[float] = None  # None = hasta el final

    @staticmethod
    def nueva(duracion: float, fps: float) -> "EdicionVideo":
        return EdicionVideo(float(duracion), float(fps), (Segmento(0.0, float(duracion)),))

    @property
    def cuadro(self) -> float:
        return 1.0 / self.fps

    @property
    def fin(self) -> float:
        return self.duracion if self.salida is None else self.salida

    def ajustar(self, t: float) -> float:
        """Lleva ``t`` al comienzo del cuadro más cercano, dentro del video."""
        t = round(max(0.0, min(self.duracion, t)) * self.fps) / self.fps
        return min(t, self.duracion)

    def indice_en(self, t: float) -> int:
        for i, s in enumerate(self.segmentos):
            if t < s.fin - 1e-9:
                return i
        return len(self.segmentos) - 1

    def cortar(self, t: float) -> "EdicionVideo":
        """Divide en ``t`` el segmento que lo contiene. Si cae a menos de un cuadro de un corte, no cambia nada."""
        t = self.ajustar(t)
        i = self.indice_en(t)
        s = self.segmentos[i]
        if t - s.inicio < self.cuadro * 0.5 or s.fin - t < self.cuadro * 0.5:
            return self
        nuevos = self.segmentos[:i] + (replace(s, fin=t), replace(s, inicio=t)) + self.segmentos[i + 1:]
        return replace(self, segmentos=nuevos)

    def con_borrado(self, i: int, borrado: bool = True) -> "EdicionVideo":
        if not 0 <= i < len(self.segmentos) or self.segmentos[i].borrado == borrado:
            return self
        nuevos = list(self.segmentos)
        nuevos[i] = replace(nuevos[i], borrado=borrado)
        return replace(self, segmentos=tuple(nuevos))

    def unir_con_siguiente(self, i: int) -> "EdicionVideo":
        """Quita el corte entre el segmento ``i`` y el siguiente (queda el estado del primero)."""
        if not 0 <= i < len(self.segmentos) - 1:
            return self
        a, b = self.segmentos[i], self.segmentos[i + 1]
        nuevos = self.segmentos[:i] + (replace(a, fin=b.fin),) + self.segmentos[i + 2:]
        return replace(self, segmentos=nuevos)

    def con_entrada(self, t: float) -> "EdicionVideo":
        """El cuadro en ``t`` pasa a ser el primero que se exporta."""
        t = self.ajustar(t)
        t = min(t, self.fin - self.cuadro)
        return replace(self, entrada=max(0.0, t))

    def con_salida(self, t: float) -> "EdicionVideo":
        """El cuadro en ``t`` pasa a ser el último que se exporta (incluido)."""
        t = self.ajustar(t) + self.cuadro
        t = max(t, self.entrada + self.cuadro)
        return replace(self, salida=None if t >= self.duracion - 1e-6 else t)

    def con_limites(self, entrada: float, salida: Optional[float]) -> "EdicionVideo":
        """Fija entrada y salida tal cual (al arrastrar las marcas)."""
        entrada = self.ajustar(entrada)
        salida = None if salida is None else self.ajustar(salida)
        if salida is not None and salida >= self.duracion - 1e-6:
            salida = None
        fin = self.duracion if salida is None else salida
        if fin - entrada < self.cuadro - 1e-9:  # con tolerancia: dejar justo un cuadro vale
            return self
        return replace(self, entrada=entrada, salida=salida)

    def tramos_conservados(self) -> list[tuple[float, float]]:
        """Lo que se exporta: [(inicio, fin)] en orden, con los tramos contiguos unidos."""
        tramos: list[tuple[float, float]] = []
        for s in self.segmentos:
            if s.borrado:
                continue
            a, b = max(s.inicio, self.entrada), min(s.fin, self.fin)
            if b - a < 1e-6:
                continue
            if tramos and abs(tramos[-1][1] - a) < 1e-6:
                tramos[-1] = (tramos[-1][0], b)
            else:
                tramos.append((a, b))
        return tramos

    def duracion_resultante(self) -> float:
        return sum(b - a for a, b in self.tramos_conservados())

    def se_exporta(self, t: float) -> bool:
        return any(a - 1e-6 <= t < b - 1e-6 for a, b in self.tramos_conservados())

    def proximo_visible(self, t: float) -> Optional[float]:
        """Primer instante desde ``t`` que se exporta (para reproducir salteando lo borrado)."""
        for a, b in self.tramos_conservados():
            if t < b - 1e-6:
                return max(t, a)
        return None

    def sin_cambios(self) -> bool:
        return len(self.segmentos) == 1 and not self.segmentos[0].borrado and self.entrada == 0 and self.salida is None


def normalizar_tramos(tramos: Optional[Sequence[tuple[float, float]]], duracion: float) -> list[tuple[float, float]]:
    """Ordena, recorta a [0, duración] y une los tramos que se tocan."""
    if tramos is None:
        return [(0.0, float(duracion))] if duracion > 0 else []
    limpios = sorted((max(0.0, float(a)), min(float(duracion), float(b))) for a, b in tramos)
    salida: list[tuple[float, float]] = []
    for a, b in limpios:
        if b - a < 1e-4:
            continue
        if salida and a <= salida[-1][1] + 1e-6:
            salida[-1] = (salida[-1][0], max(salida[-1][1], b))
        else:
            salida.append((a, b))
    return salida


# ---------------------------------------------------------------------------
# Tiempo del resultado ↔ tiempo original
#
# La línea de tiempo del editor muestra el resultado: los tramos conservados uno
# detrás de otro, sin lo borrado ni lo recortado. La edición sigue en el tiempo
# original (``EdicionVideo``, los silencios de ``AjustesAudio``); estas piezas
# convierten de un tiempo al otro. Son puras: no leen el archivo.
# ---------------------------------------------------------------------------

EPS_TIEMPO = 1e-9  # segundos: absorbe el error de redondeo al comparar con los bordes de los tramos


@dataclass(frozen=True)
class Hueco:
    """Lo que no se ve en una unión de la línea de tiempo: lo borrado o recortado entre dos
    tramos conservados, antes del primero o después del último.

    inicio, fin  el rango que falta, en segundos del tiempo ORIGINAL.
    en           dónde queda la unión, en segundos del resultado.
    principio    si es lo de antes del primer tramo (la entrada o lo borrado al principio).
    final        si es lo de después del último (la salida o lo borrado al final).
    """

    inicio: float
    fin: float
    en: float
    principio: bool = False
    final: bool = False

    @property
    def duracion(self) -> float:
        return self.fin - self.inicio


@dataclass(frozen=True)
class MapaTiempo:
    """Convierte entre el tiempo original y el del resultado.

    El resultado son los ``tramos`` (tiempo original, en orden y sin pisarse, como los
    de ``EdicionVideo.tramos_conservados``) puestos uno detrás de otro.

    * ``a_resultado(t)``: un instante del original que no está en el resultado (borrado
      o recortado) va a la unión, o sea, a donde empieza lo que sigue.
    * ``a_original(r)``: justo en una unión da el comienzo del tramo que sigue; desde el
      final del resultado, el final del último tramo.

    Las dos aceptan un número o un arreglo de NumPy (para convertir muchas columnas de una
    vez). Inmutable y comparable: sirve de clave de caché.
    """

    tramos: tuple[tuple[float, float], ...]
    duracion_original: float

    def __post_init__(self):
        tramos = tuple((float(a), float(b)) for a, b in self.tramos if float(b) - float(a) > EPS_TIEMPO)
        object.__setattr__(self, "tramos", tramos)
        object.__setattr__(self, "duracion_original", max(0.0, float(self.duracion_original)))
        inicios = np.array([a for a, _ in tramos], dtype=np.float64)
        fines = np.array([b for _, b in tramos], dtype=np.float64)
        largos = fines - inicios
        acumulado = np.concatenate([[0.0], np.cumsum(largos)])
        # Arreglos de trabajo (no son campos: no cuentan al comparar ni en la clave).
        object.__setattr__(self, "_inicios", inicios)
        object.__setattr__(self, "_fines", fines)
        object.__setattr__(self, "_r0", acumulado[:-1])   # dónde empieza cada tramo en el resultado
        object.__setattr__(self, "_r1", acumulado[1:])    # dónde termina
        object.__setattr__(self, "_total", float(acumulado[-1]))

    @staticmethod
    def de_edicion(edicion: "EdicionVideo") -> "MapaTiempo":
        return MapaTiempo(tuple(edicion.tramos_conservados()), edicion.duracion)

    @staticmethod
    def identidad(duracion: float) -> "MapaTiempo":
        """Todo el original, sin cortes: los dos tiempos son el mismo."""
        return MapaTiempo(((0.0, float(duracion)),), duracion)

    @property
    def duracion(self) -> float:
        """Duración del resultado (la suma de los tramos)."""
        return self._total

    @property
    def inicios_resultado(self) -> tuple[float, ...]:
        """Dónde empieza cada tramo en el resultado."""
        return tuple(float(r) for r in self._r0)

    def a_resultado(self, t):
        """Segundo del resultado donde cae el instante ``t`` del original (ver la clase)."""
        valores = np.asarray(t, dtype=np.float64)
        n = len(self.tramos)
        if n == 0:
            salida = np.zeros_like(valores)
        else:
            i = np.searchsorted(self._fines - EPS_TIEMPO, valores, side="right")  # primer tramo con t < fin
            j = np.minimum(i, n - 1)
            salida = np.where(i < n, self._r0[j] + np.maximum(0.0, valores - self._inicios[j]), self._total)
        return float(salida) if np.ndim(salida) == 0 else salida

    def a_original(self, r):
        """Instante del original que se ve en el segundo ``r`` del resultado (ver la clase)."""
        valores = np.asarray(r, dtype=np.float64)
        n = len(self.tramos)
        if n == 0:
            salida = np.zeros_like(valores)
        else:
            i = np.searchsorted(self._r1 - EPS_TIEMPO, valores, side="right")  # primer tramo con r < su final
            j = np.minimum(i, n - 1)
            salida = np.where(i < n, self._inicios[j] + np.maximum(0.0, valores - self._r0[j]), self._fines[-1])
        return float(salida) if np.ndim(salida) == 0 else salida

    def visible(self, t: float) -> bool:
        """Si el instante ``t`` del original está en el resultado."""
        i = int(np.searchsorted(self._fines - EPS_TIEMPO, float(t), side="right"))
        return i < len(self.tramos) and float(t) >= self._inicios[i] - EPS_TIEMPO

    def rangos_resultado(self, inicio: float, fin: float) -> list[tuple[float, float]]:
        """Las partes de [inicio, fin) del original que están en el resultado, en segundos del
        resultado y en orden (una por tramo que tocan)."""
        salida = []
        for (a, b), r0 in zip(self.tramos, self._r0):
            x, y = max(a, float(inicio)), min(b, float(fin))
            if y - x > EPS_TIEMPO:
                salida.append((float(r0 + x - a), float(r0 + y - a)))
        return salida

    def huecos(self, minimo: float = 1e-6) -> list[Hueco]:
        """Lo que falta en cada unión, en orden: antes del primer tramo, entre tramos y después
        del último. Sin tramos, todo el original es un solo hueco (al principio)."""
        salida: list[Hueco] = []
        anterior = 0.0
        for (a, b), r0 in zip(self.tramos, self._r0):
            if a - anterior > minimo:
                salida.append(Hueco(anterior, a, float(r0), principio=not salida and anterior <= minimo))
            anterior = b
        if self.duracion_original - anterior > minimo:
            salida.append(Hueco(anterior, self.duracion_original, self._total, principio=not self.tramos,
                                final=True))
        return salida


def segmentos_visibles(edicion: EdicionVideo) -> list[tuple[int, float, float]]:
    """Los segmentos que están en el resultado: (índice, inicio, fin) de la parte que se ve, en
    tiempo original y en orden (sin los borrados ni lo de fuera de la entrada y la salida)."""
    salida = []
    for i, s in enumerate(edicion.segmentos):
        if s.borrado:
            continue
        a, b = max(s.inicio, edicion.entrada), min(s.fin, edicion.fin)
        if b - a >= 1e-6:
            salida.append((i, a, b))
    return salida


def recuperar_hueco(edicion: EdicionVideo, hueco: Hueco) -> EdicionVideo:
    """Vuelve a poner lo que falta en una unión ("Recuperar lo borrado"): los segmentos borrados
    que caen en el hueco y, si es el del principio o el del final, la entrada o la salida.
    Los cortes quedan donde estaban. Si no hay nada que recuperar, devuelve la misma edición."""
    a, b = hueco.inicio, hueco.fin
    nueva = edicion
    for i, s in enumerate(edicion.segmentos):
        if s.borrado and s.inicio < b - 1e-6 and s.fin > a + 1e-6:
            nueva = nueva.con_borrado(i, False)
    if edicion.entrada > 0 and a <= 1e-6:  # lo recortado al principio está en este hueco
        nueva = replace(nueva, entrada=0.0)
    if edicion.salida is not None and b >= edicion.duracion - 1e-6:  # y lo recortado al final
        nueva = replace(nueva, salida=None)
    return nueva


# ---------------------------------------------------------------------------
# Filtro por cuadro
# ---------------------------------------------------------------------------

def _campos_variables() -> tuple[str, ...]:
    """Campos del ruido de sensor y del grano (sin el Bayer, que no es aleatorio)."""
    campos: list[str] = []
    for sec in SECCIONES:
        if sec.nombre in ("Sensor", "Grano"):
            if sec.interruptor:
                campos.append(sec.interruptor)
            campos.extend(c.campo for c in sec.controles if c.campo != "bayer")
    return tuple(campos)


_CAMPOS_VARIABLES = _campos_variables()


def separar_capa(ajustes: Ajustes, indice: int) -> tuple[Ajustes, Optional[Ajustes]]:
    """Divide una capa en la parte estable (semilla fija) y la del cuadro (ruido y grano).

    La segunda usa la semilla ``semilla + indice``: cambia en cada cuadro. Es
    None si la capa no tiene ruido ni grano.
    """
    a = ajustes
    hay_ruido = a.sensor_activo and a.ruido > 0
    hay_grano = a.grano_activo and a.grano > 0
    if a.intensidad <= 0 or not (hay_ruido or hay_grano):
        return a, None
    estable = replace(a, ruido=0, grano=0)
    valores = {c: getattr(a, c) for c in _CAMPOS_VARIABLES}
    valores.update(intensidad=a.intensidad, semilla=a.semilla + int(indice))
    if a.regiones_activas and hay_ruido and any(getattr(a, f"reg_{r}_ruido") != 100 for r in REGIONES):
        # Solo hace falta si las máscaras cambian la cantidad de ruido por región.
        valores["regiones_activas"] = True
        valores.update({f"reg_{r}_ruido": getattr(a, f"reg_{r}_ruido") for r in REGIONES})
    return estable, replace(NEUTRO, **valores)


def procesar_cuadro(
    rgb: np.ndarray,
    pila: Sequence[Ajustes],
    indice: int,
    escala_vista: float = 1.0,
    cancelado: Optional[Callable[[], bool]] = None,
) -> np.ndarray:
    """Aplica la pila de capas a un cuadro, con el ruido y el grano propios del cuadro ``indice``.

    Para ``indice`` 0 da exactamente lo mismo que ``procesar_pila`` con una foto.
    ``escala_vista``: tamaño del cuadro respecto del exportado (vista previa reducida).
    """
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("Se esperaba un cuadro RGB uint8 de forma HxWx3")
    if not pila:
        return rgb.copy()
    img: np.ndarray = rgb
    for i, ajustes in enumerate(pila):
        estable, variable = separar_capa(ajustes, indice)
        img = procesar_flotante(img, estable, escala_vista, cancelado, variacion_semilla=i)
        if variable is not None:
            img = procesar_flotante(img, variable, escala_vista, cancelado, variacion_semilla=i)
    return _finalizar(img, pila)


def procesar_cuadro_seguro(rgb: np.ndarray, pila: Sequence[Ajustes], indice: int, escala_vista: float = 1.0,
                           cancelado: Optional[Callable[[], bool]] = None) -> np.ndarray:
    """``procesar_cuadro`` para usar desde varios hilos a la vez.

    La caché de máscaras por región (``mascaras.py``) no está pensada para hilos:
    muy de vez en cuando dos hilos quieren desalojar la misma entrada y uno
    recibe KeyError. Como el resultado es determinista, se repite el cuadro.
    """
    for intento in range(3):
        try:
            return procesar_cuadro(rgb, pila, indice, escala_vista, cancelado)
        except (KeyError, RuntimeError):
            if intento == 2 or not any(a.regiones_activas for a in pila):
                raise
    raise AssertionError("inalcanzable")


# ---------------------------------------------------------------------------
# Mejorar calidad (sin IA): cuadros vecinos de cada tramo
#
# ``mejorar_cuadro`` (motor/mejora_video.py) usa los cuadros t-2, t-1, t+1 y t+2.
# Los vecinos salen siempre del MISMO tramo conservado: lo que viene después de
# un borrado no se mezcla con lo de antes. La vista previa (``tiempos_vecinos``)
# y la exportación (``VentanaVecinos``, la ventana de ``MejoradorVideo`` con su
# ``reiniciar`` en cada tramo) eligen los mismos, así se ve lo mismo.
# ---------------------------------------------------------------------------

def tamano_lectura(ancho: int, alto: int, ancho_salida: int, alto_salida: int) -> tuple[int, int]:
    """Tamaño al que se leen los cuadros para mejorarlos: el del original si la salida es igual o
    más grande (la mejora agranda) y, si es más chica, el de la salida (se achica al leer: mejorar
    un 4K entero para después achicarlo sería muy lento)."""
    if ancho_salida >= ancho and alto_salida >= alto:
        return int(ancho), int(alto)
    return int(ancho_salida), int(alto_salida)


def tiempos_vecinos(tramos: Sequence[tuple[float, float]], t: float, fps: float,
                    ultimo: Optional[float] = None, radio: int = RADIO_VECINOS) -> list[Optional[float]]:
    """Instantes (tiempo original) de los vecinos del cuadro que se ve en ``t``: [t-2, t-1, t+1, t+2]
    con ``radio`` 2. None donde el vecino no existe o cae fuera del tramo conservado de ``t``.

    Usa el mismo criterio que la exportación para decidir qué cuadro va en qué tramo (un cuadro
    que empieza en ``s`` va en el tramo (a, b) si ``a - ε <= s < b - ε``, con ε un cuarto de
    cuadro). ``ultimo``: comienzo del último cuadro del video (después no hay más). Para videos
    de cuadros por segundo constantes elige exactamente los mismos vecinos que la exportación.
    """
    eps = 0.25 / fps
    i = indice_en(t, fps)
    s = i / fps
    tramo = next(((a, b) for a, b in tramos if a - eps <= s < b - eps), None)
    salida: list[Optional[float]] = []
    for d in range(-radio, radio + 1):
        if d == 0:
            continue
        j = i + d
        sj = j / fps
        valido = (tramo is not None and j >= 0 and tramo[0] - eps <= sj < tramo[1] - eps
                  and (ultimo is None or sj <= ultimo + eps))
        salida.append(sj if valido else None)
    return salida


class VentanaVecinos:
    """Arma, en orden, cada cuadro con sus vecinos [t-2, t-1, t+1, t+2] dentro de su tramo.

    Es la misma ventana de ``MejoradorVideo`` (los mismos vecinos y el mismo retraso de ``radio``
    cuadros) pero no mejora: devuelve (cuadro, vecinos, dato) para mejorar varios cuadros a la vez
    en hilos. Con ``mejorar_cuadro(cuadro, vecinos, ...)`` da exactamente lo mismo que
    ``MejoradorVideo`` (``tests/test_mejora_ui.py`` lo compara cuadro por cuadro).

    * ``agregar(cuadro, dato)`` suma el próximo cuadro y devuelve los que ya tienen sus vecinos de
      adelante (el de hace ``radio`` cuadros).
    * ``cortar()`` cierra el tramo (un borrado en el medio, o el final): devuelve los que faltaban,
      con None donde no hay vecino. Lo que venga después no usa de vecinos a los de antes (es el
      ``reiniciar`` de ``MejoradorVideo``).

    ``dato`` acompaña al cuadro (por ejemplo, su número y su tiempo de salida). Los cuadros no se
    copian: no hay que modificarlos después de agregarlos.
    """

    def __init__(self, radio: int = RADIO_VECINOS):
        self.radio = int(radio)
        self._ventana: deque = deque()  # (cuadro, dato) del tramo actual: hasta 2·radio + 1
        self._sin_salir = 0  # cuántos de la ventana (los más nuevos) todavía no salieron

    def _armar(self, i: int) -> tuple:
        vecinos = []
        for d in range(-self.radio, self.radio + 1):
            if d:
                j = i + d
                vecinos.append(self._ventana[j][0] if 0 <= j < len(self._ventana) else None)
        cuadro, dato = self._ventana[i]
        return cuadro, vecinos, dato

    def agregar(self, cuadro, dato=None) -> list[tuple]:
        self._ventana.append((cuadro, dato))
        self._sin_salir += 1
        salida = []
        if self._sin_salir > self.radio:
            salida.append(self._armar(len(self._ventana) - self._sin_salir))
            self._sin_salir -= 1
            # El próximo en salir necesita ``radio`` cuadros de atrás: lo anterior sobra.
            while len(self._ventana) - self._sin_salir > self.radio:
                self._ventana.popleft()
        return salida

    def cortar(self) -> list[tuple]:
        n = len(self._ventana)
        salida = [self._armar(i) for i in range(n - self._sin_salir, n)]
        self._ventana.clear()
        self._sin_salir = 0
        return salida


class _Cupo:
    """Cuántas mejoras corren a la vez. Se puede agrandar en marcha (``fijar``)."""

    def __init__(self, n: int):
        self.n = n
        self._activos = 0
        self._condicion = threading.Condition()

    def fijar(self, n: int) -> None:
        with self._condicion:
            self.n = n
            self._condicion.notify_all()

    def __enter__(self):
        with self._condicion:
            while self._activos >= self.n:
                self._condicion.wait()
            self._activos += 1
        return self

    def __exit__(self, *_error) -> None:
        with self._condicion:
            self._activos -= 1
            self._condicion.notify_all()


# ---------------------------------------------------------------------------
# Exportación
# ---------------------------------------------------------------------------

def tamano_salida(ancho: int, alto: int, resolucion: Resolucion = None, agrandar: bool = False) -> tuple[int, int]:
    """Tamaño de salida (pares, como pide yuv420p). La resolución es el lado corto; nunca se agranda.

    ``agrandar`` (con "Mejorar calidad" prendida): si el video es más chico que la resolución pedida,
    se agranda hasta ella con ``tamano_mejorado`` (854×480 a "1080p" da 1920×1080). Lo que se achica
    sale igual que sin ``agrandar``."""
    lado = RESOLUCIONES.get(resolucion, None) if isinstance(resolucion, str) else resolucion
    if agrandar and lado is not None and min(ancho, alto) < lado:
        return tamano_mejorado(ancho, alto, lado)
    if lado is None or min(ancho, alto) <= lado:
        w, h = ancho, alto
    else:
        f = lado / min(ancho, alto)
        w, h = round(ancho * f), round(alto * f)
    return max(2, w - w % 2), max(2, h - h % 2)


@lru_cache(maxsize=2)
def elegir_codificador(gpu: bool = False) -> str:
    """El primer codificador de ``CODIFICADORES_H264`` que abre de verdad en esta PC.

    Con ``gpu``, antes prueba los de la placa (``CODIFICADORES_GPU``): el primero que abre gana.
    """
    _verificar_av()
    for nombre in (CODIFICADORES_GPU if gpu else ()) + CODIFICADORES_H264:
        try:
            cc = av.CodecContext.create(nombre, "w")
            cc.width, cc.height = 64, 64
            cc.pix_fmt = _FORMATO_PIXEL.get(nombre, "yuv420p")
            cc.time_base = Fraction(1, 30)
            cc.framerate = Fraction(30)
            if nombre != "libx264":
                cc.bit_rate = 1_000_000
            cc.open()
            return nombre
        except Exception:
            continue
    raise RuntimeError("No hay ningún codificador de video disponible en esta instalación de PyAV.")


def ruta_salida_video(original: Union[str, os.PathLike]) -> Path:
    """``nombre_celular.mp4`` junto al original, sin pisar nada que ya exista."""
    return ruta_salida_sugerida(original, ".mp4")


def _misma_ruta(a: Path, b: Path) -> bool:
    try:
        if a.exists() and b.exists():
            return os.path.samefile(a, b)
    except OSError:
        pass
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def hilos_por_defecto(pixeles: int) -> int:
    """Hilos de procesamiento. El filtro está limitado por el acceso a memoria: en
    esta PC (16 hilos) 1080p da 2,8 cuadros/s con 4 hilos y 2,9 con 6 u 8."""
    n = os.cpu_count() or 4
    hilos = max(2, min(6, n // 2))
    if pixeles > 3_000_000:  # 1440p o 4K: cada cuadro en vuelo ocupa mucha memoria
        hilos = min(hilos, 4)
    return hilos


@dataclass(frozen=True)
class ResultadoVideo:
    ruta: Path
    cuadros: int
    duracion: float
    ancho: int
    alto: int
    codec: str
    con_audio: bool
    segundos: float            # lo que tardó
    cuadros_por_segundo: float  # velocidad de exportación
    mejorado: bool = False     # si se aplicó "Mejorar calidad"
    hilos_mejora: int = 0      # cuántos cuadros se mejoraron a la vez al final (0 = sin la mejora)


# ---------------------------------------------------------------------------
# Sonido de otro archivo (ida y vuelta con el modo Audio, "Cambiar el sonido por…")
#
# El video puede sonar con otro archivo en vez del suyo (``AudioExterno``):
# * "original": el archivo está alineado con el video ORIGINAL, sin cortes (por ejemplo, el
#   sonido del propio video procesado en el modo Audio). Se le aplican los mismos tramos y los
#   mismos ``AjustesAudio`` que al sonido del video: es exactamente el camino de siempre, con
#   otra ruta.
# * "resultado": el archivo empieza en el 0 del RESULTADO (una voz en off). Se corta al largo
#   del resultado y, si es más corto, sigue en silencio. Volumen, normalizar y fundidos van
#   igual (los fundidos, en el principio y el final del resultado); los silencios, que están
#   en tiempo original, se pasan al resultado con ``MapaTiempo``. Lo arma ``LectorDesdeCero``,
#   el mismo para exportar y para escuchar.
# Con ``AjustesAudio.quitar`` no hay sonido, haya o no externo.
# ---------------------------------------------------------------------------

ALINEADOS = ("original", "resultado")
CARPETA_DATOS = "NaturalShot PRO"   # dentro de %APPDATA% (la misma de la sesión)
CARPETA_TEMPORAL = "temporal"       # %APPDATA%\NaturalShot PRO\temporal: los WAV para el modo Audio
DIAS_TEMPORALES = 7                 # los temporales de más de una semana se borran al abrir el editor


@dataclass(frozen=True)
class AudioExterno:
    """El sonido de otro archivo, puesto en lugar del sonido del video.

    ruta      el archivo (audio: MP3, M4A, AAC, WAV, OGG, OPUS, FLAC; o un video con sonido).
    alineado  "original": alineado con el video original, sin cortes (se le aplican los mismos
              tramos); "resultado": empieza en el 0 de lo que se exporta (voz en off).

    Inmutable (entra al historial de deshacer) y se puede guardar con pickle. Que el archivo
    exista y tenga sonido se comprueba al usarlo (``validar_audio_externo``).
    """

    ruta: str
    alineado: str = "original"

    def __post_init__(self):
        ruta = os.fspath(self.ruta) if isinstance(self.ruta, os.PathLike) else self.ruta
        if not isinstance(ruta, str) or not ruta.strip():
            raise ValueError("Falta la ruta del sonido.")
        if self.alineado not in ALINEADOS:
            raise ValueError(f"Alineación desconocida: {self.alineado!r} (usá 'original' o 'resultado').")
        object.__setattr__(self, "ruta", str(ruta))

    @property
    def nombre(self) -> str:
        return Path(self.ruta).name

    @property
    def desde_cero(self) -> bool:
        """True si empieza en el 0 del resultado (voz en off)."""
        return self.alineado == "resultado"


def validar_audio_externo(externo: "AudioExterno"):
    """Comprueba que el sonido externo se pueda usar y devuelve su información (``audio.info_medio``).

    ``ValueError`` con un mensaje claro si no existe, no se puede abrir o no tiene sonido."""
    if not isinstance(externo, AudioExterno):
        raise ValueError("El sonido externo tiene que ser un AudioExterno.")
    from . import audio as ma
    ruta = Path(externo.ruta)
    if not ruta.is_file():
        raise ValueError(f"No se encuentra el sonido elegido: {ruta}")
    try:
        info = ma.info_medio(ruta)
    except Exception as error:
        raise ValueError(f"No se pudo abrir el sonido elegido ({ruta.name}): {error}") from error
    if not info.tiene_audio:
        raise ValueError(f"{ruta.name} no tiene sonido.")
    return info


def silencios_en_resultado(silencios: Sequence[tuple[float, float]], mapa: "MapaTiempo"
                           ) -> tuple[tuple[float, float], ...]:
    """Los silencios (tiempo original) pasados al tiempo del resultado: solo sus partes que se ven,
    unidas si quedan pegadas (un silencio que cruza un borrado queda de un solo trozo)."""
    rangos = sorted(r for a, b in silencios for r in mapa.rangos_resultado(a, b))
    unidos: list[tuple[float, float]] = []
    for a, b in rangos:
        if unidos and a <= unidos[-1][1] + 1e-6:
            unidos[-1] = (unidos[-1][0], max(unidos[-1][1], b))
        else:
            unidos.append((a, b))
    return tuple(unidos)


def sonido_a_medir(ruta_video: Union[str, os.PathLike], tramos: Optional[Sequence[tuple[float, float]]],
                   duracion: float, silencios: Sequence[tuple[float, float]] = (),
                   audio_externo: Optional["AudioExterno"] = None
                   ) -> tuple[str, tuple[tuple[float, float], ...], tuple[tuple[float, float], ...]]:
    """(ruta, tramos, silencios) de lo que suena, para ``audio.medir_pico`` (normalizar) y su caché.

    Sin externo: el video con sus tramos. "original": el externo con los mismos tramos y silencios.
    "resultado": el externo de 0 al largo del resultado, con los silencios pasados al resultado."""
    tramos_ok = tuple(normalizar_tramos(tramos, duracion))
    silencios = tuple(tuple(s) for s in silencios)
    if audio_externo is None:
        return str(ruta_video), tramos_ok, silencios
    if not audio_externo.desde_cero:
        return audio_externo.ruta, tramos_ok, silencios
    mapa = MapaTiempo(tramos_ok, duracion)
    return audio_externo.ruta, ((0.0, mapa.duracion),), silencios_en_resultado(silencios, mapa)


class LectorDesdeCero:
    """Un sonido externo "desde el principio del resultado" (voz en off), con la interfaz de
    ``audio.LectorPCM``: lo usan la exportación y la vista previa (``ReproductorAudio.reproducir_lector``).

    ruta      el sonido externo.
    tramos    los que conserva el VIDEO (tiempo original; None = todo) y ``duracion``, la del video:
              arman el ``MapaTiempo`` que dice cuánto dura el resultado y qué instante del original
              se ve en cada segundo (para que la imagen siga al sonido).
    ajustes   los ``AjustesAudio`` del video. Los silencios se pasan al resultado; los fundidos van en
              el principio y el final del resultado (aunque el externo sea más corto).
    desde     instante del tiempo ORIGINAL donde empezar.
    frecuencia, canales, formato, pico: como en ``LectorPCM``.

    El sonido es el del externo desde su segundo 0, cortado al largo del resultado (con un fundido
    corto de 5 ms en el corte) y, si es más corto, completado con silencio. Adentro hay un
    ``LectorPCM`` del externo (tramo de 0 al largo del resultado, sin fundidos): los fundidos se
    aplican acá, después de la ganancia (con volumen de más de 100 % y saturación, la curva del
    fundido se aplica sobre lo ya recortado: la diferencia no se oye).
    """

    FORMATOS = {"s16": np.int16, "f32": np.float32}

    def __init__(self, ruta: Union[str, os.PathLike], tramos: Optional[Sequence[tuple[float, float]]],
                 duracion: float, ajustes: Optional["AjustesAudio"] = None, desde: float = 0.0,
                 frecuencia: int = 48000, canales: int = 2, formato: str = "s16", pico: Optional[float] = None):
        from . import audio as ma
        if formato not in self.FORMATOS:
            raise ValueError(f"Formato desconocido: {formato!r} (usá 's16' o 'f32').")
        self._ma = ma
        self.ruta = str(ruta)
        self.mapa = MapaTiempo(tuple(normalizar_tramos(tramos, duracion)), duracion)
        self.frecuencia = int(frecuencia)
        self.canales = 1 if int(canales) == 1 else 2
        self.formato = formato
        self.total = round(self.mapa.duracion * self.frecuencia)  # muestras del resultado
        self._candado = threading.Lock()
        self.ajustes = ajustes or ma.AjustesAudio()
        self._fundidos(self.ajustes)
        self._lector = ma.LectorPCM(self.ruta, [(0.0, self.mapa.duracion)], self._para_lector(self.ajustes), 0.0,
                                    self.frecuencia, self.canales, "f32", pico)
        self.tiene_audio = bool(self._lector.tiene_audio)
        self._pos = 0
        self.ir_a(desde)

    # ------------------------------------------------------------ ajustes
    def _para_lector(self, ajustes: "AjustesAudio") -> "AjustesAudio":
        """Lo que hace el lector de adentro: todo menos los fundidos, con los silencios en el resultado."""
        return ajustes.con(fundido_entrada=0.0, fundido_salida=0.0,
                           silencios=silencios_en_resultado(ajustes.silencios, self.mapa))

    def _fundidos(self, ajustes: "AjustesAudio") -> None:
        self._entrada = round(ajustes.fundido_entrada * self.frecuencia)
        self._salida = round(ajustes.fundido_salida * self.frecuencia)

    def cambiar_ajustes(self, ajustes: "AjustesAudio", pico: Optional[float] = None) -> None:
        """Ajustes nuevos sin moverse de lugar (como ``LectorPCM.cambiar_ajustes``)."""
        self._lector.cambiar_ajustes(self._para_lector(ajustes), pico)
        with self._candado:
            self.ajustes = ajustes
            self._fundidos(ajustes)

    # ------------------------------------------------------------ datos
    @property
    def bytes_por_muestra(self) -> int:
        return self.canales * np.dtype(self.FORMATOS[self.formato]).itemsize

    @property
    def duracion_resultado(self) -> float:
        return self.total / self.frecuencia

    @property
    def posicion_resultado(self) -> float:
        return self._pos / self.frecuencia

    @property
    def posicion(self) -> float:
        """Instante del tiempo original que se ve con la próxima muestra."""
        return self.original_de_resultado(self.posicion_resultado)

    @property
    def terminado(self) -> bool:
        return self._pos >= self.total

    def original_de_resultado(self, t: float) -> float:
        return float(self.mapa.a_original(min(self.mapa.duracion, max(0.0, float(t)))))

    def resultado_de_original(self, t: float) -> float:
        return float(self.mapa.a_resultado(max(0.0, float(t))))

    # ------------------------------------------------------------ control
    def ir_a(self, t: float) -> None:
        """Salta al instante ``t`` del tiempo original (si está borrado, a la unión)."""
        self.ir_a_resultado(self.resultado_de_original(t))

    def ir_a_resultado(self, t: float) -> None:
        with self._candado:
            self._pos = min(self.total, max(0, round(float(t) * self.frecuencia)))
            self._lector.ir_a_resultado(self._pos / self.frecuencia)

    def _envolvente(self, o0: int, n: int) -> Optional[np.ndarray]:
        g: Optional[np.ndarray] = None
        if self._entrada and o0 < self._entrada:
            g = np.clip((np.arange(o0, o0 + n) + 0.5) / self._entrada, 0.0, 1.0) ** 2
        if self._salida and o0 + n > self.total - self._salida:
            f = np.clip((self.total - np.arange(o0, o0 + n) - 0.5) / self._salida, 0.0, 1.0) ** 2
            g = f if g is None else g * f
        return None if g is None else g.astype(np.float32)

    def leer_array(self, muestras: int) -> np.ndarray:
        """Hasta ``muestras`` muestras como float32 (n × canales); vacío al terminar."""
        with self._candado:
            m = max(0, min(int(muestras), self.total - self._pos))
            if m == 0:
                return np.zeros((0, self.canales), np.float32)
            datos = self._lector.leer_array(m)
            if datos.shape[0] < m:  # el externo terminó antes que el video: sigue en silencio
                datos = np.concatenate((datos, np.zeros((m - datos.shape[0], self.canales), np.float32)))
            else:
                datos = np.array(datos, dtype=np.float32, copy=True)
            g = self._envolvente(self._pos, m)
            if g is not None:
                datos *= g[:, None]
            self._pos += m
            return datos

    def leer(self, muestras: int) -> bytes:
        datos = self.leer_array(muestras)
        if self.formato == "s16":
            datos = self._ma._a_int16(datos)
        return datos.astype("<" + np.dtype(self.FORMATOS[self.formato]).str[1:], copy=False).tobytes()

    def cerrar(self) -> None:
        self._lector.cerrar()

    def __enter__(self) -> "LectorDesdeCero":
        return self

    def __exit__(self, *_exc) -> None:
        self.cerrar()


class _MezclaDeLector:
    """Un lector (n × canales) con la forma de la mezcla que codifica la exportación (canales × n)."""

    def __init__(self, lector):
        self.lector = lector
        self.total = lector.total

    def leer(self, n: int) -> np.ndarray:
        return np.ascontiguousarray(self.lector.leer_array(n).T)

    def cerrar(self) -> None:
        self.lector.cerrar()


def _mezcla_sonido(entrada: Path, info: InfoVideo, tramos: list, ajustes: Optional["AjustesAudio"],
                   externo: Optional[AudioExterno], frecuencia: int, canales: int, cancelado):
    """La mezcla del sonido que se exporta: el del video o el externo (ver arriba)."""
    from . import audio as ma
    if externo is None:
        return ma.preparar_mezcla(entrada, tramos, ajustes, frecuencia, canales, cancelado=cancelado)
    if not externo.desde_cero:  # "original": el camino de siempre, con el otro archivo
        return ma.preparar_mezcla(externo.ruta, tramos, ajustes, frecuencia, canales, cancelado=cancelado)
    ajustes = ajustes or ma.AjustesAudio()
    pico = None
    if ajustes.normalizar:
        pico = ma.medir_pico(*sonido_a_medir(entrada, tramos, info.duracion, ajustes.silencios, externo), cancelado)
    return _MezclaDeLector(LectorDesdeCero(externo.ruta, tramos, info.duracion, ajustes, 0.0, frecuencia, canales,
                                           "f32", pico))


def exportar_sonido(
    ruta_video: Union[str, os.PathLike],
    ruta_salida: Union[str, os.PathLike],
    tramos: Optional[Sequence[tuple[float, float]]] = None,
    ajustes: Optional["AjustesAudio"] = None,
    audio_externo: Optional[AudioExterno] = None,
    formato: Optional[str] = None,
    progreso: Optional[Progreso] = None,
    cancelado: Optional[Callable[[], bool]] = None,
    pico: Optional[float] = None,
):
    """"Guardar solo el audio" de lo que se exporta, también con un sonido externo.

    Sin externo es ``audio.exportar_audio`` del video; con "original", del externo con los mismos
    tramos; con "resultado", el externo desde el 0 del resultado (``LectorDesdeCero``), con el
    mismo cuidado: temporal en la misma carpeta, nada a medias. Devuelve ``audio.ResultadoAudio``."""
    from . import audio as ma
    if audio_externo is None:
        return ma.exportar_audio(ruta_video, ruta_salida, tramos, ajustes, formato, progreso, cancelado, pico)
    inicio_reloj = time.perf_counter()
    salida = Path(ruta_salida)
    if _misma_ruta(Path(ruta_video), salida):
        raise ValueError("Ese es el video original. Para no sobrescribirlo, elegí otro nombre.")
    info_externo = validar_audio_externo(audio_externo)
    if not audio_externo.desde_cero:
        return ma.exportar_audio(audio_externo.ruta, salida, tramos, ajustes, formato, progreso, cancelado, pico)
    if _misma_ruta(Path(audio_externo.ruta), salida):
        raise ValueError("Ese es el sonido que se está usando. Para no sobrescribirlo, elegí otro nombre.")
    nombre = (formato or salida.suffix.lstrip(".")).lower()
    if nombre not in ma.FORMATOS_AUDIO:
        raise ValueError(f"Formato de audio desconocido: {nombre!r}. Usá M4A, WAV o MP3.")
    if nombre not in ma._disponibles():
        raise ValueError(f"Esta instalación no puede guardar {ma.FORMATOS_AUDIO[nombre].descripcion}.")
    fmt = ma.FORMATOS_AUDIO[nombre]
    ajustes = ajustes or ma.AjustesAudio()
    if ajustes.quitar:
        raise ValueError("El sonido está quitado: no hay audio para guardar.")
    info = info_video(ruta_video)
    tramos_ok = normalizar_tramos(tramos, info.duracion)
    if not tramos_ok:
        raise ValueError("No queda ningún tramo para exportar: están todos borrados.")
    frecuencia, canales = ma._formato_natural(info_externo)
    frecuencia = ma._frecuencia_para(fmt.codec, frecuencia)
    cancelado = cancelado or (lambda: False)
    salida.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(prefix=f".{salida.stem}.", suffix=".parcial" + fmt.extension,
                                    dir=str(salida.parent))
    os.close(fd)
    try:
        if ajustes.normalizar and pico is None:
            pico = ma.medir_pico(*sonido_a_medir(ruta_video, tramos_ok, info.duracion, ajustes.silencios,
                                                 audio_externo), cancelado)
        mezcla = _MezclaDeLector(LectorDesdeCero(audio_externo.ruta, tramos_ok, info.duracion, ajustes, 0.0,
                                                 frecuencia, canales, "f32", pico))
        try:
            escritas = ma._codificar(mezcla, temporal, fmt, frecuencia, canales, progreso, cancelado)
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
    return ma.ResultadoAudio(salida, nombre, escritas / frecuencia, frecuencia, canales,
                             time.perf_counter() - inicio_reloj)


def carpeta_temporal() -> Path:
    """``%APPDATA%\\NaturalShot PRO\\temporal``: los WAV que van y vuelven del modo Audio."""
    return Path(os.environ.get("APPDATA") or Path.home()) / CARPETA_DATOS / CARPETA_TEMPORAL


def ruta_temporal_sonido(ruta_video: Union[str, os.PathLike]) -> Path:
    """Un WAV nuevo en ``carpeta_temporal()`` con el nombre del video y la hora
    (``charla_sonido_20261013-164500.wav``; si ya existe, con ``-2``, ``-3``…). Crea la carpeta."""
    carpeta = carpeta_temporal()
    carpeta.mkdir(parents=True, exist_ok=True)
    base = "".join(c if c.isalnum() or c in " -_." else "_" for c in Path(ruta_video).stem).strip() or "video"
    base = f"{base[:60]}_sonido_{time.strftime('%Y%m%d-%H%M%S')}"
    ruta, n = carpeta / f"{base}.wav", 2
    while ruta.exists():
        ruta, n = carpeta / f"{base}-{n}.wav", n + 1
    return ruta


def limpiar_temporales(dias: float = DIAS_TEMPORALES, conservar: Sequence[Union[str, os.PathLike]] = (),
                       antes_de_borrar: Optional[Callable[[Path], None]] = None) -> list[Path]:
    """Borra los archivos de ``carpeta_temporal()`` de más de ``dias`` días (por la fecha de
    modificación). ``conservar``: los que están en uso (no se borran aunque sean viejos).
    ``antes_de_borrar(ruta)``: para cerrar un lector que lo esté leyendo. Los que no se pueden
    borrar (abiertos por otro programa) quedan. Devuelve los borrados."""
    carpeta = carpeta_temporal()
    if not carpeta.is_dir():
        return []
    limite = time.time() - float(dias) * 86400
    protegidos = {os.path.normcase(os.path.abspath(p)) for p in conservar}
    borrados = []
    for ruta in carpeta.iterdir():
        try:
            if not ruta.is_file() or ruta.stat().st_mtime >= limite:
                continue
            if os.path.normcase(os.path.abspath(ruta)) in protegidos:
                continue
            if antes_de_borrar is not None:
                antes_de_borrar(ruta)
            ruta.unlink()
            borrados.append(ruta)
        except OSError:
            continue
    return borrados


class _EscritorAudio:
    """Ubica las muestras en la línea de tiempo de salida y las codifica en AAC.

    Si entre dos bloques queda un hueco se rellena con silencio; si se pisan, se
    descarta lo repetido. Los últimos ``reserva`` segundos no se codifican hasta
    saber dónde termina el último cuadro: así el audio dura exactamente lo mismo
    que el video aunque el contenedor declare una duración un poco más larga
    (pasa en MKV y WebM, donde la cola del audio pasa al último cuadro).
    """

    def __init__(self, contenedor, stream, frecuencia: int, canales: int, total: int, reserva: float = 0.5):
        self._contenedor = contenedor
        self._stream = stream
        self._frecuencia = frecuencia
        self._canales = canales
        self._layout = "stereo" if canales == 2 else "mono"
        self._reserva = int(reserva * frecuencia)
        self.total = total  # muestras como máximo (la duración de los tramos)
        self.escritas = 0   # muestras ya ubicadas (en el búfer o codificadas)
        self._bufer: list[np.ndarray] = []
        self._en_bufer = 0
        self._codificadas = 0

    def colocar(self, inicio: int, datos: np.ndarray) -> None:
        if inicio > self.escritas + 2:
            self._agregar(np.zeros((self._canales, inicio - self.escritas), np.float32))
        elif inicio < self.escritas - 2:
            datos = datos[:, self.escritas - inicio:]
        lugar = self.total - self.escritas
        if lugar <= 0 or datos.shape[1] == 0:
            return
        self._agregar(datos[:, :lugar])

    def _agregar(self, datos: np.ndarray) -> None:
        datos = np.ascontiguousarray(datos, dtype=np.float32)
        self._bufer.append(datos)
        self._en_bufer += datos.shape[1]
        self.escritas += datos.shape[1]
        self._vaciar(final=False)

    def _vaciar(self, final: bool) -> None:
        guardar = 0 if final else self._reserva
        if self._en_bufer - guardar < MUESTRAS_AAC and not (final and self._en_bufer):
            return
        todo = np.concatenate(self._bufer, axis=1) if len(self._bufer) > 1 else self._bufer[0]
        pos = 0
        while todo.shape[1] - guardar - pos >= MUESTRAS_AAC or (final and pos < todo.shape[1]):
            trozo = np.ascontiguousarray(todo[:, pos:pos + MUESTRAS_AAC])
            cuadro = av.AudioFrame.from_ndarray(trozo, format="fltp", layout=self._layout)
            cuadro.sample_rate = self._frecuencia
            cuadro.pts = self._codificadas
            cuadro.time_base = Fraction(1, self._frecuencia)
            for paquete in self._stream.encode(cuadro):
                self._contenedor.mux(paquete)
            self._codificadas += trozo.shape[1]
            pos += trozo.shape[1]
        resto = todo[:, pos:]
        self._bufer = [resto] if resto.shape[1] else []
        self._en_bufer = resto.shape[1]

    def terminar(self, total: Optional[int] = None) -> None:
        """Completa con silencio o recorta la cola para llegar a ``total`` muestras y cierra."""
        if total is not None:
            self.total = min(self.total, total) if self.escritas >= total else total
        sobra = self.escritas - self.total
        if sobra > 0 and self._en_bufer:
            todo = np.concatenate(self._bufer, axis=1)
            quitar = min(sobra, todo.shape[1])
            todo = todo[:, :todo.shape[1] - quitar]
            self._bufer = [todo] if todo.shape[1] else []
            self._en_bufer = todo.shape[1]
            self.escritas -= quitar
        if self.escritas < self.total:
            self._agregar(np.zeros((self._canales, self.total - self.escritas), np.float32))
        if self._en_bufer:
            self._vaciar(final=True)
        for paquete in self._stream.encode(None):
            self._contenedor.mux(paquete)


def exportar_video(
    ruta_entrada: Union[str, os.PathLike],
    ruta_salida: Union[str, os.PathLike],
    pila: Sequence[Ajustes],
    tramos: Optional[Sequence[tuple[float, float]]] = None,
    resolucion: Resolucion = None,
    calidad: Union[str, int] = "Alta",
    progreso: Optional[Progreso] = None,
    cancelado: Optional[Callable[[], bool]] = None,
    hilos: Optional[int] = None,
    audio: Optional["AjustesAudio"] = None,
    mejora: Optional[AjustesMejora] = None,
    audio_externo: Optional[AudioExterno] = None,
    gpu: bool = False,
) -> ResultadoVideo:
    """Exporta el video con el filtro a un MP4 nuevo (H.264 + AAC).

    pila        capas de ``Ajustes`` (la misma pila de la app; vacía = sin filtro).
    tramos      [(inicio, fin)] en segundos que se CONSERVAN, en orden; None = todo.
    resolucion  None/"Original", "1080p", "720p" o el lado corto en píxeles.
    calidad     "Alta", "Normal", "Liviana" (ver ``CALIDADES``) o un CRF de x264 (0-51).
    progreso    progreso(hechos, total, segundos_restantes_estimados o None).
    cancelado   cancelado() -> True para abandonar: se lanza ``Cancelado`` y no queda archivo.
    audio       ``AjustesAudio`` de ``motor/audio.py``: con ``quitar`` el MP4 sale sin pista
                de audio; si no, se aplican volumen, normalizar, fundidos y silencios.
                None = el sonido tal cual (igual que ``AjustesAudio()``). Con normalizar,
                antes de empezar se hace una pasada rápida solo de audio para medir el pico.
    mejora      ``AjustesMejora`` de ``motor/mejora_video.py`` ("Mejorar calidad", sin IA).
                None o apagada = igual que siempre. Prendida: 720p y 1080p también agrandan
                un video más chico, y cada cuadro se mejora (con sus vecinos del mismo tramo)
                antes del filtro, ya al tamaño de salida. Tarda más.
    audio_externo  ``AudioExterno``: el sonido sale de otro archivo, con los mismos ``audio``
                ("original": los mismos tramos del video; "resultado": desde el 0 del resultado,
                cortado a su largo o completado con silencio; ver ``LectorDesdeCero``). Se
                remuestrea a la frecuencia del sonido del video (o, si el video no tiene, a la del
                externo) y sale en estéreo si alguno de los dos lo es. Con ``audio.quitar`` no hay
                sonido. Un externo que no existe o no tiene sonido da ``ValueError`` antes de empezar.
    gpu         NS-101.2: codificar con la placa de video si hay una (NVENC, Quick Sync o AMF). Si
                no hay o falla a mitad de camino, sale igual con x264 (``ResultadoVideo.codec`` dice cuál).
    """
    _verificar_av()
    inicio_reloj = time.perf_counter()
    entrada, salida = Path(ruta_entrada), Path(ruta_salida)
    if not entrada.is_file():
        raise FileNotFoundError(f"No existe el video: {entrada}")
    if _misma_ruta(entrada, salida):
        raise ValueError("Ese es el video original. Para no sobrescribirlo, elegí otro nombre.")
    if audio_externo is not None and audio is not None and audio.quitar:
        audio_externo = None  # sin sonido: el externo no importa
    if audio_externo is not None:
        validar_audio_externo(audio_externo)
        if _misma_ruta(Path(audio_externo.ruta), salida):
            raise ValueError("Ese es el sonido que se está usando. Para no sobrescribirlo, elegí otro nombre.")
    info = info_video(entrada)
    tramos_ok = normalizar_tramos(tramos, info.duracion)
    if not tramos_ok:
        raise ValueError("No queda ningún tramo para exportar: están todos borrados.")
    if mejora is not None and not mejora.activa:
        mejora = None  # apagada: exactamente el camino de siempre
    ancho, alto = tamano_salida(info.ancho, info.alto, resolucion, agrandar=mejora is not None)
    codec = elegir_codificador(gpu)
    crf, tune = CALIDADES.get(calidad, CALIDADES["Alta"]) if isinstance(calidad, str) else (int(calidad), None)
    pila = tuple(pila or ())
    cancelado = cancelado or (lambda: False)
    fps = info.fps
    eps = 0.25 / fps
    total = sum(max(1, round((b - a) * fps)) for a, b in tramos_ok)
    duracion_total = sum(b - a for a, b in tramos_ok)
    hilos = max(1, int(hilos or hilos_por_defecto(ancho * alto)))

    salida.parent.mkdir(parents=True, exist_ok=True)
    detalle: dict = {}  # lo que cuenta _exportar además (cuántos cuadros se mejoraron a la vez)
    fd, temporal = tempfile.mkstemp(prefix=f".{salida.stem}.", suffix=".parcial.mp4", dir=str(salida.parent))
    os.close(fd)
    try:
        try:
            cuadros, con_audio, duracion_total = _exportar(entrada, temporal, info, pila, tramos_ok, ancho, alto,
                                                           codec, crf, tune, total, duracion_total, eps, progreso,
                                                           cancelado, hilos, audio, mejora, detalle, audio_externo)
        except Cancelado:
            raise
        except Exception:
            # La placa abrió en la prueba pero falló con el video real (driver, memoria, tamaño):
            # se repite entera con el codificador de siempre.
            if codec not in CODIFICADORES_GPU or cancelado():
                raise
            codec = elegir_codificador(False)
            cuadros, con_audio, duracion_total = _exportar(entrada, temporal, info, pila, tramos_ok, ancho, alto,
                                                           codec, crf, tune, total, duracion_total, eps, progreso,
                                                           cancelado, hilos, audio, mejora, detalle, audio_externo)
        if cancelado():
            raise Cancelado()
        os.replace(temporal, salida)
    except BaseException:
        try:
            os.remove(temporal)
        except OSError:
            pass
        raise
    segundos = time.perf_counter() - inicio_reloj
    return ResultadoVideo(salida, cuadros, duracion_total, ancho, alto, codec, con_audio, segundos,
                          cuadros / segundos if segundos > 0 else 0.0, mejora is not None,
                          detalle.get("hilos_mejora", 0))


def _exportar(entrada: Path, temporal: str, info: InfoVideo, pila: tuple, tramos: list, ancho: int, alto: int,
              codec: str, crf: int, tune: Optional[str], total: int, duracion_total: float, eps: float,
              progreso, cancelado, hilos: int, ajustes_audio: Optional["AjustesAudio"] = None,
              mejora: Optional[AjustesMejora] = None, detalle: Optional[dict] = None,
              audio_externo: Optional[AudioExterno] = None,
              ) -> tuple[int, bool, float]:
    fps = info.fps
    formato_pixel = _FORMATO_PIXEL.get(codec, "yuv420p")
    # Para cada tramo, cuánto se corre hacia atrás: (inicio, fin, inicio en la salida).
    acumulado, con_offset = 0.0, []
    for a, b in tramos:
        con_offset.append((a, b, acumulado))
        acumulado += b - a
    fin_total = tramos[-1][1]

    contenedor = av.open(str(entrada))
    destino = None
    mezcla = None
    pool = ThreadPoolExecutor(max_workers=hilos, thread_name_prefix="video")
    pendientes: deque = deque()
    # Mejorar calidad: sus propios hilos (hasta HILOS_MEJORA cuadros a la vez, cada uno con sus vecinos; ver
    # ``_Cupo`` y ``decidir``); el filtro sigue en paralelo, después.
    hilos_mejora = max(1, int(HILOS_MEJORA))
    hilo_mejora = (ThreadPoolExecutor(max_workers=hilos_mejora, thread_name_prefix="mejora")
                   if mejora is not None else None)
    en_mejora: deque = deque()  # (mejora en curso -> futuro del filtro, tiempo de salida), en orden
    try:
        vs = contenedor.streams.video[0]
        vs.thread_type = "AUTO"
        aud = contenedor.streams.audio[0] if contenedor.streams.audio else None
        if aud is not None:
            # El audio se lee aparte (motor/audio.py, con su propio archivo abierto): acá ni se lee.
            try:
                aud.discard = av.stream.Discard.all
            except Exception:
                pass
        quitar = ajustes_audio is not None and ajustes_audio.quitar
        destino = av.open(temporal, "w", format="mp4", container_options={"movflags": "+faststart"})

        tb = vs.time_base or Fraction(1, 90000)
        if codec == "mpeg4" and tb.denominator > 65535:
            tb = Fraction(1, 60000)
        ov = destino.add_stream(codec, rate=info.tasa)
        ov.width, ov.height = ancho, alto
        ov.pix_fmt = formato_pixel
        ov.codec_context.time_base = tb
        ov.time_base = tb
        cc = ov.codec_context
        cc.color_primaries, cc.color_trc, cc.colorspace, cc.color_range = 1, 1, 1, 1  # BT.709, rango limitado
        if codec == "libx264":
            ov.options = {"crf": str(crf), "preset": "medium", "profile": "high", **({"tune": tune} if tune else {})}
        else:
            # Sin CRF: tasa de bits según tamaño y calidad (≈ lo que da x264 con ese CRF en video con ruido).
            bpp = max(0.04, 0.22 * 2 ** ((17 - crf) / 6))
            cc.bit_rate = int(ancho * alto * fps * bpp)

        # Audio: la mezcla del motor de sonido entrega el resultado ya armado (tramos uno
        # detrás de otro, con los ajustes) y se codifica a la par del video. Con un sonido
        # externo, la mezcla sale de ese archivo (``_mezcla_sonido``). "Quitar el sonido": el
        # MP4 sale sin pista de audio.
        escritor: Optional[_EscritorAudio] = None
        frecuencia = 0
        if not quitar and (aud is not None or audio_externo is not None):
            try:
                if aud is not None:
                    ca = aud.codec_context
                    frecuencia = int(ca.sample_rate or 48000)
                    canales = 2 if int(getattr(ca, "channels", 0) or 2) >= 2 else 1
                else:
                    frecuencia, canales = 0, 1
                if audio_externo is not None:
                    from . import audio as motor_audio
                    info_externo = motor_audio.info_medio(audio_externo.ruta)
                    frecuencia = frecuencia or int(info_externo.frecuencia_audio or 48000)
                    if int(info_externo.canales_audio or 2) >= 2:
                        canales = 2  # estéreo si alguno de los dos lo es
                if frecuencia not in _FRECUENCIAS_AAC:
                    frecuencia = 48000
                mezcla = _mezcla_sonido(entrada, info, tramos, ajustes_audio, audio_externo, frecuencia, canales,
                                        cancelado)
                oa = destino.add_stream("aac", rate=frecuencia)
                oa.layout = "stereo" if canales == 2 else "mono"
                oa.bit_rate = 192_000 if canales == 2 else 128_000
                escritor = _EscritorAudio(destino, oa, frecuencia, canales, mezcla.total)
            except Cancelado:
                raise
            except Exception:
                # Audio que no se puede leer: video sin sonido.
                if mezcla is not None:
                    mezcla.cerrar()
                mezcla, escritor = None, None

        audio_estado = {"fin": escritor is None}

        def bombear(hasta: int) -> None:
            """Codifica el audio del resultado hasta la muestra ``hasta`` (va un poco adelante del video)."""
            while not audio_estado["fin"] and escritor.escritas < min(hasta, escritor.total):
                try:
                    bloque = mezcla.leer(min(8192, hasta - escritor.escritas))
                except Cancelado:
                    raise
                except Exception:
                    bloque = None  # audio que deja de poder leerse: lo que falta queda en silencio
                if bloque is None or not bloque.shape[1]:
                    audio_estado["fin"] = True
                    break
                escritor.colocar(escritor.escritas, bloque)

        rotacion = info.rotacion
        dst = "ITU709"

        def trabajo(cuadro, indice: int):
            if cancelado():
                raise Cancelado()
            rgb = _a_rgb(cuadro, rotacion, ancho, alto)
            del cuadro
            listo = procesar_cuadro_seguro(rgb, pila, indice, 1.0, cancelado)
            vf = av.VideoFrame.from_ndarray(listo, format="rgb24")
            return vf.reformat(format=formato_pixel, dst_colorspace=dst, dst_color_range="MPEG",
                               interpolation=_flags())

        # Mejorar calidad: los cuadros se leen a este tamaño (el original o, si la salida es más chica,
        # el de salida). La ventana arma cada cuadro con sus vecinos del mismo tramo (como
        # ``MejoradorVideo``, que se reinicia en cada tramo); cada uno se mejora en los hilos de la
        # mejora y después pasa al filtro, en paralelo. Se escriben en orden.
        lectura = tamano_lectura(info.ancho, info.alto, ancho, alto) if mejora is not None else None
        ventana = VentanaVecinos() if mejora is not None else None
        # De a un cuadro hasta saber qué es lo lento. Con el filtro de la app la mejora no es el cuello
        # de botella y repartirla solo le saca CPU al filtro (medido: 1080p, 158 s de a uno contra 183
        # de a tres); sin filtro, sí (32 s contra 49). El resultado es el mismo: solo cambia la velocidad.
        cupo = _Cupo(1)
        medidas: dict = {"mejora": [], "filtro": [], "decidido": False}

        def decidir() -> None:
            mejoras, filtros = medidas["mejora"], medidas["filtro"]
            if medidas["decidido"] or len(mejoras) < CUADROS_PARA_DECIDIR or len(filtros) < CUADROS_PARA_DECIDIR:
                return
            medidas["decidido"] = True
            # De a uno, la mejora hace 1/mejora cuadros por segundo y el filtro, ACELERACION_FILTRO/filtro.
            if max(mejoras) * ACELERACION_FILTRO > sum(filtros) / len(filtros):
                cupo.fijar(hilos_mejora)

        def trabajo_mejorado(mejorado: np.ndarray, indice: int):
            if cancelado():
                raise Cancelado()
            inicio = time.perf_counter()
            listo = procesar_cuadro_seguro(mejorado, pila, indice, 1.0, cancelado)
            if len(medidas["filtro"]) < CUADROS_PARA_DECIDIR:
                medidas["filtro"].append(time.perf_counter() - inicio)
                decidir()
            del mejorado
            vf = av.VideoFrame.from_ndarray(listo, format="rgb24")
            return vf.reformat(format=formato_pixel, dst_colorspace=dst, dst_color_range="MPEG",
                               interpolation=_flags())

        def paso_mejora(actual: np.ndarray, vecinos: list, indice: int):
            """En un hilo de la mejora: mejora un cuadro con sus vecinos y lo manda al filtro."""
            with cupo:
                if cancelado():
                    raise Cancelado()
                inicio = time.perf_counter()
                mejorado = mejorar_cuadro(actual, vecinos, ancho, alto, mejora)
                if len(medidas["mejora"]) < CUADROS_PARA_DECIDIR:
                    medidas["mejora"].append(time.perf_counter() - inicio)
            decidir()
            del actual, vecinos
            return pool.submit(trabajo_mejorado, mejorado, indice)

        estado = {"hechos": 0, "ultimo_pts": -1, "primero": None, "fin_video": 0.0}

        def escribir(item) -> None:
            futuro, t_salida = item
            vf = futuro.result()
            pts = int(round(t_salida / tb))
            if pts <= estado["ultimo_pts"]:
                pts = estado["ultimo_pts"] + 1
            estado["ultimo_pts"] = pts
            estado["fin_video"] = max(estado["fin_video"], t_salida + 1.0 / fps)
            vf.pts = pts
            vf.time_base = tb
            for paquete in ov.encode(vf):
                destino.mux(paquete)
            if escritor is not None:
                bombear(round((t_salida + 1.0) * frecuencia))
            estado["hechos"] += 1
            if progreso is not None:
                hechos = estado["hechos"]
                ahora = time.perf_counter()
                if estado["primero"] is None:
                    estado["primero"] = (ahora, hechos)
                t0, h0 = estado["primero"]
                restante = None
                if hechos - h0 >= 2 and ahora > t0:
                    velocidad = (hechos - h0) / (ahora - t0)
                    restante = max(0.0, (max(total, hechos) - hechos) / velocidad)
                progreso(hechos, max(total, hechos), restante)

        en_vuelo = hilos + 2
        indice_tramo = 0
        ultimo_t_video: Optional[float] = None
        tramo_mejora = -1  # el tramo de los cuadros que están en la ventana de vecinos
        en_vuelo_mejora = hilos_mejora + EN_VUELO_MEJORA

        def recoger_mejora(todo: bool = False) -> None:
            """Pasa a la cola de escritura lo que ya se mejoró (en orden) y escribe lo que sobra. Sin
            ``todo``, deja unos cuadros en la mejora para que sus hilos no se queden esperando."""
            while en_mejora and (todo or len(en_mejora) > en_vuelo_mejora):
                paso, t_salida = en_mejora.popleft()
                pendientes.append((paso.result(), t_salida))
                while len(pendientes) >= en_vuelo:
                    escribir(pendientes.popleft())

        def mandar_mejora(listos: list) -> None:
            """Cuadros que ya tienen sus vecinos: a los hilos de la mejora, en orden."""
            for actual, vecinos, (indice, t_salida) in listos:
                en_mejora.append((hilo_mejora.submit(paso_mejora, actual, vecinos, indice), t_salida))
            recoger_mejora()

        for paquete in contenedor.demux(vs):
            if cancelado():
                raise Cancelado()
            for cuadro in paquete.decode():
                t = _tiempo_cuadro(cuadro)
                if t is None:
                    t = (ultimo_t_video + 1.0 / fps) if ultimo_t_video is not None else info.inicio
                ultimo_t_video = t
                t -= info.inicio
                if t >= fin_total - eps:
                    break
                while indice_tramo < len(con_offset) and t >= con_offset[indice_tramo][1] - eps:
                    indice_tramo += 1
                if indice_tramo >= len(con_offset):
                    break
                a, _b, desplazado = con_offset[indice_tramo]
                if t < a - eps:
                    continue  # parte borrada
                if ventana is None:
                    futuro = pool.submit(trabajo, cuadro, indice_en(t, fps))
                    pendientes.append((futuro, max(0.0, t - a + desplazado)))
                    while len(pendientes) >= en_vuelo:
                        escribir(pendientes.popleft())
                    continue
                if indice_tramo != tramo_mejora:
                    # Otro tramo conservado: los vecinos no cruzan lo borrado.
                    mandar_mejora(ventana.cortar())
                    tramo_mejora = indice_tramo
                rgb = _a_rgb(cuadro, rotacion, *lectura)
                del cuadro
                mandar_mejora(ventana.agregar(rgb, (indice_en(t, fps), max(0.0, t - a + desplazado))))
            else:
                continue
            break  # se llegó al final del último tramo
        if ventana is not None:
            mandar_mejora(ventana.cortar())  # los últimos, sin vecinos de adelante
            recoger_mejora(todo=True)
        while pendientes:
            if cancelado():
                raise Cancelado()
            escribir(pendientes.popleft())
        for paquete in ov.encode(None):
            destino.mux(paquete)
        # La duración real es la del video escrito (el contenedor puede declarar algo más por el audio).
        fin = min(estado["fin_video"], duracion_total + 1.0 / fps) if estado["hechos"] else duracion_total
        if escritor is not None:
            bombear(escritor.total)
            escritor.terminar(round(fin * frecuencia))
        destino.close()
        destino = None
        if detalle is not None and mejora is not None:
            detalle["hilos_mejora"] = cupo.n
        return estado["hechos"], escritor is not None, fin
    finally:
        for futuro, _t in pendientes:
            futuro.cancel()
        if hilo_mejora is not None:
            for paso, _t in en_mejora:
                paso.cancel()
            hilo_mejora.shutdown(wait=True, cancel_futures=True)  # antes que el filtro: le manda trabajo
        pool.shutdown(wait=True, cancel_futures=True)
        if destino is not None:
            try:
                destino.close()
            except Exception:
                pass
        if mezcla is not None:
            mezcla.cerrar()
        contenedor.close()


__all__ = [
    "EXTENSIONES_VIDEO", "RESOLUCIONES", "CALIDADES", "CODIFICADORES_H264",
    "InfoVideo", "info_video", "indice_en", "tiempo_de", "LectorVideo", "cuadro_en", "miniaturas",
    "cerrar_lectores", "Segmento", "EdicionVideo", "normalizar_tramos", "separar_capa", "procesar_cuadro",
    "procesar_cuadro_seguro",
    "tamano_salida", "elegir_codificador", "ruta_salida_video", "hilos_por_defecto", "ResultadoVideo",
    "exportar_video",
    # Sonido de otro archivo (ida y vuelta con el modo Audio)
    "ALINEADOS", "AudioExterno", "validar_audio_externo", "silencios_en_resultado", "sonido_a_medir",
    "LectorDesdeCero", "exportar_sonido", "carpeta_temporal", "ruta_temporal_sonido", "limpiar_temporales",
    "DIAS_TEMPORALES",
    # Mejorar calidad (sin IA)
    "AjustesMejora", "tamano_lectura", "tiempos_vecinos", "VentanaVecinos", "HILOS_MEJORA",
]
