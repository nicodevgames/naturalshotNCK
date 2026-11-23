# Modo Audio

Toma una voz limpia (grabada en una oficina sin ruido, o hecha con IA) y hace que **suene grabada con un celular en un lugar real**: le pone un ambiente de fondo (ciudad, lluvia, olas…), sonidos en un momento justo ("en el segundo 12 pasa un colectivo"), el micrófono y la compresión del destino (una nota de voz de WhatsApp, un video de celular, unos auriculares) y le saca lo demasiado perfecto a una voz de IA. Es lo mismo que hace NaturalShot con las fotos, pero en sonido. Exporta un audio nuevo y nunca toca el original.

Es el **modo Audio** de la ventana principal: el selector de arriba a la izquierda tiene **Fácil | Editor | Video | Audio**, y Audio muestra el editor **en la misma ventana** (nunca en una aparte). Es el documento hermano de [`VIDEO.md`](VIDEO.md): comparte con el editor de video los cortes, la forma de onda, el reproductor y la tarjeta de volumen. Al final están la API, las pruebas y el muestrario para escuchar.

**No usa IA ni grabaciones de nadie.** Los fondos y los sonidos sueltos los genera la app por síntesis (solo `numpy`, sin archivos). Lo que no se puede sintetizar de forma creíble (gente hablando, pájaros, un perro) va en **Mis sonidos**, con tus propios archivos.

## Cómo se usa

0. **Entrar a Audio:** tocá **Audio** en el selector (ícono de ondas de sonido), o **Ctrl+Shift+A**, que desde Audio vuelve al modo de antes (fotos o Video). También se entra solo al abrir o arrastrar un audio estando en otro modo (la app avisa a dónde lo llevó). Si soltás una foto o un video estando en Audio, se va a su modo. A diferencia de Video, **Audio sí se recuerda**: si cerrás la app en Audio, la próxima vez abre ahí (y desde ahí, Ctrl+E o Ctrl+Shift+A llevan al último modo de fotos). El audio, sus cortes, el historial y una exportación en curso siguen ahí al cambiar de modo.
1. **Abrir un audio** (Ctrl+O), o arrastrá el archivo a la vista. Formatos: MP3, M4A, AAC, WAV, OGG, OPUS y FLAC (también se abre un video con sonido). Si el archivo no tiene sonido o no se puede leer, avisa ("Este archivo no tiene sonido") y el modo queda como estaba.
2. **Recorrer y cortar**, igual que en Video. Arriba está la forma de onda grande de la voz, con zoom (Ctrl+rueda, Ctrl++, Ctrl+−, Ctrl+0 para ajustar) y cursor, y debajo la línea de tiempo con tres pistas:
   - **Voz:** los cortes. **Espacio** reproduce o pausa, **← →** mueven una décima, **J** y **L** un segundo, **Inicio** y **Fin** van a los extremos. **Entrada (I)** y **Salida (O)** recortan lo de antes y lo de después del cursor, **Cortar (S)** divide el tramo, **Supr** borra el tramo elegido (desaparece y lo que sigue se corre; no se puede borrar todo), **R** recupera lo borrado más cerca del cursor (también con la marquita rosa de cada unión) y **Silenciar tramo (M)** lo deja mudo. **Ctrl+Z** y **Ctrl+Y** deshacen y rehacen todo: cortes, escena, fondo y sonidos. Los movimientos seguidos de un mismo control (menos de 1,5 s) son un solo paso.
   - **Fondo:** una franja con el nombre y el volumen de cada capa (con sus fundidos del principio y el final).
   - **Sonidos:** un bloque por sonido suelto, que se arrastra en el tiempo.
   - **Antes / Después:** **Antes** escucha la voz sola, con sus cortes y su volumen, sin la escena; **Después**, como se va a exportar.
3. **Columna izquierda, "Que suene real":**
   - **Escenas:** una galería de 10 tarjetas que arman todo con un clic (ver la tabla *Las 10 escenas*), más tus **escenas propias**: con **Guardar como escena…** se guarda la voz, el fondo y los sonidos del proyecto con el nombre que quieras (si ya había una con ese nombre, pregunta; las propias se borran con la × de la tarjeta). Una escena cambia los ajustes de voz, el fondo y los sonidos sueltos; no toca los cortes ni el volumen general.
   - **¿Cómo se grabó?:** **WhatsApp** (nota de voz), **Video** (de celular), **Auriculares** (o manos libres) o **Sin cambios**. Es el micrófono y la compresión del destino.
   - **Cuánto:** **Sutil** (30), **Normal** (60) o **Fuerte** (90), con un deslizador de 0 a 100. Escala todo lo de la grabación: con 0 no se graba nada y 100 es el máximo creíble.
   - **Bajarle lo de IA:** de 0 a 100. Le saca a la voz lo demasiado perfecto (ver la etapa 1, más abajo). No depende de "Cuánto".
   - **Avanzado** (plegado): el **Lugar** (Habitación, Oficina, Adentro de un auto, Adentro de un colectivo, Calle, Al aire libre o Ningún lugar), el **Eco del lugar**, el **Ruido propio del micrófono** y la casilla **Compresión del destino (Opus o AAC)**.
4. **Columna derecha, "Ambiente":**
   - **Fondo continuo:** hasta **3 capas** (por ejemplo, olas + viento), de la galería de fondos generados o de Mis sonidos. Cada capa tiene **volumen**, **intensidad** (más o menos lluvia, más o menos tránsito; solo en los fondos generados que la admiten), **quitar** y un botón para **escuchar 3 segundos** de ese fondo solo, con su volumen. Los fondos se oyen de punta a punta, con fundidos de 0,3 s al principio y al final.
   - **Sonidos sueltos:** **Agregar en el cursor** pone un sonido (generado o de Mis sonidos) que empieza donde está el cursor. En la lista, cada uno tiene volumen y borrar; en la pista **Sonidos** se **arrastran** para moverlos. Están anclados a un momento de la voz, así que **siguen a las palabras si cortás**; suenan enteros (los cortes no los recortan).
   - **Que tape la voz** (de 0 a 100): el control automático de volumen del celular baja todo cuando pasa algo fuerte (un colectivo) y la voz "se tapa". Con 0 casi no baja; con 100 la tapa bastante.
   - **Mis sonidos:** **Agregar a Mis sonidos…** copia tus archivos (MP3, M4A, AAC, WAV, OGG, OPUS o FLAC, de hasta 10 minutos) a la carpeta de la app; el original no se toca. Se pueden escuchar, renombrar y borrar. Sirven de fondo o de sonido suelto. Si un archivo desaparece por fuera de la app, se marca como "falta" y la mezcla lo saltea.
   - **Volumen general:** volumen, normalizar y fundidos de entrada y de salida de todo lo que se exporta (voz y ambiente juntos). 100 % lo deja como está.
   - **Exportar** (Ctrl+S): **WhatsApp** (`.ogg`, Opus mono), **M4A**, **MP3** o **WAV** (MP3 solo si esta instalación de PyAV trae `libmp3lame`). Se sugiere `nombre_celular.ogg` (o la extensión del formato) junto al original. Corre en segundo plano, con barra, tiempo restante y **Cancelar** (que no deja archivos a medias). Sigue aunque cambies de modo: debajo del selector aparece un chip con el porcentaje (tocarlo vuelve a Audio) y, al terminar, un aviso. Si cerrás la app con una exportación en curso, pregunta antes (cerrar la cancela, sin dejar archivos a medias).
5. **Cerrar el audio:** si tiene cambios sin exportar, pregunta (también antes de reemplazarlo por otro).

**Atajos** (solo andan mientras se ve Audio): Espacio, ← →, J L, Inicio, Fin, I, O, S, Supr (o Retroceso), R, M, Ctrl+Z, Ctrl+Y (o Ctrl+Shift+Z), Ctrl+O, Ctrl+S, Ctrl+rueda, Ctrl++, Ctrl+− y Ctrl+0. La columna izquierda trae la tarjeta "Atajos del audio" con los principales.

**Sesión:** el proyecto de audio (voz, cortes, escena, fondos, sonidos, historial y cursor) se recuerda al cerrar la app, igual que las fotos. Si la voz ya no está, aparece el aviso flotante de siempre.

## Ida y vuelta con Video

El sonido de un video se puede retocar en el modo Audio y volver al video, o se le puede poner a un video otro audio. Del lado del video, el detalle está en [`VIDEO.md`](VIDEO.md), *Sonido de otro archivo y modo Audio*.

- **Ir:** en la tarjeta **Sonido** de Video, **Editar el sonido en el modo Audio** guarda el sonido **completo del original** (sin los cortes ni los ajustes del video) en un WAV de `%APPDATA%\NaturalShot PRO\temporal\`, en segundo plano, y emite `editarSonidoPedido(wav, video)`. La ventana cambia a Audio y llama a `EditorAudio.abrir_desde_video(wav, video)`. Si el video no tiene sonido, el botón queda apagado.
- **Cortes bloqueados:** el sonido abre con `video_origen` puesto. Arriba se ve la franja "Sonido del video X · **Volver al video con este sonido**" y **no se puede cortar ni borrar tramos** (`EditorAudio.cortes_bloqueados`), porque si no el sonido se desalinea con la imagen: los cortes se hacen en el video. Todo lo demás (escena, fondo, sonidos sueltos, volumen, silencios) sí se puede.
- **Volver:** **Volver al video con este sonido** exporta el proyecto a un WAV en `temporal\` (con barra y Cancelar en la franja) y emite `volverAlVideoPedido(wav, video)`. La ventana vuelve a Video y llama a `EditorVideo.usar_sonido_externo(wav, "original")`. Si el video ya no está abierto, avisa y deja la ruta del WAV. Si abriste otro audio mientras se preparaba, el sonido no vuelve (y se borra el WAV).
- **`AudioExterno`** (en `motor/video.py`): `AudioExterno(ruta, alineado)`.
  - `"original"`: el sonido está alineado con el video **original**, sin cortes (es lo que vuelve del modo Audio). Se le aplican **los mismos tramos** del video y los mismos ajustes de sonido (volumen, silencios, fundidos, normalizar).
  - `"resultado"`: el sonido empieza en el 0 del **resultado**, como una voz en off. Se corta al largo del video y, si es más corto, sigue en silencio.
- **Cambiar el sonido por…** (también en la tarjeta Sonido de Video): pone cualquier audio como sonido `"resultado"`, desde el principio. También sirve para ponerle sonido a un video mudo. **Volver al original** lo saca. Poner, cambiar o sacar el sonido externo es un paso de deshacer.

## Cómo funciona por dentro

Todo se procesa adentro a **48 kHz, estéreo, float32**, en bloques `(n, 2)`; una voz mono se duplica en los dos canales. Solo hacen falta `numpy`, `opencv`, PyAV y PySide6 (no hay `scipy`): filtros FIR por FFT, convolución por FFT para el eco y envolventes a 1 ms para el AGC y las variaciones. No hay bucles de Python muestra por muestra.

| Unidad | Archivo | Qué hace |
|---|---|---|
| Biblioteca generada | `celular_natural/motor/ambientes.py` | Fondos y sonidos sueltos por síntesis, deterministas, con acceso aleatorio |
| Voz natural | `celular_natural/motor/voz_natural.py` | `AjustesVoz` y `CadenaVoz`: la cadena de 7 etapas |
| Proyecto y mezcla | `celular_natural/motor/proyecto_audio.py` | Proyecto, escenas, Mis sonidos, `MezcladorAudio` y exportación |
| Interfaz | `celular_natural/ui/modo_audio.py`, `paneles_audio.py`, `pistas_audio.py` | El editor, las tarjetas de las columnas y las pistas de la línea de tiempo |
| Ida y vuelta | `celular_natural/motor/video.py`, `ui/editor_video.py` | `AudioExterno` y los botones de la tarjeta Sonido de Video |

Reutiliza del editor de video `ui/forma_onda.py`, `ui/reproductor_audio.py`, `ui/panel_sonido.py` (como "Volumen general") y la línea de tiempo con sus cortes (`LineaVoz` es una `LineaTiempo`).

### La cadena de voz (`CadenaVoz`)

Siete etapas, en el orden fijo en que pasa en la vida real. La voz entra ya editada (tramos y silencios) y el ambiente entra ya con su volumen:

1. **Bajarle lo de IA** (solo a la voz, si `anti_ia` > 0): recorte suave de los extremos que un celular no capta (debajo de 60 Hz y arriba de 15 kHz); un de-esser que comprime la banda de 5 a 9 kHz cuando domina (las "s" demasiado perfectas); el brillo se mueve ±1 dB, despacio; y el volumen se mueve ±1,5 dB, despacio (unos 0,3 Hz), como si se moviera la cabeza. **No cambia el tono ni el tiempo** (eso suena raro).
2. **El lugar** (si `lugar` no es "ninguno"): eco corto con una respuesta al impulso sintética (reflexiones tempranas y una cola de ruido que decae, más rápido en los agudos), por convolución FFT. El nivel depende de `eco`, de `cuanto` y de la distancia del destino (el video se graba a un brazo y suma más lugar; WhatsApp, pegado a la boca, menos).
3. **Voz y ambiente juntos:** acá se suman el fondo y los sonidos sueltos. Así pasan por el mismo micrófono y la misma compresión que la voz, y no suena "pegado".
4. **Micrófono del destino** (un FIR de fase mínima, más una saturación suave sobremuestreada ×2):
   - **WhatsApp:** pegado a la boca, con efecto de proximidad (+3 dB a 150 Hz), banda de 80 Hz a 7,5 kHz.
   - **Video:** a un brazo de distancia, menos graves (−2 dB) y más lugar, banda de 100 Hz a 12 kHz.
   - **Auriculares:** banda angosta de 200 Hz a 7 kHz con un pico de presencia a 2,5 kHz, y una compuerta que baja el fondo en las pausas y lo devuelve al hablar (el "bombeo" de la reducción de ruido del Bluetooth).
   - WhatsApp y auriculares graban con un solo micrófono (mono desde acá); el video, en estéreo.
5. **Control automático de volumen del celular (AGC):** envolvente RMS cada 1 ms, objetivo −20 dBFS, ataque de 30 ms y liberación de 400 ms, de −15 a +6 dB. Cuando pasa algo fuerte, baja todo y la voz se tapa; `tapa` regula cuánto.
6. **Ruido propio del micrófono:** ruido rosa muy bajo (−62 dBFS × `ruido_propio` × `cuanto`).
7. **Compresión del destino**, codificando y decodificando de verdad con PyAV: WhatsApp, Opus mono a 16 kHz y 24 kbit/s; Video, AAC estéreo de 128 kbit/s; Auriculares, Opus mono a 16 kHz y 32 kbit/s (como el mSBC del Bluetooth).

Las etapas 4 a 7 ("cómo se grabó") solo corren con un destino y `cuanto` > 0. Con destino, la salida se recorta a ±1 (un celular graba en 16 bits). `cuanto` escala todo lo de la grabación: el lugar, la respuesta del micrófono (en dB, así 0 es plano), la saturación, el AGC, la compuerta y el ruido. Con `AjustesVoz()` por defecto (sin destino, sin lugar y sin anti IA), la salida es `voz + ambiente` sin tocar.

**Bloques, saltos y latencia:**
- Procesar de corrido en bloques de cualquier tamaño da lo mismo que en uno solo (los controles se deciden en una grilla absoluta de 1 ms).
- Lo que depende del tiempo (las variaciones lentas del anti IA, el ruido propio) sale del tiempo absoluto, así que un salto da lo mismo.
- Después de un salto, `reiniciar(inicio)` con una **pre-lectura de 0,5 s** (`PRELECTURA`) deja el eco y los filtros exactos y el AGC casi igual. El códec no: arranca con otro estado, así que con compresión suena igual pero la forma de onda no es la de corrido.
- El códec atrasa (Opus 1368 muestras, AAC 3120); la cadena lo compensa y la salida queda alineada con la entrada. Al terminar, `vaciar()` entrega lo que el códec guardaba.
- Con códec, la cadena trabaja solo a 48 kHz.
- Velocidad (con todo prendido, en bloques de 50 ms): unas 18 veces el tiempo real con WhatsApp o auriculares y unas 12 con video (el codificador AAC es lo más lento).

### Fondos sintéticos deterministas, con acceso aleatorio

Cada fondo es una receta por capas (ruido de color, tonos con armónicos y temblor, eventos como autos que pasan, olas, ráfagas o puertas del colectivo). Nada de tonos puros quietos ni de "ruido de radio sin señal": todo varía despacio. Los ruidos de fondo se arman con **estéreo de celular** (dos micrófonos a unos 14 cm, con la coherencia entre canales de un campo difuso) y los vehículos con **Doppler** exacto de la geometría, la diferencia de tiempo entre micrófonos y el rebote en el piso.

- **Determinista:** la misma semilla da siempre lo mismo, en cualquier proceso (el azar sale de un hash estable, no de `hash()` de Python). Por eso la vista previa suena igual que la exportación y nunca hay un loop audible.
- **Acceso aleatorio exacto:** `GeneradorFondo.leer(inicio, n)` da lo mismo que leer de corrido desde 0 y cortar. Se arma por **trozos fijos de 1 s**; el azar sale de bloques de 0,25 s con su propia semilla; cada trozo se filtra junto con una **pre-lectura** de los bloques anteriores (regenerados con sus semillas) que se descarta, así no hay uniones entre trozos. Las variaciones lentas y las envolventes dependen del tiempo absoluto; los osciladores integran la fase por ranuras de varios segundos con un número entero de ciclos; y los eventos salen de un calendario pseudoaleatorio por ventana de tiempo.
- **Niveles calibrados:** un fondo sale con −30 dBFS RMS a intensidad 0,5 (`NIVEL_FONDO_DBFS`) y un sonido suelto con el pico en −6 dBFS (`PICO_SONIDO_DBFS`). El volumen lo pone el mezclador.
- **Velocidad:** cada fondo, más de 20 veces el tiempo real; cada sonido suelto, en menos de medio segundo. Los sonidos sueltos quedan en una caché de los últimos 8.

### La mezcla (`MezcladorAudio`)

Tiene la **misma interfaz que `LectorPCM`** (`leer`, `leer_array`, `bytes_por_muestra`, `ir_a`, `ir_a_resultado`, `posicion_resultado`, `duracion_resultado`, `terminado`, `cambiar_ajustes`, `cerrar`…), así `ReproductorAudio` reproduce cualquiera de los dos. Adentro, en orden:

1. **Voz:** un `LectorPCM` en float32 con los tramos y los silencios (lo borrado se saltea; las uniones y los silencios llevan fundidos de 5 ms).
2. **Ambiente:** los fondos (de 0 a 3 capas) más los sonidos sueltos, cada uno con su volumen. El volumen va de 0 a 1 con una curva en dB: 12·log2(2·v) dB, o sea que 0,5 es el nivel de referencia, 1 es +12 dB y 0 es silencio. Un archivo de Mis sonidos se calibra igual (de fondo, su RMS a −30 dBFS; de sonido suelto, su pico a −6 dBFS), así "0,5" quiere decir lo mismo en todos los casos.
3. **`CadenaVoz`**, con las siete etapas.
4. **Final**, en el tiempo del resultado: volumen y normalizar de `AjustesAudio`, fundidos de entrada y de salida, y un **limitador suave** (por debajo de 0,9 no toca nada; por encima, una curva tanh que nunca llega a ±1).
5. **Formato de salida:** int16 (lo que pide el reproductor) o float32.

Detalles de la mezcla:
- **Anclas:** los sonidos sueltos se anclan a un momento de la voz en tiempo **original**. Si el ancla cae en un tramo borrado, el sonido arranca al principio del siguiente tramo conservado. Si pasan del final del resultado, se apagan con un fundido de 15 ms.
- **Fondos:** cada capa cubre todo el resultado (no se corta en los cortes). Un archivo de Mis sonidos usado de fondo se repite con un fundido cruzado de igual potencia de 2 s, calculado por índices (cualquier punto da lo mismo que de corrido).
- **Lectura adelantada:** un fondo puede tardar 150 a 200 ms en un solo pedido y el reproductor lee desde el hilo de la interfaz. Con `adelanto` (la vista previa usa `ADELANTO_VISTA_PREVIA`, 1 s), un hilo propio mantiene lleno un búfer con la mezcla de antes del paso final; `leer` solo copia y aplica el volumen (menos de 1 ms). Si el búfer no alcanza (al arrancar o tras un salto), `leer` da lo que haya, sin rellenar con silencio, y la posición se queda quieta. Un cambio de proyecto mientras suena se funde en 10 ms (sin clic al mover un deslizador); un cambio solo de volumen, normalizar o fundidos se oye enseguida.
- **Lo que falta:** un archivo de Mis sonidos que ya no está (o que no se puede leer, o que dura más de 10 minutos) y un fondo o sonido generado que esta versión no conoce se saltean sin error. `MezcladorAudio.faltan` los nombra para que la interfaz los marque.
- **Normalizar:** el pico se mide con una pasada del mismo mezclador (`medir_pico_proyecto`, en caché por proyecto) sin volumen, sin fundidos y sin limitador. La interfaz lo mide en otro hilo y, mientras tanto, usa el estimado con la forma de onda.

### La vista previa es igual a la exportación

`exportar_proyecto` usa **el mismo `MezcladorAudio`** que la vista previa, así que lo que escuchás es lo que sale. La cadena se alimenta siempre en una grilla fija del resultado (trozos de 100 ms), lean lo que lean de afuera, y se reinicia en un borde de la grilla al menos 0,5 s antes de cada salto. Sin compresión, lo que sigue a un salto da lo mismo que de corrido (salvo diferencias mínimas del AGC); con compresión suena igual, pero la forma de onda no es la misma.

### Formatos

| Formato | Archivo | Cómo se codifica |
|---|---|---|
| `whatsapp` | `.ogg` | Opus **mono**, 24 kbit/s, **codificado a 16 kHz** como las notas de voz de verdad (se decodifica a 48 kHz y corta arriba de 8 kHz igual que la vista previa) |
| `m4a` | `.m4a` | AAC estéreo, 192 kbit/s, a 48 kHz |
| `mp3` | `.mp3` | MP3 estéreo, 192 kbit/s, a 48 kHz (si PyAV trae `libmp3lame`) |
| `wav` | `.wav` | PCM de 16 bits, estéreo, a 48 kHz |

- Con destino **WhatsApp** y formato WhatsApp, la etapa 7 de la cadena se saltea al exportar (`codec=False`): el archivo ya sale en Opus y no se comprime dos veces.
- Se escribe a un temporal en la misma carpeta y se renombra al final; si algo falla o se cancela, el temporal se borra. No se puede exportar sobre el original, ni con el sonido quitado, ni sin tramos.
- Con **normalizar** y el pico todavía sin medir, el progreso cuenta dos pasadas: medir y escribir.

## Las 10 escenas

Salen de `proyecto_audio.ESCENAS`. Una escena es un dato: `AjustesVoz` + de 0 a 3 capas de fondo + sonidos sugeridos (en **fracción de la duración del resultado**, que `aplicar_escena` convierte en anclas). Todas usan "Cuánto" en Normal (0,6) y un poco de "Bajarle lo de IA" (0,4), salvo la última (0,6). Los volúmenes son los de la escena (0,5 es el nivel de referencia).

| Clave | Escena | Cómo se grabó | Lugar | Fondo (volumen) | Sonidos sugeridos (posición, volumen) |
|---|---|---|---|---|---|
| `nota_oficina` | Nota de voz en la oficina | WhatsApp | Oficina | Oficina (0,30) | — |
| `nota_calle` | Nota de voz caminando por la calle | WhatsApp | Calle | Calle con tránsito (0,50) | Colectivo pasando a los 40 % (0,55) |
| `nota_colectivo` | Nota de voz arriba del colectivo | WhatsApp | Adentro de un colectivo | Motor del colectivo (0,55) | Frenada de colectivo a los 60 % (0,45) |
| `nota_lluvia` | Nota de voz bajo la lluvia | WhatsApp | Al aire libre | Lluvia (0,50) | Auto pasando a los 50 % (0,45) |
| `video_playa` | Video en la playa | Video de celular | Al aire libre | Olas (0,55) + Viento (0,40, intensidad 0,4) | — |
| `video_ciudad` | Video en la ciudad | Video de celular | Calle | Ciudad (0,50) | Sirena lejos a los 30 % (0,40) |
| `video_casa` | Video en casa | Video de celular | Habitación | Habitación (0,30) | — |
| `manos_libres_auto` | Manos libres en el auto | Auriculares | Adentro de un auto | Adentro de un auto (0,50) | — |
| `auriculares_calle` | Auriculares en la calle | Auriculares | Calle | Calle con tránsito (0,50) + Viento en el micrófono (0,35, intensidad 0,4) | — |
| `solo_anti_ia` | Solo bajarle lo de IA | Sin cambios | Ninguno | Sin fondo | — (Bajarle lo de IA en 0,6) |

## Fondos y sonidos

De `ambientes.FONDOS` (11 fondos continuos) y `ambientes.SONIDOS` (6 sonidos sueltos). "Intensidad" dice si ese control cambia algo; la habitación no tiene.

| Clave | Fondo | Qué es | Intensidad |
|---|---|---|---|
| `ciudad` | Ciudad | Rumor grave de la ciudad y autos lejanos | sí |
| `calle` | Calle con tránsito | Autos, motos y colectivos que pasan cerca | sí |
| `lluvia` | Lluvia | De llovizna a lluvia fuerte | sí |
| `agua` | Agua o río | Un arroyo que corre; con más intensidad, un río | sí |
| `olas` | Olas | Olas que rompen en la orilla | sí |
| `viento` | Viento | Viento con ráfagas entre los árboles | sí |
| `oficina` | Oficina | Aire acondicionado, zumbido eléctrico y un teclado lejos | sí |
| `habitacion` | Habitación | El aire quieto de una habitación | no |
| `auto` | Adentro de un auto | Ruido de ruta desde adentro; con más intensidad, más rápido | sí |
| `colectivo` | Motor del colectivo | Desde adentro: arranca, acelera, frena y abre las puertas | sí |
| `viento_mic` | Viento en el micrófono | Golpes graves del viento sobre el celular | sí |

| Clave | Sonido suelto | Qué es | Duración típica |
|---|---|---|---|
| `colectivo_pasa` | Colectivo pasando | Motor diésel que pasa cerca, con el silbido del freno | 10 s |
| `auto_pasa` | Auto pasando | Un auto que pasa cerca | 6,4 s |
| `moto_pasa` | Moto pasando | Una moto que pasa acelerando | 6 s |
| `frenada_colectivo` | Frenada de colectivo | El «pssst» del freno de aire | 2,2 s |
| `bocina` | Bocina | Un auto toca bocina | 2 s |
| `sirena_lejos` | Sirena lejos | Una sirena a varias cuadras | 8 s |

Cada sonido suelto tiene variantes por semilla (otra velocidad, otro lado, otro toque de bocina).

## API (para programadores)

Todo el motor está sin PySide6. PyAV se carga recién al usarlo (comprimir, leer o escribir archivos).

```python
from celular_natural.motor import ambientes as am
from celular_natural.motor import proyecto_audio as pa
from celular_natural.motor.audio import AjustesAudio
from celular_natural.motor.voz_natural import AjustesVoz, CadenaVoz

# --- Biblioteca generada (motor/ambientes.py) ---
am.FONDOS, am.SONIDOS                                # dict[str, InfoAmbiente]: clave, nombre, descripcion, icono, intensidad, duracion
g = am.GeneradorFondo("lluvia", intensidad=0.5, semilla=0, frecuencia=48000)
x = g.leer(inicio, n)                                # (n, 2) float32; acceso aleatorio exacto
y = am.generar_sonido("colectivo_pasa", semilla=0)   # (n, 2) float32, de solo lectura, con caché

# --- Voz natural (motor/voz_natural.py) ---
ajustes = AjustesVoz(destino="whatsapp", cuanto=0.6, anti_ia=0.4, lugar="calle", eco=0.5,
                     ruido_propio=0.5, compresion=True, tapa=0.5, semilla=0)   # inmutable; ajustes.sin_cambios()
cadena = CadenaVoz(ajustes, frecuencia=48000, codec=True)
salida = cadena.procesar(voz, ambiente, inicio)      # (n, 2) float32; con códec devuelve menos al principio (cadena.latencia)
cadena.reiniciar(inicio)                             # al saltar (antes, procesar PRELECTURA = 0,5 s anteriores)
cola = cadena.vaciar()                               # al terminar: lo que el códec todavía guardaba

# --- Proyecto (motor/proyecto_audio.py) ---
p = pa.abrir_proyecto("voz.m4a")                     # ProyectoAudio nuevo; ValueError si no tiene sonido
p = pa.aplicar_escena(p, pa.ESCENAS["nota_calle"])
p = p.con(sonidos=p.sonidos + (pa.SonidoSuelto("generado", "bocina", ancla=12.0, volumen=0.7),),
          fondos=(pa.FondoProyecto("generado", "lluvia", volumen=0.5, intensidad=0.6),))   # hasta pa.CAPAS_MAX = 3
pa.ProyectoAudio(ruta, tramos, sonido: AjustesAudio, voz: AjustesVoz, fondos, sonidos, video_origen=None)
pa.duracion_resultado(p); pa.ancla_en_resultado(p, ancla)

pa.escenas_propias(); pa.guardar_escena("Mi escena", p); pa.borrar_escena("Mi escena")
pa.carpeta_sonidos(); pa.mis_sonidos()               # %APPDATA%\NaturalShot PRO\sonidos
pa.agregar_a_mis_sonidos(ruta)                       # copia con nombre único; devuelve la ruta nueva
pa.renombrar_sonido("viejo.wav", "nuevo"); pa.borrar_sonido("nuevo.wav"); pa.cargar_sonido("nuevo.wav")

m = pa.MezcladorAudio(p, desde=0.0, formato="s16", pico=None, codec=True, adelanto=0.0)
datos = m.leer(48000)                                # bytes int16 intercalados (leer_array: (n, 2) float32)
m.ir_a_resultado(5.0); m.cambiar_proyecto(otro); m.faltan; m.cerrar()
pico = pa.medir_pico_proyecto(p, cancelado=lambda: False)

pa.formatos_proyecto_disponibles()                   # lista de FormatoAudio; WhatsApp, M4A, MP3 (si hay), WAV
pa.ruta_salida_proyecto(p, "whatsapp")               # voz_celular.ogg junto a la voz, sin pisar nada
r = pa.exportar_proyecto(p, "salida.ogg", formato=None, progreso=lambda hechas, total, falta: ...,
                         cancelado=lambda: False)    # ResultadoAudio(ruta, formato, duracion, frecuencia, canales, segundos)
```

- `volumen` de `FondoProyecto` y `SonidoSuelto` va de 0 a 1 (`pa.ganancia_volumen(v)` da el factor lineal).
- `ProyectoAudio`, `FondoProyecto`, `SonidoSuelto`, `AjustesVoz` y `Escena` son inmutables (`dataclass(frozen=True)`), se guardan con `pickle` y se cambian con `.con(...)`: deshacer es guardar estados.
- Al cancelar se lanza `Cancelado`, el mismo de `procesado.py`.
- La interfaz: `from celular_natural.ui.modo_audio import EditorAudio`. Una sola instancia, que `ventana.py` arma la primera vez que se entra a Audio. Señales: `audioCambiado`, `estadoCambiado`, `exportacionCambiada(bool)`, `progresoExportacion(hechas, total)`, `exportacionLista(texto, detalle)` y `volverAlVideoPedido(wav, video)`. Métodos útiles: `abrir(ruta)`, `abrir_desde_video(wav, video)`, `cargar_proyecto(...)`, `aplicar_escena(clave)`, `agregar_fondo(origen, clave)`, `agregar_sonido(origen, clave, ancla)`, `exportar()`, `volver_al_video()`, `estado_sesion()` y `restaurar_sesion(...)`.

## Dónde se guardan las cosas

Todo va dentro de `%APPDATA%\NaturalShot PRO\` (la misma carpeta de la sesión y de las actualizaciones):

| Qué | Dónde |
|---|---|
| Mis sonidos | `%APPDATA%\NaturalShot PRO\sonidos\` (se crea al agregar el primero; los nombres repetidos quedan `nombre (2).ext`) |
| Escenas propias | `%APPDATA%\NaturalShot PRO\escenas.json` (se escribe de forma atómica: un temporal y `os.replace`; si está dañado, no hay ninguna y no es un error) |
| WAV de la ida y vuelta con Video | `%APPDATA%\NaturalShot PRO\temporal\` (el video borra los de más de 7 días al abrir el editor) |
| Sesión | `%APPDATA%\NaturalShot PRO\sesion\sesion.pkl`: el proyecto de audio va en una clave aparte (`audio`), dentro de su propio pickle; una sesión de antes, que no la tiene, se lee igual, y si el audio no se puede leer, se sigue sin él pero con las fotos |
| Preferencias | `QSettings("NaturalShot", "NaturalShot PRO")`: `interfaz/modo` (puede ser Audio), `audio/sonido_vista_previa` (si la vista previa suena) y `audio/formato_exportar` (el último formato elegido) |

Las exportaciones van donde elijas (se sugiere junto al original) y el audio original nunca se modifica.

## Pruebas

Corren con el resto: `.venv\Scripts\python -m unittest discover -s tests -v`. Los audios se generan en cada prueba (tonos y "voces" sintéticas con PyAV); nada usa archivos del usuario, y las que tocan datos usan un `APPDATA` y un `.ini` temporales.

| Archivo | Qué prueba |
|---|---|
| `tests/test_ambientes.py` (19) | Determinismo (también entre procesos y con varios hilos), acceso aleatorio exacto (bloques sueltos = de corrido), niveles calibrados, sin NaN ni saturación, espectro esperable por tipo (lluvia con agudos, motor con graves), que no haya loop, el Doppler del colectivo, memoria y velocidad |
| `tests/test_voz_natural.py` (31) | `AjustesVoz()` no toca; bloques = todo junto; la banda de cada destino medida con FFT sobre ruido blanco; el AGC baja la voz con un ruido fuerte (y más con más `tapa`); el eco alarga la cola; el anti IA varía el nivel dentro de lo pedido sin cambiar el tono; el códec (alineación, largo, que no rompa); saltos y `reiniciar`; velocidad |
| `tests/test_proyecto_audio.py` (37) | Anclas al cortar, mezclador = exportación (misma señal), saltar y seguir, cada formato, cancelar sin dejar archivos, escenas propias y Mis sonidos en un `APPDATA` temporal, lo que falta, pickle y sesión, archivos de solo audio (MP3, M4A, OGG y WAV) |
| `tests/test_modo_audio.py` (16) | La ventana real, sin pantalla: el selector con Audio, Ctrl+Shift+A, ruteo de archivos (un audio soltado en otro modo pasa a Audio; una foto vuelve a las fotos; un archivo sin sonido avisa), escenas, cortes, sonidos sueltos que se arrastran, hasta 3 capas, deshacer y rehacer, exportar a WhatsApp con un diálogo simulado, la exportación que sigue al cambiar de modo (chip), escuchar con y sin salida de sonido y la sesión |
| `tests/test_ida_y_vuelta.py` (30) | `AudioExterno` ("original" y "resultado"), `exportar_video(..., audio_externo=)`, `LectorDesdeCero`, "Guardar solo el audio" con externo y los temporales; en el editor de video, los botones de la tarjeta Sonido, `editarSonidoPedido`, `usar_sonido_externo`, deshacer y rehacer, la pista y la vista previa con el externo, y exportar |

(Entre paréntesis, la cantidad de funciones `test_`.) En los tests con hilos, para esperar se usa `time.sleep` y `processEvents`: `QTest.qWait` no suelta el GIL (ver *Limitaciones* de [`VIDEO.md`](VIDEO.md)).

## Muestrario para escuchar

`herramientas/muestrario_audio.py` genera en `Muestras de audio\` (en la carpeta del proyecto) lo necesario para escuchar y decidir qué suena creíble:

- `2 - Fondos y sonidos\Fondos\`: cada fondo en dos intensidades (`(suave)`, 0,3, y `(fuerte)`, 0,8), de 20 s, con la semilla 1.
- `2 - Fondos y sonidos\Sonidos\`: cada sonido suelto.
- `3 - Escenas\`: una voz de prueba (`Voz de prueba.wav`) y cada escena aplicada a esa voz con `aplicar_escena` y exportada con `exportar_proyecto` (las notas de voz en `.ogg`, en el formato de WhatsApp; las demás en `.m4a`), más un `LEEME.txt` con qué es cada cosa y qué hay que decir de cada una.
- `1 - Voz (adelanto)\` no la toca el script: son las muestras que se hicieron antes, con la cadena de voz sola (cada destino, el AGC con poca y mucha "tapa"…).

La voz de prueba la genera Windows con su voz en español (`System.Speech`, sin conexión; Microsoft Sabina si está; si no hay ninguna en español, cualquier voz instalada, y avisa). **Nunca usa archivos personales.**

```bat
.venv\Scripts\python herramientas\muestrario_audio.py                 todo
.venv\Scripts\python herramientas\muestrario_audio.py --solo-escenas
.venv\Scripts\python herramientas\muestrario_audio.py --voz-nueva     vuelve a generar la voz de prueba
```

## Limitaciones

- **Es síntesis, no grabaciones.** Los fondos y los sonidos suenan creíbles, pero no son grabaciones reales; lo que no se puede sintetizar de forma creíble (gente hablando, pájaros, perros) va en Mis sonidos. No hay llamada telefónica entre los destinos, ni cambio de tono o de velocidad de la voz, ni varias voces o pistas de voz, ni reducción de ruido de grabaciones sucias.
- **El objetivo es sonar a celular, no engañar a un detector.** Es un conjunto de aproximaciones: ningún ajuste garantiza que una voz de IA deje de reconocerse como tal.
- **Con compresión, después de un salto la forma de onda no es la de corrido.** Suena igual (medido: −15 dB de diferencia en Opus con voz, −23 dB en AAC), pero no es muestra a muestra. La exportación, que va de corrido, es siempre la misma. El AGC, después de un salto, puede diferir unos 0,1 dB durante un segundo.
- **Con códec, la cadena trabaja solo a 48 kHz.**
- **Mis sonidos:** hasta 10 minutos por archivo (uno más largo da error al agregarlo y la mezcla no lo usa); la caché guarda hasta 10 minutos de audio decodificado (unos 230 MB). Renombrar un sonido hace que los proyectos y las escenas que lo usaban por el nombre viejo lo vean como "falta".
- **Un archivo de Mis sonidos que falta se saltea sin error** (la interfaz lo marca como "falta"). Un fondo o sonido generado de una versión futura que esta no conoce también.
- **Sin destino no se recorta** dentro de la cadena (voz + ambiente + eco puede pasar de ±1); el limitador suave final de la mezcla evita que se pase.
- **No se puede borrar todo el audio:** tiene que quedar algo. Con el sonido quitado o sin tramos no se exporta.
- **Sonido de la vista previa:** sale por la salida predeterminada de Windows (como en Video). No se compensa la demora del dispositivo, y sin salida de sonido, sin QtMultimedia o en modo sin pantalla (las pruebas) todo anda igual pero sin sonido, con un reloj propio. Al mover un deslizador mientras suena, el cambio se oye al instante, pero un cambio de tramos vuelve a armar lo que suena desde el cursor.
- **Ida y vuelta con Video:**
  - la sesión guardada no recuerda el sonido externo del video (ni nada del video);
  - "Editar el sonido en el modo Audio" siempre parte del sonido del video, aunque ya haya un sonido editado;
  - el WAV que vuelve tiene que ser del largo del original (por eso en ese caso no se corta en Audio);
  - con `"original"` y un externo más corto que el video, el fundido de salida cae al final del externo (igual en la vista previa y en el archivo).
- **El editor se arma recién la primera vez que se entra a Audio** (ahí se carga PyAV).
