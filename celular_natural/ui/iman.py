"""Imán y guías inteligentes del modo Photoshop (NaturalShot Lite). Sin Qt.

Al mover capas, su caja (``documento.caja_capa``, alineada al documento) se pega a lo que tenga
cerca: el centro y los bordes del lienzo y los bordes y centros de las otras capas. Se mira cada
eje por separado: de los tres puntos de la caja que se mueve (borde de un lado, centro y el otro
borde) y de todos los objetivos, gana el par más cercano, si está a ``umbral`` o menos (en píxeles
del documento: la interfaz pasa unos pocos píxeles de pantalla divididos por el zoom). Las guías
son las líneas que se dibujan (magenta) donde se pegó: ("v", x, y0, y1) o ("h", y, x0, x1).
"""

from __future__ import annotations

from typing import Iterable, Optional

from ..motor.documento import AlmacenImagenes, Documento, caja_capa

UMBRAL_PANTALLA = 7.0  # píxeles de pantalla


def objetivos(doc: Documento, almacen: AlmacenImagenes, excluir: Iterable[str] = ()) -> tuple[list, list]:
    """Los objetivos del imán: (en x, en y), cada uno (valor, desde, hasta), donde desde y hasta son
    lo que ocupa en el otro eje (para dibujar la guía). El lienzo (bordes y centro) y cada capa
    visible que no se mueve (ni la base ni el ajuste ni un relleno, que cubren todo el lienzo), con
    sus bordes y su centro. ``excluir``: las que se mueven (y lo que tienen adentro o las contiene)."""
    W, H = float(doc.ancho), float(doc.alto)
    xs = [(0.0, 0.0, H), (W / 2, 0.0, H), (W, 0.0, H)]
    ys = [(0.0, 0.0, W), (H / 2, 0.0, W), (H, 0.0, W)]
    fuera = set(excluir)
    for i in list(fuera):
        try:
            capa = doc.capa(i)
        except KeyError:
            continue
        if capa.tipo == "grupo":
            fuera.update(d.id for d in doc.descendientes(i))
        fuera.update(doc.ancestros(i))
    for c in doc.capas[1:]:
        if c.id in fuera or c.tipo in ("ajuste_natural", "relleno", "grupo") or not c.visible:
            continue
        if any(not doc.capa(a).visible for a in doc.ancestros(c.id)):
            continue
        caja = caja_capa(doc, c.id, almacen)
        if caja is None:
            continue
        x0, y0, x1, y1 = caja
        for v in (x0, (x0 + x1) / 2, x1):
            xs.append((v, y0, y1))
        for v in (y0, (y0 + y1) / 2, y1):
            ys.append((v, x0, x1))
    return xs, ys


def _eje(a: float, b: float, objetivos_eje: list, umbral: float) -> Optional[tuple[float, tuple]]:
    """El corrimiento más chico (de los tres puntos a, centro, b a algún objetivo) y su objetivo."""
    mejor = None
    for punto in (a, (a + b) / 2, b):
        for obj in objetivos_eje:
            d = obj[0] - punto
            if abs(d) <= umbral and (mejor is None or abs(d) < abs(mejor[0])):
                mejor = (d, obj)
    return mejor


def ajustar(caja: tuple, xs: list, ys: list, umbral: float) -> tuple[float, float, list]:
    """(dx, dy, guías): cuánto correr la caja (x0, y0, x1, y1) para que se pegue, y las guías."""
    x0, y0, x1, y1 = caja
    dx = dy = 0.0
    guias = []
    en_x = _eje(x0, x1, xs, umbral)
    en_y = _eje(y0, y1, ys, umbral)
    if en_x is not None:
        dx = en_x[0]
    if en_y is not None:
        dy = en_y[0]
    if en_x is not None:
        v, desde, hasta = en_x[1]
        guias.append(("v", v, min(desde, y0 + dy), max(hasta, y1 + dy)))
    if en_y is not None:
        v, desde, hasta = en_y[1]
        guias.append(("h", v, min(desde, x0 + dx), max(hasta, x1 + dx)))
    return dx, dy, guias


__all__ = ["UMBRAL_PANTALLA", "ajustar", "objetivos"]
