"""Pruebas de las actualizaciones automáticas (``celular_natural/actualizador.py`` y su interfaz).

* Comparación de versiones y validación del manifiesto (``version.json``).
* SHA-256 y descarga contra un servidor HTTP local que imita a GitHub
  (``servidor_github_falso.py``): la redirección del asset a la URL "firmada" de otro
  host **no** lleva el encabezado ``Authorization``.
* Device flow: ``authorization_pending``, ``slow_down``, ``expired_token``,
  ``access_denied``, cancelar y cortes de red.
* Sesión cifrada con DPAPI (ida y vuelta, archivo sin el token en texto plano) y
  renovación con el refresh token.
* "Sin internet": no hay errores visibles, solo una línea en el registro.
* Paquete: descompresión segura y validación de NaturalShot.exe con _internal.
* Script de instalación: solo toca la carpeta de instalación indicada; se ejecuta de
  verdad con PowerShell (instala, y con una falla simulada restaura el respaldo).
* Interfaz: el banner (nueva versión, conectar, sin acceso), "Más tarde", "No avisar de
  esta versión" y el diálogo de conexión.

Usan un APPDATA y un .ini temporales: no tocan la sesión, el registro ni las
preferencias del usuario.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
# Las pruebas del actualizador corren en cualquier sistema (en la app real, solo en Windows).
os.environ.setdefault("NATURALSHOT_ACTUALIZAR_EN_CUALQUIERA", "1")
if "NATURALSHOT_CONFIG" not in os.environ:  # como en test_modo_facil: nunca el registro del usuario
    import atexit
    _CARPETA_CONFIG = tempfile.mkdtemp(prefix="naturalshot_config_")
    atexit.register(shutil.rmtree, _CARPETA_CONFIG, True)
    os.environ["NATURALSHOT_CONFIG"] = os.path.join(_CARPETA_CONFIG, "preferencias.ini")

from celular_natural import __version__  # noqa: E402
from celular_natural import actualizador as act  # noqa: E402
from celular_natural.motor import Cancelado  # noqa: E402
from servidor_github_falso import ServidorGitHubFalso, manifiesto, zip_de_prueba  # noqa: E402

TOKEN = "ghu_tokenDePrueba123456"
# La "versión nueva" de las pruebas de interfaz: una más que la de la app (publicar.py sube
# __version__ antes de correr las pruebas, así que no puede ser un número fijo).
_A, _B, _C = act.interpretar_version(__version__)
NUEVA = f"{_A}.{_B}.{_C + 1}"
VARIABLES = ("APPDATA", act.VAR_API, act.VAR_LOGIN, act.VAR_CLIENT_ID, act.VAR_AUTO, act.VAR_FALLA, act.VAR_PUBLICO)


def _puerto_cerrado() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _ConEntorno(unittest.TestCase):
    """APPDATA temporal y las URL de GitHub apuntando al servidor falso."""

    def setUp(self):
        self._entorno = {k: os.environ.get(k) for k in VARIABLES}
        self.carpeta = Path(tempfile.mkdtemp(prefix="ns_act_"))
        os.environ["APPDATA"] = str(self.carpeta / "appdata")
        os.environ[act.VAR_CLIENT_ID] = "Iv23liPrueba"
        os.environ[act.VAR_PUBLICO] = "0"  # casi todas las pruebas son del repositorio privado (con cuenta)
        os.environ.pop(act.VAR_AUTO, None)
        os.environ.pop(act.VAR_FALLA, None)
        self.servidor = ServidorGitHubFalso(TOKEN)
        self.servidor.iniciar()
        os.environ[act.VAR_API] = self.servidor.base
        os.environ[act.VAR_LOGIN] = self.servidor.base

    def tearDown(self):
        self.servidor.detener()
        for k, v in self._entorno.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.carpeta, ignore_errors=True)

    def conectar(self, token=TOKEN, **kw) -> act.Sesion:
        sesion = act.Sesion(token=token, **kw)
        act.guardar_sesion(sesion)
        return sesion

    def log(self) -> str:
        ruta = act.archivo_log()
        return ruta.read_text(encoding="utf-8") if ruta.exists() else ""


# ====================================================================== versiones
class PruebasVersiones(unittest.TestCase):
    def test_comparacion_semantica(self):
        self.assertTrue(act.es_mas_nueva("1.10.0", "1.9.0"))
        self.assertTrue(act.es_mas_nueva("2.0.0", "1.99.99"))
        self.assertTrue(act.es_mas_nueva("1.0.1", "1.0.0"))
        self.assertTrue(act.es_mas_nueva("v1.2.0", "1.1.9"))
        self.assertFalse(act.es_mas_nueva("1.0.0", "1.0.0"))
        self.assertFalse(act.es_mas_nueva("1.9.0", "1.10.0"))

    def test_versiones_invalidas(self):
        for mala in ("1.0", "1.0.0.0", "1.0.x", "", "v", "1.0.0-beta", " ", None, 1.0):
            with self.assertRaises(ValueError, msg=repr(mala)):
                act.interpretar_version(mala)
        self.assertEqual(act.interpretar_version(" v3.2.1 "), (3, 2, 1))

    def test_version_actual_valida(self):
        act.interpretar_version(__version__)


# ====================================================================== manifiesto
class PruebasPlataforma(unittest.TestCase):
    def test_actualizacion_automatica_solo_en_windows(self):
        """En Mac la app anda igual, pero las versiones nuevas se bajan desde Pyro."""
        from unittest import mock
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NATURALSHOT_ACTUALIZAR_EN_CUALQUIERA", None)
            with mock.patch.object(act.sys, "platform", "win32"):
                self.assertTrue(act.plataforma_con_actualizaciones())
            with mock.patch.object(act.sys, "platform", "darwin"):
                self.assertFalse(act.plataforma_con_actualizaciones())
                os.environ["NATURALSHOT_ACTUALIZAR_EN_CUALQUIERA"] = "1"
                self.assertTrue(act.plataforma_con_actualizaciones())


class PruebasManifiesto(unittest.TestCase):
    BASE = {"version": "1.1.0", "fecha": "2026-10-13", "notas": ["Uno", "Dos"], "zip": "NaturalShot-PRO.zip",
            "sha256": "a" * 64, "tamano": 117000000, "minima": "1.0.0"}

    def test_valido(self):
        m = act.leer_manifiesto(json.dumps(self.BASE).encode("utf-8"))
        self.assertEqual((m.version, m.zip, m.sha256, m.tamano, m.notas, m.minima),
                         ("1.1.0", "NaturalShot-PRO.zip", "a" * 64, 117000000, ("Uno", "Dos"), "1.0.0"))

    def test_version_obligatoria(self):
        """NS-103.6: ``obligatoria`` es opcional (0.0.0 = ninguna) y se valida como versión."""
        self.assertEqual(act.leer_manifiesto(self.BASE).obligatoria, "0.0.0")
        self.assertEqual(act.leer_manifiesto(dict(self.BASE, obligatoria="v1.1.0")).obligatoria, "1.1.0")
        with self.assertRaises(act.ManifiestoInvalido):
            act.leer_manifiesto(dict(self.BASE, obligatoria="pronto"))

    def test_zip_como_url_y_campos_opcionales(self):
        datos = dict(self.BASE, zip="https://github.com/x/y/releases/download/v1.1.0/NaturalShot-PRO.zip",
                     sha256="A" * 64)
        del datos["notas"], datos["minima"], datos["fecha"]
        m = act.leer_manifiesto(datos)
        self.assertEqual((m.zip, m.sha256, m.notas, m.minima), ("NaturalShot-PRO.zip", "a" * 64, (), "0.0.0"))

    def test_campos_faltantes(self):
        for campo in ("version", "zip", "sha256", "tamano"):
            datos = dict(self.BASE)
            del datos[campo]
            with self.assertRaises(act.ManifiestoInvalido) as ctx:
                act.leer_manifiesto(datos)
            self.assertIn(campo, str(ctx.exception))

    def test_valores_invalidos(self):
        malos = [dict(self.BASE, version="1.1"), dict(self.BASE, version="uno"), dict(self.BASE, minima="x"),
                 dict(self.BASE, sha256="abc"), dict(self.BASE, sha256="g" * 64), dict(self.BASE, tamano=0),
                 dict(self.BASE, tamano="117"), dict(self.BASE, tamano=True), dict(self.BASE, notas=[1, 2]),
                 dict(self.BASE, zip=""), dict(self.BASE, zip="paquete.exe"), dict(self.BASE, zip="a\\b.zip"),
                 [1, 2, 3]]
        for datos in malos:
            with self.assertRaises(act.ManifiestoInvalido, msg=repr(datos)):
                act.leer_manifiesto(datos)
        for crudo in (b"{no es json", b"\xff\xfe", b"null"):
            with self.assertRaises(act.ManifiestoInvalido):
                act.leer_manifiesto(crudo)


# ====================================================================== SHA-256, red y descarga
class PruebasDescarga(_ConEntorno):
    def test_sha256_de_archivo(self):
        ruta = self.carpeta / "x.bin"
        datos = os.urandom(3 * 1024 * 1024 + 17)
        ruta.write_bytes(datos)
        self.assertEqual(act.sha256_de(ruta), hashlib.sha256(datos).hexdigest())

    def test_busca_y_descarga_sin_reenviar_authorization(self):
        datos = zip_de_prueba()
        self.servidor.publicar("1.0.1", datos, notas=["Novedad A", "Novedad B"])
        self.conectar()
        novedad = act.buscar_actualizacion("1.0.0")
        self.assertIsNotNone(novedad)
        self.assertEqual((novedad.version, novedad.id_zip, novedad.tamano_zip, novedad.instalable),
                         ("1.0.1", 22, len(datos), True))
        self.assertEqual(novedad.manifiesto.notas, ("Novedad A", "Novedad B"))
        avances = []
        destino = self.carpeta / "bajada"
        destino.mkdir()
        archivo = act.descargar_paquete(novedad, destino, lambda h, t: avances.append((h, t)))
        self.assertEqual(archivo.read_bytes(), datos)
        self.assertTrue(avances and avances[-1] == (len(datos), len(datos)))
        # La API recibió el token y los encabezados de GitHub…
        latest = self.servidor.pedidos_a("/releases/latest")[0]["encabezados"]
        self.assertEqual(latest["authorization"], f"Bearer {TOKEN}")
        self.assertEqual(latest["accept"], "application/vnd.github+json")
        self.assertEqual(latest["x-github-api-version"], "2022-11-28")
        for p in self.servidor.pedidos_a("/releases/assets/"):
            self.assertEqual(p["encabezados"]["authorization"], f"Bearer {TOKEN}")
            self.assertEqual(p["encabezados"]["accept"], "application/octet-stream")
        # …y la URL firmada (otro host) no: si lo hubiera recibido, habría respondido 400.
        firmados = self.servidor.pedidos_a("/firmado/")
        self.assertEqual(len(firmados), 2)  # version.json y el zip
        for p in firmados:
            self.assertNotEqual(p["host"], f"127.0.0.1:{self.servidor.puerto}")  # otro host
            self.assertNotIn("authorization", p["encabezados"])
        self.assertEqual(self.servidor.violaciones, [])
        self.assertNotIn(TOKEN, self.log())

    def test_al_dia_y_minima(self):
        self.servidor.publicar("1.0.0", zip_de_prueba())
        self.conectar()
        self.assertIsNone(act.buscar_actualizacion("1.0.0"))
        self.assertIsNone(act.buscar_actualizacion("1.2.0"))
        self.servidor.publicar("2.0.0", zip_de_prueba(), minima="1.5.0")
        self.assertFalse(act.buscar_actualizacion("1.0.0").instalable)
        self.assertTrue(act.buscar_actualizacion("1.5.0").instalable)

    def test_version_obligatoria(self):
        """NS-103.6: debajo de ``obligatoria`` la novedad no se puede omitir; arriba, sí."""
        self.conectar()
        self.servidor.publicar("2.0.0", zip_de_prueba(), obligatoria="1.8.0")
        self.assertTrue(act.buscar_actualizacion("1.5.0").obligatoria)
        self.assertFalse(act.buscar_actualizacion("1.8.0").obligatoria)
        self.servidor.publicar("2.0.1", zip_de_prueba())
        self.assertFalse(act.buscar_actualizacion("1.0.0").obligatoria)

    def test_sha_incorrecto_no_deja_nada(self):
        self.servidor.publicar("1.0.1", zip_de_prueba(), sha="0" * 64)
        self.conectar()
        novedad = act.buscar_actualizacion("1.0.0")
        trabajo = self.carpeta / "trabajo"
        trabajo.mkdir()
        with self.assertRaises(act.HashIncorrecto) as ctx:
            act.preparar_paquete(novedad, trabajo)
        self.assertIn("SHA-256", str(ctx.exception))
        self.assertFalse(trabajo.exists())  # se borró lo bajado
        self.assertIn("SHA-256 no coincide", self.log())

    def test_manifiesto_publicado_invalido(self):
        self.servidor.publicar("1.0.1", zip_de_prueba(), manifiesto_crudo=b'{"version": "1.0.1"}')
        self.conectar()
        with self.assertRaises(act.ManifiestoInvalido):
            act.buscar_actualizacion("1.0.0")
        datos = zip_de_prueba()
        self.servidor.publicar("1.0.1", datos)
        self.servidor.release["assets"][1]["size"] = 5  # no coincide con el manifiesto
        with self.assertRaises(act.ManifiestoInvalido):
            act.buscar_actualizacion("1.0.0")

    def test_cancelar_descarga(self):
        self.servidor.publicar("1.0.1", zip_de_prueba(extra={"NaturalShot PRO/_internal/grande.bin": os.urandom(2_000_000)}))
        self.conectar()
        novedad = act.buscar_actualizacion("1.0.0")
        trabajo = self.carpeta / "trabajo2"
        trabajo.mkdir()
        with self.assertRaises(Cancelado):
            act.preparar_paquete(novedad, trabajo, cancelado=lambda: True)
        self.assertFalse(trabajo.exists())

    def test_errores_de_acceso(self):
        self.servidor.publicar("1.0.1", zip_de_prueba())
        with self.assertRaises(act.SinSesion):
            act.buscar_actualizacion("1.0.0")
        self.conectar(token="ghu_tokenQueNoExiste000")
        with self.assertRaises(act.SesionVencida):  # 401 sin refresh token
            act.buscar_actualizacion("1.0.0")
        self.conectar()
        for codigo in (404, 403):
            self.servidor.estado_release = codigo
            with self.assertRaises(act.SinAcceso) as ctx:
                act.buscar_actualizacion("1.0.0")
            self.assertIn("Pedile al dueño que te invite", str(ctx.exception))
        self.servidor.estado_release = None
        self.servidor.limite_agotado = True  # 403 por límite de consultas: no es "sin acceso"
        with self.assertRaises(act.SinConexion):
            act.buscar_actualizacion("1.0.0")

    def test_renueva_con_refresh_token(self):
        self.servidor.publicar("1.0.1", zip_de_prueba())
        self.servidor.refresh_validos.add("ghr_refreshViejo1234567")
        # Vencido por la hora: se renueva antes de consultar.
        self.conectar(token="ghu_vencidoPorHora00000", refresco="ghr_refreshViejo1234567",
                      vence=time.time() - 10, refresco_vence=time.time() + 1000)
        self.assertEqual(act.buscar_actualizacion("1.0.0").version, "1.0.1")
        guardada = act.cargar_sesion()
        self.assertEqual(guardada.token, self.servidor.token_nuevo + "R")
        self.assertGreater(guardada.vence, time.time() + 28000)
        renovar = [p for p in self.servidor.pedidos_a("/login/oauth/access_token")]
        self.assertIn("grant_type=refresh_token", renovar[0]["cuerpo"])
        self.assertNotIn("client_secret", renovar[0]["cuerpo"])
        # 401 aunque la hora diga que vale (revocado): renueva y reintenta una vez.
        self.servidor.refresh_validos.add("ghr_otroRefresh12345678")
        self.conectar(token="ghu_revocado000000000", refresco="ghr_otroRefresh12345678",
                      vence=time.time() + 5000, refresco_vence=time.time() + 1000)
        self.assertEqual(act.buscar_actualizacion("1.0.0").version, "1.0.1")
        # Refresh token vencido: hay que volver a conectar.
        self.conectar(token="ghu_vencido2222222222", refresco="ghr_noValido", vence=time.time() - 1,
                      refresco_vence=time.time() + 1000)
        with self.assertRaises(act.SesionVencida):
            act.buscar_actualizacion("1.0.0")

    def test_sin_internet_es_silencioso(self):
        os.environ[act.VAR_API] = f"http://127.0.0.1:{_puerto_cerrado()}"
        self.conectar()
        inicio = time.monotonic()
        with self.assertRaises(act.SinConexion):
            act.buscar_actualizacion("1.0.0")
        self.assertLess(time.monotonic() - inicio, 15)

    def test_redireccion_insegura_se_rechaza(self):
        self.assertTrue(act._redireccion_permitida("https://objects.githubusercontent.com/x"))
        self.assertTrue(act._redireccion_permitida("http://localhost:8000/x"))
        self.assertFalse(act._redireccion_permitida("http://ejemplo.com/x"))
        self.assertFalse(act._redireccion_permitida("file:///C:/Windows/win.ini"))


# ====================================================================== device flow
class PruebasRepositorioPublico(_ConEntorno):
    """Con un repositorio público se busca y se baja sin cuenta de GitHub (y sin mandar Authorization)."""

    def setUp(self):
        super().setUp()
        os.environ[act.VAR_PUBLICO] = "1"
        os.environ[act.VAR_CLIENT_ID] = act.CLIENT_ID  # sin GitHub App: igual queda configurado
        self.servidor.publico = True

    def test_busca_y_descarga_sin_cuenta(self):
        self.assertTrue(act.configurado())
        self.assertFalse(act.necesita_conectar())
        datos = zip_de_prueba()
        self.servidor.publicar("1.0.1", datos)
        novedad = act.buscar_actualizacion("1.0.0")
        self.assertEqual(novedad.version, "1.0.1")
        destino = self.carpeta / "bajada"
        destino.mkdir()
        self.assertEqual(act.descargar_paquete(novedad, destino).read_bytes(), datos)
        self.assertTrue(self.servidor.pedidos)
        for p in self.servidor.pedidos:
            self.assertNotIn("authorization", p["encabezados"])

    def test_privado_sin_sesion_pide_conectar(self):
        os.environ[act.VAR_PUBLICO] = "0"
        self.assertTrue(act.necesita_conectar())
        with self.assertRaises(act.SinSesion):
            act.buscar_actualizacion("1.0.0")


class PruebasDeviceFlow(_ConEntorno):
    def codigo(self, intervalo=5, expira=900):
        self.servidor.respuesta_codigo = dict(self.servidor.respuesta_codigo, interval=intervalo, expires_in=expira)
        return act.pedir_codigo()

    def test_pending_slow_down_y_token(self):
        self.servidor.respuestas_token = [{"error": "authorization_pending"}, {"error": "slow_down", "interval": 10},
                                          {"error": "authorization_pending"}]
        codigo = self.codigo()
        self.assertEqual(codigo.codigo_usuario, "WDJB-MJHT")
        self.assertNotIn("dc_secreto", repr(codigo))
        esperas = []
        sesion = act.esperar_autorizacion(codigo, dormir=esperas.append)
        self.assertEqual(esperas, [5, 5, 10, 10])  # respeta interval y el intervalo nuevo de slow_down
        self.assertEqual((sesion.token, sesion.refresco, sesion.usuario),
                         (self.servidor.token_nuevo, self.servidor.refresh_nuevo, "editora-prueba"))
        self.assertGreater(sesion.vence, time.time() + 28000)
        self.assertNotIn(sesion.token, repr(sesion))
        sondeos = self.servidor.pedidos_a("/login/oauth/access_token")
        self.assertEqual(len(sondeos), 4)
        self.assertIn("grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code", sondeos[0]["cuerpo"])
        self.assertIn("client_id=Iv23liPrueba", sondeos[0]["cuerpo"])
        self.assertTrue(all(p["encabezados"]["accept"] == "application/json" for p in sondeos))

    def test_slow_down_sin_intervalo_suma_cinco(self):
        self.servidor.respuestas_token = [{"error": "slow_down"}]
        esperas = []
        act.esperar_autorizacion(self.codigo(), dormir=esperas.append)
        self.assertEqual(esperas, [5, 10])

    def test_expirado_denegado_y_mal_configurado(self):
        for respuesta, error in (({"error": "expired_token"}, act.CodigoVencido),
                                 ({"error": "token_expired"}, act.CodigoVencido),
                                 ({"error": "access_denied"}, act.AccesoDenegado),
                                 ({"error": "device_flow_disabled"}, act.ConfiguracionInvalida),
                                 ({"error": "incorrect_client_credentials"}, act.ConfiguracionInvalida)):
            self.servidor.respuestas_token = [{"error": "authorization_pending"}, respuesta]
            with self.assertRaises(error, msg=respuesta):
                act.esperar_autorizacion(self.codigo(), dormir=lambda _s: None)

    def test_vence_por_tiempo_y_cancelar(self):
        self.servidor.respuestas_token = [{"error": "authorization_pending"}] * 50
        reloj = iter(range(0, 10000, 400))
        with self.assertRaises(act.CodigoVencido):
            act.esperar_autorizacion(self.codigo(expira=900), dormir=lambda _s: None, reloj=lambda: next(reloj))
        inicio = time.monotonic()
        with self.assertRaises(Cancelado):  # con la espera real, cancelar corta enseguida
            act.esperar_autorizacion(self.codigo(intervalo=30), cancelado=lambda: time.monotonic() - inicio > 0.3)
        self.assertLess(time.monotonic() - inicio, 3)

    def test_corte_de_red_no_corta_la_espera(self):
        codigo = self.codigo()
        base = os.environ[act.VAR_LOGIN]
        llamadas = []

        def dormir(_s):  # el primer sondeo va a un puerto cerrado; después vuelve la red
            llamadas.append(_s)
            os.environ[act.VAR_LOGIN] = f"http://127.0.0.1:{_puerto_cerrado()}" if len(llamadas) == 1 else base

        sesion = act.esperar_autorizacion(codigo, dormir=dormir)
        self.assertEqual(sesion.token, self.servidor.token_nuevo)
        self.assertEqual(len(llamadas), 2)

    def test_sin_configurar(self):
        os.environ[act.VAR_CLIENT_ID] = act.CLIENT_ID  # el valor de relleno
        self.assertFalse(act.configurado())
        with self.assertRaises(act.ConfiguracionInvalida):
            act.pedir_codigo()
        self.assertEqual(self.servidor.pedidos, [])


# ====================================================================== DPAPI y sesión
@unittest.skipUnless(sys.platform == "win32", "DPAPI es de Windows")
class PruebasSesion(_ConEntorno):
    def test_dpapi_ida_y_vuelta(self):
        for datos in (b"hola", os.urandom(5000), "ñandú ✓".encode("utf-8")):
            cifrado = act.proteger(datos)
            self.assertNotEqual(cifrado, datos)
            self.assertNotIn(datos, cifrado)
            self.assertEqual(act.desproteger(cifrado), datos)
        cifrado = bytearray(act.proteger(b"secreto"))
        cifrado[-5] ^= 0xFF
        with self.assertRaises(OSError):
            act.desproteger(bytes(cifrado))

    def test_archivo_de_sesion_cifrado(self):
        sesion = act.Sesion("ghu_secretoSecretoSecreto42", "ghr_refrescoSecreto4242", 123.0, 456.0, "editora")
        act.guardar_sesion(sesion)
        crudo = act.archivo_sesion().read_bytes()
        self.assertEqual(act.archivo_sesion().parent, Path(os.environ["APPDATA"]) / "NaturalShot PRO")
        for secreto in (b"ghu_secretoSecretoSecreto42", b"ghr_refrescoSecreto4242", b"editora"):
            self.assertNotIn(secreto, crudo)
            self.assertNotIn(secreto, crudo.replace(b"\0", b""))  # tampoco en UTF-16
        leida = act.cargar_sesion()
        self.assertEqual((leida.token, leida.refresco, leida.vence, leida.refresco_vence, leida.usuario),
                         (sesion.token, sesion.refresco, 123.0, 456.0, "editora"))
        act.archivo_sesion().write_bytes(crudo[:-10])  # dañado: se ignora, sin errores
        self.assertIsNone(act.cargar_sesion())
        act.borrar_sesion()
        self.assertFalse(act.archivo_sesion().exists())
        self.assertIsNone(act.cargar_sesion())

    def test_registro_sin_secretos(self):
        act.registrar("token ghu_abcdefghijklmnop1234 y Bearer ghu_x1234567890abcdef y "
                      "access_token=gho_zzzzzzzzzzzzzz&refresh_token=ghr_yyyyyyyyyyyy y \"device_code\": \"abc123\"")
        texto = self.log()
        for secreto in ("ghu_abcdefghijklmnop1234", "ghu_x1234567890abcdef", "gho_zzzz", "ghr_yyyy", "abc123"):
            self.assertNotIn(secreto, texto)


# ====================================================================== paquete
class PruebasPaquete(unittest.TestCase):
    def setUp(self):
        self.carpeta = Path(tempfile.mkdtemp(prefix="ns_paq_"))

    def tearDown(self):
        shutil.rmtree(self.carpeta, ignore_errors=True)

    def extraer(self, datos: bytes) -> Path:
        z = self.carpeta / f"p{len(list(self.carpeta.iterdir()))}.zip"
        z.write_bytes(datos)
        return act.extraer_paquete(z, self.carpeta / f"x_{z.stem}")

    def test_carpeta_raiz_con_cualquier_nombre(self):
        for raiz in ("NaturalShot PRO", "Otra carpeta ñ", ""):
            app = self.extraer(zip_de_prueba(raiz))
            self.assertTrue((app / "NaturalShot.exe").is_file() and (app / "_internal").is_dir())
            self.assertEqual(app.name if raiz else "", raiz)

    def test_paquetes_invalidos(self):
        sin_internal = io.BytesIO()
        with zipfile.ZipFile(sin_internal, "w") as z:
            z.writestr("NaturalShot PRO/NaturalShot.exe", b"MZ")
        dos = zip_de_prueba(extra={"Copia/NaturalShot.exe": b"MZ", "Copia/_internal/a": b"a"})
        malicioso = zip_de_prueba(extra={"../afuera.txt": b"no"})
        absoluto = zip_de_prueba(extra={"C:/Windows/x.txt": b"no"})
        for datos in (sin_internal.getvalue(), dos, malicioso, absoluto, b"esto no es un zip"):
            with self.assertRaises(act.PaqueteInvalido):
                self.extraer(datos)
        self.assertFalse((self.carpeta / "afuera.txt").exists())


# ====================================================================== script de instalación
class PruebasScript(_ConEntorno):
    """El script solo toca la carpeta de instalación; se ejecuta de verdad con PowerShell."""

    def armar(self, nombre_raiz="Mis cosas O’Brien's (ñ) & más"):
        self.raiz = self.carpeta / nombre_raiz
        self.inst = self.raiz / "NaturalShot PRO"
        (self.inst / "_internal" / "viejo").mkdir(parents=True)
        (self.inst / "NaturalShot.exe").write_bytes(b"exe viejo")
        (self.inst / "_internal" / "base_library.zip").write_bytes(b"viejo")
        (self.inst / "_internal" / "viejo" / "solo_en_la_vieja.txt").write_text("v")
        (self.inst / "foto_de_la_usuaria.jpg").write_bytes(b"suya")  # no es de la app: no se toca
        (self.raiz / "vecino.txt").write_text("afuera")
        self.trabajo = act.nueva_carpeta_trabajo()
        self.addCleanup(shutil.rmtree, self.trabajo, True)
        z = self.trabajo / act.NOMBRE_ZIP
        z.write_bytes(zip_de_prueba(contenido_exe=b"exe nuevo"))
        nueva = act.extraer_paquete(z, self.trabajo / "nueva")
        z.unlink()
        datos = zip_de_prueba()
        novedad = act.Novedad(act.leer_manifiesto(manifiesto("1.0.1", datos)), "v1.0.1", "", 22, len(datos))
        self.paquete = act.PaqueteListo(novedad, self.trabajo, nueva,
                                        tuple(sorted(p.name for p in nueva.iterdir() if p.is_file())))

    def pid_terminado(self) -> int:
        p = subprocess.Popen(["cmd", "/c", "exit"], creationflags=0x08000000)
        p.wait()
        return p.pid

    def correr(self, script: Path) -> subprocess.CompletedProcess:
        return subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                               "-File", str(script)], capture_output=True, text=True, timeout=120,
                              creationflags=0x08000000)

    def test_contenido_solo_toca_la_instalacion(self):
        self.armar()
        script = act.generar_script(self.paquete, self.inst, 4242, "1.0.0", reabrir=False)
        texto = script.read_text(encoding="utf-8-sig")
        self.assertEqual(script.read_bytes()[:3], b"\xef\xbb\xbf")
        self.assertIn(act.literal_ps(str(self.inst.resolve())), texto)
        self.assertIn("$ProcesoApp = 4242", texto)
        self.assertIn("$Archivos = @('NaturalShot.exe')", texto)  # el LEEME del zip va afuera de la carpeta
        # El espejo (/MIR) solo va contra _internal de la instalación (o desde el respaldo al restaurar).
        mir = [l.strip() for l in texto.splitlines() if "/MIR" in l and not l.lstrip().startswith("#")]
        self.assertEqual(len(mir), 2)
        for linea in mir:
            self.assertIn("(Join-Path $Instalacion '_internal')", linea)
        # Las únicas rutas absolutas son las declaradas arriba (instalación, nueva, trabajo, log y resultado).
        declaradas = {str(self.inst.resolve()), str(self.paquete.nueva.resolve()), str(self.trabajo.resolve()),
                      str(act.archivo_log()), str(act.archivo_resultado()),
                      str(self.trabajo.resolve() / "instalador_iniciado.txt")}
        rutas = {l.split(" = ", 1)[1].strip("'").replace("''", "'").replace("’’", "’")
                 for l in texto.splitlines() if l.startswith("$") and " = '" in l and ":\\" in l}
        self.assertEqual(rutas, declaradas)
        self.assertNotIn("Remove-Item -LiteralPath $Instalacion", texto)
        self.assertIn("$SimularFalla = $false", texto)

    def test_valida_la_instalacion(self):
        self.armar()
        for mala in (self.carpeta, Path(self.carpeta.anchor), self.raiz):
            with self.assertRaises(act.ErrorActualizacion):
                act.generar_script(self.paquete, mala, 1)
        afuera = act.PaqueteListo(self.paquete.novedad, self.trabajo, self.inst, self.paquete.archivos)
        with self.assertRaises(act.PaqueteInvalido):  # la "nueva" tiene que estar en la carpeta de trabajo
            act.generar_script(afuera, self.inst, 1)
        malo = act.PaqueteListo(self.paquete.novedad, self.trabajo, self.paquete.nueva, ("..\\x.exe",))
        with self.assertRaises(act.PaqueteInvalido):
            act.generar_script(malo, self.inst, 1)

    def test_literal_powershell(self):
        self.assertEqual(act.literal_ps("C:\\a b"), "'C:\\a b'")
        self.assertEqual(act.literal_ps("O'Brien’s $x"), "'O''Brien’’s $x'")
        with self.assertRaises(ValueError):
            act.literal_ps("a\nb")

    @unittest.skipUnless(sys.platform == "win32", "PowerShell")
    def test_instala_de_verdad(self):
        self.armar()
        script = act.generar_script(self.paquete, self.inst, self.pid_terminado(), "1.0.0", reabrir=False)
        r = self.correr(script)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.inst / "NaturalShot.exe").read_bytes(), b"exe nuevo")
        internos = sorted(p.relative_to(self.inst / "_internal").as_posix()
                          for p in (self.inst / "_internal").rglob("*") if p.is_file())
        self.assertEqual(internos, ["PySide6/plugins/leeme.txt", "base_library.zip"])  # /MIR: lo viejo se fue
        self.assertEqual((self.inst / "foto_de_la_usuaria.jpg").read_bytes(), b"suya")
        self.assertEqual((self.raiz / "vecino.txt").read_text(), "afuera")
        self.assertFalse(self.trabajo.exists())  # se borraron los temporales (con el script)
        resultado = act.leer_resultado_anterior()
        self.assertEqual((resultado["estado"], resultado["version_nueva"]), ("ok", "1.0.1"))
        self.assertIn("Listo: versión 1.0.1 instalada.", self.log())

    @unittest.skipUnless(sys.platform == "win32", "PowerShell")
    def test_falla_a_mitad_restaura(self):
        self.armar()
        antes = {p.relative_to(self.inst).as_posix(): p.read_bytes() for p in self.inst.rglob("*") if p.is_file()}
        script = act.generar_script(self.paquete, self.inst, self.pid_terminado(), "1.0.0", reabrir=False,
                                    simular_falla=True)
        r = self.correr(script)
        self.assertEqual(r.returncode, 0, r.stderr)
        despues = {p.relative_to(self.inst).as_posix(): p.read_bytes() for p in self.inst.rglob("*") if p.is_file()}
        self.assertEqual(despues, antes)  # todo como estaba
        resultado = act.leer_resultado_anterior()
        self.assertEqual(resultado["estado"], "restaurado")
        self.assertIn("Falla simulada", resultado["detalle"])
        self.assertIn("Respaldo restaurado.", self.log())
        self.assertFalse(self.trabajo.exists())


# ====================================================================== interfaz
def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class PruebasInterfaz(_ConEntorno):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        super().setUp()
        from celular_natural.ui.ventana import VentanaPrincipal
        from celular_natural.ui.modo_facil import configuracion
        configuracion().clear()
        self.ventana = VentanaPrincipal()
        self.ventana.resize(1366, 768)
        self.ventana.show()
        self.ctrl = self.ventana.actualizaciones
        self.informes = []
        self.ctrl._informar = lambda titulo, texto, pagina=False: self.informes.append((titulo, texto))

    def tearDown(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        self.ventana.close()
        self.ventana.deleteLater()
        self.esperar(lambda: False, 0.1)
        # deleteLater() sin un bucle de eventos corriendo no borra nada: se completa el borrado acá.
        # Si no, cada ventana cerrada queda viva hasta el final de la suite (con sus miles de widgets).
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        from celular_natural.ui.modo_facil import configuracion
        configuracion().clear()
        super().tearDown()

    def esperar(self, condicion, segundos=10.0) -> bool:
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            self.app.processEvents()
            if condicion():
                return True
            time.sleep(0.01)
        self.app.processEvents()
        return condicion()

    def test_banner_de_version_nueva(self):
        self.servidor.publicar(NUEVA, zip_de_prueba(), notas=["Aviso de actualizaciones", "Arreglos"])
        self.conectar()
        self.assertFalse(self.ctrl.banner.isVisible())
        self.ctrl.al_iniciar()
        self.assertTrue(self.esperar(lambda: self.ctrl.banner.tipo == "nueva"))
        banner = self.ctrl.banner
        self.assertTrue(banner.isVisible())
        self.assertEqual(banner.titulo.text(), f"Hay una versión nueva ({NUEVA})")
        self.assertEqual(set(banner.botones), {"actualizar", "luego", "omitir"})
        self.assertEqual(banner.botones["actualizar"].text().strip(), "Actualizar ahora")
        self.assertEqual(banner.botones["actualizar"].objectName(), "botonPrimario")
        self.assertTrue(banner.boton_novedades.isVisible())
        banner.boton_novedades.click()
        self.assertTrue(banner.notas.isVisible())
        self.assertIn("Aviso de actualizaciones", banner.notas.text())
        self.assertTrue(self.ctrl.boton_version.property("hayNueva"))
        # Desde el código no se instala: lo explica.
        banner.botones["actualizar"].click()
        self.assertEqual(self.informes[-1][0], "Actualizar a mano")
        # Más tarde: se oculta.
        banner.botones["luego"].click()
        self.assertFalse(banner.isVisible())

    def test_no_avisar_de_esta_version(self):
        from celular_natural.ui.actualizaciones import CLAVE_OMITIR
        from celular_natural.ui.modo_facil import configuracion
        self.servidor.publicar(NUEVA, zip_de_prueba())
        self.conectar()
        self.ctrl.al_iniciar()
        self.assertTrue(self.esperar(lambda: self.ctrl.banner.tipo == "nueva"))
        self.ctrl.banner.botones["omitir"].click()
        self.assertFalse(self.ctrl.banner.isVisible())
        self.assertEqual(configuracion().value(CLAVE_OMITIR), NUEVA)
        self.assertTrue(Path(os.environ["NATURALSHOT_CONFIG"]).exists())  # en el .ini, no en el registro
        self.ctrl._novedad = None
        self.ctrl.buscar(manual=False)  # al iniciar: no vuelve a avisar de esa versión…
        self.assertTrue(self.esperar(lambda: not self.ctrl._buscando))
        self.assertFalse(self.ctrl.banner.isVisible())
        self.ctrl.buscar(manual=True)  # …pero si la persona busca a mano, sí
        self.assertTrue(self.esperar(lambda: self.ctrl.banner.tipo == "nueva"))

    def test_sin_sesion_pide_conectar_y_conecta(self):
        from PySide6.QtCore import Qt
        self.servidor.publicar(NUEVA, zip_de_prueba())
        self.servidor.respuesta_codigo = dict(self.servidor.respuesta_codigo, interval=0.05)
        self.servidor.respuestas_token = [{"error": "authorization_pending"}, {"error": "authorization_pending"}]
        self.ctrl.al_iniciar()
        self.assertEqual(self.ctrl.banner.tipo, "conectar")
        self.assertIn("Conectá tu cuenta de GitHub para recibir actualizaciones", self.ctrl.banner.titulo.text())
        self.ctrl.banner.botones["conectar"].click()
        self.assertIsNotNone(self.ctrl._dialogo)
        self.assertTrue(self.esperar(lambda: self.ctrl._dialogo is not None
                                     and self.ctrl._dialogo.etiqueta_codigo.text() == "WDJB-MJHT"))
        self.assertTrue(self.ctrl._dialogo.boton_copiar.isEnabled())
        self.assertEqual(self.ctrl._dialogo.paso2.textFormat(), Qt.RichText)
        self.assertTrue(self.esperar(lambda: self.ctrl.banner.tipo == "nueva"))
        self.assertIsNone(self.ctrl._dialogo)
        self.assertEqual(act.cargar_sesion().token, self.servidor.token_nuevo)
        self.assertNotIn(self.servidor.token_nuevo, self.log())
        self.assertNotIn(self.servidor.refresh_nuevo, self.log())

    def test_cancelar_conexion(self):
        self.servidor.respuesta_codigo = dict(self.servidor.respuesta_codigo, interval=0.05)
        self.servidor.respuestas_token = [{"error": "authorization_pending"}] * 1000
        self.ctrl.conectar()
        self.assertTrue(self.esperar(lambda: self.ctrl._dialogo.etiqueta_codigo.text() == "WDJB-MJHT"))
        self.ctrl._dialogo.reject()
        self.assertTrue(self.esperar(lambda: self.ctrl._pool.activeThreadCount() == 0, 3))
        self.assertIsNone(act.cargar_sesion())

    def test_sin_acceso_y_sin_internet(self):
        self.servidor.publicar(NUEVA, zip_de_prueba())
        self.conectar()
        self.servidor.estado_release = 404
        self.ctrl.al_iniciar()
        self.assertTrue(self.esperar(lambda: self.ctrl.banner.tipo == "aviso"))
        self.assertIn("no tiene acceso", self.ctrl.banner.titulo.text())
        self.assertIn("Pedile al dueño que te invite", self.ctrl.banner.detalle.text())
        # Sin internet: nada visible, solo el registro.
        self.ctrl.banner.ocultar()
        os.environ[act.VAR_API] = f"http://127.0.0.1:{_puerto_cerrado()}"
        self.ctrl.al_iniciar()
        self.assertTrue(self.esperar(lambda: not self.ctrl._buscando))
        self.assertFalse(self.ctrl.banner.isVisible())
        self.assertEqual(self.informes, [])
        self.assertIn("Búsqueda: SinConexion", self.log())

    def test_resultado_de_la_actualizacion_anterior(self):
        act.archivo_resultado().parent.mkdir(parents=True, exist_ok=True)
        act.archivo_resultado().write_text(json.dumps({"estado": "restaurado", "detalle": "disco lleno",
                                                       "version_nueva": "1.0.1", "version_anterior": "1.0.0"}),
                                           encoding="utf-8")
        os.environ[act.VAR_CLIENT_ID] = act.CLIENT_ID  # sin configurar: no busca nada más
        self.ctrl.al_iniciar()
        self.assertEqual(self.ctrl.banner.tipo, "aviso")
        self.assertIn("seguís con la 1.0.0", self.ctrl.banner.titulo.text())
        self.assertIn("disco lleno", self.ctrl.banner.detalle.text())
        self.assertFalse(act.archivo_resultado().exists())
        self.assertEqual(self.servidor.pedidos, [])

    def test_espera_la_exportacion_y_pregunta_si_hay_cambios(self):
        from unittest import mock
        from PySide6.QtWidgets import QMessageBox
        datos = zip_de_prueba()
        novedad = act.Novedad(act.leer_manifiesto(manifiesto(NUEVA, datos)), f"v{NUEVA}", "", 22, len(datos))
        trabajo = act.nueva_carpeta_trabajo()
        self.addCleanup(shutil.rmtree, trabajo, True)
        self.ctrl._novedad = novedad
        self.ctrl._paquete = act.PaqueteListo(novedad, trabajo, trabajo / "nueva", ("NaturalShot.exe",))
        lanzados = []
        self.ctrl._lanzar_instalador = lambda: lanzados.append(True)
        # 1. Con una exportación en curso, espera (y lo dice en el banner).
        self.ventana._exportando = True
        self.ctrl._instalar_cuando_se_pueda()
        self.assertIn("exportación en curso", self.ctrl.banner.detalle.text())
        self.assertTrue(self.ctrl._timer_exportacion.isActive())
        self.esperar(lambda: False, 1.3)
        self.assertEqual(lanzados, [])
        # 2. Termina la exportación, pero hay fotos con cambios: pregunta. "No" la deja para después.
        self.ventana._exportando = False
        self.ventana._historial.append(("Cambio", self.ventana._historial[0][1]))
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.No) as pregunta:
            self.assertTrue(self.esperar(lambda: pregunta.called, 3))
        self.assertFalse(self.ctrl._timer_exportacion.isActive())
        self.assertEqual(lanzados, [])
        self.assertIn("descargada y lista", self.ctrl.banner.titulo.text())
        # 3. "Reiniciar y actualizar" y "Sí": lanza el instalador.
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            self.ctrl.banner.botones["instalar"].click()
        self.assertEqual(lanzados, [True])

    def test_boton_de_version(self):
        self.assertEqual(self.ctrl.boton_version.text(), f"v{__version__}")
        self.assertTrue(self.ctrl.boton_version.isVisible())
        self.ventana.establecer_modo("editor", guardar=False)
        self.assertTrue(self.ctrl.boton_version.isVisible())  # en los dos modos


if __name__ == "__main__":
    unittest.main()
