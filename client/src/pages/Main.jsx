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

function agentLabel(agentType) {
  return AGENT_OPTIONS.find((agent) => agent.value === agentType)?.label || 'General'
}

export default function Main({ onNavigate }) {
  const {
    user,
    conversations,
    conversationsLoading,
    loadConversations,
    loadMessages,
    sendMessage,
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
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)
  const messageIdRef = useRef(0)

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
              <button
                type="button"
                key={conversation.conversation_id}
                className={selectedConversation === conversation.conversation_id ? 'conversation-item active' : 'conversation-item'}
                onClick={() => openConversation(conversation)}
              >
                <span className="conversation-icon" aria-hidden="true">◎</span>
                <span className="conversation-copy">
                  <strong>{conversation.title}</strong>
                  <small>{agentLabel(conversation.agent_type)} · {formatConversationTime(conversation.updated_at)}</small>
                </span>
              </button>
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
          <div className="thread-status">
            <span className="status-dot online" />
            {activeConversation ? 'Conversation saved in Redis' : 'Ready for a new question'}
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
                            {message.verdict === 'pass' ? '✓ Validated' : message.verdict ? message.verdict : agentLabel(message.agent_type)}
                          </span>
                        )}
                      </div>
                      <div className="message-bubble">{message.content}</div>
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
    </div>
  )
}
