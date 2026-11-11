import { afterEach, describe, expect, it, vi } from 'vitest'

// The status line ("accounts are suspended while the server is being moved")
// is shown by the security and method pages while BACKEND_CONFIGURED is false
// and by the sign-in page while API_CONFIGURED is false: the two flags must
// never disagree, or the pages would contradict each other.
async function flags() {
  vi.resetModules()
  const status = await import('../service-status')
  const api = await import('../api')
  return { backend: status.BACKEND_CONFIGURED, api: api.API_CONFIGURED, on: status.SERVICE_STATUS_ON }
}

describe('service status', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('is "no backend" when NEXT_PUBLIC_API_BASE_URL is empty, for both flags', async () => {
    vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', '')
    const { backend, api } = await flags()
    expect(backend).toBe(false)
    expect(api).toBe(false)
  })

  it('is "backend configured" when the variable is set, for both flags', async () => {
    vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', 'https://api.example.test')
    const { backend, api } = await flags()
    expect(backend).toBe(true)
    expect(api).toBe(true)
  })

  it('dates the status line with a real past day, never with a promise', async () => {
    const { on } = await flags()
    expect(on.toISOString()).toBe('2026-11-11T00:00:00.000Z')
  })
})
