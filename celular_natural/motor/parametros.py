"""Descripción de todos los parámetros: una sola fuente para el motor y la interfaz.

Cada control dice su campo en ``Ajustes``, su etiqueta, su rango y una ayuda
que explica qué hace fotográficamente. La interfaz arma los paneles con esta
lista y la descripción automática de cada preset ("qué modifica") también.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .compresion import ALGORITMOS


@dataclass(frozen=True)
class Control:
    campo: str
    etiqueta: str
    minimo: int = 0
    maximo: int = 100
    ayuda: str = ""
    tipo: str = "entero"  # "entero" (deslizador) · "booleano" · "opcion"
    opciones: tuple[str, ...] = ()
    efecto: bool = True  # False = parámetro de forma (no hace nada por sí solo)


@dataclass(frozen=True)
class Seccion:
    nombre: str
    interruptor: str | None
    icono: str
    descripcion: str
    controles: tuple[Control, ...] = field(default_factory=tuple)


SECCIONES: tuple[Seccion, ...] = (
    Seccion("Sensor", "sensor_activo", "cpu",
            "Ruido residual del sensor (modelo Poisson-Gaussiano en luz lineal) y mosaico de color.", (
        Control("ruido", "Ruido de sensor (ISO)", ayuda="Ruido que crece con la luz como en un sensor real; más visible en sombras."),
        Control("ruido_lectura", "Ruido de lectura", ayuda="Peso del ruido electrónico (domina en sombras) frente al de disparo (sigue a la luz).", efecto=False),
        Control("ruido_croma", "Ruido cromático", ayuda="Manchas de color tenues dentro del ruido. 0 = solo luminancia.", efecto=False),
        Control("ruido_correlacion", "Tamaño del grano de ruido", ayuda="Correlación espacial: el demosaico y la reducción de ruido agrupan el ruido en granitos de 1-2 px.", efecto=False),
        Control("bayer", "Mosaico Bayer y demosaico", tipo="booleano", ayuda="Reconstruye la imagen como un sensor RGGB: leve ablandamiento y falsos colores mínimos en bordes finos."),
    )),
    Seccion("Óptica", "optica_activa", "aperture",
            "Imperfecciones del lente, calculadas en luz lineal antes del sensor.", (
        Control("desenfoque", "Desenfoque óptico (PSF)", ayuda="Disco de foco + difracción: la nitidez cae suave, como un lente real, sin el corte de un blur simple."),
        Control("distorsion", "Distorsión radial", -100, 100, "Positivo: barril (gran angular de celular). Negativo: cojín."),
        Control("aberracion", "Aberración cromática", ayuda="Rojo y azul con un aumento apenas distinto: ribetes de color de menos de 1 px en las esquinas."),
        Control("bordes", "Pérdida de nitidez en bordes", ayuda="Curvatura de campo: el centro nítido y las esquinas algo más blandas."),
        Control("vineteo", "Viñeteo", ayuda="Caída de luz hacia las esquinas (en luz lineal, como la real)."),
    )),
    Seccion("Detalles", "detalle_activo", "scan-search",
            "Nitidez y contraste local, con filtros que preservan los contornos.", (
        Control("nitidez", "Reducir nitidez artificial", ayuda="Comprime los halos de enfoque y el sobreenfoque sin borrar contornos."),
        Control("microcontraste", "Reducir microcontraste", ayuda="Baja el contraste de la textura fina que hace que la imagen parezca un render."),
        Control("claridad", "Claridad local", -100, 100, "Contraste de frecuencias medias. Negativo: menos 'punch' artificial."),
        Control("nitidez_variable", "Nitidez variable", ayuda="Foco apenas desparejo en la imagen, como en cualquier foto real."),
    )),
    Seccion("Texturas", "textura_activa", "grid-3x3",
            "Superficies: suavizado del procesado del teléfono o textura real para la piel de IA.", (
        Control("suavizado", "Suavizado de texturas", ayuda="Reducción de ruido del celular: aplana texturas finas y conserva los bordes."),
        Control("piel", "Piel real (anti IA)", ayuda="Lo contrario del suavizado: poros en la piel demasiado lisa y menos brillo de plástico."),
    )),
    Seccion("Iluminación", "iluminacion_activa", "sun-moon",
            "Respuesta tonal: curvas no lineales, rango dinámico y zonas.", (
        Control("tono", "Procesado de luces y sombras (HDR)", ayuda="Compresión local del rango: abre sombras y contiene luces, como el HDR del teléfono."),
        Control("exposicion", "Exposición", -100, 100, "Hasta ±0,5 pasos, en luz lineal."),
        Control("contraste", "Contraste", -100, 100, "Curva en S sobre los medios tonos."),
        Control("luces", "Caída suave de luces", ayuda="Highlight roll-off: el blanco llega de a poco en vez de cortarse."),
        Control("sombras", "Pie de sombras", ayuda="Shadow roll-off: el negro queda apenas levantado y las sombras se comprimen suave."),
        Control("zona_sombras", "Brillo en sombras", -100, 100, "Solo las zonas oscuras."),
        Control("zona_medios", "Brillo en medios tonos", -100, 100, "Solo los medios tonos."),
        Control("zona_luces", "Brillo en luces", -100, 100, "Solo las zonas claras."),
    )),
    Seccion("Color", "color_activo", "palette",
            "Balance de blancos, saturación y render de color de cámara.", (
        Control("temperatura", "Temperatura", -100, 100, "Positivo: más cálido. Negativo: más frío."),
        Control("tinte", "Tinte", -100, 100, "Positivo: magenta. Negativo: verde."),
        Control("variacion_balance", "Variación de balance", ayuda="Luz mezclada: el balance cambia apenas entre zonas (ventana fría, lámpara cálida)."),
        Control("saturacion", "Saturación", -100, 100, "Intensidad general del color."),
        Control("desat_luces", "Desaturar altas luces", ayuda="Cerca del blanco el color se lava, como cuando el sensor se satura."),
        Control("respuesta_camara", "Respuesta de color de cámara", ayuda="Rojos hacia naranja, verdes hacia amarillo, azules hacia cian, como el render típico de una cámara."),
    )),
    Seccion("Grano", "grano_activo", "grip",
            "Grano fotográfico con tamaño, agrupamiento y respuesta por zonas.", (
        Control("grano", "Intensidad del grano"),
        Control("grano_tam", "Tamaño del grano", ayuda="De 0,5 a 3 px en una foto de 12 MP.", efecto=False),
        Control("grano_correlacion", "Correlación espacial", ayuda="Cuánto se agrupa el grano en grumos.", efecto=False),
        Control("grano_croma", "Grano cromático", ayuda="0 = monocromático. 100 = cada canal con su propio grano.", efecto=False),
        Control("grano_sombras", "Grano en sombras", ayuda="Intensidad relativa en las zonas oscuras.", efecto=False),
        Control("grano_medios", "Grano en medios tonos", efecto=False),
        Control("grano_luces", "Grano en luces", efecto=False),
    )),
    Seccion("Compresión", "compresion_activa", "file-archive",
            "Reescalado y JPEG simulados una sola vez al final: nunca se acumulan.", (
        Control("reescalado", "Reescalado (pérdida de resolución)", ayuda="Achica y vuelve a agrandar, como una foto pasada por una app. Hasta el 40 %."),
        Control("reescalado_algoritmo", "Algoritmo de reescalado", 0, len(ALGORITMOS) - 1, "Cómo se interpola al achicar y agrandar.",
                tipo="opcion", opciones=ALGORITMOS, efecto=False),
        Control("jpeg", "Compresión JPEG", ayuda="0 = sin compresión. 100 = calidad 35 con artefactos claros."),
        Control("submuestreo", "Submuestreo de croma 4:2:0", tipo="booleano",
                ayuda="El color a media resolución, como en casi todos los JPEG de celular.", efecto=False),
    )),
)

CONTROLES: dict[str, Control] = {c.campo: c for sec in SECCIONES for c in sec.controles}
CONTROLES["intensidad"] = Control("intensidad", "Intensidad general", efecto=False)
CONTROLES["semilla"] = Control("semilla", "Semilla", 0, 9999,
                               "Mismo número = exactamente el mismo ruido y grano. Cambiala para otra variación.", efecto=False)
