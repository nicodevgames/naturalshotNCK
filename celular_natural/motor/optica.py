"""Sistema óptico: lo que hace el lente antes de que la luz llegue al sensor.

Todas las etapas trabajan en luz LINEAL, porque el lente mezcla luz, no valores
codificados: un desenfoque en gamma oscurece los bordes brillantes y deja
halos que una lente real no produce.

Orden: desenfoque (PSF) → distorsión → aberración cromática → pérdida de
nitidez hacia los bordes → viñeteo.

Rendimiento (12 MP, CPU): desenfoque ≈ 0,4 s · distorsión ≈ 0,3 s ·
aberración ≈ 0,2 s · bordes ≈ 0,3 s · viñeteo ≈ 0,05 s.
"""

from __future__ import annotations

from functools import lru_cache

import cv2
import numpy as np

from .comun import escalar_canal, gauss, radio_normalizado, suavestep


@lru_cache(maxsize=8)
def _disco(radio_decimas: int) -> np.ndarray:
    """Núcleo de desenfoque por defocus: un disco con borde antialias."""
    r = radio_decimas / 10.0
    n = int(np.ceil(r)) + 1
    yy, xx = np.mgrid[-n:n + 1, -n:n + 1].astype(np.float32)
    k = np.clip(r + 0.5 - np.sqrt(xx * xx + yy * yy), 0.0, 1.0)
    return (k / k.sum()).astype(np.float32)


def desenfoque(lin: np.ndarray, s: float, d: float) -> np.ndarray:
    """PSF aproximada: disco de desenfoque (foco) convolucionado con una gaussiana
    (difracción y aberraciones). Su MTF cae suave, sin el "corte" de un blur simple.

    d 0..1 → radio del disco hasta 3 px en una foto de 12 MP.
    """
    r = 3.0 * d * s
    if r >= 0.6:
        lin = cv2.filter2D(lin, -1, _disco(round(r * 10)), borderType=cv2.BORDER_REFLECT)
    sigma = max(0.3, 0.45 * max(r, 0.6 * d * s))
    return gauss(lin, sigma) if d * s > 0.05 else lin


@lru_cache(maxsize=4)
def _mapas_distorsion(h: int, w: int, k_milesimas: int) -> tuple[np.ndarray, np.ndarray]:
    k1 = k_milesimas / 1000.0
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    norma = float(np.hypot(cx, cy)) or 1.0
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = (xx - cx) / norma, (yy - cy) / norma
    r2 = dx * dx + dy * dy
    # Barril (k1 > 0) toma muestras más afuera: se reescala para que las
    # esquinas no salgan del cuadro (como el recorte que hace la cámara).
    ajuste = 1.0 / (1.0 + max(k1, 0.0))
    f = (1.0 + k1 * r2) * ajuste
    return (cx + dx * f * norma).astype(np.float32), (cy + dy * f * norma).astype(np.float32)


def distorsion(img: np.ndarray, k: float) -> np.ndarray:
    """Distorsión radial: k > 0 barril (gran angular de celular), k < 0 cojín.

    k -1..1 → coeficiente radial ±0,035 (≈1-2 % de desplazamiento en las esquinas).
    """
    h, w = img.shape[:2]
    mx, my = _mapas_distorsion(h, w, round(35 * k))
    out = cv2.remap(img, mx, my, interpolation=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
    # La interpolación bicúbica sobrepasa un poco en bordes duros: la luz no es negativa.
    return np.maximum(out, 0.0, out=out)


def aberracion(img: np.ndarray, a: float) -> None:
    """Aberración cromática lateral: rojo y azul con un aumento apenas distinto
    (≈1 px en las esquinas de 12 MP con a = 1)."""
    h, w = img.shape[:2]
    desplazamiento = 0.00045 * a
    if desplazamiento * max(h, w) > 0.05:
        img[..., 0] = escalar_canal(np.ascontiguousarray(img[..., 0]), 1.0 + desplazamiento)
        img[..., 2] = escalar_canal(np.ascontiguousarray(img[..., 2]), 1.0 - desplazamiento)


def bordes_blandos(img: np.ndarray, s: float, b: float) -> None:
    """Pérdida progresiva de nitidez hacia los bordes (curvatura de campo)."""
    h, w = img.shape[:2]
    mascara = suavestep(0.35, 1.0, radio_normalizado(h, w)) * (0.9 * b)
    borroso = gauss(img, max(0.6, 1.8 * s))
    img += (borroso - img) * mascara[..., None]


def vineteo(img: np.ndarray, v: float) -> None:
    """Viñeteo óptico: caída de luz hacia las esquinas (en luz lineal es una
    multiplicación; con v = 1 las esquinas reciben un 40 % menos de luz)."""
    h, w = img.shape[:2]
    r = radio_normalizado(h, w)
    img *= (1.0 - 0.4 * v * r * r)[..., None]
