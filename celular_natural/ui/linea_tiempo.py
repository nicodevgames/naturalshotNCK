"""Línea de tiempo del editor de video, dibujada con QPainter.

Muestra **el resultado**: lo que se va a exportar, de corrido. Lo borrado y lo
recortado (antes de la entrada y después de la salida) no se dibuja, y lo que
sigue se corre para cerrar el hueco, como en los editores de los celulares. En
cada unión donde faltaba algo queda una marquita finita: tocarla (o el menú del
botón derecho) ofrece **"Recuperar lo borrado"**.

Dibuja la regla y el cursor en el tiempo del resultado, la tira de miniaturas
(cada tramo conservado empieza su propia tira, así lo que seguía a un borrado
arranca justo en la unión), los cortes, las marquitas, el tramo elegido y la
entrada y la salida: dos corchetes en los extremos que se arrastran hacia
adentro para recortar más.

Tiempos: todo lo que entra y sale (``establecer_tiempo``, ``tiempoPedido``,
``limitesPedidos``, las miniaturas) va en el tiempo ORIGINAL del archivo, como
``EdicionVideo``. La conversión al resultado es cosa de la línea
(``motor.video.MapaTiempo``). No edita por su cuenta: avisa lo que pidió el
usuario y el editor decide (así deshacer y rehacer quedan en un solo lugar).
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QMenu, QSizePolicy, QToolTip, QWidget

from ..motor.video import EdicionVideo, Hueco, MapaTiempo, segmentos_visibles
from . import estilo, iconos

ALTO_REGLA = 22
ALTO_TIRA = 64
ALTO_PIE = 18     # debajo de la tira: las pestañas de las marquitas (para tocarlas)
MARGEN = 14       # a los costados, para poder agarrar las marcas en los extremos
DISTANCIA_MARCA = 8   # píxeles para agarrar la entrada o la salida
DISTANCIA_UNION = 4   # píxeles a cada lado de la línea de una marquita, dentro de la tira
ANCHO_PESTANA = 16
ALTO_PESTANA = 11
PASOS_REGLA = (0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1200, 3600)


def formato_tiempo(segundos: float, decimas: bool = True) -> str:
    """'1:05,40' (minutos:segundos,centésimas) o '1:05' sin decimales."""
    segundos = max(0.0, segundos)
    if decimas:
        centesimas = int(round(segundos * 100))
        m, resto = divmod(centesimas, 6000)
        s, c = divmod(resto, 100)
        h, m = divmod(m, 60)
        return (f"{h}:{m:02d}:{s:02d},{c:02d}" if h else f"{m}:{s:02d},{c:02d}")
    total = int(round(segundos))
    m, s = divmod(total, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def formato_duracion(segundos: float) -> str:
    """Una duración corta para los textos: '0,5 s', '12,3 s' o, desde un minuto, '1:05'."""
    if segundos >= 60:
        return formato_tiempo(segundos, decimas=False)
    return f"{segundos:.1f} s".replace(".", ",")


def texto_hueco(hueco: Hueco) -> str:
    """Qué falta en una unión, para el menú y la ayuda de la marquita."""
    largo = formato_duracion(hueco.duracion)
    if hueco.principio and hueco.final:
        return f"Está todo borrado ({largo})"
    if hueco.principio:
        return f"Recortado del principio: {largo}"
    if hueco.final:
        return f"Recortado del final: {largo}"
    return f"Borrado acá: {largo}"


class LineaTiempo(QWidget):
    tiempoPedido = Signal(float, bool)       # segundos (tiempo original), ¿se sigue arrastrando?
    seleccionCambiada = Signal(int)          # índice del segmento elegido (-1 = ninguno)
    limitesPedidos = Signal(float, object)   # entrada, salida (None = hasta el final), al soltar una marca
    recuperarPedido = Signal(object)         # Hueco: "Recuperar lo borrado" en esa unión

    # Alto de la tira (las miniaturas). Una subclase (por ejemplo, la pista Voz del modo Audio) puede
    # cambiarlo, y dibujar otra cosa en la tira con ``dibujar_tira``.
    alto_tira = ALTO_TIRA

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)  # el teclado lo maneja la ventana (atajos)
        self.setMinimumHeight(ALTO_REGLA + self.alto_tira + ALTO_PIE + 4)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self._edicion: Optional[EdicionVideo] = None
        self._mapa: Optional[MapaTiempo] = None
        self._huecos: list[Hueco] = []
        # Segmentos que se ven: (índice, inicio y fin en el original, inicio y fin en el resultado).
        self._visibles: list[tuple[int, float, float, float, float]] = []
        self._tiempo = 0.0                      # cursor, en tiempo original
        self._seleccion = -1
        self._miniaturas: list[tuple[float, QImage]] = []
        self._tiempos_mini = np.zeros(0)
        self._arrastre: Optional[str] = None    # "cursor" | "entrada" | "salida"
        self._ultimo_r: Optional[float] = None  # dónde iba el cursor arrastrado (tiempo del resultado)
        self._limite: Optional[float] = None    # dónde va la marca que se arrastra (tiempo del resultado)
        self._hover: Optional[float] = None     # tiempo del resultado bajo el mouse
        self._hover_union = -1
        self.menu_union: Optional[QMenu] = None  # el último menú de una marquita (las pruebas lo usan)

    def sizeHint(self) -> QSize:
        return QSize(640, ALTO_REGLA + self.alto_tira + ALTO_PIE + 4)

    # --------------------------------------------------------------- datos
    @property
    def seleccion(self) -> int:
        return self._seleccion

    @property
    def mapa(self) -> Optional[MapaTiempo]:
        return self._mapa

    @property
    def huecos(self) -> list[Hueco]:
        """Lo que falta en cada unión (una marquita por hueco), en orden."""
        return list(self._huecos)

    @property
    def tiempo_resultado(self) -> float:
        """Dónde está el cursor, en segundos del resultado."""
        return self._mapa.a_resultado(self._tiempo) if self._mapa is not None else 0.0

    def establecer_edicion(self, edicion: Optional[EdicionVideo]) -> None:
        self._edicion = edicion
        if edicion is None:
            self._mapa, self._huecos, self._visibles = None, [], []
        else:
            self._mapa = MapaTiempo.de_edicion(edicion)
            self._huecos = self._mapa.huecos()
            self._visibles = [(i, a, b, self._mapa.a_resultado(a), self._mapa.a_resultado(a) + (b - a))
                              for i, a, b in segmentos_visibles(edicion)]
        if self._seleccion >= 0 and not any(v[0] == self._seleccion for v in self._visibles):
            self._seleccion = -1  # lo elegido ya no se ve (se borró o quedó fuera)
        self._hover_union = -1
        if self.menu_union is not None and self.menu_union.isVisible():
            self.menu_union.close()  # la unión del menú puede haber cambiado
        self.update()

    def establecer_tiempo(self, segundos: float) -> None:
        if segundos != self._tiempo:
            self._tiempo = segundos
            self.update()

    def establecer_miniaturas(self, lista: list[tuple[float, QImage]]) -> None:
        """Miniaturas del original: [(segundos del original, imagen)], en cualquier orden."""
        self._miniaturas = sorted(lista, key=lambda m: m[0])
        self._tiempos_mini = np.array([t for t, _ in self._miniaturas], dtype=np.float64)
        self.update()

    def seleccionar(self, indice: int) -> None:
        """Elige un segmento (índice de ``EdicionVideo.segmentos``). Solo los que se ven."""
        if not any(v[0] == indice for v in self._visibles):
            indice = -1
        if indice != self._seleccion:
            self._seleccion = indice
            self.seleccionCambiada.emit(indice)
            self.update()

    # --------------------------------------------------------- geometría
    def _pista(self) -> QRectF:
        return QRectF(MARGEN, ALTO_REGLA + 4, max(1.0, self.width() - 2 * MARGEN), self.alto_tira)

    def rect_tira(self) -> QRectF:
        """Dónde va la tira (el rectángulo de las miniaturas), en coordenadas del widget."""
        return self._pista()

    def _duracion(self) -> float:
        """Duración del resultado (lo que mide la línea)."""
        return max(1e-6, self._mapa.duracion) if self._mapa is not None else 1.0

    def _x(self, r: float) -> float:
        """Coordenada de un instante del resultado."""
        p = self._pista()
        return p.left() + p.width() * max(0.0, min(1.0, r / self._duracion()))

    def _r(self, x: float) -> float:
        """Instante del resultado en la coordenada ``x``."""
        p = self._pista()
        return max(0.0, min(self._duracion(), (x - p.left()) / p.width() * self._duracion()))

    def x_de(self, t: float) -> float:
        """Coordenada donde se ve el instante ``t`` del original (lo que no se ve: su unión)."""
        return self._x(self._mapa.a_resultado(t)) if self._mapa is not None else self._pista().left()

    def x_de_resultado(self, r: float) -> float:
        return self._x(r)

    def tiempo_en(self, x: float) -> float:
        """Instante del original que se ve en la coordenada ``x``."""
        return self._mapa.a_original(self._r(x)) if self._mapa is not None else 0.0

    def _cuadro_resultado(self, r: float) -> float:
        """``r`` llevado al comienzo del cuadro más cercano (los tramos empiezan en la grilla de cuadros)."""
        fps = self._edicion.fps if self._edicion is not None else 30.0
        return round(r * fps) / fps

    def _visible_en(self, r: float) -> int:
        """Índice del segmento que se ve en el instante ``r`` del resultado (-1 si no hay ninguno)."""
        if not self._visibles:
            return -1
        r = min(r, self._duracion() - 1e-6)
        for indice, _a, _b, ra, rb in self._visibles:
            if r < rb - 1e-9:
                return indice
        return self._visibles[-1][0]

    def pestana(self, i: int) -> QRectF:
        """La pestaña de la marquita ``i``, debajo de la tira (donde se toca)."""
        x = self._x(self._huecos[i].en)
        p = self._pista()
        return QRectF(x - ANCHO_PESTANA / 2, p.bottom() + 3, ANCHO_PESTANA, ALTO_PESTANA)

    def _en_borde(self, x: float) -> bool:
        p = self._pista()
        return abs(x - p.left()) < 1.5 or abs(x - p.right()) < 1.5

    def union_en(self, pos: QPointF, holgura: float = 0.0) -> int:
        """Índice de la marquita que se toca en ``pos`` (su pestaña o, si no está en un extremo, su
        línea dentro de la tira), o -1. ``holgura``: píxeles de más (para el menú contextual)."""
        p = self._pista()
        mejor, distancia = -1, math.inf
        for i, h in enumerate(self._huecos):
            x = self._x(h.en)
            d = abs(pos.x() - x)
            en_pestana = self.pestana(i).adjusted(-4 - holgura, -3, 4 + holgura, 4).contains(pos)
            en_linea = (not self._en_borde(x) and p.top() <= pos.y() <= p.bottom()
                        and d <= DISTANCIA_UNION + holgura)
            if (en_pestana or en_linea) and d < distancia:
                mejor, distancia = i, d
        return mejor

    def celdas(self) -> list[tuple[QRectF, int]]:
        """Dónde va cada miniatura: (rectángulo, índice en las miniaturas).

        Cada tramo conservado empieza su propia tira en su comienzo, así lo que seguía a un
        borrado empieza justo en la unión. Cada celda muestra la miniatura más cercana a lo que
        se ve en su centro, entre las de su mismo tramo (si hay alguna)."""
        mapa = self._mapa
        if not self._miniaturas or mapa is None or mapa.duracion <= 0:
            return []
        pista = self._pista()
        n = len(self._miniaturas)
        original = mapa.duracion_original or mapa.duracion
        # Sin cortes, n celdas parejas (como siempre). Si el resultado es más corto, cada celda
        # se ensancha para cubrir lo mismo del original (sin repetir), hasta su proporción natural.
        img = next((m for _t, m in self._miniaturas if not m.isNull()), None)
        natural = pista.height() * img.width() / max(1, img.height()) if img is not None else pista.width() / n
        ancho = max(pista.width() / n, min(natural, pista.width() * (original / n) / mapa.duracion))
        salida = []
        for (a, b), r0 in zip(mapa.tramos, mapa.inicios_resultado):
            x0, x1 = self._x(r0), self._x(r0 + (b - a))
            x = x0
            while x < x1 - 0.25:
                centro = (x + min(x + ancho, x1)) / 2
                o = min(b, a + (self._r(centro) - r0))
                salida.append((QRectF(x, pista.top(), ancho, pista.height()), self._miniatura_para(o, a, b)))
                x += ancho
        return salida

    def _miniatura_para(self, t: float, a: float, b: float) -> int:
        """La miniatura más cercana a ``t``, de las que caen en [a, b) si hay alguna."""
        tiempos = self._tiempos_mini
        lo = int(np.searchsorted(tiempos, a - 1e-9, side="left"))
        hi = int(np.searchsorted(tiempos, b - 1e-9, side="left"))
        if lo >= hi:
            lo, hi = 0, len(tiempos)
        k = min(max(int(np.searchsorted(tiempos, t)), lo), hi - 1)
        if k > lo and abs(tiempos[k - 1] - t) <= abs(tiempos[k] - t):
            k -= 1
        return k

    # ------------------------------------------------------------- dibujo
    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        pista = self._pista()
        fondo = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(estilo.BORDE), 1))
        p.setBrush(QColor("#313339"))
        p.drawRoundedRect(fondo, 12, 12)
        if self._edicion is None:
            p.setPen(QColor(estilo.TEXTO_TENUE))
            p.drawText(self.rect(), Qt.AlignCenter, "Abrí un video para ver su línea de tiempo")
            p.end()
            return
        vacia = self._mapa.duracion <= 0
        if not vacia:
            self._dibujar_regla(p, pista)
        self.dibujar_tira(p, pista)
        if vacia:
            p.setPen(QColor(estilo.TEXTO_TENUE))
            p.drawText(pista, Qt.AlignCenter, "No queda nada: tocá la marquita para recuperar lo borrado (o Ctrl+Z)")
        else:
            self._dibujar_segmentos(p, pista)
        self._dibujar_uniones(p, pista)
        if not vacia:
            self._dibujar_marcas(p, pista)
            self._dibujar_cursor(p, pista)
        p.end()

    def _dibujar_regla(self, p: QPainter, pista: QRectF) -> None:
        dur = self._duracion()
        por_segundo = pista.width() / dur
        paso = next((s for s in PASOS_REGLA if s * por_segundo >= 78), PASOS_REGLA[-1])
        fuente = QFont(self.font())
        fuente.setPointSizeF(7.5)
        p.setFont(fuente)
        menor = paso / 5
        n = int(math.floor(dur / menor + 1e-9)) + 1
        for k in range(n):
            t = k * menor
            x = self._x(t)
            mayor = k % 5 == 0
            p.setPen(QPen(QColor("#565962" if mayor else "#43464d"), 1))
            p.drawLine(QPointF(x, ALTO_REGLA - (8 if mayor else 4)), QPointF(x, ALTO_REGLA))
            if mayor:
                if paso >= 1:
                    texto = formato_tiempo(t, decimas=False)
                else:  # pasos de décimas: 0:01,5
                    decimas = int(round(t * 10))
                    m, resto = divmod(decimas, 600)
                    texto = f"{m}:{resto // 10:02d},{resto % 10}"
                if x + 3 + p.fontMetrics().horizontalAdvance(texto) > self.width() - 4:
                    continue  # no entra entera: mejor no mostrarla cortada
                p.setPen(QColor(estilo.TEXTO_TENUE))
                p.drawText(QRectF(x + 3, 3, 70, ALTO_REGLA - 6), Qt.AlignLeft | Qt.AlignVCenter, texto)

    def dibujar_tira(self, p: QPainter, pista: QRectF) -> None:
        """Dibuja la tira en ``pista`` (``rect_tira()``): las miniaturas de cada tramo. Una subclase
        lo puede reemplazar para dibujar otra cosa (por ejemplo, una forma de onda). Por defecto llama a
        ``_dibujar_tira`` (que también se puede reemplazar, como antes)."""
        self._dibujar_tira(p, pista)

    def _dibujar_tira(self, p: QPainter, pista: QRectF) -> None:
        camino = QPainterPath()
        camino.addRoundedRect(pista, 8, 8)
        p.save()
        p.setClipPath(camino)
        grad = QLinearGradient(pista.topLeft(), pista.bottomLeft())
        grad.setColorAt(0, QColor("#3a3c43"))
        grad.setColorAt(1, QColor("#35373d"))
        p.fillRect(pista, grad)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        mapa = self._mapa
        celdas = self.celdas()
        tramos = list(zip(mapa.tramos, mapa.inicios_resultado)) if mapa is not None else []
        k = 0
        for (a, b), r0 in tramos:
            # Cada tramo con su propio recorte: la última celda no se mete en el tramo de al lado.
            x0, x1 = self._x(r0), self._x(r0 + (b - a))
            p.save()
            p.setClipRect(QRectF(x0, pista.top(), x1 - x0, pista.height()), Qt.IntersectClip)
            while k < len(celdas) and celdas[k][0].left() < x1 - 0.25:
                celda, j = celdas[k]
                k += 1
                img = self._miniaturas[j][1]
                if img.isNull():
                    continue
                # Cubre la celda conservando la proporción (se recorta el centro).
                escala = max(celda.width() / img.width(), celda.height() / img.height())
                w, h = celda.width() / escala, celda.height() / escala
                fuente = QRectF((img.width() - w) / 2, (img.height() - h) / 2, w, h)
                p.drawImage(celda.adjusted(0, 0, 0.5, 0), img, fuente)
            p.restore()
        p.restore()

    def _dibujar_segmentos(self, p: QPainter, pista: QRectF) -> None:
        camino = QPainterPath()
        camino.addRoundedRect(pista, 8, 8)
        p.save()
        p.setClipPath(camino)
        # Mientras se arrastra la entrada o la salida: lo que se va a recortar, apagado.
        if self._arrastre in ("entrada", "salida") and self._limite is not None:
            sombra = QColor(0, 0, 0, 175)
            x = self._x(self._limite)
            if self._arrastre == "entrada":
                p.fillRect(QRectF(pista.left(), pista.top(), x - pista.left(), pista.height()), sombra)
            else:
                p.fillRect(QRectF(x, pista.top(), pista.right() - x, pista.height()), sombra)
        # Cortes entre dos segmentos que siguen en el original: una ranura oscura con un filo claro.
        for anterior, actual in zip(self._visibles, self._visibles[1:]):
            if abs(anterior[2] - actual[1]) > 1e-6:
                continue  # ahí falta algo: es una marquita, no un corte
            x = self._x(actual[3])
            p.fillRect(QRectF(x - 1.5, pista.top(), 3, pista.height()), QColor(estilo.FONDO))
            p.fillRect(QRectF(x - 0.5, pista.top() + 6, 1, pista.height() - 12), QColor(255, 255, 255, 150))
        p.restore()
        # Segmento elegido: borde magenta.
        for indice, _a, _b, ra, rb in self._visibles:
            if indice == self._seleccion:
                rect = QRectF(self._x(ra), pista.top(), self._x(rb) - self._x(ra), pista.height())
                p.setPen(QPen(QColor(estilo.MAGENTA), 2))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 7, 7)

    def _dibujar_uniones(self, p: QPainter, pista: QRectF) -> None:
        """Las marquitas: una costura rosa en la unión y una pestaña debajo de la tira."""
        for i, hueco in enumerate(self._huecos):
            x = self._x(hueco.en)
            resaltada = i == self._hover_union
            color = QColor(estilo.MAGENTA if resaltada else estilo.ROSA)
            if not self._en_borde(x):
                p.fillRect(QRectF(x - 2, pista.top(), 4, pista.height()), QColor(estilo.FONDO))
                p.fillRect(QRectF(x - 1, pista.top(), 2, pista.height()), color)
            # Pestaña: un hilo que baja de la tira y una lengüeta redondeada.
            pestana = self.pestana(i)
            p.fillRect(QRectF(x - 0.75, pista.bottom(), 1.5, pestana.top() - pista.bottom() + 1), color)
            p.setPen(QPen(QColor("#ffffff") if resaltada else QColor(estilo.FONDO), 1))
            p.setBrush(color)
            p.drawRoundedRect(pestana, 4, 4)
            # Dos rayitas blancas: "acá hay algo plegado".
            p.setPen(QPen(QColor(255, 255, 255, 235), 1.2))
            centro = pestana.center()
            for dx in (-2.0, 2.0):
                p.drawLine(QPointF(centro.x() + dx, pestana.top() + 3), QPointF(centro.x() + dx, pestana.bottom() - 3))

    def _dibujar_marcas(self, p: QPainter, pista: QRectF) -> None:
        e = self._edicion
        recortes = (e.entrada > 1e-6, e.salida is not None)
        for lado, r, activa in ((1, 0.0, recortes[0]), (-1, self._duracion(), recortes[1])):
            nombre = "entrada" if lado == 1 else "salida"
            if self._arrastre == nombre and self._limite is not None:
                r, activa = self._limite, True
            color = QColor(estilo.ROSA if activa else "#5c5868")
            x = self._x(r)
            # Corchete: "[" en la entrada y "]" en la salida.
            camino = QPainterPath()
            camino.moveTo(x + 7 * lado, pista.top() - 1)
            camino.lineTo(x, pista.top() - 1)
            camino.lineTo(x, pista.bottom() + 1)
            camino.lineTo(x + 7 * lado, pista.bottom() + 1)
            p.setPen(QPen(color, 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(camino)

    def _dibujar_cursor(self, p: QPainter, pista: QRectF) -> None:
        if self._hover is not None and self._arrastre is None and self._hover_union < 0:
            xh = self._x(self._hover)
            p.setPen(QPen(QColor(255, 255, 255, 70), 1, Qt.DashLine))
            p.drawLine(QPointF(xh, pista.top()), QPointF(xh, pista.bottom()))
        r = self.tiempo_resultado
        x = self._x(r)
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawLine(QPointF(x, 6), QPointF(x, pista.bottom() + 2))
        cabeza = QPainterPath()
        cabeza.addRoundedRect(QRectF(x - 6, 2, 12, 12), 4, 4)
        grad = QLinearGradient(QPointF(x - 6, 2), QPointF(x + 6, 14))
        grad.setColorAt(0, QColor(estilo.MAGENTA))
        grad.setColorAt(1, QColor(estilo.VIOLETA))
        p.setPen(QPen(QColor("#ffffff"), 1.5))
        p.setBrush(grad)
        p.drawPath(cabeza)
        if self._arrastre == "cursor":
            self._burbuja(p, x, formato_tiempo(r))
        elif self._arrastre in ("entrada", "salida") and self._limite is not None:
            self._burbuja(p, self._x(self._limite), formato_tiempo(self._limite))

    def _burbuja(self, p: QPainter, x: float, texto: str) -> None:
        fuente = QFont(self.font())
        fuente.setPointSizeF(8.5)
        fuente.setBold(True)
        p.setFont(fuente)
        m = p.fontMetrics()
        ancho, alto = m.horizontalAdvance(texto) + 14, m.height() + 6
        izquierda = max(2.0, min(self.width() - ancho - 2.0, x - ancho / 2))
        rect = QRectF(izquierda, self._pista().bottom() - alto - 4, ancho, alto)
        p.setPen(QPen(QColor(estilo.BORDE_SELECCION), 1))
        p.setBrush(QColor(20, 10, 18, 225))
        p.drawRoundedRect(rect, alto / 2, alto / 2)
        p.setPen(QColor("#ffffff"))
        p.drawText(rect, Qt.AlignCenter, texto)

    # ------------------------------------------------------------ menú de una marquita
    def mostrar_menu_union(self, i: int, donde: Optional[QPoint] = None) -> Optional[QMenu]:
        """Abre (sin bloquear) el menú de la marquita ``i``: qué falta ahí y "Recuperar lo borrado"."""
        if not 0 <= i < len(self._huecos):
            return None
        hueco = self._huecos[i]
        if self.menu_union is not None:
            self.menu_union.close()
            self.menu_union.deleteLater()
        menu = QMenu(self)
        menu.setObjectName("menuUnion")
        titulo = menu.addAction(texto_hueco(hueco))
        titulo.setEnabled(False)
        menu.addSeparator()
        accion = menu.addAction(iconos.icono("rotate-ccw", 16), "Recuperar lo borrado")
        accion.setToolTip("Vuelve a poner en la línea de tiempo lo que falta acá (Ctrl+Z lo vuelve a sacar)")
        accion.triggered.connect(lambda: self.recuperarPedido.emit(hueco))
        self.menu_union = menu
        if donde is None:
            pestana = self.pestana(i)
            donde = self.mapToGlobal(QPoint(round(pestana.left()), round(pestana.bottom()) + 2))
        menu.popup(donde)
        return menu

    # ------------------------------------------------------------ eventos
    def _marca_cerca(self, x: float) -> Optional[str]:
        if self._mapa is None or self._mapa.duracion <= 0:
            return None
        d_entrada, d_salida = abs(x - self._x(0.0)), abs(x - self._x(self._duracion()))
        if min(d_entrada, d_salida) > DISTANCIA_MARCA:
            return None
        return "entrada" if d_entrada <= d_salida else "salida"

    def event(self, evento) -> bool:
        if evento.type() == QEvent.ToolTip and self._edicion is not None:
            i = self.union_en(QPointF(evento.pos()), holgura=2)
            if i >= 0:
                QToolTip.showText(evento.globalPos(), f"{texto_hueco(self._huecos[i])}. Tocá la marquita para "
                                  "recuperarlo (o Ctrl+Z).", self)
            else:
                QToolTip.hideText()
                evento.ignore()
            return True
        return super().event(evento)

    def contextMenuEvent(self, evento) -> None:
        if self._edicion is None:
            return
        i = self.union_en(QPointF(evento.pos()), holgura=6)
        if i < 0 and self._huecos:  # cerca de una unión, a cualquier altura
            x = evento.pos().x()
            cercana = min(range(len(self._huecos)), key=lambda k: abs(self._x(self._huecos[k].en) - x))
            if abs(self._x(self._huecos[cercana].en) - x) <= 10:
                i = cercana
        if i >= 0:
            self.mostrar_menu_union(i, evento.globalPos())

    def mousePressEvent(self, evento) -> None:
        if self._edicion is None or evento.button() != Qt.LeftButton:
            return
        pos = evento.position()
        i = self.union_en(pos)
        if i >= 0:
            self.mostrar_menu_union(i)
            return
        if self._mapa.duracion <= 0:
            return
        pista = self._pista()
        marca = self._marca_cerca(pos.x()) if pista.top() - 4 <= pos.y() <= pista.bottom() + 2 else None
        if marca is not None:
            self._arrastre = marca
            self._limite = 0.0 if marca == "entrada" else self._duracion()
            self.update()
            return
        self._arrastre = "cursor"
        r = self._r(pos.x())
        self._ultimo_r = r
        if pos.y() >= pista.top():
            self.seleccionar(self._visible_en(r))
        self.tiempoPedido.emit(self._mapa.a_original(r), True)

    def terminar_arrastre(self) -> None:
        """Corta un arrastre cuyo soltar se perdió (un cuadro de diálogo en medio, Alt+Tab): el cursor
        queda donde iba (y se pide el cuadro final) y un corchete vuelve a su lugar sin recortar."""
        arrastre, self._arrastre = self._arrastre, None
        self._limite = None
        if arrastre == "cursor" and self._edicion is not None and self._ultimo_r is not None:
            self.tiempoPedido.emit(self._mapa.a_original(self._ultimo_r), False)
        if arrastre is not None:
            self.update()

    def mouseMoveEvent(self, evento) -> None:
        if self._edicion is None:
            return
        if self._arrastre is not None and not (evento.buttons() & Qt.LeftButton):
            self.terminar_arrastre()  # el botón ya no está apretado: el soltar se perdió
        pos = evento.position()
        r = self._r(pos.x())
        if self._arrastre == "cursor":
            self._ultimo_r = r
            self.tiempoPedido.emit(self._mapa.a_original(r), True)
            return
        if self._arrastre in ("entrada", "salida"):
            cuadro = self._edicion.cuadro
            r = self._cuadro_resultado(r)
            if self._arrastre == "entrada":
                self._limite = max(0.0, min(r, self._duracion() - cuadro))
            else:
                self._limite = min(self._duracion(), max(r, cuadro))
            self.update()
            return
        union = self.union_en(pos)
        self._hover = r
        if union != self._hover_union:
            self._hover_union = union
        if union >= 0:
            self.setCursor(Qt.PointingHandCursor)
        elif self._marca_cerca(pos.x()) and pos.y() <= self._pista().bottom() + 2:
            self.setCursor(Qt.SplitHCursor)
        else:
            self.setCursor(Qt.PointingHandCursor)
        self.update()

    def mouseReleaseEvent(self, evento) -> None:
        if evento.button() != Qt.LeftButton or self._arrastre is None:
            return
        arrastre, self._arrastre = self._arrastre, None
        if arrastre == "cursor":
            self.tiempoPedido.emit(self._mapa.a_original(self._r(evento.position().x())), False)
        elif self._limite is not None:
            limite, self._limite = self._limite, None
            e = self._edicion
            if arrastre == "entrada" and limite > 1e-6:
                self.limitesPedidos.emit(self._mapa.a_original(limite), e.salida)
            elif arrastre == "salida" and limite < self._duracion() - e.cuadro / 2:
                self.limitesPedidos.emit(e.entrada, self._mapa.a_original(limite))
        self.update()

    def leaveEvent(self, evento) -> None:
        if self._arrastre is not None and not (QApplication.mouseButtons() & Qt.LeftButton):
            self.terminar_arrastre()  # se fue sin soltar dentro (con el botón apretado, el arrastre sigue)
        self._hover = None
        self._hover_union = -1
        self.update()
        super().leaveEvent(evento)

    def focusOutEvent(self, evento) -> None:
        self.terminar_arrastre()  # un cuadro de diálogo o Alt+Tab en medio del arrastre
        super().focusOutEvent(evento)
