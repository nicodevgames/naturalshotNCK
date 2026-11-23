"""Modo Audio: el proyecto (la voz, sus cortes y su ambiente), las escenas, "Mis sonidos",
la mezcla para escuchar y la exportación.

No depende de la interfaz gráfica. PyAV (con ``motor/video.py``) y la biblioteca de
ambientes (``motor/ambientes.py``) se importan recién al usarlos, así las dataclasses
(``ProyectoAudio``, ``Escena``…) se pueden importar desde la sesión sin cargar FFmpeg.

Tiempos
-------
* **Original:** el del archivo de la voz. Los tramos conservados, los silencios y las
  **anclas** de los sonidos sueltos van en este tiempo: siguen a las palabras al cortar.
* **Resultado:** el de lo que se escucha y se exporta, con lo borrado ya sacado. Los
  fondos, los fundidos de entrada y de salida y la posición de la cadena de la voz van
  en este tiempo.

La mezcla, en orden (``MezcladorAudio``)
----------------------------------------
1. **Voz:** un ``LectorPCM`` en float32 con los tramos y ``AjustesAudio(silencios=…)``:
   lo borrado se saltea y las uniones y los silencios llevan sus fundidos de 5 ms. Sin
   volumen ni fundidos (van al final). Una voz mono se lee mono y se duplica (FFmpeg, al
   pasarla a estéreo, la bajaba 3 dB).
2. **Ambiente:** los fondos (de 0 a 3 capas) más los sonidos sueltos, cada uno con su volumen.
3. **``CadenaVoz``** (``motor/voz_natural.py``): la voz pasa por el lugar y, junto con el
   ambiente, por el micrófono, el AGC, el ruido propio y la compresión del destino.
4. **Final**, en el tiempo del resultado: la ganancia de ``AjustesAudio`` (volumen y
   normalizar), los fundidos de entrada y de salida (cuadráticos, como en ``audio.py``) y un
   **limitador suave** sin memoria: igual por debajo de ``LIMITE_SUAVE`` (0,9 = -0,9 dBFS, así
   la normalización a -1 dBFS no se toca) y, por encima, una curva tanh que nunca llega a ±1
   (sin destino, voz + ambiente + eco puede pasar de 1; un volumen de 2, también).
5. Formato de salida: int16 ("s16", lo que pide ``QAudioSink``) o float32 ("f32").

Volúmenes
---------
``volumen`` va de 0 a 1 con una curva en dB: ``VOLUMEN_MAX_DB`` (12 dB) por cada vez que se
duplica, o sea 12·log2(2·v) dB (la ganancia es casi (2·v)²). 0,5 es el nivel de referencia
(×1), 1 es +12 dB, 0,25 es -12 dB, 0,125 es -24 dB y 0 es silencio.
Las referencias: un fondo generado sale a ``NIVEL_FONDO_DBFS`` (-30 dBFS RMS a intensidad
0,5) y un sonido suelto con el pico en ``PICO_SONIDO_DBFS`` (-6 dBFS). Un archivo de "Mis
sonidos" se calibra igual: usado de fondo, su RMS se lleva a -30 dBFS; usado de sonido
suelto, su pico a -6 dBFS. Así 0,5 quiere decir lo mismo en los dos casos. Los niveles son
absolutos (no dependen de la voz): con una voz muy baja, el fondo queda más adelante.

Fondos
------
Cada capa cubre todo el resultado (no se corta en los cortes: va en el tiempo del
resultado), con fundidos de coseno de ``FUNDIDO_FONDO`` (0,3 s) al principio y al final.
Un fondo generado sale de ``GeneradorFondo`` (acceso aleatorio exacto). Un archivo de
"Mis sonidos" de largo L se repite así: hasta ``P = L - X`` suena tal cual y desde ahí
se repite con período P, donde los primeros X de cada vuelta son un fundido cruzado de
igual potencia (seno y coseno) entre el principio del archivo y su final. X es
``CRUCE_FONDO`` (2 s), o L / 2 si el archivo dura menos de 4 s. Se calcula muestra por
muestra con índices: cualquier punto da lo mismo que de corrido.

Sonidos sueltos
---------------
Suenan enteros desde su ancla, pasada al tiempo del resultado (si cae en lo borrado,
arrancan al principio del tramo conservado siguiente): los cortes de la voz no los
recortan. El final del resultado sí (el resultado dura lo que la voz): ahí se apagan en
``FUNDIDO_SUELTO`` (15 ms), no se cortan en seco.

Lo que falta
------------
Un archivo de "Mis sonidos" que ya no está (o que no se puede leer, o que dura más de 10
minutos) y un fondo o un sonido generado que esta versión no conoce se saltean sin error.
``MezcladorAudio.faltan`` los nombra, para que la interfaz los marque.

Saltos, bloques y vista previa = exportación
--------------------------------------------
La cadena se alimenta siempre en una grilla fija del resultado (trozos ``[k·_PASO,
(k+1)·_PASO)``, de 100 ms), lean lo que lean de afuera: la vista previa y la exportación
salen idénticas, muestra por muestra (la exportación usa este mismo mezclador). Después
de un salto a p se sigue la receta de ``voz_natural``: se reinicia la cadena en un borde de
la grilla al menos ``PRELECTURA`` (0,5 s) antes de p, se procesa desde ahí y se descarta lo
anterior a p; al llegar al final, ``vaciar()``. Sin compresión, lo que sigue al salto da lo
mismo que de corrido (salvo el AGC, que puede diferir apenas: ver ``voz_natural``). Con
compresión suena igual, pero la forma de onda no es la misma.

Lectura adelantada (para escuchar desde la interfaz)
----------------------------------------------------
Un fondo puede tardar 150 a 200 ms en un solo pedido (sintetiza la pasada entera de un
auto) y el reproductor lee desde el hilo de la interfaz. Con ``adelanto`` (por ejemplo
``ADELANTO_VISTA_PREVIA``, 1 s), un hilo propio del mezclador mantiene lleno un búfer con
la mezcla de antes del paso final y ``leer`` solo copia y aplica el volumen: menos de 1 ms.
Ver ``MezcladorAudio``. La exportación y la medición del pico leen directo, sin hilo.

Normalizar
----------
El pico se mide con una pasada del mezclador sin normalizar, sin volumen, sin fundidos y
sin el limitador (``medir_pico_proyecto``, en caché por proyecto y por la fecha de los
archivos). ``MezcladorAudio(p, pico=…)`` lo acepta, como ``LectorPCM``; si falta, lo mide.

Mis sonidos y escenas propias
-----------------------------
En ``%APPDATA%\\NaturalShot PRO\\sonidos\\`` y ``%APPDATA%\\NaturalShot PRO\\escenas.json``.
Los sonidos se decodifican con PyAV a 48 kHz estéreo float32 y quedan en una caché LRU de
hasta 10 minutos de audio (unos 230 MB); uno más largo que ``DURACION_MAX_SONIDO`` da
``ValueError``. Las escenas propias se escriben de forma atómica (temporal y ``os.replace``).

Exportar
--------
WhatsApp (``.ogg``, Opus mono a 24 kbit/s, codificado a 16 kHz como las notas de voz de
verdad: se decodifica a 48 kHz y corta arriba de 8 kHz igual que la vista previa), M4A (AAC,
192 kbit/s), MP3 (192 kbit/s) y WAV (16 bits), a 48 kHz. Con destino WhatsApp y formato WhatsApp, la cadena no
comprime (``codec=False``): el archivo ya sale en Opus y no se comprime dos veces. Temporal
en la misma carpeta y renombrado al final, como ``exportar_audio``: cancelar o un error no
dejan nada.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import threading
import time
import weakref
from collections import OrderedDict, deque
from dataclasses import dataclass, fields, replace
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional, Union

import numpy as np

from .audio import FORMATOS_AUDIO, AjustesAudio, FormatoAudio, ResultadoAudio, _a_int16, _numero, _unir_tramos
from .procesado import Cancelado
from .voz_natural import PRELECTURA, AjustesVoz, CadenaVoz

FRECUENCIA = 48000
CAPAS_MAX = 3                 # capas de fondo
ORIGENES = ("generado", "archivo")
FUNDIDO_FONDO = 0.3           # s: fundido de cada fondo al principio y al final del resultado
CRUCE_FONDO = 2.0             # s: fundido cruzado al repetir un archivo usado de fondo
FUNDIDO_SUELTO = 0.015        # s: un sonido suelto que pasa el final del resultado se apaga en este tiempo
CRUCE_CAMBIO = 0.010          # s: fundido cruzado al cambiar el proyecto mientras suena (lectura adelantada)
DURACION_MAX_SONIDO = 600.0   # s: un archivo de "Mis sonidos" más largo no se usa (ValueError)
MEMORIA_SONIDOS = 600.0       # s de audio decodificado que guarda la caché de "Mis sonidos"
VOLUMEN_MAX_DB = 12.0         # lo que suma un volumen de 1 sobre el nivel de referencia (0,5)
LIMITE_SUAVE = 0.9            # el limitador final no toca nada por debajo de esto
FORMATOS_PROYECTO = ("whatsapp", "m4a", "mp3", "wav")
# Lo que se puede abrir como voz y guardar en "Mis sonidos".
EXTENSIONES_AUDIO = (".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac")
CARPETA_DATOS = "NaturalShot PRO"   # dentro de %APPDATA% (la misma de la sesión)
CARPETA_SONIDOS = "sonidos"
ARCHIVO_ESCENAS = "escenas.json"

NOMBRES_DESTINO = {"ninguno": "Sin cambios", "whatsapp": "Nota de voz de WhatsApp", "video": "Video de celular",
                   "auriculares": "Auriculares o manos libres"}
NOMBRES_LUGAR = {"ninguno": "Ningún lugar", "habitacion": "Habitación", "oficina": "Oficina",
                 "auto": "Adentro de un auto", "colectivo": "Adentro de un colectivo", "calle": "Calle",
                 "exterior": "Al aire libre"}

_PASO = 4800                  # muestras: la grilla fija en la que se alimenta la cadena (100 ms)
_BLOQUE = 8192                # muestras por vuelta al exportar o medir
_NIVEL_FONDO = 10.0 ** (-30.0 / 20.0)   # = ambientes.NIVEL_FONDO_DBFS (sin importar ambientes acá)
_PICO_SONIDO = 10.0 ** (-6.0 / 20.0)    # = ambientes.PICO_SONIDO_DBFS
_CALIBRACION_MAX = 10.0 ** (40.0 / 20.0)  # un archivo casi mudo no se sube más de +40 dB

Progreso = Callable[[int, int, Optional[float]], None]


def _video():
    """``motor/video.py`` (y con él PyAV), recién cuando hace falta."""
    from . import video
    video._verificar_av()
    return video


def _ambientes():
    from . import ambientes
    return ambientes


# ---------------------------------------------------------------------------
# Ajustes y datos del proyecto
# ---------------------------------------------------------------------------

def _acomodar(valor, defecto: float) -> float:
    """Entre 0 y 1, redondeado a 0,01 (NaN o algo que no es un número: el valor por defecto)."""
    v = _numero(valor, defecto)
    return round(min(1.0, max(0.0, v)), 2)


def _entero(valor) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError, OverflowError):
        return 0


def _origen(origen) -> str:
    if origen not in ORIGENES:
        raise ValueError(f"Origen desconocido: {origen!r}. Usá 'generado' o 'archivo'.")
    return origen


def _clave(clave) -> str:
    if not isinstance(clave, str) or not clave:
        raise ValueError("Falta la clave del sonido (un id de la biblioteca o el nombre del archivo).")
    return clave


def ganancia_volumen(volumen: float) -> float:
    """Factor lineal de un ``volumen`` de 0 a 1: ``VOLUMEN_MAX_DB``·log2(2·v) dB (casi (2·v)²).

    0,5 = el nivel de referencia (×1), 1 = +12 dB, 0,25 = -12 dB, 0,1 = -27,9 dB y
    0 = silencio. NaN o algo que no es un número cuenta como 0,5.
    """
    v = min(1.0, max(0.0, _numero(volumen, 0.5)))
    return (2.0 * v) ** (VOLUMEN_MAX_DB / (20.0 * math.log10(2.0)))


@dataclass(frozen=True)
class FondoProyecto:
    """Una capa del fondo continuo.

    origen      "generado" (de la biblioteca, ``ambientes.FONDOS``) o "archivo" (de "Mis sonidos").
    clave       id de ``FONDOS`` o nombre del archivo en "Mis sonidos" (con su extensión).
    volumen     de 0 a 1, con curva en dB (0,5 = el nivel de referencia; ver ``ganancia_volumen``).
    intensidad  de 0 a 1 (más o menos lluvia, tránsito…); solo en los generados.
    semilla     otra realización del mismo fondo (otra lluvia, otros autos).

    Los números se acomodan entre 0 y 1 (redondeados a 0,01; NaN vuelve al valor por
    defecto). Un origen desconocido o una clave vacía dan ``ValueError``; una clave que no
    existe no (la mezcla la saltea): así un proyecto viejo se sigue abriendo.
    """

    origen: str
    clave: str
    volumen: float = 0.5
    intensidad: float = 0.5
    semilla: int = 0

    def __post_init__(self):
        _origen(self.origen)
        _clave(self.clave)
        object.__setattr__(self, "volumen", _acomodar(self.volumen, 0.5))
        object.__setattr__(self, "intensidad", _acomodar(self.intensidad, 0.5))
        object.__setattr__(self, "semilla", _entero(self.semilla))

    def con(self, **cambios) -> "FondoProyecto":
        return replace(self, **cambios)


@dataclass(frozen=True)
class SonidoSuelto:
    """Un sonido en un momento justo ("a los 12 segundos pasa un colectivo").

    origen   "generado" (``ambientes.SONIDOS``) o "archivo" (de "Mis sonidos").
    clave    id de ``SONIDOS`` o nombre del archivo en "Mis sonidos".
    ancla    dónde empieza, en segundos del tiempo ORIGINAL de la voz (sigue a las palabras al cortar).
    volumen  de 0 a 1, con curva en dB (0,5 = pico en -6 dBFS).
    semilla  otra variante del mismo sonido (otro lado, otra velocidad).
    """

    origen: str
    clave: str
    ancla: float
    volumen: float = 0.7
    semilla: int = 0

    def __post_init__(self):
        _origen(self.origen)
        _clave(self.clave)
        object.__setattr__(self, "ancla", max(0.0, _numero(self.ancla, 0.0)))
        object.__setattr__(self, "volumen", _acomodar(self.volumen, 0.7))
        object.__setattr__(self, "semilla", _entero(self.semilla))

    def con(self, **cambios) -> "SonidoSuelto":
        return replace(self, **cambios)


@dataclass(frozen=True)
class ProyectoAudio:
    """Todo lo que hace falta para escuchar y exportar un audio del modo Audio.

    ruta          el archivo de la voz.
    tramos        los que se conservan, (inicio, fin) en segundos del tiempo original
                  (``EdicionVideo.tramos_conservados()``). Se ordenan y se unen los que se pisan.
    sonido        ``AjustesAudio``: volumen, normalizar, fundidos (en el resultado) y silencios
                  (en el original). ``quitar`` deja todo en silencio.
    voz           ``AjustesVoz``: cómo se grabó, cuánto, "bajarle lo de IA", lugar…
    fondos        de 0 a ``CAPAS_MAX`` (3) capas de ``FondoProyecto``; más dan ``ValueError``.
    sonidos       ``SonidoSuelto``, en cualquier orden.
    video_origen  el video del que salió la voz ("Editar el sonido en el modo Audio"), o None.

    Inmutable (cada cambio devuelve otro: deshacer es guardar estados) y se puede guardar
    con pickle. Las listas se pasan a tuplas.
    """

    ruta: str
    tramos: tuple
    sonido: AjustesAudio
    voz: AjustesVoz
    fondos: tuple
    sonidos: tuple
    video_origen: Optional[str] = None

    def __post_init__(self):
        object.__setattr__(self, "ruta", str(self.ruta))
        object.__setattr__(self, "tramos", _unir_tramos(self.tramos))
        if not isinstance(self.sonido, AjustesAudio):
            raise TypeError("sonido tiene que ser un AjustesAudio.")
        if not isinstance(self.voz, AjustesVoz):
            raise TypeError("voz tiene que ser un AjustesVoz.")
        fondos = tuple(self.fondos or ())
        if not all(isinstance(f, FondoProyecto) for f in fondos):
            raise TypeError("fondos tiene que tener solo FondoProyecto.")
        if len(fondos) > CAPAS_MAX:
            raise ValueError(f"El fondo tiene como mucho {CAPAS_MAX} capas (llegaron {len(fondos)}).")
        sonidos = tuple(self.sonidos or ())
        if not all(isinstance(s, SonidoSuelto) for s in sonidos):
            raise TypeError("sonidos tiene que tener solo SonidoSuelto.")
        object.__setattr__(self, "fondos", fondos)
        object.__setattr__(self, "sonidos", sonidos)
        if self.video_origen is not None:
            object.__setattr__(self, "video_origen", str(self.video_origen))

    def con(self, **cambios) -> "ProyectoAudio":
        """Otro con esos campos cambiados (acomodados igual que al crearlo)."""
        return replace(self, **cambios)


def _info(ruta):
    """Datos del archivo (``audio.info_medio``): sirve para audios sin video."""
    from .audio import info_medio
    return info_medio(ruta)


def abrir_proyecto(ruta: Union[str, os.PathLike]) -> ProyectoAudio:
    """Un proyecto nuevo con la voz de ``ruta``: todo conservado, sin ajustes, sin fondo ni sonidos.

    Abre archivos de solo audio (MP3, M4A, AAC, OGG/Opus, WAV, FLAC) y también videos con
    sonido. ``FileNotFoundError`` si no existe; ``ValueError`` si no se puede abrir ("No se
    pudo abrir…") o si no tiene sonido ("Este archivo no tiene sonido.").
    """
    ruta = Path(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el archivo: {ruta}")
    try:
        info = _info(ruta)
    except Exception as error:
        raise ValueError(f"No se pudo abrir «{ruta.name}»: no parece un archivo de sonido.") from error
    if not info.tiene_audio or info.duracion <= 0:
        raise ValueError("Este archivo no tiene sonido.")
    return ProyectoAudio(str(ruta), ((0.0, float(info.duracion)),), AjustesAudio(), AjustesVoz(), (), ())


def duracion_original(p: ProyectoAudio) -> float:
    """Segundos del archivo de la voz."""
    return float(_info(p.ruta).duracion)


def _tramos_ok(p: ProyectoAudio) -> list[tuple[float, float]]:
    """Los tramos del proyecto recortados al archivo (como los usa ``LectorPCM``)."""
    return _video().normalizar_tramos(p.tramos, duracion_original(p))


def _mapa(p: ProyectoAudio):
    """``video.MapaTiempo`` del proyecto: original ↔ resultado."""
    mv = _video()
    return mv.MapaTiempo(tuple(_tramos_ok(p)), duracion_original(p))


def duracion_resultado(p: ProyectoAudio) -> float:
    """Segundos de lo que se escucha y se exporta (redondeado a muestras, como el mezclador)."""
    total = 0
    for a, b in _tramos_ok(p):
        total += max(0, round(b * FRECUENCIA) - round(a * FRECUENCIA))
    return total / FRECUENCIA


def ancla_en_resultado(p: ProyectoAudio, ancla: float) -> float:
    """Segundo del resultado donde empieza un sonido anclado en ``ancla`` (tiempo original).

    Si el ancla cae en lo borrado, el comienzo del tramo conservado siguiente; después del
    último tramo, el final del resultado (no se oye).
    """
    return float(_mapa(p).a_resultado(max(0.0, _numero(ancla, 0.0))))


# ---------------------------------------------------------------------------
# Escenas
# ---------------------------------------------------------------------------

def _sonido_de_escena(item) -> tuple:
    """Un sonido sugerido, acomodado y en su forma más corta (ver ``Escena.sonidos``)."""
    item = tuple(item)
    if len(item) not in (3, 4, 5):
        raise ValueError(f"Sonido de escena inválido: {item!r} (va clave, fracción, volumen y, si hace falta, "
                         "el origen y la semilla).")
    origen = _origen(item[3]) if len(item) >= 4 else "generado"
    semilla = _entero(item[4]) if len(item) == 5 else 0
    clave = _clave(item[0])
    fraccion = min(1.0, max(0.0, _numero(item[1], 0.0)))
    volumen = min(1.0, max(0.0, _numero(item[2], 0.7)))
    if semilla:
        return (clave, fraccion, volumen, origen, semilla)
    return (clave, fraccion, volumen) + (("archivo",) if origen == "archivo" else ())


@dataclass(frozen=True)
class Escena:
    """Un preset del modo Audio: cómo se grabó, el fondo y los sonidos sugeridos.

    clave        id estable (para las de la app) o el nombre (para las propias).
    nombre       para la tarjeta: "Nota de voz caminando por la calle".
    descripcion  una línea.
    voz          ``AjustesVoz``.
    fondos       de 0 a 3 ``FondoProyecto``.
    sonidos      (clave de ``SONIDOS``, fracción de la duración del resultado, volumen); un sonido
                 de "Mis sonidos" lleva un cuarto elemento, "archivo", y uno con semilla (no 0), un
                 cuarto y un quinto: (clave, fracción, volumen, origen, semilla). Siempre en la forma
                 más corta: las de la app son de 3. Para leerlos: ``item[:3]``, el origen en
                 ``item[3]`` si está ("generado" si no) y la semilla en ``item[4]`` si está (0 si no).
    propia       guardada por el usuario ("Guardar como escena").
    """

    clave: str
    nombre: str
    descripcion: str
    voz: AjustesVoz
    fondos: tuple
    sonidos: tuple
    propia: bool = False

    def __post_init__(self):
        if not isinstance(self.voz, AjustesVoz):
            raise TypeError("voz tiene que ser un AjustesVoz.")
        fondos = tuple(self.fondos or ())
        if not all(isinstance(f, FondoProyecto) for f in fondos):
            raise TypeError("fondos tiene que tener solo FondoProyecto.")
        if len(fondos) > CAPAS_MAX:
            raise ValueError(f"Una escena tiene como mucho {CAPAS_MAX} capas de fondo.")
        object.__setattr__(self, "fondos", fondos)
        object.__setattr__(self, "sonidos", tuple(_sonido_de_escena(s) for s in self.sonidos or ()))
        object.__setattr__(self, "clave", str(self.clave))
        object.__setattr__(self, "nombre", str(self.nombre))
        object.__setattr__(self, "descripcion", str(self.descripcion))
        object.__setattr__(self, "propia", bool(self.propia))


def _fondo(clave: str, volumen: float = 0.5, intensidad: float = 0.5) -> FondoProyecto:
    return FondoProyecto("generado", clave, volumen, intensidad)


def _escena(clave, nombre, descripcion, voz, fondos=(), sonidos=()) -> Escena:
    return Escena(clave, nombre, descripcion, voz, tuple(fondos), tuple(sonidos))


# Las de la tabla del diseño. "Cuánto" en Normal (0,6) y un poco de "bajarle lo de IA" (0,4) en
# todas. Volúmenes de los fondos (0,5 = -30 dBFS RMS): los de interiores tranquilos más bajos
# (oficina y habitación, 0,3 = -39 dBFS), el colectivo un poco más alto.
ESCENAS: dict[str, Escena] = {e.clave: e for e in (
    _escena("nota_oficina", "Nota de voz en la oficina",
            "Un audio de WhatsApp grabado en la oficina, con el aire acondicionado de fondo.",
            AjustesVoz(destino="whatsapp", lugar="oficina", anti_ia=0.4), [_fondo("oficina", 0.3)]),
    _escena("nota_calle", "Nota de voz caminando por la calle",
            "Un audio de WhatsApp en la vereda: el tránsito y un colectivo que pasa.",
            AjustesVoz(destino="whatsapp", lugar="calle", anti_ia=0.4), [_fondo("calle", 0.5)],
            [("colectivo_pasa", 0.4, 0.55)]),
    _escena("nota_colectivo", "Nota de voz arriba del colectivo",
            "Un audio de WhatsApp arriba del colectivo: el motor y una frenada.",
            AjustesVoz(destino="whatsapp", lugar="colectivo", anti_ia=0.4), [_fondo("colectivo", 0.55)],
            [("frenada_colectivo", 0.6, 0.45)]),
    _escena("nota_lluvia", "Nota de voz bajo la lluvia",
            "Un audio de WhatsApp afuera, bajo la lluvia, con un auto que pasa.",
            AjustesVoz(destino="whatsapp", lugar="exterior", anti_ia=0.4), [_fondo("lluvia", 0.5)],
            [("auto_pasa", 0.5, 0.45)]),
    _escena("video_playa", "Video en la playa",
            "Un video de celular frente al mar: las olas y el viento.",
            AjustesVoz(destino="video", lugar="exterior", anti_ia=0.4),
            [_fondo("olas", 0.55), _fondo("viento", 0.4, 0.4)]),
    _escena("video_ciudad", "Video en la ciudad",
            "Un video de celular en la ciudad, con una sirena lejos.",
            AjustesVoz(destino="video", lugar="calle", anti_ia=0.4), [_fondo("ciudad", 0.5)],
            [("sirena_lejos", 0.3, 0.4)]),
    _escena("video_casa", "Video en casa",
            "Un video de celular adentro de una habitación.",
            AjustesVoz(destino="video", lugar="habitacion", anti_ia=0.4), [_fondo("habitacion", 0.3)]),
    _escena("manos_libres_auto", "Manos libres en el auto",
            "Hablando por el manos libres mientras se maneja por la ruta.",
            AjustesVoz(destino="auriculares", lugar="auto", anti_ia=0.4), [_fondo("auto", 0.5)]),
    _escena("auriculares_calle", "Auriculares en la calle",
            "Con auriculares en la calle: el tránsito y el viento que golpea el micrófono.",
            AjustesVoz(destino="auriculares", lugar="calle", anti_ia=0.4),
            [_fondo("calle", 0.5), _fondo("viento_mic", 0.35, 0.4)]),
    _escena("solo_anti_ia", "Solo bajarle lo de IA",
            "Sin lugar ni fondo: solo le saca a la voz lo demasiado perfecto.",
            AjustesVoz(anti_ia=0.6)),
)}


def aplicar_escena(p: ProyectoAudio, e: Escena) -> ProyectoAudio:
    """El proyecto con la voz, los fondos y los sonidos de la escena (los sonidos de antes se van).

    Cada sonido sugerido va en su fracción de la duración del resultado, pasada a un ancla en
    tiempo original (así después sigue a la voz si se corta).
    """
    mapa = _mapa(p)
    total = mapa.duracion
    sonidos = []
    for item in e.sonidos:
        clave, fraccion, volumen = item[:3]
        origen = item[3] if len(item) > 3 else "generado"
        semilla = item[4] if len(item) > 4 else 0
        sonidos.append(SonidoSuelto(origen, clave, float(mapa.a_original(fraccion * total)), volumen, semilla))
    return replace(p, voz=e.voz, fondos=e.fondos, sonidos=tuple(sonidos))


def _carpeta_datos() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home()) / CARPETA_DATOS


def _archivo_escenas() -> Path:
    return _carpeta_datos() / ARCHIVO_ESCENAS


def _nombre_escena(nombre) -> str:
    nombre = " ".join(str(nombre or "").split())
    if not nombre:
        raise ValueError("Poné un nombre para la escena.")
    if len(nombre) > 80:
        raise ValueError("El nombre de la escena es muy largo (como mucho 80 letras).")
    return nombre


def describir(voz: AjustesVoz, fondos=(), sonidos=()) -> str:
    """Una línea que dice qué tiene una escena o un proyecto: "Nota de voz de WhatsApp · Calle · …"."""
    partes = [NOMBRES_DESTINO.get(voz.destino, voz.destino)]
    if voz.lugar != "ninguno":
        partes.append(NOMBRES_LUGAR.get(voz.lugar, voz.lugar))
    if fondos:
        catalogo = _ambientes().FONDOS
        nombres = [catalogo[f.clave].nombre if f.origen == "generado" and f.clave in catalogo else Path(f.clave).stem
                   for f in fondos]
        partes.append("Fondo: " + " + ".join(nombres))
    if sonidos:
        partes.append("1 sonido" if len(sonidos) == 1 else f"{len(sonidos)} sonidos")
    if voz.anti_ia > 0 and voz.destino == "ninguno" and voz.lugar == "ninguno" and not fondos:
        partes.append("bajarle lo de IA")
    return " · ".join(partes)


def _escena_a_json(e: Escena) -> dict:
    return {"nombre": e.nombre, "descripcion": e.descripcion,
            "voz": {f.name: getattr(e.voz, f.name) for f in fields(AjustesVoz)},
            "fondos": [{f.name: getattr(c, f.name) for f in fields(FondoProyecto)} for c in e.fondos],
            "sonidos": [list(s) for s in e.sonidos]}


def _escena_de_json(d) -> Escena:
    if not isinstance(d, dict):
        raise ValueError("escena inválida")
    nombre = _nombre_escena(d["nombre"])
    campos_voz = {f.name for f in fields(AjustesVoz)}
    voz = AjustesVoz(**{k: v for k, v in dict(d.get("voz") or {}).items() if k in campos_voz})
    campos_fondo = {f.name for f in fields(FondoProyecto)}
    fondos = tuple(FondoProyecto(**{k: v for k, v in dict(f).items() if k in campos_fondo})
                   for f in d.get("fondos") or ())
    return Escena(nombre, nombre, str(d.get("descripcion") or ""), voz, fondos,
                  tuple(tuple(s) for s in d.get("sonidos") or ()), propia=True)


def _leer_escenas(respaldar: bool = False) -> "OrderedDict[str, Escena]":
    """Las escenas propias del archivo. Dañado: ninguna (y, con ``respaldar``, queda como ``.bak``)."""
    archivo = _archivo_escenas()
    try:
        crudo = archivo.read_bytes()
    except OSError:
        return OrderedDict()
    try:
        datos = json.loads(crudo.decode("utf-8"))   # bytes que no son UTF-8: ValueError, como un JSON roto
        lista = datos["escenas"]
        if not isinstance(lista, list):
            raise ValueError("sin lista de escenas")
    except (ValueError, KeyError, TypeError):
        if respaldar:
            try:
                os.replace(archivo, archivo.with_name(ARCHIVO_ESCENAS + ".bak"))
            except OSError:
                pass
        return OrderedDict()
    salida: "OrderedDict[str, Escena]" = OrderedDict()
    for item in lista:
        try:
            e = _escena_de_json(item)
        except (ValueError, TypeError, KeyError, AttributeError):
            continue   # una escena rota no se lleva a las demás
        salida[e.nombre] = e
    return salida


def _escribir_atomico(ruta: Path, contenido: bytes) -> None:
    """Temporal en la misma carpeta, al disco (``fsync``) y ``os.replace``: nunca queda a medias."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(prefix=ruta.name + ".", suffix=".tmp", dir=ruta.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contenido)
            f.flush()
            os.fsync(f.fileno())
        for intento in range(6):
            try:
                os.replace(temporal, ruta)
                break
            except PermissionError:   # un antivirus o un lector lo tiene abierto un instante
                if intento == 5:
                    raise
                time.sleep(0.05 * (intento + 1))
    except BaseException:
        try:
            os.unlink(temporal)
        except OSError:
            pass
        raise


def _escribir_escenas(escenas) -> None:
    datos = {"version": 1, "escenas": [_escena_a_json(e) for e in escenas.values()]}
    _escribir_atomico(_archivo_escenas(), json.dumps(datos, ensure_ascii=False, indent=1).encode("utf-8"))


def escenas_propias() -> dict[str, Escena]:
    """Las escenas guardadas por el usuario, por nombre y en el orden en que se guardaron.

    Si el archivo no está o está dañado, no hay ninguna (no es un error).
    """
    return dict(_leer_escenas())


def guardar_escena(nombre: str, p: ProyectoAudio) -> Escena:
    """Guarda la voz, los fondos y los sonidos del proyecto como una escena propia.

    Los sonidos sueltos quedan en fracción de la duración del resultado (redondeada a
    0,0001). Si ya había una con ese nombre, la reemplaza (en su lugar). ``ValueError``
    si el nombre está vacío.
    """
    nombre = _nombre_escena(nombre)
    total = duracion_resultado(p) if p.sonidos else 0.0
    sonidos = []
    for s in p.sonidos:
        fraccion = round(ancla_en_resultado(p, s.ancla) / total, 4) if total > 0 else 0.0
        sonidos.append((s.clave, fraccion, s.volumen, s.origen, s.semilla))   # se acorta al crear la Escena
    e = Escena(nombre, nombre, describir(p.voz, p.fondos, p.sonidos), p.voz, p.fondos, tuple(sonidos), propia=True)
    escenas = _leer_escenas(respaldar=True)
    escenas[nombre] = e
    _escribir_escenas(escenas)
    return e


def borrar_escena(nombre: str) -> None:
    """Borra una escena propia (si no existe, no pasa nada)."""
    escenas = _leer_escenas(respaldar=True)
    if escenas.pop(" ".join(str(nombre or "").split()), None) is not None:
        _escribir_escenas(escenas)


# ---------------------------------------------------------------------------
# Mis sonidos
# ---------------------------------------------------------------------------

_RESERVADOS = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
               *(f"{p}{i}" for p in ("COM", "LPT") for i in "0123456789¹²³")}
_LARGO_NOMBRE = 120   # letras del nombre del archivo, con la extensión
_PROHIBIDOS = set('<>:"/\\|?*')


def carpeta_sonidos() -> Path:
    """``%APPDATA%\\NaturalShot PRO\\sonidos`` (se crea al agregar el primero)."""
    return _carpeta_datos() / CARPETA_SONIDOS


def mis_sonidos() -> list[Path]:
    """Los archivos de sonido de la carpeta, por nombre (sin distinguir mayúsculas)."""
    try:
        archivos = [p for p in carpeta_sonidos().iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONES_AUDIO]
    except OSError:
        return []
    return sorted(archivos, key=lambda p: (p.stem.casefold(), p.suffix.casefold()))


def _ruta_sonido(nombre) -> Path:
    """La ruta de un sonido de la carpeta por su nombre; nada de rutas que se salgan de ella."""
    nombre = str(nombre or "")
    if not nombre or nombre in (".", "..") or any(c in "/\\:" for c in nombre) or Path(nombre).name != nombre:
        raise ValueError(f"Nombre de sonido inválido: {nombre!r}.")
    return carpeta_sonidos() / nombre


def _nombre_valido(nombre) -> str:
    """Un nombre de archivo que Windows acepta, sin espacios en los bordes."""
    nombre = str(nombre or "").strip()
    if (not nombre or nombre.endswith(".") or len(nombre) > _LARGO_NOMBRE
            or any(c in _PROHIBIDOS or ord(c) < 32 for c in nombre)
            or nombre.split(".")[0].strip().upper() in _RESERVADOS):
        raise ValueError(f"«{nombre}» no sirve como nombre de archivo (no puede estar vacío ni llevar "
                         "\\ / : * ? \" < > |).")
    return nombre


def _minutos(segundos: float) -> str:
    m = segundos / 60.0
    return "1 minuto" if m == 1 else f"{m:g} minutos"


def agregar_a_mis_sonidos(ruta: Union[str, os.PathLike]) -> Path:
    """Copia un archivo de sonido a "Mis sonidos" y devuelve la copia.

    Si ya hay uno con ese nombre, la copia se llama "nombre (2).ext", "(3)", etc. (nunca
    pisa nada). ``FileNotFoundError`` si no existe; ``ValueError`` si no es un archivo de
    sonido (``EXTENSIONES_AUDIO``), si no se puede abrir, si no tiene sonido o si dura más de
    ``DURACION_MAX_SONIDO`` (10 minutos).
    """
    origen = Path(ruta)
    if not origen.is_file():
        raise FileNotFoundError(f"No existe el archivo: {origen}")
    if origen.suffix.lower() not in EXTENSIONES_AUDIO:
        raise ValueError(f"«{origen.name}» no es un archivo de sonido (MP3, M4A, AAC, WAV, OGG, OPUS o FLAC).")
    try:
        info = _info(origen)
    except Exception as error:
        raise ValueError(f"No se pudo abrir «{origen.name}»: no parece un archivo de sonido.") from error
    if not info.tiene_audio:
        raise ValueError(f"«{origen.name}» no tiene sonido.")
    if info.duracion > DURACION_MAX_SONIDO:
        raise ValueError(f"«{origen.name}» dura más de {_minutos(DURACION_MAX_SONIDO)}: es demasiado largo para "
                         "un sonido.")
    carpeta = carpeta_sonidos()
    carpeta.mkdir(parents=True, exist_ok=True)
    k = 1
    while True:   # el nombre se reserva creando el archivo (O_EXCL): dos copias a la vez no se pisan
        destino = carpeta / (f"{origen.stem}{origen.suffix}" if k == 1 else f"{origen.stem} ({k}){origen.suffix}")
        try:
            fd = os.open(destino, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0))
            break
        except FileExistsError:
            k += 1
    try:
        with os.fdopen(fd, "wb") as f, open(origen, "rb") as g:
            while True:
                trozo = g.read(1 << 20)
                if not trozo:
                    break
                f.write(trozo)
    except BaseException:
        try:
            destino.unlink()
        except OSError:
            pass
        raise
    return destino


def renombrar_sonido(nombre: str, nuevo: str) -> Path:
    """Le cambia el nombre a un sonido de la carpeta y devuelve la ruta nueva.

    La extensión se conserva (si ``nuevo`` no la trae, se agrega). ``FileNotFoundError`` si
    no está; ``ValueError`` si el nombre nuevo no sirve o si ya hay otro que se llama así.
    Ojo: los proyectos y las escenas que lo usaban por el nombre viejo lo van a ver como
    "falta" (la interfaz puede actualizarlos).
    """
    viejo = _ruta_sonido(nombre)
    if not viejo.is_file():
        raise FileNotFoundError(f"No está el sonido «{nombre}».")
    nuevo = _nombre_valido(nuevo)
    if Path(nuevo).suffix.lower() != viejo.suffix.lower():
        nuevo = _nombre_valido(nuevo + viejo.suffix)   # con la extensión también tiene que entrar en el largo
    destino = viejo.with_name(nuevo)
    if destino.exists():
        try:
            mismo = os.path.samefile(destino, viejo)
        except OSError:
            mismo = False
        if not mismo:
            raise ValueError(f"Ya hay un sonido que se llama «{destino.name}».")
        if destino.name == viejo.name:
            return viejo
    os.rename(viejo, destino)   # en Windows, cambiar solo mayúsculas también anda
    _olvidar_sonido(viejo)
    return destino


def borrar_sonido(nombre: str) -> None:
    """Borra un sonido de la carpeta (si ya no está, no pasa nada)."""
    ruta = _ruta_sonido(nombre)
    try:
        ruta.unlink()
    except FileNotFoundError:
        pass
    _olvidar_sonido(ruta)


@dataclass(frozen=True, eq=False)
class _SonidoCargado:
    """Un sonido de "Mis sonidos" decodificado y medido una sola vez (para calibrarlo sin recorrerlo de nuevo)."""

    datos: np.ndarray   # (n, 2) float32, de solo lectura
    rms: float
    pico: float


_CACHE_SONIDOS: "OrderedDict[tuple, _SonidoCargado]" = OrderedDict()
_CANDADO_SONIDOS = threading.Lock()


def _medir(datos: np.ndarray) -> tuple[float, float]:
    """(RMS, pico) por trozos: sin la copia entera en float64 (con 10 minutos eran 440 MB más)."""
    suma, pico = 0.0, 0.0
    paso = 1 << 18
    for i in range(0, len(datos), paso):
        trozo = datos[i:i + paso]
        plano = trozo.reshape(-1)
        suma += float(np.dot(plano.astype(np.float64), plano.astype(np.float64)))
        pico = max(pico, float(trozo.max()), -float(trozo.min()))
    return (math.sqrt(suma / datos.size) if datos.size else 0.0), pico


def _clave_sonido(ruta: Path) -> Optional[tuple]:
    try:
        st = ruta.stat()
    except OSError:
        return None
    return (os.path.normcase(str(ruta)), st.st_mtime_ns, st.st_size)


def _olvidar_sonido(ruta: Path) -> None:
    camino = os.path.normcase(str(ruta))
    with _CANDADO_SONIDOS:
        for clave in [c for c in _CACHE_SONIDOS if c[0] == camino]:
            del _CACHE_SONIDOS[clave]


def cargar_sonido(nombre: str) -> Optional[np.ndarray]:
    """Un sonido de "Mis sonidos" decodificado: (n, 2) float32 a 48 kHz, de solo lectura.

    None si el archivo no está (aunque estuviera en la caché: se mira el archivo cada vez).
    ``ValueError`` si no se puede leer, si no tiene sonido o si dura más de
    ``DURACION_MAX_SONIDO``. Queda en una caché LRU (por ruta, fecha y tamaño) de hasta
    ``MEMORIA_SONIDOS`` segundos de audio en total, con su RMS y su pico ya medidos.
    """
    cargado = _cargar_sonido(nombre)
    return cargado.datos if cargado is not None else None


def _cargar_sonido(nombre: str) -> Optional[_SonidoCargado]:
    ruta = _ruta_sonido(nombre)
    clave = _clave_sonido(ruta)
    if clave is None:
        return None
    with _CANDADO_SONIDOS:
        if clave in _CACHE_SONIDOS:
            _CACHE_SONIDOS.move_to_end(clave)
            return _CACHE_SONIDOS[clave]
    datos = _decodificar(ruta)
    cargado = _SonidoCargado(datos, *_medir(datos))
    with _CANDADO_SONIDOS:
        _CACHE_SONIDOS[clave] = cargado
        limite = int(MEMORIA_SONIDOS * FRECUENCIA)
        while len(_CACHE_SONIDOS) > 1 and sum(len(x.datos) for x in _CACHE_SONIDOS.values()) > limite:
            _CACHE_SONIDOS.popitem(last=False)
    return cargado


def _decodificar(ruta: Path) -> np.ndarray:
    """Todo el archivo a 48 kHz estéreo float32 (n, 2). Mono se duplica (sin los -3 dB de FFmpeg)."""
    av = _video().av
    try:
        contenedor = av.open(str(ruta))
    except Exception as error:
        raise ValueError(f"No se pudo abrir «{ruta.name}».") from error
    maximo = int(DURACION_MAX_SONIDO * FRECUENCIA)
    partes, total, largo = [], 0, False
    with contenedor:
        if not contenedor.streams.audio:
            raise ValueError(f"«{ruta.name}» no tiene sonido.")
        stream = contenedor.streams.audio[0]
        canales = 1 if (stream.codec_context.channels or 2) == 1 else 2
        remuestreo = av.AudioResampler(format="fltp", layout="mono" if canales == 1 else "stereo", rate=FRECUENCIA)
        try:
            for cuadro in contenedor.decode(stream):
                for c in remuestreo.resample(cuadro):
                    partes.append(c.to_ndarray())
                    total += c.samples
                if total > maximo:
                    largo = True
                    break
            if not largo:
                for c in remuestreo.resample(None):
                    partes.append(c.to_ndarray())
                    total += c.samples
        except (av.error.FFmpegError, ValueError):
            if not partes:   # ni un pedazo: no se puede usar
                raise ValueError(f"No se pudo leer «{ruta.name}».") from None
            # Se cortó a mitad (archivo dañado): queda lo que se pudo leer.
    if largo or total > maximo:
        raise ValueError(f"«{ruta.name}» dura más de {_minutos(DURACION_MAX_SONIDO)}: es demasiado largo para "
                         "un sonido.")
    if not total:
        raise ValueError(f"«{ruta.name}» no tiene sonido.")
    x = np.concatenate(partes, axis=1)
    if x.shape[0] == 1:
        x = np.repeat(x, 2, axis=0)
    datos = np.ascontiguousarray(x.T, dtype=np.float32)
    datos.flags.writeable = False
    return datos


# ---------------------------------------------------------------------------
# Fuentes del ambiente
# ---------------------------------------------------------------------------

class _FondoArchivo:
    """Un archivo usado de fondo, repetido con un fundido cruzado (ver "Fondos" arriba)."""

    def __init__(self, datos: np.ndarray):
        self.datos = datos
        largo = len(datos)
        self.X = min(int(round(CRUCE_FONDO * FRECUENCIA)), largo // 2)
        self.P = largo - self.X
        if self.X:
            u = (np.arange(self.X) + 0.5) / self.X
            entra = np.sin(0.5 * np.pi * u)[:, None]
            sale = np.cos(0.5 * np.pi * u)[:, None]
            # Los primeros X de cada vuelta: el principio entra mientras el final se va.
            self.cruce = (datos[:self.X] * entra + datos[self.P:] * sale).astype(np.float32)
        else:
            self.cruce = np.zeros((0, 2), np.float32)

    def leer(self, inicio: int, n: int) -> np.ndarray:
        if self.P <= 0:
            return np.zeros((n, 2), np.float32)
        t = np.arange(inicio, inicio + n, dtype=np.int64)
        i = np.where(t < self.P, t, t % self.P)
        salida = self.datos[i]
        cruce = (t >= self.P) & (i < self.X)
        if cruce.any():
            salida[cruce] = self.cruce[i[cruce]]
        return salida


def _rampa(x: np.ndarray) -> np.ndarray:
    """Coseno elevado de 0 a 1."""
    return 0.5 - 0.5 * np.cos(np.pi * np.clip(x, 0.0, 1.0))


def _limitar(x: np.ndarray) -> np.ndarray:
    """Limitador suave sin memoria: igual hasta ``LIMITE_SUAVE``; arriba, tanh hacia 1 (sin llegar)."""
    a = np.abs(x)
    if not a.size or float(a.max()) <= LIMITE_SUAVE:
        return x
    rango = 1.0 - LIMITE_SUAVE
    suave = np.sign(x) * (LIMITE_SUAVE + rango * np.tanh((a - LIMITE_SUAVE) / rango))
    return np.where(a > LIMITE_SUAVE, suave, x).astype(np.float32)


# ---------------------------------------------------------------------------
# El mezclador
# ---------------------------------------------------------------------------

def _misma_mezcla(a: ProyectoAudio, b: ProyectoAudio) -> bool:
    """Si dos proyectos dan lo mismo antes del paso final (volumen, normalizar y fundidos)."""
    return (a.ruta == b.ruta and a.tramos == b.tramos and a.sonido.silencios == b.sonido.silencios
            and a.voz == b.voz and a.fondos == b.fondos and a.sonidos == b.sonidos)


def _sonido_archivo(nombre: str) -> Optional[_SonidoCargado]:
    """Un sonido de "Mis sonidos" (con su RMS y su pico), o None si falta o no se puede usar (la mezcla lo saltea)."""
    try:
        return _cargar_sonido(nombre)
    except (ValueError, OSError):
        return None


class _Motor:
    """La mezcla antes del paso final (pasos 1 a 3 del módulo): voz, ambiente y cadena.

    Alimenta la cadena en la grilla fija de ``_PASO`` y guarda lo que ya salió en una
    cola. ``leer(n)`` da exactamente n muestras (menos solo al final) desde ``pos``.
    No es para usar desde varios hilos: en ``MezcladorAudio`` lo usa uno solo a la vez.
    """

    def __init__(self, proyecto: ProyectoAudio, voz, cadena: CadenaVoz, fondos: list, sueltos: list,
                 faltan: tuple, generadores: dict):
        self.proyecto = proyecto
        self.voz = voz                       # LectorPCM en float32 (mono o estéreo, como el archivo)
        self.mono = voz.canales == 1
        self.total = round(voz.duracion_resultado * FRECUENCIA)
        self.cadena = cadena
        self.fondos, self.sueltos, self.faltan = fondos, sueltos, faltan
        # GeneradorFondo por (clave, intensidad, semilla), uno por mezclador, y los sonidos generados por
        # ("suelto", clave, semilla): lo que se reusa en el próximo armado.
        self.generadores = generadores
        self.pre = 0 if proyecto.voz.sin_cambios() else round(PRELECTURA * FRECUENCIA)
        self.fundido = round(FUNDIDO_FONDO * FRECUENCIA)
        self.fundido_suelto = round(FUNDIDO_SUELTO * FRECUENCIA)
        self.cola: deque = deque()
        self.en_cola = 0
        self.pos = 0
        self.entrada = 0
        self.vaciado = False

    def saltar(self, muestra: int) -> None:
        """Deja todo listo para dar desde ``muestra`` del resultado (con la pre-lectura de la cadena)."""
        self.pos = min(self.total, max(0, int(muestra)))
        self.cola.clear()
        self.en_cola = 0
        inicio = max(0, self.pos - self.pre) // _PASO * _PASO   # en la grilla, como de corrido
        self.entrada = inicio
        self.vaciado = False
        self.cadena.reiniciar(inicio)
        self.voz.ir_a_resultado(inicio / FRECUENCIA)

    def _leer_voz(self, n: int) -> np.ndarray:
        x = self.voz.leer_array(n)
        if self.mono:
            x = np.repeat(x, 2, axis=1)
        if len(x) < n:   # no debería pasar (el total es el del lector): por las dudas, silencio
            x = np.concatenate((x, np.zeros((n - len(x), 2), np.float32)))
        return x

    def _ambiente(self, a: int, n: int) -> np.ndarray:
        """Fondos (con sus fundidos en el resultado) más sonidos sueltos, de la muestra ``a`` a ``a + n``."""
        amb = np.zeros((n, 2), np.float32)
        if self.fondos:
            for fuente, g in self.fondos:
                amb += fuente.leer(a, n) * g
            F, T = self.fundido, self.total
            if F and (a < F or a + n > T - F):
                o = np.arange(a, a + n) + 0.5
                amb *= (_rampa(o / F) * _rampa((T - o) / F)).astype(np.float32)[:, None]
        T, F = self.total, self.fundido_suelto
        for inicio, datos, g in self.sueltos:
            i, j = max(a, inicio), min(a + n, inicio + len(datos))
            if j <= i:
                continue
            parte = datos[i - inicio:j - inicio] * g
            if inicio + len(datos) > T and j > T - F:   # pasa el final del resultado: se apaga, no se corta en seco
                o = np.arange(i, j) + 0.5
                parte *= _rampa((T - o) / F).astype(np.float32)[:, None]
            amb[i - a:j - a] += parte
        return amb

    def _alimentar(self) -> None:
        """Procesa el próximo trozo de la grilla (o, ya en el final, vacía la cadena) y lo encola."""
        a = self.entrada
        if a >= self.total:
            desde = self.cadena.posicion_salida
            y = self.cadena.vaciar()
            self.vaciado = True
        else:
            b = min(self.total, (a // _PASO + 1) * _PASO)
            voz = self._leer_voz(b - a)
            amb = self._ambiente(a, b - a)
            desde = self.cadena.posicion_salida
            y = self.cadena.procesar(voz, amb, a)
            self.entrada = b
        fin_cola = self.pos + self.en_cola
        if desde > fin_cola:   # no pasa (la cadena entrega en orden): por las dudas, silencio en el hueco
            self.cola.append(np.zeros((desde - fin_cola, 2), np.float32))
            self.en_cola += desde - fin_cola
            fin_cola = desde
        saltear = fin_cola - desde   # lo de la pre-lectura (antes de la posición) no se entrega
        if saltear < len(y):
            parte = y[saltear:]
            self.cola.append(parte)
            self.en_cola += len(parte)

    def leer(self, n: int) -> np.ndarray:
        """Las próximas ``n`` muestras (menos solo al final), (m, 2) float32; avanza ``pos``."""
        n = max(0, min(int(n), self.total - self.pos))
        while self.en_cola < n and not self.vaciado:
            self._alimentar()
        partes, falta = [], n
        while falta > 0 and self.cola:
            x = self.cola[0]
            if len(x) <= falta:
                partes.append(x)
                self.cola.popleft()
                falta -= len(x)
            else:
                partes.append(x[:falta])
                self.cola[0] = x[falta:]
                falta = 0
        if falta:   # no pasa: si la cadena se quedó corta, silencio (así siempre se llega al final)
            partes.append(np.zeros((falta, 2), np.float32))
        self.en_cola = max(0, self.en_cola - n)
        self.pos += n
        if not partes:
            return np.zeros((0, 2), np.float32)
        return partes[0] if len(partes) == 1 else np.concatenate(partes)


def _preparar_motor(p: ProyectoAudio, anterior: Optional[_Motor], codec: bool) -> _Motor:
    """Un motor para ``p``, reusando del ``anterior`` lo que no cambió (lector de la voz, cadena, generadores).

    Lo nuevo se arma antes de tocar nada: si algo falla (la voz ya no está), el anterior sigue igual.
    """
    from .audio import LectorPCM
    if not isinstance(p, ProyectoAudio):
        raise TypeError("proyecto tiene que ser un ProyectoAudio.")
    a = anterior.proyecto if anterior is not None else None
    nueva_voz = a is None or (p.ruta, p.tramos) != (a.ruta, a.tramos)
    if nueva_voz:
        info = _info(p.ruta)
        canales = 1 if int(info.canales_audio or 2) == 1 else 2
        voz = LectorPCM(p.ruta, p.tramos, AjustesAudio(silencios=p.sonido.silencios), frecuencia=FRECUENCIA,
                        canales=canales, formato="f32")
    else:
        voz = anterior.voz
    try:
        if nueva_voz or (p.fondos, p.sonidos) != (a.fondos, a.sonidos):
            fondos, sueltos, faltan, generadores = _armar_ambiente(p, voz, anterior.generadores if anterior else {})
        else:
            fondos, sueltos, faltan = anterior.fondos, anterior.sueltos, anterior.faltan
            generadores = anterior.generadores
        cadena = anterior.cadena if a is not None and p.voz == a.voz else CadenaVoz(p.voz, codec=codec)
        # Al final, después de todo lo que puede fallar: cambia el lector compartido con el motor anterior.
        if not nueva_voz and p.sonido.silencios != a.sonido.silencios:
            voz.cambiar_ajustes(AjustesAudio(silencios=p.sonido.silencios))
    except BaseException:
        if nueva_voz:
            voz.cerrar()
        raise
    return _Motor(p, voz, cadena, fondos, sueltos, faltan, generadores)


def _armar_ambiente(p: ProyectoAudio, voz, generadores_antes: dict) -> tuple[list, list, tuple, dict]:
    """Las fuentes del ambiente: [(fuente, ganancia)], [(inicio, datos, ganancia)], lo que falta y los generadores."""
    am = _ambientes()
    fondos, sueltos, faltan = [], [], []
    generadores = {}
    for f in p.fondos:
        g = ganancia_volumen(f.volumen)
        if f.origen == "generado":
            if f.clave not in am.FONDOS:
                faltan.append(f.clave)
                continue
            clave = (f.clave, f.intensidad, f.semilla)
            fuente = generadores_antes.get(clave) or am.GeneradorFondo(f.clave, f.intensidad, f.semilla, FRECUENCIA)
            generadores[clave] = fuente
        else:
            cargado = _sonido_archivo(f.clave)
            if cargado is None:
                faltan.append(f.clave)
                continue
            g *= min(_NIVEL_FONDO / max(cargado.rms, 1e-12), _CALIBRACION_MAX)
            fuente = _FondoArchivo(cargado.datos)
        if g > 0:
            fondos.append((fuente, np.float32(g)))
    for s in p.sonidos:
        g = ganancia_volumen(s.volumen)
        if s.origen == "generado":
            if s.clave not in am.SONIDOS:
                faltan.append(s.clave)
                continue
            # Los ya generados en el armado anterior se reusan: la caché de ``ambientes`` guarda pocos y,
            # con más sonidos que eso, cada cambio de proyecto los volvía a sintetizar (medio segundo o más).
            clave = ("suelto", s.clave, s.semilla)
            datos = generadores_antes.get(clave)
            if datos is None:
                datos = am.generar_sonido(s.clave, s.semilla, FRECUENCIA)
            generadores[clave] = datos
        else:
            cargado = _sonido_archivo(s.clave)
            if cargado is None:
                faltan.append(s.clave)
                continue
            datos = cargado.datos
            g *= min(_PICO_SONIDO / max(cargado.pico, 1e-12), _CALIBRACION_MAX)
        if g > 0 and len(datos):
            inicio = round(voz.resultado_de_original(s.ancla) * FRECUENCIA)
            sueltos.append((inicio, datos, np.float32(g)))
    return fondos, sueltos, tuple(faltan), generadores


@dataclass(frozen=True)
class _Final:
    """El paso final, en muestras del resultado: ganancia y fundidos de entrada y de salida."""

    ganancia: float
    entrada: int
    salida: int
    total: int


def _paso_final(p: ProyectoAudio, pico: Optional[float], total: int, codec: bool) -> _Final:
    if p.sonido.normalizar and pico is None and total and not p.sonido.quitar:
        pico = _medir_pico(p, None, codec)
    return _Final(float(p.sonido.ganancia(pico if pico is not None else 1.0)),
                  round(p.sonido.fundido_entrada * FRECUENCIA), round(p.sonido.fundido_salida * FRECUENCIA), total)


def _terminar(final: _Final, o0: int, x: np.ndarray) -> np.ndarray:
    """Paso final: ganancia, fundidos de entrada y de salida del resultado y limitador."""
    n = len(x)
    if not n:
        return np.zeros((0, 2), np.float32)
    y = x * np.float32(final.ganancia)
    E, S, T = final.entrada, final.salida, final.total
    if (E and o0 < E) or (S and o0 + n > T - S):
        o = np.arange(o0, o0 + n) + 0.5
        g = np.ones(n)
        if E:
            g *= np.clip(o / E, 0.0, 1.0) ** 2
        if S:
            g *= np.clip((T - o) / S, 0.0, 1.0) ** 2
        y *= g.astype(np.float32)[:, None]
    return np.ascontiguousarray(_limitar(y), dtype=np.float32)


ADELANTO_VISTA_PREVIA = 1.0   # s de lectura adelantada que conviene para escuchar desde la interfaz


class MezcladorAudio:
    """El resultado del proyecto, listo para escuchar o para exportar (ver el docstring del módulo).

    Misma interfaz que ``audio.LectorPCM``: ``leer`` (bytes intercalados), ``leer_array``
    ((n, 2) float32), ``bytes_por_muestra``, ``ir_a`` (tiempo original), ``ir_a_resultado``,
    ``posicion``, ``posicion_resultado``, ``duracion_resultado``, ``terminado``, ``tiene_audio``,
    ``original_de_resultado``, ``resultado_de_original``, ``cambiar_ajustes``, ``cerrar`` y
    ``with``. Además, ``cambiar_proyecto``.

    proyecto  ``ProyectoAudio``.
    desde     instante del tiempo ORIGINAL donde empezar, como en ``LectorPCM`` (si cae en lo
              borrado, el tramo siguiente). Para el resultado, ``ir_a_resultado``.
    formato   "s16" (int16) o "f32" (float32), siempre a 48 kHz y en estéreo.
    pico      el de ``medir_pico_proyecto``, si se normaliza. Si falta, se mide al crearlo
              (con caché: la segunda vez es inmediato).
    codec     False saltea la compresión de la cadena aunque ``voz.compresion`` sea True
              (lo usa la exportación a WhatsApp con destino WhatsApp).
    adelanto  segundos de lectura adelantada en un hilo propio (0 = sin hilo).

    Dos maneras de leer:

    * **Directa** (``adelanto=0``, la de la exportación y la medición del pico): ``leer(n)``
      calcula en el momento y siempre da n muestras (menos solo al final). Determinista.
    * **Adelantada** (``adelanto=ADELANTO_VISTA_PREVIA``, para escuchar desde la interfaz): un
      hilo mantiene lleno un búfer de ese largo con la mezcla *antes* del paso final, así
      ``leer(n)`` vuelve enseguida (copiar y aplicar el volumen: menos de 1 ms) aunque un
      fondo tarde 200 ms en sintetizar una pasada. Si el búfer no alcanza (al arrancar o
      después de un salto), ``leer`` da **lo que haya, aunque sea nada**, sin rellenar con
      silencio: no se pierde nada y la posición (que sale de lo que de verdad sonó, como
      en ``reproductor_audio``) se queda quieta. ``faltaron`` suma esas muestras pedidas
      que no estaban. Lo que se entrega es idéntico a la lectura directa. ``ir_a`` e
      ``ir_a_resultado`` no esperan (el hilo salta en su próxima vuelta); ``cambiar_proyecto``
      arma lo nuevo en el hilo que llama (así los errores llegan) y el hilo lo cambia;
      un cambio solo de volumen, normalizar o fundidos se oye enseguida, sin vaciar el
      búfer. Cuando ``cambiar_proyecto`` vacía el búfer mientras suena, lo viejo y lo nuevo se
      funden en ``CRUCE_CAMBIO`` (10 ms): sin clic al mover un deslizador (un salto con
      ``ir_a`` no se funde). Si el búfer estaba casi vacío (no hay 10 ms de lo viejo), lo nuevo
      arranca desde la última muestra que sonó y la diferencia se va en esos 10 ms.
      ``cerrar(esperar)`` avisa al hilo y espera como mucho ``esperar`` segundos a que suelte
      el archivo (con 0 vuelve enseguida; el hilo lo suelta al terminar su vuelta, unos 50 a
      70 ms). Si el hilo falla (un disco que se desconectó), cuando se
      acaba lo que había en el búfer ``leer`` y ``leer_array`` **lanzan** ese error (también
      queda en ``error``); ``terminado`` sigue en False. Un salto o un cambio lo vuelve a intentar.
      El hilo no retiene al mezclador: si nadie lo cierra y se lo deja de usar, el hilo lo nota
      (en menos de ``_ESPERA_HILO``), suelta el archivo y termina. Igual conviene cerrarlo.

    ``faltan``: los fondos y sonidos que se saltearon (archivos que no están, claves que no
    existen), por su clave. Se puede usar desde varios hilos (un pedido a la vez). Cada
    mezclador tiene sus propios generadores de fondo (no se comparten: su candado bloquea
    mientras calculan).
    """

    FORMATOS = {"s16": np.int16, "f32": np.float32}

    def __init__(self, proyecto: ProyectoAudio, desde: float = 0.0, formato: str = "s16",
                 pico: Optional[float] = None, codec: bool = True, adelanto: float = 0.0):
        if formato not in self.FORMATOS:
            raise ValueError(f"Formato desconocido: {formato!r} (usá 's16' o 'f32').")
        self.formato = formato
        self.frecuencia = FRECUENCIA
        self.canales = 2
        self._codec = bool(codec)
        # Protege el estado de entrega. En el modo adelantado nunca se lo tiene mientras se calcula
        # (solo para copiar del búfer); en el directo, sí (no hay otro hilo).
        self._cond = threading.Condition()
        self._cambio = threading.Lock()       # un cambio de proyecto a la vez
        self.faltaron = 0
        self.error: Optional[BaseException] = None
        self._cerrado = False
        self._hilo: Optional[threading.Thread] = None
        motor = _preparar_motor(proyecto, None, self._codec)
        try:
            self._final = _paso_final(proyecto, pico, motor.total, self._codec)
        except BaseException:
            motor.voz.cerrar()
            raise
        self.proyecto = proyecto
        self._motor = motor          # el que calcula (en modo adelantado, solo lo toca el hilo)
        self._ultimo = motor         # el más nuevo (pendiente o no): mapas de tiempo y base para el próximo
        self.faltan = motor.faltan
        self._total = motor.total
        self._pos = self._muestra_de_original(desde)   # próxima muestra que se entrega
        self._adelanto = max(0, round(_numero(adelanto, 0.0) * FRECUENCIA))
        if self._adelanto:
            self._bufer: deque = deque()
            self._en_bufer = 0
            self._generacion = 0
            self._pendiente: Optional[tuple] = (None, self._pos)   # (motor nuevo o None, muestra)
            self._cruce: Optional[tuple] = None   # (modo, desde, lo viejo, salto) tras un cambio
            self._ultima: Optional[np.ndarray] = None   # la última muestra entregada (antes del paso final)
            # El hilo recibe una referencia débil: no retiene al mezclador (ver _hilo_adelantado).
            self._hilo = threading.Thread(target=_hilo_adelantado, args=(weakref.ref(self), self._cond),
                                          name="MezcladorAudio", daemon=True)
            self._hilo.start()
        else:
            motor.saltar(self._pos)

    # ------------------------------------------------------------ datos
    @property
    def bytes_por_muestra(self) -> int:
        """Bytes de una muestra con sus dos canales (``QAudioFormat.bytesPerFrame``)."""
        return self.canales * np.dtype(self.FORMATOS[self.formato]).itemsize

    @property
    def tiene_audio(self) -> bool:
        return True

    @property
    def duracion_resultado(self) -> float:
        return self._total / FRECUENCIA

    @property
    def posicion_resultado(self) -> float:
        """Segundos del resultado de la próxima muestra que se va a entregar."""
        return self._pos / FRECUENCIA

    @property
    def posicion(self) -> float:
        """Instante del tiempo original de la próxima muestra (para mover el cursor)."""
        return self._ultimo.voz.original_de_resultado(self._pos / FRECUENCIA)

    @property
    def terminado(self) -> bool:
        """True al llegar al final. Un error del hilo no es un final: lo lanza ``leer``."""
        return self._pos >= self._total

    @property
    def adelantado(self) -> float:
        """Segundos listos en el búfer (modo adelantado; en el directo, 0)."""
        return self._en_bufer / FRECUENCIA if self._adelanto else 0.0

    def original_de_resultado(self, t: float) -> float:
        """Instante del original que suena en el segundo ``t`` del resultado."""
        return self._ultimo.voz.original_de_resultado(t)

    def resultado_de_original(self, t: float) -> float:
        """Segundo del resultado del instante ``t`` del original (si está borrado, el tramo siguiente)."""
        return self._ultimo.voz.resultado_de_original(t)

    def _muestra_de_original(self, t: float) -> int:
        return round(self._ultimo.voz.resultado_de_original(max(0.0, _numero(t, 0.0))) * FRECUENCIA)

    # ------------------------------------------------------------ control
    def ir_a(self, t: float) -> None:
        """Salta al instante ``t`` del tiempo original (si está borrado, al tramo siguiente)."""
        self._saltar(self._muestra_de_original(t))

    def ir_a_resultado(self, t: float) -> None:
        """Salta al segundo ``t`` del resultado."""
        self._saltar(round(max(0.0, _numero(t, 0.0)) * FRECUENCIA))

    def _saltar(self, muestra: int, motor: Optional[_Motor] = None) -> None:
        with self._cond:
            self._pos = min(self._total, max(0, int(muestra)))
            if not self._adelanto:
                if motor is not None:
                    self._cambiar_motor(motor)
                self._motor.saltar(self._pos)
                return
            if self._cerrado:   # llegó tarde: el hilo ya termina (y cierra el suyo)
                if motor is not None:
                    self._soltar(motor, conservar=(self._motor,))
                return
            if motor is not None:   # un cambio mientras suena: sin clic (ver "Dos maneras de leer")
                k = round(CRUCE_CAMBIO * FRECUENCIA)
                viejo = self._primeras(k)
                if len(viejo) == k:          # lo que iba a sonar se funde con lo nuevo
                    self._cruce = ("cruce", self._pos, viejo, None)
                elif self._ultima is not None:   # casi nada en el búfer: se empalma con lo último que sonó
                    self._cruce = ("empalme", self._pos, self._ultima, None)
                else:
                    self._cruce = None
            else:
                self._cruce = None
            self._bufer.clear()
            self._en_bufer = 0
            self._generacion += 1
            pendiente = self._pendiente[0] if self._pendiente is not None else None
            if motor is not None:
                if pendiente is not None:
                    self._soltar(pendiente, conservar=(motor, self._motor))   # nunca lo usó el hilo
                pendiente = motor
            self._pendiente = (pendiente, self._pos)
            self.error = None
            self._cond.notify_all()

    def _primeras(self, n: int) -> np.ndarray:
        """Copia de las primeras n muestras del búfer (o las que haya), sin sacarlas."""
        partes, falta = [], n
        for x in self._bufer:
            if falta <= 0:
                break
            partes.append(x[:falta])
            falta -= len(partes[-1])
        return np.concatenate(partes) if partes else np.zeros((0, 2), np.float32)

    def _cambiar_motor(self, nuevo: _Motor) -> None:
        viejo, self._motor = self._motor, nuevo
        if viejo is not nuevo:
            self._soltar(viejo, conservar=(nuevo,))

    @staticmethod
    def _soltar(motor: _Motor, conservar=()) -> None:
        """Cierra el lector de la voz de un motor que ya no se usa (si no lo comparte otro)."""
        if all(motor.voz is not otro.voz for otro in conservar if otro is not None):
            motor.voz.cerrar()

    def cambiar_proyecto(self, proyecto: ProyectoAudio, pico: Optional[float] = None) -> None:
        """Cambia el proyecto sin moverse del segundo del resultado en que está.

        Si solo cambia el paso final (volumen, normalizar o fundidos), sigue de corrido; si
        no, arma lo que cambió y sigue desde el mismo punto (con su pre-lectura). Con
        normalizar y sin ``pico``, lo mide (conviene pasarlo: medir es una pasada entera).
        """
        with self._cambio:
            if self._cerrado:
                raise ValueError("El mezclador ya está cerrado.")
            if _misma_mezcla(self.proyecto, proyecto):
                final = _paso_final(proyecto, pico, self._total, self._codec)
                with self._cond:
                    self.proyecto, self._final = proyecto, final
                return
            nuevo = _preparar_motor(proyecto, self._ultimo, self._codec)
            try:
                final = _paso_final(proyecto, pico, nuevo.total, self._codec)
            except BaseException:
                self._soltar(nuevo, conservar=(self._ultimo, self._motor))
                raise
            with self._cond:
                self.proyecto, self._final, self._ultimo = proyecto, final, nuevo
                self.faltan, self._total = nuevo.faltan, nuevo.total
                self._saltar(min(self._pos, nuevo.total), nuevo)

    def cambiar_ajustes(self, ajustes: AjustesAudio, pico: Optional[float] = None) -> None:
        """Como ``LectorPCM.cambiar_ajustes``: otro ``AjustesAudio`` para el mismo proyecto."""
        self.cambiar_proyecto(replace(self.proyecto, sonido=ajustes), pico)

    # ------------------------------------------------------------ leer
    def leer_array(self, muestras: int) -> np.ndarray:
        """Hasta ``muestras`` muestras como float32 (n × 2); vacío al terminar (ver "Dos maneras de leer")."""
        with self._cond:
            o0 = self._pos
            final = self._final
            if not self._adelanto:
                x = self._motor.leer(muestras)
                self._pos = self._motor.pos
            else:
                n = max(0, min(int(muestras), self._total - self._pos))
                x = self._sacar(n)
                if n and not len(x) and self.error is not None:
                    raise self.error.with_traceback(None)   # se acabó lo bueno: que la interfaz se entere
        return _terminar(final, o0, x)

    def _sacar(self, n: int) -> np.ndarray:
        """Hasta n muestras del búfer (modo adelantado; con ``_cond`` tomado)."""
        partes, falta = [], n
        while falta > 0 and self._bufer:
            x = self._bufer[0]
            if len(x) <= falta:
                partes.append(x)
                self._bufer.popleft()
                falta -= len(x)
            else:
                partes.append(x[:falta])
                self._bufer[0] = x[falta:]
                falta = 0
        dadas = n - falta
        o0 = self._pos
        self._en_bufer -= dadas
        self._pos += dadas
        self.faltaron += falta
        self._cond.notify_all()   # que el hilo vuelva a llenar
        if not partes:
            return np.zeros((0, 2), np.float32)
        x = partes[0] if len(partes) == 1 else np.concatenate(partes)
        if self._cruce is not None:
            x = self._fundir_cambio(o0, x)
        self._ultima = x[-1].copy()
        return x

    def _fundir_cambio(self, o0: int, x: np.ndarray) -> np.ndarray:
        """Sin clic después de ``cambiar_proyecto``: fundido cruzado con lo que iba a sonar o empalme.

        "cruce": los primeros ``CRUCE_CAMBIO`` van de lo viejo (las muestras que había en el
        búfer) a lo nuevo. "empalme": lo nuevo arranca desde la última muestra que sonó y la
        diferencia se va en ese mismo tiempo. Las dos con un coseno elevado.
        """
        modo, desde, viejo, salto = self._cruce
        k = round(CRUCE_CAMBIO * FRECUENCIA)
        a, b = max(o0, desde), min(o0 + len(x), desde + k)
        if b > a:
            j = np.arange(a - desde, b - desde)
            w = (0.5 - 0.5 * np.cos(np.pi * (j + 0.5) / k)).astype(np.float32)[:, None]
            x = x.copy()
            if modo == "cruce":
                x[a - o0:b - o0] = viejo[a - desde:b - desde] * (1 - w) + x[a - o0:b - o0] * w
            else:
                if salto is None:   # la primera muestra nueva es la de ``desde`` (b > a: está en este bloque)
                    salto = viejo - x[desde - o0]
                    self._cruce = (modo, desde, viejo, salto)
                x[a - o0:b - o0] += salto * (1 - w)
        if o0 + len(x) >= desde + k:
            self._cruce = None
        return x

    def leer(self, muestras: int) -> bytes:
        """Hasta ``muestras`` muestras en el formato del mezclador, intercaladas; b"" al terminar."""
        datos = self.leer_array(muestras)
        if self.formato == "s16":
            return _a_int16(datos).astype("<i2", copy=False).tobytes()
        return datos.astype("<f4", copy=False).tobytes()

    def _leer_sin_terminar(self, muestras: int) -> np.ndarray:
        """Para medir el pico (modo directo): la mezcla sin ganancia, sin fundidos y sin limitador."""
        with self._cond:
            x = self._motor.leer(muestras)
            self._pos = self._motor.pos
            return x

    # ------------------------------------------------------------ cerrar
    def cerrar(self, esperar: float = 0.0) -> None:
        """Suelta el archivo de la voz.

        En el modo adelantado avisa al hilo y espera como mucho ``esperar`` segundos a que
        termine (y suelte el archivo): con 0, vuelve enseguida y el hilo lo suelta al terminar
        su vuelta (unos 50 a 70 ms). Para borrar el archivo justo después, ``cerrar(1.0)``.
        """
        with self._cond:
            if not self._cerrado:
                self._cerrado = True
                self._cond.notify_all()
                if self._hilo is None:
                    self._motor.voz.cerrar()
        hilo = self._hilo
        if hilo is not None and esperar > 0 and hilo is not threading.current_thread():
            hilo.join(esperar)

    def __enter__(self) -> "MezcladorAudio":
        return self

    def __exit__(self, *_exc) -> None:
        self.cerrar()


_ESPERA_HILO = 0.2   # s: cada cuánto el hilo, sin trabajo, mira si el mezclador sigue vivo


def _hilo_adelantado(ref: "weakref.ReferenceType[MezcladorAudio]", cond: threading.Condition) -> None:
    """El hilo de la lectura adelantada: mantiene lleno el búfer del mezclador.

    Solo este hilo toca ``_motor`` en el modo adelantado. Tiene al mezclador con una
    referencia débil y lo suelta mientras espera: si nadie lo cerró y se lo deja de usar, se
    recolecta, el hilo lo nota, cierra el lector de la voz y termina.
    """
    motor: Optional[_Motor] = None
    m: Optional[MezcladorAudio] = None
    while True:
        with cond:
            m = ref()
            while m is not None and not m._cerrado and m._pendiente is None and (
                    m.error is not None or m._en_bufer >= m._adelanto or m._motor.pos >= m._motor.total):
                motor = m._motor
                m = None   # mientras espera no lo retiene
                cond.wait(_ESPERA_HILO)
                m = ref()
            if m is None or m._cerrado:
                break
            motor = m._motor
            pendiente, m._pendiente = m._pendiente, None
            generacion = m._generacion
        try:
            if pendiente is not None:
                nuevo, muestra = pendiente
                if nuevo is not None:
                    m._cambiar_motor(nuevo)
                    motor = nuevo
                m._motor.saltar(muestra)
                m = None
                continue
            x = m._motor.leer(_PASO)
        except Exception as error:   # el archivo se borró, un disco que se desconectó…: no se cae nada
            with cond:
                if generacion == m._generacion:
                    m.error = error
                cond.notify_all()
            m = None
            continue
        with cond:
            if generacion == m._generacion and m._pendiente is None and len(x):
                m._bufer.append(x)
                m._en_bufer += len(x)
            cond.notify_all()
        m = None
    if m is not None:   # lo cerraron
        with cond:
            pendiente = m._pendiente[0] if m._pendiente is not None else None
            m._pendiente = None
        if pendiente is not None:
            m._soltar(pendiente, conservar=(m._motor,))
        m._motor.voz.cerrar()
    elif motor is not None:   # nadie lo cerró y se recolectó: el archivo se suelta igual
        motor.voz.cerrar()


# ---------------------------------------------------------------------------
# Pico (para normalizar)
# ---------------------------------------------------------------------------

_CACHE_PICOS: "OrderedDict[tuple, float]" = OrderedDict()
_CANDADO_PICOS = threading.Lock()


def _clave_pico(p: ProyectoAudio, codec: bool) -> tuple:
    archivos = sorted({c.clave for c in p.fondos + p.sonidos if c.origen == "archivo"})
    claves = tuple((nombre, _clave_sonido(_ruta_sonido(nombre))) for nombre in archivos)
    return (_video()._clave_archivo(p.ruta), p.tramos, p.sonido.silencios, p.voz, p.fondos, p.sonidos, claves,
            bool(codec))


def _medir_pico(p: ProyectoAudio, cancelado: Optional[Callable[[], bool]], codec: bool,
                avance: Optional[Callable[[int, int], None]] = None) -> float:
    clave = _clave_pico(p, codec)
    with _CANDADO_PICOS:
        if clave in _CACHE_PICOS:
            _CACHE_PICOS.move_to_end(clave)
            return _CACHE_PICOS[clave]
    cancelado = cancelado or (lambda: False)
    base = replace(p, sonido=AjustesAudio(silencios=p.sonido.silencios))
    pico = 0.0
    with MezcladorAudio(base, formato="f32", codec=codec) as m:
        while True:
            if cancelado():
                raise Cancelado()
            bloque = m._leer_sin_terminar(_BLOQUE)
            if not len(bloque):
                break
            pico = max(pico, float(np.abs(bloque).max()))
            if avance is not None:
                avance(m._pos, m._total)
    with _CANDADO_PICOS:
        _CACHE_PICOS[clave] = pico
        while len(_CACHE_PICOS) > 32:
            _CACHE_PICOS.popitem(last=False)
    return pico


def _pico_en_cache(p: ProyectoAudio, codec: bool) -> bool:
    with _CANDADO_PICOS:
        return _clave_pico(p, codec) in _CACHE_PICOS


def medir_pico_proyecto(p: ProyectoAudio, cancelado: Optional[Callable[[], bool]] = None) -> float:
    """Pico (valor absoluto) del resultado sin normalizar, sin volumen, sin fundidos y sin limitador.

    Es una pasada del mismo mezclador (unas 10 veces más rápida que el tiempo real con una
    escena completa). Queda en caché por proyecto (sin contar volumen, normalizar ni fundidos)
    y por la fecha y el tamaño de los archivos. ``cancelado() -> True`` lanza ``Cancelado``.
    """
    return _medir_pico(p, cancelado, True)


# ---------------------------------------------------------------------------
# Exportar
# ---------------------------------------------------------------------------

FORMATOS_PROYECTO_INFO: dict[str, FormatoAudio] = {
    "whatsapp": FormatoAudio("whatsapp", ".ogg", "WhatsApp (nota de voz, Opus)", "libopus", "ogg", "flt"),
    "m4a": FORMATOS_AUDIO["m4a"],
    "mp3": FORMATOS_AUDIO["mp3"],
    "wav": FORMATOS_AUDIO["wav"],
}
_CANALES_FORMATO = {"whatsapp": 1, "m4a": 2, "mp3": 2, "wav": 2}
_BITS_FORMATO = {"whatsapp": 24_000, "m4a": 192_000, "mp3": 192_000, "wav": None}
_CUADRO_FORMATO = {"libopus": 960, "aac": 1024, "libmp3lame": 1152}
_FRECUENCIA_CODIFICADOR = {"whatsapp": 16000}   # a la que codifica (lo demás, a 48 kHz)
_OPCIONES_AAC = {"aac_is": "0", "aac_pns": "0"}   # ver _codificar
_EXTENSIONES_FORMATO = {".ogg": "whatsapp", ".opus": "whatsapp", ".m4a": "m4a", ".mp3": "mp3", ".wav": "wav"}


@lru_cache(maxsize=1)
def _disponibles() -> tuple[str, ...]:
    av = _video().av
    nombres = []
    for nombre in FORMATOS_PROYECTO:
        f = FORMATOS_PROYECTO_INFO[nombre]
        try:
            cc = av.CodecContext.create(f.codec, "w")
            cc.sample_rate = FRECUENCIA
            cc.layout = "mono" if _CANALES_FORMATO[nombre] == 1 else "stereo"
            cc.format = f.muestra
            if _BITS_FORMATO[nombre]:
                cc.bit_rate = _BITS_FORMATO[nombre]
            cc.open()
            nombres.append(nombre)
        except Exception:
            continue
    return tuple(nombres)


def formatos_proyecto_disponibles() -> list[FormatoAudio]:
    """Los formatos que este PyAV puede escribir, en orden (WhatsApp, M4A, MP3 si hay libmp3lame, WAV)."""
    return [FORMATOS_PROYECTO_INFO[n] for n in _disponibles()]


def ruta_salida_proyecto(p: ProyectoAudio, formato: str = "whatsapp") -> Path:
    """``voz_celular.ogg`` (o .m4a, .mp3, .wav) junto a la voz, sin pisar nada que ya exista."""
    from .imagen_io import ruta_salida_sugerida
    return ruta_salida_sugerida(p.ruta, FORMATOS_PROYECTO_INFO[formato].extension)


def _cuadro(datos: np.ndarray, muestra: str, layout: str, pts: int):
    """Bloque float32 (canales × n) -> ``av.AudioFrame`` en el formato del codificador."""
    from fractions import Fraction
    av = _video().av
    if muestra == "s16":
        cuadro = av.AudioFrame.from_ndarray(np.ascontiguousarray(_a_int16(datos).T).reshape(1, -1), format="s16",
                                            layout=layout)
    elif muestra == "flt":
        cuadro = av.AudioFrame.from_ndarray(np.ascontiguousarray(datos.T, dtype=np.float32).reshape(1, -1),
                                            format="flt", layout=layout)
    else:
        cuadro = av.AudioFrame.from_ndarray(np.ascontiguousarray(datos, dtype=np.float32), format="fltp",
                                            layout=layout)
    cuadro.sample_rate = FRECUENCIA
    cuadro.pts = pts
    cuadro.time_base = Fraction(1, FRECUENCIA)
    return cuadro


def _codificar(m: MezcladorAudio, temporal: str, nombre: str, avance: Callable[[int], None],
               cancelado: Callable[[], bool]) -> int:
    av = _video().av
    fmt = FORMATOS_PROYECTO_INFO[nombre]
    canales = _CANALES_FORMATO[nombre]
    layout = "mono" if canales == 1 else "stereo"
    opciones = {"movflags": "+faststart"} if fmt.contenedor == "ipod" else {}
    destino = av.open(temporal, "w", format=fmt.contenedor, container_options=opciones)
    try:
        # WhatsApp: Opus a 16 kHz, como las notas de voz de verdad y como la etapa 7 de la cadena (se
        # decodifica a 48 kHz igual). A 48 kHz, aun con cutoff, dejaba pasar de 8 a 9 kHz unos 6 dB más
        # que la vista previa. PyAV remuestrea al codificar (los cuadros van a 48 kHz).
        rate = _FRECUENCIA_CODIFICADOR.get(nombre, FRECUENCIA)
        stream = destino.add_stream(fmt.codec, rate=rate)
        stream.layout = layout
        stream.codec_context.format = fmt.muestra
        if _BITS_FORMATO[nombre]:
            stream.bit_rate = _BITS_FORMATO[nombre]
        if fmt.codec == "libopus":
            # Como una nota de voz: voz y banda ancha (hasta 8 kHz).
            stream.codec_context.options = {"application": "voip", "cutoff": "8000"}
        elif fmt.codec == "aac":
            # Sin "intensity stereo" ni PNS (ruido sintético en lugar de algunas bandas): a 192 kbit/s no ahorran
            # nada y, en un golpe fuerte, el AAC de FFmpeg se pasaba de 0 dBFS (medido en "Video en casa": +2,6 dB
            # con los dos, +1 dB solo con PNS; sin ellos, -0,5 dBFS y el mismo tamaño).
            stream.codec_context.options = _OPCIONES_AAC
        tamano = _CUADRO_FORMATO.get(fmt.codec, 4096)
        escritas, pendiente = 0, np.zeros((canales, 0), np.float32)
        while True:
            if cancelado():
                raise Cancelado()
            bloque = m.leer_array(_BLOQUE).T
            if canales == 1:
                bloque = bloque.mean(axis=0, keepdims=True)
            final = not bloque.shape[1]
            pendiente = np.concatenate((pendiente, bloque), axis=1) if pendiente.shape[1] else bloque
            usar = pendiente.shape[1] if final else pendiente.shape[1] - pendiente.shape[1] % tamano
            for pos in range(0, usar, tamano):
                trozo = pendiente[:, pos:min(pos + tamano, usar)]
                for paquete in stream.encode(_cuadro(trozo, fmt.muestra, layout, escritas)):
                    destino.mux(paquete)
                escritas += trozo.shape[1]
            pendiente = pendiente[:, usar:]
            avance(escritas)
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


def exportar_proyecto(
    p: ProyectoAudio,
    ruta_salida: Union[str, os.PathLike],
    formato: Optional[str] = None,
    progreso: Optional[Progreso] = None,
    cancelado: Optional[Callable[[], bool]] = None,
) -> ResultadoAudio:
    """Guarda el resultado del proyecto, con el mismo mezclador que la vista previa.

    formato     "whatsapp" (``.ogg``, Opus mono de 24 kbit/s a 16 kHz), "m4a", "mp3" o "wav"
                (``FORMATOS_PROYECTO``); None = según la extensión (``.ogg`` y ``.opus`` son WhatsApp).
    progreso    progreso(hechas, total, segundos_restantes o None). Con normalizar (y el pico
                todavía sin medir) cuenta las dos pasadas: medir y escribir.
    cancelado   cancelado() -> True para abandonar: se lanza ``Cancelado`` y no queda archivo.

    Se escribe a un temporal en la misma carpeta y se renombra al final; la voz nunca se toca.
    ``ValueError`` si el formato no existe o no está en esta instalación, si la salida es la
    voz, si el sonido está quitado o si no queda ningún tramo.
    """
    inicio_reloj = time.perf_counter()
    entrada, salida = Path(p.ruta), Path(ruta_salida)
    if not entrada.is_file():
        raise FileNotFoundError(f"No existe la voz: {entrada}")
    mv = _video()
    if mv._misma_ruta(entrada, salida):
        raise ValueError("Ese es el audio original. Para no sobrescribirlo, elegí otro nombre.")
    nombre = (formato or _EXTENSIONES_FORMATO.get(salida.suffix.lower(), salida.suffix.lstrip("."))).lower()
    if nombre not in FORMATOS_PROYECTO:
        raise ValueError(f"Formato de audio desconocido: {nombre!r}. Usá WhatsApp (.ogg), M4A, MP3 o WAV.")
    if nombre not in _disponibles():
        raise ValueError(f"Esta instalación no puede guardar {FORMATOS_PROYECTO_INFO[nombre].descripcion}.")
    if p.sonido.quitar:
        raise ValueError("El sonido está quitado: no hay nada para guardar.")
    if duracion_resultado(p) <= 0:
        raise ValueError("No queda ningún tramo para exportar: están todos borrados.")
    fmt = FORMATOS_PROYECTO_INFO[nombre]
    codec = not (nombre == "whatsapp" and p.voz.destino == "whatsapp")   # no comprimir dos veces en Opus
    cancelado = cancelado or (lambda: False)

    salida.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(prefix=f".{salida.stem}.", suffix=".parcial" + fmt.extension,
                                    dir=str(salida.parent))
    os.close(fd)
    try:
        total = round(duracion_resultado(p) * FRECUENCIA)
        medir = p.sonido.normalizar and not _pico_en_cache(p, codec)
        trabajo = 2 * total if medir else total
        t0 = time.perf_counter()

        def avisar(hechas: int) -> None:
            if progreso is None or not trabajo:
                return
            hechas = min(hechas, trabajo)
            pasado = time.perf_counter() - t0
            restante = pasado * (trabajo - hechas) / hechas if hechas and pasado > 0.05 else None
            progreso(hechas, trabajo, restante)

        pico = None
        if p.sonido.normalizar:
            pico = _medir_pico(p, cancelado, codec, (lambda h, _t: avisar(h)) if medir else None)
        base = total if medir else 0
        with MezcladorAudio(p, formato="f32", pico=pico, codec=codec) as m:
            escritas = _codificar(m, temporal, nombre, lambda h: avisar(base + h), cancelado)
        if cancelado():
            raise Cancelado()
        os.replace(temporal, salida)
    except BaseException:
        try:
            os.remove(temporal)
        except OSError:
            pass
        raise
    return ResultadoAudio(salida, nombre, escritas / FRECUENCIA, FRECUENCIA, _CANALES_FORMATO[nombre],
                          time.perf_counter() - inicio_reloj)


__all__ = [
    "FRECUENCIA", "CAPAS_MAX", "ORIGENES", "FUNDIDO_FONDO", "CRUCE_FONDO", "DURACION_MAX_SONIDO", "VOLUMEN_MAX_DB",
    "LIMITE_SUAVE", "FORMATOS_PROYECTO", "FORMATOS_PROYECTO_INFO", "EXTENSIONES_AUDIO", "NOMBRES_DESTINO",
    "NOMBRES_LUGAR", "ganancia_volumen", "FondoProyecto", "SonidoSuelto", "ProyectoAudio", "abrir_proyecto",
    "duracion_original", "duracion_resultado", "ancla_en_resultado", "Escena", "ESCENAS", "escenas_propias",
    "guardar_escena", "borrar_escena", "aplicar_escena", "describir", "carpeta_sonidos", "mis_sonidos",
    "agregar_a_mis_sonidos", "renombrar_sonido", "borrar_sonido", "cargar_sonido", "ADELANTO_VISTA_PREVIA",
    "MezcladorAudio",
    "medir_pico_proyecto", "formatos_proyecto_disponibles", "ruta_salida_proyecto", "exportar_proyecto",
]
