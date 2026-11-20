import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithIntl } from '@/test/i18n'
import { AlertsTab, checkHref, normaliseAlerts, type AlertView } from '../AlertsTab'

vi.mock('next/link', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  default: ({ children, href, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), fetch: vi.fn() },
}))

import { api } from '@/lib/api'

const CHECK_ID = '6f1c2a9e-3b4d-4e5f-8a7b-9c0d1e2f3a4b'
const TODAY = new Date(2026, 10, 11)

function alert(partial: Partial<AlertView>): AlertView {
  return {
    id: 'a1',
    client_id: '',
    severity: 'MEDIUM',
    framework: 'GDPR',
    title: 'Documento da rivedere: nota.docx',
    description: 'Dopo il controllo è cambiata una disposizione citata nel documento: GDPR, Art. 33.',
    actions_required: [],
    is_read: false,
    is_dismissed: false,
    created_at: '2026-11-09T06:00:00Z',
    ...partial,
  }
}

function answer(alerts: AlertView[]) {
  ;(api.get as Mock).mockImplementation((path: string) =>
    Promise.resolve(
      path.startsWith('/api/v1/alerts/summary')
        ? { total: alerts.length, total_unread: alerts.filter((a) => !a.is_read).length, by_severity: [], by_framework: [] }
        : { alerts, total: alerts.length, limit: 50, offset: 0 },
    ),
  )
}

describe('checkHref', () => {
  it('links an alert to the check of its document, and nothing else', () => {
    expect(checkHref(alert({ document_check_id: CHECK_ID }))).toBe(`/app/controlla/${CHECK_ID}`)
    expect(checkHref(alert({ document_check_id: null }))).toBeUndefined()
    expect(checkHref(alert({}))).toBeUndefined()
    expect(checkHref(alert({ document_check_id: '../admin' }))).toBeUndefined()
  })
  it('keeps the check id the API sends', () => {
    const [a] = normaliseAlerts({ alerts: [alert({ document_check_id: CHECK_ID })] })
    expect(a.document_check_id).toBe(CHECK_ID)
  })
})

describe('AlertsTab', () => {
  beforeEach(() => vi.clearAllMocks())

  it('says who creates the alerts and opens the check of the document', async () => {
    answer([alert({ document_check_id: CHECK_ID })])
    renderWithIntl(<AlertsTab today={TODAY} />)
    expect(await screen.findByText('Documento da rivedere: nota.docx')).toBeInTheDocument()
    expect(screen.getByText(/ricontrollo settimanale dei documenti che tieni sotto controllo/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Apri il controllo del documento' })).toHaveAttribute(
      'href',
      `/app/controlla/${CHECK_ID}`,
    )
    // An alert from the re-check is not written by a language model: no AI notice.
    expect(screen.queryByText(/sistema di IA/)).not.toBeInTheDocument()
  })

  it('shows no link and keeps the AI notice for an alert that is not about a document', async () => {
    answer([alert({ id: 'a2', title: 'Novità normativa', document_check_id: null })])
    renderWithIntl(<AlertsTab today={TODAY} />)
    expect(await screen.findByText('Novità normativa')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Apri il controllo del documento' })).not.toBeInTheDocument()
    expect(screen.getByText(/senza un documento collegato possono essere generati da un sistema di IA/)).toBeInTheDocument()
  })

  it('explains, when there is none, what makes an alert appear, in both languages', async () => {
    answer([])
    renderWithIntl(<AlertsTab today={TODAY} />)
    expect(await screen.findByText('Nessun avviso per la tua organizzazione')).toBeInTheDocument()
    expect(screen.getByText(/il ricontrollo settimanale trova cambiata o soppressa una disposizione/)).toBeInTheDocument()
  })

  it('speaks English', async () => {
    answer([alert({ document_check_id: CHECK_ID })])
    renderWithIntl(<AlertsTab today={TODAY} />, { language: 'en' })
    expect(await screen.findByRole('link', { name: 'Open the check of the document' })).toBeInTheDocument()
    expect(screen.getByText(/the weekly re-check of the documents you keep under watch/)).toBeInTheDocument()
  })
})
