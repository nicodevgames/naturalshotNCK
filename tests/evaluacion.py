"""Escenas de prueba y métricas de calidad fotográfica.

No se usa ningún detector de imágenes de IA: sus puntajes no garantizan
naturalidad ni calidad. Se mide lo que un fotógrafo revisaría a mano:

  detalle      cuánto contraste conserva un borde nítido (no se lava la imagen)
  halo         sobreimpulso junto a un borde duro (niveles de 0-255)
  color        desvío de color promedio en una carta (ΔE CIE76, Lab)
  banding      escalones planos en un degradado suave (largo máximo de un tramo plano)
  ruido        desvío en un gris plano (niveles)
  resolución   energía de alta frecuencia que sobrevive en una textura fina (0-1)
  brillo       cambio del brillo medio (niveles)
"""

from __future__ import annotations

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# Escenas (RGB uint8). Tamaño moderado: rápidas pero con s ≈ 0,3.
# ---------------------------------------------------------------------------

def _f(img: np.ndarray) -> np.ndarray:
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def retrato(w=1200, h=900, semilla=0) -> np.ndarray:
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.empty((h, w, 3), np.float32)
    img[:] = (0.35, 0.38, 0.42)
    cara = ((xx - w * .45) / (w * .17)) ** 2 + ((yy - h * .45) / (h * .3)) ** 2 < 1
    piel = np.array([0.82, 0.6, 0.5], np.float32)
    sombreado = 0.85 + 0.15 * (1 - (xx - w * .45) / (w * .3))
    img[cara] = (piel[None, :] * sombreado[cara][:, None])
    # cabello: líneas finas oscuras
    pelo = (yy < h * .25) | ((xx < w * .3) & (yy < h * .8))
    hebras = 0.12 + 0.08 * np.sin(xx * 1.7 + rng.random() * 3) * np.sin(yy * 0.05)
    img[pelo & ~cara] = np.stack([hebras, hebras * .8, hebras * .6], -1)[pelo & ~cara]
    return _f(img)


def interior(w=1200, h=900) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    luz = np.exp(-(((xx - w * .7) / (w * .35)) ** 2 + ((yy - h * .3) / (h * .4)) ** 2))
    img = np.stack([0.15 + 0.6 * luz, 0.1 + 0.45 * luz, 0.06 + 0.28 * luz], -1)
    img[int(h * .6):, :] *= 0.6  # piso
    return _f(img)


def exterior(w=1200, h=900) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cielo = np.stack([0.45 + 0.3 * yy / h, 0.62 + 0.2 * yy / h, 0.95 - 0.1 * yy / h], -1)
    img = cielo.copy()
    suelo = yy > h * .55 + 30 * np.sin(xx / 90)
    img[suelo] = (0.25, 0.42, 0.18)
    img[int(h * .2):int(h * .55), int(w * .6):int(w * .75)] = (0.92, 0.9, 0.86)  # pared al sol
    return _f(img)


def noche(w=1200, h=900) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.stack([0.04 + 0.03 * yy / h, 0.04 + 0.02 * yy / h, 0.07 + 0.02 * yy / h], -1)
    for cx, cy in ((300, 300), (700, 250), (950, 420)):
        img += np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / 900.0)[..., None] * np.array([1.0, 0.75, 0.4])
    return _f(img)


def textil(w=1200, h=900) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    trama = 0.5 + 0.2 * np.sign(np.sin(xx * 1.1)) * np.sign(np.sin(yy * 1.1))
    img = np.stack([trama * .9, trama * .5, trama * .45], -1)
    return _f(img)


def degradado(w=1024, h=300) -> np.ndarray:
    rampa = np.linspace(0.25, 0.75, w, dtype=np.float32)
    return _f(np.repeat(np.tile(rampa, (h, 1))[..., None], 3, axis=2) * np.array([1.0, 0.9, 0.8], np.float32))


def alto_contraste(w=1200, h=900) -> np.ndarray:
    img = np.full((h, w, 3), 0.08, np.float32)
    img[:, w // 2:] = 0.92
    return _f(img)


def carta_color(w=1200, h=800) -> np.ndarray:
    colores = [(115, 82, 68), (194, 150, 130), (98, 122, 157), (87, 108, 67), (133, 128, 177),
               (103, 189, 170), (214, 126, 44), (80, 91, 166), (193, 90, 99), (94, 60, 108),
               (157, 188, 64), (224, 163, 46), (56, 61, 150), (70, 148, 73), (175, 54, 60),
               (231, 199, 31), (187, 86, 149), (8, 133, 161), (243, 243, 242), (200, 200, 200),
               (160, 160, 160), (122, 122, 121), (85, 85, 85), (52, 52, 52)]
    img = np.zeros((h, w, 3), np.uint8)
    cw, ch = w // 6, h // 4
    for i, c in enumerate(colores):
        r, q = divmod(i, 6)
        img[r * ch:(r + 1) * ch, q * cw:(q + 1) * cw] = c
    return img


ESCENAS = {
    "retrato": retrato, "interior": interior, "exterior": exterior, "noche": noche,
    "textil": textil, "degradado": degradado, "alto contraste": alto_contraste, "carta": carta_color,
}


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------

def _gris(x: np.ndarray) -> np.ndarray:
    return x.astype(np.float32).mean(-1)


def detalle_borde(antes: np.ndarray, despues: np.ndarray) -> float:
    """Contraste conservado a ±6 px del borde (1 = igual)."""
    a, d = _gris(antes), _gris(despues)
    w = a.shape[1] // 2
    filas = slice(a.shape[0] // 3, 2 * a.shape[0] // 3)
    salto = lambda x: x[filas, w + 6].mean() - x[filas, w - 7].mean()
    return float(salto(d) / max(salto(a), 1e-6))


def halo(antes: np.ndarray, despues: np.ndarray) -> float:
    """Cuánto pasa el lado claro de su meseta junto al borde (niveles)."""
    d = _gris(despues)
    w = d.shape[1] // 2
    filas = slice(d.shape[0] // 3, 2 * d.shape[0] // 3)
    perfil = d[filas].mean(0)
    meseta_clara = perfil[w + 40:w + 120].mean()
    meseta_oscura = perfil[w - 120:w - 40].mean()
    sobre = perfil[w:w + 20].max() - meseta_clara
    bajo = meseta_oscura - perfil[w - 20:w].min()
    return float(max(sobre, bajo, 0.0))


def delta_e(antes: np.ndarray, despues: np.ndarray) -> float:
    """ΔE76 medio por parche (centro de cada parche, sin bordes)."""
    lab = lambda x: cv2.cvtColor(x.astype(np.float32) / 255.0, cv2.COLOR_RGB2Lab)
    la, ld = lab(antes), lab(despues)
    h, w = antes.shape[:2]
    cw, ch = w // 6, h // 4
    total = []
    for r in range(4):
        for q in range(6):
            sl = (slice(r * ch + ch // 4, (r + 1) * ch - ch // 4), slice(q * cw + cw // 4, (q + 1) * cw - cw // 4))
            total.append(np.linalg.norm(la[sl].mean((0, 1)) - ld[sl].mean((0, 1))))
    return float(np.mean(total))


def banding(img: np.ndarray) -> int:
    """Largo del tramo plano más largo en una fila del degradado (px)."""
    fila = img[img.shape[0] // 2, :, 1].astype(np.int16)
    maximo = actual = 1
    for a, b in zip(fila[:-1], fila[1:]):
        actual = actual + 1 if a == b else 1
        maximo = max(maximo, actual)
    return int(maximo)


def ruido_plano(despues: np.ndarray) -> float:
    h, w = despues.shape[:2]
    return float(_gris(despues[h // 4:3 * h // 4, w // 4:3 * w // 4]).std())


def resolucion(antes: np.ndarray, despues: np.ndarray) -> float:
    """Energía de alta frecuencia que sobrevive (1 = toda)."""
    hf = lambda x: np.abs(cv2.Laplacian(_gris(x), cv2.CV_32F)).mean()
    return float(hf(despues) / max(hf(antes), 1e-6))


def brillo(antes: np.ndarray, despues: np.ndarray) -> float:
    return float(abs(despues.astype(np.float32).mean() - antes.astype(np.float32).mean()))
