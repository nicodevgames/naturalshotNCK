# Modo Audio: plan de implementación

> **Para los subagentes:** se ejecuta tarea por tarea con superpowers:subagent-driven-development. Los pasos usan casillas (`- [ ]`). La carpeta **no es un repositorio git**: no hay commits. Antes de editar un archivo existente, guardá una copia en el scratchpad que te indiquen.

**Objetivo:** un modo "Audio" en NaturalShot PRO que haga que una voz limpia o generada con IA suene grabada con un celular en un lugar real (fondo, sonidos sueltos y cadena de micrófono, AGC y códec), con escenas, "Mis sonidos" e ida y vuelta con Video.

**Arquitectura:** cinco unidades:
- A. `motor/ambientes.py`: síntesis determinista con acceso aleatorio.
- B. `motor/voz_natural.py`: cadena de voz en streaming.
- C. `motor/proyecto_audio.py`: proyecto, mezclador con la interfaz de `LectorPCM`, exportación, escenas, Mis sonidos y sesión.
- D. `ui/modo_audio.py`: la interfaz.
- E. Sonido externo en Video.

Todo se procesa a 48 kHz, estéreo, float32. El diseño completo está en `docs/superpowers/specs/2026-10-13-modo-audio-design.md`: **leelo antes de empezar cualquier tarea**.

**Stack:**
- Python 3 (`.venv\Scripts\python`), numpy 2.5, PyAV 19.0.1 (con libopus y libmp3lame, sin libvorbis), opencv-headless y PySide6 6.12.
- **No hay scipy y no se instalan paquetes.**
- Pruebas con `unittest`. La suite completa se corre con:

```
$env:QT_QPA_PLATFORM="offscreen"; .venv\Scripts\python -m unittest discover -s tests
```

**Reglas comunes a todas las tareas:**
- Nombres, docstrings y comentarios en español rioplatense, con la densidad de `motor/audio.py`. La interfaz, con "vos" ("tocá", "marcá").
- DSP sin bucles de Python muestra por muestra:
  - filtros FIR por FFT (solapar y sumar);
  - convolución FFT para el eco;
  - envolventes a 1 ms (1 valor cada 48 muestras) con bucles de Python solo a esa tasa o con `np.cumsum` o `lfilter` casero vectorizado por trozos;
  - códecs con PyAV.
- **Privacidad:** fuera de la carpeta del proyecto y del scratchpad no leas ni listes nada. Los medios de prueba se generan.
- Nada de internet, git ni GitHub.
- Sin filtros globales de eventos en la interfaz (ver `_FiltroGlobal` en `ui/ventana.py`).

---

## Mapa de archivos

| Archivo | Tarea | Responsabilidad |
|---|---|---|
| `celular_natural/motor/ambientes.py` (nuevo) | A | Catálogo `FONDOS` y `SONIDOS`, `GeneradorFondo`, `generar_sonido` |
| `tests/test_ambientes.py` (nuevo) | A | Pruebas de A |
| `celular_natural/motor/voz_natural.py` (nuevo) | B | `AjustesVoz`, `CadenaVoz`, constantes `DESTINOS` y `LUGARES` |
| `tests/test_voz_natural.py` (nuevo) | B | Pruebas de B |
| `celular_natural/motor/proyecto_audio.py` (nuevo) | C | `FondoProyecto`, `SonidoSuelto`, `ProyectoAudio`, `MezcladorAudio`, `exportar_proyecto`, escenas, Mis sonidos |
| `celular_natural/sesion.py` | C | Suma las clases nuevas a `CLASES` y el proyecto de audio a la sesión |
| `tests/test_proyecto_audio.py` (nuevo) | C | Pruebas de C |
| `herramientas/muestrario_audio.py` (nuevo) | C | Genera `Muestras de audio\` para escuchar |
| `celular_natural/ui/modo_audio.py` (nuevo) | D | `EditorAudio`: el modo Audio entero |
| `celular_natural/ui/ventana.py`, `ui/modo_video.py`, `ui/modo_facil.py` | D | Selector con Audio, ruteo de audios, atajo y chip de exportación |
| `tests/test_modo_audio.py` (nuevo) | D | Pruebas de interfaz |
| `celular_natural/motor/video.py`, `ui/editor_video.py` | E | `AudioExterno` y los botones de ida y vuelta |
| `tests/test_ida_y_vuelta.py` (nuevo) | E | Pruebas de E |
| `NaturalShot.spec`, `README.md`, `ESTADO_DEL_PROYECTO.md`, `VIDEO.md`, `AUDIO.md` (nuevo) | F | Empaquetado y documentación |

A y B no dependen entre sí y van **en paralelo**. C usa A y B. D usa C más `ui/forma_onda.py` y `ui/reproductor_audio.py`, que salen de la integración del sonido en Video (otra tarea, ya en curso); **D no empieza hasta que esa termine**. E va después de D.

---

## Tarea A: biblioteca generada (`motor/ambientes.py`)

**Archivos:** crear `celular_natural/motor/ambientes.py` y `tests/test_ambientes.py`.

**Contrato:**

```python
@dataclass(frozen=True)
class InfoAmbiente:
    clave: str
    nombre: str          # para la interfaz, en español: "Calle con tránsito"
    descripcion: str     # una línea: "Autos y motos que pasan cerca"
    icono: str           # nombre de un ícono Lucide sugerido: "car", "cloud-rain", "waves"...
    intensidad: bool     # si el parámetro intensidad cambia algo
    duracion: float = 0.0  # solo sonidos sueltos: duración típica en segundos

FONDOS: dict[str, InfoAmbiente]   # claves: "ciudad", "calle", "lluvia", "agua", "olas", "viento", "oficina",
                                  # "habitacion", "auto", "colectivo", "viento_mic"
SONIDOS: dict[str, InfoAmbiente]  # claves: "colectivo_pasa", "auto_pasa", "moto_pasa", "frenada_colectivo",
                                  # "bocina", "sirena_lejos"
FRECUENCIA = 48000
NIVEL_FONDO_DBFS = -30.0   # RMS de un fondo a intensidad 0.5
PICO_SONIDO_DBFS = -6.0    # pico de un sonido suelto

class GeneradorFondo:
    def __init__(self, tipo: str, intensidad: float = 0.5, semilla: int = 0, frecuencia: int = FRECUENCIA): ...
    def leer(self, inicio: int, n: int) -> np.ndarray: ...   # (n, 2) float32, acceso aleatorio exacto

def generar_sonido(tipo: str, semilla: int = 0, frecuencia: int = FRECUENCIA) -> np.ndarray: ...  # (n, 2) float32, caché LRU
```

**Técnica sugerida:**
- **Trozos fijos de 1 s:** cada trozo `k` se genera con un `np.random.Generator` sembrado con `(semilla, hash(tipo), k)` y con 0,25 s de pre-lectura (el final del trozo `k-1`, regenerado con su propia semilla) para que los filtros FIR se asienten. Entre trozos va un fundido cruzado igual-potencia de 50 ms. Así `leer(inicio, n)` es exacto en cualquier punto.
- **Ruidos de color:** ruido blanco filtrado por FFT con una curva en frecuencia: rosa, marrón o una banda para lluvia y agua.
- **Eventos dentro de los fondos** (autos de la calle, gotas grandes, ráfagas, olas): un calendario por ventana de 4 s con semilla `(semilla, ventana)`, del que salen tiempos y parámetros. Cada evento se sintetiza entero (con caché) y se suma donde cae; un evento que empieza en la ventana anterior también suena.
- **Pasadas de vehículos** (colectivo, auto y moto):
  - motor como suma de armónicos de una fundamental (colectivo diésel unos 30-45 Hz con aspereza; moto unos 80-120 Hz), más ruido de neumáticos (rosa con pasabanda de 300-3000 Hz);
  - envolvente de distancia `1/sqrt(d² + x(t)²)`;
  - Doppler con `f · c/(c ∓ v)`, hecho con remuestreo por interpolación de fase acumulada;
  - un poco de paneo izquierda→derecha y un pasabajos que se abre cuando el vehículo está cerca.
- **Frenada de colectivo:** ruido con pasabanda de 2-6 kHz, ataque corto y caída de 1,5 s.
- **Bocina:** dos tonos de unos 400 y 500 Hz, ricos en armónicos (onda cuadrada suavizada).
- **Sirena:** barrido de 600 a 1200 Hz, lejos (pasabajos y poco nivel).

- [ ] **Paso 1: escribir las pruebas (que fallen)** en `tests/test_ambientes.py`:

```python
import time, unittest
import numpy as np
from celular_natural.motor import ambientes as am

def rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(np.square(x, dtype=np.float64))) + 1e-12)

def energia_banda(x, lo, hi, sr=48000):
    m = x.mean(axis=1)
    e = np.abs(np.fft.rfft(m)) ** 2
    f = np.fft.rfftfreq(len(m), 1 / sr)
    return e[(f >= lo) & (f < hi)].sum() / e.sum()

class PruebasFondos(unittest.TestCase):
    def test_catalogo(self):
        for clave in ("ciudad", "calle", "lluvia", "agua", "olas", "viento", "oficina", "habitacion",
                      "auto", "colectivo", "viento_mic"):
            self.assertIn(clave, am.FONDOS)
            self.assertTrue(am.FONDOS[clave].nombre)

    def test_acceso_aleatorio_exacto(self):
        for clave in am.FONDOS:
            g = am.GeneradorFondo(clave, 0.5, semilla=7)
            todo = g.leer(0, 48000 * 6)
            for inicio, n in ((0, 1000), (47_999, 2), (48000 * 2 + 123, 30_000), (48000 * 5, 48000)):
                np.testing.assert_allclose(am.GeneradorFondo(clave, 0.5, semilla=7).leer(inicio, n),
                                           todo[inicio:inicio + n], atol=1e-6, err_msg=clave)

    def test_forma_y_tipo(self):
        x = am.GeneradorFondo("lluvia").leer(0, 4800)
        self.assertEqual(x.shape, (4800, 2))
        self.assertEqual(x.dtype, np.float32)

    def test_semillas_distintas_dan_distinto(self):
        a = am.GeneradorFondo("calle", semilla=1).leer(0, 48000)
        b = am.GeneradorFondo("calle", semilla=2).leer(0, 48000)
        self.assertGreater(np.abs(a - b).mean(), 1e-4)

    def test_nivel_calibrado_y_sin_saturar(self):
        for clave in am.FONDOS:
            x = am.GeneradorFondo(clave, 0.5, semilla=3).leer(0, 48000 * 10)
            self.assertTrue(np.isfinite(x).all(), clave)
            self.assertLess(np.abs(x).max(), 0.99, clave)
            self.assertAlmostEqual(rms_db(x), am.NIVEL_FONDO_DBFS, delta=4.0, msg=clave)

    def test_intensidad_cambia_el_nivel(self):
        for clave, info in am.FONDOS.items():
            if info.intensidad:
                poco = rms_db(am.GeneradorFondo(clave, 0.1).leer(0, 48000 * 8))
                mucho = rms_db(am.GeneradorFondo(clave, 0.9).leer(0, 48000 * 8))
                self.assertGreater(mucho, poco + 3, clave)

    def test_espectros_esperables(self):
        lluvia = am.GeneradorFondo("lluvia", 0.6).leer(0, 48000 * 4)
        colectivo = am.GeneradorFondo("colectivo", 0.6).leer(0, 48000 * 4)
        self.assertGreater(energia_banda(lluvia, 2000, 12000), 0.3)
        self.assertGreater(energia_banda(colectivo, 20, 300), 0.4)

    def test_sin_loop_audible(self):
        # Dos ventanas de 2 s separadas 30 s no se parecen (correlación baja).
        x = am.GeneradorFondo("agua", semilla=5).leer(0, 48000 * 34)[:, 0]
        a, b = x[:96000], x[48000 * 30:48000 * 32]
        c = np.corrcoef(a, b)[0, 1]
        self.assertLess(abs(c), 0.2)

    def test_velocidad(self):
        for clave in am.FONDOS:
            g = am.GeneradorFondo(clave, 0.5)
            t = time.perf_counter()
            g.leer(48000 * 3, 48000 * 10)
            self.assertLess(time.perf_counter() - t, 0.5, clave)   # >= 20 veces el tiempo real

class PruebasSonidos(unittest.TestCase):
    def test_catalogo_y_pico(self):
        for clave in ("colectivo_pasa", "auto_pasa", "moto_pasa", "frenada_colectivo", "bocina", "sirena_lejos"):
            x = am.generar_sonido(clave, semilla=1)
            self.assertEqual(x.ndim, 2)
            self.assertEqual(x.shape[1], 2)
            pico = 20 * np.log10(np.abs(x).max())
            self.assertAlmostEqual(pico, am.PICO_SONIDO_DBFS, delta=1.0, msg=clave)
            self.assertAlmostEqual(len(x) / 48000, am.SONIDOS[clave].duracion, delta=am.SONIDOS[clave].duracion * 0.5)

    def test_determinista(self):
        np.testing.assert_array_equal(am.generar_sonido("auto_pasa", 4), am.generar_sonido("auto_pasa", 4))

    def test_colectivo_sube_y_baja_con_doppler(self):
        x = am.generar_sonido("colectivo_pasa", semilla=2).mean(axis=1)
        env = np.sqrt(np.convolve(x ** 2, np.ones(4800) / 4800, mode="same"))
        i = int(np.argmax(env))
        self.assertTrue(0.2 * len(x) < i < 0.8 * len(x))
        self.assertGreater(env[i], 4 * env[2400])
        self.assertGreater(env[i], 4 * env[-2400])
        # Doppler: el centroide espectral antes del pico es mayor que después.
        def centroide(s):
            e = np.abs(np.fft.rfft(s * np.hanning(len(s))))
            f = np.fft.rfftfreq(len(s), 1 / 48000)
            sel = f < 1500
            return (e[sel] * f[sel]).sum() / e[sel].sum()
        antes = centroide(x[max(0, i - 48000):i - 12000])
        despues = centroide(x[i + 12000:i + 48000])
        self.assertGreater(antes, despues * 1.05)

    def test_velocidad(self):
        am.generar_sonido.cache_clear() if hasattr(am.generar_sonido, "cache_clear") else None
        for clave in am.SONIDOS:
            t = time.perf_counter()
            am.generar_sonido(clave, semilla=99)
            self.assertLess(time.perf_counter() - t, 0.5, clave)
```

- [ ] **Paso 2:** correr `.venv\Scripts\python -m unittest tests.test_ambientes -v`. Resultado esperado: falla con `ModuleNotFoundError: celular_natural.motor.ambientes`.
- [ ] **Paso 3:** implementar `motor/ambientes.py` siguiendo el contrato y la técnica sugerida.
- [ ] **Paso 4:** correr las pruebas de A. Resultado esperado: OK. Si un umbral de espectro o de nivel resulta irreal para un sonido bien hecho, ajustalo **con justificación escrita en la prueba**. No ajustes el sonido para engañar a la prueba.
- [ ] **Paso 5:** muestras para escuchar: escribí en el scratchpad cada fondo (20 s) y cada sonido como WAV de 16 bits (con PyAV o el módulo `wave`). Revisá sus espectrogramas: generá PNG con opencv o PIL y miralos con la herramienta de leer imágenes. Corregí lo que se vea mal: clics en las uniones de trozos, tonos puros sospechosos, cortes secos.
- [ ] **Paso 6:** correr la suite completa. Resultado esperado: OK.

---

## Tarea B: voz natural (`motor/voz_natural.py`)

**Archivos:** crear `celular_natural/motor/voz_natural.py` y `tests/test_voz_natural.py`.

**Contrato:** exacto como en el diseño, sección "B".

```python
DESTINOS = ("ninguno", "whatsapp", "video", "auriculares")
LUGARES = ("ninguno", "habitacion", "oficina", "auto", "colectivo", "calle", "exterior")

@dataclass(frozen=True)
class AjustesVoz:
    destino: str = "ninguno"
    cuanto: float = 0.6
    anti_ia: float = 0.0
    lugar: str = "ninguno"
    eco: float = 0.5
    ruido_propio: float = 0.5
    compresion: bool = True
    tapa: float = 0.5
    semilla: int = 0
    def sin_cambios(self) -> bool: ...          # destino "ninguno", lugar "ninguno" y anti_ia 0
    def con(self, **cambios) -> "AjustesVoz": ...  # valores fuera de rango se acomodan, como AjustesAudio

class CadenaVoz:
    latencia: int
    def __init__(self, ajustes: AjustesVoz, frecuencia: int = 48000, codec: bool = True): ...
    def procesar(self, voz: np.ndarray, ambiente: np.ndarray, inicio: int) -> np.ndarray: ...
    def reiniciar(self, inicio: int) -> None: ...
```

- `codec=False` deja la cadena sin la etapa 7. Lo usa C al exportar en formato WhatsApp con destino WhatsApp, y las pruebas.
- **`latencia`:** las muestras de retardo fijo que agrega la cadena (sobre todo el códec). La salida de `procesar` ya viene **compensada**: la muestra `i` de la salida corresponde a la `i` de la entrada. Para eso la cadena guarda internamente lo que hace falta; al terminar, C llama a `procesar` con ceros para vaciar. Documentá el método exacto, por ejemplo `vaciar() -> np.ndarray`.

**Etapas:** las del diseño, con estos detalles:
1. **Anti IA:**
   - ganancia lenta de ±(1,5 dB × anti_ia), un ruido suave de unos 0,3 Hz que depende del tiempo absoluto: semilla `(semilla, segundo)` e interpolación;
   - de-esser: compresión de la banda de 5-9 kHz según su envolvente;
   - variación lenta de brillo: un shelf de agudos que se mueve ±1 dB.
2. **Lugar:** una respuesta al impulso sintética por lugar: reflexiones tempranas con retardos y ganancias por lugar, más una cola de ruido con decaimiento exponencial (RT60: habitación 0,35 s, oficina 0,5 s, auto 0,12 s, colectivo 0,25 s, calle 0,8 s con muy poco nivel, exterior casi nada). Convolución FFT por bloques (solapar y sumar). El nivel húmedo es `eco × cuanto`.
3. **Suma de voz y ambiente:** se suma acá.
4. **Micrófono:** FIR por destino (WhatsApp con proximidad +3 dB a 150 Hz, banda de 80 Hz a 7,5 kHz; video de 100 Hz a 12 kHz con −2 dB en graves; auriculares de 200 Hz a 7 kHz con un pico a 2,5 kHz) más una saturación suave `tanh` con leve sobremuestreo. Todo escalado por `cuanto`.
5. **AGC:** envolvente RMS a 1 ms del total (voz y ambiente); objetivo de −20 dBFS, ataque de 30 ms y liberación de 400 ms, rango −15 dB / +6 dB. La cantidad de reducción se escala con `tapa`. En auriculares, además, una compuerta de ruido que "bombea" en las pausas.
6. **Ruido propio:** rosa, a −62 dBFS × `ruido_propio` × `cuanto`, con la misma semilla por tiempo absoluto.
7. **Códec** (si `compresion` y `codec=True`): codificar y decodificar con PyAV en streaming.
   - WhatsApp: libopus mono a 16 kHz y 24 kbit/s;
   - video: AAC a 128 kbit/s;
   - auriculares: libopus a 16 kHz y 32 kbit/s.
   - Remuestrear con `av.AudioResampler`.

- [ ] **Paso 1: escribir las pruebas (que fallen)** en `tests/test_voz_natural.py`:

```python
import time, unittest
import numpy as np
from celular_natural.motor.voz_natural import AjustesVoz, CadenaVoz, DESTINOS, LUGARES

SR = 48000

def tono(f, s, nivel=0.3):
    t = np.arange(int(SR * s)) / SR
    m = (nivel * np.sin(2 * np.pi * f * t)).astype(np.float32)
    return np.stack([m, m], axis=1)

def ruido(s, nivel=0.1, semilla=0):
    r = np.random.default_rng(semilla).standard_normal(int(SR * s)).astype(np.float32) * nivel
    return np.stack([r, r], axis=1)

def procesar_por_bloques(cad, voz, amb, bloque):
    partes = [cad.procesar(voz[i:i + bloque], amb[i:i + bloque], i) for i in range(0, len(voz), bloque)]
    return np.concatenate(partes)

def banda(x, lo, hi):
    e = np.abs(np.fft.rfft(x[:, 0])) ** 2
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return e[(f >= lo) & (f < hi)].sum() / e.sum()

class PruebasVozNatural(unittest.TestCase):
    def test_por_defecto_no_toca(self):
        voz, amb = ruido(2, 0.1, 1), ruido(2, 0.01, 2)
        sal = CadenaVoz(AjustesVoz()).procesar(voz, amb, 0)
        np.testing.assert_allclose(sal, voz + amb, atol=1e-6)

    def test_ajustes_se_acomodan(self):
        a = AjustesVoz().con(cuanto=7, anti_ia=-1, destino="whatsapp")
        self.assertEqual((a.cuanto, a.anti_ia), (1.0, 0.0))
        with self.assertRaises(ValueError):
            AjustesVoz(destino="radio")

    def test_bloques_igual_que_todo(self):
        aj = AjustesVoz(destino="video", lugar="oficina", anti_ia=0.7, cuanto=0.8)
        voz, amb = ruido(3, 0.1, 3), ruido(3, 0.02, 4)
        a = procesar_por_bloques(CadenaVoz(aj, codec=False), voz, amb, len(voz))
        b = procesar_por_bloques(CadenaVoz(aj, codec=False), voz, amb, 2400)
        np.testing.assert_allclose(a, b, atol=1e-5)

    def test_banda_de_cada_destino(self):
        voz, amb = ruido(4, 0.1, 5), np.zeros((SR * 4, 2), np.float32)
        wa = CadenaVoz(AjustesVoz(destino="whatsapp", cuanto=1.0), codec=False).procesar(voz, amb, 0)
        au = CadenaVoz(AjustesVoz(destino="auriculares", cuanto=1.0), codec=False).procesar(voz, amb, 0)
        vi = CadenaVoz(AjustesVoz(destino="video", cuanto=1.0), codec=False).procesar(voz, amb, 0)
        self.assertLess(banda(wa, 9000, 24000), 0.02)
        self.assertLess(banda(au, 8000, 24000), 0.01)
        self.assertLess(banda(au, 0, 150), 0.02)
        self.assertGreater(banda(vi, 9000, 13000), banda(wa, 9000, 13000))

    def test_agc_tapa_la_voz(self):
        voz = tono(300, 6, 0.2)
        amb = np.zeros_like(voz)
        amb[SR * 2:SR * 4] = ruido(2, 0.5, 6)   # pasa el colectivo
        def nivel_voz(tapa):
            s = CadenaVoz(AjustesVoz(destino="whatsapp", tapa=tapa, cuanto=1.0), codec=False).procesar(voz, amb, 0)
            # nivel del tono (300 Hz) en el medio del ruido, por correlación con la voz original
            seg = slice(SR * 3, SR * 3 + SR // 2)
            ref = voz[seg, 0]
            return abs(np.dot(s[seg, 0], ref) / np.dot(ref, ref))
        self.assertLess(nivel_voz(1.0), nivel_voz(0.0) * 0.7)

    def test_eco_alarga_la_cola(self):
        voz = np.zeros((SR * 2, 2), np.float32)
        voz[1000:1100] = 0.5
        amb = np.zeros_like(voz)
        seco = CadenaVoz(AjustesVoz(lugar="ninguno", destino="video"), codec=False).procesar(voz, amb, 0)
        mojado = CadenaVoz(AjustesVoz(lugar="habitacion", destino="video", eco=1.0, cuanto=1.0), codec=False).procesar(voz, amb, 0)
        cola = slice(1100 + int(0.05 * SR), 1100 + int(0.3 * SR))
        self.assertGreater(np.abs(mojado[cola]).mean(), 5 * np.abs(seco[cola]).mean() + 1e-6)

    def test_anti_ia_no_cambia_el_tono(self):
        voz = tono(220, 3)
        s = CadenaVoz(AjustesVoz(anti_ia=1.0), codec=False).procesar(voz, np.zeros_like(voz), 0)
        f = np.fft.rfftfreq(len(s), 1 / SR)
        self.assertAlmostEqual(f[np.argmax(np.abs(np.fft.rfft(s[:, 0])))], 220, delta=1.0)
        env = np.sqrt(np.convolve(s[:, 0] ** 2, np.ones(4800) / 4800, mode="valid"))
        variacion = 20 * np.log10(env.max() / env.min())
        self.assertTrue(0.5 < variacion < 4.5, variacion)

    def test_salto_es_determinista(self):
        aj = AjustesVoz(destino="whatsapp", anti_ia=0.8, lugar="calle")
        voz, amb = ruido(4, 0.1, 7), ruido(4, 0.02, 8)
        todo = CadenaVoz(aj, codec=False).procesar(voz, amb, 0)
        cad = CadenaVoz(aj, codec=False)
        cad.reiniciar(SR * 2 - SR // 2)   # pre-lectura de 0,5 s
        cad.procesar(voz[SR * 2 - SR // 2:SR * 2], amb[SR * 2 - SR // 2:SR * 2], SR * 2 - SR // 2)
        parte = cad.procesar(voz[SR * 2:SR * 3], amb[SR * 2:SR * 3], SR * 2)
        np.testing.assert_allclose(parte, todo[SR * 2:SR * 3], atol=2e-3)

    def test_codec_redondea_y_compensa_latencia(self):
        aj = AjustesVoz(destino="whatsapp", cuanto=1.0)
        voz, amb = tono(440, 3), np.zeros((SR * 3, 2), np.float32)
        con = procesar_por_bloques(CadenaVoz(aj, codec=True), voz, amb, 2400)
        sin = procesar_por_bloques(CadenaVoz(aj, codec=False), voz, amb, 2400)
        # Alineados (latencia compensada): alta correlación, pero no idénticos.
        c = np.corrcoef(con[SR // 2:-SR // 2, 0], sin[SR // 2:-SR // 2, 0])[0, 1]
        self.assertGreater(c, 0.9)
        self.assertGreater(np.abs(con - sin).max(), 1e-3)

    def test_velocidad(self):
        aj = AjustesVoz(destino="whatsapp", lugar="calle", anti_ia=1.0, cuanto=1.0)
        voz, amb = ruido(10, 0.1, 9), ruido(10, 0.02, 10)
        cad = CadenaVoz(aj)
        t = time.perf_counter()
        procesar_por_bloques(cad, voz, amb, 2400)
        self.assertLess(time.perf_counter() - t, 10 / 8)   # >= 8 veces el tiempo real
```

- [ ] **Paso 2:** correr `.venv\Scripts\python -m unittest tests.test_voz_natural -v`. Resultado esperado: falla con `ModuleNotFoundError`.
- [ ] **Paso 3:** implementar la cadena, etapa por etapa, corriendo las pruebas en cada una.
- [ ] **Paso 4:** pruebas de B en OK. La misma regla que en A para ajustar umbrales.
- [ ] **Paso 5:** muestras en el scratchpad. Generá una voz de prueba con la voz de Windows: PowerShell `Add-Type -AssemblyName System.Speech`, `SpeechSynthesizer.SelectVoiceByHints` con cultura `es-*`, si hay, y `SetOutputToWaveFile`. Pasala por cada destino y lugar y guardá WAV. Mirá los espectrogramas.
- [ ] **Paso 6:** suite completa en OK.

---

## Tarea C: proyecto, mezcla y exportación (`motor/proyecto_audio.py`)

**Archivos:**
- crear `celular_natural/motor/proyecto_audio.py`, `tests/test_proyecto_audio.py` y `herramientas/muestrario_audio.py`;
- modificar `celular_natural/sesion.py`.

**Contrato:** el del diseño, sección "C", con `fondos: tuple[FondoProyecto, ...]` de 0 a 3 capas. Además:

```python
def abrir_proyecto(ruta: str) -> ProyectoAudio: ...   # valida que tenga audio (ValueError si no) y arma tramos = todo
def duracion_resultado(p: ProyectoAudio) -> float: ...
def ancla_en_resultado(p: ProyectoAudio, ancla: float) -> float: ...
FORMATOS_PROYECTO = ("whatsapp", "m4a", "mp3", "wav")

@dataclass(frozen=True)
class Escena:
    clave: str
    nombre: str
    descripcion: str
    voz: AjustesVoz
    fondos: tuple[FondoProyecto, ...]
    sonidos: tuple[tuple[str, float, float], ...]   # (clave de SONIDOS, fracción de la duración, volumen)
    propia: bool = False

ESCENAS: dict[str, Escena]   # las 10 de la tabla del diseño
def escenas_propias() -> dict[str, Escena]: ...
def guardar_escena(nombre: str, p: ProyectoAudio) -> Escena: ...
def borrar_escena(nombre: str) -> None: ...
def aplicar_escena(p: ProyectoAudio, e: Escena) -> ProyectoAudio: ...
def carpeta_sonidos() -> Path: ...
def mis_sonidos() -> list[Path]: ...
def agregar_a_mis_sonidos(ruta: str) -> Path: ...
def renombrar_sonido(nombre: str, nuevo: str) -> Path: ...
def borrar_sonido(nombre: str) -> None: ...
```

- **Mezclador:**
  - `MezcladorAudio` imita a `LectorPCM` (mirá `motor/audio.py`): `leer(n) -> bytes`, `leer_array(n)`, `bytes_por_muestra`, `ir_a_resultado(t)`, `posicion_resultado`, `duracion_resultado`, `terminado`, `cambiar_proyecto(p)` (sin moverse) y `cerrar()`, con candado.
  - Adentro: un `LectorPCM` en f32 de la voz con los tramos y `AjustesAudio(silencios=p.sonido.silencios)` (sin volumen ni fundidos: esos van al final), los fondos y sonidos con su volumen y una `CadenaVoz`.
  - Al final, el volumen, la normalización y los fundidos de `p.sonido`, en el tiempo del resultado.
  - **Normalizar:** mide el pico del resultado con una pasada del mezclador sin normalizar, en un hilo, con caché por proyecto. `MezcladorAudio(p, pico=...)` lo acepta como `LectorPCM`.
- **Mis sonidos:** se decodifican con PyAV a 48 kHz estéreo f32, con caché (los de hasta 10 min en memoria; más largos se rechazan con `ValueError`).
- **Sesión:** agregá las clases a `CLASES` y un campo `audio` (proyecto opcional) al estado de la sesión, compatible con sesiones viejas. Mirá cómo se rearman las dataclasses al leer.

- [ ] **Paso 1: pruebas que fallen** en `tests/test_proyecto_audio.py`. Medios generados con PyAV en una carpeta temporal: una voz como tono modulado o ruido con envolvente de sílabas, en MP3, M4A, OGG/Opus y WAV. `APPDATA` y `NATURALSHOT_CONFIG` en carpetas temporales. Pruebas:

```python
class PruebasProyectoAudio(unittest.TestCase):
    def test_abrir_cada_formato(self): ...            # mp3, m4a, ogg (opus), wav: duración ±0,05 s
    def test_archivo_sin_audio_da_error(self): ...    # un MP4 sin pista de audio -> ValueError
    def test_mezclador_igual_a_exportacion_wav(self): ...
        # proyecto con escena "Nota de voz caminando por la calle", leer todo con MezcladorAudio(f32)
        # y exportar a WAV: misma señal (|dif| < 1/32768 * 2, salvo el códec: probar con compresion=False)
    def test_saltar_y_seguir(self): ...                # ir_a_resultado(2.0) y leer 1 s ~ lo mismo que de corrido (atol 2e-3)
    def test_anclas_siguen_a_la_voz_al_cortar(self): ...
        # sonido anclado en 5,0 s; borrar el tramo 1-2 s -> en el resultado empieza en 4,0 s
        # ancla dentro de un tramo borrado -> arranca al principio del siguiente tramo conservado
    def test_fondos_hasta_tres_capas(self): ...        # 4 capas -> ValueError en ProyectoAudio
    def test_cada_formato_de_exportacion(self): ...    # whatsapp (.ogg, opus, mono), m4a, mp3, wav; se vuelven a abrir con PyAV
    def test_cancelar_no_deja_archivos(self): ...
    def test_escenas(self): ...                        # las 10 existen; aplicar una cambia voz, fondos y sonidos
    def test_escenas_propias(self): ...                # guardar, leer en otro proceso de lectura, borrar (APPDATA temporal)
    def test_mis_sonidos(self): ...                    # agregar (copia con nombre único), usar como fondo (se repite con fundido), renombrar y borrar
    def test_sonido_que_falta_se_saltea(self): ...     # borrar el archivo por fuera -> la mezcla sigue sin error
    def test_pickle_y_sesion(self): ...                # guardar y leer la sesión con un proyecto de audio
    def test_velocidad(self): ...                      # MezcladorAudio con escena completa >= 5 veces el tiempo real
```

  Completá cada prueba con datos concretos. Las de arriba son la lista obligatoria.
- [ ] **Paso 2:** correr. Resultado esperado: fallan.
- [ ] **Paso 3:** implementar.
- [ ] **Paso 4:** pruebas de C en OK y suite completa en OK.
- [ ] **Paso 5:** `herramientas/muestrario_audio.py`. Genera en `Muestras de audio\` (carpeta del proyecto):
  - `Fondos\<nombre>.wav` de 20 s;
  - `Sonidos\<nombre>.wav`;
  - `Escenas\<nombre>.ogg` o `.m4a`, cada escena aplicada a la voz de prueba;
  - `Voz de prueba.wav`;
  - un `LEEME.txt` que diga qué es cada cosa.
  - La voz de prueba se arma con `System.Speech`, en español si hay. Nunca se usan archivos personales.
  - Correrlo y verificar que todo se abre.

---

## Tarea D: interfaz del modo Audio

**Empieza cuando termine la integración del sonido en Video**, que deja `ui/forma_onda.py` y `ui/reproductor_audio.py`.

**Archivos:**
- crear `celular_natural/ui/modo_audio.py` y `tests/test_modo_audio.py`;
- modificar `ui/ventana.py`, `ui/modo_video.py` (`es_audio`, `clasificar_rutas` y `mensaje_ruteo` con audios), `ui/modo_facil.py` (constante `AUDIO`) y `ui/estilo.py`.

**Contenido:** lo de "Cómo se usa (interfaz)" del diseño, completo. Las piezas:
- `EditorAudio(QWidget)` con señales `audioCambiado`, `exportacionCambiada(bool)`, `progresoExportacion(int)` y `exportacionLista(str, str)`, como `EditorVideo`, para el chip.
- **Centro:** la forma de onda grande y la línea de tiempo de 3 pistas (Voz, Fondo, Sonidos), con bloques arrastrables que cambian el `ancla`.
- **Izquierda:** galería de escenas (tarjetas de 2 columnas, como la de estilos del modo fácil), "¿Cómo se grabó?" (4 tarjetas), "Cuánto" (Sutil, Normal y Fuerte), "Bajarle lo de IA" y "Avanzado" plegado.
- **Derecha:** "Fondo continuo" (hasta 3 capas), "Sonidos sueltos", "Que tape la voz", "Mis sonidos" y "Exportar".
- **Historial:** deshacer y rehacer de `ProyectoAudio` (es inmutable: la pila guarda proyectos).
- **Reproducción:** `ui/reproductor_audio.py` con `MezcladorAudio`. Al cambiar un ajuste, `cambiar_proyecto` sin cortar el sonido.

- [ ] **Paso 1: pruebas de interfaz (que fallen)** en `tests/test_modo_audio.py`. Ventana real offscreen:
  - el selector tiene Audio y Ctrl+Shift+A va y vuelve;
  - soltar un audio en Fácil pasa a Audio con aviso, y soltar una foto en Audio vuelve a fotos;
  - aplicar una escena cambia el proyecto y entra al historial (y deshacer vuelve);
  - agregar un sonido en el cursor y arrastrarlo cambia el ancla;
  - hasta 3 capas de fondo (la cuarta, deshabilitada);
  - exportar a WhatsApp con un diálogo simulado deja un `.ogg` válido;
  - la exportación sigue al cambiar de modo (chip);
  - sin dispositivo de audio no hay errores;
  - la sesión recuerda el proyecto de audio.
  - Cerrá las ventanas vaciando los borrados diferidos (`QApplication.sendPostedEvents(None, QEvent.DeferredDelete)`).
- [ ] **Paso 2:** implementar, de a una sección, corriendo las pruebas.
- [ ] **Paso 3:** capturas offscreen a 1366×768 y 1600×900:
  - Audio vacío;
  - con una voz;
  - con una escena;
  - con 2 capas de fondo y 2 sonidos;
  - exportando;
  - "Avanzado" abierto.
  - Mirarlas y corregir.
- [ ] **Paso 4:** arranque real con `python -X faulthandler main.py` (APPDATA de prueba): entrar a Audio, abrir, reproducir, exportar y cerrar. Sin *access violation*.
- [ ] **Paso 5:** suite completa en OK.

---

## Tarea E: ida y vuelta con Video

**Archivos:**
- modificar `celular_natural/motor/video.py`, `ui/editor_video.py`, `ui/modo_audio.py` y `ui/ventana.py`;
- crear `tests/test_ida_y_vuelta.py`.

- [ ] **Paso 1: pruebas que fallen:**
  - `exportar_video(..., audio_externo=AudioExterno(ruta, "original"))` con un video con cortes: el audio del MP4 es el externo con los mismos cortes (correlación > 0,95 contra el esperado);
  - con `"resultado"`, el audio externo empieza en 0 del resultado y se corta al largo;
  - un audio externo más corto que el video completa con silencio;
  - en la interfaz, "Editar el sonido en el modo Audio" abre Audio con la franja y el WAV en `%APPDATA%\NaturalShot PRO\temporal\`;
  - "Volver al video con este sonido" deja el video con ese sonido (y la vista previa lo usa);
  - "Cambiar el sonido por…" y "Volver al sonido original";
  - la sesión guarda la relación.
- [ ] **Paso 2:** implementar `AudioExterno` en el motor y después la interfaz.
- [ ] **Paso 3:** capturas a 1366 y 1600 px de los botones en Video y la franja en Audio. Suite completa en OK.

---

## Tarea F: cierre

- [ ] **`NaturalShot.spec`:** `hiddenimports` con `celular_natural.motor.ambientes`, `voz_natural`, `proyecto_audio` y `ui.modo_audio`.
- [ ] **Documentación:** `AUDIO.md` nuevo (como `VIDEO.md`), y en el README una sección "Modo Audio".
- [ ] **`ESTADO_DEL_PROYECTO.md`:** sección "Modo Audio ✅" con archivos, verificación y limitaciones.
- [ ] **Tutorial:** sumar la página del modo Audio y actualizar la de Video (ya no es una ventana aparte; sección Sonido). Esto es con capturas reales y solo `Foto.png` (ver las reglas de privacidad en el estado).
- [ ] **Compilación:** recompilar el .exe con `construir_exe.bat` y rehacer el zip con `herramientas.publicar.armar_zip`, sin cambiar la versión. Probar el zip descomprimido en una carpeta temporal: abre, entra a Audio y exporta.
