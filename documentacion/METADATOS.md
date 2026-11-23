# Metadatos de salida (NS-104)

Qué metadatos sale de NaturalShot en cada archivo exportado, y dónde se decide. La regla
para todo el código: **ningún exportador escribe metadatos por su cuenta**. Las fotos pasan
por `celular_natural/motor/metadatos.py` (desde `imagen_io.exportar_imagen`), y el video y el
audio se escriben con PyAV sin copiar los metadatos del original.

## Política (NS-104.1)

Esta política cubre **privacidad y coherencia técnica**. No agrega, quita ni imita marcas de
procedencia (por ejemplo C2PA o el campo IPTC que dice cómo se hizo una imagen), ni imita la
identidad de una cámara o un celular. La app no escribe XMP ni IPTC.

### Fotos (JPEG y PNG), con "Conservar metadatos EXIF" marcado

| Campo | Qué pasa | Por qué |
|---|---|---|
| GPS (todo el bloque) | Se quita | Privacidad: la ubicación de quien sacó la foto |
| `BodySerialNumber`, `LensSerialNumber` | Se quitan | Privacidad: identifican el equipo de una persona |
| `CameraOwnerName` | Se quita | Privacidad |
| `HostComputer`, `DocumentName` | Se quitan | Privacidad: el nombre de la PC y del archivo |
| `XPAuthor`, `XPComment`, `XPTitle`, `XPKeywords`, `XPSubject` (Windows) | Se quitan | Privacidad: autor, títulos y comentarios personales |
| `Artist`, `Copyright` | Se quitan | Privacidad: casi siempre el nombre real de quien sacó la foto |
| `UserComment`, `ImageDescription` | Se quitan (siempre, no solo si es una ruta) | Privacidad: texto libre, puede decir dónde o de quién es la foto |
| `ImageUniqueID` | Se quita | Privacidad: liga la exportada con el original |
| `MakerNote` | Se quita | Privacidad: ahí las cámaras guardan seriales y datos internos |
| `Orientation` | Sale como 1 (no se escribe) | Los píxeles ya vienen girados al abrir la foto |
| `PixelXDimension`, `PixelYDimension` | Se escriben con el tamaño real | Coherencia tras recortar o reescalar |
| Miniatura EXIF (IFD1) | No se copia | Mostraría la foto de antes de editar |
| Perfil ICC | Se conserva (o sRGB si no tenía) | Los colores se ven igual en cualquier programa |
| `Make`, `Model`, `Software`, fechas, exposición y el resto técnico | Se conservan tal cual | Es lo que la casilla promete ("Copia fecha, cámara y demás datos") |
| XMP, IPTC, textos de PNG (prompts de ComfyUI, comentarios) | No se copian nunca | La app arma el archivo desde los píxeles y solo escribe el EXIF de arriba |

Sin la casilla marcada, la foto sale sin ningún EXIF (solo el perfil ICC).

### Video (MP4) y audio (M4A, MP3, WAV)

| Campo | Qué pasa |
|---|---|
| Ubicación (`location`, `©xyz`, `com.apple.quicktime.location.*`) | No se copia del original |
| `creation_time` | No se copia; nunca puede quedar en el futuro (lo revisa la auditoría) |
| Rotación (`displaymatrix`) | Los cuadros se exportan ya girados (ver `VIDEO.md`) |
| `encoder`, `handler_name` | Los que pone FFmpeg (`Lavf…`, `Lavc…`), sin cambios |

> **Pendiente del dueño (D2):** si quiere fijar otro valor de `encoder`, `handler_name` o
> `creation_time`, tiene que decidirlo y anotarlo acá antes de cambiar el código.

## Dónde sale cada archivo (NS-104.2)

| Salida | Función | Archivo | Metadatos |
|---|---|---|---|
| Foto única (JPEG/PNG) | `exportar_imagen` | `celular_natural/motor/imagen_io.py` | `metadatos.limpiar_exif` |
| Lote de fotos | `procesar_lote` → `exportar_imagen` | `celular_natural/motor/lote.py` | `metadatos.limpiar_exif` |
| Exportar desde el editor | `VentanaPrincipal` → `exportar_imagen` | `celular_natural/ui/ventana.py` | `metadatos.limpiar_exif` |
| Video (MP4) | `exportar_video` → `_exportar` | `celular_natural/motor/video.py` | Ninguno del original |
| Solo el sonido de un video | `exportar_sonido` | `celular_natural/motor/video.py` | Ninguno del original |
| Audio (M4A/MP3/WAV) | `exportar_audio` | `celular_natural/motor/audio.py` | Ninguno del original |
| Proyecto de audio | `exportar_proyecto` | `celular_natural/motor/proyecto_audio.py` | Ninguno del original |

## Marcas de procedencia

La app no escribe C2PA ni XMP propios, y no imita la identidad de ninguna cámara.

De hecho, **el archivo se arma desde los píxeles**, así que nada de lo que traía el original
sobrevive: EXIF sensible, XMP, IPTC, los textos de PNG (los prompts de ComfyUI) y cualquier
bloque C2PA/JUMBF. `auditar_imagen` lo comprueba y falla si aparece uno.

Lo que **no** desaparece solo son las marcas incrustadas en los píxeles (SynthID). Con un
preset aplicado, el reescalado, el grano y el JPEG las degradan de paso. Con "Sin efecto" y
PNG los píxeles quedan intactos, así que para eso está la perturbación al exportar: reescala
un 1,5 % y agrega ruido de sigma 2, sin cambiar el tamaño ni el color.

Las marcas **visibles** (un logo en una esquina) las quita la tarjeta **Borrar objetos**:
"Quitar marca" marca la posición típica y la rellena con lo de alrededor; el botón de lupa
la busca sola en las cuatro esquinas. Va antes del filtro, así el grano queda parejo encima.

## Otros cuidados (no son metadatos)

* **El nombre del archivo exportado** sale del nombre del original (`IMG_0001_celular.jpg`). Si el
  original se llama con el nombre de alguien, cambialo al exportar.
* **Los proyectos (`.nslite`) guardan la ruta de la foto base en la PC** (por ejemplo
  `C:\Users\<usuario>\...`, con el usuario de Windows) junto con las capas (estas, sin metadatos):
  son para trabajar, no para compartir. Para publicar, siempre se exporta.

## Auditoría (NS-104.3)

```bat
.venv\Scripts\python herramientas\auditar_metadatos.py CARPETA --reporte reporte.csv
```

Revisa cada foto, video y audio contra esta política y sale con código 1 si alguno no cumple.
`--completo` agrega al reporte el volcado de ExifTool y ffprobe, si están instalados.

## Pruebas (NS-104.8)

`tests/test_metadatos.py` exporta JPEG, PNG, lote, MP4, M4A y WAV desde originales con GPS,
seriales, rutas, orientación girada y miniatura, y falla si alguno viola la política. También
cubre la herramienta de auditoría.
