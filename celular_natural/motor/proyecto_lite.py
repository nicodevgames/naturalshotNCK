"""Proyecto de NaturalShot Lite (``.nslite``): el documento de capas con sus imágenes.

No depende de la interfaz gráfica ni de los módulos de video y audio.

Qué hay adentro
---------------
Un zip con:

* ``documento.json``: ``{"formato": 1 o 2, "app": "NaturalShot Lite", "documento": {...},
  "extra": {...}}``. ``documento`` es ``Documento.como_dict()``; ``extra`` es de la interfaz
  (por ejemplo, la ruta de la foto base y el estado del editor), un objeto JSON cualquiera.
* ``imagenes/<id>.png``: la imagen de cada capa imagen o pixeles (RGBA, RGB o gris, tal cual
  estaba en el almacén), una vez por id.
* ``mascaras/<id>.png``: cada máscara, en gris de 8 bits.

El id es el del ``AlmacenImagenes`` (el hash del contenido): al abrir, cada PNG se vuelve a
guardar en un almacén nuevo y da el mismo id, así el documento no cambia.

Formatos
--------
* **1** (Etapa 1): foto, capas imagen y el ajuste.
* **2** (Etapa 2): además, en cada capa, ``params`` (el texto, la forma o el relleno, como
  diccionarios: ``ParamsTexto``, ``ParamsForma`` y ``Relleno`` de ``motor/texto.py`` y
  ``motor/formas.py``), ``estilos`` (``EstilosCapa.como_dict()``) y ``padre`` (el grupo), y en
  la transformación ``escala_y`` y ``voltear_v``; tipos nuevos (pixeles, texto, forma, relleno
  y grupo) y la base puede ser un relleno. Cada cosa nueva va solo si no es la de por defecto.

Se guarda en formato 1 si el documento no usa nada de la Etapa 2 (``Documento.usa_etapa2``),
así una versión anterior lo sigue abriendo; si no, en el 2. Se abren los dos.

Guardar
-------
Escritura atómica: el zip se arma en un temporal en la misma carpeta, se baja al disco
(``fsync``) y se renombra encima con ``os.replace``. Un error a mitad de camino (o un
``extra`` que no se puede pasar a JSON, que se revisa antes de escribir nada) deja el
archivo anterior como estaba y no deja temporales. Solo se guardan las imágenes que el
documento usa; las que no están en el almacén se saltean (al abrir, esas capas "faltan").

Abrir
-----
Se lee solo ``documento.json`` y los PNG que nombra el documento, por su nombre: nada de
pickle ni de ejecutar lo que venga en el archivo (cualquier otra cosa adentro se ignora).

* El archivo no existe: ``FileNotFoundError``.
* No es un zip, está cortado, no tiene ``documento.json`` o este no se puede leer, el
  formato no es un entero válido o el documento no cumple las reglas: ``ValueError`` con un
  mensaje claro que nombra el archivo.
* Formato más nuevo que ``FORMATO``: ``ValueError`` ("lo guardó una versión más nueva…").
* Una imagen o una máscara que no está, que no se puede leer o que no coincide con su id: el
  proyecto se abre igual y esa capa "falta" (``documento.capas_faltantes``). Lo mismo si el PNG
  declara en su encabezado más de ``MAX_PIXELES_IMAGEN`` (una imagen) o más píxeles que el
  documento (una máscara): se mira **antes** de decodificar, así un PNG chico que dice medir
  30000×30000 no reserva gigas ("bomba de descompresión"). Si OpenCV falla o no hay memoria al
  decodificar, también "falta".
"""

from __future__ import annotations

import json
import os
import struct
import tempfile
import time
import zipfile
import zlib
from pathlib import Path
from typing import Callable, Optional, Union

import cv2
import numpy as np

from .documento import LADO_MAX, AlmacenImagenes, Documento

FORMATO = 2          # el más nuevo que se escribe y se abre (ver "Formatos")
EXTENSION = ".nslite"
APP = "NaturalShot Lite"
_DOCUMENTO = "documento.json"
_MAX_JSON = 64 * 2 ** 20        # bytes de documento.json, como mucho
_MAX_PNG = 512 * 2 ** 20        # bytes de un PNG adentro del zip, como mucho
MAX_PIXELES_IMAGEN = 100_000_000  # píxeles de la imagen de una capa, como mucho (100 MP)
_FIRMA_PNG = b"\x89PNG\r\n\x1a\n"
_TIPOS_COLOR = {0: 1, 2: 3, 6: 4}   # tipos de color de PNG que se escriben (gris, RGB, RGBA) → canales
_COMPRESION_PNG = 3

# Lo que puede fallar al leer una entrada de un zip dañado.
_ERRORES_ZIP = (zipfile.BadZipFile, zlib.error, EOFError, OSError, NotImplementedError, RuntimeError, ValueError)

Ruta = Union[str, os.PathLike]


# ---------------------------------------------------------------------------
# Guardar
# ---------------------------------------------------------------------------

def _png(arr: np.ndarray) -> bytes:
    """PNG de 8 bits de un arreglo del almacén (gris, RGB o RGBA), sin perder nada."""
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGRA if arr.shape[2] == 4 else cv2.COLOR_RGB2BGR)
    ok, datos = cv2.imencode(".png", arr, [cv2.IMWRITE_PNG_COMPRESSION, _COMPRESION_PNG])
    if not ok:
        raise OSError("No se pudo codificar una imagen del proyecto en PNG.")
    return datos.tobytes()


def _escribir_atomico(ruta: Path, escribir: Callable[[object], None]) -> None:
    """Temporal en la misma carpeta, al disco (``fsync``) y ``os.replace``: nunca queda a medias."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(prefix=ruta.name + ".", suffix=".tmp", dir=ruta.parent)
    try:
        with os.fdopen(fd, "w+b") as f:
            escribir(f)
            f.flush()
            os.fsync(f.fileno())
        for intento in range(6):
            try:
                os.replace(temporal, ruta)
                break
            except PermissionError:   # un antivirus o un lector lo tiene abierto un instante
                if intento == 5:
                    raise
                time.sleep(0.05 * (intento + 1))
    except BaseException:
        try:
            os.unlink(temporal)
        except OSError:
            pass
        raise


def guardar_proyecto(ruta: Ruta, doc: Documento, almacen: AlmacenImagenes, extra: Optional[dict] = None) -> None:
    """Guarda el documento, sus imágenes y sus máscaras en ``ruta`` (un ``.nslite``), de forma atómica.

    ``extra``: un dict que se pueda pasar a JSON (``TypeError`` o ``ValueError`` si no, sin
    tocar nada en el disco). Ver el módulo.
    """
    if extra is None:
        extra = {}
    if not isinstance(extra, dict):
        raise TypeError("extra tiene que ser un dict.")
    formato = FORMATO if doc.usa_etapa2() else 1
    datos = {"formato": formato, "app": APP, "documento": doc.como_dict(), "extra": extra}
    texto = json.dumps(datos, ensure_ascii=False, indent=1, allow_nan=False).encode("utf-8")
    entradas = []   # (nombre en el zip, id)
    vistos = set()
    for capa in doc.capas:
        for carpeta, id_img in (("imagenes", capa.imagen), ("mascaras", capa.mascara)):
            if id_img is None or (carpeta, id_img) in vistos or id_img not in almacen:
                continue
            vistos.add((carpeta, id_img))
            entradas.append((f"{carpeta}/{id_img}.png", id_img))

    def escribir(f) -> None:
        with zipfile.ZipFile(f, "w") as z:
            z.writestr(_DOCUMENTO, texto, compress_type=zipfile.ZIP_DEFLATED)
            for nombre, id_img in entradas:   # un PNG ya está comprimido: va sin comprimir de nuevo
                z.writestr(nombre, _png(almacen.obtener(id_img)), compress_type=zipfile.ZIP_STORED)

    _escribir_atomico(Path(ruta), escribir)


# ---------------------------------------------------------------------------
# Abrir
# ---------------------------------------------------------------------------

def _encabezado_png(cabeza: bytes) -> Optional[tuple[int, int]]:
    """(ancho, alto) del IHDR de un PNG de 8 bits en gris, RGB o RGBA (lo que escribe ``_png``),
    o None si no es eso. Se mira antes de decodificar: un PNG chico puede declarar 30000×30000."""
    if len(cabeza) < 26 or cabeza[:8] != _FIRMA_PNG or cabeza[12:16] != b"IHDR":
        return None
    ancho, alto = struct.unpack(">II", cabeza[16:24])
    if cabeza[24] != 8 or cabeza[25] not in _TIPOS_COLOR or not ancho or not alto:
        return None
    return ancho, alto


def _leer_png(z: zipfile.ZipFile, nombre: str, max_pixeles: int) -> Optional[np.ndarray]:
    """La imagen de esa entrada (RGB/RGBA o gris, uint8), o None si no está o no se puede usar:
    si no es un PNG de los que se escriben, si declara más de ``max_pixeles`` o más de
    ``LADO_MAX`` por lado (se mira el encabezado antes de decodificar), o si al decodificarla
    OpenCV falla o no hay memoria."""
    try:
        info = z.getinfo(nombre)
    except KeyError:
        return None
    if info.file_size > _MAX_PNG:
        return None
    try:
        with z.open(info) as f:
            tamano = _encabezado_png(f.read(26))
        if tamano is None:
            return None
        ancho, alto = tamano
        if ancho > LADO_MAX or alto > LADO_MAX or ancho * alto > max_pixeles:
            return None
        datos = z.read(info)
    except _ERRORES_ZIP:
        return None
    try:
        img = cv2.imdecode(np.frombuffer(datos, np.uint8), cv2.IMREAD_UNCHANGED)
    except (cv2.error, MemoryError):
        return None
    if img is None or img.dtype != np.uint8 or img.shape[:2] != (alto, ancho):
        return None
    if img.ndim == 3:
        if img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
        elif img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        else:
            return None
    return img


def abrir_proyecto(ruta: Ruta) -> tuple[Documento, AlmacenImagenes, dict]:
    """Abre un ``.nslite``: ``(documento, almacén con sus imágenes y máscaras, extra)``.

    ``FileNotFoundError`` si no existe; ``ValueError`` si está roto o es de una versión
    futura. Una imagen que falta no es un error (ver el módulo). Nunca usa pickle.
    """
    ruta = Path(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el archivo: {ruta}")
    roto = f"No se pudo abrir «{ruta.name}»: no es un proyecto de {APP} o está dañado"
    try:
        z = zipfile.ZipFile(ruta)
    except _ERRORES_ZIP as error:
        raise ValueError(f"{roto}.") from error
    with z:
        try:
            info = z.getinfo(_DOCUMENTO)
        except KeyError:
            raise ValueError(f"{roto} (le falta {_DOCUMENTO}).") from None
        if info.file_size > _MAX_JSON:
            raise ValueError(f"{roto} ({_DOCUMENTO} es demasiado grande).")
        try:
            datos = json.loads(z.read(info).decode("utf-8"))
        except _ERRORES_ZIP as error:   # ValueError cubre el JSON roto y el texto que no es UTF-8
            raise ValueError(f"{roto} ({_DOCUMENTO} no se puede leer).") from error
        if not isinstance(datos, dict):
            raise ValueError(f"{roto} ({_DOCUMENTO} no tiene la forma esperada).")
        formato = datos.get("formato")
        if isinstance(formato, bool) or not isinstance(formato, int) or formato < 1:
            raise ValueError(f"{roto} (no dice qué formato tiene).")
        if formato > FORMATO:
            raise ValueError(f"«{ruta.name}» lo guardó una versión más nueva de {APP} (formato {formato}; esta "
                             f"versión abre hasta el {FORMATO}). Actualizá la app para abrirlo.")
        try:
            doc = Documento.desde_dict(datos.get("documento"))
        except ValueError as error:
            raise ValueError(f"{roto}: {error}") from error
        extra = datos.get("extra", {})
        if not isinstance(extra, dict):
            raise ValueError(f"{roto} (los datos de la interfaz no tienen la forma esperada).")
        almacen = AlmacenImagenes()
        topes = {"imagenes": MAX_PIXELES_IMAGEN, "mascaras": doc.ancho * doc.alto}   # una máscara: como el documento
        for capa in doc.capas:
            for carpeta, id_img in (("imagenes", capa.imagen), ("mascaras", capa.mascara)):
                if id_img is None or id_img in almacen:
                    continue
                img = _leer_png(z, f"{carpeta}/{id_img}.png", topes[carpeta])
                # Se guarda solo si es lo que se guardó (mismo id): si no, esa capa "falta".
                if img is not None and AlmacenImagenes.id_de(img) == id_img:
                    almacen.guardar(img)
    return doc, almacen, extra


__all__ = ["APP", "EXTENSION", "FORMATO", "MAX_PIXELES_IMAGEN", "abrir_proyecto", "guardar_proyecto"]
