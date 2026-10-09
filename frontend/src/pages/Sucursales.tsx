// Las sucursales: la pantalla del kit (`libra-ui/comercio/Sucursales`), sobre el router del motor
// (`/api/sucursales`, modelo jerárquico sucursal → depósitos). Una sucursal agrupa depósitos: el stock vive en
// éstos, y «Ver depósitos» lleva al detalle de la sucursal.
//
// Variantes de VentaLibra, todas props del kit: el título propio, **sólo lectura** para quien no administra la estructura (el backend igual
// rechaza sus escrituras con 403) y las rutas del detalle y de la transferencia, que son las de este producto.
//
// **Un solo local (ADR-048).** Con el plan único (ADR-072) `multisucursal` viene prendido; si un administrador lo apagó, sin el módulo `multisucursal` el backend rechaza el alta de una segunda
// sucursal (403). El kit no tiene una prop para apagar sólo ese botón —`soloLectura` esconde también la edición, y
// renombrar la sucursal que ya existe tiene que seguir andando—, así que acá se avisa arriba y el botón lo dice; el
// que corta es el backend, cuyo mensaje el kit muestra en el formulario.
import { Sucursales as SucursalesComercio } from 'libra-ui/comercio/Sucursales'
import { AvisoModulo } from '../components/aviso-modulo'
import { useAuth } from '../context/AuthContext'
import { MULTISUCURSAL, useTieneModulo } from '../lib/modulos'
import { puede } from '../lib/permisos'

export function Sucursales() {
  const { user } = useAuth()
  // El alta, la edición y la baja son de quien administra la estructura (`sucursales.admin`, sólo admin).
  const esAdmin = puede(user, 'sucursales.admin')
  const multisucursal = useTieneModulo(MULTISUCURSAL)
  return (
    <div className="grid gap-4">
      {esAdmin && !multisucursal && (
        <AvisoModulo titulo="Más de una sucursal">
          Esta instancia es de un solo local: podés tener todos los depósitos que necesites dentro de él. Las
          sucursales que ya estén cargadas siguen funcionando; para dar de alta otra y mover mercadería entre
          sucursales, escribinos para activarlo.
        </AvisoModulo>
      )}
      <SucursalesComercio
        soloLectura={!esAdmin}
        titulo="Sucursales"
        etiquetaNuevo={multisucursal ? 'Nueva sucursal' : 'Nueva sucursal (sin activar)'}
        rutaDelDetalle={(id) => `/sucursales/${id}`}
        rutaDeTransferencia="/transferencias"
      />
    </div>
  )
}
