import { useCallback, useEffect, useState } from 'react'

import './App.css'
import Footer from './components/Footer.jsx'
import Header from './components/Header.jsx'
import { useSupportFlow } from './context/contextApi.jsx'
import Login from './pages/Login.jsx'
import Main from './pages/Main.jsx'
import SignUp from './pages/SignUp.jsx'

function normalizePath(pathname) {
  if (pathname === '/signup') return '/signup'
  if (pathname === '/app') return '/app'
  return '/login'
}

export default function App() {
  const { user, authReady } = useSupportFlow()
  const [path, setPath] = useState(() => normalizePath(window.location.pathname))

  const navigate = useCallback((nextPath, replace = false) => {
    const normalized = normalizePath(nextPath)
    window.history[replace ? 'replaceState' : 'pushState']({}, '', normalized)
    setPath(normalized)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [])

  useEffect(() => {
    const handlePopState = () => setPath(normalizePath(window.location.pathname))
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    if (!authReady) return
    const requiredPath = user ? '/app' : path === '/app' ? '/login' : path
    if (window.location.pathname !== requiredPath) {
      window.history.replaceState({}, '', requiredPath)
    }
  }, [authReady, path, user])

  if (!authReady) {
    return (
      <div className="app-loading" role="status">
        <span className="brand-mark large" aria-hidden="true"><span /><span /><span /></span>
        <p>Preparing your support workspace…</p>
      </div>
    )
  }

  if (user) return <Main onNavigate={navigate} />

  return (
    <div className="public-shell">
      <Header publicView onNavigate={navigate} />
      <main className="auth-main">
        {path === '/signup' ? (
          <SignUp onNavigate={navigate} />
        ) : (
          <Login onNavigate={navigate} />
        )}
      </main>
      <Footer />
    </div>
  )
}
