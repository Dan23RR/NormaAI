'use client'

import { Button } from '@/components/ui/Button'
import { Checkbox, Field, Input, Select } from '@/components/ui/Field'
import { formatInt } from '@/lib/scope/format'
import { EMPTY_INPUT, NO_AI, aiToKeys, keysToAi } from '@/lib/scope/query'
import type { AiKey, GroupRole, ScopeInput } from '@/lib/scope/types'
import { NumberField } from './NumberField'
import type { ClientOption } from './clients'

export const EU_COUNTRIES: Array<{ code: string; name: string }> = [
  { code: 'AT', name: 'Austria' },
  { code: 'BE', name: 'Belgio' },
  { code: 'BG', name: 'Bulgaria' },
  { code: 'CY', name: 'Cipro' },
  { code: 'HR', name: 'Croazia' },
  { code: 'DK', name: 'Danimarca' },
  { code: 'EE', name: 'Estonia' },
  { code: 'FI', name: 'Finlandia' },
  { code: 'FR', name: 'Francia' },
  { code: 'DE', name: 'Germania' },
  { code: 'GR', name: 'Grecia' },
  { code: 'IE', name: 'Irlanda' },
  { code: 'IT', name: 'Italia' },
  { code: 'LV', name: 'Lettonia' },
  { code: 'LT', name: 'Lituania' },
  { code: 'LU', name: 'Lussemburgo' },
  { code: 'MT', name: 'Malta' },
  { code: 'NL', name: 'Paesi Bassi' },
  { code: 'PL', name: 'Polonia' },
  { code: 'PT', name: 'Portogallo' },
  { code: 'CZ', name: 'Repubblica Ceca' },
  { code: 'RO', name: 'Romania' },
  { code: 'SK', name: 'Slovacchia' },
  { code: 'SI', name: 'Slovenia' },
  { code: 'ES', name: 'Spagna' },
  { code: 'SE', name: 'Svezia' },
  { code: 'HU', name: 'Ungheria' },
]

/** The three example companies of public/scope-csrd.html and the Codex, ch. 2.1. */
const EXAMPLES: Array<{ employees: number; turnoverEur: number }> = [
  { employees: 600, turnoverEur: 120_000_000 },
  { employees: 1200, turnoverEur: 380_000_000 },
  { employees: 1500, turnoverEur: 620_000_000 },
]

const AI_QUESTIONS: Array<{ key: AiKey; label: string; description: string }> = [
  {
    key: 'chat',
    label: 'Un sistema di IA interagisce direttamente con persone',
    description: 'Chatbot, assistenti virtuali, voicebot rivolti a clienti, utenti o dipendenti.',
  },
  {
    key: 'gen',
    label: 'Generate contenuti sintetici: testo, immagini, audio o video',
    description: 'Strumenti di IA generativa offerti ai vostri utenti o integrati nei vostri prodotti.',
  },
  {
    key: 'emo',
    label: 'Usate riconoscimento delle emozioni o categorizzazione biometrica',
    description: 'Per esempio su clienti, utenti o personale (analisi del tono, del volto, del comportamento).',
  },
  {
    key: 'deep',
    label: 'Pubblicate deepfake o testi generati dall’IA per informare il pubblico',
    description: 'Immagini, audio o video generati o manipolati, o testi generati dall’IA su temi di interesse pubblico.',
  },
]

export function ScopeForm({
  value,
  onChange,
  onSubmit,
  onReset,
  clients,
  clientsLoading,
  onLoadClient,
  error,
}: {
  value: ScopeInput
  onChange: (next: ScopeInput) => void
  onSubmit: () => void
  onReset: () => void
  clients: ClientOption[]
  clientsLoading: boolean
  onLoadClient: (id: string) => void
  error?: string
}) {
  const set = <K extends keyof ScopeInput>(key: K, v: ScopeInput[K]) => onChange({ ...value, [key]: v })

  const aiKeys = value.ai ? aiToKeys(value.ai) : []
  const noneChecked = value.ai != null && aiKeys.length === 0

  const toggleAi = (key: AiKey, checked: boolean) => {
    const next = checked ? [...aiKeys, key] : aiKeys.filter((k) => k !== key)
    set('ai', keysToAi(next))
  }

  return (
    <form
      noValidate
      className="space-y-6"
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit()
      }}
    >
      {(clients.length > 0 || clientsLoading) && (
        <Field
          label="Carica da un cliente"
          htmlFor="scope-client"
          help="Compila dipendenti, ricavi, settore e Paese dal profilo del cliente. Puoi poi modificarli."
        >
          <Select
            id="scope-client"
            defaultValue=""
            disabled={clientsLoading}
            onChange={(e) => {
              if (e.target.value) onLoadClient(e.target.value)
            }}
          >
            <option value="">{clientsLoading ? 'Caricamento dei clienti' : 'Scegli un cliente'}</option>
            {clients.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
      )}

      <Field label="Nome dell’impresa" htmlFor="scope-name" help="Facoltativo: compare nel risultato copiato.">
        <Input
          id="scope-name"
          value={value.name ?? ''}
          onChange={(e) => set('name', e.target.value)}
          placeholder="Per esempio Acme Srl"
          maxLength={200}
          autoComplete="organization"
        />
      </Field>

      <div className="grid gap-4 sm:grid-cols-2">
        <NumberField
          id="scope-employees"
          label="Dipendenti"
          help="Numero medio annuo, a livello dell’entità o del gruppo consolidato."
          value={value.employees}
          onChange={(n) => set('employees', n)}
          placeholder="Es. 850"
          suffix="dipendenti"
        />
        <NumberField
          id="scope-turnover"
          label="Ricavi netti annui"
          help="In euro, per esempio 450.000.000."
          value={value.turnoverEur}
          onChange={(n) => set('turnoverEur', n)}
          placeholder="Es. 300.000.000"
          suffix="€"
        />
      </div>

      <div className="flex flex-wrap items-center gap-2 text-small text-ink-3">
        <span>Prova con un esempio:</span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex.employees}
            type="button"
            onClick={() => onChange({ ...value, employees: ex.employees, turnoverEur: ex.turnoverEur })}
            className="rounded-md border border-rule bg-surface px-2.5 py-1 text-small tabular text-ink-2 hover:border-rule-2 hover:text-ink"
          >
            {formatInt(ex.employees)} dipendenti, {formatInt(ex.turnoverEur / 1_000_000)} milioni
          </button>
        ))}
      </div>

      <div className="space-y-3">
        <Checkbox
          id="scope-listed"
          label="Quotata in un mercato regolamentato UE"
          description="Le PMI quotate sono escluse dal nuovo perimetro, ma restano casi di confine."
          checked={value.listedEu}
          onChange={(e) => set('listedEu', e.target.checked)}
        />
        <Checkbox
          id="scope-wave1"
          label="Già soggetta a rendicontazione di sostenibilità (Wave 1 / NFRD, esercizio 2024)"
          description="Per i reporter Wave 1 l’Omnibus I prevede un’esenzione transitoria per gli esercizi 2025 e 2026."
          checked={value.wave1Reporter}
          onChange={(e) => set('wave1Reporter', e.target.checked)}
        />
        <Checkbox
          id="scope-noneu"
          label="Sede fuori dall’Unione europea"
          description="Per le imprese di Paesi terzi conta il fatturato realizzato nell’Unione."
          checked={value.nonEu}
          onChange={(e) => set('nonEu', e.target.checked)}
        />
      </div>

      {value.nonEu && (
        <NumberField
          id="scope-eu-turnover"
          label="Ricavi netti realizzati nell’Unione"
          help="Soglia del Codex per le imprese di Paesi terzi: 450 milioni di euro."
          value={value.euTurnoverEur}
          onChange={(n) => set('euTurnoverEur', n)}
          placeholder="Es. 500.000.000"
          suffix="€"
        />
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Ruolo nel gruppo" htmlFor="scope-group">
          <Select id="scope-group" value={value.groupRole} onChange={(e) => set('groupRole', e.target.value as GroupRole)}>
            <option value="standalone">Società singola</option>
            <option value="parent">Capogruppo con bilancio consolidato</option>
            <option value="subsidiary">Società controllata</option>
          </Select>
        </Field>
        <Field label="Paese" htmlFor="scope-country">
          <Select id="scope-country" value={value.country ?? ''} onChange={(e) => set('country', e.target.value)}>
            {EU_COUNTRIES.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
            <option value="ALTRO">Altro Paese</option>
          </Select>
        </Field>
      </div>

      <Field label="Settore" htmlFor="scope-sector" help="Facoltativo: non cambia il risultato, resta nel profilo.">
        <Input
          id="scope-sector"
          value={value.sector ?? ''}
          onChange={(e) => set('sector', e.target.value)}
          placeholder="Per esempio manifattura, servizi finanziari"
          maxLength={100}
        />
      </Field>

      <fieldset className="space-y-3 border-t border-rule pt-5">
        <legend className="text-h4">Intelligenza artificiale (AI Act, art. 50)</legend>
        <p className="text-small text-ink-2">
          Spunta ciò che vale per l’impresa, sia che il sistema lo offriate voi (fornitore) sia che lo usiate da
          terzi (utilizzatore): il risultato distingue i due casi.
        </p>
        {AI_QUESTIONS.map((q) => (
          <Checkbox
            key={q.key}
            id={`scope-ai-${q.key}`}
            label={q.label}
            description={q.description}
            checked={aiKeys.includes(q.key)}
            onChange={(e) => toggleAi(q.key, e.target.checked)}
          />
        ))}
        <Checkbox
          id="scope-ai-none"
          label="Nessuna delle quattro situazioni ci riguarda"
          description="Senza una risposta, l’AI Act resta non valutato."
          checked={noneChecked}
          onChange={(e) => set('ai', e.target.checked ? NO_AI : null)}
        />
      </fieldset>

      {error && (
        <p className="text-small text-bad" role="alert">
          {error}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <Button type="submit">Verifica l’ambito</Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            onReset()
            onChange(EMPTY_INPUT)
          }}
        >
          Azzera il modulo
        </Button>
      </div>
    </form>
  )
}
