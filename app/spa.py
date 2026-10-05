"""La SPA es del motor desde libracore v1.133.0 (`libracore.spa`, ADR-020 del motor).

Este archivo era la implementación, byte a byte igual en seis productos; ahora
re-exporta la del motor para que `app/asgi.py` y los tests sigan importando de
acá. Lo nuevo del motor: una ruta `/api/...` que no existe contesta 404 en JSON
en vez del `index.html` con 200 (así se veía «`/api/health` 200» cuando el
chequeo real es `/health`).
"""
from libracore.spa import (  # noqa: F401
    PARA_SIEMPRE,
    PREFIJOS_API,
    SIN_CACHE,
    TIPOS_PROPIOS,
    AssetsInmutables,
    archivo_publico,
    es_de_la_api,
    montar_spa,
)
