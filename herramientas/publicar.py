"""Prepara una versión nueva de NaturalShot PRO para publicar (y, si se pide, la sube a GitHub).

Uso (desde la carpeta del proyecto):

    publicar_version.bat 1.1.0 "Novedad 1" "Novedad 2"
    publicar_version.bat                       pregunta la versión y las novedades
    publicar_version.bat 1.1.0 "Novedad" --subir

Pasos:
  1. Actualiza ``__version__`` en ``celular_natural/__init__.py``.
  2. Corre todas las pruebas; si alguna falla, se detiene y deja la versión como estaba.
  3. Compila con PyInstaller (``NaturalShot.spec``) en ``dist\\NaturalShot``.
  4. Arma ``NaturalShot-PRO.zip``: la carpeta ``NaturalShot PRO\\`` y el ``LEEME.txt``
     (``herramientas/LEEME_distribucion.txt``).
  5. Calcula el SHA-256 y el tamaño.
  6. Escribe ``version.json`` (el manifiesto que lee la app).
  7. Deja todo en ``publicar\\vX.Y.Z\\`` y actualiza ``NaturalShot PRO - para otra PC.zip``.

La subida a GitHub es aparte y solo con ``--subir``: usa ``gh release create`` en el
repositorio privado (``REPOSITORIO`` de ``celular_natural/actualizador.py``) con la sesión
de ``gh`` del dueño. Si el repositorio no existe, lo avisa: no lo crea. Sin ``--subir``,
imprime el comando para hacerlo a mano.

``Tutorial\\tutorial_compartible.pdf``, si existe, se sube junto con la versión. La guía
``Tutorial\\NaturalShot - Guía de uso.pdf`` NO se sube nunca (tiene una foto personal).
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

ARCHIVO_VERSION = RAIZ / "celular_natural" / "__init__.py"
LEEME = RAIZ / "herramientas" / "LEEME_distribucion.txt"
TUTORIAL_COMPARTIBLE = RAIZ / "Tutorial" / "tutorial_compartible.pdf"
ZIP_RAIZ = RAIZ / "NaturalShot PRO - para otra PC.zip"
CARPETA_ZIP = "NaturalShot PRO"  # carpeta raíz dentro del zip
_PATRON = re.compile(r'^__version__\s*=\s*"([^"]*)"', re.MULTILINE)


def paso(numero, texto: str) -> None:
    print(f"\n[{numero}] {texto}", flush=True)


def version_actual() -> str:
    m = _PATRON.search(ARCHIVO_VERSION.read_text(encoding="utf-8"))
    if m is None:
        raise SystemExit(f"No encontré __version__ en {ARCHIVO_VERSION}.")
    return m.group(1)


def escribir_version(version: str) -> None:
    crudo = ARCHIVO_VERSION.read_bytes().decode("utf-8")
    nuevo, n = _PATRON.subn(f'__version__ = "{version}"', crudo, count=1)
    if n != 1:
        raise SystemExit(f"No pude actualizar __version__ en {ARCHIVO_VERSION}.")
    ARCHIVO_VERSION.write_bytes(nuevo.encode("utf-8"))


def pedir_datos(args) -> tuple[str, list[str]]:
    """La versión y las novedades: de la línea de comandos o preguntando por consola."""
    version = args.version
    notas = [n.strip() for n in args.notas if n.strip()]
    if not version:
        version = input(f"Versión nueva (la actual es {version_actual()}): ").strip()
    if not notas:
        print("Novedades de esta versión, una por línea (Enter en una línea vacía para terminar):")
        while True:
            linea = input("  • ").strip()
            if not linea:
                break
            notas.append(linea)
    return version.lstrip("vV"), notas


def correr(comando: list, **kw) -> int:
    print("    $ " + subprocess.list2cmdline([str(c) for c in comando]), flush=True)
    return subprocess.call([str(c) for c in comando], **kw)


def correr_pruebas() -> bool:
    entorno = dict(os.environ)
    temporal = Path(tempfile.mkdtemp(prefix="naturalshot_publicar_"))
    # Las pruebas no tocan el registro ni los presets del usuario.
    entorno.update(QT_QPA_PLATFORM="offscreen", APPDATA=str(temporal / "appdata"),
                   NATURALSHOT_CONFIG=str(temporal / "preferencias.ini"))
    for variable in [k for k in entorno if k.startswith("NATURALSHOT_") and k != "NATURALSHOT_CONFIG"]:
        del entorno[variable]
    try:
        return correr([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=RAIZ, env=entorno) == 0
    finally:
        shutil.rmtree(temporal, ignore_errors=True)


def compilar(distpath: Path, workpath: Path) -> Path:
    codigo = correr([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", distpath,
                     "--workpath", workpath, RAIZ / "NaturalShot.spec"], cwd=RAIZ)
    app = distpath / "NaturalShot"
    if codigo != 0 or not (app / "NaturalShot.exe").is_file() or not (app / "_internal").is_dir():
        raise SystemExit("La compilación falló. Si NaturalShot está abierta desde dist\\, cerrala y probá de nuevo.")
    return app


def armar_zip(app: Path, destino: Path, carpeta: str = CARPETA_ZIP, leeme: Path = LEEME) -> None:
    """``NaturalShot PRO\\`` (el .exe y _internal) más el LEEME, como el paquete de siempre.
    ``carpeta`` y ``leeme``: para otra edición (``construir_lite.bat`` arma "NaturalShot Lite")."""
    tmp = destino.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for ruta in sorted(app.rglob("*")):
            if ruta.is_file():
                z.write(ruta, f"{carpeta}/{ruta.relative_to(app).as_posix()}")
        z.write(leeme, "LEEME.txt")
    os.replace(tmp, destino)


def sha256_de(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def _relativa(ruta: Path) -> str:
    """La ruta desde la carpeta del proyecto (el comando se corre desde ahí)."""
    try:
        return str(ruta.resolve().relative_to(RAIZ))
    except ValueError:
        return str(ruta)


def comando_subida(repo: str, version: str, archivos: list[Path], notas: Path) -> list[str]:
    return ["gh", "release", "create", f"v{version}", *[_relativa(a) for a in archivos], "--repo", repo,
            "--title", f"NaturalShot PRO {version}", "--notes-file", _relativa(notas)]


def subir(repo: str, version: str, archivos: list[Path], notas: Path) -> int:
    """Sube la versión con gh. No crea el repositorio: si no existe, lo avisa."""
    if shutil.which("gh") is None:
        print("No encontré la herramienta 'gh' (GitHub CLI). Instalala desde https://cli.github.com y "
              "corré 'gh auth login'.")
        return 1
    if subprocess.call(["gh", "auth", "status"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        print("'gh' no tiene una sesión iniciada. Corré 'gh auth login' con la cuenta del dueño.")
        return 1
    vista = subprocess.run(["gh", "repo", "view", repo, "--json", "visibility"], capture_output=True, text=True)
    if vista.returncode != 0:
        print(f"El repositorio {repo} no existe o tu cuenta de gh no tiene acceso.\n"
              "Este script no lo crea: crealo primero (privado), como explica el README.")
        return 1
    visibilidad = (json.loads(vista.stdout or "{}").get("visibility") or "").upper()
    if visibilidad != "PRIVATE":
        print(f"El repositorio {repo} es {visibilidad or 'de visibilidad desconocida'}, no privado. "
              "Las versiones solo se publican en un repositorio privado: no subo nada.")
        return 1
    if subprocess.call(["gh", "release", "view", f"v{version}", "--repo", repo],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
        print(f"Ya existe la versión v{version} en {repo}. Usá un número de versión nuevo.")
        return 1
    return correr(comando_subida(repo, version, archivos, notas), cwd=RAIZ)


def main(argv=None) -> int:
    from celular_natural.actualizador import NOMBRE_MANIFIESTO, NOMBRE_ZIP, REPOSITORIO, es_mas_nueva, interpretar_version

    parser = argparse.ArgumentParser(description="Prepara una versión nueva de NaturalShot PRO.")
    parser.add_argument("version", nargs="?", help="número de versión nuevo, por ejemplo 1.1.0")
    parser.add_argument("notas", nargs="*", help="novedades (una por argumento, entre comillas)")
    parser.add_argument("--subir", action="store_true",
                        help="además, subirla a GitHub con 'gh release create' (paso aparte y opcional)")
    parser.add_argument("--obligatoria", default="0.0.0",
                        help="NS-103.6: las versiones instaladas anteriores a esta tienen que actualizar "
                             "(sin \"Más tarde\" ni \"No avisar\"); por ejemplo, la misma versión nueva")
    parser.add_argument("--minima", default="1.0.0",
                        help="versión más vieja que se puede actualizar sola a esta (por defecto 1.0.0)")
    parser.add_argument("--distpath", type=Path, default=RAIZ / "dist", help="dónde compilar (por defecto dist)")
    parser.add_argument("--workpath", type=Path, default=RAIZ / "build",
                        help="carpeta de trabajo de PyInstaller (por defecto build)")
    args = parser.parse_args(argv)

    version, notas = pedir_datos(args)
    try:
        interpretar_version(version)
        interpretar_version(args.minima)
        interpretar_version(args.obligatoria)
    except ValueError as error:
        print(f"{error}. Ejemplo: publicar_version.bat 1.1.0 \"Novedad\"")
        return 2
    if not notas:
        print("Escribí al menos una novedad (aparecen en el aviso de la app).")
        return 2
    anterior = version_actual()
    if es_mas_nueva(anterior, version):
        print(f"La versión {version} es más vieja que la actual ({anterior}).")
        return 2
    if version == anterior:
        print(f"Aviso: la versión ya es {version}; se vuelve a compilar con el mismo número.")

    salida = RAIZ / "publicar" / f"v{version}"
    print(f"NaturalShot PRO {anterior} -> {version}  ·  repositorio {REPOSITORIO}")

    paso(1, f"Versión {version} en celular_natural/__init__.py")
    escribir_version(version)
    try:
        paso(2, "Corriendo todas las pruebas…")
        if not correr_pruebas():
            raise SystemExit("Fallaron pruebas: no se publica nada.")
        paso(3, "Compilando con PyInstaller…")
        app = compilar(args.distpath.resolve(), args.workpath.resolve())
    except BaseException:
        escribir_version(anterior)
        print(f"Se dejó la versión como estaba ({anterior}).")
        raise

    paso(4, f"Armando {NOMBRE_ZIP}…")
    salida.mkdir(parents=True, exist_ok=True)
    archivo_zip = salida / NOMBRE_ZIP
    armar_zip(app, archivo_zip)

    paso(5, "Calculando SHA-256 y tamaño…")
    sha, tamano = sha256_de(archivo_zip), archivo_zip.stat().st_size
    print(f"    SHA-256 {sha}\n    {tamano:,} bytes ({tamano / 1024 / 1024:.1f} MB)".replace(",", "."))

    paso(6, f"Escribiendo {NOMBRE_MANIFIESTO}…")
    manifiesto = {"version": version, "fecha": datetime.date.today().isoformat(), "notas": notas,
                  "zip": NOMBRE_ZIP, "sha256": sha, "tamano": tamano, "minima": args.minima,
                  "obligatoria": args.obligatoria}
    (salida / NOMBRE_MANIFIESTO).write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
    archivo_notas = salida / "notas.md"
    archivo_notas.write_text(f"## Novedades de NaturalShot PRO {version}\n\n" + "".join(f"- {n}\n" for n in notas)
                             + "\nPara instalarla: abrí NaturalShot y tocá **Actualizar ahora** en el aviso.\n",
                             encoding="utf-8")
    archivos = [archivo_zip, salida / NOMBRE_MANIFIESTO]
    if TUTORIAL_COMPARTIBLE.exists():
        copia = salida / TUTORIAL_COMPARTIBLE.name
        shutil.copy2(TUTORIAL_COMPARTIBLE, copia)
        archivos.append(copia)

    paso(7, "Listo para publicar")
    shutil.copy2(archivo_zip, ZIP_RAIZ)
    print(f"    Carpeta: {salida}")
    for a in archivos:
        print(f"      {a.name}")
    print(f"    También se actualizó \"{ZIP_RAIZ.name}\".")

    comando = comando_subida(REPOSITORIO, version, archivos, archivo_notas)
    if not args.subir:
        print("\nNo se subió nada. Para publicarla en GitHub (repositorio privado), corré desde la carpeta "
              "del proyecto:\n")
        print("    " + subprocess.list2cmdline(comando))
        print("\no volvé a correr este script con --subir.")
        return 0
    paso(8, f"Subiendo v{version} a {REPOSITORIO}…")
    return subir(REPOSITORIO, version, archivos, archivo_notas)


if __name__ == "__main__":
    sys.exit(main())
