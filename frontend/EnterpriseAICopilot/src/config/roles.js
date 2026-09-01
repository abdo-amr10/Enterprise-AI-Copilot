export const ROLES = Object.freeze({ ADMIN: 'admin', NORMAL: 'normal' })
export const isRole = (role) => Object.values(ROLES).includes(role)

const API_ROLE_BY_ROLE = Object.freeze({ [ROLES.ADMIN]: 'admin', [ROLES.NORMAL]: 'user' })
const ROLE_BY_API_ROLE = Object.freeze({ admin: ROLES.ADMIN, user: ROLES.NORMAL, normal: ROLES.NORMAL })

export const toApiRole = (role) => API_ROLE_BY_ROLE[role] ?? null
export const normalizeRole = (role) => ROLE_BY_API_ROLE[String(role || '').toLowerCase()] ?? null
