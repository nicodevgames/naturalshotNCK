"""Política de metadatos de salida (NS-104): un solo lugar decide qué EXIF sale de la app.

Se aplica a toda foto exportada (``imagen_io.exportar_imagen``: foto única, lote y Lite)
cuando el usuario elige "Conservar metadatos EXIF". Sin esa opción no sale ningún EXIF.

Qué hace con el EXIF del original:

* **Privacidad**: se quitan siempre la ubicación (todo el bloque GPS), los números de serie
  de cámara y lente, el dueño de la cámara, el nombre de la PC, el nombre del documento,
  el identificador único de la foto, la nota del fabricante (``MakerNote``, donde las
  cámaras guardan seriales y datos internos) y los campos de Windows con autor o
  comentarios (``XPAuthor``, ``XPComment``). Una descripción que es una ruta de archivo
  (``C:\\Users\\...``, ``/home/...``) también se quita.
* **Coherencia con la foto editada**: la orientación sale como 1 (los píxeles ya vienen
  girados al cargarla), las dimensiones (``PixelXDimension``/``PixelYDimension``) son las
  reales del archivo exportado y no se copia la miniatura del original (mostraría la foto
  de antes de editar).
* El resto (fecha, cámara, exposición...) se conserva tal cual, como hasta ahora.

El perfil ICC no es EXIF: lo maneja ``exportar_imagen`` y se conserva siempre.

``auditar_imagen`` revisa un archivo ya exportado contra esta política (lo usan los tests y
``herramientas/auditar_metadatos.py``).
"""

from __future__ import annotations

import re
from typing import Optional

from PIL import Image

# IFD0
TAG_ORIENTACION = 0x0112
TAG_DESCRIPCION = 0x010E
TAG_DOCUMENTO = 0x010D
TAG_PC = 0x013C  # HostComputer
TAG_XP_COMENTARIO = 0x9C9C
TAG_XP_AUTOR = 0x9C9D
IFD_EXIF = 0x8769
IFD_GPS = 0x8825
# IFD de EXIF
TAG_ANCHO = 0xA002  # PixelXDimension
TAG_ALTO = 0xA003  # PixelYDimension
TAG_NOTA_FABRICANTE = 0x927C  # MakerNote
TAG_ID_UNICO = 0xA420  # ImageUniqueID
TAG_DUENO = 0xA430  # CameraOwnerName
TAG_SERIE_CUERPO = 0xA431  # BodySerialNumber
TAG_SERIE_LENTE = 0xA435  # LensSerialNumber

QUITAR_IFD0 = (TAG_DOCUMENTO, TAG_PC, TAG_XP_COMENTARIO, TAG_XP_AUTOR, TAG_ORIENTACION)
QUITAR_EXIF = (TAG_NOTA_FABRICANTE, TAG_ID_UNICO, TAG_DUENO, TAG_SERIE_CUERPO, TAG_SERIE_LENTE)

NOMBRES = {
    IFD_GPS: "GPS (ubicación)", TAG_DOCUMENTO: "DocumentName", TAG_PC: "HostComputer",
    TAG_XP_COMENTARIO: "XPComment", TAG_XP_AUTOR: "XPAuthor", TAG_NOTA_FABRICANTE: "MakerNote",
    TAG_ID_UNICO: "ImageUniqueID", TAG_DUENO: "CameraOwnerName", TAG_SERIE_CUERPO: "BodySerialNumber",
    TAG_SERIE_LENTE: "LensSerialNumber", TAG_DESCRIPCION: "ImageDescription (ruta de archivo)",
}

_RUTA = re.compile(r"(^[a-zA-Z]:[\\/])|(^\\\\)|(^/(home|users|Users|mnt|media|tmp|var)/)")


def _texto(valor) -> str:
    if isinstance(valor, bytes):
        return valor.decode("utf-8", "ignore")
    return str(valor or "")


def es_ruta(valor) -> bool:
    """True si el texto parece una ruta de archivo de una PC."""
    return bool(_RUTA.search(_texto(valor).strip()))


def limpiar_exif(exif: Optional[bytes], ancho: int, alto: int) -> Optional[bytes]:
    """El EXIF del original según la política, para una foto exportada de ``ancho`` × ``alto``.

    Devuelve ``None`` si no queda nada que escribir.
    """
    if not exif:
        return None
    e = Image.Exif()
    e.load(exif)
    for tag in QUITAR_IFD0:
        e.pop(tag, None)
    if es_ruta(e.get(TAG_DESCRIPCION)):
        del e[TAG_DESCRIPCION]
    # GPS: fuera el bloque entero (Pillow lo vuelve a escribir si queda la entrada o el IFD cargado).
    e.pop(IFD_GPS, None)
    try:
        e.get_ifd(IFD_GPS).clear()
    except Exception:
        pass
    sub = e.get_ifd(IFD_EXIF)
    for tag in QUITAR_EXIF:
        sub.pop(tag, None)
    if sub:
        sub[TAG_ANCHO] = int(ancho)
        sub[TAG_ALTO] = int(alto)
    if not len(e) and not sub:
        return None
    return e.tobytes()


def tiene_miniatura(exif: bytes) -> bool:
    """True si el EXIF crudo trae un segundo IFD (IFD1, la miniatura)."""
    datos = exif[6:] if exif[:6] == b"Exif\x00\x00" else exif
    if len(datos) < 8 or datos[:2] not in (b"II", b"MM"):
        return False
    orden = "little" if datos[:2] == b"II" else "big"
    ifd0 = int.from_bytes(datos[4:8], orden)
    if ifd0 + 2 > len(datos):
        return False
    n = int.from_bytes(datos[ifd0:ifd0 + 2], orden)
    siguiente = ifd0 + 2 + 12 * n
    if siguiente + 4 > len(datos):
        return False
    return int.from_bytes(datos[siguiente:siguiente + 4], orden) != 0


def auditar_imagen(ruta) -> list[str]:
    """Problemas del EXIF de una foto exportada según la política (lista vacía = cumple)."""
    problemas: list[str] = []
    with Image.open(ruta) as im:
        ancho, alto = im.size
        e = im.getexif()
        if not len(e):
            return problemas
        if e.get(TAG_ORIENTACION, 1) not in (0, 1):
            problemas.append(f"Orientation = {e.get(TAG_ORIENTACION)} (tiene que ser 1: los píxeles ya están girados)")
        gps = e.get_ifd(IFD_GPS)
        if gps:
            problemas.append(f"Tiene {NOMBRES[IFD_GPS]}: {len(gps)} campos")
        for tag in QUITAR_IFD0:
            if tag != TAG_ORIENTACION and tag in e:
                problemas.append(f"Tiene {NOMBRES[tag]}")
        if es_ruta(e.get(TAG_DESCRIPCION)):
            problemas.append(f"Tiene {NOMBRES[TAG_DESCRIPCION]}")
        sub = e.get_ifd(IFD_EXIF)
        for tag in QUITAR_EXIF:
            if tag in sub:
                problemas.append(f"Tiene {NOMBRES[tag]}")
        w, h = sub.get(TAG_ANCHO), sub.get(TAG_ALTO)
        if (w is not None and int(w) != ancho) or (h is not None and int(h) != alto):
            problemas.append(f"Dimensiones EXIF {w}×{h} distintas de las reales {ancho}×{alto}")
        if tiene_miniatura(im.info.get("exif") or b""):
            problemas.append("Tiene miniatura EXIF (IFD1): mostraría la foto de antes de editar")
    return problemas
