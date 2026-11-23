"""Lectura y escritura de imágenes con manejo de orientación EXIF y perfiles ICC.

Criterio de color:
  * Si la imagen trae un perfil RGB (sRGB, Display P3, Adobe RGB...), se procesa
    en ese mismo espacio y el perfil se vuelve a incrustar al exportar. Así no
    se recorta el gamut ni cambian los colores al abrirla en otro programa.
  * Para mostrarla en pantalla se convierte a sRGB con LittleCMS.
  * Imágenes CMYK se convierten a sRGB al cargarlas (usando su perfil si lo tienen).
  * Sin perfil se asume sRGB y se incrusta un perfil sRGB al exportar.
"""

from __future__ import annotations

import io
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageCms, ImageOps

from .metadatos import limpiar_exif

EXTENSIONES_SOPORTADAS = (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp")
# Videos (los abre el modo Video, con ``motor/video.py``). Van acá, en un módulo liviano, para
# que la interfaz reconozca un video al abrirlo o arrastrarlo sin tener que cargar PyAV.
EXTENSIONES_VIDEO = (".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm")

_TAG_ORIENTACION = 0x0112

Image.MAX_IMAGE_PIXELS = 300_000_000  # fotos grandes legítimas (hasta ~300 MP)


def _perfil_srgb() -> ImageCms.ImageCmsProfile:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))


_SRGB_BYTES: Optional[bytes] = None


def bytes_perfil_srgb() -> bytes:
    global _SRGB_BYTES
    if _SRGB_BYTES is None:
        _SRGB_BYTES = _perfil_srgb().tobytes()
    return _SRGB_BYTES


@dataclass
class ImagenCargada:
    ruta: Path
    rgb: np.ndarray  # HxWx3 uint8 en el espacio de color de ``icc`` (sRGB si es None)
    alpha: Optional[np.ndarray]  # HxW uint8 o None
    icc: Optional[bytes]
    nombre_perfil: str
    exif: Optional[bytes]  # EXIF original con la orientación normalizada a 1
    orientacion_original: int
    notas: list[str]

    @property
    def ancho(self) -> int:
        return int(self.rgb.shape[1])

    @property
    def alto(self) -> int:
        return int(self.rgb.shape[0])


def _abrir_perfil(icc: bytes) -> Optional[ImageCms.ImageCmsProfile]:
    try:
        return ImageCms.ImageCmsProfile(io.BytesIO(icc))
    except Exception:
        return None


def _espacio_perfil(perfil: ImageCms.ImageCmsProfile) -> str:
    try:
        return perfil.profile.xcolor_space.strip().upper()
    except Exception:
        return ""


def _descripcion_perfil(perfil: ImageCms.ImageCmsProfile) -> str:
    try:
        return ImageCms.getProfileDescription(perfil).strip() or "Perfil incrustado"
    except Exception:
        return "Perfil incrustado"


def cargar_imagen(ruta: str | os.PathLike) -> ImagenCargada:
    ruta = Path(ruta)
    notas: list[str] = []
    with Image.open(ruta) as original:
        original.load()
        exif_original = original.getexif()
        orientacion = int(exif_original.get(_TAG_ORIENTACION, 1) or 1)
        im = ImageOps.exif_transpose(original)
        if im is None:  # versiones antiguas de Pillow devuelven None si no hay cambios
            im = original.copy()
        info = dict(original.info)

    if orientacion not in (1, 0):
        notas.append(f"Orientación EXIF {orientacion} aplicada")

    exif = im.getexif()
    if _TAG_ORIENTACION in exif:
        del exif[_TAG_ORIENTACION]
    exif_bytes = exif.tobytes() if len(exif) else None

    icc: Optional[bytes] = info.get("icc_profile") or None
    perfil = _abrir_perfil(icc) if icc else None
    if icc and perfil is None:
        notas.append("Perfil ICC ilegible: se asume sRGB")
        icc = None
    alpha: Optional[np.ndarray] = None
    modo = im.mode

    if modo == "CMYK":
        if perfil is not None and _espacio_perfil(perfil) == "CMYK":
            im = ImageCms.profileToProfile(
                im, perfil, _perfil_srgb(),
                renderingIntent=ImageCms.Intent.PERCEPTUAL, outputMode="RGB",
            )
            notas.append("CMYK convertido a sRGB con su perfil")
        else:
            im = im.convert("RGB")
            notas.append("CMYK convertido a sRGB")
        icc, perfil = None, None
        rgb = np.asarray(im, dtype=np.uint8).copy()
    elif modo in ("I;16", "I;16B", "I;16L", "I;16N", "I", "F"):
        arr = np.asarray(im).astype(np.float32)
        if modo == "F":
            arr = np.clip(arr, 0.0, 1.0) * 255.0
        elif arr.max() > 255:
            arr = arr / 257.0
        gris = np.clip(arr + 0.5, 0, 255).astype(np.uint8)
        rgb = np.repeat(gris[..., None], 3, axis=2)
        notas.append("Imagen de 16 bits en escala de grises convertida a 8 bits")
        icc, perfil = None, None
    else:
        tiene_alpha = modo in ("RGBA", "LA", "PA", "La", "RGBa") or (
            modo == "P" and "transparency" in info
        )
        if tiene_alpha:
            rgba = im.convert("RGBA")
            a = np.asarray(rgba.getchannel("A"), dtype=np.uint8)
            if a.min() < 255:
                alpha = a.copy()
            im = rgba.convert("RGB")
        else:
            im = im.convert("RGB")
        rgb = np.asarray(im, dtype=np.uint8).copy()
        if perfil is not None and _espacio_perfil(perfil) != "RGB":
            # Perfil de grises u otro: la imagen ya se expandió a RGB, se trata como sRGB.
            icc, perfil = None, None

    nombre = _descripcion_perfil(perfil) if perfil is not None else "sRGB (supuesto)"
    return ImagenCargada(
        ruta=ruta,
        rgb=rgb,
        alpha=alpha,
        icc=icc,
        nombre_perfil=nombre,
        exif=exif_bytes,
        orientacion_original=orientacion,
        notas=notas,
    )


class TransformacionPantalla:
    """Convierte arreglos del espacio de la imagen a sRGB para mostrarlos."""

    def __init__(self, icc: Optional[bytes]):
        self._transformacion = None
        if icc:
            perfil = _abrir_perfil(icc)
            if perfil is not None:
                try:
                    self._transformacion = ImageCms.buildTransform(
                        perfil, _perfil_srgb(), "RGB", "RGB",
                        renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
                    )
                except Exception:
                    self._transformacion = None

    def a_srgb(self, rgb: np.ndarray) -> np.ndarray:
        if self._transformacion is None:
            return rgb
        im = Image.fromarray(rgb, "RGB")
        return np.asarray(ImageCms.applyTransform(im, self._transformacion), dtype=np.uint8)


def ruta_salida_sugerida(original: str | os.PathLike, extension: str, sufijo: str = "_celular") -> Path:
    """Ruta nueva junto al original que nunca coincide con un archivo existente."""
    original = Path(original)
    extension = extension if extension.startswith(".") else "." + extension
    candidata = original.with_name(f"{original.stem}{sufijo}{extension}")
    n = 2
    while candidata.exists():
        candidata = original.with_name(f"{original.stem}{sufijo}_{n}{extension}")
        n += 1
    return candidata


def _es_mismo_archivo(a: Path, b: Path) -> bool:
    try:
        if a.exists() and b.exists():
            return os.path.samefile(a, b)
    except OSError:
        pass
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _desmarcar_pixeles(rgb: np.ndarray, semilla: int = 0) -> np.ndarray:
    """Perturba la firma en píxeles (SynthID) sin cambiar tamaño ni color.

    Ida y vuelta por un reescalado del 98,5 % (rompe la grilla de bloques, que es
    justamente lo que la vuelve robusta a recortes y recompresión) más ruido
    gaussiano de sigma 2 en 8 bits, por debajo de la tolerancia de los bloques.
    La imagen vuelve a su tamaño exacto.
    """
    alto, ancho = rgb.shape[:2]
    if min(alto, ancho) < 32:
        return rgb
    f = 0.985
    im = Image.fromarray(rgb, "RGB")
    im = im.resize((max(1, round(ancho * f)), max(1, round(alto * f))), Image.LANCZOS)
    im = im.resize((ancho, alto), Image.LANCZOS)
    a = np.asarray(im, np.float32) + np.random.default_rng(semilla).normal(0.0, 2.0, (alto, ancho, 3))
    return np.clip(a + 0.5, 0, 255).astype(np.uint8)


def exportar_imagen(
    destino: str | os.PathLike,
    rgb: np.ndarray,
    *,
    original: str | os.PathLike,
    alpha: Optional[np.ndarray] = None,
    icc: Optional[bytes] = None,
    exif: Optional[bytes] = None,
    formato: str = "PNG",
    calidad_jpeg: int = 92,
    desmarcar: bool = False,
    semilla: int = 0,
) -> Path:
    """Guarda el resultado en un archivo nuevo. Nunca sobrescribe el original."""
    destino = Path(destino)
    if _es_mismo_archivo(destino, Path(original)):
        raise ValueError("El archivo de destino es el original. Elegí otro nombre para no sobrescribirlo.")
    formato = formato.upper()
    if formato not in ("PNG", "JPEG"):
        raise ValueError(f"Formato no soportado: {formato}")

    perfil = icc or bytes_perfil_srgb()
    opciones: dict = {"icc_profile": perfil}
    # NS-104: el EXIF sale según la política de motor/metadatos.py (sin GPS, seriales ni rutas;
    # orientación 1, dimensiones reales y sin la miniatura del original).
    exif = limpiar_exif(exif, int(rgb.shape[1]), int(rgb.shape[0]))
    if exif:
        opciones["exif"] = exif

    if desmarcar:
        rgb = _desmarcar_pixeles(rgb, semilla)

    if formato == "PNG":
        if alpha is not None:
            im = Image.fromarray(np.dstack([rgb, alpha]), "RGBA")
        else:
            im = Image.fromarray(rgb, "RGB")
        opciones["compress_level"] = 6
    else:
        if alpha is not None:
            # JPEG no admite transparencia: se compone sobre blanco.
            a = alpha.astype(np.float32)[..., None] / 255.0
            rgb = np.clip(rgb.astype(np.float32) * a + 255.0 * (1.0 - a) + 0.5, 0, 255).astype(np.uint8)
        im = Image.fromarray(rgb, "RGB")
        calidad = int(max(1, min(100, calidad_jpeg)))
        opciones.update(quality=calidad, subsampling=0 if calidad >= 90 else 2, optimize=True)

    destino.parent.mkdir(parents=True, exist_ok=True)
    # Se escribe a un temporal y luego se renombra: nunca queda un archivo a medias.
    fd, tmp = tempfile.mkstemp(prefix=".celular_", suffix=destino.suffix or ".tmp", dir=destino.parent)
    os.close(fd)
    try:
        try:
            im.save(tmp, formato, **opciones)
        except OSError:
            # Pillow reserva para el JPEG optimizado un búfer del tamaño de la foto en bytes: en
            # fotos con mucho grano a calidad alta no alcanza ("broken data stream"). Sin
            # optimizar la tabla de Huffman sale la misma imagen, apenas más pesada.
            if formato != "JPEG" or not opciones.get("optimize"):
                raise
            opciones["optimize"] = False
            im.save(tmp, formato, **opciones)
        os.replace(tmp, destino)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return destino
