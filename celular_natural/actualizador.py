"""Actualización automática desde las versiones (releases) de GitHub.

Las versiones se publican en un repositorio **privado** (``REPOSITORIO``) que solo
tiene la app compilada. Solo pueden actualizar las personas que el dueño invitó
como colaboradoras (permiso de lectura) y que aceptaron la invitación.

Acceso
    Con una **GitHub App** del dueño (permisos: Contents y Metadata de solo lectura,
    instalada solo en ese repositorio, con *Device flow* activado). La editora conecta
    su cuenta una vez con el *device flow*: la app muestra un código, ella lo escribe
    en github.com/login/device y autoriza. El token queda cifrado con DPAPI de Windows
    en ``%APPDATA%\\NaturalShot PRO\\sesion_github.dat`` (solo lo puede leer su usuario
    de Windows en esa PC) y nunca se escribe en texto plano ni en el registro (log).
    Si la GitHub App tiene activada la expiración de tokens (8 horas), se renueva solo
    con el *refresh token* (6 meses).

Búsqueda
    ``GET /repos/<repo>/releases/latest`` y, de esa versión, el asset ``version.json``
    (el manifiesto: versión, notas, nombre del zip, SHA-256, tamaño y versión mínima).
    Los assets se bajan con ``GET /repos/<repo>/releases/assets/<id>`` y
    ``Accept: application/octet-stream``: GitHub responde con una redirección a una URL
    firmada de otro dominio, que se sigue **sin** el encabezado ``Authorization``.

Instalación (solo con la app compilada)
    Se baja el zip, se verifica el SHA-256, se descomprime en una carpeta temporal y
    se genera un script de PowerShell que, ya con la app cerrada, respalda la versión
    instalada, copia la nueva (``robocopy /MIR`` solo sobre ``_internal``), restaura el
    respaldo si algo falla, vuelve a abrir NaturalShot y borra los temporales.

Este módulo no usa Qt: la interfaz está en ``ui/actualizaciones.py``.

Variables de entorno de prueba (no hacen nada si no están definidas):
    NATURALSHOT_API_BASE                 reemplaza https://api.github.com
    NATURALSHOT_LOGIN_BASE               reemplaza https://github.com (device flow)
    NATURALSHOT_CLIENT_ID                reemplaza ``CLIENT_ID``
    NATURALSHOT_PRUEBA_ACTUALIZAR_AUTO   =1: acepta solo la conexión y la actualización
    NATURALSHOT_PRUEBA_FALLA_COPIA       =1: el instalador simula una falla a mitad de la copia
"""

from __future__ import annotations

import ctypes
import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable, Optional

from . import __version__
from .motor import Cancelado

# ------------------------------------------------------------------ configuración
# Repositorio PRIVADO con las versiones compiladas (sin el código). Cambiarlo acá alcanza.
REPOSITORIO = "Zergeeenk/naturalshot-releases"
# Client ID de la GitHub App del dueño (Settings > Developer settings > GitHub Apps >
# la app > "Client ID", empieza con "Iv"). Es público: no es un secreto. Mientras tenga
# este valor de relleno, las actualizaciones quedan desactivadas (ver README).
CLIENT_ID = "Iv23li_RELLENO_CAMBIAR"

API_BASE = "https://api.github.com"
LOGIN_BASE = "https://github.com"
VERSION_API = "2022-11-28"

NOMBRE_MANIFIESTO = "version.json"
NOMBRE_ZIP = "NaturalShot-PRO.zip"
NOMBRE_EXE = "NaturalShot.exe"
CARPETA_INTERNA = "_internal"

CARPETA_DATOS = "NaturalShot PRO"  # dentro de %APPDATA%
ARCHIVO_SESION = "sesion_github.dat"
ARCHIVO_LOG = "actualizaciones.log"
ARCHIVO_RESULTADO = "ultima_actualizacion.json"  # lo escribe el instalador, lo lee la app al abrir
PREFIJO_TEMPORAL = "NaturalShot-actualizacion-"

TIEMPO_CONSULTA = 10  # segundos: buscar versión (no frena nada: va en segundo plano)
TIEMPO_DESCARGA = 30  # segundos sin recibir datos antes de abandonar la descarga
MAX_MANIFIESTO = 64 * 1024
MAX_LOG = 512 * 1024

VAR_API = "NATURALSHOT_API_BASE"
VAR_LOGIN = "NATURALSHOT_LOGIN_BASE"
VAR_CLIENT_ID = "NATURALSHOT_CLIENT_ID"
VAR_AUTO = "NATURALSHOT_PRUEBA_ACTUALIZAR_AUTO"
VAR_FALLA = "NATURALSHOT_PRUEBA_FALLA_COPIA"

AGENTE = f"NaturalShot-PRO/{__version__}"


# ------------------------------------------------------------------ errores
class ErrorActualizacion(Exception):
    """Error con un mensaje listo para mostrar en la interfaz."""


class SinConexion(ErrorActualizacion):
    """No hay internet, GitHub no responde o se agotó el límite de consultas: no se avisa nada."""


class SinSesion(ErrorActualizacion):
    """Todavía no se conectó ninguna cuenta de GitHub."""


class SesionVencida(ErrorActualizacion):
    """El token ya no sirve (401): hay que volver a conectar la cuenta."""


class SinAcceso(ErrorActualizacion):
    """403 o 404: la cuenta no tiene acceso al repositorio privado."""


class ManifiestoInvalido(ErrorActualizacion):
    pass


class DescargaFallida(ErrorActualizacion):
    pass


class HashIncorrecto(ErrorActualizacion):
    pass


class PaqueteInvalido(ErrorActualizacion):
    pass


class CodigoVencido(ErrorActualizacion):
    """El código del device flow venció sin que se autorizara."""


class AccesoDenegado(ErrorActualizacion):
    """La persona tocó "Cancel" en GitHub en vez de autorizar."""


class ConfiguracionInvalida(ErrorActualizacion):
    """La GitHub App está mal configurada (Client ID o device flow)."""


MENSAJE_SIN_ACCESO = ("Tu cuenta de GitHub no tiene acceso. Pedile al dueño que te invite y aceptá "
                      "la invitación que te llega por mail.")
MENSAJE_VENCIDA = "Tu sesión de GitHub venció. Volvé a conectar tu cuenta para recibir actualizaciones."


# ------------------------------------------------------------------ entorno
def api_base() -> str:
    return (os.environ.get(VAR_API) or API_BASE).rstrip("/")


def login_base() -> str:
    return (os.environ.get(VAR_LOGIN) or LOGIN_BASE).rstrip("/")


def client_id() -> str:
    return os.environ.get(VAR_CLIENT_ID) or CLIENT_ID


def configurado() -> bool:
    """False mientras ``CLIENT_ID`` tenga el valor de relleno."""
    return "RELLENO" not in client_id()


def plataforma_con_actualizaciones() -> bool:
    """La actualización automática es de Windows (guarda la sesión con DPAPI e instala con PowerShell).

    En Mac la app funciona igual, pero las versiones nuevas se bajan desde Pyro ("Descargar
    NaturalShot"). ``NATURALSHOT_ACTUALIZAR_EN_CUALQUIERA=1`` la prende igual (solo para pruebas).
    """
    return sys.platform == "win32" or os.environ.get("NATURALSHOT_ACTUALIZAR_EN_CUALQUIERA") == "1"


def modo_prueba_auto() -> bool:
    return os.environ.get(VAR_AUTO) == "1"


def compilada() -> bool:
    """True si corre el .exe de PyInstaller (desde el código no se instala nada)."""
    return bool(getattr(sys, "frozen", False))


def pagina_releases() -> str:
    return f"https://github.com/{REPOSITORIO}/releases/latest"


def carpeta_datos() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home()) / CARPETA_DATOS


# ------------------------------------------------------------------ registro (log)
_candado_log = threading.Lock()
_SECRETOS = (
    (re.compile(r"\bgh[a-z]_[A-Za-z0-9_]{8,}"), "gh*_***"),
    (re.compile(r"(?i)(bearer\s+)\S+"), r"\1***"),
    (re.compile(r"(?i)((?:access_token|refresh_token|device_code)[\"']?\s*[:=]\s*[\"']?)[^\"'&\s,}]+"), r"\1***"),
)


def sin_secretos(texto: str) -> str:
    """Tapa cualquier cosa que parezca un token (por las dudas: nunca se los manda al log)."""
    for patron, reemplazo in _SECRETOS:
        texto = patron.sub(reemplazo, texto)
    return texto


def archivo_log() -> Path:
    return carpeta_datos() / ARCHIVO_LOG


def registrar(mensaje: str) -> None:
    """Anota una línea en ``actualizaciones.log``. Nunca falla ni muestra nada."""
    linea = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {sin_secretos(str(mensaje))}\n"
    try:
        with _candado_log:
            ruta = archivo_log()
            ruta.parent.mkdir(parents=True, exist_ok=True)
            if ruta.exists() and ruta.stat().st_size > MAX_LOG:  # se queda con la segunda mitad
                datos = ruta.read_bytes()[-MAX_LOG // 2:]
                ruta.write_bytes(datos[datos.find(b"\n") + 1:])
            with open(ruta, "a", encoding="utf-8") as f:
                f.write(linea)
    except OSError:
        pass


# ------------------------------------------------------------------ versiones
_PATRON_VERSION = re.compile(r"^v?(\d{1,6})\.(\d{1,6})\.(\d{1,6})$")


def interpretar_version(texto) -> tuple[int, int, int]:
    """"1.10.0" -> (1, 10, 0). Acepta una "v" adelante. ValueError si no es X.Y.Z."""
    m = _PATRON_VERSION.match(str(texto).strip()) if isinstance(texto, str) else None
    if m is None:
        raise ValueError(f"Versión inválida: {texto!r} (tiene que ser X.Y.Z)")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def es_mas_nueva(candidata: str, actual: str) -> bool:
    """Comparación semántica: 1.10.0 es más nueva que 1.9.0."""
    return interpretar_version(candidata) > interpretar_version(actual)


# ------------------------------------------------------------------ manifiesto
_PATRON_SHA = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Manifiesto:
    version: str
    zip: str  # nombre del asset de la versión (por ejemplo NaturalShot-PRO.zip)
    sha256: str
    tamano: int
    notas: tuple[str, ...] = ()
    fecha: str = ""
    minima: str = "0.0.0"  # versión desde la que se puede actualizar sola
    # NS-103.6: una instalada anterior a ``obligatoria`` tiene que actualizar (no se puede omitir).
    obligatoria: str = "0.0.0"


def leer_manifiesto(datos) -> Manifiesto:
    """Valida ``version.json`` (bytes, texto o dict). ManifiestoInvalido si algo no cierra."""
    try:
        if isinstance(datos, (bytes, bytearray)):
            datos = datos.decode("utf-8-sig")
        if isinstance(datos, str):
            datos = json.loads(datos)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ManifiestoInvalido(f"El archivo {NOMBRE_MANIFIESTO} no es JSON válido: {error}") from None
    if not isinstance(datos, dict):
        raise ManifiestoInvalido(f"El archivo {NOMBRE_MANIFIESTO} no tiene el formato esperado.")
    faltan = [c for c in ("version", "zip", "sha256", "tamano") if c not in datos]
    if faltan:
        raise ManifiestoInvalido(f"Al manifiesto le faltan campos: {', '.join(faltan)}.")
    try:
        version = ".".join(map(str, interpretar_version(datos["version"])))
        minima = ".".join(map(str, interpretar_version(datos.get("minima") or "0.0.0")))
        obligatoria = ".".join(map(str, interpretar_version(datos.get("obligatoria") or "0.0.0")))
    except ValueError as error:
        raise ManifiestoInvalido(str(error)) from None
    nombre_zip = datos["zip"]
    if not isinstance(nombre_zip, str) or not nombre_zip.strip():
        raise ManifiestoInvalido("El campo zip del manifiesto está vacío.")
    # Se acepta el nombre del asset o una URL de descarga: se usa el nombre del archivo.
    nombre_zip = urllib.parse.unquote(PurePosixPath(urllib.parse.urlparse(nombre_zip.strip()).path).name)
    if not nombre_zip.lower().endswith(".zip") or any(c in nombre_zip for c in '\\/:*?"<>|'):
        raise ManifiestoInvalido(f"Nombre de zip inválido en el manifiesto: {nombre_zip!r}.")
    sha = datos["sha256"]
    if not isinstance(sha, str) or not _PATRON_SHA.match(sha.strip().lower()):
        raise ManifiestoInvalido("El SHA-256 del manifiesto no es válido (64 caracteres hexadecimales).")
    tamano = datos["tamano"]
    if isinstance(tamano, bool) or not isinstance(tamano, int) or tamano <= 0:
        raise ManifiestoInvalido("El tamaño del manifiesto no es válido.")
    notas = datos.get("notas") or []
    if isinstance(notas, str):
        notas = [notas]
    if not isinstance(notas, list) or not all(isinstance(n, str) for n in notas):
        raise ManifiestoInvalido("Las notas del manifiesto tienen que ser una lista de textos.")
    fecha = datos.get("fecha") or ""
    return Manifiesto(version=version, zip=nombre_zip, sha256=sha.strip().lower(), tamano=tamano,
                      notas=tuple(n.strip() for n in notas if n.strip()), fecha=str(fecha), minima=minima,
                      obligatoria=obligatoria)


def sha256_de(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


# ------------------------------------------------------------------ HTTP
class _SinRedireccion(urllib.request.HTTPRedirectHandler):
    """Las redirecciones se siguen a mano: así se decide qué encabezados viajan."""

    def redirect_request(self, *args, **kwargs):  # noqa: D401 - API de urllib
        return None


def _abridor() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_SinRedireccion())


def _origen(url: str) -> tuple[str, str]:
    partes = urllib.parse.urlsplit(url)
    return partes.scheme.lower(), partes.netloc.lower()


def _redireccion_permitida(url: str) -> bool:
    """Solo HTTPS (o HTTP a la misma PC, para las pruebas con un servidor local)."""
    partes = urllib.parse.urlsplit(url)
    if partes.scheme == "https":
        return True
    return partes.scheme == "http" and (partes.hostname or "") in ("127.0.0.1", "localhost", "::1")


def abrir_url(url: str, encabezados: Optional[dict] = None, *, token: Optional[str] = None,
              datos: Optional[bytes] = None, tiempo: float = TIEMPO_CONSULTA, saltos: int = 5):
    """Abre ``url`` siguiendo hasta ``saltos`` redirecciones a mano.

    El token (``Authorization: Bearer``) solo se manda al mismo origen (esquema y host)
    de la URL inicial: las URL firmadas a las que redirige GitHub para bajar un asset
    están en otro dominio y fallan si reciben ese encabezado.

    Devuelve la respuesta abierta. Lanza ``urllib.error.HTTPError`` para los códigos de
    error (el que llama decide qué significan) y ``SinConexion`` si no hay red."""
    origen = _origen(url)
    actual = url
    encabezados = dict(encabezados or {})
    encabezados.setdefault("User-Agent", AGENTE)
    for _ in range(saltos + 1):
        cabecera = dict(encabezados)
        if token and _origen(actual) == origen:
            cabecera["Authorization"] = f"Bearer {token}"
        pedido = urllib.request.Request(actual, data=datos, headers=cabecera,
                                         method="POST" if datos is not None else "GET")
        try:
            return _abridor().open(pedido, timeout=tiempo)
        except urllib.error.HTTPError as error:
            destino = error.headers.get("Location") if error.code in (301, 302, 303, 307, 308) else None
            if not destino:
                raise
            error.close()
            siguiente = urllib.parse.urljoin(actual, destino)
            if not _redireccion_permitida(siguiente):
                raise DescargaFallida("GitHub redirigió a una dirección no segura.") from None
            if error.code == 303 or (error.code in (301, 302) and datos is not None):
                datos = None
                encabezados.pop("Content-Type", None)
            actual = siguiente
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, OSError) as error:
            raise SinConexion(f"Sin conexión con {urllib.parse.urlsplit(actual).netloc}: "
                              f"{getattr(error, 'reason', error)}") from None
    raise DescargaFallida("Demasiadas redirecciones.")


def _leer_cuerpo(error: urllib.error.HTTPError, limite: int = 16384) -> str:
    try:
        return error.read(limite).decode("utf-8", "replace")
    except Exception:
        return ""
    finally:
        error.close()


def _error_api(error: urllib.error.HTTPError, que: str) -> ErrorActualizacion:
    """Traduce un error HTTP de la API de GitHub."""
    cuerpo = _leer_cuerpo(error)
    registrar(f"API: {que} respondió {error.code} {sin_secretos(cuerpo[:200])!r}")
    if error.code == 401:
        return SesionVencida(MENSAJE_VENCIDA)
    if error.code in (403, 429) and (error.headers.get("X-RateLimit-Remaining") == "0"
                                     or "rate limit" in cuerpo.lower() or error.code == 429):
        return SinConexion("Se alcanzó el límite de consultas de GitHub. Probá de nuevo en un rato.")
    if error.code in (403, 404):
        return SinAcceso(MENSAJE_SIN_ACCESO)
    if error.code >= 500:
        return SinConexion(f"GitHub no responde bien ahora (error {error.code}). Probá más tarde.")
    return ErrorActualizacion(f"GitHub respondió con un error ({error.code}).")


def _encabezados_api() -> dict:
    return {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": VERSION_API}


def api_json(ruta: str, token: str, tiempo: float = TIEMPO_CONSULTA):
    """GET a la API de GitHub con el token y devuelve el JSON."""
    url = api_base() + ruta
    try:
        with abrir_url(url, _encabezados_api(), token=token, tiempo=tiempo) as respuesta:
            return json.loads(respuesta.read(4 * 1024 * 1024).decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise _error_api(error, ruta) from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ErrorActualizacion("GitHub respondió algo que no se pudo leer.") from None
    except (TimeoutError, OSError, http.client.HTTPException) as error:  # cortes a mitad de la lectura
        raise SinConexion(f"Se cortó la conexión: {error}") from None


def abrir_asset(asset_id: int, token: str, tiempo: float = TIEMPO_DESCARGA):
    """Abre la descarga de un asset de una versión (sigue la redirección sin el token)."""
    url = f"{api_base()}/repos/{REPOSITORIO}/releases/assets/{int(asset_id)}"
    encabezados = {"Accept": "application/octet-stream", "X-GitHub-Api-Version": VERSION_API}
    try:
        return abrir_url(url, encabezados, token=token, tiempo=tiempo)
    except urllib.error.HTTPError as error:
        raise _error_api(error, f"asset {asset_id}") from None


# ------------------------------------------------------------------ DPAPI
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


_ENTROPIA = b"NaturalShot PRO - sesion de GitHub"
_UI_PROHIBIDA = 0x1  # CRYPTPROTECT_UI_FORBIDDEN


def _dpapi():
    if sys.platform != "win32":
        raise ErrorActualizacion("El cifrado de la sesión solo está disponible en Windows.")
    from ctypes import wintypes
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    puntero = ctypes.POINTER(_Blob)
    crypt32.CryptProtectData.argtypes = [puntero, wintypes.LPCWSTR, puntero, ctypes.c_void_p, ctypes.c_void_p,
                                         wintypes.DWORD, puntero]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [puntero, ctypes.c_void_p, puntero, ctypes.c_void_p, ctypes.c_void_p,
                                           wintypes.DWORD, puntero]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return crypt32, kernel32


def _a_blob(datos: bytes):
    memoria = (ctypes.c_ubyte * max(1, len(datos))).from_buffer_copy(datos or b"\0")
    return _Blob(len(datos), ctypes.cast(memoria, ctypes.POINTER(ctypes.c_ubyte))), memoria


def _usar_dpapi(datos: bytes, cifrar: bool) -> bytes:
    crypt32, kernel32 = _dpapi()
    entrada, _m1 = _a_blob(datos)
    entropia, _m2 = _a_blob(_ENTROPIA)
    salida = _Blob()
    if cifrar:
        ok = crypt32.CryptProtectData(ctypes.byref(entrada), "NaturalShot PRO", ctypes.byref(entropia),
                                      None, None, _UI_PROHIBIDA, ctypes.byref(salida))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(entrada), None, ctypes.byref(entropia),
                                        None, None, _UI_PROHIBIDA, ctypes.byref(salida))
    if not ok:
        raise OSError(ctypes.get_last_error(), "DPAPI no pudo " + ("cifrar" if cifrar else "descifrar"))
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(salida.pbData, ctypes.c_void_p))


def proteger(datos: bytes) -> bytes:
    """Cifra con DPAPI de Windows: solo el mismo usuario de Windows, en esta PC, lo puede descifrar."""
    return _usar_dpapi(bytes(datos), True)


def desproteger(datos: bytes) -> bytes:
    return _usar_dpapi(bytes(datos), False)


# ------------------------------------------------------------------ sesión de GitHub
_CABECERA_SESION = b"NSG1"


@dataclass(repr=False)
class Sesion:
    """Token de usuario de la GitHub App. ``repr`` no muestra los tokens."""
    token: str
    refresco: str = ""
    vence: float = 0.0  # hora (epoch) en que vence el token; 0 = no vence
    refresco_vence: float = 0.0
    usuario: str = ""

    def __repr__(self) -> str:
        return f"Sesion(usuario={self.usuario!r}, vence={self.vence:.0f}, con_refresco={bool(self.refresco)})"

    def vencida(self, margen: float = 120.0, ahora: Optional[float] = None) -> bool:
        ahora = time.time() if ahora is None else ahora
        return bool(self.vence) and ahora >= self.vence - margen

    def renovable(self, ahora: Optional[float] = None) -> bool:
        ahora = time.time() if ahora is None else ahora
        return bool(self.refresco) and (not self.refresco_vence or ahora < self.refresco_vence - 60)


def archivo_sesion() -> Path:
    return carpeta_datos() / ARCHIVO_SESION


def guardar_sesion(sesion: Sesion) -> None:
    datos = json.dumps({"token": sesion.token, "refresco": sesion.refresco, "vence": sesion.vence,
                        "refresco_vence": sesion.refresco_vence, "usuario": sesion.usuario}).encode("utf-8")
    cifrado = _CABECERA_SESION + proteger(datos)
    ruta = archivo_sesion()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_bytes(cifrado)
    os.replace(tmp, ruta)


def cargar_sesion() -> Optional[Sesion]:
    """La sesión guardada, o None si no hay (o si el archivo no se puede descifrar)."""
    ruta = archivo_sesion()
    try:
        crudo = ruta.read_bytes()
    except OSError:
        return None
    if not crudo.startswith(_CABECERA_SESION):
        registrar("Sesión: el archivo guardado no tiene el formato esperado; se ignora.")
        return None
    try:
        datos = json.loads(desproteger(crudo[len(_CABECERA_SESION):]).decode("utf-8"))
        return Sesion(token=str(datos["token"]), refresco=str(datos.get("refresco") or ""),
                      vence=float(datos.get("vence") or 0), refresco_vence=float(datos.get("refresco_vence") or 0),
                      usuario=str(datos.get("usuario") or ""))
    except Exception as error:  # otro usuario u otra PC, o el archivo se dañó
        registrar(f"Sesión: no se pudo descifrar ({type(error).__name__}); hay que volver a conectar.")
        return None


def borrar_sesion() -> None:
    try:
        archivo_sesion().unlink()
    except FileNotFoundError:
        pass
    registrar("Sesión: se desconectó la cuenta de GitHub.")


def _sesion_de_respuesta(datos: dict, usuario: str = "") -> Sesion:
    ahora = time.time()
    vence = float(datos.get("expires_in") or 0)
    refresco_vence = float(datos.get("refresh_token_expires_in") or 0)
    return Sesion(token=str(datos["access_token"]), refresco=str(datos.get("refresh_token") or ""),
                  vence=ahora + vence if vence else 0.0,
                  refresco_vence=ahora + refresco_vence if refresco_vence else 0.0, usuario=usuario)


def _post_login(ruta: str, campos: dict, tiempo: float = TIEMPO_CONSULTA) -> dict:
    """POST de formulario a github.com/login/... y devuelve el JSON (también el de los errores)."""
    url = login_base() + ruta
    cuerpo = urllib.parse.urlencode(campos).encode("ascii")
    encabezados = {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}
    try:
        with abrir_url(url, encabezados, datos=cuerpo, tiempo=tiempo) as respuesta:
            texto = respuesta.read(65536).decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        texto = _leer_cuerpo(error)
        try:
            datos = json.loads(texto)
            if isinstance(datos, dict) and datos.get("error"):
                return datos
        except json.JSONDecodeError:
            pass
        registrar(f"Login: {ruta} respondió {error.code}")
        if error.code == 404:
            raise ConfiguracionInvalida("GitHub no reconoce la app de NaturalShot (revisá el Client ID).") from None
        raise ErrorActualizacion(f"GitHub respondió con un error ({error.code}).") from None
    except (TimeoutError, OSError, http.client.HTTPException) as error:
        raise SinConexion(f"Se cortó la conexión: {error}") from None
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        raise ErrorActualizacion("GitHub respondió algo que no se pudo leer.") from None
    if not isinstance(datos, dict):
        raise ErrorActualizacion("GitHub respondió algo que no se pudo leer.")
    return datos


def renovar_sesion(sesion: Sesion) -> Sesion:
    """Pide un token nuevo con el refresh token (con device flow no hace falta el secreto)."""
    if not sesion.renovable():
        raise SesionVencida(MENSAJE_VENCIDA)
    datos = _post_login("/login/oauth/access_token", {
        "client_id": client_id(), "grant_type": "refresh_token", "refresh_token": sesion.refresco})
    if not datos.get("access_token"):
        registrar(f"Sesión: no se pudo renovar ({datos.get('error') or 'sin token'}).")
        raise SesionVencida(MENSAJE_VENCIDA)
    nueva = _sesion_de_respuesta(datos, sesion.usuario)
    guardar_sesion(nueva)
    registrar("Sesión: token renovado.")
    return nueva


def sesion_vigente() -> Optional[Sesion]:
    """La sesión guardada, renovada si venció. None si no hay. SesionVencida si no se puede renovar."""
    sesion = cargar_sesion()
    if sesion is None:
        return None
    if sesion.vencida():
        return renovar_sesion(sesion)
    return sesion


def obtener_usuario(token: str) -> str:
    """El nombre de usuario de GitHub (para mostrar "Conectada como @…"). Vacío si falla."""
    try:
        return str(api_json("/user", token).get("login") or "")
    except ErrorActualizacion:
        return ""


# ------------------------------------------------------------------ device flow
@dataclass(frozen=True, repr=False)
class CodigoDispositivo:
    codigo_dispositivo: str  # device_code: secreto, no se muestra
    codigo_usuario: str  # user_code: el que escribe la persona (ABCD-1234)
    url_verificacion: str
    expira_en: float
    intervalo: float

    def __repr__(self) -> str:
        return f"CodigoDispositivo({self.codigo_usuario!r}, {self.url_verificacion!r})"


def pedir_codigo() -> CodigoDispositivo:
    """Paso 1 del device flow: POST /login/device/code."""
    if not configurado():
        raise ConfiguracionInvalida("Las actualizaciones no están configuradas en esta copia "
                                    "(falta el Client ID de la GitHub App).")
    datos = _post_login("/login/device/code", {"client_id": client_id()})
    if datos.get("error"):
        raise _error_device(datos)
    try:
        return CodigoDispositivo(str(datos["device_code"]), str(datos["user_code"]),
                                 str(datos.get("verification_uri") or "https://github.com/login/device"),
                                 float(datos.get("expires_in") or 900), float(datos.get("interval") or 5))
    except (KeyError, TypeError, ValueError):
        raise ErrorActualizacion("GitHub respondió algo que no se pudo leer.") from None


def _error_device(datos: dict) -> ErrorActualizacion:
    error = str(datos.get("error"))
    registrar(f"Conexión: GitHub respondió {error!r}")
    if error in ("expired_token", "token_expired", "incorrect_device_code", "bad_verification_code"):
        return CodigoVencido("El código venció. Tocá \"Conectar con GitHub\" para pedir uno nuevo.")
    if error == "access_denied":
        return AccesoDenegado("Cancelaste la autorización en GitHub. Podés volver a intentarlo cuando quieras.")
    if error == "device_flow_disabled":
        return ConfiguracionInvalida("La app de GitHub de NaturalShot no tiene activado el device flow "
                                     "(el dueño tiene que activarlo).")
    if error in ("incorrect_client_credentials", "unsupported_grant_type", "invalid_client"):
        return ConfiguracionInvalida("GitHub no reconoce la app de NaturalShot (revisá el Client ID).")
    return ErrorActualizacion(f"GitHub respondió con un error ({error}).")


def _dormir(segundos: float, cancelado: Callable[[], bool]) -> None:
    limite = time.monotonic() + max(0.0, segundos)
    while time.monotonic() < limite:
        if cancelado():
            raise Cancelado()
        time.sleep(min(0.2, max(0.0, limite - time.monotonic())))


def esperar_autorizacion(codigo: CodigoDispositivo, cancelado: Callable[[], bool] = lambda: False,
                         dormir: Optional[Callable[[float], None]] = None,
                         reloj: Callable[[], float] = time.monotonic) -> Sesion:
    """Paso 2 del device flow: sondea /login/oauth/access_token hasta que la persona autorice.

    Respeta ``interval`` y ``slow_down`` (usa el intervalo nuevo que manda GitHub, o le
    suma 5 segundos). Lanza CodigoVencido, AccesoDenegado o Cancelado. Los cortes de red
    no cortan la espera: se vuelve a probar en el siguiente intervalo."""
    intervalo = max(0.0, codigo.intervalo)
    limite = reloj() + codigo.expira_en
    while True:
        if dormir is None:
            _dormir(intervalo, cancelado)
        else:
            dormir(intervalo)
        if cancelado():
            raise Cancelado()
        if reloj() >= limite:
            raise CodigoVencido("El código venció. Tocá \"Conectar con GitHub\" para pedir uno nuevo.")
        try:
            datos = _post_login("/login/oauth/access_token", {
                "client_id": client_id(), "device_code": codigo.codigo_dispositivo,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
        except SinConexion as error:
            registrar(f"Conexión: {error} (se vuelve a probar)")
            continue
        if datos.get("access_token"):
            sesion = _sesion_de_respuesta(datos)
            sesion.usuario = obtener_usuario(sesion.token)
            registrar(f"Conexión: cuenta conectada{' (@' + sesion.usuario + ')' if sesion.usuario else ''}.")
            return sesion
        error = datos.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            try:
                intervalo = float(datos["interval"])
            except (KeyError, TypeError, ValueError):
                intervalo += 5
            continue
        raise _error_device(datos)


# ------------------------------------------------------------------ búsqueda de versión
@dataclass(frozen=True)
class Novedad:
    """Una versión más nueva que la instalada, lista para mostrar e instalar."""
    manifiesto: Manifiesto
    etiqueta: str
    pagina: str
    id_zip: int
    tamano_zip: int
    instalable: bool = True  # False si la versión instalada es anterior a ``minima``
    obligatoria: bool = False  # True si la instalada es anterior a ``obligatoria``: no se puede omitir

    @property
    def version(self) -> str:
        return self.manifiesto.version


def _con_sesion(funcion: Callable[[Sesion], object], sesion: Optional[Sesion]):
    """Ejecuta ``funcion(sesion)``; si GitHub dice 401 y hay refresh token, renueva y reintenta una vez."""
    if sesion is None:
        sesion = sesion_vigente()
        if sesion is None:
            raise SinSesion("Conectá tu cuenta de GitHub para recibir actualizaciones.")
    try:
        return funcion(sesion)
    except SesionVencida:
        if not sesion.renovable():
            raise
        return funcion(renovar_sesion(sesion))


def _bajar_chico(asset_id: int, token: str, limite: int) -> bytes:
    with abrir_asset(asset_id, token, TIEMPO_CONSULTA) as respuesta:
        datos = respuesta.read(limite + 1)
    if len(datos) > limite:
        raise ManifiestoInvalido(f"El archivo {NOMBRE_MANIFIESTO} es demasiado grande.")
    return datos


def buscar_actualizacion(version_actual: str = __version__, sesion: Optional[Sesion] = None) -> Optional[Novedad]:
    """Devuelve la Novedad si la última versión publicada es más nueva, o None si ya está al día.

    Lanza SinSesion, SinConexion, SesionVencida, SinAcceso, ManifiestoInvalido o ErrorActualizacion."""
    def buscar(s: Sesion) -> Optional[Novedad]:
        release = api_json(f"/repos/{REPOSITORIO}/releases/latest", s.token)
        if not isinstance(release, dict):
            raise ErrorActualizacion("GitHub respondió algo que no se pudo leer.")
        assets = {a.get("name"): a for a in release.get("assets") or [] if isinstance(a, dict)}
        info = assets.get(NOMBRE_MANIFIESTO)
        if info is None:
            raise ManifiestoInvalido(f"La última versión publicada no tiene {NOMBRE_MANIFIESTO}.")
        manifiesto = leer_manifiesto(_bajar_chico(int(info["id"]), s.token, MAX_MANIFIESTO))
        etiqueta = str(release.get("tag_name") or "")
        if not es_mas_nueva(manifiesto.version, version_actual):
            registrar(f"Búsqueda: al día (instalada {version_actual}, publicada {manifiesto.version}).")
            return None
        zip_info = assets.get(manifiesto.zip)
        if zip_info is None:
            raise ManifiestoInvalido(f"La versión {manifiesto.version} no tiene el archivo {manifiesto.zip}.")
        tamano = int(zip_info.get("size") or 0)
        if tamano and tamano != manifiesto.tamano:
            raise ManifiestoInvalido("El tamaño del zip publicado no coincide con el del manifiesto.")
        if etiqueta and etiqueta.lstrip("v") != manifiesto.version:
            registrar(f"Búsqueda: aviso, la etiqueta {etiqueta} no coincide con la versión {manifiesto.version}.")
        instalable = not es_mas_nueva(manifiesto.minima, version_actual)
        obligatoria = es_mas_nueva(manifiesto.obligatoria, version_actual)
        registrar(f"Búsqueda: hay una versión nueva {manifiesto.version} (instalada {version_actual}"
                  f"{', obligatoria' if obligatoria else ''}).")
        return Novedad(manifiesto, etiqueta, str(release.get("html_url") or pagina_releases()),
                       int(zip_info["id"]), tamano or manifiesto.tamano, instalable, obligatoria)

    try:
        return _con_sesion(buscar, sesion)
    except (KeyError, TypeError, ValueError) as error:
        raise ErrorActualizacion(f"La versión publicada tiene datos incompletos ({error}).") from None


# ------------------------------------------------------------------ descarga y paquete
def descargar_paquete(novedad: Novedad, carpeta: Path, progreso: Optional[Callable[[int, int], None]] = None,
                      cancelado: Callable[[], bool] = lambda: False, sesion: Optional[Sesion] = None) -> Path:
    """Baja el zip a ``carpeta`` verificando el tamaño y el SHA-256 del manifiesto.

    Si el SHA-256 no coincide, borra lo bajado y lanza HashIncorrecto."""
    destino = Path(carpeta) / NOMBRE_ZIP
    esperado = novedad.manifiesto.tamano

    def bajar(s: Sesion) -> Path:
        h = hashlib.sha256()
        hechos, ultimo = 0, 0.0
        with abrir_asset(novedad.id_zip, s.token, TIEMPO_DESCARGA) as respuesta, open(destino, "wb") as salida:
            while True:
                if cancelado():
                    raise Cancelado()
                try:
                    bloque = respuesta.read(256 * 1024)
                except (TimeoutError, OSError, http.client.HTTPException) as error:
                    raise DescargaFallida(f"Se cortó la descarga: {error}") from None
                if not bloque:
                    break
                hechos += len(bloque)
                if hechos > esperado:
                    raise DescargaFallida("La descarga es más grande de lo esperado.")
                h.update(bloque)
                salida.write(bloque)
                ahora = time.monotonic()
                if progreso is not None and (ahora - ultimo > 0.15 or hechos == esperado):
                    ultimo = ahora
                    progreso(hechos, esperado)
        if hechos != esperado:
            raise DescargaFallida(f"La descarga quedó incompleta ({hechos} de {esperado} bytes).")
        calculado = h.hexdigest()
        if calculado != novedad.manifiesto.sha256:
            registrar(f"Descarga: SHA-256 no coincide (esperado {novedad.manifiesto.sha256}, bajado {calculado}).")
            raise HashIncorrecto("El archivo bajado no coincide con el publicado (SHA-256 distinto). "
                                 "No se instaló nada. Probá de nuevo más tarde.")
        registrar(f"Descarga: {NOMBRE_ZIP} {hechos} bytes, SHA-256 verificado.")
        return destino

    try:
        return _con_sesion(bajar, sesion)
    except BaseException:
        destino.unlink(missing_ok=True)
        raise


def extraer_paquete(archivo_zip: Path, carpeta: Path) -> Path:
    """Descomprime el zip en ``carpeta`` y devuelve la carpeta con NaturalShot.exe y _internal.

    Tolera que la carpeta raíz tenga cualquier nombre (o que no haya). Rechaza rutas
    que se salgan de ``carpeta``."""
    carpeta = Path(carpeta).resolve()
    carpeta.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archivo_zip) as z:
            total = 0
            for info in z.infolist():
                nombre = info.filename.replace("\\", "/")
                partes = PurePosixPath(nombre).parts
                if nombre.startswith("/") or ".." in partes or ":" in nombre:
                    raise PaqueteInvalido(f"El zip tiene una ruta no permitida: {info.filename!r}.")
                if not (carpeta / nombre).resolve().is_relative_to(carpeta):
                    raise PaqueteInvalido(f"El zip tiene una ruta no permitida: {info.filename!r}.")
                total += info.file_size
            if total > 4 * 1024 ** 3:
                raise PaqueteInvalido("El zip es demasiado grande.")
            z.extractall(carpeta)
    except zipfile.BadZipFile:
        raise PaqueteInvalido("El archivo bajado no es un zip válido.") from None
    candidatas = [carpeta] + sorted(p for p in carpeta.iterdir() if p.is_dir())
    validas = [c for c in candidatas if _es_carpeta_app(c)]
    if len(validas) != 1:
        raise PaqueteInvalido("El zip no tiene la carpeta de NaturalShot (NaturalShot.exe con _internal)."
                              if not validas else "El zip tiene más de una copia de NaturalShot.")
    return validas[0]


def _es_carpeta_app(carpeta: Path) -> bool:
    exe, interna = carpeta / NOMBRE_EXE, carpeta / CARPETA_INTERNA
    return exe.is_file() and exe.stat().st_size > 0 and interna.is_dir() and any(interna.iterdir())


# ------------------------------------------------------------------ instalación
def carpeta_instalacion() -> Optional[Path]:
    """La carpeta del .exe que está corriendo (None desde el código)."""
    return Path(sys.executable).resolve().parent if compilada() else None


def validar_instalacion(carpeta: Path) -> Path:
    """Comprueba que ``carpeta`` sea una instalación de NaturalShot que se pueda reemplazar."""
    carpeta = Path(carpeta).resolve()
    if carpeta.parent == carpeta:
        raise ErrorActualizacion("NaturalShot está en la raíz de un disco: no se puede actualizar sola.")
    sistema = Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve()
    if carpeta == sistema or carpeta.is_relative_to(sistema) or carpeta == Path.home().resolve():
        raise ErrorActualizacion("NaturalShot está en una carpeta del sistema: no se puede actualizar sola.")
    if not _es_carpeta_app(carpeta):
        raise ErrorActualizacion("No encontré NaturalShot.exe con su carpeta _internal en la carpeta de la app.")
    return carpeta


def se_puede_escribir(carpeta: Path) -> bool:
    """Prueba de verdad (os.access no sirve en Windows): crea y borra un archivo."""
    for lugar in (Path(carpeta), Path(carpeta) / CARPETA_INTERNA):
        try:
            with tempfile.NamedTemporaryFile(dir=lugar, prefix=".naturalshot-prueba-", delete=True):
                pass
        except OSError:
            return False
    return True


def espacio_suficiente(carpeta_temporal: Path, instalacion: Path, tamano_zip: int) -> bool:
    """Hacen falta el zip, lo descomprimido y el respaldo (más o menos 3,5 veces el zip)."""
    try:
        temporal = shutil.disk_usage(carpeta_temporal).free
        destino = shutil.disk_usage(instalacion).free
    except OSError:
        return True
    if Path(carpeta_temporal).anchor.lower() == Path(instalacion).anchor.lower():
        return temporal > tamano_zip * 4
    return temporal > tamano_zip * 4 and destino > tamano_zip * 1.5


def nueva_carpeta_trabajo() -> Path:
    return Path(tempfile.mkdtemp(prefix=PREFIJO_TEMPORAL))


def limpiar_temporales_viejos(dias: float = 3) -> None:
    """Borra carpetas de actualizaciones que quedaron a medias (salvo las marcadas CONSERVAR)."""
    limite = time.time() - dias * 86400
    try:
        for carpeta in Path(tempfile.gettempdir()).glob(PREFIJO_TEMPORAL + "*"):
            try:
                if (carpeta.is_dir() and carpeta.stat().st_mtime < limite
                        and not (carpeta / "CONSERVAR.txt").exists()):
                    shutil.rmtree(carpeta, ignore_errors=True)
            except OSError:
                pass
    except OSError:
        pass


_COMILLAS_SIMPLES = "'\u2018\u2019\u201a\u201b"  # PowerShell toma todas como comilla simple


def literal_ps(texto: str) -> str:
    """Texto literal de PowerShell entre comillas simples (sin expansión de variables)."""
    texto = str(texto)
    if any(c in texto for c in "\r\n\0"):
        raise ValueError("El texto tiene caracteres no permitidos.")
    return "'" + "".join(c + c if c in _COMILLAS_SIMPLES else c for c in texto) + "'"


_PLANTILLA_SCRIPT = r"""# Instalador de NaturalShot PRO, generado por la app. Se borra solo al terminar.
# Solo toca la carpeta de instalación indicada abajo: reemplaza su carpeta _internal
# (robocopy /MIR) y los archivos sueltos del paquete nuevo; lo demás queda como estaba.
$ErrorActionPreference = 'Stop'
$Instalacion = @@INSTALACION@@
$Nueva = @@NUEVA@@
$Trabajo = @@TRABAJO@@
$ArchivoLog = @@LOG@@
$ArchivoResultado = @@RESULTADO@@
$MarcaInicio = @@MARCA@@
$ProcesoApp = @@PID@@
$VersionNueva = @@VERSION_NUEVA@@
$VersionAnterior = @@VERSION_ANTERIOR@@
$Archivos = @(@@ARCHIVOS@@)
$Reabrir = @@REABRIR@@
$SimularFalla = @@SIMULAR_FALLA@@

$Respaldo = Join-Path $Trabajo 'respaldo'
$Exe = Join-Path $Instalacion 'NaturalShot.exe'
$Etapa = 'esperando'
$AppCerrada = $false
$Conservar = $false
$Utf8 = New-Object System.Text.UTF8Encoding($false)

function Anotar([string]$Texto) {
    $linea = '{0}  [instalador] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Texto
    try {
        [void](New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ArchivoLog))
        [System.IO.File]::AppendAllText($ArchivoLog, $linea + "`r`n", $Utf8)
    } catch { }
}

function Informar([string]$Estado, [string]$Detalle) {
    $datos = [ordered]@{ estado = $Estado; detalle = $Detalle; version_nueva = $VersionNueva;
                         version_anterior = $VersionAnterior; fecha = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') }
    try { [System.IO.File]::WriteAllText($ArchivoResultado, ($datos | ConvertTo-Json), $Utf8) } catch { }
}

function Copiar([string]$Origen, [string]$Destino, [string[]]$Opciones) {
    # robocopy sin ventana: hereda la consola oculta de este proceso.
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = Join-Path $env:SystemRoot 'System32\robocopy.exe'
    $psi.Arguments = ('"{0}" "{1}" ' -f $Origen.TrimEnd('\'), $Destino.TrimEnd('\')) + ($Opciones -join ' ')
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $p = [System.Diagnostics.Process]::Start($psi)
    $salida = $p.StandardOutput.ReadToEnd()
    $p.WaitForExit()
    if ($p.ExitCode -ge 8) {
        $ultimas = ($salida -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -Last 4) -join ' | '
        throw ('robocopy terminó con el código {0}: {1}' -f $p.ExitCode, $ultimas)
    }
}

function Restaurar {
    Anotar 'Restaurando la versión anterior desde el respaldo...'
    Copiar (Join-Path $Respaldo '_internal') (Join-Path $Instalacion '_internal') @('/MIR', '/R:5', '/W:2', '/XJ', '/NP', '/NFL', '/NDL')
    foreach ($nombre in $Archivos) {
        $guardado = Join-Path $Respaldo $nombre
        $destino = Join-Path $Instalacion $nombre
        if (Test-Path -LiteralPath $guardado -PathType Leaf) {
            Copy-Item -LiteralPath $guardado -Destination $destino -Force
        } elseif (Test-Path -LiteralPath $destino -PathType Leaf) {
            Remove-Item -LiteralPath $destino -Force  # lo había agregado la versión nueva
        }
    }
    Anotar 'Respaldo restaurado.'
}

try {
    [System.IO.File]::WriteAllText($MarcaInicio, 'ok', $Utf8)  # la app sabe que el instalador arrancó
    Anotar ('Instalando la versión {0} en {1}' -f $VersionNueva, $Instalacion)

    # 1. Esperar a que la app se cierre (y cualquier otra ventana abierta desde esa carpeta).
    $proceso = Get-Process -Id $ProcesoApp -ErrorAction SilentlyContinue
    if ($proceso -and -not $proceso.WaitForExit(180000)) { throw 'La app no se cerró a tiempo.' }
    $AppCerrada = $true
    $limite = (Get-Date).AddSeconds(90)
    while ($true) {
        $otras = @(Get-Process -Name 'NaturalShot' -ErrorAction SilentlyContinue |
                   Where-Object { try { $_.Path -and ($_.Path -ieq $Exe) } catch { $false } })
        if ($otras.Count -eq 0) { break }
        if ((Get-Date) -gt $limite) { throw 'Hay otra ventana de NaturalShot abierta. Cerrala y probá de nuevo.' }
        Start-Sleep -Milliseconds 500
    }
    Start-Sleep -Milliseconds 700  # Windows libera los archivos un momento después

    if (-not (Test-Path -LiteralPath $Exe -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $Instalacion '_internal') -PathType Container)) {
        throw 'La carpeta de instalación no tiene NaturalShot.exe con _internal.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Nueva 'NaturalShot.exe') -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $Nueva '_internal') -PathType Container)) {
        throw 'La versión nueva no tiene NaturalShot.exe con _internal.'
    }

    # 2. Respaldo de lo que se va a reemplazar.
    $Etapa = 'respaldo'
    Anotar 'Haciendo el respaldo de la versión instalada...'
    Copiar (Join-Path $Instalacion '_internal') (Join-Path $Respaldo '_internal') @('/E', '/R:3', '/W:1', '/XJ', '/NP', '/NFL', '/NDL')
    foreach ($nombre in $Archivos) {
        $actual = Join-Path $Instalacion $nombre
        if (Test-Path -LiteralPath $actual -PathType Leaf) {
            Copy-Item -LiteralPath $actual -Destination (Join-Path $Respaldo $nombre) -Force
        }
    }

    # 3. Copiar la versión nueva encima.
    $Etapa = 'copiando'
    Anotar 'Copiando la versión nueva...'
    Copiar (Join-Path $Nueva '_internal') (Join-Path $Instalacion '_internal') @('/MIR', '/R:5', '/W:2', '/XJ', '/NP', '/NFL', '/NDL')
    if ($SimularFalla) { throw 'Falla simulada a mitad de la copia (modo de prueba).' }
    foreach ($nombre in $Archivos) {
        Copy-Item -LiteralPath (Join-Path $Nueva $nombre) -Destination (Join-Path $Instalacion $nombre) -Force
    }
    $Etapa = 'listo'
    Informar 'ok' ''
    Anotar ('Listo: versión {0} instalada.' -f $VersionNueva)
} catch {
    $detalle = $_.Exception.Message
    Anotar ('Error en la etapa "{0}": {1}' -f $Etapa, $detalle)
    if ($Etapa -eq 'copiando') {
        try {
            Restaurar
            Informar 'restaurado' $detalle
        } catch {
            $Conservar = $true
            Anotar ('No se pudo restaurar: {0}. El respaldo quedó en {1}' -f $_.Exception.Message, $Respaldo)
            Informar 'error' ('{0}. El respaldo quedó en {1}' -f $detalle, $Respaldo)
            try { [System.IO.File]::WriteAllText((Join-Path $Trabajo 'CONSERVAR.txt'), 'Respaldo de NaturalShot', $Utf8) } catch { }
        }
    } else {
        Informar 'abortado' $detalle
    }
}

# 4. Volver a abrir NaturalShot (solo si la app llegó a cerrarse) y borrar los temporales.
if ($Reabrir -and $AppCerrada -and (Test-Path -LiteralPath $Exe -PathType Leaf)) {
    try {
        Start-Process -FilePath $Exe -WorkingDirectory $Instalacion
        Anotar 'NaturalShot abierta de nuevo.'
    } catch { Anotar ('No se pudo volver a abrir NaturalShot: {0}' -f $_.Exception.Message) }
}
if (-not $Conservar) {
    Set-Location -LiteralPath $env:SystemRoot
    [System.IO.Directory]::SetCurrentDirectory($env:SystemRoot)  # para poder borrar la carpeta de trabajo
    Remove-Item -LiteralPath $Trabajo -Recurse -Force -ErrorAction SilentlyContinue
}
"""


@dataclass
class PaqueteListo:
    """Lo que deja la descarga: el zip verificado y descomprimido en la carpeta de trabajo."""
    novedad: Novedad
    trabajo: Path
    nueva: Path  # carpeta con NaturalShot.exe y _internal
    archivos: tuple[str, ...] = field(default=())  # archivos sueltos de la versión nueva (el .exe)


def preparar_paquete(novedad: Novedad, trabajo: Path, progreso=None, cancelado=lambda: False,
                     sesion: Optional[Sesion] = None) -> PaqueteListo:
    """Descarga, verifica y descomprime. Si algo falla, borra la carpeta de trabajo."""
    try:
        archivo = descargar_paquete(novedad, trabajo, progreso, cancelado, sesion)
        if cancelado():
            raise Cancelado()
        nueva = extraer_paquete(archivo, Path(trabajo) / "nueva")
        archivo.unlink(missing_ok=True)  # ya no hace falta: libera espacio
        archivos = tuple(sorted(p.name for p in nueva.iterdir() if p.is_file()))
        registrar(f"Paquete listo en {nueva} ({', '.join(archivos)}).")
        return PaqueteListo(novedad, Path(trabajo), nueva, archivos)
    except BaseException:
        shutil.rmtree(trabajo, ignore_errors=True)
        raise


def archivo_resultado() -> Path:
    return carpeta_datos() / ARCHIVO_RESULTADO


def generar_script(paquete: PaqueteListo, instalacion: Path, pid: int, version_actual: str = __version__,
                   reabrir: bool = True, simular_falla: bool = False) -> Path:
    """Escribe ``actualizar.ps1`` en la carpeta de trabajo y devuelve su ruta.

    Todas las rutas van como literales de PowerShell (sin expansión). El script solo
    modifica ``instalacion\\_internal`` y los archivos sueltos de la versión nueva."""
    instalacion = validar_instalacion(instalacion)
    trabajo = Path(paquete.trabajo).resolve()
    nueva = Path(paquete.nueva).resolve()
    if not nueva.is_relative_to(trabajo) or not _es_carpeta_app(nueva):
        raise PaqueteInvalido("La versión nueva no está en la carpeta de trabajo.")
    if instalacion.is_relative_to(trabajo) or trabajo.is_relative_to(instalacion):
        raise ErrorActualizacion("La carpeta de trabajo no puede estar dentro de la instalación (ni al revés).")
    for nombre in paquete.archivos:
        if not nombre or any(c in nombre for c in '\\/:*?"<>|') or nombre in (".", ".."):
            raise PaqueteInvalido(f"Nombre de archivo no permitido en el paquete: {nombre!r}.")
    if NOMBRE_EXE not in paquete.archivos:
        raise PaqueteInvalido("El paquete no tiene NaturalShot.exe.")
    valores = {
        "INSTALACION": literal_ps(str(instalacion)),
        "NUEVA": literal_ps(str(nueva)),
        "TRABAJO": literal_ps(str(trabajo)),
        "LOG": literal_ps(str(archivo_log())),
        "RESULTADO": literal_ps(str(archivo_resultado())),
        "MARCA": literal_ps(str(trabajo / "instalador_iniciado.txt")),
        "PID": str(int(pid)),
        "VERSION_NUEVA": literal_ps(paquete.novedad.version),
        "VERSION_ANTERIOR": literal_ps(version_actual),
        "ARCHIVOS": ", ".join(literal_ps(n) for n in paquete.archivos),
        "REABRIR": "$true" if reabrir else "$false",
        "SIMULAR_FALLA": "$true" if simular_falla else "$false",
    }
    texto = _PLANTILLA_SCRIPT
    for clave, valor in valores.items():
        texto = texto.replace(f"@@{clave}@@", valor)
    script = trabajo / "actualizar.ps1"
    script.write_text(texto, encoding="utf-8-sig")  # con BOM: PowerShell 5.1 lo lee como UTF-8
    return script


def marca_inicio(script: Path) -> Path:
    return Path(script).parent / "instalador_iniciado.txt"


def entorno_instalador() -> dict:
    """El entorno de la app sin las variables internas de PyInstaller, para que la
    versión nueva arranque como una app recién abierta."""
    entorno = {k: v for k, v in os.environ.items() if not k.upper().startswith(("_PYI_", "_MEIPASS"))}
    entorno["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return entorno


def lanzar_instalador(script: Path) -> subprocess.Popen:
    """Lanza el script separado de la app y sin ventana.

    No se usa DETACHED_PROCESS: PowerShell 5.1 lanzado así termina sin ejecutar nada
    (lo medimos). Con CREATE_NO_WINDOW tiene una consola oculta, que heredan robocopy
    y los demás comandos; CREATE_NEW_PROCESS_GROUP y CREATE_BREAKAWAY_FROM_JOB lo
    separan de la app, así que sigue corriendo cuando la app se cierra."""
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    argumentos = [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    sin_ventana, grupo, fuera_del_job = 0x08000000, 0x00000200, 0x01000000
    for banderas in (sin_ventana | grupo | fuera_del_job, sin_ventana | grupo):
        try:
            proceso = subprocess.Popen(argumentos, creationflags=banderas, close_fds=True, cwd=tempfile.gettempdir(),
                                       env=entorno_instalador(), stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            registrar(f"Instalador lanzado (PID {proceso.pid}).")
            return proceso
        except OSError as error:  # el job de la app no permite separarse: sin esa bandera
            registrar(f"Instalador: no se pudo lanzar con banderas {banderas:#x} ({error}).")
    raise ErrorActualizacion("No se pudo iniciar el instalador.")


def leer_resultado_anterior() -> Optional[dict]:
    """Lo que dejó el instalador la última vez (y lo borra), o None."""
    ruta = archivo_resultado()
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    finally:
        try:
            ruta.unlink()
        except OSError:
            pass
    return datos if isinstance(datos, dict) else None
