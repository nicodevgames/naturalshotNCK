"""La edición de la app: **NaturalShot PRO** (fotos, video y audio) o **NaturalShot Lite** (solo fotos).

Hay una sola base de código. Lo que cambia en la Lite (sin modo Video ni Audio, otro nombre,
la insignia LITE, sus propios datos y sin actualizaciones automáticas) se decide acá:

1. la variable de entorno ``NATURALSHOT_EDICION`` ("pro" o "lite"; ``ejecutar_lite.bat`` la
   pone en "lite");
2. si no está (o tiene otra cosa), en el .exe, el archivo ``edicion.txt`` que deja
   ``NaturalShot Lite.spec`` en ``_internal`` (``sys._MEIPASS``) o uno junto al ejecutable;
3. si no hay nada, "pro": así nada de la PRO cambia.

Las funciones vuelven a mirar la variable cada vez que se las llama (es barato), así las
pruebas cambian de edición con ``mock.patch.dict(os.environ)`` sin recargar el módulo.
``EDICION`` es la edición al importar, para leerla de un vistazo.

``ruta_recurso`` elige el ícono, el logo y el tutorial de cada edición (los de la Lite, si
están; si no, los de siempre).

No usa Qt ni nada pesado: lo importan ``main.py``, la sesión y la pantalla de carga.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PRO, LITE = "pro", "lite"
VARIABLE = "NATURALSHOT_EDICION"
ARCHIVO = "edicion.txt"           # lo deja el .spec de la Lite (con "lite" adentro)
MARCA = "NaturalShot"             # la marca; también la organización de los QSettings
_NOMBRES = {PRO: "NaturalShot PRO", LITE: "NaturalShot Lite"}
_INSIGNIAS = {PRO: "PRO", LITE: "LITE"}


def _normalizar(valor) -> str | None:
    """ "pro" o "lite" (sin importar mayúsculas, espacios ni BOM); otra cosa, None."""
    if not isinstance(valor, str):
        return None
    valor = valor.strip().lstrip("﻿").strip().lower()
    return valor if valor in (PRO, LITE) else None


def _de_archivo() -> str | None:
    """En el .exe: ``edicion.txt`` en ``_internal`` o junto al ejecutable. Desde el código, nada."""
    if not getattr(sys, "frozen", False):
        return None
    carpetas = []
    if getattr(sys, "_MEIPASS", None):
        carpetas.append(Path(sys._MEIPASS))
    carpetas.append(Path(sys.executable).resolve().parent)
    for carpeta in carpetas:
        try:
            edicion = _normalizar((carpeta / ARCHIVO).read_text(encoding="utf-8")[:64])
        except (OSError, UnicodeDecodeError):
            continue
        if edicion is not None:
            return edicion
    return None


def edicion_actual() -> str:
    """ "pro" o "lite", según la variable, el ``edicion.txt`` del .exe o, si no hay nada, "pro"."""
    return _normalizar(os.environ.get(VARIABLE)) or _de_archivo() or PRO


def es_lite() -> bool:
    return edicion_actual() == LITE


def nombre_app() -> str:
    """ "NaturalShot PRO" o "NaturalShot Lite": el título de la ventana, la carga y el "Acerca de"."""
    return _NOMBRES[edicion_actual()]


def insignia() -> str:
    """ "PRO" o "LITE": la pastilla junto al nombre."""
    return _INSIGNIAS[edicion_actual()]


def carpeta_datos() -> Path:
    """``%APPDATA%\\NaturalShot PRO`` o ``%APPDATA%\\NaturalShot Lite``: sesión, logs y temporales.
    Las dos ediciones no se mezclan."""
    return Path(os.environ.get("APPDATA") or Path.home()) / nombre_app()


def organizacion_qsettings() -> tuple[str, str]:
    """(organización, aplicación) de los QSettings: ("NaturalShot", "NaturalShot PRO" | "NaturalShot Lite")."""
    return MARCA, nombre_app()


# ------------------------------------------------------------------ recursos (ícono, logo y tutorial)
# En la Lite, estos tienen su propia versión en assets\ (si falta, se usa la de siempre).
RECURSOS_LITE = {"icono.ico": "icono_lite.ico", "logo.png": "logo_lite.png", "tutorial.pdf": "tutorial_lite.pdf"}


def carpeta_recursos() -> Path:
    """Donde están ``assets\\``: ``_internal`` en el .exe (``sys._MEIPASS``), la carpeta del proyecto desde el código."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def ruta_recurso(relativa: str) -> Path:
    """La ruta de un recurso (por ejemplo, "assets/logo.png"). En la Lite, el ícono, el logo y el
    tutorial salen de su versión Lite ("assets/logo_lite.png") si existe; si no, del de siempre."""
    base = carpeta_recursos()
    ruta = base / relativa
    lite = RECURSOS_LITE.get(ruta.name)
    if lite is not None and es_lite():
        propia = ruta.with_name(lite)
        if propia.is_file():
            return propia
    return ruta


def ruta_logo() -> Path:
    """El logo (la marca de la ventana, la pantalla de carga y el tutorial): ``logo.png`` o ``logo_lite.png``."""
    return ruta_recurso("assets/logo.png")


def ruta_icono() -> Path:
    """El ícono de la app (ventana y barra de tareas): ``icono.ico`` o ``icono_lite.ico``."""
    return ruta_recurso("assets/icono.ico")


EDICION: str = edicion_actual()
