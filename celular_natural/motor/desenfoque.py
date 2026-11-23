"""Desenfoque de fondo (modo retrato): el objeto queda nítido y lo de afuera se
desenfoca como con un lente muy abierto.

Técnica
-------
* **Disco, no campana.** Un punto fuera de foco se ve como la apertura del
  lente: un disco parejo de borde definido (bokeh). Se usa un disco con
  antialias en vez de una gaussiana, que da el borroso lavado de un filtro barato.
* **En luz lineal.** Se promedia luz y no valores codificados: las luces chicas
  se abren en discos brillantes en vez de apagarse. Las casi quemadas se
  realzan un poco antes de desenfocar (en la escena eran más fuertes que el
  blanco del archivo) y el realce se deshace después, así una zona pareja no
  cambia de brillo.
* **Sin halo (convolución normalizada).** Se desenfocan por separado ``img·p``
  y ``p``, donde ``p`` es el peso del fondo (0 en el objeto y en una franja
  fina alrededor del contorno, que suele tener colores mezclados), y se
  dividen. Cada píxel del fondo promedia solo fondo: el color del objeto no se
  derrama y el borde no se oscurece ni se aclara. El borde de la imagen se
  trata igual: no se inventan píxeles reflejados.
* **Relleno del objeto.** Donde el disco no ve fondo (adentro del objeto) se
  completa con el fondo vecino: primero con el nivel de desenfoque más grueso
  y, en el más grueso, por pirámide (push-pull). Así el borde suave de la
  máscara mezcla el objeto con fondo desenfocado y no con negro.
* **Transición y profundidad.** Se calculan hasta tres niveles (1/3, 2/3 y el
  radio completo) y se mezclan píxel por píxel según la distancia al objeto:
  la transición hace que el fondo pegado al objeto pase de nítido a borroso de
  a poco, y la profundidad gradual desenfoca más lo que está más lejos.
* **A resolución reducida.** Cada disco se calcula sobre la imagen achicada
  hasta que su radio mide unos 5 px (un kernel de 11 × 11, que OpenCV aplica
  directo y en paralelo) y se vuelve a ampliar: lo borroso no tiene detalle
  fino que perder. Solo la mezcla con la foto nítida va a resolución completa.

El radio es relativo al lado largo de la foto ORIGINAL (como las zonas): se ve
igual en la vista previa reducida, en la exportación y con recorte.

Va ANTES del filtro, como el montaje: el ruido, el grano y la óptica se aplican
parejos sobre toda la foto y el fondo no queda liso delatando el truco.

Costo (12 MP, 4000 × 3000, medido en esta PC): ≈0,2 s con un nivel y ≈0,4 s
con transición o profundidad, más ≈0,2 s de la máscara de un lazo (en total
0,4-0,6 s). En la vista previa de 1280 px, 0,05-0,2 s. Se cachea por imagen y
parámetros, así mover otros controles no lo recalcula.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Optional

import cv2
import numpy as np

from .comun import lineal_a_srgb, srgb_a_lineal
from .zonas import Recorte, Zona, _lado_original, mascara_zona

INTENSIDAD_INICIAL = 35
TRANSICION_INICIAL = 15
RADIO_MAXIMO = 0.035          # radio del disco con intensidad 100, relativo al lado largo
TRANSICION_MAXIMA = 0.10      # ancho de la transición con 100, relativo al lado largo
PROFUNDIDAD_LEJOS = 0.35      # distancia al objeto (relativa) donde llega al desenfoque completo
PROFUNDIDAD_CERCA = 0.45      # fracción del desenfoque pegado al objeto con profundidad gradual
MARGEN_CONTORNO = 0.002       # franja alrededor del contorno que no aporta color al fondo
RADIO_CHICO = 5.0             # radio (px) al que se achica la imagen para calcular cada disco
LADO_NIVEL = 2048             # lado largo máximo de la imagen achicada de un nivel
NIVELES = (1 / 3, 2 / 3, 1.0)  # fracciones del radio que se calculan para mezclar
CONFIANZA = 0.1               # fracción de fondo dentro del disco a partir de la cual no se rellena
REALCE_LUCES = 1.5            # cuánto más fuerte se toma una luz quemada al desenfocar
UMBRAL_LUCES = 0.8            # desde qué luz lineal se realza (≈ 231 en 8 bits)


# ---------------------------------------------------------------- tablas
def _realce(lin: np.ndarray) -> np.ndarray:
    t = np.clip((lin - UMBRAL_LUCES) / (1.0 - UMBRAL_LUCES), 0.0, 1.0)
    return lin * (1.0 + REALCE_LUCES * t * t)


# 8 bits → luz lineal con las luces realzadas.
LUT_REALZAR = _realce(srgb_a_lineal(np.arange(256, dtype=np.float64) / 255.0)).astype(np.float32)
# Inversa: luz realzada → valor codificado 0..1 (deshace el realce y codifica en un paso).
_TOPE = 1.0 + REALCE_LUCES
_x = np.linspace(0.0, 1.0, 8193)
LUT_DESHACER = lineal_a_srgb(np.interp(np.linspace(0.0, _TOPE, 65536), _realce(_x), _x)).astype(np.float32)


def _deshacer(v: np.ndarray) -> np.ndarray:
    idx = np.clip(v * (65535.0 / _TOPE), 0.0, 65535.0)
    idx += 0.5
    return LUT_DESHACER[idx.astype(np.uint16)]


def radio_desenfoque(intensidad: float, lado: float) -> float:
    """Radio del disco en píxeles para una foto de lado largo ``lado``."""
    return RADIO_MAXIMO * min(max(float(intensidad), 0.0), 100.0) / 100.0 * float(lado)


def disco(radio: float) -> np.ndarray:
    """Kernel de disco con borde antialias (suma 1)."""
    r = max(float(radio), 0.5)
    n = int(np.floor(r + 0.5))
    yy, xx = np.mgrid[-n:n + 1, -n:n + 1].astype(np.float32)
    k = np.clip(r + 0.5 - np.sqrt(xx * xx + yy * yy), 0.0, 1.0)
    return (k / k.sum()).astype(np.float32)


# ---------------------------------------------------------------- etapas
def _rellenar(valor: np.ndarray, peso: np.ndarray) -> np.ndarray:
    """Push-pull: donde ``peso`` es bajo, completa con el promedio del entorno.

    Donde ``peso`` llega a 1 el valor queda tal cual.
    """
    if float(peso.min()) >= 1.0:
        return valor
    num, den = valor * peso[..., None], peso
    pila = []
    while min(den.shape[:2]) > 4:
        pila.append((num, den))
        num, den = cv2.pyrDown(num), cv2.pyrDown(den)
    if float(den.max()) <= 0.0:
        return valor
    est = num / np.maximum(den, 1e-6)[..., None]
    sin_dato = den <= 1e-6
    if sin_dato.any():
        est[sin_dato] = num.reshape(-1, 3).sum(0) / max(float(den.sum()), 1e-6)
    for num_n, den_n in reversed(pila):
        grueso = cv2.pyrUp(est, dstsize=(den_n.shape[1], den_n.shape[0]))
        a = np.clip(den_n * 4.0, 0.0, 1.0)[..., None]
        est = num_n / np.maximum(den_n, 1e-6)[..., None] * a + grueso * (1.0 - a)
    return est


def _disco_normalizado(num: np.ndarray, den: np.ndarray, radio: float) -> tuple[np.ndarray, np.ndarray]:
    """Promedio del fondo dentro del disco y cuánto fondo vio (confianza 0..1)."""
    k = disco(radio)
    a = cv2.filter2D(num, -1, k, borderType=cv2.BORDER_CONSTANT)
    b = cv2.filter2D(den, -1, k, borderType=cv2.BORDER_CONSTANT)
    a /= np.maximum(b, 1e-6)[..., None]
    return a, np.clip(b * (1.0 / CONFIANZA), 0.0, 1.0)


def _subida(t: np.ndarray) -> np.ndarray:
    """0 → 1 entre t = 0 y t = 1, rápida al principio (cúbica invertida)."""
    t = 1.0 - np.clip(t, 0.0, 1.0)
    return 1.0 - t * t * t


def mapa_desenfoque(mascara: np.ndarray, tam: tuple[int, int], lado: float, transicion: float,
                    profundidad: bool) -> np.ndarray:
    """Cuánto desenfoque lleva cada píxel (0..1 del radio) según su distancia al objeto.

    ``tam``: (ancho, alto) de salida. ``lado``: lado largo de la foto original en
    píxeles de ``mascara``.
    """
    h, w = mascara.shape[:2]
    f = min(1.0, 1024.0 / max(h, w))
    dw, dh = max(1, round(w * f)), max(1, round(h * f))
    chica = cv2.resize(mascara, (dw, dh), interpolation=cv2.INTER_AREA) if f < 1.0 else mascara
    objeto = chica >= 0.5
    if objeto.any():
        dist = cv2.distanceTransform((~objeto).astype(np.uint8), cv2.DIST_L2, 5)
        dist *= (w / dw) / max(lado, 1.0)  # relativa al lado largo de la foto original
    else:
        dist = np.full((dh, dw), 10.0, np.float32)
    # Curvas que suben rápido al principio: el fondo deja de verse nítido a pocos
    # píxeles del contorno y no queda un "aura" nítida alrededor del objeto. La
    # transición arranca ya un poco desenfocada (+0,1), así el fondo pegado al
    # contorno no se ve recortado a tijera.
    a = np.ones_like(dist)
    if transicion > 0:
        a = _subida(dist / (TRANSICION_MAXIMA * min(float(transicion), 100.0) / 100.0) + 0.1)
    if profundidad:
        a = a * (PROFUNDIDAD_CERCA + (1.0 - PROFUNDIDAD_CERCA) * _subida(dist / PROFUNDIDAD_LEJOS))
    a = a.astype(np.float32, copy=False)
    if (dw, dh) != tuple(tam):
        a = cv2.resize(a, tuple(tam), interpolation=cv2.INTER_LINEAR)
    return a


def desenfocar_fondo(rgb: np.ndarray, mascara: np.ndarray, intensidad: float = INTENSIDAD_INICIAL,
                     transicion: float = TRANSICION_INICIAL, profundidad: bool = False,
                     lado: Optional[float] = None) -> np.ndarray:
    """Desenfoca lo de afuera del objeto. Devuelve un RGB uint8 nuevo.

    ``mascara``: float32 HxW en 0..1, 1 = objeto (queda nítido). ``lado``: lado
    largo de la foto original medido en píxeles de ``rgb`` (por defecto, el de
    ``rgb``); el radio es relativo a él.
    """
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("Se esperaba un arreglo RGB uint8 de forma HxWx3")
    rgb = np.ascontiguousarray(rgb)
    h, w = rgb.shape[:2]
    lado = float(lado or max(h, w))
    radio = radio_desenfoque(intensidad, lado)
    m = np.clip(mascara.astype(np.float32, copy=False), 0.0, 1.0)
    if radio < 0.5 or float(m.min()) >= 1.0:
        return rgb.copy()

    # Peso del fondo: 0 desde la mitad del borde suave hacia adentro, más una
    # franja fina donde el contorno marcado a mano suele mezclar colores.
    peso = cv2.max(cv2.addWeighted(m, -2.0, m, 0.0, 1.0), 0.0)
    margen = int(round(MARGEN_CONTORNO * lado))
    if margen >= 1:
        peso = cv2.erode(peso, cv2.getStructuringElement(cv2.MORPH_RECT, (2 * margen + 1, 2 * margen + 1)))
    if float(peso.max()) <= 0.0:
        peso = 1.0 - m
    num = cv2.LUT(rgb, LUT_REALZAR)
    num *= peso[..., None]  # solo color del fondo: el del objeto no entra en ningún promedio

    # Niveles de desenfoque, cada uno achicado hasta que su disco mide ~5 px
    # (y a lo sumo LADO_NIVEL de lado largo).
    usar = (1.0,) if transicion <= 0 and not profundidad else NIVELES
    piramide = []
    fuente_num, fuente_den = num, peso
    for frac in usar:
        r = radio * frac
        f = max(1.0, r / RADIO_CHICO, max(h, w) / LADO_NIVEL)
        tam = (max(1, round(w / f)), max(1, round(h / f)))
        if tam != (fuente_den.shape[1], fuente_den.shape[0]):
            fuente_num = cv2.resize(fuente_num, tam, interpolation=cv2.INTER_AREA)
            fuente_den = cv2.resize(fuente_den, tam, interpolation=cv2.INTER_AREA)
        piramide.append((fuente_num, fuente_den, r / (0.5 * (w / tam[0] + h / tam[1]))))
    del num, fuente_num, fuente_den
    # De grueso a fino: lo que un disco no ve (adentro del objeto) lo completa el
    # nivel más grueso; el más grueso se completa por pirámide.
    niveles: list = [None] * len(piramide)
    grueso = None
    for i in reversed(range(len(piramide))):
        num_i, den_i, r_i = piramide[i]
        valor, confianza = _disco_normalizado(num_i, den_i, r_i)
        if grueso is None:
            valor = _rellenar(valor, confianza)
        else:
            base = cv2.resize(grueso, (valor.shape[1], valor.shape[0]), interpolation=cv2.INTER_LINEAR)
            valor -= base
            valor *= confianza[..., None]
            valor += base
        grueso = valor
        niveles[i] = _deshacer(valor)
    del piramide, grueso

    # Mezcla de niveles en la resolución del más fino; "nítido" es el peso de la foto original.
    th, tw = niveles[0].shape[:2]
    nitido = None
    if len(niveles) == 1:
        borroso = niveles[0]
    else:
        x = mapa_desenfoque(m, (tw, th), lado, transicion, profundidad) * 3.0
        nitido = np.clip(1.0 - x, 0.0, 1.0)
        borroso = np.zeros((th, tw, 3), np.float32)
        for i, nivel in enumerate(niveles, start=1):
            peso_i = np.clip(x - 2.0, 0.0, 1.0) if i == 3 else np.clip(1.0 - np.abs(x - i), 0.0, 1.0)
            if i == 1:
                peso_i += nitido  # donde manda la foto nítida, el nivel 1 completa
            if nivel.shape[:2] != (th, tw):
                nivel = cv2.resize(nivel, (tw, th), interpolation=cv2.INTER_LINEAR)
            borroso += nivel * peso_i[..., None]

    # A resolución completa: foto nítida + fondo desenfocado según la máscara.
    borroso = np.clip(borroso * 255.0 + 0.5, 0.0, 255.0).astype(np.uint8)
    if borroso.shape[:2] != (h, w):
        borroso = cv2.resize(borroso, (w, h), interpolation=cv2.INTER_CUBIC)
    mezcla = 1.0 - m
    if nitido is not None:
        if nitido.shape[:2] != (h, w):
            nitido = cv2.resize(nitido, (w, h), interpolation=cv2.INTER_LINEAR)
        mezcla *= 1.0 - nitido
    # (borroso·w1 + foto·w2) / (w1 + w2): donde la mezcla es 0 el píxel queda idéntico.
    return cv2.blendLinear(borroso, rgb, mezcla, 1.0 - mezcla)


# ------------------------------------------------------------------- caché
_CACHE: "OrderedDict[tuple, tuple[np.ndarray, np.ndarray]]" = OrderedDict()
_MAX_BYTES = 200 * 2 ** 20
_CANDADO = threading.Lock()  # la vista rápida y la completa corren en hilos distintos


def desenfocar_zona(rgb: np.ndarray, zona: Zona, intensidad: float = INTENSIDAD_INICIAL,
                    transicion: float = TRANSICION_INICIAL, profundidad: bool = False,
                    recorte: Optional[Recorte] = None) -> np.ndarray:
    """Desenfoca lo de afuera de ``zona`` (en coordenadas de la foto original).

    ``recorte``: con el que se recortó ``rgb`` (ubica la zona y da el lado largo
    de la original). El resultado se cachea por imagen y parámetros y es de solo
    lectura.
    """
    clave = (id(rgb), rgb.shape, zona, int(intensidad), int(transicion), bool(profundidad), recorte)
    with _CANDADO:
        previo = _CACHE.get(clave)
        if previo is not None and previo[0] is rgb:
            _CACHE.move_to_end(clave)
            return previo[1]
    h, w = rgb.shape[:2]
    mascara = mascara_zona(zona, h, w, recorte)
    salida = desenfocar_fondo(rgb, mascara, intensidad, transicion, profundidad, _lado_original(h, w, recorte))
    salida.flags.writeable = False
    with _CANDADO:
        # Se guarda también la entrada: así su id no se reutiliza mientras esté en la caché.
        _CACHE[clave] = (rgb, salida)
        while len(_CACHE) > 1 and sum(a.nbytes + b.nbytes for a, b in _CACHE.values()) > _MAX_BYTES:
            _CACHE.popitem(last=False)
    return salida


def limpiar_cache() -> None:
    with _CANDADO:
        _CACHE.clear()
