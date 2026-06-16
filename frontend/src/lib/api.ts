import { getAccessToken, getRefreshToken, setTokens, clearTokens, isTokenExpired, isDemoMode } from './auth'
import type { TokenPair, ApiError, ApiResponse, QAResponse, GapAnalysisResponse, MonitorResponse, SystemStats } from './types'
import {
  DEMO_TOKENS, DEMO_USER, DEMO_STATS, DEMO_PROCESSORS,
  DEMO_ALERTS, DEMO_ALERT_SUMMARY, DEMO_CLIENTS,
  getMockQAResponse, getMockGapAnalysis, getMockMonitorResponse, mockDelay,
} from './mock-data'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Validate API URL format at build time
if (API_URL && !API_URL.startsWith('http://') && !API_URL.startsWith('https://')) {
  console.error('NEXT_PUBLIC_API_URL must start with http:// or https://')
}

class ApiClient {
  private baseUrl: string

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl
  }

  // ─── Demo mode interceptors ─────────────────────────────

  private async handleDemoGet<T>(path: string): Promise<T> {
    await mockDelay(300)

    if (path === '/api/v1/auth/me') return DEMO_USER as T
    if (path === '/api/v1/stats') return DEMO_STATS as T
    if (path === '/api/v1/processors') return DEMO_PROCESSORS as T
    if (path === '/api/v1/metrics') return DEMO_STATS.metrics as T
    if (path === '/api/v1/alerts/summary') return DEMO_ALERT_SUMMARY as T
    if (path.startsWith('/api/v1/alerts')) return { alerts: DEMO_ALERTS, total: DEMO_ALERTS.length, limit: 50, offset: 0 } as T
    if (path.startsWith('/api/v1/reports/history')) {
      try {
        const stored = sessionStorage.getItem('normaai_demo_reports')
        if (stored) return { data: JSON.parse(stored) } as T
      } catch { /* ignore */ }
      return { data: [] } as T
    }
    if (path.startsWith('/api/v1/clients')) {
      const extra: Record<string, unknown>[] = (() => { try { const s = sessionStorage.getItem('normaai_demo_clients'); return s ? JSON.parse(s) : [] } catch { return [] } })()
      const deletedIds: string[] = (() => { try { const s = sessionStorage.getItem('normaai_demo_clients_deleted'); return s ? JSON.parse(s) : [] } catch { return [] } })()
      const extraIds = new Set(extra.map(c => c.id))
      const deletedSet = new Set(deletedIds)
      // Merge: session edits override DEMO_CLIENTS with same id, filter deleted, plus any new ones
      const base = DEMO_CLIENTS.filter(c => !extraIds.has(c.id) && !deletedSet.has(c.id))
      const all = [...base, ...extra]
      return { data: all, clients: all, total: all.length } as T
    }

    return {} as T
  }

  private async handleDemoPost<T>(path: string, body: unknown, method?: string): Promise<T> {
    const data = body as Record<string, unknown>

    if (path === '/api/v1/qa') {
      await mockDelay(2000)
      const question = (data?.question as string) || ''
      const language = (data?.language as string) || 'it'
      return {
        status: 'success',
        data: getMockQAResponse(question, language),
        metadata: { timestamp: new Date().toISOString(), model: 'demo-mode' },
      } as T
    }

    if (path === '/api/v1/gap-analysis') {
      await mockDelay(3000)
      const framework = (data?.framework as string) || 'CSRD'
      return {
        status: 'success',
        data: getMockGapAnalysis(framework),
        metadata: { timestamp: new Date().toISOString(), framework },
      } as T
    }

    if (path === '/api/v1/monitor') {
      await mockDelay(2500)
      const changeText = (data?.regulation_change as string) || ''
      return {
        status: 'success',
        data: getMockMonitorResponse(changeText),
        metadata: { timestamp: new Date().toISOString() },
      } as T
    }

    // Demo client CRUD
    if (path.startsWith('/api/v1/clients')) {
      await mockDelay(500)
      const clientIdMatch = path.match(/\/api\/v1\/clients\/(.+?)(?:\/|$)/)
      const clientId = clientIdMatch?.[1]

      if (method === 'DELETE' && clientId) {
        try {
          const stored = sessionStorage.getItem('normaai_demo_clients')
          const list = stored ? JSON.parse(stored) : []
          sessionStorage.setItem('normaai_demo_clients', JSON.stringify(list.filter((c: Record<string, unknown>) => c.id !== clientId)))
          // Also track deleted base DEMO_CLIENTS so they don't reappear on re-fetch
          const deletedRaw = sessionStorage.getItem('normaai_demo_clients_deleted')
          const deleted: string[] = deletedRaw ? JSON.parse(deletedRaw) : []
          if (!deleted.includes(clientId)) deleted.push(clientId)
          sessionStorage.setItem('normaai_demo_clients_deleted', JSON.stringify(deleted))
        } catch { /* ignore */ }
        return {} as T
      }

      if (method === 'PUT' && clientId) {
        try {
          const stored = sessionStorage.getItem('normaai_demo_clients')
          const list = stored ? JSON.parse(stored) : []
          const idx = list.findIndex((c: Record<string, unknown>) => c.id === clientId)
          if (idx >= 0) {
            list[idx] = { ...list[idx], ...data }
          } else {
            // Editing a pre-loaded DEMO_CLIENT — save the edited copy to session
            list.push({ id: clientId, ...data })
          }
          sessionStorage.setItem('normaai_demo_clients', JSON.stringify(list))
        } catch { /* ignore */ }
        return { id: clientId, ...data } as T
      }

      // POST — create new client
      const newClient = { id: `demo-${Date.now()}`, ...data }
      try {
        const stored = sessionStorage.getItem('normaai_demo_clients')
        const list = stored ? JSON.parse(stored) : []
        list.push(newClient)
        sessionStorage.setItem('normaai_demo_clients', JSON.stringify(list))
      } catch { /* ignore */ }
      return newClient as T
    }

    return {} as T
  }

  // ─── Token refresh ──────────────────────────────────────

  private async refreshAccessToken(): Promise<boolean> {
    const refreshToken = getRefreshToken()
    if (!refreshToken) return false

    try {
      const res = await fetch(`${this.baseUrl}/api/v1/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })

      if (!res.ok) return false

      const data: TokenPair = await res.json()
      setTokens(data.access_token, data.refresh_token)
      return true
    } catch {
      return false
    }
  }

  // ─── Core fetch ─────────────────────────────────────────

  async fetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    // Demo mode: return mock data
    if (isDemoMode()) {
      if (!options.method || options.method === 'GET') {
        return this.handleDemoGet<T>(path)
      }
      const body = options.body ? JSON.parse(options.body as string) : {}
      return this.handleDemoPost<T>(path, body, options.method)
    }

    let token = getAccessToken()

    // Auto-refresh if expired
    if (token && isTokenExpired(token)) {
      const refreshed = await this.refreshAccessToken()
      if (refreshed) {
        token = getAccessToken()
      } else {
        clearTokens()
        window.location.href = '/login'
        throw new Error('Session expired')
      }
    }

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> || {}),
    }

    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }

    const res = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers,
    })

    if (res.status === 401) {
      const refreshed = await this.refreshAccessToken()
      if (refreshed) {
        headers['Authorization'] = `Bearer ${getAccessToken()}`
        const retry = await fetch(`${this.baseUrl}${path}`, { ...options, headers })
        if (retry.ok) return retry.json()
      }
      clearTokens()
      window.location.href = '/login'
      throw new Error('Unauthorized')
    }

    if (!res.ok) {
      const error: ApiError = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
      throw new Error(error.detail || `Request failed: ${res.status}`)
    }

    return res.json()
  }

  // ─── Auth endpoints ─────────────────────────────────────

  async login(email: string, password: string): Promise<TokenPair> {
    if (isDemoMode()) {
      await mockDelay(500)
      setTokens(DEMO_TOKENS.access_token, DEMO_TOKENS.refresh_token)
      return DEMO_TOKENS
    }

    const res = await fetch(`${this.baseUrl}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Login failed' }))
      throw new Error(err.detail)
    }
    const data: TokenPair = await res.json()
    setTokens(data.access_token, data.refresh_token)
    return data
  }

  async register(email: string, password: string, name: string, orgName: string): Promise<TokenPair> {
    if (isDemoMode()) {
      await mockDelay(500)
      setTokens(DEMO_TOKENS.access_token, DEMO_TOKENS.refresh_token)
      return DEMO_TOKENS
    }

    const res = await fetch(`${this.baseUrl}/api/v1/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, name, organization_name: orgName }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Registration failed' }))
      throw new Error(err.detail)
    }
    const data: TokenPair = await res.json()
    setTokens(data.access_token, data.refresh_token)
    return data
  }

  // ─── Typed helpers ──────────────────────────────────────

  get<T>(path: string) {
    return this.fetch<T>(path)
  }

  post<T>(path: string, body: unknown) {
    return this.fetch<T>(path, {
      method: 'POST',
      body: JSON.stringify(body),
    })
  }

  put<T>(path: string, body: unknown) {
    return this.fetch<T>(path, {
      method: 'PUT',
      body: JSON.stringify(body),
    })
  }

  del<T>(path: string) {
    return this.fetch<T>(path, { method: 'DELETE' })
  }

  /**
   * Upload a file via FormData with full auth handling.
   * Does NOT set Content-Type (browser sets it with multipart boundary).
   */
  async upload<T>(path: string, formData: FormData): Promise<T> {
    if (isDemoMode()) {
      throw new Error('File upload is not available in demo mode')
    }

    let token = getAccessToken()

    if (token && isTokenExpired(token)) {
      const refreshed = await this.refreshAccessToken()
      if (refreshed) {
        token = getAccessToken()
      } else {
        clearTokens()
        window.location.href = '/login'
        throw new Error('Session expired')
      }
    }

    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`

    const res = await fetch(`${this.baseUrl}${path}`, {
      method: 'POST',
      headers,
      body: formData,
    })

    if (res.status === 401) {
      const refreshed = await this.refreshAccessToken()
      if (refreshed) {
        headers['Authorization'] = `Bearer ${getAccessToken()}`
        const retry = await fetch(`${this.baseUrl}${path}`, { method: 'POST', headers, body: formData })
        if (retry.ok) return retry.json()
      }
      clearTokens()
      window.location.href = '/login'
      throw new Error('Unauthorized')
    }

    if (!res.ok) {
      const error: ApiError = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
      throw new Error(error.detail || `Request failed: ${res.status}`)
    }

    return res.json()
  }

  /**
   * Fetch a binary response (PDF, etc.) with full auth handling.
   * Unlike fetch<T>, this returns a raw Response instead of parsing JSON.
   */
  async fetchBlob(path: string, options: RequestInit = {}): Promise<Response> {
    if (isDemoMode()) {
      throw new Error('Report generation is not available in demo mode')
    }

    let token = getAccessToken()

    // Auto-refresh if expired
    if (token && isTokenExpired(token)) {
      const refreshed = await this.refreshAccessToken()
      if (refreshed) {
        token = getAccessToken()
      } else {
        clearTokens()
        window.location.href = '/login'
        throw new Error('Session expired')
      }
    }

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> || {}),
    }

    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }

    const res = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers,
    })

    if (res.status === 401) {
      const refreshed = await this.refreshAccessToken()
      if (refreshed) {
        headers['Authorization'] = `Bearer ${getAccessToken()}`
        const retry = await fetch(`${this.baseUrl}${path}`, { ...options, headers })
        if (retry.ok) return retry
      }
      clearTokens()
      window.location.href = '/login'
      throw new Error('Unauthorized')
    }

    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
      throw new Error(error.detail || `Request failed: ${res.status}`)
    }

    return res
  }

  getBaseUrl() {
    return this.baseUrl
  }
}

export const api = new ApiClient(API_URL)
