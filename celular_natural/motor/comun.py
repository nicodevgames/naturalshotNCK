"""Utilidades compartidas por las etapas: color, filtros y geometría.

Convenciones:
  * Las imágenes intermedias son float32 HxWx3 en [0, 1] (pueden salirse un poco
    del rango entre etapas; se recorta solo al final).
  * "Lineal" = luz lineal (decodificada de la curva sRGB). "Gamma" = codificada.
  * ``s`` es la escala espacial de la imagen respecto de una foto de 12 MP
    (lado largo 4032 px): todos los radios se multiplican por ``s`` para que la
    vista previa reducida y la exportación completa se vean equivalentes.
"""

from __future__ import annotations

import cv2
import numpy as np

LADO_REFERENCIA = 4032  # lado largo de una foto de 12 MP

PESOS_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


# ---------------------------------------------------------------------------
# Curva sRGB (con tablas: mucho más rápidas que las potencias sobre 12 MP)
# ---------------------------------------------------------------------------

def srgb_a_lineal(x: np.ndarray) -> np.ndarray:
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def lineal_a_srgb(x: np.ndarray) -> np.ndarray:
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


LUT_DECODIFICAR_8 = srgb_a_lineal(np.arange(256, dtype=np.float64) / 255.0).astype(np.float32)
_LUT_16 = np.linspace(0.0, 1.0, 65536)
LUT_DECODIFICAR_16 = srgb_a_lineal(_LUT_16).astype(np.float32)
LUT_CODIFICAR_16 = lineal_a_srgb(_LUT_16).astype(np.float32)
# Derivada de la codificación (d gamma / d lineal): convierte un desvío de ruido
# medido en luz lineal al desvío equivalente en la imagen codificada.
_DERIVADA = np.gradient(LUT_CODIFICAR_16.astype(np.float64), _LUT_16)
_DERIVADA[0] = 12.92
LUT_DERIVADA_CODIFICAR_16 = np.minimum(_DERIVADA, 12.92).astype(np.float32)


def _indice16(x: np.ndarray) -> np.ndarray:
    idx = np.clip(np.nan_to_num(x, nan=0.0), 0.0, 1.0) * 65535.0
    idx += 0.5
    return idx.astype(np.uint16)


def decodificar(img: np.ndarray) -> np.ndarray:
    """Gamma → lineal. Acepta uint8 (exacto) o float (precisión de 16 bits)."""
    if img.dtype == np.uint8:
        return LUT_DECODIFICAR_8[img]
    return LUT_DECODIFICAR_16[_indice16(img)]


def codificar(lin: np.ndarray) -> np.ndarray:
    """Lineal → gamma, con precisión de 16 bits.

    Lo que supera el blanco (por exposición o HDR) se codifica con la fórmula
    en vez de recortarse: la caída suave de luces lo comprime después, como el
    margen de luces de una cámara.
    """
    out = LUT_CODIFICAR_16[_indice16(lin)]
    sobre = lin > 1.0
    if sobre.any():
        out[sobre] = 1.055 * np.power(lin[sobre], 1 / 2.4) - 0.055
    return out


def derivada_codificar(lin: np.ndarray) -> np.ndarray:
    return LUT_DERIVADA_CODIFICAR_16[_indice16(lin)]


def luma(img: np.ndarray) -> np.ndarray:
    return (img @ PESOS_LUMA).astype(np.float32)


def suavestep(a: float, b: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------

def caja(x: np.ndarray, r: int) -> np.ndarray:
    k = 2 * r + 1
    return cv2.boxFilter(x, -1, (k, k), normalize=True, borderType=cv2.BORDER_REFLECT)


def guiado_coeficientes(guia: np.ndarray, r: int, eps: float) -> tuple[np.ndarray, np.ndarray]:
    """Filtro guiado autoguiado (He et al.). Devuelve los coeficientes medios a, b."""
    media = caja(guia, r)
    var = caja(guia * guia, r) - media * media
    np.maximum(var, 0.0, out=var)
    a = var / (var + eps)
    b = media - a * media
    return caja(a, r), caja(b, r)


def guiado(guia: np.ndarray, r: int, eps: float) -> np.ndarray:
    """Suavizado que preserva bordes: aplana texturas de varianza < eps."""
    a, b = guiado_coeficientes(guia, r, eps)
    return a * guia + b


def guiado_con_guia(guia: np.ndarray, x: np.ndarray, r: int, eps: float) -> np.ndarray:
    """Filtro guiado clásico: suaviza ``x`` siguiendo los bordes de ``guia``.

    Se usa para que las máscaras sigan los contornos reales sin halos.
    """
    mg, mx = caja(guia, r), caja(x, r)
    cov = caja(guia * x, r) - mg * mx
    var = caja(guia * guia, r) - mg * mg
    a = cov / (np.maximum(var, 0.0) + eps)
    b = mx - a * mg
    return caja(a, r) * guia + caja(b, r)


def gauss(x: np.ndarray, sigma: float) -> np.ndarray:
    return cv2.GaussianBlur(x, (0, 0), sigmaX=sigma, sigmaY=sigma, borderType=cv2.BORDER_REFLECT)


def desvio_local(y: np.ndarray, r: int) -> np.ndarray:
    media = caja(y, r)
    return np.sqrt(np.maximum(caja(y * y, r) - media * media, 0.0))


def campo_suave(h: int, w: int, rng: np.random.Generator, celdas: int = 4) -> np.ndarray:
    """Campo aleatorio muy suave en [-1, 1] (variaciones de baja frecuencia)."""
    lado = max(h, w, 1)
    ch, cw = max(2, round(celdas * h / lado)), max(2, round(celdas * w / lado))
    base = rng.standard_normal((ch + 2, cw + 2)).astype(np.float32)
    campo = cv2.resize(base, (w, h), interpolation=cv2.INTER_CUBIC)
    m = float(np.abs(campo).max()) or 1.0
    return campo / m


_cache_radio: dict[tuple[int, int], np.ndarray] = {}


def radio_normalizado(h: int, w: int) -> np.ndarray:
    """Distancia al centro, 0 en el centro y 1 en las esquinas."""
    clave = (h, w)
    r = _cache_radio.get(clave)
    if r is None:
        yy = (np.arange(h, dtype=np.float32) - (h - 1) / 2.0)[:, None]
        xx = (np.arange(w, dtype=np.float32) - (w - 1) / 2.0)[None, :]
        r = np.sqrt(xx * xx + yy * yy) / np.float32(np.hypot((w - 1) / 2.0, (h - 1) / 2.0) or 1.0)
        _cache_radio.clear()
        _cache_radio[clave] = r
    return r


def escalar_canal(canal: np.ndarray, escala: float) -> np.ndarray:
    h, w = canal.shape
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    m = np.array([[escala, 0, cx * (1 - escala)], [0, escala, cy * (1 - escala)]], dtype=np.float32)
    return cv2.warpAffine(canal, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
