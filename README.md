# NaturalShot PRO

> **Para probar (Windows y Mac):** bajá el archivo de tu compu de la última versión de prueba, en
> **https://github.com/nicodevgames/naturalshotNCK/releases/latest**. Se compila sola con cada cambio
> en `main` (`.github/workflows/compilar.yml`). En Mac, la primera vez abrila con clic derecho › Abrir.

Aplicación de escritorio para Windows que cambia el *carácter fotográfico* de fotos demasiado perfectas, de altísima calidad o generadas por IA para que se parezcan a una foto cotidiana de celular. El preset principal es **“Celular natural — inspirado en iPhone 13”**.

Todo se procesa localmente con OpenCV/NumPy. No usa IA generativa ni recrea la imagen: no cambia rostros, objetos ni composición, y conserva las dimensiones originales.

> **Aviso:** los presets son aproximaciones visuales, incluidos los que llevan nombre de un teléfono. Ningún filtro reproduce exactamente la cámara de un iPhone, Samsung, Pixel u otro modelo, ni elimina todos los indicios de que una imagen fue generada por IA. Los nombres de los teléfonos se usan solo para describir el estilo; NaturalShot no tiene relación con esas marcas.

## Al abrir: pantalla de carga

Apenas hacés doble clic aparece una pantalla de carga mientras se preparan el motor y la ventana: una tarjeta gris oscura con esquinas redondeadas y sombra suave, el logo que "respira" delante de un halo magenta y violeta (cada tanto lo cruza un brillo y titila la estrellita), el nombre, "Editor de fotos realistas" y una barra con degradado que avanza con cada etapa real del arranque: **Preparando el motor…**, **Cargando la interfaz…**, **Armando la ventana…**, **Abriendo tus fotos…** y **¡Listo!**. Después se desvanece y la ventana aparece maximizada con un fundido y una leve subida (unos 0,4 s). Si todo carga muy rápido, igual queda a la vista unos 0,7 s, para que no sea un parpadeo. Con la sesión anterior, la ventana aparece con la foto que estaba abierta ya cargada.

El tutorial (si no tildaste "No volver a mostrar") aparece cuando la ventana terminó de aparecer y de recuperar tus fotos, y la búsqueda de actualizaciones empieza 1,5 s después.

### Por dentro

- **Orden del arranque** (`main.py`): primero la `QApplication` y la pantalla de carga (`ui/carga.py`, que solo usa PySide6 y la paleta de `estilo.py`). Después NumPy, OpenCV, Pillow, el motor y el módulo de actualizaciones se importan **en otro hilo** mientras la animación sigue, y la interfaz y la ventana se arman en el hilo principal, atendiendo eventos entre parte y parte (`VentanaPrincipal(..., al_avanzar=)`). Por último se recupera la sesión y se espera la foto abierta (hasta 4 s).
- **Animación:** todo con `QPainter` a unos 60 cuadros por segundo (`QTimer`); la barra avanza suave hacia el valor de cada etapa y, en una etapa larga, sigue despacio hacia la siguiente. `revelar()` hace el pase: la pantalla de carga baja su `windowOpacity` mientras la ventana sube la suya, y una "cortina" con la foto de la ventana sube 14 px en esos 380 ms.
- **Tiempos** (esta PC, medidos desde que arranca el proceso): la pantalla de carga está dibujada a los **0,30-0,44 s** desde el código y a los **0,31-0,37 s** con el .exe; el motor, a los 0,5-0,7 s; la ventana armada, a los 0,95-1,2 s; y la app entera a la vista, con la sesión de 3 fotos de 2400 px recuperada, a los **1,8-2,2 s**. Con la variable `NATURALSHOT_REGISTRO_ARRANQUE=<archivo>` se anotan esos tiempos en cada arranque.
- **Pantalla nativa de PyInstaller (`Splash` en el `.spec`): no se usa.** Necesita meter Tcl/Tk en el paquete (hoy `tkinter` está excluido), muestra una imagen fija y el pase a la pantalla animada de Qt se vería como un salto (otra ventana, sin la misma escala de Windows). La de Qt ya aparece en un tercio de segundo.
- **Ventanas sueltas:** al armar las secciones plegables y los pasos del modo fácil, algunos controles se hacían visibles antes de tener padre, y Windows creaba y mostraba por un instante una ventana nativa suelta por cada uno (20 en total). Ahora se muestran recién al estar en su lugar: la ventana se arma en 0,3 s en vez de 0,57 s y no hay parpadeos.

## Modos: Fácil, Editor y Video

Arriba a la izquierda, debajo del logo, está el selector **Fácil | Editor | Video**. Es una sola ventana: el logo, el nombre y el selector quedan siempre en el mismo lugar, en los tres modos, para poder cambiar en cualquier momento.

- **Fácil** y **Editor** son de fotos. **Ctrl+E** alterna entre los dos. Trabajan sobre lo mismo: la foto, la tira, el historial, el estilo y todo lo que hiciste en el editor. Cambiar entre ellos no pierde nada: solo cambia qué se ve.
- **Video** (ícono de película en rosa, con contorno: se distingue de los modos de fotos) muestra el editor de video **en la misma ventana**, con su propia columna izquierda y derecha (ver *Modo Video*). También se llega con el botón **Video** de la barra superior de fotos o con **Ctrl+Shift+V**, que además vuelve de Video al último modo de fotos. Desde Video, Ctrl+E también vuelve a las fotos.
- **Audio** (ícono de ondas de sonido) muestra el editor de audio en la misma ventana: una voz limpia o hecha con IA que suena grabada con un celular en un lugar real (ver *Modo Audio*). Se llega con **Ctrl+Shift+A**, que desde Audio vuelve al modo de antes. A diferencia de Video, Audio sí se recuerda: si cerrás la app en Audio, la próxima vez abre ahí.
- La primera vez la app abre en **Fácil**; después recuerda el último modo de fotos que usaste. Video no se recuerda: si cerrás estando en Video, la próxima vez abre en Fácil o Editor (el último que usaste).

## NaturalShot Lite y las capas

**NaturalShot Lite** es la edición solo de fotos (sin Video ni Audio, con sus propios datos y su `.exe`) que va camino a ser un editor tipo Photoshop. Se abre con `NaturalShot Lite.lnk` o `ejecutar_lite.bat` y se compila con `construir_lite.bat`. Detalle completo en **`LITE.md`**.

Desde la etapa 1, la Lite tiene un tercer modo en el selector, **Photoshop** (**Fácil | Editor | Photoshop**, **Ctrl+Shift+P**), donde cada foto tiene **capas de verdad**. El flujo: primero se arma la foto como en Photoshop y después se le pone el filtro. En Photoshop la vista va **sin el filtro** ("Ver con el filtro" lo previsualiza); en Fácil y Editor el filtro va **arriba de la composición** (y su "Antes" es la composición sin el filtro). El Editor queda como antes. Distribución tipo Photopea: a la izquierda una barra angosta de herramientas (Mover y las de la máscara) con sus opciones; en el centro la vista y la tira; a la derecha el panel **Capas** y el **Historial**. La PRO (en pausa) no tiene este modo:

- abajo, la **Foto** (con todo lo de siempre: geometría, montaje, borrados, recorte y fondo); en el medio, **imágenes** (PNG con transparencia, logos, otras fotos) con posición, escala, rotación, volteo, **modo de fusión**, opacidad y **máscara**; arriba de todo, **Celular natural**: el filtro de siempre aplicado sobre todo lo de abajo (su opacidad es "cuánto filtro");
- **Agregar imagen** o soltar una imagen sobre la foto (en Photoshop entra como capa; en Fácil y Editor, con **Ctrl**); **Mover / Transformar** con **V** (manijas, flechas, Enter aplica y Esc cancela); máscaras pintadas con rectángulo, elipse, lazo o pincel, en modo "se ve" o "se oculta";
- cada cambio es un paso del historial; la sesión recuerda las capas; en la Lite **Ctrl+S** guarda un proyecto **`.nslite`** (la foto original, su edición y las capas) y Abrir lo vuelve a abrir;
- **exportar** (en la Lite, **Ctrl+Shift+E**; en la PRO, Ctrl+S como siempre) aplana todo con el filtro; sin capas, el resultado es exactamente el de antes.

Lo que antes se llamaba **"Capas"** (presets extra apilados encima del base) ahora se llama **"Efectos"**.
- **Abrir y arrastrar llevan cada cosa a su modo.** Si estás en fotos y abrís o arrastrás un video, la app pasa sola a Video con ese video y avisa abajo de la vista: "Esto es un video: lo abrimos en el modo Video". Si estás en Video y abrís o arrastrás una foto, vuelve al último modo de fotos, la suma a la tira y avisa "Esto es una foto: la abrimos en el modo de fotos". Fotos y videos juntos: las fotos van a la tira y el primer video a Video (se edita uno a la vez; el aviso dice si quedaron videos sin abrir).

### Modo fácil, paso a paso

1. **Tu foto:** tocá **Abrir fotos** (podés elegir varias) o arrastralas a la vista. Con una foto abierta, el paso queda en una línea con su nombre y un botón chico para abrir más.
2. **Elegí un estilo:** cada tarjeta muestra **tu foto** con ese estilo. Tocá una para aplicarla: la elegida queda con borde magenta y un tilde.
   - Primero están los **Recomendados**: Natural iPhone 13 (el principal), Natural sutil, Natural marcado, Anti IA, iPhone 15 Pro, Galaxy S23, Interior cálido y Noche urbana.
   - **Ver más estilos** despliega el resto, agrupado como en el editor, más tus presets guardados y **Sin efecto**.
   - Si todavía no abriste una foto, podés elegir el estilo igual: se usa al abrirla.
3. **¿Cuánto efecto?:** mové la barra, de **Sutil** a **Fuerte**. En 0 la foto queda como está y en 100 tiene el estilo completo.
4. **Exportar:** elegí **Mejor calidad (PNG)** o **Más liviano (JPEG)** y tocá **Exportar foto**. Se guarda un archivo nuevo y el original no se toca. **Exportar varias fotos…** aplica el estilo y la intensidad a muchas fotos de una vez.

Los pasos 3 y 4 quedan fijos abajo, siempre a la vista, aunque la galería sea larga.

En el modo fácil:

- **Barra superior:** quedan Abrir, deshacer y rehacer, los modos de comparar (Dividir, Antes, Después y Lado a lado), Recortar, girar 90° y Video (lleva al modo Video).
- **Vista previa:** la columna de ajustes se oculta y la foto se ve más grande. La tira de fotos y el zoom quedan igual.
- **Historial:** no se muestra, pero es el mismo. Ctrl+Z y Ctrl+Y funcionan igual.

Si la foto tiene cosas hechas en el editor (capas, montaje, objetos borrados, fondo, enderezado o volteo), aparece un aviso chico: se mantienen aunque elijas otro estilo. Los **ajustes finos** del editor, en cambio, se reemplazan al elegir otro estilo, igual que con el desplegable del editor (Ctrl+Z los recupera). El aviso también lo dice.

### Modo editor

Todo lo de siempre: preset y capas, zonas, montaje, borrar objetos, fondo, ajustes finos por sección, historial, enderezar y voltear.

### Por dentro

- **Código:** `celular_natural/ui/modo_facil.py`, con `PanelFacil` (los cuatro pasos), `GaleriaEstilos`, `TarjetaEstilo` y `TarjetaPaso` (una `SeccionPlegable` con el número del paso). En `ventana.py` están el selector, `establecer_modo` (Fácil, Editor o Video), `alternar_modo` (Ctrl+E), `alternar_video` (Ctrl+Shift+V), `abrir_rutas` (lleva cada archivo a su modo) y `fuente_para_estilos`. Lo chico del modo Video (clasificar fotos y videos, los textos del aviso, el botón del selector con su punto y el chip de la exportación) está en `ui/modo_video.py`.
- **Sin estado propio:** tocar una tarjeta cambia el `combo_preset` del `PanelAjustes` y la barra mueve la misma `intensidad` del editor. Por eso cada cambio queda en el historial ("Preset: …", "Intensidad general: 100 → 60") y el render es el mismo.
- **Exportar:** usa el mismo selector de formato y la misma `exportar()` del editor, así que el archivo es idéntico. JPEG sale con la calidad del editor (92 si no la cambiaste).
- **Miniaturas:**
  - Se arman con la foto que entra al filtro (girada, con montaje, borrados y recorte), reducida a 256 px de lado largo y procesada con `procesar_pila` y su `escala_vista`.
  - Se calculan en un `QThreadPool` propio, de un hilo y baja prioridad, con `Tarea`. Mientras cargan, la tarjeta muestra un brillo que la cruza.
  - Se guardan en caché por foto, geometría, montaje, borrados, recorte, preset y valores del preset (hasta 240). Volver a una foto o deshacer un giro no recalcula nada.
  - Tardan unos 12 ms cada una: los 35 estilos, en menos de medio segundo. En el modo editor no se calculan.
- **Preferencia del modo:** se guarda con `QSettings("NaturalShot", "NaturalShot PRO")`, clave `interfaz/modo` (en Windows, en el registro del usuario), y puede ser `facil`, `editor` o `audio`: Video nunca se guarda. Las pruebas usan un .ini propio con la variable `NATURALSHOT_CONFIG`.

## Qué hace el tratamiento

El motor simula el camino de una foto real, de la luz al archivo. Cada efecto es independiente, arranca en 0 (apagado), tiene su botón de ojo para desactivarlo solo a él y cada sección tiene su interruptor.

### Orden de operaciones

| # | Espacio | Etapa | Por qué ahí |
|---|---|---|---|
| 1 | Lineal | Exposición, balance de blancos, variación de balance | La luz se multiplica en lineal |
| 2 | Lineal | Óptica: desenfoque (PSF) → distorsión → aberración cromática → bordes blandos → viñeteo | El lente actúa antes del sensor y mezcla luz, no valores codificados |
| 3 | Lineal | Mosaico Bayer y demosaico | Es lo que hace el sensor |
| 4 | Lineal | Tono local (HDR) | Compresión de rango sobre la luz |
| 5 | Codificado | Curva global, caída de luces, pie de sombras, contraste, zonas | Las curvas son perceptuales |
| 6 | Codificado | Saturación, desaturación de luces, respuesta de color de cámara | |
| 7 | Codificado | Claridad, microcontraste, nitidez, suavizado, nitidez variable, piel real | Procesado de detalle del teléfono |
| 8 | Codificado | Ruido residual de sensor (calculado en lineal, ver abajo) | Después del detalle, si no el suavizado lo borraría |
| 9 | Codificado | Grano fotográfico | Donde se percibe el grano |
| 10 | 8 bits | Reescalado y JPEG, **una sola vez** al final de toda la pila | Nunca se acumulan |

Entre etapas y entre capas todo es float32 con curvas de 16 bits; se cuantiza a 8 bits una sola vez, al final. Lo que la exposición o el HDR empujan por encima del blanco no se recorta: la caída suave de luces lo comprime.

### Módulos

| Sección | Controles | Explicación técnica | 12 MP |
|---|---|---|---|
| **Sensor** | Ruido de sensor (ISO), ruido de lectura, ruido cromático, tamaño del grano de ruido, Bayer | Modelo Poisson-Gaussiano: var = a·x + b en luz lineal (disparo + lectura), convertido a la imagen codificada con la derivada de la curva sRGB. El negro puro sale limpio. Bayer: mosaico RGGB + demosaico adaptativo a bordes de OpenCV | 0,9 s · Bayer 0,7 s |
| **Óptica** | Desenfoque (PSF), distorsión radial, aberración cromática, pérdida de nitidez en bordes, viñeteo | PSF = disco de foco ⊗ gaussiana (MTF que cae suave). Distorsión de Brown con k₁ ±0,035 y recorte para no salirse del cuadro. Viñeteo multiplicativo en lineal | 0,5-0,8 s c/u |
| **Detalles** | Reducir nitidez, reducir microcontraste, claridad local, nitidez variable | Filtros guiados que preservan bordes; la nitidez comprime sobreimpulsos con tanh (halos); la nitidez variable usa un campo aleatorio de baja frecuencia | 0,4-0,6 s c/u |
| **Texturas** | Suavizado, piel real | Suavizado = reducción de ruido del celular (también del croma). Piel real = textura de poro pasa-banda en zonas lisas de medios tonos y menos brillo de plástico | 0,8 s · 1,2 s |
| **Iluminación** | HDR, exposición, contraste, caída de luces, pie de sombras, brillo por zona | HDR con base de iluminación por filtro guiado (sin halos); curvas no lineales; zonas con pesos suaves que no tocan el negro ni el blanco | 1,0-1,4 s |
| **Color** | Temperatura, tinte, variación de balance, saturación, desaturar luces, respuesta de cámara | Respuesta de cámara: rojos → naranja, verdes → amarillo, azules → cian, conservando la luminancia | 0,7-1,4 s |
| **Grano** | Intensidad, tamaño, correlación, croma, sombras/medios/luces | Ruido gaussiano filtrado a dos escalas (fino + grumos), monocromo o por canal, con respuesta por zona | 0,8 s · 1,6 s cromático |
| **Compresión** | Reescalado (+ algoritmo), JPEG, submuestreo 4:2:0 | Reescalado bilineal/bicúbico/área/Lanczos; JPEG real con Pillow en memoria | 0,2-0,3 s |
| **Máscaras** | % de nitidez, suavizado, ruido y microcontraste para piel, bordes, textura alta y textura baja | Sin IA: piel por color (YCrCb), bordes = gradiente fuerte y aislado, textura = energía local del detalle fino. Partición suave con prioridad, máscaras suavizadas con filtro guiado sobre la propia foto (sin halos). Se cachean por imagen | 4,2 s la 1ª vez |

**Semilla:** el mismo número da exactamente el mismo ruido y grano; cambiala para otra variación.

Algunos pedidos de la especificación ya los cubren controles existentes y no se duplicaron: la *preservación de texturas naturales* es el % de "textura alta" en Máscaras; la *simulación del procesado de smartphone* son los perfiles; la *reducción adaptativa de microcontraste* es el filtro guiado (respeta los bordes) más las máscaras.

El control **Intensidad general** escala todos los efectos a la vez. En 0 la salida es idéntica al original, píxel por píxel.

## Presets

Todos buscan un resultado natural y moderado. Cada uno combina de otra forma los mismos controles, que después podés retocar.

| Grupo | Presets |
|---|---|
| Generales | Celular natural — inspirado en iPhone 13 (principal) · Celular natural — sutil · Celular natural — marcado |
| Fotos de IA | Anti IA — piel real, sin calidad exagerada (no suaviza: baja el sobreenfoque y el detalle de render, le devuelve poros a la piel y apaga el color exagerado) |
| Perfiles fotográficos | Smartphone moderno · Smartphone antiguo · Cámara compacta digital · DSLR convencional · Cámara mirrorless · JPEG comprimido de redes sociales · Interior con flash · Noche con ISO alto |
| Teléfonos | Estilo iPhone 15 Pro · Estilo iPhone 11 · Estilo iPhone 8 / X · Estilo Samsung Galaxy S23 · Estilo Samsung Galaxy A (gama media) · Estilo Google Pixel 8 · Estilo Xiaomi Redmi · Estilo Motorola Moto G |
| Luz y lugar | Exterior soleado · Día nublado · Paisaje con HDR · Interior con luz cálida · Interior con poca luz · Noche urbana |
| Personas y temas | Selfie con cámara frontal · Retrato con luz de ventana · Comida y restaurante · Colores vivos |
| Tipo de cámara | Celular de gama básica · Foto reenviada por mensajería |
| Parciales | Solo textura (sin tocar el color) · Solo color y tono (sin textura) |
| — | Sin efecto |

Los perfiles simulan características generales de cada tipo de cámara; no reproducen ningún sensor ni modelo concreto (no hay mediciones de referencia). Debajo del preset elegido se ve la lista exacta de parámetros que modifica.

**Presets propios:** **Guardar como preset** guarda todos los valores actuales con el nombre que elijas (en `%APPDATA%\NaturalShot\presets.json`). Aparecen al final de la lista y se borran con el tachito.

Al cambiar de preset se conservan la intensidad general y la semilla. **Restablecer ajustes** vuelve a los valores del preset seleccionado. Para agregar o modificar presets, editá `GRUPOS_PRESETS` en `celular_natural/motor/procesado.py` y asignale un ícono de Lucide en `ICONO_PRESET` de `celular_natural/ui/iconos.py` (el nombre del SVG en `assets/iconos`).

### Capas

> Desde la etapa 1 de NaturalShot Lite, en la interfaz esto se llama **Efectos** ("Agregar efecto", "Efecto 1"…): "Capas" son ahora las capas de verdad de cada foto (ver *NaturalShot Lite y las capas* y `LITE.md`). Lo de abajo sigue valiendo, con "efecto" donde dice "capa".

Además del preset base podés apilar hasta 4 capas, cada una con otro preset y su propia intensidad. Por ejemplo: **Estilo iPhone 11** como base y **Noche urbana** al 50 % encima. Las capas se aplican en orden, de arriba hacia abajo, sobre el resultado de la anterior, y cada una usa un patrón de ruido distinto para que el grano no se duplique. **Agregar capa** suma una y la **×** la quita.

**Zona de una capa.** En **Dónde**, cada capa puede aplicarse a toda la foto o solo a una parte que marcás sobre la vista previa: un **rectángulo** o una **elipse** (arrastrando), un **lazo poligonal** (clic punto por punto; se cierra con doble clic, Enter o tocando el primer punto, y Retroceso borra el último), una zona pintada a mano con el **pincel** (ver abajo), o el **cielo** o la **piel**, que se detectan solos (ver *Selección automática*). Por ejemplo, Noche urbana solo en el fondo, o más suavizado solo en la cara. **Borde suave** controla cuán gradual es la transición, para que no se note el corte. **Invertir** aplica la capa a todo menos la zona. El botón de mira vuelve a marcarla y **Zonas**, en la cabecera de la vista previa, muestra u oculta los contornos. Esc cancela el marcado.

### Pincel (zona pintada a mano)

Sirve para zonas irregulares, como el pelo, una sombra o un objeto que no entra en un rectángulo. Está en **Dónde → Pincel** (capas y montaje) y en **Fondo → Pintar objeto**.

1. Elegí **Pincel**. Arriba de la foto aparece la barra del pincel.
2. Pintá con el clic izquierdo: lo pintado se ve en rosa y el círculo bajo el cursor muestra el tamaño.
3. Para borrar lo pintado de más, usá el **clic derecho**, o activá **Goma** (tecla **E**) y pintá con el izquierdo.
4. **Tamaño** cambia el pincel (también con **[** y **]**, o **−** y **+**). **Dureza** va de borde suave, que se funde, a borde duro. El círculo punteado de adentro marca hasta dónde pinta al 100 %.
5. **Ctrl+Z** (o Retroceso) quita el último trazo mientras pintás. Con la rueda hacés zoom, y con la rueda apretada te desplazás.
6. Terminá con **Listo** o **Enter**. **Esc** o **Cancelar** descartan lo pintado en esa vez y vuelven a la zona anterior.

Con la **mira** de la fila (o **Seguir pintando** en Fondo) volvés a entrar: ves lo que ya pintaste y podés sumar o borrar encima. Cada vez que terminás queda un paso en el historial ("Capa 1: zona pintada", "zona retocada con el pincel"). Sobre una zona automática (cielo, piel o un contorno ajustado) el pincel la corrige: lo detectado queda como base, pintar suma y la goma resta.

En una zona pintada, el borde lo da la dureza de cada trazo, así que no aparece el control **Borde suave**. **Invertir** funciona igual que en las otras zonas. Los trazos se guardan normalizados a la foto base (la original ya girada y enderezada, sin recortar), con el radio relativo a su lado largo, y se vuelven a dibujar al tamaño de cada salida. Por eso la vista previa reducida y la exportación coinciden, y la zona no se mueve si cambiás el recorte ni si girás la foto.

### Recorte

**Recortar**, en la barra superior, muestra la foto completa (ya girada y con los objetos borrados) para elegir qué parte queda, con proporción libre, la original, 1:1, 4:5, 3:4, 9:16, 4:3 o 16:9, y una cuadrícula de tercios. **Aplicar** (o Enter) confirma, **Quitar recorte** vuelve a la foto completa y **Cancelar** deja todo como estaba. El recorte no es destructivo: se guarda como un ajuste más, se puede cambiar o quitar en cualquier momento y el original nunca se toca. La exportación sale con el tamaño de la parte recortada. Las zonas se guardan relativas a la foto base completa, así que no se desplazan si cambiás el recorte. Si después girás la foto, el recorte gira con ella; si la enderezás, conserva su centro y su tamaño en píxeles. "Procesar varias fotos" no aplica ni el recorte, ni las zonas, ni la geometría, ni los borrados, porque dependen de cada foto.

### Girar, voltear y enderezar

Al lado de **Recortar**, en la barra superior:

- **Girar 90°** a la izquierda o a la derecha, **voltear horizontal** (espejo izquierda-derecha) y **voltear vertical**: un clic, un paso del historial.
- **Enderezar** abre una barra con el ángulo (de −15° a 15°, con el deslizador o escribiendo el valor), **Nivelar automático** (busca el horizonte y las líneas rectas de la foto y propone el ángulo), una **cuadrícula** de guía, **Cancelar** y **Aplicar** (Enter aplica, Esc cancela). Mientras movés el deslizador la foto gira al instante y se recortan las esquinas que quedarían vacías, como en el celular.

Cómo se usa para enderezar un horizonte torcido:

1. Tocá **Enderezar** (el ícono de la regla).
2. Tocá **Nivelar automático**. Si la foto tiene un horizonte o líneas rectas claras, se endereza sola; si no, avisa.
3. Revisalo con la cuadrícula y corregí con el deslizador si hace falta.
4. Tocá **Aplicar**.

Es **no destructivo**: la geometría se guarda como un ajuste más de cada foto (historial, tira de fotos, deshacer y rehacer, exportación) y el original nunca se toca. Todo lo que marcaste gira con la foto y sigue sobre el mismo objeto: zonas de capas, montaje y fondo, trazos del pincel, zonas borradas y recorte. Con giros de 90° y volteos un rectángulo o una elipse siguen siéndolo; al enderezar quedarían torcidos, así que pasan a polígono con la misma forma. Mientras se endereza, la vista previa muestra la foto original girada, sin montaje ni borrados; al aplicar se recalcula todo.

**Estrategia de coordenadas ("lo que ves").** Todo lo que marcás se guarda normalizado respecto de la **foto base**: la original ya girada, volteada y enderezada, sin recortar. Cuando cambia la geometría, `motor/edicion.py` lleva cada zona del marco viejo al nuevo con la misma matriz que usa `aplicar_geometria` (`matriz_cambio`): los puntos se transforman, los radios del pincel se reescalan (son relativos al lado largo) y a las máscaras automáticas solo se les compone una matriz, sin volver a muestrear (ir y volver no las degrada). Cada paso del historial guarda la geometría junto con las zonas ya convertidas. El resto del motor (zonas, desenfoque, montaje, filtro) no necesita saber nada de la geometría.

**Orden de la foto que entra al filtro:** original → geometría → montaje → borrar objetos → recorte → fondo (desenfoque) → filtro. Todo a resolución completa: la vista previa es una reducción de lo mismo y la exportación es idéntica a la vista.

### Varias fotos (tira)

**Abrir** permite elegir varias fotos a la vez, y también se pueden arrastrar juntas a la vista. Aparecen como miniaturas en la **tira** de abajo: un clic cambia de foto, el **+** agrega más y el clic derecho quita una. Cada foto guarda su propia edición: ajustes, capas, zonas, recorte, geometría, montaje, objetos borrados, fondo e historial, y todo eso se recuerda al cerrar la app (ver *Recordar la sesión*). El tacho, a la derecha de la tira, quita todas las fotos. Una foto que se abre por primera vez hereda el preset y las capas de la que estabas editando, pero no lo que es propio de cada foto, como zonas, recorte, giro o enderezado, montaje, objetos borrados o el objeto marcado en Fondo (sí el modo y los valores del desenfoque).

### Recordar la sesión: tus fotos al volver a abrir

Si cerrás NaturalShot con fotos en la tira, la próxima vez que la abras aparecen **las mismas fotos con sus ediciones**: preset, capas con sus zonas, recorte, giro y enderezado, montaje, objetos borrados, fondo y **el historial de cada una** (Ctrl+Z sigue andando). También vuelve a abrir la foto que estaba abierta. El modo Fácil o Editor ya se recordaba aparte.

- **Se guarda sola:** 2 s después de cada cambio que entra al historial, al agregar o quitar fotos, al cambiar de foto y al cerrar (al cerrar, también lo último que tocaste aunque todavía no haya pasado al historial). Si se corta la luz, se pierden como mucho los últimos 2 s.
- **Dónde:** `%APPDATA%\NaturalShot PRO\sesion\sesion.pkl`. Guarda solo las **rutas** de las fotos, nunca las imágenes, y los originales no se tocan.
- **Fotos que ya no están:** si moviste o borraste alguna, se saltea y aparece un aviso abajo de la foto, por ejemplo "2 fotos de la sesión anterior ya no están en su carpeta" (pasando el mouse se ven los nombres). Se va solo a los 12 s o con la ×. Si la que estaba abierta es la que falta, se abre la más cercana.
- **Empezar de cero:** el tacho a la derecha de la tira, o clic derecho en la tira → **Quitar todas las fotos…**. Pide confirmación y vacía la tira y la sesión guardada; conserva el preset y las capas, como para una foto nueva.
- **Si el archivo se daña** (o es de una versión incompatible), la app arranca limpia, lo avisa y deja el archivo como `sesion.bak` (con el motivo en `sesion.log`) para diagnóstico.
- Al actualizarse sola, la app ya no pregunta por las fotos con cambios: al volver a abrir están igual.
- El editor de video no recuerda nada.

**Por dentro:**

- **Archivo** (`celular_natural/sesion.py`, sin Qt): `pickle` con una marca, el número de versión del formato y un CRC32. Los estados son dataclasses congeladas del motor (`Ajustes`, `Zona`, `Recorte`, `Geometria`, `CapaFoto`, `ZonaBorrado`) y tuplas; lo que se repite de un paso al siguiente se guarda una sola vez. Al leer, solo se aceptan esas clases (y los números de NumPy), y cada dataclass se vuelve a armar con sus campos de esta versión: si falta uno obligatorio, la sesión se descarta entera en vez de fallar después.
- **Escritura atómica:** temporal en la misma carpeta, `fsync` y `os.replace`. Los temporales que deja un corte se borran solos.
- **Ventana** (`ui/ventana.py`): `activar_sesion()` (la llama `main.py`) lee el archivo y revisa qué fotos siguen en su carpeta en segundo plano (`QThreadPool` y `Tarea`). Después arma la tira, abre la foto actual con `cambiar_a_foto` y carga las demás miniaturas con `_cargar_miniatura`, como al abrir fotos. Hasta que termina no se guarda nada, para no pisar la sesión anterior. Además: `instantanea_sesion`, `guardar_sesion` (en segundo plano, o ya mismo al cerrar), `quitar_todas_las_fotos`, `cuando_sesion_lista` y la señal `sesionRestaurada`. Las ventanas que no llaman a `activar_sesion`, como las de las pruebas, no leen ni escriben nada.
- **Rendimiento:** con 20 fotos de 1600 px, la sesión se recupera y están las 20 miniaturas en 2,1 s, y la interfaz nunca queda trabada más de 40 ms (cada miniatura se pone en la tira sin rearmarla). Guardar 20 fotos con 100 pasos de historial cada una y máscaras automáticas tarda 11 ms (0,9 MB); leerla y validarla, 0,1 s.

### Montaje (partes de otra foto)

Para fotos casi iguales, como dos tomas de la misma escena, donde de una te gusta una parte y de la otra otra. En **Montaje → Superponer otra foto** elegís una foto de la tira y en **Dónde** indicás qué parte se pega: mitad de arriba, de abajo, izquierda o derecha, toda la foto, un rectángulo, una elipse, un lazo, una zona pintada con el pincel, o el **cielo** o la **piel** detectados solos (por ejemplo, el cielo de otra toma que salió mejor). Si la foto base está girada o enderezada, la otra se gira igual antes de alinearla.

- **Borde suave:** funde la unión.
- **Opacidad:** controla cuánto se ve la foto pegada.
- **Alinear automáticamente:** corrige si el celular se movió un poco entre tomas. Usa puntos ORB y una homografía con RANSAC. Si no encuentra coincidencias suficientes, lo avisa y pega sin alinear.
- **Igualar brillo y color:** empareja la exposición, con media y desvío por canal.

El montaje se arma **antes** del filtro, así el ruido y el grano quedan parejos y no delatan la unión. La alineación se calcula una vez y se guarda en caché: unos 0,3 s en 12 MP.

### Fondo: transparente o desenfocado

En la tarjeta **Fondo** marcás un objeto y elegís qué hacer con lo de afuera. Con **Marcar objeto** marcás su contorno, por ejemplo una persona o un auto, con el lazo poligonal. Con **Pintar objeto** lo pintás a mano con el pincel. **Ajustar al contorno** pega esa selección aproximada al borde real del objeto (ver *Selección automática*). Arriba de la tarjeta elegís el modo, y la misma selección sirve para los dos:

- **Transparente** (PNG sin fondo): todo lo de afuera queda transparente y en la vista previa se ve como un tablero de ajedrez. Siempre se exporta en **PNG**, aunque esté elegido JPEG, porque JPEG no admite transparencia.
- **Desenfocado** (modo retrato): el objeto queda nítido y el fondo se desenfoca como con un lente luminoso. Se exporta normal, en el formato elegido (PNG o JPEG), sin transparencia. En la vista, **Después** muestra el desenfoque y **Antes**, la foto sin desenfocar.

Controles:

- **Suavizado del borde** (los dos modos): unos pocos píxeles de suavizado evitan el serrucho. Con el pincel, el borde lo da la dureza.
- **Invertir** (los dos modos): en Transparente borra el objeto y deja el fondo. En Desenfocado desenfoca el objeto y deja nítido el fondo.
- **Recortar al tamaño del objeto** (Transparente): el PNG sale justo del tamaño del objeto.
- **Intensidad del desenfoque** (Desenfocado): el tamaño del desenfoque, como abrir más o menos el diafragma. Es relativo al tamaño de la foto, así que se ve igual en la vista previa y al exportar. Arranca en 35, un desenfoque moderado.
- **Transición nítido → borroso** (Desenfocado): qué tan gradual es el paso del objeto al fondo. En 0 el fondo está desenfocado desde el mismo borde, lo que conviene si el fondo está lejos. Más alto, lo que toca al objeto, como el piso bajo los pies, se desenfoca de a poco.
- **Profundidad gradual** (Desenfocado): cerca del objeto desenfoca menos y cuanto más lejos, más, como si el fondo se alejara.

Cómo se calcula el desenfoque, para que se vea fotográfico (`celular_natural/motor/desenfoque.py`):

- Usa un **disco** (bokeh), no una campana gaussiana, y promedia en **luz lineal**. Así las luces chicas se abren en discos brillantes, como en un lente real.
- **Sin halo:** se desenfoca solo el fondo (convolución normalizada con la máscara). El color del objeto no se derrama sobre el fondo y el borde no se oscurece. Lo que el disco no ve, adentro del objeto, se rellena con el fondo vecino.
- Para la transición y la profundidad mezcla tres niveles de desenfoque según la distancia al objeto.
- Cada disco se calcula sobre una copia reducida y se vuelve a ampliar. En 12 MP tarda 0,4-0,6 s y se guarda en caché, así que mover otros controles no lo recalcula.
- Va **antes** del filtro, como el montaje. El ruido, el grano y la óptica se aplican parejos sobre toda la foto, y el fondo no queda liso delatando el truco. El orden es geometría → montaje → borrar objetos → recorte → desenfoque de fondo → filtro.

Cada foto de la tira guarda su objeto y su modo. Una foto que abrís por primera vez arranca sin objeto, pero conserva el modo y los valores del desenfoque de la que estabas editando.

### Selección automática: cielo, piel y ajustar al contorno

Sin IA ni nada descargado: color, textura, conectividad y GrabCut de OpenCV (`motor/seleccion_auto.py`). Se calculan en segundo plano sobre la foto base completa (girada, con montaje y borrados, sin recortar), con el aviso **Detectando…** en la vista (Esc cancela), y se guardan en caché: volver a elegir lo mismo es instantáneo.

- **Cielo** y **Piel**, en el **Dónde** de las capas y del montaje. Elegilos y la zona aparece sola, con el borde pegado a los contornos de la foto (siluetas de edificios, árboles, pelo). Ejemplo: una capa "Día nublado" solo en el cielo, o "Retrato con luz de ventana" solo en la piel.
- **Ajustar al contorno**, en la tarjeta **Fondo**:
  1. Marcá el objeto aproximado con **Marcar objeto** (lazo) o **Pintar objeto** (pincel). No hace falta ser prolijo: alcanza con rodearlo.
  2. Tocá **Ajustar al contorno**. Si todavía no marcaste nada, arrastrá un rectángulo alrededor del objeto, con un poco de margen.
  3. La selección se pega al borde real. Si algo quedó afuera o de más, tocá **Seguir pintando** y corregilo.

Para corregir cualquier zona automática usá la **mira** de su fila (o **Seguir pintando** en Fondo): el pincel arranca con lo detectado en rosa; pintar suma y la goma (o el clic derecho) resta. Cada detección y cada corrección quedan en el historial ("Capa 1: zona Cielo (automático)", "zona retocada con el pincel", "Objeto ajustado al contorno").

Estas zonas son máscaras raster (forma `"mascara"` de `Zona`): se guardan como un PNG compacto de lado ≤ 1024 (unos pocos KB) más los trazos de pincel encima. Mientras la app está abierta, la exportación usa la máscara a resolución completa, con el borde exacto.

Tiempos en 12 MP: cielo ≈ 0,6 s, piel ≈ 0,35 s, ajustar al contorno ≈ 0,9 s.

### Borrar objetos

En la tarjeta **Borrar objetos** (columna izquierda, entre Montaje y Fondo) quitás cosas de la foto: un cable, un cartel, una persona de fondo, una mancha.

1. Elegí el modo: **Rellenar automático** (completa lo borrado con lo de alrededor: cielo, pasto, pared, arena, agua) o **Clonar desde…** (copia otra parte de la foto que elegís vos).
2. Marcá lo que querés borrar con **Pintar** (lo más común; pintá con un poco de margen), **Lazo** o el **rectángulo**.
3. Con **Rellenar automático**, al terminar (Listo o Enter) se borra solo. En la vista, **Antes** sigue mostrando el objeto, así comparás con el divisor.
4. Con **Clonar desde…**, después de marcar arrastrá desde la zona hasta la parte de la foto que la reemplaza: la zona muestra cómo va a quedar y la fuente se ve con línea de puntos. Podés agarrar la fuente y correrla. **Fundir luz y color** (activado) empareja la luz del parche con su borde; **Listo** (o Enter) confirma y Esc cancela.

Cada borrado queda como una fila: se puede cambiar de modo, elegir otra fuente (sello), volver a marcar o seguir pintando (mira), o quitarlo (×). Puede haber varios por foto; se aplican en orden y cada uno queda en el historial ("Objeto borrado (relleno automático)", "Borrado 2: fuente del clonado", "Borrado quitado").

Va **antes** del filtro, como el montaje, y se calcula sobre la foto completa a resolución completa (≈ 0,5-1,3 s en 12 MP según el tamaño de lo borrado, con el aviso **Borrando…**). La vista previa es una reducción de ese mismo resultado, así que coincide con la exportación. Rellena bien texturas naturales, degradés y patrones regulares; para estructuras que no están alrededor (texto, caras, objetos tapados a medias) conviene clonar.

### Historial

El panel **Historial**, abajo a la izquierda, lista cada cambio con una descripción, por ejemplo "Ruido de sensor: 35 → 60", "Capa 1: zona marcada", "Recorte", "Girar 90° a la derecha", "Enderezar: 0° → −2,5°" u "Objeto borrado (clonado)". Un clic en cualquier paso vuelve a ese estado. Los pasos posteriores quedan en gris para poder rehacerlos, hasta que hagas un cambio nuevo. Ctrl+Z y Ctrl+Y recorren el mismo historial. Mover un deslizador cuenta como un solo paso.

## Modo Video (editor de video)

El modo **Video** del selector (o el botón **Video** de la barra de fotos, o **Ctrl+Shift+V**) muestra el editor de video **en la misma ventana**, en lugar de las columnas de fotos. No se abre ninguna ventana aparte. Arrastrar un video sobre `NaturalShot.exe`, abrirlo con la app, o abrirlo o arrastrarlo estando en fotos también lleva a Video con ese video (con el aviso "Esto es un video: lo abrimos en el modo Video").

- **Columnas propias:** a la izquierda, debajo del logo y del selector, el preset y las capas del video, los datos del video abierto y los atajos; a la derecha, las tarjetas **Sonido** y **Mejorar calidad**, los ajustes del video y **Exportar video**. Abajo a la izquierda, el nombre del video y una **×** para cerrarlo.
- **Volver a las fotos** (Fácil o Editor en el selector, Ctrl+E o Ctrl+Shift+V) oculta el video sin cerrarlo: al volver siguen el video, sus cortes y la posición. Mientras estás en fotos, el botón Video lleva un punto rosa que indica que hay un video abierto. El video se pierde solo si lo cerrás con la ×, si abrís otro o al cerrar la app. Si tiene cortes o cambios de sonido sin exportar, antes de cerrarlo o de reemplazarlo por otro se pregunta.
- **El filtro:** la primera vez que entrás a Video, el video toma el filtro de las fotos (preset, intensidad, capas y ajustes; las capas van a todo el cuadro). Desde ahí el video tiene **su propio filtro**: lo que cambies en Video no toca las fotos y lo que cambies en las fotos no toca el video. **Usar el de las fotos**, arriba a la izquierda, lo vuelve a copiar cuando quieras.
- **Exportar y seguir con las fotos:** si volvés a las fotos mientras se exporta, la exportación sigue. Debajo del selector aparece **Exportando video · 45 %** con una barrita (tocarlo vuelve a Video, donde están el detalle y Cancelar) y, al terminar, un aviso: "Listo: se exportó el video …". Si cerrás la app con una exportación en curso, pregunta antes (cerrar la cancela, sin dejar archivos a medias).
- **Abrir** (Ctrl+O o "Abrir video") usa el mismo diálogo que las fotos, **Fotos y videos**: si elegís fotos, vuelve a las fotos y las suma a la tira.

1. **Abrir video** (Ctrl+O) o arrastralo a la vista. Formatos: MP4, MOV, M4V, AVI, MKV y WEBM. Los videos verticales de celular se enderezan solos.
2. Ajustá el filtro como en fotos y mirá el cuadro actual con Dividir, Antes, Después o Lado a lado.
3. Moverse por el video:
   - La **línea de tiempo** muestra cómo va a quedar: lo borrado y lo recortado no están, y el tiempo, la duración y la reproducción son los del video final.
   - **Espacio** reproduce o pausa.
   - **← →** van cuadro a cuadro.
   - **J / L** saltan un segundo.
4. Cortar:
   - **I / O** recortan lo de antes o lo de después del cursor (o arrastrá hacia adentro los corchetes de los extremos).
   - **S** corta en el cursor.
   - Tocá un tramo y apretá **Supr** para borrarlo: **desaparece** y lo que sigue se corre, como en los editores del celular.
   - En cada unión donde se borró o recortó algo queda una **marquita rosa**: tocala (o botón derecho) y elegí **Recuperar lo borrado**. **R** recupera la más cercana al cursor.
   - **Ctrl+Z** deshace y **Ctrl+Y** rehace (cortes, borrados, lo recuperado y el sonido, en el mismo historial).
5. Sonido:
   - Debajo de las miniaturas está la **pista de sonido**, con la forma de onda: muestra cómo va a salir (sin lo borrado, alineada con la línea de tiempo) y los silencios en rosa. Si el video no tiene sonido, dice **Sin sonido**.
   - **Silenciar tramo** (o **M**) deja sin sonido el mismo tramo que borraría Supr: el que tocaste en la línea de tiempo (o en la pista) o, si no tocaste ninguno, el del cursor. La imagen queda. Si ya está en silencio, el botón dice **Devolver el sonido**. Para silenciar una parte cualquiera, cortá al principio y al final.
   - La tarjeta **Sonido**, arriba a la derecha: **Quitar el sonido** (el video sale sin audio), **Volumen** (0 a 200 %), **Normalizar** (lo más fuerte queda en -1 dB), **Fundido de entrada** y **de salida** (como mucho la mitad de lo que dura el video final), **Devolver todo** y **Guardar solo el audio…** (M4A, WAV o MP3, con progreso y Cancelar).
   - Al reproducir **se escucha** lo que se va a exportar, y la imagen sigue al sonido. El botón del parlante, junto a **Filtro al reproducir**, silencia solo la vista previa (se recuerda). Si la PC no tiene salida de sonido, la vista previa anda igual, sin sonido.
6. **Mejorar calidad** (sin IA), la tarjeta debajo de **Sonido**: para videos chicos o muy comprimidos. Prendela con su interruptor y ajustá **Quitar cuadraditos**, **Nitidez** y **Usar cuadros vecinos** (0 a 100 %). Limpia los cuadraditos de la compresión, enfoca los bordes y junta detalle de los cuadros vecinos (nunca del otro lado de un corte): un 480p queda como un buen 720p, no como un 4K.
   - Al pausar, el cuadro del cursor se ve mejorado, igual que en el archivo. "Antes" es el original agrandado simple. Al reproducir se ve sin la mejora.
   - Al exportar, **720p** y **1080p** agrandan el video (con la mejora apagada nunca se agranda) y el resumen avisa que tarda más.
   - Entra al mismo historial (Ctrl+Z y Ctrl+Y) y sigue prendida al abrir otro video.
7. **Exportar video…** (Ctrl+S): MP4 H.264 con el audio sincronizado (o sin audio, si lo quitaste), en Original, 1080p o 720p. Muestra progreso, tiempo restante y un botón para cancelar. El original no se toca.

El ruido y el grano cambian en cada cuadro, como en un video real de celular, y lo demás no parpadea. El detalle del sonido está en la sección *Sonido* de [`VIDEO.md`](VIDEO.md); el de la línea de tiempo, en *Cortes que desaparecen*, y el de la mejora (con sus tiempos), en *Mejorar calidad*.

La exportación tarda bastante más que el video, porque se aplica el filtro cuadro por cuadro. Valores medidos en una PC de 16 hilos:

| Salida | Velocidad | Un video de 30 s tarda |
|---|---|---|
| 1080p | unos 2,8 cuadros/s | unos 5 min |
| 720p | unos 6 cuadros/s | unos 2,5 min |

Las capas en video se aplican a todo el cuadro, porque las zonas no siguen el movimiento. El detalle técnico, las mediciones y las limitaciones están en [`VIDEO.md`](VIDEO.md). Usa PyAV (FFmpeg) con `libx264`: PyAV es BSD y FFmpeg es LGPL, pero `libx264` es GPL. Para uso propio no cambia nada; para distribuirla como producto, tenelo en cuenta.

## Modo Audio

El modo **Audio** del selector (o **Ctrl+Shift+A**) toma una voz limpia, grabada en una oficina sin ruido o hecha con IA, y hace que **suene grabada con un celular en un lugar real**. Es lo mismo que NaturalShot hace con las fotos, pero en sonido, y también se muestra en la misma ventana. Nunca toca el audio original.

- **Escenas:** 10 presets que arman todo con un clic (nota de voz en la oficina, caminando por la calle o arriba del colectivo; video en la playa o en la ciudad; manos libres en el auto…) y escenas propias con **Guardar como escena**.
- **¿Cómo se grabó?:** nota de voz de WhatsApp, video de celular o auriculares, con el micrófono, el AGC del celular y la compresión (Opus o AAC) de cada uno. **Cuánto** va de Sutil a Fuerte y **Bajarle lo de IA** le saca a la voz lo demasiado perfecto, sin cambiar el tono ni el tiempo.
- **Ambiente:** hasta 3 capas de fondo continuo (ciudad, lluvia, olas, oficina, colectivo…) y sonidos sueltos que se arrastran en el tiempo (un colectivo, una bocina, una sirena). Todo lo genera la app por síntesis, sin grabaciones de nadie; los sonidos propios van en **Mis sonidos**.
- **Exportar** a WhatsApp (`.ogg`, Opus mono), M4A, MP3 o WAV, en segundo plano. La vista previa suena igual que lo que se exporta.
- **Con Video:** en la tarjeta Sonido del editor de video, **Editar el sonido en el modo Audio** y **Volver al video con este sonido**, y **Cambiar el sonido por…** para ponerle otra voz a un video.

El detalle (cómo se usa, la cadena de voz, los fondos, la API, las pruebas y las limitaciones) está en [`AUDIO.md`](AUDIO.md).

## Requisitos

- Windows 10 u 11
- Python 3.11 o posterior (probado con 3.14)

## Instalación y ejecución desde el código

```bat
cd AppLowCalidad
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

Después podés abrirla con doble clic en `ejecutar.bat`.

## Uso

En el modo fácil alcanza con los cuatro pasos de la columna izquierda (ver *Modos: Fácil, Editor y Video*). Lo que sigue describe el modo editor.

1. **Abrir** (Ctrl+O), o arrastrá la imagen a la vista. Formatos: JPG, PNG, WEBP, TIFF y BMP. El diálogo es de **fotos y videos**: un video se abre en el modo Video.
2. Compará el antes y el después:
   - **Dividir**: arrastrá el divisor para comparar.
   - **Antes** / **Después**: muestran una sola versión.
   - Mantené la **barra espaciadora** para ver el original.
3. Zoom:
   - Rueda del mouse (acerca hacia el cursor).
   - **100 %** (Ctrl+1) para revisar el detalle real y **200 %** (Ctrl+2) para ver ruido, grano y bordes píxel por píxel.
   - **Ajustar** (Ctrl+0) para ver la foto completa.
   - Doble clic alterna entre ajustar y 100 %. Arrastrá para desplazarte.
4. Ajustá la intensidad, agregá capas si querés y retocá las secciones. Cada valor se puede escribir exacto en su casilla. Doble clic sobre el nombre de un control lo devuelve al valor del preset; el ojo apaga solo ese efecto. **Restablecer ajustes** vuelve a los valores del preset elegido.
   - **Deshacer / Rehacer** (Ctrl+Z / Ctrl+Y): historial de hasta 100 pasos.
5. **Exportar como archivo nuevo…** (Ctrl+S):
   - **PNG**: sin pérdida.
   - **JPEG**: calidad configurable de 60 a 100.
   - Se sugiere `nombre_celular.png` y nunca se sobrescribe el original.
6. **Procesar varias fotos…**: aplica los ajustes actuales (con capas) a muchas fotos a resolución completa, con el formato y la calidad elegidos. Si cancelás la carpeta de destino, cada archivo queda junto a su original. Una foto que falla no corta el lote.

La vista previa se calcula primero sobre una copia reducida, para que responda al instante, y después a resolución completa. La versión completa es exactamente la que se exporta. Todo el procesamiento corre en hilos aparte, así que la interfaz no se congela.

## Color y orientación

- **Orientación EXIF**: se aplica al abrir, así que las fotos de celular giradas se ven derechas. Al exportar, la orientación queda en 1 para que ningún visor la vuelva a rotar.
- **Perfiles ICC**:
  - **Perfil RGB** (sRGB, Display P3, Adobe RGB…): la foto se procesa en su propio espacio y el perfil se vuelve a incrustar al exportar. Así no se recorta el gamut ni cambian los colores. Para mostrarla en pantalla se convierte a sRGB con LittleCMS.
  - **CMYK**: se convierte a sRGB.
  - **Sin perfil**: se asume sRGB y se incrusta un perfil sRGB.
- **Transparencia**: se conserva en PNG. En JPEG se compone sobre blanco.
- **EXIF**: copiar los metadatos del original es opcional (casilla en Exportar). Aun marcada, nunca salen la ubicación (GPS), los números de serie, el dueño de la cámara, el nombre de la PC ni rutas de archivos; la orientación sale en 1, las dimensiones son las reales y no se copia la miniatura del original. La política completa, la lista de salidas y la auditoría están en [`documentacion/METADATOS.md`](documentacion/METADATOS.md).

## Pruebas

```bat
.venv\Scripts\python -m unittest discover -s tests -v
```

Las pruebas verifican:

- Se conservan las dimensiones en PNG y JPEG.
- El original queda intacto (mismo hash y misma fecha de modificación).
- No se puede exportar sobre el original.
- La orientación EXIF se aplica correctamente.
- El perfil ICC se conserva.
- CMYK, transparencia y grises de 16 bits se manejan bien.
- Cada control produce un cambio visible pero acotado.
- El ruido es mayor en sombras que en luces.
- El detalle fino se reduce sin aplanar los bordes.
- La vista previa coincide con la exportación.
- Todos los presets son moderados y distintos entre sí, y las capas apiladas suman cambios acotados.
- Cada módulo hace lo que dice (`test_modulos.py`): el ruido crece con la luz en lineal, el de lectura pesa en sombras, el barril curva las rectas y deja quieto el centro, el viñeteo no toca el centro, la caída de luces quema menos blancos, el JPEG no se acumula en la pila, las máscaras forman una partición y detectan cada zona, etc.
- **Evaluación de calidad** (`test_calidad.py` + `tests/evaluacion.py`): los 34 presets sobre escenas de retrato, interior, exterior, noche, tela, degradado, alto contraste y carta de color. Se mide conservación del detalle, halos, corrimiento de color (ΔE), banding, ruido, pérdida de resolución, cambio de brillo y escalones en los límites de las máscaras. No se usa ningún detector de IA: sus puntajes no garantizan naturalidad ni calidad.
- Lote: procesa todas las fotos, sigue ante un error y no toca los originales.
- Geometría (`test_geometria.py`), selección automática (`test_seleccion_auto.py`) y borrado de objetos (`test_borrado.py`): cada motor por separado.
- Integración (`test_integracion.py`): las zonas "mascara" (congeladas, comparables, al tamaño pedido, con recorte, trazos y matriz), que cada forma de zona, el recorte y los borrados sigan sobre el mismo objeto al girar, voltear y enderezar, que la ventana real (sin pantalla) exporte exactamente lo que muestra y en el orden documentado, el nivelado automático, el cielo con caché, ajustar al contorno desde un lazo, el arrastre del clonado y que los pasos viejos del historial se sigan pudiendo abrir.
- Modo Video (`test_modo_video.py`, con la ventana real): ir a Video y volver conserva la foto, la tira, el historial y el video abierto con sus cortes, con la marca y el selector en el mismo lugar; abrir un video en Fácil pasa a Video y lo carga (con el aviso y el filtro de las fotos); soltar una foto en Video vuelve al último modo de fotos; fotos y videos juntos van cada uno a su lugar (y reemplazar un video con cortes pregunta); el diálogo de Abrir es de fotos y videos y rutea cada cosa; nunca se crea una ventana aparte ni un segundo editor; la exportación sigue al volver a las fotos (chip con el porcentaje y aviso al terminar) y cerrar la app con una en curso pregunta; el modo guardado nunca es Video; Ctrl+E y Ctrl+Shift+V; "Usar el de las fotos" y cerrar el video.
- Video (`test_video.py`): el motor (lectura, cortes, filtro por cuadro, exportación con audio, rotación) y el modo Video de la ventana real manejado con el teclado (cortar, borrar, deshacer, cuadro a cuadro y exportar).
- Cortes que desaparecen (`test_cortes.py`): el mapeo entre el tiempo original y el del resultado (`MapaTiempo`, huecos y "Recuperar lo borrado" en el motor), la línea de tiempo y la pista que muestran solo lo que se exporta (miniaturas corridas, marquitas con su menú, corchetes) y, con la ventana real, borrar, recuperar (marquita, botón derecho y R), Ctrl+Z y Ctrl+Y, recortar el principio, silenciar después de borrar, el cursor que nunca queda en lo borrado y la reproducción en el tiempo del resultado.
- Sonido del video (`test_audio.py`, el motor, y `test_sonido_ui.py`, la interfaz): la pista con la forma de onda (y "Sin sonido"), Silenciar tramo (M), la tarjeta Sonido, deshacer y rehacer de cortes y sonido, exportar sin sonido o con un silencio (medido en el archivo), guardar solo el audio y cancelar, la vista previa que suena con la imagen siguiendo al sonido (con un QtMultimedia de mentira) y que todo siga andando sin salida de sonido o sin QtMultimedia.
- Mejorar calidad en Video (`test_mejora_video.py`, el motor, y `test_mejora_ui.py`, la integración): exportar con un borrado y la mejora a 1080p da 1920×1080 con los cuadros que quedan, en orden, el audio y la duración, sin que ningún cuadro use vecinos del otro lado del corte; la ventana de vecinos es igual a `MejoradorVideo` cuadro por cuadro; con la mejora apagada sale como siempre; la tarjeta, las resoluciones que agrandan, deshacer y rehacer, "Antes" agrandado simple y "Después" igual a la exportación, la mejora que espera a que el cursor se quede quieto, y exportar desde la ventana. También los arreglos de la revisión del sonido y los cortes (juntar pasos de deshacer, un solo cuadro con los corchetes, arrastres que pierden el soltar, el tramo elegido al deshacer y las mediciones del pico que sobran).
- Modo Audio (`test_ambientes.py`, `test_voz_natural.py`, `test_proyecto_audio.py`, `test_modo_audio.py` y `test_ida_y_vuelta.py`): los fondos y sonidos generados (deterministas, con acceso aleatorio exacto, niveles y espectros); la cadena de voz (la banda de cada destino, el AGC, el eco, el anti IA sin cambio de tono, el códec y los saltos); el proyecto, las anclas al cortar, el mezclador igual a la exportación, cada formato, cancelar, escenas y Mis sonidos; la ventana real (selector, Ctrl+Shift+A, ruteo de archivos, escenas, cortes, sonidos que se arrastran, exportar y sesión) y la ida y vuelta con Video (`AudioExterno`, `editarSonidoPedido` y `usar_sonido_externo`). Detalle en [`AUDIO.md`](AUDIO.md).
- Modo fácil (`test_modo_facil.py`): cambiar de modo conserva la foto, la tira, el historial, el preset y lo editado (y cancela una herramienta del editor a medias); tocar una tarjeta cambia el preset y queda en el historial; las miniaturas son la foto procesada con cada preset, se cachean y se recalculan solo si cambia la foto, el giro o el recorte; el modo se recuerda y arranca en Fácil la primera vez; en Fácil se oculta la columna derecha; y exportar desde Fácil da el mismo archivo que desde el editor, en PNG y en JPEG.
- Actualizaciones automáticas (`test_actualizador.py`, con un servidor local que imita a GitHub):
  - versiones y manifiesto: comparación semántica y `version.json` inválido o con campos faltantes;
  - descarga: SHA-256, cancelación y que la redirección a la URL firmada no lleve `Authorization`;
  - errores: 401 (con renovación por refresh token), 403 o 404 y "sin internet" sin nada visible;
  - device flow: `authorization_pending`, `slow_down`, `expired_token`, `access_denied`, cancelar y cortes de red;
  - sesión cifrada con DPAPI, sin tokens en el registro;
  - descompresión segura;
  - script de instalación: solo toca la carpeta indicada y se ejecuta con PowerShell (instala, y con una falla simulada restaura todo);
  - el banner y el diálogo en la ventana real.
- Sesión (`test_sesion.py`): guardar y leer 3 fotos con ediciones variadas (capas con zona, pincel y máscara automática, recorte, geometría, montaje, borrados y fondo) da estados `==` a los originales; una foto que ya no existe se saltea con el aviso; un archivo dañado, cortado, de otra versión, con una clase que cambió o que pide otra clase arranca limpio y deja el `.bak`; la escritura es atómica (si falla, queda la anterior y no quedan temporales); "Quitar todas" vacía la tira y la sesión; el guardado automático llega a los 2 s sin cerrar; y **de punta a punta** con la ventana real: abrir 3 fotos, editarlas, cerrar y abrir otra ventana con el mismo APPDATA da las mismas fotos, la misma foto actual, las mismas ediciones e historial y la misma vista procesada. Con 20 fotos, recuperar no traba la interfaz.
- Desenfoque de fondo (`test_desenfoque.py`): el objeto queda idéntico, el fondo pierde el detalle fino sin cambiar de brillo, no hay halo (un objeto rojo o uno azul dejan el fondo cercano igual, y un fondo liso sigue liso hasta el borde), la intensidad escala el efecto, el resultado casi no depende de la resolución, la transición y la profundidad hacen lo que dicen, la entrada no se modifica, y el historial entiende los estados viejos de "Quitar fondo".
- Capas (`test_fusion.py`, `test_documento.py` y `test_proyecto_lite.py`, el motor; `test_capas_ui.py`, la interfaz con la ventana real en la Lite): el modo Photoshop (selector, Ctrl+Shift+P, la vista sin el filtro, el filtro sobre la composición en Fácil y Editor, soltar una imagen como capa); Ctrl+S por edición (Lite: proyecto; PRO: exportar); sin capas extra, exportar da exactamente lo de antes, bit a bit; con capas, la exportación es la vista; el panel (agregar, reordenar con botones y arrastrando, duplicar, opacidad como un solo paso por gesto, fusión, máscara pintada con las herramientas de zona, invertir, ocultar todo, ocultar, renombrar, candado y borrar, con las reglas del motor como avisos); Mover/Transformar con el mouse simulado (mover, escalar con una esquina, rotar, flechas, voltear, Enter = un paso, Esc = nada); el historial; girar y recortar con capas; el proyecto `.nslite` (ida y vuelta igual, abrir desde el diálogo y arrastrando, sin la foto original y roto); la sesión con capas (cerrar y volver a abrir); Fácil con capas; y Ctrl+arrastrar.

Rendimiento por efecto en esta PC: `.venv\Scripts\python herramientas\medir_rendimiento.py`.

## Generar el .exe con PyInstaller

```bat
construir_exe.bat
```

El script instala las dependencias, corre las pruebas y genera:

```
dist\NaturalShot\NaturalShot.exe
```

En la carpeta del proyecto queda el acceso directo **NaturalShot PRO**, que apunta a ese .exe. Para distribuirla, comprimí la carpeta `dist\NaturalShot` completa. El `.exe` necesita la carpeta `_internal` que está a su lado. Se usa el modo carpeta (`onedir`) porque arranca mucho más rápido que un único archivo.

El paquete lleva QtMultimedia (el sonido de la vista previa del video) con su plugin de Windows, y QtNetwork, que QtMultimedia necesita. El plugin de FFmpeg de Qt y el FFmpeg propio de PySide6 quedan afuera (unos 20 MB): los videos los lee PyAV, que trae el suyo. Con eso, la carpeta pesa unos 5 MB más que antes del sonido.

Para hacerlo a mano:

```bat
.venv\Scripts\python -m PyInstaller --noconfirm --clean NaturalShot.spec
```

> Cerrá la app y cualquier terminal o explorador que tenga abierta la carpeta `dist` antes de recompilar. Si no, PyInstaller no puede reemplazarla y el ejecutable queda incompleto.

Para armar el zip que se le pasa a otra persona y publicarlo como versión nueva (con el manifiesto de las actualizaciones automáticas), usá `publicar_version.bat`: ver la sección siguiente.

### Windows y Mac sin tener cada compu: GitHub Actions

En la pestaña **Actions** del repositorio, **Compilar Windows y Mac › Run workflow** arma la app en las máquinas de GitHub (también se corre sola al subir una etiqueta `vX.Y.Z`). En **Artifacts** quedan:

- `NaturalShot-PRO-windows.zip`: la carpeta `NaturalShot` (el `.exe` y `_internal`).
- `NaturalShot-PRO-mac-apple.dmg`: Mac con chip Apple (M1, M2, M3, M4…).
- `NaturalShot-PRO-mac-intel.dmg`: Mac con Intel.

Con **subir** tildado, los `.dmg` se agregan a la última versión de `Zergeeenk/naturalshot-releases`, y el botón "Descargar NaturalShot" de Pyro los ofrece a quien entra desde una Mac. Hace falta el secreto `RELEASES_TOKEN` en este repositorio (*Settings › Secrets and variables › Actions*): un token fine-grained de `naturalshot-releases` con *Contents: Read and write*.

**En Mac:**
- La primera vez, abrí el `.dmg`, arrastrá NaturalShot a Aplicaciones y abrila con **clic derecho › Abrir** (o *Ajustes del Sistema › Privacidad y seguridad › Abrir igualmente*). Va sin firma de Apple (no hace falta la cuenta de Apple Developer para un equipo interno); después abre sola.
- La actualización automática es de Windows. En Mac, las versiones nuevas se bajan desde Pyro (*menú del usuario › Descargar NaturalShot*) y se reemplaza la app en Aplicaciones.
- "Usar la placa de video" usa VideoToolbox, el codificador de Apple.

### Instalador (Inno Setup)

```bat
construir_instalador.bat
```

Construye el `.exe` (con `construir_exe.bat`) y arma `dist\instalador\NaturalShot-Setup-X.Y.Z.exe` con [Inno Setup 6](https://jrsoftware.org/isdl.php), que hay que tener instalado. El script es `instalador\NaturalShot.iss`:

- Instala en `%LOCALAPPDATA%\Programs\NaturalShot PRO` **sin pedir permisos de administrador**, así el actualizador puede escribir en esa carpeta.
- Crea el acceso directo en el menú Inicio (y en el escritorio, si se elige) y el desinstalador en "Aplicaciones instaladas".
- La versión sale de `celular_natural/__init__.py`, igual que la de "Acerca de" y la de las Propiedades del `.exe` (`NaturalShot.spec`).

Sin firma de código (D3), Windows SmartScreen va a mostrar "editor desconocido" la primera vez: hay que tocar "Más información" y después "Ejecutar de todas formas".

## Actualizaciones automáticas y cómo publicar una versión

La app compilada busca sola si hay una versión nueva, avisa y se actualiza con un clic. Las versiones se publican como *releases* de un repositorio **privado** de GitHub que solo tiene la app compilada (sin el código): `Zergeeenk/naturalshot-releases`. **No es el repositorio del código** (`Zergeeenk/NaturalShot-Pro`): si las versiones se publicaran ahí, todos los que reciben actualizaciones podrían leer el código. Pyro baja el instalador de este mismo repositorio para el botón "Descargar NaturalShot" (`NATURALSHOT_REPO=Zergeeenk/naturalshot-releases` en el servidor de Pyro). Solo pueden actualizar las personas que el dueño invita como colaboradoras y que aceptan la invitación.

El nombre del repositorio y el Client ID de la GitHub App están en dos constantes, una al lado de la otra, al principio de `celular_natural/actualizador.py`: `REPOSITORIO` y `CLIENT_ID`. Mientras `CLIENT_ID` tenga el valor de relleno (`Iv23li_RELLENO_CAMBIAR`), las actualizaciones quedan apagadas: la app no muestra avisos y el botón de la versión explica que falta configurarlas.

### Para la editora

1. **Una sola vez, crear la cuenta:** entrá a [github.com](https://github.com) y creá una cuenta gratis (con tu mail). Pasale tu nombre de usuario al dueño.
2. **Una sola vez, aceptar la invitación:** te llega un mail de GitHub ("invited you to collaborate"). Tocá **View invitation** y **Accept invitation**. Si no lo encontrás, entrá a `https://github.com/Zergeeenk/naturalshot-releases/invitations` con tu cuenta.
3. **Una sola vez, conectar la app:** abrí NaturalShot. Arriba aparece **"Conectá tu cuenta de GitHub para recibir actualizaciones"**; tocá **Conectar con GitHub**. También está en la versión (`v1.0.0`), arriba a la izquierda, junto al nombre.
   - La app muestra un código grande. Tocá **Abrir github.com/login/device**: el código se copia solo.
   - En el navegador, pegá el código, tocá **Continue** y después **Authorize**.
   - La ventanita de NaturalShot se cierra sola.
4. **Desde ahí, cada vez que haya una versión nueva**, al abrir la app aparece arriba un aviso: **"Hay una versión nueva (X.Y.Z)"**.
   - **Ver novedades** muestra qué cambió.
   - **Actualizar ahora:** se descarga la versión, se verifica, NaturalShot se cierra y se vuelve a abrir sola ya actualizada (tarda unos segundos). Al volver a abrir dice **"Listo: NaturalShot se actualizó a la versión X.Y.Z"**.
   - **Más tarde** lo oculta hasta la próxima vez que abras la app. **No avisar de esta versión** no vuelve a avisar de esa en particular, pero sí de las siguientes.
5. Para buscar a mano o desconectar la cuenta, tocá la versión (`v1.0.0`, arriba a la izquierda): **Buscar actualizaciones**, **Conectar con GitHub…**, **Desconectar la cuenta de GitHub** y **Abrir la página de versiones**.

Cosas que conviene saber:

- **No se pierde nada.** Las preferencias, en el registro de Windows, y los presets propios, en `%APPDATA%\NaturalShot`, no se tocan. Lo único que se reemplaza es la app: `NaturalShot.exe` y la carpeta `_internal`. Otros archivos que hayas dejado en esa carpeta quedan como estaban.
- **Si estás exportando** (fotos o video), la actualización espera a que termine. Si tenés fotos abiertas con cambios sin exportar, primero pregunta.
- **Sin internet**, no aparece nada: la app sigue igual y lo intenta la próxima vez.
- **Ubicación de la carpeta:** si la carpeta de NaturalShot está donde no se puede escribir (por ejemplo, en *Archivos de programa*), la app avisa y ofrece abrir la página de la versión para bajarla a mano. Lo más simple es tenerla en el Escritorio o en Documentos.
- **Errores al buscar:**
  - Si dice **"Tu cuenta de GitHub no tiene acceso"**, falta la invitación o falta aceptarla.
  - Si dice **"Tu sesión de GitHub venció"**, tocá **Conectar con GitHub** otra vez.

### Para el dueño: preparar todo (una sola vez)

Estos pasos crean cosas en GitHub. Hacelos vos, o alguien con tu permiso.

**(a) Crear el repositorio privado** (solo para las versiones compiladas; el código no se sube). Con [GitHub CLI](https://cli.github.com) y tu sesión (`gh auth login`):

```bat
gh repo create Zergeeenk/naturalshot-releases --private --add-readme --description "NaturalShot PRO: versiones compiladas"
```

`--add-readme` hace falta porque GitHub no deja crear versiones en un repositorio vacío.

**(b) Crear la GitHub App.** Es lo que permite que la app lea las versiones de un repositorio privado sin guardar ninguna contraseña tuya:

1. En GitHub, entrá a **Settings › Developer settings › GitHub Apps › New GitHub App**. No es una *OAuth App*.
2. Completá así:
   - **GitHub App name:** un nombre único, por ejemplo `NaturalShot PRO actualizaciones`.
   - **Homepage URL:** `https://github.com/Zergeeenk/naturalshot-releases`.
   - **Callback URL:** vacío. Destildá *Request user authorization (OAuth) during installation*.
   - **Expire user authorization tokens:** tildado (recomendado). Los tokens duran 8 horas y la app los renueva sola durante 6 meses.
   - **Enable Device Flow:** **tildado**. Es obligatorio.
   - **Webhook:** destildá **Active**.
   - **Repository permissions:**
     - **Contents: Read-only.**
     - **Metadata: Read-only** (se marca sola).
     - Todo lo demás en *No access*.
   - **Where can this GitHub App be installed?:** *Only on this account*.
3. Tocá **Create GitHub App** y copiá el **Client ID**, que empieza con `Iv`. No hace falta *client secret* ni *private key*: no los generes.
4. En la app, tocá **Install App**, elegí tu cuenta, después **Only select repositories** y elegí `naturalshot-releases`. Instalala solo en ese repositorio.
5. Pegá el Client ID en `CLIENT_ID`, en `celular_natural/actualizador.py`. Es público, no es un secreto.

**(c) Invitar a la editora** (con su usuario de GitHub). Ella tiene que aceptar la invitación del mail.

```bat
gh api -X PUT repos/Zergeeenk/naturalshot-releases/collaborators/USUARIO_DE_LA_EDITORA
```

> **Ojo con el permiso.** Si `Zergeeenk` es una **cuenta personal**, GitHub no permite colaboradores de solo lectura: quien acepta puede leer y escribir en el repositorio desde la web. La app igual solo lee, porque la GitHub App tiene *Contents: Read-only*. Para dar solo lectura (*Read*), el repositorio tiene que ser de una **organización** (gratis); en ese caso agregá `-f permission=pull` al comando y cambiá `REPOSITORIO`. También se puede invitar desde la web: *Settings › Collaborators › Add people*.

**(d) Publicar la primera versión con actualizaciones** y dársela a la editora a mano, por última vez. Su copia actual no tiene el actualizador:

```bat
publicar_version.bat 1.0.0 "Primera versión con actualizaciones automáticas" --subir
```

El zip para pasarle queda en `publicar\v1.0.0\NaturalShot-PRO.zip`. Es el mismo que `NaturalShot PRO - para otra PC.zip`.

### Para el dueño: publicar cada versión nueva

```bat
publicar_version.bat 1.1.0 "Novedad 1" "Novedad 2"
```

Sin argumentos, pregunta la versión y las novedades. El script (`herramientas/publicar.py`) hace estos pasos:

1. Pone `__version__ = "1.1.0"` en `celular_natural/__init__.py`.
2. Corre **todas** las pruebas. Si alguna falla, se detiene y deja la versión como estaba.
3. Compila con PyInstaller (`NaturalShot.spec`) en `dist\NaturalShot`. Antes cerrá NaturalShot si la abriste desde ahí.
4. Arma `NaturalShot-PRO.zip`, con la carpeta `NaturalShot PRO\` (el .exe y `_internal`) y el `LEEME.txt` (`herramientas/LEEME_distribucion.txt`).
5. Calcula el SHA-256 y el tamaño.
6. Escribe `version.json`, el manifiesto que lee la app:
   ```json
   {"version": "1.1.0", "fecha": "2026-10-13", "notas": ["Novedad 1", "Novedad 2"],
    "zip": "NaturalShot-PRO.zip", "sha256": "…", "tamano": 117000000, "minima": "1.0.0"}
   ```
   `minima` es la versión más vieja que se puede actualizar sola a esta. Se cambia con `--minima`.
   `obligatoria` (con `--obligatoria X.Y.Z`): quien tenga una versión **anterior** a esa tiene que actualizar. El aviso sale sin "Más tarde", sin "No avisar de esta versión" y sin la cruz para cerrarlo. Por ejemplo, `--obligatoria 1.1.0` obliga a todos los que tengan menos que 1.1.0.
7. Deja todo en `publicar\v1.1.0\` (zip, `version.json` y `notas.md`) y actualiza `NaturalShot PRO - para otra PC.zip`.

**La subida a GitHub va aparte y es opcional.** Sin `--subir` no sube nada: imprime el comando para hacerlo a mano. Con `--subir`, el script hace esto:

- Comprueba que `gh` tenga sesión, que el repositorio exista y que sea **privado**. Si no existe, lo avisa y no lo crea.
- Comprueba que esa versión no esté publicada.
- Corre:

```bat
gh release create v1.1.0 publicar\v1.1.0\NaturalShot-PRO.zip publicar\v1.1.0\version.json --repo Zergeeenk/naturalshot-releases --title "NaturalShot PRO 1.1.0" --notes-file publicar\v1.1.0\notas.md
```

Si existe `Tutorial\tutorial_compartible.pdf`, se sube junto con la versión. La guía `Tutorial\NaturalShot - Guía de uso.pdf` **no se sube nunca**, porque tiene una foto personal. La carpeta `publicar\` crece unos 115 MB por versión: se pueden borrar las viejas.

### Cómo funciona por dentro

- **Código:**
  - `celular_natural/actualizador.py` tiene la lógica. No usa Qt ni dependencias nuevas: `urllib`, `ctypes` y PowerShell.
  - `celular_natural/ui/actualizaciones.py` tiene el banner, el diálogo de conexión, el botón de versión y la coordinación con la ventana.
- **Búsqueda al abrir:** empieza 1,5 s después de abrir la ventana, en segundo plano (`QThreadPool` y `Tarea`).
  - Lee `GET https://api.github.com/repos/<repo>/releases/latest` con `Authorization: Bearer <token>`, `Accept: application/vnd.github+json` y `X-GitHub-Api-Version: 2022-11-28`.
  - De esa versión baja el asset `version.json` y compara las versiones de forma semántica (`1.10.0 > 1.9.0`).
- **Assets:** se bajan con `GET /repos/<repo>/releases/assets/<id>` y `Accept: application/octet-stream`. GitHub responde con una redirección a una URL firmada de otro dominio.
  - Las redirecciones se siguen a mano. El token **solo viaja al mismo origen** que el pedido original: a la URL firmada no se le manda (si se le mandara, fallaría).
  - Solo se siguen redirecciones a HTTPS.
- **Errores:**
  - **401:** primero intenta renovar el token con el refresh token. Si no puede, avisa "Tu sesión venció" y ofrece reconectar.
  - **403 o 404:** avisa "Tu cuenta de GitHub no tiene acceso. Pedile al dueño que te invite y aceptá la invitación que te llega por mail". Un 403 por límite de consultas se trata como "sin conexión".
  - **Sin internet, *timeout* o GitHub caído:** no se muestra nada; solo queda anotado en el registro.
- **Conexión (device flow de la GitHub App):**
  - `POST https://github.com/login/device/code` con el `client_id`.
  - Después sondea `POST https://github.com/login/oauth/access_token`:
    - respeta `interval`;
    - con `slow_down` usa el intervalo nuevo, o le suma 5 s;
    - `authorization_pending` sigue esperando;
    - `expired_token` y `access_denied` cortan con un mensaje;
    - un corte de red no corta la espera.
  - Con tokens que vencen, se renueva con `grant_type=refresh_token`. En el device flow no hace falta el *client secret*.
- **Sesión:** el token y el refresh token se guardan **cifrados con DPAPI de Windows** (`CryptProtectData`, vía `ctypes`) en `%APPDATA%\NaturalShot PRO\sesion_github.dat`.
  - Solo ese usuario de Windows, en esa PC, lo puede descifrar.
  - Nunca se escriben en texto plano ni en el registro (`actualizaciones.log`, que además tapa cualquier cosa con forma de token).
  - **Desconectar** borra el archivo.
- **Actualizar ahora** (solo con la app compilada; desde el código explica que hay que actualizar a mano):
  1. **Comprobaciones:** que la carpeta del .exe se pueda escribir (si no, ofrece la página de la versión), que haya espacio y que la versión instalada no sea anterior a `minima`.
  2. **Descarga:** baja el zip en segundo plano a una carpeta temporal (`%TEMP%\NaturalShot-actualizacion-*`), con progreso y **Cancelar**.
  3. **Verificación:** comprueba el tamaño y el **SHA-256**. Si no coinciden, borra lo bajado y no instala nada.
  4. **Descompresión:** rechaza rutas que se salgan de la carpeta y busca `NaturalShot.exe` con `_internal\` (la carpeta raíz puede tener cualquier nombre).
  5. **Espera:** si hay una exportación en curso, espera a que termine. Si hay fotos con cambios, pregunta.
  6. **Instalador:** genera `actualizar.ps1` y lo lanza separado de la app y sin ventana. Las rutas van como literales de PowerShell, con BOM UTF-8, así que sirven rutas con tildes, `'`, `’` o `&`. La app se cierra recién cuando el instalador avisa que arrancó; si no arranca en 40 s (antivirus o política de PowerShell), la app sigue abierta y avisa.
- **El script de instalación:**
  1. Espera a que termine el proceso de la app (por PID) y cualquier otra ventana abierta desde ese mismo .exe.
  2. Respalda `_internal\` y los archivos sueltos del paquete (el .exe) en la carpeta temporal.
  3. Copia la versión nueva con `robocopy /MIR` **solo sobre `<instalación>\_internal`**, y el .exe encima. No toca nada fuera de la carpeta de instalación ni los archivos ajenos que haya en ella.
  4. **Si algo falla a mitad de la copia, restaura el respaldo.**
  5. Vuelve a abrir `NaturalShot.exe`, borra los temporales y deja el resultado en `%APPDATA%\NaturalShot PRO\ultima_actualizacion.json`. La app lo muestra al abrir ("Listo…" o "No se pudo instalar…, seguís con la X").
- **Lanzamiento separado:** se usa `CREATE_NO_WINDOW` con `CREATE_NEW_PROCESS_GROUP` y `CREATE_BREAKAWAY_FROM_JOB`, no `DETACHED_PROCESS`. PowerShell 5.1 lanzado con `DETACHED_PROCESS` termina sin ejecutar nada (lo medimos). Con una consola oculta, robocopy no abre ninguna ventana.
- **Preferencias** (`QSettings("NaturalShot", "NaturalShot PRO")`):
  - `actualizaciones/omitir_version`: lo guarda "No avisar de esta versión".
  - `actualizaciones/no_pedir_conexion`: lo guarda "No mostrar más" en el aviso de conectar.

**Variables de entorno de prueba.** No cambian nada si no están definidas:

| Variable | Para qué |
|---|---|
| `NATURALSHOT_API_BASE` | Reemplaza `https://api.github.com` (por ejemplo, un servidor local). |
| `NATURALSHOT_LOGIN_BASE` | Reemplaza `https://github.com` en el device flow. |
| `NATURALSHOT_CLIENT_ID` | Reemplaza `CLIENT_ID`. |
| `NATURALSHOT_PRUEBA_ACTUALIZAR_AUTO=1` | Modo de prueba: conecta (sin abrir el navegador), toca "Actualizar ahora" y salta las confirmaciones. Guarda capturas `prueba_*.png` en `%APPDATA%\NaturalShot PRO` y cierra la app cuando no queda nada por hacer. |
| `NATURALSHOT_PRUEBA_FALLA_COPIA=1` | El instalador simula una falla a mitad de la copia, para probar que restaura el respaldo. |
| `NATURALSHOT_CONFIG` | Un `.ini` para las preferencias, en vez del registro (ya existía). |

Las pruebas están en `tests/test_actualizador.py`, con un servidor local que imita a GitHub (`tests/servidor_github_falso.py`).

## Estructura

```
main.py                         Punto de entrada
celular_natural/
  motor/                        Procesamiento (sin dependencias de interfaz)
    procesado.py                Orquestador: orden de operaciones, Ajustes, presets y perfiles
    parametros.py               Descripción de todos los controles (una sola fuente para la UI)
    comun.py                    Curvas sRGB de 16 bits, filtros guiados, utilidades
    sensor.py · optica.py       Ruido Poisson-Gaussiano y Bayer · Lente en luz lineal
    textura.py · tono.py        Detalle y texturas · Respuesta tonal y color
    grano.py · compresion.py    Grano fotográfico · Reescalado y JPEG
    mascaras.py                 Regiones sin IA (piel, bordes, textura alta y baja)
    zonas.py                    Zona (rect, elipse, lazo, pincel, máscara), recorte y su rasterizado
    fusion.py                   Capas: los 16 modos de fusión (W3C Compositing)
    documento.py                Capas: Documento, Capa, Transformacion, AlmacenImagenes y componer (con caché)
    proyecto_lite.py            Capas: proyecto .nslite (zip con el documento, sus imágenes y máscaras)
    montaje.py                  Partes de otra foto, con alineación e igualado de color
    desenfoque.py               Desenfoque de fondo (modo retrato): disco en luz lineal, sin halo
    geometria.py                Girar, voltear, enderezar y horizonte automático
    seleccion_auto.py           Cielo, piel y recorte inteligente (GrabCut)
    borrado.py                  Borrar objetos: relleno automático y tampón de clonar
    edicion.py                  Orden previo al filtro, conversión de zonas al girar y borrados con caché
    lote.py                     Procesamiento por lotes
    imagen_io.py                Carga/exportación, EXIF e ICC (y las extensiones de fotos y videos)
    video.py                    Video: lectura, edición y exportación con PyAV
    mejora_video.py             Mejorar calidad del video sin IA: vecinos, cuadraditos, agrandar y enfocar
    audio.py                    Sonido del video: ajustes, forma de onda, escucha (PCM) y exportar solo el audio
    ambientes.py                Modo Audio: fondos y sonidos sueltos por síntesis (deterministas, con acceso aleatorio)
    voz_natural.py              Modo Audio: la cadena de voz (anti IA, lugar, micrófono, AGC, ruido, códec)
    proyecto_audio.py           Modo Audio: proyecto, escenas, Mis sonidos, mezclador y exportación
  actualizador.py               Actualizaciones: GitHub (device flow, releases), DPAPI, SHA-256 e instalador
  sesion.py                     Sesión: las fotos de la tira y sus ediciones entre una vez y otra (sin Qt)
  ui/                           Interfaz PySide6
    carga.py                    Pantalla de carga animada y pase a la ventana principal
    aviso.py                    Aviso flotante discreto (por ejemplo, fotos de la sesión que ya no están)
    ventana.py                  Ventana principal: los tres modos, abrir y arrastrar, tareas y la sesión
    modo_video.py               Modo Video en la ventana: clasificar archivos, avisos, botón del selector y chip
    editor_video.py             Editor de video (el modo Video, adentro de la ventana)
    modo_audio.py               Editor de audio (el modo Audio, adentro de la ventana)
    paneles_audio.py            Tarjetas del modo Audio: escenas, cómo se grabó, cuánto, capas de fondo y sonidos
    pistas_audio.py             Pistas del modo Audio: onda grande, voz, fondo y sonidos sueltos
    linea_tiempo.py             Línea de tiempo del video (muestra el resultado, con las marquitas de lo borrado)
    forma_onda.py               Pista de sonido: forma de onda y su carga en segundo plano (reutilizable)
    reproductor_audio.py        Sonido de la vista previa: QAudioSink + LectorPCM (reutilizable)
    panel_sonido.py             Tarjeta Sonido: quitar, volumen, normalizar, fundidos y guardar el audio
    panel_mejora.py             Tarjeta Mejorar calidad (sin IA): interruptor, cuadraditos, nitidez y vecinos
    actualizaciones.py          Banner de versión nueva, conexión con GitHub y botón de la versión
    vista_comparacion.py        Antes/después, zoom, desplazamiento y arrastrar y soltar
    controles.py                Preset, intensidad, efectos (antes "capas"), secciones y máscaras
    panel_capas.py              Panel Capas (modo Photoshop de la Lite): lista, fusión, opacidad, máscara, botones y reordenar
    herramienta_transformar.py  Mover / Transformar (V): manijas, mover, escalar, rotar y voltear
    documento_capas.py          El documento de cada foto: girar y recortar con capas, máscaras y el estado en JSON
    modo_facil.py               Modo fácil: cuatro pasos y galería de estilos con miniaturas (y el modo guardado)
    montaje.py                  Tarjeta Montaje
    borrar.py                   Tarjeta Borrar objetos
    fondo.py                    Tarjeta Fondo: objeto transparente o fondo desenfocado (y ajustar al contorno)
    historial.py                Textos de cada paso del historial
    presets_usuario.py          Presets propios en JSON
    iconos.py                   Íconos de línea (Lucide SVG) que toman el color del tema
    tareas.py                   Ejecución en segundo plano con cancelación
    estilo.py                   Tema visual
tests/                          Pruebas automáticas y evaluación de calidad
herramientas/medir_rendimiento.py  Tiempos por efecto a 12 MP
herramientas/muestrario_audio.py  Genera en Muestras de audio\ los fondos, los sonidos y las escenas para escuchar
NaturalShot.spec                Configuración de PyInstaller
assets/iconos/                  Íconos SVG de Lucide (outline, monocromos)
construir_exe.bat               Compilación del .exe
publicar_version.bat            Prepara una versión (pruebas, .exe, zip, version.json); --subir la publica
herramientas/publicar.py        Lo que corre publicar_version.bat
herramientas/LEEME_distribucion.txt  El LEEME.txt que va en el zip
herramientas/generar_icono.py   Genera assets/icono.ico
```

## Limitaciones conocidas

- Las imágenes de 16 bits por canal en color se procesan a 8 bits (las de grises de 16 bits se convierten a 8).
- No abre HEIC. Convertilas antes a JPG o PNG.
- Una foto de 12 MP tarda unos 4 a 6 s en procesarse a resolución completa según el preset (en segundo plano). La vista previa reducida responde en menos de un segundo.
- **Sin GPU:** OpenCV de pip no trae CUDA, y la vía OpenCL (UMat) en una placa AMD sumaba copias y complejidad para una ganancia incierta en estos filtros. Todo corre en CPU con OpenCV/NumPy vectorizados.
- La vista previa reducida aproxima el JPEG y el Bayer (sus artefactos son de 1 px del original); a 100 % se ve la versión completa, que es la que se exporta.
- Las máscaras de piel son por color: madera, arena o cuero pueden entrar como "piel". Por eso arrancan en 100 % (neutras) y se pueden apagar. Lo mismo vale para la zona automática **Piel**: corregila con el pincel.
- **Cielo** no reconoce cielos de atardecer anaranjados ni de noche, y puede tomar una pared o un techo blanco o celeste liso que toca el borde de arriba. Detecta sobre la foto tal como se ve: si está acostada, girala primero.
- **Ajustar al contorno** falla si el objeto y el fondo tienen los mismos colores, con pelo suelto o pelaje (el borde es suave pero no un recorte de pelo a pelo) y con objetos transparentes.
- **Borrar objetos**: el relleno automático puede dejar una loma en un borde largo que cruza un hueco grande lejos de su centro, y no inventa lo que no aparece alrededor (texto, caras). Con **Fundir luz y color**, si la fuente toca un borde fuerte (por ejemplo, el horizonte), ese borde tiñe el parche: elegí la fuente un poco más adentro o desactivalo. La vista previa del clonado muestra la copia directa, sin el fundido.
- Mientras se endereza, la vista previa muestra la foto original girada, sin montaje ni borrados (al aplicar se recalcula todo).
- **Modo fácil:**
  - Las miniaturas muestran sobre todo el color y la luz de cada estilo. Los presets son moderados, así que el ruido, el grano y la nitidez casi no se notan a ese tamaño: para eso está la vista previa al 100 % o 200 %.
  - Las miniaturas muestran el estilo solo, sin las capas del editor ni el desenfoque de fondo (la vista previa sí los muestra).
  - Con 768 px de alto la galería deja ver una fila y media de estilos a la vez, porque los pasos 3 y 4 quedan fijos abajo. Las demás se ven desplazando la galería.
- **Actualizaciones automáticas:**
  - **SmartScreen y antivirus:** el .exe no está firmado, así que Windows puede volver a mostrar "Windows protegió su PC" con cada versión nueva, y algún antivirus puede demorar o bloquear el .exe nuevo o el script de PowerShell que lo instala. Si el instalador no arranca en 40 s, la app sigue abierta y ofrece bajar la versión a mano. La solución de fondo es firmar el .exe con un certificado de firma de código.
  - **Políticas de PowerShell:** en una PC de empresa, una política que fuerce la ejecución solo de scripts firmados impide instalar sola. Se avisa igual que en el punto anterior.
  - **Cuenta personal:** si el repositorio es de una cuenta personal (no de una organización), GitHub no permite colaboradores de solo lectura. La app solo lee, pero la colaboradora puede escribir en el repositorio desde la web.
  - **Sesión:** el refresh token dura 6 meses. Si la editora no abre la app en ese tiempo, tiene que volver a conectar. La sesión se cifra para el usuario de Windows y esa PC: en otra PC o con otro usuario hay que conectar de nuevo.
  - **La primera versión con el actualizador hay que pasarla a mano**, porque las copias anteriores no lo tienen.
  - Si la app se cierra de golpe a mitad de una descarga, la carpeta temporal se borra a los 3 días, la próxima vez que abra.
- **Sesión:**
  - Si abrís dos NaturalShot a la vez, la sesión que queda es la del último que guardó.
  - Las máscaras automáticas (cielo, piel, contorno) vuelven en su versión de lado 1024 (ver el punto siguiente): en una foto grande, el borde puede quedar apenas más suave que antes de cerrar.
  - Si la foto de un montaje ya no está, la foto que la usa avisa "Error al armar la foto" hasta que quites esa capa de montaje.
  - Las fotos de la tira se mantienen cargadas en memoria, como al abrirlas a mano: con muchas fotos grandes la app usa más memoria.
- **Modo Video:**
  - La primera vez que se entra a Video se carga PyAV y se arma el editor: tarda medio segundo (después es al instante).
  - A 1366 px de ancho algunos botones del modo Video quedan solo con el ícono (Filtro al reproducir) y no se ve "cuadro N de M"; el nombre sigue en la ayuda. Los modos de comparar y los de la línea de tiempo conservan el nombre.
  - El video abierto, sus cortes, su sonido y su filtro no se recuerdan al cerrar la app (las fotos sí). Al actualizarse sola, la app no pregunta por los cortes sin exportar.
  - **Sonido de la vista previa:** un cambio de volumen o de fundido se oye unos 0,3 s después (lo que ya estaba en el búfer), y no se compensa la demora del dispositivo: con auriculares inalámbricos la imagen puede ir un poco adelantada respecto del sonido.
  - Un preset propio guardado en un modo aparece en el otro al cambiar de modo.
  - **Mejorar calidad:** no inventa detalle (un 480p queda como un buen 720p), se ve recién al pausar y hace la exportación bastante más lenta, sobre todo a 1080p. En videos de cuadros por segundo variables, la vista previa puede tomar un cuadro vecino distinto del que usa la exportación.
- **Pantalla de carga:** mientras se arma la ventana (unos 0,3 s, en el hilo principal) la animación puede trabarse un instante (hasta unos 0,17 s). El fundido de la ventana usa la opacidad de Windows; en un escritorio remoto o sin efectos visuales puede verse como una aparición directa.
- Las máscaras automáticas se guardan en el historial a lado 1024; mientras la app está abierta se usa la versión completa, pero si se perdiera de la caché (muchas detecciones seguidas) la exportación usaría la de 1024, con el borde un poco más suave.

## Créditos

Los íconos son SVG de [Lucide](https://lucide.dev) v1.54.0 (licencia ISC, copia en `assets/iconos/LICENCIA-lucide-ISC.txt`). Los de girar, voltear, enderezar, nivelar, cielo, piel y clonar salen del paquete `lucide-static@0.460.0`; los del sonido (`volume-2`, `volume-x`, `audio-lines` y `music`) se copiaron a mano con ese mismo formato. Son de línea, monocromos y sin fondo: al dibujarlos se les pone el color del tema (`estilo.py`) y un trazo de 1,6, así se ven uniformes y se adaptan si cambia la paleta.
