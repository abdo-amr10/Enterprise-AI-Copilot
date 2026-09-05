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
  let response
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, {
      ...options,
      headers: {
        ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    })
  } catch {
    const error = new Error('We could not reach the server. Check your connection and try again.')
    error.code = 'NETWORK_ERROR'
    throw error
  }

  const payload = response.status === 204 ? null : await response.json().catch(() => null)

  if (!response.ok) {
    const validationMessage = payload?.errors && typeof payload.errors === 'object'
      ? Object.values(payload.errors).flat().filter(Boolean).join(' ')
      : ''
    const error = new Error(
      payload?.message || payload?.detail || validationMessage || payload?.title ||
      `Request failed (${response.status}). Please try again.`,
    )
    error.status = response.status
    error.code = payload?.errorCode
    throw error
  }

  return payload
}

export async function requestFile(path, options = {}) {
  const token = readToken()
  const response = await fetch(`${env.apiBaseUrl}${path}`, {
    ...options,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    const error = new Error(payload?.message || 'We could not prepare this file. Please try again.')
    error.status = response.status
    error.code = payload?.errorCode
    throw error
  }

  const disposition = response.headers.get('content-disposition') || ''
  const filenameMatch = disposition.match(/filename\*?=(?:UTF-8''|")?([^;"]+)/i)
  return {
    blob: await response.blob(),
    fileName: filenameMatch ? decodeURIComponent(filenameMatch[1].trim()) : '',
  }
}
