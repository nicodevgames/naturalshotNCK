"""Compresión y procesamiento digital: reescalado y JPEG simulados.

Se aplican UNA sola vez, al final de toda la pila de capas y siempre a partir
del original: nunca se acumulan aunque se mueva un control cien veces, porque
cada vista previa y cada exportación se recalculan desde cero.

  * reescalado    baja la resolución y la vuelve a subir (foto achicada por una
                  app o una red social). Algoritmos: bilineal, bicúbico, área, Lanczos.
  * JPEG          codifica y decodifica en memoria con la calidad elegida; el
                  submuestreo de croma 4:2:0 es el de casi todas las fotos de celular.

Rendimiento (12 MP, CPU): reescalado ≈ 0,1 s · JPEG ≈ 0,5 s.
"""

from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image

ALGORITMOS = ("Bilineal", "Bicúbico", "Área", "Lanczos")
_INTERP = (cv2.INTER_LINEAR, cv2.INTER_CUBIC, cv2.INTER_AREA, cv2.INTER_LANCZOS4)


def reescalar(img: np.ndarray, r: float, algoritmo: int) -> np.ndarray:
    """r 0..1 → la resolución intermedia baja hasta el 40 %."""
    h, w = img.shape[:2]
    f = 1.0 - 0.6 * r
    chico = (max(1, round(w * f)), max(1, round(h * f)))
    if chico == (w, h):
        return img
    i = _INTERP[int(algoritmo) % len(_INTERP)]
    abajo = cv2.resize(img, chico, interpolation=i)
    # INTER_AREA solo sirve para achicar: para volver a agrandar se usa bilineal.
    arriba = cv2.INTER_LINEAR if i == cv2.INTER_AREA else i
    return cv2.resize(abajo, (w, h), interpolation=arriba)


def calidad_jpeg(j: float) -> int:
    """j 0..1 → calidad 95 (casi invisible) a 35 (artefactos claros)."""
    return int(round(95 - 60 * j))


def jpeg(rgb8: np.ndarray, calidad: int, submuestreo: bool) -> np.ndarray:
    buf = io.BytesIO()
    Image.fromarray(rgb8, "RGB").save(buf, "JPEG", quality=int(calidad), subsampling=2 if submuestreo else 0)
    buf.seek(0)
    with Image.open(buf) as im:
        return np.asarray(im.convert("RGB"), dtype=np.uint8).copy()
