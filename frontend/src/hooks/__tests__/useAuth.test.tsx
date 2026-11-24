import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ApiError } from '@/lib/api-error'

const mocks = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('@/lib/api', () => ({
  api: { get: (...args: unknown[]) => mocks.get(...args), logout: vi.fn() },
}))

// happy-dom does not expose the storages as globals: the hook and the test
// share these in-memory ones.
function memoryStorage(): Storage {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => (key in store ? store[key] : null),
    setItem: (key: string, value: string) => {
      store[key] = String(value)
    },
    removeItem: (key: string) => {
      delete store[key]
    },
    clear: () => {
      for (const k of Object.keys(store)) delete store[k]
    },
    key: (i: number) => Object.keys(store)[i] ?? null,
    get length() {
      return Object.keys(store).length
    },
  }
}
vi.stubGlobal('localStorage', memoryStorage())
vi.stubGlobal('sessionStorage', memoryStorage())

import { AuthProvider, useAuth } from '../useAuth'
import { getAccessToken, setTokens } from '@/lib/auth'

const ANNA = { id: 'u-anna', email: 'anna@studio.example', name: 'Anna Bianchi', role: 'admin', organization_name: 'Studio Esempio' }

function Probe() {
  const { user, loading, refreshUser } = useAuth()
  if (loading) return <p>loading</p>
  return (
    <div>
      <p>role: {user?.role ?? 'nobody'}</p>
      <button onClick={() => refreshUser()}>refresh</button>
    </div>
  )
}

describe('useAuth().refreshUser', () => {
  beforeEach(() => {
    localStorage.clear()
    mocks.get.mockReset()
    setTokens('access.token.value', 'refresh.token.value')
  })

  it('reads the account again, with its new role', async () => {
    const user = userEvent.setup()
    mocks.get.mockResolvedValueOnce(ANNA).mockResolvedValueOnce({ ...ANNA, role: 'member' })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    expect(await screen.findByText('role: admin')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'refresh' }))
    expect(await screen.findByText('role: member')).toBeInTheDocument()
    expect(mocks.get).toHaveBeenLastCalledWith('/api/v1/auth/me')
  })

  it('keeps the session when the account cannot be read again', async () => {
    const user = userEvent.setup()
    mocks.get.mockResolvedValueOnce(ANNA).mockRejectedValueOnce(new ApiError('network'))
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    expect(await screen.findByText('role: admin')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'refresh' }))
    await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2))
    expect(screen.getByText('role: admin')).toBeInTheDocument()
    expect(getAccessToken()).toBe('access.token.value')
  })
})
