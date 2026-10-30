"""ASGI entrypoint (`uvicorn app.asgi:app`): create_app() requiere db_path,
asi que este modulo lo lee de env una vez al importar.

Bridges dos convenciones de env vars: el `docker-compose.yml` de este repo
(VENTALIBRA_DB_PATH/VENTALIBRA_ADMIN_*, seteadas explicitamente) para dev
local, y el contrato generico que escribe `libracore.provisioning` para
clientes reales (DATA_DIR/ADMIN_USER/ADMIN_PASSWORD -- mismos nombres que
Contalibra/Restolibra ya leen directamente, y que gestiolibra/medlibra
puentean igual, ver wiki/entities/libracore.md). Cuando DATA_DIR esta
presente tiene prioridad para todo lo que no este ya seteado
explicitamente, asi un contenedor de cliente provisionado no necesita
ninguna env var especifica de VentaLibra.

Tambien sirve el build de la SPA (`frontend/dist`) -- mismo patron que
gestiolibra/app/asgi.py: las rutas de la API ya registradas por
create_app() tienen prioridad, cualquier otra cosa cae al catch-all que
sirve `index.html` (ruteo del lado del cliente, ver DECISIONS.md ADR-014).
Corriendo `uvicorn app.asgi:app` sin haber buildeado el frontend sigue
funcionando como API pura -- el mount se salta en silencio si no existe.
"""
import os
from pathlib import Path

from libracore.db.url_de_instancia import url_de_instancia

from app.frontend_dist import frontend_dist
from app.spa import montar_spa

from .main import create_app

DATA_DIR = os.environ.get("DATA_DIR")
if DATA_DIR:
    os.makedirs(DATA_DIR, exist_ok=True)
    db_path = url_de_instancia(
        "ventalibra", default=f"{DATA_DIR}/ventalibra.db"
    )
    # Ya no se puentea `VENTALIBRA_LIBRACORE_DB_PATH` a un archivo SQLite de DATA_DIR: `create_app()` resuelve el core con la
    # base del dominio cuando no hay variable (ADR-094), y un archivo SQLite lo rechaza `billing.configure`.
    if os.environ.get("ADMIN_USER"):
        os.environ.setdefault("VENTALIBRA_ADMIN_USERNAME", os.environ["ADMIN_USER"])
    if os.environ.get("ADMIN_PASSWORD"):
        os.environ.setdefault("VENTALIBRA_ADMIN_PASSWORD", os.environ["ADMIN_PASSWORD"])
else:
    db_path = url_de_instancia("ventalibra", requerida=True)

app = create_app(db_path)

FRONTEND_DIST = frontend_dist()
if FRONTEND_DIST.is_dir():
    montar_spa(app, FRONTEND_DIST)
