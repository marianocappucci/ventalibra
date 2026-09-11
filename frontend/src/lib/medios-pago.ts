/** Shim: los medios de pago salen del backend por el hook del kit
 *  (`libra-ui/comercio/medios-pago`), igual que en Contalibra y Restolibra.
 *  Hasta el 2026-09-11 este producto tenía tres listas propias —POS,
 *  devolución y cobranza— y ninguna ofrecía Cuenta DNI, otras billeteras ni
 *  cheque. Las pantallas lo importan de acá. */
export { useMediosPago, useEtiquetaDeMedio, _resetCacheDeMedios, type MedioPago } from 'libra-ui/comercio/medios-pago'
