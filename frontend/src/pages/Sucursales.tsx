// Las sucursales: la pantalla del kit (`libra-ui/comercio/Sucursales`), sobre el router del motor
// (`/api/sucursales`, modelo jerárquico sucursal → depósitos). Una sucursal agrupa depósitos: el stock vive en
// éstos, y «Ver depósitos» lleva al detalle de la sucursal.
//
// Variantes de VentaLibra, todas props del kit: el título propio, **sólo lectura** para el cajero (el backend igual
// rechaza sus escrituras con 403) y las rutas del detalle y de la transferencia, que son las de este producto.
//
// **Plan Básico (ADR-048): un solo local.** Sin el módulo `multisucursal` el backend rechaza el alta de una segunda
// sucursal (403). El kit no tiene una prop para apagar sólo ese botón —`soloLectura` esconde también la edición, y
// renombrar la sucursal que ya existe tiene que seguir andando—, así que acá se avisa arriba y el botón lo dice; el
// que corta es el backend, cuyo mensaje el kit muestra en el formulario.
import { Sucursales as SucursalesComercio } from 'libra-ui/comercio/Sucursales'
import { AvisoPremium } from '../components/aviso-premium'
import { useAuth } from '../context/AuthContext'
import { MULTISUCURSAL, useTieneModulo } from '../lib/modulos'

export function Sucursales() {
  const { user } = useAuth()
  const esAdmin = user?.role === 'admin'
  const multisucursal = useTieneModulo(MULTISUCURSAL)
  return (
    <div className="grid gap-4">
      {esAdmin && !multisucursal && (
        <AvisoPremium titulo="Más de una sucursal">
          El plan Básico es para un solo local: podés tener todos los depósitos que necesites dentro de él. Las
          sucursales que ya estén cargadas siguen funcionando; dar de alta otra y mover mercadería entre sucursales
          es del plan Premium.
        </AvisoPremium>
      )}
      <SucursalesComercio
        soloLectura={!esAdmin}
        titulo="Sucursales"
        etiquetaNuevo={multisucursal ? 'Nueva sucursal' : 'Nueva sucursal (Premium)'}
        rutaDelDetalle={(id) => `/sucursales/${id}`}
        rutaDeTransferencia="/transferencias"
      />
    </div>
  )
}
