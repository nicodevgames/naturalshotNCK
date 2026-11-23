"""Pruebas del kit para flyers del modo Photoshop (NaturalShot Lite), con la ventana real sin pantalla.

Nuevo lienzo, varias imágenes a la vez (en cascada), texto como capa, quitar fondo y exportar.
Usan un APPDATA y un .ini temporales, e imágenes generadas.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
if "NATURALSHOT_CONFIG" not in os.environ:
    import atexit
    _CARPETA_CONFIG = tempfile.mkdtemp(prefix="naturalshot_config_")
    atexit.register(shutil.rmtree, _CARPETA_CONFIG, True)
    os.environ["NATURALSHOT_CONFIG"] = os.path.join(_CARPETA_CONFIG, "preferencias.ini")


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def foto_color(w, h, color, semilla=0) -> np.ndarray:
    rng = np.random.default_rng(semilla)
    base = np.zeros((h, w, 3), np.float32) + np.array(color, np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    base += 40 * np.sin(xx / 30.0)[..., None] + rng.normal(0, 3, (h, w, 1))
    return np.clip(base, 0, 255).astype(np.uint8)


def circulo(w=400, h=300) -> np.ndarray:
    """Un círculo naranja sobre un fondo celeste liso."""
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = (150, 200, 235)
    yy, xx = np.mgrid[0:h, 0:w]
    dentro = (xx - w / 2) ** 2 + (yy - h / 2) ** 2 < (min(w, h) * 0.32) ** 2
    img[dentro] = (240, 120, 20)
    return img


class PruebasKitFlyer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PIL import Image
        cls.app = _app()
        cls.carpeta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        base = Path(cls.carpeta.name)
        cls._entorno = {k: os.environ.get(k) for k in ("APPDATA", "NATURALSHOT_CONFIG", "NATURALSHOT_EDICION")}
        os.environ["APPDATA"] = str(base / "appdata")
        os.environ["NATURALSHOT_EDICION"] = "lite"
        os.environ["NATURALSHOT_CONFIG"] = str(base / "config.ini")
        cls.base = base
        cls.fotos = []
        for i, color in enumerate(((200, 60, 60), (60, 160, 80), (60, 90, 200), (220, 180, 40))):
            r = base / f"foto{i + 1}.png"
            Image.fromarray(foto_color(640, 480, color, i)).save(r)
            cls.fotos.append(r)
        cls.ruta_circulo = base / "circulo.png"
        Image.fromarray(circulo()).save(cls.ruta_circulo)

    @classmethod
    def tearDownClass(cls):
        for clave, valor in cls._entorno.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
        cls.carpeta.cleanup()

    def setUp(self):
        from celular_natural.ui.ventana import VentanaPrincipal
        self.v = VentanaPrincipal()
        self.v.resize(1366, 768)
        self.v.show()
        self.v.establecer_modo("photoshop", guardar=False)

    def tearDown(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        self.v.close()
        self.v.deleteLater()
        self.app.processEvents()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    # ------------------------------------------------------------ ayudas
    def quieto(self) -> bool:
        v = self.v
        return (v._imagen is not None and not v._fuentes_pendientes and v._deteccion is None
                and v._generacion_completa_mostrada == v._generacion and not v._exportando
                and not v._quitando_fondo and v._pool_archivos.activeThreadCount() == 0)

    def esperar(self, condicion=None, segundos=90.0):
        condicion = condicion or self.quieto
        fin = time.monotonic() + segundos
        while time.monotonic() < fin:
            self.app.processEvents()
            if condicion():
                for _ in range(5):
                    self.app.processEvents()
                if condicion():
                    return
            time.sleep(0.005)
        self.fail("no se cumplió a tiempo")

    def lienzo(self, ancho=1080, alto=1920, color=(255, 255, 255)):
        self.v.nuevo_lienzo(ancho, alto, color)
        self.esperar(lambda: self.quieto() and self.v._fuente is not None
                     and self.v._fuente.shape[:2] == (alto, ancho))

    def imagenes(self):
        return [c for c in self.v._documento.capas if c.tipo == "imagen"]

    def agregar_cuatro(self):
        self.v.agregar_imagenes_como_capa([str(r) for r in self.fotos])
        self.esperar(lambda: len(self.imagenes()) == 4 and self.quieto())

    # ------------------------------------------------------------ pruebas
    def test_nuevo_abre_un_documento_de_ese_tamano(self):
        self.lienzo(1080, 1920, (0, 0, 0))
        v = self.v
        self.assertEqual(v._modo, "photoshop")
        self.assertEqual((v._documento.ancho, v._documento.alto), (1080, 1920))
        self.assertEqual(int(v._fuente.max()), 0)  # negro
        # Ctrl+N está en el modo Photoshop y el botón también.
        self.assertTrue(v.boton_nuevo.isVisible())

    def test_cuatro_imagenes_a_la_vez_dan_cuatro_capas_en_cascada(self):
        self.lienzo()
        self.agregar_cuatro()
        capas = self.imagenes()
        self.assertEqual(len(capas), 4)
        xs = [c.transform.x for c in capas]
        self.assertEqual(len(set(xs)), 4, "en cascada: cada una corrida")
        for c in capas:  # entran en el lienzo
            self.assertLessEqual(c.transform.escala * 640, 1080)

    def test_soltar_varias_las_agrega_todas(self):
        from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
        from PySide6.QtGui import QDragEnterEvent, QDropEvent
        from PySide6.QtWidgets import QApplication
        self.lienzo(1080, 1080)
        datos = QMimeData()
        datos.setUrls([QUrl.fromLocalFile(str(r)) for r in self.fotos[:3]])
        w = self.v.vista
        centro = w.rect().center()
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            entrar = QDragEnterEvent(centro, Qt.CopyAction, datos, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(w, entrar)
        QApplication.sendEvent(w, QDropEvent(QPointF(centro), Qt.CopyAction, datos, Qt.LeftButton, Qt.NoModifier))
        self.esperar(lambda: len(self.imagenes()) == 3 and self.quieto())

    def test_agregar_texto_da_una_capa_de_texto_vivo(self):
        # Desde U2, el texto del kit es una capa de texto vivo (y el botón elige la herramienta Texto).
        from celular_natural.ui.kit_flyer import datos_texto_por_defecto
        self.lienzo()
        datos = {**datos_texto_por_defecto(), "texto": "Gran apertura\neste sábado", "color": (230, 30, 120)}
        self.v.agregar_texto(datos)
        self.esperar()
        textos = [c for c in self.v._documento.capas if c.tipo == "texto"]
        self.assertEqual(len(textos), 1)
        self.assertEqual(textos[0].nombre, "Gran apertura")
        self.assertEqual(textos[0].params.contenido, "Gran apertura\neste sábado")
        self.assertEqual(textos[0].params.color, (230, 30, 120, 255))
        self.assertIn("sombra", textos[0].estilos.activos)
        # Editarlo: con la capa elegida, cambia ese texto (no agrega otro).
        self.v.agregar_texto({**datos, "texto": "Otro texto"})
        self.esperar()
        textos = [c for c in self.v._documento.capas if c.tipo == "texto"]
        self.assertEqual(len(textos), 1)
        self.assertEqual(textos[0].params.contenido, "Otro texto")
        # El botón Texto elige la herramienta.
        self.v.boton_texto.click()
        self.assertEqual(self.v.photoshop.herramienta, "texto")

    def test_quitar_fondo_deja_las_esquinas_transparentes(self):
        self.lienzo(1080, 1080)
        self.v.agregar_imagenes_como_capa([str(self.ruta_circulo)])
        self.esperar(lambda: len(self.imagenes()) == 1 and self.quieto())
        capa = self.imagenes()[0]
        self.assertEqual(self.v.panel_capas.capa_elegida, capa.id)
        self.v.quitar_fondo_capa()
        self.esperar(lambda: self.quieto() and self.imagenes()[0].imagen != capa.imagen)
        arr = self.v._arreglo(self.imagenes()[0].imagen)
        self.assertEqual(arr.shape[2], 4)
        h, w = arr.shape[:2]
        for y, x in ((2, 2), (2, w - 3), (h - 3, 2), (h - 3, w - 3)):
            self.assertLess(int(arr[y, x, 3]), 30)
        self.assertGreater(int(arr[h // 2, w // 2, 3]), 200)
        self.assertTrue(self.v._historial[self.v._pos_historial][0].startswith("Fondo quitado"))

    def test_quitar_fondo_de_la_foto_agrega_capa_y_la_oculta(self):
        self.v.agregar_fotos([str(self.ruta_circulo)])
        self.esperar()
        self.v.panel_capas.elegir_sin_avisar("foto")
        self.v._actualizar_habilitados()
        self.v.quitar_fondo_capa()
        self.esperar(lambda: self.quieto() and len(self.imagenes()) == 1)
        self.assertFalse(self.v._documento.capa("foto").visible)

    def test_recortar_en_una_foto_es_la_herramienta(self):
        # U3: en una foto, "Recortar" elige la herramienta Recortar ahí mismo (su recorte sigue siendo el
        # no destructivo de siempre: ver test_pintura_ui); ya no lleva al Editor.
        self.v.agregar_fotos([str(self.ruta_circulo)])
        self.esperar()
        self.v.recortar_desde_photoshop()
        self.assertEqual(self.v._modo, "photoshop")
        self.assertEqual(self.v.photoshop.herramienta, "recortar")
        self.assertFalse(self.v.boton_recortar.isChecked())
        self.v.cancelar_herramienta()

    def test_recortar_un_documento_nuevo_recorta_el_lienzo(self):
        # En un documento nuevo (sin foto), "Recortar" recorta el lienzo ahí mismo, en el modo Photoshop.
        from PySide6.QtCore import QRectF
        self.lienzo(1080, 1080)
        self.v.recortar_desde_photoshop()
        self.assertEqual(self.v._modo, "photoshop")
        self.assertEqual(self.v.photoshop.herramienta, "recortar")
        self.v.photoshop.caja_recorte_actual().rect = QRectF(0, 0, 540, 1080)
        self.v._confirmar_herramienta()
        self.esperar(lambda: self.quieto() and self.v._documento.ancho == 540)
        self.assertEqual(self.v._fuente.shape[:2], (1080, 540))

    def test_exportar_el_flyer_da_un_png_de_ese_tamano(self):
        from PIL import Image
        from PySide6.QtWidgets import QFileDialog
        from celular_natural.ui.kit_flyer import datos_texto_por_defecto
        self.lienzo()
        self.agregar_cuatro()
        self.v.agregar_texto({**datos_texto_por_defecto(), "texto": "Flyer"})
        self.esperar()
        destino = self.base / "flyer.png"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "PNG (*.png)")):
            self.v.exportar()
        self.esperar(lambda: not self.v._exportando and destino.exists())
        with Image.open(destino) as im:
            self.assertEqual(im.size, (1080, 1920))


if __name__ == "__main__":
    unittest.main()
