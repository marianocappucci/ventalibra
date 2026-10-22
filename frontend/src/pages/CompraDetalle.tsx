// El detalle de una orden de compra: la pantalla del kit (`libra-ui/comercio/CompraDetalle`) sobre el router del motor.
//
// Dos props de rol (libra-ui 0.146.0, ADR-058 del kit; ADR-083 de este repo), que son las dos capacidades que el backend pide:
//  - `puedeEscribir` (`compras.escribir`): «Agregar línea» y, desde libra-ui 0.147.0, «Enviar al proveedor» y «Cancelar orden»
//    (libracommerce ADR-055: las dos rutas llevan `OpcionesCompras.autorizar_escritura`, la misma guarda que agregar una línea).
//  - `puedeRecibir` (`compras.recibir`): «Recibir mercadería» y «Confirmar recepción». El depósito no la tiene (decisión del
//    humano, 2026-09-29): quien recibe fija el costo.
// El que corta de verdad es el backend; esto sólo decide qué se ofrece.
//
// En un nodo offline (ADR-093) `puedeEscribir` es `false`: la orden se carga, se envía y se cancela en la versión web; en el equipo
// del local queda «Recibir mercadería» (lote, vencimiento y costo), que sube al central como `compra.recibida`.
import { CompraDetalle as CompraDetalleComercio } from 'libra-ui/comercio/CompraDetalle'
import { useConexionDelNodo } from 'libra-ui/nodo-offline'
import { AvisoComprasEnElNodo } from '../components/aviso-compras-en-el-nodo'
import { useAuth } from '../context/AuthContext'
import { puede } from '../lib/permisos'

export function CompraDetalle() {
  const { user } = useAuth()
  const { esNodo } = useConexionDelNodo()
  return (
    <>
      <AvisoComprasEnElNodo>Acá se recibe la mercadería contra esta orden; los cambios de la orden se hacen en la web.</AvisoComprasEnElNodo>
      <CompraDetalleComercio
        puedeEscribir={puede(user, 'compras.escribir') && !esNodo}
        puedeRecibir={puede(user, 'compras.recibir')}
      />
    </>
  )
}
