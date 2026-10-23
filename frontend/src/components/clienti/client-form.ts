import type { Client } from '@/lib/types'
import type { ClientPayload } from './clients-api'

/** The form keeps strings: validation decides what becomes a number. */
export interface ClientFormValues {
  name: string
  sector: string
  employee_count: string
  revenue_eur: string
  jurisdictions: string
  applicable_frameworks: string[]
}

export type ClientFormErrors = Partial<Record<keyof ClientFormValues, string>>

export function emptyClientForm(): ClientFormValues {
  return {
    name: '',
    sector: '',
    employee_count: '',
    revenue_eur: '',
    jurisdictions: '',
    applicable_frameworks: [],
  }
}

export function clientToForm(client: Client): ClientFormValues {
  return {
    name: client.name ?? '',
    sector: client.sector ?? '',
    employee_count: typeof client.employee_count === 'number' ? String(client.employee_count) : '',
    revenue_eur: typeof client.revenue_eur === 'number' ? String(client.revenue_eur) : '',
    jurisdictions: (client.jurisdictions ?? []).join(', '),
    applicable_frameworks: [...(client.applicable_frameworks ?? [])],
  }
}

const INTEGER = /^\d+$/
const COUNTRY_CODE = /^[A-Z]{2}$/

export function parseJurisdictions(raw: string): string[] {
  return raw
    .split(/[,;\s]+/)
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean)
}

export function validateClientForm(values: ClientFormValues): ClientFormErrors {
  const errors: ClientFormErrors = {}
  const name = values.name.trim()
  if (!name) errors.name = 'Inserisci il nome del cliente.'
  else if (name.length > 255) errors.name = 'Il nome può avere al massimo 255 caratteri.'

  if (values.sector.trim().length > 100) errors.sector = 'Il settore può avere al massimo 100 caratteri.'

  const employees = values.employee_count.trim()
  if (employees && !INTEGER.test(employees)) {
    errors.employee_count = 'Inserisci il numero di dipendenti come intero, zero o più.'
  }

  const revenue = values.revenue_eur.trim()
  if (revenue && !INTEGER.test(revenue)) {
    errors.revenue_eur = 'Inserisci il fatturato annuo in euro, senza decimali.'
  }

  const invalidCodes = parseJurisdictions(values.jurisdictions).filter((c) => !COUNTRY_CODE.test(c))
  if (invalidCodes.length > 0) {
    errors.jurisdictions = `Usa codici Paese di due lettere separati da virgola, per esempio IT, DE. Non validi: ${invalidCodes.join(', ')}.`
  }

  return errors
}

export function formToPayload(values: ClientFormValues): ClientPayload {
  const employees = values.employee_count.trim()
  const revenue = values.revenue_eur.trim()
  return {
    name: values.name.trim(),
    sector: values.sector.trim() || null,
    employee_count: employees ? Number(employees) : null,
    revenue_eur: revenue ? Number(revenue) : null,
    jurisdictions: parseJurisdictions(values.jurisdictions),
    applicable_frameworks: values.applicable_frameworks,
  }
}
