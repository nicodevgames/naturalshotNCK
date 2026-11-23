"""Selección automática: cielo, piel y recorte inteligente del sujeto.

Sin IA ni pesos descargados: solo color, textura, conectividad y GrabCut de
OpenCV. Todas las funciones devuelven máscaras float32 HxW en [0, 1] con el
borde suave y pegado a los contornos reales de la foto.

Esquema común (rápido e independiente de la resolución):
  1. La foto se reduce (INTER_AREA) a lado largo ≤ 1024 px: la "resolución de
     trabajo". Los radios se expresan respecto de 1024 px y se escalan con la
     reducción, así la vista previa y la foto completa dan la misma máscara.
  2. A esa resolución se arma una máscara aproximada (binaria o casi).
  3. Se refina con un filtro guiado en color (He et al.: guía RGB, covarianza
     3x3 por píxel) usando la foto reducida como guía, y se lleva a la
     resolución completa con el "filtro guiado rápido" (He y Sun, 2015): los
     coeficientes lineales a, b se calculan reducidos, se amplían bilinealmente
     y se aplican sobre la foto COMPLETA (q = a·I + b). El borde sale nítido a
     resolución completa aunque el análisis se haya hecho reducido.

Las máscaras se pueden guardar en el historial con ``codificar_mascara`` (PNG
de 8 bits, lado largo ≤ 1024) y recuperar con ``decodificar_mascara``.

Costos medidos (PC de escritorio de 16 hilos, foto de 12 MP 4032x3024 uint8):
  * ``mascara_cielo``         ≈ 0,5-0,6 s (≈ 0,15 s es la ampliación guiada a 12 MP)
  * ``mascara_piel``          ≈ 0,3-0,4 s
  * ``recortar_objeto``       ≈ 0,8-0,95 s con 5 iteraciones: GrabCut a lado ≤ 640
    px ≈ 0,75 s (crece lineal con las iteraciones y con ``LADO_GRABCUT`` al
    cuadrado); reducir + filtro guiado + ampliar ≈ 0,15 s.
  * ``codificar_mascara``     ≈ 0,02 s (PNG de ≈ 10-15 KB para 12 MP)
  * ``decodificar_mascara``   ≈ 0,01 s
Las máscaras dependen solo de la foto (y de la selección inicial): conviene
cachearlas mientras se mueven los controles, como ``mascaras.regiones_en_cache``.
"""

from __future__ import annotations

from typing import Sequence

import cv2
import numpy as np

from .comun import caja, desvio_local, gauss, luma, suavestep

LADO_TRABAJO = 1024        # análisis de cielo y piel
LADO_GRABCUT = 640         # GrabCut es O(N·iteraciones): se corre más chico
LADO_GUARDADO = 1024       # máscaras guardadas en el historial
_SEMILLA_GRABCUT = 1234    # GrabCut inicializa sus GMM con k-means: semilla fija = resultado repetible

# Etiquetas de GrabCut (alias legibles).
_FONDO, _OBJETO, _PR_FONDO, _PR_OBJETO = cv2.GC_BGD, cv2.GC_FGD, cv2.GC_PR_BGD, cv2.GC_PR_FGD


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

def _rgb_uint8(rgb: np.ndarray) -> np.ndarray:
    """La foto como uint8 HxWx3. Nunca modifica la entrada (copia si convierte)."""
    a = np.asarray(rgb)
    if a.ndim == 2:
        a = np.repeat(a[..., None], 3, axis=2)
    elif a.ndim == 3 and a.shape[2] == 1:
        a = np.repeat(a, 3, axis=2)
    elif a.ndim == 3 and a.shape[2] > 3:
        a = np.ascontiguousarray(a[..., :3])
    if a.ndim != 3 or a.shape[2] != 3:
        raise ValueError(f"se esperaba una imagen HxWx3, llegó {np.asarray(rgb).shape}")
    if a.dtype == np.uint8:
        return a
    if a.dtype == np.uint16:
        return (a // 257).astype(np.uint8)
    return (np.clip(a.astype(np.float32), 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def _tam_reducido(h: int, w: int, lado_max: int) -> tuple[int, int]:
    lado = max(h, w)
    if lado <= lado_max:
        return h, w
    f = lado_max / lado
    return max(1, round(h * f)), max(1, round(w * f))


def _reducir(img: np.ndarray, lado_max: int) -> np.ndarray:
    h, w = img.shape[:2]
    hr, wr = _tam_reducido(h, w, lado_max)
    if (hr, wr) == (h, w):
        return np.ascontiguousarray(img)
    return cv2.resize(img, (wr, hr), interpolation=cv2.INTER_AREA)


def _escala(img: np.ndarray, referencia: int = LADO_TRABAJO) -> float:
    """Escala de los radios: 1 a lado largo ``referencia``; menos si la foto es chica."""
    return max(img.shape[:2]) / float(referencia)


def _radio(k: float, s: float, minimo: int = 1) -> int:
    return max(minimo, int(round(k * s)))


def _elipse(r: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def _componentes(binaria: np.ndarray) -> tuple[int, np.ndarray, np.ndarray]:
    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats(binaria.astype(np.uint8), connectivity=8)
    return n, etiquetas, stats


def _quitar_chicos(binaria: np.ndarray, area_min: float) -> np.ndarray:
    """Saca los componentes conexos de menos de ``area_min`` píxeles."""
    n, etiquetas, stats = _componentes(binaria)
    if n <= 1:
        return binaria.astype(np.uint8)
    quedan = stats[:, cv2.CC_STAT_AREA] >= area_min
    quedan[0] = False
    return quedan[etiquetas].astype(np.uint8)


def _toca_borde(stats: np.ndarray, h: int, w: int) -> np.ndarray:
    izq, arr = stats[:, cv2.CC_STAT_LEFT], stats[:, cv2.CC_STAT_TOP]
    der = izq + stats[:, cv2.CC_STAT_WIDTH]
    aba = arr + stats[:, cv2.CC_STAT_HEIGHT]
    return (izq <= 0) | (arr <= 0) | (der >= w) | (aba >= h)


def _rellenar_huecos(binaria: np.ndarray, area_max: float, apto: np.ndarray | None = None,
                     apto_min: float = 0.3) -> np.ndarray:
    """Rellena los huecos encerrados (no tocan el borde) de menos de ``area_max`` px.

    ``apto`` (opcional, 0..1): solo se rellenan los huecos cuyo promedio supere
    ``apto_min`` (o los diminutos, que son ruido).
    """
    h, w = binaria.shape
    n, etiquetas, stats = _componentes(binaria == 0)
    if n <= 1:
        return binaria.astype(np.uint8)
    rellenar = (stats[:, cv2.CC_STAT_AREA] <= area_max) & ~_toca_borde(stats, h, w)
    rellenar[0] = False
    if apto is not None and rellenar.any():
        suma = np.bincount(etiquetas.ravel(), weights=apto.ravel(), minlength=n)
        media = suma / np.maximum(stats[:, cv2.CC_STAT_AREA], 1)
        diminuto = stats[:, cv2.CC_STAT_AREA] <= max(4.0, area_max * 0.05)
        rellenar &= (media > apto_min) | diminuto
    return (binaria.astype(bool) | rellenar[etiquetas]).astype(np.uint8)


def _coeficientes_guiado_color(guia: np.ndarray, p: np.ndarray, r: int,
                               eps: float) -> tuple[np.ndarray, np.ndarray]:
    """Filtro guiado con guía en color (He et al., 2013, ec. 14-15).

    ``guia`` float32 HxWx3 en [0, 1], ``p`` float32 HxW. Devuelve los
    coeficientes ya promediados (a: HxWx3, b: HxW) para q = a·I + b. Con guía
    en color el borde se pega aunque objeto y fondo tengan la misma luminancia.
    """
    media = caja(guia, r)
    mp = caja(p, r)
    cov = caja(guia * p[..., None], r) - media * mp[..., None]
    diag = caja(guia * guia, r) - media * media + eps
    cruz_g = np.stack([guia[..., 0] * guia[..., 1], guia[..., 0] * guia[..., 2],
                       guia[..., 1] * guia[..., 2]], axis=2)
    cruz = caja(cruz_g, r) - np.stack([media[..., 0] * media[..., 1], media[..., 0] * media[..., 2],
                                       media[..., 1] * media[..., 2]], axis=2)
    rr, gg, bb = diag[..., 0], diag[..., 1], diag[..., 2]
    rg, rb, gb = cruz[..., 0], cruz[..., 1], cruz[..., 2]
    # Inversa de la covarianza 3x3 simétrica por cofactores (vectorizada).
    i_rr = gg * bb - gb * gb
    i_rg = gb * rb - rg * bb
    i_rb = rg * gb - gg * rb
    i_gg = rr * bb - rb * rb
    i_gb = rb * rg - rr * gb
    i_bb = rr * gg - rg * rg
    det = rr * i_rr + rg * i_rg + rb * i_rb
    det = np.where(np.abs(det) < 1e-12, 1e-12, det)
    c0, c1, c2 = cov[..., 0], cov[..., 1], cov[..., 2]
    a = np.stack([(i_rr * c0 + i_rg * c1 + i_rb * c2) / det,
                  (i_rg * c0 + i_gg * c1 + i_gb * c2) / det,
                  (i_rb * c0 + i_gb * c1 + i_bb * c2) / det], axis=2).astype(np.float32)
    b = (mp - (a * media).sum(axis=2)).astype(np.float32)
    return caja(a, r), caja(b, r)


def _aplicar_coeficientes(a: np.ndarray, b: np.ndarray, rgb8: np.ndarray) -> np.ndarray:
    """q = a·I + b sobre la foto ``rgb8`` (uint8, cualquier tamaño): filtro guiado rápido.

    Los coeficientes se amplían bilinealmente; la guía es la foto a resolución
    completa, por eso el borde queda nítido aunque a, b vengan reducidos.
    """
    h, w = rgb8.shape[:2]
    planos = cv2.split(np.ascontiguousarray(rgb8))
    misma = a.shape[:2] == (h, w)
    q = b.copy() if misma else cv2.resize(b, (w, h), interpolation=cv2.INTER_LINEAR)
    for c in range(3):
        ac = np.ascontiguousarray(a[..., c]) * np.float32(1.0 / 255.0)
        if not misma:
            ac = cv2.resize(ac, (w, h), interpolation=cv2.INTER_LINEAR)
        q += cv2.multiply(ac, planos[c].astype(np.float32))
    return q


def _limpiar(q: np.ndarray, t: float = 0.02) -> np.ndarray:
    """Recorta los restos mínimos del filtro guiado: lo que era 0 queda en 0 y lo que era 1 en 1."""
    q -= t
    q *= 1.0 / (1.0 - 2.0 * t)
    np.clip(q, 0.0, 1.0, out=q)
    return q.astype(np.float32, copy=False)


def _refinar(m0: np.ndarray, guia_chica: np.ndarray, rgb8: np.ndarray, r: int, eps: float) -> np.ndarray:
    """Refina ``m0`` (reducida) con la guía reducida y la lleva al tamaño de ``rgb8``."""
    f = guia_chica.astype(np.float32) * np.float32(1.0 / 255.0)
    a, b = _coeficientes_guiado_color(f, m0.astype(np.float32), r, eps)
    return _limpiar(_aplicar_coeficientes(a, b, rgb8))


# ---------------------------------------------------------------------------
# Cielo
# ---------------------------------------------------------------------------

def _probabilidad_cielo(f: np.ndarray, s: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Mapas por píxel (0..1) a resolución de trabajo.

    Devuelve (lab, p_color, estricta, suelta):
      * ``p_color``: solo el color (azul de cielo, o gris claro sin croma).
      * ``estricta``: color × lisura × gradiente MUY suave: núcleo seguro de cielo.
      * ``suelta``: color × lisura × sin bordes NETOS: deja pasar el borde difuso
        de las nubes, pero no el corte nítido de una pared o un techo.
    """
    lab = cv2.cvtColor(f, cv2.COLOR_RGB2Lab)  # L 0..100; a, b ≈ ±127
    L, A, B = lab[..., 0], lab[..., 1], lab[..., 2]
    croma = np.hypot(A, B)
    tono = np.degrees(np.arctan2(B, A))  # azul de cielo: ≈ -140°..-55°
    banda_azul = suavestep(-155.0, -138.0, tono) * (1.0 - suavestep(-62.0, -45.0, tono))
    p_azul = banda_azul * suavestep(4.0, 10.0, croma) * suavestep(25.0, 40.0, L)
    # Nublado / blanco: casi sin color, claro y entre lo más luminoso de la foto.
    mediana = float(np.median(L))
    p_nublado = ((1.0 - suavestep(7.0, 15.0, croma)) * suavestep(50.0, 66.0, L)
                 * suavestep(-14.0, -4.0, L - mediana))
    p_color = np.maximum(p_azul, p_nublado).astype(np.float32)

    # Textura fina: el cielo es liso (solo ruido o compresión).
    y = luma(f)
    fino = y - gauss(y, max(0.8, 1.5 * s))
    energia = desvio_local(fino, _radio(3, s))
    p_lisa = 1.0 - suavestep(0.006, 0.02, energia)

    # Gradiente a escala media (por píxel de 1024): el cielo cambia despacio. Se
    # tolera más el cambio vertical (se aclara hacia el horizonte) que el horizontal.
    ys = gauss(y, max(1.0, 2.0 * s))
    gx = cv2.Sobel(ys, cv2.CV_32F, 1, 0, ksize=3) / 8.0
    gy = cv2.Sobel(ys, cv2.CV_32F, 0, 1, ksize=3) / 8.0
    g = np.sqrt(gx * gx + 0.25 * gy * gy) * (1.0 / max(s, 1e-3))
    base = p_color * p_lisa
    estricta = base * (1.0 - suavestep(0.008, 0.025, g))
    suelta = base * (1.0 - suavestep(0.05, 0.09, g))
    return lab, p_color, estricta.astype(np.float32), suelta.astype(np.float32)


def _crecer_por_color(region: np.ndarray, f: np.ndarray, s: float, pasos: int = 4,
                      umbral: float = 0.05) -> np.ndarray:
    """Devuelve a ``region`` el anillo que le sacaron las medidas por ventana.

    La lisura y el gradiente se miden en ventanas, así que cerca de un contorno
    fuerte el cielo queda unos píxeles corto. Se lo hace crecer de a poco
    (dilatación geodésica) solo sobre píxeles cuyo color está a menos de
    ``umbral`` (RGB 0..1) del color LOCAL del cielo: el borde queda en el
    contorno real y no cruza a edificios ni árboles.
    """
    peso = region.astype(np.float32)
    sigma = max(2.0, 12.0 * s)
    den = gauss(peso, sigma)
    color_local = gauss(f * peso[..., None], sigma) / np.maximum(den, 1e-4)[..., None]
    distancia = np.sqrt(((f - color_local) ** 2).sum(axis=2))
    acepta = ((distancia < umbral) & (den > 0.02)).astype(np.uint8)
    paso = _elipse(_radio(2, s))
    out = region.astype(np.uint8)
    for _ in range(pasos):
        nuevo = cv2.dilate(out, paso) & acepta
        nuevo |= out
        if np.array_equal(nuevo, out):
            break
        out = nuevo
    return out


def _huecos_con_color_de_cielo(cielo: np.ndarray, etiquetas: np.ndarray, stats: np.ndarray,
                               candidatos: np.ndarray, lab: np.ndarray, s: float,
                               delta_e_max: float = 12.0) -> np.ndarray:
    """Qué componentes ``candidatos`` (que no tocan arriba) son cielo visto entre ramas.

    Se aceptan solo si a SU MISMA ALTURA hay cielo principal y su color medio
    (Lab) está a menos de ``delta_e_max`` del color de ese cielo en esas filas.
    Un objeto azul más abajo del cielo (auto, ropa, pileta) no tiene cielo en
    sus filas y queda afuera. Devuelve un vector booleano por etiqueta.
    """
    n = stats.shape[0]
    acepta = np.zeros(n, bool)
    idx = np.flatnonzero(candidatos)
    if idx.size == 0:
        return acepta
    peso = cielo.astype(np.float32)
    suma_filas = np.concatenate([np.zeros((1, 3), np.float64),
                                 np.cumsum((lab * peso[..., None]).sum(axis=1), axis=0, dtype=np.float64)])
    cuenta_filas = np.concatenate([[0.0], np.cumsum(peso.sum(axis=1), dtype=np.float64)])
    plano = etiquetas.ravel()
    area = np.maximum(stats[:, cv2.CC_STAT_AREA], 1).astype(np.float64)
    medias = np.stack([np.bincount(plano, weights=lab[..., c].ravel(), minlength=n) / area
                       for c in range(3)], axis=1)
    minimo_cielo = max(20.0, 200.0 * s * s)
    for i in idx:
        arriba = int(stats[i, cv2.CC_STAT_TOP])
        abajo = arriba + int(stats[i, cv2.CC_STAT_HEIGHT])
        cuenta = cuenta_filas[abajo] - cuenta_filas[arriba]
        if cuenta < minimo_cielo:
            continue
        referencia = (suma_filas[abajo] - suma_filas[arriba]) / cuenta
        acepta[i] = float(np.linalg.norm(medias[i] - referencia)) < delta_e_max
    return acepta


def mascara_cielo(rgb: np.ndarray) -> np.ndarray:
    """Máscara del cielo (azul, nublado o blanco), float32 HxW en [0, 1].

    Técnica (a lado largo ≤ 1024):
      * Probabilidad de "cielo" = color (Lab: tono azul con algo de croma, o gris
        claro sin croma y entre lo más luminoso de la foto) × lisura (desvío
        local del detalle fino bajo) × gradiente suave a escala media (se tolera
        el degradé vertical hacia el horizonte). Con histéresis: un núcleo
        estricto (gradiente muy suave) y una zona suelta que también acepta el
        borde difuso de las nubes pero no un corte nítido (pared, techo).
      * Componentes conexos de la zona suelta: el cielo principal son los que
        TOCAN EL BORDE SUPERIOR y contienen núcleo. Un objeto azul que no llega
        arriba no es cielo. Excepción: el cielo visto entre ramas (componentes
        sueltos con el mismo color que el cielo principal EN SUS MISMAS FILAS).
      * Crecimiento geodésico por color local (recupera el anillo que las
        medidas por ventana le sacan junto a los contornos) y relleno de huecos
        encerrados con color de cielo (nubes con textura, ruido). Cielos de
        menos del 0,5 % de la foto se descartan.
      * Borde: filtro guiado en color + ampliación guiada a resolución completa
        (siluetas de edificios y árboles quedan pegadas al contorno real).

    Si no hay cielo devuelve una máscara de ceros. Dónde falla: cielos de
    atardecer anaranjados o de noche (el color no entra en el modelo), paredes
    o techos blancos/celestes lisos que tocan el borde superior (parecen cielo
    nublado), montañas lejanas azuladas pegadas al cielo, nubes muy texturadas
    que tocan el horizonte y huecos de cielo de pocos píxeles entre hojas
    densas (quedan parciales). Costo: ver el docstring del módulo.
    """
    rgb8 = _rgb_uint8(rgb)
    h, w = rgb8.shape[:2]
    chica = _reducir(rgb8, LADO_TRABAJO)
    hc, wc = chica.shape[:2]
    s = _escala(chica)
    f = chica.astype(np.float32) * np.float32(1.0 / 255.0)
    area_total = float(hc * wc)

    lab, p_color, estricta, suelta = _probabilidad_cielo(f, s)
    abrir = _elipse(_radio(2, s))
    nucleo = cv2.morphologyEx((estricta > 0.4).astype(np.uint8), cv2.MORPH_OPEN, abrir)
    zona = cv2.morphologyEx((suelta > 0.4).astype(np.uint8), cv2.MORPH_OPEN, abrir) | nucleo
    n, etiquetas, stats = _componentes(zona)
    if n <= 1:
        return np.zeros((h, w), np.float32)
    con_nucleo = np.zeros(n, bool)
    con_nucleo[np.unique(etiquetas[nucleo > 0])] = True
    area = stats[:, cv2.CC_STAT_AREA]
    arriba = stats[:, cv2.CC_STAT_TOP] <= _radio(2, s, minimo=0)
    principal = con_nucleo & arriba & (area >= 0.002 * area_total)
    principal[0] = False
    cielo = principal[etiquetas].astype(np.uint8)
    if cielo.sum() < 0.005 * area_total:
        return np.zeros((h, w), np.float32)

    sueltos = ~principal & ~arriba & (area >= max(12.0, 0.0001 * area_total))
    sueltos[0] = False
    entre_ramas = _huecos_con_color_de_cielo(cielo, etiquetas, stats, sueltos, lab, s)
    if entre_ramas.any():
        cielo |= entre_ramas[etiquetas].astype(np.uint8)

    cielo = _crecer_por_color(cielo, f, s)
    # Huecos encerrados: chicos con algo de color de cielo (ruido, nubes con
    # textura) o medianos con mucho color de cielo (nubes grandes).
    cielo = _rellenar_huecos(cielo, 0.003 * area_total, apto=p_color, apto_min=0.3)
    cielo = _rellenar_huecos(cielo, 0.03 * area_total, apto=p_color, apto_min=0.6)
    return _refinar(cielo.astype(np.float32), chica, rgb8, _radio(6, s, minimo=2), 1e-3)


# ---------------------------------------------------------------------------
# Piel
# ---------------------------------------------------------------------------

def _probabilidad_piel(f: np.ndarray) -> np.ndarray:
    """Probabilidad de piel por color (0..1): YCrCb Y HSV tienen que coincidir."""
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    yy = 0.299 * r + 0.587 * g + 0.114 * b
    cr = (r - yy) * 0.713 + 0.5
    cb = (b - yy) * 0.564 + 0.5
    # Mismos rangos ampliados que mascaras.calcular_regiones (Cr ≈ 129..181, Cb ≈ 71..135).
    p_ycc = (suavestep(0.505, 0.53, cr) * (1.0 - suavestep(0.68, 0.71, cr))
             * suavestep(0.28, 0.31, cb) * (1.0 - suavestep(0.50, 0.53, cb)))
    hsv = cv2.cvtColor(f, cv2.COLOR_RGB2HSV)  # H 0..360, S y V 0..1
    tono = hsv[..., 0]
    tono = np.where(tono > 180.0, tono - 360.0, tono)  # -180..180: rojo en 0
    p_tono = suavestep(-28.0, -10.0, tono) * (1.0 - suavestep(42.0, 58.0, tono))
    sat = hsv[..., 1]
    p_sat = suavestep(0.08, 0.16, sat) * (1.0 - suavestep(0.70, 0.82, sat))
    p_luz = suavestep(0.06, 0.16, yy) * (1.0 - suavestep(0.95, 0.995, yy))
    return (p_ycc * p_tono * p_sat * p_luz).astype(np.float32)


def mascara_piel(rgb: np.ndarray) -> np.ndarray:
    """Máscara de piel humana, float32 HxW en [0, 1].

    Técnica (a lado largo ≤ 1024):
      * Color: los rangos de YCrCb de ``mascaras.calcular_regiones`` combinados
        (producto) con HSV (tono entre rojo y amarillo, saturación media) y
        límites de luminancia. Pedir que los dos espacios coincidan saca la
        mayoría de los falsos positivos de un solo espacio (naranjas saturados,
        grises cálidos).
      * Limpieza: umbral 0,5, apertura (puntos sueltos) y cierre (poros, ruido),
        y fuera los componentes de menos del 0,05 % de la foto.
      * Borde: alrededor de la piel detectada se conserva la probabilidad suave;
        luego filtro guiado en color + ampliación guiada a resolución completa.

    Dónde falla: madera, arena, cuero, cartón o paredes de tono piel también
    se marcan (no hay detección de caras); con luz muy coloreada (tungsteno
    fuerte, neón, atardecer) o en sombras muy profundas la piel puede quedar
    afuera; pelo rubio/pelirrojo y labios a veces entran parcialmente.
    Costo: ver el docstring del módulo.
    """
    rgb8 = _rgb_uint8(rgb)
    h, w = rgb8.shape[:2]
    chica = _reducir(rgb8, LADO_TRABAJO)
    hc, wc = chica.shape[:2]
    s = _escala(chica)
    f = chica.astype(np.float32) * np.float32(1.0 / 255.0)

    p = _probabilidad_piel(f)
    binaria = (p > 0.5).astype(np.uint8)
    binaria = cv2.morphologyEx(binaria, cv2.MORPH_OPEN, _elipse(_radio(2, s)))
    binaria = cv2.morphologyEx(binaria, cv2.MORPH_CLOSE, _elipse(_radio(3, s)))
    binaria = _quitar_chicos(binaria, max(9.0, 0.0005 * hc * wc))
    if not binaria.any():
        return np.zeros((h, w), np.float32)
    cerca = cv2.dilate(binaria, _elipse(_radio(3, s)))
    m0 = np.maximum(binaria.astype(np.float32), p * cerca)
    return _refinar(m0, chica, rgb8, _radio(4, s, minimo=2), 1e-3)


# ---------------------------------------------------------------------------
# Recorte inteligente (GrabCut)
# ---------------------------------------------------------------------------

_COMPONENTES_GMM = 5  # fijo en la implementación de GrabCut de OpenCV (modelo de 65 = 5·(1+3+9))


def _depurar_modelo_objeto(modelo_objeto: np.ndarray, modelo_fondo: np.ndarray,
                           peso_max: float = 0.05, distancia2_max: float = 9.0) -> bool:
    """Saca del GMM del objeto las componentes CHICAS cuyo color es de fondo.

    Con un rectángulo holgado, el modelo del objeto aprende también algunos
    colores del fondo que quedaron adentro (con poco peso) y GrabCut pega
    astillas de fondo al sujeto. Una componente del objeto con menos de
    ``peso_max`` del peso y cuya media cae a menos de 3 desvíos (Mahalanobis)
    de alguna componente del fondo se anula. Los detalles chicos del sujeto con
    colores que el fondo no tiene se conservan. Devuelve True si cambió algo.
    """
    k = _COMPONENTES_GMM
    pesos_o = modelo_objeto[0, :k]
    medias_o = modelo_objeto[0, k:4 * k].reshape(k, 3)
    pesos_f = modelo_fondo[0, :k]
    medias_f = modelo_fondo[0, k:4 * k].reshape(k, 3)
    cov_f = modelo_fondo[0, 4 * k:13 * k].reshape(k, 3, 3)
    cambio = False
    for i in range(k):
        if not 0.0 < pesos_o[i] < peso_max:
            continue
        for j in range(k):
            if pesos_f[j] <= 0.0:
                continue
            d = medias_o[i] - medias_f[j]
            try:
                d2 = float(d @ np.linalg.solve(cov_f[j], d))
            except np.linalg.LinAlgError:
                continue
            if d2 < distancia2_max:
                pesos_o[i] = 0.0
                cambio = True
                break
    if cambio:
        pesos_o /= max(float(pesos_o.sum()), 1e-12)
    return cambio


def _limpiar_objeto(objeto: np.ndarray, s: float) -> np.ndarray:
    """Saca islas de fondo y tapa agujeritos del resultado de GrabCut.

    Una apertura separa los pedazos de fondo pegados al sujeto por una esquina
    o un cuello fino. Los bloques chicos que quedan sueltos tras la apertura
    (< 5 % del mayor) se borran, salvo cerca del cuerpo principal. Las
    estructuras finas del sujeto (dedos, patas, antenas) desaparecen en la
    apertura sin formar bloque propio, así que NO se borran. Después: fuera las
    islas desconectadas (< 2 % del mayor) y se rellenan los huecos diminutos.
    """
    r = _radio(3, s)
    elipse = _elipse(r + 1)
    abierto = cv2.morphologyEx(objeto, cv2.MORPH_OPEN, _elipse(r))
    n, etiquetas, stats = _componentes(abierto)
    if n > 2:
        areas = stats[:, cv2.CC_STAT_AREA]
        chico = areas < 0.05 * float(areas[1:].max())
        chico[0] = False
        if chico.any():
            grande = ~chico
            grande[0] = False
            borrar = cv2.dilate(chico[etiquetas].astype(np.uint8), elipse)
            proteger = cv2.dilate(grande[etiquetas].astype(np.uint8), elipse)
            objeto = objeto & ~(borrar & ~proteger)
    n, _, stats = _componentes(objeto)
    if n > 2:
        objeto = _quitar_chicos(objeto, max(4.0, 0.02 * float(stats[1:, cv2.CC_STAT_AREA].max())))
    if not objeto.any():
        return objeto
    return _rellenar_huecos(objeto, max(4.0, 0.002 * float(objeto.sum())))


def _es_rectangulo(inicial) -> bool:
    if isinstance(inicial, np.ndarray):
        return inicial.ndim == 1 and inicial.size == 4
    return isinstance(inicial, (tuple, list)) and len(inicial) == 4 and np.ndim(inicial) == 1


def _region_de_interes(x0: float, y0: float, x1: float, y1: float, margen: float,
                       h: int, w: int) -> tuple[int, int, int, int]:
    """Caja (en píxeles completos) agrandada en ``margen`` (fracción del tamaño de la caja)."""
    mx = max((x1 - x0) * margen, 0.02)
    my = max((y1 - y0) * margen, 0.02)
    ax0 = int(np.floor(max(0.0, x0 - mx) * w))
    ay0 = int(np.floor(max(0.0, y0 - my) * h))
    ax1 = int(np.ceil(min(1.0, x1 + mx) * w))
    ay1 = int(np.ceil(min(1.0, y1 + my) * h))
    return ax0, ay0, max(ax1, ax0 + 1), max(ay1, ay0 + 1)


def recortar_objeto(rgb: np.ndarray, inicial: Sequence[float] | np.ndarray,
                    iteraciones: int = 5) -> np.ndarray:
    """Recorte inteligente del sujeto con GrabCut. Devuelve float32 HxW en [0, 1].

    ``inicial`` puede ser:
      * un rectángulo aproximado ``(x0, y0, x1, y1)`` normalizado (0..1): afuera
        es fondo seguro, adentro "probable objeto";
      * una máscara aproximada HxW (cualquier resolución, bool/uint8/float; por
        ejemplo un lazo dibujado a mano): adentro = probable objeto, una banda
        alrededor del contorno = indecisa (puede pasar a objeto o a fondo),
        lejos afuera = fondo seguro.

    Técnica:
      * Solo se procesa la región de interés (la caja más un margen, que da el
        modelo de color del fondo cercano), reducida a lado largo ≤ 640 px.
      * ``cv2.grabCut`` (GMM de color de objeto y fondo + corte mínimo en grafo),
        ``iteraciones`` vueltas, semilla fija (resultado repetible). Después se
        depura el GMM del objeto (componentes chicas con color de fondo) y se
        corre una vuelta más con el modelo congelado.
      * Limpieza: apertura + descarte de bloques sueltos (pedazos de fondo
        pegados por una esquina), islas chicas y huecos diminutos; las
        estructuras finas del sujeto se conservan.
      * Borde: filtro guiado en color a la resolución de GrabCut y ampliación
        guiada sobre la región a resolución COMPLETA (filtro guiado rápido): el
        contorno se pega a los bordes reales de la foto de 12 MP.

    Si GrabCut no puede correr (región diminuta) se devuelve la selección
    inicial refinada. Rectángulo vacío o máscara vacía → máscara de ceros.

    Dónde falla: sujeto y fondo con los mismos colores (camuflaje, ropa del
    color de la pared), fondo que entra al rectángulo y no aparece afuera,
    pelo suelto o pelaje (el borde guiado es suave pero no un "matting" real),
    objetos transparentes o muy finos de menos de ~1 px a la resolución de
    GrabCut. Costo: ver el docstring del módulo (objetivo < 2 s a 12 MP).
    """
    rgb8 = _rgb_uint8(rgb)
    h, w = rgb8.shape[:2]
    vacia = np.zeros((h, w), np.float32)

    if _es_rectangulo(inicial):
        rx0, ry0, rx1, ry1 = (float(v) for v in inicial)
        rx0, rx1 = sorted((min(max(rx0, 0.0), 1.0), min(max(rx1, 0.0), 1.0)))
        ry0, ry1 = sorted((min(max(ry0, 0.0), 1.0), min(max(ry1, 0.0), 1.0)))
        if rx1 - rx0 <= 0.0 or ry1 - ry0 <= 0.0:
            return vacia
        mascara = None
        margen = 0.12
    else:
        mascara = np.asarray(inicial)
        if mascara.ndim != 2:
            raise ValueError("la máscara inicial tiene que ser HxW")
        mascara = mascara.astype(np.float32)
        if mascara.max() > 1.0:
            mascara = mascara / 255.0
        bx, by, bw, bh = cv2.boundingRect((mascara >= 0.5).astype(np.uint8))
        if bw == 0 or bh == 0:
            return vacia
        mh, mw = mascara.shape
        rx0, rx1 = bx / mw, (bx + bw) / mw
        ry0, ry1 = by / mh, (by + bh) / mh
        margen = 0.20  # incluye la banda indecisa más el fondo cercano

    ax0, ay0, ax1, ay1 = _region_de_interes(rx0, ry0, rx1, ry1, margen, h, w)
    region = rgb8[ay0:ay1, ax0:ax1]
    chica = _reducir(region, LADO_GRABCUT)
    hc, wc = chica.shape[:2]
    s = _escala(chica, LADO_GRABCUT)

    # Etiquetas iniciales en coordenadas de la región reducida.
    def a_chica_x(x: float) -> float:
        return (x * w - ax0) / (ax1 - ax0) * wc

    def a_chica_y(y: float) -> float:
        return (y * h - ay0) / (ay1 - ay0) * hc

    etiquetas = np.full((hc, wc), _FONDO, np.uint8)
    if mascara is None:
        cx0, cx1 = int(np.floor(a_chica_x(rx0))), int(np.ceil(a_chica_x(rx1)))
        cy0, cy1 = int(np.floor(a_chica_y(ry0))), int(np.ceil(a_chica_y(ry1)))
        etiquetas[max(cy0, 0):min(cy1, hc), max(cx0, 0):min(cx1, wc)] = _PR_OBJETO
    else:
        mh, mw = mascara.shape
        # Recorte de la máscara a la región (en sus propias coordenadas) y a la resolución reducida.
        mx0, mx1 = ax0 / w * mw, ax1 / w * mw
        my0, my1 = ay0 / h * mh, ay1 / h * mh
        escala_x, escala_y = (mx1 - mx0) / wc, (my1 - my0) / hc
        mapa = np.array([[escala_x, 0.0, mx0 + 0.5 * escala_x - 0.5],
                         [0.0, escala_y, my0 + 0.5 * escala_y - 0.5]], np.float32)
        aprox = cv2.warpAffine(mascara, mapa, (wc, hc), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=0.0)
        adentro = (aprox >= 0.5).astype(np.uint8)
        if not adentro.any():
            return vacia
        banda = max(3, int(round(0.10 * np.sqrt(float(adentro.sum())))))
        cerca = cv2.dilate(adentro, _elipse(banda))
        etiquetas[cerca > 0] = _PR_FONDO
        etiquetas[adentro > 0] = _PR_OBJETO

    # Hace falta algo de fondo para el modelo de color: si el rectángulo cubre
    # toda la foto, un marco fino pasa a fondo (arriba y a los costados) y a
    # "probable fondo" abajo, donde los sujetos suelen cortarse con el encuadre.
    if not np.any((etiquetas == _FONDO) | (etiquetas == _PR_FONDO)):
        marco = max(2, int(round(0.03 * max(hc, wc))))
        etiquetas[-marco:, :] = _PR_FONDO
        etiquetas[:marco, :] = _FONDO
        etiquetas[:, :marco] = _FONDO
        etiquetas[:, -marco:] = _FONDO
    if not np.any((etiquetas == _OBJETO) | (etiquetas == _PR_OBJETO)):
        return vacia

    iniciales = etiquetas.copy()
    modelo_fondo = np.zeros((1, 65), np.float64)
    modelo_objeto = np.zeros((1, 65), np.float64)
    cv2.setRNGSeed(_SEMILLA_GRABCUT)  # RNG de OpenCV (por hilo): solo afecta a este cálculo
    try:
        cv2.grabCut(chica, etiquetas, None, modelo_fondo, modelo_objeto,
                    max(1, int(iteraciones)), cv2.GC_INIT_WITH_MASK)
        # Una vuelta más con el modelo del objeto depurado y congelado.
        if _depurar_modelo_objeto(modelo_objeto, modelo_fondo):
            cv2.grabCut(chica, etiquetas, None, modelo_fondo, modelo_objeto, 1,
                        cv2.GC_EVAL_FREEZE_MODEL)
    except cv2.error:
        # Región diminuta o sin muestras para algún modelo de color: se devuelve
        # la selección inicial (refinada) en vez de nada.
        etiquetas = iniciales
    objeto = ((etiquetas == _OBJETO) | (etiquetas == _PR_OBJETO)).astype(np.uint8)
    if not objeto.any():
        return vacia

    objeto = _limpiar_objeto(objeto, s)

    refinada = _refinar(objeto.astype(np.float32), chica, region, _radio(4, s, minimo=2), 1e-4)
    vacia[ay0:ay1, ax0:ax1] = refinada
    return vacia


# ---------------------------------------------------------------------------
# Guardado compacto en el historial
# ---------------------------------------------------------------------------

def codificar_mascara(m: np.ndarray) -> bytes:
    """Máscara float 0..1 → PNG gris de 8 bits a lado largo ≤ 1024 (bytes).

    Determinista: la misma máscara da siempre los mismos bytes, así el
    historial puede comparar estados por igualdad. Una máscara de 12 MP ocupa
    típicamente unos pocos KB (los bordes suaves comprimen bien).
    """
    m = np.asarray(m, dtype=np.float32)
    if m.ndim != 2:
        raise ValueError("la máscara tiene que ser HxW")
    chica = _reducir(np.clip(m, 0.0, 1.0), LADO_GUARDADO)
    u8 = (chica * 255.0 + 0.5).astype(np.uint8)
    ok, datos = cv2.imencode(".png", u8, [cv2.IMWRITE_PNG_COMPRESSION, 6])
    if not ok:
        raise ValueError("no se pudo codificar la máscara")
    return datos.tobytes()


def decodificar_mascara(datos: bytes, h: int, w: int) -> np.ndarray:
    """Bytes de ``codificar_mascara`` → float32 HxW en [0, 1] (interpolación lineal)."""
    u8 = cv2.imdecode(np.frombuffer(datos, np.uint8), cv2.IMREAD_GRAYSCALE)
    if u8 is None:
        raise ValueError("datos de máscara inválidos")
    m = u8.astype(np.float32) * np.float32(1.0 / 255.0)
    if m.shape != (h, w):
        m = cv2.resize(m, (int(w), int(h)), interpolation=cv2.INTER_LINEAR)
    return m
