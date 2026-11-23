# NaturalShot Lite, etapas 0 y 1: plan de implementación

> **Para los subagentes:** se ejecuta tarea por tarea con superpowers:subagent-driven-development. La carpeta **no es un repositorio git**: no hay commits. Antes de editar un archivo existente, guardá una copia en el scratchpad que te indiquen.

**Objetivo:** una edición "NaturalShot Lite" solo de fotos (etapa 0) con capas de verdad tipo Photoshop (etapa 1). El filtro "celular natural" queda como capa de ajuste arriba de todo.

**Arquitectura:**
- La edición se decide en `celular_natural/edicion.py`, con un `.spec` propio.
- **Motor de capas sin Qt:** `motor/fusion.py`, `motor/documento.py` y `motor/proyecto_lite.py`. `componer()` recibe la foto base ya procesada y el filtro como función, así no depende de la interfaz.
- **Interfaz:** `ui/panel_capas.py` y la herramienta Mover/Transformar en la vista, integradas en `ui/ventana.py`.

**Diseño completo:** `docs/superpowers/specs/2026-10-14-naturalshot-lite-design.md`. **Leelo antes de empezar.**

**Stack:** Python 3.14 (`.venv\Scripts\python`), numpy 2.5, opencv-headless 5, Pillow 12, PySide6 6.12. **No hay scipy y no se instalan paquetes.**

**Suite completa:**

```
$env:QT_QPA_PLATFORM="offscreen"; .venv\Scripts\python -m unittest discover -s tests
```

Hoy son unas 535 pruebas, y tarda unos 9 minutos.

**Reglas comunes:**
- Español rioplatense en la interfaz; nombres, docstrings y comentarios en español, con la densidad de `motor/audio.py`.
- Sin filtros globales de eventos (ver `_FiltroGlobal`). Hilos con `Tarea` y `QThreadPool`.
- **Privacidad:** fuera del proyecto y del scratchpad no se lee ni se lista nada. Los medios de prueba se generan.
- Nada de internet, git ni GitHub. No se toca `dist\` ni `build\` de la PRO.
- Las pruebas de interfaz vacían los borrados diferidos en `tearDown`.

---

## Tarea L0: edición Lite (etapa 0)

**Archivos:**
- **crear:** `celular_natural/edicion.py`, `NaturalShot Lite.spec`, `construir_lite.bat`, `ejecutar_lite.bat` y `tests/test_edicion_lite.py`;
- **modificar:** lo mínimo para que se respete la edición:
  - `celular_natural/__init__.py` (`NOMBRE_APP` y la insignia);
  - `main.py`;
  - `ui/ventana.py` (selector, atajos, ruteo y chips);
  - `ui/modo_video.py` (ruteo);
  - `ui/carga.py` (insignia);
  - `ui/actualizaciones.py` (apagado en Lite);
  - `sesion.py` y `ui/presets_usuario.py` (carpeta de datos);
  - el lugar donde se crean los QSettings (`NATURALSHOT_CONFIG` sigue funcionando para las pruebas).

**Contrato:**

```python
# celular_natural/edicion.py
EDICION: str            # "pro" | "lite"
def es_lite() -> bool: ...
def nombre_app() -> str: ...          # "NaturalShot PRO" | "NaturalShot Lite"
def insignia() -> str: ...            # "PRO" | "LITE"
def carpeta_datos() -> Path: ...      # %APPDATA%\NaturalShot PRO | %APPDATA%\NaturalShot Lite
def organizacion_qsettings() -> tuple[str, str]: ...
```

- **Cómo se decide la edición:**
  1. la variable de entorno `NATURALSHOT_EDICION`;
  2. si no está, en el `.exe`, un archivo `edicion.txt` junto al ejecutable (o en `sys._MEIPASS`) que pone el `.spec`;
  3. si no hay nada, "pro".
- **Interfaz en Lite:** se comporta como dice el diseño (etapa 0): selector Fácil | Editor, sin Video ni Audio, sin sus atajos ni chips, y aviso "NaturalShot Lite es solo para fotos" para videos y audios. El editor de video y el de audio **no se importan nunca**.

**Pasos:**
- [ ] **Pruebas primero** (`tests/test_edicion_lite.py`), creando ventanas con `NATURALSHOT_EDICION=lite` (con `mock.patch.dict(os.environ)`, recargando `edicion` si hace falta):
  - el selector no tiene Video ni Audio;
  - Ctrl+Shift+V y Ctrl+Shift+A no hacen nada;
  - soltar un MP4 o un MP3 no cambia de modo, muestra el aviso y `editor_video` y `editor_audio` siguen en None;
  - `carpeta_datos()` termina en "NaturalShot Lite";
  - el título y la insignia dicen Lite;
  - las actualizaciones están apagadas;
  - en PRO, todo igual que hoy.
- [ ] Implementar.
- [ ] **`NaturalShot Lite.spec`** (copia del `.spec` de PRO): `name="NaturalShot Lite"`, excluye `av`, `PySide6.QtMultimedia`, `celular_natural.ui.editor_video`, `modo_audio`, `paneles_audio`, `pistas_audio`, `motor.video`, `motor.audio`, `motor.proyecto_audio`, `motor.ambientes` y `motor.voz_natural` (**solo si ningún import del camino de fotos los necesita**: verificalo), y agrega `edicion.txt` con "lite".
- [ ] **`construir_lite.bat`:** compila en `dist_lite\` (no pisa `dist\`) y arma `NaturalShot Lite - para otra PC.zip` con `herramientas.publicar.armar_zip`, adaptado para un nombre de carpeta "NaturalShot Lite". Creá también el acceso directo `NaturalShot Lite.lnk` en la carpeta del proyecto, apuntando a `dist_lite\NaturalShot Lite\NaturalShot Lite.exe`.
- [ ] **Verificar:**
  - compilar;
  - abrir el `.exe` descomprimido desde el zip en una carpeta temporal, con APPDATA temporal;
  - que no tenga `av` ni Qt6Multimedia;
  - que pese menos que la PRO (contá cuánto);
  - capturas offscreen de la ventana Lite a 1366 y 1600 px (Fácil y Editor), revisadas.
- [ ] Suite completa en OK (en PRO).

---

## Tarea L1a: motor de capas (etapa 1, sin interfaz)

**Archivos:**
- **crear:** `celular_natural/motor/fusion.py`, `celular_natural/motor/documento.py` y `celular_natural/motor/proyecto_lite.py`;
- **pruebas:** `tests/test_fusion.py`, `tests/test_documento.py` y `tests/test_proyecto_lite.py`;
- **no tocar** nada más.

**Contrato:**

```python
# motor/fusion.py
MODOS_FUSION: dict[str, str]   # "normal": "Normal", "multiplicar": "Multiplicar", "pantalla": "Trama",
                               # "superponer", "luz_suave", "luz_fuerte", "oscurecer", "aclarar",
                               # "sobreexponer", "subexponer", "diferencia", "exclusion",
                               # "tono", "saturacion", "color", "luminosidad"
def fusionar(fondo_rgb, fondo_alfa, capa_rgb, capa_alfa, modo="normal", opacidad=1.0, mascara=None):
    """float32 [0,1]; rgb (h,w,3), alfa (h,w). Devuelve (rgb, alfa). Fórmulas W3C Compositing
    (separables y no separables), con alfa "source-over"."""

# motor/documento.py
@dataclass(frozen=True)
class Transformacion: x: float = 0.0; y: float = 0.0; escala: float = 1.0; rotacion: float = 0.0; voltear_h: bool = False
#   x, y: centro de la capa en píxeles del documento; escala sobre el tamaño original de la imagen; rotación en grados (positivo = horario)

@dataclass(frozen=True)
class Capa:
    id: str; tipo: str          # "foto" | "imagen" | "ajuste_natural"
    nombre: str
    visible: bool = True; bloqueada: bool = False
    opacidad: float = 1.0; fusion: str = "normal"
    imagen: Optional[str] = None        # id en AlmacenImagenes (solo "imagen"): RGBA uint8
    transform: Transformacion = Transformacion()
    mascara: Optional[str] = None       # id en AlmacenImagenes: gris uint8 del tamaño del documento

@dataclass(frozen=True)
class Documento:
    ancho: int; alto: int; capas: tuple[Capa, ...]   # de abajo hacia arriba; capas[0].tipo == "foto"; a lo sumo un "ajuste_natural", siempre la última
    @staticmethod
    def nuevo(ancho, alto) -> "Documento": ...      # foto + ajuste_natural
    # funciones puras (devuelven documento nuevo): agregar_imagen(id_img, nombre, encima_de=None), quitar(id), mover(id, delta),
    # duplicar(id), con_capa(id, **cambios), capa(id), indice(id); validan las reglas (la foto no se borra, el ajuste siempre arriba)

class AlmacenImagenes:   # en memoria, por contenido (hash) -> ndarray de solo lectura; thread-safe
    def guardar(arr) -> str: ...; def obtener(id) -> np.ndarray: ...; def ids() -> set[str]: ...

def componer(doc: Documento, almacen: AlmacenImagenes, foto_rgb: np.ndarray, escala: float = 1.0,
             filtro: Optional[Callable[[np.ndarray], np.ndarray]] = None, cache: Optional["CacheComposicion"] = None) -> np.ndarray:
    """Devuelve RGB uint8 de (round(alto*escala), round(ancho*escala)).
    ``foto_rgb`` es la foto base ya procesada (geometría, montaje, borrado, recorte, fondo) y ya escalada al tamaño de
    salida (la interfaz se la pasa). Se compone de abajo hacia arriba; ``filtro`` (el procesado celular natural de
    hoy) se aplica sobre la composición de todo lo de abajo y se mezcla según la opacidad, visibilidad, fusión y
    máscara de la capa ajuste_natural. Sin capas extra, con la foto visible al 100 % normal y el ajuste visible al
    100 % normal: resultado == filtro(foto_rgb) exacto (regresión)."""

class CacheComposicion: ...  # por (capa, escala): imagen transformada, máscara escalada, y "lo de abajo" del ajuste
```

- **Transformaciones:** `cv2.warpAffine` con `INTER_LINEAR` (o `INTER_AREA` al achicar mucho), y el alfa con las mismas reglas.
- **Proyecto (`motor/proyecto_lite.py`):**
  - `guardar_proyecto(ruta, doc, almacen, extra: dict)` y `abrir_proyecto(ruta) -> (doc, almacen, extra)`;
  - zip con `documento.json` (`"formato": 1`), `imagenes/<id>.png` y `mascaras/<id>.png`;
  - escritura atómica (temporal más `os.replace`);
  - sin pickle;
  - un archivo roto o de una versión futura da `ValueError` claro;
  - `extra` es para la interfaz (por ejemplo, la ruta de la foto base y el estado del editor de hoy, serializados en JSON por la interfaz).

**Pasos:**
- [ ] **Pruebas primero:**
  - `tests/test_fusion.py`: cada modo contra valores calculados a mano en píxeles sueltos (por ejemplo, multiplicar 0,5 × 0,5 = 0,25; pantalla 1-(1-a)(1-b); superponer en los dos lados de 0,5; tono, saturación, color y luminosidad con un par de colores conocidos de la especificación W3C); opacidad 0 = fondo; alfa 0 = fondo; máscara.
  - `tests/test_documento.py`:
    - reglas del documento;
    - funciones puras;
    - componer: sin capas = `filtro(foto)` bit a bit;
    - una imagen opaca normal tapa;
    - el orden importa;
    - ocultar;
    - la opacidad;
    - la transformación contra `cv2.warpAffine` directo;
    - la escala de vista previa contra la escala completa (tamaños);
    - ajuste oculto = sin filtro;
    - opacidad del ajuste al 50 % = la mitad entre con y sin filtro;
    - la caché (contar llamadas al filtro: mover una capa encima del ajuste no existe, porque el ajuste va siempre arriba; ocultar la capa y volver a mostrarla usa la caché);
    - `AlmacenImagenes` con varios hilos.
  - `tests/test_proyecto_lite.py`: ida y vuelta igual; zip roto; formato futuro; que no use pickle (un zip con un `.pkl` no se ejecuta).
- [ ] Implementar.
- [ ] **Velocidad:** componer 3 capas más el ajuste sin filtro, a 1920×1080, en menos de 60 ms; con la caché llena y solo moviendo una capa, en menos de 40 ms.
- [ ] Suite completa en OK.

---

## Tarea L1b: interfaz de capas (etapa 1)

**Empieza cuando terminen L0 y L1a.**

**Archivos:**
- **crear:** `ui/panel_capas.py`, `ui/herramienta_transformar.py` y `tests/test_capas_ui.py`;
- **modificar:** `ui/ventana.py`, `ui/vista_comparacion.py`, `ui/controles.py` (renombrar "Capas" a "Efectos"), `sesion.py` (documentos en la sesión), `ui/modo_facil.py` (nota si hay capas extra) y `ui/estilo.py`.

**Contenido:** la sección "Interfaz (modo Editor)" del diseño, completa:
- panel de capas;
- Mover/Transformar con manijas;
- máscaras con las herramientas de zona;
- agregar imagen, también con Ctrl+arrastrar;
- guardar y abrir `.nslite`;
- historial;
- sesión;
- Fácil.

La vista previa usa `componer` con la caché, en un hilo como hoy `_recalcular_fuentes`. La exportación usa `componer` a escala 1 (exportación = vista).

**Pasos:**
- [ ] Pruebas de interfaz primero.
- [ ] Implementar de a una sección, corriendo las pruebas.
- [ ] Capturas a 1366 y 1600 px, revisadas.
- [ ] Arranque real con `-X faulthandler`.
- [ ] **Suite completa:**
  - en PRO, que el modo Video y el Audio sigan andando;
  - en Lite, compilar con `construir_lite.bat` y probar el zip.

---

## Revisión y entrega

- Una revisión de cumplimiento y calidad por tarea, con un subagente revisor y sus arreglos.
- Actualizar `ESTADO_DEL_PROYECTO.md`, el README (sección Lite) y `LITE.md` (nuevo, como `VIDEO.md`).
- Compilar la Lite y entregar el zip y el acceso directo.
