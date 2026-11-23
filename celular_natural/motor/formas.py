"""Formas vectoriales y rellenos (color o degradado) a RGBA. Sin Qt.

Rellenos
--------
Un ``Relleno`` es "ninguno", un "color" (el primero de ``colores``) o un degradado "lineal" o
"radial" de dos o más colores, con ``paradas`` de 0 a 1 (vacío = repartidas parejo). Los
colores son RGBA de 0 a 255, **sin premultiplicar**. El degradado se interpola
**premultiplicado** (como Photoshop y los navegadores): de rojo opaco a azul transparente,
el medio es rojo semitransparente, no violeta. ``renderizar_relleno`` cubre un lienzo:

* lineal: ``angulo`` en grados, con la y hacia abajo: 0 = de izquierda a derecha y 90 = de
  arriba hacia abajo. La línea del degradado pasa por el centro y mide lo que la proyección
  del rectángulo sobre esa dirección (|ancho·cos| + |alto·sen|): las dos esquinas extremas
  tienen exactamente el primer y el último color.
* radial: desde el centro, con radio igual a media diagonal (las esquinas llegan al último color).

Formas
------
``ParamsForma`` describe la forma en píxeles del documento; ``ancho`` × ``alto`` es su caja
(sin el trazo):

* **rectangulo**: con ``radio`` en las esquinas (se limita a la mitad del lado corto).
* **elipse**: inscripta en la caja.
* **linea**: una barra horizontal de ``ancho`` de largo y ``alto`` de grosor, con el relleno
  (la dirección la da la rotación de la capa: la interfaz pone el largo y el ángulo del arrastre).
* **flecha**: horizontal, apunta a la derecha. La punta ocupa el alto entero y mide
  min(alto, ancho / 2) de largo; el cuerpo, el 40 % del alto.
* **poligono**: regular, de ``lados`` lados y con un vértice arriba, con los vértices sobre la
  elipse de la caja (con ancho = alto es regular; si no, se estira).
* **estrella**: ``puntas`` puntas, una arriba; las puntas sobre la elipse de la caja y los
  vértices de adentro sobre la misma elipse achicada por ``radio_interno``.

El **trazo** (``trazo`` y ``grosor``) va **centrado en el borde**, con esquinas en inglete
(límite 4, como SVG; más agudo, bisel). Se pinta encima del relleno.

``renderizar_forma(p, escala)``
-------------------------------
RGBA uint8 sin premultiplicar, con ``escala`` píxeles por píxel del documento. **El centro de
la imagen es el centro de la forma** y el tamaño es par: 2·⌈mitad de lo que se pinta⌉ por lado
(sin margen extra, porque el antialias no sale de la figura). Un rectángulo de 400 × 300 sin
trazo da exactamente 400 × 300; con trazo de 20, 420 × 320. A otra escala el tamaño es
*casi* proporcional (por el redondeo): para ubicarla hay que usar el centro y la escala, no
la razón entre los tamaños. Donde el alfa es 0, el RGB es el del relleno (no se ensucia de
negro al interpolar).

Cómo se dibuja
--------------
Los bordes curvos se aproximan con segmentos (error de 0,05 px como mucho) y cada región se
rasteriza con **cobertura exacta** (``_cobertura``: el área de cada píxel que cae adentro,
como los rasterizadores de fuentes, vectorizado con numpy): antialias sin sobremuestreo,
área exacta y simetría exacta. (``cv2.fillPoly`` no sirve para esto: llena de
``round(x0)`` a ``round(x1)`` con los dos extremos incluidos, así que agranda medio píxel
de cada lado y desempata siempre para el mismo lado.) El trazo es el contorno desplazado
hacia afuera menos el desplazado hacia adentro (medio grosor cada uno; en el rectángulo y la
elipse, con la fórmula exacta), en una sola pasada. Si el trazo es tan grueso que el
desplazamiento se da vuelta, se usa ``cv2.polylines`` grueso y sobremuestreado (uniones
redondas), que cubre lo mismo salvo en las esquinas.
"""

from __future__ import annotations

import math
import numbers
from dataclasses import dataclass, fields
from typing import Optional

import cv2
import numpy as np

Color = tuple[int, int, int, int]          # RGBA 0..255, sin premultiplicar

TIPOS_RELLENO = ("ninguno", "color", "lineal", "radial")
TIPOS_FORMA = ("rectangulo", "elipse", "linea", "flecha", "poligono", "estrella")
LIMITE_INGLETE = 4.0             # como stroke-miterlimit de SVG
LADO_MAX_RENDER = 32768          # píxeles por lado de un render, como mucho
AREA_MAX_RENDER = 100_000_000    # píxeles de un render, como mucho (400 MB en RGBA)

_SUBPIXEL = 4                    # bits de subpíxel para cv2.fillPoly
_TOLERANCIA_CURVA = 0.05         # px: error máximo al aproximar un arco con segmentos
_PIXELES_FRANJA = 12_000_000     # píxeles sobremuestreados por franja, como mucho
_PASOS_TABLA = 4096              # entradas de la tabla de colores de un degradado

_F = np.float32


# ---------------------------------------------------------------------------
# Validaciones
# ---------------------------------------------------------------------------

def _real(valor, nombre: str) -> float:
    """Un número finito (no texto, ni booleano, ni None)."""
    if (isinstance(valor, (str, bytes, bool, np.bool_)) or valor is None
            or not isinstance(valor, (numbers.Real, np.number))):
        raise ValueError(f"{nombre} tiene que ser un número (llegó {valor!r}).")
    v = float(valor)
    if not math.isfinite(v):
        raise ValueError(f"{nombre} tiene que ser un número finito (llegó {valor!r}).")
    return v


def _entero(valor, nombre: str, minimo: int) -> int:
    if isinstance(valor, (bool, np.bool_)) or not isinstance(valor, (numbers.Integral, np.integer)):
        raise ValueError(f"{nombre} tiene que ser un entero (llegó {valor!r}).")
    if int(valor) < minimo:
        raise ValueError(f"{nombre} tiene que ser {minimo} o más (llegó {valor!r}).")
    return int(valor)


def _booleano(valor, nombre: str) -> bool:
    if not isinstance(valor, (bool, np.bool_)):
        raise ValueError(f"{nombre} tiene que ser verdadero o falso (llegó {valor!r}).")
    return bool(valor)


def color_rgba(valor, nombre: str = "color") -> Color:
    """Un color como tupla RGBA de enteros 0..255. Acepta lista o tupla de 3 (opaco) o 4 números."""
    if isinstance(valor, (str, bytes)) or not isinstance(valor, (tuple, list, np.ndarray)):
        raise ValueError(f"{nombre} tiene que ser RGB o RGBA (llegó {valor!r}).")
    if len(valor) not in (3, 4):
        raise ValueError(f"{nombre} tiene que tener 3 o 4 valores (llegó {valor!r}).")
    canales = []
    for v in valor:
        x = _real(v, nombre)
        if not 0.0 <= x <= 255.0:
            raise ValueError(f"{nombre}: cada canal va de 0 a 255 (llegó {valor!r}).")
        canales.append(int(round(x)))
    if len(canales) == 3:
        canales.append(255)
    return tuple(canales)


def _positivo(valor, nombre: str) -> float:
    v = _real(valor, nombre)
    if v <= 0:
        raise ValueError(f"{nombre} tiene que ser mayor que 0 (llegó {valor!r}).")
    return v


def _desde_dict(clase, datos, nombre: str):
    if not isinstance(datos, dict):
        raise ValueError(f"{nombre} inválido: se esperaba un diccionario (llegó {type(datos).__name__}).")
    try:
        return clase(**{f.name: datos[f.name] for f in fields(clase) if f.name in datos})
    except TypeError as error:
        raise ValueError(f"{nombre} inválido: {error}") from error


# ---------------------------------------------------------------------------
# Relleno y parámetros de forma
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Relleno:
    """Cómo se rellena algo (ver el módulo). Inmutable y hasheable (sirve de clave de caché).

    tipo      "ninguno" | "color" | "lineal" | "radial".
    colores   RGBA 0..255 (al menos uno; "color" usa el primero).
    paradas   de 0 a 1, no decrecientes, una por color; vacío = repartidas parejo.
    angulo    grados (lineal), con la y hacia abajo: 0 = hacia la derecha, 90 = hacia abajo.
    """

    tipo: str = "color"
    colores: tuple[Color, ...] = ((255, 255, 255, 255),)
    paradas: tuple[float, ...] = ()
    angulo: float = 90.0

    def __post_init__(self):
        if not isinstance(self.tipo, str) or self.tipo not in TIPOS_RELLENO:
            raise ValueError(f"Tipo de relleno desconocido: {self.tipo!r}.")
        cols = self.colores
        if isinstance(cols, (str, bytes)) or not isinstance(cols, (tuple, list)):
            raise ValueError(f"colores tiene que ser una lista de colores (llegó {cols!r}).")
        cols = tuple(color_rgba(c, f"colores[{i}]") for i, c in enumerate(cols))
        if not cols:
            raise ValueError("Un relleno necesita al menos un color.")
        pars = self.paradas
        if isinstance(pars, (str, bytes)) or not isinstance(pars, (tuple, list)):
            raise ValueError(f"paradas tiene que ser una lista de números (llegó {pars!r}).")
        pars = tuple(_real(v, "paradas") for v in pars)
        if pars:
            if len(pars) != len(cols):
                raise ValueError(f"Tiene que haber una parada por color ({len(cols)}), o ninguna.")
            if any(not 0.0 <= v <= 1.0 for v in pars):
                raise ValueError(f"Las paradas van de 0 a 1 (llegó {pars}).")
            if any(b < a for a, b in zip(pars, pars[1:])):
                raise ValueError(f"Las paradas no pueden bajar (llegó {pars}).")
        object.__setattr__(self, "colores", cols)
        object.__setattr__(self, "paradas", pars)
        object.__setattr__(self, "angulo", _real(self.angulo, "angulo"))

    def como_dict(self) -> dict:
        """Para JSON: solo tipos básicos."""
        return {"tipo": self.tipo, "colores": [list(c) for c in self.colores],
                "paradas": list(self.paradas), "angulo": self.angulo}

    @staticmethod
    def desde_dict(d) -> "Relleno":
        """El de ``como_dict`` (o un ``Relleno``, tal cual). Lo que falta toma el valor por
        defecto y lo desconocido se ignora; lo que no vale: ``ValueError``."""
        if isinstance(d, Relleno):
            return d
        return _desde_dict(Relleno, d, "Relleno")


@dataclass(frozen=True)
class ParamsForma:
    """Una forma vectorial (ver el módulo). Inmutable y hasheable.

    tipo            rectangulo | elipse | linea | flecha | poligono | estrella.
    ancho, alto     la caja de la forma, en píxeles del documento (> 0; en la línea, alto = grosor).
    radio           de las esquinas del rectángulo (>= 0).
    lados           del polígono (>= 3).
    puntas          de la estrella (>= 3); radio_interno, de 0 (excluido) a 1.
    relleno         ``Relleno`` (o su diccionario).
    trazo, grosor   color y grosor del trazo (0 = sin trazo), centrado en el borde.
    """

    tipo: str = "rectangulo"
    ancho: float = 400.0
    alto: float = 300.0
    radio: float = 0.0
    lados: int = 6
    puntas: int = 5
    radio_interno: float = 0.45
    relleno: Relleno = Relleno()
    trazo: Color = (0, 0, 0, 255)
    grosor: float = 0.0

    def __post_init__(self):
        if not isinstance(self.tipo, str) or self.tipo not in TIPOS_FORMA:
            raise ValueError(f"Tipo de forma desconocido: {self.tipo!r}.")
        object.__setattr__(self, "ancho", _positivo(self.ancho, "ancho"))
        object.__setattr__(self, "alto", _positivo(self.alto, "alto"))
        radio = _real(self.radio, "radio")
        if radio < 0:
            raise ValueError(f"El radio no puede ser negativo (llegó {radio}).")
        object.__setattr__(self, "radio", radio)
        object.__setattr__(self, "lados", _entero(self.lados, "lados", 3))
        object.__setattr__(self, "puntas", _entero(self.puntas, "puntas", 3))
        ri = _real(self.radio_interno, "radio_interno")
        if not 0.0 < ri <= 1.0:
            raise ValueError(f"radio_interno va de 0 (excluido) a 1 (llegó {ri}).")
        object.__setattr__(self, "radio_interno", ri)
        relleno = self.relleno
        if isinstance(relleno, dict):
            relleno = Relleno.desde_dict(relleno)
        if not isinstance(relleno, Relleno):
            raise ValueError(f"relleno tiene que ser un Relleno (llegó {relleno!r}).")
        object.__setattr__(self, "relleno", relleno)
        object.__setattr__(self, "trazo", color_rgba(self.trazo, "trazo"))
        grosor = _real(self.grosor, "grosor")
        if grosor < 0:
            raise ValueError(f"El grosor no puede ser negativo (llegó {grosor}).")
        object.__setattr__(self, "grosor", grosor)

    def como_dict(self) -> dict:
        """Para JSON: solo tipos básicos (el relleno, anidado)."""
        d = {f.name: getattr(self, f.name) for f in fields(self)}
        d["relleno"] = self.relleno.como_dict()
        d["trazo"] = list(self.trazo)
        return d

    @staticmethod
    def desde_dict(d) -> "ParamsForma":
        """El de ``como_dict``. Lo que falta toma el valor por defecto y lo desconocido se
        ignora; lo que no vale: ``ValueError``."""
        if isinstance(d, ParamsForma):
            return d
        return _desde_dict(ParamsForma, d, "ParamsForma")


# ---------------------------------------------------------------------------
# Degradados
# ---------------------------------------------------------------------------

def _tabla_colores(relleno: Relleno, pasos: int = _PASOS_TABLA) -> np.ndarray:
    """(pasos, 4) uint8: el color en t = i / (pasos - 1), interpolado premultiplicado."""
    cols = np.array(relleno.colores, np.float64)
    if len(cols) == 1:
        return np.repeat(cols.round().astype(np.uint8), pasos, axis=0)
    pos = np.array(relleno.paradas if relleno.paradas else np.linspace(0.0, 1.0, len(cols)))
    t = np.linspace(0.0, 1.0, pasos)
    alfa = cols[:, 3] / 255.0
    a = np.interp(t, pos, alfa)
    tabla = np.empty((pasos, 4))
    tabla[:, 3] = a * 255.0
    for c in range(3):
        premult = np.interp(t, pos, cols[:, c] * alfa)
        directo = np.interp(t, pos, cols[:, c])          # donde todo es transparente
        with np.errstate(divide="ignore", invalid="ignore"):
            tabla[:, c] = np.where(a > 1e-9, premult / a, directo)
    return np.clip(np.rint(tabla), 0, 255).astype(np.uint8)


def _direccion(grados: float) -> tuple[float, float]:
    """(cos, sen) exactos en los múltiplos de 90°."""
    if float(grados) % 90.0 == 0.0:
        k = int(round(float(grados) / 90.0)) % 4
        return ((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0))[k]
    r = math.radians(grados)
    return math.cos(r), math.sin(r)


def _degradado(ancho: int, alto: int, p0, p1, relleno: Relleno, radial: bool) -> np.ndarray:
    """RGBA (alto, ancho, 4) del degradado de ``relleno`` de ``p0`` a ``p1`` (en píxeles, con
    el centro del píxel (i, j) en (i + 0,5, j + 0,5)). Lineal: t es la proyección sobre p0→p1;
    radial: la distancia a p0 sobre |p1 - p0|. Antes de p0, el primer color, y después de p1,
    el último, exactos. Si p0 = p1, todo es el último color."""
    tabla = _tabla_colores(relleno)
    n = len(tabla) - 1
    x0, y0 = float(p0[0]), float(p0[1])
    dx, dy = float(p1[0]) - x0, float(p1[1]) - y0
    largo2 = dx * dx + dy * dy
    if largo2 <= 1e-18:
        out = np.empty((alto, ancho, 4), np.uint8)
        out[:] = tabla[-1]
        return out
    xs = np.arange(ancho, dtype=np.float64) + 0.5 - x0
    ys = np.arange(alto, dtype=np.float64) + 0.5 - y0
    if not radial:
        bx = (xs * (dx * n / largo2)).astype(_F)
        by = (ys * (dy * n / largo2)).astype(_F)
        if dy == 0.0 or dx == 0.0:              # una sola dirección: una fila o una columna
            eje = bx if dy == 0.0 else by
            idx = np.clip(np.rint(eje.astype(np.float64)), 0, n).astype(np.intp)
            colores = tabla[idx]
            if dy == 0.0:
                return np.ascontiguousarray(np.broadcast_to(colores[None, :, :], (alto, ancho, 4)))
            return np.ascontiguousarray(np.broadcast_to(colores[:, None, :], (alto, ancho, 4)))
        t = bx[None, :] + (by + _F(0.5))[:, None]
    else:
        esc = n / math.sqrt(largo2)
        t = ((xs * esc) ** 2).astype(_F)[None, :] + ((ys * esc) ** 2).astype(_F)[:, None]
        cv2.sqrt(t, t)
        t += _F(0.5)
    np.clip(t, 0, n, out=t)
    # la tabla empaquetada (un uint32 por color) se busca más rápido que (n, 4)
    empaquetada = np.ascontiguousarray(tabla).view(np.uint32).ravel()
    return empaquetada[t.astype(np.int32)].view(np.uint8).reshape(alto, ancho, 4)


def _degradado_caja(relleno: Relleno, ancho: int, alto: int, cx: float, cy: float,
                    caja_w: float, caja_h: float) -> np.ndarray:
    """El relleno lineal o radial de una caja de ``caja_w`` × ``caja_h`` centrada en (cx, cy),
    pintado en un lienzo de ``ancho`` × ``alto``."""
    if relleno.tipo == "radial":
        r = math.hypot(caja_w, caja_h) / 2.0
        return _degradado(ancho, alto, (cx, cy), (cx + r, cy), relleno, radial=True)
    c, s = _direccion(relleno.angulo)
    medio = (abs(caja_w * c) + abs(caja_h * s)) / 2.0
    return _degradado(ancho, alto, (cx - c * medio, cy - s * medio), (cx + c * medio, cy + s * medio),
                      relleno, radial=False)


def _lado(valor, nombre: str) -> int:
    v = _entero(valor, nombre, 1)
    if v > LADO_MAX_RENDER:
        raise ValueError(f"{nombre} es demasiado grande ({v}; como mucho {LADO_MAX_RENDER}).")
    return v


def renderizar_relleno(r: Relleno, ancho: int, alto: int) -> np.ndarray:
    """RGBA uint8 (alto, ancho, 4) del relleno sobre un lienzo de ``ancho`` × ``alto`` (ver el
    módulo). "ninguno" da todo transparente."""
    if not isinstance(r, Relleno):
        raise ValueError(f"Se esperaba un Relleno (llegó {r!r}).")
    ancho, alto = _lado(ancho, "ancho"), _lado(alto, "alto")
    if ancho * alto > AREA_MAX_RENDER:
        raise ValueError(f"El relleno es demasiado grande ({ancho}×{alto}).")
    if r.tipo == "ninguno":
        return np.zeros((alto, ancho, 4), np.uint8)
    if r.tipo == "color":
        out = np.empty((alto, ancho, 4), np.uint8)
        out[:] = r.colores[0]
        return out
    return _degradado_caja(r, ancho, alto, ancho / 2.0, alto / 2.0, float(ancho), float(alto))


# ---------------------------------------------------------------------------
# Geometría (en píxeles del render, centrada en el origen, con la y hacia abajo)
# ---------------------------------------------------------------------------

def _segmentos_arco(radio: float, angulo: float) -> int:
    """Segmentos para que un arco de ``radio`` y ``angulo`` (radianes) no se aparte más de
    ``_TOLERANCIA_CURVA`` de la curva."""
    if radio <= _TOLERANCIA_CURVA:
        return 1
    paso = 2.0 * math.acos(1.0 - _TOLERANCIA_CURVA / radio)
    return max(2, int(math.ceil(angulo / paso)))


def _rectangulo(mw: float, mh: float, r: float) -> np.ndarray:
    """Rectángulo de medio ancho ``mw`` y medio alto ``mh``, con esquinas de radio ``r``."""
    r = min(max(r, 0.0), mw, mh)
    if r <= 1e-9:
        return np.array([[-mw, -mh], [mw, -mh], [mw, mh], [-mw, mh]])
    n = _segmentos_arco(r, math.pi / 2)
    a = np.linspace(0.0, math.pi / 2, n + 1)
    arco = np.stack([np.cos(a), np.sin(a)], 1) * r
    partes = []
    for k, (cx, cy) in enumerate(((mw - r, -mh + r), (mw - r, mh - r), (-mw + r, mh - r), (-mw + r, -mh + r))):
        giro = math.pi / 2 * (k - 1)          # arranca arriba a la derecha, en -90°
        c, s = math.cos(giro), math.sin(giro)
        rot = arco @ np.array([[c, s], [-s, c]])
        partes.append(rot + (cx, cy))
    return np.concatenate(partes)


def _elipse(a: float, b: float, d: float = 0.0) -> np.ndarray:
    """Elipse de semiejes ``a`` y ``b``, desplazada ``d`` por la normal (curva paralela)."""
    n = 4 * _segmentos_arco(max(a, b) + max(d, 0.0), math.pi / 2)
    t = np.linspace(0.0, 2 * math.pi, n, endpoint=False)
    c, s = np.cos(t), np.sin(t)
    p = np.stack([a * c, b * s], 1)
    if d:
        normal = np.stack([b * c, a * s], 1)
        normal /= np.hypot(normal[:, 0], normal[:, 1])[:, None]
        p = p + d * normal
    return p


def _flecha(mw: float, mh: float) -> np.ndarray:
    cabeza = min(2.0 * mh, mw)               # min(alto, ancho / 2)
    cuerpo = 0.4 * mh
    xc = mw - cabeza
    return np.array([[-mw, -cuerpo], [xc, -cuerpo], [xc, -mh], [mw, 0.0],
                     [xc, mh], [xc, cuerpo], [-mw, cuerpo]])


def _regular(n: int, mw: float, mh: float, interno: Optional[float] = None) -> np.ndarray:
    """Polígono regular de ``n`` lados (o estrella de ``n`` puntas, con ``interno``) con un
    vértice arriba, sobre la elipse de semiejes ``mw`` y ``mh``."""
    if interno is None:
        ang = -math.pi / 2 + 2 * math.pi * np.arange(n) / n
        radios = np.ones(n)
    else:
        ang = -math.pi / 2 + math.pi * np.arange(2 * n) / n
        radios = np.where(np.arange(2 * n) % 2 == 0, 1.0, interno)
    p = np.stack([np.cos(ang) * radios * mw, np.sin(ang) * radios * mh], 1)
    # simetría exacta respecto del eje vertical (cos(90°) no da 0 justo)
    p[np.abs(p[:, 0]) < 1e-9 * max(mw, 1.0), 0] = 0.0
    return p


def _sin_repetidos(p: np.ndarray) -> np.ndarray:
    siguiente = np.roll(p, -1, axis=0)
    distinto = np.hypot(*(siguiente - p).T) > 1e-9
    return p[distinto] if distinto.any() else p[:1]


def _area_con_signo(p: np.ndarray) -> float:
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def _desplazar(poli: np.ndarray, d: float) -> Optional[np.ndarray]:
    """El contorno desplazado ``d`` hacia afuera (negativo = hacia adentro), con esquinas en
    inglete (bisel si pasa ``LIMITE_INGLETE``). None si algún lado se da vuelta (el
    desplazamiento es más grande que la forma en esa zona)."""
    p = _sin_repetidos(np.asarray(poli, np.float64))
    if len(p) < 3:
        return None
    lados = np.roll(p, -1, axis=0) - p
    largo = np.hypot(lados[:, 0], lados[:, 1])
    signo = 1.0 if _area_con_signo(p) > 0 else -1.0
    normal = signo * np.stack([lados[:, 1], -lados[:, 0]], 1) / largo[:, None]   # hacia afuera
    normal_prev = np.roll(normal, 1, axis=0)
    lados_prev = np.roll(lados, 1, axis=0)
    coseno = np.einsum("ij,ij->i", normal_prev, normal)
    denom = 1.0 + coseno
    with np.errstate(divide="ignore", invalid="ignore"):
        inglete = (normal_prev + normal) / denom[:, None]
        razon = 1.0 / np.sqrt(np.maximum(denom, 0.0) / 2.0)
    giro = lados_prev[:, 0] * lados[:, 1] - lados_prev[:, 1] * lados[:, 0]
    convexo = giro * signo > 0
    sobresale = convexo if d > 0 else ~convexo
    bisel = (sobresale & (razon > LIMITE_INGLETE)) | (denom < 1e-9)
    if np.any((denom < 1e-9) & ~sobresale):
        return None
    inglete = np.where(bisel[:, None], 0.0, inglete)
    primero = np.where(bisel[:, None], p + d * normal_prev, p + d * inglete)
    ultimo = np.where(bisel[:, None], p + d * normal, p + d * inglete)
    # cada lado tiene que seguir apuntando para el mismo lado
    tramo = np.roll(primero, -1, axis=0) - ultimo
    if np.any(np.einsum("ij,ij->i", tramo, lados) <= 0):
        return None
    return np.stack([primero, ultimo], 1).reshape(-1, 2)


def _contornos(p: ParamsForma, escala: float):
    """(relleno, afuera, adentro, linea): polígonos centrados en el origen, en píxeles del render.

    ``afuera`` y ``adentro`` son el contorno desplazado medio grosor (``adentro`` None = vacío);
    si no se pueden desplazar, los dos son None y ``linea`` es el grosor para ``polylines``.
    Sin trazo, todo None salvo ``relleno``.
    """
    mw, mh = p.ancho * escala / 2.0, p.alto * escala / 2.0
    d = p.grosor * escala / 2.0
    hay_trazo = d > 0 and p.trazo[3] > 0
    if p.tipo in ("rectangulo", "linea"):
        r = p.radio * escala if p.tipo == "rectangulo" else 0.0
        r = min(r, mw, mh)
        forma = _rectangulo(mw, mh, r)
        if not hay_trazo:
            return forma, None, None, None
        afuera = _rectangulo(mw + d, mh + d, r + d if r > 0 else 0.0)
        adentro = _rectangulo(mw - d, mh - d, max(r - d, 0.0)) if d < min(mw, mh) else None
        return forma, afuera, adentro, None
    if p.tipo == "elipse":
        forma = _elipse(mw, mh)
        if not hay_trazo:
            return forma, None, None, None
        afuera = _elipse(mw, mh, d)
        if d >= min(mw, mh):
            return forma, afuera, None, None
        adentro = _desplazar_suave(mw, mh, -d)
        if adentro is None:
            return forma, None, None, 2.0 * d
        return forma, afuera, adentro, None
    if p.tipo == "flecha":
        forma = _flecha(mw, mh)
    elif p.tipo == "poligono":
        forma = _regular(p.lados, mw, mh)
    else:
        forma = _regular(p.puntas, mw, mh, p.radio_interno)
    if not hay_trazo:
        return forma, None, None, None
    afuera, adentro = _desplazar(forma, d), _desplazar(forma, -d)
    if afuera is None or adentro is None:
        return forma, None, None, 2.0 * d
    return forma, afuera, adentro, None


def _desplazar_suave(a: float, b: float, d: float) -> Optional[np.ndarray]:
    """La elipse desplazada por la normal; None si se cruza (``d`` más que el radio de curvatura)."""
    if -d >= min(a, b) ** 2 / max(a, b):
        return None
    return _elipse(a, b, d)


# ---------------------------------------------------------------------------
# Rasterizado con sobremuestreo
# ---------------------------------------------------------------------------

def _tramos(n: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Para expandir: el índice del dueño y el número dentro del dueño, para ``n[i]`` elementos
    de cada dueño ``i``."""
    duenio = np.repeat(np.arange(len(n)), n)
    inicio = np.cumsum(n) - n
    return duenio, np.arange(int(n.sum())) - inicio[duenio]


def _h(t: np.ndarray) -> np.ndarray:
    """∫ de −∞ a t de clamp(v, 0, 1) dv."""
    return np.where(t <= 0.0, 0.0, np.where(t < 1.0, 0.5 * t * t, t - 0.5))


def _cobertura(polis, ancho: int, alto: int) -> np.ndarray:
    """Una sola cobertura (ver ``_coberturas``)."""
    return _coberturas([polis], ancho, alto)[0]


def _coberturas(grupos, ancho: int, alto: int) -> list:
    """Por cada grupo, uint8 (alto, ancho): la fracción **exacta** de cada píxel cubierta por
    sus polígonos. Los grupos se cuentan juntos, uno al lado del otro en el mismo acumulador
    (cada polígono cerrado suma 0 por fila, así que la suma por filas no pasa de un grupo al
    otro): relleno y trazo salen de una sola pasada.

    Cada grupo: pares (polígono, signo) en píxeles del render (origen arriba a la izquierda;
    el píxel (i, j) es [i, i + 1) × [j, j + 1)). Signo +1 suma y −1 resta (un agujero
    contenido en otro polígono: así sale un trazo, afuera menos adentro, de una sola vez).

    Cada lado se parte por filas y cada tramo deja en las celdas que toca el área que queda a
    su derecha (con signo, según suba o baje); la suma acumulada por fila es la cobertura.
    Es la cuenta de los rasterizadores de fuentes, vectorizada: sin sobremuestreo, el área
    sale exacta (salvo redondeo a 1/255) y una figura simétrica da un render simétrico.
    """
    trozos = []
    for g, polis in enumerate(grupos):
        for poli, signo in polis:
            p = np.asarray(poli, np.float64)
            if len(p) < 3:
                continue
            if _area_con_signo(p) < 0:
                signo = -signo
            trozos.append((p, np.roll(p, -1, axis=0), float(signo), g))
    if not trozos:
        return [np.zeros((alto, ancho), np.uint8) for _ in grupos]
    p0 = np.concatenate([t[0] for t in trozos])
    p1 = np.concatenate([t[1] for t in trozos])
    signos = np.concatenate([np.full(len(t[0]), t[2]) for t in trozos])
    grupo = np.concatenate([np.full(len(t[0]), t[3], np.int64) for t in trozos])
    x0, y0, x1, y1 = p0[:, 0], p0[:, 1], p1[:, 0], p1[:, 1]
    sentido = np.where(y1 > y0, 1.0, -1.0) * signos
    vuelta = y0 > y1
    ya, yb = np.where(vuelta, y1, y0), np.where(vuelta, y0, y1)
    xa, xb = np.where(vuelta, x1, x0), np.where(vuelta, x0, x1)
    yt, yf = np.clip(ya, 0.0, alto), np.clip(yb, 0.0, alto)
    sirve = yf > yt                       # sin los lados horizontales (no aportan)
    xa, xb, ya, yb, yt, yf = xa[sirve], xb[sirve], ya[sirve], yb[sirve], yt[sirve], yf[sirve]
    sentido, grupo = sentido[sirve], grupo[sirve]
    pendiente = (xb - xa) / (yb - ya)
    xa = xa + (yt - ya) * pendiente
    ya, yb = yt, yf
    # cada lado, por filas
    f0 = np.floor(ya).astype(np.int64)
    filas_lado = np.ceil(yb).astype(np.int64) - f0
    lado, k = _tramos(filas_lado)
    fila = f0[lado] + k
    arriba = np.maximum(fila, ya[lado])
    abajo = np.minimum(fila + 1.0, yb[lado])
    xs = xa[lado] + (arriba - ya[lado]) * pendiente[lado]
    xi = xa[lado] + (abajo - ya[lado]) * pendiente[lado]
    izq = np.clip(np.minimum(xs, xi), 0.0, ancho)
    der = np.clip(np.maximum(xs, xi), 0.0, ancho)
    peso = (abajo - arriba) * sentido[lado]
    # cada tramo, por celdas (de la de su punto izquierdo a la de su punto derecho)
    c0 = np.floor(izq).astype(np.int64)
    c1 = np.minimum(np.ceil(der).astype(np.int64), ancho)
    c1 = np.maximum(c1, c0)
    tramo, k = _tramos(c1 - c0 + 1)
    celda = c0[tramo] + k
    i, d = izq[tramo], der[tramo]
    w = d - i
    angosto = w < 1e-9
    w_seguro = np.where(angosto, 1.0, w)
    medio = 0.5 * (i + d)

    def derecha(c):
        """La parte de la celda ``c`` a la derecha del tramo, promediada en el tramo."""
        exacta = (_h(c + 1.0 - i) - _h(c + 1.0 - d)) / w_seguro
        return np.where(angosto, np.clip(c + 1.0 - medio, 0.0, 1.0), exacta)

    aporte = peso[tramo] * (derecha(celda) - derecha(celda - 1))
    paso = ancho + 1
    total = len(grupos) * paso
    acumulado = np.bincount(fila[tramo] * total + grupo[lado][tramo] * paso + celda, weights=aporte,
                            minlength=alto * total)
    # suma acumulada por filas = resta de dos filas de la integral 2D (más rápida que np.cumsum)
    integral = cv2.integral(acumulado.reshape(alto, total), sdepth=cv2.CV_64F)
    cobertura = cv2.convertScaleAbs(cv2.subtract(integral[1:, 1:], integral[:-1, 1:]), alpha=255.0)
    return [np.ascontiguousarray(cobertura[:, g * paso:g * paso + ancho]) for g in range(len(grupos))]


def _cobertura_linea(poli: np.ndarray, ancho: int, alto: int, grosor: float) -> np.ndarray:
    """uint8 (alto, ancho): el contorno cerrado de ``poli`` dibujado con ``grosor`` (uniones
    redondas), con ``cv2.polylines`` sobremuestreado ×4 (×2 si es grande). Es el respaldo del
    trazo cuando no se puede desplazar el contorno (trazo más grueso que la forma)."""
    ss = 4 if ancho * alto <= 1_000_000 else 2
    fijo = 1 << _SUBPIXEL
    q = np.round((np.asarray(poli, np.float64) * ss - 0.5) * fijo).astype(np.int64)
    ws = ancho * ss
    filas = max(1, _PIXELES_FRANJA // (ws * ss))
    out = np.empty((alto, ancho), np.uint8)
    for y0 in range(0, alto, filas):
        h = min(filas, alto - y0)
        m = np.zeros((h * ss, ws), np.uint8)
        qf = (q - np.array([0, y0 * ss * fijo])).astype(np.int32)
        cv2.polylines(m, [qf], True, 255, max(1, int(round(grosor * ss))), cv2.LINE_8, _SUBPIXEL)
        out[y0:y0 + h] = cv2.resize(m, (ancho, h), interpolation=cv2.INTER_AREA)
    return out


def _medio_lado(*polis, extra: float = 0.0) -> tuple[float, float]:
    mx = my = 0.0
    for poli in polis:
        if poli is not None and len(poli):
            mx = max(mx, float(np.abs(poli[:, 0]).max()))
            my = max(my, float(np.abs(poli[:, 1]).max()))
    return mx + extra, my + extra


def renderizar_forma(p: ParamsForma, escala: float = 1.0) -> np.ndarray:
    """RGBA uint8 de la forma, centrada, con el margen justo para el trazo (ver el módulo).

    ``escala``: píxeles del render por píxel del documento (> 0). ``ValueError`` si los
    parámetros no valen o el render pasaría ``LADO_MAX_RENDER`` por lado o ``AREA_MAX_RENDER``.
    """
    if not isinstance(p, ParamsForma):
        raise ValueError(f"Se esperaba ParamsForma (llegó {p!r}).")
    escala = _positivo(escala, "escala")
    forma, afuera, adentro, linea = _contornos(p, escala)
    mx, my = _medio_lado(forma, afuera, extra=(linea / 2.0 if linea else 0.0))
    ancho = max(2, 2 * int(math.ceil(mx - 1e-6)))
    alto = max(2, 2 * int(math.ceil(my - 1e-6)))
    if ancho > LADO_MAX_RENDER or alto > LADO_MAX_RENDER or ancho * alto > AREA_MAX_RENDER:
        raise ValueError(f"La forma a escala {escala:g} es demasiado grande ({ancho}×{alto}).")
    cx, cy = ancho / 2.0, alto / 2.0
    centro = np.array([cx, cy])

    relleno = p.relleno
    hay_relleno = relleno.tipo != "ninguno" and max(c[3] for c in relleno.colores) > 0
    cob_relleno = _cobertura([(forma + centro, 1)], ancho, alto) if hay_relleno else None
    cob_trazo = None
    if linea:
        cob_trazo = _cobertura_linea(forma + centro, ancho, alto, linea)
    elif afuera is not None:
        partes = [(afuera + centro, 1)]
        if adentro is not None:
            partes.append((adentro + centro, -1))
        cob_trazo = _cobertura(partes, ancho, alto)

    # el color del relleno (o del trazo, si no hay relleno) va en todo el RGB
    if hay_relleno and relleno.tipo in ("lineal", "radial"):
        out = _degradado_caja(relleno, ancho, alto, cx, cy, p.ancho * escala, p.alto * escala)
        opaco = all(c[3] == 255 for c in relleno.colores)
        alfa_relleno = cob_relleno if opaco else cv2.multiply(cob_relleno, out[..., 3].copy(), scale=1 / 255)
    else:
        col = relleno.colores[0] if hay_relleno or cob_trazo is None else p.trazo
        out = np.empty((alto, ancho, 4), np.uint8)
        out[:] = col
        alfa_relleno = None
        if hay_relleno:
            alfa_relleno = _por_alfa(cob_relleno, col[3])
    if cob_trazo is None:
        out[..., 3] = alfa_relleno if alfa_relleno is not None else 0
        return out
    alfa_trazo = _por_alfa(cob_trazo, p.trazo[3])
    if alfa_relleno is None:
        out[..., 3] = alfa_trazo
        return out
    # el trazo encima del relleno ("source-over", sin premultiplicar):
    # αo = αt + αr·(1 − αt) y C = Cr + (Ct − Cr)·αt / αo, solo donde hay trazo
    out[..., 3] = cv2.add(alfa_trazo, cv2.multiply(alfa_relleno, cv2.bitwise_not(alfa_trazo), scale=1 / 255))
    donde = cv2.findNonZero(alfa_trazo)
    if donde is not None:
        donde = donde.reshape(-1, 2)          # (N, 1, 2) en OpenCV 4 y (N, 2) en OpenCV 5
        xs, ys = donde[:, 0], donde[:, 1]
        a_t = alfa_trazo[ys, xs].astype(_F) / _F(255)
        a_r = alfa_relleno[ys, xs].astype(_F) / _F(255)
        peso = (a_t / (a_t + a_r * (_F(1) - a_t)))[:, None]
        c_r = out[ys, xs, :3].astype(_F)
        rgb = c_r + (np.array(p.trazo[:3], _F)[None, :] - c_r) * peso
        out[ys, xs, :3] = np.clip(np.rint(rgb), 0, 255).astype(np.uint8)
    return out


def _por_alfa(cobertura: np.ndarray, alfa: int) -> np.ndarray:
    """cobertura · alfa / 255, redondeado (uint8)."""
    return cobertura if alfa == 255 else cv2.convertScaleAbs(cobertura, alpha=alfa / 255.0)


__all__ = ["AREA_MAX_RENDER", "Color", "LADO_MAX_RENDER", "LIMITE_INGLETE", "ParamsForma", "Relleno",
           "TIPOS_FORMA", "TIPOS_RELLENO", "color_rgba", "renderizar_forma", "renderizar_relleno"]
