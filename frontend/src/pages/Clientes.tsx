// Clientes: la pantalla del kit (`libra-ui/comercio/Clientes`), la misma que monta Contalibra, sobre
// el router del motor (`/api/clientes`, ADR-029).
//
// Fase 14 (ADR-040): `conConsultaCuit` pasa a su default (`true`) -- el motor ya tiene
// `build_consultar_cuit_router`, montado en `/api/consultar-cuit`.
import { Clientes as ClientesComercio } from 'libra-ui/comercio/Clientes'

export function Clientes() {
  return <ClientesComercio />
}
