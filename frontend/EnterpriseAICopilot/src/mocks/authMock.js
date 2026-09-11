import { ROLES } from '../config/roles'
const users = [
  { email: 'normal@enterprise.com', password: 'securepassword123', user: { userId: 'USR-001', firstName: 'Normal', lastName: 'User', email: 'normal@enterprise.com', role: ROLES.NORMAL, branchId: 1 } },
  { email: 'admin@enterprise.com', password: 'securepassword123', user: { userId: 'USR-002', firstName: 'Admin', lastName: 'User', email: 'admin@enterprise.com', role: ROLES.ADMIN, branchId: 1 } },
]
const pause = () => new Promise((resolve) => window.setTimeout(resolve, 450))
export async function loginMock({ email, password }) { await pause(); const match = users.find((item) => item.email === email && item.password === password); if (!match) { const error = new Error('Invalid email or password.'); error.code = 'UNAUTHORIZED'; throw error }; const expiresAt = new Date(Date.now() + 60 * 60 * 1000).toISOString(); return { status: 'Success', token: `mock-${match.user.userId}-${Date.now()}`, expiresAt, user: match.user } }
