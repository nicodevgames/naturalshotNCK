# Modo Audio: diseño

Fecha: 13/10/2026. Estado: aprobado por el dueño en el chat (partes 1 y 2), con el pedido de hacerlo rápido con subagentes.

## Para qué

El dueño graba su voz en una oficina, sin ningún ruido, y a veces genera su voz con IA. Quiere que esos audios suenen **grabados de verdad con un celular en un lugar real**:

- un ambiente de fondo (ciudad, agua, lluvia…);
- sonidos en un momento justo ("en el segundo 12 pasa un colectivo y se entiende la mitad");
- "bajarle lo de IA" a una voz demasiado perfecta.

Es lo mismo que hace NaturalShot con las fotos, pero en sonido.

## Decisiones del dueño

| Pregunta | Respuesta |
|---|---|
| ¿De dónde salen los sonidos? | Una biblioteca **generada por la app** (síntesis) y **"Mis sonidos"** (archivos propios que quedan guardados) |
| ¿Qué se edita? | **Audios sueltos**, en un modo "Audio" nuevo. Los videos siguen con su sección Sonido |
| ¿Cómo va el fondo? | Un **fondo continuo** y **sonidos sueltos** ubicados en la línea de tiempo |
| ¿Video y Audio se conectan? | **Ida y vuelta:** desde Video, "Editar el sonido en el modo Audio" y "Volver al video con este sonido"; en Video, además, "Cambiar el sonido por…" |
| ¿A qué tiene que sonar? | **Nota de voz de WhatsApp**, **video de celular** y **auriculares o manos libres** (llamada telefónica no) |
| Presets | Sí, "**escenas**" que arman todo con un clic, y escenas propias |

## Cómo se usa (interfaz)

**Selector:** `Fácil | Editor | Video | Audio` (atajo Ctrl+Shift+A). Se abre o se arrastra un audio (MP3, M4A, WAV, OGG, OPUS, AAC, FLAC). Si se suelta un audio en otro modo, se pasa a Audio con un aviso (igual que con los videos, `mensaje_ruteo`). Si se suelta una foto o un video en Audio, se va a su modo.

**Centro:**
- Forma de onda grande de la voz, con reproducir y pausar (Espacio), zoom y cursor.
- Línea de tiempo con tres pistas:
  1. **Voz**, con cortes, tramos borrados y silencios, como en Video.
  2. **Fondo:** una franja con el nombre y el volumen.
  3. **Sonidos:** bloques que se arrastran en el tiempo.
- Herramientas: entrada (I), salida (O), cortar (S), borrar tramo (Supr), silenciar tramo y deshacer y rehacer con historial.

**Columna izquierda, "Que suene real":**
- **Escenas:** galería de tarjetas (tabla de abajo) más las escenas propias ("Guardar como escena").
- **¿Cómo se grabó?:** WhatsApp, Video de celular, Auriculares o manos libres, o Sin cambios.
- **Cuánto:** Sutil, Normal o Fuerte (de 0 a 100).
- **Bajarle lo de IA:** de 0 a 100.
- **Avanzado** (plegado): lugar y eco, ruido propio, compresión del destino y "que tape la voz".

**Columna derecha, "Ambiente":**
- **Fondo continuo:** hasta **3 capas** (por ejemplo, olas + viento), elegidas de una galería de fondos generados y de "Mis sonidos". Cada capa con volumen, intensidad (por ejemplo, más o menos lluvia) y quitar, y un botón para escuchar solo el fondo.
- **Sonidos sueltos:**
  - "Agregar en el cursor", con los sonidos generados o los de "Mis sonidos".
  - Una lista de los que ya están, cada uno con volumen y borrar.
- **Que tape la voz** (de 0 a 100): el control automático de volumen del celular baja la voz cuando hay un sonido fuerte.
- **Mis sonidos:**
  - "Agregar a Mis sonidos…" copia el archivo a `%APPDATA%\NaturalShot PRO\sonidos\`;
  - también se puede renombrar y borrar.
- **Exportar:**
  - formatos: **WhatsApp** (`.ogg`, Opus mono), M4A, MP3 y WAV;
  - progreso y cancelar, en segundo plano;
  - sigue aunque se cambie de modo, con el chip junto al selector, como el video.

**Sesión:** el proyecto de audio se recuerda al cerrar, igual que las fotos (`sesion.py`).

**Ida y vuelta con Video** (lo hace la etapa E):
- En Video, **"Editar el sonido en el modo Audio"** extrae el sonido completo del video, sin los cortes, a un WAV en `%APPDATA%\NaturalShot PRO\temporal\` y lo abre en Audio. Arriba se ve una franja: "Sonido del video X · **Volver al video con este sonido**".
- **"Volver al video con este sonido"** exporta el proyecto a WAV y se lo pone al video como sonido **alineado con el original**: los cortes del video se le aplican igual.
- En Video, **"Cambiar el sonido por…"** pone cualquier audio como sonido **desde el principio del resultado** (voz en off), cortado al largo del video. "Volver al sonido original" lo saca.

## Escenas (presets)

| Escena | Cómo se grabó | Lugar | Fondo | Sonidos sugeridos |
|---|---|---|---|---|
| Nota de voz en la oficina | WhatsApp | Oficina | Oficina (aire acondicionado) | — |
| Nota de voz caminando por la calle | WhatsApp | Calle | Calle con tránsito | Colectivo pasando a los 40 % |
| Nota de voz arriba del colectivo | WhatsApp | Adentro de un colectivo | Motor del colectivo | Frenada a los 60 % |
| Nota de voz bajo la lluvia | WhatsApp | Exterior | Lluvia | Auto pasando a los 50 % |
| Video en la playa | Video de celular | Exterior | Olas + viento | — |
| Video en la ciudad | Video de celular | Calle | Ciudad | Sirena lejos a los 30 % |
| Video en casa | Video de celular | Habitación | Habitación | — |
| Manos libres en el auto | Auriculares | Adentro de un auto | Ruta desde el auto | — |
| Auriculares en la calle | Auriculares | Calle | Calle con tránsito + viento en el micrófono | — |
| Solo bajarle lo de IA | Sin cambios | Ninguno | Sin fondo | — |

Una escena es un dato: `AjustesVoz` + de 0 a 3 capas de fondo + sonidos sugeridos (en fracción de la duración). Las escenas propias se guardan en `%APPDATA%\NaturalShot PRO\escenas.json`.

## Biblioteca generada

Todo con síntesis por capas, **determinista por semilla**. El mismo proyecto suena siempre igual, así que la vista previa es igual a la exportación. Nunca hay un loop audible.

- **Fondos continuos:**
  - Ciudad: rumor grave y autos lejanos esporádicos (sin pájaros: eso va en Mis sonidos).
  - Calle con tránsito: autos y motos que pasan cerca, con Doppler.
  - Lluvia (intensidad: llovizna a fuerte).
  - Agua o río.
  - Olas.
  - Viento, con ráfagas.
  - Oficina: aire acondicionado, zumbido eléctrico y un teclado lejano opcional.
  - Habitación ("aire" de la habitación).
  - Adentro de un auto: ruido de ruta.
  - Motor del colectivo, desde adentro.
  - Viento en el micrófono: golpes graves.
- **Sonidos sueltos** (de 2 a 15 s):
  - colectivo pasando, con motor diésel, Doppler y silbido del freno de aire;
  - auto pasando;
  - moto pasando;
  - frenada de colectivo (el "pssst" del aire);
  - bocina;
  - sirena lejos.

Lo que no se puede sintetizar de forma creíble (gente hablando, pájaros, perros) queda para "Mis sonidos". **No se incluyen grabaciones de terceros.**

## Cómo suena real (procesado de la voz)

Orden fijo, como pasa en la vida real:

1. **Bajarle lo de IA** (solo a la voz):
   - micro variaciones lentas de volumen, de ±1 a 2 dB, como si se moviera la cabeza;
   - suavizado de sibilantes demasiado perfectas (de-esser);
   - leve variación de brillo;
   - recorte de los extremos del espectro que un celular no capta.
   - Sin cambiar el tono ni el tiempo: eso suena raro.
2. **El lugar:** eco corto con una respuesta al impulso sintética según el lugar (oficina, habitación, auto o colectivo, calle o exterior), por convolución FFT.
3. **Voz y ambiente juntos**, antes del micrófono: el fondo y los sonidos sueltos se suman acá, con su volumen. Así pasan por el mismo micrófono y la misma compresión que la voz, y no suena "pegado".
4. **Micrófono del destino:**
   - **WhatsApp:** cerca de la boca, con efecto de proximidad (más graves), banda de unos 80 Hz a 7,5 kHz y algo de saturación suave.
   - **Video:** a un brazo de distancia, menos graves y más lugar, banda de unos 100 Hz a 12 kHz.
   - **Auriculares:** banda angosta de 16 kHz, unos 200 Hz a 7 kHz, con la reducción de ruido del Bluetooth que "bombea".
5. **Control automático de volumen del celular** (AGC): con un sonido fuerte (el colectivo), baja todo y la voz se tapa. "Que tape la voz" regula cuánto.
6. **Ruido propio del micrófono:** un piso de ruido muy bajo.
7. **Compresión del destino**, codificando y decodificando de verdad con PyAV:
   - WhatsApp: Opus mono a 16 kHz y unos 24 kbit/s;
   - Video: AAC de 128 kbit/s;
   - Auriculares: remuestreo a 16 kHz más Opus de banda ancha a unos 32 kbit/s, como mSBC.

"Cuánto" escala todo junto: 0 deja la voz igual y 100 es el máximo creíble. El volumen general y la normalización (`AjustesAudio`) van al final.

## Arquitectura

Todo se procesa adentro a **48 kHz, estéreo, float32**, en bloques `(n, 2)`. Una voz mono se duplica en los dos canales. WhatsApp exporta mono.

**Restricciones:**
- solo `numpy`, `opencv`, `PyAV` (códecs y filtros de FFmpeg) y PySide6: **no hay `scipy`** y no se instalan paquetes;
- filtros FIR por FFT (solapar y sumar), convolución por FFT para el eco y envolventes a tasa reducida (1 ms) para el AGC y las variaciones;
- nada de bucles de Python muestra por muestra.

| Unidad | Archivo | Qué hace | Depende de |
|---|---|---|---|
| A. Biblioteca generada | `motor/ambientes.py` | Fondos y sonidos generados, deterministas, con acceso aleatorio | numpy |
| B. Voz natural | `motor/voz_natural.py` | `AjustesVoz` y `CadenaVoz` (pasos 1, 2 y 4 a 7) | numpy, PyAV |
| C. Proyecto y mezcla | `motor/proyecto_audio.py` | Proyecto, escenas, Mis sonidos, mezclador en streaming y exportación | A, B, `motor/audio.py` |
| D. Interfaz | `ui/modo_audio.py` (+ `ventana.py`) | El modo Audio | C, `ui/forma_onda.py`, `ui/reproductor_audio.py` |
| E. Ida y vuelta | `motor/video.py`, `ui/editor_video.py` | Sonido externo en video | C, D |

### A. `motor/ambientes.py`

```python
FONDOS: dict[str, InfoAmbiente]      # id -> nombre, descripción, si tiene intensidad
SONIDOS: dict[str, InfoAmbiente]     # id -> nombre, descripción, duración típica

class GeneradorFondo:
    def __init__(self, tipo: str, intensidad: float = 0.5, semilla: int = 0, frecuencia: int = 48000): ...
    def leer(self, inicio: int, n: int) -> np.ndarray:   # (n, 2) float32, acceso aleatorio
        ...

def generar_sonido(tipo: str, semilla: int = 0, frecuencia: int = 48000) -> np.ndarray:  # (n, 2) float32, con caché
    ...
```

- **Acceso aleatorio exacto:** `leer(inicio, n)` da lo mismo que leer de corrido desde 0 y cortar. Se arma por trozos fijos con semilla `(semilla, índice)` y solape con fundido entre trozos. Los eventos internos (autos de la calle, gotas grandes, ráfagas) salen de un calendario pseudoaleatorio por ventana de tiempo, calculado de la semilla.
- **Nivel:** cada fondo sale calibrado a un nivel de referencia (por ejemplo, −30 dBFS RMS a intensidad 0,5) y cada sonido suelto con su pico cerca de −6 dBFS. El volumen lo pone C.
- **Velocidad:** cada fondo, al menos 20 veces el tiempo real; cada sonido suelto, en menos de 0,5 s.

### B. `motor/voz_natural.py`

```python
DESTINOS = ("ninguno", "whatsapp", "video", "auriculares")
LUGARES = ("ninguno", "habitacion", "oficina", "auto", "colectivo", "calle", "exterior")

@dataclass(frozen=True)
class AjustesVoz:
    destino: str = "ninguno"
    cuanto: float = 0.6        # 0..1 (Sutil 0.3 · Normal 0.6 · Fuerte 0.9)
    anti_ia: float = 0.0       # 0..1
    lugar: str = "ninguno"
    eco: float = 0.5           # 0..1, cuánto lugar
    ruido_propio: float = 0.5  # 0..1
    compresion: bool = True    # códec del destino
    tapa: float = 0.5          # 0..1, AGC
    semilla: int = 0
    def sin_cambios(self) -> bool: ...

class CadenaVoz:
    def __init__(self, ajustes: AjustesVoz, frecuencia: int = 48000): ...
    def procesar(self, voz: np.ndarray, ambiente: np.ndarray, inicio: int) -> np.ndarray:  # (n, 2) float32
        ...
    def reiniciar(self, inicio: int) -> None: ...   # al saltar
    latencia: int    # muestras de retardo fijo (el códec); C las compensa
```

- **`voz`:** la voz ya editada (tramos, silencios). **`ambiente`:** la suma del fondo y los sonidos, ya con volumen. **`inicio`:** la posición en muestras del resultado. Las variaciones "anti IA" dependen del tiempo absoluto, así que un salto da lo mismo.
- Con `AjustesVoz()` (ninguno, sin anti IA), sale `voz + ambiente` sin tocar.
- **Bloques:** procesar de corrido en bloques de cualquier tamaño da lo mismo que en uno solo, salvo el códec (diferencia por debajo de −60 dB).
- **Después de un salto:** C hace una "pre-lectura" de 0,5 s para que el eco y los filtros se asienten.
- **Velocidad:** al menos 8 veces el tiempo real con todo prendido, en bloques de 50 ms.

### C. `motor/proyecto_audio.py`

```python
@dataclass(frozen=True)
class FondoProyecto:
    origen: str            # "generado" | "archivo"
    clave: str             # id de FONDOS o nombre del archivo en Mis sonidos
    volumen: float = 0.5   # 0..1 (lineal sobre el nivel de referencia, con curva en dB)
    intensidad: float = 0.5
    semilla: int = 0

@dataclass(frozen=True)
class SonidoSuelto:
    origen: str            # "generado" | "archivo"
    clave: str
    ancla: float           # segundos del tiempo ORIGINAL de la voz
    volumen: float = 0.7
    semilla: int = 0

@dataclass(frozen=True)
class ProyectoAudio:
    ruta: str                          # la voz
    tramos: tuple                      # tramos conservados (como EdicionVideo)
    sonido: AjustesAudio               # volumen, normalizar, fundidos, silencios
    voz: AjustesVoz
    fondos: tuple[FondoProyecto, ...]   # de 0 a 3 capas
    sonidos: tuple[SonidoSuelto, ...]
    video_origen: Optional[str] = None # si vino de "Editar el sonido en el modo Audio"
```

- **Anclas:** los sonidos sueltos se anclan a un momento de la voz, en tiempo original, así que siguen a las palabras al cortar. Si el ancla cae en un tramo borrado, el sonido arranca al principio del siguiente tramo conservado. Suenan enteros: los cortes no los recortan.
- **Fondos:** cada capa cubre todo el resultado, con fundidos de 0,3 s al principio y al final. Un archivo de "Mis sonidos" usado de fondo se repite con un fundido cruzado de 2 s.
- **`MezcladorAudio(proyecto, desde=0.0, formato="s16")`** tiene la **misma interfaz que `LectorPCM`**: `leer`, `leer_array`, `bytes_por_muestra`, `ir_a_resultado`, `posicion_resultado`, `duracion_resultado`, `terminado`, `cambiar_proyecto` y `cerrar`. Así `ui/reproductor_audio.py` reproduce cualquiera de los dos. Adentro:
  1. voz (`LectorPCM` con tramos y silencios, en f32);
  2. ambiente (fondo + sonidos);
  3. `CadenaVoz`;
  4. volumen, normalizar y fundidos de `AjustesAudio`, sobre el resultado final;
  5. formato de salida.
- **`exportar_proyecto(proyecto, ruta_salida, formato=None, progreso=None, cancelado=None)`**:
  - formatos: `whatsapp` (`.ogg`, Opus mono a 48 kHz, unos 24 kbit/s), `m4a`, `mp3` y `wav`;
  - temporal y renombrado al final, como `exportar_audio`;
  - la exportación usa el mismo mezclador que la vista previa;
  - con destino WhatsApp y formato WhatsApp, la etapa 7 de la cadena se saltea al exportar, porque el archivo ya sale en Opus y no se comprime dos veces.
- **Escenas:** `ESCENAS` y `escenas_propias()`, `guardar_escena(nombre, …)`, `borrar_escena(nombre)` y `aplicar_escena(proyecto, escena)`. Los sonidos sugeridos van en fracción de la duración resultante.
- **Mis sonidos:** `carpeta_sonidos()`, `mis_sonidos()`, `agregar_a_mis_sonidos(ruta)` (copia, con nombre único), `renombrar_sonido` y `borrar_sonido`. Se leen con PyAV, a 48 kHz estéreo, con caché.
- **Sesión:** `ProyectoAudio`, `FondoProyecto`, `SonidoSuelto`, `AjustesVoz` y `AjustesAudio` van en `CLASES` de `sesion.py`. La sesión suma el proyecto de audio (formato nuevo compatible: si falta, no hay proyecto).

### D. Interfaz (`ui/modo_audio.py`)

- **Reutiliza:**
  - `ui/forma_onda.py` y `ui/reproductor_audio.py`, de la integración del sonido en Video;
  - la línea de tiempo y la lógica de cortes del editor de video, donde se pueda.
- **Ventana:**
  - el selector suma "Audio" (`AUDIO = "audio"`, junto a `FACIL, EDITOR, VIDEO`);
  - el editor de audio se arma la primera vez que se entra, como el de video;
  - el ruteo de archivos suma los audios (`es_audio`).
- **Galerías:** las escenas y los fondos, en tarjetas con ícono y nombre. Al pasar el mouse por un fondo hay "escuchar 3 s".
- Hilos con `Tarea` y `QThreadPool`. **Sin filtros globales de eventos.**

### E. Ida y vuelta con Video

- **Motor:** en `motor/video.py`, `exportar_video(..., audio_externo: Optional[AudioExterno] = None)`, donde `AudioExterno(ruta, alineado="original" | "resultado")`. Se lee con `LectorPCM` (sin tramos si es "resultado") y se le aplican los mismos `AjustesAudio` del video.
- **Interfaz:** los botones de Video, la franja en Audio y la vista previa del video con el sonido externo.

## Errores

- **Archivo sin audio o ilegible:** aviso claro ("Este archivo no tiene sonido" o "No se pudo abrir") y el modo queda como estaba.
- **Archivo de Mis sonidos borrado por fuera:** se ve como "falta" y la mezcla lo saltea.
- **Sin dispositivo de audio:** todo anda sin sonido, como en Video.
- **Exportación cancelada o con error:** no queda ningún archivo a medias.
- **Sesión con un audio que ya no está:** el aviso flotante de siempre.

## Pruebas

- **A:**
  - determinismo y acceso aleatorio (bloques sueltos = de corrido);
  - niveles calibrados;
  - sin NaN ni saturación;
  - espectro esperable por tipo (por ejemplo, lluvia con energía en agudos y motor con energía en graves);
  - en el colectivo que pasa, la envolvente sube y baja y la frecuencia dominante baja (Doppler);
  - velocidad.
- **B:**
  - `AjustesVoz()` no toca;
  - bloques = todo junto;
  - la banda de cada destino, medida con FFT sobre ruido blanco;
  - el AGC baja la voz cuando entra un ruido fuerte (y más con más `tapa`);
  - el eco alarga la cola;
  - anti IA: variación de nivel dentro de lo pedido y sin cambio de tono (pico del espectro igual con un tono);
  - el códec redondea;
  - velocidad.
- **C:**
  - anclas al cortar;
  - mezclador = exportación (WAV, misma señal);
  - saltar y seguir;
  - cada formato;
  - cancelar;
  - escenas propias y Mis sonidos en un APPDATA temporal;
  - pickle y sesión;
  - archivos de solo audio (MP3, M4A, OGG y WAV, generados con PyAV).
- **D y E:** pruebas offscreen de la ventana y capturas revisadas a 1366 y 1600 px.
- **Muestrario para escuchar:** `herramientas/muestrario_audio.py` genera en `Muestras de audio\` (en la carpeta del proyecto):
  - cada fondo (20 s);
  - cada sonido suelto;
  - cada escena aplicada a una voz de prueba.
  - **Voz de prueba:** se genera con la voz en español de Windows (`System.Speech`, offline). Si no hay voz en español, se usa cualquier voz instalada y se avisa. Nunca se usan archivos personales del dueño.
  - Es para que el dueño escuche y diga qué suena creíble.

## Fuera de alcance (por ahora)

- grabaciones reales incluidas;
- llamada telefónica;
- cambio de tono o de velocidad de la voz;
- varias voces o pistas de voz;
- reducción de ruido de grabaciones sucias.
