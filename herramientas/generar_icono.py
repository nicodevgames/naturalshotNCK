"""Genera assets/icono.ico y assets/logo.png.

El logo es una foto (marco con montaña y sol, ícono "image" de Lucide) con un
destello, en blanco sobre un cuadrado redondeado con degradado magenta → violeta.
Comunica "editor de fotos" de un vistazo. Se dibuja con Qt para reutilizar los
mismos SVG de la interfaz.

Uso:  python herramientas/generar_icono.py
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QByteArray, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
ICONOS = RAIZ / "assets" / "iconos"


def _svg_blanco(nombre: str, trazo: float) -> QSvgRenderer:
    datos = (ICONOS / f"{nombre}.svg").read_bytes()
    datos = datos.replace(b"currentColor", b"#ffffff").replace(b'stroke-width="2"', f'stroke-width="{trazo}"'.encode())
    return QSvgRenderer(QByteArray(datos))


def dibujar(tam: int = 1024) -> QImage:
    img = QImage(tam, tam, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    # Fondo: cuadrado redondeado con degradado diagonal y un brillo arriba.
    fondo = QPainterPath()
    fondo.addRoundedRect(QRectF(0, 0, tam, tam), tam * 0.24, tam * 0.24)
    grad = QLinearGradient(QPointF(0, 0), QPointF(tam, tam))
    grad.setColorAt(0.0, QColor("#ec4899"))
    grad.setColorAt(0.45, QColor("#d946ef"))
    grad.setColorAt(1.0, QColor("#6d28d9"))
    p.fillPath(fondo, grad)
    brillo = QLinearGradient(QPointF(0, 0), QPointF(0, tam * 0.6))
    brillo.setColorAt(0.0, QColor(255, 255, 255, 60))
    brillo.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillPath(fondo, brillo)

    # Foto (marco + montaña + sol) en una capa aparte, con un hueco donde va el destello.
    import math
    cx, cy, r = tam * 0.735, tam * 0.27, tam * 0.15
    capa = QImage(tam, tam, QImage.Format_ARGB32)
    capa.fill(Qt.transparent)
    pc = QPainter(capa)
    pc.setRenderHint(QPainter.Antialiasing)
    _svg_blanco("image", 1.9).render(pc, QRectF(tam * 0.17, tam * 0.20, tam * 0.62, tam * 0.62))
    pc.setCompositionMode(QPainter.CompositionMode_DestinationOut)
    pc.setPen(Qt.NoPen)
    pc.setBrush(QColor(0, 0, 0, 255))
    pc.drawEllipse(QPointF(cx, cy), r * 0.98, r * 0.98)
    pc.end()
    p.drawImage(0, 0, capa)

    # Destello de cuatro puntas
    estrella = QPainterPath()
    for i in range(8):
        ang = i * math.pi / 4
        rr = r * (0.9 if i % 2 == 0 else 0.26)
        x, y = cx + rr * math.sin(ang), cy - rr * math.cos(ang)
        estrella.moveTo(x, y) if i == 0 else estrella.lineTo(x, y)
    estrella.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#ffffff"))
    p.drawPath(estrella)
    p.end()
    return img


def a_pil(img: QImage) -> Image.Image:
    buf = QBuffer()
    buf.open(QBuffer.WriteOnly)
    img.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    grande = a_pil(dibujar(1024))
    grande.resize((256, 256), Image.LANCZOS).save(RAIZ / "assets" / "logo.png")
    grande.resize((256, 256), Image.LANCZOS).save(
        RAIZ / "assets" / "icono.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Generados assets/icono.ico y assets/logo.png")
