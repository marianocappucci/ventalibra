import { useEffect, useState } from 'react'
import {
  api, ApiError, type CajaReport, type SalesReport, type StockReport,
} from '../api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { BadgeEstado } from 'libra-ui/badge-estado'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { BarChart3 } from 'lucide-react'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'

function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

function money(value: string): string {
  return Number(value).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function firstOfMonthIso(): string {
  const now = new Date()
  return new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10)
}

export function Reportes() {
  const [dateFrom, setDateFrom] = useState(firstOfMonthIso())
  const [dateTo, setDateTo] = useState(todayIso())
  const [sales, setSales] = useState<SalesReport | null>(null)
  const [caja, setCaja] = useState<CajaReport | null>(null)
  const [stock, setStock] = useState<StockReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadPeriodReports()
    loadStock()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function loadPeriodReports() {
    setLoading(true)
    setError(null)
    try {
      const [salesReport, cajaReport] = await Promise.all([
        api.get<SalesReport>(`/reports/sales?date_from=${dateFrom}&date_to=${dateTo}`),
        api.get<CajaReport>(`/reports/caja?date_from=${dateFrom}&date_to=${dateTo}`),
      ])
      setSales(salesReport)
      setCaja(cajaReport)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  async function loadStock() {
    try {
      setStock(await api.get<StockReport>('/reports/stock'))
    } catch (err) {
      setError(describeError(err))
    }
  }

  return (
    <div className="grid gap-4">
      <TituloPantalla icono={BarChart3}>Reportes</TituloPantalla>

      <Card>
        <CardContent className="flex flex-wrap items-end gap-2 pt-6">
          <div className="grid gap-1.5">
            <Label>Desde</Label>
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-40" />
          </div>
          <div className="grid gap-1.5">
            <Label>Hasta</Label>
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-40" />
          </div>
          <Button variant="outline" onClick={loadPeriodReports}>Actualizar</Button>
        </CardContent>
      </Card>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading ? (
        <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Ventas</CardTitle>
                <CardDescription>{dateFrom} a {dateTo}</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-2xl font-semibold">{sales?.total_ventas ?? 0}</p>
                    <p className="text-xs text-muted-foreground">Ventas confirmadas</p>
                  </div>
                  <div>
                    <p className="text-2xl font-semibold">${money(sales?.total_facturado ?? '0')}</p>
                    <p className="text-xs text-muted-foreground">Total facturado</p>
                  </div>
                </div>
                {sales && sales.top_items.length > 0 && (
                  <div>
                    <p className="mb-2 text-sm font-medium">Top items</p>
                    <Table>
                      <TableHeader>
                        <TableRow><TableHead>Item</TableHead><TableHead>Cant.</TableHead><TableHead className="text-right">Total</TableHead></TableRow>
                      </TableHeader>
                      <TableBody>
                        {sales.top_items.map((item) => (
                          <TableRow key={item.item_id}>
                            <TableCell>{item.descripcion}</TableCell>
                            <TableCell>{item.cantidad}</TableCell>
                            <TableCell className="text-right">${money(item.total)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Caja</CardTitle>
                <CardDescription>{dateFrom} a {dateTo}</CardDescription>
              </CardHeader>
              <CardContent className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-2xl font-semibold">${money(caja?.ingresos ?? '0')}</p>
                  <p className="text-xs text-muted-foreground">Ingresos del período</p>
                </div>
                <div>
                  <p className="text-2xl font-semibold">${money(caja?.egresos ?? '0')}</p>
                  <p className="text-xs text-muted-foreground">Egresos del período</p>
                </div>
                <div>
                  <p className="text-2xl font-semibold">${money(caja?.saldo_periodo ?? '0')}</p>
                  <p className="text-xs text-muted-foreground">Saldo del período</p>
                </div>
                <div>
                  <p className="text-2xl font-semibold">${money(caja?.saldo_total ?? '0')}</p>
                  <p className="text-xs text-muted-foreground">Saldo total de caja</p>
                </div>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Stock</CardTitle>
              <CardDescription>
                {stock ? `${stock.low_stock.length} item(s) con stock bajo o en cero` : ''}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow><TableHead>Item</TableHead><TableHead>Unidad</TableHead><TableHead className="text-right">Stock</TableHead></TableRow>
                </TableHeader>
                <TableBody>
                  {(stock?.items.length ?? 0) === 0 && (
                    <TableRow><TableCell colSpan={3} className="text-center text-sm text-muted-foreground">Sin productos todavía.</TableCell></TableRow>
                  )}
                  {stock?.items.map((item) => {
                    const isLow = stock.low_stock.some((low) => low.item_id === item.item_id)
                    return (
                      <TableRow key={item.item_id}>
                        <TableCell>{item.name}</TableCell>
                        <TableCell>{item.unit_code}</TableCell>
                        <TableCell className="text-right">
                          <BadgeEstado tono={isLow ? 'negativo' : 'neutro'}>{item.stock}</BadgeEstado>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
