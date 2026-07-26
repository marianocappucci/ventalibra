# Tasks — TiendaLibra

Trabajo concreto y vigente. Al completar o descartar una tarea, actualizarla;
no usar este archivo como historial (para eso está `CHANGELOG.md`).

## En curso

- [ ] Ninguna por ahora.

## Completadas

- [x] Scaffold Fase 1: persistencia (`app/db.py`), auth
  (`app/auth.py`/`security.py`/`services/users.py`), catálogo
  (`app/services/catalog.py`), stock, ventas POS (`app/services/sales.py`),
  routers, tests, CI — responsable: LLM.
- [x] Fase 2: compras (proveedores, orden/recepción, orquestación de stock
  vía `libracommerce.usecases.purchasing.confirm_purchase_receipt`) — pin
  de `libracommerce` a v0.1.2, secuencias propias (`app/db.py`), 10 tests
  nuevos (30 en total) + smoke end-to-end — responsable: LLM.
- [x] Fase 3: caja/facturación vía LibraCore (`app/services/billing.py`,
  segunda base SQLite dedicada, clientes con extensión `party_billing`,
  facturación opcional por venta, caja siempre al confirmar) — 8 tests
  nuevos (39 en total) + smoke end-to-end — responsable: LLM.

## Próximas

- [ ] Fase 4: extensiones de catálogo (códigos de barra, variantes,
  listas de precio) — requieren tocar LibraCommerce primero.

## Bloqueadas

- [ ] Ninguna por ahora.
