"""Modo fácil: la columna izquierda en cuatro pasos, para editar rápido.

1. **Tu foto:** abrir (o arrastrar) fotos.
2. **Elegí un estilo:** galería con la foto actual procesada con cada preset.
3. **¿Cuánto efecto?:** la intensidad general.
4. **Exportar:** PNG o JPEG.

No tiene estado propio: trabaja sobre el mismo ``PanelAjustes`` y la misma
exportación que el modo editor. Por eso cambiar de modo no pierde nada y cada
cambio queda en el mismo historial (Ctrl+Z y Ctrl+Y siguen andando).

Las miniaturas de la galería se calculan en segundo plano, a lado ``LADO_ESTILO``,
sobre la misma foto que entra al filtro (girada, con montaje, borrados y recorte),
y se guardan en caché por foto, preset y valores del preset.

**Capas:** Fácil no muestra el panel de capas (está en el modo Photoshop de la Lite). El estilo
elegido es la capa de ajuste "Celular natural" del documento de la foto, que va arriba de todo.
Si la foto tiene capas de imagen, la vista y "Exportar foto" las componen igual que el Editor
(su "Antes" es la composición sin el filtro), y la nota lo dice ("capas del modo Photoshop"). Lo que antes se llamaba "capas" (presets
apilados) ahora son los "efectos". Las miniaturas de la galería muestran la foto sin las
capas de imagen (solo el estilo).
"""

from __future__ import annotations

import math
import os
import traceback
from collections import OrderedDict
from dataclasses import replace
from typing import TYPE_CHECKING, Optional

import numpy as np
from PySide6.QtCore import QRectF, QSettings, QSize, Qt, QThread, QThreadPool, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QTransform,
)
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QSlider,
    QVBoxLayout, QWidget,
)

from ..motor import (
    Cancelado, DESCRIPCIONES_PRESETS, GRUPOS_PRESETS, PRESET_ANTI_IA, PRESET_PRINCIPAL, procesar_pila, reducir_para_vista,
)
from .. import edicion
from . import estilo, iconos, presets_usuario
from .controles import SIN_EFECTO, SeccionPlegable, todos_los_presets
from .tareas import SenalesTarea, Tarea

if TYPE_CHECKING:  # pragma: no cover
    from .ventana import VentanaPrincipal

# ------------------------------------------------------------------ preferencias
ORGANIZACION = "NaturalShot"
APLICACION = "NaturalShot PRO"
CLAVE_MODO = "interfaz/modo"
CLAVE_MODO_FOTOS = "interfaz/modo_fotos"  # el último de fotos (a donde se vuelve desde Audio al abrir)
# Los modos del selector. Video (el editor de video, en la misma ventana) no se guarda: si se
# cierra la app estando en Video, la próxima vez arranca en el último modo de fotos. Audio sí se
# guarda (y aparte, el último modo de fotos, para volver a él).
FACIL, EDITOR, VIDEO, AUDIO = "facil", "editor", "video", "audio"
# NaturalShot Lite: el modo "Photoshop" (capas, sin el filtro). Se guarda como Fácil y Editor.
PHOTOSHOP = "photoshop"
# Para las pruebas: un .ini propio en vez del registro de Windows del usuario.
VARIABLE_CONFIG = "NATURALSHOT_CONFIG"

LADO_ESTILO = 256  # lado largo de las miniaturas de la galería
MAX_CACHE = 240  # miniaturas guardadas (unas 7 fotos con todos los estilos)

# Los que más se usan, en este orden. El resto queda en "Ver más estilos".
RECOMENDADOS = (
    PRESET_PRINCIPAL,
    "Celular natural — sutil",
    "Celular natural — marcado",
    PRESET_ANTI_IA,
    "Estilo iPhone 15 Pro",
    "Estilo Samsung Galaxy S23",
    "Interior con luz cálida",
    "Noche urbana",
)
# Un nombre por grupo de GRUPOS_PRESETS, en el mismo orden (los del README).
NOMBRES_GRUPOS = ("Generales", "Fotos de IA", "Perfiles fotográficos", "Teléfonos", "Luz y lugar",
                  "Personas y temas", "Tipo de cámara", "Parciales")
# Nombres cortos para que entren en la tarjeta; el nombre completo queda en la ayuda.
NOMBRES_CORTOS = {
    PRESET_PRINCIPAL: "Natural iPhone 13",
    "Celular natural — sutil": "Natural sutil",
    "Celular natural — marcado": "Natural marcado",
    PRESET_ANTI_IA: "Anti IA · piel real",
    "Smartphone moderno — foto cotidiana": "Smartphone moderno",
    "Smartphone antiguo — menos rango dinámico": "Smartphone antiguo",
    "JPEG comprimido de redes sociales": "JPEG de redes",
    "Estilo Samsung Galaxy A (gama media)": "Galaxy A (gama media)",
    "Estilo Samsung Galaxy S23": "Galaxy S23",
    "Interior con luz cálida": "Interior cálido",
    "Solo textura (sin tocar el color)": "Solo textura",
    "Solo color y tono (sin textura)": "Solo color y tono",
    "Foto reenviada por mensajería": "Reenviada por chat",
    SIN_EFECTO: "Sin efecto",
}


def configuracion() -> QSettings:
    """Preferencias de la interfaz (QSettings de "NaturalShot" / "NaturalShot PRO"; en la Lite,
    "NaturalShot" / "NaturalShot Lite": ``edicion.organizacion_qsettings``).

    Si está definida la variable ``NATURALSHOT_CONFIG``, se usa ese archivo .ini
    (las pruebas no tocan las preferencias del usuario)."""
    ruta = os.environ.get(VARIABLE_CONFIG)
    if ruta:
        return QSettings(ruta, QSettings.IniFormat)
    return QSettings(*edicion.organizacion_qsettings())


def modo_guardado() -> str:
    """El último modo usado: Fácil, Editor o Audio (Video no se guarda). La primera vez, Fácil."""
    valor = configuracion().value(CLAVE_MODO, FACIL)
    if edicion.es_lite():  # la Lite no tiene Audio (pero sí Photoshop): si no, el último de fotos
        return valor if valor in (FACIL, EDITOR, PHOTOSHOP) else modo_fotos_guardado()
    return valor if valor in (FACIL, EDITOR, AUDIO) else FACIL


def modo_fotos_guardado() -> str:
    """El último modo de fotos usado (Fácil o Editor), aunque después se haya pasado a Audio."""
    config = configuracion()
    valor = config.value(CLAVE_MODO_FOTOS, None)
    if valor not in (FACIL, EDITOR):
        valor = config.value(CLAVE_MODO, FACIL)  # de antes del modo Audio: el modo era siempre de fotos
    return valor if valor in (FACIL, EDITOR) else FACIL


def guardar_modo(modo: str) -> None:
    """Recuerda el modo: Fácil, Editor o Audio (en la Lite, también Photoshop). Video no se guarda."""
    lite = edicion.es_lite()
    if modo not in (FACIL, EDITOR, AUDIO, PHOTOSHOP) or (modo == AUDIO and lite) or (modo == PHOTOSHOP and not lite):
        return
    config = configuracion()
    config.setValue(CLAVE_MODO, modo)
    if modo in (FACIL, EDITOR):
        config.setValue(CLAVE_MODO_FOTOS, modo)
    config.sync()


def nombre_corto(nombre: str) -> str:
    if nombre in NOMBRES_CORTOS:
        return NOMBRES_CORTOS[nombre]
    return nombre.removeprefix("Estilo ")


def grupos_mas() -> list[tuple[str, tuple[str, ...]]]:
    """Los estilos de "Ver más", agrupados como en ``GRUPOS_PRESETS``, más los propios."""
    grupos = []
    for i, grupo in enumerate(GRUPOS_PRESETS):
        nombres = tuple(n for n in grupo if n not in RECOMENDADOS)
        if nombres:
            grupos.append((NOMBRES_GRUPOS[i] if i < len(NOMBRES_GRUPOS) else "Más estilos", nombres))
    propios = tuple(presets_usuario.cargar())
    if propios:
        grupos.append(("Tus presets", propios))
    grupos.append(("Sin filtro", (SIN_EFECTO,)))
    return grupos


def icono_con_activo(nombre: str, tam: int = 16) -> QIcon:
    """Ícono del tema que se vuelve blanco cuando el botón está marcado (sobre el degradado)."""
    ic = QIcon(iconos.icono(nombre, tam))
    for modo in (QIcon.Normal, QIcon.Active, QIcon.Selected):
        ic.addPixmap(iconos.pixmap(nombre, tam, "#ffffff"), modo, QIcon.On)
    return ic


def _a_qimage(rgb: np.ndarray) -> QImage:
    rgb = np.ascontiguousarray(rgb)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


def _lineas(fm: QFontMetrics, texto: str, ancho: float, maximo: int = 2) -> list[str]:
    """Parte el texto en hasta ``maximo`` líneas por palabras; la última se corta con "…"."""
    lineas: list[str] = []
    resto = texto.split()
    while resto and len(lineas) < maximo - 1:
        linea = resto.pop(0)
        while resto and fm.horizontalAdvance(linea + " " + resto[0]) <= ancho:
            linea += " " + resto.pop(0)
        lineas.append(linea)
    if resto:
        lineas.append(" ".join(resto))
    return [fm.elidedText(l, Qt.ElideRight, int(ancho)) for l in lineas]


def _enumerar(partes: list[str]) -> str:
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


# ======================================================================== tarjetas
class TarjetaPaso(SeccionPlegable):
    """Tarjeta de un paso: la misma de las secciones del editor, con el número del paso
    en la insignia, una línea opcional que dice qué hacer y lugar a la derecha de la
    cabecera para un control chico (así los pasos fijos de abajo ocupan poco alto)."""

    def __init__(self, numero: int, nombre: str, subtitulo: str = "", parent=None):
        super().__init__(nombre, "check", subtitulo or nombre, True, parent, con_interruptor=False,
                         plegable=False)
        fila = self.cabecera.layout()
        fila.setContentsMargins(10, 7, 10, 7)
        insignia = fila.itemAt(0).widget()  # (insignia, textos, interruptor, flecha)
        insignia.setPixmap(QPixmap())
        insignia.setStyleSheet("")
        insignia.setObjectName("numeroPaso")
        insignia.setFixedSize(26, 26)
        insignia.setText(str(numero))
        self.subtitulo = QLabel(subtitulo)
        self.subtitulo.setObjectName("subtituloCaja")
        # No ensancha la columna aunque el texto no entre (letra grande o escalado de Windows).
        self.subtitulo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.subtitulo.setMinimumWidth(0)
        fila.itemAt(1).layout().addWidget(self.subtitulo)
        self.subtitulo.setVisible(bool(subtitulo))  # ya con padre: no abre una ventana suelta

    def agregar_a_cabecera(self, widget: QWidget) -> None:
        self.cabecera.layout().addWidget(widget, 0, Qt.AlignVCenter)


class TarjetaEstilo(QWidget):
    """Una tarjeta de la galería: la foto con ese estilo (bordes redondeados), su nombre
    debajo y, si es la elegida, borde magenta y un tilde."""

    elegida = Signal(str)
    MARGEN = 6
    ALTO_MINI = 90
    ALTO = 138

    def __init__(self, nombre: str, parent=None):
        super().__init__(parent)
        self.nombre = nombre
        self.texto = nombre_corto(nombre)
        self.miniatura: Optional[QPixmap] = None
        self.cargando = False
        self._fase = 0.0
        self._seleccionada = False
        self._encima = False
        self._apretada = False
        self.setFixedHeight(self.ALTO)
        self.setMinimumWidth(110)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)  # con Tab y Enter también se elige
        if nombre == SIN_EFECTO:
            descripcion = "La foto tal cual, sin el filtro."
        else:
            descripcion = DESCRIPCIONES_PRESETS.get(nombre, "Preset guardado por vos.")
        self.setToolTip(f"<b>{nombre}</b><br>{descripcion}")
        self.setAccessibleName(f"Estilo {nombre}")

    def sizeHint(self) -> QSize:
        return QSize(150, self.ALTO)

    # ---------------------------------------------------------------- estado
    @property
    def seleccionada(self) -> bool:
        return self._seleccionada

    def establecer_seleccionada(self, valor: bool) -> None:
        if valor != self._seleccionada:
            self._seleccionada = valor
            self.update()

    def establecer_miniatura(self, pixmap: Optional[QPixmap]) -> None:
        self.miniatura = pixmap
        self.cargando = False
        self.update()

    def establecer_cargando(self, valor: bool) -> None:
        if valor != self.cargando:
            self.cargando = valor
            self.update()

    def latir(self) -> None:
        self._fase += 0.55
        self.update()

    # ---------------------------------------------------------------- eventos
    def enterEvent(self, evento) -> None:
        self._encima = True
        self.update()
        super().enterEvent(evento)

    def leaveEvent(self, evento) -> None:
        self._encima = False
        self._apretada = False
        self.update()
        super().leaveEvent(evento)

    def mousePressEvent(self, evento) -> None:
        if evento.button() == Qt.LeftButton:
            self._apretada = True
            self.update()
        super().mousePressEvent(evento)

    def mouseReleaseEvent(self, evento) -> None:
        if evento.button() == Qt.LeftButton and self._apretada:
            self._apretada = False
            self.update()
            if self.rect().contains(evento.position().toPoint()):
                self.elegida.emit(self.nombre)
        super().mouseReleaseEvent(evento)

    def keyPressEvent(self, evento) -> None:
        if evento.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.elegida.emit(self.nombre)
            return
        super().keyPressEvent(evento)

    def focusInEvent(self, evento) -> None:
        self.update()
        super().focusInEvent(evento)

    def focusOutEvent(self, evento) -> None:
        self.update()
        super().focusOutEvent(evento)

    # ---------------------------------------------------------------- dibujo
    def _rect_miniatura(self) -> QRectF:
        m = self.MARGEN
        return QRectF(m, m, self.width() - 2 * m, self.ALTO_MINI)

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        sel, encima = self._seleccionada, self._encima
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
        p.setPen(QPen(borde, grosor))
        p.setBrush(fondo)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(grosor / 2, grosor / 2, -grosor / 2, -grosor / 2), 12, 12)

        mini = self._rect_miniatura()
        camino = QPainterPath()
        camino.addRoundedRect(mini, 8, 8)
        p.save()
        p.setClipPath(camino)
        pm = self.miniatura
        if pm is not None and not pm.isNull():
            # Como "cubrir": llena el recuadro y recorta lo que sobra, centrado.
            f = max(mini.width() / pm.width(), mini.height() / pm.height())
            w, h = pm.width() * f, pm.height() * f
            destino = QRectF(mini.center().x() - w / 2, mini.center().y() - h / 2, w, h)
            if self.cargando:
                p.setOpacity(0.45)
            p.drawPixmap(destino, pm, QRectF(pm.rect()))
            p.setOpacity(1.0)
            if self.cargando:
                self._dibujar_latido(p, mini, sobre_foto=True)
        else:
            p.fillRect(mini, QColor("#3a3c43"))
            if self.cargando:
                self._dibujar_latido(p, mini, sobre_foto=False)
            nombre_icono = iconos.ICONO_PRESET.get(self.nombre, "bookmark-plus")
            ic = iconos.pixmap(nombre_icono, 24, estilo.TEXTO_TENUE)
            p.setOpacity(0.55 + 0.35 * (0.5 + 0.5 * math.sin(self._fase)) if self.cargando else 0.8)
            p.drawPixmap(QRectF(mini.center().x() - 12, mini.center().y() - 12, 24, 24), ic, QRectF(ic.rect()))
            p.setOpacity(1.0)
        p.restore()
        if encima and not sel and pm is not None:
            p.setPen(QPen(QColor(255, 255, 255, 40), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(mini.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)

        if sel:  # tilde en la esquina de la foto
            c = QRectF(mini.right() - 25, mini.top() + 5, 20, 20)
            grad = QLinearGradient(c.topLeft(), c.bottomRight())
            grad.setColorAt(0, QColor(estilo.MAGENTA))
            grad.setColorAt(1, QColor(estilo.VIOLETA))
            p.setPen(QPen(QColor("#ffffff"), 1.5))
            p.setBrush(grad)
            p.drawEllipse(c)
            tilde = iconos.pixmap("check", 12, "#ffffff")
            p.drawPixmap(QRectF(c.center().x() - 6, c.center().y() - 6, 12, 12), tilde, QRectF(tilde.rect()))

        fuente = QFont(self.font())
        fuente.setPointSizeF(9.0)
        fuente.setWeight(QFont.DemiBold if sel else QFont.Medium)
        p.setFont(fuente)
        fm = QFontMetrics(fuente)
        p.setPen(QColor(estilo.TEXTO if (sel or encima) else estilo.TEXTO_2))
        ancho = self.width() - 2 * (self.MARGEN + 4)
        y = mini.bottom() + 6
        for linea in _lineas(fm, self.texto, ancho):
            p.drawText(QRectF(self.MARGEN + 4, y, ancho, fm.height()), Qt.AlignHCenter | Qt.AlignVCenter, linea)
            y += fm.height()
        p.end()

    def _dibujar_latido(self, p: QPainter, mini: QRectF, sobre_foto: bool) -> None:
        """Marcador mientras se calcula: un brillo que cruza la tarjeta."""
        ancho = mini.width() * 0.55
        recorrido = mini.width() + ancho
        x = mini.left() - ancho + (self._fase * 0.18 % 1.0) * recorrido
        grad = QLinearGradient(x, 0, x + ancho, 0)
        alfa = 46 if sobre_foto else 30
        grad.setColorAt(0, QColor(255, 255, 255, 0))
        grad.setColorAt(0.5, QColor(240, 171, 252, alfa))
        grad.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(mini, grad)


class GaleriaEstilos(QWidget):
    """Recomendados en dos columnas y "Ver más estilos", que despliega el resto por grupos."""

    elegido = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tarjetas: dict[str, TarjetaEstilo] = {}
        self._seleccionado: Optional[str] = None
        self._grupos_mas: Optional[list] = None
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(8)
        capa.addWidget(self._titulo("Recomendados"))
        capa.addWidget(self._grilla(RECOMENDADOS))

        self.boton_mas = QPushButton()
        self.boton_mas.setObjectName("botonVerMas")
        self.boton_mas.setCheckable(True)
        self.boton_mas.setCursor(Qt.PointingHandCursor)
        self.boton_mas.setToolTip("Mostrar todos los estilos, agrupados")
        self.boton_mas.toggled.connect(self._alternar_mas)
        capa.addWidget(self.boton_mas)
        self.contenedor_mas = QWidget()
        self._capa_mas = QVBoxLayout(self.contenedor_mas)
        self._capa_mas.setContentsMargins(0, 2, 0, 0)
        self._capa_mas.setSpacing(8)
        self.contenedor_mas.hide()
        capa.addWidget(self.contenedor_mas)
        self.reconstruir_mas(grupos_mas())

        self._timer_latido = QTimer(self, interval=80)
        self._timer_latido.timeout.connect(self._latir)

    @staticmethod
    def _titulo(texto: str) -> QLabel:
        etiqueta = QLabel(texto.upper())
        etiqueta.setObjectName("tituloGaleria")
        return etiqueta

    def _grilla(self, nombres) -> QWidget:
        caja = QWidget()
        grilla = QGridLayout(caja)
        grilla.setContentsMargins(0, 0, 0, 0)
        grilla.setSpacing(8)
        for i, nombre in enumerate(nombres):
            tarjeta = TarjetaEstilo(nombre)
            tarjeta.elegida.connect(self.elegido)
            tarjeta.establecer_seleccionada(nombre == self._seleccionado)
            self.tarjetas[nombre] = tarjeta
            grilla.addWidget(tarjeta, i // 2, i % 2)
        if len(nombres) % 2:
            # Un hueco invisible: si no, una tarjeta sola en su fila sale más ancha que las otras.
            hueco = QWidget()
            hueco.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            grilla.addWidget(hueco, len(nombres) // 2, 1)
        grilla.setColumnStretch(0, 1)
        grilla.setColumnStretch(1, 1)
        return caja

    def reconstruir_mas(self, grupos: list) -> bool:
        """Arma los grupos de "Ver más" (cambian si se guardan o borran presets propios)."""
        if grupos == self._grupos_mas:
            return False
        for nombre in [n for g in (self._grupos_mas or []) for n in g[1]]:
            tarjeta = self.tarjetas.pop(nombre, None)
            if tarjeta is not None:
                tarjeta.deleteLater()
        while self._capa_mas.count():
            item = self._capa_mas.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._grupos_mas = grupos
        for titulo, nombres in grupos:
            self._capa_mas.addWidget(self._titulo(titulo))
            self._capa_mas.addWidget(self._grilla(nombres))
        self._texto_boton_mas()
        return True

    def _texto_boton_mas(self) -> None:
        abierto = self.boton_mas.isChecked()
        n = sum(len(g[1]) for g in self._grupos_mas or [])
        self.boton_mas.setText(" Ver menos estilos" if abierto else f" Ver más estilos ({n})")
        pm = iconos.pixmap("chevron-down", 16)
        if abierto:  # la misma flecha, hacia arriba
            pm = pm.transformed(QTransform().rotate(180))
            pm.setDevicePixelRatio(iconos.pixmap("chevron-down", 16).devicePixelRatio())
        self.boton_mas.setIcon(QIcon(pm))

    def _alternar_mas(self, abierto: bool) -> None:
        self.contenedor_mas.setVisible(abierto)
        self._texto_boton_mas()

    def mostrar_mas(self, abierto: bool) -> None:
        self.boton_mas.setChecked(abierto)

    def orden(self) -> list[str]:
        """Todos los estilos de la galería, en el orden en que se ven."""
        return list(RECOMENDADOS) + [n for _t, nombres in self._grupos_mas or [] for n in nombres]

    def seleccionar(self, nombre: Optional[str]) -> None:
        self._seleccionado = nombre
        for n, t in self.tarjetas.items():
            t.establecer_seleccionada(n == nombre)

    @property
    def seleccionado(self) -> Optional[str]:
        return self._seleccionado

    def establecer_miniatura(self, nombre: str, pixmap: Optional[QPixmap]) -> None:
        tarjeta = self.tarjetas.get(nombre)
        if tarjeta is not None:
            tarjeta.establecer_miniatura(pixmap)

    def establecer_cargando(self, nombre: str, valor: bool) -> None:
        tarjeta = self.tarjetas.get(nombre)
        if tarjeta is not None:
            tarjeta.establecer_cargando(valor)
        if valor and not self._timer_latido.isActive():
            self._timer_latido.start()

    def _latir(self) -> None:
        cargando = [t for t in self.tarjetas.values() if t.cargando]
        if not cargando:
            self._timer_latido.stop()
            return
        for t in cargando:
            if t.isVisible():
                t.latir()


# ======================================================================== panel
class PanelFacil(QWidget):
    """La columna izquierda del modo fácil: cuatro pasos numerados.

    Los pasos 1 y 2 se desplazan; el 3 (intensidad) y el 4 (exportar) quedan fijos
    abajo, siempre a la vista aunque la galería sea larga.
    """

    def __init__(self, ventana: "VentanaPrincipal"):
        super().__init__()
        self._ventana = ventana
        self._cache: "OrderedDict[tuple, QPixmap]" = OrderedDict()
        self._clave_fuente: Optional[tuple] = None  # foto de las miniaturas que se ven
        self._pendientes: set = set()
        self._generacion = 0
        self.calculadas = 0  # miniaturas calculadas (no salidas de la caché)
        # Un hilo propio y de baja prioridad: la vista previa nunca espera a la galería.
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._pool.setThreadPriority(QThread.LowPriority)
        self._senales = SenalesTarea(self)
        self._senales.terminada.connect(self._miniatura_lista)
        self._senales.fallida.connect(self._miniatura_fallida)
        self._timer_miniaturas = QTimer(self, singleShot=True, interval=250)
        self._timer_miniaturas.timeout.connect(self._lanzar_miniaturas)
        # Varios cambios seguidos (restaurar el historial toca varios paneles) = una sola actualización.
        self._timer_sincronizar = QTimer(self, singleShot=True, interval=0)
        self._timer_sincronizar.timeout.connect(self.sincronizar)

        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(0)
        contenido = QWidget()
        capa_contenido = QVBoxLayout(contenido)
        capa_contenido.setContentsMargins(16, 2, 12, 12)
        capa_contenido.setSpacing(10)
        capa_contenido.addWidget(self._construir_paso_foto())
        capa_contenido.addWidget(self._construir_paso_estilo())
        capa_contenido.addStretch(1)
        self.desplazable = QScrollArea()
        self.desplazable.setWidgetResizable(True)
        self.desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.desplazable.setWidget(contenido)
        capa.addWidget(self.desplazable, 1)

        pie = QFrame()
        pie.setObjectName("pieFacil")
        capa_pie = QVBoxLayout(pie)
        capa_pie.setContentsMargins(16, 8, 20, 10)
        capa_pie.setSpacing(8)
        capa_pie.addWidget(self._construir_paso_intensidad())
        capa_pie.addWidget(self._construir_paso_exportar())
        capa.addWidget(pie)

        v = ventana
        v.panel_ajustes.ajustesCambiados.connect(self._programar_sincronizacion)
        v.panel_montaje.cambiado.connect(self._programar_sincronizacion)
        v.panel_fondo.cambiado.connect(self._programar_sincronizacion)
        v.panel_borrar.cambiado.connect(self._programar_sincronizacion)
        v.grupo_formato.buttonClicked.connect(self._sincronizar_formato)
        self.sincronizar()
        self._sincronizar_formato()
        self.actualizar_habilitados()

    # ------------------------------------------------------------ construcción
    def _construir_paso_foto(self) -> QWidget:
        paso = TarjetaPaso(1, "Tu foto", "Abrí una o varias, o arrastralas a la vista")
        self.paso_foto = paso
        # Con una foto abierta el paso queda en una línea: el nombre y un botón chico.
        self.boton_abrir_chico = QPushButton(" Abrir fotos")
        self.boton_abrir_chico.setObjectName("botonChico")
        self.boton_abrir_chico.setIcon(iconos.icono(iconos.ABRIR, 15))
        self.boton_abrir_chico.setCursor(Qt.PointingHandCursor)
        self.boton_abrir_chico.setToolTip("Abrir más fotos (Ctrl+O). También podés arrastrarlas a la vista previa.")
        self.boton_abrir_chico.clicked.connect(lambda: self._ventana.elegir_archivo())
        self.boton_abrir_chico.hide()
        paso.agregar_a_cabecera(self.boton_abrir_chico)

        cuerpo = paso.capa_cuerpo
        self.boton_abrir = QPushButton("  Abrir fotos")
        self.boton_abrir.setObjectName("botonPrimario")
        self.boton_abrir.setProperty("grande", True)
        self.boton_abrir.setIcon(iconos.icono(iconos.ABRIR, 18, color="#ffffff"))
        self.boton_abrir.setIconSize(QSize(18, 18))
        self.boton_abrir.setCursor(Qt.PointingHandCursor)
        self.boton_abrir.setToolTip("Abrir una o varias fotos (Ctrl+O). También podés arrastrarlas a la vista previa.")
        self.boton_abrir.clicked.connect(lambda: self._ventana.elegir_archivo())
        cuerpo.addWidget(self.boton_abrir)
        self.etiqueta_foto = QLabel("O arrastralas a la vista previa. JPG, PNG, WEBP, TIFF o BMP.")
        self.etiqueta_foto.setObjectName("nota")
        self.etiqueta_foto.setWordWrap(True)
        cuerpo.addWidget(self.etiqueta_foto)
        return paso

    def _construir_paso_estilo(self) -> QWidget:
        paso = TarjetaPaso(2, "Elegí un estilo", "Tocá uno para aplicarlo a tu foto")
        self.nota_estilos = QLabel("Abrí una foto para ver cada estilo aplicado a ella. Si elegís uno antes, "
                                   "se usa al abrirla.")
        self.nota_estilos.setObjectName("nota")
        self.nota_estilos.setWordWrap(True)
        paso.capa_cuerpo.addWidget(self.nota_estilos)

        # Aviso chico si la foto tiene ediciones hechas en el modo Editor.
        self.nota_editor = QFrame()
        self.nota_editor.setObjectName("notaEditor")
        fila = QHBoxLayout(self.nota_editor)
        fila.setContentsMargins(8, 6, 8, 6)
        fila.setSpacing(7)
        icono = QLabel()
        icono.setPixmap(iconos.pixmap("info", 14, estilo.ROSA))
        icono.setFixedSize(16, 16)
        fila.addWidget(icono, 0, Qt.AlignTop)
        self.texto_nota_editor = QLabel()
        self.texto_nota_editor.setObjectName("textoNotaEditor")
        self.texto_nota_editor.setWordWrap(True)
        fila.addWidget(self.texto_nota_editor, 1)
        self.nota_editor.hide()
        paso.capa_cuerpo.addWidget(self.nota_editor)

        self.galeria = GaleriaEstilos()
        self.galeria.elegido.connect(self.elegir_estilo)
        paso.capa_cuerpo.addWidget(self.galeria)
        return paso

    def _construir_paso_intensidad(self) -> QWidget:
        paso = TarjetaPaso(3, "¿Cuánto efecto?")
        self.valor_intensidad = QLabel("100 %")
        self.valor_intensidad.setObjectName("valorControl")
        self.valor_intensidad.setAlignment(Qt.AlignCenter)
        self.valor_intensidad.setFixedWidth(52)
        paso.agregar_a_cabecera(self.valor_intensidad)
        self.slider_intensidad = QSlider(Qt.Horizontal)
        self.slider_intensidad.setRange(0, 100)
        self.slider_intensidad.setPageStep(5)
        self.slider_intensidad.setToolTip("Cuánto se nota el estilo. 0 deja la foto como está; 100 es el estilo "
                                          "completo.")
        self.slider_intensidad.valueChanged.connect(self._al_mover_intensidad)
        paso.capa_cuerpo.setSpacing(2)
        paso.capa_cuerpo.setContentsMargins(12, 8, 12, 8)
        paso.capa_cuerpo.addWidget(self.slider_intensidad)
        referencias = QHBoxLayout()
        referencias.setContentsMargins(0, 0, 0, 0)
        for i, texto in enumerate(("Sutil", "Normal", "Fuerte")):
            etiqueta = QLabel(texto)
            etiqueta.setObjectName("referenciaIntensidad")
            etiqueta.setAlignment((Qt.AlignLeft, Qt.AlignHCenter, Qt.AlignRight)[i] | Qt.AlignVCenter)
            referencias.addWidget(etiqueta, 1)
        paso.capa_cuerpo.addLayout(referencias)
        return paso

    def _construir_paso_exportar(self) -> QWidget:
        paso = TarjetaPaso(4, "Exportar")
        self.boton_lote = QPushButton(" Exportar varias fotos…")
        self.boton_lote.setObjectName("botonEnlace")
        self.boton_lote.setIcon(iconos.icono("images", 15))
        self.boton_lote.setCursor(Qt.PointingHandCursor)
        self.boton_lote.setToolTip("Aplica el estilo y la intensidad actuales a muchas fotos y guarda archivos "
                                   "nuevos (no aplica recortes, giros ni ediciones propias de cada foto; las de "
                                   "la tira con una Medida sí salen con su encuadre y en esa medida).")
        self.boton_lote.clicked.connect(lambda: self._ventana.procesar_varias())
        paso.agregar_a_cabecera(self.boton_lote)

        cuerpo = paso.capa_cuerpo
        cuerpo.setSpacing(8)
        cuerpo.setContentsMargins(12, 8, 12, 10)
        selector = QFrame()
        selector.setObjectName("selectorFormato")
        fila = QHBoxLayout(selector)
        fila.setContentsMargins(3, 3, 3, 3)
        fila.setSpacing(3)
        self.grupo_formato = QButtonGroup(self)
        self.grupo_formato.setExclusive(True)
        self.botones_formato: dict[str, QPushButton] = {}
        for formato, texto, ayuda in (
            ("PNG", "Mejor calidad (PNG)", "Sin pérdida: la máxima calidad. El archivo pesa más."),
            ("JPEG", "Más liviano (JPEG)", "Archivo mucho más liviano, con muy buena calidad (92)."),
        ):
            b = QPushButton(texto)
            b.setObjectName("opcionFormato")
            b.setProperty("centrado", True)
            b.setProperty("formato", formato)
            b.setCheckable(True)
            b.setToolTip(ayuda)
            b.setCursor(Qt.PointingHandCursor)
            self.grupo_formato.addButton(b)
            self.botones_formato[formato] = b
            fila.addWidget(b, 1)
        self.grupo_formato.buttonClicked.connect(lambda b: self._elegir_formato(b.property("formato")))
        cuerpo.addWidget(selector)

        self.boton_exportar = QPushButton("  Exportar foto")
        self.boton_exportar.setObjectName("botonPrimario")
        self.boton_exportar.setProperty("grande", True)
        self.boton_exportar.setIcon(iconos.icono(iconos.GUARDAR, 20, color="#ffffff"))
        self.boton_exportar.setIconSize(QSize(20, 20))
        self.boton_exportar.setCursor(Qt.PointingHandCursor)
        self.boton_exportar.setToolTip("Guarda la foto como un archivo nuevo, con el mismo tamaño o en la Medida que "
                                       "elegiste (Ctrl+Shift+E). "
                                       "El original no se modifica.")
        self.boton_exportar.clicked.connect(lambda: self._ventana.exportar())
        cuerpo.addWidget(self.boton_exportar)
        return paso

    # ------------------------------------------------------------ estilo e intensidad
    def elegir_estilo(self, nombre: str) -> None:
        """Tocar una tarjeta: cambia el preset base como el desplegable del editor
        (conserva la intensidad y queda en el historial)."""
        combo = self._ventana.panel_ajustes.combo_preset
        if combo.findText(nombre) < 0:
            return
        self.galeria.seleccionar(nombre)
        combo.setCurrentText(nombre)

    def _al_mover_intensidad(self, valor: int) -> None:
        self.valor_intensidad.setText(f"{valor} %")
        # El mismo deslizador del editor: emite el cambio y lo anota en el historial.
        self._ventana.panel_ajustes.intensidad.slider.setValue(valor)

    # ------------------------------------------------------------ exportar
    def _elegir_formato(self, formato: str) -> None:
        """Usa el selector de formato del editor (la exportación es una sola)."""
        v = self._ventana
        for b in v.grupo_formato.buttons():
            if b.property("formato") == formato:
                b.setChecked(True)
        v._al_cambiar_formato()

    def _sincronizar_formato(self, *_args) -> None:
        boton = self.botones_formato.get(self._ventana._formato())
        if boton is not None:
            boton.setChecked(True)

    def actualizar_habilitados(self) -> None:
        v = self._ventana
        hay = v._imagen is not None
        self.boton_exportar.setEnabled(hay and not v._exportando)
        self.boton_exportar.setText("  Exportando…" if v._exportando else "  Exportar foto")
        self.boton_lote.setEnabled(not v._exportando)

    # ------------------------------------------------------------ sincronización
    def _programar_sincronizacion(self, *_args) -> None:
        # En el modo editor no se gasta nada: al volver a Fácil se sincroniza todo (showEvent).
        if self.isVisible():
            self._timer_sincronizar.start()

    def foto_cambiada(self) -> None:
        """Se abrió otra foto (o la misma de la tira)."""
        self.fuente_cambiada()

    def sincronizar(self) -> None:
        """Pone los pasos igual que el editor: estilo elegido, intensidad, foto y aviso."""
        v = self._ventana
        pa = v.panel_ajustes
        preset = pa.estado()["preset"]
        if preset not in self.galeria.tarjetas:
            self._refrescar_presets()
        self.galeria.seleccionar(preset)
        self.slider_intensidad.blockSignals(True)
        self.slider_intensidad.setValue(pa.ajustes().intensidad)
        self.slider_intensidad.blockSignals(False)
        self.valor_intensidad.setText(f"{pa.ajustes().intensidad} %")
        self._actualizar_foto()
        self._actualizar_nota()

    def _actualizar_foto(self) -> None:
        """Sin foto, el paso 1 muestra el botón grande; con foto, queda en una línea."""
        v = self._ventana
        imagen = v._imagen
        paso = self.paso_foto
        paso.cuerpo.setVisible(imagen is None)
        self.boton_abrir_chico.setVisible(imagen is not None)
        self.nota_estilos.setVisible(imagen is None)
        if imagen is None:
            paso.subtitulo.setText("Abrí una o varias, o arrastralas a la vista")
            paso.subtitulo.setToolTip("")
            return
        if v._fuente is not None:
            h, w = v._fuente.shape[:2]
        else:
            w, h = imagen.ancho, imagen.alto
        cantidad = len(v._fotos)
        prefijo = f"{v._actual + 1} de {cantidad}  ·  " if cantidad > 1 else ""
        fm = paso.subtitulo.fontMetrics()
        disponible = max(60, 168 - fm.horizontalAdvance(prefijo))
        from .documento_capas import nombre_documento  # un documento nuevo se muestra sin su extensión
        paso.subtitulo.setText(prefijo + fm.elidedText(nombre_documento(imagen.ruta), Qt.ElideMiddle, disponible))
        paso.subtitulo.setToolTip(f"{imagen.ruta}\n{w} × {h} px" +
                                  ("\nCambiá de foto en la tira de abajo." if cantidad > 1 else ""))

    def ediciones_editor(self) -> list[str]:
        """Lo que la foto tiene hecho en el modo Editor y el modo fácil no muestra."""
        v = self._ventana
        partes = []
        if v.panel_ajustes.capas():
            partes.append("efectos" if edicion.es_lite() else "capas")  # en la PRO se siguen llamando "capas"
        if v.panel_montaje.estado():
            partes.append("montaje")
        if v.panel_borrar.estado():
            partes.append("objetos borrados")
        if v.panel_fondo.zona is not None:
            partes.append("fondo")
        g = v._geometria.normalizada()
        if g.enderezar:
            partes.append("enderezado")
        if g.voltear_h or g.voltear_v:
            partes.append("volteo")
        return partes

    def ajustes_finos_modificados(self) -> bool:
        """Si se tocaron controles del editor respecto del preset (elegir otro estilo los reemplaza)."""
        pa = self._ventana.panel_ajustes
        referencia = todos_los_presets().get(pa.estado()["preset"])
        if referencia is None:
            return False
        actual = pa.ajustes()
        return replace(referencia, intensidad=actual.intensidad) != actual

    def _actualizar_nota(self) -> None:
        if self._ventana._imagen is None:
            self.nota_editor.hide()
            return
        textos = []
        if self._ventana.tiene_capas_extra():
            # Las capas del modo Photoshop (Lite): Fácil las muestra, con el estilo elegido encima.
            textos.append("Esta foto tiene capas del modo Photoshop: se ven con el estilo encima y se mantienen.")
        partes = self.ediciones_editor()
        if partes:
            textos.append(f"Esta foto tiene ediciones del modo Editor ({_enumerar(partes)}) y se mantienen.")
        if self.ajustes_finos_modificados():
            textos.append("Tiene ajustes finos del modo Editor: si elegís otro estilo se reemplazan "
                          "(Ctrl+Z los recupera).")
        self.texto_nota_editor.setText(" ".join(textos))
        self.nota_editor.setVisible(bool(textos))

    def _refrescar_presets(self) -> None:
        """Suma o quita de la galería los presets propios (se guardan desde el editor)."""
        if self.galeria.reconstruir_mas(grupos_mas()):
            self.galeria.seleccionar(self._ventana.panel_ajustes.estado()["preset"])
            self._clave_fuente = None  # vuelve a poner las miniaturas en las tarjetas nuevas
            self.fuente_cambiada(inmediato=True)

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        self._refrescar_presets()
        self.sincronizar()
        self._sincronizar_formato()
        self.actualizar_habilitados()
        # Si el estilo elegido está en "Ver más", se despliega para que se vea.
        if self.galeria.seleccionado not in RECOMENDADOS and self.galeria.seleccionado in self.galeria.tarjetas:
            self.galeria.mostrar_mas(True)
        self.fuente_cambiada(inmediato=True)

    # ------------------------------------------------------------ miniaturas
    def fuente_cambiada(self, inmediato: bool = False) -> None:
        """La foto que entra al filtro cambió (otra foto, giro, recorte, montaje o borrados)."""
        self._programar_sincronizacion()  # el tamaño de la foto y el aviso del editor
        self._timer_miniaturas.start(30 if inmediato else 250)

    def _lanzar_miniaturas(self) -> None:
        """Pone en las tarjetas las miniaturas de la caché y calcula en segundo plano las que faltan."""
        if not self.isVisible():
            return  # en el modo editor no se gasta nada: se calculan al volver
        v = self._ventana
        if v._imagen is None:
            self._clave_fuente = None
            for nombre in self.galeria.orden():
                self.galeria.establecer_miniatura(nombre, None)
            return
        fuente = v.fuente_para_estilos()
        if fuente is None:
            return  # se está armando la foto (girar, recortar...): se vuelve a llamar al terminar
        clave, rgb, escala, transformacion = fuente
        if clave != self._clave_fuente:
            otra_foto = self._clave_fuente is None or self._clave_fuente[0][0] != clave[0][0]
            self._clave_fuente = clave
            self._generacion += 1
            self._pool.clear()  # lo que esperaba era de la foto anterior
            self._pendientes = set()
            if otra_foto:  # no mostrar la foto anterior mientras carga
                for nombre in self.galeria.orden():
                    self.galeria.establecer_miniatura(nombre, None)
        presets = todos_los_presets()
        chica, f = None, 1.0
        generacion = self._generacion
        for nombre in self.galeria.orden():
            ajustes = presets.get(nombre) if nombre != SIN_EFECTO else None
            if ajustes is None and nombre != SIN_EFECTO:
                continue
            k = (clave, nombre, ajustes)
            guardada = self._cache.get(k)
            if guardada is not None:
                self._cache.move_to_end(k)
                self.galeria.establecer_miniatura(nombre, guardada)
                continue
            if k in self._pendientes:
                continue
            if chica is None:
                chica, f = reducir_para_vista(rgb, LADO_ESTILO)
            self._pendientes.add(k)
            self.galeria.establecer_cargando(nombre, True)
            self._pool.start(Tarea("estilo", generacion, self._trabajo(k, chica, escala * f, ajustes, transformacion),
                                   self._senales, lambda: self._generacion))

    @staticmethod
    def _trabajo(k, chica, escala, ajustes, transformacion):
        def trabajo(cancelado):
            try:
                salida = chica if ajustes is None else procesar_pila(chica, (ajustes,), escala_vista=escala,
                                                                      cancelado=cancelado)
                return k, _a_qimage(transformacion.a_srgb(salida))
            except Cancelado:
                raise
            except Exception:  # sin miniatura: la tarjeta queda con su ícono y se puede elegir igual
                traceback.print_exc()
                return k, None
        return trabajo

    def _miniatura_lista(self, _tipo: str, _generacion: int, resultado) -> None:
        k, qimagen = resultado
        self._pendientes.discard(k)
        if qimagen is None:
            if k[0] == self._clave_fuente:
                self.galeria.establecer_cargando(k[1], False)
            return
        pixmap = QPixmap.fromImage(qimagen)
        # Es válida para su clave aunque la foto ya haya cambiado: se guarda igual.
        self._cache[k] = pixmap
        self._cache.move_to_end(k)
        while len(self._cache) > MAX_CACHE:
            self._cache.popitem(last=False)
        self.calculadas += 1
        if k[0] == self._clave_fuente:
            self.galeria.establecer_miniatura(k[1], pixmap)

    def _miniatura_fallida(self, _tipo: str, _generacion: int, _mensaje: str) -> None:
        pass  # los errores se devuelven como miniatura vacía (``_trabajo``)

    def miniaturas_listas(self) -> bool:
        """Si todas las tarjetas tienen su miniatura de la foto actual (para las pruebas)."""
        if self._clave_fuente is None or self._pendientes:
            return False
        return all(t.miniatura is not None and not t.cargando for t in self.galeria.tarjetas.values())

    def miniatura_en_cache(self, nombre: str) -> Optional[QPixmap]:
        presets = todos_los_presets()
        ajustes = presets.get(nombre) if nombre != SIN_EFECTO else None
        return self._cache.get((self._clave_fuente, nombre, ajustes))

    def detener(self) -> None:
        """Al cerrar: descarta lo que falta y espera a la miniatura en curso."""
        self._generacion += 1
        self._timer_miniaturas.stop()
        self._pool.clear()
        self._pool.waitForDone(3000)
