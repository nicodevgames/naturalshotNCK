"""Pruebas de la ventana de tutorial (se muestra al abrir hasta tildar "No volver a mostrar")."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Preferencias en un .ini temporal: no se toca la configuración real del usuario.
_CARPETA = tempfile.mkdtemp()
os.environ["NATURALSHOT_CONFIG"] = str(Path(_CARPETA) / "prueba_tutorial.ini")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from celular_natural.ui import tutorial  # noqa: E402
from celular_natural.ui.modo_facil import configuracion  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv)


class PruebasTutorial(unittest.TestCase):
    def setUp(self):
        os.environ["NATURALSHOT_CONFIG"] = str(Path(_CARPETA) / "prueba_tutorial.ini")
        configuracion().remove(tutorial.CLAVE_NO_MOSTRAR)

    def test_el_pdf_viaja_con_la_app(self):
        self.assertTrue(tutorial.ruta_tutorial().exists(), "falta assets/tutorial.pdf")

    def test_el_paquete_no_lleva_la_guia_personal(self):
        """NS-106.4: la guía con la foto personal (Tutorial/... - Guía de uso.pdf) nunca va en assets/."""
        import hashlib
        raiz = Path(__file__).resolve().parent.parent
        huella = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()  # noqa: E731
        personales = {huella(p) for p in (raiz / "Tutorial").glob("*Guía de uso.pdf")}
        for empaquetado in (raiz / "assets").glob("*.pdf"):
            self.assertNotIn(huella(empaquetado), personales,
                             f"{empaquetado.name} es la guía personal: copiá encima la tutorial_compartible")

    def test_se_muestra_hasta_tildar_no_volver_a_mostrar(self):
        self.assertTrue(tutorial.debe_mostrarse_al_iniciar())
        d = tutorial.DialogoTutorial()
        d.accept()  # cerrar sin tildar: vuelve a salir la próxima vez
        self.assertTrue(tutorial.debe_mostrarse_al_iniciar())
        d = tutorial.DialogoTutorial()
        d.check_no_mostrar.setChecked(True)
        d.accept()
        self.assertFalse(tutorial.debe_mostrarse_al_iniciar())
        # Al reabrirlo a mano, la casilla aparece tildada y se puede destildar.
        d = tutorial.DialogoTutorial()
        self.assertTrue(d.check_no_mostrar.isChecked())
        d.check_no_mostrar.setChecked(False)
        d.reject()
        self.assertTrue(tutorial.debe_mostrarse_al_iniciar())

    def test_carga_la_guia_y_navega(self):
        d = tutorial.DialogoTutorial()
        total = d.documento.pageCount()
        self.assertGreaterEqual(total, 10)
        self.assertTrue(d.etiqueta_pagina.text().startswith("Página 1 de"))
        self.assertFalse(d.boton_anterior.isEnabled())
        d._ir(total - 1)
        _APP.processEvents()
        self.assertEqual(d._pagina(), total - 1)
        self.assertFalse(d.boton_siguiente.isEnabled())
        d.reject()


if __name__ == "__main__":
    unittest.main()
