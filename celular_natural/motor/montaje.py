"""Montaje: pegar partes de otras fotos sobre la foto base.

Pensado para fotos casi iguales (ráfagas, varias tomas de la misma escena):
de la foto 1 te gusta la mitad de arriba y de la foto 2 la de abajo.

Cada ``CapaFoto`` toma otra foto, la lleva al tamaño de la base, opcionalmente
la **alinea** (homografía estimada con puntos ORB + RANSAC, para corregir que
el celular se movió un poco entre tomas) y la **iguala en color** (media y
desvío por canal sobre la zona en común), y la mezcla dentro de su ``Zona`` con
borde fundido.

El montaje se arma ANTES del filtro: así el ruido, el grano y la óptica se
aplican parejos sobre el resultado y no se nota dónde se unieron las fotos.

Costo (12 MP): alineación ≈0,3 s la primera vez (se cachea), mezcla ≈0,2 s.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

import cv2
import numpy as np

from .zonas import Zona, mascara_zona


@dataclass(frozen=True)
class CapaFoto:
    ruta: str
    zona: Optional[Zona] = None  # None = toda la foto
    opacidad: int = 100  # 0..100
    alinear: bool = True
    igualar: bool = True


# ---------------------------------------------------------------- alineación
def _gris_chico(rgb: np.ndarray, lado: int = 1000) -> tuple[np.ndarray, float]:
    h, w = rgb.shape[:2]
    f = min(1.0, lado / max(h, w))
    chico = cv2.resize(rgb, (max(1, round(w * f)), max(1, round(h * f))), interpolation=cv2.INTER_AREA) if f < 1 else rgb
    return cv2.cvtColor(chico, cv2.COLOR_RGB2GRAY), f


def estimar_alineacion(base: np.ndarray, otra: np.ndarray) -> Optional[np.ndarray]:
    """Homografía 3x3 que lleva ``otra`` (ya del tamaño de ``base``) sobre ``base``.

    Devuelve None si no hay suficientes coincidencias confiables o si la
    transformación es implausible para dos tomas de la misma escena.
    """
    gb, f = _gris_chico(base)
    go, _ = _gris_chico(otra)
    orb = cv2.ORB_create(nfeatures=4000, fastThreshold=10)
    kb, db = orb.detectAndCompute(gb, None)
    ko, do = orb.detectAndCompute(go, None)
    if db is None or do is None or len(kb) < 12 or len(ko) < 12:
        return None
    pares = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(do, db, k=2)
    buenos = [m for m, *n in pares if n and m.distance < 0.75 * n[0].distance]
    if len(buenos) < 12:
        return None
    origen = np.float32([ko[m.queryIdx].pt for m in buenos])
    destino = np.float32([kb[m.trainIdx].pt for m in buenos])
    H, inliers = cv2.findHomography(origen, destino, cv2.RANSAC, 3.0)
    if H is None or inliers is None or int(inliers.sum()) < 12:
        return None
    det = float(np.linalg.det(H[:2, :2]))
    if not 0.7 < det < 1.4 or abs(H[2, 0]) > 2e-3 or abs(H[2, 1]) > 2e-3:
        return None
    S = np.diag([f, f, 1.0])
    return np.linalg.inv(S) @ H @ S


def alinear_foto(base: np.ndarray, otra: np.ndarray, alinear: bool = True
                 ) -> tuple[np.ndarray, np.ndarray, bool]:
    """Lleva ``otra`` al tamaño de ``base`` y, si se pide, la alinea.

    Devuelve (imagen uint8, máscara de píxeles válidos float32, si se alineó).
    """
    h, w = base.shape[:2]
    if otra.shape[:2] != (h, w):
        interp = cv2.INTER_AREA if otra.shape[0] * otra.shape[1] > h * w else cv2.INTER_CUBIC
        otra = cv2.resize(otra, (w, h), interpolation=interp)
    valida = np.ones((h, w), np.float32)
    if not alinear:
        return otra, valida, False
    H = estimar_alineacion(base, otra)
    if H is None:
        return otra, valida, False
    if np.allclose(H, np.eye(3), atol=1e-3):
        return otra, valida, True
    alineada = cv2.warpPerspective(otra, H, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    unos = np.full((h, w), 255, np.uint8)
    valida = cv2.warpPerspective(unos, H, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)
    # Se achica un poco el borde válido para no mezclar el borde replicado.
    valida = cv2.erode(valida, np.ones((5, 5), np.uint8)).astype(np.float32) / 255.0
    return alineada, valida, True


def igualar_color(base: np.ndarray, otra: np.ndarray, valida: np.ndarray) -> np.ndarray:
    """Empareja brillo y color de ``otra`` con ``base`` (media y desvío por canal)."""
    paso = max(1, int(np.sqrt(base.shape[0] * base.shape[1] / 250_000)))
    b = base[::paso, ::paso].reshape(-1, 3).astype(np.float32)
    o = otra[::paso, ::paso].reshape(-1, 3).astype(np.float32)
    m = valida[::paso, ::paso].reshape(-1) > 0.99
    if m.sum() < 100:
        return otra
    b, o = b[m], o[m]
    mb, sb = b.mean(0), b.std(0) + 1e-3
    mo, so = o.mean(0), o.std(0) + 1e-3
    ganancia = np.clip(sb / so, 0.8, 1.25)
    salida = (otra.astype(np.float32) - mo) * ganancia + mb
    return np.clip(salida + 0.5, 0, 255).astype(np.uint8)


# ------------------------------------------------------------------- caché
_CACHE: "OrderedDict[tuple, tuple[np.ndarray, np.ndarray, bool]]" = OrderedDict()
_MAX_CACHE = 6


def _preparada(clave_base: str, base: np.ndarray, capa: CapaFoto,
               cargar: Callable[[str], np.ndarray]) -> tuple[np.ndarray, np.ndarray, bool]:
    clave = (clave_base, base.shape, capa.ruta, capa.alinear, capa.igualar)
    if clave in _CACHE:
        _CACHE.move_to_end(clave)
        return _CACHE[clave]
    alineada, valida, ok = alinear_foto(base, cargar(capa.ruta), capa.alinear)
    if capa.igualar:
        alineada = igualar_color(base, alineada, valida)
    _CACHE[clave] = (alineada, valida, ok)
    while len(_CACHE) > _MAX_CACHE:
        _CACHE.popitem(last=False)
    return _CACHE[clave]


def componer(base: np.ndarray, capas: Sequence[CapaFoto], cargar: Callable[[str], np.ndarray],
             clave_base: str = "") -> tuple[np.ndarray, list[str]]:
    """Pega las capas de foto sobre ``base`` (uint8 HxWx3) en orden.

    ``cargar(ruta)`` devuelve el RGB uint8 de otra foto. Devuelve la imagen
    compuesta y avisos para mostrar (por ejemplo, si una foto no se pudo alinear).
    """
    avisos: list[str] = []
    if not capas:
        return base, avisos
    h, w = base.shape[:2]
    salida: Optional[np.ndarray] = None
    for capa in capas:
        if capa.opacidad <= 0:
            continue
        alineada, valida, ok = _preparada(clave_base, base, capa, cargar)
        if capa.alinear and not ok:
            avisos.append(f"No se pudo alinear {capa.ruta.replace(chr(92), '/').rsplit('/', 1)[-1]}: "
                          "se pegó sin alinear")
        m = mascara_zona(capa.zona, h, w) if capa.zona is not None else np.ones((h, w), np.float32)
        m = m * valida * (min(100, capa.opacidad) / 100.0)
        if salida is None:
            salida = base.astype(np.float32)
        salida += (alineada.astype(np.float32) - salida) * m[..., None]
    if salida is None:
        return base, avisos
    return np.clip(salida + 0.5, 0, 255).astype(np.uint8), avisos


def limpiar_cache() -> None:
    _CACHE.clear()
