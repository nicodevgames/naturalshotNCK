"""La **Medida** de salida: exportar la foto exacta en una medida estándar (celular, PC y redes).

Una medida es un (ancho, alto) en píxeles que va en el estado de cada foto (``estado["medida"]``;
sin medida, la clave no está y todo es como antes). Elegirla pone un **recorte** con su proporción
(el no destructivo de siempre, ``zonas.Recorte``), así se ve enseguida, y al final la foto
recortada se lleva **exacta** a esos píxeles.

**El orden respecto del filtro.** El filtro "celular natural" depende de la resolución: el ruido,
el grano, el mosaico de Bayer y la piel van por píxel (con ``escala_vista`` para la vista previa) y
la compresión simulada achica y vuelve a agrandar la foto entera. Si se redimensionara **después**
del filtro, achicar 3000 px a 1920 promediaría el grano (quedaría más fino y más suave que el de un
celular) y agrandar a 4K lo volvería manchas grandes y blandas. Por eso la foto recortada se lleva a
la medida **antes** del filtro (``llevar_a_medida``) y el filtro trabaja a la resolución de salida:
el grano y la compresión tienen el tamaño de un archivo de verdad de esa medida.

En la vista previa reducida pasa lo mismo, a escala: la foto se lleva a la medida achicada
(``tamano_trabajo``) y el filtro recibe esa escala como ``escala_vista``, igual que hoy (vista =
exportación). A escala 1 (la vista completa y exportar) sale exactamente la medida.

Achicar usa ``INTER_AREA``; agrandar, Lanczos (``INTER_LANCZOS4``). Sin Qt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .zonas import Recorte

LADO_MAX = 20000  # una medida más grande que esto no es de ninguna pantalla: se descarta


@dataclass(frozen=True)
class Medida:
    nombre: str        # "Celular vertical · historia"
    proporcion: str    # "9:16"
    ancho: int
    alto: int
    icono: str         # nombre de Lucide (assets/iconos)

    @property
    def tam(self) -> tuple[int, int]:
        return self.ancho, self.alto


# En el orden del menú (Original va aparte: es "sin medida").
MEDIDAS: tuple[Medida, ...] = (
    Medida("Celular vertical · historia", "9:16", 1080, 1920, "smartphone"),
    Medida("PC / YouTube", "16:9", 1920, 1080, "monitor"),
    Medida("PC 4K", "16:9", 3840, 2160, "tv"),
    Medida("Foto de celular vertical", "3:4", 3024, 4032, "rectangle-vertical"),
    Medida("Foto de celular horizontal", "4:3", 4032, 3024, "rectangle-horizontal"),
    Medida("Instagram vertical", "4:5", 1080, 1350, "heart"),
    Medida("Cuadrado", "1:1", 1080, 1080, "square"),
)
ORIGINAL = Medida("Original", "", 0, 0, "image")  # sin cambiar el tamaño


def medida_valida(valor) -> Optional[tuple[int, int]]:
    """(ancho, alto) si ``valor`` es una medida usable (de la sesión, del proyecto o del historial);
    si no, None ("Original"). Acepta tupla o lista (el proyecto ``.nslite`` la guarda en JSON)."""
    if not isinstance(valor, (tuple, list)) or len(valor) != 2:
        return None
    try:
        w, h = (int(v) for v in valor)
    except (TypeError, ValueError):
        return None
    if any(isinstance(v, bool) for v in valor) or not (1 <= w <= LADO_MAX and 1 <= h <= LADO_MAX):
        return None
    return w, h


def buscar(tam) -> Optional[Medida]:
    """La medida del menú con ese tamaño (None si no es ninguna, o si es "Original")."""
    tam = medida_valida(tam)
    return next((m for m in MEDIDAS if m.tam == tam), None)


def _proporcion(w: int, h: int) -> str:
    d = math.gcd(w, h)
    return f"{w // d}:{h // d}"


def texto_boton(tam) -> str:
    """Lo que dice el botón: "9:16 · 1080×1920" (o "Medida", sin medida)."""
    tam = medida_valida(tam)
    if tam is None:
        return "Medida"
    m = buscar(tam)
    return f"{m.proporcion if m else _proporcion(*tam)} · {tam[0]}×{tam[1]}"


def texto_medida(tam) -> str:
    """Para el historial: "Celular vertical · historia (1080 × 1920)", o "original"."""
    tam = medida_valida(tam)
    if tam is None:
        return "original"
    m = buscar(tam)
    return f"{m.nombre} {m.proporcion} ({tam[0]} × {tam[1]})" if m else f"{tam[0]} × {tam[1]}"


# ---------------------------------------------------------------------------
# El recorte con la proporción de la medida
# ---------------------------------------------------------------------------

def _caja(recorte: Optional[Recorte], wb: int, hb: int) -> tuple[float, float, float, float]:
    """(x0, y0, ancho, alto) en píxeles de la foto base, de lo que queda con ese recorte."""
    if recorte is None or recorte.es_completo():
        return 0.0, 0.0, float(wb), float(hb)
    x0, y0, x1, y1 = recorte.pixeles(wb, hb)
    return float(x0), float(y0), float(x1 - x0), float(y1 - y0)


def tiene_proporcion(recorte: Optional[Recorte], wb: int, hb: int, tam) -> bool:
    """Si la foto con ese recorte (``wb`` × ``hb``: la base, ya girada) ya tiene la proporción de la
    medida, con lo que se pierde al redondear a píxeles (hasta 1,5 px)."""
    tam = medida_valida(tam)
    if tam is None:
        return True
    a = tam[0] / tam[1]
    _x, _y, cw, ch = _caja(recorte, wb, hb)
    return min(abs(cw - ch * a), abs(ch - cw / a)) <= 1.5


def _a_recorte(x0: float, y0: float, cw: float, ch: float, wb: int, hb: int) -> Optional[Recorte]:
    r = Recorte(x0 / wb, y0 / hb, (x0 + cw) / wb, (y0 + ch) / hb).normalizado()
    return None if r.es_completo() else r


def recorte_centrado(wb: int, hb: int, tam) -> Optional[Recorte]:
    """El recorte más grande con la proporción de la medida que entra en la foto, centrado. None si
    la foto ya tiene esa proporción (no hace falta recortar)."""
    w, h = medida_valida(tam)
    a = w / h
    cw = min(float(wb), hb * a)
    ch = cw / a
    if ch > hb:
        ch, cw = float(hb), hb * a
    return _a_recorte((wb - cw) / 2, (hb - ch) / 2, cw, ch, wb, hb)


def recorte_con_medida(recorte: Optional[Recorte], wb: int, hb: int, tam, previa=None) -> Optional[Recorte]:
    """El recorte para usar esa medida en una foto base de ``wb`` × ``hb``:

    * sin recorte: el centrado más grande (``recorte_centrado``);
    * con la misma proporción: el mismo;
    * con otra: la proporción nueva **alrededor de su centro**, con la misma superficie (lo que se
      eligió de cerca sigue de cerca), sin salirse de la foto. Si era el centrado de la medida
      anterior (``previa``: nadie lo movió), el centrado de la nueva (el más grande)."""
    tam = medida_valida(tam)
    if tam is None:
        return recorte
    if recorte is None or recorte.es_completo():
        return recorte_centrado(wb, hb, tam)
    if tiene_proporcion(recorte, wb, hb, tam):
        return recorte
    previa = medida_valida(previa)
    if previa is not None and recorte == recorte_centrado(wb, hb, previa):
        return recorte_centrado(wb, hb, tam)
    a = tam[0] / tam[1]
    x0, y0, cw, ch = _caja(recorte, wb, hb)
    cx, cy = x0 + cw / 2, y0 + ch / 2
    nw = math.sqrt(cw * ch * a)
    nh = nw / a
    f = min(1.0, wb / nw, hb / nh)
    nw, nh = nw * f, nh * f
    nx = min(max(cx - nw / 2, 0.0), wb - nw)
    ny = min(max(cy - nh / 2, 0.0), hb - nh)
    return _a_recorte(nx, ny, nw, nh, wb, hb)


# ---------------------------------------------------------------------------
# Llevar la foto a la medida (antes del filtro)
# ---------------------------------------------------------------------------

def tamano_trabajo(tam, forma: tuple, escala_vista: float) -> tuple[tuple[int, int], float]:
    """((ancho, alto), escala) a la que trabaja el filtro con esa medida.

    ``forma``: la de la foto que entra (la recortada, o su reducción para la vista previa);
    ``escala_vista``: la de esa foto respecto de la completa. A escala 1 (vista completa y exportar)
    es la medida exacta y escala 1. En la vista previa reducida, la medida achicada al lado largo
    de la foto que entra (sin pasarse de la medida), y esa es la ``escala_vista`` del filtro."""
    w, h = medida_valida(tam)
    if escala_vista >= 1.0:
        return (w, h), 1.0
    e = min(1.0, max(int(forma[0]), int(forma[1])) / max(w, h))
    return (max(1, round(w * e)), max(1, round(h * e))), e


def llevar_a_medida(img: np.ndarray, tam: tuple[int, int]) -> np.ndarray:
    """``img`` (RGB uint8, o un alfa HxW) a exactamente ``tam`` (ancho, alto): ``INTER_AREA`` para
    achicar, Lanczos para agrandar. Si la proporción no coincide (más de 1 %; no debería pasar: el
    recorte ya la tiene), primero se recorta al centro, así nunca se deforma."""
    import cv2

    w, h = int(tam[0]), int(tam[1])
    hi, wi = img.shape[:2]
    if (wi, hi) == (w, h):
        return img
    a = w / h
    if abs(wi / hi - a) > 0.01 * a:
        if wi / hi > a:
            nw = max(1, round(hi * a))
            x0 = (wi - nw) // 2
            img = img[:, x0:x0 + nw]
        else:
            nh = max(1, round(wi / a))
            y0 = (hi - nh) // 2
            img = img[y0:y0 + nh]
        hi, wi = img.shape[:2]
    interpolacion = cv2.INTER_AREA if w * h <= wi * hi else cv2.INTER_LANCZOS4
    salida = cv2.resize(np.ascontiguousarray(img), (w, h), interpolation=interpolacion)
    if img.dtype != np.uint8 and np.issubdtype(img.dtype, np.floating):
        salida = np.clip(salida, float(img.min()), float(img.max()))  # el rebote de Lanczos
    return salida


__all__ = ["MEDIDAS", "ORIGINAL", "Medida", "buscar", "llevar_a_medida", "medida_valida", "recorte_centrado",
           "recorte_con_medida", "tamano_trabajo", "texto_boton", "texto_medida", "tiene_proporcion"]
