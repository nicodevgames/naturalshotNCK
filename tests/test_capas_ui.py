"""Pruebas de la interfaz de capas (NaturalShot Lite, etapa 1), con la ventana real sin pantalla.

Las capas se editan en el modo **Photoshop** de la Lite (sin el filtro); en Fácil y en Editor el
filtro va arriba de todo, sobre la composición. Las pruebas corren en la edición Lite
(``NATURALSHOT_EDICION=lite``) y arrancan en el modo Photoshop.

* **Modo Photoshop:** el selector de la Lite (Fácil | Editor | Photoshop), Ctrl+Shift+P, que se
  recuerde, la vista sin el filtro ("Ver con el filtro" lo muestra), el "Antes" de Fácil y Editor
  (la composición sin el filtro) y soltar una imagen (sin Ctrl) la agrega como capa.
* **Atajos por edición:** en la Lite, Ctrl+S guarda el proyecto y Ctrl+Shift+E exporta; en la PRO,
  Ctrl+S exporta como siempre.

* **Regresión:** sin capas extra, exportar da exactamente lo de antes (``procesar_pila`` sobre la
  foto que entra al filtro), bit a bit; con capas, la exportación es la vista (``componer``).
* **Panel Capas:** agregar (diálogo y Ctrl+arrastrar), reordenar (botones y arrastrando),
  opacidad (un gesto del deslizador = un paso), fusión, máscara (agregar, pintar, invertir,
  ocultar todo, quitar), ocultar, renombrar, candado y borrar; las reglas del motor como avisos.
* **Mover / Transformar** con el mouse simulado (``QTest``): mover, escalar con una esquina,
  rotar, flechas, voltear, Enter (un paso) y Esc (nada).
* **Historial:** cada cambio de capas es un paso; Ctrl+Z / Ctrl+Y.
* **Proyecto ``.nslite``:** guardar y abrir en otra ventana da lo mismo; sin la foto original
  se abre igual, con un aviso.
* **Sesión:** cerrar y volver a abrir conserva las capas (las imágenes, como PNG en la carpeta
  de la sesión).
* **Fácil:** muestra las capas en la vista y lo avisa; exportar desde Fácil también compone.
* **Girar y recortar** llevan las capas al marco nuevo.

Usan un .ini propio (``NATURALSHOT_CONFIG``) y un APPDATA temporal, e imágenes generadas.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import unittest
import warnings
from dataclasses import replace
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
if "NATURALSHOT_CONFIG" not in os.environ:
    import atexit
    _CARPETA_CONFIG = tempfile.mkdtemp(prefix="naturalshot_config_")
    atexit.register(shutil.rmtree, _CARPETA_CONFIG, True)
    os.environ["NATURALSHOT_CONFIG"] = os.path.join(_CARPETA_CONFIG, "preferencias.ini")

from celular_natural.motor import PRESETS, Zona, procesar_pila  # noqa: E402
from celular_natural.motor.documento import Documento, componer  # noqa: E402


def escena(w=640, h=480, semilla=0) -> np.ndarray:
    """Cielo, pasto con textura y un cuadrado rojo."""
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cielo = np.dstack([90 + 60 * yy / h, 150 + 50 * yy / h, 230 + 0 * yy])
    grano = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), 1.5)
    pasto = np.dstack([60 + 0 * xx, 120 + 0 * xx, 50 + 0 * xx]) + 30 * grano[..., None]
    img = np.where((yy > h * 0.5)[..., None], pasto, cielo)
    img[int(h * 0.6):int(h * 0.8), int(w * 0.3):int(w * 0.4)] = (210, 30, 30)
    return np.clip(img + rng.normal(0, 2, (h, w, 1)) + 0.5, 0, 255).astype(np.uint8)


def logo(w=160, h=100, color=(240, 60, 150)) -> np.ndarray:
    """Un rectángulo de color con un borde transparente (RGBA)."""
    a = np.zeros((h, w, 4), np.uint8)
    a[8:h - 8, 8:w - 8, :3] = color
    a[8:h - 8, 8:w - 8, 3] = 255
    return a


def leer_png(ruta) -> np.ndarray:
    from PIL import Image
    with Image.open(ruta) as im:
        return np.asarray(im.convert("RGB")).copy()


def soltar(widget, rutas, modificadores=None) -> None:
    """Arrastra y suelta archivos sobre ``widget`` (como desde el Explorador)."""
    from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent
    from PySide6.QtWidgets import QApplication
    modificadores = Qt.NoModifier if modificadores is None else modificadores
    datos = QMimeData()
    datos.setUrls([QUrl.fromLocalFile(str(r)) for r in rutas])
    centro = widget.rect().center()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        entrar = QDragEnterEvent(centro, Qt.CopyAction, datos, Qt.LeftButton, modificadores)
    QApplication.sendEvent(widget, entrar)
    QApplication.sendEvent(widget, QDropEvent(QPointF(centro), Qt.CopyAction, datos, Qt.LeftButton, modificadores))


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _Base(unittest.TestCase):
    """Una ventana real en el modo Editor, con una foto abierta."""

    activar_sesion = False

    @classmethod
    def setUpClass(cls):
        from PIL import Image
        cls.app = _app()
        cls.carpeta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        base = Path(cls.carpeta.name)
        cls._entorno = {k: os.environ.get(k) for k in ("APPDATA", "NATURALSHOT_CONFIG", "NATURALSHOT_EDICION")}
        os.environ["APPDATA"] = str(base / "appdata")
        os.environ["NATURALSHOT_EDICION"] = "lite"  # las capas se editan en el modo Photoshop de la Lite
        cls.config = base / "config.ini"
        os.environ["NATURALSHOT_CONFIG"] = str(cls.config)
        cls.base = base
        cls.ruta = base / "escena.png"
        Image.fromarray(escena()).save(cls.ruta)
        cls.logos = []
        for i, color in enumerate(((240, 60, 150), (40, 200, 90), (60, 90, 240))):
            r = base / f"logo{i + 1}.png"
            Image.fromarray(logo(color=color), "RGBA").save(r)
            cls.logos.append(r)

    @classmethod
    def tearDownClass(cls):
        for clave, valor in cls._entorno.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
        cls.carpeta.cleanup()

    def setUp(self):
        self.ventanas = []
        self.v = self.ventana()
        self.v.abrir_archivo(str(self.ruta))
        self.esperar()

    def tearDown(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        for v in self.ventanas:
            v.close()
            v.deleteLater()
        self.app.processEvents()
        # deleteLater() sin un bucle de eventos no borra nada: se vacían los borrados diferidos.
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    # ------------------------------------------------------------ ayudas
    def ventana(self, activar=None, modo="photoshop"):
        from celular_natural.ui.ventana import VentanaPrincipal
        v = VentanaPrincipal()
        v.resize(1366, 768)
        v.show()
        v.establecer_modo(modo, guardar=False)
        self.ventanas.append(v)
        if self.activar_sesion if activar is None else activar:
            v.activar_sesion()
            self.esperar(lambda: v.sesion_restaurada, v)
        return v

    def cerrar(self, v):
        v.close()
        self.ventanas.remove(v)
        v.deleteLater()
        self.app.processEvents()

    def quieto(self, v=None) -> bool:
        v = v or self.v
        return (v._imagen is not None and not v._fuentes_pendientes and v._deteccion is None
                and v._generacion_completa_mostrada == v._generacion and not v._exportando
                and not v._guardando_proyecto and v._pool_archivos.activeThreadCount() == 0)

    def esperar(self, condicion=None, v=None, segundos=60.0):
        condicion = condicion or (lambda: self.quieto(v))
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

    def agregar(self, *indices, v=None):
        """Agrega esos logos como capas y espera a que se vean."""
        v = v or self.v
        n = len(v._documento.capas)
        v.agregar_imagenes_como_capa([str(self.logos[i]) for i in indices])
        self.esperar(lambda: len(v._documento.capas) == n + len(indices) and self.quieto(v), v)
        return [c.id for c in v._documento.capas[1:-1]]

    def vista(self, v=None) -> np.ndarray:
        v = v or self.v
        self.esperar(lambda: self.quieto(v), v)
        return v._resultado_completo[1].copy()

    def esperado(self, v=None, doc=None, con_filtro=None) -> np.ndarray:
        """Lo que tiene que dar la foto con sus capas, calculado directo con el motor: con el filtro
        (Fácil, Editor y exportar) o sin él (el modo Photoshop, salvo "Ver con el filtro")."""
        v = v or self.v
        pa = v.panel_ajustes
        doc = doc or v._documento
        if con_filtro is None:
            con_filtro = v._con_filtro()

        def filtro(img):
            return procesar_pila(img, pa.pila(), escala_vista=1.0, zonas=pa.zonas(), recorte=v._recorte)

        h, w = v._fuente.shape[:2]
        return componer(Documento(w, h, doc.capas), v._almacen, v._fuente, 1.0, filtro if con_filtro else None)

    def filtrada(self, v=None) -> np.ndarray:
        """La foto con el filtro de siempre, sin capas."""
        v = v or self.v
        pa = v.panel_ajustes
        return procesar_pila(v._fuente, pa.pila(), escala_vista=1.0, zonas=pa.zonas(), recorte=v._recorte)

    def exportar(self, destino: Path, v=None) -> np.ndarray:
        from PySide6.QtWidgets import QFileDialog
        v = v or self.v
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "PNG (*.png)")):
            v.exportar()
        self.esperar(lambda: not v._exportando and destino.exists(), v)
        return leer_png(destino)

    def paso(self, v=None) -> str:
        v = v or self.v
        return v._historial[v._pos_historial][0]


# ====================================================================== regresión
class PruebasRegresion(_Base):
    def test_exportar_sin_capas_es_lo_de_antes_bit_a_bit(self):
        """Sin capas extra, la vista y la exportación son ``procesar_pila`` sobre la foto de siempre."""
        from celular_natural.ui.modo_facil import EDITOR
        v = self.v
        v.establecer_modo(EDITOR, guardar=False)
        v.panel_ajustes.combo_preset.setCurrentText("Noche urbana")
        v.panel_ajustes.agregar_capa("Día nublado", 40, zona=Zona("rect", 0.1, 0.1, 0.5, 0.5))
        self.esperar()
        antes = self.filtrada()
        self.assertTrue(np.array_equal(self.vista(), antes))
        exportada = self.exportar(self.base / "regresion.png")
        self.assertTrue(np.array_equal(exportada, antes), "exportar sin capas cambió algo")
        # Sin capas, el estado no lleva documento (igual que el de antes).
        self.assertNotIn("documento", v._estado_completo())

    def test_con_capas_exportar_es_la_vista(self):
        from celular_natural.ui.modo_facil import EDITOR
        v = self.v
        self.agregar(0)
        # Desde el modo Photoshop se exporta con el filtro (como desde cualquier modo).
        exportada = self.exportar(self.base / "con_capas.png")
        self.assertTrue(np.array_equal(exportada, self.esperado(con_filtro=True)))
        v.establecer_modo(EDITOR, guardar=False)
        vista = self.vista()
        self.assertTrue(np.array_equal(vista, exportada))
        # Y la capa se ve: no es lo mismo que sin ella.
        self.assertFalse(np.array_equal(vista, self.filtrada()))

    def test_vista_rapida_compone_a_escala(self):
        """Una foto grande: la vista rápida (reducida) también compone, con su caché."""
        from PIL import Image
        from celular_natural.ui.ventana import procesar_con_capas
        grande = self.base / "grande.png"
        Image.fromarray(escena(2000, 1400, semilla=4)).save(grande)
        v = self.v
        v.agregar_fotos([str(grande)])
        self.esperar(lambda: self.quieto() and v._imagen.ruta.name == "grande.png")
        self.agregar(1)
        pa = v.panel_ajustes
        rgb, escala = v._vista_previa, v._escala_vista_previa
        self.assertLess(escala, 1.0)
        salida = procesar_con_capas(rgb, v._documento, v._almacen, pa.pila(), pa.zonas(), v._recorte, None, escala,
                                    (v._fuente.shape[1], v._fuente.shape[0]))
        self.assertEqual(salida.shape, rgb.shape)
        self.assertGreater(v._cache_rapida.bytes_usados, 0)


# ====================================================================== panel
class PruebasPanel(_Base):
    def test_agregar_desde_el_dialogo(self):
        from PySide6.QtWidgets import QFileDialog
        v = self.v
        with mock.patch.object(QFileDialog, "getOpenFileNames", return_value=([str(self.logos[0])], "")):
            v.panel_capas.boton_agregar.click()
        self.esperar(lambda: len(v._documento.capas) == 3 and self.quieto())
        capa = v._documento.capas[1]
        self.assertEqual((capa.tipo, capa.nombre), ("imagen", "logo1"))
        # Entra centrada (y como es más chica que la foto, a escala 1).
        self.assertEqual((capa.transform.x, capa.transform.y, capa.transform.escala), (320.0, 240.0, 1.0))
        self.assertEqual(self.paso(), "Capa agregada: logo1")
        self.assertEqual(v.panel_capas.capa_elegida, capa.id)
        # El panel: de arriba hacia abajo, "Celular natural", la capa y la foto.
        self.assertEqual([f.nombre.text() for f in v.panel_capas.filas()], ["Filtro celular natural", "logo1", "Foto"])

    def test_imagen_demasiado_grande_avisa(self):
        from celular_natural.ui import modo_photoshop as modulo  # agregar capas vive en el modo Photoshop
        v = self.v
        with mock.patch.object(modulo, "MAX_PIXELES_IMAGEN", 1000):
            v.agregar_imagenes_como_capa([str(self.logos[0])])
            self.esperar(lambda: v._pool_archivos.activeThreadCount() == 0 and "como capa" in v.aviso.texto.text())
        self.assertEqual(len(v._documento.capas), 2)
        self.assertIn("demasiado grande", v.aviso.toolTip())

    def test_reordenar_opacidad_fusion_ocultar_renombrar_y_borrar(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        v = self.v
        p = v.panel_capas
        ids = self.agregar(0, 1)  # logo1 abajo, logo2 arriba
        nombres = lambda: [c.nombre for c in v._documento.capas]  # noqa: E731
        self.assertEqual(nombres(), ["Foto", "logo1", "logo2", "Celular natural"])
        # Subir y bajar con los botones (la de abajo de todo no baja más: botón deshabilitado).
        p.elegir(ids[0])
        self.assertFalse(p.boton_bajar.isEnabled())
        p.boton_subir.click()
        self.assertEqual(nombres(), ["Foto", "logo2", "logo1", "Celular natural"])
        self.assertEqual(self.paso(), "Capa «logo1» subida")
        self.assertFalse(p.boton_subir.isEnabled())  # ya está arriba de todo (debajo del filtro)
        # Arrastrando la fila: logo1 (fila 1, arriba) a la fila 2 → baja.
        p.lista.filaSoltada.emit(ids[0], 2)
        self.esperar(lambda: nombres() == ["Foto", "logo1", "logo2", "Celular natural"])
        self.assertEqual(self.paso(), "Capa «logo1» bajada")
        # Soltarla arriba de "Celular natural" no la pasa por encima del filtro (el motor la frena).
        p.lista.filaSoltada.emit(ids[0], 0)
        self.esperar(lambda: nombres() == ["Foto", "logo2", "logo1", "Celular natural"])
        # Duplicar (y deshacerlo).
        p.elegir(ids[0])
        p.boton_duplicar.click()
        self.esperar()
        self.assertEqual(nombres(), ["Foto", "logo2", "logo1", "logo1 copia", "Celular natural"])
        self.assertEqual(self.paso(), "Capa duplicada: logo1 copia")
        v.deshacer()
        self.esperar(lambda: nombres() == ["Foto", "logo2", "logo1", "Celular natural"])
        # Opacidad: un gesto del deslizador = un paso.
        p.elegir(ids[0])
        pasos = v._pos_historial
        p.slider_opacidad.setSliderDown(True)  # (avisa sliderPressed, como al agarrarlo con el mouse)
        for valor in (90, 70, 50):
            p.slider_opacidad.setValue(valor)
        self.esperar()
        self.assertEqual(v._pos_historial, pasos)  # mientras se arrastra, solo se ve
        self.assertAlmostEqual(v._documento_vista().capa(ids[0]).opacidad, 0.5)
        p.slider_opacidad.setSliderDown(False)  # (avisa sliderReleased: fin del gesto)
        self.esperar()
        self.assertEqual(v._pos_historial, pasos + 1)
        self.assertEqual(self.paso(), "Capa «logo1»: opacidad 100 % → 50 %")
        self.assertTrue(np.array_equal(self.vista(), self.esperado()))
        # Fusión.
        p.establecer_fusion(ids[0], "multiplicar")
        self.esperar()
        self.assertEqual(v._documento.capa(ids[0]).fusion, "multiplicar")
        self.assertEqual(self.paso(), "Capa «logo1»: fusión Multiplicar")
        self.esperar(lambda: "Multiplicar" in p.fila(ids[0]).detalle.text())
        # Ocultar con el ojo.
        con = self.vista()
        p.fila(ids[0]).boton_ojo.click()
        self.esperar()
        self.assertFalse(v._documento.capa(ids[0]).visible)
        self.assertEqual(self.paso(), "Capa «logo1» oculta")
        self.assertFalse(np.array_equal(self.vista(), con))
        self.assertTrue(np.array_equal(self.vista(), self.esperado()))
        # Renombrar con F2 (el doble clic abre el estilo de capa, desde U2).
        self.esperar(lambda: p.fila(ids[1]) is not None)
        p.elegir(ids[1])
        fila = p.fila(ids[1])
        p.renombrar_elegida()
        self.assertTrue(fila.editor.isVisible())
        fila.editor.selectAll()
        QTest.keyClicks(fila.editor, "Marca de agua")
        QTest.keyClick(fila.editor, Qt.Key_Return)
        self.esperar(lambda: v._documento.capa(ids[1]).nombre == "Marca de agua")
        self.assertEqual(self.paso(), "Capa renombrada: logo2 → Marca de agua")
        # Candado: bloqueada no se borra ni se transforma.
        self.esperar(lambda: p.fila(ids[1]) is not None)
        p.fila(ids[1]).boton_candado.click()
        self.esperar(lambda: v._documento.capa(ids[1]).bloqueada)
        p.elegir(ids[1])
        self.assertFalse(p.boton_borrar.isEnabled())
        self.assertFalse(p.boton_transformar.isEnabled())
        self.assertFalse(p.slider_opacidad.isEnabled())
        self.assertEqual(self.paso(), "Capa «Marca de agua» bloqueada")
        # Borrar (la otra).
        p.elegir(ids[0])
        p.boton_borrar.click()
        self.esperar()
        self.assertEqual(nombres(), ["Foto", "Marca de agua", "Celular natural"])
        self.assertEqual(self.paso(), "Capa borrada: logo1")
        # La foto y el filtro no se borran: el botón no aplica y el motor avisa si se intenta igual.
        p.elegir("foto")
        self.assertFalse(p.boton_borrar.isEnabled())
        p._aplicar(lambda d: d.quitar("foto"))
        self.assertIn("no se puede borrar", v.aviso.texto.text())
        self.assertEqual(nombres(), ["Foto", "Marca de agua", "Celular natural"])

    def test_el_filtro_queda_arriba_bloqueado(self):
        """En el modo Photoshop, "Celular natural" está arriba de todo, atenuado y sin controles."""
        from PySide6.QtCore import Qt
        v = self.v
        p = v.panel_capas
        fila = p.filas()[0]
        self.assertEqual(fila.id, "celular_natural")
        self.assertEqual(fila.nombre.text(), "Filtro celular natural")
        self.assertIn("Fácil o Editor", fila.detalle.text())
        self.assertFalse(fila.isEnabled())
        self.assertFalse(p.lista.item(0).flags() & Qt.ItemIsSelectable)
        p.elegir("celular_natural")
        self.assertNotEqual(p.capa_elegida, "celular_natural")
        self.assertTrue(p.caja_mascara.isHidden())  # la máscara se pinta con las herramientas de la izquierda

    def test_mascaras(self):
        v = self.v
        p = v.panel_capas
        ids = self.agregar(0)
        p.elegir(ids[0])
        p.boton_mascara.click()  # sin máscara: la agrega (blanca)
        self.esperar()
        capa = v._documento.capa(ids[0])
        self.assertIsNotNone(capa.mascara)
        m = v._almacen.obtener(capa.mascara)
        self.assertEqual(m.shape, (480, 640))
        self.assertTrue((m == 255).all())
        self.assertEqual(self.paso(), "Capa «logo1»: máscara agregada")
        con_logo = self.vista()
        # Pintar con el rectángulo de la barra de herramientas, "se oculta": la mitad izquierda desaparece.
        v.botones_mascara_ps["ocultar"].click()
        v.botones_herramienta_ps["rect"].click()
        self.assertEqual(v.vista.herramienta, "zona")
        self.assertTrue(v.botones_herramienta_ps["rect"].isChecked())
        self.assertIn("Máscara de «logo1»", v.etiqueta_estado.text())
        v._seleccion_terminada(__import__("PySide6.QtCore", fromlist=["QRectF"]).QRectF(0.0, 0.0, 0.5, 1.0))
        self.esperar()
        m = v._almacen.obtener(v._documento.capa(ids[0]).mascara)
        self.assertEqual(int(m[240, 100]), 0)
        self.assertEqual(int(m[240, 500]), 255)
        self.assertEqual(self.paso(), "Capa «logo1»: máscara editada")
        self.assertFalse(v.botones_herramienta_ps["rect"].isChecked())
        vista = self.vista()
        self.assertTrue(np.array_equal(vista, self.esperado()))
        self.assertFalse(np.array_equal(vista, con_logo))
        # El pincel: "se ve" vuelve a mostrar parte de lo oculto.
        v.botones_mascara_ps["mostrar"].click()
        v.botones_herramienta_ps["pincel"].click()
        self.assertTrue(v.vista.pintando)
        v._trazos_terminados([(((0.3, 0.5), (0.45, 0.5)), 0.05, 100, False)])
        self.esperar()
        m = v._almacen.obtener(v._documento.capa(ids[0]).mascara)
        self.assertEqual(int(m[240, 250]), 255)
        # Invertir, ocultar todo, mostrar todo y quitar.
        p.invertir_mascara()
        self.esperar()
        m2 = v._almacen.obtener(v._documento.capa(ids[0]).mascara)
        self.assertTrue(np.array_equal(m2, 255 - m))
        p.mascara_llena(0)
        self.esperar()
        self.assertTrue((v._almacen.obtener(v._documento.capa(ids[0]).mascara) == 0).all())
        self.assertTrue(np.array_equal(self.vista(), v._fuente), "ocultar todo: la capa no se ve (y sin filtro)")
        p.quitar_mascara()
        self.esperar()
        self.assertIsNone(v._documento.capa(ids[0]).mascara)
        self.assertEqual(self.paso(), "Capa «logo1»: máscara quitada")

    def test_ctrl_arrastrar_agrega_capa_y_sin_ctrl_suma_a_la_tira(self):
        from PySide6.QtCore import Qt
        from celular_natural.ui.modo_facil import EDITOR
        v = self.v
        v.establecer_modo(EDITOR, guardar=False)  # en Fácil y Editor, sin Ctrl va a la tira
        soltar(v.vista, [self.logos[2]], Qt.ControlModifier)
        self.esperar(lambda: len(v._documento.capas) == 3 and self.quieto())
        self.assertEqual(v._documento.capas[1].nombre, "logo3")
        self.assertEqual(len(v._fotos), 1)
        soltar(v.vista, [self.logos[1]])
        self.esperar(lambda: len(v._fotos) == 2 and self.quieto() and v._imagen.ruta.name == "logo2.png")
        # La otra foto no hereda las capas (son de cada foto).
        self.assertEqual(len(v._documento.capas), 2)
        v.cambiar_a_foto(0)
        self.esperar(lambda: self.quieto() and v._imagen.ruta.name == "escena.png")
        self.assertEqual([c.nombre for c in v._documento.capas], ["Foto", "logo3", "Celular natural"])


# ====================================================================== Mover / Transformar
class PruebasTransformar(_Base):
    def a_pantalla(self, x, y):
        from PySide6.QtCore import QPoint
        vista = self.v.vista
        return QPoint(round(vista._origen.x() + x * vista._zoom), round(vista._origen.y() + y * vista._zoom))

    def test_mover_escalar_rotar_con_el_mouse(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        v = self.v
        ids = self.agregar(0)
        pasos = len(v._historial)
        # La tecla V (o el botón "Mover") activa la herramienta sobre la capa elegida.
        v.activateWindow()
        v.vista.setFocus()
        v.alternar_transformar(True)
        self.assertEqual(v.vista.herramienta, "transformar")
        self.assertTrue(v.boton_transformar.isChecked())
        self.assertTrue(v.barra_transformar.isVisible())
        vista = v.vista
        t0 = v._documento.capa(ids[0]).transform  # 160 × 100 centrado en (320, 240)
        # Mover: arrastrar desde adentro de la capa.
        desde, hasta = self.a_pantalla(320, 240), self.a_pantalla(370, 260)
        QTest.mousePress(vista, Qt.LeftButton, Qt.NoModifier, desde)
        QTest.mouseMove(vista, self.a_pantalla(345, 250))
        QTest.mouseMove(vista, hasta)
        QTest.mouseRelease(vista, Qt.LeftButton, Qt.NoModifier, hasta)
        t = vista.transformador.transform
        self.assertAlmostEqual(t.x, 370, delta=2)
        self.assertAlmostEqual(t.y, 260, delta=2)
        self.assertEqual(len(v._historial), pasos)  # todavía no es un paso
        self.assertIsNotNone(v._doc_provisorio)
        # Escalar con la esquina de abajo a la derecha: la de arriba a la izquierda queda fija.
        no = (t.x - 80, t.y - 50)
        se = self.a_pantalla(t.x + 80, t.y + 50)
        destino = self.a_pantalla(t.x + 160, t.y + 100)
        QTest.mousePress(vista, Qt.LeftButton, Qt.NoModifier, se)
        QTest.mouseMove(vista, destino)
        QTest.mouseRelease(vista, Qt.LeftButton, Qt.NoModifier, destino)
        t = vista.transformador.transform
        self.assertAlmostEqual(t.escala, 1.5, delta=0.03)
        self.assertAlmostEqual(t.x - 80 * t.escala, no[0], delta=2)
        self.assertAlmostEqual(t.y - 50 * t.escala, no[1], delta=2)
        # Rotar con la manija redonda (arriba): llevarla a la derecha del centro = +90°.
        manija = vista.transformador.manijas(vista.zoom)["rotar"]
        QTest.mousePress(vista, Qt.LeftButton, Qt.NoModifier, self.a_pantalla(manija.x(), manija.y()))
        lejos = self.a_pantalla(t.x + 300, t.y)
        QTest.mouseMove(vista, lejos)
        QTest.mouseRelease(vista, Qt.LeftButton, Qt.NoModifier, lejos)
        self.assertAlmostEqual(vista.transformador.transform.rotacion, 90, delta=3)
        # Flechas: de a 1 px (de a 10 con Mayús).
        x = vista.transformador.transform.x
        QTest.keyClick(vista, Qt.Key_Right)
        QTest.keyClick(vista, Qt.Key_Right, Qt.ShiftModifier)
        self.assertAlmostEqual(vista.transformador.transform.x, x + 11)
        # Voltear.
        v.voltear_capa()
        self.assertTrue(vista.transformador.transform.voltear_h)
        final = vista.transformador.transform
        # Enter aplica: un solo paso del historial.
        QTest.keyClick(vista, Qt.Key_Return)
        self.esperar()
        self.assertIsNone(vista.transformador)
        self.assertEqual(len(v._historial), pasos + 1)
        self.assertEqual(self.paso(), "Capa «logo1» transformada")
        self.assertEqual(v._documento.capa(ids[0]).transform, final)
        self.assertTrue(np.array_equal(self.vista(), self.esperado()))
        # Esc cancela: nada cambia.
        v.alternar_transformar(True)
        QTest.keyClick(vista, Qt.Key_Left, Qt.ShiftModifier)
        self.assertIsNotNone(v._doc_provisorio)
        QTest.keyClick(vista, Qt.Key_Escape)
        self.esperar()
        self.assertIsNone(v._transformando)
        self.assertEqual(v._documento.capa(ids[0]).transform, final)
        self.assertEqual(len(v._historial), pasos + 1)
        # Deshacer vuelve a la transformación de antes.
        v.deshacer()
        self.esperar()
        self.assertEqual(v._documento.capa(ids[0]).transform, t0)

    def test_solo_capas_imagen_sin_candado(self):
        v = self.v
        v.alternar_transformar(True)  # sin capas que se transformen: avisa y no hace nada
        self.assertIsNone(v._transformando)
        self.assertNotEqual(v.vista.herramienta, "transformar")
        self.assertIn("transformar", v.aviso.texto.text())
        ids = self.agregar(0)
        v.panel_capas.alternar_bloqueo(ids[0])
        self.esperar()
        v.alternar_transformar(True)
        self.assertIsNone(v._transformando)
        v.panel_capas.alternar_bloqueo(ids[0])
        self.esperar()
        v.alternar_transformar(True)
        self.assertEqual(v._transformando[0], ids[0])
        v.alternar_transformar(False)  # el botón otra vez: aplica (sin cambios, ningún paso)
        self.assertIsNone(v._transformando)

    def test_la_tecla_v_es_un_atajo(self):
        from PySide6.QtGui import QKeySequence
        acciones = [a for a in self.v._pagina_fotos.actions() if a.shortcut() == QKeySequence("V")]
        self.assertEqual(len(acciones), 1)
        self.agregar(0)
        # V elige Mover (como en Photoshop); la transformación libre es Ctrl+T.
        self.v.photoshop.elegir_herramienta("mano")
        self.assertFalse(self.v.boton_transformar.isChecked())
        acciones[0].trigger()
        self.assertEqual(self.v.vista.herramienta, "ps")
        self.assertEqual(self.v.photoshop.herramienta, "mover")
        self.assertTrue(self.v.boton_transformar.isChecked())
        ctrl_t = [a for a in self.v._pagina_fotos.actions() if a.shortcut() == QKeySequence("Ctrl+T")]
        self.assertEqual(len(ctrl_t), 1)
        ctrl_t[0].trigger()
        self.assertEqual(self.v.vista.herramienta, "transformar")


# ====================================================================== historial, girar y recortar
class PruebasHistorial(_Base):
    def test_cada_cambio_es_un_paso_y_se_deshace(self):
        v = self.v
        p = v.panel_capas
        inicio = self.vista()
        ids = self.agregar(0)
        con_capa = self.vista()
        p.establecer_fusion(ids[0], "diferencia")
        self.esperar()
        con_fusion = self.vista()
        self.assertEqual([d for d, _e in v._historial[1:]], ["Capa agregada: logo1", "Capa «logo1»: fusión Diferencia"])
        v.deshacer()
        self.esperar()
        self.assertEqual(v._documento.capa(ids[0]).fusion, "normal")
        self.assertTrue(np.array_equal(self.vista(), con_capa))
        self.assertEqual(p.combo_fusion.currentData(), "normal")
        v.deshacer()
        self.esperar()
        self.assertEqual(len(v._documento.capas), 2)
        self.assertTrue(np.array_equal(self.vista(), inicio))
        self.assertEqual(len(p.filas()), 2)
        v.rehacer()
        v.rehacer()
        self.esperar()
        self.assertTrue(np.array_equal(self.vista(), con_fusion))
        # Ctrl+Z / Ctrl+Y son los atajos de siempre.
        v.ir_al_historial(1)
        self.esperar()
        self.assertTrue(np.array_equal(self.vista(), con_capa))

    def test_girar_y_recortar_llevan_las_capas(self):
        v = self.v
        ids = self.agregar(0)
        p = v.panel_capas
        p.elegir(ids[0])
        p.agregar_mascara()
        self.esperar()
        doc = v._documento
        doc = doc.con_capa(ids[0], transform=replace(doc.capa(ids[0]).transform, x=100.0, y=80.0))
        v._cambiar_documento(doc, refrescar_panel=True)
        self.esperar()
        # Girar 90° a la derecha: el punto (100, 80) de una foto de 640 × 480 va a (480 - 80, 100).
        v.girar(1)
        self.esperar()
        capa = v._documento.capa(ids[0])
        self.assertEqual((v._documento.ancho, v._documento.alto), (480, 640))
        self.assertAlmostEqual(capa.transform.x, 400.0, delta=1)
        self.assertAlmostEqual(capa.transform.y, 100.0, delta=1)
        self.assertAlmostEqual(capa.transform.rotacion, 90.0)
        self.assertEqual(v._almacen.obtener(capa.mascara).shape, (640, 480))
        self.assertTrue(np.array_equal(self.vista(), self.esperado()))
        self.assertEqual(self.paso(), "Girar 90° a la derecha")
        v.deshacer()
        self.esperar()
        self.assertEqual(v._documento.capa(ids[0]).transform.x, 100.0)
        # Recortar: la capa sigue sobre el mismo lugar de la foto.
        v.boton_recortar.setChecked(True)
        v.vista._sel = __import__("PySide6.QtCore", fromlist=["QRectF"]).QRectF(64, 48, 640 - 128, 480 - 96)
        v._salir_recorte("aplicar")
        self.esperar()
        capa = v._documento.capa(ids[0])
        self.assertEqual((v._documento.ancho, v._documento.alto), (512, 384))
        self.assertAlmostEqual(capa.transform.x, 100.0 - 64, delta=1)
        self.assertAlmostEqual(capa.transform.y, 80.0 - 48, delta=1)
        self.assertTrue(np.array_equal(self.vista(), self.esperado()))


# ====================================================================== proyecto .nslite
class PruebasProyecto(_Base):
    def guardar(self, ruta: Path, v=None):
        from PySide6.QtWidgets import QFileDialog
        v = v or self.v
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(ruta), "")):
            v.guardar_proyecto()  # la primera vez pregunta dónde
        self.esperar(lambda: not v._guardando_proyecto and ruta.exists(), v)

    def test_guardar_y_abrir_da_lo_mismo(self):
        from celular_natural.motor.proyecto_lite import abrir_proyecto
        from celular_natural.ui import documento_capas as dc
        v = self.v
        v.panel_ajustes.combo_preset.setCurrentText("Noche urbana")
        v.panel_ajustes.agregar_capa("Día nublado", 40, zona=Zona("elipse", 0.2, 0.2, 0.6, 0.7))
        self.esperar()
        ids = self.agregar(0, 1)
        v.panel_capas.establecer_fusion(ids[1], "pantalla")
        v.panel_capas.elegir(ids[0])
        v.panel_capas.agregar_mascara()
        self.esperar()
        v._pintar_mascara(ids[0], Zona("elipse", 0.3, 0.3, 0.6, 0.6, pluma=0), "ocultar")
        self.esperar()  # se pinta en segundo plano
        v.girar(1)
        self.esperar()
        estado, vista = v._estado_completo(), self.vista()
        ruta = self.base / "proyecto.nslite"
        self.guardar(ruta)
        self.assertEqual(v._fotos[0].proyecto, str(ruta))
        # Lo que va en extra: la foto original y el estado de la edición en JSON (ida y vuelta igual).
        doc, almacen, extra = abrir_proyecto(ruta)
        self.assertEqual(extra["foto"]["ruta"], str(self.ruta))
        sin_doc = {k: e for k, e in estado.items() if k != "documento"}
        self.assertEqual(dc.estado_desde_json(extra["estado"]), sin_doc)
        self.assertEqual(doc, estado["documento"])
        self.assertTrue(doc.ids_usados() <= almacen.ids())
        # Ctrl+S otra vez: no pregunta (usa el mismo archivo).
        from PySide6.QtWidgets import QFileDialog
        with mock.patch.object(QFileDialog, "getSaveFileName", side_effect=AssertionError("no tenía que preguntar")):
            v.guardar_proyecto()
        self.esperar(lambda: not v._guardando_proyecto)
        # Abrirlo en otra ventana (como "Abrir con…"): misma edición, mismas capas y misma vista.
        otra = self.ventana()
        otra.abrir_rutas([str(ruta)])
        self.esperar(lambda: self.quieto(otra) and otra._documento is not None and len(otra._documento.capas) == 4,
                     otra)
        self.assertEqual(otra._estado_completo(), estado)
        self.assertTrue(np.array_equal(self.vista(otra), vista))
        self.assertTrue(otra._historial[-1][0].startswith("Proyecto abierto: proyecto.nslite"))
        self.assertEqual(otra._fotos[0].proyecto, str(ruta))

    def test_abrir_desde_el_dialogo_y_arrastrando(self):
        from PySide6.QtWidgets import QFileDialog
        v = self.v
        self.agregar(2)
        ruta = self.base / "arrastre.nslite"
        self.guardar(ruta)
        otra = self.ventana()
        with mock.patch.object(QFileDialog, "getOpenFileNames", return_value=([str(ruta)], "")) as dialogo:
            otra.elegir_archivo()
        self.assertIn("*.nslite", dialogo.call_args[0][3])
        self.esperar(lambda: self.quieto(otra) and len(otra._documento.capas) == 3, otra)
        tercera = self.ventana()
        soltar(tercera.vista, [ruta])
        self.esperar(lambda: self.quieto(tercera) and len(tercera._documento.capas) == 3, tercera)

    def test_sin_la_foto_original_se_abre_igual_con_un_aviso(self):
        from PIL import Image
        foto = self.base / "se_va.png"
        Image.fromarray(escena(320, 240, semilla=7)).save(foto)
        v = self.v
        v.agregar_fotos([str(foto)])
        self.esperar(lambda: self.quieto() and v._imagen.ruta.name == "se_va.png")
        ids = self.agregar(0)
        ruta = self.base / "sin_foto.nslite"
        self.guardar(ruta)
        foto.unlink()
        otra = self.ventana()
        otra.abrir_proyecto(str(ruta))
        self.esperar(lambda: self.quieto(otra) and otra._documento is not None and len(otra._documento.capas) == 3,
                     otra)
        self.assertIn("ya no está", otra.aviso.texto.text())
        self.assertEqual((otra._imagen.ancho, otra._imagen.alto), (320, 240))
        self.assertEqual(otra._documento.capas[1].id, ids[0])

    def test_proyecto_roto_avisa_y_no_cambia_nada(self):
        roto = self.base / "roto.nslite"
        roto.write_bytes(b"esto no es un zip")
        v = self.v
        antes = v._estado_completo()
        v.abrir_proyecto(str(roto))
        self.esperar(lambda: "No se pudo abrir el proyecto" in v.aviso.texto.text())
        self.assertEqual(v._estado_completo(), antes)
        self.assertEqual(len(v._fotos), 1)


# ====================================================================== sesión
class PruebasSesion(_Base):
    activar_sesion = True

    def test_cerrar_y_volver_a_abrir_conserva_las_capas(self):
        from celular_natural import sesion
        v = self.v
        ids = self.agregar(0, 1)
        v.panel_capas.elegir(ids[1])
        v.panel_capas.agregar_mascara()
        self.esperar()
        v._pintar_mascara(ids[1], Zona("rect", 0.0, 0.0, 0.5, 1.0, pluma=0), "ocultar")
        self.esperar()  # se pinta en segundo plano
        v.panel_capas.establecer_opacidad(ids[0], 60)
        self.esperar()
        estado, historial, vista = v._estado_completo(), list(v._historial), self.vista()
        self.cerrar(v)
        pngs = {r.stem for r in sesion.carpeta_imagenes().glob("*.png")}
        self.assertTrue(estado["documento"].ids_usados() <= pngs)
        otra = self.ventana()
        self.esperar(lambda: self.quieto(otra), otra)
        self.assertEqual(otra._estado_completo(), estado)
        self.assertEqual(otra._historial, historial)
        self.assertTrue(np.array_equal(self.vista(otra), vista))
        self.assertEqual([f.nombre.text() for f in otra.panel_capas.filas()],
                         ["Filtro celular natural", "logo2", "logo1", "Foto"])
        # Deshacer sigue andando (las imágenes de los pasos de antes también están).
        otra.deshacer()
        self.esperar(lambda: self.quieto(otra), otra)
        self.assertAlmostEqual(otra._documento.capa(ids[0]).opacidad, 1.0)
        # "Quitar todas las fotos" borra también las imágenes de la sesión.
        otra.quitar_todas_las_fotos(confirmar=False)
        self.assertEqual(list(sesion.carpeta_imagenes().glob("*.png")), [])


# ====================================================================== Fácil
class PruebasFacil(_Base):
    def test_facil_muestra_las_capas_y_exporta_compuesto(self):
        from celular_natural.ui.modo_facil import FACIL, PHOTOSHOP
        v = self.v
        self.agregar(0)
        en_editor = self.exportar(self.base / "editor.png")
        v.establecer_modo(FACIL, guardar=False)
        self.esperar()
        pf = v.panel_facil
        pf.sincronizar()
        self.assertTrue(v.panel_derecho.isHidden())  # Fácil no muestra el panel de capas
        self.assertTrue(pf.nota_editor.isVisible())
        self.assertIn("capas", pf.texto_nota_editor.text())
        self.assertTrue(np.array_equal(self.vista(), self.esperado()))
        en_facil = self.exportar(self.base / "facil.png")
        self.assertTrue(np.array_equal(en_facil, en_editor))
        # El estilo elegido en Fácil es la capa de ajuste: cambia el filtro, las capas quedan.
        pf.elegir_estilo("Noche urbana")
        self.esperar()
        self.assertEqual(v.panel_ajustes.estado()["preset"], "Noche urbana")
        self.assertEqual(len(v._documento.capas), 3)
        self.assertTrue(np.array_equal(self.vista(), self.esperado()))
        # Una herramienta del modo Photoshop a medias (transformar) se cancela al pasar a Fácil.
        v.establecer_modo(PHOTOSHOP, guardar=False)
        v.alternar_transformar(True)
        self.assertIsNotNone(v._transformando)
        v.establecer_modo(FACIL, guardar=False)
        self.assertIsNone(v._transformando)
        v.alternar_transformar(True)  # V en Fácil no hace nada
        self.assertIsNone(v._transformando)


# ====================================================================== modo Photoshop
class PruebasModoPhotoshop(_Base):
    def test_selector_atajo_y_que_se_recuerde(self):
        from PySide6.QtGui import QKeySequence
        from celular_natural.ui.modo_facil import EDITOR, FACIL, PHOTOSHOP, modo_guardado
        v = self.v
        self.assertEqual([b.property("modo") for b in v.grupo_interfaz.buttons()], [FACIL, EDITOR, PHOTOSHOP])
        boton = next(b for b in v.grupo_interfaz.buttons() if b.property("modo") == PHOTOSHOP)
        v.establecer_modo(FACIL)
        boton.click()
        self.assertEqual(v.modo, PHOTOSHOP)
        self.assertEqual(modo_guardado(), PHOTOSHOP)  # se recuerda, como Fácil y Editor
        # La distribución: herramientas e Historial a la izquierda, Propiedades y Capas a la derecha, sin Ajustes.
        self.assertTrue(v.panel_herramientas_ps.isVisible())
        self.assertTrue(v.panel_derecho_ps.isVisible())
        self.assertFalse(v.panel_derecho.isVisible())
        self.assertTrue(v.panel_herramientas_ps.isAncestorOf(v._tarjeta_historial))
        self.assertTrue(v.panel_derecho_ps.isAncestorOf(v.panel_capas))
        self.assertFalse(v._lateral_editor.isVisible())
        self.assertTrue(v._segmento_capa.isVisible())
        self.assertFalse(v._segmento_recorte.isVisible())
        self.assertEqual(v.vista.modo, "solo")  # sin Antes ni Después
        # Ctrl+Shift+P: vuelve al último de Fácil y Editor, y otra vez a Photoshop.
        acciones = [a for a in v.actions() if a.shortcut() == QKeySequence("Ctrl+Shift+P")]
        self.assertEqual(len(acciones), 1)
        acciones[0].trigger()
        self.assertEqual(v.modo, FACIL)
        self.assertEqual(v.vista.modo, "dividir")
        acciones[0].trigger()
        self.assertEqual(v.modo, PHOTOSHOP)
        v.establecer_modo(EDITOR)
        self.assertTrue(v.panel_derecho.isVisible())
        self.assertTrue(v._caja_historial.isAncestorOf(v._tarjeta_historial))
        self.assertFalse(v.panel_derecho_ps.isVisible())
        self.assertEqual(modo_guardado(), EDITOR)

    def test_la_pro_no_tiene_modo_photoshop(self):
        from celular_natural.ui.modo_facil import PHOTOSHOP
        from celular_natural.ui.ventana import VentanaPrincipal
        with mock.patch.dict(os.environ, {"NATURALSHOT_EDICION": "pro"}):
            pro = VentanaPrincipal()
            self.ventanas.append(pro)
            self.assertNotIn(PHOTOSHOP, [b.property("modo") for b in pro.grupo_interfaz.buttons()])
            pro.establecer_modo(PHOTOSHOP)
            self.assertNotEqual(pro.modo, PHOTOSHOP)

    def test_photoshop_sin_filtro_y_facil_editor_con_el_filtro_arriba(self):
        from celular_natural.ui.modo_facil import EDITOR, FACIL, PHOTOSHOP
        v = self.v
        v.panel_ajustes.combo_preset.setCurrentText("Noche urbana")
        self.esperar()
        # Sin capas extra: Photoshop muestra la foto tal cual.
        self.assertTrue(np.array_equal(self.vista(), v._fuente))
        self.agregar(0)
        compuesta = self.esperado(con_filtro=False)
        self.assertTrue(np.array_equal(self.vista(), compuesta), "Photoshop: la composición, sin el filtro")
        # "Ver con el filtro" lo previsualiza (sin cambiar nada).
        pasos = len(v._historial)
        v.boton_ver_filtro.setChecked(True)
        self.esperar()
        con_filtro = self.esperado(con_filtro=True)
        self.assertTrue(np.array_equal(self.vista(), con_filtro))
        self.assertEqual(len(v._historial), pasos)
        v.boton_ver_filtro.setChecked(False)
        self.esperar()
        self.assertTrue(np.array_equal(self.vista(), compuesta))
        # En Fácil y Editor el filtro va arriba de la composición, y su "Antes" es la composición.
        for modo in (EDITOR, FACIL):
            v.establecer_modo(modo, guardar=False)
            self.esperar()
            self.assertTrue(np.array_equal(self.vista(), con_filtro), modo)
            self.assertIsNot(v.vista.antes, v._antes_actual)
            self.assertEqual((v.vista.antes.width(), v.vista.antes.height()), (640, 480))
        v.establecer_modo(PHOTOSHOP, guardar=False)
        self.esperar()
        self.assertTrue(np.array_equal(self.vista(), compuesta))
        self.assertFalse(v.boton_ver_filtro.isChecked())

    def test_soltar_una_imagen_en_photoshop_la_agrega_como_capa(self):
        v = self.v
        soltar(v.vista, [self.logos[1]])  # sin Ctrl
        self.esperar(lambda: len(v._documento.capas) == 3 and self.quieto())
        self.assertEqual(v._documento.capas[1].nombre, "logo2")
        self.assertEqual(len(v._fotos), 1)
        # También soltándola en otra parte de la ventana.
        soltar(v, [self.logos[2]])
        self.esperar(lambda: len(v._documento.capas) == 4 and self.quieto())
        self.assertEqual(len(v._fotos), 1)

    def test_herramientas_solo_las_que_existen(self):
        v = self.v
        # Etapa 2 (U3): Mover, Recortar, Texto, Formas, Pincel, Borrador, Bote (y Degradado), Mano, Zoom y
        # Cuentagotas, y las de la máscara (sin "próximamente").
        self.assertEqual(list(v.botones_herramienta_ps),
                         ["mover", "recortar", "texto", "formas", "pintar", "borrador", "bote", "mano", "zoom",
                          "cuentagotas", "rect", "elipse", "lazo", "pincel"])
        self.assertIs(v.boton_transformar, v.botones_herramienta_ps["mover"])
        ids = self.agregar(0)
        v.panel_capas.elegir(ids[0])
        self.assertTrue(v.botones_herramienta_ps["pincel"].isEnabled())
        v.botones_herramienta_ps["mano"].click()
        self.assertEqual(v.photoshop.herramienta, "mano")
        self.assertFalse(v.botones_herramienta_ps["mover"].isChecked())
        v.botones_herramienta_ps["mover"].click()
        self.assertEqual(v.photoshop.herramienta, "mover")
        self.assertEqual(v.vista.herramienta, "ps")
        # El pincel de la izquierda y el de la vista son el mismo.
        v.sliders_pincel_ps["tam"].setValue(20)
        self.assertEqual(v.vista.pincel[0], 20)


# ====================================================================== atajos por edición
class PruebasAtajos(_Base):
    def _accion(self, v, secuencia):
        from PySide6.QtGui import QKeySequence
        return next(a for a in v._pagina_fotos.actions() if a.shortcut() == QKeySequence(secuencia))

    def test_lite_ctrl_s_guarda_el_proyecto_y_ctrl_shift_e_exporta(self):
        from PySide6.QtGui import QKeySequence
        from PySide6.QtWidgets import QFileDialog
        v = self.v
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=("", "")) as dialogo:
            self._accion(v, QKeySequence.Save).trigger()
        self.assertIn("proyecto", dialogo.call_args[0][1].lower())
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=("", "")) as dialogo:
            self._accion(v, "Ctrl+Shift+E").trigger()
        self.assertEqual(dialogo.call_args[0][1], "Exportar como archivo nuevo")

    def test_pro_ctrl_s_exporta_como_siempre(self):
        from PySide6.QtGui import QKeySequence
        from PySide6.QtWidgets import QFileDialog
        with mock.patch.dict(os.environ, {"NATURALSHOT_EDICION": "pro"}):
            pro = self.ventana(modo="editor")
            pro.abrir_archivo(str(self.ruta))
            self.esperar(v=pro)
            with mock.patch.object(QFileDialog, "getSaveFileName", return_value=("", "")) as dialogo:
                self._accion(pro, QKeySequence.Save).trigger()
            self.assertEqual(dialogo.call_args[0][1], "Exportar como archivo nuevo")
            secuencias = [a.shortcut() for a in pro._pagina_fotos.actions()]
            self.assertNotIn(QKeySequence("Ctrl+Shift+E"), secuencias)
            self.assertNotIn(QKeySequence("V"), secuencias)


# ====================================================================== arreglos de la revisión
class PruebasRevision(_Base):
    def test_pro_ctrl_arrastrar_va_a_la_tira(self):
        """La PRO no tiene capas: con o sin Ctrl, una imagen soltada se suma a la tira."""
        from PySide6.QtCore import Qt
        with mock.patch.dict(os.environ, {"NATURALSHOT_EDICION": "pro"}):
            pro = self.ventana(modo="facil")
            pro.abrir_archivo(str(self.ruta))
            self.esperar(v=pro)
            soltar(pro.vista, [self.logos[0]], Qt.ControlModifier)
            self.esperar(lambda: len(pro._fotos) == 2 and self.quieto(pro) and pro._imagen.ruta.name == "logo1.png",
                         pro)
            pro.agregar_imagenes_como_capa([str(self.logos[1])])  # por cualquier camino
            self.esperar(lambda: len(pro._fotos) == 3 and self.quieto(pro), pro)
            for f in pro._fotos:
                self.assertNotIn("documento", f.estado or {})
            self.assertFalse(pro.tiene_capas_extra())
            pro.panel_facil.sincronizar()
            self.assertNotIn("Photoshop", pro.panel_facil.texto_nota_editor.text())

    def test_ctrl_z_durante_transformar_solo_cancela(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        v = self.v
        ids = self.agregar(0)
        pasos, pos = len(v._historial), v._pos_historial
        t0 = v._documento.capa(ids[0]).transform
        v.alternar_transformar(True)
        for _ in range(5):
            QTest.keyClick(v.vista, Qt.Key_Right, Qt.ShiftModifier)  # 50 px
        self.assertIsNotNone(v._doc_provisorio)
        v.deshacer()
        self.esperar()
        self.assertIsNone(v._transformando)
        self.assertEqual(len(v._documento.capas), 3, "la capa sigue")
        self.assertEqual(v._documento.capa(ids[0]).transform, t0)
        self.assertEqual((len(v._historial), v._pos_historial), (pasos, pos))
        # Ctrl+Y también: solo cancela.
        v.alternar_transformar(True)
        QTest.keyClick(v.vista, Qt.Key_Left)
        v.rehacer()
        self.esperar()
        self.assertIsNone(v._transformando)
        self.assertEqual(v._documento.capa(ids[0]).transform, t0)

    def test_dos_agregar_seguidos_entran_los_dos(self):
        v = self.v
        v.agregar_imagenes_como_capa([str(self.logos[0])])
        v.agregar_imagenes_como_capa([str(self.logos[1])])
        self.esperar(lambda: len(v._documento.capas) == 4 and self.quieto())
        self.assertEqual([c.nombre for c in v._documento.capas[1:-1]], ["logo1", "logo2"])

    def test_mascaras_de_pasos_viejos_comprimidas(self):
        from PIL import Image
        v = self.v
        foto = self.base / "grande_mascaras.png"
        Image.fromarray(escena(1600, 1200, semilla=9)).save(foto)
        v.agregar_fotos([str(foto)])
        self.esperar(lambda: self.quieto() and v._imagen.ruta.name == "grande_mascaras.png")
        ids = self.agregar(0)
        vistas = []
        for k in range(6):
            x = 0.1 * k
            v._pintar_mascara(ids[0], Zona("rect", x, 0.0, x + 0.08, 1.0, pluma=0), "ocultar")
            self.esperar()
            vistas.append(self.vista())
        # En el almacén, solo la máscara que se ve (las de los pasos de antes, comprimidas).
        mascaras = [i for i in v._almacen.ids() if v._almacen.obtener(i).ndim == 2]
        self.assertEqual(mascaras, [v._documento.capa(ids[0]).mascara])
        self.assertGreaterEqual(len(v._comprimidas), 5)
        comprimido = sum(len(d) for _f, d in v._comprimidas.values())
        self.assertLess(comprimido, 5 * 1600 * 1200 // 20)
        # Deshacer vuelve a traerlas: la vista es la de cada paso.
        for k in range(4, -1, -1):
            v.deshacer()
            self.esperar()
            self.assertTrue(np.array_equal(self.vista(), vistas[k]), k)

    def test_textos_de_efectos_por_edicion(self):
        from celular_natural.ui.historial import describir_cambio
        v = self.v  # Lite
        v.panel_ajustes.agregar_capa("Noche urbana", 40)
        fila = v.panel_ajustes.capas()[0]
        self.assertEqual(fila.etiqueta.text(), "Efecto 1")
        self.assertEqual(v.panel_ajustes.boton_agregar_capa.text().strip(), "Agregar efecto")
        base = {"preset": "x", "ajustes": None, "capas": []}
        self.assertEqual(describir_cambio(base, dict(base, capas=[("Noche urbana", 40, None)])),
                         "Efecto agregado: Noche urbana")
        with mock.patch.dict(os.environ, {"NATURALSHOT_EDICION": "pro"}):
            pro = self.ventana(modo="editor")
            pro.panel_ajustes.agregar_capa("Noche urbana", 40)
            self.assertEqual(pro.panel_ajustes.capas()[0].etiqueta.text(), "Capa 1")
            self.assertEqual(pro.panel_ajustes.boton_agregar_capa.text().strip(), "Agregar capa")
            self.assertEqual(describir_cambio(base, dict(base, capas=[("Noche urbana", 40, None)])),
                             "Capa agregada: Noche urbana")
            titulos = [t.text() for t in pro.findChildren(type(fila.etiqueta), "tituloCaja")]
            self.assertIn("Capas", titulos)
            self.assertNotIn("Efectos", titulos)

    def test_el_nombre_es_el_mismo_en_la_lista_y_el_historial(self):
        from PIL import Image
        v = self.v
        ruta = self.base / "sticker_verano.png"
        Image.fromarray(logo(color=(250, 200, 30)), "RGBA").save(ruta)
        v.agregar_imagenes_como_capa([str(ruta)])
        self.esperar(lambda: len(v._documento.capas) == 3 and self.quieto())
        capa = v._documento.capas[1]
        self.esperar(lambda: v.panel_capas.fila(capa.id) is not None)
        self.assertEqual(v.panel_capas.fila(capa.id).nombre.text(), "sticker_verano")
        self.assertEqual(self.paso(), "Capa agregada: sticker_verano")

    def test_proyecto_sin_foto_y_enorme_avisa(self):
        from celular_natural.motor.documento import AlmacenImagenes
        from celular_natural.motor.proyecto_lite import guardar_proyecto
        ruta = self.base / "enorme.nslite"
        guardar_proyecto(ruta, Documento.nuevo(20000, 20000), AlmacenImagenes(),
                         {"foto": {"ruta": str(self.base / "no_existe.png")}})
        v = self.v
        v.abrir_proyecto(str(ruta))
        self.esperar(lambda: "No se pudo abrir el proyecto" in v.aviso.texto.text())
        self.assertIn("demasiado grande", v.aviso.toolTip())
        self.assertEqual(len(v._fotos), 1)


class PruebasSesionPNG(unittest.TestCase):
    """Un PNG de la sesión vacío (de un corte) o dañado se vuelve a escribir."""

    def test_png_vacio_o_danado_se_reescribe(self):
        from celular_natural import sesion
        from celular_natural.motor.documento import AlmacenImagenes
        carpeta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(carpeta.cleanup)
        with mock.patch.dict(os.environ, {"APPDATA": carpeta.name, "NATURALSHOT_EDICION": "lite"}):
            img = logo()
            id_img = AlmacenImagenes.id_de(img)
            doc = Documento.nuevo(640, 480).agregar_imagen(id_img, "logo")
            estado = {"preset": "x", "ajustes": None, "capas": [], "documento": doc}
            guardada = sesion.SesionGuardada([sesion.FotoGuardada("foto.png", estado)], 0, imagenes={id_img: img})
            sesion._escribir_imagenes(guardada.imagenes)
            png = sesion.carpeta_imagenes() / f"{id_img}.png"
            png.write_bytes(b"")  # un corte de luz a mitad de camino
            sesion._escribir_imagenes(guardada.imagenes)
            self.assertGreater(png.stat().st_size, 0)
            self.assertEqual(list(sesion.cargar_imagenes(guardada)), [id_img])
            png.write_bytes(b"\x89PNG basura")  # dañado
            self.assertEqual(sesion.cargar_imagenes(guardada), {})
            self.assertFalse(png.exists(), "el dañado se borra: el próximo guardado lo vuelve a escribir")
            sesion._escribir_imagenes(guardada.imagenes)
            self.assertEqual(list(sesion.cargar_imagenes(guardada)), [id_img])


if __name__ == "__main__":
    unittest.main()
