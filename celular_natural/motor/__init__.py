"""Motor de procesamiento de imagen. No depende de la interfaz gráfica."""

from .procesado import (
    Ajustes,
    Cancelado,
    NEUTRO,
    PRESET_PRINCIPAL,
    PRESET_ANTI_IA,
    PRESETS,
    GRUPOS_PRESETS,
    DESCRIPCIONES_PRESETS,
    cambios_respecto_de_neutro,
    procesar,
    procesar_flotante,
    procesar_pila,
    reducir_para_vista,
)
from .parametros import CONTROLES, SECCIONES, Control, Seccion
from .mascaras import EFECTOS_REGIONALES, NOMBRES_EFECTOS, NOMBRES_REGIONES, REGIONES
from .lote import ResultadoLote, procesar_lote
from .zonas import (
    FORMAS, FORMAS_LIBRES, ORIGENES_MASCARA, Recorte, Zona, aplicar_recorte, mascara_zona, registrar_mascara,
    transformar_zona,
)
from .geometria import (
    Geometria, aplicar_geometria, destransformar_puntos, detectar_horizonte, matriz_geometria,
    tamano_resultante, transformar_puntos,
)
from .seleccion_auto import (
    codificar_mascara, decodificar_mascara, mascara_cielo, mascara_piel, recortar_objeto,
)
from .borrado import clonar, rellenar
from .edicion import (
    MODOS_BORRADO, ZonaBorrado, aplicar_borrado, aplicar_borrados, con_geometria, convertir_borrado,
    convertir_recorte, convertir_zona, matriz_cambio,
)
from .imagen_io import (
    ImagenCargada,
    cargar_imagen,
    exportar_imagen,
    ruta_salida_sugerida,
    TransformacionPantalla,
)

__all__ = [
    "Ajustes",
    "Cancelado",
    "NEUTRO",
    "PRESET_PRINCIPAL",
    "PRESET_ANTI_IA",
    "PRESETS",
    "GRUPOS_PRESETS",
    "DESCRIPCIONES_PRESETS",
    "cambios_respecto_de_neutro",
    "procesar",
    "procesar_flotante",
    "procesar_pila",
    "reducir_para_vista",
    "CONTROLES",
    "SECCIONES",
    "Control",
    "Seccion",
    "EFECTOS_REGIONALES",
    "NOMBRES_EFECTOS",
    "NOMBRES_REGIONES",
    "REGIONES",
    "ResultadoLote",
    "procesar_lote",
    "FORMAS",
    "FORMAS_LIBRES",
    "Recorte",
    "Zona",
    "aplicar_recorte",
    "mascara_zona",
    "ORIGENES_MASCARA",
    "registrar_mascara",
    "transformar_zona",
    "Geometria",
    "aplicar_geometria",
    "destransformar_puntos",
    "detectar_horizonte",
    "matriz_geometria",
    "tamano_resultante",
    "transformar_puntos",
    "codificar_mascara",
    "decodificar_mascara",
    "mascara_cielo",
    "mascara_piel",
    "recortar_objeto",
    "clonar",
    "rellenar",
    "MODOS_BORRADO",
    "ZonaBorrado",
    "aplicar_borrado",
    "aplicar_borrados",
    "con_geometria",
    "convertir_borrado",
    "convertir_recorte",
    "convertir_zona",
    "matriz_cambio",
    "ImagenCargada",
    "cargar_imagen",
    "exportar_imagen",
    "ruta_salida_sugerida",
    "TransformacionPantalla",
]
