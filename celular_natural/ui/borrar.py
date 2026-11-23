"""Tarjeta "Borrar objetos": quitar cosas de la foto rellenando con lo de alrededor o
clonando otra parte.

Se marca lo que hay que borrar con el pincel (lo más común), el lazo o un
rectángulo. Cada zona queda como una fila con su modo:

* **Rellenar automático** (``borrado.rellenar``): completa el hueco con parches
  del entorno; sirve para cielo, pasto, pared, arena, agua...
* **Clonar desde…** (``borrado.clonar``): copia otra parte de la foto que vos
  elegís arrastrando desde la zona hasta la fuente, con vista previa.

El borrado va antes del filtro (como el montaje) y se calcula sobre la foto
completa: el ruido y el grano quedan parejos encima y la exportación coincide
con la vista. Cada cambio queda en el historial.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ..motor.edicion import ZonaBorrado
from ..motor.marca_agua import (NOMBRES_POSICION, POSICIONES, borrado_de_marca,
                                caja_de_preset, detectar_marca)
from ..motor.zonas import Zona
from . import iconos
from .controles import SeccionPlegable

RELLENAR = "rellenar"
CLONAR = "clonar"
MAX_BORRADOS = 12
NOMBRES_MODO = {RELLENAR: "Rellenar automático", CLONAR: "Clonar desde…"}
ICONOS_MODO = {RELLENAR: "wand-sparkles", CLONAR: "stamp"}
DESCRIPCION_FORMA = {"pincel": "pintado", "poligono": "con lazo", "lazo": "con lazo", "rect": "rectángulo",
                     "elipse": "elipse", "mascara": "ajustado"}


class FilaBorrado(QFrame):
    """Una zona borrada. Tiene la misma interfaz de zona que una capa (nombre, zona...)."""

    cambiada = Signal()
    eliminar = Signal(object)
    pedirZona = Signal(object, str)
    pedirFuente = Signal(object)

    def __init__(self, numero: int, borrado: ZonaBorrado, parent=None):
        super().__init__(parent)
        self.setObjectName("filaCapa")
        self.numero = numero
        self._borrado = borrado
        capa = QVBoxLayout(self)
        capa.setContentsMargins(10, 8, 8, 10)
        capa.setSpacing(6)

        arriba = QHBoxLayout()
        arriba.setSpacing(8)
        self.icono = QLabel()
        self.icono.setFixedSize(18, 18)
        self.etiqueta = QLabel()
        self.etiqueta.setObjectName("etiquetaCapa")
        boton_quitar = QPushButton()
        boton_quitar.setIcon(iconos.icono("x", 16))
        boton_quitar.setObjectName("botonQuitar")
        boton_quitar.setFixedSize(24, 24)
        boton_quitar.setToolTip("Quitar este borrado: lo que estaba vuelve a aparecer")
        boton_quitar.clicked.connect(lambda: self.eliminar.emit(self))
        arriba.addWidget(self.icono)
        arriba.addWidget(self.etiqueta, 1)
        arriba.addWidget(boton_quitar)
        capa.addLayout(arriba)

        fila = QHBoxLayout()
        fila.setSpacing(6)
        self.combo_modo = QComboBox()
        for modo in (RELLENAR, CLONAR):
            self.combo_modo.addItem(iconos.icono(ICONOS_MODO[modo], 16), NOMBRES_MODO[modo], modo)
        self.combo_modo.setItemData(0, "Completa la zona con lo de alrededor (cielo, pasto, pared...)", Qt.ToolTipRole)
        self.combo_modo.setItemData(1, "Copia otra parte de la foto que elegís vos", Qt.ToolTipRole)
        self.combo_modo.currentIndexChanged.connect(self._al_cambiar_modo)
        self.boton_fuente = QPushButton()
        self.boton_fuente.setIcon(iconos.icono("stamp", 16))
        self.boton_fuente.setFixedWidth(34)
        self.boton_fuente.setToolTip("Elegir de dónde se copia: arrastrá desde la zona hasta la fuente")
        self.boton_fuente.clicked.connect(lambda: self.pedirFuente.emit(self))
        self.boton_marcar = QPushButton()
        self.boton_marcar.setIcon(iconos.icono("crosshair", 16))
        self.boton_marcar.setFixedWidth(34)
        self.boton_marcar.clicked.connect(self._volver_a_marcar)
        fila.addWidget(self.combo_modo, 1)
        fila.addWidget(self.boton_fuente)
        fila.addWidget(self.boton_marcar)
        capa.addLayout(fila)
        self._mostrar()

    # ------------------------------------------------------------ interfaz de zona
    @property
    def nombre(self) -> str:
        return f"Borrado {self.numero}"

    @property
    def zona(self) -> Zona:
        return self._borrado.zona

    def borrado(self) -> ZonaBorrado:
        return self._borrado

    def establecer_zona(self, zona: Optional[Zona], emitir: bool = True) -> None:
        if zona is None:
            return
        self._borrado = replace(self._borrado, zona=zona)
        self._mostrar()
        if emitir:
            self.cambiada.emit()

    def zona_cancelada(self) -> None:
        self._mostrar()

    def establecer_fuente(self, dx: float, dy: float, sin_costuras: bool = True) -> None:
        self._borrado = replace(self._borrado, modo=CLONAR, dx=float(dx), dy=float(dy), sin_costuras=sin_costuras)
        self._mostrar()
        self.cambiada.emit()

    def fuente_cancelada(self) -> None:
        """Se canceló elegir la fuente: si todavía no tenía, vuelve a rellenar."""
        if not self._borrado.listo:
            self._borrado = replace(self._borrado, modo=RELLENAR)
        self._mostrar()

    # ------------------------------------------------------------------- interno
    def renumerar(self, numero: int) -> None:
        self.numero = numero
        self._mostrar()

    def _mostrar(self) -> None:
        b = self._borrado
        modo = b.modo if b.listo else RELLENAR
        self.icono.setPixmap(iconos.pixmap(ICONOS_MODO[modo], 16))
        forma = DESCRIPCION_FORMA.get(b.zona.forma, "")
        self.etiqueta.setText(f"Borrado {self.numero}" + (f"  ·  {forma}" if forma else ""))
        self.combo_modo.blockSignals(True)
        self.combo_modo.setCurrentIndex(1 if b.modo == CLONAR else 0)
        self.combo_modo.blockSignals(False)
        self.boton_fuente.setVisible(b.modo == CLONAR)
        self.boton_marcar.setToolTip("Seguir pintando lo que se borra" if b.zona.es_raster else
                                     "Volver a marcar lo que se borra")

    def _al_cambiar_modo(self, _i: int) -> None:
        modo = self.combo_modo.currentData()
        if modo == CLONAR and not (abs(self._borrado.dx) > 1e-9 or abs(self._borrado.dy) > 1e-9):
            # Todavía no hay fuente: se elige ahora (la fila sigue rellenando si se cancela).
            self._mostrar()
            self.pedirFuente.emit(self)
            return
        self._borrado = replace(self._borrado, modo=modo)
        self._mostrar()
        self.cambiada.emit()

    def _volver_a_marcar(self) -> None:
        forma = self._borrado.zona.forma
        if forma in ("pincel", "mascara"):
            forma = "pincel"
        elif forma == "lazo":
            forma = "poligono"
        self.pedirZona.emit(self, forma)


class _ZonaNueva:
    """Destino de una zona recién marcada: todavía no es una fila."""

    def __init__(self, panel: "PanelBorrar"):
        self._panel = panel
        self.zona: Optional[Zona] = None
        self.nombre = "Borrar"

    def establecer_zona(self, zona: Optional[Zona]) -> None:
        if zona is not None:
            self._panel._zona_marcada(zona)

    def zona_cancelada(self) -> None:
        pass


class _ClonNuevo:
    """Zona marcada en modo "Clonar desde…" que espera que se elija la fuente."""

    def __init__(self, panel: "PanelBorrar", zona: Zona):
        self._panel = panel
        self.zona = zona
        self.nombre = "Borrar"

    def borrado(self) -> ZonaBorrado:
        return ZonaBorrado(self.zona, CLONAR)

    def establecer_fuente(self, dx: float, dy: float, sin_costuras: bool = True) -> None:
        self._panel.agregar(ZonaBorrado(self.zona, CLONAR, float(dx), float(dy), sin_costuras))

    def fuente_cancelada(self) -> None:
        pass  # no se agrega nada


class PanelBorrar(QWidget):
    cambiado = Signal()
    pedirZona = Signal(object, str)  # (destino, forma): hay que marcar en la foto
    pedirFuente = Signal(object)  # (destino): elegir de dónde clonar
    aviso = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filas: list[FilaBorrado] = []
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        self.tarjeta = SeccionPlegable("Borrar objetos", "eraser",
                                       "Quitá cosas de la foto: se rellenan con lo de alrededor o con otra parte "
                                       "que elegís", True, con_interruptor=False, plegable=False)
        capa.addWidget(self.tarjeta)
        cuerpo = self.tarjeta.capa_cuerpo

        selector = QFrame()
        selector.setObjectName("selectorFormato")
        fila_modo = QHBoxLayout(selector)
        fila_modo.setContentsMargins(3, 3, 3, 3)
        fila_modo.setSpacing(3)
        self.grupo_modo = QButtonGroup(self)
        self.grupo_modo.setExclusive(True)
        self.botones_modo = {}
        for modo, texto, ayuda in (
            (RELLENAR, "Rellenar\nautomático", "Completa lo borrado con lo de alrededor: cielo, pasto, pared, "
                                               "arena, agua... Es lo más rápido."),
            (CLONAR, "Clonar\ndesde…", "Copia otra parte de la foto que elegís vos, arrastrando desde la zona "
                                       "hasta la fuente. Sirve para patrones o cuando el relleno no queda bien."),
        ):
            b = QPushButton(texto)
            b.setObjectName("opcionFormato")
            b.setCheckable(True)
            b.setChecked(modo == RELLENAR)
            b.setProperty("modo", modo)
            b.setIcon(iconos.icono(ICONOS_MODO[modo], 20))
            b.setIconSize(QSize(20, 20))
            b.setToolTip(ayuda)
            b.setCursor(Qt.PointingHandCursor)
            self.grupo_modo.addButton(b)
            self.botones_modo[modo] = b
            fila_modo.addWidget(b, 1)
        self.grupo_modo.buttonClicked.connect(lambda _b: self._refrescar())
        cuerpo.addWidget(selector)

        self.nota = QLabel()
        self.nota.setObjectName("nota")
        self.nota.setWordWrap(True)
        cuerpo.addWidget(self.nota)

        fila = QHBoxLayout()
        fila.setSpacing(6)
        self.boton_pintar = QPushButton(" Pintar")
        self.boton_pintar.setIcon(iconos.icono("brush", 16))
        self.boton_pintar.setToolTip("Pintá lo que querés borrar, un poco más grande que el objeto. "
                                     "Clic derecho o la goma borran lo pintado de más; Enter o Listo terminan.")
        self.boton_pintar.clicked.connect(lambda: self._marcar("pincel"))
        self.boton_lazo = QPushButton(" Lazo")
        self.boton_lazo.setIcon(iconos.icono("pentagon", 16))
        self.boton_lazo.setToolTip("Clic punto por punto alrededor de lo que querés borrar. Cerrá con doble clic, "
                                   "Enter o tocando el primer punto.")
        self.boton_lazo.clicked.connect(lambda: self._marcar("poligono"))
        self.boton_rect = QPushButton()
        self.boton_rect.setIcon(iconos.icono("square-dashed", 16))
        self.boton_rect.setFixedWidth(40)
        self.boton_rect.setToolTip("Arrastrá un rectángulo sobre lo que querés borrar")
        self.boton_rect.clicked.connect(lambda: self._marcar("rect"))
        fila.addWidget(self.boton_pintar, 1)
        fila.addWidget(self.boton_lazo, 1)
        fila.addWidget(self.boton_rect)
        cuerpo.addLayout(fila)

        self._aspecto = 1.0
        self._proveedor = None
        self._hay_foto = False
        fila_marca = QHBoxLayout()
        fila_marca.setSpacing(6)
        self.combo_posicion = QComboBox()
        for clave in POSICIONES:
            self.combo_posicion.addItem(NOMBRES_POSICION[clave], clave)
        self.boton_marca = QPushButton(" Quitar marca")
        self.boton_marca.setIcon(iconos.icono("badge-check", 16))
        self.boton_marca.setToolTip("Marca la esquina típica de un logo de IA y la rellena. "
                                    "Si no cae donde está el logo, mové la caja con la mira.")
        self.boton_marca.clicked.connect(self._marca_de_preset)
        self.boton_detectar = QPushButton()
        self.boton_detectar.setIcon(iconos.icono("scan-search", 16))
        self.boton_detectar.setFixedWidth(40)
        self.boton_detectar.setToolTip("Buscar la marca sola en las esquinas")
        self.boton_detectar.clicked.connect(self._detectar)
        fila_marca.addWidget(self.combo_posicion, 1)
        fila_marca.addWidget(self.boton_marca)
        fila_marca.addWidget(self.boton_detectar)
        cuerpo.addLayout(fila_marca)

        self.contenedor = QVBoxLayout()
        self.contenedor.setSpacing(8)
        cuerpo.addLayout(self.contenedor)
        self._refrescar()

    # --------------------------------------------------------------------- modo
    def modo(self) -> str:
        boton = self.grupo_modo.checkedButton()
        return boton.property("modo") if boton is not None else RELLENAR

    def _refrescar(self) -> None:
        self._hay_foto = self._proveedor is not None and self._proveedor() is not None
        if self.modo() == CLONAR:
            texto = ("Marcá lo que querés borrar y después arrastrá desde ahí hasta la parte de la foto que lo "
                     "reemplaza. Vas a ver cómo queda antes de confirmar.")
        else:
            texto = ("Pintá lo que querés borrar, con un poco de margen: se rellena solo con lo de alrededor. "
                     "Funciona mejor sobre fondos parejos o con textura.")
        self.nota.setText(texto)
        lleno = len(self._filas) >= MAX_BORRADOS
        for b in (self.boton_pintar, self.boton_lazo, self.boton_rect):
            b.setEnabled(not lleno)
        for b in (self.combo_posicion, self.boton_marca, self.boton_detectar):
            b.setEnabled(not lleno and self._hay_foto)

    def preparar(self, proveedor) -> None:
        """``proveedor()`` devuelve (rgb, aspecto) de la foto abierta, o None."""
        self._proveedor = proveedor
        self._refrescar()

    def _foto(self):
        return self._proveedor() if self._proveedor is not None else None

    def _marca_de_preset(self) -> None:
        datos = self._foto()
        if datos is None:
            return
        self.agregar(borrado_de_marca(caja_de_preset(self.combo_posicion.currentData(), datos[1])))

    def _detectar(self) -> None:
        datos = self._foto()
        if datos is None:
            return
        caja = detectar_marca(datos[0])
        if caja is None:
            self.aviso.emit("No encontré ninguna marca en las esquinas: probá con la posición a mano.")
        else:
            self.agregar(borrado_de_marca(caja))

    def _marcar(self, forma: str) -> None:
        self.pedirZona.emit(_ZonaNueva(self), forma)

    def _zona_marcada(self, zona: Zona) -> None:
        if self.modo() == CLONAR:
            self.pedirFuente.emit(_ClonNuevo(self, zona))
        else:
            self.agregar(ZonaBorrado(zona, RELLENAR))

    # -------------------------------------------------------------------- filas
    def agregar(self, borrado: ZonaBorrado, emitir: bool = True) -> None:
        if len(self._filas) >= MAX_BORRADOS:
            return
        fila = FilaBorrado(len(self._filas) + 1, borrado)
        fila.cambiada.connect(self.cambiado)
        fila.eliminar.connect(self._quitar)
        fila.pedirZona.connect(self.pedirZona)
        fila.pedirFuente.connect(self.pedirFuente)
        self._filas.append(fila)
        self.contenedor.addWidget(fila)
        self._refrescar()
        if emitir:
            self.cambiado.emit()

    def _quitar(self, fila: FilaBorrado, emitir: bool = True) -> None:
        self._filas.remove(fila)
        fila.setParent(None)
        fila.deleteLater()
        for i, f in enumerate(self._filas, start=1):
            f.renumerar(i)
        self._refrescar()
        if emitir:
            self.cambiado.emit()

    def filas(self) -> list[FilaBorrado]:
        return list(self._filas)

    def estado(self) -> tuple[ZonaBorrado, ...]:
        return tuple(f.borrado() for f in self._filas)

    def restaurar(self, borrados) -> None:
        if tuple(borrados or ()) == self.estado():
            return
        for f in list(self._filas):
            self._quitar(f, emitir=False)
        for b in borrados or ():
            self.agregar(b, emitir=False)
