"""Las cabeceras de caché del frontend, que son lo que hace que un deploy se vea.

**Por qué existe este archivo.** Hasta el 2026-08-20 esta aplicación servía el
`index.html` **sin `Cache-Control`** — medido contra el dominio, no leído del
compose. Sin esa cabecera el navegador aplica caché heurística y puede servir la
copia guardada sin preguntar. Como Vite le pone un hash en el nombre a cada
bundle, el bundle viejo **sigue existiendo**: el `index.html` viejo lo pide y lo
recibe, con 200. No hay error en ninguna capa — ni un 404 que delate nada.

Le pasó a LibraCargo el 2026-08-19 con la pantalla de Backup: desplegada y sin
verse, con todo bien del lado del servidor.

Los dos tests principales son las dos mitades del mismo arreglo, y ninguna sirve
sola:

- el archivo cuyo nombre NO cambia (`index.html`) revalida siempre;
- los que llevan el hash en el nombre se cachean para siempre, que es seguro
  **porque** el index revalida.
"""

from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parent.parent
ASSET = "index-DELTEST123.js"


@pytest.fixture(scope="module")
def cliente():
    """La app de verdad, con un `dist` presente.

    🔴 El `dist` no es decorado: el mount de `/assets` y el catch-all **se arman
    en el import** y sólo si el directorio existe. Sin él, este archivo probaría
    una app sin frontend, o sea nada — y en verde. Se fabrica uno mínimo si el
    checkout no lo tiene (el job de tests del CI no construye el frontend) y se
    borra sólo lo que se haya creado.
    """
    dist = REPO / "frontend" / "dist"
    creado = not dist.is_dir()
    (dist / "assets").mkdir(parents=True, exist_ok=True)
    if creado:
        (dist / "index.html").write_text(
            "<!doctype html><title>VentaLibra</title>", encoding="utf-8"
        )
    asset = dist / "assets" / ASSET
    asset.write_text("console.log(1)", encoding="utf-8")
    suelto = dist / "prueba-de-cache.txt"
    suelto.write_text("hola", encoding="utf-8")

    # Reimportar: el módulo lee el entorno y arma las rutas EN EL IMPORT, así
    # que si ya está en `sys.modules` de otro test tendría el `dist` de antes.
    sys.modules.pop("app.asgi", None)
    modulo = importlib.import_module("app.asgi")
    assert (dist / "index.html").is_file(), "sin index.html esto no prueba nada"

    yield TestClient(modulo.app, base_url="https://testserver")

    sys.modules.pop("app.asgi", None)
    asset.unlink(missing_ok=True)
    suelto.unlink(missing_ok=True)
    if creado:
        shutil.rmtree(dist, ignore_errors=True)


def test_el_index_revalida_siempre(cliente):
    """El archivo cuyo nombre no cambia no se puede cachear a ciegas.

    Es el único que dice cuál es el bundle de ahora. Si el navegador se queda
    con el viejo, pide el bundle viejo —que existe, porque el nombre lleva
    hash— y lo recibe con 200: el deploy no se ve y nada falla.
    """
    r = cliente.get("/")
    assert r.status_code == 200
    assert "no-cache" in r.headers.get("cache-control", ""), dict(r.headers)


def test_una_ruta_del_ruteo_del_cliente_tambien(cliente):
    """Cae en el mismo `index.html` por el catch-all, y trae lo mismo."""
    r = cliente.get("/ventas")
    assert r.status_code == 200
    assert "no-cache" in r.headers.get("cache-control", ""), dict(r.headers)


def test_los_assets_se_cachean_para_siempre(cliente):
    """La otra mitad: el nombre lleva el hash del contenido, así que el mismo
    nombre nunca cambia de contenido."""
    r = cliente.get(f"/assets/{ASSET}")
    assert r.status_code == 200
    cache = r.headers.get("cache-control", "")
    assert "immutable" in cache and "max-age=31536000" in cache, cache


def test_los_archivos_sueltos_del_dist_no_se_cachean(cliente):
    """Un favicon o un manifest no llevan hash: mismo criterio que el index."""
    r = cliente.get("/prueba-de-cache.txt")
    assert r.status_code == 200
    assert "no-cache" in r.headers.get("cache-control", ""), dict(r.headers)


def test_las_dos_politicas_son_distintas(cliente):
    """El control de los dos de arriba, juntos.

    Si algún día las dos rutas devolvieran la misma cabecera, uno de los dos
    tests seguiría pasando por el motivo equivocado y nadie se enteraría.
    """
    index = cliente.get("/").headers.get("cache-control", "")
    asset = cliente.get(f"/assets/{ASSET}").headers.get("cache-control", "")
    assert index and asset and index != asset, f"index={index!r} asset={asset!r}"
