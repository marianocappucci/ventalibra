"""Router /auth (login/logout/me/verify) -- shim sobre
libracore.auth.build_json_api_auth_router. Extraído 2026-07-26: era
byte-idéntico en Gestiolibra/MedLibra/VentaLibra, ver
wiki/analyses/auditoria-duplicacion-familia-libra.md."""
from libracore.auth import build_json_api_auth_router

router = build_json_api_auth_router()
