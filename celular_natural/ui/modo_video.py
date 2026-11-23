"""Modo Video (y Audio): lo que la ventana principal usa para tener los editores adentro.

El selector de arriba a la izquierda tiene cuatro modos: **Fácil | Editor | Video |
Audio**. Fácil y Editor son de fotos y comparten todo; Video muestra el editor de video
(``editor_video.EditorVideo``) y Audio el de audio (``modo_audio.EditorAudio``) en la
misma ventana, cada uno con su propia columna izquierda y derecha. La marca y el
selector quedan siempre en el mismo lugar.

Acá están las piezas chicas que no son de los editores ni de la ventana:

* ``clasificar_rutas``: separa fotos, videos y (con ``audios=True``) audios, por la
  extensión, al abrir o arrastrar.
* ``mensaje_ruteo``: el aviso que explica a qué modo fue cada cosa.
* ``mensaje_solo_fotos`` y ``FILTRO_ABRIR_FOTOS``: en NaturalShot Lite (solo fotos), el aviso
  para los videos y audios (no se abren) y el diálogo de Abrir con solo imágenes.
* ``BotonModo``: botón del selector, con un punto opcional ("hay un video abierto").
* ``ChipExportacion``: el progreso de una exportación de video (o de audio) mientras
  se trabaja en otro modo (tocarlo lleva a su modo).
* ``EtiquetaElidida``: el estado de la vista previa (fotos y video) termina en "…"
  si no entra, en vez de cortarse a mitad de palabra.

Este módulo no importa PyAV: la app de fotos no lo carga hasta entrar a Video o a Audio (y la
Lite, nunca). ``EXTENSIONES_AUDIO`` viene de ``motor/proyecto_audio.py``, que tampoco lo importa
al cargarse (lo pide recién al leer o exportar un audio).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSizePolicy

from ..motor.imagen_io import EXTENSIONES_SOPORTADAS, EXTENSIONES_VIDEO
from ..motor.proyecto_audio import EXTENSIONES_AUDIO  # sin PyAV (la sesión ya importa este módulo)
from . import estilo, iconos

# Diálogo de Abrir: fotos y videos juntos (cada cosa va después a su modo).
_FOTOS = " ".join(f"*{e}" for e in EXTENSIONES_SOPORTADAS)
_VIDEOS = " ".join(f"*{e}" for e in EXTENSIONES_VIDEO)
_AUDIOS = " ".join(f"*{e}" for e in EXTENSIONES_AUDIO)
FILTRO_FOTOS_Y_VIDEOS = (f"Fotos y videos ({_FOTOS} {_VIDEOS});;Fotos ({_FOTOS});;Videos ({_VIDEOS});;"
                         "Todos los archivos (*)")
# El de la ventana: también los audios (van al modo Audio). El nombre del primero sigue empezando
# con "Fotos y videos": así lo reconocen las pruebas del modo Video y lo de siempre no cambia.
FILTRO_ABRIR = (f"Fotos y videos (y audios) ({_FOTOS} {_VIDEOS} {_AUDIOS});;Fotos ({_FOTOS});;"
                f"Videos ({_VIDEOS});;Audios ({_AUDIOS});;Todos los archivos (*)")
# En el modo Audio, primero los audios (y todo lo demás a mano, en la misma lista de filtros).
FILTRO_ABRIR_AUDIO = (f"Audios ({_AUDIOS});;Fotos, videos y audios ({_FOTOS} {_VIDEOS} {_AUDIOS});;"
                      "Todos los archivos (*)")
# NaturalShot Lite (solo fotos): el diálogo de Abrir ofrece solo imágenes.
FILTRO_ABRIR_FOTOS = f"Fotos ({_FOTOS});;Todos los archivos (*)"
AVISO_SOLO_FOTOS = "NaturalShot Lite es solo para fotos"
COLOR_VIDEO = estilo.ROSA  # el ícono del modo Video, para que se distinga de Fácil y Editor
COLOR_AUDIO = "#a78bfa"    # el del modo Audio (lavanda, de la misma paleta)


def es_video(ruta: str) -> bool:
    return Path(ruta).suffix.lower() in EXTENSIONES_VIDEO


def es_foto(ruta: str) -> bool:
    return Path(ruta).suffix.lower() in EXTENSIONES_SOPORTADAS


def es_audio(ruta: str) -> bool:
    """Un archivo de solo sonido (MP3, M4A, AAC, WAV, OGG, OPUS o FLAC), por la extensión."""
    return Path(ruta).suffix.lower() in EXTENSIONES_AUDIO


def clasificar_rutas(rutas: Iterable[str], audios: bool = False) -> tuple:
    """(fotos, videos) en el orden en que vinieron, sin repetidos; con ``audios=True``,
    (fotos, videos, audios).

    Lo que no es un video (ni, con ``audios``, un audio) se trata como foto (por ejemplo,
    desde "Todos los archivos"): si no se puede leer, la ventana avisa como siempre."""
    fotos, videos, sonidos, vistas = [], [], [], set()
    for ruta in rutas:
        if not ruta:
            continue
        ruta = str(Path(ruta))
        clave = os.path.normcase(os.path.abspath(ruta))
        if clave in vistas:
            continue
        vistas.add(clave)
        if es_video(ruta):
            videos.append(ruta)
        elif audios and es_audio(ruta):
            sonidos.append(ruta)
        else:
            fotos.append(ruta)
    return (fotos, videos, sonidos) if audios else (fotos, videos)


def mensaje_solo_fotos(videos: list[str], audios: list[str], fotos: list[str]) -> tuple[str, str]:
    """NaturalShot Lite: el aviso para los videos y audios que no se abren, (texto, detalle para
    la ayuda). ``fotos``: las que sí van a la tira. Sin videos ni audios, ("", "")."""
    afuera = list(videos) + list(audios)
    if not afuera:
        return "", ""
    if videos and audios:
        cosa = "Los videos y los audios no se abren"
    elif videos:
        cosa = "Los videos no se abren" if len(videos) > 1 else "El video no se abre"
    else:
        cosa = "Los audios no se abren" if len(audios) > 1 else "El audio no se abre"
    texto = f"{AVISO_SOLO_FOTOS}: {cosa[0].lower()}{cosa[1:]}."
    if fotos:
        texto += " La foto va a la tira." if len(fotos) == 1 else f" Las {len(fotos)} fotos van a la tira."
    nombres = [Path(r).name for r in afuera[:10]] + (["…"] if len(afuera) > 10 else [])
    return texto, "No se abrieron: " + ", ".join(nombres)


def _otros(ignorados: list[str], cosa: str, cosas: str) -> str:
    if not ignorados:
        return ""
    if len(ignorados) == 1:
        return f" El otro {cosa} no se abrió: se edita uno a la vez."
    return f" Los otros {len(ignorados)} {cosas} no se abrieron: se edita uno a la vez."


def mensaje_ruteo(desde_video: bool, fotos: list[str], video: Optional[str], ignorados: list[str],
                  video_abierto: bool = False, *, audio: Optional[str] = None, ignorados_audio=(),
                  desde_audio: bool = False, audio_abierto: bool = False) -> tuple[str, str]:
    """El aviso que explica a dónde fue cada cosa: (texto, detalle para la ayuda).

    ``desde_video``: si se abrió estando en el modo Video. ``video``: el video que se
    abrió (o None). ``ignorados``: los otros videos (se edita uno a la vez).
    ``video_abierto``: si en el modo Video queda un video abierto. Sin nada que
    explicar (fotos en el modo de fotos, o un video en el modo Video) devuelve ("", "").

    Con audios: ``audio`` es el que se abrió en el modo Audio (o None),
    ``ignorados_audio`` los otros, ``desde_audio`` si se abrió estando en Audio y
    ``audio_abierto`` si en Audio queda un audio abierto. Sin nada de eso, el aviso es
    el de siempre.
    """
    if audio or desde_audio or ignorados_audio:
        return _mensaje_con_audio(desde_video, desde_audio, fotos, video, list(ignorados), audio,
                                  list(ignorados_audio), video_abierto, audio_abierto)
    otros = _otros(ignorados, "video", "videos")
    nombres = [Path(r).name for r in fotos[:10]] + (["…"] if len(fotos) > 10 else [])
    detalle = []
    if video:
        detalle.append(f"Video: {Path(video).name}")
    if nombres:
        detalle.append(("Foto: " if len(fotos) == 1 else "Fotos: ") + ", ".join(nombres))
    if ignorados:
        detalle.append("No se abrieron: " + ", ".join(Path(r).name for r in ignorados[:10]))
    detalle = "\n".join(detalle)
    if video and fotos:
        texto = ("La foto va a la tira de fotos" if len(fotos) == 1 else f"Las {len(fotos)} fotos van a la tira "
                 "de fotos") + " y el video lo abrimos en el modo Video." + otros
        return texto, detalle
    if video:
        if desde_video:
            return (f"Abrimos {Path(video).name}." + otros, detalle) if ignorados else ("", "")
        return ("Esto es un video: lo abrimos en el modo Video." + otros
                + " Para volver a tus fotos, tocá Fácil o Editor.", detalle)
    if fotos and desde_video:
        texto = ("Esto es una foto: la abrimos en el modo de fotos." if len(fotos) == 1 else
                 "Estas son fotos: las abrimos en el modo de fotos.")
        if video_abierto:
            texto += " Tu video sigue abierto en el modo Video."
        return texto, detalle
    return "", ""


def _mensaje_con_audio(desde_video: bool, desde_audio: bool, fotos: list[str], video: Optional[str],
                       ignorados: list[str], audio: Optional[str], ignorados_audio: list[str],
                       video_abierto: bool, audio_abierto: bool) -> tuple[str, str]:
    """``mensaje_ruteo`` cuando hay audios o se abrió desde el modo Audio."""
    otros = _otros(ignorados, "video", "videos") + _otros(ignorados_audio, "audio", "audios")
    nombres = [Path(r).name for r in fotos[:10]] + (["…"] if len(fotos) > 10 else [])
    detalle = []
    if video:
        detalle.append(f"Video: {Path(video).name}")
    if audio:
        detalle.append(f"Audio: {Path(audio).name}")
    if nombres:
        detalle.append(("Foto: " if len(fotos) == 1 else "Fotos: ") + ", ".join(nombres))
    if ignorados or ignorados_audio:
        detalle.append("No se abrieron: " + ", ".join(Path(r).name for r in (ignorados + ignorados_audio)[:10]))
    detalle = "\n".join(detalle)
    tira = ("La foto va a la tira de fotos" if len(fotos) == 1 else f"Las {len(fotos)} fotos van a la tira de "
            "fotos") if fotos else ""
    sigue_audio = " Tu audio sigue abierto en el modo Audio." if desde_audio and audio_abierto and not audio else ""
    if audio and video:
        cosas = "el video lo abrimos en el modo Video y el audio, en el modo Audio."
        texto = (f"{tira}, {cosas}" if tira else cosas[0].upper() + cosas[1:]) + otros
        return texto, detalle
    if audio:
        if tira:
            return f"{tira} y el audio lo abrimos en el modo Audio." + otros, detalle
        if desde_audio:
            return (f"Abrimos {Path(audio).name}." + otros, detalle) if otros else ("", "")
        volver = (" Tu video sigue abierto en el modo Video." if desde_video and video_abierto else
                  " Para volver a tus fotos, tocá Fácil o Editor.")
        return "Esto es un audio: lo abrimos en el modo Audio." + otros + volver, detalle
    if video:  # desde Audio (o con audios ignorados)
        if tira:
            return f"{tira} y el video lo abrimos en el modo Video." + otros + sigue_audio, detalle
        if desde_video:
            return (f"Abrimos {Path(video).name}." + otros, detalle) if otros else ("", "")
        return "Esto es un video: lo abrimos en el modo Video." + otros + sigue_audio, detalle
    if fotos and (desde_audio or desde_video):
        texto = ("Esto es una foto: la abrimos en el modo de fotos." if len(fotos) == 1 else
                 "Estas son fotos: las abrimos en el modo de fotos.")
        if desde_video and video_abierto:
            texto += " Tu video sigue abierto en el modo Video."
        return texto + sigue_audio + otros, detalle
    return (otros.strip(), detalle) if otros else ("", "")


def icono_modo(nombre: str, tam: int = 16, color: Optional[str] = None) -> QIcon:
    """Ícono del selector: en ``color`` (o el del tema) y blanco cuando el botón está marcado."""
    ic = QIcon(iconos.icono(nombre, tam, color))
    for modo in (QIcon.Normal, QIcon.Active, QIcon.Selected):
        ic.addPixmap(iconos.pixmap(nombre, tam, "#ffffff"), modo, QIcon.On)
    return ic


class BotonModo(QPushButton):
    """Botón del selector Fácil | Editor | Video, con un punto opcional arriba a la derecha
    (en Video: hay un video abierto mientras se trabaja en fotos)."""

    def __init__(self, texto: str, parent=None):
        super().__init__(texto, parent)
        self._punto = False

    @property
    def punto(self) -> bool:
        return self._punto

    def establecer_punto(self, valor: bool) -> None:
        if valor != self._punto:
            self._punto = valor
            self.update()

    def paintEvent(self, evento) -> None:
        super().paintEvent(evento)
        if not self._punto or self.isChecked():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.width() - 13, 5, 8, 8)
        p.setPen(QPen(QColor(estilo.LATERAL), 2))
        p.setBrush(QColor(estilo.MAGENTA))
        p.drawEllipse(r)
        p.end()


class ChipExportacion(QFrame):
    """Progreso de la exportación de video mientras se está en Fácil o Editor (o, con
    ``tipo="audio"``, la de audio mientras se está en otro modo).

    Va debajo del selector de modo; tocarlo lleva a su modo (ahí están el detalle,
    el tiempo que falta y Cancelar)."""

    clicked = Signal()

    def __init__(self, parent=None, tipo: str = "video"):
        super().__init__(parent)
        self.setObjectName("chipVideo")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_Hover, True)  # para el :hover de la hoja de estilo
        self.setCursor(Qt.PointingHandCursor)
        self._cosa = "audio" if tipo == "audio" else "video"
        if self._cosa == "audio":
            self.setToolTip("Se está exportando tu audio. Podés seguir en otro modo: la exportación sigue.\n"
                            "Tocá acá para ir al modo Audio (ahí está Cancelar).")
        else:
            self.setToolTip("Se está exportando tu video. Podés seguir con tus fotos: la exportación sigue.\n"
                            "Tocá acá para ir al modo Video (ahí está Cancelar).")
        fila = QHBoxLayout(self)
        fila.setContentsMargins(10, 5, 10, 5)
        fila.setSpacing(8)
        icono = QLabel()
        icono.setPixmap(iconos.pixmap("audio-lines", 14, COLOR_AUDIO) if self._cosa == "audio" else
                        iconos.pixmap("film", 14, COLOR_VIDEO))
        icono.setFixedSize(QSize(16, 16))
        fila.addWidget(icono, 0, Qt.AlignVCenter)
        self.texto = QLabel(f"Exportando {self._cosa}…")
        self.texto.setObjectName("textoChipVideo")
        self.texto.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        fila.addWidget(self.texto, 1)
        self.barra = QProgressBar()
        self.barra.setObjectName("barraChipVideo")
        self.barra.setRange(0, 1000)
        self.barra.setTextVisible(False)
        self.barra.setFixedWidth(84)
        fila.addWidget(self.barra, 0, Qt.AlignVCenter)
        self.porcentaje = 0

    def establecer_progreso(self, hechos: int, total: int) -> None:
        fraccion = max(0.0, min(1.0, hechos / max(1, total)))
        self.porcentaje = int(fraccion * 100)
        self.barra.setValue(round(fraccion * 1000))
        self.texto.setText(f"Exportando {self._cosa} · {self.porcentaje} %")

    def reiniciar(self) -> None:
        self.porcentaje = 0
        self.barra.setValue(0)
        self.texto.setText(f"Exportando {self._cosa}…")

    def mouseReleaseEvent(self, evento) -> None:
        if evento.button() == Qt.LeftButton and self.rect().contains(evento.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(evento)


class EtiquetaElidida(QLabel):
    """Etiqueta de una línea que, si no entra, termina en "…" en vez de cortarse a mitad de
    palabra (el texto completo queda en la ayuda). Si entra, se dibuja como cualquier otra
    (y se puede seleccionar, si la etiqueta lo permite)."""

    def __init__(self, texto: str = "", parent=None):
        super().__init__(texto, parent)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(0)

    def paintEvent(self, evento) -> None:
        ancho = max(0, self.contentsRect().width())
        if self.fontMetrics().horizontalAdvance(self.text()) <= ancho:
            if self.toolTip() == self.text():
                self.setToolTip("")
            super().paintEvent(evento)
            return
        self.setToolTip(self.text())
        p = QPainter(self)
        self.style().drawItemText(p, self.contentsRect(), int(self.alignment()), self.palette(), self.isEnabled(),
                                  self.fontMetrics().elidedText(self.text(), Qt.ElideRight, ancho),
                                  self.foregroundRole())
        p.end()
