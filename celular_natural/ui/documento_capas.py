"""El documento de capas de cada foto, del lado de la ventana. Sin Qt.

El motor de capas (``motor/documento.py``) no sabe nada de la edición de hoy: recibe la foto
base ya hecha. Acá está lo que la ventana necesita para unir las dos cosas:

Tamaño y marco del documento
----------------------------
El documento de una foto mide lo mismo que la foto que entra al filtro (``ventana._fuente``):
la original con la geometría (girar, voltear, enderezar) y el recorte. Las capas se ubican en
píxeles de ese documento. Cuando cambia la geometría o el recorte, cambia el marco: para que
cada capa siga sobre el mismo lugar de la foto, ``convertir_documento`` la lleva del marco
viejo al nuevo con la misma matriz que usa la edición de hoy (``motor.edicion.matriz_cambio``):

* la posición de cada capa imagen pasa por la matriz;
* el giro y el espejo de la matriz se suman a la rotación y al volteo de la capa (y su escala,
  si la hubiera, a la de la capa);
* cada máscara se vuelve a muestrear con ``cv2.warpAffine`` al tamaño nuevo (lo que queda
  afuera de la foto vieja repite el borde).

Documentos sin foto
-------------------
"Archivo › Nuevo" crea un ``Documento.nuevo_lienzo`` (la base es un fondo de relleno). En la tira
es una entrada más, con una "ruta" que no es un archivo (``EXTENSION_DOCUMENTO``, en la carpeta de
la app); su "foto" es una imagen lisa del tamaño del documento, hecha en memoria
(``imagen_documento``), que no entra a la composición.

Documento "trivial"
-------------------
Solo la foto y el ajuste "Celular natural", con todo por defecto (visibles, al 100 %, normal,
sin máscara ni candado y con sus nombres de siempre). Es lo mismo que no tener capas: la
ventana **no lo guarda** en el estado de la foto (``estado["documento"]`` falta), así los
estados, historiales y sesiones de antes siguen siendo iguales a los de ahora, y la vista y la
exportación son exactamente las de antes (``es_trivial``).

Máscaras
--------
``pintar_mascara`` suma ("mostrar") o resta ("ocultar") una zona (rectángulo, elipse, lazo o
pincel, como las de los efectos) a la máscara de una capa, en el tamaño del documento.

El estado del editor en JSON (para el proyecto ``.nslite``)
-----------------------------------------------------------
``estado_a_json`` y ``estado_desde_json``: el dict de estado de la ventana (preset, ajustes,
efectos con sus zonas, recorte, geometría, montaje, borrados y fondo) con etiquetas para lo
que JSON no tiene: ``{"$tupla": [...]}``, ``{"$bytes": "<base64>"}`` (las máscaras de las
zonas, que ya son PNG) y ``{"$clase": "Zona", "campos": {...}}`` (solo las clases de
``sesion.CLASES``; al leer, cada una se vuelve a armar con sus campos actuales, como la
sesión). Nunca se usa pickle ni se ejecuta nada del archivo.
"""

from __future__ import annotations

import base64
import dataclasses
import math
import os
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from ..motor.documento import (
    ID_AJUSTE, ID_FOTO, NOMBRE_AJUSTE, NOMBRE_FOTO, TIPOS_CON_TRANSFORMACION, AlmacenImagenes, Capa, Documento,
    Transformacion,
)
from ..motor.estilos import EstilosCapa
from ..motor.edicion import matriz_cambio
from ..motor.geometria import Geometria, tamano_resultante
from ..motor.zonas import Recorte, Zona, mascara_zona

VERSION_ESTADO = 1  # del estado del editor dentro del "extra" de un .nslite
MODOS_MASCARA = ("mostrar", "ocultar")


# ---------------------------------------------------------------------------
# Documento por defecto y "trivial"
# ---------------------------------------------------------------------------

def documento_nuevo(ancho: int, alto: int) -> Documento:
    """Foto + ajuste "Celular natural", del tamaño de la foto que entra al filtro."""
    return Documento.nuevo(max(1, int(ancho)), max(1, int(alto)))


def es_trivial(doc: Optional[Documento]) -> bool:
    """Si el documento equivale a no tener capas (ver el módulo). None también lo es."""
    if doc is None:
        return True
    if len(doc.capas) != 2:
        return False
    foto, ajuste = doc.capas
    return (foto == Capa(ID_FOTO, "foto", NOMBRE_FOTO)
            and ajuste == Capa(ID_AJUSTE, "ajuste_natural", NOMBRE_AJUSTE))


def tiene_capas_extra(doc: Optional[Documento]) -> bool:
    """Si hay capas además de la base y el filtro (lo que Fácil avisa como "capas")."""
    return doc is not None and any(c.tipo not in ("foto", "ajuste_natural") for c in doc.capas[1:])


# ---------------------------------------------------------------------------
# Documentos sin foto ("Archivo › Nuevo")
# ---------------------------------------------------------------------------

EXTENSION_DOCUMENTO = ".nsdoc"  # la "ruta" de un documento nuevo en la tira: no es un archivo
_NO_VALEN_EN_NOMBRES = frozenset('<>:"/\\|?*')


def es_ruta_documento(ruta) -> bool:
    """Si esa entrada de la tira es un documento sin foto (``Documento.nuevo_lienzo``): su ruta es
    un nombre en la carpeta de la app con ``EXTENSION_DOCUMENTO``, que no existe en el disco (el
    documento vive en el estado de la foto: sesión, historial y proyecto)."""
    try:
        return Path(str(ruta)).suffix.lower() == EXTENSION_DOCUMENTO
    except (TypeError, ValueError):
        return False


def ruta_documento_nueva(existentes=(), nombre: str = "Sin título") -> str:
    """Una ruta de documento (``EXTENSION_DOCUMENTO``) que no esté entre ``existentes``:
    "Sin título 1", "Sin título 2"… (con otro nombre, ese y después "nombre 2", "nombre 3"…)."""
    from .. import edicion
    carpeta = edicion.carpeta_datos() / "documentos"
    usados = {os.path.normcase(str(Path(r).name)) for r in existentes}
    nombre = "".join(c for c in str(nombre) if c not in _NO_VALEN_EN_NOMBRES).strip() or "Sin título"
    if nombre != "Sin título" and os.path.normcase(nombre + EXTENSION_DOCUMENTO) not in usados:
        return str(carpeta / (nombre + EXTENSION_DOCUMENTO))
    n = 1 if nombre == "Sin título" else 2
    while True:
        candidato = f"{nombre} {n}{EXTENSION_DOCUMENTO}"
        if os.path.normcase(candidato) not in usados:
            return str(carpeta / candidato)
        n += 1


def nombre_documento(ruta) -> str:
    """El nombre que se muestra de una entrada de la tira (sin la extensión, si es un documento)."""
    p = Path(str(ruta))
    return p.stem if es_ruta_documento(p) else p.name


def color_base(doc: Documento) -> tuple[int, int, int]:
    """El color con que se rellena la "foto" de relleno de un documento sin foto: el del fondo si es
    un color opaco; si no (transparente o degradado), blanco."""
    base = doc.capas[0]
    rel = base.params
    if base.tipo == "relleno" and rel is not None and rel.tipo == "color" and rel.colores[0][3] == 255:
        return tuple(int(v) for v in rel.colores[0][:3])
    return 255, 255, 255


def imagen_documento(ruta, doc: Documento):
    """La "foto" de un documento sin foto, para la ventana: una ``ImagenCargada`` en memoria del
    tamaño del documento, lisa (``color_base``). No entra a la composición (``componer`` no usa foto
    en un documento sin foto): sirve para que la vista, las zonas de los efectos, el tamaño y la
    exportación trabajen como con una foto."""
    from ..motor.imagen_io import ImagenCargada
    rgb = np.empty((doc.alto, doc.ancho, 3), np.uint8)
    rgb[:] = color_base(doc)
    return ImagenCargada(ruta=Path(str(ruta)), rgb=rgb, alpha=None, icc=None, nombre_perfil="sRGB", exif=None,
                         orientacion_original=1, notas=[])


def fondo_transparente(doc: Optional[Documento]) -> bool:
    """Si es un documento sin foto cuyo fondo deja ver a través (sin relleno, con transparencia,
    oculto, con menos opacidad o con máscara): ahí la imagen final lleva alfa."""
    if doc is None or doc.tiene_foto:
        return False
    base = doc.capas[0]
    rel = base.params
    opaco = (base.visible and base.opacidad >= 1.0 and base.mascara is None and rel is not None
             and rel.tipo != "ninguno" and all(c[3] == 255 for c in rel.colores))
    return not opaco


def con_alfa_de_documento(doc: Documento, almacen: AlmacenImagenes, salida: np.ndarray,
                          sin_filtro: bool) -> tuple[np.ndarray, np.ndarray]:
    """(RGB, alfa) de un documento sin foto con el fondo transparente, del tamaño de ``salida``.

    ``componer`` aplana lo transparente sobre blanco: para saber cuánto tapa cada píxel se compone
    dos veces lo mismo con una base opaca negra y otra blanca debajo de todo (el fondo de verdad queda
    como una capa más): alfa = 1 − (blanco − negro) / 255. Es exacto con capas en modo normal (con
    otros modos de fusión, aproximado). Sin el filtro, el color es el de "sobre negro" dividido por el
    alfa; con el filtro, queda ``salida`` (lo filtrado) y solo se le suma el alfa."""
    from ..motor.documento import componer
    from ..motor.formas import Relleno
    h, w = salida.shape[:2]
    escala = w / doc.ancho
    id_base = doc.id_libre()

    def sobre(color) -> np.ndarray:
        base = Capa(id_base, "relleno", "Base", params=Relleno("color", (color,)))
        d = Documento(doc.ancho, doc.alto, (base,) + doc.capas)
        rgb = componer(d, almacen, None, escala)
        if rgb.shape[:2] != (h, w):
            rgb = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_LINEAR)
        return rgb.astype(np.float32)

    negro, blanco = sobre((0, 0, 0, 255)), sobre((255, 255, 255, 255))
    a = np.clip(1.0 - (blanco - negro).mean(axis=2) / 255.0, 0.0, 1.0)
    alfa = np.clip(a * 255.0 + 0.5, 0, 255).astype(np.uint8)
    if not sin_filtro:
        return salida, alfa
    rgb = np.clip(negro / np.maximum(a, 1e-6)[..., None] + 0.5, 0, 255).astype(np.uint8)
    return rgb, alfa


def con_tamano(doc: Documento, ancho: int, alto: int) -> Documento:
    """El mismo documento con otro tamaño (sin mover nada): para componer sobre una foto que
    cambió de tamaño sin pasar por ``convertir_documento``."""
    if (doc.ancho, doc.alto) == (ancho, alto):
        return doc
    return Documento(int(ancho), int(alto), doc.capas)


def ids_usados(estados) -> set[str]:
    """Los ids del almacén que usan los documentos de esos estados (dicts del editor)."""
    usados: set[str] = set()
    for estado in estados:
        doc = estado.get("documento") if isinstance(estado, dict) else None
        if isinstance(doc, Documento):
            usados |= doc.ids_usados()
    return usados


# ---------------------------------------------------------------------------
# Del marco viejo al nuevo (geometría y recorte)
# ---------------------------------------------------------------------------

def tamano_documento(w: int, h: int, geometria: Optional[Geometria], recorte: Optional[Recorte]) -> tuple[int, int]:
    """(ancho, alto) del documento de una foto ORIGINAL de ``w`` × ``h``: el de la foto que entra al filtro."""
    wb, hb = tamano_resultante(w, h, geometria or Geometria())
    if recorte is None:
        return wb, hb
    x0, y0, x1, y1 = recorte.pixeles(wb, hb)
    return max(1, x1 - x0), max(1, y1 - y0)


def _base_a_documento(w: int, h: int, geometria: Geometria, recorte: Optional[Recorte]) -> np.ndarray:
    """3×3: de coordenadas normalizadas de la foto base (con esa geometría) a píxeles del documento."""
    wb, hb = tamano_resultante(w, h, geometria)
    x0, y0 = (0, 0) if recorte is None else recorte.pixeles(wb, hb)[:2]
    return np.array([[wb, 0.0, -x0], [0.0, hb, -y0], [0.0, 0.0, 1.0]])


def matriz_marco(w: int, h: int, geo_antes: Optional[Geometria], recorte_antes: Optional[Recorte],
                 geo_despues: Optional[Geometria], recorte_despues: Optional[Recorte]) -> np.ndarray:
    """3×3 que lleva píxeles del documento viejo a los del nuevo (``w`` × ``h``: la foto ORIGINAL)."""
    ga, gb = geo_antes or Geometria(), geo_despues or Geometria()
    cambio = np.eye(3) if ga == gb else matriz_cambio(ga, gb, w, h)
    return _base_a_documento(w, h, gb, recorte_despues) @ cambio @ np.linalg.inv(
        _base_a_documento(w, h, ga, recorte_antes))


def _partes_marco(m: np.ndarray) -> tuple[float, float, bool]:
    """(escala, giro en grados, espejo) de la parte lineal de ``m``: a = s·R(θ)·F, con F el espejo
    horizontal si el determinante es negativo (los cambios de marco son giros, espejos, escalas
    parejas y traslaciones)."""
    a = m[:2, :2]
    det = float(np.linalg.det(a))
    s = math.sqrt(abs(det)) or 1.0
    espejo = det < 0
    giro = a @ np.diag([-1.0, 1.0]) / s if espejo else a / s  # a·F/s es un giro puro
    return s, math.degrees(math.atan2(giro[1, 0], giro[0, 0])), espejo


def _transformacion_llevada(t: Transformacion, m: np.ndarray) -> Transformacion:
    """La transformación de una capa después de aplicarle la matriz ``m`` (3×3) al documento.

    La capa es c + R(r)·diag(±sx, ±sy): con s·R(θ) delante queda R(θ + r)·diag(±s·sx, ±s·sy); con
    s·R(θ)·F (espejo), como F·R(r) = R(-r)·F, queda R(θ - r)·diag(∓s·sx, ±s·sy): la rotación pasa a
    θ - r, el volteo horizontal se invierte y el vertical queda. Las dos escalas se multiplican por s
    (``escala_y`` y ``voltear_v`` se conservan)."""
    x, y, _ = m @ np.array([t.x, t.y, 1.0])
    s, theta, espejo = _partes_marco(m)
    rotacion = theta - t.rotacion if espejo else theta + t.rotacion
    rotacion = (rotacion + 180.0) % 360.0 - 180.0
    if abs(rotacion - round(rotacion)) < 1e-9:
        rotacion = float(round(rotacion))
    return Transformacion(float(x), float(y), t.escala * s, rotacion, t.voltear_h != espejo,
                          None if t.escala_y is None else t.escala_y * s, t.voltear_v)


def _relleno_llevado(r, m: np.ndarray):
    """El ángulo de un relleno (degradado) llevado con el cambio de marco: el espejo lo refleja
    (α → 180 - α) y el giro lo suma."""
    _s, theta, espejo = _partes_marco(m)
    angulo = (180.0 - r.angulo) if espejo else r.angulo
    return dataclasses.replace(r, angulo=(angulo + theta) % 360.0)


def _estilos_llevados(e, m: np.ndarray):
    """Los estilos de una capa con el cambio de marco: espejados, girados y escalados (sus medidas)."""
    s, theta, espejo = _partes_marco(m)
    if espejo:
        e = e.espejados("h")
    if abs(theta) > 1e-9:
        e = e.girados(theta)
    if abs(s - 1.0) > 1e-9:
        e = e.escalados(s)
    return e


def _mascara_llevada(m: np.ndarray, matriz: np.ndarray, ancho: int, alto: int) -> np.ndarray:
    """La máscara (gris uint8) llevada al documento nuevo, con OpenCV (centro del píxel 0 en 0)."""
    a = matriz[:2, :2]
    b = matriz[:2, 2] + a @ np.array([0.5, 0.5]) - 0.5
    cv = np.hstack([a, b[:, None]])
    if m.ndim == 3:
        m = np.ascontiguousarray(m[..., 0])
    return cv2.warpAffine(m, cv, (int(ancho), int(alto)), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def convertir_documento(doc: Optional[Documento], almacen: AlmacenImagenes, matriz: np.ndarray,
                        ancho: int, alto: int) -> Optional[Documento]:
    """El documento llevado al marco nuevo (ver el módulo). Uno trivial solo cambia de tamaño."""
    if doc is None:
        return None
    if es_trivial(doc):
        return documento_nuevo(ancho, alto)
    identidad = np.allclose(matriz, np.eye(3)) and (doc.ancho, doc.alto) == (ancho, alto)
    if identidad:
        return doc
    capas = []
    for c in doc.capas:
        cambios = {}
        if c.tipo in TIPOS_CON_TRANSFORMACION:  # imagen, pixeles, texto y forma (no solo las imagen)
            cambios["transform"] = _transformacion_llevada(c.transform, matriz)
        if c.tipo == "relleno" and c.params is not None:
            cambios["params"] = _relleno_llevado(c.params, matriz)
        if c.estilos != EstilosCapa():
            cambios["estilos"] = _estilos_llevados(c.estilos, matriz)
        if c.mascara is not None and c.mascara in almacen:
            cambios["mascara"] = almacen.guardar(_mascara_llevada(almacen.obtener(c.mascara), matriz, ancho, alto))
        capas.append(dataclasses.replace(c, **cambios) if cambios else c)
    return Documento(int(ancho), int(alto), tuple(capas))


# ---------------------------------------------------------------------------
# Máscaras
# ---------------------------------------------------------------------------

def mascara_de(doc: Documento, almacen: AlmacenImagenes, id_capa: str) -> np.ndarray:
    """La máscara de esa capa al tamaño del documento, en uint8 (blanca si no tiene o si falta)."""
    capa = doc.capa(id_capa)
    if capa.mascara is not None and capa.mascara in almacen:
        m = almacen.obtener(capa.mascara)
        if m.ndim == 3:
            m = m[..., 0]
        if m.shape != (doc.alto, doc.ancho):
            m = cv2.resize(np.ascontiguousarray(m), (doc.ancho, doc.alto), interpolation=cv2.INTER_LINEAR)
        return m
    return np.full((doc.alto, doc.ancho), 255, np.uint8)


def mascara_llena(doc: Documento, valor: int) -> np.ndarray:
    """Una máscara pareja: 255 = "Mostrar todo", 0 = "Ocultar todo"."""
    return np.full((doc.alto, doc.ancho), int(valor), np.uint8)


def pintar_mascara(actual: np.ndarray, zona: Zona, modo: str, recorte: Optional[Recorte]) -> np.ndarray:
    """``actual`` (uint8, del tamaño del documento) con la zona sumada ("mostrar") o restada
    ("ocultar"). La zona está en coordenadas de la foto base, como las de los efectos: con
    ``recorte`` se toma la parte que se ve (``mascara_zona``)."""
    if modo not in MODOS_MASCARA:
        raise ValueError(f"Modo de máscara desconocido: {modo!r}.")
    alto, ancho = actual.shape[:2]
    m = mascara_zona(zona, alto, ancho, recorte).astype(np.float32)
    base = actual.astype(np.float32)
    nueva = np.maximum(base, m * 255.0) if modo == "mostrar" else base * (1.0 - m)
    return np.clip(nueva + 0.5, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# El estado del editor en JSON
# ---------------------------------------------------------------------------

def _clases() -> dict:
    from ..sesion import CLASES  # las mismas que acepta la sesión
    return CLASES


def a_json(valor):
    """Un valor del estado del editor pasado a tipos de JSON (ver el módulo). ``TypeError`` si no se puede."""
    if valor is None or isinstance(valor, (bool, str)):
        return valor
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if isinstance(valor, float) and not math.isfinite(valor):
            raise TypeError(f"número no finito en el estado: {valor!r}")
        return valor
    if isinstance(valor, np.generic):
        return a_json(valor.item())
    if isinstance(valor, (bytes, bytearray)):
        return {"$bytes": base64.b64encode(bytes(valor)).decode("ascii")}
    if isinstance(valor, tuple):
        return {"$tupla": [a_json(v) for v in valor]}
    if isinstance(valor, list):
        return [a_json(v) for v in valor]
    if isinstance(valor, dict):
        if not all(isinstance(k, str) and not k.startswith("$") for k in valor):
            raise TypeError("el estado tiene claves que no son texto")
        return {k: a_json(v) for k, v in valor.items()}
    if dataclasses.is_dataclass(valor) and type(valor).__name__ in _clases() \
            and _clases()[type(valor).__name__] is type(valor):
        return {"$clase": type(valor).__name__,
                "campos": {f.name: a_json(getattr(valor, f.name)) for f in dataclasses.fields(valor)}}
    raise TypeError(f"no se puede pasar a JSON: {type(valor).__name__}")


def desde_json(valor):
    """Lo inverso de ``a_json``. ``ValueError`` si algo no tiene la forma esperada."""
    if valor is None or isinstance(valor, (bool, str, int, float)):
        return valor
    if isinstance(valor, list):
        return [desde_json(v) for v in valor]
    if not isinstance(valor, dict):
        raise ValueError(f"valor inesperado en el estado: {type(valor).__name__}")
    if "$bytes" in valor:
        try:
            return base64.b64decode(valor["$bytes"], validate=True)
        except (ValueError, TypeError) as error:
            raise ValueError("bytes inválidos en el estado") from error
    if "$tupla" in valor:
        if not isinstance(valor["$tupla"], list):
            raise ValueError("tupla inválida en el estado")
        return tuple(desde_json(v) for v in valor["$tupla"])
    if "$clase" in valor:
        cls = _clases().get(valor["$clase"])
        campos = valor.get("campos")
        if cls is None or not isinstance(campos, dict):
            raise ValueError(f"clase no permitida en el estado: {valor['$clase']!r}")
        argumentos = {}
        for campo in dataclasses.fields(cls):
            if campo.name in campos:
                argumentos[campo.name] = desde_json(campos[campo.name])
            elif campo.default is dataclasses.MISSING and campo.default_factory is dataclasses.MISSING:
                raise ValueError(f"a {cls.__name__} le falta el campo {campo.name}")
        try:
            return cls(**argumentos)
        except Exception as error:  # noqa: BLE001 - cualquier cosa que no sirva
            raise ValueError(f"{cls.__name__} inválido: {error}") from error
    if any(k.startswith("$") for k in valor):
        raise ValueError("etiqueta desconocida en el estado")
    return {k: desde_json(v) for k, v in valor.items()}


def estado_a_json(estado: dict) -> dict:
    """El estado del editor (sin el documento, que va aparte en el proyecto) en JSON."""
    return a_json({k: v for k, v in estado.items() if k != "documento"})


def estado_desde_json(datos) -> dict:
    """El estado del editor desde JSON, con lo mínimo validado (como la sesión)."""
    from ..motor.procesado import Ajustes
    estado = desde_json(datos)
    if not isinstance(estado, dict) or not isinstance(estado.get("preset"), str) \
            or not isinstance(estado.get("ajustes"), Ajustes):
        raise ValueError("el estado de la foto no tiene preset o ajustes")
    capas = estado.get("capas", [])
    if not isinstance(capas, (list, tuple)) or not all(isinstance(c, tuple) and len(c) >= 2 for c in capas):
        raise ValueError("los efectos del estado no tienen la forma esperada")
    estado["capas"] = list(capas)
    return estado


__all__ = [
    "EXTENSION_DOCUMENTO", "MODOS_MASCARA", "VERSION_ESTADO", "a_json", "color_base", "con_alfa_de_documento",
    "con_tamano", "fondo_transparente",
    "convertir_documento", "desde_json", "documento_nuevo", "es_ruta_documento", "es_trivial", "imagen_documento",
    "nombre_documento", "ruta_documento_nueva", "estado_a_json", "estado_desde_json", "ids_usados", "mascara_de",
    "mascara_llena", "matriz_marco", "pintar_mascara", "tamano_documento", "tiene_capas_extra",
]
