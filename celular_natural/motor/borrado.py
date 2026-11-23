"""Borrar objetos: relleno automático ("pincel corrector") y tampón de clonar.

Funciones puras sobre RGB uint8 HxWx3 y una máscara HxW (float 0..1, 1 = borrar;
también se acepta bool o uint8 0..255). No modifican la entrada y devuelven
siempre un arreglo nuevo uint8 del mismo tamaño. No dependen de la interfaz.

Máscara
-------
La máscara puede venir con borde suave (pincel, pluma). Se separa en:

  * núcleo   (≥ 0,5): se binariza y se dilata unos píxeles (``dilatar``) para
             tapar también el borde del objeto (antialias, halo, sombra fina).
             Dentro del núcleo dilatado se borra todo, con una rampa suave
             hacia el borde de la dilatación.
  * pluma    (0,01..0,5): se rellena igual, pero se mezcla con el original en
             la proporción que indica la máscara (respeta el borde suave).

Lo que queda fuera de esa zona no se toca: queda idéntico, bit a bit.

Relleno (``rellenar``)
----------------------
OpenCV headless solo trae ``cv2.inpaint`` (Telea / Navier-Stokes), que propaga
el borde hacia adentro: en zonas grandes deja una mancha lisa con "conos", y a
resolución completa es lento. Acá se completa el hueco copiando parches del
entorno, en dos bandas:

  1. Estructura y textura media, a resolución reducida (el hueco queda con
     ≈ ``PIX_BAJA`` píxeles, factor ≤ 1/2): EM de Wexler, Shechtman e Irani
     (2007) sobre un conjunto FIJO de desplazamientos candidatos (estadística
     de desplazamientos de He y Sun, 2012, + un abanico de cobertura). Para un
     desplazamiento fijo, el costo de todos los parches sale de un
     ``boxFilter``: todo vectorizado, sin bucles por píxel ni PatchMatch. Va
     de grueso a fino (pirámide de hasta 4 niveles, semilla armónica en el
     más grueso) y al votar cada parche se corre en color (sesgo acotado) para
     seguir degradés. Resultado: horizontes y bordes que siguen, patrones
     regulares (ladrillos, baldosas) en fase, nubes/pasto con su textura.
  2. Detalle fino, a resolución completa: se copia el detalle (original −
     base reducida ampliada) desde el mismo desplazamiento que eligió el EM en
     cada lugar, con mezcla bilineal que conserva la varianza en las costuras
     (Σwᵢpᵢ / √Σwᵢ²). El grano queda como el del entorno.

Huecos finos o chicos (cables, rayones, manchitas: el EM no rinde ahí) van por
un camino barato: Telea reducido para la base + parches de detalle elegidos
por color en una banda alrededor, mezclados conservando la varianza.

Cada mancha de la máscara (componente conexa, agrupando las cercanas) se
procesa en su propio recorte, con su propio factor de reducción.

Costo medido (Windows, CPU de escritorio de 16 hilos, foto sintética de 12 MP
con degradé, nubes, pasto y ruido): círculo del 5 % de la foto ≈ 0,65 s;
franja del 5 % ≈ 0,4 s; círculo del 20 % ≈ 1,3 s; 50 manchas chicas ≈ 0,4 s;
cable de 8 px cruzando la foto ≈ 0,35 s. Crece con el área del hueco, casi no
con el tamaño de la foto (la reducción fija el trabajo del EM).

Rellena bien: texturas naturales (cielo con nubes, pasto, arena, asfalto, agua,
follaje, pared, ruido de sensor), degradés, bordes que cruzan el hueco cerca de
su centro (horizonte, cordón) y patrones regulares (ladrillos, baldosas).
Rellena peor: un borde largo que cruza un hueco grande lejos de su centro
(puede quedar una loma o un escalón), estructuras que no aparecen en el
entorno (caras, texto, objetos tapados a medias), líneas en perspectiva y
huecos que ocupan casi toda la foto. Para eso conviene ``clonar``.

Clonar (``clonar``)
-------------------
Tampón de clonar / corrector: copia en la zona marcada el contenido de la
misma zona desplazada (fuente = destino + desplazamiento). Con
``sin_costuras=True`` mezcla en el dominio del gradiente (``cv2.seamlessClone``
con ``NORMAL_CLONE``: Poisson, toma la textura de la fuente y el color/luz del
borde del destino); con ``False`` copia directo con el borde fundido. Lo que de
la fuente cae fuera de la foto se descarta y esa parte del destino queda sin
cambios (con el corte fundido). Costo (12 MP, zona del 5 %): ≈ 0,25 s sin
costuras, ≈ 0,1 s directo.

Ojo con ``cv2.seamlessClone`` (OpenCV 5.0): modifica la máscara que recibe y
la erosiona 3 px por dentro antes de armar el campo guía; si el borde del
objeto cae en esa franja, su gradiente "reconstruye" el objeto. Por eso se le
pasa una máscara propia, dilatada ``EROSION_CV + 1`` px.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import cv2
import numpy as np

from .comun import LADO_REFERENCIA, gauss

UMBRAL_MASCARA = 0.01  # por debajo de esto el píxel no se toca
UMBRAL_NUCLEO = 0.5    # desde acá la máscara es "objeto": se binariza y se dilata
PIX_BAJA = 8000        # píxeles de hueco buscados en la resolución reducida
FACTOR_MAXIMO = 0.5    # siempre se reduce al menos a la mitad (si no, no hay banda de detalle)
MAX_COMPONENTES = 64   # con más manchas que esto se procesa todo junto
# EM por desplazamientos (huecos gruesos)
LADO_EM = 9            # parche del EM (en la resolución reducida)
NIVELES_MAX = 4        # niveles de la pirámide del EM
ITER_EM_GRUESO = 8     # iteraciones en el nivel más chico
ITER_EM_FINO = 4       # iteraciones en cada nivel siguiente
MUESTRAS_ESTADISTICA = 80   # parches de muestra para la estadística de desplazamientos
RADIO_ESTADISTICA = 40      # radio de búsqueda de esos vecinos (resolución del nivel)
PICOS_ESTADISTICA = 24      # desplazamientos más repetidos que se agregan
ITER_MEMBRANA = 1500   # tope de relajaciones de la membrana (semilla del nivel más grueso)
SESGO_MAXIMO = 30.0    # corrimiento de color máximo de un parche al votar (niveles 0..255)
HEREDADOS_MAX = 48     # desplazamientos que pasan de un nivel al siguiente (los más usados)
ESPESOR_FINO = 6.0     # huecos más finos que esto (reducidos) van por Telea + parches
EM_MIN_PIX = 2000      # ...y los más chicos que esto (píxeles reducidos; ≈ 8000 px de foto)
COMPACIDAD_MIN = 0.15  # ...y los que ocupan menos que esto de su caja (líneas en diagonal)
EROSION_CV = 3         # px que cv2.seamlessClone le come a la máscara por dentro
# Parches de textura (huecos finos)
PARCHE_MIN, PARCHE_MAX = 32, 128
CANDIDATOS_MAX = 3000  # parches fuente considerados por grupo
ELEGIBLES = 6          # se elige al azar entre los N más parecidos
PESO_DISTANCIA = 1.0   # penalización por lejanía (en niveles de color por parche de distancia)


# ---------------------------------------------------------------- validación
def _validar_rgb(rgb: np.ndarray) -> None:
    if not isinstance(rgb, np.ndarray):
        raise TypeError("rgb debe ser un arreglo de NumPy")
    if rgb.dtype != np.uint8:
        raise TypeError(f"rgb debe ser uint8 (vino {rgb.dtype})")
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.shape[0] < 1 or rgb.shape[1] < 1:
        raise ValueError(f"rgb debe tener forma HxWx3 (vino {rgb.shape})")


def _validar_mascara(mascara: np.ndarray, forma: tuple[int, int]) -> np.ndarray:
    """Devuelve la máscara HxW (vista, sin copiar). Acepta float, bool o uint8 0..255."""
    if not isinstance(mascara, np.ndarray):
        raise TypeError("la máscara debe ser un arreglo de NumPy")
    m = mascara
    if m.ndim == 3 and m.shape[2] == 1:
        m = m[..., 0]
    if m.ndim != 2 or m.shape != tuple(forma):
        raise ValueError(f"la máscara debe ser HxW = {tuple(forma)} (vino {mascara.shape})")
    if not (m.dtype == np.bool_ or m.dtype == np.uint8 or np.issubdtype(m.dtype, np.floating)):
        raise TypeError(f"la máscara debe ser float 0..1, bool o uint8 (vino {m.dtype})")
    return m


def _mascara_activa(m: np.ndarray) -> np.ndarray:
    """Píxeles que se tocan (bool). Los NaN cuentan como 0."""
    if m.dtype == np.bool_:
        return m
    if m.dtype == np.uint8:
        return m > round(UMBRAL_MASCARA * 255)
    return m > UMBRAL_MASCARA


def _mascara_a_float(m: np.ndarray) -> np.ndarray:
    if m.dtype == np.bool_:
        return m.astype(np.float32)
    if m.dtype == np.uint8:
        return m.astype(np.float32) * np.float32(1.0 / 255.0)
    f = np.nan_to_num(m.astype(np.float32), nan=0.0, posinf=1.0, neginf=0.0)
    return np.clip(f, 0.0, 1.0)


def _numero(valor, nombre: str) -> float:
    if isinstance(valor, (bool, np.bool_)):
        raise TypeError(f"{nombre} debe ser un número")
    try:
        x = float(valor)
    except (TypeError, ValueError):
        raise TypeError(f"{nombre} debe ser un número (vino {valor!r})") from None
    if not math.isfinite(x):
        raise ValueError(f"{nombre} debe ser finito (vino {valor!r})")
    return x


def _radio_dilatacion(dilatar, h: int, w: int) -> int:
    """``None`` = automático: 6 px en una foto de 12 MP, proporcional al tamaño."""
    if dilatar is None:
        return max(2, round(6 * max(h, w) / LADO_REFERENCIA))
    r = _numero(dilatar, "dilatar")
    if r < 0:
        raise ValueError(f"dilatar no puede ser negativo (vino {dilatar!r})")
    return int(round(r))


def _validar_desplazamiento(desplazamiento_xy) -> tuple[int, int]:
    if isinstance(desplazamiento_xy, (str, bytes)):
        raise TypeError("desplazamiento_xy debe ser un par (dx, dy)")
    try:
        dx, dy = desplazamiento_xy
    except (TypeError, ValueError):
        raise TypeError(f"desplazamiento_xy debe ser un par (dx, dy) (vino {desplazamiento_xy!r})") from None
    return int(round(_numero(dx, "dx"))), int(round(_numero(dy, "dy")))


# ------------------------------------------------------------------ máscara
@dataclass
class _Zona:
    """Zona a modificar, recortada al rectángulo [y0:y1, x0:x1] de la foto."""
    y0: int
    y1: int
    x0: int
    x1: int
    hueco: np.ndarray  # bool: píxeles que se sintetizan (y los únicos que cambian)
    alfa: np.ndarray   # float32 0..1: cuánto del relleno entra en cada píxel


def _rampa(binaria: np.ndarray, sigma: float) -> np.ndarray:
    """0 en el borde de ``binaria`` y fuera, sube suave a 1 hacia adentro (≈3σ)."""
    return np.clip(2.0 * gauss(binaria.astype(np.float32), sigma) - 1.0, 0.0, 1.0)


def _preparar(mascara: np.ndarray, radio: int) -> Optional[_Zona]:
    h, w = mascara.shape
    activa = np.ascontiguousarray(_mascara_activa(mascara))
    bx, by, bw, bh = cv2.boundingRect(activa.view(np.uint8))
    if bw == 0 or bh == 0:
        return None
    sigma = max(0.7, radio / 3.0)
    pad = radio + int(math.ceil(3 * sigma)) + 1
    y0, y1 = max(0, by - pad), min(h, by + bh + pad)
    x0, x1 = max(0, bx - pad), min(w, bx + bw + pad)
    suave = _mascara_a_float(mascara[y0:y1, x0:x1])
    nucleo = (suave >= UMBRAL_NUCLEO).astype(np.uint8)
    if radio > 0 and nucleo.any():
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radio + 1, 2 * radio + 1))
        nucleo = cv2.dilate(nucleo, k)
    hueco = (nucleo > 0) | (suave > UMBRAL_MASCARA)
    alfa = np.maximum(suave, _rampa(nucleo, sigma))
    alfa[~hueco] = 0.0
    return _Zona(y0, y1, x0, x1, hueco, alfa.astype(np.float32))


# --------------------------------------------------------------- relleno
def _factor(area: int) -> float:
    """Factor de reducción para que el hueco tenga ≈ PIX_BAJA píxeles."""
    return min(FACTOR_MAXIMO, math.sqrt(PIX_BAJA / max(1, area)))


def _lado_parche(f: float) -> int:
    t = int(np.clip(round(4.0 / f), PARCHE_MIN, PARCHE_MAX))
    return t + (t % 2)


def _grupos(zona: _Zona, h: int, w: int) -> list[tuple[int, int, int, int]]:
    """Recortes (y0, y1, x0, x1) en coordenadas de la foto, uno por grupo de manchas.

    Cada mancha lleva un margen de contexto proporcional a su espesor; las que
    se tocan con margen y todo se procesan juntas. Los recortes no se solapan,
    así cada píxel del hueco pertenece a un solo grupo.
    """
    n, _, stats, _ = cv2.connectedComponentsWithStats(zona.hueco.view(np.uint8), connectivity=8)
    rects = []
    for i in range(1, n):
        cx, cy, cw, ch, area = (int(v) for v in stats[i])
        espesor = area / max(cw, ch)
        margen = max(2 * _lado_parche(_factor(area)) + 4, round(0.5 * espesor))
        rects.append([max(0, zona.y0 + cy - margen), min(h, zona.y0 + cy + ch + margen),
                      max(0, zona.x0 + cx - margen), min(w, zona.x0 + cx + cw + margen)])
    if len(rects) > MAX_COMPONENTES:
        return [(min(r[0] for r in rects), max(r[1] for r in rects),
                 min(r[2] for r in rects), max(r[3] for r in rects))]
    fusiono = True
    while fusiono:
        fusiono = False
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                a, b = rects[i], rects[j]
                if a[0] < b[1] and b[0] < a[1] and a[2] < b[3] and b[2] < a[3]:
                    rects[i] = [min(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), max(a[3], b[3])]
                    del rects[j]
                    fusiono = True
                    break
            if fusiono:
                break
    return [tuple(r) for r in rects]


def _inpaint_float(img: np.ndarray, hueco: np.ndarray, radio: int = 3) -> np.ndarray:
    """Telea por canal en float32 (evita los escalones de cuantizar a 8 bits)."""
    m = hueco.astype(np.uint8)
    canales = [cv2.inpaint(np.ascontiguousarray(img[..., c]), m, radio, cv2.INPAINT_TELEA) for c in range(3)]
    return np.stack(canales, axis=-1)


def _espesor(hueco: np.ndarray) -> float:
    """Espesor máximo del hueco (2 × la mayor distancia a lo conocido)."""
    return 2.0 * float(cv2.distanceTransform(hueco.astype(np.uint8), cv2.DIST_L2, 3).max())


def _ventanas_libres(hueco: np.ndarray, lado: int) -> np.ndarray:
    """Esquinas (y, x) cuya ventana lado×lado no toca el hueco ni sale de la imagen."""
    integral = cv2.integral(hueco.astype(np.uint8))
    return (integral[lado:, lado:] - integral[:-lado, lado:] - integral[lado:, :-lado]
            + integral[:-lado, :-lado]) == 0


def _candidatos(img: np.ndarray, hueco: np.ndarray, lado: int, rng: np.random.Generator,
                previos: Optional[np.ndarray]) -> np.ndarray:
    """Desplazamientos (dy, dx) candidatos para copiar dentro del hueco.

    * Estadística de desplazamientos (He y Sun, 2012): para una muestra de
      parches conocidos se busca su vecino más parecido (no pegado) y se toman
      los desplazamientos más repetidos. En un patrón regular (ladrillos,
      baldosas, rejas) aparecen su período y sus múltiplos.
    * Cobertura: 8 o 16 direcciones × 2..6 distancias (según el tamaño del
      hueco) hasta su espesor, para que todo píxel tenga de dónde copiar.
    * Los que usó el nivel más grueso de la pirámide (ya escalados).
    """
    h, w = hueco.shape
    alcance = _espesor(hueco) + lado + 2
    minima = lado // 2 + 2
    distancias = np.geomspace(minima, alcance, int(np.clip(round(2 * math.log2(alcance / minima)), 2, 6)))
    direcciones = 16 if alcance > 3 * lado else 8
    angulos = np.arange(direcciones) * (2.0 * np.pi / direcciones)
    cobertura = np.stack([np.outer(distancias, np.sin(angulos)).ravel(),
                          np.outer(distancias, np.cos(angulos)).ravel()], axis=1)
    listas = [np.round(cobertura).astype(np.int64)]
    if previos is not None and len(previos):
        listas.append(previos.astype(np.int64))

    libres = _ventanas_libres(hueco, lado)
    ys, xs = np.nonzero(libres)
    if ys.size:
        vecinos = []
        radio = int(min(1.5 * alcance, RADIO_ESTADISTICA))
        muestras = int(np.clip(np.count_nonzero(hueco) / 25, 24, MUESTRAS_ESTADISTICA))
        for i in rng.choice(ys.size, min(muestras, ys.size), replace=False):
            y, x = int(ys[i]), int(xs[i])
            by0, by1 = max(0, y - radio), min(h, y + lado + radio)
            bx0, bx1 = max(0, x - radio), min(w, x + lado + radio)
            costo = cv2.matchTemplate(img[by0:by1, bx0:bx1], img[y:y + lado, x:x + lado], cv2.TM_SQDIFF)
            costo[~libres[by0:by0 + costo.shape[0], bx0:bx0 + costo.shape[1]]] = np.inf
            cy, cx = y - by0, x - bx0
            costo[max(0, cy - lado + 1):cy + lado, max(0, cx - lado + 1):cx + lado] = np.inf  # no él mismo
            j = int(np.argmin(costo))
            if np.isfinite(costo.flat[j]):
                vecinos.append((by0 + j // costo.shape[1] - y, bx0 + j % costo.shape[1] - x))
        if vecinos:
            v = np.array(vecinos, np.int64)
            m = int(np.abs(v).max())
            histograma = np.zeros((2 * m + 1, 2 * m + 1), np.float32)
            np.add.at(histograma, (v[:, 0] + m, v[:, 1] + m), 1.0)
            histograma = cv2.GaussianBlur(histograma, (0, 0), 1.0)
            picos = (histograma == cv2.dilate(histograma, np.ones((5, 5), np.uint8))) & (histograma > 0.15)
            py, px = np.nonzero(picos)
            orden = np.argsort(-histograma[py, px])[:PICOS_ESTADISTICA]
            listas.append(np.stack([py[orden] - m, px[orden] - m], axis=1))
    todos = np.unique(np.concatenate(listas), axis=0)
    return todos[np.abs(todos).max(axis=1) > 0]


def _em_nivel(img: np.ndarray, hueco: np.ndarray, inicial: np.ndarray, d: np.ndarray,
              lado: int, iteraciones: int) -> tuple[np.ndarray, np.ndarray]:
    """Completa el hueco por EM (Wexler, Shechtman e Irani, 2007) con desplazamientos fijos.

    * Paso E: cada parche que toca el hueco elige el desplazamiento ``d[k]``
      cuyo parche fuente (todo conocido) más se parece al relleno actual. Para
      un desplazamiento fijo, el costo de TODOS los parches sale de un solo
      ``boxFilter`` de la diferencia: K pasadas vectorizadas, sin bucles por píxel.
      Lo conocido pesa 1 y lo rellenado menos cuanto más adentro está.
    * Paso M: cada píxel del hueco es el promedio de lo que le proponen los
      parches que lo cubren, pesado por lo bien que encajó cada uno y por su
      confianza. Al votar, cada parche se corre en color por la media de su
      diferencia con el relleno actual (sesgo acotado a ±``SESGO_MAXIMO``,
      como el "corrector" de Image Melding, Darabi et al. 2012): un cielo con
      degradé se puede copiar de más lejos sin traer otro tono. El sesgo NO
      entra al elegir parches: medido, eso deja que un parche de cielo "se
      haga pasar" por pasto y rompe los bordes (horizontes, cordones).

    Devuelve el relleno (todo el nivel) y la etiqueta (índice en ``d``) del
    parche centrado en cada píxel (-1 fuera de la zona).
    """
    r = lado // 2
    rel = inicial.astype(np.float32, copy=True)
    etiqueta_nivel = np.full(hueco.shape, -1, np.int32)
    if len(d) == 0:
        return rel, etiqueta_nivel
    p = int(np.abs(d).max()) + 2 * r + 2
    img_pad = cv2.copyMakeBorder(img, p, p, p, p, cv2.BORDER_REPLICATE)
    malo_pad = cv2.copyMakeBorder(hueco.astype(np.float32), p, p, p, p, cv2.BORDER_CONSTANT, value=1.0)
    caja = np.ones((lado, lado), np.uint8)
    centros = cv2.dilate(hueco.astype(np.uint8), caja) > 0
    zona = cv2.dilate(centros.astype(np.uint8), caja) > 0
    filas, columnas = np.nonzero(zona.any(axis=1))[0], np.nonzero(zona.any(axis=0))[0]
    y0, y1, x0, x1 = filas[0], filas[-1] + 1, columnas[0], columnas[-1] + 1
    hz = hueco[y0:y1, x0:x1]
    fuera = ~centros[y0:y1, x0:x1]
    distancia = cv2.distanceTransform(hz.astype(np.uint8), cv2.DIST_L2, 3)
    peso = np.where(hz, 1.3 ** (-distancia), 1.0).astype(np.float32)
    # Peso total de cada parche: normaliza el costo (los del borde tienen más
    # píxeles conocidos) y es la confianza con la que vota cada parche.
    peso_parche = cv2.boxFilter(peso, -1, (lado, lado), normalize=False, borderType=cv2.BORDER_CONSTANT)
    confianza = peso_parche / float(lado * lado)
    peso3 = cv2.merge([peso, peso, peso])
    f = np.ascontiguousarray(rel[y0:y1, x0:x1])
    fuentes, penal = [], []
    for dy, dx in d.tolist():
        sl = (slice(p + y0 + dy, p + y1 + dy), slice(p + x0 + dx, p + x1 + dx))
        fuentes.append(np.ascontiguousarray(img_pad[sl]))
        malos = cv2.boxFilter(malo_pad[sl], -1, (lado, lado), normalize=False, borderType=cv2.BORDER_CONSTANT)
        pk = np.where(malos > 0.5, np.float32(np.inf), np.float32(0.0)).astype(np.float32)
        pk[fuera] = np.inf
        penal.append(pk)
    forma = hz.shape
    mejor = np.empty(forma, np.float32)
    etiqueta = np.empty(forma, np.int32)
    gana = np.empty(forma, bool)
    sumar = np.ones((1, 3), np.float32)
    for _ in range(iteraciones):
        mejor.fill(np.inf)
        etiqueta.fill(-1)
        for k, fuente in enumerate(fuentes):
            dif = cv2.subtract(f, fuente)
            costo = cv2.boxFilter(cv2.multiply(cv2.transform(cv2.multiply(dif, dif), sumar), peso), -1,
                                  (lado, lado), normalize=False, borderType=cv2.BORDER_CONSTANT)
            costo += penal[k]
            np.less(costo, mejor, out=gana)
            np.copyto(mejor, costo, where=gana)
            np.copyto(etiqueta, k, where=gana)
        validas = etiqueta >= 0
        if not validas.any():
            break
        normalizado = np.maximum(mejor / np.maximum(peso_parche, 1e-6), 0.0)
        sigma2 = float(np.percentile(normalizado[validas], 75)) + 1e-3
        similitud = np.where(validas, confianza * np.exp(-normalizado / (2.0 * sigma2)), 0.0).astype(np.float32)
        acumulado = np.zeros(forma + (3,), np.float32)
        suma = np.zeros(forma, np.float32)
        sesgo = np.zeros(forma + (3,), np.float32)
        for k in np.unique(etiqueta[validas]).tolist():
            es_k = etiqueta == k
            a = cv2.boxFilter(cv2.multiply(cv2.subtract(f, fuentes[k]), peso3), -1, (lado, lado),
                              normalize=False, borderType=cv2.BORDER_CONSTANT)
            sesgo[es_k] = a[es_k] / np.maximum(peso_parche[es_k], 1e-6)[:, None]
            votos = cv2.boxFilter(np.where(es_k, similitud, 0.0).astype(np.float32), -1,
                                  (lado, lado), normalize=False, borderType=cv2.BORDER_CONSTANT)
            acumulado += votos[..., None] * fuentes[k]
            suma += votos
        np.clip(sesgo, -SESGO_MAXIMO, SESGO_MAXIMO, out=sesgo)
        acumulado += cv2.boxFilter(sesgo * similitud[..., None], -1, (lado, lado), normalize=False,
                                   borderType=cv2.BORDER_CONSTANT)
        nuevo = hz & (suma > 1e-6)
        f[nuevo] = acumulado[nuevo] / suma[nuevo][:, None]
    rel[y0:y1, x0:x1] = f
    etiqueta_nivel[y0:y1, x0:x1] = etiqueta
    return rel, etiqueta_nivel


def _membrana(img: np.ndarray, hueco: np.ndarray) -> np.ndarray:
    """Interpolación armónica (Laplace con el borde fijo) del hueco.

    Es la semilla del EM en el nivel más grueso: Telea avanza desde el borde y
    deja conos que el EM después "congela" como lomas; la membrana no tiene
    dirección preferida (un borde que cruza el hueco por el centro queda recto,
    solo esfumado). Medido sobre horizontes: menos píxeles con la clase
    equivocada que partiendo de Telea. Se parte de Telea y se relaja con
    Jacobi; el nivel más grueso es chico, así que es barato.
    """
    rel = _inpaint_float(img, hueco)
    y0, y1, x0, x1 = _caja_del_hueco(hueco)
    y0, y1, x0, x1 = max(0, y0 - 1), min(hueco.shape[0], y1 + 1), max(0, x0 - 1), min(hueco.shape[1], x1 + 1)
    sub = np.ascontiguousarray(rel[y0:y1, x0:x1])
    hs = hueco[y0:y1, x0:x1][..., None]
    nucleo = np.array([[0, 0.25, 0], [0.25, 0, 0.25], [0, 0.25, 0]], np.float32)
    for _ in range(int(np.clip(2 * _espesor(hueco) ** 2, 50, ITER_MEMBRANA))):
        np.copyto(sub, cv2.filter2D(sub, -1, nucleo, borderType=cv2.BORDER_REPLICATE), where=hs)
    rel[y0:y1, x0:x1] = sub
    return rel


def _por_desplazamientos(img: np.ndarray, hueco: np.ndarray, rng: np.random.Generator
                         ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """EM de grueso a fino: el nivel más chico fija la estructura (horizonte,
    bordes), los siguientes la afinan partiendo del anterior ampliado.

    Devuelve (relleno float32, etiqueta por píxel, desplazamientos) del nivel
    más fino (el de ``img``).
    """
    piramide = [(img, hueco)]
    while len(piramide) < NIVELES_MAX:
        im, hu = piramide[-1]
        if _espesor(hu) <= 2 * LADO_EM or min(hu.shape) < 6 * LADO_EM:
            break
        tam = (max(1, round(hu.shape[1] / 2)), max(1, round(hu.shape[0] / 2)))
        hu2 = cv2.resize(hu.astype(np.float32), tam, interpolation=cv2.INTER_AREA) > 1e-4
        if hu2.all():
            break
        piramide.append((cv2.resize(im, tam, interpolation=cv2.INTER_AREA), hu2))
    relleno = etiqueta = d = None
    previos = None
    for nivel in range(len(piramide) - 1, -1, -1):
        im, hu = piramide[nivel]
        if relleno is None:
            inicial = _membrana(im, hu)
        else:
            ampliado = cv2.resize(relleno, (hu.shape[1], hu.shape[0]), interpolation=cv2.INTER_LINEAR)
            inicial = np.where(hu[..., None], ampliado, im)
        d = _candidatos(im, hu, LADO_EM, rng, previos)
        iteraciones = ITER_EM_GRUESO if relleno is None else ITER_EM_FINO
        relleno, etiqueta = _em_nivel(im, hu, inicial, d, LADO_EM, iteraciones)
        if nivel > 0:
            usados, cuantos = np.unique(etiqueta[etiqueta >= 0], return_counts=True)
            usados = usados[np.argsort(-cuantos)[:HEREDADOS_MAX]]
            escala = np.array(piramide[nivel - 1][1].shape, np.float64) / np.array(hu.shape, np.float64)
            previos = np.round(d[usados] * escala).astype(np.int64)
    return relleno, etiqueta, d


def _caja_del_hueco(hueco: np.ndarray) -> tuple[int, int, int, int]:
    filas, columnas = np.nonzero(hueco.any(axis=1))[0], np.nonzero(hueco.any(axis=0))[0]
    return int(filas[0]), int(filas[-1]) + 1, int(columnas[0]), int(columnas[-1]) + 1


def _detalle_por_etiquetas(detalle: np.ndarray, hueco: np.ndarray, etiqueta: np.ndarray,
                           d: np.ndarray, escala: tuple[float, float],
                           caja: tuple[int, int, int, int]) -> np.ndarray:
    """Copia el detalle fino a resolución completa siguiendo las etiquetas del EM.

    Cada píxel mezcla (bilineal) lo que proponen las etiquetas de los 4
    píxeles reducidos vecinos. Donde las 4 coinciden (casi todo) es una copia
    exacta, que se resuelve de una con ``cv2.remap``; en las celdas de costura
    se mezclan conservando la varianza (Σwᵢpᵢ / √Σwᵢ² agrupando etiquetas
    iguales) para no lavar la textura. Trabaja sobre ``caja`` (y0, y1, x0, x1).
    """
    y0, y1, x0, x1 = caja
    h, w = hueco.shape
    hs, ws = etiqueta.shape
    ey, ex = escala
    salida = np.zeros((y1 - y0, x1 - x0, 3), np.float32)
    if len(d) == 0:
        return salida
    dy = np.round(d[:, 0] / ey).astype(np.float32)
    dx = np.round(d[:, 1] / ex).astype(np.float32)
    valida = etiqueta >= 0
    lab_c = np.maximum(etiqueta, 0)
    dy_c, dx_c = dy[lab_c], dx[lab_c]

    # Celda reducida de cada fila/columna de la caja y peso bilineal.
    yy = np.arange(y0, y1, dtype=np.float32)
    xx = np.arange(x0, x1, dtype=np.float32)
    u, v = (yy + 0.5) * ey - 0.5, (xx + 0.5) * ex - 0.5
    u0, v0 = np.floor(u).astype(np.int64), np.floor(v).astype(np.int64)
    fu, fv = (u - u0).astype(np.float32), (v - v0).astype(np.float32)
    filas = [np.clip(u0, 0, hs - 1), np.clip(u0 + 1, 0, hs - 1)]
    columnas = [np.clip(v0, 0, ws - 1), np.clip(v0 + 1, 0, ws - 1)]

    def ampliar(grilla: np.ndarray, a: int, b: int) -> np.ndarray:
        return np.take(np.take(grilla, filas[a], axis=0), columnas[b], axis=1)

    # Celdas uniformes: los 4 vecinos con la misma etiqueta válida.
    abajo = np.concatenate([etiqueta[1:], etiqueta[-1:]], axis=0)
    derecha = np.concatenate([etiqueta[:, 1:], etiqueta[:, -1:]], axis=1)
    diagonal = np.concatenate([abajo[:, 1:], abajo[:, -1:]], axis=1)
    uniforme_c = valida & (etiqueta == abajo) & (etiqueta == derecha) & (etiqueta == diagonal)
    uniforme = ampliar(uniforme_c, 0, 0)
    mapa_y = yy[:, None] + ampliar(dy_c, 0, 0)
    mapa_x = xx[None, :] + ampliar(dx_c, 0, 0)
    muestra = cv2.remap(detalle, mapa_x, mapa_y, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT)
    malo = cv2.remap(hueco.astype(np.uint8), mapa_x, mapa_y, cv2.INTER_NEAREST,
                     borderMode=cv2.BORDER_CONSTANT, borderValue=1)
    copia = uniforme & (malo == 0)
    salida[copia] = muestra[copia]

    # Costuras: mezcla bilineal de las 4 propuestas, solo en esos píxeles.
    py, px = np.nonzero(~uniforme)
    if py.size == 0:
        return salida
    ry, rx = py + y0, px + x0
    acumulado = np.zeros((py.size, 3), np.float32)
    pesos, etiquetas = [], []
    for a, b in ((0, 0), (0, 1), (1, 0), (1, 1)):
        cu, cv = filas[a][py], columnas[b][px]
        lab = etiqueta[cu, cv]
        sy = ry + dy_c[cu, cv].astype(np.int64)
        sx = rx + dx_c[cu, cv].astype(np.int64)
        ok = (lab >= 0) & (sy >= 0) & (sy < h) & (sx >= 0) & (sx < w)
        sy, sx = np.where(ok, sy, 0), np.where(ok, sx, 0)
        ok &= ~hueco[sy, sx]
        peso = (fu[py] if a else 1.0 - fu[py]) * (fv[px] if b else 1.0 - fv[px])
        peso = np.where(ok, peso, 0.0).astype(np.float32)
        acumulado += peso[:, None] * detalle[sy, sx]
        pesos.append(peso)
        etiquetas.append(np.where(ok, lab, -1))
    norma2 = pesos[0] * pesos[0] + pesos[1] * pesos[1] + pesos[2] * pesos[2] + pesos[3] * pesos[3]
    for i in range(4):
        for j in range(i + 1, 4):
            norma2 += 2.0 * pesos[i] * pesos[j] * ((etiquetas[i] == etiquetas[j]) & (etiquetas[i] >= 0))
    hay = norma2 > 1e-8
    salida[py[hay], px[hay]] = acumulado[hay] / np.sqrt(norma2[hay])[:, None]
    return salida


def _ruido_de_reserva(detalle: np.ndarray, hueco: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Si no hay de dónde copiar parches: ruido con el desvío del detalle conocido."""
    conocido = ~hueco
    if not conocido.any():
        return np.zeros_like(detalle)
    sigma = detalle[conocido].std(axis=0).astype(np.float32)
    return rng.standard_normal(hueco.shape + (1,)).astype(np.float32) * sigma


def _suma_ventanas(integral: np.ndarray, ys: np.ndarray, xs: np.ndarray, t: int) -> np.ndarray:
    """Suma de la máscara en las ventanas txt con esquina (ys, xs) (arreglos que se difunden)."""
    return integral[ys + t, xs + t] - integral[ys, xs + t] - integral[ys + t, xs] + integral[ys, xs]


def _a_reducida(v: np.ndarray, escala: float, limite: int) -> np.ndarray:
    return np.clip(np.round((v + 0.5) * escala - 0.5).astype(np.int64), 0, limite - 1)


def _textura_por_parches(detalle: np.ndarray, hueco: np.ndarray, guia_chica: np.ndarray,
                         escala: tuple[float, float], rng: np.random.Generator) -> np.ndarray:
    """Detalle fino para huecos finos (cables, rayones): parches del entorno.

    Grilla de parches TxT con solapamiento del 50 % y ventanas sen² (suman 1);
    cada parche toma, entre las ventanas libres de la banda alrededor, una al
    azar de las ``ELEGIBLES`` más parecidas en color de base (y cercanas). Se
    mezclan conservando la varianza (Σwᵢpᵢ / √Σwᵢ²).
    """
    h, w = hueco.shape
    hs, ws = guia_chica.shape[:2]
    ey, ex = escala
    f = min(ey, ex)
    t = min(_lado_parche(f), (min(h, w) // 2) & ~1)
    if t < 8:
        return _ruido_de_reserva(detalle, hueco, rng)
    paso = t // 2

    # Destinos: grilla con paso t/2 que cubre el hueco (esquinas en coordenadas del recorte).
    filas, columnas = np.nonzero(hueco.any(axis=1))[0], np.nonzero(hueco.any(axis=0))[0]
    dys = np.arange(filas[0] - t + 1, filas[-1] + 1, paso)
    dxs = np.arange(columnas[0] - t + 1, columnas[-1] + 1, paso)
    integral_pad = cv2.integral(np.pad(hueco.astype(np.uint8), t))
    ty, tx = np.nonzero(_suma_ventanas(integral_pad, dys[:, None] + t, dxs[None, :] + t, t) > 0)
    ty, tx = dys[ty], dxs[tx]

    # Fuentes: ventanas txt libres, lejos del borde que el reescalado contamina.
    borde = int(math.ceil(1.0 / f)) + 1
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * borde + 1, 2 * borde + 1))
    integral_excl = cv2.integral(cv2.dilate(hueco.astype(np.uint8), k))
    paso_fuente = max(2, t // 4)
    ys = np.arange(0, h - t + 1, paso_fuente)
    xs = np.arange(0, w - t + 1, paso_fuente)
    fy, fx = np.nonzero(_suma_ventanas(integral_excl, ys[:, None], xs[None, :], t) == 0)
    if fy.size == 0:
        return _ruido_de_reserva(detalle, hueco, rng)
    fy, fx = ys[fy], xs[fx]
    if fy.size > CANDIDATOS_MAX:
        elegidos = rng.choice(fy.size, CANDIDATOS_MAX, replace=False)
        fy, fx = fy[elegidos], fx[elegidos]
    k_guia = max(1, int(round(t * f)))
    guia = cv2.blur(guia_chica, (k_guia, k_guia), borderType=cv2.BORDER_REFLECT)

    def rasgos(yy, xx):
        return guia[_a_reducida(yy + t / 2.0, ey, hs), _a_reducida(xx + t / 2.0, ex, ws)]

    rasgo_f = rasgos(fy, fx)
    pos_f = np.stack([fy, fx], axis=1).astype(np.float32) / t
    n_eleg = min(ELEGIBLES, fy.size)
    fuente_y = np.empty(ty.size, np.int64)
    fuente_x = np.empty(ty.size, np.int64)
    for i0 in range(0, ty.size, 1024):
        sl = slice(i0, i0 + 1024)
        dc = ((rasgos(ty[sl], tx[sl])[:, None, :] - rasgo_f[None, :, :]) ** 2).sum(-1)
        pos_d = np.stack([ty[sl], tx[sl]], axis=1).astype(np.float32) / t
        dd = ((pos_d[:, None, :] - pos_f[None, :, :]) ** 2).sum(-1)
        costo = dc + (PESO_DISTANCIA ** 2) * dd
        mejores = np.argpartition(costo, n_eleg - 1, axis=1)[:, :n_eleg]
        j = mejores[np.arange(mejores.shape[0]), rng.integers(0, n_eleg, mejores.shape[0])]
        fuente_y[sl], fuente_x[sl] = fy[j], fx[j]

    v = np.sin(np.pi * (np.arange(t) + 0.5) / t) ** 2
    peso = np.outer(v, v).astype(np.float32)
    peso3 = peso[..., None]
    peso2 = peso * peso
    acumulado = np.zeros((h + 2 * t, w + 2 * t, 3), np.float32)
    acumulado_w2 = np.zeros((h + 2 * t, w + 2 * t), np.float32)
    for y, x, sy, sx in zip((ty + t).tolist(), (tx + t).tolist(), fuente_y.tolist(), fuente_x.tolist()):
        acumulado[y:y + t, x:x + t] += peso3 * detalle[sy:sy + t, sx:sx + t]
        acumulado_w2[y:y + t, x:x + t] += peso2
    acumulado = acumulado[t:t + h, t:t + w]
    norma = np.sqrt(np.maximum(acumulado_w2[t:t + h, t:t + w], 1e-6))
    return acumulado / norma[..., None]


def _sintetizar(rgb: np.ndarray, hueco: np.ndarray, textura: float, rng: np.random.Generator
                ) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Relleno float32 de la caja del hueco dentro del recorte ``rgb``.

    Devuelve (relleno, (y0, y1, x0, x1)): el relleno cubre solo la caja que
    encierra el hueco (es lo único que se va a escribir).
    """
    caja = _caja_del_hueco(hueco)
    y0, y1, x0, x1 = caja
    img = rgb.astype(np.float32)
    if hueco.all():
        return img, caja
    h, w = hueco.shape
    f = _factor(int(np.count_nonzero(hueco)))
    hs, ws = max(1, round(h * f)), max(1, round(w * f))
    if min(hs, ws) < 2 * LADO_EM:
        # Recorte diminuto: Telea directo, sin banda de detalle.
        return _inpaint_float(img, hueco)[y0:y1, x0:x1], caja
    escala = (hs / h, ws / w)
    chico = cv2.resize(img, (ws, hs), interpolation=cv2.INTER_AREA)
    # Un píxel reducido es hueco si cubre aunque sea parte del hueco: así el
    # color del objeto no se cuela en la base.
    hueco_chico = cv2.resize(hueco.astype(np.float32), (ws, hs), interpolation=cv2.INTER_AREA) > 1e-4
    if hueco_chico.all():
        return _inpaint_float(img, hueco)[y0:y1, x0:x1], caja
    area_chica = int(np.count_nonzero(hueco_chico))
    cy0, cy1, cx0, cx1 = _caja_del_hueco(hueco_chico)
    caja_chica = (cy1 - cy0 + 2 * LADO_EM) * (cx1 - cx0 + 2 * LADO_EM)
    fino = (area_chica < EM_MIN_PIX or area_chica < COMPACIDAD_MIN * caja_chica
            or _espesor(hueco_chico) <= ESPESOR_FINO)
    if fino:
        # Manchita, cable, rayón: la difusión alcanza para la base, y el EM
        # sería caro (trabaja sobre la caja que encierra el hueco, que en una
        # línea larga en diagonal es enorme).
        base_chica, etiqueta, d = _inpaint_float(chico, hueco_chico), None, None
    else:
        base_chica, etiqueta, d = _por_desplazamientos(chico, hueco_chico, rng)
    base = cv2.resize(base_chica, (w, h), interpolation=cv2.INTER_CUBIC)
    relleno = base[y0:y1, x0:x1]
    if textura <= 0:
        return relleno, caja
    detalle = cv2.subtract(img, base)
    if fino:
        sintetico = _textura_por_parches(detalle, hueco, base_chica, escala, rng)[y0:y1, x0:x1]
    else:
        sintetico = _detalle_por_etiquetas(detalle, hueco, etiqueta, d, escala, caja)
    return relleno + np.float32(textura) * sintetico, caja


def rellenar(rgb: np.ndarray, mascara: np.ndarray, *, dilatar: Optional[float] = None,
             textura: float = 1.0, semilla: Optional[int] = 0) -> np.ndarray:
    """Borra lo marcado en ``mascara`` rellenándolo con lo de alrededor.

    * ``rgb``: uint8 HxWx3 (no se modifica).
    * ``mascara``: HxW float 0..1 (1 = borrar; admite borde suave), bool o uint8 0..255.
    * ``dilatar``: píxeles que se agranda el núcleo (≥ 0,5) para tapar el borde
      del objeto. ``None`` = 6 px a 12 MP, proporcional al tamaño de la foto.
    * ``textura``: cuánto detalle fino del entorno se repone (0 = solo la
      banda reducida, más lisa; 1 = como el entorno; > 1 lo exagera).
    * ``semilla``: azar de la muestra de parches (fija = resultado repetible;
      ``None`` = distinto cada vez).

    Técnica: EM de parches sobre desplazamientos candidatos, de grueso a fino,
    a resolución reducida + detalle fino copiado a resolución completa con los
    mismos desplazamientos (ver el docstring del módulo). Costo ≈ 0,65 s para
    una máscara del 5 % de una foto de 12 MP.
    Devuelve un uint8 nuevo del mismo tamaño; fuera de la zona marcada
    (dilatada) la imagen queda idéntica. Máscara vacía (o que tapa toda la
    foto: no hay de dónde copiar) → copia igual.
    """
    _validar_rgb(rgb)
    m = _validar_mascara(mascara, rgb.shape[:2])
    nivel = _numero(textura, "textura")
    if nivel < 0:
        raise ValueError(f"textura no puede ser negativa (vino {textura!r})")
    h, w = rgb.shape[:2]
    salida = rgb.copy()
    zona = _preparar(m, _radio_dilatacion(dilatar, h, w))
    if zona is None:
        return salida
    if (zona.y0, zona.y1, zona.x0, zona.x1) == (0, h, 0, w) and zona.hueco.all():
        return salida  # no queda nada alrededor de donde sacar el relleno
    rng = np.random.default_rng(semilla)
    for gy0, gy1, gx0, gx1 in _grupos(zona, h, w):
        # Hueco y alfa del grupo, en coordenadas del recorte.
        hueco = np.zeros((gy1 - gy0, gx1 - gx0), bool)
        alfa = np.zeros((gy1 - gy0, gx1 - gx0), np.float32)
        iy0, iy1 = max(gy0, zona.y0), min(gy1, zona.y1)
        ix0, ix1 = max(gx0, zona.x0), min(gx1, zona.x1)
        if iy0 >= iy1 or ix0 >= ix1:
            continue
        origen = (slice(iy0 - zona.y0, iy1 - zona.y0), slice(ix0 - zona.x0, ix1 - zona.x0))
        destino = (slice(iy0 - gy0, iy1 - gy0), slice(ix0 - gx0, ix1 - gx0))
        hueco[destino] = zona.hueco[origen]
        alfa[destino] = zona.alfa[origen]
        if not hueco.any():
            continue
        relleno, (y0, y1, x0, x1) = _sintetizar(rgb[gy0:gy1, gx0:gx1], hueco, nivel, rng)
        # Mezcla con el original según alfa, solo sobre la caja del hueco; se
        # escriben únicamente los píxeles del hueco (el resto queda idéntico).
        region = (slice(gy0 + y0, gy0 + y1), slice(gx0 + x0, gx0 + x1))
        original = rgb[region].astype(np.float32)
        a = alfa[y0:y1, x0:x1]
        mezcla = cv2.add(original, cv2.multiply(cv2.subtract(relleno, original), cv2.merge([a, a, a])))
        nuevo = np.clip(mezcla + 0.5, 0, 255).astype(np.uint8)
        np.copyto(salida[region], nuevo, where=hueco[y0:y1, x0:x1, None])
    return salida


# ----------------------------------------------------------------- clonar
def _tomar(img: np.ndarray, y0: int, y1: int, x0: int, x1: int) -> np.ndarray:
    """Recorte [y0:y1, x0:x1] que puede salirse de la foto (se repite el borde)."""
    h, w = img.shape[:2]
    if y0 >= 0 and x0 >= 0 and y1 <= h and x1 <= w:
        return np.ascontiguousarray(img[y0:y1, x0:x1])
    ys = np.clip(np.arange(y0, y1), 0, h - 1)
    xs = np.clip(np.arange(x0, x1), 0, w - 1)
    return img[ys[:, None], xs[None, :]]


def clonar(rgb: np.ndarray, mascara: np.ndarray, desplazamiento_xy: Sequence[float], *,
           sin_costuras: bool = True, dilatar: Optional[float] = None) -> np.ndarray:
    """Tampón de clonar / corrector: copia en la zona marcada lo que hay desplazado.

    * ``desplazamiento_xy``: (dx, dy) en píxeles de ``rgb``, de la zona marcada a
      la fuente: el píxel (x, y) toma el contenido de (x + dx, y + dy). Se
      redondea a entero.
    * ``sin_costuras``: True = mezcla en el dominio del gradiente
      (``cv2.seamlessClone`` NORMAL_CLONE: textura de la fuente, color y luz del
      borde del destino); False = copia directa con el borde fundido.
    * ``dilatar``: como en ``rellenar``.

    Si parte de la fuente cae fuera de la foto, esa parte del destino queda sin
    cambios (el corte se funde); si cae toda afuera o el desplazamiento es
    (0, 0), devuelve una copia igual. No modifica la entrada.
    """
    _validar_rgb(rgb)
    m = _validar_mascara(mascara, rgb.shape[:2])
    dx, dy = _validar_desplazamiento(desplazamiento_xy)
    h, w = rgb.shape[:2]
    salida = rgb.copy()
    if (dx == 0 and dy == 0) or abs(dx) >= w or abs(dy) >= h:
        return salida
    radio = _radio_dilatacion(dilatar, h, w)
    zona = _preparar(m, radio)
    if zona is None:
        return salida

    # Solo vale el destino cuya fuente cae dentro de la foto.
    fy = np.arange(zona.y0, zona.y1) + dy
    fx = np.arange(zona.x0, zona.x1) + dx
    valida = ((fy >= 0) & (fy < h))[:, None] & ((fx >= 0) & (fx < w))[None, :]
    hueco, alfa = zona.hueco, zona.alfa
    if not valida.all():
        alfa = alfa * _rampa(valida, max(0.7, radio / 3.0))
        hueco = hueco & valida & (alfa > 0)
    if not hueco.any():
        return salida

    filas, columnas = np.nonzero(hueco.any(axis=1))[0], np.nonzero(hueco.any(axis=0))[0]
    by0, by1, bx0, bx1 = filas[0], filas[-1] + 1, columnas[0], columnas[-1] + 1
    # seamlessClone erosiona la máscara 3 px por dentro (3 pasadas de 3x3) y
    # anula su anillo exterior de 1 px: se le pasa el hueco dilatado
    # ``EROSION_CV + 1`` px y el recorte lleva margen para eso.
    p = EROSION_CV + 4
    wy0, wy1 = zona.y0 + by0 - p, zona.y0 + by1 + p
    wx0, wx1 = zona.x0 + bx0 - p, zona.x0 + bx1 + p
    destino = _tomar(rgb, wy0, wy1, wx0, wx1)
    fuente = _tomar(rgb, wy0 + dy, wy1 + dy, wx0 + dx, wx1 + dx)
    hueco_c = np.zeros(destino.shape[:2], bool)
    hueco_c[p:-p, p:-p] = hueco[by0:by1, bx0:bx1]
    alfa_c = np.zeros(destino.shape[:2], np.float32)
    alfa_c[p:-p, p:-p] = alfa[by0:by1, bx0:bx1]

    mezcla = fuente
    if sin_costuras:
        lado_k = 2 * (EROSION_CV + 1) + 1
        mascara_cv = cv2.dilate(hueco_c.astype(np.uint8), np.ones((lado_k, lado_k), np.uint8)) * 255
        x, y, bw, bh = cv2.boundingRect(mascara_cv)
        try:
            # seamlessClone modifica la máscara que recibe: va una propia.
            mezcla = cv2.seamlessClone(fuente, destino, mascara_cv, (x + bw // 2, y + bh // 2),
                                       cv2.NORMAL_CLONE)
        except cv2.error:
            mezcla = fuente  # zona degenerada (1 px, etc.): copia directa

    # Composición con alfa, solo sobre los píxeles del hueco (todos dentro de la foto).
    sl = (slice(p, -p), slice(p, -p))
    region = salida[zona.y0 + by0:zona.y0 + by1, zona.x0 + bx0:zona.x0 + bx1]
    hc = hueco_c[sl]
    original = destino[sl][hc].astype(np.float32)
    a = alfa_c[sl][hc][:, None]
    nuevo = original + a * (mezcla[sl][hc].astype(np.float32) - original)
    region[hc] = np.clip(nuevo + 0.5, 0, 255).astype(np.uint8)
    return salida
