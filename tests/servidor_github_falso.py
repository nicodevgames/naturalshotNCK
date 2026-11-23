"""Servidor HTTP local que imita lo que usa el actualizador de GitHub (para las pruebas).

* ``POST /login/device/code`` y ``POST /login/oauth/access_token`` (device flow y
  renovación con refresh token), con respuestas programables: ``authorization_pending``,
  ``slow_down``, ``expired_token``, ``access_denied``…
* ``GET /repos/<repo>/releases/latest`` y ``GET /user``, que piden ``Authorization: Bearer``.
* ``GET /repos/<repo>/releases/assets/<id>`` con ``Accept: application/octet-stream``:
  responde **302** a una URL "firmada" en otro host (``[::1]``, o ``localhost`` si la PC
  no tiene IPv6, en vez de ``127.0.0.1``), que falla con 400 si le llega el encabezado
  ``Authorization``, como las URL firmadas de verdad.

Anota cada pedido (ruta, host y encabezados) en ``pedidos`` para revisarlo después.
"""

from __future__ import annotations

import hashlib
import io
import json
import socket
import threading
import urllib.parse
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from celular_natural.actualizador import REPOSITORIO as REPO


def zip_de_prueba(raiz: str = "NaturalShot PRO", contenido_exe: bytes = b"MZ exe de prueba",
                  extra: Optional[dict] = None, leeme: bool = True) -> bytes:
    """Un zip con la forma del paquete publicado: <raiz>/NaturalShot.exe, <raiz>/_internal/… y LEEME.txt."""
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as z:
        prefijo = f"{raiz}/" if raiz else ""
        z.writestr(f"{prefijo}NaturalShot.exe", contenido_exe)
        z.writestr(f"{prefijo}_internal/base_library.zip", b"biblioteca")
        z.writestr(f"{prefijo}_internal/PySide6/plugins/leeme.txt", b"plugin")
        for nombre, datos in (extra or {}).items():
            z.writestr(nombre, datos)
        if leeme:
            z.writestr("LEEME.txt", "Leeme de prueba".encode("utf-8"))
    return memoria.getvalue()


def manifiesto(version: str, datos_zip: bytes, sha: Optional[str] = None, notas=None, minima="1.0.0",
               obligatoria: Optional[str] = None) -> dict:
    man = {"version": version, "fecha": "2026-10-13",
           "notas": list(notas if notas is not None else ["Aviso de actualizaciones", "Arreglos menores"]),
           "zip": "NaturalShot-PRO.zip", "sha256": sha or hashlib.sha256(datos_zip).hexdigest(),
           "tamano": len(datos_zip), "minima": minima}
    if obligatoria is not None:
        man["obligatoria"] = obligatoria
    return man


class ServidorGitHubFalso:
    def __init__(self, token_valido: str = "ghu_tokenDePrueba123456", repo: str = REPO):
        self.repo = repo
        self.tokens_validos = {token_valido}
        self.refresh_validos: set[str] = set()
        self.assets: dict[int, tuple[str, bytes]] = {}
        self.release: Optional[dict] = None
        self.respuestas_token: list[dict] = []  # se consumen en orden en cada sondeo del device flow
        self.respuesta_codigo: dict = {"device_code": "dc_secreto_0123456789", "user_code": "WDJB-MJHT",
                                       "expires_in": 900, "interval": 5}
        self.token_nuevo = "ghu_tokenNuevoDelDeviceFlow99"
        self.refresh_nuevo = "ghr_refreshNuevoDelDeviceFlow99"
        self.expira = 28800
        self.estado_release: Optional[int] = None  # forzar 403/404 en releases/latest
        self.limite_agotado = False
        self.publico = False  # True: releases y assets responden sin Authorization (repositorio público)
        self.pedidos: list[dict] = []
        self.violaciones: list[str] = []  # Authorization reenviado a la URL firmada
        self._candado = threading.Lock()
        servidor = self

        class Manejador(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):  # silencio
                pass

            def _anotar(self, cuerpo: bytes = b""):
                with servidor._candado:
                    servidor.pedidos.append({"metodo": self.command, "ruta": self.path,
                                             "host": self.headers.get("Host", ""),
                                             "encabezados": {k.lower(): v for k, v in self.headers.items()},
                                             "cuerpo": cuerpo.decode("utf-8", "replace")})

            def _responder(self, codigo: int, datos=b"", tipo="application/json", extra=None):
                if isinstance(datos, (dict, list)):
                    datos = json.dumps(datos).encode("utf-8")
                self.send_response(codigo)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(datos)))
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(datos)

            def _token(self) -> Optional[str]:
                valor = self.headers.get("Authorization", "")
                return valor[7:] if valor.startswith("Bearer ") else None

            def do_POST(self):
                largo = int(self.headers.get("Content-Length") or 0)
                cuerpo = self.rfile.read(largo)
                self._anotar(cuerpo)
                campos = dict(urllib.parse.parse_qsl(cuerpo.decode("ascii")))
                if self.path == "/login/device/code":
                    datos = dict(servidor.respuesta_codigo)
                    datos.setdefault("verification_uri", f"http://127.0.0.1:{servidor.puerto}/login/device")
                    return self._responder(200, datos)
                if self.path == "/login/oauth/access_token":
                    if campos.get("grant_type") == "refresh_token":
                        if campos.get("refresh_token") in servidor.refresh_validos:
                            servidor.refresh_validos.discard(campos["refresh_token"])
                            nuevo = servidor.token_nuevo + "R"
                            servidor.tokens_validos.add(nuevo)
                            servidor.refresh_validos.add(servidor.refresh_nuevo + "R")
                            return self._responder(200, {"access_token": nuevo, "expires_in": servidor.expira,
                                                         "refresh_token": servidor.refresh_nuevo + "R",
                                                         "refresh_token_expires_in": 15897600,
                                                         "token_type": "bearer", "scope": ""})
                        return self._responder(200, {"error": "bad_refresh_token"})
                    if servidor.respuestas_token:
                        respuesta = servidor.respuestas_token.pop(0)
                    else:
                        respuesta = {"access_token": servidor.token_nuevo, "expires_in": servidor.expira,
                                     "refresh_token": servidor.refresh_nuevo, "refresh_token_expires_in": 15897600,
                                     "token_type": "bearer", "scope": ""}
                    if "access_token" in respuesta:
                        servidor.tokens_validos.add(respuesta["access_token"])
                        if respuesta.get("refresh_token"):
                            servidor.refresh_validos.add(respuesta["refresh_token"])
                    return self._responder(200, respuesta)
                return self._responder(404, {"message": "Not Found"})

            def do_GET(self):
                self._anotar()
                ruta = urllib.parse.urlsplit(self.path).path
                if ruta.startswith("/firmado/"):
                    # URL firmada de "otro dominio": no admite Authorization (como las de verdad).
                    if "Authorization" in self.headers:
                        servidor.violaciones.append(self.path)
                        return self._responder(400, b"<Error>Only one auth mechanism allowed</Error>",
                                               "application/xml")
                    asset = servidor.assets.get(int(ruta.rsplit("/", 1)[1]))
                    if asset is None:
                        return self._responder(404, b"no")
                    return self._responder(200, asset[1], "application/octet-stream")
                if servidor.limite_agotado:
                    return self._responder(403, {"message": "API rate limit exceeded"},
                                           extra={"X-RateLimit-Remaining": "0"})
                token = self._token()
                anonimo = servidor.publico and token is None and ruta != "/user"
                if token not in servidor.tokens_validos and not anonimo:
                    return self._responder(401, {"message": "Bad credentials"})
                if ruta == "/user":
                    return self._responder(200, {"login": "editora-prueba"})
                base = f"/repos/{servidor.repo}/releases"
                if ruta == base + "/latest":
                    if servidor.estado_release:
                        return self._responder(servidor.estado_release, {"message": "Not Found"})
                    if servidor.release is None:
                        return self._responder(404, {"message": "Not Found"})
                    return self._responder(200, servidor.release)
                if ruta.startswith(base + "/assets/"):
                    if servidor.estado_release:
                        return self._responder(servidor.estado_release, {"message": "Not Found"})
                    id_asset = int(ruta.rsplit("/", 1)[1])
                    if id_asset not in servidor.assets:
                        return self._responder(404, {"message": "Not Found"})
                    if self.headers.get("Accept") != "application/octet-stream":
                        return self._responder(200, {"id": id_asset, "name": servidor.assets[id_asset][0]})
                    destino = f"{servidor.base_firmada}/firmado/{id_asset}?X-Amz-Signature=abc123"
                    return self._responder(302, b"", "text/plain", {"Location": destino})
                return self._responder(404, {"message": "Not Found"})

        self._http = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        self._http.daemon_threads = True
        self.puerto = self._http.server_address[1]
        self._servidores = [self._http]
        # Las URL "firmadas" van a otro host. Con IPv6, a [::1] (otro servidor, solo local);
        # si no, a localhost (Windows tarda unos 2 s en descartar ::1 en cada pedido).
        try:
            class _V6(ThreadingHTTPServer):
                address_family = socket.AF_INET6
            v6 = _V6(("::1", 0), Manejador)
            v6.daemon_threads = True
            self._servidores.append(v6)
            self.base_firmada = f"http://[::1]:{v6.server_address[1]}"
        except OSError:
            self.base_firmada = f"http://localhost:{self.puerto}"
        self._hilos = [threading.Thread(target=s.serve_forever, daemon=True) for s in self._servidores]

    # ------------------------------------------------------------ uso
    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.puerto}"

    def __enter__(self):
        self.iniciar()
        return self

    def __exit__(self, *_):
        self.detener()

    def iniciar(self) -> None:
        for hilo in self._hilos:
            hilo.start()

    def detener(self) -> None:
        for s in self._servidores:
            s.shutdown()
            s.server_close()

    def publicar(self, version: str, datos_zip: bytes, sha: Optional[str] = None, notas=None,
                 minima: str = "1.0.0", manifiesto_crudo: Optional[bytes] = None,
                 obligatoria: Optional[str] = None) -> dict:
        """Publica una "release" con version.json y NaturalShot-PRO.zip como assets."""
        man = manifiesto(version, datos_zip, sha, notas, minima, obligatoria)
        crudo = manifiesto_crudo if manifiesto_crudo is not None else json.dumps(man, ensure_ascii=False).encode()
        self.assets = {11: ("version.json", crudo), 22: ("NaturalShot-PRO.zip", datos_zip)}
        self.release = {
            "tag_name": f"v{version}", "name": f"NaturalShot PRO {version}",
            "html_url": f"https://github.com/{self.repo}/releases/tag/v{version}",
            "assets": [{"id": i, "name": n, "size": len(d), "url": f"{self.base}/repos/{self.repo}/releases/assets/{i}"}
                       for i, (n, d) in self.assets.items()],
        }
        return man

    def pedidos_a(self, fragmento: str) -> list[dict]:
        return [p for p in self.pedidos if fragmento in p["ruta"]]
