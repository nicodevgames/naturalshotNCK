"""Audita los metadatos de lo que exportó NaturalShot contra la política (NS-104.3).

Uso:
    .venv\\Scripts\\python herramientas\\auditar_metadatos.py CARPETA_O_ARCHIVO [...] [--reporte reporte.csv] [--completo]

Revisa fotos (JPEG, PNG, WebP, TIFF) con ``celular_natural/motor/metadatos.py`` y videos y audios
(MP4, MOV, M4A, MP3, WAV) con PyAV:

* fotos: sin GPS, seriales, dueño, nombre de la PC ni rutas; orientación 1; dimensiones EXIF
  iguales a las reales; sin miniatura del original;
* video y audio: sin ubicación (``location``, ``©xyz``, ``com.apple.quicktime.location.*``) y
  ``creation_time`` nunca en el futuro.

``--completo`` agrega al reporte el volcado entero de ExifTool (``-a -G1 -s``) y de ffprobe
(``-show_format -show_streams``) si están instalados, para revisar a mano.

Sale con código 1 si algún archivo viola la política, 0 si todos cumplen.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from celular_natural.motor import metadatos  # noqa: E402

FOTOS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
MEDIOS = {".mp4", ".mov", ".m4v", ".m4a", ".mp3", ".wav", ".aac"}
CLAVES_UBICACION = ("location", "xyz", "gps")


def auditar_medio(ruta: Path) -> list[str]:
    import av

    problemas: list[str] = []
    ahora = datetime.now(timezone.utc)
    with av.open(str(ruta)) as c:
        bloques = [("contenedor", dict(c.metadata))]
        bloques += [(f"pista {s.index} ({s.type})", dict(s.metadata)) for s in c.streams]
        for donde, meta in bloques:
            for clave, valor in meta.items():
                if any(k in clave.lower() for k in CLAVES_UBICACION):
                    problemas.append(f"{donde}: ubicación en {clave}={valor}")
                if clave == "creation_time":
                    try:
                        cuando = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
                    except ValueError:
                        problemas.append(f"{donde}: creation_time ilegible ({valor})")
                        continue
                    if cuando.tzinfo is None:
                        cuando = cuando.replace(tzinfo=timezone.utc)
                    if cuando > ahora:
                        problemas.append(f"{donde}: creation_time en el futuro ({valor})")
    return problemas


def volcado(ruta: Path) -> str:
    partes = []
    if shutil.which("exiftool"):
        r = subprocess.run(["exiftool", "-a", "-G1", "-s", str(ruta)], capture_output=True, text=True, timeout=60)
        partes.append(r.stdout.strip())
    if ruta.suffix.lower() in MEDIOS and shutil.which("ffprobe"):
        r = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", str(ruta)],
                           capture_output=True, text=True, timeout=60)
        partes.append(r.stdout.strip())
    return "\n".join(p for p in partes if p) or "(sin ExifTool ni ffprobe instalados)"


def archivos(rutas: list[str]) -> list[Path]:
    salida: list[Path] = []
    for r in rutas:
        p = Path(r)
        candidatos = sorted(p.rglob("*")) if p.is_dir() else [p]
        salida += [x for x in candidatos if x.is_file() and x.suffix.lower() in FOTOS | MEDIOS]
    return salida


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audita los metadatos de lo que exportó NaturalShot.")
    ap.add_argument("rutas", nargs="+", help="archivos o carpetas")
    ap.add_argument("--reporte", help="guarda un CSV: archivo, resultado, problema")
    ap.add_argument("--completo", action="store_true", help="agrega el volcado de ExifTool/ffprobe al reporte")
    args = ap.parse_args(argv)

    lista = archivos(args.rutas)
    if not lista:
        print("No hay fotos, videos ni audios en lo que pasaste.")
        return 0
    filas, fallan = [], 0
    for ruta in lista:
        try:
            problemas = (metadatos.auditar_imagen(ruta) if ruta.suffix.lower() in FOTOS else auditar_medio(ruta))
        except Exception as e:  # un archivo roto no corta la auditoría
            problemas = [f"no se pudo leer: {e}"]
        estado = "OK" if not problemas else "FALLA"
        fallan += bool(problemas)
        print(f"[{estado}] {ruta}")
        for p in problemas:
            print(f"        - {p}")
        extra = volcado(ruta) if args.completo else ""
        if problemas:
            filas += [(str(ruta), estado, p, extra) for p in problemas]
        else:
            filas.append((str(ruta), estado, "", extra))
    if args.reporte:
        with open(args.reporte, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["archivo", "resultado", "problema", "volcado"])
            w.writerows(filas)
        print(f"Reporte: {args.reporte}")
    print(f"{len(lista)} archivos, {fallan} con problemas.")
    return 1 if fallan else 0


if __name__ == "__main__":
    sys.exit(main())
