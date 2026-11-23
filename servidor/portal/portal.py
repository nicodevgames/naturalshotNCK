"""Portal de NaturalShot: la página del link, las descargas y los archivos de la versión en el navegador.

Corre detrás de Caddy (que pone HTTPS y usuario y contraseña). Solo usa la biblioteca estándar.

  GET  /                      la página (index.html)
  GET  /api/version           la última versión publicada en GitHub y sus archivos (5 min en memoria)
  GET  /descargar/<archivo>   redirige al link firmado de GitHub de ese archivo (el token no sale de acá)
  GET  /api/archivos          lo que hay en Exportados (lo que guardó la app en el navegador)
  GET  /exportados/<archivo>  baja un archivo de Exportados
  PUT  /subir/<archivo>       sube un archivo a Entradas (para abrirlo en la app del navegador)

Variables: GITHUB_REPO (dueño/nombre), GITHUB_TOKEN (solo lectura de ese repo), DATOS (carpeta con
Entradas y Exportados), DOMINIO (para el link de la app en el navegador).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote

REPO = os.environ.get("GITHUB_REPO", "nicodevgames/naturalshotNCK")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
DATOS = Path(os.environ.get("DATOS", "/datos"))
DOMINIO = os.environ.get("DOMINIO", "")
ENTRADAS, EXPORTADOS = DATOS / "Entradas", DATOS / "Exportados"
AQUI = Path(__file__).resolve().parent
MAX_SUBIDA = 4 * 1024**3  # 4 GB por archivo
_NOMBRE = re.compile(r"^[^/\\\x00]{1,200}$")

_cache: dict = {"t": 0.0, "datos": None}
_candado = threading.Lock()


class _SinRedireccion(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _github(ruta: str, accept: str = "application/vnd.github+json", seguir: bool = True):
    pedido = urllib.request.Request(f"https://api.github.com{ruta}", headers={
        "Authorization": f"Bearer {TOKEN}", "Accept": accept, "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "naturalshot-portal"})
    abridor = urllib.request.build_opener() if seguir else urllib.request.build_opener(_SinRedireccion)
    return abridor.open(pedido, timeout=15)


def ultima_version() -> dict:
    with _candado:
        if _cache["datos"] is not None and time.time() - _cache["t"] < 300:
            return _cache["datos"]
    try:
        with _github(f"/repos/{REPO}/releases/latest") as r:
            rel = json.load(r)
        datos = {"ok": True, "version": rel.get("name") or rel.get("tag_name"), "fecha": rel.get("published_at", ""),
                 "notas": rel.get("body") or "",
                 "archivos": [{"nombre": a["name"], "tamano": a.get("size", 0)} for a in rel.get("assets", [])]}
    except urllib.error.HTTPError as e:
        datos = {"ok": False, "motivo": "Todavía no hay ninguna versión publicada." if e.code == 404
                 else f"GitHub respondió {e.code}. Revisá el token del servidor."}
    except Exception as e:  # sin internet, DNS, etc.
        datos = {"ok": False, "motivo": f"No se pudo consultar GitHub ({type(e).__name__})."}
    with _candado:
        _cache.update(t=time.time(), datos=datos)
    return datos


def link_firmado(nombre: str) -> str | None:
    with _github(f"/repos/{REPO}/releases/latest") as r:
        rel = json.load(r)
    asset = next((a for a in rel.get("assets", []) if a["name"] == nombre), None)
    if asset is None:
        return None
    try:
        _github(f"/repos/{REPO}/releases/assets/{asset['id']}", "application/octet-stream", seguir=False)
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location", "").startswith("https://"):
            return e.headers["Location"]
        raise
    return None


class Portal(BaseHTTPRequestHandler):
    server_version = "NaturalShotPortal"

    def log_message(self, fmt, *args):  # sin ruido en los registros: solo errores
        pass

    def _json(self, datos, codigo: int = 200) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _nombre(self, prefijo: str) -> str | None:
        nombre = unquote(self.path[len(prefijo):].split("?", 1)[0])
        return nombre if _NOMBRE.match(nombre) and nombre not in (".", "..") else None

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = (AQUI / "index.html").read_text(encoding="utf-8").replace("{{APP}}", f"https://app.{DOMINIO}/")
            cuerpo = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
        elif self.path == "/api/version":
            self._json(ultima_version())
        elif self.path.startswith("/descargar/"):
            nombre = self._nombre("/descargar/")
            try:
                link = link_firmado(nombre) if nombre else None
            except Exception:
                link = None
            if not link:
                return self._json({"error": "Ese archivo no está en la última versión."}, 404)
            self.send_response(302)
            self.send_header("Location", link)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
        elif self.path == "/api/archivos":
            EXPORTADOS.mkdir(parents=True, exist_ok=True)
            archivos = sorted((p for p in EXPORTADOS.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime,
                              reverse=True)
            self._json([{"nombre": p.name, "tamano": p.stat().st_size, "url": "/exportados/" + quote(p.name)}
                        for p in archivos[:200]])
        elif self.path.startswith("/exportados/"):
            nombre = self._nombre("/exportados/")
            ruta = (EXPORTADOS / nombre) if nombre else None
            if not ruta or not ruta.is_file() or ruta.resolve().parent != EXPORTADOS.resolve():
                return self._json({"error": "No existe."}, 404)
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(ruta.stat().st_size))
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(ruta.name)}")
            self.end_headers()
            with open(ruta, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
        else:
            self._json({"error": "No existe."}, 404)

    def do_PUT(self):
        if not self.path.startswith("/subir/"):
            return self._json({"error": "No existe."}, 404)
        nombre = self._nombre("/subir/")
        largo = int(self.headers.get("Content-Length") or 0)
        if not nombre:
            return self._json({"error": "Nombre de archivo inválido."}, 400)
        if largo <= 0 or largo > MAX_SUBIDA:
            return self._json({"error": "El archivo está vacío o pesa más de 4 GB."}, 400)
        ENTRADAS.mkdir(parents=True, exist_ok=True)
        destino = ENTRADAS / nombre
        parcial = destino.with_name("." + destino.name + ".subiendo")
        restante = largo
        with open(parcial, "wb") as f:
            while restante > 0:
                bloque = self.rfile.read(min(restante, 1024 * 1024))
                if not bloque:
                    break
                f.write(bloque)
                restante -= len(bloque)
        if restante:
            parcial.unlink(missing_ok=True)
            return self._json({"error": "La subida se cortó."}, 400)
        os.replace(parcial, destino)
        self._json({"ok": True, "nombre": destino.name})


if __name__ == "__main__":
    for carpeta in (ENTRADAS, EXPORTADOS):
        carpeta.mkdir(parents=True, exist_ok=True)
    print(f"Portal de NaturalShot en :8000 (repo {REPO})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8000), Portal).serve_forever()
