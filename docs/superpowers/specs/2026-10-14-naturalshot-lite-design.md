# NaturalShot Lite: diseño

Fecha: 14/10/2026. Estado: aprobado por el dueño en el chat ("perfecto").

## Para qué

- **NaturalShot PRO** (fotos, video y audio) queda **en pausa**, tal cual está, y se puede seguir compilando.
- **NaturalShot Lite** es la app nueva, **solo de fotos**. Trae todo lo que ya existe para fotos:
  - modo Fácil y modo Editor;
  - presets, efectos apilados y zonas;
  - montaje, fondo, borrar objetos, girar y enderezar;
  - selección automática, tira de fotos, historial y sesión;
  - exportar y tutorial.

  Y se convierte, por etapas, en un editor **tipo Photoshop/Photopea**.
- **El flujo del dueño:** primero edita la foto como en Photoshop (capas, retoque, texto) y **al final** aplica el filtro anti IA o de teléfono (por ejemplo, iPhone 13 Pro) **sobre el resultado entero**.

## Decisiones del dueño

| Pregunta | Respuesta |
|---|---|
| ¿Lite y PRO? | PRO en pausa; Lite = solo fotos, con todo lo de fotos más lo de Photoshop |
| ¿Qué de Photoshop? | Todo: capas, selección y retoque, texto y formas, ajustes clásicos |
| ¿Cómo? | **Camino A:** lo construimos nosotros, por etapas, sin internet (Photopea embebido, descartado) |
| ¿Orden del filtro? | El filtro "celular natural" va **arriba de todo**, sobre la edición terminada |

## Cambio del 14/10 (14:30): modo propio "Photoshop"

El dueño pidió que lo de Photoshop esté en **un modo propio del selector**: `Fácil | Editor | Photoshop` (solo en Lite; nombre elegido por él). Atajo Ctrl+Shift+P.

- **Modo Photoshop:** se edita la imagen con capas, sin el filtro celular natural. Distribución tipo Photopea:
  - herramientas a la izquierda (Mover y las de máscara; solo las que existen);
  - la vista en el centro, con la tira abajo;
  - Capas e Historial a la derecha.
  - La capa del filtro se ve arriba de todo, bloqueada, como "se elige en Fácil o Editor".
- **Fácil y Editor:** como siempre, pero la foto que entra al filtro es la composición del modo Photoshop. Sin capas extra, todo da igual que antes. El panel de capas **no** está en Editor; "Capas" (presets apilados) pasa a llamarse "Efectos".
- Este cambio reemplaza lo que dice la sección "Interfaz (modo Editor)" de abajo sobre dónde va el panel de capas.

## Etapas

| Etapa | Qué trae | Este documento |
|---|---|---|
| 0 | La edición Lite: sin Video ni Audio, `.exe` propio | **Sí** |
| 1 | Capas de verdad (documento, panel de capas, mover y transformar, máscaras, fusión, proyecto `.nslite`) | **Sí** |
| 2 | Selección (varita mágica, selección rápida, lazo) y retoque (pincel, borrador, tampón, parche, sobreexponer y subexponer, desenfocar o enfocar zona) | Diseño propio después |
| 3 | Ajustes clásicos como capas de ajuste (niveles, curvas, tono/saturación, balance, blanco y negro) y filtros | Diseño propio después |
| 4 | Texto y formas | Diseño propio después |
| 5 | Abrir y guardar PSD | Diseño propio después |

## Etapa 0: edición Lite

- **Una sola base de código, dos ediciones.** `celular_natural/edicion.py` define `EDICION` ("pro" | "lite").
  - **Cómo se decide:** en el `.exe`, por un archivo o constante que deja el `.spec`; desde el código, con la variable `NATURALSHOT_EDICION=lite` o `ejecutar_lite.bat`.
  - **Por defecto:** "pro", así nada de lo de PRO cambia.
- **En Lite:**
  - **Nombre e imagen:** "NaturalShot Lite", con la insignia **LITE** (violeta) en lugar de PRO; el título de la ventana, la pantalla de carga y el "Acerca de" dicen Lite.
  - **Modos:** el selector muestra solo **Fácil | Editor**. No hay botón Video, Ctrl+Shift+V ni Ctrl+Shift+A, ni chips de exportación de video o audio.
  - **Archivos que se sueltan o se abren:** los videos y audios no se abren y avisan "NaturalShot Lite es solo para fotos". El diálogo de abrir solo ofrece imágenes (y después proyectos `.nslite`).
  - **Datos propios:**
    - `%APPDATA%\NaturalShot Lite\` (sesión, logs y temporales);
    - QSettings `("NaturalShot", "NaturalShot Lite")`;
    - presets propios en su propio JSON.
    - Nada se mezcla con la PRO.
  - **Actualizaciones automáticas:** apagadas (sin banner ni menú de GitHub), hasta que haya un repositorio para Lite.
  - **Tutorial:** el mismo PDF por ahora. Las páginas de Video y Audio quedan; en una próxima versión del tutorial se arma una edición Lite.
- **Empaquetado:**
  - `NaturalShot Lite.spec`: excluye `av`, `PySide6.QtMultimedia`, `QtNetwork` si no hace falta, y los módulos de video y audio; ícono propio (el mismo con un detalle LITE, o el mismo si no hay tiempo).
  - Sale en `dist\NaturalShot Lite\` y en el zip `NaturalShot Lite - para otra PC.zip`.
  - `construir_lite.bat`, más un acceso directo `NaturalShot Lite.lnk`.
- **Pruebas:**
  - en edición Lite: no hay botones de Video ni Audio, un video soltado avisa y no abre nada, y la carpeta de datos es la de Lite;
  - el `.exe` Lite abre y no contiene `av` ni QtMultimedia;
  - toda la suite sigue pasando en edición PRO.

## Etapa 1: capas de verdad

### Conceptos

- **Documento:** cada foto de la tira es un documento (como las pestañas de Photopea). Tiene ancho y alto (los de la foto base, después de la geometría y el recorte de hoy) y una **pila de capas**, de abajo hacia arriba.
- **Tipos de capa** en esta etapa:
  - **Foto:** la de abajo, una sola. Es la foto original con todo el procesado previo de hoy (geometría, montaje, borrar objetos, recorte y fondo), como un "objeto inteligente". No se puede borrar, pero sí ocultar o bajar su opacidad.
  - **Imagen:** otra foto, un PNG con transparencia o un logo. Tiene **posición, escala, rotación y volteo**.
  - **Ajuste "Celular natural":** el filtro de siempre (preset, intensidad, efectos apilados y ajustes del panel derecho). Hay **una sola** y va **arriba de todo**; se puede ocultar (sin filtro) y bajar su opacidad. Se aplica **sobre la composición de todas las capas de abajo**.
- Lo que hoy la interfaz llama **"Capas"** (presets apilados) pasa a llamarse **"Efectos"**.
- **Propiedades de cada capa:** nombre, visible, bloqueada, opacidad (0-100 %), **modo de fusión** y **máscara** (opcional, en escala de grises, del tamaño del documento).
- **Modos de fusión:** normal, multiplicar, pantalla, superponer, luz suave, luz fuerte, oscurecer, aclarar, sobreexponer color, subexponer color, diferencia, exclusión, tono, saturación, color y luminosidad. Se usan las fórmulas estándar (W3C Compositing / Photoshop), en float32 lineal sobre sRGB como hace Photoshop por defecto, es decir, en el espacio de la imagen sin linealizar.

### Motor (sin Qt)

- **`motor/fusion.py`:** `fusionar(fondo_rgb, fondo_alfa, capa_rgb, capa_alfa, modo, opacidad, mascara=None) -> (rgb, alfa)`, en float32 de 0 a 1, vectorizado. Más `MODOS_FUSION` (clave → nombre en español).
- **`motor/documento.py`:**
  - **Dataclasses congeladas** (pickle-seguras, para el historial y la sesión): `Transformacion(x, y, escala, rotacion, voltear_h)`, `CapaImagen(id, nombre, ruta_o_datos, transform, visible, bloqueada, opacidad, fusion, mascara)`, `CapaFoto(...)`, `CapaAjusteNatural(...)` y `Documento(ancho, alto, capas)`.
  - **Funciones puras** que devuelven documentos nuevos: agregar, quitar, mover en la pila, duplicar y cambiar propiedades.
  - **Las imágenes de las capas** se guardan por **referencia de contenido**: un id más un almacén en memoria (`AlmacenImagenes`), así el historial no copia megas en cada paso.
- **`componer(documento, escala, fuente_foto, filtro) -> rgb`:**
  - compone de abajo hacia arriba;
  - aplica el ajuste "Celular natural" al final con el motor de siempre (`procesar_pila`);
  - tiene una **caché por capa y por escala**: mover una capa no recalcula el filtro de las demás, y el filtro se recalcula solo si cambia lo de abajo.
  - Vista previa a escala de pantalla; exportación a resolución completa (exportación = vista, como hoy).
- **Proyecto `.nslite`:**
  - zip con `documento.json` (versión de formato), las imágenes de las capas en PNG y las máscaras en PNG de 8 bits;
  - escritura atómica;
  - leerlo **no usa pickle**;
  - un proyecto roto da un error claro.

### Interfaz (modo Editor)

- **Panel "Capas"** a la derecha, arriba de los ajustes, con tarjetas como el resto:
  - cada fila: miniatura, ojo, nombre (doble clic para renombrar) y candado;
  - arriba: modo de fusión y opacidad de la capa elegida;
  - abajo: agregar imagen, duplicar, máscara, borrar, subir y bajar (también se arrastra para reordenar).
  - La capa "Celular natural" se ve siempre arriba con su ícono; su opacidad es "cuánto filtro".
- **Herramienta Mover / Transformar** (V): manijas en la vista para mover, escalar (Mayús = libre / proporcional) y rotar, más voltear horizontal. Enter aplica y Esc cancela. Las flechas mueven de a 1 px (de a 10 con Mayús).
- **Máscaras:** "Agregar máscara" (blanca) en la capa elegida. Para pintarla se reusan las herramientas de zona (rectángulo, elipse, lazo y pincel con borde suave), en modo "mostrar" u "ocultar", más "Mostrar todo", "Ocultar todo" e "Invertir".
- **Agregar imágenes:** "Agregar imagen como capa…", o arrastrar una imagen **sobre la vista** con Ctrl apretado (sin Ctrl, se suma a la tira como hoy). Entra centrada y ajustada al documento.
- **Archivo:**
  - "Guardar proyecto" (Ctrl+S) y "Abrir proyecto" (`.nslite`, también arrastrándolo);
  - "Exportar" aplana todo a PNG o JPG, como hoy;
  - la sesión recuerda los documentos con sus capas, como hoy las fotos.
- **Historial:** cada cambio de capas es un paso (agregar, borrar, mover en la pila, transformar, opacidad, fusión y máscara), con Ctrl+Z / Ctrl+Y.
- **Modo Fácil:** no muestra capas. El estilo elegido es la capa "Celular natural". Si el documento tiene capas extra, Fácil las respeta (se ven) y avisa con la nota de "ediciones del editor", como hoy.

### Errores

- **Imagen que no se puede abrir:** aviso y nada cambia.
- **Proyecto roto o de una versión futura:** aviso y no se abre.
- **Falta una imagen en el proyecto:** la capa queda marcada "falta" y vacía.
- **Memoria:** documentos de hasta unos 40 MP con 10 capas en una PC de 16 GB; la vista previa siempre a escala.

### Pruebas

- **Motor:**
  - cada modo de fusión contra valores de referencia calculados a mano (y opacidad 0 y 1, alfa, máscara);
  - componer: una capa normal = la foto; el orden importa; ocultar o mostrar; transformaciones (posición, escala, rotación) contra OpenCV; el filtro al final es igual a hoy cuando no hay capas extra (**regresión: misma salida bit a bit que la versión actual**);
  - caché: mover una capa no recalcula el filtro de abajo más de lo necesario;
  - proyecto: guardar y abrir da el mismo documento, archivos rotos, versión futura y sin pickle.
- **Interfaz:**
  - panel de capas: agregar, reordenar, opacidad, fusión, máscara, ocultar, renombrar y borrar;
  - Mover/Transformar con el mouse simulado;
  - historial;
  - Fácil sin capas extra exporta igual que hoy;
  - sesión y proyecto.
- **Capturas** a 1366 y 1600 px, revisadas.
