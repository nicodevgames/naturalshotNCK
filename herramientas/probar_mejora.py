"""Prueba "Mejorar calidad" (sin IA) con un pedazo de un video, antes de que esté la interfaz.

Uso:
    .venv\\Scripts\\python.exe herramientas\\probar_mejora.py <video> <inicio_s> <duracion_s> <720p|1080p> <salida.mp4>

Ejemplo (10 segundos desde el minuto 1, a 720p):
    .venv\\Scripts\\python.exe herramientas\\probar_mejora.py "C:\\videos\\cumple.mp4" 60 10 720p comparacion.mp4

Toma el pedazo del video que empieza en ``inicio_s`` y dura ``duracion_s``
segundos, lo mejora con los ajustes por defecto ("Mejorar calidad" prendido,
todas las barras a la mitad) y guarda un MP4 **lado a lado**: a la izquierda el
mismo pedazo agrandado con bicúbico (lo que haría cualquier programa) y a la
derecha el mejorado, cada uno con su etiqueta. Sin sonido. El cuadro de salida
mide el doble de ancho que la resolución pedida (2560×720 para un horizontal a
720p). Respeta la rotación de los videos de celular.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import av  # noqa: E402

from celular_natural.motor import video as motor_video  # noqa: E402
from celular_natural.motor.mejora_video import (  # noqa: E402
    AjustesMejora, MejoradorVideo, RESOLUCIONES_MEJORA, tamano_mejorado)


def _rotular(rgb: np.ndarray, texto: str) -> np.ndarray:
    """Etiqueta blanca sobre una franja oscura, arriba a la izquierda (en el lugar)."""
    escala = max(0.6, rgb.shape[0] / 900)
    grosor = max(1, round(escala * 1.6))
    (tw, th), base = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, escala, grosor)
    margen = round(10 * escala)
    cv2.rectangle(rgb, (0, 0), (tw + 2 * margen, th + base + 2 * margen), (0, 0, 0), -1)
    cv2.putText(rgb, texto, (margen, margen + th), cv2.FONT_HERSHEY_SIMPLEX, escala, (255, 255, 255), grosor,
                cv2.LINE_AA)
    return rgb


def _cuadros(ruta: str, inicio: float, duracion: float, rotacion: int, origen: float):
    """Cuadros RGB (ya derechos) del pedazo pedido, en orden."""
    with av.open(ruta) as contenedor:
        vs = contenedor.streams.video[0]
        vs.thread_type = "AUTO"
        tb = vs.time_base
        if inicio > 0 and tb:
            contenedor.seek(int((origen + max(0.0, inicio - 0.5)) / tb), stream=vs, backward=True)
        fin = inicio + duracion
        for cuadro in contenedor.decode(vs):
            if cuadro.pts is None or cuadro.time_base is None:
                continue
            t = float(cuadro.pts * cuadro.time_base) - origen
            if t < inicio - 1e-3:
                continue
            if t >= fin:
                break
            rgb = cuadro.to_ndarray(format="rgb24")
            if rotacion:
                rgb = np.rot90(rgb, k=rotacion // 90)
            yield np.ascontiguousarray(rgb)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Compara bicúbico contra 'Mejorar calidad' en un MP4 lado a lado.")
    p.add_argument("video")
    p.add_argument("inicio", type=float, help="segundos desde el principio")
    p.add_argument("duracion", type=float, help="segundos a procesar")
    p.add_argument("resolucion", choices=sorted(RESOLUCIONES_MEJORA))
    p.add_argument("salida")
    a = p.parse_args(argv)

    info = motor_video.info_video(a.video)
    ancho, alto = tamano_mejorado(info.ancho, info.alto, a.resolucion)
    print(f"{Path(a.video).name}: {info.ancho}x{info.alto}, {info.fps:.2f} cuadros/s -> {ancho}x{alto} "
          f"(lado a lado: {2 * ancho}x{alto})")

    codec = motor_video.elegir_codificador()
    destino = av.open(a.salida, "w", format="mp4")
    ov = destino.add_stream(codec, rate=info.tasa)
    ov.width, ov.height = 2 * ancho, alto
    ov.pix_fmt = "nv12" if codec == "h264_mf" else "yuv420p"
    if codec == "libx264":
        ov.options = {"crf": "16", "preset": "fast"}  # casi sin pérdida: que no tape la comparación
    else:
        ov.codec_context.bit_rate = int(2 * ancho * alto * info.fps * 0.3)

    mejorador = MejoradorVideo(AjustesMejora(activa=True), ancho, alto)
    originales: deque = deque()  # esperan a que salga su mejorado (sale con retraso)
    escritos = 0
    t0 = time.perf_counter()

    def escribir(mejorados):
        nonlocal escritos
        for mejorado in mejorados:
            original = originales.popleft()
            bicubico = cv2.resize(original, (ancho, alto), interpolation=cv2.INTER_CUBIC)
            lado_a_lado = np.hstack([_rotular(bicubico, "Bicubico"), _rotular(mejorado, "Mejorado (sin IA)")])
            for paquete in ov.encode(av.VideoFrame.from_ndarray(lado_a_lado, format="rgb24")):
                destino.mux(paquete)
            escritos += 1
            if escritos % 24 == 0:
                print(f"  {escritos} cuadros ({escritos / (time.perf_counter() - t0):.1f} cuadros/s)", flush=True)

    try:
        for rgb in _cuadros(a.video, a.inicio, a.duracion, info.rotacion, info.inicio):
            originales.append(rgb)
            escribir(mejorador.agregar(rgb))
        escribir(mejorador.terminar())
        for paquete in ov.encode():
            destino.mux(paquete)
    finally:
        destino.close()
    segundos = time.perf_counter() - t0
    if not escritos:
        print("No había cuadros en ese pedazo del video.")
        return 1
    print(f"Listo: {a.salida} ({escritos} cuadros en {segundos:.1f} s, "
          f"{1000 * segundos / escritos:.0f} ms por cuadro con la lectura y la escritura)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
