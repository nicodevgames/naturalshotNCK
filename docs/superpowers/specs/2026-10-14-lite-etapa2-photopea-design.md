# NaturalShot Lite, Etapa 2: "Photopea de verdad"

Fecha: 14/10/2026. Estado: aprobado por el dueño ("todo quiero todooo").

## Para qué

El modo Photoshop de la Etapa 1 tiene capas, pero no se parece a Photopea: arranca con una foto y no tiene texto, formas, menú ni herramientas de pintura. El dueño quiere, **literalmente, Photoshop o Photopea**. El caso de prueba es **armar un flyer con 4 fotos**, texto y formas. Después aplica el filtro anti IA (en Fácil o Editor), como siempre.

Esta etapa trae **todo lo que hace falta para trabajar como en Photopea**, salvo:
- selección avanzada y retoque (varita, selección rápida, tampón, parche, sobreexponer y subexponer): Etapa 3;
- ajustes clásicos (niveles, curvas…): Etapa 4;
- PSD: Etapa 5.

## Qué trae

### Documento

- **Archivo › Nuevo:**
  - tamaños listos: A4 (2480×3508), carta, post cuadrado 1080×1080, post vertical 1080×1350, historia 1080×1920, portada 1920×1080, banner 1500×500 y personalizado (ancho, alto, píxeles);
  - fondo: blanco, negro, transparente o un color;
  - el documento nuevo **no tiene foto base**: su capa de abajo es un **fondo** (relleno de color).
- **Abrir o arrastrar varias imágenes:**
  - en el modo Photoshop, si hay un documento abierto, entran **como capas**, cada una ajustada al lienzo y en cascada;
  - si no hay documento, la primera abre el documento y las demás entran como capas;
  - "Archivo › Abrir como capas…" hace lo mismo desde un diálogo.
- **Imagen:**
  - **Tamaño del lienzo** (agrega o recorta bordes, con un anclaje de 3×3);
  - **Tamaño de imagen** (escala todo);
  - **Recortar** (herramienta);
  - **Rotar el lienzo** 90° y 180°, y voltear.

### Capas (amplía la Etapa 1)

- **Tipos nuevos:**
  - **Texto:** el contenido (varias líneas) más fuente, tamaño, color, negrita y cursiva, alineación (izquierda, centro, derecha), interlineado y espaciado. Se puede editar después (es texto vivo, no píxeles).
  - **Forma:** rectángulo (con radio de esquinas), elipse, línea, flecha, polígono y estrella. Tiene relleno (color, degradado o sin relleno) y trazo (color y grosor). Es vectorial y se puede editar.
  - **Relleno:** un color o un degradado (lineal o radial, de dos o más colores) que cubre el lienzo; sirve de fondo o se usa con máscara.
  - **Píxeles:** una capa vacía o rasterizada, donde se pinta con pincel, borrador y bote.
  - **Grupo:** una carpeta con su propia opacidad, fusión, visibilidad y máscara.
- **Rasterizar:** pasa texto o forma a píxeles.
- **Transformación libre:**
  - escala X e Y por separado (Mayús mantiene la proporción, como Photoshop moderno), rotación, volteo horizontal y vertical;
  - para todo tipo de capa (texto y formas se re-renderizan, no se pixelan).
- **Estilos de capa** (doble clic en la capa o "Capa › Estilo de capa…"):
  - sombra paralela (color, opacidad, ángulo, distancia, tamaño);
  - trazo (color, grosor, afuera, adentro o centro);
  - resplandor exterior;
  - superposición de color;
  - superposición de degradado.
  - Cada uno se prende y apaga.
- **Alinear y distribuir:** la capa respecto del lienzo, o varias capas elegidas entre sí. Izquierda, centro, derecha, arriba, medio y abajo; distribuir en horizontal y en vertical.
- **Imán y guías inteligentes:** al mover, las capas se pegan al centro y los bordes del lienzo y de otras capas, con líneas guía magenta.
- **Selección múltiple de capas** (Ctrl+clic y Mayús+clic) para mover, alinear, agrupar o borrar.
- **Panel Capas:**
  - grupos plegables con sangría;
  - un ícono por tipo;
  - fx cuando hay estilos;
  - menú contextual: duplicar, borrar, agrupar, desagrupar, rasterizar, estilo de capa, combinar hacia abajo y acoplar.

### Herramientas (barra izquierda, como Photopea)

| Herramienta | Tecla | Qué hace |
|---|---|---|
| Mover | V | Elegir, mover y transformar capas (con "selección automática" al hacer clic en la vista); imán y guías |
| Recortar | C | Recorta el lienzo (proporciones como el recorte de hoy) |
| Texto | T | Clic para escribir y arrastrar para una caja; editar en el lugar |
| Formas | U | Rectángulo, elipse, línea, flecha, polígono y estrella (submenú) |
| Pincel | B | Pinta en una capa de píxeles (tamaño, dureza, opacidad, color de frente) |
| Borrador | E | Borra en una capa de píxeles (a transparente) |
| Bote de pintura | G | Rellena por color parecido (tolerancia) en una capa de píxeles |
| Degradado | G (con Mayús) | Arrastrar para un degradado lineal o radial: nueva capa de relleno, o pinta en la de píxeles |
| Cuentagotas | I | Toma el color de la composición y lo pone como frente |
| Mano | H, o Espacio sostenido | Desplazar la vista |
| Zoom | Z | Clic para acercar y Alt+clic para alejar |
| Máscara | (botones) | Lo de la Etapa 1: rectángulo, elipse, lazo y pincel sobre la máscara |

- **Colores de frente y fondo** debajo de la barra (los dos cuadraditos), con intercambiar (X) y restablecer (D). Un clic abre un **selector de color** propio: cuadro de saturación y brillo, barra de tono, hexadecimal, RGB y muestras recientes.
- **Barra de opciones** arriba de la vista: cambia según la herramienta (como Photopea). Fuente y tamaño para Texto; relleno, trazo y radio para Formas; tamaño, dureza y opacidad para Pincel; etc.

### Menú arriba (en el modo Photoshop)

- **Archivo:** Nuevo, Abrir, Abrir como capas, Guardar proyecto, Guardar como, Exportar (PNG o JPG, con o sin el filtro celular natural).
- **Editar:** Deshacer, Rehacer, Cortar, Copiar, Pegar (pega imágenes del portapapeles como capa nueva), Duplicar capa, Borrar capa, Transformación libre.
- **Imagen:** Tamaño de imagen, Tamaño del lienzo, Rotar lienzo, Voltear lienzo, Recortar.
- **Capa:** Nueva capa de píxeles, Nueva capa de relleno, Duplicar, Borrar, Agrupar, Desagrupar, Rasterizar, Estilo de capa, Máscara, Alinear, Distribuir, Combinar hacia abajo, Acoplar imagen.
- **Ver:** Acercar, Alejar, Ajustar a la ventana, 100 %, Mostrar guías inteligentes, Mostrar bordes del lienzo.

### Panel Propiedades (derecha, arriba de Capas)

Muestra lo de la capa elegida:
- **texto:** fuente, tamaño, color, estilo y alineación;
- **forma:** tipo, relleno, trazo y radio;
- **relleno:** colores y ángulo;
- **cualquier capa:** posición X/Y, ancho y alto, y rotación, con números editables.

## El filtro anti IA

Como en la Etapa 1: el filtro celular natural es la capa de arriba de todo y se elige en Fácil o Editor. Un documento creado con "Nuevo" también va a Fácil y Editor: su composición es la "foto" que entra al filtro. "Exportar" en el modo Photoshop ofrece **con filtro** (el elegido) o **sin filtro**.

## Arquitectura

- **Motor, sin Qt salvo donde se diga:**
  - `motor/documento.py` (ampliado, compatible hacia atrás con los `.nslite` de la Etapa 1):
    - tipos `texto`, `forma`, `relleno`, `pixeles` y `grupo`;
    - `Transformacion` con `escala_y` y `voltear_v` (si faltan, igual a la Etapa 1);
    - `EstilosCapa`;
    - un documento con fondo de relleno en lugar de foto (la capa de abajo puede ser `foto` o `relleno`);
    - grupos con `padre`;
    - operaciones de lienzo (tamaño, recorte, rotación);
    - combinar y acoplar.
  - `motor/texto.py`: dibuja texto a RGBA con FreeType de **Pillow**, con las fuentes instaladas en Windows (`C:\Windows\Fonts`, que es del sistema, no del usuario) y una lista de familias. Si no hay Pillow con FreeType, QPainter sobre QImage (funciona en hilos sin pantalla).
  - `motor/formas.py`: las formas a RGBA, con antialias (rasterizado por OpenCV con sobremuestreo, o QPainterPath), relleno, degradado y trazo.
  - `motor/estilos.py`: sombra, trazo, resplandor y superposiciones a partir del RGBA de la capa.
  - `motor/pintura.py`: trazos de pincel y borrador (en coordenadas de la capa, con dureza y opacidad), bote de pintura (inundación con tolerancia, vectorizada con `cv2.floodFill`) y degradado.
  - `motor/proyecto_lite.py`: formato 2 (abre el 1).
- **Interfaz:**
  - El modo Photoshop pasa a su **propio módulo**, `ui/modo_photoshop.py` (como `modo_audio.py`), para que `ventana.py` no siga creciendo.
  - Más piezas en archivos propios: `ui/herramientas_ps.py` (barra izquierda y colores), `ui/opciones_ps.py` (barra de opciones), `ui/propiedades_ps.py`, `ui/menu_ps.py`, `ui/selector_color.py`, `ui/estilos_capa.py` (diálogo) y `ui/nuevo_documento.py` (diálogo).
- **Rendimiento:**
  - texto y formas se cachean por sus parámetros y la escala;
  - pintar con pincel es interactivo: el trazo se muestra en una superposición mientras se arrastra y se aplica al soltar.

## Orden de trabajo

1. **En paralelo, cuando terminen los arreglos de la Etapa 1:**
   - **M1:** `documento.py` ampliado y `estilos.py`.
   - **M2:** `texto.py`, `formas.py` y `pintura.py`.

   Son archivos distintos. M1 usa las funciones de M2 según un contrato fijo.
2. **U1** (cuando terminen los arreglos de L1b):
   - el modo Photoshop en `ui/modo_photoshop.py`;
   - menú, Nuevo documento, abrir varias como capas;
   - barra de herramientas con Mover libre, Mano, Zoom, Cuentagotas y colores;
   - barra de opciones, Propiedades, alinear e imán, selección múltiple y grupos en el panel.
3. **U2** (después de U1, cuando estén M1 y M2): Texto, Formas, Relleno o Degradado y estilos de capa.
4. **U3** (después de U2): Pincel, Borrador, Bote, Recortar, Tamaño de lienzo e imagen, Rotar y voltear el lienzo, Combinar y acoplar, Pegar del portapapeles.
5. **Cierre:** revisión, tutorial (otra sesión) y compilar la Lite.

**Siempre:** pruebas, capturas a 1366 y 1600 px revisadas, arranque real y suite completa (la PRO no cambia).

## Prueba de aceptación (el flyer)

Una prueba con la ventana real (offscreen) arma un flyer, lo exporta y verifica que el PNG tenga cada elemento donde va:
1. Nuevo, historia 1080×1920, fondo con degradado.
2. Abrir 4 fotos generadas como capas.
3. Acomodarlas en una grilla con imán.
4. Un título con texto, sombra y trazo.
5. Un rectángulo redondeado como banda con texto encima.
6. Una estrella.
7. Exportar.

También se guardan capturas para el tutorial.
