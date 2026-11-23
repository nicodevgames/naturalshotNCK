"""Ventana principal.

Una sola ventana con cuatro modos en el selector de arriba a la izquierda,
"Fácil | Editor | Video | Audio". Fácil y Editor son de fotos (comparten todo el
estado); Video muestra el editor de video (``editor_video.EditorVideo``) y Audio
el de audio (``modo_audio.EditorAudio``) en esta misma ventana, en lugar de las
columnas de fotos. La marca y el selector quedan siempre en el mismo lugar. Abrir
y arrastrar llevan cada archivo a su modo (``abrir_rutas``).

En **NaturalShot Lite** (``edicion.es_lite()``, solo fotos) el selector tiene solo
"Fácil | Editor": no hay botón de Video, ni Ctrl+Shift+V ni Ctrl+Shift+A, ni chips de
exportación, y los videos y audios no se abren (avisa "NaturalShot Lite es solo para
fotos"). El editor de video y el de audio no se importan nunca.

Capas (etapa 1) y el modo Photoshop (solo en la Lite)
-----------------------------------------------------
En la Lite el selector es "Fácil | Editor | Photoshop" (Ctrl+Shift+P va y vuelve). Las capas se
editan en **Photoshop**: a la izquierda, una barra angosta de herramientas (Mover y las de la
máscara) con sus opciones; en el centro, la vista **sin el filtro** (sin Antes ni Después; "Ver
con el filtro" lo previsualiza) y la tira; a la derecha, el panel Capas y el Historial. En Fácil
y en Editor (que queda como antes) el filtro va arriba de la composición, y su "Antes" es la
composición sin el filtro. En la PRO no hay modo Photoshop.

Cada foto de la tira tiene su **documento de capas** (``motor.documento.Documento``): la
"Foto" abajo, capas imagen en el medio y el ajuste "Celular natural" arriba. Todas las
imágenes y máscaras van en un solo ``AlmacenImagenes`` de la ventana (por contenido).

* **La capa "Foto"** es lo que hoy entra al filtro: lo que arma ``_recalcular_fuentes``
  (geometría, montaje, borrado y recorte) más el desenfoque de fondo (``con_desenfoque``).
* **El filtro** de siempre (``procesar_pila`` con el preset, los efectos y los ajustes) es la
  función ``filtro`` de ``componer``, que lo aplica sobre todo lo de abajo y lo mezcla según la
  capa "Celular natural" (opacidad = cuánto filtro, visible, fusión y máscara).
* **Sin capas** (documento "trivial": ``documento_capas.es_trivial``) no se llama a
  ``componer``: la vista y la exportación son las de siempre, bit a bit, y el estado de la
  foto no lleva documento (las sesiones e historiales viejos siguen iguales).
* **Vista previa:** en los mismos hilos de siempre, con ``componer`` y una
  ``CacheComposicion`` por escala (la rápida y la completa). **Exportar:** ``componer`` a
  escala 1, sin caché. En los dos casos la foto se pasa con ``clave_foto`` y el filtro con
  ``clave_filtro``.
* **El documento** va en el estado de la foto (``estado["documento"]``), así cada cambio de
  capas es un paso del historial, la sesión lo recuerda (las imágenes, como PNG en la carpeta
  de la sesión) y deshacer lo vuelve atrás. Al girar o recortar, las capas se llevan al marco
  nuevo (``documento_capas.convertir_documento``).
* **Proyecto ``.nslite``** (Ctrl+S): el documento con sus imágenes más, en ``extra``, la ruta
  de la foto original y el estado de la edición en JSON (``documento_capas.estado_a_json``).

Medida de salida (Fácil y Editor)
---------------------------------
El botón **Medida** de la barra (``ui/medida.py``) elige una medida estándar (9:16 · 1080×1920,
16:9 · 1920×1080…). Va en el estado de la foto (``estado["medida"]``; sin medida, la clave no está):
pone un recorte con esa proporción (el de siempre) y la foto recortada se lleva a esos píxeles
**antes** del filtro (``procesar_con_capas(…, medida=…)``), así el grano y la compresión tienen el
tamaño de la salida; la vista previa hace lo mismo a escala (``motor/medida.py``). Con una medida,
el recorte siempre tiene su proporción: Recortar la deja fija, y girar o enderezar lo reacomodan.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
import os
import threading
import traceback
import zlib
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Optional

import numpy as np
from PIL import Image
from PySide6.QtCore import QEvent, QObject, QRectF, QSize, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton,
    QAbstractScrollArea, QAbstractSpinBox, QListWidget, QListWidgetItem, QPlainTextEdit, QScrollArea, QSizePolicy,
    QSlider, QTextEdit, QVBoxLayout, QWidget,
)

from .. import NOMBRE_APP, edicion, sesion
from ..motor import (
    PRESETS, Ajustes, ImagenCargada, TransformacionPantalla, cargar_imagen, exportar_imagen,
    procesar_lote, procesar_pila, reducir_para_vista, ruta_salida_sugerida,
)
from ..motor.desenfoque import desenfocar_zona
from ..motor.documento import (
    LADO_MAX, AlmacenImagenes, CacheComposicion, Documento, capas_faltantes, componer as componer_capas,
    tamano_salida, transformacion_ajustada,
)
from ..motor import medida as md
from ..motor.edicion import (
    aplicar_borrados, con_geometria, convertir_borrado, convertir_recorte, convertir_zona,
)
from ..motor.proyecto_lite import EXTENSION as EXTENSION_PROYECTO, MAX_PIXELES_IMAGEN, abrir_proyecto, guardar_proyecto
from ..motor.geometria import Geometria, aplicar_geometria, detectar_horizonte, tamano_resultante
from ..motor.imagen_io import EXTENSIONES_SOPORTADAS
from ..motor.montaje import componer
from ..motor.seleccion_auto import mascara_cielo, mascara_piel, recortar_objeto
from ..motor.zonas import Recorte, Zona, aplicar_recorte, mascara_registrada, mascara_zona, registrar_mascara
from . import estilo, iconos, presets_usuario
from .actualizaciones import ControladorActualizaciones
from .aviso import AvisoFlotante
from .borrar import PanelBorrar
from .controles import SIN_EFECTO, PanelAjustes, SeccionPlegable, separador
from . import documento_capas as dc
from .historial import describir_cambio
from .medida import MenuMedida
from .modo_photoshop import ModoPhotoshop
from .panel_capas import PanelCapas, miniatura as miniatura_capa
from .fondo import FONDO_INICIAL, PanelFondo, completar_estado
from .modo_facil import (
    AUDIO, EDITOR, FACIL, PHOTOSHOP, VIDEO, PanelFacil, guardar_modo, modo_fotos_guardado, modo_guardado,
)
from .modo_video import (
    COLOR_AUDIO, COLOR_VIDEO, FILTRO_ABRIR_AUDIO, FILTRO_ABRIR_FOTOS, BotonModo, ChipExportacion, EtiquetaElidida,
    clasificar_rutas, es_audio, es_foto, es_video, icono_modo, mensaje_ruteo, mensaje_solo_fotos,
)
from .modo_video import FILTRO_ABRIR as FILTRO_ABRIR_TODO  # Abrir (acá FILTRO_ABRIR es el de "Procesar varias")
from .montaje import PanelMontaje
from .tira import LADO_MINIATURA, TiraFotos
from .tareas import SenalesTarea, Tarea
from .vista_comparacion import VistaComparacion

AYUDA_SIN_FOTO = ("Es un documento nuevo, sin foto: recortar, enderezar, montaje, borrar objetos y fondo son para "
                  "fotos. Recortá, rotá o cambiá el tamaño desde el menú Imagen del modo Photoshop.")
LADO_VISTA_PREVIA = 1280  # lado largo de la versión reducida para respuesta inmediata
LADO_INICIAL_CONTORNO = 1024  # la selección aproximada que se le pasa a "Ajustar al contorno"
MAX_HISTORIAL = 100
ESPERA_SESION = 2000  # ms: la sesión se guarda a los 2 s de un cambio (como mucho una vez cada 2 s)
FILTRO_ABRIR = "Imágenes ({})".format(" ".join(f"*{e}" for e in EXTENSIONES_SOPORTADAS))
TEXTO_DETECCION = {"cielo": "Detectando el cielo…", "piel": "Detectando la piel…",
                   "contorno": "Ajustando al contorno…"}
SIN_DETECCION = {"cielo": "No encontré cielo en esta foto.",
                 "piel": "No encontré piel en esta foto.",
                 "contorno": "No pude separar el objeto del fondo. Probá marcarlo con más margen."}


def estado_con_geometria(estado: dict, nueva: Geometria, w: int, h: int,
                         almacen: Optional[AlmacenImagenes] = None) -> dict:
    """El estado del editor con otra geometría: zonas, recorte, borrados y capas convertidos.

    Todo lo marcado se guarda en coordenadas de la foto base (girada, volteada y
    enderezada, sin recortar). Al cambiar la geometría se lleva cada cosa al
    marco nuevo para que siga sobre el mismo objeto (``motor.edicion``). Las capas del
    documento (si hay, y con ``almacen``, donde quedan sus máscaras convertidas) también.
    ``w`` y ``h``: tamaño de la foto ORIGINAL.
    """
    vieja = estado.get("geometria") or Geometria()
    nuevo = dict(estado)
    nuevo["geometria"] = nueva
    if nueva == vieja:
        return nuevo

    def zona(z):
        return convertir_zona(z, vieja, nueva, w, h)

    nuevo["capas"] = [(p, i, zona(resto[0]) if resto else None) for p, i, *resto in estado.get("capas", [])]
    nuevo["montaje"] = tuple(replace(c, zona=zona(c.zona)) for c in estado.get("montaje", ()))
    fondo = completar_estado(estado.get("fondo"))
    nuevo["fondo"] = (zona(fondo[0]),) + tuple(fondo[1:])
    nuevo["borrado"] = tuple(convertir_borrado(b, vieja, nueva, w, h) for b in estado.get("borrado", ()))
    nuevo["recorte"] = convertir_recorte(estado.get("recorte"), vieja, nueva, w, h)
    medida = md.medida_valida(estado.get("medida"))
    if medida is not None:
        # Con una medida, el recorte conserva su proporción (al girar 90° se daría vuelta).
        nuevo["recorte"] = md.recorte_con_medida(nuevo["recorte"], *tamano_resultante(w, h, nueva), medida)
    doc = estado.get("documento")
    if isinstance(doc, Documento) and almacen is not None:
        m = dc.matriz_marco(w, h, vieja, estado.get("recorte"), nueva, nuevo["recorte"])
        doc = dc.convertir_documento(doc, almacen, m, *dc.tamano_documento(w, h, nueva, nuevo["recorte"]))
        if dc.es_trivial(doc):
            nuevo.pop("documento", None)
        else:
            nuevo["documento"] = doc
    return nuevo


def a_qimage(rgb: np.ndarray, alpha: Optional[np.ndarray] = None) -> QImage:
    """Convierte un arreglo RGB uint8 a QImage (copia independiente)."""
    if alpha is not None:
        # Para mostrar, las zonas transparentes se componen sobre gris neutro.
        if alpha.shape[:2] != rgb.shape[:2]:
            import cv2
            alpha = cv2.resize(alpha, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_AREA)
        a = alpha.astype(np.float32)[..., None] / 255.0
        # Las zonas transparentes se ven sobre un tablero de ajedrez, como en un editor de fotos.
        h, w = rgb.shape[:2]
        lado = max(6, round(max(h, w) / 90))
        yy, xx = np.mgrid[0:h, 0:w]
        tablero = np.where(((yy // lado + xx // lado) % 2) == 0, 58, 88).astype(np.float32)[..., None]
        rgb = (rgb.astype(np.float32) * a + tablero * (1.0 - a) + 0.5).astype(np.uint8)
    rgb = np.ascontiguousarray(rgb)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


def alpha_con_fondo(alpha: Optional[np.ndarray], fondo: Optional[Zona], recorte: Optional[Recorte],
                    h: int, w: int) -> Optional[np.ndarray]:
    """Transparencia final: la de la foto combinada con el fondo transparente (afuera del objeto = transparente)."""
    if fondo is None:
        return alpha
    m = mascara_zona(fondo, h, w, recorte)
    if alpha is not None:
        if alpha.shape[:2] != (h, w):
            import cv2
            alpha = cv2.resize(alpha, (w, h), interpolation=cv2.INTER_AREA)
        m = m * (alpha.astype(np.float32) / 255.0)
    return np.clip(m * 255.0 + 0.5, 0, 255).astype(np.uint8)


def con_desenfoque(rgb: np.ndarray, desenfoque: Optional[tuple], recorte: Optional[Recorte]) -> np.ndarray:
    """La foto con el fondo desenfocado (modo retrato), o tal cual si no se desenfoca.

    ``desenfoque``: (zona, intensidad, transición, profundidad) de la tarjeta Fondo.
    Va antes del filtro, así el ruido y el grano quedan parejos sobre toda la foto.
    """
    if desenfoque is None:
        return rgb
    zona, intensidad, transicion, profundidad = desenfoque
    return desenfocar_zona(rgb, zona, intensidad, transicion, profundidad, recorte)


def _png_escrito(ruta: Path) -> bool:
    """Si ese PNG de la sesión ya está escrito (uno vacío, de un corte, no cuenta)."""
    try:
        return ruta.stat().st_size > 0
    except OSError:
        return False


def es_proyecto(ruta: str) -> bool:
    """Un proyecto con capas de NaturalShot (``.nslite``)."""
    return Path(ruta).suffix.lower() == EXTENSION_PROYECTO


def con_proyectos(filtro: str) -> str:
    """El filtro del diálogo de Abrir con los proyectos ``.nslite``: suma la extensión al primer
    grupo (el que se ve al abrir) y agrega "Proyectos de NaturalShot" como opción propia."""
    primero, _, resto = filtro.partition(";;")
    if primero.endswith(")"):
        primero = primero[:-1] + f" *{EXTENSION_PROYECTO})"
    proyectos = f"Proyectos de NaturalShot (*{EXTENSION_PROYECTO})"
    return ";;".join(x for x in (primero, proyectos, resto) if x)


def _escala_documento(ancho: int, alto: int, rgb: np.ndarray) -> Optional[float]:
    """La escala de ``componer`` que da exactamente el tamaño de ``rgb`` para un documento de
    ``ancho`` × ``alto`` (la vista previa reducida redondea cada lado por su cuenta). None si no hay."""
    h, w = rgb.shape[:2]
    doc = Documento.nuevo(ancho, alto)
    for e in (w / ancho, h / alto, (w / ancho + h / alto) / 2):
        if tamano_salida(doc, e) == (h, w):
            return e
    return None


def procesar_con_capas(rgb: np.ndarray, doc: Optional[Documento], almacen: AlmacenImagenes, pila, zonas,
                       recorte: Optional[Recorte], desenfoque: Optional[tuple], escala_vista: float,
                       tam_documento: tuple[int, int], cancelado=None, cache: Optional[CacheComposicion] = None,
                       clave_foto=None, con_filtro: bool = True,
                       medida: Optional[tuple[int, int]] = None) -> np.ndarray:
    """El resultado de la foto con sus capas: lo que se ve y lo que se exporta.

    ``rgb``: la foto que entra al filtro (``_fuente`` o su reducción para la vista previa), sin el
    desenfoque de fondo (se aplica acá: es parte de la capa "Foto"). ``tam_documento``: (ancho,
    alto) de la foto a resolución completa, que es el tamaño del documento.

    Sin capas (``es_trivial``) es exactamente lo de siempre: ``procesar_pila`` sobre la foto. Con
    capas, ``componer`` con el filtro de siempre como capa de ajuste (ver el módulo).

    ``con_filtro=False`` (el modo Photoshop, y el "Antes" de Fácil y Editor): la composición de las
    capas sin el filtro (la capa "Celular natural" no se aplica).

    ``medida`` (ancho, alto): la Medida de salida. La foto (ya recortada con su proporción) se lleva
    a esa medida **antes** del filtro, así el filtro trabaja a la resolución de salida (el grano y la
    compresión dependen de la escala: ver ``motor/medida.py``). A escala 1 sale exacta; en la vista
    previa reducida, a escala (``medida.tamano_trabajo``). Sin medida, nada cambia.
    """
    base = con_desenfoque(rgb, desenfoque, recorte)
    medida = md.medida_valida(medida)
    tam_trabajo = None
    if medida is not None:
        tam_trabajo, escala_vista = md.tamano_trabajo(medida, base.shape[:2], escala_vista)
        base = md.llevar_a_medida(base, tam_trabajo)

    def filtro(img: np.ndarray) -> np.ndarray:
        return procesar_pila(img, pila, escala_vista=escala_vista, cancelado=cancelado, zonas=zonas, recorte=recorte)

    if dc.es_trivial(doc):
        return filtro(base) if con_filtro else base.copy()
    ancho, alto = tam_documento
    doc_r = dc.con_tamano(doc, ancho, alto)
    escala = _escala_documento(ancho, alto, base)
    if escala is None:  # no debería pasar: se lleva la foto al tamaño exacto
        import cv2
        escala = base.shape[1] / ancho
        h, w = tamano_salida(doc_r, escala)
        base = cv2.resize(base, (w, h), interpolation=cv2.INTER_AREA)
    clave_filtro = (tuple(pila), tuple(zonas), recorte, float(escala_vista))
    salida = componer_capas(doc_r, almacen, base, escala, filtro if con_filtro else None, cache,
                            clave_foto=(clave_foto, desenfoque, base.shape), clave_filtro=clave_filtro)
    if tam_trabajo is not None and (salida.shape[1], salida.shape[0]) != tam_trabajo:
        salida = md.llevar_a_medida(salida, tam_trabajo)  # el redondeo de las capas (1 px como mucho)
    return salida


def forma_salida(fuente: np.ndarray, medida) -> tuple:
    """La forma (alto, ancho, 3) del resultado a escala 1: la de la foto que entra o la de la medida."""
    medida = md.medida_valida(medida)
    return fuente.shape if medida is None else (medida[1], medida[0], 3)


@lru_cache(maxsize=48)
def contornos_pincel(zona: Zona, recorte: Optional[Recorte], h: int, w: int) -> tuple:
    """Contorno de una zona (pintada, automática o cualquier otra), normalizado a la
    foto mostrada (recortada).

    ``h`` y ``w``: tamaño chico con la proporción de la foto mostrada (alcanza para dibujarlo).
    """
    import cv2
    m = mascara_zona(replace(zona, invertir=False), h, w, recorte)
    contornos, _ = cv2.findContours((m >= 0.5).astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    salida = []
    for c in contornos:
        c = cv2.approxPolyDP(c, 0.8, True).reshape(-1, 2)
        if len(c) >= 3:
            salida.append(tuple(((x + 0.5) / w, (y + 0.5) / h) for x, y in c))
    return tuple(salida)


def recortar_a_objeto(rgb: np.ndarray, alpha: np.ndarray, margen: float = 0.02):
    """Recorta imagen y alfa al rectángulo que ocupa el objeto (más un margen chico)."""
    filas = np.where(alpha.max(axis=1) > 2)[0]
    cols = np.where(alpha.max(axis=0) > 2)[0]
    if filas.size == 0 or cols.size == 0:
        return rgb, alpha
    h, w = alpha.shape
    m = round(max(h, w) * margen)
    y0, y1 = max(0, filas[0] - m), min(h, filas[-1] + 1 + m)
    x0, x1 = max(0, cols[0] - m), min(w, cols[-1] + 1 + m)
    return np.ascontiguousarray(rgb[y0:y1, x0:x1]), np.ascontiguousarray(alpha[y0:y1, x0:x1])


@dataclass
class FotoSesion:
    """Una foto de la tira, con su imagen cacheada y su propia edición."""
    ruta: str
    imagen: Optional[ImagenCargada] = None
    miniatura: Optional[QPixmap] = None
    estado: Optional[dict] = None  # ajustes, efectos, recorte, montaje y capas (documento) de esta foto
    historial: Optional[list] = None
    pos: int = 0
    proyecto: Optional[str] = None  # el .nslite donde se guardó (Ctrl+S lo vuelve a usar)


class _FiltroGlobal(QObject):
    """Base de los filtros instalados en toda la aplicación.

    Qt también les pasa eventos de objetos que viven en hilos de trabajo (por
    ejemplo, durante el procesado del video). Tocar esos eventos desde Python
    puede romper la memoria y cerrar la app, así que se ignoran de entrada,
    sin leerlos: solo se atienden los del hilo de la interfaz.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hilo_interfaz = threading.get_ident()

    def _es_de_otro_hilo(self) -> bool:
        return threading.get_ident() != self._hilo_interfaz


class FiltroRueda(_FiltroGlobal):
    """La rueda del mouse desplaza los paneles en vez de cambiar valores sin querer.

    Los desplegables y los números nunca cambian con la rueda; los deslizadores
    solo si antes se les hizo clic (tienen el foco). La rueda pasa al panel que
    los contiene, así que se sigue pudiendo bajar por la lista de ajustes.
    """

    def eventFilter(self, objeto, evento) -> bool:
        if self._es_de_otro_hilo():
            return False
        if evento.type() != QEvent.Wheel or not isinstance(objeto, QWidget):
            return False
        control = objeto
        while control is not None and not isinstance(control, (QComboBox, QAbstractSpinBox, QSlider)):
            if isinstance(control, (QAbstractScrollArea, VistaComparacion)) or control.isWindow():
                return False  # la rueda llegó a un panel o a la foto: comportamiento normal
            control = control.parentWidget()
        if control is None:
            return False
        if isinstance(control, QSlider) and control.hasFocus():
            return False
        # Se reenvía a la barra de desplazamiento del panel que contiene el control.
        area = control.parentWidget()
        while area is not None and not isinstance(area, QAbstractScrollArea):
            area = area.parentWidget()
        if area is not None:
            QApplication.sendEvent(area.verticalScrollBar(), evento)
        return True


class FiltroBarraEspaciadora(_FiltroGlobal):
    """Mientras se mantiene la barra espaciadora se muestra la foto original (en el modo Photoshop,
    que no tiene "Antes": la Mano, para desplazar la vista con cualquier herramienta)."""

    def __init__(self, ventana: "VentanaPrincipal"):
        super().__init__(ventana)
        self._ventana = ventana

    def eventFilter(self, objeto, evento) -> bool:
        if self._es_de_otro_hilo():
            return False
        tipo = evento.type()
        if tipo in (QEvent.KeyPress, QEvent.KeyRelease) and evento.key() == Qt.Key_Space:
            if self._ventana.modo in (VIDEO, AUDIO):
                return False  # en Video y en Audio, Espacio reproduce o pausa (atajo de su editor)
            if isinstance(objeto, (QLineEdit, QAbstractSpinBox, QTextEdit, QPlainTextEdit)):
                return False  # escribiendo (el nombre de una capa, un texto en la vista): el espacio es un espacio
            if not self._ventana.isActiveWindow() or not self._ventana.vista.tiene_imagen():
                return False
            if not evento.isAutoRepeat():
                if self._ventana.modo == PHOTOSHOP:
                    self._ventana.photoshop.mano_temporal(tipo == QEvent.KeyPress)
                else:
                    self._ventana.vista.mostrar_antes_temporal(tipo == QEvent.KeyPress)
            return True
        return False


class _RectanguloContorno:
    """Destino del rectángulo que se arrastra alrededor del objeto para "Ajustar al contorno"."""

    nombre = "Objeto"
    zona = None
    instrucciones = "arrastrá un rectángulo alrededor del objeto, con un poco de margen"

    def __init__(self, ventana: "VentanaPrincipal"):
        self._ventana = ventana

    def establecer_zona(self, zona: Optional[Zona]) -> None:
        if zona is not None:
            z = zona.normalizada()
            self._ventana._detectar(self._ventana.panel_fondo, "contorno", (z.x0, z.y0, z.x1, z.y1))

    def zona_cancelada(self) -> None:
        pass


class VentanaPrincipal(QMainWindow):
    sesionRestaurada = Signal()  # terminó de recuperar la sesión anterior (con o sin fotos)

    def __init__(self, icono: Optional[QIcon] = None, al_avanzar=None):
        """``al_avanzar``: se llama entre las partes grandes de la construcción (main.py
        atiende ahí los eventos para que la animación de la pantalla de carga no se trabe)."""
        super().__init__()
        self._al_avanzar = al_avanzar or (lambda: None)
        # La edición se fija al armar la ventana: PRO (fotos, video y audio) o Lite (solo fotos).
        self._lite = edicion.es_lite()
        self._nombre_app = edicion.nombre_app()  # "NaturalShot PRO" o "NaturalShot Lite"
        self.setWindowTitle(self._nombre_app)
        if icono is not None:
            self.setWindowIcon(icono)
        self.resize(1360, 860)
        self.setMinimumSize(980, 620)
        self.setAcceptDrops(True)  # fotos y videos en cualquier parte de la ventana (``abrir_rutas``)

        self._imagen: Optional[ImagenCargada] = None
        self._transformacion: Optional[TransformacionPantalla] = None
        self._vista_previa: Optional[np.ndarray] = None
        self._escala_vista_previa = 1.0
        self._generacion = 0
        self._generacion_carga = 0
        self._generacion_completa_mostrada = -1
        self._resultado_completo: Optional[tuple[tuple[Ajustes, ...], np.ndarray]] = None
        self._exportando = False
        # Historial: lista de (descripción, estado) y la posición actual en ella.
        self._historial: list[tuple[str, dict]] = []
        self._pos_historial = 0
        self._restaurando = False
        # Recorte no destructivo y la foto ya recortada que se procesa.
        self._recorte: Optional[Recorte] = None
        self._medida: Optional[tuple[int, int]] = None  # la Medida de salida (ancho, alto) o None (Original)
        self._fuente: Optional[np.ndarray] = None
        self._alpha_fuente: Optional[np.ndarray] = None
        self._antes_completo: Optional[QImage] = None
        self._antes_actual: Optional[QImage] = None
        self._generacion_fuentes = 0
        self._modo_recorte = False
        self._capa_zona = None  # capa que espera que se dibuje su zona
        # Geometría no destructiva (girar, voltear, enderezar) y la foto base completa
        # (geometría + montaje + borrados, sin recortar) que usan las detecciones.
        self._geometria = Geometria()
        self._antes_original: Optional[QImage] = None  # la foto tal como se abrió
        self._base_completa: Optional[np.ndarray] = None
        self._clave_base: tuple = ()
        self._version_fuente = 0  # cambia cada vez que cambia la foto que entra al filtro
        self._fuentes_pendientes = False  # se está armando la foto base (geometría, montaje, borrado)
        self._modo_enderezar = False
        self._enderezar_fuente: Optional[np.ndarray] = None  # base chica, girada y en sRGB
        # Selección automática en segundo plano: (destino, tipo, generación).
        self._deteccion: Optional[tuple] = None
        self._generacion_deteccion = 0
        self._cache_detecciones: "OrderedDict[tuple, tuple[Zona, Optional[np.ndarray]]]" = OrderedDict()
        self._clon = None  # destino que espera que se elija de dónde clonar
        # Capas: el documento de la foto abierta (el de la historia: ``_estado_completo``), uno
        # provisorio mientras dura un gesto (arrastrar la opacidad o transformar: se ve pero todavía
        # no es un paso) y un solo almacén de imágenes y máscaras para todas las fotos.
        self._almacen = AlmacenImagenes()
        # Las máscaras de los pasos que no son el actual (historial, otras fotos), comprimidas (zlib):
        # una máscara de 24 MP ocupa 24 MB en el almacén y unos pocos KB acá. Se vuelven a poner en el
        # almacén al usarlas (``_traer_mascaras``). id -> (forma, bytes).
        self._comprimidas: dict[str, tuple] = {}
        self._documento: Optional[Documento] = None
        self._doc_provisorio: Optional[Documento] = None
        # (La transformación libre en curso, ``_transformando``, la lleva el modo Photoshop.)
        self._generacion_capa = 0
        self._guardando_proyecto = False
        # Una caché de ``componer`` por escala: la vista rápida y la completa (exportar no usa caché).
        self._cache_rapida = CacheComposicion()
        self._cache_completa = CacheComposicion(max_bytes=512 * 2 ** 20, max_ajustes=2)
        # Modo fácil o editor (comparten todo el estado) y qué foto es la vista previa reducida
        # (clave de la foto base y recorte), para las miniaturas de la galería de estilos.
        self._modo = EDITOR
        self._modo_fotos = EDITOR  # el último modo de fotos (Fácil o Editor): a donde vuelve Video
        self._clave_vista_previa: Optional[tuple] = None
        # El editor de video (modo Video): uno solo, adentro de esta ventana. Se arma la primera
        # vez que se entra a Video (recién ahí se carga PyAV).
        self.editor_video = None
        # El editor de audio (modo Audio): igual, se arma la primera vez que se entra a Audio.
        self.editor_audio = None
        self._audio_pendiente: Optional[sesion.AudioGuardado] = None  # de la sesión, hasta que se entra a Audio
        self._modo_antes_de_audio: Optional[str] = None  # a donde vuelve Ctrl+Shift+A
        self._titulo_fotos = self._nombre_app

        # Hilos: uno para la vista previa rápida, otro para la resolución completa
        # y otro para cargar/exportar. Así la vista rápida nunca espera a la lenta.
        self._pool_rapido = QThreadPool(self)
        self._pool_rapido.setMaxThreadCount(1)
        self._pool_completo = QThreadPool(self)
        self._pool_completo.setMaxThreadCount(1)
        self._pool_archivos = QThreadPool(self)
        self._pool_archivos.setMaxThreadCount(1)
        self._pool_deteccion = QThreadPool(self)  # cielo, piel y ajuste al contorno
        self._pool_deteccion.setMaxThreadCount(1)

        self._senales = SenalesTarea(self)
        self._senales.terminada.connect(self._tarea_terminada)
        self._senales.fallida.connect(self._tarea_fallida)

        self._timer_rapido = QTimer(self, singleShot=True, interval=15)
        self._timer_rapido.timeout.connect(self._lanzar_vista_rapida)
        self._timer_completo = QTimer(self, singleShot=True, interval=450)
        self._timer_completo.timeout.connect(self._lanzar_vista_completa)

        # El historial guarda un paso cuando los controles quedan quietos un momento
        # (mover un deslizador no llena el historial con cien pasos).
        self._timer_historial = QTimer(self, singleShot=True, interval=500)
        self._timer_historial.timeout.connect(self._registrar_historial)
        # El montaje se recalcula cuando los controles quedan quietos (es más pesado).
        self._timer_montaje = QTimer(self, singleShot=True, interval=250)
        self._timer_montaje.timeout.connect(self._recalcular_fuentes)
        self._fotos: list[FotoSesion] = []
        self._actual = -1
        self._pool_miniaturas = QThreadPool(self)
        self._pool_miniaturas.setMaxThreadCount(1)
        # Sesión: las fotos de la tira y sus ediciones se recuperan al volver a abrir la app.
        # Se enciende con ``activar_sesion`` (lo llama main.py; las pruebas, con un APPDATA propio).
        self._sesion_activa = False
        self._sesion_lista = False  # ya se recuperó: antes no se guarda nada (no se pisa la anterior)
        self._sesion_foto_pendiente = -1  # la foto de la sesión que se está abriendo
        self._al_restaurar_sesion: list = []  # funciones que esperan a que se recupere
        self._error_sesion_avisado = False
        self._pool_sesion = QThreadPool(self)  # leer y escribir el archivo, de a una vez y en orden
        self._pool_sesion.setMaxThreadCount(1)
        self._timer_sesion = QTimer(self, singleShot=True, interval=ESPERA_SESION)
        self._timer_sesion.timeout.connect(self.guardar_sesion)

        self._construir_interfaz()
        self._construir_acciones()
        self._historial = [("Inicio", self._estado_completo())]
        self._pos_historial = 0
        self._refrescar_historial()
        self._actualizar_habilitados()
        modo = modo_guardado()  # la primera vez, Fácil
        if modo == AUDIO:  # se cerró en Audio: abre ahí (y desde ahí se vuelve al último de fotos)
            self.establecer_modo(modo_fotos_guardado(), guardar=False)
        self.establecer_modo(modo, guardar=False)

        self._filtro_espacio = FiltroBarraEspaciadora(self)
        self._filtro_rueda = FiltroRueda(self)
        self._filtros_puestos = False
        self._poner_filtros_globales()

    def _poner_filtros_globales(self) -> None:
        """Instala los filtros de toda la app (barra espaciadora y rueda). Al cerrar la ventana se
        sacan (``closeEvent``): una ventana cerrada no tiene por qué seguir viendo cada evento de la
        app (en las pruebas quedaban decenas de ventanas cerradas filtrando todo)."""
        if not self._filtros_puestos:
            app = QApplication.instance()
            app.installEventFilter(self._filtro_espacio)
            app.installEventFilter(self._filtro_rueda)
            self._filtros_puestos = True

    def _sacar_filtros_globales(self) -> None:
        if self._filtros_puestos:
            app = QApplication.instance()
            app.removeEventFilter(self._filtro_espacio)
            app.removeEventFilter(self._filtro_rueda)
            self._filtros_puestos = False

    def showEvent(self, evento) -> None:
        self._poner_filtros_globales()  # si se volviera a mostrar después de cerrarla
        super().showEvent(evento)

    # ============================================================ interfaz
    def _construir_interfaz(self) -> None:
        central = QWidget()
        central.setObjectName("raiz")
        # Arriba, el aviso de actualizaciones (oculto salvo que haya algo que decir).
        self.actualizaciones = ControladorActualizaciones(self)
        externa = QVBoxLayout(central)
        externa.setContentsMargins(0, 0, 0, 0)
        externa.setSpacing(0)
        externa.addWidget(self.actualizaciones.banner)
        raiz = QHBoxLayout()
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        externa.addLayout(raiz, 1)
        # Tres columnas al estilo Photoshop: presets | foto | ajustes.
        self.panel_ajustes = PanelAjustes()
        self.panel_ajustes.ajustesCambiados.connect(self._al_cambiar_ajustes)
        self.panel_ajustes.pedirZona.connect(self._pedir_zona)
        self.panel_montaje = PanelMontaje(self._otras_fotos)
        self.panel_montaje.cambiado.connect(self._al_cambiar_montaje)
        self.panel_montaje.pedirZona.connect(self._pedir_zona)
        self.panel_fondo = PanelFondo()
        self.panel_fondo.cambiado.connect(self._al_cambiar_fondo)
        self.panel_fondo.pedirZona.connect(self._pedir_zona)
        self.panel_fondo.pedirAjuste.connect(self.ajustar_al_contorno)
        self.panel_borrar = PanelBorrar()
        self.panel_borrar.cambiado.connect(self._al_cambiar_borrado)
        self.panel_borrar.pedirZona.connect(self._pedir_zona)
        self.panel_borrar.pedirFuente.connect(self._elegir_fuente)
        # Capas de la foto (columna derecha, arriba de los ajustes).
        self.panel_capas = PanelCapas()
        self.panel_capas.documentoCambiado.connect(self._al_cambiar_documento)
        self.panel_capas.agregarImagenPedida.connect(self.elegir_imagen_capa)
        self.panel_capas.transformarPedido.connect(lambda: self.alternar_transformar(True))
        self.panel_capas.pintarMascaraPedido.connect(self.pintar_mascara)
        self.panel_capas.aviso.connect(lambda texto: self.aviso.mostrar(texto, "", icono="triangle-alert"))
        self.panel_capas.capaElegida.connect(self._al_elegir_capa)
        # En el modo Photoshop el filtro no se ve: "Celular natural" queda arriba, bloqueado y atenuado,
        # y la máscara se pinta con las herramientas de la izquierda.
        self.panel_capas.configurar_photoshop()
        # Lo propio del modo Photoshop (menú, herramientas, opciones, Propiedades): ``ui/modo_photoshop.py``.
        self.photoshop = ModoPhotoshop(self)
        self._al_avanzar()
        raiz.addWidget(self._construir_barra_lateral())
        self._al_avanzar()

        # Fotos (Fácil y Editor): la columna del centro y la derecha. En el modo Video se
        # ocultan y en su lugar se ve el editor de video (``_asegurar_editor``).
        self._pagina_fotos = QWidget()
        pagina = QHBoxLayout(self._pagina_fotos)
        pagina.setContentsMargins(0, 0, 0, 0)
        pagina.setSpacing(0)
        contenido = QVBoxLayout()
        contenido.setContentsMargins(14, 14, 14, 14)
        contenido.setSpacing(12)
        contenido.addWidget(self._construir_barra_herramientas())
        contenido.addWidget(self._construir_tarjeta_vista(), 1)
        self._al_avanzar()
        self.tira = TiraFotos()
        self.tira.fotoElegida.connect(self.cambiar_a_foto)
        self.tira.agregarPedido.connect(self.elegir_archivo)
        self.tira.quitarPedido.connect(self.quitar_foto)
        self.tira.quitarTodasPedido.connect(self.quitar_todas_las_fotos)
        self.tira.hide()
        contenido.addWidget(self.tira)
        pagina.addLayout(contenido, 1)
        self.panel_derecho = self._construir_panel_derecho()
        self._al_avanzar()
        pagina.addWidget(self.panel_derecho)
        # Modo Photoshop (solo en la Lite): a la derecha, Capas e Historial.
        self.panel_derecho_ps = self._construir_panel_photoshop()
        pagina.addWidget(self.panel_derecho_ps)
        raiz.addWidget(self._pagina_fotos, 1)
        self._raiz = raiz
        # Modo fácil: usa el panel de ajustes y la exportación de las otras columnas,
        # así que se arma al final y va en la columna izquierda, debajo del selector.
        self.panel_facil = PanelFacil(self)
        self._al_avanzar()
        self._capa_lateral.insertWidget(self._capa_lateral.indexOf(self._caja_historial) + 1, self.panel_facil, 1)
        # Modo Photoshop: la barra de herramientas y sus opciones, en la columna izquierda.
        self.panel_herramientas_ps = self._construir_herramientas_photoshop()
        self._capa_lateral.insertWidget(0, self.panel_herramientas_ps, 1)
        self.setCentralWidget(central)
        self.statusBar().hide()

    def _construir_barra_lateral(self) -> QWidget:
        lateral = QFrame()
        lateral.setObjectName("barraLateral")
        lateral.setFixedWidth(372)
        capa = QVBoxLayout(lateral)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(0)

        # Marca
        marca = QHBoxLayout()
        marca.setContentsMargins(18, 18, 18, 14)
        marca.setSpacing(12)
        logo = QLabel()
        logo.setFixedSize(42, 42)
        ruta_logo = self.ruta_logo = edicion.ruta_logo()  # en la Lite, logo_lite.png
        if ruta_logo.exists():
            # Se escala al doble del tamaño en pantalla para que se vea nítido con escalado de Windows.
            pm = QPixmap(str(ruta_logo)).scaled(84, 84, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pm.setDevicePixelRatio(2.0)
            logo.setPixmap(pm)
        marca.addWidget(logo)
        textos = QVBoxLayout()
        textos.setSpacing(0)
        fila_titulo = QHBoxLayout()
        fila_titulo.setSpacing(8)
        titulo = QLabel(NOMBRE_APP)
        titulo.setObjectName("tituloApp")
        insignia = QLabel(edicion.insignia())
        insignia.setObjectName("insigniaPro")
        insignia.setAlignment(Qt.AlignCenter)
        if self._lite:  # LITE, violeta (la PRO va con el degradado magenta → violeta de estilo.py)
            insignia.setObjectName("insigniaLite")
            insignia.setStyleSheet(
                f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #a78bfa, stop:1 {estilo.VIOLETA});"
                " color: white; border-radius: 6px; font-size: 7.5pt; font-weight: 800; letter-spacing: 1px;"
                " padding: 2px 7px;")
        fila_titulo.addWidget(titulo)
        fila_titulo.addWidget(insignia, 0, Qt.AlignVCenter)
        fila_titulo.addStretch(1)
        # Solo el ícono: así no le quita lugar al nombre de la app.
        self.boton_tutorial = QPushButton()
        self.boton_tutorial.setObjectName("botonVersion")  # mismo estilo de chip que la versión
        self.boton_tutorial.setIcon(iconos.icono("book-open", 13))
        self.boton_tutorial.setIconSize(QSize(13, 13))
        self.boton_tutorial.setCursor(Qt.PointingHandCursor)
        self.boton_tutorial.setToolTip("Ver el tutorial: todo lo que podés hacer, paso a paso (F1)")
        self.boton_tutorial.clicked.connect(self.mostrar_tutorial)
        fila_titulo.addWidget(self.boton_tutorial, 0, Qt.AlignVCenter)
        fila_titulo.addWidget(self.actualizaciones.boton_version, 0, Qt.AlignVCenter)  # versión y actualizaciones
        self.subtitulo_app = subtitulo = QLabel("Editor de fotos realistas")
        subtitulo.setObjectName("subtituloApp")
        textos.addLayout(fila_titulo)
        textos.addWidget(subtitulo)
        marca.addLayout(textos, 1)
        capa.addLayout(marca)
        self._capa_columna = capa  # la columna entera: acá va también la del modo Video

        # Selector de modo, bien a la vista y siempre en el mismo lugar: Fácil (cuatro pasos),
        # Editor (todo) o Video (el editor de video, en esta misma ventana).
        self.grupo_interfaz = QButtonGroup(self)
        self.grupo_interfaz.setExclusive(True)
        botones_interfaz = []
        comun = " Fácil y Editor trabajan sobre la misma foto: cambiar no pierde nada (Ctrl+E)."
        modos = (
            (FACIL, " Fácil", "sparkles", "Modo fácil: abrir, elegir un estilo, cuánto efecto y exportar." + comun),
            (EDITOR, " Editor", "sliders-horizontal",
             "Modo editor: todos los controles (" + ("efectos, " if self._lite else "capas, ")
             + "zonas, montaje, borrar objetos, fondo y ajustes finos)."
             + comun),
            (VIDEO, " Video", "film",
             "Modo Video: editá un video con el mismo filtro (cortar, borrar partes y exportar en MP4 con sonido). "
             "Tus fotos quedan como estaban y el video sigue abierto al volver (Ctrl+Shift+V)."),
            (AUDIO, " Audio", "audio-lines",
             "Modo Audio: que una voz (grabada o hecha con IA) suene grabada con un celular en un lugar real: "
             "escenas, fondos, sonidos sueltos y bajarle lo de IA. Exporta para WhatsApp, M4A, MP3 o WAV. "
             "Lo demás queda como estaba y el audio sigue abierto al volver (Ctrl+Shift+A)."),
        )
        if self._lite:  # NaturalShot Lite: solo fotos, con el modo Photoshop (capas, sin el filtro)
            modos = modos[:2] + ((PHOTOSHOP, " Photoshop", "layers",
                                  "Modo Photoshop: editá la foto con capas (imágenes, logos, PNG con transparencia), "
                                  "moverlas y transformarlas, máscaras y modos de fusión. Se ve sin el filtro: el "
                                  "filtro celular natural se elige en Fácil o Editor y va arriba de todo "
                                  "(Ctrl+Shift+P)."),)
        for modo, texto, icono, ayuda in modos:
            b = BotonModo(texto)
            b.setIcon(icono_modo(icono, 16, {VIDEO: COLOR_VIDEO, AUDIO: COLOR_AUDIO}.get(modo)))
            b.setIconSize(QSize(16, 16))
            b.setCheckable(True)
            b.setProperty("modo", modo)
            b.setProperty("ayuda", ayuda)
            b.setToolTip(ayuda)
            self.grupo_interfaz.addButton(b)
            botones_interfaz.append(b)
        self.grupo_interfaz.buttonClicked.connect(lambda b: self.establecer_modo(b.property("modo")))
        selector = self._segmento(botones_interfaz)
        selector.setObjectName("selectorModo")
        for b in botones_interfaz:
            b.setObjectName("botonModo")
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # Video y Audio se distinguen de los dos modos de fotos (ícono de color y contorno).
        # En la Lite no están (ni sus chips): quedan en None.
        self.boton_modo_video = self.boton_modo_audio = self.chip_video = self.chip_audio = None
        if not self._lite:
            self.boton_modo_video, self.boton_modo_audio = botones_interfaz[2], botones_interfaz[3]
            for b in (self.boton_modo_video, self.boton_modo_audio):
                b.setProperty("destacado", True)
        caja_modo = QWidget()
        capa_modo = QVBoxLayout(caja_modo)
        capa_modo.setContentsMargins(16, 0, 16, 8)
        capa_modo.setSpacing(6)
        capa_modo.addWidget(selector)
        if not self._lite:
            # Exportación de video en curso mientras se trabaja en fotos (tocarlo lleva a Video).
            self.chip_video = ChipExportacion()
            self.chip_video.clicked.connect(lambda: self.establecer_modo(VIDEO))
            self.chip_video.hide()
            capa_modo.addWidget(self.chip_video)
            # Y la de audio, mientras se está en otro modo (tocarlo lleva a Audio).
            self.chip_audio = ChipExportacion(tipo="audio")
            self.chip_audio.clicked.connect(lambda: self.establecer_modo(AUDIO))
            self.chip_audio.hide()
            capa_modo.addWidget(self.chip_audio)
        capa.addWidget(caja_modo)

        # Lo de las fotos (tarjetas del editor, historial, pasos del modo fácil y pie), en su
        # propio contenedor: en el modo Video se oculta y se ve la columna del editor de video.
        self._lateral_fotos = QWidget()
        capa_fotos = QVBoxLayout(self._lateral_fotos)
        capa_fotos.setContentsMargins(0, 0, 0, 0)
        capa_fotos.setSpacing(0)
        capa.addWidget(self._lateral_fotos, 1)
        capa = self._capa_lateral = capa_fotos

        # Presets y capas desplazables
        panel = QWidget()
        capa_panel = QVBoxLayout(panel)
        capa_panel.setContentsMargins(16, 6, 12, 16)
        capa_panel.setSpacing(10)
        capa_panel.addWidget(self.panel_ajustes.lado_presets)
        # Un documento nuevo (sin foto): lo de la foto de base no aplica (se dice acá, arriba de esas tarjetas).
        self.nota_sin_foto = QLabel("Documento nuevo, sin foto: el filtro va sobre su composición. Montaje, "
                                    "borrar objetos y fondo son para fotos; recortar, rotar y el tamaño están en el "
                                    "menú Imagen del modo Photoshop.")
        self.nota_sin_foto.setObjectName("nota")
        self.nota_sin_foto.setWordWrap(True)
        self.nota_sin_foto.hide()
        capa_panel.addWidget(self.nota_sin_foto)
        # En el orden en que se aplican antes del filtro: montaje → borrar → fondo.
        capa_panel.addWidget(self.panel_montaje)
        capa_panel.addWidget(self.panel_borrar)
        capa_panel.addWidget(self.panel_fondo)
        capa_panel.addStretch(1)
        tarjeta_hist = SeccionPlegable("Historial", "history", "Cada cambio; tocá uno para volver a ese punto", True,
                                       con_interruptor=False, plegable=False)
        self.lista_historial = QListWidget()
        self.lista_historial.setObjectName("listaHistorial")
        self.lista_historial.setMinimumHeight(170)
        self.lista_historial.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        # Los pasos largos se cortan con "…" (el texto completo queda en la ayuda) en vez
        # de mostrar una barra horizontal.
        self.lista_historial.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lista_historial.setTextElideMode(Qt.ElideRight)
        self.lista_historial.itemClicked.connect(lambda it: self.ir_al_historial(self.lista_historial.row(it)))
        tarjeta_hist.capa_cuerpo.addWidget(self.lista_historial)
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        desplazable.setWidget(panel)
        capa.addWidget(desplazable, 1)
        self._lateral_editor = desplazable

        # Historial fijo abajo: siempre a la vista, aunque las capas ocupen mucho.
        caja_hist = QWidget()
        capa_hist = QVBoxLayout(caja_hist)
        capa_hist.setContentsMargins(16, 6, 16, 10)
        capa_hist.addWidget(tarjeta_hist)
        self._tarjeta_historial, self._capa_hist_izquierda = tarjeta_hist, capa_hist
        self.lista_historial.setMinimumHeight(0)
        self.lista_historial.setFixedHeight(150)
        capa.addWidget(caja_hist)
        self._caja_historial = caja_hist

        # Pie: foto abierta
        pie = QFrame()
        pie.setObjectName("pieLateral")
        self._pie_lateral = pie
        fila = QHBoxLayout(pie)
        fila.setContentsMargins(18, 12, 18, 14)
        fila.setSpacing(10)
        self.pie_avatar = QLabel("—")
        self.pie_avatar.setObjectName("avatar")
        self.pie_avatar.setFixedSize(34, 34)
        self.pie_avatar.setAlignment(Qt.AlignCenter)
        fila.addWidget(self.pie_avatar)
        datos = QVBoxLayout()
        datos.setSpacing(0)
        self.pie_nombre = QLabel("Sin foto abierta")
        self.pie_nombre.setObjectName("pieNombre")
        self.pie_detalle = QLabel("Procesado local · sin IA generativa")
        self.pie_detalle.setObjectName("pieDetalle")
        datos.addWidget(self.pie_nombre)
        datos.addWidget(self.pie_detalle)
        fila.addLayout(datos, 1)
        capa.addWidget(pie)
        return lateral

    def _construir_panel_derecho(self) -> QWidget:
        derecho = QFrame()
        derecho.setObjectName("panelDerecho")
        derecho.setFixedWidth(340)
        capa = QVBoxLayout(derecho)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(0)

        encabezado = QHBoxLayout()
        encabezado.setContentsMargins(16, 16, 12, 8)
        encabezado.setSpacing(8)
        icono = QLabel()
        icono.setPixmap(iconos.pixmap("sliders-horizontal", 18))
        titulo = QLabel("AJUSTES")
        titulo.setObjectName("tituloSeccion")
        restablecer = self.panel_ajustes.boton_restablecer
        restablecer.setText(" Restablecer")
        restablecer.setObjectName("botonChico")
        encabezado.addWidget(icono)
        encabezado.addWidget(titulo, 1)
        encabezado.addWidget(restablecer)
        capa.addLayout(encabezado)

        panel = QWidget()
        capa_panel = QVBoxLayout(panel)
        capa_panel.setContentsMargins(16, 0, 12, 12)
        capa_panel.addWidget(self.panel_ajustes.lado_ajustes)
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        desplazable.setWidget(panel)
        capa.addWidget(desplazable, 1)

        exportar = QFrame()
        exportar.setObjectName("pieDerecho")
        capa_exp = QVBoxLayout(exportar)
        capa_exp.setContentsMargins(16, 12, 16, 14)
        capa_exp.addWidget(self._construir_exportacion())
        capa.addWidget(exportar)
        return derecho

    # ------------------------------------------------------------ modo Photoshop (NaturalShot Lite)
    # Lo arma y lo maneja ``ui/modo_photoshop.py`` (``self.photoshop``). Acá quedan los nombres de
    # siempre, que usan el resto de la ventana y las pruebas.
    def _construir_panel_photoshop(self) -> QWidget:
        """La columna derecha del modo Photoshop: Propiedades y Capas."""
        return self.photoshop.construir_columna_derecha()

    def _construir_herramientas_photoshop(self) -> QWidget:
        """La columna izquierda del modo Photoshop: la barra de herramientas (con los colores) y el
        Historial al lado."""
        return self.photoshop.construir_columna_izquierda()

    @property
    def modo_mascara_ps(self) -> str:
        """"mostrar" u "ocultar": cómo pintan la máscara las herramientas del modo Photoshop."""
        return self.photoshop.modo_mascara

    def _herramienta_mascara_ps(self, forma: str) -> None:
        self.photoshop.herramienta_mascara(forma)

    def _actualizar_herramientas_ps(self) -> None:
        if hasattr(self, "photoshop"):
            self.photoshop.actualizar_herramientas()

    def _mudar_historial(self, a_photoshop: bool) -> None:
        self.photoshop.mudar_historial(a_photoshop)

    @property
    def _transformando(self) -> Optional[tuple]:
        """La transformación libre en curso: (id de la capa, transformación de antes), o None."""
        return self.photoshop.transformando if hasattr(self, "photoshop") else None

    @property
    def _textos_capas(self) -> dict:
        return self.photoshop.textos_capas

    @property
    def _quitando_fondo(self) -> bool:
        return self.photoshop.quitando_fondo

    def alternar_transformar(self, activo: bool) -> None:
        """Ctrl+T (y el botón del panel Capas): la transformación libre (``ModoPhotoshop.alternar_transformar``)."""
        self.photoshop.alternar_transformar(activo)

    def _capa_transformable(self) -> Optional[str]:
        return self.photoshop.capa_transformable()

    def _al_transformar(self, t) -> None:
        self.photoshop.al_transformar(t)

    def voltear_capa(self, vertical: bool = False) -> None:
        self.photoshop.voltear_capa(vertical)

    def _salir_transformar(self, accion: str) -> None:
        self.photoshop.salir_transformar(accion)

    def elegir_imagen_capa(self) -> None:
        self.photoshop.elegir_imagen_capa()

    def agregar_imagenes_como_capa(self, rutas) -> None:
        self.photoshop.agregar_imagenes_como_capa(rutas)

    def _capas_cargadas(self, resultado) -> None:
        self.photoshop.capas_cargadas(resultado)

    def nuevo_lienzo(self, ancho: Optional[int] = None, alto: Optional[int] = None, color=None, fondo=None) -> None:
        """"Nuevo" (Ctrl+N): un documento sin foto (``ModoPhotoshop.nuevo_lienzo``)."""
        self.photoshop.nuevo_lienzo(ancho, alto, color, fondo)

    def _capa_elegida(self):
        return self.photoshop.capa_elegida()

    def agregar_texto(self, datos: Optional[dict] = None) -> None:
        self.photoshop.agregar_texto(datos)

    def quitar_fondo_capa(self) -> None:
        self.photoshop.quitar_fondo_capa()

    def _fondo_quitado(self, resultado) -> None:
        self.photoshop.fondo_quitado(resultado)

    def recortar_desde_photoshop(self) -> None:
        self.photoshop.recortar_desde_photoshop()

    def pintar_mascara(self, forma: str) -> None:
        self.photoshop.pintar_mascara(forma)

    def _pintar_mascara(self, id_capa: str, zona: Zona, modo: str) -> None:
        self.photoshop.pintar_zona_en_mascara(id_capa, zona, modo)

    def _mascara_pintada(self, resultado) -> None:
        self.photoshop.mascara_pintada(resultado)

    # Para el menú Ver y la barra de opciones (se arman antes que la vista).
    def vista_acercar(self) -> None:
        self.vista.acercar()

    def vista_alejar(self) -> None:
        self.vista.alejar()

    def vista_ajustar(self) -> None:
        self.vista.ajustar()

    def vista_100(self) -> None:
        self.vista.fijar_zoom(1.0)

    def carpeta_inicio(self) -> str:
        """Dónde abren los diálogos de archivos: la carpeta de la foto abierta (un documento nuevo no
        tiene carpeta: Imágenes)."""
        if self._imagen is not None and not dc.es_ruta_documento(self._imagen.ruta):
            return str(self._imagen.ruta.parent)
        return str(Path.home() / "Pictures")

    @staticmethod
    def _segmento(botones) -> QFrame:
        """Agrupa botones en una sola píldora (control segmentado)."""
        caja = QFrame()
        caja.setObjectName("segmento")
        fila = QHBoxLayout(caja)
        fila.setContentsMargins(3, 3, 3, 3)
        fila.setSpacing(2)
        for b in botones:
            if isinstance(b, QPushButton):
                b.setObjectName("botonSegmento")
                b.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
                b.setCursor(Qt.PointingHandCursor)
            fila.addWidget(b)
        return caja

    def mostrar_tutorial(self) -> None:
        """Abre la guía de uso adentro de la app."""
        from .tutorial import DialogoTutorial
        DialogoTutorial(self).exec()

    def mostrar_tutorial_si_corresponde(self) -> None:
        """Al abrir la app: muestra el tutorial hasta que se tilde "No volver a mostrar"."""
        from .tutorial import debe_mostrarse_al_iniciar
        if debe_mostrarse_al_iniciar():
            self.mostrar_tutorial()

    def abrir_editor_video(self, ruta: Optional[str] = None) -> None:
        """Pasa al modo Video (en esta misma ventana) y, si viene ``ruta``, abre ese video.
        En la Lite no hay modo Video: solo avisa."""
        if self._lite:
            if ruta:
                self.abrir_rutas([str(ruta)])
            else:
                self._avisar_solo_fotos()
            return
        if ruta:
            self.abrir_rutas([str(ruta)])
        else:
            self.establecer_modo(VIDEO)

    # ============================================================ modos: fácil, editor, video y audio
    @property
    def modo(self) -> str:
        return self._modo

    @property
    def modo_fotos(self) -> str:
        """El último modo de fotos usado (Fácil o Editor): a donde se vuelve desde Video."""
        return self._modo_fotos

    def establecer_modo(self, modo: str, guardar: bool = True) -> None:
        """Fácil (cuatro pasos, sin la columna de ajustes), Editor (todo), Video o Audio.

        Fácil y Editor usan el mismo estado: la foto, la tira, el historial, el preset y lo
        editado en el editor quedan como estaban. Solo cambia qué se ve. Video muestra el
        editor de video en esta misma ventana: las fotos quedan como estaban y, al volver,
        el video sigue abierto con sus cortes (y una exportación en curso sigue). Audio,
        igual, con el editor de audio. Se recuerda el modo de fotos y Audio: si se cierra en
        Video, se vuelve a abrir en el último de fotos; si se cierra en Audio, en Audio.

        En la Lite, Video y Audio no existen: pedirlos no hace nada. En cambio tiene **Photoshop**
        (capas): a la izquierda, la barra de herramientas (Mover y las de la máscara) con sus opciones;
        en el centro, la vista sin el filtro (sin Antes ni Después) y la tira; a la derecha, Capas e
        Historial. En la PRO, Photoshop no existe."""
        if self._lite and modo in (VIDEO, AUDIO):
            return
        if modo == PHOTOSHOP and not self._lite:
            return
        if modo == VIDEO:
            self._entrar_a_video()
            return
        if modo == AUDIO:
            self._entrar_a_audio(guardar)
            return
        photoshop = modo == PHOTOSHOP
        facil = modo == FACIL
        modo = PHOTOSHOP if photoshop else FACIL if facil else EDITOR
        if self._modo == VIDEO:
            self._salir_de_video()
        elif self._modo == AUDIO:
            self._salir_de_audio()
        cambia_ps = photoshop != (self._modo == PHOTOSHOP)
        if modo != self._modo and (facil or cambia_ps):
            # Herramientas que el modo nuevo no muestra: se cancelan (no se pierde nada guardado). El
            # recorte está en Fácil y en Editor: solo se cancela al entrar o salir de Photoshop.
            if cambia_ps and self._modo_recorte:
                self._salir_recorte("cancelar")
            if self._modo_enderezar:
                self._salir_enderezar("cancelar")
            if self._transformando is not None:
                self._salir_transformar("cancelar")
            if self._clon is not None:
                self._cancelar_clon()
            if self._capa_zona is not None:
                self._zona_cancelada(self._capa_zona)
                self._cerrar_herramienta_zona()
        estaba_en_photoshop = self._modo == PHOTOSHOP
        self._modo = modo
        if not photoshop:
            self._modo_fotos = modo  # el último de Fácil y Editor (a donde vuelven Ctrl+Shift+P y Video)
        self._actualizar_selector()
        # Columna izquierda: los pasos, las tarjetas del editor (con historial y pie) o las herramientas.
        self._lateral_editor.setVisible(modo == EDITOR)
        self._caja_historial.setVisible(modo == EDITOR)
        self._pie_lateral.setVisible(modo == EDITOR)
        self.panel_facil.setVisible(facil)
        self.panel_herramientas_ps.setVisible(photoshop)
        self._mudar_historial(photoshop)
        # Derecha: los ajustes (Editor), nada (Fácil: la vista gana espacio) o Propiedades y Capas (Photoshop).
        self.panel_derecho.setVisible(modo == EDITOR)
        self.panel_derecho_ps.setVisible(photoshop)
        # Barra superior: en Fácil, solo lo esencial (girar 90° sí; enderezar fino y voltear no). En
        # Photoshop: el menú (Archivo tiene abrir y guardar), deshacer y rehacer, el kit y el zoom.
        self.grupo_modo.buttons()[0].parentWidget().setVisible(not photoshop)
        self.boton_abrir.setVisible(not photoshop)
        self._segmento_recorte.setVisible(not photoshop)
        self._segmento_medida.setVisible(not photoshop)  # en Photoshop está su propio Recortar
        self.boton_enderezar.setVisible(modo == EDITOR)
        self.botones_geometria[0].parentWidget().setVisible(not photoshop)
        for b in self.botones_geometria[2:]:
            b.setVisible(modo == EDITOR)
        self.boton_proyecto.parentWidget().setVisible(False)  # en Photoshop está en Archivo
        self._segmento_capa.setVisible(photoshop)
        self._segmento_zonas.setVisible(not photoshop)
        self._segmento_ver_filtro.setVisible(photoshop)
        # La vista: sin Antes ni Después en Photoshop (y sin los contornos de las zonas de los efectos).
        if photoshop and not estaba_en_photoshop:
            self._modo_vista_antes_de_ps = self.vista.modo
            self.vista.establecer_modo(VistaComparacion.MODO_SOLO)
        elif not photoshop and estaba_en_photoshop:
            self.vista.establecer_modo(getattr(self, "_modo_vista_antes_de_ps", VistaComparacion.MODO_DIVIDIR))
            self._marcar_boton(self.boton_ver_filtro, False)
        self._actualizar_superposiciones()
        if photoshop != estaba_en_photoshop:
            self._resultado_completo = None
            self.solicitar_render()  # con o sin el filtro
        if photoshop:
            self._sincronizar_pincel()  # las opciones del pincel, igual que el pincel de la vista
        self.photoshop.al_cambiar_modo(photoshop and not estaba_en_photoshop, estaba_en_photoshop and not photoshop)
        self._actualizar_herramientas_ps()
        self._actualizar_habilitados()
        self._actualizar_chip()
        self._actualizar_titulo()
        self._compactar_barra()
        if guardar:
            guardar_modo(modo)

    def alternar_photoshop(self) -> None:
        """Ctrl+Shift+P (Lite): al modo Photoshop y, desde ahí, de vuelta al último de Fácil y Editor."""
        if self._lite:
            self.establecer_modo(self._modo_fotos if self._modo == PHOTOSHOP else PHOTOSHOP)

    def alternar_modo(self) -> None:
        """Ctrl+E: Fácil <-> Editor. Desde Video, Audio o Photoshop, vuelve al último de Fácil y Editor."""
        if self._modo in (VIDEO, AUDIO, PHOTOSHOP):
            self.establecer_modo(self._modo_fotos)
        else:
            self.establecer_modo(EDITOR if self._modo == FACIL else FACIL)

    def alternar_video(self) -> None:
        """Ctrl+Shift+V: a Video y, desde Video, de vuelta al último modo de fotos."""
        self.establecer_modo(self._modo_fotos if self._modo == VIDEO else VIDEO)

    def alternar_audio(self) -> None:
        """Ctrl+Shift+A: a Audio y, desde Audio, de vuelta al modo de antes (fotos o Video)."""
        if self._modo == AUDIO:
            self.establecer_modo(self._modo_antes_de_audio or self._modo_fotos)
        else:
            self.establecer_modo(AUDIO)

    # ------------------------------------------------------------ modo Audio
    def _asegurar_editor_audio(self):
        """El editor de audio: se arma una sola vez, la primera que se entra a Audio (recién ahí se
        importa, con PyAV), y queda adentro de esta ventana. Como el de video: su columna izquierda
        va debajo de la marca y del selector; lo demás, en lugar de las columnas de fotos."""
        if self.editor_audio is not None:
            return self.editor_audio
        from .modo_audio import EditorAudio
        editor = EditorAudio(self)
        editor.hide()
        editor.lateral.hide()
        self._capa_columna.addWidget(editor.lateral, 1)
        self._raiz.addWidget(editor, 1)
        editor.audioCambiado.connect(self._al_cambiar_audio)
        editor.estadoCambiado.connect(self._sesion_cambiada)
        editor.exportacionCambiada.connect(self._al_cambiar_exportacion_audio)
        editor.progresoExportacion.connect(self.chip_audio.establecer_progreso)
        editor.exportacionLista.connect(self._audio_exportado)
        editor.volverAlVideoPedido.connect(self._volver_al_video_con_sonido)
        self.editor_audio = editor
        pendiente, self._audio_pendiente = self._audio_pendiente, None
        if pendiente is not None:
            self._restaurar_audio(pendiente)
        return editor

    def _restaurar_audio(self, guardado) -> None:
        """El proyecto de audio de la sesión anterior, en el editor (que ya existe)."""
        if not self.editor_audio.restaurar_sesion(guardado):
            nombre = Path(guardado.estado["proyecto"].ruta).name
            self.aviso.mostrar(f"No se pudo abrir {nombre}, el audio de la sesión anterior.",
                               guardado.estado["proyecto"].ruta)

    def _entrar_a_audio(self, guardar: bool = True) -> None:
        if self._modo == AUDIO:
            return
        editor = self._asegurar_editor_audio()
        self._modo_antes_de_audio = self._modo
        if self._modo == VIDEO:
            self._ocultar_video()
        self._modo = AUDIO
        # Primero se oculta lo de fotos: sus atajos dejan de andar y quedan los del editor de audio.
        self._lateral_fotos.hide()
        self._pagina_fotos.hide()
        editor.lateral.show()
        editor.show()
        self.subtitulo_app.setText("Que tu voz suene real")
        self._mover_aviso(editor.vista)
        self._actualizar_selector()
        self._actualizar_chip()
        self._actualizar_titulo()
        editor.compactar()
        if guardar:
            guardar_modo(AUDIO)

    def _ocultar_audio(self) -> None:
        """Oculta el editor de audio sin cerrar nada (el audio, su historial y una exportación en
        curso siguen ahí). Solo se pausa lo que suena."""
        editor = self.editor_audio
        if editor is not None:
            editor.pausar()
            editor.hide()
            editor.lateral.hide()

    def _salir_de_audio(self) -> None:
        self._ocultar_audio()
        self._lateral_fotos.show()
        self._pagina_fotos.show()
        self.subtitulo_app.setText("Editor de fotos realistas")
        self._mover_aviso(self._tarjeta_vista_fotos)
        self._refrescar_presets_propios(self.panel_ajustes)

    def _al_cambiar_audio(self) -> None:
        self._actualizar_selector()
        self._actualizar_titulo()

    def _al_cambiar_exportacion_audio(self, exportando: bool) -> None:
        if exportando:
            self.chip_audio.reiniciar()
        self._actualizar_chip()

    def _audio_exportado(self, texto: str, detalle: str) -> None:
        """Terminó de exportarse el audio mientras se trabajaba en otro modo: un aviso que no interrumpe."""
        self.aviso.mostrar(texto, detalle, icono="circle-check", segundos=20)

    def _asegurar_editor(self):
        """El editor de video: se arma una sola vez, la primera que se entra a Video, y queda
        adentro de esta ventana (nunca en una aparte). Su columna izquierda va debajo de la
        marca y del selector; lo demás, en lugar de las columnas de fotos."""
        if self.editor_video is not None:
            return self.editor_video
        from .editor_video import EditorVideo  # PyAV se carga recién acá: la app de fotos no lo usa
        editor = EditorVideo(self)
        editor.hide()  # ocultos antes de entrar al layout: así no aparecen solos
        editor.lateral.hide()
        self._capa_columna.addWidget(editor.lateral, 1)
        self._raiz.addWidget(editor, 1)
        # La primera vez, el filtro de las fotos (preset, intensidad, capas y ajustes; sin zonas).
        # Después el video tiene el suyo ("Usar el de las fotos" lo vuelve a copiar).
        editor.cargar_estado_panel(self.panel_ajustes.estado())
        editor.videoCambiado.connect(self._al_cambiar_video)
        editor.exportacionCambiada.connect(self._al_cambiar_exportacion_video)
        editor.progresoExportacion.connect(self.chip_video.establecer_progreso)
        editor.exportacionLista.connect(self._video_exportado)
        editor.boton_filtro_fotos.clicked.connect(self.copiar_filtro_a_video)
        editor.editarSonidoPedido.connect(self._editar_sonido_del_video)
        self.editor_video = editor
        return editor

    # ------------------------------------------------------------ ida y vuelta Video <-> Audio
    def _editar_sonido_del_video(self, ruta_wav: str, ruta_video: str) -> None:
        """"Editar el sonido en el modo Audio" (desde Video): el sonido completo del video, sin sus
        cortes, se abre en Audio con los cortes bloqueados, así sigue alineado con la imagen. Si no
        se abre (se eligió seguir con el audio que estaba), se vuelve a Video."""
        self.establecer_modo(AUDIO)
        if not self.editor_audio.abrir_desde_video(ruta_wav, ruta_video):
            self.establecer_modo(VIDEO)

    def _volver_al_video_con_sonido(self, ruta_wav: str, ruta_video: str) -> None:
        """"Volver al video con este sonido" (desde Audio): el WAV que exportó el modo Audio pasa a
        ser el sonido del video, alineado con el original (los cortes del video se le aplican)."""
        editor = self._asegurar_editor()
        abierto = editor.ruta
        if abierto is None or os.path.normcase(os.path.abspath(abierto)) != os.path.normcase(
                os.path.abspath(ruta_video)):
            self.aviso.mostrar(f"El video {Path(ruta_video).name} ya no está abierto en el modo Video.",
                               "Abrilo de nuevo y usá \"Cambiar el sonido por…\" con el audio exportado.\n"
                               + ruta_wav, icono="film", tipo="modo")
            return
        self.establecer_modo(VIDEO)
        if editor.usar_sonido_externo(ruta_wav, "original"):
            self.aviso.mostrar("Listo: el video usa el sonido que editaste en el modo Audio.",
                               "Para volver al sonido de siempre, tocá \"Volver al original\" en la tarjeta Sonido.",
                               icono="circle-check", tipo="modo")

    def _entrar_a_video(self) -> None:
        if self._modo == VIDEO:
            return
        editor = self._asegurar_editor()
        if self._modo == AUDIO:
            self._ocultar_audio()
            guardar_modo(self._modo_fotos)  # Video no se guarda: la próxima vez, el último de fotos
        self._modo = VIDEO
        # Primero se oculta lo de fotos: sus atajos (Ctrl+Z, Ctrl+O...) dejan de andar y quedan
        # los del editor de video.
        self._lateral_fotos.hide()
        self._pagina_fotos.hide()
        editor.lateral.show()
        editor.show()
        self.subtitulo_app.setText("Editor de video")
        self._mover_aviso(editor.vista)
        self._refrescar_presets_propios(editor.panel_ajustes)
        self._actualizar_selector()
        self._actualizar_chip()
        self._actualizar_titulo()
        editor.compactar()

    def _ocultar_video(self) -> None:
        """Oculta el editor de video sin cerrar nada: el video, sus cortes y una exportación en
        curso siguen ahí. Solo se pausa la reproducción."""
        editor = self.editor_video
        if editor is not None:
            editor.pausar()
            editor.hide()
            editor.lateral.hide()

    def _salir_de_video(self) -> None:
        self._ocultar_video()
        self._lateral_fotos.show()
        self._pagina_fotos.show()
        self.subtitulo_app.setText("Editor de fotos realistas")
        self._mover_aviso(self._tarjeta_vista_fotos)
        self._refrescar_presets_propios(self.panel_ajustes)

    def _mover_aviso(self, contenedor) -> None:
        """El aviso va a la vista del modo que se ve. Uno que explicaba un cambio de modo ("Esto es
        un video…") ya no sirve al volver a cambiar: se cierra. Los demás (la sesión, un video
        exportado) siguen a la vista."""
        if self.aviso.tipo == "modo":
            self.aviso.ocultar()
        self.aviso.mover_a(contenedor)

    @staticmethod
    def _refrescar_presets_propios(panel: PanelAjustes) -> None:
        """Un preset propio guardado (o borrado) en un modo también aparece (o se va) en el otro."""
        propios = set(presets_usuario.cargar())
        combo = panel.combo_preset
        en_combo = {combo.itemText(i) for i in range(combo.count())} - set(PRESETS) - {SIN_EFECTO, ""}
        if en_combo != propios:
            panel._refrescar_combos()

    def _actualizar_selector(self) -> None:
        for b in self.grupo_interfaz.buttons():
            b.setChecked(b.property("modo") == self._modo)
        if self._lite:
            return
        editor = self.editor_video
        hay_video = editor is not None and editor.info is not None
        self.boton_modo_video.establecer_punto(hay_video and self._modo != VIDEO)
        ayuda = self.boton_modo_video.property("ayuda")
        if hay_video:
            ayuda += f"\n\nAbierto: {Path(editor.ruta).name}"
        self.boton_modo_video.setToolTip(ayuda)
        # Audio: un punto si hay un audio abierto (o uno de la sesión que espera a que se entre).
        ruta_audio = self._ruta_audio()
        self.boton_modo_audio.establecer_punto(ruta_audio is not None and self._modo != AUDIO)
        ayuda = self.boton_modo_audio.property("ayuda")
        if ruta_audio is not None:
            ayuda += f"\n\nAbierto: {Path(ruta_audio).name}"
        self.boton_modo_audio.setToolTip(ayuda)

    def _ruta_audio(self) -> Optional[str]:
        """La voz abierta en el modo Audio (o la de la sesión, si todavía no se entró)."""
        if self.editor_audio is not None:
            return self.editor_audio.ruta
        if self._audio_pendiente is not None:
            return self._audio_pendiente.estado["proyecto"].ruta
        return None

    def _actualizar_chip(self) -> None:
        """El progreso de las exportaciones de video y de audio, junto al selector, mientras se está
        en otro modo."""
        if self._lite:
            return
        editor = self.editor_video
        self.chip_video.setVisible(editor is not None and editor.exportando and self._modo != VIDEO)
        self.chip_audio.setVisible(self.exportando_audio() and self._modo != AUDIO)

    def _actualizar_titulo(self) -> None:
        if self._modo == VIDEO:
            editor = self.editor_video
            nombre = Path(editor.ruta).name if editor is not None and editor.ruta else None
            self.setWindowTitle(f"{nombre} — {NOMBRE_APP} PRO · Video" if nombre else f"{NOMBRE_APP} PRO · Video")
        elif self._modo == AUDIO:
            ruta = self.editor_audio.ruta if self.editor_audio is not None else None
            nombre = Path(ruta).name if ruta else None
            self.setWindowTitle(f"{nombre} — {NOMBRE_APP} PRO · Audio" if nombre else f"{NOMBRE_APP} PRO · Audio")
        else:
            self.setWindowTitle(self._titulo_fotos)

    def _al_cambiar_video(self) -> None:
        self._actualizar_selector()
        self._actualizar_titulo()

    def _al_cambiar_exportacion_video(self, exportando: bool) -> None:
        if exportando:
            self.chip_video.reiniciar()
        self._actualizar_chip()

    def _video_exportado(self, texto: str, detalle: str) -> None:
        """Terminó de exportarse el video mientras se trabajaba en fotos: un aviso que no interrumpe."""
        self.aviso.mostrar(texto, detalle, icono="circle-check", segundos=20)

    def copiar_filtro_a_video(self) -> None:
        """"Usar el de las fotos": el video toma el preset, la intensidad, las capas y los ajustes
        de las fotos (sin zonas: en video las capas van a todo el cuadro)."""
        editor = self._asegurar_editor()
        editor.cargar_estado_panel(self.panel_ajustes.estado())
        editor.etiqueta_estado.setText("Listo: el video usa el mismo filtro que tus fotos.")

    def fuente_para_estilos(self) -> Optional[tuple]:
        """(clave, foto reducida, escala, transformación) de la foto que entra al filtro,
        para las miniaturas de la galería del modo fácil. None si no hay foto o si se
        está armando (después de girar, recortar, montar o borrar)."""
        if (self._imagen is None or self._vista_previa is None or self._fuentes_pendientes
                or self._transformacion is None or self._clave_vista_previa is None):
            return None
        return self._clave_vista_previa, self._vista_previa, self._escala_vista_previa, self._transformacion

    def _compactar_barra(self) -> None:
        """Ajusta la barra superior al ancho que hay, de a pasos, hasta que entre:

        0. todos los botones con su nombre;
        1. Medida, corta: solo la proporción ("9:16"), o solo el ícono si no hay una elegida;
        2. los modos de vista solo con el ícono (el nombre queda en la ayuda);
        3. Recortar, Enderezar y Medida también solo con el ícono;
        4. además, botones más angostos.

        Las barras de las herramientas (recorte, enderezar) acortan sus textos si no entran.
        En el modo fácil no está la columna derecha y hay menos botones.
        """
        if not hasattr(self, "barra_herramientas") or not hasattr(self, "boton_nivelar"):
            return
        if self._modo in (VIDEO, AUDIO):
            return  # la barra de fotos no se ve; se acomoda al volver (establecer_modo)
        derecha = 0 if self._modo == FACIL else 340
        disponible = self.width() - 372 - derecha - 28  # columna central, sin los márgenes
        modos = list(self.grupo_modo.buttons())
        herramientas = [b for b in (self.boton_recortar, self.boton_enderezar, self.boton_medida, self.boton_agregar_capa,
                                    self.boton_nuevo, self.boton_texto, self.boton_quitar_fondo,
                                    self.boton_video) if b is not None]
        medida_corta = " " + md.texto_boton(self._medida).split(" · ")[0] if self._medida is not None else ""
        for nivel in range(5):
            for b in modos:
                b.setText("" if nivel >= 2 else b.property("texto"))
            for b in herramientas:
                b.setText("" if nivel >= 3 else b.property("texto"))
            if nivel in (1, 2):
                self.boton_medida.setText(medida_corta)
            for b in self.barra_herramientas.findChildren(QPushButton, "botonSegmento"):
                if bool(b.property("compacto")) != (nivel >= 4):
                    b.setProperty("compacto", nivel >= 4)
                    b.style().unpolish(b)
                    b.style().polish(b)
            if self._ancho_barra() <= disponible:
                break
        corta = disponible - 32 < 680
        # La medida en la cabecera de la vista: sin el "Sale a" si no hay lugar (así no aprieta el zoom).
        if self._medida is not None:
            w, h = self._medida
            self.etiqueta_medida.setText(f"{w} × {h}" if corta else f"Sale a {w} × {h}")
        # Modo Photoshop: "Ver con el filtro" se acorta si la cabecera de la vista no tiene lugar.
        self.boton_ver_filtro.setText(" Con filtro" if disponible < 720 else " Ver con el filtro")
        for b in (self.boton_nivelar, self.boton_quitar_recorte):
            b.setText(b.property("corto" if corta else "texto"))
        self.etiqueta_angulo.setVisible(not corta)

    def _ancho_barra(self) -> int:
        """Ancho que pide la barra superior con los textos actuales.

        Se suma botón por botón: el tamaño que guardan los layouts recién se
        actualiza en el próximo ciclo de eventos. Lo oculto (en el modo fácil) no cuenta."""
        fila = self.barra_herramientas.layout()
        total, piezas = 0, 0
        for i in range(fila.count()):
            w = fila.itemAt(i).widget()
            if w is None or w.isHidden():
                continue
            piezas += 1
            if w.objectName() == "segmento":
                botones = [c for c in w.findChildren(QPushButton) if not c.isHidden()]
                margen = w.layout().contentsMargins()
                total += (sum(b.sizeHint().width() for b in botones) + margen.left() + margen.right() + 2
                          + w.layout().spacing() * max(0, len(botones) - 1))
            else:
                total += w.sizeHint().width()
        return total + fila.spacing() * max(0, piezas - 1)

    def resizeEvent(self, evento) -> None:
        self._compactar_barra()
        super().resizeEvent(evento)

    def _construir_barra_herramientas(self) -> QWidget:
        barra = QFrame()
        barra.setObjectName("barraHerramientas")
        self.barra_herramientas = barra
        fila = QHBoxLayout(barra)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(8)
        # Modo Photoshop: el menú (Archivo, Editar, Imagen, Capa, Ver), al principio de la barra.
        fila.addWidget(self.photoshop.construir_menu())

        self.boton_abrir = QPushButton(" Abrir")
        self.boton_abrir.setIcon(iconos.icono(iconos.ABRIR, 18, color="#ffffff"))
        self.boton_abrir.setIconSize(QSize(18, 18))
        self.boton_abrir.setObjectName("botonPrimario")
        if self._lite:
            self.boton_abrir.setToolTip("Abrir fotos (Ctrl+O). También podés arrastrarlas a la vista.")
        else:
            self.boton_abrir.setToolTip("Abrir fotos o un video (Ctrl+O). También podés arrastrarlos a la vista: "
                                        "los videos se abren en el modo Video.")
        self.boton_abrir.setCursor(Qt.PointingHandCursor)
        self.boton_abrir.clicked.connect(self.elegir_archivo)
        fila.addWidget(self.boton_abrir)

        # Proyecto con capas (.nslite): guardar (Ctrl+S), guardar como y abrir.
        self.boton_proyecto = QPushButton()
        self.boton_proyecto.setIcon(iconos.icono("save", 17))
        self.boton_proyecto.setIconSize(QSize(17, 17))
        self.boton_proyecto.setToolTip("Proyecto: guardá la foto con sus capas y su edición para seguir después "
                                       "(.nslite, Ctrl+S). Exportar (Ctrl+Shift+E) arma la imagen final.")
        menu = QMenu(self.boton_proyecto)
        menu.addAction(iconos.icono("save", 15), "Guardar proyecto\tCtrl+S", self.guardar_proyecto)
        menu.addAction(iconos.icono("save", 15), "Guardar proyecto como…\tCtrl+Shift+S", self.guardar_proyecto_como)
        menu.addSeparator()
        menu.addAction(iconos.icono(iconos.ABRIR, 15), "Abrir proyecto…", self.elegir_proyecto)
        self.boton_proyecto.setMenu(menu)
        self.boton_proyecto.setProperty("texto", "")
        fila.addWidget(self._segmento([self.boton_proyecto]))

        self.boton_deshacer = QPushButton()
        self.boton_deshacer.setIcon(iconos.icono("undo-2"))
        self.boton_deshacer.setToolTip("Deshacer (Ctrl+Z)")
        self.boton_deshacer.clicked.connect(self.deshacer)
        self.boton_rehacer = QPushButton()
        self.boton_rehacer.setIcon(iconos.icono("redo-2"))
        self.boton_rehacer.setToolTip("Rehacer (Ctrl+Y)")
        self.boton_rehacer.clicked.connect(self.rehacer)
        fila.addWidget(self._segmento([self.boton_deshacer, self.boton_rehacer]))

        self.grupo_modo = QButtonGroup(self)
        self.grupo_modo.setExclusive(True)
        botones_modo = []
        for texto, modo, icono, ayuda in (
            ("Dividir", VistaComparacion.MODO_DIVIDIR, "square-split-horizontal", "Comparación con divisor arrastrable"),
            ("Antes", VistaComparacion.MODO_ANTES, "image", "Foto original"),
            ("Después", VistaComparacion.MODO_DESPUES, "wand-sparkles", "Resultado"),
            ("Lado a lado", VistaComparacion.MODO_LADO, "columns-2",
             "Antes y después uno al lado del otro, con el mismo zoom y desplazamiento"),
        ):
            boton = QPushButton(texto)
            boton.setIcon(iconos.icono(icono, 15))
            boton.setIconSize(QSize(15, 15))
            boton.setCheckable(True)
            boton.setToolTip(ayuda + ". Mantené la barra espaciadora para ver el original.")
            boton.setProperty("modo", modo)
            boton.setProperty("texto", texto)
            boton.setChecked(modo == VistaComparacion.MODO_DIVIDIR)
            self.grupo_modo.addButton(boton)
            botones_modo.append(boton)
        self.grupo_modo.buttonClicked.connect(lambda b: self.vista.establecer_modo(b.property("modo")))
        fila.addWidget(self._segmento(botones_modo))

        self.boton_recortar = QPushButton(" Recortar")
        self.boton_recortar.setIcon(iconos.icono("crop", 16))
        self.boton_recortar.setCheckable(True)
        self.boton_recortar.setToolTip("Recortar la foto (no destructivo: se puede cambiar o quitar después)")
        self.boton_recortar.toggled.connect(self._alternar_recorte)
        self.boton_recortar.setProperty("texto", " Recortar")
        self.boton_enderezar = QPushButton(" Enderezar")
        self.boton_enderezar.setIcon(iconos.icono("ruler", 16))
        self.boton_enderezar.setCheckable(True)
        self.boton_enderezar.setToolTip("Enderezar la foto: girarla de a poco (hasta 15°) o nivelarla sola con "
                                        "el horizonte. Recorta las esquinas que quedarían vacías.")
        self.boton_enderezar.toggled.connect(self._alternar_enderezar)
        self.boton_enderezar.setProperty("texto", " Enderezar")
        self._segmento_recorte = self._segmento([self.boton_recortar, self.boton_enderezar])
        fila.addWidget(self._segmento_recorte)
        # Medida de salida: un clic abre el menú (celular, PC y redes); el botón dice la elegida.
        self.boton_medida = QPushButton(" Medida")
        self.boton_medida.setIcon(iconos.icono("ratio", 16))
        self.boton_medida.setProperty("texto", " Medida")
        self.boton_medida.setProperty("activo", False)
        self.boton_medida.clicked.connect(self._abrir_menu_medida)
        self.menu_medida = MenuMedida(self)
        self.menu_medida.medidaElegida.connect(self.elegir_medida)
        self._segmento_medida = self._segmento([self.boton_medida])
        fila.addWidget(self._segmento_medida)
        # Modo Photoshop: agregar una imagen como capa.
        self.boton_agregar_capa = QPushButton(" Agregar imagen")
        self.boton_agregar_capa.setIcon(iconos.icono("image-plus", 16))
        self.boton_agregar_capa.setToolTip("Agregar imagen como capa… (PNG con transparencia, JPG, WEBP…). También "
                                           "podés soltarla sobre la foto.")
        self.boton_agregar_capa.setProperty("texto", " Agregar imagen")
        self.boton_agregar_capa.clicked.connect(self.elegir_imagen_capa)
        # Kit para flyers (modo Photoshop): nuevo lienzo, texto, quitar fondo y recortar.
        self.boton_nuevo = QPushButton(" Nuevo")
        self.boton_nuevo.setIcon(iconos.icono("file-plus", 16))
        self.boton_nuevo.setToolTip("Nuevo documento (Ctrl+N): post, historia, A4, carta, portada, banner o a medida, "
                                    "con fondo de color, transparente o degradado. Entra a la tira como una foto más.")
        self.boton_nuevo.setProperty("texto", " Nuevo")
        self.boton_nuevo.clicked.connect(lambda: self.nuevo_lienzo())
        self.boton_texto = QPushButton(" Texto")
        self.boton_texto.setIcon(iconos.icono("type", 16))
        self.boton_texto.setToolTip("Texto (T): clic en la imagen para escribir, o arrastrá para una caja. "
                                    "Fuente, tamaño y color en la barra de opciones; doble clic sobre un texto "
                                    "para editarlo.")
        self.boton_texto.setProperty("texto", " Texto")
        self.boton_texto.clicked.connect(lambda: self.agregar_texto())
        self.boton_quitar_fondo = QPushButton(" Quitar fondo")
        self.boton_quitar_fondo.setIcon(iconos.icono("scissors", 16))
        self.boton_quitar_fondo.setToolTip("Quitar el fondo de la capa elegida (automático). Si es la Foto, "
                                           "el objeto recortado va a una capa nueva y la foto se oculta.")
        self.boton_quitar_fondo.setProperty("texto", " Quitar fondo")
        self.boton_quitar_fondo.clicked.connect(self.quitar_fondo_capa)
        self.boton_recortar_ps = QPushButton()
        self.boton_recortar_ps.setIcon(iconos.icono("crop", 16))
        self.boton_recortar_ps.setToolTip("Recortar (C): un recuadro con manijas sobre la imagen, acá mismo; Enter "
                                          "aplica y Esc cancela. En una foto, el recorte no destructivo de siempre "
                                          "(las capas siguen a la foto).")
        self.boton_recortar_ps.setProperty("texto", "")
        self.boton_recortar_ps.clicked.connect(self.recortar_desde_photoshop)
        self._segmento_capa = self._segmento([self.boton_nuevo, self.boton_agregar_capa, self.boton_texto,
                                              self.boton_quitar_fondo, self.boton_recortar_ps])
        fila.addWidget(self._segmento_capa)
        self._segmento_capa.hide()

        # Girar y voltear: un clic, un paso del historial. Las zonas y el recorte giran con la foto.
        self.botones_geometria = []
        for icono, ayuda, accion in (
            ("rotate-ccw-square", "Girar 90° a la izquierda", lambda: self.girar(-1)),
            ("rotate-cw-square", "Girar 90° a la derecha", lambda: self.girar(1)),
            ("flip-horizontal-2", "Voltear horizontal (espejo izquierda-derecha)", lambda: self.voltear(True)),
            ("flip-vertical-2", "Voltear vertical (espejo arriba-abajo)", lambda: self.voltear(False)),
        ):
            b = QPushButton()
            b.setIcon(iconos.icono(icono, 16))
            b.setToolTip(ayuda + ". No destructivo: las zonas marcadas y el recorte siguen a la foto.")
            b.clicked.connect(accion)
            self.botones_geometria.append(b)
        fila.addWidget(self._segmento(self.botones_geometria))

        self.boton_video = None  # en la Lite no hay modo Video
        if not self._lite:
            self.boton_video = QPushButton(" Video")
            self.boton_video.setIcon(iconos.icono("film", 16))
            self.boton_video.setToolTip("Ir al modo Video: editar un video con el mismo filtro (cortar, borrar partes "
                                        "y exportar en MP4 con sonido), en esta misma ventana (Ctrl+Shift+V)")
            self.boton_video.setProperty("texto", " Video")
            self.boton_video.clicked.connect(lambda: self.establecer_modo(VIDEO))
            fila.addWidget(self._segmento([self.boton_video]))
        fila.addStretch(1)

        # Zoom: se ubica en la cabecera de la vista previa.
        self.boton_alejar = QPushButton()
        self.boton_alejar.setIcon(iconos.icono("minus", 15))
        self.boton_alejar.setToolTip("Alejar (Ctrl+−)")
        self.boton_acercar = QPushButton()
        self.boton_acercar.setIcon(iconos.icono("plus", 15))
        self.boton_acercar.setToolTip("Acercar (Ctrl++)")
        self.boton_ajustar = QPushButton()
        self.boton_ajustar.setIcon(iconos.icono("maximize", 15))
        self.boton_ajustar.setToolTip("Ver la foto completa (Ctrl+0)")
        self.boton_100 = QPushButton("100%")
        self.boton_100.setToolTip("Tamaño real, para revisar detalles (Ctrl+1)")
        self.boton_200 = QPushButton("200%")
        self.boton_200.setToolTip("Al doble, para revisar ruido, grano y bordes píxel por píxel (Ctrl+2)")
        self.etiqueta_zoom = QLabel("—")
        self.etiqueta_zoom.setObjectName("etiquetaZoom")
        self.etiqueta_zoom.setMinimumWidth(50)
        self.etiqueta_zoom.setAlignment(Qt.AlignCenter)
        for b in barra.findChildren(QPushButton):
            b.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        return barra

    def _construir_tarjeta_vista(self) -> QWidget:
        tarjeta = QFrame()
        tarjeta.setObjectName("tarjetaVista")
        self._tarjeta_vista_fotos = tarjeta
        capa = QVBoxLayout(tarjeta)
        capa.setContentsMargins(16, 12, 16, 16)
        capa.setSpacing(10)

        encabezado = QHBoxLayout()
        encabezado.setSpacing(8)
        punto = QLabel("●")  # punto de estado como en las tarjetas del CRM
        punto.setObjectName("puntoEstado")
        titulo = QLabel("Vista previa")
        titulo.setObjectName("tituloTarjeta")
        self.etiqueta_estado = EtiquetaElidida("Abrí una foto para empezar.")  # si no entra, termina en "…"
        self.etiqueta_estado.setObjectName("estadoImagen")
        self.etiqueta_estado.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.barra_progreso = QProgressBar()
        self.barra_progreso.setRange(0, 0)
        # Se achica si hace falta: en pantallas angostas no aprieta los botones de zoom.
        self.barra_progreso.setMinimumWidth(30)
        self.barra_progreso.setMaximumWidth(110)
        self.barra_progreso.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.barra_progreso.setTextVisible(False)
        self.barra_progreso.hide()
        encabezado.addWidget(punto)
        encabezado.addWidget(titulo)
        encabezado.addSpacing(10)
        # El estado puede recortarse; el nombre y tamaño completos están en el pie izquierdo.
        self.etiqueta_estado.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        encabezado.addWidget(self.etiqueta_estado, 1)
        # Con una Medida elegida: a qué tamaño sale la foto al exportarla.
        self.etiqueta_medida = QLabel()
        self.etiqueta_medida.setObjectName("pastillaMedida")
        self.etiqueta_medida.hide()
        encabezado.addWidget(self.etiqueta_medida)
        encabezado.addWidget(self.barra_progreso)
        encabezado.addSpacing(6)
        self.boton_zonas = QPushButton()
        self.boton_zonas.setIcon(iconos.icono("square-dashed", 15))
        self.boton_zonas.setCheckable(True)
        self.boton_zonas.setChecked(True)
        self.boton_zonas.setToolTip("Mostrar u ocultar el contorno de las zonas de los "
                                    + ("efectos" if self._lite else "capas"))
        self.boton_zonas.toggled.connect(lambda _v: self._actualizar_superposiciones())
        self._segmento_zonas = self._segmento([self.boton_zonas])
        encabezado.addWidget(self._segmento_zonas)
        # Modo Photoshop: la vista va sin el filtro; esto lo muestra un momento (no cambia nada).
        self.boton_ver_filtro = QPushButton(" Ver con el filtro")
        self.boton_ver_filtro.setIcon(iconos.icono(iconos.CELULAR, 15))
        self.boton_ver_filtro.setCheckable(True)
        self.boton_ver_filtro.setToolTip("Previsualizar la foto con el filtro celular natural (el que elegiste en "
                                         "Fácil o Editor). Las capas se editan sin el filtro.")
        self.boton_ver_filtro.toggled.connect(lambda _v: self.solicitar_render())
        self._segmento_ver_filtro = self._segmento([self.boton_ver_filtro])
        encabezado.addWidget(self._segmento_ver_filtro)
        self._segmento_ver_filtro.hide()
        encabezado.addWidget(self._segmento([self.boton_alejar, self.etiqueta_zoom, self.boton_acercar]))
        encabezado.addWidget(self._segmento([self.boton_ajustar, self.boton_100, self.boton_200]))
        capa.addLayout(encabezado)
        # Modo Photoshop: la barra de opciones de la herramienta (cambia con la herramienta).
        capa.addWidget(self.photoshop.construir_opciones())

        # Barra del recorte (visible solo mientras se recorta)
        self.barra_recorte = QFrame()
        self.barra_recorte.setObjectName("barraRecorte")
        fila_rec = QHBoxLayout(self.barra_recorte)
        fila_rec.setContentsMargins(10, 6, 10, 6)
        fila_rec.setSpacing(8)
        icono_rec = QLabel()
        icono_rec.setPixmap(iconos.pixmap("crop", 16))
        texto_rec = QLabel("Arrastrá sobre la foto para elegir qué parte queda.")
        texto_rec.setObjectName("nota")
        texto_rec.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.combo_aspecto = QComboBox()
        for texto, valor in (("Libre", None), ("Original", "original"), ("1:1 cuadrado", 1.0),
                             ("4:5 Instagram", 4 / 5), ("3:4 celular", 3 / 4), ("9:16 historia", 9 / 16),
                             ("4:3", 4 / 3), ("16:9", 16 / 9)):
            self.combo_aspecto.addItem(texto, valor)
        self.combo_aspecto.setToolTip("Proporción del recorte")
        self.combo_aspecto.currentIndexChanged.connect(lambda _i: self.vista.establecer_aspecto(self._aspecto()))
        boton_aplicar = QPushButton(" Aplicar")
        boton_aplicar.setObjectName("botonPrimario")
        boton_aplicar.setIcon(iconos.icono("check", 16, color="#ffffff"))
        boton_aplicar.clicked.connect(lambda: self._salir_recorte("aplicar"))
        self.boton_quitar_recorte = QPushButton("Quitar recorte")
        self.boton_quitar_recorte.setProperty("texto", "Quitar recorte")
        self.boton_quitar_recorte.setProperty("corto", "Quitar")
        self.boton_quitar_recorte.setToolTip("Volver a la foto completa")
        self.boton_quitar_recorte.clicked.connect(lambda: self._salir_recorte("quitar"))
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.clicked.connect(lambda: self._salir_recorte("cancelar"))
        fila_rec.addWidget(icono_rec)
        fila_rec.addWidget(texto_rec, 1)
        fila_rec.addWidget(self.combo_aspecto)
        fila_rec.addWidget(self.boton_quitar_recorte)
        fila_rec.addWidget(boton_cancelar)
        fila_rec.addWidget(boton_aplicar)
        self.barra_recorte.hide()
        capa.addWidget(self.barra_recorte)

        # Barra de enderezar (visible solo mientras se endereza). Como la del pincel,
        # sus botones no toman el foco: Enter y Esc siguen yendo a la foto.
        self.barra_enderezar = QFrame()
        self.barra_enderezar.setObjectName("barraRecorte")
        fila_end = QHBoxLayout(self.barra_enderezar)
        fila_end.setContentsMargins(10, 6, 10, 6)
        fila_end.setSpacing(8)
        icono_end = QLabel()
        icono_end.setPixmap(iconos.pixmap("ruler", 16))
        self.etiqueta_angulo = etiqueta_angulo = QLabel("Ángulo")
        etiqueta_angulo.setObjectName("etiquetaControl")
        self.slider_angulo = QSlider(Qt.Horizontal)
        self.slider_angulo.setRange(-150, 150)  # décimas de grado
        self.slider_angulo.setPageStep(10)
        self.slider_angulo.setFocusPolicy(Qt.NoFocus)
        self.slider_angulo.setMinimumWidth(80)
        self.slider_angulo.setToolTip("Girá la foto de a poco hasta que el horizonte o las líneas verticales "
                                      "queden derechos. Hacia la derecha gira en el sentido del reloj.")
        self.numero_angulo = QDoubleSpinBox()
        self.numero_angulo.setObjectName("valorControl")
        self.numero_angulo.setRange(-15.0, 15.0)
        self.numero_angulo.setDecimals(1)
        self.numero_angulo.setSingleStep(0.1)
        self.numero_angulo.setSuffix("°")
        self.numero_angulo.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.numero_angulo.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.numero_angulo.setFixedWidth(58)
        self.numero_angulo.setToolTip("Escribí un ángulo exacto (−15° a 15°)")
        self.slider_angulo.valueChanged.connect(self._al_mover_angulo)
        self.numero_angulo.valueChanged.connect(lambda v: self.slider_angulo.setValue(round(v * 10)))
        self.boton_nivelar = QPushButton(" Nivelar automático")
        self.boton_nivelar.setIcon(iconos.icono("scan-line", 16))
        self.boton_nivelar.setProperty("texto", " Nivelar automático")
        self.boton_nivelar.setProperty("corto", " Nivelar")
        self.boton_nivelar.setFocusPolicy(Qt.NoFocus)
        self.boton_nivelar.setToolTip("Busca el horizonte y las líneas rectas de la foto y la endereza sola")
        self.boton_nivelar.clicked.connect(self.nivelar_automatico)
        self.boton_cuadricula = QPushButton()
        self.boton_cuadricula.setIcon(iconos.icono("grid-3x3", 16))
        self.boton_cuadricula.setCheckable(True)
        self.boton_cuadricula.setChecked(True)
        self.boton_cuadricula.setFocusPolicy(Qt.NoFocus)
        self.boton_cuadricula.setFixedWidth(40)
        self.boton_cuadricula.setToolTip("Mostrar u ocultar la cuadrícula de guía")
        self.boton_cuadricula.toggled.connect(lambda v: self.vista.establecer_cuadricula(v))
        boton_cancelar_end = QPushButton("Cancelar")
        boton_cancelar_end.setFocusPolicy(Qt.NoFocus)
        boton_cancelar_end.setToolTip("Dejar la foto como estaba (Esc)")
        boton_cancelar_end.clicked.connect(lambda: self._salir_enderezar("cancelar"))
        boton_aplicar_end = QPushButton(" Aplicar")
        boton_aplicar_end.setObjectName("botonPrimario")
        boton_aplicar_end.setIcon(iconos.icono("check", 16, color="#ffffff"))
        boton_aplicar_end.setFocusPolicy(Qt.NoFocus)
        boton_aplicar_end.setToolTip("Enderezar (Enter). Se puede cambiar o quitar después.")
        boton_aplicar_end.clicked.connect(lambda: self._salir_enderezar("aplicar"))
        fila_end.addWidget(icono_end)
        fila_end.addWidget(etiqueta_angulo)
        fila_end.addWidget(self.slider_angulo, 1)
        fila_end.addWidget(self.numero_angulo)
        fila_end.addWidget(self.boton_nivelar)
        fila_end.addWidget(self.boton_cuadricula)
        fila_end.addWidget(boton_cancelar_end)
        fila_end.addWidget(boton_aplicar_end)
        self.barra_enderezar.hide()
        capa.addWidget(self.barra_enderezar)

        # Barra del clonado (visible mientras se elige de dónde copiar).
        self.barra_clon = QFrame()
        self.barra_clon.setObjectName("barraRecorte")
        fila_clon = QHBoxLayout(self.barra_clon)
        fila_clon.setContentsMargins(10, 6, 10, 6)
        fila_clon.setSpacing(8)
        icono_clon = QLabel()
        icono_clon.setPixmap(iconos.pixmap("stamp", 16))
        self.texto_clon = QLabel("Arrastrá desde la zona hasta lo que querés copiar.")
        self.texto_clon.setObjectName("nota")
        self.texto_clon.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.check_costuras = QCheckBox("Fundir luz y color")
        self.check_costuras.setChecked(True)
        self.check_costuras.setFocusPolicy(Qt.NoFocus)
        self.check_costuras.setToolTip("Toma la textura de la fuente pero empareja la luz y el color con el borde "
                                       "de la zona, para que no se note el parche")
        boton_cancelar_clon = QPushButton("Cancelar")
        boton_cancelar_clon.setFocusPolicy(Qt.NoFocus)
        boton_cancelar_clon.setToolTip("No clonar (Esc)")
        boton_cancelar_clon.clicked.connect(self.cancelar_herramienta)
        boton_listo_clon = QPushButton(" Listo")
        boton_listo_clon.setObjectName("botonPrimario")
        boton_listo_clon.setIcon(iconos.icono("check", 16, color="#ffffff"))
        boton_listo_clon.setFocusPolicy(Qt.NoFocus)
        boton_listo_clon.setToolTip("Clonar desde la fuente elegida (Enter)")
        boton_listo_clon.clicked.connect(self._clon_listo)
        fila_clon.addWidget(icono_clon)
        fila_clon.addWidget(self.texto_clon, 1)
        fila_clon.addWidget(self.check_costuras)
        fila_clon.addWidget(boton_cancelar_clon)
        fila_clon.addWidget(boton_listo_clon)
        self.barra_clon.hide()
        capa.addWidget(self.barra_clon)

        # Barra de Mover / Transformar (visible mientras se transforma una capa). Sus botones no
        # toman el foco: Enter, Esc y las flechas siguen yendo a la foto.
        self.barra_transformar = QFrame()
        self.barra_transformar.setObjectName("barraRecorte")
        fila_tr = QHBoxLayout(self.barra_transformar)
        fila_tr.setContentsMargins(10, 6, 10, 6)
        fila_tr.setSpacing(8)
        icono_tr = QLabel()
        icono_tr.setPixmap(iconos.pixmap("move", 16))
        self.texto_transformar = QLabel("")
        self.texto_transformar.setObjectName("nota")
        self.texto_transformar.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        boton_voltear_capa = QPushButton(" Voltear")
        boton_voltear_capa.setIcon(iconos.icono("flip-horizontal-2", 16))
        boton_voltear_capa.setFocusPolicy(Qt.NoFocus)
        boton_voltear_capa.setToolTip("Voltear la capa horizontal (espejo)")
        boton_voltear_capa.clicked.connect(lambda: self.voltear_capa())
        boton_voltear_v = QPushButton()
        boton_voltear_v.setIcon(iconos.icono("flip-vertical-2", 16))
        boton_voltear_v.setFocusPolicy(Qt.NoFocus)
        boton_voltear_v.setToolTip("Voltear la capa vertical (arriba ↔ abajo)")
        boton_voltear_v.clicked.connect(lambda: self.voltear_capa(vertical=True))
        boton_cancelar_tr = QPushButton("Cancelar")
        boton_cancelar_tr.setFocusPolicy(Qt.NoFocus)
        boton_cancelar_tr.setToolTip("Dejar la capa como estaba (Esc)")
        boton_cancelar_tr.clicked.connect(lambda: self._salir_transformar("cancelar"))
        boton_aplicar_tr = QPushButton(" Aplicar")
        boton_aplicar_tr.setObjectName("botonPrimario")
        boton_aplicar_tr.setIcon(iconos.icono("check", 16, color="#ffffff"))
        boton_aplicar_tr.setFocusPolicy(Qt.NoFocus)
        boton_aplicar_tr.setToolTip("Aplicar la transformación (Enter): queda como un paso del historial")
        boton_aplicar_tr.clicked.connect(lambda: self._salir_transformar("aplicar"))
        fila_tr.addWidget(icono_tr)
        fila_tr.addWidget(self.texto_transformar, 1)
        fila_tr.addWidget(boton_voltear_capa)
        fila_tr.addWidget(boton_voltear_v)
        fila_tr.addWidget(boton_cancelar_tr)
        fila_tr.addWidget(boton_aplicar_tr)
        self.barra_transformar.hide()
        capa.addWidget(self.barra_transformar)

        # Barra del pincel (visible solo mientras se pinta una zona). Sus controles
        # no toman el foco: así Enter, Esc, E y [ ] siguen yendo a la foto.
        self.barra_pincel = QFrame()
        self.barra_pincel.setObjectName("barraPincel")
        fila_pin = QHBoxLayout(self.barra_pincel)
        fila_pin.setContentsMargins(10, 6, 10, 6)
        fila_pin.setSpacing(8)
        icono_pin = QLabel()
        icono_pin.setPixmap(iconos.pixmap("brush", 16))
        fila_pin.addWidget(icono_pin)
        self.sliders_pincel = {}
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
            slider.setMinimumWidth(60)
            slider.setMaximumWidth(130)
            slider.setToolTip(ayuda)
            slider.valueChanged.connect(lambda v, c=clave: self.vista.establecer_pincel(**{c: v}))
            self.sliders_pincel[clave] = slider
            fila_pin.addWidget(etiqueta)
            fila_pin.addWidget(slider, 1)
        self.boton_goma = QPushButton(" Goma")
        self.boton_goma.setIcon(iconos.icono("eraser", 16))
        self.boton_goma.setCheckable(True)
        self.boton_goma.setFocusPolicy(Qt.NoFocus)
        self.boton_goma.setToolTip("Borrar lo pintado de más (tecla E). También podés borrar con el clic derecho.")
        self.boton_goma.toggled.connect(lambda v: self.vista.establecer_pincel(goma=v))
        fila_pin.addWidget(self.boton_goma)
        fila_pin.addStretch(1)
        boton_cancelar_pin = QPushButton("Cancelar")
        boton_cancelar_pin.setFocusPolicy(Qt.NoFocus)
        boton_cancelar_pin.setToolTip("Descartar lo pintado ahora y volver a la zona anterior (Esc)")
        boton_cancelar_pin.clicked.connect(self.cancelar_herramienta)
        self.boton_listo_pincel = QPushButton(" Listo")
        self.boton_listo_pincel.setObjectName("botonPrimario")
        self.boton_listo_pincel.setIcon(iconos.icono("check", 16, color="#ffffff"))
        self.boton_listo_pincel.setFocusPolicy(Qt.NoFocus)
        self.boton_listo_pincel.setToolTip("Terminar de pintar (Enter)")
        self.boton_listo_pincel.clicked.connect(lambda: self.vista.terminar_pincel())
        fila_pin.addWidget(boton_cancelar_pin)
        fila_pin.addWidget(self.boton_listo_pincel)
        self.barra_pincel.hide()
        capa.addWidget(self.barra_pincel)

        self.vista = VistaComparacion()
        # Fotos a la tira, un video al modo Video; en el modo Photoshop, las imágenes van como capas.
        self.vista.archivosSoltados.connect(self._soltado_en_vista)
        self.vista.clicSinImagen.connect(self.elegir_archivo)
        self.vista.seleccionTerminada.connect(self._seleccion_terminada)
        self.vista.seleccionCancelada.connect(self.cancelar_herramienta)
        self.vista.formaTerminada.connect(self._forma_terminada)
        self.vista.trazosTerminados.connect(self._trazos_terminados)
        self.vista.pincelCambiado.connect(self._sincronizar_pincel)
        self.vista.confirmado.connect(self._confirmar_herramienta)
        self.vista.clonCambiado.connect(lambda _dx, _dy: self._texto_clon_elegido())
        self.vista.zoomCambiado.connect(lambda z: self.etiqueta_zoom.setText(f"{z * 100:.0f} %"))
        self.vista.transformacionCambiada.connect(self._al_transformar)
        self.vista.imagenesComoCapa.connect(self.agregar_imagenes_como_capa)
        self.boton_alejar.clicked.connect(self.vista.alejar)
        self.boton_acercar.clicked.connect(self.vista.acercar)
        self.boton_ajustar.clicked.connect(self.vista.ajustar)
        self.boton_100.clicked.connect(lambda: self.vista.fijar_zoom(1.0))
        self.boton_200.clicked.connect(lambda: self.vista.fijar_zoom(2.0))
        capa.addWidget(self.vista, 1)
        # Avisos discretos que flotan abajo de la foto (por ejemplo, fotos de la sesión que ya no están,
        # o "Esto es un video: lo abrimos en el modo Video"). En Video pasa a la vista del video.
        self.aviso = AvisoFlotante(tarjeta)
        return tarjeta

    def _construir_exportacion(self) -> QWidget:
        caja = QWidget()
        capa = QVBoxLayout(caja)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(8)
        titulo = QLabel("EXPORTAR")
        titulo.setObjectName("tituloSeccion")
        capa.addWidget(titulo)

        # Selector de formato: dos opciones grandes lado a lado.
        selector = QFrame()
        selector.setObjectName("selectorFormato")
        fila_formato = QHBoxLayout(selector)
        fila_formato.setContentsMargins(3, 3, 3, 3)
        fila_formato.setSpacing(3)
        self.grupo_formato = QButtonGroup(self)
        self.grupo_formato.setExclusive(True)
        for formato, texto, icono, ayuda in (
            ("PNG", "PNG\nSin pérdida", "images", "Máxima calidad: no comprime con pérdida. Archivo más pesado."),
            ("JPEG", "JPEG\nMás liviano", "file-archive", "Archivo más liviano, con la calidad que elijas."),
        ):
            b = QPushButton(texto)
            b.setObjectName("opcionFormato")
            b.setCheckable(True)
            b.setChecked(formato == "PNG")
            b.setProperty("formato", formato)
            b.setIcon(iconos.icono(icono, 20))
            b.setIconSize(QSize(20, 20))
            b.setToolTip(ayuda)
            b.setCursor(Qt.PointingHandCursor)
            self.grupo_formato.addButton(b)
            fila_formato.addWidget(b, 1)
        self.grupo_formato.buttonClicked.connect(lambda _b: self._al_cambiar_formato())
        capa.addWidget(selector)

        self.caja_calidad = QWidget()
        capa_calidad = QVBoxLayout(self.caja_calidad)
        capa_calidad.setContentsMargins(0, 2, 0, 0)
        capa_calidad.setSpacing(4)
        fila = QHBoxLayout()
        self.etiqueta_calidad = QLabel("Calidad JPEG")
        self.valor_calidad = QLabel("92")
        self.valor_calidad.setObjectName("valorControl")
        fila.addWidget(self.etiqueta_calidad, 1)
        fila.addWidget(self.valor_calidad)
        capa_calidad.addLayout(fila)
        self.slider_calidad = QSlider(Qt.Horizontal)
        self.slider_calidad.setRange(60, 100)
        self.slider_calidad.setValue(92)
        self.slider_calidad.valueChanged.connect(lambda v: self.valor_calidad.setText(str(v)))
        capa_calidad.addWidget(self.slider_calidad)
        capa.addWidget(self.caja_calidad)

        self.check_exif = QCheckBox("Conservar metadatos EXIF")
        self.check_exif.setToolTip("Copia fecha, cámara y demás datos del archivo original (con la orientación corregida).")
        capa.addWidget(self.check_exif)

        self.boton_exportar = QPushButton("  Exportar como archivo nuevo…")
        self.boton_exportar.setIcon(iconos.icono(iconos.GUARDAR, color="#ffffff"))
        self.boton_exportar.setIconSize(QSize(20, 20))
        self.boton_exportar.setObjectName("botonPrimario")
        if self._lite:
            self.boton_exportar.setToolTip("Guarda la imagen final (todas las capas, con el filtro) como un archivo "
                                           "nuevo, con las mismas dimensiones (Ctrl+Shift+E). El original no se "
                                           "modifica. Para seguir editando después, guardá el proyecto (Ctrl+S).")
        else:
            self.boton_exportar.setToolTip("Guarda un archivo nuevo con las mismas dimensiones (Ctrl+S). El original no se modifica.")
        self.boton_exportar.clicked.connect(self.exportar)
        capa.addWidget(self.boton_exportar)

        self.boton_lote = QPushButton("  Procesar varias fotos…")
        self.boton_lote.setIcon(iconos.icono("images"))
        self.boton_lote.setIconSize(QSize(18, 18))
        self.boton_lote.setToolTip("Aplica los ajustes actuales (con " + ("efectos" if self._lite else "capas")
                                   + ") a muchas fotos y guarda archivos nuevos. Las fotos de la tira con una "
                                   "Medida salen con su encuadre y en esa medida.")
        self.boton_lote.clicked.connect(self.procesar_varias)
        capa.addWidget(self.boton_lote)

        caja.setToolTip("El original nunca se sobrescribe. Se conservan las dimensiones y el perfil de color.")
        self._al_cambiar_formato()
        return caja

    def _construir_acciones(self) -> None:
        # Los atajos de las fotos van en la página de fotos: en el modo Video no se ven y no
        # chocan con los del editor de video (Ctrl+Z, Ctrl+O, Ctrl+S, zoom...), que van en la suya.
        fotos = self._pagina_fotos
        esc = QAction(fotos)
        esc.setShortcut(QKeySequence(Qt.Key_Escape))
        esc.triggered.connect(self.cancelar_herramienta)
        fotos.addAction(esc)
        if self._lite:
            # Ctrl+S guarda el proyecto con sus capas (.nslite); exportar la imagen final es Ctrl+Shift+E.
            # Las herramientas y el menú del modo Photoshop (cada una no hace nada fuera de ese modo).
            ps = self.photoshop

            def solo_ps(funcion):
                return lambda: funcion() if self._modo == PHOTOSHOP else None

            propios = ((QKeySequence.Save, self.guardar_proyecto),
                       (QKeySequence("Ctrl+Shift+S"), self.guardar_proyecto_como),
                       (QKeySequence("Ctrl+Shift+E"), self.exportar),
                       (QKeySequence.New, lambda: self.nuevo_lienzo()),
                       (QKeySequence(Qt.Key_V), lambda: ps.tecla_herramienta("V")),
                       (QKeySequence(Qt.Key_H), lambda: ps.tecla_herramienta("H")),
                       (QKeySequence(Qt.Key_Z), lambda: ps.tecla_herramienta("Z")),
                       (QKeySequence(Qt.Key_I), lambda: ps.tecla_herramienta("I")),
                       (QKeySequence(Qt.Key_T), lambda: ps.tecla_herramienta("T")),
                       (QKeySequence(Qt.Key_U), lambda: ps.tecla_herramienta("U")),
                       (QKeySequence(Qt.Key_B), lambda: ps.tecla_herramienta("B")),
                       (QKeySequence(Qt.Key_E), lambda: ps.tecla_herramienta("E")),
                       (QKeySequence(Qt.Key_G), lambda: ps.tecla_herramienta("G")),
                       (QKeySequence("Shift+G"), lambda: ps.tecla_herramienta("Mayús+G")),
                       (QKeySequence(Qt.Key_C), lambda: ps.tecla_herramienta("C")),
                       (QKeySequence(Qt.Key_BracketLeft), lambda: ps.cambiar_tamano_pincel(-1)),
                       (QKeySequence(Qt.Key_BracketRight), lambda: ps.cambiar_tamano_pincel(1)),
                       (QKeySequence(Qt.Key_F2), solo_ps(lambda: self.panel_capas.renombrar_elegida())),
                       (QKeySequence(Qt.Key_X), ps.intercambiar_colores),
                       (QKeySequence(Qt.Key_D), ps.restablecer_colores),
                       (QKeySequence("Ctrl+T"), solo_ps(lambda: ps.alternar_transformar(True))),
                       (QKeySequence("Ctrl+J"), solo_ps(ps.duplicar)),
                       (QKeySequence("Ctrl+G"), solo_ps(ps.agrupar)),
                       (QKeySequence("Ctrl+Shift+G"), solo_ps(ps.desagrupar)),
                       (QKeySequence("Ctrl+Shift+N"), solo_ps(ps.nueva_capa_pixeles)),
                       (QKeySequence("Ctrl+Alt+I"), solo_ps(ps.tamano_imagen)),
                       (QKeySequence("Ctrl+Alt+C"), solo_ps(ps.tamano_lienzo)),
                       (QKeySequence("Ctrl+Shift+O"), solo_ps(ps.abrir_como_capas)),
                       (QKeySequence.Paste, solo_ps(ps.pegar)),
                       (QKeySequence(Qt.Key_Delete), solo_ps(ps.borrar)))
        else:
            propios = ((QKeySequence.Save, self.exportar),)  # la PRO, como siempre
        for atajo, funcion in propios + (
            (QKeySequence.Open, self.elegir_archivo),
            (QKeySequence("Ctrl+0"), self.vista.ajustar),
            (QKeySequence("Ctrl+1"), lambda: self.vista.fijar_zoom(1.0)),
            (QKeySequence("Ctrl+2"), lambda: self.vista.fijar_zoom(2.0)),
            (QKeySequence.Undo, self.deshacer),
            (QKeySequence("Ctrl+Y"), self.rehacer),
            (QKeySequence("Ctrl+Shift+Z"), self.rehacer),
            (QKeySequence.ZoomIn, self.vista.acercar),
            (QKeySequence("Ctrl+="), self.vista.acercar),
            (QKeySequence.ZoomOut, self.vista.alejar),
        ):
            accion = QAction(fotos)
            accion.setShortcut(atajo)
            accion.triggered.connect(funcion)
            fotos.addAction(accion)
        # Los de todos los modos, en la ventana (en la Lite, sin los de Video y Audio).
        atajos = [(QKeySequence("Ctrl+E"), self.alternar_modo)]  # Fácil <-> Editor (desde Video o Audio, a fotos)
        if self._lite:
            atajos.append((QKeySequence("Ctrl+Shift+P"), self.alternar_photoshop))  # Photoshop <-> Fácil/Editor
        else:
            atajos += [(QKeySequence("Ctrl+Shift+V"), self.alternar_video),  # Video <-> fotos
                       (QKeySequence("Ctrl+Shift+A"), self.alternar_audio)]  # Audio <-> el modo de antes
        atajos.append((QKeySequence(Qt.Key_F1), self.mostrar_tutorial))
        for atajo, funcion in atajos:
            accion = QAction(self)
            accion.setShortcut(atajo)
            accion.triggered.connect(funcion)
            self.addAction(accion)

    def _formato(self) -> str:
        boton = self.grupo_formato.checkedButton()
        return boton.property("formato") if boton is not None else "PNG"

    def _al_cambiar_formato(self) -> None:
        es_jpeg = self._formato() == "JPEG"
        self.caja_calidad.setVisible(es_jpeg)
        for w in (self.slider_calidad, self.etiqueta_calidad, self.valor_calidad):
            w.setEnabled(es_jpeg)

    def _actualizar_habilitados(self) -> None:
        hay = self._imagen is not None
        for w in (self.boton_alejar, self.boton_ajustar, self.boton_100, self.boton_200, self.boton_acercar):
            w.setEnabled(hay)
        self.boton_deshacer.setEnabled(self._pos_historial > 0)
        self.boton_rehacer.setEnabled(self._pos_historial < len(self._historial) - 1)
        # Un documento nuevo (sin foto) no tiene las herramientas de la foto de base: el recorte y el
        # enderezado del Editor, el montaje, borrar objetos y el fondo (girar y voltear sí: giran el lienzo).
        lienzo = self.es_documento_sin_foto()
        self.boton_recortar.setEnabled(hay and not lienzo)
        self.boton_enderezar.setEnabled(hay and not lienzo)
        self.boton_medida.setEnabled(hay and not lienzo)
        self.boton_medida.setToolTip(AYUDA_SIN_FOTO if lienzo else self._ayuda_medida())
        for b, ayuda in ((self.boton_recortar, "Recortar la foto (no destructivo: se puede cambiar o quitar después)"),
                         (self.boton_enderezar, "Enderezar la foto: girarla de a poco (hasta 15°) o nivelarla sola "
                                                "con el horizonte. Recorta las esquinas que quedarían vacías.")):
            b.setToolTip(AYUDA_SIN_FOTO if lienzo else ayuda)
        for panel in (self.panel_montaje, self.panel_borrar, self.panel_fondo):
            panel.setEnabled(not lienzo)
            panel.setToolTip(AYUDA_SIN_FOTO if lienzo else "")
        if hasattr(self, "nota_sin_foto"):
            self.nota_sin_foto.setVisible(lienzo)
        self.boton_transformar.setEnabled(True)
        # Las del modo Photoshop: máscaras, kit, alinear (``ModoPhotoshop.actualizar_habilitados``).
        self.photoshop.actualizar_habilitados(hay)
        for b in self.botones_geometria:
            b.setEnabled(hay)
        self.boton_lote.setEnabled(not self._exportando)
        self.boton_exportar.setEnabled(hay and not self._exportando)
        self.boton_exportar.setText("  Exportando…" if self._exportando else "  Exportar como archivo nuevo…")
        if hasattr(self, "panel_facil"):
            self.panel_facil.actualizar_habilitados()

    def _ocupado(self) -> None:
        procesando = self._imagen is not None and self._generacion_completa_mostrada != self._generacion
        pendiente = self._imagen is not None and self._fuentes_pendientes
        detectando = self._deteccion is not None
        if detectando:
            texto = TEXTO_DETECCION.get(self._deteccion[1])
        else:
            texto = "Borrando…" if pendiente and self.panel_borrar.estado() else None
        self.vista.establecer_procesando(procesando or pendiente or detectando, texto)
        self.barra_progreso.setVisible(procesando or pendiente or detectando or self._exportando
                                       or self._guardando_proyecto)

    # =============================================================== carga
    def elegir_archivo(self) -> None:
        """Abrir (Ctrl+O, en todos los modos): fotos, videos y audios en el mismo diálogo; cada cosa
        va a su modo (``abrir_rutas``). En la Lite, solo fotos."""
        if self._lite:
            inicio = self.carpeta_inicio()
            rutas, _ = QFileDialog.getOpenFileNames(self, "Abrir fotos o un proyecto (podés elegir varias fotos)",
                                                    inicio, con_proyectos(FILTRO_ABRIR_FOTOS))
            if rutas:
                self.abrir_rutas(rutas)
            return
        en_video, en_audio = self._modo == VIDEO, self._modo == AUDIO
        editor = self.editor_video
        if en_video and editor is not None and editor.ruta:
            inicio = str(Path(editor.ruta).parent)
        elif en_audio and self.editor_audio is not None and self.editor_audio.ruta:
            inicio = str(Path(self.editor_audio.ruta).parent)
        elif self._imagen is not None and not en_audio:
            inicio = str(self._imagen.ruta.parent)
        else:
            inicio = str(Path.home() / ("Videos" if en_video else "Music" if en_audio else "Pictures"))
        if en_audio:
            titulo, filtro = "Abrir un audio (si elegís fotos o videos, se abren en su modo)", FILTRO_ABRIR_AUDIO
        elif en_video:
            titulo, filtro = "Abrir un video (si elegís fotos, se abren en el modo de fotos)", FILTRO_ABRIR_TODO
        else:
            titulo, filtro = "Abrir fotos, un video o un audio (podés elegir varias fotos)", FILTRO_ABRIR_TODO
        rutas, _ = QFileDialog.getOpenFileNames(self, titulo, inicio, con_proyectos(filtro))
        if rutas:
            self.abrir_rutas(rutas)

    def abrir_archivo(self, ruta: str) -> None:
        """Abre un archivo: un video va al modo Video; un audio, al modo Audio; una foto, a la tira.
        (En la Lite, un video o un audio solo avisa: ``abrir_rutas``.) Un ``.nslite``, como proyecto."""
        if es_video(ruta) or es_audio(ruta) or es_proyecto(ruta) or self._modo in (VIDEO, AUDIO):
            self.abrir_rutas([ruta])
        else:
            self.agregar_fotos([ruta])

    def abrir_rutas(self, rutas) -> None:
        """Abre fotos, videos y audios, cada cosa en su modo (Abrir, arrastrar o "Abrir con…").

        * Fotos: a la tira. Si se estaba en Video o en Audio, se vuelve al último modo de fotos.
        * Un video: al modo Video. Se edita uno a la vez: de varios se abre el primero.
        * Un audio: al modo Audio (también de a uno). Si no tiene sonido o no se puede leer,
          se avisa y el modo queda como estaba.
        * Varias cosas juntas: cada una a su lugar. Se termina en el modo en que se estaba si
          algo fue ahí; si no, en Video (si se abrió un video), en Audio o en las fotos.

        Un aviso explica cada cambio de modo. Lo que no es un video ni un audio se trata como
        foto (si no se puede leer, se avisa como siempre).

        En la Lite solo entran las fotos: los videos y audios no se abren (ni se carga nada
        de video o audio) y un aviso lo explica. El modo no cambia.

        Un proyecto ``.nslite`` se abre como proyecto (``abrir_proyecto``), en el modo de fotos."""
        rutas = [str(r) for r in rutas if r]
        proyectos = [r for r in rutas if es_proyecto(r)]
        if proyectos:
            otras = [r for r in rutas if not es_proyecto(r)]
            if otras:
                self.abrir_rutas(otras)
            if self._modo in (VIDEO, AUDIO):
                self.establecer_modo(self._modo_fotos)
            for ruta in proyectos:
                self.abrir_proyecto(ruta)
            return
        fotos, videos, audios = clasificar_rutas(rutas, audios=True)
        if not fotos and not videos and not audios:
            return
        if self._lite:
            if fotos:
                self.agregar_fotos(fotos)
            if videos or audios:
                self._avisar_solo_fotos(videos, audios, fotos)
            return
        desde_video, desde_audio = self._modo == VIDEO, self._modo == AUDIO
        video, ignorados = (videos[0], videos[1:]) if videos else (None, [])
        audio, ignorados_audio = (audios[0], audios[1:]) if audios else (None, [])
        editor = self.editor_video
        if video is not None and editor is not None and not editor.confirmar_reemplazo(video):
            video, ignorados = None, []  # se eligió seguir con el video abierto (y sus cortes)
        proyecto, error_audio = None, None
        if audio is not None:
            if self.editor_audio is None and self._audio_pendiente is not None:
                self._asegurar_editor_audio()  # primero el de la sesión: si tiene cambios, se pregunta
            editor_audio = self.editor_audio
            if editor_audio is not None and editor_audio.es_el_abierto(audio):
                pass  # ya está abierto: se conserva como está
            elif editor_audio is not None and not editor_audio.confirmar_reemplazo(audio):
                audio, ignorados_audio = None, []
            else:
                from .modo_audio import abrir_voz  # recién acá se carga lo del audio (y PyAV)
                try:
                    proyecto = abrir_voz(audio)
                except ValueError as error:
                    error_audio, audio, ignorados_audio = str(error), None, []
        if not fotos and video is None and audio is None:
            if error_audio:  # el modo queda como estaba
                self.aviso.mostrar(error_audio, "", icono="triangle-alert")
            return
        if fotos:
            if (desde_video or desde_audio) and video is None and audio is None:
                self.establecer_modo(self._modo_fotos)
            self.agregar_fotos(fotos)
        # El modo en que se termina: el de antes si algo fue ahí; si no, Video, Audio o las fotos.
        if video is not None:
            if not (desde_audio and audio is not None):
                self.establecer_modo(VIDEO)
            self._asegurar_editor().abrir(video, confirmar=False)
        if audio is not None:
            if not (desde_video and video is not None) and not (video is not None and not desde_audio):
                self.establecer_modo(AUDIO)
            editor_audio = self._asegurar_editor_audio()
            if proyecto is not None:
                editor_audio.cargar_proyecto(proyecto)
        editor = self.editor_video
        texto, detalle = mensaje_ruteo(desde_video, fotos, video, ignorados,
                                       video_abierto=editor is not None and editor.ruta is not None,
                                       audio=audio, ignorados_audio=ignorados_audio, desde_audio=desde_audio,
                                       audio_abierto=self.editor_audio is not None and self.editor_audio.ruta is not None)
        if error_audio:
            texto = (texto + " " if texto else "") + error_audio
        if texto:
            icono = "triangle-alert" if error_audio else "audio-lines" if audio else "film" if video else "image"
            self.aviso.mostrar(texto, detalle, icono=icono, tipo="modo")

    def _soltado_en_vista(self, rutas) -> None:
        """Archivos soltados sobre la foto: en el modo Photoshop, las imágenes entran como capas (no
        hace falta Ctrl); lo demás (y en los otros modos, todo) se abre como siempre."""
        rutas = [str(r) for r in rutas]
        if self._modo == PHOTOSHOP and self._imagen is not None:
            imagenes = [r for r in rutas if es_foto(r)]
            otras = [r for r in rutas if not es_foto(r)]
            if imagenes:
                self.agregar_imagenes_como_capa(imagenes)
            if otras:
                self.abrir_rutas(otras)
            return
        self.abrir_rutas(rutas)

    def _avisar_solo_fotos(self, videos=(), audios=(), fotos=()) -> None:
        """NaturalShot Lite: "es solo para fotos" (los videos y audios no se abren)."""
        texto, detalle = mensaje_solo_fotos(list(videos), list(audios), list(fotos))
        if not texto:
            texto, detalle = "NaturalShot Lite es solo para fotos: no tiene modo Video ni Audio.", ""
        self.aviso.mostrar(texto, detalle, icono="image", tipo="modo")

    @staticmethod
    def _rutas_arrastradas(evento) -> list:
        datos = evento.mimeData()
        if not datos.hasUrls():
            return []
        return [u.toLocalFile() for u in datos.urls()
                if u.toLocalFile() and (es_foto(u.toLocalFile()) or es_video(u.toLocalFile())
                                        or es_audio(u.toLocalFile()) or es_proyecto(u.toLocalFile()))]

    def dragEnterEvent(self, evento) -> None:
        if self._rutas_arrastradas(evento):
            evento.acceptProposedAction()
        else:
            evento.ignore()

    def dragMoveEvent(self, evento) -> None:
        if self._rutas_arrastradas(evento):
            evento.acceptProposedAction()

    def dropEvent(self, evento) -> None:
        """Fotos o videos soltados fuera de la vista (en una columna, por ejemplo). En el modo
        Photoshop, las imágenes entran como capas, igual que sobre la vista."""
        rutas = self._rutas_arrastradas(evento)
        if rutas:
            evento.acceptProposedAction()
            self._soltado_en_vista(rutas)

    # ================================================================ tira de fotos
    @staticmethod
    def _misma_ruta(a: str, b: str) -> bool:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))

    def agregar_fotos(self, rutas: list) -> None:
        """Suma fotos a la tira y muestra la primera de las nuevas."""
        destino = None
        nuevas = []
        for ruta in rutas:
            ruta = str(Path(ruta))
            existente = next((i for i, f in enumerate(self._fotos) if self._misma_ruta(f.ruta, ruta)), None)
            if existente is None:
                self._fotos.append(FotoSesion(ruta))
                nuevas.append(len(self._fotos) - 1)
            elif destino is None:
                destino = existente
        if nuevas:
            destino = nuevas[0]
        if destino is None:
            return
        self._refrescar_tira()
        for i in nuevas:
            if i != destino:
                self._cargar_miniatura(self._fotos[i].ruta)
        self.cambiar_a_foto(destino)
        self._sesion_cambiada()

    def _cargar_miniatura(self, ruta: str) -> None:
        foto = next((f for f in self._fotos if self._misma_ruta(f.ruta, ruta)), None)
        doc = (foto.estado or {}).get("documento") if foto is not None and dc.es_ruta_documento(ruta) else None
        almacen = self._almacen

        def trabajo(_cancelado):
            if doc is not None:  # un documento sin foto: su composición, en chico
                imagen = dc.imagen_documento(ruta, doc)
                escala = min(1.0, LADO_MINIATURA / max(doc.ancho, doc.alto))
                return ruta, imagen, a_qimage(componer_capas(doc, almacen, None, escala))
            imagen = cargar_imagen(ruta)
            chica, _ = reducir_para_vista(imagen.rgb, LADO_MINIATURA)
            return ruta, imagen, a_qimage(TransformacionPantalla(imagen.icc).a_srgb(chica))
        self._pool_miniaturas.start(Tarea("miniatura", 0, trabajo, self._senales))

    def _miniatura_lista(self, resultado) -> None:
        ruta, imagen, qimagen = resultado
        for i, f in enumerate(self._fotos):
            if self._misma_ruta(f.ruta, ruta):
                if f.imagen is None:
                    f.imagen = imagen
                f.miniatura = QPixmap.fromImage(qimagen)
                self.tira.actualizar_miniatura(i, f.miniatura)  # sin rearmar la tira
        self.panel_montaje.completar_miniaturas(self._miniatura_de)

    def _refrescar_tira(self) -> None:
        self.tira.establecer([(f.ruta, f.miniatura) for f in self._fotos], self._actual)

    def _otras_fotos(self) -> list:
        """Las otras fotos de la tira (para el montaje): los documentos sin foto no cuentan."""
        return [(f.ruta, f.miniatura) for i, f in enumerate(self._fotos)
                if i != self._actual and not dc.es_ruta_documento(f.ruta)]

    def _miniatura_de(self, ruta: str) -> Optional[QPixmap]:
        return next((f.miniatura for f in self._fotos if self._misma_ruta(f.ruta, ruta)), None)

    def _guardar_foto_actual(self) -> None:
        if not (0 <= self._actual < len(self._fotos)) or self._imagen is None:
            return
        self._timer_historial.stop()
        self._registrar_historial()
        foto = self._fotos[self._actual]
        foto.estado = self._estado_completo()
        foto.historial = list(self._historial)
        foto.pos = self._pos_historial

    def cambiar_a_foto(self, indice: int) -> None:
        if not (0 <= indice < len(self._fotos)):
            return
        if indice == self._actual and self._imagen is not None:
            return
        # Primero los modos que muestran la foto entera (sin recalcularla: se va a cambiar).
        if self._modo_recorte:
            self._salir_recorte("cancelar", recalcular=False)
        if self._modo_enderezar:
            self._salir_enderezar("cancelar", recalcular=False)
        self.cancelar_herramienta()
        self._guardar_foto_actual()
        self._actual = indice
        self._refrescar_tira()
        self._sesion_cambiada()
        foto = self._fotos[indice]
        ruta, cacheada = foto.ruta, foto.imagen
        self._generacion_carga += 1
        generacion = self._generacion_carga
        self.etiqueta_estado.setText(f"Abriendo {dc.nombre_documento(ruta)}…")
        self.barra_progreso.show()
        # Un documento sin foto ("Nuevo"): su "foto" se arma en memoria, del tamaño del documento.
        doc_sin_foto = (foto.estado or {}).get("documento") if dc.es_ruta_documento(ruta) else None

        def cargar(_cancelado):
            if doc_sin_foto is not None:
                imagen = cacheada if cacheada is not None and (cacheada.ancho, cacheada.alto) == (
                    doc_sin_foto.ancho, doc_sin_foto.alto) else dc.imagen_documento(ruta, doc_sin_foto)
            else:
                imagen = cacheada if cacheada is not None else cargar_imagen(ruta)
            transformacion = TransformacionPantalla(imagen.icc)
            antes = a_qimage(transformacion.a_srgb(imagen.rgb), imagen.alpha)
            vista_previa, escala = reducir_para_vista(imagen.rgb, LADO_VISTA_PREVIA)
            chica, _ = reducir_para_vista(imagen.rgb, LADO_MINIATURA)
            mini = a_qimage(transformacion.a_srgb(chica))
            return imagen, transformacion, antes, vista_previa, escala, mini, indice

        self._pool_archivos.start(Tarea("carga", generacion, cargar, self._senales))

    def quitar_foto(self, indice: int) -> None:
        if not (0 <= indice < len(self._fotos)) or len(self._fotos) <= 1:
            return
        if indice == self._actual:
            vecina = indice + 1 if indice + 1 < len(self._fotos) else indice - 1
            self.cambiar_a_foto(vecina)
        del self._fotos[indice]
        if self._actual > indice:
            self._actual -= 1
        self._refrescar_tira()
        self._sesion_cambiada()

    def _imagen_cargada(self, resultado) -> None:
        imagen, transformacion, antes, vista_previa, escala, mini, indice = resultado
        if indice != self._actual:
            return
        foto = self._fotos[indice]
        foto.imagen = imagen
        foto.miniatura = QPixmap.fromImage(mini)
        self._refrescar_tira()
        self._imagen = imagen
        self._transformacion = transformacion
        self._vista_previa = vista_previa
        self._escala_vista_previa = escala
        self._resultado_completo = None
        self._fuente, self._alpha_fuente = imagen.rgb, imagen.alpha
        self._antes_completo = self._antes_actual = self._antes_original = antes
        self._base_completa = imagen.rgb
        self._clave_base = (str(imagen.ruta), Geometria(), (), ())
        self._clave_vista_previa = (self._clave_base, None)  # la vista previa es la foto tal cual
        self._version_fuente += 1
        if self._modo_recorte:
            self._salir_recorte("cancelar", recalcular=False)
        if self._modo_enderezar:
            self._salir_enderezar("cancelar", recalcular=False)
        self.vista.establecer_imagenes(antes, None, (imagen.ancho, imagen.alto))
        # Cada foto tiene su propia edición. Una foto nueva hereda el preset y las
        # capas de la anterior, pero no lo que es propio de cada foto.
        if foto.estado is not None:
            estado, historial, pos = foto.estado, list(foto.historial or [("Inicio", foto.estado)]), foto.pos
        else:
            estado = self._estado_para_foto_nueva()
            historial, pos = [("Inicio", estado)], 0
        self._restaurando = True
        try:
            self.panel_ajustes.restaurar(estado)
            self.panel_montaje.restaurar(estado.get("montaje", ()), self._miniatura_de)
            self.panel_fondo.restaurar(estado.get("fondo", FONDO_INICIAL))
            self.panel_borrar.restaurar(estado.get("borrado", ()))
        finally:
            self._restaurando = False
        self._recorte = estado.get("recorte")
        self._medida = md.medida_valida(estado.get("medida"))
        self._geometria = estado.get("geometria") or Geometria()
        self._documento = self._documento_de(estado)
        self._doc_provisorio = None
        self._actualizar_medida()
        self._refrescar_panel_capas(miniatura=True)
        self._historial, self._pos_historial = historial, min(pos, len(historial) - 1)
        self._limpiar_almacen()  # las máscaras de la foto anterior pasan a comprimidas
        self._refrescar_historial()
        self._actualizar_superposiciones()
        if (self._recorte is not None or estado.get("montaje") or estado.get("borrado")
                or not self._geometria.es_identidad()):
            self._recalcular_fuentes()
        notas = (" · " + " · ".join(imagen.notas)) if imagen.notas else ""
        nombre = dc.nombre_documento(imagen.ruta)
        documento = dc.es_ruta_documento(imagen.ruta)
        self._texto_imagen = (
            f"{nombre}  ·  {imagen.ancho} × {imagen.alto} px  ·  "
            + ("documento" if documento else imagen.nombre_perfil)
            + ("  ·  con transparencia" if imagen.alpha is not None else "") + notas
        )
        self.etiqueta_estado.setText(self._texto_imagen)
        self.pie_avatar.setText((Path(nombre).stem[:1] or "?").upper())
        self.pie_nombre.setText(self.pie_nombre.fontMetrics().elidedText(nombre, Qt.ElideMiddle, 230))
        self.pie_detalle.setText(f"{imagen.ancho} × {imagen.alto} px · "
                                 + ("documento nuevo" if documento else imagen.nombre_perfil))
        self._titulo_fotos = f"{nombre} — {self._nombre_app}"
        self._sincronizar_lienzo()
        self._actualizar_titulo()
        self._actualizar_habilitados()
        self.solicitar_render()
        self.panel_facil.foto_cambiada()
        self._sesion_cambiada()
        self.photoshop.foto_cargada()
        if self._sesion_foto_pendiente >= 0:  # ya se ve la foto que estaba abierta la vez anterior
            self._terminar_restauracion()

    def _estado_para_foto_nueva(self) -> dict:
        """Una foto nueva hereda el preset y las capas de la actual, pero no lo que es
        propio de cada foto (zonas, recorte, giro, montaje, borrados ni el objeto del fondo)."""
        estado = dict(self._estado_completo())
        estado["capas"] = [(p, i, None) for p, i, *_ in estado["capas"]]
        estado["recorte"] = None
        estado["montaje"] = ()
        estado["fondo"] = (None,) + completar_estado(estado.get("fondo"))[1:]
        estado["geometria"] = Geometria()
        estado["borrado"] = ()
        estado.pop("documento", None)  # las capas son de cada foto
        estado.pop("medida", None)  # la medida también (va con su recorte)
        return estado

    # ========================================================== capas
    def _documento_de(self, estado: dict) -> Documento:
        """El documento de capas de un estado o, si no tiene (el de siempre), uno nuevo del tamaño
        de la foto que entra al filtro."""
        doc = estado.get("documento")
        if isinstance(doc, Documento):
            self._traer_mascaras(doc)
            return doc
        return dc.documento_nuevo(*self._tam_mostrado())

    def _con_filtro(self) -> bool:
        """Si la vista lleva el filtro: siempre, salvo en el modo Photoshop (ahí, con "Ver con el filtro")."""
        return self._modo != PHOTOSHOP or self.boton_ver_filtro.isChecked()

    def _documento_vista(self) -> Optional[Documento]:
        """El que se ve: el provisorio de un gesto en curso o el de la foto."""
        return self._doc_provisorio if self._doc_provisorio is not None else self._documento

    def tiene_capas_extra(self) -> bool:
        """Si la foto tiene capas imagen (Fácil las muestra y lo avisa)."""
        return dc.tiene_capas_extra(self._documento)

    def _miniatura_foto(self) -> Optional[QPixmap]:
        if self._vista_previa is None or self._transformacion is None:
            return None
        import cv2
        h, w = self._vista_previa.shape[:2]
        f = 72 / max(h, w)
        chica = cv2.resize(self._vista_previa, (max(1, round(w * f)), max(1, round(h * f))),
                           interpolation=cv2.INTER_AREA) if f < 1 else self._vista_previa
        return miniatura_capa(self._transformacion.a_srgb(np.ascontiguousarray(chica)))

    def _refrescar_panel_capas(self, miniatura: bool = False) -> None:
        """Pone en el panel el documento de la foto (y, si se pide, la miniatura de la "Foto")."""
        if self._imagen is None or self._documento is None:
            self.panel_capas.establecer(None, None)
            self.photoshop.refrescar_propiedades()
            return
        self.panel_capas.establecer(self._documento, self._almacen, self._miniatura_foto() if miniatura else None)
        self.photoshop.refrescar_propiedades()

    def _al_elegir_capa(self, id_capa: str) -> None:
        """Se eligió otra capa en el panel: una transformación en curso de otra capa queda aplicada."""
        if self._transformando is not None and self._transformando[0] != id_capa:
            self._salir_transformar("aplicar")
        self._actualizar_habilitados()
        self.photoshop.refrescar_propiedades()
        self.vista.update()

    def _al_cambiar_documento(self, doc: Documento, registrar: bool) -> None:
        """Un cambio en el panel de capas: con ``registrar``, queda como un paso del historial; si
        no (mientras dura un gesto, como arrastrar la opacidad), solo se ve."""
        if self._imagen is None:
            return
        if registrar:
            self._cambiar_documento(doc, descripcion=self.panel_capas.descripcion)
        else:
            self._doc_provisorio = doc
            self.solicitar_render()
        self.photoshop.refrescar_propiedades(doc if not registrar else None)

    def _cambiar_documento(self, doc: Documento, refrescar_panel: bool = False,
                           descripcion: Optional[str] = None) -> None:
        """El documento nuevo de la foto, como un paso del historial (lo pendiente queda como su propio paso)."""
        self._timer_historial.stop()
        self._registrar_historial()  # lo que estaba sin registrar (un deslizador, por ejemplo), aparte
        self._documento = doc
        self._doc_provisorio = None
        self._sincronizar_lienzo()  # un documento sin foto que cambió de tamaño
        if refrescar_panel:
            self._refrescar_panel_capas()
        self._registrar_historial(descripcion)
        self._limpiar_almacen()
        self.solicitar_render()
        self._actualizar_habilitados()
        if self.panel_facil.isVisible():
            self.panel_facil.sincronizar()  # la nota de "ediciones del editor"

    def _limpiar_almacen(self) -> None:
        """Ordena la memoria de las capas:

        * lo que usa el documento de la foto abierta (y el provisorio de un gesto) queda en el almacén;
        * las máscaras que solo usan otros pasos (el historial, otras fotos) pasan a ``_comprimidas``
          (cada paso de pincel es una máscara entera: sin esto, 100 pasos a 24 MP eran unos 2,4 GB);
        * lo que ya no usa ningún paso de ninguna foto se suelta.

        Las imágenes de las capas que solo usan otros pasos también se comprimen si son grandes (con el
        pincel, el borrador o el bote, cada paso es una imagen entera de la capa); las chicas quedan."""
        estados = [self._estado_completo()] + [e for _d, e in self._historial]
        for f in self._fotos:
            estados += ([f.estado] if f.estado else []) + [e for _d, e in (f.historial or ())]
        usados = dc.ids_usados(estados)
        vivos = set()
        for doc in (self._documento, self._doc_provisorio):
            if doc is not None:
                vivos |= doc.ids_usados()
        usados |= vivos
        for id_img in self._almacen.ids():
            if id_img not in usados:
                self._almacen.quitar(id_img)
                continue
            if id_img in vivos:
                continue
            try:
                arr = self._almacen.obtener(id_img)
            except KeyError:
                continue
            if arr.ndim == 2 or arr.nbytes >= 1 << 20:  # una máscara o una imagen grande de un paso que no se ve
                if id_img not in self._comprimidas:
                    self._comprimidas[id_img] = (arr.shape, zlib.compress(arr.tobytes(), 1))
                self._almacen.quitar(id_img)
        for id_img in list(self._comprimidas):
            if id_img not in usados:
                del self._comprimidas[id_img]

    def _arreglo(self, id_img: str) -> Optional[np.ndarray]:
        """Una imagen o máscara de las capas: del almacén o, si está comprimida, descomprimida. None si falta."""
        try:
            return self._almacen.obtener(id_img)
        except KeyError:
            pass
        comprimida = self._comprimidas.get(id_img)
        if comprimida is None:
            return None
        forma, datos = comprimida
        return np.frombuffer(zlib.decompress(datos), np.uint8).reshape(forma)

    def _traer_mascaras(self, doc: Optional[Documento]) -> None:
        """Vuelve a poner en el almacén las máscaras comprimidas que usa ``doc`` (el mismo contenido da
        el mismo id)."""
        if doc is None:
            return
        for id_img in doc.ids_usados():
            if id_img not in self._almacen and id_img in self._comprimidas:
                self._almacen.guardar(self._arreglo(id_img))

    # ------------------------------------------------------------ documentos sin foto ("Nuevo")
    def es_documento_sin_foto(self) -> bool:
        """Si lo abierto es un documento nuevo (``Documento.nuevo_lienzo``): no tiene foto de base."""
        return (self._imagen is not None and 0 <= self._actual < len(self._fotos)
                and dc.es_ruta_documento(self._fotos[self._actual].ruta))

    def agregar_documento(self, doc: Documento, descripcion: str, nombre: str = "Sin título") -> None:
        """Suma a la tira un documento sin foto (``doc``, con un fondo de relleno) y lo abre. Su estado
        hereda el preset y los efectos de la foto abierta, como una foto nueva; su historial empieza
        con ``descripcion``."""
        estado = dict(self._estado_para_foto_nueva())
        estado["documento"] = doc
        ruta = dc.ruta_documento_nueva([f.ruta for f in self._fotos], nombre)
        self._fotos.append(FotoSesion(ruta, estado=estado, historial=[(descripcion, estado)], pos=0))
        self._refrescar_tira()
        self.cambiar_a_foto(len(self._fotos) - 1)
        self._sesion_cambiada()

    def _sincronizar_lienzo(self) -> None:
        """En un documento sin foto, su "foto" (una imagen lisa, ``dc.imagen_documento``) mide siempre
        lo mismo que el documento: si cambió el tamaño del lienzo (Imagen › Tamaño, Recortar, Rotar, o
        deshacer uno de esos), se rearma. Así la vista, las zonas de los efectos y la exportación siguen
        el tamaño nuevo."""
        doc = self._documento
        if doc is None or doc.tiene_foto or self._imagen is None or not self.es_documento_sin_foto():
            return
        nuevo_color = dc.color_base(doc)
        if (self._imagen.ancho, self._imagen.alto) == (doc.ancho, doc.alto) \
                and tuple(int(c) for c in self._imagen.rgb[0, 0]) == nuevo_color:
            return
        foto = self._fotos[self._actual]
        imagen = dc.imagen_documento(foto.ruta, doc)
        foto.imagen = imagen
        self._poner_fuente_documento(imagen)

    def _poner_fuente_documento(self, imagen) -> None:
        """La "foto" de un documento sin foto como fuente de la vista (sin geometría, recorte, montaje
        ni borrados: no aplican)."""
        self._imagen = imagen
        self._transformacion = TransformacionPantalla(None)
        self._fuente, self._alpha_fuente = imagen.rgb, None
        self._base_completa = imagen.rgb
        self._vista_previa, self._escala_vista_previa = reducir_para_vista(imagen.rgb, LADO_VISTA_PREVIA)
        antes = a_qimage(self._vista_previa)
        self._antes_completo = self._antes_actual = self._antes_original = antes
        self._clave_base = (str(imagen.ruta), Geometria(), (), (), (imagen.ancho, imagen.alto))
        self._clave_vista_previa = (self._clave_base, None)
        self._version_fuente += 1
        self._resultado_completo = None
        self.vista.establecer_imagenes(antes, None, (imagen.ancho, imagen.alto))
        self.pie_detalle.setText(f"{imagen.ancho} × {imagen.alto} px · documento nuevo")
        self._texto_imagen = f"{dc.nombre_documento(imagen.ruta)}  ·  {imagen.ancho} × {imagen.alto} px  ·  documento"
        self.etiqueta_estado.setText(self._texto_imagen)

    # ========================================================== historial
    def _al_cambiar_ajustes(self, _pila) -> None:
        if not self._restaurando:
            self._timer_historial.start()
        self._actualizar_superposiciones()
        self.solicitar_render()

    def _estado_completo(self) -> dict:
        estado = dict(self.panel_ajustes.estado())
        estado["recorte"] = self._recorte
        estado["montaje"] = self.panel_montaje.estado()
        estado["fondo"] = self.panel_fondo.estado_fondo()
        estado["geometria"] = self._geometria
        estado["borrado"] = self.panel_borrar.estado()
        # La medida, solo si hay una: sin ella el estado es igual al de antes (historial y sesión).
        if self._medida is not None:
            estado["medida"] = self._medida
        # Las capas, solo si hay algo más que la foto y el filtro de siempre: así el estado de una foto
        # sin capas es igual al de antes (y también sus pasos del historial y la sesión).
        if not dc.es_trivial(self._documento):
            estado["documento"] = self._documento
        return estado

    def _registrar_historial(self, descripcion: Optional[str] = None) -> None:
        """Anota un paso si el estado cambió. ``descripcion``: la del paso (si no, se deduce del cambio)."""
        estado = self._estado_completo()
        actual = self._historial[self._pos_historial][1]
        if estado == actual:
            return
        descripcion = descripcion or describir_cambio(actual, estado)
        del self._historial[self._pos_historial + 1:]  # un cambio nuevo descarta los pasos deshechos
        self._historial.append((descripcion, estado))
        if len(self._historial) > MAX_HISTORIAL:
            del self._historial[1:len(self._historial) - MAX_HISTORIAL + 1]
        self._pos_historial = len(self._historial) - 1
        self._refrescar_historial()
        self._actualizar_habilitados()
        self._sesion_cambiada()

    def _refrescar_historial(self) -> None:
        lista = self.lista_historial
        lista.blockSignals(True)
        lista.clear()
        for i, (descripcion, _estado) in enumerate(self._historial):
            item = QListWidgetItem(f"{i}.  {descripcion}" if i else "Inicio")
            item.setToolTip(descripcion)
            item.setIcon(iconos.icono("history" if i == 0 else "check", 14))
            if i > self._pos_historial:
                # Pasos deshechos: siguen ahí para rehacerlos, pero apagados.
                item.setForeground(QColor(estilo.TEXTO_TENUE))
                fuente = QFont(item.font())
                fuente.setItalic(True)
                item.setFont(fuente)
            lista.addItem(item)
        lista.setCurrentRow(self._pos_historial)
        lista.scrollToItem(lista.currentItem())
        lista.blockSignals(False)

    def _restaurar(self, estado: dict) -> None:
        """Pone el editor en ``estado`` (de cualquier versión: las claves que falten
        toman su valor inicial) y recalcula la foto base si hace falta."""
        montaje = estado.get("montaje", ())
        borrados = tuple(estado.get("borrado", ()))
        geometria = estado.get("geometria") or Geometria()
        cambio_montaje = montaje != self.panel_montaje.estado()
        cambio_base = (cambio_montaje or borrados != self.panel_borrar.estado() or geometria != self._geometria
                       or estado.get("recorte") != self._recorte)
        self._restaurando = True
        try:
            self.panel_ajustes.restaurar(estado)
            if cambio_montaje:
                self.panel_montaje.restaurar(montaje, self._miniatura_de)
            self.panel_fondo.restaurar(estado.get("fondo", FONDO_INICIAL))
            self.panel_borrar.restaurar(borrados)
        finally:
            self._restaurando = False
        self._geometria = geometria
        self._recorte = estado.get("recorte")
        medida = md.medida_valida(estado.get("medida"))
        cambio_medida = medida != self._medida
        self._medida = medida
        if cambio_medida:
            self._actualizar_medida()
        documento = self._documento_de(estado) if self._imagen is not None else None
        cambio_capas = documento != self._documento
        self._documento = documento
        self._doc_provisorio = None
        self._sincronizar_lienzo()  # deshacer o rehacer un cambio de tamaño del lienzo
        if cambio_capas:
            self._refrescar_panel_capas()
            self._limpiar_almacen()
        if cambio_base:
            self._recalcular_fuentes()
        elif cambio_capas or cambio_medida:
            self.solicitar_render()
        self._actualizar_superposiciones()
        self._refrescar_historial()
        self._actualizar_habilitados()

    def ir_al_historial(self, indice: int) -> None:
        if self._herramienta_activa():
            self.cancelar_herramienta()  # restaurar puede rehacer las filas: no se deja una zona a medias
        self._timer_historial.stop()
        self._registrar_historial()
        indice = max(0, min(indice, len(self._historial) - 1))
        if indice == self._pos_historial:
            return
        self._pos_historial = indice
        self._restaurar(self._historial[indice][1])
        self._sesion_cambiada()

    def deshacer(self) -> None:
        if self._transformando is not None:
            self._salir_transformar("cancelar")  # lo transformado todavía no es un paso: se descarta
            return
        if self.vista.pintando:
            self.vista.deshacer_trazo()  # mientras se pinta, Ctrl+Z quita el último trazo
            return
        self._timer_historial.stop()
        self._registrar_historial()  # lo que estaba sin registrar también se puede rehacer
        if self._pos_historial > 0:
            self.ir_al_historial(self._pos_historial - 1)

    def rehacer(self) -> None:
        if self._transformando is not None:
            self._salir_transformar("cancelar")
            return
        if self.vista.pintando:
            return
        if self._pos_historial < len(self._historial) - 1:
            self.ir_al_historial(self._pos_historial + 1)

    # ============================================================ recorte
    def _aspecto(self) -> Optional[float]:
        valor = self.combo_aspecto.currentData()
        if valor == "original" and self._imagen is not None:
            w, h = self._tam_base()  # la proporción de la foto tal como se ve (girada)
            return w / h
        return valor

    def _tam_base(self) -> tuple[int, int]:
        """(ancho, alto) a resolución completa de la foto base: la original con la geometría."""
        return tamano_resultante(self._imagen.ancho, self._imagen.alto, self._geometria)

    def _alternar_recorte(self, activo: bool) -> None:
        if activo:
            if self._imagen is None or self._antes_completo is None:
                self.boton_recortar.setChecked(False)
                return
            if self._transformando is not None:
                self._salir_transformar("aplicar")  # otra herramienta: lo transformado queda
            self.cancelar_herramienta()
            self._modo_recorte = True
            self.barra_recorte.show()
            # Se muestra la foto completa (girada, sin recortar) para poder elegir cualquier parte.
            # Con objetos borrados, ya sin ellos (en chico alcanza para elegir el encuadre).
            completo = self._antes_completo
            if self.panel_borrar.estado() and self._base_completa is not None and self._transformacion is not None:
                chica, _ = reducir_para_vista(self._base_completa, 2048)
                alpha = None
                if self._imagen.alpha is not None:
                    import cv2
                    alpha = con_geometria(self._imagen.alpha, self._geometria, clave=(str(self._imagen.ruta), "alfa"))
                    alpha = cv2.resize(alpha, (chica.shape[1], chica.shape[0]), interpolation=cv2.INTER_AREA)
                completo = a_qimage(self._transformacion.a_srgb(chica), alpha)
            self.vista.establecer_imagenes(completo, completo, self._tam_base())
            self.vista.establecer_superposiciones([])
            inicial = None
            if self._recorte is not None:
                r = self._recorte.normalizado()
                inicial = QRectF(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0)
            self._fijar_aspecto_medida()
            self.vista.establecer_herramienta("recorte", aspecto=self._aspecto(), inicial=inicial)
        elif self._modo_recorte:
            self._salir_recorte("cancelar")

    def _salir_recorte(self, accion: str, recalcular: bool = True) -> None:
        if not self._modo_recorte:
            return
        seleccion = self.vista.seleccion_normalizada()
        self._modo_recorte = False
        self.vista.establecer_herramienta(None)
        self.barra_recorte.hide()
        self.boton_recortar.blockSignals(True)
        self.boton_recortar.setChecked(False)
        self.boton_recortar.blockSignals(False)
        nuevo = self._recorte
        if accion == "aplicar" and seleccion is not None and seleccion.width() > 0.01 and seleccion.height() > 0.01:
            nuevo = Recorte(seleccion.left(), seleccion.top(), seleccion.right(), seleccion.bottom()).normalizado()
            if nuevo.es_completo():
                nuevo = None
        elif accion == "quitar":
            nuevo = None
        if self._medida is not None and self._imagen is not None and accion in ("aplicar", "quitar"):
            # Con una medida, el recorte tiene su proporción (la del recuadro, que ya la tenía fija;
            # "Quitar" vuelve al centrado más grande, porque sin recorte la medida no entra).
            nuevo = md.recorte_con_medida(nuevo, *self._tam_base(), self._medida)
        cambio = nuevo != self._recorte
        if cambio and self._imagen is not None and self._documento is not None:
            # Las capas siguen sobre el mismo lugar de la foto (el documento cambia de marco).
            w0, h0 = self._imagen.ancho, self._imagen.alto
            m = dc.matriz_marco(w0, h0, self._geometria, self._recorte, self._geometria, nuevo)
            self._documento = dc.convertir_documento(self._documento, self._almacen, m,
                                                     *dc.tamano_documento(w0, h0, self._geometria, nuevo))
            self._refrescar_panel_capas()
        self._recorte = nuevo
        if recalcular:
            self._recalcular_fuentes()
        if cambio:
            self._registrar_historial()

    # ============================================================ medida de salida
    def _ayuda_medida(self) -> str:
        if self._medida is None:
            return ("Medida de salida: elegí dónde vas a usar la foto (historia del celular, PC, YouTube, Instagram…) "
                    "y se exporta exacta en esos píxeles. Pone un recorte con esa proporción: lo movés con Recortar.")
        w, h = self._medida
        return (f"La foto sale a {w} × {h} px ({md.texto_medida(self._medida)}). Tocá para elegir otra medida, u "
                "Original para dejar el tamaño de la foto. Con Recortar movés el recuadro (la proporción queda fija).")

    def _medida_vista(self) -> Optional[tuple[int, int]]:
        """La medida para la vista previa. En el modo Photoshop no: ahí se edita la foto a su tamaño (la
        exportación sí la usa, desde cualquier modo)."""
        if self._modo == PHOTOSHOP or self._imagen is None or self.es_documento_sin_foto():
            return None
        return self._medida

    def _abrir_menu_medida(self) -> None:
        if self._imagen is None or self.es_documento_sin_foto():
            return
        self.menu_medida.abrir_debajo(self.boton_medida, self._medida)

    def elegir_medida(self, tam) -> None:
        """Elige la Medida de salida de esta foto (``tam``: (ancho, alto), o None = Original). Un paso
        del historial.

        * Sin recorte: uno centrado con esa proporción, el más grande que entra (el no destructivo de
          siempre: se ve enseguida y se mueve con Recortar).
        * Con un recorte de otra proporción: la nueva alrededor de su centro, dentro de la foto; con la
          misma, queda.
        * Original: quita la medida (el recorte queda como esté).
        """
        if self._imagen is None or self.es_documento_sin_foto():
            return
        tam = md.medida_valida(tam)
        if self._transformando is not None:
            self._salir_transformar("aplicar")
        if self._modo_recorte:
            self._salir_recorte("cancelar")
        if self._modo_enderezar:
            self._salir_enderezar("cancelar")
        self._timer_historial.stop()
        self._registrar_historial()  # lo pendiente queda como su propio paso
        previa = self._medida
        if tam == previa:
            return
        nuevo = self._recorte
        if tam is not None:
            nuevo = md.recorte_con_medida(self._recorte, *self._tam_base(), tam, previa)
        self._medida = tam
        self._cambiar_recorte(nuevo)
        self._actualizar_medida()
        self._registrar_historial("Medida: " + md.texto_medida(tam))

    def _cambiar_recorte(self, nuevo: Optional[Recorte]) -> None:
        """Pone otro recorte (las capas siguen sobre el mismo lugar de la foto, como en ``_salir_recorte``)
        y vuelve a armar la foto; si es el mismo, solo vuelve a procesar (cambió la medida)."""
        if nuevo == self._recorte:
            self.solicitar_render()
            return
        if self._documento is not None:
            w0, h0 = self._imagen.ancho, self._imagen.alto
            m = dc.matriz_marco(w0, h0, self._geometria, self._recorte, self._geometria, nuevo)
            self._documento = dc.convertir_documento(self._documento, self._almacen, m,
                                                     *dc.tamano_documento(w0, h0, self._geometria, nuevo))
            self._refrescar_panel_capas()
        self._recorte = nuevo
        self._recalcular_fuentes()

    def _actualizar_medida(self) -> None:
        """El botón Medida (su texto y el resaltado) y la cabecera de la vista ("Sale a 1080 × 1920")."""
        if not hasattr(self, "boton_medida"):
            return
        m = self._medida
        texto = " " + md.texto_boton(m)
        self.boton_medida.setProperty("texto", texto)
        self.boton_medida.setText(texto)
        activo = m is not None
        if bool(self.boton_medida.property("activo")) != activo:
            self.boton_medida.setProperty("activo", activo)
            self.boton_medida.style().unpolish(self.boton_medida)
            self.boton_medida.style().polish(self.boton_medida)
        if not self.es_documento_sin_foto():
            self.boton_medida.setToolTip(self._ayuda_medida())
        self.etiqueta_medida.setVisible(activo)
        if activo:
            self.etiqueta_medida.setText(f"Sale a {m[0]} × {m[1]}")  # _compactar_barra lo acorta si hace falta
            self.etiqueta_medida.setToolTip(f"Al exportar, la foto sale exacta a {m[0]} × {m[1]} px "
                                            f"({md.texto_medida(m)}). Se cambia con Medida, en la barra de arriba.")
        self._compactar_barra()

    def _fijar_aspecto_medida(self) -> None:
        """Al recortar con una medida, el recuadro tiene su proporción: el combo la muestra y queda fijo."""
        combo = self.combo_aspecto
        if self._medida is None:
            combo.setEnabled(True)
            combo.setToolTip("Proporción del recorte")
            return
        a = self._medida[0] / self._medida[1]
        indice = next((i for i in range(combo.count()) if isinstance(combo.itemData(i), float)
                       and abs(combo.itemData(i) - a) < 1e-6), -1)
        combo.blockSignals(True)
        if indice < 0:  # una medida sin su proporción en la lista (no pasa con las del menú)
            combo.addItem(md.texto_boton(self._medida).split(" · ")[0], a)
            indice = combo.count() - 1
        combo.setCurrentIndex(indice)
        combo.blockSignals(False)
        combo.setEnabled(False)
        combo.setToolTip(f"La proporción la fija la Medida ({md.texto_boton(self._medida)}). Para cambiarla, "
                         "elegí otra medida u Original.")

    def _encuadres_lote(self, rutas) -> dict:
        """Para "Procesar varias fotos…": de las elegidas que están en la tira con una Medida, su giro, su
        recorte y la medida (``procesar_lote`` las encuadra y las lleva a la medida antes del filtro).
        Las demás salen como siempre."""
        encuadres = {}
        for ruta in rutas:
            indice = next((i for i, f in enumerate(self._fotos)
                           if not dc.es_ruta_documento(f.ruta) and self._misma_ruta(f.ruta, str(ruta))), None)
            if indice is None:
                continue
            vivo = indice == self._actual and self._imagen is not None
            estado = self._estado_completo() if vivo else self._fotos[indice].estado
            medida = md.medida_valida((estado or {}).get("medida"))
            if medida is not None:
                encuadres[str(ruta)] = (estado.get("geometria") or Geometria(), estado.get("recorte"), medida)
        return encuadres

    def _recalcular_fuentes(self) -> None:
        """Arma en segundo plano la foto que entra al filtro y vuelve a procesar:

            original → geometría → montaje → borrar objetos → recorte

        Todo a resolución completa (la vista previa es una reducción de eso, así que
        coincide con la exportación) y con caché en cada paso. "Antes" muestra la
        foto sin los borrados, para comparar. El desenfoque de fondo va después, al
        procesar (``con_desenfoque``): así la vista rápida lo calcula sobre la copia
        reducida y responde al instante.
        """
        if self._imagen is None:
            return
        self._generacion_fuentes += 1
        imagen, recorte, transformacion = self._imagen, self._recorte, self._transformacion
        geo = self._geometria
        montaje = self.panel_montaje.estado()
        borrados = self.panel_borrar.estado()
        original = self._antes_original
        previo = getattr(self, "_completo_cache", None)
        cacheadas = {f.ruta: f.imagen for f in self._fotos if f.imagen is not None}
        ruta = str(imagen.ruta)
        clave_completo = (ruta, geo, montaje)

        def cargar_otra(otra_ruta: str) -> np.ndarray:
            # La otra foto se gira igual que la base; la alineación corrige lo que falte.
            otra = cacheadas.get(otra_ruta)
            otra = otra if otra is not None else cargar_imagen(otra_ruta)
            return con_geometria(otra.rgb, geo, clave=("otra", otra_ruta))

        def trabajo(cancelado):
            base = con_geometria(imagen.rgb, geo, clave=(ruta, "rgb"))
            alpha = None if imagen.alpha is None else con_geometria(imagen.alpha, geo, clave=(ruta, "alfa"))
            avisos = []
            if montaje:
                # El montaje va antes del filtro: el ruido y el grano quedan parejos encima.
                base, avisos = componer(base, montaje, cargar_otra, f"{ruta}|{geo}")
            sin_borrar = base
            if borrados:
                base = aplicar_borrados(sin_borrar, borrados, clave=(ruta, geo, montaje), cancelado=cancelado)
            if geo.es_identidad() and not montaje and original is not None:
                completo = original
            elif previo is not None and previo[0] == clave_completo:
                completo = previo[1]
            else:
                completo = a_qimage(transformacion.a_srgb(sin_borrar), alpha)
            fuente = np.ascontiguousarray(aplicar_recorte(base, recorte))
            alpha_r = None if alpha is None else np.ascontiguousarray(aplicar_recorte(alpha, recorte))
            if recorte is None:
                antes = completo
            else:
                antes = a_qimage(transformacion.a_srgb(np.ascontiguousarray(aplicar_recorte(sin_borrar, recorte))),
                                 alpha_r)
            vista_previa, escala = reducir_para_vista(fuente, LADO_VISTA_PREVIA)
            return {"imagen": imagen, "geo": geo, "recorte": recorte, "montaje": montaje, "borrados": borrados,
                    "fuente": fuente, "alpha": alpha_r, "antes": antes, "vista_previa": vista_previa,
                    "escala": escala, "completo": completo, "clave_completo": clave_completo, "base": base,
                    "avisos": avisos}

        self._fuentes_pendientes = True
        self._ocupado()
        generacion = self._generacion_fuentes
        self._pool_archivos.start(Tarea("fuentes", generacion, trabajo, self._senales,
                                        lambda: self._generacion_fuentes))

    def _fuentes_listas(self, r: dict) -> None:
        if (r["imagen"] is not self._imagen or r["recorte"] != self._recorte or r["geo"] != self._geometria
                or r["montaje"] != self.panel_montaje.estado() or r["borrados"] != self.panel_borrar.estado()
                or self._modo_recorte or self._modo_enderezar):
            return
        imagen, fuente = r["imagen"], r["fuente"]
        self._antes_completo = r["completo"]
        self._completo_cache = (r["clave_completo"], r["completo"])
        if r["avisos"]:
            self.etiqueta_estado.setText("  ·  ".join(r["avisos"]))
        self._fuente, self._alpha_fuente = fuente, r["alpha"]
        self._base_completa = r["base"]
        self._clave_base = (str(imagen.ruta), r["geo"], r["montaje"], r["borrados"])
        self._version_fuente += 1
        self._antes_actual = r["antes"]
        self._vista_previa, self._escala_vista_previa = r["vista_previa"], r["escala"]
        self._clave_vista_previa = (self._clave_base, r["recorte"])
        self._resultado_completo = None
        h, w = fuente.shape[:2]
        if dc.es_trivial(self._documento):
            self._documento = dc.documento_nuevo(w, h)  # sin capas, el documento sigue el tamaño de la foto
        self._refrescar_panel_capas(miniatura=True)
        self.vista.establecer_imagenes(r["antes"], None, (w, h))
        notas = [n for n, si in (("recortada", r["recorte"] is not None),
                                 ("girada", not r["geo"].es_identidad())) if si]
        self.pie_detalle.setText(f"{w} × {h} px" + "".join(f"  · {n}" for n in notas) +
                                 f" · {imagen.nombre_perfil}")
        self._actualizar_superposiciones()
        self.solicitar_render()
        self.panel_facil.fuente_cambiada()

    def _al_cambiar_fondo(self) -> None:
        if self._restaurando:
            return
        self._timer_historial.start()
        self._actualizar_superposiciones()
        self.solicitar_render()

    def _al_cambiar_montaje(self) -> None:
        if self._restaurando:
            return
        self._timer_historial.start()
        self._actualizar_superposiciones()
        self._timer_montaje.start()

    def _al_cambiar_borrado(self) -> None:
        if self._restaurando:
            return
        if self._clon is not None and hasattr(self._clon, "renumerar") and self._clon not in self.panel_borrar.filas():
            self._cerrar_clon()  # se quitó la fila cuya fuente se estaba eligiendo
        self._timer_historial.start()
        self._actualizar_superposiciones()
        self._recalcular_fuentes()

    # ============================================================ geometría
    def girar(self, pasos: int) -> None:
        """Gira la foto ``pasos`` cuartos de vuelta (positivo = horario), sin tocar el original. En un
        documento sin foto, gira el lienzo (``documento.rotar_lienzo``: trabaja sobre la composición)."""
        if self.es_documento_sin_foto():
            grados = (90 * int(pasos)) % 360
            if grados:
                self.photoshop.rotar(grados)
            return
        self._cambiar_geometria(self._geometria.girada(pasos))

    def voltear(self, horizontal: bool = True) -> None:
        """Espejo de la foto tal como se ve (horizontal: izquierda-derecha). En un documento sin foto,
        voltea el lienzo (``documento.voltear_lienzo``)."""
        if self.es_documento_sin_foto():
            self.photoshop.voltear("h" if horizontal else "v")
            return
        self._cambiar_geometria(self._geometria.volteada(horizontal))

    def _cambiar_geometria(self, nueva: Geometria) -> None:
        """Pasa a otra geometría: zonas, recorte y borrados se convierten para seguir sobre
        lo mismo, y queda un solo paso en el historial."""
        if self._imagen is None or nueva == self._geometria:
            return
        self.cancelar_herramienta()
        self._timer_historial.stop()
        self._registrar_historial()  # lo pendiente queda como su propio paso
        estado = estado_con_geometria(self._estado_completo(), nueva, self._imagen.ancho, self._imagen.alto,
                                      self._almacen)
        self._restaurar(estado)
        self._registrar_historial()

    def _alternar_enderezar(self, activo: bool) -> None:
        if activo:
            if self._imagen is None or self._transformacion is None:
                self._marcar_boton(self.boton_enderezar, False)
                return
            if self._transformando is not None:
                self._salir_transformar("aplicar")  # otra herramienta: lo transformado queda
            self.cancelar_herramienta()
            self._modo_enderezar = True
            # Base chica ya girada y volteada (sin enderezar) y en sRGB: así el
            # deslizador responde al instante. El enderezado se calcula encima.
            chica, _ = reducir_para_vista(self._imagen.rgb, LADO_VISTA_PREVIA)
            chica = self._transformacion.a_srgb(chica)
            self._enderezar_fuente = aplicar_geometria(chica, replace(self._geometria, enderezar=0.0))
            self.slider_angulo.blockSignals(True)
            self.numero_angulo.blockSignals(True)
            self.slider_angulo.setValue(round(self._geometria.enderezar * 10))
            self.numero_angulo.setValue(self._geometria.enderezar)
            self.slider_angulo.blockSignals(False)
            self.numero_angulo.blockSignals(False)
            self.barra_enderezar.show()
            self.vista.establecer_superposiciones([])
            self.vista.establecer_cuadricula(self.boton_cuadricula.isChecked())
            self._previsualizar_enderezado()
            self.vista.establecer_herramienta("enderezar")
            self.etiqueta_estado.setText("Enderezar: mové el deslizador o tocá «Nivelar automático»  ·  "
                                         "Enter aplica, Esc cancela")
        elif self._modo_enderezar:
            self._salir_enderezar("cancelar")

    def _angulo_enderezar(self) -> float:
        return self.slider_angulo.value() / 10.0

    def _al_mover_angulo(self, valor: int) -> None:
        self.numero_angulo.blockSignals(True)
        self.numero_angulo.setValue(valor / 10.0)
        self.numero_angulo.blockSignals(False)
        if self._modo_enderezar:
            self._previsualizar_enderezado()

    def _previsualizar_enderezado(self) -> None:
        """Muestra la foto enderezada (recortada para que no queden esquinas vacías).

        El marco de la vista queda fijo: al enderezar más, la foto se ve un poco más
        grande, como en el celular, y no se pierde el zoom ni el desplazamiento."""
        if self._enderezar_fuente is None:
            return
        import cv2
        angulo = self._angulo_enderezar()
        img = aplicar_geometria(self._enderezar_fuente, Geometria(enderezar=angulo), interpolacion=cv2.INTER_LINEAR)
        qimagen = a_qimage(img)
        marco = tamano_resultante(self._imagen.ancho, self._imagen.alto, replace(self._geometria, enderezar=0.0))
        self.vista.establecer_imagenes(qimagen, qimagen, marco)

    def nivelar_automatico(self) -> None:
        """Endereza sola la foto con el horizonte y las líneas rectas (``detectar_horizonte``)."""
        if not self._modo_enderezar or self._enderezar_fuente is None:
            return
        angulo = detectar_horizonte(self._enderezar_fuente)
        if angulo is None:
            self.etiqueta_estado.setText("No encontré un horizonte ni líneas rectas claras: enderezala con el "
                                         "deslizador.")
            return
        self.slider_angulo.setValue(round(angulo * 10))
        texto = "ya estaba derecha" if abs(angulo) < 0.05 else f"{angulo:+.1f}°".replace(".", ",")
        self.etiqueta_estado.setText(f"Nivelado automático: {texto}. Revisalo con la cuadrícula y tocá Aplicar.")

    def _salir_enderezar(self, accion: str, recalcular: bool = True) -> None:
        if not self._modo_enderezar:
            return
        angulo = self._angulo_enderezar()
        self._modo_enderezar = False
        self._enderezar_fuente = None
        self.vista.establecer_herramienta(None)
        self.barra_enderezar.hide()
        self._marcar_boton(self.boton_enderezar, False)
        if self._imagen is not None:
            self.etiqueta_estado.setText(self._texto_imagen)
        if accion == "aplicar" and abs(angulo - self._geometria.enderezar) > 1e-6:
            self._cambiar_geometria(replace(self._geometria, enderezar=angulo))
        elif recalcular:
            self._recalcular_fuentes()  # vuelve a mostrar la foto como estaba (sale de la caché)

    @staticmethod
    def _marcar_boton(boton: QPushButton, marcado: bool) -> None:
        boton.blockSignals(True)
        boton.setChecked(marcado)
        boton.blockSignals(False)

    def _confirmar_herramienta(self) -> None:
        """Enter sobre la foto: aplica el recorte, el enderezado, la transformación o el clonado."""
        if self._modo_recorte:
            self._salir_recorte("aplicar")
        elif self._modo_enderezar:
            self._salir_enderezar("aplicar")
        elif self._transformando is not None:
            self._salir_transformar("aplicar")
        elif self.photoshop.recortando:
            self.photoshop.terminar_recorte(True)
        elif self._clon is not None:
            self._clon_listo()

    # ============================================================== zonas
    # Un "destino" de zona es cualquier cosa que espera una zona marcada en la foto:
    # una capa, una foto del montaje, el objeto de Fondo o un borrado. Tiene ``nombre``,
    # ``zona``, ``establecer_zona(zona)`` y ``zona_cancelada()``; si además tiene
    # ``pluma`` (deslizador) y ``check_invertir``, la zona nueva toma esos valores.
    @staticmethod
    def _pluma_inicial(destino, previa: Optional[Zona]) -> int:
        if previa is not None:
            return previa.pluma
        pluma = getattr(destino, "pluma", None)
        return pluma.valor() if pluma is not None else 12

    @staticmethod
    def _invertir_inicial(destino, previa: Optional[Zona]) -> bool:
        if previa is not None:
            return previa.invertir
        casilla = getattr(destino, "check_invertir", None)
        return casilla.isChecked() if casilla is not None else False

    @staticmethod
    def _zona_cancelada(destino) -> None:
        cancelar = getattr(destino, "zona_cancelada", None)
        if cancelar is not None:
            try:
                cancelar()
            except RuntimeError:
                pass  # la fila ya no existe (se rehízo el panel)

    def _pedir_zona(self, fila, forma: str) -> None:
        if self._imagen is None:
            self._zona_cancelada(fila)
            QMessageBox.information(self, "Primero abrí una foto", "Abrí una foto para marcar la zona sobre ella.")
            return
        if self._transformando is not None:
            self._salir_transformar("aplicar")  # otra herramienta: lo transformado queda
        if forma in ("cielo", "piel"):
            self._detectar(fila, forma)
            return
        if self._modo_recorte:
            self._salir_recorte("cancelar")
        if self._modo_enderezar:
            self._salir_enderezar("cancelar")
        if self._deteccion is not None:
            self._cancelar_deteccion()
        if self._clon is not None:
            self._cancelar_clon()
        if self._capa_zona is not None and self._capa_zona is not fila:
            self._zona_cancelada(self._capa_zona)
        self._capa_zona = fila
        self.vista.establecer_superposiciones([])
        if forma == "pincel":
            # Se sigue pintando sobre lo que ya estaba (si la zona ya era pintada). Sobre una
            # máscara automática (cielo, piel, contorno), la máscara es la base y los trazos
            # suman o restan.
            previa = fila.zona
            previos = self._trazos_a_vista(previa.trazos) if previa is not None and previa.es_raster else ()
            base = None
            if previa is not None and previa.es_mascara:
                w, h = self._tam_mostrado()
                f = min(1.0, 1600 / max(w, h))
                base = mascara_zona(replace(previa, trazos=(), invertir=False),
                                    max(1, round(h * f)), max(1, round(w * f)), self._recorte)
            self.vista.establecer_herramienta("zona", forma=forma, trazos=previos, base=base)
            self._sincronizar_pincel()
            self.barra_pincel.show()
        else:
            self.barra_pincel.hide()
            self.vista.establecer_herramienta("zona", forma=forma)
        instrucciones = {
            "lazo": "Mantené apretado y dibujá el contorno; al soltar se cierra",
            "poligono": "Hacé clic punto por punto; cerrá con doble clic, Enter o tocando el primer punto",
            "pincel": "Pintá donde va; clic derecho borra, Ctrl+Z quita el último trazo y Enter termina",
        }.get(forma, "Arrastrá sobre la foto para marcar la zona")
        if getattr(fila, "instrucciones", None):
            instrucciones = fila.instrucciones
        self.etiqueta_estado.setText(f"{fila.nombre}: {instrucciones}  ·  Esc para cancelar")

    def _sincronizar_pincel(self) -> None:
        """Pone la barra del pincel igual que el pincel de la vista."""
        tam, dureza, goma = self.vista.pincel
        for clave, valor in (("tam", tam), ("dureza", dureza)):
            for sliders in (self.sliders_pincel, getattr(self, "sliders_pincel_ps", {})):
                slider = sliders.get(clave)
                if slider is None:
                    continue
                slider.blockSignals(True)
                slider.setValue(valor)
                slider.blockSignals(False)
        self.boton_goma.blockSignals(True)
        self.boton_goma.setChecked(goma)
        self.boton_goma.blockSignals(False)

    def _tam_mostrado(self) -> tuple[int, int]:
        """(ancho, alto) a resolución completa de la foto mostrada: la base recortada."""
        w, h = self._tam_base()
        if self._recorte is None:
            return w, h
        x0, y0, x1, y1 = self._recorte.pixeles(w, h)
        return x1 - x0, y1 - y0

    def _marco_vista(self) -> tuple[Optional[Recorte], float]:
        """(recorte normalizado, lado largo de la foto base / lado largo de la mostrada)."""
        r = self._recorte.normalizado() if self._recorte is not None else None
        w, h = self._tam_mostrado()
        return r, max(self._tam_base()) / max(w, h, 1)

    def _trazos_a_vista(self, trazos) -> tuple:
        """Trazos del pincel: de la foto base a la foto mostrada (recortada)."""
        r, escala = self._marco_vista()
        salida = []
        for pts, radio, dureza, borrar in trazos:
            if r is not None:
                aw, ah = max(r.x1 - r.x0, 1e-6), max(r.y1 - r.y0, 1e-6)
                pts = tuple(((x - r.x0) / aw, (y - r.y0) / ah) for x, y in pts)
            salida.append((pts, radio * escala, dureza, borrar))
        return tuple(salida)

    def _a_base(self, puntos) -> list:
        """Puntos normalizados de la foto mostrada (recortada) a la foto base completa."""
        if self._recorte is None:
            return [(float(x), float(y)) for x, y in puntos]
        r = self._recorte.normalizado()
        aw, ah = r.x1 - r.x0, r.y1 - r.y0
        return [(r.x0 + x * aw, r.y0 + y * ah) for x, y in puntos]

    def _trazos_terminados(self, nuevos: list) -> None:
        """Listo con el pincel: los trazos nuevos se suman a lo que ya estaba pintado."""
        if self.vista.herramienta != "zona" or self._capa_zona is None:
            return
        fila, previa = self._capa_zona, self._capa_zona.zona
        _r, escala = self._marco_vista()
        convertidos = tuple((tuple(self._a_base(pts)), radio / escala, dureza, borrar)
                            for pts, radio, dureza, borrar in nuevos)
        w, h = self._tam_base()
        if previa is not None and previa.es_mascara:
            # Corrección de una máscara automática: sigue siendo la máscara, con los trazos encima.
            if not convertidos:
                self.cancelar_herramienta()
                return
            pintado = Zona.desde_trazos(previa.trazos + convertidos, aspecto=w / h)
            zona = replace(previa, trazos=previa.trazos + convertidos,
                           x0=min(previa.x0, pintado.x0), y0=min(previa.y0, pintado.y0),
                           x1=max(previa.x1, pintado.x1), y1=max(previa.y1, pintado.y1))
        else:
            previos = previa.trazos if previa is not None and previa.es_pincel else ()
            trazos = previos + convertidos
            if not convertidos or all(borrar for *_resto, borrar in trazos):
                self.cancelar_herramienta()  # nada nuevo (o nada pintado): queda la zona que había
                return
            zona = Zona.desde_trazos(trazos, pluma=self._pluma_inicial(fila, previa),
                                     invertir=self._invertir_inicial(fila, previa), aspecto=w / h)
        self._cerrar_herramienta_zona()
        fila.establecer_zona(zona)

    def _cerrar_herramienta_zona(self) -> None:
        self._capa_zona = None
        self.vista.establecer_herramienta(None)
        self.barra_pincel.hide()
        self.photoshop.reponer_herramienta()  # en Photoshop vuelve la herramienta de antes (Mover…)
        if self._imagen is not None:
            self.etiqueta_estado.setText(self._texto_imagen)

    def _seleccion_terminada(self, rn: QRectF) -> None:
        if self.vista.herramienta != "zona" or self._capa_zona is None:
            return  # en el recorte, la selección se confirma con "Aplicar"
        fila, forma = self._capa_zona, self.vista._forma
        # De coordenadas de la foto mostrada (recortada) a las de la foto base.
        (x0, y0), (x1, y1) = self._a_base([(rn.left(), rn.top()), (rn.right(), rn.bottom())])
        previa = fila.zona
        zona = Zona(forma, x0, y0, x1, y1, pluma=self._pluma_inicial(fila, previa),
                    invertir=self._invertir_inicial(fila, previa))
        self._cerrar_herramienta_zona()
        fila.establecer_zona(zona)

    def _forma_terminada(self, puntos: list) -> None:
        """Se cerró un lazo: se guarda como zona (en coordenadas de la foto base)."""
        if self.vista.herramienta != "zona" or self._capa_zona is None:
            return
        fila, forma = self._capa_zona, self.vista._forma
        previa = fila.zona
        zona = Zona.desde_puntos(forma, self._a_base(puntos), pluma=self._pluma_inicial(fila, previa),
                                 invertir=self._invertir_inicial(fila, previa))
        self._cerrar_herramienta_zona()
        fila.establecer_zona(zona)

    def _herramienta_activa(self) -> bool:
        return (self._modo_recorte or self._modo_enderezar or self._capa_zona is not None
                or self._deteccion is not None or self._clon is not None or self._transformando is not None
                or self.photoshop.recortando)

    def cancelar_herramienta(self) -> None:
        """Esc: cancela lo que esté en curso (recorte, enderezado, transformación, zona, detección o clonado)."""
        if self.photoshop.cancelar_gesto():  # un trazo de pincel o un degradado que se arrastra
            return
        if self._modo_recorte:
            self._salir_recorte("cancelar")
            return
        if self._modo_enderezar:
            self._salir_enderezar("cancelar")
            return
        if self._transformando is not None:
            self._salir_transformar("cancelar")
            return
        if self.photoshop.recortando:
            self.photoshop.terminar_recorte(False)
            return
        if self._deteccion is not None:
            self._cancelar_deteccion()
        if self._clon is not None:
            self._cancelar_clon()
        if self._capa_zona is not None:
            self._zona_cancelada(self._capa_zona)
            self._cerrar_herramienta_zona()
            self._actualizar_superposiciones()

    # ============================================================ selección automática
    def _detectar(self, destino, tipo: str, inicial=None) -> None:
        """Cielo, piel o "ajustar al contorno" en segundo plano, con "Detectando…" en la vista.

        Se calcula sobre la foto base completa (girada, con montaje y borrados, sin
        recortar) y se guarda como zona "mascara". Se cachea por foto y selección
        inicial: volver a elegir lo mismo es instantáneo.
        """
        if self._imagen is None:
            return
        if self._modo_recorte:
            self._salir_recorte("cancelar")
        if self._modo_enderezar:
            self._salir_enderezar("cancelar")
        if self._capa_zona is not None:
            self._zona_cancelada(self._capa_zona)
            self._cerrar_herramienta_zona()
        if self._clon is not None:
            self._cancelar_clon()
        if self._deteccion is not None:
            self._cancelar_deteccion()
        base = self._base_completa if self._base_completa is not None else self._imagen.rgb
        clave = (self._clave_base, tipo, inicial)
        guardada = self._cache_detecciones.get(clave)
        if guardada is not None:
            self._cache_detecciones.move_to_end(clave)
            zona, alta = guardada
            if alta is not None:
                registrar_mascara(zona.datos, alta)
            self._aplicar_deteccion(destino, tipo, zona)
            return
        self._generacion_deteccion += 1
        generacion = self._generacion_deteccion
        self._deteccion = (destino, tipo, generacion)
        if tipo == "contorno":
            self.panel_fondo.establecer_detectando(True)
        self.etiqueta_estado.setText(TEXTO_DETECCION[tipo] + "  ·  Esc para cancelar")
        self._ocupado()

        def trabajo(_cancelado):
            if tipo == "cielo":
                m = mascara_cielo(base)
            elif tipo == "piel":
                m = mascara_piel(base)
            else:
                if isinstance(inicial, Zona):
                    # La selección aproximada (lazo, pincel...) en chico alcanza como punto de partida.
                    h, w = base.shape[:2]
                    f = min(1.0, LADO_INICIAL_CONTORNO / max(h, w))
                    aprox = mascara_zona(inicial, max(1, round(h * f)), max(1, round(w * f)))
                else:
                    aprox = inicial
                m = recortar_objeto(base, aprox)
            if float(m.max()) < 0.5:
                return clave, None
            return clave, Zona.desde_mascara(m, origen=tipo)

        self._pool_deteccion.start(Tarea("deteccion", generacion, trabajo, self._senales,
                                         lambda: self._generacion_deteccion))

    def _deteccion_lista(self, resultado) -> None:
        destino, tipo, _generacion = self._deteccion
        clave, zona = resultado
        self._terminar_deteccion()
        if zona is None:
            self._zona_cancelada(destino)
            self.etiqueta_estado.setText(SIN_DETECCION[tipo])
            QMessageBox.information(self, "Selección automática", SIN_DETECCION[tipo])
            return
        self._cache_detecciones[clave] = (zona, mascara_registrada(zona.datos))
        while len(self._cache_detecciones) > 4:
            self._cache_detecciones.popitem(last=False)
        if clave[0] != self._clave_base:
            # La foto base cambió mientras se detectaba (por ejemplo, se giró): se vuelve a calcular.
            self._detectar(destino, tipo, clave[2])
            return
        self._aplicar_deteccion(destino, tipo, zona)

    def _destino_vigente(self, destino) -> bool:
        """Si la fila que pidió la zona todavía existe (se puede haber quitado la capa)."""
        return (destino is self.panel_fondo or destino in self.panel_ajustes.capas()
                or destino in self.panel_montaje.filas())

    def _aplicar_deteccion(self, destino, tipo: str, zona: Zona) -> None:
        if not self._destino_vigente(destino):
            return
        previa = destino.zona
        zona = replace(zona, invertir=self._invertir_inicial(destino, previa),
                       pluma=previa.pluma if previa is not None else zona.pluma)
        if self._imagen is not None:
            self.etiqueta_estado.setText(self._texto_imagen)
        try:
            destino.establecer_zona(zona)
        except RuntimeError:
            return  # la fila ya no existe

    def _terminar_deteccion(self) -> None:
        if self._deteccion is not None and self._deteccion[1] == "contorno":
            self.panel_fondo.establecer_detectando(False)
        self._deteccion = None
        self._ocupado()

    def _cancelar_deteccion(self) -> None:
        if self._deteccion is None:
            return
        destino = self._deteccion[0]
        self._generacion_deteccion += 1  # el resultado en curso se descarta
        self._terminar_deteccion()
        self._zona_cancelada(destino)
        if self._imagen is not None:
            self.etiqueta_estado.setText(self._texto_imagen)

    def ajustar_al_contorno(self) -> None:
        """Fondo → "Ajustar al contorno": pega la selección al borde real del objeto (GrabCut).

        Parte de lo que ya esté marcado (lazo, pincel o un contorno ajustado antes); si
        no hay nada, primero se arrastra un rectángulo alrededor del objeto."""
        if self._imagen is None:
            QMessageBox.information(self, "Primero abrí una foto", "Abrí una foto para marcar el objeto.")
            return
        zona = self.panel_fondo.zona
        if zona is not None:
            self._detectar(self.panel_fondo, "contorno", replace(zona, invertir=False))
            return
        self._pedir_zona(_RectanguloContorno(self), "rect")

    # ================================================================== clonar
    def _elegir_fuente(self, destino) -> None:
        """Borrar objetos → "Clonar desde…": se arrastra desde la zona hasta la fuente, con vista previa."""
        if self._imagen is None:
            return
        if self._herramienta_activa():
            self.cancelar_herramienta()
        self._clon = destino
        zona = destino.zona
        w, h = self._tam_mostrado()
        f = 480 / max(w, h)
        contornos = contornos_pincel(replace(zona, invertir=False), self._recorte,
                                     max(1, round(h * f)), max(1, round(w * f)))
        borrado = destino.borrado() if hasattr(destino, "borrado") else None
        wb, hb = self._tam_base()
        d = (borrado.dx * wb, borrado.dy * hb) if borrado is not None else (0.0, 0.0)
        if borrado is not None:
            self.check_costuras.setChecked(borrado.sin_costuras)
        # La vista previa copia de la foto con los borrados que ya hay (lo que de verdad se clona).
        imagen = None
        if self._vista_previa is not None and self._transformacion is not None:
            imagen = a_qimage(self._transformacion.a_srgb(self._vista_previa))
        self.vista.establecer_superposiciones([])
        self.vista.establecer_herramienta("clonar", contornos=contornos, desplazamiento=d, imagen_clon=imagen)
        self.barra_pincel.hide()
        self.barra_clon.show()
        self._texto_clon_elegido()
        self.etiqueta_estado.setText(f"{destino.nombre}: arrastrá desde la zona hasta la fuente  ·  "
                                     "Enter confirma, Esc cancela")

    def _texto_clon_elegido(self) -> None:
        dx, dy = self.vista.desplazamiento_clon
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            self.texto_clon.setText("Arrastrá desde la zona hasta lo que querés copiar.")
        else:
            self.texto_clon.setText("Así queda. Arrastrá la fuente para ajustarla.")

    def _clon_listo(self) -> None:
        if self._clon is None:
            return
        dx, dy = self.vista.desplazamiento_clon
        if abs(dx) < 0.5 and abs(dy) < 0.5:
            self.texto_clon.setText("Primero arrastrá desde la zona marcada hasta la parte que querés copiar.")
            return
        wb, hb = self._tam_base()
        destino = self._clon
        self._cerrar_clon()
        try:
            destino.establecer_fuente(dx / wb, dy / hb, self.check_costuras.isChecked())
        except RuntimeError:
            pass  # la fila se quitó mientras se elegía la fuente

    def _cerrar_clon(self) -> None:
        self._clon = None
        self.vista.establecer_herramienta(None)
        self.barra_clon.hide()
        if self._imagen is not None:
            self.etiqueta_estado.setText(self._texto_imagen)
        self._actualizar_superposiciones()

    def _cancelar_clon(self) -> None:
        destino = self._clon
        self._cerrar_clon()
        cancelar = getattr(destino, "fuente_cancelada", None)
        if cancelar is not None:
            try:
                cancelar()
            except RuntimeError:
                pass

    # ============================================================ superposiciones
    def _contornos_zona(self, zona: Zona) -> tuple:
        w, h = self._tam_mostrado()
        f = 480 / max(w, h)
        return contornos_pincel(zona, self._recorte, max(1, round(h * f)), max(1, round(w * f)))

    def _actualizar_superposiciones(self) -> None:
        """Contorno punteado de cada zona (capas, montaje, fondo y borrados) sobre la vista previa."""
        if self._modo == PHOTOSHOP:
            self.vista.establecer_superposiciones([])  # las zonas de los efectos son del Editor
            return
        if self._modo_recorte or self._modo_enderezar or self.vista.herramienta in ("zona", "clonar", "transformar"):
            return
        if self._imagen is None:
            return
        lista = []
        r = self._recorte.normalizado() if self._recorte is not None else None
        for fila in self.panel_ajustes.capas() + self.panel_montaje.filas() + [self.panel_fondo]:
            z = fila.zona
            if z is None:
                continue
            texto = fila.nombre + (" (invertida)" if z.invertir else "")
            if z.es_raster:
                # Zona pintada o automática: se dibuja su contorno (calculado en chico).
                contornos = self._contornos_zona(replace(z, invertir=False))
                if contornos:
                    lista.append((texto, "pincel", self._caja(contornos), list(contornos)))
                continue
            z = z.normalizada()
            x0, y0, x1, y1 = z.x0, z.y0, z.x1, z.y1
            if r is not None:
                aw, ah = max(r.x1 - r.x0, 1e-6), max(r.y1 - r.y0, 1e-6)
                x0, x1 = (x0 - r.x0) / aw, (x1 - r.x0) / aw
                y0, y1 = (y0 - r.y0) / ah, (y1 - r.y0) / ah
            puntos = list(z.puntos) if z.es_libre else []
            if puntos and r is not None:
                puntos = [((x - r.x0) / aw, (y - r.y0) / ah) for x, y in puntos]
            lista.append((texto, z.forma, QRectF(x0, y0, x1 - x0, y1 - y0), puntos))
        # Borrados: la zona y, si se clona, de dónde se copia.
        aw, ah = (r.x1 - r.x0, r.y1 - r.y0) if r is not None else (1.0, 1.0)
        for fila in self.panel_borrar.filas():
            b = fila.borrado()
            contornos = self._contornos_zona(replace(b.zona, invertir=False))
            if not contornos:
                continue
            lista.append((fila.nombre, "pincel", self._caja(contornos), list(contornos)))
            if b.modo == "clonar" and b.listo:
                ddx, ddy = b.dx / max(aw, 1e-6), b.dy / max(ah, 1e-6)
                fuente = [tuple((x + ddx, y + ddy) for x, y in c) for c in contornos]
                lista.append((f"Fuente {fila.numero}", "pincel", self._caja(fuente), fuente))
        self.vista.establecer_superposiciones(lista if self.boton_zonas.isChecked() else [])

    @staticmethod
    def _caja(contornos) -> QRectF:
        xs = [x for c in contornos for x, _y in c]
        ys = [y for c in contornos for _x, y in c]
        return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    # ============================================================ render
    def solicitar_render(self) -> None:
        if self._imagen is None:
            return
        self._generacion += 1
        if self._escala_vista_previa < 1.0:
            self._timer_rapido.start()
            self._timer_completo.start(450)
        else:
            self._timer_completo.start(15)  # imagen chica: directamente a resolución completa
        self._ocupado()

    def _vigente(self) -> int:
        return self._generacion

    def _lanzar_vista_rapida(self) -> None:
        if self._vista_previa is None:
            return
        ajustes, zonas, recorte = self.panel_ajustes.pila(), self.panel_ajustes.zonas(), self._recorte
        rgb, escala, transformacion, alpha = (
            self._vista_previa, self._escala_vista_previa, self._transformacion, self._alpha_fuente,
        )
        fondo = self.panel_fondo.zona_transparente()
        desenfoque = self.panel_fondo.desenfoque()
        doc, almacen, cache = self._documento_vista(), self._almacen, self._cache_rapida
        tam_doc = (self._fuente.shape[1], self._fuente.shape[0]) if self._fuente is not None else (1, 1)
        clave_foto = ("rapida", self._version_fuente)
        con_filtro = self._con_filtro()
        medida = self._medida_vista()

        def render(cancelado):
            salida = procesar_con_capas(rgb, doc, almacen, ajustes, zonas, recorte, desenfoque, escala, tam_doc,
                                        cancelado, cache, clave_foto, con_filtro, medida)
            return a_qimage(transformacion.a_srgb(salida), alpha_con_fondo(alpha, fondo, recorte, *salida.shape[:2]))

        self._pool_rapido.start(Tarea("rapida", self._generacion, render, self._senales, self._vigente))

    def _lanzar_vista_completa(self) -> None:
        if self._imagen is None:
            return
        # La clave incluye el desenfoque de fondo (cambia la foto que entra al filtro) y las capas.
        clave = (self.panel_ajustes.pila(), self.panel_ajustes.zonas(), self._recorte, self.panel_fondo.desenfoque(),
                 self._version_fuente, self._documento_vista(), self._con_filtro(), self._medida_vista())
        imagen, transformacion = self._imagen, self._transformacion
        fuente, alpha = self._fuente, self._alpha_fuente
        previo = self._resultado_completo
        fondo = self.panel_fondo.zona_transparente()
        almacen, cache = self._almacen, self._cache_completa

        def render(cancelado):
            tam = (fuente.shape[1], fuente.shape[0])
            if previo is not None and previo[0] == clave and previo[1].shape == forma_salida(fuente, clave[7]):
                salida = previo[1]
            else:
                if cancelado():
                    return None
                salida = procesar_con_capas(fuente, clave[5], almacen, clave[0], clave[1], clave[2], clave[3], 1.0,
                                            tam, cancelado, cache, ("completa", clave[4]), clave[6], clave[7])
            if cancelado():
                return None
            alpha_vista = alpha_con_fondo(alpha, fondo, clave[2], *salida.shape[:2])
            if dc.fondo_transparente(clave[5]):  # documento sin foto con fondo transparente: el tablero
                salida_vista, alpha_vista = dc.con_alfa_de_documento(clave[5], almacen, salida, not clave[6])
                return clave, salida, a_qimage(salida_vista, alpha_vista), imagen, None
            antes = None
            if clave[6] and not dc.es_trivial(clave[5]):
                # Con capas, el "Antes" de Fácil y Editor es la composición sin el filtro (sale de la caché).
                sin = procesar_con_capas(fuente, clave[5], almacen, clave[0], clave[1], clave[2], clave[3], 1.0,
                                         tam, cancelado, cache, ("completa", clave[4]), False, clave[7])
                antes = a_qimage(transformacion.a_srgb(sin), alpha_vista)
            return clave, salida, a_qimage(transformacion.a_srgb(salida), alpha_vista), imagen, antes

        self._pool_completo.start(Tarea("completa", self._generacion, render, self._senales, self._vigente))

    def _tarea_terminada(self, tipo: str, generacion: int, resultado) -> None:
        if tipo == "carga":
            if generacion == self._generacion_carga:
                self._imagen_cargada(resultado)
            return
        if tipo == "exportacion":
            self._exportacion_terminada(resultado)
            return
        if tipo == "fuentes":
            if generacion == self._generacion_fuentes:
                self._fuentes_pendientes = False
                self._fuentes_listas(resultado)
                self._ocupado()
            return
        if tipo == "deteccion":
            if self._deteccion is not None and generacion == self._deteccion[2]:
                self._deteccion_lista(resultado)
            return
        if tipo == "miniatura":
            self._miniatura_lista(resultado)
            return
        if tipo == "sesion_cargada":
            self._sesion_cargada(resultado)
            return
        if tipo == "sesion_guardada":
            return
        if tipo == "capa_cargada":
            self.photoshop.capas_cargadas(resultado)  # descarta solo si ya es otra foto (lo mira adentro)
            return
        if tipo == "fondo_quitado":
            self.photoshop.fondo_quitado(resultado)
            return
        if tipo == "proyecto_abierto":
            self._proyecto_abierto(resultado)
            return
        if tipo == "mascara_pintada":
            self.photoshop.mascara_pintada(resultado)
            return
        if tipo == "proyecto_guardado":
            self._proyecto_guardado(resultado)
            return
        if tipo == "lote_avance":
            i, n, nombre = resultado
            self.etiqueta_estado.setText(f"Procesando {i + 1} de {n}: {nombre}…" if nombre else "Terminando…")
            return
        if tipo == "lote":
            self._lote_terminado(resultado)
            return
        if resultado is None or generacion != self._generacion:
            return
        if self._modo_recorte or self._modo_enderezar:
            return  # mientras se recorta o endereza se muestra la foto sin procesar
        if tipo == "rapida":
            if self._generacion_completa_mostrada != generacion:
                self.vista.establecer_despues(resultado)
        elif tipo == "completa":
            ajustes, salida, qimagen, imagen, antes = resultado
            if imagen is not self._imagen:
                return
            self._resultado_completo = (ajustes, salida)
            self._generacion_completa_mostrada = generacion
            # "Antes": con capas, la composición sin el filtro; sin capas, la foto de siempre.
            if antes is not None or self._antes_actual is not None:
                if not self.photoshop.recortando:
                    self.vista.establecer_antes(antes if antes is not None else self._antes_actual)
            self.vista.establecer_despues(qimagen)
            if self.es_documento_sin_foto():
                # La miniatura de un documento sin foto en la tira: lo que se ve.
                foto = self._fotos[self._actual]
                foto.miniatura = QPixmap.fromImage(qimagen.scaled(LADO_MINIATURA, LADO_MINIATURA, Qt.KeepAspectRatio,
                                                                  Qt.SmoothTransformation))
                self.tira.actualizar_miniatura(self._actual, foto.miniatura)
        self._ocupado()

    def _tarea_fallida(self, tipo: str, _generacion: int, mensaje: str) -> None:
        if tipo == "carga":
            self.barra_progreso.hide()
            self.etiqueta_estado.setText("No se pudo abrir la imagen.")
            if self._sesion_foto_pendiente >= 0:
                # Al recuperar la sesión no se interrumpe con un diálogo (la ventana quizás ni se ve).
                indice = self._actual  # la que se estaba abriendo
                nombre = Path(self._fotos[indice].ruta).name if 0 <= indice < len(self._fotos) else "una foto"
                self.aviso.mostrar(f"No se pudo abrir {nombre}, de la sesión anterior.", mensaje)
                self._terminar_restauracion()
            else:
                QMessageBox.warning(self, "No se pudo abrir", f"No se pudo leer la imagen.\n\n{mensaje}")
        elif tipo == "sesion_cargada":
            self._terminar_restauracion()
        elif tipo == "sesion_guardada":
            if not self._error_sesion_avisado:  # una sola vez: se reintenta con el próximo cambio
                self._error_sesion_avisado = True
                self.aviso.mostrar("No se pudo guardar la sesión: tus fotos podrían no recuperarse al volver "
                                   "a abrir.", mensaje)
        elif tipo == "capa_cargada":
            if self._imagen is not None:
                self.etiqueta_estado.setText(self._texto_imagen)
            self.aviso.mostrar("No se pudo agregar la imagen como capa.", mensaje, icono="triangle-alert")
        elif tipo == "fondo_quitado":
            self.photoshop.quitando_fondo = False
            if self._imagen is not None:
                self.etiqueta_estado.setText(self._texto_imagen)
            self._actualizar_habilitados()
            self.aviso.mostrar("No se pudo quitar el fondo.", mensaje, icono="triangle-alert")
        elif tipo == "proyecto_abierto":
            self.barra_progreso.hide()
            self.aviso.mostrar("No se pudo abrir el proyecto.", mensaje, icono="triangle-alert")
        elif tipo == "proyecto_guardado":
            self._guardando_proyecto = False
            self._ocupado()
            QMessageBox.critical(self, "No se pudo guardar el proyecto", f"No se pudo guardar el proyecto.\n\n{mensaje}")
        elif tipo in ("exportacion", "lote"):
            self._exportando = False
            self._actualizar_habilitados()
            self._ocupado()
            QMessageBox.critical(self, "Error al exportar", f"No se pudo guardar el archivo.\n\n{mensaje}")
        elif tipo == "deteccion":
            if self._deteccion is not None and _generacion == self._deteccion[2]:
                destino = self._deteccion[0]
                self._terminar_deteccion()
                self._zona_cancelada(destino)
                self.etiqueta_estado.setText(f"No se pudo detectar la zona: {mensaje}")
        elif tipo == "fuentes":
            if _generacion == self._generacion_fuentes:
                self._fuentes_pendientes = False
                self.etiqueta_estado.setText(f"Error al armar la foto: {mensaje}")
                self._ocupado()
        elif _generacion == self._generacion:  # un render viejo que falló no cuenta
            self.etiqueta_estado.setText(f"Error al procesar: {mensaje}")
            self._generacion_completa_mostrada = self._generacion
            self._ocupado()

    # ========================================================= exportación
    def exportar(self, *, con_filtro: bool = True) -> None:
        """Exporta la imagen final (Ctrl+Shift+E en la Lite). ``con_filtro=False`` ("Exportar sin el
        filtro", del modo Photoshop): la composición de las capas, sin el filtro celular natural. Un
        documento sin foto con el fondo transparente se exporta con transparencia (en PNG)."""
        if self._imagen is None or self._exportando:
            return
        formato = self._formato()
        # Transparente: PNG con alfa. Desenfocado: se exporta normal, en el formato elegido.
        fondo = self.panel_fondo.zona_transparente()
        recortar_objeto = self.panel_fondo.estado_fondo()[1]
        if fondo is not None and formato != "PNG":
            QMessageBox.information(self, "Se exporta en PNG",
                                    "Quitaste el fondo: para que quede transparente se guarda en PNG "
                                    "(JPEG no admite transparencia).")
            formato = "PNG"
        doc_vista = self._documento_vista()
        transparente = doc_vista is not None and dc.fondo_transparente(doc_vista)
        if transparente and formato != "PNG":
            QMessageBox.information(self, "Se exporta en PNG",
                                    "El documento tiene el fondo transparente: para que quede así se guarda en PNG "
                                    "(JPEG no admite transparencia).")
            formato = "PNG"
        extension = ".png" if formato == "PNG" else ".jpg"
        if dc.es_ruta_documento(self._imagen.ruta):  # un documento nuevo: en Imágenes, con su nombre
            base = Path(self.carpeta_inicio()) / dc.nombre_documento(self._imagen.ruta)
            sugerida = ruta_salida_sugerida(base.with_suffix(extension), extension, "" if con_filtro else "_sin_filtro")
        else:
            sugerida = ruta_salida_sugerida(self._imagen.ruta, extension, "_celular" if con_filtro else "_sin_filtro")
        filtro = "PNG (*.png)" if formato == "PNG" else "JPEG (*.jpg *.jpeg)"
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar como archivo nuevo", str(sugerida), filtro)
        if not ruta:
            return
        destino = Path(ruta)
        if destino.suffix.lower() not in ((".png",) if formato == "PNG" else (".jpg", ".jpeg")):
            destino = destino.with_suffix(extension)
        if destino.resolve() == self._imagen.ruta.resolve():
            QMessageBox.warning(self, "Elegí otro nombre",
                                "Ese es el archivo original. Para no sobrescribirlo, elegí otro nombre.")
            return

        if self._transformando is not None:
            self._salir_transformar("aplicar")  # se exporta lo que se ve
        # La medida va siempre (también desde el modo Photoshop, cuya vista no la muestra).
        medida = None if dc.es_ruta_documento(self._imagen.ruta) else self._medida
        clave = (self.panel_ajustes.pila(), self.panel_ajustes.zonas(), self._recorte, self.panel_fondo.desenfoque(),
                 self._version_fuente, self._documento_vista(), bool(con_filtro), medida)
        imagen = self._imagen
        fuente, alpha = self._fuente, self._alpha_fuente
        previo = self._resultado_completo
        calidad = self.slider_calidad.value()
        exif = imagen.exif if self.check_exif.isChecked() else None
        almacen = self._almacen

        def trabajo(_cancelado):
            if previo is not None and previo[0] == clave and previo[1].shape == forma_salida(fuente, medida):
                salida = previo[1]
            else:
                # A resolución completa y sin caché (la de la vista previa no se ensucia ni retiene esto).
                salida = procesar_con_capas(fuente, clave[5], almacen, clave[0], clave[1], clave[2], clave[3], 1.0,
                                            (fuente.shape[1], fuente.shape[0]), None, None,
                                            ("exportar", clave[4]), clave[6], medida)
            alpha_final = alpha_con_fondo(alpha, fondo, clave[2], *salida.shape[:2])
            if transparente:  # documento sin foto con el fondo transparente: el alfa de la composición
                salida, alpha_final = dc.con_alfa_de_documento(clave[5], almacen, salida, sin_filtro=not clave[6])
            if fondo is not None and recortar_objeto and medida is None:  # con una medida, sale exacta
                salida, alpha_final = recortar_a_objeto(salida, alpha_final)
            guardado = exportar_imagen(
                destino, salida, original=imagen.ruta, alpha=alpha_final, icc=imagen.icc,
                exif=exif, formato=formato, calidad_jpeg=calidad,
            )
            with Image.open(guardado) as verificacion:
                tam = verificacion.size
            # Con recorte, el tamaño esperado es el de la parte recortada.
            return guardado, tam, (salida.shape[1], salida.shape[0])

        self._exportando = True
        self._actualizar_habilitados()
        self._ocupado()
        self.etiqueta_estado.setText(f"Exportando {destino.name}…")
        self._pool_archivos.start(Tarea("exportacion", 0, trabajo, self._senales))

    def _exportacion_terminada(self, resultado) -> None:
        guardado, tam, original = resultado
        self._exportando = False
        self._actualizar_habilitados()
        self._ocupado()
        if tam != original:
            QMessageBox.warning(self, "Revisá la exportación",
                                f"El archivo se guardó con {tam[0]}×{tam[1]} px en lugar de {original[0]}×{original[1]} px.")
        self.etiqueta_estado.setText(f"Exportado: {guardado}  ·  {tam[0]} × {tam[1]} px")

    # ================================================================ proyecto .nslite
    def guardar_proyecto(self) -> None:
        """Ctrl+S: guarda la foto abierta con sus capas y su edición en su ``.nslite`` (la primera vez
        pregunta dónde, como "Guardar proyecto como…")."""
        if self._imagen is None or not (0 <= self._actual < len(self._fotos)):
            self.aviso.mostrar("Primero abrí una foto: el proyecto guarda la foto con sus capas.", "", icono="save")
            return
        ruta = self._fotos[self._actual].proyecto
        if ruta is None:
            self.guardar_proyecto_como()
        else:
            self._escribir_proyecto(ruta)

    def guardar_proyecto_como(self) -> None:
        """Ctrl+Shift+S: elige dónde guardar el proyecto (``.nslite``)."""
        if self._imagen is None or not (0 <= self._actual < len(self._fotos)):
            self.aviso.mostrar("Primero abrí una foto: el proyecto guarda la foto con sus capas.", "", icono="save")
            return
        previo = self._fotos[self._actual].proyecto
        if dc.es_ruta_documento(self._imagen.ruta):  # un documento nuevo: en Imágenes, con su nombre
            sugerida = previo or str(Path(self.carpeta_inicio()) / (dc.nombre_documento(self._imagen.ruta)
                                                                     + EXTENSION_PROYECTO))
        else:
            sugerida = previo or str(self._imagen.ruta.with_suffix(EXTENSION_PROYECTO))
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar proyecto (con sus capas)", sugerida,
                                              f"Proyecto de NaturalShot (*{EXTENSION_PROYECTO})")
        if not ruta:
            return
        if Path(ruta).suffix.lower() != EXTENSION_PROYECTO:
            ruta = str(Path(ruta).with_suffix(EXTENSION_PROYECTO))
        self._escribir_proyecto(ruta)

    def extra_proyecto(self) -> dict:
        """Lo que va en ``extra`` del proyecto: la foto original y el estado de la edición en JSON
        (``documento_capas.estado_a_json``). ``TypeError`` si algo del estado no se puede pasar a JSON."""
        imagen = self._imagen
        return {
            "app": self._nombre_app,
            "version_estado": dc.VERSION_ESTADO,
            "foto": {"ruta": str(imagen.ruta), "nombre": imagen.ruta.name, "ancho": imagen.ancho,
                     "alto": imagen.alto, "documento": dc.es_ruta_documento(imagen.ruta)},
            "estado": dc.estado_a_json(self._estado_completo()),
        }

    def _escribir_proyecto(self, ruta: str) -> None:
        if self._transformando is not None:
            self._salir_transformar("aplicar")
        self._timer_historial.stop()
        self._registrar_historial()
        try:
            extra = self.extra_proyecto()
        except TypeError as error:
            QMessageBox.critical(self, "No se pudo guardar el proyecto",
                                 f"Una parte de la edición no se puede guardar en el proyecto.\n\n{error}")
            return
        ancho, alto = self._tam_mostrado()
        doc = dc.con_tamano(self._documento, ancho, alto)
        # Un almacén solo con lo que usa este documento: el de la ventana puede soltar una imagen
        # (``_limpiar_almacen``) mientras el hilo escribe.
        almacen = AlmacenImagenes()
        for id_img in doc.ids_usados():
            arr = self._arreglo(id_img)
            if arr is not None:
                almacen.guardar(arr)
        indice, foto = self._actual, self._fotos[self._actual]

        def trabajo(_cancelado):
            guardar_proyecto(ruta, doc, almacen, extra)
            return foto, ruta

        self._guardando_proyecto = True
        self.etiqueta_estado.setText(f"Guardando el proyecto {Path(ruta).name}…")
        self.barra_progreso.show()
        self._pool_archivos.start(Tarea("proyecto_guardado", indice, trabajo, self._senales))

    def _proyecto_guardado(self, resultado) -> None:
        foto, ruta = resultado
        self._guardando_proyecto = False
        foto.proyecto = ruta
        self._ocupado()
        texto = f"Proyecto guardado: {Path(ruta).name}"
        self.etiqueta_estado.setText(texto)
        self.aviso.mostrar(texto, ruta, icono="circle-check", segundos=6)

    def elegir_proyecto(self) -> None:
        """"Abrir proyecto…": un ``.nslite``."""
        inicio = self.carpeta_inicio()
        ruta, _ = QFileDialog.getOpenFileName(self, "Abrir proyecto", inicio,
                                              f"Proyectos de NaturalShot (*{EXTENSION_PROYECTO})")
        if ruta:
            self.abrir_proyecto(ruta)

    def abrir_proyecto(self, ruta: str) -> None:
        """Abre un ``.nslite`` (en segundo plano): la foto original con su edición y sus capas. Si la
        foto ya no está, se abre igual, con las capas sobre un fondo blanco del mismo tamaño y un aviso.
        Un proyecto roto o de una versión más nueva avisa y no cambia nada."""
        ruta = str(ruta)

        def trabajo(_cancelado):
            doc, almacen, extra = abrir_proyecto(ruta)
            foto = extra.get("foto") if isinstance(extra.get("foto"), dict) else {}
            ruta_foto = foto.get("ruta") if isinstance(foto.get("ruta"), str) else None
            try:
                estado = dc.estado_desde_json(extra["estado"]) if "estado" in extra else None
            except ValueError as error:
                raise ValueError(f"«{Path(ruta).name}» tiene la edición de la foto dañada ({error}).") from error
            try:
                existe = ruta_foto is not None and Path(ruta_foto).is_file()
            except OSError:
                existe = False
            falta = None
            if not doc.tiene_foto:
                # Un documento sin foto ("Nuevo"): no hay foto que buscar; entra a la tira como documento.
                if ruta_foto is None or not dc.es_ruta_documento(ruta_foto):
                    ruta_foto = dc.ruta_documento_nueva([], Path(ruta).stem)
                return ruta, doc, almacen, estado, ruta_foto, None
            if not existe:
                # La foto ya no está: un fondo blanco del tamaño del documento, en la carpeta de la app.
                falta = ruta_foto or "(el proyecto no dice cuál era)"
                if doc.ancho * doc.alto > MAX_PIXELES_IMAGEN:
                    raise ValueError(f"La foto original de «{Path(ruta).name}» ya no está y el proyecto es demasiado "
                                     f"grande ({doc.ancho} × {doc.alto} px) para abrirlo sobre un fondo blanco.")
                carpeta = edicion.carpeta_datos() / "proyectos sin foto"
                carpeta.mkdir(parents=True, exist_ok=True)
                ruta_foto = str(carpeta / f"{Path(ruta).stem} (falta la foto).png")
                lienzo = Path(ruta_foto)
                tam_ok = False
                if lienzo.is_file():
                    try:
                        with Image.open(lienzo) as im:
                            tam_ok = im.size == (doc.ancho, doc.alto)
                    except OSError:
                        tam_ok = False
                if not tam_ok:
                    Image.new("RGB", (doc.ancho, doc.alto), (255, 255, 255)).save(lienzo)
            return ruta, doc, almacen, estado, ruta_foto, falta

        self.etiqueta_estado.setText(f"Abriendo el proyecto {Path(ruta).name}…")
        self.barra_progreso.show()
        self._pool_archivos.start(Tarea("proyecto_abierto", 0, trabajo, self._senales))

    def _proyecto_abierto(self, resultado) -> None:
        ruta, doc, almacen, estado, ruta_foto, falta = resultado
        self.barra_progreso.hide()
        for id_img in almacen.ids():
            self._almacen.guardar(almacen.obtener(id_img))
        if estado is None or falta is not None:
            # Sin la foto original no se puede rearmar su edición (recorte, giro, montaje, borrados y
            # fondo): quedan el estilo, los efectos (a toda la foto) y las capas.
            base = estado if estado is not None else self._estado_para_foto_nueva()
            estado = dict(base)
            estado["capas"] = [(p, i, None) for p, i, *_ in base.get("capas", [])]
            estado["recorte"] = None
            estado["geometria"] = Geometria()
            estado["montaje"] = ()
            estado["borrado"] = ()
            estado["fondo"] = (None,) + completar_estado(base.get("fondo"))[1:]
            estado.pop("medida", None)  # va con el recorte, que no se pudo rearmar
        estado = dict(estado)
        if dc.es_trivial(doc):
            estado.pop("documento", None)
        else:
            estado["documento"] = doc
        nombre = Path(ruta).name
        paso = (f"Proyecto abierto: {nombre}", estado)
        existente = next((i for i, f in enumerate(self._fotos) if self._misma_ruta(f.ruta, ruta_foto)), None)
        if dc.es_ruta_documento(ruta_foto):
            # Un documento sin foto es el mismo solo si viene del mismo proyecto (los nombres se repiten).
            if existente is not None and not (self._fotos[existente].proyecto
                                              and self._misma_ruta(self._fotos[existente].proyecto, ruta)):
                existente = None
                ruta_foto = dc.ruta_documento_nueva([f.ruta for f in self._fotos], Path(ruta).stem)
        if existente is not None and existente == self._actual and self._estado_vivo():
            # La foto ya está abierta: el proyecto queda como un paso más (se puede deshacer).
            if self._herramienta_activa():
                self.cancelar_herramienta()
            self._timer_historial.stop()
            self._registrar_historial()
            del self._historial[self._pos_historial + 1:]
            self._historial.append(paso)
            self._pos_historial = len(self._historial) - 1
            self._restaurar(estado)
            self._fotos[existente].proyecto = ruta
            self._sesion_cambiada()
        elif existente is not None:
            f = self._fotos[existente]
            historial = list(f.historial or ([("Inicio", f.estado)] if f.estado is not None else []))
            f.historial = historial[:f.pos + 1] + [paso] if historial else [paso]
            f.pos = len(f.historial) - 1
            f.estado = estado
            f.proyecto = ruta
            self.cambiar_a_foto(existente)
        else:
            self._fotos.append(FotoSesion(ruta_foto, estado=estado, historial=[paso], pos=0, proyecto=ruta))
            self._refrescar_tira()
            self.cambiar_a_foto(len(self._fotos) - 1)
            self._sesion_cambiada()
        avisos, detalle = [], []
        if falta is not None:
            avisos.append(f"La foto original de «{nombre}» ya no está: se abrió con sus capas sobre un fondo blanco "
                          "del mismo tamaño (sin el recorte, el giro, el montaje, los borrados ni el fondo).")
            detalle.append(f"Foto original: {falta}")
        faltan = capas_faltantes(doc, self._almacen)
        if faltan:
            avisos.append(f"Faltan {len(faltan)} imágenes del proyecto: esas capas quedan vacías." if len(faltan) > 1
                          else "Falta una imagen del proyecto: esa capa queda vacía.")
        if avisos:
            self.aviso.mostrar(" ".join(avisos), "\n".join(detalle), icono="triangle-alert", segundos=20)

    # ================================================================ lote
    def procesar_varias(self) -> None:
        if self._exportando:
            return
        inicio = self.carpeta_inicio()
        rutas, _ = QFileDialog.getOpenFileNames(self, "Elegí las fotos a procesar", inicio, FILTRO_ABRIR)
        if not rutas:
            return
        carpeta = QFileDialog.getExistingDirectory(
            self, "Carpeta de destino (Cancelar = junto a cada original)", str(Path(rutas[0]).parent))
        pila = self.panel_ajustes.pila()
        formato = self._formato()
        calidad = self.slider_calidad.value()
        exif = self.check_exif.isChecked()
        senales = self._senales
        encuadres = self._encuadres_lote(rutas)

        def trabajo(_cancelado):
            def avance(i, n, nombre):
                senales.terminada.emit("lote_avance", 0, (i, n, nombre))
            return procesar_lote(rutas, pila, carpeta or None, formato, calidad, exif, avance, encuadres=encuadres)

        self._exportando = True
        self._actualizar_habilitados()
        self._ocupado()
        self._pool_archivos.start(Tarea("lote", 0, trabajo, self._senales))

    def _lote_terminado(self, resultados) -> None:
        self._exportando = False
        self._actualizar_habilitados()
        self._ocupado()
        bien = [r for r in resultados if r.error is None]
        mal = [r for r in resultados if r.error is not None]
        self.etiqueta_estado.setText(f"Lote listo: {len(bien)} de {len(resultados)} fotos guardadas.")
        if mal:
            detalle = "\n".join(f"• {r.original.name}: {r.error}" for r in mal[:10])
            QMessageBox.warning(self, "Algunas fotos no se procesaron", detalle)

    # =============================================================== sesión
    @property
    def sesion_restaurada(self) -> bool:
        """Si ya terminó de recuperar la sesión anterior (o si esta ventana no la recuerda)."""
        return self._sesion_lista or not self._sesion_activa

    def activar_sesion(self) -> None:
        """Recupera las fotos de la vez anterior y, desde ahí, guarda la sesión sola.

        El archivo se lee en segundo plano y ahí mismo se revisa qué fotos siguen en su
        carpeta. Después se arma la tira, se abre la foto que estaba abierta y las
        miniaturas cargan en segundo plano, igual que al abrir fotos. Hasta que termina
        no se guarda nada: un cierre a mitad de camino no pisa la sesión anterior.
        """
        if self._sesion_activa:
            return
        self._sesion_activa = True

        def leer(_cancelado):
            guardada, problema = sesion.cargar()
            faltantes = []
            for i, foto in enumerate(guardada.fotos if guardada is not None else ()):
                if dc.es_ruta_documento(foto.ruta):
                    # Un documento sin foto no es un archivo: está si su estado tiene el documento.
                    doc = (foto.estado or {}).get("documento")
                    existe = isinstance(doc, Documento) and not doc.tiene_foto
                else:
                    try:
                        existe = Path(foto.ruta).is_file()
                    except OSError:
                        existe = False
                if not existe:
                    faltantes.append(i)
            audio_falta = False  # la voz del proyecto del modo Audio ya no está en su carpeta
            if guardada is not None and guardada.audio is not None:
                try:
                    audio_falta = not Path(guardada.audio.estado["proyecto"].ruta).is_file()
                except OSError:
                    audio_falta = True
            # Las imágenes y máscaras de las capas (PNG en la carpeta de la sesión).
            imagenes = sesion.cargar_imagenes(guardada)
            return guardada, faltantes, problema, audio_falta, imagenes

        self._pool_sesion.start(Tarea("sesion_cargada", 0, leer, self._senales))

    @property
    def recuerda_sesion(self) -> bool:
        """Si las fotos y sus ediciones se van a recuperar al volver a abrir (se guardan solas)."""
        return self._sesion_activa and self._sesion_lista

    def cuando_sesion_lista(self, funcion) -> None:
        """Llama a ``funcion`` cuando termine de recuperarse la sesión (o enseguida, si ya terminó)."""
        if self.sesion_restaurada:
            QTimer.singleShot(0, funcion)
        else:
            self._al_restaurar_sesion.append(funcion)

    def _sesion_cargada(self, resultado) -> None:
        guardada, faltantes, problema, audio_falta, imagenes = resultado
        for arr in imagenes.values():
            self._almacen.guardar(arr)
        # Mientras se leía, se empezó de cero ("Quitar todas las fotos"): las fotos ya no se suman,
        # pero el proyecto del modo Audio no es una foto y se recupera igual (ese "Quitar todas" pudo
        # haber borrado el archivo: se vuelve a guardar).
        de_cero = self._sesion_lista
        if problema and not de_cero:
            self.aviso.mostrar("No se pudo recuperar la sesión anterior: la app arrancó de cero.",
                               f"Motivo: {problema}.\nQuedó una copia en {sesion.archivo_respaldo()}")
        # El proyecto del modo Audio: se pone si el editor ya está (y vacío); si no, espera a que se
        # entre a Audio (así no se carga nada del audio sin hacer falta).
        aviso_audio = None
        audio = guardada.audio if guardada is not None else None
        if self._lite:  # la Lite no tiene modo Audio (y su sesión no debería tener uno)
            audio = None
        if audio is not None:
            if audio_falta:
                aviso_audio = ("El audio de la sesión anterior ya no está en su carpeta.",
                               audio.estado["proyecto"].ruta)
                self.aviso.mostrar(*aviso_audio)
            elif self.editor_audio is None:
                self._audio_pendiente = audio
            elif self.editor_audio.ruta is None:
                self._restaurar_audio(audio)
            self._actualizar_selector()
        if de_cero:
            if audio is not None and not audio_falta:
                self._sesion_cambiada()
            return
        if guardada is None or not guardada.fotos:
            self._terminar_restauracion()
            return
        faltan = set(faltantes)
        nuevas = []  # (índice en la sesión guardada, índice en la tira)
        for i, foto in enumerate(guardada.fotos):
            if i in faltan or any(self._misma_ruta(f.ruta, foto.ruta) for f in self._fotos):
                continue
            self._fotos.append(FotoSesion(foto.ruta, estado=foto.estado, historial=foto.historial, pos=foto.pos,
                                          proyecto=foto.proyecto))
            nuevas.append((i, len(self._fotos) - 1))
        if faltantes:
            n = len(faltantes)
            nombres = [Path(guardada.fotos[i].ruta).name for i in faltantes]
            texto = (f"{n} fotos de la sesión anterior ya no están en su carpeta." if n > 1 else
                     "1 foto de la sesión anterior ya no está en su carpeta.")
            detalle = "\n".join(nombres[:12]) + ("\n…" if n > 12 else "")
            if aviso_audio is not None:  # un solo aviso con las dos cosas
                texto, detalle = f"{texto} {aviso_audio[0]}", f"{detalle}\n{aviso_audio[1]}"
            self.aviso.mostrar(texto, detalle)
        if not nuevas:
            self._terminar_restauracion()
            return
        self._refrescar_tira()
        if self._actual >= 0:  # mientras tanto se abrió otra foto: se suman a la tira sin cambiar de foto
            for _i, j in nuevas:
                self._cargar_miniatura(self._fotos[j].ruta)
            self._terminar_restauracion()
            return
        # La que estaba abierta o, si ya no está, la más cercana (a igual distancia, la siguiente).
        destino = min(nuevas, key=lambda par: (abs(par[0] - guardada.actual), par[0] < guardada.actual))[1]
        self._sesion_foto_pendiente = destino
        self.cambiar_a_foto(destino)
        for _i, j in nuevas:
            if j != destino:
                self._cargar_miniatura(self._fotos[j].ruta)

    def _terminar_restauracion(self) -> None:
        self._sesion_foto_pendiente = -1
        if self._sesion_lista:
            return
        self._sesion_lista = True
        esperando, self._al_restaurar_sesion = self._al_restaurar_sesion, []
        self.sesionRestaurada.emit()
        for funcion in esperando:
            funcion()
        self._sesion_cambiada()  # sin las fotos que ya no estaban, el aviso no se repite la próxima vez

    def _sesion_cambiada(self) -> None:
        """Cambió algo que se recuerda (fotos, foto actual o un paso del historial): se
        guarda a los 2 s. Si ya había un guardado programado no se posterga: como mucho
        se pierden 2 s si se corta la luz, y se escribe como mucho una vez cada 2 s."""
        if self._sesion_activa and self._sesion_lista and not self._timer_sesion.isActive():
            self._timer_sesion.start()

    def _estado_vivo(self) -> bool:
        """Si lo que muestran los paneles es de la foto actual (no lo es mientras se abre otra)."""
        return (self._imagen is not None and 0 <= self._actual < len(self._fotos)
                and self._fotos[self._actual].imagen is self._imagen)

    def instantanea_sesion(self) -> "sesion.SesionGuardada":
        """La sesión tal como está: ruta, estado, historial y posición de cada foto, y cuál
        está abierta. Copia las listas (los estados nunca se modifican), así se puede
        escribir en segundo plano."""
        vivo = self._estado_vivo()
        fotos = []
        for i, f in enumerate(self._fotos):
            if i == self._actual and vivo:
                fotos.append(sesion.FotoGuardada(f.ruta, self._estado_completo(), list(self._historial),
                                                 self._pos_historial, f.proyecto))
            else:
                fotos.append(sesion.FotoGuardada(f.ruta, f.estado, list(f.historial) if f.historial else None,
                                                 f.pos, f.proyecto))
        # El proyecto del modo Audio: el del editor o, si todavía no se entró a Audio, el de la sesión.
        audio = self.editor_audio.estado_sesion() if self.editor_audio is not None else self._audio_pendiente
        if self._lite:
            audio = None
        guardada = sesion.SesionGuardada(fotos, self._actual, audio)
        # Las imágenes y máscaras de las capas: los arreglos del almacén (de solo lectura, se pueden
        # escribir en otro hilo); la sesión los guarda como PNG.
        # (Las que ya están escritas en la carpeta de la sesión no hace falta descomprimirlas.)
        carpeta = sesion.carpeta_imagenes()
        guardada.imagenes = {}
        for i in sesion.ids_de_imagenes(guardada):
            if i not in self._almacen and _png_escrito(carpeta / f"{i}.png"):
                continue
            arr = self._arreglo(i)
            if arr is not None:
                guardada.imagenes[i] = arr
        return guardada

    def guardar_sesion(self, esperar: bool = False) -> None:
        """Escribe la sesión: en segundo plano o, con ``esperar`` (al cerrar), ya mismo."""
        self._timer_sesion.stop()
        if not (self._sesion_activa and self._sesion_lista):
            return
        instantanea = self.instantanea_sesion()
        if esperar:
            self._pool_sesion.waitForDone()  # que una escritura vieja no quede después de esta
            sesion.guardar(instantanea)
            return
        self._pool_sesion.start(Tarea("sesion_guardada", 0, lambda _c: sesion.guardar(instantanea),
                                      self._senales))

    def quitar_todas_las_fotos(self, confirmar: bool = True) -> bool:
        """Vacía la tira y empieza de cero (los archivos no se tocan). También vacía la
        sesión guardada. Se conservan el preset y las capas, como para una foto nueva."""
        if not self._fotos:
            return False
        if confirmar:
            n = len(self._fotos)
            respuesta = QMessageBox.question(
                self, "Quitar todas las fotos",
                (f"¿Quitar las {n} fotos de la tira?" if n > 1 else "¿Quitar la foto de la tira?")
                + "\n\nSe pierden sus ediciones y su historial (lo que no exportaste). Los archivos "
                "originales no se tocan.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if respuesta != QMessageBox.Yes:
                return False
        if self._modo_recorte:
            self._salir_recorte("cancelar", recalcular=False)
        if self._modo_enderezar:
            self._salir_enderezar("cancelar", recalcular=False)
        self.cancelar_herramienta()
        for timer in (self._timer_historial, self._timer_montaje, self._timer_rapido, self._timer_completo):
            timer.stop()
        # Lo que esté en curso queda viejo y se descarta al terminar.
        self._generacion += 1
        self._generacion_carga += 1
        self._generacion_fuentes += 1
        self._generacion_deteccion += 1
        self._pool_miniaturas.clear()
        self._sesion_foto_pendiente = -1
        self._fotos = []
        self._actual = -1
        self._imagen = self._transformacion = self._vista_previa = None
        self._escala_vista_previa = 1.0
        self._resultado_completo = None
        self._fuente = self._alpha_fuente = None
        self._antes_completo = self._antes_actual = self._antes_original = None
        self._base_completa = None
        self._clave_base = ()
        self._clave_vista_previa = None
        self._completo_cache = None
        self._fuentes_pendientes = False
        self._version_fuente += 1
        estado = self._estado_para_foto_nueva()
        self._restaurando = True
        try:
            self.panel_ajustes.restaurar(estado)
            self.panel_montaje.restaurar((), self._miniatura_de)
            self.panel_fondo.restaurar(estado["fondo"])
            self.panel_borrar.restaurar(())
        finally:
            self._restaurando = False
        self._recorte = None
        self._medida = None
        self._actualizar_medida()
        self._geometria = Geometria()
        self._documento = self._doc_provisorio = None
        for id_img in self._almacen.ids():
            self._almacen.quitar(id_img)
        self._comprimidas.clear()
        self._cache_rapida.limpiar()
        self._cache_completa.limpiar()
        self.panel_capas.establecer(None, None)
        self._historial, self._pos_historial = [("Inicio", estado)], 0
        self._refrescar_historial()
        self.vista.vaciar()
        self._refrescar_tira()  # sin fotos, la tira se oculta
        self.etiqueta_estado.setText("Abrí una foto para empezar.")
        self.pie_avatar.setText("—")
        self.pie_nombre.setText("Sin foto abierta")
        self.pie_detalle.setText("Procesado local · sin IA generativa")
        self._titulo_fotos = self._nombre_app
        self._actualizar_titulo()
        self._actualizar_habilitados()
        self._ocupado()
        self.panel_facil.foto_cambiada()
        if self._sesion_activa and not self._sesion_lista:
            self._terminar_restauracion()  # lo que se estaba recuperando ya no se suma
        if self._sesion_activa:
            self._timer_sesion.stop()
            self._pool_sesion.waitForDone()  # un guardado en curso no la vuelve a crear después
            try:
                instantanea = self.instantanea_sesion()
                if instantanea.audio is None:
                    sesion.borrar()
                else:  # el proyecto del modo Audio no es una foto: queda
                    sesion.guardar(instantanea)
            except OSError:
                traceback.print_exc()
        return True

    # =============================================================== cierre
    def exportando_algo(self) -> bool:
        """Si hay una exportación de fotos, de video o de audio en curso (la actualización espera)."""
        return self._exportando or self.exportando_video() or self.exportando_audio()

    def exportando_video(self) -> bool:
        """Si se está exportando un video (aunque se esté trabajando en las fotos)."""
        return self.editor_video is not None and self.editor_video.exportando

    def exportando_audio(self) -> bool:
        """Si se está exportando un audio (aunque se esté en otro modo)."""
        return self.editor_audio is not None and self.editor_audio.exportando

    def tiene_ediciones(self) -> bool:
        """Si alguna foto abierta (o el audio) tiene cambios (se pierden al cerrar si no se exportaron)."""
        return (len(self._historial) > 1 or any(len(f.historial or ()) > 1 for f in self._fotos)
                or (self.editor_audio is not None and self.editor_audio.tiene_cambios()))

    def closeEvent(self, evento) -> None:
        # Una exportación de video tarda minutos (y una de audio, segundos): antes de cortarla, se pregunta.
        if self.exportando_video() or self.exportando_audio():
            cosa = ("un video y un audio" if self.exportando_video() and self.exportando_audio() else
                    "un video" if self.exportando_video() else "un audio")
            respuesta = QMessageBox.question(
                self, "Exportación en curso" if self.exportando_audio() else "Exportación de video en curso",
                f"Se está exportando {cosa}. Si cerrás NaturalShot, la exportación se cancela (no queda ningún "
                "archivo a medias).\n\n¿Cancelarla y cerrar?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if respuesta != QMessageBox.Yes:
                evento.ignore()
                return
        # Primero la sesión: lo último que se tocó (aunque no haya pasado al historial) queda guardado.
        if self._sesion_activa and self._sesion_lista:
            if self._estado_vivo():
                self._timer_historial.stop()
                self._registrar_historial()
            try:
                self.guardar_sesion(esperar=True)
            except Exception:  # nunca impide cerrar
                traceback.print_exc()
        self.actualizaciones.detener()  # búsqueda, conexión o descarga en curso
        self._generacion += 1  # cancela renders en curso
        self._generacion_fuentes += 1  # y los borrados y detecciones que todavía no empezaron
        self._generacion_deteccion += 1
        self.panel_facil.detener()  # miniaturas de la galería que falten
        if self._exportando or self._guardando_proyecto:
            self.etiqueta_estado.setText("Esperando a que termine la exportación…" if self._exportando else
                                         "Esperando a que termine de guardarse el proyecto…")
            self._pool_archivos.waitForDone()
        if self.editor_video is not None:
            self.editor_video.detener()  # cancela la exportación de video (si se confirmó) y espera sus hilos
        if self.editor_audio is not None:
            self.editor_audio.detener()  # lo mismo con el audio (y suelta lo que suena)
        super().closeEvent(evento)
        if evento.isAccepted():
            self._sacar_filtros_globales()
