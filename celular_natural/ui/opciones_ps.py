"""Controles de Texto, Formas y degradados del modo Photoshop (NaturalShot Lite, Etapa 2, U2).

Los mismos controles van en dos lugares: en la **barra de opciones** (en fila, arriba de la vista) y
en **Propiedades** (en columna, a la derecha). No cambian nada por su cuenta: avisan qué cambió
(``cambio(dict)``, con los nombres de los campos de ``ParamsTexto`` o ``ParamsForma``) y quien los
usa decide (la herramienta: los valores para lo que se cree después y, si hay una capa de ese tipo
elegida, la cambia como un paso del historial).

* ``ControlesTexto``: familia (combo con búsqueda, ``familias_disponibles``), tamaño, color, negrita,
  cursiva, alineación (3 botones), interlineado y espaciado.
* ``ControlesForma``: el tipo (rectángulo, elipse, línea, flecha, polígono y estrella), el relleno
  (sin relleno, color o degradado), el trazo (color y grosor) y lo de cada tipo: radio (rectángulo),
  lados (polígono), puntas (estrella) y grosor o alto (línea y flecha).
* ``EditorDegradado``: de 2 a 4 colores con su posición, el tipo (lineal o radial) y el ángulo, con
  una muestra; ``DialogoDegradado`` lo abre en un diálogo y ``BotonRelleno`` muestra un relleno y lo
  cambia (el selector de color o el de degradado).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QAbstractSpinBox, QButtonGroup, QComboBox, QCompleter, QDialog, QDialogButtonBox, QDoubleSpinBox, QGridLayout,
    QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from ..motor.formas import ParamsForma, Relleno
from ..motor.texto import ParamsTexto
from . import iconos
from .selector_color import BotonColor, _tablero, elegir_color

NOMBRES_FORMA = {"rectangulo": "Rectángulo", "elipse": "Elipse", "linea": "Línea", "flecha": "Flecha",
                 "poligono": "Polígono", "estrella": "Estrella"}
ICONOS_FORMA = {"rectangulo": "ps-rectangulo", "elipse": "ps-elipse", "linea": "ps-linea", "flecha": "ps-flecha",
                "poligono": "ps-poligono", "estrella": "ps-estrella"}
TIPOS_RELLENO_FORMA = (("ninguno", "Sin relleno"), ("color", "Color"), ("lineal", "Lineal"), ("radial", "Radial"))
ICONOS_ALINEACION = {"izquierda": "ps-alinear-texto-izquierda", "centro": "ps-alinear-texto-centro",
                     "derecha": "ps-alinear-texto-derecha"}
NOMBRES_ALINEACION = {"izquierda": "Alinear a la izquierda", "centro": "Centrar", "derecha": "Alinear a la derecha"}


def _numero(minimo: float, maximo: float, decimales: int = 0, sufijo: str = "", prefijo: str = "",
            ancho: int = 64, paso: float = 1.0) -> QDoubleSpinBox:
    n = QDoubleSpinBox()
    n.setObjectName("valorControl")
    n.setRange(minimo, maximo)
    n.setDecimals(decimales)
    n.setSingleStep(paso)
    n.setSuffix(sufijo)
    n.setPrefix(prefijo)
    n.setButtonSymbols(QAbstractSpinBox.NoButtons)
    n.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    n.setKeyboardTracking(False)  # un valor escrito = un cambio (al Enter o al salir)
    n.setFixedWidth(ancho)
    return n


def _boton_icono(icono: str, ayuda: str, marcable: bool = True) -> QToolButton:
    b = QToolButton()
    b.setObjectName("botonOpcionPS")
    b.setIcon(iconos.icono(icono, 16))
    b.setIconSize(QSize(16, 16))
    b.setCheckable(marcable)
    b.setAutoRaise(True)
    b.setFixedSize(28, 26)
    b.setToolTip(ayuda)
    b.setFocusPolicy(Qt.NoFocus)
    b.setCursor(Qt.PointingHandCursor)
    return b


def _etiqueta(texto: str, ayuda: str = "") -> QLabel:
    e = QLabel(texto)
    e.setObjectName("etiquetaControl")
    if ayuda:
        e.setToolTip(ayuda)
    return e


# ---------------------------------------------------------------------------
# Muestra de un relleno
# ---------------------------------------------------------------------------

def pintar_relleno(p: QPainter, rect: QRectF, relleno: Relleno) -> None:
    """Dibuja el relleno (color o degradado) en ese rectángulo, sobre un tablero."""
    _tablero(p, rect, 5)
    if relleno.tipo == "ninguno":
        p.save()
        p.setPen(QPen(QColor(230, 60, 60), 2))
        p.drawLine(rect.bottomLeft(), rect.topRight())
        p.restore()
        return
    cols = relleno.colores
    if relleno.tipo == "color" or len(cols) == 1:
        p.fillRect(rect, QColor(*cols[0]))
        return
    paradas = relleno.paradas or tuple(i / (len(cols) - 1) for i in range(len(cols)))
    if relleno.tipo == "radial":
        g = QRadialGradient(rect.center(), max(rect.width(), rect.height()) / 2.0)
    else:
        g = QLinearGradient(rect.topLeft(), rect.topRight())
    for c, s in zip(cols, paradas):
        g.setColorAt(float(s), QColor(*c))
    p.fillRect(rect, g)


class MuestraRelleno(QWidget):
    """Una barra que muestra un relleno."""

    def __init__(self, relleno: Optional[Relleno] = None, parent=None):
        super().__init__(parent)
        self.relleno = relleno or Relleno()
        self.setMinimumSize(60, 18)

    def establecer(self, relleno: Relleno) -> None:
        self.relleno = relleno
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        camino = QPainterPath()
        camino.addRoundedRect(r, 4, 4)
        p.save()
        p.setClipPath(camino)
        rel = self.relleno
        if rel.tipo == "radial":  # en la barra se ve mejor de izquierda a derecha
            rel = replace(rel, tipo="lineal")
        pintar_relleno(p, r, rel)
        p.restore()
        p.setPen(QPen(QColor("#6b6e78"), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 4, 4)
        p.end()


# ---------------------------------------------------------------------------
# Editor de degradado
# ---------------------------------------------------------------------------

class EditorDegradado(QWidget):
    """De 2 a 4 colores con su posición (0-100 %), el tipo (lineal o radial, si ``con_tipo``) y el
    ángulo (lineal). ``cambiado(Relleno)`` con cada cambio terminado (un color elegido, un número
    escrito, agregar o quitar un color)."""

    cambiado = Signal(object)

    MAX_COLORES = 4

    def __init__(self, relleno: Optional[Relleno] = None, con_tipo: bool = True, parent=None, compacto: bool = False):
        super().__init__(parent)
        self._cargando = False
        self._relleno = relleno or Relleno("lineal", ((0, 0, 0, 255), (255, 255, 255, 255)))
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(5)
        self.muestra = MuestraRelleno(self._relleno)
        self.muestra.setFixedHeight(16 if compacto else 20)
        capa.addWidget(self.muestra)
        fila = QHBoxLayout()
        fila.setSpacing(6)
        self.combo_tipo = QComboBox()
        self.combo_tipo.addItem("Lineal", "lineal")
        self.combo_tipo.addItem("Radial", "radial")
        self.combo_tipo.setToolTip("Degradado lineal (en una dirección) o radial (desde el centro)")
        self.combo_tipo.currentIndexChanged.connect(lambda _i: self._avisar())
        self.combo_tipo.setVisible(con_tipo)
        fila.addWidget(self.combo_tipo)
        self.etiqueta_angulo = _etiqueta("Ángulo", "Dirección del degradado lineal (90°: de arriba hacia abajo)")
        self.numero_angulo = _numero(-360, 360, 0, "°", ancho=58)
        self.numero_angulo.setToolTip(self.etiqueta_angulo.toolTip())
        self.numero_angulo.valueChanged.connect(lambda _v: self._avisar())
        fila.addWidget(self.etiqueta_angulo)
        fila.addWidget(self.numero_angulo)
        fila.addStretch(1)
        self.boton_mas = QPushButton(" Color")
        self.boton_mas.setIcon(iconos.icono("plus", 14))
        self.boton_mas.setToolTip("Agregar un color (hasta 4)")
        self.boton_mas.setFocusPolicy(Qt.NoFocus)
        self.boton_mas.clicked.connect(self.agregar_color)
        fila.addWidget(self.boton_mas)
        capa.addLayout(fila)
        self.caja_paradas = QGridLayout()
        self.caja_paradas.setHorizontalSpacing(6)
        self.caja_paradas.setVerticalSpacing(4)
        capa.addLayout(self.caja_paradas)
        self.filas: list[tuple[BotonColor, QSpinBox, QToolButton, QLabel]] = []
        for i in range(self.MAX_COLORES):
            boton = BotonColor((0, 0, 0, 255), titulo="Color del degradado")
            boton.colorCambiado.connect(lambda _c: self._avisar())
            pos = QSpinBox()
            pos.setObjectName("valorControl")
            pos.setRange(0, 100)
            pos.setSuffix(" %")
            pos.setButtonSymbols(QAbstractSpinBox.NoButtons)
            pos.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            pos.setKeyboardTracking(False)
            pos.setFixedWidth(58)
            pos.setToolTip("Posición del color en el degradado (0 %: el principio, 100 %: el final)")
            pos.valueChanged.connect(lambda _v: self._avisar())
            quitar = _boton_icono("x", "Quitar este color", marcable=False)
            quitar.clicked.connect(lambda _c=False, k=i: self.quitar_color(k))
            etiqueta = _etiqueta(f"{i + 1}")
            self.caja_paradas.addWidget(etiqueta, i // 2, (i % 2) * 4)
            self.caja_paradas.addWidget(boton, i // 2, (i % 2) * 4 + 1)
            self.caja_paradas.addWidget(pos, i // 2, (i % 2) * 4 + 2)
            self.caja_paradas.addWidget(quitar, i // 2, (i % 2) * 4 + 3)
            self.filas.append((boton, pos, quitar, etiqueta))
        self.caja_paradas.setColumnStretch(8, 1)
        self.establecer(self._relleno)

    # ------------------------------------------------------------ datos
    def establecer(self, relleno: Relleno) -> None:
        """Muestra ese degradado (sin avisar). Un color liso se muestra como degradado de ese color al negro."""
        if relleno.tipo not in ("lineal", "radial"):
            c = relleno.colores[0]
            relleno = Relleno("lineal", (c, (0, 0, 0, 255)), (), relleno.angulo)
        self._relleno = relleno
        self._cargando = True
        try:
            self.combo_tipo.setCurrentIndex(max(0, self.combo_tipo.findData(relleno.tipo)))
            self.numero_angulo.setValue(relleno.angulo)
            n = min(len(relleno.colores), self.MAX_COLORES)
            paradas = relleno.paradas or tuple(i / max(1, len(relleno.colores) - 1)
                                               for i in range(len(relleno.colores)))
            for i, (boton, pos, quitar, etiqueta) in enumerate(self.filas):
                visible = i < n
                for w in (boton, pos, quitar, etiqueta):
                    w.setVisible(visible)
                if visible:
                    boton.establecer(relleno.colores[i])
                    pos.setValue(round(paradas[i] * 100))
                quitar.setEnabled(n > 2)
            self.boton_mas.setEnabled(n < self.MAX_COLORES)
            lineal = relleno.tipo == "lineal"
            self.numero_angulo.setVisible(lineal)
            self.etiqueta_angulo.setVisible(lineal)
            self.muestra.establecer(relleno)
        finally:
            self._cargando = False

    def relleno(self) -> Relleno:
        return self._relleno

    def _leer(self) -> Relleno:
        n = sum(1 for f in self.filas if not f[0].isHidden())
        pares = sorted(((self.filas[i][1].value() / 100.0, self.filas[i][0].color) for i in range(n)),
                       key=lambda par: par[0])
        return Relleno(self.combo_tipo.currentData() or "lineal", tuple(c for _s, c in pares),
                       tuple(s for s, _c in pares), float(self.numero_angulo.value()))

    def _avisar(self) -> None:
        if self._cargando:
            return
        nuevo = self._leer()
        cambio = nuevo != self._relleno
        self.establecer(nuevo)
        if cambio:
            self.cambiado.emit(nuevo)

    def agregar_color(self) -> None:
        rel = self._leer()
        if len(rel.colores) >= self.MAX_COLORES:
            return
        # En el hueco más grande, con el color del medio.
        paradas = list(rel.paradas)
        k = max(range(len(paradas) - 1), key=lambda i: paradas[i + 1] - paradas[i])
        s = (paradas[k] + paradas[k + 1]) / 2.0
        a, b = rel.colores[k], rel.colores[k + 1]
        c = tuple(round((x + y) / 2) for x, y in zip(a, b))
        colores = rel.colores[:k + 1] + (c,) + rel.colores[k + 1:]
        paradas = tuple(paradas[:k + 1]) + (s,) + tuple(paradas[k + 1:])
        nuevo = Relleno(rel.tipo, colores, paradas, rel.angulo)
        self.establecer(nuevo)
        self.cambiado.emit(nuevo)

    def quitar_color(self, indice: int) -> None:
        rel = self._leer()
        if len(rel.colores) <= 2 or indice >= len(rel.colores):
            return
        colores = rel.colores[:indice] + rel.colores[indice + 1:]
        paradas = rel.paradas[:indice] + rel.paradas[indice + 1:]
        nuevo = Relleno(rel.tipo, colores, paradas, rel.angulo)
        self.establecer(nuevo)
        self.cambiado.emit(nuevo)


class DialogoDegradado(QDialog):
    """El editor de degradado en un diálogo (para la barra de opciones de Formas)."""

    def __init__(self, relleno: Relleno, parent=None, titulo: str = "Degradado"):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(16, 14, 16, 14)
        self.editor = EditorDegradado(relleno, True)
        self.editor.setMinimumWidth(360)
        capa.addWidget(self.editor)
        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.button(QDialogButtonBox.Ok).setText("Aceptar")
        botones.button(QDialogButtonBox.Ok).setObjectName("botonPrimario")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        capa.addWidget(botones)

    def relleno(self) -> Relleno:
        return self.editor.relleno()


class BotonRelleno(QPushButton):
    """Muestra un relleno; un clic lo cambia: un color liso con el selector de color y un degradado
    con ``DialogoDegradado``. (El tipo lo elige un combo aparte.)"""

    rellenoCambiado = Signal(object)

    def __init__(self, relleno: Optional[Relleno] = None, parent=None, ancho: int = 46):
        super().__init__(parent)
        self.relleno = relleno or Relleno()
        self.setFixedSize(ancho, 24)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.clicked.connect(self._elegir)
        self._ayuda()

    def establecer(self, relleno: Relleno) -> None:
        self.relleno = relleno
        self._ayuda()
        self.update()

    def _ayuda(self) -> None:
        t = self.relleno.tipo
        self.setToolTip("Sin relleno" if t == "ninguno" else
                        "Color del relleno: clic para elegir otro" if t == "color" else
                        f"Degradado {'lineal' if t == 'lineal' else 'radial'} de {len(self.relleno.colores)} "
                        "colores: clic para cambiarlo")

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        camino = QPainterPath()
        camino.addRoundedRect(r, 5, 5)
        p.save()
        p.setClipPath(camino)
        pintar_relleno(p, r, self.relleno)
        p.restore()
        p.setPen(QPen(QColor("#6b6e78"), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 5, 5)
        if not self.isEnabled():
            p.fillRect(r, QColor(40, 40, 46, 150))
        p.end()

    def _elegir(self) -> None:
        rel = self.relleno
        if rel.tipo == "ninguno":
            return
        if rel.tipo == "color":
            c = elegir_color(self, rel.colores[0], "Color del relleno")
            if c is None:
                return
            nuevo = replace(rel, colores=(tuple(c),) + rel.colores[1:], paradas=() if len(rel.colores) == 1
                            else rel.paradas)
        else:
            dialogo = DialogoDegradado(rel, self, "Degradado del relleno")
            try:
                if dialogo.exec() != QDialog.Accepted:
                    return
                nuevo = dialogo.relleno()
            finally:
                dialogo.deleteLater()
        if nuevo != rel:
            self.establecer(nuevo)
            self.rellenoCambiado.emit(nuevo)


def relleno_de_tipo(actual: Relleno, tipo: str, frente=(0, 0, 0)) -> Relleno:
    """El relleno ``actual`` pasado a otro tipo (conserva los colores que se puedan)."""
    if tipo == actual.tipo:
        return actual
    c0 = actual.colores[0]
    if tipo in ("ninguno", "color"):
        return Relleno(tipo, (c0,), (), actual.angulo)
    if actual.tipo in ("lineal", "radial"):
        return replace(actual, tipo=tipo)
    otro = (255, 255, 255, 255) if sum(c0[:3]) < 384 else (0, 0, 0, 255)
    return Relleno(tipo, (c0, otro), (), actual.angulo)


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------

class ComboFamilias(QComboBox):
    """Las familias instaladas, con búsqueda (escribí parte del nombre). Se llena la primera vez que
    se ve (leer las fuentes tarda unas décimas)."""

    familiaElegida = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setMaxVisibleItems(18)
        self.setToolTip("Fuente: escribí parte del nombre para buscarla")
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(10)
        self._lleno = False
        self._actual = "Arial"
        self.addItem("Arial")
        self.lineEdit().editingFinished.connect(self._al_terminar)
        self.activated.connect(lambda _i: self._al_terminar())

    def llenar(self) -> None:
        if self._lleno:
            return
        self._lleno = True
        from ..motor.texto import familias_disponibles
        try:
            familias = familias_disponibles()
        except Exception:  # noqa: BLE001 - sin fuentes, queda la actual
            familias = []
        actual = self._actual
        self.blockSignals(True)
        self.clear()
        self.addItems(familias or [actual])
        completador = QCompleter(familias, self)
        completador.setCaseSensitivity(Qt.CaseInsensitive)
        completador.setFilterMode(Qt.MatchContains)
        completador.setCompletionMode(QCompleter.PopupCompletion)
        completador.activated.connect(lambda _t: self._al_terminar())
        self.setCompleter(completador)
        self.establecer(actual)
        self.blockSignals(False)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.llenar()

    def showPopup(self) -> None:
        self.llenar()
        super().showPopup()

    def establecer(self, familia: str) -> None:
        self._actual = familia
        self.blockSignals(True)
        i = self.findText(familia, Qt.MatchFixedString)
        if i < 0:
            self.addItem(familia)
            i = self.count() - 1
        self.setCurrentIndex(i)
        self.setEditText(self.itemText(i))
        self.blockSignals(False)

    def familia(self) -> str:
        return self._actual

    def _al_terminar(self) -> None:
        texto = self.currentText().strip()
        if not texto:
            self.establecer(self._actual)
            return
        i = self.findText(texto, Qt.MatchFixedString)
        if i < 0:  # lo escrito no es una familia: la primera que lo contiene
            i = next((k for k in range(self.count()) if texto.casefold() in self.itemText(k).casefold()), -1)
        if i < 0:
            self.establecer(self._actual)
            return
        familia = self.itemText(i)
        cambio = familia != self._actual
        self.establecer(familia)
        if cambio:
            self.familiaElegida.emit(familia)


class ControlesTexto(QWidget):
    """Familia, tamaño, color, negrita, cursiva, alineación, interlineado y espaciado (ver el módulo)."""

    cambio = Signal(dict)

    def __init__(self, vertical: bool = False, parent=None):
        super().__init__(parent)
        self._cargando = False
        self.combo_familia = ComboFamilias()
        self.combo_familia.familiaElegida.connect(lambda f: self._avisar({"fuente": f}))
        self.numero_tamano = _numero(1, 2000, 1, " px", ancho=66)
        self.numero_tamano.setToolTip("Tamaño de la letra, en píxeles del documento")
        self.numero_tamano.valueChanged.connect(lambda v: self._avisar({"tamano": float(v)}))
        self.boton_color = BotonColor((255, 255, 255, 255), titulo="Color del texto", ancho=34)
        self.boton_color.colorCambiado.connect(lambda c: self._avisar({"color": tuple(c)}))
        self.boton_negrita = _boton_icono("ps-negrita", "Negrita")
        self.boton_negrita.toggled.connect(lambda x: self._avisar({"negrita": bool(x)}))
        self.boton_cursiva = _boton_icono("ps-cursiva", "Cursiva")
        self.boton_cursiva.toggled.connect(lambda x: self._avisar({"cursiva": bool(x)}))
        self.grupo_alineacion = QButtonGroup(self)
        self.grupo_alineacion.setExclusive(True)
        self.botones_alineacion: dict[str, QToolButton] = {}
        for clave in ("izquierda", "centro", "derecha"):
            b = _boton_icono(ICONOS_ALINEACION[clave], NOMBRES_ALINEACION[clave])
            self.grupo_alineacion.addButton(b)
            self.botones_alineacion[clave] = b
            b.toggled.connect(lambda x, c=clave: x and self._avisar({"alineacion": c}))
        self.numero_interlineado = _numero(0.3, 5.0, 2, "", "↕ ", ancho=60, paso=0.05)
        self.numero_interlineado.setToolTip("Interlineado: distancia entre renglones, en veces el tamaño "
                                            "(1,20 es el automático)")
        self.numero_interlineado.valueChanged.connect(lambda v: self._avisar({"interlineado": float(v)}))
        self.numero_espaciado = _numero(-200, 500, 1, "", "↔ ", ancho=60)
        self.numero_espaciado.setToolTip("Espaciado entre letras, en píxeles (puede ser negativo)")
        self.numero_espaciado.valueChanged.connect(lambda v: self._avisar({"espaciado": float(v)}))

        alineacion = QWidget()
        fila_al = QHBoxLayout(alineacion)
        fila_al.setContentsMargins(0, 0, 0, 0)
        fila_al.setSpacing(0)
        for b in self.botones_alineacion.values():
            fila_al.addWidget(b)
        estilo_txt = QWidget()
        fila_es = QHBoxLayout(estilo_txt)
        fila_es.setContentsMargins(0, 0, 0, 0)
        fila_es.setSpacing(0)
        fila_es.addWidget(self.boton_negrita)
        fila_es.addWidget(self.boton_cursiva)
        if vertical:
            grilla = QGridLayout(self)
            grilla.setContentsMargins(0, 0, 0, 0)
            grilla.setHorizontalSpacing(6)
            grilla.setVerticalSpacing(5)
            grilla.addWidget(self.combo_familia, 0, 0, 1, 4)
            grilla.addWidget(self.numero_tamano, 1, 0)
            grilla.addWidget(self.boton_color, 1, 1)
            grilla.addWidget(estilo_txt, 1, 2)
            grilla.addWidget(alineacion, 1, 3, Qt.AlignRight)
            grilla.addWidget(_etiqueta("Interlineado"), 2, 0)
            grilla.addWidget(self.numero_interlineado, 2, 1)
            grilla.addWidget(_etiqueta("Espaciado"), 2, 2)
            grilla.addWidget(self.numero_espaciado, 2, 3, Qt.AlignRight)
            self.combo_familia.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        else:
            fila = QHBoxLayout(self)
            fila.setContentsMargins(0, 0, 0, 0)
            fila.setSpacing(6)
            self.combo_familia.setFixedWidth(150)
            for w in (self.combo_familia, self.numero_tamano, self.boton_color, estilo_txt, alineacion,
                      self.numero_interlineado, self.numero_espaciado):
                fila.addWidget(w)
        self.mostrar(ParamsTexto())

    def mostrar(self, p: ParamsTexto) -> None:
        """Pone esos valores (sin avisar)."""
        self._cargando = True
        try:
            self.combo_familia.establecer(p.fuente)
            self.numero_tamano.setValue(p.tamano)
            self.boton_color.establecer(p.color)
            self.boton_negrita.setChecked(p.negrita)
            self.boton_cursiva.setChecked(p.cursiva)
            self.botones_alineacion[p.alineacion].setChecked(True)
            self.numero_interlineado.setValue(p.interlineado)
            self.numero_espaciado.setValue(p.espaciado)
        finally:
            self._cargando = False

    def valores(self) -> dict:
        alineacion = next((c for c, b in self.botones_alineacion.items() if b.isChecked()), "izquierda")
        return {"fuente": self.combo_familia.familia(), "tamano": float(self.numero_tamano.value()),
                "color": tuple(self.boton_color.color), "negrita": self.boton_negrita.isChecked(),
                "cursiva": self.boton_cursiva.isChecked(), "alineacion": alineacion,
                "interlineado": float(self.numero_interlineado.value()),
                "espaciado": float(self.numero_espaciado.value())}

    def _avisar(self, cambios: dict) -> None:
        if not self._cargando:
            self.cambio.emit(cambios)


# ---------------------------------------------------------------------------
# Formas
# ---------------------------------------------------------------------------

class ControlesForma(QWidget):
    """Tipo, relleno, trazo y lo propio de cada tipo (ver el módulo). ``cambio(dict)`` con los campos de
    ``ParamsForma`` que cambiaron (``relleno`` es un ``Relleno``)."""

    cambio = Signal(dict)

    def __init__(self, vertical: bool = False, parent=None):
        super().__init__(parent)
        self._cargando = False
        self._tipo = "rectangulo"
        self.grupo_tipo = QButtonGroup(self)
        self.grupo_tipo.setExclusive(True)
        self.botones_tipo: dict[str, QToolButton] = {}
        tipos = QWidget()
        fila_t = QHBoxLayout(tipos)
        fila_t.setContentsMargins(0, 0, 0, 0)
        fila_t.setSpacing(0)
        for clave, nombre in NOMBRES_FORMA.items():
            b = _boton_icono(ICONOS_FORMA[clave], nombre)
            self.grupo_tipo.addButton(b)
            self.botones_tipo[clave] = b
            b.toggled.connect(lambda x, c=clave: x and self._al_elegir_tipo(c))
            fila_t.addWidget(b)
        self.combo_relleno = QComboBox()
        for clave, texto in TIPOS_RELLENO_FORMA:
            self.combo_relleno.addItem(texto, clave)
        self.combo_relleno.setToolTip("Relleno: ninguno, un color o un degradado (lineal o radial)")
        self.combo_relleno.setFocusPolicy(Qt.NoFocus)
        self.combo_relleno.currentIndexChanged.connect(lambda _i: self._al_cambiar_tipo_relleno())
        self.boton_relleno = BotonRelleno(Relleno("color", ((0, 0, 0, 255),)), ancho=40)
        self.boton_relleno.rellenoCambiado.connect(lambda r: self._avisar({"relleno": r}))
        self.boton_trazo = BotonColor((0, 0, 0, 255), titulo="Color del trazo", ancho=34)
        self.boton_trazo.setToolTip("Color del trazo (el borde)")
        self.boton_trazo.colorCambiado.connect(lambda c: self._avisar({"trazo": tuple(c)}))
        self.numero_grosor = _numero(0, 500, 1, " px", ancho=58)
        self.numero_grosor.setToolTip("Grosor del trazo (0: sin trazo)")
        self.numero_grosor.valueChanged.connect(lambda v: self._avisar({"grosor": float(v)}))
        self.etiqueta_extra = _etiqueta("Radio")
        self.numero_radio = _numero(0, 5000, 0, " px", ancho=62)
        self.numero_radio.setToolTip("Radio de las esquinas del rectángulo")
        self.numero_radio.valueChanged.connect(lambda v: self._avisar({"radio": float(v)}))
        self.numero_lados = QSpinBox()
        self.numero_puntas = QSpinBox()
        for n, campo, ayuda in ((self.numero_lados, "lados", "Lados del polígono"),
                                (self.numero_puntas, "puntas", "Puntas de la estrella")):
            n.setObjectName("valorControl")
            n.setRange(3, 64)
            n.setButtonSymbols(QAbstractSpinBox.NoButtons)
            n.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            n.setKeyboardTracking(False)
            n.setFixedWidth(48)
            n.setToolTip(ayuda)
            n.valueChanged.connect(lambda v, c=campo: self._avisar({c: int(v)}))
        self.numero_alto = _numero(1, 5000, 0, " px", ancho=62)
        self.numero_alto.setToolTip("Grosor de la línea (o alto de la flecha)")
        self.numero_alto.valueChanged.connect(lambda v: self._avisar({"alto": float(v)}))

        etiqueta_relleno = _etiqueta("Relleno")
        etiqueta_trazo = _etiqueta("Trazo")
        extras = QWidget()
        fila_x = QHBoxLayout(extras)
        fila_x.setContentsMargins(0, 0, 0, 0)
        fila_x.setSpacing(6)
        fila_x.addWidget(self.etiqueta_extra)
        for w in (self.numero_radio, self.numero_lados, self.numero_puntas, self.numero_alto):
            fila_x.addWidget(w)
        if vertical:
            grilla = QGridLayout(self)
            grilla.setContentsMargins(0, 0, 0, 0)
            grilla.setHorizontalSpacing(6)
            grilla.setVerticalSpacing(5)
            grilla.addWidget(tipos, 0, 0, 1, 4)
            grilla.addWidget(etiqueta_relleno, 1, 0)
            grilla.addWidget(self.combo_relleno, 1, 1)
            grilla.addWidget(self.boton_relleno, 1, 2)
            grilla.addWidget(etiqueta_trazo, 2, 0)
            grilla.addWidget(self.boton_trazo, 2, 1, Qt.AlignLeft)
            grilla.addWidget(self.numero_grosor, 2, 2)
            grilla.addWidget(extras, 3, 0, 1, 4, Qt.AlignLeft)
            grilla.setColumnStretch(3, 1)
        else:
            # En la barra de opciones (angosta a 1366 px): sin las etiquetas (lo dicen las ayudas).
            fila = QHBoxLayout(self)
            fila.setContentsMargins(0, 0, 0, 0)
            fila.setSpacing(5)
            for b in self.botones_tipo.values():
                b.setFixedSize(25, 26)
            self.combo_relleno.setFixedWidth(92)
            for w in (tipos, self.combo_relleno, self.boton_relleno, self.boton_trazo, self.numero_grosor, extras):
                fila.addWidget(w)
            etiqueta_relleno.hide()
            etiqueta_trazo.hide()
            self.boton_trazo.setToolTip("Color del trazo (el borde); el grosor, al lado")
        self.mostrar(ParamsForma(relleno=Relleno("color", ((0, 0, 0, 255),))))

    @property
    def tipo(self) -> str:
        return self._tipo

    def mostrar(self, p: ParamsForma) -> None:
        """Pone esos valores (sin avisar)."""
        self._cargando = True
        try:
            self._tipo = p.tipo
            self.botones_tipo[p.tipo].setChecked(True)
            self.combo_relleno.setCurrentIndex(max(0, self.combo_relleno.findData(p.relleno.tipo)))
            self.boton_relleno.establecer(p.relleno)
            self.boton_relleno.setEnabled(p.relleno.tipo != "ninguno")
            self.boton_trazo.establecer(p.trazo)
            self.numero_grosor.setValue(p.grosor)
            self.numero_radio.setValue(p.radio)
            self.numero_lados.setValue(p.lados)
            self.numero_puntas.setValue(p.puntas)
            self.numero_alto.setValue(p.alto)
            self._mostrar_extras()
        finally:
            self._cargando = False

    def _mostrar_extras(self) -> None:
        t = self._tipo
        self.numero_radio.setVisible(t == "rectangulo")
        self.numero_lados.setVisible(t == "poligono")
        self.numero_puntas.setVisible(t == "estrella")
        self.numero_alto.setVisible(t in ("linea", "flecha"))
        self.etiqueta_extra.setText({"rectangulo": "Radio", "poligono": "Lados", "estrella": "Puntas",
                                     "linea": "Grosor", "flecha": "Alto"}.get(t, ""))
        self.etiqueta_extra.setVisible(t != "elipse")
        self.numero_alto.setToolTip("Grosor de la línea" if t == "linea" else "Alto de la flecha (el de la punta)")

    def establecer_tipo(self, tipo: str) -> None:
        """Elige el tipo (como el botón): avisa."""
        self.botones_tipo[tipo].setChecked(True)

    def _al_elegir_tipo(self, tipo: str) -> None:
        self._tipo = tipo
        self._mostrar_extras()
        self._avisar({"tipo": tipo})

    def _al_cambiar_tipo_relleno(self) -> None:
        if self._cargando:
            return
        nuevo = relleno_de_tipo(self.boton_relleno.relleno, self.combo_relleno.currentData())
        self.boton_relleno.establecer(nuevo)
        self.boton_relleno.setEnabled(nuevo.tipo != "ninguno")
        self._avisar({"relleno": nuevo})

    def valores(self) -> dict:
        return {"tipo": self._tipo, "relleno": self.boton_relleno.relleno, "trazo": tuple(self.boton_trazo.color),
                "grosor": float(self.numero_grosor.value()), "radio": float(self.numero_radio.value()),
                "lados": int(self.numero_lados.value()), "puntas": int(self.numero_puntas.value())}

    def _avisar(self, cambios: dict) -> None:
        if not self._cargando:
            self.cambio.emit(cambios)


__all__ = ["BotonRelleno", "ControlesForma", "ControlesTexto", "DialogoDegradado", "EditorDegradado",
           "ICONOS_FORMA", "MuestraRelleno", "NOMBRES_FORMA", "pintar_relleno", "relleno_de_tipo"]
