"""Panel de ajustes: preset, intensidad, efectos (presets apilados), secciones del motor y máscaras.

En NaturalShot **Lite** los presets apilados se llaman "Efectos" (las "Capas" son las del modo
Photoshop); en la **PRO** se siguen llamando "Capas", como en su tutorial (``efecto_o_capa``).

Lo que antes se llamaba "Capas" (presets extra apilados encima del base) ahora se llama
"Efectos" en la interfaz: "Capas" son las capas de verdad del documento (``panel_capas``).
Por dentro siguen siendo ``capas`` (``estado["capas"]``, ``FilaCapa``), así las sesiones y
los historiales de antes se siguen leyendo.

Las secciones y sus controles salen de ``motor.parametros.SECCIONES``: agregar un
parámetro allí lo agrega acá sin tocar la interfaz.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QMessageBox,
    QPushButton, QSlider, QSpinBox, QToolButton, QToolTip, QVBoxLayout, QWidget,
)

from ..motor.zonas import FORMAS_LIBRES, Zona
from ..motor import (
    CONTROLES, DESCRIPCIONES_PRESETS, EFECTOS_REGIONALES, GRUPOS_PRESETS, NEUTRO, NOMBRES_EFECTOS,
    NOMBRES_REGIONES, PRESET_PRINCIPAL, PRESETS, REGIONES, SECCIONES, Ajustes, cambios_respecto_de_neutro,
)
from .. import edicion
from . import estilo, iconos, presets_usuario


def efecto_o_capa(efecto: str, capa: str) -> str:
    """El texto de la Lite ("Efecto…") o el de la PRO ("Capa…") para los presets apilados."""
    return efecto if edicion.es_lite() else capa

SIN_EFECTO = "Sin efecto"
MAX_CAPAS = 4
# Zonas que se detectan solas (máscara raster); en el "Dónde" de capas y montaje.
ZONAS_AUTOMATICAS = ("cielo", "piel")


def clave_zona(zona: Optional[Zona]) -> Optional[str]:
    """Opción del "Dónde" que corresponde a una zona (None = toda la foto)."""
    if zona is None:
        return None
    if zona.es_mascara:
        return zona.origen if zona.origen in ZONAS_AUTOMATICAS else "pincel"
    return "poligono" if zona.forma == "lazo" else zona.forma


def titulo(texto: str, nombre_icono: str | None = None, secundario: bool = False) -> QWidget:
    """Título de sección, opcionalmente con un ícono de línea a la izquierda."""
    caja = QWidget()
    fila = QHBoxLayout(caja)
    fila.setContentsMargins(0, 10 if secundario else 4, 0, 0)
    fila.setSpacing(7)
    if nombre_icono:
        icono = QLabel()
        icono.setPixmap(iconos.pixmap(nombre_icono, 18))
        icono.setFixedSize(20, 20)
        fila.addWidget(icono)
    etiqueta = QLabel(texto if secundario else texto.upper())
    etiqueta.setObjectName("tituloGrupo" if secundario else "tituloSeccion")
    fila.addWidget(etiqueta, 1)
    return caja


def todos_los_presets() -> dict[str, Ajustes]:
    return {**PRESETS, **presets_usuario.cargar()}


def llenar_combo_presets(combo: QComboBox, incluir_sin_efecto: bool) -> None:
    actual = combo.currentText()
    combo.blockSignals(True)
    combo.clear()
    combo.setIconSize(QSize(18, 18))
    for grupo in GRUPOS_PRESETS:
        if combo.count():
            combo.insertSeparator(combo.count())
        for nombre in grupo:
            combo.addItem(iconos.icono_preset(nombre), nombre)
            combo.setItemData(combo.count() - 1, DESCRIPCIONES_PRESETS[nombre], Qt.ToolTipRole)
    propios = presets_usuario.cargar()
    if propios:
        combo.insertSeparator(combo.count())
        for nombre in propios:
            combo.addItem(iconos.icono("bookmark-plus"), nombre)
            combo.setItemData(combo.count() - 1, "Preset guardado por vos.", Qt.ToolTipRole)
    if incluir_sin_efecto:
        combo.insertSeparator(combo.count())
        combo.addItem(iconos.icono_preset(SIN_EFECTO), SIN_EFECTO)
    combo.setMaxVisibleItems(40)
    combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(10)
    if actual and combo.findText(actual) >= 0:
        combo.setCurrentText(actual)
    combo.blockSignals(False)


def texto_cambios(ajustes: Ajustes) -> str:
    """'Modifica: Nitidez 45 · Ruido 25 …' con las etiquetas de la interfaz."""
    partes = []
    for campo, valor in cambios_respecto_de_neutro(ajustes):
        c = CONTROLES.get(campo)
        if c is None:
            if campo.startswith("reg_"):
                continue
            nombre = campo.replace("_", " ")
        else:
            nombre = c.etiqueta
        if isinstance(valor, bool):
            partes.append(f"{nombre}: {'sí' if valor else 'no'}")
        elif c is not None and c.tipo == "opcion":
            partes.append(f"{nombre}: {c.opciones[valor]}")
        else:
            partes.append(f"{nombre} {valor:+d}" if c is not None and c.minimo < 0 else f"{nombre} {valor}")
    return "Modifica: " + " · ".join(partes) if partes else "No modifica nada."


class ControlDeslizante(QWidget):
    """Deslizador con valor numérico editable y botón para apagar solo este efecto."""

    valorCambiado = Signal(str, int)

    def __init__(self, campo: str, etiqueta: str, minimo: int, maximo: int, ayuda: str,
                 apagable: bool = False, parent=None):
        super().__init__(parent)
        self.campo = campo
        self._predeterminado = 0
        self._guardado = 0  # valor antes de apagarlo
        self.setToolTip(ayuda)

        self._nombre = QLabel(etiqueta)
        self._nombre.setObjectName("etiquetaControl")
        self._nombre.setWordWrap(True)
        self.numero = QSpinBox()
        self.numero.setRange(minimo, maximo)
        self.numero.setObjectName("valorControl")
        self.numero.setButtonSymbols(QSpinBox.NoButtons)
        self.numero.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.numero.setFixedWidth(46)
        self.numero.setToolTip("Escribí un valor exacto")

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(minimo, maximo)
        self.slider.setPageStep(5)
        self.slider.setToolTip(ayuda + "\nDoble clic en el nombre para volver al valor del preset.")
        self.slider.valueChanged.connect(self._al_mover)
        self.numero.valueChanged.connect(self._al_escribir)

        fila = QHBoxLayout()
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(4)
        fila.addWidget(self._nombre, 1)
        self.boton_activo = None
        if apagable:
            self.boton_activo = QToolButton()
            self.boton_activo.setObjectName("botonActivo")
            self.boton_activo.setCheckable(True)
            self.boton_activo.setChecked(True)
            self.boton_activo.setAutoRaise(True)
            self.boton_activo.setIconSize(QSize(15, 15))
            self.boton_activo.setToolTip("Activar o desactivar solo este efecto")
            self.boton_activo.toggled.connect(self._al_alternar)
            self._icono_activo(True)
            fila.addWidget(self.boton_activo)
        fila.addWidget(self.numero)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 2, 0, 2)
        capa.setSpacing(2)
        capa.addLayout(fila)
        capa.addWidget(self.slider)

    def _icono_activo(self, activo: bool) -> None:
        if self.boton_activo is not None:
            self.boton_activo.setIcon(iconos.icono("eye" if activo else "eye-off", 15))

    def _al_mover(self, valor: int) -> None:
        self.numero.blockSignals(True)
        self.numero.setValue(valor)
        self.numero.blockSignals(False)
        if valor and self.boton_activo is not None and not self.boton_activo.isChecked():
            self.boton_activo.blockSignals(True)
            self.boton_activo.setChecked(True)
            self.boton_activo.blockSignals(False)
            self._icono_activo(True)
        self.valorCambiado.emit(self.campo, valor)

    def _al_escribir(self, valor: int) -> None:
        self.slider.setValue(valor)

    def _al_alternar(self, activo: bool) -> None:
        self._icono_activo(activo)
        if activo:
            self.slider.setValue(self._guardado or self._predeterminado)
        else:
            self._guardado = self.slider.value()
            self.slider.blockSignals(True)
            self.slider.setValue(0)
            self.slider.blockSignals(False)
            self.numero.blockSignals(True)
            self.numero.setValue(0)
            self.numero.blockSignals(False)
            self.valorCambiado.emit(self.campo, 0)

    def valor(self) -> int:
        return self.slider.value()

    def establecer(self, valor: int, predeterminado: int | None = None) -> None:
        if predeterminado is not None:
            self._predeterminado = predeterminado
        for w in (self.slider, self.numero):
            w.blockSignals(True)
            w.setValue(int(valor))
            w.blockSignals(False)
        if self.boton_activo is not None:
            self.boton_activo.blockSignals(True)
            self.boton_activo.setChecked(True)
            self.boton_activo.blockSignals(False)
            self._icono_activo(True)

    def mouseDoubleClickEvent(self, _evento) -> None:
        self.slider.setValue(self._predeterminado)


class FilaCapa(QFrame):
    """Un efecto: otro preset aplicado encima, con su propia intensidad (en la interfaz, "Efecto N")."""

    cambiada = Signal()
    eliminar = Signal(object)
    pedirZona = Signal(object, str)  # (fila, forma): hay que dibujar la zona en la foto

    FORMAS_ZONA = (("Toda la foto", None), ("Rectángulo", "rect"), ("Elipse", "elipse"),
                   ("Lazo poligonal", "poligono"), ("Pincel", "pincel"),
                   ("Cielo (automático)", "cielo"), ("Piel (automática)", "piel"))
    ICONOS_ZONA = {None: "scan", "rect": "square-dashed", "elipse": "circle-dashed",
                   "lazo": "lasso", "poligono": "pentagon", "pincel": "brush",
                   "cielo": "cloud-sun", "piel": "hand"}
    AYUDA_ZONA = {
        "rect": "Arrastrá sobre la foto para marcar un rectángulo.",
        "elipse": "Arrastrá sobre la foto para marcar una elipse.",
        "lazo": "Mantené apretado y dibujá el contorno; al soltar, la forma se cierra sola.",
        "poligono": "Hacé clic punto por punto. Cerrá con doble clic, Enter o tocando el primer punto. "
                    "Retroceso borra el último punto.",
        "pincel": "Pintá a mano dónde se aplica. Clic derecho o la goma borran; Enter o Listo terminan. "
                  "Con la mira volvés a pintar encima de lo que ya pintaste.",
        "cielo": "Detecta el cielo solo (azul, nublado o blanco). Después podés corregirlo con el pincel "
                 "(botón de la mira).",
        "piel": "Detecta la piel sola, por color. Madera o arena pueden entrar: corregilo con el pincel "
                "(botón de la mira).",
    }

    def __init__(self, numero: int, preset: str, intensidad: int = 50, parent=None,
                 zona: Optional[Zona] = None):
        super().__init__(parent)
        self.setObjectName("filaCapa")
        self.numero = numero
        self.zona: Optional[Zona] = None
        capa = QVBoxLayout(self)
        capa.setContentsMargins(10, 8, 8, 10)
        capa.setSpacing(6)

        arriba = QHBoxLayout()
        arriba.setSpacing(6)
        self.etiqueta = QLabel(f"{efecto_o_capa('Efecto', 'Capa')} {numero}")
        self.etiqueta.setObjectName("etiquetaCapa")
        self.boton_quitar = QPushButton()
        self.boton_quitar.setIcon(iconos.icono("x", 16))
        self.boton_quitar.setObjectName("botonQuitar")
        self.boton_quitar.setFixedSize(24, 24)
        self.boton_quitar.setToolTip(efecto_o_capa("Quitar este efecto", "Quitar esta capa"))
        self.boton_quitar.clicked.connect(lambda: self.eliminar.emit(self))
        arriba.addWidget(self.etiqueta, 1)
        arriba.addWidget(self.boton_quitar)
        capa.addLayout(arriba)

        self.combo = QComboBox()
        llenar_combo_presets(self.combo, incluir_sin_efecto=False)
        self.combo.setCurrentText(preset)
        self.combo.currentTextChanged.connect(lambda _t: self._al_cambiar_preset())
        capa.addWidget(self.combo)

        self.intensidad = ControlDeslizante(
            "intensidad", efecto_o_capa("Intensidad del efecto", "Intensidad de la capa"), 0, 100,
            "Cuánto se aplica este preset encima de lo anterior.",
        )
        self.intensidad.establecer(intensidad, 50)
        self.intensidad.valorCambiado.connect(lambda *_: self.cambiada.emit())
        capa.addWidget(self.intensidad)

        # ---- Zona: dónde se aplica la capa
        fila_zona = QHBoxLayout()
        fila_zona.setSpacing(6)
        etiqueta_zona = QLabel("Dónde")
        etiqueta_zona.setObjectName("etiquetaControl")
        self.combo_zona = QComboBox()
        for texto, forma in self.FORMAS_ZONA:
            self.combo_zona.addItem(iconos.icono(self.ICONOS_ZONA[forma], 16), texto, forma)
            if forma:
                self.combo_zona.setItemData(self.combo_zona.count() - 1, self.AYUDA_ZONA[forma], Qt.ToolTipRole)
        self.combo_zona.setToolTip(efecto_o_capa("Aplicar el efecto", "Aplicar la capa")
                                   + " a toda la foto o solo a una parte que marcás vos")
        self.combo_zona.currentIndexChanged.connect(self._al_cambiar_forma)
        self.boton_marcar = QPushButton()
        self.boton_marcar.setIcon(iconos.icono("crosshair", 16))
        self.boton_marcar.setFixedWidth(34)
        self.boton_marcar.setToolTip("Volver a marcar la zona en la foto (con el pincel: seguir pintando)")
        self.boton_marcar.clicked.connect(self._volver_a_marcar)
        fila_zona.addWidget(etiqueta_zona)
        fila_zona.addWidget(self.combo_zona, 1)
        fila_zona.addWidget(self.boton_marcar)
        capa.addLayout(fila_zona)

        self.opciones_zona = QWidget()
        capa_op = QVBoxLayout(self.opciones_zona)
        capa_op.setContentsMargins(0, 0, 0, 0)
        capa_op.setSpacing(4)
        self.pluma = ControlDeslizante("pluma", "Borde suave", 0, 100,
                                       "Qué tan gradual es el paso entre la zona y el resto de la foto.")
        self.pluma.establecer(35, 35)
        self.pluma.valorCambiado.connect(lambda *_: self._actualizar_zona())
        self.check_invertir = QCheckBox("Invertir (todo menos la zona)")
        self.check_invertir.toggled.connect(lambda _v: self._actualizar_zona())
        capa_op.addWidget(self.pluma)
        capa_op.addWidget(self.check_invertir)
        capa.addWidget(self.opciones_zona)
        self._mostrar_opciones_zona()
        if zona is not None:
            self.establecer_zona(zona, emitir=False)
        self._al_cambiar_preset(emitir=False)

    # ---------------------------------------------------------------- zona
    def _mostrar_opciones_zona(self) -> None:
        tiene = self.zona is not None
        self.opciones_zona.setVisible(tiene)
        # El borde de lo pintado (o de una máscara automática) no sale del "Borde suave".
        self.pluma.setVisible(tiene and not self.zona.es_raster)
        forma = self.combo_zona.currentData()
        self.boton_marcar.setVisible(forma is not None)
        self.boton_marcar.setToolTip(
            "Corregir la zona con el pincel: pintá para sumar y usá la goma o el clic derecho para restar"
            if forma in ZONAS_AUTOMATICAS else
            "Volver a marcar la zona en la foto (con el pincel: seguir pintando)")

    def _volver_a_marcar(self) -> None:
        forma = self.combo_zona.currentData() or "rect"
        # Una zona automática se corrige con el pincel, encima de lo detectado.
        self.pedirZona.emit(self, "pincel" if forma in ZONAS_AUTOMATICAS else forma)

    def _al_cambiar_forma(self, _i: int) -> None:
        forma = self.combo_zona.currentData()
        if forma is None:
            self.zona = None
            self._mostrar_opciones_zona()
            self.cambiada.emit()
        elif forma in ZONAS_AUTOMATICAS:
            # Se detecta en segundo plano; la ventana avisa con "Detectando…".
            self._mostrar_opciones_zona()
            if not (self.zona is not None and self.zona.es_mascara and self.zona.origen == forma):
                self.pedirZona.emit(self, forma)
        elif (self.zona is not None and forma != "pincel"
              and (forma not in FORMAS_LIBRES or self.zona.puntos)):
            # Rectángulo <-> elipse <-> lazo con puntos: se reutiliza lo marcado
            # (de una zona pintada o automática queda el rectángulo que la abarca).
            libre = forma in FORMAS_LIBRES
            self.zona = replace(self.zona, forma=forma, puntos=self.zona.puntos if libre else (), trazos=(),
                                datos=b"", matriz=(), origen="")
            self._mostrar_opciones_zona()
            self.cambiada.emit()
        else:
            self._mostrar_opciones_zona()
            self.pedirZona.emit(self, forma)

    def _actualizar_zona(self) -> None:
        if self.zona is None:
            return
        self.zona = replace(self.zona, pluma=self.pluma.valor(), invertir=self.check_invertir.isChecked())
        self.cambiada.emit()

    def establecer_zona(self, zona: Optional[Zona], emitir: bool = True) -> None:
        """Fija la zona (dibujada en la foto o restaurada del historial)."""
        if zona is not None:
            zona = replace(zona, pluma=zona.pluma, invertir=zona.invertir)
        self.zona = zona
        for w in (self.combo_zona, self.check_invertir):
            w.blockSignals(True)
        formas = [f for _t, f in self.FORMAS_ZONA]
        forma = clave_zona(zona)
        indice = 0 if zona is None else formas.index(forma) if forma in formas else 1
        self.combo_zona.setCurrentIndex(indice)
        if zona is not None:
            self.check_invertir.setChecked(zona.invertir)
            self.pluma.establecer(zona.pluma, 35)
        for w in (self.combo_zona, self.check_invertir):
            w.blockSignals(False)
        self._mostrar_opciones_zona()
        if emitir:
            self.cambiada.emit()

    def zona_cancelada(self) -> None:
        """Se canceló el dibujo: vuelve a mostrar la zona que había ('Toda la foto' si no había)."""
        self.establecer_zona(self.zona, emitir=False)

    def _al_cambiar_preset(self, emitir: bool = True) -> None:
        nombre = self.combo.currentText()
        self.combo.setToolTip(DESCRIPCIONES_PRESETS.get(nombre, "") + "\n\n" + texto_cambios(
            todos_los_presets().get(nombre, NEUTRO)))
        if emitir:
            self.cambiada.emit()

    @property
    def nombre(self) -> str:
        return f"{efecto_o_capa('Efecto', 'Capa')} {self.numero}"

    def renumerar(self, numero: int) -> None:
        self.numero = numero
        self.etiqueta.setText(f"{efecto_o_capa('Efecto', 'Capa')} {numero}")

    def ajustes(self) -> Ajustes:
        base = todos_los_presets().get(self.combo.currentText(), NEUTRO)
        return replace(base, intensidad=self.intensidad.valor())


# Color de la etiqueta de cada sección y una línea que explica qué hace.
COLOR_SECCION = {
    "Preset": "#d946ef",
    "Efectos": "#a78bfa",
    "Capas": "#a78bfa",  # los presets apilados de la PRO (el panel Capas de la Lite pasa su color)
    "Sensor": "#e879f9",
    "Óptica": "#a78bfa",
    "Detalles": "#60a5fa",
    "Texturas": "#22d3ee",
    "Iluminación": "#fbbf24",
    "Color": "#f472b6",
    "Grano": "#fb923c",
    "Compresión": "#34d399",
    "Máscaras por región": "#f87171",
    "Historial": "#94a3b8",
    "Montaje": "#38bdf8",
    "Fondo": "#a3e635",
    "Borrar objetos": "#5eead4",
}
SUBTITULO_SECCION = {
    "Preset": "El punto de partida del look",
    "Efectos": "Presets extra apilados encima",
    "Capas": "Presets extra apilados encima",
    "Sensor": "Ruido real de la cámara",
    "Óptica": "Lente, viñeteo y aberración",
    "Detalles": "Nitidez y microcontraste",
    "Texturas": "Suavizado y piel",
    "Iluminación": "Luces, sombras y rango",
    "Color": "Balance de blancos y saturación",
    "Grano": "Grano fotográfico",
    "Compresión": "JPEG y reescalado",
    "Máscaras por región": "Cada efecto según la zona",
    "Historial": "Tocá un paso para volver ahí",
    "Montaje": "Partes de otra foto encima de esta",
    "Fondo": "Transparente o desenfocado",
    "Borrar objetos": "Quitá cosas de la foto",
}


class Interruptor(QCheckBox):
    """Interruptor tipo celular. Es un QCheckBox: se usa igual (toggled, setChecked)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(38, 22)

    def sizeHint(self) -> QSize:
        return QSize(38, 22)

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pista = QRectF(1, 2, 36, 18)
        if self.isChecked():
            grad = QLinearGradient(pista.topLeft(), pista.topRight())
            grad.setColorAt(0, QColor(estilo.MAGENTA))
            grad.setColorAt(1, QColor(estilo.VIOLETA))
            p.setBrush(grad)
            p.setPen(Qt.NoPen)
        else:
            p.setBrush(QColor("#3d4047"))
            p.setPen(QPen(QColor("#4b4e56"), 1))
        if not self.isEnabled():
            p.setOpacity(0.45)
        p.drawRoundedRect(pista, 9, 9)
        x = pista.right() - 16 if self.isChecked() else pista.left() + 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff") if self.isChecked() else QColor("#8e8a99"))
        p.drawEllipse(QRectF(x, pista.top() + 2, 14, 14))
        p.end()


class _Cabecera(QFrame):
    clic = Signal()

    def mousePressEvent(self, evento) -> None:
        if evento.button() == Qt.LeftButton:
            self.clic.emit()
        super().mousePressEvent(evento)


class SeccionPlegable(QFrame):
    """Tarjeta de una sección: etiqueta de color con ícono, nombre, descripción corta,
    interruptor para activarla y flecha para abrir o cerrar sus controles."""

    def __init__(self, nombre: str, icono: str, descripcion: str, abierta: bool,
                 parent=None, con_interruptor: bool = True, plegable: bool = True,
                 color: Optional[str] = None, subtitulo: Optional[str] = None):
        """``color`` y ``subtitulo``: si no vienen, los de ``COLOR_SECCION`` y ``SUBTITULO_SECCION``."""
        super().__init__(parent)
        self.setObjectName("tarjetaSeccion")
        color = color or COLOR_SECCION.get(nombre, estilo.MAGENTA)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(0)

        self.cabecera = _Cabecera()
        self.cabecera.setObjectName("cabeceraSeccion")
        self.cabecera.setToolTip(descripcion)
        if plegable:
            self.cabecera.setCursor(Qt.PointingHandCursor)
        fila = QHBoxLayout(self.cabecera)
        fila.setContentsMargins(10, 9, 10, 9)
        fila.setSpacing(10)

        insignia = QLabel()
        insignia.setFixedSize(30, 30)
        insignia.setAlignment(Qt.AlignCenter)
        c = QColor(color)
        insignia.setStyleSheet(
            f"background: rgba({c.red()}, {c.green()}, {c.blue()}, 38); border-radius: 9px;"
        )
        insignia.setPixmap(iconos.pixmap(icono, 17, color))
        fila.addWidget(insignia)

        textos = QVBoxLayout()
        textos.setSpacing(0)
        self.titulo = QLabel(nombre)
        self.titulo.setObjectName("tituloCaja")
        subtitulo = QLabel(subtitulo if subtitulo is not None else SUBTITULO_SECCION.get(nombre, ""))
        subtitulo.setObjectName("subtituloCaja")
        textos.addWidget(self.titulo)
        if subtitulo.text():
            textos.addWidget(subtitulo)
        fila.addLayout(textos, 1)

        self.interruptor = Interruptor()
        self.interruptor.setToolTip("Activar o desactivar toda la sección sin perder sus valores")
        fila.addWidget(self.interruptor)
        # Recién con padre: setVisible(True) en un widget suelto crea (y muestra) una ventana nativa.
        self.interruptor.setVisible(con_interruptor)

        self.boton = QToolButton()
        self.boton.setObjectName("chevron")
        self.boton.setCheckable(True)
        self.boton.setChecked(abierta)
        self.boton.setIconSize(QSize(16, 16))
        self.boton.setToolTip("Mostrar u ocultar los controles")
        self.boton.toggled.connect(self._alternar)
        fila.addWidget(self.boton)
        self.boton.setVisible(plegable)
        if plegable:
            self.cabecera.clic.connect(self.boton.toggle)
        capa.addWidget(self.cabecera)

        self.cuerpo = QFrame()
        self.cuerpo.setObjectName("cuerpoSeccion")
        self.capa_cuerpo = QVBoxLayout(self.cuerpo)
        self.capa_cuerpo.setContentsMargins(12, 8, 12, 12)
        self.capa_cuerpo.setSpacing(6)
        capa.addWidget(self.cuerpo)
        self._alternar(abierta if plegable else True)

    def _alternar(self, abierta: bool) -> None:
        self.cuerpo.setVisible(abierta)
        self.boton.setIcon(iconos.icono("chevron-down" if abierta else "chevron-right", 16))
        self.setProperty("abierta", abierta)
        self.style().unpolish(self)
        self.style().polish(self)


class PanelAjustes(QWidget):
    ajustesCambiados = Signal(object)  # tuple[Ajustes, ...] (pila de capas)
    pedirZona = Signal(object, str)  # una capa necesita que se dibuje su zona en la foto

    def __init__(self, parent=None):
        super().__init__(parent)
        self._preset = PRESET_PRINCIPAL
        self._ajustes: Ajustes = PRESETS[self._preset]
        self._controles: dict[str, ControlDeslizante] = {}
        self._booleanos: dict[str, QCheckBox] = {}
        self._opciones: dict[str, QComboBox] = {}
        self._regionales: dict[str, QSpinBox] = {}
        self._capas: list[FilaCapa] = []
        self._cargando = False

        # Dos columnas al estilo Photoshop: a la izquierda preset y capas
        # (``lado_presets``), a la derecha los ajustes finos (``lado_ajustes``).
        self.lado_presets = QWidget()
        capa = QVBoxLayout(self.lado_presets)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(10)
        capa_izq = capa
        self.lado_ajustes = QWidget()
        capa_ajustes = QVBoxLayout(self.lado_ajustes)
        capa_ajustes.setContentsMargins(0, 0, 0, 0)
        capa_ajustes.setSpacing(8)

        # ---- Preset base
        tarjeta = SeccionPlegable("Preset", iconos.PRESET, "Elegí el look base", True,
                                  con_interruptor=False, plegable=False)
        capa_izq.addWidget(tarjeta)
        capa = tarjeta.capa_cuerpo
        self.combo_preset = QComboBox()
        llenar_combo_presets(self.combo_preset, incluir_sin_efecto=True)
        self.combo_preset.setCurrentText(self._preset)
        self.combo_preset.currentTextChanged.connect(self._al_elegir_preset)
        # Al lado del selector, un (i): la descripción y lo que cambia van en su ayuda
        # en vez de ocupar un párrafo fijo en el panel.
        self.info_preset = QToolButton()
        self.info_preset.setObjectName("botonInfo")
        self.info_preset.setIcon(iconos.icono("info", 17))
        self.info_preset.setIconSize(QSize(17, 17))
        self.info_preset.setFixedSize(30, 30)
        self.info_preset.setCursor(Qt.PointingHandCursor)
        self.info_preset.clicked.connect(
            lambda: QToolTip.showText(self.info_preset.mapToGlobal(self.info_preset.rect().bottomLeft()),
                                      self.info_preset.toolTip(), self.info_preset))
        # El (i) va en la esquina de la cabecera de la tarjeta: el selector conserva todo el ancho.
        tarjeta.cabecera.layout().addWidget(self.info_preset)
        capa.addWidget(self.combo_preset)

        fila_presets = QHBoxLayout()
        fila_presets.setSpacing(6)
        self.boton_guardar_preset = QPushButton(" Guardar como preset")
        self.boton_guardar_preset.setIcon(iconos.icono("bookmark-plus", 16))
        self.boton_guardar_preset.setToolTip("Guarda todos los valores actuales como un preset propio")
        self.boton_guardar_preset.clicked.connect(self.guardar_preset)
        self.boton_borrar_preset = QPushButton()
        self.boton_borrar_preset.setIcon(iconos.icono("trash-2", 16))
        self.boton_borrar_preset.setToolTip("Borrar este preset propio")
        self.boton_borrar_preset.setFixedWidth(36)
        self.boton_borrar_preset.clicked.connect(self.borrar_preset)
        fila_presets.addWidget(self.boton_guardar_preset, 1)
        fila_presets.addWidget(self.boton_borrar_preset)
        capa.addLayout(fila_presets)

        # Una sola línea, y solo cuando se tocaron los valores del preset.
        self.estado_preset = QLabel("")
        self.estado_preset.setObjectName("notaModificado")
        capa.addWidget(self.estado_preset)

        self.intensidad = ControlDeslizante(
            "intensidad", "Intensidad general", 0, 100,
            "Escala todos los efectos del preset base. 0 = sin tratamiento base.",
        )
        self.intensidad.valorCambiado.connect(self._al_cambiar_valor)
        self._controles["intensidad"] = self.intensidad
        capa.addWidget(self.intensidad)

        fila_semilla = QHBoxLayout()
        etiqueta_semilla = QLabel("Semilla del ruido y el grano")
        etiqueta_semilla.setObjectName("etiquetaControl")
        etiqueta_semilla.setToolTip(CONTROLES["semilla"].ayuda)
        self.semilla = QSpinBox()
        self.semilla.setRange(0, 9999)
        self.semilla.setToolTip(CONTROLES["semilla"].ayuda)
        self.semilla.valueChanged.connect(lambda v: self._al_cambiar_valor("semilla", v))
        fila_semilla.addWidget(etiqueta_semilla, 1)
        fila_semilla.addWidget(self.semilla)
        capa.addLayout(fila_semilla)

        # ---- Efectos (presets extra apilados; en la PRO siguen siendo "Capas")
        tarjeta = SeccionPlegable(efecto_o_capa("Efectos", "Capas"), efecto_o_capa(iconos.EFECTOS, iconos.CAPAS),
                                  "Presets extra encima del base", True,
                                  con_interruptor=False, plegable=False)
        capa_izq.addWidget(tarjeta)
        capa = tarjeta.capa_cuerpo
        nota_capas = QLabel("Sumá otros presets encima del base. Se aplican en orden, de arriba hacia abajo.")
        nota_capas.setObjectName("nota")
        nota_capas.setWordWrap(True)
        capa.addWidget(nota_capas)
        self.contenedor_capas = QVBoxLayout()
        self.contenedor_capas.setSpacing(8)
        capa.addLayout(self.contenedor_capas)
        self.boton_agregar_capa = QPushButton(efecto_o_capa(" Agregar efecto", " Agregar capa"))
        self.boton_agregar_capa.setIcon(iconos.icono("plus", 16))
        self.boton_agregar_capa.setObjectName("botonAgregarCapa")
        self.boton_agregar_capa.setToolTip(f"Hasta {MAX_CAPAS} {efecto_o_capa('efectos', 'capas')} encima del preset base.")
        self.boton_agregar_capa.clicked.connect(lambda: self.agregar_capa())
        capa.addWidget(self.boton_agregar_capa)


        # ---- Secciones del motor (columna derecha)
        capa = capa_ajustes
        self._secciones: dict[str, SeccionPlegable] = {}
        for i, sec in enumerate(SECCIONES):
            caja = SeccionPlegable(sec.nombre, sec.icono, sec.descripcion, abierta=i == 0)
            if sec.interruptor:
                caja.interruptor.toggled.connect(lambda v, c=sec.interruptor: self._al_cambiar_bool(c, v))
                self._booleanos[sec.interruptor] = caja.interruptor
            for c in sec.controles:
                if c.tipo == "booleano":
                    w = QCheckBox(c.etiqueta)
                    w.setToolTip(c.ayuda)
                    w.toggled.connect(lambda v, campo=c.campo: self._al_cambiar_bool(campo, v))
                    self._booleanos[c.campo] = w
                elif c.tipo == "opcion":
                    w = QWidget()
                    f = QHBoxLayout(w)
                    f.setContentsMargins(0, 2, 0, 2)
                    et = QLabel(c.etiqueta)
                    et.setObjectName("etiquetaControl")
                    combo = QComboBox()
                    combo.addItems(c.opciones)
                    combo.setToolTip(c.ayuda)
                    combo.currentIndexChanged.connect(lambda v, campo=c.campo: self._al_cambiar_valor(campo, v))
                    f.addWidget(et, 1)
                    f.addWidget(combo)
                    self._opciones[c.campo] = combo
                else:
                    w = ControlDeslizante(c.campo, c.etiqueta, c.minimo, c.maximo, c.ayuda, apagable=c.efecto)
                    w.valorCambiado.connect(self._al_cambiar_valor)
                    self._controles[c.campo] = w
                caja.capa_cuerpo.addWidget(w)
            self._secciones[sec.nombre] = caja
            capa.addWidget(caja)

        # ---- Máscaras regionales
        caja = SeccionPlegable("Máscaras por región", "scan-face",
                               "Cada región recibe su propia cantidad de cada efecto (100 % = normal).", abierta=False)
        caja.interruptor.toggled.connect(lambda v: self._al_cambiar_bool("regiones_activas", v))
        self._booleanos["regiones_activas"] = caja.interruptor
        nota = QLabel("Sin IA: las regiones salen de color, bordes y textura, así que funciona aunque no haya "
                      "personas. La piel por color puede incluir madera o arena. Valores en % del efecto.")
        nota.setObjectName("nota")
        nota.setWordWrap(True)
        caja.capa_cuerpo.addWidget(nota)
        grilla = QGridLayout()
        grilla.setHorizontalSpacing(4)
        grilla.setVerticalSpacing(4)
        for j, ef in enumerate(EFECTOS_REGIONALES):
            et = QLabel(NOMBRES_EFECTOS[ef].replace(" ", "\n", 1))
            et.setObjectName("nota")
            et.setAlignment(Qt.AlignCenter)
            grilla.addWidget(et, 0, j + 1)
        for i, reg in enumerate(REGIONES):
            et = QLabel(NOMBRES_REGIONES[reg])
            et.setObjectName("etiquetaControl")
            et.setWordWrap(True)
            grilla.addWidget(et, i + 1, 0)
            for j, ef in enumerate(EFECTOS_REGIONALES):
                campo = f"reg_{reg}_{ef}"
                sp = QSpinBox()
                sp.setRange(0, 200)
                sp.setSuffix(" %")
                sp.setSingleStep(10)
                sp.setToolTip(f"{NOMBRES_EFECTOS[ef]} en {NOMBRES_REGIONES[reg].lower()}")
                sp.valueChanged.connect(lambda v, c=campo: self._al_cambiar_valor(c, v))
                self._regionales[campo] = sp
                grilla.addWidget(sp, i + 1, j + 1)
        caja.capa_cuerpo.addLayout(grilla)
        self._secciones["Máscaras por región"] = caja
        capa.addWidget(caja)
        capa.addStretch(1)

        # Acordeón: al abrir una sección se cierran las demás.
        for caja in self._secciones.values():
            caja.boton.toggled.connect(lambda abierta, c=caja: abierta and self._abrir_solo(c))

        self.boton_restablecer = QPushButton(" Restablecer ajustes")
        self.boton_restablecer.setIcon(iconos.icono("rotate-ccw", 16))
        self.boton_restablecer.setToolTip(efecto_o_capa("Vuelve a los valores del preset base elegido (los efectos se mantienen).",
                                                        "Vuelve a los valores del preset base elegido (las capas se mantienen)."))
        self.boton_restablecer.clicked.connect(self.restablecer)

        self._cargar_en_controles(self._ajustes, self._ajustes)

    def _abrir_solo(self, abierta: SeccionPlegable) -> None:
        for caja in self._secciones.values():
            if caja is not abierta and caja.boton.isChecked():
                caja.boton.setChecked(False)

    # ------------------------------------------------------------- capas
    def agregar_capa(self, preset: str = "Interior con poca luz", intensidad: int = 50, emitir: bool = True,
                     zona: Optional[Zona] = None) -> None:
        if len(self._capas) >= MAX_CAPAS:
            return
        if not isinstance(preset, str) or preset not in todos_los_presets():
            preset = "Interior con poca luz"
        fila = FilaCapa(len(self._capas) + 1, preset, intensidad, zona=zona)
        fila.pedirZona.connect(self.pedirZona)
        fila.cambiada.connect(self._emitir)
        fila.eliminar.connect(self._quitar_capa)
        self._capas.append(fila)
        self.contenedor_capas.addWidget(fila)
        self.boton_agregar_capa.setEnabled(len(self._capas) < MAX_CAPAS)
        if emitir:
            self._emitir()

    def _quitar_capa(self, fila: FilaCapa, emitir: bool = True) -> None:
        self._capas.remove(fila)
        fila.setParent(None)
        fila.deleteLater()
        for i, f in enumerate(self._capas, start=1):
            f.renumerar(i)
        self.boton_agregar_capa.setEnabled(True)
        if emitir:
            self._emitir()

    # ------------------------------------------------------------ preset
    def _referencia(self) -> Ajustes:
        return todos_los_presets().get(self._preset, replace(NEUTRO))

    def _cargar_en_controles(self, ajustes: Ajustes, referencia: Ajustes) -> None:
        self._cargando = True
        for campo, control in self._controles.items():
            control.establecer(getattr(ajustes, campo), getattr(referencia, campo))
        for campo, w in self._booleanos.items():
            w.blockSignals(True)
            w.setChecked(bool(getattr(ajustes, campo)))
            w.blockSignals(False)
        for campo, w in list(self._opciones.items()) + list(self._regionales.items()):
            w.blockSignals(True)
            w.setCurrentIndex(getattr(ajustes, campo)) if isinstance(w, QComboBox) else w.setValue(getattr(ajustes, campo))
            w.blockSignals(False)
        self.semilla.blockSignals(True)
        self.semilla.setValue(ajustes.semilla)
        self.semilla.blockSignals(False)
        self._habilitar_secciones()
        self._cargando = False
        self._actualizar_estado()

    def _habilitar_secciones(self) -> None:
        for sec in SECCIONES:
            if sec.interruptor:
                activa = bool(getattr(self._ajustes, sec.interruptor))
                for c in sec.controles:
                    w = self._controles.get(c.campo) or self._booleanos.get(c.campo) or self._opciones.get(c.campo)
                    if w is not None:
                        w.setEnabled(activa)
        for w in self._regionales.values():
            w.setEnabled(self._ajustes.regiones_activas)

    def _actualizar_estado(self) -> None:
        propios = presets_usuario.cargar()
        self.boton_borrar_preset.setVisible(self._preset in propios)
        if self._preset in PRESETS or self._preset in propios:
            referencia = replace(self._referencia(), intensidad=self._ajustes.intensidad)
            descripcion = DESCRIPCIONES_PRESETS.get(self._preset, "Preset propio.")
            cambios = texto_cambios(self._referencia())
            self.info_preset.setToolTip(f"<b>{self._preset}</b><br>{descripcion}<br><br>"
                                        f"<span style='color:{estilo.TEXTO_TENUE}'>{cambios}</span>")
            modificado = self._ajustes != referencia
            self.estado_preset.setText("● Modificado respecto del preset")
            self.estado_preset.setVisible(modificado)
        else:
            self.info_preset.setToolTip(efecto_o_capa("Sin tratamiento base. Los efectos, si hay, se siguen aplicando.",
                                                      "Sin tratamiento base. Las capas, si hay, se siguen aplicando."))
            self.estado_preset.setVisible(False)

    def _emitir(self) -> None:
        if self._cargando:
            return
        self._actualizar_estado()
        self.ajustesCambiados.emit(self.pila())

    def _al_cambiar_valor(self, campo: str, valor: int) -> None:
        if self._cargando:
            return
        self._ajustes = replace(self._ajustes, **{campo: int(valor)})
        self._emitir()

    def _al_cambiar_bool(self, campo: str, valor: bool) -> None:
        if self._cargando:
            return
        self._ajustes = replace(self._ajustes, **{campo: bool(valor)})
        self._habilitar_secciones()
        self._emitir()

    def _al_elegir_preset(self, nombre: str) -> None:
        # Al cambiar de preset se conservan la intensidad general y la semilla.
        intensidad, semilla = self._ajustes.intensidad, self._ajustes.semilla
        self._preset = nombre
        self._ajustes = replace(self._referencia(), intensidad=intensidad, semilla=semilla)
        self._cargar_en_controles(self._ajustes, self._referencia())
        self._emitir()

    def restablecer(self) -> None:
        """Vuelve a los valores del preset base elegido, incluida la intensidad."""
        if self._preset == SIN_EFECTO:
            self.combo_preset.setCurrentText(PRESET_PRINCIPAL)  # emite por sí solo
            return
        self._ajustes = self._referencia()
        self._cargar_en_controles(self._ajustes, self._ajustes)
        self._emitir()

    def guardar_preset(self) -> None:
        nombre, ok = QInputDialog.getText(self, "Guardar preset", "Nombre del preset:")
        nombre = (nombre or "").strip()
        if not ok or not nombre:
            return
        if nombre in PRESETS or nombre == SIN_EFECTO:
            QMessageBox.warning(self, "Nombre en uso", "Ese nombre es de un preset incluido. Elegí otro.")
            return
        presets_usuario.guardar(nombre, replace(self._ajustes, intensidad=100))
        self._preset = nombre
        self._refrescar_combos()

    def borrar_preset(self) -> None:
        if self._preset not in presets_usuario.cargar():
            return
        presets_usuario.borrar(self._preset)
        self._preset = PRESET_PRINCIPAL
        self._refrescar_combos()
        self._actualizar_estado()

    def _refrescar_combos(self) -> None:
        llenar_combo_presets(self.combo_preset, incluir_sin_efecto=True)
        self.combo_preset.blockSignals(True)
        self.combo_preset.setCurrentText(self._preset)
        self.combo_preset.blockSignals(False)
        for f in self._capas:
            llenar_combo_presets(f.combo, incluir_sin_efecto=False)
        self._actualizar_estado()

    # -------------------------------------------------------- historial
    def estado(self) -> dict:
        return {
            "preset": self._preset,
            "ajustes": self._ajustes,
            "capas": [(f.combo.currentText(), f.intensidad.valor(), f.zona) for f in self._capas],
        }

    def restaurar(self, estado: dict) -> None:
        self._preset = estado["preset"]
        self._ajustes = estado["ajustes"]
        self.combo_preset.blockSignals(True)
        self.combo_preset.setCurrentText(self._preset)
        self.combo_preset.blockSignals(False)
        for f in list(self._capas):
            self._quitar_capa(f, emitir=False)
        for preset, intensidad, *resto in estado["capas"]:
            self.agregar_capa(preset, intensidad, emitir=False, zona=resto[0] if resto else None)
        self._cargar_en_controles(self._ajustes, self._referencia())
        self._emitir()

    def ajustes(self) -> Ajustes:
        return self._ajustes

    def zonas(self) -> tuple[Optional[Zona], ...]:
        """Zona de cada elemento de la pila (el preset base siempre va a toda la foto)."""
        return (None,) + tuple(f.zona for f in self._capas)

    def capas(self) -> list["FilaCapa"]:
        return list(self._capas)

    def pila(self) -> tuple[Ajustes, ...]:
        """Preset base seguido de las capas, en el orden en que se aplican."""
        return (self._ajustes,) + tuple(f.ajustes() for f in self._capas)


def separador() -> QFrame:
    linea = QFrame()
    linea.setObjectName("separador")
    linea.setFrameShape(QFrame.HLine)
    return linea
