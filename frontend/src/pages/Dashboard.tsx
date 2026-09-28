// Dashboard: la pantalla del kit (`libra-ui/comercio/Dashboard`), la misma que Contalibra, sobre el
// router del motor (`/api/dashboard`, ADR-039).
//
// Sin accesos rápidos (VentaLibra no tiene facturas, presupuestos ni remitos como documentos propios, y
// no hay una pantalla de "nuevo movimiento de caja" suelta), sin la tarjeta de presupuestos, y sin los
// links a factura/caja general que este producto no tiene -- mismo criterio que `rutaDeFactura={null}`
// en `pages/Ventas.tsx`.
import { Dashboard as DashboardComercio } from 'libra-ui/comercio/Dashboard'

export function Dashboard() {
  return (
    <DashboardComercio
      accionesRapidas={[]}
      conPresupuestos={false}
      rutaDeFactura={null}
      rutaDeFacturas={null}
      rutaDeCaja={null}
    />
  )
}
