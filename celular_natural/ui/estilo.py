"""Tema oscuro con acentos magenta y violeta."""

# Paleta
FONDO = "#2f3136"          # fondo general
LATERAL = "#313338"        # barra lateral
TARJETA = "#33353b"        # tarjetas
TARJETA_2 = "#37393f"      # controles sobre tarjeta
BORDE = "#3f4148"
BORDE_TARJETA = "#59344c"  # borde rosado tenue de las tarjetas
SELECCION = "#4f2e46"      # fondo de elemento seleccionado (tono vino)
BORDE_SELECCION = "#7a2a55"
TEXTO = "#f2f0f5"
TEXTO_2 = "#c9c4d3"
TEXTO_TENUE = "#8e8a99"
MAGENTA = "#d946ef"
VIOLETA = "#7c3aed"
ROSA = "#ec4899"
PUNTO = "#ff4d6d"

DEGRADADO = f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {MAGENTA}, stop:1 {VIOLETA})"
DEGRADADO_H = f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ROSA}, stop:1 {VIOLETA})"

HOJA_ESTILO = f"""
QWidget {{
    background: transparent;
    color: {TEXTO};
    font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif;
    font-size: 10pt;
}}
QMainWindow, #raiz {{ background: {FONDO}; }}
QToolTip {{
    background: {TARJETA_2}; color: {TEXTO}; border: 1px solid {BORDE_SELECCION};
    border-radius: 6px; padding: 6px;
}}

/* ---------- Barra lateral ---------- */
#barraLateral {{ background: {LATERAL}; border-right: 1px solid {BORDE}; }}
#tituloApp {{
    font-family: "Segoe UI Variable Display", "Segoe UI", sans-serif;
    font-size: 13.5pt; font-weight: 700; color: {TEXTO};
}}
#subtituloApp {{ color: {TEXTO_TENUE}; font-size: 9pt; }}
#insigniaPro {{
    background: {DEGRADADO}; color: white; border-radius: 6px;
    font-size: 7.5pt; font-weight: 800; letter-spacing: 1px; padding: 2px 7px;
}}
#filaCapa {{
    background: {TARJETA_2}; border: 1px solid {BORDE_TARJETA}; border-radius: 12px;
}}
#etiquetaCapa {{ color: {TEXTO}; font-weight: 600; }}
QPushButton#botonQuitar {{
    background: transparent; border: none; color: {TEXTO_TENUE}; font-size: 13pt; padding: 0;
}}
QPushButton#botonQuitar:hover {{ color: {PUNTO}; background: #4f2e40; border-radius: 12px; }}
QPushButton#botonAgregarCapa {{
    background: transparent; border: 1px dashed #61405b; color: {TEXTO_2};
}}
QPushButton#botonAgregarCapa:hover {{ border-color: {ROSA}; color: {TEXTO}; background: #36393f; }}
#pieLateral {{ border-top: 1px solid {BORDE}; }}
#panelDerecho {{ background: {LATERAL}; border-left: 1px solid {BORDE}; }}
#pieDerecho {{ border-top: 1px solid {BORDE}; }}
QListWidget#listaHistorial {{
    background: transparent; border: none; outline: none; font-size: 9pt;
}}
QListWidget#listaHistorial::item {{
    color: {TEXTO_2}; padding: 5px 6px; border-radius: 7px; margin: 1px 0;
}}
QListWidget#listaHistorial::item:hover {{ background: #393c42; }}
QListWidget#listaHistorial::item:selected {{
    background: {SELECCION}; color: {TEXTO}; border: 1px solid {BORDE_SELECCION};
}}
#barraRecorte, #barraPincel {{ background: #35373d; border: 1px solid {BORDE_SELECCION}; border-radius: 10px; }}

/* ---------- Panel Capas (capas de verdad del documento) ---------- */
QListWidget#listaCapas {{
    background: #2f3136; border: 1px solid {BORDE}; border-radius: 10px; outline: none; padding: 2px;
}}
QListWidget#listaCapas::item {{ border: 1px solid transparent; border-radius: 8px; margin: 1px 0; }}
QListWidget#listaCapas::item:hover {{ background: #393c42; }}
QListWidget#listaCapas::item:selected {{ background: {SELECCION}; border-color: {BORDE_SELECCION}; }}
#filaCapaDoc {{ background: transparent; border: none; }}
#miniCapa {{ border: 1px solid #4b4e56; border-radius: 4px; background: #3a3c43; }}
#nombreCapa {{ color: {TEXTO}; font-weight: 600; font-size: 9.5pt; background: transparent; }}
#nombreCapa[apagada="true"] {{ color: {TEXTO_TENUE}; }}
#detalleCapa {{ color: {TEXTO_TENUE}; font-size: 8pt; background: transparent; }}
#detalleCapaFalta {{ color: {ROSA}; font-size: 8pt; background: transparent; }}
QLineEdit#editorNombreCapa {{
    background: #3a3c43; border: 1px solid {ROSA}; border-radius: 6px; padding: 1px 4px; color: {TEXTO};
}}
QToolButton#botonOjo, QToolButton#botonCandado {{ background: transparent; border: none; border-radius: 6px; }}
QToolButton#botonOjo:hover, QToolButton#botonCandado:hover {{ background: #4b4e56; }}
QPushButton#botonCapa {{ padding: 0; border-radius: 8px; }}
#cajaMascara {{ background: #35373d; border: 1px solid {BORDE_SELECCION}; border-radius: 10px; }}
QSplitter#divisorDerecho::handle {{ background: transparent; margin: 0 40px; border-radius: 2px; }}
QSplitter#divisorDerecho::handle:hover {{ background: {BORDE_SELECCION}; }}
QToolButton#botonInfo {{
    background: {TARJETA_2}; border: 1px solid {BORDE}; border-radius: 10px;
}}
QToolButton#botonInfo:hover {{ border-color: {BORDE_SELECCION}; background: #3c3e45; }}
#notaModificado {{ color: {ROSA}; font-size: 8.5pt; }}
#tiraFotos {{ background: {TARJETA}; border: 1px solid {BORDE}; border-radius: 14px; }}
QListWidget#listaTira {{ background: transparent; border: none; outline: none; }}
QListWidget#listaTira::item {{ border: 2px solid transparent; border-radius: 9px; padding: 1px; }}
QListWidget#listaTira::item:hover {{ border-color: #4b4e56; }}
QListWidget#listaTira::item:selected {{ border-color: {MAGENTA}; background: {SELECCION}; }}
QPushButton#botonAgregarFoto {{
    background: transparent; border: 1px dashed #61405b; border-radius: 10px;
}}
QPushButton#botonAgregarFoto:hover {{ border-color: {ROSA}; background: #36393f; }}
QPushButton#botonQuitarTodas {{ background: transparent; border: 1px solid transparent; border-radius: 9px; padding: 0; }}
QPushButton#botonQuitarTodas:hover {{ background: #4f2e40; border-color: #7a2a55; }}
#avisoFlotante {{
    background: #3a3c43; border: 1px solid {BORDE_SELECCION}; border-radius: 12px;
}}
#textoAviso {{ color: {TEXTO}; font-size: 9pt; background: transparent; }}
QPushButton#botonCerrarAviso {{ background: transparent; border: none; padding: 0; border-radius: 7px; }}
QPushButton#botonCerrarAviso:hover {{ background: #4b4e56; }}
#miniMontaje {{ border-radius: 6px; background: #3a3c43; }}
#cajaNoMostrar {{ background: {TARJETA_2}; border: 1px solid {BORDE}; border-radius: 12px; }}
#cajaNoMostrar:hover {{ border-color: {BORDE_SELECCION}; }}
#cajaNoMostrar[activo="true"] {{ background: {SELECCION}; border-color: {BORDE_SELECCION}; }}
#tituloNoMostrar {{ color: {TEXTO}; font-weight: 600; font-size: 10pt; background: transparent; }}
#notaNoMostrar {{ color: {TEXTO_TENUE}; font-size: 8.5pt; background: transparent; }}
#marcoTutorial {{ background: #1e1f22; border: 1px solid {BORDE}; border-radius: 12px; }}
QPdfView#vistaTutorial {{ background: #1e1f22; border: none; border-radius: 12px; }}
#selectorFormato {{ background: #35373d; border: 1px solid {BORDE}; border-radius: 12px; }}
QPushButton#opcionFormato {{
    background: transparent; border: 1px solid transparent; border-radius: 9px;
    padding: 6px 10px; color: {TEXTO_TENUE}; text-align: left; font-size: 9pt;
}}
QPushButton#opcionFormato:hover {{ background: #393c42; color: {TEXTO_2}; }}
QPushButton#opcionFormato:checked {{
    background: {SELECCION}; border: 1px solid {BORDE_SELECCION}; color: {TEXTO}; font-weight: 600;
}}
QPushButton#botonChico {{ padding: 4px 10px; font-size: 9pt; border-radius: 8px; }}
#avatar {{
    background: {DEGRADADO}; color: white; border-radius: 17px;
    font-weight: 700; font-size: 10pt;
}}
#pieNombre {{ font-weight: 700; color: {TEXTO}; }}
#pieDetalle {{ color: {TEXTO_TENUE}; font-size: 8.5pt; }}

/* ---------- Secciones del panel ---------- */
#tituloSeccion {{
    color: {TEXTO_TENUE}; font-size: 8.5pt; font-weight: 700; letter-spacing: 1px; margin-top: 6px;
}}
#tituloGrupo {{ color: {TEXTO}; font-weight: 600; margin-top: 12px; }}
#etiquetaControl {{ color: {TEXTO_2}; }}
#valorControl {{
    color: {TEXTO}; background: #3a3c43; border: 1px solid {BORDE}; border-radius: 7px;
    padding: 0px 3px; min-height: 20px; font-weight: 600;
}}
#valorControl:focus {{ border-color: {ROSA}; }}
#valorControl::up-button, #valorControl::down-button {{
    subcontrol-origin: border; width: 0px; height: 0px; border: none;
}}
#tarjetaSeccion {{ background: {TARJETA}; border: 1px solid {BORDE}; border-radius: 14px; }}
#tarjetaSeccion[abierta="true"] {{ border-color: {BORDE_TARJETA}; background: #34363c; }}
#cabeceraSeccion {{ background: transparent; border: none; border-radius: 13px; }}
#cabeceraSeccion:hover {{ background: #37393f; }}
#cuerpoSeccion {{ background: transparent; border: none; border-top: 1px solid {BORDE}; }}
#tituloCaja {{ font-weight: 700; font-size: 10.5pt; color: {TEXTO}; }}
#subtituloCaja {{ color: {TEXTO_TENUE}; font-size: 8.5pt; }}
QToolButton#chevron {{ background: transparent; border: none; padding: 2px; }}
QToolButton#chevron:hover {{ background: #3e4047; border-radius: 6px; }}
#nota {{ color: {TEXTO_TENUE}; font-size: 9pt; }}
#separador {{ background: {BORDE}; max-height: 1px; min-height: 1px; border: none; }}

/* ---------- Contenido ---------- */
#barraHerramientas {{ background: transparent; border: none; }}
#segmento {{ background: #34363b; border: 1px solid {BORDE}; border-radius: 11px; }}
QPushButton#botonSegmento {{
    background: transparent; border: 1px solid transparent; border-radius: 8px;
    padding: 5px 10px; color: {TEXTO_2};
}}
QPushButton#botonSegmento:hover {{ background: #3b3d44; color: {TEXTO}; }}
QPushButton#botonSegmento:checked {{
    background: {SELECCION}; border: 1px solid {BORDE_SELECCION}; color: {TEXTO};
}}
QPushButton#botonSegmento:disabled {{ color: #5c5868; }}
QPushButton#botonSegmento[compacto="true"] {{ padding: 5px 6px; }}
#tarjetaVista {{
    background: {TARJETA}; border: 1px solid {BORDE_TARJETA}; border-radius: 18px;
}}
#tituloTarjeta {{
    font-family: "Segoe UI Variable Display", "Segoe UI", sans-serif;
    font-size: 11.5pt; font-weight: 700;
}}
#puntoEstado {{ color: {PUNTO}; font-size: 13pt; }}
#estadoImagen {{ color: {TEXTO_TENUE}; }}
#etiquetaZoom {{ color: {TEXTO}; font-weight: 600; font-size: 9pt; }}

/* ---------- Botones ---------- */
QPushButton {{
    background: {TARJETA_2}; border: 1px solid {BORDE}; border-radius: 10px;
    padding: 7px 14px; color: {TEXTO_2};
}}
QPushButton:hover {{ background: #3c3e45; border-color: #4b4e56; color: {TEXTO}; }}
QPushButton:pressed {{ background: #35373d; }}
QPushButton:disabled {{ color: #5c5868; background: #34363c; border-color: #3a3c43; }}
QPushButton:checked {{
    background: {SELECCION}; border: 1px solid {BORDE_SELECCION}; color: {TEXTO};
}}
QPushButton#botonPrimario {{
    background: {DEGRADADO}; border: none; color: white; font-weight: 700; padding: 9px 16px;
}}
QPushButton#botonPrimario:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #e879f9, stop:1 #8b5cf6);
}}
QPushButton#botonPrimario:disabled {{ background: #40434a; color: #8a7a99; }}
QPushButton#botonAbrir {{
    background: {SELECCION}; border: 1px solid {BORDE_SELECCION}; color: {TEXTO}; font-weight: 600;
}}
QPushButton#botonAbrir:hover {{ background: #58324e; border-color: {ROSA}; }}

QToolButton#botonAvanzado {{
    background: transparent; border: none; color: {TEXTO}; font-weight: 600; padding: 4px 0;
}}

/* ---------- Modo fácil y selector Fácil | Editor ---------- */
#selectorModo {{ background: #34363b; border: 1px solid {BORDE}; border-radius: 12px; }}
QPushButton#botonModo {{
    background: transparent; border: 1px solid transparent; border-radius: 9px;
    padding: 6px 10px; color: {TEXTO_2}; font-weight: 600;
}}
QPushButton#botonModo:hover {{ background: #3b3d44; color: {TEXTO}; }}
QPushButton#botonModo:checked {{ background: {DEGRADADO}; color: white; border: 1px solid transparent; }}
/* Video: otro tipo de trabajo, se distingue de Fácil y Editor (ícono rosa y contorno, sin relleno:
   así no parece marcado). */
QPushButton#botonModo[destacado="true"] {{
    background: transparent; border: 1px solid #8a3a6c; color: {TEXTO};
}}
QPushButton#botonModo[destacado="true"]:hover {{ background: #3b3d44; border-color: {ROSA}; }}
QPushButton#botonModo[destacado="true"]:checked {{
    background: {DEGRADADO}; color: white; border: 1px solid transparent;
}}
#chipVideo {{ background: #3a2f3d; border: 1px solid {BORDE_SELECCION}; border-radius: 10px; }}
#chipVideo:hover {{ border-color: {ROSA}; background: #43324a; }}
#textoChipVideo {{ color: {TEXTO}; font-size: 9pt; font-weight: 600; background: transparent; }}
QProgressBar#barraChipVideo {{ background: #4c3f52; }}
QPushButton#botonCerrarVideo {{ background: transparent; border: 1px solid transparent; padding: 0; border-radius: 9px; }}
QPushButton#botonCerrarVideo:hover {{ background: #4f2e40; border-color: #7a2a55; }}
/* ---------- Modo Audio ---------- */
#etiquetaPista {{ color: {TEXTO_TENUE}; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }}
QPushButton#botonIconoAudio {{ background: transparent; border: 1px solid transparent; padding: 0; border-radius: 8px; }}
QPushButton#botonIconoAudio:hover {{ background: #3e4047; border-color: #4b4e56; }}
QPushButton#botonIconoAudio:disabled {{ background: transparent; border-color: transparent; }}
#insigniaFalta {{
    background: #4a2230; color: #fca5a5; border: 1px solid #8a2f4a; border-radius: 7px;
    padding: 0px 6px; font-size: 8pt; font-weight: 700;
}}
#filaMiSonido {{ background: transparent; border: 1px solid transparent; border-radius: 9px; }}
#filaMiSonido:hover {{ background: #37393f; border-color: {BORDE}; }}
#franjaVideo {{ background: #3a2f3d; border: 1px solid {BORDE_SELECCION}; border-radius: 12px; }}
#textoFranjaVideo {{ color: {TEXTO}; font-weight: 600; background: transparent; }}
#ondaGrande QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 1px 14px; }}
#ondaGrande QScrollBar::handle:horizontal {{ background: #43464d; border-radius: 4px; min-width: 30px; }}
#ondaGrande QScrollBar::handle:horizontal:hover {{ background: {BORDE_SELECCION}; }}
#ondaGrande QScrollBar::add-line:horizontal, #ondaGrande QScrollBar::sub-line:horizontal {{ width: 0; }}
#ondaGrande QScrollBar::add-page:horizontal, #ondaGrande QScrollBar::sub-page:horizontal {{ background: transparent; }}
#numeroPaso {{
    background: {DEGRADADO}; color: white; border-radius: 8px; font-weight: 800; font-size: 10pt;
}}
#tituloGaleria {{ color: {TEXTO_TENUE}; font-size: 8pt; font-weight: 700; letter-spacing: 1px; margin-top: 2px; }}
QPushButton#botonVerMas {{
    background: transparent; border: 1px dashed #61405b; color: {TEXTO_2}; padding: 7px 12px;
}}
QPushButton#botonVerMas:hover {{ border-color: {ROSA}; color: {TEXTO}; background: #36393f; }}
QPushButton#botonVerMas:checked {{
    background: transparent; border: 1px solid {BORDE_SELECCION}; color: {TEXTO};
}}
QPushButton#botonEnlace {{
    background: transparent; border: none; color: {TEXTO_2}; padding: 3px 8px; font-size: 9pt;
}}
QPushButton#botonEnlace:hover {{ color: {ROSA}; background: transparent; }}
QPushButton#botonEnlace:disabled {{ color: #5c5868; background: transparent; }}
#notaEditor {{ background: #37393f; border: 1px solid {BORDE_TARJETA}; border-radius: 9px; }}
#textoNotaEditor {{ color: {TEXTO_2}; font-size: 8.5pt; }}
#referenciaIntensidad {{ color: {TEXTO_TENUE}; font-size: 8.5pt; }}
#pieFacil {{ border-top: 1px solid {BORDE}; }}
QPushButton#botonPrimario[grande="true"], QPushButton#botonAbrir[grande="true"] {{
    padding: 10px 16px; font-size: 10.5pt;
}}
QPushButton#opcionFormato[centrado="true"] {{ text-align: center; padding: 7px 6px; }}

/* ---------- Entradas ---------- */
QComboBox {{
    background: {TARJETA_2}; border: 1px solid {BORDE}; border-radius: 10px;
    padding: 7px 10px; color: {TEXTO};
}}
QComboBox:hover {{ border-color: {BORDE_SELECCION}; }}
QComboBox:on {{ border-color: {ROSA}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {TARJETA_2}; border: 1px solid {BORDE_SELECCION}; border-radius: 8px;
    padding: 4px; outline: none;
    selection-background-color: {SELECCION}; selection-color: {TEXTO};
}}
QComboBox QAbstractItemView::item {{ min-height: 26px; padding: 2px 8px; }}

QSlider {{ min-height: 20px; }}
QSlider::groove:horizontal {{ height: 4px; background: #404349; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {DEGRADADO_H}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: #ffffff; border: 3px solid {MAGENTA};
    width: 10px; height: 10px; margin: -7px 0; border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{ border-color: #f0abfc; }}
QSlider::sub-page:horizontal:disabled {{ background: #4c4f58; }}
QSlider::handle:horizontal:disabled {{ background: #6b6577; border-color: #4c4f58; }}

QCheckBox {{ spacing: 8px; color: {TEXTO_2}; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 5px; border: 1px solid #4b4e56; background: {TARJETA_2};
}}
QCheckBox::indicator:hover {{ border-color: {BORDE_SELECCION}; }}
QCheckBox::indicator:checked {{ background: {DEGRADADO}; border-color: {MAGENTA}; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #43464d; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {BORDE_SELECCION}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QProgressBar {{ background: #404349; border: none; border-radius: 3px; max-height: 5px; }}
QProgressBar::chunk {{ background: {DEGRADADO_H}; border-radius: 3px; }}

QMessageBox, QFileDialog, QDialog {{ background: {TARJETA}; }}

/* ---------- Actualizaciones ---------- */
#bannerActualizacion {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4e2a55, stop:0.5 #3c3e45, stop:1 #383a40);
    border: none; border-bottom: 1px solid {BORDE_SELECCION};
}}
#bannerActualizacion[tipo="aviso"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #542a3f, stop:1 #34363b);
    border-bottom: 1px solid #8a2f4a;
}}
#iconoBanner {{ background: {DEGRADADO}; border-radius: 17px; }}
#bannerActualizacion[tipo="aviso"] #iconoBanner {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {PUNTO}, stop:1 #b4235c);
}}
#tituloBanner {{ color: {TEXTO}; font-weight: 700; font-size: 10.5pt; }}
#detalleBanner {{ color: {TEXTO_2}; font-size: 9pt; }}
#notasBanner {{ color: {TEXTO_2}; font-size: 9pt; }}
#progresoBanner {{ background: #42454c; }}
QPushButton#botonCerrarBanner {{ background: transparent; border: none; padding: 5px; border-radius: 8px; }}
QPushButton#botonCerrarBanner:hover {{ background: #3f4148; }}
QPushButton#botonVersion {{
    background: #34363b; border: 1px solid {BORDE}; border-radius: 9px;
    padding: 2px 8px; color: {TEXTO_TENUE}; font-size: 8.5pt; font-weight: 600;
}}
QPushButton#botonVersion:hover {{ border-color: {BORDE_SELECCION}; color: {TEXTO}; background: #393c42; }}
QPushButton#botonVersion[hayNueva="true"] {{ border-color: {MAGENTA}; color: {TEXTO}; background: {SELECCION}; }}
QMenu {{
    background: {TARJETA_2}; border: 1px solid {BORDE_SELECCION}; border-radius: 10px; padding: 6px;
}}
QMenu::item {{ padding: 7px 18px 7px 10px; border-radius: 7px; color: {TEXTO_2}; }}
QMenu::item:selected {{ background: {SELECCION}; color: {TEXTO}; }}
QMenu::item:disabled {{ color: {TEXTO_TENUE}; }}
QMenu::icon {{ padding-left: 8px; }}
QMenu::separator {{ height: 1px; background: {BORDE}; margin: 5px 6px; }}
/* ---------- Medida (botón de la barra y su menú) ---------- */
QPushButton#botonSegmento[activo="true"] {{
    background: {SELECCION}; border: 1px solid {MAGENTA}; color: {TEXTO}; font-weight: 600;
}}
#filaMedida {{ background: transparent; border: 1px solid transparent; border-radius: 8px; }}
#filaMedida[elegida="true"] {{ background: #3d2a39; border: 1px solid {BORDE_SELECCION}; }}
#filaMedida:hover, #filaMedida[activa="true"] {{ background: {SELECCION}; }}
#nombreMedida {{ color: {TEXTO}; font-weight: 600; }}
#proporcionMedida {{
    color: {MAGENTA}; background: #45283f; border-radius: 5px; padding: 1px 6px;
    font-size: 8.5pt; font-weight: 700;
}}
#pixelesMedida {{ color: {TEXTO_TENUE}; font-size: 9pt; }}
#tituloMedida {{ color: {TEXTO}; font-weight: 700; font-size: 10pt; }}
#notaMedida {{ color: {TEXTO_TENUE}; font-size: 8.5pt; }}
#pastillaMedida {{
    color: {TEXTO}; background: {SELECCION}; border: 1px solid {BORDE_SELECCION}; border-radius: 9px;
    padding: 2px 9px; font-size: 8.5pt; font-weight: 600;
}}
#tituloDialogo {{
    font-family: "Segoe UI Variable Display", "Segoe UI", sans-serif;
    font-size: 13pt; font-weight: 700; color: {TEXTO};
}}
#pasoDialogo {{ color: {TEXTO_2}; }}
#codigoDispositivo {{
    font-family: "Cascadia Mono", "Consolas", monospace; font-size: 26pt; font-weight: 700;
    letter-spacing: 4px; color: #ffffff; background: #37393f; border: 1px solid {BORDE_SELECCION};
    border-radius: 14px; padding: 12px 18px;
}}
"""
