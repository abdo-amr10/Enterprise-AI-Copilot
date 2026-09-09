import { useEffect, useState } from 'react'
import { IconLogOut } from './icons'
import { fetchCurrentUser } from '../services/adminUsersService'

function nameFromEmail(email = '') {
  const localPart = email.split('@')[0]?.trim()
  if (!localPart) return ''

  return localPart
    .split(/[._-]+/)
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(' ')
}

function getUserDisplayName(user) {
  const name = [user?.firstName || user?.FirstName || user?.first_name, user?.lastName || user?.LastName || user?.last_name].filter(Boolean).join(' ').trim()
  const normalizedName = name.includes('@') ? '' : name
  return normalizedName || user?.name || user?.fullName || user?.displayName || user?.userName || nameFromEmail(user?.email || user?.Email) || 'Account'
}

function getInitials(name) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase() || 'A'
}

function usersFromResponse(response) {
  if (Array.isArray(response)) return response
  const data = response?.items || response?.users || response?.data || response?.user || response
  if (Array.isArray(data)) return data
  if (data?.userId || data?.UserId || data?.email || data?.Email || data?.firstName || data?.FirstName || data?.fullName) return [data]
  return data?.items || data?.users || data?.user ? [data.user] : []
}

export default function SidebarProfile({ user, subtitle, onSignOut, variant }) {
  const [profileUser, setProfileUser] = useState(user)

  useEffect(() => {
    let active = true
    fetchCurrentUser()
      .then((response) => {
        if (active) setProfileUser(usersFromResponse(response)[0] || user)
      })
      .catch(() => {
        // Keep the authenticated JWT profile visible if the directory is unavailable.
      })
    return () => { active = false }
  }, [user])

  const name = getUserDisplayName(profileUser)
  const isAdmin = variant === 'admin'
  const rootClass = isAdmin ? 'admin-user' : 'copilot-sidebar-footer'
  const avatarClass = isAdmin ? 'admin-user-avatar' : 'copilot-avatar'

  return (
    <div className={rootClass}>
      <div className={avatarClass} aria-hidden="true">{getInitials(name)}</div>
      <div className="sidebar-profile-details">
        <strong title={name}>{name}</strong>
        <small>{subtitle}</small>
        <button type="button" onClick={onSignOut}>
          <IconLogOut aria-hidden="true" />
          Sign out
        </button>
      </div>
    </div>
  )
}
