"""Documento de capas de NaturalShot Lite: capas de verdad, como en Photoshop. Sin Qt.

El documento
------------
Un ``Documento`` tiene ancho y alto y una pila de ``Capa``, de abajo hacia arriba:

* **la base** (siempre la primera, una sola): o la **foto** o un **fondo** de relleno.

  - **foto**: la foto con todo el procesado previo de hoy (geometría, montaje, borrado, recorte
    y fondo). No viene en el documento: ``componer`` la recibe ya hecha (``foto_rgb``). No se
    borra, pero se puede ocultar o bajar su opacidad. El ancho y el alto son los de la foto.
  - **relleno** (``Documento.nuevo_lienzo``, el "Archivo › Nuevo" de la Etapa 2): un color o un
    degradado que cubre el lienzo (``ID_FONDO``); sin relleno (tipo "ninguno") es transparente.
    Tampoco se borra ni se mueve. Con un fondo, ``componer`` no necesita foto (``foto_rgb=None``).

* Las capas del medio (de 0 a muchas), de estos tipos:

  - **imagen**: otra foto, un PNG con transparencia o un logo. Su contenido está en un
    ``AlmacenImagenes`` (por id) y se ubica con una ``Transformacion``.
  - **pixeles**: como imagen, pero es donde se pinta (pincel, borrador, bote): una capa vacía,
    rasterizada o la foto pasada a capa.
  - **texto** y **forma**: vectoriales; sus ``params`` (``texto.ParamsTexto`` y
    ``formas.ParamsForma``, de ``motor/texto.py`` y ``motor/formas.py``) se dibujan con
    ``renderizar_texto`` y ``renderizar_forma``. Para componer son una imagen cuyo tamaño
    natural es el del dibujo a escala 1, transformada por el centro como las imagen. Se vuelven
    a dibujar a la escala efectiva (vista × transformación, redondeada hacia arriba a pasos de
    2^(1/8), un 9 %), así no se pixelan, y se guardan en la caché por (params, escala).
  - **relleno**: un ``formas.Relleno`` que cubre todo el lienzo (sirve con máscara).
  - **grupo**: una carpeta. Sus hijos están **inmediatamente debajo** del grupo en la tupla,
    con ``padre`` = el id del grupo (se pueden anidar, hasta ``PROFUNDIDAD_MAX`` niveles). Se
    componen aparte, sobre transparente, y el resultado se funde como una capa más, con la
    opacidad, la fusión, la máscara, los estilos y la visibilidad del grupo.

* **ajuste_natural** (a lo sumo una, siempre la última): el filtro "celular natural" de
  siempre, aplicado sobre la composición de todo lo de abajo.

Las capas imagen, pixeles, texto, forma y grupo pueden tener **estilos** (``EstilosCapa``, de
``motor/estilos.py``: sombra, trazo, resplandor y superposiciones). Se aplican en las
coordenadas del documento, después de la transformación (como en Photoshop: girar la capa no
gira la sombra), a la escala de la salida.

Todo es inmutable (dataclasses congeladas, que se pueden guardar con pickle para el historial y
la sesión; ``Capa`` se guarda con sus ``params`` y ``estilos`` como diccionarios, así la sesión
solo necesita conocer ``Documento``, ``Capa`` y ``Transformacion``). Cada cambio (``agregar``,
``agregar_imagen``, ``quitar``, ``mover``, ``reubicar``, ``duplicar``, ``agrupar``,
``desagrupar``, ``con_capa``) devuelve otro documento y valida las reglas (la base no se borra
ni se mueve, el ajuste siempre arriba, los hijos de un grupo juntos y debajo de él, ids
únicos). ``bloqueada`` es solo un dato: la interfaz decide qué no se puede hacer con una capa
bloqueada. Las operaciones que necesitan píxeles (lienzo, rasterizar, combinar, acoplar, cajas)
son funciones del módulo que reciben el almacén.

Coordenadas
-----------
En píxeles del documento, continuas: el píxel (i, j) ocupa [i, i + 1) × [j, j + 1), así
que el centro del documento es (ancho / 2, alto / 2). ``Transformacion.x`` e ``y`` son el
centro de la capa; ``escala`` es sobre el tamaño original de la imagen (``escala_y``, si está,
es la vertical); ``rotacion`` en grados, positivo = horario (en pantalla, con la y hacia abajo);
``voltear_h`` y ``voltear_v`` espejan la imagen en su propio eje antes de girarla.
``matriz_transformacion`` y ``esquinas`` dan la cuenta (para las manijas de la interfaz).

Las imágenes y las máscaras
---------------------------
``AlmacenImagenes`` guarda arreglos uint8 de solo lectura por su contenido (un hash): el
historial guarda solo ids y no copia megas en cada paso. Imágenes RGBA (o RGB, opacas);
máscaras en gris del tamaño del documento (blanco = se ve, negro = no). Una imagen o una
máscara que no está en el almacén "falta" (``capas_faltantes``): la capa no se dibuja
(una máscara que falta se ignora).

componer
--------
1. La base es el fondo: ``foto_rgb`` (uint8, ya al tamaño de salida), o el relleno del fondo
   (si es opaco, se usa igual que una foto; si no, va como una capa más sobre transparente),
   con su opacidad, máscara y visibilidad. Sin base visible, el fondo es transparente.
2. Cada capa visible (de arriba de la base; un grupo, con todo lo de adentro) se convierte en
   un "elemento": RGBA uint8 **premultiplicado** en planos (4, h, w), en el rectángulo que
   ocupa. Las imagen, pixeles, texto y forma se premultiplican (así el borde no se ensucia de
   negro al interpolar) y se transforman con ``cv2.warpAffine`` (``INTER_LINEAR``; si una imagen
   se achica a menos de la mitad, antes ``cv2.resize`` con ``INTER_AREA``), con el alfa junto,
   solo en el rectángulo que ocupan; después, sus estilos. Se funden con las fórmulas de
   ``fusion`` (W3C, en float32 de 0 a 1, alfa "source-over"); en normal, multiplicar y trama
   sobre fondo opaco, con la misma fórmula despejada para no despremultiplicar.
3. Lo que quedó transparente se aplana sobre **blanco** (como "Acoplar imagen" de Photoshop)
   y se cuantiza a uint8 una sola vez. Para que sea rápido, la cuenta se hace solo en el
   rectángulo que cubren las capas, en planos (3, h, w) y por franjas de filas (ver
   ``_componer_abajo``); el resultado es el mismo que haciéndola en el cuadro entero.
4. El ajuste "celular natural": ``filtro`` recibe eso (RGB uint8) y su resultado se funde
   sobre lo mismo con la opacidad, el modo y la máscara de la capa. Visible al 100 %,
   normal y sin máscara: el resultado ES el del filtro. Sin capas extra y con la foto
   visible al 100 %, ``filtro`` recibe ``foto_rgb`` tal cual: la salida es
   ``filtro(foto_rgb)`` bit a bit (la de hoy).

``CacheComposicion`` guarda la imagen transformada de cada capa (por su contenido,
transformación y tamaño de salida), los dibujos de texto y forma por escala, los rellenos, los
grupos ya compuestos (por el estado de sus hijos: mover otra capa o cambiar la opacidad del
grupo no lo recompone), las capas con sus estilos, las máscaras ya escaladas y, para el ajuste,
"lo de abajo" y su resultado filtrado (por el estado de las capas de abajo, la foto y el
filtro): cambiar la opacidad, el modo o la máscara del ajuste, o el nombre de una capa, no
vuelve a llamar al filtro, y ocultar una capa y volver a mostrarla tampoco (queda en la caché).
**La interfaz tiene que pasar ``clave_foto`` y ``clave_filtro``** (y cambiarlas cuando cambian
la foto o los ajustes del filtro). Sin ellas, la foto se reconoce por un sello (su id, su forma
y un CRC de algunas filas; la caché no la retiene) y el filtro por identidad (la caché sí lo
retiene, para que su id no se reuse). La caché es para la vista previa: para exportar a
resolución completa, ``cache=None`` o una caché aparte. Con fotos grandes y muchas capas,
``componer`` va capa por capa para no tener todas las capas transformadas en memoria a la vez
(ver ``_componer_abajo``). Aparte, el módulo recuerda los dibujos de texto y forma a escala 1
(hasta ``_BYTES_GENERADOS``), que dan su tamaño natural y su caja.

Topes: un documento tiene como mucho ``LADO_MAX`` (65535) píxeles por lado y ``AREA_MAX``
(500 MP) en total.
"""

from __future__ import annotations

import hashlib
import importlib
import math
import numbers
import threading
import uuid
import zlib
from collections import OrderedDict
from dataclasses import dataclass, fields, replace
from typing import Callable, Hashable, Iterable, Optional

import cv2
import numpy as np

from .estilos import EstilosCapa, aplicar_premultiplicado, margenes
from .fusion import MODOS_FUSION, mezcla, mezclar, validar_modo

TIPOS_CAPA = ("foto", "imagen", "ajuste_natural", "pixeles", "texto", "forma", "relleno", "grupo")
TIPOS_CON_TRANSFORMACION = ("imagen", "pixeles", "texto", "forma")
TIPOS_GENERADOS = ("texto", "forma")
TIPOS_CON_ESTILOS = ("imagen", "pixeles", "texto", "forma", "grupo")
TIPOS_BASE = ("foto", "relleno")
ID_FOTO = "foto"
ID_AJUSTE = "celular_natural"
ID_FONDO = "fondo"
NOMBRE_FOTO = "Foto"
NOMBRE_AJUSTE = "Celular natural"
NOMBRE_FONDO = "Fondo"
PROFUNDIDAD_MAX = 16         # grupos dentro de grupos, como mucho
ACHICAR_CON_AREA = 0.5      # escala efectiva por debajo de la cual se achica primero con INTER_AREA
CACHE_BYTES = 768 * 2 ** 20  # memoria de una CacheComposicion, por defecto
CACHE_AJUSTES = 4            # resultados del filtro que se recuerdan
_PIXELES_FRANJA = 40_000     # píxeles por franja al componer (que entre en la caché del procesador)
LADO_MAX = 65535             # píxeles por lado de un documento, como mucho
AREA_MAX = 500_000_000       # píxeles de un documento, como mucho (500 MP)
ANCLAS = {                   # tamano_lienzo: dónde queda lo que había (fracción de lo que se agrega)
    "arriba_izquierda": (0.0, 0.0), "arriba": (0.5, 0.0), "arriba_derecha": (1.0, 0.0),
    "izquierda": (0.0, 0.5), "centro": (0.5, 0.5), "derecha": (1.0, 0.5),
    "abajo_izquierda": (0.0, 1.0), "abajo": (0.5, 1.0), "abajo_derecha": (1.0, 1.0),
}
MODOS_ALINEAR = ("izquierda", "centro_h", "derecha", "arriba", "centro_v", "abajo")
_LADO_RENDER = 8192          # píxeles por lado de un dibujo de texto o forma a la escala de la vista, como mucho
_AREA_RENDER = 40_000_000    # y en total
_PASOS_ESCALA = 8            # la escala de dibujo se redondea hacia arriba a pasos de 2^(1/8)

_F = np.float32


# ---------------------------------------------------------------------------
# Validaciones
# ---------------------------------------------------------------------------

def _real(valor, nombre: str) -> float:
    """Un número finito (no texto ni None)."""
    if (isinstance(valor, (str, bytes, bool, np.bool_)) or valor is None
            or not isinstance(valor, (numbers.Real, np.number))):
        raise ValueError(f"{nombre} tiene que ser un número (llegó {valor!r}).")
    v = float(valor)
    if not math.isfinite(v):
        raise ValueError(f"{nombre} tiene que ser un número finito (llegó {valor!r}).")
    return v


def _booleano(valor, nombre: str) -> bool:
    """Solo verdadero o falso (en el JSON, true o false): ni 0/1 ni texto."""
    if not isinstance(valor, (bool, np.bool_)):
        raise ValueError(f"{nombre} tiene que ser verdadero o falso (llegó {valor!r}).")
    return bool(valor)


def _id_opcional(valor, nombre: str) -> Optional[str]:
    if valor is None:
        return None
    if not isinstance(valor, str) or not valor:
        raise ValueError(f"{nombre} tiene que ser un id (texto no vacío) o None (llegó {valor!r}).")
    return valor


def _entero_positivo(valor, nombre: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, (numbers.Integral, np.integer)) or int(valor) < 1:
        raise ValueError(f"{nombre} tiene que ser un entero mayor que 0 (llegó {valor!r}).")
    return int(valor)


def _modulo(nombre: str):
    """``motor/texto.py`` o ``motor/formas.py`` (de M2), importados recién cuando hacen falta."""
    return importlib.import_module(f"{__package__}.{nombre}")


# Tipo de capa → (módulo, clase) de sus params.
_CLASE_PARAMS = {"texto": ("texto", "ParamsTexto"), "forma": ("formas", "ParamsForma"),
                 "relleno": ("formas", "Relleno")}


def _validar_params(tipo: str, params):
    """Los params de una capa de ese tipo (un dict se convierte), o ``ValueError``."""
    donde = _CLASE_PARAMS.get(tipo)
    if donde is None:
        if params is not None:
            raise ValueError(f"Las capas {tipo} no llevan params.")
        return None
    if params is None:
        raise ValueError(f"Las capas {tipo} llevan params (un {donde[1]}).")
    try:
        clase = getattr(_modulo(donde[0]), donde[1])
    except ImportError as error:
        raise ValueError(f"Para las capas {tipo} hace falta motor/{donde[0]}.py.") from error
    if isinstance(params, dict):
        try:
            params = clase.desde_dict(params)
        except (TypeError, KeyError, AttributeError) as error:
            raise ValueError(f"params inválidos para una capa {tipo} ({error}).") from error
    if not isinstance(params, clase):
        raise ValueError(f"Las capas {tipo} llevan un {donde[1]} (llegó {type(params).__name__}).")
    return params


# ---------------------------------------------------------------------------
# Transformación, capa y documento
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Transformacion:
    """Dónde va una capa imagen, pixeles, texto o forma (ver "Coordenadas" arriba).

    x, y       centro de la capa en píxeles del documento.
    escala     sobre el tamaño original de la imagen (> 0); con ``escala_y``, la horizontal.
    rotacion   en grados, positivo = horario.
    voltear_h  espejo horizontal (en el eje de la imagen, antes de girar).
    escala_y   la vertical (> 0), o None = igual a ``escala`` (como la Etapa 1).
    voltear_v  espejo vertical (en el eje de la imagen, antes de girar).
    """

    x: float = 0.0
    y: float = 0.0
    escala: float = 1.0
    rotacion: float = 0.0
    voltear_h: bool = False
    escala_y: Optional[float] = None
    voltear_v: bool = False

    def __post_init__(self):
        for campo in ("x", "y", "escala", "rotacion"):
            object.__setattr__(self, campo, _real(getattr(self, campo), campo))
        if self.escala <= 0:
            raise ValueError(f"La escala tiene que ser mayor que 0 (llegó {self.escala}).")
        object.__setattr__(self, "voltear_h", _booleano(self.voltear_h, "voltear_h"))
        if self.escala_y is not None:
            object.__setattr__(self, "escala_y", _real(self.escala_y, "escala_y"))
            if self.escala_y <= 0:
                raise ValueError(f"La escala vertical tiene que ser mayor que 0 (llegó {self.escala_y}).")
        object.__setattr__(self, "voltear_v", _booleano(self.voltear_v, "voltear_v"))

    @property
    def escala_vertical(self) -> float:
        """La escala vertical efectiva (``escala_y``, o ``escala`` si no está)."""
        return self.escala if self.escala_y is None else self.escala_y


_SIN_ESTILOS = EstilosCapa()


@dataclass(frozen=True)
class Capa:
    """Una capa del documento.

    id         único en el documento.
    tipo       uno de ``TIPOS_CAPA``.
    nombre     el que se ve en el panel.
    opacidad   de 0 a 1 (se acomoda a ese rango).
    fusion     clave de ``MODOS_FUSION``.
    imagen     id en ``AlmacenImagenes`` (solo y siempre en las "imagen" y "pixeles"): RGBA uint8
               (o RGB, opaca).
    transform  cuenta en las imagen, pixeles, texto y forma.
    mascara    id en ``AlmacenImagenes``: gris uint8 del tamaño del documento, o None.
    params     solo y siempre en las texto (``ParamsTexto``), forma (``ParamsForma``) y relleno
               (``Relleno``); un dict se convierte.
    estilos    ``EstilosCapa`` (un dict o None se convierten); solo en imagen, pixeles, texto,
               forma y grupo.
    padre      el id del grupo que la contiene, o None.
    """

    id: str
    tipo: str
    nombre: str
    visible: bool = True
    bloqueada: bool = False
    opacidad: float = 1.0
    fusion: str = "normal"
    imagen: Optional[str] = None
    transform: Transformacion = Transformacion()
    mascara: Optional[str] = None
    params: object = None
    estilos: EstilosCapa = _SIN_ESTILOS
    padre: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id:
            raise ValueError(f"El id de la capa tiene que ser un texto no vacío (llegó {self.id!r}).")
        if self.tipo not in TIPOS_CAPA:
            raise ValueError(f"Tipo de capa desconocido: {self.tipo!r}.")
        if not isinstance(self.nombre, str):
            raise ValueError(f"El nombre de la capa tiene que ser un texto (llegó {self.nombre!r}).")
        object.__setattr__(self, "visible", _booleano(self.visible, "visible"))
        object.__setattr__(self, "bloqueada", _booleano(self.bloqueada, "bloqueada"))
        object.__setattr__(self, "opacidad", min(1.0, max(0.0, _real(self.opacidad, "opacidad"))))
        validar_modo(self.fusion)
        object.__setattr__(self, "imagen", _id_opcional(self.imagen, "imagen"))
        object.__setattr__(self, "mascara", _id_opcional(self.mascara, "mascara"))
        if (self.tipo in ("imagen", "pixeles")) != (self.imagen is not None):
            raise ValueError("Las capas imagen y pixeles llevan imagen y las demás no.")
        if not isinstance(self.transform, Transformacion):
            raise ValueError("transform tiene que ser una Transformacion.")
        object.__setattr__(self, "params", _validar_params(self.tipo, self.params))
        estilos = self.estilos
        if estilos is None:
            estilos = _SIN_ESTILOS
        elif isinstance(estilos, dict):
            estilos = EstilosCapa.desde_dict(estilos)
        elif not isinstance(estilos, EstilosCapa):
            raise ValueError("estilos tiene que ser un EstilosCapa.")
        if self.tipo not in TIPOS_CON_ESTILOS and estilos != _SIN_ESTILOS:
            raise ValueError(f"Las capas {self.tipo} no llevan estilos.")
        if estilos == _SIN_ESTILOS:
            # Sin estilos, el campo no queda en la instancia (se lee el valor por defecto de la clase):
            # así una capa como las de la Etapa 1 tiene en vars() lo mismo que antes, y la sesión
            # (``sesion._reconstruir``, que rearma con vars() y rechaza los tipos que no conoce) la
            # sigue leyendo.
            self.__dict__.pop("estilos", None)
        else:
            object.__setattr__(self, "estilos", estilos)
        object.__setattr__(self, "padre", _id_opcional(self.padre, "padre"))
        if self.padre is not None and self.tipo in ("foto", "ajuste_natural"):
            raise ValueError("La foto y el ajuste no van dentro de un grupo.")
        if self.padre == self.id:
            raise ValueError("Una capa no puede ser su propio grupo.")

    def __reduce__(self):
        # Para pickle (historial y sesión): params y estilos como diccionarios, así quien lee solo
        # necesita conocer Capa y Transformacion (la sesión tiene una lista cerrada de clases).
        return (Capa, (self.id, self.tipo, self.nombre, self.visible, self.bloqueada, self.opacidad, self.fusion,
                       self.imagen, self.transform, self.mascara,
                       None if self.params is None else self.params.como_dict(),
                       None if self.estilos == _SIN_ESTILOS else self.estilos.como_dict(), self.padre))


_CAMPOS_CAPA = tuple(f.name for f in fields(Capa))
_CAMPOS_TRANSFORMACION = tuple(f.name for f in fields(Transformacion))
_CAMPOS_TRANSFORMACION_1 = ("x", "y", "escala", "rotacion", "voltear_h")   # los de la Etapa 1


def _bloque(capas, i: int) -> int:
    """Dónde empieza el bloque de la capa ``i`` (ella y, si es un grupo, todo lo de adentro, que
    está justo debajo)."""
    c = capas[i]
    if c.tipo != "grupo":
        return i
    ids = {c.id}
    j = i - 1
    while j >= 0 and capas[j].padre in ids:
        if capas[j].tipo == "grupo":
            ids.add(capas[j].id)
        j -= 1
    return j + 1


def _unidades(capas, desde: int, hasta: int) -> list[tuple[int, int]]:
    """Los bloques de hermanos en capas[desde:hasta], de abajo hacia arriba, como (inicio, fin)."""
    unidades = []
    i = hasta - 1
    while i >= desde:
        j = _bloque(capas, i)
        unidades.append((j, i + 1))
        i = j - 1
    unidades.reverse()
    return unidades


@dataclass(frozen=True)
class Documento:
    """La pila de capas (de abajo hacia arriba). Ver el módulo.

    Reglas: ``capas[0]`` es la base (la foto o un relleno, la única foto si hay); hay a lo sumo
    un "ajuste_natural" y, si está, es la última; los hijos de cada grupo están juntos, justo
    debajo de él (hasta ``PROFUNDIDAD_MAX`` niveles); ids únicos. ``ValueError`` si no se cumplen.
    """

    ancho: int
    alto: int
    capas: tuple

    def __post_init__(self):
        for campo in ("ancho", "alto"):
            v = getattr(self, campo)
            if isinstance(v, bool) or not isinstance(v, (numbers.Integral, np.integer)) or int(v) < 1:
                raise ValueError(f"{campo} tiene que ser un entero mayor que 0 (llegó {v!r}).")
            object.__setattr__(self, campo, int(v))
        if self.ancho > LADO_MAX or self.alto > LADO_MAX or self.ancho * self.alto > AREA_MAX:
            raise ValueError(f"El documento es demasiado grande ({self.ancho}×{self.alto}): como mucho "
                             f"{LADO_MAX} píxeles por lado y {AREA_MAX // 1_000_000} MP.")
        capas = tuple(self.capas or ())
        if not all(isinstance(c, Capa) for c in capas):
            raise ValueError("capas tiene que tener solo objetos Capa.")
        object.__setattr__(self, "capas", capas)
        if not capas or capas[0].tipo not in TIPOS_BASE:
            raise ValueError("La primera capa (la de abajo) tiene que ser la foto o un fondo de relleno.")
        tipos = [c.tipo for c in capas]
        if tipos.count("foto") > 1:
            raise ValueError("Un documento tiene una sola capa foto.")
        if "foto" in tipos[1:]:
            raise ValueError("La foto va siempre abajo de todo.")
        if tipos.count("ajuste_natural") > 1:
            raise ValueError("Un documento tiene a lo sumo una capa «Celular natural».")
        if "ajuste_natural" in tipos and tipos[-1] != "ajuste_natural":
            raise ValueError("La capa «Celular natural» va siempre arriba de todo.")
        if len({c.id for c in capas}) != len(capas):
            raise ValueError("Hay dos capas con el mismo id.")
        if capas[0].padre is not None:
            raise ValueError("La base no va dentro de un grupo.")
        # Grupos: de arriba hacia abajo, con la pila de grupos "abiertos". Una capa con padre tiene
        # que tener a su grupo abierto; al pasar a una capa de otro grupo, los de adentro se cierran.
        abiertos: list[str] = []
        for c in reversed(capas):
            while abiertos and abiertos[-1] != c.padre:
                abiertos.pop()
            if c.padre is not None and not abiertos:
                raise ValueError(f"La capa {c.id!r} no está justo debajo de su grupo {c.padre!r} "
                                 "(o ese grupo no existe).")
            if c.tipo == "grupo":
                abiertos.append(c.id)
                if len(abiertos) > PROFUNDIDAD_MAX:
                    raise ValueError(f"Demasiados grupos uno dentro de otro (como mucho {PROFUNDIDAD_MAX}).")

    # ---- creación y consulta

    @staticmethod
    def nuevo(ancho: int, alto: int) -> "Documento":
        """Foto (``ID_FOTO``) más el ajuste "Celular natural" (``ID_AJUSTE``), todo visible al 100 %."""
        return Documento(ancho, alto, (Capa(ID_FOTO, "foto", NOMBRE_FOTO),
                                       Capa(ID_AJUSTE, "ajuste_natural", NOMBRE_AJUSTE)))

    @staticmethod
    def nuevo_lienzo(ancho: int, alto: int, fondo=None, ajuste: bool = True) -> "Documento":
        """Un documento sin foto ("Archivo › Nuevo"): un fondo de relleno (``ID_FONDO``) con ese
        ``formas.Relleno`` (None = transparente) y, si ``ajuste``, el "Celular natural" arriba."""
        if fondo is None:
            fondo = _modulo("formas").Relleno("ninguno")
        capas = [Capa(ID_FONDO, "relleno", NOMBRE_FONDO, params=fondo)]
        if ajuste:
            capas.append(Capa(ID_AJUSTE, "ajuste_natural", NOMBRE_AJUSTE))
        return Documento(ancho, alto, tuple(capas))

    @property
    def base(self) -> Capa:
        """La capa de abajo: la foto o el fondo de relleno."""
        return self.capas[0]

    @property
    def foto(self) -> Capa:
        """La capa de abajo (como en la Etapa 1; en un documento sin foto, el fondo). Ver ``base``."""
        return self.capas[0]

    @property
    def tiene_foto(self) -> bool:
        """Si la base es una foto (``componer`` la necesita) o un relleno."""
        return self.capas[0].tipo == "foto"

    @property
    def ajuste(self) -> Optional[Capa]:
        """La capa "ajuste_natural", o None si el documento no la tiene."""
        return self.capas[-1] if self.capas[-1].tipo == "ajuste_natural" else None

    def indice(self, id_capa: str) -> int:
        """Posición en la pila (0 = la base). ``KeyError`` si no está."""
        for i, c in enumerate(self.capas):
            if c.id == id_capa:
                return i
        raise KeyError(f"No hay ninguna capa con id {id_capa!r}.")

    def capa(self, id_capa: str) -> Capa:
        return self.capas[self.indice(id_capa)]

    def ids_usados(self) -> set[str]:
        """Los ids del almacén que usa el documento (imágenes y máscaras)."""
        usados = {c.imagen for c in self.capas if c.imagen is not None}
        return usados | {c.mascara for c in self.capas if c.mascara is not None}

    def hijos(self, id_grupo: Optional[str]) -> tuple[Capa, ...]:
        """Las capas que están directamente en ese grupo (None = arriba de todo, sin la base ni el
        ajuste), de abajo hacia arriba."""
        return tuple(c for c in self.capas[1:self._tope()] if c.padre == id_grupo)

    def descendientes(self, id_grupo: str) -> tuple[Capa, ...]:
        """Todo lo que hay dentro de un grupo (a cualquier profundidad), de abajo hacia arriba."""
        i = self.indice(id_grupo)
        return self.capas[_bloque(self.capas, i):i]

    def ancestros(self, id_capa: str) -> tuple[str, ...]:
        """Los ids de los grupos que contienen a la capa, del más cercano al de más afuera."""
        por_id = {c.id: c for c in self.capas}
        salida = []
        p = self.capa(id_capa).padre
        while p is not None:
            salida.append(p)
            p = por_id[p].padre
        return tuple(salida)

    def id_libre(self) -> str:
        """Un id que no usa ninguna capa (para una capa nueva)."""
        return self._id_nuevo(None)

    # ---- cambios (funciones puras)

    def _con(self, capas) -> "Documento":
        return Documento(self.ancho, self.alto, tuple(capas))

    def _tope(self) -> int:
        """Índice donde termina la zona de las capas del medio (el del ajuste, o el largo)."""
        return len(self.capas) - 1 if self.ajuste is not None else len(self.capas)

    def _id_nuevo(self, pedido: Optional[str]) -> str:
        if pedido is not None:
            if any(c.id == pedido for c in self.capas):
                raise ValueError(f"Ya hay una capa con id {pedido!r}.")
            return pedido
        usados = {c.id for c in self.capas}
        while True:
            nuevo = uuid.uuid4().hex[:12]
            if nuevo not in usados:
                return nuevo

    def _movible(self, id_capa: str) -> int:
        """El índice de una capa que se puede mover, borrar o agrupar (ni la base ni el ajuste)."""
        i = self.indice(id_capa)
        c = self.capas[i]
        if i == 0:
            raise ValueError("La foto (o el fondo) va siempre abajo: no se borra ni se mueve (se puede ocultar).")
        if c.tipo == "ajuste_natural":
            raise ValueError("La capa «Celular natural» va siempre arriba: no se borra ni se mueve (se puede ocultar).")
        return i

    def _region(self, padre: Optional[str]) -> tuple[int, int]:
        """[desde, hasta) de las capas que están directamente o no dentro de ``padre`` (None = todo el medio)."""
        if padre is None:
            return 1, self._tope()
        g = self.indice(padre)
        return _bloque(self.capas, g), g

    def _insertar(self, capa: Capa, encima_de: Optional[str], dentro: Optional[str]) -> "Documento":
        if dentro is not None:
            g = self.indice(dentro)
            if self.capas[g].tipo != "grupo":
                raise ValueError(f"{dentro!r} no es un grupo.")
            i, padre = g, dentro
        elif encima_de is None:
            i, padre = self._tope(), None
        else:
            j = self.indice(encima_de)
            d = self.capas[j]
            if d.tipo == "ajuste_natural":
                i, padre = self._tope(), None
            else:
                i, padre = j + 1, d.padre
        capas = list(self.capas)
        capas.insert(max(1, i), replace(capa, padre=padre))
        return self._con(capas)

    def agregar_imagen(self, id_img: str, nombre: str, encima_de: Optional[str] = None,
                       transform: Optional[Transformacion] = None, id_capa: Optional[str] = None) -> "Documento":
        """Otro documento con una capa imagen nueva.

        Va justo arriba de ``encima_de`` (y en su mismo grupo), o arriba de todas las capas si es
        None, siempre debajo del ajuste. Sin ``transform``, centrada a escala 1
        (``transformacion_ajustada`` la achica para que entre). Sin ``id_capa``, un id nuevo al azar.
        """
        if transform is None:
            transform = Transformacion(self.ancho / 2, self.alto / 2)
        nueva = Capa(self._id_nuevo(id_capa), "imagen", nombre, imagen=id_img, transform=transform)
        return self._insertar(nueva, encima_de, None)

    def agregar(self, capa: Capa, encima_de: Optional[str] = None, dentro: Optional[str] = None) -> "Documento":
        """Otro documento con esa capa (de cualquier tipo salvo foto y ajuste; su id tiene que
        estar libre: ``id_libre``). Va justo arriba de ``encima_de`` (en su mismo grupo), arriba de
        todo dentro del grupo ``dentro``, o arriba de todas las capas. Su ``padre`` lo decide eso."""
        if not isinstance(capa, Capa):
            raise ValueError("Se esperaba una Capa.")
        if capa.tipo in ("foto", "ajuste_natural"):
            raise ValueError("La foto y el ajuste no se agregan: ya están (o no van).")
        self._id_nuevo(capa.id)
        return self._insertar(capa, encima_de, dentro)

    def quitar(self, id_capa: str) -> "Documento":
        """Sin esa capa (un grupo, con todo lo de adentro). La base y el ajuste no se borran (se
        ocultan): ``ValueError``."""
        c = self.capa(id_capa)
        if c.tipo == "foto":
            raise ValueError("La foto no se puede borrar (se puede ocultar).")
        if c.tipo == "ajuste_natural":
            raise ValueError("La capa «Celular natural» no se puede borrar (se puede ocultar).")
        i = self._movible(id_capa)
        return self._con(self.capas[:_bloque(self.capas, i)] + self.capas[i + 1:])

    def mover(self, id_capa: str, delta: int) -> "Documento":
        """La capa ``delta`` lugares más arriba (positivo) o más abajo (negativo) **entre sus
        hermanos** (un grupo se mueve con todo lo de adentro y una capa no sale de su grupo; para
        eso, ``reubicar``). No pasa la base ni el ajuste (se queda en el borde)."""
        i = self._movible(id_capa)
        desde, hasta = self._region(self.capas[i].padre)
        unidades = [u for u in _unidades(self.capas, desde, hasta) if self.capas[u[1] - 1].padre == self.capas[i].padre]
        k = next(n for n, u in enumerate(unidades) if u[1] - 1 == i)
        j = min(max(k + int(delta), 0), len(unidades) - 1)
        if j == k:
            return self
        unidades.insert(j, unidades.pop(k))
        medio = tuple(c for a, b in unidades for c in self.capas[a:b])
        return self._con(self.capas[:desde] + medio + self.capas[hasta:])

    def reubicar(self, id_capa: str, destino: str, donde: str = "encima") -> "Documento":
        """La capa (un grupo, con todo lo de adentro) pasa justo ``"encima"`` o ``"debajo"`` de
        ``destino`` (en su mismo grupo), o ``"dentro"`` del grupo ``destino`` (arriba de todo).
        Para arrastrar en el panel. ``ValueError`` si no se puede (un grupo dentro de sí mismo,
        debajo de la base, encima del ajuste…)."""
        i = self._movible(id_capa)
        inicio = _bloque(self.capas, i)
        bloque = self.capas[inicio:i + 1]
        if any(c.id == destino for c in bloque):
            raise ValueError("Una capa no se puede mover adentro de sí misma.")
        d = self.capa(destino)
        resto = self.capas[:inicio] + self.capas[i + 1:]
        k = next(n for n, c in enumerate(resto) if c.id == destino)
        if donde == "encima":
            if d.tipo == "ajuste_natural":
                raise ValueError("Arriba del «Celular natural» no va nada.")
            pos, padre = k + 1, d.padre
        elif donde == "debajo":
            if k == 0:
                raise ValueError("Debajo de la base no va nada.")
            if d.tipo == "ajuste_natural":
                pos, padre = k, None
            else:
                pos, padre = _bloque(resto, k), d.padre
        elif donde == "dentro":
            if d.tipo != "grupo":
                raise ValueError(f"{destino!r} no es un grupo.")
            pos, padre = k, d.id
        else:
            raise ValueError(f"donde es 'encima', 'debajo' o 'dentro' (llegó {donde!r}).")
        nuevo = bloque[:-1] + (replace(bloque[-1], padre=padre),)
        return self._con(resto[:pos] + nuevo + resto[pos:])

    def duplicar(self, id_origen: str, /, id_capa: Optional[str] = None) -> "Documento":
        """Una copia de la capa (un grupo, con copias de todo lo de adentro) justo arriba de ella
        (mismo contenido y propiedades, nombre "… copia"). Sin ``id_capa``, un id nuevo al azar.
        La base y el ajuste no se duplican (``ValueError``)."""
        i = self.indice(id_origen)
        if i == 0 or self.capas[i].tipo == "ajuste_natural":
            raise ValueError("La foto (o el fondo) y el ajuste no se duplican.")
        inicio = _bloque(self.capas, i)
        nuevo_id = self._id_nuevo(id_capa)
        usados = {c.id for c in self.capas} | {nuevo_id}
        mapa = {self.capas[i].id: nuevo_id}
        for c in self.capas[inicio:i]:
            while True:
                n = uuid.uuid4().hex[:12]
                if n not in usados:
                    break
            usados.add(n)
            mapa[c.id] = n
        copia = []
        for c in self.capas[inicio:i + 1]:
            cambios = {"id": mapa[c.id], "padre": mapa.get(c.padre, c.padre)}
            if c.id == id_origen:
                cambios["nombre"] = f"{c.nombre} copia"
            copia.append(replace(c, **cambios))
        return self._con(self.capas[:i + 1] + tuple(copia) + self.capas[i + 1:])

    def agrupar(self, ids: Iterable[str], nombre: str = "Grupo", id_grupo: Optional[str] = None) -> "Documento":
        """Mete esas capas (y grupos, con todo lo de adentro) en un grupo nuevo, que queda donde
        estaba la de más arriba (y en su grupo). Una capa elegida dentro de otro grupo elegido va
        con su grupo. Sin ``id_grupo``, un id nuevo al azar."""
        ids = list(dict.fromkeys(ids))
        if not ids:
            raise ValueError("Para agrupar hace falta al menos una capa.")
        for i in ids:
            self._movible(i)
        elegidos = set(ids)
        sel = [i for i in ids if not any(a in elegidos for a in self.ancestros(i))]
        indices = sorted(self.indice(i) for i in sel)
        arriba = self.capas[indices[-1]]
        gid = self._id_nuevo(id_grupo)
        bloques = [(_bloque(self.capas, i), i) for i in indices]
        en_bloque = {k for a, b in bloques for k in range(a, b + 1)}
        resto = [c for k, c in enumerate(self.capas) if k not in en_bloque]
        pos = sum(1 for k in range(indices[-1]) if k not in en_bloque)
        nuevos = []
        for a, b in bloques:
            nuevos.extend(self.capas[a:b])
            nuevos.append(replace(self.capas[b], padre=gid))
        grupo = Capa(gid, "grupo", nombre, padre=arriba.padre)
        return self._con(resto[:pos] + nuevos + [grupo] + resto[pos:])

    def desagrupar(self, id_grupo: str) -> "Documento":
        """Saca el grupo: lo de adentro queda en el mismo lugar, en el grupo de afuera."""
        g = self.capa(id_grupo)
        if g.tipo != "grupo":
            raise ValueError(f"{id_grupo!r} no es un grupo.")
        return self._con(replace(c, padre=g.padre) if c.padre == id_grupo else c
                         for c in self.capas if c.id != id_grupo)

    def con_capa(self, id_capa: str, /, **cambios) -> "Documento":
        """La capa con esos campos cambiados (``nombre``, ``visible``, ``opacidad``, ``fusion``,
        ``transform``, ``mascara``, ``params``, ``estilos``…). El id y el tipo no se cambian
        (``ValueError``); un campo que no existe da ``TypeError``."""
        if "id" in cambios or "tipo" in cambios:
            raise ValueError("El id y el tipo de una capa no se cambian.")
        i = self.indice(id_capa)
        capas = list(self.capas)
        capas[i] = replace(capas[i], **cambios)
        return self._con(capas)

    def _reemplazar(self, id_capa: str, nueva: Capa) -> "Documento":
        """La capa cambiada por otra (puede cambiar el tipo; para rasterizar y combinar)."""
        i = self.indice(id_capa)
        return self._con(self.capas[:i] + (nueva,) + self.capas[i + 1:])

    # ---- JSON

    def como_dict(self) -> dict:
        """Para JSON: solo tipos básicos. Lo nuevo de la Etapa 2 (params, estilos, padre, escala_y,
        voltear_v) va solo si no es el valor por defecto: un documento de la Etapa 1 da lo mismo."""
        capas = []
        for c in self.capas:
            d = {k: getattr(c, k) for k in ("id", "tipo", "nombre", "visible", "bloqueada", "opacidad", "fusion",
                                            "imagen", "mascara")}
            t = c.transform
            d["transform"] = {k: getattr(t, k) for k in _CAMPOS_TRANSFORMACION_1}
            if t.escala_y is not None:
                d["transform"]["escala_y"] = t.escala_y
            if t.voltear_v:
                d["transform"]["voltear_v"] = True
            if c.params is not None:
                d["params"] = c.params.como_dict()
            if c.estilos != _SIN_ESTILOS:
                d["estilos"] = c.estilos.como_dict()
            if c.padre is not None:
                d["padre"] = c.padre
            capas.append(d)
        return {"ancho": self.ancho, "alto": self.alto, "capas": capas}

    def usa_etapa2(self) -> bool:
        """Si usa algo que la Etapa 1 no conoce (para guardar el proyecto en el formato 1 o el 2)."""
        return any(c.tipo not in ("foto", "imagen", "ajuste_natural") or c.params is not None or c.padre is not None
                   or c.estilos != _SIN_ESTILOS or c.transform.escala_y is not None or c.transform.voltear_v
                   for c in self.capas)

    @staticmethod
    def desde_dict(datos) -> "Documento":
        """El de ``como_dict``. Campos desconocidos se ignoran; lo que falta o no vale: ``ValueError``."""
        try:
            if not isinstance(datos, dict) or not isinstance(datos.get("capas"), list):
                raise ValueError("faltan las capas")
            capas = []
            for c in datos["capas"]:
                if not isinstance(c, dict):
                    raise ValueError("capa inválida")
                t = c.get("transform", {})
                if not isinstance(t, dict):
                    raise ValueError("transformación inválida")
                transform = Transformacion(**{k: t[k] for k in _CAMPOS_TRANSFORMACION if k in t})
                otros = {k: c[k] for k in _CAMPOS_CAPA if k in c and k != "transform"}
                capas.append(Capa(transform=transform, **otros))
            return Documento(datos["ancho"], datos["alto"], tuple(capas))
        except ValueError as error:
            raise ValueError(f"Documento de capas inválido: {error}") from error
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError(f"Documento de capas inválido (falta o sobra algo: {error}).") from error


# ---------------------------------------------------------------------------
# Geometría de una capa
# ---------------------------------------------------------------------------

def _rotacion(grados: float) -> tuple[float, float]:
    """(cos, sen) exactos en los múltiplos de 90° (así 90° no deja bordes borrosos)."""
    if float(grados) % 90.0 == 0.0:
        k = int(round(float(grados) / 90.0)) % 4
        return ((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0))[k]
    r = math.radians(grados)
    return math.cos(r), math.sin(r)


def _lineal(t: Transformacion) -> np.ndarray:
    """2×2: voltear, escalar y girar (horario con la y hacia abajo)."""
    c, s = _rotacion(t.rotacion)
    giro = np.array([[c, -s], [s, c]])
    if t.escala_y is None and not t.voltear_v:   # la cuenta de la Etapa 1, tal cual
        return giro * t.escala @ np.diag([-1.0 if t.voltear_h else 1.0, 1.0])
    return giro @ np.diag([(-1.0 if t.voltear_h else 1.0) * t.escala,
                           (-1.0 if t.voltear_v else 1.0) * t.escala_vertical])


def matriz_transformacion(t: Transformacion, ancho_img: int, alto_img: int) -> np.ndarray:
    """2×3 que lleva coordenadas continuas de la imagen a las del documento."""
    a = _lineal(t)
    b = np.array([t.x, t.y]) - a @ np.array([ancho_img / 2.0, alto_img / 2.0])
    return np.hstack([a, b[:, None]])


def esquinas(t: Transformacion, ancho_img: int, alto_img: int) -> np.ndarray:
    """4×2: arriba-izquierda, arriba-derecha, abajo-derecha y abajo-izquierda de la imagen,
    en coordenadas del documento (para las manijas)."""
    m = matriz_transformacion(t, ancho_img, alto_img)
    p = np.array([[0, 0, 1], [ancho_img, 0, 1], [ancho_img, alto_img, 1], [0, alto_img, 1]], float)
    return p @ m.T


def transformacion_ajustada(ancho_img: int, alto_img: int, ancho_doc: int, alto_doc: int) -> Transformacion:
    """Centrada en el documento y, si no entra, achicada para que entre (nunca agrandada)."""
    escala = min(1.0, ancho_doc / max(1, ancho_img), alto_doc / max(1, alto_img))
    return Transformacion(ancho_doc / 2.0, alto_doc / 2.0, escala)


def tamano_salida(doc: Documento, escala: float = 1.0) -> tuple[int, int]:
    """(alto, ancho) de ``componer`` a esa escala: (round(alto·escala), round(ancho·escala)), al menos 1."""
    e = _real(escala, "escala")
    if e <= 0:
        raise ValueError(f"La escala tiene que ser mayor que 0 (llegó {escala}).")
    return max(1, round(doc.alto * e)), max(1, round(doc.ancho * e))


# ---------------------------------------------------------------------------
# Almacén de imágenes
# ---------------------------------------------------------------------------

class AlmacenImagenes:
    """Imágenes y máscaras en memoria, por contenido: el mismo arreglo da siempre el mismo id.

    Guarda una copia de solo lectura (cambiar el original después no la toca). Acepta
    uint8 en gris (h, w), RGB (h, w, 3) o RGBA (h, w, 4). Se puede usar desde varios hilos.
    """

    def __init__(self):
        self._datos: dict[str, np.ndarray] = {}
        self._candado = threading.Lock()

    @staticmethod
    def id_de(arr: np.ndarray) -> str:
        """El id de un arreglo: blake2b de 128 bits de su forma y sus bytes (32 letras hex)."""
        arr = np.ascontiguousarray(arr)
        h = hashlib.blake2b(digest_size=16)
        h.update(f"{arr.dtype.str}{arr.shape}".encode("ascii"))
        h.update(memoryview(arr).cast("B"))
        return h.hexdigest()

    @staticmethod
    def _validar(arr) -> np.ndarray:
        arr = np.asarray(arr)
        if arr.dtype != np.uint8:
            raise ValueError(f"Se esperaba uint8 (llegó {arr.dtype}).")
        if not (arr.ndim == 2 or (arr.ndim == 3 and arr.shape[2] in (3, 4))) or arr.size == 0:
            raise ValueError(f"Se esperaba gris (h, w), RGB (h, w, 3) o RGBA (h, w, 4) (llegó {arr.shape}).")
        return arr

    def guardar(self, arr: np.ndarray) -> str:
        """Lo guarda (si ya estaba, no copia nada) y devuelve su id."""
        arr = self._validar(arr)
        clave = self.id_de(arr)
        with self._candado:
            if clave in self._datos:
                return clave
        copia = np.array(arr, dtype=np.uint8, order="C", copy=True)
        copia.flags.writeable = False
        with self._candado:
            self._datos.setdefault(clave, copia)
        return clave

    def obtener(self, id_img: str) -> np.ndarray:
        """El arreglo (de solo lectura). ``KeyError`` si no está."""
        with self._candado:
            try:
                return self._datos[id_img]
            except KeyError:
                raise KeyError(f"No está la imagen {id_img!r}.") from None

    def ids(self) -> set[str]:
        with self._candado:
            return set(self._datos)

    def quitar(self, id_img: str) -> None:
        """Lo saca (si no estaba, no pasa nada). Ojo: un documento que lo use lo va a ver como "falta"."""
        with self._candado:
            self._datos.pop(id_img, None)

    def __contains__(self, id_img) -> bool:
        with self._candado:
            return id_img in self._datos

    def __len__(self) -> int:
        with self._candado:
            return len(self._datos)

    def __getstate__(self):
        with self._candado:
            return {"datos": dict(self._datos)}

    def __setstate__(self, estado):
        self._datos = dict(estado["datos"])
        for arr in self._datos.values():
            arr.flags.writeable = False
        self._candado = threading.Lock()


def capas_faltantes(doc: Documento, almacen: AlmacenImagenes) -> tuple[str, ...]:
    """Ids de las capas cuya imagen o máscara no está en el almacén (para marcarlas "falta")."""
    ids = almacen.ids()
    return tuple(c.id for c in doc.capas
                 if (c.imagen is not None and c.imagen not in ids) or (c.mascara is not None and c.mascara not in ids))


# ---------------------------------------------------------------------------
# Caché
# ---------------------------------------------------------------------------

class CacheComposicion:
    """Lo que ``componer`` puede reusar de una vez a la otra (ver el módulo). Es para la vista previa:
    para exportar a resolución completa, ``cache=None`` (o una caché aparte), así lo de la exportación
    no desplaza lo de la vista ni queda retenido.

    LRU con un tope de memoria (``max_bytes``, contando cada entrada al menos ``_COSTO_MINIMO``) y
    otro de resultados del filtro (``max_ajustes``). Se puede usar desde varios hilos (dos hilos
    pueden llegar a calcular lo mismo a la vez; da igual). ``limpiar()`` la vacía.

    Retiene, como mucho, ``max_ajustes`` referencias a funciones de filtro (para compararlas por
    identidad cuando no hay ``clave_filtro``); nunca retiene la foto que se le pasa a ``componer``.
    """

    def __init__(self, max_bytes: int = CACHE_BYTES, max_ajustes: int = CACHE_AJUSTES):
        self.max_bytes = int(max_bytes)
        self.max_ajustes = max(1, int(max_ajustes))
        self._entradas: "OrderedDict[tuple, tuple[object, int]]" = OrderedDict()
        self._bytes = 0
        self._ajustes = 0   # cuántas entradas son resultados del filtro
        self._candado = threading.Lock()

    @property
    def bytes_usados(self) -> int:
        with self._candado:
            return self._bytes

    def limpiar(self) -> None:
        with self._candado:
            self._entradas.clear()
            self._bytes = 0
            self._ajustes = 0

    def _obtener(self, clave: tuple):
        with self._candado:
            entrada = self._entradas.get(clave)
            if entrada is None:
                return None
            self._entradas.move_to_end(clave)
            return entrada[0]

    def _sacar(self, clave: tuple) -> None:
        """Saca una entrada (con el candado tomado)."""
        _valor, n = self._entradas.pop(clave)
        self._bytes -= n
        if clave[0] == "ajuste":
            self._ajustes -= 1

    def _guardar(self, clave: tuple, valor, nbytes: int) -> None:
        nbytes = max(_COSTO_MINIMO, int(nbytes))
        if nbytes > self.max_bytes:   # no entra: se usa y no se guarda
            return
        with self._candado:
            if clave in self._entradas:
                self._sacar(clave)
            self._entradas[clave] = (valor, nbytes)
            self._bytes += nbytes
            if clave[0] == "ajuste":
                self._ajustes += 1
                if self._ajustes > self.max_ajustes:   # el resultado del filtro más viejo
                    self._sacar(next(k for k in self._entradas if k[0] == "ajuste"))
            while self._bytes > self.max_bytes and len(self._entradas) > 1:
                self._sacar(next(iter(self._entradas)))


# ---------------------------------------------------------------------------
# Texto, forma y relleno: los dibujos
# ---------------------------------------------------------------------------

_BYTES_GENERADOS = 96 * 2 ** 20   # dibujos a escala 1 que recuerda el módulo
_GENERADOS: "OrderedDict[tuple, np.ndarray]" = OrderedDict()   # (tipo, params) → RGBA a escala 1
_NATURALES: "OrderedDict[tuple, tuple]" = OrderedDict()        # (tipo, params) → (ancho, alto, caja)
_CAJAS_IMAGEN: "OrderedDict[str, Optional[tuple]]" = OrderedDict()   # id → caja de lo que se ve
_MAX_NATURALES = 2048
_candado_generados = threading.Lock()
_bytes_generados = 0
_ERRORES_DIBUJO = (ImportError, ValueError, OSError, MemoryError)


def _limpiar_generados() -> None:
    """Olvida los dibujos y tamaños que recuerda el módulo (para las pruebas)."""
    global _bytes_generados
    with _candado_generados:
        _GENERADOS.clear()
        _NATURALES.clear()
        _CAJAS_IMAGEN.clear()
        _bytes_generados = 0


def _caja_alfa(alfa: np.ndarray) -> Optional[tuple[int, int, int, int]]:
    """(x0, y0, x1, y1) de lo que no es transparente, o None si es todo transparente."""
    x, y, w, h = cv2.boundingRect(np.ascontiguousarray(alfa))
    return None if w == 0 or h == 0 else (x, y, x + w, y + h)


def _renderizar(tipo: str, params, escala: float) -> np.ndarray:
    """El dibujo de un texto o una forma a esa escala: RGBA uint8 (de solo lectura)."""
    if tipo == "texto":
        img = _modulo("texto").renderizar_texto(params, escala)
    else:
        img = _modulo("formas").renderizar_forma(params, escala)
    img = np.asarray(img)
    if img.dtype != np.uint8 or img.ndim != 3 or img.shape[2] != 4 or img.size == 0:
        raise ValueError(f"El dibujo de la capa {tipo} no es RGBA uint8 (llegó {img.dtype} {img.shape}).")
    img = np.ascontiguousarray(img)
    img.flags.writeable = False
    return img


def _dibujo_natural(tipo: str, params) -> np.ndarray:
    """El dibujo a escala 1 (recordado por el módulo, hasta ``_BYTES_GENERADOS``)."""
    global _bytes_generados
    clave = (tipo, params)
    with _candado_generados:
        img = _GENERADOS.get(clave)
        if img is not None:
            _GENERADOS.move_to_end(clave)
            return img
    img = _renderizar(tipo, params, 1.0)
    with _candado_generados:
        if clave not in _GENERADOS and img.nbytes <= _BYTES_GENERADOS:
            _GENERADOS[clave] = img
            _bytes_generados += img.nbytes
            while _bytes_generados > _BYTES_GENERADOS and len(_GENERADOS) > 1:
                _bytes_generados -= _GENERADOS.popitem(last=False)[1].nbytes
        _NATURALES[clave] = (img.shape[1], img.shape[0], _caja_alfa(img[..., 3]))
        while len(_NATURALES) > _MAX_NATURALES:
            _NATURALES.popitem(last=False)
    return img


def _natural(tipo: str, params) -> Optional[tuple]:
    """(ancho, alto, caja) del dibujo a escala 1, o None si no se puede dibujar (falta el módulo…)."""
    with _candado_generados:
        n = _NATURALES.get((tipo, params))
    if n is not None:
        return n
    try:
        _dibujo_natural(tipo, params)
    except _ERRORES_DIBUJO:
        return None
    with _candado_generados:
        return _NATURALES.get((tipo, params))


def _escala_render(k: float, ancho: int, alto: int) -> float:
    """A qué escala dibujar un texto o una forma que en la salida queda a escala ``k``: hacia
    arriba, a pasos de 2^(1/8) (así no se pixela y no se redibuja a cada píxel de zoom), y sin
    pasar de ``_LADO_RENDER`` por lado ni ``_AREA_RENDER`` en total."""
    k = max(float(k), 1e-6)
    e = 2.0 ** (math.ceil(math.log2(k) * _PASOS_ESCALA - 1e-9) / _PASOS_ESCALA)
    tope = min(_LADO_RENDER / max(ancho, alto, 1), math.sqrt(_AREA_RENDER / max(1, ancho * alto)))
    return max(min(e, tope), 1.0 / 64.0)


def _caja_imagen(id_img: str, img: np.ndarray) -> Optional[tuple]:
    """Caja de lo que se ve de una imagen del almacén (recordada por id)."""
    with _candado_generados:
        if id_img in _CAJAS_IMAGEN:
            return _CAJAS_IMAGEN[id_img]
    caja = (0, 0, img.shape[1], img.shape[0]) if img.ndim == 2 or img.shape[2] == 3 else _caja_alfa(img[..., 3])
    with _candado_generados:
        _CAJAS_IMAGEN[id_img] = caja
        while len(_CAJAS_IMAGEN) > _MAX_NATURALES:
            _CAJAS_IMAGEN.popitem(last=False)
    return caja


def _relleno_rgba(rel, ancho: int, alto: int) -> np.ndarray:
    """RGBA uint8 (sin premultiplicar) de un relleno del tamaño del lienzo."""
    if rel.tipo == "color":
        img = np.empty((alto, ancho, 4), np.uint8)
        img[...] = rel.colores[0]
        return img
    if rel.tipo == "ninguno":
        return np.zeros((alto, ancho, 4), np.uint8)
    return np.asarray(_modulo("formas").renderizar_relleno(rel, ancho, alto))


def _relleno_opaco(rel, ancho: int, alto: int, cache: Optional[CacheComposicion]) -> Optional[np.ndarray]:
    """El RGB de un relleno opaco (todos sus colores con alfa 255), o None si no es opaco."""
    if rel.tipo == "ninguno" or any(c[3] != 255 for c in rel.colores):
        return None
    clave = ("fondo", rel, ancho, alto)
    if cache is not None:
        previo = cache._obtener(clave)
        if previo is not None:
            return previo
    if rel.tipo == "color":
        rgb = np.empty((alto, ancho, 3), np.uint8)
        rgb[...] = rel.colores[0][:3]
    else:
        rgb = np.ascontiguousarray(_relleno_rgba(rel, ancho, alto)[..., :3])
    rgb.flags.writeable = False
    if cache is not None:
        cache._guardar(clave, rgb, rgb.nbytes)
    return rgb


def _relleno_planos(rel, ancho: int, alto: int, cache: Optional[CacheComposicion]) -> Optional[np.ndarray]:
    """Un relleno del tamaño de la salida, premultiplicado en planos (4, alto, ancho) uint8 (None si
    es todo transparente)."""
    if rel.tipo == "ninguno":
        return None
    clave = ("relleno", rel, ancho, alto)
    if cache is not None:
        previo = cache._obtener(clave)
        if previo is not None:
            return previo[0]
    prem = cv2.cvtColor(np.ascontiguousarray(_relleno_rgba(rel, ancho, alto)), cv2.COLOR_RGBA2mRGBA)
    planos = None
    if cv2.countNonZero(cv2.extractChannel(prem, 3)):
        planos = np.empty((4, alto, ancho), np.uint8)
        for i in range(4):
            cv2.extractChannel(prem, i, planos[i])
        planos.flags.writeable = False
    if cache is not None:
        cache._guardar(clave, (planos,), 0 if planos is None else planos.nbytes)
    return planos


# ---------------------------------------------------------------------------
# componer
# ---------------------------------------------------------------------------

_R = _F(1.0 / 255.0)
_COSTO_MINIMO = 64   # bytes que cuenta como mínimo cada entrada de la caché (aunque esté vacía)
_FILAS_SELLO = 256   # filas de la foto que mira el sello (``_sello``)
_MEMORIA_CAPAS = 256 * 2 ** 20   # bytes de capas transformadas para componer por franjas (si no, de a una)


def _a_flotante(u8: np.ndarray) -> np.ndarray:
    """uint8 → float32 de 0 a 1 (misma forma)."""
    salida = np.empty(u8.shape, _F)
    np.multiply(u8, _R, out=salida, dtype=_F)
    return salida


def _a_planos(u8: np.ndarray) -> np.ndarray:
    """RGB uint8 (h, w, 3) (puede ser un recorte) → float32 en planos (3, h, w)."""
    salida = np.empty((3,) + u8.shape[:2], _F)
    np.multiply(np.moveaxis(u8, -1, 0), _R, out=salida, dtype=_F)
    return salida


def _de_planos(planos: np.ndarray) -> np.ndarray:
    """float32 en planos (3, h, w), de 0 a 1 → RGB uint8 (h, w, 3), redondeando al más cercano.

    ``cv2.convertScaleAbs`` satura a 0..255 y es mucho más rápido que hacerlo con numpy (en
    1920×1080: 1,9 ms contra 17). Un valor que viene de un uint8 vuelve exacto al mismo uint8.
    """
    return cv2.merge([cv2.convertScaleAbs(np.ascontiguousarray(planos[i]), alpha=255.0) for i in range(3)])


def _filas_franja(ancho: int) -> int:
    return max(8, _PIXELES_FRANJA // max(1, ancho))


def _sello(foto: np.ndarray) -> tuple:
    """Identifica una foto sin retenerla: su id, su forma y un CRC de unas ``_FILAS_SELLO`` filas
    repartidas (si la cambian en su lugar, casi seguro cambia). Cuesta menos de 1 ms en 1080p."""
    paso = max(1, foto.shape[0] // _FILAS_SELLO)
    return (id(foto), foto.shape, zlib.crc32(np.ascontiguousarray(foto[::paso]).data))


def _premultiplicada(img: np.ndarray) -> np.ndarray:
    """RGBA uint8 premultiplicado (una RGB, opaca)."""
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    if img.shape[2] == 3:
        return cv2.cvtColor(img, cv2.COLOR_RGB2RGBA)
    return cv2.cvtColor(img, cv2.COLOR_RGBA2mRGBA)


class _Contexto:
    """Lo que no cambia durante una llamada a ``componer`` (o a una operación que compone)."""

    __slots__ = ("almacen", "sx", "sy", "ancho", "alto", "cache", "hijos", "escala_estilos")

    def __init__(self, doc: Documento, almacen: AlmacenImagenes, ancho: int, alto: int,
                 cache: Optional[CacheComposicion]):
        self.almacen = almacen
        self.sx, self.sy = ancho / doc.ancho, alto / doc.alto
        self.ancho, self.alto = ancho, alto
        self.cache = cache
        self.escala_estilos = math.sqrt(self.sx * self.sy)
        # Capas visibles por grupo (None = arriba de todo), de abajo hacia arriba, sin la base ni el
        # ajuste. Lo que está dentro de un grupo oculto nunca se alcanza.
        self.hijos: dict = {}
        for c in doc.capas[1:doc._tope()]:
            if c.visible and c.opacidad > 0:
                self.hijos.setdefault(c.padre, []).append(c)


def _firma(c: Capa, ctx: _Contexto) -> tuple:
    """Lo que define los píxeles de una capa (sin nombre, id ni candado; un grupo, con sus hijos)."""
    almacen = ctx.almacen
    f = (c.tipo, c.opacidad, c.fusion, c.imagen, c.imagen is not None and c.imagen in almacen,
         c.transform if c.tipo in TIPOS_CON_TRANSFORMACION else None, c.mascara,
         c.mascara is not None and c.mascara in almacen, c.params, c.estilos)
    if c.tipo == "grupo":
        f += (tuple(_firma(h, ctx) for h in ctx.hijos.get(c.id, ())),)
    return f


def _geo_rect(t: Transformacion, iw: float, ih: float, sx: float, sy: float, lim: tuple) -> Optional[tuple]:
    """El rectángulo (x0, y0, x1, y1) que ocupa en la salida una imagen de tamaño natural iw × ih con
    esa transformación (con un píxel de margen), recortado a ``lim``; None si cae afuera."""
    a = _lineal(t)
    sa = np.diag([sx, sy]) @ a
    b = np.diag([sx, sy]) @ (np.array([t.x, t.y]) - a @ np.array([iw / 2.0, ih / 2.0]))
    puntos = np.array([[0, 0], [iw, 0], [iw, ih], [0, ih]], float) @ sa.T + b
    x0 = max(lim[0], math.floor(puntos[:, 0].min()) - 1)
    y0 = max(lim[1], math.floor(puntos[:, 1].min()) - 1)
    x1 = min(lim[2], math.ceil(puntos[:, 0].max()) + 1)
    y1 = min(lim[3], math.ceil(puntos[:, 1].max()) + 1)
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def _ampliar(lim: tuple, m: tuple) -> tuple:
    """Lo que hace falta de contenido para que los estilos (que crecen ``m`` = izq, arr, der, aba)
    llenen ``lim``: un píxel de contenido llega desde ``x - izq`` hasta ``x + der``."""
    return lim[0] - m[2], lim[1] - m[3], lim[2] + m[0], lim[3] + m[1]


def _estilos_de(c: Capa) -> Optional[EstilosCapa]:
    return None if c.tipo not in TIPOS_CON_ESTILOS or c.estilos.vacio else c.estilos


def _rect_contenido(c: Capa, ctx: _Contexto, lim: tuple) -> Optional[tuple]:
    """El rectángulo del contenido de una capa (sin estilos) en la salida, recortado a ``lim``."""
    if c.tipo == "grupo":
        rects = [r for h in ctx.hijos.get(c.id, ()) for r in (_rect(h, ctx, lim),) if r is not None]
        if not rects:
            return None
        return (min(r[0] for r in rects), min(r[1] for r in rects),
                max(r[2] for r in rects), max(r[3] for r in rects))
    if c.tipo == "relleno":
        x0, y0, x1, y1 = max(0, lim[0]), max(0, lim[1]), min(ctx.ancho, lim[2]), min(ctx.alto, lim[3])
        return None if x1 <= x0 or y1 <= y0 else (x0, y0, x1, y1)
    if c.tipo in ("imagen", "pixeles"):
        if c.imagen not in ctx.almacen:
            return None
        ih, iw = ctx.almacen.obtener(c.imagen).shape[:2]
    elif c.tipo in TIPOS_GENERADOS:
        nat = _natural(c.tipo, c.params)
        if nat is None:
            return None
        iw, ih = nat[0], nat[1]
    else:
        return None
    return _geo_rect(c.transform, iw, ih, ctx.sx, ctx.sy, lim)


def _rect(c: Capa, ctx: _Contexto, lim: tuple) -> Optional[tuple]:
    """El rectángulo que ocupa el elemento de la capa (con sus estilos) en la salida, recortado a ``lim``.
    Es exactamente el de ``_elemento`` (que puede ser None si queda todo transparente)."""
    est = _estilos_de(c)
    if est is None:
        return _rect_contenido(c, ctx, lim)
    m = margenes(est, ctx.escala_estilos)
    r = _rect_contenido(c, ctx, _ampliar(lim, m))
    if r is None:
        return None
    x0, y0 = max(lim[0], r[0] - m[0]), max(lim[1], r[1] - m[1])
    x1, y1 = min(lim[2], r[2] + m[2]), min(lim[3], r[3] + m[3])
    return None if x1 <= x0 or y1 <= y0 else (x0, y0, x1, y1)


def _a_planos_u8(warp: np.ndarray) -> Optional[np.ndarray]:
    """RGBA intercalado (h, w, 4) → planos (4, h, w) nuevos, de solo lectura (None si es todo transparente)."""
    if not cv2.countNonZero(cv2.extractChannel(warp, 3)):
        return None
    planos = np.empty((4,) + warp.shape[:2], np.uint8)
    for i in range(4):
        cv2.extractChannel(warp, i, planos[i])
    planos.flags.writeable = False
    return planos


def _prep_generado(c: Capa, r: float, cache: Optional[CacheComposicion]) -> Optional[np.ndarray]:
    """El dibujo de un texto o una forma a escala ``r``, premultiplicado (h, w, 4)."""
    clave = ("prep_gen", c.tipo, c.params, r)
    if cache is not None:
        previo = cache._obtener(clave)
        if previo is not None:
            return previo
    try:
        img = _dibujo_natural(c.tipo, c.params) if r == 1.0 else _renderizar(c.tipo, c.params, r)
    except _ERRORES_DIBUJO:
        return None
    prep = cv2.cvtColor(img, cv2.COLOR_RGBA2mRGBA)
    prep.flags.writeable = False
    if cache is not None:
        cache._guardar(clave, prep, prep.nbytes)
    return prep


def _contenido_transformado(c: Capa, ctx: _Contexto, lim: tuple) -> Optional[tuple]:
    """Una capa imagen, pixeles, texto o forma en su rectángulo de la salida: (clave, planos, x0, y0)
    con los planos RGBA uint8 premultiplicados (4, h, w), o None si no se ve."""
    t = c.transform
    k_vista = min(ctx.sx, ctx.sy)
    if c.tipo in ("imagen", "pixeles"):
        if c.imagen not in ctx.almacen:
            return None
        forma = ctx.almacen.obtener(c.imagen).shape
        ih, iw = forma[:2]
        # Achicar con INTER_AREA: se decide con la escala efectiva en la salida (la de la capa por la
        # de la vista), por eje. Por eso una capa puede pasar por INTER_AREA en la vista previa (que
        # achica) y no en la exportación: las dos son correctas, pero no coinciden píxel a píxel.
        kx, ky = t.escala * k_vista, t.escala_vertical * k_vista
        if t.escala_y is None:
            nw, nh = (max(1, round(iw * kx)), max(1, round(ih * kx))) if kx < ACHICAR_CON_AREA else (iw, ih)
        else:
            nw = max(1, round(iw * kx)) if kx < ACHICAR_CON_AREA else iw
            nh = max(1, round(ih * ky)) if ky < ACHICAR_CON_AREA else ih
        fuente = c.imagen
    else:
        nat = _natural(c.tipo, c.params)
        if nat is None:
            return None
        iw, ih = nat[0], nat[1]
        r = _escala_render(max(t.escala, t.escala_vertical) * max(ctx.sx, ctx.sy), iw, ih)
        fuente = ("gen", c.tipo, c.params, r)
    rect = _geo_rect(t, iw, ih, ctx.sx, ctx.sy, lim)
    if rect is None:
        return None
    x0, y0, x1, y1 = rect
    clave = ("capa", fuente, t, ctx.sx, ctx.sy, ctx.ancho, ctx.alto, lim)
    if ctx.cache is not None:
        previa = ctx.cache._obtener(clave)
        if previa is not None:
            return None if previa[0] is None else (clave, previa[0], x0, y0)
    # La imagen preparada (premultiplicada y, si hace falta, achicada con INTER_AREA o dibujada a escala).
    if c.tipo in ("imagen", "pixeles"):
        clave_prep = ("prep", c.imagen, nw, nh)
        prep = ctx.cache._obtener(clave_prep) if ctx.cache is not None else None
        if prep is None:
            img = ctx.almacen.obtener(c.imagen)
            prep = _premultiplicada(img)
            if (nw, nh) != (img.shape[1], img.shape[0]):
                prep = cv2.resize(prep, (nw, nh), interpolation=cv2.INTER_AREA)
            prep.flags.writeable = False
            if ctx.cache is not None:
                ctx.cache._guardar(clave_prep, prep, prep.nbytes)
    else:
        prep = _prep_generado(c, r, ctx.cache)
        if prep is None:
            return None
        nh, nw = prep.shape[:2]
    a = _lineal(t)
    lin = np.diag([ctx.sx, ctx.sy]) @ a @ np.diag([iw / nw, ih / nh])
    b = np.diag([ctx.sx, ctx.sy]) @ (np.array([t.x, t.y]) - a @ np.array([iw / 2.0, ih / 2.0]))
    # Coordenadas de píxel de OpenCV (centro del píxel 0 en 0): p_cv = p_continua - 0,5.
    m = np.hstack([lin, (lin @ np.array([0.5, 0.5]) + b - 0.5 - np.array([x0, y0]))[:, None]])
    warp = cv2.warpAffine(prep, m, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    planos = _a_planos_u8(warp)   # una sola copia, a un arreglo nuevo en planos (4, h, w)
    del warp
    if ctx.cache is not None:
        ctx.cache._guardar(clave, (planos,), 0 if planos is None else planos.nbytes)
    return None if planos is None else (clave, planos, x0, y0)


def _contenido(c: Capa, ctx: _Contexto, lim: tuple) -> Optional[tuple]:
    """El contenido de una capa (sin estilos), recortado a ``lim``: (clave, planos, x0, y0) o None."""
    if c.tipo == "grupo":
        hijos = ctx.hijos.get(c.id, ())
        if not hijos:
            return None
        clave = ("grupo", tuple(_firma(h, ctx) for h in hijos), ctx.sx, ctx.sy, ctx.ancho, ctx.alto, lim)
        if ctx.cache is not None:
            previo = ctx.cache._obtener(clave)
            if previo is not None:
                return None if previo[0] is None else (clave,) + previo
        hecho = _componer_lista(hijos, ctx, lim)
        if ctx.cache is not None:
            ctx.cache._guardar(clave, hecho if hecho is not None else (None,),
                               0 if hecho is None else hecho[0].nbytes)
        return None if hecho is None else (clave,) + hecho
    if c.tipo == "relleno":
        r = _rect_contenido(c, ctx, lim)
        planos = None if r is None else _relleno_planos(c.params, ctx.ancho, ctx.alto, ctx.cache)
        if planos is None:
            return None
        x0, y0, x1, y1 = r
        return ("relleno", c.params, ctx.ancho, ctx.alto, r), planos[:, y0:y1, x0:x1], x0, y0
    if c.tipo in TIPOS_CON_TRANSFORMACION:
        return _contenido_transformado(c, ctx, lim)
    return None


def _elemento(c: Capa, ctx: _Contexto, lim: tuple) -> Optional[tuple]:
    """La capa lista para fundir: (planos, x0, y0), RGBA uint8 premultiplicado (4, h, w) en el
    rectángulo de ``_rect``, con sus estilos; None si no se ve."""
    est = _estilos_de(c)
    if est is None:
        e = _contenido(c, ctx, lim)
        return None if e is None else e[1:]
    m = margenes(est, ctx.escala_estilos)
    e = _contenido(c, ctx, _ampliar(lim, m))
    if e is None:
        return None
    clave_c, planos, x0, y0 = e
    clave = ("estilo", clave_c, est, ctx.escala_estilos, lim)
    if ctx.cache is not None:
        previo = ctx.cache._obtener(clave)
        if previo is not None:
            return None if previo[0] is None else previo
    hecho = (None,)
    p2, (dx, dy) = aplicar_premultiplicado(np.ascontiguousarray(planos), est, ctx.escala_estilos)
    nx0, ny0 = x0 + dx, y0 + dy
    ax0, ay0 = max(lim[0], nx0), max(lim[1], ny0)
    ax1, ay1 = min(lim[2], nx0 + p2.shape[2]), min(lim[3], ny0 + p2.shape[1])
    if ax1 > ax0 and ay1 > ay0:
        recorte = np.ascontiguousarray(p2[:, ay0 - ny0:ay1 - ny0, ax0 - nx0:ax1 - nx0])
        if cv2.countNonZero(recorte[3]):
            recorte.flags.writeable = False
            hecho = (recorte, ax0, ay0)
    if ctx.cache is not None:
        ctx.cache._guardar(clave, hecho, 0 if hecho[0] is None else hecho[0].nbytes)
    return None if hecho[0] is None else hecho


def _mascara(id_mascara: Optional[str], almacen: AlmacenImagenes, ancho: int, alto: int,
             cache: Optional[CacheComposicion]) -> Optional[np.ndarray]:
    """La máscara a la escala de salida, en uint8 (None si no hay o si falta). Se pasa a float
    de a franjas (en float32 ocuparía 4 veces más: 96 MB en vez de 24 a 24 MP)."""
    if id_mascara is None or id_mascara not in almacen:
        return None
    clave = ("mascara", id_mascara, ancho, alto)
    if cache is not None:
        previa = cache._obtener(clave)
        if previa is not None:
            return previa
    m = almacen.obtener(id_mascara)
    if m.ndim == 3:
        m = np.ascontiguousarray(m[..., 0])
    if m.shape != (alto, ancho):
        achica = ancho <= m.shape[1] and alto <= m.shape[0]
        m = cv2.resize(m, (ancho, alto), interpolation=cv2.INTER_AREA if achica else cv2.INTER_LINEAR)
        m.flags.writeable = False
    if cache is not None:
        cache._guardar(clave, m, m.nbytes)
    return m


def _trozo(m: np.ndarray, y0: int, y1: int, x0: int, x1: int) -> np.ndarray:
    """m[y0:y1, x0:x1]; lo que cae fuera de la máscara (los estilos pueden pedir contenido de afuera
    del documento) cuenta como blanco (se ve)."""
    if y0 >= 0 and x0 >= 0 and y1 <= m.shape[0] and x1 <= m.shape[1]:
        return m[y0:y1, x0:x1]
    salida = np.full((y1 - y0, x1 - x0), 255, np.uint8)
    a0, a1, b0, b1 = max(y0, 0), min(y1, m.shape[0]), max(x0, 0), min(x1, m.shape[1])
    if a1 > a0 and b1 > b0:
        salida[a0 - y0:a1 - y0, b0 - x0:b1 - x0] = m[a0:a1, b0:b1]
    return salida


def _aplicar_capa(fondo: np.ndarray, alfa: Optional[np.ndarray], color: np.ndarray, a: np.ndarray,
                  capa: Capa, mascara: Optional[np.ndarray]) -> None:
    """Funde la capa sobre ``fondo`` (3, h, w) y ``alfa`` (h, w; None = opaco), en su lugar.

    ``color`` (3, h, w) premultiplicado y ``a`` (h, w) son de la capa; ``mascara`` (h, w), float
    de 0 a 1, o None. Todo del mismo tamaño (ya recortado a la parte que se pisa).
    """
    factor = None   # opacidad × máscara (None = 1)
    if mascara is not None:
        factor = mascara if capa.opacidad >= 1 else mascara * _F(capa.opacidad)
    elif capa.opacidad < 1:
        factor = _F(capa.opacidad)
    a_ef = a if factor is None else a * factor
    if alfa is None and capa.fusion in ("normal", "multiplicar", "pantalla"):
        # Fondo opaco: fondo + αs·(B - fondo) con αs·Cs = factor·premultiplicado, que en estos
        # tres modos se despeja sin despremultiplicar (la misma fórmula, menos pasadas):
        #   normal       fondo·(1 - αs) + factor·premult
        #   multiplicar  fondo·(1 - αs + factor·premult)
        #   pantalla     fondo + factor·premult·(1 - fondo)
        cs = color if factor is None else color * factor
        if capa.fusion == "normal":
            fondo *= _F(1.0) - a_ef
            fondo += cs
        elif capa.fusion == "multiplicar":
            fondo *= cs + (_F(1.0) - a_ef)
        else:
            resto = _F(1.0) - fondo
            resto *= cs
            fondo += resto
        return
    if alfa is not None and capa.fusion == "normal":
        # Sobre transparente (dentro de un grupo, o sin foto), en normal: "source-over" directo
        # (la fórmula de ``mezclar`` sin despremultiplicar la capa): co = cs + (1 - αs)·αb·Cb.
        cs = color if factor is None else color * factor
        resto = _F(1.0) - a_ef
        ab_resto = alfa * resto
        nuevo_alfa = a_ef + ab_resto
        co = fondo * ab_resto
        co += cs
        np.divide(co, nuevo_alfa, out=fondo, where=np.broadcast_to(nuevo_alfa > 0, co.shape))
        fondo[:, nuevo_alfa <= 0] = 0.0
        alfa[...] = nuevo_alfa
        return
    # Sin premultiplicar. Donde el alfa es 0 el color premultiplicado también: queda 0.
    puro = color * (_F(1.0) / np.maximum(a, _F(1e-12)))
    np.minimum(puro, _F(1.0), out=puro)
    if alfa is None:
        # Fondo opaco: fondo + αs·(B - fondo), en su lugar (``mezcla`` siempre da un arreglo nuevo
        # salvo en "normal", que no pasa por acá).
        dif = mezcla(capa.fusion, fondo, puro)
        dif -= fondo
        dif *= a_ef
        fondo += dif
        return
    nuevo, nuevo_alfa = mezclar(fondo, alfa, puro, a_ef, capa.fusion)
    fondo[...] = nuevo
    alfa[...] = nuevo_alfa


def _aplicar_filas(lienzo: np.ndarray, alfa: Optional[np.ndarray], planos: np.ndarray, desde: int, hasta: int,
                   c: Capa, m: Optional[np.ndarray], x0: int, y0: int, rx0: int, ly0: int,
                   tmp: np.ndarray) -> None:
    """Funde las filas ``desde``..``hasta`` de la capa transformada (``planos``, en su rectángulo
    que empieza en (x0, y0) de la salida) sobre ``lienzo`` y ``alfa``, cuya primera fila es la
    ``ly0`` de la salida y su primera columna la ``rx0``. ``m``: máscara uint8 de la salida, o None.

    ``tmp``: un búfer float32 de (4, al menos esas filas, al menos ese ancho), reservado una vez
    por llamada a ``componer``. Pedir un arreglo nuevo de ese tamaño en cada franja pasa del
    umbral (unos 512 KB) a partir del cual Windows le pide la memoria al sistema y la paga con
    fallos de página cada vez: medido, hacía todo 1,5 veces más lento."""
    w = planos.shape[2]
    p = tmp[:, :hasta - desde, :w]
    np.multiply(planos[:, desde:hasta], _R, out=p, dtype=_F)   # (4, filas, w)
    filas = slice(y0 + desde - ly0, y0 + hasta - ly0)
    columnas = slice(x0 - rx0, x0 - rx0 + w)
    mm = None if m is None else np.multiply(_trozo(m, y0 + desde, y0 + hasta, x0, x0 + w), _R, dtype=_F)
    _aplicar_capa(lienzo[:, filas, columnas], None if alfa is None else alfa[filas, columnas], p[:3], p[3], c, mm)


def _componer_lista(capas, ctx: _Contexto, lim: tuple) -> Optional[tuple]:
    """Esas capas (de abajo hacia arriba) compuestas sobre transparente, en el rectángulo que
    cubren (recortado a ``lim``): (planos, x0, y0), RGBA uint8 premultiplicado (4, h, w); None si
    no queda nada. Es lo que hace un grupo (y "combinar"). Van de a una: nunca hay más de una
    capa transformada a la vez (además del lienzo del grupo)."""
    rects = [(c, r) for c in capas for r in (_rect(c, ctx, lim),) if r is not None]
    if not rects:
        return None
    gx0, gy0 = min(r[0] for _c, r in rects), min(r[1] for _c, r in rects)
    gx1, gy1 = max(r[2] for _c, r in rects), max(r[3] for _c, r in rects)
    lienzo = np.zeros((3, gy1 - gy0, gx1 - gx0), _F)
    alfa = np.zeros((gy1 - gy0, gx1 - gx0), _F)
    for c, _r in rects:
        e = _elemento(c, ctx, lim)
        if e is None:
            continue
        planos, x0, y0 = e
        m = _mascara(c.mascara, ctx.almacen, ctx.ancho, ctx.alto, ctx.cache)
        paso = _filas_franja(planos.shape[2])
        tmp = np.empty((4, paso, planos.shape[2]), _F)
        for desde in range(0, planos.shape[1], paso):
            _aplicar_filas(lienzo, alfa, planos, desde, min(desde + paso, planos.shape[1]), c, m, x0, y0,
                           gx0, gy0, tmp)
        del planos, m
    salida = np.empty((4, gy1 - gy0, gx1 - gx0), np.uint8)
    lienzo *= alfa   # premultiplicado
    for i in range(3):
        cv2.convertScaleAbs(lienzo[i], salida[i], alpha=255.0)
    cv2.convertScaleAbs(alfa, salida[3], alpha=255.0)
    del lienzo, alfa
    if not cv2.countNonZero(salida[3]):
        return None
    np.minimum(salida[:3], salida[3], out=salida[:3])
    salida.flags.writeable = False
    return salida, gx0, gy0


def _componer_abajo(doc: Documento, almacen: AlmacenImagenes, foto: Optional[np.ndarray], alto: int, ancho: int,
                    cache: Optional[CacheComposicion]) -> np.ndarray:
    """Todo lo de abajo del ajuste, aplanado sobre blanco: RGB uint8 (puede ser ``foto`` misma).

    Con la base opaca (la foto, o un relleno opaco), la cuenta en float se hace solo en el
    rectángulo que cubren las capas: afuera queda la base tal cual (8 bits → float → 8 bits vuelve
    exacto, así que es lo mismo que daría la cuenta). Adentro, a cada píxel se le hacen las mismas
    operaciones en el mismo orden (base, capa 1, capa 2…, aplanar sobre blanco, cuantizar),
    recorriendo de una de dos maneras que dan el mismo resultado, bit a bit:

    * **Por franjas** (si los elementos ocupan hasta ``_MEMORIA_CAPAS``: la vista previa y las
      fotos chicas): se preparan todos (transformados, con estilos; un grupo, ya compuesto) y se
      recorre la salida en franjas de unos ``_PIXELES_FRANJA`` píxeles (20 filas a 1920 de ancho),
      cada una con todas las capas. La franja entra en la caché del procesador: unas 3 veces más
      rápido que de corrido.
    * **Capa por capa** (si no): un lienzo float del rectángulo entero y las capas de a una (cada
      una se prepara, se funde por franjas y se suelta). Más lento, pero sin caché nunca hay más
      de un elemento en memoria (más el lienzo de un grupo): es para exportar fotos grandes con
      muchas capas.
    """
    ctx = _Contexto(doc, almacen, ancho, alto, cache)
    lim = (0, 0, ancho, alto)
    base = doc.capas[0]
    unidades = list(ctx.hijos.get(None, ()))
    fondo = None   # RGB de la base opaca, o None (base transparente)
    mascara_base = None
    if base.visible and base.opacidad > 0:
        mascara_base = _mascara(base.mascara, almacen, ancho, alto, cache)
        if base.tipo == "foto":
            fondo = foto
        else:
            fondo = _relleno_opaco(base.params, ancho, alto, cache)
            if fondo is None:   # un relleno con transparencia: va como una capa más, sobre transparente
                unidades.insert(0, base)
                mascara_base = None
    foto_visible = fondo is not None
    foto_plena = foto_visible and base.opacidad >= 1 and mascara_base is None
    rects = [(u, r) for u in unidades for r in (_rect(u, ctx, lim),) if r is not None]
    if foto_plena and not rects:
        return fondo if fondo is foto else fondo.copy()
    if foto_plena:
        rx0, ry0 = min(r[0] for _u, r in rects), min(r[1] for _u, r in rects)
        rx1, ry1 = max(r[2] for _u, r in rects), max(r[3] for _u, r in rects)
    else:
        rx0, ry0, rx1, ry1 = 0, 0, ancho, alto
    rw = rx1 - rx0
    franja = _filas_franja(rw)
    salida = fondo.copy() if foto_plena else np.empty((alto, ancho, 3), np.uint8)

    def iniciar(lienzo, alfa, y, y2):
        """La base (o nada) en las filas y..y2 de la salida, sobre ``lienzo`` y ``alfa`` (esas filas)."""
        if foto_visible:
            np.multiply(np.moveaxis(fondo[y:y2, rx0:rx1], -1, 0), _R, out=lienzo, dtype=_F)
            if alfa is not None:
                alfa[...] = base.opacidad
                if mascara_base is not None:
                    alfa *= np.multiply(mascara_base[y:y2, rx0:rx1], _R, dtype=_F)
        else:
            lienzo[...] = 0.0
            alfa[...] = 0.0

    def terminar(lienzo, alfa, y, y2):
        """Aplana sobre blanco y cuantiza las filas y..y2 a ``salida``."""
        if alfa is not None:
            lienzo *= alfa
            lienzo += _F(1.0) - alfa
        salida[y:y2, rx0:rx1] = _de_planos(lienzo)

    estimado = sum(4 * (r[2] - r[0]) * (r[3] - r[1]) for _u, r in rects)
    if estimado <= _MEMORIA_CAPAS:
        hechas = []
        for u, _r in rects:
            e = _elemento(u, ctx, lim)
            if e is not None:
                planos, x0, y0 = e
                hechas.append((u, planos, x0, y0, _mascara(u.mascara, almacen, ancho, alto, cache)))
        lienzo_franja = np.empty((3, franja, rw), _F)
        tmp = np.empty((4, franja, max([p.shape[2] for _c, p, _x, _y, _m in hechas], default=1)), _F)
        for y in range(ry0, ry1, franja):
            y2 = min(y + franja, ry1)
            lienzo = lienzo_franja[:, :y2 - y]
            alfa = None if foto_plena else np.empty((y2 - y, rw), _F)
            iniciar(lienzo, alfa, y, y2)
            for c, planos, x0, y0, m in hechas:
                desde, hasta = max(y, y0) - y0, min(y2, y0 + planos.shape[1]) - y0
                if hasta > desde:
                    _aplicar_filas(lienzo, alfa, planos, desde, hasta, c, m, x0, y0, rx0, y, tmp)
            terminar(lienzo, alfa, y, y2)
        return salida

    lienzo = np.empty((3, ry1 - ry0, rw), _F)
    alfa = None if foto_plena else np.empty((ry1 - ry0, rw), _F)
    for y in range(ry0, ry1, franja):
        y2 = min(y + franja, ry1)
        iniciar(lienzo[:, y - ry0:y2 - ry0], None if alfa is None else alfa[y - ry0:y2 - ry0], y, y2)
    for c, _r in rects:
        e = _elemento(c, ctx, lim)
        if e is None:
            continue
        planos, x0, y0 = e
        m = _mascara(c.mascara, almacen, ancho, alto, cache)
        paso = _filas_franja(planos.shape[2])
        tmp = np.empty((4, paso, planos.shape[2]), _F)
        for desde in range(0, planos.shape[1], paso):
            _aplicar_filas(lienzo, alfa, planos, desde, min(desde + paso, planos.shape[1]), c, m, x0, y0,
                           rx0, ry0, tmp)
        del planos, m, e
    for y in range(ry0, ry1, franja):
        y2 = min(y + franja, ry1)
        terminar(lienzo[:, y - ry0:y2 - ry0], None if alfa is None else alfa[y - ry0:y2 - ry0], y, y2)
    return salida


def _estado_abajo(doc: Documento, almacen: AlmacenImagenes, ancho: int, alto: int) -> tuple:
    """Lo que define los píxeles de las capas de abajo del ajuste (sin nombres, ids ni candados)."""
    ctx = _Contexto(doc, almacen, ancho, alto, None)
    base = doc.capas[0]
    return ((base.visible and base.opacidad > 0,) + _firma(base, ctx),
            tuple(_firma(u, ctx) for u in ctx.hijos.get(None, ())))


def _filtrar(filtro: Callable[[np.ndarray], np.ndarray], base: np.ndarray) -> np.ndarray:
    salida = np.asarray(filtro(base))
    if salida.shape != base.shape:
        raise ValueError(f"El filtro tiene que devolver una imagen de {base.shape} (devolvió {salida.shape}).")
    if salida.dtype != np.uint8:
        f = np.clip(salida.astype(_F), 0.0, 1.0)
        salida = _de_planos(np.ascontiguousarray(np.moveaxis(f, -1, 0)))
    return salida


def componer(doc: Documento, almacen: AlmacenImagenes, foto_rgb: Optional[np.ndarray], escala: float = 1.0,
             filtro: Optional[Callable[[np.ndarray], np.ndarray]] = None,
             cache: Optional[CacheComposicion] = None, *, clave_foto: Optional[Hashable] = None,
             clave_filtro: Optional[Hashable] = None) -> np.ndarray:
    """Devuelve RGB uint8 de (round(alto·escala), round(ancho·escala)) (``tamano_salida``).

    ``foto_rgb`` es la foto base ya procesada (geometría, montaje, borrado, recorte, fondo) y
    ya escalada al tamaño de salida. En un documento sin foto (la base es un relleno:
    ``Documento.nuevo_lienzo``) no hace falta: se ignora (puede ser None). Se compone de abajo
    hacia arriba; ``filtro`` (el procesado celular natural de hoy: RGB uint8 → RGB uint8 del mismo
    tamaño) se aplica sobre la composición de todo lo de abajo y se mezcla según la opacidad,
    visibilidad, fusión y máscara de la capa ajuste_natural. Sin capas extra, con la foto visible
    al 100 % normal y el ajuste visible al 100 % normal: resultado == filtro(foto_rgb) exacto
    (regresión).

    ``cache``: ver ``CacheComposicion`` (para la vista previa; al exportar, ``None`` o una aparte).
    ``clave_foto`` y ``clave_filtro``: identifican la foto y el filtro en la caché. **La interfaz
    tiene que pasarlas** (cambiándolas cuando cambian la foto o los ajustes del filtro). Sin ellas,
    la foto se reconoce por un sello (``_sello``: su id, su forma y un CRC de algunas filas) y el
    filtro por identidad: funciona, pero un cambio de la foto en su lugar fuera de las filas del
    sello no se notaría, y un filtro nuevo en cada llamada nunca acierta.
    Siempre devuelve un arreglo nuevo. ``ValueError`` si (con foto) la foto no es RGB uint8 del
    tamaño de salida.
    """
    alto, ancho = tamano_salida(doc, escala)
    if doc.tiene_foto:
        foto = np.asarray(foto_rgb) if foto_rgb is not None else None
        if foto is None or foto.dtype != np.uint8 or foto.shape != (alto, ancho, 3):
            raise ValueError(f"foto_rgb tiene que ser RGB uint8 de {(alto, ancho, 3)} "
                             f"(llegó {None if foto is None else (foto.dtype, foto.shape)}).")
    else:
        foto = None
    ajuste = doc.ajuste
    if filtro is None or ajuste is None or not ajuste.visible or ajuste.opacidad <= 0:
        base = _componer_abajo(doc, almacen, foto, alto, ancho, cache)
        return base.copy() if base is foto else base

    hecho = None
    if cache is not None:
        if foto is None:
            k_foto = ("lienzo",)
        else:
            k_foto = ("clave", clave_foto) if clave_foto is not None else ("sello", _sello(foto))
        k_filtro = ("clave", clave_filtro) if clave_filtro is not None else ("id", id(filtro))
        clave = ("ajuste", _estado_abajo(doc, almacen, ancho, alto), k_foto, k_filtro, doc.ancho, doc.alto,
                 alto, ancho)
        previo = cache._obtener(clave)
        # El filtro (sin clave) se guarda para compararlo por identidad: su id no se reusa mientras esté acá.
        if previo is not None and (clave_filtro is not None or previo[2] is filtro):
            hecho = (foto if previo[0] is None else previo[0], previo[1])
    if hecho is None:
        base = _componer_abajo(doc, almacen, foto, alto, ancho, cache)
        if base is not foto:
            base.flags.writeable = False   # queda en la caché: el filtro no lo puede cambiar
        filtrada = _filtrar(filtro, base)
        if (foto is not None and np.may_share_memory(filtrada, foto)) or np.may_share_memory(filtrada, base):
            filtrada = filtrada.copy()   # un filtro que devuelve lo mismo: no se toca la foto de nadie
        filtrada.flags.writeable = False
        hecho = (base, filtrada)
        if cache is not None:
            # La foto no se retiene: si "lo de abajo" es la foto misma, se guarda None.
            guardada = None if base is foto else base
            nbytes = filtrada.nbytes + (0 if guardada is None else guardada.nbytes)
            cache._guardar(clave, (guardada, filtrada, filtro), nbytes)
    base, filtrada = hecho

    mascara = _mascara(ajuste.mascara, almacen, ancho, alto, cache)
    if ajuste.opacidad >= 1 and ajuste.fusion == "normal" and mascara is None:
        return filtrada.copy()
    salida = np.empty_like(filtrada)
    franja = _filas_franja(ancho)
    for y in range(0, alto, franja):   # por franjas, como _componer_abajo
        y2 = min(y + franja, alto)
        alfa = np.full((y2 - y, ancho), ajuste.opacidad, _F)
        if mascara is not None:
            alfa *= np.multiply(mascara[y:y2], _R, dtype=_F)
        rgb, _ = mezclar(_a_planos(base[y:y2]), None, _a_planos(filtrada[y:y2]), alfa, ajuste.fusion)
        salida[y:y2] = _de_planos(rgb)
    return salida


# ---------------------------------------------------------------------------
# Operaciones con píxeles: rasterizar, combinar, acoplar
# ---------------------------------------------------------------------------

def _rgba_de_planos(planos: np.ndarray) -> np.ndarray:
    """Planos premultiplicados (4, h, w) → RGBA uint8 (h, w, 4) sin premultiplicar."""
    junto = np.ascontiguousarray(np.moveaxis(planos, 0, -1))
    return cv2.cvtColor(junto, cv2.COLOR_mRGBA2RGBA)


def _capa_de_pixeles(base: Capa, almacen: AlmacenImagenes, hecho: Optional[tuple], doc: Documento,
                     **cambios) -> Capa:
    """Una capa pixeles (con el id, el nombre y el resto de ``base``) con lo compuesto en ``hecho``
    ((planos, x0, y0) en píxeles del documento), centrada donde estaba."""
    if hecho is None:   # no quedó nada: un píxel transparente en el centro
        img, cx, cy = np.zeros((1, 1, 4), np.uint8), doc.ancho / 2.0, doc.alto / 2.0
    else:
        planos, x0, y0 = hecho
        img = _rgba_de_planos(planos)
        cx, cy = x0 + planos.shape[2] / 2.0, y0 + planos.shape[1] / 2.0
    campos = dict(tipo="pixeles", imagen=almacen.guardar(img), params=None, transform=Transformacion(cx, cy))
    campos.update(cambios)
    return replace(base, **campos)


def _contexto_documento(doc: Documento, almacen: AlmacenImagenes) -> _Contexto:
    return _Contexto(doc, almacen, doc.ancho, doc.alto, None)


def rasterizar(doc: Documento, almacen: AlmacenImagenes, id_capa: str) -> Documento:
    """La capa pasada a ``pixeles`` (para pintarla): un texto o una forma, con su dibujo a escala 1
    (misma transformación: se ve igual); un relleno, del tamaño del lienzo; una imagen, tal cual; un
    grupo, combinado en una sola capa (``combinar_abajo``). Los estilos quedan como estilos. Guarda
    en ``almacen`` lo que haga falta. La base y el ajuste: ``ValueError``."""
    i = doc.indice(id_capa)
    c = doc.capas[i]
    if i == 0 or c.tipo == "ajuste_natural":
        raise ValueError("La base y el ajuste no se rasterizan.")
    if c.tipo == "pixeles":
        return doc
    if c.tipo == "imagen":
        return doc._reemplazar(id_capa, replace(c, tipo="pixeles"))
    if c.tipo == "grupo":
        return combinar_abajo(doc, almacen, id_capa)
    if c.tipo in TIPOS_GENERADOS:
        img = _dibujo_natural(c.tipo, c.params)
        return doc._reemplazar(id_capa, replace(c, tipo="pixeles", params=None, imagen=almacen.guardar(img)))
    if c.tipo == "relleno":
        img = np.ascontiguousarray(_relleno_rgba(c.params, doc.ancho, doc.alto))
        return doc._reemplazar(id_capa, replace(c, tipo="pixeles", params=None, imagen=almacen.guardar(img),
                                                transform=Transformacion(doc.ancho / 2.0, doc.alto / 2.0)))
    raise ValueError(f"Las capas {c.tipo} no se rasterizan.")


def combinar_abajo(doc: Documento, almacen: AlmacenImagenes, id_capa: str) -> Documento:
    """"Combinar hacia abajo": la capa y la de abajo (su hermana; ni la base ni un grupo) pasan a
    ser una sola capa pixeles, con el id, el nombre y el lugar de la de abajo, visible al 100 %,
    normal, sin máscara ni estilos (ya aplicados). Si la capa es un grupo, "combinar grupo": todo
    lo de adentro (con los estilos del grupo) pasa a una capa pixeles con la opacidad, la fusión
    y la máscara del grupo. Lo oculto se pierde (como en Photoshop). ``ValueError`` si no se puede.

    Se compone a escala 1, sobre transparente: si la de abajo tenía un modo de fusión que no es
    normal, su modo deja de notarse (se funde contra transparente)."""
    i = doc._movible(id_capa)
    c = doc.capas[i]
    ctx = _contexto_documento(doc, almacen)
    lim = (0, 0, doc.ancho, doc.alto)
    if c.tipo == "grupo":
        hecho = _elemento(replace(c, opacidad=1.0), ctx, lim) if c.visible else None
        inicio = _bloque(doc.capas, i)
        nueva = _capa_de_pixeles(c, almacen, hecho, doc, estilos=_SIN_ESTILOS)
        return doc._con(doc.capas[:inicio] + (nueva,) + doc.capas[i + 1:])
    inicio = _bloque(doc.capas, i)
    j = inicio - 1
    abajo = doc.capas[j]
    if j == 0 or abajo.padre != c.padre:
        raise ValueError("No hay una capa abajo con la cual combinar (abajo está la base o el borde del grupo).")
    if abajo.tipo == "grupo":
        raise ValueError("No se puede combinar con un grupo (combiná el grupo primero).")
    visibles = [x for x in (abajo, c) if x.visible and x.opacidad > 0]
    hecho = _componer_lista(visibles, ctx, lim)
    nueva = _capa_de_pixeles(abajo, almacen, hecho, doc, visible=True, opacidad=1.0, fusion="normal",
                             mascara=None, estilos=_SIN_ESTILOS)
    return doc._con(doc.capas[:j] + (nueva,) + doc.capas[i + 1:])


def acoplar(doc: Documento, almacen: AlmacenImagenes, foto_rgb: Optional[np.ndarray] = None) -> Documento:
    """"Acoplar imagen": todo lo de abajo del ajuste en una sola capa pixeles (aplanada sobre blanco,
    como ``componer`` sin filtro), sobre un fondo blanco; el ajuste queda como estaba. Con foto,
    hace falta ``foto_rgb`` (a tamaño completo)."""
    rgb = componer(doc, almacen, foto_rgb)
    formas = _modulo("formas")
    fondo = Capa(ID_FONDO, "relleno", NOMBRE_FONDO, params=formas.Relleno("color", ((255, 255, 255, 255),)))
    usados = {ID_FONDO} | ({doc.ajuste.id} if doc.ajuste is not None else set())
    id_img = next(n for n in ("imagen", *(uuid.uuid4().hex[:12] for _ in range(100))) if n not in usados)
    capa = Capa(id_img, "pixeles", "Imagen", imagen=almacen.guardar(rgb),
                transform=Transformacion(doc.ancho / 2.0, doc.alto / 2.0))
    return Documento(doc.ancho, doc.alto, (fondo, capa) + ((doc.ajuste,) if doc.ajuste is not None else ()))


def convertir_foto_en_capa(doc: Documento, almacen: AlmacenImagenes, foto_rgb: np.ndarray,
                           fondo=None) -> Documento:
    """Un documento de foto pasado a uno de lienzo: la foto (``foto_rgb``, RGB uint8 del tamaño del
    documento) pasa a ser una capa pixeles (con la visibilidad, opacidad, fusión y máscara que
    tenía) y abajo queda un fondo de relleno (``fondo``; None = transparente). Se ve igual. Las
    operaciones de lienzo lo hacen solas si les pasan ``foto_rgb``. Sin foto, lo devuelve igual."""
    if not doc.tiene_foto:
        return doc
    foto = np.asarray(foto_rgb) if foto_rgb is not None else None
    if foto is None or foto.dtype != np.uint8 or foto.shape != (doc.alto, doc.ancho, 3):
        raise ValueError(f"Este documento tiene la foto de base: hace falta foto_rgb, RGB uint8 de "
                         f"{(doc.alto, doc.ancho, 3)}.")
    f = doc.base
    id_fondo = ID_FONDO if all(c.id != ID_FONDO for c in doc.capas) else doc.id_libre()
    if fondo is None:
        fondo = _modulo("formas").Relleno("ninguno")
    base = Capa(id_fondo, "relleno", NOMBRE_FONDO, params=fondo)
    capa = Capa(doc.id_libre(), "pixeles", f.nombre, visible=f.visible, bloqueada=f.bloqueada, opacidad=f.opacidad,
                fusion=f.fusion, imagen=almacen.guardar(foto), mascara=f.mascara,
                transform=Transformacion(doc.ancho / 2.0, doc.alto / 2.0))
    return Documento(doc.ancho, doc.alto, (base, capa) + doc.capas[1:])


# ---------------------------------------------------------------------------
# Operaciones de lienzo
# ---------------------------------------------------------------------------

def _preparar_lienzo(doc: Documento, almacen: AlmacenImagenes, foto_rgb) -> Documento:
    if doc.tiene_foto:
        if foto_rgb is None:
            raise ValueError("Este documento tiene la foto de base: para cambiar el lienzo, pasá foto_rgb "
                             "(la foto pasa a ser una capa).")
        return convertir_foto_en_capa(doc, almacen, foto_rgb)
    return doc


def _cada_capa(doc: Documento, ancho: int, alto: int, transform=None, mascara=None, relleno=None,
               estilos=None) -> Documento:
    """Un documento de ``ancho`` × ``alto`` con cada capa cambiada por esas funciones (de la
    transformación, del arreglo de la máscara ya guardado como id, del relleno, de los estilos)."""
    capas = []
    for c in doc.capas:
        cambios = {}
        if transform is not None and c.tipo in TIPOS_CON_TRANSFORMACION:
            cambios["transform"] = transform(c.transform)
        if mascara is not None and c.mascara is not None:
            cambios["mascara"] = mascara(c.mascara)
        if relleno is not None and c.tipo == "relleno":
            cambios["params"] = relleno(c.params)
        if estilos is not None and c.estilos != _SIN_ESTILOS:
            cambios["estilos"] = estilos(c.estilos)
        capas.append(replace(c, **cambios) if cambios else c)
    return Documento(ancho, alto, tuple(capas))


def _mascara_nueva(almacen: AlmacenImagenes, funcion):
    """Para ``_cada_capa``: la máscara (id) → la de ``funcion(arreglo)`` (id); si falta, queda el id."""
    def cambiar(id_m):
        if id_m not in almacen:
            return id_m
        m = almacen.obtener(id_m)
        if m.ndim == 3:
            m = m[..., 0]
        return almacen.guardar(np.ascontiguousarray(funcion(m)))
    return cambiar


def _dimensiones(ancho, alto) -> tuple[int, int]:
    ancho, alto = _entero_positivo(ancho, "ancho"), _entero_positivo(alto, "alto")
    if ancho > LADO_MAX or alto > LADO_MAX or ancho * alto > AREA_MAX:
        raise ValueError(f"El documento es demasiado grande ({ancho}×{alto}).")
    return ancho, alto


def _reencuadrar(doc: Documento, almacen: AlmacenImagenes, ancho: int, alto: int, dx: int, dy: int) -> Documento:
    """Lienzo de ancho × alto con lo de antes corrido (dx, dy) píxeles (enteros)."""
    def mover_mascara(m):
        if m.shape != (doc.alto, doc.ancho):
            m = cv2.resize(m, (doc.ancho, doc.alto), interpolation=cv2.INTER_LINEAR)
        return cv2.warpAffine(m, np.float64([[1, 0, dx], [0, 1, dy]]), (ancho, alto), flags=cv2.INTER_NEAREST,
                              borderMode=cv2.BORDER_REPLICATE)
    return _cada_capa(doc, ancho, alto, transform=lambda t: replace(t, x=t.x + dx, y=t.y + dy),
                      mascara=_mascara_nueva(almacen, mover_mascara))


def tamano_lienzo(doc: Documento, almacen: AlmacenImagenes, ancho: int, alto: int, ancla="centro",
                  foto_rgb: Optional[np.ndarray] = None) -> Documento:
    """"Tamaño del lienzo": agrega o recorta bordes. ``ancla`` es una clave de ``ANCLAS`` (o
    (fx, fy) de 0 a 1): dónde queda lo que había. Las capas no cambian de tamaño; las máscaras
    se agrandan repitiendo su borde. Con foto, hace falta ``foto_rgb`` (pasa a ser una capa)."""
    ancho, alto = _dimensiones(ancho, alto)
    if isinstance(ancla, str):
        if ancla not in ANCLAS:
            raise ValueError(f"Ancla desconocida: {ancla!r} (son {', '.join(ANCLAS)}).")
        fx, fy = ANCLAS[ancla]
    else:
        try:
            fx, fy = (min(1.0, max(0.0, _real(v, "ancla"))) for v in ancla)
        except TypeError as error:
            raise ValueError(f"Ancla inválida: {ancla!r}.") from error
    doc = _preparar_lienzo(doc, almacen, foto_rgb)
    return _reencuadrar(doc, almacen, ancho, alto, int(round((ancho - doc.ancho) * fx)),
                        int(round((alto - doc.alto) * fy)))


def recortar(doc: Documento, almacen: AlmacenImagenes, x: int, y: int, ancho: int, alto: int,
             foto_rgb: Optional[np.ndarray] = None) -> Documento:
    """Recorta el lienzo al rectángulo (x, y, ancho, alto) en píxeles del documento (puede salirse:
    eso agrega borde). Con foto, hace falta ``foto_rgb``."""
    ancho, alto = _dimensiones(ancho, alto)
    for v, n in ((x, "x"), (y, "y")):
        if isinstance(v, bool) or not isinstance(v, (numbers.Integral, np.integer)):
            raise ValueError(f"{n} tiene que ser un entero (llegó {v!r}).")
    doc = _preparar_lienzo(doc, almacen, foto_rgb)
    return _reencuadrar(doc, almacen, ancho, alto, -int(x), -int(y))


def escalar_imagen(doc: Documento, almacen: AlmacenImagenes, ancho: int, alto: int,
                   foto_rgb: Optional[np.ndarray] = None) -> Documento:
    """"Tamaño de imagen": escala todo (posiciones, escalas, máscaras y medidas de los estilos).
    Las imágenes no se remuestrean: cambia su escala. Con proporción distinta y capas giradas, la
    deformación se aproxima (se escala cada capa en sus propios ejes). Con foto, hace falta ``foto_rgb``."""
    ancho, alto = _dimensiones(ancho, alto)
    doc = _preparar_lienzo(doc, almacen, foto_rgb)
    fx, fy = ancho / doc.ancho, alto / doc.alto

    def transformar(t):
        if t.escala_y is None and fx == fy:
            return replace(t, x=t.x * fx, y=t.y * fy, escala=t.escala * fx)
        # En los ejes de la capa: el de x de la imagen, girado, se estira según cuánto mira a x o a y.
        c, s = _rotacion(t.rotacion)
        ex = t.escala * math.hypot(fx * c, fy * s)
        ey = t.escala_vertical * math.hypot(fx * s, fy * c)
        return replace(t, x=t.x * fx, y=t.y * fy, escala=ex, escala_y=ey)

    def mascara(m):
        achica = ancho <= m.shape[1] and alto <= m.shape[0]
        return cv2.resize(m, (ancho, alto), interpolation=cv2.INTER_AREA if achica else cv2.INTER_LINEAR)

    f = math.sqrt(fx * fy)
    return _cada_capa(doc, ancho, alto, transform=transformar, mascara=_mascara_nueva(almacen, mascara),
                      estilos=lambda e: e.escalados(f))


def rotar_lienzo(doc: Documento, almacen: AlmacenImagenes, grados: int,
                 foto_rgb: Optional[np.ndarray] = None) -> Documento:
    """Gira el lienzo 90, 180 o 270 grados en sentido horario (todo gira con él). Con foto, hace
    falta ``foto_rgb``."""
    if isinstance(grados, bool) or grados not in (90, 180, 270):
        raise ValueError(f"El lienzo gira 90, 180 o 270 grados (llegó {grados!r}).")
    doc = _preparar_lienzo(doc, almacen, foto_rgb)
    W, H = doc.ancho, doc.alto
    punto = {90: lambda x, y: (H - y, x), 180: lambda x, y: (W - x, H - y), 270: lambda x, y: (y, W - x)}[grados]
    nuevo = (H, W) if grados != 180 else (W, H)

    def transformar(t):
        x, y = punto(t.x, t.y)
        return replace(t, x=x, y=y, rotacion=(t.rotacion + grados) % 360.0)

    k = -grados // 90
    return _cada_capa(doc, nuevo[0], nuevo[1], transform=transformar,
                      mascara=_mascara_nueva(almacen, lambda m: np.rot90(m, k)),
                      relleno=lambda r: replace(r, angulo=(r.angulo + grados) % 360.0),
                      estilos=lambda e: e.girados(grados))


def voltear_lienzo(doc: Documento, almacen: AlmacenImagenes, eje: str,
                   foto_rgb: Optional[np.ndarray] = None) -> Documento:
    """Voltea el lienzo: ``eje`` "h" (izquierda ↔ derecha) o "v" (arriba ↔ abajo). Con foto, hace
    falta ``foto_rgb``."""
    if eje not in ("h", "v"):
        raise ValueError(f"El eje es 'h' o 'v' (llegó {eje!r}).")
    doc = _preparar_lienzo(doc, almacen, foto_rgb)
    W, H = doc.ancho, doc.alto

    def transformar(t):
        rot = (-t.rotacion) % 360.0
        if eje == "h":
            return replace(t, x=W - t.x, rotacion=rot, voltear_h=not t.voltear_h)
        return replace(t, y=H - t.y, rotacion=rot, voltear_v=not t.voltear_v)

    return _cada_capa(doc, W, H, transform=transformar,
                      mascara=_mascara_nueva(almacen, np.fliplr if eje == "h" else np.flipud),
                      relleno=lambda r: replace(r, angulo=((180.0 - r.angulo) if eje == "h" else -r.angulo) % 360.0),
                      estilos=lambda e: e.espejados(eje))


# ---------------------------------------------------------------------------
# Cajas, mover, alinear y distribuir
# ---------------------------------------------------------------------------

def caja_capa(doc: Documento, id_capa: str, almacen: AlmacenImagenes) -> Optional[tuple[float, float, float, float]]:
    """(x0, y0, x1, y1): la caja alineada al documento de lo que se ve de la capa (sin los estilos),
    con su transformación, en píxeles del documento. La base, un relleno y el ajuste: el lienzo. Un
    grupo: la de todo lo de adentro. None si no hay nada que se vea (vacía, o la imagen falta)."""
    c = doc.capa(id_capa)
    if c.tipo in ("foto", "relleno", "ajuste_natural"):
        return 0.0, 0.0, float(doc.ancho), float(doc.alto)
    if c.tipo == "grupo":
        cajas = [k for h in doc.hijos(c.id) for k in (caja_capa(doc, h.id, almacen),) if k is not None]
        if not cajas:
            return None
        return (min(k[0] for k in cajas), min(k[1] for k in cajas), max(k[2] for k in cajas), max(k[3] for k in cajas))
    if c.tipo in ("imagen", "pixeles"):
        if c.imagen not in almacen:
            return None
        img = almacen.obtener(c.imagen)
        ih, iw = img.shape[:2]
        caja = _caja_imagen(c.imagen, img)
    else:
        nat = _natural(c.tipo, c.params)
        if nat is None:
            return None
        iw, ih, caja = nat
    if caja is None:
        return None
    m = matriz_transformacion(c.transform, iw, ih)
    x0, y0, x1, y1 = caja
    p = np.array([[x0, y0, 1], [x1, y0, 1], [x1, y1, 1], [x0, y1, 1]], float) @ m.T
    return (float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()), float(p[:, 1].max()))


def _sin_repetir(doc: Documento, ids) -> list[str]:
    """Los ids sin los que ya están dentro de un grupo elegido (se mueven con él)."""
    elegidos = set(ids)
    return [i for i in dict.fromkeys(ids) if not any(a in elegidos for a in doc.ancestros(i))]


def trasladar(doc: Documento, ids: Iterable[str], dx: float, dy: float) -> Documento:
    """Mueve esas capas (dx, dy) píxeles del documento; un grupo, con todo lo de adentro. Las que no
    tienen transformación (la base, rellenos, el ajuste) no se mueven."""
    dx, dy = _real(dx, "dx"), _real(dy, "dy")
    mover = set()
    for i in _sin_repetir(doc, ids):
        k = doc.indice(i)
        mover.update(c.id for c in doc.capas[_bloque(doc.capas, k):k + 1])
    return doc._con(replace(c, transform=replace(c.transform, x=c.transform.x + dx, y=c.transform.y + dy))
                    if c.id in mover and c.tipo in TIPOS_CON_TRANSFORMACION else c for c in doc.capas)


def _movibles(doc: Documento, ids) -> list[str]:
    return [i for i in _sin_repetir(doc, ids) if doc.indice(i) != 0
            and doc.capa(i).tipo not in ("relleno", "ajuste_natural")]


def alinear(doc: Documento, ids: Iterable[str], modo: str, respecto: str = "lienzo", *,
            almacen: AlmacenImagenes) -> Documento:
    """Alinea las capas (por su ``caja_capa``): ``modo`` en ``MODOS_ALINEAR`` ("izquierda",
    "centro_h", "derecha", "arriba", "centro_v", "abajo"), ``respecto`` del "lienzo" o de la
    "seleccion" (la caja de todas juntas; con una sola capa, del lienzo, como Photoshop)."""
    if modo not in MODOS_ALINEAR:
        raise ValueError(f"Modo de alinear desconocido: {modo!r}.")
    if respecto not in ("lienzo", "seleccion"):
        raise ValueError(f"respecto es 'lienzo' o 'seleccion' (llegó {respecto!r}).")
    cajas = {i: k for i in _movibles(doc, ids) for k in (caja_capa(doc, i, almacen),) if k is not None}
    if not cajas:
        return doc
    if respecto == "seleccion" and len(cajas) > 1:
        ref = (min(k[0] for k in cajas.values()), min(k[1] for k in cajas.values()),
               max(k[2] for k in cajas.values()), max(k[3] for k in cajas.values()))
    else:
        ref = (0.0, 0.0, float(doc.ancho), float(doc.alto))
    for i, (x0, y0, x1, y1) in cajas.items():
        dx = dy = 0.0
        if modo == "izquierda":
            dx = ref[0] - x0
        elif modo == "derecha":
            dx = ref[2] - x1
        elif modo == "centro_h":
            dx = (ref[0] + ref[2]) / 2 - (x0 + x1) / 2
        elif modo == "arriba":
            dy = ref[1] - y0
        elif modo == "abajo":
            dy = ref[3] - y1
        else:
            dy = (ref[1] + ref[3]) / 2 - (y0 + y1) / 2
        if dx or dy:
            doc = trasladar(doc, [i], dx, dy)
    return doc


def distribuir(doc: Documento, ids: Iterable[str], eje: str, *, almacen: AlmacenImagenes) -> Documento:
    """Reparte los centros de las capas parejo entre el primero y el último (por su ``caja_capa``),
    en horizontal (``eje`` "h") o en vertical ("v"). Con menos de 3 capas, no cambia nada."""
    if eje not in ("h", "v"):
        raise ValueError(f"El eje es 'h' o 'v' (llegó {eje!r}).")
    a, b = (0, 2) if eje == "h" else (1, 3)
    centros = sorted(((k[a] + k[b]) / 2, i) for i in _movibles(doc, ids)
                     for k in (caja_capa(doc, i, almacen),) if k is not None)
    if len(centros) < 3:
        return doc
    primero, ultimo = centros[0][0], centros[-1][0]
    paso = (ultimo - primero) / (len(centros) - 1)
    for n, (centro, i) in enumerate(centros[1:-1], start=1):
        d = primero + paso * n - centro
        if d:
            doc = trasladar(doc, [i], d if eje == "h" else 0.0, d if eje == "v" else 0.0)
    return doc


__all__ = [
    "ACHICAR_CON_AREA", "ANCLAS", "AREA_MAX", "AlmacenImagenes", "CacheComposicion", "Capa", "Documento",
    "ID_AJUSTE", "ID_FONDO", "ID_FOTO", "LADO_MAX", "MODOS_ALINEAR", "MODOS_FUSION", "NOMBRE_AJUSTE",
    "NOMBRE_FONDO", "NOMBRE_FOTO", "PROFUNDIDAD_MAX", "TIPOS_BASE", "TIPOS_CAPA", "TIPOS_CON_ESTILOS",
    "TIPOS_CON_TRANSFORMACION", "TIPOS_GENERADOS", "Transformacion", "acoplar", "alinear", "caja_capa",
    "capas_faltantes", "combinar_abajo", "componer", "convertir_foto_en_capa", "distribuir", "escalar_imagen",
    "esquinas", "matriz_transformacion", "rasterizar", "recortar", "rotar_lienzo", "tamano_lienzo", "tamano_salida",
    "transformacion_ajustada", "trasladar", "voltear_lienzo",
]
