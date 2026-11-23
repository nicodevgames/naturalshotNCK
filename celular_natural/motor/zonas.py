"""Zonas de capa y recorte, ambos no destructivos.

Las coordenadas se guardan normalizadas (0..1) respecto de la foto BASE
completa: la original ya girada, volteada y enderezada (``geometria``), sin
recortar. Es lo que el usuario ve y marca. Así valen igual para la vista previa
reducida y para la exportación, y una zona no se desplaza si después se cambia
el recorte. Si cambia la geometría, ``edicion.convertir_zona`` lleva cada zona
al marco nuevo con ``transformar_zona`` (queda sobre el mismo objeto).

* ``Zona``: limita una capa a un rectángulo, una elipse o una forma libre
  (lazo a mano o poligonal, definida por sus puntos). El borde se funde de
  forma gradual (``pluma``) para que no quede un corte visible.
  También puede ser **pintada a mano** (``pincel``): se guardan los trazos
  (puntos, radio, dureza, si borra) y se rasterizan al tamaño de cada salida.
  O una **máscara raster** (``mascara``: cielo, piel o el contorno ajustado de
  un objeto), guardada como PNG compacto (``seleccion_auto.codificar_mascara``)
  más una matriz afín que la ubica en la foto. Encima se pueden sumar o restar
  trazos de pincel para corregirla.
* ``Recorte``: rectángulo de la foto que se conserva. Se aplica antes de
  procesar, así los efectos de lente (viñeteo, bordes) siguen al encuadre final.

Costo: una máscara es una operación vectorizada sobre la imagen (≈0,1 s a 12 MP).
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Optional

import cv2
import numpy as np

FORMAS = ("rect", "elipse", "lazo", "poligono", "pincel", "mascara")
FORMAS_LIBRES = ("lazo", "poligono")  # se definen por sus puntos
# De dónde sale una zona "mascara" (para mostrarla y describirla en el historial).
ORIGENES_MASCARA = {"cielo": "Cielo", "piel": "Piel", "contorno": "Contorno ajustado"}


@dataclass(frozen=True)
class Recorte:
    x0: float
    y0: float
    x1: float
    y1: float

    def normalizado(self) -> "Recorte":
        x0, x1 = sorted((min(max(self.x0, 0.0), 1.0), min(max(self.x1, 0.0), 1.0)))
        y0, y1 = sorted((min(max(self.y0, 0.0), 1.0), min(max(self.y1, 0.0), 1.0)))
        return Recorte(x0, y0, x1, y1)

    def pixeles(self, w: int, h: int) -> tuple[int, int, int, int]:
        """Límites en píxeles (x0, y0, x1, y1), con al menos 1 px de lado."""
        r = self.normalizado()
        x0 = min(int(round(r.x0 * w)), w - 1)
        y0 = min(int(round(r.y0 * h)), h - 1)
        x1 = max(int(round(r.x1 * w)), x0 + 1)
        y1 = max(int(round(r.y1 * h)), y0 + 1)
        return x0, y0, x1, y1

    def es_completo(self) -> bool:
        r = self.normalizado()
        return r.x0 <= 0.0 and r.y0 <= 0.0 and r.x1 >= 1.0 and r.y1 >= 1.0


@dataclass(frozen=True)
class Zona:
    forma: str  # "rect" | "elipse" | "lazo" | "poligono" | "pincel" | "mascara"
    x0: float
    y0: float
    x1: float
    y1: float
    pluma: int = 35  # 0..100: ancho del borde suave
    invertir: bool = False
    puntos: tuple[tuple[float, float], ...] = ()  # contorno de las formas libres
    # Pincel: trazos (puntos, radio, dureza, borrar) en orden. El radio es relativo
    # al lado largo de la foto base; la dureza va de 0 (muy suave) a 100 (dura).
    # En una "mascara" son las correcciones con el pincel encima de la máscara.
    trazos: tuple[tuple[tuple[tuple[float, float], ...], float, int, bool], ...] = ()
    # Máscara raster: bytes de ``codificar_mascara`` (PNG gris de 8 bits) y la
    # matriz afín que lleva sus coordenadas normalizadas a las de la foto base
    # (las dos primeras filas de la 3x3, por filas; vacía = identidad). Al girar
    # la foto solo cambia la matriz: la máscara no se vuelve a muestrear.
    datos: bytes = b""
    matriz: tuple[float, ...] = ()
    origen: str = ""  # "cielo" | "piel" | "contorno" (ver ``ORIGENES_MASCARA``)

    @staticmethod
    def desde_mascara(mascara: np.ndarray, origen: str = "", pluma: int = 0,
                      invertir: bool = False) -> "Zona":
        """Zona raster a partir de una máscara float 0..1 (de cualquier resolución).

        La guarda compacta (PNG de lado ≤ 1024) y registra la versión completa
        para que la exportación use el borde a resolución completa.
        """
        from .seleccion_auto import codificar_mascara

        m = np.clip(np.asarray(mascara, dtype=np.float32), 0.0, 1.0)
        datos = codificar_mascara(m)
        registrar_mascara(datos, m)
        x0, y0, x1, y1 = _caja_mascara(m)
        return Zona("mascara", x0, y0, x1, y1, pluma, invertir, datos=datos, origen=origen)

    @staticmethod
    def desde_puntos(forma: str, puntos, pluma: int = 35, invertir: bool = False) -> "Zona":
        pts = tuple((float(x), float(y)) for x, y in puntos)
        xs, ys = [x for x, _ in pts], [y for _, y in pts]
        return Zona(forma, min(xs), min(ys), max(xs), max(ys), pluma, invertir, pts)

    @staticmethod
    def desde_trazos(trazos, pluma: int = 35, invertir: bool = False, aspecto: float = 1.0) -> "Zona":
        """``aspecto``: ancho / alto de la foto original (solo para el recuadro)."""
        tr = tuple((tuple((float(x), float(y)) for x, y in pts), float(radio), int(dureza), bool(borrar))
                   for pts, radio, dureza, borrar in trazos if len(pts))
        # El recuadro abarca lo pintado (sirve para ubicar la etiqueta en la vista).
        pintados = [t for t in tr if not t[3]] or tr
        if not pintados:
            return Zona("pincel", 0.0, 0.0, 0.0, 0.0, pluma, invertir, (), tr)
        fx, fy = max(1.0, 1.0 / aspecto), max(1.0, aspecto)  # el radio es relativo al lado largo
        x0 = min(x - r * fx for pts, r, _d, _b in pintados for x, _y in pts)
        y0 = min(y - r * fy for pts, r, _d, _b in pintados for _x, y in pts)
        x1 = max(x + r * fx for pts, r, _d, _b in pintados for x, _y in pts)
        y1 = max(y + r * fy for pts, r, _d, _b in pintados for _x, y in pts)
        return Zona("pincel", x0, y0, x1, y1, pluma, invertir, (), tr)

    @property
    def es_libre(self) -> bool:
        return self.forma in FORMAS_LIBRES and len(self.puntos) >= 3

    @property
    def es_pincel(self) -> bool:
        return self.forma == "pincel"

    @property
    def es_mascara(self) -> bool:
        return self.forma == "mascara"

    @property
    def es_raster(self) -> bool:
        """Pintada o máscara: el borde no sale de ``pluma`` y se dibuja por su contorno."""
        return self.forma in ("pincel", "mascara")

    def matriz_3x3(self) -> np.ndarray:
        """Matriz de la máscara raster (identidad si no tiene)."""
        if len(self.matriz) != 6:
            return np.eye(3)
        return np.vstack([np.asarray(self.matriz, np.float64).reshape(2, 3), [0.0, 0.0, 1.0]])

    def normalizada(self) -> "Zona":
        x0, x1 = sorted((self.x0, self.x1))
        y0, y1 = sorted((self.y0, self.y1))
        return replace(self, x0=x0, y0=y0, x1=x1, y1=y1)


def _caja_mascara(m: np.ndarray) -> tuple[float, float, float, float]:
    """Recuadro normalizado de lo marcado en una máscara (vacía = todo en 0)."""
    h, w = m.shape[:2]
    for umbral in (0.5, 0.02):
        filas = np.flatnonzero(m.max(axis=1) >= umbral)
        if filas.size:
            cols = np.flatnonzero(m.max(axis=0) >= umbral)
            return cols[0] / w, filas[0] / h, (cols[-1] + 1) / w, (filas[-1] + 1) / h
    return 0.0, 0.0, 0.0, 0.0


# ---------------------------------------------------------------------------
# Máscaras raster: versión completa en memoria y lectura de los bytes
# ---------------------------------------------------------------------------

_ALTA: "OrderedDict[bytes, np.ndarray]" = OrderedDict()  # bytes -> máscara completa uint8
_MAX_ALTA = 6
_CANDADO_ALTA = threading.Lock()


def registrar_mascara(datos: bytes, mascara: np.ndarray) -> None:
    """Guarda en memoria la máscara completa que corresponde a ``datos``.

    En el historial va la versión compacta (lado ≤ 1024); mientras la app esté
    abierta, la exportación a 12 MP usa esta, con el borde a resolución completa.
    """
    m = np.asarray(mascara)
    if m.dtype == np.uint8:
        u8 = m
    else:
        u8 = (np.clip(m.astype(np.float32), 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    with _CANDADO_ALTA:
        _ALTA[datos] = u8
        _ALTA.move_to_end(datos)
        while len(_ALTA) > _MAX_ALTA:
            _ALTA.popitem(last=False)


def _alta(datos: bytes) -> Optional[np.ndarray]:
    with _CANDADO_ALTA:
        return _ALTA.get(datos)


def mascara_registrada(datos: bytes) -> Optional[np.ndarray]:
    """La máscara completa (uint8) registrada para ``datos``, o None."""
    return _alta(datos)


@lru_cache(maxsize=16)
def _decodificada(datos: bytes) -> np.ndarray:
    """La máscara guardada (uint8, a su tamaño compacto). Solo lectura."""
    u8 = cv2.imdecode(np.frombuffer(datos, np.uint8), cv2.IMREAD_GRAYSCALE)
    if u8 is None:
        raise ValueError("datos de máscara inválidos")
    u8.flags.writeable = False
    return u8


def _mapa_raster(m: np.ndarray, rh: int, rw: int, h: int, w: int) -> np.ndarray:
    """Matriz 3x3 de píxeles de la máscara (rh x rw) a píxeles de la salida (h x w), con el
    centro de cada píxel en coordenadas enteras como usa OpenCV. ``m``: normalizada -> normalizada."""
    t = np.diag([w, h, 1.0]) @ m @ np.diag([1.0 / rw, 1.0 / rh, 1.0])
    return np.array([[1, 0, -0.5], [0, 1, -0.5], [0, 0, 1.0]]) @ t @ np.array([[1, 0, 0.5], [0, 1, 0.5], [0, 0, 1.0]])


def raster_zona(zona: Zona, h: int, w: int, recorte: Optional[Recorte] = None) -> np.ndarray:
    """La máscara raster de una zona "mascara" (sin trazos ni invertir), float32 HxW 0..1,
    llevada al encuadre (``recorte``) y al tamaño pedido en una sola interpolación."""
    m = zona.matriz_3x3()
    if recorte is not None and not recorte.es_completo():
        r = recorte.normalizado()
        aw, ah = max(r.x1 - r.x0, 1e-6), max(r.y1 - r.y0, 1e-6)
        m = np.array([[1 / aw, 0, -r.x0 / aw], [0, 1 / ah, -r.y0 / ah], [0, 0, 1.0]]) @ m
    fuente = _decodificada(zona.datos)
    alta = _alta(zona.datos)
    if alta is not None:
        # La completa solo si la salida es más grande que la versión guardada.
        t = _mapa_raster(m, *fuente.shape, h, w)
        if abs(np.linalg.det(t[:2, :2])) > 1.1:
            fuente = alta
    rh, rw = fuente.shape
    t = _mapa_raster(m, rh, rw, h, w)
    escala = float(np.sqrt(abs(np.linalg.det(t[:2, :2]))))
    if escala < 0.7:
        # Mucho más chica: se reduce antes por área (sin serrucho) y se ubica después.
        nw, nh = max(1, round(rw * escala)), max(1, round(rh * escala))
        fuente = cv2.resize(fuente, (nw, nh), interpolation=cv2.INTER_AREA)
        rh, rw = fuente.shape
        t = _mapa_raster(m, rh, rw, h, w)
    if (rh, rw) == (h, w) and np.allclose(t, np.eye(3), atol=1e-9):
        salida = np.array(fuente)
    else:
        salida = cv2.warpAffine(np.ascontiguousarray(fuente), t[:2], (int(w), int(h)), flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    return salida.astype(np.float32) * np.float32(1.0 / 255.0)


def transformar_zona(zona: Zona, m, factor_radio: float = 1.0, aspecto: float = 1.0) -> Zona:
    """Lleva una zona a otro marco con la matriz afín ``m`` (3x3, de coordenadas
    normalizadas del marco viejo a las del nuevo; ver ``edicion.matriz_cambio``).

    * Rectángulo y elipse siguen siéndolo si ``m`` no los tuerce (giros de 90° y
      volteos); si los tuerce (enderezar), pasan a polígono con la misma forma.
    * Lazo y polígono: se transforman sus puntos.
    * Pincel: se transforman los puntos de los trazos y el radio se multiplica
      por ``factor_radio`` (lado largo viejo / lado largo nuevo: los radios son
      relativos al lado largo del marco). ``aspecto``: ancho / alto del marco nuevo.
    * Máscara: se compone su matriz (sin volver a muestrear) y sus trazos se
      transforman como los del pincel.
    """
    m = np.asarray(m, dtype=np.float64)

    def llevar(puntos) -> tuple[tuple[float, float], ...]:
        p = np.asarray(puntos, dtype=np.float64).reshape(-1, 2)
        q = p @ m[:2, :2].T + m[:2, 2]
        return tuple((float(x), float(y)) for x, y in q)

    z = zona.normalizada()
    trazos = tuple((llevar(pts), float(radio) * factor_radio, dureza, borrar)
                   for pts, radio, dureza, borrar in z.trazos)
    if z.es_pincel:
        return Zona.desde_trazos(trazos, z.pluma, z.invertir, aspecto)
    esquinas = llevar([(z.x0, z.y0), (z.x1, z.y0), (z.x1, z.y1), (z.x0, z.y1)])
    xs, ys = [x for x, _ in esquinas], [y for _, y in esquinas]
    if z.es_mascara:
        matriz = m @ z.matriz_3x3()
        return replace(z, x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys), trazos=trazos,
                       matriz=tuple(float(v) for v in matriz[:2].ravel()))
    if z.es_libre:
        return Zona.desde_puntos(z.forma, llevar(z.puntos), z.pluma, z.invertir)
    alineada = ((abs(m[0, 1]) < 1e-9 and abs(m[1, 0]) < 1e-9)
                or (abs(m[0, 0]) < 1e-9 and abs(m[1, 1]) < 1e-9))
    if alineada:
        return replace(z, x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys), puntos=())
    if z.forma == "elipse":
        t = np.linspace(0.0, 2.0 * np.pi, 72, endpoint=False)
        cx, cy, rx, ry = (z.x0 + z.x1) / 2, (z.y0 + z.y1) / 2, (z.x1 - z.x0) / 2, (z.y1 - z.y0) / 2
        contorno = np.column_stack([cx + rx * np.cos(t), cy + ry * np.sin(t)])
    else:
        contorno = [(z.x0, z.y0), (z.x1, z.y0), (z.x1, z.y1), (z.x0, z.y1)]
    return Zona.desde_puntos("poligono", llevar(contorno), z.pluma, z.invertir)


def aplicar_recorte(img: np.ndarray, recorte: Optional[Recorte]) -> np.ndarray:
    """Devuelve la parte recortada (una vista, sin copiar). Sin recorte, la imagen tal cual."""
    if recorte is None or recorte.es_completo():
        return img
    h, w = img.shape[:2]
    x0, y0, x1, y1 = recorte.pixeles(w, h)
    return img[y0:y1, x0:x1]


def _a_marco(zona: Zona, recorte: Optional[Recorte]) -> Zona:
    """Pasa la zona de coordenadas de la foto original a las del encuadre recortado."""
    z = zona.normalizada()
    if recorte is None or recorte.es_completo():
        return z
    r = recorte.normalizado()
    ancho, alto = max(r.x1 - r.x0, 1e-6), max(r.y1 - r.y0, 1e-6)
    puntos = tuple(((x - r.x0) / ancho, (y - r.y0) / alto) for x, y in z.puntos)
    # Los radios del pincel no cambian: son relativos a la foto original.
    trazos = tuple((tuple(((x - r.x0) / ancho, (y - r.y0) / alto) for x, y in pts), radio, dureza, borrar)
                   for pts, radio, dureza, borrar in z.trazos)
    return replace(z, x0=(z.x0 - r.x0) / ancho, x1=(z.x1 - r.x0) / ancho,
                   y0=(z.y0 - r.y0) / alto, y1=(z.y1 - r.y0) / alto, puntos=puntos, trazos=trazos)


def _lado_original(h: int, w: int, recorte: Optional[Recorte]) -> float:
    """Lado largo de la foto original, medido en píxeles de este encuadre."""
    if recorte is None or recorte.es_completo():
        return float(max(h, w))
    r = recorte.normalizado()
    return max(w / max(r.x1 - r.x0, 1e-6), h / max(r.y1 - r.y0, 1e-6))


def alfa_trazo(puntos_px, radio_px: float, dureza: int, h: int, w: int):
    """Opacidad (0..1) de un trazo de pincel, calculada solo en su recuadro.

    Sale de la distancia de cada píxel a la línea del trazo: 1 hasta
    ``radio * dureza``, y de ahí cae suave hasta 0 en el radio. Un trazo entero
    da lo mismo que la unión de sus tramos, así que se puede pintar de a poco.
    Devuelve (filas, columnas, alfa) o None si el trazo queda fuera de la imagen.
    """
    pts = np.asarray(puntos_px, dtype=np.float64).reshape(-1, 2)
    r = max(float(radio_px), 0.5)
    margen = int(np.ceil(r)) + 2
    # El lienzo puede salirse un radio de la imagen: un trazo pintado justo afuera
    # del borde igual alcanza a pintar adentro.
    x0 = max(int(np.floor(pts[:, 0].min())) - margen, -margen)
    y0 = max(int(np.floor(pts[:, 1].min())) - margen, -margen)
    x1 = min(int(np.ceil(pts[:, 0].max())) + margen + 1, w + margen)
    y1 = min(int(np.ceil(pts[:, 1].max())) + margen + 1, h + margen)
    if x0 >= min(x1, w) or y0 >= min(y1, h) or x1 <= 0 or y1 <= 0:
        return None
    # Línea de 1 px sobre fondo blanco: la transformada de distancia mide cuánto
    # dista cada píxel del centro del trazo. (El centro del píxel i está en i + 0,5.)
    lienzo = np.full((y1 - y0, x1 - x0), 255, np.uint8)
    rel = np.round((pts - (x0 + 0.5, y0 + 0.5)) * 16).astype(np.int32)
    if len(rel) == 1:
        rel = np.vstack([rel, rel])  # un clic sin mover: un punto
    cv2.polylines(lienzo, [rel.reshape(-1, 1, 2)], False, 0, 1, cv2.LINE_8, shift=4)
    if lienzo.min() > 0:
        return None  # la línea no pasa cerca de la imagen
    dist = cv2.distanceTransform(lienzo, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    # Solo la parte que cae dentro de la imagen.
    fx0, fy0, fx1, fy1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
    dist = dist[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0]
    ancho = max(r * (1.0 - max(0, min(100, dureza)) / 100.0), 1.0)
    t = np.clip((r + 0.5 - dist) / ancho, 0.0, 1.0)
    return slice(fy0, fy1), slice(fx0, fx1), (t * t * (3.0 - 2.0 * t)).astype(np.float32, copy=False)


def mascara_trazos(trazos, h: int, w: int, lado_px: float, inicial: Optional[np.ndarray] = None) -> np.ndarray:
    """Rasteriza trazos de pincel (coordenadas normalizadas de este encuadre).

    ``lado_px``: lado largo de la foto base en píxeles de este encuadre (los
    radios son relativos a él). Pintar suma con máximo; la goma multiplica.
    ``inicial``: máscara HxW de partida (por ejemplo, la del cielo que se corrige);
    sin ella se parte de cero. No se modifica.
    """
    if inicial is not None:
        m = np.array(inicial, dtype=np.float32, copy=True).reshape(h, w)
    else:
        m = np.zeros((h, w), np.float32)
    for puntos, radio, dureza, borrar in trazos:
        pts = np.asarray(puntos, dtype=np.float64).reshape(-1, 2) * (w, h)
        res = alfa_trazo(pts, radio * lado_px, dureza, h, w)
        if res is None:
            continue
        filas, cols, a = res
        if borrar:
            m[filas, cols] *= 1.0 - a
        else:
            np.maximum(m[filas, cols], a, out=m[filas, cols])
    return m


def mascara_zona(zona: Zona, h: int, w: int, recorte: Optional[Recorte] = None) -> np.ndarray:
    """Máscara float32 HxW en 0..1 (1 = la capa se aplica completa).

    El borde suave se calcula con la distancia al contorno, así que su ancho es
    igual en todos los lados y no depende de la resolución de la vista previa.
    """
    z = _a_marco(zona, recorte)
    if z.es_pincel or z.es_mascara:
        # El borde lo da la dureza de cada trazo o la propia máscara (no usa ``pluma``).
        inicial = raster_zona(zona, h, w, recorte) if z.es_mascara else None
        if z.trazos or inicial is None:
            mascara = mascara_trazos(z.trazos, h, w, _lado_original(h, w, recorte), inicial)
        else:
            mascara = inicial
        return 1.0 - mascara if z.invertir else mascara
    x0, x1, y0, y1 = z.x0 * w, z.x1 * w, z.y0 * h, z.y1 * h
    lado = max(min(x1 - x0, y1 - y0), 1.0)
    ancho_pluma = max(1.0, lado * 0.35 * max(0, min(100, z.pluma)) / 100.0)

    xs = np.arange(w, dtype=np.float32) + 0.5
    ys = np.arange(h, dtype=np.float32) + 0.5
    if z.es_libre:
        # Forma libre: se rasteriza el polígono y la distancia al contorno sale
        # de la transformada de distancia (adentro negativa, afuera positiva).
        pts = np.array([[x * w, y * h] for x, y in z.puntos], dtype=np.float64)
        binaria = np.zeros((h, w), np.uint8)
        cv2.fillPoly(binaria, [np.round(pts * 16).astype(np.int32)], 255, lineType=cv2.LINE_8, shift=4)
        adentro = cv2.distanceTransform(binaria, cv2.DIST_L2, 5)
        afuera = cv2.distanceTransform(255 - binaria, cv2.DIST_L2, 5)
        dist = afuera - adentro + np.where(binaria > 0, 0.5, -0.5).astype(np.float32)
    elif z.forma == "elipse":
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        rx, ry = max((x1 - x0) / 2, 0.5), max((y1 - y0) / 2, 0.5)
        nx = ((xs - cx) / rx)[None, :]
        ny = ((ys - cy) / ry)[:, None]
        radio = np.sqrt(nx * nx + ny * ny)
        # Distancia aproximada al borde de la elipse, en píxeles (negativa adentro).
        dist = (radio - 1.0) * min(rx, ry)
    else:
        dx = np.maximum(x0 - xs, xs - x1)[None, :]
        dy = np.maximum(y0 - ys, ys - y1)[:, None]
        afuera = np.sqrt(np.maximum(dx, 0) ** 2 + np.maximum(dy, 0) ** 2)
        adentro = np.minimum(np.maximum(dx, dy), 0)
        dist = afuera + adentro
    # Fundido centrado en el contorno: mitad adentro, mitad afuera.
    t = np.clip(0.5 - dist / ancho_pluma, 0.0, 1.0).astype(np.float32)
    mascara = t * t * (3.0 - 2.0 * t)
    if z.invertir:
        mascara = 1.0 - mascara
    return mascara.astype(np.float32, copy=False)
