// El detalle de una venta: la pantalla del kit (F4, ADR-025, P9-M3), con la
// devolución de VentaLibra (`DevolucionDeVenta`, en `./Ventas`) montada como
// `accionesExtra` y sin recibo, facturas ni remitos -- ninguno de los tres
// existe como pantalla propia en este producto.
import { VentaDetalle as VentaDetalleComercio } from 'libra-ui/comercio/VentaDetalle'
import { DevolucionDeVenta } from './Ventas'

export function VentaDetalle() {
  return (
    <VentaDetalleComercio
      // Mismo criterio que `Ventas.tsx`: un cajero (staff) también puede
      // anular -- el motor no está gateado a admin en este producto.
      puedeAnular
      // Los cuatro en `null` (libra-ui v0.72.1, nullables desde acá):
      // VentaLibra no tiene pantalla de recibo, de factura ni de remito. El
      // dato de la factura queda como texto (`factura_display`), sin link;
      // el bloque de remito y los botones de recibo/generar remito no se
      // ofrecen. El ticket queda en el default del kit
      // (`/ventas/{id}/ticket`), que es justo la ruta del backend
      // (`app/routers/ventas_extra.py`) -- ese no es prop, está fijo.
      rutaDeRecibo={null}
      rutaDeFactura={null}
      rutaDeRemito={null}
      rutaDeRemitoNuevo={null}
      // 🔴 `(ctx) => <DevolucionDeVenta {...ctx} />`, NO `accionesExtra=
      // {DevolucionDeVenta}` a secas. `accionesExtra` es `(ctx) => ReactNode`
      // y `DevolucionDeVenta` encaja esa forma, pero pasarla directa hace
      // que el kit la invoque como FUNCIÓN (`accionesExtra(ctx)`), no como
      // elemento de React -- sus hooks (`useState` de `open`, `devuelto`...)
      // terminan corriendo pegados a la secuencia de hooks de
      // `VentaDetalle`, y el día que ese bloque aparece o desaparece entre
      // renders (justo lo que hace: sólo se muestra con la venta cobrada o
      // parcial) React tira "Rendered more hooks than during the previous
      // render". Envuelta en JSX, `<DevolucionDeVenta .../>` es un
      // componente aparte con su propia secuencia -- se cae sola cuando el
      // bloque no está. Se midió el error roto antes de este comentario.
      accionesExtra={(ctx) => <DevolucionDeVenta {...ctx} />}
    />
  )
}
