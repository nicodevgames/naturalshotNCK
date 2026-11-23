"""Ejecución en segundo plano para no congelar la interfaz."""

from __future__ import annotations

import traceback
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, Signal

from ..motor import Cancelado


class SenalesTarea(QObject):
    """Debe crearse en el hilo de la interfaz: las señales llegan encoladas a él."""

    terminada = Signal(str, int, object)  # tipo, generación, resultado
    fallida = Signal(str, int, str)  # tipo, generación, mensaje


class Tarea(QRunnable):
    """Ejecuta ``funcion(cancelado)`` y avisa el resultado.

    Si al empezar la generación ya no es la vigente, la tarea se descarta; la
    función también puede consultar ``cancelado()`` para abandonar a mitad de camino.
    """

    def __init__(
        self,
        tipo: str,
        generacion: int,
        funcion: Callable[[Callable[[], bool]], object],
        senales: SenalesTarea,
        generacion_vigente: Callable[[], int] | None = None,
    ):
        super().__init__()
        self.setAutoDelete(True)
        self._tipo = tipo
        self._generacion = generacion
        self._funcion = funcion
        self._senales = senales
        self._vigente = generacion_vigente

    def _cancelado(self) -> bool:
        return self._vigente is not None and self._vigente() != self._generacion

    def run(self) -> None:  # noqa: D401 - API de Qt
        if self._cancelado():
            return
        try:
            resultado = self._funcion(self._cancelado)
        except Cancelado:
            return
        except Exception as error:  # se informa en la interfaz
            detalle = "".join(traceback.format_exception_only(type(error), error)).strip()
            traceback.print_exc()
            self._senales.fallida.emit(self._tipo, self._generacion, detalle)
            return
        self._senales.terminada.emit(self._tipo, self._generacion, resultado)
