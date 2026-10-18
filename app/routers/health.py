from fastapi import APIRouter

router = APIRouter()


# 🔑 **`GET` y `HEAD`.** Un monitor de uptime (uptime-kuma) sondea con `HEAD`, y
# `@router.get` a secas lo contestaba con 405: la instancia figuraba caída estando
# sana. FastAPI no deriva el `HEAD` del `GET`.
@router.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"ok": True, "product": "ventalibra"}
