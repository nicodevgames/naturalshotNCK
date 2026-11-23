"""Aviso flotante: un mensaje discreto abajo de la vista que se va solo.

Lo usa la sesión, por ejemplo: "2 fotos de la sesión anterior ya no están en su
carpeta", y el cambio de modo: "Esto es un video: lo abrimos en el modo Video".
No tapa nada importante, no pide confirmación y tiene una × para cerrarlo antes.
Se acomoda solo cuando cambia el tamaño de su contenedor (con un filtro de eventos
en ese widget, no en toda la aplicación). Hay uno solo en la ventana: al cambiar
entre fotos y Video pasa a la vista del modo que se ve (``mover_a``).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from . import iconos

MARGEN_ABAJO = 18  # px desde el borde de abajo del contenedor
ANCHO_MAXIMO = 560


class AvisoFlotante(QFrame):
    def __init__(self, contenedor: QWidget):
        super().__init__(contenedor)
        self.setObjectName("avisoFlotante")
        self.setAttribute(Qt.WA_StyledBackground, True)
        fila = QHBoxLayout(self)
        fila.setContentsMargins(12, 8, 8, 8)
        fila.setSpacing(10)
        self.icono = QLabel()
        self.icono.setFixedSize(18, 18)
        fila.addWidget(self.icono, 0, Qt.AlignVCenter)
        self.texto = QLabel()
        self.texto.setObjectName("textoAviso")
        self.texto.setWordWrap(True)
        self.texto.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        fila.addWidget(self.texto, 1)
        self.boton_cerrar = QPushButton()
        self.boton_cerrar.setObjectName("botonCerrarAviso")
        self.boton_cerrar.setIcon(iconos.icono("x", 14))
        self.boton_cerrar.setIconSize(QSize(14, 14))
        self.boton_cerrar.setFixedSize(24, 24)
        self.boton_cerrar.setCursor(Qt.PointingHandCursor)
        self.boton_cerrar.setToolTip("Cerrar este aviso")
        self.boton_cerrar.clicked.connect(self.ocultar)
        fila.addWidget(self.boton_cerrar, 0, Qt.AlignVCenter)
        self._timer = QTimer(self, singleShot=True)
        self._timer.timeout.connect(self.ocultar)
        self._segundos = 12
        self.tipo = ""  # para qué es el aviso (por ejemplo, "modo": explica un cambio de modo)
        contenedor.installEventFilter(self)
        self.hide()

    def mostrar(self, texto: str, detalle: str = "", icono: str = "triangle-alert", segundos: int = 12,
                tipo: str = "") -> None:
        """Muestra el aviso (el tiempo empieza a correr cuando de verdad se ve)."""
        self.tipo = tipo
        self.icono.setPixmap(iconos.pixmap(icono, 16))
        self.texto.setText(texto)
        self.setToolTip(detalle)
        self._segundos = segundos
        self._ubicar()
        self.raise_()
        if self.isVisible():  # ya estaba a la vista: vuelve a contar
            self._timer.start(segundos * 1000)
        self.show()  # si la ventana todavía no se ve, cuenta desde que aparece (showEvent)

    def ocultar(self) -> None:
        self._timer.stop()
        self.hide()

    @property
    def mostrado(self) -> bool:
        """Si el aviso está puesto (aunque su contenedor no se vea en este momento)."""
        return not self.isHidden()

    def mover_a(self, contenedor: QWidget) -> None:
        """Pasa el aviso a otro contenedor (la vista de fotos o la de video). Si estaba a la
        vista, sigue a la vista allá, con el tiempo que le quedaba."""
        anterior = self.parentWidget()
        if contenedor is anterior:
            return
        mostrado = self.mostrado
        restante = self._timer.remainingTime() if self._timer.isActive() else -1
        if anterior is not None:
            anterior.removeEventFilter(self)
        self.setParent(contenedor)  # queda oculto
        contenedor.installEventFilter(self)
        if mostrado:
            self._ubicar()
            self.raise_()
            self.show()
            if restante > 0:
                self._timer.start(restante)

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        self._ubicar()
        self._timer.start(self._segundos * 1000)

    # Los clics sobre el aviso son del aviso: no pasan a la vista de abajo (que, vacía, abriría
    # el diálogo de Abrir, o arrastraría la foto).
    def mousePressEvent(self, evento) -> None:
        evento.accept()

    def mouseReleaseEvent(self, evento) -> None:
        evento.accept()

    def mouseDoubleClickEvent(self, evento) -> None:
        evento.accept()

    def _ubicar(self) -> None:
        contenedor = self.parentWidget()
        if contenedor is None:
            return
        # Tan ancho como el texto (más el ícono, la × y los márgenes), sin pasarse.
        natural = self.texto.fontMetrics().horizontalAdvance(self.texto.text()) + 12 + 18 + 10 + 10 + 24 + 8 + 6
        ancho = max(200, min(ANCHO_MAXIMO, contenedor.width() - 48, natural))
        self.setFixedWidth(ancho)
        self.adjustSize()
        self.move((contenedor.width() - self.width()) // 2,
                  max(0, contenedor.height() - self.height() - MARGEN_ABAJO))

    def eventFilter(self, objeto, evento) -> bool:
        if objeto is self.parentWidget() and evento.type() == QEvent.Resize and self.isVisible():
            self._ubicar()
        return False
