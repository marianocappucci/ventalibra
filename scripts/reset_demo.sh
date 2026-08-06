#!/usr/bin/env bash
# Reset diario de la demo publica de Ventalibra — item 8 de los pendientes de
# Libra.
#
# Borra la base, deja que el arranque reconstruya el esquema y vuelve a
# sembrar. **El estado limpio es codigo, no un backup guardado a mano**: eso es
# lo que hace que sea reproducible, y que agregar un dato de ejemplo sea un
# commit y no una operacion manual sobre el servidor.
#
# Corre por cron a las 04:30, despues de los backups de las 03:15 y 03:30 — no
# se pisan, y si un backup tarda de mas el reset no lo interrumpe.
#
# 🔴 **Solo toca la instancia demo.** El contenedor esta escrito aca, no
# viene por argumento: un reset apuntado al contenedor equivocado le borra la
# base a un cliente, y no hay confirmacion que valga a las cuatro de la manana.
set -euo pipefail

CONTENEDOR="ventalibra-demo"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# --- La guarda ------------------------------------------------------------
# Si el nombre no es el de una demo, no se sigue. Es barato, y es lo unico que
# separa "resetear la demo" de "borrarle la base a un cliente".
case "$CONTENEDOR" in
  *-demo|*-publica) ;;
  *) log "ABORTA: '$CONTENEDOR' no parece una instancia demo."; exit 2 ;;
esac

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTENEDOR"; then
  log "ABORTA: el contenedor $CONTENEDOR no esta corriendo."
  exit 3
fi

log "=== reset de $CONTENEDOR ==="

# --- 1. Base de cero ------------------------------------------------------
# Se borran tambien los `-wal` y `-shm`: sin eso SQLite puede reconstruir parte
# de lo borrado desde el journal, y el reset queda a medias.
docker exec "$CONTENEDOR" sh -c 'rm -f /app/data/*.db /app/data/*.db-wal /app/data/*.db-shm'
log "base borrada"

docker restart "$CONTENEDOR" >/dev/null
for _ in $(seq 1 40); do
  estado=$(docker inspect -f '{{.State.Health.Status}}' "$CONTENEDOR" 2>/dev/null || echo starting)
  [ "$estado" = "healthy" ] && break
  sleep 3
done
estado=$(docker inspect -f '{{.State.Health.Status}}' "$CONTENEDOR" 2>/dev/null || echo desconocido)
log "contenedor: $estado"
if [ "$estado" != "healthy" ]; then
  log "ABORTA: no levanto sano; no se siembra sobre una instancia rota."
  exit 4
fi

# --- 2. Sembrar -----------------------------------------------------------
# Por la API y desde adentro del contenedor: la contrasena sale de su propio
# entorno y nunca pasa por la linea de comandos del host, donde quedaria en el
# `ps` y en el log del cron.
docker cp "/root/ventalibra/scripts/seed_demo.py" "$CONTENEDOR:/tmp/seed.py"
docker exec -i "$CONTENEDOR" sh -c '
  python3 /tmp/seed.py \
    --url https://demo.ventalibra.com.ar \
    --usuario "${VENTALIBRA_ADMIN_USERNAME:-admin}" \
    --password "$VENTALIBRA_ADMIN_PASSWORD"
'
docker exec "$CONTENEDOR" rm -f /tmp/seed.py

log "=== listo ==="
