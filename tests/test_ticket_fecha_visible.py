"""La fecha que sale IMPRESA en el ticket de una venta.

🔴 El assert es sobre el texto del PDF, no sobre lo que `ticket_de_venta` le
pasa al generador. Leyendo `app/services/tickets.py` solo, el
`strftime("%Y-%m-%d %H:%M")` parece una fuga de formato ISO; punta a punta no lo
es, porque `libracore.ticket_generator` le aplica `fmt_fecha` antes de
imprimirlo. Este test existe para que un proximo barrido de formato no
"arregle" ese strftime y rompa el ticket sin que nada se ponga en rojo.
"""
import io
from datetime import datetime

from pypdf import PdfReader

from app.services.tickets import ticket_de_venta


class _Linea:
    description_snapshot = "Yerba 1kg"
    quantity = 2
    unit_price = 5500


class _Pago:
    method = "efectivo"
    amount = 11000


class _Venta:
    number = "0001-00000042"
    # 🔴 El 11 de marzo, no un 1 de enero: con `01-01` las lecturas `dd-mm` y
    # `mm-dd` dan el mismo texto y el test pasaria con el formato invertido.
    confirmed_at = datetime(2026, 3, 11, 14, 30)
    items = [_Linea()]
    discount_total = 0
    total = 11000
    payments = [_Pago()]


def _texto_del_ticket() -> str:
    pdf = ticket_de_venta(_Venta())
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)


def test_el_papel_muestra_dd_mm_aaaa():
    assert "11-03-2026" in _texto_del_ticket()


def test_el_papel_no_muestra_iso_ni_barras():
    texto = _texto_del_ticket()
    assert "2026-03-11" not in texto
    assert "11/03/2026" not in texto
