import { normalizeRole } from '../config/roles.js'

const ROLE_CLAIMS = [
  'role',
  'roles',
  'Role',
  'http://schemas.microsoft.com/ws/2008/06/identity/claims/role',
]

const CLAIMS = {
  userId: ['sub', 'userId', 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier'],
  email: ['email', 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress'],
  name: ['name', 'unique_name', 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name'],
  branchId: ['branchId'],
}

function decodeSegment(segment) {
  const normalized = segment.replace(/-/g, '+').replace(/_/g, '/')
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')
  const value = atob(padded)
  const bytes = Uint8Array.from(value, (character) => character.charCodeAt(0))
  return JSON.parse(new TextDecoder().decode(bytes))
}

export function decodeJwt(token) {
  if (!token || typeof token !== 'string') return null

  try {
    const [, payload] = token.split('.')
    return payload ? decodeSegment(payload) : null
  } catch {
    return null
  }
}

function firstClaim(payload, claimNames) {
  return claimNames.map((name) => payload?.[name]).find(Boolean) ?? null
}

export function readRoleFromJwt(token) {
  const payload = decodeJwt(token)
  const roles = ROLE_CLAIMS.flatMap((claim) => {
    const value = payload?.[claim]
    return Array.isArray(value) ? value : [value]
  })

  return roles.map(normalizeRole).find(Boolean) ?? null
}

export function readUserFromJwt(token, fallbackEmail = '') {
  const payload = decodeJwt(token)
  const email = firstClaim(payload, CLAIMS.email) || fallbackEmail
  const claimedName = firstClaim(payload, CLAIMS.name)?.trim()
  const fullName = claimedName && !claimedName.includes('@')
    ? claimedName
    : String(email || '').split('@')[0]?.split(/[._-]+/).filter(Boolean).map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`).join(' ')
  const [firstName = '', ...lastName] = fullName?.trim().split(/\s+/) || []

  return {
    userId: firstClaim(payload, CLAIMS.userId),
    firstName,
    lastName: lastName.join(' '),
    email,
    branchId: firstClaim(payload, CLAIMS.branchId),
    role: readRoleFromJwt(token),
  }
}
