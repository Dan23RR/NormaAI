'use client'

import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from 'react'
import { api } from '@/lib/api'
import { getAccessToken, clearTokens, setTokens, setDemoMode, isDemoMode } from '@/lib/auth'
import { DEMO_USER, DEMO_TOKENS } from '@/lib/mock-data'
import type { User } from '@/lib/types'

interface AuthContextType {
  user: User | null
  loading: boolean
  demoMode: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, name: string, orgName: string) => Promise<void>
  loginDemo: () => void
  logout: () => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [demoMode, setDemo] = useState(false)

  const fetchUser = useCallback(async () => {
    const token = getAccessToken()
    if (!token) {
      setLoading(false)
      return
    }

    // Demo mode: return demo user directly
    if (isDemoMode()) {
      setUser(DEMO_USER)
      setDemo(true)
      setLoading(false)
      return
    }

    try {
      const u = await api.get<User>('/api/v1/auth/me')
      setUser(u)
    } catch {
      clearTokens()
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchUser()
  }, [fetchUser])

  const login = async (email: string, password: string) => {
    await api.login(email, password)
    await fetchUser()
  }

  const register = async (email: string, password: string, name: string, orgName: string) => {
    await api.register(email, password, name, orgName)
    await fetchUser()
  }

  const loginDemo = () => {
    setDemoMode(true)
    setTokens(DEMO_TOKENS.access_token, DEMO_TOKENS.refresh_token)
    setUser(DEMO_USER)
    setDemo(true)
  }

  const logout = () => {
    clearTokens()
    setDemoMode(false)
    setUser(null)
    setDemo(false)
  }

  return (
    <AuthContext.Provider value={{ user, loading, demoMode, login, register, loginDemo, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
