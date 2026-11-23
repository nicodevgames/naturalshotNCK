"""Genera el manual PDF y capturas reales de Qt; requiere reportlab y pypdf."""
from pathlib import Path
import os
import sys
import time
import zipfile
from html import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PIL import Image, ImageDraw
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont
from celular_natural.ui.estilo import HOJA_ESTILO
from celular_natural.ui.ventana import VentanaPrincipal
from celular_natural.ui.vista_comparacion import VistaComparacion
from celular_natural.motor import PRESET_PRINCIPAL, PRESETS, DESCRIPCIONES_PRESETS, SECCIONES
from celular_natural.motor.zonas import Zona
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as PDFImage, PageBreak, Table, TableStyle, Preformatted
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4

OUT = ROOT / 'documentacion'
CAP = OUT / 'capturas'
CAP.mkdir(parents=True, exist_ok=True)
app = QApplication([])
for font in ['arial.ttf', 'arialbd.ttf', 'segoeui.ttf', 'seguisb.ttf']:
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
app.setFont(QFont('Arial',10))
app.setStyle('Fusion')
app.setStyleSheet(HOJA_ESTILO)
window = VentanaPrincipal()
window.resize(1680, 1050)
window.show()

def pump(seconds=0.5):
    end = time.monotonic()+seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(.015)

def shot(name, widget=None):
    pump()
    assert (widget or window).grab().save(str(CAP / (name+'.png')))

pump()
shot('01_inicio')
# Escena dibujada para enseñar controles sin usar fotos privadas ni recursos externos.
im = Image.new('RGB', (1400, 1000), '#b9d3da')
d = ImageDraw.Draw(im)
for y in range(1000):
    d.line((0,y,1400,y), fill=(int(190-y*.065),int(214-y*.055),int(218-y*.07)))
d.rectangle((0,680,1400,1000), fill='#a77c59')
d.rectangle((85,95,460,640), fill='#f4e7ce')
for x in range(100,450,15):
    d.line((x,110,x,625), fill='#c5b89d', width=2)
d.rectangle((710,120,1270,610), fill='#4a696b')
d.rectangle((730,140,1250,590), fill='#aec8cb')
d.line((990,140,990,590), fill='#edf2e9', width=12)
d.line((730,365,1250,365), fill='#edf2e9', width=12)
d.ellipse((440,745,1010,860), fill='#79533c')
d.rounded_rectangle((505,475,950,800),radius=20,fill='#dfaa6e')
for y in range(500,780,9):
    d.line((525,y,925,y),fill='#c58c51',width=2)
d.ellipse((505,450,950,525),fill='#eee0ba')
d.ellipse((560,460,885,505),fill='#704f35')
d.arc((900,535,1080,740),270,90,fill='#dfaa6e',width=27)
d.text((55,925),'ESCENA DIBUJADA DE DEMOSTRACION | 1400 x 1000 px',fill='white',font=ImageDraw.ImageFont.truetype('C:/Windows/Fonts/arial.ttf',25))
im.save(OUT/'escena_demo.png')
window.abrir_archivo(str(OUT/'escena_demo.png'))
end=time.monotonic()+30
while (window._imagen is None or window._resultado_completo is None) and time.monotonic()<end:
    pump(.1)
assert window._imagen is not None and window._resultado_completo is not None, 'La imagen no terminó de procesarse'
shot('02_editor')
window.vista.establecer_modo(VistaComparacion.MODO_LADO)
shot('03_comparacion')
window.vista.establecer_modo(VistaComparacion.MODO_DIVIDIR)
window.panel_ajustes._secciones['Detalles'].boton.setChecked(True)
shot('04_detalles')
window.panel_ajustes.agregar_capa('Solo textura (sin tocar el color)',25,zona=Zona('elipse',.35,.40,.72,.82,35))
pump(2)
shot('05_capas')
window._pedir_zona(window.panel_ajustes.capas()[0], 'pincel')
shot('06_pincel')
window.cancelar_herramienta()
window.panel_fondo.establecer_zona(Zona('elipse',.35,.40,.72,.82,12))
pump(2)
shot('07_fondo')
window.panel_fondo.establecer_zona(None)
window.boton_recortar.setChecked(True)
shot('08_recorte')
window.cancelar_herramienta()
for b in window.grupo_formato.buttons():
    if b.property('formato')=='JPEG':
        b.click()
shot('09_exportacion')
window.panel_ajustes._secciones['Máscaras por región'].boton.setChecked(True)
shot('10_mascaras')
window.close()
pump()

pdfmetrics.registerFont(TTFont('Arial','C:/Windows/Fonts/arial.ttf'))
pdfmetrics.registerFont(TTFont('ArialBold','C:/Windows/Fonts/arialbd.ttf'))
pdfmetrics.registerFontFamily('Arial',normal='Arial',bold='ArialBold',italic='Arial',boldItalic='ArialBold')
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyES',fontName='Arial',fontSize=10,leading=15,spaceAfter=9,textColor=HexColor('#25354a')))
styles.add(ParagraphStyle(name='TitleES',fontName='ArialBold',fontSize=27,leading=32,spaceAfter=18,textColor=HexColor('#123752')))
styles.add(ParagraphStyle(name='SubES',fontName='ArialBold',fontSize=14,leading=19,spaceAfter=10,textColor=HexColor('#167d83')))
styles.add(ParagraphStyle(name='CaptionES',fontName='Arial',fontSize=8,leading=11,spaceAfter=12,textColor=HexColor('#64748b')))
styles.add(ParagraphStyle(name='CodeES',fontName='Courier',fontSize=7,leading=10,backColor=HexColor('#eef3f7'),borderPadding=8,spaceAfter=12))
story=[]
def p(s): story.append(Paragraph(s,styles['BodyES']))
def sub(s): story.append(Paragraph(s,styles['SubES']))
def title(s): story.append(Paragraph(s,styles['TitleES']))
def code(s): story.append(Preformatted(s,styles['CodeES']))
def pic(name,caption,width=495):
    path=CAP/(name+'.png')
    with Image.open(path) as img: w,h=img.size
    story.append(PDFImage(str(path),width=width,height=width*h/w))
    story.append(Paragraph(caption,styles['CaptionES']))
def page(t):
    if story: story.append(PageBreak())
    title(t)
def rows(items,widths=(145,350)):
    table=Table([[Paragraph(escape(str(c)),styles['BodyES']) for c in row] for row in items],colWidths=widths,hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor('#e0edf0')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),.3,HexColor('#dbe4ec')),('LEFTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),6)]))
    story.append(table)

page('NaturalShot PRO')
sub('Manual ilustrado · uso y código base')
p('De una imagen demasiado perfecta a un aspecto de foto cotidiana de celular. Guía preparada a partir del código de este proyecto, el 12 de octubre de 2026.')
pic('02_editor','Captura real de la aplicación ejecutada desde el código. La escena de la taza es un dibujo de demostración, no una fotografía ni evidencia de realismo fotográfico.')
p('<b>Para vos:</b> un recorrido paso a paso, consejos para el estilo inspirado en iPhone 13 y una referencia de controles. <b>Para desarrollar:</b> arquitectura, ejemplos ejecutables y una copia del código base en ZIP.')
page('Tu recorrido')
rows([('Parte','Qué vas a encontrar'),('Empezar','Abrir la app, entender la pantalla y editar tu primera foto.'),('Ajustar','Comparación, recetas, capas, pincel y máscaras.'),('Herramientas','Recorte, montaje, fondo, varias fotos y exportación.'),('Código base','Motor, parámetros, archivos, ejemplos y compilación.'),('Referencia','Catálogo real de controles y presets extraído del código.')])
p('El índice lateral del lector de PDF permite saltar entre las secciones. Las capturas muestran estados reales de Qt renderizados fuera de pantalla; el tamaño de tu monitor puede cambiar la distribución visible.')
page('01 · Abrí la aplicación')
p('Si ya está compilada, abrí <b>dist\\NaturalShot\\NaturalShot.exe</b> o el acceso directo NaturalShot PRO. Conservá la carpeta <b>_internal</b> junto al ejecutable.')
p('Para usar el código en esta PC, abrí una terminal en la carpeta del proyecto y ejecutá:')
code('.venv\\Scripts\\python.exe main.py')
pic('01_inicio','Pantalla inicial: Abrir está en la barra superior; también podés arrastrar un archivo al centro.')
p('Admite JPG, JPEG, PNG, WEBP, TIFF y BMP. HEIC no está incluido: convertí esa foto previamente a JPG o PNG.')
page('02 · Conocé la pantalla')
pic('02_editor','Izquierda: preset, capas y herramientas. Centro: foto y comparación. Derecha: ajustes y exportación.')
rows([('Sector','Para qué sirve'),('Preset e intensidad','Elegir el estilo y cuánto aplicarlo.'),('Vista central','Comparar, acercar y trabajar sobre selecciones.'),('Ajustes','Afinar sensor, óptica, detalles, texturas, luz, color y grano.'),('Historial','Volver a un cambio anterior.'),('Exportar','Guardar una copia PNG o JPEG.')])
page('03 · Tu primera foto de celular')
for s in ['1. Abrí tu imagen con <b>Ctrl+O</b>.','2. Elegí <b>Celular natural — inspirado en iPhone 13</b>.','3. Como punto de partida personal, probá <b>Intensidad general entre 35 y 60</b>. Ese rango es una recomendación del tutorial, no una calibración de cámara.','4. Compará el encuadre completo y después revisá al <b>100 %</b>.','5. Si se ve muy blanda, bajá Suavizado o Reducir nitidez. Si el ruido distrae, bajá Ruido de sensor.','6. Exportá en <b>PNG</b> con un nombre nuevo.']:
    p(s)
sub('Para conservar detalle y tamaño')
p('No uses Recortar ni Recortar al tamaño del objeto si necesitás conservar el encuadre y las dimensiones. Dejá Reescalado y JPEG simulado en 0, o apagá la sección Compresión. El reescalado simulado puede perder detalle aunque el archivo final mantenga su tamaño.')
p('Los presets son aproximaciones visuales. El filtro no reproduce exactamente un sensor ni garantiza eliminar los indicios de IA. La naturalidad se juzga sobre una foto real, en especial rostros, pelo, piel y sombras.')
page('04 · Compará bien el resultado')
pic('03_comparacion','Lado a lado permite revisar ambas versiones con el mismo zoom y desplazamiento.')
p('<b>Dividir:</b> mové el divisor. <b>Antes / Después:</b> aislá cada versión. <b>Lado a lado:</b> compará las dos juntas. Mantené la barra espaciadora para ver temporalmente el original.')
p('<b>Ctrl+0</b> ajusta la foto al área visible; <b>Ctrl+1</b> muestra el 100 % y <b>Ctrl+2</b> el 200 %. La rueda hace zoom; doble clic alterna ajustar y 100 %.')
p('La app calcula primero una vista rápida y después la completa. Esperá que termine antes de evaluar ruido fino, Bayer o JPEG: la vista reducida aproxima los artefactos de un píxel.')
page('05 · Ajustá sin pasarte')
pic('04_detalles','Detalles abierto: los controles muestran un valor editable y un ojo para apagar cada efecto.')
p('<b>Reducir nitidez:</b> atenúa el sobreenfoque. <b>Reducir microcontraste:</b> baja el relieve demasiado marcado del detalle. <b>Suavizado:</b> calma textura y ruido; demasiado puede dejar piel plástica.')
p('Modificá un control por vez. Podés escribir un número exacto. El ojo apaga un efecto; el interruptor de la sección apaga el grupo. Doble clic en el nombre vuelve al valor de referencia del preset.')
p('<b>Restablecer</b> vuelve a los valores del preset base; las capas se mantienen. Al cambiar de preset se conservan intensidad general y semilla. La semilla permite repetir el patrón de ruido.')
page('06 · Tres puntos de partida')
rows([('Situación','Receta sugerida para experimentar'),('Foto de IA con piel plástica','Probá Anti IA — piel real, sin calidad exagerada al 30–50 %. Revisá piel y pelo al 100 %; evitá compensar todo con suavizado.'),('Foto excelente demasiado perfecta','Preset principal al 35–60 %, compresión apagada. Afiná nitidez y microcontraste antes de sumar ruido.'),('Foto ya tomada con celular','Probá Celular natural — sutil al 15–35 %. Si no mejora, reducí intensidad a 0 y compará.')])
p('Estos rangos son sugerencias de edición, no mediciones del iPhone 13. Una foto nocturna necesita otro tratamiento que una toma al sol. Cambiá con moderación y mirá toda la imagen además del detalle.')
sub('Chequeo antes de exportar')
p('¿La piel conserva textura? ¿El pelo sigue legible? ¿Hay halos en contornos? ¿El ruido se percibe como parte de la foto? ¿Las luces mantienen información? Si un efecto llama más la atención que la imagen, bajalo.')
page('07 · Capas y zonas')
pic('05_capas','Ejemplo: una capa de Solo textura aplicada a una elipse sobre la escena de demostración.')
p('El preset base actúa sobre toda la imagen. <b>Agregar capa</b> suma otro preset encima; hay hasta cuatro capas extra y se aplican de arriba hacia abajo. Cada una tiene su intensidad.')
p('En <b>Dónde</b> elegí Toda la foto, Rectángulo, Elipse, Lazo poligonal o Pincel. Rectángulo y Elipse se marcan arrastrando. En el lazo, hacé clic punto por punto y cerrá con doble clic o Enter.')
p('<b>Borde suave</b> funde la transición. <b>Invertir</b> afecta lo de afuera. La mira permite volver a marcar; la × elimina la capa. Usá capas para un problema localizado y revisá la unión.')
page('08 · Pintá con el pincel')
pic('06_pincel','Estado real de la herramienta Pincel: controles arriba de la vista y selección localizada.')
for s in ['1. En Dónde elegí <b>Pincel</b>.','2. Pintá con clic izquierdo. Ajustá Tamaño y Dureza.','3. Borrá lo que sobra con clic derecho o con <b>Goma / E</b>.','4. <b>Ctrl+Z</b> o Retroceso quita el último trazo mientras pintás.','5. Terminá con <b>Listo / Enter</b>; <b>Esc</b> descarta la edición de esa vez.']:
    p(s)
p('La dureza controla el borde de cada trazo. La mira permite seguir pintando. Las zonas se guardan relativas a la imagen original para acompañar el cambio de tamaño de la vista previa y el recorte.')
page('09 · Máscaras por región')
pic('10_mascaras','Panel de máscaras: multiplicadores por región y efecto; no equivale a selección semántica con IA.')
p('Activá la sección para variar nitidez, suavizado, ruido y microcontraste en piel, bordes, textura alta y textura baja. <b>100 %</b> aplica la cantidad normal; <b>0 %</b> la suprime en esa región; <b>200 %</b> la duplica.')
p('Ejemplo orientativo: si la piel queda demasiado suave, reducí el multiplicador de suavizado en piel y compará. Los multiplicadores no producen un efecto si su control base está en 0.')
p('Las regiones salen de color, bordes y textura. La máscara de piel puede incluir madera, arena o cuero; para una zona precisa conviene el pincel de una capa.')
page('10 · Recorte e historial')
pic('08_recorte','Herramienta Recortar con proporciones y botones Aplicar, Quitar recorte y Cancelar.')
p('Elegí una proporción o dejala libre, ajustá el marco y tocá <b>Aplicar</b>. <b>Quitar recorte</b> recupera el encuadre completo. El original permanece intacto, pero la exportación recortada sí cambia de dimensiones.')
p('En <b>Historial</b>, un clic vuelve a ese estado. Ctrl+Z deshace y Ctrl+Y o Ctrl+Shift+Z rehacen. Un cambio nuevo después de volver atrás reemplaza la rama futura. El historial tiene un límite de 100 pasos.')
p('El historial y las ediciones por foto son estados de la sesión. No hay una función de guardar proyecto documentada: exportá antes de cerrar para conservar el resultado. Los presets propios sí se guardan en JSON.')
page('11 · Fondo y montaje')
pic('07_fondo','Fondo transparente con una selección de elipse de demostración. Para un objeto real, marcá su contorno o pintalo.')
p('<b>Fondo:</b> Marcar objeto usa el lazo; Pintar objeto usa el pincel. Transparente elimina lo exterior y obliga a exportar PNG. Desenfocado mantiene el objeto nítido y permite ajustar intensidad, transición y profundidad gradual.')
p('Si querés el tamaño original en transparente, desactivá <b>Recortar al tamaño del objeto</b>. Esa opción viene activada en el estado inicial del panel.')
p('<b>Montaje:</b> abrí dos tomas similares; en Superponer otra foto elegí la fuente, definí Dónde y ajustá opacidad y borde. Alinear automáticamente busca coincidencias; revisá posibles desplazamientos. Igualar brillo y color ayuda a fundir la unión. El montaje cambia contenido, así que es opcional para tu objetivo inicial.')
page('12 · Varias fotos y lotes')
p('Podés abrir varias imágenes juntas. La tira de miniaturas aparece abajo: clic para cambiar, + para agregar y clic derecho para quitar. Cada foto conserva sus ajustes durante la sesión.')
p('Una foto nueva hereda preset y capas de la actual, pero no sus zonas, recorte, montaje ni selección del objeto. Eso evita pegar una selección de una escena sobre otra distinta.')
sub('Procesar varias fotos…')
p('Aplica los ajustes y capas actuales a los archivos seleccionados a resolución completa. Usa el formato y calidad elegidos. No aplica recortes, zonas, montaje ni selección de fondo propios de una foto: las capas se procesan globalmente.')
p('Elegí una carpeta de salida para revisar todo junto. Si cancelás ese selector de carpeta, el flujo actual guarda junto a cada original; para abandonar el lote, cancelá antes la selección de archivos. Un error de un archivo no corta los demás.')
p('Probá primero una foto representativa. Un mismo preset puede funcionar distinto en exterior, retrato y noche; separá los lotes por condiciones parecidas.')
page('13 · Exportación y archivos')
pic('09_exportacion','JPEG seleccionado: calidad 60–100 y opción de conservar EXIF. PNG permite conservar transparencia.')
p('<b>PNG:</b> guarda sin pérdida adicional de compresión. <b>JPEG:</b> genera un archivo más liviano; probá 92–98 para un resultado cuidado. La calidad JPEG de exportación es distinta del efecto JPEG simulado en Compresión: pueden acumular pérdida si usás ambos.')
p('Ctrl+S abre Exportar como archivo nuevo. El nombre sugerido agrega <b>_celular</b>. La app impide escribir sobre el original. Elegí otro nombre para conservar también exportaciones anteriores, porque un destino existente puede reemplazarse.')
p('EXIF es opcional y copia información original: no convierte los metadatos en los de un iPhone. La orientación se aplica al cargar y se elimina la etiqueta de rotación al exportar. Los perfiles RGB se conservan; CMYK se convierte a sRGB.')
page('14 · Atajos y soluciones')
rows([('Atajo','Acción'),('Ctrl+O / Ctrl+S','Abrir / Exportar'),('Ctrl+0 / Ctrl+1 / Ctrl+2','Ajustar / 100 % / 200 %'),('Ctrl+Z / Ctrl+Y','Deshacer / Rehacer'),('Espacio sostenido','Ver original temporalmente'),('Enter / Esc','Terminar selección / cancelar herramienta'),('E / clic derecho','Goma / borrar mientras pintás')])
sub('Si algo no queda bien')
p('<b>Foto lavada:</b> bajá suavizado y reducción de detalle. <b>Ruido excesivo:</b> bajá ruido o intensidad y comprobá al 100 %. <b>Color raro:</b> restá temperatura, tinte o saturación y compará en un visor con gestión de color. <b>PNG más chico:</b> revisá recorte y recorte al objeto. <b>No abre HEIC:</b> convertí antes. <b>No inicia el EXE:</b> asegurate de conservar _internal junto a él.')
p('El motor usa CPU; la demora depende de tamaño, ajustes y equipo. El trabajo en segundo plano mantiene la interfaz disponible, pero esperá la vista completa para juzgar el resultado final.')
page('15 · El código base')
p('Se adjunta <b>NaturalShot_codigo_base.zip</b> con main.py, motor, interfaz, recursos, pruebas y configuración de compilación. No incluye .venv, build ni dist: las dependencias se reinstalan y el ejecutable se genera aparte.')
rows([('Archivo o carpeta','Responsabilidad'),('main.py','Crea QApplication, carga estilo y muestra la ventana.'),('ui/ventana.py','Coordina fotos, historial, vista, tareas y exportación.'),('ui/controles.py','Construye controles, presets, capas y máscaras.'),('motor/procesado.py','Define Ajustes y presets; ordena el procesamiento.'),('motor/parametros.py','Etiquetas, rangos y ayudas de cada control.'),('motor/imagen_io.py','Carga, EXIF, ICC y exportación segura.'),('motor/mascaras.py','Regiones por color, bordes y textura.'),('motor/zonas.py','Zonas, pincel y recorte normalizados.'),('tests/','Pruebas de motor, archivos y herramientas.')])
page('16 · Cómo viaja una foto')
sub('Archivo → edición → copia exportada')
p('imagen_io carga los píxeles y corrige la orientación. ventana mantiene la imagen y el estado de cada foto. Montaje y recorte construyen la fuente; el fondo desenfocado se calcula antes del tratamiento. procesar_pila aplica base y capas; la salida pasa a la vista y al exportador.')
rows([('Etapa','Módulos'),('Luz lineal','Exposición y balance → óptica → Bayer → HDR local.'),('Respuesta perceptual','Tono y color → detalle y texturas → ruido → grano.'),('Final de la pila','Reescalado y JPEG simulados, una vez; cuantización a 8 bits.'),('Archivo final','PNG o JPEG, perfil ICC, EXIF opcional y alfa si corresponde.')])
p('Entre efectos y capas se trabaja con float32. La vista usa una versión reducida primero, tareas en QThreadPool y generaciones para descartar resultados viejos. El motor no depende de los widgets: podés usarlo desde un script.')
page('17 · Ejemplo mínimo con el motor')
p('Este ejemplo usa las funciones reales del proyecto. Guardalo como ejemplo_motor.py en la raíz y ejecutalo con el Python de .venv. Reemplazá entrada.png por una foto tuya.')
code('from dataclasses import replace\nfrom celular_natural.motor import (\n    PRESETS, PRESET_PRINCIPAL, cargar_imagen,\n    procesar_pila, exportar_imagen,\n)\n\nimagen = cargar_imagen("entrada.png")\najustes = replace(\n    PRESETS[PRESET_PRINCIPAL],\n    intensidad=45, compresion_activa=False,\n)\nsalida = procesar_pila(imagen.rgb, (ajustes,))\nexportar_imagen(\n    "salida_natural.png", salida,\n    original=imagen.ruta, alpha=imagen.alpha,\n    icc=imagen.icc, formato="PNG",\n)')
p('No hace falta crear QApplication para usar el motor. La copia usa la resolución de la entrada y conserva su alfa y perfil; este ejemplo omite EXIF y no aplica montaje, recorte ni fondo.')
sub('Una segunda capa')
code('extra = replace(\n    PRESETS["Solo textura (sin tocar el color)"],\n    intensidad=20,\n)\nsalida = procesar_pila(imagen.rgb, (ajustes, extra))')
page('18 · Modificar y compilar')
p('<b>Un preset nuevo:</b> añadí su nombre, Ajustes y descripción en GRUPOS_PRESETS de motor/procesado.py. Para el ícono, revisá ICONO_PRESET en ui/iconos.py. No prometas una réplica calibrada de cámara si no hay referencias medidas.')
p('<b>Un efecto nuevo:</b> agregá el campo a Ajustes, describí su control en parametros.py e implementá su aplicación en el motor. Respetá interruptores, intensidad 0, semilla y escala de la vista. Los widgets se generan desde SECCIONES.')
sub('Instalar desde una copia limpia')
code('python -m venv .venv\n.venv\\Scripts\\python -m pip install -r requirements.txt\n.venv\\Scripts\\python main.py')
sub('Verificar y generar EXE')
code('.venv\\Scripts\\python -m unittest discover -s tests -v\n.venv\\Scripts\\python -m PyInstaller --noconfirm --clean NaturalShot.spec')
p('También existe construir_exe.bat. Cerrá la aplicación compilada antes de recompilar. Distribuí la carpeta dist\\NaturalShot completa. Los comandos de compilación se documentan; no se recompiló el ejecutable para crear esta guía.')
sub('Volver a generar este manual')
code('.venv\\Scripts\\python -m pip install reportlab pypdf\n.venv\\Scripts\\python herramientas\\generar_manual.py')

for sec in SECCIONES:
    page('Referencia · '+sec.nombre)
    p(escape(sec.descripcion))
    for control in sec.controles:
        sub(control.etiqueta)
        r='Opciones: '+', '.join(control.opciones) if control.tipo=='opcion' else ('Interruptor' if control.tipo=='booleano' else f'Rango: {control.minimo} a {control.maximo}')
        p(escape(r+' · Campo: '+control.campo))
        p(escape(control.ayuda))
page('Referencia · Presets incluidos')
p('Catálogo extraído directamente de PRESETS y DESCRIPCIONES_PRESETS. Las descripciones son las del código revisado; el estilo final depende de tu imagen y de la intensidad.')
for nombre in PRESETS:
    sub(nombre)
    p(escape(DESCRIPCIONES_PRESETS.get(nombre,'')))

def decorate(canvas,doc):
    canvas.saveState()
    canvas.setStrokeColor(HexColor('#dbe4ec'))
    canvas.line(40,39,A4[0]-40,39)
    canvas.setFont('Arial',8)
    canvas.setFillColor(HexColor('#64748b'))
    canvas.drawString(40,25,'NaturalShot PRO · Manual de uso y código · 12/10/2026')
    canvas.drawRightString(A4[0]-40,25,str(doc.page))
    canvas.restoreState()

class ManualDoc(SimpleDocTemplate):
    def afterFlowable(self,flowable):
        if isinstance(flowable,Paragraph) and flowable.style.name=='TitleES':
            key='seccion-'+str(self.page)
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(flowable.getPlainText(),key,0,False)

pdf=OUT/'NaturalShot_PRO_Manual.pdf'
ManualDoc(str(pdf),pagesize=A4,rightMargin=40,leftMargin=40,topMargin=42,bottomMargin=52,title='NaturalShot PRO — Manual ilustrado y código base',author='Manual del proyecto NaturalShot').build(story,onFirstPage=decorate,onLaterPages=decorate)
with zipfile.ZipFile(OUT/'NaturalShot_codigo_base.zip','w',zipfile.ZIP_DEFLATED) as z:
    for name in ['main.py','README.md','requirements.txt','NaturalShot.spec','ejecutar.bat','construir_exe.bat','celular_natural','tests','assets','herramientas']:
        item=ROOT/name
        files=item.rglob('*') if item.is_dir() else [item]
        for file in files:
            if file.is_file() and '__pycache__' not in file.parts and file.suffix!='.pyc':
                z.write(file,file.relative_to(ROOT))
from pypdf import PdfReader
reader=PdfReader(pdf)
assert len(reader.pages)>=20
assert all((page.extract_text() or '').strip() for page in reader.pages)
print(f'PDF: {pdf}\nPáginas: {len(reader.pages)}\nCapturas: {len(list(CAP.glob("*.png")))}\nCódigo: {OUT / "NaturalShot_codigo_base.zip"}')
