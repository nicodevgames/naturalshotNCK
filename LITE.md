# NaturalShot Lite

**NaturalShot Lite** es la edición **solo de fotos** de NaturalShot, que va creciendo por etapas hasta ser un editor tipo Photoshop/Photopea. Trae todo lo de fotos de la PRO (modo Fácil y modo Editor, presets, efectos apilados y zonas, montaje, fondo, borrar objetos, girar y enderezar, selección automática, tira de fotos, historial, sesión y exportar) y suma **capas de verdad**. El flujo pensado: primero se arma la foto como en Photoshop (capas, retoque, texto) y **al final** se aplica el filtro "celular natural" (por ejemplo, iPhone 13) **sobre el resultado entero**.

Es el mismo código que la PRO (que está en pausa y sigue andando, con Video y Audio): la edición se decide en `celular_natural/edicion.py`. Diseño: `docs/superpowers/specs/2026-10-14-naturalshot-lite-design.md`; plan: `docs/superpowers/plans/2026-10-14-naturalshot-lite.md`.

## Cómo se abre

- **Acceso directo:** `NaturalShot Lite.lnk`, en esta carpeta (apunta a `dist_lite\NaturalShot Lite\NaturalShot Lite.exe`).
- **Para otra PC:** `NaturalShot Lite - para otra PC.zip`.
- **Desde el código:** `ejecutar_lite.bat`, o `NATURALSHOT_EDICION=lite` y `.venv\Scripts\python main.py`.
- **Compilar:** `construir_lite.bat` (compila en `dist_lite\`, arma el zip y el acceso directo; no toca `dist\` ni `build\` de la PRO).

## Etapas

| Etapa | Qué trae | Estado |
|---|---|---|
| 0 | La edición Lite: sin Video ni Audio, datos y `.exe` propios | ✅ |
| 1 | Capas de verdad: panel Capas, mover y transformar, máscaras, fusión y proyecto `.nslite` | ✅ |
| 2 | "Photopea de verdad": Nuevo documento, menú, herramientas, texto, formas, pintura, grupos y estilos (diseño: `docs/superpowers/specs/2026-10-14-lite-etapa2-photopea-design.md`) | ✅ motor (M1, M2), U1 (menú, Nuevo, herramientas, Propiedades, grupos e imán), U2 (texto, formas, rellenos con degradado, estilos de capa y selector de color) y U3 (pincel, borrador, bote, degradado y recortar como herramienta); falta el cierre (revisión y tutorial) |
| 3 | Selección avanzada y retoque (varita, selección rápida, tampón, parche…) | después |
| 4 | Ajustes clásicos como capas de ajuste (niveles, curvas…) | después |
| 5 | Abrir y guardar PSD | después |

## Capas (etapa 1)

Cada foto de la tira es un **documento** con su pila de capas, de abajo hacia arriba:

- **Foto** (abajo, una sola): la foto con todo lo de siempre (geometría, montaje, borrados, recorte y fondo), como un "objeto inteligente". No se borra, pero se puede ocultar o bajarle la opacidad.
- **Imágenes** (las que quieras): otra foto, un PNG con transparencia o un logo. Cada una con posición, escala, rotación y volteo.
- **Celular natural** (arriba de todo, una sola): el filtro de siempre (preset, intensidad, efectos y ajustes del panel derecho), aplicado **sobre todo lo de abajo**.

Lo que antes se llamaba **"Capas"** (presets extra apilados encima del base) ahora se llama **"Efectos"**: es parte del filtro, no del documento.

### El modo Photoshop

El flujo del dueño: **"edito la foto como en Photoshop y después le pongo los filtros anti IA"**. Por eso las capas tienen su propio modo en el selector: **Fácil | Editor | Photoshop** (solo en la Lite; **Ctrl+Shift+P** va y vuelve, y se recuerda como Fácil y Editor).

- **En Photoshop** se edita la foto con capas y la vista muestra **la composición sin el filtro**. Sin Antes ni Después (no hace falta): solo la imagen, con zoom y "ver la foto completa". El botón chico **"Ver con el filtro"** (cabecera de la vista) la previsualiza con el filtro, sin cambiar nada.
- **En Fácil y en Editor** la foto que entra al filtro es **la composición del modo Photoshop**, y el filtro va arriba de todo. Su **"Antes"** es la composición sin el filtro. Sin capas extra, todo da **exactamente** lo de siempre.
- **El Editor** quedó como antes (sin panel de capas, con los "Efectos"): sus herramientas de la foto base (girar, enderezar, recortar, montaje, borrar objetos, fondo y zonas de los efectos) actúan sobre la capa "Foto".

**Distribución del modo Photoshop (tipo Photopea):**

| Lugar | Qué hay |
|---|---|
| Izquierda (debajo del logo y del selector) | Una barra vertical angosta: **Mover (V)**, **Recortar (C)**, **Texto (T)**, **Formas (U)**, **Pincel (B)**, **Borrador (E)**, **Bote y Degradado (G, Mayús+G; un botón)**, **Mano (H)**, **Zoom (Z)**, **Cuentagotas (I)** y, separadas, las de la máscara: **Rectángulo**, **Elipse**, **Lazo** y **Pincel**. Abajo, los **colores de frente y fondo** (X intercambia, D vuelve a negro y blanco, clic elige). Al lado, el **Historial** (el mismo de toda la app). |
| Centro | El **menú** (Archivo, Editar, Imagen, Capa, Ver) arriba, con deshacer y rehacer y el kit (Nuevo, Agregar imagen, Texto, Quitar fondo, Recortar); la **barra de opciones** de la herramienta arriba de la vista; la vista grande (sin el filtro) y la tira abajo. |
| Derecha | **Propiedades** (X, Y, ancho, alto y rotación de la capa elegida; colores y ángulo de un relleno) y el panel **Capas** (fusión y opacidad arriba, la lista con grupos en el medio y los botones abajo). |

### Etapa 2, U1: el modo Photoshop de verdad (14/10/2026)

El modo vive en su propio módulo, `ui/modo_photoshop.py` (la ventana guarda el documento, el historial, la vista, la sesión y el proyecto; el módulo arma el menú, las herramientas, la barra de opciones y Propiedades, y hace las operaciones con la API del motor). **Cada operación es un paso del historial.**

- **Nuevo (Ctrl+N):** el diálogo de siempre del kit (post, post vertical, historia, A4, **carta**, portada, **banner** o a medida) con el fondo **blanco, negro, transparente, un color o un degradado**. Crea un documento de verdad, **sin foto** (`Documento.nuevo_lienzo`): ya no se escribe ningún PNG. Entra a la tira como una foto más (con una "ruta" que no es un archivo: `Sin título 1.nsdoc`), y la sesión, el proyecto `.nslite` y exportar lo tratan como a cualquier foto.
  - En **Fácil y Editor**, su composición es la "foto" que entra al filtro. Las herramientas de la foto de base (**recortar y enderezar del Editor, montaje, borrar objetos y fondo**) quedan **deshabilitadas** con una nota ("es un documento nuevo, sin foto…"); **girar y voltear** sí andan: giran el lienzo (`rotar_lienzo`, `voltear_lienzo`). Las zonas de los efectos se marcan igual.
  - Con el fondo **transparente**, la vista muestra el tablero y **exportar da un PNG con transparencia** (el alfa sale de componer dos veces, sobre negro y sobre blanco: exacto con capas en modo normal).
- **Menú:**
  - **Archivo:** Nuevo, Abrir, **Abrir como capas** (Ctrl+Mayús+O; sin documento, la primera abre y las demás van como capas), Abrir proyecto, Guardar proyecto, Guardar como, **Exportar con el filtro** y **Exportar sin el filtro**.
  - **Editar:** Deshacer, Rehacer, **Pegar como capa** (Ctrl+V: una imagen del portapapeles, o archivos de imagen copiados), Duplicar (Ctrl+J), Borrar (Supr) y **Transformación libre** (Ctrl+T).
  - **Imagen:** **Tamaño de imagen** (Ctrl+Alt+I, en px o %), **Tamaño del lienzo** (Ctrl+Alt+C, con el **ancla de 3 × 3** y "relativo"), Rotar lienzo (90° horario y antihorario, 180°), Voltear lienzo (H y V) y **Recortar** (desde U3, elige la herramienta Recortar: ver abajo).
    - En una **foto** (con su edición no destructiva) rotar, voltear y recortar usan la geometría y el recorte de siempre (la foto se conserva); **tamaño de imagen, tamaño del lienzo y acoplar** arman un **documento nuevo** en la tira (la foto pasa a una capa de píxeles y queda como estaba en su entrada).
  - **Capa:** Nueva capa de píxeles (Ctrl+Mayús+N) o de relleno (con el color de frente), Duplicar, Borrar, **Agrupar (Ctrl+G)**, **Desagrupar (Ctrl+Mayús+G)**, **Rasterizar**, Máscara (agregar, mostrar u ocultar todo, invertir, quitar), **Alinear** (6) y **Distribuir** (H y V), **Combinar hacia abajo** y **Acoplar imagen**.
  - **Ver:** Acercar, Alejar, Ajustar, 100 % y **Guías inteligentes** (el imán, prendido o apagado).
- **Herramientas:** **Mover** (V), **Mano** (H; también **Espacio sostenido**, con cualquier herramienta), **Zoom** (Z: clic acerca, Alt+clic aleja), **Cuentagotas** (I: el color de lo que se ve pasa a frente; muestra de 1 px, 3 × 3 o 5 × 5) y las de la máscara. **Texto** (T) y **Formas** (U) llegaron en U2; **Pincel**, **Borrador**, **Bote**, **Degradado** y **Recortar**, en U3 (ver abajo).
- **Barra de opciones** (cambia con la herramienta): en Mover, **Selección automática** (un clic elige la capa de arriba que tiene algo visible bajo el mouse: se mira el alfa y la máscara), **Mostrar controles** (las manijas de la capa elegida) y los botones de **alinear** y **distribuir**; en Mano y Zoom, sus atajos; en el Cuentagotas, la muestra; en la máscara, si lo pintado se ve o se oculta y el pincel (tamaño, dureza, goma, cancelar y listo); al recortar un documento, la proporción, Aplicar y Cancelar.
- **Mover:** arrastrar mueve la capa (o **todas las elegidas**); cada gesto es un paso ("Capa «x» movida", "2 capas movidas"). Las flechas corren lo elegido de a 1 px (10 con Mayús). Con **Mostrar controles**, las manijas escalan con **escala libre** (X e Y por separado; **Mayús** en una esquina mantiene la proporción; Alt, desde el centro) y rotan. La **transformación libre** (Ctrl+T) es la de la Etapa 1 (Enter aplica, Esc cancela), ahora para imagen, píxeles, texto y forma, con escala libre y **voltear vertical**.
- **Imán y guías inteligentes:** al mover, la caja de lo que se mueve se pega (a 7 px de pantalla o menos) al **centro y los bordes del lienzo** y a los bordes y centros de **las otras capas** (`caja_capa`), con **líneas magenta** mientras se arrastra (`ui/iman.py`).
- **Selección múltiple:** Ctrl+clic y Mayús+clic en el panel Capas (o Mayús+clic en la vista); se mueven, alinean, agrupan y borran juntas.
- **Panel Capas:** **grupos plegables con sangría**, un **ícono por tipo** (imagen, píxeles, texto, forma, relleno, grupo), **"fx"** si la capa tiene estilos, **menú contextual** (duplicar, borrar, agrupar, desagrupar, rasterizar y combinar hacia abajo) y **arrastrar** para reordenar, **adentro de un grupo** (soltando sobre él) o afuera (`Documento.reubicar`). Un botón nuevo agrupa.
- **Propiedades:** X e Y (la caja de la capa en el lienzo), ancho y alto (con la cadena, en proporción) y rotación, editables; de un **grupo o varias capas**, X e Y mueven todo. En un **relleno** (también el fondo de un documento nuevo): color, degradado lineal o radial (sus dos colores) y el ángulo.

### Etapa 2, U2: texto, formas, degradados, estilos de capa y selector de color (14/10/2026)

- **Texto (T)** en la barra de herramientas (y el botón **Texto** del kit, que ahora elige la herramienta; los textos que el kit hizo antes eran imágenes y siguen siéndolo):
  - **un clic** crea una capa `texto` con la línea base del primer renglón donde se hizo clic; **arrastrar** crea una **caja**: el texto se corta a ese ancho (`ancho_caja`);
  - **se escribe en el lugar**: un campo transparente sobre la vista, a su escala, con el cursor; lo que se ve es **la capa de verdad**, que se vuelve a dibujar con cada tecla (con sus estilos). **Enter** es otro renglón; **Esc**, **Ctrl+Enter** o **un clic afuera** terminan: un paso ("Texto nuevo", "Texto cambiado"; vacío, no se crea o se borra);
  - mientras se escribe, todas las teclas son del texto (V, X, Supr, Ctrl+Z… no disparan los atajos de la ventana) y el Espacio es un espacio;
  - **doble clic** sobre un texto (con Mover o Texto, en la vista) o en **su miniatura** del panel lo vuelve a editar; con la herramienta Texto, un clic sobre un texto también;
  - el texto no "salta" al cambiar: queda fijo su **ancla** (arriba a la izquierda, al centro o a la derecha, según la alineación);
  - la capa se llama como su primer renglón.
- **Barra de opciones de Texto** (y lo mismo en **Propiedades** de una capa de texto): familia (un combo con búsqueda: escribí parte del nombre), tamaño (px), color, negrita, cursiva, alineación (3 botones), interlineado (× el tamaño) y espaciado (px). Con un texto elegido, cada cambio lo modifica (un paso); siempre queda para el próximo. Elegir un texto pasa su estilo a la herramienta, y el color de frente es el del próximo texto.
- **Formas (U)**: rectángulo, elipse, línea, flecha, polígono y estrella (en la barra de opciones o con **clic derecho** en el botón). **Arrastrar** la dibuja (**Mayús**: 1:1, o de a 45° en la línea y la flecha; **Alt**: desde el centro); un paso ("Forma nueva: Rectángulo 1") y queda elegida.
  - **Barra de opciones**: el tipo (de la herramienta: no cambia la forma elegida), el **relleno** (sin relleno, color o degradado lineal o radial; el color de frente por defecto), el **trazo** (color y grosor) y el radio (rectángulo), los lados (polígono), las puntas (estrella) o el grosor (línea) y el alto (flecha). Con una forma elegida, relleno, trazo y lo demás la cambian (un paso).
  - **Propiedades** de una forma: lo mismo, y ahí el tipo sí cambia la forma.
- **Rellenos con degradado**: en Propiedades de un relleno (la capa de "Capa › Nueva › Capa de relleno" o el fondo de un documento), el tipo (color, lineal, radial o transparente), los colores con su **posición** (de 2 a 4: "+ Color" y la ✕ de cada uno), el ángulo y una muestra. El mismo editor está en el relleno de las formas (un diálogo) y en la superposición de degradado.
- **Estilo de capa** (`ui/estilos_capa.py`): **doble clic en la capa** del panel, el botón **fx** de abajo del panel, el "fx" de la fila, el menú contextual o **"Capa › Estilo de capa…"**. A la izquierda, los estilos con su tilde: **Sombra paralela** (color, opacidad, ángulo, distancia y tamaño), **Trazo** (color, grosor, afuera, adentro o centro, y opacidad), **Resplandor exterior** (color, opacidad y tamaño), **Superposición de color** (color y opacidad) y **Superposición de degradado** (el degradado y la opacidad). Tocar un valor prende ese estilo; destildarlo lo apaga sin perder los valores. **Vista previa en vivo** sobre el lienzo; **Aceptar** es un paso ("Estilo de capa: «x»") y **Cancelar** deja todo como estaba. El diálogo aparece a la izquierda, para que el lienzo quede a la vista.
  - **Renombrar** pasó a **F2** (o "Cambiar el nombre…" del menú contextual): el doble clic en la fila es el estilo de capa (como Photoshop).
- **Selector de color propio** (`ui/selector_color.py`), en vez del de Windows, para los colores de frente y fondo, todos los de texto, formas, rellenos y estilos y los del diálogo Nuevo: cuadro de **saturación y brillo**, barra de **tono**, barra de **alfa** (en los colores que la llevan), **hexadecimal** (`rrggbb` o `rrggbbaa`), **R, G, B** y **A** (%), el color nuevo y el de antes, **muestras recientes** (se recuerdan en la configuración) y un **cuentagotas** (tocalo y hacé clic donde está el color: sobre la vista toma el de la composición que se ve; Esc cancela).

### Etapa 2, U3: pincel, borrador, bote, degradado y recortar (14/10/2026)

- **Pincel (B)**: pinta con el **color de frente** en la capa elegida.
  - En una capa de **píxeles** o una **imagen** (también son píxeles), ahí mismo. Sobre un **texto**, una **forma** o un **relleno**, pregunta **"¿Rasterizar la capa?"** (como Photoshop): con Sí la pasa a píxeles (un paso) y el próximo trazo ya pinta. Sobre la **base** (la Foto o el Fondo), un **grupo** o nada elegido, el trazo va a una **capa de píxeles nueva** encima (en el mismo paso: "Pincel: capa nueva «Capa 1»"). Una capa oculta o con candado avisa.
  - **Mientras se arrastra**, el trazo se ve en una **superposición** sobre la vista (solo el pedazo que cambió; no se recompone el documento): fluido aun en 4000 × 3000 (0,3 ms por movimiento). Al **soltar** se aplica de verdad (`pintura.trazo`, unos 70 ms en 12 MP) y es **un paso** ("Pincel en «Capa 1»"). La superposición queda hasta que llega la vista con el trazo (no parpadea).
  - Si se pinta **afuera de la capa** (una imagen chica, o una capa de píxeles después de agrandar el lienzo), la capa **crece** lo justo (sin pasar del lienzo) y lo de antes queda en su lugar.
  - **Barra de opciones**: tamaño (deslizador y número, en px del documento), **dureza** y **opacidad**. **[** y **]** achican y agrandan (de a 1 hasta 10, de a 5 hasta 50, de a 10 hasta 100…). El **cursor** es un círculo del tamaño del pincel (con una cruz si es chico).
- **Borrador (E)**: lo mismo, **a transparente** (mientras se arrastra se ve el tablero). No agranda la capa; sobre la base avisa (no se borra la foto ni el fondo). Tiene su propio tamaño, dureza y opacidad.
- **Bote de pintura (G)**: un clic rellena con el color de frente lo parecido al clic (`pintura.bote`). Opciones: **tolerancia** (0 a 255), **contiguo** (solo la zona unida al clic; sin tildar, todos los parecidos) y **"Todas las capas"** (la zona sale de la composición que se ve; el relleno va igual en la capa elegida). Sobre la base, va a una capa nueva y la zona siempre sale de lo que se ve.
- **Degradado (Mayús+G**, o clic derecho en el botón del Bote: comparten el botón, que muestra el último usado): arrastrar de p0 a p1 (**Mayús**: de a 45°), con una línea y los dos colores mientras se arrastra.
  - En una capa de **píxeles** (o imagen) **lo pinta** encima (con la opacidad).
  - Si no, crea una **capa de relleno** "Degradado 1" encima de la elegida: **lineal**, con el ángulo de p0 a p1 y las paradas corridas para que empiece en p0 y termine en p1 (se sigue editando en Propiedades). Un **radial** (su centro en p0) o uno que necesitaría más de 4 colores va a una **capa de píxeles** (un relleno de la app solo hace radiales centrados).
  - **Barra de opciones**: Lineal o Radial, los **colores** (por defecto **de frente a fondo**, y los sigue si cambian; clic en la muestra: el editor de degradado de U2, de 2 a 4 colores; "Frente → fondo" vuelve a esos) y la opacidad.
- **Recortar (C)**: un **recuadro con 8 manijas** sobre el lienzo (empieza en todo el lienzo): las manijas lo ajustan, adentro se mueve y afuera se arrastra uno nuevo; lo de afuera se oscurece, con la regla de los tercios y la medida. **Proporción** en la barra (libre, original, 1:1, 4:5, 3:4, 9:16, 4:3, 16:9 y 3:1; en libre, Mayús en una esquina mantiene la del recuadro). **Enter**, **Aplicar** o **doble clic adentro** aplican (un paso: "Lienzo recortado: 980 × 980 px") y **Esc** o **Cancelar** vuelven al lienzo entero; la herramienta sigue elegida.
  - En un documento, con `documento.recortar` (el recuadro puede salirse del lienzo: agrega borde).
  - En una **foto**, con su **recorte no destructivo** de siempre (el del Editor): el recuadro no se sale de la foto, se suma al recorte que ya tenía, las capas siguen sobre el mismo lugar de la foto y se puede deshacer o cambiar desde el Editor.
  - **Reemplaza** al botón Recortar del kit (ya no lleva al Editor) y a "Imagen › Recortar".
- **Pegar (Ctrl+V)**: también lo que copian **otras apps**: la imagen del portapapeles o, si no, los bytes de un PNG (con su transparencia: se prefiere el PNG cuando está), JPG, WEBP, GIF o BMP. **Sin documento abierto**, la imagen pegada abre un **documento nuevo** de su tamaño (fondo transparente).
- **Memoria del historial**: cada trazo (o bote, o degradado en una capa) es una imagen entera de la capa; las de los pasos que no se ven se guardan **comprimidas** (como las máscaras), así cien trazos no llenan la memoria.

### Cómo se usa

1. **Agregar una imagen:** **Agregar imagen** en la barra o el primer botón de abajo del panel **Capas** (PNG con transparencia, JPG, WEBP…), o **soltala sobre la foto**: en el modo Photoshop entra como capa; en Fácil y Editor, **con Ctrl** entra como capa y sin Ctrl se suma a la tira, como siempre. Entra centrada y achicada para que entre. Como mucho 100 MP por imagen.
2. **El panel Capas:**
   - la capa de arriba se ve arriba, como en Photoshop: arriba de todo, **"Filtro celular natural"**, atenuado y bloqueado (se elige en Fácil o Editor); abajo, la "Foto";
   - cada fila: **ojo** (ver u ocultar), miniatura (y la de la máscara), **nombre** (**F2** para renombrar; el doble clic abre el estilo de capa), el modo de fusión y la opacidad, y **candado**;
   - arriba: el **modo de fusión** (Normal, Multiplicar, Trama, Superponer, Luz suave, Luz fuerte, Oscurecer, Aclarar, Sobreexponer y Subexponer color, Diferencia, Exclusión, Tono, Saturación, Color y Luminosidad) y la **opacidad** (0-100 %) de la capa elegida;
   - abajo: agregar imagen, **duplicar**, **máscara**, **Mover / Transformar**, **subir**, **bajar** y **borrar**. Las filas también se reordenan **arrastrando**;
   - las reglas de la pila las pone el motor: la foto no se borra ni se mueve, el filtro va siempre arriba. Lo que no aplica queda deshabilitado y, si igual se intenta, avisa.
   - Una capa con **candado** no se mueve, no se transforma, no se borra y no cambia su opacidad, su fusión ni su máscara (sí se puede ocultar y renombrar).
3. **Mover / Transformar** (**V** o el primer botón de la barra de herramientas):
   - **mover:** arrastrá la capa (con **Mayús**, solo en horizontal o vertical); las **flechas** la mueven de a 1 px (con Mayús, de a 10);
   - **escalar:** las manijas de las esquinas y de los lados. **Siempre mantiene la proporción** (como Photoshop moderno): el motor tiene una sola escala por capa, así que no se deforma. La esquina o el lado opuesto queda fijo; con **Alt**, desde el centro;
   - **rotar:** la manija redonda de arriba, o arrastrando apenas afuera de una esquina (con **Mayús**, de a 15°);
   - **Voltear** en la barra de la herramienta, arriba de la vista;
   - **Enter** (o **Aplicar**) aplica y queda como **un solo paso** del historial; **Esc** (o **Cancelar**) deja todo como estaba. Elegir otra herramienta o cambiar de capa aplica lo transformado.
   - Solo sobre capas de imagen sin candado.
4. **Máscaras:** elegí la capa y una herramienta de máscara (**rectángulo**, **elipse**, **lazo** o **pincel**, las mismas de las zonas de los efectos), y si lo que marcás **se ve** o **se oculta**. Si la capa no tenía máscara, se le crea una (blanca) al pintar. El botón de máscara del panel agrega una blanca o, si ya tiene, ofrece **Mostrar todo**, **Ocultar todo**, **Invertir** y **Quitar máscara**. La "Foto" también puede tener máscara.
5. **Historial:** cada cambio de capas es un paso (agregar, duplicar, borrar, subir o bajar, transformar, opacidad, fusión, máscara, ver u ocultar, renombrar y candado), en la misma lista de siempre, con **Ctrl+Z** y **Ctrl+Y**. Arrastrar el deslizador de opacidad es **un** paso (se ve mientras se arrastra y se anota al soltar).
6. **Girar, voltear, enderezar y recortar** (en el Editor) llevan las capas al marco nuevo: siguen sobre el mismo lugar de la foto (y sus máscaras también).
7. **Exportar** (**Ctrl+Shift+E** en la Lite, desde cualquier modo) aplana todo **con el filtro** a PNG o JPG: es lo que se ve en Fácil y en Editor.

### Proyecto `.nslite`

- **Ctrl+S** "Guardar proyecto" (en la Lite; en la PRO, Ctrl+S sigue exportando): la primera vez pregunta dónde (sugiere el nombre de la foto con `.nslite`); después guarda en el mismo archivo. **Ctrl+Shift+S** "Guardar proyecto como…". También en el botón con el disquete del modo Photoshop.
- **Abrir:** desde **Abrir** (el diálogo acepta `.nslite`), "Abrir proyecto…" del botón del disquete, **arrastrándolo** a la ventana o con **"Abrir con…"**. Si la foto ya estaba en la tira, el proyecto queda como un paso más de su historial (se puede deshacer).
- **Qué guarda:** el documento con sus imágenes y máscaras (PNG) y, aparte, la **ruta de la foto original** y **toda la edición** (preset, ajustes, efectos con sus zonas, recorte, geometría, montaje, borrados y fondo).
- **Si la foto original ya no está:** se abre igual, con un aviso: las capas quedan sobre un **fondo blanco** del mismo tamaño (`%APPDATA%\NaturalShot Lite\proyectos sin foto\`), sin la edición propia de la foto (recorte, giro, montaje, borrados y fondo), que no se puede rearmar sin ella.
- Un proyecto roto o de una versión más nueva avisa y no cambia nada. Una imagen que falta deja su capa marcada "Falta la imagen".

### Modo Fácil

No muestra capas. El estilo que se elige es la capa "Celular natural", arriba de todo. Si la foto tiene capas de imagen, la vista y **Exportar foto** las componen igual que el Editor (el "Antes" es la composición sin el filtro), y la nota "Esta foto tiene capas del modo Photoshop…" lo dice.

### Sesión

La sesión recuerda las capas de cada foto: el documento va en el estado (como siempre, en `sesion.pkl`) y sus imágenes y máscaras, como PNG en `%APPDATA%\NaturalShot Lite\sesion\imagenes\` (el nombre es el id del contenido: una imagen que ya estaba no se vuelve a escribir; las que ya no usa nadie se borran después de guardar). Escritura atómica y en segundo plano, como siempre. Las sesiones de antes se siguen leyendo.

## Por dentro

### Motor (sin Qt)

- `motor/fusion.py`: los 16 modos de fusión (fórmulas W3C Compositing, en float32 sobre sRGB sin linealizar, como Photoshop).
- `motor/documento.py`: `Documento`, `Capa`, `Transformacion` (dataclasses congeladas), `AlmacenImagenes` (por contenido) y `componer(doc, almacen, foto_rgb, escala, filtro, cache, *, clave_foto, clave_filtro)` con `CacheComposicion`.
- `motor/proyecto_lite.py`: `guardar_proyecto` y `abrir_proyecto` (zip con `documento.json`, `imagenes/` y `mascaras/`; sin pickle; escritura atómica).

### Interfaz

| Archivo | Qué hace |
|---|---|
| `ui/modo_photoshop.py` | **El modo Photoshop** (Etapa 2, U1): menú, barra de herramientas y colores, barra de opciones, columnas, el controlador de la vista (Mover con selección automática, imán y manijas; Mano; Zoom; Cuentagotas), Nuevo documento, las operaciones de Imagen y Capa, la transformación libre, el kit de flyers y las máscaras. |
| `ui/propiedades_ps.py` | El panel Propiedades (X, Y, ancho, alto, rotación y rellenos): pide cada cambio como una función documento → documento. |
| `ui/iman.py` | El imán y las guías inteligentes (sin Qt): objetivos (lienzo y otras capas) y cuánto correr una caja. |
| `ui/texto_ps.py` | (U2) El texto vivo: medidas de la caja (las mismas cuentas que `motor/texto.py`), el ancla que no se corre (`con_params_texto`), el nombre de la capa y la **edición en el lugar** (`EdicionTexto`, `EditorTexto`: un `QTextEdit` transparente con la misma fuente cargada en Qt; el documento provisorio se vuelve a dibujar con cada tecla). |
| `ui/pintura_ps.py` | (U3) La pintura y el recorte: `Lienzo` (la imagen de una capa y su transformación; la capa crece si se pinta afuera), `TrazoEnCurso` (la superposición mientras se arrastra y el trazo de verdad al soltar), `relleno_lineal_de_arrastre` (un degradado arrastrado como relleno lineal), `fundir_encima`, `CajaRecorte` (el recuadro con manijas y la proporción) y las barras de opciones (`ControlesPincel`, `ControlesBote`, `ControlesDegradado`). |
| `ui/opciones_ps.py` | (U2) Los controles de Texto (`ControlesTexto`, con el combo de familias con búsqueda) y de Formas (`ControlesForma`), en fila (barra de opciones) o en columna (Propiedades); el editor de degradado (`EditorDegradado`, de 2 a 4 colores), su diálogo y `BotonRelleno`. |
| `ui/estilos_capa.py` | (U2) El diálogo "Estilo de capa" (`DialogoEstilos`): avisa cada cambio (`vistaPrevia`) y el modo decide (Aceptar, un paso; Cancelar, vuelve). |
| `ui/selector_color.py` | (U2) El selector de color propio (`SelectorColor`, `elegir_color`, `BotonColor`) y las muestras recientes en QSettings (`photoshop/colores_recientes`). |
| `ui/dialogos_ps.py` | Los diálogos de Tamaño de imagen y Tamaño del lienzo (con el ancla de 3 × 3). |
| `ui/panel_capas.py` | El panel Capas del modo Photoshop (tarjeta, lista con grupos plegables, íconos por tipo, "fx", selección múltiple, menú contextual, arrastrar con `reubicar`, fusión, opacidad y botones; el filtro arriba, bloqueado). No guarda nada: cada cambio arma un documento nuevo con las funciones del motor y lo manda a la ventana (`documentoCambiado(doc, registrar)`). |
| `ui/herramienta_transformar.py` | Las manijas de una capa: arrastre (mover con imán, escala libre en X e Y, rotar), flechas, voltear (H y V) y su dibujo, con las guías. La vista (o el controlador del modo) le pasa el mouse y el teclado. |
| `ui/documento_capas.py` | Lo que une el documento con la edición de hoy: documento "trivial", tamaño y conversión al girar o recortar (`matriz_marco`, `convertir_documento`, que lleva todas las capas con transformación con su `escala_y` y `voltear_v`, los rellenos y los estilos), los documentos sin foto (`es_ruta_documento`, `imagen_documento`, el alfa de un fondo transparente), pintar máscaras y el estado del editor en JSON para el proyecto. |
| `ui/ventana.py` | El selector (Ctrl+Shift+P), el documento de cada foto (y de cada documento sin foto, con su "foto" en memoria del tamaño del documento), el render con `componer` (con o sin el filtro), el historial, la sesión, el proyecto, exportar y soltar imágenes. Delega lo del modo en `ui/modo_photoshop.py`. |
| `ui/vista_comparacion.py` | La herramienta "transformar" (mouse, flechas, Enter y Esc), Ctrl al soltar y el modo de vista "solo" (sin Antes ni Después). |

**Cómo se integra `componer` con la foto de siempre** (`procesar_con_capas` en `ui/ventana.py`):

1. `_recalcular_fuentes` arma, como siempre, la foto que entra al filtro (`_fuente`: original → geometría → montaje → borrados → recorte), y su reducción para la vista previa rápida.
2. La capa **Foto** es eso más el desenfoque de fondo (`con_desenfoque`), a la escala de la vista o a la completa.
3. El **filtro** de `componer` es `procesar_pila` con la pila de presets y efectos, sus zonas, el recorte y la `escala_vista` de siempre. `componer` lo aplica sobre todo lo de abajo y lo mezcla según la capa "Celular natural".
4. **Sin capas** (documento "trivial": solo la foto y el filtro, todo por defecto) no se llama a `componer`: es `procesar_pila` sobre la foto, igual que antes, bit a bit (hay una prueba). El estado de la foto tampoco lleva documento: los historiales y las sesiones de antes siguen iguales.
5. **Con o sin el filtro:** en el modo Photoshop, `componer` va con `filtro=None` (la composición), salvo con "Ver con el filtro". En Fácil y Editor, con el filtro; con capas, el "Antes" es la composición sin el filtro (sale de la misma caché).
6. **Vista previa:** en los hilos de siempre (rápida y completa), cada una con su `CacheComposicion`, pasando `clave_foto` (la versión de la foto que entra al filtro y el desenfoque) y `clave_filtro` (la pila, las zonas, el recorte y la escala). Mientras dura un gesto (opacidad, transformar) se ve un documento provisorio. **Exportar:** `componer` a escala 1 y `cache=None`.
7. La transparencia de la foto (un PNG con alfa o el fondo transparente) se aplica al final, como antes.

**Qué va en `extra` del proyecto:** `{"app", "version_estado": 1, "foto": {"ruta", "nombre", "ancho", "alto"}, "estado": <el estado del editor en JSON>}`. El estado se pasa a JSON con etiquetas para lo que JSON no tiene (`{"$tupla": …}`, `{"$bytes": <base64>}` para las máscaras de las zonas, que ya son PNG, y `{"$clase": "Zona", "campos": …}` solo para las clases que acepta la sesión). Todo lo del estado de hoy se puede pasar a JSON; si algún día algo no se puede, guardar avisa y no escribe nada.

### Pruebas

`tests/test_modo_photoshop.py` (Etapa 2, U1; ventana real sin pantalla, en la Lite): Nuevo (sin foto, fondos, en Fácil y Editor con el filtro y sin las herramientas de la foto, exportar con y sin filtro y con transparencia, proyecto y sesión), el menú (una prueba por grupo), colores, Mano, Zoom y Espacio, Cuentagotas, escala libre y volteo vertical, Mover con el mouse, imán (al soltar cerca del centro queda centrado), selección múltiple y alinear, selección automática, grupos en el panel, Propiedades, la sesión con un documento de la Etapa 2 (no va a `.bak`), `convertir_documento` y la regresión del kit de flyers.

`tests/test_pintura_ui.py` (Etapa 2, U3; ventana real sin pantalla, en la Lite): el pincel con el mouse simulado (la superposición mientras se arrastra, el color de frente, un solo paso, deshacer y rehacer), sobre la base (capa nueva en el mismo paso), afuera de la capa (crece), el borrador (baja el alfa), pintar un texto (pregunta; con No nada, con Sí rasteriza), `[` y `]`, B, E, G, Mayús+G y C, Esc durante un trazo, el bote contiguo, global, con tolerancia y con "Todas las capas", el degradado (capa de relleno con esos puntos, radial a píxeles, sobre una capa de píxeles y con los colores del editor), recortar con las manijas (Enter recorta, Esc no; proporción; doble clic; el botón del kit) y en una foto (no destructivo, sin salirse, deshacer), pegar un PNG de otra app (con y sin documento) y la sesión y el `.nslite` con una capa pintada.

`tests/test_texto_formas_ui.py` (Etapa 2, U2; ventana real sin pantalla, en la Lite): texto con un clic y escribir (el espacio, una letra que es atajo, Enter, Ctrl+Enter), editarlo con doble clic (sin correr el ancla) y deshacer, clic afuera, texto vacío, doble clic en la miniatura, la barra de opciones (fuente con búsqueda, tamaño, color, negrita, cursiva, alineación, interlineado y espaciado) y Propiedades, caja que corta las líneas, cada forma arrastrando y con Mayús (línea y flecha de a 45°), relleno con degradado (con píxeles), trazo y radio, el tipo en la barra y en Propiedades, la capa de relleno con 2 a 4 colores, el diálogo de estilos (vista previa con píxeles, Cancelar vuelve, Aceptar es un paso, apagar un estilo), F2 para renombrar, el selector de color (hexadecimal, alfa, tono, recientes y cuentagotas), el **flyer de aceptación** (Nuevo 1080 × 1920 con degradado, 4 imágenes en grilla, título con sombra y trazo, banda redondeada con texto encima y estrella, exportado y revisado con los píxeles) y la sesión y el `.nslite` con texto y formas (siguen siendo editables).

`tests/test_capas_ui.py` (ventana real sin pantalla, en la Lite): el modo Photoshop (selector, Ctrl+Shift+P, que se recuerde, la distribución, la vista sin el filtro y "Ver con el filtro", el filtro sobre la composición en Fácil y Editor con su "Antes", soltar una imagen como capa, solo las herramientas que existen y que la PRO no lo tenga), los atajos por edición (Lite: Ctrl+S proyecto y Ctrl+Shift+E exportar; PRO: Ctrl+S exporta), la regresión bit a bit de exportar sin capas, el panel (agregar, reordenar, duplicar, opacidad, fusión, máscara, ocultar, renombrar, candado y borrar), Mover/Transformar con el mouse simulado, el historial, girar y recortar con capas, guardar y abrir `.nslite` (también sin la foto original y roto), la sesión con capas, Fácil con capas y Ctrl+arrastrar. Más las del motor: `test_fusion.py`, `test_documento.py` y `test_proyecto_lite.py`.

## Limitaciones

- (U3) La superposición del trazo muestra el color con la opacidad del pincel, sin el modo de fusión ni la opacidad de la capa (al soltar sí se ve todo como es).
- (U3) Un degradado radial (o de más de 4 colores) sobre la base va a una capa de píxeles, no a una de relleno (los rellenos de la app solo hacen radiales centrados en el lienzo).
- (U3) La capa crece al pintar afuera de ella, pero no más allá del lienzo (lo que se pinta afuera del lienzo no queda). El borrador y el bote no agrandan la capa.
- (U3) El Degradado sobre una capa de píxeles cubre solo esa capa (no la agranda).
- (U3) En una foto, el recuadro de Recortar no puede salirse de ella (su recorte es el no destructivo); en un documento sí (agrega borde).
- (U2) Mientras se escribe, el cursor y la selección los pone un campo de Qt con la misma fuente (el mismo archivo) a la escala de la vista; la letra que se ve es la de la capa (Pillow). Pueden diferir un poco (el interlineado, el corte de una caja en el borde), así que el cursor puede quedar uno o dos píxeles corrido. En un texto rotado, el campo queda derecho sobre su caja.
- (U2) Un clic sin arrastrar con Formas no crea nada (Photoshop abre un diálogo con el tamaño).
- (U2) El tipo de la barra de opciones de Formas es el de la herramienta; para cambiar el de una forma ya hecha, en Propiedades.
- (U2) La sombra de los estilos se mezcla en modo normal (la de Photoshop, en "multiplicar"): lo dice `motor/estilos.py`.
- (U2) Mientras está abierto el diálogo de estilos o se escribe un texto, el documento que se ve es provisorio: guardar el proyecto o la sesión en ese momento guarda lo de antes (al terminar, queda).

- (Etapa 2, U1) Escalar con las manijas es libre (X e Y por separado; Mayús mantiene la proporción). La escala de la Etapa 1, una sola, sigue andando en los proyectos de antes.
- (U1) En un documento sin foto, la galería de estilos del modo Fácil muestra las miniaturas sobre su fondo liso (sin las capas), y la detección automática de cielo o piel mira esa "foto" lisa.
- (U1) El "Antes" de Fácil y Editor en un documento con el fondo transparente es el fondo liso (la composición con el filtro sí se ve bien). El alfa de un fondo transparente es exacto con capas en modo normal; con otros modos de fusión, aproximado.
- (U1) Mover pega con el imán solo al mover (no al escalar ni al rotar). Un grupo no tiene manijas (se mueve entero).
- (U1) En una foto, tamaño de imagen, tamaño del lienzo y acoplar arman un documento nuevo en la tira (la foto no cambia).
- Las imágenes de las capas se pasan a sRGB al agregarlas y se componen en el espacio de color de la foto (casi siempre sRGB; con una foto en otro perfil, como Display P3, los colores de la capa se corren un poco).
- En el modo Photoshop no se ven las zonas de los efectos ni el filtro (salvo "Ver con el filtro"); la capa "Celular natural" (su opacidad, su máscara) no se edita desde la interfaz: el filtro se elige en Fácil o Editor.
- Mover y las herramientas de la máscara terminan al aplicar (Enter, o al soltar la forma): para otra pasada se vuelven a elegir.
- La transparencia de la foto (un PNG con alfa o el fondo transparente) también recorta las capas que caen afuera de ella.
- Las miniaturas de la galería del modo Fácil muestran la foto sin las capas de imagen.
- "Procesar varias fotos…" (lote) aplica solo el filtro (preset, efectos y ajustes), sin capas: las capas son de cada foto.
- Sin la foto original, un proyecto se abre sobre un fondo blanco y sin la edición propia de la foto.
- Las máscaras automáticas de las zonas (cielo, piel, contorno) vuelven de un proyecto o de la sesión en su versión de lado 1024 (como siempre con la sesión).
- Mientras se arrastra una capa, la vista se actualiza con el filtro aplicado (se recalcula sobre todo lo de abajo), así que en fotos grandes acompaña con un poco de demora; el recuadro de la herramienta sí sigue al mouse al instante.
