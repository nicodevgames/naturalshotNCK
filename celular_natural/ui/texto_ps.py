"""Texto vivo en el modo Photoshop (NaturalShot Lite, Etapa 2, U2): medidas, ancla y edición en el lugar.

**Medidas y ancla.** Una capa ``texto`` se dibuja con ``motor.texto.renderizar_texto``: la imagen está
centrada en la **caja del texto** (el ancho de la línea más ancha, o ``ancho_caja``, por el alto de
los renglones), y la transformación de la capa pone ese centro en el documento. Cuando el texto
cambia (se escribe, cambia el tamaño o la fuente), la caja cambia; para que no "salte", se conserva
fijo el **ancla**: arriba a la izquierda si está alineado a la izquierda, arriba al centro si está
centrado y arriba a la derecha si está a la derecha (como Photoshop). ``con_params_texto`` arma la
capa nueva con eso.

**Edición en el lugar** (``EdicionTexto``): un ``QTextEdit`` transparente (``EditorTexto``) encima de
la vista, del tamaño de la caja a la escala de la vista y con la misma fuente (el mismo archivo, que
se carga en Qt). Lo que se ve es **la capa de verdad**: con cada tecla se vuelve a dibujar (un
documento provisorio de la ventana), con sus estilos; el editor solo pone el cursor (dibujado a
mano) y la selección. Enter es un salto de línea; **Esc**, **Ctrl+Enter** o un clic afuera confirman
(un paso del historial: "Texto nuevo" o "Texto cambiado"). Un texto que queda vacío no se crea (o,
si ya existía, se borra).
"""

from __future__ import annotations

import math
from dataclasses import replace
from functools import lru_cache
from typing import Optional

import numpy as np
from PySide6.QtCore import QEvent, QObject, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QPainter, QPalette, QPen, QTextBlockFormat, QTextCharFormat, QTextCursor,
)
from PySide6.QtWidgets import QFrame, QTextEdit

from ..motor.documento import Capa, Documento, Transformacion, matriz_transformacion
from ..motor.texto import ParamsTexto

FACTOR_ALINEACION = {"izquierda": 0.0, "centro": 0.5, "derecha": 1.0}
ALTO_FIJO = int(QTextBlockFormat.LineHeightTypes.FixedHeight.value)  # setLineHeight pide un int en PySide6


# ---------------------------------------------------------------------------
# Medidas y ancla
# ---------------------------------------------------------------------------

@lru_cache(maxsize=256)
def medidas_texto(p: ParamsTexto) -> tuple[float, float, float]:
    """(ancho, alto, ascenso) de la caja del texto a escala 1, en píxeles del documento (las mismas
    cuentas que ``motor.texto``)."""
    from ..motor import texto as mt
    if mt.MOTOR_TEXTO == "pillow":
        try:
            tam = p.tamano
            cara = mt._elegir_cara(p.fuente, p.negrita, p.cursiva)
            if cara is None:
                ruta, indice, sint_negrita = None, 0, p.negrita
            else:
                ruta, indice, sint_negrita, _c = cara
            fuente = mt._fuente_pillow(ruta, indice, round(tam * 64.0) / 64.0)
            grosor = tam * mt.NEGRITA_SINTETICA if sint_negrita else 0.0
            medir = mt._medidor_pillow(fuente, p.espaciado + 2.0 * grosor)
            ascenso, descenso = fuente.getmetrics()
            armado = mt._armar(p, 1.0, medir, float(ascenso), float(descenso))
            return float(armado.ancho), float(armado.alto), float(ascenso)
        except (AttributeError, OSError, ValueError):
            pass
    from .propiedades_ps import dibujo_natural
    img = dibujo_natural("texto", p)
    if img is None:
        return 0.0, p.tamano * 1.2, p.tamano * 0.9
    margen = p.tamano * 0.6
    return max(0.0, img.shape[1] - 2 * margen), max(1.0, img.shape[0] - 2 * margen), p.tamano * 0.9


def _local_ancla(p: ParamsTexto) -> tuple[float, float]:
    """El ancla en coordenadas de la caja, desde su centro (a escala 1)."""
    ancho, alto, _a = medidas_texto(p)
    return (FACTOR_ALINEACION[p.alineacion] - 0.5) * ancho, -alto / 2.0


def punto_ancla(p: ParamsTexto, t: Transformacion) -> tuple[float, float]:
    """Dónde cae el ancla (ver el módulo) en el documento."""
    m = matriz_transformacion(t, 0, 0)
    lx, ly = _local_ancla(p)
    x, y = m[:, :2] @ np.array([lx, ly]) + m[:, 2]
    return float(x), float(y)


def transformacion_con_ancla(p: ParamsTexto, t: Transformacion, ancla: tuple[float, float]) -> Transformacion:
    """La transformación ``t`` corrida para que el ancla de ``p`` caiga en ``ancla``."""
    m = matriz_transformacion(replace(t, x=0.0, y=0.0), 0, 0)
    lx, ly = _local_ancla(p)
    dx, dy = m[:, :2] @ np.array([lx, ly])
    return replace(t, x=float(ancla[0] - dx), y=float(ancla[1] - dy))


def con_params_texto(doc: Documento, id_capa: str, params: ParamsTexto, nombre: Optional[str] = None) -> Documento:
    """El documento con la capa de texto con esos parámetros, sin que se corra su ancla."""
    capa = doc.capa(id_capa)
    t = capa.transform
    if capa.params is not None:
        t = transformacion_con_ancla(params, t, punto_ancla(capa.params, t))
    cambios = {"params": params, "transform": t}
    if nombre is not None:
        cambios["nombre"] = nombre
    return doc.con_capa(id_capa, **cambios)


def nombre_texto(contenido: str) -> str:
    """El nombre de una capa de texto: su primer renglón, corto (como Photoshop)."""
    primera = next((l.strip() for l in str(contenido).splitlines() if l.strip()), "")
    if not primera:
        return "Texto"
    return primera if len(primera) <= 32 else primera[:31].rstrip() + "…"


def transformacion_nueva(p: ParamsTexto, x: float, y: float, por_linea_base: bool = True) -> Transformacion:
    """La transformación de un texto nuevo cuyo ancla cae en (x, y); con ``por_linea_base``, (x, y)
    es la línea base del primer renglón (como un clic con la herramienta Texto)."""
    _w, _h, ascenso = medidas_texto(p)
    ay = y - ascenso if por_linea_base else y
    return transformacion_con_ancla(p, Transformacion(x, y), (x, ay))


# ---------------------------------------------------------------------------
# Fuente de Qt para el editor
# ---------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _familia_qt(ruta: Optional[str]) -> Optional[str]:
    """Carga el archivo de la fuente en Qt (una vez) y devuelve su familia."""
    if not ruta:
        return None
    try:
        id_fuente = QFontDatabase.addApplicationFont(ruta)
    except Exception:  # noqa: BLE001
        return None
    if id_fuente < 0:
        return None
    familias = QFontDatabase.applicationFontFamilies(id_fuente)
    return familias[0] if familias else None


def fuente_qt(p: ParamsTexto, tam_px: float) -> QFont:
    """Una QFont parecida a la del dibujo (el mismo archivo, si se puede), de ``tam_px`` píxeles."""
    familia = None
    try:
        from ..motor import texto as mt
        cara = mt._elegir_cara(p.fuente, p.negrita, p.cursiva) if mt.MOTOR_TEXTO == "pillow" else None
        if cara is not None:
            familia = _familia_qt(cara[0])
    except Exception:  # noqa: BLE001
        familia = None
    f = QFont(familia or p.fuente)
    f.setPixelSize(max(1, int(round(tam_px))))
    f.setBold(p.negrita)
    f.setItalic(p.cursiva)
    f.setKerning(True)
    return f


# ---------------------------------------------------------------------------
# El editor
# ---------------------------------------------------------------------------

class EditorTexto(QTextEdit):
    """El campo de texto transparente de la edición en el lugar (ver el módulo). Todas las teclas son
    suyas mientras edita (los atajos de la ventana no se disparan); Esc y Ctrl+Enter confirman."""

    def __init__(self, vista, al_confirmar):
        super().__init__(vista)
        self._al_confirmar = al_confirmar
        self.setObjectName("editorTextoPS")
        self.setFrameShape(QFrame.NoFrame)
        self.setAcceptRichText(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.WidgetWidth)
        self.setTabChangesFocus(False)
        self.setCursorWidth(0)  # el cursor lo dibuja ``paintEvent`` (el texto de Qt no se ve)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.viewport().setAutoFillBackground(False)
        # El texto de Qt no se ve (lo que se ve es la capa de verdad): solo la selección y el cursor.
        self.setStyleSheet("QTextEdit#editorTextoPS { background: transparent; border: none; color: rgba(0, 0, 0, 0);"
                           " selection-color: rgba(0, 0, 0, 0); selection-background-color: rgba(80, 140, 255, 110); }")
        pal = self.palette()
        transparente = QColor(0, 0, 0, 0)
        for grupo in (QPalette.Active, QPalette.Inactive):
            pal.setColor(grupo, QPalette.Text, transparente)
            pal.setColor(grupo, QPalette.Base, transparente)
            pal.setColor(grupo, QPalette.Highlight, QColor(80, 140, 255, 110))
            pal.setColor(grupo, QPalette.HighlightedText, transparente)
        self.setPalette(pal)
        self.setCursor(Qt.IBeamCursor)
        self.viewport().setCursor(Qt.IBeamCursor)

    def event(self, e) -> bool:
        if e.type() == QEvent.ShortcutOverride:
            e.accept()  # mientras se escribe, las teclas son del texto (V, X, Supr, Ctrl+J...)
            return True
        return super().event(e)

    def keyPressEvent(self, e) -> None:
        k = e.key()
        if k == Qt.Key_Escape or (k in (Qt.Key_Return, Qt.Key_Enter) and e.modifiers() & Qt.ControlModifier):
            e.accept()
            self._al_confirmar()
            return
        if k in (Qt.Key_Return, Qt.Key_Enter):
            self.textCursor().insertText("\n")  # un salto de línea (no un párrafo con otro formato)
            e.accept()
            return
        super().keyPressEvent(e)

    def paintEvent(self, e) -> None:
        super().paintEvent(e)
        if not self.hasFocus():
            return
        r = self.cursorRect()
        p = QPainter(self.viewport())
        x = r.x() + 0.5
        p.setPen(QPen(QColor(0, 0, 0, 170), 3))
        p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
        p.setPen(QPen(QColor(255, 255, 255), 1.4))
        p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
        p.end()


class EdicionTexto(QObject):
    """Una edición de texto en el lugar (ver el módulo). ``ps``: el ``ModoPhotoshop``.

    ``doc0``: el documento de la foto al empezar (sin la capa, si es nueva); ``capa0``: la capa (para
    una nueva, la que se agrega, con el texto vacío); ``encima_de``: dónde va una capa nueva."""

    def __init__(self, ps, doc0: Documento, capa0: Capa, nueva: bool, encima_de: Optional[str] = None):
        super().__init__(ps)
        self.ps = ps
        self.v = ps.v
        self.imagen = self.v._imagen
        self.doc0 = doc0
        self.id = capa0.id
        self.nueva = nueva
        self.params0: ParamsTexto = capa0.params
        self.params: ParamsTexto = capa0.params
        self.nombre0 = capa0.nombre
        self.nombre_auto = nueva or capa0.nombre == nombre_texto(capa0.params.contenido)
        self.base = doc0.agregar(capa0, encima_de=encima_de) if nueva else doc0
        self.ancla = punto_ancla(capa0.params, capa0.transform)
        self.t0 = capa0.transform
        self.doc = self.base
        self._formateando = False
        self.terminada = False
        self.editor = EditorTexto(self.v.vista, lambda: self.ps.terminar_texto(True))
        self.editor.textChanged.connect(self._al_escribir)
        self._timer_ubicar = QTimer(self, singleShot=True, interval=0)
        self._timer_ubicar.timeout.connect(self.ubicar)

    # ------------------------------------------------------------ ciclo
    def abrir(self, seleccionar: bool = False) -> None:
        self._formateando = True
        self.editor.setPlainText(self.params.contenido)
        self._formateando = False
        self._formatear()
        self.editor.document().clearUndoRedoStacks()
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        if seleccionar:
            cursor.select(QTextCursor.Document)
        self.editor.setTextCursor(cursor)
        self._actualizar_documento()
        self.ubicar()
        self.editor.show()
        self.editor.raise_()
        self.editor.setFocus(Qt.OtherFocusReason)

    def vigente(self) -> bool:
        """Si todavía vale: la misma foto y nadie cambió el documento mientras tanto."""
        v = self.v
        return not self.terminada and v._imagen is self.imagen and v._documento is self.doc0

    def cerrar(self) -> None:
        self.terminada = True
        self._timer_ubicar.stop()
        self.editor.hide()
        self.editor.setParent(None)
        self.editor.deleteLater()

    # ------------------------------------------------------------ cambios
    def _al_escribir(self) -> None:
        if self._formateando or self.terminada:
            return
        if not self.vigente():
            self.ps.terminar_texto(False)
            return
        texto = self.editor.toPlainText().replace(" ", "\n").replace(" ", "\n")
        if texto == self.params.contenido:
            return
        self.params = replace(self.params, contenido=texto)
        self._actualizar_documento()
        self._timer_ubicar.start()

    def cambiar_params(self, cambios: dict) -> None:
        """Un cambio de la barra de opciones (fuente, tamaño...) mientras se edita."""
        if self.terminada:
            return
        try:
            self.params = replace(self.params, **cambios)
        except (TypeError, ValueError):
            return
        self._formatear()
        self._actualizar_documento()
        self.ubicar()

    def _actualizar_documento(self) -> None:
        t = transformacion_con_ancla(self.params, self.t0, self.ancla)
        cambios = {"params": self.params, "transform": t}
        if self.nombre_auto:
            cambios["nombre"] = nombre_texto(self.params.contenido)
        self.doc = self.base.con_capa(self.id, **cambios)
        v = self.v
        v._doc_provisorio = self.doc
        v.solicitar_render()
        v.vista.update()

    def documento_final(self) -> Documento:
        return self.doc

    # ------------------------------------------------------------ geometría
    def _escala(self) -> float:
        t = self.doc.capa(self.id).transform
        return abs(t.escala)

    def _margen(self, zoom: float) -> float:
        tam = self.params.tamano * self._escala() * zoom
        return 4.0 if self.params.ancho_caja is not None else 4.0 + 0.6 * tam

    def caja_documento(self) -> tuple[float, float, float, float]:
        """La caja del texto en el documento (sin rotación): (x0, y0, x1, y1)."""
        t = self.doc.capa(self.id).transform
        ancho, alto, _a = medidas_texto(self.params)
        sx, sy = abs(t.escala), abs(t.escala_vertical)
        return t.x - ancho * sx / 2, t.y - alto * sy / 2, t.x + ancho * sx / 2, t.y + alto * sy / 2

    def _formatear(self) -> None:
        """La fuente, el interlineado y la alineación del editor, como los del dibujo, a la escala de la vista."""
        zoom = self.v.vista.zoom
        e = self.editor
        escala = self._escala() * zoom
        p = self.params
        fuente = fuente_qt(p, p.tamano * escala)
        if p.espaciado:
            fuente.setLetterSpacing(QFont.AbsoluteSpacing, p.espaciado * escala)
        self._formateando = True
        try:
            e.document().setDefaultFont(fuente)
            # La hoja de estilo de la app pone su letra a todos los widgets: la del texto va en el formato.
            letra = QTextCharFormat()
            letra.setFont(fuente, QTextCharFormat.FontPropertiesAll)
            e.document().setDocumentMargin(self._margen(zoom))
            formato = QTextBlockFormat()
            formato.setAlignment({"izquierda": Qt.AlignLeft, "centro": Qt.AlignHCenter,
                                  "derecha": Qt.AlignRight}[p.alineacion])
            formato.setLineHeight(max(1.0, p.interlineado * p.tamano * escala), ALTO_FIJO)
            cursor = QTextCursor(e.document())
            cursor.select(QTextCursor.Document)
            cursor.setBlockFormat(formato)
            cursor.setBlockCharFormat(letra)
            cursor.setCharFormat(letra)
            e.setCurrentCharFormat(letra)
        finally:
            self._formateando = False
        self._zoom_formato = zoom

    def reubicar_luego(self) -> None:
        """Vuelve a poner el editor sobre la caja en el próximo ciclo (la vista se movió o cambió de zoom)."""
        if not self.terminada:
            self._timer_ubicar.start()

    def ubicar(self) -> None:
        """Pone el editor sobre la caja del texto, a la escala de la vista."""
        if self.terminada:
            return
        vista = self.v.vista
        zoom = vista.zoom
        if abs(getattr(self, "_zoom_formato", zoom) - zoom) > 1e-9:
            self._formatear()
        x0, y0, x1, y1 = self.caja_documento()
        a = vista.a_pantalla(QPointF(x0, y0))
        b = vista.a_pantalla(QPointF(x1, y1))
        m = self._margen(zoom)
        rect = QRectF(a, b).adjusted(-m, -m, m, m + 2)
        geo = QRect(int(math.floor(rect.left())), int(math.floor(rect.top())),
                    max(8, int(math.ceil(rect.width()))), max(8, int(math.ceil(rect.height()))))
        if self.editor.geometry() != geo:
            self.editor.setGeometry(geo)

    def rect_pantalla(self) -> Optional[QRectF]:
        """La caja del texto en la vista (para dibujarle el borde)."""
        if self.terminada:
            return None
        vista = self.v.vista
        x0, y0, x1, y1 = self.caja_documento()
        return QRectF(vista.a_pantalla(QPointF(x0, y0)), vista.a_pantalla(QPointF(x1, y1)))


__all__ = ["EdicionTexto", "EditorTexto", "con_params_texto", "fuente_qt", "medidas_texto", "nombre_texto",
           "punto_ancla", "transformacion_con_ancla", "transformacion_nueva"]
