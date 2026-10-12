// El `POST /api/listas-precio/{id}/precios` del motor (libracommerce ADR-048), para los tests del POS: cuenta las cantidades
// POR PRODUCTO, suma las líneas del mismo `producto_id` (con o sin variante) y devuelve una entrada por línea, en el mismo
// orden. `tabla` es la lista de precios del test: qué precio corresponde a esa cantidad de ese producto.
type Linea = { producto_id: number; variante_id: number | null; cantidad: number }

export function lineasDelPedido(init?: RequestInit): Linea[] {
  return (JSON.parse(String(init?.body ?? '{}')).lineas ?? []) as Linea[]
}

export function responderPrecios(init: RequestInit | undefined, tabla: (cantidadDelProducto: number, productoId: number) => number): Response {
  const lineas = lineasDelPedido(init)
  const total = new Map<number, number>()
  for (const l of lineas) if (l.cantidad > 0) total.set(l.producto_id, (total.get(l.producto_id) ?? 0) + l.cantidad)
  const precios = lineas.map((l) => ({
    producto_id: l.producto_id, variante_id: l.variante_id,
    cantidad_producto: total.get(l.producto_id) ?? 0, precio: tabla(total.get(l.producto_id) ?? 0, l.producto_id),
  }))
  return new Response(JSON.stringify({ precios }), { status: 200, headers: { 'content-type': 'application/json' } })
}
