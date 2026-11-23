"""Escuchar en la vista previa: un ``QAudioSink`` alimentado por un ``LectorPCM``.

Pieza reutilizable (la usa el editor de video y la puede usar un futuro modo
Audio): no depende del editor. Suena el **resultado** (lo borrado se saltea, con
los silencios, los fundidos y el volumen ya aplicados) y dice qué instante del
original está sonando, para mover la imagen al ritmo del sonido.

* Formato fijo: 48 kHz, estéreo, int16 (``LectorPCM`` por defecto).
* Modo "push": la interfaz escribe en el búfer del sink (unos 0,3 s) cada 20 ms,
  desde el hilo principal. No hay código de Python en hilos de Qt: nada de
  filtros ni de ``readData`` llamados desde el hilo del audio.
* ``posicion()``: el instante del original que está sonando, con
  ``processedUSecs()`` (lo que ya tomó el dispositivo). Si se traba la
  alimentación, el sonido se corta y la posición se queda quieta: la imagen
  espera al sonido.
* Si QtMultimedia no carga, si no hay salida de sonido o si la plataforma es
  "offscreen" (las pruebas: así no suenan en los parlantes), ``disponible`` es
  False, ``motivo`` dice por qué y todo lo demás no hace nada: quien lo usa sigue
  con su propio reloj, sin sonido y sin errores. Con la variable
  ``NATURALSHOT_AUDIO_OFFSCREEN=1`` también se usa la salida en "offscreen".
* Si el dispositivo falla a mitad (por ejemplo, se desconectan los auriculares),
  se detiene y emite ``fallo``; en el próximo ``reproducir`` se busca de nuevo la
  salida predeterminada.
* ``reproducir_lector``: suena cualquier lector con la interfaz de ``LectorPCM``
  (``leer``, ``bytes_por_muestra``, ``tiene_audio``, ``terminado``,
  ``posicion_resultado``, ``original_de_resultado``, ``ir_a``, ``cerrar``…), por
  ejemplo el ``MezcladorAudio`` del modo Audio. Un lector con lectura adelantada
  puede devolver ``b""`` sin haber terminado (se le acabó el búfer): eso no corta
  nada; el fin lo dice ``terminado``.

QtMultimedia se importa recién al crear el primer reproductor.
"""

from __future__ import annotations

import os
from typing import Callable, Optional, Sequence, Union

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from ..motor import audio as ma

FRECUENCIA = 48000
CANALES = 2
BUFER = 0.3            # s de sonido en el búfer del sink: aguanta trabas cortas de la interfaz
INTERVALO_ALIMENTAR = 20  # ms
VARIABLE_OFFSCREEN = "NATURALSHOT_AUDIO_OFFSCREEN"


def _cargar_qtmultimedia():
    """El módulo ``PySide6.QtMultimedia`` (aparte, para poder simular que falla)."""
    from PySide6 import QtMultimedia
    return QtMultimedia


class ReproductorAudio(QObject):
    """Sonido de la vista previa (ver el docstring del módulo).

    Uso: ``reproducir(ruta, tramos, ajustes, desde, pico)`` arranca desde el instante
    ``desde`` del original (o ``reproducir_lector(lector)``, con un lector ya armado);
    ``posicion()`` dice qué instante suena; ``ir_a``, ``cambiar_ajustes`` y ``detener``
    mientras suena; ``cerrar`` al final. ``silenciado`` hace que ``reproducir`` no suene
    (quien lo usa sigue con su reloj).
    """

    terminado = Signal()   # sonó hasta el final de lo que se conserva
    fallo = Signal(str)    # el dispositivo dejó de andar (se detuvo)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.motivo = ""          # por qué no está disponible (vacío si lo está)
        self.silenciado = False
        self._qtm = None
        self._formato = None
        self._sink = None
        self._id_dispositivo = None
        self._io = None
        self._lector: Optional[ma.LectorPCM] = None
        self._pendiente = b""     # lo que el sink no aceptó en la última escritura
        self._base = 0.0          # segundo del resultado donde arrancó el sink actual
        self._sonando = False
        self._volumen = 1.0
        self._timer = QTimer(self, interval=INTERVALO_ALIMENTAR)
        self._timer.timeout.connect(self._alimentar)
        self._preparar()

    # ------------------------------------------------------------ preparación
    def _preparar(self) -> None:
        if (QGuiApplication.platformName() == "offscreen" and os.environ.get(VARIABLE_OFFSCREEN) != "1"):
            self.motivo = "Sin pantalla (pruebas): la vista previa no suena."
            return
        try:
            qtm = _cargar_qtmultimedia()
            formato = qtm.QAudioFormat()
            formato.setSampleRate(FRECUENCIA)
            formato.setChannelCount(CANALES)
            formato.setSampleFormat(qtm.QAudioFormat.SampleFormat.Int16)
        except Exception as error:  # QtMultimedia no está o no carga: se sigue sin sonido
            self.motivo = f"No se pudo usar el sonido de Qt ({error.__class__.__name__})."
            return
        self._qtm, self._formato = qtm, formato
        self._buscar_salida()

    def _buscar_salida(self) -> bool:
        """Usa la salida de sonido predeterminada (si cambió desde la vez anterior, arma otro sink)."""
        if self._qtm is None:
            return False
        try:
            dispositivo = self._qtm.QMediaDevices.defaultAudioOutput()
            if dispositivo.isNull():
                self._soltar_sink()
                self.motivo = "No hay ninguna salida de sonido."
                return False
            if self._sink is not None and dispositivo.id() == self._id_dispositivo:
                return True
            if not dispositivo.isFormatSupported(self._formato):
                self._soltar_sink()
                self.motivo = f"La salida de sonido «{dispositivo.description()}» no acepta 48 kHz estéreo."
                return False
            self._soltar_sink()
            sink = self._qtm.QAudioSink(dispositivo, self._formato, self)
            sink.setBufferSize(int(BUFER * FRECUENCIA) * CANALES * 2)
            sink.setVolume(self._volumen)
            self._sink, self._id_dispositivo = sink, dispositivo.id()
            self.motivo = ""
            return True
        except Exception as error:
            self._soltar_sink()
            self.motivo = f"No se pudo abrir la salida de sonido ({error.__class__.__name__})."
            return False

    def _soltar_sink(self) -> None:
        sink, self._sink, self._io, self._id_dispositivo = self._sink, None, None, None
        if sink is not None:
            try:
                sink.stop()
            except Exception:
                pass
            sink.deleteLater()

    # ------------------------------------------------------------ estado
    @property
    def disponible(self) -> bool:
        """Si hay salida de sonido para usar (aunque esté silenciado)."""
        return self._sink is not None

    def hay_salida(self) -> bool:
        """Como ``disponible``, pero busca otra vez la salida predeterminada (si cambió o se había
        perdido). Sirve para no armar un lector en vano cuando igual no va a sonar."""
        return self._buscar_salida()

    @property
    def sonando(self) -> bool:
        return self._sonando

    @property
    def lector(self) -> Optional[ma.LectorPCM]:
        return self._lector

    def establecer_silenciado(self, silenciado: bool) -> None:
        """Silenciado, ``reproducir`` no suena. Si estaba sonando, se detiene."""
        self.silenciado = bool(silenciado)
        if self.silenciado:
            self.detener()

    def establecer_volumen_salida(self, volumen: float) -> None:
        """Volumen del dispositivo (0 a 1). No cambia lo que se exporta (eso va en ``AjustesAudio``)."""
        self._volumen = max(0.0, min(1.0, float(volumen)))
        if self._sink is not None:
            self._sink.setVolume(self._volumen)

    def posicion(self) -> Optional[float]:
        """Instante del original que está sonando ahora (None si no suena)."""
        if not self._sonando or self._sink is None or self._lector is None:
            return None
        return self._lector.original_de_resultado(self._base + self._sink.processedUSecs() / 1e6)

    # ------------------------------------------------------------ control
    def reproducir(self, ruta: str, tramos: Optional[Sequence[tuple[float, float]]], ajustes: ma.AjustesAudio,
                   desde: float, pico: Optional[float] = None) -> bool:
        """Empieza a sonar desde ``desde`` (tiempo original). True si de verdad suena.

        ``tramos``: los que se conservan (None = todo). ``pico``: el de ``medir_pico``
        si se normaliza; si falta, suena como si el pico fuera 0 dBFS hasta que llegue
        con ``cambiar_ajustes`` (así nunca se traba midiendo)."""
        self.detener()
        if self.silenciado or ajustes.quitar or not self._buscar_salida():
            return False
        try:
            lector = ma.LectorPCM(ruta, tramos, ajustes, desde=desde, frecuencia=FRECUENCIA, canales=CANALES,
                                  formato="s16", pico=self._pico(ajustes, pico))
        except Exception as error:  # el archivo no se puede leer: se sigue sin sonido
            self.motivo = f"No se pudo leer el sonido ({error.__class__.__name__})."
            return False
        if not lector.tiene_audio or lector.terminado:
            lector.cerrar()
            return False
        self._lector = lector
        return self._arrancar()

    def reproducir_lector(self, lector: Union[object, Callable[[], object]]) -> bool:
        """Empieza a sonar con un lector ya armado (por ejemplo, un ``MezcladorAudio``),
        desde donde está. True si de verdad suena.

        ``lector``: el lector o una función sin argumentos que lo arma. Con una función,
        el lector se arma solo si va a sonar (silenciado o sin salida de sonido no se arma
        nada). El reproductor se queda con él: lo cierra al detenerse o, si no suena, enseguida.
        Para cambiar lo que suena sin cortar, quien lo usa le habla al lector (``lector``),
        por ejemplo ``cambiar_proyecto``."""
        self.detener()
        es_fabrica = callable(lector) and not hasattr(lector, "leer")
        if self.silenciado or not self._buscar_salida():
            if not es_fabrica:
                self._cerrar_otro(lector)
            return False
        if es_fabrica:
            try:
                lector = lector()
            except Exception as error:  # no se pudo armar (el archivo no está, etc.): se sigue sin sonido
                self.motivo = f"No se pudo leer el sonido ({error.__class__.__name__})."
                return False
        if lector is None or not lector.tiene_audio or lector.terminado:
            self._cerrar_otro(lector)
            return False
        self._lector = lector
        return self._arrancar()

    @staticmethod
    def _cerrar_otro(lector) -> None:
        if lector is not None and hasattr(lector, "cerrar"):
            try:
                lector.cerrar()
            except Exception:
                pass

    def _arrancar(self) -> bool:
        try:
            self._base = self._lector.posicion_resultado
            self._pendiente = b""
            self._io = self._sink.start()
        except Exception as error:
            self.motivo = f"No se pudo abrir la salida de sonido ({error.__class__.__name__})."
            self._io = None
        if self._io is None:
            self._cerrar_lector()
            return False
        self._sonando = True
        self._alimentar()
        self._timer.start()
        return True

    def ir_a(self, t: float) -> bool:
        """Salta al instante ``t`` del original sin cambiar nada más. True si sigue sonando."""
        if not self._sonando or self._lector is None:
            return False
        self._timer.stop()
        self._sonando = False
        try:
            self._sink.stop()  # descarta lo que quedaba en el búfer
        except Exception:
            pass
        self._lector.ir_a(t)
        if self._lector.terminado:
            self._cerrar_lector()
            return False
        return self._arrancar()

    def cambiar_ajustes(self, ajustes: ma.AjustesAudio, pico: Optional[float] = None) -> None:
        """Ajustes nuevos sin moverse (se oyen después de lo que ya está en el búfer, unos 0,3 s)."""
        if self._lector is not None:
            if ajustes.quitar:
                self.detener()
                return
            self._lector.cambiar_ajustes(ajustes, self._pico(ajustes, pico))

    @staticmethod
    def _pico(ajustes: ma.AjustesAudio, pico: Optional[float]) -> Optional[float]:
        return pico if pico is not None or not ajustes.normalizar else 1.0

    def detener(self) -> None:
        self._timer.stop()
        estaba = self._sonando
        self._sonando = False
        if estaba and self._sink is not None:
            try:
                self._sink.stop()
            except Exception:
                pass
        self._io = None
        self._cerrar_lector()

    def _cerrar_lector(self) -> None:
        lector, self._lector = self._lector, None
        if lector is not None:
            lector.cerrar()

    def cerrar(self) -> None:
        """Al terminar: detiene y suelta el dispositivo."""
        self.detener()
        self._soltar_sink()

    # ------------------------------------------------------------ alimentar
    # El estado del sink se mira por nombre y en cada vuelta, sin conectarse a ``stateChanged``: en
    # PySide 6.12 esa señal trae el tipo viejo ``QAudio::State`` (que no se puede convertir) y
    # ``state()`` devuelve ``QtAudio.State``, distinto de ``QAudio.State`` al comparar.
    def _estado(self) -> str:
        return self._sink.state().name

    def _alimentar(self) -> None:
        if not self._sonando or self._sink is None or self._io is None or self._lector is None:
            return
        try:
            if self._estado() == "StoppedState" and self._sink.error().name != "NoError":
                self.detener()
                self._soltar_sink()  # en el próximo reproducir se busca otra vez la salida
                self.fallo.emit("La salida de sonido dejó de responder.")
                return
            libres = self._sink.bytesFree()
            if self._pendiente:
                escritos = self._io.write(self._pendiente)
                self._pendiente = self._pendiente[max(0, escritos):]
                libres -= max(0, escritos)
                if self._pendiente:
                    return
            muestras = libres // self._lector.bytes_por_muestra
            if muestras >= FRECUENCIA // 200 and not self._lector.terminado:  # de a 5 ms o más
                datos = self._lector.leer(muestras)
                if datos:
                    escritos = self._io.write(datos)
                    self._pendiente = datos[max(0, escritos):]
            elif self._lector.terminado and not self._pendiente:
                # Ya se escribió todo: cuando el sink vacía su búfer, terminó.
                if self._estado() == "IdleState":
                    self.detener()
                    self.terminado.emit()
        except Exception as error:  # nunca rompe la interfaz: se sigue sin sonido
            self.detener()
            self.fallo.emit(f"El sonido se cortó ({error.__class__.__name__}).")


__all__ = ["ReproductorAudio", "FRECUENCIA", "CANALES", "BUFER", "VARIABLE_OFFSCREEN"]
