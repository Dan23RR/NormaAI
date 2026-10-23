/**
 * Number parsing and formatting for the scope form. The parser is a port of
 * toNum() in public/scope-csrd.html: it accepts Italian thousands separators
 * ("1.200", "450.000.000"), a decimal comma ("1,5") and plain digits.
 */

export function parseItNumber(raw: string | number | null | undefined): number | null {
  if (raw == null) return null
  if (typeof raw === 'number') return Number.isFinite(raw) ? raw : null
  let s = String(raw).trim().replace(/\s/g, '').replace(/€/g, '')
  if (s === '') return null
  if (s.includes(',')) {
    s = s.replace(/\./g, '').replace(',', '.')
  } else if (/^\d{1,3}(\.\d{3})+$/.test(s)) {
    s = s.replace(/\./g, '')
  } else if (/^\d+\.\d{1,2}$/.test(s)) {
    // decimal point kept: "12.5"
  } else {
    s = s.replace(/\./g, '')
  }
  const n = parseFloat(s.replace(/[^0-9.]/g, ''))
  return Number.isFinite(n) ? n : null
}

const decFmt = new Intl.NumberFormat('it-IT', { maximumFractionDigits: 1 })

/** Groups thousands with a dot, also for four-digit numbers (Intl in it-IT writes "1200"). */
function groupIt(n: number): string {
  const sign = n < 0 ? '-' : ''
  const digits = String(Math.abs(Math.round(n)))
  return sign + digits.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
}

/** "1.200" */
export function formatInt(n: number): string {
  return groupIt(n)
}

/** "450.000.000 €" */
export function formatEur(n: number): string {
  return `${groupIt(n)} €`
}

/** "450 milioni di euro", "1,5 miliardi di euro". */
export function formatMillionsEur(n: number): string {
  if (n >= 1_000_000_000) {
    const v = Math.round((n / 1_000_000_000) * 10) / 10
    return v === 1 ? '1 miliardo di euro' : `${decFmt.format(v)} miliardi di euro`
  }
  const v = Math.round((n / 1_000_000) * 10) / 10
  return v === 1 ? '1 milione di euro' : `${decFmt.format(v)} milioni di euro`
}
