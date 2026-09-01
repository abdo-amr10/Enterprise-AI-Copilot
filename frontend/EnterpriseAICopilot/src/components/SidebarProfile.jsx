import { IconLogOut } from './icons'

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
  const name = [user?.firstName, user?.lastName].filter(Boolean).join(' ').trim()
  const normalizedName = name.includes('@') ? '' : name
  return normalizedName || nameFromEmail(user?.email) || 'Account'
}

function getInitials(name) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase() || 'A'
}

export default function SidebarProfile({ user, subtitle, onSignOut, variant }) {
  const name = getUserDisplayName(user)
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
