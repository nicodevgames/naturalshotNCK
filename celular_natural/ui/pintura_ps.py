"""Pintura y recorte del modo Photoshop (NaturalShot Lite, Etapa 2, U3).

Lo que el modo (``modo_photoshop``) usa para las herramientas Pincel (B), Borrador (E), Bote de pintura
(G), Degradado (Mayús+G) y Recortar (C), sin tocar el documento por su cuenta:

* ``Lienzo``: la imagen de una capa (imagen o píxeles) y cómo se pasa del documento a la capa (con su
  transformación). Si se pinta afuera de la imagen, la capa crece (hasta cubrir el lienzo).
* ``TrazoEnCurso``: el trazo de pincel o de borrador mientras se arrastra. Cada tramo nuevo suma su
  cobertura (``pintura.mascara_trazo``) y se dibuja en una **superposición** (una ``QImage`` que se
  actualiza solo en el pedazo que cambió): fluido, sin recomponer el documento. Al soltar,
  ``aplicar`` hace el trazo de verdad (``pintura.trazo``) sobre la imagen de la capa.
* ``relleno_lineal_de_arrastre``: un degradado arrastrado de p0 a p1, como ``Relleno`` lineal de una
  capa de relleno (el ángulo y las paradas corridas para que empiece en p0 y termine en p1).
* ``fundir_encima``: un RGBA encima de otro (el degradado sobre una capa de píxeles).
* ``CajaRecorte``: el recuadro de Recortar, con sus 8 manijas, la proporción y el dibujo.
* ``ControlesPincel``, ``ControlesBote`` y ``ControlesDegradado``: las barras de opciones.
"""

from __future__ import annotations

import math
from typing import Callable, Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QTransform
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QPushButton, QSizePolicy, QSlider, QToolButton, QWidget

from ..motor.documento import matriz_transformacion
from ..motor.formas import Relleno
from ..motor.pintura import mascara_trazo, trazo
from . import iconos
from .opciones_ps import BotonRelleno, _etiqueta, _numero

AREA_MAX_AMPLIADA = 64_000_000  # píxeles de una capa agrandada para pintar afuera de ella, como mucho
TAMANO_MIN, TAMANO_MAX = 1, 2500  # px del documento
MANIJA_PANTALLA = 9.0  # px de pantalla alrededor de una manija del recorte


def siguiente_tamano(tam: float, sentido: int) -> int:
    """El tamaño del pincel después de ``]`` (``sentido`` = 1) o ``[`` (-1), a pasos como Photoshop:
    de a 1 hasta 10, de a 5 hasta 50, de a 10 hasta 100, de a 25 hasta 300 y de a 50 después."""
    def paso(t: int) -> int:
        return 1 if t < 10 else 5 if t < 50 else 10 if t < 100 else 25 if t < 300 else 50

    tam = int(round(tam))
    if sentido > 0:
        p = paso(tam)
        nuevo = (tam // p + 1) * p
    else:
        p = paso(tam - 1)
        nuevo = -(-tam // p) * p - p
    return int(min(TAMANO_MAX, max(TAMANO_MIN, nuevo)))


def como_rgba(img: np.ndarray) -> np.ndarray:
    """RGBA uint8 (una imagen RGB, opaca, gana el alfa)."""
    img = np.asarray(img)
    if img.ndim == 3 and img.shape[2] == 4:
        return img
    if img.ndim == 2:
        img = np.dstack([img, img, img])
    return np.dstack([img[..., :3], np.full(img.shape[:2], 255, np.uint8)])


# ---------------------------------------------------------------------------
# Dónde se pinta
# ---------------------------------------------------------------------------

class Lienzo:
    """La imagen de una capa (RGBA) y su transformación, para pintar con coordenadas del documento.

    Con ``ampliar``, el espacio de trabajo de la capa se extiende (hacia afuera de la imagen) hasta
    cubrir todo el lienzo del documento: así se puede pintar donde la capa no llegaba. Las
    coordenadas "de trabajo" son las de la capa más ``pad`` (lo que se extendió a la izquierda y
    arriba); ``tam`` es el tamaño del espacio de trabajo."""

    def __init__(self, img: np.ndarray, transform, ancho_doc: int, alto_doc: int, ampliar: bool = True):
        self.img = como_rgba(img)
        self.transform = transform
        h, w = self.img.shape[:2]
        self.m = np.vstack([matriz_transformacion(transform, w, h), [0.0, 0.0, 1.0]])
        self.inv = np.linalg.inv(self.m)
        self.escala = math.sqrt(abs(float(np.linalg.det(self.m[:2, :2])))) or 1.0
        pad_x = pad_y = 0
        ancho, alto = w, h
        if ampliar:
            esq = self.inv @ np.array([[0, ancho_doc, ancho_doc, 0], [0, 0, alto_doc, alto_doc], [1, 1, 1, 1]], float)
            ux0 = min(0, int(math.floor(esq[0].min())))
            uy0 = min(0, int(math.floor(esq[1].min())))
            ux1 = max(w, int(math.ceil(esq[0].max())))
            uy1 = max(h, int(math.ceil(esq[1].max())))
            if (ux1 - ux0) * (uy1 - uy0) <= max(AREA_MAX_AMPLIADA, w * h):
                pad_x, pad_y, ancho, alto = -ux0, -uy0, ux1 - ux0, uy1 - uy0
        self.pad = (pad_x, pad_y)
        self.tam = (ancho, alto)

    def a_capa(self, x: float, y: float) -> tuple[float, float]:
        """Un punto del documento en coordenadas de trabajo."""
        u, v, _ = self.inv @ np.array([x, y, 1.0])
        return float(u + self.pad[0]), float(v + self.pad[1])

    def transformacion_qt(self, origen: QPointF, zoom: float) -> QTransform:
        """De coordenadas de trabajo a la pantalla (origen y zoom de la vista)."""
        a = self.m
        px, py = self.pad
        dx = a[0, 2] - a[0, 0] * px - a[0, 1] * py
        dy = a[1, 2] - a[1, 0] * px - a[1, 1] * py
        return QTransform(zoom * a[0, 0], zoom * a[1, 0], zoom * a[0, 1], zoom * a[1, 1],
                          origen.x() + zoom * dx, origen.y() + zoom * dy)

    def aplicar(self, funcion: Callable[[np.ndarray, float, float], np.ndarray], caja: tuple):
        """Aplica ``funcion(imagen, dx, dy)`` (que devuelve la imagen nueva; ``dx, dy`` llevan las
        coordenadas de trabajo a las de esa imagen) y devuelve (imagen, transformación). Si ``caja``
        (lo tocado, en coordenadas de trabajo) se sale de la imagen, la capa crece lo justo y su
        transformación se corre para que lo de antes quede en el mismo lugar."""
        from dataclasses import replace
        px, py = self.pad
        h, w = self.img.shape[:2]
        x0, y0, x1, y1 = (int(math.floor(caja[0])), int(math.floor(caja[1])), int(math.ceil(caja[2])),
                          int(math.ceil(caja[3])))
        if x0 >= px and y0 >= py and x1 <= px + w and y1 <= py + h:
            return funcion(self.img, -px, -py), self.transform
        ux0, uy0 = min(px, x0), min(py, y0)
        ux1, uy1 = max(px + w, x1), max(py + h, y1)
        grande = np.zeros((uy1 - uy0, ux1 - ux0, 4), np.uint8)
        grande[py - uy0:py - uy0 + h, px - ux0:px - ux0 + w] = self.img
        out = funcion(grande, -ux0, -uy0)
        # Lo que quedó transparente afuera de la imagen de antes no hace falta: se recorta.
        alfa = out[..., 3] > 0
        filas, cols = np.nonzero(alfa.any(axis=1))[0], np.nonzero(alfa.any(axis=0))[0]
        rx0, ry0, rx1, ry1 = px - ux0, py - uy0, px - ux0 + w, py - uy0 + h
        if len(filas):
            rx0, rx1 = min(rx0, int(cols[0])), max(rx1, int(cols[-1]) + 1)
            ry0, ry1 = min(ry0, int(filas[0])), max(ry1, int(filas[-1]) + 1)
        out = np.ascontiguousarray(out[ry0:ry1, rx0:rx1])
        # El centro de la imagen nueva, en coordenadas de la capa de antes, va al documento.
        cx = (rx0 + rx1) / 2.0 + ux0 - px
        cy = (ry0 + ry1) / 2.0 + uy0 - py
        x, y, _ = self.m @ np.array([cx, cy, 1.0])
        return out, replace(self.transform, x=float(x), y=float(y))


# ---------------------------------------------------------------------------
# El trazo mientras se arrastra
# ---------------------------------------------------------------------------

class TrazoEnCurso:
    """Un trazo de pincel o de borrador que se está haciendo (ver el módulo). ``tamano`` en px del
    documento; ``dureza`` y ``opacidad`` de 0 a 1; ``color`` RGBA."""

    def __init__(self, lienzo: Lienzo, tamano: float, dureza: float, opacidad: float, color, borrar: bool):
        self.lienzo = lienzo
        self.tamano_doc = float(tamano)
        self.tamano = max(0.5, float(tamano) / lienzo.escala)  # en px de la capa
        self.dureza = float(dureza)
        self.opacidad = float(opacidad)
        self.color = tuple(int(c) for c in color)
        self.borrar = bool(borrar)
        ancho, alto = lienzo.tam
        # np.zeros no toca la memoria hasta que se escribe: lo que no se pinta no cuesta.
        self.cobertura = np.zeros((alto, ancho), np.uint8)
        self._vista = np.zeros((alto, ancho, 4), np.uint8)  # BGRA premultiplicado (ARGB32 en memoria)
        self.imagen = QImage(self._vista.data, ancho, alto, 4 * ancho, QImage.Format_ARGB32_Premultiplied)
        self.puntos: list[tuple[float, float]] = []
        self.ultimo_doc: Optional[QPointF] = None
        self.caja: Optional[list] = None  # lo tocado (x0, y0, x1, y1), en coordenadas de trabajo
        fuerza = self.opacidad * (1.0 if self.borrar else self.color[3] / 255.0)
        self._fuerza = float(min(1.0, max(0.0, fuerza)))

    def agregar(self, x: float, y: float) -> None:
        """Un punto más (del documento): suma la cobertura del tramo nuevo y la superposición."""
        u, v = self.lienzo.a_capa(x, y)
        if self.puntos:
            pu, pv = self.puntos[-1]
            if (u - pu) ** 2 + (v - pv) ** 2 < 0.04:
                return
            tramo = [self.puntos[-1], (u, v)]
        else:
            tramo = [(u, v)]
        self.puntos.append((u, v))
        self.ultimo_doc = QPointF(x, y)
        ancho, alto = self.lienzo.tam
        hecho = mascara_trazo(ancho, alto, tramo, self.tamano, self.dureza)
        if hecho is None:
            return
        x0, y0, m = hecho
        h, w = m.shape
        zona = self.cobertura[y0:y0 + h, x0:x0 + w]
        np.maximum(zona, np.rint(m * 255.0).astype(np.uint8), out=zona)
        self._pintar_vista(x0, y0, x0 + w, y0 + h)
        if self.caja is None:
            self.caja = [x0, y0, x0 + w, y0 + h]
        else:
            c = self.caja
            self.caja = [min(c[0], x0), min(c[1], y0), max(c[2], x0 + w), max(c[3], y0 + h)]

    def _pintar_vista(self, x0: int, y0: int, x1: int, y1: int) -> None:
        a = self.cobertura[y0:y1, x0:x1].astype(np.float32) * np.float32(self._fuerza / 255.0)
        trozo = self._vista[y0:y1, x0:x1]
        if self.borrar:
            # Lo que se borra se ve como el tablero de la transparencia.
            yy, xx = np.mgrid[y0:y1, x0:x1]
            bloque = max(2, int(round(8 / max(self.lienzo.escala, 1e-3))))
            gris = np.where(((yy // bloque + xx // bloque) % 2) == 0, 204.0, 150.0).astype(np.float32)
            for c in range(3):
                trozo[..., c] = np.rint(gris * a).astype(np.uint8)
        else:
            r, g, b = self.color[:3]
            for c, valor in ((0, b), (1, g), (2, r)):
                trozo[..., c] = np.rint(np.float32(valor) * a).astype(np.uint8)
        trozo[..., 3] = np.rint(a * 255.0).astype(np.uint8)

    def dibujar(self, p: QPainter, origen: QPointF, zoom: float) -> None:
        """La superposición del trazo (solo la parte tocada) sobre la vista."""
        if self.caja is None:
            return
        x0, y0, x1, y1 = self.caja
        p.save()
        p.setRenderHint(QPainter.SmoothPixmapTransform, zoom < 2.0)
        p.setTransform(self.lienzo.transformacion_qt(origen, zoom), True)
        r = QRectF(x0, y0, x1 - x0, y1 - y0)
        p.drawImage(r, self.imagen, r)
        p.restore()

    def aplicar(self):
        """El trazo de verdad sobre la imagen de la capa: (imagen nueva, transformación), o None si
        no tocó nada."""
        if self.caja is None or not self.puntos:
            return None
        caja = list(self.caja)
        if self.borrar:  # el borrador no agranda la capa
            px, py = self.lienzo.pad
            h, w = self.lienzo.img.shape[:2]
            caja = [max(caja[0], px), max(caja[1], py), min(caja[2], px + w), min(caja[3], py + h)]
            if caja[2] <= caja[0] or caja[3] <= caja[1]:
                return None
        puntos = np.array(self.puntos, np.float64)

        def pintar(img, dx, dy):
            return trazo(img, puntos + np.array([dx, dy]), self.tamano, self.dureza, self.opacidad, self.color,
                         borrar=self.borrar)

        return self.lienzo.aplicar(pintar, caja)


def fundir_encima(destino: np.ndarray, fuente: np.ndarray, opacidad: float = 1.0) -> np.ndarray:
    """``fuente`` (RGBA) encima de ``destino`` (RGBA, del mismo tamaño), "source-over" sin
    premultiplicar, con ``opacidad``. Devuelve una copia nueva."""
    d = destino.astype(np.float32)
    s = fuente.astype(np.float32)
    a_s = s[..., 3:4] / 255.0 * float(opacidad)
    a_d = d[..., 3:4] / 255.0
    a_o = a_s + a_d * (1.0 - a_s)
    with np.errstate(divide="ignore", invalid="ignore"):
        rgb = np.where(a_o > 0, (s[..., :3] * a_s + d[..., :3] * a_d * (1.0 - a_s)) / a_o, s[..., :3])
    out = np.empty_like(destino)
    out[..., :3] = np.clip(np.rint(rgb), 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(np.rint(a_o[..., 0] * 255.0), 0, 255).astype(np.uint8)
    return out


# ---------------------------------------------------------------------------
# Degradado arrastrado → capa de relleno
# ---------------------------------------------------------------------------

def _direccion(grados: float) -> tuple[float, float]:
    """(cos, sen), exactos en los múltiplos de 90° (como ``formas``)."""
    if float(grados) % 90.0 == 0.0:
        k = int(round(float(grados) / 90.0)) % 4
        return ((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0))[k]
    r = math.radians(grados)
    return math.cos(r), math.sin(r)


def _color_en(relleno: Relleno, t: float) -> tuple:
    """El color del degradado en ``t`` (0..1), interpolado directo (sin premultiplicar)."""
    cols = np.array(relleno.colores, np.float64)
    pos = np.array(relleno.paradas) if relleno.paradas else np.linspace(0.0, 1.0, len(cols))
    t = min(1.0, max(0.0, t))
    return tuple(int(round(float(np.interp(t, pos, cols[:, c])))) for c in range(4))


def relleno_lineal_de_arrastre(relleno: Relleno, p0, p1, ancho: int, alto: int,
                               max_colores: int = 4) -> Optional[Relleno]:
    """El ``Relleno`` lineal (de una capa de relleno de ``ancho`` × ``alto``) que da el degradado de
    ``relleno`` (sus colores y paradas) arrastrado de ``p0`` a ``p1``: el ángulo de p0 a p1 y las
    paradas corridas para que el primer color esté en p0 y el último en p1 (antes y después, esos
    colores). None si p0 = p1 o si harían falta más de ``max_colores`` colores."""
    dx, dy = float(p1[0]) - float(p0[0]), float(p1[1]) - float(p0[1])
    if math.hypot(dx, dy) < 1e-6:
        return None
    angulo = math.degrees(math.atan2(dy, dx))
    if abs(angulo - round(angulo)) < 1e-9:
        angulo = float(round(angulo))
    c, s = _direccion(angulo)
    medio = (abs(ancho * c) + abs(alto * s)) / 2.0
    ix, iy = ancho / 2.0 - c * medio, alto / 2.0 - s * medio
    total = 2.0 * medio
    t0 = ((float(p0[0]) - ix) * c + (float(p0[1]) - iy) * s) / total
    t1 = ((float(p1[0]) - ix) * c + (float(p1[1]) - iy) * s) / total
    if t1 - t0 < 1e-9:
        return None
    pos = list(relleno.paradas) if relleno.paradas else list(np.linspace(0.0, 1.0, len(relleno.colores)))
    paradas, colores = [], []
    # El color en el borde de entrada (t = 0) si el degradado empieza antes.
    if t0 + pos[0] * (t1 - t0) < 0.0:
        paradas.append(0.0)
        colores.append(_color_en(relleno, (0.0 - t0) / (t1 - t0)))
    for q, col in zip(pos, relleno.colores):
        t = t0 + q * (t1 - t0)
        if 0.0 <= t <= 1.0:
            paradas.append(float(t))
            colores.append(tuple(col))
    if t0 + pos[-1] * (t1 - t0) > 1.0:
        paradas.append(1.0)
        colores.append(_color_en(relleno, (1.0 - t0) / (t1 - t0)))
    if not colores:  # todo el lienzo cae antes de p0 o después de p1
        u = 0.0 if t1 <= 0.0 else 1.0
        colores = [_color_en(relleno, (u - t0) / (t1 - t0))] * 2
        paradas = [0.0, 1.0]
    if len(colores) == 1:
        colores.append(colores[0])
        paradas.append(1.0 if paradas[0] < 1.0 else paradas[0])
    if len(colores) > max_colores:
        return None
    paradas = [min(1.0, max(0.0, x)) for x in paradas]
    for i in range(1, len(paradas)):
        paradas[i] = max(paradas[i], paradas[i - 1])
    return Relleno("lineal", tuple(colores), tuple(paradas), angulo)


# ---------------------------------------------------------------------------
# Recortar
# ---------------------------------------------------------------------------

class CajaRecorte:
    """El recuadro de Recortar en píxeles del documento (``rect``), con 8 manijas, la proporción
    (``aspecto`` = ancho / alto, o None) y, con ``limitar``, sin salirse del lienzo (una foto)."""

    MANIJAS = ("tl", "t", "tr", "r", "br", "b", "bl", "l")
    CURSORES = {"tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor, "tr": Qt.SizeBDiagCursor,
                "bl": Qt.SizeBDiagCursor, "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor, "l": Qt.SizeHorCursor,
                "r": Qt.SizeHorCursor, "mover": Qt.SizeAllCursor}

    def __init__(self, ancho: int, alto: int, aspecto: Optional[float] = None, limitar: bool = False):
        self.tam = (int(ancho), int(alto))
        self.limitar = bool(limitar)
        self.aspecto: Optional[float] = None
        self.rect = QRectF(0, 0, ancho, alto)
        self._gesto: Optional[tuple] = None
        if aspecto:
            self.establecer_aspecto(aspecto)

    # ------------------------------------------------------------ medidas
    def es_todo(self) -> bool:
        return self.pixeles() == (0, 0, self.tam[0], self.tam[1])

    def pixeles(self) -> tuple[int, int, int, int]:
        """(x0, y0, x1, y1) enteros."""
        r = self.rect.normalized()
        x0, y0 = int(round(r.left())), int(round(r.top()))
        x1, y1 = max(x0 + 1, int(round(r.right()))), max(y0 + 1, int(round(r.bottom())))
        return x0, y0, x1, y1

    def _puntos_manijas(self) -> dict:
        r = self.rect.normalized()
        cx, cy = r.center().x(), r.center().y()
        return {"tl": QPointF(r.left(), r.top()), "t": QPointF(cx, r.top()), "tr": QPointF(r.right(), r.top()),
                "r": QPointF(r.right(), cy), "br": QPointF(r.right(), r.bottom()), "b": QPointF(cx, r.bottom()),
                "bl": QPointF(r.left(), r.bottom()), "l": QPointF(r.left(), cy)}

    def manija_en(self, q: QPointF, zoom: float) -> Optional[str]:
        """La manija en (q) (px del documento): una de ``MANIJAS``, "mover" (adentro) o None (afuera)."""
        tol = MANIJA_PANTALLA / max(zoom, 1e-6)
        mejor, dist = None, tol
        for clave, punto in self._puntos_manijas().items():
            d = max(abs(punto.x() - q.x()), abs(punto.y() - q.y()))
            if d <= dist and (mejor is None or len(clave) >= len(mejor) or d < dist):
                mejor, dist = clave, d
        if mejor is not None:
            return mejor
        return "mover" if self.rect.normalized().contains(q) else None

    # ------------------------------------------------------------ proporción
    def establecer_aspecto(self, aspecto: Optional[float]) -> None:
        """Con una proporción, el recuadro más grande con esa proporción dentro del actual, centrado."""
        self.aspecto = float(aspecto) if aspecto else None
        if not self.aspecto:
            return
        r = self.rect.normalized()
        w, h = r.width(), r.height()
        if w / max(h, 1e-6) > self.aspecto:
            w = h * self.aspecto
        else:
            h = w / self.aspecto
        c = r.center()
        self.rect = QRectF(c.x() - w / 2, c.y() - h / 2, w, h)
        self._limitar()

    # ------------------------------------------------------------ arrastre
    def empezar(self, manija: Optional[str], q: QPointF) -> None:
        self._gesto = (manija, QPointF(q), QRectF(self.rect.normalized()))

    def arrastrar(self, q: QPointF, mayus: bool = False) -> None:
        if self._gesto is None:
            return
        manija, q0, r0 = self._gesto
        dx, dy = q.x() - q0.x(), q.y() - q0.y()
        aspecto = self.aspecto or ((r0.width() / max(r0.height(), 1e-6)) if mayus and manija in
                                   ("tl", "tr", "bl", "br") else None)
        if manija == "mover":
            r = r0.translated(dx, dy)
            if self.limitar:
                w, h = self.tam
                r.moveLeft(min(max(r.left(), 0.0), w - r.width()))
                r.moveTop(min(max(r.top(), 0.0), h - r.height()))
            self.rect = r
            return
        if manija is None:  # un recuadro nuevo, desde donde se apretó
            ancla, punta = q0, q
            w, h = punta.x() - ancla.x(), punta.y() - ancla.y()
            if aspecto or (mayus and not self.aspecto):
                aspecto = aspecto or 1.0
                w, h = self._con_aspecto(w, h, aspecto)
            self.rect = QRectF(ancla.x(), ancla.y(), w, h).normalized()
            self._limitar(ancla)
            return
        left, top, right, bottom = r0.left(), r0.top(), r0.right(), r0.bottom()
        if "l" in manija:
            left += dx
        if "r" in manija:
            right += dx
        if "t" in manija:
            top += dy
        if "b" in manija:
            bottom += dy
        if manija in ("tl", "tr", "bl", "br"):
            ax = r0.right() if "l" in manija else r0.left()
            ay = r0.bottom() if "t" in manija else r0.top()
            px = left if "l" in manija else right
            py = top if "t" in manija else bottom
            w, h = px - ax, py - ay
            if aspecto:
                w, h = self._con_aspecto(w, h, aspecto)
            self.rect = QRectF(ax, ay, w, h).normalized()
            self._limitar(QPointF(ax, ay))
            return
        # Un lado: con proporción, el otro lado crece parejo alrededor del centro.
        r = QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()
        if aspecto:
            c = r0.center()
            if manija in ("l", "r"):
                h = r.width() / aspecto
                r = QRectF(r.left(), c.y() - h / 2, r.width(), h)
            else:
                w = r.height() * aspecto
                r = QRectF(c.x() - w / 2, r.top(), w, r.height())
        self.rect = r
        self._limitar()

    @staticmethod
    def _con_aspecto(w: float, h: float, aspecto: float) -> tuple[float, float]:
        sx, sy = (1.0 if w >= 0 else -1.0), (1.0 if h >= 0 else -1.0)
        if abs(w) / aspecto >= abs(h):
            h = sy * abs(w) / aspecto
        else:
            w = sx * abs(h) * aspecto
        return w, h

    def _limitar(self, ancla: Optional[QPointF] = None) -> None:
        """Al menos 1 px de lado; con ``limitar``, adentro del lienzo (manteniendo la proporción,
        achicado hacia el ``ancla`` si hace falta)."""
        r = self.rect.normalized()
        if r.width() < 1:
            r.setWidth(1)
        if r.height() < 1:
            r.setHeight(1)
        if self.limitar:
            w, h = self.tam
            dentro = r.intersected(QRectF(0, 0, w, h))
            if dentro.isEmpty():
                dentro = QRectF(0, 0, w, h)
            if self.aspecto and dentro != r:
                ancla = ancla if ancla is not None else dentro.center()
                aw, ah = dentro.width(), dentro.height()
                if aw / max(ah, 1e-6) > self.aspecto:
                    aw = ah * self.aspecto
                else:
                    ah = aw / self.aspecto
                x = dentro.left() if abs(ancla.x() - dentro.left()) <= abs(ancla.x() - dentro.right()) \
                    else dentro.right() - aw
                y = dentro.top() if abs(ancla.y() - dentro.top()) <= abs(ancla.y() - dentro.bottom()) \
                    else dentro.bottom() - ah
                dentro = QRectF(x, y, aw, ah)
            r = dentro
        self.rect = r

    def soltar(self) -> None:
        self._gesto = None

    # ------------------------------------------------------------ dibujo
    def dibujar(self, p: QPainter, a_pantalla: Callable[[QPointF], QPointF], ancho_vista: float,
                alto_vista: float) -> None:
        """Oscurece lo que se va, la regla de los tercios, el borde, las 8 manijas y la medida."""
        r = QRectF(a_pantalla(self.rect.normalized().topLeft()), a_pantalla(self.rect.normalized().bottomRight()))
        p.save()
        p.setRenderHint(QPainter.Antialiasing, False)
        afuera = QPainterPath()
        afuera.addRect(QRectF(-10, -10, ancho_vista + 20, alto_vista + 20))
        adentro = QPainterPath()
        adentro.addRect(r)
        p.fillPath(afuera.subtracted(adentro), QColor(0, 0, 0, 140))
        p.setPen(QPen(QColor(255, 255, 255, 90), 1))
        for i in (1, 2):
            p.drawLine(QPointF(r.left() + r.width() * i / 3, r.top()), QPointF(r.left() + r.width() * i / 3, r.bottom()))
            p.drawLine(QPointF(r.left(), r.top() + r.height() * i / 3), QPointF(r.right(), r.top() + r.height() * i / 3))
        p.setPen(QPen(QColor(0, 0, 0, 160), 3))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)
        p.setPen(QPen(QColor("#ffffff"), 1.4))
        p.drawRect(r)
        p.setRenderHint(QPainter.Antialiasing, True)
        for clave, punto in self._puntos_manijas().items():
            s = a_pantalla(punto)
            lado = 9.0 if len(clave) == 2 else 7.0
            p.setPen(QPen(QColor(0, 0, 0, 200), 1.2))
            p.setBrush(QColor("#ffffff"))
            p.drawRect(QRectF(s.x() - lado / 2, s.y() - lado / 2, lado, lado))
        x0, y0, x1, y1 = self.pixeles()
        texto = f"{x1 - x0} × {y1 - y0} px"
        f = p.font()
        f.setPointSizeF(9.0)
        f.setBold(True)
        p.setFont(f)
        ancho_texto = p.fontMetrics().horizontalAdvance(texto) + 14
        caja = QRectF(r.left(), r.bottom() + 8, ancho_texto, 22)
        if caja.bottom() > alto_vista - 4:
            caja.moveTop(r.bottom() - 30)
            caja.moveLeft(r.left() + 6)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20, 20, 24, 220))
        p.drawRoundedRect(caja, 6, 6)
        p.setPen(QColor("#ffffff"))
        p.drawText(caja, Qt.AlignCenter, texto)
        p.restore()


# ---------------------------------------------------------------------------
# Barras de opciones
# ---------------------------------------------------------------------------

def _fila(widget: QWidget) -> QHBoxLayout:
    capa = QHBoxLayout(widget)
    capa.setContentsMargins(0, 0, 0, 0)
    capa.setSpacing(6)
    return capa


class ControlesPincel(QWidget):
    """Pincel y Borrador: tamaño (deslizador y número; ``[`` y ``]``), dureza y opacidad.
    ``cambio(dict)`` con ``tamano`` (px), ``dureza`` y ``opacidad`` (0 a 1)."""

    cambio = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cargando = False
        capa = _fila(self)
        ayuda = "Tamaño del pincel en píxeles del documento. Con el teclado: [ achica y ] agranda."
        capa.addWidget(_etiqueta("Tamaño", ayuda))
        self.slider_tamano = QSlider(Qt.Horizontal)
        self.slider_tamano.setRange(TAMANO_MIN, 300)
        self.slider_tamano.setFixedWidth(84)
        self.slider_tamano.setFocusPolicy(Qt.NoFocus)
        self.slider_tamano.setToolTip(ayuda)
        self.slider_tamano.valueChanged.connect(lambda v: self._avisar({"tamano": float(v)}))
        capa.addWidget(self.slider_tamano)
        self.numero_tamano = _numero(TAMANO_MIN, TAMANO_MAX, 0, " px", ancho=62)
        self.numero_tamano.setToolTip(ayuda)
        self.numero_tamano.valueChanged.connect(lambda v: self._avisar({"tamano": float(v)}))
        capa.addWidget(self.numero_tamano)
        capa.addSpacing(4)
        ayuda = "Dureza del borde: 0 % es muy suave (se funde) y 100 %, duro."
        capa.addWidget(_etiqueta("Dureza", ayuda))
        self.numero_dureza = _numero(0, 100, 0, " %", ancho=54)
        self.numero_dureza.setToolTip(ayuda)
        self.numero_dureza.valueChanged.connect(lambda v: self._avisar({"dureza": v / 100.0}))
        capa.addWidget(self.numero_dureza)
        capa.addSpacing(4)
        ayuda = "Opacidad del trazo (pasar dos veces por el mismo lugar en el mismo trazo no lo oscurece de más)."
        capa.addWidget(_etiqueta("Opacidad", ayuda))
        self.numero_opacidad = _numero(1, 100, 0, " %", ancho=54)
        self.numero_opacidad.setToolTip(ayuda)
        self.numero_opacidad.valueChanged.connect(lambda v: self._avisar({"opacidad": v / 100.0}))
        capa.addWidget(self.numero_opacidad)

    def mostrar(self, valores: dict) -> None:
        self._cargando = True
        try:
            tam = float(valores.get("tamano", 20.0))
            self.slider_tamano.setValue(int(round(min(tam, self.slider_tamano.maximum()))))
            self.numero_tamano.setValue(tam)
            self.numero_dureza.setValue(round(float(valores.get("dureza", 0.8)) * 100))
            self.numero_opacidad.setValue(round(float(valores.get("opacidad", 1.0)) * 100))
        finally:
            self._cargando = False

    def _avisar(self, cambios: dict) -> None:
        if not self._cargando:
            self.cambio.emit(cambios)


class ControlesBote(QWidget):
    """Bote de pintura: tolerancia, contiguo y "Todas las capas". ``cambio(dict)`` con
    ``tolerancia`` (0 a 255), ``contiguo`` y ``todas``."""

    cambio = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cargando = False
        capa = _fila(self)
        ayuda = ("Tolerancia: cuánto se puede parecer un color al del clic para rellenarlo (0: solo el mismo "
                 "color; 255: todo).")
        capa.addWidget(_etiqueta("Tolerancia", ayuda))
        self.numero_tolerancia = _numero(0, 255, 0, "", ancho=50)
        self.numero_tolerancia.setToolTip(ayuda)
        self.numero_tolerancia.valueChanged.connect(lambda v: self._avisar({"tolerancia": int(v)}))
        capa.addWidget(self.numero_tolerancia)
        capa.addSpacing(6)
        self.check_contiguo = QCheckBox("Contiguo")
        self.check_contiguo.setFocusPolicy(Qt.NoFocus)
        self.check_contiguo.setToolTip("Rellena solo la zona unida al clic. Sin tildar: todos los píxeles "
                                       "parecidos de la capa.")
        self.check_contiguo.toggled.connect(lambda x: self._avisar({"contiguo": bool(x)}))
        capa.addWidget(self.check_contiguo)
        self.check_todas = QCheckBox("Todas las capas")
        self.check_todas.setFocusPolicy(Qt.NoFocus)
        self.check_todas.setToolTip("Elige la zona por lo que se ve (la composición de todas las capas), "
                                    "no solo por la capa elegida. El relleno va igual en la capa elegida.")
        self.check_todas.toggled.connect(lambda x: self._avisar({"todas": bool(x)}))
        capa.addWidget(self.check_todas)

    def mostrar(self, valores: dict) -> None:
        self._cargando = True
        try:
            self.numero_tolerancia.setValue(int(valores.get("tolerancia", 32)))
            self.check_contiguo.setChecked(bool(valores.get("contiguo", True)))
            self.check_todas.setChecked(bool(valores.get("todas", False)))
        finally:
            self._cargando = False

    def _avisar(self, cambios: dict) -> None:
        if not self._cargando:
            self.cambio.emit(cambios)


class ControlesDegradado(QWidget):
    """Degradado: lineal o radial, los colores (de frente a fondo, o el editor de degradado) y la
    opacidad. ``cambio(dict)`` con ``radial`` (bool), ``relleno`` (``Relleno`` o None = de frente a
    fondo) y ``opacidad`` (0 a 1)."""

    cambio = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cargando = False
        capa = _fila(self)
        self.boton_lineal = self._boton_texto("Lineal", "Degradado lineal: de donde apretás a donde soltás")
        self.boton_radial = self._boton_texto("Radial", "Degradado radial: desde donde apretás (el centro) hasta "
                                                        "donde soltás (el borde)")
        self.boton_lineal.clicked.connect(lambda: self._avisar({"radial": False}))
        self.boton_radial.clicked.connect(lambda: self._avisar({"radial": True}))
        capa.addWidget(self.boton_lineal)
        capa.addWidget(self.boton_radial)
        capa.addSpacing(6)
        capa.addWidget(_etiqueta("Colores", "Los colores del degradado: clic en la muestra para editarlos (de 2 a 4 "
                                            "colores, con su posición)"))
        self.boton_relleno = BotonRelleno(Relleno("lineal", ((0, 0, 0, 255), (255, 255, 255, 255))), ancho=74)
        self.boton_relleno.rellenoCambiado.connect(lambda r: self._avisar({"relleno": r}))
        capa.addWidget(self.boton_relleno)
        self.boton_frente_fondo = QPushButton()
        self.boton_frente_fondo.setObjectName("botonOpcionPS")
        self.boton_frente_fondo.setIcon(iconos.icono("refresh-cw", 14))
        self.boton_frente_fondo.setCheckable(True)
        self.boton_frente_fondo.setFocusPolicy(Qt.NoFocus)
        self.boton_frente_fondo.setCursor(Qt.PointingHandCursor)
        self.boton_frente_fondo.setToolTip("De frente a fondo: el degradado va del color de frente al de fondo (y "
                                           "los sigue si cambian)")
        self.boton_frente_fondo.setText(" Frente → fondo")
        self.boton_frente_fondo.clicked.connect(lambda: self._avisar({"relleno": None}))
        capa.addWidget(self.boton_frente_fondo)
        capa.addSpacing(4)
        ayuda = "Opacidad del degradado"
        capa.addWidget(_etiqueta("Opacidad", ayuda))
        self.numero_opacidad = _numero(1, 100, 0, " %", ancho=54)
        self.numero_opacidad.setToolTip(ayuda)
        self.numero_opacidad.valueChanged.connect(lambda v: self._avisar({"opacidad": v / 100.0}))
        capa.addWidget(self.numero_opacidad)
        for w in (self.boton_lineal, self.boton_radial):
            w.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    @staticmethod
    def _boton_texto(texto: str, ayuda: str) -> QToolButton:
        b = QToolButton()
        b.setObjectName("botonOpcionPS")
        b.setText(texto)
        b.setToolButtonStyle(Qt.ToolButtonTextOnly)
        b.setCheckable(True)
        b.setAutoRaise(True)
        b.setFixedHeight(26)
        b.setToolTip(ayuda)
        b.setFocusPolicy(Qt.NoFocus)
        b.setCursor(Qt.PointingHandCursor)
        return b

    def mostrar(self, radial: bool, relleno: Relleno, de_frente_y_fondo: bool, opacidad: float) -> None:
        """``relleno``: el degradado que se usa (ya con los colores de frente y fondo si corresponde)."""
        self._cargando = True
        try:
            self.boton_lineal.setChecked(not radial)
            self.boton_radial.setChecked(bool(radial))
            from dataclasses import replace
            self.boton_relleno.establecer(replace(relleno, tipo="radial" if radial else "lineal"))
            self.boton_frente_fondo.setChecked(bool(de_frente_y_fondo))
            self.numero_opacidad.setValue(round(float(opacidad) * 100))
        finally:
            self._cargando = False

    def _avisar(self, cambios: dict) -> None:
        if not self._cargando:
            self.cambio.emit(cambios)


__all__ = ["CajaRecorte", "ControlesBote", "ControlesDegradado", "ControlesPincel", "Lienzo", "TrazoEnCurso",
           "como_rgba", "fundir_encima", "relleno_lineal_de_arrastre", "siguiente_tamano"]
