"""Descripción legible de cada paso del historial ("Ruido de sensor: 35 → 60")."""

from __future__ import annotations

from dataclasses import fields

from .. import edicion
from ..motor import CONTROLES, SECCIONES
from ..motor.documento import Documento
from ..motor.fusion import MODOS_FUSION
from ..motor.geometria import Geometria
from ..motor.zonas import ORIGENES_MASCARA
from .fondo import DESENFOCADO, completar_estado

# Interruptores de sección -> nombre que se muestra
_INTERRUPTORES = {sec.interruptor: sec.nombre for sec in SECCIONES if sec.interruptor}
_INTERRUPTORES["regiones_activas"] = "Máscaras por región"


def _nombre_campo(campo: str) -> str:
    if campo in _INTERRUPTORES:
        return _INTERRUPTORES[campo]
    control = CONTROLES.get(campo)
    if control is not None:
        return control.etiqueta
    if campo == "intensidad":
        return "Intensidad general"
    if campo == "semilla":
        return "Semilla"
    return campo.replace("_", " ").capitalize()


def _valor(v) -> str:
    if isinstance(v, bool):
        return "activada" if v else "desactivada"
    return str(v)


def _cambios_ajustes(a, b) -> list[str]:
    cambios = []
    for f in fields(a):
        va, vb = getattr(a, f.name), getattr(b, f.name)
        if va == vb:
            continue
        nombre = _nombre_campo(f.name)
        if isinstance(vb, bool):
            cambios.append(f"{nombre} {_valor(vb)}")
        else:
            cambios.append(f"{nombre}: {_valor(va)} → {_valor(vb)}")
    return cambios


def _con_pincel(za, zb) -> str | None:
    """'pintada' o 'retocada con el pincel' si la zona cambió con el pincel; si no, None.

    Una máscara automática (cielo, piel, contorno) corregida con el pincel
    también cuenta como retocada.
    """
    if zb is None or not zb.es_raster:
        return None
    if zb.es_mascara:
        if za is not None and za.es_mascara and za.datos == zb.datos and za.trazos != zb.trazos:
            return "retocada con el pincel"
        return None
    if za is None or not za.es_pincel:
        return "pintada"
    return "retocada con el pincel" if za.trazos != zb.trazos else None


def _automatica(za, zb) -> str | None:
    """'Cielo (automático)' o 'Piel (automática)' si la zona nueva es una máscara detectada."""
    if zb is None or not zb.es_mascara or (za is not None and za.es_mascara and za.datos == zb.datos):
        return None
    nombre = ORIGENES_MASCARA.get(zb.origen, "automática")
    if zb.origen == "cielo":
        return "Cielo (automático)"
    if zb.origen == "piel":
        return "Piel (automática)"
    return nombre


def _angulo(v: float) -> str:
    return f"{v:+.1f}°".replace(".", ",").replace("+0,0°", "0°")


def describir_geometria(a: Geometria, b: Geometria) -> str:
    """'Girar 90° a la derecha', 'Voltear horizontal', 'Enderezar: 0° → +2,5°'..."""
    if b == a.girada(1):
        return "Girar 90° a la derecha"
    if b == a.girada(-1):
        return "Girar 90° a la izquierda"
    if b == a.girada(2):
        return "Girar 180°"
    if b == a.volteada(True):
        return "Voltear horizontal"
    if b == a.volteada(False):
        return "Voltear vertical"
    if (a.giro90, a.voltear_h, a.voltear_v) == (b.giro90, b.voltear_h, b.voltear_v):
        if b.enderezar == 0:
            return "Enderezado quitado"
        return f"Enderezar: {_angulo(a.enderezar)} → {_angulo(b.enderezar)}"
    if b.es_identidad():
        return "Rotación quitada"
    return "Rotar y voltear"


def _describir_borrado(ba: tuple, bb: tuple) -> str:
    if len(bb) > len(ba):
        nuevo = bb[-1]
        return "Objeto borrado (clonado)" if nuevo.modo == "clonar" else "Objeto borrado (relleno automático)"
    if len(bb) < len(ba):
        return "Borrado quitado"
    for i, (a, b) in enumerate(zip(ba, bb), start=1):
        if a == b:
            continue
        if a.modo != b.modo:
            return f"Borrado {i}: clonar" if b.modo == "clonar" else f"Borrado {i}: relleno automático"
        if a.zona != b.zona:
            pincel = _con_pincel(a.zona, b.zona)
            return f"Borrado {i}: zona {pincel}" if pincel else f"Borrado {i}: zona"
        if (a.dx, a.dy) != (b.dx, b.dy):
            return f"Borrado {i}: fuente del clonado"
        return f"Borrado {i}: fundido " + ("activado" if b.sin_costuras else "desactivado")
    return "Borrar objetos"


def _pct(v: float) -> str:
    return f"{round(v * 100)} %"


def _nombre_capa(c) -> str:
    return f"«{c.nombre}»" if c.nombre else "sin nombre"


def describir_documento(da: Documento | None, db: Documento | None) -> str | None:
    """Qué cambió en las capas ("Capa agregada: logo.png", "Capa «logo» transformada"...), o
    None si nada. Un documento que falta (None) es el de siempre: la foto y "Celular natural"."""
    if da == db:
        return None
    capas_a = {c.id: c for c in da.capas} if da is not None else {}
    capas_b = {c.id: c for c in db.capas} if db is not None else {}
    if da is None or db is None:
        # Uno de los dos es el documento de siempre: se compara con sus capas por defecto.
        base = db if da is None else da
        nuevo = Documento.nuevo(base.ancho, base.alto)
        if da is None:
            da, capas_a = nuevo, {c.id: c for c in nuevo.capas}
        else:
            db, capas_b = nuevo, {c.id: c for c in nuevo.capas}
    agregadas = [c for i, c in capas_b.items() if i not in capas_a]
    if len(agregadas) > 1:
        return f"{len(agregadas)} capas agregadas"
    if agregadas:
        c = agregadas[-1]
        copia = any(x.imagen == c.imagen for x in capas_a.values()) and c.nombre.endswith(" copia")
        return f"Capa duplicada: {c.nombre}" if copia else f"Capa agregada: {c.nombre}"
    quitadas = [c for i, c in capas_a.items() if i not in capas_b]
    if quitadas:
        return f"Capa borrada: {quitadas[0].nombre}"
    orden_a, orden_b = [c.id for c in da.capas], [c.id for c in db.capas]
    if orden_a != orden_b:
        movida = max(orden_b, key=lambda i: abs(orden_b.index(i) - orden_a.index(i)))
        sube = orden_b.index(movida) > orden_a.index(movida)
        return f"Capa {_nombre_capa(capas_b[movida])} " + ("subida" if sube else "bajada")
    for i in orden_b:
        a, b = capas_a[i], capas_b[i]
        if a == b:
            continue
        nombre = _nombre_capa(b)
        if a.nombre != b.nombre:
            return f"Capa renombrada: {a.nombre} → {b.nombre}"
        if a.visible != b.visible:
            return f"Capa {nombre} " + ("visible" if b.visible else "oculta")
        if a.bloqueada != b.bloqueada:
            return f"Capa {nombre} " + ("bloqueada" if b.bloqueada else "desbloqueada")
        if a.opacidad != b.opacidad:
            if b.tipo == "ajuste_natural":
                return f"Cuánto filtro: {_pct(a.opacidad)} → {_pct(b.opacidad)}"
            return f"Capa {nombre}: opacidad {_pct(a.opacidad)} → {_pct(b.opacidad)}"
        if a.fusion != b.fusion:
            return f"Capa {nombre}: fusión {MODOS_FUSION.get(b.fusion, b.fusion)}"
        if a.mascara != b.mascara:
            if a.mascara is None:
                return f"Capa {nombre}: máscara agregada"
            if b.mascara is None:
                return f"Capa {nombre}: máscara quitada"
            return f"Capa {nombre}: máscara editada"
        if a.transform != b.transform:
            ta, tb = a.transform, b.transform
            if (ta.x, ta.y, ta.escala, ta.escala_y, ta.rotacion) == (tb.x, tb.y, tb.escala, tb.escala_y, tb.rotacion):
                return f"Capa {nombre} volteada"
            if ((ta.escala, ta.escala_y, ta.rotacion, ta.voltear_h, ta.voltear_v)
                    == (tb.escala, tb.escala_y, tb.rotacion, tb.voltear_h, tb.voltear_v)):
                return f"Capa {nombre} movida"
            return f"Capa {nombre} transformada"
        if a.imagen != b.imagen:
            return f"Capa {nombre}: imagen cambiada"
        if a.padre != b.padre:
            return f"Capa {nombre} " + ("sacada del grupo" if b.padre is None else "metida en un grupo")
        if a.params != b.params:
            return f"Capa {nombre} cambiada"
        if a.estilos != b.estilos:
            return f"Capa {nombre}: estilos"
        if a.tipo != b.tipo:
            return f"Capa {nombre} rasterizada"
    if (da.ancho, da.alto) != (db.ancho, db.alto):
        return f"Tamaño del lienzo: {db.ancho} × {db.alto} px"
    return "Capas"


def describir_cambio(antes: dict, despues: dict) -> str:
    """Texto corto que explica qué cambió entre dos estados del editor.

    Acepta estados viejos (sin geometría ni borrado, fondo de dos elementos,
    capas sin zona).
    """
    ga, gb = antes.get("geometria") or Geometria(), despues.get("geometria") or Geometria()
    if ga != gb:
        # Al girar también se convierten las zonas y el recorte: el paso es el giro.
        return describir_geometria(ga, gb)
    ba, bb = tuple(antes.get("borrado", ())), tuple(despues.get("borrado", ()))
    if ba != bb:
        return _describir_borrado(ba, bb)
    if antes.get("medida") != despues.get("medida"):
        # Elegir una medida también pone su recorte: el paso es la medida.
        from ..motor.medida import texto_medida
        return "Medida: " + texto_medida(despues.get("medida"))
    if antes.get("recorte") != despues.get("recorte"):
        return "Recorte quitado" if despues.get("recorte") is None else "Recorte"
    capas = describir_documento(antes.get("documento"), despues.get("documento"))
    if capas:
        return capas
    fa, fb = completar_estado(antes.get("fondo")), completar_estado(despues.get("fondo"))
    if fa != fb:
        (za, recorte_a, modo_a, intensidad_a, transicion_a, prof_a) = fa
        (zb, recorte_b, modo_b, intensidad_b, transicion_b, prof_b) = fb
        desenfocado = modo_b == DESENFOCADO
        if zb is None and za is not None:
            return "Fondo restaurado"
        if za is None and zb is not None:
            objeto = ("contorno ajustado" if zb.es_mascara else
                      "objeto pintado" if zb.es_pincel else "objeto marcado")
            return f"Fondo desenfocado ({objeto})" if desenfocado else f"Fondo quitado ({objeto})"
        if modo_a != modo_b:
            return "Fondo: desenfocado" if desenfocado else "Fondo: transparente"
        if recorte_a != recorte_b:
            return "Recortar al objeto: " + ("sí" if recorte_b else "no")
        if intensidad_a != intensidad_b:
            return f"Desenfoque de fondo: intensidad {intensidad_a} → {intensidad_b}"
        if transicion_a != transicion_b:
            return f"Desenfoque de fondo: transición {transicion_a} → {transicion_b}"
        if prof_a != prof_b:
            return "Profundidad gradual " + _valor(prof_b)
        if zb is not None and zb.es_mascara and not (za is not None and za.es_mascara and za.datos == zb.datos):
            return "Objeto ajustado al contorno"
        pincel = _con_pincel(za, zb)
        if pincel:
            return "Objeto pintado" if pincel == "pintada" else "Objeto retocado con el pincel"
        return "Contorno del objeto"
    ma, mb = antes.get("montaje", ()), despues.get("montaje", ())
    if ma != mb:
        if len(mb) > len(ma):
            return f"Foto superpuesta: {mb[-1].ruta.replace(chr(92), '/').rsplit('/', 1)[-1]}"
        if len(mb) < len(ma):
            return "Foto superpuesta quitada"
        for i, (a, b) in enumerate(zip(ma, mb), start=1):
            if a == b:
                continue
            if a.zona != b.zona:
                auto = _automatica(a.zona, b.zona)
                if auto:
                    return f"Foto {i}: zona {auto}"
                pincel = _con_pincel(a.zona, b.zona)
                return f"Foto {i}: zona {pincel}" if pincel else f"Foto {i}: zona"
            if a.opacidad != b.opacidad:
                return f"Foto {i}: opacidad {a.opacidad} → {b.opacidad}"
            return f"Foto {i}: alinear / igualar"
    if antes["preset"] != despues["preset"]:
        return f"Preset: {despues['preset']}"

    capas_a, capas_b = antes["capas"], despues["capas"]
    if len(capas_b) > len(capas_a):
        return (f"Efecto agregado: {capas_b[-1][0]}" if edicion.es_lite() else f"Capa agregada: {capas_b[-1][0]}")
    if len(capas_b) < len(capas_a):
        return "Efecto quitado" if edicion.es_lite() else "Capa quitada"
    efecto = "Efecto" if edicion.es_lite() else "Capa"  # la PRO sigue diciendo "Capa", como su tutorial
    for i, (ca, cb) in enumerate(zip(capas_a, capas_b), start=1):
        if ca == cb:
            continue
        if ca[0] != cb[0]:
            return f"{efecto} {i}: {cb[0]}"
        if ca[1] != cb[1]:
            return f"{efecto} {i}: intensidad {ca[1]} → {cb[1]}"
        za, zb = (ca[2] if len(ca) > 2 else None), (cb[2] if len(cb) > 2 else None)
        if zb is None:
            return f"{efecto} {i}: toda la foto"
        auto = _automatica(za, zb)
        if auto:
            return f"{efecto} {i}: zona {auto}"
        if za is None:
            return f"{efecto} {i}: zona pintada" if zb.es_pincel else f"{efecto} {i}: zona marcada"
        pincel = _con_pincel(za, zb)
        if pincel:
            return f"{efecto} {i}: zona {pincel}"
        if (za.x0, za.y0, za.x1, za.y1, za.forma, za.puntos) != (zb.x0, zb.y0, zb.x1, zb.y1, zb.forma, zb.puntos):
            return f"{efecto} {i}: zona movida"
        if za.invertir != zb.invertir:
            return f"{efecto} {i}: zona invertida" if zb.invertir else f"{efecto} {i}: zona sin invertir"
        return f"{efecto} {i}: borde suave {za.pluma} → {zb.pluma}"

    cambios = _cambios_ajustes(antes["ajustes"], despues["ajustes"])
    if not cambios:
        return "Cambio"
    if len(cambios) == 1:
        return cambios[0]
    return f"{cambios[0]} y {len(cambios) - 1} más"
