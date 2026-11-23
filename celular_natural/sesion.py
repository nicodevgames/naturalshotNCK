"""Sesión: las fotos de la tira y sus ediciones (y el proyecto del modo Audio), para recuperarlas al volver a abrir.

Se guarda en ``%APPDATA%\\NaturalShot PRO\\sesion\\sesion.pkl``:

* De cada foto, solo la **ruta** (nunca la imagen), su estado de edición (preset,
  capas con sus zonas, recorte, geometría, montaje, borrados y fondo: lo mismo que
  ``FotoSesion.estado`` en la ventana), su historial y la posición en él. Además,
  qué foto estaba abierta. El modo Fácil | Editor se guarda aparte (QSettings).
* El **proyecto del modo Audio** (``AudioGuardado``), si hay: su estado (un dict con
  el ``ProyectoAudio`` en "proyecto" y lo que la ventana quiera sumar), su historial y
  la posición en él. Es una clave más del archivo ("audio"): una sesión de antes, que
  no la tiene, se lee igual y queda sin proyecto de audio. Va en un pickle aparte
  (bytes adentro del archivo) y se lee aislado: si no se puede rearmar (un lugar que
  una versión nueva renombró, una clase que no está en ``CLASES``), se anota en
  ``sesion.log`` y se sigue sin proyecto de audio, **con las fotos**.
* Las **capas** de cada foto (NaturalShot Lite, etapa 1): el estado puede tener un
  ``Documento`` (con sus ``Capa`` y ``Transformacion``) en "documento". El pickle guarda
  solo el documento; sus imágenes y máscaras van aparte, como PNG, en
  ``sesion\\imagenes\\<id>.png`` (el id es el del ``AlmacenImagenes``: el hash del
  contenido, así una imagen que ya estaba no se vuelve a escribir). Cada PNG se escribe
  de forma atómica **antes** que el pickle, y los que ya no usa ninguna foto se borran
  **después**: un corte de luz nunca deja una sesión que apunte a una imagen que no está.
  Al leer, ``cargar_imagenes`` trae las que nombran los documentos (en segundo plano, en
  la ventana); una que falta o que no coincide con su id deja esa capa "falta". Una
  sesión de antes, sin documentos, se lee igual.
* Con ``pickle``: los estados son dataclasses congeladas del motor (``Ajustes``,
  ``Zona``, ``Recorte``, ``Geometria``, ``CapaFoto``, ``ZonaBorrado``, ``Documento``,
  ``Capa``, ``Transformacion`` y, desde la Etapa 2 de la Lite, lo que llevan las capas
  nuevas: ``EstilosCapa`` con sus efectos, ``Relleno``, ``ParamsForma`` y ``ParamsTexto``; en el audio,
  ``ProyectoAudio``, ``FondoProyecto``, ``SonidoSuelto``, ``AjustesVoz``,
  ``AjustesAudio`` y ``Escena``) y tuplas, y
  pickle guarda una sola vez cada objeto que se repite de un paso del historial al
  siguiente (por ejemplo, las máscaras automáticas no se copian en cada paso).
* El archivo empieza con una marca y un CRC32 del contenido. Al leerlo solo se
  aceptan esas clases (``_Lector.find_class``) y cada dataclass se vuelve a armar
  con sus campos actuales. Si algo falla (archivo dañado, de una versión
  incompatible o con clases que cambiaron), se lo deja como ``sesion.bak`` para
  diagnóstico, se anota el motivo en ``sesion.log`` y se arranca limpio.
* La escritura es atómica: archivo temporal en la misma carpeta, ``fsync`` y
  ``os.replace``. Un corte de luz deja la sesión anterior o la nueva, nunca una a
  medias.

No usa Qt: la ventana arma la sesión (``SesionGuardada``) y decide cuándo guardar.
"""

from __future__ import annotations

import dataclasses
import io
import os
import pickle
import struct
import tempfile
import time
import traceback
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import __version__, edicion
import cv2
import numpy as np

from .motor.audio import AjustesAudio
from .motor.documento import AlmacenImagenes, Capa, Documento, Transformacion
from .motor.estilos import EstilosCapa, Resplandor, Sombra, SuperposicionColor, SuperposicionDegradado, Trazo
from .motor.formas import ParamsForma, Relleno
from .motor.texto import ParamsTexto
from .motor.edicion import ZonaBorrado
from .motor.geometria import Geometria
from .motor.montaje import CapaFoto
from .motor.procesado import Ajustes
from .motor.proyecto_audio import Escena, FondoProyecto, ProyectoAudio, SonidoSuelto
from .motor.voz_natural import AjustesVoz
from .motor.zonas import Recorte, Zona

VERSION_FORMATO = 1  # subirla si cambia la forma del archivo (las versiones viejas se descartan)
CARPETA_DATOS = "NaturalShot PRO"  # dentro de %APPDATA% (la misma que usan las actualizaciones)
CARPETA_SESION = "sesion"
ARCHIVO_SESION = "sesion.pkl"
ARCHIVO_RESPALDO = "sesion.bak"  # el último archivo que no se pudo leer, para diagnóstico
ARCHIVO_LOG = "sesion.log"
MARCA = b"NaturalShotPRO-sesion\n"
_CABECERA = struct.Struct(">I")  # CRC32 del contenido
# Las únicas clases que puede tener el archivo (más los números de NumPy, abajo).
CLASES = {c.__name__: c for c in (Ajustes, Zona, Recorte, Geometria, CapaFoto, ZonaBorrado,
                                   Documento, Capa, Transformacion,
                                   # Etapa 2 de la Lite: lo que puede tener una capa (params y estilos).
                                   EstilosCapa, Sombra, Trazo, Resplandor, SuperposicionColor, SuperposicionDegradado,
                                   Relleno, ParamsForma, ParamsTexto,
                                   ProyectoAudio, FondoProyecto, SonidoSuelto, AjustesVoz, AjustesAudio, Escena)}
CARPETA_IMAGENES = "imagenes"  # las imágenes y máscaras de las capas, en PNG, por id
_COMPRESION_PNG = 3
# Algún valor puede salir de un cálculo con NumPy (por ejemplo, el recuadro de una máscara).
_NUMPY = {("numpy._core.multiarray", "scalar"), ("numpy.core.multiarray", "scalar"), ("numpy", "dtype")}
TEMPORALES_VIEJOS = 3600  # s: los .tmp más viejos que esto quedaron de un corte y se borran


class SesionIncompatible(Exception):
    """El archivo no es una sesión de esta versión (dañado, viejo o con clases que cambiaron)."""


@dataclass
class FotoGuardada:
    ruta: str
    estado: Optional[dict] = None  # None: la foto nunca se abrió (hereda el preset al abrirla)
    historial: Optional[list] = None  # [(descripción, estado), ...]
    pos: int = 0
    proyecto: Optional[str] = None  # el .nslite donde se guardó por última vez (Ctrl+S lo vuelve a usar)


@dataclass
class AudioGuardado:
    """El proyecto del modo Audio: ``estado`` es un dict con el ``ProyectoAudio`` en "proyecto"
    (y lo que la ventana quiera sumar, con valores simples o clases de ``CLASES``)."""
    estado: dict
    historial: Optional[list] = None  # [(descripción, estado), ...]
    pos: int = 0


@dataclass
class SesionGuardada:
    fotos: list = field(default_factory=list)  # FotoGuardada, en el orden de la tira
    actual: int = -1  # índice de la foto que estaba abierta
    audio: Optional[AudioGuardado] = None  # el proyecto del modo Audio (None: no hay)
    # Las imágenes y máscaras de las capas que usan los documentos (id -> arreglo uint8 del
    # ``AlmacenImagenes``, de solo lectura): se escriben como PNG en ``carpeta_imagenes()``.
    imagenes: dict = field(default_factory=dict)


# ------------------------------------------------------------------ ubicación
def carpeta_sesion() -> Path:
    """``%APPDATA%\\NaturalShot PRO\\sesion`` (``CARPETA_DATOS``); en la Lite, ``NaturalShot Lite\\sesion``."""
    return edicion.carpeta_datos() / CARPETA_SESION


def archivo_sesion() -> Path:
    return carpeta_sesion() / ARCHIVO_SESION


def archivo_respaldo() -> Path:
    return carpeta_sesion() / ARCHIVO_RESPALDO


def carpeta_imagenes() -> Path:
    """``sesion\\imagenes``: las imágenes y máscaras de las capas, en PNG, por su id."""
    return carpeta_sesion() / CARPETA_IMAGENES


# ------------------------------------------------------------------ guardar
def guardar(sesion: SesionGuardada) -> None:
    """Guarda la sesión (atómicamente). Sin fotos ni proyecto de audio, la borra: se arranca de cero."""
    if not sesion.fotos and sesion.audio is None:
        borrar()
        return
    audio = sesion.audio
    if audio is not None:  # aparte: si un día no se puede leer, no se lleva las fotos
        audio = pickle.dumps({"estado": audio.estado,
                              "historial": list(audio.historial) if audio.historial is not None else None,
                              "pos": int(audio.pos)}, protocol=pickle.HIGHEST_PROTOCOL)
    datos = {
        "version": VERSION_FORMATO,
        "app": __version__,
        "guardada": time.time(),
        "actual": int(sesion.actual),
        "fotos": [{"ruta": str(f.ruta), "estado": f.estado,
                   "historial": list(f.historial) if f.historial is not None else None, "pos": int(f.pos),
                   "proyecto": str(f.proyecto) if f.proyecto else None}
                  for f in sesion.fotos],
        "audio": audio,
    }
    contenido = pickle.dumps(datos, protocol=pickle.HIGHEST_PROTOCOL)
    usadas = ids_de_imagenes(sesion)
    _escribir_imagenes({k: v for k, v in sesion.imagenes.items() if k in usadas})  # antes que el pickle
    escribir_atomico(archivo_sesion(), MARCA + _CABECERA.pack(zlib.crc32(contenido)) + contenido)
    _borrar_imagenes_sobrantes(usadas)  # después: la sesión anterior ya no las nombra


# ------------------------------------------------------------------ imágenes de las capas
def _documentos(sesion: SesionGuardada):
    """Los documentos de capas de todos los estados de la sesión (de cada foto y su historial)."""
    for f in sesion.fotos:
        estados = [f.estado] + [paso[1] for paso in (f.historial or ())]
        for estado in estados:
            if isinstance(estado, dict) and isinstance(estado.get("documento"), Documento):
                yield estado["documento"]


def ids_de_imagenes(sesion: SesionGuardada) -> set:
    """Los ids de las imágenes y máscaras que usan los documentos de la sesión."""
    usados = set()
    for doc in _documentos(sesion):
        usados |= doc.ids_usados()
    return usados


def _png(arr: np.ndarray) -> bytes:
    """PNG de 8 bits (gris, RGB o RGBA), sin perder nada."""
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGRA if arr.shape[2] == 4 else cv2.COLOR_RGB2BGR)
    ok, datos = cv2.imencode(".png", arr, [cv2.IMWRITE_PNG_COMPRESSION, _COMPRESION_PNG])
    if not ok:
        raise OSError("No se pudo codificar una imagen de las capas en PNG.")
    return datos.tobytes()


def _escribir_imagenes(imagenes: dict) -> None:
    """Escribe (de forma atómica) las que todavía no están: el nombre es el id del contenido."""
    if not imagenes:
        return
    carpeta = carpeta_imagenes()
    carpeta.mkdir(parents=True, exist_ok=True)
    for id_img, arr in imagenes.items():
        ruta = carpeta / f"{id_img}.png"
        try:
            if ruta.stat().st_size > 0:
                continue  # ya está (un PNG vacío, de un corte, se vuelve a escribir)
        except OSError:
            pass
        escribir_atomico(ruta, _png(np.asarray(arr)))


def _borrar_imagenes_sobrantes(usadas: set) -> None:
    """Borra los PNG que ya no usa ninguna foto de la sesión (y temporales viejos). Nunca falla."""
    try:
        for ruta in carpeta_imagenes().glob("*"):
            try:
                if ruta.suffix == ".png" and ruta.stem not in usadas:
                    ruta.unlink()
                elif ruta.suffix == ".tmp" and time.time() - ruta.stat().st_mtime > TEMPORALES_VIEJOS:
                    ruta.unlink()
            except OSError:
                pass
    except OSError:
        pass


def cargar_imagenes(sesion: Optional[SesionGuardada]) -> dict:
    """Las imágenes y máscaras de las capas de la sesión (id -> arreglo), desde sus PNG.

    Una que no está, que no se puede leer o que no coincide con su id no se devuelve: esa capa
    queda "falta" (``documento.capas_faltantes``). Un PNG que está pero no sirve (dañado o que no
    coincide) se borra: si la imagen vuelve a estar en memoria (por ejemplo, desde un proyecto), el
    próximo guardado lo escribe de nuevo. Nunca falla."""
    if sesion is None:
        return {}
    carpeta = carpeta_imagenes()
    salida = {}
    for id_img in ids_de_imagenes(sesion):
        ruta = carpeta / f"{id_img}.png"
        try:
            datos = ruta.read_bytes()
        except OSError:
            continue  # no está
        img = _decodificar(datos)
        if img is not None and AlmacenImagenes.id_de(img) == id_img:
            salida[id_img] = img
            continue
        try:
            ruta.unlink()
        except OSError:
            pass
    return salida


def _decodificar(datos: bytes) -> Optional[np.ndarray]:
    """Un PNG de la sesión → gris, RGB o RGBA uint8 (None si no se puede leer)."""
    try:
        img = cv2.imdecode(np.frombuffer(datos, np.uint8), cv2.IMREAD_UNCHANGED)
    except (cv2.error, MemoryError):
        return None
    if img is None or img.dtype != np.uint8:
        return None
    if img.ndim == 3:
        if img.shape[2] == 4:
            return cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
        if img.shape[2] == 3:
            return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return None
    return img


def escribir_atomico(ruta: Path, contenido: bytes) -> None:
    """Escribe en un temporal de la misma carpeta, lo baja al disco y recién ahí lo
    pone en lugar del archivo (``os.replace`` es atómico en NTFS)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(prefix=ruta.name + ".", suffix=".tmp", dir=ruta.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contenido)
            f.flush()
            os.fsync(f.fileno())
        for intento in range(6):
            try:
                os.replace(temporal, ruta)
                break
            except PermissionError:  # un antivirus o un lector lo tiene abierto un instante
                if intento == 5:
                    raise
                time.sleep(0.05 * (intento + 1))
    except BaseException:
        try:
            os.unlink(temporal)
        except OSError:
            pass
        raise


def borrar() -> None:
    """Vacía la sesión guardada ("Quitar todas las fotos" o cerrar sin fotos), con sus imágenes."""
    try:
        archivo_sesion().unlink()
    except FileNotFoundError:
        pass
    _borrar_imagenes_sobrantes(set())


# ------------------------------------------------------------------ cargar
class _Lector(pickle.Unpickler):
    """Solo arma las clases de la sesión: cualquier otra cosa se rechaza."""

    def find_class(self, modulo: str, nombre: str):
        if modulo.startswith("celular_natural.") and nombre in CLASES:
            return CLASES[nombre]  # por nombre: sigue andando aunque la clase cambie de módulo
        if (modulo, nombre) in _NUMPY:
            return super().find_class(modulo, nombre)
        raise SesionIncompatible(f"clase no permitida: {modulo}.{nombre}")


def cargar() -> tuple[Optional[SesionGuardada], Optional[str]]:
    """(sesión, problema). Sin sesión guardada: (None, None).

    Si el archivo no se puede usar, queda como ``sesion.bak`` y devuelve
    (None, motivo): la app arranca limpia, sin romper nada."""
    _borrar_temporales_viejos()
    ruta = archivo_sesion()
    try:
        crudo = ruta.read_bytes()
    except FileNotFoundError:
        return None, None
    except OSError as error:
        return None, f"no se pudo leer la sesión anterior ({error.strerror or error})"
    try:
        return leer(crudo), None
    except Exception as error:  # dañado, incompatible o lo que sea: se arranca limpio
        motivo = (str(error) if isinstance(error, SesionIncompatible)
                  else f"{type(error).__name__}: {error}")
        _registrar(f"No se pudo usar la sesión ({motivo}); quedó como {ARCHIVO_RESPALDO}.\n"
                   + "".join(traceback.format_exception_only(type(error), error)).strip())
        try:
            os.replace(ruta, archivo_respaldo())
        except OSError:
            pass
        return None, motivo


def leer(crudo: bytes) -> SesionGuardada:
    """Arma la sesión desde el contenido del archivo. Lanza una excepción si no sirve."""
    if not crudo.startswith(MARCA) or len(crudo) < len(MARCA) + _CABECERA.size:
        raise SesionIncompatible("el archivo no es una sesión de NaturalShot")
    (crc,) = _CABECERA.unpack_from(crudo, len(MARCA))
    contenido = memoryview(crudo)[len(MARCA) + _CABECERA.size:]
    if zlib.crc32(contenido) != crc:
        raise SesionIncompatible("el archivo está dañado (incompleto o modificado)")
    datos = _Lector(io.BytesIO(contenido)).load()
    if not isinstance(datos, dict) or not isinstance(datos.get("fotos"), list):
        raise SesionIncompatible("formato desconocido")
    if datos.get("version") != VERSION_FORMATO:
        raise SesionIncompatible(f"versión de sesión incompatible ({datos.get('version')!r}, "
                                 f"esta app usa la {VERSION_FORMATO})")
    memo: dict[int, object] = {}
    fotos = []
    for f in datos["fotos"]:
        if not isinstance(f, dict) or not isinstance(f.get("ruta"), str) or not f["ruta"]:
            raise SesionIncompatible("foto sin ruta")
        estado = f.get("estado")
        historial = f.get("historial")
        if estado is not None:
            estado = _validar_estado(_reconstruir(estado, memo))
        if historial is not None:
            if not isinstance(historial, list) or not historial:
                raise SesionIncompatible("historial inválido")
            historial = [_validar_paso(_reconstruir(p, memo)) for p in historial]
        pos = f.get("pos", 0)
        if not isinstance(pos, int) or isinstance(pos, bool):
            raise SesionIncompatible("posición del historial inválida")
        if historial is not None:
            pos = max(0, min(pos, len(historial) - 1))
        proyecto = f.get("proyecto")  # una sesión de antes no lo tiene
        fotos.append(FotoGuardada(f["ruta"], estado, historial, pos, proyecto if isinstance(proyecto, str) else None))
    actual = datos.get("actual", 0)
    if not isinstance(actual, int) or isinstance(actual, bool):
        raise SesionIncompatible("foto actual inválida")
    try:
        audio = _leer_audio(datos.get("audio"))  # una sesión de antes no lo tiene: None
    except Exception as error:  # SesionIncompatible, un pickle que no se puede leer…: las fotos siguen
        motivo = str(error) if isinstance(error, SesionIncompatible) else f"{type(error).__name__}: {error}"
        _registrar(f"No se pudo usar el proyecto de audio de la sesión ({motivo}); se siguió sin él.")
        audio = None
    return SesionGuardada(fotos, max(-1, min(actual, len(fotos) - 1)), audio)


def _leer_audio(guardado) -> Optional[AudioGuardado]:
    if guardado is None:
        return None
    if isinstance(guardado, (bytes, bytearray)):  # como lo guarda ``guardar``: un pickle aparte, con las mismas clases
        guardado = _Lector(io.BytesIO(guardado)).load()
    # (Un dict suelto es como lo guardaban las primeras pruebas del modo Audio: se sigue leyendo.)
    memo: dict[int, object] = {}
    if not isinstance(guardado, dict):
        raise SesionIncompatible("proyecto de audio inválido")
    estado = _validar_estado_audio(_reconstruir(guardado.get("estado"), memo))
    historial = guardado.get("historial")
    if historial is not None:
        if not isinstance(historial, list) or not historial:
            raise SesionIncompatible("historial del audio inválido")
        historial = [_validar_paso_audio(_reconstruir(p, memo)) for p in historial]
    pos = guardado.get("pos", 0)
    if not isinstance(pos, int) or isinstance(pos, bool):
        raise SesionIncompatible("posición del historial del audio inválida")
    if historial is not None:
        pos = max(0, min(pos, len(historial) - 1))
    return AudioGuardado(estado, historial, pos)


def _reconstruir(valor, memo: dict):
    """Vuelve a armar cada dataclass con sus campos de ESTA versión.

    Un campo que falte y no tenga valor inicial hace la sesión incompatible; uno que
    ya no exista se ignora. Así nunca queda un objeto a medias que falle después, al
    procesar. Los objetos repetidos (el mismo en varios pasos) se arman una sola vez.
    """
    if valor is None or isinstance(valor, (str, bytes, bool, int, float)):
        return valor
    clave = id(valor)
    if clave in memo:
        return memo[clave]
    if isinstance(valor, dict):
        armado = {k: _reconstruir(v, memo) for k, v in valor.items()}
    elif isinstance(valor, list):
        armado = [_reconstruir(v, memo) for v in valor]
    elif isinstance(valor, tuple):
        armado = tuple(_reconstruir(v, memo) for v in valor)
    elif type(valor) in CLASES.values():
        cls = type(valor)
        guardados = vars(valor)
        argumentos = {}
        for campo in dataclasses.fields(cls):
            if campo.name in guardados:
                argumentos[campo.name] = _reconstruir(guardados[campo.name], memo)
            elif campo.default is dataclasses.MISSING and campo.default_factory is dataclasses.MISSING:
                raise SesionIncompatible(f"a {cls.__name__} le falta el campo {campo.name}")
        try:
            armado = cls(**argumentos)
        except Exception as error:
            raise SesionIncompatible(f"{cls.__name__} inválido: {error}") from error
    elif hasattr(valor, "dtype") and hasattr(valor, "item"):  # número de NumPy
        armado = valor.item()
    else:
        raise SesionIncompatible(f"valor inesperado: {type(valor).__name__}")
    memo[clave] = armado
    return armado


def _validar_estado(estado) -> dict:
    """Lo mínimo que necesita la ventana para restaurar una foto (lo demás tiene valor inicial)."""
    if not isinstance(estado, dict):
        raise SesionIncompatible("estado inválido")
    if not isinstance(estado.get("preset"), str) or not isinstance(estado.get("ajustes"), Ajustes):
        raise SesionIncompatible("estado sin preset o sin ajustes")
    capas = estado.get("capas")
    if not isinstance(capas, (list, tuple)) or not all(isinstance(c, tuple) and len(c) >= 2 for c in capas):
        raise SesionIncompatible("capas inválidas")
    if "documento" in estado and not isinstance(estado["documento"], Documento):
        raise SesionIncompatible("documento de capas inválido")
    return estado


def _validar_paso(paso) -> tuple:
    if not isinstance(paso, tuple) or len(paso) != 2 or not isinstance(paso[0], str):
        raise SesionIncompatible("paso del historial inválido")
    return paso[0], _validar_estado(paso[1])


def _validar_estado_audio(estado) -> dict:
    """Lo mínimo para restaurar el modo Audio: el proyecto (lo demás lo valida la ventana)."""
    if not isinstance(estado, dict) or not isinstance(estado.get("proyecto"), ProyectoAudio):
        raise SesionIncompatible("estado del audio sin proyecto")
    return estado


def _validar_paso_audio(paso) -> tuple:
    if not isinstance(paso, tuple) or len(paso) != 2 or not isinstance(paso[0], str):
        raise SesionIncompatible("paso del historial del audio inválido")
    return paso[0], _validar_estado_audio(paso[1])


# ------------------------------------------------------------------ varios
def _borrar_temporales_viejos() -> None:
    """Un corte de luz justo al guardar puede dejar un temporal: se borra (la sesión no se toca)."""
    try:
        for temporal in carpeta_sesion().glob(ARCHIVO_SESION + ".*.tmp"):
            try:
                if time.time() - temporal.stat().st_mtime > TEMPORALES_VIEJOS:
                    temporal.unlink()
            except OSError:
                pass
    except OSError:
        pass


def _registrar(mensaje: str) -> None:
    """Anota una línea en ``sesion.log`` (solo problemas). Nunca falla."""
    try:
        carpeta = carpeta_sesion()
        carpeta.mkdir(parents=True, exist_ok=True)
        with open(carpeta / ARCHIVO_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {mensaje}\n")
    except OSError:
        pass
