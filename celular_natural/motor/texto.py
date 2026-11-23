"""Texto a RGBA (capas de texto vivo de NaturalShot Lite). Sin Qt, salvo el respaldo.

Motor
-----
FreeType de **Pillow** (``ImageFont.truetype``), con antialias, con las fuentes instaladas
en el sistema (``C:\\Windows\\Fonts``: son de Windows, no del usuario). Si Pillow no tiene
FreeType (``MOTOR_TEXTO == "qt"``), se usa QPainter sobre QImage, que funciona en hilos y
sin pantalla (necesita una QGuiApplication, que se crea si no hay).

Familias
--------
Se leen todas las caras (.ttf, .otf y .ttc) y se agrupan por el nombre tipográfico que da
FreeType. Regular, Bold, Italic y Bold Italic son la misma familia con ``negrita`` y
``cursiva``; los otros pesos y anchos son una familia aparte con el estilo en el nombre
("Arial Black", "Arial Narrow", "Segoe UI Semibold", "Calibri Light"), como en Word.
Si falta el archivo de negrita o de cursiva, se **sintetizan**: la negrita engorda el trazo
(``NEGRITA_SINTETICA`` × tamaño de cada lado, y separa las letras lo mismo para que no se
peguen) y la cursiva inclina 12°. Una familia que no existe (o
escrita con otras mayúsculas) vuelve a Arial; sin Arial, a la fuente de Pillow.

Medidas y armado
----------------
Todo en píxeles del documento (× ``escala``): ``tamano`` es el tamaño de la fuente en px
(el "em"), ``interlineado`` multiplica el tamaño para la distancia entre líneas base
(1,2 = el "automático" de Photoshop) y ``espaciado`` son px que se agregan **entre** letras
(no después de la última). ``ancho_caja`` corta las líneas por palabras (y una palabra que
no entra, por letras); los saltos de línea del contenido siempre cortan.

La **caja del texto** va del borde izquierdo de la línea más ancha (o de la caja, si hay
``ancho_caja``) al derecho, y de la altura de las mayúsculas con acentos de la primera línea
(``ascent``) al fondo de las letras con cola de la última (``descent``). La imagen está
**centrada en esa caja** y la cubre; si la tinta se sale (letras que sobresalen, cursiva),
la imagen crece lo mismo de los dos lados para que haya 1 px libre alrededor de la tinta.
Así el centro de la capa no salta al escribir. Los lados de la imagen son pares.

``renderizar_texto`` devuelve RGBA uint8 sin premultiplicar: el RGB es el color en toda la
imagen y el alfa es la cobertura × el alfa del color.
"""

from __future__ import annotations

import math
import numbers
import os
import threading
from dataclasses import dataclass, fields
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, features

from .formas import Color, color_rgba

CARPETA_FUENTES = Path(os.environ.get("WINDIR") or r"C:\Windows") / "Fonts"
EXTENSIONES_FUENTE = (".ttf", ".otf", ".ttc")
FUENTE_RESPALDO = "Arial"
ALINEACIONES = ("izquierda", "centro", "derecha")
NEGRITA_SINTETICA = 0.022                        # grosor extra del trazo, por px de tamaño
INCLINACION_SINTETICA = math.tan(math.radians(12.0))
TAMANO_MAX = 4000.0                              # px de la fuente ya escalada, como mucho
MOTOR_TEXTO = "pillow" if features.check("freetype2") else "qt"

_ESTILOS_NORMALES = {"regular", "normal", "book", "roman", "plain", "standard"}
_CURSIVAS = {"italic", "oblique", "cursiva", "kursiv"}


# ---------------------------------------------------------------------------
# Parámetros
# ---------------------------------------------------------------------------

def _real(valor, nombre: str) -> float:
    if (isinstance(valor, (str, bytes, bool, np.bool_)) or valor is None
            or not isinstance(valor, (numbers.Real, np.number))):
        raise ValueError(f"{nombre} tiene que ser un número (llegó {valor!r}).")
    v = float(valor)
    if not math.isfinite(v):
        raise ValueError(f"{nombre} tiene que ser un número finito (llegó {valor!r}).")
    return v


def _positivo(valor, nombre: str) -> float:
    v = _real(valor, nombre)
    if v <= 0:
        raise ValueError(f"{nombre} tiene que ser mayor que 0 (llegó {valor!r}).")
    return v


def _booleano(valor, nombre: str) -> bool:
    if not isinstance(valor, (bool, np.bool_)):
        raise ValueError(f"{nombre} tiene que ser verdadero o falso (llegó {valor!r}).")
    return bool(valor)


@dataclass(frozen=True)
class ParamsTexto:
    """Un texto vivo (ver el módulo). Inmutable y hasheable (sirve de clave de caché).

    contenido      el texto, con saltos de línea.
    fuente         nombre de familia (de ``familias_disponibles``); si no existe, Arial.
    tamano         px del documento (> 0).
    color          RGBA 0..255.
    negrita, cursiva
    alineacion     "izquierda" | "centro" | "derecha".
    interlineado   × tamano entre líneas base (> 0).
    espaciado      px entre letras (puede ser negativo).
    ancho_caja     px; con valor (> 0), corta las líneas a ese ancho.
    """

    contenido: str = "Texto"
    fuente: str = "Arial"
    tamano: float = 72.0
    color: Color = (255, 255, 255, 255)
    negrita: bool = False
    cursiva: bool = False
    alineacion: str = "izquierda"
    interlineado: float = 1.2
    espaciado: float = 0.0
    ancho_caja: Optional[float] = None

    def __post_init__(self):
        if not isinstance(self.contenido, str):
            raise ValueError(f"El contenido tiene que ser un texto (llegó {self.contenido!r}).")
        if not isinstance(self.fuente, str) or not self.fuente.strip():
            raise ValueError(f"La fuente tiene que ser un nombre (llegó {self.fuente!r}).")
        object.__setattr__(self, "tamano", _positivo(self.tamano, "tamano"))
        object.__setattr__(self, "color", color_rgba(self.color, "color"))
        object.__setattr__(self, "negrita", _booleano(self.negrita, "negrita"))
        object.__setattr__(self, "cursiva", _booleano(self.cursiva, "cursiva"))
        if self.alineacion not in ALINEACIONES:
            raise ValueError(f"Alineación desconocida: {self.alineacion!r}.")
        object.__setattr__(self, "interlineado", _positivo(self.interlineado, "interlineado"))
        object.__setattr__(self, "espaciado", _real(self.espaciado, "espaciado"))
        if self.ancho_caja is not None:
            object.__setattr__(self, "ancho_caja", _positivo(self.ancho_caja, "ancho_caja"))

    def como_dict(self) -> dict:
        """Para JSON: solo tipos básicos."""
        d = {f.name: getattr(self, f.name) for f in fields(self)}
        d["color"] = list(self.color)
        return d

    @staticmethod
    def desde_dict(d) -> "ParamsTexto":
        """El de ``como_dict``. Lo que falta toma el valor por defecto y lo desconocido se
        ignora; lo que no vale: ``ValueError``."""
        if isinstance(d, ParamsTexto):
            return d
        if not isinstance(d, dict):
            raise ValueError(f"ParamsTexto inválido: se esperaba un diccionario (llegó {type(d).__name__}).")
        try:
            return ParamsTexto(**{f.name: d[f.name] for f in fields(ParamsTexto) if f.name in d})
        except TypeError as error:
            raise ValueError(f"ParamsTexto inválido: {error}") from error


# ---------------------------------------------------------------------------
# Familias (Pillow)
# ---------------------------------------------------------------------------

def _clasificar(familia: str, estilo: str) -> tuple[str, bool, bool]:
    """(familia que se muestra, negrita, cursiva) de una cara."""
    palabras = estilo.replace("-", " ").split()
    cursiva = any(p.casefold() in _CURSIVAS for p in palabras)
    negrita = any(p.casefold() == "bold" for p in palabras)
    resto = [p for p in palabras if p.casefold() not in _CURSIVAS | _ESTILOS_NORMALES | {"bold"}]
    nombre = " ".join([familia.strip()] + resto)
    return nombre, negrita, cursiva


_cerrojo_catalogo = threading.Lock()
_cerrojo_render = threading.Lock()


@lru_cache(maxsize=1)
def _catalogo() -> dict[str, tuple[str, dict[tuple[bool, bool], tuple[str, int]]]]:
    """{familia en minúsculas: (nombre, {(negrita, cursiva): (archivo, índice)})}. Se arma una
    vez (unos 60 ms con las fuentes de Windows)."""
    catalogo: dict[str, tuple[str, dict]] = {}
    if MOTOR_TEXTO != "pillow" or not CARPETA_FUENTES.is_dir():
        return catalogo
    try:
        archivos = sorted(CARPETA_FUENTES.iterdir(), key=lambda f: f.name.casefold())
    except OSError:
        return catalogo
    for archivo in archivos:
        ext = archivo.suffix.casefold()
        if ext not in EXTENSIONES_FUENTE:
            continue
        for indice in range(64 if ext == ".ttc" else 1):
            try:
                cara = ImageFont.truetype(str(archivo), 16, index=indice)
                familia, estilo = cara.getname()
            except (OSError, ValueError):
                break
            if not familia:
                continue
            nombre, negrita, cursiva = _clasificar(familia, estilo or "")
            entrada = catalogo.setdefault(nombre.casefold(), (nombre, {}))
            entrada[1].setdefault((negrita, cursiva), (str(archivo), indice))
    return catalogo


def familias_disponibles() -> list[str]:
    """Los nombres de las familias instaladas, ordenados (sin importar mayúsculas)."""
    if MOTOR_TEXTO == "qt":
        _app_qt()
        from PySide6.QtGui import QFontDatabase
        nombres = {f.casefold(): f for f in QFontDatabase.families()}
        return sorted(nombres.values(), key=str.casefold)
    with _cerrojo_catalogo:
        catalogo = _catalogo()
    return sorted((nombre for nombre, _ in catalogo.values()), key=str.casefold)


def _elegir_cara(familia: str, negrita: bool, cursiva: bool):
    """(archivo, índice, negrita sintética, cursiva sintética), o None si no hay ninguna fuente
    (ni la pedida ni Arial)."""
    with _cerrojo_catalogo:
        catalogo = _catalogo()
    entrada = catalogo.get(familia.strip().casefold()) or catalogo.get(FUENTE_RESPALDO.casefold())
    if entrada is None:
        return None
    caras = entrada[1]
    preferencias = [(negrita, cursiva), (negrita, False), (False, cursiva), (False, False)]
    for clave in preferencias + list(caras):
        if clave in caras:
            ruta, indice = caras[clave]
            return ruta, indice, negrita and not clave[0], cursiva and not clave[1]
    return None


@lru_cache(maxsize=48)
def _fuente_pillow(ruta: Optional[str], indice: int, tamano: float):
    if ruta is None:
        return ImageFont.load_default(size=tamano)
    return ImageFont.truetype(ruta, tamano, index=indice, layout_engine=ImageFont.Layout.BASIC)


# ---------------------------------------------------------------------------
# Armado (común a los dos motores)
# ---------------------------------------------------------------------------

def _cortar(contenido: str, medir: Callable[[str], float], maximo: Optional[float]) -> list[str]:
    """Las líneas: por los saltos del contenido y, con ``maximo``, por palabras (una palabra
    más ancha que la caja se parte por letras)."""
    parrafos = contenido.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if maximo is None:
        return parrafos
    lineas: list[str] = []
    for parrafo in parrafos:
        linea = ""
        for palabra in parrafo.split(" "):
            prueba = palabra if not linea else f"{linea} {palabra}"
            if medir(prueba.rstrip(" ")) <= maximo:
                linea = prueba
                continue
            if linea:
                lineas.append(linea)
            while len(palabra) > 1 and medir(palabra) > maximo:
                lo, hi = 1, len(palabra) - 1           # el prefijo más largo que entra (al menos 1 letra)
                while lo < hi:
                    medio = (lo + hi + 1) // 2
                    if medir(palabra[:medio]) <= maximo:
                        lo = medio
                    else:
                        hi = medio - 1
                lineas.append(palabra[:lo])
                palabra = palabra[lo:]
            linea = palabra
        lineas.append(linea)
    return lineas


@dataclass
class _Armado:
    lineas: list[str]
    x: list[float]          # borde izquierdo de cada línea, desde el de la caja
    base: list[float]       # línea base de cada línea, desde el borde de arriba de la caja
    ancho: float            # de la caja
    alto: float


def _armar(p: ParamsTexto, escala: float, medir: Callable[[str], float], ascenso: float, descenso: float) -> _Armado:
    maximo = p.ancho_caja * escala if p.ancho_caja is not None else None
    lineas = _cortar(p.contenido, medir, maximo)
    anchos = [medir(l.rstrip(" ")) for l in lineas]
    ancho = maximo if maximo is not None else max(anchos, default=0.0)
    paso = p.interlineado * p.tamano * escala
    factor = {"izquierda": 0.0, "centro": 0.5, "derecha": 1.0}[p.alineacion]
    xs = [(ancho - a) * factor for a in anchos]
    bases = [ascenso + i * paso for i in range(len(lineas))]
    alto = ascenso + descenso + paso * (len(lineas) - 1)
    return _Armado(lineas, xs, bases, max(ancho, 0.0), alto)


def _lienzo(armado: _Armado, margen: float, inclinacion: float) -> tuple[int, int, int, int, float, float]:
    """(ancho, alto, cx, cy, ox, oy) del lienzo de dibujo: el centro de la caja cae en (cx, cy),
    enteros, y (ox, oy) es la esquina de la caja."""
    mw, mh = armado.ancho / 2.0, armado.alto / 2.0
    pad_y = int(math.ceil(margen))
    pad_x = int(math.ceil(margen + inclinacion * (mh + margen)))
    cx = pad_x + int(math.ceil(mw))
    cy = pad_y + int(math.ceil(mh))
    return 2 * cx, 2 * cy, cx, cy, cx - mw, cy - mh


def _inclinar(mascara: np.ndarray, cy: int, inclinacion: float) -> np.ndarray:
    """Cursiva sintética: corre cada fila a la derecha según su altura sobre el centro."""
    alto, ancho = mascara.shape
    m = np.float32([[1.0, inclinacion, -inclinacion * (cy - 0.5)], [0.0, 1.0, 0.0]])
    return cv2.warpAffine(mascara, m, (ancho, alto), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def _recortar(mascara: np.ndarray, armado: _Armado, cx: int, cy: int, color: Color) -> np.ndarray:
    """Recorta la máscara centrada en (cx, cy): cubre la caja y deja 1 px libre alrededor de la
    tinta. Devuelve el RGBA con el color."""
    hx = max(1, int(math.ceil(armado.ancho / 2.0 - 1e-9)))
    hy = max(1, int(math.ceil(armado.alto / 2.0 - 1e-9)))
    filas = np.flatnonzero(mascara.any(axis=1))
    if len(filas):
        cols = np.flatnonzero(mascara.any(axis=0))
        hx = max(hx, cx - int(cols[0]) + 1, int(cols[-1]) + 2 - cx)
        hy = max(hy, cy - int(filas[0]) + 1, int(filas[-1]) + 2 - cy)
    hx, hy = min(hx, cx), min(hy, cy)
    recorte = mascara[cy - hy:cy + hy, cx - hx:cx + hx]
    out = np.empty((2 * hy, 2 * hx, 4), np.uint8)
    out[..., :3] = color[:3]
    out[..., 3] = recorte if color[3] == 255 else cv2.convertScaleAbs(recorte, alpha=color[3] / 255.0)
    return out


# ---------------------------------------------------------------------------
# Render con Pillow
# ---------------------------------------------------------------------------

def _medidor_pillow(fuente, espaciado: float) -> Callable[[str], float]:
    def medir(s: str) -> float:
        if not s:
            return 0.0
        return float(fuente.getlength(s)) + espaciado * (len(s) - 1)
    return medir


def _renderizar_pillow(p: ParamsTexto, escala: float) -> np.ndarray:
    tam = p.tamano * escala
    cara = _elegir_cara(p.fuente, p.negrita, p.cursiva)
    if cara is None:
        ruta, indice, sint_negrita, sint_cursiva = None, 0, p.negrita, p.cursiva
    else:
        ruta, indice, sint_negrita, sint_cursiva = cara
    fuente = _fuente_pillow(ruta, indice, round(tam * 64.0) / 64.0)
    grosor = tam * NEGRITA_SINTETICA if sint_negrita else 0.0
    inclinacion = INCLINACION_SINTETICA if sint_cursiva else 0.0
    # la negrita sintética engorda cada letra `grosor` por lado: se corren para que no se peguen
    espaciado = p.espaciado * escala + 2.0 * grosor
    medir = _medidor_pillow(fuente, espaciado)
    ascenso, descenso = fuente.getmetrics()
    armado = _armar(p, escala, medir, float(ascenso), float(descenso))
    margen = tam * 0.6 + grosor + 2.0
    ancho, alto, cx, cy, ox, oy = _lienzo(armado, margen, inclinacion)
    imagen = Image.new("L", (ancho, alto), 0)
    dibujo = ImageDraw.Draw(imagen)
    extra = {"stroke_width": grosor, "stroke_fill": 255} if grosor else {}
    for linea, x, base in zip(armado.lineas, armado.x, armado.base):
        if not linea.strip():
            continue
        x0, y0 = ox + x, oy + base
        if espaciado == 0.0:
            dibujo.text((x0, y0), linea, font=fuente, fill=255, anchor="ls", **extra)
            continue
        for i, letra in enumerate(linea):              # letra por letra, con el interletraje de cada par
            if not letra.isspace():
                dibujo.text((x0, y0), letra, font=fuente, fill=255, anchor="ls", **extra)
            if i + 1 < len(linea):
                par = letra + linea[i + 1]
                x0 += float(fuente.getlength(par)) - float(fuente.getlength(linea[i + 1])) + espaciado
    mascara = np.asarray(imagen)
    if inclinacion:
        mascara = _inclinar(mascara, cy, inclinacion)
    return _recortar(mascara, armado, cx, cy, p.color)


# ---------------------------------------------------------------------------
# Respaldo con Qt (si Pillow no tiene FreeType)
# ---------------------------------------------------------------------------

_app = None


_fuentes_qt_cargadas = False


def _app_qt():
    """La QGuiApplication (la crea si no hay: QFont la necesita). Con la plataforma
    "offscreen", Qt no ve las fuentes del sistema: si falta Arial, se cargan una vez las de
    ``CARPETA_FUENTES``."""
    global _app, _fuentes_qt_cargadas
    from PySide6.QtGui import QFontDatabase, QGuiApplication
    app = QGuiApplication.instance()
    if app is None:
        _app = app = QGuiApplication(["naturalshot"])
    with _cerrojo_catalogo:
        if not _fuentes_qt_cargadas:
            _fuentes_qt_cargadas = True
            familias = {f.casefold() for f in QFontDatabase.families()}
            if FUENTE_RESPALDO.casefold() not in familias and CARPETA_FUENTES.is_dir():
                for archivo in sorted(CARPETA_FUENTES.iterdir()):
                    if archivo.suffix.casefold() in EXTENSIONES_FUENTE:
                        QFontDatabase.addApplicationFont(str(archivo))
    return app


def _renderizar_qt(p: ParamsTexto, escala: float) -> np.ndarray:
    """El mismo armado con QPainter sobre QImage (a 72 ppp, así un punto es un píxel)."""
    _app_qt()
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QImage, QPainter

    tam = p.tamano * escala
    espaciado = p.espaciado * escala
    familias = {f.casefold(): f for f in QFontDatabase.families()}
    familia = familias.get(p.fuente.strip().casefold()) or familias.get(FUENTE_RESPALDO.casefold()) or p.fuente
    fuente = QFont(familia)
    fuente.setPointSizeF(tam)
    fuente.setBold(p.negrita)
    fuente.setItalic(p.cursiva)
    fuente.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, espaciado)
    ppm = int(round(72 / 0.0254))
    muestra = QImage(1, 1, QImage.Format.Format_ARGB32_Premultiplied)
    muestra.setDotsPerMeterX(ppm)
    muestra.setDotsPerMeterY(ppm)
    metricas = QFontMetricsF(fuente, muestra)

    def medir(s: str) -> float:
        return metricas.horizontalAdvance(s) - espaciado if s else 0.0   # Qt suma el espaciado también tras la última

    armado = _armar(p, escala, medir, metricas.ascent(), metricas.descent())
    ancho, alto, cx, cy, ox, oy = _lienzo(armado, tam * 0.6 + 2.0, INCLINACION_SINTETICA if p.cursiva else 0.0)
    imagen = QImage(ancho, alto, QImage.Format.Format_ARGB32_Premultiplied)
    imagen.setDotsPerMeterX(ppm)
    imagen.setDotsPerMeterY(ppm)
    imagen.fill(0)
    pintor = QPainter(imagen)
    pintor.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pintor.setFont(fuente)
    pintor.setPen(QColor(255, 255, 255, 255))
    for linea, x, base in zip(armado.lineas, armado.x, armado.base):
        if linea.strip():
            pintor.drawText(QPointF(ox + x, oy + base), linea)
    pintor.end()
    datos = np.frombuffer(imagen.constBits(), np.uint8, count=imagen.sizeInBytes())
    bgra = datos.reshape(alto, imagen.bytesPerLine())[:, :ancho * 4].reshape(alto, ancho, 4)
    mascara = np.ascontiguousarray(bgra[..., 3])
    return _recortar(mascara, armado, cx, cy, p.color)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def renderizar_texto(p: ParamsTexto, escala: float = 1.0) -> np.ndarray:
    """RGBA uint8 del texto, centrado en su caja (ver el módulo).

    ``escala``: píxeles del render por píxel del documento (> 0). ``ValueError`` si los
    parámetros no valen o la fuente escalada pasa ``TAMANO_MAX`` px.
    """
    if not isinstance(p, ParamsTexto):
        raise ValueError(f"Se esperaba ParamsTexto (llegó {p!r}).")
    escala = _positivo(escala, "escala")
    if p.tamano * escala > TAMANO_MAX:
        raise ValueError(f"El texto a escala {escala:g} es demasiado grande ({p.tamano * escala:.0f} px).")
    if MOTOR_TEXTO == "qt":
        return _renderizar_qt(p, escala)
    with _cerrojo_render:          # las caras de FreeType (cacheadas) no se usan de a dos hilos
        return _renderizar_pillow(p, escala)


__all__ = ["ALINEACIONES", "CARPETA_FUENTES", "FUENTE_RESPALDO", "MOTOR_TEXTO", "ParamsTexto",
           "familias_disponibles", "renderizar_texto"]
