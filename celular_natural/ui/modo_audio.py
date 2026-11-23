"""Modo Audio: que una voz limpia (o hecha con IA) suene grabada con un celular en un lugar real.

Es el cuarto modo de la ventana principal (selector "Fácil | Editor | Video |
Audio", Ctrl+Shift+A): va adentro de la misma ventana, nunca en una aparte.
``EditorAudio`` es la parte central y derecha; su columna izquierda ("Que suene
real") está en ``EditorAudio.lateral``, que la ventana pone debajo de la marca y
del selector. Hay una sola instancia, que la ventana arma la primera vez que se
entra a Audio (recién ahí se carga PyAV).

El motor es ``motor/proyecto_audio.py`` (``ProyectoAudio``, escenas, "Mis
sonidos", ``MezcladorAudio`` y ``exportar_proyecto``); acá solo está la interfaz.

* **Centro:** la forma de onda grande de la voz (con zoom y cursor), reproducir y
  pausar (Espacio) y la línea de tiempo con tres pistas: **Voz** (cortes, tramos
  borrados con su marquita para recuperarlos y silencios, como en Video: I, O, S,
  Supr, M y R), **Fondo** (una franja con cada capa) y **Sonidos** (bloques que se
  arrastran en el tiempo). Comparar: "Antes" escucha la voz sin la escena. Arriba,
  si el sonido vino de un video, la franja "Volver al video con este sonido" (y
  ahí no se corta: los cortes se hacen en el video).
* **Izquierda, "Que suene real":** escenas (y las propias, con "Guardar como
  escena"), ¿Cómo se grabó?, Cuánto, Bajarle lo de IA y Avanzado (lugar y eco,
  ruido propio y compresión del destino).
* **Derecha, "Ambiente":** fondo continuo (hasta 3 capas, de la galería o de Mis
  sonidos, con volumen, intensidad, quitar y escuchar 3 s), sonidos sueltos
  ("Agregar en el cursor", volumen y borrar), que tape la voz, Mis sonidos
  (agregar, renombrar, borrar; lo que falta se marca), el volumen general
  (``PanelSonido``) y Exportar (WhatsApp, M4A, MP3 o WAV, en segundo plano, con
  progreso y Cancelar; sigue aunque se cambie de modo: la ventana muestra un chip).

Estado e historial
------------------
El estado es un par (``ProyectoAudio``, ``EdicionVideo``): el proyecto tiene todo lo
que suena y la edición, los cortes de la voz (en la grilla de 1 ms de
``audio.FPS_SOLO_AUDIO``; ``proyecto.tramos`` son siempre sus tramos conservados).
Los dos son inmutables: el historial es una lista de pasos (descripción, proyecto,
edición) y una posición. Deshacer y rehacer (Ctrl+Z, Ctrl+Y) se mueven por ella. Los
movimientos seguidos de un mismo control (un deslizador) en menos de ``JUNTAR``
segundos son un solo paso; si vuelven al valor de antes, el paso se saca y el gesto
termina (lo próximo es un paso nuevo, nunca se pega a uno de otra cosa).

La sesión (``sesion.AudioGuardado``) guarda el proyecto, la edición (como tupla
simple), el cursor, el historial y la posición: ``estado_sesion`` y
``restaurar_sesion``. La ventana decide cuándo.

Escuchar
--------
Con ``ReproductorAudio.reproducir_lector`` y un ``MezcladorAudio`` con lectura
adelantada (el mismo de la exportación). Un cambio mientras suena se aplica con
``cambiar_proyecto``, sin cortar; un cambio de tramos vuelve a armar lo que suena
desde el cursor. "Normalizar" mide el pico exacto en otro hilo
(``medir_pico_proyecto``) y, mientras tanto, usa el que se estima con la forma de
onda de la voz. "Escuchar 3 s" de un fondo usa un ``GeneradorFondo`` nuevo cada vez
(nunca el del mezclador). Sin salida de sonido (o en las pruebas sin pantalla) todo
anda igual, con un reloj propio y sin sonido.

Hilos con ``Tarea`` y ``QThreadPool``, como el resto de la app. Sin filtros
globales de eventos.
"""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Sequence

import numpy as np
from PySide6.QtCore import QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLayout, QLineEdit,
    QMenu,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import sesion
from ..motor import Cancelado
from ..motor import ambientes as am
from ..motor import audio as ma
from ..motor import proyecto_audio as pa
from ..motor import voz_natural as vn
from ..motor.video import EdicionVideo, Hueco, MapaTiempo, Segmento, recuperar_hueco
from . import estilo, iconos
from .controles import COLOR_SECCION, SUBTITULO_SECCION, ControlDeslizante, SeccionPlegable
from .forma_onda import CargadorOnda, pico_aproximado
from .linea_tiempo import formato_duracion, formato_tiempo
from .modo_facil import configuracion
from .modo_video import COLOR_AUDIO, FILTRO_ABRIR_AUDIO, EtiquetaElidida
from .paneles_audio import (
    ControlCuanto, FilaCapaFondo, FilaMiSonido, FilaSonido, GaleriaEscenas, PanelSonidoAudio, SelectorDestino,
    TarjetaOpcion, grilla, titulo_galeria,
)
from .pistas_audio import (
    BloqueSonido, CapaVista, InvitacionAudio, LineaVoz, OndaGrande, PistaFondo, PistaSonidos,
)
from .reproductor_audio import ReproductorAudio
from .tareas import SenalesTarea, Tarea

if TYPE_CHECKING:  # pragma: no cover
    from .ventana import VentanaPrincipal

FPS = float(ma.FPS_SOLO_AUDIO)   # la grilla de los cortes: 1 ms
COLUMNAS_ONDA = 8000             # la forma de onda se pide una vez (el zoom llega a 8 veces el ancho)
MAX_HISTORIAL = 100
JUNTAR = 1.5                     # s: los cambios seguidos de un mismo control son un solo paso de deshacer
ESPERA_SONIDO = 0.08             # s: al mover el cursor mientras suena, el sonido vuelve cuando se queda quieto
SEGUNDOS_ESCUCHAR = 3.0          # "escuchar 3 s" de un fondo o de un archivo de Mis sonidos
ESPERA_CERRAR = 0.5              # s que se espera al hilo del mezclador al cerrar la app
ESPERA_ARCHIVOS = 1.0            # s que se espera al mezclador antes de borrar o renombrar un archivo
ANCHO_DERECHO = 340
CLAVE_SONIDO_VISTA = "audio/sonido_vista_previa"   # QSettings: si la vista previa suena
CLAVE_FORMATO = "audio/formato_exportar"
SIN_AUDIO = "Abrí un audio para empezar: una voz grabada o hecha con IA."
AYUDA_LINEA = ("Tocá o arrastrá para moverte · S corta · tocá un tramo: Supr lo borra y M lo silencia · arrastrá "
               "los corchetes para recortar · arrastrá un sonido para moverlo")
AYUDA_LINEA_CON_BORRADOS = ("Tocá una marquita rosa para recuperar lo borrado (o R, o Ctrl+Z) · S corta · Supr borra "
                            "· M silencia · arrastrá un sonido para moverlo")
AYUDA_LINEA_VIDEO = ("Sonido de un video: los cortes se hacen en el video · tocá o arrastrá para moverte · M silencia "
                     "un tramo · arrastrá un sonido para moverlo")
TEXTO_CORTES_EN_VIDEO = "Para cortar, hacelo en el video: si lo cortás acá, el sonido se desalinea con la imagen."
NOMBRES_FORMATO = {"whatsapp": "WhatsApp", "m4a": "M4A", "mp3": "MP3", "wav": "WAV"}
DETALLE_FORMATO = {
    "whatsapp": "Nota de voz de WhatsApp: .ogg, Opus mono",
    "m4a": "M4A (AAC), estéreo",
    "mp3": "MP3, estéreo",
    "wav": "WAV sin compresión, estéreo",
}

# Tarjetas propias del modo (mismo estilo que las secciones del panel).
for _nombre, _color, _subtitulo in (
    ("Escenas", "#d946ef", "Todo armado con un clic"),
    ("¿Cómo se grabó?", "#a78bfa", "El micrófono y la compresión"),
    ("Bajarle lo de IA", "#f472b6", "Que la voz no suene perfecta"),
    ("Avanzado", "#94a3b8", "Lugar y eco, ruido y compresión"),
    ("Fondo continuo", "#a78bfa", "Hasta 3 capas, de punta a punta"),
    ("Sonidos sueltos", "#38bdf8", "En un momento justo"),
    ("Mis sonidos", "#fbbf24", "Tus archivos, guardados en la app"),
    ("Atajos del audio", "#94a3b8", "Para editar sin el mouse"),
):
    COLOR_SECCION.setdefault(_nombre, _color)
    SUBTITULO_SECCION.setdefault(_nombre, _subtitulo)


# ======================================================================== piezas sin interfaz
def abrir_voz(ruta: str) -> pa.ProyectoAudio:
    """Un proyecto nuevo con la voz de ``ruta``, o ``ValueError`` con un texto claro para el
    aviso ("«x.m4a» no tiene sonido…", "No se pudo abrir «x»…")."""
    nombre = Path(ruta).name
    try:
        return pa.abrir_proyecto(ruta)
    except FileNotFoundError:
        raise ValueError(f"No se encontró «{nombre}».") from None
    except ValueError as error:
        texto = str(error)
        if "no tiene sonido" in texto and nombre not in texto:
            texto = f"«{nombre}» no tiene sonido: no se puede abrir en el modo Audio."
        raise ValueError(texto) from None
    except Exception:
        raise ValueError(f"No se pudo abrir «{nombre}»: no parece un archivo de sonido.") from None


def datos_edicion(e: EdicionVideo) -> tuple:
    """Una edición como tupla de números (para la sesión, que solo guarda valores simples)."""
    return (float(e.duracion), float(e.fps), tuple((float(s.inicio), float(s.fin), bool(s.borrado))
                                                   for s in e.segmentos),
            float(e.entrada), None if e.salida is None else float(e.salida))


def edicion_de_tramos(tramos: Sequence[tuple[float, float]], duracion: float) -> EdicionVideo:
    """Una edición cuyos tramos conservados son ``tramos`` (lo de en medio, borrado)."""
    segmentos, anterior = [], 0.0
    for a, b in tramos:
        a, b = max(0.0, float(a)), min(float(duracion), float(b))
        if b - a < 1e-6:
            continue
        if a - anterior > 1e-6:
            segmentos.append(Segmento(anterior, a, True))
        segmentos.append(Segmento(a, b))
        anterior = b
    if duracion - anterior > 1e-6 or not segmentos:
        segmentos.append(Segmento(anterior, float(duracion), bool(segmentos)))
    return EdicionVideo(float(duracion), FPS, tuple(segmentos))


def _mismos_tramos(a: Sequence, b: Sequence) -> bool:
    a, b = list(a), list(b)
    return len(a) == len(b) and all(abs(x[0] - y[0]) < 1e-5 and abs(x[1] - y[1]) < 1e-5 for x, y in zip(a, b))


def edicion_de_datos(datos, duracion: float, tramos: Sequence) -> EdicionVideo:
    """La edición guardada (``datos_edicion``) si sigue valiendo para este archivo y estos tramos;
    si no (otra versión, archivo cambiado), una armada con los tramos del proyecto."""
    try:
        dur, fps, segs, entrada, salida = datos
        segmentos = tuple(Segmento(float(a), float(b), bool(c)) for a, b, c in segs)
        e = EdicionVideo(float(dur), float(fps), segmentos, float(entrada), None if salida is None else float(salida))
        contiguos = (segmentos and abs(segmentos[0].inicio) < 1e-9 and abs(segmentos[-1].fin - e.duracion) < 1e-6
                     and all(abs(x.fin - y.inicio) < 1e-9 for x, y in zip(segmentos, segmentos[1:])))
        if contiguos and abs(e.duracion - duracion) < 0.01 and _mismos_tramos(e.tramos_conservados(), tramos):
            return e
    except (TypeError, ValueError):
        pass
    return edicion_de_tramos(tramos, duracion)


def semilla_libre(elementos, origen: str, clave: str) -> int:
    """La primera semilla que no usa ninguna capa (o sonido) con ese origen y esa clave: así dos
    iguales nunca suenan idénticos (también después de quitar uno del medio)."""
    usadas = {e.semilla for e in elementos if (e.origen, e.clave) == (origen, clave)}
    return next(s for s in range(len(usadas) + 1) if s not in usadas)


def nombre_fondo(f: pa.FondoProyecto) -> tuple[str, str, bool]:
    """(ícono, nombre, si tiene intensidad) de una capa."""
    if f.origen == "generado":
        info = am.FONDOS.get(f.clave)
        return (info.icono, info.nombre, info.intensidad) if info else ("waves", f.clave, False)
    return "music", Path(f.clave).stem, False


def nombre_sonido(s: pa.SonidoSuelto) -> tuple[str, str]:
    if s.origen == "generado":
        info = am.SONIDOS.get(s.clave)
        return (info.icono, info.nombre) if info else ("music", s.clave)
    return "music", Path(s.clave).stem


def _calibrar(x: np.ndarray, nivel: float) -> np.ndarray:
    rms = float(np.sqrt(np.mean(np.square(x, dtype=np.float64)))) if x.size else 0.0
    return x * min(nivel / max(rms, 1e-12), 100.0)


def muestra_fondo(fondo: pa.FondoProyecto, segundos: float = SEGUNDOS_ESCUCHAR) -> np.ndarray:
    """Los primeros ``segundos`` de una capa, sola y con su volumen: (n, 2) float32.

    Un fondo generado sale de un ``GeneradorFondo`` nuevo (nunca el de un mezclador); un
    archivo de Mis sonidos, calibrado al mismo nivel que en la mezcla y repetido si es corto."""
    n = int(round(segundos * pa.FRECUENCIA))
    if fondo.origen == "generado":
        x = am.GeneradorFondo(fondo.clave, fondo.intensidad, fondo.semilla, pa.FRECUENCIA).leer(0, n)
    else:
        datos = pa.cargar_sonido(fondo.clave)
        if datos is None or not len(datos):
            raise ValueError(f"No está «{fondo.clave}» en Mis sonidos.")
        x = np.resize(np.asarray(datos), (n, 2)) if len(datos) < n else np.asarray(datos[:n])
        x = _calibrar(x, 10 ** (am.NIVEL_FONDO_DBFS / 20))
    return _con_fundidos(np.asarray(x, np.float32) * np.float32(pa.ganancia_volumen(fondo.volumen)))


def muestra_archivo(nombre: str, segundos: float = SEGUNDOS_ESCUCHAR) -> np.ndarray:
    """Los primeros ``segundos`` de un archivo de Mis sonidos, tal cual (con fundidos cortos)."""
    datos = pa.cargar_sonido(nombre)
    if datos is None or not len(datos):
        raise ValueError(f"No está «{nombre}» en Mis sonidos.")
    return _con_fundidos(np.array(datos[:int(round(segundos * pa.FRECUENCIA))], np.float32))


def _con_fundidos(x: np.ndarray, fundido: float = 0.03) -> np.ndarray:
    n = min(len(x) // 2, int(fundido * pa.FRECUENCIA))
    if n > 0:
        rampa = np.linspace(0.0, 1.0, n, dtype=np.float32)[:, None]
        x[:n] *= rampa
        x[-n:] *= rampa[::-1]
    return np.clip(x, -1.0, 1.0)


class LectorArreglo:
    """Un lector (interfaz de ``LectorPCM``) de un arreglo ya en memoria: para "escuchar 3 s"."""

    bytes_por_muestra = 4
    tiene_audio = True

    def __init__(self, datos: np.ndarray):
        self._datos = (np.clip(datos, -1.0, 1.0) * 32767.0).astype("<i2")
        self._pos = 0

    @property
    def terminado(self) -> bool:
        return self._pos >= len(self._datos)

    @property
    def posicion_resultado(self) -> float:
        return self._pos / pa.FRECUENCIA

    def original_de_resultado(self, t: float) -> float:
        return t

    def leer(self, muestras: int) -> bytes:
        trozo = self._datos[self._pos:self._pos + max(0, int(muestras))]
        self._pos += len(trozo)
        return trozo.tobytes()

    def ir_a(self, t: float) -> None:
        self._pos = min(len(self._datos), max(0, round(t * pa.FRECUENCIA)))

    def cambiar_ajustes(self, *_args, **_kw) -> None:
        pass

    def cerrar(self) -> None:
        pass


def cerrar_lector(lector, esperar: float = 0.0) -> None:
    """Cierra un lector; si es un mezclador que lo acepta, espera a su hilo hasta ``esperar`` s."""
    if lector is None:
        return
    try:
        lector.cerrar(esperar=esperar)
    except TypeError:  # una versión del motor sin "esperar"
        lector.cerrar()
    except Exception:
        pass


def ancho_pedido(capa: QLayout) -> int:
    """Ancho que pide una fila horizontal con los textos de ahora (como en el editor de video:
    se suma pieza por pieza, entrando en los segmentos; lo oculto y lo que se puede achicar no cuenta)."""
    margen = capa.contentsMargins()
    total, piezas = margen.left() + margen.right(), 0
    for i in range(capa.count()):
        item = capa.itemAt(i)
        w, sub = item.widget(), item.layout()
        if w is not None:
            if w.isHidden():
                continue
            if isinstance(w.layout(), QHBoxLayout):
                ancho = ancho_pedido(w.layout()) + 2
            elif w.sizePolicy().horizontalPolicy() == QSizePolicy.Ignored:
                ancho = 0
            else:
                ancho = max(w.sizeHint().width(), w.minimumWidth())
        elif sub is not None:
            ancho = ancho_pedido(sub)
        else:
            total += item.sizeHint().width()
            continue
        total += ancho
        piezas += 1
    return total + max(0, capa.spacing()) * max(0, piezas - 1)


# ======================================================================== el editor
class EditorAudio(QWidget):
    """El modo Audio (ver el docstring del módulo).

    ``ventana``: la ventana principal. Abrir (Ctrl+O, el botón o un clic en la invitación)
    y soltar archivos pasan por ella, que rutea fotos, videos y audios. Sin ventana (usos
    aislados) abre audios por su cuenta.

    Para la ventana: ``lateral`` (la columna izquierda), ``vista`` (donde va el aviso
    flotante), ``ruta``, ``proyecto``, ``exportando``, ``abrir``, ``cargar_proyecto``,
    ``confirmar_reemplazo``, ``es_el_abierto``, ``tiene_cambios``, ``cerrar_audio``,
    ``pausar``, ``compactar``, ``detener``, ``estado_sesion`` y ``restaurar_sesion``.

    Ida y vuelta con Video: ``abrir_desde_video(ruta_wav, ruta_video)`` abre el sonido de un
    video (``video_origen``): se ve la franja "Sonido del video X · Volver al video con este
    sonido" y no se corta ni se borra (``cortes_bloqueados``; I, O, S, Supr, R y los
    corchetes avisan "Para cortar, hacelo en el video"). ``volver_al_video()`` (el botón de la
    franja) exporta un WAV a ``carpeta_temporal()`` y emite
    ``volverAlVideoPedido(ruta_wav, ruta_video)``. ``mostrar_franja_video(nombre)`` la muestra
    a mano. Abrir un audio común saca el bloqueo y la franja.
    """

    audioCambiado = Signal()                # se abrió o se cerró un audio
    estadoCambiado = Signal()               # cambió el proyecto o el historial (para la sesión)
    exportacionCambiada = Signal(bool)      # empezó (True) o terminó (False) una exportación
    progresoExportacion = Signal(int, int)  # muestras hechas y total
    exportacionLista = Signal(str, str)     # terminó mientras el editor no estaba a la vista: (texto, detalle)
    # Ida y vuelta con Video: "Volver al video con este sonido" ya exportó el WAV: (ruta del WAV, ruta del video).
    volverAlVideoPedido = Signal(str, str)

    def __init__(self, ventana: Optional["VentanaPrincipal"] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._ventana = ventana
        self.proyecto: Optional[pa.ProyectoAudio] = None
        self.edicion: Optional[EdicionVideo] = None
        self.info = None                       # InfoVideo de la voz (audio.info_medio)
        self.duracion_original = 0.0
        self.tiempo = 0.0                      # el cursor, en tiempo original (siempre en algo que se oye)
        self._mapa_de: tuple = (None, MapaTiempo((), 0.0))
        # Historial: [(descripción, proyecto, edición)] y la posición actual.
        self._historial: list[tuple[str, pa.ProyectoAudio, EdicionVideo]] = []
        self._pos = -1
        self._ultimo_control = ("", 0.0)       # (control, momento) del último cambio con control
        self._indice_gesto = -1                # el paso que abrió ese gesto (solo se junta con él)
        self.exportando = False
        self.ultima_exportacion: Optional[ma.ResultadoAudio] = None
        self._cancelar_exportacion = False
        self._inicio_exportacion = 0.0
        self._picos: dict = {}                 # pico exacto por proyecto (sin volumen, normalizar ni fundidos)
        self._midiendo: set = set()
        self._pico_pedido = None
        self._largos: dict = {}                # (origen, clave, semilla) -> segundos de un sonido suelto
        self._calentando: set = set()
        self._faltan_mezcla: tuple = ()
        self._reproduciendo = False
        self._con_sonido = False
        self._t_base = 0.0
        self._t_reloj = 0.0
        self._escuchar_antes = False           # comparar: la voz sin la escena
        self._generacion_escucha = 0
        self._iconos_linea = 0
        self._resultado_corto = False

        self._pool_exportar = QThreadPool(self)
        self._pool_exportar.setMaxThreadCount(1)
        self._pool_pico = QThreadPool(self)
        self._pool_pico.setMaxThreadCount(1)
        self._pool_trabajo = QThreadPool(self)  # sonidos que se preparan y "escuchar 3 s"
        self._pool_trabajo.setMaxThreadCount(1)
        self._pool_volver = QThreadPool(self)   # "Volver al video con este sonido": el WAV para el video
        self._pool_volver.setMaxThreadCount(1)
        # Lo que suena se arma y se cambia en este hilo (sintetizar sonidos o leer los de Mis sonidos puede
        # tardar): primero se preparan los sonidos y después el mezclador, en ese orden.
        self._pool_sonido = QThreadPool(self)
        self._pool_sonido.setMaxThreadCount(1)
        self._gen_armado = 0                    # el último mezclador pedido (los viejos se descartan)
        self._gen_cambio = 0                    # el último cambio pedido para lo que suena
        self.volviendo = False
        self._cancelar_volver = False
        self._proyecto_exportando: Optional[pa.ProyectoAudio] = None
        self._proyecto_volviendo: Optional[pa.ProyectoAudio] = None
        self._senales = SenalesTarea(self)
        self._senales.terminada.connect(self._tarea_terminada)
        self._senales.fallida.connect(self._tarea_fallida)

        self._timer_reproducir = QTimer(self, interval=16)
        self._timer_reproducir.timeout.connect(self._tick)
        self._timer_sonido = QTimer(self, singleShot=True, interval=round(ESPERA_SONIDO * 1000))
        self._timer_sonido.timeout.connect(self._iniciar_sonido)

        self.reproductor = ReproductorAudio(self)
        self.reproductor.establecer_silenciado(not self._sonido_vista_guardado())
        self.reproductor.fallo.connect(self._sonido_fallo)
        self.reproductor.terminado.connect(self._sonido_terminado)
        self.cargador_onda = CargadorOnda(self, columnas=COLUMNAS_ONDA)

        self._construir_interfaz()
        self._construir_acciones()
        self.cargador_onda.parcial.connect(self._onda_parcial)
        self.cargador_onda.lista.connect(self._onda_lista)
        self.cargador_onda.fallida.connect(self._onda_fallida)
        self._refrescar_escenas()
        self._refrescar_mis_sonidos()
        self._actualizar_vistas()

    # ============================================================ interfaz
    def _construir_interfaz(self) -> None:
        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        centro = QVBoxLayout()
        centro.setContentsMargins(14, 14, 14, 14)
        centro.setSpacing(12)
        centro.addWidget(self._construir_franja_video())
        centro.addWidget(self._construir_barra_herramientas())
        centro.addWidget(self._construir_tarjeta_onda(), 1)
        centro.addWidget(self._construir_tarjeta_linea())
        raiz.addLayout(centro, 1)
        self._derecho = self._construir_panel_derecho()
        raiz.addWidget(self._derecho)
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

    @staticmethod
    def _desplazable(contenido: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setWidget(contenido)
        return area

    # ------------------------------------------------------------ centro
    def _construir_franja_video(self) -> QWidget:
        """La franja de la ida y vuelta con Video: "Sonido del video X · Volver al video con este
        sonido", con el progreso del WAV que se arma al volver. Se ve si el proyecto vino de un
        video (``ProyectoAudio.video_origen``)."""
        franja = QFrame()
        franja.setObjectName("franjaVideo")
        fila = QHBoxLayout(franja)
        fila.setContentsMargins(12, 6, 8, 6)
        fila.setSpacing(10)
        icono = QLabel()
        icono.setPixmap(iconos.pixmap("film", 16, estilo.ROSA))
        self.texto_franja_video = EtiquetaElidida("")
        self.texto_franja_video.setObjectName("textoFranjaVideo")
        self.barra_volver = QProgressBar()
        self.barra_volver.setRange(0, 1000)
        self.barra_volver.setTextVisible(False)
        self.barra_volver.setFixedWidth(90)
        self.barra_volver.hide()
        self.boton_cancelar_volver = QPushButton()
        self.boton_cancelar_volver.setObjectName("botonIconoAudio")
        self.boton_cancelar_volver.setIcon(iconos.icono("x", 14))
        self.boton_cancelar_volver.setFixedSize(26, 26)
        self.boton_cancelar_volver.setToolTip("Cancelar: el video queda como estaba")
        self.boton_cancelar_volver.clicked.connect(self.cancelar_volver)
        self.boton_cancelar_volver.hide()
        self.boton_volver_al_video = QPushButton(" Volver al video con este sonido")
        self.boton_volver_al_video.setObjectName("botonChico")
        self.boton_volver_al_video.setIcon(iconos.icono("film", 14))
        self.boton_volver_al_video.setCursor(Qt.PointingHandCursor)
        self.boton_volver_al_video.setToolTip("Arma el sonido con todo lo que le hiciste (un WAV) y se lo pone al "
                                              "video, alineado con la imagen")
        self.boton_volver_al_video.clicked.connect(self.volver_al_video)
        fila.addWidget(icono)
        fila.addWidget(self.texto_franja_video, 1)
        fila.addWidget(self.barra_volver)
        fila.addWidget(self.boton_cancelar_volver)
        fila.addWidget(self.boton_volver_al_video)
        franja.hide()
        self.franja_video = franja
        return franja

    def mostrar_franja_video(self, nombre_video: Optional[str]) -> None:
        """Muestra arriba "Sonido del video ``nombre_video``" con el botón "Volver al video con este
        sonido" (``volver_al_video``). None la oculta. La pone sola ``_actualizar_vistas`` según
        ``proyecto.video_origen``."""
        if not nombre_video:
            self.franja_video.hide()
            return
        self.texto_franja_video.setText(f"Sonido del video {nombre_video}")
        self.texto_franja_video.setToolTip("Lo que cortes en el video se le aplica igual a este sonido: acá no se "
                                           "corta. Cuando termines, tocá «Volver al video con este sonido».")
        self.franja_video.show()

    def _construir_barra_herramientas(self) -> QWidget:
        barra = QFrame()
        barra.setObjectName("barraHerramientas")
        fila = QHBoxLayout(barra)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(10)
        self._fila_barra = fila
        self.boton_abrir = QPushButton(" Abrir audio")
        self.boton_abrir.setIcon(iconos.icono("audio-lines", 18, color="#ffffff"))
        self.boton_abrir.setIconSize(QSize(18, 18))
        self.boton_abrir.setObjectName("botonPrimario")
        self.boton_abrir.setToolTip("Abrir una voz (Ctrl+O): MP3, M4A, WAV, OGG, OPUS, AAC o FLAC. También podés "
                                    "arrastrarla. Si elegís fotos o videos, se abren en su modo.")
        self.boton_abrir.setCursor(Qt.PointingHandCursor)
        self.boton_abrir.clicked.connect(self.elegir_archivo)
        fila.addWidget(self.boton_abrir)
        self.boton_deshacer = self._boton("", "undo-2", "Deshacer el último cambio (Ctrl+Z): escenas, cortes, "
                                          "fondo, sonidos o volumen", 18)
        self.boton_deshacer.clicked.connect(self.deshacer)
        self.boton_rehacer = self._boton("", "redo-2", "Rehacer (Ctrl+Y)", 18)
        self.boton_rehacer.clicked.connect(self.rehacer)
        fila.addWidget(self._segmento([self.boton_deshacer, self.boton_rehacer]))
        self.etiqueta_paso = EtiquetaElidida("")
        self.etiqueta_paso.setObjectName("nota")
        self.etiqueta_paso.setToolTip("El último paso del historial (Ctrl+Z lo deshace)")
        fila.addWidget(self.etiqueta_paso, 1)
        return barra

    def _construir_tarjeta_onda(self) -> QWidget:
        tarjeta = QFrame()
        tarjeta.setObjectName("tarjetaVista")
        self.tarjeta_onda = tarjeta
        capa = QVBoxLayout(tarjeta)
        capa.setContentsMargins(16, 12, 16, 14)
        capa.setSpacing(10)
        encabezado = QHBoxLayout()
        encabezado.setSpacing(8)
        self._fila_onda = encabezado
        punto = QLabel("●")
        punto.setObjectName("puntoEstado")
        titulo = QLabel("Voz")
        titulo.setObjectName("tituloTarjeta")
        self.etiqueta_estado = EtiquetaElidida(SIN_AUDIO)
        self.etiqueta_estado.setObjectName("estadoImagen")
        self.barra_ocupado = QProgressBar()
        self.barra_ocupado.setRange(0, 0)
        self.barra_ocupado.setMaximumWidth(70)
        self.barra_ocupado.setTextVisible(False)
        self.barra_ocupado.hide()
        self.boton_alejar = self._boton("", "zoom-out", "Alejar (Ctrl+-)", 15)
        self.boton_acercar = self._boton("", "zoom-in", "Acercar (Ctrl++). También Ctrl + rueda sobre la onda.", 15)
        self.etiqueta_zoom = QLabel("×1")
        self.etiqueta_zoom.setObjectName("etiquetaZoom")
        self.etiqueta_zoom.setMinimumWidth(30)
        self.etiqueta_zoom.setAlignment(Qt.AlignCenter)
        self.boton_ajustar = self._boton("", "maximize", "Ver todo (Ctrl+0)", 15)
        encabezado.addWidget(punto)
        encabezado.addWidget(titulo)
        encabezado.addSpacing(10)
        encabezado.addWidget(self.etiqueta_estado, 1)
        encabezado.addWidget(self.barra_ocupado)
        encabezado.addWidget(self._segmento([self.boton_alejar, self.etiqueta_zoom, self.boton_acercar,
                                             self.boton_ajustar]))
        capa.addLayout(encabezado)

        self.invitacion = InvitacionAudio()
        self.invitacion.clic.connect(self.elegir_archivo)
        self.onda = OndaGrande()
        self.onda.pista.tiempoPedido.connect(self._tiempo_pedido)
        self.onda.pista.presionada.connect(self._pista_presionada)
        self.onda.zoomCambiado.connect(lambda z: self.etiqueta_zoom.setText(f"×{z}"))
        self.boton_alejar.clicked.connect(self.onda.alejar)
        self.boton_acercar.clicked.connect(self.onda.acercar)
        self.boton_ajustar.clicked.connect(self.onda.ajustar)
        self.vista = QStackedWidget()   # donde va el aviso flotante de la ventana
        self.vista.addWidget(self.invitacion)
        self.vista.addWidget(self.onda)
        capa.addWidget(self.vista, 1)

        transporte = QHBoxLayout()
        transporte.setSpacing(8)
        self._fila_transporte = transporte
        self.boton_inicio = self._boton("", "skip-back", "Ir al principio (Inicio)", 16)
        self.boton_inicio.clicked.connect(self.ir_al_inicio)
        self.boton_atras = self._boton("", "step-back", "Un segundo atrás (J)", 16)
        self.boton_atras.clicked.connect(lambda: self.mover_segundos(-1.0))
        self.boton_reproducir = QPushButton()
        self.boton_reproducir.setObjectName("botonPrimario")
        self.boton_reproducir.setIcon(iconos.icono("play", 18, color="#ffffff"))
        self.boton_reproducir.setIconSize(QSize(18, 18))
        self.boton_reproducir.setFixedSize(52, 36)
        self.boton_reproducir.setCursor(Qt.PointingHandCursor)
        self.boton_reproducir.setToolTip("Reproducir o pausar (Espacio)")
        self.boton_reproducir.clicked.connect(self.alternar_reproduccion)
        self.boton_adelante = self._boton("", "step-forward", "Un segundo adelante (L)", 16)
        self.boton_adelante.clicked.connect(lambda: self.mover_segundos(1.0))
        self.boton_fin = self._boton("", "skip-forward", "Ir al final (Fin)", 16)
        self.boton_fin.clicked.connect(self.ir_al_final)
        transporte.addWidget(self._segmento([self.boton_inicio, self.boton_atras]))
        transporte.addWidget(self.boton_reproducir)
        transporte.addWidget(self._segmento([self.boton_adelante, self.boton_fin]))
        transporte.addSpacing(6)
        self.etiqueta_tiempo = QLabel("0:00,00 / 0:00,00")
        self.etiqueta_tiempo.setObjectName("tituloTarjeta")
        self.etiqueta_tiempo.setToolTip("Tiempo actual / duración de lo que se exporta (sin lo borrado)")
        transporte.addWidget(self.etiqueta_tiempo)
        transporte.addStretch(1)
        self.boton_antes = self._boton(" Antes", "user-round", "Antes: escuchá la voz sin la escena (sin lugar, "
                                       "micrófono, fondo ni sonidos), con los cortes. Para comparar.", 15)
        self.boton_despues = self._boton(" Después", "wand-sparkles", "Después: como se va a exportar", 15)
        for b in (self.boton_antes, self.boton_despues):
            b.setCheckable(True)
        self.boton_despues.setChecked(True)
        self.boton_antes.clicked.connect(lambda: self._comparar(True))
        self.boton_despues.clicked.connect(lambda: self._comparar(False))
        transporte.addWidget(self._segmento([self.boton_antes, self.boton_despues]))
        self.boton_sonido = self._boton(" Sonido", "volume-2", "", 15)
        self.boton_sonido.setCheckable(True)
        self.boton_sonido.setChecked(not self.reproductor.silenciado)
        self.boton_sonido.toggled.connect(self._al_alternar_sonido_vista)
        transporte.addWidget(self._segmento([self.boton_sonido]))
        capa.addLayout(transporte)
        return tarjeta

    def _construir_tarjeta_linea(self) -> QWidget:
        tarjeta = QFrame()
        tarjeta.setObjectName("tiraFotos")
        capa = QVBoxLayout(tarjeta)
        capa.setContentsMargins(14, 10, 14, 12)
        capa.setSpacing(6)
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
                                         "Entrada (I): recorta lo de antes del cursor. Queda una marquita al "
                                         "principio para recuperarlo.", 15)
        self.boton_entrada.clicked.connect(self.marcar_entrada)
        self.boton_salida = self._boton(" Salida", "arrow-right-to-line",
                                        "Salida (O): recorta lo de después del cursor. Queda una marquita al final "
                                        "para recuperarlo.", 15)
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
        self.etiqueta_resultado.setToolTip("Lo que va a durar el audio exportado, de lo que dura la voz original")
        cabecera.addWidget(self.icono_reloj)
        cabecera.addWidget(self.etiqueta_resultado)
        capa.addLayout(cabecera)

        pistas = QGridLayout()
        pistas.setContentsMargins(0, 0, 0, 0)
        pistas.setHorizontalSpacing(8)
        pistas.setVerticalSpacing(4)
        self.linea = LineaVoz()
        self.linea.tiempoPedido.connect(self._tiempo_pedido)
        self.linea.seleccionCambiada.connect(lambda _i: self._al_cambiar_seleccion())
        self.linea.limitesPedidos.connect(self._limites_pedidos)
        self.linea.recuperarPedido.connect(self.recuperar)
        self.pista_fondo = PistaFondo()
        self.pista_fondo.tiempoPedido.connect(self._tiempo_pedido)
        self.pista_sonidos = PistaSonidos()
        self.pista_sonidos.tiempoPedido.connect(self._tiempo_pedido)
        self.pista_sonidos.anclaPedida.connect(self.mover_sonido)
        self.pista_sonidos.elegido.connect(self._sonido_elegido_en_pista)
        for fila, (texto, icono, widget) in enumerate((("Voz", "audio-lines", self.linea),
                                                       ("Fondo", "waves", self.pista_fondo),
                                                       ("Sonidos", "music", self.pista_sonidos))):
            etiqueta = QLabel(texto.upper())
            etiqueta.setObjectName("etiquetaPista")
            etiqueta.setFixedWidth(58)
            etiqueta.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            etiqueta.setToolTip({"Voz": "La voz: cortes, tramos borrados y silencios",
                                 "Fondo": "El fondo continuo (a la derecha, «Fondo continuo»)",
                                 "Sonidos": "Los sonidos sueltos: arrastralos para moverlos"}[texto])
            pistas.addWidget(etiqueta, fila, 0)
            pistas.addWidget(widget, fila, 1)
        pistas.setColumnStretch(1, 1)
        capa.addLayout(pistas)
        self.ayuda_linea = EtiquetaElidida(AYUDA_LINEA)
        self.ayuda_linea.setObjectName("nota")
        capa.addWidget(self.ayuda_linea)
        return tarjeta

    # ------------------------------------------------------------ derecha
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
        icono.setPixmap(iconos.pixmap("waves", 18))
        titulo = QLabel("AMBIENTE")
        titulo.setObjectName("tituloSeccion")
        encabezado.addWidget(icono)
        encabezado.addWidget(titulo, 1)
        capa.addLayout(encabezado)
        panel = QWidget()
        capa_panel = QVBoxLayout(panel)
        capa_panel.setContentsMargins(16, 0, 12, 12)
        capa_panel.setSpacing(8)
        capa_panel.addWidget(self._construir_tarjeta_fondo())
        capa_panel.addWidget(self._construir_tarjeta_sonidos())
        capa_panel.addWidget(self._construir_tarjeta_mis_sonidos())
        self.panel_volumen = PanelSonidoAudio(abierta=False)
        self.panel_volumen.ajustesCambiados.connect(self._al_cambiar_volumen_general)
        capa_panel.addWidget(self.panel_volumen)
        capa_panel.addStretch(1)
        capa.addWidget(self._desplazable(panel), 1)
        pie = QFrame()
        pie.setObjectName("pieDerecho")
        capa_pie = QVBoxLayout(pie)
        capa_pie.setContentsMargins(16, 12, 16, 14)
        capa_pie.addWidget(self._construir_exportacion())
        capa.addWidget(pie)
        return derecho

    def _construir_tarjeta_fondo(self) -> QWidget:
        tarjeta = SeccionPlegable("Fondo continuo", "waves", "Un ambiente que suena de punta a punta: hasta 3 capas "
                                  "(por ejemplo, olas y viento), de la galería o de Mis sonidos.", True,
                                  con_interruptor=False)
        self.tarjeta_fondo = tarjeta
        self.caja_capas = QVBoxLayout()
        self.caja_capas.setContentsMargins(0, 0, 0, 0)
        self.caja_capas.setSpacing(6)
        tarjeta.capa_cuerpo.addLayout(self.caja_capas)
        self.filas_capas: list[FilaCapaFondo] = []
        self.nota_fondo = QLabel("Sin fondo. Elegí uno de la galería (podés sumar hasta 3).")
        self.nota_fondo.setObjectName("nota")
        self.nota_fondo.setWordWrap(True)
        tarjeta.capa_cuerpo.addWidget(self.nota_fondo)
        self.boton_agregar_fondo = QPushButton(" Agregar una capa")
        self.boton_agregar_fondo.setObjectName("botonVerMas")
        self.boton_agregar_fondo.setIcon(iconos.icono("plus", 15))
        self.boton_agregar_fondo.setCheckable(True)
        self.boton_agregar_fondo.setCursor(Qt.PointingHandCursor)
        self.boton_agregar_fondo.setToolTip("Mostrar la galería de fondos (pasá el mouse por uno y tocá ▶ para "
                                            "escucharlo 3 segundos)")
        self.boton_agregar_fondo.toggled.connect(self._alternar_galeria_fondos)
        tarjeta.capa_cuerpo.addWidget(self.boton_agregar_fondo)
        self.galeria_fondos = QWidget()
        self._capa_galeria_fondos = QVBoxLayout(self.galeria_fondos)
        self._capa_galeria_fondos.setContentsMargins(0, 2, 0, 0)
        self._capa_galeria_fondos.setSpacing(6)
        self.tarjetas_fondo: dict[tuple[str, str], TarjetaOpcion] = {}
        tarjetas = []
        for clave, info in am.FONDOS.items():
            t = TarjetaOpcion(clave, info.nombre, "Con intensidad" if info.intensidad else "Generado",
                              info.icono, f"<b>{info.nombre}</b><br>{info.descripcion}<br>Tocá para sumarlo; ▶ lo "
                              "escucha 3 segundos.", accion="escuchar", color="#a78bfa")
            t.elegida.connect(lambda c: self.agregar_fondo("generado", c))
            t.accionPedida.connect(lambda c: self.escuchar_fondo(pa.FondoProyecto("generado", c)))
            self.tarjetas_fondo[("generado", clave)] = t
            tarjetas.append(t)
        self._capa_galeria_fondos.addWidget(titulo_galeria("Generados por la app"))
        self._capa_galeria_fondos.addWidget(grilla(tarjetas))
        self._titulo_fondos_mios = titulo_galeria("De Mis sonidos")
        self._capa_galeria_fondos.addWidget(self._titulo_fondos_mios)
        self._caja_fondos_mios: Optional[QWidget] = None
        self.galeria_fondos.hide()
        tarjeta.capa_cuerpo.addWidget(self.galeria_fondos)
        return tarjeta

    def _construir_tarjeta_sonidos(self) -> QWidget:
        tarjeta = SeccionPlegable("Sonidos sueltos", "music", "Un sonido en un momento justo: \"a los 12 segundos "
                                  "pasa un colectivo\". Sigue a la voz si cortás.", True, con_interruptor=False)
        self.tarjeta_sonidos = tarjeta
        self.boton_agregar_sonido = QPushButton(" Agregar en el cursor")
        self.boton_agregar_sonido.setObjectName("botonAbrir")
        self.boton_agregar_sonido.setIcon(iconos.icono("plus", 16))
        self.boton_agregar_sonido.setCursor(Qt.PointingHandCursor)
        self.boton_agregar_sonido.setToolTip("Suma un sonido que empieza donde está el cursor: uno generado por la "
                                             "app o uno de Mis sonidos")
        self.menu_sonidos = QMenu(self)
        self.menu_sonidos.aboutToShow.connect(self._armar_menu_sonidos)
        self.boton_agregar_sonido.setMenu(self.menu_sonidos)
        tarjeta.capa_cuerpo.addWidget(self.boton_agregar_sonido)
        self.caja_sonidos = QVBoxLayout()
        self.caja_sonidos.setContentsMargins(0, 0, 0, 0)
        self.caja_sonidos.setSpacing(6)
        tarjeta.capa_cuerpo.addLayout(self.caja_sonidos)
        self.filas_sonidos: list[FilaSonido] = []
        self.nota_sonidos = QLabel("Todavía no hay sonidos sueltos.")
        self.nota_sonidos.setObjectName("nota")
        self.nota_sonidos.setWordWrap(True)
        tarjeta.capa_cuerpo.addWidget(self.nota_sonidos)
        separador = QFrame()
        separador.setObjectName("separador")
        tarjeta.capa_cuerpo.addWidget(separador)
        self.control_tapa = ControlDeslizante(
            "tapa", "Que tape la voz", 0, 100,
            "El control automático de volumen del celular baja todo cuando pasa algo fuerte (el colectivo): la voz "
            "se tapa. 0 casi no baja; 100 la tapa bastante.")
        self.control_tapa.valorCambiado.connect(lambda _c, v: self.cambiar_voz("tapa", v / 100.0))
        tarjeta.capa_cuerpo.addWidget(self.control_tapa)
        return tarjeta

    def _construir_tarjeta_mis_sonidos(self) -> QWidget:
        tarjeta = SeccionPlegable("Mis sonidos", "folder-open", "Tus archivos de sonido (gente hablando, pájaros, "
                                  "un perro…): se copian a la app y quedan para usarlos de fondo o sueltos.", False,
                                  con_interruptor=False)
        self.tarjeta_mis_sonidos = tarjeta
        self.boton_agregar_mio = QPushButton(" Agregar a Mis sonidos…")
        self.boton_agregar_mio.setIcon(iconos.icono("plus", 15))
        self.boton_agregar_mio.setCursor(Qt.PointingHandCursor)
        self.boton_agregar_mio.setToolTip("Copia archivos de sonido (MP3, M4A, WAV, OGG, OPUS, AAC o FLAC, de hasta "
                                          "10 minutos) a la carpeta de la app. El original no se toca.")
        self.boton_agregar_mio.clicked.connect(self.agregar_a_mis_sonidos)
        tarjeta.capa_cuerpo.addWidget(self.boton_agregar_mio)
        self.caja_mis_sonidos = QVBoxLayout()
        self.caja_mis_sonidos.setContentsMargins(0, 0, 0, 0)
        self.caja_mis_sonidos.setSpacing(2)
        tarjeta.capa_cuerpo.addLayout(self.caja_mis_sonidos)
        self.filas_mis_sonidos: list[FilaMiSonido] = []
        self.nota_mis_sonidos = QLabel("")
        self.nota_mis_sonidos.setObjectName("nota")
        self.nota_mis_sonidos.setWordWrap(True)
        tarjeta.capa_cuerpo.addWidget(self.nota_mis_sonidos)
        return tarjeta

    def _construir_exportacion(self) -> QWidget:
        caja = QWidget()
        capa = QVBoxLayout(caja)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(8)
        titulo = QLabel("EXPORTAR AUDIO")
        titulo.setObjectName("tituloSeccion")
        capa.addWidget(titulo)
        selector = QFrame()
        selector.setObjectName("selectorFormato")
        fila = QHBoxLayout(selector)
        fila.setContentsMargins(3, 3, 3, 3)
        fila.setSpacing(3)
        disponibles = {f.nombre for f in pa.formatos_proyecto_disponibles()}
        self._formatos_disponibles = disponibles
        self.botones_formato: dict[str, QPushButton] = {}
        guardado = configuracion().value(CLAVE_FORMATO, "whatsapp")
        for nombre in pa.FORMATOS_PROYECTO:
            b = QPushButton(NOMBRES_FORMATO[nombre])
            b.setObjectName("opcionFormato")
            b.setProperty("centrado", True)
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setEnabled(nombre in disponibles)
            b.setToolTip(DETALLE_FORMATO[nombre] if nombre in disponibles else
                         f"{DETALLE_FORMATO[nombre]}: esta instalación no lo puede guardar.")
            b.clicked.connect(lambda _c=False, n=nombre: self._elegir_formato(n))
            self.botones_formato[nombre] = b
            fila.addWidget(b, 1)
        elegido = guardado if guardado in disponibles else next(iter(sorted(disponibles, key=pa.FORMATOS_PROYECTO.index)),
                                                                 "wav")
        if elegido in self.botones_formato:
            self.botones_formato[elegido].setChecked(True)
        capa.addWidget(selector)
        self.etiqueta_formato = QLabel("")
        self.etiqueta_formato.setObjectName("nota")
        self.etiqueta_formato.setWordWrap(True)
        capa.addWidget(self.etiqueta_formato)
        self.boton_exportar = QPushButton("  Exportar audio…")
        self.boton_exportar.setIcon(iconos.icono(iconos.GUARDAR, color="#ffffff"))
        self.boton_exportar.setIconSize(QSize(20, 20))
        self.boton_exportar.setObjectName("botonPrimario")
        self.boton_exportar.setToolTip("Guarda un archivo nuevo con todo (Ctrl+S). La voz original no se toca. "
                                       "Mientras exporta podés ir a otro modo: la exportación sigue.")
        self.boton_exportar.clicked.connect(self.exportar)
        capa.addWidget(self.boton_exportar)
        self.caja_progreso = QWidget()
        capa_prog = QVBoxLayout(self.caja_progreso)
        capa_prog.setContentsMargins(0, 2, 0, 0)
        capa_prog.setSpacing(6)
        fila_prog = QHBoxLayout()
        fila_prog.setSpacing(10)
        self.barra_exportacion = QProgressBar()
        self.barra_exportacion.setRange(0, 1000)
        self.barra_exportacion.setTextVisible(False)
        self.boton_cancelar = self._boton(" Cancelar", "x", "Cancelar la exportación: no queda ningún archivo a medias",
                                          15)
        self.boton_cancelar.setObjectName("botonChico")
        self.boton_cancelar.clicked.connect(self.cancelar_exportacion)
        fila_prog.addWidget(self.barra_exportacion, 1)
        fila_prog.addWidget(self.boton_cancelar)
        capa_prog.addLayout(fila_prog)
        self.etiqueta_progreso = QLabel("Preparando…")
        self.etiqueta_progreso.setObjectName("nota")
        self.etiqueta_progreso.setWordWrap(True)
        capa_prog.addWidget(self.etiqueta_progreso)
        self.caja_progreso.hide()
        capa.addWidget(self.caja_progreso)
        return caja

    # ------------------------------------------------------------ izquierda
    def _construir_barra_lateral(self) -> QWidget:
        """La columna izquierda, "Que suene real" (sin la marca ni el selector: son de la ventana)."""
        lateral = QWidget()
        lateral.setObjectName("lateralAudio")
        capa = QVBoxLayout(lateral)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(0)
        panel = QWidget()
        capa_panel = QVBoxLayout(panel)
        capa_panel.setContentsMargins(16, 6, 12, 16)
        capa_panel.setSpacing(10)
        encabezado = QHBoxLayout()
        encabezado.setContentsMargins(2, 0, 0, 0)
        encabezado.setSpacing(8)
        icono = QLabel()
        icono.setPixmap(iconos.pixmap("sparkles", 16))
        titulo = QLabel("QUE SUENE REAL")
        titulo.setObjectName("tituloSeccion")
        encabezado.addWidget(icono)
        encabezado.addWidget(titulo, 1)
        capa_panel.addLayout(encabezado)

        escenas = SeccionPlegable("Escenas", "sparkles", "Todo armado con un clic: cómo se grabó, el lugar, el fondo "
                                  "y algún sonido. Después podés ajustar lo que quieras.", True, con_interruptor=False)
        self.tarjeta_escenas = escenas
        self.galeria_escenas = GaleriaEscenas()
        self.galeria_escenas.elegida.connect(self._escena_elegida)
        self.galeria_escenas.borrarPedido.connect(lambda n: self.borrar_escena_propia(n))
        escenas.capa_cuerpo.addWidget(self.galeria_escenas)
        self.boton_guardar_escena = QPushButton(" Guardar como escena…")
        self.boton_guardar_escena.setObjectName("botonVerMas")
        self.boton_guardar_escena.setIcon(iconos.icono("bookmark-plus", 15))
        self.boton_guardar_escena.setCursor(Qt.PointingHandCursor)
        self.boton_guardar_escena.setToolTip("Guarda cómo se grabó, el lugar, el fondo y los sonidos (en proporción "
                                             "de la duración) como una escena tuya, para usarla con otras voces.")
        self.boton_guardar_escena.clicked.connect(lambda: self.guardar_como_escena())
        escenas.capa_cuerpo.addWidget(self.boton_guardar_escena)
        capa_panel.addWidget(escenas)

        destino = SeccionPlegable("¿Cómo se grabó?", "smartphone", "El micrófono, el control de volumen y la "
                                  "compresión del celular.", True, con_interruptor=False)
        self.tarjeta_destino = destino
        self.selector_destino = SelectorDestino()
        self.selector_destino.elegido.connect(self.elegir_destino)
        destino.capa_cuerpo.addWidget(self.selector_destino)
        self.control_cuanto = ControlCuanto()
        self.control_cuanto.valorCambiado.connect(lambda v: self.cambiar_voz("cuanto", v / 100.0))
        destino.capa_cuerpo.addWidget(self.control_cuanto)
        capa_panel.addWidget(destino)

        anti = SeccionPlegable("Bajarle lo de IA", "scan-face", "Una voz hecha con IA (o muy producida) suena "
                               "demasiado perfecta: pequeñas variaciones de volumen y de brillo, las «s» más suaves y "
                               "los extremos que un celular no capta. No cambia el tono.", True, con_interruptor=False)
        self.control_anti_ia = ControlDeslizante(
            "anti_ia", "Cuánto", 0, 100,
            "0 no toca la voz; 100 le saca todo lo demasiado perfecto (sin cambiar el tono ni el tiempo).")
        self.control_anti_ia.valorCambiado.connect(lambda _c, v: self.cambiar_voz("anti_ia", v / 100.0))
        anti.capa_cuerpo.addWidget(self.control_anti_ia)
        capa_panel.addWidget(anti)

        avanzado = SeccionPlegable("Avanzado", "sliders-horizontal", "El lugar y su eco, el ruido propio del "
                                   "micrófono y la compresión del destino.", False, con_interruptor=False)
        self.tarjeta_avanzado = avanzado
        fila_lugar = QHBoxLayout()
        etiqueta = QLabel("Lugar")
        etiqueta.setObjectName("etiquetaControl")
        self.combo_lugar = QComboBox()
        for lugar in vn.LUGARES:
            self.combo_lugar.addItem(pa.NOMBRES_LUGAR.get(lugar, lugar), lugar)
        self.combo_lugar.setToolTip("Dónde se grabó: cambia el eco (una sala chica, una oficina, un auto, la calle…)")
        self.combo_lugar.currentIndexChanged.connect(
            lambda _i: self.cambiar_voz("lugar", self.combo_lugar.currentData()))
        fila_lugar.addWidget(etiqueta)
        fila_lugar.addWidget(self.combo_lugar, 1)
        avanzado.capa_cuerpo.addLayout(fila_lugar)
        self.control_eco = ControlDeslizante("eco", "Eco del lugar", 0, 100,
                                             "Cuánto se oye el lugar (el eco). Con \"Ningún lugar\" no hace nada.")
        self.control_eco.valorCambiado.connect(lambda _c, v: self.cambiar_voz("eco", v / 100.0))
        avanzado.capa_cuerpo.addWidget(self.control_eco)
        self.control_ruido = ControlDeslizante("ruido_propio", "Ruido propio del micrófono", 0, 100,
                                               "El soplido muy bajo que tiene todo micrófono de celular.")
        self.control_ruido.valorCambiado.connect(lambda _c, v: self.cambiar_voz("ruido_propio", v / 100.0))
        avanzado.capa_cuerpo.addWidget(self.control_ruido)
        self.check_compresion = QCheckBox("Compresión del destino (Opus o AAC)")
        self.check_compresion.setToolTip("Codifica y decodifica de verdad como el destino (WhatsApp: Opus a 24 kbit/s; "
                                         "video: AAC). Si exportás para WhatsApp, no se comprime dos veces.")
        self.check_compresion.toggled.connect(lambda v: self.cambiar_voz("compresion", bool(v)))
        avanzado.capa_cuerpo.addWidget(self.check_compresion)
        capa_panel.addWidget(avanzado)
        capa_panel.addWidget(self._construir_tarjeta_atajos())
        capa_panel.addStretch(1)
        capa.addWidget(self._desplazable(panel), 1)

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
        self.pie_nombre = QLabel("Sin audio abierto")
        self.pie_nombre.setObjectName("pieNombre")
        self.pie_detalle = QLabel("Procesado local · sin IA generativa")
        self.pie_detalle.setObjectName("pieDetalle")
        for etiqueta in (self.pie_nombre, self.pie_detalle):
            etiqueta.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        datos.addWidget(self.pie_nombre)
        datos.addWidget(self.pie_detalle)
        fila.addLayout(datos, 1)
        self.boton_cerrar_audio = QPushButton()
        self.boton_cerrar_audio.setObjectName("botonCerrarVideo")
        self.boton_cerrar_audio.setIcon(iconos.icono("x", 16))
        self.boton_cerrar_audio.setIconSize(QSize(16, 16))
        self.boton_cerrar_audio.setFixedSize(30, 30)
        self.boton_cerrar_audio.setCursor(Qt.PointingHandCursor)
        self.boton_cerrar_audio.setToolTip("Cerrar el audio (el archivo no se toca). Se pierde lo que no exportaste.")
        self.boton_cerrar_audio.clicked.connect(lambda: self.cerrar_audio())
        self.boton_cerrar_audio.hide()
        fila.addWidget(self.boton_cerrar_audio, 0, Qt.AlignVCenter)
        capa.addWidget(pie)
        return lateral

    def _construir_tarjeta_atajos(self) -> QWidget:
        tarjeta = SeccionPlegable("Atajos del audio", "info", "Teclado del modo Audio", False, con_interruptor=False)
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(6)
        for fila, (tecla, texto) in enumerate((
            ("Espacio", "Reproducir o pausar"),
            ("← →", "Una décima atrás o adelante"),
            ("J  L", "Un segundo atrás o adelante"),
            ("I  O", "Recortar lo de antes o lo de después del cursor"),
            ("S", "Cortar en el cursor"),
            ("Supr", "Borrar el tramo elegido"),
            ("R", "Recuperar lo borrado más cerca del cursor"),
            ("M", "Silenciar o devolver el sonido del tramo"),
            ("Ctrl+Z  Ctrl+Y", "Deshacer o rehacer"),
            ("Ctrl+Shift+A", "Volver al modo de antes"),
        )):
            chip = QLabel(tecla)
            chip.setObjectName("valorControl")
            chip.setAlignment(Qt.AlignCenter)
            texto_l = QLabel(texto)
            texto_l.setObjectName("etiquetaControl")
            texto_l.setWordWrap(True)
            g.addWidget(chip, fila, 0)
            g.addWidget(texto_l, fila, 1)
        g.setColumnStretch(1, 1)
        tarjeta.capa_cuerpo.addLayout(g)
        return tarjeta

    def _construir_acciones(self) -> None:
        """Atajos del modo Audio. Van en este widget: solo andan mientras se ve."""
        for atajo, funcion in (
            (QKeySequence(Qt.Key_Space), self.alternar_reproduccion),
            (QKeySequence(Qt.Key_Right), lambda: self.mover_segundos(0.1)),
            (QKeySequence(Qt.Key_Left), lambda: self.mover_segundos(-0.1)),
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
            (QKeySequence.ZoomIn, lambda: self.onda.acercar()),
            (QKeySequence("Ctrl+="), lambda: self.onda.acercar()),
            (QKeySequence.ZoomOut, lambda: self.onda.alejar()),
            (QKeySequence("Ctrl+0"), lambda: self.onda.ajustar()),
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
        """Acomoda las filas de botones al ancho que hay (como el editor de video): primero se
        acortan los textos y después quedan solo los íconos (el nombre sigue en la ayuda)."""
        if not hasattr(self, "_fila_linea") or self.width() <= 0:
            return
        centro = self.width() - self._derecho.width() - 28
        for nivel in range(3):  # transporte (dentro de la tarjeta)
            for b in (self.boton_antes, self.boton_despues, self.boton_sonido):
                b.setText("" if nivel >= 1 else b.property("texto"))
            self.boton_antes.setVisible(nivel < 2)
            self.boton_despues.setVisible(nivel < 2)
            if ancho_pedido(self._fila_transporte) <= centro - 34:
                break
        for nivel in range(6):  # cabecera de la línea de tiempo
            self._resultado_corto = nivel >= 1
            self.titulo_linea.setVisible(nivel < 2)
            self._iconos_linea = max(0, nivel - 2)
            self._textos_linea(medir=True)
            if ancho_pedido(self._fila_linea) <= centro - 30:
                break
        self._textos_linea()

    # ============================================================ tiempo
    @property
    def ruta(self) -> Optional[str]:
        return self.proyecto.ruta if self.proyecto is not None else None

    @property
    def mapa(self) -> MapaTiempo:
        """Tiempo original ↔ tiempo del resultado, para la edición de ahora."""
        if self._mapa_de[0] is not self.edicion:
            mapa = MapaTiempo.de_edicion(self.edicion) if self.edicion is not None else MapaTiempo((), 0.0)
            self._mapa_de = (self.edicion, mapa)
        return self._mapa_de[1]

    @property
    def tiempo_resultado(self) -> float:
        return self.mapa.a_resultado(self.tiempo)

    def _visible(self, t: float) -> float:
        """``t`` si se oye; si cae en algo borrado o recortado, el comienzo de lo que sigue (la
        unión) o, después de todo, el final del último tramo."""
        mapa = self.mapa
        if not mapa.tramos or mapa.visible(t):
            return t
        for a, _b in mapa.tramos:
            if t < a:
                return a
        return mapa.tramos[-1][1]

    def ir_a(self, segundos: float, arrastrando: bool = False) -> None:
        """Lleva el cursor al instante ``segundos`` del original (si ahí no se oye nada, a la unión)."""
        if self.proyecto is None:
            return
        self.tiempo = self._visible(min(max(0.0, float(segundos)), self.duracion_original))
        self._mostrar_cursor()
        if self._reproduciendo:
            self._t_base, self._t_reloj = self.tiempo_resultado, time.monotonic()
            # El sonido vuelve desde acá cuando el cursor se queda quieto (arrastrando, ni suena).
            self.reproductor.detener()
            self._con_sonido = False
            self._gen_armado += 1  # un mezclador que se estaba armando para antes ya no sirve
            if not arrastrando:
                self._timer_sonido.start()
            else:
                self._timer_sonido.stop()

    def ir_a_resultado(self, segundos: float, arrastrando: bool = False) -> None:
        mapa = self.mapa
        self.ir_a(mapa.a_original(min(max(0.0, segundos), mapa.duracion)), arrastrando)

    def _tiempo_pedido(self, segundos: float, arrastrando: bool) -> None:
        self.ir_a(segundos, arrastrando)

    def mover_segundos(self, segundos: float) -> None:
        if self.proyecto is not None:
            self.ir_a_resultado(self.tiempo_resultado + segundos)

    def ir_al_inicio(self) -> None:
        if self.proyecto is not None:
            self.ir_a_resultado(0.0)

    def ir_al_final(self) -> None:
        if self.proyecto is not None:
            self.pausar()
            self.ir_a_resultado(self.mapa.duracion)

    def _mostrar_cursor(self, seguir: bool = False) -> None:
        t = self.tiempo
        self.linea.establecer_tiempo(t)
        self.onda.pista.establecer_tiempo(t)
        self.pista_fondo.establecer_tiempo(t)
        self.pista_sonidos.establecer_tiempo(t)
        if seguir:
            self.onda.seguir(t)
        self._actualizar_tiempo()

    def _actualizar_tiempo(self) -> None:
        if self.proyecto is None:
            self.etiqueta_tiempo.setText("0:00,00 / 0:00,00")
            return
        mapa = self.mapa
        self.etiqueta_tiempo.setText(f"{formato_tiempo(mapa.a_resultado(self.tiempo))} / {formato_tiempo(mapa.duracion)}")

    # ============================================================ abrir y cerrar
    def elegir_archivo(self) -> None:
        """Abrir (Ctrl+O): con la ventana, su diálogo (cada cosa va a su modo)."""
        if self._ventana is not None:
            self._ventana.elegir_archivo()
            return
        inicio = str(Path(self.ruta).parent) if self.ruta else str(Path.home() / "Music")
        ruta, _ = QFileDialog.getOpenFileName(self, "Abrir un audio", inicio, FILTRO_ABRIR_AUDIO)
        if ruta:
            self.abrir(ruta)

    def tiene_cambios(self) -> bool:
        """Si el audio abierto tiene algo que no está en el archivo (se pierde al cerrarlo)."""
        if self.proyecto is None or not self._historial:
            return False
        _d, p0, e0 = self._historial[0]
        return (self.proyecto, self.edicion) != (p0, e0)

    def es_el_abierto(self, ruta: str) -> bool:
        if self.ruta is None:
            return False
        try:
            return os.path.samefile(ruta, self.ruta)
        except OSError:
            return os.path.normcase(os.path.abspath(ruta)) == os.path.normcase(os.path.abspath(self.ruta))

    def confirmar_reemplazo(self, ruta: str) -> bool:
        """Antes de abrir ``ruta``: si el audio abierto tiene cambios, pregunta si se reemplaza."""
        if self.es_el_abierto(ruta) or not self.tiene_cambios():
            return True
        respuesta = QMessageBox.question(
            self, "Abrir otro audio",
            f"{Path(self.ruta).name} tiene cambios que no exportaste: si abrís {Path(ruta).name}, se pierden.\n\n"
            "¿Abrirlo igual?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return respuesta == QMessageBox.Yes

    def abrir(self, ruta: str, confirmar: bool = True) -> bool:
        """Abre la voz de ``ruta`` en un proyecto nuevo. Si no se puede (no tiene sonido, no se
        lee), avisa y deja todo como estaba. False si no se abrió."""
        ruta = str(ruta)
        if self.es_el_abierto(ruta):
            return True
        if confirmar and not self.confirmar_reemplazo(ruta):
            return False
        try:
            proyecto = abrir_voz(ruta)
        except ValueError as error:
            self.etiqueta_estado.setText(str(error))
            QMessageBox.warning(self, "No se pudo abrir", str(error))
            return False
        self.cargar_proyecto(proyecto)
        return True

    def abrir_desde_video(self, ruta_wav: str, ruta_video: str, confirmar: bool = True) -> bool:
        """"Editar el sonido en el modo Audio" (desde Video): abre ``ruta_wav`` (el sonido completo
        del video, sin sus cortes) como una voz con ``video_origen = ruta_video``. Se ve la franja
        "Sonido del video X · Volver al video con este sonido" y no se puede cortar ni borrar tramos
        (si no, el sonido se desalinea con la imagen): eso se hace en el video. Lo demás sí.
        Si el audio abierto tiene cambios, pregunta antes (``confirmar``). False si no se abrió."""
        if confirmar and not self.confirmar_reemplazo(ruta_wav):
            return False
        try:
            proyecto = abrir_voz(ruta_wav).con(video_origen=str(ruta_video))
        except ValueError as error:
            self.etiqueta_estado.setText(str(error))
            QMessageBox.warning(self, "No se pudo abrir", str(error))
            return False
        self.cargar_proyecto(proyecto)
        self.etiqueta_estado.setText(f"Sonido de {Path(ruta_video).name}: los cortes se hacen en el video. Cuando "
                                     "termines, tocá «Volver al video con este sonido».")
        return True

    @property
    def cortes_bloqueados(self) -> bool:
        """Si el sonido es de un video (``video_origen``): ahí no se corta ni se borra (se hace en el video)."""
        return self.proyecto is not None and self.proyecto.video_origen is not None

    def _sin_cortes(self) -> bool:
        """True (y avisa) si no se puede cortar porque el sonido es de un video."""
        if self.cortes_bloqueados:
            self.etiqueta_estado.setText("Este sonido es de un video: para cortar, hacelo en el video (si no, se "
                                         "desalinea con la imagen).")
            return True
        return False

    def cargar_proyecto(self, proyecto: pa.ProyectoAudio, historial: Optional[list] = None, pos: int = 0,
                        tiempo: float = 0.0) -> None:
        """Pone un proyecto: recién abierto (``abrir_voz``) o de la sesión, con su historial
        [(descripción, proyecto, edición)] y la posición en él."""
        self.pausar()
        info = ma.info_medio(proyecto.ruta)
        duracion = float(info.duracion)
        if not historial:
            historial = [("Inicio", proyecto, edicion_de_tramos(proyecto.tramos, duracion))]
            pos = 0
        self.info, self.duracion_original = info, duracion
        self._historial = list(historial)[-MAX_HISTORIAL:]
        self._pos = max(0, min(int(pos) - (len(historial) - len(self._historial)), len(self._historial) - 1))
        self._ultimo_control, self._indice_gesto = ("", 0.0), -1
        self._picos.clear()
        self._midiendo.clear()
        self._faltan_mezcla = ()
        self.proyecto = self.edicion = None
        self.tiempo = max(0.0, min(float(tiempo or 0.0), duracion))
        self.linea.seleccionar(-1)
        self.pista_sonidos.seleccionar(-1)
        self.linea.establecer_forma(None)
        self.onda.pista.cargando(duracion)
        self.onda.ajustar()
        self.cargador_onda.cargar(proyecto.ruta)
        self.vista.setCurrentWidget(self.onda)
        _d, p, e = self._historial[self._pos]
        self._fijar_estado(p, e)
        self._actualizar_info()
        self.etiqueta_estado.setText(f"{Path(proyecto.ruta).name}  ·  {formato_tiempo(duracion)}")
        self.compactar()
        self.audioCambiado.emit()

    def cerrar_audio(self, confirmar: bool = True) -> bool:
        """Cierra el audio abierto (el archivo no se toca) y vuelve a la invitación."""
        if self.proyecto is None:
            return True
        if self.exportando:
            QMessageBox.information(self, "Exportación en curso", "Se está exportando este audio. Esperá a que "
                                    "termine o cancelalo para cerrarlo.")
            return False
        if confirmar and self.tiene_cambios():
            respuesta = QMessageBox.question(
                self, "Cerrar el audio", f"{Path(self.ruta).name} tiene cambios que no exportaste y se pierden.\n\n"
                "¿Cerrarlo igual?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if respuesta != QMessageBox.Yes:
                return False
        self.pausar()
        self._parar_escucha()
        self.cargador_onda.cancelar()
        self.proyecto = self.edicion = self.info = None
        self.duracion_original = 0.0
        self._historial, self._pos = [], -1
        self._ultimo_control, self._indice_gesto = ("", 0.0), -1
        self._picos.clear()
        self._midiendo.clear()
        self.tiempo = 0.0
        self.linea.establecer_edicion(None)
        self.linea.establecer_forma(None)
        self.onda.pista.vaciar()
        self.vista.setCurrentWidget(self.invitacion)
        self._actualizar_vistas()
        self._actualizar_info()
        self.etiqueta_estado.setText(SIN_AUDIO)
        self.audioCambiado.emit()
        self.estadoCambiado.emit()
        return True

    def _actualizar_info(self) -> None:
        info = self.info
        if info is None or self.proyecto is None:
            self.pie_avatar.setText("—")
            self.pie_nombre.setText("Sin audio abierto")
            self.pie_nombre.setToolTip("")
            self.pie_detalle.setText("Procesado local · sin IA generativa")
            self.boton_cerrar_audio.hide()
            return
        nombre = Path(self.proyecto.ruta).name
        self.pie_avatar.setText((Path(nombre).stem[:1] or "A").upper())
        self.pie_nombre.setText(self.pie_nombre.fontMetrics().elidedText(nombre, Qt.ElideMiddle, 220))
        self.pie_nombre.setToolTip(self.proyecto.ruta)
        canales = {1: "mono", 2: "estéreo"}.get(int(info.canales_audio or 0), f"{info.canales_audio} canales")
        partes = [formato_tiempo(info.duracion, decimas=False)]
        if info.frecuencia_audio:
            partes.append(f"{info.frecuencia_audio / 1000:g} kHz".replace(".", ","))
        partes.append(canales)
        if info.codec_audio:
            partes.append(info.codec_audio.upper())
        self.pie_detalle.setText(" · ".join(partes))
        self.boton_cerrar_audio.show()
        self.boton_cerrar_audio.setEnabled(not self.exportando)

    # ============================================================ estado e historial
    def _fijar_estado(self, proyecto: pa.ProyectoAudio, edicion: EdicionVideo) -> None:
        """Pone un estado (un paso nuevo, deshacer o rehacer) en todo: pistas, paneles y, si está
        sonando, lo que se escucha."""
        antes = self.proyecto
        cambio_tramos = antes is None or antes.ruta != proyecto.ruta or antes.tramos != proyecto.tramos
        self.proyecto, self.edicion = proyecto, edicion
        self.linea.establecer_edicion(edicion)
        if cambio_tramos:
            self.tiempo = self._visible(self.tiempo)
        claves = {c.clave for c in proyecto.fondos + proyecto.sonidos}
        self._faltan_mezcla = tuple(c for c in self._faltan_mezcla if c in claves)  # lo que ya no se usa, no falta
        self._actualizar_vistas()
        # Primero se preparan los sonidos nuevos (en el hilo de lo que suena): así armar o cambiar el
        # mezclador, que va después en ese mismo hilo, ya los encuentra hechos.
        self._precalentar()
        if self._reproduciendo:
            if cambio_tramos:
                # El reloj va en el tiempo del resultado, que cambió: sigue desde el cursor.
                self._t_base, self._t_reloj = self.tiempo_resultado, time.monotonic()
                self._iniciar_sonido()
            elif self._con_sonido and antes is not None and proyecto != antes:
                self._cambiar_lo_que_suena()
        self.estadoCambiado.emit()

    def _editar(self, proyecto: Optional[pa.ProyectoAudio] = None, edicion: Optional[EdicionVideo] = None,
                descripcion: str = "", control: str = "") -> bool:
        """Un paso nuevo de deshacer con este proyecto y esta edición (lo que no viene, queda).

        ``control``: el control que cambió. Si es el mismo que el del paso anterior y pasó poco
        tiempo (``JUNTAR``), se junta con ese paso. Si así vuelve a como estaba antes del gesto,
        el paso se saca y el gesto termina."""
        if self.proyecto is None:
            return False
        edicion = edicion if edicion is not None else self.edicion
        proyecto = proyecto if proyecto is not None else self.proyecto
        tramos = tuple(edicion.tramos_conservados())
        if not _mismos_tramos(proyecto.tramos, tramos):
            proyecto = proyecto.con(tramos=tramos)
        proyecto = self._limitar_fundidos(proyecto, edicion)
        if proyecto == self.proyecto and edicion == self.edicion:
            return False
        ahora = time.monotonic()
        anterior, momento = self._ultimo_control
        ultimo = len(self._historial) - 1
        juntar = (bool(control) and control == anterior and ahora - momento < JUNTAR and self._pos == ultimo
                  and self._indice_gesto == ultimo and ultimo > 0)
        terminado = False
        paso = descripcion.split(". ")[0].rstrip(".") if descripcion else ""  # en el historial, la primera oración
        if juntar:
            _d, p_antes, e_antes = self._historial[ultimo - 1]
            if (p_antes, e_antes) == (proyecto, edicion):
                # Volvió a como estaba antes de empezar a moverlo: no queda un paso vacío, y el gesto
                # termina (lo próximo no se junta con el paso de antes, que es de otra cosa).
                del self._historial[ultimo]
                self._pos = ultimo - 1
                terminado = True
            else:
                self._historial[ultimo] = (paso or self._historial[ultimo][0], proyecto, edicion)
        else:
            del self._historial[self._pos + 1:]
            self._historial.append((paso or "Cambio", proyecto, edicion))
            del self._historial[:-MAX_HISTORIAL]
            self._pos = len(self._historial) - 1
        if control and not terminado:
            self._ultimo_control, self._indice_gesto = (control, ahora), self._pos
        else:
            self._ultimo_control, self._indice_gesto = ("", 0.0), -1
        self._fijar_estado(proyecto, edicion)
        if descripcion:
            self.etiqueta_estado.setText(descripcion)
        return True

    def _limitar_fundidos(self, p: pa.ProyectoAudio, edicion: EdicionVideo) -> pa.ProyectoAudio:
        """Los fundidos de entrada y de salida, como mucho la mitad de la duración final."""
        mitad = max(0.0, edicion.duracion_resultante() / 2)
        s = p.sonido
        if s.fundido_entrada <= mitad and s.fundido_salida <= mitad:
            return p
        return p.con(sonido=s.con(fundido_entrada=min(s.fundido_entrada, mitad),
                                  fundido_salida=min(s.fundido_salida, mitad)))

    @property
    def historial(self) -> list[tuple[str, pa.ProyectoAudio, EdicionVideo]]:
        return list(self._historial)

    @property
    def posicion_historial(self) -> int:
        return self._pos

    def deshacer(self) -> None:
        if self.proyecto is not None and self._pos > 0:
            descripcion = self._historial[self._pos][0]
            self._pos -= 1
            self._ultimo_control, self._indice_gesto = ("", 0.0), -1
            self._restaurar()
            self.etiqueta_estado.setText(f"Deshecho: {descripcion}.")

    def rehacer(self) -> None:
        if self.proyecto is not None and self._pos < len(self._historial) - 1:
            self._pos += 1
            self._ultimo_control, self._indice_gesto = ("", 0.0), -1
            self._restaurar()
            self.etiqueta_estado.setText(f"Rehecho: {self._historial[self._pos][0]}.")

    def _restaurar(self) -> None:
        """Pone el paso actual del historial. El tramo elegido sigue elegido solo si en ese paso
        está el mismo tramo (al deshacer un corte, los índices se corren)."""
        elegido = None
        i = self.linea.seleccion
        if self.edicion is not None and 0 <= i < len(self.edicion.segmentos):
            s = self.edicion.segmentos[i]
            elegido = (s.inicio, s.fin)
        _d, p, e = self._historial[self._pos]
        self._fijar_estado(p, e)
        nuevo = -1
        if elegido is not None:
            nuevo = next((k for k, s in enumerate(e.segmentos)
                          if abs(s.inicio - elegido[0]) < 1e-9 and abs(s.fin - elegido[1]) < 1e-9), -1)
        self.linea.seleccionar(nuevo)
        self._seleccion_en_onda()

    # ============================================================ cortes
    def _tramo_objetivo(self) -> int:
        return self.linea.seleccion if self.linea.seleccion >= 0 else self.edicion.indice_en(self.tiempo)

    def _rango_visto(self, inicio: float, fin: float) -> str:
        rangos = self.mapa.rangos_resultado(inicio, fin)
        a, b = (rangos[0][0], rangos[-1][1]) if rangos else (self.mapa.a_resultado(inicio),) * 2
        return f"de {formato_tiempo(a)} a {formato_tiempo(b)}"

    def marcar_entrada(self) -> None:
        if self.edicion is None or self._sin_cortes():
            return
        quita = self.tiempo_resultado
        if self._editar(edicion=self.edicion.con_entrada(self.tiempo),
                        descripcion=f"Principio recortado ({formato_duracion(quita)}). Para recuperarlo, tocá la "
                                    "marquita del principio (o Ctrl+Z)."):
            self.linea.seleccionar(-1)

    def marcar_salida(self) -> None:
        if self.edicion is None or self._sin_cortes():
            return
        quita = max(0.0, self.mapa.duracion - self.tiempo_resultado - self.edicion.cuadro)
        if self._editar(edicion=self.edicion.con_salida(self.tiempo),
                        descripcion=f"Final recortado ({formato_duracion(quita)}). Para recuperarlo, tocá la marquita "
                                    "del final (o Ctrl+Z)."):
            self.linea.seleccionar(-1)

    def _limites_pedidos(self, entrada: float, salida: Optional[float]) -> None:
        if self.edicion is None or self._sin_cortes():
            return
        antes = self.mapa.duracion
        nueva = self.edicion.con_limites(entrada, salida)
        if not nueva.tramos_conservados():  # como Borrar tramo: tiene que quedar algo
            self.etiqueta_estado.setText("Es lo único que queda: no se puede borrar todo el audio.")
            return
        quita = max(0.0, antes - nueva.duracion_resultante())
        self._editar(edicion=nueva, descripcion=f"Recortado ({formato_duracion(quita)}). Para recuperarlo, tocá su "
                                                "marquita (o Ctrl+Z).")

    def cortar(self) -> None:
        if self.edicion is None or self._sin_cortes():
            return
        if not self._editar(edicion=self.edicion.cortar(self.tiempo),
                            descripcion=f"Corte en {formato_tiempo(self.tiempo_resultado)}."):
            self.etiqueta_estado.setText("Ahí ya hay un corte (o es el principio o el final).")
            return
        self.linea.seleccionar(self.edicion.indice_en(self.tiempo))

    def borrar_tramo(self) -> None:
        if self.edicion is None or self._sin_cortes():
            return
        i = self._tramo_objetivo()
        s = self.edicion.segmentos[i]
        if s.borrado:
            return
        nueva = self.edicion.con_borrado(i)
        if not nueva.tramos_conservados():
            self.etiqueta_estado.setText("Es lo único que queda: no se puede borrar todo el audio.")
            return
        largo = sum(b - a for a, b in self.mapa.rangos_resultado(s.inicio, s.fin))
        if self._editar(edicion=nueva, descripcion=f"Tramo borrado ({formato_duracion(largo)}). Para recuperarlo, "
                                                   "tocá la marquita rosa de la unión (o Ctrl+Z)."):
            self.linea.seleccionar(-1)

    def recuperar(self, hueco: Optional[Hueco] = None) -> bool:
        """"Recuperar lo borrado" en una unión. Sin ``hueco`` (R), el más cercano al cursor."""
        if self.edicion is None or self._sin_cortes():
            return False
        huecos = self.mapa.huecos()
        if hueco is None:
            if not huecos:
                self.etiqueta_estado.setText("No hay nada borrado para recuperar.")
                return False
            r = self.tiempo_resultado
            hueco = min(huecos, key=lambda h: abs(h.en - r))
        if not self._editar(edicion=recuperar_hueco(self.edicion, hueco),
                            descripcion=f"Se recuperó lo borrado ({formato_duracion(hueco.duracion)})."):
            return False
        self.linea.seleccionar(-1)
        self.ir_a(hueco.inicio)
        return True

    def silenciar_tramo(self) -> None:
        """Silencia el tramo elegido (o el del cursor); si ya está en silencio, le devuelve el sonido."""
        if self.edicion is None:
            return
        i = self._tramo_objetivo()
        s = self.edicion.segmentos[i]
        if s.borrado:
            return
        sonido = self.proyecto.sonido
        rango = self._rango_visto(s.inicio, s.fin)
        if sonido.silenciado(s.inicio, s.fin):
            nuevo, texto = sonido.con_sonido(s.inicio, s.fin), f"Sonido devuelto {rango}."
        else:
            nuevo, texto = sonido.con_silencio(s.inicio, s.fin), f"Silenciado {rango} (el fondo sigue)."
        if self._editar(self.proyecto.con(sonido=nuevo), descripcion=texto):
            self.linea.seleccionar(i)

    def _al_cambiar_seleccion(self) -> None:
        self._seleccion_en_onda()
        self._textos_linea()

    def _seleccion_en_onda(self) -> None:
        i = self.linea.seleccion
        if self.edicion is None or not 0 <= i < len(self.edicion.segmentos):
            self.onda.pista.establecer_seleccion(None)
        else:
            s = self.edicion.segmentos[i]
            self.onda.pista.establecer_seleccion((s.inicio, s.fin))

    def _pista_presionada(self, t: float) -> None:
        if self.edicion is not None:
            self.linea.seleccionar(self.edicion.indice_en(self._visible(t)))

    # ============================================================ que suene real
    def _escena_elegida(self, clave: str) -> None:
        propia = clave not in pa.ESCENAS
        self.aplicar_escena(clave, propia=propia)

    def aplicar_escena(self, clave: str, propia: bool = False) -> bool:
        """Aplica una escena de la app (por su clave) o una propia (por su nombre): cómo se grabó,
        el fondo y los sonidos sugeridos. Entra al historial."""
        if self.proyecto is None:
            self.etiqueta_estado.setText("Abrí un audio para aplicarle una escena.")
            return False
        escena = (pa.escenas_propias() if propia else pa.ESCENAS).get(clave)
        if escena is None:
            self.etiqueta_estado.setText("Esa escena ya no está.")
            self._refrescar_escenas()
            return False
        nuevo = pa.aplicar_escena(self.proyecto, escena)
        # Una propia puede ser igual a una de la app: se marca la que se eligió.
        self._escena_preferida = (clave, propia)
        if not self._editar(nuevo, descripcion=f"Escena: {escena.nombre}."):
            self._marcar_escena()  # ya estaba así: igual se marca la tarjeta que se tocó
            self.etiqueta_estado.setText(f"Ya está así: {escena.nombre}.")
            return False
        return True

    def guardar_como_escena(self, nombre: Optional[str] = None) -> bool:
        """"Guardar como escena…": la voz, el fondo y los sonidos del proyecto, como escena propia."""
        if self.proyecto is None:
            return False
        if nombre is None:
            sugerido = pa.describir(self.proyecto.voz, self.proyecto.fondos, ())[:60]
            nombre, ok = QInputDialog.getText(self, "Guardar como escena", "Nombre de la escena:", QLineEdit.Normal,
                                              sugerido)
            if not ok:
                return False
        nombre = " ".join(str(nombre or "").split())
        if not nombre:
            return False
        if nombre in pa.escenas_propias():
            respuesta = QMessageBox.question(self, "Guardar como escena", f"Ya tenés una escena «{nombre}». "
                                             "¿Reemplazarla?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if respuesta != QMessageBox.Yes:
                return False
        try:
            pa.guardar_escena(nombre, self.proyecto)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "No se pudo guardar la escena", str(error))
            return False
        self._escena_preferida = (nombre, True)  # recién guardada: se marca ella, no una de la app igual
        self._refrescar_escenas()
        self.etiqueta_estado.setText(f"Escena guardada: {nombre}. Está en «Tus escenas».")
        return True

    def borrar_escena_propia(self, nombre: str, confirmar: bool = True) -> bool:
        if confirmar:
            respuesta = QMessageBox.question(self, "Borrar la escena", f"¿Borrar tu escena «{nombre}»?",
                                             QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if respuesta != QMessageBox.Yes:
                return False
        try:
            pa.borrar_escena(nombre)
        except OSError as error:
            QMessageBox.warning(self, "No se pudo borrar la escena", str(error))
            return False
        self._refrescar_escenas()
        self.etiqueta_estado.setText(f"Escena borrada: {nombre}.")
        return True

    def _refrescar_escenas(self) -> None:
        self._propias = pa.escenas_propias()   # se lee del disco solo acá (al guardar, borrar o empezar)
        self.galeria_escenas.establecer(list(pa.ESCENAS.values()), list(self._propias.values()))
        self._marcar_escena()

    def _marcar_escena(self) -> None:
        p = self.proyecto
        if p is None:
            self.galeria_escenas.seleccionar(None)
            return
        preferida = getattr(self, "_escena_preferida", None)  # la última elegida o guardada, si sigue igual
        if preferida is not None:
            clave, propia = preferida
            e = (getattr(self, "_propias", {}) if propia else pa.ESCENAS).get(clave)
            if e is not None and e.voz == p.voz and e.fondos == p.fondos:
                self.galeria_escenas.seleccionar(clave, propia=propia)
                return
        for clave, e in pa.ESCENAS.items():
            if e.voz == p.voz and e.fondos == p.fondos:
                self.galeria_escenas.seleccionar(clave)
                return
        for nombre, e in getattr(self, "_propias", {}).items():
            if e.voz == p.voz and e.fondos == p.fondos:
                self.galeria_escenas.seleccionar(nombre, propia=True)
                return
        self.galeria_escenas.seleccionar(None)

    def elegir_destino(self, destino: str) -> None:
        nombre = pa.NOMBRES_DESTINO.get(destino, destino)
        self.cambiar_voz("destino", destino, f"Cómo se grabó: {nombre}.")

    def cambiar_voz(self, campo: str, valor, descripcion: str = "") -> bool:
        """Un cambio de ``AjustesVoz`` (cuánto, anti IA, lugar, eco, ruido, compresión, tapa…)."""
        if self.proyecto is None:
            self._actualizar_vistas()
            return False
        voz = self.proyecto.voz.con(**{campo: valor})
        if not descripcion:
            nombres = {"cuanto": "Cuánto", "anti_ia": "Bajarle lo de IA", "eco": "Eco del lugar",
                       "ruido_propio": "Ruido propio", "tapa": "Que tape la voz"}
            if campo in nombres:
                descripcion = f"{nombres[campo]}: {round(getattr(voz, campo) * 100)}"
            elif campo == "lugar":
                descripcion = f"Lugar: {pa.NOMBRES_LUGAR.get(voz.lugar, voz.lugar)}."
            elif campo == "compresion":
                descripcion = "Con la compresión del destino." if voz.compresion else "Sin la compresión del destino."
        control = campo if campo in ("cuanto", "anti_ia", "eco", "ruido_propio", "tapa") else ""
        return self._editar(self.proyecto.con(voz=voz), descripcion=descripcion, control=control)

    # ============================================================ fondo continuo
    def agregar_fondo(self, origen: str, clave: str) -> bool:
        """Suma una capa al fondo (hasta ``CAPAS_MAX``). False si ya hay 3 o no hay audio."""
        if self.proyecto is None:
            self.etiqueta_estado.setText("Abrí un audio para sumarle un fondo.")
            return False
        fondos = self.proyecto.fondos
        if len(fondos) >= pa.CAPAS_MAX:
            self.etiqueta_estado.setText(f"Ya hay {pa.CAPAS_MAX} capas: quitá una para agregar otra.")
            return False
        semilla = semilla_libre(fondos, origen, clave)
        capa = pa.FondoProyecto(origen, clave, 0.5, 0.5, semilla)
        _icono, nombre, _i = nombre_fondo(capa)
        ok = self._editar(self.proyecto.con(fondos=fondos + (capa,)), descripcion=f"Fondo: se sumó {nombre}.")
        if ok and len(self.proyecto.fondos) >= pa.CAPAS_MAX:
            self.boton_agregar_fondo.setChecked(False)
        return ok

    def quitar_fondo(self, indice: int) -> bool:
        fondos = list(self.proyecto.fondos) if self.proyecto is not None else []
        if not 0 <= indice < len(fondos):
            return False
        capa = fondos.pop(indice)
        return self._editar(self.proyecto.con(fondos=tuple(fondos)), descripcion=f"Fondo: se quitó "
                                                                                  f"{nombre_fondo(capa)[1]}.")

    def cambiar_fondo(self, indice: int, control: str, valor: int) -> bool:
        fondos = list(self.proyecto.fondos) if self.proyecto is not None else []
        if not 0 <= indice < len(fondos):
            return False
        fondos[indice] = fondos[indice].con(**{control: valor / 100.0})
        nombre = nombre_fondo(fondos[indice])[1]
        texto = "volumen" if control == "volumen" else "intensidad"
        return self._editar(self.proyecto.con(fondos=tuple(fondos)), descripcion=f"{nombre}: {texto} {valor}",
                            control=f"fondo_{indice}_{control}")

    def escuchar_fondo(self, fondo: pa.FondoProyecto) -> None:
        """"Escuchar 3 s" de un fondo, solo y con su volumen (en otro hilo, con un generador nuevo)."""
        self._escuchar(lambda: muestra_fondo(fondo), nombre_fondo(fondo)[1])

    def escuchar_mi_sonido(self, nombre: str) -> None:
        self._escuchar(lambda: muestra_archivo(nombre), Path(nombre).stem)

    def _escuchar(self, preparar, nombre: str) -> None:
        self.pausar()
        self.reproductor.detener()
        if self.reproductor.silenciado:
            self.etiqueta_estado.setText("La vista previa está silenciada (botón Sonido).")
            return
        if not self.reproductor.disponible:
            self.etiqueta_estado.setText(f"Sin salida de sonido: {self.reproductor.motivo or 'no se puede escuchar.'}")
            return
        self._generacion_escucha += 1
        generacion = self._generacion_escucha
        self.etiqueta_estado.setText(f"Escuchando {nombre} (3 segundos)…")
        self._pool_trabajo.start(Tarea("escuchar", generacion, lambda _c: (nombre, preparar()), self._senales))

    def _parar_escucha(self) -> None:
        self._generacion_escucha += 1
        if isinstance(self.reproductor.lector, LectorArreglo):
            self.reproductor.detener()

    # ============================================================ sonidos sueltos
    def _armar_menu_sonidos(self) -> None:
        menu = self.menu_sonidos
        menu.clear()
        titulo = menu.addAction("Generados por la app")
        titulo.setEnabled(False)
        for clave, info in am.SONIDOS.items():
            accion = menu.addAction(iconos.icono(info.icono, 16), f"{info.nombre}  ·  {info.duracion:g} s".replace(".", ","))
            accion.setToolTip(info.descripcion)
            accion.triggered.connect(lambda _c=False, k=clave: self.agregar_sonido("generado", k))
        menu.addSeparator()
        mios = pa.mis_sonidos()
        titulo = menu.addAction("De Mis sonidos" if mios else "Mis sonidos: todavía no agregaste ninguno")
        titulo.setEnabled(False)
        for ruta in mios:
            accion = menu.addAction(iconos.icono("music", 16), ruta.stem)
            accion.triggered.connect(lambda _c=False, n=ruta.name: self.agregar_sonido("archivo", n))
        menu.setEnabled(self.proyecto is not None)

    def agregar_sonido(self, origen: str, clave: str, ancla: Optional[float] = None) -> bool:
        """Suma un sonido suelto que empieza en el cursor (o en ``ancla``, tiempo original)."""
        if self.proyecto is None:
            self.etiqueta_estado.setText("Abrí un audio para sumarle sonidos.")
            return False
        ancla = self.tiempo if ancla is None else float(ancla)
        semilla = semilla_libre(self.proyecto.sonidos, origen, clave)
        sonido = pa.SonidoSuelto(origen, clave, ancla, 0.7, semilla)
        _icono, nombre = nombre_sonido(sonido)
        ok = self._editar(self.proyecto.con(sonidos=self.proyecto.sonidos + (sonido,)),
                          descripcion=f"Sonido: {nombre} en {formato_tiempo(self.mapa.a_resultado(ancla))}.")
        if ok:
            self.pista_sonidos.seleccionar(len(self.proyecto.sonidos) - 1)
        return ok

    def borrar_sonido(self, indice: int) -> bool:
        sonidos = list(self.proyecto.sonidos) if self.proyecto is not None else []
        if not 0 <= indice < len(sonidos):
            return False
        s = sonidos.pop(indice)
        self.pista_sonidos.seleccionar(-1)
        return self._editar(self.proyecto.con(sonidos=tuple(sonidos)), descripcion=f"Sonido borrado: "
                                                                                    f"{nombre_sonido(s)[1]}.")

    def cambiar_sonido(self, indice: int, control: str, valor: int) -> bool:
        sonidos = list(self.proyecto.sonidos) if self.proyecto is not None else []
        if not 0 <= indice < len(sonidos):
            return False
        sonidos[indice] = sonidos[indice].con(**{control: valor / 100.0})
        return self._editar(self.proyecto.con(sonidos=tuple(sonidos)),
                            descripcion=f"{nombre_sonido(sonidos[indice])[1]}: volumen {valor}",
                            control=f"sonido_{indice}_{control}")

    def mover_sonido(self, indice: int, ancla: float) -> bool:
        """Lo que pide la pista Sonidos al soltar un bloque: el ancla nueva (tiempo original)."""
        sonidos = list(self.proyecto.sonidos) if self.proyecto is not None else []
        if not 0 <= indice < len(sonidos):
            return False
        sonidos[indice] = sonidos[indice].con(ancla=max(0.0, float(ancla)))
        r = self.mapa.a_resultado(sonidos[indice].ancla)
        ok = self._editar(self.proyecto.con(sonidos=tuple(sonidos)),
                          descripcion=f"{nombre_sonido(sonidos[indice])[1]} movido a {formato_tiempo(r)}.")
        self.pista_sonidos.seleccionar(indice)
        return ok

    def ir_al_sonido(self, indice: int) -> None:
        if self.proyecto is not None and 0 <= indice < len(self.proyecto.sonidos):
            self.ir_a(self.proyecto.sonidos[indice].ancla)
            self.pista_sonidos.seleccionar(indice)

    def _sonido_elegido_en_pista(self, indice: int) -> None:
        if indice >= 0 and self.proyecto is not None and indice < len(self.proyecto.sonidos):
            nombre = nombre_sonido(self.proyecto.sonidos[indice])[1]
            self.etiqueta_estado.setText(f"{nombre}: arrastralo para moverlo; su volumen está a la derecha.")

    def _largo_sonido(self, s: pa.SonidoSuelto) -> float:
        clave = (s.origen, s.clave, s.semilla)
        if clave in self._largos:
            return self._largos[clave]
        if s.origen == "generado" and s.clave in am.SONIDOS:
            return am.SONIDOS[s.clave].duracion
        return 2.0

    def _precalentar(self) -> None:
        """Prepara en el hilo de lo que suena los sonidos nuevos del proyecto (genera los sueltos y lee
        los de Mis sonidos), antes de armar o cambiar el mezclador en ese mismo hilo. Así se sabe
        también cuánto dura cada sonido suelto (para dibujarlo)."""
        p = self.proyecto
        if p is None:
            return
        claves = [(s.origen, s.clave, s.semilla) for s in p.sonidos] + [
            ("archivo_fondo", f.clave, 0) for f in p.fondos if f.origen == "archivo"]
        pendientes = [k for k in dict.fromkeys(claves) if k not in self._largos and k not in self._calentando]
        if not pendientes:
            return
        self._calentando.update(pendientes)

        def trabajo(_c):
            largos = {}
            for origen, clave, semilla in pendientes:
                try:
                    if origen == "generado":
                        datos = am.generar_sonido(clave, semilla) if clave in am.SONIDOS else None
                    else:
                        datos = pa.cargar_sonido(clave)
                except Exception:
                    datos = None
                if datos is not None:
                    largos[(origen, clave, semilla)] = len(datos) / pa.FRECUENCIA
            return pendientes, largos

        self._pool_sonido.start(Tarea("largos", 0, trabajo, self._senales))

    # ============================================================ Mis sonidos
    def _refrescar_mis_sonidos(self) -> None:
        mios = pa.mis_sonidos()
        for fila in self.filas_mis_sonidos:
            self.caja_mis_sonidos.removeWidget(fila)
            fila.hide()  # que no quede a la vista hasta que se borre
            fila.deleteLater()
        self.filas_mis_sonidos = []
        for ruta in mios:
            try:
                tam = ruta.stat().st_size
            except OSError:
                tam = 0
            detalle = f"{ruta.suffix.lstrip('.').upper()} · " + (f"{tam / 1e6:.1f} MB".replace(".", ",") if tam >= 1e5
                                                                 else f"{max(1, round(tam / 1e3))} KB")
            fila = FilaMiSonido(ruta.name, detalle)
            fila.escucharPedido.connect(self.escuchar_mi_sonido)
            fila.renombrarPedido.connect(lambda n: self.renombrar_mi_sonido(n))
            fila.borrarPedido.connect(lambda n: self.borrar_mi_sonido(n))
            self.caja_mis_sonidos.addWidget(fila)
            self.filas_mis_sonidos.append(fila)
        carpeta = pa.carpeta_sonidos()
        self.nota_mis_sonidos.setText("Todavía no agregaste ninguno. Sirven de fondo o de sonido suelto (gente "
                                      "hablando, pájaros, un perro…)." if not mios else
                                      f"{len(mios)} archivo{'s' if len(mios) != 1 else ''}, guardados en la app.")
        self.nota_mis_sonidos.setToolTip(str(carpeta))
        # La galería de fondos también ofrece los de Mis sonidos.
        if self._caja_fondos_mios is not None:
            for clave in [k for k in self.tarjetas_fondo if k[0] == "archivo"]:
                self.tarjetas_fondo.pop(clave)
            self._capa_galeria_fondos.removeWidget(self._caja_fondos_mios)
            self._caja_fondos_mios.hide()  # que no quede a la vista hasta que se borre
            self._caja_fondos_mios.deleteLater()
            self._caja_fondos_mios = None
        tarjetas = []
        for ruta in mios:
            t = TarjetaOpcion(ruta.name, ruta.stem, "Mis sonidos", "music", f"<b>{ruta.stem}</b><br>De Mis sonidos: "
                              "se repite con un fundido para cubrir todo.", accion="escuchar", color="#fbbf24")
            t.elegida.connect(lambda c: self.agregar_fondo("archivo", c))
            t.accionPedida.connect(lambda c: self.escuchar_fondo(pa.FondoProyecto("archivo", c)))
            self.tarjetas_fondo[("archivo", ruta.name)] = t
            tarjetas.append(t)
        if tarjetas:
            self._caja_fondos_mios = grilla(tarjetas)
            self._capa_galeria_fondos.addWidget(self._caja_fondos_mios)
        self._titulo_fondos_mios.setVisible(bool(tarjetas))
        self._actualizar_fondo_panel()

    def agregar_a_mis_sonidos(self, rutas: Optional[Sequence[str]] = None) -> list[Path]:
        """Copia archivos a Mis sonidos (con un diálogo si no vienen rutas). Devuelve las copias."""
        if rutas is None:
            filtro = FILTRO_ABRIR_AUDIO.split(";;")[0] + ";;Todos los archivos (*)"
            rutas, _ = QFileDialog.getOpenFileNames(self, "Agregar a Mis sonidos", str(Path.home() / "Music"), filtro)
            if not rutas:
                return []
        copias, errores = [], []
        for ruta in rutas:
            try:
                copias.append(pa.agregar_a_mis_sonidos(ruta))
            except (ValueError, OSError) as error:
                errores.append(f"• {Path(ruta).name}: {error}")
        self._olvidar_archivos([c.name for c in copias])  # uno que faltaba puede haber vuelto con ese nombre
        self._refrescar_mis_sonidos()
        if self.proyecto is not None:
            self._actualizar_vistas()
        if copias:
            self.tarjeta_mis_sonidos.boton.setChecked(True)
            self.etiqueta_estado.setText("Agregado a Mis sonidos: " + ", ".join(c.stem for c in copias[:4])
                                         + ("…" if len(copias) > 4 else "") + ".")
        if errores:
            QMessageBox.warning(self, "Algunos no se agregaron", "\n".join(errores[:10]))
        return copias

    def _soltar_archivos(self) -> None:
        """Antes de borrar o renombrar un archivo de Mis sonidos: que nada lo tenga abierto. Se
        espera al mezclador (hasta ``ESPERA_ARCHIVOS``) y a los hilos que leen sonidos (preparar
        los sueltos, escuchar 3 s); una medición del pico en curso se corta."""
        self.pausar()
        lector = self.reproductor.lector
        if lector is not None:
            cerrar_lector(lector, ESPERA_ARCHIVOS)
        self.reproductor.detener()
        self._generacion_escucha += 1
        self._pico_pedido = None
        self._pool_trabajo.waitForDone()
        self._pool_sonido.waitForDone()
        self._pool_pico.waitForDone()

    def _olvidar_archivos(self, nombres) -> None:
        """Lo que se sabía de unos archivos de Mis sonidos (cuánto duran, si el mezclador no los pudo
        usar) ya no vale: se agregaron, se renombraron o se borraron."""
        nombres = set(nombres)
        self._largos = {k: v for k, v in self._largos.items() if k[1] not in nombres}
        self._faltan_mezcla = tuple(c for c in self._faltan_mezcla if c not in nombres)

    @staticmethod
    def _usa_archivo(p: Optional[pa.ProyectoAudio], nombre: str) -> bool:
        return p is not None and any((c.origen, c.clave) == ("archivo", nombre) for c in p.fondos + p.sonidos)

    def _en_uso_exportando(self, nombre: str, accion: str) -> bool:
        """Si una exportación (o "Volver al video") en curso usa ese archivo: no se puede tocar (si no,
        sale sin él y sin avisar). Avisa y devuelve True."""
        if not ((self.exportando and self._usa_archivo(self._proyecto_exportando, nombre))
                or (self.volviendo and self._usa_archivo(self._proyecto_volviendo, nombre))):
            return False
        QMessageBox.information(self, "Esperá a que termine de exportar",
                                f"«{Path(nombre).stem}» está en lo que se está exportando. Esperá a que termine de "
                                f"exportar (o cancelalo) para {accion}.")
        return True

    def _nombre_nuevo(self, nombre: str, nuevo: str) -> str:
        """El nombre de archivo que va a quedar al renombrar (con la extensión), sin tocar nada.
        ``ValueError`` si no sirve o si ya hay otro que se llama así; ``FileNotFoundError`` si no está."""
        viejo = pa.carpeta_sonidos() / nombre
        if not viejo.is_file():
            raise FileNotFoundError(f"No está el sonido «{nombre}».")
        validar = getattr(pa, "_nombre_valido", None)   # las mismas reglas que el motor
        nuevo = validar(nuevo) if validar is not None else str(nuevo or "").strip()
        if not nuevo:
            raise ValueError("Poné un nombre.")
        if Path(nuevo).suffix.lower() != viejo.suffix.lower():
            nuevo += viejo.suffix
        destino = viejo.with_name(nuevo)
        if destino.exists() and destino.name.casefold() != viejo.name.casefold():
            raise ValueError(f"Ya hay un sonido que se llama «{destino.name}».")
        return destino.name

    @staticmethod
    def _renombrar_en_escenas(nombre: str, nuevo: str) -> int:
        """Las escenas propias que usan ese archivo de Mis sonidos se guardan de nuevo con el nombre
        nuevo. Devuelve cuántas cambiaron. (Usa la lectura y escritura del archivo de escenas del motor.)"""
        leer, escribir = getattr(pa, "_leer_escenas", None), getattr(pa, "_escribir_escenas", None)
        if leer is None or escribir is None:
            return 0
        escenas = leer(respaldar=True)
        cambiadas = 0
        for clave, e in list(escenas.items()):
            fondos = tuple(f.con(clave=nuevo) if (f.origen, f.clave) == ("archivo", nombre) else f for f in e.fondos)
            sonidos = tuple((nuevo,) + tuple(s[1:]) if len(s) > 3 and s[3] == "archivo" and s[0] == nombre
                            else tuple(s) for s in e.sonidos)
            if (fondos, sonidos) != (e.fondos, e.sonidos):
                escenas[clave] = replace(e, fondos=fondos, sonidos=sonidos)
                cambiadas += 1
        if cambiadas:
            escribir(escenas)
        return cambiadas

    def renombrar_mi_sonido(self, nombre: str, nuevo: Optional[str] = None) -> bool:
        """Le cambia el nombre a un archivo de Mis sonidos y actualiza el proyecto (todo su historial) y
        las escenas propias que lo usan. No mientras se exporta algo que lo usa."""
        if self._en_uso_exportando(nombre, "cambiarle el nombre"):
            return False
        if nuevo is None:
            nuevo, ok = QInputDialog.getText(self, "Cambiar el nombre", "Nombre nuevo:", QLineEdit.Normal,
                                             Path(nombre).stem)
            if not ok:
                return False
        try:  # primero se valida: un nombre que no sirve no corta lo que suena
            self._nombre_nuevo(nombre, nuevo)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "No se pudo cambiar el nombre", str(error))
            return False
        self._soltar_archivos()
        try:
            destino = pa.renombrar_sonido(nombre, nuevo)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "No se pudo cambiar el nombre", str(error))
            return False
        self._olvidar_archivos([nombre, destino.name])
        if destino.name != nombre:
            try:
                self._renombrar_en_escenas(nombre, destino.name)
            except (ValueError, OSError):
                pass  # las escenas quedan como estaban (lo verán como "falta")
            self._refrescar_escenas()
        if destino.name != nombre and self._historial:
            def cambiar(p: pa.ProyectoAudio) -> pa.ProyectoAudio:
                fondos = tuple(f.con(clave=destino.name) if (f.origen, f.clave) == ("archivo", nombre) else f
                               for f in p.fondos)
                sonidos = tuple(s.con(clave=destino.name) if (s.origen, s.clave) == ("archivo", nombre) else s
                                for s in p.sonidos)
                return p.con(fondos=fondos, sonidos=sonidos) if (fondos, sonidos) != (p.fondos, p.sonidos) else p
            self._historial = [(d, cambiar(p), e) for d, p, e in self._historial]
            _d, p, e = self._historial[self._pos]
            self._fijar_estado(p, e)
        self._refrescar_mis_sonidos()
        self.etiqueta_estado.setText(f"Ahora se llama {destino.stem}.")
        return True

    def borrar_mi_sonido(self, nombre: str, confirmar: bool = True) -> bool:
        if self._en_uso_exportando(nombre, "borrarlo"):
            return False
        usado = self._usa_archivo(self.proyecto, nombre)
        if confirmar:
            texto = f"¿Borrar «{Path(nombre).stem}» de Mis sonidos? El archivo original (de donde lo agregaste) no se toca."
            if usado:
                texto += "\n\nTu audio lo usa: va a quedar marcado como «falta» y no va a sonar."
            respuesta = QMessageBox.question(self, "Borrar de Mis sonidos", texto, QMessageBox.Yes | QMessageBox.No,
                                             QMessageBox.No)
            if respuesta != QMessageBox.Yes:
                return False
        self._soltar_archivos()
        try:
            pa.borrar_sonido(nombre)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "No se pudo borrar", str(error))
            return False
        self._olvidar_archivos([nombre])
        self._refrescar_mis_sonidos()
        self._actualizar_vistas()
        self.etiqueta_estado.setText(f"Se borró {Path(nombre).stem} de Mis sonidos.")
        return True

    def _faltan(self) -> set:
        """Las claves de los fondos y sonidos que no suenan: archivos de Mis sonidos que no están (o
        que el mezclador no pudo usar) y claves que esta versión no conoce."""
        p = self.proyecto
        if p is None:
            return set()
        faltan = set(self._faltan_mezcla)
        carpeta = pa.carpeta_sonidos()
        for c in p.fondos:
            if (c.origen == "archivo" and not (carpeta / c.clave).is_file()) or (
                    c.origen == "generado" and c.clave not in am.FONDOS):
                faltan.add(c.clave)
        for c in p.sonidos:
            if (c.origen == "archivo" and not (carpeta / c.clave).is_file()) or (
                    c.origen == "generado" and c.clave not in am.SONIDOS):
                faltan.add(c.clave)
        return faltan

    # ============================================================ volumen general
    def _al_cambiar_volumen_general(self, nuevo: ma.AjustesAudio, control: str) -> None:
        if self.proyecto is None:
            self._actualizar_vistas()
            return
        textos = {"normalizar": "Normalizar: lo más fuerte queda en -1 dB." if nuevo.normalizar else
                  "Sin normalizar.", "silencios": "Se devolvió todo el sonido.",
                  "volumen": f"Volumen general: {round(nuevo.volumen * 100)} %",
                  "fundido_entrada": f"Fundido de entrada: {formato_duracion(nuevo.fundido_entrada)}",
                  "fundido_salida": f"Fundido de salida: {formato_duracion(nuevo.fundido_salida)}"}
        juntar = control if control in ("volumen", "fundido_entrada", "fundido_salida") else ""
        self._editar(self.proyecto.con(sonido=nuevo), descripcion=textos.get(control, ""), control=juntar)

    # ============================================================ mostrar el estado
    def _actualizar_vistas(self) -> None:
        """Todo lo que se ve, con el proyecto de ahora."""
        p, e = self.proyecto, self.edicion
        hay = p is not None and e is not None
        mapa = self.mapa
        faltan = self._faltan() if hay else set()
        # Centro: onda grande, pistas y tiempos.
        if hay:
            self.onda.pista.establecer_edicion(list(e.tramos_conservados()), p.sonido, self._ganancia_dibujo())
            self.linea.establecer_silencios(p.sonido.silencios)
            self.pista_fondo.establecer_mapa(mapa)
            self.pista_fondo.establecer([CapaVista(nombre_fondo(f)[0], nombre_fondo(f)[1], round(f.volumen * 100),
                                                   f.clave in faltan) for f in p.fondos], pa.FUNDIDO_FONDO)
            self.pista_sonidos.establecer_mapa(mapa)
            self.pista_sonidos.establecer([BloqueSonido(float(mapa.a_resultado(s.ancla)), self._largo_sonido(s),
                                                        nombre_sonido(s)[1], nombre_sonido(s)[0], s.clave in faltan)
                                           for s in p.sonidos])
        else:
            self.pista_fondo.establecer_mapa(None)
            self.pista_fondo.establecer([])
            self.pista_sonidos.establecer_mapa(None)
            self.pista_sonidos.establecer([])
            self.linea.establecer_silencios(())
        self._mostrar_cursor()
        self._seleccion_en_onda()
        self._textos_linea()
        self.ayuda_linea.setText(AYUDA_LINEA_VIDEO if self.cortes_bloqueados else
                                 AYUDA_LINEA_CON_BORRADOS if hay and mapa.huecos() else AYUDA_LINEA)
        # Izquierda.
        voz = p.voz if hay else vn.AjustesVoz()
        self._marcar_escena()
        self.selector_destino.establecer(voz.destino if hay else "")
        self.control_cuanto.establecer(round(voz.cuanto * 100))
        self.control_anti_ia.establecer(round(voz.anti_ia * 100), 0)
        self.combo_lugar.blockSignals(True)
        self.combo_lugar.setCurrentIndex(max(0, self.combo_lugar.findData(voz.lugar)))
        self.combo_lugar.blockSignals(False)
        self.control_eco.establecer(round(voz.eco * 100), 50)
        self.control_ruido.establecer(round(voz.ruido_propio * 100), 50)
        self.check_compresion.blockSignals(True)
        self.check_compresion.setChecked(voz.compresion)
        self.check_compresion.blockSignals(False)
        self.control_tapa.establecer(round(voz.tapa * 100), 50)
        for w in (self.galeria_escenas, self.selector_destino, self.control_cuanto, self.control_anti_ia,
                  self.combo_lugar, self.control_eco, self.control_ruido, self.check_compresion, self.control_tapa,
                  self.boton_guardar_escena):
            w.setEnabled(hay)
        # Derecha.
        self._actualizar_fondo_panel(faltan)
        self._actualizar_sonidos_panel(faltan)
        self.panel_volumen.establecer(p.sonido if hay else ma.AjustesAudio(), mapa.duracion if hay else 0.0, True, hay)
        self._actualizar_formato()
        self._actualizar_habilitados()

    def _ganancia_dibujo(self) -> Optional[float]:
        """La ganancia con que se dibuja la voz: con normalizar y el pico ya medido, la exacta."""
        p = self.proyecto
        if p is None or not p.sonido.normalizar:
            return None
        pico = self._picos.get(self._clave_pico(p))
        return p.sonido.ganancia(pico) if pico is not None else None

    def _actualizar_fondo_panel(self, faltan: Optional[set] = None) -> None:
        p = self.proyecto
        fondos = p.fondos if p is not None else ()
        faltan = self._faltan() if faltan is None else faltan
        if len(self.filas_capas) != len(fondos):
            for fila in self.filas_capas:
                self.caja_capas.removeWidget(fila)
                fila.hide()  # que no quede a la vista hasta que se borre
                fila.deleteLater()
            self.filas_capas = []
            for i in range(len(fondos)):
                fila = FilaCapaFondo(i)
                fila.cambiada.connect(self.cambiar_fondo)
                fila.quitarPedido.connect(self.quitar_fondo)
                fila.escucharPedido.connect(lambda k: self.escuchar_fondo(self.proyecto.fondos[k]))
                self.caja_capas.addWidget(fila)
                self.filas_capas.append(fila)
        for fila, f in zip(self.filas_capas, fondos):
            icono, nombre, con_intensidad = nombre_fondo(f)
            ayuda = am.FONDOS[f.clave].descripcion if f.origen == "generado" and f.clave in am.FONDOS else \
                "De Mis sonidos: se repite con un fundido para cubrir todo."
            fila.establecer(icono, nombre, round(f.volumen * 100), round(f.intensidad * 100) if con_intensidad else None,
                            f.clave in faltan, ayuda)
        lleno = len(fondos) >= pa.CAPAS_MAX
        hay = p is not None
        self.boton_agregar_fondo.setEnabled(hay and not lleno)
        if lleno and self.boton_agregar_fondo.isChecked():
            self.boton_agregar_fondo.setChecked(False)
        self.boton_agregar_fondo.setText(f" Ya hay {pa.CAPAS_MAX} capas (el máximo)" if lleno else " Agregar una capa")
        self.boton_agregar_fondo.setToolTip(
            f"Ya hay {pa.CAPAS_MAX} capas: quitá una (con su ×) para sumar otra." if lleno else
            "Mostrar la galería de fondos (pasá el mouse por uno y tocá ▶ para escucharlo 3 segundos)")
        for t in self.tarjetas_fondo.values():
            t.setEnabled(hay and not lleno)
        if not hay:
            self.nota_fondo.setText("Abrí un audio para sumarle un fondo.")
        elif not fondos:
            self.nota_fondo.setText("Sin fondo. Elegí uno de la galería (podés sumar hasta 3, por ejemplo olas y "
                                    "viento).")
        else:
            self.nota_fondo.setText(f"{len(fondos)} de {pa.CAPAS_MAX} capas. 50 es el nivel de siempre.")

    def _alternar_galeria_fondos(self, abierta: bool) -> None:
        self.galeria_fondos.setVisible(abierta)
        self.boton_agregar_fondo.setIcon(iconos.icono("chevron-down" if abierta else "plus", 15))

    def _actualizar_sonidos_panel(self, faltan: Optional[set] = None) -> None:
        p = self.proyecto
        sonidos = p.sonidos if p is not None else ()
        faltan = self._faltan() if faltan is None else faltan
        if len(self.filas_sonidos) != len(sonidos):
            for fila in self.filas_sonidos:
                self.caja_sonidos.removeWidget(fila)
                fila.hide()  # que no quede a la vista hasta que se borre
                fila.deleteLater()
            self.filas_sonidos = []
            for i in range(len(sonidos)):
                fila = FilaSonido(i)
                fila.cambiada.connect(self.cambiar_sonido)
                fila.borrarPedido.connect(self.borrar_sonido)
                fila.irPedido.connect(self.ir_al_sonido)
                self.caja_sonidos.addWidget(fila)
                self.filas_sonidos.append(fila)
        mapa = self.mapa
        for fila, s in zip(self.filas_sonidos, sonidos):
            icono, nombre = nombre_sonido(s)
            fila.establecer(icono, nombre, formato_tiempo(mapa.a_resultado(s.ancla)), round(s.volumen * 100),
                            s.clave in faltan)
        self.boton_agregar_sonido.setEnabled(p is not None)
        self.nota_sonidos.setVisible(not sonidos)
        self.nota_sonidos.setText("Abrí un audio para sumarle sonidos." if p is None else
                                  "Todavía no hay sonidos sueltos: llevá el cursor a donde querés uno y tocá "
                                  "«Agregar en el cursor».")

    def _textos_linea(self, medir: bool = False) -> None:
        """Textos de la cabecera de la línea de tiempo según el ancho y el tramo elegido."""
        for b in (self.boton_entrada, self.boton_salida, self.boton_cortar):
            b.setText("" if self._iconos_linea >= 1 else b.property("texto"))
        if self.edicion is None:
            self.etiqueta_resultado.setText("—" if self._resultado_corto else "Duración final —")
        else:
            final, total = formato_tiempo(self.mapa.duracion), formato_tiempo(self.duracion_original)
            self.etiqueta_resultado.setText(f"{final} de {total}" if self._resultado_corto else
                                            f"Duración final {final}  de {total}")
        solo_icono, corto = self._iconos_linea >= 3, self._iconos_linea == 2
        devolver, silenciar = (" Devolver sonido", " Silenciar") if corto else (" Devolver el sonido",
                                                                                " Silenciar tramo")
        self.boton_borrar.setText("" if solo_icono else (" Borrar" if corto else " Borrar tramo"))
        if medir:
            self.boton_silenciar.setText("" if solo_icono else devolver)
            return
        silenciado, queda_algo = False, True
        if self.edicion is not None:
            i = self._tramo_objetivo()
            s = self.edicion.segmentos[i]
            silenciado = self.proyecto.sonido.silenciado(s.inicio, s.fin)
            queda_algo = bool(self.edicion.con_borrado(i).tramos_conservados())
        self.boton_borrar.setEnabled(self.edicion is not None and queda_algo and not self.cortes_bloqueados)
        self.boton_borrar.setToolTip(
            TEXTO_CORTES_EN_VIDEO if self.cortes_bloqueados else
            "Es lo único que queda: no se puede borrar todo el audio." if not queda_algo else
            "Borrar el tramo elegido (Supr): desaparece y no se exporta. Si no elegiste ninguno, el del cursor. "
            "Queda una marquita rosa en la unión para recuperarlo (o Ctrl+Z). Los sonidos sueltos siguen a la voz.")
        self.boton_silenciar.setText("" if solo_icono else (devolver if silenciado else silenciar))
        self.boton_silenciar.setIcon(iconos.icono("volume-2" if silenciado else "volume-x", 15))
        self.boton_silenciar.setEnabled(self.edicion is not None)
        self.boton_silenciar.setToolTip(
            "Devolverle el sonido al tramo elegido (M)" if silenciado else
            "Silenciar el tramo elegido (M): la voz se calla ahí, pero el fondo y los sonidos siguen. Para una parte "
            "cualquiera, cortá al principio y al final (S).")

    def _actualizar_formato(self) -> None:
        nombre = self._formato_elegido()
        partes = [DETALLE_FORMATO.get(nombre, nombre)]
        if self.proyecto is not None:
            partes.append(formato_tiempo(self.mapa.duracion, decimas=False))
            if nombre == "whatsapp" and self.proyecto.voz.destino == "whatsapp" and self.proyecto.voz.compresion:
                partes.append("sin comprimir dos veces")
        self.etiqueta_formato.setText(" · ".join(partes))

    def _formato_elegido(self) -> str:
        return next((n for n, b in self.botones_formato.items() if b.isChecked()), "wav")

    def _elegir_formato(self, nombre: str) -> None:
        config = configuracion()
        config.setValue(CLAVE_FORMATO, nombre)
        config.sync()
        self._actualizar_formato()

    def _actualizar_habilitados(self) -> None:
        hay = self.proyecto is not None
        for w in (self.boton_alejar, self.boton_acercar, self.boton_ajustar, self.boton_inicio, self.boton_atras,
                  self.boton_reproducir, self.boton_adelante, self.boton_fin, self.boton_antes, self.boton_despues):
            w.setEnabled(hay)
        # Con el sonido de un video, los cortes se hacen en el video (si no, se desalinea con la imagen).
        bloqueados = self.cortes_bloqueados
        for b, ayuda in ((self.boton_entrada, "Entrada (I): recorta lo de antes del cursor. Queda una marquita al "
                                              "principio para recuperarlo."),
                         (self.boton_salida, "Salida (O): recorta lo de después del cursor. Queda una marquita al "
                                             "final para recuperarlo."),
                         (self.boton_cortar, "Cortar: dividir el tramo en el cursor (S)")):
            b.setEnabled(hay and not bloqueados)
            b.setToolTip(TEXTO_CORTES_EN_VIDEO if bloqueados else ayuda)
        self.franja_video.setVisible(bloqueados)
        if bloqueados:
            self.mostrar_franja_video(Path(self.proyecto.video_origen).name)
        self.boton_volver_al_video.setEnabled(bloqueados and not self.volviendo)
        self.boton_deshacer.setEnabled(hay and self._pos > 0)
        self.boton_rehacer.setEnabled(hay and self._pos < len(self._historial) - 1)
        paso = self._historial[self._pos][0] if hay and 0 <= self._pos < len(self._historial) and self._pos > 0 else ""
        self.etiqueta_paso.setText(f"Último paso: {paso}" if paso else "")
        quedan = hay and self.mapa.duracion > 0
        self.boton_exportar.setEnabled(quedan and not self.exportando)
        self.boton_exportar.setText("  Exportando…" if self.exportando else "  Exportar audio…")
        for nombre, b in self.botones_formato.items():
            b.setEnabled(not self.exportando and nombre in self._formatos_disponibles)
        self.boton_cerrar_audio.setEnabled(hay and not self.exportando)
        self._actualizar_boton_sonido()

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
        if self.proyecto is None or self._reproduciendo:
            return
        mapa = self.mapa
        if mapa.duracion <= 0:
            self.etiqueta_estado.setText("No queda nada para escuchar: recuperá lo borrado o deshacé con Ctrl+Z.")
            return
        self._parar_escucha()
        if mapa.a_resultado(self.tiempo) >= mapa.duracion - 0.02:
            self.tiempo = mapa.a_original(0.0)  # desde el final: vuelve a empezar
        self._reproduciendo = True
        self._t_base, self._t_reloj = self.tiempo_resultado, time.monotonic()
        self.boton_reproducir.setIcon(iconos.icono("pause", 18, color="#ffffff"))
        self._timer_reproducir.start()
        self._iniciar_sonido()
        self._tick()

    def pausar(self) -> None:
        """Pausa (y corta "escuchar 3 s", si estaba sonando: también al cambiar de modo o de audio)."""
        self._parar_escucha()
        if not self._reproduciendo:
            return
        self._reproduciendo = False
        self._timer_reproducir.stop()
        self._timer_sonido.stop()
        self._gen_armado += 1   # un mezclador que se esté armando ya no hace falta
        self._gen_cambio += 1
        self.reproductor.detener()
        self._con_sonido = False
        self.boton_reproducir.setIcon(iconos.icono("play", 18, color="#ffffff"))

    def _proyecto_a_escuchar(self) -> pa.ProyectoAudio:
        """Lo que suena: el proyecto o, comparando ("Antes"), la voz sola con sus cortes y su volumen."""
        p = self.proyecto
        if self._escuchar_antes:
            return p.con(voz=vn.AjustesVoz(), fondos=(), sonidos=())
        return p

    def _iniciar_sonido(self) -> None:
        """Hace sonar desde el cursor. El mezclador se arma en otro hilo (``_pool_sonido``: sintetizar
        los sonidos o leer los de Mis sonidos puede tardar) y, mientras tanto, sigue sonando lo de antes
        (si sonaba algo): no se corta. Cuando está listo salta al cursor de ese momento y suena
        (``_sonido_armado``). Mientras suena, el reloj de la reproducción es el sonido; sin salida de
        sonido, el reloj propio."""
        self._timer_sonido.stop()
        self._gen_armado += 1
        generacion = self._gen_armado
        if (not self._reproduciendo or self.proyecto is None or self.reproductor.silenciado
                or not self.reproductor.hay_salida()):
            self.reproductor.detener()
            self._con_sonido = False
            return
        p = self._proyecto_a_escuchar()
        desde, pico = self.tiempo, self._pico_para(p)
        vigente = lambda: self._gen_armado  # noqa: E731 - se lee desde el hilo que arma

        def armar(_c):
            m = pa.MezcladorAudio(p, desde=desde, formato="s16", pico=pico, adelanto=pa.ADELANTO_VISTA_PREVIA)
            if vigente() != generacion:  # mientras se armaba se pausó, se movió el cursor o se cortó
                cerrar_lector(m)
                return generacion, None
            return generacion, m

        self._pool_sonido.start(Tarea("armar_sonido", generacion, armar, self._senales, vigente))

    def _sonido_armado(self, generacion: int, mezclador) -> None:
        """Llegó el mezclador pedido por ``_iniciar_sonido``: reemplaza a lo que sonaba (si sigue haciendo falta)."""
        if mezclador is None:
            return
        if generacion != self._gen_armado or not self._reproduciendo or self.reproductor.silenciado:
            cerrar_lector(mezclador)
            return
        mezclador.ir_a(self.tiempo)  # el cursor siguió mientras se armaba (no espera: lo hace su hilo)
        self._con_sonido = self.reproductor.reproducir_lector(mezclador)
        if not self._con_sonido:
            self._no_suena(self.reproductor.motivo)
            return
        self._t_base, self._t_reloj = self.tiempo_resultado, time.monotonic()
        self._poner_faltan_mezcla(getattr(mezclador, "faltan", ()))
        if mezclador.proyecto != self._proyecto_a_escuchar():  # cambió algo mientras se armaba
            self._cambiar_lo_que_suena()

    def _no_suena(self, motivo: str) -> None:
        """No se pudo armar lo que suena (por ejemplo, la voz ya no está): se pausa y se avisa. No se
        sigue con el reloj como si sonara."""
        self.pausar()
        self.etiqueta_estado.setText(f"No se pudo escuchar: {motivo or 'no se pudo leer el sonido.'}")

    def _cambiar_lo_que_suena(self) -> None:
        """Un cambio mientras suena: el mezclador lo toma sin cortar, en el hilo de lo que suena (armar lo
        nuevo puede tardar; mientras, sigue sonando lo de antes). Si no puede, se arma de nuevo."""
        lector = self.reproductor.lector
        if lector is None or not hasattr(lector, "cambiar_proyecto"):
            return
        p = self._proyecto_a_escuchar()
        pico = self._pico_para(p)
        self._gen_cambio += 1
        generacion = self._gen_cambio
        vigente = lambda: self._gen_cambio  # noqa: E731 - se lee desde el hilo que cambia

        def cambiar(_c):
            try:
                lector.cambiar_proyecto(p, pico=pico)
            except ValueError:  # el mezclador ya se cerró (se pausó o se armó otro): no hace falta
                return generacion, lector, None
            return generacion, lector, tuple(getattr(lector, "faltan", ()) or ())

        self._pool_sonido.start(Tarea("cambiar_sonido", generacion, cambiar, self._senales, vigente))

    def _sonido_cambiado(self, _generacion: int, lector, faltan) -> None:
        if faltan is not None and lector is self.reproductor.lector:
            self._poner_faltan_mezcla(faltan)

    def _poner_faltan_mezcla(self, faltan) -> None:
        """Lo que el mezclador no pudo usar (archivos que faltan o no se leen): se marca como "falta"."""
        faltan = tuple(faltan or ())
        if faltan != self._faltan_mezcla:
            self._faltan_mezcla = faltan
            if self.proyecto is not None:
                self._actualizar_vistas()

    def _comparar(self, antes: bool) -> None:
        self.boton_antes.setChecked(antes)
        self.boton_despues.setChecked(not antes)
        if antes == self._escuchar_antes:
            return
        self._escuchar_antes = antes
        self.etiqueta_estado.setText("Antes: la voz sin la escena (con los cortes)." if antes else
                                     "Después: como se va a exportar.")
        if self._reproduciendo and self._con_sonido:
            self._cambiar_lo_que_suena()

    def _tick(self) -> None:
        if not self._reproduciendo or self.proyecto is None:
            return
        ahora = time.monotonic()
        mapa = self.mapa
        if self._con_sonido:
            t = self.reproductor.posicion()
            if t is not None:
                r = mapa.a_resultado(t)
                self._t_base, self._t_reloj = r, ahora
            else:
                self._con_sonido = False
                r = self._t_base + (ahora - self._t_reloj)
        else:
            r = self._t_base + (ahora - self._t_reloj)
        if not mapa.tramos or r >= mapa.duracion - 1e-6:
            self.tiempo = mapa.a_original(mapa.duracion) if mapa.tramos else 0.0
            self._mostrar_cursor(seguir=True)
            self.pausar()
            return
        self.tiempo = mapa.a_original(max(0.0, r))
        self._mostrar_cursor(seguir=True)

    @staticmethod
    def _sonido_vista_guardado() -> bool:
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
                self._con_sonido = False

    def _actualizar_boton_sonido(self) -> None:
        activo = self.boton_sonido.isChecked()
        self.boton_sonido.setIcon(iconos.icono("volume-2" if activo else "volume-x", 15))
        disponible = self.reproductor.disponible
        self.boton_sonido.setEnabled(disponible)
        if not disponible:
            ayuda = f"Sin sonido en la vista previa: {self.reproductor.motivo or 'no hay salida de sonido.'}"
        else:
            ayuda = ("Sonido al reproducir: escuchá cómo va a quedar. Apagalo para recorrer en silencio (no cambia lo "
                     "que se exporta).")
            if not activo:
                ayuda = "La vista previa está silenciada. " + ayuda
        self.boton_sonido.setToolTip(ayuda)

    def _sonido_fallo(self, mensaje: str) -> None:
        self._con_sonido = False
        self.etiqueta_estado.setText(f"{mensaje} La vista previa sigue sin sonido.")
        self._actualizar_boton_sonido()

    def _sonido_terminado(self) -> None:
        self._con_sonido = False  # el reloj sigue hasta el final (o terminó "escuchar 3 s")

    # ============================================================ normalizar
    @staticmethod
    def _clave_pico(p: pa.ProyectoAudio) -> pa.ProyectoAudio:
        """Lo que define el pico: el proyecto sin volumen, normalizar ni fundidos."""
        return replace(p, sonido=ma.AjustesAudio(silencios=p.sonido.silencios))

    def _pico_para(self, p: pa.ProyectoAudio) -> Optional[float]:
        """Pico exacto para escuchar con "Normalizar" o, mientras se mide en otro hilo, el que se
        estima con la forma de onda de la voz. Solo vale lo último que se pidió: lo viejo se descarta."""
        if not p.sonido.normalizar:
            return None
        clave = self._clave_pico(p)
        self._pico_pedido = clave
        if clave in self._picos:
            return self._picos[clave]
        if clave not in self._midiendo:
            self._midiendo.add(clave)
            vieja = lambda: self._pico_pedido != clave  # noqa: E731 - se lee desde el hilo que mide

            def medir(_c):
                if vieja():
                    return clave, None
                try:
                    return clave, pa.medir_pico_proyecto(clave, vieja)
                except Cancelado:
                    return clave, None

            self._pool_pico.start(Tarea("pico", 0, medir, self._senales))
        forma = self.cargador_onda.forma if self.cargador_onda.ruta == p.ruta else None
        aproximado = pico_aproximado(forma, p.tramos, p.sonido.silencios)
        return aproximado if aproximado else 1.0

    def _pico_medido(self, clave, pico: Optional[float]) -> None:
        self._midiendo.discard(clave)
        if pico is None:
            return
        self._picos[clave] = pico
        p = self.proyecto
        if p is None or not p.sonido.normalizar or self._clave_pico(p) != clave:
            return
        self.onda.pista.establecer_edicion(list(self.edicion.tramos_conservados()), p.sonido, self._ganancia_dibujo())
        if self._reproduciendo and self._con_sonido and not self._escuchar_antes:
            self._cambiar_lo_que_suena()

    # ============================================================ forma de onda
    def _onda_parcial(self, forma) -> None:
        if self.proyecto is not None:
            self.onda.pista.establecer_forma(forma)
            self.linea.establecer_forma(forma)

    def _onda_lista(self, forma) -> None:
        if self.proyecto is None:
            return
        if forma is None:
            self.onda.pista.sin_sonido(self.duracion_original)
            self.linea.establecer_forma(None)
        else:
            self.onda.pista.establecer_forma(forma)
            self.linea.establecer_forma(forma)

    def _onda_fallida(self, _mensaje: str) -> None:
        if self.proyecto is not None:
            self.onda.pista.sin_sonido(self.duracion_original, "No se pudo leer la forma de onda")

    # ============================================================ tareas
    def _tarea_terminada(self, tipo: str, generacion: int, resultado) -> None:
        if tipo == "avance":
            self._avance_exportacion(*resultado)
        elif tipo == "exportacion":
            self._exportacion_terminada(resultado)
        elif tipo == "avance_volver":
            if self.volviendo:
                hechas, total = resultado
                self.barra_volver.setValue(round(1000 * hechas / max(1, total)))
        elif tipo == "volver":
            self._vuelta_lista(resultado)
        elif tipo == "armar_sonido":
            self._sonido_armado(*resultado)
        elif tipo == "cambiar_sonido":
            self._sonido_cambiado(*resultado)
        elif tipo == "pico":
            self._pico_medido(*resultado)
        elif tipo == "largos":
            pendientes, largos = resultado
            self._calentando.difference_update(pendientes)
            if largos:
                self._largos.update(largos)
                if self.proyecto is not None:
                    self._actualizar_vistas()
        elif tipo == "escuchar":
            if generacion != self._generacion_escucha or self._reproduciendo:
                return
            nombre, datos = resultado
            if self.reproductor.reproducir_lector(LectorArreglo(datos)):
                self.etiqueta_estado.setText(f"Escuchando {nombre} (3 segundos).")
            else:
                self.etiqueta_estado.setText(f"No se pudo escuchar {nombre}: {self.reproductor.motivo or 'sin sonido.'}")

    def _tarea_fallida(self, tipo: str, _generacion: int, mensaje: str) -> None:
        if tipo == "exportacion":
            self._fin_exportacion()
            self.etiqueta_estado.setText("La exportación falló.")
            QMessageBox.critical(self, "Error al exportar", f"No se pudo exportar el audio.\n\n{mensaje}")
        elif tipo == "armar_sonido":
            if _generacion == self._gen_armado and self._reproduciendo:
                self._no_suena(mensaje)
        elif tipo == "cambiar_sonido":
            if _generacion == self._gen_cambio and self._reproduciendo:
                self._iniciar_sonido()  # no se pudo cambiar sin cortar: se arma de nuevo desde el cursor
        elif tipo == "volver":
            self._fin_volver()
            self.etiqueta_estado.setText("No se pudo preparar el sonido para el video.")
            QMessageBox.warning(self, "No se pudo volver al video", f"No se pudo preparar el sonido: el video "
                                f"queda como estaba.\n\n{mensaje}")
        elif tipo == "pico":
            self._midiendo.clear()   # se vuelve a intentar la próxima vez (mientras, la estimación)
        elif tipo == "largos":
            self._calentando.clear()
        elif tipo == "escuchar":
            self.etiqueta_estado.setText(f"No se pudo escuchar: {mensaje}")

    # ============================================================ exportar
    def exportar(self) -> None:
        if self.proyecto is None or self.exportando:
            return
        if self.mapa.duracion <= 0:
            QMessageBox.information(self, "Nada para exportar", "No queda nada: está todo borrado. Recuperá lo "
                                    "borrado (tocá una marquita rosa) o deshacé con Ctrl+Z.")
            return
        nombre = self._formato_elegido()
        info = pa.FORMATOS_PROYECTO_INFO[nombre]
        self.pausar()
        self._parar_escucha()
        sugerida = pa.ruta_salida_proyecto(self.proyecto, nombre)
        filtro = f"{info.descripcion} (*{info.extension})"
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar audio", str(sugerida), filtro)
        if not ruta:
            return
        destino = Path(ruta)
        validas = (".ogg", ".opus") if nombre == "whatsapp" else (info.extension,)
        if destino.suffix.lower() not in validas:
            destino = destino.with_suffix(info.extension)
        if self.es_el_abierto(str(destino)):
            QMessageBox.warning(self, "Elegí otro nombre", "Ese es el audio original. Para no sobrescribirlo, elegí "
                                "otro nombre.")
            return
        p = self.proyecto
        senales = self._senales
        self._cancelar_exportacion = False
        cancelado = lambda: self._cancelar_exportacion  # noqa: E731 - se lee desde el hilo de la exportación

        def trabajo(_c):
            def avance(hechas, total, restante):
                senales.terminada.emit("avance", 0, (hechas, total, restante))
            try:
                return pa.exportar_proyecto(p, destino, nombre, avance, cancelado)
            except Cancelado:
                return "cancelado"

        self.exportando = True
        self._proyecto_exportando = p  # sus archivos de Mis sonidos no se tocan hasta que termine
        self._inicio_exportacion = time.monotonic()
        self.barra_exportacion.setValue(0)
        self.etiqueta_progreso.setText("Preparando…")
        self.caja_progreso.show()
        self.boton_cancelar.setEnabled(True)
        self._actualizar_habilitados()
        self.etiqueta_estado.setText(f"Exportando {destino.name}…")
        self._pool_exportar.start(Tarea("exportacion", 0, trabajo, self._senales))
        self.exportacionCambiada.emit(True)

    def _avance_exportacion(self, hechas: int, total: int, restante: Optional[float]) -> None:
        if not self.exportando:
            return
        self.barra_exportacion.setValue(round(1000 * hechas / max(1, total)))
        texto = f"{round(100 * hechas / max(1, total))} %"
        if restante is not None:
            texto += f" · faltan {formato_tiempo(restante, decimas=False)}"
        self.etiqueta_progreso.setText(texto)
        self.progresoExportacion.emit(int(hechas), int(total))

    def cancelar_exportacion(self) -> None:
        if self.exportando:
            self._cancelar_exportacion = True
            self.boton_cancelar.setEnabled(False)
            self.etiqueta_progreso.setText("Cancelando…")

    def _fin_exportacion(self) -> None:
        self.exportando = False
        self._proyecto_exportando = None
        self.caja_progreso.hide()
        self._actualizar_habilitados()
        self._actualizar_info()
        self.exportacionCambiada.emit(False)

    def _exportacion_terminada(self, resultado) -> None:
        self._fin_exportacion()
        if resultado == "cancelado":
            self.etiqueta_estado.setText("Exportación cancelada. No quedó ningún archivo a medias.")
            return
        r: ma.ResultadoAudio = resultado
        self.ultima_exportacion = r
        canales = "mono" if r.canales == 1 else "estéreo"
        descripcion = pa.FORMATOS_PROYECTO_INFO[r.formato].descripcion if r.formato in pa.FORMATOS_PROYECTO_INFO \
            else r.formato
        detalle = (f"{descripcion} · {formato_tiempo(r.duracion)} · {r.frecuencia // 1000} kHz · {canales}\n"
                   f"Tardó {formato_tiempo(r.segundos, decimas=False)}.")
        self.etiqueta_estado.setText(f"Exportado: {r.ruta}")
        if not self.isVisible():
            self.exportacionLista.emit(f"Listo: se exportó el audio {Path(r.ruta).name}.", f"{r.ruta}\n{detalle}")
            return
        QMessageBox.information(self, "Audio exportado", f"Se guardó el audio en:\n{r.ruta}\n\n{detalle}")

    # ============================================================ volver al video
    @staticmethod
    def carpeta_temporal() -> Path:
        """``%APPDATA%\\NaturalShot PRO\\temporal``: los WAV que van y vienen con el modo Video."""
        return Path(os.environ.get("APPDATA") or Path.home()) / "NaturalShot PRO" / "temporal"

    def volver_al_video(self) -> bool:
        """"Volver al video con este sonido": exporta el proyecto a un WAV (en segundo plano, con
        progreso en la franja) en ``carpeta_temporal()``, con un nombre único, y al terminar emite
        ``volverAlVideoPedido(ruta_wav, ruta_video)``. Si falla o se cancela, avisa y no emite
        nada (y no queda el archivo). False si no empezó."""
        p = self.proyecto
        if p is None or p.video_origen is None or self.volviendo:
            return False
        if self.mapa.duracion <= 0:
            return False
        self.pausar()
        self._parar_escucha()
        carpeta = self.carpeta_temporal()
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            fd, ruta = tempfile.mkstemp(prefix=f"{Path(p.video_origen).stem} - sonido ", suffix=".wav",
                                        dir=str(carpeta))
            os.close(fd)
        except OSError as error:
            QMessageBox.warning(self, "No se pudo volver al video", f"No se pudo preparar el sonido.\n\n{error}")
            return False
        destino, video = Path(ruta), str(p.video_origen)
        senales = self._senales
        self._cancelar_volver = False
        cancelado = lambda: self._cancelar_volver  # noqa: E731 - se lee desde el hilo que exporta

        def borrar_reservado() -> None:
            try:
                destino.unlink()
            except OSError:
                pass

        def trabajo(_c):
            def avance(hechas, total, _restante):
                senales.terminada.emit("avance_volver", 0, (hechas, total))
            try:
                pa.exportar_proyecto(p, destino, "wav", avance, cancelado)
            except Cancelado:
                borrar_reservado()
                return "cancelado"
            except BaseException:
                borrar_reservado()  # no queda nada a medias
                raise
            return str(destino), video

        self.volviendo = True
        self._proyecto_volviendo = p  # sus archivos de Mis sonidos no se tocan hasta que termine
        self.barra_volver.setValue(0)
        self.barra_volver.show()
        self.boton_cancelar_volver.show()
        self.boton_cancelar_volver.setEnabled(True)
        self.boton_volver_al_video.setText(" Preparando el sonido…")
        self._actualizar_habilitados()
        self.etiqueta_estado.setText(f"Preparando el sonido para {Path(video).name}…")
        self._pool_volver.start(Tarea("volver", 0, trabajo, self._senales))
        return True

    def cancelar_volver(self) -> None:
        if self.volviendo:
            self._cancelar_volver = True
            self.boton_cancelar_volver.setEnabled(False)

    def _fin_volver(self) -> None:
        self.volviendo = False
        self._proyecto_volviendo = None
        self.barra_volver.hide()
        self.boton_cancelar_volver.hide()
        self.boton_volver_al_video.setText(" Volver al video con este sonido")
        self._actualizar_habilitados()

    def _vuelta_lista(self, resultado) -> None:
        self._fin_volver()
        if resultado == "cancelado":
            self.etiqueta_estado.setText("Se canceló: el video queda como estaba.")
            return
        ruta_wav, ruta_video = resultado
        if self.proyecto is None or self.proyecto.video_origen != ruta_video:
            # Mientras se armaba se abrió otro audio (o se cerró): ese sonido ya no va a ningún video.
            try:
                Path(ruta_wav).unlink()
            except OSError:
                pass
            self.etiqueta_estado.setText(f"El sonido no volvió a {Path(ruta_video).name}: abriste otro audio "
                                         "mientras se preparaba.")
            return
        self.etiqueta_estado.setText(f"Listo: el sonido va al video {Path(ruta_video).name}.")
        self.volverAlVideoPedido.emit(ruta_wav, ruta_video)

    # ============================================================ sesión
    def estado_sesion(self) -> Optional[sesion.AudioGuardado]:
        """Lo que se recuerda del modo Audio: el proyecto, la edición, el cursor, el historial y la
        posición en él (None si no hay audio abierto)."""
        if self.proyecto is None or not self._historial:
            return None
        datos: dict[int, tuple] = {}

        def estado(p: pa.ProyectoAudio, e: EdicionVideo) -> dict:
            if id(e) not in datos:
                datos[id(e)] = datos_edicion(e)
            return {"proyecto": p, "edicion": datos[id(e)]}

        historial = [(d, estado(p, e)) for d, p, e in self._historial]
        actual = dict(estado(self.proyecto, self.edicion))
        actual["tiempo"] = float(self.tiempo)
        return sesion.AudioGuardado(actual, historial, self._pos)

    def restaurar_sesion(self, guardado: sesion.AudioGuardado) -> bool:
        """Vuelve a poner el proyecto de la sesión anterior. False si la voz ya no se puede abrir."""
        try:
            estado = guardado.estado
            proyecto = estado["proyecto"]
            info = ma.info_medio(proyecto.ruta)
        except Exception:
            return False
        duracion = float(info.duracion)
        pasos = guardado.historial or [("Inicio", estado)]
        historial = []
        for descripcion, paso in pasos:
            p = paso["proyecto"]
            historial.append((str(descripcion), p, edicion_de_datos(paso.get("edicion"), duracion, p.tramos)))
        pos = max(0, min(int(guardado.pos), len(historial) - 1))
        if historial[pos][1] != proyecto:  # no debería pasar: el estado es el paso actual
            historial = historial[:pos + 1] + [("Sesión", proyecto, edicion_de_datos(estado.get("edicion"), duracion,
                                                                                     proyecto.tramos))]
            pos = len(historial) - 1
        self.cargar_proyecto(proyecto, historial, pos, float(estado.get("tiempo") or 0.0))
        self.etiqueta_estado.setText(f"Se recuperó {Path(proyecto.ruta).name}, de la sesión anterior.")
        return True

    # ============================================================ cerrar la app
    def detener(self) -> None:
        """Al cerrar la ventana: cancela lo que esté en curso (también una exportación, que no deja
        archivos a medias), espera a los hilos y suelta los archivos."""
        if self.exportando:
            self._cancelar_exportacion = True
        self._cancelar_volver = True
        self._reproduciendo = False
        self._timer_reproducir.stop()
        self._timer_sonido.stop()
        self._generacion_escucha += 1
        self._pico_pedido = None   # una medición en curso se corta
        lector = self.reproductor.lector
        if lector is not None:
            cerrar_lector(lector, ESPERA_CERRAR)
        self.reproductor.cerrar()
        self._con_sonido = False
        self.cargador_onda.detener()
        self._gen_armado += 1
        self._gen_cambio += 1
        for pool in (self._pool_exportar, self._pool_pico, self._pool_trabajo, self._pool_volver, self._pool_sonido):
            pool.waitForDone()


__all__ = ["EditorAudio", "abrir_voz", "datos_edicion", "edicion_de_datos", "edicion_de_tramos", "muestra_fondo",
           "muestra_archivo", "LectorArreglo", "nombre_fondo", "nombre_sonido"]
