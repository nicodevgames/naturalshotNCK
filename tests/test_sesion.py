"""Pruebas de la sesión: las fotos de la tira y sus ediciones se recuperan al volver a abrir.

* Guardar y leer una sesión de 3 fotos con ediciones variadas (capas con zona,
  recorte, geometría, montaje, borrado y fondo): lo leído es ``==`` a lo guardado.
* Una foto que ya no existe se saltea, con un aviso discreto.
* Un archivo dañado, de una versión incompatible o con clases que cambiaron: se
  arranca limpio y queda el ``.bak``.
* La escritura es atómica: si falla a mitad de camino, queda la sesión anterior.
* "Quitar todas las fotos" vacía la tira y la sesión guardada.
* El guardado automático, 2 s después de un cambio, sin cerrar la ventana.
* De punta a punta con la ventana real (sin pantalla): abrir 3 fotos, editarlas,
  cerrar y abrir una ventana nueva: las mismas fotos, la misma foto actual, las
  mismas ediciones y la misma vista procesada.
* Con 20 fotos, recuperar la sesión no traba la interfaz.

Usan un APPDATA y un .ini temporales: no tocan la sesión ni las preferencias del usuario.
"""

from __future__ import annotations

import os
import pickle
import sys
import tempfile
import time
import unittest
import zlib
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
if "NATURALSHOT_CONFIG" not in os.environ:  # como en test_modo_facil: nunca el registro del usuario
    import atexit
    import shutil
    _CARPETA_CONFIG = tempfile.mkdtemp(prefix="naturalshot_config_")
    atexit.register(shutil.rmtree, _CARPETA_CONFIG, True)
    os.environ["NATURALSHOT_CONFIG"] = os.path.join(_CARPETA_CONFIG, "preferencias.ini")

from celular_natural import sesion  # noqa: E402
from celular_natural.motor import (  # noqa: E402
    PRESET_PRINCIPAL, PRESETS, Geometria, Recorte, Zona, ZonaBorrado,
)
from celular_natural.motor.montaje import CapaFoto  # noqa: E402


def escena(w=480, h=360, semilla=0):
    """Cielo arriba, pasto con textura abajo y un cuadrado rojo (cambia con la semilla)."""
    rng = np.random.default_rng(semilla)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cielo = np.dstack([90 + 60 * yy / h, 150 + 50 * yy / h, 230 + 0 * yy])
    grano = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), 1.5)
    pasto = np.dstack([60 + 0 * xx, 120 + 0 * xx, 50 + 0 * xx]) + 30 * grano[..., None]
    img = np.where((yy > h * 0.5)[..., None], pasto, cielo)
    x0 = int(w * (0.25 + 0.05 * (semilla % 3)))
    img[int(h * 0.6):int(h * 0.8), x0:x0 + int(w * 0.1)] = (210, 30, 30)
    img += rng.normal(0, 2, (h, w, 1))
    return np.clip(img + 0.5, 0, 255).astype(np.uint8)


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def estados_variados(rutas: list[str]) -> sesion.SesionGuardada:
    """Tres fotos: una con todo (y su historial), otra con lo justo y otra sin abrir."""
    mascara = np.zeros((300, 400), np.float32)
    cv2.circle(mascara, (150, 100), 60, 1.0, -1)
    cielo = Zona.desde_mascara(cv2.GaussianBlur(mascara, (0, 0), 3), "cielo")  # bytes y números de NumPy
    pincel = Zona.desde_trazos([(((0.2, 0.2), (0.3, 0.25)), 0.03, 80, False),
                                (((0.25, 0.22),), 0.01, 100, True)], pluma=10, aspecto=4 / 3)
    lazo = Zona.desde_puntos("poligono", [(0.3, 0.5), (0.5, 0.45), (0.55, 0.8), (0.28, 0.85)], pluma=4)
    base = {"preset": PRESET_PRINCIPAL, "ajustes": PRESETS[PRESET_PRINCIPAL], "capas": [],
            "recorte": None, "montaje": (), "fondo": (None, True, "transparente", 50, 35, False),
            "geometria": Geometria(), "borrado": ()}
    paso1 = dict(base, capas=[("Noche urbana", 60, Zona("rect", 0.1, 0.1, 0.5, 0.5, pluma=20))])
    paso2 = dict(paso1, capas=paso1["capas"] + [("Estilo iPhone 15 Pro", 40, cielo), ("Noche urbana", 30, pincel)],
                 recorte=Recorte(0.05, 0.1, 0.9, 0.95), geometria=Geometria(1, False, True, 2.5))
    completo = dict(paso2,
                    montaje=(CapaFoto(rutas[1], Zona("elipse", 0.2, 0.2, 0.6, 0.7, pluma=15), 80, True, False),),
                    borrado=(ZonaBorrado(Zona("rect", 0.6, 0.6, 0.7, 0.7)),
                             ZonaBorrado(lazo, "clonar", 0.12, -0.05, False)),
                    fondo=(lazo, False, "desenfocado", 70, 40, True))
    historial = [("Inicio", base), ("Capa agregada: Noche urbana", paso1), ("Varios cambios", paso2),
                 ("Montaje, borrados y fondo", completo)]
    simple = dict(base, preset="Noche urbana", ajustes=PRESETS["Noche urbana"],
                  capas=[("Estilo iPhone 15 Pro", 55, None)])
    return sesion.SesionGuardada([
        sesion.FotoGuardada(rutas[0], completo, historial, 2),
        sesion.FotoGuardada(rutas[1], simple, [("Inicio", simple)], 0),
        sesion.FotoGuardada(rutas[2]),
    ], actual=1)


class _ConAppdata(unittest.TestCase):
    """APPDATA temporal para toda la clase (la sesión va en %APPDATA%\\NaturalShot PRO\\sesion)."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        cls.carpeta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.base = Path(cls.carpeta.name)
        cls._appdata = os.environ.get("APPDATA")
        os.environ["APPDATA"] = str(cls.base / "appdata")

    @classmethod
    def tearDownClass(cls):
        if cls._appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = cls._appdata
        cls.carpeta.cleanup()

    def setUp(self):
        sesion.borrar()
        for extra in (sesion.archivo_respaldo(), sesion.carpeta_sesion() / sesion.ARCHIVO_LOG):
            if extra.exists():
                extra.unlink()

    def fotos(self, cantidad=3, lado=480, prefijo="foto", extension=".png"):
        from PIL import Image
        rutas = []
        for i in range(cantidad):
            r = self.base / f"{prefijo}_{i}{extension}"
            if not r.exists():
                Image.fromarray(escena(lado, lado * 3 // 4, i)).save(r, quality=92)
            rutas.append(str(r))
        return rutas


# ====================================================================== archivo
class PruebasArchivo(_ConAppdata):
    def test_guardar_y_restaurar_tres_fotos(self):
        original = estados_variados(self.fotos())
        sesion.guardar(original)
        ruta = sesion.archivo_sesion()
        self.assertEqual(ruta.parent, self.base / "appdata" / "NaturalShot PRO" / "sesion")
        self.assertLess(ruta.stat().st_size, 60_000, "solo rutas y ediciones, nunca las imágenes")
        leida, problema = sesion.cargar()
        self.assertIsNone(problema)
        self.assertEqual(leida.actual, 1)
        self.assertEqual(len(leida.fotos), 3)
        for a, b in zip(original.fotos, leida.fotos):
            self.assertEqual(a.ruta, b.ruta)
            self.assertEqual(a.estado, b.estado)
            self.assertEqual(a.historial, b.historial)
            self.assertEqual(a.pos, b.pos)
        self.assertEqual(original.fotos, leida.fotos)
        # Los tipos se conservan (tuplas siguen siendo tuplas; las zonas, zonas).
        estado = leida.fotos[0].estado
        self.assertIsInstance(estado["montaje"], tuple)
        self.assertIsInstance(estado["capas"], list)
        self.assertIsInstance(estado["capas"][1][2], Zona)
        self.assertEqual(estado["capas"][1][2].datos, original.fotos[0].estado["capas"][1][2].datos)
        # Lo que se repite entre pasos del historial se guarda una sola vez y se lee compartido.
        self.assertIs(leida.fotos[0].historial[2][1]["capas"][1][2], estado["capas"][1][2])

    def test_sin_fotos_no_queda_archivo(self):
        sesion.guardar(estados_variados(self.fotos()))
        sesion.guardar(sesion.SesionGuardada([], -1))
        self.assertFalse(sesion.archivo_sesion().exists())
        self.assertEqual(sesion.cargar(), (None, None))

    def _escribir_crudo(self, datos) -> None:
        contenido = pickle.dumps(datos, protocol=pickle.HIGHEST_PROTOCOL)
        sesion.escribir_atomico(sesion.archivo_sesion(),
                                sesion.MARCA + sesion._CABECERA.pack(zlib.crc32(contenido)) + contenido)

    def _comprobar_arranque_limpio(self, crudo: bytes, texto: str) -> None:
        leida, problema = sesion.cargar()
        self.assertIsNone(leida)
        self.assertIn(texto, problema)
        self.assertFalse(sesion.archivo_sesion().exists(), "se arranca limpio")
        self.assertEqual(sesion.archivo_respaldo().read_bytes(), crudo, "el archivo malo queda como .bak")
        self.assertIn("sesion.bak", (sesion.carpeta_sesion() / sesion.ARCHIVO_LOG).read_text(encoding="utf-8"))
        # Y la próxima vez se puede guardar normalmente.
        sesion.guardar(estados_variados(self.fotos()))
        self.assertIsNotNone(sesion.cargar()[0])

    def test_archivo_danado(self):
        ruta = sesion.archivo_sesion()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(b"esto no es una sesion")
        self._comprobar_arranque_limpio(b"esto no es una sesion", "no es una sesión")

    def test_archivo_cortado_a_la_mitad(self):
        sesion.guardar(estados_variados(self.fotos()))
        crudo = sesion.archivo_sesion().read_bytes()[:-200]
        sesion.archivo_sesion().write_bytes(crudo)
        self._comprobar_arranque_limpio(crudo, "dañado")

    def test_version_incompatible(self):
        self._escribir_crudo({"version": 999, "actual": 0, "fotos": [{"ruta": "x.png", "estado": None}]})
        crudo = sesion.archivo_sesion().read_bytes()
        self._comprobar_arranque_limpio(crudo, "incompatible")

    def test_clase_que_cambio(self):
        """Una Zona guardada por una versión que no tenía un campo obligatorio de hoy."""
        zona = Zona("rect", 0.1, 0.1, 0.4, 0.4)
        del zona.__dict__["x1"]
        estado = {"preset": PRESET_PRINCIPAL, "ajustes": PRESETS[PRESET_PRINCIPAL], "capas": [("Noche urbana", 50, zona)]}
        self._escribir_crudo({"version": sesion.VERSION_FORMATO, "actual": 0,
                              "fotos": [{"ruta": "x.png", "estado": estado, "historial": None, "pos": 0}]})
        crudo = sesion.archivo_sesion().read_bytes()
        self._comprobar_arranque_limpio(crudo, "le falta el campo x1")

    def test_campo_nuevo_con_valor_inicial(self):
        """Al revés: un campo que hoy existe y el archivo no tiene, pero con valor inicial, se completa."""
        zona = Zona("rect", 0.1, 0.1, 0.4, 0.4, pluma=12)
        del zona.__dict__["origen"]
        estado = {"preset": PRESET_PRINCIPAL, "ajustes": PRESETS[PRESET_PRINCIPAL], "capas": [("Noche urbana", 50, zona)]}
        self._escribir_crudo({"version": sesion.VERSION_FORMATO, "actual": 0,
                              "fotos": [{"ruta": "x.png", "estado": estado, "historial": None, "pos": 0}]})
        leida, problema = sesion.cargar()
        self.assertIsNone(problema)
        self.assertEqual(leida.fotos[0].estado["capas"][0][2], Zona("rect", 0.1, 0.1, 0.4, 0.4, pluma=12))

    def test_clase_no_permitida(self):
        """El archivo no puede pedir otras clases (por ejemplo, ejecutar algo al leerlo)."""
        self._escribir_crudo({"version": sesion.VERSION_FORMATO, "actual": 0,
                              "fotos": [{"ruta": "x.png", "estado": None, "extra": os.getcwd}]})
        crudo = sesion.archivo_sesion().read_bytes()
        self._comprobar_arranque_limpio(crudo, "clase no permitida")

    def test_escritura_atomica(self):
        original = estados_variados(self.fotos())
        sesion.guardar(original)
        antes = sesion.archivo_sesion().read_bytes()
        reemplazos = []
        real = os.replace

        def falla(origen, destino):
            reemplazos.append((Path(origen), Path(destino)))
            raise OSError("corte de luz simulado")

        otra = sesion.SesionGuardada([sesion.FotoGuardada(self.fotos()[2])], 0)
        sesion.os.replace = falla
        try:
            with self.assertRaises(OSError):
                sesion.guardar(otra)
        finally:
            sesion.os.replace = real
        # El temporal estaba en la misma carpeta (os.replace es atómico ahí) y no quedó tirado.
        self.assertEqual(reemplazos[0][0].parent, reemplazos[0][1].parent)
        self.assertEqual(reemplazos[0][1], sesion.archivo_sesion())
        self.assertEqual(list(sesion.carpeta_sesion().glob("*.tmp")), [])
        self.assertEqual(sesion.archivo_sesion().read_bytes(), antes, "queda entera la sesión anterior")
        self.assertEqual(sesion.cargar()[0].fotos, original.fotos)
        # Un temporal viejo que dejó un corte de luz se limpia al leer.
        viejo = sesion.carpeta_sesion() / (sesion.ARCHIVO_SESION + ".abc.tmp")
        viejo.write_bytes(b"a medias")
        hace_rato = time.time() - 2 * sesion.TEMPORALES_VIEJOS
        os.utime(viejo, (hace_rato, hace_rato))
        sesion.cargar()
        self.assertFalse(viejo.exists())


# ====================================================================== ventana
class _ConVentana(_ConAppdata):
    def setUp(self):
        super().setUp()
        self.ventanas = []

    def tearDown(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        for v in self.ventanas:
            v.close()
            v.deleteLater()
        self.app.processEvents()
        # deleteLater() sin un bucle de eventos corriendo no borra nada: se completa el borrado acá.
        # Si no, cada ventana cerrada queda viva hasta el final de la suite (con sus miles de widgets).
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def ventana(self, activar=True):
        from celular_natural.ui.ventana import VentanaPrincipal
        v = VentanaPrincipal()
        v.resize(1366, 768)
        self.ventanas.append(v)
        if activar:
            v.activar_sesion()
            self.esperar(lambda: v.sesion_restaurada)
        return v

    def cerrar(self, v):
        v.close()
        self.ventanas.remove(v)
        v.deleteLater()
        self.app.processEvents()

    @staticmethod
    def quieto(v) -> bool:
        return (v._imagen is not None and not v._fuentes_pendientes and v._deteccion is None
                and v._generacion_completa_mostrada == v._generacion and not v._exportando)

    def abierta(self, v, indice) -> bool:
        """La foto ``indice`` ya se ve (mientras carga, los paneles todavía son de la anterior)."""
        return v._actual == indice and v._estado_vivo() and self.quieto(v)

    def esperar(self, condicion, segundos=60.0):
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

    def registrar(self, v):
        v._timer_historial.stop()
        v._registrar_historial()


class PruebasVentana(_ConVentana):
    def test_foto_que_ya_no_existe(self):
        rutas = self.fotos(4, prefijo="faltan")
        v = self.ventana()
        v.agregar_fotos(rutas)
        self.esperar(lambda: self.quieto(v))
        v.cambiar_a_foto(2)
        self.esperar(lambda: self.abierta(v, 2))
        self.cerrar(v)
        Path(rutas[2]).unlink()  # la que estaba abierta
        Path(rutas[0]).unlink()
        v = self.ventana()
        self.esperar(lambda: self.quieto(v))
        self.assertEqual([f.ruta for f in v._fotos], [rutas[1], rutas[3]])
        self.assertEqual(v._fotos[v._actual].ruta, rutas[3], "la más cercana a la que estaba abierta")
        self.assertFalse(v.aviso.isHidden())
        self.assertEqual(v.aviso.texto.text(), "2 fotos de la sesión anterior ya no están en su carpeta.")
        self.assertIn("faltan_2.png", v.aviso.toolTip())
        # La próxima vez ya no avisa: la sesión se volvió a guardar sin esas fotos.
        self.esperar(lambda: not v._timer_sesion.isActive())
        v._pool_sesion.waitForDone()
        self.assertEqual([f.ruta for f in sesion.cargar()[0].fotos], [rutas[1], rutas[3]])

    def test_archivo_danado_en_la_ventana(self):
        ruta = sesion.archivo_sesion()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(b"\x00\x01basura")
        v = self.ventana()
        self.assertEqual(v._fotos, [])
        self.assertIsNone(v._imagen)
        self.assertTrue(sesion.archivo_respaldo().exists())
        self.assertIn("No se pudo recuperar la sesión anterior", v.aviso.texto.text())
        # Y desde ahí guarda normalmente.
        v.agregar_fotos(self.fotos(1))
        self.esperar(lambda: self.quieto(v))
        v.guardar_sesion(esperar=True)
        self.assertEqual(len(sesion.cargar()[0].fotos), 1)

    def test_quitar_todas_vacia_la_sesion(self):
        from PySide6.QtWidgets import QMessageBox
        rutas = self.fotos()
        v = self.ventana()
        v.agregar_fotos(rutas)
        self.esperar(lambda: self.quieto(v))
        v.panel_ajustes.agregar_capa("Noche urbana", 50, zona=Zona("rect", 0.1, 0.1, 0.4, 0.4))
        v.girar(1)
        self.esperar(lambda: self.quieto(v))
        v.guardar_sesion(esperar=True)
        self.assertTrue(sesion.archivo_sesion().exists())
        # Con "No" no pasa nada.
        original = QMessageBox.question
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
        try:
            self.assertFalse(v.quitar_todas_las_fotos())
        finally:
            QMessageBox.question = original
        self.assertEqual(len(v._fotos), 3)
        # Con "Sí": la tira queda vacía, como recién abierta, y la sesión guardada también.
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
        try:
            self.assertTrue(v.quitar_todas_las_fotos())
        finally:
            QMessageBox.question = original
        self.assertEqual(v._fotos, [])
        self.assertIsNone(v._imagen)
        self.assertTrue(v.tira.isHidden())
        self.assertFalse(v.vista.tiene_imagen())
        self.assertEqual(len(v._historial), 1)
        self.assertEqual(v._geometria, Geometria())
        self.assertEqual([z for z in v.panel_ajustes.zonas() if z is not None], [])
        self.assertFalse(sesion.archivo_sesion().exists())
        self.app.processEvents()
        self.cerrar(v)  # cerrar sin fotos tampoco deja sesión
        self.assertFalse(sesion.archivo_sesion().exists())
        v = self.ventana()
        self.assertEqual(v._fotos, [])
        # Se puede seguir usando: abrir fotos de nuevo.
        v.agregar_fotos(rutas[:1])
        self.esperar(lambda: self.quieto(v))
        self.assertFalse(v.tira.isHidden())

    def test_guardado_automatico_despues_de_un_cambio(self):
        rutas = self.fotos()
        v = self.ventana()
        v.agregar_fotos(rutas)
        self.esperar(lambda: self.quieto(v) and not v._timer_sesion.isActive())
        v._pool_sesion.waitForDone()
        self.assertEqual(len(sesion.cargar()[0].fotos), 3, "agregar fotos ya guarda la sesión")
        v.panel_ajustes.agregar_capa("Noche urbana", 45, zona=Zona("elipse", 0.2, 0.2, 0.6, 0.6))
        inicio = time.monotonic()
        self.registrar(v)  # el cambio pasa al historial
        self.assertTrue(v._timer_sesion.isActive())

        def guardado():
            leida = sesion.cargar()[0]
            return leida is not None and len(leida.fotos[leida.actual].estado["capas"]) == 1

        self.assertFalse(guardado(), "todavía no: espera 2 s")
        self.esperar(guardado, 10)
        self.assertGreater(time.monotonic() - inicio, 1.8)
        leida = sesion.cargar()[0]
        self.assertEqual(leida.fotos[leida.actual].estado, v._estado_completo())
        self.assertEqual(leida.fotos[leida.actual].historial, v._historial)
        # Cambiar de foto también queda guardado, sin cerrar.
        v.cambiar_a_foto(2)
        self.esperar(lambda: self.abierta(v, 2) and not v._timer_sesion.isActive())
        v._pool_sesion.waitForDone()
        self.assertEqual(sesion.cargar()[0].actual, 2)

    def test_sin_activar_no_toca_nada(self):
        """Las ventanas que no activan la sesión (las demás pruebas) no leen ni escriben el archivo."""
        sesion.guardar(estados_variados(self.fotos()))
        antes = sesion.archivo_sesion().read_bytes()
        v = self.ventana(activar=False)
        v.agregar_fotos(self.fotos()[:1])
        self.esperar(lambda: self.quieto(v))
        self.cerrar(v)
        self.assertEqual(sesion.archivo_sesion().read_bytes(), antes)


class PruebasPuntaAPunta(_ConVentana):
    def test_cerrar_y_volver_a_abrir(self):
        from celular_natural.ui.fondo import DESENFOCADO
        rutas = self.fotos(3, prefijo="punta")
        v = self.ventana()
        v.agregar_fotos(rutas)
        self.esperar(lambda: self.quieto(v))
        # Foto 1: preset, una capa con zona y otra con máscara automática, recorte y giro.
        v.panel_ajustes.combo_preset.setCurrentText("Noche urbana")
        v.panel_ajustes.agregar_capa("Estilo iPhone 15 Pro", 60, zona=Zona("elipse", 0.15, 0.1, 0.65, 0.55, pluma=25))
        self.esperar(lambda: self.quieto(v))
        self.registrar(v)
        m = np.zeros((360, 480), np.float32)
        m[:150] = 1.0
        v.panel_ajustes.agregar_capa("Noche urbana", 35, zona=Zona.desde_mascara(cv2.GaussianBlur(m, (0, 0), 4), "cielo"))
        self.registrar(v)
        v._recorte = Recorte(0.05, 0.08, 0.92, 0.9)
        v._recalcular_fuentes()
        self.esperar(lambda: self.quieto(v))
        self.registrar(v)
        v.girar(1)
        self.esperar(lambda: self.quieto(v))
        vista_1 = v._resultado_completo[1].copy()
        # Foto 2: montaje con la foto 1, un objeto borrado y deshacer/rehacer.
        v.cambiar_a_foto(1)
        self.esperar(lambda: self.abierta(v, 1))
        v.panel_montaje.agregar(rutas[0], None, CapaFoto(rutas[0], Zona("rect", 0.0, 0.0, 0.5, 1.0, pluma=30)))
        self.esperar(lambda: self.quieto(v) and not v._timer_montaje.isActive())
        self.registrar(v)
        v.panel_borrar.agregar(ZonaBorrado(Zona("rect", 0.24, 0.58, 0.4, 0.82, pluma=8)))
        self.esperar(lambda: self.quieto(v))
        self.registrar(v)
        v.deshacer()
        self.esperar(lambda: self.quieto(v))
        v.rehacer()
        self.esperar(lambda: self.quieto(v))
        vista_2 = v._resultado_completo[1].copy()
        # Foto 3: fondo desenfocado con un lazo y volteo.
        v.cambiar_a_foto(2)
        self.esperar(lambda: self.abierta(v, 2))
        v.panel_fondo.establecer_zona(Zona.desde_puntos("poligono", [(0.3, 0.5), (0.5, 0.5), (0.5, 0.9), (0.3, 0.9)], 5))
        v.panel_fondo.botones_modo[DESENFOCADO].click()
        self.esperar(lambda: self.quieto(v))
        self.registrar(v)
        v.voltear(True)
        self.esperar(lambda: self.quieto(v))
        self.assertIsNotNone(v.panel_fondo.desenfoque())
        vista_3 = v._resultado_completo[1].copy()
        # Se queda abierta la foto 2, con un cambio que todavía no pasó al historial.
        v.cambiar_a_foto(1)
        self.esperar(lambda: self.abierta(v, 1))
        v.panel_ajustes.intensidad.slider.setValue(70)
        self.esperar(lambda: self.quieto(v))
        v._timer_historial.start()  # el paso todavía no se registró (al cerrar se registra)
        self.assertNotEqual(v._historial[v._pos_historial][1], v._estado_completo())
        v._guardar_foto_actual()  # para comparar: lo mismo que hace la ventana al cerrar
        esperado = [(f.ruta, f.estado, list(f.historial), f.pos) for f in v._fotos]
        vista_2b = v._resultado_completo[1].copy()
        self.cerrar(v)

        # "Se vuelve a abrir la app": ventana nueva con el mismo APPDATA.
        v = self.ventana()
        self.esperar(lambda: self.quieto(v))
        self.assertEqual([f.ruta for f in v._fotos], rutas)
        self.assertEqual(v._actual, 1)
        self.assertEqual(v._estado_completo(), esperado[1][1])
        self.assertEqual(v._historial, esperado[1][2])
        self.assertEqual(v._pos_historial, esperado[1][3])
        self.assertEqual(v.panel_ajustes.ajustes().intensidad, 70)
        self.assertEqual(len(v.panel_montaje.estado()), 1)
        self.assertEqual(len(v.panel_borrar.estado()), 1)
        self.assertTrue(np.array_equal(v._resultado_completo[1], vista_2b), "la vista procesada coincide")
        for i in (0, 2):
            f = v._fotos[i]
            self.assertEqual((f.ruta, f.estado, f.historial, f.pos), esperado[i])
        # El historial sigue andando: deshacer vuelve a la foto 2 de antes de la intensidad.
        v.deshacer()
        self.esperar(lambda: self.quieto(v))
        self.assertTrue(np.array_equal(v._resultado_completo[1], vista_2))
        # Las otras fotos también: misma edición y misma vista.
        v.cambiar_a_foto(0)
        self.esperar(lambda: self.abierta(v, 0))
        self.assertEqual(v._estado_completo(), esperado[0][1])
        self.assertEqual(v._geometria, Geometria(1))
        self.assertTrue(np.array_equal(v._resultado_completo[1], vista_1))
        v.cambiar_a_foto(2)
        self.esperar(lambda: self.abierta(v, 2))
        self.assertEqual(v._estado_completo(), esperado[2][1])
        self.assertTrue(np.array_equal(v._resultado_completo[1], vista_3))


class PruebasRendimiento(_ConVentana):
    def test_veinte_fotos_sin_trabar_la_interfaz(self):
        from PySide6.QtCore import QTimer
        rutas = self.fotos(20, lado=1600, prefijo="muchas", extension=".jpg")
        historial = [("Inicio", {"preset": PRESET_PRINCIPAL, "ajustes": PRESETS[PRESET_PRINCIPAL], "capas": []})]
        for k in range(1, 60):  # historiales largos, con zonas
            historial.append((f"Paso {k}", dict(historial[-1][1], capas=[("Noche urbana", k, Zona("rect", 0.1, 0.1,
                                                                                                0.2 + k / 100, 0.5))])))
        guardada = sesion.SesionGuardada(
            [sesion.FotoGuardada(r, historial[-1][1], list(historial), len(historial) - 1) for r in rutas], 7)
        sesion.guardar(guardada)
        latidos = []
        reloj = QTimer()
        reloj.setInterval(10)
        reloj.timeout.connect(lambda: latidos.append(time.perf_counter()))
        reloj.start()
        inicio = time.perf_counter()
        v = self.ventana(activar=False)
        construida = time.perf_counter()
        v.activar_sesion()
        self.esperar(lambda: v.sesion_restaurada and self.quieto(v))
        self.esperar(lambda: all(f.miniatura is not None for f in v._fotos), 120)
        reloj.stop()
        self.assertEqual(len(v._fotos), 20)
        self.assertEqual(v._actual, 7)
        self.assertEqual(len(v._historial), 60)
        huecos = [b - a for a, b in zip(latidos, latidos[1:]) if a >= construida]
        maximo = max(huecos)
        print(f"\n  20 fotos de 1600 px: sesión recuperada y 20 miniaturas en {time.perf_counter() - construida:.2f} s; "
              f"hueco máximo de la interfaz {maximo * 1000:.0f} ms (construir la ventana {construida - inicio:.2f} s)")
        self.assertLess(maximo, 0.4, "la interfaz no se traba mientras se recupera")


if __name__ == "__main__":
    unittest.main()
