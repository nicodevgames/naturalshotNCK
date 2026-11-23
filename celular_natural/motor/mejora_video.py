"""Mejorar calidad de video sin IA: vecinos, cuadraditos, agrandar y enfocar.

Pensado para videos chicos (480p o menos) y muy comprimidos. Lo acordado con el
dueño: un 480p muy comprimido queda como **un buen 720p**, no como un 4K. No usa
modelos ni redes neuronales: solo OpenCV y numpy. No depende de la interfaz.

Cada cuadro, en orden
---------------------
Todo se hace en YCrCb: la luminancia (Y) lleva el detalle y el color (Cr, Cb)
va aparte, a media resolución (en un video 4:2:0 ya viene así).

1. **Cuadros vecinos** (superresolución multicuadro). Los cuadros t-2…t+2 se
   alinean con el actual (t) con flujo óptico DIS de OpenCV (preset ULTRAFAST
   con parches de 16 px), calculado a la resolución de entrada sobre la
   luminancia apenas desenfocada (σ = 0,7: así el aliasing de los detalles
   finos y los bloques engañan menos al flujo). Al de DIS se le suma una
   versión robusta (promedio por bloques de 16 px y mediana entre bloques), más
   precisa para el movimiento de cámara; donde el de DIS alinea claramente
   mejor (algo que se mueve por su cuenta) manda el de DIS.

   * **Pesos robustos:** después de alinear se mide el error cuadrático medio
     local contra el actual (sobre la luminancia apenas desenfocada, en una
     ventana de ≈ 6×6 píxeles). Hasta 3 niveles el
     vecino cuenta entero; desde 10-18 (según ``vecinos``) no cuenta nada. Así
     una oclusión, algo que el flujo no siguió o un cambio de luz no dejan
     fantasmas.
   * **Corte de escena:** si en promedio el vecino no coincide (confianza media
     menor que 0,35) se descarta entero y se usa solo el cuadro actual.
   * **En la grilla grande:** cada vecino se remapea DIRECTO a la resolución de
     salida con su flujo agrandado (``cv2.remap`` cúbico). Antes se le resta
     un poco de laplaciano en los bordes fuertes, que compensa lo blanda que es
     la cúbica: rinde más que Lanczos y cuesta la mitad. Como cada cuadro cayó
     corrido una fracción de píxel, el promedio recupera detalle real y baja el
     ruido de la compresión, en vez de promediar versiones ya borroneadas.
   * ``vecinos`` regula el peso (0 = no se usan; 1 = cuentan como el actual) y
     cuánta diferencia se tolera. Los de distancia 2 pesan un 75 %.
2. **Quitar cuadraditos:** filtro bilateral sobre la luminancia de cada cuadro,
   con el cambio limitado a pocos niveles (±4 con 0,5) y solo donde hay
   artefactos: zonas planas (escalones de los bloques) y alrededor de los
   bordes fuertes (el "mosquito"). La textura de amplitud media (pasto, pelo,
   tela) no se toca: el bilateral la dejaba plástica. El color, ya promediado
   entre los cuadros alineados, pasa por un bilateral de 3 canales (los bordes
   de luminancia lo frenan) que borra las manchas de color en bloques.
3. **Agrandar:** el cuadro actual con Lanczos (``cv2.INTER_LANCZOS4``) y los
   vecinos como se dijo arriba, todos combinados en la grilla de salida. El
   color se agranda con cúbica.
4. **Enfocar:** máscara de enfoque (σ = 0,6 píxeles de entrada) solo donde hay
   bordes (gradiente de la luminancia limpia entre 4 y 16 niveles por píxel:
   las zonas planas, con su ruido, quedan igual) y con límite contra halos: lo
   que se pasa del mínimo o el máximo del vecindario (≈ 2 píxeles de entrada)
   se achica al 40 % (cortarlo del todo dejaba la textura en manchas planas).
   ``nitidez`` regula la cantidad.

Si la salida es más chica que la entrada se trabaja a la resolución de entrada
y al final se achica con ``INTER_AREA``. Con ``activa=False`` (o en cuadros de
menos de 8 px de lado) solo se cambia el tamaño (Lanczos), sin tocar nada más.

Vista previa = exportación
--------------------------
``mejorar_cuadro`` es una función pura y determinista: con los mismos cuadros da
el mismo resultado, bit a bit. ``MejoradorVideo`` (para exportar) la llama con
los vecinos de cada cuadro dentro de su tramo, así que lo que se ve en la vista
previa es lo que sale en el archivo. Se puede llamar desde varios hilos a la vez,
también desde los hilos internos de este módulo (ahí alinea los vecinos en el
mismo hilo, para no trabarse). La memoria de cuadros preparados (hasta
``CACHE_PREPARADOS`` bytes, o ``CACHE_MINIMO`` cuadros si son grandes) se busca
por contenido, así que no cambia el resultado: solo evita repetir trabajo. Se
libera con ``vaciar_memoria()``, que ``motor/video.py`` llama al cerrar el video
o el editor.

Resultados y tiempos
--------------------
Con el video de prueba de ``tests/test_mejora_video.py`` (1080p sintético con
paneo de subpíxel, achicado a 854×480 y comprimido con H.264 a ≈ 300 kbit/s),
contra la verdad, promedio de 8 cuadros (PSNR en RGB / SSIM de la luminancia):

                   a 1920×1080         a 1280×720
    bicúbico       22,76 dB / 0,863    25,67 dB / 0,920
    sin vecinos    23,46 dB / 0,874    26,31 dB / 0,928
    con vecinos    23,91 dB / 0,884    26,71 dB / 0,934

Tiempos en esta PC (Ryzen 7 5700, 8 núcleos), 854×480 de entrada, medidos como
al exportar (cada llamada trae un cuadro nuevo y cuatro ya preparados), con poca
carga de otros programas: a 1280×720, ≈ 69 ms por cuadro por defecto y ≈ 79 ms
con todo al máximo (mediana; el mejor, ≈ 63 ms); a 1920×1080, ≈ 112 y ≈ 118 ms.
Con otros procesos usando la mitad de la CPU suben ≈ 15-20 %. En un salto de la
vista previa (nada preparado) la primera llamada tarda ≈ 10 % más. Sin vecinos,
≈ 25 ms a 720p y 40 ms a 1080p.

Cómo se reparte: los 4 vecinos se preparan y alinean en hilos (OpenCV suelta el
GIL) mientras el hilo principal prepara el actual; cada cuadro preparado se
guarda por su contenido (``_preparado``), porque se usa cinco veces; el hilo
principal lleva cada vecino a la grilla grande apenas llega (≈ 8 ms cada uno a
1080p). Hacer eso en los hilos de los vecinos, o con mapas de punto fijo
(``cv2.convertMaps`` a ``CV_16SC2``), se probó y era más lento. Una entrada más
grande cuesta más en proporción a sus píxeles.
"""

from __future__ import annotations

import math
import threading
import zlib
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import NamedTuple, Optional, Sequence, Union

import cv2
import numpy as np

RADIO_VECINOS = 2  # se usan t-2, t-1, t+1 y t+2
RESOLUCIONES_MEJORA: dict[str, int] = {"720p": 720, "1080p": 1080}  # lado corto

# Flujo óptico (a la resolución de entrada).
PRESET_FLUJO = cv2.DISOPTICAL_FLOW_PRESET_ULTRAFAST
PARCHE_FLUJO = 16  # px: parches grandes = menos errores en texto y líneas finas
PASO_PARCHE = 8
SIGMA_GUIA_FLUJO = 0.7  # desenfoque previo: el aliasing y los bloques engañan menos al flujo
BLOQUE_FLUJO_SUAVE = 16  # px: tamaño de los bloques del flujo robusto
MEDIANA_BLOQUES = 3  # mediana de 3×3 bloques
VENTAJA_FLUJO_FINO = 2.0  # DIS reemplaza al robusto donde su error es menos de la mitad
LADO_MINIMO_VECINOS = 32  # px: en cuadros más chicos no se usan vecinos
LADO_MINIMO_MEJORA = 8  # px: en cuadros más chicos que esto solo se cambia el tamaño
LADO_LARGO_MAXIMO = 4096  # px: ``tamano_mejorado`` no da salidas más largas (4K DCI)
CACHE_PREPARADOS = 96 * 2 ** 20  # bytes de cuadros ya preparados que se guardan (≈ 30 de 480p)...
CACHE_MINIMO = 8  # ...pero siempre al menos estos cuadros (3 a la vez con sus vecinos), salvo...
CACHE_MAXIMO = 512 * 2 ** 20  # ...que pasen de esto (entradas enormes, como un 4K)

# Pesos robustos (error cuadrático medio local, en niveles de 0 a 255).
ERROR_CONFIABLE = 3.0  # hasta acá el vecino cuenta entero
ERROR_DESCARTE = 10.0  # desde acá no cuenta nada (con vecinos = 0)...
ERROR_DESCARTE_EXTRA = 8.0  # ...más esto por ``vecinos`` (18 con vecinos = 1)
CONFIANZA_CORTE = 0.35  # confianza media menor: corte de escena, el vecino no se usa
PESO_LEJANO = 0.75  # peso relativo de t±2 frente a t±1
REALCE_VECINO = 0.12  # laplaciano restado antes del remap cúbico (compensa su blandura)
REALCE_DESDE = 40.0  # el realce va solo donde |laplaciano| pasa de esto...
REALCE_HASTA = 80.0  # ...y entero desde acá: bordes fuertes, no la textura (ahí sumaba ruido)

# Quitar cuadraditos (luminancia, a la resolución de entrada).
BILATERAL_COLOR = 40.0  # × cuadraditos
BILATERAL_ESPACIO = 2.0
CAMBIO_MAXIMO = 8.0  # niveles × cuadraditos: el bilateral no mueve más que esto
RANGO_BORDE_FUERTE = 48  # máximo - mínimo en 3×3 desde el que hay un borde fuerte...
LADO_CERCA = 7  # ...y su "mosquito" llega a ≈ 3 píxeles
RANGO_PLANO = 10  # por debajo, zona plana (donde se ven los escalones de los bloques)

# Color (a media resolución): bilateral de 3 canales, así los bordes de luminancia frenan el suavizado.
COLOR_BILATERAL = 40.0  # × cuadraditos
COLOR_ESPACIO = 3.0

# Enfoque.
SIGMA_ENFOQUE = 0.6  # en píxeles de entrada
CANTIDAD_ENFOQUE = 2.0  # × nitidez
BORDE_DESDE = 4.0  # gradiente (niveles por píxel de entrada) donde empieza a enfocar...
BORDE_HASTA = 16.0  # ...y donde ya enfoca entero
EXCESO_PERMITIDO = 0.4  # fracción que queda de lo que se pasa del mínimo/máximo local


def _fraccion(valor, defecto: float) -> float:
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return defecto
    if not math.isfinite(v):
        return defecto
    return min(1.0, max(0.0, v))


@dataclass(frozen=True)
class AjustesMejora:
    """Cómo se mejora el video. Por defecto está apagada (no cambia nada).

    activa       prende la mejora. Apagada, el cuadro solo cambia de tamaño.
    cuadraditos  0..1: cuánto se quitan los bloques y el "mosquito" de la compresión.
    nitidez      0..1: cuánto se enfocan los bordes.
    vecinos      0..1: cuánto pesan los cuadros vecinos (0 = no se usan).

    Inmutable y con los valores ya acomodados (de 0 a 1; NaN, infinito o algo
    que no es un número vuelve al valor por defecto): cada cambio devuelve otro,
    así deshacer es guardar estados. Se puede guardar con pickle.
    """

    activa: bool = False
    cuadraditos: float = 0.5
    nitidez: float = 0.5
    vecinos: float = 0.5

    def __post_init__(self):
        object.__setattr__(self, "activa", bool(self.activa))
        object.__setattr__(self, "cuadraditos", _fraccion(self.cuadraditos, 0.5))
        object.__setattr__(self, "nitidez", _fraccion(self.nitidez, 0.5))
        object.__setattr__(self, "vecinos", _fraccion(self.vecinos, 0.5))

    def sin_cambios(self) -> bool:
        """True si el video sale igual (apagada)."""
        return not self.activa

    def con(self, **cambios) -> "AjustesMejora":
        """Otro con esos campos cambiados (acomodados igual que al crearlo)."""
        return replace(self, **cambios)


def tamano_mejorado(ancho: int, alto: int, resolucion: Union[str, int]) -> tuple[int, int]:
    """(ancho, alto) de salida para llevar un video ``ancho``×``alto`` a ``resolucion``.

    ``resolucion`` es "720p", "1080p" o el lado corto en píxeles. Agranda o
    achica hasta que el lado corto mida eso, conserva la proporción y la
    orientación (un vertical de 480×854 a "1080p" queda en 1080×1920) y deja
    lados pares, como pide yuv420p. Si un múltiplo de 8 queda a menos de 0,2 %
    de la proporción exacta se prefiere (854×480 a "1080p" da 1920×1080 y no
    1922×1080), porque los codificadores trabajan mejor así. Si el lado largo
    pasara de ``LADO_LARGO_MAXIMO`` (proporciones absurdas, como 1×1000), da
    ``ValueError``.
    """
    lado = RESOLUCIONES_MEJORA.get(resolucion) if isinstance(resolucion, str) else resolucion
    try:
        lado, ancho, alto = int(lado), int(ancho), int(alto)
    except (TypeError, ValueError):
        raise ValueError(f"resolución desconocida: {resolucion!r} (válidas: 720p, 1080p o un número)") from None
    if lado < 2 or ancho < 1 or alto < 1:
        raise ValueError(f"tamaño inválido: {ancho}x{alto} a {resolucion!r}")
    lado -= lado % 2
    corto, largo = min(ancho, alto), max(ancho, alto)
    exacto = largo * lado / corto
    par = max(2, 2 * math.floor(exacto / 2 + 0.5))
    multiplo8 = max(8, 8 * math.floor(exacto / 8 + 0.5))
    largo2 = multiplo8 if abs(multiplo8 - exacto) <= max(2.0, 0.002 * exacto) else par
    if largo2 > LADO_LARGO_MAXIMO:
        raise ValueError(f"proporción demasiado extrema: {ancho}x{alto} a {resolucion!r} daría un lado de "
                         f"{largo2} px (máximo {LADO_LARGO_MAXIMO})")
    return (largo2, lado) if ancho >= alto else (lado, largo2)


# ---------------------------------------------------------------------------
# Piezas
# ---------------------------------------------------------------------------

_POOL: Optional[ThreadPoolExecutor] = None
_POOL_CANDADO = threading.Lock()
_HILO = threading.local()  # ``del_pool`` es True en los hilos de ``_pool()``


def _marcar_hilo() -> None:
    _HILO.del_pool = True


def _pool() -> ThreadPoolExecutor:
    """Hilos para los vecinos (uno por vecino). Se crean la primera vez."""
    global _POOL
    with _POOL_CANDADO:
        if _POOL is None:
            _POOL = ThreadPoolExecutor(max_workers=2 * RADIO_VECINOS, thread_name_prefix="mejora_video",
                                       initializer=_marcar_hilo)
        return _POOL


class _Senal:
    """El cuadro actual preparado, que el hilo principal les pasa a los hilos de los vecinos.

    Si el hilo principal falla antes de tenerlo, lo avisa con ``fallar`` y los
    hilos que esperaban terminan con error: nunca queda uno esperando algo que no
    va a llegar."""

    def __init__(self):
        self._evento = threading.Event()
        self._valor = None
        self._error: Optional[BaseException] = None

    def dar(self, valor) -> None:
        self._valor = valor
        self._evento.set()

    def fallar(self, error: BaseException) -> None:
        self._error = error
        self._evento.set()

    def esperar(self):
        self._evento.wait()
        if self._error is not None:
            raise RuntimeError("no se pudo preparar el cuadro actual") from self._error
        return self._valor


def _flujo(guia_t: np.ndarray, guia_k: np.ndarray) -> np.ndarray:
    """Flujo óptico DIS de t hacia el vecino: guia_t(x) ≈ guia_k(x + flujo(x)).

    Un objeto DIS nuevo cada vez (cuesta ≈ 0,1 ms): uno reusado arrastra estado de
    la llamada anterior y el resultado deja de ser determinista."""
    dis = cv2.DISOpticalFlow_create(PRESET_FLUJO)
    dis.setPatchSize(PARCHE_FLUJO)
    dis.setPatchStride(PASO_PARCHE)
    return dis.calc(guia_t, guia_k, None)


@lru_cache(maxsize=8)
def _grilla(h: int, w: int) -> np.ndarray:
    """Coordenadas (x, y) de cada píxel, para armar mapas de ``cv2.remap``. Solo lectura."""
    gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
    g = cv2.merge([gx, gy])
    g.flags.writeable = False
    return g


def _validar(img, nombre: str) -> np.ndarray:
    if not isinstance(img, np.ndarray) or img.dtype != np.uint8 or img.ndim != 3 or img.shape[2] != 3:
        raise ValueError(f"{nombre}: se espera RGB uint8 (alto, ancho, 3)")
    if img.shape[0] < 1 or img.shape[1] < 1:
        raise ValueError(f"{nombre}: imagen vacía")
    return np.ascontiguousarray(img)


def _cambiar_tamano(rgb: np.ndarray, ancho: int, alto: int) -> np.ndarray:
    if rgb.shape[1] == ancho and rgb.shape[0] == alto:
        return rgb.copy()
    return cv2.resize(rgb, (ancho, alto), interpolation=cv2.INTER_LANCZOS4)


def _suavizar_pasos(x: np.ndarray, desde: float, hasta: float) -> np.ndarray:
    """0 por debajo de ``desde``, 1 por encima de ``hasta`` y curva suave (smoothstep) entre medio."""
    t = np.clip((x - desde) * (1.0 / (hasta - desde)), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


class _Cuadro(NamedTuple):
    ycc: np.ndarray  # YCrCb uint8 (h, w, 3)
    y: np.ndarray  # luminancia sin cuadraditos, float32 (h, w)
    guia: np.ndarray  # luminancia apenas desenfocada, uint8: para el flujo


def _preparar(rgb: np.ndarray, cuadraditos: float) -> _Cuadro:
    """Pasa a YCrCb y quita los cuadraditos de la luminancia (bilateral con el cambio limitado)."""
    ycc = cv2.cvtColor(rgb, cv2.COLOR_RGB2YCrCb)
    y8 = np.ascontiguousarray(ycc[..., 0])
    guia = cv2.GaussianBlur(y8, (0, 0), SIGMA_GUIA_FLUJO)
    if cuadraditos <= 0:
        return _Cuadro(ycc, y8.astype(np.float32), guia)
    filtrada = cv2.bilateralFilter(y8, 5, BILATERAL_COLOR * cuadraditos, BILATERAL_ESPACIO)
    cambio = cv2.subtract(filtrada, y8, dtype=cv2.CV_32F)
    tope = CAMBIO_MAXIMO * cuadraditos
    np.clip(cambio, -tope, tope, out=cambio)
    cambio = cv2.multiply(cambio, _zonas_con_artefactos(y8), scale=1.0 / 255.0, dtype=cv2.CV_32F)
    return _Cuadro(ycc, cv2.add(cambio, y8, dtype=cv2.CV_32F), guia)


_CACHE: "OrderedDict[tuple, _Cuadro]" = OrderedDict()
_CACHE_BYTES = 0
_CACHE_CANDADO = threading.Lock()
_EN_CURSO: dict = {}  # clave -> threading.Event de una preparación que está haciendo otro hilo
_GENERACION = 0  # sube con cada ``vaciar_memoria``: lo que se estaba preparando antes no se guarda


def vaciar_memoria() -> None:
    """Libera la memoria de cuadros preparados (hasta ``CACHE_PREPARADOS``). Se llama al cerrar el
    video o el editor (``motor/video.py``, ``cerrar_lectores``). No cambia ningún resultado: la
    próxima vez, simplemente se vuelven a preparar."""
    global _CACHE_BYTES, _GENERACION
    with _CACHE_CANDADO:
        _CACHE.clear()
        _CACHE_BYTES = 0
        _GENERACION += 1


def _preparado(rgb: np.ndarray, cuadraditos: float) -> _Cuadro:
    """``_preparar`` con memoria: cada cuadro de un video se usa cinco veces (como actual y
    como vecino de los otros cuatro), así que se prepara una sola.

    La clave es el contenido (CRC32 y Adler32 de los bytes: 64 bits, ≈ 0,4 ms en
    480p) y no el objeto: si alguien reusa o modifica un arreglo, simplemente no
    coincide. El resultado es exactamente el de ``_preparar``, salvo una colisión
    de 64 bits (dos cuadros distintos con los mismos dos códigos): la función sigue
    siendo pura. Los arreglos guardados quedan de solo lectura.

    Si otro hilo ya está preparando el mismo cuadro (al exportar de a varios cuadros
    a la vez pasa seguido), se espera a que termine en vez de repetirlo."""
    global _CACHE_BYTES
    datos = memoryview(rgb).cast("B")
    clave = (rgb.shape, float(cuadraditos), zlib.crc32(datos), zlib.adler32(datos))
    while True:
        with _CACHE_CANDADO:
            cuadro = _CACHE.get(clave)
            if cuadro is not None:
                _CACHE.move_to_end(clave)
                return cuadro
            evento = _EN_CURSO.get(clave)
            mio = evento is None
            if mio:
                evento = _EN_CURSO[clave] = threading.Event()
                generacion = _GENERACION
        if mio:
            break
        evento.wait()  # después se vuelve a mirar: si el otro falló o se vació la memoria, lo prepara este
    try:
        cuadro = _preparar(rgb, cuadraditos)
        for a in cuadro:
            a.flags.writeable = False
        with _CACHE_CANDADO:
            if generacion == _GENERACION and clave not in _CACHE:
                _CACHE[clave] = cuadro
                _CACHE_BYTES += sum(a.nbytes for a in cuadro)
                while len(_CACHE) > 1 and (
                        (_CACHE_BYTES > CACHE_PREPARADOS and len(_CACHE) > CACHE_MINIMO)
                        or _CACHE_BYTES > CACHE_MAXIMO):
                    _, viejo = _CACHE.popitem(last=False)
                    _CACHE_BYTES -= sum(a.nbytes for a in viejo)
    finally:
        with _CACHE_CANDADO:
            _EN_CURSO.pop(clave, None)
        evento.set()
    return cuadro


def _zonas_con_artefactos(y8: np.ndarray) -> np.ndarray:
    """Dónde se quitan los cuadraditos (uint8, 0..255): zonas planas (escalones de los bloques) y
    alrededor de los bordes fuertes (el "mosquito"). En la textura de amplitud media
    (pasto, pelo, tela) no: ahí el bilateral la alisaba y se veía plástica."""
    rango = cv2.morphologyEx(y8, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))  # máximo - mínimo en 3×3
    fuerte = cv2.compare(rango, RANGO_BORDE_FUERTE, cv2.CMP_GT)
    cerca = cv2.dilate(fuerte, np.ones((LADO_CERCA, LADO_CERCA), np.uint8))
    plano = cv2.compare(rango, RANGO_PLANO, cv2.CMP_LT)
    return cv2.blur(cv2.max(cerca, plano), (3, 3))


def _medio(img: np.ndarray) -> np.ndarray:
    """Mitad de resolución (promedio de 2×2)."""
    h, w = img.shape[:2]
    return cv2.resize(img, (max(1, w // 2), max(1, h // 2)), interpolation=cv2.INTER_AREA)


def _bloques_flujo(flujo: np.ndarray) -> np.ndarray:
    """Flujo robusto, uno por bloque: promedio por bloques y mediana entre bloques vecinos."""
    h, w = flujo.shape[:2]
    hb, wb = max(1, round(h / BLOQUE_FLUJO_SUAVE)), max(1, round(w / BLOQUE_FLUJO_SUAVE))
    bloques = cv2.resize(flujo, (wb, hb), interpolation=cv2.INTER_AREA)
    if min(hb, wb) >= MEDIANA_BLOQUES:
        bloques = cv2.merge([cv2.medianBlur(np.ascontiguousarray(bloques[..., c]), MEDIANA_BLOQUES)
                             for c in range(2)])
    return bloques


def _error_alineado(y_k: np.ndarray, mapa: np.ndarray, y_t_medio: np.ndarray) -> np.ndarray:
    """Error cuadrático medio local entre el vecino llevado al actual con ``mapa`` y el actual.

    Se mide sobre las guías del flujo (luminancia apenas desenfocada, uint8): el
    desenfoque saca el ruido que la interpolación agrega en la textura fina, que
    si no se confunde con desalineación. Se alinea a la resolución de entrada y
    recién después se pasa a media resolución (promedio de 2×2): remapear la
    imagen ya achicada agrega aliasing en el texto. La ventana de 3×3 a media
    resolución cubre ≈ 6×6 píxeles."""
    alineado = cv2.remap(y_k, mapa, None, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    d = cv2.subtract(_medio(alineado), y_t_medio, dtype=cv2.CV_32F)
    return cv2.blur(cv2.multiply(d, d), (3, 3))


class _Medio(NamedTuple):
    """El cuadro actual a media resolución (para pesos y color)."""
    guia: np.ndarray  # luminancia apenas desenfocada, uint8
    ycc: np.ndarray  # YCrCb uint8


class _Vecino(NamedTuple):
    mapa: np.ndarray  # (h, w, 2) float32: dónde buscar cada píxel del actual en el vecino
    y_realzada: np.ndarray  # (h, w) float32: luminancia del vecino, lista para el remap cúbico
    peso: np.ndarray  # (h/2, w/2) float32: peso del vecino en cada lugar (0 = no se usa)
    ycc: np.ndarray  # (h/2, w/2, 3) uint8: el vecino alineado, a media resolución (para el color)


def _alinear(senal: _Senal, rgb_k: np.ndarray, peso: float, ajustes: AjustesMejora) -> Optional[_Vecino]:
    """Prepara un vecino: flujo, pesos robustos y corte de escena. None si no sirve.

    Corre en un hilo aparte (uno por vecino): prepara su cuadro mientras el hilo
    principal prepara el actual, que recibe por ``senal`` ((_Cuadro, _Medio)).

    Lo que va a la grilla grande (``_a_la_grilla``) lo hace el hilo principal, a
    medida que llega cada vecino: probado, hacerlo acá era 6-17 ms más lento por
    cuadro, porque esas operaciones ya usan todos los núcleos por dentro y cuatro
    a la vez se pisan el ancho de banda de la memoria."""
    k = _preparado(rgb_k, ajustes.cuadraditos)
    actual, medio = senal.esperar()
    h, w = actual.y.shape
    grilla = _grilla(h, w)
    # (En los hilos conviene numpy "en el lugar" para lo elemental: las funciones de OpenCV
    # se reparten en sus propios hilos y, con cuatro vecinos a la vez, se estorban.)
    mapa_fino = _flujo(actual.guia, k.guia)
    bloques = _bloques_flujo(mapa_fino)
    mapa_fino += grilla
    mapa_suave = cv2.resize(bloques, (w, h), interpolation=cv2.INTER_LINEAR)
    mapa_suave += grilla
    e_fino = _error_alineado(k.guia, mapa_fino, medio.guia)
    e_suave = _error_alineado(k.guia, mapa_suave, medio.guia)

    # Donde el flujo de DIS alinea claramente mejor (algo que se mueve por su cuenta) manda
    # ese; en el resto, el robusto (para el movimiento de cámara es más preciso).
    piso = ERROR_CONFIABLE * ERROR_CONFIABLE
    eleccion = cv2.blur(np.clip((e_suave - (VENTAJA_FLUJO_FINO * e_fino + piso)) / (e_fino + piso), 0.0, 1.0),
                        (3, 3))
    if float(eleccion.max()) > 0.0:
        error = cv2.blendLinear(e_fino, e_suave, eleccion, 1.0 - eleccion)
        s = cv2.resize(eleccion, (w, h), interpolation=cv2.INTER_LINEAR)
        mapa = cv2.blendLinear(mapa_fino, mapa_suave, s, 1.0 - s)
    else:  # el robusto alcanza en todo el cuadro (lo común con movimiento de cámara)
        error, mapa = e_suave, mapa_suave

    # Confianza: 1 hasta ERROR_CONFIABLE, 0 desde el de descarte; nada fuera del cuadro.
    descarte = ERROR_DESCARTE + ERROR_DESCARTE_EXTRA * ajustes.vecinos
    confianza = _suavizar_pasos(cv2.sqrt(cv2.max(error, 0.0)), descarte, ERROR_CONFIABLE)
    dentro = _medio(cv2.inRange(mapa, (-0.5, -0.5), (w - 0.5, h - 0.5)))
    confianza = cv2.multiply(confianza, dentro.astype(np.float32), scale=1.0 / 255.0)
    if float(confianza.mean()) < CONFIANZA_CORTE:
        return None  # corte de escena (o el vecino no coincide casi en ningún lado)
    confianza *= peso

    # Luminancia realzada solo en las estructuras fuertes (bordes de texto, líneas finas).
    y_realzada = cv2.Laplacian(k.y, cv2.CV_32F, ksize=1)
    fuerza = np.abs(y_realzada)
    fuerza -= REALCE_DESDE
    fuerza *= 1.0 / (REALCE_HASTA - REALCE_DESDE)
    np.clip(fuerza, 0.0, 1.0, out=fuerza)
    y_realzada *= fuerza
    y_realzada *= -REALCE_VECINO
    y_realzada += k.y
    ycc = _medio(cv2.remap(k.ycc, mapa, None, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE))
    return _Vecino(mapa, y_realzada, confianza, ycc)


def _a_la_grilla(v: _Vecino, W: int, H: int) -> np.ndarray:
    """El vecino remapeado directo a la grilla grande (cúbica) y multiplicado por su peso."""
    h, w = v.y_realzada.shape
    mapa = v.mapa if (W, H) == (w, h) else cv2.resize(v.mapa, (W, H), interpolation=cv2.INTER_LINEAR)
    remapeado = cv2.remap(v.y_realzada, mapa, None, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return cv2.multiply(remapeado, cv2.resize(v.peso, (W, H), interpolation=cv2.INTER_LINEAR))


def _mapa_bordes(y_entrada: np.ndarray, W: int, H: int) -> np.ndarray:
    """Dónde enfocar (0..1, en la grilla grande): gradiente de la luminancia limpia entre
    BORDE_DESDE y BORDE_HASTA niveles por píxel de entrada."""
    gx = cv2.Sobel(y_entrada, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(y_entrada, cv2.CV_32F, 0, 1, ksize=3)
    bordes = _suavizar_pasos(cv2.magnitude(gx, gy) * 0.25, BORDE_DESDE, BORDE_HASTA)
    if bordes.shape != (H, W):
        bordes = cv2.resize(bordes, (W, H), interpolation=cv2.INTER_LINEAR)
    return bordes


def _enfocar(y: np.ndarray, bordes: np.ndarray, escala: float, nitidez: float) -> np.ndarray:
    """Máscara de enfoque solo en bordes, con el exceso sobre el mínimo/máximo local achicado."""
    desenfoque = cv2.GaussianBlur(y, (0, 0), SIGMA_ENFOQUE * escala)
    lado = 2 * int(math.ceil(escala / 2)) + 1  # vecindario de ≈ 2 píxeles de entrada
    nucleo = cv2.getStructuringElement(cv2.MORPH_RECT, (lado, lado))
    bajo, alto = cv2.erode(y, nucleo), cv2.dilate(y, nucleo)
    detalle = cv2.subtract(y, desenfoque)
    enfocada = cv2.scaleAdd(cv2.multiply(detalle, bordes), CANTIDAD_ENFOQUE * nitidez, y)
    limitada = cv2.min(cv2.max(enfocada, bajo), alto)
    return cv2.addWeighted(enfocada, EXCESO_PERMITIDO, limitada, 1.0 - EXCESO_PERMITIDO, 0.0)


# ---------------------------------------------------------------------------
# Un cuadro
# ---------------------------------------------------------------------------

def mejorar_cuadro(actual: np.ndarray, vecinos: Sequence[Optional[np.ndarray]], ancho: int, alto: int,
                   ajustes: AjustesMejora) -> np.ndarray:
    """Mejora un cuadro y lo lleva a ``ancho``×``alto``.

    actual   RGB uint8 (h, w, 3).
    vecinos  [t-2, t-1, t+1, t+2] (RGB uint8 del mismo tamaño), None donde no hay
             (principio o fin del tramo); también vale una lista vacía.
    Devuelve RGB uint8 (alto, ancho, 3), nuevo. No modifica las entradas.

    Con ``ajustes.activa`` en False solo agranda o achica con Lanczos (o
    devuelve una copia si el tamaño es el mismo). Función pura y determinista:
    la vista previa y la exportación dan lo mismo.
    """
    actual = _validar(actual, "actual")
    ancho, alto = int(ancho), int(alto)
    if ancho < 1 or alto < 1:
        raise ValueError(f"tamaño de salida inválido: {ancho}x{alto}")
    vecinos = list(vecinos)
    if len(vecinos) not in (0, 2 * RADIO_VECINOS):
        raise ValueError(f"se esperan {2 * RADIO_VECINOS} vecinos (o ninguno), llegaron {len(vecinos)}")
    for i, v in enumerate(vecinos):
        if v is not None:
            v = _validar(v, f"vecino {i}")
            if v.shape != actual.shape:
                raise ValueError(f"vecino {i}: tamaño {v.shape[:2]} distinto del actual {actual.shape[:2]}")
            vecinos[i] = v
    h, w = actual.shape[:2]
    if not ajustes.activa or min(h, w) < LADO_MINIMO_MEJORA:
        return _cambiar_tamano(actual, ancho, alto)
    W, H = max(ancho, w), max(alto, h)  # si hay que achicar, se trabaja a la resolución de entrada
    escala = max(W / w, H / h)

    # 1. Vecinos (en hilos): flujo, pesos y corte de escena.
    tareas = []
    if ajustes.vecinos > 0 and vecinos and min(h, w) >= LADO_MINIMO_VECINOS:
        distancias = [d for d in range(-RADIO_VECINOS, RADIO_VECINOS + 1) if d != 0]
        for d, v in zip(distancias, vecinos):
            if v is not None:
                tareas.append((v, ajustes.vecinos * (1.0 if abs(d) == 1 else PESO_LEJANO)))
    senal = _Senal()
    trabajos = []
    en_linea = getattr(_HILO, "del_pool", False)  # llamada desde un hilo del pool: sin hilos (si no, se traba)
    try:
        if not en_linea:
            for v, peso in tareas:
                trabajos.append(_pool().submit(_alinear, senal, v, peso, ajustes))
        # Sin vecinos el cuadro se usa una sola vez: no vale la pena guardarlo.
        t = _preparado(actual, ajustes.cuadraditos) if tareas else _preparar(actual, ajustes.cuadraditos)
        medio = _Medio(_medio(t.guia), _medio(t.ycc))
        senal.dar((t, medio))
    except BaseException as e:
        senal.fallar(e)  # que los hilos que ya arrancaron no se queden esperando
        raise
    # Mientras los hilos trabajan, lo que depende solo del cuadro actual.
    y_hr = cv2.resize(t.y, (W, H), interpolation=cv2.INTER_LANCZOS4)  # siempre una copia nueva
    bordes = _mapa_bordes(t.y, W, H) if ajustes.nitidez > 0 else None

    # 2-3. Luminancia en la grilla grande: (actual + Σ vecino·peso) / (1 + Σ peso). Cada
    # vecino se suma apenas llega (mientras los otros hilos siguen), pero siempre en el
    # mismo orden (t-2, t-1, t+1, t+2): el resultado no depende de los hilos.
    if en_linea:
        resultados = (_alinear(senal, v, peso, ajustes) for v, peso in tareas)
    else:
        resultados = (tr.result() for tr in trabajos)
    vecinos_ok = []
    for a in resultados:
        if a is not None:
            vecinos_ok.append(a)
            y_hr += _a_la_grilla(a, W, H)
    if vecinos_ok:
        inversa = 1.0 / (1.0 + sum(a.peso for a in vecinos_ok))  # a media resolución
        y_hr *= cv2.resize(inversa, (W, H), interpolation=cv2.INTER_LINEAR)

    # Color: a media resolución (en un video 4:2:0 ya viene así), promedio de los cuadros
    # alineados y agrandado suave. El canal 0 después se reemplaza por la luminancia.
    ycc = medio.ycc
    if vecinos_ok:
        mezcla = cv2.multiply(ycc, cv2.merge([inversa] * 3), dtype=cv2.CV_32F)
        for a in vecinos_ok:
            cv2.accumulateProduct(a.ycc.astype(np.float32), cv2.merge([a.peso * inversa] * 3), mezcla)
        ycc = cv2.convertScaleAbs(mezcla)
    if ajustes.cuadraditos > 0:  # quita las manchas de color en bloques de la compresión
        ycc = cv2.bilateralFilter(ycc, 5, COLOR_BILATERAL * ajustes.cuadraditos, COLOR_ESPACIO)
    ycc = cv2.resize(ycc, (W, H), interpolation=cv2.INTER_CUBIC)

    # 4. Enfoque solo en bordes.
    if bordes is not None:
        y_hr = _enfocar(y_hr, bordes, escala, ajustes.nitidez)

    ycc[..., 0] = cv2.convertScaleAbs(cv2.max(y_hr, 0.0))  # redondea y satura a 0..255
    salida = cv2.cvtColor(ycc, cv2.COLOR_YCrCb2RGB)
    if (W, H) != (ancho, alto):
        salida = cv2.resize(salida, (ancho, alto), interpolation=cv2.INTER_AREA)
    return salida


# ---------------------------------------------------------------------------
# Video entero
# ---------------------------------------------------------------------------

class MejoradorVideo:
    """Para exportar: se le dan los cuadros en orden y devuelve los mejorados con
    ``RADIO_VECINOS`` cuadros de retraso.

    Uso::

        m = MejoradorVideo(ajustes, ancho, alto)
        for tramo in tramos_conservados:
            m.reiniciar()  # los vecinos no cruzan cortes (en el primero no hace nada)
            for cuadro in cuadros_del_tramo:
                for listo in m.agregar(cuadro):
                    escribir(listo)
        for listo in m.terminar():
            escribir(listo)

    * ``agregar`` del cuadro n devuelve el cuadro n-2 ya mejorado (los dos
      primeros de cada tramo devuelven nada: todavía faltan sus vecinos de
      adelante).
    * ``reiniciar`` marca un corte: lo que venga después no usa como vecinos los
      cuadros de antes, ni al revés. No se pierde nada: los dos cuadros que
      quedaban del tramo anterior salen en el próximo ``agregar`` (o en
      ``terminar``), antes que los nuevos.
    * ``terminar`` devuelve todo lo que falta y deja el mejorador vacío, listo
      para usar de nuevo.

    Cada cuadro sale exactamente una vez y en orden, igual que con
    ``mejorar_cuadro(cuadro, [t-2, t-1, t+1, t+2], ...)`` con los vecinos de su
    tramo (None en los bordes). Los cuadros se copian al recibirlos.
    """

    def __init__(self, ajustes: AjustesMejora, ancho: int, alto: int):
        self.ajustes = ajustes
        self.ancho, self.alto = int(ancho), int(alto)
        self._ventana: deque = deque()  # últimos cuadros del tramo actual (hasta 2·RADIO + 1)
        self._sin_salir = 0  # cuántos de la ventana (los más nuevos) todavía no salieron
        self._listos: list = []  # mejorados del tramo anterior, esperando salir

    def _mejorar(self, i: int) -> np.ndarray:
        """Mejora el cuadro ``i`` de la ventana con sus vecinos de la ventana."""
        cuadros = self._ventana
        vecinos = []
        for d in range(-RADIO_VECINOS, RADIO_VECINOS + 1):
            if d:
                j = i + d
                vecinos.append(cuadros[j] if 0 <= j < len(cuadros) else None)
        return mejorar_cuadro(cuadros[i], vecinos, self.ancho, self.alto, self.ajustes)

    def agregar(self, rgb: np.ndarray) -> list[np.ndarray]:
        """Suma el próximo cuadro (RGB uint8) y devuelve los que ya quedaron listos.

        Si falla (por ejemplo, falta memoria) queda como si no se hubiera llamado:
        no se pierde nada y se puede reintentar con el mismo cuadro."""
        self._ventana.append(_validar(rgb, "cuadro").copy())
        self._sin_salir += 1
        nuevos = []
        if self._sin_salir > RADIO_VECINOS:
            try:
                nuevos.append(self._mejorar(len(self._ventana) - self._sin_salir))
            except BaseException:
                self._ventana.pop()
                self._sin_salir -= 1
                raise
            self._sin_salir -= 1
            # El próximo en salir necesita RADIO_VECINOS cuadros de atrás: lo anterior sobra.
            while len(self._ventana) - self._sin_salir > RADIO_VECINOS:
                self._ventana.popleft()
        salida = self._listos + nuevos
        self._listos = []  # recién ahora, con todo hecho
        return salida

    def _cerrar_tramo(self) -> list[np.ndarray]:
        """Mejora lo que queda del tramo y lo vacía (solo si todo salió bien)."""
        n = len(self._ventana)
        salida = [self._mejorar(i) for i in range(n - self._sin_salir, n)]
        self._ventana.clear()
        self._sin_salir = 0
        return salida

    def reiniciar(self) -> None:
        """Corte: los vecinos no cruzan de un tramo al otro. No se pierde ningún cuadro."""
        self._listos.extend(self._cerrar_tramo())

    def terminar(self) -> list[np.ndarray]:
        """Devuelve todo lo que falta (en orden) y deja el mejorador vacío. Si falla, no se
        pierde nada: se puede volver a llamar."""
        salida = self._listos + self._cerrar_tramo()
        self._listos = []
        return salida


__all__ = [
    "AjustesMejora", "MejoradorVideo", "RADIO_VECINOS", "RESOLUCIONES_MEJORA", "mejorar_cuadro",
    "tamano_mejorado", "vaciar_memoria",
]
