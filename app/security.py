"""Password hashing para la tabla `users` propia de VentaLibra.

Misma construccion PBKDF2 (260k iteraciones, salt por password, comparacion
en tiempo constante) que gestiolibra/app/security.py y
medlibra/app/security.py -- ver DECISIONS.md ADR-002 sobre por que no se
reusa libracore.db.usuarios en esta fase.
"""
import hashlib
import hmac
import secrets


def hash_password(password: str) -> str:
    salt = secrets.token_hex(32)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return f"pbkdf2:sha256:{salt}:{dk.hex()}"


def verify_password(stored: str, provided: str) -> bool:
    try:
        _, algo, salt, stored_hash = stored.split(":")
        dk = hashlib.pbkdf2_hmac(algo, provided.encode(), salt.encode(), 260_000)
        return hmac.compare_digest(dk.hex(), stored_hash)
    except Exception:
        return False


# Mismo costo que un hash real, verificado cuando el username no existe para
# que check_credentials() tarde lo mismo en ambos casos (sin canal de tiempo
# para enumeracion de usuarios). Se genera una sola vez al importar.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_hex(16))
