"""Selector de color propio del modo Photoshop (NaturalShot Lite), como el de Photopea.

* Un **cuadro de saturación y brillo** (a la izquierda) y una **barra de tono** (vertical, al lado).
* Una **barra de alfa** (opacidad) abajo, sobre un tablero (si el color lleva alfa).
* El **hexadecimal** (``#rrggbb`` o ``#rrggbbaa``) y los números **R, G, B** (y **A**, en %).
* El color **nuevo** y el de **antes** lado a lado (un clic en el de antes lo vuelve a poner).
* Las **muestras recientes** (se recuerdan en QSettings, ``photoshop/colores_recientes``).
* Un **cuentagotas**: con el botón apretado, el próximo clic en la pantalla toma el color (sobre la
  vista del documento, el de la composición que se ve; en otro lado, el de la pantalla). Esc lo cancela.

Uso: ``elegir_color(parent, (r, g, b, a), "Color de frente")`` devuelve el RGBA elegido o None.
``BotonColor`` es un botón que muestra un color y lo cambia con este selector.

El cuentagotas no usa filtros de eventos globales: mientras está activo, el diálogo toma el mouse
(``grabMouse``) y recibe el clic él mismo.
"""

from __future__ import annotations

import colorsys
from typing import Callable, Optional

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from . import estilo, iconos

CLAVE_RECIENTES = "photoshop/colores_recientes"
MAX_RECIENTES = 14
Color = tuple  # (r, g, b, a) 0..255


# ---------------------------------------------------------------------------
# Muestras recientes (QSettings)
# ---------------------------------------------------------------------------

def _config():
    from .modo_facil import configuracion
    return configuracion()


def a_hex(color, con_alfa: bool = False) -> str:
    r, g, b = (int(v) for v in color[:3])
    a = int(color[3]) if len(color) > 3 else 255
    return f"#{r:02x}{g:02x}{b:02x}" + (f"{a:02x}" if con_alfa and a < 255 else "")


def desde_hex(texto: str) -> Optional[Color]:
    """``#rgb``, ``#rrggbb`` o ``#rrggbbaa`` (con o sin #) → RGBA; None si no es un color."""
    t = str(texto).strip().lstrip("#")
    if len(t) == 3:
        t = "".join(c * 2 for c in t)
    if len(t) not in (6, 8):
        return None
    try:
        valores = [int(t[i:i + 2], 16) for i in range(0, len(t), 2)]
    except ValueError:
        return None
    if len(valores) == 3:
        valores.append(255)
    return tuple(valores)


def recientes() -> list[Color]:
    """Las muestras recientes (la última primero)."""
    try:
        valor = _config().value(CLAVE_RECIENTES, "")
    except Exception:  # noqa: BLE001 - una configuración rota no rompe el selector
        return []
    if isinstance(valor, (list, tuple)):
        valor = ",".join(str(v) for v in valor)
    salida = []
    for parte in str(valor or "").split(","):
        c = desde_hex(parte)
        if c is not None and c not in salida:
            salida.append(c)
    return salida[:MAX_RECIENTES]


def recordar(color) -> None:
    """Suma el color a las muestras recientes (adelante, sin repetir)."""
    c = tuple(int(v) for v in color[:4]) if len(color) >= 4 else tuple(int(v) for v in color[:3]) + (255,)
    lista = [c] + [x for x in recientes() if x != c]
    try:
        cfg = _config()
        cfg.setValue(CLAVE_RECIENTES, ",".join(a_hex(x, True) for x in lista[:MAX_RECIENTES]))
        cfg.sync()
    except Exception:  # noqa: BLE001
        pass


def _tablero(p: QPainter, rect: QRectF, paso: int = 6) -> None:
    p.save()
    p.setClipRect(rect)
    p.fillRect(rect, QColor(200, 200, 200))
    y = int(rect.top())
    fila = 0
    while y < rect.bottom():
        x = int(rect.left()) + (paso if fila % 2 else 0)
        while x < rect.right():
            p.fillRect(QRectF(x, y, paso, paso), QColor(150, 150, 150))
            x += 2 * paso
        y += paso
        fila += 1
    p.restore()


# ---------------------------------------------------------------------------
# Las piezas
# ---------------------------------------------------------------------------

class CuadroSV(QWidget):
    """Saturación (izquierda → derecha) y brillo (arriba → abajo) para un tono."""

    cambiado = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tono, self.sat, self.val = 0.0, 1.0, 1.0
        self.setFixedSize(224, 224)
        self.setCursor(Qt.CrossCursor)
        self._fondo: Optional[QPixmap] = None
        self._tono_fondo = None

    def establecer(self, tono: float, sat: float, val: float) -> None:
        self.tono, self.sat, self.val = tono, sat, val
        self.update()

    def _pintar_fondo(self) -> QPixmap:
        if self._fondo is None or self._tono_fondo != self.tono or self._fondo.size() != self.size():
            pm = QPixmap(self.size())
            p = QPainter(pm)
            r = QRectF(0, 0, self.width(), self.height())
            h = QLinearGradient(0, 0, self.width(), 0)
            h.setColorAt(0, QColor(255, 255, 255))
            h.setColorAt(1, QColor.fromHsvF(self.tono, 1.0, 1.0))
            p.fillRect(r, h)
            v = QLinearGradient(0, 0, 0, self.height())
            v.setColorAt(0, QColor(0, 0, 0, 0))
            v.setColorAt(1, QColor(0, 0, 0, 255))
            p.fillRect(r, v)
            p.end()
            self._fondo, self._tono_fondo = pm, self.tono
        return self._fondo

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.drawPixmap(0, 0, self._pintar_fondo())
        p.setRenderHint(QPainter.Antialiasing, True)
        c = QPointF(self.sat * (self.width() - 1), (1.0 - self.val) * (self.height() - 1))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 180), 3))
        p.drawEllipse(c, 6, 6)
        p.setPen(QPen(QColor(255, 255, 255), 1.5))
        p.drawEllipse(c, 6, 6)
        p.end()

    def _desde(self, pos) -> None:
        self.sat = min(1.0, max(0.0, pos.x() / max(1, self.width() - 1)))
        self.val = min(1.0, max(0.0, 1.0 - pos.y() / max(1, self.height() - 1)))
        self.update()
        self.cambiado.emit()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._desde(e.position())

    def mouseMoveEvent(self, e) -> None:
        if e.buttons() & Qt.LeftButton:
            self._desde(e.position())


class BarraTono(QWidget):
    """El tono, de arriba (0°) hacia abajo (360°)."""

    cambiado = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tono = 0.0
        self.setFixedSize(22, 224)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        g = QLinearGradient(0, 0, 0, self.height())
        for i in range(7):
            g.setColorAt(i / 6.0, QColor.fromHsvF((i / 6.0) % 1.0, 1.0, 1.0))
        r = QRectF(4, 0, self.width() - 8, self.height())
        p.fillRect(r, g)
        y = self.tono * (self.height() - 1)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor(0, 0, 0, 200), 3))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(1, y - 3, self.width() - 2, 6), 2, 2)
        p.setPen(QPen(QColor(255, 255, 255), 1.5))
        p.drawRoundedRect(QRectF(1, y - 3, self.width() - 2, 6), 2, 2)
        p.end()

    def _desde(self, pos) -> None:
        self.tono = min(1.0, max(0.0, pos.y() / max(1, self.height() - 1)))
        self.update()
        self.cambiado.emit()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._desde(e.position())

    def mouseMoveEvent(self, e) -> None:
        if e.buttons() & Qt.LeftButton:
            self._desde(e.position())


class BarraAlfa(QWidget):
    """La opacidad del color, de transparente (izquierda) a opaco (derecha)."""

    cambiado = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.alfa = 1.0
        self.color = QColor(255, 0, 0)
        self.setFixedHeight(20)
        self.setMinimumWidth(120)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        r = QRectF(0, 4, self.width(), self.height() - 8)
        _tablero(p, r, 4)
        g = QLinearGradient(0, 0, self.width(), 0)
        c0 = QColor(self.color)
        c0.setAlpha(0)
        c1 = QColor(self.color)
        c1.setAlpha(255)
        g.setColorAt(0, c0)
        g.setColorAt(1, c1)
        p.fillRect(r, g)
        x = self.alfa * (self.width() - 1)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 200), 3))
        p.drawRoundedRect(QRectF(x - 3, 1, 6, self.height() - 2), 2, 2)
        p.setPen(QPen(QColor(255, 255, 255), 1.5))
        p.drawRoundedRect(QRectF(x - 3, 1, 6, self.height() - 2), 2, 2)
        p.end()

    def _desde(self, pos) -> None:
        self.alfa = min(1.0, max(0.0, pos.x() / max(1, self.width() - 1)))
        self.update()
        self.cambiado.emit()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._desde(e.position())

    def mouseMoveEvent(self, e) -> None:
        if e.buttons() & Qt.LeftButton:
            self._desde(e.position())


class _Muestra(QWidget):
    """Un cuadrito de color (con el tablero abajo si es transparente)."""

    clic = Signal()

    def __init__(self, color=(0, 0, 0, 255), lado: int = 18, parent=None):
        super().__init__(parent)
        self.color = tuple(color)
        self.setFixedSize(lado, lado)
        self.setCursor(Qt.PointingHandCursor)

    def establecer(self, color) -> None:
        self.color = tuple(color)
        self.setToolTip(a_hex(self.color, True))
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        r = QRectF(0, 0, self.width(), self.height())
        _tablero(p, r, 4)
        p.fillRect(r, QColor(*self.color[:3], self.color[3] if len(self.color) > 3 else 255))
        p.setPen(QPen(QColor("#6b6e78"), 1))
        p.drawRect(r.adjusted(0, 0, -1, -1))
        p.end()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.clic.emit()


# ---------------------------------------------------------------------------
# El diálogo
# ---------------------------------------------------------------------------

def _muestreador_de(widget) -> Optional[Callable[[QPoint], Optional[tuple]]]:
    """El cuentagotas de la ventana que contiene a ``widget`` (si es la de NaturalShot, toma el color
    de la composición que se ve), o None."""
    w = widget
    while w is not None:
        ps = getattr(w, "photoshop", None)
        if ps is not None and hasattr(ps, "color_en_pantalla"):
            return ps.color_en_pantalla
        w = w.parentWidget()
    return None


def color_de_pantalla(pos: QPoint) -> Optional[tuple]:
    """El color de la pantalla en esa posición global (puede no andar sin pantalla real)."""
    pantalla = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
    if pantalla is None:
        return None
    geo = pantalla.geometry()
    pm = pantalla.grabWindow(0, pos.x() - geo.x(), pos.y() - geo.y(), 1, 1)
    img = pm.toImage()
    if img.isNull() or img.width() < 1:
        return None
    c = img.pixelColor(0, 0)
    return c.red(), c.green(), c.blue()


class SelectorColor(QDialog):
    """El selector (ver el módulo). ``color()``: el RGBA elegido."""

    colorCambiado = Signal(tuple)

    def __init__(self, color=(0, 0, 0, 255), titulo: str = "Elegir color", alfa: bool = True, parent=None,
                 muestrear: Optional[Callable[[QPoint], Optional[tuple]]] = None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setObjectName("selectorColor")
        self._alfa = bool(alfa)
        self._muestrear = muestrear if muestrear is not None else _muestreador_de(parent)
        self._antes = self._normalizar(color)
        self._color = self._antes
        self._cargando = False
        self._tomando = False

        capa = QVBoxLayout(self)
        capa.setContentsMargins(16, 14, 16, 14)
        capa.setSpacing(10)
        arriba = QHBoxLayout()
        arriba.setSpacing(10)
        izquierda = QVBoxLayout()
        izquierda.setSpacing(8)
        fila_sv = QHBoxLayout()
        fila_sv.setSpacing(8)
        self.cuadro = CuadroSV()
        self.cuadro.setToolTip("Saturación (izquierda → derecha) y brillo (arriba → abajo)")
        self.barra_tono = BarraTono()
        self.barra_tono.setToolTip("Tono")
        fila_sv.addWidget(self.cuadro)
        fila_sv.addWidget(self.barra_tono)
        izquierda.addLayout(fila_sv)
        self.barra_alfa = BarraAlfa()
        self.barra_alfa.setToolTip("Opacidad (alfa)")
        self.barra_alfa.setVisible(self._alfa)
        izquierda.addWidget(self.barra_alfa)
        arriba.addLayout(izquierda)

        derecha = QVBoxLayout()
        derecha.setSpacing(8)
        fila_muestras = QHBoxLayout()
        fila_muestras.setSpacing(0)
        self.muestra_nueva = _Muestra(self._color, 44)
        self.muestra_nueva.setFixedSize(54, 40)
        self.muestra_nueva.setToolTip("El color nuevo")
        self.muestra_antes = _Muestra(self._antes, 44)
        self.muestra_antes.setFixedSize(54, 40)
        self.muestra_antes.setToolTip("El de antes (clic para volver a él)")
        self.muestra_antes.clic.connect(lambda: self.establecer_color(self._antes))
        fila_muestras.addWidget(self.muestra_nueva)
        fila_muestras.addWidget(self.muestra_antes)
        fila_muestras.addStretch(1)
        derecha.addLayout(fila_muestras)
        etiquetas = QHBoxLayout()
        for texto in ("Nuevo", "Antes"):
            e = QLabel(texto)
            e.setObjectName("detalleCapa")
            e.setFixedWidth(54)
            etiquetas.addWidget(e)
        etiquetas.addStretch(1)
        derecha.addLayout(etiquetas)

        grilla = QGridLayout()
        grilla.setHorizontalSpacing(6)
        grilla.setVerticalSpacing(5)
        e = QLabel("#")
        e.setObjectName("etiquetaControl")
        self.campo_hex = QLineEdit()
        self.campo_hex.setObjectName("campoHex")
        self.campo_hex.setMaxLength(9)
        self.campo_hex.setFixedWidth(96)
        self.campo_hex.setToolTip("Hexadecimal: rrggbb" + (" (o rrggbbaa, con el alfa)" if self._alfa else ""))
        self.campo_hex.editingFinished.connect(self._al_escribir_hex)
        grilla.addWidget(e, 0, 0)
        grilla.addWidget(self.campo_hex, 0, 1)
        self.numeros: dict[str, QSpinBox] = {}
        for fila, (clave, texto, maximo, sufijo) in enumerate((("r", "R", 255, ""), ("g", "G", 255, ""),
                                                               ("b", "B", 255, ""), ("a", "A", 100, " %")), 1):
            e = QLabel(texto)
            e.setObjectName("etiquetaControl")
            n = QSpinBox()
            n.setObjectName("valorControl")
            n.setRange(0, maximo)
            n.setSuffix(sufijo)
            n.setFixedWidth(96)
            n.setKeyboardTracking(False)
            n.valueChanged.connect(lambda _v: self._al_cambiar_numeros())
            self.numeros[clave] = n
            grilla.addWidget(e, fila, 0)
            grilla.addWidget(n, fila, 1)
            if clave == "a" and not self._alfa:
                e.hide()
                n.hide()
        derecha.addLayout(grilla)
        self.boton_cuentagotas = QPushButton(" Cuentagotas")
        self.boton_cuentagotas.setIcon(iconos.icono("pipette", 15))
        self.boton_cuentagotas.setCheckable(True)
        self.boton_cuentagotas.setToolTip("Tomar un color de la imagen (o de la pantalla): tocá acá y después hacé "
                                          "clic donde está el color. Esc cancela.")
        self.boton_cuentagotas.toggled.connect(self._alternar_cuentagotas)
        derecha.addWidget(self.boton_cuentagotas)
        derecha.addStretch(1)
        arriba.addLayout(derecha)
        capa.addLayout(arriba)

        e = QLabel("Recientes")
        e.setObjectName("etiquetaControl")
        capa.addWidget(e)
        self.fila_recientes = QHBoxLayout()
        self.fila_recientes.setSpacing(4)
        self.muestras_recientes: list[_Muestra] = []
        for c in recientes():
            m = _Muestra(c, 20)
            m.establecer(c)
            m.clic.connect(lambda c=c: self.establecer_color(c))
            self.muestras_recientes.append(m)
            self.fila_recientes.addWidget(m)
        if not self.muestras_recientes:
            vacia = QLabel("Todavía no hay: los colores que elijas quedan acá.")
            vacia.setObjectName("nota")
            self.fila_recientes.addWidget(vacia)
        self.fila_recientes.addStretch(1)
        capa.addLayout(self.fila_recientes)

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.button(QDialogButtonBox.Ok).setText("Aceptar")
        botones.button(QDialogButtonBox.Ok).setObjectName("botonPrimario")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        capa.addWidget(botones)

        self.cuadro.cambiado.connect(self._al_mover_hsv)
        self.barra_tono.cambiado.connect(self._al_mover_hsv)
        self.barra_alfa.cambiado.connect(self._al_mover_hsv)
        self._cargar(self._color, desde_hsv=False)

    # ------------------------------------------------------------ datos
    def _normalizar(self, color) -> Color:
        c = tuple(int(min(255, max(0, round(float(v))))) for v in color)
        if len(c) == 3:
            c = c + (255,)
        if not self._alfa:
            c = c[:3] + (255,)
        return c[:4]

    def color(self) -> Color:
        return self._color

    def establecer_color(self, color) -> None:
        self._cargar(self._normalizar(color), desde_hsv=False)

    def establecer_hex(self, texto: str) -> bool:
        c = desde_hex(texto)
        if c is None:
            self._cargar(self._color, desde_hsv=False)
            return False
        self.establecer_color(c)
        return True

    def _cargar(self, color: Color, desde_hsv: bool) -> None:
        """Pone el color en todas las piezas (sin que se avisen entre ellas)."""
        self._cargando = True
        try:
            self._color = color
            if not desde_hsv:
                h, s, v = colorsys.rgb_to_hsv(*(x / 255.0 for x in color[:3]))
                if s == 0 or v == 0:
                    h = self.barra_tono.tono  # el gris no tiene tono: queda el que estaba
                if v == 0:
                    s = self.cuadro.sat
                self.cuadro.establecer(h, s, v)
                self.barra_tono.tono = h
                self.barra_tono.update()
                self.barra_alfa.alfa = color[3] / 255.0
            self.barra_alfa.color = QColor(*color[:3])
            self.barra_alfa.update()
            self.campo_hex.setText(a_hex(color, self._alfa).lstrip("#"))
            for clave, valor in zip("rgb", color[:3]):
                self.numeros[clave].setValue(int(valor))
            self.numeros["a"].setValue(round(color[3] / 2.55))
            self.muestra_nueva.establecer(color)
        finally:
            self._cargando = False
        self.colorCambiado.emit(self._color)

    def _al_mover_hsv(self) -> None:
        if self._cargando:
            return
        self.cuadro.tono = self.barra_tono.tono
        self.cuadro.update()
        r, g, b = colorsys.hsv_to_rgb(self.barra_tono.tono % 1.0, self.cuadro.sat, self.cuadro.val)
        a = round(self.barra_alfa.alfa * 255) if self._alfa else 255
        self._cargar((round(r * 255), round(g * 255), round(b * 255), a), desde_hsv=True)

    def _al_cambiar_numeros(self) -> None:
        if self._cargando:
            return
        a = round(self.numeros["a"].value() * 2.55) if self._alfa else 255
        self.establecer_color((self.numeros["r"].value(), self.numeros["g"].value(), self.numeros["b"].value(), a))

    def _al_escribir_hex(self) -> None:
        if not self._cargando:
            self.establecer_hex(self.campo_hex.text())

    # ------------------------------------------------------------ cuentagotas
    def _alternar_cuentagotas(self, activo: bool) -> None:
        if activo == self._tomando:
            return
        self._tomando = activo
        if activo:
            self.grabMouse(QCursor(iconos.pixmap("pipette", 22, "#ffffff"), 2, 20))
            self.grabKeyboard()
        else:
            self.releaseMouse()
            self.releaseKeyboard()

    def tomar_de(self, pos_global: QPoint) -> Optional[Color]:
        """El cuentagotas: el color en esa posición de la pantalla (de la vista, si está ahí)."""
        color = None
        if self._muestrear is not None:
            try:
                color = self._muestrear(pos_global)
            except RuntimeError:  # la ventana ya no existe
                color = None
        if color is None:
            color = color_de_pantalla(pos_global)
        if color is not None:
            a = self._color[3]
            self.establecer_color(tuple(color[:3]) + (a,))
        return self._color if color is not None else None

    def mousePressEvent(self, e) -> None:
        if self._tomando:
            self.tomar_de(e.globalPosition().toPoint())
            self.boton_cuentagotas.setChecked(False)
            e.accept()
            return
        super().mousePressEvent(e)

    def keyPressEvent(self, e) -> None:
        if self._tomando:
            if e.key() == Qt.Key_Escape:
                self.boton_cuentagotas.setChecked(False)
            e.accept()
            return
        super().keyPressEvent(e)

    def done(self, resultado: int) -> None:
        if self._tomando:
            self.boton_cuentagotas.setChecked(False)
        if resultado == QDialog.Accepted:
            recordar(self._color)
        super().done(resultado)


def elegir_color(parent, inicial=(0, 0, 0, 255), titulo: str = "Elegir color", alfa: bool = True,
                 muestrear: Optional[Callable[[QPoint], Optional[tuple]]] = None) -> Optional[Color]:
    """Abre el selector y devuelve el RGBA elegido (con alfa 255 si ``alfa`` es False), o None."""
    dialogo = SelectorColor(inicial, titulo, alfa, parent, muestrear)
    try:
        if dialogo.exec() != QDialog.Accepted:
            return None
        return dialogo.color()
    finally:
        dialogo.deleteLater()


# ---------------------------------------------------------------------------
# Un botón de color
# ---------------------------------------------------------------------------

class BotonColor(QPushButton):
    """Un botón que muestra un color (RGBA) y lo cambia con el selector propio."""

    colorCambiado = Signal(tuple)

    def __init__(self, color=(255, 255, 255, 255), parent=None, alfa: bool = True, titulo: str = "Elegir color",
                 ancho: int = 46, alto: int = 24):
        super().__init__(parent)
        self._alfa = alfa
        self._titulo = titulo
        c = tuple(int(v) for v in color)
        self.color = c if len(c) == 4 else c + (255,)
        self.setFixedSize(ancho, alto)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.clicked.connect(self._elegir)
        self._pintar()

    def establecer(self, color) -> None:
        c = tuple(int(v) for v in color)
        self.color = c if len(c) == 4 else c + (255,)
        self._pintar()

    def _pintar(self) -> None:
        r, g, b, a = self.color
        self.setToolTip(f"#{r:02x}{g:02x}{b:02x}" + (f" · {round(a / 2.55)} %" if a < 255 else "")
                        + "\nClic para elegir otro color")
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.save()
        camino = QPainterPath()
        camino.addRoundedRect(r, 5, 5)
        p.setClipPath(camino)
        _tablero(p, r, 5)
        p.fillRect(r, QColor(*self.color))
        p.restore()
        p.setPen(QPen(QColor("#6b6e78") if self.isEnabled() else QColor(estilo.BORDE), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 5, 5)
        if not self.isEnabled():
            p.fillRect(r, QColor(40, 40, 46, 150))
        p.end()

    def sizeHint(self) -> QSize:
        return self.size()

    def _elegir(self) -> None:
        elegido = elegir_color(self, self.color, self._titulo, self._alfa)
        if elegido is not None and tuple(elegido) != self.color:
            self.establecer(elegido)
            self.colorCambiado.emit(self.color)


__all__ = ["BotonColor", "SelectorColor", "a_hex", "desde_hex", "elegir_color", "recientes", "recordar"]
