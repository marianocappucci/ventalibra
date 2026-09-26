// Clientes: la pantalla del kit (`libra-ui/comercio/Clientes`), la misma que monta Contalibra, sobre
// el router del motor (`/api/clientes`, ADR-029).
//
// Variante de VentaLibra: sin consulta del CUIT en ARCA (`conConsultaCuit={false}`): el endpoint
// `/api/consultar-cuit` es hoy código propio de Contalibra y Restolibra y todavía no está en el motor.
import { Clientes as ClientesComercio } from 'libra-ui/comercio/Clientes'

export function Clientes() {
  return <ClientesComercio conConsultaCuit={false} />
}
