"""El modo **Photoshop** de NaturalShot Lite (capas, como Photopea), en su propio módulo.

La ventana (``ventana.VentanaPrincipal``) tiene el documento de cada foto, el historial, la vista, la
tira, la sesión y el proyecto; este módulo arma lo propio del modo y opera sobre eso:

* **Menú arriba** (``construir_menu``): Archivo, Editar, Imagen, Capa y Ver. Cada operación usa la
  API del motor (``motor/documento.py``) y queda como **un paso del historial**.
* **Barra de herramientas izquierda** (``construir_columna_izquierda``, ``HERRAMIENTAS``): Mover (V),
  Recortar (C), Texto (T), Formas (U), Pincel (B), Borrador (E), Bote y Degradado (G, Mayús+G; un solo
  botón), Mano (H, o Espacio sostenido), Zoom (Z), Cuentagotas (I) y las de la máscara (rectángulo,
  elipse, lazo y pincel), más los **colores de frente y fondo** (X intercambia, D restablece, clic
  elige). Al lado, el Historial.
* **Barra de opciones** arriba de la vista (``construir_opciones``): cambia con la herramienta. En
  Mover: "Selección automática", "Mostrar controles" y alinear y distribuir.
* **Columna derecha** (``construir_columna_derecha``): Propiedades arriba y Capas abajo.
* **Mover** (``ControladorVista``): con "Selección automática", un clic elige la capa de arriba bajo
  el mouse; arrastrar mueve la capa o todas las elegidas (Ctrl o Mayús + clic en el panel); con
  "Mostrar controles", las manijas escalan libre (X e Y por separado; Mayús mantiene la proporción) y
  rotan. Cada gesto es un paso. El **imán** pega la caja de lo que se mueve al centro y a los bordes
  del lienzo y de las otras capas, con **guías** magenta (``iman.py``).
* **Transformación libre** (Ctrl+T, ``alternar_transformar``): la de la Etapa 1 (Enter aplica, Esc
  cancela), ahora con escala libre, volteo vertical, para todo tipo de capa con transformación e imán.
* **Texto (T)** y **Formas (U)** (Etapa 2, U2): un clic con Texto crea una capa ``texto`` y se escribe
  ahí mismo (``texto_ps.EdicionTexto``: un campo transparente sobre la vista; lo que se ve es la capa
  de verdad, que se vuelve a dibujar con cada tecla); arrastrar crea una caja (el texto se corta a ese
  ancho). Doble clic sobre un texto (con Mover o Texto, o en su miniatura) lo vuelve a editar. Con
  Formas, arrastrar dibuja la forma elegida (Mayús: 1:1; Alt: desde el centro). Sus barras de opciones
  (``opciones_ps``) son también las de Propiedades.
* **Estilo de capa** (``estilos_capa.DialogoEstilos``): doble clic en la capa del panel, "fx" o
  "Capa › Estilo de capa…", con vista previa en vivo; Aceptar es un paso y Cancelar vuelve.
* Los colores se eligen con el **selector propio** (``selector_color``).
* **Pincel (B)**, **Borrador (E)**, **Bote (G)**, **Degradado (Mayús+G)** y **Recortar (C)** (Etapa 2, U3;
  las piezas, en ``pintura_ps``): el trazo se ve en una superposición mientras se arrastra y se aplica
  al soltar (un paso); sobre un texto, una forma o un relleno pregunta "¿Rasterizar la capa?"; sobre la
  base, pinta en una capa de píxeles nueva. El Degradado pinta en una capa de píxeles o crea una capa de
  relleno. Recortar es un recuadro con manijas (Enter aplica, Esc cancela); en una foto, con su recorte
  no destructivo. ``[`` y ``]`` cambian el tamaño del pincel.
* El **kit de flyers** (Nuevo, Agregar imagen, Texto, Quitar fondo y Recortar) y las **máscaras**
  (pintarlas con las herramientas de la izquierda) también viven acá. El botón Texto del kit elige
  la herramienta Texto (los textos del kit de antes, que eran imágenes, siguen siendo imágenes).

**Documentos nuevos (sin foto).** "Nuevo" (Ctrl+N) crea un ``Documento.nuevo_lienzo`` con el fondo
elegido (color, transparente o degradado): una entrada más de la tira, sin archivo
(``documento_capas.es_ruta_documento``). En Fácil y Editor su composición es la "foto" que entra al
filtro. Las operaciones de lienzo (tamaño, recorte, rotación, volteo, acoplar) usan el motor; en una
**foto** con su edición no destructiva, rotar, voltear y recortar usan la geometría y el recorte de
siempre (la foto se conserva), y tamaño de imagen, tamaño del lienzo y acoplar arman un **documento
nuevo** en la tira (la foto queda como estaba).
"""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from PySide6.QtCore import QObject, QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QMenu, QMenuBar, QMessageBox, QPushButton, QSizePolicy, QSlider, QStackedWidget, QVBoxLayout, QWidget,
)

from ..motor.documento import (
    LADO_MAX, MODOS_ALINEAR, TIPOS_CON_ESTILOS, TIPOS_CON_TRANSFORMACION, Capa, Documento, Transformacion, acoplar,
    alinear,
    caja_capa, distribuir, escalar_imagen, matriz_transformacion, recortar, rotar_lienzo, tamano_lienzo,
    transformacion_ajustada, trasladar, voltear_lienzo,
)
from ..motor import medida as md
from ..motor.estilos import EstilosCapa, Sombra
from ..motor.formas import ParamsForma, Relleno
from ..motor.proyecto_lite import MAX_PIXELES_IMAGEN
from ..motor.texto import ParamsTexto
from ..motor.zonas import Zona
from . import documento_capas as dc
from . import estilo, iconos, iman
from .herramienta_transformar import HerramientaTransformar, dibujar_guias
from .modo_facil import EDITOR, PHOTOSHOP
from .modo_video import FILTRO_ABRIR_FOTOS
from .opciones_ps import ICONOS_FORMA, NOMBRES_FORMA, ControlesForma, ControlesTexto
from .pintura_ps import (
    CajaRecorte, ControlesBote, ControlesDegradado, ControlesPincel, Lienzo, TrazoEnCurso, como_rgba, fundir_encima,
    relleno_lineal_de_arrastre, siguiente_tamano,
)
from .propiedades_ps import PanelPropiedades, dibujo_natural, tamano_natural
from .tareas import Tarea
from .texto_ps import (
    FACTOR_ALINEACION, EdicionTexto, con_params_texto, medidas_texto, nombre_texto, transformacion_con_ancla,
    transformacion_nueva,
)

# Las herramientas de la barra, en orden: (clave, ícono, tecla, ayuda). Las de máscara pintan la
# máscara de la capa elegida (la maquinaria de las zonas de los efectos). El Bote y el Degradado comparten
# un botón (clic derecho: cuál), como en Photoshop; "pintar" es el Pincel de verdad (el "pincel" de abajo
# es el de la máscara).
HERRAMIENTAS = (
    ("mover", "move", "V", "Mover (V): elegí y mové capas; con «Mostrar controles», escalalas y rotalas con las "
                           "manijas. Selección automática: un clic elige la capa de arriba bajo el mouse."),
    ("recortar", "crop", "C", "Recortar (C): ajustá el recuadro con las manijas (o arrastrá uno nuevo), con la "
                              "proporción de la barra de opciones. Enter aplica, Esc cancela."),
    ("texto", "type", "T", "Texto (T): clic en la imagen para escribir; arrastrá para una caja (el texto se corta "
                           "a ese ancho). Doble clic sobre un texto para editarlo. Esc o Ctrl+Enter terminan."),
    ("formas", "ps-rectangulo", "U", "Formas (U): arrastrá para dibujar (Mayús: 1:1; Alt: desde el centro). "
                                     "Rectángulo, elipse, línea, flecha, polígono o estrella: en la barra de "
                                     "opciones o con clic derecho acá."),
    ("pintar", "paintbrush", "B", "Pincel (B): pintá con el color de frente en la capa elegida (de píxeles o "
                                  "imagen). Tamaño, dureza y opacidad arriba; [ y ] cambian el tamaño."),
    ("borrador", "eraser", "E", "Borrador (E): borrá a transparente en la capa elegida (de píxeles o imagen). "
                                "[ y ] cambian el tamaño."),
    ("bote", "ps-bote", "G", "Bote de pintura (G): un clic rellena con el color de frente lo parecido (tolerancia). "
                             "Clic derecho: Degradado (Mayús+G)."),
    ("mano", "hand", "H", "Mano (H, o Espacio sostenido): arrastrá para desplazar la vista."),
    ("zoom", "zoom-in", "Z", "Zoom (Z): clic para acercar, Alt+clic para alejar."),
    ("cuentagotas", "pipette", "I", "Cuentagotas (I): tomá un color de la imagen como color de frente."),
    None,  # separador: las de la máscara
    ("rect", "square-dashed", "", "Rectángulo: pintá la máscara de la capa elegida (Se ve / Se oculta)."),
    ("elipse", "circle-dashed", "", "Elipse: pintá la máscara de la capa elegida (Se ve / Se oculta)."),
    ("lazo", "lasso", "", "Lazo: mantené apretado y dibujá; al soltar se pinta la máscara de la capa elegida."),
    ("pincel", "brush", "", "Pincel: pintá la máscara de la capa elegida, con tamaño y dureza. Enter termina."),
)
HERRAMIENTAS_MASCARA = ("rect", "elipse", "lazo", "pincel")
HERRAMIENTAS_PINTURA = ("pintar", "borrador")
AYUDA_BOTE = next(d[3] for d in HERRAMIENTAS if d is not None and d[0] == "bote")
AYUDA_DEGRADADO = ("Degradado (Mayús+G): arrastrá de donde empieza a donde termina (Mayús: de a 45°). En una capa de "
                   "píxeles, lo pinta ahí; si no, crea una capa de relleno. Clic derecho: Bote de pintura (G).")
TECLAS_HERRAMIENTA = {"V": "mover", "H": "mano", "Z": "zoom", "I": "cuentagotas", "T": "texto", "U": "formas",
                      "B": "pintar", "E": "borrador", "G": "bote", "C": "recortar"}
ASPECTOS_RECORTE = (("Libre", None), ("Original", "original"), ("1:1 cuadrado", 1.0), ("4:5 Instagram", 4 / 5),
                    ("3:4", 3 / 4), ("9:16 historia", 9 / 16), ("4:3", 4 / 3), ("16:9", 16 / 9), ("3:1 banner", 3.0))
FRENTE_INICIAL, FONDO_INICIAL = (0, 0, 0), (255, 255, 255)
NOMBRES_ALINEAR = {"izquierda": "a la izquierda", "centro_h": "al centro horizontal", "derecha": "a la derecha",
                   "arriba": "arriba", "centro_v": "al medio vertical", "abajo": "abajo"}
ICONOS_ALINEAR = {"izquierda": "ps-alinear-izquierda", "centro_h": "ps-alinear-centro-h",
                  "derecha": "ps-alinear-derecha", "arriba": "ps-alinear-arriba", "centro_v": "ps-alinear-centro-v",
                  "abajo": "ps-alinear-abajo"}
ESTILO_MENU = f"""
QMenuBar#menuPS {{ background: transparent; color: {estilo.TEXTO_2}; font-weight: 600; spacing: 2px; }}
QMenuBar#menuPS::item {{ padding: 7px 10px; border-radius: 8px; background: transparent; }}
QMenuBar#menuPS::item:selected {{ background: {estilo.TARJETA_2}; color: {estilo.TEXTO}; }}
QMenuBar#menuPS::item:pressed {{ background: {estilo.SELECCION}; color: {estilo.TEXTO}; }}
"""


# ---------------------------------------------------------------------------
# Destino de zona: la máscara de una capa
# ---------------------------------------------------------------------------

class DestinoMascara:
    """Destino de zona que pinta la máscara de una capa (con las herramientas de los efectos).

    Cada zona marcada (rectángulo, elipse, lazo o pincel) se suma ("mostrar") o se resta
    ("ocultar") a la máscara: ``ModoPhotoshop.pintar_zona_en_mascara``."""

    zona = None  # cada vez se marca una zona nueva

    class _SinBorde:
        @staticmethod
        def valor() -> int:
            return 0  # borde duro, como una selección de Photoshop (el pincel tiene su dureza)

    pluma = _SinBorde()

    def __init__(self, modo_ps: "ModoPhotoshop", id_capa: str, nombre: str, modo: str):
        self._modo_ps = modo_ps
        self.id_capa = id_capa
        self.modo = modo
        self.nombre = f"Máscara de «{nombre}»"
        self.instrucciones = None

    def establecer_zona(self, zona: Optional[Zona]) -> None:
        if zona is not None:
            self._modo_ps.pintar_zona_en_mascara(self.id_capa, zona, self.modo)

    def zona_cancelada(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Colores de frente y fondo
# ---------------------------------------------------------------------------

class ColoresFrenteFondo(QWidget):
    """Los dos cuadraditos de Photoshop: el de frente arriba a la izquierda y el de fondo abajo a la
    derecha. Clic en uno: elegir el color (el selector propio, ``selector_color``); la flechita:
    intercambiar (X); el cuadrito chico: restablecer negro y blanco (D)."""

    cambiados = Signal()

    LADO = 44

    def __init__(self, parent=None):
        super().__init__(parent)
        self.frente, self.fondo = FRENTE_INICIAL, FONDO_INICIAL
        self.setFixedSize(self.LADO, self.LADO)
        self.setCursor(Qt.PointingHandCursor)
        self._actualizar_ayuda()

    def _actualizar_ayuda(self) -> None:
        self.setToolTip(f"Color de frente {self._hex(self.frente)} y de fondo {self._hex(self.fondo)}.\n"
                        "Clic en uno para elegirlo · X los intercambia · D vuelve a negro y blanco")

    @staticmethod
    def _hex(c) -> str:
        return "#{:02x}{:02x}{:02x}".format(*c[:3])

    def establecer(self, frente=None, fondo=None) -> None:
        if frente is not None:
            self.frente = tuple(int(v) for v in frente[:3])
        if fondo is not None:
            self.fondo = tuple(int(v) for v in fondo[:3])
        self._actualizar_ayuda()
        self.update()
        self.cambiados.emit()

    def intercambiar(self) -> None:
        self.establecer(self.fondo, self.frente)

    def restablecer(self) -> None:
        self.establecer(FRENTE_INICIAL, FONDO_INICIAL)

    def _rect_frente(self) -> QRectF:
        return QRectF(1, 1, 26, 26)

    def _rect_fondo(self) -> QRectF:
        return QRectF(self.LADO - 27, self.LADO - 27, 26, 26)

    def _rect_intercambiar(self) -> QRectF:
        return QRectF(self.LADO - 15, 0, 15, 15)

    def _rect_restablecer(self) -> QRectF:
        return QRectF(0, self.LADO - 14, 14, 14)

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        for rect, color in ((self._rect_fondo(), self.fondo), (self._rect_frente(), self.frente)):
            p.setPen(QPen(QColor("#1e1f22"), 3))
            p.setBrush(QColor(*color))
            p.drawRoundedRect(rect, 4, 4)
            p.setPen(QPen(QColor("#d9d6df"), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(1.5, 1.5, -1.5, -1.5), 3, 3)
        # Intercambiar: una flecha curva chica.
        r = self._rect_intercambiar()
        p.setPen(QPen(QColor(estilo.TEXTO_2), 1.4))
        p.drawArc(QRectF(r.x() + 2, r.y() + 3, 10, 10), 0 * 16, 90 * 16)
        p.drawLine(QPointF(r.x() + 12, r.y() + 8), QPointF(r.x() + 10, r.y() + 6))
        p.drawLine(QPointF(r.x() + 7, r.y() + 3), QPointF(r.x() + 9, r.y() + 5))
        # Restablecer: negro y blanco en miniatura.
        r = self._rect_restablecer()
        p.setPen(QPen(QColor("#d9d6df"), 1))
        p.setBrush(QColor(255, 255, 255))
        p.drawRect(QRectF(r.x() + 5, r.y() + 5, 7, 7))
        p.setBrush(QColor(0, 0, 0))
        p.drawRect(QRectF(r.x() + 1, r.y() + 1, 7, 7))
        p.end()

    def mousePressEvent(self, evento) -> None:
        pos = evento.position()
        if self._rect_intercambiar().contains(pos):
            self.intercambiar()
        elif self._rect_restablecer().contains(pos):
            self.restablecer()
        elif self._rect_frente().contains(pos):
            self.elegir("frente")
        elif self._rect_fondo().contains(pos):
            self.elegir("fondo")

    def elegir(self, cual: str) -> None:
        from .selector_color import elegir_color
        actual = self.frente if cual == "frente" else self.fondo
        elegido = elegir_color(self, tuple(actual) + (255,), "Color de frente" if cual == "frente" else
                               "Color de fondo", alfa=False)
        if elegido is not None:
            c = tuple(elegido[:3])
            self.establecer(frente=c) if cual == "frente" else self.establecer(fondo=c)


# ---------------------------------------------------------------------------
# Controlador de la vista: Mover, Mano, Zoom y Cuentagotas
# ---------------------------------------------------------------------------

def _cursor_icono(nombre: str, x: int, y: int) -> QCursor:
    pm = iconos.pixmap(nombre, 22, "#ffffff")
    return QCursor(pm, x, y)


class ControladorVista:
    """Lo que hacen el mouse y el teclado sobre la vista con las herramientas del modo Photoshop (la
    vista lo llama con la herramienta "ps": ``VistaComparacion.establecer_herramienta``). Todo en
    píxeles del documento."""

    def __init__(self, modo_ps: "ModoPhotoshop"):
        self.ps = modo_ps
        self._gesto: Optional[dict] = None  # el arrastre en curso
        self.guias: list = []
        self._herr: Optional[HerramientaTransformar] = None  # las manijas de la capa elegida
        self._clave_herr = None
        self.raton: Optional[QPointF] = None  # dónde está el mouse (el círculo del pincel)
        # El último trazo, hasta que llega la vista que ya lo tiene (así no parpadea al soltar).
        self._residuo: Optional[tuple] = None

    @property
    def v(self):
        return self.ps.v

    # ------------------------------------------------------------ ayudas
    def _doc(self) -> Optional[Documento]:
        return self.v._documento

    def _umbral(self) -> float:
        return iman.UMBRAL_PANTALLA / max(self.v.vista.zoom, 1e-6)

    def manijas(self) -> Optional[HerramientaTransformar]:
        """Las manijas de la capa elegida (Mover con "Mostrar controles"), o None: una sola capa
        elegida, con transformación, sin candado y con su imagen."""
        doc = self.v._documento_vista()
        if doc is None or not self.ps.mostrar_controles or self.ps.herramienta != "mover":
            return None
        ids = self.v.panel_capas.capas_elegidas
        if len(ids) != 1:
            return None
        try:
            capa = doc.capa(ids[0])
        except KeyError:
            return None
        if capa.tipo not in TIPOS_CON_TRANSFORMACION or capa.bloqueada:
            return None
        clave = (capa.id, capa.transform, capa.imagen, capa.params)
        if self._herr is not None and self._clave_herr == clave and self._gesto is None:
            return self._herr
        if self._gesto is not None and self._gesto.get("tipo") == "manijas":
            return self._herr
        natural = tamano_natural(capa, self.v._almacen)
        if natural is None:
            return None
        self._herr = HerramientaTransformar(capa.transform, natural[0], natural[1],
                                            ajustar_mover=self.ps.iman_para(capa.id))
        self._clave_herr = clave
        return self._herr

    def _caja_seleccion(self, doc: Documento, ids) -> Optional[tuple]:
        cajas = [k for i in ids for k in (caja_capa(doc, i, self.v._almacen),) if k is not None]
        if not cajas:
            return None
        return (min(k[0] for k in cajas), min(k[1] for k in cajas), max(k[2] for k in cajas),
                max(k[3] for k in cajas))

    # ------------------------------------------------------------ interfaz con la vista
    def cursor(self, q: Optional[QPointF]):
        h = self.ps.herramienta
        if h == "mano":
            return Qt.OpenHandCursor
        if h == "zoom":
            return _cursor_icono("zoom-in", 9, 9)
        if h == "cuentagotas":
            return _cursor_icono("pipette", 2, 20)
        if h == "texto":
            return Qt.IBeamCursor
        if h == "formas" or h == "degradado":
            return Qt.CrossCursor
        if h in HERRAMIENTAS_PINTURA:
            # Un círculo del tamaño del pincel, dibujado en la vista (``dibujar``).
            if q is not None:
                self.raton = QPointF(q)
                self.v.vista.update()
            return Qt.BlankCursor
        if h == "bote":
            return _cursor_icono("ps-bote", 19, 20)
        if h == "recortar":
            caja = self.ps.caja_recorte_actual()
            manija = caja.manija_en(q, self.v.vista.zoom) if caja is not None and q is not None else None
            return CajaRecorte.CURSORES.get(manija, Qt.CrossCursor)
        herr = self.manijas()
        if herr is not None and q is not None:
            manija = herr.manija_en(q, self.v.vista.zoom)
            if manija not in (None, "mover"):
                return HerramientaTransformar.cursor(manija, herr.transform.rotacion)
        return Qt.SizeAllCursor if q is not None and self.ps.capa_bajo(q) is not None else Qt.ArrowCursor

    def presionar(self, q: QPointF, pos: QPointF, mods) -> bool:
        """Empieza un gesto; False: no hay nada que agarrar (la vista desplaza)."""
        h = self.ps.herramienta
        if self.ps.edicion_texto is not None:
            self.ps.terminar_texto(True)  # un clic afuera del texto que se escribe lo confirma
            self._gesto = {"tipo": "nada"}
            return True
        if h == "mano" or self._doc() is None:
            return False
        if h == "zoom":
            vista = self.v.vista
            vista.fijar_zoom(vista.zoom / 1.5 if mods & Qt.AltModifier else vista.zoom * 1.5, QPointF(pos))
            return True
        if h == "cuentagotas":
            self.ps.tomar_color(q)
            self._gesto = {"tipo": "cuentagotas"}
            return True
        if h == "texto":
            return self._presionar_texto(q)
        if h == "formas":
            g = self.ps.empezar_forma(q)
            self._gesto = g
            return g is not None
        if h in HERRAMIENTAS_PINTURA:
            self._residuo = None
            g = self.ps.empezar_trazo(q, borrar=h == "borrador")
            self._gesto = g if g is not None else {"tipo": "nada"}
            return True
        if h == "bote":
            self._gesto = {"tipo": "nada"}
            self.ps.bote_en(q)
            return True
        if h == "degradado":
            self._gesto = {"tipo": "degradado", "p0": QPointF(q), "p1": QPointF(q)}
            return True
        if h == "recortar":
            caja = self.ps.caja_recorte_actual()
            if caja is None:
                return False
            caja.empezar(caja.manija_en(q, self.v.vista.zoom), q)
            self._gesto = {"tipo": "recorte"}
            return True
        return self._presionar_mover(q, mods)

    def _texto_bajo(self, q: QPointF) -> Optional[str]:
        """La capa de texto (sin candado) que se toca en (q), o None: la de arriba que se ve ahí si es un
        texto; si no, el de más arriba cuya caja contiene (q) (así se agarra también entre las letras)."""
        doc = self.v._documento
        if doc is None:
            return None
        tocada = self.ps.capa_bajo(q)
        if tocada is not None:
            capa = doc.capa(tocada)
            if capa.tipo == "texto":
                return tocada if not capa.bloqueada else None
        for capa in reversed(doc.capas):
            if capa.tipo != "texto" or capa.bloqueada or not capa.visible:
                continue
            caja = caja_capa(doc, capa.id, self.v._almacen)
            if caja is not None and caja[0] <= q.x() <= caja[2] and caja[1] <= q.y() <= caja[3]:
                return capa.id
        return None

    def _presionar_texto(self, q: QPointF) -> bool:
        """Texto: sobre un texto, lo edita; si no, empieza uno nuevo (un clic o una caja arrastrada)."""
        tocado = self._texto_bajo(q)
        if tocado is not None:
            self.ps.editar_texto(tocado)
            self._gesto = {"tipo": "nada"}
            return True
        self._gesto = {"tipo": "texto", "p0": QPointF(q), "p1": QPointF(q)}
        return True

    def doble_clic(self, q: QPointF) -> bool:
        """Doble clic con Mover o Texto sobre una capa de texto: editarla; con Recortar, adentro del
        recuadro: aplicar. True si lo hizo."""
        if self.ps.herramienta == "recortar" and self.v._documento is not None:
            caja = self.ps.caja_recorte_actual()
            if caja is not None and caja.rect.normalized().contains(q):
                self._gesto = None
                self.ps.terminar_recorte(True)
                return True
            return False
        if self.ps.herramienta not in ("mover", "texto") or self.v._documento is None:
            return False
        tocado = self._texto_bajo(q)
        if tocado is None:
            return False
        self._gesto = None
        self.ps.editar_texto(tocado)
        return True

    def _presionar_mover(self, q: QPointF, mods) -> bool:
        v = self.v
        if v._transformando is not None:
            return False
        doc = v._documento
        panel = v.panel_capas
        # 1. Las manijas de la capa elegida (escalar y rotar).
        herr = self.manijas()
        if herr is not None:
            manija = herr.manija_en(q, v.vista.zoom)
            if manija == "rotar" and self.ps.seleccion_automatica:
                # Apenas afuera de una esquina se rota; pero si ahí se ve otra capa, el clic la elige.
                tocada = self.ps.capa_bajo(q)
                if tocada is not None and tocada not in panel.capas_elegidas:
                    manija = None
            if manija not in (None, "mover"):
                herr.empezar(manija, q)
                self._gesto = {"tipo": "manijas", "id": panel.capas_elegidas[0], "doc0": doc, "movio": False}
                return True
        # 2. La capa bajo el mouse (selección automática) o la selección.
        mayus = bool(mods & (Qt.ShiftModifier | Qt.ControlModifier))
        elegidas = panel.capas_elegidas
        tocada = self.ps.capa_bajo(q) if self.ps.seleccion_automatica else None
        if tocada is not None:
            if mayus:
                if tocada in elegidas and len(elegidas) > 1:
                    panel.elegir_varias([i for i in elegidas if i != tocada])
                    return True
                panel.elegir_varias(elegidas + [tocada], actual=tocada)
            elif tocada not in elegidas:
                panel.elegir(tocada)
            elegidas = panel.capas_elegidas
        elif self.ps.seleccion_automatica:
            caja = self._caja_seleccion(doc, elegidas)
            if caja is None or not (caja[0] <= q.x() <= caja[2] and caja[1] <= q.y() <= caja[3]):
                return False  # nada que mover ahí: desplaza la vista
        ids = self.ps.movibles(elegidas)
        if not ids:
            return tocada is not None  # se eligió (una base, un relleno o una capa bloqueada) sin moverla
        caja = self._caja_seleccion(doc, ids)
        xs, ys = iman.objetivos(doc, v._almacen, ids) if self.ps.guias_activas else ([], [])
        self._gesto = {"tipo": "mover", "ids": ids, "doc0": doc, "p0": QPointF(q), "caja": caja, "xs": xs, "ys": ys,
                       "movio": False}
        return True

    def mover(self, q: QPointF, mods) -> None:
        g = self._gesto
        if g is None:
            return
        if g["tipo"] == "cuentagotas":
            self.ps.tomar_color(q)
            return
        if g["tipo"] == "nada":
            return
        if g["tipo"] == "texto":
            g["p1"] = QPointF(q)
            return
        if g["tipo"] == "trazo":
            g["trazo"].agregar(q.x(), q.y())
            return
        if g["tipo"] == "degradado":
            g["p1"] = self._con_45(g["p0"], q) if mods & Qt.ShiftModifier else QPointF(q)
            return
        if g["tipo"] == "recorte":
            caja = self.ps.caja_recorte_actual()
            if caja is not None:
                caja.arrastrar(q, bool(mods & Qt.ShiftModifier))
            return
        v = self.v
        if g["tipo"] == "forma":
            doc = self.ps.documento_con_forma(g, q, mods)
            if doc is not None:
                g["movio"] = True
                v._al_cambiar_documento(doc, False)
            return
        if g["tipo"] == "manijas":
            herr = self._herr
            t = herr.arrastrar(q, bool(mods & Qt.ShiftModifier), bool(mods & Qt.AltModifier))
            g["movio"] = True
            self.guias = list(herr.guias)
            doc = g["doc0"].con_capa(g["id"], transform=t)
            v._al_cambiar_documento(doc, False)
            self.ps.refrescar_propiedades(doc)
            return
        dx, dy = q.x() - g["p0"].x(), q.y() - g["p0"].y()
        if mods & Qt.ShiftModifier:  # solo en un eje
            if abs(dx) >= abs(dy):
                dy = 0.0
            else:
                dx = 0.0
        self.guias = []
        if g["caja"] is not None and self.ps.guias_activas:
            x0, y0, x1, y1 = g["caja"]
            sx, sy, guias = iman.ajustar((x0 + dx, y0 + dy, x1 + dx, y1 + dy), g["xs"], g["ys"], self._umbral())
            if mods & Qt.ShiftModifier:
                sx, sy = (sx, 0.0) if dy == 0.0 else (0.0, sy)
                guias = [gu for gu in guias if (gu[0] == "v") == (dy == 0.0)]
            dx, dy = dx + sx, dy + sy
            self.guias = guias
        if abs(dx) < 1e-9 and abs(dy) < 1e-9 and not g["movio"]:
            return
        g["movio"] = True
        g["d"] = (dx, dy)
        doc = trasladar(g["doc0"], g["ids"], dx, dy)
        v._al_cambiar_documento(doc, False)
        self.ps.refrescar_propiedades(doc)

    @staticmethod
    def _con_45(p0: QPointF, q: QPointF) -> QPointF:
        """q, llevado a la dirección de a 45° más cercana desde p0 (Mayús)."""
        dx, dy = q.x() - p0.x(), q.y() - p0.y()
        largo = math.hypot(dx, dy)
        angulo = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
        return QPointF(p0.x() + largo * math.cos(angulo), p0.y() + largo * math.sin(angulo))

    def cancelar(self) -> bool:
        """Esc durante un trazo o un degradado: se descarta. True si había uno."""
        g = self._gesto
        if g is None or g.get("tipo") not in ("trazo", "degradado"):
            return False
        self._gesto = None
        self.v.vista.update()
        return True

    def salio(self) -> None:
        """El mouse salió de la vista: el círculo del pincel se va con él."""
        if self.raton is not None and (self._gesto is None or self._gesto.get("tipo") != "trazo"):
            self.raton = None
            self.v.vista.update()

    def soltar(self, q: QPointF, mods) -> None:
        g, self._gesto = self._gesto, None
        self.guias = []
        if g is None or g["tipo"] in ("cuentagotas", "nada"):
            return
        v = self.v
        if g["tipo"] == "trazo":
            hecho = self.ps.terminar_trazo(g)
            self._residuo = (g["trazo"], v.vista._despues) if hecho else None
            return
        if g["tipo"] == "degradado":
            p1 = self._con_45(g["p0"], q) if mods & Qt.ShiftModifier else QPointF(q)
            d = p1 - g["p0"]
            if math.hypot(d.x(), d.y()) * v.vista.zoom >= 3:
                self.ps.aplicar_degradado(g["p0"], p1)
            return
        if g["tipo"] == "recorte":
            caja = self.ps.caja_recorte_actual()
            if caja is not None:
                caja.soltar()
            self.ps.texto_recorte()
            return
        if g["tipo"] == "texto":
            r = QRectF(g["p0"], g["p1"]).normalized()
            if r.width() * v.vista.zoom >= 12:
                self.ps.nuevo_texto(r.left(), r.top(), ancho_caja=r.width())
            else:
                self.ps.nuevo_texto(g["p0"].x(), g["p0"].y())
            return
        if g["tipo"] == "forma":
            doc = self.ps.documento_con_forma(g, q, mods) if g.get("movio") else None
            if doc is not None:
                self.ps.confirmar_forma(g, doc)
            elif v._doc_provisorio is not None:
                v._doc_provisorio = None
                v.solicitar_render()
            return
        if not g.get("movio"):
            return
        if g["tipo"] == "manijas":
            herr = self._herr
            herr.soltar()
            t = herr.transform
            nombre = g["doc0"].capa(g["id"]).nombre
            doc = g["doc0"].con_capa(g["id"], transform=t)
            self.ps.confirmar(doc, f"Capa «{nombre}» transformada")
            return
        ids = g["ids"]
        dx, dy = g.get("d", (0.0, 0.0))
        doc = trasladar(g["doc0"], ids, dx, dy)
        texto = f"Capa «{g['doc0'].capa(ids[0]).nombre}» movida" if len(ids) == 1 else f"{len(ids)} capas movidas"
        self.ps.confirmar(doc, texto)

    def tecla(self, evento) -> bool:
        """Flechas: mueven lo elegido de a 1 px (10 con Mayús), con Mover. Enter, con Recortar: aplica."""
        k = evento.key()
        if self.ps.herramienta == "recortar" and k in (Qt.Key_Return, Qt.Key_Enter) and self.v._documento is not None:
            self.ps.terminar_recorte(True)
            return True
        if self.ps.herramienta != "mover" or self.v._documento is None:
            return False
        if k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            paso = 10.0 if evento.modifiers() & Qt.ShiftModifier else 1.0
            dx = {Qt.Key_Left: -paso, Qt.Key_Right: paso}.get(k, 0.0)
            dy = {Qt.Key_Up: -paso, Qt.Key_Down: paso}.get(k, 0.0)
            return self.ps.empujar(dx, dy)
        return False

    @staticmethod
    def _rect_punteado(p: QPainter, rect: QRectF, color: str = "#ffffff") -> None:
        p.save()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 150), 3))
        p.drawRect(rect)
        p.setPen(QPen(QColor(color), 1.2, Qt.DashLine))
        p.drawRect(rect)
        p.restore()

    def _dibujar_seleccion(self, p: QPainter, a_pantalla) -> None:
        """El recuadro punteado de lo elegido (sin manijas)."""
        doc = self.v._documento_vista()
        ids = self.v.panel_capas.capas_elegidas if doc is not None else []
        ids = [i for i in ids if doc is not None and any(c.id == i for c in doc.capas)
               and doc.capa(i).tipo not in ("foto", "ajuste_natural")]
        if doc is not None and ids and not (len(ids) == 1 and doc.capa(ids[0]).tipo == "relleno"):
            caja = self._caja_seleccion(doc, ids)
            if caja is not None:
                a, b = a_pantalla(QPointF(caja[0], caja[1])), a_pantalla(QPointF(caja[2], caja[3]))
                self._rect_punteado(p, QRectF(a, b))

    def _dibujar_pincel(self, p: QPainter, a_pantalla, zoom: float) -> None:
        """El trazo que se arrastra y el círculo del pincel."""
        g = self._gesto
        pos = self.raton
        if g is not None and g.get("tipo") == "trazo":
            g["trazo"].dibujar(p, a_pantalla(QPointF(0, 0)), zoom)
            pos = g["trazo"].ultimo_doc or pos
        if pos is None:
            return
        radio = self.ps.opciones_pincel()["tamano"] / 2.0 * zoom
        c = a_pantalla(pos)
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrush(Qt.NoBrush)
        if radio >= 3:
            p.setPen(QPen(QColor(0, 0, 0, 150), 2.6))
            p.drawEllipse(c, radio, radio)
            p.setPen(QPen(QColor(255, 255, 255, 230), 1.1))
            p.drawEllipse(c, radio, radio)
        if radio < 8:  # chico: una cruz para saber dónde cae
            for color, ancho in ((QColor(0, 0, 0, 150), 2.6), (QColor(255, 255, 255, 230), 1.1)):
                p.setPen(QPen(color, ancho))
                p.drawLine(QPointF(c.x() - 7, c.y()), QPointF(c.x() - 3, c.y()))
                p.drawLine(QPointF(c.x() + 3, c.y()), QPointF(c.x() + 7, c.y()))
                p.drawLine(QPointF(c.x(), c.y() - 7), QPointF(c.x(), c.y() - 3))
                p.drawLine(QPointF(c.x(), c.y() + 3), QPointF(c.x(), c.y() + 7))
        p.restore()

    def _dibujar_degradado(self, p: QPainter, a_pantalla) -> None:
        g = self._gesto
        if g is None or g.get("tipo") != "degradado":
            return
        a, b = a_pantalla(g["p0"]), a_pantalla(g["p1"])
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor(0, 0, 0, 160), 3.2))
        p.drawLine(a, b)
        p.setPen(QPen(QColor("#ffffff"), 1.4))
        p.drawLine(a, b)
        colores = self.ps.relleno_degradado_efectivo().colores
        for punto, color in ((a, colores[0]), (b, colores[-1])):
            p.setPen(QPen(QColor("#ffffff"), 1.6))
            p.setBrush(QColor(*color[:3]))
            p.drawEllipse(punto, 5.5, 5.5)
        p.restore()

    def dibujar(self, p: QPainter, a_pantalla: Callable[[QPointF], QPointF], zoom: float) -> None:
        h = self.ps.herramienta
        residuo = self._residuo
        if residuo is not None:
            if residuo[1] is not None and residuo[1] is self.v.vista._despues:
                residuo[0].dibujar(p, a_pantalla(QPointF(0, 0)), zoom)
            else:
                self._residuo = None  # ya llegó la vista con el trazo
        if h in HERRAMIENTAS_PINTURA:
            self._dibujar_pincel(p, a_pantalla, zoom)
            return
        if h == "degradado":
            self._dibujar_degradado(p, a_pantalla)
            return
        if h == "recortar":
            caja = self.ps.caja_recorte_actual()
            if caja is not None:
                vista = self.v.vista
                caja.dibujar(p, a_pantalla, vista._ancho_vista(), vista.height())
            return
        if h == "bote":
            return
        edicion = self.ps.edicion_texto
        if edicion is not None:
            r = edicion.rect_pantalla()
            if r is not None:
                self._rect_punteado(p, r.adjusted(-3, -3, 3, 3), "#d946ef")
            edicion.reubicar_luego()
            return
        if h == "texto":
            g = self._gesto
            if g is not None and g.get("tipo") == "texto":
                r = QRectF(a_pantalla(g["p0"]), a_pantalla(g["p1"])).normalized()
                if r.width() >= 12:
                    self._rect_punteado(p, r, "#d946ef")
                return
            self._dibujar_seleccion(p, a_pantalla)
            return
        if h == "formas":
            if self._gesto is None:
                self._dibujar_seleccion(p, a_pantalla)
            return
        if h != "mover":
            return
        herr = self.manijas()
        if herr is not None:
            herr.dibujar(p, a_pantalla, zoom)
        else:
            self._dibujar_seleccion(p, a_pantalla)
        dibujar_guias(p, self.guias, a_pantalla)


# ---------------------------------------------------------------------------
# El modo
# ---------------------------------------------------------------------------

class ModoPhotoshop(QObject):
    """Lo propio del modo Photoshop (ver el módulo). ``ventana``: la ``VentanaPrincipal``."""

    def __init__(self, ventana):
        super().__init__(ventana)
        self.v = ventana
        self.herramienta = "mover"  # la herramienta elegida (las de máscara son de una pasada)
        self.seleccion_automatica = True
        self.mostrar_controles = True
        self.guias_activas = True
        self.transformando: Optional[tuple] = None  # transformación libre: (id de la capa, transformación de antes)
        self.textos_capas: dict = {}  # kit: id de capa -> datos del texto (para volver a editarlo)
        self.quitando_fondo = False
        self._caja_recorte: Optional[CajaRecorte] = None  # el recuadro de Recortar (C)
        # Pincel, Borrador, Bote y Degradado (U3): los valores de la barra de opciones.
        self.pinceles = {"pintar": {"tamano": 20.0, "dureza": 0.8, "opacidad": 1.0},
                         "borrador": {"tamano": 40.0, "dureza": 0.8, "opacidad": 1.0}}
        self.opciones_bote = {"tolerancia": 32, "contiguo": True, "todas": False}
        self.degradado_radial = False
        self.relleno_degradado: Optional[Relleno] = None  # None: del color de frente al de fondo
        self.opacidad_degradado = 1.0
        self._ultima_de_bote = "bote"  # el botón del Bote también es el del Degradado
        self._capas_pendientes: list = []  # "Abrir como capas" sin documento: las que van cuando abra
        self.controlador = ControladorVista(self)
        self.colores: Optional[ColoresFrenteFondo] = None
        self.propiedades: Optional[PanelPropiedades] = None
        self.botones_herramienta: dict[str, QPushButton] = {}
        # Texto y Formas (U2): los valores para lo próximo que se cree (la barra de opciones).
        self.edicion_texto: Optional[EdicionTexto] = None
        self.params_texto = ParamsTexto("", "Arial", 72.0, (0, 0, 0, 255))
        self.params_forma = ParamsForma("rectangulo", relleno=Relleno("color", ((0, 0, 0, 255),)))
        self.alto_forma = {"linea": 8.0, "flecha": 60.0}  # grosor de la línea y alto de la flecha
        self.dialogo_estilos = None

    # ================================================================== armado
    def construir_columna_izquierda(self) -> QWidget:
        """La barra vertical de herramientas (con los colores abajo) y, al lado, el Historial (la
        tarjeta se muda acá al entrar al modo: ``mudar_historial``)."""
        v = self.v
        caja = QWidget()
        fila = QHBoxLayout(caja)
        fila.setContentsMargins(16, 4, 16, 12)
        fila.setSpacing(10)
        barra = QFrame()
        barra.setObjectName("barraHerramientasPS")
        columna = QVBoxLayout(barra)
        columna.setContentsMargins(4, 5, 4, 7)
        columna.setSpacing(2)  # 14 herramientas: tienen que entrar a 768 px de alto
        self.grupo_herramientas = QButtonGroup(self)
        self.grupo_herramientas.setExclusive(False)  # se marca a mano (las de máscara son de una pasada)
        for datos in HERRAMIENTAS:
            if datos is None:
                linea = QFrame()
                linea.setFixedHeight(1)
                linea.setStyleSheet(f"background: {estilo.BORDE};")
                columna.addSpacing(2)
                columna.addWidget(linea)
                columna.addSpacing(2)
                continue
            clave, icono, tecla, ayuda = datos
            b = QPushButton()
            b.setObjectName("botonHerramientaPS")
            b.setIcon(iconos.icono(icono, 18))
            b.setIconSize(QSize(18, 18))
            b.setFixedSize(36, 34)
            b.setCheckable(True)
            b.setToolTip(ayuda)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.setProperty("herramienta", clave)
            columna.addWidget(b)
            self.botones_herramienta[clave] = b
            if clave in HERRAMIENTAS_MASCARA:
                b.clicked.connect(lambda _c=False, f=clave: self.herramienta_mascara(f))
            else:
                b.clicked.connect(lambda _c=False, h=clave: self.elegir_herramienta(h))
            if clave == "formas":  # clic derecho: qué forma
                self.menu_formas = QMenu(b)
                for tipo, nombre in NOMBRES_FORMA.items():
                    self.menu_formas.addAction(iconos.icono(ICONOS_FORMA[tipo], 15), nombre,
                                               lambda t=tipo: self.elegir_forma(t))
                b.setContextMenuPolicy(Qt.CustomContextMenu)
                b.customContextMenuRequested.connect(
                    lambda pos, boton=b: self.menu_formas.exec(boton.mapToGlobal(pos)))
            if clave == "bote":  # clic derecho: Bote o Degradado (comparten el botón, como en Photoshop)
                self.menu_bote = QMenu(b)
                self.menu_bote.addAction(iconos.icono("ps-bote", 15), "Bote de pintura\tG",
                                         lambda: self.elegir_herramienta("bote"))
                self.menu_bote.addAction(iconos.icono("ps-degradado", 15), "Degradado\tMayús+G",
                                         lambda: self.elegir_herramienta("degradado"))
                b.setContextMenuPolicy(Qt.CustomContextMenu)
                b.customContextMenuRequested.connect(
                    lambda pos, boton=b: self.menu_bote.exec(boton.mapToGlobal(pos)))
                b.clicked.disconnect()
                b.clicked.connect(lambda _c=False: self.elegir_herramienta(self._ultima_de_bote))
        columna.addStretch(1)
        self.colores = ColoresFrenteFondo()
        self.colores.cambiados.connect(self._al_cambiar_colores)
        columna.addWidget(self.colores, 0, Qt.AlignHCenter)
        fila.addWidget(barra)
        self.caja_historial = QWidget()
        self.capa_historial = QVBoxLayout(self.caja_historial)
        self.capa_historial.setContentsMargins(0, 0, 0, 0)
        self.capa_historial.setSpacing(0)
        fila.addWidget(self.caja_historial, 1)
        caja.hide()
        self.panel_herramientas = caja
        # Los nombres de siempre de la ventana (las pruebas y el resto de la app los usan).
        v.botones_herramienta_ps = self.botones_herramienta
        v.boton_transformar = self.botones_herramienta["mover"]
        return caja

    def construir_columna_derecha(self) -> QWidget:
        """Propiedades arriba y Capas abajo."""
        derecho = QFrame()
        derecho.setObjectName("panelDerecho")
        derecho.setFixedWidth(340)
        capa = QVBoxLayout(derecho)
        capa.setContentsMargins(16, 14, 12, 12)
        capa.setSpacing(10)
        self.propiedades = PanelPropiedades()
        self.propiedades.cambioPedido.connect(self._al_pedir_cambio)
        capa.addWidget(self.propiedades)
        capa.addWidget(self.v.panel_capas, 1)
        derecho.hide()
        self.panel_derecho = derecho
        self.v.panel_capas.seleccionCambiada.connect(lambda _ids: self.al_cambiar_seleccion())
        self.v.panel_capas.estilosPedidos.connect(lambda i: self.estilo_de_capa(i))
        self.v.panel_capas.editarTextoPedido.connect(lambda i: self.editar_texto(i))
        return derecho

    def construir_menu(self) -> QMenuBar:
        """El menú del modo (Archivo, Editar, Imagen, Capa, Ver). Los atajos que ya tiene la ventana
        (Ctrl+Z, Ctrl+S…) se muestran en el texto; los nuevos están en ``atajos``."""
        v = self.v
        barra = QMenuBar()
        barra.setObjectName("menuPS")
        barra.setNativeMenuBar(False)
        barra.setStyleSheet(ESTILO_MENU)
        barra.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.menus: dict[str, QMenu] = {}
        self.acciones: dict[str, QAction] = {}

        def menu(clave: str, titulo: str, padre=None) -> QMenu:
            m = (padre or barra).addMenu(titulo)
            self.menus[clave] = m
            return m

        def accion(m: QMenu, clave: str, texto: str, funcion, atajo: str = "", icono: Optional[str] = None,
                   marcable: bool = False) -> QAction:
            a = QAction(texto + (f"\t{atajo}" if atajo else ""), m)
            if icono:
                a.setIcon(iconos.icono(icono, 15))
            if marcable:
                a.setCheckable(True)
                a.toggled.connect(funcion)
            else:
                a.triggered.connect(lambda _c=False: funcion())
            m.addAction(a)
            self.acciones[clave] = a
            return a

        m = menu("archivo", "Archivo")
        accion(m, "nuevo", "Nuevo…", lambda: self.nuevo_lienzo(), "Ctrl+N", "file-plus")
        accion(m, "abrir", "Abrir…", v.elegir_archivo, "Ctrl+O", iconos.ABRIR)
        accion(m, "abrir_capas", "Abrir como capas…", self.abrir_como_capas, "Ctrl+Mayús+O", "image-plus")
        accion(m, "abrir_proyecto", "Abrir proyecto…", v.elegir_proyecto)
        m.addSeparator()
        accion(m, "guardar", "Guardar proyecto", v.guardar_proyecto, "Ctrl+S", "save")
        accion(m, "guardar_como", "Guardar proyecto como…", v.guardar_proyecto_como, "Ctrl+Mayús+S")
        m.addSeparator()
        accion(m, "exportar", "Exportar con el filtro…", v.exportar, "Ctrl+Mayús+E", iconos.CELULAR)
        accion(m, "exportar_sin", "Exportar sin el filtro…", lambda: v.exportar(con_filtro=False), "", "image")

        m = menu("editar", "Editar")
        accion(m, "deshacer", "Deshacer", v.deshacer, "Ctrl+Z", "undo-2")
        accion(m, "rehacer", "Rehacer", v.rehacer, "Ctrl+Y", "redo-2")
        m.addSeparator()
        accion(m, "pegar", "Pegar como capa", self.pegar, "Ctrl+V")
        m.addSeparator()
        accion(m, "duplicar", "Duplicar capa", self.duplicar, "Ctrl+J", "copy")
        accion(m, "borrar", "Borrar capa", self.borrar, "Supr", "trash-2")
        m.addSeparator()
        accion(m, "transformar", "Transformación libre", lambda: self.alternar_transformar(True), "Ctrl+T", "move")

        m = menu("imagen", "Imagen")
        accion(m, "tamano_imagen", "Tamaño de imagen…", self.tamano_imagen, "Ctrl+Alt+I")
        accion(m, "tamano_lienzo", "Tamaño del lienzo…", self.tamano_lienzo, "Ctrl+Alt+C")
        m.addSeparator()
        rotar = menu("rotar", "Rotar lienzo", m)
        accion(rotar, "rotar_90", "90° horario", lambda: self.rotar(90), "", "rotate-cw-square")
        accion(rotar, "rotar_270", "90° antihorario", lambda: self.rotar(270), "", "rotate-ccw-square")
        accion(rotar, "rotar_180", "180°", lambda: self.rotar(180))
        voltear = menu("voltear", "Voltear lienzo", m)
        accion(voltear, "voltear_h", "Horizontal", lambda: self.voltear("h"), "", "flip-horizontal-2")
        accion(voltear, "voltear_v", "Vertical", lambda: self.voltear("v"), "", "flip-vertical-2")
        m.addSeparator()
        accion(m, "recortar", "Recortar", self.recortar, "C", "crop")

        m = menu("capa", "Capa")
        nueva = menu("nueva", "Nueva", m)
        accion(nueva, "nueva_pixeles", "Capa de píxeles", self.nueva_capa_pixeles, "Ctrl+Mayús+N", "paintbrush")
        accion(nueva, "nueva_relleno", "Capa de relleno (color de frente)", self.nueva_capa_relleno, "", "droplets")
        accion(m, "duplicar_capa", "Duplicar capa", self.duplicar, "Ctrl+J", "copy")
        accion(m, "borrar_capa", "Borrar capa", self.borrar, "Supr", "trash-2")
        m.addSeparator()
        accion(m, "agrupar", "Agrupar", self.agrupar, "Ctrl+G", "folder-open")
        accion(m, "desagrupar", "Desagrupar", self.desagrupar, "Ctrl+Mayús+G")
        m.addSeparator()
        accion(m, "rasterizar", "Rasterizar", self.rasterizar, "", "paintbrush")
        accion(m, "estilo", "Estilo de capa…", lambda: self.estilo_de_capa(), "", "ps-fx")
        mascara = menu("mascara", "Máscara", m)
        p = v.panel_capas
        accion(mascara, "mascara_agregar", "Agregar (se ve todo)", p.agregar_mascara, "", "contrast")
        accion(mascara, "mascara_mostrar", "Mostrar todo", lambda: p.mascara_llena(255), "", "eye")
        accion(mascara, "mascara_ocultar", "Ocultar todo", lambda: p.mascara_llena(0), "", "eye-off")
        accion(mascara, "mascara_invertir", "Invertir", p.invertir_mascara)
        accion(mascara, "mascara_quitar", "Quitar máscara", p.quitar_mascara, "", "x")
        m.addSeparator()
        alin = menu("alinear", "Alinear", m)
        for modo in MODOS_ALINEAR:
            accion(alin, f"alinear_{modo}", NOMBRES_ALINEAR[modo].capitalize(), lambda m_=modo: self.alinear(m_), "",
                   ICONOS_ALINEAR[modo])
        dist = menu("distribuir", "Distribuir", m)
        accion(dist, "distribuir_h", "En horizontal", lambda: self.distribuir("h"), "", "ps-distribuir-h")
        accion(dist, "distribuir_v", "En vertical", lambda: self.distribuir("v"), "", "ps-distribuir-v")
        m.addSeparator()
        accion(m, "combinar", "Combinar hacia abajo", self.combinar_abajo)
        accion(m, "acoplar", "Acoplar imagen", self.acoplar)

        m = menu("ver", "Ver")
        accion(m, "acercar", "Acercar", v.vista_acercar, "Ctrl++", "zoom-in")
        accion(m, "alejar", "Alejar", v.vista_alejar, "Ctrl+−", "zoom-out")
        accion(m, "ajustar", "Ajustar a la ventana", v.vista_ajustar, "Ctrl+0", "maximize")
        accion(m, "100", "100 %", v.vista_100, "Ctrl+1")
        m.addSeparator()
        guias = accion(m, "guias", "Guías inteligentes (imán)", self.establecer_guias, "", None, marcable=True)
        guias.setChecked(True)
        for m in self.menus.values():
            m.aboutToShow.connect(self.actualizar_menu)
        barra.hide()
        self.barra_menu = barra
        return barra

    def construir_opciones(self) -> QWidget:
        """La barra de opciones (arriba de la vista): una página por herramienta."""
        v = self.v
        barra = QFrame()
        barra.setObjectName("barraRecorte")
        fila = QHBoxLayout(barra)
        fila.setContentsMargins(10, 4, 10, 4)
        fila.setSpacing(8)
        self.icono_opciones = QLabel()
        fila.addWidget(self.icono_opciones)
        self.paginas_opciones = QStackedWidget()
        self.paginas_opciones.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        fila.addWidget(self.paginas_opciones, 1)
        self._paginas: dict[str, int] = {}

        def pagina(clave: str) -> QHBoxLayout:
            w = QWidget()
            capa = QHBoxLayout(w)
            capa.setContentsMargins(0, 0, 0, 0)
            capa.setSpacing(8)
            self._paginas[clave] = self.paginas_opciones.addWidget(w)
            return capa

        def nota(texto: str) -> QLabel:
            e = QLabel(texto)
            e.setObjectName("nota")
            e.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            return e

        def boton_chico(icono: str, ayuda: str, funcion, texto: str = "") -> QPushButton:
            b = QPushButton(texto)
            if icono:
                b.setIcon(iconos.icono(icono, 15))
            b.setToolTip(ayuda)
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False: funcion())
            return b

        # Mover.
        capa = pagina("mover")
        self.check_auto = QCheckBox("Selección automática")
        self.check_auto.setChecked(True)
        self.check_auto.setFocusPolicy(Qt.NoFocus)
        self.check_auto.setToolTip("Un clic en la vista elige la capa de arriba bajo el mouse (si no, se mueve "
                                   "la elegida en el panel Capas)")
        self.check_auto.toggled.connect(lambda x: setattr(self, "seleccion_automatica", x))
        self.check_controles = QCheckBox("Mostrar controles")
        self.check_controles.setChecked(True)
        self.check_controles.setFocusPolicy(Qt.NoFocus)
        self.check_controles.setToolTip("Las manijas de la capa elegida: escalar (libre; Mayús mantiene la "
                                         "proporción) y rotar")
        self.check_controles.toggled.connect(self._al_mostrar_controles)
        capa.addWidget(self.check_auto)
        capa.addWidget(self.check_controles)
        self.botones_alinear: dict[str, QPushButton] = {}
        botones = []
        for modo in MODOS_ALINEAR:
            b = boton_chico(ICONOS_ALINEAR[modo], f"Alinear {NOMBRES_ALINEAR[modo]} (con una capa: respecto del "
                            "lienzo; con varias: entre ellas)", lambda m=modo: self.alinear(m))
            self.botones_alinear[modo] = b
            botones.append(b)
        capa.addWidget(v._segmento(botones))
        self.botones_distribuir = {
            "h": boton_chico("ps-distribuir-h", "Distribuir en horizontal (3 capas o más)", lambda: self.distribuir("h")),
            "v": boton_chico("ps-distribuir-v", "Distribuir en vertical (3 capas o más)", lambda: self.distribuir("v")),
        }
        capa.addWidget(v._segmento(list(self.botones_distribuir.values())))
        capa.addStretch(1)

        # Mano.
        capa = pagina("mano")
        capa.addWidget(nota("Arrastrá para desplazar la vista. Con cualquier herramienta, mantené Espacio."), 1)
        capa.addWidget(v._segmento([boton_chico("maximize", "Ver todo el lienzo (Ctrl+0)", v.vista_ajustar),
                                    boton_chico("", "Tamaño real (Ctrl+1)", v.vista_100, "100 %")]))

        # Zoom.
        capa = pagina("zoom")
        capa.addWidget(nota("Clic para acercar; Alt+clic para alejar. También con la rueda del mouse."), 1)
        capa.addWidget(v._segmento([boton_chico("zoom-in", "Acercar (Ctrl++)", v.vista_acercar),
                                    boton_chico("zoom-out", "Alejar (Ctrl+−)", v.vista_alejar),
                                    boton_chico("maximize", "Ver todo el lienzo (Ctrl+0)", v.vista_ajustar)]))

        # Cuentagotas.
        capa = pagina("cuentagotas")
        capa.addWidget(nota("Clic (o arrastrá) sobre la imagen: ese color pasa a ser el de frente."), 1)
        etiqueta = QLabel("Muestra")
        etiqueta.setObjectName("etiquetaControl")
        self.combo_muestra = QComboBox()
        for texto, radio in (("1 píxel", 0), ("Promedio 3 × 3", 1), ("Promedio 5 × 5", 2)):
            self.combo_muestra.addItem(texto, radio)
        self.combo_muestra.setFocusPolicy(Qt.NoFocus)
        self.combo_muestra.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        capa.addWidget(etiqueta)
        capa.addWidget(self.combo_muestra)

        # Máscara (rectángulo, elipse, lazo y pincel): si lo pintado se ve o se oculta, y el pincel.
        capa = pagina("mascara")
        self.etiqueta_mascara = QLabel("Máscara:")
        self.etiqueta_mascara.setObjectName("etiquetaControl")
        self.etiqueta_mascara.setToolTip("Pintá la máscara de la capa elegida: lo que marques se ve o se oculta")
        capa.addWidget(self.etiqueta_mascara)
        self.grupo_mascara = QButtonGroup(self)
        self.grupo_mascara.setExclusive(True)
        self.botones_mascara: dict[str, QPushButton] = {}
        botones = []
        for modo, texto, ayuda in (("mostrar", " Se ve", "Se ve: lo que pintes en la máscara se ve"),
                                   ("ocultar", " Se oculta", "Se oculta: lo que pintes en la máscara se oculta")):
            b = QPushButton()  # solo el ícono (el texto, en la ayuda): la barra entra a 1366 px
            b.setIcon(iconos.icono("eye" if modo == "mostrar" else "eye-off", 15))
            b.setCheckable(True)
            b.setChecked(modo == "ocultar")
            b.setToolTip(ayuda)
            b.setFocusPolicy(Qt.NoFocus)
            self.grupo_mascara.addButton(b)
            self.botones_mascara[modo] = b
            botones.append(b)
        capa.addWidget(v._segmento(botones))
        capa.addStretch(1)
        self.sliders_pincel: dict[str, QSlider] = {}
        for clave, texto, ayuda in (
            ("tam", "Tamaño", "Tamaño del pincel. Con el teclado: [ y ] (o − y +)."),
            ("dureza", "Dureza", "Borde del pincel: a la izquierda suave (se funde), a la derecha duro."),
        ):
            etiqueta = QLabel(texto)
            etiqueta.setObjectName("etiquetaControl")
            etiqueta.setToolTip(ayuda)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setFocusPolicy(Qt.NoFocus)
            slider.setFixedWidth(64)
            slider.setToolTip(ayuda)
            slider.valueChanged.connect(lambda val, c=clave: v.vista.establecer_pincel(**{c: val}))
            self.sliders_pincel[clave] = slider
            capa.addWidget(etiqueta)
            capa.addWidget(slider)
            self._widgets_pincel = getattr(self, "_widgets_pincel", []) + [etiqueta, slider]
        self.boton_goma = QPushButton()
        self.boton_goma.setIcon(iconos.icono("eraser", 15))
        self.boton_goma.setCheckable(True)
        self.boton_goma.setFocusPolicy(Qt.NoFocus)
        self.boton_goma.setToolTip("Goma: borrar lo pintado de más (tecla E). También con el clic derecho.")
        self.boton_goma.toggled.connect(lambda val: v.vista.establecer_pincel(goma=val))
        listo = boton_chico("check", "Terminar de pintar (Enter)", lambda: v.vista.terminar_pincel(), " Listo")
        listo.setObjectName("botonPrimario")
        listo.setIcon(iconos.icono("check", 15, color="#ffffff"))
        listo.setMinimumWidth(listo.sizeHint().width() + 6)
        cancelar = boton_chico("x", "Cancelar: descartar lo pintado ahora (Esc)", v.cancelar_herramienta)
        for w in (self.boton_goma, cancelar, listo):
            capa.addWidget(w)
        self._widgets_pincel += [self.boton_goma, cancelar, listo]

        # Texto: fuente, tamaño, color, estilo, alineación, interlineado y espaciado.
        capa = pagina("texto")
        self.opciones_texto = ControlesTexto(vertical=False)
        self.opciones_texto.cambio.connect(self._al_cambiar_opciones_texto)
        capa.addWidget(self.opciones_texto)
        capa.addStretch(1)

        # Formas: tipo, relleno, trazo y lo de cada tipo.
        capa = pagina("formas")
        self.opciones_forma = ControlesForma(vertical=False)
        self.opciones_forma.cambio.connect(self._al_cambiar_opciones_forma)
        capa.addWidget(self.opciones_forma)
        capa.addStretch(1)

        # Pincel y Borrador (U3): tamaño, dureza y opacidad (cada uno recuerda los suyos).
        capa = pagina("pintar")
        self.opciones_pintura = ControlesPincel()
        self.opciones_pintura.cambio.connect(self._al_cambiar_opciones_pincel)
        capa.addWidget(self.opciones_pintura)
        capa.addStretch(1)

        # Bote de pintura (U3): tolerancia, contiguo y todas las capas.
        capa = pagina("bote")
        self.opciones_bote_ui = ControlesBote()
        self.opciones_bote_ui.cambio.connect(self._al_cambiar_opciones_bote)
        capa.addWidget(self.opciones_bote_ui)
        capa.addWidget(nota("Clic: rellena con el color de frente."), 1)

        # Degradado (U3): lineal o radial, colores y opacidad.
        capa = pagina("degradado")
        self.opciones_degradado = ControlesDegradado()
        self.opciones_degradado.cambio.connect(self._al_cambiar_opciones_degradado)
        capa.addWidget(self.opciones_degradado)
        capa.addStretch(1)  # (cómo se usa, en la barra de estado: no entra a 1366 px)

        # Recortar (C): proporción, Aplicar y Cancelar.
        capa = pagina("recortar")
        etiqueta = QLabel("Proporción")
        etiqueta.setObjectName("etiquetaControl")
        capa.addWidget(etiqueta)
        self.combo_aspecto = QComboBox()
        for texto, valor in ASPECTOS_RECORTE:
            self.combo_aspecto.addItem(texto, valor)
        self.combo_aspecto.setFocusPolicy(Qt.NoFocus)
        self.combo_aspecto.setToolTip("Proporción del recorte (Libre: la que quieras; con Mayús en una esquina, "
                                      "mantiene la del recuadro)")
        self.combo_aspecto.currentIndexChanged.connect(lambda _i: self._al_cambiar_aspecto())
        capa.addWidget(self.combo_aspecto)
        nota_recorte = nota("Enter aplica · Esc cancela")
        nota_recorte.setToolTip("Ajustá el recuadro con las manijas, arrastrá adentro para moverlo o afuera para "
                                "uno nuevo. Enter (o doble clic adentro) aplica; Esc cancela.")
        capa.addWidget(nota_recorte, 1)
        cancelar = boton_chico("", "Dejar el lienzo como estaba (Esc)", lambda: self.terminar_recorte(False),
                               "Cancelar")
        aplicar = boton_chico("check", "Recortar el lienzo (Enter): un paso del historial",
                              lambda: self.terminar_recorte(True), " Aplicar")
        aplicar.setObjectName("botonPrimario")
        aplicar.setIcon(iconos.icono("check", 15, color="#ffffff"))
        capa.addWidget(cancelar)
        capa.addWidget(aplicar)

        barra.hide()
        self.barra_opciones = barra
        v.botones_mascara_ps = self.botones_mascara
        v.sliders_pincel_ps = self.sliders_pincel
        self._mostrar_opciones("mover")
        return barra

    def _mostrar_opciones(self, clave: str) -> None:
        if not hasattr(self, "paginas_opciones"):
            return
        icono = {"mover": "move", "mano": "hand", "zoom": "zoom-in", "cuentagotas": "pipette", "mascara": "contrast",
                 "recortar": "crop", "texto": "type", "pintar": "paintbrush", "borrador": "eraser", "bote": "ps-bote",
                 "degradado": "ps-degradado",
                 "formas": ICONOS_FORMA.get(self.params_forma.tipo, "ps-rectangulo")}.get(clave, "move")
        self.icono_opciones.setPixmap(iconos.pixmap(icono, 16))
        pagina = "pintar" if clave in HERRAMIENTAS_PINTURA else clave
        self.paginas_opciones.setCurrentIndex(self._paginas.get(pagina, 0))

    # ================================================================== estado general
    @property
    def activo(self) -> bool:
        return self.v._modo == PHOTOSHOP

    @property
    def modo_mascara(self) -> str:
        """"mostrar" u "ocultar": cómo pintan la máscara las herramientas del modo Photoshop."""
        return "mostrar" if self.botones_mascara["mostrar"].isChecked() else "ocultar"

    def mudar_historial(self, a_photoshop: bool) -> None:
        """El historial es uno solo: en el modo Photoshop, a la izquierda (al lado de las
        herramientas); en el Editor, en su columna."""
        v = self.v
        destino = self.capa_historial if a_photoshop else v._capa_hist_izquierda
        if v._tarjeta_historial.parentWidget() is not destino.parentWidget():
            destino.addWidget(v._tarjeta_historial)
        v.lista_historial.setMinimumHeight(0)
        if a_photoshop:
            v.lista_historial.setMaximumHeight(16777215)
            v.lista_historial.setMinimumHeight(120)
            v.lista_historial.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
            self.capa_historial.setStretchFactor(v._tarjeta_historial, 1)
        else:
            v.lista_historial.setFixedHeight(150)

    def al_cambiar_modo(self, entra: bool, sale: bool) -> None:
        """La ventana cambió de modo: entrar a Photoshop pone la herramienta en la vista; salir la saca."""
        v = self.v
        en_ps = v._modo == PHOTOSHOP
        self.barra_menu.setVisible(en_ps)
        self.barra_opciones.setVisible(en_ps)
        if sale:
            self.terminar_texto(True)
            if self.recortando:
                self.terminar_recorte(False)
            if v.vista.herramienta == "ps":
                v.vista.establecer_herramienta(None)
            v.vista.establecer_mano_temporal(False)
        if entra:
            self.reponer_herramienta()
            self.refrescar_propiedades()

    def actualizar_habilitados(self, hay: bool) -> None:
        """Lo del modo que depende de que haya imagen y de la capa elegida (lo llama la ventana)."""
        v = self.v
        elegida = self.capa_elegida() if hay else None
        pintable = elegida is not None and elegida.tipo != "ajuste_natural" and not elegida.bloqueada
        for clave in HERRAMIENTAS_MASCARA:
            self.botones_herramienta[clave].setEnabled(pintable)
        v.boton_agregar_capa.setEnabled(hay)
        v.boton_texto.setEnabled(hay)
        v.boton_recortar_ps.setEnabled(hay)
        v.boton_quitar_fondo.setEnabled(hay and elegida is not None and elegida.tipo in ("imagen", "foto")
                                        and not elegida.bloqueada and not self.quitando_fondo)
        ids = v.panel_capas.capas_elegidas if hay else []
        movibles = self.movibles(ids)
        for b in getattr(self, "botones_alinear", {}).values():
            b.setEnabled(bool(movibles))
        for b in getattr(self, "botones_distribuir", {}).values():
            b.setEnabled(len(movibles) >= 3)

    def actualizar_menu(self) -> None:
        """Habilita cada acción del menú según lo que hay (al abrir un menú)."""
        v = self.v
        hay = v._imagen is not None and v._documento is not None
        a = self.acciones
        capa = self.capa_elegida() if hay else None
        p = v.panel_capas
        movible = capa is not None and p._movible(capa)
        libre = movible and not capa.bloqueada
        ids = self.movibles(p.capas_elegidas) if hay else []
        for clave in ("abrir_capas", "guardar", "guardar_como", "exportar", "exportar_sin", "pegar", "tamano_imagen",
                      "tamano_lienzo", "rotar_90", "rotar_270", "rotar_180", "voltear_h", "voltear_v", "recortar",
                      "nueva_pixeles", "nueva_relleno", "acoplar", "acercar", "alejar", "ajustar", "100"):
            a[clave].setEnabled(hay if clave not in ("abrir_capas", "pegar") else True)
        a["deshacer"].setEnabled(v._pos_historial > 0)
        a["rehacer"].setEnabled(v._pos_historial < len(v._historial) - 1)
        for clave in ("duplicar", "duplicar_capa"):
            a[clave].setEnabled(movible)
        for clave in ("borrar", "borrar_capa"):
            a[clave].setEnabled(libre)
        a["transformar"].setEnabled(hay and self.capa_transformable() is not None)
        a["agrupar"].setEnabled(hay and p._se_puede_agrupar())
        a["desagrupar"].setEnabled(capa is not None and capa.tipo == "grupo")
        a["rasterizar"].setEnabled(libre and capa.tipo != "pixeles")
        a["estilo"].setEnabled(capa is not None and capa.tipo in TIPOS_CON_ESTILOS and not capa.bloqueada)
        a["combinar"].setEnabled(libre and p._se_puede_combinar(capa))
        con_mascara = capa is not None and capa.mascara is not None and not capa.bloqueada
        a["mascara_agregar"].setEnabled(capa is not None and capa.mascara is None and not capa.bloqueada)
        for clave in ("mascara_mostrar", "mascara_ocultar", "mascara_invertir", "mascara_quitar"):
            a[clave].setEnabled(con_mascara)
        for modo in MODOS_ALINEAR:
            a[f"alinear_{modo}"].setEnabled(bool(ids))
        for eje in ("h", "v"):
            a[f"distribuir_{eje}"].setEnabled(len(ids) >= 3)

    # ================================================================== herramientas
    def elegir_herramienta(self, nombre: str) -> None:
        """Mover, Mano, Zoom o Cuentagotas (V, H, Z, I). Lo que estaba en curso termina: una
        transformación libre queda aplicada y una máscara a medio pintar se cancela."""
        if (nombre not in self.botones_herramienta and nombre != "degradado") or nombre in HERRAMIENTAS_MASCARA:
            return
        v = self.v
        self.terminar_texto(True)
        self.controlador.cancelar()
        if self.transformando is not None:
            self.salir_transformar("aplicar")
        if v._capa_zona is not None or v._clon is not None:
            v.cancelar_herramienta()
        if self.recortando:
            self.terminar_recorte(False)
        self._caja_recorte = None
        if nombre in ("bote", "degradado"):
            self._ultima_de_bote = nombre
        self.herramienta = nombre
        self.reponer_herramienta()
        self.actualizar_herramientas()
        self._sincronizar_opciones()
        ayudas = {"pintar": "Pincel: pintá sobre la imagen  ·  [ y ] cambian el tamaño  ·  X intercambia los colores",
                  "borrador": "Borrador: arrastrá para borrar a transparente  ·  [ y ] cambian el tamaño",
                  "bote": "Bote de pintura: clic para rellenar con el color de frente",
                  "degradado": "Degradado: arrastrá de donde empieza a donde termina  ·  Mayús: de a 45°",
                  "recortar": "Recortar: ajustá el recuadro con las manijas  ·  Enter aplica, Esc cancela"}
        if nombre in ayudas and v._imagen is not None:
            v.etiqueta_estado.setText(ayudas[nombre])
            if nombre == "recortar":
                self.texto_recorte()
        elif nombre == "texto" and v._imagen is not None:
            v.etiqueta_estado.setText("Texto: clic en la imagen para escribir, o arrastrá para una caja  ·  Esc o "
                                      "Ctrl+Enter terminan")
        elif nombre == "formas" and v._imagen is not None:
            v.etiqueta_estado.setText(f"{NOMBRES_FORMA[self.params_forma.tipo]}: arrastrá sobre la imagen  ·  "
                                      "Mayús: 1:1  ·  Alt: desde el centro")
        elif v._imagen is not None:
            v.etiqueta_estado.setText(v._texto_imagen)

    def elegir_forma(self, tipo: str) -> None:
        """Elige la forma de la herramienta Formas (y la herramienta)."""
        if tipo not in NOMBRES_FORMA:
            return
        self.params_forma = replace(self.params_forma, tipo=tipo)
        self._icono_formas()
        if self.herramienta != "formas":
            self.elegir_herramienta("formas")
        else:
            self._sincronizar_opciones()
            self._mostrar_opciones("formas")

    def _icono_formas(self) -> None:
        b = self.botones_herramienta.get("formas")
        if b is not None:
            b.setIcon(iconos.icono(ICONOS_FORMA[self.params_forma.tipo], 18))

    def reponer_herramienta(self) -> None:
        """Pone en la vista la herramienta elegida (después de pintar una máscara, de una
        transformación libre o al entrar al modo). No hace nada si hay otra cosa en curso."""
        v = self.v
        if not self.activo or self.transformando is not None:
            self.actualizar_herramientas()
            return
        if v.vista.herramienta in (None, "ps"):
            v.vista.establecer_herramienta("ps", controlador=self.controlador)
        self._mostrar_opciones(self.herramienta)
        self.actualizar_herramientas()

    def actualizar_herramientas(self) -> None:
        """Marca en la barra la herramienta en uso (una de máscara mientras se pinta)."""
        if not self.botones_herramienta:
            return
        v = self.v
        en_uso = self.herramienta
        if isinstance(v._capa_zona, DestinoMascara):
            forma = v.vista._forma
            en_uso = forma if forma in HERRAMIENTAS_MASCARA else en_uso
            self._mostrar_opciones("mascara")
        elif self.transformando is not None:
            en_uso = "mover"
        bote = self.botones_herramienta.get("bote")
        if bote is not None:  # el botón compartido muestra la herramienta que se usó por última vez
            bote.setIcon(iconos.icono("ps-degradado" if self._ultima_de_bote == "degradado" else "ps-bote", 18))
            bote.setToolTip(AYUDA_DEGRADADO if self._ultima_de_bote == "degradado" else AYUDA_BOTE)
        if en_uso == "degradado":
            en_uso = "bote"
        for clave, b in self.botones_herramienta.items():
            if b.isChecked() != (clave == en_uso):
                b.blockSignals(True)
                b.setChecked(clave == en_uso)
                b.blockSignals(False)

    def herramienta_mascara(self, forma: str) -> None:
        """Rectángulo, elipse, lazo o pincel de la barra: pinta la máscara de la capa elegida."""
        if not self.activo:
            return
        self.terminar_texto(True)
        self.v.panel_capas.establecer_modo_mascara(self.modo_mascara)
        self._mostrar_opciones("mascara")
        self.pintar_mascara(forma)
        self.actualizar_herramientas()

    def mano_temporal(self, activa: bool) -> None:
        """Espacio sostenido: la Mano mientras se mantiene (con cualquier herramienta)."""
        self.v.vista.establecer_mano_temporal(activa)

    def tecla_herramienta(self, tecla: str) -> None:
        """V, H, Z, I, T, U, B, E, G o C (los atajos de la página de fotos; solo en el modo Photoshop).
        "Mayús+G" alterna el Bote y el Degradado."""
        vista = self.v.vista
        if tecla == "E" and vista._es_pincel():
            # El pincel de una máscara (o de una zona) sigue usando E para su goma.
            vista.establecer_pincel(goma=not vista.pincel[2])
            vista.pincelCambiado.emit()
            return
        if not self.activo:
            return
        if tecla == "Mayús+G":
            self.elegir_herramienta("bote" if self.herramienta == "degradado" else "degradado")
            return
        nombre = TECLAS_HERRAMIENTA.get(tecla)
        if nombre is not None:
            self.elegir_herramienta(nombre)

    def cambiar_tamano_pincel(self, sentido: int) -> None:
        """``[`` (-1) y ``]`` (1): el tamaño del Pincel o del Borrador (o del pincel de una máscara)."""
        vista = self.v.vista
        if vista._es_pincel():
            vista.establecer_pincel(tam=vista.pincel[0] + (5 if sentido > 0 else -5))
            vista.pincelCambiado.emit()
            return
        if not self.activo or self.herramienta not in HERRAMIENTAS_PINTURA:
            return
        op = self.pinceles[self.herramienta]
        op["tamano"] = float(siguiente_tamano(op["tamano"], sentido))
        self._sincronizar_opciones()
        vista.update()

    def _al_mostrar_controles(self, valor: bool) -> None:
        self.mostrar_controles = bool(valor)
        self.v.vista.update()

    def establecer_guias(self, valor: bool) -> None:
        """Ver › Guías inteligentes: el imán y sus líneas, prendidos o apagados."""
        self.guias_activas = bool(valor)
        a = getattr(self, "acciones", {}).get("guias")
        if a is not None and a.isChecked() != self.guias_activas:
            a.blockSignals(True)
            a.setChecked(self.guias_activas)
            a.blockSignals(False)

    # ------------------------------------------------------------ colores
    @property
    def frente(self) -> tuple:
        return self.colores.frente if self.colores is not None else FRENTE_INICIAL

    @property
    def fondo(self) -> tuple:
        return self.colores.fondo if self.colores is not None else FONDO_INICIAL

    def intercambiar_colores(self) -> None:
        if self.activo and self.colores is not None:
            self.colores.intercambiar()

    def restablecer_colores(self) -> None:
        if self.activo and self.colores is not None:
            self.colores.restablecer()

    def _al_cambiar_colores(self) -> None:
        """El color de frente es el del texto y el relleno de la forma que se creen después (como Photoshop)."""
        c = tuple(int(x) for x in self.frente[:3]) + (255,)
        self.params_texto = replace(self.params_texto, color=c)
        rel = self.params_forma.relleno
        if rel.tipo == "color":
            self.params_forma = replace(self.params_forma, relleno=replace(rel, colores=(c,)))
        self._sincronizar_opciones()

    def tomar_color(self, q: QPointF) -> Optional[tuple]:
        """Cuentagotas: el color de la imagen que se ve en (q) (píxeles del documento) pasa a frente."""
        color = self.color_en(q)
        if color is not None:
            self.colores.establecer(frente=color)
        return color

    def color_en_pantalla(self, pos_global: QPoint) -> Optional[tuple]:
        """El color de lo que se ve en la vista en esa posición de la pantalla (el cuentagotas del
        selector de color), o None si ahí no está la imagen."""
        vista = self.v.vista
        local = vista.mapFromGlobal(pos_global)
        if not vista.rect().contains(local):
            return None
        return self.color_en(vista.a_documento(QPointF(local)))

    def color_en(self, q: QPointF) -> Optional[tuple]:
        """El color (r, g, b) de la imagen que se ve en (q) (píxeles del documento), con la muestra del
        Cuentagotas, o None si (q) cae afuera."""
        from ..motor.pintura import cuentagotas
        vista = self.v.vista
        img = vista._despues or vista._antes
        w, h = vista._tam
        if img is None or not w or not h or not (0 <= q.x() < w and 0 <= q.y() < h):
            return None
        x, y = q.x() * img.width() / w, q.y() * img.height() / h
        radio = int(self.combo_muestra.currentData() or 0) if hasattr(self, "combo_muestra") else 0
        x0, y0 = max(0, int(x) - radio), max(0, int(y) - radio)
        x1, y1 = min(img.width(), int(x) + radio + 1), min(img.height(), int(y) + radio + 1)
        trozo = img.copy(x0, y0, max(1, x1 - x0), max(1, y1 - y0)).convertToFormat(QImage.Format_RGB888)
        tw, th = trozo.width(), trozo.height()
        arr = np.frombuffer(trozo.constBits(), np.uint8, count=trozo.bytesPerLine() * th)
        arr = arr.reshape(th, trozo.bytesPerLine())[:, :tw * 3].reshape(th, tw, 3)
        return tuple(int(c) for c in cuentagotas(arr, int(x) - x0, int(y) - y0, radio))

    # ================================================================== selección y Propiedades
    def capa_elegida(self):
        """La capa elegida en el panel (o None)."""
        v = self.v
        if v._documento is None or v.panel_capas.capa_elegida is None:
            return None
        try:
            return v._documento.capa(v.panel_capas.capa_elegida)
        except KeyError:
            return None

    def movibles(self, ids) -> list[str]:
        """De esas, las que se pueden mover (ni la base, ni el ajuste, ni un relleno, ni bloqueadas)."""
        doc = self.v._documento
        if doc is None:
            return []
        salida = []
        for i in ids:
            try:
                c = doc.capa(i)
            except KeyError:
                continue
            if doc.indice(i) == 0 or c.tipo in ("ajuste_natural", "relleno", "foto") or c.bloqueada:
                continue
            salida.append(i)
        return salida

    def al_cambiar_seleccion(self) -> None:
        ed = self.edicion_texto
        if ed is not None and self.v.panel_capas.capa_elegida != ed.id:
            self.terminar_texto(True)
        self._tomar_estilo_de_la_elegida()
        self.refrescar_propiedades()
        v = self.v
        v._actualizar_habilitados()
        v.vista.update()

    def refrescar_propiedades(self, doc: Optional[Documento] = None) -> None:
        if self.edicion_texto is not None and not self.edicion_texto.vigente():
            self.terminar_texto(False)  # cambió la foto o el documento (deshacer, la tira…): se descarta
        self._sincronizar_opciones()
        if self.propiedades is None:
            return
        v = self.v
        doc = doc if doc is not None else v._documento_vista()
        if v._imagen is None or doc is None:
            self.propiedades.mostrar(None, None, [])
            return
        self.propiedades.mostrar(doc, v._almacen, v.panel_capas.capas_elegidas)

    def _al_pedir_cambio(self, funcion, descripcion: str) -> None:
        """Un número de Propiedades: un paso del historial."""
        if self.transformando is not None:
            self.salir_transformar("aplicar")
        self.v.panel_capas.aplicar(funcion, descripcion)
        self.refrescar_propiedades()

    def confirmar(self, doc: Documento, descripcion: str) -> None:
        """Un gesto terminado (mover, escalar, rotar): un paso del historial."""
        v = self.v
        v._doc_provisorio = None
        v._cambiar_documento(doc, refrescar_panel=True, descripcion=descripcion)
        self.refrescar_propiedades()

    def empujar(self, dx: float, dy: float) -> bool:
        """Flechas con Mover: lo elegido se corre (dx, dy) píxeles; un paso."""
        v = self.v
        ids = self.movibles(v.panel_capas.capas_elegidas)
        if not ids or v._documento is None:
            return False
        doc = trasladar(v._documento, ids, dx, dy)
        nombre = v._documento.capa(ids[0]).nombre
        self.confirmar(doc, f"Capa «{nombre}» movida" if len(ids) == 1 else f"{len(ids)} capas movidas")
        return True

    def capa_bajo(self, q: QPointF) -> Optional[str]:
        """La capa de arriba que tiene algo visible en (q) (selección automática), o None: se mira
        el alfa de las imágenes (y de los dibujos de texto y forma) y la máscara. Los grupos no se
        eligen así (se elige la capa de adentro); la base y el ajuste, tampoco."""
        v = self.v
        doc = v._documento_vista()
        almacen = v._almacen
        if doc is None or not (0 <= q.x() < doc.ancho and 0 <= q.y() < doc.alto):
            return None
        visibles = {}
        for c in doc.capas:
            visibles[c.id] = c.visible and (c.padre is None or visibles.get(c.padre, True))
        for c in reversed(doc.capas[1:]):
            if c.tipo in ("ajuste_natural", "grupo") or not visibles.get(c.id) or c.opacidad <= 0:
                continue
            if c.mascara is not None and c.mascara in almacen:
                m = almacen.obtener(c.mascara)
                mh, mw = m.shape[:2]
                if m[min(mh - 1, int(q.y() * mh / doc.alto)), min(mw - 1, int(q.x() * mw / doc.ancho))].max() < 128:
                    continue
            if c.tipo == "relleno":
                return c.id
            if c.tipo in ("imagen", "pixeles"):
                if c.imagen not in almacen:
                    continue
                img = almacen.obtener(c.imagen)
            else:
                img = self._dibujo(c)
                if img is None:
                    continue
            ih, iw = img.shape[:2]
            m = matriz_transformacion(c.transform, iw, ih)
            inv = np.linalg.inv(np.vstack([m, [0.0, 0.0, 1.0]]))
            u, w_, _ = inv @ np.array([q.x(), q.y(), 1.0])
            if not (0 <= u < iw and 0 <= w_ < ih):
                continue
            if img.ndim == 3 and img.shape[2] == 4 and img[int(w_), int(u), 3] < 10:
                continue
            return c.id
        return None

    @staticmethod
    def _dibujo(capa) -> Optional[np.ndarray]:
        return dibujo_natural(capa.tipo, capa.params)

    def iman_para(self, id_capa: str):
        """El imán de una capa que se transforma (``HerramientaTransformar.ajustar_mover``): su caja
        se pega a lo que tenga cerca; devuelve (transformación, guías)."""
        cache = {}

        def ajustar(t0: Transformacion, t: Transformacion):
            if not self.guias_activas:
                return t, []
            v = self.v
            doc = v._documento
            if doc is None or not any(c.id == id_capa for c in doc.capas):
                return t, []
            if cache.get("t0") != t0:
                d0 = doc.con_capa(id_capa, transform=t0)
                cache["t0"] = t0
                cache["caja"] = caja_capa(d0, id_capa, v._almacen)
                cache["obj"] = iman.objetivos(d0, v._almacen, [id_capa])
            caja = cache["caja"]
            if caja is None:
                return t, []
            dx, dy = t.x - t0.x, t.y - t0.y
            xs, ys = cache["obj"]
            sx, sy, guias = iman.ajustar((caja[0] + dx, caja[1] + dy, caja[2] + dx, caja[3] + dy), xs, ys,
                                         iman.UMBRAL_PANTALLA / max(v.vista.zoom, 1e-6))
            return replace(t, x=t.x + sx, y=t.y + sy), guias

        return ajustar

    # ================================================================== Archivo
    def nuevo_lienzo(self, ancho: Optional[int] = None, alto: Optional[int] = None, color=None, fondo=None) -> None:
        """"Nuevo" (Ctrl+N): un documento de verdad, sin foto (``Documento.nuevo_lienzo``), con el fondo
        elegido (color, transparente o degradado). Entra a la tira como una foto más y se abre en el
        modo Photoshop. Sin tamaño, pregunta con el diálogo de siempre (``kit_flyer.DialogoNuevo``).
        ``color``: (r, g, b) del fondo; ``fondo``: un ``formas.Relleno`` (gana sobre ``color``)."""
        from . import kit_flyer
        v = self.v
        self.terminar_texto(True)
        if ancho is None or alto is None:
            dialogo = kit_flyer.DialogoNuevo(v)
            if dialogo.exec() != QDialog.Accepted:
                return
            ancho, alto, _color = dialogo.valores()
            fondo = dialogo.relleno()
        relleno = kit_flyer.relleno_de_fondo(fondo if fondo is not None else (color or (255, 255, 255)))
        try:
            doc = Documento.nuevo_lienzo(int(ancho), int(alto), relleno)
        except ValueError as error:
            v.aviso.mostrar("No se pudo crear el documento.", str(error), icono="triangle-alert")
            return
        if doc.ancho * doc.alto > MAX_PIXELES_IMAGEN:
            v.aviso.mostrar(f"El documento es demasiado grande ({doc.ancho} × {doc.alto} px): como mucho "
                            f"{MAX_PIXELES_IMAGEN // 1_000_000} MP.", "", icono="triangle-alert")
            return
        if v._lite and v._modo != PHOTOSHOP:
            v.establecer_modo(PHOTOSHOP)
        v.agregar_documento(doc, "Nuevo documento")

    def abrir_como_capas(self) -> None:
        """"Archivo › Abrir como capas…": en el documento abierto entran como capas (ajustadas al
        lienzo y en cascada); sin documento, la primera abre el documento y las demás van como capas."""
        v = self.v
        inicio = v.carpeta_inicio()
        rutas, _ = QFileDialog.getOpenFileNames(v, "Abrir como capas (podés elegir varias)", inicio, FILTRO_ABRIR_FOTOS)
        if rutas:
            self.abrir_rutas_como_capas(rutas)

    def abrir_rutas_como_capas(self, rutas) -> None:
        v = self.v
        rutas = [str(r) for r in rutas]
        if v._imagen is None:
            self._capas_pendientes = rutas[1:]
            v.agregar_fotos(rutas[:1])
        else:
            self.agregar_imagenes_como_capa(rutas)

    def foto_cargada(self) -> None:
        """La ventana terminó de abrir una foto: si había capas esperando ("Abrir como capas"), entran."""
        pendientes, self._capas_pendientes = self._capas_pendientes, []
        if pendientes:
            self.agregar_imagenes_como_capa(pendientes)
        self.refrescar_propiedades()
        self.v.vista.update()

    # ================================================================== Editar
    def pegar(self) -> None:
        """"Pegar" (Ctrl+V): una imagen del portapapeles entra como capa (o, si son archivos, cada uno).
        Sirve con lo que copian otras apps (el navegador, una captura, Paint, Photoshop…): la imagen del
        portapapeles o, si no, un PNG, JPG, BMP… en sus formatos. Sin documento abierto, la imagen pegada
        abre un documento nuevo de su tamaño."""
        v = self.v
        if not self.activo:
            return
        datos = QApplication.clipboard().mimeData()
        if datos is not None and datos.hasUrls():
            from .modo_video import es_foto
            rutas = [u.toLocalFile() for u in datos.urls() if u.toLocalFile() and es_foto(u.toLocalFile())]
            if rutas:
                if v._imagen is None:
                    self.abrir_rutas_como_capas(rutas)
                else:
                    self.agregar_imagenes_como_capa(rutas)
                return
        imagen = imagen_del_portapapeles(datos)
        if imagen is None:
            v.aviso.mostrar("No hay una imagen en el portapapeles para pegar.",
                            "Copiá una imagen (en el navegador: clic derecho › Copiar imagen) o archivos de imagen.",
                            icono="image")
            return
        arr = _rgba_de_qimage(imagen)
        if v._imagen is None or v._documento is None:
            self._pegar_como_documento(arr)
            return
        self.agregar_arreglo_como_capa(arr, "Pegado")

    def _pegar_como_documento(self, arr: np.ndarray) -> None:
        """Pegar sin documento: uno nuevo del tamaño de la imagen (fondo transparente) con la imagen como capa."""
        v = self.v
        alto, ancho = arr.shape[:2]
        if ancho * alto > MAX_PIXELES_IMAGEN:
            v.aviso.mostrar("La imagen del portapapeles es demasiado grande.", "", icono="triangle-alert")
            return
        doc = Documento.nuevo_lienzo(ancho, alto, None)
        id_img = v._almacen.guardar(np.ascontiguousarray(arr))
        doc = doc.agregar_imagen(id_img, "Pegado", transform=Transformacion(ancho / 2.0, alto / 2.0))
        v.agregar_documento(doc, "Pegado", nombre="Pegado")

    def agregar_arreglo_como_capa(self, arr: np.ndarray, nombre: str) -> Optional[str]:
        """Una imagen (RGBA o RGB uint8, sRGB) como capa nueva arriba de la elegida, centrada y achicada
        para que entre. Un paso del historial. Devuelve el id de la capa."""
        v = self.v
        if v._documento is None:
            return None
        if self.transformando is not None:
            self.salir_transformar("aplicar")
        doc = dc.con_tamano(v._documento, *v._tam_mostrado())
        encima = self._encima_de(doc)
        id_img = v._almacen.guardar(np.ascontiguousarray(arr))
        t = transformacion_ajustada(arr.shape[1], arr.shape[0], doc.ancho, doc.alto)
        previas = {c.id for c in doc.capas}
        try:
            doc = doc.agregar_imagen(id_img, nombre, encima_de=encima, transform=t)
        except ValueError as error:
            v.aviso.mostrar(str(error), "", icono="triangle-alert")
            return None
        nueva = next(c.id for c in doc.capas if c.id not in previas)
        v.panel_capas.elegir_sin_avisar(nueva)
        v._cambiar_documento(doc, refrescar_panel=True)
        return nueva

    def _encima_de(self, doc: Documento) -> Optional[str]:
        """Dónde va una capa nueva: arriba de la elegida (si no es el filtro)."""
        elegida = self.v.panel_capas.capa_elegida
        if elegida is None or not any(c.id == elegida for c in doc.capas):
            return None
        return None if doc.capa(elegida).tipo == "ajuste_natural" else elegida

    def duplicar(self) -> None:
        if self.activo and self.v._documento is not None:
            self._antes_de_operar()
            self.v.panel_capas.duplicar()

    def borrar(self) -> None:
        if self.activo and self.v._documento is not None:
            self._antes_de_operar()
            self.v.panel_capas.borrar()

    def _antes_de_operar(self) -> None:
        """Una operación del menú: lo que estaba en curso (un texto que se escribe, una transformación
        libre) queda aplicado."""
        self.terminar_texto(True)
        if self.transformando is not None:
            self.salir_transformar("aplicar")

    # ================================================================== Imagen
    def _foto_srgb(self) -> Optional[np.ndarray]:
        """La foto de base de un documento con foto, a resolución completa, como entra a ``componer``
        (con el desenfoque de fondo) y en sRGB (como las capas): para pasarla a una capa."""
        from .ventana import con_desenfoque
        v = self.v
        if v._fuente is None:
            return None
        rgb = con_desenfoque(v._fuente, v.panel_fondo.desenfoque(), v._recorte)
        if v._transformacion is not None:
            rgb = v._transformacion.a_srgb(np.ascontiguousarray(rgb))
        return np.ascontiguousarray(rgb)

    def _operar_lienzo(self, funcion, descripcion: str, con_foto: str = "documento") -> None:
        """Una operación de lienzo (``funcion(doc, foto_rgb)``) como un paso del historial. En un
        documento con foto (``con_foto``): "documento" arma un documento nuevo en la tira (la foto
        queda como estaba)."""
        v = self.v
        if v._imagen is None or v._documento is None:
            return
        self._antes_de_operar()
        doc = dc.con_tamano(v._documento, *v._tam_mostrado())
        try:
            if doc.tiene_foto:
                foto = self._foto_srgb()
                if foto is None:
                    return
                nuevo = funcion(doc, foto)
                nombre = dc.nombre_documento(v._imagen.ruta)
                v.agregar_documento(nuevo, descripcion, nombre=f"{Path(nombre).stem} (documento)")
                v.aviso.mostrar(f"Listo: «{descripcion}» armó un documento nuevo en la tira; la foto quedó como "
                                "estaba.", "En una foto, rotar, voltear y recortar no la cambian (son no "
                                "destructivos); el tamaño del lienzo o de la imagen y acoplar la pasan a una capa "
                                "de un documento nuevo.", icono="layers", segundos=10)
                return
            nuevo = funcion(doc, None)
        except (ValueError, MemoryError) as error:
            v.aviso.mostrar(f"No se pudo: {descripcion}.", str(error), icono="triangle-alert")
            return
        if nuevo == doc:
            return
        v._cambiar_documento(nuevo, refrescar_panel=True, descripcion=descripcion)

    def tamano_imagen(self) -> None:
        """"Imagen › Tamaño de imagen…" (``documento.escalar_imagen``)."""
        from .dialogos_ps import DialogoTamanoImagen
        v = self.v
        if v._imagen is None or v._documento is None:
            return
        w, h = v._tam_mostrado()
        dialogo = DialogoTamanoImagen(w, h, v)
        if dialogo.exec() != QDialog.Accepted:
            return
        self.aplicar_tamano_imagen(*dialogo.valores())

    def aplicar_tamano_imagen(self, ancho: int, alto: int) -> None:
        almacen = self.v._almacen
        self._operar_lienzo(lambda d, f: escalar_imagen(d, almacen, ancho, alto, foto_rgb=f),
                            f"Tamaño de imagen: {ancho} × {alto} px")

    def tamano_lienzo(self) -> None:
        """"Imagen › Tamaño del lienzo…" (``documento.tamano_lienzo``, con el ancla)."""
        from .dialogos_ps import DialogoTamanoLienzo
        v = self.v
        if v._imagen is None or v._documento is None:
            return
        w, h = v._tam_mostrado()
        dialogo = DialogoTamanoLienzo(w, h, v)
        if dialogo.exec() != QDialog.Accepted:
            return
        self.aplicar_tamano_lienzo(*dialogo.valores())

    def aplicar_tamano_lienzo(self, ancho: int, alto: int, ancla: str = "centro") -> None:
        almacen = self.v._almacen
        self._operar_lienzo(lambda d, f: tamano_lienzo(d, almacen, ancho, alto, ancla, foto_rgb=f),
                            f"Tamaño del lienzo: {ancho} × {alto} px")

    def rotar(self, grados: int) -> None:
        """"Rotar lienzo" 90°, 180° o 270° (horario). En una foto, el giro no destructivo de siempre."""
        v = self.v
        if v._imagen is None or v._documento is None:
            return
        if v._documento.tiene_foto:
            self._antes_de_operar()
            v.girar({90: 1, 180: 2, 270: -1}[grados])
            return
        almacen = v._almacen
        texto = {90: "Lienzo rotado 90° a la derecha", 180: "Lienzo rotado 180°", 270: "Lienzo rotado 90° a la izquierda"}
        self._operar_lienzo(lambda d, _f: rotar_lienzo(d, almacen, grados), texto[grados])

    def voltear(self, eje: str) -> None:
        """"Voltear lienzo" horizontal ("h") o vertical ("v"). En una foto, el volteo no destructivo."""
        v = self.v
        if v._imagen is None or v._documento is None:
            return
        if v._documento.tiene_foto:
            self._antes_de_operar()
            v.voltear(eje == "h")
            return
        almacen = v._almacen
        self._operar_lienzo(lambda d, _f: voltear_lienzo(d, almacen, eje),
                            "Lienzo volteado " + ("horizontal" if eje == "h" else "vertical"))

    def recortar(self) -> None:
        """"Imagen › Recortar" (y el botón del kit): elige la herramienta Recortar (C)."""
        v = self.v
        if v._imagen is None or v._documento is None:
            return
        self.elegir_herramienta("recortar")

    # ------------------------------------------------------------ la herramienta Recortar (C)
    @property
    def recortando(self) -> bool:
        """Si la herramienta Recortar está en uso (Enter aplica y Esc cancela su recuadro)."""
        return self.activo and self.herramienta == "recortar" and self.v._imagen is not None

    def _aspecto(self) -> Optional[float]:
        valor = self.combo_aspecto.currentData() if hasattr(self, "combo_aspecto") else None
        if valor == "original":
            w, h = self.v._tam_mostrado()
            return w / max(h, 1)
        return valor

    def caja_recorte_actual(self) -> Optional[CajaRecorte]:
        """El recuadro de Recortar: todo el lienzo (con la proporción elegida) al empezar o si el
        lienzo cambió de tamaño. En una foto no se sale de ella (su recorte es el no destructivo)."""
        v = self.v
        if v._imagen is None or v._documento is None or self.herramienta != "recortar":
            return None
        w, h = v._tam_mostrado()
        caja = self._caja_recorte
        if caja is None or caja.tam != (w, h):
            caja = self._caja_recorte = CajaRecorte(w, h, self._aspecto(), limitar=v._documento.tiene_foto)
        return caja

    def _al_cambiar_aspecto(self) -> None:
        caja = self.caja_recorte_actual()
        if caja is not None:
            if self._aspecto():
                caja.establecer_aspecto(self._aspecto())
            else:
                caja.aspecto = None
            self.texto_recorte()
            self.v.vista.update()

    def texto_recorte(self) -> None:
        caja = self.caja_recorte_actual()
        if caja is None:
            return
        x0, y0, x1, y1 = caja.pixeles()
        self.v.etiqueta_estado.setText(f"Recortar: {x1 - x0} × {y1 - y0} px  ·  ajustá las manijas  ·  Enter aplica, "
                                       "Esc cancela")

    def terminar_recorte(self, aplicar: bool) -> None:
        """Enter (``aplicar``): recorta el lienzo al recuadro, un paso del historial; Esc: el recuadro
        vuelve a todo el lienzo. La herramienta sigue elegida (como en Photoshop)."""
        v = self.v
        caja = self.caja_recorte_actual()
        self._caja_recorte = None
        if caja is not None and aplicar and not caja.es_todo():
            x0, y0, x1, y1 = caja.pixeles()
            if v._documento.tiene_foto:
                self._recortar_foto(x0, y0, x1, y1)
            else:
                almacen = v._almacen
                self._operar_lienzo(lambda d, _f: recortar(d, almacen, x0, y0, x1 - x0, y1 - y0),
                                    f"Lienzo recortado: {x1 - x0} × {y1 - y0} px")
        if self.herramienta == "recortar" and v._imagen is not None:
            self.texto_recorte()
        v.vista.update()

    def _recortar_foto(self, x0: int, y0: int, x1: int, y1: int) -> None:
        """Recorta una foto con su recorte no destructivo de siempre (el del Editor): el recuadro (en
        píxeles de lo que se ve, la foto ya recortada) se suma al recorte que tenía; las capas siguen
        sobre el mismo lugar de la foto. Un paso del historial."""
        from ..motor.zonas import Recorte
        v = self.v
        wb, hb = v._tam_base()
        ox, oy = (0, 0) if v._recorte is None else v._recorte.pixeles(wb, hb)[:2]
        nuevo = Recorte((ox + x0) / wb, (oy + y0) / hb, (ox + x1) / wb, (oy + y1) / hb).normalizado()
        if nuevo.es_completo():
            nuevo = None
        if nuevo == v._recorte:
            return
        if v._documento is not None:
            w0, h0 = v._imagen.ancho, v._imagen.alto
            m = dc.matriz_marco(w0, h0, v._geometria, v._recorte, v._geometria, nuevo)
            v._documento = dc.convertir_documento(v._documento, v._almacen, m,
                                                  *dc.tamano_documento(w0, h0, v._geometria, nuevo))
            v._refrescar_panel_capas()
        v._recorte = nuevo
        if v._medida is not None and not md.tiene_proporcion(nuevo, wb, hb, v._medida):
            v._medida = None  # un recuadro libre: la Medida de Fácil y Editor (que fija la proporción) se quita
            v._actualizar_medida()
        v._recalcular_fuentes()
        v._registrar_historial()

    def acoplar(self) -> None:
        """"Capa › Acoplar imagen": todo en una sola capa sobre fondo blanco (``documento.acoplar``)."""
        almacen = self.v._almacen
        self._operar_lienzo(lambda d, f: acoplar(d, almacen, f), "Imagen acoplada")

    # ================================================================== Capa
    def nueva_capa_pixeles(self) -> None:
        """"Capa › Nueva › Capa de píxeles": una capa vacía (transparente, del tamaño del lienzo)."""
        v = self.v
        if not self.activo or v._documento is None:
            return
        self._antes_de_operar()
        doc = dc.con_tamano(v._documento, *v._tam_mostrado())
        n = 1 + sum(1 for c in doc.capas if c.tipo == "pixeles")
        id_img = v._almacen.guardar(np.zeros((doc.alto, doc.ancho, 4), np.uint8))
        capa = Capa(doc.id_libre(), "pixeles", f"Capa {n}", imagen=id_img,
                    transform=Transformacion(doc.ancho / 2.0, doc.alto / 2.0))
        self._agregar_capa(doc, capa, f"Capa nueva: {capa.nombre}")

    def nueva_capa_relleno(self) -> None:
        """"Capa › Nueva › Capa de relleno": un relleno del color de frente sobre todo el lienzo."""
        from ..motor.formas import Relleno
        v = self.v
        if not self.activo or v._documento is None:
            return
        self._antes_de_operar()
        doc = dc.con_tamano(v._documento, *v._tam_mostrado())
        n = 1 + sum(1 for c in doc.capas if c.tipo == "relleno" and doc.indice(c.id) > 0)
        capa = Capa(doc.id_libre(), "relleno", f"Relleno {n}", params=Relleno("color", (tuple(self.frente) + (255,),)))
        self._agregar_capa(doc, capa, f"Capa nueva: {capa.nombre}")

    def _agregar_capa(self, doc: Documento, capa: Capa, descripcion: str) -> None:
        v = self.v
        try:
            nuevo = doc.agregar(capa, encima_de=self._encima_de(doc))
        except ValueError as error:
            v.aviso.mostrar(str(error), "", icono="triangle-alert")
            return
        v.panel_capas.elegir_sin_avisar(capa.id)
        v._cambiar_documento(nuevo, refrescar_panel=True, descripcion=descripcion)
        self.refrescar_propiedades()

    def agrupar(self) -> None:
        if self.activo and self.v._documento is not None:
            self._antes_de_operar()
            self.v.panel_capas.agrupar()

    def desagrupar(self) -> None:
        if self.activo and self.v._documento is not None:
            self._antes_de_operar()
            self.v.panel_capas.desagrupar()

    def rasterizar(self) -> None:
        if self.activo and self.v._documento is not None:
            self._antes_de_operar()
            self.v.panel_capas.rasterizar()

    def combinar_abajo(self) -> None:
        if self.activo and self.v._documento is not None:
            self._antes_de_operar()
            self.v.panel_capas.combinar_abajo()

    def alinear(self, modo: str) -> None:
        """Alinea las elegidas: una sola, respecto del lienzo; varias, entre ellas (``documento.alinear``)."""
        v = self.v
        if v._documento is None:
            return
        ids = self.movibles(v.panel_capas.capas_elegidas)
        if not ids:
            return
        self._antes_de_operar()
        respecto = "seleccion" if len(ids) > 1 else "lienzo"
        almacen = v._almacen
        v.panel_capas.aplicar(lambda d: alinear(d, ids, modo, respecto, almacen=almacen),
                              ("Capa alineada " if len(ids) == 1 else "Capas alineadas ") + NOMBRES_ALINEAR[modo])
        self.refrescar_propiedades()

    def distribuir(self, eje: str) -> None:
        """Reparte parejo los centros de 3 o más capas elegidas (``documento.distribuir``)."""
        v = self.v
        if v._documento is None:
            return
        ids = self.movibles(v.panel_capas.capas_elegidas)
        if len(ids) < 3:
            v.aviso.mostrar("Para distribuir, elegí 3 capas o más (Ctrl o Mayús + clic en el panel Capas).", "",
                            icono="layers")
            return
        self._antes_de_operar()
        almacen = v._almacen
        v.panel_capas.aplicar(lambda d: distribuir(d, ids, eje, almacen=almacen),
                              "Capas distribuidas en " + ("horizontal" if eje == "h" else "vertical"))
        self.refrescar_propiedades()

    # ================================================================== Transformación libre (Ctrl+T)
    def capa_transformable(self) -> Optional[str]:
        """La capa que se transformaría con Ctrl+T: la elegida si tiene transformación (imagen, píxeles,
        texto o forma) y no tiene candado; si no, la de esas de más arriba. None si no hay."""
        v = self.v
        doc = v._documento
        if doc is None:
            return None

        def sirve(c) -> bool:
            return (c.tipo in TIPOS_CON_TRANSFORMACION and not c.bloqueada
                    and (c.tipo not in ("imagen", "pixeles") or c.imagen in v._almacen))

        elegida = v.panel_capas.capa_elegida
        if elegida is not None:
            try:
                c = doc.capa(elegida)
            except KeyError:
                c = None
            if c is not None and sirve(c):
                return c.id
        for c in reversed(doc.capas):
            if sirve(c):
                return c.id
        return None

    def alternar_transformar(self, activo: bool) -> None:
        """Ctrl+T (y "Transformación libre"): empieza o termina (aplicando) la transformación libre de
        una capa: manijas, Enter aplica (un paso) y Esc cancela."""
        v = self.v
        boton = self.botones_herramienta.get("mover")
        if not activo:
            if self.transformando is not None:
                self.salir_transformar("aplicar")
            self.actualizar_herramientas()
            return
        if self.transformando is not None:
            self.actualizar_herramientas()
            return
        self.terminar_texto(True)
        if v._imagen is None or v._modo != PHOTOSHOP:
            if boton is not None and v._modo != PHOTOSHOP:
                v._marcar_boton(boton, False)
            return
        id_capa = self.capa_transformable()
        if id_capa is None:
            v.aviso.mostrar("Para transformar, sumá una capa (imagen, texto o forma) sin candado en el panel Capas.",
                            "", icono="move")
            return
        v.cancelar_herramienta()
        if self.recortando:
            self.terminar_recorte(False)
        doc = v._documento
        ancho, alto = v._tam_mostrado()
        if (doc.ancho, doc.alto) != (ancho, alto):
            doc = v._documento = dc.con_tamano(doc, ancho, alto)
        capa = doc.capa(id_capa)
        natural = tamano_natural(capa, v._almacen)
        if natural is None:
            return
        self.herramienta = "mover"
        v.panel_capas.elegir_sin_avisar(id_capa)
        self.transformando = (id_capa, capa.transform)
        herramienta = HerramientaTransformar(capa.transform, natural[0], natural[1],
                                             ajustar_mover=self.iman_para(id_capa))
        v.vista.establecer_superposiciones([])
        v.vista.establecer_herramienta("transformar", transformador=herramienta)
        v.barra_pincel.hide()
        v.barra_transformar.show()
        self._texto_transformacion(herramienta)
        v.etiqueta_estado.setText(f"Transformación libre de «{capa.nombre}»: arrastrá la capa o sus manijas  ·  "
                                  "Enter aplica, Esc cancela")
        self.actualizar_herramientas()
        v._actualizar_habilitados()
        self.refrescar_propiedades()

    def _texto_transformacion(self, herramienta: HerramientaTransformar) -> None:
        t = herramienta.transform
        v = self.v
        v.texto_transformar.setText(f"{t.x:.0f}, {t.y:.0f} px  ·  " + herramienta.texto())
        v.texto_transformar.setToolTip(
            "Arrastrá la capa para moverla (Mayús: solo derecho; se pega a las guías), las manijas para escalarla "
            "(libre; Mayús en una esquina mantiene la proporción; Alt: desde el centro) y la manija redonda para "
            "rotarla (Mayús: de a 15°). Flechas: de a 1 px (Mayús: 10). Enter aplica, Esc cancela.")

    def al_transformar(self, t) -> None:
        """La vista movió la capa en la transformación libre: se ve enseguida, sin ser un paso todavía."""
        v = self.v
        if self.transformando is None or v._documento is None:
            return
        id_capa = self.transformando[0]
        v._doc_provisorio = v._documento.con_capa(id_capa, transform=t)
        herramienta = v.vista.transformador
        if herramienta is not None:
            self._texto_transformacion(herramienta)
        v.solicitar_render()
        self.refrescar_propiedades(v._doc_provisorio)

    def voltear_capa(self, vertical: bool = False) -> None:
        """"Voltear" de la barra de la transformación libre: espejo horizontal (o vertical)."""
        herramienta = self.v.vista.transformador
        if self.transformando is None or herramienta is None:
            return
        self.al_transformar(herramienta.voltear_v() if vertical else herramienta.voltear())
        self.v.vista.update()

    def salir_transformar(self, accion: str) -> None:
        """Termina la transformación libre: "aplicar" la deja como un paso; "cancelar" vuelve atrás."""
        v = self.v
        if self.transformando is None:
            return
        id_capa, antes = self.transformando
        herramienta = v.vista.transformador
        nueva = herramienta.transform if herramienta is not None else antes
        self.transformando = None
        v._doc_provisorio = None
        if v.vista.herramienta == "transformar":
            v.vista.establecer_herramienta(None)
        v.barra_transformar.hide()
        if v._imagen is not None:
            v.etiqueta_estado.setText(v._texto_imagen)
        if accion == "aplicar" and nueva != antes and v._documento is not None \
                and any(c.id == id_capa for c in v._documento.capas):
            v._cambiar_documento(v._documento.con_capa(id_capa, transform=nueva), refrescar_panel=True)
        else:
            v.solicitar_render()
        v._actualizar_superposiciones()
        self.reponer_herramienta()
        v._actualizar_habilitados()
        self.refrescar_propiedades()

    # ================================================================== imágenes como capas (Etapa 1)
    def elegir_imagen_capa(self) -> None:
        """"Agregar imagen como capa…": un diálogo de imágenes (PNG con transparencia, JPG, WEBP…)."""
        v = self.v
        if v._imagen is None:
            v.aviso.mostrar("Primero abrí una foto o creá un documento (Nuevo): las capas van encima.", "",
                            icono="image")
            return
        rutas, _ = QFileDialog.getOpenFileNames(v, "Agregar imagen como capa (podés elegir varias)",
                                                v.carpeta_inicio(), FILTRO_ABRIR_FOTOS)
        if rutas:
            self.agregar_imagenes_como_capa(rutas)

    def agregar_imagenes_como_capa(self, rutas) -> None:
        """Suma cada imagen como una capa del documento abierto, arriba de la elegida, centrada y
        achicada para que entre (varias: en cascada). Se leen en segundo plano; una que no se puede
        abrir (o que pasa de ``MAX_PIXELES_IMAGEN``) avisa y no cambia nada."""
        v = self.v
        if v._imagen is None or not v._lite:  # la PRO no tiene capas: a la tira, como siempre
            v.agregar_fotos(list(rutas))
            return
        rutas = [str(r) for r in rutas]
        imagen = v._imagen

        def trabajo(_cancelado):
            from PIL import Image
            from ..motor import cargar_imagen
            from ..motor.imagen_io import TransformacionPantalla as _T
            leidas, errores = [], []
            for ruta in rutas:
                nombre = Path(ruta).name
                try:
                    with Image.open(ruta) as im:
                        w, h = im.size
                    if w * h > MAX_PIXELES_IMAGEN or max(w, h) > LADO_MAX:
                        errores.append(f"{nombre}: es demasiado grande ({w} × {h} px; como mucho "
                                       f"{MAX_PIXELES_IMAGEN // 1_000_000} MP).")
                        continue
                    cargada = cargar_imagen(ruta)
                except Exception as error:  # noqa: BLE001 - cualquier archivo que no sea una imagen
                    errores.append(f"{nombre}: no se pudo abrir ({error}).")
                    continue
                rgb = _T(cargada.icc).a_srgb(cargada.rgb)  # las capas, en sRGB (como se ven)
                if cargada.alpha is not None:
                    arr = np.dstack([rgb, cargada.alpha])
                else:
                    arr = np.ascontiguousarray(rgb)
                leidas.append((Path(ruta).stem, arr))
            return imagen, leidas, errores

        v.etiqueta_estado.setText("Agregando la imagen como capa…" if len(rutas) == 1 else
                                  f"Agregando {len(rutas)} imágenes como capas…")
        v._pool_archivos.start(Tarea("capa_cargada", v._generacion_capa, trabajo, v._senales))

    def capas_cargadas(self, resultado) -> None:
        v = self.v
        imagen, leidas, errores = resultado
        if v._imagen is not None:
            v.etiqueta_estado.setText(v._texto_imagen)
        if errores:
            v.aviso.mostrar("No se pudo agregar como capa: " + errores[0] if len(errores) == 1 else
                            f"No se pudieron agregar {len(errores)} imágenes como capas.", "\n".join(errores),
                            icono="triangle-alert")
        if imagen is not v._imagen or not leidas or v._documento is None:
            return
        if self.transformando is not None:
            self.salir_transformar("aplicar")
        doc = dc.con_tamano(v._documento, *v._tam_mostrado())
        encima = self._encima_de(doc)
        nueva = None
        varias = len(leidas) > 1
        paso = 0.04 * min(doc.ancho, doc.alto)  # varias a la vez: en cascada, cada una un poco corrida
        for i, (nombre, arr) in enumerate(leidas):
            id_img = v._almacen.guardar(arr)
            t = transformacion_ajustada(arr.shape[1], arr.shape[0], doc.ancho, doc.alto)
            if varias:
                n = len(leidas) - 1
                escala = min(t.escala, 0.6 * doc.ancho / max(1, arr.shape[1]), 0.6 * doc.alto / max(1, arr.shape[0]))
                t = replace(t, x=t.x + (i - n / 2) * paso, y=t.y + (i - n / 2) * paso, escala=max(escala, 1e-3))
            previas = {c.id for c in doc.capas}
            try:
                doc = doc.agregar_imagen(id_img, nombre, encima_de=encima, transform=t)
            except ValueError as error:
                v.aviso.mostrar(str(error), "", icono="triangle-alert")
                break
            nueva = next(c.id for c in doc.capas if c.id not in previas)
            encima = nueva
        if nueva is None:
            return
        v.panel_capas.elegir_sin_avisar(nueva)
        v._cambiar_documento(doc, refrescar_panel=True)
        self.refrescar_propiedades()

    # ================================================================== kit de flyers
    def agregar_texto(self, datos: Optional[dict] = None) -> None:
        """"Texto" (kit): elige la herramienta Texto (clic en la imagen para escribir). Con ``datos`` (los
        del kit: texto, fuente, tamaño, color, negrita, alineación y sombra) crea un texto vivo centrado
        sin preguntar; si la capa elegida es un texto, lo cambia. Un paso del historial."""
        v = self.v
        if v._imagen is None or v._documento is None:
            v.aviso.mostrar("Primero abrí una foto o creá un documento (Nuevo): el texto va encima.", "", icono="image")
            return
        if datos is None:
            self.elegir_herramienta("texto")
            return
        contenido = str(datos.get("texto", ""))
        if not contenido.strip():
            return
        self._antes_de_operar()
        color = tuple(int(c) for c in datos.get("color", (255, 255, 255)))[:4]
        p = ParamsTexto(contenido, str(datos.get("fuente", "Arial")), float(datos.get("tamano", 72)),
                        color + (255,) if len(color) == 3 else color, bool(datos.get("negrita", False)),
                        bool(datos.get("cursiva", False)), str(datos.get("alineacion", "centro")))
        estilos = EstilosCapa(sombra=Sombra((0, 0, 0, 255), 0.55, 120.0, max(2.0, p.tamano * 0.04),
                                            max(2.0, p.tamano * 0.06))) if datos.get("sombra") else EstilosCapa()
        doc = dc.con_tamano(v._documento, *v._tam_mostrado())
        elegida = self.capa_elegida()
        if elegida is not None and elegida.tipo == "texto" and not elegida.bloqueada:
            nuevo = con_params_texto(doc, elegida.id, p, nombre_texto(contenido)).con_capa(elegida.id, estilos=estilos)
            v._cambiar_documento(nuevo, refrescar_panel=True, descripcion=f"Texto cambiado: «{nombre_texto(contenido)}»")
            return
        ancho, alto, _a = medidas_texto(p)
        t = Transformacion(doc.ancho / 2.0, doc.alto / 2.0)
        if ancho > doc.ancho * 0.95:  # que entre en el lienzo
            t = replace(t, escala=max(1e-3, doc.ancho * 0.9 / ancho))
        capa = Capa(doc.id_libre(), "texto", nombre_texto(contenido), params=p, transform=t, estilos=estilos)
        self._agregar_capa(doc, capa, f"Texto nuevo: «{capa.nombre}»")

    def quitar_fondo_capa(self) -> None:
        """"Quitar fondo" (kit) de la capa elegida, en segundo plano (``kit_flyer.quitar_fondo``). Una
        capa imagen cambia su imagen; con la Foto, el objeto va a una capa nueva y la foto se oculta."""
        from . import kit_flyer
        v = self.v
        capa = self.capa_elegida()
        if v._imagen is None or capa is None or capa.tipo not in ("imagen", "foto"):
            v.aviso.mostrar("Elegí una capa de imagen (o la Foto) para quitarle el fondo.", "", icono="image")
            return
        if capa.bloqueada:
            v.aviso.mostrar(f"La capa «{capa.nombre}» está bloqueada.", "", icono="lock")
            return
        if self.quitando_fondo:
            return
        if self.transformando is not None:
            self.salir_transformar("aplicar")
        if capa.tipo == "imagen":
            arr = v._arreglo(capa.imagen)
            if arr is None:
                return
            rgb, alpha = arr[..., :3], (arr[..., 3] if arr.ndim == 3 and arr.shape[2] == 4 else None)
        else:
            if v._fuente is None:
                return
            rgb = v._fuente
            if v._transformacion is not None:
                rgb = v._transformacion.a_srgb(np.ascontiguousarray(rgb))
            alpha = None
        imagen, id_capa, tipo, id_antes = v._imagen, capa.id, capa.tipo, capa.imagen

        def trabajo(_cancelado):
            return imagen, id_capa, tipo, id_antes, kit_flyer.quitar_fondo(rgb, alpha)

        self.quitando_fondo = True
        v._actualizar_habilitados()
        v.etiqueta_estado.setText("Quitando el fondo…")
        v._pool_archivos.start(Tarea("fondo_quitado", 0, trabajo, v._senales))

    def fondo_quitado(self, resultado) -> None:
        v = self.v
        imagen, id_capa, tipo, id_antes, rgba = resultado
        self.quitando_fondo = False
        if v._imagen is not None:
            v.etiqueta_estado.setText(v._texto_imagen)
        doc = v._documento
        if imagen is not v._imagen or doc is None or not any(c.id == id_capa for c in doc.capas):
            v._actualizar_habilitados()
            return
        if self.transformando is not None:
            self.salir_transformar("aplicar")
        doc = dc.con_tamano(doc, *v._tam_mostrado())
        capa = doc.capa(id_capa)
        id_img = v._almacen.guardar(rgba)
        if tipo == "imagen":
            if capa.imagen != id_antes:
                v._actualizar_habilitados()
                return  # la capa cambió mientras tanto
            doc = doc.con_capa(id_capa, imagen=id_img)
            elegir = id_capa
        else:
            previas = {c.id for c in doc.capas}
            t = transformacion_ajustada(rgba.shape[1], rgba.shape[0], doc.ancho, doc.alto)
            try:
                doc = doc.agregar_imagen(id_img, "Objeto recortado", encima_de=id_capa, transform=t)
            except ValueError as error:
                v._actualizar_habilitados()
                v.aviso.mostrar(str(error), "", icono="triangle-alert")
                return
            elegir = next(c.id for c in doc.capas if c.id not in previas)
            doc = doc.con_capa(id_capa, visible=False)
        v.panel_capas.elegir_sin_avisar(elegir)
        v._cambiar_documento(doc, refrescar_panel=True, descripcion=f"Fondo quitado: {capa.nombre}")
        v.aviso.mostrar("Listo: fondo quitado." + (" La foto quedó oculta." if tipo == "foto" else ""),
                        "Si quedó algo de más o de menos, corregilo con la máscara de la capa.", icono="scissors")

    def recortar_desde_photoshop(self) -> None:
        """"Recortar" (el botón del kit): la herramienta Recortar (C), acá mismo. En un documento sin foto
        recorta el lienzo; en una foto, con su recorte no destructivo (las capas siguen a la foto)."""
        if self.v._imagen is None:
            return
        if self.transformando is not None:
            self.salir_transformar("aplicar")
        self.recortar()

    # ================================================================== Texto (U2)
    def nuevo_texto(self, x: float, y: float, ancho_caja: Optional[float] = None,
                    contenido: str = "") -> Optional[EdicionTexto]:
        """Un texto nuevo para escribir en el lugar: con un clic, la línea base del primer renglón queda
        en (x, y); con una caja (``ancho_caja``), (x, y) es su esquina de arriba a la izquierda y el
        texto se corta a ese ancho. Con los valores de la barra de opciones."""
        v = self.v
        if v._imagen is None or v._documento is None:
            return None
        self._antes_de_operar()
        if self.herramienta != "texto":
            self.herramienta = "texto"
            self.reponer_herramienta()
        doc = v._documento
        ancho_doc, alto_doc = v._tam_mostrado()
        if (doc.ancho, doc.alto) != (ancho_doc, alto_doc):
            doc = v._documento = dc.con_tamano(doc, ancho_doc, alto_doc)
        p = replace(self.params_texto, contenido=contenido, ancho_caja=ancho_caja)
        if ancho_caja is None:
            t = transformacion_nueva(p, x, y)
        else:
            ancla = (x + FACTOR_ALINEACION[p.alineacion] * ancho_caja, y)
            t = transformacion_con_ancla(p, Transformacion(x, y), ancla)
        capa = Capa(doc.id_libre(), "texto", nombre_texto(contenido), params=p, transform=t)
        encima = self._encima_de(doc)
        try:
            doc.agregar(capa, encima_de=encima)
        except ValueError as error:
            v.aviso.mostrar(str(error), "", icono="triangle-alert")
            return None
        self.edicion_texto = EdicionTexto(self, doc, capa, True, encima)
        self.edicion_texto.abrir()
        self._sincronizar_opciones()
        v.etiqueta_estado.setText("Escribí el texto  ·  Enter: otro renglón  ·  Esc, Ctrl+Enter o un clic afuera: listo")
        return self.edicion_texto

    def editar_texto(self, id_capa: Optional[str] = None, seleccionar: bool = False) -> Optional[EdicionTexto]:
        """Vuelve a editar en el lugar una capa de texto (la elegida, si no se dice)."""
        v = self.v
        if not self.activo or v._imagen is None or v._documento is None:
            return None
        id_capa = id_capa or v.panel_capas.capa_elegida
        ed = self.edicion_texto
        if ed is not None and ed.id == id_capa and ed.vigente():
            return ed
        try:
            capa = v._documento.capa(id_capa)
        except KeyError:
            return None
        if capa.tipo != "texto" or capa.params is None:
            return None
        if capa.bloqueada:
            v.aviso.mostrar(f"La capa «{capa.nombre}» está bloqueada.", "", icono="lock")
            return None
        if self.herramienta != "texto":
            self.elegir_herramienta("texto")
        else:
            self._antes_de_operar()
        doc = v._documento
        if v.panel_capas.capa_elegida != id_capa:
            v.panel_capas.elegir(id_capa)
        capa = doc.capa(id_capa)
        self.edicion_texto = EdicionTexto(self, doc, capa, False)
        self.edicion_texto.abrir(seleccionar)
        self._sincronizar_opciones()
        v.etiqueta_estado.setText("Editando el texto  ·  Enter: otro renglón  ·  Esc, Ctrl+Enter o un clic afuera: listo")
        return self.edicion_texto

    def terminar_texto(self, confirmar: bool = True) -> None:
        """Termina la edición en el lugar: con ``confirmar``, un paso del historial ("Texto nuevo",
        "Texto cambiado" o, si quedó vacío, "Texto borrado"); si no, todo queda como estaba."""
        ed = self.edicion_texto
        if ed is None:
            return
        self.edicion_texto = None
        v = self.v
        vigente = ed.vigente()
        doc = ed.documento_final()
        ed.cerrar()
        v._doc_provisorio = None
        if v._imagen is not None:
            v.etiqueta_estado.setText(v._texto_imagen)
        if not vigente or not confirmar:
            v.solicitar_render()
            self.refrescar_propiedades()
            return
        capa = doc.capa(ed.id)
        vacio = not capa.params.contenido.strip()
        if ed.nueva:
            if vacio:
                v.solicitar_render()
                self.refrescar_propiedades()
                return
            v.panel_capas.elegir_sin_avisar(ed.id)
            v._cambiar_documento(doc, refrescar_panel=True, descripcion=f"Texto nuevo: «{capa.nombre}»")
        elif vacio:
            v._cambiar_documento(ed.doc0.quitar(ed.id), refrescar_panel=True,
                                 descripcion=f"Texto borrado: «{ed.nombre0}»")
        elif doc == ed.doc0:
            v.solicitar_render()
        else:
            v._cambiar_documento(doc, refrescar_panel=True, descripcion=f"Texto cambiado: «{capa.nombre}»")
        self.refrescar_propiedades()
        v.vista.setFocus()

    def _sincronizar_opciones(self) -> None:
        """La barra de opciones de Texto y Formas muestra los valores de la herramienta (o los del texto
        que se escribe)."""
        if not hasattr(self, "opciones_degradado"):  # la barra de opciones todavía no está armada
            return
        ed = self.edicion_texto
        self.opciones_texto.mostrar(ed.params if ed is not None else self.params_texto)
        self.opciones_forma.mostrar(replace(self.params_forma,
                                            alto=self.alto_forma.get(self.params_forma.tipo, self.params_forma.alto)))
        self.opciones_pintura.mostrar(self.opciones_pincel())
        self.opciones_bote_ui.mostrar(self.opciones_bote)
        self.opciones_degradado.mostrar(self.degradado_radial, self.relleno_degradado_efectivo(),
                                        self.relleno_degradado is None, self.opacidad_degradado)

    # ------------------------------------------------------------ Pincel, Borrador, Bote y Degradado (U3)
    def opciones_pincel(self) -> dict:
        """Tamaño, dureza y opacidad de la herramienta de pintura elegida (o del Pincel)."""
        return self.pinceles["borrador" if self.herramienta == "borrador" else "pintar"]

    def relleno_degradado_efectivo(self) -> Relleno:
        """Los colores del Degradado: los elegidos o, si no, del color de frente al de fondo."""
        tipo = "radial" if self.degradado_radial else "lineal"
        if self.relleno_degradado is not None:
            return replace(self.relleno_degradado, tipo=tipo)
        return Relleno(tipo, (tuple(self.frente[:3]) + (255,), tuple(self.fondo[:3]) + (255,)))

    def _al_cambiar_opciones_pincel(self, cambios: dict) -> None:
        op = self.opciones_pincel()
        for clave, valor in cambios.items():
            op[clave] = float(valor)
        self._sincronizar_opciones()
        self.v.vista.update()

    def _al_cambiar_opciones_bote(self, cambios: dict) -> None:
        self.opciones_bote.update(cambios)

    def _al_cambiar_opciones_degradado(self, cambios: dict) -> None:
        if "radial" in cambios:
            self.degradado_radial = bool(cambios["radial"])
        if "relleno" in cambios:
            r = cambios["relleno"]
            self.relleno_degradado = None if r is None else replace(r, tipo="lineal")
        if "opacidad" in cambios:
            self.opacidad_degradado = float(cambios["opacidad"])
        self._sincronizar_opciones()

    def _tomar_estilo_de_la_elegida(self) -> None:
        """Elegir un texto o una forma pasa su estilo a la herramienta (lo próximo sale igual)."""
        capa = self.capa_elegida()
        if capa is None or capa.params is None or self.edicion_texto is not None:
            return
        if capa.tipo == "texto":
            self.params_texto = replace(capa.params, contenido="", ancho_caja=None)
        elif capa.tipo == "forma":
            f = capa.params
            self.params_forma = replace(self.params_forma, relleno=f.relleno, trazo=f.trazo, grosor=f.grosor,
                                        radio=f.radio, lados=f.lados, puntas=f.puntas)

    def _al_cambiar_opciones_texto(self, cambios: dict) -> None:
        """La barra de opciones de Texto: el valor queda para lo próximo y, si hay un texto que se escribe
        o uno elegido, lo cambia (el elegido, como un paso del historial)."""
        try:
            self.params_texto = replace(self.params_texto, **cambios)
        except (TypeError, ValueError):
            return
        ed = self.edicion_texto
        if ed is not None:
            ed.cambiar_params(cambios)
            return
        capa = self.capa_elegida()
        if capa is None or capa.tipo != "texto" or capa.bloqueada or capa.params is None:
            return
        nuevos = replace(capa.params, **cambios)
        if nuevos != capa.params:
            id_capa = capa.id
            self.v.panel_capas.aplicar(lambda d: con_params_texto(d, id_capa, nuevos), f"Texto «{capa.nombre}» cambiado")
            self.refrescar_propiedades()

    def _al_cambiar_opciones_forma(self, cambios: dict) -> None:
        """La barra de opciones de Formas: el tipo es de la herramienta; lo demás queda para lo próximo y
        cambia la forma elegida (un paso del historial)."""
        cambios = dict(cambios)
        alto = cambios.pop("alto", None)
        tipo = cambios.pop("tipo", None)
        if tipo is not None:
            self.elegir_forma(tipo)
            return
        if alto is not None and self.params_forma.tipo in self.alto_forma:
            self.alto_forma[self.params_forma.tipo] = float(alto)
        try:
            self.params_forma = replace(self.params_forma, **cambios)
        except (TypeError, ValueError):
            return
        capa = self.capa_elegida()
        if capa is None or capa.tipo != "forma" or capa.bloqueada or capa.params is None:
            return
        if alto is not None and capa.params.tipo in ("linea", "flecha"):
            cambios["alto"] = float(alto)
        try:
            nuevos = replace(capa.params, **cambios)
        except (TypeError, ValueError):
            return
        if nuevos != capa.params:
            id_capa = capa.id
            self.v.panel_capas.aplicar(lambda d: d.con_capa(id_capa, params=nuevos), f"Forma «{capa.nombre}» cambiada")
            self.refrescar_propiedades()

    # ================================================================== Formas (U2)
    def empezar_forma(self, q: QPointF) -> Optional[dict]:
        """El gesto de una forma nueva (se dibuja al arrastrar: ``documento_con_forma``)."""
        v = self.v
        if v._documento is None or v._transformando is not None:
            return None
        self._antes_de_operar()
        doc = v._documento
        ancho_doc, alto_doc = v._tam_mostrado()
        if (doc.ancho, doc.alto) != (ancho_doc, alto_doc):
            doc = v._documento = dc.con_tamano(doc, ancho_doc, alto_doc)
        tipo = self.params_forma.tipo
        n = 1 + sum(1 for c in doc.capas if c.tipo == "forma" and c.params is not None and c.params.tipo == tipo)
        return {"tipo": "forma", "p0": QPointF(q), "doc0": doc, "id": doc.id_libre(), "encima": self._encima_de(doc),
                "nombre": f"{NOMBRES_FORMA[tipo]} {n}", "movio": False}

    def forma_de_arrastre(self, p0: QPointF, q: QPointF, mods) -> Optional[tuple]:
        """(ParamsForma, Transformacion) de un arrastre de p0 a q (Mayús: 1:1, o de a 45° en la línea y la
        flecha; Alt: desde el centro). None si es demasiado chico."""
        base = self.params_forma
        tipo = base.tipo
        dx, dy = q.x() - p0.x(), q.y() - p0.y()
        zoom = max(self.v.vista.zoom, 1e-6)
        mayus, alt = bool(mods & Qt.ShiftModifier), bool(mods & Qt.AltModifier)
        if tipo in ("linea", "flecha"):
            largo = math.hypot(dx, dy)
            if largo * zoom < 3:
                return None
            angulo = math.atan2(dy, dx)
            if mayus:
                angulo = round(angulo / (math.pi / 4)) * (math.pi / 4)
                dx, dy = largo * math.cos(angulo), largo * math.sin(angulo)
            if alt:
                cx, cy, largo = p0.x(), p0.y(), 2 * largo
            else:
                cx, cy = p0.x() + dx / 2, p0.y() + dy / 2
            params = replace(base, ancho=max(1.0, largo), alto=max(1.0, self.alto_forma.get(tipo, 8.0)))
            return params, Transformacion(cx, cy, 1.0, math.degrees(angulo))
        w, h = abs(dx), abs(dy)
        if mayus:
            w = h = max(w, h)
        sx, sy = (1.0 if dx >= 0 else -1.0), (1.0 if dy >= 0 else -1.0)
        if alt:
            cx, cy, w, h = p0.x(), p0.y(), 2 * w, 2 * h
        else:
            cx, cy = p0.x() + sx * w / 2, p0.y() + sy * h / 2
        if min(w, h) * zoom < 3 and max(w, h) * zoom < 6:
            return None
        params = replace(base, ancho=max(1.0, w), alto=max(1.0, h))
        return params, Transformacion(cx, cy)

    def documento_con_forma(self, g: dict, q: QPointF, mods) -> Optional[Documento]:
        hecho = self.forma_de_arrastre(g["p0"], q, mods)
        if hecho is None:
            return None
        params, t = hecho
        capa = Capa(g["id"], "forma", g["nombre"], params=params, transform=t)
        try:
            return g["doc0"].agregar(capa, encima_de=g["encima"])
        except ValueError:
            return None

    def confirmar_forma(self, g: dict, doc: Documento) -> None:
        """La forma arrastrada queda: un paso del historial ("Forma nueva"), y elegida."""
        if self.v._documento is not g["doc0"]:
            self.v._doc_provisorio = None
            self.v.solicitar_render()
            return
        self.v.panel_capas.elegir_sin_avisar(g["id"])
        self.confirmar(doc, f"Forma nueva: {g['nombre']}")

    def nueva_forma(self, x0: float, y0: float, x1: float, y1: float, mayus: bool = False) -> Optional[str]:
        """Una forma de la herramienta de (x0, y0) a (x1, y1) (como un arrastre). Devuelve su id."""
        g = self.empezar_forma(QPointF(x0, y0))
        if g is None:
            return None
        doc = self.documento_con_forma(g, QPointF(x1, y1), Qt.ShiftModifier if mayus else Qt.NoModifier)
        if doc is None:
            return None
        self.confirmar_forma(g, doc)
        return g["id"]

    # ================================================================== Pincel, Borrador, Bote y Degradado (U3)
    def preguntar_rasterizar(self, capa: Capa) -> bool:
        """"¿Rasterizar la capa?" (como Photoshop) antes de pintar un texto, una forma o un relleno."""
        tipo = {"texto": "de texto", "forma": "de forma", "relleno": "de relleno"}.get(capa.tipo, "")
        que = {"texto": "texto", "forma": "forma", "relleno": "relleno"}.get(capa.tipo, "capa")
        r = QMessageBox.question(
            self.v, "¿Rasterizar la capa?",
            f"«{capa.nombre}» es una capa {tipo}: para pintarla hay que rasterizarla (pasarla a píxeles). "
            f"Después ya no se va a poder editar como {que}.\n\n¿Rasterizar la capa?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        return r == QMessageBox.Yes

    def _visible(self, doc: Documento, capa: Capa) -> bool:
        """Si la capa se ve (ella y los grupos que la contienen)."""
        if not capa.visible:
            return False
        return all(doc.capa(i).visible for i in doc.ancestros(capa.id))

    def destino_pintura(self, herramienta: str) -> Optional[tuple]:
        """Dónde pinta el Pincel, el Borrador o el Bote: (documento, id de la capa, nombre, nueva) o None.

        * Una capa de **píxeles** o una **imagen** (que también son píxeles): ahí mismo.
        * Un **texto**, una **forma** o un **relleno**: pregunta "¿Rasterizar la capa?" (con Sí, la
          rasteriza: un paso; se vuelve a pintar encima).
        * La **base** (la foto o el fondo), un **grupo** o nada elegido: una **capa de píxeles nueva**
          encima (``nueva``; queda en el documento recién al terminar el trazo, en el mismo paso). El
          Borrador ahí no hace nada (avisa).
        """
        v = self.v
        if v._imagen is None or v._documento is None:
            return None
        self._antes_de_operar()
        doc = v._documento
        ancho, alto = v._tam_mostrado()
        if (doc.ancho, doc.alto) != (ancho, alto):
            doc = v._documento = dc.con_tamano(doc, ancho, alto)
        capa = self.capa_elegida()
        if capa is None or capa.tipo in ("foto", "ajuste_natural", "grupo") or doc.indice(capa.id) == 0:
            if herramienta == "borrador":
                v.aviso.mostrar("El borrador borra en una capa de píxeles o de imagen: elegila en el panel Capas.",
                                "La foto y el fondo no se borran (ocultalos o usá una máscara).", icono="eraser")
                return None
            n = 1 + sum(1 for c in doc.capas if c.tipo == "pixeles")
            id_img = v._almacen.guardar(np.zeros((doc.alto, doc.ancho, 4), np.uint8))
            nueva = Capa(doc.id_libre(), "pixeles", f"Capa {n}", imagen=id_img,
                         transform=Transformacion(doc.ancho / 2.0, doc.alto / 2.0))
            try:
                doc = doc.agregar(nueva, encima_de=self._encima_de(doc))
            except ValueError as error:
                v.aviso.mostrar(str(error), "", icono="triangle-alert")
                return None
            return doc, nueva.id, nueva.nombre, True
        if capa.bloqueada:
            v.aviso.mostrar(f"La capa «{capa.nombre}» está bloqueada.", "", icono="lock")
            return None
        if capa.tipo in ("texto", "forma", "relleno"):
            if self.preguntar_rasterizar(capa):
                v.panel_capas.elegir_sin_avisar(capa.id)
                v.panel_capas.rasterizar()
                self.refrescar_propiedades()
            return None
        if capa.tipo not in ("pixeles", "imagen") or v._arreglo(capa.imagen) is None:
            return None
        if not self._visible(doc, capa):
            v.aviso.mostrar(f"La capa «{capa.nombre}» está oculta: mostrala (el ojo del panel Capas) para pintarla.",
                            "", icono="eye-off")
            return None
        return doc, capa.id, capa.nombre, False

    def _lienzo_de(self, doc: Documento, id_capa: str, ampliar: bool) -> Optional[Lienzo]:
        capa = doc.capa(id_capa)
        img = self.v._arreglo(capa.imagen)
        if img is None:
            return None
        return Lienzo(img, capa.transform, doc.ancho, doc.alto, ampliar=ampliar)

    def empezar_trazo(self, q: QPointF, borrar: bool = False) -> Optional[dict]:
        """El gesto de un trazo de Pincel o de Borrador que empieza en (q) (px del documento). Mientras se
        arrastra se ve en una superposición; al soltar, ``terminar_trazo``."""
        v = self.v
        destino = self.destino_pintura("borrador" if borrar else "pintar")
        if destino is None:
            return None
        doc, id_capa, nombre, nueva = destino
        lienzo = self._lienzo_de(doc, id_capa, ampliar=not borrar)
        if lienzo is None:
            return None
        op = self.pinceles["borrador" if borrar else "pintar"]
        trazo = TrazoEnCurso(lienzo, op["tamano"], op["dureza"], op["opacidad"], tuple(self.frente[:3]) + (255,),
                             borrar)
        trazo.agregar(q.x(), q.y())
        return {"tipo": "trazo", "trazo": trazo, "doc0": doc, "base": v._documento, "imagen": v._imagen,
                "id": id_capa, "nombre": nombre, "nueva": nueva, "borrar": borrar}

    def terminar_trazo(self, g: dict) -> bool:
        """El trazo se aplica a la capa (``pintura.trazo``): un paso del historial. True si cambió algo."""
        v = self.v
        if v._imagen is not g["imagen"] or v._documento is not g["base"]:
            return False  # cambió la foto o el documento mientras se pintaba (deshacer, la tira…)
        hecho = g["trazo"].aplicar()
        if hecho is None:
            return False
        img, transform = hecho
        id_img = v._almacen.guardar(np.ascontiguousarray(img))
        doc = g["doc0"].con_capa(g["id"], imagen=id_img, transform=transform)
        if g["nueva"]:
            v.panel_capas.elegir_sin_avisar(g["id"])
            descripcion = f"Pincel: capa nueva «{g['nombre']}»"
        else:
            descripcion = ("Borrador" if g["borrar"] else "Pincel") + f" en «{g['nombre']}»"
        self.confirmar(doc, descripcion)
        return True

    def cancelar_gesto(self) -> bool:
        """Esc durante un trazo o un degradado: se descarta (True si había uno)."""
        return self.activo and self.controlador.cancelar()

    def _composicion(self, doc: Documento) -> Optional[np.ndarray]:
        """Lo que se ve (sin el filtro), a tamaño completo: RGB uint8 del tamaño del documento."""
        from ..motor.documento import componer
        foto = None
        if doc.tiene_foto:
            foto = self._foto_srgb()
            if foto is None:
                return None
        try:
            return np.ascontiguousarray(componer(doc, self.v._almacen, foto)[..., :3])
        except (ValueError, MemoryError):
            return None

    def bote_en(self, q: QPointF) -> bool:
        """Bote de pintura en (q): rellena con el color de frente lo parecido (``pintura.bote``) en la capa
        elegida (o en una capa nueva). Un paso del historial. True si cambió algo."""
        import cv2
        from ..motor.pintura import bote
        v = self.v
        destino = self.destino_pintura("bote")
        if destino is None:
            return False
        doc, id_capa, nombre, nueva = destino
        lienzo = self._lienzo_de(doc, id_capa, ampliar=False)
        if lienzo is None:
            return False
        u, w_ = lienzo.a_capa(q.x(), q.y())
        img = lienzo.img
        alto, ancho = img.shape[:2]
        if not (0 <= u < ancho and 0 <= w_ < alto):
            return False
        op = self.opciones_bote
        muestra = None
        if op["todas"] or nueva:
            # La zona se elige por lo que se ve (una capa nueva está vacía: siempre así).
            comp = self._composicion(v._documento if nueva else doc)
            if comp is None:
                return False
            muestra = cv2.warpAffine(comp, lienzo.inv[:2], (ancho, alto), flags=cv2.INTER_NEAREST,
                                     borderMode=cv2.BORDER_REPLICATE)
        out = bote(img, u, w_, tuple(self.frente[:3]) + (255,), op["tolerancia"], op["contiguo"], muestra)
        if np.array_equal(out, img):
            return False
        doc = doc.con_capa(id_capa, imagen=v._almacen.guardar(np.ascontiguousarray(out)))
        if nueva:
            v.panel_capas.elegir_sin_avisar(id_capa)
            descripcion = f"Bote de pintura: capa nueva «{nombre}»"
        else:
            descripcion = f"Bote de pintura en «{nombre}»"
        self.confirmar(doc, descripcion)
        return True

    def aplicar_degradado(self, p0: QPointF, p1: QPointF) -> Optional[str]:
        """El degradado de p0 a p1 (px del documento). Si la capa elegida es de píxeles (o una imagen), se
        pinta ahí encima; si no, va a una **capa de relleno** nueva (lineal: el ángulo y las paradas de
        ese arrastre) o, si un relleno no lo puede repetir (radial con su centro, o más de 4 colores), a
        una capa de píxeles nueva. Un paso del historial. Devuelve el id de la capa."""
        from ..motor.pintura import degradado
        v = self.v
        if v._imagen is None or v._documento is None:
            return None
        self._antes_de_operar()
        doc = v._documento
        ancho, alto = v._tam_mostrado()
        if (doc.ancho, doc.alto) != (ancho, alto):
            doc = v._documento = dc.con_tamano(doc, ancho, alto)
        rel = self.relleno_degradado_efectivo()
        radial = self.degradado_radial
        opacidad = self.opacidad_degradado
        capa = self.capa_elegida()
        if capa is not None and capa.tipo in ("pixeles", "imagen") and doc.indice(capa.id) > 0:
            if capa.bloqueada:
                v.aviso.mostrar(f"La capa «{capa.nombre}» está bloqueada.", "", icono="lock")
                return None
            if not self._visible(doc, capa):
                v.aviso.mostrar(f"La capa «{capa.nombre}» está oculta: mostrala para pintarla.", "", icono="eye-off")
                return None
            lienzo = self._lienzo_de(doc, capa.id, ampliar=False)
            if lienzo is None:
                return None
            img = lienzo.img
            a, b = lienzo.a_capa(p0.x(), p0.y()), lienzo.a_capa(p1.x(), p1.y())
            grad = degradado(img.shape[1], img.shape[0], a, b, rel, radial=radial)
            out = fundir_encima(img, grad, opacidad)
            nuevo = doc.con_capa(capa.id, imagen=v._almacen.guardar(out))
            self.confirmar(nuevo, f"Degradado en «{capa.nombre}»")
            return capa.id
        n = 1 + sum(1 for c in doc.capas if c.nombre.startswith("Degradado"))
        nombre = f"Degradado {n}"
        relleno = None if radial else relleno_lineal_de_arrastre(rel, (p0.x(), p0.y()), (p1.x(), p1.y()),
                                                                 doc.ancho, doc.alto)
        if relleno is not None:
            nueva = Capa(doc.id_libre(), "relleno", nombre, opacidad=opacidad, params=relleno)
        else:
            img = degradado(doc.ancho, doc.alto, (p0.x(), p0.y()), (p1.x(), p1.y()), rel, radial=radial)
            nueva = Capa(doc.id_libre(), "pixeles", nombre, opacidad=opacidad, imagen=v._almacen.guardar(img),
                         transform=Transformacion(doc.ancho / 2.0, doc.alto / 2.0))
        self._agregar_capa(doc, nueva, f"Capa nueva: {nombre}")
        return nueva.id

    # ================================================================== Estilo de capa (U2)
    def estilo_de_capa(self, id_capa: Optional[str] = None):
        """"Capa › Estilo de capa…" (también doble clic en la capa o "fx"): el diálogo, con vista previa
        en vivo. Aceptar es un paso del historial; Cancelar vuelve. Devuelve el diálogo (abierto)."""
        from .estilos_capa import DialogoEstilos
        v = self.v
        if not self.activo or v._imagen is None or v._documento is None:
            return None
        if self.dialogo_estilos is not None:
            self.dialogo_estilos.raise_()
            return self.dialogo_estilos
        self._antes_de_operar()
        id_capa = id_capa or v.panel_capas.capa_elegida
        try:
            capa = v._documento.capa(id_capa)
        except KeyError:
            return None
        if capa.tipo not in TIPOS_CON_ESTILOS:
            v.aviso.mostrar("Los estilos de capa van en capas de imagen, píxeles, texto, forma o grupo.", "",
                            icono="layers")
            return None
        if capa.bloqueada:
            v.aviso.mostrar(f"La capa «{capa.nombre}» está bloqueada.", "", icono="lock")
            return None
        doc0 = v._documento
        dialogo = DialogoEstilos(capa.estilos, capa.nombre, v)
        dialogo.vistaPrevia.connect(lambda e: self._vista_previa_estilos(doc0, id_capa, e))
        dialogo.finished.connect(lambda r: self._terminar_estilos(dialogo, doc0, id_capa, r))
        self.dialogo_estilos = dialogo
        # A la izquierda de la ventana (sobre el Historial): así el lienzo queda a la vista.
        dialogo.adjustSize()
        arriba = max(0, (v.height() - dialogo.height()) // 2)
        dialogo.move(v.mapToGlobal(QPoint(12, arriba)))
        dialogo.open()
        return dialogo

    def _vista_previa_estilos(self, doc0: Documento, id_capa: str, estilos: EstilosCapa) -> None:
        v = self.v
        if v._documento is not doc0:
            return
        v._doc_provisorio = doc0.con_capa(id_capa, estilos=estilos)
        v.solicitar_render()

    def _terminar_estilos(self, dialogo, doc0: Documento, id_capa: str, resultado: int) -> None:
        v = self.v
        self.dialogo_estilos = None
        estilos = dialogo.estilos()
        dialogo.deleteLater()
        v._doc_provisorio = None
        doc = v._documento
        if resultado != QDialog.Accepted or doc is None or not any(c.id == id_capa for c in doc.capas):
            v.solicitar_render()
            return
        capa = doc.capa(id_capa)
        if capa.estilos == estilos:
            v.solicitar_render()
            return
        v._cambiar_documento(doc.con_capa(id_capa, estilos=estilos), refrescar_panel=True,
                             descripcion=f"Estilo de capa: «{capa.nombre}»")
        self.refrescar_propiedades()

    # ================================================================== máscaras
    def pintar_mascara(self, forma: str) -> None:
        """Pinta la máscara de la capa elegida con una zona (rectángulo, elipse, lazo o pincel), en el
        modo "mostrar" u "ocultar". Usa las mismas herramientas que los efectos."""
        v = self.v
        id_capa = v.panel_capas.capa_elegida
        if v._imagen is None or v._documento is None or id_capa is None:
            return
        capa = v._documento.capa(id_capa)
        if capa.bloqueada:
            v.aviso.mostrar(f"La capa «{capa.nombre}» está bloqueada.", "", icono="lock")
            return
        if self.transformando is not None:
            self.salir_transformar("aplicar")
        if self.recortando:
            self.terminar_recorte(False)
            self.herramienta = "mover"  # la máscara es de una pasada: después vuelve a Mover
        destino = DestinoMascara(self, id_capa, capa.nombre, v.panel_capas.modo_mascara)
        destino.instrucciones = {
            "mostrar": "marcá lo que querés que se vea",
            "ocultar": "marcá lo que querés ocultar",
        }[destino.modo] + (" (pintá; clic derecho borra, Enter termina)" if forma == "pincel" else "")
        self.etiqueta_mascara.setToolTip(f"Pintá la máscara de «{capa.nombre}»: lo que marques se ve o se oculta")
        v._pedir_zona(destino, forma)
        if self.activo:
            v.barra_pincel.hide()  # en Photoshop, el pincel se regula en la barra de opciones
        for w in getattr(self, "_widgets_pincel", []):
            w.setVisible(forma == "pincel")
        self.etiqueta_mascara.setVisible(forma != "pincel")  # con el pincel, el lugar es para sus controles
        v._sincronizar_pincel()
        self.boton_goma.blockSignals(True)
        self.boton_goma.setChecked(v.vista.pincel[2])
        self.boton_goma.blockSignals(False)

    def pintar_zona_en_mascara(self, id_capa: str, zona: Zona, modo: str) -> None:
        """Suma o resta la zona a la máscara de la capa (un paso del historial). La cuenta (a resolución
        completa) va en segundo plano; al terminar se pone en el documento de ese momento."""
        v = self.v
        doc = v._documento
        if doc is None or v._imagen is None or not any(c.id == id_capa for c in doc.capas):
            return
        doc = dc.con_tamano(doc, *v._tam_mostrado())
        v._traer_mascaras(doc)
        base = doc.capa(id_capa).mascara
        actual = dc.mascara_de(doc, v._almacen, id_capa)
        recorte = v._recorte
        marco = (v._imagen, v._geometria, v._recorte)

        def trabajo(_cancelado):
            return marco, id_capa, base, zona, modo, dc.pintar_mascara(actual, zona, modo, recorte)

        v._pool_archivos.start(Tarea("mascara_pintada", 0, trabajo, v._senales))

    def mascara_pintada(self, resultado) -> None:
        v = self.v
        marco, id_capa, base, zona, modo, nueva = resultado
        doc = v._documento
        if marco != (v._imagen, v._geometria, v._recorte) or doc is None \
                or not any(c.id == id_capa for c in doc.capas):
            return  # cambió la foto o su marco mientras tanto: esa pasada ya no vale
        if doc.capa(id_capa).mascara != base:
            self.pintar_zona_en_mascara(id_capa, zona, modo)  # otra pasada llegó antes: se suma sobre esa
            return
        id_m = v._almacen.guardar(nueva)
        v._cambiar_documento(dc.con_tamano(doc, *v._tam_mostrado()).con_capa(id_capa, mascara=id_m),
                             refrescar_panel=True)


FORMATOS_PORTAPAPELES = ("image/png", "PNG", "image/webp", "image/jpeg", "image/jpg", "JFIF", "image/gif",
                         "image/bmp", "image/x-bmp")


def imagen_del_portapapeles(datos) -> Optional[QImage]:
    """La imagen que hay en el portapapeles (``QMimeData``), o None. Primero la "imagen" que entiende Qt
    (la de casi todas las apps: el navegador, una captura de pantalla, Paint); si no, los bytes de un
    formato de imagen que dejaron ahí (un PNG con transparencia, un JPG…)."""
    if datos is None:
        return None
    formatos = list(datos.formats())

    def de_formato(buscados) -> Optional[QImage]:
        for buscado in buscados:
            for formato in formatos:
                # En Windows los formatos propios llegan como 'application/x-qt-windows-mime;value="PNG"'.
                if formato == buscado or formato.endswith(f'value="{buscado}"'):
                    imagen = QImage.fromData(bytes(datos.data(formato)))
                    if not imagen.isNull():
                        return imagen
        return None

    # Un PNG primero: conserva la transparencia (la imagen de Windows, un BMP, a veces la pierde).
    imagen = de_formato(("image/png", "PNG"))
    if imagen is not None:
        return imagen
    if datos.hasImage():
        imagen = datos.imageData()
        if isinstance(imagen, QPixmap):
            imagen = imagen.toImage()
        if isinstance(imagen, QImage) and not imagen.isNull():
            return imagen
    return de_formato(FORMATOS_PORTAPAPELES)


def _rgba_de_qimage(imagen: QImage) -> np.ndarray:
    """Una QImage (del portapapeles) → RGBA uint8 (h, w, 4), sin premultiplicar."""
    q = imagen.convertToFormat(QImage.Format_RGBA8888)
    h, w = q.height(), q.width()
    arr = np.frombuffer(q.constBits(), np.uint8, count=q.bytesPerLine() * h)
    return arr.reshape(h, q.bytesPerLine())[:, :w * 4].reshape(h, w, 4).copy()


__all__ = ["ColoresFrenteFondo", "ControladorVista", "DestinoMascara", "HERRAMIENTAS", "ModoPhotoshop"]
