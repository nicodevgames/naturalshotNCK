"""Íconos de línea (Lucide, SVG monocromo) que toman el color del tema.

Reemplazan a los emojis de colores. Cada SVG de ``assets/iconos`` usa
``stroke="currentColor"``: al dibujarlo se reemplaza por el color del tema y el
trazo se afina, así todos quedan uniformes, con fondo transparente y se
adaptan solos si cambia la paleta (claro u oscuro).
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import estilo

_CARPETA = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "assets" / "iconos"
TRAZO = 1.6  # Lucide trae 2: más fino queda más prolijo a 16-20 px

# Nombres de Lucide (archivo sin .svg)
ABRIR = "folder-open"
GUARDAR = "download"
CAPAS = "layers"      # el panel Capas (capas de verdad del documento)
EFECTOS = "sparkle"   # la tarjeta Efectos (presets apilados; antes "Capas")
PRESET = "sliders-horizontal"
CELULAR = "smartphone"

ICONO_PRESET = {
    "Celular natural — inspirado en iPhone 13": "smartphone",
    "Celular natural — sutil": "feather",
    "Celular natural — marcado": "flame",
    "Anti IA — piel real, sin calidad exagerada": "scan-face",
    "Estilo iPhone 15 Pro": "gem",
    "Estilo iPhone 11": "apple",
    "Estilo iPhone 8 / X": "history",
    "Estilo Samsung Galaxy S23": "sparkles",
    "Estilo Samsung Galaxy A (gama media)": "tablet-smartphone",
    "Estilo Google Pixel 8": "camera",
    "Estilo Xiaomi Redmi": "circle-dot",
    "Estilo Motorola Moto G": "smartphone-charging",
    "Exterior soleado": "sun",
    "Día nublado": "cloud",
    "Paisaje con HDR": "mountain",
    "Interior con luz cálida": "lamp",
    "Interior con poca luz": "moon",
    "Noche urbana": "building-2",
    "Selfie con cámara frontal": "user-round",
    "Retrato con luz de ventana": "app-window",
    "Comida y restaurante": "utensils",
    "Colores vivos": "palette",
    "Celular de gama básica": "camera",
    "Foto reenviada por mensajería": "message-circle",
    "Solo textura (sin tocar el color)": "grid-3x3",
    "Solo color y tono (sin textura)": "paintbrush",
    "Sin efecto": "ban",
}

ICONO_GRUPO = {
    "Detalle": "scan-search",
    "Ruido de sensor": "cpu",
    "Luces, sombras y color": "sun-moon",
    "Imperfecciones ópticas": "aperture",
}


@lru_cache(maxsize=None)
def _svg(nombre: str) -> bytes:
    ruta = _CARPETA / f"{nombre}.svg"
    return ruta.read_bytes() if ruta.exists() else b""


@lru_cache(maxsize=None)
def pixmap(nombre: str, tam: int = 18, color: str | None = None, escala: float = 2.0) -> QPixmap:
    """Ícono dibujado en ``color`` (por defecto el texto secundario del tema).

    Se genera al doble de tamaño y se marca el ratio, para que quede nítido en
    pantallas con escalado.
    """
    datos = _svg(nombre)
    lado = round(tam * escala)
    pm = QPixmap(lado, lado)
    pm.fill(Qt.transparent)
    if datos:
        datos = (datos.replace(b"currentColor", (color or estilo.TEXTO_2).encode())
                      .replace(b'stroke-width="2"', f'stroke-width="{TRAZO}"'.encode()))
        render = QSvgRenderer(QByteArray(datos))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        render.render(p, QRectF(0, 0, lado, lado))
        p.end()
    pm.setDevicePixelRatio(escala)
    return pm


@lru_cache(maxsize=None)
def icono(nombre: str, tam: int = 18, color: str | None = None) -> QIcon:
    """QIcon con un color por estado: normal, activo/seleccionado y deshabilitado.

    ``color`` fija el color normal (por ejemplo blanco sobre un botón con degradado).
    """
    ic = QIcon()
    ic.addPixmap(pixmap(nombre, tam, color or estilo.TEXTO_2), QIcon.Normal)
    ic.addPixmap(pixmap(nombre, tam, color or estilo.TEXTO), QIcon.Active)
    ic.addPixmap(pixmap(nombre, tam, color or estilo.TEXTO), QIcon.Selected)
    ic.addPixmap(pixmap(nombre, tam, estilo.TEXTO_TENUE), QIcon.Disabled)
    return ic


def icono_preset(nombre: str) -> QIcon:
    return icono(ICONO_PRESET.get(nombre, CELULAR))


def limpiar_cache() -> None:
    """Llamar si cambia la paleta (tema claro/oscuro) para redibujar con el color nuevo."""
    pixmap.cache_clear()
    icono.cache_clear()
