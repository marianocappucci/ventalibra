# Roadmap — TiendaLibra

Dirección estratégica del producto. No usar para tareas pequeñas del sprint
(ver `TASKS.md`).

## Objetivo actual

- [ ] Fase 1: probar de punta a punta que TiendaLibra puede componer
  LibraCore (auth) + LibraCommerce (catálogo/inventario/ventas) con un
  flujo de POS real, antes de construir el resto del alcance.

## Fases

### Fase 1 — Auth + catálogo + inventario + POS básico (en curso)

- Resultado esperado: API FastAPI con login por sesión, CRUD de
  categorías/unidades/items de catálogo, ubicaciones, movimientos de stock
  manuales, y un flujo de venta (crear → agregar líneas → confirmar) que
  descuenta stock real.
- Criterio de terminado: suite de tests contra SQLite real pasando +
  verificación manual del flujo POS completo con `uvicorn`.
- Dependencias: `libracommerce` v0.1.1 (tag cortado para esta fase),
  `libracore` v0.17.1.

### Fase 2 — Compras

- Recepción de mercadería (`PurchaseOrder`/`PurchaseReceipt`, ya modelados
  en LibraCommerce) con la orquestación recepción→stock que LibraCommerce
  deliberadamente no automatiza.
- Proveedores como `Party` con rol `supplier`.

### Fase 3 — Caja y facturación ARCA

- Segunda base SQLite dedicada a `libracore.db` (mismo patrón que
  `medlibra/app/services/billing.py`): `init_core_schema`, `caja`,
  `arca_facturacion`.
- Decisión pendiente en esa fase: si conviene reusar `libracore.db.usuarios`
  para esa base en vez de mantener una tabla de usuarios propia (para
  entonces ya existiría de todos modos).

### Fase 4 — Extensiones de catálogo (requieren tocar LibraCommerce primero)

- Códigos de barra (`item_codes`), variantes de talle/color
  (`item_variants`), listas de precio (`price_lists`/`item_prices`),
  productos pesables. Ninguno de estos existe todavía en LibraCommerce —
  son extensiones al motor compartido, no al vertical, según el propio
  análisis de arquitectura de la familia. Se decide de forma explícita
  cuando se llegue a esta fase, no de pasada.

### Fase 5 — Onboarding, planes, frontend, reportes

- Onboarding multi-cliente con enforcement de planes (mismo patrón que
  GestioLibra/MedLibra).
- Frontend React/Vite/Tailwind/shadcn-ui (estándar de la familia).
- Reportes de ventas, caja y stock.
- Validar con un comercio real antes de sumar promociones avanzadas,
  multi-sucursal o modo offline (ver `wiki/analyses/arquitectura-familia-libra-alcance.md`,
  "Orden de implementación").

## Futuro

- Modo offline (mini PC local) reusando `libraedge`/la integración ya
  construida en LibraCommerce — evaluar una vez validado con un comercio real.
