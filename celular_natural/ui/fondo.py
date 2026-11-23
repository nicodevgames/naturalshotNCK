"""Fondo: marcar un objeto (lazo poligonal o pincel) y elegir qué hacer con lo de afuera:
dejarlo transparente (PNG) o desenfocarlo como el modo retrato de un celular.

"Ajustar al contorno" toma esa selección aproximada (o un rectángulo alrededor
del objeto) y la pega al borde real con ``seleccion_auto.recortar_objeto``."""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ..motor.desenfoque import INTENSIDAD_INICIAL, TRANSICION_INICIAL
from ..motor.zonas import Zona
from . import iconos
from .controles import ControlDeslizante, SeccionPlegable

TRANSPARENTE = "transparente"
DESENFOCADO = "desenfocado"
# Estado del historial: (zona, recortar, modo, intensidad, transición, profundidad).
# Los estados viejos de dos elementos (zona, recortar) se completan con estos valores.
FONDO_INICIAL = (None, True, TRANSPARENTE, INTENSIDAD_INICIAL, TRANSICION_INICIAL, False)


def completar_estado(estado) -> tuple:
    """Lleva un estado de fondo (de cualquier versión) a la forma completa."""
    estado = tuple(estado) if estado else ()
    return estado[:len(FONDO_INICIAL)] + FONDO_INICIAL[len(estado):]


class PanelFondo(QWidget):
    """Tiene la misma interfaz de zona que una capa (nombre, zona, pluma, invertir...)."""

    cambiado = Signal()
    pedirZona = Signal(object, str)
    pedirAjuste = Signal()  # "Ajustar al contorno": la ventana lo calcula en segundo plano

    numero = 0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zona: Optional[Zona] = None
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        self.tarjeta = SeccionPlegable("Fondo", "focus", "Marcá un objeto y elegí qué hacer con lo de afuera: "
                                       "dejarlo transparente o desenfocarlo (modo retrato)",
                                       True, con_interruptor=False, plegable=False)
        capa.addWidget(self.tarjeta)
        cuerpo = self.tarjeta.capa_cuerpo

        # Qué se hace con lo de afuera del objeto: dos opciones lado a lado.
        selector = QFrame()
        selector.setObjectName("selectorFormato")
        fila_modo = QHBoxLayout(selector)
        fila_modo.setContentsMargins(3, 3, 3, 3)
        fila_modo.setSpacing(3)
        self.grupo_modo = QButtonGroup(self)
        self.grupo_modo.setExclusive(True)
        self.botones_modo = {}
        for modo, texto, icono, ayuda in (
            (TRANSPARENTE, "Transparente\nPNG sin fondo", "scissors",
             "Lo de afuera del objeto queda transparente. Se exporta en PNG."),
            (DESENFOCADO, "Desenfocado\nModo retrato", "aperture",
             "El objeto queda nítido y el fondo se desenfoca como con un lente luminoso. "
             "Se exporta en el formato elegido."),
        ):
            b = QPushButton(texto)
            b.setObjectName("opcionFormato")
            b.setCheckable(True)
            b.setChecked(modo == TRANSPARENTE)
            b.setProperty("modo", modo)
            b.setIcon(iconos.icono(icono, 20))
            b.setIconSize(QSize(20, 20))
            b.setToolTip(ayuda)
            b.setCursor(Qt.PointingHandCursor)
            self.grupo_modo.addButton(b)
            self.botones_modo[modo] = b
            fila_modo.addWidget(b, 1)
        self.grupo_modo.buttonClicked.connect(lambda _b: self._al_cambiar_modo())
        cuerpo.addWidget(selector)

        self.estado = QLabel()
        self.estado.setObjectName("nota")
        self.estado.setWordWrap(True)
        cuerpo.addWidget(self.estado)

        fila = QHBoxLayout()
        fila.setSpacing(6)
        self.boton_marcar = QPushButton(" Marcar objeto")
        self.boton_marcar.setIcon(iconos.icono("pentagon", 16))
        self.boton_marcar.setToolTip("Clic punto por punto alrededor del objeto. Cerrá con doble clic, Enter o "
                                     "tocando el primer punto. Retroceso borra el último punto.")
        self.boton_marcar.clicked.connect(lambda: self.pedirZona.emit(self, "poligono"))
        self.boton_pintar = QPushButton(" Pintar objeto")
        self.boton_pintar.setIcon(iconos.icono("brush", 16))
        self.boton_pintar.setToolTip("Pintá el objeto a mano con el pincel. Clic derecho o la goma borran lo "
                                     "pintado de más; Enter o Listo terminan. Si ya lo pintaste, seguís encima.")
        self.boton_pintar.clicked.connect(lambda: self.pedirZona.emit(self, "pincel"))
        self.boton_quitar = QPushButton()
        self.boton_quitar.setIcon(iconos.icono("trash-2", 16))
        self.boton_quitar.setFixedWidth(36)
        self.boton_quitar.setToolTip("Olvidar el objeto: la foto vuelve a quedar completa, sin cambios en el fondo")
        self.boton_quitar.clicked.connect(lambda: self.establecer_zona(None))
        fila.addWidget(self.boton_marcar, 1)
        fila.addWidget(self.boton_pintar, 1)
        fila.addWidget(self.boton_quitar)
        cuerpo.addLayout(fila)

        self.boton_ajustar = QPushButton(" Ajustar al contorno")
        self.boton_ajustar.setIcon(iconos.icono("wand-sparkles", 16))
        self.boton_ajustar.setToolTip(
            "Pega tu selección al borde real del objeto, sola. Partí de un lazo o de lo pintado (aunque sea "
            "aproximado); si todavía no marcaste nada, arrastrá un rectángulo alrededor del objeto. "
            "Después podés corregirla con el pincel.")
        self.boton_ajustar.clicked.connect(self.pedirAjuste)
        cuerpo.addWidget(self.boton_ajustar)

        self.opciones = QWidget()
        op = QVBoxLayout(self.opciones)
        op.setContentsMargins(0, 0, 0, 0)
        op.setSpacing(4)
        self.pluma = ControlDeslizante("pluma", "Suavizado del borde", 0, 30,
                                       "Unos pocos píxeles de borde suave evitan el serrucho entre el objeto y el fondo.")
        self.pluma.establecer(3, 3)
        self.pluma.valorCambiado.connect(lambda *_: self._actualizar())
        self.check_invertir = QCheckBox()
        self.check_invertir.toggled.connect(lambda _v: self._actualizar())
        op.addWidget(self.pluma)
        op.addWidget(self.check_invertir)

        # Solo en Transparente
        self.check_recortar = QCheckBox("Recortar al tamaño del objeto al exportar")
        self.check_recortar.setChecked(True)
        self.check_recortar.toggled.connect(lambda _v: self.cambiado.emit())
        op.addWidget(self.check_recortar)

        # Solo en Desenfocado
        self.opciones_desenfoque = QWidget()
        od = QVBoxLayout(self.opciones_desenfoque)
        od.setContentsMargins(0, 0, 0, 0)
        od.setSpacing(4)
        self.intensidad = ControlDeslizante(
            "intensidad", "Intensidad del desenfoque", 0, 100,
            "Tamaño del desenfoque, como abrir más o menos el diafragma. Es relativo al tamaño de la foto: "
            "se ve igual en la vista previa y al exportar.")
        self.intensidad.establecer(INTENSIDAD_INICIAL, INTENSIDAD_INICIAL)
        self.intensidad.valorCambiado.connect(lambda *_: self.cambiado.emit())
        self.transicion = ControlDeslizante(
            "transicion", "Transición nítido → borroso", 0, 100,
            "Qué tan gradual es el paso del objeto nítido al fondo borroso. En 0 el fondo está desenfocado "
            "desde el mismo borde; más alto, lo pegado al objeto (por ejemplo, el piso bajo los pies) se "
            "desenfoca de a poco.")
        self.transicion.establecer(TRANSICION_INICIAL, TRANSICION_INICIAL)
        self.transicion.valorCambiado.connect(lambda *_: self.cambiado.emit())
        self.check_profundidad = QCheckBox("Profundidad gradual (más borroso lejos del objeto)")
        self.check_profundidad.setToolTip("Simula que el fondo se aleja: cerca del objeto se desenfoca menos y "
                                          "cuanto más lejos, más.")
        self.check_profundidad.toggled.connect(lambda _v: self.cambiado.emit())
        for w in (self.intensidad, self.transicion, self.check_profundidad):
            od.addWidget(w)
        op.addWidget(self.opciones_desenfoque)
        cuerpo.addWidget(self.opciones)
        self._refrescar()

    @property
    def nombre(self) -> str:
        return "Objeto"

    def modo(self) -> str:
        boton = self.grupo_modo.checkedButton()
        return boton.property("modo") if boton is not None else TRANSPARENTE

    def _refrescar(self) -> None:
        tiene = self.zona is not None
        pintado = tiene and self.zona.es_raster  # pintado o ajustado al contorno
        ajustado = tiene and self.zona.es_mascara
        desenfocado = self.modo() == DESENFOCADO
        self.opciones.setVisible(tiene)
        self.boton_quitar.setVisible(tiene)
        # El borde de lo pintado lo da la dureza del pincel (y el de lo ajustado, la propia foto).
        self.pluma.setVisible(not pintado)
        self.check_recortar.setVisible(not desenfocado)
        self.opciones_desenfoque.setVisible(desenfocado)
        self.check_invertir.setText("Invertir (desenfocar el objeto y dejar nítido el fondo)" if desenfocado else
                                    "Invertir (borrar el objeto y dejar el fondo)")
        self.boton_marcar.setText(" Volver a marcar" if tiene and not pintado else " Marcar objeto")
        self.boton_pintar.setText(" Seguir pintando" if pintado else " Pintar objeto")
        self.boton_pintar.setToolTip(
            "Corregí el contorno ajustado con el pincel: pintá para sumar y usá la goma o el clic derecho "
            "para restar." if ajustado else
            "Pintá el objeto a mano con el pincel. Clic derecho o la goma borran lo pintado de más; Enter o "
            "Listo terminan. Si ya lo pintaste, seguís encima.")
        self.boton_ajustar.setText(" Ajustar de nuevo" if ajustado else " Ajustar al contorno")
        objeto = "Objeto ajustado al contorno" if ajustado else "Objeto pintado" if pintado else "Objeto marcado"
        if desenfocado:
            self.estado.setText(
                f"{objeto}: queda nítido y el fondo, desenfocado. Se exporta en el formato elegido." if tiene else
                "Marcá el contorno del objeto (por ejemplo, una persona) con el lazo poligonal, o pintalo con el "
                "pincel: queda nítido y el fondo se desenfoca, como el modo retrato de un celular.")
        else:
            self.estado.setText(
                f"{objeto}: se exporta en PNG con fondo transparente." if tiene else
                "Marcá el contorno del objeto (por ejemplo, tu auto) con el lazo poligonal, o pintalo con el "
                "pincel: todo lo de afuera queda transparente.")

    def _al_cambiar_modo(self) -> None:
        self._refrescar()
        self.cambiado.emit()

    def _actualizar(self) -> None:
        if self.zona is None:
            return
        self.zona = replace(self.zona, pluma=self.pluma.valor(), invertir=self.check_invertir.isChecked())
        self.cambiado.emit()

    def establecer_zona(self, zona: Optional[Zona], emitir: bool = True) -> None:
        self.zona = zona
        if zona is not None:
            self.check_invertir.blockSignals(True)
            self.check_invertir.setChecked(zona.invertir)
            self.check_invertir.blockSignals(False)
            self.pluma.establecer(zona.pluma, 3)
        self._refrescar()
        if emitir:
            self.cambiado.emit()

    def zona_cancelada(self) -> None:
        self._refrescar()

    def establecer_detectando(self, activo: bool) -> None:
        """Mientras se ajusta al contorno, el botón avisa y no se puede volver a tocar."""
        self.boton_ajustar.setEnabled(not activo)
        if activo:
            self.boton_ajustar.setText(" Ajustando…")
        else:
            self._refrescar()

    # ------------------------------------------------------------ para la ventana
    def zona_transparente(self) -> Optional[Zona]:
        """La zona del objeto si lo de afuera queda transparente; si no, None."""
        return self.zona if self.modo() == TRANSPARENTE else None

    def desenfoque(self) -> Optional[tuple]:
        """(zona, intensidad, transición, profundidad) si se desenfoca el fondo; si no, None."""
        if self.zona is None or self.modo() != DESENFOCADO or self.intensidad.valor() <= 0:
            return None
        return self.zona, self.intensidad.valor(), self.transicion.valor(), self.check_profundidad.isChecked()

    def estado_fondo(self) -> tuple:
        return (self.zona, self.check_recortar.isChecked(), self.modo(), self.intensidad.valor(),
                self.transicion.valor(), self.check_profundidad.isChecked())

    def restaurar(self, estado) -> None:
        zona, recortar, modo, intensidad, transicion, profundidad = completar_estado(estado)
        for w in (self.check_recortar, self.check_profundidad):
            w.blockSignals(True)
        self.check_recortar.setChecked(recortar)
        self.check_profundidad.setChecked(profundidad)
        for w in (self.check_recortar, self.check_profundidad):
            w.blockSignals(False)
        self.botones_modo.get(modo, self.botones_modo[TRANSPARENTE]).setChecked(True)
        self.intensidad.establecer(intensidad, INTENSIDAD_INICIAL)
        self.transicion.establecer(transicion, TRANSICION_INICIAL)
        self.establecer_zona(zona, emitir=False)
