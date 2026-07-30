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

router = build_json_api_auth_router(incluir_verify=True)
