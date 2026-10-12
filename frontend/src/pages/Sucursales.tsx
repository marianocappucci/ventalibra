// Las sucursales: la pantalla del kit (`libra-ui/comercio/Sucursales`), sobre el router del motor
// (`/api/sucursales`, modelo jerárquico sucursal → depósitos). Una sucursal agrupa depósitos: el stock vive en
// éstos, y «Ver depósitos» lleva al detalle de la sucursal.
//
// Variantes de VentaLibra, todas props del kit: el título propio, **sólo lectura** para quien no administra la estructura (el backend igual
// rechaza sus escrituras con 403) y las rutas del detalle y de la transferencia, que son las de este producto.
//
// **Un solo local (ADR-048, ADR-077).** Con el plan único (ADR-072) `multisucursal` viene prendido; si un administrador lo apagó, sin el módulo `multisucursal` el backend rechaza el alta de una segunda
// sucursal (403). `soloLectura` no sirve para anticiparlo —esconde también la edición, y renombrar la sucursal que ya
// existe tiene que seguir andando—, así que se le pasa al kit `motivoSinAlta` (libra-ui, ADR-052): «Nueva sucursal» queda
// deshabilitada y el motivo se lee debajo del título, en el lugar y con el estilo del aviso de las contratadas, **sin una caja
// aparte** (antes: una `AvisoModulo` más el rótulo «(sin activar)», dos avisos para lo mismo). El que corta es el backend,
// cuyo mensaje el kit muestra en el formulario si igual se llega al alta.
//
// **Sucursales contratadas (ADR-073 del producto, ADR-048 del kit, libra-ui 0.136.0).** `rutaDelLimite` le dice al kit dónde leer «activas vs
// contratadas» (`GET /api/limites/sucursales`, del motor): con tope muestra «N de M» y, al llegar, deshabilita «Nueva sucursal» con el motivo.
// Sólo lo lee el admin (la ruta es de `sucursales.admin` o del token de servicio): al resto no se le pide, para no provocar un 403 de más.
// Si la lectura falla, la pantalla queda como siempre; el que corta es el 409 del backend.
import { Sucursales as SucursalesComercio } from 'libra-ui/comercio/Sucursales'
import { useAuth } from '../context/AuthContext'
import { MULTISUCURSAL, useTieneModulo } from '../lib/modulos'
import { puede } from '../lib/permisos'

/** Por qué no se puede sumar otra sucursal sin el módulo `multisucursal` (el 403 del backend lo nombra; acá, en castellano de cliente). */
const MOTIVO_UN_SOLO_LOCAL =
  'Esta instancia es de un solo local: podés tener todos los depósitos que necesites dentro de él. Para sumar otra sucursal, escribinos para activarlo.'

export function Sucursales() {
  const { user } = useAuth()
  // El alta, la edición y la baja son de quien administra la estructura (`sucursales.admin`, sólo admin).
  const esAdmin = puede(user, 'sucursales.admin')
  const multisucursal = useTieneModulo(MULTISUCURSAL)
  return (
    <SucursalesComercio
      soloLectura={!esAdmin}
      titulo="Sucursales"
      rutaDelDetalle={(id) => `/sucursales/${id}`}
      rutaDeTransferencia="/transferencias"
      rutaDelLimite={esAdmin ? '/api/limites/sucursales' : undefined}
      motivoSinAlta={multisucursal ? undefined : MOTIVO_UN_SOLO_LOCAL}
    />
  )
}
