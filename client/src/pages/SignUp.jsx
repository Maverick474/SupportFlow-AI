import { useMemo, useState } from 'react'

import { useSupportFlow } from '../context/contextApi.jsx'

function createWorkspaceId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return '00000000-0000-4000-8000-000000000000'
}

export default function SignUp({ onNavigate }) {
  const { signUp, backendOnline } = useSupportFlow()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [workspaceId, setWorkspaceId] = useState(createWorkspaceId)
  const [showWorkspace, setShowWorkspace] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const passwordReady = useMemo(() => password.length >= 8, [password])

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await signUp({
        fullName: fullName.trim(),
        email: email.trim(),
        password,
        workspaceId: workspaceId.trim(),
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
              placeholder="At least 8 characters"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              minLength={8}
              required
            />
            <small className={passwordReady ? 'field-hint valid' : 'field-hint'}>
              <span>{passwordReady ? '✓' : '•'}</span> Minimum 8 characters
            </small>
          </label>

          <div className="workspace-field">
            <div className="workspace-label-row">
              <span>Workspace ID</span>
              <button type="button" onClick={() => setShowWorkspace((value) => !value)}>
                {showWorkspace ? 'Hide details' : 'Workspace details'}
              </button>
            </div>
            {showWorkspace ? (
              <>
                <input
                  type="text"
                  value={workspaceId}
                  onChange={(event) => setWorkspaceId(event.target.value)}
                  aria-label="Workspace ID"
                  required
                />
                <button className="secondary-small-button" type="button" onClick={() => setWorkspaceId(createWorkspaceId())}>
                  Generate a new ID
                </button>
              </>
            ) : (
              <div className="workspace-summary">
                <span className="status-dot online" /> New workspace ID generated securely
              </div>
            )}
          </div>

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
