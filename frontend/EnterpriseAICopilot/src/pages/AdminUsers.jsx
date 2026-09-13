import { useEffect, useRef, useState } from 'react'
import AdminSidebar from '../components/AdminSidebar'
import AdminTopBar from '../components/AdminTopBar'
import ConfirmDialog from '../components/ConfirmDialog'
import PasswordInput from '../components/PasswordInput'
import { changeUserPassword, deleteUser, fetchBranches, fetchUsers, registerUser, updateUserRole } from '../services/adminUsersService'
import '../styles/admin.css'
import '../styles/admin-pages.css'
import '../styles/admin-overrides.css'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const ROLE_OPTIONS = [{ value: 'normal', label: 'Normal User' }, { value: 'admin', label: 'Administrator' }]

function StatusMessage({ status, message }) { return message ? <p className={status === 'success' ? 'admin-success' : 'admin-error'} role="status">{message}</p> : null }
function SubmitButton({ status, children }) { return <div className="admin-actions"><button type="submit" className="primary" disabled={status === 'loading'}>{status === 'loading' ? 'Saving…' : children}</button></div> }

function userListFromResponse(response) {
  if (Array.isArray(response)) return response
  const data = response?.items || response?.users || response?.data || response
  if (Array.isArray(data)) return data
  return data?.items || data?.users || []
}

function branchListFromResponse(response) {
  const data = Array.isArray(response) ? response : response?.items || response?.branches || response?.data || response
  const items = Array.isArray(data) ? data : data?.items || data?.branches || []
  return items.map((branch) => {
    const id = branch?.branchId ?? branch?.id ?? branch?.value ?? branch?.code ?? branch?.branchName ?? branch?.name
    const name = branch?.branchName ?? branch?.name ?? branch?.label ?? branch?.title ?? branch?.branchId ?? branch?.id
    return { id: id === undefined || id === null ? '' : String(id), name: name === undefined || name === null ? '' : String(name) }
  }).filter((branch) => branch.id && branch.name.trim())
}

function formatUserDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('en-US', { dateStyle: 'medium' }).format(date)
}

function UserDirectory() {
  const [status, setStatus] = useState('loading')
  const [users, setUsers] = useState([])

  async function loadUsers() {
    setStatus('loading')
    try {
      const response = await fetchUsers()
      const nextUsers = userListFromResponse(response)
      setUsers(nextUsers)
      setStatus(nextUsers.length ? 'ready' : 'empty')
    } catch {
      setStatus('error')
    }
  }

  useEffect(() => { Promise.resolve().then(loadUsers) }, [])

  if (status === 'loading') return <section className="admin-users-panel admin-card"><div className="admin-users-state"><span className="admin-users-spinner" aria-hidden="true" /><h3>Loading users</h3><p>Retrieving the user directory.</p></div></section>
  if (status === 'error') return <section className="admin-users-panel admin-card"><div className="admin-users-state"><h3>We couldn’t load users</h3><p>Please try again in a moment.</p><button type="button" className="primary" onClick={loadUsers}>Try again</button></div></section>
  if (status === 'empty') return <section className="admin-users-panel admin-card"><div className="admin-users-state"><h3>No users found</h3><p>There are no user accounts to display yet.</p></div></section>

  return <section className="admin-users-panel admin-card"><div className="admin-users-table-wrap"><table className="admin-users-table"><caption className="sr-only">All users</caption><thead><tr><th scope="col">User</th><th scope="col">Role</th><th scope="col">Branch</th><th scope="col">Activity</th><th scope="col">Created</th></tr></thead><tbody>{users.map((user) => { const name = [user.firstName, user.lastName].filter(Boolean).join(' ') || 'Unnamed user'; const role = String(user.role || '—'); return <tr key={user.userId || user.email}><td><strong>{name}</strong><span>{user.email || '—'}</span></td><td><span className={`admin-user-role ${role.toLowerCase() === 'admin' ? 'is-admin' : ''}`}>{role}</span></td><td><strong>{user.branchName || user.branchId || '—'}</strong>{user.branchName && user.branchId ? <span>{user.branchId}</span> : null}</td><td><strong>{user.conversationCount ?? 0}</strong><span>{user.queryCount ?? 0} queries</span></td><td>{formatUserDate(user.createdAt)}</td></tr> })}</tbody></table></div></section>
}

function AddUserForm() {
  const [form, setForm] = useState({ firstName: '', lastName: '', email: '', password: '', confirmPassword: '', role: 'normal', branchId: '' })
  const [branchInput, setBranchInput] = useState('')
  const [branches, setBranches] = useState([])
  const [branchesStatus, setBranchesStatus] = useState('loading')
  const [branchOpen, setBranchOpen] = useState(false)
  const branchFieldRef = useRef(null)
  const [message, setMessage] = useState('')
  const [status, setStatus] = useState('idle')
  const update = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }))

  useEffect(() => {
    let active = true
    fetchBranches()
      .then((response) => {
        if (!active) return
        setBranches(branchListFromResponse(response))
        setBranchesStatus('ready')
      })
      .catch(() => {
        if (active) setBranchesStatus('error')
      })
    return () => { active = false }
  }, [])

  useEffect(() => {
    const closeOnOutsideClick = (event) => {
      if (branchFieldRef.current && !branchFieldRef.current.contains(event.target)) setBranchOpen(false)
    }
    document.addEventListener('mousedown', closeOnOutsideClick)
    return () => document.removeEventListener('mousedown', closeOnOutsideClick)
  }, [])

  const matchingBranches = branches.filter((branch) => branch.name.toLowerCase().includes(branchInput.trim().toLowerCase()))

  function updateBranch(event) {
    const value = event.target.value
    setBranchInput(value)
    setForm((current) => ({ ...current, branchId: value }))
    setBranchOpen(true)
  }

  function selectBranch(branch) {
    setBranchInput(branch.name)
    setForm((current) => ({ ...current, branchId: String(branch.id) }))
    setBranchOpen(false)
  }

  async function submit(event) {
    event.preventDefault()
    if (!form.firstName.trim() || !form.lastName.trim() || !EMAIL_RE.test(form.email) || !form.password || form.password !== form.confirmPassword || !form.branchId.trim()) {
      setStatus('error'); setMessage('Please complete all fields and make sure the passwords match.'); return
    }
    setStatus('loading'); setMessage('')
    try {
      await registerUser(form)
      setStatus('success'); setMessage(`${form.firstName} ${form.lastName} was added successfully.`)
      setForm({ firstName: '', lastName: '', email: '', password: '', confirmPassword: '', role: 'normal', branchId: '' })
      setBranchInput('')
    } catch (error) { setStatus('error'); setMessage(error.message) }
  }

  return <form className="admin-card admin-form" onSubmit={submit} noValidate>
    <small>NEW ACCOUNT</small><h3>Add a user</h3><p>Create a secure account and choose the access level for this person.</p>
    <div className="admin-fields">
      <input aria-label="First name" placeholder="First name" value={form.firstName} onChange={update('firstName')} />
      <input aria-label="Last name" placeholder="Last name" value={form.lastName} onChange={update('lastName')} />
      <input aria-label="Work email" type="email" placeholder="Work email" value={form.email} onChange={update('email')} />
      <select aria-label="Access level" value={form.role} onChange={update('role')}>{ROLE_OPTIONS.map((role) => <option key={role.value} value={role.value}>{role.label}</option>)}</select>
      <PasswordInput aria-label="Password" placeholder="Password" value={form.password} onChange={update('password')} />
      <PasswordInput aria-label="Confirm password" placeholder="Confirm password" value={form.confirmPassword} onChange={update('confirmPassword')} />
      <div className="admin-branch-field" ref={branchFieldRef}>
        <input aria-label="Branch" placeholder="Branch" value={branchInput} onFocus={() => setBranchOpen(true)} onChange={updateBranch} autoComplete="off" />
        {branchOpen ? <div className="admin-branch-dropdown" role="listbox" aria-label="Available branches">
          {branchesStatus === 'loading' ? <div className="admin-branch-state"><span className="admin-users-spinner" aria-hidden="true" />Loading branches…</div> : null}
          {branchesStatus === 'error' ? <div className="admin-branch-state">Branches are unavailable. You can enter a value manually.</div> : null}
          {branchesStatus === 'ready' && matchingBranches.length ? matchingBranches.map((branch) => <button type="button" role="option" className="admin-branch-option" key={`${branch.id}-${branch.name}`} onMouseDown={(event) => event.preventDefault()} onClick={() => selectBranch(branch)}><strong>{branch.name}</strong>{String(branch.id) !== branch.name ? <small>{branch.id}</small> : null}</button>) : null}
          {branchesStatus === 'ready' && !branches.length ? <div className="admin-branch-state">No branches available. You can enter a value manually.</div> : null}
          {branchesStatus === 'ready' && branches.length && !matchingBranches.length ? <div className="admin-branch-state">No matching branches. You can enter a value manually.</div> : null}
        </div> : null}
      </div>
    </div>
    <SubmitButton status={status}>Add user</SubmitButton><StatusMessage status={status} message={message} />
  </form>
}

function ManagedForm({ kind }) {
  const isDelete = kind === 'delete'
  const isPassword = kind === 'password'
  const [email, setEmail] = useState('')
  const [newRole, setNewRole] = useState('normal')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [confirmationOpen, setConfirmationOpen] = useState(false)
  const [status, setStatus] = useState('idle')
  const [message, setMessage] = useState('')
  const copy = isDelete ? ['REMOVE ACCOUNT', 'Remove a user', 'Remove a user account when it is no longer needed.', 'Remove user'] : isPassword ? ['CREDENTIALS', 'Reset a password', 'Set a new password for an existing user.', 'Update password'] : ['ACCESS LEVEL', 'Change access level', 'Update the access level assigned to an existing user.', 'Update access']

  function requestConfirmation(event) {
    event.preventDefault()
    if (!EMAIL_RE.test(email)) { setStatus('error'); setMessage('Enter a valid email address.'); return }
    if (isPassword && (!newPassword || newPassword !== confirmPassword)) { setStatus('error'); setMessage('Enter matching passwords.'); return }
    setStatus('idle'); setMessage(''); setConfirmationOpen(true)
  }

  async function confirm() {
    setConfirmationOpen(false); setStatus('loading')
    try {
      if (isDelete) await deleteUser({ email })
      else if (isPassword) await changeUserPassword({ email, newPassword, confirmPassword })
      else await updateUserRole({ email, newRole })
      setStatus('success'); setMessage(isDelete ? 'The user was removed successfully.' : isPassword ? 'The password was updated successfully.' : 'The access level was updated successfully.')
      setEmail(''); setNewPassword(''); setConfirmPassword(''); setNewRole('normal')
    } catch (error) { setStatus('error'); setMessage(error.message) }
  }

  return <>
    <form className="admin-card admin-form" onSubmit={requestConfirmation} noValidate>
      <small>{copy[0]}</small><h3>{copy[1]}</h3><p>{copy[2]}</p>
      <div className="admin-fields">
        <input aria-label="User email" type="email" placeholder="User email" value={email} onChange={(event) => setEmail(event.target.value)} />
        {!isDelete && !isPassword ? <select aria-label="New access level" value={newRole} onChange={(event) => setNewRole(event.target.value)}>{ROLE_OPTIONS.map((role) => <option key={role.value} value={role.value}>{role.label}</option>)}</select> : null}
        {isPassword ? <><PasswordInput aria-label="New password" placeholder="New password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /><PasswordInput aria-label="Confirm new password" placeholder="Confirm new password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} /></> : null}
      </div>
      <SubmitButton status={status}>{copy[3]}</SubmitButton><StatusMessage status={status} message={message} />
    </form>
    <ConfirmDialog open={confirmationOpen} title={`${copy[3]}?`} message={isDelete ? 'This removes the account permanently. You cannot undo this action.' : 'The change will take effect immediately.'} confirmLabel={copy[3]} variant={isDelete ? 'destructive' : 'primary'} onConfirm={confirm} onCancel={() => setConfirmationOpen(false)} />
  </>
}

export default function AdminUsers() {
  const [tab, setTab] = useState('users')
  const panels = { users: <UserDirectory />, add: <AddUserForm />, role: <ManagedForm kind="role" />, password: <ManagedForm kind="password" />, delete: <ManagedForm kind="delete" /> }
  return <main className="admin-shell"><AdminSidebar active="users" /><section className={`admin-main admin-users-main ${tab === 'users' ? 'is-directory' : ''}`}><AdminTopBar title="Users" description="Manage user accounts and access levels." /><div className="admin-tabs">{[['users', 'Users'], ['add', 'Add User'], ['role', 'Access'], ['password', 'Password'], ['delete', 'Remove User']].map(([key, label]) => <button key={key} className={tab === key ? 'active' : ''} type="button" onClick={() => setTab(key)}>{label}</button>)}</div>{tab === 'users' ? <div className="admin-users-directory">{panels[tab]}</div> : panels[tab]}</section></main>
}
