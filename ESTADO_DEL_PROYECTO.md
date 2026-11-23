# NaturalShot PRO: estado del proyecto

Última actualización: 13/10/2026, después de agregar la pantalla de carga y la sesión que se recuerda (sin publicar nada).

Para retomar, abrí Claude Code en esta carpeta y decile: **"seguí desde ESTADO_DEL_PROYECTO.md"**.

---

## Cómo abrir la app

- **Acceso directo:** `NaturalShot PRO.lnk`, en esta carpeta.
- **Ejecutable:** `dist\NaturalShot\NaturalShot.exe`. Tiene **todo**, incluidos la pantalla de carga, la sesión recordada y el zoom del tutorial (recompilado el 13/10). El zip `NaturalShot PRO - para otra PC.zip` (118 MB) también está al día y probado.
- **Desde el código:** `ejecutar.bat`, o `.venv\Scripts\python main.py`.
- **Recompilar el .exe:** `construir_exe.bat`, o `.venv\Scripts\python -m PyInstaller --noconfirm --clean NaturalShot.spec`. Antes de recompilar cerrá la app.
- **Armar una versión para la editora:** `publicar_version.bat X.Y.Z "Novedad"` (pruebas, .exe, zip y `version.json` en `publicar\vX.Y.Z\`). Con `--subir` la publica en GitHub: solo con el OK del dueño.

## Terminado y verificado (todo dentro del .exe)

| Función | Detalle |
|---|---|
| Filtro "celular natural" | Motor por módulos: sensor, óptica, detalle, texturas, iluminación, color, grano, compresión y máscaras por región. |
| Presets | 34, incluidos estilos de teléfonos y perfiles de cámara. Botón (i) con la descripción y la opción de guardar presets propios. |
| Capas | Hasta 4 presets apilados, cada uno con su intensidad. |
| Zonas por capa | Rectángulo, elipse, lazo poligonal y **pincel** (tamaño, dureza y goma). Con borde suave e invertir. |
| Comparar | Dividir, Antes, Después y **Lado a lado** con zoom sincronizado. Zoom al 100 % y 200 %. |
| Recorte | No destructivo, con proporciones: libre, original, 1:1, 4:5, 3:4, 9:16, 4:3 y 16:9. |
| **Tira de fotos** | Abrir o arrastrar varias fotos a la vez. Cada foto guarda su propia edición. |
| **Montaje** | Pegar partes de otra foto (mitades, rectángulo, elipse, lazo o pincel), con alineación e igualado de color automáticos. |
| **Fondo** | Marcar un objeto y elegir **Transparente** (PNG sin fondo, recortado al objeto) o **Desenfocado** (modo retrato con bokeh, sin halo). |
| **Girar, voltear y enderezar** ✅ | Botones al lado de Recortar: girar 90° a cada lado, voltear horizontal y vertical, y **Enderezar** (barra con ángulo −15° a 15°, **Nivelar automático**, cuadrícula, Aplicar y Cancelar). No destructivo, por foto, con historial. Zonas, trazos, borrados y recorte giran con la foto (`motor/edicion.py`). *(solo desde el código)* |
| **Selección automática** ✅ | **Cielo** y **Piel** en el "Dónde" de capas y montaje; **Ajustar al contorno** en Fondo (desde lazo, pincel o un rectángulo). En segundo plano con "Detectando…", con caché y corregibles con el pincel. Zona raster `"mascara"` en `Zona`. *(solo desde el código)* |
| **Borrar objetos** ✅ | Tarjeta propia en la columna izquierda: marcar con pincel, lazo o rectángulo; **Rellenar automático** o **Clonar desde…** (arrastrando, con vista previa de la fuente). Varias zonas por foto, con historial; va antes del filtro y a resolución completa. *(solo desde el código)* |
| Historial | Lista con cada cambio; un clic vuelve a ese punto. Ctrl+Z y Ctrl+Y. |
| Interfaz | Estilo de tu CRM: oscura, magenta y violeta, tres columnas tipo Photoshop, tarjetas por sección, íconos Lucide y logo nuevo. La rueda del mouse no cambia valores sin querer. |
| Exportar | PNG o JPEG con calidad. El original nunca se toca. Procesamiento de varias fotos (lote). |

**Pruebas:** pasan las 181 (158 de antes + 23 nuevas de la integración en `tests/test_integracion.py`). `tests.test_video` es del editor de video y se corre aparte.

```
set QT_QPA_PLATFORM=offscreen
.venv\Scripts\python -m unittest tests.test_motor tests.test_modulos tests.test_calidad tests.test_zonas tests.test_montaje tests.test_desenfoque tests.test_geometria tests.test_seleccion_auto tests.test_borrado tests.test_integracion
```

## Motores integrados (12/10/2026)

| Módulo | Dónde se usa | API principal |
|---|---|---|
| `motor/geometria.py` (24 pruebas) | Botones de girar y voltear, barra de Enderezar | `Geometria(giro90, voltear_h, voltear_v, enderezar, recortar_bordes)`, `girada()`, `volteada()`, `aplicar_geometria`, `tamano_resultante`, `transformar_puntos`, `destransformar_puntos`, `matriz_geometria`, `detectar_horizonte`. Positivo = horario. |
| `motor/seleccion_auto.py` (17 pruebas) | "Dónde" → Cielo / Piel; Fondo → Ajustar al contorno | `mascara_cielo`, `mascara_piel`, `recortar_objeto(rgb, rect o mascara)`, `codificar_mascara`, `decodificar_mascara`. |
| `motor/borrado.py` (20 pruebas) | Tarjeta Borrar objetos | `rellenar(rgb, mascara, ...)`, `clonar(rgb, mascara, (dx, dy), sin_costuras=True)`. |
| `motor/edicion.py` (nuevo) | Ventana: arma la foto que entra al filtro | `matriz_cambio`, `convertir_zona`, `convertir_recorte`, `convertir_borrado`, `ZonaBorrado(zona, modo, dx, dy, sin_costuras)`, `aplicar_borrados` (con caché por prefijo), `con_geometria` (con caché). |
| `motor/zonas.py` (ampliado) | Todas las zonas | Forma `"mascara"`: `Zona.desde_mascara(m, origen)`, campos `datos` (PNG), `matriz` (afín, 6 valores) y `origen`; `transformar_zona`, `registrar_mascara` (versión completa en memoria), `mascara_trazos(..., inicial=)`. |

Todo se exporta en `celular_natural/motor/__init__.py`.

**Estrategia de coordenadas (opción a, "lo que ves"):** zonas, trazos, borrados (con su desplazamiento de clonado) y recorte se guardan normalizados respecto de la **foto base** = original con la geometría, sin recortar. Al cambiar la geometría, `ventana.estado_con_geometria` convierte todo el estado con la matriz exacta de `aplicar_geometria`: rectángulos y elipses pasan a polígono solo si quedan torcidos, los radios del pincel se reescalan y a las máscaras solo se les compone la matriz (sin remuestrear). El recorte, con 90° y volteos, se transforma exacto; al enderezar conserva centro y tamaño en píxeles. Cada paso del historial guarda geometría + zonas ya convertidas.

**Orden:** original → geometría → montaje (la otra foto se gira igual y se alinea) → borrar objetos → recorte → fondo → filtro, a resolución completa en `_recalcular_fuentes` (la vista previa es una reducción: exportación = vista). "Antes" muestra la foto sin los borrados para comparar.

## Pendiente (en este orden)

1. ~~Motor de "Borrar objetos"~~: ✅ terminado (ver tabla de arriba).
2. ~~Tutorial en PDF~~: ✅ hecho, en `Tutorial\NaturalShot - Guía de uso.pdf` (15 páginas A4, con capturas reales de `Foto.png`). Es solo local. Cuando se integren las funciones nuevas hay que sumarles su sección. Los scripts de captura quedaron en una carpeta temporal y se pierden al apagar, así que esas capturas habrá que rehacerlas. Requisitos que se usaron (sirven para las secciones nuevas):
   - **Destino:** `Tutorial\NaturalShot - Guía de uso.pdf`.
   - **Diseño:** tema oscuro de la app y A4, con capturas reales y marcadores numerados.
   - **Contenido:** portada, índice y secciones paso a paso (pantalla, abrir y tira, presets, comparar, ajustes, capas y zonas, recorte, montaje, fondo, historial, exportar y atajos), con una caja "Tip" en cada una.
   - **Herramientas:** capturas desde un script con la ventana en modo offscreen (`ventana.grab()`), y el PDF con `QPdfWriter` y `QPainter` de PySide6. No instalar paquetes en el `.venv`.
   - ⚠️ **Privacidad:**
     - Usar **solo** `C:\Users\cappa\OneDrive\Escritorio\Foto.png` (foto de la novia del usuario, generada con IA). Ningún otro archivo del Escritorio y nada de comodines como `foto*`.
     - El PDF queda **solo local**: no se publica en claude.ai y no se mete en el .exe.
3. ~~**Integración en la interfaz** de geometría, selección automática y borrar objetos~~: ✅ hecha (ver "Motores integrados"). Verificada con la ventana real en offscreen a 1366 y 1600 px (capturas revisadas), exportación idéntica a la vista también a 12 MP. Archivos tocados: `motor/__init__.py`, `motor/zonas.py`, `motor/edicion.py` (nuevo), `ui/ventana.py`, `ui/vista_comparacion.py`, `ui/controles.py`, `ui/montaje.py`, `ui/fondo.py`, `ui/borrar.py` (nuevo), `ui/historial.py`, `ui/estilo.py`, `tests/test_integracion.py` (nuevo), `assets/iconos/` (9 íconos nuevos) y este archivo y el README.
   - **Falta:** sumar al PDF del tutorial las secciones de girar/enderezar, selección automática y borrar objetos (con las reglas de privacidad de arriba: solo `Foto.png`).
4. ~~Pruebas completas y .exe~~: ✅ hecho. Pasan las **197 pruebas** (`QT_QPA_PLATFORM=offscreen .venv\Scripts\python -m unittest discover -s tests`). El .exe está recompilado con todo, incluido el video. También está el paquete **`NaturalShot PRO - para otra PC.zip`** (112 MB, con un LEEME): lo probé descomprimido en otra carpeta y abre videos.
5. ~~Tutorial actualizado~~: ✅ 24 páginas, con secciones nuevas para girar y enderezar, borrar objetos, selección automática y editor de video. Sigue siendo solo local.
6. ✅ **Arreglos del 12/10 (noche):**
   - **Cierre intermitente:** los filtros globales de teclado y rueda (`FiltroRueda`, `FiltroBarraEspaciadora` en `ventana.py`) recibían eventos de hilos de trabajo y eso provocaba un *access violation*. Ahora heredan de `_FiltroGlobal`, que ignora los eventos de otros hilos sin leerlos. Con el código anterior el error aparecía 3 de 3 veces; con el arreglo, 0 de 3.
   - **Miniaturas:** con un video de un solo keyframe salían todas iguales. Ahora hay un recorrido secuencial de respaldo (`_miniaturas_secuenciales` en `motor/video.py`), con su prueba.
   - **Verificación:** pasan las **198 pruebas**, .exe y zip recompilados, y la app abrió con video 6 de 6 veces desde el zip.

## Modo fácil y modo editor ✅ (12/10/2026, solo desde el código)

La app la va a usar sobre todo una diseñadora. Arriba a la izquierda, debajo del logo, hay un selector **"Fácil | Editor"** (también con **Ctrl+E**). Se recuerda con `QSettings("NaturalShot", "NaturalShot PRO")`, clave `interfaz/modo`, y la primera vez arranca en **Fácil**. Los dos modos comparten el mismo estado (foto, tira, historial, preset y ediciones): cambiar de modo solo cambia qué se ve.

- **Modo fácil:** cuatro pasos numerados en tarjetas, en la columna izquierda.
  1. **Tu foto:** botón grande "Abrir fotos". Con una foto abierta queda en una línea, con el nombre.
  2. **Elegí un estilo:** galería en dos columnas con **la foto actual procesada con cada preset**. Primero 8 recomendados y después "Ver más estilos", agrupado como en `GRUPOS_PRESETS`, con los presets propios y "Sin efecto". La elegida va con borde magenta y tilde; también se puede elegir con Tab y Enter.
  3. **¿Cuánto efecto?:** la intensidad general, con referencias Sutil · Normal · Fuerte.
  4. **Exportar:** "Mejor calidad (PNG)" o "Más liviano (JPEG)", el botón "Exportar foto" con degradado y el enlace "Exportar varias fotos…".
- **Pasos 3 y 4:** quedan fijos abajo, siempre a la vista.
- **Aviso:** si la foto tiene ediciones del editor (capas, montaje, borrados, fondo, enderezado o volteo), aparece una nota chica.
- **Resto de la pantalla en Fácil:**
  - Se ocultan la columna derecha y el historial (Ctrl+Z y Ctrl+Y siguen andando).
  - En la barra quedan Abrir, deshacer y rehacer, comparar, Recortar, girar 90° y Video.
  - `_compactar_barra` descuenta lo oculto.
- **Modo editor:** igual que antes, más el selector.
- **Miniaturas:**
  - Se calculan a 256 px con `procesar_pila` y la `escala_vista` correcta, en un `QThreadPool` propio de baja prioridad y con `Tarea`.
  - Se guardan en caché por foto, geometría, montaje, borrados, recorte y preset.
  - Tardan unos 12 ms cada una y en el modo editor no se calculan.
- **Archivos:** `ui/modo_facil.py` (nuevo), `ui/ventana.py` (selector, `establecer_modo`, `fuente_para_estilos`, Ctrl+E y ganchos en carga, fuentes, habilitados y cierre), `ui/estilo.py` (estilos nuevos), `tests/test_modo_facil.py` (nuevo, 7 pruebas), README y este archivo. No se agregaron filtros globales de eventos. El editor de video no cambió.
- **Verificación:**
  - Pasan las **205 pruebas** (198 de antes + 7 de `tests/test_modo_facil.py`) con `QT_QPA_PLATFORM=offscreen .venv\Scripts\python -m unittest discover -s tests`. Las pruebas usan un .ini temporal (`NATURALSHOT_CONFIG`) y no tocan el registro.
  - Ventana real offscreen en 1366, 1600 y 1920 px, en los dos modos, con y sin foto (capturas revisadas).
  - Tres recorridos con `python -X faulthandler`, con cambios de modo, clics en tarjetas, giros, recortes, deshacer, varias fotos, exportar, editor de video y cierre con miniaturas en curso: ningún *access violation*.
- **Falta:**
  - Recompilar el .exe y rehacer el zip (no se tocaron `dist/` ni `build/`).
  - Sumar al tutorial una página del modo fácil.

## Actualizaciones automáticas ✅ (12/10/2026, solo desde el código; no se publicó nada)

La app compilada busca versiones nuevas en un repositorio **privado** de GitHub (`Zergeeenk/naturalshot-releases`), avisa con un banner arriba de la ventana y se actualiza sola con un clic. Solo pueden actualizar las personas que el dueño invita como colaboradoras y que aceptan la invitación. Detalle completo en el README, sección *Actualizaciones automáticas y cómo publicar una versión*.

- **Acceso:** GitHub App del dueño con *Contents* y *Metadata* de solo lectura, instalada solo en ese repositorio y con **device flow**. La editora toca **Conectar con GitHub**, escribe el código en github.com/login/device y autoriza. El token (y el refresh token, si vencen) queda **cifrado con DPAPI** en `%APPDATA%\NaturalShot PRO\sesion_github.dat`. Hay botón para desconectar.
- **Constantes:** `REPOSITORIO` y `CLIENT_ID`, juntas al principio de `celular_natural/actualizador.py`. `CLIENT_ID` tiene un **valor de relleno**: mientras no se cambie, las actualizaciones quedan apagadas y no se muestra ningún aviso.
- **Interfaz:**
  - **Banner:** "Hay una versión nueva (X.Y.Z)", con Ver novedades, **Actualizar ahora**, Más tarde y No avisar de esta versión. También avisa "Conectá tu cuenta…", el progreso con Cancelar, "sin acceso", "sesión vencida" y "Listo: se actualizó".
  - **Versión:** `v1.0.0`, junto al nombre (visible en los dos modos), con un menú para buscar, conectar o desconectar y abrir la página de versiones.
- **Instalación:**
  1. Descarga en segundo plano y verifica el SHA-256.
  2. Descomprime y valida que estén `NaturalShot.exe` y `_internal`.
  3. Lanza un script de PowerShell sin ventana que espera a que se cierre la app, hace un respaldo y copia la versión nueva (`robocopy /MIR` solo sobre `_internal`). Si algo falla, restaura el respaldo. Después vuelve a abrir la app y borra los temporales.
  4. Si hay una exportación en curso, espera; si hay fotos con cambios, pregunta.
- **Archivos nuevos:**
  - `celular_natural/actualizador.py` (lógica, sin Qt) y `celular_natural/ui/actualizaciones.py` (banner, diálogo y menú).
  - `herramientas/publicar.py` y `publicar_version.bat`.
  - `herramientas/LEEME_distribucion.txt` (el LEEME del zip, con un párrafo sobre las actualizaciones).
  - `tests/test_actualizador.py` (41 pruebas) y `tests/servidor_github_falso.py`.
  - 8 íconos de Lucide en `assets/iconos/`.
- **Archivos tocados:** `ui/ventana.py` (banner arriba, botón de versión, `exportando_algo`, `tiene_ediciones` y aviso al cerrar), `ui/estilo.py`, `main.py` (busca 1,5 s después de abrir), README y este archivo.
- **Verificación:**
  - Pasan las **246 pruebas** (205 + 41).
  - Prueba de punta a punta con la app **compilada**, en carpetas temporales, con un servidor local que imita a GitHub. La versión 1.0.1 se armó con `publicar_version.bat` en una copia del proyecto. Tres casos:
    - **Normal:** device flow, banner, descarga de 115 MB, instalación y la app vuelve a abrir como 1.0.1. La carpeta queda idéntica a la compilación 1.0.1, en unos 17 s.
    - **SHA-256 incorrecto:** no instala nada.
    - **Falla a mitad de la copia:** restaura todo y vuelve a abrir la 1.0.0.
  - En los tres casos: ninguna ventana de consola, el token nunca en el log ni en texto plano, la URL firmada sin `Authorization` y sin temporales sobrantes.
  - Capturas offscreen del banner a 1366 y 1600 px revisadas.
- **Falta (lo hace el dueño, u otra persona con su permiso; ver README):**
  1. Crear el repositorio privado.
  2. Crear la GitHub App, instalarla solo en ese repositorio y pegar el Client ID en `CLIENT_ID`.
  3. Invitar a la editora.
  4. `publicar_version.bat 1.0.0 "…" --subir`, y pasarle ese zip a mano por última vez (su copia actual no tiene el actualizador).
  - No se recompiló `dist\` ni se rehízo `NaturalShot PRO - para otra PC.zip`: conviene hacerlo con `publicar_version.bat` cuando esté el Client ID.
- **Antes de publicar:**
  - **Todavía no se publicó nada.** Antes de crear el repositorio, la GitHub App o la primera versión, hay que pedirle el OK final al dueño.
  - Si es una cuenta personal, GitHub no permite colaboradores de solo lectura (ver README).
- **Tutorial para la versión:** no se usa la foto de la novia, aunque el repositorio sea privado. Hace falta una foto de ejemplo sin personas reales. `publicar.py` solo sube `Tutorial\tutorial_compartible.pdf` si existe, y nunca la guía actual.
- **Falta para activarlo, y lo tiene que hacer el dueño** (el sistema de permisos bloquea las subidas a internet):
  1. crear el repositorio privado con el comando de arriba;
  2. crear la GitHub App en la web y poner su Client ID en `CLIENT_ID`;
  3. pasar el usuario de GitHub de la editora para invitarla;
  4. `publicar_version.bat 1.0.0 "…" --subir`.

## Colores gris tipo Discord ✅ (12/10/2026, noche)

A pedido del dueño, el fondo pasó de casi negro a gris oscuro. Paleta en `ui/estilo.py`: `FONDO #2f3136`, `LATERAL #313338`, `TARJETA #33353b`, `TARJETA_2 #37393f`, `BORDE #3f4148`; el fondo de la foto en la vista es `#1e1f22`. Los acentos magenta y violeta siguen igual.

Los colores oscuros que estaban escritos directamente en otros archivos de la interfaz se pasaron con la misma regla (se conserva el orden de claridad). Copia de los archivos anteriores en `scratchpad\respaldo_colores\`.

Pasan las 246 pruebas. El .exe y el zip están recompilados. Antes, la compu se había apagado de golpe y se verificó que no se rompió nada.

## Tutoriales ✅ (29 páginas cada uno, paleta gris)

- `Tutorial\NaturalShot - Guía de uso.pdf`: personal, con la foto de la novia. **No se comparte.**
- `Tutorial\tutorial_compartible.pdf`: sin ninguna imagen personal, con una foto de ejemplo generada (lago, montañas, bote). Es el que se publica con cada versión.

Los dos tienen la sección "Actualizaciones automáticas". Los scripts están en `scratchpad\guia4\` (carpeta temporal).

## Tutorial dentro de la app ✅ (13/10/2026)

Ventana `ui/tutorial.py` (`DialogoTutorial`, con `QPdfView`). Aparece **cada vez que se abre la app** hasta que se tilda "No volver a mostrar" (clave QSettings `interfaz/tutorial_no_mostrar`). Se vuelve a abrir con el ícono del libro, junto a la versión, o con **F1**. La guía va en `assets/tutorial.pdf` (empaquetada por `NaturalShot.spec`, que ya no excluye QtPdf).

**NS-106.4 (20/11): `assets/tutorial.pdf` y `assets/tutorial_lite.pdf` son ahora las `tutorial_compartible`** (paisaje generado, sin personas reales). La guía con Foto.png queda solo en `Tutorial\` y una prueba (`tests/test_tutorial.py`) impide que vuelva a entrar al paquete.

Pasan las 249 pruebas, entre ellas `tests/test_tutorial.py`. El .exe y el zip (118 MB) están recompilados, y se verificó que el tutorial aparece al abrir la app desde el zip descomprimido.

## Pantalla de carga y recordar la sesión (pedido nuevo, en curso, 13/10/2026)

- **Pantalla de carga** animada al abrir: logo con brillo y barra de progreso con etapas reales. Se desvanece y la ventana aparece con un efecto suave.
- **Sesión:** al cerrar con fotos, la próxima vez se reabren las mismas fotos con sus ediciones, la foto actual y el modo.
  - Se guarda sola mientras se trabaja (por los apagones), en `%APPDATA%\NaturalShot PRO\sesion\`, con escritura atómica.
  - Si el archivo está roto, arranca limpio y lo guarda como `.bak`.
  - En la tira habrá "Quitar todas las fotos" para empezar de cero.

Si se cortó, revisar `ui/carga.py`, `main.py`, `ui/ventana.py` y `tests/test_sesion.py`. Al terminar falta recompilar el .exe y rehacer el zip.

## Pantalla de carga y sesión ✅ (13/10/2026, solo desde el código)

### Pantalla de carga

Antes, al hacer doble clic pasaban unos segundos sin nada en pantalla. Ahora aparece enseguida una pantalla de carga propia (`ui/carga.py`, `PantallaCarga`):

- **Aspecto:** ventana sin marco, centrada, con fondo translúcido, una tarjeta gris tipo Discord (`TARJETA` arriba → `FONDO` abajo, borde `BORDE`, esquinas de 18 px) y una sombra suave.
- **Logo animado con `QPainter` a unos 60 cuadros por segundo:** "respira" (escala 1 ± 2,5 %) delante de un halo magenta y violeta que pulsa. Cada 3,2 s lo cruza un brillo en diagonal, recortado a la forma del logo, y titila la estrellita.
- **Textos:** "NaturalShot" con la insignia PRO, "Editor de fotos realistas" y la versión.
- **Barra de progreso:** degradado rosa → magenta → violeta, con un reflejo que la recorre. Abajo, la etapa (con fundido al cambiar) y el porcentaje.
- **Etapas reales** (`main.py`): Preparando el motor… → Cargando la interfaz… → Armando la ventana… → Abriendo tus fotos… → ¡Listo!. NumPy, OpenCV, Pillow, el motor, la sesión y el módulo de actualizaciones se importan **en otro hilo** (la animación no se traba: hueco máximo de 18 ms). La interfaz y la ventana se arman en el hilo principal, atendiendo eventos entre parte y parte (`VentanaPrincipal(icono, al_avanzar=)`).
- **Mínimo de 0,7 s** a la vista. La foto de la sesión se espera hasta 4 s.
- **Al terminar** (`revelar`): la pantalla de carga se desvanece (`windowOpacity`) mientras la ventana, maximizada, aparece con un fundido y una "cortina" con su imagen que sube 14 px. Todo en 380 ms.
- **Después:** el tutorial sale 250 ms más tarde, cuando además ya se recuperó la sesión (`cuando_sesion_lista`). La búsqueda de actualizaciones arranca a los 1,5 s. "Abrir con…" una foto la suma a la tira recuperada; con un video se abre el editor de video.
- **Arreglo de paso:** al armar las secciones plegables (`controles.py`) y los pasos del modo fácil (`modo_facil.py`), 20 controles se hacían visibles antes de tener padre. Windows creaba y mostraba por un instante una ventana nativa suelta por cada uno. Ahora se muestran recién al estar en su lugar: la ventana se arma en 0,30 s en vez de 0,57 s, sin esas ventanitas.
- **Tiempos medidos** (desde que arranca el proceso; `NATURALSHOT_REGISTRO_ARRANQUE=<archivo>` los anota):

  | | Desde el código (`python -X faulthandler main.py`) | .exe compilado en una carpeta temporal |
  |---|---|---|
  | Pantalla de carga visible | 0,25-0,46 s (en 5 de 14 corridas, 1,3-2,4 s: el lanzador del `.venv` o el disco tardaron en arrancar el intérprete) | **0,26-0,39 s** |
  | Ya dibujada (medido adentro) | 0,30-0,44 s (dos corridas lentas: 0,67 y 1,4 s) | 0,31-0,37 s |
  | Motor importado | 0,54-0,73 s | 0,50-0,62 s |
  | Ventana armada | 0,95-1,2 s | 0,94-1,05 s |
  | App a la vista (sesión de 3 fotos de 2400 px) | 1,8-2,2 s | 1,8-2,0 s |

- **Splash nativo de PyInstaller: no se hizo.** Hace falta meter Tcl/Tk en el paquete (`tkinter` está excluido) y muestra una imagen fija sin la escala de Windows, así que el pase a la pantalla de Qt se vería como un salto. La de Qt ya aparece en un tercio de segundo.

### Recordar la sesión

Si se cierra la app con fotos en la tira, al volver a abrirla aparecen **las mismas fotos con sus ediciones** (estado completo e historial de cada una) y la misma foto abierta. El modo Fácil | Editor ya se guardaba aparte.

- **Archivo** (`celular_natural/sesion.py`, sin Qt): `%APPDATA%\NaturalShot PRO\sesion\sesion.pkl`.
  - Es un `pickle` con marca, versión de formato (`VERSION_FORMATO = 1`) y CRC32.
  - Guarda solo **rutas**, nunca imágenes.
  - Al leer, solo acepta las dataclasses del motor (y números de NumPy) y rearma cada una con sus campos actuales. Si algo no sirve (dañado, cortado, otra versión, una clase cambiada o una clase no permitida), queda como `sesion.bak`, se anota el motivo en `sesion.log` y se arranca limpio, con un aviso.
  - La escritura es atómica (temporal en la misma carpeta, `fsync` y `os.replace`, con reintentos si un antivirus lo tiene abierto). Los temporales que deja un corte se borran solos.
- **Cuándo se guarda:** 2 s después de cada paso nuevo del historial, deshacer o rehacer, agregar o quitar fotos o cambiar de foto (como mucho una vez cada 2 s), y al cerrar. Al cerrar, primero se registra lo pendiente. Se escribe en segundo plano (`QThreadPool` de un hilo + `Tarea`); al cerrar, en el momento. Si falla, avisa una sola vez.
- **Al abrir:** `ventana.activar_sesion()` (la llama `main.py`) lee el archivo y revisa en segundo plano qué fotos siguen en su carpeta. Después:
  1. arma la tira y abre la foto actual con `cambiar_a_foto` (si ya no está, la más cercana);
  2. carga las miniaturas con `_cargar_miniatura`;
  3. avisa con un **aviso flotante** abajo de la foto (`ui/aviso.py`): "2 fotos de la sesión anterior ya no están en su carpeta", con los nombres en la ayuda. Se va solo a los 12 s.

  Hasta que termina no se guarda nada, para no pisar la sesión anterior.
- **Pruebas sin riesgo:** las ventanas que no llaman a `activar_sesion` (todas las pruebas viejas) no leen ni escriben nada.
- **Empezar de cero:** botón de tacho a la derecha de la tira y "Quitar todas las fotos…" en el menú contextual. Pide confirmación (`quitar_todas_las_fotos`), deja la ventana como recién abierta (conserva preset y capas) y borra la sesión guardada. `VistaComparacion.vaciar()` vuelve a la invitación a abrir.
- **Actualizaciones:** con la sesión activa, al actualizarse ya no pregunta "lo que no exportaste se pierde" (`recuerda_sesion`).
- **Rendimiento:**
  - 20 fotos de 1600 px se recuperan, con sus 20 miniaturas, en 2,1 s, y la interfaz nunca queda trabada más de 40 ms. Cada miniatura se pone sin rearmar la tira (`TiraFotos.actualizar_miniatura`), y las del montaje se completan cuando llegan.
  - Guardar 20 fotos con 100 pasos y máscaras automáticas: 11 ms, 0,9 MB. Leer y validar: 0,1 s.

### Archivos

- **Nuevos:**
  - `celular_natural/sesion.py`, `celular_natural/ui/carga.py` y `celular_natural/ui/aviso.py`;
  - `tests/test_sesion.py` (16 pruebas).
- **Tocados:**
  - `main.py` (arranque por etapas);
  - `ui/ventana.py` (sesión, aviso, quitar todas y `al_avanzar`);
  - `ui/tira.py` (tacho, menú y `actualizar_miniatura`);
  - `ui/vista_comparacion.py` (`vaciar`), `ui/montaje.py` (`completar_miniaturas`) y `ui/estilo.py` (aviso y tacho);
  - `ui/actualizaciones.py` (no preguntar si la sesión se recuerda);
  - `ui/controles.py` y `ui/modo_facil.py` (las ventanas sueltas);
  - README y este archivo.
- **Copias de antes:** en `scratchpad\respaldo_sesion_carga\`.
- **No se tocaron:** `NaturalShot.spec`, `dist\` ni `build\`.

### Verificación

- **Pruebas:** pasan las **265** (249 + 16 de `tests/test_sesion.py`), con `QT_QPA_PLATFORM=offscreen .venv\Scripts\python -m unittest discover -s tests`. Incluyen la prueba de **punta a punta** con la ventana real:
  1. abrir 3 fotos y editarlas: preset, capa con zona, capa con máscara automática, recorte, giro, montaje, borrado, deshacer y rehacer, fondo desenfocado y volteo;
  2. dejar un cambio sin registrar, cerrar y abrir una ventana nueva con el mismo APPDATA;
  3. resultado: mismas fotos, misma foto actual, estados e historiales `==` y vista procesada idéntica, píxel por píxel, en las 3 fotos (y deshacer sigue andando).
- **Capturas offscreen revisadas** (en `scratchpad\trabajo_sesion\`):
  - la pantalla de carga en 8 momentos, al 100 % y al 150 %;
  - una hoja con el logo en distintas fases (respirar, brillo, estrellita);
  - el pase a la ventana a 1366 × 768, con la sesión recuperada, el aviso de la foto que falta y el tacho en la tira.
- **Arranques reales:** 14 con `python -X faulthandler main.py`, con APPDATA y .ini de prueba, una sesión de 3 fotos, el tutorial a la vista y cierre con WM_CLOSE. En 2 se pasó una foto como argumento: se sumó a la tira recuperada como foto actual. Ningún *access violation*, salida 0 y la sesión guardada al cerrar.
- **.exe de prueba:** compilado con `--distpath` y `--workpath` temporales, abrió 4 de 4 veces.
- **Limpieza:** no quedó nada en el `%APPDATA%` real (solo el `actualizaciones.log` de antes, sin cambios) ni claves nuevas en el registro.

### Limitaciones

- Durante el armado de la ventana (unos 0,3 s, en el hilo principal) la animación puede trabarse hasta unos 0,17 s; al mostrar la ventana, unos 0,13 s más.
- Con dos NaturalShot abiertos a la vez, queda la sesión del último que guardó.
- Las máscaras automáticas vuelven en su versión de lado 1024 (como cuando se pierden de la caché): en fotos grandes el borde puede quedar apenas más suave.
- Si la foto de un montaje ya no está, la que la usa muestra "Error al armar la foto" hasta quitar esa capa.
- Las fotos de la tira se mantienen en memoria, como al abrirlas a mano.

### Falta

- Recompilar el .exe y rehacer el zip (mejor con `publicar_version.bat`).
- Sumar al tutorial una línea sobre la sesión y el botón "Quitar todas".

## Editor de video ✅ (integrado el 12/10/2026)

**Botón "Video"** en la barra superior (ícono de película), que llama a `abrir_editor_video(self, estado_panel=self.panel_ajustes.estado())`. Arrastrar un video sobre el .exe también abre el editor. Doc completa en `VIDEO.md` y sección en el README. En `NaturalShot.spec` agregué los `hiddenimports` del editor de video y de `av`. Arreglé la caché de `mascaras.py` para que funcione con varios hilos.

## Editor de video: diseño

Ventana aparte, `celular_natural/ui/editor_video.py`, con motor en `celular_natural/motor/video.py` (usa PyAV `av==19.0.1`, video más audio).

- **Edición:** vista previa antes/después del cuadro actual y línea de tiempo con miniaturas. Entrada (I), salida (O), cortar en el cursor (S) y borrar tramos (Supr).
- **Filtro:** el mismo que en fotos. El ruido y el grano cambian en cada cuadro.
- **Exportación:** MP4 H.264 con audio (720p, 1080p u original), con progreso y botón para cancelar.

Velocidad medida: unos 2,8 cuadros/s a 1080p y unos 6 a 720p (30 s de video tardan unos 5 min o 2,5 min). En video, las capas van a todo el cuadro y las zonas no se usan.

## Ideas sugeridas que quedan para después

- ~~Galería de presets con miniaturas~~: hecha en el modo fácil.
- Preset A contra preset B lado a lado.
- Lupa al pasar el mouse.
- Favoritos y atajos 1–9.
- ~~Recordar la sesión al abrir~~: hecha (13/10, ver *Pantalla de carga y sesión*).
- Exportar a una carpeta fija.
- Histograma en vivo.
- Tema claro.
- Pantalla de inicio con fotos recientes.

## Reglas para quien siga el trabajo

- **Idioma:** interfaz y textos en español rioplatense ("vos", "tocá", "marcá"). Estilo del código existente: nombres y comentarios en español.
- **Archivos personales:** fuera del proyecto, tocar **solo** los archivos que el usuario nombra. Si hace falta otro, avisar antes.
- **Subagentes:** los que editan la interfaz van de a uno. En paralelo solo pueden crear archivos nuevos.
- **Antes de dar algo por terminado:** pruebas, capturas offscreen revisadas y recompilar el .exe.
- **Prohibido:** escribir datos falsos de cámara en el EXIF.
- **GitHub:** no crear repositorios, apps ni versiones, y no correr `--subir` ni `gh release`, sin el OK del dueño.

## Estructura rápida

```
main.py                         entrada
celular_natural/motor/          procesado (pipeline y presets), parametros, sensor, optica, textura, tono,
                                grano, compresion, mascaras, zonas (Zona/Recorte/pincel), montaje, desenfoque,
                                geometria, seleccion_auto, borrado, edicion (orden previo al filtro y conversión al girar)
celular_natural/actualizador.py actualizaciones: GitHub (device flow, releases), DPAPI, SHA-256 e instalador
celular_natural/sesion.py       sesión: fotos de la tira y sus ediciones entre una vez y otra (pickle seguro, escritura atómica)
celular_natural/ui/             ventana (tres columnas, selector Fácil | Editor, tira, historial, geometría, detecciones, clonado, sesión),
                                carga (pantalla de carga animada y pase a la ventana), aviso (aviso flotante),
                                actualizaciones (banner, conexión con GitHub, botón de versión),
                                modo_facil (cuatro pasos y galería de estilos con miniaturas),
                                vista_comparacion (herramientas: zona, recorte, enderezar, clonar),
                                controles (presets, capas, secciones), montaje, borrar, fondo, tira, historial, iconos, estilo
assets/                         icono.ico, logo.png, iconos/ (SVG de Lucide, licencia ISC)
tests/                          pruebas unittest
NaturalShot.spec / construir_exe.bat   empaquetado
publicar_version.bat / herramientas/publicar.py   versión nueva para publicar (--subir la sube a GitHub)
```

---

## Retomado el 13/10/2026 a las 10:10 (leer esto primero)

- **Modo Video integrado ✅ verificado:** pasan las **273 pruebas**. La de rendimiento de la sesión falló una vez por 2 ms (0,402 s contra 0,4 s) con la compu cargada; sola pasa, con un hueco de 60 ms. Capturas offscreen revisadas a 1366, 1600 y 1920 px, en los tres modos y con avisos, chip de exportación y video vacío (`scratchpad\modo_video\capturas\` de la sesión 4014f8d8).
- **Renombrar Purbea:** el sistema de permisos bloqueó `Rename-Item` (carpeta fuera del proyecto). Queda para el dueño. El acceso directo `Purbea\PhoneFleet.lnk` apunta a `Purbea\.venv\Scripts\pythonw.exe` con `Purbea\main.py`: después de renombrar, hay que cambiar esas rutas.
- **Motor de sonido ✅:** `motor/audio.py` (`AjustesAudio`, `LectorPCM`, `forma_de_onda`, `exportar_audio`) y bug de MKV arreglado (388 clics → 0). Pasan 300 pruebas.
- **Interfaz del sonido en Video ✅:** ver la sección "Sonido del video" de abajo. Pasan 314 pruebas y la suite tarda 286 s (antes 506 s). Las piezas reutilizables son `ui/forma_onda.py`, `ui/reproductor_audio.py` y `ui/panel_sonido.py`.
- **Pedido nuevo: modo Audio** (13/10). Voz limpia o hecha con IA → que suene grabada con un celular en un lugar real: fondos y sonidos generados, escenas, Mis sonidos, "bajarle lo de IA" e ida y vuelta con Video. Diseño aprobado en `docs/superpowers/specs/2026-10-13-modo-audio-design.md` y plan en `docs/superpowers/plans/2026-10-13-modo-audio.md` (tareas A-F). Las tareas A (`motor/ambientes.py`) y B (`motor/voz_natural.py`) están en curso en paralelo. C va después; D, cuando termine la interfaz del sonido en Video; después E y F.
- **Pedido nuevo: "Mejorar calidad" de video sin IA y cortes que desaparecen** (13/10). Diseño en `docs/superpowers/specs/2026-10-13-video-mejoras-design.md`. El motor (`motor/mejora_video.py`, multicuadro con flujo óptico + quitar bloques + Lanczos + enfoque sin halos) está en curso. También deja `herramientas/probar_mejora.py`, para probar con el video del dueño (pedirle la ruta exacta). La interfaz y lo de "cortes que desaparecen" van en `ui/editor_video.py` cuando termine la interfaz del sonido en Video. **Cortes que desaparecen ✅** (ver su sección, abajo); falta la interfaz de "Mejorar calidad".
- **Reparto entre dos sesiones (13/10, 16:30):** la sesión "a3" tiene las tareas C, E y F del modo Audio, Mejorar calidad (motor e interfaz), `NaturalShot.spec`, `dist\`, el zip y `Muestras de audio\`. La sesión "d0" hizo el tutorial (34 páginas, a las 16:04) y tiene la **Tarea D** completa (`ui/modo_audio.py`, `ventana.py`, `modo_video.py`, `modo_facil.py`, `estilo.py` y la extensión de `reproductor_audio.py`). Los botones de Sí y No ya salen en español (`main._traducir_qt`, `tests/test_traduccion.py`).
- **Versión intermedia compilada (13/10, 16:51):** `dist\` y el zip (123 MB) traen Video completo: sonido, cortes que desaparecen, Mejorar calidad y Sí/No en español. No traen el modo Audio. Se compiló desde una copia con los archivos de la interfaz de antes de la Tarea D (script en `scratchpad\compilar_intermedia.ps1` de la sesión 4014f8d8). En esa copia pasan las 478 pruebas (lo verificó la sesión "d0"). A, B, C y Mejorar calidad (motor e interfaz) quedaron aprobados por revisión.
- **En curso:** la Tarea D (sesión "d0") y la Tarea E parte 1 (subagente de "a3": `AudioExterno` en `motor/video.py`, los botones en la tarjeta Sonido, la señal `editarSonidoPedido` y `usar_sonido_externo`). Después: el pegamento en `ventana.py`, la F (spec, `AUDIO.md`, página del tutorial y versión final).
- **VERSIÓN FINAL COMPILADA (13/10, 23:05):** `dist\` y el zip (124 MB) traen todo: el modo Audio (Tarea D de "d0"), la ida y vuelta con Video (E: `ventana._editar_sonido_del_video` y `_volver_al_video_con_sonido`, con las pruebas `PruebasVentanaIdaYVuelta`), Mejorar calidad, el sonido y los cortes. Pasan 534 pruebas; la única falla fue de tiempo (`test_mejora_video` a 720p, 80,4 ms contra 80, con carga), y sola pasa. `NaturalShot.spec` ya tiene los `hiddenimports` del modo Audio. Documentación en `AUDIO.md` y el README. **Falta:** recompilar cuando "d0" entregue el tutorial con el modo Audio (rehace todas las capturas, ahora con 4 modos); por ahora va el de 36 páginas. Para después: `renombrar_en_escenas` público en `proyecto_audio.py` (D usa privados), la unificación de DSP duplicado (`ambientes` y `voz_natural`) y que la sesión guarde el estado del video.
- **Falta, en orden:** terminar lo de arriba, el tutorial (modo Video en la misma ventana, sonido, modo Audio, sesión y "Quitar todas"), recompilar el .exe y el zip.

## Sonido del video ✅ (13/10/2026, interfaz; solo desde el código)

Lo que pidió el usuario ("sacarle el audio, cortarlo, editarlo un poco, recortar"), en el modo Video. Detalle completo en `VIDEO.md`, sección *Sonido*.

- **Pista de sonido** debajo de las miniaturas: la forma de onda (4000 columnas, en un hilo, que se va dibujando mientras se lee) muestra cómo va a salir: volumen, fundidos, lo que no se exporta apagado y los silencios en rosa. Sin audio, una franja "Sin sonido". Tocarla mueve el cursor y elige el tramo.
- **Silenciar tramo (M)**, que alterna con **Devolver el sonido**. Actúa sobre el mismo tramo que Borrar (el elegido o, si no hay, el del cursor). Los silencios van en tiempo original.
- **Tarjeta Sonido** arriba de los ajustes del video (mismo acordeón): Quitar el sonido, Volumen 0-200 %, Normalizar, Fundido de entrada y de salida (como mucho la mitad del resultado; se acortan solos al cortar) y **Guardar solo el audio…** (M4A, WAV o MP3, en segundo plano, con progreso y Cancelar).
- **Se escucha al reproducir** (`QAudioSink`, 48 kHz estéreo int16, con `LectorPCM`) y la imagen sigue al sonido. Botón del parlante para silenciar la vista previa (se recuerda en `QSettings`, `video/sonido_vista_previa`). Sin salida de sonido, sin QtMultimedia o en "offscreen", anda igual sin sonido.
- **Exportar video** con `audio=ajustes`; con el sonido quitado, el MP4 sale sin pista y el resumen dice "sin sonido".
- **Deshacer y rehacer** de cortes y sonido juntos (mover un deslizador seguido es un solo paso).
- **Sesión:** no guarda el estado del video (solo fotos), así que no hizo falta sumar `AjustesAudio` a sus clases.
- **Pruebas que se colgaban:** las pruebas de interfaz completan el borrado de sus ventanas en el `tearDown` (`sendPostedEvents(DeferredDelete)`) y `VentanaPrincipal` saca sus filtros globales al cerrarse. Toda la suite pasó de **506 s a 286 s**. En `test_sesion`, construir la ventana pasó de 7,37 s a 0,23 s y el hueco máximo de la interfaz, de 403 ms a 40 ms (la prueba que fallaba por 2 ms ahora sobra).

### Archivos

- **Nuevos:**
  - `ui/forma_onda.py` (`PistaOnda`, `CargadorOnda`, `pico_aproximado`) y `ui/reproductor_audio.py` (`ReproductorAudio`): reutilizables para el modo Audio, sin depender del editor de video. API en `VIDEO.md`, *Piezas para un modo Audio*.
  - `ui/panel_sonido.py` (`PanelSonido`, también reutilizable).
  - `tests/test_sonido_ui.py` (14 pruebas).
  - Íconos Lucide `volume-2`, `volume-x`, `audio-lines` y `music` (copiados a mano con el formato de `lucide-static` 0.460.0).
- **Tocados:**
  - `ui/editor_video.py` (todo lo de arriba), `ui/ventana.py` (solo sacar los filtros globales al cerrar).
  - `NaturalShot.spec`: ya no excluye `QtMultimedia` ni `QtNetwork` (QtMultimedia lo importa) y suma los `hiddenimports`. Deja afuera el plugin de FFmpeg de Qt y el FFmpeg de PySide6 (unos 20 MB; los videos los lee PyAV).
  - Pruebas: `test_integracion`, `test_modo_facil`, `test_modo_video` (también la exportación falsa acepta `audio=`), `test_sesion`, `test_actualizador` y `test_video` (el borrado de las ventanas).
  - `VIDEO.md`, el README y este archivo.
- **Copias de antes:** `scratchpad\respaldo_sonido_ui\` (sesión 4014f8d8).
- **No se tocaron:** `motor/audio.py`, `dist\` ni `build\`.

### Verificación

- **Pruebas:** pasan las **314** (300 + 14). La suite completa dio además 2 errores de importación **ajenos**: `tests/test_ambientes.py` y `tests/test_voz_natural.py`, del modo Audio que se está haciendo en paralelo (en ese momento sus módulos todavía no existían).
- **Capturas offscreen revisadas**, a 1366 × 768 y 1600 × 900 (`scratchpad\sonido_ui\capturas\`): video con un tramo borrado y otro silenciado, guardando el audio, el diálogo de guardar, sonido quitado, vista previa silenciada y video sin sonido. Se corrigieron dos cosas:
  - el botón "Devolver el sonido" salía cortado a 1600 px: ahora la cabecera se compacta midiendo el texto más largo de cada botón que alterna, con un paso de nombres cortos ("Borrar", "Devolver sonido");
  - con el sonido quitado se pisaban dos etiquetas en la pista.
- **.exe de prueba** (compilado con `--distpath` y `--workpath` en el scratchpad, en 72 s; 298 MB contra 293 de antes):
  - abrió 3 de 3 veces directo en Video con el video cargado (título "charla_en_la_plaza.mp4 — NaturalShot PRO · Video"), con `QtMultimedia.pyd`, `Qt6Multimedia.dll` y `windowsmediaplugin.dll` cargados, y cerró con código 0;
  - una sonda compilada con las mismas exclusiones reprodujo el sonido congelada (volumen del dispositivo en 0): la posición avanza al ritmo del reloj, saltea lo borrado, y están M4A, WAV y MP3.
- **Arranques reales** con `python -X faulthandler main.py` (6, APPDATA e .ini temporales, sonido al 10 %): pasar a Video con un video, reproducir con sonido, saltar mientras suena, silenciar y volver a activar la vista previa, silenciar un tramo mientras suena, pausar y cerrar. Ningún *access violation* y código 0 en los 6.

### Falta

- Recompilar el `.exe` de verdad y rehacer el zip (mejor con `publicar_version.bat`).
- Sumar el sonido al tutorial.
- Probar con un video real largo de celular: solo se probó con videos sintéticos.
- Con auriculares inalámbricos la imagen puede ir un poco adelantada: no se compensa la demora del dispositivo.

## Cortes que desaparecen ✅ (13/10/2026, interfaz; solo desde el código)

Sección 2 de `docs/superpowers/specs/2026-10-13-video-mejoras-design.md`. Detalle en `VIDEO.md`, *Cortes que desaparecen*.

- **La línea de tiempo muestra el resultado**, como en CapCut: lo borrado y lo recortado no se dibujan y lo que sigue se corre. En el tiempo del resultado van la regla, el cursor, el tiempo y el cuadro del transporte, la duración, las miniaturas (cada tramo arranca su tira en la unión), la reproducción (el reloj avanza en el resultado), ← → J L Inicio Fin, los mensajes y la pista de sonido con sus silencios y fundidos.
- **Adentro todo sigue en tiempo original:** `EdicionVideo`, `EditorVideo.tiempo` (el cuadro que se ve), los silencios y la exportación (sin cambios).
- **Marquitas:** una costura rosa en cada unión donde falta algo (también en los extremos, si se recortó) y una pestaña debajo de las miniaturas. Tocarla, o el botón derecho cerca de la unión, abre un menú ("Borrado acá: 1,0 s") con **Recuperar lo borrado**. **R** recupera la más cercana al cursor. Todo entra al historial (Ctrl+Z y Ctrl+Y, también del borrado de siempre).
- **Supr ya no restaura** (lo borrado no se ve ni se elige) y **no se puede borrar todo**. El cursor nunca queda en algo borrado: va a la unión. Se sacó el aviso "No se exporta" del transporte. Los corchetes quedan en los extremos y recortan arrastrándolos hacia adentro.
- **Textos revisados:** botones, ayudas, atajos (Supr, R, I/O, Ctrl+Z), la ayuda de abajo (cambia si hay algo borrado), los mensajes de estado y los de "Nada para exportar".

### El mapeo resultado ↔ original (para "Mejorar calidad" y lo que siga)

En `motor/video.py`, funciones puras agregadas sin tocar lo existente:

- `MapaTiempo` (`de_edicion`, `identidad`, `duracion`, `a_resultado`, `a_original` —números o arreglos—, `visible`, `rangos_resultado`, `huecos`, `inicios_resultado`);
- `Hueco` (inicio, fin, en, principio, final);
- `segmentos_visibles(edicion)` y `recuperar_hueco(edicion, hueco)`.

En el editor: `EditorVideo.mapa` (con caché por edición), `tiempo_resultado`, `ir_a_resultado(r)`, `_visible(t)`, `_ultimo_visible()` y `recuperar(hueco=None)`. `LineaTiempo` y `PistaOnda` hablan en tiempo original y convierten al dibujar. `LectorPCM.original_de_resultado` (en `motor/audio.py`) hace lo mismo con muestras para el sonido; no se tocó.

### Archivos

- **Tocados:**
  - `motor/video.py` (solo agregados al final de la sección de edición);
  - `ui/linea_tiempo.py` (reescrita: es la clase de la línea de tiempo, solo la usa el editor de video);
  - `ui/forma_onda.py` (`PistaOnda(solo_resultado=True)` y `onda_en_resultado`; sin `solo_resultado`, igual que antes);
  - `ui/editor_video.py`.
- **Pruebas:**
  - nueva `tests/test_cortes.py` (13);
  - `test_video.py`: L después de un borrado salta en el resultado;
  - `test_sonido_ui.py`: lo borrado no se elige y M actúa sobre lo que se ve.
- **Documentación:** `VIDEO.md`, el README y este archivo.
- **Copias de antes:** `scratchpad\respaldo_cortes\` (sesión 4014f8d8).
- **No se tocaron:** `motor/audio.py`, `ui/ventana.py`, `ui/modo_video.py`, `ui/estilo.py`, `dist\` ni `build\`.

### Verificación

- **Pruebas:**
  - pasan las 13 nuevas y todas las de video, sonido y modo Video;
  - la suite completa corrió 390 pruebas en 367 s: fallaron 4, todas de otros subagentes que estaban escribiendo sus archivos en ese momento (`test_ambientes`: nivel de un fondo; `test_mejora_video`: igualdad cuadro a cuadro y una de velocidad con la PC cargada).
- **Capturas offscreen revisadas** a 1366 × 768 y 1600 × 900, con recortes ampliados (`scratchpad\cortes\capturas\`): dos tramos borrados con sus marquitas, el menú "Recuperar lo borrado", un silencio después de borrar y la entrada y la salida recortadas.
- **3 arranques reales** con `python -X faulthandler main.py` (APPDATA e .ini temporales, sonido al 5 %), en `scratchpad\cortes\arranque\`. Recorrido: pasar a Video con el selector, abrir, cortar y borrar, recuperar desde el menú, deshacer y reproducir con sonido cruzando la unión. El cursor va de corrido en el resultado (de 1,75 a 2,17 s en 0,4 s) y el sonido acompaña. Código 0, stderr vacío y ningún *access violation*.

### Limitaciones

- Las miniaturas siguen siendo 28 de todo el original (keyframes). Si queda muy poco del video, las celdas se ensanchan y, pasado el ancho natural, se repiten: no se piden miniaturas nuevas del resultado.
- La línea de tiempo no tiene zoom (no lo tenía antes).
- Para ver lo borrado hay que recuperarlo: no hay una vista "con todo" para mirar lo borrado sin traerlo.
- Falta el tutorial (PDF): todavía dice que lo borrado queda rayado.

## Mejorar calidad ✅ (13/10/2026, integración en Video; solo desde el código)

Sección 1 de `docs/superpowers/specs/2026-10-13-video-mejoras-design.md`, "Integración". El motor (`motor/mejora_video.py`) es de otro subagente y no se tocó. Detalle en `VIDEO.md`, *Mejorar calidad*.

- **Tarjeta "Mejorar calidad"** (`ui/panel_mejora.py`, ícono `sparkles`) debajo de Sonido, en el mismo acordeón: interruptor en la cabecera (se ve con la tarjeta cerrada, como en las secciones del filtro), barras **Quitar cuadraditos**, **Nitidez** y **Usar cuadros vecinos** (0-100 %) y la ayuda "No es IA… un video chico queda como un buen 720p, no como un 4K".
- **Vista previa:** el cuadro del cursor se ve mejorado con sus vecinos del mismo tramo (igual al archivo, bit a bit), con caché. La mejora espera a que el cursor se quede quieto (la vista rápida no mejora) y al reproducir se ve sin ella. "Antes" es el original agrandado simple (bicúbico).
- **Exportar:** con la mejora, 720p y 1080p agrandan ("1080p 1920 × 1080"), se sugiere 720p para un video chico y el resumen dice "mejorado a 1920 × 1080: tarda más, unos 2 min". `exportar_video(..., mejora=)`; con `None` o apagada, el camino de siempre.
- **Orden y tramos:** decodificar → mejorar → filtro → codificar. `VentanaVecinos` (la ventana de `MejoradorVideo`) corta en cada tramo: los vecinos nunca cruzan un borrado.
- **Hilos (medido):** el coordinador pidió mejorar en serie; medí las dos formas con la misma carga y varias tandas. Sin filtro, 3 a la vez es más rápido (1080p: 32 s contra 49); con el filtro de la app, en serie (1080p: 158 s contra 183; 720p: 64 contra 66). La exportación empieza de a uno y pasa a 3 solo si la mejora es lo lento. Mismo resultado de las dos maneras (probado cuadro por cuadro).
- **Tiempos** (video de prueba de 10 s, 640×360, preset principal, PC cargada): sin mejora 14,5 s; con la mejora a 720p, 64 s; a 1080p, 158 s.
- **Deshacer y rehacer:** historial en triples (edición, sonido, mejora); una barra arrastrada es un paso.
- **Arreglos de la revisión del sonido y los cortes** (pedidos por el coordinador, con prueba cada uno):
  1. juntar pasos de deshacer: después de volver al valor de antes ya no se pega al paso anterior, y solo se junta con el paso que abrió el gesto;
  2. `con_limites` acepta dejar justo un cuadro (`< cuadro - 1e-9`);
  3. arrastres cuyo soltar se pierde (línea de tiempo y pista): se cortan con un movimiento sin botón, al salir sin botón o al perder el foco;
  4. al deshacer o rehacer, el tramo elegido se vuelve a buscar por inicio y fin (si no está, no queda nada elegido);
  5. el pico de "Normalizar": las mediciones que ya no hacen falta no empiezan o se cortan, y la clave lleva la ruta.
- **Arreglo propio:** "cuadro 121 de 300" se ensanchaba al avanzar y cortaba el tiempo del transporte ("0:10,0("): ahora reserva el ancho del texto más largo.

### Archivos

- **Nuevos:** `ui/panel_mejora.py` y `tests/test_mejora_ui.py` (18 pruebas).
- **Tocados:** `motor/video.py` (agregados: `tamano_salida(..., agrandar)`, `tamano_lectura`, `tiempos_vecinos`, `VentanaVecinos`, `_Cupo`, `exportar_video(..., mejora=)`, `ResultadoVideo.mejorado` y `.hilos_mejora`; y el arreglo de `con_limites`), `ui/editor_video.py`, `ui/linea_tiempo.py` y `ui/forma_onda.py` (solo el arrastre perdido), `VIDEO.md`, el README y este archivo.
- **Copias de antes:** `scratchpad\respaldo_mejora_ui\` (sesión 4014f8d8).
- **No se tocaron:** `motor/mejora_video.py`, `ui/ventana.py`, `ui/estilo.py`, `ui/modo_video.py`, `sesion.py`, `motor/audio.py`, `dist\` ni `build\`.

### Verificación

- **Pruebas:** pasa toda la suite, **465 pruebas en 476 s** (`QT_QPA_PLATFORM=offscreen`), con las 18 nuevas. Ninguna falló, tampoco las de otros subagentes.
- **Sin la mejora, idéntico a antes:** el mismo video exportado con el `video.py` de antes y con el de ahora (`mejora=None`) da el mismo archivo, byte por byte (mismo SHA-256).
- **Capturas offscreen revisadas** a 1366 × 768 y 1600 × 900 (`scratchpad\mejora_ui\capturas\`, sesión 4014f8d8), con un video sintético de 640×360 con texto, líneas y textura, comprimido fuerte: la tarjeta apagada y prendida, "Lado a lado" a 1080p entero, al 100 % sobre el texto y al 200 % sobre las líneas, recortes ampliados del antes y el después (con y sin filtro) y las opciones de exportar con y sin la mejora. Se corrigió el tiempo cortado del transporte (ver arriba).
- **2 arranques reales** con `python -X faulthandler` y `main.main()` (APPDATA e .ini en `scratchpad\mejora_ui\arranque\`, sonido al 5 %): pasar a Video con el selector, abrir, prender la mejora (sugiere 720p), elegir 1080p, ver el cuadro mejorado (1,3 s), reproducir con sonido, pausar (mejorado otra vez en 1,3-1,4 s), exportar a 1080p (60 cuadros en 26,5 y 28,7 s; el resumen decía "menos de un minuto"; el MP4 sale de 1920×1080, con audio y 2,0 s) y cerrar. Código 0, stderr vacío y ningún *access violation*.

### Limitaciones

- No inventa detalle: a 1080p se ve más grande, no más nítido que a 720p.
- Al reproducir se ve sin la mejora (aparece al pausar).
- En videos de cuadros por segundo variables, la vista previa elige los vecinos por tiempo y puede tomar uno distinto del que usa la exportación.
- La estimación del resumen sale de un solo cuadro de la vista previa: es aproximada.
- Falta sumarla al tutorial y recompilar el .exe.

## PAUSA 13/10/2026 03:35: trabajo a medias (lo de abajo ya quedó viejo)

El usuario tuvo que irse y se frenaron los dos subagentes a mitad de camino.

1. **Modo Video integrado en la misma ventana**
   - Pedido: selector "Fácil | Editor | Video", sin ventana aparte.
   - Si se abre o se suelta un video en fotos, aviso "Esto es un video: lo abrimos en el modo Video" y cambia de modo; con una foto en Video, lo mismo al revés.
   - La exportación sigue si cambiás de modo. Atajo Ctrl+Shift+V.
   - Estado: **frenado a mitad**. Ya existían `tests/test_modo_video.py` y cambios en `ui/ventana.py` y `ui/editor_video.py`, modificados por última vez a las 03:33.
   - Al volver: compilar, correr las pruebas (`QT_QPA_PLATFORM=offscreen .venv/Scripts/python -m unittest discover -s tests`, antes eran 265), terminar lo que falte, sacar capturas a 1366 y 1600 px, y después recompilar el exe y el zip.
   - El agente guardó copias de los archivos originales en una carpeta temporal propia.
   - El PDF del tutorial dice que el video "se abre en una ventana aparte": hay que actualizarlo.
2. **Edición básica del sonido del video**
   - Pedido del usuario: "sacarle el audio, cortarlo, editarlo un poco, recortar".
   - Plan:
     - motor nuevo `celular_natural/motor/audio.py` con `AjustesAudio` (quitar, volumen 0–2, normalizar, fundido de entrada y de salida, silencios por tramo en tiempo original);
     - forma de onda en streaming;
     - lector PCM para escuchar la vista previa (`QAudioSink`);
     - `exportar_audio` en M4A, WAV y MP3 si PyAV trae libmp3lame;
     - pruebas en `tests/test_audio.py`.
   - Después, integrar en la interfaz:
     - pista con forma de onda en la línea de tiempo y botón "Silenciar tramo";
     - sección "Sonido" con quitar, volumen, normalizar, fundidos y "Guardar solo el audio";
     - sonido en la vista previa con botón de silenciar;
     - aplicar `AjustesAudio` en la exportación de `motor/video.py`;
     - sacar `PySide6.QtMultimedia` de `EXCLUIR` en `NaturalShot.spec`.
   - Estado: **el motor recién arrancaba**. Revisar si `motor/audio.py` y `tests/test_audio.py` quedaron a medias.
3. **Renombrar `Escritorio\Purbea` a `PhoneFleet`**
   - Falló dos veces porque otro proceso tiene la carpeta abierta.
   - Cuando se pueda, renombrar y corregir `PhoneFleet.lnk`.
4. Lo bloqueado del auto-update y del tutorial sigue igual (ver arriba).

**Actualización de la pausa (03:37)**
- **Modo Video:** el agente estaba casi terminado: corría toda la suite de pruebas y le faltaba escribir su sección en este archivo. `ventana.py`, `editor_video.py` y `main.py` **compilan bien**. Al volver: correr las pruebas, sacar las capturas y revisar.
- **Audio:** el agente todavía no había creado `motor/audio.py`; estaba probando y escribiendo sus prototipos aparte. **Encontró un bug real:** al exportar a **MKV** un tono continuo, el audio sale con unos 365 saltos o clics en 3 s; en MP4 sale bien. Revisar `_EscritorAudio` y `_ubicar_audio` en `motor/video.py` con contenedores MKV y WebM.

## Tutorial actualizado ✅ (13/10/2026 16:04, sesión paralela "d0")

Se trabajó en paralelo con otra sesión de Claude Code. Esta se encargó del tutorial y de una revisión; la otra, del modo Audio, "Mejorar calidad" y la compilación.

- **PDF:** `Tutorial\NaturalShot - Guía de uso.pdf` (personal), `Tutorial\tutorial_compartible.pdf` y `assets\tutorial.pdf` (copia de la personal). Ahora tienen **34 páginas** (antes 29).
- **Qué cambió:**
  - sección 3: "La sesión se recuerda" y "Quitar todas las fotos";
  - sección 16, Modo Video, rehecha: en la misma ventana, con el aviso, los cortes que desaparecen y el chip de exportación;
  - sección 17, nueva: Sonido del video;
  - sección 18, Actualizaciones: ya no dice que se pierde lo no exportado;
  - sección 19, Atajos: con los del video;
  - todas las capturas, rehechas con la app del 13/10.
- **Falta:** las páginas de "Mejorar calidad" y del modo Audio, cuando estén estables. La tarjeta "Mejorar calidad" ya sale en la captura de Video, pero el texto no la menciona.
- **Privacidad:** la compartible pasó `verificar_sin_foto.py` (0 páginas con la foto). Los videos de prueba tienen una voz sintética, sin grabaciones reales.
- **Scripts:** en el scratchpad de la sesión 57d45be4, `guia5\` (con `capturar_todo.sh personal|compartible`), y `guia2\` con las fotos derivadas. Copia de los PDF de antes en `respaldo_tutorial\`.
- **Revisión de solo lectura** del sonido en Video y de los cortes: ningún crítico, 1 importante (deshacer junta pasos que no corresponden después de volver un control a su valor) y 4 menores. Los pasé a la otra sesión, que los arregla junto con "Mejorar calidad".
- **Bug encontrado:** las preguntas de sí o no muestran "Yes / No" en inglés, porque no se carga ningún QTranslator. Son 5 `QMessageBox.question`. También se lo pasé a la otra sesión.

## Ida y vuelta Video ↔ Audio, lado del video ✅ (13/10/2026, Tarea E parte 1; solo desde el código)

Detalle en `VIDEO.md`, *Sonido de otro archivo y modo Audio*. Falta conectarlo en `ventana.py` (lo hace el coordinador).

- **Motor** (`motor/video.py`, solo agregados): `AudioExterno(ruta, alineado="original" | "resultado")` (validado, con pickle) y `exportar_video(..., audio_externo=)`, compatible hacia atrás. "original": los mismos tramos y `AjustesAudio` del video, con otro archivo. "resultado": voz en off desde el 0 del resultado, cortada al largo o completada con silencio, con los silencios pasados al resultado (`LectorDesdeCero`, el mismo para exportar y escuchar). Además: `validar_audio_externo`, `silencios_en_resultado`, `sonido_a_medir`, `exportar_sonido`, `carpeta_temporal`, `ruta_temporal_sonido` y `limpiar_temporales`.
- **Editor** (`ui/editor_video.py`, `ui/panel_sonido.py`): en la tarjeta Sonido, el renglón "Sonido: …", **Editar el sonido en el modo Audio** (WAV del original completo en `%APPDATA%\NaturalShot PRO\temporal`, con progreso y Cancelar; emite `editarSonidoPedido(wav, video)`), **Cambiar el sonido por…** y **Volver al original**. Método `usar_sonido_externo(ruta, alineado)`. El historial guarda `EstadoEditor(edicion, audio, mejora, externo)`. La pista (`forma_alineada` en `ui/forma_onda.py`), la vista previa, "Guardar solo el audio" y la exportación usan el externo. Al abrir el editor se borran los temporales de más de 7 días.
- **Para el modo Audio** (pedido del coordinador): `PanelSonido(solo_volumen=True)`; en `LineaTiempo`, `alto_tira`, `rect_tira()` y el gancho `dibujar_tira(p, rect)`; en `PistaOnda`, `x_de(t)` y `tiempo`. No se renombró ningún privado (`_pista`, `_dibujar_tira`, `_edicion`, `_mapa`, `_x`, `_tiempo`).
- **Arreglos de las capturas** (pedidos por el coordinador):
  - la columna derecha de Video cortaba unos 13 px: el subtítulo de "Mejorar calidad" medía 186 px y ensanchaba todo. Se cambió por "Sin IA: cuadraditos y nitidez" y los títulos de las dos tarjetas ya no ensanchan (`no_ensanchar` en `ui/panel_mejora.py`). Ahora miden 304 px, como las secciones del filtro;
  - el resumen de exportar ya no parte la medida en dos renglones (espacios duros);
  - con la mejora apagada, 1080p y 720p dicen "con la mejora" en lugar del tamaño del original, y la ayuda explica "Prendé Mejorar calidad para agrandar a 1920 × 1080".
- **Pruebas:** nueva `tests/test_ida_y_vuelta.py` (28: 16 del motor y 12 del editor). En `test_mejora_ui.py` se actualizaron dos comprobaciones por los arreglos de arriba (espacios duros y "con la mejora").
- **Copias de antes:** `scratchpad\respaldo_tarea_e\` (sesión 4014f8d8). Capturas en `scratchpad\tarea_e\capturas\`.
- **No se tocaron:** `ventana.py`, `modo_video.py`, `modo_facil.py`, `estilo.py`, `reproductor_audio.py`, `modo_audio.py`, `motor/audio.py`, `proyecto_audio.py`, `sesion.py`, `dist\` ni `build\`.
- **Limitaciones:** la sesión no guarda el sonido externo (no guarda nada del video); "Editar el sonido en el modo Audio" siempre parte del sonido del video, aunque ya haya un sonido editado; el WAV que vuelve del modo Audio tiene que tener el largo del original (sin cortes propios del modo Audio); con "original" y un externo más corto que el video, el fundido de salida cae al final del externo (igual en la vista previa y en el archivo).

## Modo Audio: pantalla e integración (Tarea D) ✅ (13/10/2026 22:52, sesión paralela "d0")

- **Archivos nuevos:**
  - `ui/modo_audio.py` (`EditorAudio`): estado, historial, reproducción, exportación, sesión y la ida y vuelta con Video;
  - `ui/pistas_audio.py`: onda grande con zoom, la línea de 3 pistas (Voz, Fondo y Sonidos arrastrables);
  - `ui/paneles_audio.py`: escenas, ¿Cómo se grabó?, Cuánto, capas, sonidos, Mis sonidos y `PanelSonidoAudio`;
  - `tests/test_modo_audio.py` (25 pruebas);
  - 18 íconos Lucide.
- **Archivos tocados:**
  - `ui/ventana.py`: selector de 4 modos, Ctrl+Shift+A, ruteo de audios, chip, sesión del audio (queda pendiente hasta entrar a Audio, sin cargar PyAV antes) y "Quitar todas" que no borra el audio;
  - `ui/modo_video.py`: `es_audio`, filtros y `ChipExportacion(tipo="audio")`;
  - `ui/modo_facil.py`: `AUDIO`;
  - `ui/estilo.py`;
  - `ui/reproductor_audio.py`: `reproducir_lector` y `hay_salida`, compatibles.
  - Copias de antes en el scratchpad de la sesión 57d45be4, en `respaldo_modo_audio\`.
- **Para la Tarea E:** `abrir_desde_video(wav, video)` bloquea los cortes y muestra la franja; `volver_al_video()` exporta un WAV a `%APPDATA%\NaturalShot PRO\temporal` y emite `volverAlVideoPedido(wav, video)`. La otra sesión lo conectó en `ventana.py` (`tests/test_ida_y_vuelta.py`).
- **Revisión de código** (solo lectura): sin críticos. Se arreglaron:
  - 2 importantes: armar o cambiar lo que suena trababa la interfaz (ahora va en un hilo propio, sin cortar el sonido); y renombrar o borrar Mis sonidos mientras se exporta (ahora no se puede);
  - 8 menores: corchetes que borraban todo, semillas repetidas, una carrera con "Quitar todas", escenas propias al renombrar, el aviso si no suena, "Escuchar 3 s" que no se cortaba, "falta" desactualizado y la vuelta al video con otro audio abierto.
- **Verificación:**
  - `test_modo_audio` + `test_ida_y_vuelta`: 55 OK;
  - las tandas de sonido, video, fácil y sesión: OK;
  - capturas a 1366 y 1600 revisadas (scratchpad 57d45be4, `modo_audio\capturas\`);
  - arranque real con `main.py`: entró a Audio, sonó, aplicó una escena y exportó a WhatsApp, con código 0.
- **Limitaciones:**
  - al renombrar, las escenas propias se actualizan con funciones privadas del motor (`_leer_escenas` y `_escribir_escenas`);
  - un archivo de Mis sonidos recién agregado puede tardar un instante en sonar la primera vez.
- **Tutorial con el modo Audio ✅ (23:5x):** 43 páginas en las dos ediciones y en `assets\tutorial.pdf`.
  - Secciones nuevas: 18 Modo Audio (págs. 31-36, con la ida y vuelta con Video) y los atajos de Audio.
  - Todas las capturas, rehechas con el selector de 4 modos.
  - La compartible pasó los dos verificadores de privacidad.
  - La voz es solo `Muestras de audio\3 - Escenas\Voz de prueba.wav`.
  - Copias de las de 36 páginas en el scratchpad 57d45be4, `respaldo_tutorial_36\`.
- **Arreglo de último momento:** "Guardar como escena" ahora marca la escena recién guardada, aunque sea igual a una de la app.
  - Prueba: `test_guardar_igual_a_una_de_la_app_marca_la_propia`.
  - Verificación: `test_modo_audio`, `test_ida_y_vuelta` y `test_sesion`, 72 OK.
- **Para la próxima (cosmético):**
  - nombres largos cortados con "…" en la galería de fondos y en bloques angostos de Sonidos;
  - el menú "Agregar en el cursor" es más ancho que su botón.

## NaturalShot Lite: edición ✅ (14/10/2026, Tarea L0)

Plan: `docs/superpowers/plans/2026-10-14-naturalshot-lite.md`. La PRO no cambió: por defecto la edición es "pro".

- **Cómo se decide** (`celular_natural/edicion.py`): la variable `NATURALSHOT_EDICION` ("lite" o "pro"); si no está, en el .exe, un `edicion.txt` en `_internal` (lo pone el `.spec`) o junto al ejecutable; si no hay nada, "pro". Las funciones (`es_lite`, `nombre_app`, `insignia`, `carpeta_datos`, `organizacion_qsettings`, `ruta_logo`, `ruta_icono`, `ruta_recurso`) vuelven a mirar la variable cada vez.
- **En Lite:**
  - selector Fácil | Editor, sin botón Video, sin Ctrl+Shift+V ni Ctrl+Shift+A y sin chips;
  - un video o un audio (soltado, abierto o con "Abrir con…") no se abre y avisa "NaturalShot Lite es solo para fotos"; las fotos que vienen junto sí entran;
  - Abrir ofrece solo imágenes;
  - título, insignia LITE (violeta), pantalla de carga, logo, ícono, tutorial (`tutorial_lite.pdf` si existe) y "Acerca de" de la Lite;
  - datos en `%APPDATA%\NaturalShot Lite` (sesión y presets) y QSettings `("NaturalShot", "NaturalShot Lite")`;
  - actualizaciones apagadas (sin banner, sin GitHub y sin escribir el registro).
- **Archivos nuevos:** `celular_natural/edicion.py`, `NaturalShot Lite.spec`, `construir_lite.bat`, `ejecutar_lite.bat`, `herramientas/LEEME_lite.txt` y `tests/test_edicion_lite.py` (17 pruebas).
- **Archivos tocados:** `__init__.py`, `main.py`, `sesion.py`, `ui/ventana.py`, `ui/modo_video.py`, `ui/modo_facil.py`, `ui/carga.py`, `ui/actualizaciones.py`, `ui/presets_usuario.py`, `ui/tutorial.py`, `ui/vista_comparacion.py` (la invitación no habla de videos) y `herramientas/publicar.py` (`armar_zip` con carpeta y LEEME opcionales). Copias de antes en el scratchpad de la sesión 4014f8d8, `respaldo_l0\`.
- **Paquete:** `construir_lite.bat` compila en `dist_lite\` (no toca `dist\`, `build\` ni el zip de la PRO), arma `NaturalShot Lite - para otra PC.zip` y crea `NaturalShot Lite.lnk`. El `.spec` excluye `av`, QtMultimedia y los módulos de video y audio; quedan `motor/audio.py`, `proyecto_audio.py` y `voz_natural.py`, porque los importa la sesión y ninguno carga PyAV al importarse. También quedan QtNetwork (lo necesita `Qt6Pdf.dll`, el tutorial) y los plugins `qgif`, `qjpeg` y `qico`.
- **Tamaño:** la carpeta Lite pesa 229 MB y la PRO, 299 MB (70 MB menos: `av.libs` 65 MB, `av` y Qt6Multimedia). El zip Lite pesa 96,5 MB y el de la PRO, 125,5 MB.
- **Verificación:**
  - suite completa: 634 OK, en 506 s;
  - el zip, descomprimido en una carpeta temporal y con un APPDATA temporal, abre como Lite sin la variable, no carga DLL de video ni de sonido, guarda la sesión en `NaturalShot Lite\` y cierra con código 0;
  - capturas offscreen a 1366 y 1600 px (Fácil, Editor, aviso y carga), revisadas: scratchpad 4014f8d8, `l0\capturas\`.
- **Limitaciones:**
  - la PRO sigue escribiendo sus temporales de audio y su registro de actualizaciones en `NaturalShot PRO` (no se tocó);
  - el `tutorial_lite.pdf` todavía no existe: la Lite lleva el tutorial de siempre, con las páginas de Video y Audio, y se va a incluir solo cuando esté al recompilar;
  - la Lite no tiene repositorio para actualizarse.

## Capas ✅ (14/10/2026, Tarea L1b: interfaz de capas, etapa 1)

Plan: `docs/superpowers/plans/2026-10-14-naturalshot-lite.md`. Detalle para usarlo y por dentro: **`LITE.md`**. Es el mismo código para la Lite y la PRO (la PRO sigue andando, con Video y Audio).

**Cambio de diseño del dueño (durante la tarea):** las capas no van en el Editor sino en un **modo nuevo, "Photoshop"**, solo en la Lite: **Fácil | Editor | Photoshop**, Ctrl+Shift+P para ir y volver, recordado en QSettings. En Photoshop la vista muestra la composición **sin el filtro** (sin Antes/Después; "Ver con el filtro" lo previsualiza); en Fácil y Editor el filtro va arriba de la composición y su "Antes" es la composición sin filtro. El Editor volvió a ser como antes (con "Efectos"). Distribución tipo Photopea: a la izquierda una barra vertical angosta con Mover (V), Rectángulo, Elipse, Lazo y Pincel (estas cuatro pintan la máscara de la capa elegida) y una tarjeta con sus opciones (se ve / se oculta, tamaño y dureza del pincel); en el centro la vista y la tira; a la derecha Capas (con "Filtro celular natural" arriba, bloqueado y atenuado) e Historial (el mismo, que se muda de columna); arriba Abrir, Guardar proyecto, deshacer/rehacer, Agregar imagen y el zoom. Soltar una imagen en Photoshop la agrega como capa (en Fácil y Editor, con Ctrl). **La PRO no tiene el modo** y queda como estaba: ahí **Ctrl+S sigue exportando**; en la Lite, Ctrl+S guarda el proyecto y Ctrl+Shift+E exporta (prueba para cada edición). Lo de abajo se lee con eso en mente.

- **Documento por foto:** cada foto de la tira tiene su `Documento` (Foto + imágenes + "Celular natural") en su estado (`estado["documento"]`) y un `AlmacenImagenes` compartido en la ventana. La capa "Foto" es lo que arma `_recalcular_fuentes` más el desenfoque de fondo; el filtro de siempre es la función `filtro` de `componer` (`procesar_con_capas` en `ui/ventana.py`). **Sin capas** (documento "trivial") no se llama a `componer` y el estado no lleva documento: vista, exportación, historial y sesión iguales a antes, bit a bit (prueba). Vista previa en los hilos de siempre con una `CacheComposicion` por escala y `clave_foto`/`clave_filtro`; exportar a escala 1 con `cache=None`.
- **Panel "Capas"** (`ui/panel_capas.py`): en la columna derecha del modo Photoshop, arriba del Historial (en 768 px se ven unas 7 filas). Lista de abajo hacia arriba, ojo, miniatura (y la de la máscara), nombre (doble clic), fusión y opacidad, candado; fusión y opacidad de la elegida; agregar imagen, duplicar, máscara, mover, subir, bajar, borrar y arrastrar para reordenar. Los `ValueError` del motor salen como aviso.
- **"Capas" → "Efectos"** en `ui/controles.py`, el historial ("Efecto agregado…"), los textos de la ventana, del modo Fácil y del editor de video. Por dentro sigue siendo `estado["capas"]`.
- **Mover / Transformar** (`ui/herramienta_transformar.py`, V o el primer botón de la barra de herramientas del modo Photoshop): manijas en esquinas y lados, rotación (manija redonda o afuera de una esquina, Mayús de a 15°), mover (Mayús: derecho), flechas de a 1 px (10 con Mayús), voltear, Enter aplica (un paso) y Esc cancela. **Escalar siempre mantiene la proporción** (el motor tiene una sola escala; como Photoshop moderno); Alt escala desde el centro.
- **Máscaras:** agregar (blanca), pintar con rectángulo, elipse, lazo o pincel de la barra de herramientas, en modo "se ve" o "se oculta" (la maquinaria de zonas de siempre, `_DestinoMascara`; si la capa no tenía máscara, se crea al pintar), Mostrar todo, Ocultar todo, Invertir y Quitar.
- **Agregar imágenes:** diálogo ("Agregar imagen"), soltar sobre la foto en Photoshop, o Ctrl+arrastrar en Fácil y Editor (sin Ctrl, a la tira); centradas con `transformacion_ajustada`; tope `MAX_PIXELES_IMAGEN`; en segundo plano; pasadas a sRGB.
- **Proyecto `.nslite`:** en la Lite, Ctrl+S (la primera vez pregunta), Ctrl+Shift+S, Abrir/arrastrar/"Abrir con…"; **exportar es Ctrl+Shift+E** en la Lite (en la PRO, Ctrl+S sigue exportando). En `extra`: la foto original (ruta, nombre y tamaño) y el estado de la edición en JSON (`ui/documento_capas.py`, con etiquetas `$tupla`, `$bytes` y `$clase`; todo lo de hoy se puede pasar). Sin la foto original, se abre sobre un fondo blanco del mismo tamaño, con aviso.
- **Girar, voltear, enderezar y recortar** llevan las capas y sus máscaras al marco nuevo (`documento_capas.convertir_documento`).
- **Historial:** cada cambio de capas es un paso; un gesto del deslizador de opacidad es un paso.
- **Sesión:** `Documento`, `Capa` y `Transformacion` en `CLASES`; las imágenes y máscaras como PNG en `sesion\imagenes\<id>.png` (antes que el pickle; las que sobran se borran después). Las sesiones viejas se leen igual. `FotoGuardada.proyecto` recuerda el `.nslite`.
- **Fácil:** no muestra capas; el estilo es la capa de ajuste; la vista y "Exportar foto" componen y la nota dice "capas".
- **Arreglo de paso:** el filtro de la barra espaciadora (mostrar "Antes") se comía los espacios al escribir en un campo de texto de la ventana (el nombre de una capa): ahora no actúa sobre campos de texto ni números.

### Archivos

- **Nuevos:** `ui/panel_capas.py`, `ui/herramienta_transformar.py`, `ui/documento_capas.py` (lo que une el documento con la edición de hoy, sin Qt), `tests/test_capas_ui.py` (27 pruebas, en la Lite), `LITE.md` y 6 íconos de Lucide (`lock`, `lock-open`, `arrow-up`, `arrow-down`, `move`, `image-plus`).
- **Tocados:** `ui/ventana.py`, `ui/vista_comparacion.py`, `ui/controles.py`, `ui/historial.py`, `ui/modo_facil.py`, `ui/estilo.py`, `ui/iconos.py`, `ui/editor_video.py` (solo textos), `sesion.py`, `tests/test_integracion.py` y `tests/test_modo_facil.py` (solo textos), `tests/test_edicion_lite.py` (el selector de la Lite ahora tiene Photoshop), README y este archivo. Copias de antes en el scratchpad de la sesión 4014f8d8, `respaldo_l1b\`.
- **No se tocaron:** `motor/fusion.py`, `motor/documento.py`, `motor/proyecto_lite.py`, `ui/tutorial.py`, `Tutorial\`, `assets/tutorial*.pdf`, `dist\` ni `build\`.

### Verificación

- **Pruebas:** `tests/test_capas_ui.py` con la ventana real en la Lite (modo Photoshop: selector, Ctrl+Shift+P, distribución, vista sin filtro y "Ver con el filtro", filtro sobre la composición en Fácil y Editor, soltar como capa; Ctrl+S por edición; regresión bit a bit, panel, transformar con `QTest`, historial, girar y recortar, `.nslite`, sesión, Fácil y Ctrl+arrastrar). **Suite completa en PRO: 673 OK en 488 s** (incluidas `test_edicion_lite`, `test_modo_video` y `test_modo_audio`).
- **Capturas** offscreen en Lite a 1366 × 768 y 1600 × 900 (modo Photoshop con 3 capas, multiplicar, máscara pintada, transformar con manijas, pincel de máscara, "Ver con el filtro"; Editor con "Efectos" y Fácil, los dos con la composición y el filtro), revisadas: scratchpad 4014f8d8, `l1b\capturas\`.
- **Arranque real** en Lite (plataforma de Windows, `-X faulthandler`, APPDATA e `.ini` temporales), 3 veces en dos procesos, en el modo Photoshop: abrir una foto, agregar una capa, moverla con el mouse, guardar el `.nslite`, cerrar; abrir de nuevo (sesión recuperada), abrir el proyecto y exportar (exportación = vista del Editor). Ningún *access violation*, salida 0.
- **Lite compilada** con `construir_lite.bat`: `dist_lite\NaturalShot Lite` de 226 MB, `NaturalShot Lite - para otra PC.zip` de 94,1 MB, sin `av` ni Qt6Multimedia, y `NaturalShot Lite.lnk`. El zip, descomprimido en el scratchpad, abrió un `.nslite` pasado como argumento, guardó la sesión con la imagen de la capa y cerró con código 0.

### Falta

- Un incidente durante la tarea: una primera corrida de `construir_lite.bat` chocó con una NaturalShot Lite abierta desde `dist_lite\` (no la abrió esta tarea) y alcanzó a borrar los íconos de `_internal\assets`; se restauraron enseguida desde el zip de esa misma compilación. Con la Lite ya cerrada, se volvió a compilar bien.
- Sumar las capas al tutorial (lo hace otra sesión).

## Lite Etapa 2, U1 ✅ (14/10/2026: el modo Photoshop en su módulo, Nuevo de verdad, menú, herramientas, Propiedades, grupos e imán)

Diseño: `docs/superpowers/specs/2026-10-14-lite-etapa2-photopea-design.md`; plan: `docs/superpowers/plans/2026-10-14-lite-etapa2.md`. Detalle para usarlo: **`LITE.md`** ("Etapa 2, U1"). La PRO no cambia (no tiene el modo).

- **Módulo propio:** `ui/modo_photoshop.py` (como `modo_audio.py`): menú, barra de herramientas y colores, barra de opciones, columnas, controlador de la vista, Nuevo, operaciones de Imagen y Capa, transformación libre, kit de flyers y máscaras. `ventana.py` conserva los nombres de siempre como delegados (`alternar_transformar`, `nuevo_lienzo`, `agregar_texto`, `_transformando`…). Piezas nuevas: `ui/propiedades_ps.py`, `ui/iman.py`, `ui/dialogos_ps.py`.
- **Nuevo de verdad:** `Documento.nuevo_lienzo` (fondo de color, transparente o degradado), sin PNG; entra a la tira con una ruta que no es un archivo (`Sin título 1.nsdoc`) y su "foto" es una imagen lisa en memoria del tamaño del documento (`documento_capas.imagen_documento`), que no entra a la composición y se rearma cuando cambia el tamaño. Tira, sesión, proyecto `.nslite` y exportar (con transparencia si el fondo lo es) lo tratan como a una foto. En Fácil y Editor la composición entra al filtro; recortar y enderezar del Editor, montaje, borrar objetos y fondo quedan deshabilitados con una nota; girar y voltear giran el lienzo.
- **Menú** Archivo, Editar, Imagen, Capa y Ver (cada operación con la API del motor y un paso del historial). En una foto: rotar, voltear y recortar son los no destructivos de siempre; tamaño de imagen, del lienzo y acoplar arman un documento nuevo en la tira.
- **Herramientas:** Mover, Mano (y Espacio), Zoom, Cuentagotas y las de máscara; colores de frente y fondo (X, D, `QColorDialog`). Barra de opciones por herramienta (Mover: selección automática, mostrar controles, alinear y distribuir).
- **Mover:** escala libre (X e Y; Mayús mantiene la proporción) con `escala_y`, voltear vertical, imán y guías magenta (lienzo y otras capas), selección múltiple. Arreglados `documento_capas.py` (que perdía `escala_y` y `voltear_v` y solo llevaba las capas imagen al girar o recortar: ahora todas las de transformación, más rellenos y estilos).
- **Panel Capas:** grupos plegables con sangría, ícono por tipo, "fx", menú contextual y arrastrar adentro y afuera de los grupos (`reubicar`). **Propiedades:** X, Y, ancho, alto, rotación y rellenos.
- **Sesión:** `EstilosCapa`, `Sombra`, `Trazo`, `Resplandor`, `SuperposicionColor`, `SuperposicionDegradado`, `Relleno`, `ParamsForma` y `ParamsTexto` en `sesion.CLASES` (sin eso, un documento de la Etapa 2 mandaba la sesión a `.bak`).
- **Arreglo de paso:** `exportar` ahora acepta `con_filtro` solo por nombre (con un parámetro posicional, las señales `clicked(bool)` y `triggered(bool)` lo habrían puesto en "sin filtro"); hay una prueba.
- **Historial:** describe escala vertical, volteo vertical, grupos, params, estilos, rasterizar y cambios de tamaño del lienzo.

### Archivos

- **Nuevos:** `ui/modo_photoshop.py`, `ui/propiedades_ps.py`, `ui/iman.py`, `ui/dialogos_ps.py`, `tests/test_modo_photoshop.py` (28 pruebas) y 9 íconos dibujados para la app en el estilo de Lucide (`pipette`, `ps-alinear-*` y `ps-distribuir-*`).
- **Tocados:** `ui/ventana.py` (lo del modo se mudó; documentos sin foto; `exportar(con_filtro=…)`), `ui/panel_capas.py` (reescrito), `ui/herramienta_transformar.py`, `ui/vista_comparacion.py` (la herramienta "ps" con un controlador y la mano temporal), `ui/documento_capas.py`, `ui/historial.py`, `ui/kit_flyer.py` (el diálogo Nuevo da un `Relleno`; ya no escribe PNG), `ui/modo_facil.py` (el nombre de un documento), `sesion.py`, `tests/test_capas_ui.py` y `tests/test_kit_flyer.py` (ajustadas al diseño nuevo: herramientas, Historial a la izquierda, V elige Mover, Recortar en un documento), `LITE.md` y este archivo. El motor no se tocó. Copias de antes en el scratchpad de la sesión 4014f8d8, `respaldo_u1\`.

### Verificación

- **Suite completa en PRO: 854 OK en 527 s** (eran 825; 28 nuevas de `test_modo_photoshop` y 1 del kit). Una primera corrida encontró el problema de `exportar` con `clicked(bool)` (`test_modo_facil`), ya arreglado.
- **Capturas** offscreen en Lite a 1366 × 768 y 1600 × 900 (el modo con el menú Capa y el submenú Alinear abiertos, el menú Imagen, la barra de herramientas y los colores, Propiedades, un grupo con sangría y "fx", las guías del imán mientras se arrastra, el Cuentagotas, el pincel de la máscara y el Editor con un documento sin foto), revisadas y corregidas (la barra de opciones de la máscara y del Cuentagotas se compactaron para entrar a 1366): scratchpad 4014f8d8, `u1\capturas\`.
- **Arranque real** en Lite (plataforma de Windows, `-X faulthandler`, APPDATA e `.ini` temporales), en dos procesos: Nuevo con degradado, dos imágenes, moverlas con el mouse (el imán la centró en 540, 960), Ctrl+T con escala libre, agrupar, tamaño del lienzo, guardar el `.nslite`; después la sesión trajo el documento, se abrió el proyecto, se exportó con y sin filtro, rotar, voltear, relleno, acoplar y girar desde el Editor. Salida 0 en los dos.
- **Lite compilada** (copia de `compilar_lite_copia.ps1` sin los respaldos del motor viejo y con `tests.test_modo_photoshop`): 307 pruebas OK en la copia, `dist_lite\NaturalShot Lite` actualizado y `NaturalShot Lite - para otra PC.zip` de 96 MB. El `.exe` abrió un `.nslite` de un documento nuevo y guardó la sesión con sus imágenes.

### Falta

- U2 (texto vivo, formas, relleno y degradado como herramientas, estilos de capa con su diálogo) y U3 (pincel, borrador, bote, degradado, recortar como herramienta). El botón Texto del kit sigue haciendo texto como imagen.
- El selector de color propio (por ahora `QColorDialog`).
- Sumar el modo al tutorial.

## Lite Etapa 2, U2 ✅ (14/10/2026: texto vivo, formas, rellenos con degradado, estilos de capa y selector de color)

Diseño: `docs/superpowers/specs/2026-10-14-lite-etapa2-photopea-design.md`; plan: `docs/superpowers/plans/2026-10-14-lite-etapa2.md`. Detalle para usarlo: **`LITE.md`** ("Etapa 2, U2"). La PRO no cambia (no tiene el modo). El motor no se tocó.

- **Texto (T):** clic = capa `texto` con la línea base donde se hizo clic; arrastrar = caja (`ancho_caja`). **Edición en el lugar** (`ui/texto_ps.py`): un `QTextEdit` transparente sobre la vista, a su escala y con el mismo archivo de fuente cargado en Qt; lo que se ve es la capa de verdad, re-dibujada con cada tecla en el documento provisorio (con sus estilos). Enter = renglón; Esc, Ctrl+Enter o clic afuera = un paso ("Texto nuevo" / "Texto cambiado" / "Texto borrado" si quedó vacío). Mientras se escribe, las teclas son del texto (acepta `ShortcutOverride`; el filtro del Espacio ya no actúa sobre `QTextEdit`). Doble clic sobre un texto (Mover o Texto) o en su miniatura lo vuelve a editar. El **ancla** (arriba a la izquierda, centro o derecha según la alineación) no se corre al cambiar el texto, el tamaño o la fuente (`con_params_texto`).
- **Barra de opciones y Propiedades** de Texto (`ui/opciones_ps.py`, `ControlesTexto`): familia con búsqueda, tamaño, color, negrita, cursiva, alineación, interlineado y espaciado; con un texto elegido, cada cambio es un paso. **Formas (U)** (`ControlesForma`): rectángulo, elipse, línea, flecha, polígono y estrella (barra o clic derecho en el botón), arrastrar (Mayús 1:1 o de a 45°, Alt desde el centro), relleno (ninguno, color, lineal o radial; el color de frente por defecto), trazo, radio, lados, puntas y grosor/alto de la línea y la flecha.
- **Rellenos con degradado:** `EditorDegradado` (2 a 4 colores con su posición, tipo y ángulo) en Propiedades de un relleno, en el relleno de las formas (diálogo) y en la superposición de degradado.
- **Estilo de capa** (`ui/estilos_capa.py`): doble clic en la fila del panel, "fx" (de la fila y un botón nuevo abajo del panel), menú contextual o "Capa › Estilo de capa…". Sombra, trazo, resplandor y superposiciones de color y de degradado, con tilde; vista previa en vivo (documento provisorio); Aceptar = un paso, Cancelar = vuelve. **Renombrar pasó a F2** (y al menú contextual).
- **Selector de color propio** (`ui/selector_color.py`): saturación y brillo, tono, alfa, hexadecimal, RGB(A), nuevo y antes, recientes en QSettings (`photoshop/colores_recientes`) y cuentagotas (sin filtro global: el diálogo toma el mouse con `grabMouse`; sobre la vista, el color de la composición). Reemplaza al `QColorDialog` en frente y fondo, Propiedades, texto, formas, estilos y el diálogo Nuevo del kit.
- **Kit de flyers:** el botón Texto elige la herramienta; `agregar_texto(datos)` (de las pruebas) crea un texto vivo. Los textos viejos del kit (imágenes) siguen siendo imágenes.

### Archivos

- **Nuevos:** `ui/texto_ps.py`, `ui/opciones_ps.py`, `ui/estilos_capa.py`, `ui/selector_color.py`, `tests/test_texto_formas_ui.py` (15 pruebas) y 12 íconos dibujados para la app en el estilo de Lucide (`ps-rectangulo`, `ps-elipse`, `ps-linea`, `ps-flecha`, `ps-poligono`, `ps-estrella`, `ps-negrita`, `ps-cursiva`, `ps-alinear-texto-*` y `ps-fx`).
- **Tocados:** `ui/modo_photoshop.py` (herramientas Texto y Formas, sus barras, edición en el lugar, estilo de capa, selector y cuentagotas del selector), `ui/propiedades_ps.py` (texto, forma y el editor de degradado; el `BotonColor` viejo se fue a `selector_color`), `ui/panel_capas.py` (doble clic = estilos, miniatura de un texto = editar, "fx", F2), `ui/vista_comparacion.py` (el doble clic llega al controlador), `ui/ventana.py` (atajos T, U y F2; el Espacio no actúa sobre `QTextEdit`; la ayuda del botón Texto), `ui/kit_flyer.py` (su botón de color usa el selector), `tests/test_capas_ui.py`, `tests/test_kit_flyer.py` y `tests/test_modo_photoshop.py` (ajustadas: F2 para renombrar, las herramientas nuevas, el texto vivo del kit, el selector en vez de `QColorDialog`, el editor de degradado), `LITE.md` y este archivo. Copias de antes en el scratchpad de la sesión 4014f8d8, `respaldo_u2\`.

### Verificación

- **Suite completa en PRO: 869 OK en 572 s** (eran 854; 15 nuevas de `test_texto_formas_ui`).
- **`tests/test_texto_formas_ui.py`**, incluido el **flyer de aceptación** (Nuevo 1080 × 1920 con degradado, 4 imágenes en grilla, título blanco centrado con sombra y trazo, banda redondeada amarilla con texto negro encima y estrella blanca; exportado sin filtro y revisado con píxeles: fondo arriba y abajo, color de cada imagen en su lugar, letras y trazo del título, sombra debajo y no arriba, banda con la esquina redonda, el texto adentro de la banda y la estrella).
- **Capturas** offscreen en Lite a 1366 × 768 y 1600 × 900 (escribiendo un título en el lugar, la barra de Texto y Propiedades de un texto, el estilo de capa con la vista previa, la barra de Formas y Propiedades de una forma, una forma con degradado, el selector de color y una capa de relleno con 3 colores), revisadas y corregidas: el texto de Qt se veía chico encima de la capa (la hoja de estilo le ponía su letra: ahora la fuente va en el formato de caracteres y el color es transparente por la hoja), la barra de Formas no entraba a 1366 (sin etiquetas, botones más angostos), la lista del diálogo de estilos tenía barra horizontal y el editor de degradado quedaba apretado al lado de una etiqueta, y el diálogo tapaba el lienzo (ahora aparece a la izquierda). Scratchpad 4014f8d8, `u2\capturas\`.
- **Arranque real** en Lite (plataforma de Windows, `-X faulthandler`, APPDATA e `.ini` temporales), en dos procesos: Nuevo con degradado, título con clic y teclado (Enter, Esc), texto en caja, banda y estrella arrastrando, estilo de capa con el diálogo, el selector (hexadecimal con alfa y cuentagotas sobre la vista), guardar el `.nslite`; después la sesión trajo todo, doble clic en el título y editarlo, abrir el proyecto y exportar. Salida 0 en los dos.
- **Compilación:** el script de U1 (copia en `u2\compilar_lite_u2.ps1`, con `tests.test_texto_formas_ui`) dijo **"LITE ABIERTA"**: había una NaturalShot Lite del dueño abierta desde `dist_lite\` (no se cerró). Se compiló igual **solo en la copia** (`u2\compilar_lite_u2_solo_copia.ps1`): 322 pruebas OK en la copia, `.exe` en `u2\lite_copia\dist\NaturalShot Lite\` con los íconos nuevos; abrió el `.nslite` de U2 y escribió su sesión. **`dist_lite\`, el zip y el acceso directo no se actualizaron**: falta correr `compilar_lite_u2.ps1` (o `construir_lite.bat`) con la Lite cerrada.

### Falta

- Copiar la compilación a `dist_lite\` y rearmar el zip (con la Lite cerrada). (Sigue pendiente: ver U3.)
- ~~U3 (pincel, borrador, bote, degradado, recortar como herramienta)~~: hecha (ver abajo).
- Sumar el modo (con texto, formas y estilos) al tutorial.

## Lite Etapa 2, U3 ✅ (14/10/2026: pincel, borrador, bote, degradado y recortar como herramienta)

Diseño: `docs/superpowers/specs/2026-10-14-lite-etapa2-photopea-design.md`; plan: `docs/superpowers/plans/2026-10-14-lite-etapa2.md`. Detalle para usarlo: **`LITE.md`** ("Etapa 2, U3"). La PRO no cambia (no tiene el modo). El motor no se tocó.

- **Pincel (B)** y **Borrador (E)**: en la capa de píxeles o imagen elegida; sobre un texto, una forma o un relleno pregunta "¿Rasterizar la capa?"; sobre la base, un grupo o nada, una capa de píxeles nueva (en el mismo paso). Mientras se arrastra, el trazo se ve en una **superposición** (`pintura.mascara_trazo` por tramo, una `QImage` actualizada solo donde cambió; 0,3 ms por movimiento en 4000 × 3000); al soltar, `pintura.trazo` (unos 70 ms en 12 MP) y **un paso**. Si se pinta afuera de la capa, crece (hasta el lienzo). Tamaño, dureza y opacidad (cada herramienta los suyos); **[ y ]**; el cursor es un círculo del tamaño del pincel. Esc durante un trazo lo descarta.
- **Bote (G)**: tolerancia, contiguo y "Todas las capas" (la muestra es la composición, llevada a la capa).
- **Degradado (Mayús+G**, o clic derecho en el botón del Bote; comparten botón): en una capa de píxeles lo pinta; si no, crea una **capa de relleno lineal** con el ángulo y las paradas de ese arrastre (`pintura_ps.relleno_lineal_de_arrastre`); radial (o más de 4 colores) va a una capa de píxeles. Lineal o radial, colores de frente a fondo o los del editor de degradado de U2, opacidad.
- **Recortar (C)**: recuadro con 8 manijas, mover, proporciones (libre, original, 1:1, 4:5, 3:4, 9:16, 4:3, 16:9, 3:1), Enter, Aplicar o doble clic aplican (`documento.recortar`), Esc vuelve al lienzo entero. En una **foto**, el recorte no destructivo de siempre (se suma al que tenía; las capas siguen a la foto con `matriz_marco` y `convertir_documento`, como el Editor). **Reemplaza** al botón del kit (ya no va al Editor) y a "Imagen › Recortar".
- **Pegar**: también imágenes copiadas de otras apps (prefiere el PNG del portapapeles, que conserva la transparencia; si no, la imagen de Qt o JPG, WEBP, GIF, BMP). Sin documento, abre uno nuevo del tamaño de la imagen.
- **Memoria**: `_limpiar_almacen` ahora también comprime las imágenes grandes (≥ 1 MB) que solo usan pasos que no se ven (cada trazo es una imagen entera de la capa); deshacer las trae de vuelta (`_traer_mascaras`).
- **Barra de herramientas**: 14 botones (Mover, Recortar, Texto, Formas, Pincel, Borrador, Bote/Degradado, Mano, Zoom, Cuentagotas y las 4 de máscara), de 36 × 34 px para que entren a 768 px de alto.

### Archivos

- **Nuevos:** `ui/pintura_ps.py` (`Lienzo`, `TrazoEnCurso`, `CajaRecorte`, `relleno_lineal_de_arrastre`, `fundir_encima` y las barras `ControlesPincel`, `ControlesBote`, `ControlesDegradado`), `tests/test_pintura_ui.py` (17 pruebas) y 2 íconos dibujados para la app en el estilo de Lucide (`ps-bote`, `ps-degradado`).
- **Tocados:** `ui/modo_photoshop.py` (las herramientas, sus barras, el controlador de la vista, a qué capa se pinta, el recorte como herramienta, pegar), `ui/ventana.py` (atajos B, E, G, Mayús+G, C, [ y ] solo en la Lite; E, [ y ] siguen siendo del pincel de una máscara cuando está activo; Esc descarta un trazo; la ayuda del botón Recortar; `_limpiar_almacen`), `ui/vista_comparacion.py` (al salir el mouse, avisa al controlador: el círculo del pincel se va), `tests/test_modo_photoshop.py`, `tests/test_kit_flyer.py` y `tests/test_capas_ui.py` (ajustadas: Recortar es la herramienta, la lista de herramientas), `LITE.md` y este archivo. Copias de antes en el scratchpad de la sesión 4014f8d8, `respaldo_u3\`.

### Verificación

- **Suite completa en PRO: 886 OK en 542 s** (eran 869; 17 nuevas). Una primera corrida encontró una prueba nueva frágil (el recuadro de recorte arrastrado con el mouse quedaba 1 px corrido según el zoom): ahora compara con margen.
- **Capturas** offscreen en Lite a 1366 × 768 y 1600 × 900 (pintando con la superposición, el borrador con el tablero, el bote con "Todas las capas", el degradado arrastrando y hecho, y Recortar con las manijas en 4:5), revisadas y corregidas: el botón "lineal" repetía el ícono de la herramienta (ahora "Lineal" y "Radial" con texto) y las notas de las barras se cortaban a 1366 (más cortas, o en la barra de estado). Scratchpad 4014f8d8, `u3\capturas\`.
- **Arranque real** en Lite (plataforma de Windows, `-X faulthandler`, APPDATA e `.ini` temporales), en dos procesos: Nuevo, una imagen, Pincel sobre el fondo (capa nueva), ] y [, Borrador, Bote con todas las capas, Degradado a capa de relleno, pintar un texto (rasteriza), Recortar 1:1 con las manijas y Enter, pegar un PNG del portapapeles y guardar el `.nslite`; después la sesión trajo todo, se siguió pintando, deshacer y rehacer, abrir el proyecto, recortar una foto (no destructivo) y exportar sin filtro. Salida 0 en los dos.
- **Compilación:** la Lite del dueño estaba **abierta** (`dist_lite\`, PID 2380; no se cerró), así que se compiló **solo en la copia** (`u3\compilar_lite_u3_solo_copia.ps1`; el completo es `u3\compilar_lite_u3.ps1`, con `tests.test_pintura_ui`): 339 pruebas OK en la copia, `.exe` en `u3\lite_copia\dist\NaturalShot Lite\` con los íconos nuevos; abrió el `.nslite` de U3 y escribió su sesión con las capas pintadas. **`dist_lite\`, el zip y el acceso directo no se actualizaron**: falta correr `u3\compilar_lite_u3.ps1` (o `construir_lite.bat`) con la Lite cerrada.

### Limitaciones

Las de `LITE.md` ("(U3)"): la superposición no muestra la fusión ni la opacidad de la capa; un degradado radial sobre la base va a una capa de píxeles; la capa crece al pintar afuera solo hasta el lienzo; el degradado sobre una capa de píxeles no la agranda; en una foto el recuadro de Recortar no sale de ella.

### Falta

- Copiar la compilación a `dist_lite\` y rearmar el zip (con la Lite cerrada).
- El cierre de la Etapa 2: revisión y sumar el modo Photoshop (texto, formas, estilos y pintura) al tutorial.

## Medida de salida ✅ (17/10/2026: botón "Medida" en Fácil y Editor; solo desde el código)

Un acceso rápido en la barra de arriba, al lado de Recortar/Enderezar: **Medida** abre un menú (ícono, nombre, proporción en magenta y píxeles en gris) con Original, Celular vertical · historia 9:16 (1080 × 1920), PC / YouTube 16:9 (1920 × 1080), PC 4K 16:9 (3840 × 2160), Foto de celular vertical 3:4 (3024 × 4032), horizontal 4:3 (4032 × 3024), Instagram vertical 4:5 (1080 × 1350) y Cuadrado 1:1 (1080 × 1080). El botón dice la elegida ("9:16 · 1080×1920"), queda resaltado y, con poco ancho, se acorta primero a la proporción ("9:16") y después queda solo el ícono, como Recortar; la cabecera de la vista dice "Sale a 1080 × 1920" (sin el "Sale a" si no hay lugar). Es igual en la PRO y en la Lite; en el modo Photoshop no está (ahí la vista es la foto a su tamaño), pero exportar desde ahí también respeta la medida.

- **Por foto, en el estado** (`estado["medida"] = (ancho, alto)`; sin medida la clave no está: historial, sesión y `.nslite` de antes, iguales). Un paso del historial ("Medida: …").
- **El recorte:** sin recorte, uno centrado con esa proporción, el más grande que entra (el no destructivo de siempre); con otro, la proporción nueva alrededor de su centro y con la misma superficie, sin salirse (si era el centrado de la medida anterior, el centrado de la nueva); con la misma, queda. Recortar deja la proporción fija (el combo se bloquea; "Quitar" vuelve al centrado). Girar y enderezar lo reacomodan (`estado_con_geometria`). En el modo Photoshop, un recuadro libre de otra proporción quita la medida. Original quita la medida y deja el recorte.
- **El orden con el filtro:** la foto recortada se lleva a la medida **antes** del filtro (`procesar_con_capas(…, medida=…)`; INTER_AREA para achicar, Lanczos para agrandar), así el grano, el ruido, el Bayer y la compresión simulada trabajan a la resolución de salida (después del filtro, achicar promediaría el grano y agrandar lo volvería manchas). La vista previa rápida hace lo mismo a escala (`medida.tamano_trabajo`, con esa `escala_vista`); la completa y la exportación salen exactas y son iguales bit a bit. Con capas, si el redondeo del documento da 1 px de diferencia, se ajusta al final.
- **Lote:** las fotos elegidas que están en la tira con una medida salen giradas, recortadas y en la medida (`procesar_lote(…, encuadres=…)`); las demás, como siempre.
- **EXIF:** no se toca.

**Archivos nuevos:** `motor/medida.py` (las medidas, el recorte con la proporción, llevar a la medida), `ui/medida.py` (el menú), `tests/test_medida.py` (18 pruebas) y 7 íconos de Lucide (`ratio`, `monitor`, `tv`, `square`, `rectangle-vertical`, `rectangle-horizontal`, `heart`). **Tocados:** `ui/ventana.py`, `ui/historial.py`, `ui/estilo.py`, `ui/modo_photoshop.py` (recortar una foto con otra proporción quita la medida), `ui/modo_facil.py` (ayudas), `motor/lote.py` y este archivo. Copias de antes en el scratchpad de la sesión 57d45be4, `medida\respaldo\`.

**Verificación:** sin elegir medida, cinco exportaciones (sin nada, recorte, girada, Fácil, otra foto) y el lote dan lo mismo que antes del cambio, bit a bit. Capturas offscreen en Lite a 1366 × 768 y 1600 × 900 (menú, 9:16, Recortar con la proporción fija, barra compacta), revisadas: la pastilla de la cabecera apretaba el zoom a 1366 y se acortó. Scratchpad 57d45be4, `medida\capturas\`.

**Limitaciones:** en el lote, de cada foto se usan el giro, el recorte y la medida, pero no el montaje, los borrados, el fondo ni las capas (como siempre en el lote). El 100 % del zoom sigue siendo de la foto recortada (no de la medida). Con "Recortar al objeto" del fondo transparente y una medida, sale la medida exacta (no se recorta al objeto). Falta recompilar el `.exe`.
