"""Los textos propios de Qt (botones de los diálogos) salen en español."""

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import main  # noqa: E402

app = QApplication.instance() or QApplication([])


class PruebasTraduccion(unittest.TestCase):
    def test_botones_de_si_o_no_en_espanol(self):
        self.assertTrue(main._traducir_qt(app))
        caja = QMessageBox(QMessageBox.Question, "Pregunta", "¿Seguro?", QMessageBox.Yes | QMessageBox.No)
        try:
            textos = {caja.button(b).text().replace("&", "") for b in (QMessageBox.Yes, QMessageBox.No)}
        finally:
            caja.deleteLater()
        self.assertEqual(textos, {"Sí", "No"})


if __name__ == "__main__":
    unittest.main()
