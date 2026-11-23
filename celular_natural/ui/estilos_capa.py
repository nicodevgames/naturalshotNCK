"""Diálogo "Estilo de capa" del modo Photoshop (NaturalShot Lite, Etapa 2, U2), como el de Photoshop.

A la izquierda, la lista de estilos, cada uno con su tilde (prendido o apagado): **Sombra paralela**,
**Trazo**, **Resplandor exterior**, **Superposición de color** y **Superposición de degradado**. A la
derecha, los parámetros del elegido. Tocar un parámetro de un estilo apagado lo prende (como
Photoshop). Apagar un estilo no pierde sus valores (``activo`` en ``motor.estilos``).

El diálogo no cambia el documento: avisa cada cambio (``vistaPrevia(EstilosCapa)``) para que la
ventana lo muestre sobre el lienzo, y al final ``estilos()`` es lo elegido. Quien lo abre decide:
Aceptar es **un** paso del historial y Cancelar vuelve a como estaba.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QSlider, QStackedWidget, QVBoxLayout, QWidget,
)

from ..motor.estilos import (
    EFECTOS, EstilosCapa, Resplandor, Sombra, SuperposicionColor, SuperposicionDegradado, Trazo,
)
from ..motor.formas import Relleno
from . import estilo
from .opciones_ps import EditorDegradado
from .selector_color import BotonColor

NOMBRES_ESTILO = {"sombra": "Sombra paralela", "trazo": "Trazo", "resplandor": "Resplandor exterior",
                  "color": "Superposición de color", "degradado": "Superposición de degradado"}
POSICIONES = (("afuera", "Afuera"), ("adentro", "Adentro"), ("centro", "Centro"))
_POR_DEFECTO = {"sombra": Sombra(), "trazo": Trazo(), "resplandor": Resplandor(), "color": SuperposicionColor(),
                "degradado": SuperposicionDegradado(Relleno("lineal", ((0, 0, 0, 255), (255, 255, 255, 255))))}


class Deslizador(QWidget):
    """Un deslizador con su número al lado (el número admite más que el deslizador)."""

    cambiado = Signal(float)

    def __init__(self, minimo: float, maximo: float, sufijo: str = "", decimales: int = 0, maximo_numero=None,
                 parent=None):
        super().__init__(parent)
        self._factor = 10 ** decimales
        fila = QHBoxLayout(self)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(8)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(int(minimo * self._factor), int(maximo * self._factor))
        self.slider.setFocusPolicy(Qt.NoFocus)
        self.numero = QDoubleSpinBox()
        self.numero.setObjectName("valorControl")
        self.numero.setRange(minimo, maximo if maximo_numero is None else maximo_numero)
        self.numero.setDecimals(decimales)
        self.numero.setSuffix(sufijo)
        self.numero.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.numero.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.numero.setKeyboardTracking(False)
        self.numero.setFixedWidth(72)
        fila.addWidget(self.slider, 1)
        fila.addWidget(self.numero)
        self.slider.valueChanged.connect(self._desde_slider)
        self.numero.valueChanged.connect(self._desde_numero)

    def valor(self) -> float:
        return float(self.numero.value())

    def establecer(self, valor: float) -> None:
        for w in (self.slider, self.numero):
            w.blockSignals(True)
        self.numero.setValue(float(valor))
        self.slider.setValue(int(round(min(self.slider.maximum() / self._factor, float(valor)) * self._factor)))
        for w in (self.slider, self.numero):
            w.blockSignals(False)

    def _desde_slider(self, v: int) -> None:
        self.numero.blockSignals(True)
        self.numero.setValue(v / self._factor)
        self.numero.blockSignals(False)
        self.cambiado.emit(v / self._factor)

    def _desde_numero(self, v: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(min(self.slider.maximum() / self._factor, v) * self._factor)))
        self.slider.blockSignals(False)
        self.cambiado.emit(float(v))


class DialogoEstilos(QDialog):
    """El diálogo (ver el módulo). ``estilos``: los de la capa al abrir."""

    vistaPrevia = Signal(object)  # EstilosCapa

    def __init__(self, estilos: EstilosCapa, nombre_capa: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Estilo de capa: «{nombre_capa}»" if nombre_capa else "Estilo de capa")
        self.setObjectName("dialogoEstilos")
        self.setMinimumSize(600, 380)
        self._original = estilos
        self._efectos = {n: getattr(estilos, n) for n in EFECTOS}  # None, o el efecto (prendido o no)
        self._cargando = False

        capa = QVBoxLayout(self)
        capa.setContentsMargins(16, 14, 16, 14)
        capa.setSpacing(10)
        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(12)
        self.lista = QListWidget()
        self.lista.setObjectName("listaEstilos")
        self.lista.setFixedWidth(218)
        self.lista.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lista.setTextElideMode(Qt.ElideRight)
        self.lista.setStyleSheet(
            f"QListWidget#listaEstilos {{ background: {estilo.TARJETA}; border: 1px solid {estilo.BORDE}; "
            "border-radius: 8px; padding: 4px; }"
            "QListWidget#listaEstilos::item { padding: 6px 4px; border-radius: 6px; }"
            f"QListWidget#listaEstilos::item:selected {{ background: {estilo.SELECCION}; color: {estilo.TEXTO}; }}")
        for n in EFECTOS:
            item = QListWidgetItem(NOMBRES_ESTILO[n])
            item.setData(Qt.UserRole, n)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            e = self._efectos[n]
            item.setCheckState(Qt.Checked if e is not None and e.activo else Qt.Unchecked)
            self.lista.addItem(item)
        self.lista.itemChanged.connect(self._al_tildar)
        self.lista.currentRowChanged.connect(lambda i: self.paginas.setCurrentIndex(max(0, i)))
        cuerpo.addWidget(self.lista)
        self.paginas = QStackedWidget()
        cuerpo.addWidget(self.paginas, 1)
        capa.addLayout(cuerpo, 1)

        self.controles: dict[str, dict] = {}
        self._pagina_sombra()
        self._pagina_trazo()
        self._pagina_resplandor()
        self._pagina_color()
        self._pagina_degradado()

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.button(QDialogButtonBox.Ok).setText("Aceptar")
        botones.button(QDialogButtonBox.Ok).setObjectName("botonPrimario")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        capa.addWidget(botones)
        primero = next((i for i, n in enumerate(EFECTOS) if self._efectos[n] is not None), 0)
        self.lista.setCurrentRow(primero)

    # ------------------------------------------------------------ páginas
    def _pagina(self, clave: str) -> QFormLayout:
        w = QWidget()
        caja = QVBoxLayout(w)
        caja.setContentsMargins(0, 0, 0, 0)
        titulo = QLabel(NOMBRES_ESTILO[clave])
        titulo.setObjectName("tituloDialogo")
        titulo.setStyleSheet("font-weight: 700; font-size: 11pt;")
        caja.addWidget(titulo)
        forma = QFormLayout()
        forma.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        forma.setHorizontalSpacing(10)
        forma.setVerticalSpacing(8)
        caja.addLayout(forma)
        caja.addStretch(1)
        self.paginas.addWidget(w)
        self.controles[clave] = {}
        return forma

    def _color(self, forma: QFormLayout, clave: str, campo: str, texto: str = "Color") -> None:
        e = self._efecto_o_defecto(clave)
        b = BotonColor(getattr(e, campo), titulo=f"{NOMBRES_ESTILO[clave]}: {texto.lower()}", ancho=56)
        b.colorCambiado.connect(lambda c, k=clave, f=campo: self._cambiar(k, **{f: tuple(c)}))
        forma.addRow(texto, b)
        self.controles[clave][campo] = b

    def _deslizador(self, forma: QFormLayout, clave: str, campo: str, texto: str, minimo, maximo, sufijo="",
                    factor: float = 1.0, maximo_numero=None) -> None:
        e = self._efecto_o_defecto(clave)
        d = Deslizador(minimo, maximo, sufijo, maximo_numero=maximo_numero)
        d.establecer(getattr(e, campo) * factor)
        d.cambiado.connect(lambda v, k=clave, f=campo, fa=factor: self._cambiar(k, **{f: v / fa}))
        forma.addRow(texto, d)
        self.controles[clave][campo] = d

    def _pagina_sombra(self) -> None:
        f = self._pagina("sombra")
        self._color(f, "sombra", "color")
        self._deslizador(f, "sombra", "opacidad", "Opacidad", 0, 100, " %", 100.0)
        self._deslizador(f, "sombra", "angulo", "Ángulo", 0, 359, "°")
        self._deslizador(f, "sombra", "distancia", "Distancia", 0, 200, " px", maximo_numero=2000)
        self._deslizador(f, "sombra", "tamano", "Tamaño", 0, 200, " px", maximo_numero=2000)

    def _pagina_trazo(self) -> None:
        f = self._pagina("trazo")
        self._color(f, "trazo", "color")
        self._deslizador(f, "trazo", "grosor", "Grosor", 0, 100, " px", maximo_numero=2000)
        combo = QComboBox()
        for clave, texto in POSICIONES:
            combo.addItem(texto, clave)
        combo.setCurrentIndex(max(0, combo.findData(self._efecto_o_defecto("trazo").posicion)))
        combo.currentIndexChanged.connect(lambda _i: self._cambiar("trazo", posicion=combo.currentData()))
        f.addRow("Posición", combo)
        self.controles["trazo"]["posicion"] = combo
        self._deslizador(f, "trazo", "opacidad", "Opacidad", 0, 100, " %", 100.0)

    def _pagina_resplandor(self) -> None:
        f = self._pagina("resplandor")
        self._color(f, "resplandor", "color")
        self._deslizador(f, "resplandor", "opacidad", "Opacidad", 0, 100, " %", 100.0)
        self._deslizador(f, "resplandor", "tamano", "Tamaño", 0, 200, " px", maximo_numero=2000)

    def _pagina_color(self) -> None:
        f = self._pagina("color")
        self._color(f, "color", "color")
        self._deslizador(f, "color", "opacidad", "Opacidad", 0, 100, " %", 100.0)

    def _pagina_degradado(self) -> None:
        f = self._pagina("degradado")
        e = self._efecto_o_defecto("degradado")
        editor = EditorDegradado(e.relleno_efectivo(), True)
        editor.cambiado.connect(lambda r: self._cambiar("degradado", relleno=r))
        f.addRow(editor)  # a lo ancho (los colores con su posición no entran al lado de una etiqueta)
        self.controles["degradado"]["relleno"] = editor
        self._deslizador(f, "degradado", "opacidad", "Opacidad", 0, 100, " %", 100.0)

    # ------------------------------------------------------------ datos
    def _efecto_o_defecto(self, clave: str):
        e = self._efectos[clave]
        return e if e is not None else _POR_DEFECTO[clave]

    def estilos(self) -> EstilosCapa:
        """Los estilos elegidos (los que nunca se prendieron quedan en None)."""
        return EstilosCapa(**self._efectos)

    def _item(self, clave: str) -> QListWidgetItem:
        return self.lista.item(EFECTOS.index(clave))

    def elegir(self, clave: str) -> None:
        """Muestra los parámetros de ese estilo (como un clic en la lista)."""
        self.lista.setCurrentRow(EFECTOS.index(clave))

    def prender(self, clave: str, activo: bool = True) -> None:
        """Prende o apaga ese estilo (como su tilde)."""
        self._item(clave).setCheckState(Qt.Checked if activo else Qt.Unchecked)

    def _al_tildar(self, item: QListWidgetItem) -> None:
        if self._cargando:
            return
        clave = item.data(Qt.UserRole)
        activo = item.checkState() == Qt.Checked
        e = self._efecto_o_defecto(clave)
        if e.activo != activo or self._efectos[clave] is None:
            self._efectos[clave] = replace(e, activo=activo)
            if not activo and getattr(self._original, clave) is None and self._efectos[clave] == replace(
                    _POR_DEFECTO[clave], activo=False):
                self._efectos[clave] = None  # se prendió y se apagó sin tocar nada: como si no estuviera
            self.vistaPrevia.emit(self.estilos())

    def _cambiar(self, clave: str, **cambios) -> None:
        """Un parámetro cambió: el estilo queda prendido (si estaba apagado, se prende)."""
        e = self._efecto_o_defecto(clave)
        try:
            nuevo = replace(e, activo=True, **cambios)
        except (TypeError, ValueError):
            return
        self._efectos[clave] = nuevo
        item = self._item(clave)
        if item.checkState() != Qt.Checked:
            self._cargando = True
            item.setCheckState(Qt.Checked)
            self._cargando = False
        self.vistaPrevia.emit(self.estilos())

    def establecer(self, clave: str, **cambios) -> None:
        """Para el teclado o las pruebas: cambia parámetros de un estilo y los muestra en sus controles."""
        self._cambiar(clave, **cambios)
        e = self._efectos[clave]
        for campo, control in self.controles[clave].items():
            valor = getattr(e, campo)
            if isinstance(control, BotonColor):
                control.establecer(valor)
            elif isinstance(control, Deslizador):
                control.establecer(valor * (100.0 if campo == "opacidad" else 1.0))
            elif isinstance(control, QComboBox):
                control.blockSignals(True)
                control.setCurrentIndex(max(0, control.findData(valor)))
                control.blockSignals(False)
            elif isinstance(control, EditorDegradado):
                control.establecer(e.relleno_efectivo())


__all__ = ["DialogoEstilos", "NOMBRES_ESTILO"]
