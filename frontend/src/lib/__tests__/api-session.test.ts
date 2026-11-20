import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * The API client's side of the session: signing out revokes the session on
 * the server, and the password-reset calls reach the backend even with a
 * leftover demo flag.
 */
const tokens = vi.hoisted(() => ({
  access: 'access.jwt.token' as string | null,
  refresh: 'refresh.jwt.token' as string | null,
  demo: false,
}))

vi.mock('../auth', () => ({
  isDemoMode: () => tokens.demo,
  getAccessToken: () => tokens.access,
  getRefreshToken: () => tokens.refresh,
  setTokens: vi.fn(),
  clearTokens: vi.fn(),
  isTokenExpired: () => false,
}))

const fetchMock = vi.fn()

async function client(apiBase = 'https://api.example.test') {
  vi.resetModules()
  vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', apiBase)
  return (await import('../api')).api
}

describe('API client session calls', () => {
  beforeEach(() => {
    tokens.access = 'access.jwt.token'
    tokens.refresh = 'refresh.jwt.token'
    tokens.demo = false
    fetchMock.mockReset()
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('logout sends the access token and the refresh token to the server', async () => {
    const api = await client()
    await api.logout()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('https://api.example.test/api/v1/auth/logout')
    expect(init.method).toBe('POST')
    expect(init.headers.Authorization).toBe('Bearer access.jwt.token')
    expect(JSON.parse(init.body)).toEqual({ refresh_token: 'refresh.jwt.token' })
  })

  it('logout reads the tokens before the caller clears them', async () => {
    const api = await client()
    const pending = api.logout()
    tokens.access = null
    tokens.refresh = null
    await pending
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ refresh_token: 'refresh.jwt.token' })
  })

  it('logout never fails, and calls nothing without a backend, in the demo or without tokens', async () => {
    fetchMock.mockRejectedValue(new TypeError('offline'))
    await expect((await client()).logout()).resolves.toBeUndefined()

    fetchMock.mockClear()
    await (await client('')).logout()
    tokens.demo = true
    await (await client()).logout()
    tokens.demo = false
    tokens.access = null
    tokens.refresh = null
    await (await client()).logout()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('the password-reset calls reach the backend even in demo mode', async () => {
    tokens.demo = true
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ status: 'accepted' }), { status: 202 }))
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ status: 'password_changed', email: 'anna@studio.it' }), { status: 200 }),
    )
    const api = await client()
    await api.requestPasswordReset('anna@studio.it')
    const done = await api.resetPassword('user.secret', 'lunga-abbastanza')
    expect(done.email).toBe('anna@studio.it')
    expect(fetchMock.mock.calls[0][0]).toBe('https://api.example.test/api/v1/auth/password-reset')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ email: 'anna@studio.it' })
    expect(fetchMock.mock.calls[1][0]).toBe('https://api.example.test/api/v1/auth/password-reset/confirm')
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ token: 'user.secret', password: 'lunga-abbastanza' })
  })

  it('a refused reset carries the server detail', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Il link non è valido o è scaduto.' }), { status: 400 }),
    )
    const api = await client()
    await expect(api.resetPassword('user.old', 'lunga-abbastanza')).rejects.toMatchObject({
      detail: 'Il link non è valido o è scaduto.',
    })
  })
})
