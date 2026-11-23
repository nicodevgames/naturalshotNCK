"""Color y respuesta tonal.

Lineal (antes de codificar):
  * exposición y balance de blancos       ganancias por canal
  * variación de balance                  luz mezclada: el balance cambia apenas en la escena
  * tono local                            compresión local de rango, como el HDR del celular
Codificado (después):
  * curva global                          caída de luces, pie de sombras, contraste en S
  * zonas                                 brillo de sombras / medios / luces por separado
  * saturación y desaturación de luces
  * respuesta de cámara                   corrimientos de tono típicos del procesado de color

Separación global/local: la curva, las zonas y la saturación son globales (el
mismo valor de entrada da la misma salida en toda la foto); el tono local y la
variación de balance dependen de la zona.

Rendimiento (12 MP, CPU): balance ≈ 0,1 s · variación ≈ 0,2 s · tono local ≈ 0,5 s ·
curva+zonas ≈ 0,4 s · saturación ≈ 0,2 s · respuesta de cámara ≈ 0,6 s.
"""

from __future__ import annotations

import cv2
import numpy as np

from .comun import PESOS_LUMA, campo_suave, guiado_coeficientes, luma, suavestep


def exposicion_y_balance(lin: np.ndarray, expo: float, temp: float, tinte: float) -> None:
    ganancia = 2.0 ** (0.5 * expo)  # hasta ±0,5 EV
    canales = np.array([1.0 + 0.12 * temp, 1.0 - 0.07 * tinte, 1.0 - 0.12 * temp], dtype=np.float32)
    canales /= float(canales @ PESOS_LUMA)  # el balance no cambia el brillo
    lin *= (canales * ganancia).astype(np.float32)


def variacion_balance(lin: np.ndarray, v: float, rng: np.random.Generator) -> None:
    """Luz mezclada: temperatura y tinte cambian suavemente de una zona a otra
    (ventana fría de un lado, lámpara cálida del otro). Hasta ±6 % / ±3 %."""
    h, w = lin.shape[:2]
    t = (0.06 * v) * campo_suave(h, w, rng, celdas=3)
    g = (0.03 * v) * campo_suave(h, w, rng, celdas=3)
    r, gg, b = 1.0 + t, 1.0 - g, 1.0 - t
    norma = PESOS_LUMA[0] * r + PESOS_LUMA[1] * gg + PESOS_LUMA[2] * b
    lin[..., 0] *= r / norma
    lin[..., 1] *= gg / norma
    lin[..., 2] *= b / norma


def tono_local(lin: np.ndarray, t: float) -> None:
    """Compresión local de rango (abre sombras, contiene luces), como el HDR de un celular.

    La base de iluminación sale de un filtro guiado rápido (coeficientes a baja
    resolución aplicados sobre la luminancia completa) para no generar halos.
    """
    h, w = lin.shape[:2]
    log_y = np.log2(np.maximum(luma(lin), 0.0) + 1e-4).astype(np.float32)
    f = min(1.0, 400 / max(h, w))
    sw, sh = max(1, round(w * f)), max(1, round(h * f))
    chico = cv2.resize(log_y, (sw, sh), interpolation=cv2.INTER_AREA)
    r = max(2, round(max(sw, sh) * 0.035))
    a, b = guiado_coeficientes(chico, r, eps=0.35)
    a = cv2.resize(a, (w, h), interpolation=cv2.INTER_LINEAR)
    b = cv2.resize(b, (w, h), interpolation=cv2.INTER_LINEAR)
    base = a * log_y + b
    # Asimétrico: las sombras se abren con decisión y las luces solo se
    # contienen un poco, para que el blanco siga siendo blanco.
    exponente = (-0.32 * t) * np.minimum(base - np.log2(0.18), 0.0)
    exponente -= (0.10 * t) * np.maximum(base - np.log2(0.5), 0.0)
    ganancia = np.exp2(exponente)
    np.clip(ganancia, 0.6, 3.0, out=ganancia)
    lin *= ganancia[..., None]


def curva_global(img: np.ndarray, t: float, contraste: float, luces: float, sombras: float,
                 zonas: tuple[float, float, float]) -> None:
    """Curva tonal no lineal sobre la luminancia.

    t        elevación suave de sombras y caída de luces del procesado base
    luces    highlight roll-off: hombro más largo, el blanco llega de a poco
    sombras  shadow roll-off: pie suave, el negro queda apenas levantado
    zonas    (sombras, medios, luces) brillo por zona, -1..1
    """
    y = luma(img)
    c = np.maximum(y, 0.0)
    if luces:
        # Se aplica ANTES de recortar: lo que la exposición o el HDR empujaron por
        # encima del blanco se comprime de a poco en vez de quemarse de golpe.
        rodilla = 0.62
        hombro = rodilla + (1.0 - rodilla) * np.tanh(np.maximum(c - rodilla, 0.0) / (1.0 - rodilla))
        c = np.where(c > rodilla, c + 0.6 * luces * (hombro - c), c)
    c = np.minimum(c, 1.0)
    if t:
        c = c + 0.24 * t * c * (1.0 - c) ** 3
        rodilla = 0.78
        hombro = rodilla + (1.0 - rodilla) * np.tanh(np.maximum(c - rodilla, 0.0) / (1.0 - rodilla))
        c = np.where(c > rodilla, c + 0.35 * t * (hombro - c), c)
    if sombras:
        # Pie: el negro sube hasta ≈ 9/255 y las sombras se comprimen sin cortarse.
        pie = 0.035 * (1.0 - suavestep(0.0, 0.3, c))
        c = c + sombras * pie * (1.0 - c)
    if contraste:
        s = c * c * (3.0 - 2.0 * c)
        c = c + 0.6 * contraste * (s - c)
    zs, zm, zl = zonas
    if zs or zm or zl:
        w_s = 1.0 - suavestep(0.0, 0.5, c)
        w_l = suavestep(0.5, 1.0, c)
        w_m = np.exp(-(((c - 0.5) / 0.22) ** 2))
        extremos = 4.0 * c * (1.0 - c)  # 0 en negro y blanco: no se cortan
        c = c + 0.10 * (zs * w_s + zm * w_m + zl * w_l) * extremos
    img += (c - y)[..., None]


def saturacion(img: np.ndarray, sat: float, desat_luces: float) -> None:
    if not sat and not desat_luces:
        return
    y = luma(img)[..., None]
    factor = 1.0 + 0.4 * sat
    if desat_luces:
        # Cerca del blanco el sensor se satura y el color se lava.
        factor = factor * (1.0 - 0.85 * desat_luces * suavestep(0.62, 0.98, y))
    img -= y
    img *= factor
    img += y


# Corrimientos de tono (grados) del render de color típico de una cámara:
# rojos hacia naranja (piel más cálida), verdes hacia amarillo, azules hacia cian.
_CENTROS = np.array([0.0, 120.0, 240.0], dtype=np.float32)
_CORRIMIENTOS = np.array([7.0, -9.0, -8.0], dtype=np.float32)


def respuesta_camara(img: np.ndarray, r: float) -> None:
    """Respuesta cromática de cámara aproximada: corre el tono de rojos, verdes y
    azules hacia donde los lleva el procesado de color de una cámara común.
    No reproduce ninguna cámara concreta."""
    hsv = cv2.cvtColor(np.clip(img, 0.0, 1.0), cv2.COLOR_RGB2HSV)
    h = hsv[..., 0]
    dh = np.zeros_like(h)
    for centro, corr in zip(_CENTROS, _CORRIMIENTOS):
        d = np.abs(((h - centro) + 180.0) % 360.0 - 180.0)
        dh += corr * np.exp(-((d / 35.0) ** 2))
    hsv[..., 0] = (h + r * dh) % 360.0
    nuevo = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
    # Solo cambia el tono: se respeta la luminancia y lo que se salía de rango.
    nuevo += (luma(img) - luma(nuevo))[..., None]
    img[...] = nuevo
