"""Sensor digital: ruido Poisson-Gaussiano y mosaico Bayer con demosaico.

Ruido
-----
En un sensor real la varianza del ruido crece con la luz recibida:

    var(x) = a·x + b        (x = señal en luz lineal)

``a·x`` es el ruido de disparo (Poisson, por la llegada aleatoria de fotones) y
``b`` el ruido de lectura (gaussiano, de la electrónica; domina en sombras).
El desvío se calcula en luz lineal y se pasa a la imagen codificada con la
derivada de la curva sRGB (σ_gamma = σ_lineal · dCod/dx), que es lo que pasa
en la cámara cuando la curva tonal se aplica después del sensor.

El ruido se inyecta DESPUÉS del detalle: representa el ruido residual que deja
el procesado del teléfono. Si se agregara antes, el suavizado lo borraría y el
control no tendría efecto visible.

Bayer
-----
Cada píxel del sensor ve un solo color (patrón RGGB). Se reconstruye el mosaico
y se vuelve a interpolar con el demosaico adaptativo a bordes de OpenCV: deja
el leve ablandamiento y los mínimos falsos colores en bordes finos que tiene
cualquier foto de cámara digital.

Rendimiento (12 MP, CPU): ruido ≈ 0,5 s · Bayer ≈ 0,3 s.
"""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from .comun import decodificar, derivada_codificar, gauss, luma, suavestep

_DERIVADA_MAX = 6.0  # evita que el ruido explote en el negro puro


def ruido_sensor(
    img: np.ndarray,
    s: float,
    cantidad: float,
    lectura: float,
    croma: float,
    correlacion: float,
    escala_vista: float,
    rng: np.random.Generator,
    mapa: Optional[np.ndarray] = None,
) -> None:
    """Suma ruido de sensor a ``img`` (gamma, float32), in situ.

    cantidad 0..1 (≈ ISO) · lectura 0..1 (peso del ruido de lectura frente al de
    disparo) · croma 0..1 · correlacion 0..1 (tamaño del grano tras el demosaico)
    · mapa: multiplicador por píxel (máscaras regionales) o None.
    """
    h, w = img.shape[:2]
    y = np.clip(luma(img), 0.0, 1.0)
    x = decodificar(y)
    a = 1.0 - 0.9 * lectura
    b = 0.02 * (0.1 + 0.9 * lectura)
    # Normalizado en el gris medio (18 %): "lectura" no cambia cuánto ruido hay
    # en total, solo lo corre hacia las sombras. Con 50 % el factor es 1.
    referencia = (0.55 * 0.18 + 0.011) / (a * 0.18 + b)
    sigma_lin = np.sqrt((a * x + b) * referencia)
    sigma = sigma_lin * np.minimum(derivada_codificar(x), _DERIVADA_MAX)
    # El negro puro sale limpio: el procesado lo recorta.
    sigma *= 0.3 + 0.7 * suavestep(0.0, 0.006, x)
    # En la vista previa reducida el ruido se promedia: se atenúa en proporción.
    amp = 0.044 * cantidad * escala_vista
    sigma *= amp
    if mapa is not None:
        sigma *= mapa

    grano = rng.standard_normal((h, w), dtype=np.float32)
    sigma_grano = (0.35 + 1.0 * correlacion) * s
    if sigma_grano >= 0.3:
        # El demosaico y la reducción de ruido dan un grano de 1-2 px, no píxeles sueltos.
        grano = gauss(grano, sigma_grano)
        muestra = grano[: min(h, 512), : min(w, 512)]
        grano /= max(float(muestra.std()), 1e-6)
    lum = grano * sigma

    if croma > 0:
        # Croma: manchas más grandes y sin cambiar la luminancia.
        bloque = max(1, round(4 * s))
        ch, cw = max(1, h // bloque), max(1, w // bloque)
        c = rng.standard_normal((ch, cw, 2), dtype=np.float32)
        c = cv2.resize(c, (w, h), interpolation=cv2.INTER_CUBIC)
        c *= (0.6 * croma * sigma)[..., None]
        cr, cb = c[..., 0], c[..., 1]
        cg = -(0.2126 * cr + 0.0722 * cb) / 0.7152
        img[..., 0] += lum + cr
        img[..., 1] += lum + cg
        img[..., 2] += lum + cb
    else:
        img += lum[..., None]


# Patrón RGGB: fila par R G R G…, fila impar G B G B…
# (en la nomenclatura de OpenCV ese mosaico se lee como "BayerBG").
_DEMOSAICO = cv2.COLOR_BayerBG2RGB_EA


def mosaico_bayer(lin: np.ndarray, escala_vista: float) -> np.ndarray:
    """Pasa ``lin`` (lineal, float32) por un mosaico RGGB y su demosaico."""
    h, w = lin.shape[:2]
    h2, w2 = h - h % 2, w - w % 2
    if h2 < 4 or w2 < 4:
        return lin
    q = (np.clip(lin[:h2, :w2], 0.0, 1.0) * 65535.0 + 0.5).astype(np.uint16)
    m = np.empty((h2, w2), np.uint16)
    m[0::2, 0::2] = q[0::2, 0::2, 0]  # R
    m[0::2, 1::2] = q[0::2, 1::2, 1]  # G
    m[1::2, 0::2] = q[1::2, 0::2, 1]  # G
    m[1::2, 1::2] = q[1::2, 1::2, 2]  # B
    rgb = cv2.cvtColor(m, _DEMOSAICO).astype(np.float32) / 65535.0
    salida = lin.copy()
    # En la vista previa un píxel equivale a varios del original: los artefactos
    # de 1 px se verían exagerados, así que se atenúan en proporción.
    t = float(min(1.0, escala_vista))
    salida[:h2, :w2] += t * (rgb - lin[:h2, :w2])
    return salida
