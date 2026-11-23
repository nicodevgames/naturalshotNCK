"""Herramienta Mover / Transformar: manijas sobre una capa, en la vista.

No es un widget: ``VistaComparacion`` (o el controlador del modo Photoshop) le pasa el mouse y el
teclado (en coordenadas de la imagen mostrada, que son los píxeles del documento) y le pide que se
dibuje. Trabaja sobre una ``Transformacion`` del motor (``motor/documento.py``): centro, escala
horizontal (``escala``) y vertical (``escala_y``), rotación y volteos.

Qué se puede hacer
------------------
* **Mover:** arrastrar adentro del recuadro. Con **Mayús**, solo en horizontal o en vertical.
  Con las flechas, de a 1 píxel del documento (con Mayús, de a 10). Con ``ajustar_mover`` (el
  imán del modo Photoshop), la capa se pega al centro y a los bordes del lienzo y de las otras
  capas, y quedan ``guias`` para dibujar (líneas magenta).
* **Escalar:** las manijas de las esquinas y de los lados. **Escala libre**: las esquinas cambian
  el ancho y el alto por separado y los lados, solo uno; con **Mayús**, una esquina mantiene la
  proporción (como pide el diseño de la Etapa 2). La esquina o el lado opuesto queda fijo; con
  **Alt**, se escala desde el centro.
* **Rotar:** la manija redonda de arriba, o arrastrando un poco afuera de una esquina (como
  en Photoshop). Con **Mayús**, de a 15°.
* **Voltear:** ``voltear()`` (horizontal) y ``voltear_v()`` (vertical).

Enter aplica y Esc cancela (los maneja la ventana) en la transformación libre: todo lo que se hizo
entre que se eligió la herramienta y Enter queda como **un solo paso** del historial.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Callable, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF

from ..motor.documento import Transformacion, esquinas
from . import estilo

LADO_MANIJA = 9.0         # px de pantalla
RADIO_TOQUE = 9.0         # px de pantalla alrededor de una manija que la agarran
DIST_ROTACION = 30.0      # px de pantalla entre el borde de arriba y la manija de rotación
FRANJA_ROTAR = 22.0       # px de pantalla afuera de una esquina que rotan
ESCALA_MIN = 0.002
PASO_ROTACION = 15.0      # grados, con Mayús

# Manijas en coordenadas locales de la imagen (centro = 0, en unidades de medio lado).
_LOCALES = {
    "no": (-1, -1), "n": (0, -1), "ne": (1, -1), "e": (1, 0),
    "se": (1, 1), "s": (0, 1), "so": (-1, 1), "o": (-1, 0),
}


def _giro(grados: float) -> tuple[float, float]:
    r = math.radians(grados)
    return math.cos(r), math.sin(r)


class HerramientaTransformar:
    """Estado de una transformación en curso (ver el módulo)."""

    def __init__(self, transform: Transformacion, ancho_img: int, alto_img: int,
                 ajustar_mover: Optional[Callable] = None):
        """``ajustar_mover(t0, t)``: el imán (opcional). Recibe la transformación al empezar a mover y
        la que pide el mouse, y devuelve (transformación ajustada, guías)."""
        self.original = transform
        self.transform = transform
        self.iw, self.ih = max(1, int(ancho_img)), max(1, int(alto_img))
        self._manija: Optional[str] = None
        self._t0 = transform
        self._p0 = QPointF()
        self.ajustar_mover = ajustar_mover
        self.guias: list = []  # las del imán mientras se mueve: ("v", x, y0, y1) o ("h", y, x0, x1)

    # ------------------------------------------------------------ geometría
    def _unidad(self, t: Optional[Transformacion] = None):
        """La parte lineal sin escala (giro y volteos): (a, b, c, d) de [[a, b], [c, d]] = R·diag(±1, ±1)."""
        t = t or self.transform
        c, s = _giro(t.rotacion)
        fh = -1.0 if t.voltear_h else 1.0
        fv = -1.0 if t.voltear_v else 1.0
        return c * fh, -s * fv, s * fh, c * fv

    def _local_a_doc(self, lx: float, ly: float, t: Optional[Transformacion] = None) -> QPointF:
        """Un punto local (en píxeles de la imagen, centro = 0) en coordenadas del documento."""
        t = t or self.transform
        a, b, c, d = self._unidad(t)
        sx, sy = t.escala, t.escala_vertical
        return QPointF(t.x + a * lx * sx + b * ly * sy, t.y + c * lx * sx + d * ly * sy)

    def _doc_a_local(self, p: QPointF, t: Optional[Transformacion] = None) -> tuple[float, float]:
        t = t or self.transform
        a, b, c, d = self._unidad(t)
        dx, dy = p.x() - t.x, p.y() - t.y
        # La inversa de un giro con volteos es su transpuesta; después, cada escala.
        return (a * dx + c * dy) / t.escala, (b * dx + d * dy) / t.escala_vertical

    def esquinas(self) -> list[QPointF]:
        """Arriba-izquierda, arriba-derecha, abajo-derecha y abajo-izquierda (de la imagen)."""
        return [QPointF(float(x), float(y)) for x, y in esquinas(self.transform, self.iw, self.ih)]

    def manijas(self, zoom: float) -> dict[str, QPointF]:
        """Cada manija en coordenadas del documento, más "rotar" (la de arriba, redonda)."""
        salida = {n: self._local_a_doc(u * self.iw / 2, v * self.ih / 2) for n, (u, v) in _LOCALES.items()}
        arriba = salida["n"]
        a, b, c, d = self._unidad()
        # "Arriba" de la imagen (0, -1) en el documento, en píxeles de pantalla.
        ux, uy = -b, -d
        largo = math.hypot(ux, uy) or 1.0
        salida["rotar"] = QPointF(arriba.x() + ux / largo * DIST_ROTACION / zoom,
                                  arriba.y() + uy / largo * DIST_ROTACION / zoom)
        return salida

    def _adentro(self, p: QPointF) -> bool:
        lx, ly = self._doc_a_local(p)
        return abs(lx) <= self.iw / 2 and abs(ly) <= self.ih / 2

    def manija_en(self, p: QPointF, zoom: float) -> Optional[str]:
        """Qué se agarra en ``p`` (coordenadas del documento): una manija, "rotar", "mover"
        (adentro), "rotar" (apenas afuera de una esquina) o None (lejos: desplaza la vista)."""
        radio = RADIO_TOQUE / max(zoom, 1e-6)
        manijas = self.manijas(zoom)
        cercana = min(manijas, key=lambda n: (manijas[n].x() - p.x()) ** 2 + (manijas[n].y() - p.y()) ** 2)
        q = manijas[cercana]
        if math.hypot(q.x() - p.x(), q.y() - p.y()) <= radio:
            return cercana
        if self._adentro(p):
            return "mover"
        franja = FRANJA_ROTAR / max(zoom, 1e-6)
        for n in ("no", "ne", "se", "so"):
            q = manijas[n]
            if math.hypot(q.x() - p.x(), q.y() - p.y()) <= franja:
                return "rotar"
        return None

    @staticmethod
    def cursor(manija: Optional[str], rotacion: float = 0.0) -> Qt.CursorShape:
        if manija == "mover":
            return Qt.SizeAllCursor
        if manija == "rotar":
            return Qt.CrossCursor
        if manija is None:
            return Qt.OpenHandCursor
        # La flecha de tamaño según hacia dónde apunta la manija (con la capa girada).
        u, v = _LOCALES[manija]
        angulo = (math.degrees(math.atan2(v, u)) + rotacion) % 180.0
        if angulo < 22.5 or angulo >= 157.5:
            return Qt.SizeHorCursor
        if angulo < 67.5:
            return Qt.SizeFDiagCursor
        if angulo < 112.5:
            return Qt.SizeVerCursor
        return Qt.SizeBDiagCursor

    # ------------------------------------------------------------ arrastrar
    @property
    def arrastrando(self) -> bool:
        return self._manija is not None

    def empezar(self, manija: str, p: QPointF) -> None:
        self._manija = manija
        self._t0 = self.transform
        self._p0 = QPointF(p)

    def arrastrar(self, p: QPointF, mayus: bool = False, alt: bool = False) -> Transformacion:
        """La transformación con el mouse en ``p`` (coordenadas del documento)."""
        m, t0 = self._manija, self._t0
        if m is None:
            return self.transform
        if m == "mover":
            dx, dy = p.x() - self._p0.x(), p.y() - self._p0.y()
            if mayus:  # solo en el eje en que más se movió
                if abs(dx) >= abs(dy):
                    dy = 0.0
                else:
                    dx = 0.0
            t = replace(t0, x=t0.x + dx, y=t0.y + dy)
            self.guias = []
            if self.ajustar_mover is not None:
                t, self.guias = self.ajustar_mover(t0, t)
                if mayus:  # el imán no saca la capa del eje elegido
                    t = replace(t, y=t0.y) if dy == 0.0 else replace(t, x=t0.x)
            self.transform = t
        elif m == "rotar":
            a0 = math.atan2(self._p0.y() - t0.y, self._p0.x() - t0.x)
            a1 = math.atan2(p.y() - t0.y, p.x() - t0.x)
            rot = t0.rotacion + math.degrees(a1 - a0)
            if mayus:
                rot = round(rot / PASO_ROTACION) * PASO_ROTACION
            rot = (rot + 180.0) % 360.0 - 180.0
            self.transform = replace(t0, rotacion=float(rot))
        else:
            u, v = _LOCALES[m]
            cl = (u * self.iw / 2, v * self.ih / 2)          # la manija (local)
            al = (0.0, 0.0) if alt else (-cl[0], -cl[1])     # lo que queda fijo (local)
            a, b, c, d = self._unidad(t0)
            sx0, sy0 = t0.escala, t0.escala_vertical
            fijo = self._local_a_doc(al[0], al[1], t0)       # el punto fijo, en el documento
            vx, vy = cl[0] - al[0], cl[1] - al[1]            # de lo fijo a la manija (local, sin escala)
            ex, ey = p.x() - fijo.x(), p.y() - fijo.y()
            if mayus and u != 0 and v != 0:
                # Esquina con Mayús: la proporción de antes (un solo factor sobre las dos escalas).
                wx, wy = a * vx * sx0 + b * vy * sy0, c * vx * sx0 + d * vy * sy0
                k = (ex * wx + ey * wy) / max(wx * wx + wy * wy, 1e-12)
                k = max(ESCALA_MIN / max(min(sx0, sy0), 1e-12), k)
                sx, sy = sx0 * k, sy0 * k
            else:
                # Libre: el mouse en los ejes de la capa da cada escala (un lado cambia una sola).
                lx, ly = a * ex + c * ey, b * ex + d * ey
                sx = max(ESCALA_MIN, lx / vx) if vx else sx0
                sy = max(ESCALA_MIN, ly / vy) if vy else sy0
            # El centro nuevo: el punto fijo menos lo fijo (local) con las escalas nuevas.
            cx = fijo.x() - (a * al[0] * sx + b * al[1] * sy)
            cy = fijo.y() - (c * al[0] * sx + d * al[1] * sy)
            escala_y = None if (t0.escala_y is None and abs(sx - sy) <= 1e-9 * max(sx, 1.0)) else float(sy)
            self.transform = replace(t0, x=float(cx), y=float(cy), escala=float(sx), escala_y=escala_y)
        return self.transform

    def soltar(self) -> None:
        self._manija = None
        self.guias = []

    def mover(self, dx: float, dy: float) -> Transformacion:
        """Con las flechas: ``dx``, ``dy`` en píxeles del documento."""
        t = self.transform
        self.transform = replace(t, x=t.x + dx, y=t.y + dy)
        return self.transform

    def voltear(self) -> Transformacion:
        """Espejo horizontal (en el eje de la imagen), en el mismo lugar."""
        self.transform = replace(self.transform, voltear_h=not self.transform.voltear_h)
        return self.transform

    def voltear_v(self) -> Transformacion:
        """Espejo vertical (en el eje de la imagen), en el mismo lugar."""
        self.transform = replace(self.transform, voltear_v=not self.transform.voltear_v)
        return self.transform

    @property
    def cambio(self) -> bool:
        return self.transform != self.original

    # ------------------------------------------------------------ dibujo
    def texto(self) -> str:
        """"120 %  ·  15°" (o "120 × 80 %" con escala libre), para la barra y la etiqueta."""
        t = self.transform
        rot = f"{t.rotacion:+.1f}°".replace(".", ",").replace("+0,0°", "0°").replace("-0,0°", "0°")
        if t.escala_y is None or abs(t.escala_y - t.escala) < 5e-4:
            tam = f"{t.escala * 100:.0f} %"
        else:
            tam = f"{t.escala * 100:.0f} × {t.escala_y * 100:.0f} %"
        partes = [tam, rot]
        if t.voltear_h and t.voltear_v:
            partes.append("volteada H y V")
        elif t.voltear_h:
            partes.append("volteada")
        elif t.voltear_v:
            partes.append("volteada V")
        return "  ·  ".join(partes)

    def dibujar(self, p: QPainter, a_pantalla: Callable[[QPointF], QPointF], zoom: float) -> None:
        """El recuadro, las manijas y la de rotación, sobre la vista (``a_pantalla``: del
        documento a la pantalla)."""
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        caja = QPolygonF([a_pantalla(q) for q in self.esquinas()])
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 150), 3))
        p.drawPolygon(caja)
        p.setPen(QPen(QColor("#ffffff"), 1.4))
        p.drawPolygon(caja)
        manijas = {n: a_pantalla(q) for n, q in self.manijas(zoom).items()}
        # Palito y manija de rotación.
        p.setPen(QPen(QColor("#ffffff"), 1.2))
        p.drawLine(manijas["n"], manijas["rotar"])
        p.setPen(QPen(QColor(estilo.MAGENTA), 2))
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(manijas["rotar"], LADO_MANIJA / 2 + 1, LADO_MANIJA / 2 + 1)
        # Manijas cuadradas (esquinas y lados).
        medio = LADO_MANIJA / 2
        for n in _LOCALES:
            q = manijas[n]
            p.drawRect(QRectF(q.x() - medio, q.y() - medio, LADO_MANIJA, LADO_MANIJA))
        # Centro.
        c = a_pantalla(QPointF(self.transform.x, self.transform.y))
        p.setPen(QPen(QColor(0, 0, 0, 150), 3))
        p.drawLine(c + QPointF(-5, 0), c + QPointF(5, 0))
        p.drawLine(c + QPointF(0, -5), c + QPointF(0, 5))
        p.setPen(QPen(QColor("#ffffff"), 1.2))
        p.drawLine(c + QPointF(-5, 0), c + QPointF(5, 0))
        p.drawLine(c + QPointF(0, -5), c + QPointF(0, 5))
        # Etiqueta con la escala y la rotación, debajo del recuadro.
        abajo = max(caja, key=lambda q: q.y())
        fuente = QFont(p.font())
        fuente.setPointSizeF(8.5)
        fuente.setBold(True)
        p.setFont(fuente)
        texto = self.texto()
        m = p.fontMetrics()
        rect = QRectF(abajo.x() - (m.horizontalAdvance(texto) + 14) / 2, abajo.y() + 12,
                      m.horizontalAdvance(texto) + 14, m.height() + 6)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20, 10, 18, 210))
        p.drawRoundedRect(rect, 5, 5)
        p.setPen(QColor("#ffffff"))
        p.drawText(rect, Qt.AlignCenter, texto)
        p.restore()
        dibujar_guias(p, self.guias, a_pantalla)


COLOR_GUIA = "#ff2bd6"  # magenta de las guías inteligentes (como Photoshop)


def dibujar_guias(p: QPainter, guias, a_pantalla: Callable[[QPointF], QPointF]) -> None:
    """Las guías inteligentes (del imán): ("v", x, y0, y1) es una línea vertical en x, de y0 a y1, y
    ("h", y, x0, x1) una horizontal; todo en píxeles del documento."""
    if not guias:
        return
    p.save()
    p.setRenderHint(QPainter.Antialiasing, False)
    p.setPen(QPen(QColor(COLOR_GUIA), 1))
    for tipo, pos, desde, hasta in guias:
        if tipo == "v":
            p.drawLine(a_pantalla(QPointF(pos, desde)), a_pantalla(QPointF(pos, hasta)))
        else:
            p.drawLine(a_pantalla(QPointF(desde, pos)), a_pantalla(QPointF(hasta, pos)))
    p.restore()


__all__ = ["COLOR_GUIA", "HerramientaTransformar", "dibujar_guias"]
