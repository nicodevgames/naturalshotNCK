"""Panel "Propiedades" del modo Photoshop (NaturalShot Lite): lo de la capa elegida, con números.

Va a la derecha, arriba del panel Capas, como en Photopea:

* **Cualquier capa que se mueve** (imagen, píxeles, texto, forma): X e Y (la esquina de arriba a la
  izquierda de su caja en el lienzo), ancho y alto (su tamaño, con la escala de cada eje; con la
  cadena, en proporción) y rotación.
* **Un grupo o varias capas elegidas:** X e Y de la caja de todas (moverlas); el tamaño se lee.
* **Un relleno** (también el fondo de un documento nuevo): el tipo (color, degradado lineal o
  radial), el color o los colores del degradado (de 2 a 4, con su posición) y el ángulo.
* **Un texto:** fuente, tamaño, color, negrita, cursiva, alineación, interlineado y espaciado (lo
  mismo que la barra de opciones de la herramienta Texto; cambiarlo no corre el ancla del texto).
* **Una forma:** el tipo, el relleno (color o degradado), el trazo y lo de cada tipo (radio, lados,
  puntas, grosor de la línea).
* La foto, el filtro o una capa bloqueada: se ve, pero no se cambia.

Cada número escrito (al Enter o al salir del campo), color elegido o botón tocado es **un paso del
historial**: el panel no cambia nada por su cuenta, manda una función
``documento -> documento`` con su descripción (``cambioPedido``) y el modo Photoshop la aplica.
"""

from __future__ import annotations

import math
from dataclasses import replace
from functools import lru_cache
from typing import Callable, Optional

import numpy as np

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox, QComboBox, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget,
)

from ..motor.documento import TIPOS_CON_TRANSFORMACION, AlmacenImagenes, Documento, caja_capa, trasladar
from .controles import SeccionPlegable
from .opciones_ps import ControlesForma, ControlesTexto, EditorDegradado, relleno_de_tipo
from .selector_color import BotonColor

TIPOS_RELLENO_UI = (("color", "Color"), ("lineal", "Degradado lineal"), ("radial", "Degradado radial"),
                    ("ninguno", "Transparente"))


@lru_cache(maxsize=64)
def dibujo_natural(tipo: str, params) -> Optional[np.ndarray]:
    """El dibujo a escala 1 de una capa texto o forma (RGBA), recordado por sus params (que no
    cambian: son inmutables). None si no se puede dibujar."""
    try:
        if tipo == "forma":
            from ..motor.formas import renderizar_forma
            arr = renderizar_forma(params, 1.0)
        elif tipo == "texto":
            from ..motor.texto import renderizar_texto
            arr = renderizar_texto(params, 1.0)
        else:
            return None
    except (ImportError, ValueError, OSError, MemoryError):
        return None
    arr.flags.writeable = False
    return arr


def tamano_natural(capa, almacen: Optional[AlmacenImagenes]) -> Optional[tuple[int, int]]:
    """(ancho, alto) de la capa a escala 1 (antes de su transformación): la imagen de una capa imagen o
    píxeles, o el dibujo de un texto o una forma. None si no se sabe (falta la imagen)."""
    if capa.tipo in ("imagen", "pixeles"):
        if almacen is None or capa.imagen not in almacen:
            return None
        h, w = almacen.obtener(capa.imagen).shape[:2]
        return int(w), int(h)
    dibujo = dibujo_natural(capa.tipo, capa.params) if capa.tipo in ("texto", "forma") else None
    if dibujo is None:
        return None
    h, w = dibujo.shape[:2]
    return int(w), int(h)


def _numero(minimo: float, maximo: float, sufijo: str, decimales: int = 0) -> QDoubleSpinBox:
    n = QDoubleSpinBox()
    n.setObjectName("valorControl")
    n.setRange(minimo, maximo)
    n.setDecimals(decimales)
    n.setSuffix(sufijo)
    n.setButtonSymbols(QAbstractSpinBox.NoButtons)
    n.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    n.setKeyboardTracking(False)
    n.setMinimumWidth(70)
    return n


class PanelPropiedades(SeccionPlegable):
    """La tarjeta "Propiedades" (ver el módulo)."""

    cambioPedido = Signal(object, str)  # (función documento -> documento, descripción del paso)

    def __init__(self, parent=None):
        super().__init__("Propiedades", "sliders-horizontal", "Posición, tamaño y rotación de la capa elegida, y "
                         "los colores de un relleno", True, parent, con_interruptor=False, plegable=True,
                         color="#a78bfa", subtitulo="De la capa elegida")
        self._doc: Optional[Documento] = None
        self._almacen: Optional[AlmacenImagenes] = None
        self._ids: list[str] = []
        self._cargando = False
        cuerpo = self.capa_cuerpo
        cuerpo.setSpacing(6)

        self.caja_transform = QWidget()
        grilla = QGridLayout(self.caja_transform)
        grilla.setContentsMargins(0, 0, 0, 0)
        grilla.setHorizontalSpacing(6)
        grilla.setVerticalSpacing(4)
        self.numero_x = _numero(-1e6, 1e6, " px")
        self.numero_y = _numero(-1e6, 1e6, " px")
        self.numero_ancho = _numero(1, 1e6, " px")
        self.numero_alto = _numero(1, 1e6, " px")
        self.numero_rotacion = _numero(-360, 360, "°", 1)
        self.boton_cadena = QToolButton()
        self.boton_cadena.setObjectName("botonOjo")
        self.boton_cadena.setCheckable(True)
        self.boton_cadena.setChecked(True)
        self.boton_cadena.setAutoRaise(True)
        self.boton_cadena.setText("⛓")
        self.boton_cadena.setToolTip("Mantener la proporción al cambiar el ancho o el alto")
        etiquetas = []
        for texto, ayuda in (("X", "Borde izquierdo de la capa en el lienzo"),
                             ("Y", "Borde de arriba de la capa en el lienzo"),
                             ("Ancho", "Ancho de la capa (con su escala)"), ("Alto", "Alto de la capa (con su escala)"),
                             ("Rotación", "Giro en grados (positivo: como las agujas del reloj)")):
            e = QLabel(texto)
            e.setObjectName("etiquetaControl")
            e.setToolTip(ayuda)
            etiquetas.append(e)
        grilla.addWidget(etiquetas[0], 0, 0)
        grilla.addWidget(self.numero_x, 0, 1)
        grilla.addWidget(etiquetas[1], 0, 3)
        grilla.addWidget(self.numero_y, 0, 4)
        grilla.addWidget(etiquetas[2], 1, 0)
        grilla.addWidget(self.numero_ancho, 1, 1)
        grilla.addWidget(self.boton_cadena, 1, 2)
        grilla.addWidget(etiquetas[3], 1, 3)
        grilla.addWidget(self.numero_alto, 1, 4)
        grilla.addWidget(etiquetas[4], 2, 0)
        grilla.addWidget(self.numero_rotacion, 2, 1)
        grilla.setColumnStretch(1, 1)
        grilla.setColumnStretch(4, 1)
        cuerpo.addWidget(self.caja_transform)
        self.numero_x.valueChanged.connect(lambda _v: self._mover())
        self.numero_y.valueChanged.connect(lambda _v: self._mover())
        self.numero_ancho.valueChanged.connect(lambda _v: self._escalar("ancho"))
        self.numero_alto.valueChanged.connect(lambda _v: self._escalar("alto"))
        self.numero_rotacion.valueChanged.connect(lambda _v: self._rotar())

        # Texto (lo mismo que la barra de opciones de la herramienta Texto).
        self.controles_texto = ControlesTexto(vertical=True)
        self.controles_texto.cambio.connect(self._cambiar_texto)
        cuerpo.addWidget(self.controles_texto)
        # Forma (lo mismo que la barra de opciones de Formas, más el tipo).
        self.controles_forma = ControlesForma(vertical=True)
        self.controles_forma.cambio.connect(self._cambiar_forma)
        cuerpo.addWidget(self.controles_forma)

        # Relleno: tipo, color o degradado (de 2 a 4 colores con su posición) y ángulo.
        self.caja_relleno = QWidget()
        filas = QVBoxLayout(self.caja_relleno)
        filas.setContentsMargins(0, 0, 0, 0)
        filas.setSpacing(4)
        fila = QHBoxLayout()
        fila.setSpacing(6)
        self.combo_relleno = QComboBox()
        for clave, texto in TIPOS_RELLENO_UI:
            self.combo_relleno.addItem(texto, clave)
        self.combo_relleno.setToolTip("Color liso o degradado")
        self.combo_relleno.currentIndexChanged.connect(lambda _i: self._cambiar_tipo_relleno())
        fila.addWidget(self.combo_relleno, 1)
        self.color_1 = BotonColor((255, 255, 255, 255), titulo="Color del relleno")
        self.color_1.colorCambiado.connect(lambda _c: self._cambiar_color_relleno())
        fila.addWidget(self.color_1)
        filas.addLayout(fila)
        self.editor_degradado = EditorDegradado(con_tipo=False, compacto=True)
        self.editor_degradado.cambiado.connect(self._cambiar_degradado)
        filas.addWidget(self.editor_degradado)
        self.numero_angulo = self.editor_degradado.numero_angulo
        cuerpo.addWidget(self.caja_relleno)

        self.nota = QLabel("")
        self.nota.setObjectName("nota")
        self.nota.setWordWrap(True)
        cuerpo.addWidget(self.nota)
        self.mostrar(None, None, [])

    # ------------------------------------------------------------ mostrar
    def _capa(self):
        if self._doc is None or len(self._ids) != 1:
            return None
        try:
            return self._doc.capa(self._ids[0])
        except KeyError:
            return None

    def mostrar(self, doc: Optional[Documento], almacen: Optional[AlmacenImagenes], ids) -> None:
        """Muestra lo de esas capas (la elegida o varias) en ese documento (None: nada)."""
        self._doc, self._almacen = doc, almacen
        self._ids = [i for i in (ids or []) if doc is not None and any(c.id == i for c in doc.capas)]
        self._cargando = True
        try:
            self._cargar()
        finally:
            self._cargando = False

    def _poner(self, numero: QDoubleSpinBox, valor: Optional[float], habilitado: bool) -> None:
        numero.blockSignals(True)
        numero.setEnabled(habilitado and valor is not None)
        numero.setSpecialValueText("")
        numero.setValue(float(valor) if valor is not None else numero.minimum())
        if valor is None:
            numero.setSpecialValueText("—")
        numero.blockSignals(False)

    def _cargar(self) -> None:
        doc, ids = self._doc, self._ids
        capa = self._capa()
        caja = None
        if doc is not None and ids and self._almacen is not None:
            cajas = [k for i in ids for k in (caja_capa(doc, i, self._almacen),) if k is not None]
            if cajas:
                caja = (min(k[0] for k in cajas), min(k[1] for k in cajas), max(k[2] for k in cajas),
                        max(k[3] for k in cajas))
        varias = len(ids) > 1
        movibles = doc is not None and ids and all(
            doc.capa(i).tipo in TIPOS_CON_TRANSFORMACION + ("grupo",) and not doc.capa(i).bloqueada for i in ids)
        transformable = (capa is not None and capa.tipo in TIPOS_CON_TRANSFORMACION and not capa.bloqueada)
        natural = tamano_natural(capa, self._almacen) if transformable else None
        self.caja_transform.setVisible(capa is None or capa.tipo != "relleno")
        self._poner(self.numero_x, caja[0] if caja else None, bool(movibles))
        self._poner(self.numero_y, caja[1] if caja else None, bool(movibles))
        if transformable and natural is not None:
            t = capa.transform
            self._poner(self.numero_ancho, natural[0] * t.escala, True)
            self._poner(self.numero_alto, natural[1] * t.escala_vertical, True)
            self._poner(self.numero_rotacion, t.rotacion, True)
        else:
            self._poner(self.numero_ancho, (caja[2] - caja[0]) if caja else None, False)
            self._poner(self.numero_alto, (caja[3] - caja[1]) if caja else None, False)
            self._poner(self.numero_rotacion, None, False)
        self.boton_cadena.setEnabled(transformable)
        es_relleno = capa is not None and capa.tipo == "relleno" and capa.params is not None
        self.caja_relleno.setVisible(es_relleno)
        if es_relleno:
            rel = capa.params
            libre = not capa.bloqueada
            self.combo_relleno.blockSignals(True)
            self.combo_relleno.setCurrentIndex(max(0, self.combo_relleno.findData(rel.tipo)))
            self.combo_relleno.blockSignals(False)
            self.combo_relleno.setEnabled(libre)
            degradado = rel.tipo in ("lineal", "radial")
            self.color_1.establecer(rel.colores[0])
            self.color_1.setVisible(rel.tipo == "color")
            self.color_1.setEnabled(libre)
            self.editor_degradado.setVisible(degradado)
            self.editor_degradado.setEnabled(libre)
            if degradado:
                self.editor_degradado.establecer(rel)
        es_texto = capa is not None and capa.tipo == "texto" and capa.params is not None
        self.controles_texto.setVisible(es_texto)
        if es_texto:
            self.controles_texto.mostrar(capa.params)
            self.controles_texto.setEnabled(not capa.bloqueada)
        es_forma = capa is not None and capa.tipo == "forma" and capa.params is not None
        self.controles_forma.setVisible(es_forma)
        if es_forma:
            self.controles_forma.mostrar(capa.params)
            self.controles_forma.setEnabled(not capa.bloqueada)
        if doc is None or not ids:
            nota = "Elegí una capa en el panel Capas."
        elif varias:
            nota = f"{len(ids)} capas elegidas: X e Y mueven todas juntas."
        elif capa is not None and capa.tipo in ("foto", "ajuste_natural"):
            nota = "La foto y el filtro no se mueven ni cambian de tamaño." if capa.tipo == "foto" else \
                "El filtro se elige en Fácil o Editor."
        elif capa is not None and capa.bloqueada:
            nota = "La capa está bloqueada (candado)."
        elif capa is not None and capa.tipo == "grupo":
            nota = "Un grupo se mueve entero (X e Y); su tamaño es el de lo que tiene adentro."
        elif capa is not None and capa.tipo == "relleno":
            nota = "El relleno cubre todo el lienzo."
        elif capa is not None and capa.tipo == "texto":
            nota = "Doble clic sobre el texto (en la vista o en su miniatura) para escribir."
        else:
            nota = ""
        self.nota.setText(nota)
        self.nota.setVisible(bool(nota))

    # ------------------------------------------------------------ cambios
    def _pedir(self, funcion: Callable[[Documento], Documento], descripcion: str) -> None:
        if not self._cargando and self._doc is not None:
            self.cambioPedido.emit(funcion, descripcion)

    def _nombre(self) -> str:
        capa = self._capa()
        return f"«{capa.nombre}»" if capa is not None else f"{len(self._ids)} capas"

    def _mover(self) -> None:
        if self._cargando or self._doc is None or not self._ids or self._almacen is None:
            return
        cajas = [k for i in self._ids for k in (caja_capa(self._doc, i, self._almacen),) if k is not None]
        if not cajas:
            return
        x0, y0 = min(k[0] for k in cajas), min(k[1] for k in cajas)
        dx, dy = self.numero_x.value() - x0, self.numero_y.value() - y0
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            return
        ids = list(self._ids)
        self._pedir(lambda d: trasladar(d, ids, dx, dy), f"Capa {self._nombre()} movida"
                    if len(ids) == 1 else f"{len(ids)} capas movidas")

    def _escalar(self, cual: str) -> None:
        capa = self._capa()
        if self._cargando or capa is None or capa.tipo not in TIPOS_CON_TRANSFORMACION:
            return
        natural = tamano_natural(capa, self._almacen)
        if natural is None:
            return
        t = capa.transform
        sx, sy = t.escala, t.escala_vertical
        if cual == "ancho":
            nuevo = max(1e-3, self.numero_ancho.value() / max(natural[0], 1))
            factor = nuevo / sx
            sx = nuevo
            if self.boton_cadena.isChecked():
                sy *= factor
        else:
            nuevo = max(1e-3, self.numero_alto.value() / max(natural[1], 1))
            factor = nuevo / sy
            sy = nuevo
            if self.boton_cadena.isChecked():
                sx *= factor
        escala_y = None if (t.escala_y is None and math.isclose(sx, sy, rel_tol=1e-9)) else sy
        nueva = replace(t, escala=sx, escala_y=escala_y)
        if nueva == t:
            return
        id_capa = capa.id
        self._pedir(lambda d: d.con_capa(id_capa, transform=nueva), f"Capa {self._nombre()} transformada")

    def _rotar(self) -> None:
        capa = self._capa()
        if self._cargando or capa is None or capa.tipo not in TIPOS_CON_TRANSFORMACION:
            return
        r = (self.numero_rotacion.value() + 180.0) % 360.0 - 180.0
        if math.isclose(r, capa.transform.rotacion, abs_tol=1e-6):
            return
        id_capa, nueva = capa.id, replace(capa.transform, rotacion=r)
        self._pedir(lambda d: d.con_capa(id_capa, transform=nueva), f"Capa {self._nombre()} rotada")

    def _relleno_elegido(self):
        capa = self._capa()
        if self._cargando or capa is None or capa.tipo != "relleno" or capa.params is None or capa.bloqueada:
            return None
        return capa

    def _pedir_relleno(self, capa, nuevo) -> None:
        if nuevo == capa.params:
            return
        id_capa = capa.id
        self._pedir(lambda d: d.con_capa(id_capa, params=nuevo), f"Relleno {self._nombre()} cambiado")

    def _cambiar_tipo_relleno(self) -> None:
        capa = self._relleno_elegido()
        if capa is not None:
            self._pedir_relleno(capa, relleno_de_tipo(capa.params, self.combo_relleno.currentData()))

    def _cambiar_color_relleno(self) -> None:
        capa = self._relleno_elegido()
        if capa is not None:
            rel = capa.params
            self._pedir_relleno(capa, replace(rel, colores=(tuple(self.color_1.color),) + rel.colores[1:]))

    def _cambiar_degradado(self, relleno) -> None:
        capa = self._relleno_elegido()
        if capa is not None:
            tipo = capa.params.tipo if capa.params.tipo in ("lineal", "radial") else "lineal"
            self._pedir_relleno(capa, replace(relleno, tipo=tipo))

    def _cambiar_texto(self, cambios: dict) -> None:
        capa = self._capa()
        if self._cargando or capa is None or capa.tipo != "texto" or capa.bloqueada:
            return
        try:
            nuevos = replace(capa.params, **cambios)
        except (TypeError, ValueError):
            return
        if nuevos == capa.params:
            return
        from .texto_ps import con_params_texto
        id_capa = capa.id
        self._pedir(lambda d: con_params_texto(d, id_capa, nuevos), f"Texto {self._nombre()} cambiado")

    def _cambiar_forma(self, cambios: dict) -> None:
        capa = self._capa()
        if self._cargando or capa is None or capa.tipo != "forma" or capa.bloqueada:
            return
        try:
            nuevos = replace(capa.params, **cambios)
        except (TypeError, ValueError):
            return
        if nuevos == capa.params:
            return
        id_capa = capa.id
        self._pedir(lambda d: d.con_capa(id_capa, params=nuevos), f"Forma {self._nombre()} cambiada")


__all__ = ["BotonColor", "PanelPropiedades", "dibujo_natural", "tamano_natural"]
