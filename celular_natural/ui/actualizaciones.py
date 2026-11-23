"""Interfaz de las actualizaciones automáticas: banner, conexión con GitHub y botón de versión.

La lógica (GitHub, descarga, SHA-256, instalador) está en ``celular_natural/actualizador.py``;
acá solo se muestra y se coordina con la ventana:

* **Banner** arriba de la ventana (no bloquea): "Hay una versión nueva", "Conectá tu
  cuenta de GitHub", el progreso de la descarga, errores y "Listo, se actualizó".
* **Conectar con GitHub** (device flow): un diálogo con el código grande, "Copiar
  código" y "Abrir github.com/login/device"; espera en segundo plano, con Cancelar.
* **Botón de versión** (``v1.0.0``) junto al nombre de la app, con un menú: buscar
  actualizaciones, conectar o desconectar la cuenta y ver la página de versiones.

Todo el trabajo de red va en un ``QThreadPool`` propio con ``Tarea``. Sin internet
no se muestra nada: solo se anota en el registro (``actualizaciones.log``).

En **NaturalShot Lite** las actualizaciones están apagadas (``activas`` en False) hasta que
haya un repositorio para la Lite: no se busca, no se conecta, no hay banner y no se escribe
el registro. El botón de versión queda como "Acerca de" (el nombre y la versión).
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from html import escape
from typing import TYPE_CHECKING, Callable, Optional

from PySide6.QtCore import QObject, QSize, Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QProgressBar, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from .. import __version__, edicion
from .. import actualizador as act
from ..motor import Cancelado
from . import iconos
from .modo_facil import configuracion
from .tareas import SenalesTarea, Tarea

if TYPE_CHECKING:  # pragma: no cover
    from .ventana import VentanaPrincipal

CLAVE_OMITIR = "actualizaciones/omitir_version"  # "No avisar de esta versión"
CLAVE_NO_PEDIR = "actualizaciones/no_pedir_conexion"  # "No mostrar más" en el aviso de conectar
ESPERA_INSTALADOR = 40.0  # segundos para que arranque el script de instalación (con antivirus puede tardar)


def _mb(n: int) -> str:
    return f"{n / 1024 / 1024:.0f}"


def _fecha_linda(fecha: str) -> str:
    """"2026-10-13" -> "13/10/2026" (si no tiene ese formato, queda igual)."""
    partes = fecha.split("-")
    return "/".join(reversed(partes)) if len(partes) == 3 and all(p.isdigit() for p in partes) else fecha


# ================================================================== banner
class BannerActualizacion(QFrame):
    """Franja arriba de la ventana. El controlador elige qué dice y qué botones tiene."""

    ICONOS = {"nueva": "circle-arrow-up", "conectar": "log-in", "progreso": "download", "listo": "circle-check",
              "aviso": "triangle-alert", "info": "refresh-cw"}

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("bannerActualizacion")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(18, 9, 14, 9)
        capa.setSpacing(6)
        fila = QHBoxLayout()
        fila.setSpacing(12)
        self.icono = QLabel()
        self.icono.setObjectName("iconoBanner")
        self.icono.setFixedSize(34, 34)
        self.icono.setAlignment(Qt.AlignCenter)
        fila.addWidget(self.icono, 0, Qt.AlignVCenter)
        textos = QVBoxLayout()
        textos.setSpacing(0)
        self.titulo = QLabel()
        self.titulo.setObjectName("tituloBanner")
        self.detalle = QLabel()
        self.detalle.setObjectName("detalleBanner")
        self.detalle.setTextInteractionFlags(Qt.TextSelectableByMouse)
        for etiqueta in (self.titulo, self.detalle):
            etiqueta.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)  # se recortan si no entran
        textos.addWidget(self.titulo)
        textos.addWidget(self.detalle)
        fila.addLayout(textos, 1)
        self.boton_novedades = QPushButton(" Ver novedades")
        self.boton_novedades.setObjectName("botonEnlace")
        self.boton_novedades.setIcon(iconos.icono("chevron-right", 14))
        self.boton_novedades.setCheckable(True)
        self.boton_novedades.setCursor(Qt.PointingHandCursor)
        self.boton_novedades.toggled.connect(self._alternar_notas)
        fila.addWidget(self.boton_novedades)
        self.progreso = QProgressBar()
        self.progreso.setObjectName("progresoBanner")
        self.progreso.setTextVisible(False)
        self.progreso.setFixedWidth(220)
        fila.addWidget(self.progreso)
        self._caja_botones = QHBoxLayout()
        self._caja_botones.setSpacing(8)
        fila.addLayout(self._caja_botones)
        self.boton_cerrar = QPushButton()
        self.boton_cerrar.setObjectName("botonCerrarBanner")
        self.boton_cerrar.setIcon(iconos.icono("x", 16))
        self.boton_cerrar.setToolTip("Ocultar este aviso")
        self.boton_cerrar.setCursor(Qt.PointingHandCursor)
        self.boton_cerrar.clicked.connect(self.ocultar)
        fila.addWidget(self.boton_cerrar)
        capa.addLayout(fila)
        self.notas = QLabel()
        self.notas.setObjectName("notasBanner")
        self.notas.setWordWrap(True)
        self.notas.setTextFormat(Qt.RichText)
        self.notas.setContentsMargins(46, 0, 0, 2)
        capa.addWidget(self.notas)
        self.botones: dict[str, QPushButton] = {}
        self.tipo = ""
        self.hide()

    def mostrar(self, tipo: str, titulo: str, detalle: str = "",
                botones: tuple = (), notas: tuple = (), progreso: Optional[tuple] = None,
                cerrable: bool = True) -> None:
        """``botones``: tuplas (clave, texto, función, estilo, ícono) con estilo "primario",
        "normal" o "enlace". ``progreso``: (valor, máximo) o (0, 0) para "ocupado"."""
        self.tipo = tipo
        self.setProperty("tipo", tipo)
        self.style().unpolish(self)
        self.style().polish(self)
        self.icono.setPixmap(iconos.pixmap(self.ICONOS.get(tipo, "info"), 18, color="#ffffff"))
        self.titulo.setText(titulo)
        self.detalle.setText(detalle)
        self.detalle.setVisible(bool(detalle))
        self.setToolTip(detalle if len(detalle) > 90 else "")
        while self._caja_botones.count():
            item = self._caja_botones.takeAt(0)
            if item.widget() is not None:  # se saca ya (deleteLater recién borra en el próximo ciclo)
                item.widget().hide()
                item.widget().setParent(None)
                item.widget().deleteLater()
        self.botones = {}
        for clave, texto, funcion, estilo, icono in botones:
            b = QPushButton(texto)
            b.setCursor(Qt.PointingHandCursor)
            if estilo == "primario":
                b.setObjectName("botonPrimario")
                if icono:
                    b.setIcon(iconos.icono(icono, 16, color="#ffffff"))
            elif estilo == "enlace":
                b.setObjectName("botonEnlace")
            elif icono:
                b.setIcon(iconos.icono(icono, 16))
            b.clicked.connect(funcion)
            self._caja_botones.addWidget(b)
            self.botones[clave] = b
        self.boton_novedades.setVisible(bool(notas))
        self.boton_novedades.setChecked(False)
        if notas:
            self.notas.setText("".join(f"<div style='margin:2px 0'>•&nbsp;&nbsp;{escape(n)}</div>" for n in notas))
        self.notas.hide()
        self.progreso.setVisible(progreso is not None)
        if progreso is not None:
            self.progreso.setRange(0, progreso[1])
            self.progreso.setValue(progreso[0])
        self.boton_cerrar.setVisible(cerrable)
        self.show()

    def actualizar_progreso(self, valor: int, maximo: int, detalle: str) -> None:
        self.progreso.setRange(0, maximo)
        self.progreso.setValue(valor)
        self.detalle.setText(detalle)

    def _alternar_notas(self, abiertas: bool) -> None:
        self.notas.setVisible(abiertas)
        self.boton_novedades.setIcon(iconos.icono("chevron-down" if abiertas else "chevron-right", 14))
        self.boton_novedades.setText(" Ocultar novedades" if abiertas else " Ver novedades")

    def ocultar(self) -> None:
        self.tipo = ""
        self.hide()


# ================================================================== diálogo de conexión
class DialogoConexion(QDialog):
    """Device flow de GitHub: muestra el código y espera a que la persona autorice."""

    def __init__(self, parent: Optional[QWidget], al_cancelar: Callable[[], None], al_reintentar: Callable[[], None]):
        super().__init__(parent)
        self.setObjectName("dialogoConexion")
        self.setWindowTitle("Conectar con GitHub")
        self.setModal(True)
        self.setMinimumWidth(500)
        self._al_cancelar = al_cancelar
        self._codigo = ""
        self._url = "https://github.com/login/device"
        self._vence = 0.0
        capa = QVBoxLayout(self)
        capa.setContentsMargins(26, 22, 26, 20)
        capa.setSpacing(12)
        cabecera = QHBoxLayout()
        cabecera.setSpacing(12)
        icono = QLabel()
        icono.setObjectName("iconoBanner")
        icono.setFixedSize(38, 38)
        icono.setAlignment(Qt.AlignCenter)
        icono.setPixmap(iconos.pixmap("log-in", 20, color="#ffffff"))
        cabecera.addWidget(icono)
        textos = QVBoxLayout()
        textos.setSpacing(0)
        titulo = QLabel("Conectar con GitHub")
        titulo.setObjectName("tituloDialogo")
        sub = QLabel("Una sola vez: así NaturalShot puede bajar las versiones nuevas.")
        sub.setObjectName("nota")
        textos.addWidget(titulo)
        textos.addWidget(sub)
        cabecera.addLayout(textos, 1)
        capa.addLayout(cabecera)

        self.paso1 = QLabel("1.&nbsp;&nbsp;Abrí <b>github.com/login/device</b> con la cuenta de GitHub con la que "
                            "te invitaron.")
        self.paso2 = QLabel("2.&nbsp;&nbsp;Escribí este código:")
        for etiqueta in (self.paso1, self.paso2):
            etiqueta.setWordWrap(True)
            etiqueta.setTextFormat(Qt.RichText)
            etiqueta.setObjectName("pasoDialogo")
        capa.addWidget(self.paso1)
        capa.addWidget(self.paso2)
        self.etiqueta_codigo = QLabel("· · · ·  · · · ·")
        self.etiqueta_codigo.setObjectName("codigoDispositivo")
        self.etiqueta_codigo.setAlignment(Qt.AlignCenter)
        self.etiqueta_codigo.setTextInteractionFlags(Qt.TextSelectableByMouse)
        capa.addWidget(self.etiqueta_codigo)
        fila = QHBoxLayout()
        fila.setSpacing(8)
        self.boton_copiar = QPushButton(" Copiar código")
        self.boton_copiar.setIcon(iconos.icono("copy", 16))
        self.boton_copiar.clicked.connect(self.copiar)
        self.boton_abrir = QPushButton(" Abrir github.com/login/device")
        self.boton_abrir.setObjectName("botonPrimario")
        self.boton_abrir.setIcon(iconos.icono("external-link", 16, color="#ffffff"))
        self.boton_abrir.clicked.connect(self.abrir_navegador)
        for b in (self.boton_copiar, self.boton_abrir):
            b.setCursor(Qt.PointingHandCursor)
        fila.addWidget(self.boton_copiar, 1)
        fila.addWidget(self.boton_abrir, 2)
        capa.addLayout(fila)
        self.paso3 = QLabel("3.&nbsp;&nbsp;Tocá <b>Continue</b> y después <b>Authorize</b>. Esta ventana se cierra "
                            "sola.")
        self.paso3.setWordWrap(True)
        self.paso3.setTextFormat(Qt.RichText)
        self.paso3.setObjectName("pasoDialogo")
        capa.addWidget(self.paso3)

        self.espera = QProgressBar()
        self.espera.setRange(0, 0)
        self.espera.setTextVisible(False)
        capa.addWidget(self.espera)
        self.estado = QLabel("Pidiendo un código a GitHub…")
        self.estado.setObjectName("nota")
        self.estado.setWordWrap(True)
        capa.addWidget(self.estado)
        pie = QHBoxLayout()
        pie.addStretch(1)
        self.boton_reintentar = QPushButton(" Pedir otro código")
        self.boton_reintentar.setIcon(iconos.icono("refresh-cw", 16))
        self.boton_reintentar.clicked.connect(al_reintentar)
        self.boton_reintentar.hide()
        self.boton_cancelar = QPushButton("Cancelar")
        self.boton_cancelar.clicked.connect(self.reject)
        pie.addWidget(self.boton_reintentar)
        pie.addWidget(self.boton_cancelar)
        capa.addLayout(pie)
        self._habilitar_codigo(False)
        self._timer = QTimer(self, interval=1000)
        self._timer.timeout.connect(self._cuenta_regresiva)

    def _habilitar_codigo(self, si: bool) -> None:
        self.boton_copiar.setEnabled(si)
        self.boton_abrir.setEnabled(si)

    def pidiendo(self) -> None:
        self.etiqueta_codigo.setText("· · · ·  · · · ·")
        self.estado.setText("Pidiendo un código a GitHub…")
        self.espera.show()
        self.boton_reintentar.hide()
        self.boton_cancelar.setText("Cancelar")
        self._habilitar_codigo(False)

    def mostrar_codigo(self, codigo: "act.CodigoDispositivo") -> None:
        self._codigo = codigo.codigo_usuario
        self._url = codigo.url_verificacion
        self._vence = time.monotonic() + codigo.expira_en
        self.etiqueta_codigo.setText(self._codigo)
        self._habilitar_codigo(True)
        self._cuenta_regresiva()
        self._timer.start()

    def _cuenta_regresiva(self) -> None:
        resta = max(0, int(self._vence - time.monotonic()))
        self.estado.setText(f"Esperando que autorices en GitHub…  (el código vence en {resta // 60}:{resta % 60:02d})")

    def mostrar_error(self, mensaje: str, reintentar: bool = True) -> None:
        self._timer.stop()
        self.espera.hide()
        self.estado.setText(mensaje)
        self.boton_reintentar.setVisible(reintentar)
        self.boton_cancelar.setText("Cerrar")
        self._habilitar_codigo(False)

    def copiar(self) -> None:
        if self._codigo:
            QGuiApplication.clipboard().setText(self._codigo)
            self.boton_copiar.setText(" Copiado")
            QTimer.singleShot(1500, lambda: self.boton_copiar.setText(" Copiar código"))

    def abrir_navegador(self) -> None:
        if self._codigo:
            self.copiar()  # así solo hay que pegarlo
        QDesktopServices.openUrl(QUrl(self._url))

    def reject(self) -> None:
        self._timer.stop()
        self._al_cancelar()
        super().reject()

    def terminar(self) -> None:
        self._timer.stop()
        super().accept()


# ================================================================== controlador
class ControladorActualizaciones(QObject):
    """Coordina la búsqueda, la conexión, la descarga y la instalación con la ventana."""

    def __init__(self, ventana: "VentanaPrincipal"):
        super().__init__(ventana)
        self._ventana = ventana
        # La Lite todavía no tiene repositorio: sin actualizaciones automáticas. En Mac tampoco: las
        # versiones nuevas se bajan desde Pyro (act.plataforma_con_actualizaciones).
        self.activas = not edicion.es_lite() and act.plataforma_con_actualizaciones()
        self._auto = act.modo_prueba_auto() and self.activas
        self.banner = BannerActualizacion()
        self.boton_version = QPushButton(f"v{__version__}")
        self.boton_version.setObjectName("botonVersion")
        self.boton_version.setIcon(iconos.icono("refresh-cw" if self.activas else "info", 12))
        self.boton_version.setIconSize(QSize(12, 12))
        self.boton_version.setCursor(Qt.PointingHandCursor)
        if self.activas:
            self.boton_version.setToolTip(f"NaturalShot PRO {__version__}. Tocá para buscar actualizaciones.")
        elif not edicion.es_lite():
            self.boton_version.setToolTip(f"{edicion.nombre_app()} {__version__}. Las versiones nuevas se bajan "
                                          "desde Pyro: menú del usuario > Descargar NaturalShot.")
        else:
            self.boton_version.setToolTip(f"{edicion.nombre_app()} {__version__}.")
        self.boton_version.clicked.connect(self.mostrar_menu)

        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)  # la conexión puede esperar mientras se busca
        self._senales = SenalesTarea(self)
        self._senales.terminada.connect(self._tarea_terminada)
        self._senales.fallida.connect(self._tarea_fallida)
        self._gen = {"buscar": 0, "conexion": 0, "descarga": 0}
        self._buscando = False
        self._manual = False
        self._novedad: Optional[act.Novedad] = None
        self._paquete: Optional[act.PaqueteListo] = None
        self._descargando = False
        self._dialogo: Optional[DialogoConexion] = None
        self._usuario = ""
        self._instalador = None
        self._instalacion = None
        self._script = None
        self._inicio_instalador = 0.0
        self.cerrando_para_actualizar = False
        self._timer_exportacion = QTimer(self, interval=1000)
        self._timer_exportacion.timeout.connect(self._instalar_cuando_se_pueda)
        self._timer_instalador = QTimer(self, interval=100)
        self._timer_instalador.timeout.connect(self._esperar_instalador)

    # ------------------------------------------------------------ tareas
    def _lanzar(self, tipo: str, grupo: str, funcion: Callable[[Callable[[], bool]], object]) -> None:
        """Ejecuta ``funcion`` en segundo plano. Los errores esperables vuelven como resultado
        (para conservar su tipo); cambiar ``_gen[grupo]`` la cancela."""
        self._gen[grupo] += 1
        generacion = self._gen[grupo]

        def trabajo(cancelado):
            try:
                return "ok", funcion(cancelado)
            except Cancelado:
                raise
            except act.ErrorActualizacion as error:
                return "error", error

        self._pool.start(Tarea(tipo, generacion, trabajo, self._senales, lambda: self._gen[grupo]))

    def _vigente(self, tipo: str, generacion: int) -> bool:
        grupo = {"buscar": "buscar", "codigo": "conexion", "autorizar": "conexion"}.get(tipo, "descarga")
        return generacion == self._gen[grupo]

    def _tarea_terminada(self, tipo: str, generacion: int, resultado) -> None:
        if not self._vigente(tipo, generacion):
            return
        if tipo == "progreso":
            self._progreso(*resultado)
            return
        estado, valor = resultado
        manejadores = {"buscar": (self._busqueda_lista, self._busqueda_fallida),
                       "codigo": (self._codigo_listo, self._conexion_fallida),
                       "autorizar": (self._autorizado, self._conexion_fallida),
                       "descargar": (self._paquete_listo, self._descarga_fallida)}
        bien, mal = manejadores[tipo]
        (bien if estado == "ok" else mal)(valor)

    def _tarea_fallida(self, tipo: str, generacion: int, mensaje: str) -> None:
        """Errores inesperados (no de red): se anotan y, si lo pidió la persona, se muestran."""
        if not self._vigente(tipo, generacion):
            return
        act.registrar(f"Error inesperado en {tipo}: {mensaje}")
        error = act.ErrorActualizacion(f"Algo salió mal ({mensaje}).")
        {"buscar": self._busqueda_fallida, "codigo": self._conexion_fallida, "autorizar": self._conexion_fallida,
         "descargar": self._descarga_fallida}.get(tipo, lambda _e: None)(error)

    # ------------------------------------------------------------ inicio
    def al_iniciar(self) -> None:
        """Al abrir la app: avisa cómo terminó la última actualización y busca otra en segundo plano."""
        if not self.activas:
            return
        act.registrar(f"Inicio: NaturalShot {__version__} ({sys.executable if act.compilada() else 'desde el código'}).")
        act.limpiar_temporales_viejos()
        if self._mostrar_resultado_anterior() and self._auto:
            # Modo de prueba: después de una actualización (bien o mal) no se vuelve a intentar.
            self._captura_prueba("prueba_resultado.png")
            self._fin_prueba("se mostró el resultado de la actualización anterior")
            return
        if not act.configurado():
            act.registrar("Búsqueda: las actualizaciones no están configuradas (falta el Client ID).")
            self._fin_prueba()
            return
        if act.cargar_sesion() is None:
            if self._auto:
                self.conectar()
            elif not configuracion().value(CLAVE_NO_PEDIR, False, type=bool) and not self.banner.isVisible():
                self._banner_conectar()
            return
        self.buscar(manual=False)

    def _mostrar_resultado_anterior(self) -> bool:
        """Avisa cómo terminó la última actualización (lo dejó el instalador). True si había algo."""
        resultado = act.leer_resultado_anterior()
        if not resultado:
            return False
        estado = resultado.get("estado")
        nueva, anterior = resultado.get("version_nueva", "?"), resultado.get("version_anterior", "?")
        detalle = str(resultado.get("detalle") or "")
        act.registrar(f"Resultado de la última actualización: {estado} (versión abierta: {__version__}).")
        if estado == "ok" and nueva == __version__:
            self.banner.mostrar("listo", f"Listo: NaturalShot se actualizó a la versión {__version__}.",
                                "Tus preferencias y presets siguen como estaban.")
        elif estado == "ok":
            self.banner.mostrar("aviso", "La actualización terminó, pero se abrió otra versión.",
                                f"Se instaló la {nueva} y está corriendo la {__version__}.")
        elif estado == "restaurado":
            self.banner.mostrar("aviso", f"No se pudo instalar la versión {nueva}: seguís con la {anterior}.",
                                f"Se restauró la versión anterior. Motivo: {detalle}")
        elif estado == "abortado":
            self.banner.mostrar("aviso", f"No se instaló la versión {nueva}.", detalle)
        else:
            self.banner.mostrar("aviso", "La actualización falló y no se pudo restaurar sola.",
                                f"{detalle} Si NaturalShot no anda, volvé a descomprimir el zip de la versión.")
        return True

    # ------------------------------------------------------------ búsqueda
    def buscar(self, manual: bool = True, mostrar: bool = True) -> None:
        if not self.activas or self._descargando or self._paquete is not None:
            return
        if not act.configurado():
            self._informar("Actualizaciones sin configurar",
                           "Esta copia de NaturalShot todavía no tiene configuradas las actualizaciones "
                           "automáticas (falta el Client ID de la GitHub App). Mirá el README.")
            return
        if act.cargar_sesion() is None:
            self.conectar()
            return
        self._manual = manual
        self._buscando = True
        if manual and mostrar:
            self.banner.mostrar("info", "Buscando actualizaciones…", "", progreso=(0, 0), cerrable=False)
        self._lanzar("buscar", "buscar", lambda _c: act.buscar_actualizacion(__version__))

    def _busqueda_lista(self, novedad: Optional[act.Novedad]) -> None:
        self._buscando = False
        if novedad is None:
            if self._manual:
                self.banner.mostrar("listo", f"Tenés la última versión ({__version__}).")
                QTimer.singleShot(6000, lambda: self.banner.tipo == "listo" and self.banner.ocultar())
            elif self.banner.tipo in ("info", "listo") and self.banner.progreso.isVisible():
                self.banner.ocultar()
            self._fin_prueba("no hay versión nueva")
            return
        self._novedad = novedad
        self.boton_version.setProperty("hayNueva", True)
        self.boton_version.style().unpolish(self.boton_version)
        self.boton_version.style().polish(self.boton_version)
        self.boton_version.setToolTip(f"Hay una versión nueva: {novedad.version}. Tocá para ver las opciones.")
        omitida = configuracion().value(CLAVE_OMITIR, "")
        if omitida == novedad.version and not self._manual and not novedad.obligatoria:
            act.registrar(f"Aviso: la versión {novedad.version} está marcada como \"No avisar\".")
            return
        self._banner_novedad()
        if self._auto:
            act.registrar(f"Prueba automática: aviso mostrado (versión {novedad.version}).")
            self._captura_prueba("prueba_banner.png")
            QTimer.singleShot(1500, self.actualizar_ahora)

    def _busqueda_fallida(self, error: act.ErrorActualizacion) -> None:
        self._buscando = False
        act.registrar(f"Búsqueda: {type(error).__name__}: {error}")
        if isinstance(error, act.SinConexion):
            if self._manual:
                self.banner.mostrar("aviso", "No se pudo buscar actualizaciones.",
                                    "Revisá la conexión a internet y probá de nuevo.",
                                    botones=(("reintentar", "Reintentar", lambda: self.buscar(True), "normal",
                                              "refresh-cw"),))
            elif self.banner.tipo == "info":
                self.banner.ocultar()
        elif isinstance(error, act.SinSesion):
            self._banner_conectar()
        elif isinstance(error, act.SesionVencida):
            self.banner.mostrar("conectar", "Tu sesión de GitHub venció.",
                                "Volvé a conectar tu cuenta para seguir recibiendo actualizaciones.",
                                botones=(("conectar", " Conectar con GitHub", self.conectar, "primario", "log-in"),
                                         ("luego", "Más tarde", self.banner.ocultar, "normal", None)))
        elif isinstance(error, act.SinAcceso):
            self.banner.mostrar("aviso", "Tu cuenta de GitHub no tiene acceso a las actualizaciones.",
                                "Pedile al dueño que te invite y aceptá la invitación que te llega por mail.",
                                botones=(("reintentar", "Reintentar", lambda: self.buscar(True), "normal", "refresh-cw"),
                                         ("desconectar", "Usar otra cuenta", self.reconectar, "enlace", None)))
        elif self._manual:
            self.banner.mostrar("aviso", "No se pudo buscar actualizaciones.", str(error))
        elif self.banner.tipo == "info":
            self.banner.ocultar()
        self._fin_prueba(f"error al buscar ({type(error).__name__})")

    def _banner_novedad(self) -> None:
        n = self._novedad
        if n is None:
            return
        fecha = f" · publicada el {_fecha_linda(n.manifiesto.fecha)}" if n.manifiesto.fecha else ""
        if n.obligatoria and n.instalable:
            # NS-103.6: sin "Más tarde", sin "No avisar" y sin la cruz para cerrar el aviso.
            self.banner.mostrar("nueva", f"Actualización obligatoria ({n.version})",
                                f"Tu versión ({__version__}) ya no se puede usar sin actualizar{fecha} · "
                                f"{_mb(n.tamano_zip)} MB",
                                botones=(("actualizar", " Actualizar ahora", self.actualizar_ahora, "primario",
                                          "download"),), notas=n.manifiesto.notas)
            self.banner.boton_cerrar.hide()
            return
        self.banner.boton_cerrar.show()
        botones = [("actualizar", " Actualizar ahora", self.actualizar_ahora, "primario", "download"),
                   ("luego", "Más tarde", self.mas_tarde, "normal", None),
                   ("omitir", "No avisar de esta versión", self.omitir_version, "enlace", None)]
        self.banner.mostrar("nueva", f"Hay una versión nueva ({n.version})",
                            f"Tenés la {__version__}{fecha} · {_mb(n.tamano_zip)} MB",
                            botones=tuple(botones), notas=n.manifiesto.notas)

    def _banner_conectar(self) -> None:
        self.banner.mostrar("conectar", "Conectá tu cuenta de GitHub para recibir actualizaciones",
                            "Una sola vez, con la cuenta con la que te invitaron. NaturalShot avisa solo cuando "
                            "hay una versión nueva.",
                            botones=(("conectar", " Conectar con GitHub", self.conectar, "primario", "log-in"),
                                     ("luego", "Más tarde", self.banner.ocultar, "normal", None),
                                     ("nunca", "No mostrar más", self._no_pedir_conexion, "enlace", None)))

    def mas_tarde(self) -> None:
        """Se oculta hasta el próximo inicio (el botón de versión sigue marcado)."""
        if self._novedad is not None and self._novedad.obligatoria:
            return
        self.banner.ocultar()

    def omitir_version(self) -> None:
        if self._novedad is not None and self._novedad.obligatoria:
            return
        if self._novedad is not None:
            config = configuracion()
            config.setValue(CLAVE_OMITIR, self._novedad.version)
            config.sync()
            act.registrar(f"Aviso: no avisar de la versión {self._novedad.version}.")
        self.banner.ocultar()

    def _no_pedir_conexion(self) -> None:
        config = configuracion()
        config.setValue(CLAVE_NO_PEDIR, True)
        config.sync()
        self.banner.ocultar()

    # ------------------------------------------------------------ cuenta de GitHub
    def conectar(self) -> None:
        if not self.activas:
            return
        if not act.configurado():
            self.buscar(manual=True)  # explica que falta configurar
            return
        if self._dialogo is None:
            self._dialogo = DialogoConexion(self._ventana, self._cancelar_conexion, self._pedir_codigo)
            self._dialogo.finished.connect(self._dialogo_cerrado)
        self._pedir_codigo()
        self._dialogo.open()  # no bloquea: la búsqueda y lo demás siguen andando

    def _pedir_codigo(self) -> None:
        if self._dialogo is not None:
            self._dialogo.pidiendo()
        self._lanzar("codigo", "conexion", lambda _c: act.pedir_codigo())

    def _codigo_listo(self, codigo: act.CodigoDispositivo) -> None:
        if self._dialogo is None:
            return
        self._dialogo.mostrar_codigo(codigo)
        act.registrar("Conexión: código pedido; esperando la autorización.")
        self._lanzar("autorizar", "conexion", lambda cancelado: act.esperar_autorizacion(codigo, cancelado))

    def _autorizado(self, sesion: act.Sesion) -> None:
        try:
            act.guardar_sesion(sesion)
        except Exception as error:  # noqa: BLE001 - se informa
            self._conexion_fallida(act.ErrorActualizacion(f"No se pudo guardar la sesión: {error}"))
            return
        self._usuario = sesion.usuario
        if self._dialogo is not None:
            self._dialogo.terminar()
        quien = f" como @{sesion.usuario}" if sesion.usuario else ""
        self.banner.mostrar("listo", f"Cuenta de GitHub conectada{quien}.", "Buscando actualizaciones…",
                            progreso=(0, 0), cerrable=False)
        self.buscar(manual=True, mostrar=False)

    def _conexion_fallida(self, error: act.ErrorActualizacion) -> None:
        act.registrar(f"Conexión: {type(error).__name__}: {error}")
        if isinstance(error, act.SinConexion):
            mensaje = "No hay conexión con GitHub. Revisá internet y pedí otro código."
        else:
            mensaje = str(error)
        if self._dialogo is not None:
            self._dialogo.mostrar_error(mensaje, not isinstance(error, act.ConfiguracionInvalida))
        self._fin_prueba("no se pudo conectar")

    def _cancelar_conexion(self) -> None:
        self._gen["conexion"] += 1  # corta la espera en menos de un segundo

    def _dialogo_cerrado(self, _resultado: int) -> None:
        self._gen["conexion"] += 1
        if self._dialogo is not None:
            self._dialogo.deleteLater()
            self._dialogo = None

    def desconectar(self) -> None:
        act.borrar_sesion()
        self._usuario = ""
        self.banner.mostrar("info", "Se desconectó tu cuenta de GitHub.",
                            "Para volver a recibir actualizaciones, tocá la versión (arriba a la izquierda) "
                            "y elegí \"Conectar con GitHub\".")
        QTimer.singleShot(8000, lambda: self.banner.tipo == "info" and self.banner.ocultar())

    def reconectar(self) -> None:
        act.borrar_sesion()
        self.conectar()

    # ------------------------------------------------------------ menú de la versión
    def mostrar_menu(self) -> None:
        menu = QMenu(self.boton_version)
        menu.setObjectName("menuVersion")
        titulo = menu.addAction(f"{edicion.nombre_app()} {__version__}")
        titulo.setEnabled(False)
        if not self.activas:  # Lite: solo "Acerca de"
            nota = menu.addAction("Solo fotos · procesado local, sin IA generativa")
            nota.setEnabled(False)
            menu.exec(self.boton_version.mapToGlobal(self.boton_version.rect().bottomLeft()))
            return
        menu.addSeparator()
        if self._paquete is not None:  # bajada pero pospuesta ("Más tarde")
            menu.addAction(iconos.icono("circle-arrow-up", 16),
                           f"Instalar la versión {self._paquete.novedad.version} (ya descargada)",
                           self._instalar_cuando_se_pueda)
        elif self._novedad is not None and not self._descargando:
            menu.addAction(iconos.icono("circle-arrow-up", 16), f"Ver la versión nueva ({self._novedad.version})",
                           self._banner_novedad)
        buscar = menu.addAction(iconos.icono("refresh-cw", 16), "Buscar actualizaciones", lambda: self.buscar(True))
        buscar.setEnabled(not self._buscando and not self._descargando and self._paquete is None)
        menu.addSeparator()
        sesion = act.cargar_sesion() if act.configurado() else None
        if sesion is not None:
            usuario = self._usuario or sesion.usuario
            cuenta = menu.addAction(f"Cuenta de GitHub: @{usuario}" if usuario else "Cuenta de GitHub conectada")
            cuenta.setEnabled(False)
            menu.addAction(iconos.icono("log-out", 16), "Desconectar la cuenta de GitHub", self.desconectar)
        elif act.configurado():
            menu.addAction(iconos.icono("log-in", 16), "Conectar con GitHub…", self.conectar)
        menu.addAction(iconos.icono("external-link", 16), "Abrir la página de versiones", self.abrir_pagina)
        menu.exec(self.boton_version.mapToGlobal(self.boton_version.rect().bottomLeft()))

    def abrir_pagina(self) -> None:
        url = self._novedad.pagina if self._novedad is not None else act.pagina_releases()
        QDesktopServices.openUrl(QUrl(url))

    # ------------------------------------------------------------ descarga
    def actualizar_ahora(self) -> None:
        n = self._novedad
        if not self.activas or n is None or self._descargando:
            return
        if self._paquete is not None:
            self._instalar_cuando_se_pueda()
            return
        if not act.compilada():
            self._informar("Actualizar a mano",
                           f"Estás usando NaturalShot desde el código, así que no se puede reemplazar sola.\n\n"
                           f"Para pasar a la {n.version}, actualizá el código o bajá el zip de la página de la "
                           f"versión.", pagina=True)
            return
        if not n.instalable:
            self._informar("Actualizar a mano",
                           f"La versión {n.version} no se puede instalar sola desde la {__version__} "
                           f"(necesita la {n.manifiesto.minima} o más nueva). Bajá el zip de la página de la "
                           f"versión y descomprimilo en lugar de la carpeta actual.", pagina=True)
            return
        try:
            instalacion = act.validar_instalacion(act.carpeta_instalacion())
        except act.ErrorActualizacion as error:
            self._informar("No se puede actualizar sola", f"{error}\n\nBajá la versión nueva de la página.",
                           pagina=True)
            return
        if not act.se_puede_escribir(instalacion):
            act.registrar(f"Descarga: sin permiso de escritura en {instalacion}.")
            self._informar("Sin permiso para actualizar",
                           f"NaturalShot está en una carpeta donde no puede escribir:\n{instalacion}\n\n"
                           "Pasá la carpeta de NaturalShot a otro lugar (por ejemplo, Documentos o el "
                           "Escritorio) y volvé a abrirla, o bajá la versión nueva de la página.", pagina=True)
            return
        trabajo = act.nueva_carpeta_trabajo()
        if not act.espacio_suficiente(trabajo, instalacion, n.tamano_zip):
            shutil.rmtree(trabajo, ignore_errors=True)
            self._informar("Falta espacio en el disco",
                           f"Para actualizar hacen falta unos {_mb(n.tamano_zip * 4)} MB libres. "
                           "Liberá espacio y probá de nuevo.")
            return
        self._instalacion = instalacion
        self._descargando = True
        act.registrar(f"Descarga: empieza la versión {n.version} en {trabajo}.")
        senales = self._senales

        def trabajo_descarga(cancelado):
            generacion = self._gen["descarga"]
            return act.preparar_paquete(
                n, trabajo, lambda hechos, total: senales.terminada.emit("progreso", generacion, (hechos, total)),
                cancelado)

        self.banner.mostrar("progreso", f"Descargando la versión {n.version}…", f"0 de {_mb(n.tamano_zip)} MB",
                            botones=(("cancelar", "Cancelar", self.cancelar_descarga, "normal", None),),
                            progreso=(0, 1000), cerrable=False)
        self._lanzar("descargar", "descarga", trabajo_descarga)

    def _progreso(self, hechos: int, total: int) -> None:
        if not self._descargando:
            return
        porcentaje = 100 * hechos / max(1, total)
        texto = f"{_mb(hechos)} de {_mb(total)} MB · {porcentaje:.0f} %"
        if hechos >= total:
            texto = "Verificando el archivo y preparando la instalación…"
            self.banner.titulo.setText("Preparando la actualización…")
        self.banner.actualizar_progreso(round(1000 * hechos / max(1, total)), 1000, texto)

    def cancelar_descarga(self) -> None:
        if not self._descargando:
            return
        self._gen["descarga"] += 1  # la tarea lo ve en el siguiente bloque y borra lo bajado
        self._descargando = False
        act.registrar("Descarga: cancelada.")
        self._banner_novedad()

    def _descarga_fallida(self, error: act.ErrorActualizacion) -> None:
        self._descargando = False
        act.registrar(f"Descarga: {type(error).__name__}: {error}")
        if isinstance(error, act.SinConexion):
            texto = "Se cortó la conexión. Probá de nuevo en un rato."
        else:
            texto = str(error)
        botones = [("reintentar", "Reintentar", self.actualizar_ahora, "normal", "refresh-cw"),
                   ("pagina", "Abrir la página de la versión", self.abrir_pagina, "enlace", None)]
        if isinstance(error, (act.SesionVencida, act.SinSesion)):
            botones[0] = ("conectar", " Conectar con GitHub", self.conectar, "primario", "log-in")
        self.banner.mostrar("aviso", "No se pudo descargar la actualización. No se instaló nada.", texto,
                            botones=tuple(botones))
        self._fin_prueba(f"falló la descarga ({type(error).__name__})")

    # ------------------------------------------------------------ instalación
    def _paquete_listo(self, paquete: act.PaqueteListo) -> None:
        self._descargando = False
        self._paquete = paquete
        self._instalar_cuando_se_pueda()

    def _exportando(self) -> bool:
        return self._ventana.exportando_algo()

    def _instalar_cuando_se_pueda(self) -> None:
        """Si hay una exportación en curso, espera a que termine; después confirma y cierra."""
        if self._paquete is None:
            self._timer_exportacion.stop()
            return
        version = self._paquete.novedad.version
        if self._exportando():
            if not self._timer_exportacion.isActive():
                act.registrar("Instalación: esperando a que termine una exportación.")
                self.banner.mostrar("progreso", f"La versión {version} está lista para instalar.",
                                    "Hay una exportación en curso: NaturalShot se actualiza apenas termine.",
                                    botones=(("cancelar", "Instalar después", self._posponer, "normal", None),),
                                    progreso=(0, 0), cerrable=False)
                self._timer_exportacion.start()
            return
        self._timer_exportacion.stop()
        # Con la sesión activa no se pierde nada: al volver a abrir están las mismas fotos y ediciones.
        if not self._auto and self._ventana.tiene_ediciones() and not self._ventana.recuerda_sesion:
            respuesta = QMessageBox.question(
                self._ventana, "Actualizar NaturalShot",
                f"La versión {version} está lista. Para instalarla, NaturalShot se cierra y se vuelve a abrir "
                "sola en unos segundos.\n\nTenés fotos abiertas con cambios: lo que no exportaste se pierde. "
                "¿Actualizar ahora?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if respuesta != QMessageBox.Yes:
                self._posponer()
                return
        self._lanzar_instalador()

    def _posponer(self) -> None:
        self._timer_exportacion.stop()
        if self._paquete is None:
            return
        self.banner.mostrar("nueva", f"La versión {self._paquete.novedad.version} está descargada y lista.",
                            "Cuando quieras, NaturalShot se cierra, se actualiza y se vuelve a abrir sola.",
                            botones=(("instalar", " Reiniciar y actualizar", self._instalar_cuando_se_pueda,
                                      "primario", "refresh-cw"),
                                     ("luego", "Más tarde", self.banner.ocultar, "normal", None)),
                            notas=self._paquete.novedad.manifiesto.notas)

    def _lanzar_instalador(self) -> None:
        paquete = self._paquete
        try:
            script = act.generar_script(paquete, self._instalacion, os.getpid(), __version__,
                                        simular_falla=os.environ.get(act.VAR_FALLA) == "1")
            act.marca_inicio(script).unlink(missing_ok=True)
            self._instalador = act.lanzar_instalador(script)
        except (act.ErrorActualizacion, OSError) as error:
            act.registrar(f"Instalación: no se pudo lanzar el instalador: {error}")
            self._error_instalador(str(error))
            return
        self._script = script
        self._inicio_instalador = time.monotonic()
        self.banner.mostrar("progreso", f"Instalando la versión {paquete.novedad.version}…",
                            "NaturalShot se va a cerrar y volver a abrir sola en unos segundos.",
                            progreso=(0, 0), cerrable=False)
        self._timer_instalador.start()

    def _esperar_instalador(self) -> None:
        """Se cierra recién cuando el instalador avisa que arrancó (si no, la app sigue abierta)."""
        if act.marca_inicio(self._script).exists():
            self._timer_instalador.stop()
            act.registrar("Instalación: el instalador arrancó; se cierra la app.")
            self._cerrar_app()
            return
        termino = self._instalador is not None and self._instalador.poll() is not None
        if termino or time.monotonic() - self._inicio_instalador > ESPERA_INSTALADOR:
            self._timer_instalador.stop()
            if not termino:
                try:
                    self._instalador.kill()
                except OSError:
                    pass
            act.registrar("Instalación: el instalador no arrancó (¿PowerShell bloqueado?).")
            self._error_instalador("Windows no dejó iniciar el instalador (puede ser el antivirus o una "
                                   "política de PowerShell).")

    def _error_instalador(self, detalle: str) -> None:
        if self._paquete is not None:
            shutil.rmtree(self._paquete.trabajo, ignore_errors=True)
        self._paquete = None
        self.banner.mostrar("aviso", "No se pudo instalar la actualización. NaturalShot sigue como estaba.",
                            f"{detalle} Podés bajar la versión nueva de la página y descomprimirla a mano.",
                            botones=(("pagina", "Abrir la página de la versión", self.abrir_pagina, "normal",
                                      "external-link"),))
        self._fin_prueba("no se pudo lanzar el instalador")

    def _cerrar_app(self) -> None:
        """Cierre ordenado: la ventana (con el editor de video adentro; espera exportaciones) y la
        aplicación. Se llega acá solo sin exportaciones en curso (``_instalar_cuando_se_pueda``)."""
        self.cerrando_para_actualizar = True
        self._ventana.close()
        QApplication.quit()

    # ------------------------------------------------------------ varios
    def _informar(self, titulo: str, texto: str, pagina: bool = False) -> None:
        act.registrar(f"Aviso: {titulo}.")
        if self._auto:
            self._fin_prueba(titulo)
            return
        caja = QMessageBox(QMessageBox.Information, titulo, texto, QMessageBox.Ok, self._ventana)
        abrir = caja.addButton("Abrir la página de la versión", QMessageBox.ActionRole) if pagina else None
        caja.exec()
        if abrir is not None and caja.clickedButton() is abrir:
            self.abrir_pagina()

    def _captura_prueba(self, nombre: str) -> None:
        """Modo de prueba: guarda una captura de la ventana con el aviso (para revisar). Se toma
        un momento después, cuando los botones nuevos del banner ya están ubicados."""
        def capturar():
            try:
                ruta = act.carpeta_datos() / nombre
                ruta.parent.mkdir(parents=True, exist_ok=True)
                self._ventana.grab().save(str(ruta))
            except Exception:  # noqa: BLE001 - es solo para las pruebas
                pass
        QTimer.singleShot(400, capturar)

    def _fin_prueba(self, motivo: str = "") -> None:
        """Modo de prueba: si no queda nada por hacer, la app se cierra sola."""
        if self._auto and not self.cerrando_para_actualizar:
            act.registrar(f"Prueba automática: termina ({motivo or 'nada para hacer'}).")
            QTimer.singleShot(1500, self._ventana.close)

    def detener(self) -> None:
        """Al cerrar la app: corta la búsqueda, la conexión y la descarga en curso."""
        for grupo in self._gen:
            self._gen[grupo] += 1
        self._timer_exportacion.stop()
        if not self.cerrando_para_actualizar:
            self._timer_instalador.stop()
            if self._paquete is not None:  # bajado pero no instalado: no se deja basura
                shutil.rmtree(self._paquete.trabajo, ignore_errors=True)
        self._pool.clear()
        self._pool.waitForDone(3000)
