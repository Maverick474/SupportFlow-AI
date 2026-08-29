import { useMemo, useState } from 'react'

import { useSupportFlow } from '../context/contextApi.jsx'

const PASSWORD_PATTERN = /^(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9\s]).{8,}$/

export default function SignUp({ onNavigate }) {
  const { signUp, backendOnline } = useSupportFlow()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const passwordRules = useMemo(
    () => ({
      minimumLength: password.length >= 8,
      uppercase: /[A-Z]/.test(password),
      number: /\d/.test(password),
      special: /[^A-Za-z0-9\s]/.test(password),
    }),
    [password],
  )
  const passwordReady = useMemo(
    () => PASSWORD_PATTERN.test(password),
    [password],
  )

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    if (!passwordReady) {
      setError('Password must satisfy all four requirements.')
      return
    }
    setSubmitting(true)
    try {
      await signUp({
        fullName: fullName.trim(),
        email: email.trim(),
        password,
      })
      onNavigate('/app', true)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="auth-card signup-card" aria-labelledby="signup-title">
      <div className="auth-story signup-story">
        <div className="eyebrow"><span /> Your support control room</div>
        <h1>Bring your knowledge, agents, and conversations together.</h1>
        <p>
          Create a workspace for your team. SupportFlow keeps user sessions in
          MongoDB, conversations in Redis, and approved knowledge in Supabase.
        </p>
        <ol className="setup-steps">
          <li><span>1</span><div><strong>Create your workspace</strong><p>Start with a secure workspace identifier.</p></div></li>
          <li><span>2</span><div><strong>Ingest your handbook</strong><p>Your PDF becomes searchable evidence.</p></div></li>
          <li><span>3</span><div><strong>Start resolving tickets</strong><p>Generator and validator work together.</p></div></li>
        </ol>
      </div>

      <div className="auth-form-panel">
        <div className="auth-form-heading">
          <span className={`server-indicator ${backendOnline ? 'ready' : ''}`}>
            <span /> {backendOnline ? 'Backend connected' : 'Waiting for backend'}
          </span>
          <h2 id="signup-title">Create your account</h2>
          <p>Set up your SupportFlow workspace in a minute.</p>
        </div>

        <form className="auth-form compact-form" onSubmit={handleSubmit}>
          <label>
            <span>Full name</span>
            <input
              type="text"
              autoComplete="name"
              placeholder="Alex Morgan"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              minLength={2}
              required
            />
          </label>

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
            <input
              type="password"
              autoComplete="new-password"
              placeholder="Create a strong password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              minLength={8}
              pattern={PASSWORD_PATTERN.source}
              title="Use at least 8 characters with one uppercase letter, one number, and one special character."
              required
            />
            <div className="password-requirements" aria-live="polite">
              <small className={passwordRules.minimumLength ? 'field-hint valid' : 'field-hint'}>
                <span>{passwordRules.minimumLength ? '✓' : '•'}</span> Minimum 8 characters
              </small>
              <small className={passwordRules.uppercase ? 'field-hint valid' : 'field-hint'}>
                <span>{passwordRules.uppercase ? '✓' : '•'}</span> One uppercase letter
              </small>
              <small className={passwordRules.number ? 'field-hint valid' : 'field-hint'}>
                <span>{passwordRules.number ? '✓' : '•'}</span> One number
              </small>
              <small className={passwordRules.special ? 'field-hint valid' : 'field-hint'}>
                <span>{passwordRules.special ? '✓' : '•'}</span> One special character
              </small>
            </div>
          </label>

          {error && <div className="form-error" role="alert">{error}</div>}

          <button className="primary-button" type="submit" disabled={submitting || !passwordReady}>
            {submitting ? <><span className="spinner" /> Creating workspace…</> : 'Create workspace'}
          </button>
        </form>

        <p className="auth-switch">
          Already have an account?{' '}
          <button type="button" onClick={() => onNavigate('/login')}>Sign in</button>
        </p>
      </div>
    </section>
  )
}
