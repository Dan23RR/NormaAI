import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithIntl } from '@/test/i18n'
import { DEMO_STATS } from '@/lib/mock-data'
import { SystemStatusSection } from '../SystemStatusSection'

const mocks = vi.hoisted(() => ({ demo: false }))

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn() },
}))

vi.mock('@/lib/auth', () => ({
  isDemoMode: () => mocks.demo,
}))

import { api } from '@/lib/api'

const LIVE_STATS = {
  status: 'healthy',
  version: '2.0.0',
  environment: 'production',
  llm_provider: 'gemini',
  llm_model: 'gemini-2.5-flash',
  timestamp: '2026-11-10T09:30:00Z',
  qdrant_available: true,
  llm_available: true,
  qdrant: { status: 'ok', points_count: 14823 },
  metrics: {
    total_requests: 120,
    error_count: 0,
    endpoints: { 'POST /api/v1/qa': { count: 100, avg_latency_ms: 1800, max_latency_ms: 5200 } },
  },
}

describe('SystemStatusSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.demo = false
  })

  it('shows what the server reports when there is a server', async () => {
    ;(api.get as Mock).mockResolvedValue(LIVE_STATS)
    renderWithIntl(<SystemStatusSection />)
    expect(await screen.findByText('Operativo')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/api/v1/stats')
    expect(screen.getByText('2.0.0')).toBeInTheDocument()
    expect(screen.getByText('Disponibile')).toBeInTheDocument()
    expect(screen.getByText('POST /api/v1/qa')).toBeInTheDocument()
  })

  it('claims nothing in the demo: no request, no status, no counters', async () => {
    mocks.demo = true
    // Even if the client answered with the demo stats, nothing of it may be shown.
    ;(api.get as Mock).mockResolvedValue(DEMO_STATS)
    renderWithIntl(<SystemStatusSection />)
    expect(screen.getByRole('heading', { name: 'Demo con dati di esempio' })).toBeInTheDocument()
    expect(screen.getByText(/non esiste un server da interrogare/)).toBeInTheDocument()
    await waitFor(() => expect(api.get).not.toHaveBeenCalled())
    for (const live of ['Operativo', 'Disponibile', 'Configurato', 'Aggiorna lo stato', 'Richieste totali']) {
      expect(screen.queryByText(live)).not.toBeInTheDocument()
    }
    expect(screen.queryByText(/Letto dal server/)).not.toBeInTheDocument()
  })

  it('says the same in English', () => {
    mocks.demo = true
    renderWithIntl(<SystemStatusSection />, { language: 'en' })
    expect(screen.getByRole('heading', { name: 'Demo with sample data' })).toBeInTheDocument()
    expect(screen.getByText(/there is no server to ask/)).toBeInTheDocument()
    expect(screen.queryByText('Operational')).not.toBeInTheDocument()
  })
})
