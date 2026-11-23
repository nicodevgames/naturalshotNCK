"""Pista de sonido: la forma de onda dibujada con QPainter y su carga en segundo plano.

Piezas reutilizables (el editor de video las usa debajo de la línea de tiempo y
un futuro modo Audio las puede usar igual). No dependen del editor de video:
solo de ``motor/audio.py``.

* ``CargadorOnda``: calcula la forma de onda de un archivo en un hilo
  (``forma_de_onda`` con ``COLUMNAS_ONDA`` columnas), con entregas parciales
  mientras lee. Una carga nueva descarta la anterior.
* ``PistaOnda``: el widget. Muestra cómo va a salir el sonido: la onda con el
  volumen (o la normalización) y los fundidos ya aplicados, los silencios
  marcados en rosa y el cursor. Si el archivo no tiene sonido, una franja que lo
  dice. Tocarla o arrastrarla pide un instante, como la línea de tiempo. Con
  ``solo_resultado=True`` (el editor de video) dibuja solo lo que se exporta, de
  corrido, como la línea de tiempo: lo borrado no está y en cada unión queda una
  rayita. Si no, dibuja todo el archivo con lo que no se exporta apagado.
* ``pico_aproximado``: el pico de lo que se exporta, estimado con la forma de onda
  (para dibujar o escuchar con "Normalizar" mientras se mide el exacto).

Tiempos: lo que entra y sale (``establecer_tiempo``, ``establecer_seleccion``,
``tiempoPedido``, ``presionada``, ``tiempo_en``, los tramos y los silencios) va en
el tiempo **original** del archivo, también con ``solo_resultado`` (la pista
convierte al dibujar, con ``motor.video.MapaTiempo``). Los fundidos van en el del
resultado (como en ``AjustesAudio``).
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
from PySide6.QtCore import QEvent, QLineF, QObject, QPointF, QRectF, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QSizePolicy, QToolTip, QWidget

from ..motor import audio as ma
from ..motor.video import MapaTiempo
from . import estilo, iconos
from .linea_tiempo import MARGEN, formato_tiempo
from .tareas import SenalesTarea, Tarea

COLUMNAS_ONDA = 4000   # se pide una vez con muchas columnas y se reduce al ancho al dibujar
ALTO_PISTA = 46
INTERVALO_PARCIAL = 0.2  # s entre entregas parciales mientras se lee el archivo
COLOR_SILENCIO = QColor(236, 72, 153)  # estilo.ROSA


def _tramos_o_todo(tramos: Optional[Sequence[tuple[float, float]]], duracion: float) -> list[tuple[float, float]]:
    return [(0.0, duracion)] if tramos is None else [(float(a), float(b)) for a, b in tramos if b > a]


def pico_aproximado(forma: Optional[ma.FormaOnda], tramos: Optional[Sequence[tuple[float, float]]] = None,
                    silencios: Sequence[tuple[float, float]] = ()) -> Optional[float]:
    """Pico (0 a 1) de lo que se exporta, estimado con la forma de onda.

    Toma las columnas que caen en algún tramo conservado y no del todo en un
    silencio. Como cada columna guarda el mínimo y el máximo de verdad, da el pico
    exacto o apenas más (las columnas de los bordes pueden traer un poco de lo de
    al lado). None si la forma no está completa todavía."""
    if forma is None or not forma.completa or forma.duracion <= 0:
        return None
    n = forma.columnas
    paso = forma.duracion / n
    inicio = np.arange(n) * paso
    fin = inicio + paso
    dentro = np.zeros(n, bool)
    for a, b in _tramos_o_todo(tramos, forma.duracion):
        dentro |= (fin > a) & (inicio < b)
    for a, b in silencios:
        dentro &= ~((inicio >= a) & (fin <= b))
    if not dentro.any():
        return 0.0
    return float(forma.picos()[dentro].max())


def onda_en_resultado(forma: ma.FormaOnda, mapa: MapaTiempo, columnas: int) -> tuple[np.ndarray, np.ndarray]:
    """La forma de onda del resultado (los tramos de ``mapa`` uno detrás de otro) en
    ``columnas`` columnas parejas: (mínimos, máximos).

    Cada columna toma el mínimo y el máximo de todas las columnas de ``forma`` que cubre en
    el original; si cruza una unión, los de los dos lados (nunca lo de en medio, que no
    está en el resultado)."""
    columnas = max(1, int(columnas))
    total = mapa.duracion
    if total <= 0 or forma.duracion <= 0 or not mapa.tramos:
        return np.zeros(columnas, np.float32), np.zeros(columnas, np.float32)
    n = forma.columnas
    bordes = np.arange(columnas + 1) * total / columnas
    uniones = np.array(mapa.inicios_resultado[1:], dtype=np.float64)
    cortes = np.unique(np.concatenate([bordes, uniones[(uniones > 0) & (uniones < total)]]))
    # Cada pieza entre dos cortes cae entera en un tramo: su rango en las columnas del original.
    medios = (cortes[:-1] + cortes[1:]) / 2
    o0 = np.asarray(mapa.a_original(cortes[:-1] + 1e-12))
    o1 = o0 + (cortes[1:] - cortes[:-1])
    c0 = np.clip(np.floor(o0 / forma.duracion * n).astype(np.int64), 0, n - 1)
    c1 = np.clip(np.ceil(o1 / forma.duracion * n - 1e-6).astype(np.int64), c0 + 1, n)
    # reduceat sobre [c0, c1) de cada pieza (un elemento de más al final, para poder llegar a n).
    indices = np.empty(2 * len(c0), np.int64)
    indices[0::2], indices[1::2] = c0, c1
    minimos = np.minimum.reduceat(np.append(forma.minimos, 0.0), indices)[0::2]
    maximos = np.maximum.reduceat(np.append(forma.maximos, 0.0), indices)[0::2]
    # Y las piezas de cada columna de pantalla, juntas.
    columna = np.clip(np.searchsorted(bordes, medios, side="right") - 1, 0, columnas - 1)
    primeras = np.searchsorted(columna, np.arange(columnas), side="left")
    return (np.minimum.reduceat(minimos, primeras).astype(np.float32),
            np.maximum.reduceat(maximos, primeras).astype(np.float32))


def forma_alineada(forma: Optional[ma.FormaOnda], mapa: MapaTiempo,
                   columnas: Optional[int] = None) -> Optional[ma.FormaOnda]:
    """La forma de onda de un sonido externo puesta en el tiempo ORIGINAL del video, para
    dibujarla con ``PistaOnda`` como si fuera la del video (con sus tramos y silencios).

    ``mapa`` dice en qué segundo del externo suena cada instante del original
    (``mapa.a_resultado``): ``MapaTiempo.identidad(duracion)`` si el externo está alineado
    con el original, o el de la edición si empieza en el 0 del resultado (voz en off). La
    forma que sale dura ``mapa.duracion_original`` (lo que dura el video); lo borrado y lo
    que está después del final del externo quedan en 0. Mientras el externo se lee, vale
    hasta donde se leyó."""
    if forma is None:
        return None
    n = max(1, int(columnas or forma.columnas))
    duracion = mapa.duracion_original
    ceros = np.zeros(n, np.float32)
    if duracion <= 0 or forma.duracion <= 0 or not mapa.tramos:
        return ma.FormaOnda(max(0.0, duracion), ceros, ceros.copy(), n)
    m, largo = forma.columnas, forma.duracion
    r = np.asarray(mapa.a_resultado(np.arange(n + 1) * duracion / n), dtype=np.float64)
    r0, r1 = r[:-1], r[1:]
    valido = (r1 - r0 > 1e-9) & (r0 < largo)
    c0 = np.clip(np.floor(r0 / largo * m).astype(np.int64), 0, m - 1)
    c1 = np.clip(np.ceil(r1 / largo * m - 1e-6).astype(np.int64), c0 + 1, m)
    indices = np.empty(2 * n, np.int64)
    indices[0::2], indices[1::2] = c0, c1
    minimos = np.minimum.reduceat(np.append(forma.minimos, 0.0), indices)[0::2]
    maximos = np.maximum.reduceat(np.append(forma.maximos, 0.0), indices)[0::2]
    minimos = np.where(valido, minimos, 0.0).astype(np.float32)
    maximos = np.where(valido, maximos, 0.0).astype(np.float32)
    if forma.completa:
        listas = n
    else:  # hasta donde se leyó el externo (r crece con el original: es un prefijo)
        listas = int(np.searchsorted(r1, forma.listas / m * largo, side="right"))
    return ma.FormaOnda(duracion, minimos, maximos, min(n, listas))


class CargadorOnda(QObject):
    """Calcula la forma de onda de un archivo en segundo plano.

    ``cargar(ruta)`` arranca (y descarta una carga anterior). Mientras lee emite
    ``parcial`` con lo calculado hasta ahí; al terminar, ``lista`` con la forma
    completa, o con None si el archivo no tiene sonido. Si falla, ``fallida``.
    El resultado queda en caché en el motor: volver a cargar el mismo archivo es
    inmediato."""

    parcial = Signal(object)   # FormaOnda (solo valen las primeras ``listas`` columnas)
    lista = Signal(object)     # FormaOnda completa, o None (sin sonido)
    fallida = Signal(str)

    def __init__(self, parent: Optional[QObject] = None, columnas: int = COLUMNAS_ONDA):
        super().__init__(parent)
        self.columnas = int(columnas)
        self.ruta: Optional[str] = None
        self.forma: Optional[ma.FormaOnda] = None
        self.cargando = False
        self._generacion = 0
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._senales = SenalesTarea(self)
        self._senales.terminada.connect(self._terminada)
        self._senales.fallida.connect(self._fallida)

    def cargar(self, ruta: str) -> None:
        self._generacion += 1
        generacion = self._generacion
        self.ruta, self.forma, self.cargando = str(ruta), None, True
        senales, columnas = self._senales, self.columnas

        def trabajo(cancelado):
            def avance(parcial):
                senales.terminada.emit("parcial", generacion, parcial)
            return ma.forma_de_onda(ruta, columnas, avance, cancelado, INTERVALO_PARCIAL)

        self._pool.start(Tarea("forma", generacion, trabajo, senales, lambda: self._generacion))

    def cancelar(self) -> None:
        """Descarta la carga en curso (el hilo la abandona en la próxima vuelta)."""
        self._generacion += 1
        self.ruta, self.forma, self.cargando = None, None, False

    def detener(self) -> None:
        """Cancela y espera al hilo (al cerrar)."""
        self.cancelar()
        self._pool.waitForDone()

    def _terminada(self, tipo: str, generacion: int, resultado) -> None:
        if generacion != self._generacion:
            return
        if tipo == "parcial":
            if resultado is not None and not resultado.completa:
                self.forma = resultado
                self.parcial.emit(resultado)
            return
        self.forma, self.cargando = resultado, False
        self.lista.emit(resultado)

    def _fallida(self, _tipo: str, generacion: int, mensaje: str) -> None:
        if generacion == self._generacion:
            self.cargando = False
            self.fallida.emit(mensaje)


class PistaOnda(QWidget):
    """La pista de sonido: la forma de onda del archivo.

    ``margen``: píxeles a cada lado (los mismos que la línea de tiempo, así las dos
    quedan alineadas). Estados: "vacio" (nada abierto), "cargando", "lista" y
    "sin_sonido". Con ``establecer_edicion`` muestra cómo va a salir: los silencios
    en rosa, la onda con el volumen y los fundidos, y todo apagado si el sonido se
    quita. Lo que no se exporta: con ``solo_resultado`` no se dibuja (la pista mide lo
    que dura el resultado, como la línea de tiempo del editor de video); si no, se ve
    apagado en su lugar del original. La interfaz va siempre en tiempo original."""

    tiempoPedido = Signal(float, bool)   # segundos (tiempo original), ¿se sigue arrastrando?
    presionada = Signal(float)           # se tocó la pista en ese instante (tiempo original)

    def __init__(self, parent: Optional[QWidget] = None, margen: int = MARGEN, solo_resultado: bool = False):
        super().__init__(parent)
        self._margen = margen
        self._solo_resultado = bool(solo_resultado)
        self._mapa: MapaTiempo = MapaTiempo((), 0.0)  # tiempo original ↔ lo que se dibuja
        self.setMinimumHeight(ALTO_PISTA)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.NoFocus)  # el teclado lo maneja quien la usa (atajos)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)
        self._estado = "vacio"
        self._texto_sin_sonido = "Sin sonido"
        self._forma: Optional[ma.FormaOnda] = None
        self._duracion = 0.0
        self._tramos: Optional[list[tuple[float, float]]] = None  # conservados (None = todo)
        self._ajustes = ma.AjustesAudio()
        self._ganancia: Optional[float] = None  # fija para dibujar; None = la de los ajustes
        self._tiempo = 0.0
        self._seleccion: Optional[tuple[float, float]] = None
        self._arrastrando = False
        self._ultimo_t: Optional[float] = None  # dónde iba el arrastre (por si se pierde el soltar)
        self._lienzo: Optional[QPixmap] = None  # la onda ya dibujada (sin el cursor)
        self._reducidas: dict = {}  # la forma reducida al ancho de ahora y su clave
        self.setToolTip("Sonido. Tocá o arrastrá para moverte.")

    def sizeHint(self) -> QSize:
        return QSize(640, ALTO_PISTA)

    # ------------------------------------------------------------- datos
    @property
    def estado(self) -> str:
        return self._estado

    @property
    def forma(self) -> Optional[ma.FormaOnda]:
        return self._forma

    @property
    def solo_resultado(self) -> bool:
        return self._solo_resultado

    @property
    def mapa(self) -> MapaTiempo:
        """Cómo se dibuja: el resultado (con ``solo_resultado``) o todo el original."""
        return self._mapa

    def establecer_solo_resultado(self, activo: bool) -> None:
        self._solo_resultado = bool(activo)
        self._rehacer_mapa()
        self._invalidar()

    def _rehacer_mapa(self) -> None:
        if self._solo_resultado and self._tramos is not None:
            self._mapa = MapaTiempo(tuple(self._tramos), self._duracion)
        else:
            self._mapa = MapaTiempo.identidad(self._duracion) if self._duracion > 0 else MapaTiempo((), 0.0)

    def _fijar_duracion(self, duracion: float) -> None:
        self._duracion = max(0.0, float(duracion))
        self._rehacer_mapa()

    def vaciar(self) -> None:
        """Nada abierto."""
        self._estado, self._forma = "vacio", None
        self._tramos, self._seleccion, self._tiempo = None, None, 0.0
        self._fijar_duracion(0.0)
        self._invalidar()

    def cargando(self, duracion: float) -> None:
        """Se abrió un archivo con sonido: se está leyendo."""
        self._estado, self._forma = "cargando", None
        self._fijar_duracion(duracion)
        self._invalidar()

    def sin_sonido(self, duracion: float, texto: str = "Sin sonido") -> None:
        """El archivo no tiene sonido (o no se pudo leer): una franja que lo dice."""
        self._estado, self._forma = "sin_sonido", None
        self._fijar_duracion(duracion)
        self._texto_sin_sonido = texto
        self._invalidar()

    def establecer_forma(self, forma: Optional[ma.FormaOnda]) -> None:
        """Forma parcial (mientras carga) o completa. None: el archivo no tiene sonido."""
        if forma is None:
            self.sin_sonido(self._duracion)
            return
        self._forma = forma
        if forma.duracion != self._duracion:
            self._fijar_duracion(forma.duracion)
        self._estado = "lista" if forma.completa else "cargando"
        self._invalidar()

    def establecer_edicion(self, tramos: Optional[Sequence[tuple[float, float]]], ajustes: ma.AjustesAudio,
                           ganancia: Optional[float] = None) -> None:
        """Lo que se conserva (tiempo original; None = todo) y los ajustes del sonido.

        ``ganancia``: el factor del volumen o de la normalización para dibujar (si
        falta, el volumen; con normalizar, se estima con ``pico_aproximado``)."""
        self._tramos = None if tramos is None else [(float(a), float(b)) for a, b in tramos]
        self._ajustes = ajustes
        self._ganancia = None if ganancia is None else float(ganancia)
        self._rehacer_mapa()
        self._invalidar()

    def ganancia_dibujada(self) -> float:
        """El factor con que se dibuja la onda: el dado, o el de los ajustes (con normalizar,
        con el pico estimado con la forma; mientras no esté completa, como si fuera 1)."""
        if self._ganancia is not None:
            return self._ganancia
        ajustes = self._ajustes
        if ajustes.quitar:
            return 0.0
        pico = pico_aproximado(self._forma, self._tramos, ajustes.silencios) if ajustes.normalizar else None
        return ajustes.ganancia(pico if pico is not None else 1.0)

    def establecer_tiempo(self, segundos: float) -> None:
        if segundos != self._tiempo:
            viejo = self._tiempo
            self._tiempo = segundos
            # Solo se redibuja la franja del cursor (la onda está en el lienzo).
            for t in (viejo, segundos):
                x = self._x(t)
                self.update(int(x) - 3, 0, 7, self.height())

    def establecer_seleccion(self, rango: Optional[tuple[float, float]]) -> None:
        """Tramo elegido (se marca con un borde magenta, como en la línea de tiempo)."""
        if rango != self._seleccion:
            self._seleccion = rango
            self._invalidar()

    # --------------------------------------------------------- geometría
    def _carril(self) -> QRectF:
        return QRectF(self._margen, 4, max(1.0, self.width() - 2 * self._margen), self.height() - 8)

    @property
    def _en_resultado(self) -> bool:
        """Si se dibuja solo el resultado (``solo_resultado`` y ya se sabe qué se conserva)."""
        return self._solo_resultado and self._tramos is not None

    def _largo(self) -> float:
        """Lo que mide la pista: la duración del resultado o la del original."""
        return self._mapa.duracion if self._en_resultado else self._duracion

    def _xd(self, d: float) -> float:
        """Coordenada de un instante de lo que se dibuja (el resultado o el original)."""
        c = self._carril()
        largo = self._largo()
        largo = largo if largo > 0 else 1.0
        return c.left() + c.width() * max(0.0, min(1.0, d / largo))

    def _x(self, t: float) -> float:
        """Coordenada del instante ``t`` del original."""
        return self._xd(self._mapa.a_resultado(t) if self._en_resultado else t)

    def _t(self, x: float) -> float:
        """Instante del original en la coordenada ``x``."""
        c = self._carril()
        largo = self._largo()
        d = max(0.0, min(largo, (x - c.left()) / c.width() * largo))
        if not self._en_resultado or not self._mapa.tramos:
            return d  # todo el original: los dos tiempos son el mismo
        # El último instante que se ve (el final del resultado es el final de un tramo, que ya no se ve).
        return self._mapa.a_original(min(d, max(0.0, largo - 1e-6)))

    def tiempo_en(self, x: float) -> float:
        """Instante (tiempo original) que corresponde a la coordenada ``x`` del widget."""
        return self._t(x)

    def x_de(self, t: float) -> float:
        """Coordenada del widget donde se dibuja el instante ``t`` del original (como ``LineaTiempo.x_de``)."""
        return self._x(t)

    @property
    def tiempo(self) -> float:
        """El cursor (tiempo original)."""
        return self._tiempo

    # ------------------------------------------------------------- dibujo
    def _invalidar(self) -> None:
        self._lienzo = None
        self.update()

    def resizeEvent(self, evento) -> None:
        super().resizeEvent(evento)
        self._lienzo = None

    def paintEvent(self, _evento) -> None:
        if self._lienzo is None or self._lienzo.size() != self.size() * self.devicePixelRatioF():
            self._lienzo = self._dibujar_lienzo()
        p = QPainter(self)
        p.drawPixmap(0, 0, self._lienzo)
        if self._estado != "vacio" and self._duracion > 0:
            carril = self._carril()
            x = self._x(self._tiempo)
            p.setPen(QPen(QColor("#ffffff"), 2))
            p.drawLine(QPointF(x, carril.top() - 2), QPointF(x, carril.bottom() + 2))
        p.end()

    def _dibujar_lienzo(self) -> QPixmap:
        escala = self.devicePixelRatioF()
        lienzo = QPixmap(self.size() * escala)
        lienzo.setDevicePixelRatio(escala)
        lienzo.fill(Qt.transparent)
        p = QPainter(lienzo)
        p.setRenderHint(QPainter.Antialiasing, True)
        fondo = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(estilo.BORDE), 1))
        p.setBrush(QColor("#313339"))
        p.drawRoundedRect(fondo, 10, 10)
        carril = self._carril()
        camino = QPainterPath()
        camino.addRoundedRect(carril, 7, 7)
        p.save()
        p.setClipPath(camino)
        p.fillRect(carril, QColor("#2b2d32"))
        if self._estado == "sin_sonido":
            self._texto_centrado(p, carril, self._texto_sin_sonido, "volume-x")
        elif self._estado == "vacio":
            pass
        else:
            self._dibujar_onda(p, carril)
        p.restore()
        p.end()
        return lienzo

    def _texto_centrado(self, p: QPainter, rect: QRectF, texto: str, icono: Optional[str] = None,
                        color: str = estilo.TEXTO_TENUE, fondo: bool = False) -> None:
        """Texto (con ícono) en el medio de ``rect``, si entra. ``fondo``: sobre una píldora oscura."""
        fuente = QFont(self.font())
        fuente.setPointSizeF(8.5)
        fuente.setBold(True)
        p.setFont(fuente)
        ancho = p.fontMetrics().horizontalAdvance(texto) + (20 if icono else 0)
        if ancho > rect.width() - (28 if fondo else 8):
            return
        x = rect.center().x() - ancho / 2
        if fondo:
            caja = QRectF(x - 10, rect.center().y() - 10, ancho + 20, 20)
            p.setPen(QPen(QColor(estilo.BORDE), 1))
            p.setBrush(QColor(43, 45, 50, 235))
            p.drawRoundedRect(caja, 10, 10)
        if icono:
            p.drawPixmap(QPointF(x, rect.center().y() - 7), iconos.pixmap(icono, 14, color))
            x += 20
        p.setPen(QColor(color))
        p.drawText(QRectF(x, rect.top(), ancho, rect.height()), Qt.AlignLeft | Qt.AlignVCenter, texto)

    def _reducida(self, columnas: int) -> ma.FormaOnda:
        forma = self._forma
        clave = (id(forma), forma.listas, columnas)
        cache = self._reducidas
        if cache.get("clave") != clave:
            cache.clear()
            cache["clave"] = clave
            cache["forma"] = forma.reducida(columnas)
        return cache["forma"]

    def _dibujar_onda(self, p: QPainter, carril: QRectF) -> None:
        forma, ajustes = self._forma, self._ajustes
        medio = carril.center().y()
        alto = carril.height() / 2 - 2
        p.setPen(QPen(QColor(255, 255, 255, 18), 1))
        p.drawLine(QPointF(carril.left(), medio), QPointF(carril.right(), medio))
        if forma is None:
            self._texto_centrado(p, carril, "Leyendo el sonido…", "audio-lines")
            return
        n = max(1, int(round(carril.width())))
        d = forma.duracion if forma.duracion > 0 else 1.0
        if self._en_resultado:
            # Solo lo que se exporta, de corrido: cada columna es un pedazo del resultado.
            total = self._mapa.duracion
            minimos, maximos = self._reducida_resultado(n)
            resultado = (np.arange(n) + 0.5) * total / n
            centros = np.asarray(self._mapa.a_original(resultado)) if total > 0 else np.zeros(n)
            exporta = np.full(n, total > 0)
            leido = forma.listas / max(1, forma.columnas) * d  # hasta dónde se leyó el archivo
            listas = n if forma.completa else int(np.searchsorted(centros, leido, side="left"))
        else:
            red = self._reducida(n)
            minimos, maximos = red.minimos, red.maximos
            listas = red.listas if not forma.completa else n
            centros = (np.arange(n) + 0.5) * d / n
            # Qué se exporta y en qué segundo del resultado cae cada columna (para los fundidos).
            exporta = np.zeros(n, bool)
            resultado = np.zeros(n)
            total = 0.0
            for a, b in _tramos_o_todo(self._tramos, d):
                dentro = (centros >= a) & (centros < b)
                exporta |= dentro
                resultado[dentro] = total + centros[dentro] - a
                total += b - a
        silencio = np.zeros(n, bool)
        for a, b in ajustes.silencios:
            silencio |= (centros >= a) & (centros < b)
        envolvente = np.ones(n)
        if ajustes.fundido_entrada > 0:
            envolvente *= np.clip(resultado / ajustes.fundido_entrada, 0.0, 1.0) ** 2
        if ajustes.fundido_salida > 0:
            envolvente *= np.clip((total - resultado) / ajustes.fundido_salida, 0.0, 1.0) ** 2
        activa = exporta & ~silencio & (not ajustes.quitar)
        g = np.where(activa, self.ganancia_dibujada() * envolvente, 1.0)
        arriba = maximos.astype(np.float64) * g
        abajo = minimos.astype(np.float64) * g
        saturada = activa & ((arriba > 1.0) | (abajo < -1.0))
        arriba, abajo = np.clip(arriba, -1.0, 1.0), np.clip(abajo, -1.0, 1.0)

        # Columnas como líneas verticales, por tipo: activa (degradado), saturada y apagada.
        lineas = {"activa": [], "saturada": [], "apagada": []}
        x0 = carril.left()
        for k in range(min(n, listas)):
            y1, y2 = medio - arriba[k] * alto, medio - abajo[k] * alto
            if y2 - y1 < 1.0:
                y1, y2 = medio - 0.5, medio + 0.5
            tipo = "saturada" if saturada[k] else "activa" if activa[k] else "apagada"
            lineas[tipo].append(QLineF(x0 + k + 0.5, y1, x0 + k + 0.5, y2))
        p.setRenderHint(QPainter.Antialiasing, False)
        grad = QLinearGradient(QPointF(0, carril.top()), QPointF(0, carril.bottom()))
        grad.setColorAt(0.0, QColor(estilo.ROSA))
        grad.setColorAt(0.5, QColor(estilo.MAGENTA))
        grad.setColorAt(1.0, QColor(estilo.VIOLETA))
        for tipo, pluma in (("apagada", QPen(QColor(150, 146, 162, 70), 1)),
                            ("activa", QPen(QBrush(grad), 1)),
                            ("saturada", QPen(QColor(estilo.PUNTO), 1))):
            if lineas[tipo]:
                p.setPen(pluma)
                p.drawLines(lineas[tipo])
        p.setRenderHint(QPainter.Antialiasing, True)

        if self._en_resultado:
            # Las uniones (donde se borró o recortó algo): una rayita, como la marquita de la línea de tiempo.
            union = QColor(COLOR_SILENCIO)
            union.setAlpha(150)
            for r in self._mapa.inicios_resultado[1:]:
                x = self._xd(r)
                p.fillRect(QRectF(x - 1.5, carril.top(), 3, carril.height()), QColor(estilo.FONDO))
                p.fillRect(QRectF(x - 0.5, carril.top(), 1, carril.height()), union)
        else:
            # Lo que no se exporta: apagado, como lo veía la línea de tiempo.
            sombra = QColor(0, 0, 0, 120)
            anterior = 0.0
            for a, b in _tramos_o_todo(self._tramos, d) + [(d, d)]:
                if a > anterior + 1e-9:
                    p.fillRect(QRectF(self._x(anterior), carril.top(), self._x(a) - self._x(anterior),
                                      carril.height()), sombra)
                anterior = max(anterior, b)
        # Silencios: franja rosa con la línea del medio punteada (en el resultado, una por cada parte que se ve).
        fuente = QFont(self.font())
        fuente.setPointSizeF(8)
        fuente.setBold(True)
        p.setFont(fuente)
        for x0s, x1s in self._franjas(ajustes.silencios):
            if ajustes.quitar:
                break  # con el sonido quitado todo va apagado, sin etiquetas que se pisen
            rect = QRectF(x0s, carril.top(), max(1.0, x1s - x0s), carril.height())
            tinte = QColor(COLOR_SILENCIO)
            tinte.setAlpha(34)
            p.fillRect(rect, tinte)
            borde = QColor(COLOR_SILENCIO)
            borde.setAlpha(150)
            p.setPen(QPen(borde, 1, Qt.DashLine))
            p.drawLine(QPointF(rect.left(), medio), QPointF(rect.right(), medio))
            p.setPen(QPen(borde, 1))
            p.drawLine(QPointF(rect.left() + 0.5, carril.top()), QPointF(rect.left() + 0.5, carril.bottom()))
            p.drawLine(QPointF(rect.right() - 0.5, carril.top()), QPointF(rect.right() - 0.5, carril.bottom()))
            if rect.width() > 92:
                caja = QRectF(rect.center().x() - 36, medio - 9, 72, 18)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(43, 45, 50, 225))
                p.drawRoundedRect(caja, 9, 9)
                p.drawPixmap(QPointF(caja.left() + 7, caja.top() + 3), iconos.pixmap("volume-x", 12, estilo.ROSA))
                p.setPen(QColor("#f9a8d4"))
                p.drawText(caja.adjusted(22, 0, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, "Silencio")
        # Mientras se lee: lo que falta, con un aviso.
        if not forma.completa:
            resto = QRectF(x0 + listas, carril.top(), carril.right() - x0 - listas, carril.height())
            if resto.width() > 0:
                p.fillRect(resto, QColor(255, 255, 255, 6))
                self._texto_centrado(p, resto, "Leyendo el sonido…")
        if ajustes.quitar:
            p.fillRect(carril, QColor(20, 20, 24, 150))
            self._texto_centrado(p, carril, "Sonido quitado: el video sale sin audio", "volume-x", estilo.TEXTO_2,
                                 fondo=True)
        # Tramo elegido: borde magenta, como en la línea de tiempo (solo la parte que se ve).
        if self._seleccion is not None:
            franjas = self._franjas([self._seleccion])
            if franjas:
                x0s, x1s = franjas[0][0], franjas[-1][1]
                rect = QRectF(x0s, carril.top(), x1s - x0s, carril.height())
                p.setPen(QPen(QColor(estilo.MAGENTA), 1.5))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(rect.adjusted(0.75, 0.75, -0.75, -0.75), 6, 6)

    def _franjas(self, rangos: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
        """Dónde se dibujan unos rangos del tiempo original: [(x inicial, x final)]. En el
        resultado, solo sus partes que se exportan (una por tramo que tocan)."""
        salida = []
        for a, b in rangos:
            if self._en_resultado:
                salida.extend((self._xd(ra), self._xd(rb)) for ra, rb in self._mapa.rangos_resultado(a, b))
            elif b > a:
                salida.append((self._x(a), self._x(b)))
        return salida

    def _reducida_resultado(self, columnas: int) -> tuple[np.ndarray, np.ndarray]:
        forma = self._forma
        clave = ("resultado", id(forma), forma.listas, columnas, self._mapa)
        cache = self._reducidas
        if cache.get("clave") != clave:
            cache.clear()
            cache["clave"] = clave
            cache["forma"] = onda_en_resultado(forma, self._mapa, columnas)
        return cache["forma"]

    # ------------------------------------------------------------ eventos
    def event(self, evento) -> bool:
        if evento.type() == QEvent.ToolTip and self._estado != "vacio":
            t = self._t(evento.pos().x())
            i = self._ajustes.silencio_en(t)
            if i is not None:
                a, b = self._ajustes.silencios[i]
                if self._en_resultado:  # los tiempos que se ven en la regla: los del resultado
                    a, b = self._mapa.a_resultado(a), self._mapa.a_resultado(b)
                QToolTip.showText(evento.globalPos(), f"Silenciado de {formato_tiempo(a)} a {formato_tiempo(b)}.",
                                  self)
                return True
        return super().event(evento)

    def mousePressEvent(self, evento) -> None:
        if self._estado == "vacio" or self._duracion <= 0 or evento.button() != Qt.LeftButton:
            return
        self._arrastrando = True
        t = self._t(evento.position().x())
        self._ultimo_t = t
        self.presionada.emit(t)
        self.tiempoPedido.emit(t, True)

    def mouseMoveEvent(self, evento) -> None:
        if self._arrastrando and not (evento.buttons() & Qt.LeftButton):
            self.terminar_arrastre()  # el botón ya no está apretado: el soltar se perdió
        if self._arrastrando:
            self._ultimo_t = self._t(evento.position().x())
            self.tiempoPedido.emit(self._ultimo_t, True)

    def mouseReleaseEvent(self, evento) -> None:
        if evento.button() == Qt.LeftButton and self._arrastrando:
            self._arrastrando = False
            self.tiempoPedido.emit(self._t(evento.position().x()), False)

    def terminar_arrastre(self) -> None:
        """Corta un arrastre cuyo soltar se perdió (un cuadro de diálogo en medio, Alt+Tab): el cursor
        queda donde iba y se pide el cuadro final."""
        if self._arrastrando:
            self._arrastrando = False
            if self._ultimo_t is not None:
                self.tiempoPedido.emit(self._ultimo_t, False)

    def leaveEvent(self, evento) -> None:
        if self._arrastrando and not (QApplication.mouseButtons() & Qt.LeftButton):
            self.terminar_arrastre()  # se fue sin soltar dentro (con el botón apretado, el arrastre sigue)
        super().leaveEvent(evento)

    def focusOutEvent(self, evento) -> None:
        self.terminar_arrastre()
        super().focusOutEvent(evento)


__all__ = ["COLUMNAS_ONDA", "ALTO_PISTA", "CargadorOnda", "PistaOnda", "onda_en_resultado", "pico_aproximado"]
