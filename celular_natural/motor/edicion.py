"""Edición previa al filtro: geometría, conversión de zonas y borrado de objetos.

Orden de la foto que entra al filtro (siempre el mismo):

    original → geometría → montaje → borrar objetos → recorte → fondo → filtro

* **Geometría** (``geometria.py``): girar de a 90°, voltear y enderezar. El
  resultado es la **foto base**.
* **Montaje**: la otra foto se gira igual que la base antes de alinearla.
* **Borrar objetos**: cada ``ZonaBorrado`` se rellena (``borrado.rellenar``) o
  se clona desde otra parte (``borrado.clonar``), en orden, sobre la base
  completa y a resolución completa (la vista previa es una reducción de eso:
  coincide con la exportación).
* El **recorte**, el **fondo** y las zonas de las capas trabajan sobre la base.

Estrategia de coordenadas ("lo que ves")
----------------------------------------
Todo lo que el usuario marca (zonas de capas, montaje, fondo, borrado, trazos
del pincel y el recorte) se guarda normalizado (0..1) respecto de la foto BASE
completa, sin recortar: la que ve en pantalla. Por eso el resto del motor
(``mascara_zona``, desenfoque, montaje, ``procesar_pila``) no necesita saber
nada de la geometría.

Cuando cambia la geometría, ``convertir_zona``, ``convertir_recorte`` y
``convertir_borrado`` llevan cada cosa del marco viejo al nuevo con la misma
matriz que usa ``aplicar_geometria`` (``matriz_cambio``), así una zona sigue
sobre el mismo objeto:

* giros de 90° y volteos: exactos; rectángulos y elipses siguen siéndolo;
* enderezar: rectángulos y elipses pasan a polígono (quedarían torcidos);
* trazos del pincel: se mueven sus puntos y el radio se reescala (es relativo
  al lado largo, que cambia un poco al enderezar);
* máscaras raster (cielo, piel, contorno): solo se compone su matriz; la
  máscara no se vuelve a muestrear, así ir y volver no la degrada;
* recorte: con 90° y volteos se transforma exacto; al enderezar conserva su
  centro (sobre el mismo objeto) y su tamaño en píxeles, y se ajusta para no
  salirse de la foto.

Cada paso del historial guarda la geometría junto con las zonas ya
convertidas, así deshacer y rehacer no tienen que convertir nada.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, replace
from typing import Callable, Optional, Sequence

import numpy as np

from .borrado import clonar, rellenar
from .geometria import Geometria, aplicar_geometria, matriz_geometria, tamano_resultante
from .procesado import Cancelado
from .zonas import Recorte, Zona, mascara_zona, transformar_zona

MODOS_BORRADO = ("rellenar", "clonar")


# ---------------------------------------------------------------------------
# Geometría: de un marco al otro
# ---------------------------------------------------------------------------

def matriz_cambio(antes: Geometria, despues: Geometria, w: int, h: int) -> np.ndarray:
    """Matriz 3x3 que lleva coordenadas normalizadas de la base con la geometría
    ``antes`` a las de la base con ``despues`` (``w`` x ``h``: la foto ORIGINAL)."""
    a1 = matriz_geometria(antes, w, h)
    a2 = matriz_geometria(despues, w, h)
    w1, h1 = tamano_resultante(w, h, antes)
    w2, h2 = tamano_resultante(w, h, despues)
    return np.diag([1.0 / w2, 1.0 / h2, 1.0]) @ a2 @ np.linalg.inv(a1) @ np.diag([w1, h1, 1.0])


def _datos_cambio(antes: Geometria, despues: Geometria, w: int, h: int):
    m = matriz_cambio(antes, despues, w, h)
    w1, h1 = tamano_resultante(w, h, antes)
    w2, h2 = tamano_resultante(w, h, despues)
    return m, max(w1, h1) / max(w2, h2), w2 / h2, (w1, h1), (w2, h2)


def convertir_zona(zona: Optional[Zona], antes: Geometria, despues: Geometria, w: int, h: int) -> Optional[Zona]:
    """La zona marcada con la geometría ``antes``, llevada a la base con ``despues``."""
    if zona is None or antes == despues:
        return zona
    m, factor, aspecto, _t1, _t2 = _datos_cambio(antes, despues, w, h)
    return transformar_zona(zona, m, factor, aspecto)


def convertir_recorte(recorte: Optional[Recorte], antes: Geometria, despues: Geometria,
                      w: int, h: int) -> Optional[Recorte]:
    """El recorte llevado a la base con la geometría nueva (None = sin recorte)."""
    if recorte is None or antes == despues:
        return recorte
    m, _factor, _aspecto, (w1, h1), (w2, h2) = _datos_cambio(antes, despues, w, h)
    r = recorte.normalizado()
    alineada = ((abs(m[0, 1]) < 1e-9 and abs(m[1, 0]) < 1e-9)
                or (abs(m[0, 0]) < 1e-9 and abs(m[1, 1]) < 1e-9))
    if alineada:
        esquinas = np.array([[r.x0, r.y0, 1.0], [r.x1, r.y1, 1.0]]) @ m.T
        nuevo = Recorte(float(esquinas[0, 0]), float(esquinas[0, 1]),
                        float(esquinas[1, 0]), float(esquinas[1, 1])).normalizado()
    else:
        # Mismo centro (el mismo objeto) y mismo tamaño en píxeles, sin salirse.
        cx, cy, _ = m @ np.array([(r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2, 1.0])
        ancho, alto = (r.x1 - r.x0) * w1 / w2, (r.y1 - r.y0) * h1 / h2
        f = min(1.0, 1.0 / max(ancho, 1e-9), 1.0 / max(alto, 1e-9))  # si no entra, se achica parejo
        ancho, alto = ancho * f, alto * f
        x0 = min(max(cx - ancho / 2, 0.0), 1.0 - ancho)
        y0 = min(max(cy - alto / 2, 0.0), 1.0 - alto)
        nuevo = Recorte(float(x0), float(y0), float(x0 + ancho), float(y0 + alto)).normalizado()
    if nuevo.es_completo() or nuevo.x1 - nuevo.x0 < 1e-4 or nuevo.y1 - nuevo.y0 < 1e-4:
        return None
    return nuevo


# ---------------------------------------------------------------------------
# Borrar objetos
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ZonaBorrado:
    """Una parte de la foto a borrar.

    ``modo``: "rellenar" (se completa con lo de alrededor) o "clonar" (se copia
    lo que hay desplazado ``(dx, dy)``, relativo al ancho y al alto de la base:
    el píxel (x, y) toma lo que hay en (x + dx, y + dy)). Un clonado sin fuente
    elegida (0, 0) todavía no hace nada.
    """
    zona: Zona
    modo: str = "rellenar"
    dx: float = 0.0
    dy: float = 0.0
    sin_costuras: bool = True

    @property
    def listo(self) -> bool:
        return self.modo != "clonar" or abs(self.dx) > 1e-9 or abs(self.dy) > 1e-9


def convertir_borrado(borrado: ZonaBorrado, antes: Geometria, despues: Geometria, w: int, h: int) -> ZonaBorrado:
    """El borrado (zona y desplazamiento del clonado) llevado a la geometría nueva."""
    if antes == despues:
        return borrado
    m = matriz_cambio(antes, despues, w, h)
    dx, dy = m[:2, :2] @ np.array([borrado.dx, borrado.dy])  # un vector: solo la parte lineal
    return replace(borrado, zona=convertir_zona(borrado.zona, antes, despues, w, h), dx=float(dx), dy=float(dy))


def aplicar_borrado(rgb: np.ndarray, borrado: ZonaBorrado, semilla: int = 0) -> np.ndarray:
    """Aplica un borrado sobre ``rgb`` (la base completa o una reducción). Devuelve una copia."""
    if not borrado.listo:
        return rgb.copy()
    h, w = rgb.shape[:2]
    mascara = mascara_zona(borrado.zona, h, w)
    if float(mascara.max()) <= 0.01:
        return rgb.copy()
    if borrado.modo == "clonar":
        return clonar(rgb, mascara, (borrado.dx * w, borrado.dy * h), sin_costuras=borrado.sin_costuras)
    return rellenar(rgb, mascara, semilla=semilla)


_CACHE: "OrderedDict[tuple, tuple[np.ndarray, np.ndarray]]" = OrderedDict()
_MAX_CACHE = 4
_CANDADO = threading.Lock()


def aplicar_borrados(rgb: np.ndarray, borrados: Sequence[ZonaBorrado], clave=None,
                     cancelado: Optional[Callable[[], bool]] = None) -> np.ndarray:
    """Aplica los borrados en orden sobre ``rgb`` (uint8 HxWx3). Sin borrados
    devuelve ``rgb`` tal cual; si no, un arreglo nuevo de solo lectura.

    Cada resultado parcial se guarda en caché con ``clave`` (lo que identifica a
    ``rgb``; sin clave, el propio arreglo): sumar un borrado nuevo solo calcula
    ese, y cambiar otros controles no recalcula nada. ``cancelado()`` permite
    abandonar entre un borrado y el siguiente.
    """
    borrados = tuple(b for b in borrados if b.listo)
    if not borrados:
        return rgb
    base = ("id", id(rgb), rgb.shape) if clave is None else ("clave", clave, rgb.shape)
    actual, desde = rgb, 0
    with _CANDADO:
        for k in range(len(borrados), 0, -1):
            previo = _CACHE.get((base, borrados[:k]))
            if previo is not None and (clave is not None or previo[0] is rgb):
                _CACHE.move_to_end((base, borrados[:k]))
                actual, desde = previo[1], k
                break
    for i in range(desde, len(borrados)):
        if cancelado is not None and cancelado():
            raise Cancelado()
        actual = aplicar_borrado(actual, borrados[i], semilla=i)
        actual.flags.writeable = False
        with _CANDADO:
            # Se guarda también la entrada: así su id no se reutiliza mientras esté en la caché.
            _CACHE[(base, borrados[:i + 1])] = (rgb, actual)
            while len(_CACHE) > _MAX_CACHE:
                _CACHE.popitem(last=False)
    return actual


# ---------------------------------------------------------------------------
# Foto base (geometría aplicada), con caché
# ---------------------------------------------------------------------------

_CACHE_BASE: "OrderedDict[tuple, tuple[np.ndarray, np.ndarray]]" = OrderedDict()
_MAX_BASE = 5  # la foto y su alfa, más las otras fotos del montaje


def con_geometria(img: np.ndarray, geo: Optional[Geometria], clave=None) -> np.ndarray:
    """``img`` con la geometría aplicada (sin geometría, la misma imagen, sin copiar).

    Se cachea por ``clave`` (o por el propio arreglo) y la geometría: mover otros
    controles no la recalcula. El resultado es de solo lectura.
    """
    if geo is None or geo.es_identidad():
        return img
    k = (("clave", clave) if clave is not None else ("id", id(img)), img.shape, geo.normalizada())
    with _CANDADO:
        previo = _CACHE_BASE.get(k)
        if previo is not None and (clave is not None or previo[0] is img):
            _CACHE_BASE.move_to_end(k)
            return previo[1]
    salida = aplicar_geometria(img, geo)
    salida.flags.writeable = False
    with _CANDADO:
        _CACHE_BASE[k] = (img, salida)
        while len(_CACHE_BASE) > _MAX_BASE:
            _CACHE_BASE.popitem(last=False)
    return salida


def limpiar_cache() -> None:
    with _CANDADO:
        _CACHE.clear()
        _CACHE_BASE.clear()
