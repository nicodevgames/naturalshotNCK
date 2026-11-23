"""Pruebas del modo Photoshop de NaturalShot Lite, Etapa 2 (U1), con la ventana real sin pantalla.

* **Nuevo documento** (sin foto, ``Documento.nuevo_lienzo``): fondo de color, transparente o degradado;
  en la tira, la sesión, el proyecto y exportar; en Fácil y Editor su composición entra al filtro y
  las herramientas de la foto de base quedan deshabilitadas (girar gira el lienzo).
* **Menú**: una prueba por grupo (Archivo, Editar, Imagen, Capa y Ver); cada operación es un paso.
* **Colores** de frente y fondo (X, D), **Mano** y **Zoom** (y Espacio sostenido), **Cuentagotas**.
* **Mover**: escala libre (X e Y; Mayús mantiene la proporción) y volteo vertical, **imán** (al soltar
  cerca del centro queda centrado), **selección múltiple** y **alinear**.
* **Panel Capas** con grupos (sangría, plegar, arrastrar adentro y afuera, menú contextual, ícono por
  tipo y "fx") y **Propiedades** (X, Y, ancho, alto, rotación y un relleno).
* **Sesión** con un documento de la Etapa 2 (texto, forma, estilos, grupos): no va a ``.bak``.
* **Regresión del kit de flyers** (Nuevo, varias imágenes, texto, exportar).

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

from celular_natural.motor.documento import Capa, Documento, Transformacion, caja_capa, componer  # noqa: E402
from celular_natural.motor.formas import ParamsForma, Relleno  # noqa: E402


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def foto_color(w, h, color, semilla=0) -> np.ndarray:
    rng = np.random.default_rng(semilla)
    base = np.zeros((h, w, 3), np.float32) + np.array(color, np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    base += 30 * np.sin(xx / 30.0)[..., None] + rng.normal(0, 3, (h, w, 1))
    return np.clip(base, 0, 255).astype(np.uint8)


def logo(w=160, h=100, color=(240, 60, 150)) -> np.ndarray:
    a = np.zeros((h, w, 4), np.uint8)
    a[:, :, :3] = color
    a[:, :, 3] = 255
    return a


def leer_png(ruta, modo="RGB") -> np.ndarray:
    from PIL import Image
    with Image.open(ruta) as im:
        return np.asarray(im.convert(modo)).copy()


class _Base(unittest.TestCase):
    """Una ventana real de la Lite, en el modo Photoshop."""

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
            Image.fromarray(foto_color(320, 240, color, i)).save(r)
            cls.fotos.append(r)
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

    def tearDown(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        for v in self.ventanas:
            v.close()
            v.deleteLater()
        self.app.processEvents()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    # ------------------------------------------------------------ ayudas
    def ventana(self, sesion: bool = False):
        from celular_natural.ui.ventana import VentanaPrincipal
        v = VentanaPrincipal()
        v.resize(1366, 768)
        v.show()
        v.establecer_modo("photoshop", guardar=False)
        self.ventanas.append(v)
        if sesion:
            v.activar_sesion()
            self.esperar(lambda: v.sesion_restaurada, v)
        return v

    def quieto(self, v=None) -> bool:
        v = v or self.v
        return (v._imagen is not None and not v._fuentes_pendientes and v._deteccion is None
                and v._generacion_completa_mostrada == v._generacion and not v._exportando
                and not v._guardando_proyecto and not v._quitando_fondo
                and v._pool_archivos.activeThreadCount() == 0)

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

    def documento(self, ancho=800, alto=600, color=(20, 40, 200), fondo=None, v=None):
        v = v or self.v
        n = len(v._fotos)
        v.nuevo_lienzo(ancho, alto, color, fondo)
        self.esperar(lambda: len(v._fotos) == n + 1 and self.quieto(v) and v._fuente is not None
                     and v._fuente.shape[:2] == (alto, ancho), v)

    def agregar(self, *indices, v=None):
        """Agrega esos logos como capas y devuelve los ids de las capas nuevas (de abajo hacia arriba)."""
        v = v or self.v
        antes = {c.id for c in v._documento.capas}
        v.agregar_imagenes_como_capa([str(self.logos[i]) for i in indices])
        self.esperar(lambda: len(v._documento.capas) == len(antes) + len(indices) and self.quieto(v), v)
        return [c.id for c in v._documento.capas if c.id not in antes]

    def vista(self, v=None) -> np.ndarray:
        v = v or self.v
        self.esperar(lambda: self.quieto(v), v)
        return v._resultado_completo[1].copy()

    def paso(self, v=None) -> str:
        v = v or self.v
        return v._historial[v._pos_historial][0]

    def caja(self, id_capa, v=None):
        v = v or self.v
        return caja_capa(v._documento, id_capa, v._almacen)

    def a_pantalla(self, x, y, v=None):
        from PySide6.QtCore import QPoint
        vista = (v or self.v).vista
        return QPoint(round(vista._origen.x() + x * vista._zoom), round(vista._origen.y() + y * vista._zoom))

    def arrastrar(self, desde, hasta, mods=None, pasos=4, v=None):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        vista = (v or self.v).vista
        mods = Qt.NoModifier if mods is None else mods
        a, b = self.a_pantalla(*desde, v=v), self.a_pantalla(*hasta, v=v)
        QTest.mousePress(vista, Qt.LeftButton, mods, a)
        for i in range(1, pasos + 1):
            QTest.mouseMove(vista, QPoint(round(a.x() + (b.x() - a.x()) * i / pasos),
                                          round(a.y() + (b.y() - a.y()) * i / pasos)))
        QTest.mouseRelease(vista, Qt.LeftButton, mods, b)


# ====================================================================== Nuevo documento
class PruebasNuevoDocumento(_Base):
    def test_nuevo_es_un_documento_sin_foto_en_la_tira(self):
        from celular_natural.ui import documento_capas as dc
        v = self.v
        self.documento(800, 600, (20, 40, 200))
        doc = v._documento
        self.assertFalse(doc.tiene_foto)
        self.assertEqual([c.tipo for c in doc.capas], ["relleno", "ajuste_natural"])
        self.assertEqual(doc.capas[0].params, Relleno("color", ((20, 40, 200, 255),)))
        self.assertTrue(dc.es_ruta_documento(v._fotos[-1].ruta))
        self.assertFalse(Path(v._fotos[-1].ruta).exists(), "no escribe ningún PNG (el truco de antes)")
        self.assertEqual(v.modo, "photoshop")
        self.assertEqual(self.paso(), "Nuevo documento")  # el primer paso de su historial (se ve "Inicio")
        # La vista (sin el filtro) es la composición del documento.
        self.assertTrue(np.array_equal(self.vista(), componer(doc, v._almacen, None)))
        self.assertIn("Sin título 1", v.windowTitle())

    def test_fondo_transparente_y_degradado(self):
        v = self.v
        self.documento(400, 300, fondo=Relleno("ninguno"))
        self.assertEqual(v._documento.capas[0].params.tipo, "ninguno")
        degradado = Relleno("lineal", ((255, 0, 0, 255), (0, 0, 255, 255)), (), 90.0)
        self.documento(400, 300, fondo=degradado)
        vista = self.vista()
        self.assertGreater(int(vista[2, 200, 0]), 200)  # arriba, rojo
        self.assertGreater(int(vista[297, 200, 2]), 200)  # abajo, azul
        self.assertEqual(len(v._fotos), 2)

    def test_dialogo_nuevo_da_el_relleno(self):
        from celular_natural.ui.kit_flyer import DialogoNuevo, TAMANOS
        d = DialogoNuevo()
        nombres = [n for n, _w, _h in TAMANOS]
        self.assertTrue(any("Carta" in n for n in nombres) and any("Banner" in n for n in nombres))
        d.transparente.setChecked(True)
        self.assertEqual(d.relleno(), Relleno("ninguno"))
        d.degradado.setChecked(True)
        self.assertEqual(d.relleno().tipo, "lineal")
        d.negro.setChecked(True)
        self.assertEqual(d.relleno(), Relleno("color", ((0, 0, 0, 255),)))
        d.deleteLater()

    def test_facil_y_editor_filtran_la_composicion_y_sin_herramientas_de_foto(self):
        from celular_natural.motor import procesar_pila
        v = self.v
        self.documento(400, 300, (200, 180, 160))
        self.agregar(0)
        v.panel_ajustes.combo_preset.setCurrentText("Noche urbana")
        for modo in ("editor", "facil"):
            v.establecer_modo(modo, guardar=False)
            vista = self.vista()
            pa = v.panel_ajustes

            def filtro(img):
                return procesar_pila(img, pa.pila(), escala_vista=1.0, zonas=pa.zonas(), recorte=v._recorte)

            esperado = componer(v._documento, v._almacen, None, 1.0, filtro)
            self.assertTrue(np.array_equal(vista, esperado), modo)
        v.establecer_modo("editor", guardar=False)
        self.assertFalse(v.boton_recortar.isEnabled())
        self.assertFalse(v.boton_enderezar.isEnabled())
        self.assertFalse(v.panel_montaje.isEnabled())
        self.assertFalse(v.panel_borrar.isEnabled())
        self.assertFalse(v.panel_fondo.isEnabled())
        self.assertTrue(v.nota_sin_foto.isVisible())
        self.assertIn("sin foto", v.boton_recortar.toolTip())
        # Girar (en Fácil y Editor) gira el lienzo: trabaja sobre la composición.
        v.girar(1)
        self.esperar(lambda: self.quieto() and v._documento.ancho == 300)
        self.assertEqual(v._fuente.shape[:2], (400, 300))
        self.assertEqual(self.paso(), "Lienzo rotado 90° a la derecha")

    def test_exportar_con_y_sin_filtro_y_con_transparencia(self):
        from PySide6.QtWidgets import QFileDialog
        v = self.v
        v.panel_ajustes.combo_preset.setCurrentText("Noche urbana")
        self.documento(400, 300, fondo=Relleno("ninguno"))
        ids = self.agregar(0)
        destino = self.base / "transparente.png"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "PNG (*.png)")) as d:
            v.exportar(con_filtro=False)
        self.esperar(lambda: not v._exportando and destino.exists())
        self.assertIn("Sin título", d.call_args[0][2])  # sugiere el nombre del documento
        rgba = leer_png(destino, "RGBA")
        self.assertEqual(rgba.shape, (300, 400, 4))
        self.assertEqual(int(rgba[5, 5, 3]), 0, "afuera del logo: transparente")
        x0, y0, x1, y1 = self.caja(ids[0])
        cy, cx = int((y0 + y1) / 2), int((x0 + x1) / 2)
        self.assertEqual(int(rgba[cy, cx, 3]), 255)
        self.assertEqual(tuple(int(c) for c in rgba[cy, cx, :3]), (240, 60, 150), "sin el filtro: el color tal cual")
        # Con el filtro: el logo cambia (el filtro va arriba) y lo transparente sigue transparente.
        destino2 = self.base / "con_filtro.png"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino2), "PNG (*.png)")):
            v.exportar()
        self.esperar(lambda: not v._exportando and destino2.exists())
        rgba2 = leer_png(destino2, "RGBA")
        self.assertEqual(int(rgba2[5, 5, 3]), 0)
        self.assertNotEqual(tuple(int(c) for c in rgba2[cy, cx, :3]), (240, 60, 150))
        # El botón Exportar y Ctrl+Shift+E exportan con el filtro (la señal no se cuela como "sin filtro").
        from PySide6.QtGui import QKeySequence
        for n, disparar in enumerate((v.boton_exportar.click,
                                      next(a for a in v._pagina_fotos.actions()
                                           if a.shortcut() == QKeySequence("Ctrl+Shift+E")).trigger)):
            destino3 = self.base / f"boton_{n}.png"
            with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino3), "PNG (*.png)")):
                disparar()
            self.esperar(lambda: not v._exportando and destino3.exists())
            self.assertTrue(np.array_equal(leer_png(destino3, "RGBA"), rgba2), n)

    def test_proyecto_de_un_documento_nuevo(self):
        from PySide6.QtWidgets import QFileDialog
        v = self.v
        self.documento(500, 400, (10, 120, 60))
        self.agregar(1)
        ruta = self.base / "documento.nslite"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(ruta), "")) as d:
            v.guardar_proyecto()
        self.esperar(lambda: not v._guardando_proyecto and ruta.exists())
        self.assertTrue(d.call_args[0][2].endswith("Sin título 1.nslite"))
        doc = v._documento
        otra = self.ventana()
        otra.abrir_proyecto(str(ruta))
        self.esperar(lambda: self.quieto(otra) and otra._documento is not None and not otra._documento.tiene_foto,
                     otra)
        self.assertEqual(otra._documento, doc)
        self.assertNotIn("falta", otra.aviso.texto.text().lower())
        self.assertEqual(otra._fuente.shape[:2], (400, 500))

    def test_sesion_recuerda_el_documento_nuevo(self):
        v = self.ventana(sesion=True)
        self.documento(600, 400, (90, 20, 20), v=v)
        ids = self.agregar(2, v=v)
        doc = v._documento
        v.close()
        self.ventanas.remove(v)
        v.deleteLater()
        self.app.processEvents()
        otra = self.ventana(sesion=True)
        self.esperar(lambda: self.quieto(otra) and otra._documento is not None, otra)
        self.assertEqual(otra._documento, doc)
        self.assertIn(ids[0], [c.id for c in otra._documento.capas])
        self.assertEqual(otra._fuente.shape[:2], (400, 600))


# ====================================================================== menú
class PruebasMenu(_Base):
    def test_el_menu_tiene_sus_grupos_y_solo_en_photoshop(self):
        v = self.v
        ps = v.photoshop
        self.assertTrue(ps.barra_menu.isVisible())
        titulos = [a.text() for a in ps.barra_menu.actions()]
        self.assertEqual(titulos, ["Archivo", "Editar", "Imagen", "Capa", "Ver"])
        for clave in ("nuevo", "abrir", "abrir_capas", "guardar", "guardar_como", "exportar", "exportar_sin",
                      "deshacer", "rehacer", "duplicar", "borrar", "transformar", "pegar", "tamano_imagen",
                      "tamano_lienzo", "rotar_90", "rotar_180", "voltear_h", "voltear_v", "recortar", "nueva_pixeles",
                      "nueva_relleno", "agrupar", "desagrupar", "rasterizar", "mascara_agregar", "alinear_izquierda",
                      "distribuir_h", "combinar", "acoplar", "acercar", "alejar", "ajustar", "100", "guias"):
            self.assertIn(clave, ps.acciones)
        v.establecer_modo("editor", guardar=False)
        self.assertFalse(ps.barra_menu.isVisible())
        self.assertFalse(ps.barra_opciones.isVisible())

    def test_archivo(self):
        from PySide6.QtWidgets import QFileDialog
        v = self.v
        ps = v.photoshop
        # Abrir como capas sin documento: la primera abre y las demás entran como capas.
        rutas = [str(self.fotos[0]), str(self.logos[0]), str(self.logos[1])]
        with mock.patch.object(QFileDialog, "getOpenFileNames", return_value=(rutas, "")):
            ps.acciones["abrir_capas"].trigger()
        self.esperar(lambda: self.quieto() and len(v._documento.capas) == 4)
        self.assertTrue(v._documento.tiene_foto)
        self.assertEqual([c.nombre for c in v._documento.capas[1:3]], ["logo1", "logo2"])
        # Con documento, entran como capas.
        with mock.patch.object(QFileDialog, "getOpenFileNames", return_value=([str(self.logos[2])], "")):
            ps.acciones["abrir_capas"].trigger()
        self.esperar(lambda: self.quieto() and len(v._documento.capas) == 5)
        # Exportar sin el filtro: la composición (lo que se ve en Photoshop).
        v.panel_ajustes.combo_preset.setCurrentText("Noche urbana")
        destino = self.base / "sin_filtro.png"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "PNG (*.png)")):
            ps.acciones["exportar_sin"].trigger()
        self.esperar(lambda: not v._exportando and destino.exists())
        esperado = componer(v._documento, v._almacen, v._fuente)
        self.assertTrue(np.array_equal(leer_png(destino), esperado))
        # Nuevo (con el diálogo).
        from celular_natural.ui import kit_flyer
        with mock.patch.object(kit_flyer.DialogoNuevo, "exec", return_value=1):
            ps.acciones["nuevo"].trigger()
        self.esperar(lambda: self.quieto() and not v._documento.tiene_foto)
        self.assertEqual((v._documento.ancho, v._documento.alto), (1080, 1080))

    def test_editar(self):
        from PySide6.QtGui import QImage, QColor
        from PySide6.QtWidgets import QApplication
        v = self.v
        ps = v.photoshop
        self.documento(400, 300)
        ids = self.agregar(0)
        # Pegar una imagen del portapapeles: una capa nueva.
        img = QImage(50, 40, QImage.Format_RGBA8888)
        img.fill(QColor(10, 200, 30, 255))
        QApplication.clipboard().setImage(img)
        ps.acciones["pegar"].trigger()
        self.esperar()
        pegada = v._documento.capas[-2]
        self.assertEqual(pegada.nombre, "Pegado")
        self.assertEqual(v._arreglo(pegada.imagen).shape, (40, 50, 4))
        # Duplicar, borrar, deshacer y rehacer: cada uno un paso.
        n = len(v._historial)
        ps.acciones["duplicar"].trigger()
        self.esperar()
        self.assertEqual(len(v._documento.capas), 5)
        ps.acciones["borrar"].trigger()
        self.esperar()
        self.assertEqual(len(v._documento.capas), 4)
        self.assertEqual(len(v._historial), n + 2)
        ps.acciones["deshacer"].trigger()
        self.esperar()
        self.assertEqual(len(v._documento.capas), 5)
        ps.acciones["rehacer"].trigger()
        self.esperar()
        self.assertEqual(len(v._documento.capas), 4)
        # Transformación libre: la de la capa elegida, con Enter.
        v.panel_capas.elegir(ids[0])
        ps.acciones["transformar"].trigger()
        self.assertEqual(v.vista.herramienta, "transformar")
        self.assertEqual(v._transformando[0], ids[0])
        v.cancelar_herramienta()
        self.assertIsNone(v._transformando)
        self.assertEqual(v.vista.herramienta, "ps")

    def test_imagen_en_un_documento(self):
        v = self.v
        ps = v.photoshop
        self.documento(400, 300)
        ids = self.agregar(0)
        c0 = self.caja(ids[0])
        # Tamaño del lienzo con el ancla arriba a la izquierda: lo de antes no se mueve.
        ps.aplicar_tamano_lienzo(500, 400, "arriba_izquierda")
        self.esperar(lambda: self.quieto() and v._documento.ancho == 500)
        self.assertEqual(self.caja(ids[0]), c0)
        self.assertEqual(v._fuente.shape[:2], (400, 500))
        self.assertTrue(self.paso().startswith("Tamaño del lienzo"))
        # Tamaño de imagen: todo a la mitad.
        ps.aplicar_tamano_imagen(250, 200)
        self.esperar(lambda: self.quieto() and v._documento.ancho == 250)
        self.assertAlmostEqual(v._documento.capa(ids[0]).transform.escala, 0.5)
        # Rotar 90° y voltear.
        ps.acciones["rotar_90"].trigger()
        self.esperar(lambda: self.quieto() and v._documento.ancho == 200)
        self.assertEqual(self.paso(), "Lienzo rotado 90° a la derecha")
        ps.acciones["voltear_h"].trigger()
        self.esperar()
        self.assertEqual(self.paso(), "Lienzo volteado horizontal")
        # Recortar (U3: la herramienta Recortar, con su recuadro; Enter aplica).
        from PySide6.QtCore import QRectF
        ps.acciones["recortar"].trigger()
        self.assertTrue(ps.recortando)
        self.assertEqual(ps.herramienta, "recortar")
        self.assertEqual(v.vista.herramienta, "ps")
        ps.caja_recorte_actual().rect = QRectF(0, 0, 100, 125)
        v._confirmar_herramienta()
        self.esperar(lambda: self.quieto() and v._documento.ancho == 100)
        self.assertEqual((v._documento.ancho, v._documento.alto), (100, 125))
        self.assertEqual(ps.caja_recorte_actual().pixeles(), (0, 0, 100, 125))
        self.assertEqual(v.vista.herramienta, "ps")
        # Deshacer vuelve al tamaño de antes (la "foto" del documento lo sigue).
        v.deshacer()
        self.esperar(lambda: self.quieto() and v._documento.ancho == 200)
        self.assertEqual(v._fuente.shape[:2], (250, 200))

    def test_imagen_en_una_foto(self):
        from celular_natural.ui import documento_capas as dc
        v = self.v
        ps = v.photoshop
        v.agregar_fotos([str(self.fotos[0])])
        self.esperar()
        self.agregar(0)
        # Rotar una foto usa el giro no destructivo de siempre (la foto se conserva).
        ps.rotar(90)
        self.esperar(lambda: self.quieto() and v._documento.ancho == 240)
        self.assertFalse(v._geometria.es_identidad())
        self.assertTrue(v._documento.tiene_foto)
        # El tamaño del lienzo de una foto arma un documento nuevo en la tira.
        ps.aplicar_tamano_lienzo(400, 400)
        self.esperar(lambda: self.quieto() and len(v._fotos) == 2 and not v._documento.tiene_foto)
        self.assertTrue(dc.es_ruta_documento(v._fotos[1].ruta))
        self.assertEqual((v._documento.ancho, v._documento.alto), (400, 400))
        self.assertEqual([c.tipo for c in v._documento.capas], ["relleno", "pixeles", "imagen", "ajuste_natural"])
        self.assertTrue(v._fotos[0].estado["documento"].tiene_foto, "la foto quedó como estaba")

    def test_capa(self):
        from celular_natural.motor.estilos import EstilosCapa, Sombra
        v = self.v
        ps = v.photoshop
        p = v.panel_capas
        self.documento(400, 300)
        ids = self.agregar(0, 1, 2)
        # Nueva capa de píxeles y de relleno (con el color de frente).
        ps.colores.establecer(frente=(255, 128, 0))
        ps.acciones["nueva_relleno"].trigger()
        self.esperar()
        relleno = v._documento.capa(p.capa_elegida)
        self.assertEqual(relleno.tipo, "relleno")
        self.assertEqual(relleno.params.colores[0], (255, 128, 0, 255))
        # Rasterizar el relleno: pasa a píxeles.
        ps.acciones["rasterizar"].trigger()
        self.esperar()
        self.assertEqual(v._documento.capa(relleno.id).tipo, "pixeles")
        ps.acciones["borrar"].trigger()
        self.esperar()
        ps.acciones["nueva_pixeles"].trigger()
        self.esperar()
        self.assertEqual(v._documento.capa(p.capa_elegida).tipo, "pixeles")
        ps.acciones["borrar"].trigger()
        self.esperar()
        # Agrupar (Ctrl+G) y desagrupar.
        p.elegir_varias(ids[:2])
        ps.acciones["agrupar"].trigger()
        self.esperar()
        grupo = v._documento.capa(p.capa_elegida)
        self.assertEqual(grupo.tipo, "grupo")
        self.assertEqual({c.id for c in v._documento.hijos(grupo.id)}, set(ids[:2]))
        ps.acciones["desagrupar"].trigger()
        self.esperar()
        self.assertFalse(any(c.tipo == "grupo" for c in v._documento.capas))
        # Máscara: agregar.
        p.elegir(ids[2])
        ps.acciones["mascara_agregar"].trigger()
        self.esperar()
        self.assertIsNotNone(v._documento.capa(ids[2]).mascara)
        # Alinear (submenú) y distribuir.
        ps.acciones["alinear_izquierda"].trigger()
        self.esperar()
        self.assertAlmostEqual(self.caja(ids[2])[0], 0.0, places=6)
        p.elegir_varias(ids)
        ps.acciones["distribuir_h"].trigger()
        self.esperar()
        # Combinar hacia abajo: dos capas en una de píxeles.
        p.elegir(ids[1])
        ps.acciones["combinar"].trigger()
        self.esperar()
        self.assertNotIn(ids[1], [c.id for c in v._documento.capas])
        self.assertEqual(v._documento.capa(ids[0]).tipo, "pixeles")
        # Acoplar imagen: todo en una capa sobre blanco; la vista no cambia.
        antes = self.vista()
        ps.acciones["acoplar"].trigger()
        self.esperar()
        self.assertEqual([c.tipo for c in v._documento.capas], ["relleno", "pixeles", "ajuste_natural"])
        self.assertTrue(np.array_equal(self.vista(), antes))
        self.assertEqual(self.paso(), "Imagen acoplada")

    def test_ver(self):
        v = self.v
        ps = v.photoshop
        self.documento(800, 600)
        z = v.vista.zoom
        ps.acciones["acercar"].trigger()
        self.assertGreater(v.vista.zoom, z)
        ps.acciones["alejar"].trigger()
        ps.acciones["100"].trigger()
        self.assertAlmostEqual(v.vista.zoom, 1.0)
        ps.acciones["ajustar"].trigger()
        self.assertTrue(v.vista._ajustar)
        ps.acciones["guias"].trigger()
        self.assertFalse(ps.guias_activas)
        ps.acciones["guias"].trigger()
        self.assertTrue(ps.guias_activas)


# ====================================================================== herramientas
class PruebasHerramientas(_Base):
    def test_colores_frente_y_fondo(self):
        from PySide6.QtGui import QKeySequence
        v = self.v
        ps = v.photoshop
        self.assertEqual((ps.frente, ps.fondo), ((0, 0, 0), (255, 255, 255)))
        ps.colores.establecer(frente=(200, 10, 10), fondo=(0, 0, 90))
        x = next(a for a in v._pagina_fotos.actions() if a.shortcut() == QKeySequence("X"))
        d = next(a for a in v._pagina_fotos.actions() if a.shortcut() == QKeySequence("D"))
        x.trigger()
        self.assertEqual((ps.frente, ps.fondo), ((0, 0, 90), (200, 10, 10)))
        d.trigger()
        self.assertEqual((ps.frente, ps.fondo), ((0, 0, 0), (255, 255, 255)))
        # Clic en el cuadrado de frente: el selector de color.
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtGui import QColor
        from PySide6.QtTest import QTest
        from celular_natural.ui import selector_color
        with mock.patch.object(selector_color, "elegir_color", return_value=(1, 2, 3, 255)):
            QTest.mouseClick(ps.colores, Qt.LeftButton, Qt.NoModifier, QPoint(10, 10))
        self.assertEqual(ps.frente, (1, 2, 3))

    def test_mano_zoom_y_espacio(self):
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        v = self.v
        ps = v.photoshop
        self.documento(800, 600)
        vista = v.vista
        # Zoom: clic acerca, Alt+clic aleja.
        ps.elegir_herramienta("zoom")
        self.assertTrue(v.botones_herramienta_ps["zoom"].isChecked())
        z = vista.zoom
        QTest.mouseClick(vista, Qt.LeftButton, Qt.NoModifier, self.a_pantalla(400, 300))
        self.assertAlmostEqual(vista.zoom, z * 1.5, places=4)
        QTest.mouseClick(vista, Qt.LeftButton, Qt.AltModifier, self.a_pantalla(400, 300))
        self.assertAlmostEqual(vista.zoom, z, places=4)
        # Mano: arrastrar desplaza (con zoom, para que haya lugar).
        vista.fijar_zoom(3.0)
        ps.elegir_herramienta("mano")
        self.assertEqual(ps.paginas_opciones.currentIndex(), ps._paginas["mano"])
        origen = vista._origen
        self.arrastrar((400, 300), (380, 290))
        self.assertNotEqual(vista._origen, origen)
        # Espacio sostenido: la mano temporal, con cualquier herramienta.
        ps.elegir_herramienta("mover")
        v.activateWindow()
        vista.setFocus()
        with mock.patch.object(type(v), "isActiveWindow", return_value=True):
            QApplication.sendEvent(vista, QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier))
            self.assertTrue(vista.mano_temporal)
            origen = vista._origen
            self.arrastrar((400, 300), (390, 300))
            self.assertNotEqual(vista._origen, origen)
            QApplication.sendEvent(vista, QKeyEvent(QEvent.KeyRelease, Qt.Key_Space, Qt.NoModifier))
        self.assertFalse(vista.mano_temporal)
        self.assertEqual(len(v._historial), 1, "desplazar la vista no es un paso")

    def test_cuentagotas(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        v = self.v
        ps = v.photoshop
        self.documento(400, 300, (200, 30, 90))
        self.vista()
        ps.elegir_herramienta("cuentagotas")
        QTest.mouseClick(v.vista, Qt.LeftButton, Qt.NoModifier, self.a_pantalla(20, 20))
        self.assertEqual(ps.frente, (200, 30, 90))
        self.assertEqual(len(v._historial), 1)

    def test_escala_libre_y_volteo_vertical(self):
        from celular_natural.ui.herramienta_transformar import HerramientaTransformar
        from PySide6.QtCore import QPointF
        h = HerramientaTransformar(Transformacion(100, 100), 100, 50)
        # Esquina abajo-derecha, libre: el ancho y el alto por separado (la de arriba-izquierda queda fija).
        h.empezar("se", QPointF(150, 125))
        t = h.arrastrar(QPointF(250, 135))
        self.assertAlmostEqual(t.escala, 2.0)
        self.assertAlmostEqual(t.escala_y, 1.2)
        self.assertAlmostEqual(t.x - 50 * t.escala, 50.0)
        self.assertAlmostEqual(t.y - 25 * t.escala_y, 75.0)
        # Con Mayús: mantiene la proporción.
        t = h.arrastrar(QPointF(250, 135), mayus=True)
        self.assertAlmostEqual(t.escala_vertical / t.escala, 1.0, places=6)
        h.soltar()
        # Un lado cambia un solo eje.
        h = HerramientaTransformar(Transformacion(100, 100), 100, 50)
        h.empezar("e", QPointF(150, 100))
        t = h.arrastrar(QPointF(200, 140))
        self.assertAlmostEqual(t.escala, 1.5)
        self.assertAlmostEqual(t.escala_vertical, 1.0)
        # Volteo vertical.
        self.assertTrue(h.voltear_v().voltear_v)
        self.assertIn("volteada V", h.texto())

    def test_mover_con_el_mouse_es_un_paso_y_escala_libre_con_las_manijas(self):
        v = self.v
        self.documento(800, 600)
        ids = self.agregar(0)  # 160 × 100 en el centro
        ps = v.photoshop
        ps.establecer_guias(False)
        pasos = len(v._historial)
        self.arrastrar((400, 300), (300, 200))
        self.esperar()
        t = v._documento.capa(ids[0]).transform
        self.assertAlmostEqual(t.x, 300, delta=2)
        self.assertAlmostEqual(t.y, 200, delta=2)
        self.assertEqual(len(v._historial), pasos + 1)
        self.assertEqual(self.paso(), "Capa «logo1» movida")
        # Las manijas (Mostrar controles): la esquina abajo-derecha, libre.
        self.arrastrar((t.x + 80, t.y + 50), (t.x + 160, t.y + 70))
        self.esperar()
        t2 = v._documento.capa(ids[0]).transform
        self.assertAlmostEqual(t2.escala, 1.5, delta=0.03)
        self.assertAlmostEqual(t2.escala_vertical, 1.2, delta=0.03)
        self.assertEqual(self.paso(), "Capa «logo1» transformada")
        # Sin "Mostrar controles", arrastrar la esquina mueve (no escala).
        ps.check_controles.setChecked(False)
        self.assertIsNone(ps.controlador.manijas())

    def test_iman_al_soltar_cerca_del_centro_queda_centrado(self):
        v = self.v
        self.documento(800, 600)
        ids = self.agregar(0)
        self.arrastrar((400, 300), (200, 150))
        self.esperar()
        # Se suelta a 3 px del centro del lienzo: se pega.
        x0, y0, x1, y1 = self.caja(ids[0])
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        guias = []
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        vista = v.vista
        a = self.a_pantalla(cx, cy)
        b = self.a_pantalla(400 + 3, 300 - 2)
        QTest.mousePress(vista, Qt.LeftButton, Qt.NoModifier, a)
        QTest.mouseMove(vista, QPoint((a.x() + b.x()) // 2, (a.y() + b.y()) // 2))
        QTest.mouseMove(vista, b)
        guias = list(v.photoshop.controlador.guias)
        QTest.mouseRelease(vista, Qt.LeftButton, Qt.NoModifier, b)
        self.esperar()
        x0, y0, x1, y1 = self.caja(ids[0])
        self.assertAlmostEqual((x0 + x1) / 2, 400.0, places=6)
        self.assertAlmostEqual((y0 + y1) / 2, 300.0, places=6)
        self.assertTrue(any(g[0] == "v" and abs(g[1] - 400) < 1e-6 for g in guias), guias)
        self.assertTrue(any(g[0] == "h" and abs(g[1] - 300) < 1e-6 for g in guias), guias)
        self.assertEqual(v.photoshop.controlador.guias, [], "al soltar, las guías se van")

    def test_iman_con_otra_capa(self):
        from celular_natural.ui import iman
        v = self.v
        self.documento(800, 600)
        ids = self.agregar(0, 1)
        doc = v._documento
        xs, ys = iman.objetivos(doc, v._almacen, [ids[1]])
        x0, y0, x1, y1 = self.caja(ids[0])
        self.assertIn(x1, [o[0] for o in xs])
        # Una caja con el borde izquierdo a 4 px del borde derecho de la otra se pega.
        dx, dy, guias = iman.ajustar((x1 + 4, 400, x1 + 100, 450), xs, ys, 6)
        self.assertAlmostEqual(dx, -4)
        self.assertTrue(guias)

    def test_seleccion_multiple_mover_alinear_y_borrar(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        v = self.v
        p = v.panel_capas
        ps = v.photoshop
        self.documento(800, 600)
        ids = self.agregar(0, 1)  # en cascada
        ps.establecer_guias(False)
        # Ctrl+clic en el panel: las dos elegidas.
        p.elegir(ids[0])
        fila = p._fila_de(ids[1])
        rect = p.lista.visualItemRect(p.lista.item(fila))
        QTest.mouseClick(p.lista.viewport(), Qt.LeftButton, Qt.ControlModifier, rect.center())
        self.assertEqual(set(p.capas_elegidas), set(ids))
        # Mover las dos juntas.
        c0, c1 = self.caja(ids[0]), self.caja(ids[1])
        self.arrastrar(((c1[0] + c1[2]) / 2, (c1[1] + c1[3]) / 2), ((c1[0] + c1[2]) / 2 + 50, (c1[1] + c1[3]) / 2))
        self.esperar()
        self.assertAlmostEqual(self.caja(ids[0])[0], c0[0] + 50, delta=2)
        self.assertAlmostEqual(self.caja(ids[1])[0], c1[0] + 50, delta=2)
        self.assertEqual(self.paso(), "2 capas movidas")
        # Alinear arriba entre ellas.
        ps.alinear("arriba")
        self.esperar()
        self.assertAlmostEqual(self.caja(ids[0])[1], self.caja(ids[1])[1])
        # Una sola: respecto del lienzo.
        p.elegir(ids[0])
        ps.alinear("centro_h")
        self.esperar()
        x0, _y0, x1, _y1 = self.caja(ids[0])
        self.assertAlmostEqual((x0 + x1) / 2, 400.0)
        # Borrar las dos juntas (un paso).
        p.elegir_varias(ids)
        ps.borrar()
        self.esperar()
        self.assertEqual([c.tipo for c in v._documento.capas], ["relleno", "ajuste_natural"])
        self.assertEqual(self.paso(), "2 capas borradas")

    def test_seleccion_automatica_elige_la_de_arriba(self):
        v = self.v
        p = v.panel_capas
        self.documento(800, 600)
        ids = self.agregar(0, 1)
        c0 = self.caja(ids[0])
        p.elegir(ids[1])
        # Un punto que solo tapa la de abajo: el clic la elige.
        x, y = c0[0] + 3, c0[1] + 3
        self.assertEqual(v.photoshop.capa_bajo(__import__("PySide6.QtCore", fromlist=["QPointF"]).QPointF(x, y)),
                         ids[0])
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        QTest.mouseClick(v.vista, Qt.LeftButton, Qt.NoModifier, self.a_pantalla(x, y))
        self.assertEqual(p.capa_elegida, ids[0])
        # Sin selección automática, el clic no cambia la elegida.
        v.photoshop.check_auto.setChecked(False)
        p.elegir(ids[1])
        QTest.mouseClick(v.vista, Qt.LeftButton, Qt.NoModifier, self.a_pantalla(x, y))
        self.assertEqual(p.capa_elegida, ids[1])


# ====================================================================== panel Capas y Propiedades
class PruebasPaneles(_Base):
    def test_grupos_en_el_panel(self):
        from celular_natural.motor.estilos import EstilosCapa, Sombra
        from celular_natural.ui.panel_capas import ICONO_TIPO
        v = self.v
        p = v.panel_capas
        self.documento(400, 300)
        ids = self.agregar(0, 1, 2)
        p.elegir_varias(ids[:2])
        p.agrupar()
        self.esperar()
        grupo = p.capa_elegida
        self.assertEqual(v._documento.capa(grupo).tipo, "grupo")
        # Sangría y flecha para plegar.
        fila_grupo, fila_hijo = p.fila(grupo), p.fila(ids[0])
        self.assertIsNotNone(fila_grupo.boton_plegar)
        self.assertGreater(fila_hijo.layout().contentsMargins().left(), fila_grupo.layout().contentsMargins().left())
        self.assertEqual(fila_hijo.tipo, "imagen")
        self.assertIn("imagen", ICONO_TIPO)
        # Plegar esconde lo de adentro.
        p.alternar_plegado(grupo)
        self.assertTrue(p.lista.item(p._fila_de(ids[0])).isHidden())
        p.alternar_plegado(grupo)
        self.assertFalse(p.lista.item(p._fila_de(ids[0])).isHidden())
        # Arrastrar: la tercera capa adentro del grupo, y una de adentro, afuera (debajo del grupo).
        p.reubicar(ids[2], grupo, "dentro")
        self.esperar()
        self.assertEqual(v._documento.capa(ids[2]).padre, grupo)
        p.lista.capaSoltada.emit(ids[0], grupo, "debajo")
        self.esperar(lambda: self.quieto() and v._documento.capa(ids[0]).padre is None)
        # El menú contextual tiene lo pedido.
        p.elegir(ids[1])
        textos = [a.text().split("\t")[0] for a in p.menu_capa().actions() if a.text()]
        for t in ("Duplicar capa", "Borrar capa", "Agrupar", "Desagrupar", "Rasterizar", "Combinar hacia abajo"):
            self.assertIn(t, textos)
        # "fx" si la capa tiene estilos.
        doc = v._documento.con_capa(ids[1], estilos=EstilosCapa(sombra=Sombra()))
        v._cambiar_documento(doc, refrescar_panel=True)
        self.esperar()
        self.assertIsNotNone(p.fila(ids[1]).fx)
        self.assertIsNone(p.fila(ids[2]).fx)

    def test_propiedades(self):
        v = self.v
        ps = v.photoshop
        prop = ps.propiedades
        p = v.panel_capas
        self.documento(800, 600)
        ids = self.agregar(0)  # 160 × 100 centrado
        p.elegir(ids[0])
        self.assertTrue(prop.isVisible())
        self.assertAlmostEqual(prop.numero_x.value(), 320)
        self.assertAlmostEqual(prop.numero_y.value(), 250)
        self.assertAlmostEqual(prop.numero_ancho.value(), 160)
        self.assertAlmostEqual(prop.numero_alto.value(), 100)
        # X escrito: se mueve (un paso).
        prop.numero_x.setValue(10)
        self.esperar()
        self.assertAlmostEqual(self.caja(ids[0])[0], 10)
        self.assertEqual(self.paso(), "Capa «logo1» movida")
        # Ancho con la cadena: en proporción.
        prop.numero_ancho.setValue(320)
        self.esperar()
        t = v._documento.capa(ids[0]).transform
        self.assertAlmostEqual(t.escala, 2.0)
        self.assertAlmostEqual(t.escala_vertical, 2.0)
        # Sin la cadena: solo el alto.
        prop.boton_cadena.setChecked(False)
        prop.numero_alto.setValue(100)
        self.esperar()
        t = v._documento.capa(ids[0]).transform
        self.assertAlmostEqual(t.escala, 2.0)
        self.assertAlmostEqual(t.escala_vertical, 1.0)
        prop.numero_rotacion.setValue(30)
        self.esperar()
        self.assertAlmostEqual(v._documento.capa(ids[0]).transform.rotacion, 30)
        # Un relleno (el fondo del documento): sus colores y su ángulo.
        p.elegir(v._documento.capas[0].id)
        self.assertTrue(prop.caja_relleno.isVisible())
        prop.combo_relleno.setCurrentIndex(prop.combo_relleno.findData("lineal"))
        self.esperar()
        self.assertEqual(v._documento.capas[0].params.tipo, "lineal")
        boton = prop.editor_degradado.filas[1][0]
        boton.establecer((255, 0, 0, 255))
        boton.colorCambiado.emit(boton.color)
        self.esperar()
        self.assertEqual(v._documento.capas[0].params.colores[-1], (255, 0, 0, 255))
        prop.numero_angulo.setValue(0)
        self.esperar()
        self.assertEqual(v._documento.capas[0].params.angulo, 0.0)


# ====================================================================== sesión y documento_capas
class PruebasSesion(unittest.TestCase):
    def test_sesion_con_un_documento_de_la_etapa_2(self):
        from celular_natural import sesion
        from celular_natural.motor.estilos import (
            EstilosCapa, Resplandor, Sombra, SuperposicionColor, SuperposicionDegradado, Trazo,
        )
        from celular_natural.motor.procesado import Ajustes
        from celular_natural.motor.texto import ParamsTexto
        doc = Documento.nuevo_lienzo(640, 480, Relleno("lineal", ((255, 0, 0, 255), (0, 0, 255, 255))))
        estilos = EstilosCapa(sombra=Sombra(), trazo=Trazo(), resplandor=Resplandor(), color=SuperposicionColor(),
                              degradado=SuperposicionDegradado(Relleno("radial", ((0, 0, 0, 255), (255, 255, 255, 0)))))
        doc = doc.agregar(Capa("t", "texto", "Título", params=ParamsTexto("Hola\nmundo", negrita=True),
                               transform=Transformacion(320, 100, 1.0, 10, False, 1.5, True), estilos=estilos))
        doc = doc.agregar(Capa("f", "forma", "Estrella", params=ParamsForma("estrella", relleno=Relleno("color"))))
        doc = doc.agregar(Capa("r", "relleno", "Velo", params=Relleno("color", ((0, 0, 0, 128),))))
        doc = doc.agrupar(["t", "f"], id_grupo="g")
        estado = {"preset": "Natural", "ajustes": Ajustes(), "capas": [], "documento": doc}
        carpeta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        try:
            with mock.patch.dict(os.environ, {"APPDATA": carpeta.name, "NATURALSHOT_EDICION": "lite"}):
                sesion.guardar(sesion.SesionGuardada([sesion.FotoGuardada("Sin título 1.nsdoc", estado,
                                                                          [("Inicio", estado)], 0)], 0))
                guardada, problema = sesion.cargar()
                self.assertIsNone(problema)
                self.assertFalse(sesion.archivo_respaldo().exists(), "no fue a .bak")
            self.assertEqual(guardada.fotos[0].estado["documento"], doc)
            self.assertEqual(guardada.fotos[0].historial[0][1]["documento"].capa("t").estilos, estilos)
        finally:
            carpeta.cleanup()

    def test_convertir_documento_conserva_escala_y_y_voltear_v_y_todos_los_tipos(self):
        from celular_natural.motor.documento import AlmacenImagenes
        from celular_natural.ui import documento_capas as dc
        from celular_natural.motor.texto import ParamsTexto
        doc = Documento.nuevo(400, 300)
        t = Transformacion(100, 50, 1.0, 0.0, False, 2.0, True)
        doc = doc.agregar(Capa("f", "forma", "F", params=ParamsForma(), transform=t))
        doc = doc.agregar(Capa("x", "texto", "X", params=ParamsTexto("Hola"), transform=t))
        # Girar 90° a la derecha el marco (como girar la foto): la forma y el texto se llevan también.
        m = np.array([[0.0, -1.0, 300.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        nuevo = dc.convertir_documento(doc, AlmacenImagenes(), m, 300, 400)
        for i in ("f", "x"):
            tt = nuevo.capa(i).transform
            self.assertEqual((tt.x, tt.y), (250.0, 100.0))
            self.assertEqual(tt.rotacion, 90.0)
            self.assertEqual(tt.escala_y, 2.0)
            self.assertTrue(tt.voltear_v)
        # Con espejo: el volteo horizontal se invierte y el vertical queda.
        espejo = np.array([[-1.0, 0.0, 400.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        tt = dc.convertir_documento(doc, AlmacenImagenes(), espejo, 400, 300).capa("f").transform
        self.assertTrue(tt.voltear_h)
        self.assertTrue(tt.voltear_v)
        self.assertEqual(tt.escala_y, 2.0)


# ====================================================================== regresión del kit de flyers
class PruebasKitFlyer(_Base):
    def test_el_kit_sigue_andando_en_un_documento_nuevo(self):
        from PySide6.QtWidgets import QFileDialog
        from celular_natural.ui.kit_flyer import datos_texto_por_defecto
        v = self.v
        v.nuevo_lienzo(1080, 1920, (0, 0, 0))
        self.esperar(lambda: self.quieto() and v._fuente is not None and v._fuente.shape[:2] == (1920, 1080))
        self.assertEqual(int(v._fuente.max()), 0)
        self.assertTrue(v.boton_nuevo.isVisible())
        v.agregar_imagenes_como_capa([str(r) for r in self.fotos])
        self.esperar(lambda: self.quieto() and sum(c.tipo == "imagen" for c in v._documento.capas) == 4)
        xs = [c.transform.x for c in v._documento.capas if c.tipo == "imagen"]
        self.assertEqual(len(set(xs)), 4, "en cascada")
        v.agregar_texto({**datos_texto_por_defecto(), "texto": "Flyer"})
        self.esperar()
        self.assertTrue(any(c.tipo == "texto" and c.params.contenido == "Flyer" for c in v._documento.capas))
        destino = self.base / "flyer_u1.png"
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "PNG (*.png)")):
            v.exportar()
        self.esperar(lambda: not v._exportando and destino.exists())
        self.assertEqual(leer_png(destino).shape, (1920, 1080, 3))


if __name__ == "__main__":
    unittest.main()
