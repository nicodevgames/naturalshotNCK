"""Mide cuánto tarda cada efecto sobre una foto de 12 MP (4032×3024) en esta PC.

Uso:  .venv\\Scripts\\python.exe herramientas\\medir_rendimiento.py
"""

from __future__ import annotations

import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from celular_natural.motor import NEUTRO, PRESETS, procesar  # noqa: E402

PRUEBAS = {
    "Ruido de sensor": dict(ruido=50),
    "Bayer + demosaico": dict(bayer=True),
    "Desenfoque óptico": dict(desenfoque=50),
    "Distorsión": dict(distorsion=50),
    "Aberración cromática": dict(aberracion=50),
    "Bordes blandos": dict(bordes=50),
    "Viñeteo": dict(vineteo=50),
    "Nitidez": dict(nitidez=50),
    "Microcontraste": dict(microcontraste=50),
    "Claridad": dict(claridad=-50),
    "Suavizado": dict(suavizado=50),
    "Nitidez variable": dict(nitidez_variable=50),
    "Piel real": dict(piel=50),
    "Tono local (HDR)": dict(tono=50),
    "Curva y zonas": dict(contraste=20, luces=50, sombras=50, zona_medios=30),
    "Respuesta de cámara": dict(respuesta_camara=50),
    "Variación de balance": dict(variacion_balance=50),
    "Grano monocromo": dict(grano=50),
    "Grano cromático": dict(grano=50, grano_croma=50),
    "Reescalado": dict(reescalado=50),
    "JPEG": dict(jpeg=50),
    "Máscaras regionales (1ª vez)": dict(ruido=50, regiones_activas=True),
}


def main() -> None:
    rng = np.random.default_rng(0)
    img = (rng.random((3024, 4032, 3)) * 60 + 100).astype(np.uint8)
    procesar(img[:64, :64], NEUTRO)  # calentamiento
    t0 = time.perf_counter()
    procesar(img, replace(NEUTRO, exposicion=1))
    base = time.perf_counter() - t0
    print(f"{'Efecto':32s} segundos (12 MP)")
    print(f"{'(conversión base)':32s} {base:5.2f}")
    for nombre, kw in PRUEBAS.items():
        t0 = time.perf_counter()
        procesar(img, replace(NEUTRO, **kw))
        print(f"{nombre:32s} {time.perf_counter() - t0:5.2f}")
    for nombre in ("Celular natural — inspirado en iPhone 13", "Anti IA — piel real, sin calidad exagerada",
                   "Cámara compacta digital", "Noche con ISO alto"):
        t0 = time.perf_counter()
        procesar(img, PRESETS[nombre])
        print(f"PRESET {nombre[:25]:25s} {time.perf_counter() - t0:5.2f}")


if __name__ == "__main__":
    main()
