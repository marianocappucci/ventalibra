// Las cajas: la pantalla del kit (`libra-ui/comercio/Cajas`), la misma que monta Contalibra, sobre el router
// del motor (`/api/cajas`, ADR-032).
//
// Variantes de VentaLibra, todas props del kit: la caja pertenece a una **sucursal** (se elige al crearla, la
// lista se filtra por sucursal, y las cajas nuevas van a una sucursal activa: un depósito no es una sucursal), se puede
// **activar y desactivar** desde la tarjeta (una caja con movimientos no se elimina) y no hay pantalla de
// movimientos de caja, así que no se ofrece el enlace.
import { useEffect, useState } from 'react'
import { Cajas as CajasComercio, type SucursalDeCaja } from 'libra-ui/comercio/Cajas'
import { api, type Sucursal } from '../api'

export function Cajas() {
  // `null` hasta que llegan: sin esto la pantalla arranca sin sucursales y se comporta como la de un producto
  // sin sedes durante un instante.
  const [sucursales, setSucursales] = useState<SucursalDeCaja[] | null>(null)

  useEffect(() => {
    // `/api/sucursales` trae sólo las activas: las que pueden recibir una caja nueva.
    api.get<Sucursal[]>('/api/sucursales')
      .then((locs) => setSucursales(locs.map((l) => ({ id: l.id, nombre: l.nombre }))))
      .catch(() => setSucursales([]))
  }, [])

  if (sucursales === null) return <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
  return <CajasComercio sucursales={sucursales} conActivarDesactivar verMovimientos={false} />
}
