"""Ventana de tutorial: muestra la guía en PDF adentro de la app.

Aparece cada vez que se abre la app, hasta que se tilda "No volver a mostrar".
Después se puede volver a abrir con el botón "Tutorial" (junto a la versión) o F1.
La guía se empaqueta como ``assets/tutorial.pdf`` (en NaturalShot Lite, ``assets/tutorial_lite.pdf``
si existe; si no, la de siempre: ``edicion.ruta_recurso``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPalette, QPixmap
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from .. import edicion
from . import iconos
from .controles import Interruptor
from .modo_facil import configuracion

CLAVE_NO_MOSTRAR = "interfaz/tutorial_no_mostrar"
AUMENTO_LECTURA = 1.3  # al abrir: página completa agrandada un 30 %


def ruta_tutorial() -> Path:
    """El PDF de la guía: ``assets/tutorial.pdf`` (en la Lite, ``assets/tutorial_lite.pdf`` si existe).
    Desde el código, en la carpeta del proyecto; en el .exe, en ``_internal``."""
    return edicion.ruta_recurso("assets/tutorial.pdf")


def debe_mostrarse_al_iniciar() -> bool:
    valor = configuracion().value(CLAVE_NO_MOSTRAR, False)
    no_mostrar = valor in (True, "true", "1", 1)
    return not no_mostrar and ruta_tutorial().exists()


class _CajaNoMostrar(QFrame):
    """Recuadro con interruptor: "No volver a mostrar". Tocar en cualquier parte lo cambia."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("cajaNoMostrar")
        self.setCursor(Qt.PointingHandCursor)
        fila = QHBoxLayout(self)
        fila.setContentsMargins(12, 8, 14, 8)
        fila.setSpacing(12)
        self.interruptor = Interruptor()
        self.interruptor.setToolTip("Si lo activás, el tutorial no aparece más al abrir la app")
        self.interruptor.toggled.connect(self._refrescar)
        fila.addWidget(self.interruptor, 0, Qt.AlignVCenter)
        textos = QVBoxLayout()
        textos.setSpacing(1)
        self.titulo = QLabel("No volver a mostrar al abrir la app")
        self.titulo.setObjectName("tituloNoMostrar")
        nota = QLabel("Lo abrís cuando quieras con el ícono del libro (arriba, junto a la versión) o con F1")
        nota.setObjectName("notaNoMostrar")
        textos.addWidget(self.titulo)
        textos.addWidget(nota)
        fila.addLayout(textos)
        self._refrescar(False)

    def _refrescar(self, activo: bool) -> None:
        self.setProperty("activo", activo)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, evento) -> None:
        if evento.button() == Qt.LeftButton:
            self.interruptor.toggle()
        super().mousePressEvent(evento)


class DialogoTutorial(QDialog):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("dialogoTutorial")
        self.setWindowTitle(f"Tutorial · {edicion.nombre_app()}")
        self.setModal(True)
        if parent is not None:
            g = parent.geometry()
            self.resize(max(900, int(g.width() * 0.78)), max(640, int(g.height() * 0.88)))
        else:
            self.resize(1100, 820)

        capa = QVBoxLayout(self)
        capa.setContentsMargins(18, 16, 18, 14)
        capa.setSpacing(12)

        # Encabezado: logo, título y navegación por páginas
        cabecera = QHBoxLayout()
        cabecera.setSpacing(12)
        logo = QLabel()
        ruta_logo = edicion.ruta_logo()
        if ruta_logo.exists():
            pm = QPixmap(str(ruta_logo)).scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pm.setDevicePixelRatio(2.0)
            logo.setPixmap(pm)
        cabecera.addWidget(logo)
        textos = QVBoxLayout()
        textos.setSpacing(0)
        titulo = QLabel("Tutorial")
        titulo.setObjectName("tituloApp")
        subtitulo = QLabel("Todo lo que podés hacer con NaturalShot, paso a paso. Usá la rueda del mouse para avanzar.")
        subtitulo.setObjectName("subtituloApp")
        textos.addWidget(titulo)
        textos.addWidget(subtitulo)
        cabecera.addLayout(textos, 1)

        self.boton_anterior = QPushButton()
        self.boton_anterior.setIcon(iconos.icono("chevron-left", 16))
        self.boton_anterior.setToolTip("Página anterior")
        self.boton_anterior.clicked.connect(lambda: self._ir(self._pagina() - 1))
        self.etiqueta_pagina = QLabel("")
        self.etiqueta_pagina.setObjectName("etiquetaZoom")
        self.etiqueta_pagina.setMinimumWidth(110)
        self.etiqueta_pagina.setAlignment(Qt.AlignCenter)
        self.boton_siguiente = QPushButton()
        self.boton_siguiente.setIcon(iconos.icono("chevron-right", 16))
        self.boton_siguiente.setToolTip("Página siguiente")
        self.boton_siguiente.clicked.connect(lambda: self._ir(self._pagina() + 1))
        self.boton_alejar = QPushButton()
        self.boton_alejar.setIcon(iconos.icono("zoom-out", 16))
        self.boton_alejar.setToolTip("Achicar")
        self.boton_alejar.clicked.connect(lambda: self._zoom(1 / 1.2))
        self.boton_ajustar = QPushButton(" Ajustar")
        self.boton_ajustar.setIcon(iconos.icono("maximize", 16))
        self.boton_ajustar.setToolTip("Volver al tamaño de lectura")
        self.boton_ajustar.clicked.connect(self._ajustar)
        self.boton_acercar = QPushButton()
        self.boton_acercar.setIcon(iconos.icono("zoom-in", 16))
        self.boton_acercar.setToolTip("Agrandar")
        self.boton_acercar.clicked.connect(lambda: self._zoom(1.2))
        for b in (self.boton_anterior, self.etiqueta_pagina, self.boton_siguiente):
            cabecera.addWidget(b)
        cabecera.addSpacing(10)
        for b in (self.boton_alejar, self.boton_ajustar, self.boton_acercar):
            cabecera.addWidget(b)
        capa.addLayout(cabecera)

        # La guía
        marco = QFrame()
        marco.setObjectName("marcoTutorial")
        capa_marco = QVBoxLayout(marco)
        capa_marco.setContentsMargins(0, 0, 0, 0)
        self.documento = QPdfDocument(self)
        self.vista = QPdfView(marco)
        self.vista.setObjectName("vistaTutorial")
        self.vista.setDocument(self.documento)
        self.vista.setPageMode(QPdfView.PageMode.MultiPage)
        # Página completa a la vista: con "al ancho" una hoja A4 queda gigante en una ventana apaisada.
        self.vista.setZoomMode(QPdfView.ZoomMode.FitInView)
        self.vista.setPageSpacing(14)
        paleta = self.vista.palette()
        paleta.setColor(QPalette.Dark, QColor("#1e1f22"))
        self.vista.setPalette(paleta)
        self.vista.pageNavigator().currentPageChanged.connect(lambda _p: self._refrescar_pagina())
        capa_marco.addWidget(self.vista)
        self.aviso = QLabel("No se encontró el tutorial dentro de la app.")
        self.aviso.setObjectName("nota")
        self.aviso.setAlignment(Qt.AlignCenter)
        self.aviso.hide()
        capa_marco.addWidget(self.aviso)
        capa.addWidget(marco, 1)

        # Pie: no volver a mostrar y cerrar
        pie = QHBoxLayout()
        pie.setSpacing(10)
        caja = _CajaNoMostrar()
        self.check_no_mostrar = caja.interruptor
        valor = configuracion().value(CLAVE_NO_MOSTRAR, False)
        self.check_no_mostrar.setChecked(valor in (True, "true", "1", 1))
        pie.addWidget(caja)
        pie.addStretch(1)
        self.boton_pdf = QPushButton(" Abrir como PDF")
        self.boton_pdf.setIcon(iconos.icono("book-open", 16))
        self.boton_pdf.setToolTip("Abrir la guía en el visor de PDF de la compu (para imprimirla o guardarla)")
        self.boton_pdf.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ruta_tutorial()))))
        self.boton_cerrar = QPushButton("  Empezar a usar NaturalShot")
        self.boton_cerrar.setObjectName("botonPrimario")
        self.boton_cerrar.setIcon(iconos.icono("check", 16, color="#ffffff"))
        self.boton_cerrar.setIconSize(QSize(16, 16))
        self.boton_cerrar.clicked.connect(self.accept)
        pie.addWidget(self.boton_pdf)
        pie.addWidget(self.boton_cerrar)
        capa.addLayout(pie)

        self._cargar()

    # ----------------------------------------------------------------- PDF
    def _cargar(self) -> None:
        ruta = ruta_tutorial()
        ok = ruta.exists() and self.documento.load(str(ruta)) == QPdfDocument.Error.None_
        self.vista.setVisible(ok)
        self.aviso.setVisible(not ok)
        for b in (self.boton_anterior, self.boton_siguiente, self.boton_alejar, self.boton_ajustar,
                  self.boton_acercar, self.boton_pdf):
            b.setEnabled(ok)
        self._refrescar_pagina()

    def _pagina(self) -> int:
        return self.vista.pageNavigator().currentPage()

    def _ir(self, pagina: int) -> None:
        total = self.documento.pageCount()
        if total:
            self.vista.pageNavigator().jump(max(0, min(total - 1, pagina)), QPointF(), self.vista.zoomFactor())

    def _zoom(self, factor: float) -> None:
        self.vista.setZoomMode(QPdfView.ZoomMode.Custom)
        self.vista.setZoomFactor(max(0.2, min(4.0, self.vista.zoomFactor() * factor)))

    def _ajustar(self) -> None:
        """Vuelve al tamaño de lectura: la página completa agrandada un 30 %."""
        self._zoom_inicial()

    def _zoom_inicial(self) -> None:
        """Página completa + 30 %: se lee mejor y casi toda la hoja sigue a la vista."""
        if not self.documento.pageCount():
            return
        hoja = self.documento.pagePointSize(0)
        visor = self.vista.viewport().size()
        escala = self.vista.logicalDpiX() / 72.0  # QPdfView: zoom 1 = tamaño real en pantalla
        if hoja.width() <= 0 or hoja.height() <= 0 or visor.width() < 50:
            return
        ajuste = min((visor.width() - 24) / (hoja.width() * escala),
                     (visor.height() - 24) / (hoja.height() * escala))
        self.vista.setZoomMode(QPdfView.ZoomMode.Custom)
        self.vista.setZoomFactor(max(0.2, min(4.0, ajuste * AUMENTO_LECTURA)))

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        # El tamaño del visor recién se conoce cuando la ventana ya está en pantalla.
        QTimer.singleShot(0, self._zoom_inicial)

    def _refrescar_pagina(self) -> None:
        total = self.documento.pageCount()
        actual = self._pagina() + 1 if total else 0
        self.etiqueta_pagina.setText(f"Página {actual} de {total}" if total else "")
        self.boton_anterior.setEnabled(total > 0 and actual > 1)
        self.boton_siguiente.setEnabled(total > 0 and actual < total)

    # --------------------------------------------------------------- cierre
    def done(self, resultado: int) -> None:
        configuracion().setValue(CLAVE_NO_MOSTRAR, self.check_no_mostrar.isChecked())
        super().done(resultado)
