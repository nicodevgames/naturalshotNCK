"""Vista previa con comparación antes/después, zoom y desplazamiento.

Herramientas sobre la foto: zona (marcar la zona de un efecto, de una máscara...), recorte,
enderezar, clonar y **transformar** (Mover / Transformar una capa imagen, con manijas: la
lógica está en ``herramienta_transformar.HerramientaTransformar``).

Arrastrar archivos: fotos y videos se abren (la ventana los rutea); un proyecto ``.nslite``
también. Con **Ctrl** apretado al soltar, las imágenes entran como **capas** de la foto
abierta (``imagenesComoCapa``) en vez de sumarse a la tira.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QTransform,
)
from PySide6.QtWidgets import QWidget

from .. import edicion
from ..motor.imagen_io import EXTENSIONES_SOPORTADAS, EXTENSIONES_VIDEO
from ..motor.zonas import alfa_trazo, mascara_trazos
from . import estilo
from .herramienta_transformar import HerramientaTransformar

ZOOM_MIN = 0.02
ZOOM_MAX = 16.0
SEPARACION = 8  # espacio entre los dos paneles del modo lado a lado
LADO_LIENZO = 1600  # lado largo del lienzo reducido donde se ve lo pintado
# Se aceptan fotos y videos al arrastrar: la ventana lleva cada cosa a su modo (fotos o Video).
EXTENSIONES_ARRASTRE = tuple(EXTENSIONES_SOPORTADAS) + tuple(EXTENSIONES_VIDEO) + (".nslite",)
# Rosa semitransparente (premultiplicado) para lo pintado mientras se pinta.
COLOR_PINTURA = np.array([236, 72, 153, 255], np.float32) * 0.5


def radio_pincel(tam: int) -> float:
    """Radio del pincel relativo al lado largo de la foto: de 0,2 % (tam 0) a 20 % (tam 100)."""
    return 0.002 * 100.0 ** (max(0, min(100, tam)) / 100.0)


class VistaComparacion(QWidget):
    archivoSoltado = Signal(str)
    archivosSoltados = Signal(list)  # todas las fotos y videos soltados juntos (la ventana los rutea)
    zoomCambiado = Signal(float)
    clicSinImagen = Signal()
    seleccionTerminada = Signal(QRectF)  # normalizada (0..1) respecto de la imagen mostrada
    seleccionCancelada = Signal()
    formaTerminada = Signal(list)  # puntos [(x, y)] normalizados de un lazo cerrado
    trazosTerminados = Signal(list)  # trazos nuevos del pincel: (puntos normalizados, radio, dureza, borrar)
    pincelCambiado = Signal()  # tamaño, dureza o goma cambiados desde el teclado
    confirmado = Signal()  # Enter en el recorte, el enderezado o el clonado
    clonCambiado = Signal(float, float)  # clonar: desplazamiento de la zona a la fuente (px de la imagen)
    transformacionCambiada = Signal(object)  # Mover / Transformar: la Transformacion nueva (arrastre o flechas)
    imagenesComoCapa = Signal(list)  # imágenes soltadas con Ctrl: entran como capas de la foto abierta

    MODO_DIVIDIR = "dividir"
    MODO_ANTES = "antes"
    MODO_DESPUES = "despues"
    MODO_LADO = "lado"
    MODO_SOLO = "solo"  # modo Photoshop: solo la imagen, sin Antes, Después ni divisor

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(420, 320)

        self._antes: Optional[QImage] = None
        self._despues: Optional[QImage] = None
        self._tam = (0, 0)  # tamaño real de la imagen (ancho, alto)
        self._zoom = 1.0
        self._origen = QPointF(0, 0)  # posición en pantalla del píxel (0, 0)
        self._ajustar = True
        self._division = 0.5  # fracción del ancho del widget
        self._modo = self.MODO_DIVIDIR
        self._modo_temporal: Optional[str] = None
        self._arrastre: Optional[str] = None  # "division" | "pan"
        self._ultimo = QPointF()
        self._arrastrando_archivo = False
        self._cache: dict[str, tuple[tuple, QPixmap]] = {}
        self._procesando = False
        self._texto_procesando = "Procesando…"
        # Herramientas: None (mover), "zona" (marcar la zona de una capa), "recorte",
        # "enderezar" (solo cuadrícula) o "clonar" (elegir de dónde se copia).
        self._herramienta: Optional[str] = None
        self._forma = "rect"
        self._aspecto: Optional[float] = None  # ancho / alto, solo para el recorte
        self._sel: Optional[QRectF] = None  # selección en píxeles de la imagen mostrada
        self._sel_inicio = QPointF()
        self._superposiciones: list[tuple] = []  # (texto, forma, rect normalizado[, puntos normalizados])
        self._puntos: list[QPointF] = []  # lazo en curso, en píxeles de la imagen
        self._cursor_img: Optional[QPointF] = None
        # Pincel: tamaño (0..100), dureza (0..100) y goma. Los trazos se guardan
        # normalizados a la imagen mostrada; el radio, relativo a su lado largo.
        self._pincel_tam = 45
        self._pincel_dureza = 70
        self._goma = False
        self._trazos_previos: tuple = ()  # lo ya pintado al entrar
        self._trazos: list = []  # trazos nuevos de esta vez
        self._trazo: list[QPointF] = []  # trazo en curso, en píxeles de la imagen
        self._trazo_borra = False
        self._trazo_pincel = (0.0, 0)  # radio relativo y dureza del trazo en curso (fijos al empezar)
        self._caja_trazo: Optional[list[int]] = None  # recuadro del trazo en curso en el lienzo
        self._lienzo: Optional[np.ndarray] = None  # máscara pintada (reducida), sin el trazo en curso
        self._alfa: Optional[np.ndarray] = None  # opacidad del trazo en curso
        self._rgba: Optional[np.ndarray] = None
        self._capa_pintura: Optional[QImage] = None
        self._base_pincel: Optional[np.ndarray] = None  # máscara de partida (cielo, piel...) bajo lo pintado
        self._timer_muestra = QTimer(self, singleShot=True, interval=900)
        self._timer_muestra.timeout.connect(self._ocultar_muestra)
        self._cuadricula = True  # al enderezar
        # Clonar: contorno de la zona (normalizado), desplazamiento hacia la fuente (px) y arrastre.
        self._clon_contornos: list = []
        self._clon_camino = QPainterPath()  # la zona, en píxeles de la imagen
        self._clon_d = QPointF(0, 0)
        self._clon_inicio: Optional[QPointF] = None
        self._clon_base = QPointF(0, 0)
        self._clon_imagen: Optional[QImage] = None
        # Mover / Transformar: la herramienta (manijas) de la capa que se transforma.
        self._transformar: Optional[HerramientaTransformar] = None
        self._manija_hover: Optional[str] = None
        # Modo Photoshop: las herramientas de la barra (Mover, Mano, Zoom, Cuentagotas) las maneja un
        # controlador (``modo_photoshop.ControladorVista``) que recibe el mouse en píxeles del documento
        # y se dibuja encima (herramienta "ps"). La mano temporal (Espacio sostenido) desplaza la vista
        # con cualquier herramienta.
        self._controlador = None
        self._mano_temporal = False

    # ------------------------------------------------------------------ datos
    def establecer_imagenes(self, antes: QImage, despues: Optional[QImage], tam: tuple[int, int]) -> None:
        nueva = tam != self._tam or self._antes is None
        self._antes = antes
        self._despues = despues
        self._tam = tam
        self._cache.clear()
        if nueva:
            self._ajustar = True
            self._division = 0.5
            self._ajustar_a_ventana()
            if self._es_pincel():
                self._preparar_lienzo()
        self.update()

    def establecer_despues(self, despues: QImage) -> None:
        self._despues = despues
        self._cache.pop("despues", None)
        self.update()

    def establecer_antes(self, antes: QImage) -> None:
        """Otro "Antes" del mismo tamaño (por ejemplo, la composición de las capas sin el filtro)."""
        if antes is self._antes:
            return
        self._antes = antes
        self._cache.pop("antes", None)
        self.update()

    @property
    def antes(self) -> Optional[QImage]:
        return self._antes

    @property
    def modo(self) -> str:
        return self._modo

    def establecer_procesando(self, activo: bool, texto: Optional[str] = None) -> None:
        texto = texto or "Procesando…"
        if activo != self._procesando or texto != self._texto_procesando:
            self._procesando = activo
            self._texto_procesando = texto
            self.update()

    def tiene_imagen(self) -> bool:
        return self._antes is not None

    def vaciar(self) -> None:
        """Sin foto (después de "Quitar todas las fotos"): vuelve la invitación a abrir una."""
        self._antes = None
        self._despues = None
        self._tam = (0, 0)
        self._cache.clear()
        self._procesando = False
        self._ajustar = True
        self._sel = None
        self._superposiciones = []
        self.update()

    # ----------------------------------------------------------- herramientas
    @property
    def herramienta(self) -> Optional[str]:
        return self._herramienta

    def establecer_herramienta(self, herramienta: Optional[str], forma: str = "rect",
                               aspecto: Optional[float] = None, inicial: Optional[QRectF] = None,
                               trazos: tuple = (), base: Optional[np.ndarray] = None,
                               contornos: tuple = (), desplazamiento: tuple = (0.0, 0.0),
                               imagen_clon: Optional[QImage] = None,
                               transformador: Optional[HerramientaTransformar] = None,
                               controlador=None) -> None:
        """``trazos``: con el pincel, lo ya pintado (normalizado a la imagen mostrada).
        ``base``: con el pincel, la máscara de partida (cielo, piel...) que se corrige.
        ``contornos`` y ``desplazamiento``: al clonar, la zona (normalizada) y el
        desplazamiento actual hacia la fuente (en píxeles de la imagen mostrada).
        ``imagen_clon``: de dónde se copia (la foto con los borrados anteriores); sin
        ella, la imagen "antes".
        ``transformador``: con "transformar", la herramienta con las manijas de la capa.
        ``controlador``: con "ps", el de las herramientas del modo Photoshop (ver ``__init__``)."""
        self._herramienta = herramienta
        self._transformar = transformador if herramienta == "transformar" else None
        self._controlador = controlador if herramienta == "ps" else None
        self._manija_hover = None
        self._forma = forma
        self._aspecto = aspecto
        self._puntos = []
        self._cursor_img = None
        w, h = self._tam
        self._sel = None if inicial is None else QRectF(
            inicial.x() * w, inicial.y() * h, inicial.width() * w, inicial.height() * h)
        self._trazos_previos, self._trazos, self._trazo = tuple(trazos), [], []
        self._lienzo = self._alfa = self._rgba = self._capa_pintura = None
        self._base_pincel = base
        self._clon_contornos = list(contornos)
        self._clon_camino = QPainterPath()
        self._clon_camino.setFillRule(Qt.WindingFill)
        for contorno in self._clon_contornos:
            self._clon_camino.addPolygon(QPolygonF([QPointF(x * w, y * h) for x, y in contorno]))
            self._clon_camino.closeSubpath()
        self._clon_d = QPointF(*desplazamiento)
        self._clon_inicio = None
        self._clon_imagen = imagen_clon
        if self._es_pincel():
            self._preparar_lienzo()
        self.setCursor(self._cursor_herramienta())
        if herramienta:
            self.setFocus()
        self.update()

    def establecer_cuadricula(self, visible: bool) -> None:
        self._cuadricula = bool(visible)
        self.update()

    @property
    def desplazamiento_clon(self) -> tuple[float, float]:
        return self._clon_d.x(), self._clon_d.y()

    def _marca_con_mouse(self) -> bool:
        """Herramientas que usan el arrastre para marcar (en las otras, arrastrar desplaza)."""
        return self._herramienta in ("zona", "recorte")

    @property
    def transformador(self) -> Optional[HerramientaTransformar]:
        return self._transformar

    @property
    def controlador(self):
        return self._controlador

    def establecer_mano_temporal(self, activa: bool) -> None:
        """Espacio sostenido en el modo Photoshop: arrastrar desplaza la vista, con cualquier herramienta."""
        if bool(activa) == self._mano_temporal:
            return
        self._mano_temporal = bool(activa)
        if self._arrastre != "pan":
            self.setCursor(Qt.OpenHandCursor if self._mano_temporal else self._cursor_herramienta())

    @property
    def mano_temporal(self) -> bool:
        return self._mano_temporal

    def a_documento(self, pos: QPointF) -> QPointF:
        """Una posición del widget en píxeles del documento (puede salirse de la imagen)."""
        return (self._local(QPointF(pos)) - self._origen) / self._zoom

    def a_pantalla(self, q: QPointF) -> QPointF:
        """Un punto del documento en coordenadas del widget."""
        return QPointF(self._origen.x() + q.x() * self._zoom, self._origen.y() + q.y() * self._zoom)

    def _cursor_herramienta(self) -> Qt.CursorShape:
        if self._mano_temporal:
            return Qt.OpenHandCursor
        if self._controlador is not None:
            return self._controlador.cursor(None)
        if self._transformar is not None:
            return HerramientaTransformar.cursor(self._manija_hover, self._transformar.transform.rotacion)
        if self._es_pincel():
            return Qt.BlankCursor  # se dibuja el círculo del pincel
        if self._herramienta == "clonar":
            return Qt.SizeAllCursor
        return Qt.CrossCursor if self._marca_con_mouse() else Qt.OpenHandCursor

    def establecer_aspecto(self, aspecto: Optional[float]) -> None:
        self._aspecto = aspecto
        if self._sel is not None and aspecto:
            # Mantiene el centro y ajusta la proporción dentro de la imagen.
            c = self._sel.center()
            w, h = self._sel.width(), self._sel.height()
            if w / max(h, 1e-6) > aspecto:
                w = h * aspecto
            else:
                h = w / aspecto
            self._sel = self._limitar_sel(QRectF(c.x() - w / 2, c.y() - h / 2, w, h))
        self.update()

    def seleccion_normalizada(self) -> Optional[QRectF]:
        w, h = self._tam
        if self._sel is None or not w or not h:
            return None
        r = self._sel.normalized()
        return QRectF(r.x() / w, r.y() / h, r.width() / w, r.height() / h)

    def _es_lazo(self) -> bool:
        return self._herramienta == "zona" and self._forma in ("lazo", "poligono")

    def _cerca_del_primero(self, q: QPointF) -> bool:
        if len(self._puntos) < 3:
            return False
        d = (q - self._puntos[0]) * self._zoom
        return (d.x() ** 2 + d.y() ** 2) ** 0.5 < 10

    def _terminar_lazo(self) -> None:
        w, h = self._tam
        puntos = self._puntos
        self._puntos, self._cursor_img = [], None
        if len(puntos) < 3 or not w or not h:
            self.update()
            return
        # Se simplifica el trazo a mano (cientos de puntos casi alineados).
        import numpy as np
        import cv2
        arr = np.array([[q.x(), q.y()] for q in puntos], dtype=np.float32).reshape(-1, 1, 2)
        arr = cv2.approxPolyDP(arr, max(0.6 / self._zoom, 0.5), True).reshape(-1, 2)
        if len(arr) < 3:
            self.update()
            return
        self.formaTerminada.emit([(float(x) / w, float(y) / h) for x, y in arr])
        self.update()

    # ------------------------------------------------------------------ pincel
    def _es_pincel(self) -> bool:
        return self._herramienta == "zona" and self._forma == "pincel"

    @property
    def pintando(self) -> bool:
        return self._es_pincel()

    @property
    def pincel(self) -> tuple[int, int, bool]:
        """(tamaño, dureza, goma) del pincel."""
        return self._pincel_tam, self._pincel_dureza, self._goma

    def establecer_pincel(self, tam: Optional[int] = None, dureza: Optional[int] = None,
                          goma: Optional[bool] = None) -> None:
        if tam is not None:
            self._pincel_tam = max(0, min(100, int(tam)))
        if dureza is not None:
            self._pincel_dureza = max(0, min(100, int(dureza)))
        if goma is not None:
            self._goma = bool(goma)
        if self._es_pincel() and not self.underMouse() and self._tam[0]:
            # Se muestra el pincel un momento en el centro para ver cómo quedó.
            centro = QPointF(self._ancho_vista() / 2, self.height() / 2)
            self._cursor_img = self._a_imagen(centro)
            self._timer_muestra.start()
        self.update()

    def _ocultar_muestra(self) -> None:
        if not self.underMouse():
            self._cursor_img = None
            self.update()

    def _radio_img(self) -> float:
        """Radio del pincel en píxeles de la imagen mostrada."""
        return radio_pincel(self._pincel_tam) * max(self._tam)

    def _preparar_lienzo(self) -> None:
        """Lienzo reducido con lo ya pintado (más los trazos nuevos, si los hay)."""
        w, h = self._tam
        if not w or not h:
            return
        f = min(1.0, LADO_LIENZO / max(w, h))
        lw, lh = max(1, round(w * f)), max(1, round(h * f))
        inicial = None
        if self._base_pincel is not None:
            inicial = cv2.resize(np.ascontiguousarray(self._base_pincel, dtype=np.float32), (lw, lh),
                                 interpolation=cv2.INTER_AREA)
        self._lienzo = mascara_trazos(self._trazos_previos + tuple(self._trazos), lh, lw, max(lw, lh), inicial)
        self._alfa = np.zeros((lh, lw), np.float32)
        self._rgba = np.zeros((lh, lw, 4), np.uint8)
        self._caja_trazo = None
        self._componer(slice(0, lh), slice(0, lw))

    def _componer(self, filas: slice, cols: slice) -> None:
        """Actualiza el rosa de lo pintado en esa parte del lienzo."""
        base, a = self._lienzo[filas, cols], self._alfa[filas, cols]
        m = base * (1.0 - a) if self._trazo_borra else np.maximum(base, a)
        self._rgba[filas, cols] = (m[..., None] * COLOR_PINTURA + 0.5).astype(np.uint8)
        lh, lw = self._lienzo.shape
        self._capa_pintura = QImage(self._rgba.data, lw, lh, lw * 4, QImage.Format_RGBA8888_Premultiplied)

    def _pintar_tramo(self, puntos: list[QPointF]) -> None:
        """Suma un tramo del trazo en curso al lienzo reducido."""
        if self._lienzo is None:
            return
        lh, lw = self._lienzo.shape
        fx, fy = lw / self._tam[0], lh / self._tam[1]
        pts = np.array([[q.x() * fx, q.y() * fy] for q in puntos], np.float64)
        radio, dureza = self._trazo_pincel
        res = alfa_trazo(pts, radio * max(lw, lh), dureza, lh, lw)
        if res is None:
            return
        filas, cols, a = res
        np.maximum(self._alfa[filas, cols], a, out=self._alfa[filas, cols])
        c = self._caja_trazo
        self._caja_trazo = [filas.start, filas.stop, cols.start, cols.stop] if c is None else [
            min(c[0], filas.start), max(c[1], filas.stop), min(c[2], cols.start), max(c[3], cols.stop)]
        self._componer(filas, cols)

    def _cerrar_trazo(self) -> None:
        """Termina el trazo en curso: queda en el lienzo y en la lista de trazos nuevos."""
        puntos, self._trazo = self._trazo, []
        if not puntos or self._lienzo is None:
            return
        if self._caja_trazo is not None:
            y0, y1, x0, x1 = self._caja_trazo
            filas, cols = slice(y0, y1), slice(x0, x1)
            a = self._alfa[filas, cols]
            if self._trazo_borra:
                self._lienzo[filas, cols] *= 1.0 - a
            else:
                np.maximum(self._lienzo[filas, cols], a, out=self._lienzo[filas, cols])
            a[...] = 0.0
            self._caja_trazo = None
        # Se simplifica el trazo (muchos puntos casi alineados) sin que se note.
        arr = np.array([[q.x(), q.y()] for q in puntos], np.float32)
        if len(arr) > 2:
            arr = cv2.approxPolyDP(arr.reshape(-1, 1, 2), max(0.35 / self._zoom, 0.25), False).reshape(-1, 2)
        w, h = self._tam
        radio, dureza = self._trazo_pincel
        self._trazos.append((tuple((float(x) / w, float(y) / h) for x, y in arr), radio, dureza, self._trazo_borra))
        self._trazo_borra = False

    def deshacer_trazo(self) -> bool:
        """Quita el último trazo nuevo. Devuelve False si no había ninguno."""
        if self._trazo or not self._trazos:
            return False
        self._trazos.pop()
        self._preparar_lienzo()
        self.update()
        return True

    def terminar_pincel(self) -> None:
        """Listo: entrega los trazos nuevos (la ventana los suma a la zona)."""
        if not self._es_pincel():
            return
        self._cerrar_trazo()
        self._arrastre = None
        self.trazosTerminados.emit(list(self._trazos))

    def establecer_superposiciones(self, lista: list[tuple]) -> None:
        self._superposiciones = list(lista)
        self.update()

    def _a_imagen(self, pos: QPointF) -> QPointF:
        q = (pos - self._origen) / self._zoom
        return QPointF(min(max(q.x(), 0.0), self._tam[0]), min(max(q.y(), 0.0), self._tam[1]))

    def _limitar_sel(self, r: QRectF) -> QRectF:
        w, h = self._tam
        r = r.normalized()
        if r.width() > w or r.height() > h:
            f = min(w / max(r.width(), 1e-6), h / max(r.height(), 1e-6))
            c = r.center()
            r = QRectF(c.x() - r.width() * f / 2, c.y() - r.height() * f / 2, r.width() * f, r.height() * f)
        dx = -r.left() if r.left() < 0 else (w - r.right() if r.right() > w else 0.0)
        dy = -r.top() if r.top() < 0 else (h - r.bottom() if r.bottom() > h else 0.0)
        return r.translated(dx, dy)

    def _sel_desde(self, inicio: QPointF, fin: QPointF) -> QRectF:
        dx, dy = fin.x() - inicio.x(), fin.y() - inicio.y()
        if self._herramienta == "recorte" and self._aspecto:
            w, h = abs(dx), abs(dy)
            if w / max(h, 1e-6) > self._aspecto:
                w = h * self._aspecto
            else:
                h = w / self._aspecto
            dx = w if dx >= 0 else -w
            dy = h if dy >= 0 else -h
        return self._limitar_sel(QRectF(inicio, QPointF(inicio.x() + dx, inicio.y() + dy)))

    def _rect_pantalla(self, r_img: QRectF) -> QRectF:
        return QRectF(self._origen.x() + r_img.x() * self._zoom, self._origen.y() + r_img.y() * self._zoom,
                      r_img.width() * self._zoom, r_img.height() * self._zoom)

    def _dibujar_herramientas(self, p: QPainter) -> None:
        paneles = [0.0]
        if self._lado_a_lado():
            paneles = [0.0, self._ancho_vista() + SEPARACION]
        w, h = self._tam
        for x0 in paneles:
            p.save()
            p.setClipRect(QRectF(x0, 0, self._ancho_vista(), self.height()), Qt.IntersectClip)
            p.translate(x0, 0)
            p.setRenderHint(QPainter.Antialiasing, True)
            for texto, forma, rn, *extra in self._superposiciones:
                r = self._rect_pantalla(QRectF(rn.x() * w, rn.y() * h, rn.width() * w, rn.height() * h))
                pen = QPen(QColor(estilo.MAGENTA), 1.6, Qt.DashLine)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                puntos = extra[0] if extra else ()
                if forma == "pincel":
                    # Zona pintada: contorno de lo pintado (puede tener varias partes).
                    p.setBrush(QColor(236, 72, 153, 28))
                    camino = QPainterPath()
                    camino.setFillRule(Qt.OddEvenFill)
                    for contorno in puntos:
                        camino.addPolygon(QPolygonF([QPointF(self._origen.x() + x * w * self._zoom,
                                                             self._origen.y() + y * h * self._zoom)
                                                     for x, y in contorno]))
                        camino.closeSubpath()
                    p.drawPath(camino)
                elif puntos:
                    p.drawPolygon(QPolygonF([QPointF(self._origen.x() + x * w * self._zoom,
                                                     self._origen.y() + y * h * self._zoom) for x, y in puntos]))
                elif forma == "elipse":
                    p.drawEllipse(r)
                else:
                    p.drawRect(r)
                self._etiqueta_chica(p, texto, r.topLeft())
            if self._es_lazo() and self._puntos:
                pantalla = [self._origen + q * self._zoom for q in self._puntos]
                if self._forma == "poligono" and self._cursor_img is not None:
                    pantalla.append(self._origen + self._cursor_img * self._zoom)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(217, 70, 239, 45))
                p.drawPolygon(QPolygonF(pantalla))
                p.setPen(QPen(QColor(estilo.MAGENTA), 2))
                p.setBrush(Qt.NoBrush)
                p.drawPolyline(QPolygonF(pantalla))
                p.setPen(QPen(QColor(255, 255, 255, 140), 1, Qt.DashLine))
                p.drawLine(pantalla[-1], pantalla[0])  # cómo se va a cerrar
                if self._forma == "poligono":
                    p.setPen(QPen(QColor(estilo.MAGENTA), 1.5))
                    for i, q in enumerate(pantalla[:len(self._puntos)]):
                        cerca = i == 0 and self._cursor_img is not None and self._cerca_del_primero(self._cursor_img)
                        p.setBrush(QColor("#ffffff") if cerca else QColor(estilo.MAGENTA))
                        p.drawEllipse(q, 6 if cerca else 3.5, 6 if cerca else 3.5)
            if self._es_pincel():
                self._dibujar_pincel(p)
            if self._herramienta == "enderezar" and self._cuadricula:
                self._dibujar_cuadricula(p)
            if self._herramienta == "clonar":
                self._dibujar_clon(p)
            if self._transformar is not None:
                origen, zoom = self._origen, self._zoom
                self._transformar.dibujar(p, lambda q: QPointF(origen.x() + q.x() * zoom, origen.y() + q.y() * zoom),
                                          zoom)
            if self._controlador is not None:
                origen, zoom = self._origen, self._zoom
                self._controlador.dibujar(p, lambda q: QPointF(origen.x() + q.x() * zoom, origen.y() + q.y() * zoom),
                                          zoom)
            if self._sel is not None and self._marca_con_mouse():
                r = self._rect_pantalla(self._sel.normalized())
                if self._herramienta == "recorte":
                    afuera = QPainterPath()
                    afuera.addRect(QRectF(0, 0, self._ancho_vista(), self.height()))
                    adentro = QPainterPath()
                    adentro.addRect(r)
                    p.fillPath(afuera.subtracted(adentro), QColor(0, 0, 0, 150))
                    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
                    for i in (1, 2):  # regla de los tercios
                        p.drawLine(QPointF(r.left() + r.width() * i / 3, r.top()),
                                   QPointF(r.left() + r.width() * i / 3, r.bottom()))
                        p.drawLine(QPointF(r.left(), r.top() + r.height() * i / 3),
                                   QPointF(r.right(), r.top() + r.height() * i / 3))
                    p.setPen(QPen(QColor("#ffffff"), 1.6))
                    p.setBrush(Qt.NoBrush)
                    p.drawRect(r)
                    p.setBrush(QColor("#ffffff"))
                    for esquina in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
                        p.drawRect(QRectF(esquina.x() - 4, esquina.y() - 4, 8, 8))
                    self._etiqueta_chica(p, f"{round(self._sel.width())} × {round(self._sel.height())} px",
                                         QPointF(r.left(), r.bottom() + 24))
                else:
                    p.setPen(QPen(QColor(estilo.MAGENTA), 2))
                    p.setBrush(QColor(217, 70, 239, 45))
                    p.drawEllipse(r) if self._forma == "elipse" else p.drawRect(r)
            p.restore()

    def _dibujar_cuadricula(self, p: QPainter) -> None:
        """Cuadrícula de guía para enderezar: celdas cuadradas, 8 a lo largo del lado largo."""
        r = self._rect_imagen()
        paso = max(r.width(), r.height()) / 8.0
        if paso < 4:
            return
        p.save()
        p.setClipRect(r, Qt.IntersectClip)
        lineas = []
        x = r.left() + paso
        while x < r.right() - 1:
            lineas.append((QPointF(x, r.top()), QPointF(x, r.bottom())))
            x += paso
        y = r.top() + paso
        while y < r.bottom() - 1:
            lineas.append((QPointF(r.left(), y), QPointF(r.right(), y)))
            y += paso
        # Sombra oscura y línea clara: se ven tanto sobre el cielo como sobre la sombra.
        p.setPen(QPen(QColor(0, 0, 0, 70), 2.2))
        for a, b in lineas:
            p.drawLine(a, b)
        p.setPen(QPen(QColor(255, 255, 255, 120), 1))
        for a, b in lineas:
            p.drawLine(a, b)
        p.restore()

    def _dibujar_clon(self, p: QPainter) -> None:
        """Clonar: la zona marcada muestra lo que se va a copiar y la fuente se ve con línea de puntos."""
        if self._clon_camino.isEmpty():
            return
        a_pantalla = QTransform(self._zoom, 0, 0, self._zoom, self._origen.x(), self._origen.y())
        zona = a_pantalla.map(self._clon_camino)
        d = self._clon_d * self._zoom
        hay_fuente = abs(self._clon_d.x()) > 1e-6 or abs(self._clon_d.y()) > 1e-6
        img = self._clon_imagen if self._clon_imagen is not None else self._antes
        if hay_fuente and img is not None:
            destino = self._rect_imagen().translated(-d.x(), -d.y())
            visible = zona.boundingRect().intersected(destino).intersected(
                QRectF(0, 0, self._ancho_vista(), self.height()))
            if not visible.isEmpty():
                ex, ey = img.width() / destino.width(), img.height() / destino.height()
                fuente = QRectF((visible.x() - destino.x()) * ex, (visible.y() - destino.y()) * ey,
                                visible.width() * ex, visible.height() * ey)
                p.save()
                p.setClipPath(zona, Qt.IntersectClip)
                p.setRenderHint(QPainter.SmoothPixmapTransform, True)
                p.drawImage(visible, img, fuente)
                p.restore()
            fuente_camino = zona.translated(d.x(), d.y())
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(0, 0, 0, 150), 3))
            p.drawPath(fuente_camino)
            p.setPen(QPen(QColor("#ffffff"), 1.6, Qt.DashLine))
            p.drawPath(fuente_camino)
            c1 = zona.boundingRect().center()
            c2 = c1 + d
            p.setPen(QPen(QColor(255, 255, 255, 200), 1.4, Qt.DashLine))
            p.drawLine(c1, c2)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(c2, 3.5, 3.5)
            self._etiqueta_chica(p, "Fuente", fuente_camino.boundingRect().topLeft())
        p.setBrush(Qt.NoBrush if hay_fuente else QColor(236, 72, 153, 60))
        p.setPen(QPen(QColor(estilo.MAGENTA), 2))
        p.drawPath(zona)

    def _dibujar_pincel(self, p: QPainter) -> None:
        """Lo pintado en rosa y el círculo del pincel bajo el cursor."""
        img = self._capa_pintura
        if img is not None:
            # Solo la parte visible del lienzo, escalada a la imagen en pantalla.
            destino = self._rect_imagen()
            visible = destino.intersected(QRectF(0, 0, self._ancho_vista(), self.height()))
            if not visible.isEmpty():
                ex, ey = img.width() / destino.width(), img.height() / destino.height()
                fuente = QRectF((visible.x() - destino.x()) * ex, (visible.y() - destino.y()) * ey,
                                visible.width() * ex, visible.height() * ey)
                p.save()
                p.setRenderHint(QPainter.SmoothPixmapTransform, True)
                p.drawImage(visible, img, fuente)
                p.restore()
        if self._cursor_img is None:
            return
        c = self._origen + self._cursor_img * self._zoom
        r = max(self._radio_img() * self._zoom, 1.5)
        borra = self._trazo_borra if self._trazo else self._goma
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 150), 3))
        p.drawEllipse(c, r, r)
        p.setPen(QPen(QColor("#ffffff"), 1.4, Qt.DashLine if borra else Qt.SolidLine))
        p.drawEllipse(c, r, r)
        if self._pincel_dureza < 100 and r > 6:
            # Hasta dónde pinta al 100 %: el resto del radio es el borde suave.
            rd = max(r * self._pincel_dureza / 100.0, 1.0)
            p.setPen(QPen(QColor(255, 255, 255, 110), 1, Qt.DotLine))
            p.drawEllipse(c, rd, rd)
        # Cruz chica en el centro (con la goma, solo una raya: "restar").
        p.setPen(QPen(QColor("#ffffff"), 1.2))
        p.drawLine(c + QPointF(-4, 0), c + QPointF(4, 0))
        if not borra:
            p.drawLine(c + QPointF(0, -4), c + QPointF(0, 4))

    def _etiqueta_chica(self, p: QPainter, texto: str, pos: QPointF) -> None:
        fuente = QFont(self.font())
        fuente.setPointSizeF(8.5)
        fuente.setBold(True)
        p.setFont(fuente)
        m = p.fontMetrics()
        rect = QRectF(pos.x(), pos.y() - m.height() - 6, m.horizontalAdvance(texto) + 12, m.height() + 4)
        # Siempre a la vista y sin tapar las etiquetas "Antes" y "Después" de arriba.
        x = min(max(rect.x(), 8.0), max(8.0, self._ancho_vista() - rect.width() - 8))
        y = min(max(rect.y(), 52.0), max(52.0, self.height() - rect.height() - 8))
        rect.moveTo(x, y)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20, 10, 18, 210))
        p.drawRoundedRect(rect, 5, 5)
        p.setPen(QColor("#ffffff"))
        p.drawText(rect, Qt.AlignCenter, texto)

    # ------------------------------------------------------------------- modo
    def establecer_modo(self, modo: str) -> None:
        if modo == self._modo:
            return
        # El punto de la imagen que estaba en el centro sigue en el centro.
        centro_img = (QPointF(self._ancho_vista() / 2, self.height() / 2) - self._origen) / self._zoom
        self._modo = modo
        self._cache.clear()
        if self._ajustar:
            self._ajustar_a_ventana()
        else:
            self._origen = QPointF(self._ancho_vista() / 2, self.height() / 2) - centro_img * self._zoom
            self._limitar_origen()
        self.update()

    def _lado_a_lado(self) -> bool:
        return self._modo == self.MODO_LADO

    def _ancho_vista(self) -> float:
        """Ancho del área donde se ve la imagen (la mitad en el modo lado a lado)."""
        if self._lado_a_lado():
            return max(1.0, (self.width() - SEPARACION) / 2)
        return float(self.width())

    def _local(self, pos: QPointF) -> QPointF:
        """Convierte una posición del widget a coordenadas del panel bajo el cursor."""
        if self._lado_a_lado() and pos.x() > self._ancho_vista() + SEPARACION / 2:
            return QPointF(pos.x() - self._ancho_vista() - SEPARACION, pos.y())
        return QPointF(pos)

    def mostrar_antes_temporal(self, activo: bool) -> None:
        self._modo_temporal = self.MODO_ANTES if activo else None
        self.update()

    def _modo_efectivo(self) -> str:
        return self._modo_temporal or self._modo

    # ------------------------------------------------------------------- zoom
    @property
    def zoom(self) -> float:
        return self._zoom

    def _zoom_ajuste(self) -> float:
        w, h = self._tam
        if not w or not h:
            return 1.0
        return max(ZOOM_MIN, min(self._ancho_vista() / w, self.height() / h) * 0.97)

    def _ajustar_a_ventana(self) -> None:
        w, h = self._tam
        if not w:
            return
        self._zoom = self._zoom_ajuste()
        self._origen = QPointF((self._ancho_vista() - w * self._zoom) / 2, (self.height() - h * self._zoom) / 2)
        self.zoomCambiado.emit(self._zoom)

    def ajustar(self) -> None:
        self._ajustar = True
        self._ajustar_a_ventana()
        self.update()

    def fijar_zoom(self, zoom: float, centro: Optional[QPointF] = None) -> None:
        if not self._tam[0]:
            return
        zoom = max(min(self._zoom_ajuste(), 0.1), min(ZOOM_MAX, zoom))
        centro = centro or QPointF(self._ancho_vista() / 2, self.height() / 2)
        # Mantener fijo el punto de la imagen bajo el cursor.
        p = (centro - self._origen) / self._zoom
        self._zoom = zoom
        self._origen = centro - p * zoom
        self._ajustar = False
        self._limitar_origen()
        self.zoomCambiado.emit(self._zoom)
        self.update()

    def acercar(self) -> None:
        self.fijar_zoom(self._zoom * 1.25)

    def alejar(self) -> None:
        self.fijar_zoom(self._zoom / 1.25)

    def _limitar_origen(self) -> None:
        w, h = self._tam[0] * self._zoom, self._tam[1] * self._zoom
        x, y = self._origen.x(), self._origen.y()
        ancho = self._ancho_vista()
        x = (ancho - w) / 2 if w <= ancho else min(0.0, max(ancho - w, x))
        y = (self.height() - h) / 2 if h <= self.height() else min(0.0, max(self.height() - h, y))
        self._origen = QPointF(x, y)

    # ---------------------------------------------------------------- dibujo
    def _rect_imagen(self) -> QRectF:
        return QRectF(self._origen.x(), self._origen.y(), self._tam[0] * self._zoom, self._tam[1] * self._zoom)

    def _dibujar(self, p: QPainter, clave: str, img: QImage) -> None:
        """Dibuja ``img`` (que puede ser una versión reducida) ocupando la imagen completa."""
        destino = self._rect_imagen()
        escala = destino.width() / img.width()
        if escala < 1.0:
            # Reducción de calidad cacheada por nivel de zoom: el desplazamiento es fluido.
            tam = (max(1, round(img.width() * escala)), max(1, round(img.height() * escala)))
            firma = (img.cacheKey(), tam)
            guardado = self._cache.get(clave)
            if guardado is None or guardado[0] != firma:
                pix = QPixmap.fromImage(img.scaled(tam[0], tam[1], Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
                self._cache[clave] = (firma, pix)
            pix = self._cache[clave][1]
            p.drawPixmap(destino.topLeft(), pix)
        else:
            # Solo la parte visible; sin suavizado a partir de 200 % para ver píxeles reales.
            visible = destino.intersected(QRectF(0, 0, self._ancho_vista(), self.height()))
            if visible.isEmpty():
                return
            fuente = QRectF(
                (visible.x() - destino.x()) / escala, (visible.y() - destino.y()) / escala,
                visible.width() / escala, visible.height() / escala,
            )
            p.setRenderHint(QPainter.SmoothPixmapTransform, escala < 2.0)
            p.drawImage(visible, img, fuente)

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        # Área de imagen redondeada dentro de la tarjeta.
        marco = QPainterPath()
        marco.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
        p.fillRect(self.rect(), QColor(estilo.TARJETA))
        p.fillPath(marco, QColor("#1e1f22"))
        if self._antes is None:
            self._dibujar_invitacion(p)
            p.end()
            return
        p.setClipPath(marco)

        modo = self._modo_efectivo()
        despues = self._despues or self._antes
        if self._herramienta in ("recorte", "enderezar") and not self._lado_a_lado():
            # Al recortar se ve solo la foto, sin divisor ni etiquetas.
            self._dibujar(p, "antes", self._antes)
        elif self._lado_a_lado():
            # Con la barra espaciadora, los dos paneles muestran el original.
            derecha = self._antes if modo == self.MODO_ANTES else despues
            ancho = self._ancho_vista()
            for i, (clave, img, texto) in enumerate((("antes", self._antes, "Antes"),
                                                     ("despues", derecha, "Después"))):
                x0 = i * (ancho + SEPARACION)
                p.save()
                p.setClipRect(QRectF(x0, 0, ancho, self.height()), Qt.IntersectClip)
                p.translate(x0, 0)
                self._dibujar(p, clave, img)
                p.restore()
                self._etiqueta(p, texto, QPointF(x0 + 14, 14))
            p.fillRect(QRectF(ancho, 0, SEPARACION, self.height()), QColor(estilo.TARJETA))
        elif self._modo == self.MODO_SOLO:
            # Modo Photoshop: la imagen sola (la barra espaciadora no muestra otra cosa).
            self._dibujar(p, "despues", despues)
        elif modo == self.MODO_ANTES:
            self._dibujar(p, "antes", self._antes)
            self._etiqueta(p, "Antes", QPointF(14, 14))
        elif modo == self.MODO_DESPUES:
            self._dibujar(p, "despues", despues)
            self._etiqueta(p, "Después", QPointF(14, 14))
        else:
            x = self._division * self.width()
            p.save()
            p.setClipRect(QRectF(0, 0, x, self.height()), Qt.IntersectClip)
            self._dibujar(p, "antes", self._antes)
            p.restore()
            p.save()
            p.setClipRect(QRectF(x, 0, self.width() - x, self.height()), Qt.IntersectClip)
            self._dibujar(p, "despues", despues)
            p.restore()
            self._dibujar_divisor(p, x)
            self._etiqueta(p, "Antes", QPointF(14, 14))
            self._etiqueta(p, "Después", QPointF(self.width() - 14, 14), derecha=True)

        self._dibujar_herramientas(p)
        if self._procesando:
            self._etiqueta(p, self._texto_procesando, QPointF(self.width() / 2, self.height() - 40), centro=True)
        if self._arrastrando_archivo:
            self._dibujar_marco_soltar(p)
        p.setClipping(False)
        p.setPen(QPen(QColor(estilo.BORDE), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(marco)
        p.end()

    def _dibujar_divisor(self, p: QPainter, x: float) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor(255, 255, 255, 220), 2))
        p.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        cy = self.height() / 2
        p.setBrush(QColor(255, 255, 255, 245))
        p.setPen(QPen(QColor(estilo.MAGENTA), 3))
        p.drawEllipse(QPointF(x, cy), 15, 15)
        p.setPen(QPen(QColor(estilo.VIOLETA), 2))
        for signo in (-1, 1):
            camino = QPainterPath()
            camino.moveTo(x + signo * 3, cy - 5)
            camino.lineTo(x + signo * 8, cy)
            camino.lineTo(x + signo * 3, cy + 5)
            p.setBrush(Qt.NoBrush)
            p.drawPath(camino)

    def _etiqueta(self, p: QPainter, texto: str, pos: QPointF, derecha=False, centro=False) -> None:
        fuente = QFont(self.font())
        fuente.setPointSizeF(9.5)
        fuente.setBold(True)
        p.setFont(fuente)
        m = p.fontMetrics()
        ancho, alto = m.horizontalAdvance(texto) + 20, m.height() + 10
        x = pos.x() - ancho if derecha else (pos.x() - ancho / 2 if centro else pos.x())
        rect = QRectF(x, pos.y(), ancho, alto)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor(estilo.BORDE_SELECCION), 1))
        p.setBrush(QColor(20, 10, 18, 200))
        p.drawRoundedRect(rect, alto / 2, alto / 2)
        p.setPen(QColor("#ffffff"))
        p.drawText(rect, Qt.AlignCenter, texto)

    def _dibujar_invitacion(self, p: QPainter) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(28, 28, -28, -28)
        color = QColor(estilo.MAGENTA) if self._arrastrando_archivo else QColor("#464951")
        pen = QPen(color, 2, Qt.DashLine)
        p.setPen(pen)
        p.setBrush(QColor(255, 255, 255, 8) if self._arrastrando_archivo else Qt.NoBrush)
        p.drawRoundedRect(rect, 18, 18)
        fuente = QFont(self.font())
        fuente.setPointSizeF(15)
        fuente.setBold(True)
        p.setFont(fuente)
        p.setPen(QColor(estilo.TEXTO))
        p.drawText(rect.adjusted(0, -30, 0, -30), Qt.AlignCenter, "Arrastrá una foto aquí")
        fuente.setPointSizeF(10.5)
        fuente.setBold(False)
        p.setFont(fuente)
        p.setPen(QColor(estilo.TEXTO_TENUE))
        p.drawText(rect.adjusted(0, 24, 0, 24), Qt.AlignCenter,
                   "o hacé clic para elegir un archivo  ·  JPG, PNG, WEBP, TIFF, BMP")
        fuente.setPointSizeF(9.5)
        p.setFont(fuente)
        if not edicion.es_lite():  # NaturalShot Lite es solo para fotos
            p.drawText(rect.adjusted(0, 60, 0, 60), Qt.AlignCenter, "¿Un video? Soltalo acá y se abre en el modo Video")

    def _dibujar_marco_soltar(self, p: QPainter) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor(estilo.MAGENTA), 3, Qt.DashLine))
        p.setBrush(QColor(217, 70, 239, 36))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(10, 10, -10, -10), 14, 14)
        self._etiqueta(p, "Soltá para abrir", QPointF(self.width() / 2, self.height() / 2 - 14), centro=True)

    # --------------------------------------------------------------- eventos
    def resizeEvent(self, evento) -> None:
        if self._ajustar:
            self._ajustar_a_ventana()
        else:
            self._limitar_origen()
        super().resizeEvent(evento)

    def wheelEvent(self, evento) -> None:
        if not self.tiene_imagen():
            return
        pasos = evento.angleDelta().y() / 120.0
        if pasos:
            self.fijar_zoom(self._zoom * (1.2 ** pasos), self._local(evento.position()))

    def _cerca_division(self, x: float) -> bool:
        return (self._herramienta is None and self._modo_efectivo() == self.MODO_DIVIDIR
                and abs(x - self._division * self.width()) < 18)

    def mousePressEvent(self, evento) -> None:
        if evento.button() == Qt.MiddleButton and self.tiene_imagen() and self._arrastre is None:
            # Rueda apretada: desplaza la foto aunque haya una herramienta activa.
            self._ultimo = evento.position()
            self._arrastre = "pan"
            self.setCursor(Qt.ClosedHandCursor)
            return
        if self._es_pincel() and evento.button() in (Qt.LeftButton, Qt.RightButton) and self._arrastre is None:
            # Clic izquierdo pinta; el derecho (o la goma) borra lo pintado de más.
            q = (self._local(evento.position()) - self._origen) / self._zoom  # puede salirse de la foto
            self._trazo = [q]
            self._trazo_borra = self._goma or evento.button() == Qt.RightButton
            self._trazo_pincel = (radio_pincel(self._pincel_tam), self._pincel_dureza)
            self._arrastre = "pincel"
            self._cursor_img = q
            self._pintar_tramo([q])
            self.update()
            return
        if evento.button() != Qt.LeftButton:
            return
        if not self.tiene_imagen():
            self.clicSinImagen.emit()
            return
        self._ultimo = evento.position()
        if self._mano_temporal:  # Espacio sostenido: desplaza, con cualquier herramienta
            self._arrastre = "pan"
            self.setCursor(Qt.ClosedHandCursor)
            return
        if self._controlador is not None:
            q = (self._local(evento.position()) - self._origen) / self._zoom
            if self._controlador.presionar(q, evento.position(), evento.modifiers()):
                self._arrastre = "ps"
            else:  # nada que agarrar (o la Mano): desplaza la vista
                self._arrastre = "pan"
                self.setCursor(Qt.ClosedHandCursor)
            self.update()
            return
        if self._transformar is not None:
            q = (self._local(evento.position()) - self._origen) / self._zoom  # puede salirse de la foto
            manija = self._transformar.manija_en(q, self._zoom)
            if manija is None:
                self._arrastre = "pan"  # lejos de la capa: desplaza la vista
                self.setCursor(Qt.ClosedHandCursor)
            else:
                self._transformar.empezar(manija, q)
                self._arrastre = "transformar"
            return
        if self._herramienta == "clonar":
            # Desde la zona hacia la fuente; si se agarra la fuente ya elegida, se la corre.
            q = (self._local(evento.position()) - self._origen) / self._zoom
            sobre_fuente = (not self._clon_camino.contains(q)
                            and self._clon_camino.contains(q - self._clon_d)
                            and (abs(self._clon_d.x()) > 1e-6 or abs(self._clon_d.y()) > 1e-6))
            self._clon_base = QPointF(self._clon_d) if sobre_fuente else QPointF(0, 0)
            self._clon_inicio = q
            self._arrastre = "clon"
            self.setCursor(Qt.ClosedHandCursor)
            return
        if self._es_lazo():
            q = self._a_imagen(self._local(evento.position()))
            if self._forma == "lazo":
                self._puntos = [q]
                self._arrastre = "lazo"
            elif self._cerca_del_primero(q):
                self._terminar_lazo()
            else:
                self._puntos.append(q)
            self.update()
            return
        if self._marca_con_mouse():
            self._sel_inicio = self._a_imagen(self._local(evento.position()))
            self._sel = QRectF(self._sel_inicio, self._sel_inicio)
            self._arrastre = "seleccion"
            self.update()
            return
        if self._herramienta == "enderezar":
            self._arrastre = "pan"
            self.setCursor(Qt.ClosedHandCursor)
            return
        if self._cerca_division(evento.position().x()):
            self._arrastre = "division"
        else:
            self._arrastre = "pan"
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, evento) -> None:
        pos = evento.position()
        if self._arrastre == "pan" and self._herramienta:
            self._origen += pos - self._ultimo
            self._ultimo = pos
            self._ajustar = False
            self._limitar_origen()
            self.update()
            return
        if self._arrastre == "ps" and self._controlador is not None:
            q = (self._local(pos) - self._origen) / self._zoom
            self._controlador.mover(q, evento.modifiers())
            self.update()
            return
        if self._controlador is not None and self._arrastre is None:
            q = (self._local(pos) - self._origen) / self._zoom
            self.setCursor(Qt.OpenHandCursor if self._mano_temporal else self._controlador.cursor(q))
            return
        if self._arrastre == "transformar" and self._transformar is not None:
            q = (self._local(pos) - self._origen) / self._zoom
            mods = evento.modifiers()
            t = self._transformar.arrastrar(q, bool(mods & Qt.ShiftModifier), bool(mods & Qt.AltModifier))
            self.transformacionCambiada.emit(t)
            self.update()
            return
        if self._transformar is not None:
            q = (self._local(pos) - self._origen) / self._zoom
            self._manija_hover = self._transformar.manija_en(q, self._zoom)
            self.setCursor(self._cursor_herramienta())
            return
        if self._es_pincel():
            q = (self._local(pos) - self._origen) / self._zoom
            self._cursor_img = q
            if self._arrastre == "pincel" and self._trazo:
                d = (q - self._trazo[-1]) * self._zoom
                if d.x() ** 2 + d.y() ** 2 >= 4:  # un punto cada ~2 px de pantalla
                    self._pintar_tramo([self._trazo[-1], q])
                    self._trazo.append(q)
            self.setCursor(Qt.BlankCursor)
            self.update()
            return
        if self._arrastre == "clon" and self._clon_inicio is not None:
            q = (self._local(pos) - self._origen) / self._zoom
            self._clon_d = self._clon_base + (q - self._clon_inicio)
            self.update()
            return
        if self._arrastre == "seleccion":
            self._sel = self._sel_desde(self._sel_inicio, self._a_imagen(self._local(pos)))
            self.update()
            return
        if self._arrastre == "lazo":
            q = self._a_imagen(self._local(pos))
            d = (q - self._puntos[-1]) * self._zoom
            if d.x() ** 2 + d.y() ** 2 >= 9:  # un punto cada ~3 px de pantalla
                self._puntos.append(q)
                self.update()
            return
        if self._es_lazo() and self._forma == "poligono":
            self._cursor_img = self._a_imagen(self._local(pos))
            self.setCursor(Qt.CrossCursor)
            self.update()
            return
        if self._marca_con_mouse() or self._herramienta == "clonar":
            self.setCursor(self._cursor_herramienta())
            return
        if self._arrastre == "division":
            self._division = max(0.0, min(1.0, pos.x() / max(1, self.width())))
            self.update()
        elif self._arrastre == "pan":
            self._origen += pos - self._ultimo
            self._ultimo = pos
            self._ajustar = False
            self._limitar_origen()
            self.update()
        elif self.tiene_imagen():
            self.setCursor(Qt.SplitHCursor if self._cerca_division(pos.x()) else Qt.OpenHandCursor)
        else:
            self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, evento) -> None:
        if self._arrastre == "ps":
            self._arrastre = None
            if self._controlador is not None:
                q = (self._local(evento.position()) - self._origen) / self._zoom
                self._controlador.soltar(q, evento.modifiers())
                self.setCursor(self._cursor_herramienta())
            self.update()
            return
        if self._arrastre == "transformar":
            self._arrastre = None
            if self._transformar is not None:
                self._transformar.soltar()
                self.transformacionCambiada.emit(self._transformar.transform)
            self.update()
            return
        if self._arrastre == "pincel":
            if evento.buttons() & (Qt.LeftButton | Qt.RightButton):
                return  # se soltó otro botón: el trazo sigue
            self._arrastre = None
            self._cerrar_trazo()
            self.update()
            return
        if self._arrastre == "lazo":
            self._arrastre = None
            self._terminar_lazo()  # al soltar, la forma se cierra sola
            return
        if self._arrastre == "clon":
            self._arrastre = None
            self._clon_inicio = None
            self.setCursor(self._cursor_herramienta())
            self.clonCambiado.emit(self._clon_d.x(), self._clon_d.y())
            self.update()
            return
        if self._arrastre == "seleccion":
            self._arrastre = None
            if self._sel is not None and min(self._sel.width(), self._sel.height()) * self._zoom >= 6:
                self.seleccionTerminada.emit(self.seleccion_normalizada())
            elif self._herramienta == "zona":
                self._sel = None
            self.update()
            return
        self._arrastre = None
        if self.tiene_imagen():
            self.setCursor(self._cursor_herramienta())

    def leaveEvent(self, evento) -> None:
        if self._es_pincel() and self._arrastre != "pincel":
            self._cursor_img = None  # el círculo del pincel se va con el mouse
            self.update()
        if self._controlador is not None and hasattr(self._controlador, "salio"):
            self._controlador.salio()  # modo Photoshop: también el círculo de su pincel
        super().leaveEvent(evento)

    def keyPressEvent(self, evento) -> None:
        if self._controlador is not None and self._controlador.tecla(evento):
            self.update()
            return
        if evento.key() == Qt.Key_Escape and self._herramienta:
            self.seleccionCancelada.emit()
            return
        if (evento.key() in (Qt.Key_Return, Qt.Key_Enter)
                and self._herramienta in ("recorte", "enderezar", "clonar", "transformar")):
            self.confirmado.emit()
            return
        if self._transformar is not None and evento.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            # Flechas: de a 1 píxel del documento (con Mayús, de a 10).
            paso = 10.0 if evento.modifiers() & Qt.ShiftModifier else 1.0
            dx = {Qt.Key_Left: -paso, Qt.Key_Right: paso}.get(evento.key(), 0.0)
            dy = {Qt.Key_Up: -paso, Qt.Key_Down: paso}.get(evento.key(), 0.0)
            self.transformacionCambiada.emit(self._transformar.mover(dx, dy))
            self.update()
            return
        if self._es_pincel():
            k = evento.key()
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self.terminar_pincel()
                return
            if k == Qt.Key_E:
                self.establecer_pincel(goma=not self._goma)
                self.pincelCambiado.emit()
                return
            if k in (Qt.Key_BracketLeft, Qt.Key_BracketRight, Qt.Key_Minus, Qt.Key_Plus):
                paso = 5 if k in (Qt.Key_BracketRight, Qt.Key_Plus) else -5
                self.establecer_pincel(tam=self._pincel_tam + paso)
                self.pincelCambiado.emit()
                return
            if k == Qt.Key_Backspace:
                self.deshacer_trazo()
                return
        if self._es_lazo() and self._forma == "poligono":
            if evento.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._terminar_lazo()
                return
            if evento.key() == Qt.Key_Backspace and self._puntos:
                self._puntos.pop()  # borra el último punto
                self.update()
                return
        super().keyPressEvent(evento)

    def mouseDoubleClickEvent(self, evento) -> None:
        if (self._controlador is not None and evento.button() == Qt.LeftButton and not self._mano_temporal
                and hasattr(self._controlador, "doble_clic")):
            # Modo Photoshop: el doble clic sobre un texto lo edita (lo decide el controlador).
            q = (self._local(evento.position()) - self._origen) / self._zoom
            if self._controlador.doble_clic(q):
                self._arrastre = None
                self.update()
                return
        if self._es_pincel():
            self.mousePressEvent(evento)  # el segundo clic también pinta
            return
        if self._es_lazo():
            if self._forma == "poligono":
                # El doble clic ya sumó un punto con el primer clic: se cierra ahí.
                self._terminar_lazo()
            return
        if self._herramienta and self._herramienta != "enderezar":
            return
        if not self.tiene_imagen() or self._cerca_division(evento.position().x()):
            return
        if self._ajustar or abs(self._zoom - self._zoom_ajuste()) < 1e-3:
            self.fijar_zoom(1.0, self._local(evento.position()))
        else:
            self.ajustar()

    @staticmethod
    def _ruta_valida(evento) -> Optional[str]:
        datos = evento.mimeData()
        if not datos.hasUrls():
            return None
        for url in datos.urls():
            ruta = url.toLocalFile()
            if ruta and Path(ruta).suffix.lower() in EXTENSIONES_ARRASTRE:
                return ruta
        return None

    def dragEnterEvent(self, evento) -> None:
        if self._ruta_valida(evento):
            evento.acceptProposedAction()
            self._arrastrando_archivo = True
            self.update()
        else:
            evento.ignore()

    def dragMoveEvent(self, evento) -> None:
        if self._ruta_valida(evento):
            evento.acceptProposedAction()

    def dragLeaveEvent(self, _evento) -> None:
        self._arrastrando_archivo = False
        self.update()

    def dropEvent(self, evento) -> None:
        self._arrastrando_archivo = False
        self.update()
        rutas = [u.toLocalFile() for u in evento.mimeData().urls()
                 if u.toLocalFile() and Path(u.toLocalFile()).suffix.lower() in EXTENSIONES_ARRASTRE]
        if not rutas:
            return
        evento.acceptProposedAction()
        imagenes = [r for r in rutas if Path(r).suffix.lower() in EXTENSIONES_SOPORTADAS]
        if evento.modifiers() & Qt.ControlModifier and imagenes and self.tiene_imagen() and edicion.es_lite():
            # (Solo en la Lite, que tiene capas: en la PRO, con o sin Ctrl, a la tira como siempre.)
            # Con Ctrl, las imágenes entran como capas de la foto abierta (lo demás se abre como siempre).
            self.imagenesComoCapa.emit(imagenes)
            resto = [r for r in rutas if r not in imagenes]
            if resto:
                self.archivosSoltados.emit(resto)
            return
        self.archivosSoltados.emit(rutas)
