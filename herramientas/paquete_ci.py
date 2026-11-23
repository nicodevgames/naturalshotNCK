"""Arma el paquete de Windows de una compilación automática (GitHub Actions) y su ``version.json``.

    python herramientas/paquete_ci.py dist/NaturalShot NaturalShot-PRO-windows.zip

El zip es el de siempre (``NaturalShot PRO\\`` con el .exe y _internal, más el LEEME): sirve para
bajarlo a mano y es el que baja la app para actualizarse sola. ``version.json`` queda en la carpeta
actual, con la versión de ``celular_natural/__init__.py`` (la compilación ya la subió) y como novedad
la primera línea del mensaje del commit (variable MENSAJE).
"""

from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "herramientas"))

from publicar import armar_zip, sha256_de, version_actual  # noqa: E402

from celular_natural.actualizador import NOMBRE_MANIFIESTO  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    app, destino = Path(argv[0]), Path(argv[1])
    if not (app / "NaturalShot.exe").is_file() or not (app / "_internal").is_dir():
        print(f"No está la app compilada en {app}.")
        return 1
    armar_zip(app, destino)
    nota = (os.environ.get("MENSAJE") or "").strip().splitlines()
    manifiesto = {"version": version_actual(), "fecha": datetime.date.today().isoformat(),
                  "notas": [nota[0] if nota else "Mejoras y arreglos"], "zip": destino.name,
                  "sha256": sha256_de(destino), "tamano": destino.stat().st_size, "minima": "1.0.0"}
    Path(NOMBRE_MANIFIESTO).write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{destino} ({manifiesto['tamano']} bytes) y {NOMBRE_MANIFIESTO} de la versión {manifiesto['version']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
