import { useState } from 'react'

import { useSupportFlow } from '../context/contextApi.jsx'

export default function Login({ onNavigate }) {
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
      await login({ email: email.trim(), password })
      onNavigate('/app', true)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="auth-card" aria-labelledby="login-title">
      <div className="auth-story">
        <div className="eyebrow"><span /> AI support operations</div>
        <h1>Resolve customer questions with answers your team can trust.</h1>
        <p>
          SupportFlow searches your approved handbook, drafts a clear response,
          and independently validates every answer before it reaches your team.
        </p>
        <div className="auth-proof-grid">
          <div><strong>2-step</strong><span>Generate and validate</span></div>
          <div><strong>Cited</strong><span>Answers from your PDF</span></div>
          <div><strong>Traced</strong><span>Every agent decision</span></div>
        </div>
        <blockquote>
          “One workspace for grounded support, complete chat history, and safer escalation.”
        </blockquote>
      </div>

      <div className="auth-form-panel">
        <div className="auth-form-heading">
          <span className={`server-indicator ${backendOnline ? 'ready' : ''}`}>
            <span /> {backendOnline ? 'Backend connected' : 'Waiting for backend'}
          </span>
          <h2 id="login-title">Welcome back</h2>
          <p>Sign in to continue to your support workspace.</p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            <span>Work email</span>
            <input
              type="email"
              autoComplete="email"
              placeholder="you@company.com"
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
              <button type="button" onClick={() => setShowPassword((value) => !value)}>
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
          </label>

          {error && <div className="form-error" role="alert">{error}</div>}

          <button className="primary-button" type="submit" disabled={submitting}>
            {submitting ? <><span className="spinner" /> Signing in…</> : 'Sign in to SupportFlow'}
          </button>
        </form>

        <p className="auth-switch">
          New to SupportFlow?{' '}
          <button type="button" onClick={() => onNavigate('/signup')}>Create an account</button>
        </p>
      </div>
    </section>
  )
}
