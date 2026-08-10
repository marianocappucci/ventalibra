#!/usr/bin/env bash
# Reset diario de la demo publica de Ventalibra — item 8 de los pendientes de
# Libra.
#
# Deja la base de cero, el arranque reconstruye el esquema y despues se siembra.
# **El estado limpio es codigo, no un backup guardado a mano**: eso es lo que
# hace que sea reproducible, y que agregar un dato de ejemplo sea un commit y no
# una operacion manual sobre el servidor.
#
# Corre por cron a las 04:40, despues de los backups de las 03:15 y 03:30 — no
# se pisan, y si un backup tarda de mas el reset no lo interrumpe.
#
# 🔴 **Solo toca la instancia demo.** El contenedor esta escrito aca, no
# viene por argumento: un reset apuntado al contenedor equivocado le borra la
# base a un cliente, y no hay confirmacion que valga a las cuatro de la manana.
#
# 🔴 **Este archivo es el unico lugar donde vive la logica.** Hasta el
# 2026-08-10 habia una copia suelta en `/root/scripts-demo/reset_ventalibra.sh`
# que el cron llamaba, y esa copia tenia DOS defensas que este archivo no
# tenia (la guarda por `DEMO_MODE` y el orden "seed antes de borrar", las dos
# agregadas despues de sendos incidentes). Ahora el cron llama a este, y la
# copia suelta quedo como un envoltorio de una linea.
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

# 🔴 La guarda del nombre no alcanza, y esto no es teórico: hasta el 2026-08-07
# el contenedor llamado `restolibra-demo` era el que servía
# sistema.restolibra.com.ar. El nombre decía demo y no lo era. Por eso se
# verifica una propiedad real de la instancia -DEMO_MODE, lo único que
# enciende el auto-login público- y no cómo se llama.
if ! docker exec "$CONTENEDOR" printenv DEMO_MODE 2>/dev/null | grep -qx 1; then
  log "ABORTA: $CONTENEDOR no tiene DEMO_MODE=1. El nombre no alcanza."
  exit 4
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTENEDOR"; then
  log "ABORTA: el contenedor $CONTENEDOR no esta corriendo."
  exit 3
fi

log "=== reset de $CONTENEDOR ==="

# --- 0. El seed, ANTES de tocar la base -----------------------------------
# 🔴 El 2026-08-06 este script borro la base y recien despues descubrio que no
# podia sembrar: `scripts/seed_demo.py` vive en `develop` y el checkout del VPS
# esta en `main`. Cinco demos quedaron vacias, y el cron lo habria repetido
# todas las noches. El orden correcto es conseguir el seed primero: si no esta,
# no se borra nada.
#
# Sale de `origin/develop` y no del arbol de trabajo, que es de donde sale la
# imagen que corre la demo — y asi da igual en que rama quede el checkout.
SEED_LOCAL=/tmp/seed-ventalibra.py
git -C /root/ventalibra fetch -q origin || { log "ABORTA: no se pudo hacer fetch de ventalibra."; exit 5; }
git -C /root/ventalibra show origin/develop:scripts/seed_demo.py > "$SEED_LOCAL" || { log "ABORTA: no esta scripts/seed_demo.py en origin/develop."; exit 6; }
[ -s "$SEED_LOCAL" ] || { log "ABORTA: el seed salio vacio."; exit 7; }
log "seed listo desde origin/develop ($(wc -l < "$SEED_LOCAL") lineas)"

# --- 1. Base de cero ------------------------------------------------------
# 🔴 Que sea "borrar los .db" depende del motor, y desde el corte a PostgreSQL
# ya no da igual: con la base en PostgreSQL, un `rm /app/data/*.db` borra
# archivos que no usa nadie, el contenedor reinicia contra los datos de ayer y
# el seed se apila encima. El reset seguiria diciendo "listo" todas las noches
# sin resetear nada. Por eso el motor se DETECTA, y si no se puede detectar se
# aborta en vez de suponer SQLite.
URL_BASE=$(docker exec "$CONTENEDOR" printenv VENTALIBRA_DB_PATH 2>/dev/null || true)
if [ -z "$URL_BASE" ]; then
  log "ABORTA: no pude leer VENTALIBRA_DB_PATH del contenedor."
  exit 8
fi

# El sidecar, si el motor es PostgreSQL: su nombre es el host de la URL, que en
# esta red es la clave del servicio y tambien el `container_name`.
SIDECAR=""
case "$URL_BASE" in
  postgres://*|postgresql://*)
    SIDECAR=${URL_BASE#*@}
    SIDECAR=${SIDECAR%%:*}
    SIDECAR=${SIDECAR%%/*}
    ;;
esac

# Cuantas filas hay en tres tablas del dominio. Es la unica forma de que este
# script pueda DECIR que reseteo: se mide antes y despues, y si despues no dio
# cero, se aborta sin sembrar. Un reset que no resetea y siembra igual deja la
# demo con los datos de ayer mas los de hoy, y no avisa nunca.
filas_del_dominio() {
  case "$URL_BASE" in
    postgres://*|postgresql://*)
      docker exec "$SIDECAR" sh -c '
        psql -tA -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
          SELECT COALESCE((SELECT COUNT(*) FROM products), 0)
               + COALESCE((SELECT COUNT(*) FROM sales), 0)
               + COALESCE((SELECT COUNT(*) FROM parties), 0)"
      ' 2>/dev/null || echo "?"
      ;;
    *)
      docker exec "$CONTENEDOR" python3 -c "
import sqlite3, sys
try:
    c = sqlite3.connect('$URL_BASE')
    print(sum(c.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0]
              for t in ('products', 'sales', 'parties')))
except Exception:
    print('?')
" 2>/dev/null || echo "?"
      ;;
  esac
}

ANTES=$(filas_del_dominio)
log "filas del dominio antes del reset: $ANTES"

case "$URL_BASE" in
  postgres://*|postgresql://*)
    if ! docker ps --format '{{.Names}}' | grep -qx "$SIDECAR"; then
      log "ABORTA: el sidecar '$SIDECAR' no esta corriendo."
      exit 9
    fi
    log "motor: PostgreSQL (sidecar $SIDECAR)"

    # Se para la app ANTES de tocar el schema. Con el contenedor arriba, sus
    # conexiones abiertas dejan el `DROP SCHEMA` esperando un lock: no falla,
    # se cuelga -- ya pasó, veinte minutos en silencio.
    docker stop "$CONTENEDOR" >/dev/null
    log "app parada para soltar las conexiones"

    # `psql` se corre DENTRO del sidecar y con las variables de su propio
    # entorno: asi la contrasena no pasa por la linea de comandos del host,
    # donde quedaria en el `ps` y en el log del cron.
    docker exec "$SIDECAR" sh -c '
      psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        -c "DROP SCHEMA IF EXISTS public CASCADE" \
        -c "CREATE SCHEMA public" \
        -c "GRANT ALL ON SCHEMA public TO \"$POSTGRES_USER\""
    ' >/dev/null || { log "ABORTA: no se pudo recrear el schema."; docker start "$CONTENEDOR" >/dev/null; exit 10; }
    log "schema recreado, vacio"

    docker start "$CONTENEDOR" >/dev/null
    ;;
  *)
    log "motor: SQLite ($URL_BASE)"
    # Se borran tambien los `-wal` y `-shm`: sin eso SQLite puede reconstruir
    # parte de lo borrado desde el journal, y el reset queda a medias.
    docker exec "$CONTENEDOR" sh -c 'rm -f /app/data/*.db /app/data/*.db-wal /app/data/*.db-shm'
    log "base borrada"
    docker restart "$CONTENEDOR" >/dev/null
    ;;
esac

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

# --- 1b. Que de verdad haya reseteado -------------------------------------
# La post-condicion. Sin esto el script dice "listo" igual cuando no borro nada,
# que es exactamente como se rompe un reset al cambiar de motor: el paso de
# borrado deja de aplicar, nadie lo nota, y el seed se apila todas las noches.
DESPUES=$(filas_del_dominio)
log "filas del dominio despues del reset: $DESPUES"
if [ "$DESPUES" != "0" ]; then
  log "ABORTA: la base no quedo vacia (antes $ANTES, despues $DESPUES)."
  log "        No se siembra encima: quedaria la demo de ayer mas la de hoy."
  exit 11
fi
if [ "$ANTES" = "0" ]; then
  log "OJO: antes tambien habia 0 filas -- el chequeo no probo nada esta vez."
fi

# --- 2. Sembrar -----------------------------------------------------------
# Por la API y desde adentro del contenedor: la contrasena sale de su propio
# entorno y nunca pasa por la linea de comandos del host, donde quedaria en el
# `ps` y en el log del cron.
docker cp "$SEED_LOCAL" "$CONTENEDOR:/tmp/seed.py"
docker exec -i "$CONTENEDOR" sh -c '
  python3 /tmp/seed.py \
    --url https://demo.ventalibra.com.ar \
    --usuario "${VENTALIBRA_ADMIN_USERNAME:-admin}" \
    --password "$VENTALIBRA_ADMIN_PASSWORD"
'
docker exec "$CONTENEDOR" rm -f /tmp/seed.py

log "=== listo ==="
