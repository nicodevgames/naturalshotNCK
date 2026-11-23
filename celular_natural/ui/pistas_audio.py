"""Pistas del modo Audio, dibujadas con QPainter: lo que se ve en el centro.

* ``OndaGrande``: la forma de onda grande de la voz (``PistaOnda`` con
  ``solo_resultado``), dentro de un área que se desplaza para el zoom.
* ``InvitacionAudio``: lo que se ve sin audio abierto ("Arrastrá un audio aquí").
* ``LineaVoz``: la pista **Voz** de la línea de tiempo. Es la ``LineaTiempo`` del
  editor de video (cortes, borrados con su marquita para recuperarlos, entrada y
  salida, tramo elegido y cursor) con la forma de onda en lugar de las miniaturas
  y los silencios en rosa.
* ``PistaFondo``: la pista **Fondo**, una franja que cubre todo el resultado con el
  nombre y el volumen de cada capa (y sus fundidos al principio y al final).
* ``PistaSonidos``: la pista **Sonidos**, un bloque por sonido suelto que se
  arrastra en el tiempo (al soltarlo pide un ancla nueva).

Tiempos, como en el editor de video: lo que entra y sale (cursor, anclas, pedidos)
va en el tiempo **original** de la voz; lo que se dibuja, en el del **resultado**
(``MapaTiempo``). Todas las pistas usan el mismo margen (``linea_tiempo.MARGEN``):
quedan alineadas una debajo de la otra. No editan nada: avisan lo que pidió el
usuario y el editor decide (así deshacer queda en un solo lugar).
"""

from __future__ import annotations

from typing import NamedTuple, Optional, Sequence

import numpy as np
from PySide6.QtCore import QEvent, QLineF, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QFrame, QScrollArea, QSizePolicy, QToolTip, QWidget

from ..motor.video import MapaTiempo
from . import estilo, iconos
from .forma_onda import PistaOnda, onda_en_resultado
from .linea_tiempo import ALTO_PIE, ALTO_REGLA, MARGEN, LineaTiempo, formato_tiempo

ALTO_TIRA_VOZ = 46     # la tira de la pista Voz (en video, la de las miniaturas mide 64)
ALTO_FONDO = 34
ALTO_SONIDOS = 44
ZOOMS = (1, 2, 4, 8)   # la onda grande: cuántas veces el ancho que se ve
COLOR_FONDO = QColor("#a78bfa")      # lavanda (el del modo Audio)
COLOR_SONIDO = QColor("#38bdf8")     # celeste
COLOR_FALTA = QColor(estilo.PUNTO)
COLOR_SILENCIO = QColor(estilo.ROSA)


def _fuente(widget: QWidget, puntos: float, negrita: bool = False) -> QFont:
    f = QFont(widget.font())
    f.setPointSizeF(puntos)
    f.setBold(negrita)
    return f


def _fondo_pista(p: QPainter, widget: QWidget) -> None:
    """El fondo redondeado de una pista (el mismo de la línea de tiempo y de la pista de sonido)."""
    p.setPen(QPen(QColor(estilo.BORDE), 1))
    p.setBrush(QColor("#313339"))
    p.drawRoundedRect(QRectF(widget.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)


# ======================================================================== onda grande
class OndaGrande(QScrollArea):
    """La forma de onda grande de la voz, con zoom.

    Adentro hay una ``PistaOnda`` (``pista``) que con zoom 1 mide lo que se ve y con
    zoom 2, 4 u 8 es más ancha: el área se desplaza a lo ancho. Ctrl + rueda cambia el
    zoom; la rueda sola, con zoom, se desplaza. ``seguir(t)`` mueve la vista para que se
    vea el instante ``t`` (tiempo original), por ejemplo al reproducir.
    """

    zoomCambiado = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ondaGrande")
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setMinimumHeight(90)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.pista = PistaOnda(solo_resultado=True)
        self.pista.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.pista.setToolTip("La voz: lo que se escucha y se exporta (sin lo borrado), con los silencios en rosa. "
                              "Tocá o arrastrá para moverte. Ctrl + rueda: zoom.")
        self.setWidget(self.pista)
        self._zoom = 1

    @property
    def zoom(self) -> int:
        return self._zoom

    def establecer_zoom(self, zoom: int, ancla: Optional[float] = None) -> None:
        """Cambia el zoom dejando quieto el punto ``ancla`` (x en el área; por defecto, el cursor)."""
        zoom = min(ZOOMS, key=lambda z: abs(z - zoom))
        if zoom == self._zoom:
            return
        barra = self.horizontalScrollBar()
        viejo_ancho = max(1, self.pista.width())
        if ancla is None:
            x_cursor = self.pista._x(self.pista._tiempo) - barra.value()
            ancla = x_cursor if 0 <= x_cursor <= self.viewport().width() else self.viewport().width() / 2
        fraccion = (barra.value() + ancla) / viejo_ancho
        self._zoom = zoom
        self._acomodar()
        barra.setValue(round(fraccion * self.pista.width() - ancla))
        self.zoomCambiado.emit(zoom)

    def acercar(self) -> None:
        mayores = [z for z in ZOOMS if z > self._zoom]
        if mayores:
            self.establecer_zoom(mayores[0])

    def alejar(self) -> None:
        menores = [z for z in ZOOMS if z < self._zoom]
        if menores:
            self.establecer_zoom(menores[-1])

    def ajustar(self) -> None:
        self.establecer_zoom(1)

    def _acomodar(self) -> None:
        vista = self.viewport()
        alto = max(40, vista.height())
        self.pista.setFixedSize(max(1, vista.width() * self._zoom), alto)

    def resizeEvent(self, evento) -> None:
        super().resizeEvent(evento)
        self._acomodar()

    def seguir(self, t: float) -> None:
        """Que se vea el instante ``t`` (tiempo original): si se fue de la vista, la vista lo alcanza."""
        if self._zoom == 1:
            return
        barra = self.horizontalScrollBar()
        x = self.pista._x(t)
        ancho = self.viewport().width()
        if x < barra.value() + 20 or x > barra.value() + ancho - 20:
            barra.setValue(round(x - ancho * 0.15))

    def wheelEvent(self, evento) -> None:
        if evento.modifiers() & Qt.ControlModifier:
            pasos = evento.angleDelta().y()
            if pasos > 0:
                mayores = [z for z in ZOOMS if z > self._zoom]
                if mayores:
                    self.establecer_zoom(mayores[0], evento.position().x())
            elif pasos < 0:
                menores = [z for z in ZOOMS if z < self._zoom]
                if menores:
                    self.establecer_zoom(menores[-1], evento.position().x())
            evento.accept()
            return
        if self._zoom > 1 and evento.angleDelta().y():
            barra = self.horizontalScrollBar()
            barra.setValue(barra.value() - evento.angleDelta().y())
            evento.accept()
            return
        super().wheelEvent(evento)


class InvitacionAudio(QWidget):
    """Sin audio abierto: un recuadro para soltar uno (o hacer clic y elegirlo)."""

    clic = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(90)
        self.setToolTip("Abrí un audio: una voz grabada o hecha con IA (MP3, M4A, WAV, OGG, OPUS, AAC o FLAC)")

    def mouseReleaseEvent(self, evento) -> None:
        if evento.button() == Qt.LeftButton and self.rect().contains(evento.position().toPoint()):
            self.clic.emit()
        super().mouseReleaseEvent(evento)

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        p.setPen(QPen(QColor("#464951"), 2, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, 16, 16)
        alto = rect.height()
        icono = 40 if alto > 200 else 28
        textos = [("Arrastrá un audio aquí", 15 if alto > 200 else 12.5, True, estilo.TEXTO),
                  ("o hacé clic para elegir un archivo  ·  MP3, M4A, WAV, OGG, OPUS, AAC, FLAC", 10.5, False,
                   estilo.TEXTO_TENUE),
                  ("Una voz grabada o hecha con IA. Si soltás fotos o videos, se abren en su modo.", 9.5, False,
                   estilo.TEXTO_TENUE)]
        if alto < 150:
            textos = textos[:2]
        alturas = [QFontMetrics(_fuente(self, t[1], t[2])).height() + 6 for t in textos]
        total = icono + 12 + sum(alturas)
        y = rect.center().y() - total / 2
        pm = iconos.pixmap("audio-lines", icono, estilo.TEXTO_TENUE)
        p.drawPixmap(QPointF(rect.center().x() - icono / 2, y), pm)
        y += icono + 12
        for (texto, puntos, negrita, color), h in zip(textos, alturas):
            f = _fuente(self, puntos, negrita)
            p.setFont(f)
            p.setPen(QColor(color))
            texto = QFontMetrics(f).elidedText(texto, Qt.ElideRight, int(rect.width() - 24))
            p.drawText(QRectF(rect.left(), y, rect.width(), h), Qt.AlignHCenter | Qt.AlignVCenter, texto)
            y += h
        p.end()


# ======================================================================== pista Voz
class LineaVoz(LineaTiempo):
    """La pista Voz: la línea de tiempo del editor de video con la forma de onda en la tira.

    Igual que ``LineaTiempo`` en todo lo demás (señales, cortes, marquitas, corchetes,
    menú de "Recuperar lo borrado"); la tira es más baja y muestra la voz de lo que se
    escucha, con los silencios en rosa."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._forma = None
        self._silencios: tuple = ()
        self._reducida: dict = {}
        self.setMinimumHeight(ALTO_REGLA + ALTO_TIRA_VOZ + ALTO_PIE + 4)

    def sizeHint(self) -> QSize:
        return QSize(640, ALTO_REGLA + ALTO_TIRA_VOZ + ALTO_PIE + 4)

    def _pista(self) -> QRectF:
        return QRectF(MARGEN, ALTO_REGLA + 4, max(1.0, self.width() - 2 * MARGEN), ALTO_TIRA_VOZ)

    def establecer_forma(self, forma) -> None:
        """La forma de onda de la voz (``FormaOnda``, parcial o completa) o None."""
        self._forma = forma
        self.update()

    def establecer_silencios(self, silencios: Sequence[tuple[float, float]]) -> None:
        silencios = tuple(silencios)
        if silencios != self._silencios:
            self._silencios = silencios
            self.update()

    def paintEvent(self, evento) -> None:
        if self._edicion is None:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing, True)
            _fondo_pista(p, self)
            p.setPen(QColor(estilo.TEXTO_TENUE))
            p.drawText(self.rect(), Qt.AlignCenter, "Abrí un audio para ver su línea de tiempo")
            p.end()
            return
        super().paintEvent(evento)

    def _dibujar_tira(self, p: QPainter, pista: QRectF) -> None:
        camino = QPainterPath()
        camino.addRoundedRect(pista, 8, 8)
        p.save()
        p.setClipPath(camino)
        grad = QLinearGradient(pista.topLeft(), pista.bottomLeft())
        grad.setColorAt(0, QColor("#3a3c43"))
        grad.setColorAt(1, QColor("#35373d"))
        p.fillRect(pista, grad)
        mapa, forma = self._mapa, self._forma
        if mapa is not None and mapa.duracion > 0 and forma is not None and forma.duracion > 0:
            n = max(1, int(round(pista.width())))
            clave = (id(forma), forma.listas, n, mapa)
            if self._reducida.get("clave") != clave:
                self._reducida = {"clave": clave, "datos": onda_en_resultado(forma, mapa, n)}
            minimos, maximos = self._reducida["datos"]
            medio, alto = pista.center().y(), pista.height() / 2 - 3
            # Hasta dónde se leyó (mientras carga, lo que falta queda vacío).
            centros = np.asarray(mapa.a_original((np.arange(n) + 0.5) * mapa.duracion / n))
            leido = forma.listas / max(1, forma.columnas) * forma.duracion
            listas = n if forma.completa else int(np.searchsorted(centros, leido, side="left"))
            silencio = np.zeros(n, bool)
            for a, b in self._silencios:
                silencio |= (centros >= a) & (centros < b)
            normal, callada = [], []
            for k in range(min(n, listas)):
                y1, y2 = medio - float(maximos[k]) * alto, medio - float(minimos[k]) * alto
                if y2 - y1 < 1.0:
                    y1, y2 = medio - 0.5, medio + 0.5
                (callada if silencio[k] else normal).append(QLineF(pista.left() + k + 0.5, y1, pista.left() + k + 0.5, y2))
            p.setRenderHint(QPainter.Antialiasing, False)
            if normal:
                p.setPen(QPen(QColor(196, 181, 253, 150), 1))
                p.drawLines(normal)
            if callada:
                p.setPen(QPen(QColor(150, 146, 162, 60), 1))
                p.drawLines(callada)
            p.setRenderHint(QPainter.Antialiasing, True)
            tinte = QColor(COLOR_SILENCIO)
            tinte.setAlpha(40)
            for a, b in self._silencios:
                for ra, rb in mapa.rangos_resultado(a, b):
                    p.fillRect(QRectF(self._x(ra), pista.top(), self._x(rb) - self._x(ra), pista.height()), tinte)
        p.restore()


# ======================================================================== pista Fondo
class CapaVista(NamedTuple):
    """Lo que la pista Fondo muestra de una capa."""
    icono: str
    nombre: str
    volumen: int          # %
    falta: bool = False


class _PistaBase(QWidget):
    """Lo común de las pistas Fondo y Sonidos: el mapa del tiempo, el cursor y tocar para moverse."""

    tiempoPedido = Signal(float, bool)   # segundos (tiempo original), ¿se sigue arrastrando?

    def __init__(self, alto: int, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(alto)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.NoFocus)
        self._alto = alto
        self._mapa: Optional[MapaTiempo] = None
        self._tiempo = 0.0
        self._moviendo_cursor = False

    def sizeHint(self) -> QSize:
        return QSize(640, self._alto)

    @property
    def mapa(self) -> Optional[MapaTiempo]:
        return self._mapa

    def establecer_mapa(self, mapa: Optional[MapaTiempo]) -> None:
        if mapa != self._mapa:
            self._mapa = mapa
            self.update()

    def establecer_tiempo(self, t: float) -> None:
        if t != self._tiempo:
            self._tiempo = t
            self.update()

    def _carril(self) -> QRectF:
        return QRectF(MARGEN, 4, max(1.0, self.width() - 2 * MARGEN), self.height() - 8)

    def _duracion(self) -> float:
        return max(1e-6, self._mapa.duracion) if self._mapa is not None else 1.0

    def x_de_resultado(self, r: float) -> float:
        c = self._carril()
        return c.left() + c.width() * max(0.0, min(1.0, r / self._duracion()))

    def resultado_en(self, x: float) -> float:
        c = self._carril()
        return max(0.0, min(self._duracion(), (x - c.left()) / c.width() * self._duracion()))

    def _original_en(self, x: float) -> float:
        if self._mapa is None or not self._mapa.tramos:
            return 0.0
        return float(self._mapa.a_original(min(self.resultado_en(x), max(0.0, self._duracion() - 1e-6))))

    def _dibujar_cursor(self, p: QPainter) -> None:
        if self._mapa is None or self._mapa.duracion <= 0:
            return
        c = self._carril()
        x = self.x_de_resultado(self._mapa.a_resultado(self._tiempo))
        p.setPen(QPen(QColor(255, 255, 255, 200), 1.5))
        p.drawLine(QPointF(x, c.top() - 3), QPointF(x, c.bottom() + 3))

    # Tocar un lugar vacío mueve el cursor (como la línea de tiempo).
    def _empezar_cursor(self, x: float) -> None:
        if self._mapa is None or self._mapa.duracion <= 0:
            return
        self._moviendo_cursor = True
        self.tiempoPedido.emit(self._original_en(x), True)

    def _seguir_cursor(self, x: float) -> None:
        if self._moviendo_cursor:
            self.tiempoPedido.emit(self._original_en(x), True)

    def _soltar_cursor(self, x: float) -> None:
        if self._moviendo_cursor:
            self._moviendo_cursor = False
            self.tiempoPedido.emit(self._original_en(x), False)


class PistaFondo(_PistaBase):
    """La pista Fondo: una franja que cubre todo el resultado, con el nombre y el volumen de
    cada capa. En los extremos se ven los fundidos (``fundido`` segundos del resultado)."""

    def __init__(self, parent=None):
        super().__init__(ALTO_FONDO, parent)
        self.setCursor(Qt.PointingHandCursor)
        self._capas: list[CapaVista] = []
        self._fundido = 0.3
        self.setToolTip("Fondo continuo: suena de punta a punta, con un fundido al principio y al final. "
                        "Se elige y se ajusta a la derecha, en «Fondo continuo».")

    @property
    def capas(self) -> list[CapaVista]:
        return list(self._capas)

    def establecer(self, capas: Sequence[CapaVista], fundido: float = 0.3) -> None:
        capas = list(capas)
        if capas != self._capas or fundido != self._fundido:
            self._capas, self._fundido = capas, float(fundido)
            self.update()

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        _fondo_pista(p, self)
        c = self._carril()
        if self._mapa is None:
            p.end()
            return
        if not self._capas:
            p.setPen(QPen(QColor("#4a4d55"), 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(c.adjusted(0.5, 0.5, -0.5, -0.5), 7, 7)
            p.setFont(_fuente(self, 8.5))
            p.setPen(QColor(estilo.TEXTO_TENUE))
            texto = p.fontMetrics().elidedText("Sin fondo: elegí uno a la derecha, en «Fondo continuo»",
                                               Qt.ElideRight, int(c.width() - 16))
            p.drawText(c, Qt.AlignCenter, texto)
            self._dibujar_cursor(p)
            p.end()
            return
        # La franja, con los fundidos de los extremos.
        camino = QPainterPath()
        camino.addRoundedRect(c, 7, 7)
        p.save()
        p.setClipPath(camino)
        grad = QLinearGradient(c.topLeft(), c.topRight())
        color = QColor(COLOR_FONDO)
        rampa = min(0.5, self._fundido / self._duracion()) if self._fundido > 0 else 0.0
        for posicion, alfa in ((0.0, 10), (rampa, 70), (1.0 - rampa, 70), (1.0, 10)):
            color.setAlpha(alfa)
            grad.setColorAt(max(0.0, min(1.0, posicion)), color)
        p.fillRect(c, grad)
        # Cada capa: una píldora con su ícono, su nombre y su volumen.
        f = _fuente(self, 8.5, True)
        p.setFont(f)
        fm = QFontMetrics(f)
        x = c.left() + 6
        alto = min(20.0, c.height() - 6)
        y = c.center().y() - alto / 2
        for i, capa in enumerate(self._capas):
            texto = f"{capa.nombre} · {capa.volumen} %" + (" · falta" if capa.falta else "")
            ancho = fm.horizontalAdvance(texto) + 36
            restantes = len(self._capas) - i
            if x + ancho > c.right() - 6:
                ancho = c.right() - 6 - x - (30 if restantes > 1 else 0)
                if ancho < 60:
                    resto = f"+{restantes}"
                    caja = QRectF(x, y, fm.horizontalAdvance(resto) + 14, alto)
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(43, 45, 50, 220))
                    p.drawRoundedRect(caja, alto / 2, alto / 2)
                    p.setPen(QColor(estilo.TEXTO_2))
                    p.drawText(caja, Qt.AlignCenter, resto)
                    break
            caja = QRectF(x, y, ancho, alto)
            p.setPen(QPen(COLOR_FALTA if capa.falta else QColor(196, 181, 253, 160), 1))
            p.setBrush(QColor(43, 45, 50, 225))
            p.drawRoundedRect(caja, alto / 2, alto / 2)
            p.drawPixmap(QPointF(caja.left() + 7, caja.center().y() - 6),
                         iconos.pixmap(capa.icono, 12, COLOR_FALTA.name() if capa.falta else "#c4b5fd"))
            p.setPen(QColor("#fca5a5" if capa.falta else estilo.TEXTO))
            p.drawText(caja.adjusted(24, 0, -8, 0), Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(texto, Qt.ElideRight, int(caja.width() - 32)))
            x += ancho + 6
        p.restore()
        self._dibujar_cursor(p)
        p.end()

    def mousePressEvent(self, evento) -> None:
        if evento.button() == Qt.LeftButton:
            self._empezar_cursor(evento.position().x())

    def mouseMoveEvent(self, evento) -> None:
        if self._moviendo_cursor and not (evento.buttons() & Qt.LeftButton):
            self._soltar_cursor(evento.position().x())
            return
        self._seguir_cursor(evento.position().x())

    def mouseReleaseEvent(self, evento) -> None:
        if evento.button() == Qt.LeftButton:
            self._soltar_cursor(evento.position().x())


# ======================================================================== pista Sonidos
class BloqueSonido(NamedTuple):
    """Un sonido suelto en la pista: dónde empieza (segundo del resultado) y cuánto dura."""
    inicio: float
    duracion: float
    nombre: str
    icono: str
    falta: bool = False


CARRILES_MAX = 3


class PistaSonidos(_PistaBase):
    """La pista Sonidos: un bloque por sonido suelto, que se arrastra en el tiempo.

    Suena entero desde su comienzo (los cortes de la voz no lo recortan; el final del
    resultado, sí). Si dos se pisan, van en carriles distintos. Tocar un bloque lo elige
    (``elegido``); arrastrarlo lo mueve y, al soltar, ``anclaPedida(indice, ancla)`` con
    el ancla nueva en tiempo original. Tocar fuera de los bloques mueve el cursor.
    """

    anclaPedida = Signal(int, float)   # índice del sonido, ancla nueva (tiempo original)
    elegido = Signal(int)              # se tocó un bloque (-1: ninguno)

    def __init__(self, parent=None):
        super().__init__(ALTO_SONIDOS, parent)
        self.setMouseTracking(True)
        self._bloques: list[BloqueSonido] = []
        self._carriles: list[int] = []
        self._seleccion = -1
        self._arrastre: Optional[tuple[int, float, float]] = None   # (índice, x al apretar, inicio original)
        self._inicio_arrastre: Optional[float] = None               # dónde va el bloque (segundo del resultado)
        self._movio = False
        self.setToolTip("Sonidos sueltos: arrastrá un bloque para moverlo en el tiempo. Se agregan a la derecha, "
                        "con «Agregar en el cursor».")

    # ------------------------------------------------------------- datos
    @property
    def bloques(self) -> list[BloqueSonido]:
        return list(self._bloques)

    @property
    def seleccion(self) -> int:
        return self._seleccion

    def establecer(self, bloques: Sequence[BloqueSonido]) -> None:
        bloques = list(bloques)
        if bloques != self._bloques:
            self._bloques = bloques
            self._carriles = self._repartir(bloques)
            if self._seleccion >= len(bloques):
                self._seleccion = -1
            if self._arrastre is not None and self._arrastre[0] >= len(bloques):
                self._arrastre, self._inicio_arrastre = None, None
            self.update()

    def seleccionar(self, indice: int) -> None:
        indice = indice if 0 <= indice < len(self._bloques) else -1
        if indice != self._seleccion:
            self._seleccion = indice
            self.update()

    @staticmethod
    def _repartir(bloques: Sequence[BloqueSonido]) -> list[int]:
        """Carril de cada bloque: el primero libre (los que se pisan van uno debajo del otro)."""
        fines: list[float] = []
        carriles = [0] * len(bloques)
        for i in sorted(range(len(bloques)), key=lambda k: bloques[k].inicio):
            b = bloques[i]
            libre = next((k for k, fin in enumerate(fines) if b.inicio >= fin - 1e-9), None)
            if libre is None:
                if len(fines) < CARRILES_MAX:
                    fines.append(0.0)
                    libre = len(fines) - 1
                else:
                    libre = min(range(len(fines)), key=lambda k: fines[k])
            fines[libre] = max(fines[libre], b.inicio + b.duracion)
            carriles[i] = libre
        return carriles

    def rect_bloque(self, i: int) -> QRectF:
        """Dónde se dibuja el bloque ``i`` (mientras se arrastra, donde va)."""
        b = self._bloques[i]
        inicio = self._inicio_arrastre if self._arrastre is not None and self._arrastre[0] == i else b.inicio
        c = self._carril()
        n = max(1, max(self._carriles, default=0) + 1)
        alto = (c.height() - 2 * (n - 1)) / n
        y = c.top() + self._carriles[i] * (alto + 2)
        x0 = self.x_de_resultado(inicio)
        x1 = self.x_de_resultado(min(self._duracion(), inicio + b.duracion))
        return QRectF(x0, y, max(8.0, x1 - x0), alto)

    def bloque_en(self, pos: QPointF) -> int:
        """El bloque que se toca en ``pos`` (el de más arriba si se pisan), o -1."""
        for i in reversed(range(len(self._bloques))):
            if self.rect_bloque(i).adjusted(-2, -2, 2, 2).contains(pos):
                return i
        return -1

    # ------------------------------------------------------------- dibujo
    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        _fondo_pista(p, self)
        c = self._carril()
        if self._mapa is None:
            p.end()
            return
        if not self._bloques:
            p.setPen(QPen(QColor("#4a4d55"), 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(c.adjusted(0.5, 0.5, -0.5, -0.5), 7, 7)
            p.setFont(_fuente(self, 8.5))
            p.setPen(QColor(estilo.TEXTO_TENUE))
            texto = p.fontMetrics().elidedText("Sin sonidos sueltos: llevá el cursor y tocá «Agregar en el cursor», "
                                               "a la derecha", Qt.ElideRight, int(c.width() - 16))
            p.drawText(c, Qt.AlignCenter, texto)
            self._dibujar_cursor(p)
            p.end()
            return
        f = _fuente(self, 8, True)
        p.setFont(f)
        fm = QFontMetrics(f)
        orden = [i for i in range(len(self._bloques)) if i != self._seleccion] + (
            [self._seleccion] if self._seleccion >= 0 else [])
        for i in orden:
            b = self._bloques[i]
            rect = self.rect_bloque(i)
            elegido = i == self._seleccion
            arrastrado = self._arrastre is not None and self._arrastre[0] == i
            base = COLOR_FALTA if b.falta else COLOR_SONIDO
            relleno = QColor(base)
            relleno.setAlpha(150 if (elegido or arrastrado) else 95)
            p.setPen(QPen(QColor(estilo.MAGENTA) if elegido else base.lighter(130), 2 if elegido else 1))
            p.setBrush(relleno)
            p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
            if rect.width() > 22 and rect.height() >= 12:
                lado = 12 if rect.height() >= 16 else 9
                p.drawPixmap(QPointF(rect.left() + 5, rect.center().y() - lado / 2),
                             iconos.pixmap(b.icono, lado, "#ffffff"))
                texto = b.nombre + (" · falta" if b.falta else "")
                ancho = int(rect.width() - lado - 12)
                if ancho > 18 and rect.height() >= 13:
                    p.setPen(QColor("#ffffff"))
                    p.drawText(QRectF(rect.left() + lado + 9, rect.top(), ancho, rect.height()),
                               Qt.AlignLeft | Qt.AlignVCenter, fm.elidedText(texto, Qt.ElideRight, ancho))
        self._dibujar_cursor(p)
        if self._arrastre is not None and self._inicio_arrastre is not None and self._movio:
            self._burbuja(p, self.rect_bloque(self._arrastre[0]).left(), formato_tiempo(self._inicio_arrastre))
        p.end()

    def _burbuja(self, p: QPainter, x: float, texto: str) -> None:
        f = _fuente(self, 8, True)
        p.setFont(f)
        fm = QFontMetrics(f)
        ancho, alto = fm.horizontalAdvance(texto) + 12, fm.height() + 4
        izquierda = max(2.0, min(self.width() - ancho - 2.0, x - ancho / 2))
        rect = QRectF(izquierda, 1, ancho, alto)
        p.setPen(QPen(QColor(estilo.BORDE_SELECCION), 1))
        p.setBrush(QColor(20, 10, 18, 230))
        p.drawRoundedRect(rect, alto / 2, alto / 2)
        p.setPen(QColor("#ffffff"))
        p.drawText(rect, Qt.AlignCenter, texto)

    # ------------------------------------------------------------- eventos
    def event(self, evento) -> bool:
        if evento.type() == QEvent.ToolTip:
            i = self.bloque_en(QPointF(evento.pos()))
            if i >= 0:
                b = self._bloques[i]
                texto = f"{b.nombre}: empieza en {formato_tiempo(b.inicio)}. Arrastralo para moverlo."
                if b.falta:
                    texto = f"{b.nombre}: falta el archivo (no suena). Quitalo o volvé a ponerlo en Mis sonidos."
                QToolTip.showText(evento.globalPos(), texto, self)
                return True
        return super().event(evento)

    def mousePressEvent(self, evento) -> None:
        if evento.button() != Qt.LeftButton or self._mapa is None:
            return
        pos = evento.position()
        i = self.bloque_en(pos)
        if i < 0:
            self.seleccionar(-1)
            self.elegido.emit(-1)
            self._empezar_cursor(pos.x())
            return
        self._arrastre = (i, pos.x(), self._bloques[i].inicio)
        self._inicio_arrastre = self._bloques[i].inicio
        self._movio = False
        self.seleccionar(i)
        self.setCursor(Qt.ClosedHandCursor)
        self.update()

    def mouseMoveEvent(self, evento) -> None:
        pos = evento.position()
        if self._arrastre is not None:
            if not (evento.buttons() & Qt.LeftButton):
                self.terminar_arrastre()  # el soltar se perdió
                return
            i, x0, inicio = self._arrastre
            if abs(pos.x() - x0) >= 3:
                self._movio = True
            por_px = self._duracion() / max(1.0, self._carril().width())
            self._inicio_arrastre = max(0.0, min(self._duracion(), inicio + (pos.x() - x0) * por_px))
            self.update()
            return
        if self._moviendo_cursor:
            if not (evento.buttons() & Qt.LeftButton):
                self._soltar_cursor(pos.x())
            else:
                self._seguir_cursor(pos.x())
            return
        self.setCursor(Qt.OpenHandCursor if self.bloque_en(pos) >= 0 else Qt.PointingHandCursor)

    def mouseReleaseEvent(self, evento) -> None:
        if evento.button() != Qt.LeftButton:
            return
        if self._arrastre is not None:
            self.terminar_arrastre(soltado=True)
            return
        self._soltar_cursor(evento.position().x())

    def terminar_arrastre(self, soltado: bool = False) -> None:
        """Termina un arrastre: si el bloque se movió, pide el ancla nueva. Un arrastre cuyo
        soltar se perdió (un cuadro de diálogo en medio) también deja el bloque donde iba."""
        if self._arrastre is None:
            return
        i, _x0, _inicio = self._arrastre
        nuevo, movio = self._inicio_arrastre, self._movio
        self._arrastre, self._inicio_arrastre, self._movio = None, None, False
        self.setCursor(Qt.OpenHandCursor)
        self.update()
        if movio and nuevo is not None and self._mapa is not None and self._mapa.tramos:
            r = min(nuevo, max(0.0, self._duracion() - 1e-6))
            self.anclaPedida.emit(i, float(self._mapa.a_original(r)))
        elif soltado:
            self.elegido.emit(i)

    def leaveEvent(self, evento) -> None:
        if self._arrastre is not None and not (QApplication.mouseButtons() & Qt.LeftButton):
            self.terminar_arrastre()
        super().leaveEvent(evento)

    def focusOutEvent(self, evento) -> None:
        self.terminar_arrastre()
        super().focusOutEvent(evento)


__all__ = ["OndaGrande", "InvitacionAudio", "LineaVoz", "PistaFondo", "PistaSonidos", "CapaVista", "BloqueSonido",
           "ZOOMS", "ALTO_TIRA_VOZ"]
