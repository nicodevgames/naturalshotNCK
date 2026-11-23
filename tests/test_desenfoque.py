"""Pruebas del desenfoque de fondo (modo retrato)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from celular_natural.motor.desenfoque import (  # noqa: E402
    desenfocar_fondo, desenfocar_zona, limpiar_cache, radio_desenfoque,
)
from celular_natural.motor.zonas import Recorte, Zona, aplicar_recorte, mascara_zona  # noqa: E402

# Silueta (lazo poligonal) en coordenadas normalizadas de la foto.
SILUETA = [(0.42, 0.95), (0.40, 0.55), (0.36, 0.45), (0.45, 0.38), (0.44, 0.25), (0.5, 0.18),
           (0.56, 0.25), (0.55, 0.38), (0.64, 0.45), (0.60, 0.55), (0.58, 0.95)]
ROJO = (225, 25, 30)


def fondo_textura(w, h, semilla=0):
    """Fondo verde-azulado con detalle fino que escala con el tamaño (definido en coordenadas 0..1)."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    x, y = (xx + 0.5) / w, (yy + 0.5) / h
    patron = np.sin(2 * np.pi * 60 * x) * np.sin(2 * np.pi * 45 * y)  # detalle fino
    grande = np.sin(2 * np.pi * 3 * x + 1.0) * np.cos(2 * np.pi * 2 * y)
    g = 120 + 45 * patron + 30 * grande
    b = 90 + 35 * patron - 20 * grande
    r = 30 + 10 * grande
    return np.clip(np.dstack([r, g, b]) + 0.5, 0, 255).astype(np.uint8)


def con_objeto(fondo, color=ROJO, semilla=1):
    """Pega una silueta de color saturado (con algo de textura) sobre el fondo."""
    h, w = fondo.shape[:2]
    m = (mascara_zona(Zona.desde_puntos("poligono", SILUETA, pluma=0), h, w) > 0.5)
    rng = np.random.default_rng(semilla)
    tex = rng.integers(-15, 16, (h, w, 1))
    objeto = np.clip(np.array(color)[None, None, :] + tex, 0, 255)
    salida = fondo.copy()
    salida[m] = objeto[m]
    return salida


def energia_alta(img, sel):
    """Energía del detalle fino (laplaciano) en los píxeles elegidos."""
    gris = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32)
    return float(np.abs(cv2.Laplacian(gris, cv2.CV_32F))[sel].mean())


def distancia_al_objeto(m):
    return cv2.distanceTransform((m < 0.5).astype(np.uint8), cv2.DIST_L2, 5)


class PruebasDesenfoque(unittest.TestCase):
    def setUp(self):
        limpiar_cache()
        self.w, self.h = 800, 600
        self.zona = Zona.desde_puntos("poligono", SILUETA, pluma=3)
        self.fondo = fondo_textura(self.w, self.h)
        self.img = con_objeto(self.fondo)
        self.m = mascara_zona(self.zona, self.h, self.w)
        self.dist = distancia_al_objeto(self.m)

    def test_objeto_intacto(self):
        out = desenfocar_fondo(self.img, self.m, 50, 25, True)
        self.assertEqual(out.shape, self.img.shape)
        self.assertEqual(out.dtype, np.uint8)
        adentro = self.m >= 0.999
        self.assertGreater(int(adentro.sum()), 10000)
        self.assertTrue(np.array_equal(out[adentro], self.img[adentro]))
        # En el borde suave, casi igual (se mezcla con el fondo desenfocado).
        borde = (self.m > 0.9) & ~adentro
        self.assertLess(float(np.abs(out[borde].astype(int) - self.img[borde]).mean()), 25)

    def test_fondo_pierde_detalle(self):
        out = desenfocar_fondo(self.img, self.m, 35, 0, False)
        lejos = self.dist > 40
        antes, despues = energia_alta(self.img, lejos), energia_alta(out, lejos)
        # (el disco deja pasar algo de detalle en sus lóbulos laterales, como un lente real)
        self.assertLess(despues, antes * 0.25, f"detalle fino {antes:.1f} → {despues:.1f}")
        # El brillo medio del fondo casi no cambia (no se oscurece ni se lava).
        self.assertLess(abs(float(out[lejos].mean()) - float(self.img[lejos].mean())), 6)

    def test_sin_halo(self):
        radio = radio_desenfoque(50, max(self.w, self.h))
        banda = (self.dist > 2) & (self.dist < radio)
        out = desenfocar_fondo(self.img, self.m, 50, 0, False)
        # Con un objeto azul en vez de rojo, el fondo cerca del borde debe dar lo mismo.
        out_azul = desenfocar_fondo(con_objeto(self.fondo, (20, 40, 230)), self.m, 50, 0, False)
        dif = np.abs(out[banda].astype(int) - out_azul[banda]).mean(axis=0)
        self.assertLess(float(dif.max()), 1.0, f"el color del objeto se derrama: {dif}")
        # El rojo del fondo pegado al objeto no sube respecto del fondo lejano.
        lejos = self.dist > 3 * radio
        rojo_banda, rojo_lejos = float(out[banda][:, 0].mean()), float(out[lejos][:, 0].mean())
        self.assertLess(rojo_banda - rojo_lejos, 4.0)
        # Control: un desenfoque ingenuo (gaussiano de toda la foto) sí deja halo rojo.
        m3 = self.m[..., None]
        ingenuo = (self.img * m3 + cv2.GaussianBlur(self.img, (0, 0), radio / 2) * (1 - m3)).astype(np.uint8)
        self.assertGreater(float(ingenuo[banda][:, 0].mean()) - rojo_lejos, 15.0)

    def test_borde_no_se_oscurece(self):
        # Fondo liso: desenfocado tiene que seguir liso hasta el contorno.
        liso = np.zeros_like(self.fondo)
        liso[:] = (60, 150, 100)
        out = desenfocar_fondo(con_objeto(liso), self.m, 60, 0, False)
        afuera = self.dist > 2
        self.assertLess(float(np.abs(out[afuera].astype(int) - (60, 150, 100)).max()), 2)

    def test_intensidad_escala(self):
        lejos = self.dist > 60
        energias = [energia_alta(desenfocar_fondo(self.img, self.m, i, 0, False), lejos) for i in (10, 30, 60, 100)]
        for a, b in zip(energias, energias[1:]):
            self.assertLess(b, a, f"más intensidad debería borrar más detalle: {energias}")
        self.assertTrue(np.array_equal(desenfocar_fondo(self.img, self.m, 0, 25, True), self.img))

    def test_independiente_de_la_resolucion(self):
        grande_fondo = fondo_textura(1600, 1200)
        grande = con_objeto(grande_fondo)
        m_grande = mascara_zona(self.zona, 1200, 1600)
        for kw in (dict(transicion=0, profundidad=False), dict(transicion=40, profundidad=True)):
            with self.subTest(**kw):
                chica = desenfocar_fondo(self.img, self.m, 40, **kw)
                reducida = cv2.resize(desenfocar_fondo(grande, m_grande, 40, **kw), (self.w, self.h),
                                      interpolation=cv2.INTER_AREA)
                fondo = self.dist > 6
                dif = float(np.abs(reducida[fondo].astype(int) - chica[fondo]).mean())
                efecto = float(np.abs(chica[fondo].astype(int) - self.img[fondo]).mean())
                self.assertLess(dif, 3.0)
                self.assertLess(dif, efecto * 0.2, f"diferencia {dif:.2f} vs efecto {efecto:.2f}")

    def test_transicion_y_profundidad(self):
        cerca = (self.dist > 2) & (self.dist < 15)
        sin = energia_alta(desenfocar_fondo(self.img, self.m, 40, 0, False), cerca)
        con = energia_alta(desenfocar_fondo(self.img, self.m, 40, 100, False), cerca)
        self.assertGreater(con, sin * 1.5, "con transición, lo pegado al objeto se desenfoca menos")
        prof = desenfocar_fondo(self.img, self.m, 25, 0, True)
        cerca = (self.dist > 10) & (self.dist < 40)
        lejos = self.dist > 200
        self.assertGreater(energia_alta(prof, cerca) / energia_alta(self.img, cerca),
                           energia_alta(prof, lejos) / energia_alta(self.img, lejos) * 1.5)

    def test_entrada_no_se_modifica(self):
        copia, m_copia = self.img.copy(), self.m.copy()
        desenfocar_fondo(self.img, self.m, 60, 50, True)
        desenfocar_zona(self.img, self.zona, 60, 50, True)
        self.assertTrue(np.array_equal(self.img, copia))
        self.assertTrue(np.array_equal(self.m, m_copia))

    def test_zona_cache_y_recorte(self):
        a = desenfocar_zona(self.img, self.zona, 40, 25, False)
        self.assertIs(desenfocar_zona(self.img, self.zona, 40, 25, False), a)  # de la caché
        self.assertFalse(a.flags.writeable)
        self.assertIsNot(desenfocar_zona(self.img, self.zona, 41, 25, False), a)
        # Con recorte, el radio sigue siendo relativo a la foto original y la zona no se mueve.
        r = Recorte(0.2, 0.1, 0.8, 0.9)
        recortada = np.ascontiguousarray(aplicar_recorte(self.img, r))
        con_recorte = desenfocar_zona(recortada, self.zona, 40, 0, False, r)
        completa_recortada = aplicar_recorte(desenfocar_zona(self.img, self.zona, 40, 0, False), r)
        hh, ww = recortada.shape[:2]
        centro = (slice(40, hh - 40), slice(40, ww - 40))  # lejos del borde del recorte
        dif = float(np.abs(con_recorte[centro].astype(int) - completa_recortada[centro]).mean())
        self.assertLess(dif, 1.5)


class PruebasEstadoFondo(unittest.TestCase):
    def test_estado_viejo_compatible_e_historial(self):
        from celular_natural.ui.fondo import FONDO_INICIAL, completar_estado
        from celular_natural.ui.historial import describir_cambio
        zona = Zona.desde_puntos("poligono", SILUETA)
        self.assertEqual(completar_estado((None, True)), FONDO_INICIAL)
        self.assertEqual(completar_estado(None), FONDO_INICIAL)
        viejo = {"recorte": None, "fondo": (None, True)}
        nuevo = {"recorte": None, "fondo": (zona, True, "desenfocado", 35, 25, False)}
        self.assertEqual(describir_cambio(viejo, nuevo), "Fondo desenfocado (objeto marcado)")
        self.assertEqual(describir_cambio(viejo, {"recorte": None, "fondo": (zona, True)}),
                         "Fondo quitado (objeto marcado)")
        mas = {"recorte": None, "fondo": (zona, True, "desenfocado", 60, 25, False)}
        self.assertEqual(describir_cambio(nuevo, mas), "Desenfoque de fondo: intensidad 35 → 60")
        prof = {"recorte": None, "fondo": (zona, True, "desenfocado", 35, 25, True)}
        self.assertEqual(describir_cambio(nuevo, prof), "Profundidad gradual activada")
        transp = {"recorte": None, "fondo": (zona, True, "transparente", 35, 25, False)}
        self.assertEqual(describir_cambio(nuevo, transp), "Fondo: transparente")
        self.assertEqual(describir_cambio(nuevo, viejo), "Fondo restaurado")


if __name__ == "__main__":
    unittest.main()
