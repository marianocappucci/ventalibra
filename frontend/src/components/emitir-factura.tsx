// El casillero «Emitir factura» del cobro del POS. Sin el módulo `facturacion` (con el plan único, ADR-072, sólo si se lo apagó en la instancia) se ofrece
// apagado y con el motivo: el backend contesta 403 a `/facturar`, y dejar marcarlo terminaba en una venta cobrada
// con un error de factura.
export function EmitirFactura({ marcado, disponible, onChange }: {
  marcado: boolean
  disponible: boolean
  onChange: (marcado: boolean) => void
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input
        type="checkbox" checked={marcado && disponible} disabled={!disponible}
        onChange={(e) => onChange(e.target.checked)}
      />
      Emitir factura
      {!disponible && <span className="text-muted-foreground">(no está habilitada en esta instancia; escribinos para activarla)</span>}
    </label>
  )
}
