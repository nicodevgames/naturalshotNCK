# NaturalShot con un link (navegador + descargas)

Un solo link con usuario y contraseña, por ejemplo `https://162-243-162-154.sslip.io`, con dos opciones:

- **Usar en el navegador:** NaturalShot corre en el servidor y se ve en una pestaña (Xpra). No se instala nada.
  Los archivos se suben a *Entradas* y lo exportado se guarda en *Exportados*, desde la misma página.
- **Descargar para tu compu:** el programa nativo de Windows o Mac, de la última versión que publicó
  `.github/workflows/compilar.yml`. La página marca el de tu compu. El repo sigue privado: el portal baja los
  archivos con su token y nunca lo muestra.

## Instalar (una sola vez, en el servidor, como root)

1. En GitHub, crear un token: *Settings › Developer settings › Fine-grained tokens › Generate new token*,
   repositorio `nicodevgames/naturalshotNCK`, permiso **Contents: Read-only**.
2. En el servidor:

```bash
read -rsp "Token de GitHub: " T; echo; curl -fsSL -H "Authorization: Bearer $T" -H "Accept: application/vnd.github.raw" https://api.github.com/repos/nicodevgames/naturalshotNCK/contents/servidor/instalar.sh -o /root/instalar-naturalshot.sh && GITHUB_TOKEN="$T" bash /root/instalar-naturalshot.sh
```

Pide un usuario y una contraseña para el link, instala Docker si falta, baja el código, levanta todo con HTTPS
(Let's Encrypt, por `sslip.io`) y deja un timer que cada 10 minutos trae los cambios de `main` y reconstruye.

Para cambiar la contraseña: `CAMBIAR_CLAVE=1 bash /root/instalar-naturalshot.sh`.

## Qué queda en el servidor

| Qué | Dónde |
|---|---|
| El código | `/opt/naturalshot` |
| Configuración (token, usuario, hash de la contraseña) | `/srv/naturalshot/config/` (solo root) |
| Entradas y Exportados | `/srv/naturalshot/datos/` |
| Contenedores | `app` (NaturalShot + Xpra), `portal` (la página), `caddy` (HTTPS y contraseña) |

Registros: `docker compose -f /opt/naturalshot/servidor/docker-compose.yml --env-file /srv/naturalshot/config/compose.env logs -f`

## A tener en cuenta

- En el navegador trabaja el servidor (CPU), no la compu de quien entra: fotos bien, videos largos más lentos.
  Conviene un droplet de 4 GB de RAM y 2 CPU o más.
- Es una sola sesión: si entran dos personas a la vez, ven la misma pantalla.
- Para trabajar todos los días, el programa nativo es más rápido.
