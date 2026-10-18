"""Ningún request usa la conexión de arranque (`app.state.conn`) — ADR-089.

La app tiene UNA conexión de arranque y mantenimiento (`app.state.conn`: el restore, los tests). Si un router o un servicio
la lee dentro de un request, vuelve el defecto que ADR-089 cerró: dos requests del mismo worker en la misma transacción.
Lo que un request necesita del dominio lo pide con `Depends(conexion_del_request)` o a través de `PorLlamada`.

Es un test de código y no de comportamiento a propósito: el defecto de una lectura de más no se ve con un request solo, sólo
con dos a la vez y en el orden malo (`test_requests_concurrentes.py`).
"""
import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"

#: Los únicos que pueden nombrarla: `main.py` la crea y la cierra/renueva en el restore, `conexion.py` lo explica.
PERMITIDOS = {"main.py", "conexion.py"}

LECTURA = re.compile(r"(?<![\w`])(?:request|req|app)\.app\.state\.conn\b|\bstate\.conn\b")


def _codigo(texto: str) -> str:
    """Sin comentarios ni docstrings de una línea: el texto que explica el defecto lo nombra a propósito."""
    sin_comentarios = re.sub(r"#.*", "", texto)
    return re.sub(r'"""(?:.|\n)*?"""', "", sin_comentarios)


def test_ningun_modulo_de_app_lee_la_conexion_de_arranque():
    culpables = [
        f"{archivo.relative_to(APP.parent)}:{n}"
        for archivo in sorted(APP.rglob("*.py"))
        if archivo.name not in PERMITIDOS
        for n, linea in enumerate(_codigo(archivo.read_text(encoding="utf-8")).splitlines(), 1)
        if LECTURA.search(linea)
    ]
    assert not culpables, f"leen app.state.conn dentro de un request (usar conexion_del_request / PorLlamada): {culpables}"
