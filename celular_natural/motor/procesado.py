"""Motor de simulación fotográfica "Celular natural".

Trabaja sobre la imagen original (RGB uint8, en el espacio de color de su perfil
ICC) y devuelve otra con exactamente las mismas dimensiones. No usa IA ni
modifica el contenido: solo cambia el carácter fotográfico.

Orden de operaciones (el de una cámara, de la luz al archivo)
-------------------------------------------------------------
Luz LINEAL (lo físico: luz que se suma y se multiplica):
    1. Exposición y balance de blancos, variación de balance (luz mezclada).
    2. Óptica: desenfoque (PSF) → distorsión → aberración cromática →
       pérdida de nitidez en bordes → viñeteo.
    3. Sensor: mosaico Bayer y demosaico.
    4. Tono local (HDR del teléfono).
Codificado (lo perceptual: curvas, color, detalle):
    5. Curva global: luces/sombras del procesado, caída de luces, pie de
       sombras, contraste, brillo por zonas.
    6. Saturación, desaturación de altas luces, respuesta de color de cámara.
    7. Detalle y texturas: claridad, microcontraste, nitidez, suavizado,
       nitidez variable, piel real (con máscaras regionales si están activas).
    8. Ruido residual de sensor (modelado en luz lineal, ver ``sensor.py``).
    9. Grano fotográfico.
Una sola vez al final de toda la pila de capas:
   10. Reescalado y JPEG simulados.

Precisión: entre etapas y entre capas todo es float32; se cuantiza a 8 bits
una única vez, al final. Las curvas usan tablas de 16 bits.

Todas las distancias se expresan respecto del lado largo de una foto de 12 MP
(4032 px), así la vista previa reducida y la exportación completa coinciden.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Callable, Optional, Sequence

import numpy as np

from . import compresion, grano as m_grano, optica, sensor, textura, tono
from .comun import LADO_REFERENCIA, codificar, decodificar
from .mascaras import REGIONES, regiones_en_cache
from .zonas import Recorte, Zona, mascara_zona

SEMILLA_RUIDO = 1313  # semilla base: la vista previa y la exportación coinciden


class Cancelado(Exception):
    """Se lanza cuando un procesamiento se cancela porque quedó obsoleto."""


@dataclass(frozen=True)
class Ajustes:
    """Parámetros del filtro. Enteros pensados para deslizadores (ver ``parametros.py``).

    Los efectos van de 0 a 100 (o de -100 a 100) y 0 los apaga. ``intensidad``
    escala todos los efectos a la vez. Cada sección tiene su interruptor.
    """

    intensidad: int = 100
    semilla: int = 0
    # Sensor
    sensor_activo: bool = True
    ruido: int = 0
    ruido_lectura: int = 50
    ruido_croma: int = 50
    ruido_correlacion: int = 30
    bayer: bool = False
    # Óptica
    optica_activa: bool = True
    desenfoque: int = 0
    distorsion: int = 0
    aberracion: int = 0
    bordes: int = 0
    vineteo: int = 0
    # Detalles
    detalle_activo: bool = True
    nitidez: int = 0
    microcontraste: int = 0
    claridad: int = 0
    nitidez_variable: int = 0
    # Texturas
    textura_activa: bool = True
    suavizado: int = 0
    piel: int = 0
    # Iluminación
    iluminacion_activa: bool = True
    tono: int = 0
    exposicion: int = 0
    contraste: int = 0
    luces: int = 0
    sombras: int = 0
    zona_sombras: int = 0
    zona_medios: int = 0
    zona_luces: int = 0
    # Color
    color_activo: bool = True
    temperatura: int = 0
    tinte: int = 0
    variacion_balance: int = 0
    saturacion: int = 0
    desat_luces: int = 0
    respuesta_camara: int = 0
    # Grano
    grano_activo: bool = True
    grano: int = 0
    grano_tam: int = 30
    grano_correlacion: int = 30
    grano_croma: int = 0
    grano_sombras: int = 100
    grano_medios: int = 100
    grano_luces: int = 60
    # Compresión
    compresion_activa: bool = True
    reescalado: int = 0
    reescalado_algoritmo: int = 1
    jpeg: int = 0
    submuestreo: bool = True
    # Máscaras regionales: multiplicador (%) de cada efecto en cada región
    regiones_activas: bool = False
    reg_piel_nitidez: int = 100
    reg_piel_suavizado: int = 100
    reg_piel_ruido: int = 100
    reg_piel_micro: int = 100
    reg_bordes_nitidez: int = 100
    reg_bordes_suavizado: int = 100
    reg_bordes_ruido: int = 100
    reg_bordes_micro: int = 100
    reg_alta_nitidez: int = 100
    reg_alta_suavizado: int = 100
    reg_alta_ruido: int = 100
    reg_alta_micro: int = 100
    reg_baja_nitidez: int = 100
    reg_baja_suavizado: int = 100
    reg_baja_ruido: int = 100
    reg_baja_micro: int = 100

    def como_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def nombres() -> list[str]:
        return [f.name for f in fields(Ajustes)]

    @staticmethod
    def desde_dict(datos: dict) -> "Ajustes":
        """Ignora campos desconocidos y completa los faltantes (presets viejos o nuevos)."""
        tipos = {f.name: f.type for f in fields(Ajustes)}
        limpio = {}
        for k, v in (datos or {}).items():
            if k not in tipos:
                continue
            limpio[k] = bool(v) if tipos[k] in (bool, "bool") else int(v)
        return Ajustes(**limpio)


NEUTRO = Ajustes()

PRESET_PRINCIPAL = "Celular natural — inspirado en iPhone 13"
PRESET_ANTI_IA = "Anti IA — piel real, sin calidad exagerada"


def _p(nit, micro, suav, ruido, tono_, expo, contraste, temp, tinte, sat, optica_, optica_activa=True,
       piel=0) -> Ajustes:
    """Presets clásicos. ``optica_`` reparte en aberración, bordes y viñeteo
    con la misma proporción que el control único de versiones anteriores."""
    return Ajustes(
        nitidez=nit, microcontraste=micro, suavizado=suav, piel=piel, ruido=ruido,
        tono=tono_, exposicion=expo, contraste=contraste, temperatura=temp, tinte=tinte,
        saturacion=sat, aberracion=optica_, bordes=optica_, vineteo=round(0.4 * optica_),
        optica_activa=optica_activa,
    )


def _perfil(**kw) -> Ajustes:
    return Ajustes(**kw)


# Grupos de presets en el orden en que se muestran. nombre -> (ajustes, descripción).
GRUPOS_PRESETS: list[dict[str, tuple[Ajustes, str]]] = [
    {
        PRESET_PRINCIPAL: (
            _p(45, 40, 30, 35, 45, 0, -5, 8, 3, -5, 35),
            "Equilibrado para la mayoría de las fotos. Aproximación visual al procesado de un "
            "celular; no replica exactamente la cámara del iPhone 13.",
        ),
        "Celular natural — sutil": (
            _p(30, 25, 20, 22, 30, 0, -3, 5, 2, -3, 20),
            "La misma idea, más discreta. Para fotos que ya se ven bastante naturales.",
        ),
        "Celular natural — marcado": (
            _p(65, 60, 45, 55, 60, 0, -8, 10, 3, -8, 50),
            "Más evidente. Para renders o imágenes de IA muy pulidas.",
        ),
    },
    {
        # Pensado para fotos hechas con IA: saca la calidad exagerada y la piel
        # perfecta. A diferencia de los demás NO suaviza: la piel de IA ya es
        # demasiado lisa, así que en vez de aplanarla le devuelve textura.
        PRESET_ANTI_IA: (
            _p(75, 70, 0, 45, 35, 0, -8, 3, 0, -12, 45, piel=70),
            "Para fotos generadas con IA: baja el sobreenfoque y el detalle de render, le "
            "devuelve poros a la piel lisa, apaga el brillo de plástico y tira el color a "
            "algo más real. No borra todos los indicios de IA.",
        ),
    },
    {
        # Perfiles por tipo de cámara: características generales, no un modelo concreto.
        "Smartphone moderno — foto cotidiana": (
            _perfil(nitidez=45, microcontraste=40, suavizado=30, ruido=25, tono=55, contraste=-3,
                    luces=30, sombras=10, temperatura=5, respuesta_camara=30, aberracion=25, bordes=25,
                    vineteo=10, distorsion=10, jpeg=15),
            "HDR suave, detalle limpio, algo de reducción de ruido y un JPEG liviano.",
        ),
        "Smartphone antiguo — menos rango dinámico": (
            _perfil(nitidez=60, microcontraste=55, suavizado=45, ruido=55, ruido_croma=70, tono=15,
                    contraste=15, temperatura=8, saturacion=-8, respuesta_camara=40, aberracion=50,
                    bordes=55, vineteo=25, distorsion=15, desenfoque=20, reescalado=20, jpeg=45),
            "Poco HDR, contraste duro, más ruido, lente más blando y compresión visible.",
        ),
        "Cámara compacta digital": (
            _perfil(nitidez=50, microcontraste=45, suavizado=25, ruido=40, ruido_croma=60, tono=20,
                    contraste=5, luces=20, temperatura=4, saturacion=5, respuesta_camara=50,
                    aberracion=40, bordes=40, vineteo=20, distorsion=20, desenfoque=10, bayer=True, jpeg=30),
            "Sensor chico: ruido con algo de color, zoom con distorsión de barril y JPEG de cámara.",
        ),
        "DSLR convencional": (
            _perfil(nitidez=55, microcontraste=35, ruido=20, ruido_lectura=30, ruido_croma=30, contraste=5,
                    luces=50, sombras=15, saturacion=-3, respuesta_camara=60, aberracion=15, bordes=15,
                    vineteo=25, distorsion=5, desenfoque=10, bayer=True, jpeg=10),
            "Sensor grande: poco ruido, sin HDR agresivo, luces que caen suave y viñeteo del lente.",
        ),
        "Cámara mirrorless": (
            _perfil(nitidez=50, microcontraste=30, ruido=15, ruido_correlacion=20, tono=10, contraste=3,
                    luces=45, sombras=10, respuesta_camara=45, aberracion=10, bordes=10, vineteo=15,
                    distorsion=5, desenfoque=5, bayer=True, jpeg=5),
            "Limpia y nítida sin sobreenfoque, rango amplio, óptica corregida.",
        ),
        "JPEG comprimido de redes sociales": (
            _perfil(nitidez=55, microcontraste=45, suavizado=35, ruido=10, tono=30, contraste=8,
                    saturacion=8, luces=10, reescalado=35, reescalado_algoritmo=2, jpeg=50),
            "Achicada y recomprimida como al subirla a una red: menos resolución y artefactos de JPEG.",
        ),
        "Interior con flash": (
            _perfil(nitidez=45, microcontraste=40, suavizado=30, ruido=30, contraste=18, luces=10,
                    exposicion=5, temperatura=-6, desat_luces=30, saturacion=3, respuesta_camara=30,
                    aberracion=25, bordes=30, vineteo=70, distorsion=10, jpeg=20),
            "Luz frontal dura: sujeto claro, fondo que se oscurece (caída del flash), tono neutro-frío.",
        ),
        "Noche con ISO alto": (
            _perfil(nitidez=60, microcontraste=55, suavizado=55, ruido=80, ruido_lectura=75, ruido_croma=70,
                    ruido_correlacion=50, tono=70, exposicion=-5, contraste=-5, temperatura=-10, tinte=5,
                    saturacion=-15, desat_luces=40, luces=40, sombras=25, aberracion=40, bordes=45,
                    vineteo=20, desenfoque=15, jpeg=25),
            "Mucho ruido de lectura en sombras, reducción de ruido fuerte, color apagado y luces lavadas.",
        ),
    },
    {
        # Aproximaciones al "look" típico de cada teléfono; no replican sus cámaras.
        "Estilo iPhone 15 Pro": (
            _p(40, 35, 25, 25, 55, 0, -3, 6, 2, 0, 25),
            "Detalle limpio, sombras abiertas y tono apenas cálido. Aproximación visual, no la cámara real.",
        ),
        "Estilo iPhone 11": (
            _p(50, 45, 35, 40, 40, 0, 0, 10, 3, -3, 40),
            "Algo más de ruido y suavizado, tono cálido característico. Aproximación visual.",
        ),
        "Estilo iPhone 8 / X": (
            _p(60, 55, 45, 50, 30, 0, 3, 12, 2, -5, 50),
            "Menos HDR, más contraste y ruido, bordes más blandos. Aproximación visual.",
        ),
        "Estilo Samsung Galaxy S23": (
            _p(40, 35, 40, 25, 60, 5, 8, -4, 0, 18, 30),
            "Colores vivos, imagen luminosa y texturas suavizadas. Aproximación visual.",
        ),
        "Estilo Samsung Galaxy A (gama media)": (
            _p(65, 60, 60, 55, 50, 5, 6, -6, 0, 12, 55),
            "Saturado y luminoso, con menos detalle y más ruido. Aproximación visual.",
        ),
        "Estilo Google Pixel 8": (
            _p(40, 35, 25, 30, 70, -5, 10, -6, -2, 3, 30),
            "Contraste marcado, sombras profundas pero abiertas y tono algo frío. Aproximación visual.",
        ),
        "Estilo Xiaomi Redmi": (
            _p(65, 60, 65, 55, 55, 5, 5, 4, 0, 15, 60),
            "Mucho suavizado, colores intensos y bordes blandos. Aproximación visual.",
        ),
        "Estilo Motorola Moto G": (
            _p(70, 65, 60, 60, 45, 0, 0, -3, -2, 5, 60),
            "Gama media: poco detalle, ruido visible y color neutro. Aproximación visual.",
        ),
    },
    {
        "Exterior soleado": (
            _p(45, 40, 20, 18, 65, -5, 0, 10, 2, 0, 30),
            "Mucha luz: poco ruido, sombras abiertas y luces contenidas como el HDR del teléfono.",
        ),
        "Día nublado": (
            _p(45, 35, 30, 30, 40, 5, -12, -10, 0, -15, 30),
            "Luz difusa y fría, contraste suave y colores apagados.",
        ),
        "Paisaje con HDR": (
            _p(50, 45, 20, 20, 85, -5, 3, 4, 1, 5, 35),
            "Cielos y sombras a la vez, con el aspecto de rango comprimido de un celular.",
        ),
        "Interior con luz cálida": (
            _p(50, 45, 45, 55, 55, 5, -6, 30, 5, -6, 35),
            "Casa o bar con lámparas: tono cálido, algo de ruido y texturas suavizadas.",
        ),
        "Interior con poca luz": (
            _p(60, 55, 65, 75, 70, -5, -10, 15, 4, -15, 40),
            "Ambiente oscuro: más ruido en sombras y más reducción de ruido, como de noche en casa.",
        ),
        "Noche urbana": (
            _p(65, 60, 70, 85, 80, -10, -5, -12, 6, -10, 45),
            "Calle de noche: sombras ruidosas, texturas lavadas y luces artificiales.",
        ),
    },
    {
        "Selfie con cámara frontal": (
            _p(60, 60, 55, 40, 50, 5, -8, 12, 4, -6, 15),
            "Cámara delantera: menos detalle, piel más suave y tono algo cálido.",
        ),
        "Retrato con luz de ventana": (
            _p(50, 50, 40, 30, 55, 0, -6, 6, 3, -4, 40),
            "Luz lateral suave, sombras abiertas y bordes un poco menos nítidos.",
        ),
        "Comida y restaurante": (
            _p(40, 35, 35, 40, 50, 5, 5, 25, 2, 10, 30),
            "Cálido y algo más saturado, como una foto de plato en un restaurante.",
        ),
        "Colores vivos": (
            _p(40, 35, 30, 30, 55, 5, 12, 2, 0, 20, 30),
            "Más contraste y saturación, como el procesado de muchos celulares de gama media.",
        ),
    },
    {
        "Celular de gama básica": (
            _p(75, 70, 70, 70, 40, 0, -5, -5, -4, -12, 70),
            "Cámara modesta: menos detalle, más ruido, bordes más blandos y color algo apagado.",
        ),
        "Foto reenviada por mensajería": (
            _p(70, 65, 60, 25, 40, 0, 3, 3, 0, -5, 20),
            "Detalle más blando, como una foto que pasó por varios chats, sin artefactos de JPEG.",
        ),
    },
    {
        "Solo textura (sin tocar el color)": (
            _p(45, 40, 30, 35, 0, 0, 0, 0, 0, 0, 35),
            "Nitidez, microcontraste, ruido y óptica del preset principal; el color queda igual.",
        ),
        "Solo color y tono (sin textura)": (
            _p(0, 0, 0, 0, 45, 0, -5, 8, 3, -5, 0, optica_activa=False),
            "Luces, sombras y color del preset principal; el detalle queda igual.",
        ),
    },
]

PRESETS: dict[str, Ajustes] = {n: a for g in GRUPOS_PRESETS for n, (a, _d) in g.items()}
DESCRIPCIONES_PRESETS: dict[str, str] = {n: d for g in GRUPOS_PRESETS for n, (_a, d) in g.items()}


def cambios_respecto_de_neutro(ajustes: Ajustes) -> list[tuple[str, object]]:
    """(campo, valor) de todo lo que el preset cambia: para mostrar "qué modifica"."""
    return [(f.name, getattr(ajustes, f.name)) for f in fields(Ajustes)
            if f.name != "intensidad" and getattr(ajustes, f.name) != getattr(NEUTRO, f.name)]


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def reducir_para_vista(rgb: np.ndarray, lado_max: int) -> tuple[np.ndarray, float]:
    """Devuelve una copia reducida para vista previa rápida y el factor aplicado."""
    import cv2

    h, w = rgb.shape[:2]
    lado = max(h, w)
    if lado <= lado_max:
        return rgb, 1.0
    f = lado_max / lado
    nuevo = (max(1, round(w * f)), max(1, round(h * f)))
    return cv2.resize(rgb, nuevo, interpolation=cv2.INTER_AREA), nuevo[0] / w


def _rng(ajustes: Ajustes, h: int, w: int, variacion: int, etapa: int) -> np.random.Generator:
    return np.random.default_rng([SEMILLA_RUIDO, int(ajustes.semilla), h, w, int(variacion), etapa])


def procesar_flotante(
    img: np.ndarray,
    ajustes: Ajustes,
    escala_vista: float = 1.0,
    cancelado: Optional[Callable[[], bool]] = None,
    variacion_semilla: int = 0,
) -> np.ndarray:
    """Aplica una capa de ajustes (sin la compresión final). Entra uint8 o float
    en gamma y devuelve float32 en gamma, sin cuantizar."""
    if img.ndim != 3 or img.shape[2] != 3:
        raise ValueError("Se esperaba un arreglo RGB de forma HxWx3")

    def verificar() -> None:
        if cancelado is not None and cancelado():
            raise Cancelado()

    a = ajustes
    h, w = img.shape[:2]
    k = max(0.0, min(1.0, a.intensidad / 100.0))

    def v(campo: str, activo: bool = True) -> float:
        return float(getattr(a, campo)) / 100.0 * k if activo else 0.0

    sen, opt, det, tex = a.sensor_activo, a.optica_activa, a.detalle_activo, a.textura_activa
    ilu, col, gra = a.iluminacion_activa, a.color_activo, a.grano_activo

    ruido = v("ruido", sen)
    bayer = sen and a.bayer and k > 0
    desenf, dist, aber, bord, vin = (v(c, opt) for c in ("desenfoque", "distorsion", "aberracion", "bordes", "vineteo"))
    nit, micro, clar, variable = (v(c, det) for c in ("nitidez", "microcontraste", "claridad", "nitidez_variable"))
    suav, piel = v("suavizado", tex), v("piel", tex)
    tono_, expo, contr, luces, sombras = (v(c, ilu) for c in ("tono", "exposicion", "contraste", "luces", "sombras"))
    zonas = tuple(v(c, ilu) for c in ("zona_sombras", "zona_medios", "zona_luces"))
    temp, tinte, varb, sat, desat, resp = (v(c, col) for c in (
        "temperatura", "tinte", "variacion_balance", "saturacion", "desat_luces", "respuesta_camara"))
    gr = v("grano", gra)

    lineales = (expo, temp, tinte, varb, desenf, dist, aber, bord, vin, tono_)
    codificados = (contr, luces, sombras, *zonas, sat, desat, resp, nit, micro, clar, variable, suav, piel, ruido, gr)
    if not bayer and not any(lineales) and not any(codificados):
        return img.astype(np.float32) / 255.0 if img.dtype == np.uint8 else img.astype(np.float32, copy=True)

    s = max(h, w) / LADO_REFERENCIA

    # Máscaras regionales: dependen de la imagen de entrada, se cachean.
    regiones = None
    if a.regiones_activas and any((nit, micro, suav, ruido, piel)):
        regiones = regiones_en_cache(img, s)
        verificar()

    def mapa(efecto: str, cantidad: float):
        if regiones is None or not cantidad:
            return cantidad
        mult = {r: getattr(a, f"reg_{r}_{efecto}") / 100.0 for r in REGIONES}
        return cantidad * regiones.mapa(mult)

    # ---------------- Luz lineal
    if bayer or any(lineales):
        lin = decodificar(img)
        if expo or temp or tinte:
            tono.exposicion_y_balance(lin, expo, temp, tinte)
        if varb:
            tono.variacion_balance(lin, varb, _rng(a, h, w, variacion_semilla, 1))
        verificar()
        if desenf:
            lin = optica.desenfoque(lin, s, desenf)
            verificar()
        if dist:
            lin = optica.distorsion(lin, dist)
            verificar()
        if aber:
            optica.aberracion(lin, aber)
        if bord:
            optica.bordes_blandos(lin, s, bord)
        if vin:
            optica.vineteo(lin, vin)
        verificar()
        if bayer:
            lin = sensor.mosaico_bayer(lin, escala_vista)
            verificar()
        if tono_:
            tono.tono_local(lin, tono_)
            verificar()
        out = codificar(lin)
        del lin
    else:
        out = img.astype(np.float32) / 255.0 if img.dtype == np.uint8 else img.astype(np.float32, copy=True)
    verificar()

    # ---------------- Codificado
    if tono_ or contr or luces or sombras or any(zonas):
        tono.curva_global(out, tono_, contr, luces, sombras, zonas)
    tono.saturacion(out, sat, desat)
    if resp:
        tono.respuesta_camara(out, resp)
    verificar()

    if clar or micro or nit or suav or variable:
        textura.detalle(out, s, clar, mapa("micro", micro), mapa("nitidez", nit), mapa("suavizado", suav),
                        variable, _rng(a, h, w, variacion_semilla, 2), verificar)

    if piel:
        textura.piel_real(out, s, piel, escala_vista, _rng(a, h, w, variacion_semilla, 3), verificar,
                          mascara_piel=regiones.piel if regiones is not None else None)

    if ruido:
        mapa_ruido = mapa("ruido", 1.0)
        sensor.ruido_sensor(out, s, ruido, a.ruido_lectura / 100.0, a.ruido_croma / 100.0,
                            a.ruido_correlacion / 100.0, escala_vista, _rng(a, h, w, variacion_semilla, 4),
                            mapa_ruido if isinstance(mapa_ruido, np.ndarray) else None)
        verificar()

    if gr:
        m_grano.grano(out, s, gr, a.grano_tam / 100.0, a.grano_croma / 100.0, a.grano_correlacion / 100.0,
                      (a.grano_sombras / 100.0, a.grano_medios / 100.0, a.grano_luces / 100.0),
                      escala_vista, _rng(a, h, w, variacion_semilla, 5))
        verificar()
    return out


def _cuantizar(img: np.ndarray) -> np.ndarray:
    out = img * 255.0
    out += 0.5
    np.clip(out, 0.0, 255.0, out=out)
    return out.astype(np.uint8)


def _finalizar(img: np.ndarray, pila: Sequence[Ajustes]) -> np.ndarray:
    """Compresión simulada UNA vez para toda la pila (se usa la capa que más comprime)."""
    def efectivo(a: Ajustes, campo: str) -> float:
        return getattr(a, campo) / 100.0 * max(0.0, min(1.0, a.intensidad / 100.0)) if a.compresion_activa else 0.0

    r_capa = max(pila, key=lambda a: efectivo(a, "reescalado"), default=None)
    j_capa = max(pila, key=lambda a: efectivo(a, "jpeg"), default=None)
    if r_capa is not None and efectivo(r_capa, "reescalado") > 0:
        img = compresion.reescalar(img, efectivo(r_capa, "reescalado"), r_capa.reescalado_algoritmo)
    salida = _cuantizar(img)
    if j_capa is not None and efectivo(j_capa, "jpeg") > 0:
        salida = compresion.jpeg(salida, compresion.calidad_jpeg(efectivo(j_capa, "jpeg")), j_capa.submuestreo)
    return salida


def procesar(
    rgb: np.ndarray,
    ajustes: Ajustes,
    escala_vista: float = 1.0,
    cancelado: Optional[Callable[[], bool]] = None,
    variacion_semilla: int = 0,
) -> np.ndarray:
    """Aplica el tratamiento y devuelve un arreglo uint8 de igual tamaño.

    rgb: arreglo HxWx3 uint8.
    escala_vista: tamaño de ``rgb`` respecto de la imagen original (1.0 = completa).
    cancelado: función que devuelve True si el resultado ya no es necesario.
    """
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("Se esperaba un arreglo RGB uint8 de forma HxWx3")
    return _finalizar(procesar_flotante(rgb, ajustes, escala_vista, cancelado, variacion_semilla), [ajustes])


def procesar_pila(
    rgb: np.ndarray,
    pila: Sequence[Ajustes],
    escala_vista: float = 1.0,
    cancelado: Optional[Callable[[], bool]] = None,
    zonas: Optional[Sequence[Optional[Zona]]] = None,
    recorte: Optional[Recorte] = None,
) -> np.ndarray:
    """Aplica varias capas de ajustes una encima de otra, en orden, sin cuantizar
    entre capas. Cada capa usa una semilla distinta para que su grano no se sume
    exactamente sobre el de la anterior.

    ``zonas``: una por capa (None = toda la foto). Una capa con zona solo cambia
    esa parte; el resto queda como venía de la capa anterior, con borde fundido.
    ``recorte``: el recorte con el que se recortó ``rgb`` (solo para ubicar las
    zonas, que se guardan en coordenadas de la foto original).
    """
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("Se esperaba un arreglo RGB uint8 de forma HxWx3")
    if not pila:
        return rgb.copy()
    img: np.ndarray = rgb
    h, w = rgb.shape[:2]
    for i, ajustes in enumerate(pila):
        nueva = procesar_flotante(img, ajustes, escala_vista, cancelado, variacion_semilla=i)
        zona = zonas[i] if zonas is not None and i < len(zonas) else None
        if zona is not None:
            previa = img.astype(np.float32) / 255.0 if img.dtype == np.uint8 else img
            m = mascara_zona(zona, h, w, recorte)[..., None]
            nueva = previa + (nueva - previa) * m
        img = nueva
    return _finalizar(img, pila)


__all__ = [
    "Ajustes", "Cancelado", "NEUTRO", "PRESET_PRINCIPAL", "PRESET_ANTI_IA", "PRESETS", "GRUPOS_PRESETS",
    "DESCRIPCIONES_PRESETS", "cambios_respecto_de_neutro", "procesar", "procesar_flotante", "procesar_pila",
    "reducir_para_vista",
]
