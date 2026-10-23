'use client'

import { useFormatter, useLocale, useTranslations } from 'next-intl'
import { Button } from '@/components/ui/Button'
import { Checkbox, Field, Input, Select } from '@/components/ui/Field'
import { INT } from '@/i18n/format'
import { EMPTY_INPUT, NO_AI, aiToKeys, keysToAi } from '@/lib/scope/query'
import type { AiKey, GroupRole, ScopeInput } from '@/lib/scope/types'
import { NumberField } from './NumberField'
import type { ClientOption } from './clients'

/** The EU Member States; the names live in the `ui.countries` messages. */
export const EU_COUNTRY_CODES = [
  'AT', 'BE', 'BG', 'CY', 'HR', 'DK', 'EE', 'FI', 'FR', 'DE', 'GR', 'IE', 'IT', 'LV',
  'LT', 'LU', 'MT', 'NL', 'PL', 'PT', 'CZ', 'RO', 'SK', 'SI', 'ES', 'SE', 'HU',
] as const

/** The three example companies of public/scope-csrd.html and the Codex, ch. 2.1. */
const EXAMPLES: Array<{ employees: number; turnoverEur: number }> = [
  { employees: 600, turnoverEur: 120_000_000 },
  { employees: 1200, turnoverEur: 380_000_000 },
  { employees: 1500, turnoverEur: 620_000_000 },
]

const AI_QUESTIONS: AiKey[] = ['chat', 'gen', 'emo', 'deep']
const GROUP_ROLES: GroupRole[] = ['standalone', 'parent', 'subsidiary']

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
  const t = useTranslations('ambito.form')
  const tu = useTranslations('ui')
  const locale = useLocale()
  const format = useFormatter()
  const set = <K extends keyof ScopeInput>(key: K, v: ScopeInput[K]) => onChange({ ...value, [key]: v })

  const aiKeys = value.ai ? aiToKeys(value.ai) : []
  const noneChecked = value.ai != null && aiKeys.length === 0

  const toggleAi = (key: AiKey, checked: boolean) => {
    const next = checked ? [...aiKeys, key] : aiKeys.filter((k) => k !== key)
    set('ai', keysToAi(next))
  }

  const countries = EU_COUNTRY_CODES.map((code) => ({ code, name: tu(`countries.${code}`) })).sort((a, b) =>
    a.name.localeCompare(b.name, locale),
  )

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
        <Field label={t('loadClient')} htmlFor="scope-client" help={t('loadClientHelp')}>
          <Select
            id="scope-client"
            defaultValue=""
            disabled={clientsLoading}
            onChange={(e) => {
              if (e.target.value) onLoadClient(e.target.value)
            }}
          >
            <option value="">{clientsLoading ? t('loadingClients') : t('chooseClient')}</option>
            {clients.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
      )}

      <Field label={t('name')} htmlFor="scope-name" help={t('nameHelp')}>
        <Input
          id="scope-name"
          value={value.name ?? ''}
          onChange={(e) => set('name', e.target.value)}
          placeholder={t('namePlaceholder')}
          maxLength={200}
          autoComplete="organization"
        />
      </Field>

      <div className="grid gap-4 sm:grid-cols-2">
        <NumberField
          id="scope-employees"
          label={t('employees')}
          help={t('employeesHelp')}
          value={value.employees}
          onChange={(n) => set('employees', n)}
          placeholder={t('employeesPlaceholder')}
          suffix={t('employeesSuffix')}
        />
        <NumberField
          id="scope-turnover"
          label={t('turnover')}
          help={t('turnoverHelp')}
          value={value.turnoverEur}
          onChange={(n) => set('turnoverEur', n)}
          placeholder={t('turnoverPlaceholder')}
          suffix="€"
        />
      </div>

      <div className="flex flex-wrap items-center gap-2 text-small text-ink-3">
        <span>{t('examples')}</span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex.employees}
            type="button"
            onClick={() => onChange({ ...value, employees: ex.employees, turnoverEur: ex.turnoverEur })}
            className="rounded-md border border-rule bg-surface px-2.5 py-1 text-small tabular text-ink-2 hover:border-rule-2 hover:text-ink"
          >
            {t('example', {
              employees: format.number(ex.employees, INT),
              millions: format.number(ex.turnoverEur / 1_000_000, INT),
            })}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        <Checkbox
          id="scope-listed"
          label={t('listed')}
          description={t('listedHelp')}
          checked={value.listedEu}
          onChange={(e) => set('listedEu', e.target.checked)}
        />
        <Checkbox
          id="scope-wave1"
          label={t('wave1')}
          description={t('wave1Help')}
          checked={value.wave1Reporter}
          onChange={(e) => set('wave1Reporter', e.target.checked)}
        />
        <Checkbox
          id="scope-noneu"
          label={t('nonEu')}
          description={t('nonEuHelp')}
          checked={value.nonEu}
          onChange={(e) => set('nonEu', e.target.checked)}
        />
      </div>

      {value.nonEu && (
        <NumberField
          id="scope-eu-turnover"
          label={t('euTurnover')}
          help={t('euTurnoverHelp')}
          value={value.euTurnoverEur}
          onChange={(n) => set('euTurnoverEur', n)}
          placeholder={t('euTurnoverPlaceholder')}
          suffix="€"
        />
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t('groupRole')} htmlFor="scope-group">
          <Select id="scope-group" value={value.groupRole} onChange={(e) => set('groupRole', e.target.value as GroupRole)}>
            {GROUP_ROLES.map((role) => (
              <option key={role} value={role}>
                {t(`groupRoles.${role}`)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t('country')} htmlFor="scope-country">
          <Select id="scope-country" value={value.country ?? ''} onChange={(e) => set('country', e.target.value)}>
            {countries.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
            <option value="ALTRO">{tu('countries.other')}</option>
          </Select>
        </Field>
      </div>

      <Field label={t('sector')} htmlFor="scope-sector" help={t('sectorHelp')}>
        <Input
          id="scope-sector"
          value={value.sector ?? ''}
          onChange={(e) => set('sector', e.target.value)}
          placeholder={t('sectorPlaceholder')}
          maxLength={100}
        />
      </Field>

      <fieldset className="space-y-3 border-t border-rule pt-5">
        <legend className="text-h4">{t('ai.legend')}</legend>
        <p className="text-small text-ink-2">{t('ai.intro')}</p>
        {AI_QUESTIONS.map((key) => (
          <Checkbox
            key={key}
            id={`scope-ai-${key}`}
            label={t(`ai.${key}.label`)}
            description={t(`ai.${key}.description`)}
            checked={aiKeys.includes(key)}
            onChange={(e) => toggleAi(key, e.target.checked)}
          />
        ))}
        <Checkbox
          id="scope-ai-none"
          label={t('ai.none')}
          description={t('ai.noneHelp')}
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
        <Button type="submit">{t('submit')}</Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            onReset()
            onChange(EMPTY_INPUT)
          }}
        >
          {t('reset')}
        </Button>
      </div>
    </form>
  )
}
