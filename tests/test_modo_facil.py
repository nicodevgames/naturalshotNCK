"""Pruebas del modo fácil y del selector "Fácil | Editor".

* Cambiar de modo conserva todo el estado: foto, tira, historial, preset y lo
  editado en el editor (y cancela la herramienta del editor que estaba a medias).
* Tocar una tarjeta de la galería cambia el preset y queda en el historial.
* Las miniaturas se calculan en segundo plano y se guardan en caché por foto y
  preset; se recalculan si cambia la foto, la geometría o el recorte.
* El modo se recuerda (QSettings) y la primera vez es Fácil.
* En Fácil se oculta la columna derecha y la barra superior queda con lo esencial.
* Exportar desde Fácil produce el mismo archivo que desde Editor.

Usan un .ini propio (``NATURALSHOT_CONFIG``) y un APPDATA temporal: no leen ni
cambian las preferencias ni los presets guardados del usuario.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")  # si esta prueba crea la aplicación
# Las ventanas de todas las pruebas leen el modo de las preferencias: que usen un .ini
# temporal y no el registro del usuario (se fija al importar, antes de cualquier prueba).
if "NATURALSHOT_CONFIG" not in os.environ:
    import atexit
    import shutil
    _CARPETA_CONFIG = tempfile.mkdtemp(prefix="naturalshot_config_")
    atexit.register(shutil.rmtree, _CARPETA_CONFIG, True)
    os.environ["NATURALSHOT_CONFIG"] = os.path.join(_CARPETA_CONFIG, "preferencias.ini")

from celular_natural.motor import (  # noqa: E402
    PRESET_PRINCIPAL, PRESETS, Recorte, Zona, ZonaBorrado, procesar_pila, reducir_para_vista,
)


def escena(w=640, h=480, semilla=0):
    """Cielo, pasto con textura y un cuadrado rojo."""
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cielo = np.dstack([90 + 60 * yy / h, 150 + 50 * yy / h, 230 + 0 * yy])
    grano = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), 1.5)
    pasto = np.dstack([60 + 0 * xx, 120 + 0 * xx, 50 + 0 * xx]) + 30 * grano[..., None]
    img = np.where((yy > h * 0.5)[..., None], pasto, cielo)
    img[int(h * 0.6):int(h * 0.8), int(w * 0.3):int(w * 0.4)] = (210, 30, 30)
    return np.clip(img + rng.normal(0, 2, (h, w, 1)) + 0.5, 0, 255).astype(np.uint8)


def a_arreglo(pixmap) -> np.ndarray:
    from PySide6.QtGui import QImage
    im = pixmap.toImage().convertToFormat(QImage.Format_RGB888)
    datos = np.frombuffer(im.constBits(), np.uint8, count=im.sizeInBytes())
    filas = datos.reshape(im.height(), im.bytesPerLine())[:, :im.width() * 3]
    return filas.reshape(im.height(), im.width(), 3).copy()  # copia: la QImage se libera al salir


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class PruebasModoFacil(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PIL import Image
        cls.app = _app()
        cls.carpeta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        base = Path(cls.carpeta.name)
        cls._entorno = {k: os.environ.get(k) for k in ("APPDATA", "NATURALSHOT_CONFIG")}
        os.environ["APPDATA"] = str(base / "appdata")  # sin los presets propios del usuario
        cls.config = base / "config.ini"
        os.environ["NATURALSHOT_CONFIG"] = str(cls.config)  # sin tocar el registro del usuario
        cls.ruta = base / "escena.png"
        Image.fromarray(escena()).save(cls.ruta)
        cls.ruta2 = base / "otra.png"
        Image.fromarray(escena(480, 640, semilla=2)).save(cls.ruta2)

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
        if self.config.exists():
            self.config.unlink()  # cada prueba arranca como la primera vez
        self.v = VentanaPrincipal()
        self.v.resize(1366, 768)
        self.v.show()
        self.v.abrir_archivo(str(self.ruta))
        self.esperar()

    def tearDown(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        self.v.close()
        self.v.deleteLater()
        self.app.processEvents()
        # deleteLater() sin un bucle de eventos corriendo no borra nada: se completa el borrado acá.
        # Si no, cada ventana cerrada queda viva hasta el final de la suite (con sus miles de widgets).
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    # ------------------------------------------------------------ ayudas
    def quieto(self) -> bool:
        v = self.v
        return (v._imagen is not None and not v._fuentes_pendientes and v._deteccion is None
                and v._generacion_completa_mostrada == v._generacion and not v._exportando)

    def esperar(self, condicion=None, segundos=60.0):
        condicion = condicion or self.quieto
        fin = time.monotonic() + segundos
        while time.monotonic() < fin:
            self.app.processEvents()
            if condicion():
                for _ in range(5):
                    self.app.processEvents()
                if condicion():
                    return
            time.sleep(0.01)
        self.fail("la ventana no terminó de procesar")

    def miniaturas_listas(self) -> bool:
        pf = self.v.panel_facil
        return self.quieto() and not pf._timer_miniaturas.isActive() and pf.miniaturas_listas()

    def pausa(self, segundos=0.4):
        fin = time.monotonic() + segundos
        while time.monotonic() < fin:
            self.app.processEvents()
            time.sleep(0.01)

    def registrar(self):
        self.v._timer_historial.stop()
        self.v._registrar_historial()

    # ------------------------------------------------------------ pruebas
    def test_cambiar_de_modo_conserva_el_estado(self):
        from celular_natural.ui.modo_facil import EDITOR, FACIL
        v = self.v
        v.establecer_modo(EDITOR, guardar=False)
        v.panel_ajustes.combo_preset.setCurrentText("Noche urbana")
        v.panel_ajustes.agregar_capa("Día nublado", 40, zona=Zona("rect", 0.1, 0.1, 0.5, 0.5))
        v.panel_borrar.agregar(ZonaBorrado(Zona("rect", 0.6, 0.6, 0.7, 0.7)))
        self.esperar()
        v.girar(1)
        self.esperar()
        self.registrar()
        v.agregar_fotos([str(self.ruta2)])
        self.esperar(lambda: self.quieto() and v._imagen.ruta.name == "otra.png")
        v.cambiar_a_foto(0)
        self.esperar(lambda: self.quieto() and v._imagen.ruta.name == "escena.png")
        estado = v._estado_completo()
        historial, pos = list(v._historial), v._pos_historial
        fotos, actual = [f.ruta for f in v._fotos], v._actual
        vista = v._resultado_completo[1].copy()
        for modo in (FACIL, EDITOR, FACIL):
            v.establecer_modo(modo, guardar=False)
            self.esperar()
            self.assertEqual(v.modo, modo)
            self.assertEqual(v._estado_completo(), estado)
            self.assertEqual(v._historial, historial)
            self.assertEqual(v._pos_historial, pos)
            self.assertEqual([f.ruta for f in v._fotos], fotos)
            self.assertEqual(v._actual, actual)
            self.assertTrue(np.array_equal(v._resultado_completo[1], vista))
        # El modo fácil muestra lo mismo: el estilo elegido, la intensidad y el aviso del editor.
        pf = v.panel_facil
        self.assertEqual(pf.galeria.seleccionado, "Noche urbana")
        self.assertTrue(pf.galeria.tarjetas["Noche urbana"].seleccionada)
        self.assertEqual(pf.slider_intensidad.value(), v.panel_ajustes.ajustes().intensidad)
        self.assertTrue(pf.nota_editor.isVisible())
        self.assertIn("capas", pf.texto_nota_editor.text())
        self.assertIn("objetos borrados", pf.texto_nota_editor.text())
        self.assertIn("se mantienen", pf.texto_nota_editor.text())
        # Ctrl+Z y Ctrl+Y siguen andando en Fácil, sobre el mismo historial.
        v.deshacer()
        self.esperar()
        self.assertNotEqual(v._estado_completo(), estado)
        v.rehacer()
        self.esperar()
        self.assertEqual(v._estado_completo(), estado)
        # Una herramienta del editor a medias (pintar una zona) se cancela sin cambiar nada.
        v.establecer_modo(EDITOR, guardar=False)
        capa = v.panel_ajustes.capas()[0]
        zona = capa.zona
        v._pedir_zona(capa, "pincel")
        self.assertTrue(v.vista.pintando)
        v.establecer_modo(FACIL, guardar=False)
        self.assertIsNone(v._capa_zona)
        self.assertFalse(v.vista.pintando)
        self.assertTrue(v.barra_pincel.isHidden())
        self.assertEqual(v.panel_ajustes.capas()[0].zona, zona)
        self.assertEqual(v._estado_completo(), estado)

    def test_tarjeta_cambia_el_preset_y_queda_en_el_historial(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        v = self.v
        pf = v.panel_facil
        self.assertEqual(v.modo, "facil")
        self.registrar()
        pasos = len(v._historial)
        tarjeta = pf.galeria.tarjetas["Celular natural — marcado"]
        QTest.mouseClick(tarjeta, Qt.LeftButton)
        self.assertEqual(v.panel_ajustes.estado()["preset"], "Celular natural — marcado")
        self.assertEqual(v.panel_ajustes.combo_preset.currentText(), "Celular natural — marcado")
        self.assertTrue(tarjeta.seleccionada)
        self.assertEqual(sum(t.seleccionada for t in pf.galeria.tarjetas.values()), 1)
        # El historial anota el paso solo, cuando los controles quedan quietos (como en el editor).
        self.esperar(lambda: len(v._historial) == pasos + 1)
        self.assertEqual(v._historial[-1][0], "Preset: Celular natural — marcado")
        # La intensidad del paso 3 es la del editor y también queda en el historial.
        pf.slider_intensidad.setValue(40)
        self.assertEqual(v.panel_ajustes.ajustes().intensidad, 40)
        self.assertEqual(v.panel_ajustes.intensidad.valor(), 40)
        self.esperar(lambda: len(v._historial) == pasos + 2)
        self.assertEqual(v._historial[-1][0], "Intensidad general: 100 → 40")
        # Otro estilo conserva la intensidad, como el desplegable del editor.
        QTest.mouseClick(pf.galeria.tarjetas["Noche urbana"], Qt.LeftButton)
        self.assertEqual(v.panel_ajustes.ajustes(), replace(PRESETS["Noche urbana"], intensidad=40))
        self.esperar(lambda: len(v._historial) == pasos + 3)
        # Deshacer vuelve al estilo anterior y la galería lo acompaña.
        v.deshacer()
        self.esperar()
        self.pausa(0.05)
        self.assertEqual(v.panel_ajustes.estado()["preset"], "Celular natural — marcado")
        self.assertEqual(pf.galeria.seleccionado, "Celular natural — marcado")
        self.assertEqual(pf.slider_intensidad.value(), 40)
        # Con el teclado: Tab hasta la tarjeta y Enter.
        otra = pf.galeria.tarjetas["Estilo iPhone 15 Pro"]
        QTest.keyClick(otra, Qt.Key_Return)
        self.assertEqual(v.panel_ajustes.estado()["preset"], "Estilo iPhone 15 Pro")
        # "Sin efecto" está en "Ver más" y deja la foto como estaba.
        pf.galeria.tarjetas["Sin efecto"].elegida.emit("Sin efecto")
        self.assertEqual(v.panel_ajustes.estado()["preset"], "Sin efecto")

    def test_miniaturas_se_generan_y_se_cachean(self):
        from celular_natural.ui.modo_facil import EDITOR, FACIL, LADO_ESTILO
        v = self.v
        pf = v.panel_facil
        self.esperar(self.miniaturas_listas)
        n = len(pf.galeria.tarjetas)
        self.assertGreaterEqual(n, 30)  # los 34 presets y "Sin efecto"
        self.assertEqual(pf.calculadas, n)
        # Cada una es la foto actual reducida y procesada con su preset (con la escala correcta).
        clave, rgb, escala, _t = v.fuente_para_estilos()
        chica, f = reducir_para_vista(rgb, LADO_ESTILO)
        for nombre in ("Noche urbana", PRESET_PRINCIPAL):
            esperado = procesar_pila(chica, (PRESETS[nombre],), escala_vista=escala * f)
            obtenido = a_arreglo(pf.galeria.tarjetas[nombre].miniatura)
            self.assertTrue(np.array_equal(obtenido, esperado), nombre)
        self.assertTrue(np.array_equal(a_arreglo(pf.galeria.tarjetas["Sin efecto"].miniatura), chica))
        self.assertFalse(np.array_equal(a_arreglo(pf.galeria.tarjetas["Noche urbana"].miniatura), chica))
        for t in pf.galeria.tarjetas.values():
            self.assertTrue(220 <= max(t.miniatura.width(), t.miniatura.height()) <= 260)
        # Corren en un hilo propio, aparte de los de la vista previa.
        self.assertNotIn(pf._pool, (v._pool_rapido, v._pool_completo, v._pool_archivos))
        self.assertEqual(pf._pool.maxThreadCount(), 1)

        # Pedirlas de nuevo o cambiar de modo no recalcula: salen de la caché.
        pf.fuente_cambiada(inmediato=True)
        v.establecer_modo(EDITOR, guardar=False)
        v.establecer_modo(FACIL, guardar=False)
        self.esperar(self.miniaturas_listas)
        self.assertEqual(pf.calculadas, n)

        # Girar cambia la foto base: se recalculan, ya giradas.
        v.girar(1)
        self.esperar(self.miniaturas_listas)
        self.assertEqual(pf.calculadas, 2 * n)
        mini = pf.galeria.tarjetas[PRESET_PRINCIPAL].miniatura
        self.assertGreater(mini.height(), mini.width())
        # Deshacer el giro: de la caché, sin recalcular.
        v.deshacer()
        self.esperar(self.miniaturas_listas)
        self.assertEqual(pf.calculadas, 2 * n)
        mini = pf.galeria.tarjetas[PRESET_PRINCIPAL].miniatura
        self.assertGreater(mini.width(), mini.height())

        # Recortar también: la miniatura muestra la parte recortada.
        v._recorte = Recorte(0.0, 0.0, 0.4, 1.0)
        v._recalcular_fuentes()
        self.esperar(self.miniaturas_listas)
        self.assertEqual(pf.calculadas, 3 * n)
        mini = pf.galeria.tarjetas[PRESET_PRINCIPAL].miniatura
        self.assertGreater(mini.height(), mini.width())

        # Otra foto de la tira tiene las suyas; al volver a la primera salen de la caché.
        v.agregar_fotos([str(self.ruta2)])
        self.esperar(lambda: self.miniaturas_listas() and v._imagen.ruta.name == "otra.png")
        self.assertEqual(pf.calculadas, 4 * n)
        v.cambiar_a_foto(0)
        self.esperar(lambda: self.miniaturas_listas() and v._imagen.ruta.name == "escena.png")
        self.assertEqual(pf.calculadas, 4 * n)

        # En el modo editor no se calcula nada: recién al volver a Fácil.
        v.establecer_modo(EDITOR, guardar=False)
        v.girar(-1)
        self.esperar()
        self.pausa()
        self.assertEqual(pf.calculadas, 4 * n)
        v.establecer_modo(FACIL, guardar=False)
        self.esperar(self.miniaturas_listas)
        self.assertEqual(pf.calculadas, 5 * n)

    def test_el_modo_se_recuerda(self):
        from PySide6.QtGui import QKeySequence
        from celular_natural.ui.modo_facil import (
            CLAVE_MODO, EDITOR, FACIL, VARIABLE_CONFIG, configuracion, modo_guardado,
        )
        from celular_natural.ui.ventana import VentanaPrincipal
        v = self.v
        self.assertEqual(v.modo, FACIL)  # la primera vez arranca en Fácil
        self.assertEqual(modo_guardado(), FACIL)
        boton_editor = next(b for b in v.grupo_interfaz.buttons() if b.property("modo") == EDITOR)
        boton_editor.click()
        self.assertEqual(v.modo, EDITOR)
        self.assertEqual(configuracion().value(CLAVE_MODO), EDITOR)
        otra = VentanaPrincipal()
        try:
            self.assertEqual(otra.modo, EDITOR)
            self.assertTrue(next(b for b in otra.grupo_interfaz.buttons()
                                 if b.property("modo") == EDITOR).isChecked())
        finally:
            otra.close()
            otra.deleteLater()
        # Ctrl+E alterna y también se recuerda.
        accion = next(a for a in v.actions() if a.shortcut() == QKeySequence("Ctrl+E"))
        accion.trigger()
        self.assertEqual(v.modo, FACIL)
        self.assertEqual(configuracion().value(CLAVE_MODO), FACIL)
        accion.trigger()
        self.assertEqual(v.modo, EDITOR)
        # Un valor raro en las preferencias vuelve a Fácil.
        config = configuracion()
        config.setValue(CLAVE_MODO, "otra cosa")
        config.sync()
        self.assertEqual(modo_guardado(), FACIL)
        # Sin la variable de las pruebas se usan las preferencias de "NaturalShot PRO" (solo se mira).
        guardada = os.environ.pop(VARIABLE_CONFIG)
        try:
            real = configuracion()
            self.assertEqual(real.organizationName(), "NaturalShot")
            self.assertEqual(real.applicationName(), "NaturalShot PRO")
        finally:
            os.environ[VARIABLE_CONFIG] = guardada

    def test_en_facil_se_oculta_la_columna_derecha(self):
        from celular_natural.ui.modo_facil import EDITOR, FACIL
        v = self.v
        v.establecer_modo(FACIL, guardar=False)
        self.pausa(0.1)
        self.assertTrue(v.panel_derecho.isHidden())
        self.assertTrue(v.panel_facil.isVisible())
        self.assertTrue(v._lateral_editor.isHidden() and v._caja_historial.isHidden())
        # Barra superior: lo esencial sí; enderezar fino y voltear no.
        for b in (v.boton_abrir, v.boton_deshacer, v.boton_rehacer, v.boton_recortar, v.boton_video,
                  *v.grupo_modo.buttons(), *v.botones_geometria[:2]):
            self.assertFalse(b.isHidden())
        self.assertTrue(v.boton_enderezar.isHidden())
        self.assertTrue(all(b.isHidden() for b in v.botones_geometria[2:]))
        ancho_facil = v.vista.width()
        v.establecer_modo(EDITOR, guardar=False)
        self.pausa(0.1)
        self.assertFalse(v.panel_derecho.isHidden())
        self.assertTrue(v.panel_facil.isHidden())
        self.assertFalse(v.boton_enderezar.isHidden())
        self.assertFalse(any(b.isHidden() for b in v.botones_geometria))
        self.assertGreater(ancho_facil, v.vista.width() + 300)  # la vista previa gana la columna
        # _compactar_barra: lo oculto no cuenta, y en Fácil la barra se compacta menos o igual.
        for ancho in (1366, 1600, 1920):
            v.resize(ancho, 768)
            textos = {}
            for modo in (FACIL, EDITOR):
                v.establecer_modo(modo, guardar=False)
                self.pausa(0.05)
                textos[modo] = sum(bool(b.text()) for b in (*v.grupo_modo.buttons(), v.boton_recortar))
                disponible = ancho - 372 - (0 if modo == FACIL else 340) - 28
                if modo == FACIL:
                    self.assertLessEqual(v._ancho_barra(), disponible, ancho)
            self.assertGreaterEqual(textos[FACIL], textos[EDITOR])
        v.resize(1366, 768)
        v.establecer_modo(FACIL, guardar=False)
        self.pausa(0.05)
        self.assertTrue(all(b.text() for b in v.grupo_modo.buttons()), "en Fácil entran los nombres")
        # Los botones grandes del modo fácil usan las funciones de siempre.
        llamadas = []
        v.elegir_archivo = lambda: llamadas.append("abrir")
        v.procesar_varias = lambda: llamadas.append("varias")
        v.panel_facil.boton_abrir_chico.click()
        v.panel_facil.boton_lote.click()
        self.assertEqual(llamadas, ["abrir", "varias"])

    def test_exportar_desde_facil_igual_que_desde_editor(self):
        from PIL import Image
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QFileDialog
        from celular_natural.ui.modo_facil import EDITOR, FACIL
        v = self.v
        pf = v.panel_facil
        QTest.mouseClick(pf.galeria.tarjetas["Celular natural — marcado"], Qt.LeftButton)
        pf.slider_intensidad.setValue(70)
        self.esperar()
        carpeta = Path(self.carpeta.name)
        destinos: list[Path] = []
        original = QFileDialog.getSaveFileName
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(destinos[-1]), ""))
        try:
            for modo, formato in ((FACIL, "PNG"), (EDITOR, "PNG"), (FACIL, "JPEG"), (EDITOR, "JPEG")):
                v.establecer_modo(modo, guardar=False)
                if modo == FACIL:
                    pf.botones_formato[formato].click()
                    boton = pf.boton_exportar
                else:
                    next(b for b in v.grupo_formato.buttons() if b.property("formato") == formato).click()
                    boton = v.boton_exportar
                self.assertEqual(v._formato(), formato)
                destinos.append(carpeta / f"exportada_{modo}.{'png' if formato == 'PNG' else 'jpg'}")
                self.assertTrue(boton.isEnabled())
                boton.click()
                self.esperar(lambda: not v._exportando and destinos[-1].exists())
                # El selector del otro modo acompaña (es la misma elección).
                self.assertTrue(pf.botones_formato[formato].isChecked())
        finally:
            QFileDialog.getSaveFileName = original
        png_facil, png_editor, jpg_facil, jpg_editor = destinos
        self.assertEqual(png_facil.read_bytes(), png_editor.read_bytes())
        self.assertEqual(jpg_facil.read_bytes(), jpg_editor.read_bytes())
        exportada = np.asarray(Image.open(png_facil).convert("RGB"))
        self.assertTrue(np.array_equal(exportada, v._resultado_completo[1]), "se exporta lo que se ve")
        with Image.open(jpg_facil) as jpg:
            self.assertEqual(jpg.format, "JPEG")

    def test_sin_foto(self):
        from celular_natural.ui.ventana import VentanaPrincipal
        nueva = VentanaPrincipal()
        try:
            nueva.resize(1366, 768)
            nueva.show()
            self.pausa(0.2)
            pf = nueva.panel_facil
            self.assertEqual(nueva.modo, "facil")
            self.assertFalse(pf.paso_foto.cuerpo.isHidden())  # el botón grande "Abrir fotos"
            self.assertFalse(pf.boton_exportar.isEnabled())
            self.assertTrue(pf.boton_lote.isEnabled())
            self.assertTrue(pf.nota_estilos.isVisible())
            self.assertFalse(any(t.cargando or t.miniatura is not None for t in pf.galeria.tarjetas.values()))
            # Elegir un estilo antes de abrir: la foto lo usa al abrirse.
            pf.elegir_estilo("Noche urbana")
            nueva.abrir_archivo(str(self.ruta))
            self.esperar(lambda: nueva._imagen is not None and pf.miniaturas_listas())
            self.assertEqual(nueva.panel_ajustes.estado()["preset"], "Noche urbana")
            self.assertTrue(pf.paso_foto.cuerpo.isHidden())
            self.assertTrue(pf.boton_exportar.isEnabled())
        finally:
            nueva.close()
            nueva.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
