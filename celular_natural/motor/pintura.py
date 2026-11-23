"""Pintura sobre capas de píxeles: pincel, borrador, bote, degradado y cuentagotas. Sin Qt.

Todo trabaja sobre RGBA uint8 **sin premultiplicar** (el de las capas) y devuelve una copia
nueva: no toca la entrada. Las coordenadas son las de la capa, continuas: el píxel (i, j)
ocupa [i, i + 1) × [j, j + 1), así que su centro es (i + 0,5, j + 0,5).

Pincel (``trazo``)
------------------
Los puntos se unen con estampas redondas cada 0,15 × ``tamano`` (como mucho). La estampa
tiene radio ``tamano`` / 2 y su alfa cae con la distancia al centro según la ``dureza``:
lleno hasta (radio − caída) y, de ahí al borde, una curva suave (smoothstep), con
caída = max(radio · (1 − dureza), 1 px). Con dureza 1 el borde es un antialias de 1 px y con
dureza 0 el pincel es suave del centro al borde.

Dentro de un trazo, el alfa es el **máximo** de las estampas (no se acumula: pasar dos veces
por el mismo lugar en el mismo trazo no oscurece de más, como en Photoshop). Ese alfa, por la
``opacidad`` y por el alfa del color, se aplica una sola vez:

* pintar: el color va encima ("source-over", sin premultiplicar);
* ``borrar=True``: el alfa de la capa se multiplica por (1 − alfa del trazo); el RGB queda.

Para que sea rápido, la cuenta se hace solo en la caja del trazo y la mezcla, solo en los
píxeles que toca.

Bote
----
Rellena los píxeles parecidos al del clic: cada canal a ``tolerancia`` o menos (de 0 a 255,
como Photoshop). Se compara en RGBA premultiplicado (dos píxeles transparentes son iguales,
tengan el RGB que tengan) o, con ``muestra``, en el RGB de la composición. ``contiguo``:
solo la zona unida al clic (por los 4 vecinos, con ``cv2.floodFill``); si no, todos los
parecidos de la capa. El color va encima, como el pincel, sin suavizar el borde.

Degradado
---------
``degradado`` arma un RGBA nuevo de ``ancho`` × ``alto`` con los colores y paradas de un
``Relleno`` (su tipo y su ángulo no cuentan): lineal de ``p0`` a ``p1`` (la proyección sobre
ese segmento) o radial con centro en ``p0`` y radio |p1 − p0|. Antes de ``p0`` va el primer
color y después de ``p1``, el último, exactos. Se interpola premultiplicado (ver ``formas``).
Para pintarlo encima de una capa, se funde como cualquier capa.
"""

from __future__ import annotations

import math
import numbers
from typing import Optional

import cv2
import numpy as np

from .formas import Relleno, _degradado, color_rgba

SEPARACION = 0.15            # entre estampas, por el tamaño del pincel
SEPARACION_MIN = 0.5         # px

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


def _unidad(valor, nombre: str) -> float:
    return min(1.0, max(0.0, _real(valor, nombre)))


def _capa(rgba) -> np.ndarray:
    im = np.asarray(rgba)
    if im.dtype != np.uint8 or im.ndim != 3 or im.shape[2] != 4 or im.shape[0] < 1 or im.shape[1] < 1:
        raise ValueError(f"Se esperaba una imagen RGBA uint8 (alto, ancho, 4) (llegó {im.dtype} {im.shape}).")
    return im


def _puntos(puntos) -> np.ndarray:
    try:
        p = np.asarray(puntos, np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError("puntos tiene que ser una lista de (x, y).") from error
    if p.size == 0:
        return p.reshape(0, 2)
    if p.ndim != 2 or p.shape[1] != 2:
        raise ValueError(f"puntos tiene que ser una lista de (x, y) (llegó la forma {p.shape}).")
    if not np.isfinite(p).all():
        raise ValueError("Los puntos tienen que ser números finitos.")
    return p


def _encima(destino: np.ndarray, ys: np.ndarray, xs: np.ndarray, alfa: np.ndarray, color) -> None:
    """Pone ``color`` (RGB) con ``alfa`` (float 0..1, uno por píxel) encima de esos píxeles de
    ``destino`` (RGBA uint8, sin premultiplicar), "source-over"."""
    a_s = alfa.astype(_F)
    a_d = destino[ys, xs, 3].astype(_F) / _F(255)
    a_o = a_s + a_d * (_F(1) - a_s)
    # C = Cd + (Cs − Cd)·αs/αo (donde αo = 0, queda el color del trazo)
    with np.errstate(divide="ignore", invalid="ignore"):
        peso = np.where(a_o > 0, a_s / a_o, _F(1))[:, None]
    c_d = destino[ys, xs, :3].astype(_F)
    rgb = c_d + (np.array(color[:3], _F)[None, :] - c_d) * peso
    destino[ys, xs, :3] = np.clip(np.rint(rgb), 0, 255).astype(np.uint8)
    destino[ys, xs, 3] = np.clip(np.rint(a_o * _F(255)), 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# Pincel y borrador
# ---------------------------------------------------------------------------

def _centros(p: np.ndarray, separacion: float) -> np.ndarray:
    """Los puntos más los intermedios, cada ``separacion`` px como mucho."""
    if len(p) < 2:
        return p
    tramos = np.diff(p, axis=0)
    largo = np.hypot(tramos[:, 0], tramos[:, 1])
    pasos = np.maximum(1, np.ceil(largo / separacion)).astype(np.int64)
    tramo = np.repeat(np.arange(len(tramos)), pasos)
    inicio = np.cumsum(pasos) - pasos
    t = (np.arange(int(pasos.sum())) - inicio[tramo] + 1) / pasos[tramo]
    medios = p[tramo] + tramos[tramo] * t[:, None]
    return np.concatenate([p[:1], medios])


def mascara_trazo(ancho: int, alto: int, puntos, tamano: float, dureza: float = 0.8):
    """La cobertura de un trazo (máximo de las estampas), solo en su caja.

    Devuelve ``(x0, y0, mascara)``: ``mascara`` es float32 de 0 a 1 y su esquina va en
    (x0, y0) de la capa; ``None`` si el trazo no toca la capa. Sirve para mostrar el trazo
    mientras se arrastra (la interfaz lo dibuja en una superposición) y para ``trazo``.
    """
    tam = _real(tamano, "tamano")
    if tam <= 0:
        raise ValueError(f"El tamaño del pincel tiene que ser mayor que 0 (llegó {tamano!r}).")
    radio = max(tam, 1.0) / 2.0
    dureza = _unidad(dureza, "dureza")
    p = _puntos(puntos)
    if len(p) == 0:
        return None
    centros = _centros(p, max(SEPARACION * 2.0 * radio, SEPARACION_MIN))
    alcance = radio + 0.5
    x0 = max(0, int(math.floor(centros[:, 0].min() - alcance)))
    y0 = max(0, int(math.floor(centros[:, 1].min() - alcance)))
    x1 = min(ancho, int(math.ceil(centros[:, 0].max() + alcance)))
    y1 = min(alto, int(math.ceil(centros[:, 1].max() + alcance)))
    if x1 <= x0 or y1 <= y0:
        return None
    # solo las estampas que tocan la capa
    dentro = ((centros[:, 0] + alcance > 0) & (centros[:, 0] - alcance < ancho)
              & (centros[:, 1] + alcance > 0) & (centros[:, 1] - alcance < alto))
    centros = centros[dentro]
    mascara = np.zeros((y1 - y0, x1 - x0), _F)
    caida = max(radio * (1.0 - dureza), 1.0)
    # perfil de la estampa en función de la distancia: una tabla fina (1/64 px)
    fino = 64.0
    d = np.arange(int(math.ceil(alcance * fino)) + 2, dtype=np.float64) / fino
    u = np.clip((radio + 0.5 - d) / caida, 0.0, 1.0)
    perfil = (u * u * (3.0 - 2.0 * u)).astype(_F)
    n = len(perfil) - 1
    for cx, cy in centros:
        ix0 = max(int(math.floor(cx - alcance)), x0)
        ix1 = min(int(math.ceil(cx + alcance)), x1)
        iy0 = max(int(math.floor(cy - alcance)), y0)
        iy1 = min(int(math.ceil(cy + alcance)), y1)
        if ix1 <= ix0 or iy1 <= iy0:
            continue
        dx = (np.arange(ix0, ix1, dtype=_F) + _F(0.5 - cx)) ** 2
        dy = (np.arange(iy0, iy1, dtype=_F) + _F(0.5 - cy)) ** 2
        dist = np.sqrt(dy[:, None] + dx[None, :]) * _F(fino)
        indice = np.minimum(dist, _F(n)).astype(np.int32)
        zona = mascara[iy0 - y0:iy1 - y0, ix0 - x0:ix1 - x0]
        np.maximum(zona, perfil[indice], out=zona)
    return x0, y0, mascara


def trazo(rgba, puntos, tamano, dureza=0.8, opacidad=1.0, color=(0, 0, 0, 255), borrar=False) -> np.ndarray:
    """Un trazo de pincel (o de borrador, con ``borrar=True``) por ``puntos`` (x, y), en una
    copia nueva de ``rgba`` (ver el módulo). ``tamano``: diámetro en px (> 0); ``dureza`` y
    ``opacidad`` de 0 a 1; ``color`` RGBA (el borrador no lo usa)."""
    im = _capa(rgba)
    out = im.copy()
    opacidad = _unidad(opacidad, "opacidad")
    col = color_rgba(color, "color")
    if not isinstance(borrar, (bool, np.bool_)):
        raise ValueError(f"borrar tiene que ser verdadero o falso (llegó {borrar!r}).")
    resultado = mascara_trazo(im.shape[1], im.shape[0], puntos, tamano, dureza)
    fuerza = opacidad * (1.0 if borrar else col[3] / 255.0)
    if resultado is None or fuerza <= 0:
        return out
    x0, y0, mascara = resultado
    ys, xs = np.nonzero(mascara)
    if not len(ys):
        return out
    alfa = mascara[ys, xs] * _F(fuerza)
    ys, xs = ys + y0, xs + x0
    if borrar:
        quedan = out[ys, xs, 3].astype(_F) * (_F(1) - alfa)
        out[ys, xs, 3] = np.clip(np.rint(quedan), 0, 255).astype(np.uint8)
    else:
        _encima(out, ys, xs, alfa, col)
    return out


# ---------------------------------------------------------------------------
# Bote
# ---------------------------------------------------------------------------

def _premultiplicada(im: np.ndarray) -> np.ndarray:
    """RGBA uint8 con el RGB multiplicado por el alfa (redondeado)."""
    alfa = np.ascontiguousarray(im[..., 3])
    rgb = cv2.multiply(np.ascontiguousarray(im[..., :3]), cv2.merge([alfa, alfa, alfa]), scale=1 / 255)
    return np.dstack([rgb, alfa])


def zona_bote(rgba, x, y, tolerancia=32, contiguo=True, muestra=None) -> Optional[np.ndarray]:
    """La máscara (bool, alto × ancho) de lo que llenaría el bote; None si (x, y) cae afuera."""
    im = _capa(rgba)
    alto, ancho = im.shape[:2]
    fx, fy = _real(x, "x"), _real(y, "y")
    ix, iy = int(math.floor(fx)), int(math.floor(fy))
    if not (0 <= ix < ancho and 0 <= iy < alto):
        return None
    if muestra is not None:
        ref = np.asarray(muestra)
        if ref.dtype != np.uint8 or ref.ndim != 3 or ref.shape[:2] != (alto, ancho) or ref.shape[2] not in (3, 4):
            raise ValueError(f"La muestra tiene que ser RGB uint8 de {ancho}×{alto} (llegó {ref.dtype} {ref.shape}).")
        ref = np.ascontiguousarray(ref[..., :3])
    else:
        ref = _premultiplicada(im)
    semilla = ref[iy, ix].astype(np.float64)
    canales = cv2.split(cv2.absdiff(ref, np.broadcast_to(semilla.astype(np.uint8), ref.shape).copy()))
    diferencia = canales[0]
    for c in canales[1:]:
        diferencia = cv2.max(diferencia, c)
    tol = int(round(min(255.0, max(0.0, _real(tolerancia, "tolerancia")))))
    if not contiguo:
        return diferencia <= tol
    marca = np.zeros((alto + 2, ancho + 2), np.uint8)
    flags = 4 | cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE | (1 << 8)
    cv2.floodFill(diferencia, marca, (ix, iy), 0, 0, tol, flags)
    return marca[1:-1, 1:-1].astype(bool)


def bote(rgba, x, y, color, tolerancia=32, contiguo=True, muestra=None) -> np.ndarray:
    """Bote de pintura en (x, y), en una copia nueva (ver el módulo). ``muestra``: RGB (o RGBA)
    uint8 de la composición, del tamaño de la capa, para elegir la zona por lo que se ve."""
    im = _capa(rgba)
    col = color_rgba(color, "color")
    if not isinstance(contiguo, (bool, np.bool_)):
        raise ValueError(f"contiguo tiene que ser verdadero o falso (llegó {contiguo!r}).")
    zona = zona_bote(im, x, y, tolerancia, contiguo, muestra)
    out = im.copy()
    if zona is None or col[3] == 0:
        return out
    if col[3] == 255:
        out[zona] = col
        return out
    ys, xs = np.nonzero(zona)
    _encima(out, ys, xs, np.full(len(ys), col[3] / 255.0, _F), col)
    return out


# ---------------------------------------------------------------------------
# Degradado y cuentagotas
# ---------------------------------------------------------------------------

def degradado(ancho, alto, p0, p1, relleno: Relleno, radial=False) -> np.ndarray:
    """RGBA uint8 (alto, ancho, 4) del degradado de ``p0`` a ``p1`` (ver el módulo)."""
    for valor, nombre in ((ancho, "ancho"), (alto, "alto")):
        if isinstance(valor, (bool, np.bool_)) or not isinstance(valor, (numbers.Integral, np.integer)) or valor < 1:
            raise ValueError(f"{nombre} tiene que ser un entero mayor que 0 (llegó {valor!r}).")
    if isinstance(relleno, dict):
        relleno = Relleno.desde_dict(relleno)
    if not isinstance(relleno, Relleno):
        raise ValueError(f"Se esperaba un Relleno (llegó {relleno!r}).")
    puntos = []
    for punto, nombre in ((p0, "p0"), (p1, "p1")):
        if isinstance(punto, (str, bytes)) or len(punto) != 2:
            raise ValueError(f"{nombre} tiene que ser (x, y) (llegó {punto!r}).")
        puntos.append((_real(punto[0], nombre), _real(punto[1], nombre)))
    return _degradado(int(ancho), int(alto), puntos[0], puntos[1], relleno, bool(radial))


def cuentagotas(rgb, x, y, radio=0) -> tuple[int, int, int]:
    """El color (R, G, B) en (x, y): el del píxel o, con ``radio`` r, el promedio del cuadrado
    de (2r + 1) × (2r + 1) alrededor (recortado a la imagen). Un punto afuera toma el borde.
    Acepta RGB o RGBA uint8 (el alfa no cuenta)."""
    im = np.asarray(rgb)
    if im.dtype != np.uint8 or im.ndim != 3 or im.shape[2] not in (3, 4) or im.shape[0] < 1 or im.shape[1] < 1:
        raise ValueError(f"Se esperaba una imagen RGB o RGBA uint8 (llegó {im.dtype} {im.shape}).")
    alto, ancho = im.shape[:2]
    ix = min(ancho - 1, max(0, int(math.floor(_real(x, "x")))))
    iy = min(alto - 1, max(0, int(math.floor(_real(y, "y")))))
    r = max(0, int(_real(radio, "radio")))
    zona = im[max(0, iy - r):iy + r + 1, max(0, ix - r):ix + r + 1, :3]
    media = zona.reshape(-1, 3).astype(np.float64).mean(axis=0)
    return tuple(int(v) for v in np.rint(media))


__all__ = ["SEPARACION", "bote", "cuentagotas", "degradado", "mascara_trazo", "trazo", "zona_bote"]
