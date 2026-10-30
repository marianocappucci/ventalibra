"""Dónde está el build del frontend.

Lo usan `asgi.py` (para servirlo) y `main.py` (el manifest de la marca cae al `manifest.webmanifest` del build). El dist se hornea
fuera de `/app` (`/opt/frontend-dist`) porque el compose de dev monta `./:/app` entero para el `--reload`, y eso taparía cualquier
build copiado adentro.
"""
from pathlib import Path

DOCKER_FRONTEND_DIST = Path("/opt/frontend-dist")
LOCAL_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def frontend_dist() -> Path:
    return DOCKER_FRONTEND_DIST if DOCKER_FRONTEND_DIST.is_dir() else LOCAL_FRONTEND_DIST
