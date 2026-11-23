"""Tira de fotos: miniaturas de todas las fotos abiertas para pasar de una a otra."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QListWidget, QListWidgetItem, QMenu, QPushButton

from . import iconos

LADO_MINIATURA = 150


class TiraFotos(QFrame):
    fotoElegida = Signal(int)
    agregarPedido = Signal()
    quitarPedido = Signal(int)
    quitarTodasPedido = Signal()  # "Quitar todas las fotos": empezar de cero (la ventana confirma)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tiraFotos")
        fila = QHBoxLayout(self)
        fila.setContentsMargins(8, 6, 8, 6)
        fila.setSpacing(8)

        self.boton_agregar = QPushButton()
        self.boton_agregar.setObjectName("botonAgregarFoto")
        self.boton_agregar.setIcon(iconos.icono("plus", 20))
        self.boton_agregar.setIconSize(QSize(20, 20))
        self.boton_agregar.setFixedSize(56, 72)
        self.boton_agregar.setToolTip("Agregar fotos a la tira (podés elegir varias a la vez)")
        self.boton_agregar.clicked.connect(self.agregarPedido)
        fila.addWidget(self.boton_agregar)

        self.lista = QListWidget()
        self.lista.setObjectName("listaTira")
        self.lista.setViewMode(QListWidget.IconMode)
        self.lista.setFlow(QListWidget.LeftToRight)
        self.lista.setWrapping(False)
        self.lista.setMovement(QListWidget.Static)
        self.lista.setIconSize(QSize(108, 72))
        self.lista.setSpacing(4)
        self.lista.setFixedHeight(86)
        self.lista.setHorizontalScrollMode(QListWidget.ScrollPerPixel)
        self.lista.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lista.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lista.customContextMenuRequested.connect(self._menu)
        self.lista.currentRowChanged.connect(self._al_cambiar_fila)
        fila.addWidget(self.lista, 1)

        # Empezar de cero: chico y al final, para no tocarlo sin querer (igual pide confirmación).
        self.boton_quitar_todas = QPushButton()
        self.boton_quitar_todas.setObjectName("botonQuitarTodas")
        self.boton_quitar_todas.setIcon(iconos.icono("trash-2", 16))
        self.boton_quitar_todas.setIconSize(QSize(16, 16))
        self.boton_quitar_todas.setFixedSize(34, 34)
        self.boton_quitar_todas.setCursor(Qt.PointingHandCursor)
        self.boton_quitar_todas.setToolTip("Quitar todas las fotos de la tira y empezar de cero "
                                           "(los archivos no se tocan)")
        self.boton_quitar_todas.clicked.connect(self.quitarTodasPedido)
        fila.addWidget(self.boton_quitar_todas, 0, Qt.AlignVCenter)
        self._bloqueado = False

    def _al_cambiar_fila(self, fila: int) -> None:
        if not self._bloqueado and fila >= 0:
            self.fotoElegida.emit(fila)

    def _menu(self, pos) -> None:
        if self.lista.count() == 0:
            return
        item = self.lista.itemAt(pos)
        menu = QMenu(self)
        if item is not None:
            quitar = QAction(iconos.icono("x", 14), "Quitar de la tira", menu)
            quitar.triggered.connect(lambda: self.quitarPedido.emit(self.lista.row(item)))
            menu.addAction(quitar)
            menu.addSeparator()
        todas = QAction(iconos.icono("trash-2", 14), "Quitar todas las fotos…", menu)
        todas.triggered.connect(self.quitarTodasPedido)
        menu.addAction(todas)
        menu.exec(self.lista.mapToGlobal(pos))

    def establecer(self, fotos: list[tuple[str, QPixmap | None]], actual: int) -> None:
        """``fotos``: (ruta, miniatura o None mientras carga)."""
        self._bloqueado = True
        self.lista.clear()
        for ruta, mini in fotos:
            item = QListWidgetItem(QIcon(mini) if mini is not None else iconos.icono("image", 28), "")
            item.setToolTip(Path(ruta).name)
            item.setSizeHint(QSize(116, 78))
            self.lista.addItem(item)
        if 0 <= actual < self.lista.count():
            self.lista.setCurrentRow(actual)
            self.lista.scrollToItem(self.lista.currentItem())
        self._bloqueado = False
        self.setVisible(len(fotos) > 0)

    def actualizar_miniatura(self, indice: int, mini: QPixmap) -> None:
        """Pone la miniatura de una foto que terminó de cargar, sin rearmar la tira
        (no mueve el desplazamiento mientras llegan las demás)."""
        item = self.lista.item(indice)
        if item is not None:
            item.setIcon(QIcon(mini))
