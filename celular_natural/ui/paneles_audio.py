"""Paneles del modo Audio: las tarjetas de las columnas de los costados.

Como ``PanelSonido``, no guardan estado que importe: muestran el proyecto
(``establecer``) y, cuando se toca algo, avisan lo que se pidió con una señal. El
editor (``modo_audio.EditorAudio``) decide (historial, vista previa) y vuelve a
mostrar el proyecto.

Columna izquierda, "Que suene real":
* ``GaleriaEscenas``: las escenas en tarjetas de dos columnas (ícono, lugar y cómo
  se grabó), más las propias (con una × para borrarlas).
* ``SelectorDestino``: "¿Cómo se grabó?" (WhatsApp, Video de celular, Auriculares o
  manos libres, Sin cambios).
* ``ControlCuanto``: Sutil, Normal o Fuerte, con un deslizador de 0 a 100.

Columna derecha, "Ambiente":
* ``FilaCapaFondo`` y ``FilaSonido``: una capa del fondo y un sonido suelto, con sus
  controles.
* ``FilaMiSonido``: un archivo de "Mis sonidos" (escuchar, renombrar y borrar).
* ``PanelSonidoAudio``: la tarjeta Sonido del video (volumen, normalizar y fundidos)
  con los textos del modo Audio.

Las tarjetas chicas (``TarjetaOpcion``) son las de la galería de estilos del modo
fácil, más bajas: ícono a la izquierda, nombre y una línea tenue debajo.
"""

from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from . import estilo, iconos
from .controles import ControlDeslizante
from .panel_sonido import PanelSonido

# Las escenas de la app: ícono, lugar (título de la tarjeta) y cómo se grabó (la línea de abajo).
ESCENAS_TARJETA = {
    "nota_oficina": ("briefcase", "En la oficina", "Nota de voz"),
    "nota_calle": ("car", "Por la calle", "Nota de voz"),
    "nota_colectivo": ("bus", "En el colectivo", "Nota de voz"),
    "nota_lluvia": ("cloud-rain", "Bajo la lluvia", "Nota de voz"),
    "video_playa": ("waves", "En la playa", "Video de celular"),
    "video_ciudad": ("building-2", "En la ciudad", "Video de celular"),
    "video_casa": ("house", "En casa", "Video de celular"),
    "manos_libres_auto": ("car-front", "En el auto", "Manos libres"),
    "auriculares_calle": ("headphones", "En la calle", "Auriculares"),
    "solo_anti_ia": ("scan-face", "Bajarle lo de IA", "Sin lugar ni fondo"),
}
# ¿Cómo se grabó?: (destino, nombre, línea de abajo, ícono, ayuda).
DESTINOS_TARJETA = (
    ("whatsapp", "WhatsApp", "Nota de voz", "message-circle",
     "Nota de voz de WhatsApp: el celular pegado a la boca (más graves), banda de 80 Hz a 7,5 kHz y Opus."),
    ("video", "Video", "De celular", "video",
     "Video de celular: a un brazo de distancia, menos graves y más lugar, banda de 100 Hz a 12 kHz y AAC."),
    ("auriculares", "Auriculares", "O manos libres", "headphones",
     "Auriculares o manos libres: banda angosta (200 Hz a 7 kHz) y la reducción de ruido del Bluetooth que "
     "«bombea» en las pausas."),
    ("ninguno", "Sin cambios", "Tal cual", "ban",
     "Sin micrófono ni compresión: la voz queda como está (con el lugar y el fondo, si elegiste)."),
)
NIVELES_CUANTO = (("Sutil", 30), ("Normal", 60), ("Fuerte", 90))


def _fuente(widget: QWidget, puntos: float, peso=QFont.Normal) -> QFont:
    f = QFont(widget.font())
    f.setPointSizeF(puntos)
    f.setWeight(peso)
    return f


# ======================================================================== tarjetas
class TarjetaOpcion(QWidget):
    """Una tarjeta de galería: ícono, nombre y una línea tenue debajo. Elegida: borde magenta.

    ``accion``: "borrar" (una × arriba a la derecha al pasar el mouse) o "escuchar" (un ▶),
    que emite ``accionPedida`` en vez de ``elegida``. Apagada (``setEnabled(False)``) se ve
    tenue y no responde."""

    elegida = Signal(str)
    accionPedida = Signal(str)
    ALTO = 50

    def __init__(self, clave: str, nombre: str, detalle: str, icono: str, ayuda: str = "",
                 accion: Optional[str] = None, color: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.clave, self.nombre, self.detalle, self.icono = clave, nombre, detalle, icono
        self.accion = accion
        self._color = color or estilo.MAGENTA
        self._seleccionada = False
        self._encima = False
        self._sobre_accion = False
        self._apretada = False
        self.setFixedHeight(self.ALTO)
        self.setMinimumWidth(100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setMouseTracking(True)
        self.setToolTip(ayuda or nombre)
        self.setAccessibleName(nombre)

    def sizeHint(self) -> QSize:
        return QSize(150, self.ALTO)

    @property
    def seleccionada(self) -> bool:
        return self._seleccionada

    def establecer_seleccionada(self, valor: bool) -> None:
        if valor != self._seleccionada:
            self._seleccionada = valor
            self.update()

    def _rect_accion(self) -> QRectF:
        return QRectF(self.width() - 26, 5, 20, 20)

    def changeEvent(self, evento) -> None:
        super().changeEvent(evento)
        self.update()

    def enterEvent(self, evento) -> None:
        self._encima = True
        self.update()
        super().enterEvent(evento)

    def leaveEvent(self, evento) -> None:
        self._encima = self._sobre_accion = self._apretada = False
        self.update()
        super().leaveEvent(evento)

    def mouseMoveEvent(self, evento) -> None:
        sobre = self.accion is not None and self._rect_accion().contains(evento.position())
        if sobre != self._sobre_accion:
            self._sobre_accion = sobre
            self.update()
        super().mouseMoveEvent(evento)

    def mousePressEvent(self, evento) -> None:
        if evento.button() == Qt.LeftButton:
            self._apretada = True
            self.update()
        super().mousePressEvent(evento)

    def mouseReleaseEvent(self, evento) -> None:
        if evento.button() == Qt.LeftButton and self._apretada:
            self._apretada = False
            self.update()
            pos = evento.position()
            if self.rect().contains(pos.toPoint()) and self.isEnabled():
                if self.accion is not None and self._rect_accion().contains(pos):
                    self.accionPedida.emit(self.clave)
                else:
                    self.elegida.emit(self.clave)
        super().mouseReleaseEvent(evento)

    def keyPressEvent(self, evento) -> None:
        if evento.key() in (Qt.Key_Return, Qt.Key_Enter) and self.isEnabled():
            self.elegida.emit(self.clave)
            return
        super().keyPressEvent(evento)

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        activa = self.isEnabled()
        sel, encima = self._seleccionada, self._encima and activa
        if sel:
            fondo, borde, grosor = QColor(estilo.SELECCION), QColor(estilo.MAGENTA), 2.0
        elif encima:
            fondo, borde, grosor = QColor("#3b3d44"), QColor("#575a64"), 1.0
        else:
            fondo, borde, grosor = QColor(estilo.TARJETA_2), QColor(estilo.BORDE), 1.0
        if self.hasFocus() and not sel:
            borde = QColor(estilo.ROSA)
        if self._apretada:
            fondo = fondo.darker(115)
        if not activa:
            p.setOpacity(0.45)
        p.setPen(QPen(borde, grosor))
        p.setBrush(fondo)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(grosor / 2, grosor / 2, -grosor / 2, -grosor / 2), 11, 11)
        # Insignia con el ícono, del color de la tarjeta (como en las secciones).
        color = QColor(self._color)
        insignia = QRectF(8, (self.height() - 30) / 2, 30, 30)
        tinte = QColor(color)
        tinte.setAlpha(60 if sel else 38)
        p.setPen(Qt.NoPen)
        p.setBrush(tinte)
        p.drawRoundedRect(insignia, 9, 9)
        p.drawPixmap(QRectF(insignia.center().x() - 9, insignia.center().y() - 9, 18, 18),
                     iconos.pixmap(self.icono, 18, self._color), QRectF(0, 0, 36, 36))
        # Textos: el nombre y, debajo, la línea tenue.
        x = insignia.right() + 8
        derecha = self.width() - (28 if self.accion is not None and encima else 8)
        ancho = max(10, int(derecha - x))
        f1 = _fuente(self, 9.0, QFont.DemiBold if sel else QFont.Medium)
        f2 = _fuente(self, 8.0)
        m1, m2 = QFontMetrics(f1), QFontMetrics(f2)
        alto = m1.height() + (m2.height() if self.detalle else 0)
        y = (self.height() - alto) / 2
        p.setFont(f1)
        p.setPen(QColor(estilo.TEXTO if (sel or encima) else estilo.TEXTO_2))
        p.drawText(QRectF(x, y, ancho, m1.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   m1.elidedText(self.nombre, Qt.ElideRight, ancho))
        if self.detalle:
            p.setFont(f2)
            p.setPen(QColor(estilo.TEXTO_TENUE))
            p.drawText(QRectF(x, y + m1.height(), ancho, m2.height()), Qt.AlignLeft | Qt.AlignVCenter,
                       m2.elidedText(self.detalle, Qt.ElideRight, ancho))
        # La acción de la esquina (× o ▶), solo al pasar el mouse.
        if self.accion is not None and encima:
            r = self._rect_accion()
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#4f2e40") if self._sobre_accion else QColor(255, 255, 255, 18))
            p.drawEllipse(r)
            nombre = "x" if self.accion == "borrar" else "play"
            color_accion = estilo.PUNTO if (self._sobre_accion and self.accion == "borrar") else estilo.TEXTO
            p.drawPixmap(QRectF(r.center().x() - 6, r.center().y() - 6, 12, 12),
                         iconos.pixmap(nombre, 12, color_accion), QRectF(0, 0, 24, 24))
        if sel:  # un tilde chiquito en la insignia
            c = QRectF(insignia.right() - 9, insignia.top() - 3, 13, 13)
            grad = QLinearGradient(c.topLeft(), c.bottomRight())
            grad.setColorAt(0, QColor(estilo.MAGENTA))
            grad.setColorAt(1, QColor(estilo.VIOLETA))
            p.setPen(QPen(QColor("#ffffff"), 1))
            p.setBrush(grad)
            p.drawEllipse(c)
            p.drawPixmap(QRectF(c.center().x() - 4, c.center().y() - 4, 8, 8), iconos.pixmap("check", 8, "#ffffff"),
                         QRectF(0, 0, 16, 16))
        p.end()


def grilla(tarjetas: Sequence[QWidget], columnas: int = 2) -> QWidget:
    """Las tarjetas en una grilla pareja (con un hueco si la última fila queda incompleta)."""
    caja = QWidget()
    g = QGridLayout(caja)
    g.setContentsMargins(0, 0, 0, 0)
    g.setSpacing(6)
    for i, t in enumerate(tarjetas):
        g.addWidget(t, i // columnas, i % columnas)
    if len(tarjetas) % columnas:
        hueco = QWidget()
        hueco.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        g.addWidget(hueco, len(tarjetas) // columnas, columnas - 1)
    for c in range(columnas):
        g.setColumnStretch(c, 1)
    return caja


def titulo_galeria(texto: str) -> QLabel:
    etiqueta = QLabel(texto.upper())
    etiqueta.setObjectName("tituloGaleria")
    return etiqueta


# ======================================================================== columna izquierda
class GaleriaEscenas(QWidget):
    """Las escenas de la app y las propias, en tarjetas de dos columnas.

    ``elegida(clave)``: la clave de una escena de la app, o el nombre de una propia.
    ``borrarPedido(nombre)``: la × de una escena propia."""

    elegida = Signal(str)
    borrarPedido = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tarjetas: dict[str, TarjetaOpcion] = {}
        self._seleccion: Optional[str] = None
        self._propias: tuple = ()
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(6)
        self._capa = capa
        self._caja_app: Optional[QWidget] = None
        self._titulo_propias = titulo_galeria("Tus escenas")
        self._caja_propias: Optional[QWidget] = None

    def establecer(self, escenas: Sequence, propias: Sequence) -> None:
        """``escenas`` y ``propias``: listas de ``proyecto_audio.Escena``."""
        if self._caja_app is None:
            tarjetas = []
            for e in escenas:
                icono, lugar, como = ESCENAS_TARJETA.get(e.clave, ("sparkles", e.nombre, ""))
                t = TarjetaOpcion(e.clave, lugar, como, icono, f"<b>{e.nombre}</b><br>{e.descripcion}")
                t.elegida.connect(self.elegida)
                self.tarjetas[e.clave] = t
                tarjetas.append(t)
            self._caja_app = grilla(tarjetas)
            self._capa.addWidget(self._caja_app)
            self._capa.addWidget(self._titulo_propias)
        clave_propias = tuple((e.nombre, e.descripcion) for e in propias)
        if clave_propias != self._propias:
            self._propias = clave_propias
            if self._caja_propias is not None:
                for e_nombre in [k for k in self.tarjetas if k.startswith("propia:")]:
                    self.tarjetas.pop(e_nombre)
                self._capa.removeWidget(self._caja_propias)
                self._caja_propias.hide()  # que no quede a la vista hasta que se borre
                self._caja_propias.deleteLater()
                self._caja_propias = None
            tarjetas = []
            for e in propias:
                t = TarjetaOpcion(e.nombre, e.nombre, "Tuya", "bookmark-plus",
                                  f"<b>{e.nombre}</b> (tuya)<br>{e.descripcion}<br>La × la borra.", accion="borrar")
                t.elegida.connect(self.elegida)
                t.accionPedida.connect(self.borrarPedido)
                self.tarjetas["propia:" + e.nombre] = t
                tarjetas.append(t)
            if tarjetas:
                self._caja_propias = grilla(tarjetas)
                self._capa.addWidget(self._caja_propias)
            self._titulo_propias.setVisible(bool(tarjetas))
        self.seleccionar(self._seleccion)

    def tarjeta(self, clave: str, propia: bool = False) -> Optional[TarjetaOpcion]:
        return self.tarjetas.get(("propia:" + clave) if propia else clave)

    def seleccionar(self, clave: Optional[str], propia: bool = False) -> None:
        self._seleccion = ("propia:" + clave) if (clave and propia) else clave
        for k, t in self.tarjetas.items():
            t.establecer_seleccionada(k == self._seleccion)


class SelectorDestino(QWidget):
    """¿Cómo se grabó?: cuatro tarjetas, una elegida."""

    elegido = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tarjetas: dict[str, TarjetaOpcion] = {}
        tarjetas = []
        for destino, nombre, detalle, icono, ayuda in DESTINOS_TARJETA:
            t = TarjetaOpcion(destino, nombre, detalle, icono, ayuda, color="#a78bfa")
            t.elegida.connect(self.elegido)
            self.tarjetas[destino] = t
            tarjetas.append(t)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.addWidget(grilla(tarjetas))

    def establecer(self, destino: str) -> None:
        for d, t in self.tarjetas.items():
            t.establecer_seleccionada(d == destino)


class ControlCuanto(QWidget):
    """Cuánto: Sutil (30), Normal (60) o Fuerte (90), o cualquier valor con el deslizador."""

    valorCambiado = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(4)
        segmento = QFrame()
        segmento.setObjectName("segmento")
        fila = QHBoxLayout(segmento)
        fila.setContentsMargins(3, 3, 3, 3)
        fila.setSpacing(2)
        self.botones: dict[int, QPushButton] = {}
        for nombre, valor in NIVELES_CUANTO:
            b = QPushButton(nombre)
            b.setObjectName("botonSegmento")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setToolTip(f"{nombre}: {valor} de 100")
            b.clicked.connect(lambda _c=False, v=valor: self._elegir(v))
            self.botones[valor] = b
            fila.addWidget(b, 1)
        capa.addWidget(segmento)
        self.control = ControlDeslizante(
            "cuanto", "Cuánto se nota", 0, 100,
            "Cuánto se nota la grabación: el lugar, el micrófono, el control de volumen del celular, el ruido y la "
            "compresión, todo junto. 0 deja la voz igual y 100 es lo máximo creíble.")
        self.control.valorCambiado.connect(lambda _c, v: self._al_mover(v))
        capa.addWidget(self.control)

    def _elegir(self, valor: int) -> None:
        self.control.slider.setValue(valor)   # avisa por _al_mover
        self._marcar(self.control.valor())

    def _al_mover(self, valor: int) -> None:
        self._marcar(valor)
        self.valorCambiado.emit(valor)

    def _marcar(self, valor: int) -> None:
        for v, b in self.botones.items():
            b.setChecked(v == valor)

    def establecer(self, valor: int) -> None:
        self.control.establecer(int(valor), 60)
        self._marcar(int(valor))

    def valor(self) -> int:
        return self.control.valor()


# ======================================================================== columna derecha
def _boton_icono(icono: str, ayuda: str, tam: int = 15) -> QPushButton:
    b = QPushButton()
    b.setObjectName("botonIconoAudio")
    b.setIcon(iconos.icono(icono, tam))
    b.setIconSize(QSize(tam, tam))
    b.setFixedSize(26, 26)
    b.setCursor(Qt.PointingHandCursor)
    b.setToolTip(ayuda)
    return b


def _etiqueta_falta() -> QLabel:
    e = QLabel("falta")
    e.setObjectName("insigniaFalta")
    e.setToolTip("No está el archivo en Mis sonidos (se borró o se renombró por fuera): no suena. Quitalo o volvé "
                 "a agregarlo a Mis sonidos con el mismo nombre.")
    e.hide()
    return e


class FilaCapaFondo(QFrame):
    """Una capa del fondo continuo: nombre, escuchar 3 s, quitar, volumen e intensidad."""

    cambiada = Signal(int, str, int)   # índice, control ("volumen" o "intensidad"), valor 0-100
    quitarPedido = Signal(int)
    escucharPedido = Signal(int)

    def __init__(self, indice: int, parent=None):
        super().__init__(parent)
        self.setObjectName("filaCapa")
        self.indice = indice
        capa = QVBoxLayout(self)
        capa.setContentsMargins(10, 6, 6, 8)
        capa.setSpacing(2)
        fila = QHBoxLayout()
        fila.setSpacing(6)
        self.icono = QLabel()
        self.icono.setFixedSize(18, 18)
        self.nombre = QLabel("")
        self.nombre.setObjectName("etiquetaCapa")
        self.nombre.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.falta = _etiqueta_falta()
        self.boton_escuchar = _boton_icono("play", "Escuchar 3 segundos de este fondo, solo (con su volumen)")
        self.boton_escuchar.clicked.connect(lambda: self.escucharPedido.emit(self.indice))
        self.boton_quitar = _boton_icono("x", "Quitar esta capa del fondo")
        self.boton_quitar.clicked.connect(lambda: self.quitarPedido.emit(self.indice))
        fila.addWidget(self.icono)
        fila.addWidget(self.nombre, 1)
        fila.addWidget(self.falta)
        fila.addWidget(self.boton_escuchar)
        fila.addWidget(self.boton_quitar)
        capa.addLayout(fila)
        self.volumen = ControlDeslizante(
            "volumen", "Volumen", 0, 100,
            "50 es el nivel de un fondo real a la distancia de siempre. Más alto, más adelante; 0 lo calla.")
        self.volumen.valorCambiado.connect(lambda _c, v: self.cambiada.emit(self.indice, "volumen", v))
        capa.addWidget(self.volumen)
        self.intensidad = ControlDeslizante(
            "intensidad", "Intensidad", 0, 100,
            "Más o menos de lo mismo: más lluvia, más tránsito, más viento…")
        self.intensidad.valorCambiado.connect(lambda _c, v: self.cambiada.emit(self.indice, "intensidad", v))
        capa.addWidget(self.intensidad)

    def establecer(self, icono: str, nombre: str, volumen: int, intensidad: Optional[int], falta: bool,
                   ayuda: str = "") -> None:
        self.icono.setPixmap(iconos.pixmap(icono, 16, "#c4b5fd"))
        self.nombre.setText(nombre)
        self.nombre.setToolTip(ayuda or nombre)
        self.falta.setVisible(falta)
        self.boton_escuchar.setEnabled(not falta)
        self.volumen.establecer(volumen, 50)
        self.intensidad.setVisible(intensidad is not None)
        if intensidad is not None:
            self.intensidad.establecer(intensidad, 50)


class FilaSonido(QFrame):
    """Un sonido suelto: nombre, dónde empieza (tocarlo lleva el cursor ahí), borrar y volumen."""

    cambiada = Signal(int, str, int)   # índice, "volumen", valor 0-100
    borrarPedido = Signal(int)
    irPedido = Signal(int)

    def __init__(self, indice: int, parent=None):
        super().__init__(parent)
        self.setObjectName("filaCapa")
        self.indice = indice
        capa = QVBoxLayout(self)
        capa.setContentsMargins(10, 6, 6, 8)
        capa.setSpacing(2)
        fila = QHBoxLayout()
        fila.setSpacing(6)
        self.icono = QLabel()
        self.icono.setFixedSize(18, 18)
        self.nombre = QLabel("")
        self.nombre.setObjectName("etiquetaCapa")
        self.nombre.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.falta = _etiqueta_falta()
        self.boton_ir = QPushButton("0:00,00")
        self.boton_ir.setObjectName("botonEnlace")
        self.boton_ir.setCursor(Qt.PointingHandCursor)
        self.boton_ir.setToolTip("Dónde empieza (en lo que se escucha). Tocá para llevar el cursor ahí.")
        self.boton_ir.clicked.connect(lambda: self.irPedido.emit(self.indice))
        self.boton_borrar = _boton_icono("trash-2", "Borrar este sonido")
        self.boton_borrar.clicked.connect(lambda: self.borrarPedido.emit(self.indice))
        fila.addWidget(self.icono)
        fila.addWidget(self.nombre, 1)
        fila.addWidget(self.falta)
        fila.addWidget(self.boton_ir)
        fila.addWidget(self.boton_borrar)
        capa.addLayout(fila)
        self.volumen = ControlDeslizante(
            "volumen", "Volumen", 0, 100,
            "50 deja el sonido con su pico en -6 dB (bien presente). Más alto, más cerca; 0 lo calla.")
        self.volumen.valorCambiado.connect(lambda _c, v: self.cambiada.emit(self.indice, "volumen", v))
        capa.addWidget(self.volumen)

    def establecer(self, icono: str, nombre: str, comienzo: str, volumen: int, falta: bool) -> None:
        self.icono.setPixmap(iconos.pixmap(icono, 16, "#7dd3fc"))
        self.nombre.setText(nombre)
        self.nombre.setToolTip(nombre)
        self.boton_ir.setText(comienzo)
        self.falta.setVisible(falta)
        self.volumen.establecer(volumen, 70)


class FilaMiSonido(QFrame):
    """Un archivo de "Mis sonidos": nombre, duración, escuchar, renombrar y borrar."""

    escucharPedido = Signal(str)
    renombrarPedido = Signal(str)
    borrarPedido = Signal(str)

    def __init__(self, nombre: str, detalle: str, parent=None):
        super().__init__(parent)
        self.setObjectName("filaMiSonido")
        self.archivo = nombre
        fila = QHBoxLayout(self)
        fila.setContentsMargins(8, 3, 2, 3)
        fila.setSpacing(4)
        icono = QLabel()
        icono.setPixmap(iconos.pixmap("music", 14, estilo.TEXTO_TENUE))
        icono.setFixedSize(16, 16)
        textos = QVBoxLayout()
        textos.setSpacing(0)
        self.etiqueta = QLabel(nombre)
        self.etiqueta.setObjectName("etiquetaControl")
        self.etiqueta.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.etiqueta.setToolTip(nombre)
        self.detalle = QLabel(detalle)
        self.detalle.setObjectName("nota")
        self.detalle.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        textos.addWidget(self.etiqueta)
        textos.addWidget(self.detalle)
        b_escuchar = _boton_icono("play", "Escuchar los primeros 3 segundos")
        b_escuchar.clicked.connect(lambda: self.escucharPedido.emit(self.archivo))
        b_renombrar = _boton_icono("pencil", "Cambiarle el nombre")
        b_renombrar.clicked.connect(lambda: self.renombrarPedido.emit(self.archivo))
        b_borrar = _boton_icono("trash-2", "Borrarlo de Mis sonidos (el archivo original no se toca)")
        b_borrar.clicked.connect(lambda: self.borrarPedido.emit(self.archivo))
        fila.addWidget(icono, 0, Qt.AlignVCenter)
        fila.addLayout(textos, 1)
        for b in (b_escuchar, b_renombrar, b_borrar):
            fila.addWidget(b, 0, Qt.AlignVCenter)


class PanelSonidoAudio(PanelSonido):
    """La tarjeta Sonido del modo Video, para el resultado del modo Audio: volumen general,
    normalizar y fundidos. Sin "Quitar el sonido" ni "Guardar solo el audio" (para eso está
    Exportar) y con los textos del modo Audio."""

    def __init__(self, parent=None, abierta: bool = False):
        super().__init__(parent, abierta)
        self.mostrar_quitar(False)
        self.boton_guardar.hide()
        self.titulo.setText("Volumen general")
        for etiqueta in self.cabecera.findChildren(QLabel, "subtituloCaja"):
            etiqueta.setText("Volumen, normalizar y fundidos")
        self.cabecera.setToolTip("El volumen de todo lo que se exporta (voz y ambiente juntos), normalizar y los "
                                 "fundidos del principio y del final. Los silencios se marcan en la línea de tiempo "
                                 "(Silenciar tramo).")
        self.volumen.setToolTip("100 % deja todo como está. Más de 100 % lo sube (lo que se pasaría se suaviza). "
                                "Con Normalizar, el volumen solo puede bajar.")

    def _actualizar(self) -> None:
        super()._actualizar()
        if not self._hay_archivo:
            self.nota_sin_audio.setText("Abrí un audio para ajustar el volumen.")
        # Los botones de la tarjeta que son del video (guardar solo el audio, ir y volver con el modo
        # Audio…) no van acá: solo queda "Devolver todo" (y Cancelar, que es de guardar).
        for boton in self.cuerpo.findChildren(QPushButton):
            if boton is not self.boton_devolver_todo and boton is not getattr(self, "boton_cancelar", None):
                boton.hide()
        origen = getattr(self, "caja_origen", None)  # "Sonido: el del video" (de qué sonido se trata, en Video)
        if isinstance(origen, QWidget):
            origen.hide()


__all__ = ["TarjetaOpcion", "GaleriaEscenas", "SelectorDestino", "ControlCuanto", "FilaCapaFondo", "FilaSonido",
           "FilaMiSonido", "PanelSonidoAudio", "grilla", "titulo_galeria", "ESCENAS_TARJETA", "DESTINOS_TARJETA"]
