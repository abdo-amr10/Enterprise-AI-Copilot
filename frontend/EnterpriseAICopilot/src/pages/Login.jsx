import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import Logo from '../assets/Logo.png'
import '../styles/login.css'
import {
  IconMail,
  IconLock,
  IconEye,
  IconEyeOff,
  IconAlertCircle,
  IconLoader,
  IconArrowRight,
} from "../components/icons";
import { useAuth } from '../context/useAuth'
import { HOME_BY_ROLE } from '../config/routes'

function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [errors, setErrors] = useState({})
  const [isLoading, setIsLoading] = useState(false)
  const [serverError, setServerError] = useState('')
  const { login, isAuthenticated, user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  if (isAuthenticated) return <Navigate to={HOME_BY_ROLE[user.role]} replace />

  const handleSubmit = (event) => {
    event.preventDefault()
    const nextErrors = {}
    if (!email.trim()) nextErrors.email = 'Work email is required.'
    else if (!/^\S+@\S+\.\S+$/.test(email)) nextErrors.email = 'Enter a valid work email address.'
    if (!password) nextErrors.password = 'Password is required.'
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) return

    setIsLoading(true); setServerError('')
    login({ email, password }).then((nextUser) => navigate(location.state?.from || HOME_BY_ROLE[nextUser.role], { replace: true })).catch((error) => setServerError(error.message)).finally(() => setIsLoading(false))
  }

  return (
    <main className="login-page">
      <section className="login-brand-panel" aria-label="Enterprise AI Copilot">
        <div className="login-brand-mark">
          <img src={Logo} alt="Enterprise AI Copilot" />
        </div>

        <div className="login-brand-copy">
          <p className="login-eyebrow">Enterprise AI Copilot</p>
          <h1>Intelligence that moves your business forward.</h1>
          <p>
            Ask your enterprise data the right questions and get secure, trusted answers.
          </p>
        </div>

        <div className="login-brand-orbit login-brand-orbit-one" />
        <div className="login-brand-orbit login-brand-orbit-two" />
        <div className="login-brand-grid" aria-hidden="true" />
      </section>

      <section className="login-form-panel" aria-labelledby="login-title">
        <div className="login-form-wrap">
          <div className="login-mobile-brand">
            <img src={Logo} alt="" />
            <span>Enterprise AI Copilot</span>
          </div>

          <div className="login-heading">
            <p className="login-welcome">Welcome back</p>
            <h2 id="login-title">Sign in to your account</h2>
            <p>Enter your details to access your secure workspace.</p>
          </div>

          <form className="login-form" onSubmit={handleSubmit} noValidate>
            <label htmlFor="email">Work email</label>
            <div className="login-input-wrap">
              <IconMail className="login-input-icon" aria-hidden="true" />
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="you@enterprise.com"
                value={email}
                onChange={(event) => { setEmail(event.target.value); setErrors((current) => ({ ...current, email: undefined })) }}
                aria-invalid={Boolean(errors.email)}
              />
            </div>
            {errors.email && <p className="login-field-error" role="alert"><IconAlertCircle aria-hidden="true" />{errors.email}</p>}

            <div className="login-password-label">
              <label htmlFor="password">Password</label>

            </div>
            <div className="login-input-wrap">
              <IconLock className="login-input-icon" aria-hidden="true" />
              <input
                id="password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                placeholder="Enter your password"
                value={password}
                onChange={(event) => { setPassword(event.target.value); setErrors((current) => ({ ...current, password: undefined })) }}
                aria-invalid={Boolean(errors.password)}
              />
              <button className="login-password-toggle" type="button" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? 'Hide password' : 'Show password'}>
                {showPassword ? <IconEyeOff aria-hidden="true" /> : <IconEye aria-hidden="true" />}
              </button>
            </div>
            {errors.password && <p className="login-field-error" role="alert"><IconAlertCircle aria-hidden="true" />{errors.password}</p>}
            {serverError && <p className="login-field-error" role="alert"><IconAlertCircle aria-hidden="true" />{serverError}</p>}

            <button className="login-submit" type="submit" disabled={isLoading}>
              {isLoading ? <><IconLoader className="login-loader" aria-hidden="true" />Signing in...</> : <>Sign in
              <IconArrowRight aria-hidden="true" />
              </>}
            </button>
          </form>

          <p className="login-support">
            Need access? Contact your administrator to have an account created
            for you.
            </p>
        </div>
      </section>
    </main>
  )
}

export default Login
