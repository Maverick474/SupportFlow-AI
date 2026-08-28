import { useEffect, useMemo, useRef, useState } from 'react'

import Header from '../components/Header.jsx'
import { useSupportFlow } from '../context/contextApi.jsx'

const AGENT_OPTIONS = [
  { value: 'auto', label: 'Auto route' },
  { value: 'general', label: 'General' },
  { value: 'technical', label: 'Technical' },
  { value: 'billing', label: 'Billing' },
  { value: 'account', label: 'Account' },
  { value: 'policy', label: 'Policy' },
]

const MAX_PDF_BYTES = 20 * 1024 * 1024
const STARTER_QUESTIONS = [
  {
    label: 'Account access',
    question: 'What should a customer do if they cannot access their account?',
    agent: 'account',
  },
  {
    label: 'Billing policy',
    question: 'How should a duplicate charge be handled according to our policy?',
    agent: 'billing',
  },
  {
    label: 'Technical support',
    question: 'What troubleshooting steps should we recommend for a failed webhook?',
    agent: 'technical',
  },
]

function formatConversationTime(value) {
  const date = new Date(value)
  const today = new Date()
  if (date.toDateString() === today.toDateString()) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

function formatFileSize(bytes) {
  if (bytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(bytes / 1024))} KB`
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function agentLabel(agentType) {
  return AGENT_OPTIONS.find((agent) => agent.value === agentType)?.label || 'General'
}

function verdictLabel(verdict, agentType) {
  if (verdict === 'pass') return '✓ Validated'
  if (verdict === 'refuse') return 'Rejected'
  if (verdict === 'escalate') return 'Escalate'
  if (verdict === 'revise') return 'Revision'
  return agentLabel(agentType)
}

function removeChatCitations(content) {
  let visibleText = ''
  let cursor = 0

  while (cursor < content.length) {
    const citationStart = content.indexOf('[', cursor)
    if (citationStart === -1) {
      visibleText += content.slice(cursor)
      break
    }

    const citationEnd = content.indexOf(']', citationStart + 1)
    if (citationEnd === -1) {
      visibleText += content.slice(cursor)
      break
    }

    const label = content.slice(citationStart + 1, citationEnd)
    const looksLikeSourceLabel = label.toLowerCase().includes(', p.')
    visibleText += content.slice(cursor, citationStart)
    if (!looksLikeSourceLabel) {
      visibleText += content.slice(citationStart, citationEnd + 1)
    }
    cursor = citationEnd + 1
  }

  const lineBreak = String.fromCharCode(10)
  const compactedLines = []
  visibleText.split(lineBreak).forEach((line) => {
    const cleanedLine = line.trimEnd()
    if (cleanedLine.trim() === '' && compactedLines.at(-1) === '') return
    compactedLines.push(cleanedLine)
  })
  return compactedLines.join(lineBreak).trim()
}

export default function Main({ onNavigate }) {
  const {
    user,
    conversations,
    conversationsLoading,
    loadConversations,
    loadMessages,
    renameConversation,
    deleteConversation,
    sendMessage,
    uploadKnowledge,
  } = useSupportFlow()

  const [selectedConversation, setSelectedConversation] = useState(null)
  const [messages, setMessages] = useState([])
  const [messagesLoading, setMessagesLoading] = useState(false)
  const [question, setQuestion] = useState('')
  const [agentType, setAgentType] = useState('auto')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploadFile, setUploadFile] = useState(null)
  const [replaceExisting, setReplaceExisting] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [uploadResult, setUploadResult] = useState(null)
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)
  const uploadInputRef = useRef(null)
  const messageIdRef = useRef(0)
  const [editingConversationId, setEditingConversationId] = useState(null)
  const [renameTitle, setRenameTitle] = useState('')
  const [conversationActionId, setConversationActionId] = useState(null)

  const canManageKnowledge = ['owner', 'admin'].includes(user?.role)

  useEffect(() => {
    loadConversations().catch((requestError) => setError(requestError.message))
  }, [loadConversations])

  useEffect(() => {
    if (!selectedConversation) return undefined

    let active = true
    loadMessages(selectedConversation)
      .then((result) => {
        if (active) setMessages(result)
      })
      .catch((requestError) => {
        if (active) setError(requestError.message)
      })
      .finally(() => {
        if (active) setMessagesLoading(false)
      })

    return () => {
      active = false
    }
  }, [loadMessages, selectedConversation])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, sending])

  const filteredConversations = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return conversations
    return conversations.filter((conversation) =>
      conversation.title.toLowerCase().includes(query),
    )
  }, [conversations, search])

  function beginNewConversation() {
    setSelectedConversation(null)
    setMessages([])
    setQuestion('')
    setAgentType('auto')
    setError('')
    setMessagesLoading(false)
    setSidebarOpen(false)
    window.setTimeout(() => textareaRef.current?.focus(), 0)
  }

  function openConversation(conversation) {
    setMessagesLoading(true)
    setError('')
    setSelectedConversation(conversation.conversation_id)
    setAgentType(conversation.agent_type || 'auto')
    setSidebarOpen(false)
  }

  function startRenamingConversation(event, conversation) {
    event.stopPropagation()
    if (conversationActionId) return
    setEditingConversationId(conversation.conversation_id)
    setRenameTitle(conversation.title)
  }

  function cancelRenamingConversation() {
    setEditingConversationId(null)
    setRenameTitle('')
  }

  async function submitConversationRename(event, conversation) {
    event.preventDefault()
    const title = renameTitle.trim()
    if (!title || conversationActionId) return
    if (title === conversation.title) {
      cancelRenamingConversation()
      return
    }

    setError('')
    setConversationActionId(conversation.conversation_id)
    try {
      await renameConversation(conversation.conversation_id, title)
      cancelRenamingConversation()
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setConversationActionId(null)
    }
  }

  async function handleConversationDelete(event, conversation) {
    event.stopPropagation()
    if (conversationActionId || sending) return
    const confirmed = window.confirm(
      'Delete "' + conversation.title + '" and its chat history? This cannot be undone.',
    )
    if (!confirmed) return

    setError('')
    setConversationActionId(conversation.conversation_id)
    try {
      await deleteConversation(conversation.conversation_id)
      if (selectedConversation === conversation.conversation_id) {
        beginNewConversation()
      }
      if (editingConversationId === conversation.conversation_id) {
        cancelRenamingConversation()
      }
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setConversationActionId(null)
    }
  }

  async function submitQuestion(event, suggestedQuestion, suggestedAgent) {
    event?.preventDefault()
    const outgoingQuestion = (suggestedQuestion || question).trim()
    if (!outgoingQuestion || sending) return

    const selectedAgent = suggestedAgent || agentType
    messageIdRef.current += 1
    const optimisticMessage = {
      id: `local-${messageIdRef.current}`,
      role: 'user',
      content: outgoingQuestion,
      citations: [],
    }

    setQuestion('')
    setError('')
    setSending(true)
    setMessages((current) => [...current, optimisticMessage])
    if (suggestedAgent) setAgentType(suggestedAgent)

    try {
      const result = await sendMessage({
        question: outgoingQuestion,
        conversationId: selectedConversation,
        agentType: selectedAgent,
      })
      messageIdRef.current += 1
      const assistantMessage = {
        id: `response-${messageIdRef.current}`,
        role: 'assistant',
        content: result.final_answer,
        agent_type: result.agent_type,
        citations: result.citations || [],
        verdict: result.verdict,
        revision_count: result.revision_count,
      }
      setMessages((current) => [...current, assistantMessage])
      setSelectedConversation(result.conversation_id)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSending(false)
    }
  }

  function handleComposerKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submitQuestion(event)
    }
  }

  function openUploadDialog() {
    if (!canManageKnowledge) {
      setError('Only a workspace owner or admin can upload knowledge documents.')
      return
    }
    setUploadError('')
    setUploadResult(null)
    setUploadFile(null)
    if (uploadInputRef.current) uploadInputRef.current.value = ''
    setUploadOpen(true)
  }

  function closeUploadDialog() {
    if (!uploading) setUploadOpen(false)
  }

  function handleUploadFileChange(event) {
    const selectedFile = event.target.files?.[0] || null
    setUploadError('')
    setUploadResult(null)

    if (!selectedFile) {
      setUploadFile(null)
      return
    }
    if (!selectedFile.name.toLowerCase().endsWith('.pdf')) {
      setUploadError('Please choose a PDF document.')
      setUploadFile(null)
      event.target.value = ''
      return
    }
    if (selectedFile.size > MAX_PDF_BYTES) {
      setUploadError('The PDF must be 20 MB or smaller.')
      setUploadFile(null)
      event.target.value = ''
      return
    }
    setUploadFile(selectedFile)
  }

  async function submitKnowledgeUpload(event) {
    event.preventDefault()
    if (!uploadFile || uploading) return

    setUploadError('')
    setUploadResult(null)
    setUploading(true)
    try {
      const result = await uploadKnowledge({
        file: uploadFile,
        agentType,
        replaceExisting,
      })
      setUploadResult(result)
    } catch (requestError) {
      setUploadError(requestError.message)
    } finally {
      setUploading(false)
    }
  }

  const activeConversation = conversations.find(
    (conversation) => conversation.conversation_id === selectedConversation,
  )

  return (
    <div className="workspace-shell">
      {sidebarOpen && (
        <button
          type="button"
          className="sidebar-backdrop"
          aria-label="Close conversation sidebar"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside className={`conversation-sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-brand-row">
          <button className="brand" type="button" onClick={beginNewConversation}>
            <span className="brand-mark" aria-hidden="true"><span /><span /><span /></span>
            <span className="brand-name">SupportFlow</span>
            <span className="brand-badge">AI</span>
          </button>
          <button className="sidebar-close" type="button" onClick={() => setSidebarOpen(false)} aria-label="Close sidebar">×</button>
        </div>

        <button className="new-chat-button" type="button" onClick={beginNewConversation}>
          <span aria-hidden="true">＋</span>
          New conversation
        </button>

        <label className="conversation-search">
          <span aria-hidden="true">⌕</span>
          <input
            type="search"
            placeholder="Search conversations"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>

        <div className="conversation-heading">
          <span>Recent conversations</span>
          <small>{conversations.length}</small>
        </div>

        <nav className="conversation-list" aria-label="Conversation history">
          {conversationsLoading && conversations.length === 0 ? (
            <div className="conversation-skeletons"><span /><span /><span /></div>
          ) : filteredConversations.length > 0 ? (
            filteredConversations.map((conversation) => (
              <div
                key={conversation.conversation_id}
                className={
                  selectedConversation === conversation.conversation_id
                    ? 'conversation-item-shell active'
                    : 'conversation-item-shell'
                }
              >
                {editingConversationId === conversation.conversation_id ? (
                  <form
                    className="conversation-rename-form"
                    onSubmit={(event) => submitConversationRename(event, conversation)}
                  >
                    <input
                      autoFocus
                      type="text"
                      maxLength={80}
                      value={renameTitle}
                      onChange={(event) => setRenameTitle(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Escape') cancelRenamingConversation()
                      }}
                      aria-label="Conversation name"
                    />
                    <button
                      type="submit"
                      disabled={!renameTitle.trim() || conversationActionId === conversation.conversation_id}
                      aria-label="Save conversation name"
                      title="Save"
                    >
                      {conversationActionId === conversation.conversation_id ? '…' : '✓'}
                    </button>
                    <button
                      type="button"
                      onClick={cancelRenamingConversation}
                      disabled={conversationActionId === conversation.conversation_id}
                      aria-label="Cancel renaming"
                      title="Cancel"
                    >
                      ×
                    </button>
                  </form>
                ) : (
                  <>
                    <button
                      type="button"
                      className="conversation-item"
                      onClick={() => openConversation(conversation)}
                    >
                      <span className="conversation-icon" aria-hidden="true">◎</span>
                      <span className="conversation-copy">
                        <strong>{conversation.title}</strong>
                        <small>{agentLabel(conversation.agent_type)} · {formatConversationTime(conversation.updated_at)}</small>
                      </span>
                    </button>
                    <span className="conversation-actions">
                      <button
                        type="button"
                        onClick={(event) => startRenamingConversation(event, conversation)}
                        disabled={Boolean(conversationActionId)}
                        aria-label={'Rename ' + conversation.title}
                        title="Rename conversation"
                      >
                        ✎
                      </button>
                      <button
                        type="button"
                        className="delete"
                        onClick={(event) => handleConversationDelete(event, conversation)}
                        disabled={Boolean(conversationActionId) || sending}
                        aria-label={'Delete ' + conversation.title}
                        title="Delete conversation"
                      >
                        {conversationActionId === conversation.conversation_id ? '…' : '×'}
                      </button>
                    </span>
                  </>
                )}
              </div>
            ))
          ) : (
            <div className="empty-conversations">
              <span aria-hidden="true">◇</span>
              <p>{search ? 'No matching conversations' : 'Your conversations will appear here'}</p>
            </div>
          )}
        </nav>

        <div className="sidebar-workspace">
          <span className="workspace-avatar">{user?.full_name?.charAt(0)?.toUpperCase()}</span>
          <div><strong>{user?.full_name}</strong><small>Workspace member</small></div>
          <span className="status-dot online" title="Session active" />
        </div>
      </aside>

      <section className="chat-workspace">
        <Header onNavigate={onNavigate} onToggleSidebar={() => setSidebarOpen(true)} />

        <div className="chat-toolbar">
          <div>
            <span className="toolbar-label">Active support agent</span>
            <select value={agentType} onChange={(event) => setAgentType(event.target.value)} aria-label="Select support agent">
              {AGENT_OPTIONS.map((agent) => <option value={agent.value} key={agent.value}>{agent.label}</option>)}
            </select>
          </div>
          <div className="toolbar-actions">
            <button
              type="button"
              className={`knowledge-upload-button ${canManageKnowledge ? '' : 'locked'}`}
              onClick={openUploadDialog}
              title={canManageKnowledge ? 'Upload a PDF to the workspace knowledge base' : 'Owner or admin access is required'}
            >
              <span aria-hidden="true">↑</span>
              Upload PDF
              {!canManageKnowledge && <small>Admin</small>}
            </button>
            <div className="thread-status">
              <span className="status-dot online" />
              {activeConversation ? 'Conversation saved in Redis' : 'Ready for a new question'}
            </div>
          </div>
        </div>

        <main className="chat-panel">
          <div className="messages-region" aria-live="polite">
            {messagesLoading ? (
              <div className="center-loader"><span className="spinner dark" /><p>Loading conversation…</p></div>
            ) : messages.length === 0 ? (
              <div className="welcome-state">
                <div className="welcome-symbol" aria-hidden="true"><span>✓</span></div>
                <span className="eyebrow centered"><span /> Grounded by your knowledge base</span>
                <h1>How can SupportFlow help today?</h1>
                <p>
                  Ask a support question. The generator drafts from your handbook,
                  then the validator checks every factual claim before answering.
                </p>
                <div className="starter-grid">
                  {STARTER_QUESTIONS.map((starter) => (
                    <button
                      type="button"
                      key={starter.label}
                      onClick={(event) => submitQuestion(event, starter.question, starter.agent)}
                    >
                      <span>{starter.label}</span>
                      <strong>{starter.question}</strong>
                      <small>Ask {agentLabel(starter.agent)} agent <b>→</b></small>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="message-list">
                {messages.map((message) => (
                  <article className={`message-row ${message.role}`} key={message.id}>
                    <div className="message-avatar" aria-hidden="true">
                      {message.role === 'assistant' ? 'SF' : user?.full_name?.charAt(0)?.toUpperCase()}
                    </div>
                    <div className="message-content">
                      <div className="message-meta">
                        <strong>{message.role === 'assistant' ? 'SupportFlow AI' : user?.full_name}</strong>
                        {message.role === 'assistant' && (
                          <span className={`verdict-chip ${message.verdict || 'saved'}`}>
                            {verdictLabel(message.verdict, message.agent_type)}
                          </span>
                        )}
                      </div>
                      <div className="message-bubble">{removeChatCitations(message.content)}</div>
                      {message.citations?.length > 0 && (
                        <div className="citation-list" aria-label="Answer sources">
                          {message.citations.map((citation) => <span key={citation}>Source · {citation}</span>)}
                        </div>
                      )}
                    </div>
                  </article>
                ))}
                {sending && (
                  <article className="message-row assistant typing-row">
                    <div className="message-avatar">SF</div>
                    <div className="message-content">
                      <div className="message-meta"><strong>SupportFlow AI</strong><span>Generating and validating</span></div>
                      <div className="typing-indicator"><i /><i /><i /></div>
                    </div>
                  </article>
                )}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          <div className="composer-zone">
            {error && <div className="chat-error" role="alert"><span>!</span>{error}<button type="button" onClick={() => setError('')}>×</button></div>}
            <form className="message-composer" onSubmit={submitQuestion}>
              <textarea
                ref={textareaRef}
                rows={1}
                maxLength={8000}
                placeholder="Ask a question about your support handbook…"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={handleComposerKeyDown}
                disabled={sending}
                aria-label="Support question"
              />
              <div className="composer-footer">
                <span><kbd>Enter</kbd> to send · <kbd>Shift</kbd> + <kbd>Enter</kbd> for a new line</span>
                <button type="submit" disabled={sending || question.trim().length < 2} aria-label="Send question">
                  <span>Send</span><b aria-hidden="true">↑</b>
                </button>
              </div>
            </form>
            <p className="composer-note">SupportFlow may escalate when the handbook cannot safely answer a request.</p>
          </div>
        </main>
      </section>
      {uploadOpen && (
        <div className="upload-modal-backdrop" onMouseDown={closeUploadDialog}>
          <section
            className="upload-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="upload-dialog-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header className="upload-modal-header">
              <div>
                <span className="eyebrow"><span /> Knowledge base</span>
                <h2 id="upload-dialog-title">Upload a PDF document</h2>
              </div>
              <button type="button" onClick={closeUploadDialog} disabled={uploading} aria-label="Close upload dialog">x</button>
            </header>

            <form className="upload-form" onSubmit={submitKnowledgeUpload}>
              <p>
                SupportFlow will extract, chunk, embed, and save this document
                as searchable knowledge for your workspace.
              </p>

              <label className={`pdf-dropzone ${uploadFile ? 'selected' : ''}`}>
                <input
                  ref={uploadInputRef}
                  type="file"
                  accept=".pdf,application/pdf"
                  onChange={handleUploadFileChange}
                  disabled={uploading || Boolean(uploadResult)}
                />
                <span className="pdf-file-icon" aria-hidden="true">PDF</span>
                <span className="pdf-file-copy">
                  <strong>{uploadFile ? uploadFile.name : 'Choose a PDF from your device'}</strong>
                  <small>
                    {uploadFile
                      ? `${formatFileSize(uploadFile.size)} selected`
                      : 'PDF only, maximum file size 20 MB'}
                  </small>
                </span>
                {!uploadResult && <b>{uploadFile ? 'Change' : 'Browse'}</b>}
              </label>

              <div className="upload-details">
                <span>Knowledge scope <strong>{agentType === 'auto' ? 'All agents' : `${agentLabel(agentType)} agent`}</strong></span>
                <span>Storage <strong>Supabase vectors</strong></span>
              </div>

              <label className="replace-checkbox">
                <input
                  type="checkbox"
                  checked={replaceExisting}
                  onChange={(event) => setReplaceExisting(event.target.checked)}
                  disabled={uploading || Boolean(uploadResult)}
                />
                <span>
                  <strong>Replace an existing document with the same filename</strong>
                  <small>Prevents duplicate chunks when uploading a newer version.</small>
                </span>
              </label>

              {uploadError && <div className="upload-alert error" role="alert">{uploadError}</div>}
              {uploadResult && (
                <div className="upload-alert success" role="status">
                  <strong>{uploadResult.document} is ready.</strong>
                  <span>{uploadResult.pages} pages produced {uploadResult.chunks} searchable chunks.</span>
                </div>
              )}

              <footer className="upload-modal-actions">
                <button type="button" className="upload-cancel-button" onClick={closeUploadDialog} disabled={uploading}>
                  {uploadResult ? 'Close' : 'Cancel'}
                </button>
                {!uploadResult && (
                  <button type="submit" className="upload-submit-button" disabled={!uploadFile || uploading}>
                    {uploading ? <><span className="spinner" /> Processing PDF</> : 'Upload and index'}
                  </button>
                )}
              </footer>
            </form>
          </section>
        </div>
      )}
    </div>
  )
}
