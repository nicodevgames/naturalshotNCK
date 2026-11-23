"""Tarjeta "Mejorar calidad" (sin IA) del modo Video.

Va en la columna de ajustes del modo Video, en el mismo acordeón que "Sonido" y
las secciones del filtro, con el mismo estilo (``SeccionPlegable``). El
interruptor de la cabecera la prende o la apaga (como en las secciones del
filtro: se ve aunque la tarjeta esté cerrada) y adentro están las tres barras,
de 0 a 100 %: **Quitar cuadraditos**, **Nitidez** y **Usar cuadros vecinos**.

Como ``PanelSonido``, no guarda estado propio que importe: muestra un
``AjustesMejora`` (``establecer``) y, cuando se toca algo, emite el ajuste nuevo
con ``ajustesCambiados(nuevo, clave)``. Quien lo usa decide (deshacer, vista
previa, exportación) y vuelve a llamar a ``establecer``. ``clave`` dice qué
control cambió ("activa", "cuadraditos", "nitidez" o "vecinos"), para juntar
en un solo paso de deshacer los movimientos seguidos de un mismo deslizador.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QSizePolicy

from ..motor.mejora_video import AjustesMejora
from .controles import COLOR_SECCION, SUBTITULO_SECCION, ControlDeslizante, SeccionPlegable

NOMBRE = "Mejorar calidad"
COLOR_SECCION.setdefault(NOMBRE, "#818cf8")
# Corto: con el interruptor y la flecha, en la columna de 304 px entran unos 160 px de subtítulo (el
# anterior, "Sin IA: menos cuadraditos, más nitidez", medía 186 y ensanchaba toda la columna).
SUBTITULO_SECCION.setdefault(NOMBRE, "Sin IA: cuadraditos y nitidez")
AYUDA = ("No es IA: limpia los cuadraditos de la compresión, enfoca los bordes y junta detalle de los cuadros "
         "vecinos. Un video chico queda como un buen 720p, no como un 4K.")
DESCRIPCION = ("Mejorar calidad (sin IA): para videos chicos o muy comprimidos. Con la mejora prendida, al exportar "
               "720p y 1080p también agrandan el video. Se ve al pausar y exportar tarda más.")
# Barras: (campo de AjustesMejora, nombre, ayuda).
BARRAS = (
    ("cuadraditos", "Quitar cuadraditos",
     "Borra los cuadraditos y el \"mosquito\" que deja la compresión alrededor de los bordes. Más alto limpia "
     "más, pero puede alisar algún detalle fino. La textura (pasto, pelo, tela) se respeta."),
    ("nitidez", "Nitidez",
     "Enfoca solo los bordes, sin halos y sin realzar el ruido de las zonas lisas."),
    ("vecinos", "Usar cuadros vecinos",
     "Junta detalle de los dos cuadros de antes y los dos de después, alineados con el movimiento: recupera "
     "detalle real y baja el ruido. 0 % no los usa (es más rápido). Nunca usa cuadros del otro lado de un "
     "corte ni de otra escena."),
)


def no_ensanchar(tarjeta: SeccionPlegable) -> None:
    """Que el título y el subtítulo de la cabecera nunca ensanchen la tarjeta: si no entran, se
    achican (la descripción completa está en la ayuda de la cabecera). Así la tarjeta se adapta al
    ancho de la columna, como las secciones del filtro."""
    for etiqueta in tarjeta.cabecera.findChildren(QLabel):
        if etiqueta.objectName() in ("tituloCaja", "subtituloCaja"):
            etiqueta.setMinimumWidth(1)
            etiqueta.setSizePolicy(QSizePolicy.Ignored, etiqueta.sizePolicy().verticalPolicy())


class PanelMejora(SeccionPlegable):
    """La tarjeta "Mejorar calidad" (ver el docstring del módulo)."""

    ajustesCambiados = Signal(object, str)   # AjustesMejora nuevo y qué control cambió

    def __init__(self, parent=None, abierta: bool = False):
        super().__init__(NOMBRE, "sparkles", DESCRIPCION, abierta, parent, con_interruptor=True)
        no_ensanchar(self)
        self._ajustes = AjustesMejora()
        self.interruptor.setToolTip("Prender o apagar \"Mejorar calidad\" (sin IA). Apagada, el video sale como "
                                    "siempre.")
        self.interruptor.toggled.connect(lambda v: self._emitir(self._ajustes.con(activa=bool(v)), "activa"))
        capa = self.capa_cuerpo

        self.ayuda = QLabel(AYUDA)
        self.ayuda.setObjectName("nota")
        self.ayuda.setWordWrap(True)
        capa.addWidget(self.ayuda)

        self.barras: dict[str, ControlDeslizante] = {}
        for campo, nombre, ayuda in BARRAS:
            barra = ControlDeslizante(campo, nombre, 0, 100, ayuda)
            barra.numero.setSuffix(" %")
            barra.numero.setFixedWidth(56)
            barra.slider.setPageStep(10)
            barra.establecer(round(getattr(self._ajustes, campo) * 100), 50)
            barra.valorCambiado.connect(lambda c, v: self._emitir(self._ajustes.con(**{c: v / 100.0}), c))
            self.barras[campo] = barra
            capa.addWidget(barra)
        self.cuadraditos = self.barras["cuadraditos"]
        self.nitidez = self.barras["nitidez"]
        self.vecinos = self.barras["vecinos"]

        # Qué pasa con la mejora ahora (apagada, a qué tamaño se exporta): lo completa el editor.
        self.nota = QLabel("")
        self.nota.setObjectName("nota")
        self.nota.setWordWrap(True)
        capa.addWidget(self.nota)
        self._actualizar()

    # ------------------------------------------------------------ datos
    @property
    def ajustes(self) -> AjustesMejora:
        return self._ajustes

    def establecer(self, ajustes: AjustesMejora, nota: str = "") -> None:
        """Muestra estos ajustes, sin emitir nada. ``nota``: una línea sobre lo que pasa ahora (por
        ejemplo, a qué tamaño se exporta); si no viene, se dice lo básico."""
        self._ajustes = ajustes
        self.interruptor.blockSignals(True)
        self.interruptor.setChecked(ajustes.activa)
        self.interruptor.blockSignals(False)
        self.interruptor.update()
        for campo, barra in self.barras.items():
            barra.establecer(round(getattr(ajustes, campo) * 100), 50)
        self._actualizar(nota)

    def _emitir(self, nuevo: AjustesMejora, clave: str) -> None:
        if nuevo != self._ajustes:
            self.ajustesCambiados.emit(nuevo, clave)

    def _actualizar(self, nota: str = "") -> None:
        activa = self._ajustes.activa
        for barra in self.barras.values():
            barra.setEnabled(activa)
        if not activa:
            nota = "Apagada: prendela con el interruptor de arriba. El video sale como siempre."
        elif not nota:
            nota = "Se ve al pausar (al reproducir, sin la mejora). Exportar tarda más."
        self.nota.setText(nota)


__all__ = ["PanelMejora", "AYUDA"]
