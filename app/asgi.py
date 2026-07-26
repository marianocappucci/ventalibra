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

Sin frontend todavia -- se suma cuando Fase 5 lo requiera (mismo patron
que gestiolibra/app/asgi.py cuando llegue el momento).
"""
import os

from .main import create_app

DATA_DIR = os.environ.get("DATA_DIR")
if DATA_DIR:
    os.makedirs(DATA_DIR, exist_ok=True)
    db_path = os.environ.get("VENTALIBRA_DB_PATH", f"{DATA_DIR}/ventalibra.db")
    os.environ.setdefault(
        "VENTALIBRA_LIBRACORE_DB_PATH", f"{DATA_DIR}/ventalibra_libracore.db"
    )
    if os.environ.get("ADMIN_USER"):
        os.environ.setdefault("VENTALIBRA_ADMIN_USERNAME", os.environ["ADMIN_USER"])
    if os.environ.get("ADMIN_PASSWORD"):
        os.environ.setdefault("VENTALIBRA_ADMIN_PASSWORD", os.environ["ADMIN_PASSWORD"])
else:
    db_path = os.environ["VENTALIBRA_DB_PATH"]

app = create_app(db_path)
