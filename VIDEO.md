# Editor de video

Aplica a un video el mismo filtro que a las fotos: preset, intensidad, capas y todos los ajustes finos. Además permite recortar el principio y el final y borrar partes del medio, editar un poco el sonido (escucharlo al reproducir, quitarlo, silenciar tramos, subir o bajar el volumen, normalizarlo, agregar fundidos y guardar solo el audio) y **mejorar la calidad** de un video chico o muy comprimido, sin IA. Exporta un MP4 nuevo con el audio y nunca toca el original.

Es el **modo Video** de la ventana principal: el selector de arriba a la izquierda tiene **Fácil | Editor | Video**, y Video muestra el editor **en la misma ventana** (nunca en una aparte). Al final está cómo va integrado.

## Cómo se usa

0. **Entrar a Video:** tocá **Video** en el selector (ícono de película en rosa), el botón **Video** de la barra de fotos o **Ctrl+Shift+V**. También se entra solo al abrir o arrastrar un video estando en fotos ("Esto es un video: lo abrimos en el modo Video"), o al abrir un video con la app. Para volver a las fotos: **Fácil** o **Editor** en el selector, **Ctrl+E** o **Ctrl+Shift+V**. El video, sus cortes y una exportación en curso siguen ahí al volver.
1. **Abrir video** (Ctrl+O), o arrastrá el archivo a la vista. Formatos: MP4, MOV, M4V, AVI, MKV y WEBM. Los videos grabados con el celular vertical se enderezan solos. El diálogo es el mismo que el de las fotos (**Fotos y videos**): si elegís o soltás fotos, se abren en el modo de fotos.
2. Elegí el **preset** y ajustá la intensidad, las capas y las secciones, igual que en fotos. La vista previa muestra el cuadro actual con **Dividir**, **Antes**, **Después** o **Lado a lado**, y con zoom al 100 % o al 200 %.
3. Recorré el video:
   - Tocá o arrastrá la **línea de tiempo**. Muestra **cómo va a quedar**: lo borrado y lo recortado no están (ver *Cortes que desaparecen*, más abajo).
   - **Espacio** reproduce o pausa.
   - **← →** van cuadro a cuadro.
   - **J** y **L** saltan un segundo atrás o adelante.
   - **Inicio** y **Fin** llevan al primer y al último cuadro que quedan.
4. Recortá y borrá:
   - **Entrada (I)**: recorta lo de antes del cursor.
   - **Salida (O)**: recorta lo de después del cursor. El cuadro del cursor queda incluido.
   - También podés arrastrar hacia adentro los corchetes de los extremos de la línea de tiempo (se ponen rosas cuando hay algo recortado).
   - **Cortar (S)** divide el tramo en el cursor.
   - Tocá un tramo y apretá **Supr** (o **Borrar tramo**). Si no elegiste ninguno, se borra el del cursor. **Desaparece** de la línea de tiempo y lo que sigue se corre para cerrar el hueco, como en los editores del celular. No se puede borrar todo: tiene que quedar algo.
   - Lo borrado y lo recortado dejan una **marquita rosa** en la unión (una costura y una pestaña debajo de las miniaturas). Tocala, o tocá con el botón derecho cerca de la unión, y elegí **Recuperar lo borrado**. **R** recupera lo de la marquita más cercana al cursor.
   - **Ctrl+Z** y **Ctrl+Y** deshacen y rehacen los cortes, los borrados, lo recuperado y los cambios de sonido.
   - Arriba a la derecha de la línea de tiempo se ve la **duración final** y lo que dura el original ("0:07,50 de 0:10,00").
5. Sonido (ver *Sonido*, más abajo):
   - Debajo de las miniaturas está la **pista de sonido**: la forma de onda de lo que se exporta (sin lo borrado, como la línea de tiempo), con los silencios en rosa. Tocarla también mueve el cursor y elige el tramo.
   - **Silenciar tramo (M)** deja sin sonido el tramo elegido (la imagen queda). Si ya está en silencio, el botón dice **Devolver el sonido**.
   - La tarjeta **Sonido**, arriba de los ajustes de la derecha: **Quitar el sonido**, **Volumen**, **Normalizar**, **Fundido de entrada** y **de salida**, y **Guardar solo el audio…**.
   - Al reproducir se escucha lo que se va a exportar. El botón del parlante, junto a **Filtro al reproducir**, silencia solo la vista previa.
6. **Mejorar calidad** (sin IA, ver *Mejorar calidad*, más abajo): la tarjeta de la derecha, debajo de **Sonido**. Prendela con su interruptor y ajustá **Quitar cuadraditos**, **Nitidez** y **Usar cuadros vecinos**. El cuadro del cursor se ve mejorado al pausar, y al exportar **720p** y **1080p** agrandan el video.
7. **Exportar video…** (Ctrl+S):
   - Elegí la resolución (**Original**, **1080p** o **720p**) y la calidad (**Alta**, **Normal** o **Liviana**). Con **Mejorar calidad** prendida, 720p y 1080p muestran el tamaño agrandado ("1080p 1920 × 1080") y el resumen avisa que tarda más.
   - Se sugiere `nombre_celular.mp4` junto al original.
   - Mientras exporta se ven la barra, los cuadros hechos, el tiempo restante y la velocidad. **Cancelar** corta sin dejar archivos a medias.
   - Podés volver a las fotos mientras exporta: la exportación sigue y, debajo del selector, aparece **Exportando video · 45 %** (tocarlo vuelve a Video). Al cerrar la app con una exportación en curso, se pregunta antes.
   - Al terminar, un aviso muestra la ruta del archivo: un cuadro de diálogo si estás en Video, o un aviso abajo de la foto ("Listo: se exportó el video …") si estás en fotos.
8. **Cerrar el video:** la **×** junto a su nombre, abajo a la izquierda. Si tiene cortes o cambios de sonido sin exportar, pregunta (también antes de reemplazarlo por otro video).

**Ver el filtro al reproducir:** se reproduce lo que va a quedar: el cursor avanza de corrido por la línea de tiempo y pasa las uniones sin detenerse (lo borrado no se ve ni suena). Si suena, la imagen sigue al sonido (ver *Escuchar en la vista previa*).

## Cortes que desaparecen

La línea de tiempo y la pista de sonido muestran **el resultado**: los tramos conservados uno detrás de otro. Lo borrado y lo recortado (antes de la entrada y después de la salida) no se dibuja, y lo que sigue se corre para cerrar el hueco.

- **En el tiempo del resultado:** la regla, el cursor, el tiempo y el número de cuadro del transporte ("0:03,50 / 0:07,50 · cuadro 85 de 180"), la duración, las miniaturas, la reproducción (el reloj avanza en el resultado), ← → J L Inicio Fin y los tiempos de los mensajes ("Silenciado de 0:02,00 a 0:04,50").
- **En el tiempo original** (no cambia nada adentro): la edición (`EdicionVideo`), el cursor del editor (`EditorVideo.tiempo`, el cuadro que se ve), los silencios de `AjustesAudio` y la exportación, que ya usaba los tramos conservados.
- **Miniaturas:** cada tramo conservado empieza su propia tira en su comienzo, así lo que seguía a un borrado empieza justo en la unión. Cada celda muestra la miniatura más cercana a lo que se ve en su centro, entre las de su mismo tramo. Si el resultado es más corto, las celdas se ensanchan (hasta la proporción del video) para no repetir.
- **Marquitas:** una por unión donde falta algo (`MapaTiempo.huecos()`), también al principio y al final si hay algo recortado. Tocar la pestaña (o la costura, si no es un extremo) abre un menú con lo que falta ("Borrado acá: 1,0 s", "Recortado del principio: 0,5 s") y **Recuperar lo borrado**. Recuperar vuelve a poner los tramos borrados de ese hueco y, en los extremos, la entrada o la salida (`recuperar_hueco`). Los cortes quedan donde estaban, entra al historial y el cursor va al comienzo de lo recuperado.
- **El cursor nunca queda en algo que no se ve:** si se pide un instante borrado o recortado, va a la unión (el comienzo de lo que sigue). Al borrar el tramo del cursor pasa lo mismo. Ya no hace falta el aviso "No se exporta" del transporte.
- **Elegir un tramo:** solo los que se ven. Lo borrado no se elige, así que Supr ya no restaura (para eso están la marquita, R y Ctrl+Z).
- **Corchetes:** la entrada y la salida quedan siempre en los extremos. Arrastrarlos hacia adentro recorta más (mientras se arrastra se ve apagado lo que se va a ir; al soltar desaparece). Para volver atrás: la marquita del extremo o Ctrl+Z. Con **Filtro al reproducir** activo, el filtro se ve a baja resolución. Si la PC no llega a tiempo (más de 0,3 s por cuadro), se muestra el original. Al pausar, o al soltar el cursor, primero aparece el cuadro procesado reducido y después al tamaño exacto de la exportación. Ese cuadro sale igual en el archivo, salvo por la compresión H.264.

## Mejorar calidad

Para videos chicos (480p o menos) o muy comprimidos que "se ven mal". **No es IA:** solo OpenCV y NumPy, en la CPU. Lo acordado con el dueño: un 480p muy comprimido queda como **un buen 720p**, no como un 4K. El motor es `celular_natural/motor/mejora_video.py` (su docstring explica cada paso y sus mediciones); acá va cómo está integrado.

**Qué hace, por cuadro:** alinea los dos cuadros de antes y los dos de después con el actual (flujo óptico) y los combina sobre la grilla agrandada, con menos peso donde no coinciden (así no quedan fantasmas, y en un cambio de escena usa solo el actual); quita los cuadraditos y el "mosquito" de la compresión; agranda con Lanczos y enfoca solo los bordes, sin halos. Después sigue el filtro de siempre, ya al tamaño de salida: **decodificar → mejorar → filtro → codificar**.

### En la interfaz

- **Tarjeta "Mejorar calidad"** (`ui/panel_mejora.py`, `PanelMejora`, ícono `sparkles`), en la columna derecha, debajo de **Sonido** y en el mismo acordeón (al abrir una tarjeta se cierran las demás). Al empezar está cerrada y apagada.
  - **Interruptor** en la cabecera, como las secciones del filtro: se ve aunque la tarjeta esté cerrada.
  - Tres barras de 0 a 100 % (50 % por defecto; doble clic en el nombre vuelve a 50): **Quitar cuadraditos**, **Nitidez** y **Usar cuadros vecinos** (0 % no los usa y es más rápido). Apagada, las barras quedan grises.
  - Ayuda: "No es IA: limpia los cuadraditos de la compresión, enfoca los bordes y junta detalle de los cuadros vecinos. Un video chico queda como un buen 720p, no como un 4K." Abajo, una nota con a qué tamaño se exporta.
  - Como el filtro, la mejora **sigue igual al abrir otro video** (no es un cambio "sin exportar": cerrar el video no pregunta por ella).
- **Vista previa:** con la mejora prendida, el cuadro del cursor se ve mejorado, al tamaño exacto de la exportación.
  - Usa `mejorar_cuadro` con los vecinos **del mismo tramo conservado** (`tiempos_vecinos`, el mismo criterio que la exportación), leídos con `cuadro_en`, en el hilo de la vista previa. El cuadro mejorado sale igual que en el archivo, bit a bit (salvo la compresión H.264), y lo comprueba una prueba.
  - **Espera a que el cursor se quede quieto:** la vista rápida (la que sigue al cursor al arrastrar) no mejora; muestra el filtro sobre el original o, si ya está, el mejorado de la caché. La mejora va en la vista completa, que sale 0,45 s después de que el cursor se queda quieto y se descarta si se movió. Así arrastrar no acumula trabajo ni compite con una exportación. Mientras tanto, la vista dice "Mejorando la calidad…".
  - **Caché** (`CacheMejora`, hasta 96 MB): volver a un cuadro o cambiar el filtro no repite la mejora. La clave lleva los vecinos que se usan, así que un corte cerca del cursor la vuelve a calcular.
  - **Antes / Después / Dividir / Lado a lado:** "Antes" es el original **agrandado simple** (bicúbico, lo que haría cualquier programa) y "Después", la mejora con el filtro. Las ayudas de los botones lo dicen.
  - **Al reproducir se ve sin la mejora** (necesita cuatro cuadros vecinos por cuadro y no llega a tiempo), como el filtro completo: aparece al pausar. El estado lo avisa ("Reproduciendo sin "Mejorar calidad": la mejora se ve al pausar.").
- **Exportar video:** con la mejora prendida, **720p y 1080p muestran el tamaño agrandado** ("1080p 1920 × 1080") y se pueden elegir aunque el video sea más chico. Al prenderla con un video de menos de 720p y "Original" elegido, se pasa a **720p**. Si se apaga con 720p o 1080p elegido, vuelve a "Original" (no se puede agrandar) y al prenderla de nuevo (también con Ctrl+Y) vuelve lo elegido.
  - El resumen dice "mejorado a 1920 × 1080: tarda más, unos 2 min". La estimación usa lo que tardaron el filtro y la mejora en el último cuadro completo de la vista previa, con lo que rinden en paralelo (`ACELERACION_HILOS` y `ACELERACION_MEJORA`).
  - El aviso final suma "calidad mejorada (sin IA)".
- **Deshacer y rehacer:** `AjustesMejora` entra al historial con la edición y el sonido (triples). Los movimientos seguidos de una misma barra (menos de 1,5 s) son un solo paso; si vuelven al valor de antes, no queda un paso vacío.
- La sesión guardada es solo de fotos: la mejora no se guarda de una vez a la otra.

### En la exportación

`exportar_video(..., mejora=AjustesMejora(activa=True))`; con `mejora=None` o apagada, exactamente el camino de siempre.

- **Tamaño:** `tamano_salida(ancho, alto, resolucion, agrandar=True)` deja agrandar a 720p y 1080p con `tamano_mejorado`. Lo que se achica sale igual que sin la mejora.
- **Lectura:** los cuadros se leen al tamaño del original si la salida es más grande, y al de salida si es más chica (`tamano_lectura`: mejorar un 4K entero para achicarlo sería muy lento).
- **Vecinos por tramo:** `VentanaVecinos` arma cada cuadro con sus vecinos [t-2, t-1, t+1, t+2] **dentro de su tramo conservado**; en cada tramo nuevo se corta (es la misma ventana que `MejoradorVideo`, con su `reiniciar`). Una prueba compara la ventana con `MejoradorVideo` cuadro por cuadro (iguales bit a bit) y otra espía la exportación de un video con un borrado: ningún cuadro usa vecinos del otro lado del corte.
- **Hilos:** la mejora tiene sus propios hilos y cada cuadro mejorado pasa al filtro, que sigue en los suyos. Se escriben en orden, con las mismas marcas de tiempo que sin la mejora: el audio queda sincronizado. Cancelar corta sin dejar archivos.
  - **Empieza de a un cuadro** y mide los tres primeros: si la mejora resulta ser lo lento (de a uno hace menos cuadros por segundo que el filtro en sus hilos, o sea, filtro liviano, "Sin efecto" o sin filtro), pasa a `HILOS_MEJORA` = 3 cuadros a la vez (`_Cupo`). `ResultadoVideo.hilos_mejora` dice con cuántos terminó.
  - El resultado es el mismo de las dos maneras (`mejorar_cuadro` es una función pura): solo cambia la velocidad. Una prueba lo compara cuadro por cuadro.
- **Por qué así** (lo medido con el video de prueba de 10 s: 640×360 a 30 cuadros/s, 300 cuadros, muy comprimido; tandas alternadas, con la PC cargada por otras pruebas). El revisor del motor sugirió mejorar en serie, porque dos llamadas a la vez no rendían más; sin filtro sí rinden, pero con el filtro de la app no:

  | Mejora de a… | sin filtro, a 1080p | sin filtro, a 720p | preset principal, a 1080p | preset principal, a 720p |
  |---|---|---|---|---|
  | 1 cuadro (en serie, como `MejoradorVideo`) | 49,0 s (36 a 57) | 25,5 s (20 a 34) | **158,3 s** (153 a 164) | **64,0 s** (63 a 65) |
  | 2 cuadros | 35,8 s | 17,9 s | — | — |
  | 3 cuadros | **32,0 s** (28 a 36) | **17,2 s** (14 a 20) | 183,1 s (181 a 186) | 66,2 s (66 a 66) |
  | 4 cuadros | 32,9 s | — | — | — |

  Sin filtro, la mejora es el cuello de botella y repartirla rinde un 35-50 % más. Con el filtro (0,85 s por cuadro a 1080p, contra 0,15-0,21 s de la mejora), lo lento es el filtro, y repartir la mejora solo le saca CPU. Por eso decide sola.

### Cuánto tarda

El mismo video de prueba de 10 s (640×360), con el **preset principal** y calidad Alta, en esta PC (16 hilos, cargada por otras pruebas a la vez):

| Exportación | Tiempo | Cuadros por segundo |
|---|---|---|
| Sin la mejora, Original (640×360) | 14,5 s | 20,7 |
| Con la mejora, a 720p (1280×720) | 64 s | 4,7 |
| Con la mejora, a 1080p (1920×1080) | 158 s | 1,9 |
| Solo la mejora ("Sin efecto"), a 720p | 17 s | 17 |
| Solo la mejora ("Sin efecto"), a 1080p | 32 s | 9,4 |

Casi todo el tiempo extra es el filtro de la app al tamaño agrandado (a 1080p hay 9 veces más píxeles que en 640×360); la mejora suma poco encima. Un video de 1 minuto con la mejora a 720p tarda unos 6 a 7 minutos; a 1080p, unos 16.

## El filtro en video

- **Ruido y grano cambian en cada cuadro**, como el ruido de un sensor de verdad. Si quedaran fijos, se vería una textura "pegada" a la pantalla mientras la imagen se mueve.
- **Todo lo demás queda quieto, sin parpadeo.** Cada capa se aplica en dos pasos:
  1. Todo menos el ruido y el grano, con la semilla fija. Así la variación de balance, la nitidez variable y la textura de piel real son iguales en todos los cuadros.
  2. Solo el ruido y el grano, con la semilla `semilla + número de cuadro`.

  El cuadro 0 sale idéntico, píxel por píxel, a una foto procesada con los mismos ajustes. Las pruebas comprueban que en un video quieto el brillo medio de cada cuadro varía menos de medio nivel.
- **De dónde sale el filtro:** la primera vez que se entra a Video, el video copia el de las fotos (preset, intensidad, capas y ajustes). Después tiene **el suyo**: cambiarlo en Video no toca las fotos y cambiar las fotos no toca el video. **Usar el de las fotos** (arriba de la columna izquierda) lo vuelve a copiar.
- **Capas:** se aplican a todo el cuadro. Las zonas (rectángulo, lazo, pincel) son de las fotos, así que el editor de video oculta la fila **Dónde** de cada capa.
- **Máscaras por región:** funcionan, pero se calculan en cada cuadro y hacen la exportación más lenta.
- **Compresión** (JPEG y reescalado simulados): se aplica a cada cuadro antes de codificar el video.
- **Semilla:** cambia el patrón de ruido de todo el video.
- **Piel real:** la textura de poros también queda fija respecto del cuadro. En tomas con mucho movimiento conviene bajarla.

## Exportación

| | |
|---|---|
| Contenedor | MP4, con `faststart` para que empiece a reproducirse enseguida |
| Video | H.264 (`libx264`), High, yuv420p, BT.709 con rango limitado. Se guarda derecho, sin metadata de rotación |
| Audio | AAC, 192 kbit/s en estéreo y 128 en mono, con la frecuencia del original (si AAC no la admite, 48 kHz). Más de dos canales se mezclan a estéreo. Lleva los ajustes de la tarjeta Sonido (`exportar_video(..., audio=ajustes)`); con **Quitar el sonido**, el MP4 sale sin pista de audio y el resumen dice "MP4 · H.264 · sin sonido" |
| Calidad | **Alta:** CRF 17 con `tune=grain`. **Normal:** CRF 20 con `tune=grain`. **Liviana:** CRF 24 |
| Resolución | **Original**, **1080p** o **720p** (el lado corto). Sin **Mejorar calidad**, nunca agranda: si el video ya es más chico, la opción se desactiva. Con la mejora prendida, 720p y 1080p agrandan (854×480 a 1080p da 1920×1080). Al abrir un video más grande que 1080p, se sugiere 1080p; con la mejora prendida y un video de menos de 720p, 720p |
| Tiempos | Se conservan las marcas de tiempo del original, corridas lo que se borró antes. El audio queda sincronizado aunque el video tenga cuadros por segundo variables, como los de celular |

**Por qué `libx264`:** viene dentro de las ruedas de PyAV 19.0.1 (`av.codecs_available` lo lista), es el H.264 más compatible y permite calidad constante (CRF). Si en otra instalación no estuviera, `elegir_codificador()` prueba en orden `h264_mf` (Media Foundation de Windows), `libopenh264` y `mpeg4`, y elige el primero que abre de verdad. Esos usan una tasa de bits fija según tamaño y calidad.

**Por qué `tune=grain`:** x264 borra buena parte del ruido que cambia en cada cuadro. Medido sobre el preset principal:

| Calidad | Ruido entre cuadros que sobrevive (320×240 / 1280×720) | Tamaño relativo |
|---|---|---|
| CRF 18 sin `tune` | 31 % / 42 % | 1× |
| CRF 18 con `tune=grain` | 44 % / 55 % | ≈ 1,6× |
| CRF 21 sin `tune` | 12 % / 17 % | ≈ 0,4× |

Con ruido vivo, los archivos pesan más que un video común. En la prueba, 720p en **Alta** dio ≈ 10 Mbit/s. **Normal** o **Liviana** achican el archivo, pero también se pierde más ruido.

**Archivos:**

- Se escribe a un temporal en la misma carpeta (`.nombre.xxxx.parcial.mp4`) y se renombra al final.
- Si algo falla o se cancela, el temporal se borra.
- No se puede exportar sobre el original. Ni el motor ni la ventana lo permiten.

## Rendimiento

Medido en esta PC: 16 hilos y Python 3.14. El video de prueba es sintético, de 1080p30 con movimiento y audio, y se exporta completo (decodificar, filtrar, codificar y escribir) con el preset principal.

| Salida | Cuadros por segundo | Memoria pico |
|---|---|---|
| 1080p | **2,8** (2,7 a 2,9 según la tanda) | ≈ 1,1 GB |
| 720p | **6** (5,6 a 6,4) | ≈ 0,6 GB |

- Un video de 30 s a 30 cuadros por segundo tarda unos 5 min a 1080p y unos 2,5 min a 720p.
- El panel de exportación estima el tiempo con lo que tardó el último cuadro procesado.
- **Paralelismo:** se procesan 6 cuadros a la vez con hilos (NumPy y OpenCV sueltan el GIL) y se escriben en orden. Con 4 hilos da 2,8 a 1080p, y con 6 u 8, 2,9. Con procesos tampoco rinde más (3,0 a 3,2 contra 3,1): el límite es el acceso a memoria del filtro, no la CPU.
- El filtro solo, con un hilo, tarda 0,7 s por cuadro a 1080p y 0,4 s a 720p.
- **Recorrer la línea de tiempo:** ir a un cuadro al azar tarda 20 a 40 ms en 1080p (H.264 a 25 Mbit/s: 39 ms) y unos 90 ms en 4K HEVC. Avanzar cuadro a cuadro tarda unos 2 ms. Las 28 miniaturas tardan unos 0,2 s.

## Limitaciones

- **Sonido en la vista previa:** sale por la salida predeterminada de Windows y un cambio de ajuste se oye unos 0,3 s después (lo que ya estaba en el búfer). No se compensa la demora del dispositivo: con auriculares inalámbricos la imagen puede ir un poco adelantada. En modo sin pantalla (las pruebas) no suena.
- **HDR (HLG o PQ, como el Dolby Vision del iPhone):** se pasa a SDR sin mapeo de tonos y los colores pueden verse lavados. La tarjeta **Video** lo avisa.
- La rotación se lee de la matriz de visualización o del tag `rotate`. Los espejados en la matriz, que son raros, no se aplican.
- El filtro es pesado. Un video largo en 1080p puede tardar varios minutos, y 720p exporta más del doble de rápido.
- **Mejorar calidad:**
  - No inventa detalle: un 480p muy comprimido queda como un buen 720p. A 1080p se ve más grande, pero no más nítido que a 720p.
  - Al reproducir se ve sin la mejora (aparece al pausar).
  - La vista previa elige los vecinos por tiempo (cuadro ± 1 y ± 2 a los cuadros por segundo del video). En un video de cuadros por segundo variables, como los de celular, puede tomar un vecino distinto del que toma la exportación (que usa los cuadros decodificados uno tras otro) y el cuadro mejorado de la vista previa puede diferir un poco del exportado.
  - La exportación tarda bastante más (ver *Mejorar calidad*), sobre todo a 1080p. La estimación del resumen es aproximada: sale de un solo cuadro de la vista previa.
- **Hilos desde pruebas:** `QTest.qWait` no suelta el GIL y frena la exportación (0,8 en vez de 74 cuadros/s en el video de prueba). Para esperar, hay que usar `time.sleep` y `processEvents`. La app real no tiene este problema, porque `app.exec()` sí lo suelta: medido, 6 cuadros/s a 720p desde la ventana.

## Sonido

El motor está en `celular_natural/motor/audio.py` (sin Qt). PyAV se carga recién al usarlo.

| Campo de `AjustesAudio` | Qué hace | En la interfaz |
|---|---|---|
| `quitar` | El video sale sin pista de audio | Interruptor **Quitar el sonido** |
| `volumen` | De 0 a 2 (1 = igual). Por encima de 1 puede saturar: se recorta a ±1 | **Volumen**, de 0 a 200 % |
| `normalizar` | Lleva el pico de lo que se exporta a -1 dBFS (sube como mucho +30 dB) | **Normalizar (lo más fuerte a -1 dB)** |
| `fundido_entrada`, `fundido_salida` | Segundos, en el tiempo del resultado. Curva cuadrática | **Fundido de entrada** y **de salida**, de a 0,1 s y como mucho la mitad de la duración final |
| `silencios` | Tramos (inicio, fin) en segundos del tiempo **original**: no se mueven al cortar | **Silenciar tramo (M)** y **Devolver todo** |

- Orden: tramos conservados → silencios → fundidos de 5 ms en las uniones → fundidos de entrada y salida → ganancia.
- Sin clics: en cada corte y en los bordes de cada silencio hay un fundido de 5 ms.
- Por defecto, sin cambios ni cortes, las muestras salen idénticas a las del original.
- Guardar solo el audio: M4A (AAC 192/128 kbit/s), WAV de 16 bits o MP3 (si PyAV trae libmp3lame).
- MKV y WebM guardan las marcas en milisegundos; antes eso dejaba un clic por cuadro AAC (388 en 3 s). Ahora `RelojAudio` pega cada bloque al anterior cuando la marca cae dentro de esa resolución.
- Rendimiento (video de 10 min): forma de onda ≈ 2 s, pico ≈ 1,7 s, guardar 7 min en M4A 18 s, MP3 5 s, WAV 1,7 s.

### En la interfaz

- **Pista de sonido** (`ui/forma_onda.py`, `PistaOnda` con `solo_resultado=True`): va debajo de las miniaturas, alineada con ellas y, como la línea de tiempo, solo con lo que se exporta (con una rayita rosa en cada unión).
  - La forma de onda se pide una sola vez, con 4000 columnas, en un hilo (`CargadorOnda`, con `Tarea`). Se va dibujando mientras se lee ("Leyendo el sonido…").
  - Al dibujar se reduce al ancho en píxeles y queda en un lienzo: al reproducir solo se redibuja la franja del cursor. En el resultado, `onda_en_resultado` toma para cada columna el mínimo y el máximo de lo que cubre del original, a los dos lados de una unión si la cruza (nunca lo borrado de en medio).
  - Muestra **cómo va a salir**: la onda con el volumen (o la normalización) y los fundidos ya aplicados, y en rojo lo que se pasaría de ±1. Los silencios van en rosa, con "Silencio" si entra y el rango en la ayuda (en los tiempos de la regla). Sin `solo_resultado` (otros usos de la pieza), dibuja todo el archivo con lo que no se exporta apagado.
  - Con el sonido quitado, todo apagado y "Sonido quitado: el video sale sin audio". Si el video no tiene sonido, una franja que dice **Sin sonido**.
  - El tramo elegido lleva el mismo borde magenta que en la línea de tiempo. Tocar la pista mueve el cursor y elige ese tramo.
- **Silenciar tramo (M)** actúa sobre **el mismo tramo que Borrar tramo (Supr)**: el elegido en la línea de tiempo (o en la pista) o, si no elegiste ninguno, el que está bajo el cursor.
  - Silencia de su inicio a su fin, en tiempo original (`con_silencio`). Si ese tramo ya está todo en silencio, el botón dice **Devolver el sonido** y se lo devuelve (`con_sonido`).
  - Para silenciar una parte cualquiera, cortá (S) al principio y al final.
  - Un tramo borrado no se silencia (no se exporta, ni se ve ni se puede elegir). Con el sonido quitado, el botón queda apagado.
  - Después de un borrado, el tramo que se toca en la línea de tiempo (en el resultado) se silencia en su lugar del original: si se borró de 1 a 2 s, tocar en 1,5 elige el tramo de 2 a 3 y el silencio va de 2 a 3.
  - Por qué el tramo y no "entre la entrada y la salida": la entrada y la salida ya recortan, así que silenciar todo lo que queda es lo mismo que **Quitar el sonido**.
- **Tarjeta Sonido** (`ui/panel_sonido.py`, `PanelSonido`): arriba de los ajustes de la derecha, en el mismo acordeón (al abrir una tarjeta se cierran las demás). Al empezar queda abierta Sonido.
  - Los fundidos llegan como mucho hasta la mitad de la duración final. Si un corte la achica, se acortan solos, en el mismo paso de deshacer.
  - Abajo dice cuántos tramos hay silenciados y ofrece **Devolver todo**.
  - Sin video, o con un video sin sonido, lo explica y los controles quedan apagados.
- **Guardar solo el audio…**:
  - El diálogo ofrece los formatos de `formatos_audio_disponibles()` (acá M4A, WAV y MP3) y sugiere `nombre_celular.m4a`. Si el nombre no tiene extensión, se usa la del tipo elegido.
  - Se guarda en segundo plano con `exportar_audio`, en su propio hilo (no espera a una exportación de video). En la tarjeta hay barra, porcentaje, tiempo restante y **Cancelar**, y no quedan archivos a medias.
  - Mientras guarda, el video no se puede cerrar.
- **Deshacer y rehacer** guardan pares (edición, `AjustesAudio`): los cortes y el sonido van en el mismo historial (Ctrl+Z y Ctrl+Y).
  - Los movimientos seguidos de un mismo control (por ejemplo, arrastrar el volumen) en menos de 1,5 s son un solo paso.
  - Si vuelven al valor de antes, no queda un paso vacío.
- **Exportar video** pasa `audio=ajustes` a `exportar_video`. Con el sonido quitado, el resumen dice "MP4 · H.264 · sin sonido" y el aviso final, "sin sonido".
- La sesión guardada (`sesion.py`) es solo de fotos: el estado del video, con su sonido, no se guarda de una vez a la otra.

### Escuchar en la vista previa

`ui/reproductor_audio.py` (`ReproductorAudio`): un `QAudioSink` de `PySide6.QtMultimedia` (48 kHz, estéreo, int16) alimentado por un `LectorPCM` con los tramos conservados y los ajustes de ahora.

- **Modo "push":** cada 20 ms, desde el hilo de la interfaz, se escribe lo que entra en el búfer del sink (0,3 s).
  - No corre código de Python en hilos de Qt: ni filtros de eventos ni `readData` desde el hilo del audio.
  - Arrancar tarda unos 15 ms y saltar, unos 8.
- **Sincronía:** mientras suena, el reloj de la reproducción es el sonido. El instante que se muestra es `LectorPCM.original_de_resultado(inicio + processedUSecs())`.
  - Lo borrado no suena y la imagen también lo saltea.
  - Si la alimentación se traba, el sonido se corta y la imagen espera. Si el sonido termina o se corta, la imagen sigue con su propio reloj desde ahí.
- **Mover el cursor mientras suena:** el sonido se calla y vuelve desde donde está la imagen 80 ms después de que el cursor se queda quieto.
- **Cambios mientras suena:** un corte o un borrado arma de nuevo lo que suena. Un cambio de volumen, normalizar, fundidos o silencios se aplica sin cortar (`LectorPCM.cambiar_ajustes`).
- **Normalizar al escuchar:** el pico exacto (`medir_pico`) se mide en otro hilo apenas se activa, y otra vez si cambian los tramos o los silencios.
  - Mientras tanto se usa el de la forma de onda (`pico_aproximado`), que da el exacto o apenas más.
  - La interfaz nunca se traba midiendo.
- **Silenciar la vista previa:** el botón del parlante, junto a **Filtro al reproducir**. Solo calla la vista previa (no cambia lo que se exporta) y se recuerda con `QSettings`, clave `video/sonido_vista_previa`.
- **Sin salida de sonido**, si:
  - QtMultimedia no carga;
  - no hay salida de sonido, o no acepta 48 kHz estéreo;
  - la plataforma es "offscreen" (las pruebas, así no suenan en los parlantes; `NATURALSHOT_AUDIO_OFFSCREEN=1` la usa igual).

  En esos casos, el botón queda apagado con el motivo en la ayuda y la reproducción usa su propio reloj, como antes.
- **Si el dispositivo falla a mitad** (por ejemplo, se desconectan los auriculares), se avisa en el estado y se sigue sin sonido. Al volver a reproducir se busca de nuevo la salida predeterminada.
- **PySide6 6.12:** `QAudioSink.stateChanged` trae el tipo viejo `QAudio::State`, que no se puede convertir, y `state()` devuelve `QtAudio.State`, que no es igual a `QAudio.State` al comparar. Por eso el estado se mira por nombre en cada vuelta, sin conectarse a la señal.

### Piezas para un modo Audio

`ui/forma_onda.py` y `ui/reproductor_audio.py` no dependen del editor de video. `ui/panel_sonido.py` tampoco (`mostrar_quitar(False)` esconde "Quitar el sonido").

```python
from celular_natural.ui.forma_onda import CargadorOnda, PistaOnda, pico_aproximado
from celular_natural.ui.reproductor_audio import ReproductorAudio
from celular_natural.ui.panel_sonido import PanelSonido

pista = PistaOnda(margen=14)                 # señales: tiempoPedido(float, bool), presionada(float)
# PistaOnda(solo_resultado=True): dibuja solo lo que se exporta, de corrido (como el editor de video).
# La interfaz va siempre en tiempo original: la pista convierte al dibujar (motor.video.MapaTiempo).
cargador = CargadorOnda()                    # señales: parcial(FormaOnda), lista(FormaOnda o None), fallida(str)
cargador.parcial.connect(pista.establecer_forma)
cargador.lista.connect(lambda f: pista.establecer_forma(f) if f else pista.sin_sonido(duracion))
pista.cargando(duracion)
cargador.cargar(ruta)
pista.establecer_edicion(tramos, ajustes)    # cómo va a salir: tramos conservados y AjustesAudio
pista.establecer_tiempo(t)
pista.establecer_seleccion((a, b))

reproductor = ReproductorAudio()             # disponible, motivo, silenciado; señales terminado y fallo(str)
reproductor.reproducir(ruta, tramos, ajustes, desde=t, pico=None)  # True si de verdad suena
t = reproductor.posicion()                   # instante del original que suena (None si no suena)
reproductor.ir_a(t)
reproductor.cambiar_ajustes(ajustes, pico)
reproductor.detener()
reproductor.cerrar()

tarjeta = PanelSonido()                      # señales: ajustesCambiados(AjustesAudio, control), guardarAudioPedido
tarjeta.establecer(ajustes, duracion_resultado, tiene_audio=True)
```

## Sonido de otro archivo y modo Audio

El video puede sonar con otro archivo en lugar del suyo (`AudioExterno`, en `motor/video.py`). Es la ida y vuelta con el modo Audio y "Cambiar el sonido por…" (Tarea E del modo Audio; este es el lado del video).

| `alineado` | Qué es | Cómo suena |
|---|---|---|
| `"original"` | Alineado con el video **original**, sin cortes: el sonido del propio video procesado en el modo Audio | Se le aplican **los mismos tramos** del video y los mismos `AjustesAudio` (volumen, silencios en tiempo original, fundidos y normalizar). Es el camino de siempre (`preparar_mezcla`) con otra ruta |
| `"resultado"` | Empieza en el 0 del **resultado**: una voz en off | Se corta al largo del resultado (con un fundido de 5 ms en el corte) y, si es más corto, sigue en silencio. Volumen y normalizar van igual; los fundidos, en el principio y el final del resultado; los silencios, que están en tiempo original, se pasan al resultado con `MapaTiempo` (`silencios_en_resultado`) |

- Con **Quitar el sonido** no hay pista de audio, haya o no externo.
- **Formato del audio exportado:** la frecuencia del sonido del video (si el video no tiene, la del externo; si AAC no la admite, 48 kHz) y estéreo si alguno de los dos lo es. El externo se remuestrea igual que el sonido del video.
- **Antes de empezar**, un externo que no existe, que no se puede abrir o que no tiene sonido da un `ValueError` claro (`validar_audio_externo`) y no se crea ningún archivo.
- **`LectorDesdeCero`** arma la voz en off con la interfaz de `LectorPCM`. Lo usan la exportación y la vista previa (`ReproductorAudio.reproducir_lector`), así suenan igual. Adentro hay un `LectorPCM` del externo con el tramo `[(0, largo del resultado)]` y sin fundidos; los fundidos se aplican después de la ganancia (con volumen de más de 100 % y saturación, la curva se aplica sobre lo ya recortado: no se oye). Con `original_de_resultado` la imagen sigue al sonido.
- **`sonido_a_medir`** dice qué medir para normalizar (ruta, tramos y silencios): lo usan la exportación y la caché del pico del editor.
- **"Guardar solo el audio"** con externo: `exportar_sonido` (sin externo es `audio.exportar_audio`; con "original", del externo con los mismos tramos; con "resultado", con `LectorDesdeCero`).
- **Temporales:** `carpeta_temporal()` es `%APPDATA%\NaturalShot PRO\temporal`. `ruta_temporal_sonido(video)` da `nombre_sonido_AAAAmmdd-HHMMSS.wav` (con `-2`, `-3`… si ya existe). `limpiar_temporales(dias=7, conservar, antes_de_borrar)` borra los de más de una semana.

### En el editor

- **Tarjeta Sonido**, arriba:
  - un renglón que dice qué suena: "Sonido: el del video", "Sonido: voz.m4a (desde el principio)", "Sonido: editado en el modo Audio" o "Sonido: ninguno"; la ayuda tiene la ruta;
  - **Editar el sonido en el modo Audio**: guarda el sonido **completo del original** (sin cortes ni ajustes) en un WAV de `temporal`, en segundo plano, con barra y **Cancelar** debajo del botón (como "Guardar solo el audio"). Al terminar emite `editarSonidoPedido(wav, video)`. Si el video no tiene sonido, queda apagado con su ayuda;
  - **Cambiar el sonido por…**: un audio (MP3, M4A, AAC, WAV, OGG, OPUS o FLAC: `proyecto_audio.EXTENSIONES_AUDIO`) que suena desde el principio (`"resultado"`). También sirve para ponerle sonido a un video mudo;
  - **Volver al original** (enlace junto al renglón, solo con un sonido externo): lo saca.
- `usar_sonido_externo(ruta, alineado="original")` pone un externo (lo usa la ventana a la vuelta del modo Audio). Si el sonido estaba quitado, vuelve en el mismo paso. Si el archivo no sirve, avisa y devuelve False.
- **Historial:** cada paso es un `EstadoEditor(edicion, audio, mejora, externo)`; poner, cambiar o sacar el externo es un paso de deshacer.
- **Pista de sonido:** con un externo dibuja **su** forma de onda (`CargadorOnda` con el externo), puesta en el tiempo original del video con `forma_alineada` (`ui/forma_onda.py`). Con la voz en off, al cortar o borrar se vuelve a ubicar: siempre empieza en el 0 del resultado.
- **Vista previa:** con `"original"`, `reproductor.reproducir(externo, tramos, ajustes, desde, pico)`; con `"resultado"`, `reproductor.reproducir_lector(lambda: LectorDesdeCero(...))`.
- **Exportar** pasa `audio_externo=`. El resumen dice "con el sonido de voz.m4a" o "con el sonido editado", y el aviso final también. Si el archivo ya no está, avisa antes de preguntar dónde guardar.
- **Temporales:** al abrir el editor se borran los de `temporal` de más de 7 días, menos los que están en uso (el externo de ahora, los del historial y el último WAV para el modo Audio). Si uno estuviera sonando, antes se cierra su lector.
- `tiene_cambios()` cuenta el sonido externo (cerrar el video pregunta).

### Para conectar en la ventana

```python
editor.editarSonidoPedido.connect(lambda wav, video: ...)  # abrir el modo Audio: EditorAudio.abrir_desde_video(wav, video)
# a la vuelta (EditorAudio.volverAlVideoPedido(wav, video)), con el WAV que exporta el modo Audio:
editor.usar_sonido_externo(wav, "original")                # entra al historial; devuelve False si no sirve
```

El WAV de la vuelta tiene que estar alineado con el original (mismo largo, sin cortes propios del modo Audio): los cortes del video se le aplican igual.

## API del motor (`celular_natural/motor/video.py`, sin PySide6)

```python
from celular_natural.motor import video as mv

info = mv.info_video(ruta)          # InfoVideo: duracion, fps, ancho, alto (ya rotados), cuadros, codec,
                                    # tiene_audio, rotacion, tasa, inicio, codec_audio, frecuencia_audio, hdr...
rgb = mv.cuadro_en(ruta, 1.5, lado_max=1280)        # cuadro RGB uint8 que se ve a 1,5 s (con caché)
tira = mv.miniaturas(ruta, 28, 72)                  # [(segundos, rgb)] para la línea de tiempo

edicion = mv.EdicionVideo.nueva(info.duracion, info.fps).cortar(1.0).cortar(2.0).con_borrado(1)
tramos = edicion.tramos_conservados()               # [(0.0, 1.0), (2.0, 3.0)]

# Tiempo del resultado (lo que muestra la línea de tiempo) <-> tiempo original. Puras, sin leer el archivo.
mapa = mv.MapaTiempo.de_edicion(edicion)            # o MapaTiempo(tramos, duracion_original)
mapa.duracion                                       # 2.0 (lo que dura el resultado)
mapa.a_resultado(2.5)                               # 1.5; lo borrado va a la unión: a_resultado(1.5) == 1.0
mapa.a_original(1.0)                                # 2.0 (en una unión, el comienzo de lo que sigue)
mapa.a_original(np.array([0.5, 1.5]))               # también con arreglos (columnas de la forma de onda)
mapa.visible(1.5)                                   # False
mapa.rangos_resultado(0.5, 2.5)                     # [(0.5, 1.0), (1.0, 1.5)]: las partes que se ven
mapa.huecos()                                       # [Hueco(inicio=1.0, fin=2.0, en=1.0)]: una marquita por unión
mv.recuperar_hueco(edicion, mapa.huecos()[0])       # "Recuperar lo borrado": vuelve a (0.0, 3.0), con los cortes
mv.segmentos_visibles(edicion)                      # [(0, 0.0, 1.0), (2, 2.0, 3.0)]: (índice, inicio, fin) que se ven

r = mv.exportar_video(ruta, "salida.mp4", pila, tramos, resolucion="720p", calidad="Alta",
                      progreso=lambda hechos, total, faltan: ..., cancelado=lambda: False)
# r: ResultadoVideo(ruta, cuadros, duracion, ancho, alto, codec, con_audio, segundos, cuadros_por_segundo,
#                   mejorado, hilos_mejora)

# Mejorar calidad (sin IA): con la mejora prendida, 720p y 1080p agrandan.
from celular_natural.motor.mejora_video import AjustesMejora
mejora = AjustesMejora(activa=True, cuadraditos=0.5, nitidez=0.5, vecinos=0.5)
mv.tamano_salida(640, 360, "1080p")                 # (640, 360): sin la mejora nunca agranda
mv.tamano_salida(640, 360, "1080p", agrandar=True)  # (1920, 1080)
mv.tamano_lectura(640, 360, 1920, 1080)             # (640, 360): se lee al tamaño del original
mv.tiempos_vecinos(tramos, 0.5, 24)                 # instantes de t-2, t-1, t+1, t+2 (None fuera de su tramo)
r = mv.exportar_video(ruta, "mejorado.mp4", pila, tramos, resolucion="1080p", mejora=mejora)

# Sonido de otro archivo (ver "Sonido de otro archivo y modo Audio").
externo = mv.AudioExterno("voz.m4a", "resultado")    # o "original" (lo que vuelve del modo Audio)
mv.validar_audio_externo(externo)                    # ValueError claro si no existe o no tiene sonido
r = mv.exportar_video(ruta, "con_voz.mp4", pila, tramos, audio=ajustes, audio_externo=externo)
lector = mv.LectorDesdeCero("voz.m4a", tramos, info.duracion, ajustes, desde=t)  # la vista previa de la voz en off
mv.exportar_sonido(ruta, "voz.wav", tramos, ajustes, externo)                     # "Guardar solo el audio"
mv.ruta_temporal_sonido(ruta)                        # %APPDATA%\NaturalShot PRO\temporal\nombre_sonido_….wav
mv.limpiar_temporales(dias=7, conservar=[...])
```

- `procesar_cuadro(rgb, pila, indice, escala_vista=1.0)` es el filtro de un cuadro, con el ruido propio de ese cuadro. `procesar_cuadro_seguro` hace lo mismo y además repite si choca la caché de máscaras por región, que no está pensada para hilos.
- `tamano_salida(ancho, alto, "1080p")` calcula el tamaño de salida (`agrandar=True` con la mejora prendida).
- `VentanaVecinos` arma cada cuadro con sus vecinos dentro de su tramo (la ventana de `MejoradorVideo`, para poder mejorar varios cuadros a la vez). `HILOS_MEJORA` (3) es cuántos como mucho; `ResultadoVideo.hilos_mejora`, con cuántos terminó (ver *Mejorar calidad*).
- `ruta_salida_video(ruta)` sugiere `nombre_celular.mp4`.
- `elegir_codificador()` devuelve el codificador que se va a usar.
- `cerrar_lectores()` libera los archivos abiertos.
- Al cancelar se lanza `Cancelado`, el mismo de `procesado.py`.

## Interfaz

- `celular_natural/ui/editor_video.py` define `EditorVideo` (un `QWidget`; `VentanaVideo` queda como otro nombre). Es la parte central y derecha del modo Video; su columna izquierda (preset y capas, datos del video, atajos y el pie con la ×) está en `editor.lateral`. Usa los mismos `objectName` del tema.
  - `EditorVideo(ventana)`: con la ventana, abrir (Ctrl+O, el botón o un clic en la vista vacía) y soltar archivos pasan por `ventana.elegir_archivo()` y `ventana.abrir_rutas()`, que rutean fotos y videos.
  - `abrir(ruta)`, `confirmar_reemplazo(ruta)` (pregunta si el abierto tiene cortes), `cerrar_video()`, `tiene_cambios()`, `exportar()`, `detener()` (al cerrar la app: cancela y espera los hilos) y `compactar()` (acomoda las filas de botones al ancho).
  - `cargar_estado_panel(estado)` copia `PanelAjustes.estado()` de las fotos, con el nombre del preset y sin las zonas. `cargar_pila(pila)` hace lo mismo desde una tupla de `Ajustes` (busca a qué preset corresponde cada capa).
  - Señales para la ventana: `videoCambiado`, `exportacionCambiada(bool)`, `progresoExportacion(hechos, total)` y `exportacionLista(texto, detalle)` (terminó sin estar a la vista).
- `celular_natural/ui/linea_tiempo.py` define `LineaTiempo`, dibujada con QPainter: muestra el resultado (ver *Cortes que desaparecen*) con regla, miniaturas, cortes, marquitas con su menú (señal `recuperarPedido(Hueco)`), entrada y salida arrastrables, y cursor. Lo que entra y sale va en tiempo original (`establecer_tiempo`, `tiempoPedido`, `limitesPedidos`); convierte con `MapaTiempo`. Para las pruebas: `mapa`, `huecos`, `celdas()`, `pestana(i)`, `x_de(t)`, `x_de_resultado(r)`, `tiempo_en(x)` y `menu_union`.
- En `EditorVideo`: `mapa` (el `MapaTiempo` de la edición de ahora), `tiempo_resultado`, `ir_a_resultado(r)` y `recuperar(hueco=None)` (sin hueco, el más cercano al cursor: R).
- `celular_natural/ui/forma_onda.py` (`PistaOnda`, `CargadorOnda`), `celular_natural/ui/reproductor_audio.py` (`ReproductorAudio`) y `celular_natural/ui/panel_sonido.py` (`PanelSonido`): el sonido (ver *Sonido*).
- `celular_natural/ui/panel_mejora.py` (`PanelMejora`): la tarjeta "Mejorar calidad", con la misma idea que `PanelSonido` (muestra un `AjustesMejora` con `establecer(ajustes, nota)` y emite `ajustesCambiados(nuevo, control)`). En `EditorVideo`: `mejora` (los ajustes de ahora), `estimacion_exportacion()` y las piezas de la vista previa `cuadro_mejorado`, `CacheMejora` y `agrandar_simple`.
- El procesado va en segundo plano con `QThreadPool` y `Tarea`, como en la ventana principal. La exportación corre en su propio hilo y adentro usa un `ThreadPoolExecutor`.
- Íconos nuevos de Lucide 0.460.0 en `assets/iconos`: `film`, `play`, `pause`, `step-back`, `step-forward`, `skip-back`, `skip-forward`, `arrow-right-from-line`, `arrow-right-to-line` y `timer`. Para el sonido: `volume-2`, `volume-x`, `audio-lines` y `music`, copiados a mano con el mismo formato de `lucide-static` 0.460.0 y la misma licencia ISC (`music` viene de Feather, MIT, como dice `LICENCIA-lucide-ISC.txt`).

## Pruebas

```bat
set QT_QPA_PLATFORM=offscreen
.venv\Scripts\python -m unittest tests.test_video -v
```

Los videos de prueba se generan en una carpeta temporal. Cada cuadro lleva su número en binario con bloques blancos y negros, y el audio cambia por segundo: 440 Hz, silencio y 880 Hz. Las 16 pruebas verifican que:

- `info_video` da bien la duración, los fps, el tamaño, los cuadros, el códec y el audio.
- `cuadro_en` devuelve el cuadro correcto en desorden, hacia atrás, entre cuadros y más allá del final.
- Exportar sin cortes conserva los 72 cuadros en orden, la duración, los fps, el tamaño y el audio, con el segundo de silencio en su lugar.
- Exportar con tramos elimina las partes borradas: quedan los cuadros 0-23 y 48-71. El audio dura lo mismo que el video y el cambio de tono cae justo en el corte.
- Recortar el principio y el final conserva del cuadro 12 al 48, incluidos.
- El filtro modifica los cuadros.
- El cuadro 0 es idéntico a la foto procesada.
- El ruido cambia entre cuadros, pero la variación de balance y la nitidez variable no. Si cambiara toda la semilla, sí cambiarían.
- En un video estático la media por cuadro varía menos de 0,5 niveles, mientras el ruido sigue vivo.
- Cancelar lanza `Cancelado` y deja la carpeta vacía.
- El original queda intacto (mismo hash y misma fecha) y no se puede exportar sobre él.
- Las resoluciones Original, 1080p y 720p dan el tamaño esperado.
- Un video con rotación -90 (vertical de celular) se lee derecho, se exporta derecho, sin metadata de rotación, y con los cuadros correctos.
- El modo Video de la ventana real, en modo offscreen: abre el video desde la ventana principal (con el filtro de las fotos), corta con S, borra con Supr, deshace y rehace, va cuadro a cuadro con ← → J L y exporta con un diálogo falso. Se verifican los cuadros y el audio del archivo.

La integración en la ventana (cambiar de modo, rutear fotos y videos, la exportación que sigue en fotos, que nunca haya una ventana aparte) se prueba en `tests/test_modo_video.py` (8 pruebas). El motor de sonido, en `tests/test_audio.py`.

Los cortes que desaparecen se prueban en `tests/test_cortes.py` (13 pruebas):

- **Motor:** `MapaTiempo` de ida y vuelta (números y arreglos, uniones, después del final, sin tramos), `huecos` con el principio y el final, `recuperar_hueco` (cada hueco devuelve solo lo suyo y los cortes quedan) y `segmentos_visibles`.
- **Piezas sueltas:** la línea mide el resultado, lo borrado no ocupa lugar ni usa sus miniaturas, la primera miniatura de después arranca en la unión (también en los píxeles), la costura rosa, tocar pide el instante del original y elige lo que se ve, la pestaña abre el menú y "Recuperar lo borrado" pide su hueco; los corchetes recortan pasando lo borrado; `onda_en_resultado` y la pista con `solo_resultado` (nunca toma lo de en medio de una unión).
- **Con la ventana real:** borrar el tramo del medio achica la duración, el tiempo, los cuadros y la línea, y corre las miniaturas y la pista; la marquita, el menú contextual y R recuperan, con Ctrl+Z y Ctrl+Y (también del borrado de siempre); recortar el principio con I y con el corchete, y el final con O; Silenciar tramo después de un borrado va al tramo correcto en tiempo original; el cursor nunca queda en algo borrado (← → J Fin, borrar el tramo del cursor, no se puede borrar todo); y al reproducir el cursor avanza de corrido en el tiempo del resultado (con un reloj de mentira).

La interfaz del sonido se prueba en `tests/test_sonido_ui.py` (14 pruebas):

- **Piezas sueltas:**
  - la pista dibuja la onda, los silencios y lo que no se exporta, y responde al mouse;
  - el cargador entrega partes mientras lee y `pico_aproximado` coincide con `medir_pico`;
  - el reproductor sigue al sonido, salta, termina y se recupera si falla el dispositivo (con un QtMultimedia de mentira que la prueba avanza a mano);
  - sin salida de sonido o sin QtMultimedia, el reproductor no hace nada;
  - una prueba usa la salida de verdad con el volumen en 0 (se saltea si no hay salida).
- **Con la ventana real:**
  - la pista con forma de onda y la franja "Sin sonido";
  - Silenciar tramo con M: alterna, va en tiempo original y no actúa sobre un tramo borrado;
  - la tarjeta Sonido: acordeón, volumen, normalizar con el pico medido, fundidos limitados que se acortan con un borrado y vuelven al deshacer, y quitar;
  - deshacer y rehacer de cortes y sonido, con un deslizador como un solo paso;
  - exportar sin sonido (el MP4 sale sin pista de audio), y con un silencio y el volumen a la mitad (medido en el archivo);
  - guardar solo el audio en WAV y en M4A, y cancelar;
  - reproducir sin salida de sonido o sin QtMultimedia;
  - que la imagen siga al sonido y que el botón de silenciar la vista previa se recuerde.

"Mejorar calidad" en el modo Video se prueba en `tests/test_mejora_ui.py` (el motor de la mejora, en `tests/test_mejora_video.py`):

- **Motor de video:** `tamano_salida` agranda solo con la mejora (y lo que se achica sale igual), `tamano_lectura`, `tiempos_vecinos` (nunca del otro lado de un borrado), `VentanaVecinos` igual a `MejoradorVideo` cuadro por cuadro (bit a bit, con tramos de 1 y 2 cuadros); exportar con un borrado y la mejora a 1080p da un MP4 de 1920×1080 con los 48 cuadros que quedan en orden, el audio y la duración del resultado, y un espía comprueba que cada cuadro se mejora una vez con los vecinos de su tramo (los mismos que elige la vista previa); con `mejora=None` o apagada no se mejora nada y los cuadros y el audio salen iguales; cancelar no deja archivos.
- **Con la ventana real:** la tarjeta en el acordeón, el interruptor, las barras y las resoluciones que agrandan (y se sugiere 720p, y 1080p vuelve al prenderla de nuevo); el resumen "tarda más" con la estimación; deshacer y rehacer (una barra arrastrada es un paso); "Antes" agrandado simple y "Después" igual a la exportación, bit a bit; la mejora que no corre al arrastrar el cursor y sí una vez al quedarse quieto (con caché); exportar a 1080p desde la ventana con un borrado.
- **Arreglos de la revisión del sonido y los cortes:** juntar pasos de deshacer sin pegarlos al paso anterior (quitar el sonido sí-no-sí, volumen 100→110→100→120 y una barra de la mejora), la entrada y la salida que dejan justo un cuadro (24, 25, 29,97, 30 y 60 cuadros/s), los arrastres de la línea de tiempo y de la pista cuyo soltar se pierde, el tramo elegido al deshacer un corte y las mediciones del pico que ya no hacen falta.

La ida y vuelta con el modo Audio se prueba en `tests/test_ida_y_vuelta.py` (28 pruebas):

- **Motor:** `AudioExterno` (validación y pickle), `silencios_en_resultado` y `sonido_a_medir`; "original" con cortes (correlación > 0,95 con el externo cortado igual y nada del sonido del video), con los mismos ajustes (exacto en WAV: igual a `exportar_audio` del externo) y con otra frecuencia y canales (22 kHz mono); "resultado" que empieza en 0 y se corta al largo, más corto (el resto en ceros, exacto en WAV), con silencios pasados al resultado y fundido de salida, igual al de `LectorDesdeCero`, y en un video mudo; el lector sigue a la imagen; "Quitar el sonido" sin pista; un externo que no existe o sin sonido da `ValueError` sin empezar ni dejar archivos; sin externo, igual que siempre; cancelar; los temporales.
- **Editor** (sin la ventana): los tres botones y el renglón; un video mudo con voz en off (se ajusta y se exporta); un sonido que no sirve; deshacer y rehacer; `editarSonidoPedido` con un WAV del largo del original (sin cortes ni volumen) y cancelar; la vista previa con cada externo; la pista de la voz en off después de un borrado; exportar con "original" y con "resultado" (diálogos simulados), "Guardar solo el audio" de la voz en off y el aviso si el archivo ya no está; los temporales al abrir.

## Licencias

- **PyAV:** BSD-3.
- **FFmpeg de sus ruedas:** compilado como LGPL v3, pero incluye `libx264` y `libx265`, que son GPL. Usarlo en esta PC no plantea nada. Para **distribuir** el `.exe` a terceros, conviene tener en cuenta que lleva esas bibliotecas GPL. En ese caso se puede pasar a `h264_mf`, poniéndolo primero en `CODIFICADORES_H264`, aunque las DLL igual se empaquetan.

## Cómo va integrado en la ventana

- **Una sola ventana, tres modos** (`ui/ventana.py`): la columna izquierda tiene arriba la marca y el selector **Fácil | Editor | Video** (siempre en el mismo lugar) y abajo, o lo de las fotos (`_lateral_fotos`) o la columna del video (`editor.lateral`). A la derecha, o las columnas de fotos (`_pagina_fotos`) o el `EditorVideo`. Se alternan ocultando y mostrando (así el tamaño mínimo de lo oculto no cuenta).
- **Un solo editor:** `_asegurar_editor()` lo arma la primera vez que se entra a Video (recién ahí se importa PyAV) y lo deja adentro de la ventana. No hay ninguna ventana aparte.
- **Atajos sin choques:** los de las fotos (Ctrl+Z, Ctrl+O, Ctrl+S, zoom, Esc) van en `_pagina_fotos` y los del video en el `EditorVideo`. Un atajo solo anda si su widget se ve, así que en cada modo andan los suyos. Ctrl+E, **Ctrl+Shift+V** y F1 van en la ventana. Se eligió Ctrl+Shift+V ("V de video") y no Ctrl+3 porque Ctrl+0, Ctrl+1 y Ctrl+2 ya son zoom (ajustar, 100 % y 200 %). La barra espaciadora de "ver el original" (`FiltroBarraEspaciadora`) no actúa en Video, donde Espacio reproduce.
- **Rutear archivos:** `abrir_rutas(rutas)` (el diálogo de Abrir, soltar en cualquier vista o en la ventana, y `main.py` con los archivos que recibe) separa fotos y videos por extensión (`EXTENSIONES_VIDEO`, que ahora vive en `motor/imagen_io.py` para no cargar PyAV; `motor/video.py` la reexporta) y lleva cada cosa a su modo, con el aviso flotante (`ui/aviso.py`). Los textos están en `ui/modo_video.py` (`mensaje_ruteo`).
- **Modo guardado:** `QSettings`, clave `interfaz/modo`, solo `facil` o `editor`. Si se cierra en Video, se vuelve a abrir en el último modo de fotos.
- **Exportación en segundo plano:** el editor emite su progreso; la ventana muestra el chip debajo del selector mientras no está en Video y el aviso al terminar. `exportando_algo()` la incluye (la actualización automática espera) y `closeEvent` pregunta antes de cancelarla.
- **`NaturalShot.spec`:**
  - `hiddenimports`: el editor de video, la línea de tiempo, `motor.video`, `motor.audio`, `ui/forma_onda`, `ui/reproductor_audio`, `ui/panel_sonido`, `PySide6.QtMultimedia` y `av` (que no se excluye).
  - Ya **no excluye** `PySide6.QtMultimedia` ni `PySide6.QtNetwork`, que QtMultimedia importa al cargarse. Van el plugin de Windows (`windowsmediaplugin`) y los de red que trae el hook.
  - Quedan afuera el plugin de FFmpeg de Qt y el FFmpeg propio de PySide6 (unos 20 MB). Los videos los lee PyAV, que trae el suyo en `av.libs`.
  - `ui/modo_video.py` se importa directo desde `ventana.py`, así que PyInstaller lo encuentra solo.
