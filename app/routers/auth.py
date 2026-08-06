"""Router /auth (login/logout/me/verify) -- shim sobre
libraauth.session_auth.build_json_api_auth_router.

Extraído 2026-07-26 a libracore.auth (era byte-idéntico en Gestiolibra/
MedLibra/VentaLibra, ver wiki/analyses/auditoria-duplicacion-familia-libra.md)
y **migrado el 2026-07-30 a libraauth**: VentaLibra ya no importa nada de
`libracore.auth`.

`incluir_verify=True` es obligatorio acá: `POST /auth/verify` es el chequeo
stateless de credenciales que usa el login de `/docs/` de la landing
(server-to-server con `DOCS_AUTH_SECRET`, ver ADR-018). En libraauth el
endpoint es opt-in porque no todo consumidor tiene landing; **sin este flag el
`/docs/` de la landing deja de poder validar credenciales**.
"""
from libraauth.session_auth import build_json_api_auth_router

# `incluir_demo=True` NO enciende nada por si solo: `POST /auth/demo` se
# registra unicamente si la instancia ademas tiene `DEMO_MODE` y
# `DEMO_USERNAME` puestas. En las instancias de cliente la ruta no existe —
# es un 404, no un 403. Ver `_demo_username` en libraauth.
router = build_json_api_auth_router(incluir_verify=True, incluir_password_reset=True, incluir_demo=True)
