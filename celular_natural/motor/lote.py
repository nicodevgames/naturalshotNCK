"""Procesamiento por lotes: la misma pila de ajustes sobre muchas fotos.

Cada foto se procesa a resolución completa desde su original y se guarda como
archivo nuevo (nunca se sobrescribe nada), con su perfil ICC y, si se pide, su
EXIF. Un error en una foto no corta el lote: queda anotado y se sigue.

``encuadres`` (opcional): para las fotos de la tira que tienen una **Medida** elegida, su giro, su
recorte y la medida (``medida.py``): la foto se gira, se recorta y se lleva a la medida **antes**
del filtro, igual que al exportarla sola. Las demás, como siempre (la foto entera, sin tocar).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

import numpy as np

from .geometria import aplicar_geometria
from .imagen_io import cargar_imagen, exportar_imagen, ruta_salida_sugerida
from .medida import llevar_a_medida, medida_valida
from .procesado import Ajustes, Cancelado, procesar_pila
from .zonas import aplicar_recorte


@dataclass
class ResultadoLote:
    original: Path
    destino: Optional[Path]
    error: Optional[str] = None


def _encuadrar(rgb: np.ndarray, alpha, geometria, recorte, tam) -> tuple:
    """La foto (y su alfa) girada, recortada y llevada a la medida, como la deja la ventana antes del
    filtro (``medida.llevar_a_medida``)."""
    tam = medida_valida(tam)
    if geometria is not None and not geometria.es_identidad():
        rgb = aplicar_geometria(rgb, geometria)
        alpha = None if alpha is None else aplicar_geometria(alpha, geometria)
    rgb = llevar_a_medida(np.ascontiguousarray(aplicar_recorte(rgb, recorte)), tam)
    if alpha is not None:
        alpha = llevar_a_medida(np.ascontiguousarray(aplicar_recorte(alpha, recorte)), tam)
    return rgb, alpha


def procesar_lote(
    rutas: Sequence[str | os.PathLike],
    pila: Sequence[Ajustes],
    carpeta: Optional[str | os.PathLike] = None,
    formato: str = "JPEG",
    calidad_jpeg: int = 92,
    conservar_exif: bool = True,
    progreso: Optional[Callable[[int, int, str], None]] = None,
    cancelado: Optional[Callable[[], bool]] = None,
    encuadres: Optional[Mapping[str, tuple]] = None,
) -> list[ResultadoLote]:
    """``carpeta`` None = cada foto junto a su original. ``encuadres``: {ruta (como viene en
    ``rutas``, en texto): (geometría, recorte, medida)} de las fotos con una Medida (ver el módulo)."""
    extension = ".png" if formato.upper() == "PNG" else ".jpg"
    resultados: list[ResultadoLote] = []
    for i, ruta in enumerate(rutas):
        if cancelado is not None and cancelado():
            raise Cancelado()
        encuadre = (encuadres or {}).get(str(ruta))
        ruta = Path(ruta)
        if progreso is not None:
            progreso(i, len(rutas), ruta.name)
        try:
            img = cargar_imagen(ruta)
            rgb, alpha = img.rgb, img.alpha
            if encuadre is not None and medida_valida(encuadre[2]) is not None:
                rgb, alpha = _encuadrar(rgb, alpha, *encuadre)
            salida = procesar_pila(rgb, list(pila), escala_vista=1.0, cancelado=cancelado)
            base = Path(carpeta) / ruta.name if carpeta else ruta
            destino = ruta_salida_sugerida(base, extension)
            exportar_imagen(destino, salida, original=ruta, alpha=alpha, icc=img.icc,
                            exif=img.exif if conservar_exif else None, formato=formato,
                            calidad_jpeg=calidad_jpeg)
            resultados.append(ResultadoLote(ruta, destino))
        except Cancelado:
            raise
        except Exception as error:  # se informa y se sigue con la próxima
            resultados.append(ResultadoLote(ruta, None, f"{type(error).__name__}: {error}"))
    if progreso is not None:
        progreso(len(rutas), len(rutas), "")
    return resultados
