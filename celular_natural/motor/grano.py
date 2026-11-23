"""Grano fotográfico: más rico que el ruido uniforme.

A diferencia del ruido de sensor (que sale del modelo físico), el grano es un
efecto de aspecto, como el de una película o un escaneo:

  * tamaño        diámetro del grano (0,5 a 3 px en una foto de 12 MP)
  * correlación   cuánto se agrupa en grumos (mezcla de una escala fina y otra 3× mayor)
  * croma         0 = monocromático, 1 = cada canal con su propio grano
  * zonas         intensidad independiente en sombras, medios tonos y luces
  * semilla       el mismo número da exactamente el mismo grano

Se aplica sobre la imagen codificada, que es donde se percibe el grano.
Rendimiento (12 MP, CPU): ≈ 0,6 s monocromático, ≈ 1,2 s cromático.
"""

from __future__ import annotations

import numpy as np

from .comun import gauss, luma, suavestep


def _normalizado(x: np.ndarray) -> np.ndarray:
    muestra = x[: min(x.shape[0], 512), : min(x.shape[1], 512)]
    return x / max(float(muestra.std()), 1e-6)


def _patron(h: int, w: int, sigma: float, correlacion: float, rng: np.random.Generator) -> np.ndarray:
    fino = rng.standard_normal((h, w), dtype=np.float32)
    if sigma >= 0.3:
        fino = gauss(fino, sigma)
    fino = _normalizado(fino)
    if correlacion <= 0:
        return fino
    grumo = _normalizado(gauss(rng.standard_normal((h, w), dtype=np.float32), max(0.6, 3.0 * sigma)))
    return _normalizado((1.0 - correlacion) * fino + correlacion * grumo)


def grano(img: np.ndarray, s: float, cantidad: float, tam: float, croma: float, correlacion: float,
          zonas: tuple[float, float, float], escala_vista: float, rng: np.random.Generator) -> None:
    h, w = img.shape[:2]
    sigma_completo = 0.5 + 2.5 * tam          # en px de una foto de 12 MP
    sigma = sigma_completo * s
    # En la vista previa reducida varios granos caen en un mismo píxel y se
    # promedian: se atenúa en proporción (los granos grandes se atenúan menos).
    atenuacion = min(1.0, escala_vista * max(1.0, sigma_completo))
    amp = 0.035 * cantidad * atenuacion

    y = np.clip(luma(img), 0.0, 1.0)
    zs, zm, zl = zonas
    w_s = 1.0 - suavestep(0.0, 0.45, y)
    w_l = suavestep(0.55, 1.0, y)
    w_m = np.clip(1.0 - w_s - w_l, 0.0, 1.0)
    perfil = amp * (zs * w_s + zm * w_m + zl * w_l)

    mono = _patron(h, w, sigma, correlacion, rng)
    if croma <= 0:
        img += (mono * perfil)[..., None]
        return
    for c in range(3):
        propio = _patron(h, w, sigma, correlacion, rng)
        img[..., c] += ((1.0 - croma) * mono + croma * propio) * perfil
