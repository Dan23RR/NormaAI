const TOKEN_KEY = 'normaai_access_token'
const REFRESH_KEY = 'normaai_refresh_token'
const DEMO_KEY = 'normaai_demo_mode'

export function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(TOKEN_KEY)
}

export function getRefreshToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(REFRESH_KEY)
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(TOKEN_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
}

export function clearTokens() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(DEMO_KEY)
}

export function isTokenExpired(token: string): boolean {
  if (token === 'demo.jwt.token') return false
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.exp * 1000 < Date.now()
  } catch {
    return true
  }
}

// ─── Demo mode ──────────────────────────────────────────────

export function isDemoMode(): boolean {
  if (typeof window === 'undefined') return false
  return localStorage.getItem(DEMO_KEY) === 'true'
}

export function setDemoMode(enabled: boolean) {
  if (enabled) {
    localStorage.setItem(DEMO_KEY, 'true')
  } else {
    localStorage.removeItem(DEMO_KEY)
  }
}
