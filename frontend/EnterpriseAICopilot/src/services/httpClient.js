import { env } from '../config/env'
import { SESSION_KEY } from '../context/authStore'

function readToken() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(SESSION_KEY))
    return saved?.token || ''
  } catch {
    return ''
  }
}

export async function request(path, options = {}) {
  const token = readToken()
  const isFormData = options.body instanceof FormData
  const response = await fetch(`${env.apiBaseUrl}${path}`, {
    ...options,
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })

  const payload = response.status === 204 ? null : await response.json().catch(() => null)

  if (!response.ok) {
    const error = new Error(payload?.message || 'We could not complete that request. Please try again.')
    error.status = response.status
    error.code = payload?.errorCode
    throw error
  }

  return payload
}



