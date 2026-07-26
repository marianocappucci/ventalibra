"""ASGI entrypoint (`uvicorn app.asgi:app`): create_app() requiere db_path,
asi que este modulo lo lee de env una vez al importar. Sin frontend ni
provisioning todavia (Fase 1) -- se suman en fases posteriores, mismo
patron que gestiolibra/app/asgi.py cuando llegue el momento.
"""
import os

from .main import create_app

DATA_DIR = os.environ.get("DATA_DIR", "./data")
os.makedirs(DATA_DIR, exist_ok=True)
db_path = os.environ.get("VENTALIBRA_DB_PATH", f"{DATA_DIR}/ventalibra.db")

app = create_app(db_path)
