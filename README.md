# VentaLibra

Vertical de la familia Libra para despensas, autoservicios, comercios de
alimentos, tiendas de ropa y comercios minoristas en general. Cubre catálogo,
inventario, compras y ventas/POS componiendo dos motores reutilizables:
[LibraCommerce](https://github.com/marianocappucci/libracommerce) (catálogo,
compras, inventario, ventas) y
[LibraCore](https://github.com/marianocappucci/libracore) (auth, caja,
facturación ARCA).

Alcance completo, arquitectura de la familia y orden de implementación
documentados en la wiki del ecosistema
(`wiki/analyses/arquitectura-familia-libra-alcance.md` y
`wiki/entities/ventalibra.md`).

## Estado

- Fase 1 completa: auth + catálogo + inventario + venta POS básica,
  wireados de punta a punta sobre LibraCommerce/LibraCore.
- Fase 2 completa: compras (proveedores, órdenes de compra, recepciones con
  orquestación de stock/costo).
- Fase 3 completa: caja y facturación ARCA vía LibraCore (facturación
  opcional por venta, caja siempre al confirmar).
- Entorno dev: `dev.ventalibra.com.ar` (pendiente de provisionar).
- Demo: `demo.ventalibra.com.ar` (pendiente).
- Producción: `cliente.ventalibra.com.ar` (pendiente, arquitectura silo por cliente).
- Rama de desarrollo: `develop`.
- Rama de producción: `main` (todavía no creada — se abre cuando haya un
  primer corte deployable).

## Documentación relacionada

- [ROADMAP.md](ROADMAP.md)
- [TASKS.md](TASKS.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [CONVENTIONS.md](CONVENTIONS.md)
- [DECISIONS.md](DECISIONS.md)
- [CHANGELOG.md](CHANGELOG.md)
