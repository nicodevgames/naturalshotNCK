"""Editor de video: el mismo filtro de las fotos, aplicado a cada cuadro.

Es el **modo Video** de la ventana principal (selector "Fácil | Editor | Video"):
va adentro de la misma ventana, nunca en una aparte. ``EditorVideo`` es la parte
central y derecha (el video con su línea de tiempo, los ajustes finos y la
exportación); su columna izquierda (preset y capas, datos del video y atajos)
está en ``EditorVideo.lateral``, que la ventana pone debajo de la marca y del
selector de modo. Hay una sola instancia, que la ventana crea la primera vez que
se entra a Video (recién ahí se carga PyAV).

* Vista previa antes/después del cuadro actual (Dividir, Antes, Después, Lado a
  lado y zoom), procesada en segundo plano: primero reducida y, quieta, al
  tamaño exacto de la exportación.
* Reproducir y pausar. Al reproducir se saltean los tramos borrados y se ve el
  filtro a baja resolución (si la PC no llega, el original). Al pausar o soltar
  el cursor se ve el cuadro procesado.
* Sonido al reproducir (``ReproductorAudio``): suena lo que se va a exportar
  (sin lo borrado, con los silencios, los fundidos y el volumen) y la imagen sigue
  al sonido. El botón del parlante lo silencia (se recuerda). Sin salida de
  sonido, la vista previa anda igual, sin sonido.
* Línea de tiempo que muestra **el resultado** (como en los editores de los
  celulares): entrada (I) y salida (O), cortar (S), elegir un tramo y borrarlo
  (Supr). Lo borrado y lo recortado desaparece y lo que sigue se corre; en cada
  unión queda una marquita que ofrece "Recuperar lo borrado" (también R, la más
  cercana al cursor, y Ctrl+Z). Deshacer y rehacer (Ctrl+Z, Ctrl+Y). Debajo, la
  pista de sonido (``PistaOnda`` con ``solo_resultado``) con la forma de onda y
  los silencios, alineada con la línea.
* Tiempos: la edición, el cursor (``tiempo``) y los silencios van en el tiempo
  original del archivo; lo que se muestra (regla, cursor, duración, cuadro,
  reproducción) va en el del resultado. Convierte ``mapa`` (``MapaTiempo``). El
  cursor nunca queda en algo que no se ve.
* Silenciar tramo (M): el mismo tramo que borra Supr (el elegido o, si no hay
  ninguno elegido, el del cursor) queda en silencio; si ya lo está, le devuelve
  el sonido. Los silencios van en el tiempo original (no se mueven al cortar).
* Tarjeta "Sonido" (``PanelSonido``), arriba de los ajustes: quitar el sonido,
  volumen, normalizar, fundidos de entrada y salida, y "Guardar solo el audio…"
  (M4A, WAV o MP3, en segundo plano, con progreso y Cancelar).
* Sonido de otro archivo (``audio_externo``, ``motor.video.AudioExterno``), arriba
  en la tarjeta Sonido, con un renglón que dice qué suena:
  - "Editar el sonido en el modo Audio": guarda el sonido completo del original
    (sin cortes ni ajustes) en un WAV de ``%APPDATA%\\NaturalShot PRO\\temporal`` y
    emite ``editarSonidoPedido(wav, video)``. La ventana abre el modo Audio y, a la
    vuelta, llama a ``usar_sonido_externo(ruta, "original")``: los cortes del video
    se le aplican igual.
  - "Cambiar el sonido por…": un audio desde el principio de lo que se exporta (voz
    en off), cortado al final; "Volver al original" lo saca.
  - La pista, la vista previa, "Guardar solo el audio" y la exportación usan el
    externo. Entra al historial. Al abrir el editor se borran los temporales de más
    de una semana.
* Tarjeta "Mejorar calidad" (``PanelMejora``, sin IA): interruptor y barras
  Quitar cuadraditos, Nitidez y Usar cuadros vecinos. Prendida, el cuadro del
  cursor se ve mejorado (con sus vecinos del mismo tramo, igual que en la
  exportación, en un hilo y con caché); "Antes" es el original agrandado simple
  (bicúbico). Al reproducir se ve sin la mejora (aparece al pausar), como el
  filtro a baja resolución. Al exportar, 720p y 1080p agrandan un video más
  chico y el resumen avisa que tarda más.
* Deshacer y rehacer van juntos para los cortes, el sonido, el sonido externo y la mejora (los
  movimientos seguidos de un mismo deslizador cuentan como un solo paso).
* Exportar a MP4 (H.264 + AAC, o sin pista de audio si se quitó el sonido) con
  resolución y calidad, barra de progreso, tiempo restante y Cancelar. El
  original nunca se toca. La exportación sigue aunque se vuelva a las fotos: la
  ventana muestra el progreso junto al selector.

Abrir y soltar archivos pasan por la ventana (``ventana.elegir_archivo`` y
``ventana.abrir_rutas``), que lleva cada cosa a su modo: las fotos a la tira y
los videos acá.
"""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, Optional, Sequence

import cv2
import numpy as np
from PySide6.QtCore import QRectF, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QImage, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from ..motor import NEUTRO, Ajustes, Cancelado, reducir_para_vista
from ..motor import audio as ma
from ..motor import mejora_video as mm
from ..motor import video as mv
from . import estilo, iconos
from .controles import COLOR_SECCION, SIN_EFECTO, SUBTITULO_SECCION, PanelAjustes, SeccionPlegable, todos_los_presets
from .forma_onda import CargadorOnda, PistaOnda, forma_alineada, pico_aproximado
from .linea_tiempo import LineaTiempo, formato_duracion, formato_tiempo
from .modo_facil import configuracion
from .modo_video import EtiquetaElidida
from .panel_mejora import PanelMejora
from .panel_sonido import PanelSonido
from .reproductor_audio import ReproductorAudio
from .tareas import SenalesTarea, Tarea
from .vista_comparacion import VistaComparacion

if TYPE_CHECKING:  # pragma: no cover
    from .ventana import VentanaPrincipal

LADO_VISTA = 1280         # "antes" de la vista rápida
LADO_RAPIDO = 640         # filtro de la vista rápida (responde enseguida)
LADO_REPRODUCCION = 960   # cuadros al reproducir
LADO_VIVO = 480           # filtro al reproducir
LIMITE_VIVO = 0.30        # s por cuadro: más lento que esto, al reproducir se ve el original
ALTO_MINIATURA = 72
CANTIDAD_MINIATURAS = 28
ACELERACION_HILOS = 2.2   # cuánto más rápido exporta en paralelo que un cuadro solo (medido: 2,1-2,6)
ANCHO_DERECHO = 340       # columna de ajustes y exportación (como en fotos)
FILTRO_VIDEO = "Videos ({})".format(" ".join(f"*{e}" for e in mv.EXTENSIONES_VIDEO))
TEXTO_CALIDAD = {
    "Alta": "Alta (conserva el ruido)",
    "Normal": "Normal",
    "Liviana": "Liviana (archivo chico)",
}
GIRO = {90: "90° a la izquierda", 180: "180°", 270: "90° a la derecha"}
SIN_VIDEO = "Abrí un video para empezar."
# La ayuda debajo de la línea de tiempo (lo que no entra queda en la ayuda emergente).
AYUDA_LINEA = ("Tocá o arrastrá para moverte · S corta · tocá un tramo: Supr lo borra y M lo silencia · arrastrá "
               "los corchetes para recortar el principio y el final · lo borrado desaparece y deja una marquita "
               "rosa para recuperarlo")
AYUDA_LINEA_CON_BORRADOS = ("Tocá una marquita rosa para recuperar lo borrado (o R, o Ctrl+Z) · tocá o arrastrá "
                            "para moverte · S corta · tocá un tramo: Supr lo borra y M lo silencia · arrastrá los "
                            "corchetes para recortar el principio y el final")
CLAVE_SONIDO_VISTA = "video/sonido_vista_previa"  # QSettings: si la vista previa suena
JUNTAR_SONIDO = 1.5    # s: los cambios seguidos de un mismo control (sonido o mejora) son un solo paso de deshacer
ESPERA_SONIDO = 0.08   # s: al mover el cursor mientras suena, el sonido vuelve cuando se queda quieto
# Cuánto más rápido mejora la exportación (3 cuadros a la vez, con leer y codificar) que un cuadro solo de la
# vista previa. Medido a 1080p: un cuadro solo, 0,15-0,21 s; exportando, 0,107 s por cuadro.
ACELERACION_MEJORA = 1.5
LIMITE_CACHE_MEJORA = 96 * 1024 * 1024  # bytes de cuadros ya mejorados para la vista previa

# Tarjetas propias del editor (mismo estilo que las secciones del panel).
COLOR_SECCION.setdefault("Video", "#38bdf8")
SUBTITULO_SECCION.setdefault("Video", "Datos del archivo abierto")
COLOR_SECCION.setdefault("Atajos", "#94a3b8")
SUBTITULO_SECCION.setdefault("Atajos", "Para editar sin el mouse")


try:  # los audios que acepta "Cambiar el sonido por…" (los mismos del modo Audio)
    from ..motor.proyecto_audio import EXTENSIONES_AUDIO
except Exception:  # pragma: no cover - el modo Audio se está haciendo aparte
    EXTENSIONES_AUDIO = (".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac")
FILTRO_AUDIO = "Audios ({})".format(" ".join(f"*{e}" for e in EXTENSIONES_AUDIO))


class EstadoEditor(NamedTuple):
    """Un paso del historial de deshacer y rehacer: todo lo que se deshace junto."""

    edicion: mv.EdicionVideo
    audio: ma.AjustesAudio
    mejora: mm.AjustesMejora
    externo: Optional[mv.AudioExterno] = None  # el sonido de otro archivo (None = el del video)


_IGUAL = object()  # "no cambia" en _editar y _fijar_estado (None es un valor: sin sonido externo)


def _a_qimage(rgb: np.ndarray) -> QImage:
    rgb = np.ascontiguousarray(rgb)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


class DatosMejora(NamedTuple):
    """Lo que necesita la vista previa para mejorar un cuadro igual que la exportación."""
    ajustes: mm.AjustesMejora
    tramos: tuple                  # tramos conservados (los vecinos no cruzan de uno a otro)
    fps: float
    ultimo: float                  # comienzo del último cuadro del video
    lectura: tuple[int, int]       # tamaño al que se leen los cuadros (mv.tamano_lectura)
    nativo: tuple[int, int]        # tamaño del original (ya derecho)


class CacheMejora:
    """Cuadros ya mejorados para la vista previa: cambiar el filtro o volver a un cuadro no repite
    la mejora. Se puede usar desde varios hilos."""

    def __init__(self, limite: int = LIMITE_CACHE_MEJORA):
        self._limite = limite
        self._cuadros: "OrderedDict[tuple, np.ndarray]" = OrderedDict()
        self._bytes = 0
        self._candado = threading.Lock()

    def obtener(self, clave: tuple) -> Optional[np.ndarray]:
        with self._candado:
            guardado = self._cuadros.get(clave)
            if guardado is not None:
                self._cuadros.move_to_end(clave)
            return guardado

    def guardar(self, clave: tuple, rgb: np.ndarray) -> None:
        with self._candado:
            if clave in self._cuadros:
                return
            self._cuadros[clave] = rgb
            self._bytes += rgb.nbytes
            while self._bytes > self._limite and len(self._cuadros) > 1:
                _c, viejo = self._cuadros.popitem(last=False)
                self._bytes -= viejo.nbytes

    def vaciar(self) -> None:
        with self._candado:
            self._cuadros.clear()
            self._bytes = 0

    def __len__(self) -> int:
        return len(self._cuadros)


def leer_para_mejora(ruta: str, t: float, datos: DatosMejora) -> np.ndarray:
    """El cuadro que se ve en ``t``, leído exactamente como lo lee la exportación para mejorarlo:
    directo a ``datos.lectura`` y con la misma conversión (reducir a un lado máximo y después
    ajustar daba, por ejemplo, 1280×719 estirado a 1280×720 en vez de 1280×720 directo)."""
    return mv.cuadro_en(ruta, t, tamano=tuple(datos.lectura))


def clave_mejora(ruta: str, t: float, ancho: int, alto: int, datos: DatosMejora) -> tuple:
    """Clave de la caché: el cuadro, cuáles de sus vecinos se usan (dependen del tramo), los ajustes
    y los tamaños."""
    tiempos = mv.tiempos_vecinos(datos.tramos, t, datos.fps, datos.ultimo)
    indices = tuple(None if s is None else mv.indice_en(s, datos.fps) for s in tiempos)
    return (ruta, mv.indice_en(t, datos.fps), indices, datos.ajustes, tuple(datos.lectura), (ancho, alto))


def cuadro_mejorado(ruta: str, t: float, ancho: int, alto: int, datos: DatosMejora, cache: CacheMejora,
                    cancelado=None) -> tuple[np.ndarray, Optional[np.ndarray], Optional[float]]:
    """(original, mejorado, segundos) del cuadro que se ve en ``t``, mejorado a ``ancho``×``alto`` con
    sus vecinos del mismo tramo, igual que en la exportación.

    El original va al tamaño de lectura. ``segundos`` es lo que tardó la mejora (None si ya estaba
    en la caché). Si se cancela a mitad de camino, el mejorado es None."""
    tiempos = mv.tiempos_vecinos(datos.tramos, t, datos.fps, datos.ultimo)
    clave = clave_mejora(ruta, t, ancho, alto, datos)
    guardado = cache.obtener(clave)
    if guardado is not None:
        return leer_para_mejora(ruta, t, datos), guardado, None
    # Se leen en orden (t-2, t-1, t, t+1, t+2): una sola búsqueda y después de corrido.
    mitad = len(tiempos) // 2
    leidos = {}
    for s in [*tiempos[:mitad], t, *tiempos[mitad:]]:
        if s is not None:
            leidos[s] = leer_para_mejora(ruta, s, datos)
        if cancelado is not None and cancelado():
            return leidos.get(t, leer_para_mejora(ruta, t, datos)), None, None
    actual = leidos[t]
    vecinos = [None if s is None else leidos[s] for s in tiempos]
    inicio = time.perf_counter()
    mejorado = mm.mejorar_cuadro(actual, vecinos, ancho, alto, datos.ajustes)
    segundos = time.perf_counter() - inicio
    cache.guardar(clave, mejorado)
    return actual, mejorado, segundos


def agrandar_simple(rgb: np.ndarray, ancho: int, alto: int) -> np.ndarray:
    """"Antes" con la mejora: el original agrandado (o achicado) a secas, como cualquier programa."""
    if (rgb.shape[1], rgb.shape[0]) == (ancho, alto):
        return rgb
    interpolacion = cv2.INTER_CUBIC if ancho >= rgb.shape[1] else cv2.INTER_AREA
    return cv2.resize(rgb, (ancho, alto), interpolation=interpolacion)


def _duracion_humana(segundos: float) -> str:
    if segundos < 60:
        return "menos de un minuto"
    minutos = int(round(segundos / 60))
    if minutos == 1:
        return "alrededor de un minuto"
    if minutos < 60:
        return f"unos {minutos} min"
    h, m = divmod(minutos, 60)
    return f"unas {h} h {m:02d} min"


def ancho_pedido(capa: QLayout) -> int:
    """Ancho que pide una fila horizontal con los textos de ahora.

    Se suma pieza por pieza, entrando en los segmentos: el tamaño que guardan los
    layouts recién se actualiza en el próximo ciclo de eventos. Lo oculto no cuenta
    y lo que se puede achicar sin límite (etiquetas con tamaño ignorado) tampoco."""
    margen = capa.contentsMargins()
    total, piezas = margen.left() + margen.right(), 0
    for i in range(capa.count()):
        item = capa.itemAt(i)
        w, sub = item.widget(), item.layout()
        if w is not None:
            if w.isHidden():
                continue
            if isinstance(w.layout(), QHBoxLayout):
                ancho = ancho_pedido(w.layout()) + 2  # el borde del segmento
            elif w.sizePolicy().horizontalPolicy() == QSizePolicy.Ignored:
                ancho = 0
            else:
                ancho = max(w.sizeHint().width(), w.minimumWidth())
        elif sub is not None:
            ancho = ancho_pedido(sub)
        else:
            total += item.sizeHint().width()  # espacios fijos (los estirables piden 0)
            continue
        total += ancho
        piezas += 1
    return total + max(0, capa.spacing()) * max(0, piezas - 1)


class VistaVideo(VistaComparacion):
    """La vista de comparación de la app, con su propia invitación a abrir un video.

    Al soltar archivos emite ``archivosSoltados`` con las fotos y los videos (como la
    vista de fotos): la ventana lleva cada cosa a su modo."""

    def _dibujar_invitacion(self, p: QPainter) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(28, 28, -28, -28)
        arrastrando = getattr(self, "_arrastrando_archivo", False)
        p.setPen(QPen(QColor(estilo.MAGENTA) if arrastrando else QColor("#464951"), 2, Qt.DashLine))
        p.setBrush(QColor(255, 255, 255, 8) if arrastrando else Qt.NoBrush)
        p.drawRoundedRect(rect, 18, 18)
        icono = iconos.pixmap("film", 40, estilo.TEXTO_TENUE)
        p.drawPixmap(round(rect.center().x() - 20), round(rect.center().y() - 86), icono)
        fuente = QFont(self.font())
        fuente.setPointSizeF(15)
        fuente.setBold(True)
        p.setFont(fuente)
        p.setPen(QColor(estilo.TEXTO))
        p.drawText(rect.adjusted(0, -10, 0, -10), Qt.AlignCenter, "Arrastrá un video aquí")
        fuente.setPointSizeF(10.5)
        fuente.setBold(False)
        p.setFont(fuente)
        p.setPen(QColor(estilo.TEXTO_TENUE))
        p.drawText(rect.adjusted(0, 44, 0, 44), Qt.AlignCenter,
                   "o hacé clic para elegir un archivo  ·  MP4, MOV, M4V, AVI, MKV, WEBM")
        fuente.setPointSizeF(9.5)
        p.setFont(fuente)
        p.drawText(rect.adjusted(0, 80, 0, 80), Qt.AlignCenter,
                   "Si soltás fotos, se abren en el modo de fotos")


class EditorVideo(QWidget):
    """El modo Video (ver el docstring del módulo).

    ``ventana``: la ventana principal. Abrir (Ctrl+O, el botón o un clic en la vista
    vacía) y soltar archivos pasan por ella, que rutea fotos y videos. Sin ventana
    (solo para usos aislados) abre videos por su cuenta.
    """

    videoCambiado = Signal()              # se abrió o se cerró un video
    exportacionCambiada = Signal(bool)    # empezó (True) o terminó (False) una exportación
    progresoExportacion = Signal(int, int)  # cuadros hechos y total
    exportacionLista = Signal(str, str)   # terminó mientras el editor no estaba a la vista: (texto, detalle)
    # "Editar el sonido en el modo Audio": el WAV con el sonido completo del original (en
    # %APPDATA%\NaturalShot PRO\temporal) y el video. La ventana abre el modo Audio con él.
    editarSonidoPedido = Signal(str, str)  # (ruta del WAV, ruta del video)

    def __init__(self, ventana: Optional["VentanaPrincipal"] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._ventana = ventana

        self.ruta: Optional[str] = None
        self.info: Optional[mv.InfoVideo] = None
        self.edicion: Optional[mv.EdicionVideo] = None
        self.audio = ma.AjustesAudio()  # cómo sale el sonido (se deshace junto con los cortes)
        # "Mejorar calidad" (sin IA). Como el filtro, sigue igual al abrir otro video; entra al historial.
        self.mejora = mm.AjustesMejora()
        # El sonido de otro archivo (modo Audio o "Cambiar el sonido por…"); None = el del video. Entra al
        # historial junto con lo demás.
        self.audio_externo: Optional[mv.AudioExterno] = None
        self.ultimo_sonido_para_audio: Optional[str] = None  # el último WAV preparado para el modo Audio
        self.tiempo = 0.0  # el cursor, en tiempo original (siempre en algo que se ve)
        self._mapa_de: tuple = (None, mv.MapaTiempo((), 0.0))  # (edición, su MapaTiempo)
        self.exportando = False
        self.ultima_exportacion: Optional[mv.ResultadoVideo] = None
        self.ultimo_audio: Optional[ma.ResultadoAudio] = None
        # Deshacer y rehacer: (edición, ajustes del sonido, ajustes de la mejora, sonido externo).
        self._deshacer: list[EstadoEditor] = []
        self._rehacer: list[EstadoEditor] = []
        # (control, momento): para juntar movimientos seguidos de un control del sonido o de la mejora.
        self._ultimo_cambio_sonido = ("", 0.0)
        self._largo_gesto = -1  # largo del historial con el paso que abrió ese gesto (solo se junta con él)
        self._cache_mejora = CacheMejora()  # cuadros ya mejorados (vista previa)
        # Lo que tardó mejorar un cuadro, por (tamaño de salida, ajustes): para estimar la exportación.
        self._medidas_mejora: dict[tuple, float] = {}
        self._tam_medido: Optional[tuple[int, int]] = None  # tamaño al que se midió _segundos_cuadro
        # 720p o 1080p elegido que se apagó al apagar la mejora (vuelve al prenderla de nuevo).
        self._resolucion_guardada: Optional[str] = None
        # Pico exacto de lo que se exporta, por (tramos, silencios): "Normalizar" al escuchar.
        self._picos: dict[tuple, float] = {}
        self._midiendo_pico: set[tuple] = set()
        self._clave_pico_pedida: Optional[tuple] = None  # lo último que se pidió medir (lo demás se descarta)
        self._con_sonido = False  # al reproducir, el reloj es el del sonido
        self._cancelar_audio = False
        self._generacion = 0
        self._generacion_info = 0
        self._generacion_completa = -1  # última generación mostrada a tamaño de exportación
        self._segundos_cuadro: Optional[float] = None  # lo que tardó un cuadro al tamaño de exportación
        self._reproduciendo = False
        self._sesion = 0
        self._t_base = 0.0
        self._t_reloj = 0.0
        self._en_vuelo = False
        self._vivo_lento = False
        self._cancelar_exportacion = False
        self._resultado_corto = False  # "0:02,00 de 0:03,00" en vez de "Duración final …" (poco ancho)
        # Botones de la línea de tiempo: 0 todos con nombre, 1 Entrada, Salida y Cortar solo con el ícono,
        # 2 además Borrar y Silenciar con el nombre corto, 3 todos solo con el ícono.
        self._iconos_linea = 0

        self._pool_cuadros = QThreadPool(self)
        self._pool_cuadros.setMaxThreadCount(1)
        self._pool_info = QThreadPool(self)
        self._pool_info.setMaxThreadCount(1)
        self._pool_exportar = QThreadPool(self)
        self._pool_exportar.setMaxThreadCount(1)
        self._pool_pico = QThreadPool(self)  # medir el pico para "Normalizar" al escuchar
        self._pool_pico.setMaxThreadCount(1)
        self._pool_guardar_audio = QThreadPool(self)  # "Guardar solo el audio" (aparte de la exportación)
        self._pool_guardar_audio.setMaxThreadCount(1)
        self._senales = SenalesTarea(self)
        self._senales.terminada.connect(self._tarea_terminada)
        self._senales.fallida.connect(self._tarea_fallida)

        self._timer_rapido = QTimer(self, singleShot=True, interval=10)
        self._timer_rapido.timeout.connect(self._lanzar_rapida)
        self._timer_completo = QTimer(self, singleShot=True, interval=450)
        self._timer_completo.timeout.connect(self._lanzar_completa)
        self._timer_reproducir = QTimer(self, interval=15)
        self._timer_reproducir.timeout.connect(self._tick)
        self._timer_sonido = QTimer(self, singleShot=True, interval=round(ESPERA_SONIDO * 1000))
        self._timer_sonido.timeout.connect(self._iniciar_sonido)

        # Sonido: lo que se escucha al reproducir y la forma de onda (las dos piezas son reutilizables).
        self.reproductor = ReproductorAudio(self)
        self.reproductor.establecer_silenciado(not self._sonido_vista_guardado())
        self.reproductor.fallo.connect(self._sonido_fallo)
        self.cargador_onda = CargadorOnda(self)

        self.panel_ajustes = PanelAjustes()
        self.panel_ajustes.ajustesCambiados.connect(self._al_cambiar_ajustes)
        self.panel_ajustes.pedirZona.connect(self._zona_no_disponible)
        self.panel_sonido = PanelSonido()
        self.panel_sonido.ajustesCambiados.connect(self._al_cambiar_sonido)
        self.panel_sonido.guardarAudioPedido.connect(self.guardar_audio)
        self.panel_sonido.cancelarGuardadoPedido.connect(self.cancelar_guardado_audio)
        self.panel_sonido.editarEnAudioPedido.connect(self.editar_sonido_en_audio)
        self.panel_sonido.cambiarSonidoPedido.connect(self.cambiar_sonido)
        self.panel_sonido.volverAlOriginalPedido.connect(self.volver_al_sonido_original)
        self.panel_mejora = PanelMejora()
        self.panel_mejora.ajustesCambiados.connect(self._al_cambiar_mejora)
        self._construir_interfaz()
        self._construir_acciones()
        self.cargador_onda.parcial.connect(self._onda_parcial)
        self.cargador_onda.lista.connect(self._onda_lista)
        self.cargador_onda.fallida.connect(self._onda_fallida)
        self._ocultar_zonas()
        self._actualizar_info()
        self._actualizar_sonido()
        self._actualizar_mejora()
        self._actualizar_habilitados()
        self.limpiar_temporales()
        self.simple = False
        self.establecer_simple(False)

    # ============================================================ video fácil
    def _solo_completo(self) -> list[QWidget]:
        """Lo que el "Video fácil" esconde: la línea de tiempo y los cortes, los atajos, Mejorar calidad,
        las secciones finas del filtro y las capas. Quedan el estilo, la intensidad, el sonido y exportar."""
        capas = self.panel_ajustes.boton_agregar_capa
        while capas is not None and not isinstance(capas, SeccionPlegable):
            capas = capas.parentWidget()
        widgets = [self._tarjeta_linea, self._tarjeta_atajos, self.panel_mejora, self.panel_ajustes.lado_ajustes]
        return widgets + ([capas] if capas is not None else [])

    def establecer_simple(self, simple: bool) -> None:
        """"Video fácil" (como el modo Fácil de las fotos): abrir, elegir un estilo y exportar el video
        entero. Solo cambia qué se ve: el filtro, el sonido y lo que se haya editado quedan como estaban."""
        self.simple = bool(simple)
        for w in self._solo_completo():
            w.setVisible(not self.simple)
        self.nota_simple.setVisible(self.simple)
        self.boton_simple.setText(" Todas las herramientas" if self.simple else " Video fácil")
        self.boton_simple.setToolTip("Mostrar la línea de tiempo, los cortes y todos los ajustes" if self.simple
                                     else "Solo elegir un estilo y exportar el video entero")
        self._actualizar_habilitados()

    # ============================================================ interfaz
    def _construir_interfaz(self) -> None:
        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        contenido = QVBoxLayout()
        contenido.setContentsMargins(14, 14, 14, 14)
        contenido.setSpacing(12)
        contenido.addWidget(self._construir_barra_herramientas())
        contenido.addWidget(self._construir_tarjeta_vista(), 1)
        self._tarjeta_linea = self._construir_tarjeta_linea()
        contenido.addWidget(self._tarjeta_linea)
        raiz.addLayout(contenido, 1)
        self._derecho = self._construir_panel_derecho()
        raiz.addWidget(self._derecho)
        # La columna izquierda la ubica la ventana (debajo de la marca y del selector de modo).
        self.lateral = self._construir_barra_lateral()

    @staticmethod
    def _segmento(botones) -> QFrame:
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

    @staticmethod
    def _boton(texto: str, icono: str, ayuda: str, tam: int = 16) -> QPushButton:
        b = QPushButton(texto)
        b.setIcon(iconos.icono(icono, tam))
        b.setIconSize(QSize(tam, tam))
        b.setToolTip(ayuda)
        b.setProperty("texto", texto)
        return b

    def _construir_barra_lateral(self) -> QWidget:
        """La columna izquierda del modo Video, sin la marca ni el selector (son de la ventana)."""
        lateral = QWidget()
        lateral.setObjectName("lateralVideo")
        capa = QVBoxLayout(lateral)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(0)

        panel = QWidget()
        capa_panel = QVBoxLayout(panel)
        capa_panel.setContentsMargins(16, 6, 12, 16)
        capa_panel.setSpacing(10)
        # El filtro del video es aparte del de las fotos; se puede volver a copiar.
        self.nota_filtro = QFrame()
        self.nota_filtro.setObjectName("notaEditor")
        fila_nota = QHBoxLayout(self.nota_filtro)
        fila_nota.setContentsMargins(10, 6, 6, 6)
        fila_nota.setSpacing(8)
        texto_nota = QLabel("El video tiene su propio filtro.")
        texto_nota.setObjectName("textoNotaEditor")
        texto_nota.setWordWrap(True)
        texto_nota.setToolTip("La primera vez que entrás a Video se copia el filtro de tus fotos. Desde ahí, lo "
                              "que cambies acá es solo del video (y lo que cambies en las fotos no lo toca).")
        self.boton_filtro_fotos = QPushButton(" Usar el de las fotos")
        self.boton_filtro_fotos.setObjectName("botonChico")
        self.boton_filtro_fotos.setIcon(iconos.icono("copy", 14))
        self.boton_filtro_fotos.setCursor(Qt.PointingHandCursor)
        self.boton_filtro_fotos.setToolTip("Copia al video el preset, la intensidad, las capas y los ajustes que "
                                           "estás usando en las fotos (en video las capas van a todo el cuadro).")
        fila_nota.addWidget(texto_nota, 1)
        fila_nota.addWidget(self.boton_filtro_fotos, 0, Qt.AlignVCenter)
        if self._ventana is None:
            self.nota_filtro.hide()
        # "Video fácil": una nota arriba y el botón para ir y volver de todas las herramientas.
        self.nota_simple = QLabel("Video fácil: elegí un estilo y su intensidad, y exportá el video entero "
                                  "(con su sonido). Para cortar o ajustar más, tocá \"Todas las herramientas\".")
        self.nota_simple.setObjectName("nota")
        self.nota_simple.setWordWrap(True)
        capa_panel.addWidget(self.nota_simple)
        self.boton_simple = QPushButton(" Video fácil")
        self.boton_simple.setObjectName("botonChico")
        self.boton_simple.setIcon(iconos.icono("sparkles", 14))
        self.boton_simple.setCursor(Qt.PointingHandCursor)
        self.boton_simple.clicked.connect(lambda: self.establecer_simple(not self.simple))
        capa_panel.addWidget(self.boton_simple)
        capa_panel.addWidget(self.nota_filtro)
        capa_panel.addWidget(self.panel_ajustes.lado_presets)
        capa_panel.addWidget(self._construir_tarjeta_info())
        self._tarjeta_atajos = self._construir_tarjeta_atajos()
        capa_panel.addWidget(self._tarjeta_atajos)
        capa_panel.addStretch(1)
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        desplazable.setWidget(panel)
        capa.addWidget(desplazable, 1)

        pie = QFrame()
        pie.setObjectName("pieLateral")
        fila = QHBoxLayout(pie)
        fila.setContentsMargins(18, 12, 12, 14)
        fila.setSpacing(10)
        self.pie_avatar = QLabel("—")
        self.pie_avatar.setObjectName("avatar")
        self.pie_avatar.setFixedSize(34, 34)
        self.pie_avatar.setAlignment(Qt.AlignCenter)
        fila.addWidget(self.pie_avatar)
        datos = QVBoxLayout()
        datos.setSpacing(0)
        self.pie_nombre = QLabel("Sin video abierto")
        self.pie_nombre.setObjectName("pieNombre")
        self.pie_detalle = QLabel("Procesado local · sin IA generativa")
        self.pie_detalle.setObjectName("pieDetalle")
        for etiqueta in (self.pie_nombre, self.pie_detalle):
            etiqueta.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        datos.addWidget(self.pie_nombre)
        datos.addWidget(self.pie_detalle)
        fila.addLayout(datos, 1)
        self.boton_cerrar_video = QPushButton()
        self.boton_cerrar_video.setObjectName("botonCerrarVideo")
        self.boton_cerrar_video.setIcon(iconos.icono("x", 16))
        self.boton_cerrar_video.setIconSize(QSize(16, 16))
        self.boton_cerrar_video.setFixedSize(30, 30)
        self.boton_cerrar_video.setCursor(Qt.PointingHandCursor)
        self.boton_cerrar_video.setToolTip("Cerrar el video (el archivo no se toca). Se pierden los cortes que no "
                                           "exportaste.")
        self.boton_cerrar_video.clicked.connect(lambda: self.cerrar_video())
        self.boton_cerrar_video.hide()
        fila.addWidget(self.boton_cerrar_video, 0, Qt.AlignVCenter)
        capa.addWidget(pie)
        return lateral

    def _construir_tarjeta_info(self) -> QWidget:
        tarjeta = SeccionPlegable("Video", "film", "Datos del video abierto", True, con_interruptor=False,
                                  plegable=False)
        grilla = QGridLayout()
        grilla.setHorizontalSpacing(10)
        grilla.setVerticalSpacing(5)
        self._datos_info: dict[str, QLabel] = {}
        for fila, (clave, texto) in enumerate((("tamano", "Tamaño"), ("fps", "Cuadros por segundo"),
                                               ("duracion", "Duración"), ("codec", "Códec"), ("audio", "Audio"))):
            nombre = QLabel(texto)
            nombre.setObjectName("etiquetaControl")
            valor = QLabel("—")
            valor.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            valor.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grilla.addWidget(nombre, fila, 0)
            grilla.addWidget(valor, fila, 1)
            self._datos_info[clave] = valor
        tarjeta.capa_cuerpo.addLayout(grilla)
        self.nota_video = QLabel("")
        self.nota_video.setObjectName("nota")
        self.nota_video.setWordWrap(True)
        tarjeta.capa_cuerpo.addWidget(self.nota_video)
        return tarjeta

    def _construir_tarjeta_atajos(self) -> QWidget:
        tarjeta = SeccionPlegable("Atajos", "info", "Teclado del editor de video", False, con_interruptor=False)
        grilla = QGridLayout()
        grilla.setHorizontalSpacing(10)
        grilla.setVerticalSpacing(6)
        for fila, (tecla, texto) in enumerate((
            ("Espacio", "Reproducir o pausar"),
            ("← →", "Cuadro anterior o siguiente"),
            ("J  L", "Un segundo atrás o adelante"),
            ("I  O", "Recortar lo de antes o lo de después del cursor"),
            ("S", "Cortar en el cursor"),
            ("Supr", "Borrar el tramo elegido (desaparece)"),
            ("R", "Recuperar lo borrado más cerca del cursor"),
            ("M", "Silenciar o devolver el sonido del tramo"),
            ("Ctrl+Z  Ctrl+Y", "Deshacer o rehacer (también lo borrado)"),
            ("Ctrl+Shift+V", "Volver a tus fotos (o Ctrl+E)"),
        )):
            chip = QLabel(tecla)
            chip.setObjectName("valorControl")
            chip.setAlignment(Qt.AlignCenter)
            texto_l = QLabel(texto)
            texto_l.setObjectName("etiquetaControl")
            texto_l.setWordWrap(True)
            grilla.addWidget(chip, fila, 0)
            grilla.addWidget(texto_l, fila, 1)
        grilla.setColumnStretch(1, 1)
        tarjeta.capa_cuerpo.addLayout(grilla)
        return tarjeta

    def _construir_barra_herramientas(self) -> QWidget:
        barra = QFrame()
        barra.setObjectName("barraHerramientas")
        fila = QHBoxLayout(barra)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(10)
        self._fila_barra = fila
        self.boton_abrir = QPushButton(" Abrir video")
        self.boton_abrir.setIcon(iconos.icono("film", 18, color="#ffffff"))
        self.boton_abrir.setIconSize(QSize(18, 18))
        self.boton_abrir.setObjectName("botonPrimario")
        self.boton_abrir.setToolTip("Abrir un video (Ctrl+O). También podés arrastrarlo a la vista. Si elegís "
                                    "fotos, se abren en el modo de fotos.")
        self.boton_abrir.setCursor(Qt.PointingHandCursor)
        self.boton_abrir.clicked.connect(self.elegir_archivo)
        fila.addWidget(self.boton_abrir)

        self.boton_deshacer = self._boton("", "undo-2", "Deshacer el último cambio: cortes, borrados, sonido o "
                                          "\"Mejorar calidad\" (Ctrl+Z). Deshacer un borrado lo vuelve a mostrar.", 18)
        self.boton_deshacer.clicked.connect(self.deshacer)
        self.boton_rehacer = self._boton("", "redo-2", "Rehacer (Ctrl+Y)", 18)
        self.boton_rehacer.clicked.connect(self.rehacer)
        fila.addWidget(self._segmento([self.boton_deshacer, self.boton_rehacer]))

        self.grupo_modo = QButtonGroup(self)
        self.grupo_modo.setExclusive(True)
        botones_modo = []
        for texto, modo, icono, ayuda in (
            ("Dividir", VistaComparacion.MODO_DIVIDIR, "square-split-horizontal", "Comparación con divisor arrastrable"),
            ("Antes", VistaComparacion.MODO_ANTES, "image", "Cuadro original"),
            ("Después", VistaComparacion.MODO_DESPUES, "wand-sparkles", "Cuadro con el filtro"),
            ("Lado a lado", VistaComparacion.MODO_LADO, "columns-2", "Antes y después uno al lado del otro"),
        ):
            boton = QPushButton(texto)
            boton.setIcon(iconos.icono(icono, 15))
            boton.setIconSize(QSize(15, 15))
            boton.setCheckable(True)
            boton.setToolTip(f"{texto}: {ayuda[0].lower()}{ayuda[1:]}")
            boton.setProperty("modo", modo)
            boton.setProperty("texto", texto)
            boton.setChecked(modo == VistaComparacion.MODO_DIVIDIR)
            self.grupo_modo.addButton(boton)
            botones_modo.append(boton)
        self.grupo_modo.buttonClicked.connect(lambda b: self.vista.establecer_modo(b.property("modo")))
        fila.addWidget(self._segmento(botones_modo))
        fila.addStretch(1)
        return barra

    def _construir_tarjeta_vista(self) -> QWidget:
        tarjeta = QFrame()
        tarjeta.setObjectName("tarjetaVista")
        self.tarjeta_vista = tarjeta
        capa = QVBoxLayout(tarjeta)
        capa.setContentsMargins(16, 12, 16, 14)
        capa.setSpacing(10)

        encabezado = QHBoxLayout()
        encabezado.setSpacing(8)
        punto = QLabel("●")
        punto.setObjectName("puntoEstado")
        titulo = QLabel("Vista previa")
        titulo.setObjectName("tituloTarjeta")
        self.etiqueta_estado = EtiquetaElidida(SIN_VIDEO)
        self.etiqueta_estado.setObjectName("estadoImagen")
        self.barra_ocupado = QProgressBar()
        self.barra_ocupado.setRange(0, 0)
        self.barra_ocupado.setMinimumWidth(30)
        self.barra_ocupado.setMaximumWidth(90)
        self.barra_ocupado.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.barra_ocupado.setTextVisible(False)
        self.barra_ocupado.hide()
        self.boton_alejar = self._boton("", "minus", "Alejar", 15)
        self.boton_acercar = self._boton("", "plus", "Acercar", 15)
        self.etiqueta_zoom = QLabel("—")
        self.etiqueta_zoom.setObjectName("etiquetaZoom")
        self.etiqueta_zoom.setMinimumWidth(50)
        self.etiqueta_zoom.setAlignment(Qt.AlignCenter)
        self.boton_ajustar = self._boton("", "maximize", "Ver el cuadro completo (Ctrl+0)", 15)
        self.boton_100 = QPushButton("100%")
        self.boton_100.setToolTip("Tamaño real de la exportación (Ctrl+1)")
        self.boton_200 = QPushButton("200%")
        self.boton_200.setToolTip("Al doble, para revisar el ruido y el grano (Ctrl+2)")
        encabezado.addWidget(punto)
        encabezado.addWidget(titulo)
        encabezado.addSpacing(10)
        encabezado.addWidget(self.etiqueta_estado, 1)
        encabezado.addWidget(self.barra_ocupado)
        encabezado.addSpacing(6)
        encabezado.addWidget(self._segmento([self.boton_alejar, self.etiqueta_zoom, self.boton_acercar]))
        encabezado.addWidget(self._segmento([self.boton_ajustar, self.boton_100, self.boton_200]))
        capa.addLayout(encabezado)

        self.vista = VistaVideo()
        self.vista.archivosSoltados.connect(self._soltar)
        self.vista.clicSinImagen.connect(self.elegir_archivo)
        self.vista.zoomCambiado.connect(lambda z: self.etiqueta_zoom.setText(f"{z * 100:.0f} %"))
        self.boton_alejar.clicked.connect(self.vista.alejar)
        self.boton_acercar.clicked.connect(self.vista.acercar)
        self.boton_ajustar.clicked.connect(self.vista.ajustar)
        self.boton_100.clicked.connect(lambda: self.vista.fijar_zoom(1.0))
        self.boton_200.clicked.connect(lambda: self.vista.fijar_zoom(2.0))
        capa.addWidget(self.vista, 1)

        # Transporte: reproducir, cuadro a cuadro y tiempo.
        transporte = QHBoxLayout()
        transporte.setSpacing(8)
        self._fila_transporte = transporte
        self.boton_inicio = self._boton("", "skip-back", "Ir a la entrada (Inicio)", 16)
        self.boton_inicio.clicked.connect(self.ir_al_inicio)
        self.boton_cuadro_atras = self._boton("", "step-back", "Cuadro anterior (←)", 16)
        self.boton_cuadro_atras.clicked.connect(lambda: self.mover_cuadros(-1))
        self.boton_reproducir = QPushButton()
        self.boton_reproducir.setObjectName("botonPrimario")
        self.boton_reproducir.setIcon(iconos.icono("play", 18, color="#ffffff"))
        self.boton_reproducir.setIconSize(QSize(18, 18))
        self.boton_reproducir.setFixedSize(52, 36)
        self.boton_reproducir.setCursor(Qt.PointingHandCursor)
        self.boton_reproducir.setToolTip("Reproducir o pausar (Espacio)")
        self.boton_reproducir.clicked.connect(self.alternar_reproduccion)
        self.boton_cuadro_adelante = self._boton("", "step-forward", "Cuadro siguiente (→)", 16)
        self.boton_cuadro_adelante.clicked.connect(lambda: self.mover_cuadros(1))
        self.boton_fin = self._boton("", "skip-forward", "Ir a la salida (Fin)", 16)
        self.boton_fin.clicked.connect(self.ir_al_final)
        transporte.addWidget(self._segmento([self.boton_inicio, self.boton_cuadro_atras]))
        transporte.addWidget(self.boton_reproducir)
        transporte.addWidget(self._segmento([self.boton_cuadro_adelante, self.boton_fin]))
        transporte.addSpacing(8)
        self.etiqueta_tiempo = QLabel("0:00,00 / 0:00,00")
        self.etiqueta_tiempo.setObjectName("tituloTarjeta")
        self.etiqueta_tiempo.setToolTip("Tiempo actual / duración del video que se va a exportar (sin lo borrado ni "
                                        "lo recortado: lo mismo que mide la línea de tiempo)")
        self.etiqueta_cuadro = QLabel("")
        self.etiqueta_cuadro.setObjectName("nota")
        self.etiqueta_cuadro.setToolTip("Cuadro del video que se va a exportar")
        transporte.addWidget(self.etiqueta_tiempo)
        transporte.addWidget(self.etiqueta_cuadro)
        transporte.addStretch(1)
        self.boton_vivo = self._boton(" Filtro al reproducir", "wand-sparkles",
                                      "Filtro al reproducir: al reproducir, mostrar el filtro a baja resolución. Si "
                                      "la PC no llega a tiempo, se muestra el original. Al pausar siempre se ve el "
                                      "cuadro procesado.", 15)
        self.boton_vivo.setCheckable(True)
        self.boton_vivo.setChecked(True)
        self.boton_vivo.toggled.connect(lambda _v: setattr(self, "_vivo_lento", False))
        # Sonido de la vista previa (se recuerda). No cambia lo que se exporta.
        self.boton_sonido = self._boton(" Sonido", "volume-2", "", 15)
        self.boton_sonido.setCheckable(True)
        self.boton_sonido.setChecked(not self.reproductor.silenciado)
        self.boton_sonido.toggled.connect(self._al_alternar_sonido_vista)
        transporte.addWidget(self._segmento([self.boton_sonido, self.boton_vivo]))
        capa.addLayout(transporte)
        return tarjeta

    def _construir_tarjeta_linea(self) -> QWidget:
        tarjeta = QFrame()
        tarjeta.setObjectName("tiraFotos")
        capa = QVBoxLayout(tarjeta)
        capa.setContentsMargins(14, 10, 14, 12)
        capa.setSpacing(8)
        cabecera = QHBoxLayout()
        cabecera.setSpacing(8)
        self._fila_linea = cabecera
        self.icono_linea = QLabel()
        self.icono_linea.setPixmap(iconos.pixmap("scissors", 16))
        self.titulo_linea = QLabel("LÍNEA DE TIEMPO")
        self.titulo_linea.setObjectName("tituloSeccion")
        cabecera.addWidget(self.icono_linea)
        cabecera.addWidget(self.titulo_linea)
        cabecera.addSpacing(6)
        self.boton_entrada = self._boton(" Entrada", "arrow-right-from-line",
                                         "Entrada (I): recorta lo de antes del cursor. Desaparece de la línea de "
                                         "tiempo y queda una marquita al principio para recuperarlo.", 15)
        self.boton_entrada.clicked.connect(self.marcar_entrada)
        self.boton_salida = self._boton(" Salida", "arrow-right-to-line",
                                        "Salida (O): recorta lo de después del cursor (el cuadro del cursor queda). "
                                        "Desaparece y queda una marquita al final para recuperarlo.", 15)
        self.boton_salida.clicked.connect(self.marcar_salida)
        self.boton_cortar = self._boton(" Cortar", "scissors", "Cortar: dividir el tramo en el cursor (S)", 15)
        self.boton_cortar.clicked.connect(self.cortar)
        self.boton_borrar = self._boton(" Borrar tramo", "trash-2", "", 15)
        self.boton_borrar.clicked.connect(self.borrar_tramo)
        self.boton_silenciar = self._boton(" Silenciar tramo", "volume-x", "", 15)
        self.boton_silenciar.clicked.connect(self.silenciar_tramo)
        cabecera.addWidget(self._segmento([self.boton_entrada, self.boton_salida]))
        cabecera.addWidget(self._segmento([self.boton_cortar, self.boton_borrar, self.boton_silenciar]))
        cabecera.addStretch(1)
        self.icono_reloj = QLabel()
        self.icono_reloj.setPixmap(iconos.pixmap("timer", 16))
        self.etiqueta_resultado = QLabel("Duración final —")
        self.etiqueta_resultado.setObjectName("etiquetaZoom")
        self.etiqueta_resultado.setToolTip("Lo que va a durar el video exportado (lo que ves en la línea de tiempo), "
                                           "de lo que dura el original")
        cabecera.addWidget(self.icono_reloj)
        cabecera.addWidget(self.etiqueta_resultado)
        capa.addLayout(cabecera)
        self.linea = LineaTiempo()
        self.linea.tiempoPedido.connect(self._tiempo_pedido)
        self.linea.seleccionCambiada.connect(lambda _i: self._al_cambiar_seleccion())
        self.linea.limitesPedidos.connect(self._limites_pedidos)
        self.linea.recuperarPedido.connect(self.recuperar)
        capa.addWidget(self.linea)
        # La pista de sonido, alineada con la de las miniaturas (mismo margen a los costados) y, como
        # la línea de tiempo, solo con lo que se exporta.
        self.pista_sonido = PistaOnda(solo_resultado=True)
        self.pista_sonido.tiempoPedido.connect(self._tiempo_pedido)
        self.pista_sonido.presionada.connect(self._pista_presionada)
        self.pista_sonido.setToolTip("Sonido de lo que se exporta: lo rosa está silenciado. Tocá o arrastrá para "
                                     "moverte; tocá un tramo y M lo silencia.")
        self.pista_sonido.hide()  # aparece al abrir un video
        capa.addWidget(self.pista_sonido)
        self.ayuda_linea = EtiquetaElidida(AYUDA_LINEA)  # cambia si hay algo borrado (_actualizar_resultado)
        self.ayuda_linea.setObjectName("nota")
        capa.addWidget(self.ayuda_linea)
        return tarjeta

    def _construir_panel_derecho(self) -> QWidget:
        derecho = QFrame()
        derecho.setObjectName("panelDerecho")
        derecho.setFixedWidth(ANCHO_DERECHO)
        capa = QVBoxLayout(derecho)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(0)
        encabezado = QHBoxLayout()
        encabezado.setContentsMargins(16, 16, 12, 8)
        encabezado.setSpacing(8)
        icono = QLabel()
        icono.setPixmap(iconos.pixmap("sliders-horizontal", 18))
        titulo = QLabel("AJUSTES DEL VIDEO")
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
        capa_panel.setSpacing(8)  # como entre las secciones de los ajustes
        # Sonido y Mejorar calidad arriba de los ajustes del filtro, en el mismo acordeón: al abrir
        # una tarjeta se cierran las demás. Al empezar queda abierta Sonido.
        capa_panel.addWidget(self.panel_sonido)
        capa_panel.addWidget(self.panel_mejora)
        capa_panel.addWidget(self.panel_ajustes.lado_ajustes)
        secciones = self.panel_ajustes._secciones
        propias = (self.panel_sonido, self.panel_mejora)

        def abrir_solo(tarjeta) -> None:
            self.panel_ajustes._abrir_solo(tarjeta)
            for otra in propias:
                if otra is not tarjeta:
                    otra.boton.setChecked(False)

        for tarjeta in propias:
            tarjeta.boton.toggled.connect(lambda abierta, t=tarjeta: abierta and abrir_solo(t))
        for caja in secciones.values():
            caja.boton.toggled.connect(lambda abierta: abierta and [t.boton.setChecked(False) for t in propias])
        abrir_solo(self.panel_sonido)
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        desplazable.setWidget(panel)
        capa.addWidget(desplazable, 1)
        pie = QFrame()
        pie.setObjectName("pieDerecho")
        capa_pie = QVBoxLayout(pie)
        capa_pie.setContentsMargins(16, 12, 16, 14)
        capa_pie.addWidget(self._construir_exportacion())
        capa.addWidget(pie)
        return derecho

    def _construir_exportacion(self) -> QWidget:
        caja = QWidget()
        capa = QVBoxLayout(caja)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(8)
        titulo = QLabel("EXPORTAR VIDEO")
        titulo.setObjectName("tituloSeccion")
        capa.addWidget(titulo)

        selector = QFrame()
        selector.setObjectName("selectorFormato")
        fila = QHBoxLayout(selector)
        fila.setContentsMargins(3, 3, 3, 3)
        fila.setSpacing(3)
        self.grupo_resolucion = QButtonGroup(self)
        self.grupo_resolucion.setExclusive(True)
        self.botones_resolucion: dict[str, QPushButton] = {}
        for nombre, ayuda in (("Original", "El tamaño del video original."),
                              ("1080p", "Full HD: el lado corto en 1080 píxeles."),
                              ("720p", "HD: el lado corto en 720 píxeles. Exporta más del doble de rápido.")):
            b = QPushButton(nombre)
            b.setObjectName("opcionFormato")
            b.setCheckable(True)
            b.setProperty("resolucion", nombre)
            b.setProperty("ayuda", ayuda)
            b.setToolTip(ayuda)
            b.setCursor(Qt.PointingHandCursor)
            self.grupo_resolucion.addButton(b)
            self.botones_resolucion[nombre] = b
            fila.addWidget(b, 1)
        self.botones_resolucion["Original"].setChecked(True)
        self.grupo_resolucion.buttonClicked.connect(lambda _b: self._al_cambiar_resolucion())
        capa.addWidget(selector)

        fila_calidad = QHBoxLayout()
        etiqueta = QLabel("Calidad")
        etiqueta.setObjectName("etiquetaControl")
        self.combo_calidad = QComboBox()
        for nombre in mv.CALIDADES:
            self.combo_calidad.addItem(TEXTO_CALIDAD.get(nombre, nombre), nombre)
        self.combo_calidad.setToolTip("Alta y Normal usan el ajuste para grano de x264: así el ruido del filtro "
                                      "no se pierde en la compresión.")
        self.combo_calidad.currentIndexChanged.connect(lambda _i: self._actualizar_estimacion())
        fila_calidad.addWidget(etiqueta)
        fila_calidad.addWidget(self.combo_calidad, 1)
        capa.addLayout(fila_calidad)
        # NS-101.2: codificar con la placa de video (si no hay o falla, sale igual con x264).
        self.check_gpu = QCheckBox("Usar la placa de video (más rápido)")
        self.check_gpu.setToolTip("Codifica con la placa de video (NVIDIA, Intel o AMD) si la PC tiene una. "
                                  "Es más rápido pero conserva algo menos del grano del filtro. Si no hay "
                                  "placa compatible, se exporta como siempre.")
        capa.addWidget(self.check_gpu)

        self.etiqueta_estimacion = QLabel("MP4 · H.264 + AAC")
        self.etiqueta_estimacion.setObjectName("nota")
        self.etiqueta_estimacion.setWordWrap(True)
        capa.addWidget(self.etiqueta_estimacion)

        self.boton_exportar = QPushButton("  Exportar video…")
        self.boton_exportar.setIcon(iconos.icono(iconos.GUARDAR, color="#ffffff"))
        self.boton_exportar.setIconSize(QSize(20, 20))
        self.boton_exportar.setObjectName("botonPrimario")
        self.boton_exportar.setToolTip("Guarda un MP4 nuevo con el filtro y los cortes (Ctrl+S). El original no se "
                                       "modifica. Mientras exporta podés volver a tus fotos: la exportación sigue.")
        self.boton_exportar.clicked.connect(self.exportar)
        capa.addWidget(self.boton_exportar)

        self.caja_progreso = QWidget()
        capa_prog = QVBoxLayout(self.caja_progreso)
        capa_prog.setContentsMargins(0, 2, 0, 0)
        capa_prog.setSpacing(6)
        self.barra_exportacion = QProgressBar()
        self.barra_exportacion.setRange(0, 1000)
        self.barra_exportacion.setTextVisible(False)
        fila_prog = QHBoxLayout()
        fila_prog.setSpacing(10)
        self.etiqueta_progreso = QLabel("Preparando…")
        self.etiqueta_progreso.setObjectName("nota")
        self.etiqueta_progreso.setWordWrap(True)
        self.boton_cancelar = self._boton(" Cancelar", "x", "Cancelar la exportación: no queda ningún archivo a medias", 15)
        self.boton_cancelar.setObjectName("botonChico")
        self.boton_cancelar.clicked.connect(self.cancelar_exportacion)
        fila_prog.addWidget(self.barra_exportacion, 1)
        fila_prog.addWidget(self.boton_cancelar)
        capa_prog.addLayout(fila_prog)
        capa_prog.addWidget(self.etiqueta_progreso)
        self.caja_progreso.hide()
        capa.addWidget(self.caja_progreso)
        caja.setToolTip("El original nunca se sobrescribe.")
        return caja

    def _construir_acciones(self) -> None:
        """Atajos del modo Video. Van en este widget: solo andan mientras se ve (en Fácil o
        Editor, Ctrl+Z, Ctrl+O y los demás son los de las fotos)."""
        for atajo, funcion in (
            (QKeySequence(Qt.Key_Space), self.alternar_reproduccion),
            (QKeySequence(Qt.Key_Right), lambda: self.mover_cuadros(1)),
            (QKeySequence(Qt.Key_Left), lambda: self.mover_cuadros(-1)),
            (QKeySequence(Qt.Key_L), lambda: self.mover_segundos(1.0)),
            (QKeySequence(Qt.Key_J), lambda: self.mover_segundos(-1.0)),
            (QKeySequence(Qt.Key_Home), self.ir_al_inicio),
            (QKeySequence(Qt.Key_End), self.ir_al_final),
            (QKeySequence(Qt.Key_I), self.marcar_entrada),
            (QKeySequence(Qt.Key_O), self.marcar_salida),
            (QKeySequence(Qt.Key_S), self.cortar),
            (QKeySequence(Qt.Key_Delete), self.borrar_tramo),
            (QKeySequence(Qt.Key_Backspace), self.borrar_tramo),
            (QKeySequence(Qt.Key_R), lambda: self.recuperar()),
            (QKeySequence(Qt.Key_M), self.silenciar_tramo),
            (QKeySequence.Undo, self.deshacer),
            (QKeySequence("Ctrl+Y"), self.rehacer),
            (QKeySequence("Ctrl+Shift+Z"), self.rehacer),
            (QKeySequence.Open, self.elegir_archivo),
            (QKeySequence.Save, self.exportar),
            (QKeySequence("Ctrl+0"), lambda: self.vista.ajustar()),
            (QKeySequence("Ctrl+1"), lambda: self.vista.fijar_zoom(1.0)),
            (QKeySequence("Ctrl+2"), lambda: self.vista.fijar_zoom(2.0)),
        ):
            accion = QAction(self)
            accion.setShortcut(atajo)
            accion.triggered.connect(funcion)
            self.addAction(accion)

    # ============================================================ ancho
    def resizeEvent(self, evento) -> None:
        super().resizeEvent(evento)
        self.compactar()

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        self.compactar()

    def compactar(self) -> None:
        """Acomoda las filas de botones al ancho que hay, de a pasos (como la barra de las
        fotos): primero se acortan los textos largos y después quedan solo los íconos (el
        nombre sigue en la ayuda)."""
        if not hasattr(self, "_fila_linea") or self.width() <= 0:
            return
        centro = self.width() - self._derecho.width() - 28  # la columna del centro, sin márgenes
        for nivel in range(3):  # barra de arriba
            for b in self.grupo_modo.buttons():
                b.setText("" if nivel >= 1 else b.property("texto"))
            self.boton_abrir.setText(" Abrir" if nivel >= 2 else " Abrir video")
            if ancho_pedido(self._fila_barra) <= centro:
                break
        for nivel in range(3):  # reproducir, tiempo, sonido y "Filtro al reproducir" (dentro de la tarjeta)
            for b in (self.boton_sonido, self.boton_vivo):
                b.setText("" if nivel >= 1 else b.property("texto"))
            self.etiqueta_cuadro.setVisible(nivel < 2)
            if ancho_pedido(self._fila_transporte) <= centro - 34:  # márgenes y borde de la tarjeta
                break
        for nivel in range(6):  # cabecera de la línea de tiempo: el título se va antes que los nombres
            self._resultado_corto = nivel >= 1
            self.titulo_linea.setVisible(nivel < 2)
            # Borrar y Silenciar conservan su nombre hasta el final: dicen qué va a pasar (Silenciar
            # alterna). Se mide con el más largo de cada par, así entra cuando el texto cambia.
            self._iconos_linea = max(0, nivel - 2)
            self._textos_linea(medir=True)
            if ancho_pedido(self._fila_linea) <= centro - 30:
                break
        self._textos_linea()

    def _tramo_objetivo(self) -> int:
        """El tramo sobre el que actúan Borrar y Silenciar: el elegido o, si no hay, el del cursor."""
        return self.linea.seleccion if self.linea.seleccion >= 0 else self.edicion.indice_en(self.tiempo)

    def _textos_linea(self, medir: bool = False) -> None:
        """Textos de la cabecera de la línea de tiempo según el ancho (``compactar``) y el tramo elegido.

        ``medir``: Silenciar con el más largo de sus dos textos (para elegir cuánto compactar)."""
        for b in (self.boton_entrada, self.boton_salida, self.boton_cortar):
            b.setText("" if self._iconos_linea >= 1 else b.property("texto"))
        if self.edicion is None:
            self.etiqueta_resultado.setText("—" if self._resultado_corto else "Duración final —")
        else:
            final, total = formato_tiempo(self.edicion.duracion_resultante()), formato_tiempo(self.edicion.duracion)
            self.etiqueta_resultado.setText(f"{final} de {total}" if self._resultado_corto else
                                            f"Duración final {final}  de {total}")
        solo_icono, corto = self._iconos_linea >= 3, self._iconos_linea == 2
        borrado = silenciado = medir
        queda_algo = True
        if self.edicion is not None and not medir:
            i = self._tramo_objetivo()
            s = self.edicion.segmentos[i]
            borrado = s.borrado  # no debería pasar: lo borrado no se ve ni se elige
            silenciado = self.audio.silenciado(s.inicio, s.fin)
            queda_algo = bool(self.edicion.con_borrado(i).tramos_conservados())
        devolver, silenciar = (" Devolver sonido", " Silenciar") if corto else (" Devolver el sonido",
                                                                                " Silenciar tramo")
        self.boton_borrar.setText("" if solo_icono else (" Borrar" if corto else " Borrar tramo"))
        if medir:
            self.boton_silenciar.setText("" if solo_icono else devolver)
            return
        if self.edicion is not None:
            self.boton_borrar.setEnabled(queda_algo and not borrado)
        self.boton_borrar.setToolTip(
            "Es lo único que queda: no se puede borrar todo el video." if not queda_algo else
            "Borrar el tramo elegido (Supr): desaparece de la línea de tiempo y no se exporta. Si no elegiste "
            "ninguno, el del cursor. Queda una marquita rosa en la unión: tocala para recuperarlo (o Ctrl+Z).")
        self.boton_silenciar.setText("" if solo_icono else (devolver if silenciado else silenciar))
        self.boton_silenciar.setIcon(iconos.icono("volume-2" if silenciado else "volume-x", 15))
        hay_sonido = self._hay_sonido()
        self.boton_silenciar.setEnabled(hay_sonido and not borrado and not self.audio.quitar)
        if not hay_sonido:
            ayuda = "Este video no tiene sonido." if self.info is not None else "Silenciar el tramo elegido (M)"
        elif self.audio.quitar:
            ayuda = "El sonido está quitado (tarjeta Sonido): no hay nada que silenciar."
        elif borrado:
            ayuda = "Ese tramo está borrado: no se exporta, así que no hace falta silenciarlo."
        elif silenciado:
            ayuda = "Devolverle el sonido al tramo elegido (M)"
        else:
            ayuda = ("Silenciar el tramo elegido (M): se exporta con la imagen pero sin sonido. Actúa sobre el "
                     "mismo tramo que Borrar (el elegido o, si no elegiste ninguno, el del cursor). Para "
                     "silenciar una parte cualquiera, cortá al principio y al final (S).")
        self.boton_silenciar.setToolTip(ayuda)

    # ============================================================ panel
    def _ocultar_zonas(self) -> None:
        """En video las capas van a todo el cuadro: se oculta "Dónde" (zonas de las fotos)."""
        for fila in self.panel_ajustes.capas():
            for nombre in ("combo_zona", "boton_marcar", "opciones_zona"):
                w = getattr(fila, nombre, None)
                if isinstance(w, QWidget):
                    w.hide()
            for etiqueta in fila.findChildren(QLabel):
                if etiqueta.text() == "Dónde":
                    etiqueta.hide()

    def _zona_no_disponible(self, fila, _forma: str) -> None:
        if hasattr(fila, "zona_cancelada"):
            fila.zona_cancelada()
        self.etiqueta_estado.setText("En video las capas se aplican a todo el cuadro (las zonas son para fotos).")

    def cargar_pila(self, pila: Sequence[Ajustes]) -> None:
        """Pone en el panel una pila de capas (por ejemplo, la de las fotos)."""
        pila = tuple(pila or ())
        if not pila:
            return
        presets = todos_los_presets()

        def nombre_de(ajustes: Ajustes, base: bool) -> str:
            for nombre, p in presets.items():
                if replace(p, intensidad=ajustes.intensidad, semilla=ajustes.semilla if base else p.semilla) == ajustes:
                    return nombre
            if base and replace(NEUTRO, intensidad=ajustes.intensidad, semilla=ajustes.semilla) == ajustes:
                return SIN_EFECTO
            campos = [c for c in Ajustes.nombres() if c not in ("intensidad", "semilla")]
            return min(presets, key=lambda n: sum(getattr(presets[n], c) != getattr(ajustes, c) for c in campos))

        estado = {
            "preset": nombre_de(pila[0], True),
            "ajustes": pila[0],
            "capas": [(nombre_de(a, False), a.intensidad, None) for a in pila[1:5]],
        }
        self.panel_ajustes.restaurar(estado)
        self._ocultar_zonas()

    def cargar_estado_panel(self, estado: dict) -> None:
        """Copia exacta del panel de las fotos (``PanelAjustes.estado()``), sin las zonas."""
        estado = dict(estado)
        estado["capas"] = [(c[0], c[1], None) for c in estado.get("capas", [])]
        self.panel_ajustes.restaurar(estado)
        self._ocultar_zonas()

    def _al_cambiar_ajustes(self, _pila) -> None:
        self._ocultar_zonas()
        if self._reproduciendo:
            return  # el próximo cuadro ya sale con los ajustes nuevos
        self._solicitar_render()

    # ============================================================ abrir y cerrar
    def elegir_archivo(self) -> None:
        """Abrir (Ctrl+O): con la ventana, el diálogo de fotos y videos (cada cosa va a su modo)."""
        if self._ventana is not None:
            self._ventana.elegir_archivo()
            return
        inicio = str(Path(self.ruta).parent) if self.ruta else str(Path.home() / "Videos")
        ruta, _ = QFileDialog.getOpenFileName(self, "Abrir video", inicio, f"{FILTRO_VIDEO};;Todos los archivos (*.*)")
        if ruta:
            self.abrir(ruta)

    def _soltar(self, rutas: list) -> None:
        """Archivos soltados sobre la vista: la ventana manda las fotos a la tira y el video acá."""
        if self._ventana is not None:
            self._ventana.abrir_rutas(rutas)
            return
        videos = [r for r in rutas if Path(r).suffix.lower() in mv.EXTENSIONES_VIDEO]
        if videos:
            self.abrir(videos[0])

    def tiene_cambios(self) -> bool:
        """Si el video abierto tiene cortes, borrados, entrada, salida o cambios de sonido (se
        pierden al cerrarlo)."""
        if self.info is None or self.edicion is None:
            return False
        return (self.edicion != mv.EdicionVideo.nueva(self.info.duracion, self.info.fps)
                or not self.audio.sin_cambios() or self.audio_externo is not None)

    def es_el_abierto(self, ruta: str) -> bool:
        return self.ruta is not None and mv._misma_ruta(Path(ruta), Path(self.ruta))

    def confirmar_reemplazo(self, ruta: str) -> bool:
        """Antes de abrir ``ruta``: si el video abierto tiene cortes, pregunta si se reemplaza.
        True si se puede abrir (o si es el mismo video, que queda como está)."""
        if self.es_el_abierto(ruta) or not self.tiene_cambios():
            return True
        respuesta = QMessageBox.question(
            self, "Abrir otro video",
            f"{Path(self.ruta).name} tiene cortes o cambios de sonido que no exportaste: si abrís "
            f"{Path(ruta).name}, se pierden.\n\n¿Abrirlo igual?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return respuesta == QMessageBox.Yes

    def abrir(self, ruta: str, confirmar: bool = True) -> bool:
        """Abre un video. Si el que está abierto tiene cortes, pregunta antes de reemplazarlo.
        Devuelve False si no se abrió (se eligió seguir con el actual)."""
        ruta = str(ruta)
        if self.es_el_abierto(ruta):
            return True  # ya está abierto: se conservan sus cortes
        if confirmar and not self.confirmar_reemplazo(ruta):
            return False
        self.pausar(render=False)
        self._generacion_info += 1
        generacion = self._generacion_info
        self.etiqueta_estado.setText(f"Abriendo {Path(ruta).name}…")
        self.barra_ocupado.show()
        self._pool_info.start(Tarea("info", generacion, lambda _c: (ruta, mv.info_video(ruta)), self._senales))
        return True

    def cerrar_video(self, confirmar: bool = True) -> bool:
        """Cierra el video abierto (el archivo no se toca) y vuelve a la invitación a abrir uno."""
        if self.info is None:
            return True
        if self.exportando or self.panel_sonido.guardando:
            QMessageBox.information(self, "Exportación en curso",
                                    "Se está exportando este video (o guardando su audio). Esperá a que termine o "
                                    "cancelalo para cerrarlo.")
            return False
        if confirmar and self.tiene_cambios():
            respuesta = QMessageBox.question(
                self, "Cerrar el video",
                f"{Path(self.ruta).name} tiene cortes o cambios de sonido que no exportaste y se pierden.\n\n"
                "¿Cerrarlo igual?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if respuesta != QMessageBox.Yes:
                return False
        self.pausar(render=False)
        self._timer_rapido.stop()
        self._timer_completo.stop()
        self._generacion += 1
        self._generacion_info += 1
        self.ruta = self.info = self.edicion = None
        self.audio = ma.AjustesAudio()
        self.audio_externo = None
        self._deshacer.clear()
        self._rehacer.clear()
        self._ultimo_cambio_sonido = ("", 0.0)
        self._picos.clear()
        self._midiendo_pico.clear()
        self._segundos_cuadro = None
        self._tam_medido = None
        self._cache_mejora.vaciar()
        self.tiempo = 0.0
        self.linea.establecer_edicion(None)
        self.linea.establecer_miniaturas([])
        self.linea.establecer_tiempo(0.0)
        self.cargador_onda.cancelar()
        self.pista_sonido.vaciar()
        self.pista_sonido.hide()
        self._actualizar_sonido()
        self._actualizar_mejora()
        self.vista.vaciar()
        self.etiqueta_zoom.setText("—")
        self.barra_ocupado.hide()
        self._actualizar_info()
        self._actualizar_resultado()
        self._actualizar_tiempo()
        self._actualizar_habilitados()
        self._ocupado()
        self.etiqueta_estado.setText(SIN_VIDEO)
        self._pool_cuadros.waitForDone(2000)
        mv.cerrar_lectores()
        self.videoCambiado.emit()
        return True

    def _info_lista(self, ruta: str, info: mv.InfoVideo) -> None:
        self.ruta, self.info = ruta, info
        self.edicion = mv.EdicionVideo.nueva(info.duracion, info.fps)
        self.audio = ma.AjustesAudio()
        self.audio_externo = None
        self._deshacer.clear()
        self._rehacer.clear()
        self._ultimo_cambio_sonido = ("", 0.0)
        self._picos.clear()
        self._midiendo_pico.clear()
        self._segundos_cuadro = None
        self._vivo_lento = False
        self.tiempo = 0.0
        self.linea.establecer_edicion(self.edicion)
        self.linea.establecer_miniaturas([])
        self.linea.seleccionar(-1)
        self.linea.establecer_tiempo(0.0)
        # La pista de sonido: la forma de onda se lee en segundo plano, con entregas parciales.
        self.pista_sonido.show()
        self.pista_sonido.establecer_tiempo(0.0)
        self.pista_sonido.establecer_seleccion(None)
        self._cargar_onda()
        self._actualizar_sonido()
        # Resolución sugerida: 1080p si el video es más grande (exporta mucho más rápido). Con "Mejorar
        # calidad" prendida y un video chico, 720p (lo acordado: un video chico queda como un buen 720p).
        defecto = "1080p" if min(info.ancho, info.alto) > 1080 else "Original"
        if self.mejora.activa and min(info.ancho, info.alto) < 720:
            defecto = "720p"
        self._resolucion_guardada = None
        self.botones_resolucion[defecto].setChecked(True)
        self._cache_mejora.vaciar()
        self._tam_medido = None
        self._actualizar_info()
        self._actualizar_mejora()
        self._actualizar_resultado()
        self._actualizar_tiempo()
        self._actualizar_habilitados()
        generacion = self._generacion_info

        def miniaturas(_c):
            return [(t, _a_qimage(rgb)) for t, rgb in mv.miniaturas(ruta, CANTIDAD_MINIATURAS, ALTO_MINIATURA)]

        self._pool_info.start(Tarea("miniaturas", generacion, miniaturas, self._senales))
        self._solicitar_render()
        self.compactar()
        self.videoCambiado.emit()

    def _actualizar_info(self) -> None:
        info = self.info
        if info is None:
            for valor in self._datos_info.values():
                valor.setText("—")
            self.nota_video.setText("Abrí un video para editarlo con el mismo filtro que las fotos.")
            self.nota_video.setVisible(True)
            self.pie_avatar.setText("—")
            self.pie_nombre.setText("Sin video abierto")
            self.pie_nombre.setToolTip("")
            self.pie_detalle.setText("Procesado local · sin IA generativa")
            for nombre, boton in self.botones_resolucion.items():
                boton.setText(nombre)
                boton.setEnabled(True)
                boton.setToolTip(boton.property("ayuda"))
            return
        orientacion = "vertical" if info.alto > info.ancho else "horizontal"
        self._datos_info["tamano"].setText(f"{info.ancho} × {info.alto} · {orientacion}")
        self._datos_info["fps"].setText(f"{info.fps:.2f}".rstrip("0").rstrip(",.").replace(".", ","))
        self._datos_info["duracion"].setText(f"{formato_tiempo(info.duracion)} · {info.cuadros} cuadros")
        self._datos_info["codec"].setText(info.codec.upper())
        if info.tiene_audio:
            canales = {1: "mono", 2: "estéreo"}.get(info.canales_audio, f"{info.canales_audio} canales")
            self._datos_info["audio"].setText(f"{info.codec_audio.upper()} · {info.frecuencia_audio // 1000} kHz · {canales}")
        else:
            self._datos_info["audio"].setText("Sin audio")
        notas = []
        if info.rotacion:
            notas.append(f"Grabado con el celular girado: se endereza solo ({GIRO.get(info.rotacion, '')}).")
        if info.hdr:
            notas.append("Video HDR: se pasa a SDR sin mapeo de tonos, los colores pueden verse lavados.")
        if not info.tiene_audio:
            notas.append("El video no tiene sonido.")
        self.nota_video.setText(" ".join(notas))
        self.nota_video.setVisible(bool(notas))
        nombre = Path(info.ruta).name
        self.pie_avatar.setText((Path(info.ruta).stem[:1] or "V").upper())
        self.pie_nombre.setText(self.pie_nombre.fontMetrics().elidedText(nombre, Qt.ElideMiddle, 220))
        self.pie_detalle.setText(f"{info.ancho} × {info.alto} · {self._datos_info['fps'].text()} fps · "
                                 f"{formato_tiempo(info.duracion, decimas=False)}")
        self.pie_nombre.setToolTip(info.ruta)
        self.etiqueta_estado.setText(f"{nombre}  ·  {info.ancho} × {info.alto}  ·  {formato_tiempo(info.duracion)}")
        self._actualizar_resoluciones()

    def _actualizar_resoluciones(self) -> None:
        if self.info is None:
            return
        original = (self.info.ancho, self.info.alto)
        agrandar = self.mejora.activa  # con "Mejorar calidad", 720p y 1080p también agrandan
        for nombre, boton in self.botones_resolucion.items():
            w, h = mv.tamano_salida(*original, nombre, agrandar=agrandar)
            igual = nombre != "Original" and (w, h) == mv.tamano_salida(*original, None)
            # Apagado (el video ya es de ese tamaño o menor) no muestra el tamaño del original, que
            # confundía ("1080p 640 × 360"): dice qué hace falta para usarlo.
            boton.setText(f"{nombre}\ncon la mejora" if igual else f"{nombre}\n{w} × {h}")
            boton.setEnabled(not igual)
            if igual:
                wa, ha = mv.tamano_salida(*original, nombre, agrandar=True)
                ayuda = (f"El video ya es de este tamaño o menor y, sin \"Mejorar calidad\", nunca se agranda. "
                         f"Prendé Mejorar calidad para agrandar a {wa} × {ha}, sin IA.")
            elif agrandar and nombre != "Original" and min(w, h) > min(original):
                ayuda = f"{boton.property('ayuda')} Con \"Mejorar calidad\": se agranda a {w} × {h}, sin IA."
            else:
                ayuda = boton.property("ayuda")
            boton.setToolTip(ayuda)
        elegido = self.grupo_resolucion.checkedButton()
        if elegido is not None and not elegido.isEnabled():
            # Se apagó la mejora con 720p o 1080p elegido: se ve "Original" (lo que se va a exportar) y
            # se recuerda lo elegido para cuando se vuelva a prender (por ejemplo, con Ctrl+Y).
            self._resolucion_guardada = elegido.property("resolucion")
            self.botones_resolucion["Original"].setChecked(True)
        elif self._resolucion_guardada and self._resolucion() == "Original":
            guardada = self.botones_resolucion.get(self._resolucion_guardada)
            if guardada is not None and guardada.isEnabled():
                guardada.setChecked(True)
                self._resolucion_guardada = None

    def _resolucion(self) -> str:
        b = self.grupo_resolucion.checkedButton()
        return b.property("resolucion") if b is not None and b.isEnabled() else "Original"

    def _tam_salida(self) -> tuple[int, int]:
        return mv.tamano_salida(self.info.ancho, self.info.alto, self._resolucion(), agrandar=self.mejora.activa)

    def _al_cambiar_resolucion(self) -> None:
        self._resolucion_guardada = None  # la eligió a mano
        self._segundos_cuadro = None
        self._actualizar_estimacion()
        self._actualizar_mejora()  # la nota dice a qué tamaño se exporta
        self._solicitar_render()

    # ============================================================ tiempo
    def _ultimo(self) -> float:
        """Comienzo del último cuadro."""
        if self.info is None:
            return 0.0
        return max(0.0, math.ceil(self.info.duracion * self.info.fps - 1e-6 - 1) / self.info.fps)

    def _ajustar(self, t: float) -> float:
        return min(self.edicion.ajustar(t), self._ultimo()) if self.edicion is not None else 0.0

    @property
    def mapa(self) -> mv.MapaTiempo:
        """Tiempo original ↔ tiempo del resultado (lo que muestra la línea de tiempo), para la edición de ahora."""
        if self._mapa_de[0] is not self.edicion:
            mapa = mv.MapaTiempo.de_edicion(self.edicion) if self.edicion is not None else mv.MapaTiempo((), 0.0)
            self._mapa_de = (self.edicion, mapa)
        return self._mapa_de[1]

    @property
    def tiempo_resultado(self) -> float:
        """Dónde está el cursor en el video que se va a exportar (segundos del resultado)."""
        return self.mapa.a_resultado(self.tiempo)

    def _ultimo_visible(self) -> float:
        """Comienzo del último cuadro que se ve (el último del último tramo conservado)."""
        tramos = self.mapa.tramos
        if self.info is None or not tramos:
            return self._ultimo()
        a, b = tramos[-1]
        fps = self.info.fps
        return max(a, min(self._ultimo(), (math.ceil(b * fps - 1e-6) - 1) / fps))

    def _visible(self, t: float) -> float:
        """``t`` si se ve; si cae en algo borrado o recortado, el comienzo de lo que sigue (donde
        quedó la unión) o, después de todo, el último cuadro que se ve."""
        mapa = self.mapa
        if not mapa.tramos or mapa.visible(t):
            return t
        for a, _b in mapa.tramos:
            if t < a:
                return a
        return self._ultimo_visible()

    def ir_a(self, segundos: float, arrastrando: bool = False) -> None:
        """Lleva el cursor al instante ``segundos`` del original (al cuadro más cercano). Si ahí no se
        ve nada (está borrado o recortado), a la unión: el comienzo de lo que sigue."""
        if self.info is None:
            return
        self.tiempo = self._visible(self._ajustar(segundos))
        self.linea.establecer_tiempo(self.tiempo)
        self.pista_sonido.establecer_tiempo(self.tiempo)
        self._actualizar_tiempo()
        if self._reproduciendo:
            self._t_base, self._t_reloj = self.tiempo_resultado, time.monotonic()
            # El sonido vuelve desde acá cuando el cursor se queda quieto (arrastrando, ni suena).
            self.reproductor.detener()
            self._con_sonido = False
            self._timer_sonido.start()
        else:
            self._solicitar_render(arrastrando)

    def ir_a_resultado(self, segundos: float, arrastrando: bool = False) -> None:
        """Lleva el cursor al segundo ``segundos`` del resultado (lo que mide la línea de tiempo)."""
        mapa = self.mapa
        self.ir_a(mapa.a_original(min(max(0.0, segundos), mapa.duracion)), arrastrando)

    def _tiempo_pedido(self, segundos: float, arrastrando: bool) -> None:
        self.ir_a(segundos, arrastrando)

    def mover_cuadros(self, n: int) -> None:
        """Cuadro a cuadro por lo que se ve (salta las uniones como si no hubiera nada en medio)."""
        if self.info is None:
            return
        self.pausar(render=False)
        self.ir_a_resultado(self.tiempo_resultado + n / self.info.fps)

    def mover_segundos(self, segundos: float) -> None:
        if self.info is None:
            return
        self.pausar(render=False)
        self.ir_a_resultado(self.tiempo_resultado + segundos)

    def ir_al_inicio(self) -> None:
        if self.edicion is not None:
            self.pausar(render=False)
            self.ir_a_resultado(0.0)

    def ir_al_final(self) -> None:
        if self.edicion is not None:
            self.pausar(render=False)
            self.ir_a(self._ultimo_visible())

    def _actualizar_tiempo(self) -> None:
        """El tiempo y el cuadro del cursor, en el video que se va a exportar."""
        if self.info is None or self.edicion is None:
            self.etiqueta_tiempo.setText("0:00,00 / 0:00,00")
            self.etiqueta_cuadro.setText("")
            self._reservar_ancho_cuadro("")
            return
        mapa = self.mapa
        r = mapa.a_resultado(self.tiempo)
        self.etiqueta_tiempo.setText(f"{formato_tiempo(r)} / {formato_tiempo(mapa.duracion)}")
        total = max(1, int(round(mapa.duracion * self.info.fps)))
        self.etiqueta_cuadro.setText(f"cuadro {min(total, mv.indice_en(r, self.info.fps) + 1)} de {total}")
        self._reservar_ancho_cuadro(f"cuadro {total} de {total}")

    def _reservar_ancho_cuadro(self, texto_mas_largo: str) -> None:
        """"cuadro 121 de 300" se ensancha al avanzar: se reserva el ancho del más largo, así la fila del
        transporte no salta mientras reproduce y ``compactar`` la acomoda una sola vez (antes, al
        ensancharse, apretaba el tiempo y lo cortaba)."""
        ancho = self.etiqueta_cuadro.fontMetrics().horizontalAdvance(texto_mas_largo) + 2 if texto_mas_largo else 0
        if ancho != self.etiqueta_cuadro.minimumWidth():
            self.etiqueta_cuadro.setMinimumWidth(ancho)
            self.compactar()

    # ============================================================ render
    def _solicitar_render(self, arrastrando: bool = False) -> None:
        if self.info is None:
            return
        self._generacion += 1
        self._timer_rapido.start()
        if arrastrando:
            self._timer_completo.stop()
        else:
            self._timer_completo.start()
        self._ocupado()

    def _vigente(self) -> int:
        return self._generacion

    def _datos_render(self):
        return (self.ruta, self.tiempo, mv.indice_en(self.tiempo, self.info.fps), self.panel_ajustes.pila(),
                self._tam_salida())

    def _datos_mejora(self) -> Optional[DatosMejora]:
        """Lo que hace falta para ver el cuadro mejorado como en la exportación (None si está apagada)."""
        if not self.mejora.activa or self.info is None or self.edicion is None:
            return None
        nativo = (self.info.ancho, self.info.alto)
        tramos = tuple(mv.normalizar_tramos(self.edicion.tramos_conservados(), self.info.duracion))
        return DatosMejora(self.mejora, tramos, self.info.fps, self._ultimo(),
                           mv.tamano_lectura(*nativo, *self._tam_salida()), nativo)

    def _lanzar_rapida(self) -> None:
        if self.info is None or self._reproduciendo:
            return
        ruta, t, indice, pila, tam = self._datos_render()
        completa = max(tam) <= LADO_RAPIDO
        mejora = self._datos_mejora()
        cache = self._cache_mejora

        def render(cancelado):
            if completa:  # video chico: directamente al tamaño de exportación
                antes = mv.cuadro_en(ruta, t, max(tam))
                inicio = time.perf_counter()
                despues = mv.procesar_cuadro_seguro(antes, pila, indice, 1.0, cancelado)
                return _a_qimage(antes), _a_qimage(despues), tam, True, time.perf_counter() - inicio, None
            antes = mv.cuadro_en(ruta, t, LADO_VISTA)
            chico, _ = reducir_para_vista(antes, LADO_RAPIDO)
            escala = min(1.0, max(chico.shape[:2]) / max(tam))
            despues = mv.procesar_cuadro_seguro(chico, pila, indice, escala, cancelado)
            return _a_qimage(antes), _a_qimage(despues), tam, False, None, None

        def render_mejora(cancelado):
            # La vista rápida no mejora: la mejora espera a que el cursor se quede quieto (la completa),
            # así arrastrar no acumula trabajo ni compite con una exportación. Si el cuadro ya está
            # mejorado en la caché, se usa; si no, por ahora el filtro sobre el original.
            grande = cache.obtener(clave_mejora(ruta, t, *tam, mejora))
            if grande is None:
                resultado = render(cancelado)
                return resultado[:3] + (False, None, None)  # todavía falta la mejora: no es la completa
            if completa:  # video chico: directamente al tamaño de exportación
                despues = mv.procesar_cuadro_seguro(grande, pila, indice, 1.0, cancelado)
                antes = agrandar_simple(leer_para_mejora(ruta, t, mejora), *tam)
                return _a_qimage(antes), _a_qimage(despues), tam, True, None, None
            chico, _ = reducir_para_vista(grande, LADO_RAPIDO)
            antes = mv.cuadro_en(ruta, t, LADO_VISTA)
            escala = min(1.0, max(chico.shape[:2]) / max(tam))
            despues = mv.procesar_cuadro_seguro(chico, pila, indice, escala, cancelado)
            return _a_qimage(antes), _a_qimage(despues), tam, False, None, None

        self._pool_cuadros.start(Tarea("cuadro", self._generacion, render if mejora is None else render_mejora,
                                       self._senales, self._vigente))

    def _lanzar_completa(self) -> None:
        if self.info is None or self._reproduciendo:
            return
        ruta, t, indice, pila, tam = self._datos_render()
        mejora = self._datos_mejora()
        if max(tam) <= LADO_RAPIDO and (mejora is None or self._generacion_completa == self._generacion):
            return  # ya la hizo la rápida (con la mejora, solo si el cuadro mejorado estaba en la caché)
        cache = self._cache_mejora

        def render(cancelado):
            if mejora is not None:
                return self._render_mejorado_completo(ruta, t, indice, pila, tam, mejora, cache, cancelado)
            antes = mv.cuadro_en(ruta, t, max(tam))
            if cancelado():
                return None
            inicio = time.perf_counter()
            despues = mv.procesar_cuadro_seguro(antes, pila, indice, 1.0, cancelado)
            return _a_qimage(antes), _a_qimage(despues), tam, True, time.perf_counter() - inicio, None

        self._pool_cuadros.start(Tarea("cuadro", self._generacion, render, self._senales, self._vigente))

    @staticmethod
    def _render_mejorado_completo(ruta: str, t: float, indice: int, pila, tam: tuple[int, int],
                                  mejora: DatosMejora, cache: CacheMejora, cancelado):
        """Al tamaño de exportación, como sale en el archivo: mejora (con los vecinos del tramo) y filtro.
        "Antes" es el original agrandado simple. Corre en un hilo."""
        actual, mejorado, segundos_mejora = cuadro_mejorado(ruta, t, *tam, mejora, cache, cancelado)
        if mejorado is None or cancelado():
            return None
        inicio = time.perf_counter()
        despues = mv.procesar_cuadro_seguro(mejorado, pila, indice, 1.0, cancelado)
        demora = time.perf_counter() - inicio
        medida = None if segundos_mejora is None else (tam, mejora.ajustes, segundos_mejora)
        return _a_qimage(agrandar_simple(actual, *tam)), _a_qimage(despues), tam, True, demora, medida

    def cuadro_procesado_listo(self) -> bool:
        """True si se ve el cuadro actual procesado al tamaño de exportación (para las pruebas)."""
        return self.info is not None and self._generacion_completa == self._generacion

    def _ocupado(self) -> None:
        procesando = (self.info is not None and not self._reproduciendo
                      and self._generacion_completa != self._generacion)
        self.vista.establecer_procesando(procesando, "Mejorando la calidad…" if self.mejora.activa else None)
        self.barra_ocupado.setVisible(procesando)

    # ============================================================ reproducción
    @property
    def reproduciendo(self) -> bool:
        return self._reproduciendo

    def alternar_reproduccion(self) -> None:
        if self._reproduciendo:
            self.pausar()
        else:
            self.reproducir()

    def reproducir(self) -> None:
        if self.info is None or self.edicion is None or self._reproduciendo:
            return
        mapa = self.mapa
        if not mapa.tramos:
            self.etiqueta_estado.setText("No queda nada para reproducir: recuperá lo borrado (tocá una marquita) "
                                         "o deshacé con Ctrl+Z.")
            return
        inicio = self._visible(self.tiempo)
        if inicio >= self._ultimo_visible() - 1e-6:
            inicio = mapa.tramos[0][0]  # desde el final: vuelve a empezar
        self._reproduciendo = True
        self._sesion += 1
        self._en_vuelo = False
        self._generacion += 1  # descarta los cuadros quietos pendientes
        self._timer_rapido.stop()
        self._timer_completo.stop()
        self.tiempo = self._visible(self._ajustar(inicio))
        # El reloj de la reproducción va en el tiempo del resultado: pasa las uniones de corrido.
        self._t_base, self._t_reloj = self.tiempo_resultado, time.monotonic()
        self.boton_reproducir.setIcon(iconos.icono("pause", 18, color="#ffffff"))
        if self.mejora.activa:
            # Mejorar en vivo no llega a tiempo (necesita los cuadros vecinos): como el filtro completo,
            # se ve al pausar.
            self.etiqueta_estado.setText("Reproduciendo sin \"Mejorar calidad\": la mejora se ve al pausar.")
        self._ocupado()
        self._timer_reproducir.start()
        self._iniciar_sonido()
        self._tick()

    def pausar(self, render: bool = True) -> None:
        if not self._reproduciendo:
            return
        self._reproduciendo = False
        self._timer_reproducir.stop()
        self._timer_sonido.stop()
        self.reproductor.detener()
        self._con_sonido = False
        self.boton_reproducir.setIcon(iconos.icono("play", 18, color="#ffffff"))
        if render:
            self._solicitar_render()
        else:
            self._ocupado()

    def _iniciar_sonido(self) -> None:
        """Hace sonar la vista previa desde el cursor (si corresponde). Mientras suena, el reloj de
        la reproducción es el del sonido: la imagen sigue a lo que se escucha."""
        self._timer_sonido.stop()
        self.reproductor.detener()
        self._con_sonido = False
        if not self._reproduciendo or not self._hay_sonido() or self.audio.quitar or self.reproductor.silenciado:
            return
        externo, tramos = self.audio_externo, self.edicion.tramos_conservados()
        if externo is None:
            self._con_sonido = self.reproductor.reproducir(self.ruta, tramos, self.audio, self.tiempo,
                                                           self._pico_actual())
        elif not externo.desde_cero:
            # Alineado con el original (el modo Audio): los mismos tramos y ajustes, con el otro archivo.
            self._con_sonido = self.reproductor.reproducir(externo.ruta, tramos, self.audio, self.tiempo,
                                                           self._pico_actual())
        else:
            # Desde el 0 del resultado (voz en off): el mismo lector que usa la exportación. La función
            # arma el lector solo si de verdad va a sonar.
            duracion, audio, desde = self.info.duracion, self.audio, self.tiempo
            pico = self._pico_actual()
            pico = pico if pico is not None or not audio.normalizar else 1.0
            self._con_sonido = self.reproductor.reproducir_lector(
                lambda: mv.LectorDesdeCero(externo.ruta, tramos, duracion, audio, desde, pico=pico))
        self._t_base, self._t_reloj = self.tiempo_resultado, time.monotonic()

    def _reloj(self, ahora: float) -> float:
        """Segundo del resultado que corresponde mostrar: el que suena o, sin sonido, el del reloj."""
        if self._con_sonido:
            t = self.reproductor.posicion()  # instante del original que suena
            if t is not None:
                r = self.mapa.a_resultado(t)
                self._t_base, self._t_reloj = r, ahora  # si el sonido se corta, se sigue desde acá
                return r
            self._con_sonido = False  # terminó o se cortó: sigue el reloj
        return self._t_base + (ahora - self._t_reloj)

    def _tick(self) -> None:
        if not self._reproduciendo or self.edicion is None:
            return
        ahora = time.monotonic()
        mapa = self.mapa
        r = self._reloj(ahora)
        if not mapa.tramos or r >= mapa.duracion - 1e-6:  # llegó al final de lo que se ve
            self.tiempo = self._ultimo_visible()
            self.linea.establecer_tiempo(self.tiempo)
            self.pista_sonido.establecer_tiempo(self.tiempo)
            self._actualizar_tiempo()
            self.pausar()
            return
        # El cuadro que se ve en ese segundo del resultado (el último que empezó): nunca algo borrado.
        t = mapa.a_original(max(0.0, r))
        self.tiempo = self._visible(min(mv.indice_en(t, self.info.fps) / self.info.fps, self._ultimo()))
        self.linea.establecer_tiempo(self.tiempo)
        self.pista_sonido.establecer_tiempo(self.tiempo)
        self._actualizar_tiempo()
        if self._en_vuelo:
            return  # el cuadro anterior todavía se está preparando: este se saltea
        self._en_vuelo = True
        ruta, t_cuadro, indice, pila, tam = self._datos_render()
        vivo = self.boton_vivo.isChecked() and not self._vivo_lento and bool(pila)
        sesion = self._sesion

        def render(_cancelado):
            antes = mv.cuadro_en(ruta, t_cuadro, LADO_REPRODUCCION, guardar=False)
            despues, demora = None, None
            if vivo:
                inicio = time.perf_counter()
                chico, _ = reducir_para_vista(antes, LADO_VIVO)
                escala = min(1.0, max(chico.shape[:2]) / max(tam))
                despues = _a_qimage(mv.procesar_cuadro_seguro(chico, pila, indice, escala))
                demora = time.perf_counter() - inicio
            return sesion, _a_qimage(antes), despues, tam, demora

        # Sin generación: siempre avisa al terminar, así nunca queda "en vuelo" para siempre.
        self._pool_cuadros.start(Tarea("reproduccion", 0, render, self._senales))

    # ============================================================ edición
    def _estado(self) -> EstadoEditor:
        """Lo de ahora, como un paso del historial."""
        return EstadoEditor(self.edicion, self.audio, self.mejora, self.audio_externo)

    def _editar(self, nueva: Optional[mv.EdicionVideo] = None, descripcion: str = "",
                audio: Optional[ma.AjustesAudio] = None, control: str = "",
                mejora: Optional[mm.AjustesMejora] = None, externo=_IGUAL) -> bool:
        """Un paso nuevo de deshacer con la edición, los ajustes del sonido, los de "Mejorar calidad"
        y el sonido externo (lo que no viene, queda; ``externo=None`` vuelve al sonido del video).

        ``control``: el control (de sonido o de la mejora) que cambió. Si es el mismo que el del paso
        anterior y pasó poco tiempo (``JUNTAR_SONIDO``), se junta con ese paso: mover un deslizador no
        llena el historial. Los fundidos se acortan solos si los cortes achican el resultado."""
        if self.edicion is None:
            return False
        edicion = nueva if nueva is not None else self.edicion
        audio = self._limitar_fundidos(audio if audio is not None else self.audio, edicion)
        mejora = mejora if mejora is not None else self.mejora
        externo = self.audio_externo if externo is _IGUAL else externo
        nuevo = EstadoEditor(edicion, audio, mejora, externo)
        if nuevo == self._estado():
            return False
        ahora = time.monotonic()
        anterior, momento = self._ultimo_cambio_sonido
        # Se junta solo con el paso que abrió este mismo gesto: si el historial cambió desde entonces
        # (otro paso, deshacer, rehacer), es un paso nuevo.
        juntar = (bool(control) and nueva is None and control == anterior and ahora - momento < JUNTAR_SONIDO
                  and bool(self._deshacer) and len(self._deshacer) == self._largo_gesto)
        terminado = False
        if not juntar:
            self._deshacer.append(self._estado())
            del self._deshacer[:-200]
        elif self._deshacer[-1] == nuevo:
            # Volvió a como estaba antes de empezar a moverlo: no queda un paso vacío, y el gesto
            # termina (lo próximo no se puede juntar con el paso de antes, que es de otra cosa).
            self._deshacer.pop()
            terminado = True
        self._rehacer.clear()
        if control and not terminado:
            self._ultimo_cambio_sonido = (control, ahora)
            self._largo_gesto = len(self._deshacer)
        else:
            self._ultimo_cambio_sonido = ("", 0.0)
            self._largo_gesto = -1
        self._fijar_estado(*nuevo)
        if descripcion:
            self.etiqueta_estado.setText(descripcion)
        return True

    @staticmethod
    def _limitar_fundidos(audio: ma.AjustesAudio, edicion: mv.EdicionVideo) -> ma.AjustesAudio:
        """Los fundidos de entrada y de salida, como mucho la mitad de la duración final (si no,
        se multiplican entre sí y el sonido nunca llega a su volumen)."""
        mitad = max(0.0, edicion.duracion_resultante() / 2)
        if audio.fundido_entrada <= mitad and audio.fundido_salida <= mitad:
            return audio
        return audio.con(fundido_entrada=min(audio.fundido_entrada, mitad),
                         fundido_salida=min(audio.fundido_salida, mitad))

    def _fijar_estado(self, edicion: mv.EdicionVideo, audio: Optional[ma.AjustesAudio] = None,
                      mejora: Optional[mm.AjustesMejora] = None, externo=_IGUAL) -> None:
        """Pone una edición, unos ajustes de sonido, los de la mejora y el sonido externo (un paso
        nuevo, deshacer o rehacer) en todo: línea de tiempo, pista, tarjetas Sonido y Mejorar
        calidad, la vista previa y, si está sonando, lo que se escucha."""
        audio = self.audio if audio is None else audio
        mejora = self.mejora if mejora is None else mejora
        externo = self.audio_externo if externo is _IGUAL else externo
        antes_tramos = self.edicion.tramos_conservados() if self.edicion is not None else None
        antes_audio = self.audio
        cambio_mejora = mejora != self.mejora
        cambio_externo = externo != self.audio_externo
        if cambio_mejora:
            self._poner_mejora(mejora)
        self.edicion, self.audio, self.audio_externo = edicion, audio, externo
        self.linea.establecer_edicion(edicion)
        cambio_tramos = edicion.tramos_conservados() != antes_tramos
        if cambio_externo:
            self._cargar_onda()  # la forma de onda de lo que suena ahora
        elif cambio_tramos and externo is not None and externo.desde_cero:
            self._poner_forma()  # la voz en off no se corta: cambia dónde cae cada instante del original
        movido = False
        if cambio_tramos and self.info is not None:
            # Lo que estaba bajo el cursor puede haber desaparecido: el cursor pasa a la unión.
            visible = self._visible(self.tiempo)
            movido = visible != self.tiempo
            self.tiempo = visible
            self.linea.establecer_tiempo(self.tiempo)
            self.pista_sonido.establecer_tiempo(self.tiempo)
        self._actualizar_sonido()
        self._actualizar_resultado()
        self._actualizar_tiempo()
        self._actualizar_habilitados()
        if self._reproduciendo:
            if cambio_tramos:
                # El reloj va en el tiempo del resultado, que cambió: sigue desde el cursor.
                self._t_base, self._t_reloj = self.tiempo_resultado, time.monotonic()
            if cambio_tramos or cambio_externo or audio.quitar != antes_audio.quitar:
                self._iniciar_sonido()  # lo que suena se arma de nuevo desde el cursor
            elif audio != antes_audio and self._con_sonido:
                self.reproductor.cambiar_ajustes(audio, self._pico_actual())
        elif movido or cambio_mejora or (self.mejora.activa and cambio_tramos):
            # Con la mejora, los vecinos dependen del tramo: un corte puede cambiar el cuadro mejorado.
            self._solicitar_render()

    def _rango_visto(self, inicio: float, fin: float) -> str:
        """'de 0:01,00 a 0:02,00': la parte de [inicio, fin) del original que se ve, en los tiempos
        de la línea de tiempo (los del resultado)."""
        rangos = self.mapa.rangos_resultado(inicio, fin)
        a, b = (rangos[0][0], rangos[-1][1]) if rangos else (self.mapa.a_resultado(inicio),) * 2
        return f"de {formato_tiempo(a)} a {formato_tiempo(b)}"

    def marcar_entrada(self) -> None:
        if self.edicion is None:
            return
        quita = self.tiempo_resultado
        if self._editar(self.edicion.con_entrada(self.tiempo),
                        f"Principio recortado ({formato_duracion(quita)}): lo de antes del cursor ya no está. "
                        "Para recuperarlo, tocá la marquita del principio (o Ctrl+Z)."):
            self.linea.seleccionar(-1)

    def marcar_salida(self) -> None:
        if self.edicion is None:
            return
        quita = max(0.0, self.mapa.duracion - self.tiempo_resultado - self.edicion.cuadro)
        if self._editar(self.edicion.con_salida(self.tiempo),
                        f"Final recortado ({formato_duracion(quita)}): lo de después del cursor ya no está. "
                        "Para recuperarlo, tocá la marquita del final (o Ctrl+Z)."):
            self.linea.seleccionar(-1)

    def _limites_pedidos(self, entrada: float, salida: Optional[float]) -> None:
        if self.edicion is None:
            return
        antes = self.mapa.duracion
        nueva = self.edicion.con_limites(entrada, salida)
        if nueva.entrada != self.edicion.entrada and nueva.salida == self.edicion.salida:
            texto = "Principio recortado"
        elif nueva.salida != self.edicion.salida and nueva.entrada == self.edicion.entrada:
            texto = "Final recortado"
        else:
            texto = "Principio y final recortados"
        quita = max(0.0, antes - nueva.duracion_resultante())
        self._editar(nueva, f"{texto} ({formato_duracion(quita)}). Para recuperarlo, tocá su marquita (o Ctrl+Z).")

    def cortar(self) -> None:
        if self.edicion is None:
            return
        if not self._editar(self.edicion.cortar(self.tiempo), f"Corte en {formato_tiempo(self.tiempo_resultado)}."):
            self.etiqueta_estado.setText("Ahí ya hay un corte (o es el principio o el final).")
            return
        self.linea.seleccionar(self.edicion.indice_en(self.tiempo))

    def borrar_tramo(self) -> None:
        """Borra el tramo elegido (o el del cursor): desaparece de la línea de tiempo, lo que sigue se
        corre y en la unión queda una marquita para recuperarlo (o Ctrl+Z)."""
        if self.edicion is None:
            return
        i = self._tramo_objetivo()
        s = self.edicion.segmentos[i]
        if s.borrado:
            return  # no se ve: no hay nada que borrar
        nueva = self.edicion.con_borrado(i)
        if not nueva.tramos_conservados():
            self.etiqueta_estado.setText("Es lo único que queda: no se puede borrar todo el video.")
            return
        largo = self.mapa.rangos_resultado(s.inicio, s.fin)
        largo = sum(b - a for a, b in largo)
        if self._editar(nueva, f"Tramo borrado ({formato_duracion(largo)}): ya no está en el video. Para "
                               "recuperarlo, tocá la marquita rosa de la unión (o Ctrl+Z)."):
            self.linea.seleccionar(-1)
            if not self._reproduciendo:
                self._ocupado()

    def recuperar(self, hueco: Optional[mv.Hueco] = None) -> bool:
        """"Recuperar lo borrado" en una unión: vuelve a poner lo que falta ahí (lo borrado o lo
        recortado), con su paso de deshacer. Sin ``hueco`` (R), la marquita más cercana al cursor.
        El cursor va al comienzo de lo recuperado. Devuelve si cambió algo."""
        if self.edicion is None:
            return False
        huecos = self.mapa.huecos()
        if hueco is None:
            if not huecos:
                self.etiqueta_estado.setText("No hay nada borrado para recuperar.")
                return False
            r = self.tiempo_resultado
            hueco = min(huecos, key=lambda h: abs(h.en - r))
        if not self._editar(mv.recuperar_hueco(self.edicion, hueco),
                            f"Se recuperó lo borrado ({formato_duracion(hueco.duracion)}). Ctrl+Z lo vuelve a "
                            "sacar."):
            return False
        self.linea.seleccionar(-1)
        self.ir_a(hueco.inicio)
        return True

    def silenciar_tramo(self) -> None:
        """Silencia el tramo elegido (o el del cursor, si no hay uno elegido); si ya está en
        silencio, le devuelve el sonido. Es el mismo tramo sobre el que actúa Borrar."""
        if self.edicion is None or not self._hay_sonido():
            return
        if self.audio.quitar:
            self.etiqueta_estado.setText("El sonido está quitado: no hay nada que silenciar.")
            return
        i = self._tramo_objetivo()
        s = self.edicion.segmentos[i]
        if s.borrado:
            self.etiqueta_estado.setText("Ese tramo está borrado: no se exporta, así que no hace falta silenciarlo.")
            return
        rango = self._rango_visto(s.inicio, s.fin)  # en los tiempos que se ven (el silencio va en el original)
        if self.audio.silenciado(s.inicio, s.fin):
            nuevo, texto = self.audio.con_sonido(s.inicio, s.fin), f"Sonido devuelto {rango}."
        else:
            nuevo, texto = self.audio.con_silencio(s.inicio, s.fin), f"Silenciado {rango}: la imagen queda, sin sonido."
        if self._editar(audio=nuevo, descripcion=texto):
            self.linea.seleccionar(i)

    def _al_cambiar_sonido(self, nuevo: ma.AjustesAudio, control: str) -> None:
        """Un cambio en la tarjeta Sonido: es un paso de deshacer (los movimientos seguidos del
        mismo deslizador, uno solo)."""
        if self.edicion is None:
            self._actualizar_sonido()
            return
        textos = {"quitar": "Sonido quitado: el video se exporta sin audio." if nuevo.quitar else
                  "Sonido de vuelta.",
                  "normalizar": "Normalizar: lo más fuerte queda en -1 dB." if nuevo.normalizar else
                  "Sin normalizar.",
                  "silencios": "Se devolvió todo el sonido."}
        self._editar(audio=nuevo, descripcion=textos.get(control, ""), control=control)

    def deshacer(self) -> None:
        if self._deshacer:
            self._rehacer.append(self._estado())
            self._ultimo_cambio_sonido = ("", 0.0)
            self._restaurar(self._deshacer.pop())
            self.etiqueta_estado.setText("Deshecho.")

    def rehacer(self) -> None:
        if self._rehacer:
            self._deshacer.append(self._estado())
            self._ultimo_cambio_sonido = ("", 0.0)
            self._restaurar(self._rehacer.pop())
            self.etiqueta_estado.setText("Rehecho.")

    def _restaurar(self, estado: tuple) -> None:
        """Pone un estado del historial. El tramo elegido sigue elegido solo si en ese estado está el
        mismo tramo (mismo inicio y fin): el índice solo no alcanza, porque al deshacer un corte los
        índices se corren y Supr o M actuarían sobre un tramo que no se eligió."""
        elegido = None
        i = self.linea.seleccion
        if self.edicion is not None and 0 <= i < len(self.edicion.segmentos):
            s = self.edicion.segmentos[i]
            elegido = (s.inicio, s.fin)
        self._fijar_estado(*estado)
        nuevo = -1
        if elegido is not None and self.edicion is not None:
            nuevo = next((k for k, s in enumerate(self.edicion.segmentos)
                          if abs(s.inicio - elegido[0]) < 1e-9 and abs(s.fin - elegido[1]) < 1e-9), -1)
        self.linea.seleccionar(nuevo)
        self._seleccion_en_pista()

    # ============================================================ mejorar calidad
    def _al_cambiar_mejora(self, nueva: mm.AjustesMejora, control: str) -> None:
        """Un cambio en la tarjeta "Mejorar calidad": es un paso de deshacer (los movimientos
        seguidos del mismo deslizador, uno solo). Sin video, solo queda puesto para el próximo."""
        antes = self.mejora
        if self.edicion is None:
            self._poner_mejora(nueva)
            return
        texto = ""
        if control == "activa":
            if nueva.activa:
                w, h = self._tam_salida_con(nueva)
                texto = (f"\"Mejorar calidad\" prendida (sin IA): se ve al pausar y se exporta a {w} × {h}. "
                         "Exportar tarda más.")
            else:
                texto = "\"Mejorar calidad\" apagada: el video sale como siempre."
        self._editar(mejora=nueva, descripcion=texto, control=f"mejora_{control}")
        if nueva.activa and not antes.activa and self.mejora.activa:
            self._sugerir_720p()

    def _tam_salida_con(self, mejora: mm.AjustesMejora) -> tuple[int, int]:
        """Tamaño de salida con esa mejora (con la mejora prendida, 720p y 1080p agrandan)."""
        resolucion = self._resolucion()
        if mejora.activa and resolucion == "Original" and self.info is not None and \
                min(self.info.ancho, self.info.alto) < 720:
            resolucion = "720p"  # lo que va a sugerir _sugerir_720p
        return mv.tamano_salida(self.info.ancho, self.info.alto, resolucion, agrandar=mejora.activa)

    def _sugerir_720p(self) -> None:
        """Al prender la mejora con un video chico y la resolución en "Original": 720p (lo acordado:
        un video chico queda como un buen 720p). Se puede volver a elegir otra."""
        if self.info is None or min(self.info.ancho, self.info.alto) >= 720 or self._resolucion() != "Original":
            return
        self.botones_resolucion["720p"].setChecked(True)
        self._al_cambiar_resolucion()

    def _poner_mejora(self, mejora: mm.AjustesMejora) -> None:
        """Pone estos ajustes de la mejora: tarjeta, resoluciones de la exportación y su resumen."""
        self.mejora = mejora
        self._actualizar_resoluciones()
        self._actualizar_mejora()
        self._actualizar_estimacion()
        self._ocupado()

    def _actualizar_mejora(self) -> None:
        """La tarjeta "Mejorar calidad" y los textos que dependen de ella."""
        nota = ""
        if self.mejora.activa:
            if self.info is not None:
                w, h = self._tam_salida()
                nota = f"Se exporta a {w} × {h} y tarda más. Se ve al pausar (al reproducir, sin la mejora)."
            else:
                nota = "Abrí un video: se ve al pausar y al exportar 720p y 1080p lo agrandan."
        self.panel_mejora.establecer(self.mejora, nota)
        con_mejora = self.mejora.activa
        for b in self.grupo_modo.buttons():
            modo = b.property("modo")
            if modo == VistaComparacion.MODO_ANTES:
                b.setToolTip("Antes: el original agrandado simple, sin la mejora" if con_mejora else
                             "Antes: cuadro original")
            elif modo == VistaComparacion.MODO_DESPUES:
                b.setToolTip("Después: con \"Mejorar calidad\" y el filtro" if con_mejora else
                             "Después: cuadro con el filtro")
        self.boton_vivo.setToolTip(
            "Filtro al reproducir: al reproducir, mostrar el filtro a baja resolución. Si la PC no llega a "
            "tiempo, se muestra el original. Al pausar siempre se ve el cuadro procesado."
            + (" \"Mejorar calidad\" se ve al pausar." if con_mejora else ""))

    def _actualizar_resultado(self) -> None:
        self._textos_linea()
        self._actualizar_estimacion()
        hay_borrados = self.edicion is not None and bool(self.mapa.huecos())
        self.ayuda_linea.setText(AYUDA_LINEA_CON_BORRADOS if hay_borrados else AYUDA_LINEA)

    def _actualizar_estimacion(self) -> None:
        if self.info is None or self.edicion is None:
            self.etiqueta_estimacion.setText("MP4 · H.264 + AAC")
            return
        final = self.edicion.duracion_resultante()
        cuadros = int(round(final * self.info.fps))
        con_sonido = self._hay_sonido() and not self.audio.quitar
        partes = ["MP4 · H.264" + (" + AAC" if con_sonido else " · sin sonido")]
        if self._texto_sonido_exportar():
            partes.append(self._texto_sonido_exportar())
        partes.append(f"{formato_tiempo(final, decimas=False)} · {cuadros} cuadros")
        segundos = self.estimacion_exportacion()
        tarda = None if segundos is None else _duracion_humana(segundos)
        if self.mejora.activa:
            w, h = self._tam_salida()
            # Espacios duros: la medida no se parte en dos renglones ("1280 ×" / "720").
            partes.append(f"mejorado a {w} × {h}: tarda más" + (f", {tarda}" if tarda else ""))
        elif tarda:
            partes.append(f"tarda {tarda}")
        self.etiqueta_estimacion.setText(" · ".join(partes))

    def estimacion_exportacion(self) -> Optional[float]:
        """Segundos que va a tardar la exportación, con lo que tardó el último cuadro procesado al
        tamaño de exportación (el filtro y, si está prendida, la mejora). None si todavía no se midió."""
        if self.info is None or self.edicion is None or not self._segundos_cuadro:
            return None
        tam = self._tam_salida()
        if self._tam_medido is not None and self._tam_medido != tam:
            return None  # se midió a otro tamaño
        cuadros = int(round(self.edicion.duracion_resultante() * self.info.fps))
        por_cuadro = self._segundos_cuadro / ACELERACION_HILOS
        if self.mejora.activa:
            mejora = self._medidas_mejora.get((tam, self.mejora))
            if mejora is None:
                return None
            por_cuadro += mejora / ACELERACION_MEJORA
        return cuadros * por_cuadro

    def _actualizar_habilitados(self) -> None:
        hay = self.info is not None
        for w in (self.boton_alejar, self.boton_acercar, self.boton_ajustar, self.boton_100, self.boton_200,
                  self.boton_inicio, self.boton_cuadro_atras, self.boton_reproducir, self.boton_cuadro_adelante,
                  self.boton_fin, self.boton_entrada, self.boton_salida, self.boton_cortar, self.boton_borrar):
            w.setEnabled(hay)
        self.boton_deshacer.setEnabled(bool(self._deshacer))
        self.boton_rehacer.setEnabled(bool(self._rehacer))
        quedan = hay and bool(self.edicion.tramos_conservados())
        self.boton_exportar.setEnabled(quedan and not self.exportando)
        self.boton_exportar.setText("  Exportando…" if self.exportando
                                    else "  Exportar video entero…" if getattr(self, "simple", False)
                                    else "  Exportar video…")
        self.boton_cerrar_video.setVisible(hay)
        self.boton_cerrar_video.setEnabled(hay and not self.exportando)
        self._actualizar_boton_sonido()
        self._textos_linea()

    # ============================================================ sonido
    def _hay_sonido(self) -> bool:
        """Si suena algo: el sonido del video o uno externo."""
        return self.info is not None and (bool(self.info.tiene_audio) or self.audio_externo is not None)

    def _video_tiene_sonido(self) -> bool:
        return self.info is not None and bool(self.info.tiene_audio)

    def texto_sonido(self) -> str:
        """El renglón de la tarjeta Sonido: qué suena."""
        e = self.audio_externo
        if self.info is None:
            return "Sonido: —"
        if e is None:
            return "Sonido: el del video" if self._video_tiene_sonido() else "Sonido: ninguno"
        if e.desde_cero:
            return f"Sonido: {e.nombre} (desde el principio)"
        return "Sonido: editado en el modo Audio"

    def _texto_sonido_exportar(self) -> str:
        """Para el resumen de exportar: "con el sonido de voz.m4a" o "con el sonido editado"."""
        e = self.audio_externo
        if e is None or self.audio.quitar:
            return ""
        return f"con el sonido de {e.nombre}" if e.desde_cero else "con el sonido editado"

    def _actualizar_sonido(self) -> None:
        """La tarjeta Sonido y la pista con los ajustes y la edición de ahora."""
        hay = self.info is not None and self.edicion is not None
        final = self.edicion.duracion_resultante() if hay else 0.0
        self.panel_sonido.establecer(self.audio, final, self._hay_sonido(), hay)
        e = self.audio_externo
        if e is None:
            origen = ""
        elif e.desde_cero:
            origen = (f"{e.ruta}\nSuena desde el principio de lo que se exporta (como una voz en off) y se corta "
                      "al final; si es más corto, lo que falta queda en silencio.")
        else:
            origen = (f"{e.ruta}\nEl sonido del video editado en el modo Audio: los cortes del video se le "
                      "aplican igual.")
        self.panel_sonido.establecer_origen(
            self.texto_sonido(), e is not None, self._video_tiene_sonido(),
            "Este video no tiene sonido para editar. Podés ponerle uno con \"Cambiar el sonido por…\".", origen)
        if hay:
            if self.audio.normalizar:
                self._pico_actual()  # si todavía no se midió, se mide en segundo plano
            pico = self._picos.get(self._clave_pico()) if self.audio.normalizar else None
            ganancia = None if pico is None or self.audio.quitar else self.audio.ganancia(pico)
            self.pista_sonido.establecer_edicion(self.edicion.tramos_conservados(), self.audio, ganancia)
            self._seleccion_en_pista()

    def _seleccion_en_pista(self) -> None:
        i = self.linea.seleccion
        if self.edicion is None or not 0 <= i < len(self.edicion.segmentos):
            self.pista_sonido.establecer_seleccion(None)
        else:
            s = self.edicion.segmentos[i]
            self.pista_sonido.establecer_seleccion((s.inicio, s.fin))

    def _al_cambiar_seleccion(self) -> None:
        self._seleccion_en_pista()
        self._actualizar_habilitados()

    def _pista_presionada(self, t: float) -> None:
        """Tocar la pista de sonido elige el tramo de ese instante (como en la línea de tiempo)."""
        if self.edicion is not None and self.info is not None:
            self.linea.seleccionar(self.edicion.indice_en(self._visible(t)))

    def _cargar_onda(self) -> None:
        """La forma de onda de lo que suena (el video o el sonido externo), en segundo plano."""
        if self.info is None:
            return
        ruta = self.audio_externo.ruta if self.audio_externo is not None else self.ruta
        if self._hay_sonido():
            self.pista_sonido.cargando(self.info.duracion)
            self.cargador_onda.cargar(ruta)
        else:
            self.cargador_onda.cancelar()
            self.pista_sonido.sin_sonido(self.info.duracion)

    def _forma_en_original(self, forma):
        """La forma de onda que da el cargador, en el tiempo original del video (la que dibuja la
        pista). La del video va tal cual; la de un sonido externo se ubica según cómo suena
        (``forma_alineada``)."""
        e = self.audio_externo
        if forma is None or e is None or self.info is None:
            return forma
        mapa = self.mapa if e.desde_cero else mv.MapaTiempo.identidad(self.info.duracion)
        return forma_alineada(forma, mapa)

    def _poner_forma(self) -> None:
        """Vuelve a ubicar la forma del externo (la voz en off cae en otro lugar después de un corte)."""
        forma = self.cargador_onda.forma
        if self.info is not None and forma is not None:
            self.pista_sonido.establecer_forma(self._forma_en_original(forma))

    def _onda_parcial(self, forma) -> None:
        if self.info is not None:
            self.pista_sonido.establecer_forma(self._forma_en_original(forma))

    def _onda_lista(self, forma) -> None:
        if self.info is None:
            return
        if forma is None:
            self.pista_sonido.sin_sonido(self.info.duracion)
        else:
            self.pista_sonido.establecer_forma(self._forma_en_original(forma))

    def _onda_fallida(self, _mensaje: str) -> None:
        if self.info is not None:
            self.pista_sonido.sin_sonido(self.info.duracion, "No se pudo leer la forma de onda")

    def _clave_pico(self) -> tuple:
        """(ruta, tramos, silencios) de lo que suena: lo que mide ``medir_pico`` para normalizar."""
        return mv.sonido_a_medir(self.ruta, self.edicion.tramos_conservados(), self.info.duracion,
                                 self.audio.silencios, self.audio_externo)

    def _pico_actual(self) -> Optional[float]:
        """Pico de lo que se exporta, para escuchar con "Normalizar". Si todavía no se midió, se
        mide en segundo plano y mientras tanto se usa la estimación de la forma de onda.

        Solo vale la medición de lo último que se pidió: si mientras tanto cambian los tramos o los
        silencios, las mediciones viejas que esperan su turno no empiezan y la que está midiendo se
        corta (así cinco cortes seguidos no encolan cinco pasadas por el archivo entero)."""
        if not self.audio.normalizar or not self._hay_sonido() or self.edicion is None:
            return None
        clave = self._clave_pico()
        self._clave_pico_pedida = clave
        if clave in self._picos:
            return self._picos[clave]
        if clave not in self._midiendo_pico:
            self._midiendo_pico.add(clave)
            ruta, tramos, silencios = clave[0], list(clave[1]), clave[2]
            vieja = lambda: self._clave_pico_pedida != clave  # noqa: E731 - se lee desde el hilo que mide

            def medir(_cancelado):
                if vieja():
                    return clave, None  # ya no hace falta: ni empieza
                try:
                    return clave, ma.medir_pico(ruta, tramos, silencios, vieja)
                except Cancelado:
                    return clave, None  # dejó de hacer falta a mitad de camino

            self._pool_pico.start(Tarea("pico", self._generacion_info, medir, self._senales,
                                        lambda: self._generacion_info))
        return pico_aproximado(self.cargador_onda.forma, clave[1], clave[2])

    def _pico_medido(self, clave: tuple, pico: Optional[float]) -> None:
        self._midiendo_pico.discard(clave)
        if pico is None:
            return  # se descartó: cambió lo que se exporta antes de terminar de medirlo
        self._picos[clave] = pico
        if self.edicion is None or clave != self._clave_pico() or not self.audio.normalizar:
            return
        self._actualizar_sonido()
        if self._con_sonido:
            self.reproductor.cambiar_ajustes(self.audio, pico)

    @staticmethod
    def _sonido_vista_guardado() -> bool:
        """Si la vista previa suena (se recuerda entre una vez y otra; la primera vez, sí)."""
        valor = configuracion().value(CLAVE_SONIDO_VISTA, True)
        return valor not in (False, "false", "0", 0)

    def _al_alternar_sonido_vista(self, activo: bool) -> None:
        config = configuracion()
        config.setValue(CLAVE_SONIDO_VISTA, bool(activo))
        config.sync()
        self.reproductor.establecer_silenciado(not activo)
        self._actualizar_boton_sonido()
        if self._reproduciendo:
            if activo:
                self._iniciar_sonido()
            else:
                self._con_sonido = False  # sigue con el reloj, desde donde iba

    def _actualizar_boton_sonido(self) -> None:
        activo = self.boton_sonido.isChecked()
        self.boton_sonido.setIcon(iconos.icono("volume-2" if activo else "volume-x", 15))
        disponible = self.reproductor.disponible
        self.boton_sonido.setEnabled(disponible and self._hay_sonido())
        if not disponible:
            ayuda = f"Sin sonido en la vista previa: {self.reproductor.motivo or 'no hay salida de sonido.'}"
        elif self.info is not None and not self._hay_sonido():
            ayuda = "Este video no tiene sonido."
        else:
            ayuda = ("Sonido al reproducir: escuchá el video en la vista previa, con los cortes y la tarjeta "
                     "Sonido. Apagalo para mirar en silencio (no cambia lo que se exporta).")
            if not activo:
                ayuda = "La vista previa está silenciada. " + ayuda
        self.boton_sonido.setToolTip(ayuda)

    def _sonido_fallo(self, mensaje: str) -> None:
        self._con_sonido = False
        self.etiqueta_estado.setText(f"{mensaje} La vista previa sigue sin sonido.")
        self._actualizar_boton_sonido()

    # ============================================================ tareas
    def _tarea_terminada(self, tipo: str, generacion: int, resultado) -> None:
        if tipo == "info":
            if generacion == self._generacion_info:
                self.barra_ocupado.hide()
                self._info_lista(*resultado)
            return
        if tipo == "miniaturas":
            if generacion == self._generacion_info:
                self.linea.establecer_miniaturas(resultado)
            return
        if tipo == "avance":
            self._avance_exportacion(*resultado)
            return
        if tipo == "exportacion":
            self._exportacion_terminada(resultado)
            return
        if tipo == "pico":
            if generacion == self._generacion_info:
                self._pico_medido(*resultado)
            return
        if tipo == "avance_audio":
            self.panel_sonido.mostrar_progreso(*resultado)
            return
        if tipo == "audio_guardado":
            self._audio_guardado(resultado)
            return
        if tipo == "sonido_para_audio":
            self._sonido_para_audio_listo(resultado)
            return
        if tipo == "reproduccion":
            self._en_vuelo = False
            sesion, antes, despues, tam, demora = resultado
            if not self._reproduciendo or sesion != self._sesion:
                return
            if demora is not None and demora > LIMITE_VIVO:
                self._vivo_lento = True
                self.etiqueta_estado.setText("El filtro en vivo no llega a tiempo en esta PC: al reproducir se ve "
                                             "el original. Pausá para ver el cuadro procesado.")
            self.vista.establecer_imagenes(antes, despues, tam)
            return
        if tipo == "cuadro":
            if resultado is None or generacion != self._generacion or self._reproduciendo:
                return
            antes, despues, tam, completa, demora, medida_mejora = resultado
            self.vista.establecer_imagenes(antes, despues, tam)
            if completa:
                self._generacion_completa = generacion
                if demora is not None and not self.exportando:  # exportando, la medida sale inflada
                    self._segundos_cuadro, self._tam_medido = demora, tam
                    if medida_mejora is not None:  # (tamaño, ajustes, segundos) de "Mejorar calidad"
                        self._medidas_mejora[medida_mejora[:2]] = medida_mejora[2]
                    self._actualizar_estimacion()
            self._ocupado()

    def _tarea_fallida(self, tipo: str, generacion: int, mensaje: str) -> None:
        if tipo == "info":
            if generacion == self._generacion_info:
                self.barra_ocupado.hide()
                self.etiqueta_estado.setText("No se pudo abrir el video.")
                QMessageBox.warning(self, "No se pudo abrir", f"No se pudo leer el video.\n\n{mensaje}")
        elif tipo == "miniaturas":
            pass  # sin miniaturas la línea de tiempo funciona igual
        elif tipo == "pico":
            self._midiendo_pico.clear()  # se vuelve a intentar la próxima vez (mientras, la estimación)
        elif tipo == "audio_guardado":
            self.panel_sonido.terminar_progreso()
            self.etiqueta_estado.setText("No se pudo guardar el audio.")
            QMessageBox.critical(self, "Error al guardar el audio", f"No se pudo guardar el audio.\n\n{mensaje}")
        elif tipo == "sonido_para_audio":
            self.panel_sonido.terminar_progreso()
            self.etiqueta_estado.setText("No se pudo preparar el sonido para el modo Audio.")
            QMessageBox.critical(self, "Error al preparar el sonido",
                                 f"No se pudo preparar el sonido para el modo Audio.\n\n{mensaje}")
        elif tipo == "exportacion":
            self._fin_exportacion()
            self.etiqueta_estado.setText("La exportación falló.")
            QMessageBox.critical(self, "Error al exportar", f"No se pudo exportar el video.\n\n{mensaje}")
        else:
            if tipo == "reproduccion":
                self._en_vuelo = False
            self.etiqueta_estado.setText(f"Error al procesar el cuadro: {mensaje}")
            self._generacion_completa = self._generacion
            self._ocupado()

    # ============================================================ exportar
    def exportar(self) -> None:
        if self.info is None or self.exportando:
            return
        tramos = self.edicion.tramos_conservados()
        if not tramos:
            QMessageBox.information(self, "Nada para exportar", "No queda nada: está todo borrado. Recuperá "
                                    "lo borrado (tocá una marquita rosa) o deshacé con Ctrl+Z.")
            return
        if self.audio_externo is not None and not self.audio.quitar:
            # Antes de preguntar dónde guardar: el sonido elegido tiene que seguir estando.
            try:
                mv.validar_audio_externo(self.audio_externo)
            except ValueError as error:
                QMessageBox.warning(self, "No se encuentra el sonido",
                                    f"{error}\n\nVolvé al sonido original o elegí otro con \"Cambiar el sonido "
                                    "por…\".")
                return
        self.pausar()
        sugerida = mv.ruta_salida_video(self.ruta)
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar video", str(sugerida), "Video MP4 (*.mp4)")
        if not ruta:
            return
        destino = Path(ruta)
        if destino.suffix.lower() != ".mp4":
            destino = destino.with_suffix(".mp4")
        if mv._misma_ruta(destino, Path(self.ruta)):
            QMessageBox.warning(self, "Elegí otro nombre",
                                "Ese es el video original. Para no sobrescribirlo, elegí otro nombre.")
            return
        origen = self.ruta
        pila = self.panel_ajustes.pila()
        resolucion = self._resolucion()
        calidad = self.combo_calidad.currentData() or "Alta"
        usar_gpu = self.check_gpu.isChecked()
        audio = self.audio  # quitar, volumen, normalizar, fundidos y silencios
        mejora = self.mejora if self.mejora.activa else None  # "Mejorar calidad" (sin IA)
        externo = self.audio_externo  # el sonido de otro archivo (None = el del video)
        sonido = self._texto_sonido_exportar()
        senales = self._senales
        self._cancelar_exportacion = False
        cancelado = lambda: self._cancelar_exportacion  # noqa: E731 - se lee desde el hilo de la exportación

        def trabajo(_c):
            def avance(hechos, total, restante):
                senales.terminada.emit("avance", 0, (hechos, total, restante))
            try:
                extra = {} if externo is None else {"audio_externo": externo}
                if usar_gpu:
                    extra["gpu"] = True
                if mejora is None:  # la misma llamada de siempre
                    r = mv.exportar_video(origen, destino, pila, tramos, resolucion, calidad, avance, cancelado,
                                          audio=audio, **extra)
                else:
                    r = mv.exportar_video(origen, destino, pila, tramos, resolucion, calidad, avance, cancelado,
                                          audio=audio, mejora=mejora, **extra)
                return r, sonido
            except Cancelado:
                return "cancelado"

        self.exportando = True
        self._inicio_exportacion = time.monotonic()
        self.barra_exportacion.setValue(0)
        self.etiqueta_progreso.setText("Preparando…")
        self.caja_progreso.show()
        self.boton_cancelar.setEnabled(True)
        self._actualizar_habilitados()
        self.etiqueta_estado.setText(f"Exportando {destino.name}…")
        self._pool_exportar.start(Tarea("exportacion", 0, trabajo, self._senales))
        self.exportacionCambiada.emit(True)

    def _avance_exportacion(self, hechos: int, total: int, restante: Optional[float]) -> None:
        if not self.exportando:
            return
        self.barra_exportacion.setValue(round(1000 * hechos / max(1, total)))
        texto = f"Cuadro {hechos} de {total}"
        if restante is not None:
            texto += f" · faltan {formato_tiempo(restante, decimas=False)}"
            transcurrido = time.monotonic() - self._inicio_exportacion
            if transcurrido > 0:
                texto += f" · {hechos / transcurrido:.1f} cuadros/s".replace(".", ",")
        self.etiqueta_progreso.setText(texto)
        self.progresoExportacion.emit(hechos, total)

    def cancelar_exportacion(self) -> None:
        if self.exportando:
            self._cancelar_exportacion = True
            self.boton_cancelar.setEnabled(False)
            self.etiqueta_progreso.setText("Cancelando…")

    def _fin_exportacion(self) -> None:
        self.exportando = False
        self.caja_progreso.hide()
        self._actualizar_habilitados()
        self.exportacionCambiada.emit(False)

    def _exportacion_terminada(self, resultado) -> None:
        self._fin_exportacion()
        if resultado == "cancelado":
            self.etiqueta_estado.setText("Exportación cancelada. No quedó ningún archivo a medias.")
            return
        r, sonido = resultado if isinstance(resultado, tuple) else (resultado, "")
        r: mv.ResultadoVideo
        self.ultima_exportacion = r
        velocidad = f"{r.cuadros_por_segundo:.1f}".replace(".", ",")
        self.etiqueta_estado.setText(f"Exportado: {r.ruta}  ·  {r.ancho} × {r.alto}  ·  {formato_tiempo(r.duracion)}")
        con = (f" · {sonido}" if sonido else " · con audio") if r.con_audio else " · sin sonido"
        detalle = (f"{r.ancho} × {r.alto} · {formato_tiempo(r.duracion)} · {r.cuadros} cuadros"
                   f"{con}"
                   f"{' · calidad mejorada (sin IA)' if getattr(r, 'mejorado', False) else ''}\n"
                   f"Tardó {formato_tiempo(r.segundos, decimas=False)} ({velocidad} cuadros por segundo).")
        if not self.isVisible():
            # Se está trabajando en las fotos: un aviso que no interrumpe (la ventana lo muestra).
            self.exportacionLista.emit(f"Listo: se exportó el video {Path(r.ruta).name}.", f"{r.ruta}\n{detalle}")
            return
        QMessageBox.information(self, "Video exportado", f"Se guardó el video en:\n{r.ruta}\n\n{detalle}")

    # ============================================================ guardar solo el audio
    def guardar_audio(self) -> None:
        """"Guardar solo el audio…": el sonido de lo que se exporta (cortes y tarjeta Sonido) en M4A,
        WAV o MP3, en segundo plano, con progreso y Cancelar en la tarjeta. El original no se toca."""
        if self.info is None or self.edicion is None or self.panel_sonido.guardando:
            return
        if not self._hay_sonido():
            QMessageBox.information(self, "Sin sonido", "Este video no tiene sonido para guardar.")
            return
        if self.audio.quitar:
            QMessageBox.information(self, "Sonido quitado", "El sonido está quitado (tarjeta Sonido): no hay audio "
                                    "para guardar. Apagá \"Quitar el sonido\" para guardarlo.")
            return
        tramos = self.edicion.tramos_conservados()
        if not tramos:
            QMessageBox.information(self, "Nada para guardar", "No queda nada: está todo borrado. Recuperá "
                                    "lo borrado (tocá una marquita rosa) o deshacé con Ctrl+Z.")
            return
        formatos = ma.formatos_audio_disponibles()
        if not formatos:
            QMessageBox.warning(self, "No se puede guardar", "Esta instalación no puede guardar audio.")
            return
        self.pausar()
        filtros = [f"{f.descripcion} (*{f.extension})" for f in formatos]
        sugerida = ma.ruta_salida_audio(self.ruta, formatos[0].nombre)
        ruta, filtro = QFileDialog.getSaveFileName(self, "Guardar solo el audio", str(sugerida), ";;".join(filtros))
        if not ruta:
            return
        destino = Path(ruta)
        formato = next((f for f in formatos if f.extension == destino.suffix.lower()), None)
        if formato is None:  # sin extensión (o una que no es de audio): la del tipo elegido en el diálogo
            formato = formatos[filtros.index(filtro)] if filtro in filtros else formatos[0]
            destino = destino.with_suffix(formato.extension)
        if mv._misma_ruta(destino, Path(self.ruta)):
            QMessageBox.warning(self, "Elegí otro nombre",
                                "Ese es el video original. Para no sobrescribirlo, elegí otro nombre.")
            return
        externo = self.audio_externo
        if externo is not None and mv._misma_ruta(destino, Path(externo.ruta)):
            QMessageBox.warning(self, "Elegí otro nombre",
                                "Ese es el sonido que se está usando. Para no sobrescribirlo, elegí otro nombre.")
            return
        origen, audio, nombre = self.ruta, self.audio, formato.nombre
        pico = self._picos.get(self._clave_pico()) if audio.normalizar else None
        senales = self._senales
        self._cancelar_audio = False
        cancelado = lambda: self._cancelar_audio  # noqa: E731 - se lee desde el hilo que guarda

        def trabajo(_c):
            def avance(hechas, total, restante):
                senales.terminada.emit("avance_audio", 0, (hechas, total, restante))
            try:
                if externo is None:  # la misma llamada de siempre
                    return ma.exportar_audio(origen, destino, tramos, audio, nombre, avance, cancelado, pico)
                return mv.exportar_sonido(origen, destino, tramos, audio, externo, nombre, avance, cancelado, pico)
            except Cancelado:
                return "cancelado"

        self.panel_sonido.empezar_progreso()
        self.etiqueta_estado.setText(f"Guardando {destino.name}…")
        self._pool_guardar_audio.start(Tarea("audio_guardado", 0, trabajo, self._senales))

    def cancelar_guardado_audio(self) -> None:
        if self.panel_sonido.guardando:
            self._cancelar_audio = True

    def _audio_guardado(self, resultado) -> None:
        self.panel_sonido.terminar_progreso()
        if resultado == "cancelado":
            self.etiqueta_estado.setText("Se canceló. No quedó ningún archivo a medias.")
            return
        r: ma.ResultadoAudio = resultado
        self.ultimo_audio = r
        canales = "mono" if r.canales == 1 else "estéreo"
        detalle = (f"{ma.FORMATOS_AUDIO[r.formato].descripcion} · {formato_tiempo(r.duracion)} · "
                   f"{r.frecuencia // 1000} kHz · {canales}")
        self.etiqueta_estado.setText(f"Audio guardado: {r.ruta}")
        if not self.isVisible():
            self.exportacionLista.emit(f"Listo: se guardó el audio {Path(r.ruta).name}.", f"{r.ruta}\n{detalle}")
            return
        QMessageBox.information(self, "Audio guardado", f"Se guardó el audio en:\n{r.ruta}\n\n{detalle}")

    # ============================================================ ida y vuelta con el modo Audio
    def editar_sonido_en_audio(self) -> None:
        """"Editar el sonido en el modo Audio": guarda el sonido COMPLETO del original (sin cortes ni
        ajustes: alineado con el video) en un WAV de ``%APPDATA%\\NaturalShot PRO\\temporal``, en segundo
        plano, con progreso y Cancelar en la tarjeta. Al terminar emite ``editarSonidoPedido(wav, video)``:
        la ventana abre el modo Audio con él y, a la vuelta, llama a ``usar_sonido_externo(ruta,
        "original")``."""
        if self.info is None or self.panel_sonido.guardando:
            return
        if not self._video_tiene_sonido():
            QMessageBox.information(self, "Sin sonido", "Este video no tiene sonido para editar. Podés ponerle "
                                    "uno con \"Cambiar el sonido por…\".")
            return
        self.pausar()
        try:
            destino = mv.ruta_temporal_sonido(self.ruta)
        except OSError as error:
            QMessageBox.warning(self, "No se pudo preparar el sonido", f"No se pudo crear la carpeta temporal.\n\n"
                                f"{error}")
            return
        origen, senales = self.ruta, self._senales
        self._cancelar_audio = False
        cancelado = lambda: self._cancelar_audio  # noqa: E731 - se lee desde el hilo que guarda

        def trabajo(_c):
            def avance(hechas, total, restante):
                senales.terminada.emit("avance_audio", 0, (hechas, total, restante))
            try:
                return ma.exportar_audio(origen, destino, None, None, "wav", avance, cancelado), origen
            except Cancelado:
                return "cancelado"

        self.panel_sonido.empezar_progreso(para_audio=True)
        self.etiqueta_estado.setText("Preparando el sonido para el modo Audio…")
        self._pool_guardar_audio.start(Tarea("sonido_para_audio", 0, trabajo, self._senales))

    def _sonido_para_audio_listo(self, resultado) -> None:
        self.panel_sonido.terminar_progreso()
        if resultado == "cancelado":
            self.etiqueta_estado.setText("Se canceló. No quedó ningún archivo a medias.")
            return
        r, video = resultado
        self.ultimo_sonido_para_audio = str(r.ruta)
        self.etiqueta_estado.setText(f"El sonido de {Path(video).name} está listo para el modo Audio.")
        self.editarSonidoPedido.emit(str(r.ruta), str(video))

    def cambiar_sonido(self) -> None:
        """"Cambiar el sonido por…": elegir un audio que suena desde el principio de lo que se exporta
        (voz en off), cortado al final del video. Entra al historial."""
        if self.info is None:
            return
        actual = self.audio_externo.ruta if self.audio_externo is not None else self.ruta
        ruta, _ = QFileDialog.getOpenFileName(self, "Cambiar el sonido por…", str(Path(actual).parent),
                                              f"{FILTRO_AUDIO};;Todos los archivos (*.*)")
        if ruta:
            self.usar_sonido_externo(ruta, "resultado")

    def volver_al_sonido_original(self) -> None:
        """"Volver al sonido original": saca el sonido externo (con su paso de deshacer)."""
        if self.audio_externo is None:
            return
        self._editar(externo=None, descripcion="Vuelve a sonar el sonido del video. Ctrl+Z trae el otro.")

    def usar_sonido_externo(self, ruta: str, alineado: str = "original") -> bool:
        """Pone el sonido de otro archivo en lugar del sonido del video, con su paso de deshacer.

        ``alineado``: "original" (está alineado con el video original, sin cortes: por ejemplo, lo que
        devuelve el modo Audio con "Volver al video con este sonido"; los cortes del video se le aplican
        igual) o "resultado" (empieza en el 0 de lo que se exporta, como una voz en off). Si el sonido
        estaba quitado, vuelve. Devuelve False si no se pudo usar (avisa por qué)."""
        if self.info is None or self.edicion is None:
            return False
        try:
            externo = mv.AudioExterno(str(ruta), alineado)
            mv.validar_audio_externo(externo)
        except ValueError as error:
            QMessageBox.warning(self, "No se puede usar ese sonido", str(error))
            return False
        if externo.desde_cero:
            texto = (f"Ahora suena {externo.nombre}, desde el principio: se corta al final del video. Ctrl+Z "
                     "vuelve al de antes.")
        else:
            texto = "Ahora suena el sonido editado en el modo Audio, con los mismos cortes. Ctrl+Z vuelve al de antes."
        audio = self.audio.con(quitar=False) if self.audio.quitar else None
        if not self._editar(audio=audio, externo=externo, descripcion=texto):
            self.etiqueta_estado.setText("Ese sonido ya es el que suena.")
        return True

    def _externos_en_uso(self) -> set:
        """Las rutas de los sonidos externos de ahora y del historial (no se borran)."""
        rutas = {s.externo.ruta for s in self._deshacer + self._rehacer if s.externo is not None}
        if self.audio_externo is not None:
            rutas.add(self.audio_externo.ruta)
        if self.ultimo_sonido_para_audio:
            rutas.add(self.ultimo_sonido_para_audio)
        return rutas

    def limpiar_temporales(self) -> list:
        """Borra los WAV de ``temporal`` de más de ``mv.DIAS_TEMPORALES`` días (al abrir el editor), menos
        los que están en uso. Si uno está sonando, antes se cierra su lector."""
        def antes_de_borrar(ruta: Path) -> None:
            lector = self.reproductor.lector
            leida = getattr(lector, "ruta", None) if lector is not None else None
            if leida and mv._misma_ruta(Path(leida), ruta):
                self.reproductor.detener()  # cierra el lector (y su archivo) antes de borrarlo
                self._con_sonido = False

        try:
            return mv.limpiar_temporales(conservar=self._externos_en_uso(), antes_de_borrar=antes_de_borrar)
        except Exception:  # limpiar nunca impide abrir el editor
            return []

    # ============================================================ cerrar la app
    def detener(self) -> None:
        """Al cerrar la ventana: cancela lo que esté en curso (también una exportación, que no deja
        archivos a medias), espera a los hilos y libera los archivos abiertos."""
        if self.exportando:
            self._cancelar_exportacion = True
        self._cancelar_audio = True
        self._reproduciendo = False
        self._timer_reproducir.stop()
        self._timer_rapido.stop()
        self._timer_completo.stop()
        self._timer_sonido.stop()
        self.reproductor.cerrar()
        self._con_sonido = False
        self.cargador_onda.detener()
        self._generacion += 1
        self._generacion_info += 1
        for pool in (self._pool_cuadros, self._pool_info, self._pool_exportar, self._pool_pico,
                     self._pool_guardar_audio):
            pool.waitForDone()
        mv.cerrar_lectores()


# Nombre anterior: era una ventana aparte. Ahora el editor va siempre adentro de la ventana principal.
VentanaVideo = EditorVideo
