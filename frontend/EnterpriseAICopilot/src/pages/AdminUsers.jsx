import { useState } from 'react'
import AdminSidebar from '../components/AdminSidebar'
import AdminTopBar from '../components/AdminTopBar'
import ConfirmDialog from '../components/ConfirmDialog'
import PasswordInput from '../components/PasswordInput'
import { changeUserPassword, deleteUser, registerUser, updateUserRole } from '../services/adminUsersService'
import '../styles/admin.css'
import '../styles/admin-pages.css'
import '../styles/admin-overrides.css'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const ROLE_OPTIONS = [{ value: 'normal', label: 'Normal User' }, { value: 'admin', label: 'Administrator' }]

function StatusMessage({ status, message }) { return message ? <p className={status === 'success' ? 'admin-success' : 'admin-error'} role="status">{message}</p> : null }
function SubmitButton({ status, children }) { return <div className="admin-actions"><button type="submit" className="primary" disabled={status === 'loading'}>{status === 'loading' ? 'Saving…' : children}</button></div> }

function AddUserForm() {
  const [form, setForm] = useState({ firstName: '', lastName: '', email: '', password: '', confirmPassword: '', role: 'normal', branchId: '' })
  const [message, setMessage] = useState('')
  const [status, setStatus] = useState('idle')
  const update = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }))

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
      <input aria-label="Branch" placeholder="Branch" value={form.branchId} onChange={update('branchId')} />
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
  const [tab, setTab] = useState('add')
  const panels = { add: <AddUserForm />, role: <ManagedForm kind="role" />, password: <ManagedForm kind="password" />, delete: <ManagedForm kind="delete" /> }
  return <main className="admin-shell"><AdminSidebar active="users" /><section className="admin-main"><AdminTopBar title="Users" description="Manage user accounts and access levels." /><div className="admin-tabs">{[['add', 'Add User'], ['role', 'Access'], ['password', 'Password'], ['delete', 'Remove User']].map(([key, label]) => <button key={key} className={tab === key ? 'active' : ''} type="button" onClick={() => setTab(key)}>{label}</button>)}</div>{panels[tab]}</section></main>
}
