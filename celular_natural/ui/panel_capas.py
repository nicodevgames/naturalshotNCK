"""Panel "Capas" (modo Photoshop de NaturalShot Lite): la pila de capas del documento abierto.

Va en la columna derecha del modo Photoshop, debajo de Propiedades, con la misma estética de
tarjetas. En ese modo la vista va sin el filtro: "Celular natural" aparece arriba de todo como
"Filtro celular natural", bloqueado y atenuado (se elige en Fácil o Editor), y la máscara se pinta
con las herramientas de la barra de la izquierda (``configurar_photoshop``). Muestra el
``Documento`` (``motor/documento.py``) **de abajo hacia arriba**: la capa de arriba se ve arriba.
Arriba de todo está siempre "Celular natural" (el filtro: su opacidad es "cuánto filtro") y abajo
de todo, la base (la "Foto" o el "Fondo" de un documento nuevo).

* **Cada fila:** sangría según el grupo, flecha para plegar (en los grupos), ojo, miniatura (y la
  de la máscara, si tiene), un ícono por tipo (imagen, píxeles, texto, forma, relleno, grupo),
  nombre (abajo, el modo de fusión y la opacidad), "fx" si tiene estilos y candado. **Doble clic**
  en la fila (o un clic en "fx") abre el **Estilo de capa**; doble clic en la miniatura de un texto
  lo edita en la vista; **F2** (o el menú contextual) cambia el nombre.
* **Selección múltiple:** Ctrl+clic suma o saca una capa y Mayús+clic elige un tramo
  (``capas_elegidas``). La "capa elegida" (``capa_elegida``) es la última que se tocó: la de
  Propiedades, fusión y opacidad.
* **Arriba:** el modo de fusión (``MODOS_FUSION``) y la opacidad (0-100 %) de la capa elegida.
* **Abajo:** agregar imagen, duplicar, máscara (agregar una blanca o, si ya tiene, mostrar todo,
  ocultar todo, invertir o quitarla), estilo de capa ("fx"), Mover / Transformar, agrupar, subir,
  bajar y borrar.
* **Menú contextual** (clic derecho): cambiar el nombre, estilo de capa, duplicar, borrar, agrupar,
  desagrupar, rasterizar y combinar hacia abajo.
* **Arrastrar** una fila la lleva encima o debajo de otra, o adentro de un grupo (soltándola
  sobre él): ``Documento.reubicar``, así entra y sale de los grupos.

El panel no guarda nada: cada cambio arma un documento nuevo con las funciones del motor y lo
manda a la ventana (``documentoCambiado(doc, registrar)``), que lo pone en la foto, lo muestra y
lo anota en el historial (``registrar``) o solo lo muestra mientras dura un gesto (arrastrar el
deslizador de opacidad: un gesto = un paso). Las reglas de la pila (la base no se borra, el ajuste
va siempre arriba, los grupos...) son del motor: sus ``ValueError`` se muestran como avisos
(``aviso``) y los botones que no aplican quedan deshabilitados.

Una capa **bloqueada** (candado) no se transforma, no se borra, no se mueve en la pila y no
cambia su opacidad, su fusión, su máscara ni sus estilos; sí se puede ocultar y renombrar.
"""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMenu, QPushButton, QSizePolicy, QSlider, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from ..motor.documento import (
    TIPOS_CON_TRANSFORMACION, AlmacenImagenes, Documento, capas_faltantes, combinar_abajo, rasterizar,
)
from ..motor.fusion import MODOS_FUSION
from . import estilo, iconos
from .controles import SeccionPlegable
from .documento_capas import mascara_de, mascara_llena

LADO_MINI = 32          # miniatura de cada fila (px)
ALTO_FILA = 40
SANGRIA = 14            # px por nivel de grupo
FILAS_MINIMAS = 2       # la lista nunca muestra menos filas que esto
FORMAS_MASCARA = (("rect", "square-dashed", "Rectángulo"), ("elipse", "circle-dashed", "Elipse"),
                  ("lazo", "lasso", "Lazo (mantené apretado y dibujá)"),
                  ("pincel", "brush", "Pincel (con tamaño y dureza)"))
# Un ícono por tipo de capa (junto al nombre) y cómo se llama.
ICONO_TIPO = {"foto": "camera", "imagen": "image", "pixeles": "paintbrush", "texto": "type", "forma": "pentagon",
              "relleno": "droplets", "grupo": "folder-open", "ajuste_natural": iconos.CELULAR}
NOMBRE_TIPO = {"foto": "Foto", "imagen": "Imagen", "pixeles": "Capa de píxeles", "texto": "Texto",
               "forma": "Forma", "relleno": "Relleno", "grupo": "Grupo", "ajuste_natural": "Filtro"}


def _qimage(arr: np.ndarray) -> QImage:
    """Gris, RGB o RGBA uint8 → QImage (copia)."""
    arr = np.ascontiguousarray(arr)
    h, w = arr.shape[:2]
    if arr.ndim == 2:
        return QImage(arr.data, w, h, w, QImage.Format_Grayscale8).copy()
    if arr.shape[2] == 4:
        return QImage(arr.data, w, h, 4 * w, QImage.Format_RGBA8888).copy()
    return QImage(arr.data, w, h, 3 * w, QImage.Format_RGB888).copy()


def _reducida(arr: np.ndarray, lado: int) -> np.ndarray:
    h, w = arr.shape[:2]
    f = lado / max(h, w)
    if f >= 1:
        return arr
    return cv2.resize(arr, (max(1, round(w * f)), max(1, round(h * f))), interpolation=cv2.INTER_AREA)


def _tablero(lado: int) -> QPixmap:
    """Fondo de ajedrez para las miniaturas con transparencia."""
    pm = QPixmap(lado, lado)
    pm.fill(QColor(88, 88, 88))
    p = QPainter(pm)
    paso = max(4, lado // 6)
    for y in range(0, lado, paso):
        for x in range(0, lado, paso):
            if (x // paso + y // paso) % 2 == 0:
                p.fillRect(x, y, paso, paso, QColor(58, 58, 58))
    p.end()
    return pm


def miniatura(arr: Optional[np.ndarray], lado: int = LADO_MINI) -> QPixmap:
    """La imagen centrada en un cuadrado con fondo de ajedrez (como en Photoshop)."""
    pm = _tablero(lado)
    if arr is None:
        return pm
    chica = _qimage(_reducida(arr, lado))
    p = QPainter(pm)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    x, y = (lado - chica.width()) // 2, (lado - chica.height()) // 2
    p.drawImage(x, y, chica)
    p.end()
    return pm


def miniatura_ajuste(lado: int = LADO_MINI) -> QPixmap:
    """El ícono de "Celular natural": el celular sobre el degradado de la marca."""
    pm = QPixmap(lado, lado)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    grad = QLinearGradient(0, 0, lado, lado)
    grad.setColorAt(0, QColor(estilo.MAGENTA))
    grad.setColorAt(1, QColor(estilo.VIOLETA))
    p.setBrush(grad)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(0, 0, lado, lado, 8, 8)
    icono = iconos.pixmap(iconos.CELULAR, round(lado * 0.6), "#ffffff")
    tam = icono.deviceIndependentSize()  # el ícono viene al doble (para pantallas con escalado)
    p.drawPixmap(QPointF((lado - tam.width()) / 2, (lado - tam.height()) / 2), icono)
    p.end()
    return pm


def miniatura_icono(nombre: str, lado: int = LADO_MINI) -> QPixmap:
    """Un ícono centrado en un cuadrado oscuro (la miniatura de un grupo)."""
    pm = QPixmap(lado, lado)
    pm.fill(QColor(58, 60, 67))
    p = QPainter(pm)
    icono = iconos.pixmap(nombre, round(lado * 0.6), estilo.TEXTO_2)
    tam = icono.deviceIndependentSize()
    p.drawPixmap(QPointF((lado - tam.width()) / 2, (lado - tam.height()) / 2), icono)
    p.end()
    return pm


def dibujo_de_params(tipo: str, params, lado: int = LADO_MINI) -> Optional[np.ndarray]:
    """RGBA chico de una capa texto, forma o relleno (para su miniatura). None si no se puede."""
    try:
        if tipo == "relleno":
            from ..motor.formas import renderizar_relleno
            return renderizar_relleno(params, lado, lado)
        if tipo == "forma":
            from ..motor.formas import renderizar_forma
            return renderizar_forma(params, min(1.0, (lado - 4) / max(params.ancho, params.alto, 1.0)))
        if tipo == "texto":
            from ..motor.texto import renderizar_texto
            return renderizar_texto(params, min(1.0, lado * 0.45 / max(params.tamano, 1.0)))
    except (ImportError, ValueError, OSError, MemoryError):
        return None
    return None


class _Nombre(QLabel):
    """El nombre de la capa (el doble clic avisa: abre el estilo de capa)."""

    dobleClic = Signal()

    def mouseDoubleClickEvent(self, evento) -> None:
        self.dobleClic.emit()
        evento.accept()


class FilaCapa(QFrame):
    """Una fila de la lista: sangría y flecha (grupos), ojo, miniatura (y la de la máscara), ícono del
    tipo, nombre y detalle, "fx" y candado."""

    ojo = Signal(str, bool)
    candado = Signal(str, bool)
    renombrada = Signal(str, str)
    plegar = Signal(str)
    estilos = Signal(str)  # doble clic en la fila o clic en "fx": el estilo de capa
    editarTexto = Signal(str)  # doble clic en la miniatura de un texto

    def __init__(self, capa, mini: QPixmap, mini_mascara: Optional[QPixmap], falta: bool, parent=None,
                 filtro_bloqueado: bool = False, profundidad: int = 0, plegado: Optional[bool] = None):
        """``filtro_bloqueado``: la fila de "Celular natural" en el modo Photoshop (el filtro no se ve ni se
        toca ahí: se elige en Fácil o Editor); queda arriba de todo, atenuada y sin controles.
        ``profundidad``: cuántos grupos la contienen (sangría). ``plegado``: en un grupo, si está
        plegado (None: no es un grupo)."""
        super().__init__(parent)
        self.setObjectName("filaCapaDoc")
        self.id = capa.id
        self.tipo = capa.tipo
        fila = QHBoxLayout(self)
        fila.setContentsMargins(4 + SANGRIA * profundidad, 4, 6, 4)
        fila.setSpacing(5)
        self.boton_plegar = None
        if plegado is not None:
            self.boton_plegar = QToolButton()
            self.boton_plegar.setObjectName("botonOjo")
            self.boton_plegar.setAutoRaise(True)
            self.boton_plegar.setIcon(iconos.icono("chevron-right" if plegado else "chevron-down", 13))
            self.boton_plegar.setIconSize(QSize(13, 13))
            self.boton_plegar.setFixedSize(16, 24)
            self.boton_plegar.setToolTip("Mostrar u ocultar lo que tiene adentro el grupo")
            self.boton_plegar.clicked.connect(lambda: self.plegar.emit(self.id))
            fila.addWidget(self.boton_plegar)
        self.boton_ojo = QToolButton()
        self.boton_ojo.setObjectName("botonOjo")
        self.boton_ojo.setCheckable(True)
        self.boton_ojo.setChecked(capa.visible)
        self.boton_ojo.setAutoRaise(True)
        self.boton_ojo.setIcon(iconos.icono("eye" if capa.visible else "eye-off", 15))
        self.boton_ojo.setIconSize(QSize(15, 15))
        self.boton_ojo.setFixedSize(24, 24)
        self.boton_ojo.setToolTip("Ver u ocultar esta capa")
        self.boton_ojo.toggled.connect(lambda v: self.ojo.emit(self.id, v))
        fila.addWidget(self.boton_ojo)
        self.mini = QLabel()
        self.mini.setFixedSize(LADO_MINI, LADO_MINI)
        self.mini.setPixmap(mini)
        self.mini.setObjectName("miniCapa")
        fila.addWidget(self.mini)
        self.mini_mascara = None
        if mini_mascara is not None:
            self.mini_mascara = QLabel()
            self.mini_mascara.setFixedSize(LADO_MINI - 8, LADO_MINI - 8)
            self.mini_mascara.setPixmap(mini_mascara)
            self.mini_mascara.setObjectName("miniCapa")
            self.mini_mascara.setToolTip("Máscara: lo blanco se ve, lo negro no")
            fila.addWidget(self.mini_mascara)
        textos = QVBoxLayout()
        textos.setSpacing(0)
        textos.setContentsMargins(0, 0, 0, 0)
        fila_nombre = QHBoxLayout()
        fila_nombre.setSpacing(4)
        fila_nombre.setContentsMargins(0, 0, 0, 0)
        self.icono_tipo = QLabel()
        self.icono_tipo.setObjectName("iconoTipoCapa")
        self.icono_tipo.setPixmap(iconos.pixmap(ICONO_TIPO.get(capa.tipo, "image"), 12, estilo.TEXTO_TENUE))
        self.icono_tipo.setFixedSize(14, 14)
        self.icono_tipo.setToolTip(NOMBRE_TIPO.get(capa.tipo, capa.tipo))
        fila_nombre.addWidget(self.icono_tipo)
        self.nombre = _Nombre(capa.nombre or "Sin nombre")
        self.nombre.setObjectName("nombreCapa")
        self.nombre.setToolTip("Doble clic: estilo de capa (sombra, trazo…) · F2: cambiar el nombre")
        self.nombre.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.nombre.dobleClic.connect(lambda: self.estilos.emit(self.id))
        fila_nombre.addWidget(self.nombre, 1)
        self.editor = QLineEdit(capa.nombre)
        self.editor.setObjectName("editorNombreCapa")
        self.editor.hide()
        self.editor.editingFinished.connect(self._terminar_edicion)
        detalle = MODOS_FUSION.get(capa.fusion, capa.fusion)
        if capa.tipo == "ajuste_natural":
            detalle = f"Filtro · {round(capa.opacidad * 100)} %" + ("" if capa.fusion == "normal" else f" · {detalle}")
        else:
            detalle = f"{detalle} · {round(capa.opacidad * 100)} %"
        if filtro_bloqueado:
            self.nombre.setText("Filtro celular natural")
            self.nombre.setToolTip("El filtro va arriba de todo, sobre la foto terminada. Se elige en Fácil o "
                                   "Editor; acá las capas se editan sin él (mirá «Ver con el filtro»).")
            detalle = "Se elige en Fácil o Editor"
        if falta:
            detalle = "Falta la imagen"
        self.detalle = QLabel(detalle)
        self.detalle.setObjectName("detalleCapaFalta" if falta else "detalleCapa")
        self.detalle.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        textos.addLayout(fila_nombre)
        textos.addWidget(self.editor)
        textos.addWidget(self.detalle)
        fila.addLayout(textos, 1)
        self.fx = None
        if capa.estilos.activos:
            self.fx = QLabel("fx")
            self.fx.setObjectName("fxCapa")
            self.fx.setStyleSheet(f"color: {estilo.ROSA}; font-style: italic; font-weight: 700; font-size: 9pt;"
                                  " background: transparent;")
            self.fx.setToolTip("Tiene estilos de capa: " + ", ".join(capa.estilos.activos) + ". Clic para "
                               "cambiarlos.")
            self.fx.setCursor(Qt.PointingHandCursor)
            self.fx.mousePressEvent = lambda e: (self.estilos.emit(self.id), e.accept())
            fila.addWidget(self.fx)
        self.boton_candado = QToolButton()
        self.boton_candado.setObjectName("botonCandado")
        self.boton_candado.setCheckable(True)
        self.boton_candado.setChecked(capa.bloqueada)
        self.boton_candado.setAutoRaise(True)
        self.boton_candado.setIcon(iconos.icono("lock" if capa.bloqueada else "lock-open", 14,
                                                color=estilo.ROSA if capa.bloqueada else None))
        self.boton_candado.setIconSize(QSize(14, 14))
        self.boton_candado.setFixedSize(24, 24)
        self.boton_candado.setToolTip("Bloquear la capa: no se mueve, no se transforma ni se borra")
        self.boton_candado.toggled.connect(lambda v: self.candado.emit(self.id, v))
        fila.addWidget(self.boton_candado)
        if not capa.visible:
            self.mini.setEnabled(False)
            self.nombre.setProperty("apagada", True)
        if filtro_bloqueado:
            self.boton_candado.blockSignals(True)
            self.boton_candado.setChecked(True)
            self.boton_candado.blockSignals(False)
            self.boton_candado.setIcon(iconos.icono("lock", 14))
            self.setEnabled(False)
            self.setProperty("atenuada", True)
            self.setToolTip(self.nombre.toolTip())

    def mouseDoubleClickEvent(self, evento) -> None:
        """Doble clic: en la miniatura de un texto, editarlo; en el resto de la fila, el estilo de capa."""
        if self.tipo == "texto" and self.mini.geometry().contains(evento.position().toPoint()):
            self.editarTexto.emit(self.id)
        elif self.isEnabled():
            self.estilos.emit(self.id)
        evento.accept()

    def editar_nombre(self) -> None:
        self.nombre.hide()
        self.editor.setText(self.nombre.text())
        self.editor.show()
        self.editor.setFocus()
        self.editor.selectAll()

    def _terminar_edicion(self) -> None:
        if self.editor.isHidden():
            return
        texto = self.editor.text().strip()
        self.editor.hide()
        self.nombre.show()
        if texto and texto != self.nombre.text():
            self.nombre.setText(texto)
            self.renombrada.emit(self.id, texto)


class _Lista(QListWidget):
    """La lista de capas. Al soltar una fila arrastrada avisa dónde: ``capaSoltada(id, destino,
    donde)`` con donde "encima", "debajo" o "dentro" (de un grupo), para ``Documento.reubicar``. El
    orden lo arma el panel desde el documento (la lista no mueve nada por su cuenta).

    ``filaSoltada(id, fila)`` es la forma de la Etapa 1 (la fila nueva, para ``Documento.mover``):
    se sigue aceptando."""

    filaSoltada = Signal(str, int)  # (id de la capa, fila nueva)
    capaSoltada = Signal(str, str, str)  # (id de la capa, id de la de destino, "encima" | "debajo" | "dentro")

    def dropEvent(self, evento) -> None:
        item = self.currentItem()
        id_capa = item.data(Qt.UserRole) if item is not None else None
        destino = self.itemAt(evento.position().toPoint())
        posicion = self.dropIndicatorPosition()
        evento.setDropAction(Qt.IgnoreAction)
        evento.accept()
        if id_capa is None or destino is None:
            return
        id_destino = destino.data(Qt.UserRole)
        if id_destino == id_capa:
            return
        if posicion == QAbstractItemView.OnItem:
            donde = "dentro" if destino.data(Qt.UserRole + 1) == "grupo" else "encima"
        elif posicion == QAbstractItemView.BelowItem:
            # Justo debajo de un grupo abierto se ve su primera capa: eso es "adentro, arriba de todo".
            abierto = destino.data(Qt.UserRole + 1) == "grupo" and not destino.data(Qt.UserRole + 2)
            donde = "dentro" if abierto else "debajo"
        else:
            donde = "encima"
        self.capaSoltada.emit(id_capa, id_destino, donde)


class PanelCapas(SeccionPlegable):
    """La tarjeta "Capas" (ver el módulo)."""

    documentoCambiado = Signal(object, bool)  # (Documento nuevo, si es un paso del historial)
    capaElegida = Signal(str)
    seleccionCambiada = Signal(list)  # los ids elegidos (selección múltiple), de abajo hacia arriba
    agregarImagenPedida = Signal()
    transformarPedido = Signal()
    pintarMascaraPedido = Signal(str)  # forma: "rect", "elipse", "lazo" o "pincel"
    estilosPedidos = Signal(str)  # el estilo de capa de esa capa (doble clic, "fx" o el botón)
    editarTextoPedido = Signal(str)  # editar ese texto en la vista (doble clic en su miniatura)
    aviso = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Capas", iconos.CAPAS, "Capas de la foto: imágenes, fusión, máscaras y el filtro arriba",
                         True, parent, con_interruptor=False, plegable=True, color="#f472b6",
                         subtitulo="Imágenes, grupos, fusión, máscaras y filtro")
        self.setObjectName("tarjetaSeccion")
        self._doc: Optional[Documento] = None
        self._almacen: Optional[AlmacenImagenes] = None
        self._mini_foto: Optional[QPixmap] = None
        self._elegida: Optional[str] = None
        self._seleccion: list[str] = []  # la selección múltiple (incluye a la elegida)
        self._plegados: set[str] = set()  # grupos plegados
        self._gesto: Optional[Documento] = None  # doc al empezar a arrastrar la opacidad
        self.descripcion: Optional[str] = None  # la del paso que se está mandando (ver ``_aplicar``)
        self._filtro_bloqueado = False  # modo Photoshop: "Celular natural" no se toca (``configurar_photoshop``)
        self._con_fila_mascara = True
        self._cache_minis: dict = {}
        self._reconstruyendo = False
        # Rearmar la lista después de un cambio (en el próximo ciclo de eventos: el control que avisó
        # puede ser de una fila que se va a borrar).
        self._timer_reconstruir = QTimer(self, singleShot=True, interval=0)
        self._timer_reconstruir.timeout.connect(self._reconstruir)
        cuerpo = self.capa_cuerpo
        cuerpo.setSpacing(6)

        # ---- Arriba: fusión y opacidad de la capa elegida
        fila = QHBoxLayout()
        fila.setSpacing(6)
        self.combo_fusion = QComboBox()
        for clave, nombre in MODOS_FUSION.items():
            self.combo_fusion.addItem(nombre, clave)
        self.combo_fusion.setToolTip("Modo de fusión: cómo se mezcla la capa con lo que tiene abajo")
        self.combo_fusion.setMinimumContentsLength(8)
        self.combo_fusion.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_fusion.currentIndexChanged.connect(self._al_cambiar_fusion)
        self.combo_fusion.setFixedWidth(118)
        fila.addWidget(self.combo_fusion)
        # Opacidad en la misma fila (en «Celular natural» es "cuánto filtro"): lo dice la etiqueta
        # chica de arriba del deslizador y su ayuda.
        self.etiqueta_opacidad = QLabel("Opacidad")
        self.etiqueta_opacidad.setObjectName("detalleCapa")
        self.slider_opacidad = QSlider(Qt.Horizontal)
        self.slider_opacidad.setRange(0, 100)
        self.slider_opacidad.setPageStep(10)
        self.slider_opacidad.setToolTip("Opacidad de la capa (en «Celular natural»: cuánto filtro)")
        self.slider_opacidad.sliderPressed.connect(self._empezar_gesto)
        self.slider_opacidad.sliderReleased.connect(self._terminar_gesto)
        self.slider_opacidad.valueChanged.connect(
            lambda v: self._al_cambiar_opacidad(v, not self.slider_opacidad.isSliderDown()))
        columna = QVBoxLayout()
        columna.setSpacing(0)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.addWidget(self.etiqueta_opacidad)
        columna.addWidget(self.slider_opacidad)
        fila.addLayout(columna, 1)
        self.numero_opacidad = QSpinBox()
        self.numero_opacidad.setObjectName("valorControl")
        self.numero_opacidad.setRange(0, 100)
        self.numero_opacidad.setSuffix(" %")
        self.numero_opacidad.setButtonSymbols(QSpinBox.NoButtons)
        self.numero_opacidad.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.numero_opacidad.setFixedWidth(54)
        self.numero_opacidad.setKeyboardTracking(False)  # un valor escrito = un paso (al Enter)
        self.numero_opacidad.valueChanged.connect(lambda v: self._al_cambiar_opacidad(v, True))
        self.numero_opacidad.setToolTip("Opacidad de la capa (en «Celular natural»: cuánto filtro). Escribí un valor.")
        fila.addWidget(self.numero_opacidad)
        cuerpo.addLayout(fila)

        # ---- La lista (de abajo hacia arriba: la de arriba se ve arriba)
        self.lista = _Lista()
        self.lista.setObjectName("listaCapas")
        self.lista.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.lista.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lista.setSelectionMode(QAbstractItemView.ExtendedSelection)  # Ctrl y Mayús + clic
        self.lista.setDragDropMode(QAbstractItemView.InternalMove)
        self.lista.setDefaultDropAction(Qt.MoveAction)
        self.lista.setDropIndicatorShown(True)
        # El alto lo decide el divisor de la columna (al menos dos filas a la vista).
        self.lista.setMinimumHeight(FILAS_MINIMAS * (ALTO_FILA + 2) + 6)
        self.lista.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.lista.currentRowChanged.connect(self._al_elegir_fila)
        self.lista.itemSelectionChanged.connect(self._al_cambiar_seleccion)
        self.lista.filaSoltada.connect(self._al_soltar_fila)
        self.lista.capaSoltada.connect(self._al_soltar_capa)
        self.lista.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lista.customContextMenuRequested.connect(self._menu_contextual)
        cuerpo.addWidget(self.lista, 1)

        # ---- Abajo: botones
        botones = QHBoxLayout()
        botones.setSpacing(4)

        def boton(icono: str, ayuda: str, funcion) -> QPushButton:
            b = QPushButton()
            b.setObjectName("botonCapa")
            b.setIcon(iconos.icono(icono, 16))
            b.setIconSize(QSize(16, 16))
            b.setFixedSize(32, 30)
            b.setToolTip(ayuda)
            b.setCursor(Qt.PointingHandCursor)
            if funcion is not None:
                b.clicked.connect(funcion)
            botones.addWidget(b)
            return b

        self.boton_agregar = boton("image-plus", "Agregar imagen como capa… (PNG con transparencia, JPG, WEBP…). "
                                   "También podés arrastrarla sobre la foto con Ctrl apretado.",
                                   self.agregarImagenPedida.emit)
        self.boton_duplicar = boton("copy", "Duplicar la capa (Ctrl+J)", self.duplicar)
        self.boton_mascara = boton("contrast", "Agregar máscara (blanca: se ve todo). Después la pintás con "
                                   "«Mostrar» u «Ocultar».", self._al_tocar_mascara)
        self.menu_mascara = QMenu(self)
        self.menu_mascara.addAction(iconos.icono("eye", 15), "Mostrar todo", lambda: self.mascara_llena(255))
        self.menu_mascara.addAction(iconos.icono("eye-off", 15), "Ocultar todo", lambda: self.mascara_llena(0))
        self.menu_mascara.addAction(iconos.icono("contrast", 15), "Invertir", self.invertir_mascara)
        self.menu_mascara.addSeparator()
        self.menu_mascara.addAction(iconos.icono("x", 15), "Quitar máscara", self.quitar_mascara)
        self.boton_fx = boton("ps-fx", "Estilo de capa: sombra, trazo, resplandor y superposiciones (también con "
                              "doble clic en la capa)", lambda: self._pedir_estilos())
        self.boton_transformar = boton("move", "Transformación libre de la capa (Ctrl+T): manijas para escalar y "
                                       "rotar, flechas de a 1 px. Enter aplica, Esc cancela.",
                                       self.transformarPedido.emit)
        self.boton_agrupar = boton("folder-open", "Agrupar las capas elegidas (Ctrl+G)", self.agrupar)
        botones.addStretch(1)
        self.boton_subir = boton("arrow-up", "Subir la capa (más arriba en la pila)", lambda: self.mover(1))
        self.boton_bajar = boton("arrow-down", "Bajar la capa", lambda: self.mover(-1))
        self.boton_borrar = boton("trash-2", "Borrar la capa (o las elegidas)", self.borrar)
        cuerpo.addLayout(botones)

        # ---- Pintar la máscara (si la capa elegida tiene)
        self.caja_mascara = QFrame()
        self.caja_mascara.setObjectName("cajaMascara")
        fila_m = QHBoxLayout(self.caja_mascara)
        fila_m.setContentsMargins(4, 3, 4, 3)
        fila_m.setSpacing(3)
        self.caja_mascara.setToolTip("Pintar la máscara de la capa: elegí si lo que marcás se muestra o se oculta "
                                     "y con qué (rectángulo, elipse, lazo o pincel)")
        self.grupo_modo_mascara = QButtonGroup(self)
        self.grupo_modo_mascara.setExclusive(True)
        self.botones_modo_mascara = {}
        segmento = QFrame()
        segmento.setObjectName("segmento")
        fila_seg = QHBoxLayout(segmento)
        fila_seg.setContentsMargins(2, 2, 2, 2)
        fila_seg.setSpacing(2)
        for modo, texto, ayuda in (("mostrar", "Mostrar", "Pintar la máscara: lo que marques se ve"),
                                   ("ocultar", "Ocultar", "Pintar la máscara: lo que marques se oculta")):
            b = QPushButton(texto)
            b.setObjectName("botonSegmento")
            b.setProperty("compacto", True)
            b.setMinimumWidth(66)
            b.setCheckable(True)
            b.setChecked(modo == "ocultar")
            b.setToolTip(ayuda)
            b.setCursor(Qt.PointingHandCursor)
            self.grupo_modo_mascara.addButton(b)
            self.botones_modo_mascara[modo] = b
            fila_seg.addWidget(b)
        fila_m.addWidget(segmento)
        fila_m.addStretch(1)
        self.botones_forma_mascara = {}
        for forma, icono, ayuda in FORMAS_MASCARA:
            b = QPushButton()
            b.setObjectName("botonCapa")
            b.setIcon(iconos.icono(icono, 15))
            b.setFixedSize(28, 28)
            b.setToolTip(f"Pintar la máscara: {ayuda}")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, f=forma: self.pintarMascaraPedido.emit(f))
            self.botones_forma_mascara[forma] = b
            fila_m.addWidget(b)
        cuerpo.addWidget(self.caja_mascara)
        self.caja_mascara.setVisible(False)

        self.nota = QLabel("Abrí una foto para trabajar con capas.")
        self.nota.setObjectName("nota")
        self.nota.setWordWrap(True)
        cuerpo.addWidget(self.nota)
        self._actualizar_controles()

    # ================================================================ datos
    @property
    def documento(self) -> Optional[Documento]:
        return self._doc

    @property
    def capa_elegida(self) -> Optional[str]:
        return self._elegida

    @property
    def capas_elegidas(self) -> list[str]:
        """Las elegidas (selección múltiple), de abajo hacia arriba en la pila; al menos la elegida."""
        if self._doc is None:
            return []
        ids = {c.id for c in self._doc.capas}
        sel = [i for i in self._seleccion if i in ids]
        if self._elegida is not None and self._elegida in ids and self._elegida not in sel:
            sel.append(self._elegida)
        orden = {c.id: n for n, c in enumerate(self._doc.capas)}
        return sorted(sel, key=lambda i: orden[i])

    @property
    def modo_mascara(self) -> str:
        return "mostrar" if self.botones_modo_mascara["mostrar"].isChecked() else "ocultar"

    def establecer_modo_mascara(self, modo: str) -> None:
        self.botones_modo_mascara[modo].setChecked(True)

    def _elegible_por_defecto(self, doc: Documento) -> str:
        """La de arriba de las del medio (si hay); si no, la base (o el ajuste, fuera del modo Photoshop)."""
        medio = [c for c in doc.capas[1:] if c.tipo != "ajuste_natural"]
        if medio:
            return medio[-1].id
        return doc.capas[0].id if self._filtro_bloqueado else doc.capas[-1].id

    def establecer(self, doc: Optional[Documento], almacen: Optional[AlmacenImagenes],
                   mini_foto: Optional[QPixmap] = None) -> None:
        """Muestra ese documento (None: sin foto). Conserva la capa elegida (y la selección) si sigue."""
        self._doc, self._almacen = doc, almacen
        if mini_foto is not None:
            self._mini_foto = mini_foto
        if doc is None:
            self._mini_foto = None
        actual = next((c for c in doc.capas if c.id == self._elegida), None) if doc is not None else None
        if doc is not None and (actual is None or (self._filtro_bloqueado and actual.tipo == "ajuste_natural")):
            self._elegida = self._elegible_por_defecto(doc)
            self._seleccion = [self._elegida]
        if doc is not None:
            ids = {c.id for c in doc.capas}
            self._seleccion = [i for i in self._seleccion if i in ids] or [self._elegida]
            self._plegados &= {c.id for c in doc.capas if c.tipo == "grupo"}
        self._reconstruir()

    def establecer_miniatura_foto(self, mini_foto: Optional[QPixmap]) -> None:
        self._mini_foto = mini_foto
        self._reconstruir()

    def configurar_photoshop(self) -> None:
        """Como va en el modo Photoshop: "Celular natural" arriba de todo, bloqueado y atenuado (el
        filtro se elige en Fácil o Editor), y sin la fila para pintar la máscara (las herramientas de
        la máscara están en la barra de la izquierda)."""
        self._filtro_bloqueado = True
        self._con_fila_mascara = False
        self._reconstruir()

    def elegir(self, id_capa: Optional[str]) -> None:
        """Elige solo esa capa (la selección múltiple queda en ella) y avisa."""
        if self._doc is None or id_capa is None or not any(c.id == id_capa for c in self._doc.capas):
            return
        if self._filtro_bloqueado and self._doc.capa(id_capa).tipo == "ajuste_natural":
            return
        self._elegida = id_capa
        self._seleccion = [id_capa]
        self._desplegar_hasta(id_capa)
        self._marcar_seleccion()
        self._actualizar_controles()
        self.capaElegida.emit(id_capa)
        self._seleccion_avisada = (self._elegida, tuple(self._seleccion))
        self.seleccionCambiada.emit(self.capas_elegidas)

    def elegir_varias(self, ids, actual: Optional[str] = None) -> None:
        """Elige esas capas (selección múltiple); ``actual`` (o la de más arriba) queda como la elegida."""
        if self._doc is None:
            return
        validas = {c.id for c in self._doc.capas
                   if not (self._filtro_bloqueado and c.tipo == "ajuste_natural")}
        ids = [i for i in dict.fromkeys(ids) if i in validas]
        if not ids:
            return
        self._seleccion = ids
        orden = {c.id: n for n, c in enumerate(self._doc.capas)}
        self._elegida = actual if actual in ids else max(ids, key=lambda i: orden[i])
        for i in ids:
            self._desplegar_hasta(i)
        self._marcar_seleccion()
        self._actualizar_controles()
        self.capaElegida.emit(self._elegida)
        self._seleccion_avisada = (self._elegida, tuple(self._seleccion))
        self.seleccionCambiada.emit(self.capas_elegidas)

    def elegir_sin_avisar(self, id_capa: Optional[str]) -> None:
        """Deja elegida esa capa (aunque todavía no esté en el documento del panel: se ve al
        próximo ``establecer``), sin avisar a la ventana."""
        self._elegida = id_capa
        self._seleccion = [id_capa] if id_capa is not None else []
        if self._doc is not None and id_capa is not None and any(c.id == id_capa for c in self._doc.capas):
            self._desplegar_hasta(id_capa)
            self._marcar_seleccion()
            self._actualizar_controles()

    def filas(self) -> list[FilaCapa]:
        """Las filas, de arriba hacia abajo (como se ven)."""
        return [self.lista.itemWidget(self.lista.item(i)) for i in range(self.lista.count())]

    def fila(self, id_capa: str) -> Optional[FilaCapa]:
        return next((f for f in self.filas() if f is not None and f.id == id_capa), None)

    def _fila_de(self, id_capa: str) -> int:
        n = len(self._doc.capas)
        return n - 1 - self._doc.indice(id_capa)

    # ---------------------------------------------------------------- grupos plegables
    def plegado(self, id_grupo: str) -> bool:
        return id_grupo in self._plegados

    def alternar_plegado(self, id_grupo: str) -> None:
        """Pliega o despliega un grupo (solo cambia qué filas se ven)."""
        if id_grupo in self._plegados:
            self._plegados.discard(id_grupo)
        else:
            self._plegados.add(id_grupo)
        self._reconstruir()

    def _desplegar_hasta(self, id_capa: str) -> None:
        """Despliega los grupos que contienen a esa capa (para que se vea al elegirla)."""
        if self._doc is None:
            return
        try:
            ancestros = set(self._doc.ancestros(id_capa))
        except KeyError:
            return
        if ancestros & self._plegados:
            self._plegados -= ancestros
            self._reconstruir()

    def _oculta(self, capa) -> bool:
        """Si la fila está escondida porque algún grupo que la contiene está plegado."""
        return any(a in self._plegados for a in self._doc.ancestros(capa.id))

    # ================================================================ lista
    def _mini_de(self, capa) -> QPixmap:
        if capa.tipo == "ajuste_natural":
            return miniatura_ajuste()
        if capa.tipo == "foto":
            return self._mini_foto if self._mini_foto is not None else miniatura(None)
        if capa.tipo == "grupo":
            clave = ("grupo",)
            if clave not in self._cache_minis:
                self._cache_minis[clave] = miniatura_icono("folder-open")
            return self._cache_minis[clave]
        if capa.tipo in ("texto", "forma", "relleno"):
            clave = (capa.tipo, capa.params)
            if clave not in self._cache_minis:
                self._cache_minis[clave] = miniatura(dibujo_de_params(capa.tipo, capa.params))
            return self._cache_minis[clave]
        if self._almacen is None or capa.imagen not in self._almacen:
            return miniatura(None)
        clave = ("img", capa.imagen)
        if clave not in self._cache_minis:
            self._cache_minis[clave] = miniatura(self._almacen.obtener(capa.imagen))
        return self._cache_minis[clave]

    def _mini_mascara(self, capa) -> Optional[QPixmap]:
        if capa.mascara is None:
            return None
        clave = ("mascara", capa.mascara)
        if clave not in self._cache_minis:
            if self._almacen is not None and capa.mascara in self._almacen:
                m = self._almacen.obtener(capa.mascara)
                self._cache_minis[clave] = QPixmap.fromImage(_qimage(_reducida(m, LADO_MINI - 8)).scaled(
                    LADO_MINI - 8, LADO_MINI - 8, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                return miniatura(None, LADO_MINI - 8)
        return self._cache_minis[clave]

    def _movible(self, capa) -> bool:
        """Ni la base ni el ajuste."""
        return self._doc is not None and capa.id != self._doc.capas[0].id and capa.tipo != "ajuste_natural"

    def _reconstruir(self) -> None:
        seleccion_antes = (self._elegida, tuple(self._seleccion))
        self._reconstruir_lista()
        if seleccion_antes != getattr(self, "_seleccion_avisada", None):
            self._seleccion_avisada = seleccion_antes
            if self._doc is not None:
                self.seleccionCambiada.emit(self.capas_elegidas)

    def _reconstruir_lista(self) -> None:
        self._reconstruyendo = True
        self.lista.blockSignals(True)
        self.lista.clear()
        if len(self._cache_minis) > 200:
            self._cache_minis.clear()
        doc = self._doc
        if doc is not None:
            faltan = set(capas_faltantes(doc, self._almacen)) if self._almacen is not None else set()
            for capa in reversed(doc.capas):  # la de arriba, primero
                item = QListWidgetItem()
                item.setData(Qt.UserRole, capa.id)
                item.setData(Qt.UserRole + 1, capa.tipo)
                item.setData(Qt.UserRole + 2, capa.id in self._plegados)
                item.setSizeHint(QSize(10, ALTO_FILA))
                banderas = Qt.ItemIsEnabled | Qt.ItemIsSelectable
                if self._movible(capa) and not capa.bloqueada:
                    banderas |= Qt.ItemIsDragEnabled
                if capa.tipo == "grupo" or self._movible(capa):
                    banderas |= Qt.ItemIsDropEnabled
                bloqueado = self._filtro_bloqueado and capa.tipo == "ajuste_natural"
                if bloqueado:
                    banderas = Qt.NoItemFlags  # ni se elige ni se arrastra
                item.setFlags(banderas)
                self.lista.addItem(item)
                profundidad = len(doc.ancestros(capa.id))
                fila = FilaCapa(capa, self._mini_de(capa), self._mini_mascara(capa), capa.id in faltan,
                                filtro_bloqueado=bloqueado, profundidad=profundidad,
                                plegado=(capa.id in self._plegados) if capa.tipo == "grupo" else None)
                fila.ojo.connect(self._al_ojo)
                fila.candado.connect(self._al_candado)
                fila.renombrada.connect(self._al_renombrar)
                fila.estilos.connect(lambda i: QTimer.singleShot(0, lambda: self._pedir_estilos(i)))
                fila.editarTexto.connect(lambda i: QTimer.singleShot(0, lambda: self.editarTextoPedido.emit(i)))
                fila.plegar.connect(lambda i: QTimer.singleShot(0, lambda: self.alternar_plegado(i)))
                self.lista.setItemWidget(item, fila)
                if self._oculta(capa):
                    item.setHidden(True)
            self._marcar_seleccion(senales=False)
        self.lista.blockSignals(False)
        self._reconstruyendo = False
        self._actualizar_controles()

    def _marcar_seleccion(self, senales: bool = True) -> None:
        """Pone en la lista la selección del panel (la elegida es la fila actual)."""
        if self._doc is None:
            return
        bloquear = not self.lista.signalsBlocked()
        if bloquear:
            self.lista.blockSignals(True)
        try:
            self.lista.clearSelection()
            if self._elegida is not None and any(c.id == self._elegida for c in self._doc.capas):
                self.lista.setCurrentRow(self._fila_de(self._elegida))
            for i in self._seleccion:
                if any(c.id == i for c in self._doc.capas):
                    item = self.lista.item(self._fila_de(i))
                    if item is not None and item.flags() & Qt.ItemIsSelectable:
                        item.setSelected(True)
        finally:
            if bloquear:
                self.lista.blockSignals(False)

    def _al_elegir_fila(self, fila: int) -> None:
        if self._doc is None or fila < 0:
            return
        item = self.lista.item(fila)
        if item is None:
            return
        self._elegida = item.data(Qt.UserRole)
        self._actualizar_controles()
        self.capaElegida.emit(self._elegida)

    def _al_cambiar_seleccion(self) -> None:
        if self._doc is None or self._reconstruyendo:
            return
        elegidos = [it.data(Qt.UserRole) for it in self.lista.selectedItems()]
        if not elegidos and self._elegida is not None:
            elegidos = [self._elegida]
        self._seleccion = elegidos
        if self._elegida not in elegidos and elegidos:
            self._elegida = elegidos[-1]
            self.capaElegida.emit(self._elegida)
        self._actualizar_controles()
        self._seleccion_avisada = (self._elegida, tuple(self._seleccion))
        self.seleccionCambiada.emit(self.capas_elegidas)

    def _al_soltar_fila(self, id_capa: str, fila: int) -> None:
        """Se arrastró una fila a otra fila (forma de la Etapa 1): se mueve entre sus hermanas (el
        motor la frena en los bordes)."""
        if self._doc is None:
            return
        n = len(self._doc.capas)
        destino = n - 1 - fila
        delta = destino - self._doc.indice(id_capa)
        QTimer.singleShot(0, lambda: self._mover_a(id_capa, delta))

    def _mover_a(self, id_capa: str, delta: int) -> None:
        if delta == 0:
            self._reconstruir()
            return
        self._elegida = id_capa
        self._seleccion = [id_capa]
        self._aplicar(lambda d: d.mover(id_capa, delta), descripcion=self._descripcion_movida(id_capa, delta))
        self._reconstruir()  # aunque no haya cambiado nada (se soltó en un borde), vuelve al orden real

    def _al_soltar_capa(self, id_capa: str, destino: str, donde: str) -> None:
        QTimer.singleShot(0, lambda: self.reubicar(id_capa, destino, donde))

    def reubicar(self, id_capa: str, destino: str, donde: str) -> None:
        """Lleva la capa (un grupo, con todo lo de adentro) encima o debajo de ``destino``, o adentro
        del grupo ``destino`` (``Documento.reubicar``): un paso del historial."""
        if self._doc is None:
            return
        try:
            capa = self._doc.capa(id_capa)
        except KeyError:
            return
        if capa.bloqueada:
            self.aviso.emit(f"La capa «{capa.nombre}» está bloqueada: tocá el candado para desbloquearla.")
            self._reconstruir()
            return
        self._elegida = id_capa
        self._seleccion = [id_capa]
        if donde == "dentro":
            self._plegados.discard(destino)
        nombre = self._doc.capa(destino).nombre if any(c.id == destino for c in self._doc.capas) else ""
        texto = (f"Capa «{capa.nombre}» al grupo «{nombre}»" if donde == "dentro"
                 else f"Capa «{capa.nombre}» movida")
        self._aplicar(lambda d: d.reubicar(id_capa, destino, donde), descripcion=texto)
        self._reconstruir()

    def _menu_contextual(self, pos) -> None:
        item = self.lista.itemAt(pos)
        if item is None or self._doc is None:
            return
        id_capa = item.data(Qt.UserRole)
        if id_capa not in self.capas_elegidas:
            self.elegir(id_capa)
        capa = self._capa()
        if capa is None:
            return
        menu = self.menu_capa()
        menu.exec(self.lista.viewport().mapToGlobal(pos))

    def menu_capa(self) -> QMenu:
        """El menú de la capa elegida (y del clic derecho): duplicar, borrar, agrupar, desagrupar,
        rasterizar y combinar hacia abajo, cada uno habilitado si aplica."""
        menu = QMenu(self)
        capa = self._capa()
        varias = len(self.capas_elegidas) > 1
        movible = capa is not None and self._movible(capa)
        libre = movible and not capa.bloqueada
        a = menu.addAction(iconos.icono("pencil", 15), "Cambiar el nombre…\tF2", self.renombrar_elegida)
        a.setEnabled(capa is not None and not (self._filtro_bloqueado and capa.tipo == "ajuste_natural"))
        a = menu.addAction(iconos.icono("ps-fx", 15), "Estilo de capa…", lambda: self._pedir_estilos())
        a.setEnabled(self._con_estilos(capa))
        menu.addSeparator()
        a = menu.addAction(iconos.icono("copy", 15), "Duplicar capa\tCtrl+J", self.duplicar)
        a.setEnabled(movible)
        a = menu.addAction(iconos.icono("trash-2", 15), "Borrar capas" if varias else "Borrar capa", self.borrar)
        a.setEnabled(libre)
        menu.addSeparator()
        a = menu.addAction(iconos.icono("folder-open", 15), "Agrupar\tCtrl+G", self.agrupar)
        a.setEnabled(self._se_puede_agrupar())
        a = menu.addAction("Desagrupar\tCtrl+Mayús+G", self.desagrupar)
        a.setEnabled(capa is not None and capa.tipo == "grupo")
        menu.addSeparator()
        a = menu.addAction(iconos.icono("paintbrush", 15), "Rasterizar", self.rasterizar)
        a.setEnabled(libre and capa.tipo not in ("pixeles",))
        a = menu.addAction("Combinar hacia abajo", self.combinar_abajo)
        a.setEnabled(libre and self._se_puede_combinar(capa))
        return menu

    # ================================================================ controles
    def _capa(self):
        if self._doc is None or self._elegida is None:
            return None
        try:
            return self._doc.capa(self._elegida)
        except KeyError:
            return None

    @staticmethod
    def _con_estilos(capa) -> bool:
        """Si la capa lleva estilos de capa (imagen, píxeles, texto, forma y grupo, sin candado)."""
        from ..motor.documento import TIPOS_CON_ESTILOS
        return capa is not None and capa.tipo in TIPOS_CON_ESTILOS and not capa.bloqueada

    def _pedir_estilos(self, id_capa: Optional[str] = None) -> None:
        """Pide el estilo de capa de esa capa (o de la elegida)."""
        if self._doc is None:
            return
        if id_capa is not None and id_capa != self._elegida:
            self.elegir(id_capa)
        capa = self._capa()
        if capa is None:
            return
        if not self._con_estilos(capa):
            if capa.bloqueada:
                self.aviso.emit(f"La capa «{capa.nombre}» está bloqueada: tocá el candado para desbloquearla.")
            return
        self.estilosPedidos.emit(capa.id)

    def renombrar_elegida(self) -> None:
        """F2 (o el menú contextual): el nombre de la capa elegida se edita en su fila."""
        if self._elegida is None:
            return
        fila = self.fila(self._elegida)
        if fila is not None and fila.isEnabled():
            fila.editar_nombre()

    def _se_puede_agrupar(self) -> bool:
        if self._doc is None:
            return False
        ids = self.capas_elegidas
        return bool(ids) and all(self._movible(self._doc.capa(i)) for i in ids)

    def _se_puede_combinar(self, capa) -> bool:
        """Si "Combinar hacia abajo" aplica: un grupo (se combina entero) o una capa con una hermana abajo
        que no sea un grupo ni la base."""
        if self._doc is None or capa is None or not self._movible(capa):
            return False
        if capa.tipo == "grupo":
            return True
        i = self._doc.indice(capa.id)
        inicio = i
        j = inicio - 1
        if j <= 0:
            return False
        abajo = self._doc.capas[j]
        return abajo.padre == capa.padre and abajo.tipo != "grupo"

    def _actualizar_controles(self) -> None:
        capa = self._capa()
        hay = capa is not None
        libre = hay and not capa.bloqueada
        movible = hay and self._movible(capa)
        for w in (self.combo_fusion, self.slider_opacidad, self.numero_opacidad):
            w.setEnabled(libre)
        self.etiqueta_opacidad.setText("Cuánto filtro" if hay and capa.tipo == "ajuste_natural" else "Opacidad")
        if hay:
            for w in (self.combo_fusion, self.slider_opacidad, self.numero_opacidad):
                w.blockSignals(True)
            self.combo_fusion.setCurrentIndex(max(0, self.combo_fusion.findData(capa.fusion)))
            valor = round(capa.opacidad * 100)
            if not self.slider_opacidad.isSliderDown():
                self.slider_opacidad.setValue(valor)
            self.numero_opacidad.setValue(valor)
            for w in (self.combo_fusion, self.slider_opacidad, self.numero_opacidad):
                w.blockSignals(False)
        self.boton_agregar.setEnabled(self._doc is not None)
        self.boton_duplicar.setEnabled(movible)
        self.boton_mascara.setEnabled(libre)
        self.boton_mascara.setToolTip(
            "Máscara: mostrar todo, ocultar todo, invertir o quitarla" if hay and capa.mascara is not None else
            "Agregar máscara (blanca: se ve todo). Después la pintás con «Mostrar» u «Ocultar».")
        self.boton_transformar.setEnabled(libre and capa.tipo in TIPOS_CON_TRANSFORMACION)
        self.boton_fx.setEnabled(self._con_estilos(capa))
        self.boton_agrupar.setEnabled(self._se_puede_agrupar())
        if movible and self._doc is not None:
            hermanas = [c.id for c in self._doc.hijos(capa.padre)]
            k = hermanas.index(capa.id) if capa.id in hermanas else -1
            self.boton_subir.setEnabled(libre and 0 <= k < len(hermanas) - 1)
            self.boton_bajar.setEnabled(libre and k > 0)
        else:
            self.boton_subir.setEnabled(False)
            self.boton_bajar.setEnabled(False)
        self.boton_borrar.setEnabled(movible and libre)
        self.caja_mascara.setVisible(self._con_fila_mascara and libre and capa.mascara is not None)
        if self._doc is None:
            self.nota.setText("Abrí una foto para trabajar con capas.")
        elif len(self._doc.capas) <= 2 and all(not self._movible(c) for c in self._doc.capas):
            self.nota.setText("Sumá una imagen (un logo, un PNG con transparencia u otra foto) con el primer "
                              "botón, o arrastrala sobre la foto.")
        else:
            self.nota.setText("")
        self.nota.setVisible(bool(self.nota.text()))

    # ================================================================ cambios
    def _aplicar(self, cambio, registrar: bool = True, descripcion: Optional[str] = None) -> bool:
        """Arma el documento nuevo con ``cambio(doc)`` y lo manda a la ventana. Un ``ValueError``
        del motor (una regla de la pila) se muestra como aviso y no cambia nada. ``descripcion``:
        el texto del paso del historial, si no alcanza con comparar (subir o bajar una capa)."""
        if self._doc is None:
            return False
        try:
            nuevo = cambio(self._doc)
        except ValueError as error:
            self.aviso.emit(str(error))
            return False
        except KeyError:
            return False
        if nuevo == self._doc and registrar:
            self._timer_reconstruir.start()  # vuelve a mostrar lo que hay (por ejemplo, un ojo sin cambios)
            return False
        self._doc = nuevo
        self.descripcion = descripcion
        try:
            self.documentoCambiado.emit(nuevo, registrar)
        finally:
            self.descripcion = None
        if registrar:
            self._timer_reconstruir.start()
        return True

    def aplicar(self, cambio, descripcion: Optional[str] = None, elegir: Optional[str] = None) -> bool:
        """Un cambio del documento desde afuera (el menú del modo Photoshop), como un paso del
        historial. ``elegir``: la capa que queda elegida después."""
        if elegir is not None:
            self._elegida = elegir
            self._seleccion = [elegir]
        hecho = self._aplicar(cambio, descripcion=descripcion)
        if hecho:
            self._reconstruir()
        return hecho

    def _descripcion_movida(self, id_capa: str, delta: int) -> str:
        return f"Capa «{self._doc.capa(id_capa).nombre}» " + ("subida" if delta > 0 else "bajada")

    def _bloqueada(self) -> bool:
        capa = self._capa()
        if capa is not None and capa.bloqueada:
            self.aviso.emit(f"La capa «{capa.nombre}» está bloqueada: tocá el candado para desbloquearla.")
            return True
        return False

    def _al_cambiar_fusion(self, _i: int) -> None:
        capa = self._capa()
        if capa is None or self._bloqueada():
            return
        self._aplicar(lambda d: d.con_capa(capa.id, fusion=self.combo_fusion.currentData()))

    def _empezar_gesto(self) -> None:
        self._gesto = self._doc

    def _terminar_gesto(self) -> None:
        self._gesto = None
        self._al_cambiar_opacidad(self.slider_opacidad.value(), True)

    def _al_cambiar_opacidad(self, valor: int, registrar: bool) -> None:
        capa = self._capa()
        if capa is None or capa.bloqueada:
            return
        for w in (self.slider_opacidad, self.numero_opacidad):
            if w.value() != valor:
                w.blockSignals(True)
                w.setValue(valor)
                w.blockSignals(False)
        opacidad = valor / 100.0
        if registrar:
            # Fin del gesto (o un valor escrito): un paso, aunque el documento ya tenga ese valor.
            nuevo = self._doc.con_capa(capa.id, opacidad=opacidad)
            self._doc = nuevo
            self.documentoCambiado.emit(nuevo, True)
        else:
            self._aplicar(lambda d: d.con_capa(capa.id, opacidad=opacidad), registrar=False)
        fila = self.fila(capa.id)
        if fila is not None:
            texto = fila.detalle.text().rsplit("·", 1)[0].strip()
            fila.detalle.setText(f"{texto} · {valor} %")

    # El ojo, el candado y el nombre vienen de un control de la fila: la lista se rearma después
    # (``_aplicar`` lo programa), nunca mientras ese control todavía está avisando.
    def _al_ojo(self, id_capa: str, visible: bool) -> None:
        self._elegida = id_capa
        self._seleccion = [id_capa]
        self._aplicar(lambda d: d.con_capa(id_capa, visible=visible))

    def _al_candado(self, id_capa: str, bloqueada: bool) -> None:
        self._elegida = id_capa
        self._seleccion = [id_capa]
        self._aplicar(lambda d: d.con_capa(id_capa, bloqueada=bloqueada))

    def _al_renombrar(self, id_capa: str, nombre: str) -> None:
        self._aplicar(lambda d: d.con_capa(id_capa, nombre=nombre))

    def renombrar(self, id_capa: str, nombre: str) -> None:
        self._al_renombrar(id_capa, nombre)

    def alternar_visible(self, id_capa: str) -> None:
        self._al_ojo(id_capa, not self._doc.capa(id_capa).visible)

    def alternar_bloqueo(self, id_capa: str) -> None:
        self._al_candado(id_capa, not self._doc.capa(id_capa).bloqueada)

    def establecer_opacidad(self, id_capa: str, valor: int) -> None:
        """Para el teclado o las pruebas: la opacidad (0-100) de una capa, como un paso."""
        self.elegir(id_capa)
        self._al_cambiar_opacidad(int(valor), True)

    def establecer_fusion(self, id_capa: str, modo: str) -> None:
        self.elegir(id_capa)
        self.combo_fusion.setCurrentIndex(self.combo_fusion.findData(modo))

    def duplicar(self) -> None:
        capa = self._capa()
        if capa is None or not self._movible(capa):
            return
        if self._aplicar(lambda d: d.duplicar(capa.id)):
            i = self._doc.indice(capa.id)
            fin = i + 1 + len(self._doc.descendientes(capa.id)) if capa.tipo == "grupo" else i + 1
            self._elegida = self._doc.capas[fin].id
            self._seleccion = [self._elegida]
            self._reconstruir()

    def borrar(self) -> None:
        """Borra la capa elegida o, con varias elegidas, todas (un solo paso)."""
        capa = self._capa()
        if capa is None or self._bloqueada():
            return
        ids = [i for i in self.capas_elegidas if self._movible(self._doc.capa(i))]
        if not ids:
            return
        bloqueadas = [self._doc.capa(i).nombre for i in ids if self._doc.capa(i).bloqueada]
        if bloqueadas:
            self.aviso.emit(f"La capa «{bloqueadas[0]}» está bloqueada: tocá el candado para desbloquearla.")
            return
        i = self._doc.indice(capa.id)

        def quitar(d):
            for id_capa in ids:
                if any(c.id == id_capa for c in d.capas):
                    d = d.quitar(id_capa)
            return d

        texto = f"{len(ids)} capas borradas" if len(ids) > 1 else None
        if self._aplicar(quitar, descripcion=texto):
            # Queda elegida la de abajo (como en Photoshop); si no hay, la de arriba.
            capas = self._doc.capas
            abajo, arriba = capas[max(0, min(i, len(capas) - 1) - 1)], capas[min(i, len(capas) - 1)]
            elegida = abajo if self._movible(abajo) or not self._movible(arriba) else arriba
            self._elegida = elegida.id
            self._seleccion = [elegida.id]
            self._reconstruir()

    def mover(self, delta: int) -> None:
        capa = self._capa()
        if capa is None or self._bloqueada():
            return
        self._aplicar(lambda d: d.mover(capa.id, delta), descripcion=self._descripcion_movida(capa.id, delta))
        self._reconstruir()

    # ---------------------------------------------------------------- grupos, rasterizar y combinar
    def agrupar(self) -> None:
        """Mete las elegidas en un grupo nuevo (Ctrl+G), que queda elegido y desplegado."""
        if not self._se_puede_agrupar():
            return
        ids = self.capas_elegidas
        bloqueadas = [self._doc.capa(i).nombre for i in ids if self._doc.capa(i).bloqueada]
        if bloqueadas:
            self.aviso.emit(f"La capa «{bloqueadas[0]}» está bloqueada: tocá el candado para desbloquearla.")
            return
        id_grupo = self._doc.id_libre()
        n = 1 + sum(1 for c in self._doc.capas if c.tipo == "grupo")
        texto = f"{len(ids)} capas agrupadas" if len(ids) > 1 else f"Capa «{self._doc.capa(ids[0]).nombre}» agrupada"
        if self._aplicar(lambda d: d.agrupar(ids, nombre=f"Grupo {n}", id_grupo=id_grupo), descripcion=texto):
            self._elegida = id_grupo
            self._seleccion = [id_grupo]
            self._reconstruir()

    def desagrupar(self) -> None:
        """Saca el grupo elegido (Ctrl+Mayús+G): lo de adentro queda donde estaba, elegido."""
        capa = self._capa()
        if capa is None or capa.tipo != "grupo":
            return
        hijos = [c.id for c in self._doc.hijos(capa.id)]
        if self._aplicar(lambda d: d.desagrupar(capa.id), descripcion=f"Grupo «{capa.nombre}» desagrupado"):
            if hijos:
                self._seleccion = hijos
                self._elegida = hijos[-1]
            self._reconstruir()

    def rasterizar(self) -> None:
        """Pasa la capa elegida a píxeles (un texto, una forma, un relleno o un grupo)."""
        capa = self._capa()
        if capa is None or self._almacen is None or not self._movible(capa) or self._bloqueada():
            return
        almacen = self._almacen
        if self._aplicar(lambda d: rasterizar(d, almacen, capa.id), descripcion=f"Capa «{capa.nombre}» rasterizada"):
            self._reconstruir()

    def combinar_abajo(self) -> None:
        """"Combinar hacia abajo": la elegida y la de abajo en una sola capa de píxeles (un grupo, entero)."""
        capa = self._capa()
        if capa is None or self._almacen is None or self._bloqueada():
            return
        if not self._se_puede_combinar(capa):
            self.aviso.emit("No hay una capa abajo con la cual combinar (abajo está la base, un grupo o el borde "
                            "del grupo).")
            return
        almacen = self._almacen
        abajo = None if capa.tipo == "grupo" else self._doc.capas[self._doc.indice(capa.id) - 1].id
        texto = f"Grupo «{capa.nombre}» combinado" if capa.tipo == "grupo" else f"Capa «{capa.nombre}» combinada abajo"
        if self._aplicar(lambda d: combinar_abajo(d, almacen, capa.id), descripcion=texto):
            self._elegida = abajo or capa.id
            self._seleccion = [self._elegida]
            self._reconstruir()

    # ---------------------------------------------------------------- máscara
    def _al_tocar_mascara(self) -> None:
        capa = self._capa()
        if capa is None or self._bloqueada():
            return
        if capa.mascara is None:
            self.agregar_mascara()
        else:
            self.menu_mascara.popup(self.boton_mascara.mapToGlobal(self.boton_mascara.rect().bottomLeft()))

    def agregar_mascara(self) -> None:
        """Una máscara blanca (se ve todo) en la capa elegida."""
        capa = self._capa()
        if capa is None or self._almacen is None or self._bloqueada():
            return
        id_m = self._almacen.guardar(mascara_llena(self._doc, 255))
        self._aplicar(lambda d: d.con_capa(capa.id, mascara=id_m))
        self._reconstruir()

    def mascara_llena(self, valor: int) -> None:
        """"Mostrar todo" (255) u "Ocultar todo" (0)."""
        capa = self._capa()
        if capa is None or self._almacen is None or capa.mascara is None or self._bloqueada():
            return
        id_m = self._almacen.guardar(mascara_llena(self._doc, valor))
        self._aplicar(lambda d: d.con_capa(capa.id, mascara=id_m))
        self._reconstruir()

    def invertir_mascara(self) -> None:
        capa = self._capa()
        if capa is None or self._almacen is None or capa.mascara is None or self._bloqueada():
            return
        m = mascara_de(self._doc, self._almacen, capa.id)
        id_m = self._almacen.guardar(255 - m)
        self._aplicar(lambda d: d.con_capa(capa.id, mascara=id_m))
        self._reconstruir()

    def quitar_mascara(self) -> None:
        capa = self._capa()
        if capa is None or capa.mascara is None or self._bloqueada():
            return
        self._aplicar(lambda d: d.con_capa(capa.id, mascara=None))
        self._reconstruir()


__all__ = ["FilaCapa", "ICONO_TIPO", "PanelCapas", "dibujo_de_params", "miniatura", "miniatura_ajuste"]
