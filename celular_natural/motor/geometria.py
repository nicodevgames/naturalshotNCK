"""Rotar, voltear y enderezar la foto (no destructivo, sin interfaz).

Orden de las operaciones, siempre el mismo:

1. **Voltear** la foto original: espejo izquierda-derecha (``voltear_h``) y/o
   arriba-abajo (``voltear_v``). Exacto: solo reordena píxeles.
2. **Girar** de a cuartos de vuelta en sentido horario (``giro90``). Exacto.
3. **Enderezar**: rotación fina alrededor del centro (``enderezar`` en grados,
   **positivo = horario**, como se ve en pantalla), con interpolación de calidad
   (Lanczos por defecto).

   * Con ``recortar_bordes`` (por defecto) el resultado es el mayor rectángulo
     con la misma proporción que entra entero dentro de la foto girada: no queda
     ninguna esquina vacía. El tamaño baja un poco (≈7 % de lado a 4°).
   * Sin recorte la foto conserva su tamaño y las esquinas que quedan afuera se
     rellenan con un **reflejo** de la propia foto (``borde="reflejo"``, no se
     nota un triángulo de color) o con **0** (``borde="transparente"``). Para
     dejarlas transparentes se pasa el canal alfa (o uno lleno de 255) por
     ``aplicar_geometria`` con ``borde="transparente"``.

Coordenadas: continuas, con el centro del píxel (fila i, columna j) en
(j + 0,5, i + 0,5), igual que en ``zonas``; las normalizadas (0..1) salen de
dividir por el ancho y el alto. Las zonas se guardan normalizadas respecto de la
foto ORIGINAL: ``transformar_puntos`` las lleva al resultado y
``destransformar_puntos`` las trae de vuelta (por ejemplo, un clic sobre la vista
girada). Las dos usan exactamente la misma matriz que ``aplicar_geometria``, así
que un punto marcado en la original cae en el mismo píxel del resultado.

Ojo: el recorte del enderezado se redondea a píxeles enteros en cada tamaño, así
que entre la vista previa reducida y la exportación las coordenadas normalizadas
del resultado pueden diferir en menos de un píxel de cada una.

Costo a 12 MP (medido con 16 hilos de OpenCV): girar 90° + voltear ≈ 50 ms;
enderezar ≈ 90 ms con Lanczos (≈ 20 ms con cúbica; un alfa, ≈ 35 ms).
``detectar_horizonte`` trabaja sobre una versión reducida (lado largo 1024 px):
≈ 10-40 ms.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Optional

import cv2
import numpy as np

ENDEREZAR_MINIMO = 1e-3  # grados: por debajo se toma como 0 (a 12 MP mueve < 0,04 px)
LIMITE_HORIZONTE = 15.0  # grados: ``detectar_horizonte`` nunca propone más que esto
BORDES = ("reflejo", "transparente")

# Detección del horizonte (sobre la versión reducida).
LADO_DETECCION = 1024
PESO_VERTICALES = 0.5  # las verticales también sirven, pero la perspectiva las tuerce
TOLERANCIA_HORIZONTE = 1.0  # grados: líneas que "votan" lo mismo que la mediana
APOYO_MINIMO = 0.35  # largo total de esas líneas, en lados largos de la imagen
FRACCION_MINIMA = 0.3  # parte del peso total que tiene que estar de acuerdo


@dataclass(frozen=True)
class Geometria:
    giro90: int = 0  # cuartos de vuelta en sentido horario (0..3)
    voltear_h: bool = False  # espejo izquierda-derecha de la original
    voltear_v: bool = False  # espejo arriba-abajo de la original
    enderezar: float = 0.0  # grados, rango sugerido -15..15; positivo = horario
    recortar_bordes: bool = True  # al enderezar, recortar las esquinas vacías

    def normalizada(self) -> "Geometria":
        """Forma canónica: giro en 0..3, los dos volteos juntos pasan a media vuelta
        (es lo mismo) y un enderezado despreciable queda en 0."""
        giro = int(self.giro90) % 4
        voltear_h, voltear_v = bool(self.voltear_h), bool(self.voltear_v)
        if voltear_h and voltear_v:
            voltear_h = voltear_v = False
            giro = (giro + 2) % 4
        angulo = float(self.enderezar)
        if not math.isfinite(angulo) or abs(angulo) < ENDEREZAR_MINIMO:
            angulo = 0.0
        return Geometria(giro, voltear_h, voltear_v, angulo, bool(self.recortar_bordes))

    def es_identidad(self) -> bool:
        g = self.normalizada()
        return g.giro90 == 0 and not g.voltear_h and not g.voltear_v and g.enderezar == 0.0

    def girada(self, pasos: int = 1) -> "Geometria":
        """Suma ``pasos`` cuartos de vuelta horarios (negativo = antihorario) al
        resultado tal como se ve. El enderezado no cambia: los giros conmutan."""
        return replace(self, giro90=(int(self.giro90) + int(pasos)) % 4)

    def volteada(self, horizontal: bool = True) -> "Geometria":
        """Espejo del resultado tal como se ve (para los botones de la interfaz).

        Como el volteo se aplica antes del giro, con un giro impar el espejo
        horizontal de lo que se ve es el vertical de la original (y viceversa).
        Un espejo invierte el sentido de cualquier rotación, así que el
        enderezado cambia de signo.
        """
        sobre_h = horizontal == (int(self.giro90) % 2 == 0)
        if sobre_h:
            return replace(self, voltear_h=not self.voltear_h, enderezar=-self.enderezar)
        return replace(self, voltear_v=not self.voltear_v, enderezar=-self.enderezar)


# ---------------------------------------------------------------------------
# Matriz y tamaño del resultado
# ---------------------------------------------------------------------------

def _tamano_enderezado(a: int, b: int, angulo: float) -> tuple[int, int]:
    """Mayor rectángulo centrado con la proporción a:b que entra en la foto a x b
    girada ``angulo`` grados, redondeado hacia adentro a píxeles enteros.

    Un rectángulo de lados (k·a, k·b) girado entra en a x b si
    k·(a·|cos| + b·|sen|) <= a  y  k·(a·|sen| + b·|cos|) <= b.
    El lado largo se redondea hacia abajo y el corto se elige para mantener la
    proporción (error < 1 px) sin salirse.
    """
    t = math.radians(angulo)
    c, s = abs(math.cos(t)), abs(math.sin(t))
    k = min(a / (a * c + b * s), b / (a * s + b * c))
    largo, corto = max(a, b), min(a, b)
    largo2 = max(1, math.floor(k * largo + 1e-7))
    corto2 = max(1, min(math.floor(largo2 * corto / largo + 0.5), math.floor(k * corto + 1e-7)))
    return (largo2, corto2) if a >= b else (corto2, largo2)


def _plan(geo: Geometria, w: int, h: int) -> tuple[Geometria, np.ndarray, int, int]:
    """(geometría canónica, matriz 3x3 original -> resultado en píxeles continuos, w2, h2)."""
    g = geo.normalizada()
    m = np.eye(3)
    if g.voltear_h:
        m = np.array([[-1.0, 0.0, w], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]) @ m
    if g.voltear_v:
        m = np.array([[1.0, 0.0, 0.0], [0.0, -1.0, h], [0.0, 0.0, 1.0]]) @ m
    a, b = w, h
    for _ in range(g.giro90):
        # Cuarto de vuelta horario de una imagen a x b: (x, y) -> (b - y, x); queda b x a.
        m = np.array([[0.0, -1.0, b], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]) @ m
        a, b = b, a
    if g.enderezar == 0.0:
        return g, m, a, b
    w2, h2 = _tamano_enderezado(a, b, g.enderezar) if g.recortar_bordes else (a, b)
    # Rotación horaria en pantalla (y hacia abajo) alrededor del centro, y el
    # centro de la foto girada va al centro del resultado.
    t = math.radians(g.enderezar)
    c, s = math.cos(t), math.sin(t)
    r = np.array([
        [c, -s, w2 / 2 - (c * a / 2 - s * b / 2)],
        [s, c, h2 / 2 - (s * a / 2 + c * b / 2)],
        [0.0, 0.0, 1.0],
    ])
    return g, r @ m, w2, h2


def matriz_geometria(geo: Geometria, w: int, h: int) -> np.ndarray:
    """Matriz 3x3 (float64) que lleva píxeles continuos de la original (w x h) a
    los del resultado. El centro del píxel (i, j) está en (j + 0,5, i + 0,5)."""
    return _plan(geo, int(w), int(h))[1]


def tamano_resultante(w: int, h: int, geo: Geometria) -> tuple[int, int]:
    """(ancho, alto) del resultado de ``aplicar_geometria`` sobre una foto w x h."""
    _g, _m, w2, h2 = _plan(geo, int(w), int(h))
    return w2, h2


# ---------------------------------------------------------------------------
# Puntos normalizados
# ---------------------------------------------------------------------------

def _aplicar_matriz(puntos, m: np.ndarray, desde: tuple[int, int], hacia: tuple[int, int]) -> np.ndarray:
    p = np.asarray(puntos, dtype=np.float64)
    forma = p.shape
    p = p.reshape(-1, 2) * desde
    q = p @ m[:2, :2].T + m[:2, 2]
    return (q / hacia).reshape(forma)


def transformar_puntos(puntos, geo: Geometria, w: int, h: int) -> np.ndarray:
    """Puntos normalizados de la foto ORIGINAL (w x h) -> normalizados del resultado.

    ``puntos``: (x, y) suelto o cualquier secuencia de pares (forma N x 2).
    Devuelve un ``np.ndarray`` float64 con la misma forma. Con enderezado, un
    punto puede caer fuera de 0..1 (en la parte recortada).
    """
    _g, m, w2, h2 = _plan(geo, int(w), int(h))
    return _aplicar_matriz(puntos, m, (w, h), (w2, h2))


def destransformar_puntos(puntos, geo: Geometria, w: int, h: int) -> np.ndarray:
    """Inversa exacta de ``transformar_puntos``: normalizados del resultado ->
    normalizados de la foto ORIGINAL (w x h es el tamaño de la original)."""
    _g, m, w2, h2 = _plan(geo, int(w), int(h))
    return _aplicar_matriz(puntos, np.linalg.inv(m), (w2, h2), (w, h))


# ---------------------------------------------------------------------------
# Imagen
# ---------------------------------------------------------------------------

_GIROS_CV = {1: cv2.ROTATE_90_CLOCKWISE, 2: cv2.ROTATE_180, 3: cv2.ROTATE_90_COUNTERCLOCKWISE}
_TIPOS_CV = (np.uint8, np.uint16, np.int16, np.float32, np.float64)


def _girar_y_voltear(img: np.ndarray, g: Geometria) -> np.ndarray:
    """Volteo y cuartos de vuelta exactos (``g`` canónica). Siempre devuelve una copia."""
    if (img.dtype in _TIPOS_CV and img.flags.c_contiguous
            and (img.ndim == 2 or (img.ndim == 3 and img.shape[2] <= 4))):
        # OpenCV hace lo mismo que NumPy pero ≈2 veces más rápido sobre 12 MP.
        salida = img
        if g.voltear_h or g.voltear_v:
            salida = cv2.flip(salida, 1 if g.voltear_h else 0)
        if g.giro90:
            salida = cv2.rotate(salida, _GIROS_CV[g.giro90])
        if salida is img:
            return img.copy()
        return salida[..., None] if salida.ndim < img.ndim else salida  # OpenCV quita el canal único
    salida = img
    if g.voltear_h:
        salida = salida[:, ::-1]
    if g.voltear_v:
        salida = salida[::-1]
    if g.giro90:
        salida = np.rot90(salida, -g.giro90)  # k negativo = horario
    return salida.copy(order="C")


def aplicar_geometria(img: np.ndarray, geo: Geometria, interpolacion: int = cv2.INTER_LANCZOS4,
                      borde: str = "reflejo") -> np.ndarray:
    """Voltea, gira y endereza ``img`` (siempre en ese orden). Devuelve una copia nueva.

    Sirve para RGB uint8 HxWx3, alfa uint8 HxW, máscaras float32 HxW (u otra
    imagen de hasta 4 canales que acepte OpenCV). Volteos y giros son exactos
    (cualquier tipo de dato); el enderezado interpola con ``interpolacion``
    (constante de OpenCV: Lanczos por defecto, ``cv2.INTER_LINEAR`` alcanza para
    máscaras de la vista previa). En imágenes de punto flotante el resultado se
    limita al rango de la entrada, así el rebote de Lanczos no saca una máscara
    de 0..1. Determinista; no modifica la entrada.

    ``borde`` solo importa al enderezar sin recorte: "reflejo" rellena las
    esquinas con la propia foto espejada; "transparente" las deja en 0. Con
    recorte no hay esquinas vacías (el reflejo solo completa el soporte del
    filtro en el último medio píxel).
    """
    if borde not in BORDES:
        raise ValueError(f"borde desconocido: {borde!r} (válidos: {', '.join(BORDES)})")
    h, w = img.shape[:2]
    g, m, w2, h2 = _plan(geo, w, h)
    if g.enderezar == 0.0:
        return _girar_y_voltear(img, g)

    # OpenCV ubica el centro del píxel en coordenadas enteras: se corre medio píxel.
    a_cv = np.array([[1.0, 0.0, -0.5], [0.0, 1.0, -0.5], [0.0, 0.0, 1.0]])
    desde_cv = np.array([[1.0, 0.0, 0.5], [0.0, 1.0, 0.5], [0.0, 0.0, 1.0]])
    inversa = a_cv @ np.linalg.inv(m) @ desde_cv  # píxel del resultado -> píxel de la original
    rellena = not g.recortar_bordes and borde == "transparente"
    salida = cv2.warpAffine(
        np.ascontiguousarray(img), inversa[:2], (w2, h2),
        flags=interpolacion | cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_CONSTANT if rellena else cv2.BORDER_REFLECT,
        borderValue=0,
    )
    if salida.ndim < img.ndim:
        salida = salida[..., None]  # OpenCV quita el canal único
    if np.issubdtype(img.dtype, np.floating) and img.size:
        bajo, alto = float(img.min()), float(img.max())
        if rellena:
            bajo, alto = min(bajo, 0.0), max(alto, 0.0)
        np.clip(salida, bajo, alto, out=salida)
    return salida


# ---------------------------------------------------------------------------
# Horizonte automático
# ---------------------------------------------------------------------------

def _gris_8(rgb: np.ndarray) -> np.ndarray:
    img = np.asarray(rgb)
    if img.ndim == 3:
        img = img[..., :3]
    if img.dtype != np.uint8:
        if np.issubdtype(img.dtype, np.floating):
            img = np.clip(img * 255.0 + 0.5, 0, 255).astype(np.uint8)
        else:
            img = (img.astype(np.float64) * (255.0 / max(float(np.iinfo(img.dtype).max), 1.0))).astype(np.uint8)
    img = np.ascontiguousarray(img)
    if img.ndim == 3:
        return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.shape[2] == 3 else img[..., 0].copy()
    return img


def _mediana_ponderada(valores: np.ndarray, pesos: np.ndarray) -> float:
    orden = np.argsort(valores, kind="stable")
    acumulado = np.cumsum(pesos[orden])
    return float(valores[orden][np.searchsorted(acumulado, acumulado[-1] / 2.0)])


def _afinar_segmento(bordes: np.ndarray, segmento: np.ndarray, banda: float = 1.5,
                     vueltas: int = 3) -> Optional[float]:
    """Dirección (grados) de la recta que mejor ajusta los píxeles de borde
    cercanos al segmento (mínimos cuadrados totales).

    Los extremos que da HoughLinesP son píxeles enteros: en una recta poco
    inclinada el borde es una escalera y el segmento tiende a quedar horizontal.
    Ajustar todos los píxeles de la franja (que se alarga un poco en cada
    vuelta) recupera la inclinación con precisión de centésimas de grado.
    """
    h, w = bordes.shape
    x1, y1, x2, y2 = segmento
    centro = np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0])
    direccion = np.array([x2 - x1, y2 - y1], dtype=np.float64)
    medio = float(np.hypot(*direccion)) / 2.0
    if medio < 1.0:
        return None
    direccion /= 2.0 * medio
    for _ in range(vueltas):
        medio *= 1.2
        a, b = centro - direccion * medio, centro + direccion * medio
        x0 = max(0, int(math.floor(min(a[0], b[0]) - banda - 1)))
        y0 = max(0, int(math.floor(min(a[1], b[1]) - banda - 1)))
        xf = min(w, int(math.ceil(max(a[0], b[0]) + banda + 2)))
        yf = min(h, int(math.ceil(max(a[1], b[1]) + banda + 2)))
        ys, xs = np.nonzero(bordes[y0:yf, x0:xf])
        q = np.column_stack([xs + x0, ys + y0]).astype(np.float64) - centro
        normal = np.array([-direccion[1], direccion[0]])
        cerca = (np.abs(q @ normal) <= banda) & (np.abs(q @ direccion) <= medio)
        if int(cerca.sum()) < 10:
            break
        q = q[cerca]
        media = q.mean(axis=0)
        q -= media
        _valores, vectores = np.linalg.eigh(q.T @ q)
        nueva = vectores[:, 1]  # eje principal
        if nueva @ direccion < 0:
            nueva = -nueva
        centro, direccion = centro + media, nueva
    return math.degrees(math.atan2(direccion[1], direccion[0]))


def detectar_horizonte(rgb: np.ndarray, limite: float = LIMITE_HORIZONTE) -> Optional[float]:
    """Ángulo (grados) para poner en ``Geometria.enderezar`` y nivelar la foto,
    o None si no hay líneas suficientes para decidirlo.

    Convención: si la escena está girada α grados en sentido horario (el
    horizonte baja hacia la derecha), devuelve -α; aplicar ese enderezado la
    deja nivelada. Limitado a ±``limite``.

    Busca bordes (Canny) y segmentos rectos (HoughLinesP) en una versión
    reducida. Cada segmento casi horizontal (o casi vertical, con la mitad de
    peso) vota su inclinación con peso = largo; se toma la mediana ponderada y
    se afina con el promedio de los que coinciden con ella (±1°). Exige que esos
    segmentos sumen al menos ``APOYO_MINIMO`` lados largos y ``FRACCION_MINIMA``
    del peso total: el ruido o la textura sin líneas dan None.
    """
    gris = _gris_8(rgb)
    h, w = gris.shape[:2]
    f = min(1.0, LADO_DETECCION / max(h, w, 1))
    if f < 1.0:
        gris = cv2.resize(gris, (max(1, round(w * f)), max(1, round(h * f))), interpolation=cv2.INTER_AREA)
    h, w = gris.shape[:2]
    largo, corto = max(h, w), min(h, w)
    if corto < 32:
        return None
    suave = cv2.GaussianBlur(gris, (0, 0), 1.2)
    # Umbrales según el brillo típico (con un piso para fotos oscuras).
    mediana = float(np.median(suave))
    bordes = cv2.Canny(suave, max(20.0, 0.66 * mediana), max(50.0, 1.33 * mediana), L2gradient=True)
    bordes[:3], bordes[-3:], bordes[:, :3], bordes[:, -3:] = 0, 0, 0, 0  # el marco no es una línea
    lineas = cv2.HoughLinesP(bordes, 1, np.pi / 720, threshold=max(20, corto // 20),
                             minLineLength=max(24.0, 0.08 * corto), maxLineGap=max(2.0, largo / 400))
    if lineas is None:
        return None
    seg = lineas.reshape(-1, 4).astype(np.float64)
    dx, dy = seg[:, 2] - seg[:, 0], seg[:, 3] - seg[:, 1]
    # Inclinación respecto de la horizontal o la vertical más cercana, en -45..45:
    # una escena girada α horario da α en las dos familias.
    alfa = (np.degrees(np.arctan2(dy, dx)) + 45.0) % 90.0 - 45.0
    peso = np.hypot(dx, dy) * np.where(np.abs(dy) > np.abs(dx), PESO_VERTICALES, 1.0)
    utiles = np.abs(alfa) <= limite
    if not utiles.any():
        return None
    seg, alfa, peso = seg[utiles], alfa[utiles], peso[utiles]
    centro = _mediana_ponderada(alfa, peso)
    acuerdo = np.abs(alfa - centro) <= TOLERANCIA_HORIZONTE
    apoyo = float(peso[acuerdo].sum())
    if apoyo < APOYO_MINIMO * largo or apoyo < FRACCION_MINIMA * float(peso.sum()):
        return None
    # Afinado: cada segmento que coincide se reajusta sobre sus píxeles de borde
    # (los más largos primero, hasta 80) y se promedia ponderando por largo.
    indices = np.flatnonzero(acuerdo)
    indices = indices[np.argsort(-peso[indices], kind="stable")][:80]
    finos, pesos_finos = [], []
    for i in indices:
        angulo = _afinar_segmento(bordes, seg[i])
        if angulo is None:
            continue
        fino = (angulo + 45.0) % 90.0 - 45.0
        if abs(fino - centro) <= 2.0 * TOLERANCIA_HORIZONTE:  # el ajuste no se fue a otra recta
            finos.append(fino)
            pesos_finos.append(peso[i])
    if finos:
        inclinacion = float(np.average(finos, weights=pesos_finos))
    else:
        inclinacion = float(np.average(alfa[acuerdo], weights=peso[acuerdo]))
    return float(np.clip(round(-inclinacion, 2), -limite, limite)) + 0.0
