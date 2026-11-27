"""Pruebas de la **Medida** de salida (el botón "Medida" de Fácil y Editor), con la ventana real sin pantalla.

* **Motor** (``motor/medida.py``): el recorte centrado más grande, ajustar uno con otra proporción
  alrededor de su centro (misma superficie, sin salirse), llevar a la medida (achicar y agrandar,
  sin deformar nunca) y qué es una medida válida.
* **Ventana:** elegir 9:16 en una foto de 4000 × 3000 pone un recorte 9:16 centrado y exporta
  1080 × 1920; con un recorte previo lo ajusta; Original la quita (el recorte queda); deshacer y
  rehacer; la sesión la recuerda; el lote respeta la medida de cada foto; en el modo Fácil también;
  la vista es la exportación (la completa, igual; la rápida, a escala); Recortar con la proporción
  fija; girar 90° conserva la proporción; el menú, el botón y la cabecera; la barra compacta.
* **Regresión:** sin elegir medida, exportar da lo de siempre bit a bit (``procesar_pila`` sobre la
  foto que entra al filtro) y el estado no lleva la clave.

Corren en la edición del entorno (PRO por defecto; también con ``NATURALSHOT_EDICION=lite``).
Usan un .ini propio (``NATURALSHOT_CONFIG``), un APPDATA temporal e imágenes generadas.
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

from celular_natural.motor import medida as md  # noqa: E402
from celular_natural.motor import procesar_pila  # noqa: E402
from celular_natural.motor.zonas import Recorte  # noqa: E402

HISTORIA = (1080, 1920)
CUADRADO = (1080, 1080)
PC = (1920, 1080)


def foto(w, h, semilla=0) -> np.ndarray:
    """Un degradado con textura y un rectángulo rojo (para ver dónde cae el recorte)."""
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.dstack([60 + 150 * xx / w, 70 + 120 * yy / h, 210 - 120 * xx / w])
    img[int(h * .4):int(h * .7), int(w * .45):int(w * .55)] = (220, 40, 60)
    return np.clip(img + rng.normal(0, 5, (h, w, 3)), 0, 255).astype(np.uint8)


def leer_png(ruta) -> np.ndarray:
    from PIL import Image
    with Image.open(ruta) as im:
        return np.asarray(im.convert("RGB")).copy()


def caja_px(recorte, wb, hb):
    return (0, 0, wb, hb) if recorte is None else recorte.pixeles(wb, hb)


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


# ====================================================================== motor
class PruebasMotor(unittest.TestCase):
    def test_recorte_centrado_es_el_mas_grande(self):
        r = md.recorte_centrado(4000, 3000, HISTORIA)
        x0, y0, x1, y1 = r.pixeles(4000, 3000)
        self.assertEqual((y0, y1), (0, 3000))
        self.assertAlmostEqual((x1 - x0) / 3000, 9 / 16, delta=1 / 3000)
        self.assertAlmostEqual((x0 + x1) / 2, 2000, delta=1)
        # Más ancha que alta: se toma todo el ancho.
        x0, y0, x1, y1 = md.recorte_centrado(1000, 3000, CUADRADO).pixeles(1000, 3000)
        self.assertEqual((x0, x1, y1 - y0), (0, 1000, 1000))
        # Si ya tiene la proporción, no hace falta recortar.
        self.assertIsNone(md.recorte_centrado(1920, 1080, PC))

    def test_ajustar_un_recorte_alrededor_de_su_centro(self):
        previo = Recorte(0.1, 0.1, 0.5, 0.7)  # 1600 × 1800 px de 4000 × 3000
        nuevo = md.recorte_con_medida(previo, 4000, 3000, CUADRADO)
        x0, y0, x1, y1 = nuevo.pixeles(4000, 3000)
        self.assertLessEqual(abs((x1 - x0) - (y1 - y0)), 1)
        self.assertAlmostEqual((x0 + x1) / 2, 1200, delta=1)
        self.assertAlmostEqual((y0 + y1) / 2, 1200, delta=1)
        self.assertAlmostEqual((x1 - x0) * (y1 - y0), 1600 * 1800, delta=1600 * 1800 * 0.002)  # misma superficie
        # Con esa proporción, queda igual.
        self.assertEqual(md.recorte_con_medida(nuevo, 4000, 3000, CUADRADO), nuevo)
        # Cerca del borde no se sale de la foto.
        borde = md.recorte_con_medida(Recorte(0.0, 0.0, 0.2, 0.9), 4000, 3000, PC)
        bx0, by0, bx1, by1 = borde.pixeles(4000, 3000)
        self.assertTrue(0 <= bx0 and 0 <= by0 and bx1 <= 4000 and by1 <= 3000)
        self.assertTrue(md.tiene_proporcion(borde, 4000, 3000, PC))
        # El centrado de una medida pasa al centrado (el más grande) de la otra.
        c = md.recorte_con_medida(md.recorte_centrado(4000, 3000, HISTORIA), 4000, 3000, PC, previa=HISTORIA)
        self.assertEqual(c, md.recorte_centrado(4000, 3000, PC))

    def test_llevar_a_medida(self):
        img = foto(1688, 3000)
        chica = md.llevar_a_medida(img, HISTORIA)
        self.assertEqual(chica.shape, (1920, 1080, 3))
        self.assertTrue(np.array_equal(chica, cv2.resize(img, HISTORIA, interpolation=cv2.INTER_AREA)))
        grande = md.llevar_a_medida(foto(960, 540), (3840, 2160))
        self.assertEqual(grande.shape, (2160, 3840, 3))
        self.assertTrue(np.array_equal(grande, cv2.resize(foto(960, 540), (3840, 2160),
                                                          interpolation=cv2.INTER_LANCZOS4)))
        # Con otra proporción (no debería llegar así) se recorta al centro: no se deforma.
        a = np.zeros((100, 300), np.uint8)
        a[:, 100:200] = 255
        self.assertTrue((md.llevar_a_medida(a, (50, 50)) == 255).all())
        self.assertIs(md.llevar_a_medida(img, (1688, 3000)), img)

    def test_medida_valida_y_textos(self):
        self.assertEqual(md.medida_valida([1080, 1920]), HISTORIA)
        for malo in (None, (), (0, 10), (1080,), "1080x1920", (True, 5), (1, 10 ** 6)):
            self.assertIsNone(md.medida_valida(malo), malo)
        self.assertEqual(md.texto_boton(HISTORIA), "9:16 · 1080×1920")
        self.assertEqual(md.texto_boton(None), "Medida")
        self.assertEqual([m.tam for m in md.MEDIDAS], [HISTORIA, PC, (3840, 2160), (3024, 4032), (4032, 3024),
                                                       (1080, 1350), CUADRADO])

    def test_tamano_trabajo(self):
        self.assertEqual(md.tamano_trabajo(HISTORIA, (3000, 1688), 1.0), (HISTORIA, 1.0))
        (w, h), e = md.tamano_trabajo(HISTORIA, (1280, 720), 0.43)
        self.assertEqual((w, h), (720, 1280))
        self.assertAlmostEqual(e, 1280 / 1920)
        # Una foto chica que se agranda: la vista previa trabaja a su lado.
        (w, h), e = md.tamano_trabajo((3840, 2160), (540, 960), 0.5)
        self.assertEqual((w, h), (960, 540))


# ====================================================================== ventana
class _Base(unittest.TestCase):
    activar_sesion = False

    @classmethod
    def setUpClass(cls):
        from PIL import Image
        cls.app = _app()
        cls.carpeta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        base = Path(cls.carpeta.name)
        cls._entorno = {k: os.environ.get(k) for k in ("APPDATA", "NATURALSHOT_CONFIG")}
        os.environ["APPDATA"] = str(base / "appdata")
        os.environ["NATURALSHOT_CONFIG"] = str(base / "config.ini")
        cls.base = base
        cls.grande = base / "grande.png"
        Image.fromarray(foto(4000, 3000)).save(cls.grande)
        cls.chicas = []
        for i in range(3):
            r = base / f"chica{i}.png"
            Image.fromarray(foto(1200, 900, semilla=i + 1)).save(r)
            cls.chicas.append(r)

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
    def ventana(self, rutas=(), modo="editor", activar=False, ancho=1366):
        from celular_natural.ui.ventana import VentanaPrincipal
        v = VentanaPrincipal()
        v.resize(ancho, 768)
        v.show()
        v.establecer_modo(modo, guardar=False)
        self.ventanas.append(v)
        if activar:
            v.activar_sesion()
            self.esperar(lambda: v.sesion_restaurada, v)
        if rutas:
            v.abrir_rutas([str(r) for r in rutas])
            self.esperar(v=v)
        return v

    def cerrar(self, v):
        v.close()
        self.ventanas.remove(v)
        v.deleteLater()
        self.app.processEvents()

    @staticmethod
    def quieto(v) -> bool:
        return (v._imagen is not None and not v._fuentes_pendientes and v._deteccion is None
                and v._generacion_completa_mostrada == v._generacion and not v._exportando
                and v._pool_archivos.activeThreadCount() == 0)

    def esperar(self, condicion=None, v=None, segundos=90.0):
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

    def exportar(self, v, nombre, boton=None) -> np.ndarray:
        from PySide6.QtWidgets import QFileDialog
        destino = self.base / nombre
        if destino.exists():
            destino.unlink()
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destino), "PNG (*.png)")):
            (boton.click if boton is not None else v.exportar)()
        self.esperar(lambda: not v._exportando and destino.exists(), v)
        self.esperar(v=v)
        return leer_png(destino)

    def elegir(self, v, tam):
        v.elegir_medida(tam)
        self.esperar(v=v)

    def paso(self, v) -> str:
        return v._historial[v._pos_historial][0]

    def vista(self, v) -> np.ndarray:
        self.esperar(v=v)
        return v._resultado_completo[1].copy()


class PruebasVentana(_Base):
    def test_9_16_en_4000x3000_recorte_centrado_y_exporta_1080x1920(self):
        v = self.ventana([self.grande])
        self.elegir(v, HISTORIA)
        self.assertEqual(v._medida, HISTORIA)
        x0, y0, x1, y1 = caja_px(v._recorte, 4000, 3000)
        self.assertEqual((y0, y1), (0, 3000))
        self.assertAlmostEqual((x0 + x1) / 2, 2000, delta=1)
        self.assertAlmostEqual(x1 - x0, 1687.5, delta=1)
        self.assertEqual(v._fuente.shape[:2], (3000, x1 - x0))  # la foto que entra: la recortada
        self.assertTrue(self.paso(v).startswith("Medida: Celular vertical"), self.paso(v))
        self.assertEqual(v._estado_completo()["medida"], HISTORIA)
        # El botón y la cabecera.
        self.assertEqual(v.boton_medida.property("texto"), " 9:16 · 1080×1920")
        self.assertTrue(v.boton_medida.property("activo"))
        self.assertFalse(v.etiqueta_medida.isHidden())
        self.assertTrue(v.etiqueta_medida.text().endswith("1080 × 1920"))
        # Vista = exportación, exacta a 1080 × 1920.
        vista = self.vista(v)
        self.assertEqual(vista.shape, (1920, 1080, 3))
        exportada = self.exportar(v, "historia.png")
        self.assertEqual(exportada.shape, (1920, 1080, 3))
        self.assertTrue(np.array_equal(exportada, vista))
        # El filtro trabajó a la resolución de salida: es el filtro sobre la recortada ya llevada a 1080 × 1920.
        pa = v.panel_ajustes
        esperado = procesar_pila(md.llevar_a_medida(v._fuente, HISTORIA), pa.pila(), escala_vista=1.0,
                                 zonas=pa.zonas(), recorte=v._recorte)
        self.assertTrue(np.array_equal(exportada, esperado))
        # El rectángulo rojo del centro sigue en el centro.
        self.assertGreater(exportada[960, 540, 0], 150)

    def test_vista_rapida_a_escala_coincide_con_la_exportacion(self):
        from celular_natural.ui.ventana import procesar_con_capas
        v = self.ventana([self.grande])
        self.elegir(v, HISTORIA)
        exportada = self.exportar(v, "historia_vista.png")
        # La vista previa rápida, como la arma la ventana (la foto reducida y su escala).
        self.assertLess(v._escala_vista_previa, 1.0)
        pa = v.panel_ajustes
        rapida = procesar_con_capas(v._vista_previa, None, v._almacen, pa.pila(), pa.zonas(), v._recorte, None,
                                    v._escala_vista_previa, (v._fuente.shape[1], v._fuente.shape[0]),
                                    medida=v._medida_vista())
        self.assertEqual(rapida.shape[1] / rapida.shape[0], 1080 / 1920)
        chica = cv2.resize(exportada, (rapida.shape[1], rapida.shape[0]), interpolation=cv2.INTER_AREA)
        suave = [cv2.GaussianBlur(x.astype(np.float32), (0, 0), 3) for x in (rapida, chica)]
        self.assertLess(float(np.abs(suave[0] - suave[1]).mean()), 4.0)

    def test_con_recorte_previo_lo_ajusta_y_con_la_misma_proporcion_lo_deja(self):
        v = self.ventana([self.chicas[0]])
        v._recorte = Recorte(0.1, 0.2, 0.6, 0.9)  # 600 × 630 px de 1200 × 900
        v._recalcular_fuentes()
        self.esperar(v=v)
        v._registrar_historial()
        self.elegir(v, CUADRADO)
        x0, y0, x1, y1 = caja_px(v._recorte, 1200, 900)
        self.assertLessEqual(abs((x1 - x0) - (y1 - y0)), 1)
        self.assertAlmostEqual((x0 + x1) / 2, 420, delta=1)
        self.assertAlmostEqual((y0 + y1) / 2, 495, delta=1)
        self.assertEqual(self.exportar(v, "cuadrado.png").shape, (1080, 1080, 3))  # agrandada (Lanczos)
        # Un recorte que ya tiene la proporción (corrido a un costado) queda donde está.
        self.elegir(v, None)
        cuadrado = Recorte(0.0, 0.0, 600 / 1200, 600 / 900)
        v._recorte = cuadrado
        v._recalcular_fuentes()
        self.esperar(v=v)
        v._registrar_historial()
        self.elegir(v, CUADRADO)
        self.assertEqual(v._recorte, cuadrado)

    def test_original_quita_la_medida_y_el_recorte_queda(self):
        v = self.ventana([self.chicas[0]])
        self.elegir(v, HISTORIA)
        recorte = v._recorte
        self.elegir(v, None)
        self.assertIsNone(v._medida)
        self.assertEqual(v._recorte, recorte)
        self.assertNotIn("medida", v._estado_completo())
        self.assertEqual(self.paso(v), "Medida: original")
        self.assertEqual(v.boton_medida.property("texto"), " Medida")
        self.assertFalse(v.boton_medida.property("activo"))
        self.assertTrue(v.etiqueta_medida.isHidden())
        exportada = self.exportar(v, "original.png")
        self.assertEqual(exportada.shape, v._fuente.shape)

    def test_deshacer_y_rehacer(self):
        v = self.ventana([self.chicas[0]])
        self.elegir(v, HISTORIA)
        self.elegir(v, PC)
        self.assertEqual(v._medida, PC)
        v.deshacer()
        self.esperar(v=v)
        self.assertEqual(v._medida, HISTORIA)
        self.assertTrue(md.tiene_proporcion(v._recorte, 1200, 900, HISTORIA))
        self.assertTrue(v.etiqueta_medida.text().endswith("1080 × 1920"))
        self.assertEqual(self.vista(v).shape, (1920, 1080, 3))
        v.deshacer()
        self.esperar(v=v)
        self.assertIsNone(v._medida)
        self.assertIsNone(v._recorte)
        self.assertEqual(self.vista(v).shape, (900, 1200, 3))
        v.rehacer()
        v.rehacer()
        self.esperar(v=v)
        self.assertEqual(v._medida, PC)
        self.assertEqual(self.vista(v).shape, (1080, 1920, 3))

    def test_la_sesion_la_recuerda(self):
        v = self.ventana(activar=True)
        v.abrir_rutas([str(r) for r in self.chicas[:2]])
        self.esperar(v=v)
        self.elegir(v, HISTORIA)
        recorte = v._recorte
        v.cambiar_a_foto(1)
        self.esperar(lambda: v._actual == 1 and self.quieto(v), v)
        self.assertIsNone(v._medida)  # cada foto la suya
        self.elegir(v, CUADRADO)
        self.cerrar(v)
        v = self.ventana(activar=True)
        self.esperar(v=v)
        self.assertEqual(v._actual, 1)
        self.assertEqual(v._medida, CUADRADO)
        self.assertTrue(v.etiqueta_medida.text().endswith("1080 × 1080"))
        v.cambiar_a_foto(0)
        self.esperar(lambda: v._actual == 0 and self.quieto(v), v)
        self.assertEqual(v._medida, HISTORIA)
        self.assertEqual(v._recorte, recorte)
        self.assertEqual(self.exportar(v, "de_la_sesion.png").shape, (1920, 1080, 3))
        v.deshacer()  # el historial también vino
        self.esperar(v=v)
        self.assertIsNone(v._medida)

    def test_el_lote_respeta_la_medida_de_cada_foto(self):
        from PySide6.QtWidgets import QFileDialog
        v = self.ventana(self.chicas)
        self.elegir(v, HISTORIA)
        v.cambiar_a_foto(1)
        self.esperar(lambda: v._actual == 1 and self.quieto(v), v)
        v.girar(1)  # girada: el lote también la gira antes de recortar
        self.esperar(v=v)
        self.elegir(v, CUADRADO)
        esperada_1 = self.exportar(v, "una_cuadrada.png")
        v.cambiar_a_foto(0)
        self.esperar(lambda: v._actual == 0 and self.quieto(v), v)
        carpeta = self.base / "lote"
        carpeta.mkdir(exist_ok=True)
        rutas = [str(r) for r in self.chicas]
        # Con fotos en la tira, "Exportar varias" ofrece esas; con "Elegir otras…", el selector de siempre.
        with mock.patch.object(v, "_preguntar_lote", return_value="otras") as pregunta, \
                mock.patch.object(QFileDialog, "getOpenFileNames", return_value=(rutas, "")), \
                mock.patch.object(QFileDialog, "getExistingDirectory", return_value=str(carpeta)):
            v.procesar_varias()
        pregunta.assert_called_once_with(3)
        self.esperar(lambda: not v._exportando, v)
        salidas = {p.name: leer_png(p) for p in carpeta.iterdir()}
        self.assertEqual(salidas["chica0_celular.png"].shape, (1920, 1080, 3))
        self.assertEqual(salidas["chica1_celular.png"].shape, (1080, 1080, 3))
        self.assertEqual(salidas["chica2_celular.png"].shape, (900, 1200, 3))  # sin medida, como siempre
        # Sin zonas ni montaje, el lote da lo mismo que exportarla sola.
        self.assertTrue(np.array_equal(salidas["chica1_celular.png"], esperada_1))

    def test_exportar_varias_ofrece_las_fotos_abiertas(self):
        """Un clic: "Las 3 abiertas" exporta las de la tira sin abrir el selector; Cancelar no hace nada."""
        from PySide6.QtWidgets import QFileDialog
        v = self.ventana(self.chicas)
        self.esperar(v=v)
        carpeta = self.base / "abiertas"
        carpeta.mkdir(exist_ok=True)
        with mock.patch.object(v, "_preguntar_lote", return_value=""), \
                mock.patch.object(QFileDialog, "getOpenFileNames") as selector:
            v.procesar_varias()
        selector.assert_not_called()
        self.assertFalse(v._exportando)
        with mock.patch.object(v, "_preguntar_lote", return_value="abiertas"), \
                mock.patch.object(QFileDialog, "getOpenFileNames") as selector, \
                mock.patch.object(QFileDialog, "getExistingDirectory", return_value=str(carpeta)):
            v.procesar_varias()
        selector.assert_not_called()
        self.esperar(lambda: not v._exportando, v)
        self.assertEqual(sorted(p.name for p in carpeta.iterdir()),
                         sorted(f"{Path(r).stem}_celular.png" for r in self.chicas))

    def test_en_el_modo_facil_tambien(self):
        from celular_natural.ui.modo_facil import FACIL
        v = self.ventana([self.chicas[0]], modo=FACIL)
        self.assertFalse(v._segmento_medida.isHidden())
        # Desde el menú, como el usuario: abrirlo y tocar la fila.
        v.boton_medida.click()
        self.app.processEvents()
        self.assertTrue(v.menu_medida.isVisible())
        self.assertEqual(len(v.menu_medida.filas), 8)
        self.assertTrue(v.menu_medida.filas[0][1].property("elegida"))  # Original
        fila = next(f for t, f, _a in v.menu_medida.filas if t == (1080, 1350))
        fila.tocada.emit()
        self.esperar(v=v)
        self.assertFalse(v.menu_medida.isVisible())
        self.assertEqual(v._medida, (1080, 1350))
        exportada = self.exportar(v, "facil.png", boton=v.panel_facil.boton_exportar)
        self.assertEqual(exportada.shape, (1350, 1080, 3))
        self.assertTrue(np.array_equal(exportada, self.vista(v)))
        # El menú muestra la tilde en la elegida.
        v.menu_medida.armar(v._medida)
        elegidas = [t for t, f, _a in v.menu_medida.filas if f.property("elegida")]
        self.assertEqual(elegidas, [(1080, 1350)])

    def test_recortar_con_la_proporcion_fija(self):
        from PySide6.QtCore import QRectF
        v = self.ventana([self.chicas[0]])
        self.elegir(v, HISTORIA)
        v.boton_recortar.setChecked(True)
        self.app.processEvents()
        self.assertFalse(v.combo_aspecto.isEnabled())
        self.assertAlmostEqual(v._aspecto(), 9 / 16)
        self.assertAlmostEqual(v.vista._aspecto, 9 / 16)
        # Correr el recuadro a la izquierda y aplicar: la medida sigue, con la proporción.
        sel = v.vista.seleccion_normalizada()
        v.vista._sel = QRectF(0, sel.y() * 900, sel.width() * 1200, sel.height() * 900)
        v._salir_recorte("aplicar")
        self.esperar(v=v)
        self.assertEqual(v._medida, HISTORIA)
        self.assertLess(v._recorte.x0, 0.01)
        self.assertTrue(md.tiene_proporcion(v._recorte, 1200, 900, HISTORIA))
        self.assertEqual(self.exportar(v, "corrida.png").shape, (1920, 1080, 3))
        # "Quitar recorte" con una medida vuelve al centrado (sin recorte no entra).
        v.boton_recortar.setChecked(True)
        self.app.processEvents()
        v._salir_recorte("quitar")
        self.esperar(v=v)
        self.assertEqual(v._recorte, md.recorte_centrado(1200, 900, HISTORIA))
        # Sin medida, el combo vuelve a estar libre.
        self.elegir(v, None)
        v.boton_recortar.setChecked(True)
        self.app.processEvents()
        self.assertTrue(v.combo_aspecto.isEnabled())
        v._salir_recorte("cancelar")

    def test_girar_conserva_la_proporcion(self):
        v = self.ventana([self.chicas[0]])
        self.elegir(v, HISTORIA)
        v.girar(1)
        self.esperar(v=v)
        self.assertEqual(v._medida, HISTORIA)
        self.assertTrue(md.tiene_proporcion(v._recorte, 900, 1200, HISTORIA))
        self.assertEqual(self.vista(v).shape, (1920, 1080, 3))
        v.deshacer()
        self.esperar(v=v)
        self.assertTrue(md.tiene_proporcion(v._recorte, 1200, 900, HISTORIA))

    def test_sin_medida_es_lo_de_antes_bit_a_bit(self):
        v = self.ventana([self.chicas[0]])
        v.panel_ajustes.combo_preset.setCurrentText("Noche urbana")
        v._recorte = Recorte(0.1, 0.1, 0.8, 0.9)
        v._recalcular_fuentes()
        self.esperar(v=v)
        pa = v.panel_ajustes
        antes = procesar_pila(v._fuente, pa.pila(), escala_vista=1.0, zonas=pa.zonas(), recorte=v._recorte)
        self.assertTrue(np.array_equal(self.vista(v), antes))
        self.assertTrue(np.array_equal(self.exportar(v, "regresion.png"), antes))
        self.assertNotIn("medida", v._estado_completo())
        self.assertTrue(all("medida" not in e for _d, e in v._historial))

    def test_barra_compacta(self):
        v = self.ventana([self.chicas[0]], ancho=1000)
        self.elegir(v, HISTORIA)
        v._compactar_barra()
        self.assertEqual(v.boton_medida.text(), "")  # solo el ícono, como Recortar
        self.assertEqual(v.boton_medida.property("texto"), " 9:16 · 1080×1920")
        self.assertEqual(v.etiqueta_medida.text(), "1080 × 1920")  # la cabecera, sin el "Sale a"
        from celular_natural.ui.modo_facil import FACIL
        v.resize(1900, 900)
        v.establecer_modo(FACIL, guardar=False)  # sin la columna derecha: entra todo
        self.app.processEvents()
        v._compactar_barra()
        self.assertEqual(v.boton_medida.text(), " 9:16 · 1080×1920")
        self.assertTrue(all(b.text() for b in v.grupo_modo.buttons()))
        # Antes de sacarles el nombre a los modos, Medida se acorta a la proporción.
        for ancho in range(1900, 900, -20):
            v.resize(ancho, 900)
            self.app.processEvents()
            v._compactar_barra()
            if v.boton_medida.text() != " 9:16 · 1080×1920":
                break
        self.assertEqual(v.boton_medida.text(), " 9:16")
        self.assertTrue(all(b.text() for b in v.grupo_modo.buttons()))
        self.assertEqual(v.etiqueta_medida.text(), "Sale a 1080 × 1920")

    def test_photoshop_no_la_muestra_y_exporta_igual(self):
        from celular_natural import edicion
        if not edicion.es_lite():
            self.skipTest("el modo Photoshop es de la Lite")
        from celular_natural.ui.modo_facil import EDITOR, PHOTOSHOP
        v = self.ventana([self.chicas[0]])
        self.elegir(v, HISTORIA)
        v.establecer_modo(PHOTOSHOP, guardar=False)
        self.esperar(v=v)
        self.assertTrue(v._segmento_medida.isHidden())
        self.assertEqual(self.vista(v).shape[:2], v._fuente.shape[:2])  # la foto a su tamaño, sin la medida
        self.assertEqual(self.exportar(v, "desde_ps.png").shape, (1920, 1080, 3))
        v.establecer_modo(EDITOR, guardar=False)
        self.esperar(v=v)
        self.assertFalse(v._segmento_medida.isHidden())
        self.assertEqual(self.vista(v).shape, (1920, 1080, 3))


if __name__ == "__main__":
    unittest.main()
