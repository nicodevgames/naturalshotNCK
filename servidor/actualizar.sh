#!/usr/bin/env bash
# Trae los cambios de main y, si hay, reconstruye NaturalShot en el navegador (lo corre un timer cada 10 min).
set -euo pipefail
DIR=/opt/naturalshot
CONF=/srv/naturalshot/config/servidor.env
. "$CONF"
AUTH="Authorization: Basic $(printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64 -w0)"
antes=$(git -C "$DIR" rev-parse HEAD)
git -C "$DIR" -c http.extraHeader="$AUTH" fetch -q origin main
despues=$(git -C "$DIR" rev-parse origin/main)
[ "$antes" = "$despues" ] && exit 0
git -C "$DIR" reset -q --hard origin/main
echo "NaturalShot: $antes -> $despues, reconstruyendo"
bash "$DIR/servidor/env_compose.sh"
docker compose -f "$DIR/servidor/docker-compose.yml" --env-file /srv/naturalshot/config/compose.env up -d --build --remove-orphans
docker image prune -f >/dev/null
