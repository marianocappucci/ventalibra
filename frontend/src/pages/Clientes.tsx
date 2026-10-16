// Clientes: la pantalla del kit (`libra-ui/comercio/Clientes`), la misma que monta Contalibra, sobre
// el router del motor (`/api/clientes`, ADR-029).
//
// Fase 14 (ADR-040): `conConsultaCuit` se prende -- el motor ya tiene `build_consultar_cuit_router`,
// montado en `/api/consultar-cuit`. 🔴 Pero sólo con el módulo `facturacion`: la consulta usa el
// certificado de ARCA, y sin el módulo no hay pantalla de ARCA donde cargarlo (el router da 403, igual
// que `/config/arca`; ver `app/main.py`). Con el plan único viene siempre prendido.
import { Clientes as ClientesComercio } from 'libra-ui/comercio/Clientes'
import { FACTURACION, useTieneModulo } from '../lib/modulos'

export function Clientes() {
  return <ClientesComercio conConsultaCuit={useTieneModulo(FACTURACION)} />
}
