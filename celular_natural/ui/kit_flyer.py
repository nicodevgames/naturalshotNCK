"""Kit básico para hacer flyers en el modo Photoshop de NaturalShot Lite.

* **Nuevo** (``DialogoNuevo``): el tamaño (listos o a medida) y el fondo (blanco, negro, transparente,
  un color o un degradado de dos colores). Desde la Etapa 2 la ventana crea un documento de verdad,
  sin foto (``Documento.nuevo_lienzo`` con el fondo como ``formas.Relleno``: ``DialogoNuevo.relleno``),
  en lugar del PNG liso de antes.
* **Texto** (``DialogoTexto`` y ``dibujar_texto``): el texto se dibuja con QPainter sobre un QImage
  transparente del tamaño justo (más un margen y la sombra) y se agrega como capa imagen.
* **Quitar fondo** (``quitar_fondo``): ``seleccion_auto.recortar_objeto`` con el rectángulo de toda
  la imagen menos un 3 % de margen; devuelve la imagen RGBA con el fondo transparente.

No toca el motor de capas: usa su API (el texto del kit es una capa imagen hasta que llegue el texto
vivo de la Etapa 2).
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFontComboBox,
    QFormLayout, QHBoxLayout, QPlainTextEdit, QPushButton, QRadioButton, QSpinBox, QVBoxLayout, QWidget,
)

TAMANOS = (
    ("Post (1080 × 1080)", 1080, 1080),
    ("Post vertical (1080 × 1350)", 1080, 1350),
    ("Historia (1080 × 1920)", 1080, 1920),
    ("A4 (2480 × 3508)", 2480, 3508),
    ("Carta (2550 × 3300)", 2550, 3300),
    ("Portada (1920 × 1080)", 1920, 1080),
    ("Banner (1500 × 500)", 1500, 500),
    ("Personalizado", 0, 0),
)
LADO_MAX_LIENZO = 8000
MARGEN_FONDO = 0.03  # quitar fondo: el rectángulo es toda la imagen menos este margen
ALINEACIONES = (("Izquierda", "izquierda"), ("Centro", "centro"), ("Derecha", "derecha"))
_FLAG_ALINEACION = {"izquierda": Qt.AlignLeft, "centro": Qt.AlignHCenter, "derecha": Qt.AlignRight}


# ---------------------------------------------------------------------------
# Nuevo
# ---------------------------------------------------------------------------

def relleno_de_fondo(fondo):
    """El ``formas.Relleno`` de un fondo: None o "transparente" → sin relleno; un color (r, g, b) o
    (r, g, b, a) → ese color; un ``Relleno`` → tal cual."""
    from ..motor.formas import Relleno
    if isinstance(fondo, Relleno):
        return fondo
    if fondo is None or fondo == "transparente":
        return Relleno("ninguno")
    c = tuple(int(v) for v in tuple(fondo))
    return Relleno("color", ((c + (255,))[:4],))


class _BotonColor(QPushButton):
    """Un botón que muestra un color y lo cambia con el selector de color propio."""

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self.setMinimumWidth(90)
        self.clicked.connect(self._elegir)
        self._pintar()

    def _pintar(self) -> None:
        texto = "#000" if self.color.lightness() > 128 else "#fff"
        self.setText(self.color.name())
        self.setStyleSheet(f"background:{self.color.name()}; color:{texto}; border:1px solid #888; "
                           "border-radius:6px; padding:4px 10px;")

    def _elegir(self) -> None:
        from .selector_color import elegir_color
        c = self.color
        elegido = elegir_color(self, (c.red(), c.green(), c.blue(), 255), "Elegir color", alfa=False)
        if elegido is not None:
            self.color = QColor(*elegido[:3])
            self._pintar()


class DialogoNuevo(QDialog):
    """"Nuevo": tamaños listos o personalizado, y el fondo (blanco, negro, transparente, un color o
    un degradado)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nuevo documento")
        self.combo = QComboBox()
        for nombre, _w, _h in TAMANOS:
            self.combo.addItem(nombre)
        self.ancho = QSpinBox()
        self.alto = QSpinBox()
        for s in (self.ancho, self.alto):
            s.setRange(16, LADO_MAX_LIENZO)
            s.setSuffix(" px")
        self.ancho.setValue(1080)
        self.alto.setValue(1080)
        self.combo.currentIndexChanged.connect(self._al_elegir)

        self.blanco = QRadioButton("Blanco")
        self.negro = QRadioButton("Negro")
        self.transparente = QRadioButton("Transparente")
        self.otro = QRadioButton("Color:")
        self.degradado = QRadioButton("Degradado:")
        self.blanco.setChecked(True)
        grupo = QButtonGroup(self)
        for b in (self.blanco, self.negro, self.transparente, self.otro, self.degradado):
            grupo.addButton(b)
        self.boton_color = _BotonColor(QColor("#e91e63"))
        self.boton_color.clicked.connect(lambda: self.otro.setChecked(True))
        self.boton_degradado_1 = _BotonColor(QColor("#7c3aed"))
        self.boton_degradado_2 = _BotonColor(QColor("#ec4899"))
        for b in (self.boton_degradado_1, self.boton_degradado_2):
            b.clicked.connect(lambda: self.degradado.setChecked(True))
        fila_color = QVBoxLayout()
        fila_1 = QHBoxLayout()
        for w in (self.blanco, self.negro, self.transparente):
            fila_1.addWidget(w)
        fila_1.addStretch(1)
        fila_2 = QHBoxLayout()
        for w in (self.otro, self.boton_color):
            fila_2.addWidget(w)
        fila_2.addStretch(1)
        fila_3 = QHBoxLayout()
        for w in (self.degradado, self.boton_degradado_1, self.boton_degradado_2):
            fila_3.addWidget(w)
        fila_3.addStretch(1)
        for f in (fila_1, fila_2, fila_3):
            fila_color.addLayout(f)

        forma = QFormLayout()
        forma.addRow("Tamaño", self.combo)
        forma.addRow("Ancho", self.ancho)
        forma.addRow("Alto", self.alto)
        forma.addRow("Fondo", fila_color)
        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.button(QDialogButtonBox.Ok).setText("Crear")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        caja = QVBoxLayout(self)
        caja.addLayout(forma)
        caja.addWidget(botones)
        self._al_elegir(0)

    def _al_elegir(self, indice: int) -> None:
        _n, w, h = TAMANOS[indice]
        personalizado = w == 0
        self.ancho.setEnabled(personalizado)
        self.alto.setEnabled(personalizado)
        if not personalizado:
            self.ancho.setValue(w)
            self.alto.setValue(h)

    def valores(self) -> tuple[int, int, Optional[tuple[int, int, int]]]:
        """(ancho, alto, color): el color del fondo, o None si es transparente o un degradado (ver
        ``relleno``)."""
        if self.blanco.isChecked():
            color = (255, 255, 255)
        elif self.negro.isChecked():
            color = (0, 0, 0)
        elif self.otro.isChecked():
            c = self.boton_color.color
            color = (c.red(), c.green(), c.blue())
        else:
            color = None
        return self.ancho.value(), self.alto.value(), color

    def relleno(self):
        """El fondo como ``formas.Relleno``: un color, ninguno (transparente) o un degradado lineal de
        arriba hacia abajo con los dos colores elegidos."""
        from ..motor.formas import Relleno
        if self.transparente.isChecked():
            return Relleno("ninguno")
        if self.degradado.isChecked():
            a, b = self.boton_degradado_1.color, self.boton_degradado_2.color
            return Relleno("lineal", ((a.red(), a.green(), a.blue(), 255), (b.red(), b.green(), b.blue(), 255)),
                           (), 90.0)
        return relleno_de_fondo(self.valores()[2])


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------

def datos_texto_por_defecto() -> dict:
    return {"texto": "Tu texto", "fuente": "Arial", "tamano": 120, "color": (255, 255, 255),
            "negrita": True, "alineacion": "centro", "sombra": True}


def nombre_texto(texto: str, palabras: int = 4) -> str:
    """"Texto: <primeras palabras>"."""
    partes = str(texto).split()
    corto = " ".join(partes[:palabras]) + ("…" if len(partes) > palabras else "")
    return f"Texto: {corto or '(vacío)'}"


def dibujar_texto(datos: dict) -> np.ndarray:
    """El texto en un RGBA uint8 del tamaño justo (con margen y, si se pide, sombra), fondo transparente."""
    texto = str(datos.get("texto", "")) or " "
    fuente = QFont(str(datos.get("fuente") or "Arial"))
    fuente.setPixelSize(max(4, int(datos.get("tamano", 120))))
    fuente.setBold(bool(datos.get("negrita", False)))
    alineacion = _FLAG_ALINEACION.get(datos.get("alineacion", "centro"), Qt.AlignHCenter)
    metricas = QFontMetrics(fuente)
    caja = metricas.boundingRect(QRect(0, 0, 100000, 100000), int(alineacion | Qt.AlignTop), texto)
    tam = fuente.pixelSize()
    margen = max(4, tam // 6)
    sombra = bool(datos.get("sombra", False))
    desplazamiento = max(2, tam // 16) if sombra else 0
    ancho = caja.width() + 2 * margen + desplazamiento
    alto = caja.height() + 2 * margen + desplazamiento
    imagen = QImage(max(1, ancho), max(1, alto), QImage.Format_ARGB32_Premultiplied)
    imagen.fill(Qt.transparent)
    p = QPainter(imagen)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    p.setFont(fuente)
    rect = QRect(margen, margen, caja.width(), caja.height())
    flags = int(alineacion | Qt.AlignTop)
    if sombra:
        p.setPen(QColor(0, 0, 0, 150))
        p.drawText(rect.translated(desplazamiento, desplazamiento), flags, texto)
    r, g, b = (int(c) for c in tuple(datos.get("color", (255, 255, 255)))[:3])
    p.setPen(QColor(r, g, b))
    p.drawText(rect, flags, texto)
    p.end()
    rgba = imagen.convertToFormat(QImage.Format_RGBA8888)
    h, w = rgba.height(), rgba.width()
    arr = np.frombuffer(rgba.constBits(), np.uint8, count=rgba.bytesPerLine() * h)
    return arr.reshape(h, rgba.bytesPerLine())[:, :w * 4].reshape(h, w, 4).copy()


class DialogoTexto(QDialog):
    """"Agregar texto": texto multilínea, fuente, tamaño, color, negrita, alineación y sombra."""

    def __init__(self, parent=None, datos: Optional[dict] = None):
        super().__init__(parent)
        datos = {**datos_texto_por_defecto(), **(datos or {})}
        self.setWindowTitle("Texto")
        self.texto = QPlainTextEdit(datos["texto"])
        self.texto.setMinimumHeight(90)
        self.fuente = QFontComboBox()
        self.fuente.setCurrentFont(QFont(datos["fuente"]))
        self.tamano = QSpinBox()
        self.tamano.setRange(8, 1500)
        self.tamano.setSuffix(" px")
        self.tamano.setValue(int(datos["tamano"]))
        self.boton_color = _BotonColor(QColor(*datos["color"]))
        self.negrita = QCheckBox("Negrita")
        self.negrita.setChecked(bool(datos["negrita"]))
        self.alineacion = QComboBox()
        for nombre, clave in ALINEACIONES:
            self.alineacion.addItem(nombre, clave)
        self.alineacion.setCurrentIndex(next((i for i, (_n, c) in enumerate(ALINEACIONES)
                                              if c == datos["alineacion"]), 1))
        self.sombra = QCheckBox("Sombra")
        self.sombra.setChecked(bool(datos["sombra"]))
        estilo = QWidget()
        fila = QHBoxLayout(estilo)
        fila.setContentsMargins(0, 0, 0, 0)
        for w in (self.boton_color, self.negrita, self.sombra):
            fila.addWidget(w)
        fila.addStretch(1)

        forma = QFormLayout()
        forma.addRow("Texto", self.texto)
        forma.addRow("Fuente", self.fuente)
        forma.addRow("Tamaño", self.tamano)
        forma.addRow("Alineación", self.alineacion)
        forma.addRow("Color", estilo)
        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.button(QDialogButtonBox.Ok).setText("Listo")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        caja = QVBoxLayout(self)
        caja.addLayout(forma)
        caja.addWidget(botones)
        self.resize(460, 320)

    def datos(self) -> dict:
        c = self.boton_color.color
        return {"texto": self.texto.toPlainText(), "fuente": self.fuente.currentFont().family(),
                "tamano": self.tamano.value(), "color": (c.red(), c.green(), c.blue()),
                "negrita": self.negrita.isChecked(), "alineacion": self.alineacion.currentData(),
                "sombra": self.sombra.isChecked()}


# ---------------------------------------------------------------------------
# Quitar fondo
# ---------------------------------------------------------------------------

def quitar_fondo(rgb: np.ndarray, alpha: Optional[np.ndarray] = None) -> np.ndarray:
    """RGBA uint8 con el fondo transparente (``recortar_objeto`` con toda la imagen menos un 3 %).
    Si ya tenía alfa, se respeta (se multiplican). ``ValueError`` si no encontró ningún objeto."""
    from ..motor.seleccion_auto import recortar_objeto
    rgb = np.ascontiguousarray(rgb[..., :3])
    m = MARGEN_FONDO
    mascara = recortar_objeto(rgb, (m, m, 1.0 - m, 1.0 - m))
    a = np.clip(np.asarray(mascara, np.float32), 0.0, 1.0)
    if alpha is not None:
        a = a * (alpha.astype(np.float32) / 255.0)
    if float(a.max(initial=0.0)) < 0.5:
        raise ValueError("no se encontró ningún objeto")
    return np.dstack([rgb, np.clip(a * 255.0 + 0.5, 0, 255).astype(np.uint8)])


__all__ = ["DialogoNuevo", "DialogoTexto", "TAMANOS", "datos_texto_por_defecto", "dibujar_texto", "nombre_texto",
           "quitar_fondo", "relleno_de_fondo"]
