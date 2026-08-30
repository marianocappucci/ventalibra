// La FORMA de la pantalla de Configuración de este producto.
//
// La pantalla la rinde `libra-ui/Configuracion`, que tiene sus propios tests:
// lo que se prueba acá es **lo que declara VentaLibra**, que es lo único que
// vive en este repo y lo único que puede divergir del resto de la familia sin
// que nadie lo note.
//
// Dos declaraciones que si se escriben mal no rompen nada y arruinan la
// pantalla igual:
//
//  1. 🔴 **`webhook: false`.** Este producto NO tiene webhook de MercadoPago, y
//     está medido: en la instancia real del cliente no llegó ni un `POST` a
//     `/webhooks/mercadopago` —cero contra cinco al endpoint del poll— y el
//     cobro se resuelve poleando. Mostrar el campo del Webhook Secret manda al
//     comercio a configurar algo que no hace nada.
//  2. 🔴 **El slug de la empresa de ARCA.** `services/billing.py` lee la
//     configuración de facturación con `EMPRESA = "venta"`. En una instancia
//     sin fila, el primer guardado la crea: si la crea como `default`, ese
//     servicio no la lee nunca.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Configuracion } from '../pages/Configuracion'

let pedidos: { url: string; metodo: string; cuerpo: unknown }[] = []

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  pedidos = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    pedidos.push({ url: u, metodo, cuerpo: init?.body ?? null })

    if (u.includes('/logo')) return Promise.resolve(new Response('', { status: 404 }))
    if (u.includes('/admin/smtp')) {
      return Promise.resolve(json({
        origen: 'entorno', host: '', port: 587, user: '', from_email: '', from_name: '',
        password_definida: false, password_indescifrable: false, configurado: false,
      }))
    }
    if (u.includes('/api/config/mercadopago')) {
      return Promise.resolve(json({
        mp_access_token: '', mp_access_token_cargado: false,
        mp_webhook_secret: '', mp_webhook_secret_cargado: false,
        mp_concepto_descripcion: '', mp_iva_rate: '0',
        mp_user_id: '', mp_pos_id: '', mp_auto_facturar_ventas: false,
      }))
    }
    if (u.includes('/config/arca/estado')) return Promise.resolve(json({ configurado: false }))
    // Instancia nueva: todavía no hay fila de ARCA.
    if (u.includes('/config/arca')) return Promise.resolve(json(null))
    if (u.includes('/api/config/empresa')) {
      return Promise.resolve(json({
        empresa_nombre: '', empresa_direccion: '', empresa_cuit: '', empresa_telefono: '',
        empresa_email: '', empresa_iibb: '', empresa_iva_condition: 'Monotributista',
        empresa_inicio_actividades: '',
      }))
    }
    return Promise.resolve(json([]))
  }))
})

const montar = (ruta = '/configuracion') =>
  render(<MemoryRouter initialEntries={[ruta]}><Configuracion /></MemoryRouter>)

describe('la Configuración de VentaLibra', () => {
  it('tiene las pestañas de la familia, con las dos propias del mostrador', async () => {
    montar()

    const pestanias = (await screen.findAllByRole('tab')).map((t) => t.textContent)
    expect(pestanias).toEqual([
      'Empresa', 'Integraciones', 'Balanza', 'Ticket', 'Datos / Backup',
    ])
  })

  it('las tres integraciones están, en la sub-navegación', async () => {
    montar('/configuracion?seccion=integraciones')

    await screen.findAllByRole('tab')
    const navegacion = screen.getAllByRole('button', {
      name: /^(MercadoPago|ARCA \/ AFIP|Email \/ SMTP)$/,
    })
    expect(navegacion.map((b) => b.textContent)).toEqual([
      'MercadoPago', 'ARCA / AFIP', 'Email / SMTP',
    ])
  })

  it('🔴 MercadoPago no pide una firma para un webhook que este producto no tiene', async () => {
    montar('/configuracion?seccion=integraciones&integracion=mercadopago')

    // Los tres datos del QR sí, que son los que el POS necesita…
    expect(await screen.findByLabelText(/Access Token/)).toBeInTheDocument()
    expect(screen.getByLabelText(/User ID \(QR\)/)).toBeInTheDocument()
    expect(screen.getByLabelText(/POS ID \(QR\)/)).toBeInTheDocument()
    // …y nada del webhook, que acá no existe.
    expect(screen.queryByLabelText(/Webhook Secret/)).toBeNull()
    expect(screen.queryByText(/URL del webhook/)).toBeNull()
  })

  it('avisa que el QR no cobra mientras falte alguno de los tres', async () => {
    // Sin el aviso, una caja a medio configurar se descubre recién cuando un
    // cliente escanea el cartel impreso del mostrador y no pasa nada.
    montar('/configuracion?seccion=integraciones&integracion=mercadopago')

    expect(await screen.findByText(/Faltan datos/)).toBeInTheDocument()
  })

  it('🔴 la fila de ARCA se crea con el slug que lee `services/billing.py`', async () => {
    montar('/configuracion?seccion=integraciones&integracion=arca')
    const usuario = userEvent.setup()

    await usuario.click(await screen.findByRole('button', { name: /Guardar ARCA/ }))

    const put = pedidos.find((p) => p.url.includes('/config/arca') && p.metodo === 'PUT')
    expect(put, 'no llegó ningún PUT a /config/arca').toBeTruthy()
    expect(JSON.parse(String(put!.cuerpo)).empresa).toBe('venta')
  })

  it('ARCA sube el certificado: ya no hay dónde tipear una ruta del servidor', async () => {
    montar('/configuracion?seccion=integraciones&integracion=arca')

    expect(await screen.findByLabelText(/Certificado/)).toHaveAttribute('type', 'file')
    expect(screen.getByLabelText(/Clave privada/)).toHaveAttribute('type', 'file')
    expect(screen.queryByLabelText(/Path del certificado/)).toBeNull()
  })

  it('los tutoriales nombran a VentaLibra, no al producto del que salió la pantalla', async () => {
    montar('/configuracion?seccion=integraciones&integracion=email')

    expect(await screen.findAllByText(/contraseña de aplicación/)).not.toHaveLength(0)
    expect(screen.getByText('VentaLibra')).toBeInTheDocument()
    expect(screen.queryByText('Contalibra')).toBeNull()
  })

  it('el botón de backup rápido está desde la primera pestaña', async () => {
    montar()

    expect(await screen.findByRole('link', { name: /Backup rápido/ }))
      .toHaveAttribute('href', '/api/config/backup-ahora')
  })
})
