import { SucursalSinInternet as Compartida } from 'libra-ui/SucursalSinInternet'

// «Sucursal sin internet» (libra-ui ADR-080, libraedge ADR-011): el alta del nodo de LibraEdge de cada sucursal, con el
// instalador y la carga del nodo. La pantalla vive en el kit; el backend es `create_nodos_router` (app/main.py).
export function SucursalSinInternet() {
  return <Compartida />
}
