/** Configuración de VentaLibra (ítem 5, 2026-08-05).
 *
 *  Antes eran **tres pantallas sueltas** colgando del menú lateral —ARCA,
 *  Balanza y Ticket—, sin nada que las relacionara y sin dónde poner los datos
 *  de la empresa ni el backup. Ahora son secciones de una sola pantalla.
 *
 *  El armado y las cuatro secciones comunes vienen de `libra-ui/Configuracion`;
 *  acá se declara **lo que corresponde a este producto**, que es el punto del
 *  pedido. VentaLibra factura (ARCA), imprime tickets y usa balanza; MedLibra
 *  no hace ninguna de las tres.
 */
import {
  SECCIONES_BASE, SECCION_ARCA, createConfiguracion,
} from 'libra-ui/Configuracion'
import { Printer, Scale, Settings } from 'lucide-react'

import { ConfigBalanza } from './ConfigBalanza'
import { ConfigTicket } from './ConfigTicket'

export const Configuracion = createConfiguracion({
  // El icono que el sidebar de este producto le da a /configuracion.
  icono: Settings,
  secciones: [
    // empresa (+logo), correo (SMTP) y Datos / Backup
    ...SECCIONES_BASE,
    SECCION_ARCA,
    // Las dos propias. Se quedan en el producto y no suben al paquete: la
    // balanza es de un comercio con mostrador y el formato de etiqueta que
    // parsea es específico de acá; ningún otro vertical de la familia las
    // tiene.
    { clave: 'balanza', label: 'Balanza', icono: Scale, contenido: <ConfigBalanza /> },
    { clave: 'ticket', label: 'Ticket', icono: Printer, contenido: <ConfigTicket /> },
  ],
})
