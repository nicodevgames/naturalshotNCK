"""Quitar marcas de agua visibles (logos y textos de los servicios de IA).

No es un motor nuevo: arma un ``ZonaBorrado`` en modo "rellenar" sobre la
esquina donde está el logo, así que usa el relleno por parches de
``borrado.rellenar``, corre antes del filtro (el grano queda parejo encima), se
convierte con la geometría y se cachea igual que cualquier otro borrado.

* ``caja_de_preset``: posiciones típicas (abajo a la derecha, abajo al centro...).
  Es lo que hace falta casi siempre: el logo de un servicio gratuito está
  siempre en el mismo lugar.
* ``detectar_marca``: propone una caja mirando las cuatro esquinas. Heurística,
  sin IA: busca píxeles claros o muy saturados en zona de alto gradiente
  (glifos), los agrupa y devuelve la caja que los contiene. Es una propuesta:
  la caja se corrige a mano con la herramienta de marcar, como cualquier zona.

Limitaciones conocidas: falla con logos oscuros sobre fondo oscuro y con marcas
muy translúcidas; sobre texto o caras conviene ``modo="clonar"`` en lugar de
rellenar.
"""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from .edicion import ZonaBorrado
from .zonas import Zona

LADO_MARCA = 0.18     # lado de la caja, relativo al lado corto de la foto
ASPECTO_CAJA = 2.2    # la marca es más ancha que alta
INSET = 0.025         # separación del borde, relativa al lado corto
MARGEN = 0.08         # margen alrededor de la caja (tapa antialias y halo)
PLUMA = 12            # baja a propósito: la pluma de ``mascara_zona`` es
                      # proporcional al lado de la caja y acá la caja es chica
AREA_MIN = 200        # px de un glifo candidato
AREA_MAX = 0.06       # proporción de la foto que puede ocupar un glifo
DENSIDAD_MIN = 0.05   # glifos por píxel de su propia caja (el texto tiene trazos)
LADO_DETECCION = 1000  # la detección trabaja sobre una copia reducida a este lado

POSICIONES = {
    "abajo-derecha": (1.0, 1.0),
    "abajo-izquierda": (0.0, 1.0),
    "arriba-derecha": (1.0, 0.0),
    "arriba-izquierda": (0.0, 0.0),
    "abajo-centro": (0.5, 1.0),
}
NOMBRES_POSICION = {
    "abajo-derecha": "Marca abajo a la derecha",
    "abajo-izquierda": "Marca abajo a la izquierda",
    "arriba-derecha": "Marca arriba a la derecha",
    "arriba-izquierda": "Marca arriba a la izquierda",
    "abajo-centro": "Marca abajo al centro",
}


def caja_de_preset(posicion: str, aspecto: float, escala: float = 1.0) -> tuple[float, float, float, float]:
    """Caja normalizada (x0, y0, x1, y1) de una posición típica de la marca.

    ``aspecto`` es ancho / alto de la foto: el tamaño sale del lado corto, así
    el logo ocupa la misma porción de la imagen en cualquier resolución y no se
    deforma. ``escala`` agranda o achica la caja (logos grandes o chicos).
    """
    if posicion not in POSICIONES:
        raise ValueError(f"posición desconocida: {posicion!r}")
    if aspecto <= 0:
        raise ValueError(f"aspecto debe ser positivo (vino {aspecto!r})")
    if escala <= 0:
        raise ValueError(f"escala debe ser positiva (vino {escala!r})")
    ancla_h, ancla_v = POSICIONES[posicion]
    w_rel, h_rel = max(float(aspecto), 1e-6), 1.0
    corto = min(w_rel, h_rel)
    ancho = min(LADO_MARCA * escala * ASPECTO_CAJA * corto, w_rel)
    alto = min(LADO_MARCA * escala * corto, h_rel)
    inset = INSET * corto
    x0 = ancla_h * max(0.0, w_rel - ancho - 2 * inset) + inset
    y0 = ancla_v * max(0.0, h_rel - alto - 2 * inset) + inset
    return x0 / w_rel, y0 / h_rel, (x0 + ancho) / w_rel, (y0 + alto) / h_rel


def borrado_de_marca(caja, *, margen: float = MARGEN, pluma: int = PLUMA,
                     modo: str = "rellenar") -> ZonaBorrado:
    """El borrado que corresponde a una caja de marca (``rellenar`` o ``clonar``).

    La caja se agranda ``margen`` (proporción de su propio tamaño) para tapar el
    antialias del logo; el resto lo hace la dilatación de ``borrado.rellenar``.
    """
    if len(caja) != 4:
        raise ValueError("la caja tiene que ser (x0, y0, x1, y1)")
    if modo not in ("rellenar", "clonar"):
        raise ValueError(f"modo desconocido: {modo!r}")
    x0, y0, x1, y1 = (float(v) for v in caja)
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    ax, ay = (x1 - x0) * margen, (y1 - y0) * margen
    zona = Zona("rect", x0 - ax, y0 - ay, x1 + ax, y1 + ay, int(pluma), False).normalizada()
    return ZonaBorrado(zona, modo)


def _candidatos_de_marca(rgb: np.ndarray) -> np.ndarray:
    """Máscara uint8 de posibles glifos: claros o muy saturados, con gradiente."""
    gris = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2HSV)
    grad = cv2.magnitude(cv2.Sobel(gris, cv2.CV_32F, 1, 0, ksize=3),
                         cv2.Sobel(gris, cv2.CV_32F, 0, 1, ksize=3))
    claro = (hsv[..., 2] > 185) & (hsv[..., 1] < 45)
    colorido = (hsv[..., 1] > 110) & (hsv[..., 2] > 110)
    return ((claro | colorido) & (grad > 40)).astype(np.uint8)


def detectar_marca(rgb: np.ndarray, *, ventana: float = 0.3) -> Optional[tuple[float, float, float, float]]:
    """Propone la caja de una marca visible en alguna esquina, o None.

    Heurística: glifos claros y poco saturados (o muy saturados) sobre zona de
    alto gradiente. Un cielo liso es claro pero no tiene gradiente, así que no
    entra; una pared texturada sí puede entrar y por eso la caja se revisa.

    Trabaja sobre una copia reducida (``LADO_DETECCION``): la caja que devuelve
    está normalizada, así que no depende de la resolución.
    """
    if not isinstance(rgb, np.ndarray) or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise TypeError("rgb debe ser HxWx3")
    h, w = rgb.shape[:2]
    if max(h, w) > LADO_DETECCION:
        f = LADO_DETECCION / max(h, w)
        rgb = cv2.resize(rgb, (max(1, round(w * f)), max(1, round(h * f))), interpolation=cv2.INTER_AREA)
        h, w = rgb.shape[:2]
    candidatos = _candidatos_de_marca(rgb)
    if not candidatos.any():
        return None
    # Los glifos de un logo son trazos finos: se cierran con una dilatación para
    # que cada uno sea una mancha y no un anillo de 1 px.
    agrupado = cv2.dilate(candidatos, np.ones((5, 5), np.uint8))
    area_imagen = float(h * w)
    vw, vh = max(1, int(w * ventana)), max(1, int(h * ventana))
    mejor: Optional[tuple[int, tuple[int, int, int, int]]] = None
    for ancla_h, ancla_v in POSICIONES.values():
        wx0 = int(ancla_h * (w - vw))
        wy0 = int(ancla_v * (h - vh))
        trozo = agrupado[wy0:wy0 + vh, wx0:wx0 + vw]
        if not trozo.any():
            continue
        n, _, stats, _ = cv2.connectedComponentsWithStats(trozo, connectivity=8)
        cajas = []
        for i in range(1, n):
            x, y, cw, ch, area = (int(v) for v in stats[i])
            if area < AREA_MIN or area > AREA_MAX * area_imagen:
                continue
            cajas.append((x, y, cw, ch))
        if not cajas:
            continue
        total = sum(c[2] * c[3] for c in cajas)
        x0 = min(c[0] for c in cajas)
        y0 = min(c[1] for c in cajas)
        x1 = max(c[0] + c[2] for c in cajas)
        y1 = max(c[1] + c[3] for c in cajas)
        # Densidad de glifos en su propia caja, sobre los candidatos sin
        # dilatar: el texto tiene trazos, un manchón de color parejo no.
        dentro = candidatos[wy0 + y0:wy0 + y1, wx0 + x0:wx0 + x1]
        if dentro.sum() / max(1, dentro.size) < DENSIDAD_MIN:
            continue
        if mejor is None or total > mejor[0]:
            mejor = (total, (wx0 + x0, wy0 + y0, wx0 + x1, wy0 + y1))
    if mejor is None:
        return None
    x0, y0, x1, y1 = mejor[1]
    return x0 / w, y0 / h, x1 / w, y1 / h
