#!/usr/bin/env bash
# Escribe /srv/naturalshot/config/compose.env para docker compose a partir de servidor.env.
# Compose interpreta los $ de los valores sin comillas: cada $ del hash de la contraseña va doble.
set -euo pipefail
CONF=/srv/naturalshot/config/servidor.env
SALIDA=/srv/naturalshot/config/compose.env
. "$CONF"
umask 077
{
  echo "GITHUB_REPO=$GITHUB_REPO"
  echo "GITHUB_TOKEN=$GITHUB_TOKEN"
  echo "DOMINIO=$DOMINIO"
  echo "USUARIO=$USUARIO"
  echo "CLAVE_HASH=${CLAVE_HASH//\$/\$\$}"
} > "$SALIDA"
