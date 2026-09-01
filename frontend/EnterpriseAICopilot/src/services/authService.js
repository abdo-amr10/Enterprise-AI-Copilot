import { env } from '../config/env'
import { request } from './httpClient'
import { loginMock } from '../mocks/authMock'
import { readUserFromJwt } from './jwt'

async function login(credentials) {
  if (env.useMockApi) return loginMock(credentials)

  const response = await request('/api/v1/Auth/login', {
    method: 'POST',
    body: JSON.stringify(credentials),
  })

  const token = response?.token
  const user = readUserFromJwt(token, credentials.email)

  return {
    status: response?.status,
    token,
    expiresAt: response?.expiresAt,
    user,
  }
}

async function logout() {
  if (env.useMockApi) return
  await request('/api/v1/Auth/logout', { method: 'POST' })
}

export const authService = { login, logout }
