#!/usr/bin/env python3
"""Deja lista una instancia para los tests de navegador de dominio (`frontend/e2e/`, `.github/workflows/e2e.yml`).

Dos pasos, los dos por la API y con el cliente de `seed_demo.py` (mismas validaciones que usa la pantalla):

- `terminos`: el admin acepta los Términos y Condiciones de la instancia. Va ANTES de `seed_demo.py`: mientras estén
  pendientes el motor corta con 403 toda llamada gateada por rol, la semilla incluida. El gate se recorre por la pantalla
  en el smoke (`login.smoke.ts`); acá se salta porque lo que se prueba es el dominio.
- `usuarios`: un usuario por rol (`e2e_cajero`, `e2e_vendedor`, ...) con la misma contraseña de CI, para que el proyecto
  `setup` de Playwright guarde su sesión (`.auth/<rol>.json`). Idempotente: si ya existe, lo deja.

> 🔴 Nunca contra la instancia de un cliente: se planta si el host no es de dev, demo, prueba o local
> (`seed_demo.url_no_productiva`), igual que la semilla.

Uso (desde la raíz del repo, con el python del producto):
    python -m scripts.e2e_usuarios terminos
    python -m scripts.seed_demo --url http://localhost:8000 --usuario admin --password ...
    python -m scripts.e2e_usuarios usuarios
Contraseñas por entorno (`E2E_ADMIN_CLAVE`, `E2E_CLAVE`) para que no queden en la línea de comandos.
"""
from __future__ import annotations

import argparse
import os
import sys

from scripts.seed_demo import Api, iniciar_sesion, url_no_productiva

#: Los roles que no son admin (`app/permisos.py::ROLES`). Una copia a propósito: este script no importa la app, y la
#: suite (`tests/test_e2e_usuarios.py`) falla si deja de coincidir con la matriz de permisos.
ROLES_CON_USUARIO = ("encargado", "vendedor", "cajero", "deposito")

CLAVE_POR_DEFECTO = "e2e-Clave-1234"


def usuario_de(rol: str) -> str:
    return f"e2e_{rol}"


def aceptar_terminos(api: Api) -> bool:
    """Acepta los Términos vigentes si están pendientes. `True` si los aceptó ahora."""
    estado = api.get("/terminos")
    if not estado.get("pendiente"):
        return False
    api.post("/terminos/aceptar", {"version": estado["version"]})
    return True


def crear_usuarios_por_rol(api: Api, clave: str) -> dict[str, bool]:
    """Crea `e2e_<rol>` para cada rol. Devuelve `{rol: creado_ahora}`; uno que ya estaba no se toca."""
    hechos = {}
    for rol in ROLES_CON_USUARIO:
        try:
            api.post("/users", {"username": usuario_de(rol), "name": f"E2E {rol}", "password": clave, "role": rol})
            hechos[rol] = True
        except RuntimeError as e:
            # El alta de un usuario repetido es 409 (o 400/422 según la versión del motor): se reconoce por el texto.
            if "ya existe" in str(e).lower() or " 409" in str(e):
                hechos[rol] = False
            else:
                raise
    return hechos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paso", choices=("terminos", "usuarios"))
    ap.add_argument("--url", default=os.environ.get("E2E_BASE_URL", "http://localhost:8000"))
    ap.add_argument("--usuario", default=os.environ.get("E2E_ADMIN_USUARIO", "admin"))
    ap.add_argument("--password", default=os.environ.get("E2E_ADMIN_CLAVE"))
    ap.add_argument("--clave-roles", default=os.environ.get("E2E_CLAVE", CLAVE_POR_DEFECTO))
    args = ap.parse_args()

    if not url_no_productiva(args.url):
        print(f"ERROR: {args.url} no parece una instancia de dev, demo ni local.", file=sys.stderr)
        return 2
    if not args.password:
        print("ERROR: falta la contraseña del admin (E2E_ADMIN_CLAVE o --password).", file=sys.stderr)
        return 2

    api = Api(args.url)
    iniciar_sesion(api, args.usuario, args.password)
    if args.paso == "terminos":
        print("Términos aceptados ahora." if aceptar_terminos(api) else "Los Términos ya estaban aceptados.")
    else:
        for rol, creado in crear_usuarios_por_rol(api, args.clave_roles).items():
            print(f"  {usuario_de(rol):<16} {'creado' if creado else 'ya estaba'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
