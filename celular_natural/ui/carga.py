"""Pantalla de carga: aparece apenas se abre la app, mientras cargan NumPy, OpenCV,
el motor y la ventana, y se va con un fundido cuando aparece la ventana principal.

Solo usa PySide6 y ``estilo.py`` (nada del motor), así ``main.py`` la puede mostrar
antes de importar lo pesado. Se dibuja entera con QPainter, a unos 60 cuadros por
segundo, sobre una ventana sin marco y con fondo translúcido:

* una tarjeta gris oscura (la paleta de ``estilo.py``) con esquinas redondeadas,
  borde fino y una sombra suave;
* el logo, que "respira" (escala 1 ± 2,5 %) delante de un halo magenta y violeta
  que pulsa; cada tanto lo cruza un brillo y titila la estrellita del logo;
* "NaturalShot PRO" (o "NaturalShot Lite", con la insignia violeta) y "Editor de fotos realistas";
* una barra de progreso con degradado rosa → magenta → violeta, con un reflejo que
  la recorre, y el texto de la etapa del arranque ("Preparando el motor…").

La barra nunca salta: avanza suave hacia el valor de cada etapa y, en una etapa
larga, sigue avanzando despacio hacia el valor siguiente (``etapa(..., hasta=)``).

``revelar`` hace el pase a la ventana principal: la pantalla de carga se desvanece
mientras la ventana (maximizada) aparece con un fundido y una subida de 14 px, en
``DURACION_ENTRADA`` ms.
"""

from __future__ import annotations

import math
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import (
    QAbstractAnimation, QEasingCurve, QElapsedTimer, QEventLoop, QPointF, QRectF, Qt, QTimer, QVariantAnimation,
)
from PySide6.QtGui import (
    QColor, QCursor, QFont, QFontMetricsF, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath,
    QPixmap, QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QWidget

from .. import edicion
from . import estilo

# Medidas (px lógicos)
ANCHO, ALTO = 400, 300  # la tarjeta
MARGEN = 30  # alrededor de la tarjeta, para la sombra
COLOR_LITE = "#a78bfa"  # el comienzo de la insignia LITE (lavanda; termina en el violeta de estilo.py)
RADIO = 18
LADO_LOGO = 92
CENTRO_LOGO_Y = 98  # desde el borde de arriba de la tarjeta
ESTRELLA = (0.73, 0.27)  # dónde está la estrellita dentro del logo (fracción del lado)
# Tiempos
CUADRO_MS = 16
RESPIRO_S = 2.6  # período del "respirar" del logo y del halo
BRILLO_S = 3.2  # cada cuánto cruza el brillo por el logo
DURACION_ENTRADA = 380  # ms: fundido de la pantalla de carga y entrada de la ventana
SUBIDA_ENTRADA = 14  # px que sube la ventana al aparecer
MINIMO_VISIBLE = 0.7  # s: aunque todo cargue al instante, que se vea la animación


def _soporta_opacidad() -> bool:
    """Las plataformas sin pantalla (pruebas) no manejan la opacidad de las ventanas."""
    return QGuiApplication.platformName() not in ("offscreen", "minimal")


def _opacidad(ventana: QWidget, valor: float) -> None:
    if _soporta_opacidad():
        ventana.setWindowOpacity(max(0.0, min(1.0, valor)))


class PantallaCarga(QWidget):
    def __init__(self, ruta_logo: Optional[Path | str] = None, version: str = ""):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.insignia = edicion.insignia()  # "PRO" o "LITE"
        self.setWindowTitle(edicion.nombre_app())
        self.setFixedSize(ANCHO + 2 * MARGEN, ALTO + 2 * MARGEN)
        self._logo = QPixmap(str(ruta_logo)) if ruta_logo and Path(ruta_logo).exists() else QPixmap()
        self._version = f"v{version}" if version else ""
        self._reloj = QElapsedTimer()
        self._reloj.start()
        self._ultimo = 0.0
        self._mostrado = 0.0  # lo que se ve de la barra (0..1)
        self._objetivo = 0.0  # adonde va
        self._hasta: Optional[float] = None  # en una etapa larga, sigue despacio hasta acá
        self._texto = ""
        self._texto_anterior = ""
        self._cambio_texto = -10.0  # cuándo cambió el texto (para el fundido)
        self._pintada_en: Optional[float] = None  # time.monotonic() del primer cuadro dibujado
        self._fondo: Optional[QPixmap] = None  # sombra, tarjeta y textos fijos (se dibujan una vez)
        self._fuentes()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(CUADRO_MS)
        self._timer.timeout.connect(self._cuadro)
        self._centrar()

    # ------------------------------------------------------------ uso desde main.py
    def mostrar(self) -> None:
        """Se muestra y espera (un instante) a que el primer cuadro esté en pantalla."""
        self.show()
        self.raise_()
        self._timer.start()
        fin = time.monotonic() + 0.3
        while self._pintada_en is None and time.monotonic() < fin:
            QApplication.processEvents(QEventLoop.AllEvents, 20)

    @property
    def visible_desde(self) -> Optional[float]:
        """``time.monotonic()`` del primer cuadro dibujado (None si todavía no se vio)."""
        return self._pintada_en

    def etapa(self, texto: str, valor: float, hasta: Optional[float] = None) -> None:
        """Pasa a otra etapa del arranque: la barra va hacia ``valor`` (0..1) y, si la
        etapa tarda, sigue avanzando despacio hacia ``hasta``."""
        if texto != self._texto:
            self._texto_anterior, self._texto = self._texto, texto
            self._cambio_texto = self._segundos()
        self._objetivo = max(self._objetivo, min(1.0, valor))
        self._hasta = hasta
        self.update()
        QApplication.processEvents()

    def respirar(self) -> None:
        """Atiende los eventos pendientes (entre partes de un trabajo largo en el hilo principal)."""
        QApplication.processEvents()

    def esperar(self, condicion: Callable[[], bool], maximo: float) -> bool:
        """Atiende eventos (la animación sigue) hasta que se cumpla ``condicion`` o
        pasen ``maximo`` segundos. Devuelve si se cumplió."""
        if condicion():
            return True
        fin = time.monotonic() + maximo
        bucle = QEventLoop()

        def revisar():
            if condicion() or time.monotonic() >= fin:
                bucle.quit()

        revisor = QTimer()
        revisor.setInterval(10)
        revisor.timeout.connect(revisar)
        revisor.start()
        bucle.exec()
        revisor.stop()
        return condicion()

    def en_segundo_plano(self, funcion: Callable[[], object]) -> None:
        """Corre ``funcion`` en otro hilo mientras la animación sigue (por ejemplo,
        importar NumPy y OpenCV). Si falla, la excepción sale acá, en el hilo principal."""
        error: list[BaseException] = []

        def trabajo():
            try:
                funcion()
            except BaseException as e:  # se relanza en el hilo principal
                error.append(e)

        hilo = threading.Thread(target=trabajo, name="carga", daemon=True)
        hilo.start()
        self.esperar(lambda: not hilo.is_alive(), 600.0)
        hilo.join()
        if error:
            raise error[0]

    def esperar_minimo(self, segundos: float = MINIMO_VISIBLE) -> None:
        """Si todo cargó muy rápido, sigue a la vista hasta completar ``segundos``
        (así se ve la animación y no queda como un parpadeo)."""
        inicio = self._pintada_en if self._pintada_en is not None else time.monotonic()
        restante = segundos - (time.monotonic() - inicio)
        if restante > 0:
            self.esperar(lambda: time.monotonic() - inicio >= segundos, restante + 0.05)

    def terminar(self) -> None:
        self._timer.stop()
        self.close()

    # ------------------------------------------------------------ animación
    def _segundos(self) -> float:
        return self._reloj.elapsed() / 1000.0

    def _cuadro(self) -> None:
        t = self._segundos()
        dt = min(0.1, max(0.0, t - self._ultimo))
        self._ultimo = t
        if self._hasta is not None and self._objetivo < self._hasta:
            # Etapa larga: se acerca despacio al valor siguiente, sin llegar nunca.
            self._objetivo += (self._hasta - self._objetivo) * min(1.0, dt * 0.6)
        self._mostrado += (self._objetivo - self._mostrado) * min(1.0, dt * 9.0)
        if abs(self._objetivo - self._mostrado) < 0.0005:
            self._mostrado = self._objetivo
        self.update()

    def _centrar(self) -> None:
        pantalla = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if pantalla is None:
            return
        zona = pantalla.availableGeometry()
        self.move(zona.center().x() - self.width() // 2, zona.center().y() - self.height() // 2)

    # ------------------------------------------------------------ dibujo
    def _fuentes(self) -> None:
        self._f_titulo = QFont("Segoe UI Variable Display")
        self._f_titulo.setFamilies(["Segoe UI Variable Display", "Segoe UI", "sans-serif"])
        self._f_titulo.setPointSizeF(17.5)
        self._f_titulo.setWeight(QFont.Bold)
        self._f_pro = QFont("Segoe UI")
        self._f_pro.setPointSizeF(7.5)
        self._f_pro.setWeight(QFont.ExtraBold)
        self._f_pro.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
        self._f_sub = QFont("Segoe UI Variable Text")
        self._f_sub.setFamilies(["Segoe UI Variable Text", "Segoe UI", "sans-serif"])
        self._f_sub.setPointSizeF(9.5)
        self._f_estado = QFont(self._f_sub)
        self._f_estado.setPointSizeF(9.0)
        self._f_chica = QFont(self._f_sub)
        self._f_chica.setPointSizeF(8.0)

    def _tarjeta(self) -> QRectF:
        return QRectF(MARGEN, MARGEN, ANCHO, ALTO)

    def _armar_fondo(self) -> QPixmap:
        """Lo que no se mueve: sombra, tarjeta, borde, nombre y subtítulo."""
        dpr = self.devicePixelRatioF()
        pm = QPixmap(round(self.width() * dpr), round(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        tarjeta = self._tarjeta()
        # Sombra suave: capas cada vez más grandes y más tenues, un poco corrida hacia abajo.
        p.setPen(Qt.NoPen)
        pasos = 18
        for i in range(pasos, 0, -1):
            alfa = 0.30 * (1.0 - i / (pasos + 1)) ** 2.2
            p.setBrush(QColor(0, 0, 0, round(alfa * 255 / 3)))
            r = tarjeta.adjusted(-i * 1.4, -i * 1.4 + 6, i * 1.4, i * 1.4 + 8)
            p.drawRoundedRect(r, RADIO + i * 1.4, RADIO + i * 1.4)
        camino = QPainterPath()
        camino.addRoundedRect(tarjeta, RADIO, RADIO)
        fondo = QLinearGradient(tarjeta.topLeft(), tarjeta.bottomLeft())
        fondo.setColorAt(0.0, QColor(estilo.TARJETA))
        fondo.setColorAt(1.0, QColor(estilo.FONDO))
        p.fillPath(camino, fondo)
        # Un resplandor tenue arriba, detrás del logo.
        brillo = QRadialGradient(QPointF(tarjeta.center().x(), tarjeta.top() + CENTRO_LOGO_Y), ANCHO * 0.62)
        violeta = QColor(estilo.VIOLETA)
        violeta.setAlphaF(0.10)
        brillo.setColorAt(0.0, violeta)
        brillo.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.save()
        p.setClipPath(camino)
        p.fillRect(tarjeta, brillo)
        p.restore()
        p.setPen(QColor(estilo.BORDE))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(tarjeta.adjusted(0.5, 0.5, -0.5, -0.5), RADIO, RADIO)
        # Nombre con la insignia PRO, centrados como grupo.
        fm_t, fm_p = QFontMetricsF(self._f_titulo), QFontMetricsF(self._f_pro)
        nombre = "NaturalShot"
        ancho_nombre = fm_t.horizontalAdvance(nombre)
        ancho_pro = fm_p.horizontalAdvance(self.insignia) + 14
        alto_pro = fm_p.height() + 4
        separacion = 8
        x = tarjeta.center().x() - (ancho_nombre + separacion + ancho_pro) / 2
        base = tarjeta.top() + CENTRO_LOGO_Y + LADO_LOGO / 2 + 26 + fm_t.ascent()
        p.setFont(self._f_titulo)
        p.setPen(QColor(estilo.TEXTO))
        p.drawText(QPointF(x, base), nombre)
        pildora = QRectF(x + ancho_nombre + separacion, base - fm_t.ascent() / 2 - alto_pro / 2 - 1,
                         ancho_pro, alto_pro)
        degradado = QLinearGradient(pildora.topLeft(), pildora.bottomRight())
        # PRO: magenta → violeta. LITE: violeta (lavanda → violeta).
        degradado.setColorAt(0.0, QColor(COLOR_LITE if self.insignia == "LITE" else estilo.MAGENTA))
        degradado.setColorAt(1.0, QColor(estilo.VIOLETA))
        p.setPen(Qt.NoPen)
        p.setBrush(degradado)
        p.drawRoundedRect(pildora, 6, 6)
        p.setFont(self._f_pro)
        p.setPen(QColor("#ffffff"))
        p.drawText(pildora, Qt.AlignCenter, self.insignia)
        p.setFont(self._f_sub)
        p.setPen(QColor(estilo.TEXTO_TENUE))
        fm_s = QFontMetricsF(self._f_sub)
        p.drawText(QRectF(tarjeta.left(), base + 8, ANCHO, fm_s.height()), Qt.AlignHCenter | Qt.AlignTop,
                   "Editor de fotos realistas")
        if self._version:
            p.setFont(self._f_chica)
            p.drawText(QRectF(tarjeta.left(), tarjeta.top() + 12, ANCHO - 16, 20), Qt.AlignRight | Qt.AlignTop,
                       self._version)
        p.end()
        return pm

    def paintEvent(self, _evento) -> None:
        if self._fondo is None or abs(self._fondo.devicePixelRatio() - self.devicePixelRatioF()) > 1e-3:
            self._fondo = self._armar_fondo()
        t = self._segundos()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.drawPixmap(0, 0, self._fondo)
        tarjeta = self._tarjeta()
        centro = QPointF(tarjeta.center().x(), tarjeta.top() + CENTRO_LOGO_Y)
        self._dibujar_logo(p, centro, t)
        self._dibujar_barra(p, tarjeta, t)
        p.end()
        if self._pintada_en is None:
            self._pintada_en = time.monotonic()

    def _dibujar_logo(self, p: QPainter, centro: QPointF, t: float) -> None:
        onda = math.sin(2 * math.pi * t / RESPIRO_S)  # -1..1
        # Halo que pulsa (más grande y más intenso cuando el logo "inhala").
        radio = LADO_LOGO * (0.92 + 0.08 * onda)
        halo = QRadialGradient(centro, radio)
        magenta, violeta = QColor(estilo.MAGENTA), QColor(estilo.VIOLETA)
        magenta.setAlphaF(0.30 + 0.10 * onda)
        violeta.setAlphaF(0.14 + 0.05 * onda)
        halo.setColorAt(0.0, magenta)
        halo.setColorAt(0.5, violeta)
        halo.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        p.drawEllipse(centro, radio, radio)
        if self._logo.isNull():
            return
        lado = LADO_LOGO * (1.0 + 0.025 * onda)
        rect = QRectF(centro.x() - lado / 2, centro.y() - lado / 2, lado, lado)
        p.drawPixmap(rect, self._logo, QRectF(self._logo.rect()))
        # Brillo que cruza el logo en diagonal, recortado a su forma (la transparencia del PNG).
        fase = (t % BRILLO_S) / BRILLO_S
        if fase < 0.4:
            n = max(1, round(lado * self.devicePixelRatioF()))  # en píxeles del dispositivo
            capa = QImage(n, n, QImage.Format_ARGB32_Premultiplied)
            capa.fill(Qt.transparent)
            q = QPainter(capa)
            q.setRenderHint(QPainter.SmoothPixmapTransform, True)
            q.scale(n / lado, n / lado)
            avance = QEasingCurve(QEasingCurve.InOutSine).valueForProgress(fase / 0.4)
            x = -0.7 * lado + avance * 2.4 * lado
            banda = QLinearGradient(QPointF(x, 0), QPointF(x + lado * 0.45, lado * 0.3))
            banda.setColorAt(0.0, QColor(255, 255, 255, 0))
            banda.setColorAt(0.5, QColor(255, 255, 255, 95))
            banda.setColorAt(1.0, QColor(255, 255, 255, 0))
            q.fillRect(QRectF(0, 0, lado, lado), banda)
            # La forma del logo, sobre la capa entera en píxeles enteros (sin bordes a medio cubrir).
            q.resetTransform()
            q.setCompositionMode(QPainter.CompositionMode_DestinationIn)
            q.drawPixmap(capa.rect(), self._logo)
            q.end()
            p.drawImage(rect, capa)
        # La estrellita titila justo después de que pasa el brillo.
        titila = max(0.0, math.sin(math.pi * min(1.0, max(0.0, (fase - 0.28) / 0.3))))
        if titila > 0.01:
            e = QPointF(rect.left() + ESTRELLA[0] * lado, rect.top() + ESTRELLA[1] * lado)
            r = lado * (0.10 + 0.06 * titila)
            resplandor = QRadialGradient(e, r * 1.6)
            resplandor.setColorAt(0.0, QColor(255, 255, 255, round(150 * titila)))
            resplandor.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setBrush(resplandor)
            p.drawEllipse(e, r * 1.6, r * 1.6)
            estrella = QPainterPath()
            fino = r * 0.16
            estrella.moveTo(e.x(), e.y() - r)
            estrella.quadTo(e.x() + fino, e.y() - fino, e.x() + r, e.y())
            estrella.quadTo(e.x() + fino, e.y() + fino, e.x(), e.y() + r)
            estrella.quadTo(e.x() - fino, e.y() + fino, e.x() - r, e.y())
            estrella.quadTo(e.x() - fino, e.y() - fino, e.x(), e.y() - r)
            p.fillPath(estrella, QColor(255, 255, 255, round(235 * titila)))

    def _dibujar_barra(self, p: QPainter, tarjeta: QRectF, t: float) -> None:
        izquierda, ancho_barra, alto_barra = tarjeta.left() + 40, ANCHO - 80, 6.0
        y = tarjeta.bottom() - 58
        pista = QRectF(izquierda, y, ancho_barra, alto_barra)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#25272b"))
        p.drawRoundedRect(pista, 3, 3)
        lleno = QRectF(pista.left(), pista.top(), max(alto_barra, ancho_barra * self._mostrado), alto_barra)
        if self._mostrado > 0.001:
            degradado = QLinearGradient(pista.topLeft(), pista.topRight())  # sobre toda la pista
            degradado.setColorAt(0.0, QColor(estilo.ROSA))
            degradado.setColorAt(0.55, QColor(estilo.MAGENTA))
            degradado.setColorAt(1.0, QColor(estilo.VIOLETA))
            camino = QPainterPath()
            camino.addRoundedRect(lleno, 3, 3)
            p.fillPath(camino, degradado)
            # Reflejo que recorre lo lleno.
            fase = (t % 1.6) / 1.6
            x = lleno.left() - 60 + fase * (lleno.width() + 120)
            reflejo = QLinearGradient(QPointF(x - 40, 0), QPointF(x + 40, 0))
            reflejo.setColorAt(0.0, QColor(255, 255, 255, 0))
            reflejo.setColorAt(0.5, QColor(255, 255, 255, 80))
            reflejo.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.fillPath(camino, reflejo)
            # Punta luminosa.
            punta = QRadialGradient(QPointF(lleno.right() - 2, lleno.center().y()), 9)
            rosa = QColor(estilo.MAGENTA)
            rosa.setAlphaF(0.55)
            punta.setColorAt(0.0, rosa)
            punta.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setBrush(punta)
            p.drawEllipse(QPointF(lleno.right() - 2, lleno.center().y()), 9, 9)
        # Texto de la etapa (con un fundido corto al cambiar) y el porcentaje.
        fm = QFontMetricsF(self._f_estado)
        caja = QRectF(izquierda, y + alto_barra + 10, ancho_barra, fm.height() + 2)
        p.setFont(self._f_estado)
        mezcla = min(1.0, (t - self._cambio_texto) / 0.22)
        color = QColor(estilo.TEXTO_2)
        if mezcla < 1.0 and self._texto_anterior:
            color.setAlphaF(1.0 - mezcla)
            p.setPen(color)
            p.drawText(caja.translated(0, -4 * mezcla), Qt.AlignLeft | Qt.AlignVCenter, self._texto_anterior)
        color.setAlphaF(mezcla)
        p.setPen(color)
        p.drawText(caja.translated(0, 4 * (1.0 - mezcla)), Qt.AlignLeft | Qt.AlignVCenter, self._texto)
        p.setPen(QColor(estilo.TEXTO_TENUE))
        p.drawText(caja, Qt.AlignRight | Qt.AlignVCenter, f"{round(self._mostrado * 100)} %")


class _Cortina(QWidget):
    """Una foto de la ventana que sube unos píxeles mientras la ventana se funde al
    aparecer. Tapa la ventana solo esos 400 ms y deja pasar el mouse."""

    def __init__(self, ventana: QWidget, captura: QPixmap):
        super().__init__(ventana)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self._captura = captura
        self._desplazamiento = float(SUBIDA_ENTRADA)
        self.setGeometry(ventana.rect())

    def establecer(self, avance: float) -> None:
        self._desplazamiento = SUBIDA_ENTRADA * (1.0 - avance)
        self.update()

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(estilo.FONDO))
        p.drawPixmap(QPointF(0, round(self._desplazamiento)), self._captura)
        p.end()


def revelar(ventana: QWidget, pantalla: Optional[PantallaCarga] = None,
            al_terminar: Optional[Callable[[], None]] = None, duracion: int = DURACION_ENTRADA) -> None:
    """Muestra la ventana maximizada con un fundido y una leve subida, mientras la
    pantalla de carga se desvanece. ``al_terminar`` se llama cuando ya se ve entera."""
    _opacidad(ventana, 0.0)
    ventana.showMaximized()
    # Que tome el tamaño final y se dibuje una vez (todavía invisible) antes de sacarle la foto.
    for _ in range(3):
        QApplication.processEvents()
    try:
        cortina = _Cortina(ventana, ventana.grab())
        cortina.show()
        cortina.raise_()
    except Exception:  # sin el efecto de subida: queda el fundido
        cortina = None
    animacion = QVariantAnimation(ventana)
    animacion.setStartValue(0.0)
    animacion.setEndValue(1.0)
    animacion.setDuration(duracion)
    animacion.setEasingCurve(QEasingCurve.OutCubic)

    def paso(valor) -> None:
        avance = float(valor)
        _opacidad(ventana, avance * 1.1)
        if cortina is not None:
            cortina.establecer(avance)
        if pantalla is not None:
            _opacidad(pantalla, 1.0 - avance * 1.6)  # se va en el primer 60 % del pase

    def fin() -> None:
        _opacidad(ventana, 1.0)
        if cortina is not None:
            cortina.hide()
            cortina.deleteLater()
        if pantalla is not None:
            pantalla.terminar()
            pantalla.deleteLater()
        if al_terminar is not None:
            al_terminar()

    animacion.valueChanged.connect(paso)
    animacion.finished.connect(fin)
    animacion.start(QAbstractAnimation.DeleteWhenStopped)
