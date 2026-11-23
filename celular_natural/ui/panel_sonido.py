"""Tarjeta "Sonido": quitar, volumen, normalizar, fundidos, silencios y guardar el audio.

Va en la columna de ajustes del modo Video, con el mismo estilo que las demás
secciones (``SeccionPlegable``). No guarda estado propio que importe: muestra un
``AjustesAudio`` (``establecer``) y, cuando se toca algo, emite el ajuste nuevo
con ``ajustesCambiados(nuevo, clave)``. Quien lo usa decide (deshacer, vista
previa, exportación) y vuelve a llamar a ``establecer``. ``clave`` dice qué
control cambió, para juntar en un solo paso de deshacer los movimientos seguidos
de un mismo deslizador.

Arriba dice de dónde sale el sonido (``establecer_origen``: "Sonido: el del video",
"Sonido: voz.m4a (desde el principio)"…) y ofrece la ida y vuelta con el modo Audio:
"Editar el sonido en el modo Audio" (``editarEnAudioPedido``), "Cambiar el sonido
por…" (``cambiarSonidoPedido``) y, con un sonido externo, "Volver al original"
(``volverAlOriginalPedido``). La tarjeta solo avisa: lo hace quien la usa.

No depende del editor de video: un futuro modo Audio la puede usar igual
(``mostrar_quitar(False)`` esconde "Quitar el sonido", que ahí no tiene sentido).
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSizePolicy, QSlider, QVBoxLayout,
    QWidget,
)

from ..motor import audio as ma
from . import iconos
from .controles import COLOR_SECCION, SUBTITULO_SECCION, ControlDeslizante, Interruptor, SeccionPlegable
from .linea_tiempo import formato_tiempo
from .panel_mejora import no_ensanchar

COLOR_SECCION.setdefault("Sonido", "#4ade80")
SUBTITULO_SECCION.setdefault("Sonido", "Volumen, fundidos y silencios")
PASOS_SEGUNDO = 10  # los fundidos van de a 0,1 s


class ControlSegundos(QWidget):
    """Deslizador de segundos (de a 0,1) con el valor escrito al lado, como ``ControlDeslizante``.
    Doble clic en el nombre lo vuelve a 0."""

    valorCambiado = Signal(float)

    def __init__(self, etiqueta: str, ayuda: str, parent=None):
        super().__init__(parent)
        self.setToolTip(ayuda)
        self._nombre = QLabel(etiqueta)
        self._nombre.setObjectName("etiquetaControl")
        self.numero = QDoubleSpinBox()
        self.numero.setObjectName("valorControl")
        self.numero.setDecimals(1)
        self.numero.setSingleStep(0.1)
        self.numero.setSuffix(" s")
        self.numero.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.numero.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.numero.setFixedWidth(58)
        self.numero.setToolTip("Escribí un valor exacto")
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setPageStep(5)
        self.slider.setToolTip(ayuda + "\nDoble clic en el nombre para volver a 0.")
        self.slider.valueChanged.connect(lambda v: self._al_mover(v / PASOS_SEGUNDO))
        self.numero.valueChanged.connect(self._al_escribir)
        fila = QHBoxLayout()
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(4)
        fila.addWidget(self._nombre, 1)
        fila.addWidget(self.numero)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 2, 0, 2)
        capa.setSpacing(2)
        capa.addLayout(fila)
        capa.addWidget(self.slider)
        self.establecer_maximo(0.0)

    def _al_mover(self, valor: float) -> None:
        self.numero.blockSignals(True)
        self.numero.setValue(valor)
        self.numero.blockSignals(False)
        self.valorCambiado.emit(round(valor, 1))

    def _al_escribir(self, valor: float) -> None:
        pasos = round(valor * PASOS_SEGUNDO)
        if pasos == self.slider.value():
            self.valorCambiado.emit(round(valor, 1))
        else:
            self.slider.setValue(pasos)

    def establecer_maximo(self, maximo: float) -> None:
        """Hasta dónde llega (se redondea hacia abajo a 0,1 s)."""
        pasos = max(0, int(maximo * PASOS_SEGUNDO + 1e-6))
        for w in (self.slider, self.numero):
            w.blockSignals(True)
        self.slider.setRange(0, pasos)
        self.numero.setRange(0.0, pasos / PASOS_SEGUNDO)
        for w in (self.slider, self.numero):
            w.blockSignals(False)

    def maximo(self) -> float:
        return self.slider.maximum() / PASOS_SEGUNDO

    def valor(self) -> float:
        return self.slider.value() / PASOS_SEGUNDO

    def establecer(self, valor: float) -> None:
        for w in (self.slider, self.numero):
            w.blockSignals(True)
        self.slider.setValue(round(valor * PASOS_SEGUNDO))
        self.numero.setValue(self.slider.value() / PASOS_SEGUNDO)
        for w in (self.slider, self.numero):
            w.blockSignals(False)

    def mouseDoubleClickEvent(self, _evento) -> None:
        self.slider.setValue(0)


class PanelSonido(SeccionPlegable):
    """La tarjeta "Sonido" (ver el docstring del módulo)."""

    ajustesCambiados = Signal(object, str)   # AjustesAudio nuevo y qué control cambió
    guardarAudioPedido = Signal()            # "Guardar solo el audio…"
    cancelarGuardadoPedido = Signal()        # Cancelar lo que esté guardando (también el sonido para el modo Audio)
    editarEnAudioPedido = Signal()           # "Editar el sonido en el modo Audio"
    cambiarSonidoPedido = Signal()           # "Cambiar el sonido por…"
    volverAlOriginalPedido = Signal()        # "Volver al sonido original"

    def __init__(self, parent=None, abierta: bool = True, solo_volumen: bool = False):
        """``solo_volumen``: solo volumen, normalizar, fundidos y silencios (el modo Audio): sin el renglón
        "Sonido: …", "Editar el sonido en el modo Audio", "Cambiar el sonido por…", "Volver al original"
        ni "Guardar solo el audio…", que son del video."""
        super().__init__("Sonido", "volume-2", "Quitar el sonido, volumen, normalizar, fundidos y guardar solo el "
                         "audio. Los silencios se marcan desde la línea de tiempo (Silenciar tramo).", abierta,
                         parent, con_interruptor=False)
        self._solo_volumen = bool(solo_volumen)
        no_ensanchar(self)
        self._ajustes = ma.AjustesAudio()
        self._tiene_audio = False
        self._hay_archivo = False
        capa = self.capa_cuerpo

        self.nota_sin_audio = QLabel("")
        self.nota_sin_audio.setObjectName("nota")
        self.nota_sin_audio.setWordWrap(True)
        capa.addWidget(self.nota_sin_audio)

        # De dónde sale el sonido (ida y vuelta con el modo Audio): qué suena y las tres acciones.
        self.caja_origen = QWidget()
        capa_origen = QVBoxLayout(self.caja_origen)
        capa_origen.setContentsMargins(0, 0, 0, 4)
        capa_origen.setSpacing(6)
        fila_origen = QHBoxLayout()
        fila_origen.setContentsMargins(0, 0, 0, 0)
        fila_origen.setSpacing(6)
        self.icono_origen = QLabel()
        self.icono_origen.setPixmap(iconos.pixmap("music", 14))
        self.icono_origen.setFixedWidth(16)
        self.etiqueta_origen = QLabel("Sonido: el del video")
        self.etiqueta_origen.setObjectName("nota")
        self.etiqueta_origen.setWordWrap(True)
        self.etiqueta_origen.setMinimumWidth(10)
        self.boton_volver_original = QPushButton("Volver al original")
        self.boton_volver_original.setObjectName("botonEnlace")
        self.boton_volver_original.setCursor(Qt.PointingHandCursor)
        self.boton_volver_original.setToolTip("Volver al sonido original: saca el sonido elegido y vuelve a sonar "
                                              "el del video (Ctrl+Z lo trae de nuevo).")
        self.boton_volver_original.setAccessibleName("Volver al sonido original")
        self.boton_volver_original.clicked.connect(self.volverAlOriginalPedido)
        fila_origen.addWidget(self.icono_origen, 0, Qt.AlignTop)
        fila_origen.addWidget(self.etiqueta_origen, 1)
        fila_origen.addWidget(self.boton_volver_original, 0, Qt.AlignTop)
        capa_origen.addLayout(fila_origen)
        self.boton_editar_audio = self._boton_ancho(
            " Editar el sonido en el modo Audio", "audio-lines",
            "Lleva el sonido completo del video (sin cortes ni ajustes) al modo Audio, para que suene grabado en "
            "un lugar real. Después volvés al video con ese sonido y los cortes se le aplican igual.")
        self.boton_editar_audio.clicked.connect(self.editarEnAudioPedido)
        capa_origen.addWidget(self.boton_editar_audio)
        self.boton_cambiar = self._boton_ancho(
            " Cambiar el sonido por…", "refresh-cw",
            "Pone otro audio (MP3, M4A, AAC, WAV, OGG, OPUS o FLAC) en lugar del sonido del video, desde el "
            "principio de lo que se exporta (como una voz en off). Se corta al final del video; si es más corto, "
            "lo que falta queda en silencio.")
        self.boton_cambiar.clicked.connect(self.cambiarSonidoPedido)
        capa_origen.addWidget(self.boton_cambiar)
        capa.addWidget(self.caja_origen)
        self._externo = False
        self._puede_editar = False

        # Quitar el sonido: el interruptor a la derecha, como en las cabeceras.
        self.fila_quitar = QWidget()
        fila = QHBoxLayout(self.fila_quitar)
        fila.setContentsMargins(0, 2, 0, 2)
        fila.setSpacing(8)
        etiqueta = QLabel("Quitar el sonido")
        etiqueta.setObjectName("etiquetaControl")
        self.interruptor_quitar = Interruptor()
        ayuda = "El video se exporta sin pista de audio (la vista previa tampoco suena)."
        for w in (etiqueta, self.interruptor_quitar):
            w.setToolTip(ayuda)
        self.interruptor_quitar.toggled.connect(lambda v: self._emitir(self._ajustes.con(quitar=bool(v)), "quitar"))
        fila.addWidget(etiqueta, 1)
        fila.addWidget(self.interruptor_quitar)
        capa.addWidget(self.fila_quitar)

        self.volumen = ControlDeslizante(
            "volumen", "Volumen", 0, round(ma.VOLUMEN_MAX * 100),
            "100 % deja el sonido como está. Más de 100 % lo sube y puede saturar (lo que se pasa se recorta). "
            "Con Normalizar, el volumen solo puede bajar.")
        self.volumen.numero.setSuffix(" %")
        self.volumen.numero.setFixedWidth(60)
        self.volumen.slider.setPageStep(10)
        self.volumen.establecer(100, 100)
        self.volumen.valorCambiado.connect(
            lambda _c, v: self._emitir(self._ajustes.con(volumen=v / 100.0), "volumen"))
        capa.addWidget(self.volumen)

        self.check_normalizar = QCheckBox("Normalizar (lo más fuerte a -1 dB)")
        self.check_normalizar.setToolTip(
            "Sube o baja todo el sonido para que lo más fuerte quede justo en -1 dB, sin saturar (como mucho "
            "sube 30 dB). Mide solo lo que se exporta. Después va el volumen, que acá solo puede bajar.")
        self.check_normalizar.toggled.connect(
            lambda v: self._emitir(self._ajustes.con(normalizar=bool(v)), "normalizar"))
        capa.addWidget(self.check_normalizar)

        self.fundido_entrada = ControlSegundos(
            "Fundido de entrada", "Segundos que tarda en aparecer el sonido al principio de lo que se exporta. "
            "Como mucho, la mitad de la duración final.")
        self.fundido_entrada.valorCambiado.connect(
            lambda v: self._emitir(self._ajustes.con(fundido_entrada=v), "fundido_entrada"))
        capa.addWidget(self.fundido_entrada)
        self.fundido_salida = ControlSegundos(
            "Fundido de salida", "Segundos que tarda en irse el sonido al final de lo que se exporta. "
            "Como mucho, la mitad de la duración final.")
        self.fundido_salida.valorCambiado.connect(
            lambda v: self._emitir(self._ajustes.con(fundido_salida=v), "fundido_salida"))
        capa.addWidget(self.fundido_salida)

        # Silencios: cuántos hay y cómo devolver todo.
        fila_silencios = QHBoxLayout()
        fila_silencios.setContentsMargins(0, 2, 0, 0)
        fila_silencios.setSpacing(6)
        self.nota_silencios = QLabel("")
        self.nota_silencios.setObjectName("nota")
        self.nota_silencios.setWordWrap(True)
        self.boton_devolver_todo = QPushButton("Devolver todo")
        self.boton_devolver_todo.setObjectName("botonEnlace")
        self.boton_devolver_todo.setCursor(Qt.PointingHandCursor)
        self.boton_devolver_todo.setToolTip("Quita todos los silencios: vuelve a sonar todo")
        self.boton_devolver_todo.clicked.connect(
            lambda: self._emitir(self._ajustes.sin_silencios(), "silencios"))
        fila_silencios.addWidget(self.nota_silencios, 1)
        fila_silencios.addWidget(self.boton_devolver_todo, 0, Qt.AlignTop)
        capa.addLayout(fila_silencios)

        self.boton_guardar = QPushButton(" Guardar solo el audio…")
        self.boton_guardar.setIcon(iconos.icono("music", 16))
        self.boton_guardar.setIconSize(QSize(16, 16))
        self.boton_guardar.setCursor(Qt.PointingHandCursor)
        self.boton_guardar.setToolTip("Guarda el sonido de lo que se exporta (con los cortes y estos ajustes) en "
                                      "M4A, WAV o MP3. El video original no se toca.")
        self.boton_guardar.clicked.connect(self.guardarAudioPedido)
        capa.addWidget(self.boton_guardar)

        self.caja_progreso = QWidget()
        capa_prog = QVBoxLayout(self.caja_progreso)
        capa_prog.setContentsMargins(0, 2, 0, 0)
        capa_prog.setSpacing(6)
        fila_prog = QHBoxLayout()
        fila_prog.setSpacing(10)
        self.barra = QProgressBar()
        self.barra.setRange(0, 1000)
        self.barra.setTextVisible(False)
        self.boton_cancelar = QPushButton(" Cancelar")
        self.boton_cancelar.setIcon(iconos.icono("x", 15))
        self.boton_cancelar.setIconSize(QSize(15, 15))
        self.boton_cancelar.setObjectName("botonChico")
        self.boton_cancelar.setToolTip("Cancelar: no queda ningún archivo a medias")
        self.boton_cancelar.clicked.connect(self._cancelar)
        fila_prog.addWidget(self.barra, 1)
        fila_prog.addWidget(self.boton_cancelar)
        capa_prog.addLayout(fila_prog)
        self.etiqueta_progreso = QLabel("Preparando…")
        self.etiqueta_progreso.setObjectName("nota")
        self.etiqueta_progreso.setWordWrap(True)
        capa_prog.addWidget(self.etiqueta_progreso)
        capa.addWidget(self.caja_progreso)
        self.caja_progreso.setVisible(False)
        self._guardando = False
        self._para_audio = False  # lo que se guarda es el sonido para el modo Audio
        self._actualizar()

    @staticmethod
    def _boton_ancho(texto: str, icono: str, ayuda: str) -> QPushButton:
        """Botón a todo el ancho de la tarjeta (el texto largo no la ensancha: se achica con ella)."""
        boton = QPushButton(texto)
        boton.setIcon(iconos.icono(icono, 16))
        boton.setIconSize(QSize(16, 16))
        boton.setCursor(Qt.PointingHandCursor)
        boton.setToolTip(ayuda)
        boton.setProperty("ayuda", ayuda)
        boton.setMinimumWidth(10)
        boton.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        return boton

    # ------------------------------------------------------------ datos
    @property
    def ajustes(self) -> ma.AjustesAudio:
        return self._ajustes

    def establecer_origen(self, texto: str, externo: bool, puede_editar: bool, ayuda_editar: str = "",
                          ayuda_origen: str = "") -> None:
        """De dónde sale el sonido: el renglón (``texto``, por ejemplo "Sonido: voz.m4a (desde el
        principio)"), si hay un sonido externo (muestra "Volver al original") y si se puede llevar
        el sonido del video al modo Audio (``ayuda_editar``: por qué no, si no se puede)."""
        self.etiqueta_origen.setText(texto)
        self.etiqueta_origen.setToolTip(ayuda_origen)
        self._externo, self._puede_editar = bool(externo), bool(puede_editar)
        ayuda = self.boton_editar_audio.property("ayuda")
        self.boton_editar_audio.setToolTip(ayuda_editar if ayuda_editar and not puede_editar else ayuda)
        self._actualizar()

    def mostrar_quitar(self, visible: bool) -> None:
        """Muestra u oculta "Quitar el sonido" (en un archivo de solo audio no tiene sentido)."""
        self.fila_quitar.setVisible(visible)

    def establecer(self, ajustes: ma.AjustesAudio, duracion_resultado: float, tiene_audio: bool,
                   hay_archivo: bool = True) -> None:
        """Muestra estos ajustes, sin emitir nada. Los fundidos llegan hasta la mitad de la
        duración final (``duracion_resultado``)."""
        self._ajustes = ajustes
        self._tiene_audio, self._hay_archivo = bool(tiene_audio), bool(hay_archivo)
        widgets = (self.interruptor_quitar, self.check_normalizar)
        for w in widgets:
            w.blockSignals(True)
        self.interruptor_quitar.setChecked(ajustes.quitar)
        self.check_normalizar.setChecked(ajustes.normalizar)
        for w in widgets:
            w.blockSignals(False)
        self.volumen.establecer(round(ajustes.volumen * 100), 100)
        mitad = max(0.0, duracion_resultado / 2)
        for control, valor in ((self.fundido_entrada, ajustes.fundido_entrada),
                               (self.fundido_salida, ajustes.fundido_salida)):
            control.establecer_maximo(mitad)
            control.establecer(min(valor, control.maximo()))
        self._actualizar()

    def _emitir(self, nuevo: ma.AjustesAudio, clave: str) -> None:
        if nuevo != self._ajustes:
            self.ajustesCambiados.emit(nuevo, clave)

    def _actualizar(self) -> None:
        a, activo = self._ajustes, self._tiene_audio and self._hay_archivo
        if not self._hay_archivo:
            self.nota_sin_audio.setText("Abrí un video para ajustar su sonido.")
        elif not self._tiene_audio:
            self.nota_sin_audio.setText("Este video no tiene sonido. Podés ponerle uno con \"Cambiar el sonido "
                                        "por…\".")
        elif a.quitar:
            self.nota_sin_audio.setText("El video se exporta sin pista de audio.")
        self.nota_sin_audio.setVisible(not activo or a.quitar)
        self.caja_origen.setVisible(self._hay_archivo and not self._solo_volumen)
        self.boton_guardar.setVisible(not self._solo_volumen)
        self.boton_volver_original.setVisible(self._externo)
        self.boton_volver_original.setEnabled(not self._guardando)
        self.boton_editar_audio.setEnabled(self._hay_archivo and self._puede_editar and not self._guardando)
        self.boton_cambiar.setEnabled(self._hay_archivo and not self._guardando)
        self.interruptor_quitar.setEnabled(activo)
        for w in (self.volumen, self.check_normalizar, self.fundido_entrada, self.fundido_salida):
            w.setEnabled(activo and not a.quitar)
        n = len(a.silencios)
        if n == 0:
            self.nota_silencios.setText("Para silenciar una parte, elegí su tramo en la línea de tiempo y tocá "
                                        "Silenciar tramo (M).")
        else:
            total = sum(b - x for x, b in a.silencios)
            self.nota_silencios.setText(("1 tramo silenciado" if n == 1 else f"{n} tramos silenciados")
                                        + f" · {formato_tiempo(total)}")
        self.nota_silencios.setVisible(activo)  # sin sonido no hay nada que silenciar
        self.boton_devolver_todo.setVisible(n > 0 and activo)
        self.boton_devolver_todo.setEnabled(activo and not a.quitar)
        self.boton_guardar.setEnabled(activo and not a.quitar and not self._guardando)
        self.boton_guardar.setToolTip(
            "El sonido está quitado: no hay audio para guardar." if activo and a.quitar else
            "Guarda el sonido de lo que se exporta (con los cortes y estos ajustes) en M4A, WAV o MP3. El video "
            "original no se toca.")

    # ------------------------------------------------------------ guardar
    @property
    def guardando(self) -> bool:
        return self._guardando

    def empezar_progreso(self, para_audio: bool = False) -> None:
        """Muestra la barra y Cancelar debajo del botón que lo pidió: "Guardar solo el audio" o, con
        ``para_audio``, "Editar el sonido en el modo Audio" (preparando el WAV)."""
        self._guardando = True
        self._para_audio = bool(para_audio)
        self.barra.setValue(0)
        self.etiqueta_progreso.setText("Preparando…")
        self.boton_cancelar.setEnabled(True)
        capa = self.capa_cuerpo if not para_audio else self.caja_origen.layout()
        actual = self.caja_progreso.parentWidget().layout() if self.caja_progreso.parentWidget() else None
        if actual is not None:
            actual.removeWidget(self.caja_progreso)
        if para_audio:
            capa.insertWidget(capa.indexOf(self.boton_editar_audio) + 1, self.caja_progreso)
            self.boton_editar_audio.setText(" Preparando el sonido…")
        else:
            capa.insertWidget(capa.indexOf(self.boton_guardar) + 1, self.caja_progreso)
            self.boton_guardar.setText(" Guardando el audio…")
        self.caja_progreso.setVisible(True)
        self._actualizar()

    def mostrar_progreso(self, hechas: int, total: int, restante: Optional[float]) -> None:
        if not self._guardando:
            return
        self.barra.setValue(round(1000 * hechas / max(1, total)))
        texto = f"{round(100 * hechas / max(1, total))} %"
        if restante is not None:
            texto += f" · faltan {formato_tiempo(restante, decimas=False)}"
        self.etiqueta_progreso.setText(texto)

    def terminar_progreso(self) -> None:
        self._guardando = False
        self.caja_progreso.setVisible(False)
        self.boton_guardar.setText(" Guardar solo el audio…")
        self.boton_editar_audio.setText(" Editar el sonido en el modo Audio")
        self._actualizar()

    def _cancelar(self) -> None:
        self.boton_cancelar.setEnabled(False)
        self.etiqueta_progreso.setText("Cancelando…")
        self.cancelarGuardadoPedido.emit()


__all__ = ["PanelSonido", "ControlSegundos"]
