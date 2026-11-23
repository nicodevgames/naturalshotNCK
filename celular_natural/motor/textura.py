"""Detalle y texturas (en la imagen codificada, sobre la luminancia).

Se trabaja sobre la luma para no generar corrimientos de color: la diferencia
se suma a los tres canales. Todas las cantidades pueden ser un número o un mapa
HxW (máscaras regionales), así cada zona recibe su propia dosis.

  * claridad           contraste local de frecuencias medias (±)
  * microcontraste     baja el contraste de la textura fina "de render"
  * nitidez            comprime los sobreimpulsos (halos de enfoque)
  * suavizado          aplana texturas finas como la reducción de ruido del celular
  * nitidez variable   foco apenas desparejo en la imagen
  * piel real          lo contrario del suavizado para la piel de IA: poros y menos brillo

Todos los filtros preservan bordes (filtro guiado), así no hay desenfoque global
ni halos nuevos.

Rendimiento (12 MP, CPU): claridad ≈ 0,4 s · microcontraste ≈ 0,5 s · nitidez ≈ 0,2 s
· suavizado ≈ 0,6 s · nitidez variable ≈ 0,2 s · piel ≈ 0,6 s.
"""

from __future__ import annotations

from typing import Callable, Union

import numpy as np

from .comun import campo_suave, desvio_local, gauss, guiado, guiado_con_guia, luma, suavestep

Cantidad = Union[float, np.ndarray]


def _hay(x: Cantidad) -> bool:
    return bool(np.any(x)) if isinstance(x, np.ndarray) else bool(x)


def detalle(
    img: np.ndarray,
    s: float,
    claridad: float,
    micro: Cantidad,
    nit: Cantidad,
    suav: Cantidad,
    variable: float,
    rng: np.random.Generator,
    verificar: Callable[[], None],
) -> None:
    y0 = luma(img)
    y = y0

    if claridad:
        # Base de frecuencias medias que respeta los bordes grandes: la diferencia
        # es el "punch" local. Negativo = menos claridad (la IA suele exagerarla).
        base = guiado(y, max(2, round(25 * s)), eps=0.08 ** 2)
        local = y - base
        # Protege negros y blancos para no empastar ni quemar.
        proteccion = 4.0 * np.clip(y, 0, 1) * (1.0 - np.clip(y, 0, 1))
        y = y + 0.6 * claridad * local * proteccion
        verificar()

    if _hay(micro):
        # Base que preserva bordes importantes; la diferencia es la textura fina
        # de bajo contraste que los renders y la IA suelen exagerar.
        base = guiado(y, max(2, round(10 * s)), eps=0.03 ** 2)
        y = y - 0.55 * micro * (y - base)
        verificar()

    if _hay(nit):
        borroso = gauss(y, max(0.5, 1.0 * s))
        d = y - borroso
        umbral = 0.035
        # Comprime los sobreimpulsos grandes (halos de enfoque) y atenúa el resto.
        d = (1.0 - nit) * d + nit * (umbral * np.tanh(d / umbral))
        d *= 1.0 - 0.5 * nit
        y = borroso + d
        verificar()

    if _hay(suav):
        # Aplana texturas finas de bajo contraste (piel, cielos, paredes) como la
        # reducción de ruido de un celular, manteniendo los contornos.
        suave = guiado(y, max(1, round(2.5 * s)), eps=0.018 ** 2)
        y = y + 0.8 * suav * (suave - y)
        # Los celulares suavizan el croma con más fuerza que la luminancia.
        croma = img - y0[..., None]
        croma_suave = gauss(croma, max(0.6, 1.6 * s))
        k = 0.7 * (suav[..., None] if isinstance(suav, np.ndarray) else suav)
        img += k * (croma_suave - croma)
        verificar()

    if variable:
        # Foco desparejo: un campo muy suave decide cuánto se ablanda cada zona.
        h, w = y.shape
        campo = 0.5 * (1.0 + campo_suave(h, w, rng, celdas=3))
        borroso = gauss(y, max(0.5, 1.4 * s))
        y = y + (0.75 * variable) * campo * (borroso - y)
        verificar()

    img += (y - y0)[..., None]


def piel_real(img: np.ndarray, s: float, p: float, escala_vista: float, rng: np.random.Generator,
              verificar: Callable[[], None], mascara_piel: np.ndarray | None = None) -> None:
    """Devuelve textura a las superficies "de plástico" típicas de la IA.

    Se buscan las zonas lisas de medios tonos (sobre todo piel) y se les suma una
    textura de poro irregular; además se apagan un poco los brillos altos lisos.
    Los bordes y lo que ya tiene textura no se tocan. Con máscaras regionales
    activas se limita a la piel detectada.
    """
    h, w = img.shape[:2]
    y = np.clip(luma(img), 0.0, 1.0)
    lisa = 1.0 - suavestep(0.008, 0.035, desvio_local(y, max(1, round(6 * s))))
    medios = suavestep(0.12, 0.30, y) * (1.0 - suavestep(0.88, 0.98, y))
    zona = lisa * medios
    if mascara_piel is not None:
        zona = zona * mascara_piel
    verificar()

    # Poro: ruido pasa-banda, manchitas irregulares de 1 a 4 px en 12 MP.
    base = rng.standard_normal((h, w), dtype=np.float32)
    poro = gauss(base, max(0.5, 0.9 * s)) - gauss(base, max(1.0, 3.0 * s))
    muestra = poro[: min(h, 512), : min(w, 512)]
    poro /= max(float(muestra.std()), 1e-6)
    amp = 0.03 * p * escala_vista  # en la vista previa reducida se promedia
    delta = poro * (amp * zona)
    verificar()

    # Brillo de plástico: las luces altas lisas bajan un poco. La máscara se
    # extiende siguiendo los contornos (filtro guiado): si no, la franja pegada a
    # un borde quedaría sin bajar y se vería como un ribete claro.
    lisa_guiada = np.clip(guiado_con_guia(y, lisa, max(3, round(10 * s)), eps=1e-3), 0.0, 1.0)
    brillo = suavestep(0.72, 0.95, y) * lisa_guiada
    if mascara_piel is not None:
        brillo = brillo * mascara_piel
    delta -= (0.25 * p) * brillo * np.maximum(y - 0.72, 0.0)
    img += delta[..., None]
