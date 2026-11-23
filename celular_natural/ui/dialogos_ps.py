"""Diálogos del menú Imagen del modo Photoshop (NaturalShot Lite).

* ``DialogoTamanoImagen``: "Tamaño de imagen" (escala todo: ``documento.escalar_imagen``), en
  píxeles o en porcentaje, con la proporción encadenada.
* ``DialogoTamanoLienzo``: "Tamaño del lienzo" (agrega o recorta bordes: ``documento.tamano_lienzo``)
  con el **ancla** de 3 × 3 (dónde queda lo que había) y la opción "relativo" (cuánto se agrega).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QLabel, QPushButton,
    QSpinBox, QVBoxLayout, QWidget,
)

from ..motor.documento import ANCLAS, LADO_MAX

# El orden de la grilla del ancla (fila por fila) y la flecha que muestra cada botón.
_ANCLAS_GRILLA = ("arriba_izquierda", "arriba", "arriba_derecha", "izquierda", "centro", "derecha",
                  "abajo_izquierda", "abajo", "abajo_derecha")
_FLECHAS = {"arriba_izquierda": "↖", "arriba": "↑", "arriba_derecha": "↗", "izquierda": "←", "centro": "●",
            "derecha": "→", "abajo_izquierda": "↙", "abajo": "↓", "abajo_derecha": "↘"}


def _botones(dialogo: QDialog, texto_ok: str) -> QDialogButtonBox:
    botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    botones.button(QDialogButtonBox.Ok).setText(texto_ok)
    botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
    botones.accepted.connect(dialogo.accept)
    botones.rejected.connect(dialogo.reject)
    return botones


def _lado() -> QSpinBox:
    s = QSpinBox()
    s.setRange(1, LADO_MAX)
    s.setSuffix(" px")
    s.setMinimumWidth(110)
    return s


class DialogoTamanoImagen(QDialog):
    """"Imagen › Tamaño de imagen…": el documento entero, escalado."""

    def __init__(self, ancho: int, alto: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tamaño de imagen")
        self._original = (int(ancho), int(alto))
        self._cambiando = False
        self.ancho, self.alto = _lado(), _lado()
        self.ancho.setValue(ancho)
        self.alto.setValue(alto)
        self.unidad = QComboBox()
        self.unidad.addItem("Píxeles", "px")
        self.unidad.addItem("Porcentaje", "%")
        self.unidad.currentIndexChanged.connect(self._al_cambiar_unidad)
        self.proporcion = QCheckBox("Mantener la proporción")
        self.proporcion.setChecked(True)
        self.ancho.valueChanged.connect(lambda _v: self._encadenar("ancho"))
        self.alto.valueChanged.connect(lambda _v: self._encadenar("alto"))
        forma = QFormLayout()
        forma.addRow("Ancho", self.ancho)
        forma.addRow("Alto", self.alto)
        forma.addRow("Unidad", self.unidad)
        forma.addRow("", self.proporcion)
        nota = QLabel(f"Ahora: {ancho} × {alto} px. Escala todas las capas (sus imágenes no se pierden: "
                      "cambia su escala).")
        nota.setObjectName("nota")
        nota.setWordWrap(True)
        caja = QVBoxLayout(self)
        caja.addLayout(forma)
        caja.addWidget(nota)
        caja.addWidget(_botones(self, "Aplicar"))

    def _en_pixeles(self) -> bool:
        return self.unidad.currentData() == "px"

    def _al_cambiar_unidad(self, _i: int) -> None:
        w0, h0 = self._original
        self._cambiando = True
        try:
            for s in (self.ancho, self.alto):
                s.setSuffix(" px" if self._en_pixeles() else " %")
                s.setRange(1, LADO_MAX if self._en_pixeles() else 1000)
            if self._en_pixeles():
                self.ancho.setValue(w0)
                self.alto.setValue(h0)
            else:
                self.ancho.setValue(100)
                self.alto.setValue(100)
        finally:
            self._cambiando = False

    def _encadenar(self, cual: str) -> None:
        if self._cambiando or not self.proporcion.isChecked():
            return
        w0, h0 = self._original
        self._cambiando = True
        try:
            if self._en_pixeles():
                if cual == "ancho":
                    self.alto.setValue(max(1, round(self.ancho.value() * h0 / w0)))
                else:
                    self.ancho.setValue(max(1, round(self.alto.value() * w0 / h0)))
            else:
                (self.alto if cual == "ancho" else self.ancho).setValue((self.ancho if cual == "ancho" else self.alto).value())
        finally:
            self._cambiando = False

    def valores(self) -> tuple[int, int]:
        """(ancho, alto) en píxeles."""
        if self._en_pixeles():
            return self.ancho.value(), self.alto.value()
        w0, h0 = self._original
        return max(1, round(w0 * self.ancho.value() / 100)), max(1, round(h0 * self.alto.value() / 100))


class DialogoTamanoLienzo(QDialog):
    """"Imagen › Tamaño del lienzo…": agrega o recorta bordes, con el ancla de 3 × 3."""

    def __init__(self, ancho: int, alto: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tamaño del lienzo")
        self._original = (int(ancho), int(alto))
        self.ancho, self.alto = _lado(), _lado()
        self.ancho.setValue(ancho)
        self.alto.setValue(alto)
        self.relativo = QCheckBox("Relativo (cuánto se agrega o se quita)")
        self.relativo.toggled.connect(self._al_relativo)
        self.grupo_ancla = QButtonGroup(self)
        self.grupo_ancla.setExclusive(True)
        self.botones_ancla: dict[str, QPushButton] = {}
        grilla = QGridLayout()
        grilla.setSpacing(3)
        for n, clave in enumerate(_ANCLAS_GRILLA):
            b = QPushButton(_FLECHAS[clave])
            b.setCheckable(True)
            b.setFixedSize(34, 30)
            b.setToolTip(f"Lo que había queda: {clave.replace('_', ' ')}")
            b.setChecked(clave == "centro")
            self.grupo_ancla.addButton(b)
            self.botones_ancla[clave] = b
            grilla.addWidget(b, n // 3, n % 3)
        ancla = QWidget()
        ancla.setLayout(grilla)
        forma = QFormLayout()
        forma.addRow("Ancho", self.ancho)
        forma.addRow("Alto", self.alto)
        forma.addRow("", self.relativo)
        forma.addRow("Ancla", ancla)
        nota = QLabel(f"Ahora: {ancho} × {alto} px. Las capas no cambian de tamaño; lo que se agrega queda "
                      "con el fondo.")
        nota.setObjectName("nota")
        nota.setWordWrap(True)
        caja = QVBoxLayout(self)
        caja.addLayout(forma)
        caja.addWidget(nota)
        caja.addWidget(_botones(self, "Aplicar"))

    def _al_relativo(self, relativo: bool) -> None:
        w0, h0 = self._original
        for s, base in ((self.ancho, w0), (self.alto, h0)):
            if relativo:
                s.setRange(-base + 1, LADO_MAX - base)
                s.setValue(0)
            else:
                s.setRange(1, LADO_MAX)
                s.setValue(base)

    @property
    def ancla(self) -> str:
        return next((k for k, b in self.botones_ancla.items() if b.isChecked()), "centro")

    def elegir_ancla(self, clave: str) -> None:
        if clave in self.botones_ancla:
            self.botones_ancla[clave].setChecked(True)

    def valores(self) -> tuple[int, int, str]:
        """(ancho, alto, ancla), en píxeles."""
        w0, h0 = self._original
        if self.relativo.isChecked():
            return max(1, w0 + self.ancho.value()), max(1, h0 + self.alto.value()), self.ancla
        return self.ancho.value(), self.alto.value(), self.ancla


assert set(_ANCLAS_GRILLA) == set(ANCLAS)

__all__ = ["DialogoTamanoImagen", "DialogoTamanoLienzo"]
