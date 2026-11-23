"""Máscaras regionales sin segmentación semántica.

No se usa IA ni se asume que haya personas. Las regiones salen de medidas
locales de la imagen:

  * bordes         gradiente fuerte (contornos)              → protegidos de halos y ablandado
  * piel           color en el rango típico de piel (YCrCb) en medios tonos
  * textura alta   mucha variación local: cabello, telas, follaje, ladrillo
  * textura baja   superficies lisas: cielo, paredes, piel muy lisa

La piel por color puede incluir madera, arena o cuero: por eso sus valores por
defecto son neutros y todo el sistema se puede apagar.

Las regiones forman una partición suave (suman ≤ 1 en cada píxel; lo que sobra
es "resto", que recibe la cantidad normal). Prioridad: bordes > piel > textura
alta > textura baja. Cada máscara se suaviza con un filtro guiado sobre la
propia imagen, así sigue los contornos reales sin halos ni escalones.

Rendimiento (12 MP, CPU): ≈ 1,5 s la primera vez; después sale de la caché.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import cv2
import numpy as np

from .comun import caja, desvio_local, gauss, guiado_con_guia, luma, suavestep

REGIONES = ("piel", "bordes", "alta", "baja")
NOMBRES_REGIONES = {
    "piel": "Piel",
    "bordes": "Bordes y contornos",
    "alta": "Textura alta (cabello, telas)",
    "baja": "Textura baja (fondos lisos)",
}
EFECTOS_REGIONALES = ("nitidez", "suavizado", "ruido", "micro")
NOMBRES_EFECTOS = {
    "nitidez": "Reducir nitidez",
    "suavizado": "Suavizado",
    "ruido": "Ruido",
    "micro": "Microcontraste",
}


@dataclass(frozen=True)
class Regiones:
    piel: np.ndarray
    bordes: np.ndarray
    alta: np.ndarray
    baja: np.ndarray

    def resto(self) -> np.ndarray:
        return np.clip(1.0 - (self.piel + self.bordes + self.alta + self.baja), 0.0, 1.0)

    def mapa(self, multiplicadores: dict[str, float]) -> np.ndarray:
        """Multiplicador por píxel: cada región aporta el suyo según su peso."""
        m = self.resto()
        for nombre in REGIONES:
            m = m + getattr(self, nombre) * float(multiplicadores.get(nombre, 1.0))
        return m.astype(np.float32)


def _suavizar(mascara: np.ndarray, guia: np.ndarray, s: float) -> np.ndarray:
    m = gauss(mascara.astype(np.float32), max(0.8, 1.5 * s))
    m = guiado_con_guia(guia, m, max(2, round(4 * s)), eps=1e-3)
    return np.clip(m, 0.0, 1.0)


def calcular_regiones(img: np.ndarray, s: float) -> Regiones:
    """``img`` en gamma (float32 0..1 o uint8)."""
    f = img.astype(np.float32) / 255.0 if img.dtype == np.uint8 else np.clip(img, 0.0, 1.0)
    y = luma(f)

    # Bordes: gradiente de la luma algo suavizada (ignora el ruido fino).
    ys = gauss(y, max(0.6, 1.0 * s))
    gx = cv2.Sobel(ys, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(ys, cv2.CV_32F, 0, 1, ksize=3)
    magnitud = np.sqrt(gx * gx + gy * gy) / 4.0
    # Un contorno es un gradiente fuerte y AISLADO: mucho mayor que el promedio de
    # su vecindario. En una textura (pelo, tela) los gradientes están en todos lados.
    vecindario = caja(magnitud, max(3, round(12 * s)))
    aislado = suavestep(1.6, 3.0, magnitud / (vecindario + 1e-3))
    bordes = suavestep(0.03, 0.12, magnitud) * aislado
    bordes = np.clip(gauss(bordes, max(0.8, 1.5 * s)) * 1.5, 0.0, 1.0)

    # Textura: desvío local del detalle fino (sin los bordes grandes).
    fino = y - gauss(y, max(1.0, 3.0 * s))
    energia = desvio_local(fino, max(2, round(5 * s)))
    alta = suavestep(0.012, 0.04, energia)
    baja = 1.0 - suavestep(0.003, 0.012, energia)

    # Piel por color (YCrCb, rangos clásicos ampliados con bordes suaves).
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    yy = 0.299 * r + 0.587 * g + 0.114 * b
    cr = (r - yy) * 0.713 + 0.5
    cb = (b - yy) * 0.564 + 0.5
    piel = (suavestep(0.505, 0.53, cr) * (1.0 - suavestep(0.68, 0.71, cr))
            * suavestep(0.28, 0.31, cb) * (1.0 - suavestep(0.50, 0.53, cb))
            * suavestep(0.08, 0.2, y) * (1.0 - suavestep(0.92, 0.99, y)))

    bordes = _suavizar(bordes, y, s)
    piel = _suavizar(piel, y, s)
    alta = _suavizar(alta, y, s)
    baja = _suavizar(baja, y, s)

    # Partición suave por prioridad.
    p_bordes = bordes
    p_piel = piel * (1.0 - p_bordes)
    p_alta = alta * (1.0 - p_bordes) * (1.0 - piel)
    p_baja = baja * (1.0 - p_bordes) * (1.0 - piel) * (1.0 - alta)
    return Regiones(*(x.astype(np.float32) for x in (p_piel, p_bordes, p_alta, p_baja)))


_CACHE: dict[str, Regiones] = {}


def _huella(img: np.ndarray, s: float) -> str:
    h = hashlib.blake2b(digest_size=16)
    h.update(str((img.shape, img.dtype.str, round(s, 4))).encode())
    paso = max(1, img.shape[0] // 97), max(1, img.shape[1] // 97)
    h.update(np.ascontiguousarray(img[:: paso[0], :: paso[1]]).tobytes())
    return h.hexdigest()


def regiones_en_cache(img: np.ndarray, s: float) -> Regiones:
    """Las máscaras dependen solo de la imagen: se calculan una vez y se reusan
    mientras se mueven los controles."""
    clave = _huella(img, s)
    r = _CACHE.get(clave)
    if r is None:
        r = calcular_regiones(img, s)
        if len(_CACHE) >= 4:
            _CACHE.pop(next(iter(_CACHE), None), None)
        _CACHE[clave] = r
    return r
