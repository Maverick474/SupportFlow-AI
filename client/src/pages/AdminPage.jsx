import { useRef, useState } from 'react'

import Header from '../components/Header.jsx'
import { useSupportFlow } from '../context/contextApi.jsx'


const MAX_PDF_BYTES = 20 * 1024 * 1024
const KNOWLEDGE_SCOPES = [
  { value: 'auto', label: 'All support agents' },
  { value: 'general', label: 'General support' },
  { value: 'technical', label: 'Technical support' },
  { value: 'billing', label: 'Billing support' },
  { value: 'account', label: 'Account support' },
  { value: 'policy', label: 'Policy support' },
]


function formatFileSize(bytes) {
  if (bytes < 1024 * 1024) {
    return Math.max(1, Math.round(bytes / 1024)) + ' KB'
  }
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}


export default function AdminPage({ onNavigate }) {
  const { user, backendOnline, uploadKnowledge } = useSupportFlow()
  const [file, setFile] = useState(null)
  const [agentType, setAgentType] = useState('auto')
  const [replaceExisting, setReplaceExisting] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const fileInputRef = useRef(null)
  const isAdmin = ['owner', 'admin'].includes(user?.role)

  if (!isAdmin) return null

  function resetUpload() {
    setFile(null)
    setError('')
    setResult(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  function handleFileChange(event) {
    const selectedFile = event.target.files?.[0] || null
    setError('')
    setResult(null)

    if (!selectedFile) {
      setFile(null)
      return
    }
    if (!selectedFile.name.toLowerCase().endsWith('.pdf')) {
      setError('Please choose a valid PDF document.')
      setFile(null)
      event.target.value = ''
      return
    }
    if (selectedFile.size > MAX_PDF_BYTES) {
      setError('The PDF must be 20 MB or smaller.')
      setFile(null)
      event.target.value = ''
      return
    }
    setFile(selectedFile)
  }

  async function handleUpload(event) {
    event.preventDefault()
    if (!file || uploading) return

    setError('')
    setResult(null)
    setUploading(true)
    try {
      const uploadResult = await uploadKnowledge({
        file,
        agentType,
        replaceExisting,
      })
      setResult(uploadResult)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setUploading(false)
    }
  }

  const selectedScope = KNOWLEDGE_SCOPES.find(
    (scope) => scope.value === agentType,
  )?.label

  return (
    <div className="admin-shell">
      <Header
        adminView
        homePath="/admin"
        logoutPath="/admin/login"
        onNavigate={onNavigate}
      />

      <main className="admin-main">
        <section className="admin-hero">
          <div>
            <span className="eyebrow"><span /> Knowledge administration</span>
            <h1>Shared support knowledge</h1>
            <p>
              Upload approved documents once. Every authenticated customer can
              retrieve the resulting knowledge chunks while their sessions and
              conversation histories remain separate.
            </p>
          </div>
          <button
            type="button"
            className="admin-chat-button"
            onClick={() => onNavigate('/app')}
          >
            Open support chat <span aria-hidden="true">→</span>
          </button>
        </section>

        <section className="admin-status-grid" aria-label="Administration status">
          <article>
            <span className="admin-status-icon">A</span>
            <div><small>Signed-in role</small><strong>{user.role}</strong></div>
          </article>
          <article>
            <span className="admin-status-icon">✓</span>
            <div><small>API protection</small><strong>Admin enforced</strong></div>
          </article>
          <article>
            <span className="admin-status-icon">↗</span>
            <div>
              <small>Backend</small>
              <strong>{backendOnline ? 'Connected' : 'Unavailable'}</strong>
            </div>
          </article>
        </section>

        <section className="admin-panel" aria-labelledby="knowledge-upload-title">
          <header className="admin-panel-header">
            <div>
              <span className="eyebrow"><span /> PDF ingestion</span>
              <h2 id="knowledge-upload-title">Upload a knowledge document</h2>
              <p>
                SupportFlow extracts, chunks, embeds, and stores the document
                in the shared Supabase vector knowledge base.
              </p>
            </div>
            <span className="admin-only-badge">Admin only</span>
          </header>

          <form className="upload-form admin-upload-form" onSubmit={handleUpload}>
            <label className={'pdf-dropzone ' + (file ? 'selected' : '')}>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                onChange={handleFileChange}
                disabled={uploading || Boolean(result)}
              />
              <span className="pdf-file-icon" aria-hidden="true">PDF</span>
              <span className="pdf-file-copy">
                <strong>{file ? file.name : 'Choose an approved PDF document'}</strong>
                <small>
                  {file
                    ? formatFileSize(file.size) + ' selected'
                    : 'PDF only, maximum file size 20 MB'}
                </small>
              </span>
              {!result && <b>{file ? 'Change' : 'Browse'}</b>}
            </label>

            <label className="admin-field">
              <span>Knowledge scope</span>
              <select
                value={agentType}
                onChange={(event) => setAgentType(event.target.value)}
                disabled={uploading || Boolean(result)}
              >
                {KNOWLEDGE_SCOPES.map((scope) => (
                  <option key={scope.value} value={scope.value}>
                    {scope.label}
                  </option>
                ))}
              </select>
              <small>
                Choose which support agent should retrieve this document.
              </small>
            </label>

            <div className="upload-details">
              <span>Knowledge scope <strong>{selectedScope}</strong></span>
              <span>Storage <strong>Supabase vectors</strong></span>
            </div>

            <label className="replace-checkbox">
              <input
                type="checkbox"
                checked={replaceExisting}
                onChange={(event) => setReplaceExisting(event.target.checked)}
                disabled={uploading || Boolean(result)}
              />
              <span>
                <strong>Replace a document with the same filename</strong>
                <small>
                  Prevents duplicate chunks when publishing an updated version.
                </small>
              </span>
            </label>

            {error && <div className="upload-alert error" role="alert">{error}</div>}
            {result && (
              <div className="upload-alert success" role="status">
                <strong>{result.document} is ready for retrieval.</strong>
                <span>
                  {result.pages} pages produced {result.chunks} searchable chunks.
                </span>
              </div>
            )}

            <footer className="upload-modal-actions">
              {result ? (
                <button
                  type="button"
                  className="upload-cancel-button"
                  onClick={resetUpload}
                >
                  Upload another PDF
                </button>
              ) : (
                <>
                  <button
                    type="button"
                    className="upload-cancel-button"
                    onClick={resetUpload}
                    disabled={uploading || !file}
                  >
                    Clear
                  </button>
                  <button
                    type="submit"
                    className="upload-submit-button"
                    disabled={!file || uploading || !backendOnline}
                  >
                    {uploading ? (
                      <><span className="spinner" /> Processing PDF</>
                    ) : (
                      'Upload and index'
                    )}
                  </button>
                </>
              )}
            </footer>
          </form>
        </section>
      </main>
    </div>
  )
}
