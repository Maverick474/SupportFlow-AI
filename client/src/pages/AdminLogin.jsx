import { useState } from 'react'

import { useSupportFlow } from '../context/contextApi.jsx'


export default function AdminLogin({ onNavigate }) {
  const { login, backendOnline } = useSupportFlow()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await login({
        email: email.trim(),
        password,
        allowedRoles: ['owner', 'admin'],
      })
      onNavigate('/admin', true)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="auth-card admin-auth-card" aria-labelledby="admin-login-title">
      <div className="auth-story admin-auth-story">
        <div className="eyebrow"><span /> Restricted administration</div>
        <h1>Manage trusted knowledge for every support conversation.</h1>
        <p>
          Administrators publish approved PDF documents to the shared vector
          knowledge base. Customer accounts can search that knowledge without
          receiving upload permissions.
        </p>
        <div className="auth-proof-grid">
          <div><strong>Admin</strong><span>Role-protected access</span></div>
          <div><strong>PDF</strong><span>Validated document upload</span></div>
          <div><strong>Shared</strong><span>One approved knowledge base</span></div>
        </div>
        <blockquote>
          “Knowledge management is restricted; grounded answers remain
          available to every authenticated customer.”
        </blockquote>
      </div>

      <div className="auth-form-panel">
        <div className="auth-form-heading">
          <span className={'server-indicator ' + (backendOnline ? 'ready' : '')}>
            <span /> {backendOnline ? 'Backend connected' : 'Waiting for backend'}
          </span>
          <h2 id="admin-login-title">Administrator sign in</h2>
          <p>Use an account with the admin or owner role.</p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            <span>Administrator email</span>
            <input
              type="email"
              autoComplete="email"
              placeholder="admin@company.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>

          <label>
            <span>Password</span>
            <div className="password-field">
              <input
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                placeholder="Enter your password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword((value) => !value)}
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
          </label>

          {error && <div className="form-error" role="alert">{error}</div>}

          <button className="primary-button" type="submit" disabled={submitting}>
            {submitting ? (
              <><span className="spinner" /> Verifying administrator…</>
            ) : (
              'Sign in to administration'
            )}
          </button>
        </form>

        <p className="auth-switch">
          Signing in as a customer?{' '}
          <button type="button" onClick={() => onNavigate('/login')}>
            Go to customer login
          </button>
        </p>
      </div>
    </section>
  )
}
