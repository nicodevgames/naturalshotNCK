"""Presets guardados por el usuario (JSON en %APPDATA%\\NaturalShot; en la Lite, en %APPDATA%\\NaturalShot Lite)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .. import edicion
from ..motor import Ajustes


def _archivo() -> Path:
    if edicion.es_lite():  # los suyos, sin mezclarse con los de la PRO
        return edicion.carpeta_datos() / "presets.json"
    base = Path(os.environ.get("APPDATA") or Path.home()) / "NaturalShot"
    return base / "presets.json"


def cargar() -> dict[str, Ajustes]:
    try:
        datos = json.loads(_archivo().read_text(encoding="utf-8"))
        return {n: Ajustes.desde_dict(d) for n, d in datos.items()}
    except Exception:
        return {}


def guardar(nombre: str, ajustes: Ajustes) -> None:
    todos = {n: a.como_dict() for n, a in cargar().items()}
    todos[nombre] = ajustes.como_dict()
    _escribir(todos)


def borrar(nombre: str) -> None:
    todos = {n: a.como_dict() for n, a in cargar().items() if n != nombre}
    _escribir(todos)


def _escribir(todos: dict) -> None:
    ruta = _archivo()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(todos, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, ruta)
