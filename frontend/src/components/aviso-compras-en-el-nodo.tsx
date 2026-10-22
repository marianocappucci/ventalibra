// El aviso de Compras en un nodo offline (ADR-093): los proveedores y las órdenes de compra se cargan en la versión web y bajan al
// equipo del local; acá sólo se recibe mercadería contra una orden. `role="note"` y no `alert`: no es un error, es cómo funciona.
// Sólo se muestra en un nodo (`useConexionDelNodo` lee la conexión que ya consulta el layout con `conexionDelNodo: true`); en el
// central y en una instalación común no aparece, y no hace ningún pedido.
import { Info } from 'lucide-react'

import { useConexionDelNodo } from 'libra-ui/nodo-offline'

/** El mensaje que ve quien lo intenta: el mismo de `MENSAJE_COMPRAS_SOLO_EN_EL_CENTRAL` de `app/offline.py` (el 409 `solo_en_el_central`). */
export const TEXTO_COMPRAS_EN_EL_NODO = 'Las órdenes de compra y los proveedores se cargan en la versión web.'

export function AvisoComprasEnElNodo({ children }: { children?: string }) {
  const { esNodo } = useConexionDelNodo()
  if (!esNodo) return null
  return (
    <div role="note" className="mb-4 flex items-start gap-3 rounded-lg border bg-muted/50 p-4 text-sm">
      <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
      <div className="grid gap-1">
        <p className="font-medium">{TEXTO_COMPRAS_EN_EL_NODO}</p>
        {children && <p className="text-muted-foreground">{children}</p>}
      </div>
    </div>
  )
}
