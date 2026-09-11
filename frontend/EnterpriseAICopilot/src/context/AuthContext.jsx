import { useEffect, useMemo, useState } from 'react'
import { authService } from '../services/authService'
import { isRole } from '../config/roles'
import { AuthContext, SESSION_KEY } from './authStore'

const readSession = () => {
  try {
    const saved = JSON.parse(sessionStorage.getItem(SESSION_KEY))
    const stillValid =
      saved?.expiresAt &&
      new Date(saved.expiresAt) > new Date() &&
      isRole(saved.user?.role)

    return stillValid ? saved : null
  } catch {
    return null
  }
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(readSession)

  useEffect(() => {
    if (!session) return undefined

    const delay = Math.max(0, new Date(session.expiresAt) - Date.now())
    const timer = window.setTimeout(() => {
      sessionStorage.removeItem(SESSION_KEY)
      setSession(null)
    }, delay)

    return () => window.clearTimeout(timer)
  }, [session])

  const value = useMemo(
    () => ({
      user: session?.user ?? null,
      token: session?.token ?? null,
      expiresAt: session?.expiresAt ?? null,
      isAuthenticated: Boolean(session),
      isRestoring: false,
      async login(credentials) {
        const next = await authService.login(credentials)
        if (!isRole(next.user?.role)) {
          throw new Error('Account role is unavailable.')
        }
        sessionStorage.setItem(SESSION_KEY, JSON.stringify(next))
        setSession(next)
        return next.user
      },
      async logout() {
        try {
          await authService.logout()
        } catch {
          // A local sign-out must still succeed if the server session has already expired.
        }
        sessionStorage.removeItem(SESSION_KEY)
        setSession(null)
      },
    }),
    [session],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
