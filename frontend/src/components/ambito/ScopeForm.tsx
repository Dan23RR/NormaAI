'use client'

import type { ReactNode } from 'react'
import { useFormatter, useLocale, useTranslations } from 'next-intl'
import { Button } from '@/components/ui/Button'
import { Checkbox, Field, Input, Select } from '@/components/ui/Field'
import { INT } from '@/i18n/format'
import {
  EMPTY_INPUT,
  NO_AI,
  NO_MACHINERY,
  NO_NIS,
  NO_WORK_AI,
  aiToKeys,
  keysToAi,
  keysToMachinery,
  keysToWork,
  machineryToKeys,
  workToKeys,
} from '@/lib/scope/query'
import type { AiKey, GroupRole, MachineryKey, NisSector, ScopeInput, WorkKey } from '@/lib/scope/types'
import { NIS_ANNEX_I, NIS_ANNEX_II, NIS_SECTORS } from '@/lib/scope/types'
import { NumberField } from './NumberField'
import type { ClientOption } from './clients'

/** The EU Member States; the names live in the `ui.countries` messages. */
export const EU_COUNTRY_CODES = [
  'AT', 'BE', 'BG', 'CY', 'HR', 'DK', 'EE', 'FI', 'FR', 'DE', 'GR', 'IE', 'IT', 'LV',
  'LT', 'LU', 'MT', 'NL', 'PL', 'PT', 'CZ', 'RO', 'SK', 'SI', 'ES', 'SE', 'HU',
] as const

/** Three sizes to try the form with: a small manufacturer, a medium company, a group above the CSRD thresholds. */
const EXAMPLES: Array<{ employees: number; turnoverEur: number }> = [
  { employees: 60, turnoverEur: 12_000_000 },
  { employees: 600, turnoverEur: 120_000_000 },
  { employees: 1500, turnoverEur: 620_000_000 },
]

const AI_QUESTIONS: AiKey[] = ['chat', 'gen', 'emo', 'deep']
const WORK_QUESTIONS: WorkKey[] = ['dec', 'org', 'uso', 'prof', 'emo']
const MACHINERY_QUESTIONS: MachineryKey[] = ['fab', 'imp', 'dis', 'mod']
const GROUP_ROLES: GroupRole[] = ['standalone', 'parent', 'subsidiary']
const NIS_OTHER: NisSector[] = ['pa', 'altri', 'nessuno']

/**
 * A group of yes/no situations with a last box "none of these": null until
 * the person answers, so an untouched group is never read as "none".
 */
function CheckGroup<K extends string>({
  name,
  legend,
  intro,
  keys,
  selected,
  answered,
  onChange,
  text,
}: {
  name: string
  legend: string
  intro: string
  keys: K[]
  selected: K[]
  answered: boolean
  /** The selected keys, or null when the answer is withdrawn. */
  onChange: (keys: K[] | null) => void
  text: (key: string) => string
}) {
  const noneChecked = answered && selected.length === 0
  return (
    <fieldset className="space-y-3 border-t border-rule pt-5">
      <legend className="text-h4">{legend}</legend>
      <p className="text-small text-ink-2">{intro}</p>
      {keys.map((key) => (
        <Checkbox
          key={key}
          id={`scope-${name}-${key}`}
          label={text(`${key}.label`)}
          description={text(`${key}.description`)}
          checked={selected.includes(key)}
          onChange={(e) => onChange(e.target.checked ? [...selected, key] : selected.filter((k) => k !== key))}
        />
      ))}
      <Checkbox
        id={`scope-${name}-none`}
        label={text('none')}
        description={text('noneHelp')}
        checked={noneChecked}
        onChange={(e) => onChange(e.target.checked ? [] : null)}
      />
    </fieldset>
  )
}

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
  const ts = useTranslations('ambito.nis.sectors')
  const tu = useTranslations('ui')
  const locale = useLocale()
  const format = useFormatter()
  const set = <K extends keyof ScopeInput>(key: K, v: ScopeInput[K]) => onChange({ ...value, [key]: v })

  const countries = EU_COUNTRY_CODES.map((code) => ({ code, name: tu(`countries.${code}`) })).sort((a, b) =>
    a.name.localeCompare(b.name, locale),
  )
  const sectorOption = (sector: NisSector): ReactNode => (
    <option key={sector} value={sector}>
      {ts(sector)}
    </option>
  )
  const nis = value.nis ?? NO_NIS

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
        <NumberField
          id="scope-balance"
          label={t('balanceSheet')}
          help={t('balanceSheetHelp')}
          value={value.balanceSheetEur}
          onChange={(n) => set('balanceSheetEur', n)}
          placeholder={t('balanceSheetPlaceholder')}
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

      <CheckGroup
        name="work"
        legend={t('work.legend')}
        intro={t('work.intro')}
        keys={WORK_QUESTIONS}
        selected={value.work ? workToKeys(value.work) : []}
        answered={value.work != null}
        onChange={(keys) => set('work', keys == null ? null : keys.length ? keysToWork(keys) : NO_WORK_AI)}
        text={(key) => t(`work.${key}`)}
      />

      <fieldset className="space-y-3 border-t border-rule pt-5">
        <legend className="text-h4">{t('nis.legend')}</legend>
        <p className="text-small text-ink-2">{t('nis.intro')}</p>
        <Field label={t('nis.sector')} htmlFor="scope-nis-sector" help={t('nis.sectorHelp')}>
          <Select
            id="scope-nis-sector"
            value={value.nis ? value.nis.sector : ''}
            aria-describedby="scope-nis-sector-help"
            onChange={(e) => {
              const sector = e.target.value
              if ((NIS_SECTORS as string[]).includes(sector)) set('nis', { ...nis, sector: sector as NisSector })
              else set('nis', null)
            }}
          >
            <option value="">{t('nis.choose')}</option>
            <optgroup label={t('nis.groupAnnexI')}>{NIS_ANNEX_I.map(sectorOption)}</optgroup>
            <optgroup label={t('nis.groupAnnexII')}>{NIS_ANNEX_II.map(sectorOption)}</optgroup>
            <optgroup label={t('nis.groupOther')}>{NIS_OTHER.map(sectorOption)}</optgroup>
          </Select>
        </Field>
        <Checkbox
          id="scope-nis-anysize"
          label={t('nis.anySize')}
          description={t('nis.anySizeHelp')}
          checked={value.nis?.anySize ?? false}
          onChange={(e) => set('nis', { ...nis, anySize: e.target.checked })}
        />
        <Checkbox
          id="scope-nis-linked"
          label={t('nis.linked')}
          description={t('nis.linkedHelp')}
          checked={value.nis?.linked ?? false}
          onChange={(e) => set('nis', { ...nis, linked: e.target.checked })}
        />
      </fieldset>

      <CheckGroup
        name="machinery"
        legend={t('machinery.legend')}
        intro={t('machinery.intro')}
        keys={MACHINERY_QUESTIONS}
        selected={value.machinery ? machineryToKeys(value.machinery) : []}
        answered={value.machinery != null}
        onChange={(keys) => set('machinery', keys == null ? null : keys.length ? keysToMachinery(keys) : NO_MACHINERY)}
        text={(key) => t(`machinery.${key}`)}
      />

      <CheckGroup
        name="ai"
        legend={t('ai.legend')}
        intro={t('ai.intro')}
        keys={AI_QUESTIONS}
        selected={value.ai ? aiToKeys(value.ai) : []}
        answered={value.ai != null}
        onChange={(keys) => set('ai', keys == null ? null : keys.length ? keysToAi(keys) : NO_AI)}
        text={(key) => t(`ai.${key}`)}
      />

      <fieldset className="space-y-3 border-t border-rule pt-5">
        <legend className="text-h4">{t('csrd.legend')}</legend>
        <p className="text-small text-ink-2">{t('csrd.intro')}</p>
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
