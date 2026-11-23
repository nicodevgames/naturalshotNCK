"""Estilos de capa de NaturalShot Lite (como los de Photoshop): sombra paralela, trazo,
resplandor exterior y superposiciones de color y de degradado. Sin Qt.

Los datos
---------
``EstilosCapa`` junta los cinco efectos; cada uno es ``None`` (no está) o una dataclass
congelada con sus parámetros y ``activo`` (prendido o apagado, sin perder los valores). Todo
se puede pasar a JSON (``como_dict`` y ``desde_dict``) y guardar con pickle.

Unidades: las distancias, los tamaños y los grosores están en **píxeles del documento**;
``aplicar_estilos`` recibe la ``escala`` (por ejemplo, la de la vista previa) y los multiplica.
El ángulo de la sombra es el de Photoshop: de dónde viene la luz, en grados antihorarios desde
la derecha (120 = de arriba a la izquierda, así que la sombra cae abajo a la derecha).

Cómo se aplican
---------------
``aplicar_estilos(rgba, estilos, escala) -> (rgba_resultado, (dx, dy))``: el resultado puede
crecer (la sombra, el resplandor y el trazo de afuera salen del contorno); ``(dx, dy)`` es dónde
cae su esquina de arriba a la izquierda en las coordenadas de la imagen original (0 o negativo).
De abajo hacia arriba, todo en RGBA premultiplicado (float32 de 0 a 1):

1. **sombra**: el alfa de la capa, desenfocado (``tamano``) y corrido (``distancia`` en la
   dirección contraria a la luz), con su color y opacidad;
2. **resplandor exterior**: el alfa desenfocado, sin correr;
3. **trazo** afuera (o la mitad de afuera, si es "centro"): el contorno agrandado ``grosor``
   píxeles con la distancia euclidiana (``cv2.distanceTransform``), con borde suave;
4. **el contenido**, con la superposición de degradado y después la de color encima (solo
   cambian el color: el alfa queda);
5. **trazo** adentro (o la mitad de adentro): una banda del borde hacia adentro, que tampoco
   cambia el alfa.

Simplificaciones (frente a Photoshop): todos los efectos se mezclan en modo normal (la sombra
de Photoshop va en "multiplicar"), y el desenfoque es ``cv2.stackBlur`` (parecido a un
gaussiano, con costo fijo por píxel aunque el tamaño sea grande). Todo vectorizado.
"""

from __future__ import annotations

import importlib
import math
import numbers
from dataclasses import dataclass, fields, replace
from typing import Optional

import cv2
import numpy as np

TOPE_PIXELES = 2000.0     # distancia, tamaño o grosor, como mucho (en píxeles del documento)
POSICIONES_TRAZO = ("afuera", "adentro", "centro")
EFECTOS = ("sombra", "trazo", "resplandor", "color", "degradado")

_F = np.float32


# ---------------------------------------------------------------------------
# Validaciones
# ---------------------------------------------------------------------------

def _real(valor, nombre: str) -> float:
    if (isinstance(valor, (str, bytes, bool, np.bool_)) or valor is None
            or not isinstance(valor, (numbers.Real, np.number))):
        raise ValueError(f"{nombre} tiene que ser un número (llegó {valor!r}).")
    v = float(valor)
    if not math.isfinite(v):
        raise ValueError(f"{nombre} tiene que ser un número finito (llegó {valor!r}).")
    return v


def _medida(valor, nombre: str) -> float:
    """Un largo en píxeles: de 0 a ``TOPE_PIXELES``."""
    v = _real(valor, nombre)
    if v < 0 or v > TOPE_PIXELES:
        raise ValueError(f"{nombre} tiene que estar entre 0 y {TOPE_PIXELES:g} (llegó {valor!r}).")
    return v


def _fraccion(valor, nombre: str) -> float:
    return min(1.0, max(0.0, _real(valor, nombre)))


def _booleano(valor, nombre: str) -> bool:
    if not isinstance(valor, (bool, np.bool_)):
        raise ValueError(f"{nombre} tiene que ser verdadero o falso (llegó {valor!r}).")
    return bool(valor)


def _color(valor, nombre: str = "color") -> tuple:
    """RGB o RGBA de enteros de 0 a 255 → tupla RGBA (sin alfa, 255)."""
    if isinstance(valor, (str, bytes)) or not isinstance(valor, (tuple, list)) or len(valor) not in (3, 4):
        raise ValueError(f"{nombre} tiene que ser (r, g, b) o (r, g, b, a) (llegó {valor!r}).")
    salida = []
    for v in valor:
        if isinstance(v, (bool, np.bool_)) or not isinstance(v, (numbers.Integral, np.integer)) or not 0 <= v <= 255:
            raise ValueError(f"{nombre}: cada canal es un entero de 0 a 255 (llegó {valor!r}).")
        salida.append(int(v))
    if len(salida) == 3:
        salida.append(255)
    return tuple(salida)


def _formas():
    return importlib.import_module(f"{__package__}.formas")


# ---------------------------------------------------------------------------
# Los efectos
# ---------------------------------------------------------------------------

class _Efecto:
    """Lo común: validar, pasar a dict y volver."""

    def como_dict(self) -> dict:
        return {f.name: (list(v) if isinstance(v, tuple) else v)
                for f in fields(self) for v in (getattr(self, f.name),)}

    @classmethod
    def desde_dict(cls, d) -> "_Efecto":
        if not isinstance(d, dict):
            raise ValueError(f"Datos inválidos para {cls.__name__} (llegó {d!r}).")
        nombres = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in nombres})

    def _escalado(self, f: float):
        return self

    def _girado(self, grados: float):
        return self

    def _espejado(self, eje: str):
        return self


@dataclass(frozen=True)
class Sombra(_Efecto):
    """Sombra paralela. ``angulo``: de dónde viene la luz (antihorario desde la derecha);
    ``distancia``: cuánto se corre; ``tamano``: cuánto se desenfoca (radio)."""

    color: tuple = (0, 0, 0, 255)
    opacidad: float = 0.75
    angulo: float = 120.0
    distancia: float = 10.0
    tamano: float = 10.0
    activo: bool = True

    def __post_init__(self):
        object.__setattr__(self, "color", _color(self.color))
        object.__setattr__(self, "opacidad", _fraccion(self.opacidad, "opacidad"))
        object.__setattr__(self, "angulo", _real(self.angulo, "angulo") % 360.0)
        object.__setattr__(self, "distancia", _medida(self.distancia, "distancia"))
        object.__setattr__(self, "tamano", _medida(self.tamano, "tamano"))
        object.__setattr__(self, "activo", _booleano(self.activo, "activo"))

    def desplazamiento(self, escala: float = 1.0) -> tuple[int, int]:
        """(dx, dy) de la sombra en píxeles (enteros, con la y hacia abajo)."""
        r = math.radians(self.angulo)
        d = self.distancia * escala
        return int(round(-math.cos(r) * d)), int(round(math.sin(r) * d))

    def _escalado(self, f):
        return replace(self, distancia=min(TOPE_PIXELES, self.distancia * f), tamano=min(TOPE_PIXELES, self.tamano * f))

    def _girado(self, grados):
        return replace(self, angulo=self.angulo - grados)

    def _espejado(self, eje):
        return replace(self, angulo=(180.0 - self.angulo) if eje == "h" else -self.angulo)


@dataclass(frozen=True)
class Trazo(_Efecto):
    """Trazo del contorno: ``posicion`` "afuera", "adentro" o "centro"."""

    color: tuple = (0, 0, 0, 255)
    grosor: float = 3.0
    posicion: str = "afuera"
    opacidad: float = 1.0
    activo: bool = True

    def __post_init__(self):
        object.__setattr__(self, "color", _color(self.color))
        object.__setattr__(self, "grosor", _medida(self.grosor, "grosor"))
        if self.posicion not in POSICIONES_TRAZO:
            raise ValueError(f"La posición del trazo es {', '.join(POSICIONES_TRAZO)} (llegó {self.posicion!r}).")
        object.__setattr__(self, "opacidad", _fraccion(self.opacidad, "opacidad"))
        object.__setattr__(self, "activo", _booleano(self.activo, "activo"))

    def _escalado(self, f):
        return replace(self, grosor=min(TOPE_PIXELES, self.grosor * f))


@dataclass(frozen=True)
class Resplandor(_Efecto):
    """Resplandor exterior: el contorno desenfocado (``tamano``), sin correr."""

    color: tuple = (255, 255, 190, 255)
    opacidad: float = 0.75
    tamano: float = 15.0
    activo: bool = True

    def __post_init__(self):
        object.__setattr__(self, "color", _color(self.color))
        object.__setattr__(self, "opacidad", _fraccion(self.opacidad, "opacidad"))
        object.__setattr__(self, "tamano", _medida(self.tamano, "tamano"))
        object.__setattr__(self, "activo", _booleano(self.activo, "activo"))

    def _escalado(self, f):
        return replace(self, tamano=min(TOPE_PIXELES, self.tamano * f))


@dataclass(frozen=True)
class SuperposicionColor(_Efecto):
    """Pinta la capa de un color (el alfa queda), con esa opacidad."""

    color: tuple = (255, 0, 0, 255)
    opacidad: float = 1.0
    activo: bool = True

    def __post_init__(self):
        object.__setattr__(self, "color", _color(self.color))
        object.__setattr__(self, "opacidad", _fraccion(self.opacidad, "opacidad"))
        object.__setattr__(self, "activo", _booleano(self.activo, "activo"))


@dataclass(frozen=True)
class SuperposicionDegradado(_Efecto):
    """Pinta la capa con un degradado (``formas.Relleno``; None = de negro a blanco, de arriba
    hacia abajo). El alfa de la capa queda; el del degradado multiplica la opacidad."""

    relleno: object = None
    opacidad: float = 1.0
    activo: bool = True

    def __post_init__(self):
        if self.relleno is not None:
            formas = _formas()
            if isinstance(self.relleno, dict):
                object.__setattr__(self, "relleno", formas.Relleno.desde_dict(self.relleno))
            elif not isinstance(self.relleno, formas.Relleno):
                raise ValueError(f"relleno tiene que ser un Relleno o None (llegó {self.relleno!r}).")
        object.__setattr__(self, "opacidad", _fraccion(self.opacidad, "opacidad"))
        object.__setattr__(self, "activo", _booleano(self.activo, "activo"))

    def como_dict(self) -> dict:
        return {"relleno": None if self.relleno is None else self.relleno.como_dict(),
                "opacidad": self.opacidad, "activo": self.activo}

    def relleno_efectivo(self):
        formas = _formas()
        if self.relleno is not None:
            return self.relleno
        return formas.Relleno("lineal", ((0, 0, 0, 255), (255, 255, 255, 255)), (), 90.0)

    def _girado(self, grados):
        rel = self.relleno_efectivo()
        return replace(self, relleno=replace(rel, angulo=(rel.angulo + grados) % 360.0))

    def _espejado(self, eje):
        rel = self.relleno_efectivo()
        a = rel.angulo
        return replace(self, relleno=replace(rel, angulo=((180.0 - a) if eje == "h" else -a) % 360.0))


_CLASES = {"sombra": Sombra, "trazo": Trazo, "resplandor": Resplandor, "color": SuperposicionColor,
           "degradado": SuperposicionDegradado}


@dataclass(frozen=True)
class EstilosCapa:
    """Los estilos de una capa: cada efecto es ``None`` o su dataclass (con ``activo``)."""

    sombra: Optional[Sombra] = None
    trazo: Optional[Trazo] = None
    resplandor: Optional[Resplandor] = None
    color: Optional[SuperposicionColor] = None
    degradado: Optional[SuperposicionDegradado] = None

    def __post_init__(self):
        for nombre, clase in _CLASES.items():
            v = getattr(self, nombre)
            if isinstance(v, dict):
                object.__setattr__(self, nombre, clase.desde_dict(v))
            elif v is not None and not isinstance(v, clase):
                raise ValueError(f"{nombre} tiene que ser un {clase.__name__} o None (llegó {v!r}).")

    @property
    def activos(self) -> tuple[str, ...]:
        """Los nombres de los efectos que están y están prendidos, en el orden de ``EFECTOS``."""
        return tuple(n for n in EFECTOS if getattr(self, n) is not None and getattr(self, n).activo)

    @property
    def vacio(self) -> bool:
        """Sin ningún efecto prendido (no cambia la capa)."""
        return not self.activos

    def como_dict(self) -> dict:
        """Para JSON: solo los efectos que están (prendidos o no)."""
        return {n: getattr(self, n).como_dict() for n in EFECTOS if getattr(self, n) is not None}

    @staticmethod
    def desde_dict(d) -> "EstilosCapa":
        """El de ``como_dict``. Lo desconocido se ignora; lo que no vale: ``ValueError``."""
        if not isinstance(d, dict):
            raise ValueError(f"Estilos de capa inválidos (llegó {d!r}).")
        try:
            return EstilosCapa(**{n: _CLASES[n].desde_dict(d[n]) for n in EFECTOS if d.get(n) is not None})
        except TypeError as error:
            raise ValueError(f"Estilos de capa inválidos ({error}).") from error

    def _cada(self, funcion) -> "EstilosCapa":
        return EstilosCapa(**{n: None if getattr(self, n) is None else funcion(getattr(self, n)) for n in EFECTOS})

    def escalados(self, factor: float) -> "EstilosCapa":
        """Con las distancias, tamaños y grosores multiplicados por ``factor`` (al escalar la imagen)."""
        f = _real(factor, "factor")
        if f <= 0:
            raise ValueError("El factor tiene que ser mayor que 0.")
        return self._cada(lambda e: e._escalado(f))

    def girados(self, grados: float) -> "EstilosCapa":
        """Para cuando el lienzo gira ``grados`` en sentido horario (la sombra y el degradado giran con él)."""
        g = _real(grados, "grados")
        return self._cada(lambda e: e._girado(g))

    def espejados(self, eje: str) -> "EstilosCapa":
        """Para cuando el lienzo se voltea: ``eje`` "h" (izquierda ↔ derecha) o "v" (arriba ↔ abajo)."""
        if eje not in ("h", "v"):
            raise ValueError(f"El eje es 'h' o 'v' (llegó {eje!r}).")
        return self._cada(lambda e: e._espejado(eje))


# ---------------------------------------------------------------------------
# Aplicar
# ---------------------------------------------------------------------------

def _activo(e) -> bool:
    return e is not None and e.activo


def _radio(tamano: float, escala: float) -> int:
    return max(0, int(round(tamano * escala)))


def _partes_trazo(t: Trazo, escala: float) -> tuple[float, float]:
    """(grosor afuera, grosor adentro) en píxeles de salida."""
    g = t.grosor * escala
    if t.posicion == "afuera":
        return g, 0.0
    if t.posicion == "adentro":
        return 0.0, g
    return g / 2.0, g / 2.0


def margenes(estilos: EstilosCapa, escala: float = 1.0) -> tuple[int, int, int, int]:
    """(izquierda, arriba, derecha, abajo): cuántos píxeles crece la imagen al aplicar los estilos."""
    izq = arr = der = aba = 0
    if _activo(estilos.sombra) and estilos.sombra.opacidad > 0:
        dx, dy = estilos.sombra.desplazamiento(escala)
        r = _radio(estilos.sombra.tamano, escala)
        izq, der, arr, aba = max(izq, r - dx), max(der, r + dx), max(arr, r - dy), max(aba, r + dy)
    if _activo(estilos.resplandor) and estilos.resplandor.opacidad > 0:
        r = _radio(estilos.resplandor.tamano, escala)
        izq, arr, der, aba = max(izq, r), max(arr, r), max(der, r), max(aba, r)
    if _activo(estilos.trazo) and estilos.trazo.opacidad > 0:
        afuera, _ = _partes_trazo(estilos.trazo, escala)
        if afuera > 0:
            r = int(math.ceil(afuera)) + 1
            izq, arr, der, aba = max(izq, r), max(arr, r), max(der, r), max(aba, r)
    return max(0, izq), max(0, arr), max(0, der), max(0, aba)


def _desenfocar(a: np.ndarray, radio: int) -> np.ndarray:
    """Desenfoque de ese radio (costo fijo por píxel): ``cv2.stackBlur`` con núcleo 2·radio + 1."""
    if radio <= 0:
        return a
    k = 2 * radio + 1
    return cv2.stackBlur(a, (k, k))


def _correr(a: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """``a`` corrido (dx, dy) píxeles, con ceros en lo que entra (mismo tamaño)."""
    h, w = a.shape
    salida = np.zeros_like(a)
    if abs(dx) >= w or abs(dy) >= h:
        return salida
    salida[max(0, dy):h + min(0, dy), max(0, dx):w + min(0, dx)] = a[max(0, -dy):h - max(0, dy),
                                                                      max(0, -dx):w - max(0, dx)]
    return salida


def _encima(arriba: np.ndarray, abajo: Optional[np.ndarray]) -> np.ndarray:
    """"Normal" premultiplicado: arriba + abajo·(1 - α arriba). (4, h, w)."""
    if abajo is None:
        return arriba
    abajo *= _F(1.0) - arriba[3]
    abajo += arriba
    return abajo


def _plano_color(color: tuple, alfa: np.ndarray, opacidad: float) -> np.ndarray:
    """(4, h, w) premultiplicado de un color liso con ese alfa (× opacidad × alfa del color)."""
    a = alfa * _F(opacidad * color[3] / 255.0)
    salida = np.empty((4,) + alfa.shape, _F)
    for i in range(3):
        np.multiply(a, _F(color[i] / 255.0), out=salida[i])
    salida[3] = a
    return salida


def aplicar_premultiplicado(planos: np.ndarray, estilos: EstilosCapa,
                            escala: float = 1.0) -> tuple[np.ndarray, tuple[int, int]]:
    """Como ``aplicar_estilos``, pero con RGBA **premultiplicado** en planos (4, h, w), uint8.

    Devuelve un arreglo nuevo (4, H, W) uint8 premultiplicado (o el mismo, si no hay nada que
    hacer) y (dx, dy). Es la que usa ``documento.componer``.
    """
    planos = np.asarray(planos)
    if planos.dtype != np.uint8 or planos.ndim != 3 or planos.shape[0] != 4:
        raise ValueError(f"Se esperaba RGBA premultiplicado en planos (4, h, w) uint8 (llegó {planos.dtype} "
                         f"{planos.shape}).")
    escala = _real(escala, "escala")
    if escala <= 0:
        raise ValueError("La escala tiene que ser mayor que 0.")
    if estilos.vacio:
        return planos, (0, 0)
    _, h, w = planos.shape
    izq, arr, der, aba = margenes(estilos, escala)
    H, W = h + arr + aba, w + izq + der
    contenido = np.zeros((4, H, W), _F)
    dentro = (slice(None), slice(arr, arr + h), slice(izq, izq + w))
    np.multiply(planos, _F(1.0 / 255.0), out=contenido[dentro], dtype=_F)
    alfa = contenido[3]

    binario = trazo_afuera = trazo_adentro = None
    if _activo(estilos.trazo) and estilos.trazo.opacidad > 0:
        trazo_afuera, trazo_adentro = _partes_trazo(estilos.trazo, escala)
        binario = (alfa >= _F(0.5)).astype(np.uint8)

    # 1-3: lo que va debajo del contenido.
    debajo = None
    s = estilos.sombra
    if _activo(s) and s.opacidad > 0:
        dx, dy = s.desplazamiento(escala)
        a = _correr(_desenfocar(alfa, _radio(s.tamano, escala)), dx, dy)
        debajo = _encima(_plano_color(s.color, a, s.opacidad), debajo)
    g = estilos.resplandor
    if _activo(g) and g.opacidad > 0:
        a = _desenfocar(alfa, _radio(g.tamano, escala))
        debajo = _encima(_plano_color(g.color, a, g.opacidad), debajo)
    if trazo_afuera:
        # Distancia de cada píxel de afuera al centro del píxel de adentro más cercano: el trazo cubre
        # [0, grosor] desde el borde, así que un píxel a distancia d queda cubierto clip(grosor + 1 - d).
        d = cv2.distanceTransform(1 - binario, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
        a = np.clip(_F(trazo_afuera + 1.0) - d, _F(0.0), _F(1.0))
        # Adentro, solo en el borde (lo que el antialias deja ver); en el interior, nada.
        interior = cv2.erode(binario, np.ones((3, 3), np.uint8), borderType=cv2.BORDER_CONSTANT, borderValue=0)
        a[interior.astype(bool)] = 0.0
        debajo = _encima(_plano_color(estilos.trazo.color, a, estilos.trazo.opacidad), debajo)

    # 4: el contenido, con las superposiciones (cambian el color, no el alfa: "source-atop").
    dg = estilos.degradado
    if _activo(dg) and dg.opacidad > 0:
        try:
            formas = _formas()
        except ImportError:   # sin el módulo de formas (no debería pasar): sin el degradado
            formas = None
        if formas is not None:
            grad = np.asarray(formas.renderizar_relleno(dg.relleno_efectivo(), w, h))
            t = np.multiply(grad[..., 3], _F(dg.opacidad / 255.0), dtype=_F)
            region = contenido[dentro]
            a_c = region[3]
            for i in range(3):
                c = region[i]
                c *= _F(1.0) - t
                c += np.multiply(grad[..., i], _F(1.0 / 255.0), dtype=_F) * t * a_c
    co = estilos.color
    if _activo(co) and co.opacidad > 0:
        t = _F(co.opacidad * co.color[3] / 255.0)
        for i in range(3):
            c = contenido[i]
            c *= _F(1.0) - t
            c += alfa * (t * _F(co.color[i] / 255.0))
    # 5: el trazo de adentro, sobre el contenido y también sin cambiar su alfa (los píxeles de afuera
    # del umbral tienen d = 0: el borde suave toma el color del trazo).
    if trazo_adentro:
        d = cv2.distanceTransform(binario, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
        b = np.clip(_F(trazo_adentro + 1.0) - d, _F(0.0), _F(1.0))
        b *= _F(estilos.trazo.opacidad * estilos.trazo.color[3] / 255.0)
        for i in range(3):
            c = contenido[i]
            c *= _F(1.0) - b
            c += alfa * b * _F(estilos.trazo.color[i] / 255.0)
    resultado = _encima(contenido, debajo)

    salida = np.empty((4, H, W), np.uint8)
    for i in range(4):
        cv2.convertScaleAbs(resultado[i], salida[i], alpha=255.0)
    np.minimum(salida[:3], salida[3], out=salida[:3])   # premultiplicado: el color no pasa al alfa
    return salida, (-izq, -arr)


def aplicar_estilos(rgba: np.ndarray, estilos: EstilosCapa, escala: float = 1.0) -> tuple[np.ndarray, tuple[int, int]]:
    """Aplica los estilos a una imagen RGBA uint8 (h, w, 4), **sin premultiplicar**.

    Devuelve ``(rgba_resultado, (dx, dy))``: RGBA uint8 sin premultiplicar (más grande si hace
    falta) y dónde cae su esquina de arriba a la izquierda en las coordenadas de ``rgba`` (0 o
    negativo). ``escala`` multiplica las medidas (que están en píxeles del documento). Sin
    estilos prendidos devuelve una copia y (0, 0). No modifica la entrada.
    """
    rgba = np.asarray(rgba)
    if rgba.dtype != np.uint8 or rgba.ndim != 3 or rgba.shape[2] != 4 or rgba.size == 0:
        raise ValueError(f"Se esperaba RGBA uint8 (h, w, 4) (llegó {rgba.dtype} {rgba.shape}).")
    if estilos.vacio:
        return rgba.copy(), (0, 0)
    prem = cv2.cvtColor(np.ascontiguousarray(rgba), cv2.COLOR_RGBA2mRGBA)
    planos = np.ascontiguousarray(np.moveaxis(prem, -1, 0))
    salida, desp = aplicar_premultiplicado(planos, estilos, escala)
    junto = np.ascontiguousarray(np.moveaxis(salida, 0, -1))
    return cv2.cvtColor(junto, cv2.COLOR_mRGBA2RGBA), desp


__all__ = [
    "EFECTOS", "EstilosCapa", "POSICIONES_TRAZO", "Resplandor", "Sombra", "SuperposicionColor",
    "SuperposicionDegradado", "TOPE_PIXELES", "Trazo", "aplicar_estilos", "aplicar_premultiplicado", "margenes",
]
