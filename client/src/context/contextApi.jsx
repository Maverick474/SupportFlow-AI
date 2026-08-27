/* oxlint-disable react/only-export-components */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

const SupportFlowContext = createContext(null)

const ACCESS_TOKEN_KEY = 'supportflow_access_token'
const REFRESH_TOKEN_KEY = 'supportflow_refresh_token'
const USER_KEY = 'supportflow_user'
const API_PREFIX = '/api/v1'

function readStoredUser() {
  try {
    const value = localStorage.getItem(USER_KEY)
    return value ? JSON.parse(value) : null
  } catch {
    return null
  }
}

function getErrorMessage(payload, status) {
  if (typeof payload?.detail === 'string') return payload.detail
  if (Array.isArray(payload?.detail)) {
    return payload.detail.map((item) => item.msg).join(', ')
  }
  return `Request failed with status ${status}.`
}

export function SupportFlowProvider({ children }) {
  const [user, setUser] = useState(readStoredUser)
  const [authReady, setAuthReady] = useState(false)
  const [conversations, setConversations] = useState([])
  const [conversationsLoading, setConversationsLoading] = useState(false)
  const [backendOnline, setBackendOnline] = useState(null)

  const accessTokenRef = useRef(localStorage.getItem(ACCESS_TOKEN_KEY))
  const refreshTokenRef = useRef(localStorage.getItem(REFRESH_TOKEN_KEY))
  const refreshPromiseRef = useRef(null)

  const saveSession = useCallback((session) => {
    accessTokenRef.current = session.access_token
    refreshTokenRef.current = session.refresh_token
    localStorage.setItem(ACCESS_TOKEN_KEY, session.access_token)
    localStorage.setItem(REFRESH_TOKEN_KEY, session.refresh_token)
    localStorage.setItem(USER_KEY, JSON.stringify(session.user))
    setUser(session.user)
  }, [])

  const clearSession = useCallback(() => {
    accessTokenRef.current = null
    refreshTokenRef.current = null
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    setUser(null)
    setConversations([])
  }, [])

  const parseResponse = useCallback(async (response) => {
    if (response.status === 204) return null
    const contentType = response.headers.get('content-type') || ''
    return contentType.includes('application/json')
      ? response.json()
      : response.text()
  }, [])

  const refreshAccessToken = useCallback(async () => {
    if (!refreshTokenRef.current) return false
    if (refreshPromiseRef.current) return refreshPromiseRef.current

    refreshPromiseRef.current = (async () => {
      try {
        const response = await fetch(`${API_PREFIX}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshTokenRef.current }),
        })
        const payload = await parseResponse(response)
        if (!response.ok) throw new Error(getErrorMessage(payload, response.status))
        saveSession(payload)
        return true
      } catch {
        clearSession()
        return false
      } finally {
        refreshPromiseRef.current = null
      }
    })()

    return refreshPromiseRef.current
  }, [clearSession, parseResponse, saveSession])

  const apiRequest = useCallback(
    async (path, options = {}, retryAfterRefresh = true) => {
      const sendRequest = () => {
        const headers = new Headers(options.headers || {})
        const isFormData =
          typeof FormData !== 'undefined' && options.body instanceof FormData
        if (options.body && !isFormData && !headers.has('Content-Type')) {
          headers.set('Content-Type', 'application/json')
        }
        if (accessTokenRef.current) {
          headers.set('Authorization', `Bearer ${accessTokenRef.current}`)
        }
        return fetch(`${API_PREFIX}${path}`, {
          ...options,
          headers,
        })
      }

      let response = await sendRequest()
      if (response.status === 401 && retryAfterRefresh) {
        const refreshed = await refreshAccessToken()
        if (refreshed) response = await sendRequest()
      }

      const payload = await parseResponse(response)
      if (!response.ok) throw new Error(getErrorMessage(payload, response.status))
      return payload
    },
    [parseResponse, refreshAccessToken],
  )

  const login = useCallback(
    async ({ email, password }) => {
      const response = await fetch(`${API_PREFIX}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const payload = await parseResponse(response)
      if (!response.ok) throw new Error(getErrorMessage(payload, response.status))
      saveSession(payload)
      return payload.user
    },
    [parseResponse, saveSession],
  )

  const signUp = useCallback(
    async ({ fullName, email, password, workspaceId }) => {
      const response = await fetch(`${API_PREFIX}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          full_name: fullName,
          email,
          password,
          workspace_id: workspaceId,
        }),
      })
      const payload = await parseResponse(response)
      if (!response.ok) throw new Error(getErrorMessage(payload, response.status))
      saveSession(payload)
      return payload.user
    },
    [parseResponse, saveSession],
  )

  const logout = useCallback(async () => {
    const refreshToken = refreshTokenRef.current
    try {
      if (refreshToken && accessTokenRef.current) {
        await apiRequest(
          '/auth/logout',
          {
            method: 'POST',
            body: JSON.stringify({ refresh_token: refreshToken }),
          },
          false,
        )
      }
    } finally {
      clearSession()
    }
  }, [apiRequest, clearSession])

  const loadConversations = useCallback(async () => {
    if (!accessTokenRef.current) return []
    setConversationsLoading(true)
    try {
      const result = await apiRequest('/conversations?limit=100')
      setConversations(result)
      return result
    } finally {
      setConversationsLoading(false)
    }
  }, [apiRequest])

  const loadMessages = useCallback(
    (conversationId) =>
      apiRequest(`/conversations/${conversationId}/messages?limit=1000`),
    [apiRequest],
  )

  const sendMessage = useCallback(
    async ({ question, conversationId, agentType }) => {
      const body = { question }
      if (conversationId) body.conversation_id = conversationId
      if (agentType && agentType !== 'auto') body.agent_type = agentType
      const result = await apiRequest('/chat', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      await loadConversations()
      return result
    },
    [apiRequest, loadConversations],
  )

  const uploadKnowledge = useCallback(
    async ({ file, agentType, replaceExisting = true }) => {
      const body = new FormData()
      body.append('file', file)
      if (agentType && agentType !== 'auto') {
        body.append('agent_type', agentType)
      }
      body.append('replace_existing', String(replaceExisting))

      return apiRequest('/knowledge/upload', {
        method: 'POST',
        body,
      })
    },
    [apiRequest],
  )

  useEffect(() => {
    let cancelled = false

    async function restoreSession() {
      if (!accessTokenRef.current) {
        if (!cancelled) setAuthReady(true)
        return
      }
      try {
        const currentUser = await apiRequest('/auth/me')
        if (!cancelled) {
          setUser(currentUser)
          localStorage.setItem(USER_KEY, JSON.stringify(currentUser))
        }
      } catch {
        if (!cancelled) clearSession()
      } finally {
        if (!cancelled) setAuthReady(true)
      }
    }

    restoreSession()
    return () => {
      cancelled = true
    }
  }, [apiRequest, clearSession])

  useEffect(() => {
    let active = true
    async function checkBackend() {
      try {
        const response = await fetch('/health')
        if (active) setBackendOnline(response.ok)
      } catch {
        if (active) setBackendOnline(false)
      }
    }
    checkBackend()
    const timer = window.setInterval(checkBackend, 30000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [])

  const value = useMemo(
    () => ({
      user,
      authReady,
      backendOnline,
      conversations,
      conversationsLoading,
      login,
      signUp,
      logout,
      loadConversations,
      loadMessages,
      sendMessage,
      uploadKnowledge,
    }),
    [
      user,
      authReady,
      backendOnline,
      conversations,
      conversationsLoading,
      login,
      signUp,
      logout,
      loadConversations,
      loadMessages,
      sendMessage,
      uploadKnowledge,
    ],
  )

  return (
    <SupportFlowContext.Provider value={value}>
      {children}
    </SupportFlowContext.Provider>
  )
}

export function useSupportFlow() {
  const context = useContext(SupportFlowContext)
  if (!context) {
    throw new Error('useSupportFlow must be used inside SupportFlowProvider.')
  }
  return context
}
