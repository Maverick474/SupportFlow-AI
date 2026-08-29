import { useCallback, useEffect, useState } from 'react'

import './App.css'
import Footer from './components/Footer.jsx'
import Header from './components/Header.jsx'
import { useSupportFlow } from './context/contextApi.jsx'
import AdminLogin from './pages/AdminLogin.jsx'
import AdminPage from './pages/AdminPage.jsx'
import Login from './pages/Login.jsx'
import Main from './pages/Main.jsx'
import SignUp from './pages/SignUp.jsx'

const ADMIN_ROLES = ['owner', 'admin']

function normalizePath(pathname) {
  const normalized = pathname.length > 1
    ? pathname.replace(/\/+$/, '')
    : pathname
  if (normalized === '/signup') return '/signup'
  if (normalized === '/app') return '/app'
  if (normalized === '/admin') return '/admin'
  if (normalized === '/admin/login') return '/admin/login'
  return '/login'
}

function routeForSession(path, user) {
  if (!user) {
    if (path === '/app') return '/login'
    if (path === '/admin') return '/admin/login'
    return path
  }

  const isAdmin = ADMIN_ROLES.includes(user.role)
  if (!isAdmin) return '/app'
  if (path === '/app' || path === '/admin') return path
  return '/admin'
}

export default function App() {
  const { user, authReady } = useSupportFlow()
  const [path, setPath] = useState(() => normalizePath(window.location.pathname))
  const activePath = routeForSession(path, user)

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
    if (window.location.pathname !== activePath) {
      window.history.replaceState({}, '', activePath)
    }
  }, [activePath, authReady])

  if (!authReady) {
    return (
      <div className="app-loading" role="status">
        <span className="brand-mark large" aria-hidden="true"><span /><span /><span /></span>
        <p>Preparing your support workspace…</p>
      </div>
    )
  }

  if (user) {
    if (activePath === '/admin' && ADMIN_ROLES.includes(user.role)) {
      return <AdminPage onNavigate={navigate} />
    }
    return <Main onNavigate={navigate} />
  }

  const adminLoginView = (
    activePath === '/admin' || activePath === '/admin/login'
  )

  return (
    <div className="public-shell">
      <Header
        publicView
        homePath={adminLoginView ? '/admin/login' : '/login'}
        onNavigate={navigate}
      />
      <main className="auth-main">
        {adminLoginView ? (
          <AdminLogin onNavigate={navigate} />
        ) : activePath === '/signup' ? (
          <SignUp onNavigate={navigate} />
        ) : (
          <Login onNavigate={navigate} />
        )}
      </main>
      <Footer />
    </div>
  )
}
