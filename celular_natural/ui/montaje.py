"""Panel de montaje: pegar partes de otras fotos de la tira sobre la foto actual."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget,
)

from ..motor.montaje import CapaFoto
from ..motor.zonas import Zona
from . import iconos
from .controles import ZONAS_AUTOMATICAS, ControlDeslizante, SeccionPlegable, clave_zona

MAX_FOTOS = 4

# Mitades: el rectángulo sobresale de la foto para que el borde suave solo se
# note en la unión, no contra los bordes de la imagen.
MITADES = {
    "mitad_arriba": (-0.2, -0.2, 1.2, 0.5),
    "mitad_abajo": (-0.2, 0.5, 1.2, 1.2),
    "mitad_izq": (-0.2, -0.2, 0.5, 1.2),
    "mitad_der": (0.5, -0.2, 1.2, 1.2),
}


class FilaMontaje(QFrame):
    """Una foto superpuesta. Tiene la misma interfaz de zona que una capa."""

    cambiada = Signal()
    eliminar = Signal(object)
    pedirZona = Signal(object, str)

    OPCIONES = (
        ("Mitad de arriba", "mitad_arriba", "panel-top"),
        ("Mitad de abajo", "mitad_abajo", "panel-bottom"),
        ("Mitad izquierda", "mitad_izq", "panel-left"),
        ("Mitad derecha", "mitad_der", "panel-right"),
        ("Toda la foto", None, "scan"),
        ("Rectángulo", "rect", "square-dashed"),
        ("Elipse", "elipse", "circle-dashed"),
        ("Lazo poligonal", "poligono", "pentagon"),
        ("Pincel", "pincel", "brush"),
        ("Cielo (automático)", "cielo", "cloud-sun"),
        ("Piel (automática)", "piel", "hand"),
    )

    def __init__(self, numero: int, ruta: str, miniatura: Optional[QPixmap], capa: Optional[CapaFoto] = None,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("filaCapa")
        self.numero = numero
        self.ruta = ruta
        self.zona: Optional[Zona] = None
        capa_v = QVBoxLayout(self)
        capa_v.setContentsMargins(10, 8, 8, 10)
        capa_v.setSpacing(6)

        arriba = QHBoxLayout()
        arriba.setSpacing(8)
        self.mini = QLabel()
        self.mini.setFixedSize(48, 34)
        self.mini.setObjectName("miniMontaje")
        if miniatura is not None:
            self.mini.setPixmap(miniatura.scaled(48, 34, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        self.etiqueta = QLabel()
        self.etiqueta.setObjectName("etiquetaCapa")
        self.etiqueta.setToolTip(ruta)
        boton_quitar = QPushButton()
        boton_quitar.setIcon(iconos.icono("x", 16))
        boton_quitar.setObjectName("botonQuitar")
        boton_quitar.setFixedSize(24, 24)
        boton_quitar.setToolTip("Quitar esta foto del montaje")
        boton_quitar.clicked.connect(lambda: self.eliminar.emit(self))
        arriba.addWidget(self.mini)
        arriba.addWidget(self.etiqueta, 1)
        arriba.addWidget(boton_quitar)
        capa_v.addLayout(arriba)
        self.renumerar(numero)

        fila_zona = QHBoxLayout()
        fila_zona.setSpacing(6)
        dnd = QLabel("Dónde")
        dnd.setObjectName("etiquetaControl")
        self.combo_zona = QComboBox()
        for texto, clave, icono in self.OPCIONES:
            self.combo_zona.addItem(iconos.icono(icono, 16), texto, clave)
        self.combo_zona.setToolTip("Qué parte de esta foto se pega sobre la actual")
        self.combo_zona.currentIndexChanged.connect(self._al_cambiar_opcion)
        self.boton_marcar = QPushButton()
        self.boton_marcar.setIcon(iconos.icono("crosshair", 16))
        self.boton_marcar.setFixedWidth(34)
        self.boton_marcar.setToolTip("Volver a marcar la zona en la foto (con el pincel: seguir pintando)")
        self.boton_marcar.clicked.connect(self._volver_a_marcar)
        fila_zona.addWidget(dnd)
        fila_zona.addWidget(self.combo_zona, 1)
        fila_zona.addWidget(self.boton_marcar)
        capa_v.addLayout(fila_zona)

        self.pluma = ControlDeslizante("pluma", "Borde suave", 0, 100,
                                       "Qué tan gradual es la unión entre las dos fotos.")
        self.pluma.establecer(40, 40)
        self.pluma.valorCambiado.connect(lambda *_: self._actualizar_zona())
        self.opacidad = ControlDeslizante("opacidad", "Opacidad", 0, 100, "Cuánto se ve esta foto encima de la actual.")
        self.opacidad.establecer(100, 100)
        self.opacidad.valorCambiado.connect(lambda *_: self.cambiada.emit())
        self.check_invertir = QCheckBox("Invertir (todo menos la zona)")
        self.check_invertir.toggled.connect(lambda _v: self._actualizar_zona())
        self.check_alinear = QCheckBox("Alinear automáticamente")
        self.check_alinear.setChecked(True)
        self.check_alinear.setToolTip("Corrige que el celular se haya movido un poco entre una toma y la otra")
        self.check_alinear.toggled.connect(lambda _v: self.cambiada.emit())
        self.check_igualar = QCheckBox("Igualar brillo y color")
        self.check_igualar.setChecked(True)
        self.check_igualar.setToolTip("Empareja la exposición y el color para que no se note la unión")
        self.check_igualar.toggled.connect(lambda _v: self.cambiada.emit())
        for w in (self.pluma, self.opacidad, self.check_invertir, self.check_alinear, self.check_igualar):
            capa_v.addWidget(w)

        if capa is not None:
            self.opacidad.establecer(capa.opacidad, 100)
            for chk, valor in ((self.check_alinear, capa.alinear), (self.check_igualar, capa.igualar)):
                chk.blockSignals(True)
                chk.setChecked(valor)
                chk.blockSignals(False)
            self.establecer_zona(capa.zona, emitir=False)
        else:
            self.combo_zona.blockSignals(True)
            self.combo_zona.setCurrentIndex(1)  # "Mitad de abajo"
            self.combo_zona.blockSignals(False)
            self._aplicar_mitad("mitad_abajo", emitir=False)
        self._mostrar_opciones()

    # ------------------------------------------------------------------ zona
    @property
    def nombre(self) -> str:
        return f"Montaje {self.numero}"

    def renumerar(self, numero: int) -> None:
        self.numero = numero
        nombre = Path(self.ruta).name
        self.etiqueta.setText(self.etiqueta.fontMetrics().elidedText(nombre, Qt.ElideMiddle, 190))

    def _mostrar_opciones(self) -> None:
        clave = self.combo_zona.currentData()
        self.boton_marcar.setVisible(clave in ("rect", "elipse", "poligono", "pincel") + ZONAS_AUTOMATICAS)
        self.boton_marcar.setToolTip(
            "Corregir la zona con el pincel: pintá para sumar y usá la goma o el clic derecho para restar"
            if clave in ZONAS_AUTOMATICAS else
            "Volver a marcar la zona en la foto (con el pincel: seguir pintando)")
        self.check_invertir.setVisible(self.zona is not None)
        # El borde de lo pintado (o de una máscara automática) no sale del "Borde suave".
        self.pluma.setVisible(self.zona is not None and not self.zona.es_raster)

    def _volver_a_marcar(self) -> None:
        clave = self.combo_zona.currentData() or "rect"
        self.pedirZona.emit(self, "pincel" if clave in ZONAS_AUTOMATICAS else clave)

    def _aplicar_mitad(self, clave: str, emitir: bool = True) -> None:
        x0, y0, x1, y1 = MITADES[clave]
        self.zona = Zona("rect", x0, y0, x1, y1, pluma=self.pluma.valor(), invertir=self.check_invertir.isChecked())
        self._mostrar_opciones()
        if emitir:
            self.cambiada.emit()

    def _al_cambiar_opcion(self, _i: int) -> None:
        clave = self.combo_zona.currentData()
        if clave in MITADES:
            self._aplicar_mitad(clave)
        elif clave is None:
            self.zona = None
            self._mostrar_opciones()
            self.cambiada.emit()
        elif clave in ZONAS_AUTOMATICAS and not (self.zona is not None and self._clave_de(self.zona) == clave):
            self._mostrar_opciones()
            self.pedirZona.emit(self, clave)  # se detecta en segundo plano
        elif self.zona is not None and self._clave_de(self.zona) == clave:
            self._mostrar_opciones()
        else:
            self._mostrar_opciones()
            self.pedirZona.emit(self, clave)

    @staticmethod
    def _clave_de(zona: Optional[Zona]) -> Optional[str]:
        if zona is None:
            return None
        coords = (zona.x0, zona.y0, zona.x1, zona.y1)
        for clave, valor in MITADES.items():
            if zona.forma == "rect" and all(abs(a - b) < 1e-6 for a, b in zip(coords, valor)):
                return clave
        return clave_zona(zona)

    def _actualizar_zona(self) -> None:
        if self.zona is None:
            return
        self.zona = replace(self.zona, pluma=self.pluma.valor(), invertir=self.check_invertir.isChecked())
        self.cambiada.emit()

    def establecer_zona(self, zona: Optional[Zona], emitir: bool = True) -> None:
        self.zona = zona
        clave = self._clave_de(zona)
        claves = [c for _t, c, _i in self.OPCIONES]
        for w in (self.combo_zona, self.check_invertir):
            w.blockSignals(True)
        self.combo_zona.setCurrentIndex(claves.index(clave) if clave in claves else 4)
        if zona is not None:
            self.check_invertir.setChecked(zona.invertir)
            self.pluma.establecer(zona.pluma, 40)
        for w in (self.combo_zona, self.check_invertir):
            w.blockSignals(False)
        self._mostrar_opciones()
        if emitir:
            self.cambiada.emit()

    def zona_cancelada(self) -> None:
        # Vuelve a mostrar la opción que corresponde a la zona que ya tenía.
        self.establecer_zona(self.zona, emitir=False)

    def capa(self) -> CapaFoto:
        return CapaFoto(self.ruta, self.zona, self.opacidad.valor(),
                        self.check_alinear.isChecked(), self.check_igualar.isChecked())


class PanelMontaje(QWidget):
    cambiado = Signal()
    pedirZona = Signal(object, str)

    def __init__(self, proveedor: Callable[[], list[tuple[str, Optional[QPixmap]]]], parent=None):
        """``proveedor()`` devuelve las otras fotos de la tira: (ruta, miniatura)."""
        super().__init__(parent)
        self._proveedor = proveedor
        self._filas: list[FilaMontaje] = []
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        self.tarjeta = SeccionPlegable("Montaje", "images", "Pegá partes de otra foto sobre esta", True,
                                       con_interruptor=False, plegable=False)
        capa.addWidget(self.tarjeta)
        cuerpo = self.tarjeta.capa_cuerpo
        nota = QLabel("Ideal para fotos casi iguales: tomá la mejor parte de cada una. "
                      "Se alinean y se igualan solas, y el filtro se aplica después sobre el resultado.")
        nota.setObjectName("nota")
        nota.setWordWrap(True)
        cuerpo.addWidget(nota)
        self.contenedor = QVBoxLayout()
        self.contenedor.setSpacing(8)
        cuerpo.addLayout(self.contenedor)
        self.boton_agregar = QPushButton(" Superponer otra foto")
        self.boton_agregar.setIcon(iconos.icono("plus", 16))
        self.boton_agregar.setObjectName("botonAgregarCapa")
        self.boton_agregar.clicked.connect(self._menu_fotos)
        cuerpo.addWidget(self.boton_agregar)

    def _menu_fotos(self) -> None:
        otras = self._proveedor()
        menu = QMenu(self)
        if not otras:
            accion = QAction("Primero agregá otra foto a la tira (botón + de abajo)", menu)
            accion.setEnabled(False)
            menu.addAction(accion)
        for ruta, mini in otras:
            accion = QAction(QIcon(mini) if mini is not None else iconos.icono("image", 16), Path(ruta).name, menu)
            accion.triggered.connect(lambda _c=False, r=ruta, m=mini: self.agregar(r, m))
            menu.addAction(accion)
        menu.exec(self.boton_agregar.mapToGlobal(self.boton_agregar.rect().bottomLeft()))

    def agregar(self, ruta: str, miniatura: Optional[QPixmap] = None, capa: Optional[CapaFoto] = None,
                emitir: bool = True) -> None:
        if len(self._filas) >= MAX_FOTOS:
            return
        fila = FilaMontaje(len(self._filas) + 1, ruta, miniatura, capa)
        fila.cambiada.connect(self.cambiado)
        fila.eliminar.connect(self._quitar)
        fila.pedirZona.connect(self.pedirZona)
        self._filas.append(fila)
        self.contenedor.addWidget(fila)
        self.boton_agregar.setEnabled(len(self._filas) < MAX_FOTOS)
        if emitir:
            self.cambiado.emit()

    def _quitar(self, fila: FilaMontaje, emitir: bool = True) -> None:
        self._filas.remove(fila)
        fila.setParent(None)
        fila.deleteLater()
        for i, f in enumerate(self._filas, start=1):
            f.renumerar(i)
        self.boton_agregar.setEnabled(True)
        if emitir:
            self.cambiado.emit()

    def filas(self) -> list[FilaMontaje]:
        return list(self._filas)

    def estado(self) -> tuple[CapaFoto, ...]:
        return tuple(f.capa() for f in self._filas)

    def restaurar(self, capas, miniaturas: Callable[[str], Optional[QPixmap]]) -> None:
        for f in list(self._filas):
            self._quitar(f, emitir=False)
        for c in capas:
            self.agregar(c.ruta, miniaturas(c.ruta), c, emitir=False)

    def completar_miniaturas(self, miniaturas: Callable[[str], Optional[QPixmap]]) -> None:
        """Pone la miniatura de las filas que todavía no la tenían (al recuperar la
        sesión, la otra foto puede terminar de cargar después que la actual)."""
        for f in self._filas:
            if f.mini.pixmap() is None or f.mini.pixmap().isNull():
                mini = miniaturas(f.ruta)
                if mini is not None:
                    f.mini.setPixmap(mini.scaled(48, 34, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
