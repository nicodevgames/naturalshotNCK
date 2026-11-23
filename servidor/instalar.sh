#!/usr/bin/env bash
# Instala NaturalShot en el navegador + el portal de descargas en este servidor (Ubuntu/Debian), con
# HTTPS y usuario y contraseña. Se puede volver a correr: actualiza y conserva los datos.
#
#   GITHUB_TOKEN=... bash instalar.sh
#
# GITHUB_TOKEN: token fine-grained de GitHub con acceso de SOLO LECTURA (Contents: Read-only) al
# repositorio nicodevgames/naturalshotNCK. Se guarda en /srv/naturalshot/config/servidor.env (solo root).
set -euo pipefail

REPO="${GITHUB_REPO:-nicodevgames/naturalshotNCK}"
DIR=/opt/naturalshot
CONF=/srv/naturalshot/config/servidor.env
say() { printf '\n▶ %s\n' "$*"; }
[ "$(id -u)" = 0 ] || { echo "Correlo como root (sudo -i)."; exit 1; }
mkdir -p /srv/naturalshot/datos/Entradas /srv/naturalshot/datos/Exportados /srv/naturalshot/config
[ -f "$CONF" ] && . "$CONF" || true

say "Datos"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
[ -n "$GITHUB_TOKEN" ] || { read -rsp "Token de GitHub (solo lectura de $REPO): " GITHUB_TOKEN; echo; }
IP=$(curl -fsS4 https://api.ipify.org || hostname -I | awk '{print $1}')
DOMINIO="${DOMINIO:-$(echo "$IP" | tr . -).sslip.io}"
if [ -z "${USUARIO:-}" ] || [ -n "${CAMBIAR_CLAVE:-}" ]; then
  read -rp "Usuario para entrar al link: " USUARIO
  read -rsp "Contraseña (mínimo 10 caracteres): " CLAVE; echo
  [ ${#CLAVE} -ge 10 ] || { echo "La contraseña tiene que tener 10 caracteres o más."; exit 1; }
fi
echo "  Link: https://$DOMINIO  ·  usuario: $USUARIO"

say "Docker"
if ! command -v docker >/dev/null; then curl -fsSL https://get.docker.com | sh; fi
docker compose version >/dev/null

if [ -n "${CLAVE:-}" ]; then
  CLAVE_HASH=$(docker run --rm caddy:2 caddy hash-password --plaintext "$CLAVE")
fi
umask 077
cat > "$CONF" <<CONF
GITHUB_REPO=$REPO
GITHUB_TOKEN=$GITHUB_TOKEN
DOMINIO=$DOMINIO
USUARIO=$USUARIO
CLAVE_HASH='$CLAVE_HASH'
CONF
umask 022

say "Código de NaturalShot"
AUTH="Authorization: Basic $(printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64 -w0)"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" -c http.extraHeader="$AUTH" fetch -q origin main && git -C "$DIR" reset -q --hard origin/main
else
  git -c http.extraHeader="$AUTH" clone -q "https://github.com/$REPO.git" "$DIR"
fi
echo "  Versión: $(git -C "$DIR" log --oneline -1)"

say "Levantando (la primera vez tarda unos minutos)"
bash "$DIR/servidor/env_compose.sh"
docker compose -f "$DIR/servidor/docker-compose.yml" --env-file /srv/naturalshot/config/compose.env up -d --build --remove-orphans

say "Actualización automática (cada 10 minutos, si hay cambios en main)"
install -m 755 "$DIR/servidor/actualizar.sh" /usr/local/bin/naturalshot-actualizar
cat > /etc/systemd/system/naturalshot-actualizar.service <<UNIT
[Unit]
Description=NaturalShot: trae los cambios de main y reconstruye
[Service]
Type=oneshot
ExecStart=/usr/local/bin/naturalshot-actualizar
UNIT
cat > /etc/systemd/system/naturalshot-actualizar.timer <<UNIT
[Unit]
Description=NaturalShot: buscar cambios cada 10 minutos
[Timer]
OnBootSec=5min
OnUnitActiveSec=10min
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload && systemctl enable --now naturalshot-actualizar.timer >/dev/null

if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; fi

say "Listo"
echo "  Abrí: https://$DOMINIO   (usuario: $USUARIO)"
echo "  La app en el navegador: https://app.$DOMINIO"
echo "  Registros: docker compose -f $DIR/servidor/docker-compose.yml logs -f"
