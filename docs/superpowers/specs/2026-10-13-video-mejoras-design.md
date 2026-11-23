# Video: "Mejorar calidad" (sin IA) y cortes que desaparecen

Fecha: 13/10/2026. Estado: aprobado por el dueño en el chat ("hagamos eso a ver si mejora").

## 1. Mejorar calidad

### Para qué

El dueño tiene videos de 480p o menos, muy comprimidos, que "se ven mal". Quiere que se vean mejor **sin IA**: teme que su compu no lo soporte y que el proyecto se complique. Expectativa acordada: un 480p muy comprimido queda como **un buen 720p**, no como un 4K.

### Cómo (por cuadro, en orden)

1. **Cuadros vecinos (superresolución multicuadro):**
   - Alinear los cuadros `t-2…t+2` con el cuadro `t` usando flujo óptico DIS de OpenCV (`cv2.DISOpticalFlow_create`), calculado a la resolución de entrada y sobre la luminancia.
   - Combinar con pesos robustos: menos peso donde la diferencia después de alinear es grande (oclusiones o cambios de escena), así no quedan fantasmas.
   - En un corte de escena (diferencia global grande) se usa solo el cuadro actual.
   - La combinación se hace sobre la grilla agrandada: cada vecino se remapea a la salida con su flujo, lo que aprovecha el corrimiento de subpíxel y recupera detalle real.
2. **Quitar cuadraditos:** reducción de bloques y "mosquito" de la compresión, con filtros que respetan los bordes (bilateral o guiado, en luminancia y crominancia por separado). Más suave en la luminancia, para no perder detalle.
3. **Agrandar:** Lanczos (`cv2.INTER_LANCZOS4`) o mejor, hasta la resolución pedida (720p o 1080p, conservando la proporción).
4. **Enfocar:** máscara de enfoque solo en bordes (a partir de un mapa de bordes), con límite contra halos (clamp a los mínimos y máximos locales) y sin realzar el ruido de las zonas planas.
5. Después sigue el filtro de siempre de la app (grano, etc.), ya a la resolución de salida.

### Motor: `celular_natural/motor/mejora_video.py` (nuevo)

```python
@dataclass(frozen=True)
class AjustesMejora:
    activa: bool = False
    cuadraditos: float = 0.5   # 0..1
    nitidez: float = 0.5       # 0..1
    vecinos: float = 0.5       # 0..1 (0 = no usa vecinos)
    def sin_cambios(self) -> bool: ...     # not activa
    def con(self, **cambios) -> "AjustesMejora": ...   # acomoda rangos; pickle

RADIO_VECINOS = 2

def mejorar_cuadro(actual: np.ndarray, vecinos: Sequence[Optional[np.ndarray]], ancho: int, alto: int,
                   ajustes: AjustesMejora) -> np.ndarray: ...
    # RGB uint8 (h, w, 3) -> RGB uint8 (alto, ancho, 3). vecinos: [t-2, t-1, t+1, t+2], None si no existe.

class MejoradorVideo:
    """Para exportar: se le dan los cuadros en orden y devuelve los mejorados con RADIO_VECINOS de retraso."""
    def __init__(self, ajustes: AjustesMejora, ancho: int, alto: int): ...
    def agregar(self, rgb: np.ndarray) -> list[np.ndarray]: ...
    def terminar(self) -> list[np.ndarray]: ...
```

- `mejorar_cuadro` es una función pura (sin estado). `MejoradorVideo` usa la misma función, así que la vista previa es igual a la exportación.
- **Velocidad:** de 854×480 a 1920×1080, menos de 150 ms por cuadro con todo prendido; a 1280×720, menos de 80 ms. Puede usar `cv2.setNumThreads` o hilos para el flujo de los 4 vecinos.

### Integración (después, cuando termine la interfaz del sonido en Video)

- **`motor/video.py`:**
  - `exportar_video(..., mejora: Optional[AjustesMejora] = None)`;
  - con mejora activa, `tamano_salida` deja agrandar (720p o 1080p aunque el original sea más chico);
  - la mejora va antes del filtro, en orden y con el retraso de los vecinos;
  - los tramos borrados se respetan (los vecinos solo pueden venir del mismo tramo conservado).
- **Vista previa:** `cuadro_en` del cursor más los vecinos, con caché.
- **Interfaz** (`ui/editor_video.py`):
  - sección **"Mejorar calidad"** en la columna derecha: interruptor y barras **Quitar cuadraditos**, **Nitidez** y **Usar cuadros vecinos**;
  - en "Exportar video", 720p y 1080p se habilitan para agrandar si la mejora está prendida;
  - Antes / Después muestra la diferencia;
  - el resumen de exportación avisa que tarda más.
- **Deshacer, rehacer y sesión:** `AjustesMejora` entra al historial del editor de video y, si el estado del video se guarda en la sesión, a `CLASES`.

### Pruebas (objetivas)

- **Verdad de referencia:** un video sintético en alta resolución (1920×1080) con texto, líneas finas, texturas y un paneo lento con corrimiento de subpíxel, generado con OpenCV y numpy.
- Se lo **degrada** a 854×480 con H.264 de bitrate bajo (con PyAV, CRF alto) y se mejora de vuelta a 1920×1080.
- **Criterio:** mejor PSNR y SSIM contra la verdad que un agrandado bicúbico simple del mismo 480p, por un margen medible (PSNR ≥ +0,5 dB). Con vecinos, mejor que sin vecinos en el paneo.
- **Corte de escena:** sin fantasmas. Junto al corte, el cuadro mejorado se parece al actual y no al de la otra escena.
- Determinismo, tamaños de salida, `AjustesMejora()` sin cambios y velocidad.
- **Capturas antes y después** (recortes ampliados) revisadas a ojo.

## 2. Cortes que desaparecen de la línea de tiempo

### Para qué

Hoy, al borrar un tramo del video, queda en la línea de tiempo rayado y con "Borrado". El dueño quiere que **desaparezca y el resto se junte** (como en CapCut).

### Cómo

- La línea de tiempo del editor de video muestra **el resultado**: los tramos borrados no se dibujan y lo que sigue se corre.
- Las miniaturas, la regla de tiempo, el cursor y la duración pasan al tiempo del resultado. Internamente, la edición sigue en tiempo original (`EdicionVideo`), y se convierte con un mapeo resultado ↔ original.
- En cada unión donde hubo un borrado queda una **marquita** finita. Al tocarla aparece **"Recuperar lo borrado"** (vuelve a mostrar ese tramo, con historial). Ctrl+Z también lo deshace.
- La entrada y la salida (recorte del principio y del final) siguen funcionando con los corchetes; recortar el principio también "desaparece".
- La pista de sonido (forma de onda y silencios) sigue al mismo mapeo.
- Se hace en la misma pasada que la interfaz de "Mejorar calidad", cuando termine la integración del sonido en Video, porque es el mismo archivo (`ui/editor_video.py`).
