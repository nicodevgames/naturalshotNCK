"""El botón **Medida** de la barra de arriba (Fácil y Editor) y su menú.

El menú (``MenuMedida``) es un ``QMenu`` de la app (oscuro, borde vino) con una cabecera y una
fila por medida (``FilaMedida``): el ícono, el nombre, la proporción en magenta, los píxeles en
gris y una tilde en la elegida. Tocar una fila (o elegirla con las flechas y Enter) avisa
``medidaElegida(tam)``, con ``None`` para "Original". La ventana hace el resto (recorte, estado,
historial): ver ``motor/medida.py``.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QVBoxLayout, QWidget, QWidgetAction

from ..motor import medida as md
from . import estilo, iconos


class FilaMedida(QFrame):
    """Una fila del menú: ícono, nombre, proporción, píxeles y la tilde si es la elegida."""

    tocada = Signal()

    def __init__(self, m: md.Medida, elegida: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("filaMedida")
        self.setProperty("elegida", elegida)
        self.setProperty("activa", False)
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)
        fila = QHBoxLayout(self)
        fila.setContentsMargins(10, 7, 10, 7)
        fila.setSpacing(10)
        icono = QLabel()
        icono.setPixmap(iconos.pixmap(m.icono, 18, estilo.MAGENTA if elegida else None))
        icono.setFixedWidth(20)
        fila.addWidget(icono)
        nombre = QLabel(m.nombre)
        nombre.setObjectName("nombreMedida")
        fila.addWidget(nombre)
        if m.proporcion:
            proporcion = QLabel(m.proporcion)
            proporcion.setObjectName("proporcionMedida")
            fila.addWidget(proporcion)
        fila.addStretch(1)
        pixeles = QLabel(f"{m.ancho} × {m.alto}" if m.ancho else "sin cambiar el tamaño")
        pixeles.setObjectName("pixelesMedida")
        fila.addSpacing(18)
        fila.addWidget(pixeles)
        tilde = QLabel()
        tilde.setFixedWidth(16)
        if elegida:
            tilde.setPixmap(iconos.pixmap("check", 15, estilo.MAGENTA))
        fila.addWidget(tilde)
        for hijo in self.findChildren(QLabel):
            hijo.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def marcar_activa(self, activa: bool) -> None:
        """La fila bajo el mouse o elegida con las flechas (el ``:hover`` no sigue al teclado)."""
        if bool(self.property("activa")) != activa:
            self.setProperty("activa", activa)
            self.style().unpolish(self)
            self.style().polish(self)

    def mouseReleaseEvent(self, evento) -> None:
        if evento.button() == Qt.LeftButton and self.rect().contains(evento.position().toPoint()):
            self.tocada.emit()
            return
        super().mouseReleaseEvent(evento)


class MenuMedida(QMenu):
    """El menú de las medidas. ``abrir_debajo(boton, actual)`` lo muestra debajo del botón."""

    medidaElegida = Signal(object)  # (ancho, alto) o None ("Original")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("menuMedida")
        self.filas: list[tuple[Optional[tuple[int, int]], FilaMedida, QWidgetAction]] = []
        self.hovered.connect(self._al_resaltar)

    def armar(self, actual) -> None:
        """Vuelve a armar las filas, con la tilde en ``actual`` (None = Original)."""
        actual = md.medida_valida(actual)
        self.clear()
        self.filas = []
        cabecera = QWidget()
        capa = QVBoxLayout(cabecera)
        capa.setContentsMargins(10, 6, 10, 6)
        capa.setSpacing(1)
        titulo = QLabel("Medida de salida")
        titulo.setObjectName("tituloMedida")
        nota = QLabel("Elegí dónde la vas a usar: se recorta con esa proporción y se exporta exacta.")
        nota.setObjectName("notaMedida")
        capa.addWidget(titulo)
        capa.addWidget(nota)
        accion = QWidgetAction(self)
        accion.setDefaultWidget(cabecera)
        accion.setEnabled(False)
        self.addAction(accion)
        self.addSeparator()
        for i, m in enumerate((md.ORIGINAL,) + md.MEDIDAS):
            tam = m.tam if m.ancho else None
            fila = FilaMedida(m, tam == actual)
            accion = QWidgetAction(self)
            accion.setDefaultWidget(fila)
            accion.triggered.connect(lambda _c=False, t=tam: self._elegir(t))
            fila.tocada.connect(accion.trigger)
            self.addAction(accion)
            self.filas.append((tam, fila, accion))
            if i == 0:
                self.addSeparator()

    def _al_resaltar(self, accion) -> None:
        for _tam, fila, a in self.filas:
            fila.marcar_activa(a is accion)

    def _elegir(self, tam) -> None:
        self.close()
        self.medidaElegida.emit(tam)

    def abrir_debajo(self, boton: QWidget, actual) -> None:
        self.armar(actual)
        self.popup(boton.mapToGlobal(QPoint(0, boton.height() + 4)))
