"""Muestrario del modo Audio: fondos, sonidos y escenas para escuchar y decir qué suena creíble.

Genera, en la carpeta del proyecto:

    Muestras de audio\\2 - Fondos y sonidos\\
        Fondos\\<nombre> (suave).wav    cada fondo a intensidad 0,3, 20 s
        Fondos\\<nombre> (fuerte).wav   el mismo a intensidad 0,8
        Sonidos\\<nombre>.wav           cada sonido suelto
        LEEME.txt                       solo si no hay uno (no pisa el que ya está)
    Muestras de audio\\3 - Escenas\\
        Voz de prueba.wav               una voz de Windows (System.Speech), sin conexión
        <nombre de la escena>.ogg       las notas de voz de WhatsApp, en el formato de WhatsApp
        <nombre de la escena>.m4a       las demás (video de celular, auriculares, solo IA)
        LEEME.txt                       qué es cada cosa y qué hay que decir de cada una

No toca "1 - Voz (adelanto)". **Nunca usa archivos personales:** la voz de prueba la
genera Windows con su voz en español (Microsoft Sabina, si está; si no hay ninguna en
español, cualquier voz instalada, y avisa). Los fondos y los sonidos son los de la
biblioteca generada (semilla 1, como los primeros que se publicaron); las escenas usan
el proyecto tal cual lo arma ``aplicar_escena`` y se exportan con ``exportar_proyecto``.

Uso (desde la carpeta del proyecto):

    .venv\\Scripts\\python herramientas\\muestrario_audio.py              todo
    .venv\\Scripts\\python herramientas\\muestrario_audio.py --solo-escenas
    .venv\\Scripts\\python herramientas\\muestrario_audio.py --voz-nueva   vuelve a generar la voz de prueba
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from celular_natural.motor import ambientes as am  # noqa: E402
from celular_natural.motor import proyecto_audio as pa  # noqa: E402

MUESTRAS = RAIZ / "Muestras de audio"
FONDOS_Y_SONIDOS = MUESTRAS / "2 - Fondos y sonidos"
ESCENAS = MUESTRAS / "3 - Escenas"
VOZ = ESCENAS / "Voz de prueba.wav"
SEMILLA = 1
SEGUNDOS_FONDO = 20
INTENSIDADES = (("suave", 0.3), ("fuerte", 0.8))

# Una nota de voz común, de unos 25 segundos: alcanza para que los sonidos sueltos de las
# escenas (un colectivo de 10 s a los 40 %, por ejemplo) se oigan enteros.
TEXTO = ("Hola, ¿cómo andás? Te mando este audio porque recién salgo de la reunión y no te pude llamar. "
         "Mirá, lo que hablamos ayer está bien, pero necesito que me confirmes el horario antes de las seis, "
         "así lo organizo con el resto del equipo. Si hoy no podés, avisame y lo pasamos para mañana a la "
         "mañana, no hay ningún problema. Bueno, cualquier cosa me escribís. Un abrazo, chau.")

_PS_VOZ = r"""
param([string]$Texto, [string]$Salida)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voces = @($s.GetInstalledVoices() | Where-Object { $_.Enabled })
$es = @($voces | Where-Object { $_.VoiceInfo.Culture.Name -like 'es*' })
$elegida = $es | Where-Object { $_.VoiceInfo.Name -like '*Sabina*' } | Select-Object -First 1
if (-not $elegida) { $elegida = $es | Select-Object -First 1 }
if ($elegida) { $s.SelectVoice($elegida.VoiceInfo.Name); Write-Output ("ES|" + $elegida.VoiceInfo.Name) }
else { Write-Output ("OTRA|" + $s.Voice.Name) }
$formato = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(48000,
    [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile($Salida, $formato)
# Get-Content -Raw devuelve vacío en algunas PowerShell 5.1: se lee con .NET.
$s.Speak([System.IO.File]::ReadAllText($Texto, [System.Text.Encoding]::UTF8))
$s.Dispose()
"""


def guardar_wav(ruta: Path, x: np.ndarray, frecuencia: int = 48000) -> None:
    """(n, canales) float -> WAV de 16 bits."""
    datos = np.clip(np.round(np.asarray(x, np.float64) * 32767), -32768, 32767).astype("<i2")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(datos.shape[1])
        w.setsampwidth(2)
        w.setframerate(frecuencia)
        w.writeframes(datos.tobytes())


def generar_voz(destino: Path) -> str:
    """La voz de prueba con ``System.Speech`` de Windows (sin conexión). Devuelve el nombre de la voz."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    # Los temporales, junto a la salida (no en %TEMP%): el script no toca nada fuera de la carpeta del proyecto.
    with tempfile.TemporaryDirectory(prefix=".muestrario_voz_", dir=destino.parent) as carpeta:
        script = Path(carpeta) / "voz.ps1"
        texto = Path(carpeta) / "texto.txt"
        temporal = Path(carpeta) / "voz.wav"
        script.write_text(_PS_VOZ, encoding="utf-8-sig")
        texto.write_text(TEXTO, encoding="utf-8")
        salida = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Texto", str(texto),
             "-Salida", str(temporal)], capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL)
        if salida.returncode != 0 or not temporal.is_file():
            raise RuntimeError(f"No se pudo generar la voz de prueba con Windows:\n{salida.stderr.strip()}")
        linea = next((l for l in salida.stdout.splitlines() if "|" in l), "OTRA|?")
        clase, nombre = linea.strip().split("|", 1)
        if clase != "ES":
            print(f"OJO: no hay ninguna voz de Windows en español; se usó «{nombre}».")
        destino.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporal, destino)
    return nombre


def fondos_y_sonidos() -> None:
    for clave, info in am.FONDOS.items():
        for etiqueta, intensidad in INTENSIDADES:
            t0 = time.perf_counter()
            x = am.GeneradorFondo(clave, intensidad, SEMILLA).leer(0, SEGUNDOS_FONDO * am.FRECUENCIA)
            guardar_wav(FONDOS_Y_SONIDOS / "Fondos" / f"{info.nombre} ({etiqueta}).wav", x)
            print(f"  fondo  {info.nombre} ({etiqueta}): {time.perf_counter() - t0:.1f} s")
    for clave, info in am.SONIDOS.items():
        guardar_wav(FONDOS_Y_SONIDOS / "Sonidos" / f"{info.nombre}.wav", am.generar_sonido(clave, SEMILLA))
        print(f"  sonido {info.nombre}")
    leeme = FONDOS_Y_SONIDOS / "LEEME.txt"
    if not leeme.exists():
        leeme.write_text(LEEME_FONDOS, encoding="utf-8-sig")


def formato_de(escena: pa.Escena) -> str:
    return "whatsapp" if escena.voz.destino == "whatsapp" else "m4a"


def escenas(voz: Path) -> list[tuple[pa.Escena, Path, float]]:
    hechas = []
    base = pa.abrir_proyecto(voz)
    for e in pa.ESCENAS.values():
        formato = formato_de(e)
        destino = ESCENAS / f"{e.nombre}{pa.FORMATOS_PROYECTO_INFO[formato].extension}"
        r = pa.exportar_proyecto(pa.aplicar_escena(base, e), destino, formato)
        print(f"  escena {destino.name}: {r.duracion:.1f} s en {r.segundos:.1f} s")
        hechas.append((e, destino, r.duracion))
    return hechas


LEEME_FONDOS = """FONDOS Y SONIDOS GENERADOS (sin grabaciones: todo hecho por la app)
==================================================================

Fondos\\  -> cada ambiente en 20 segundos, en versión "suave" y "fuerte".
Sonidos\\ -> los sonidos sueltos que se ponen en un momento justo.

Escuchalos con auriculares si podés y decime cuáles suenan creíbles, cuáles suenan
"a ruido" o falsos, y si alguno está muy fuerte o muy bajo.
"""


def leeme_escenas(voz: str | None, hechas) -> str:
    lineas = [
        "ESCENAS: TODO JUNTO, COMO VA A QUEDAR EN LA APP",
        "===============================================",
        "",
        "Acá está la misma voz pasada por cada \"escena\" del modo Audio. Una escena arma",
        "todo con un clic: cómo se grabó (WhatsApp, video de celular o auriculares), el",
        "lugar (el eco), el ruido de fondo y, en algunas, un sonido en un momento justo",
        "(un colectivo que pasa, una frenada, una sirena).",
        "",
        f"- \"Voz de prueba.wav\": la voz tal cual, sin nada. Es una voz de Windows{f' ({voz})' if voz else ''},",
        "  que suena bastante \"a IA\" a propósito: así se nota lo que hace cada escena.",
        "- Los archivos .ogg son notas de voz de WhatsApp, en el mismo formato que usa",
        "  WhatsApp. Si no se abren con doble clic, abrilos con VLC (o mandátelos por WhatsApp).",
        "- Los .m4a son el sonido de un video de celular o de una llamada con auriculares.",
        "",
        "Las escenas:",
    ]
    for e, destino, _duracion in hechas:
        lineas.append(f"- {destino.name}: {e.descripcion}")
    lineas += [
        "",
        "LO QUE NECESITO QUE ME DIGAS, ESCENA POR ESCENA",
        "",
        "1. ¿Suena a que alguien lo grabó de verdad con el celular en ese lugar?",
        "   (sí / más o menos / no)",
        "2. El fondo: ¿muy fuerte, muy bajo o bien?",
        "3. ¿Algo suena falso? Por ejemplo: \"el colectivo suena a juguete\", \"el eco",
        "   parece de un baño\", \"la voz suena metálica\" o \"se nota que el fondo está pegado\".",
        "4. Los sonidos sueltos (colectivo, frenada, auto, sirena): ¿entran en buen momento?",
        "   ¿Tapan demasiado la voz o casi no se oyen?",
        "",
        "Con lo que me digas ajusto los volúmenes y los sonidos antes de armar la pantalla.",
        "",
    ]
    return "\n".join(lineas)


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera el muestrario del modo Audio.")
    parser.add_argument("--solo-escenas", action="store_true", help="no vuelve a generar los fondos ni los sonidos")
    parser.add_argument("--voz-nueva", action="store_true", help="vuelve a generar la voz de prueba con Windows")
    args = parser.parse_args()
    t0 = time.perf_counter()
    if not args.solo_escenas:
        print(f"Fondos y sonidos en {FONDOS_Y_SONIDOS}")
        fondos_y_sonidos()
    if args.voz_nueva or not VOZ.exists():
        nombre_voz = generar_voz(VOZ)
        print(f"Voz de prueba ({nombre_voz}): {VOZ}")
    else:
        nombre_voz = None
        print(f"Voz de prueba: la que ya estaba ({VOZ.name})")
    print(f"Escenas en {ESCENAS}")
    hechas = escenas(VOZ)
    (ESCENAS / "LEEME.txt").write_text(leeme_escenas(nombre_voz, hechas), encoding="utf-8-sig")
    print(f"Listo en {time.perf_counter() - t0:.0f} s.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
