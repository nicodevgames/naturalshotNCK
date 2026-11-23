"""Modos de fusión de capas (los de Photoshop), con las fórmulas de W3C Compositing
and Blending Level 1. No depende de la interfaz gráfica.

Espacio de trabajo
------------------
float32 de 0 a 1, en el espacio de la imagen sin linealizar (sRGB "tal cual"), como hace
Photoshop por defecto. RGB de forma (h, w, 3) y alfa de forma (h, w). El RGB va **sin
premultiplicar** (el color "verdadero" del píxel, aunque sea semitransparente).

Mezcla y composición (W3C §5.8 y §10)
-------------------------------------
Con Cb y αb el fondo, Cs y αs la capa (αs ya multiplicado por la opacidad y la máscara) y
B(Cb, Cs) la función de mezcla del modo:

    Cs' = (1 - αb)·Cs + αb·B(Cb, Cs)          (donde no hay fondo, la capa va tal cual)
    co  = αs·Cs' + (1 - αs)·αb·Cb             (source-over, premultiplicado)
    αo  = αs + αb·(1 - αs)
    C   = co / αo                              (0 donde αo = 0)

Con el fondo opaco (αb = 1), que es el caso de casi todo el documento, queda
``C = Cb + αs·(B - Cb)`` y αo = 1, sin divisiones (``mezclar`` con ``fondo_alfa=None``).

Modos separables (canal por canal)
----------------------------------
normal Cs · multiplicar Cb·Cs · trama (pantalla) Cb + Cs - Cb·Cs · superponer =
luz fuerte con los argumentos al revés · luz fuerte: multiplicar(Cb, 2·Cs) si Cs <= 0,5 y
pantalla(Cb, 2·Cs - 1) si no · luz suave (la de W3C, con D(Cb)) · oscurecer min ·
aclarar max · sobreexponer color min(1, Cb / (1 - Cs)) (0 si Cb = 0, 1 si Cs = 1) ·
subexponer color 1 - min(1, (1 - Cb) / Cs) (1 si Cb = 1, 0 si Cs = 0) · diferencia
|Cb - Cs| · exclusión Cb + Cs - 2·Cb·Cs.

Modos no separables (con Lum, ClipColor, SetLum, Sat y SetSat de la especificación)
-----------------------------------------------------------------------------------
tono SetLum(SetSat(Cs, Sat(Cb)), Lum(Cb)) · saturación SetLum(SetSat(Cb, Sat(Cs)), Lum(Cb)) ·
color SetLum(Cs, Lum(Cb)) · luminosidad SetLum(Cb, Lum(Cs)). Lum usa 0,3 / 0,59 / 0,11.

Todo vectorizado con numpy, sin bucles por píxel. Por dentro (``mezcla`` y ``mezclar``) el
color va en **planos** (3, h, w): así un alfa (h, w) se aplica a los tres canales sin el
costo de difundirlo sobre un último eje de 3 (en numpy, eso es unas 3 veces más lento).
``fusionar`` recibe y devuelve (h, w, 3), como el resto del programa.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

# Clave → nombre en la interfaz (los de Photoshop en español), en el orden del menú.
MODOS_FUSION: dict[str, str] = {
    "normal": "Normal",
    "multiplicar": "Multiplicar",
    "pantalla": "Trama",
    "superponer": "Superponer",
    "luz_suave": "Luz suave",
    "luz_fuerte": "Luz fuerte",
    "oscurecer": "Oscurecer",
    "aclarar": "Aclarar",
    "sobreexponer": "Sobreexponer color",
    "subexponer": "Subexponer color",
    "diferencia": "Diferencia",
    "exclusion": "Exclusión",
    "tono": "Tono",
    "saturacion": "Saturación",
    "color": "Color",
    "luminosidad": "Luminosidad",
}

MODOS_NO_SEPARABLES = ("tono", "saturacion", "color", "luminosidad")

_F = np.float32


def validar_modo(modo: str) -> str:
    """El modo tal cual, o ``ValueError`` si no es uno de ``MODOS_FUSION``."""
    if modo not in MODOS_FUSION:
        raise ValueError(f"Modo de fusión desconocido: {modo!r}.")
    return modo


def _flotante(x, ndim: int, nombre: str) -> np.ndarray:
    """float32 de 0 a 1: un uint8 se divide por 255 y un uint16 por 65535; un float se recorta a
    [0, 1] (en una copia). Otros tipos (enteros con signo, booleanos…): ``ValueError``."""
    x = np.asarray(x)
    if x.ndim != ndim:
        raise ValueError(f"{nombre}: se esperaba un arreglo de {ndim} dimensiones (llegó {x.shape}).")
    if x.dtype == np.uint8:
        return x.astype(_F) / _F(255.0)
    if x.dtype == np.uint16:
        return x.astype(_F) / _F(65535.0)
    if not np.issubdtype(x.dtype, np.floating):
        raise ValueError(f"{nombre}: se esperaba float de 0 a 1, uint8 o uint16 (llegó {x.dtype}).")
    return np.clip(x.astype(_F), _F(0.0), _F(1.0))


# ---------------------------------------------------------------------------
# Funciones de mezcla B(Cb, Cs)
# ---------------------------------------------------------------------------

def _pantalla(cb: np.ndarray, cs: np.ndarray) -> np.ndarray:
    return cb + cs - cb * cs


def _luz_fuerte(cb: np.ndarray, cs: np.ndarray) -> np.ndarray:
    doble = cs * _F(2.0)
    return np.where(cs <= _F(0.5), cb * doble, _pantalla(cb, doble - _F(1.0)))


def _luz_suave(cb: np.ndarray, cs: np.ndarray) -> np.ndarray:
    d = np.where(cb <= _F(0.25), ((_F(16.0) * cb - _F(12.0)) * cb + _F(4.0)) * cb, np.sqrt(np.maximum(cb, _F(0.0))))
    oscura = cb - (_F(1.0) - _F(2.0) * cs) * cb * (_F(1.0) - cb)
    clara = cb + (_F(2.0) * cs - _F(1.0)) * (d - cb)
    return np.where(cs <= _F(0.5), oscura, clara)


def _sobreexponer(cb: np.ndarray, cs: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.minimum(_F(1.0), cb / (_F(1.0) - cs))
    r = np.where(cs >= _F(1.0), _F(1.0), r)
    return np.where(cb <= _F(0.0), _F(0.0), r)


def _subexponer(cb: np.ndarray, cs: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        r = _F(1.0) - np.minimum(_F(1.0), (_F(1.0) - cb) / cs)
    r = np.where(cs <= _F(0.0), _F(0.0), r)
    return np.where(cb >= _F(1.0), _F(1.0), r)


def _lum(c: np.ndarray) -> np.ndarray:
    """Luminosidad (h, w) de un color en planos (3, h, w)."""
    return (c[0] * _F(0.3) + c[1] * _F(0.59)) + c[2] * _F(0.11)


def _min3(c: np.ndarray) -> np.ndarray:
    return np.minimum(np.minimum(c[0], c[1]), c[2])


def _max3(c: np.ndarray) -> np.ndarray:
    return np.maximum(np.maximum(c[0], c[1]), c[2])


def _clip_color(c: np.ndarray) -> np.ndarray:
    l = _lum(c)
    n = _min3(c)
    x = _max3(c)
    with np.errstate(divide="ignore", invalid="ignore"):
        c = np.where(n < 0, l + (c - l) * l / (l - n), c)
        c = np.where(x > 1, l + (c - l) * (_F(1.0) - l) / (x - l), c)
    return c


def _set_lum(c: np.ndarray, l: np.ndarray) -> np.ndarray:
    return _clip_color(c + (l - _lum(c)))


def _sat(c: np.ndarray) -> np.ndarray:
    return _max3(c) - _min3(c)


def _set_sat(c: np.ndarray, s: np.ndarray) -> np.ndarray:
    """El mínimo va a 0, el máximo a ``s`` y el del medio en proporción (todo 0 si es gris)."""
    mn = _min3(c)
    rango = _max3(c) - mn
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(rango > 0, (c - mn) * s / rango, _F(0.0))


def mezcla(modo: str, cb: np.ndarray, cs: np.ndarray) -> np.ndarray:
    """B(Cb, Cs): el color de la mezcla, sin alfa ni opacidad. float32 en planos (3, h, w)."""
    if modo == "normal":
        return cs
    if modo == "multiplicar":
        return cb * cs
    if modo == "pantalla":
        return _pantalla(cb, cs)
    if modo == "superponer":
        return _luz_fuerte(cs, cb)
    if modo == "luz_suave":
        return _luz_suave(cb, cs)
    if modo == "luz_fuerte":
        return _luz_fuerte(cb, cs)
    if modo == "oscurecer":
        return np.minimum(cb, cs)
    if modo == "aclarar":
        return np.maximum(cb, cs)
    if modo == "sobreexponer":
        return _sobreexponer(cb, cs)
    if modo == "subexponer":
        return _subexponer(cb, cs)
    if modo == "diferencia":
        return np.abs(cb - cs)
    if modo == "exclusion":
        return cb + cs - _F(2.0) * cb * cs
    if modo == "tono":
        return _set_lum(_set_sat(cs, _sat(cb)), _lum(cb))
    if modo == "saturacion":
        return _set_lum(_set_sat(cb, _sat(cs)), _lum(cb))
    if modo == "color":
        return _set_lum(cs, _lum(cb))
    if modo == "luminosidad":
        return _set_lum(cb, _lum(cs))
    raise ValueError(f"Modo de fusión desconocido: {modo!r}.")


# ---------------------------------------------------------------------------
# Composición
# ---------------------------------------------------------------------------

def mezclar(fondo_rgb: np.ndarray, fondo_alfa: Optional[np.ndarray], capa_rgb: np.ndarray,
            alfa_capa: np.ndarray, modo: str) -> tuple[np.ndarray, Optional[np.ndarray]]:
    """El núcleo de ``fusionar``, en float32 y **en planos**: rgb (3, h, w), alfas (h, w).

    ``alfa_capa`` es el alfa efectivo de la capa (alfa × opacidad × máscara).
    ``fondo_alfa=None`` quiere decir fondo opaco: entonces el resultado también lo es y se
    devuelve ``(rgb, None)``, sin divisiones. No modifica las entradas.
    """
    b = mezcla(modo, fondo_rgb, capa_rgb)
    a_s = alfa_capa
    if fondo_alfa is None:
        return fondo_rgb + a_s * (b - fondo_rgb), None
    a_b = fondo_alfa
    cs2 = capa_rgb + a_b * (b - capa_rgb) if modo != "normal" else capa_rgb
    co = a_s * cs2 + ((_F(1.0) - a_s) * a_b) * fondo_rgb
    ao = alfa_capa + fondo_alfa * (_F(1.0) - alfa_capa)
    rgb = np.zeros_like(co)
    np.divide(co, ao, out=rgb, where=np.broadcast_to(ao > 0, co.shape))
    return rgb, ao.astype(_F, copy=False)


def fusionar(fondo_rgb, fondo_alfa, capa_rgb, capa_alfa, modo: str = "normal", opacidad: float = 1.0,
             mascara=None) -> tuple[np.ndarray, np.ndarray]:
    """Pone la capa sobre el fondo con el modo de fusión, la opacidad y la máscara.

    float32 de 0 a 1 (se recorta a ese rango; también se aceptan uint8 y uint16, que se dividen
    por 255 y por 65535; otros tipos dan ``ValueError``); rgb (h, w, 3) sin
    premultiplicar, alfa (h, w). ``fondo_alfa`` o ``capa_alfa`` en None = opaco.
    ``mascara`` (h, w) multiplica el alfa de la capa (blanco = se ve, negro = no).
    Devuelve ``(rgb, alfa)`` en float32; donde el resultado es transparente del todo, el RGB es 0.
    Fórmulas W3C Compositing (separables y no separables), con alfa "source-over".
    ``ValueError`` si el modo no existe o las formas no coinciden. No modifica las entradas.
    """
    validar_modo(modo)
    cb = _flotante(fondo_rgb, 3, "fondo_rgb")
    cs = _flotante(capa_rgb, 3, "capa_rgb")
    if cb.shape != cs.shape or cb.shape[-1] != 3:
        raise ValueError(f"El fondo {cb.shape} y la capa {cs.shape} tienen que ser RGB del mismo tamaño.")
    forma = cb.shape[:2]
    ab = None if fondo_alfa is None else _flotante(fondo_alfa, 2, "fondo_alfa")
    alfa = np.full(forma, max(0.0, min(1.0, float(opacidad))), _F)
    for extra, nombre in ((ab, "fondo_alfa"), (capa_alfa, "capa_alfa"), (mascara, "mascara")):
        if extra is not None and np.shape(extra) != forma:
            raise ValueError(f"{nombre} tiene que ser de {forma} (llegó {np.shape(extra)}).")
    if capa_alfa is not None:
        alfa *= _flotante(capa_alfa, 2, "capa_alfa")
    if mascara is not None:
        alfa *= _flotante(mascara, 2, "mascara")
    planos = lambda x: np.ascontiguousarray(np.moveaxis(x, -1, 0))   # noqa: E731
    rgb, ao = mezclar(planos(cb), ab, planos(cs), alfa, modo)
    if ao is None:
        ao = np.ones(forma, _F)
    return np.ascontiguousarray(np.moveaxis(rgb, 0, -1), dtype=_F), ao


__all__ = ["MODOS_FUSION", "MODOS_NO_SEPARABLES", "fusionar", "mezcla", "mezclar", "validar_modo"]
