import { useEffect, useState } from 'react'
import { Check, X } from 'lucide-react'
import { api, post, setCsrf } from './api'
import { navigate, useRoute } from './hooks'
import { ErrorBanner, Logo, Spinner } from './components/ui'
import { Shell } from './components/Shell'
import { Landing } from './pages/Landing'
import { Auth } from './pages/Auth'
import { Dashboard } from './pages/Dashboard'
import { CategoryStages } from './components/CategoryStages'
import { NewSubmission } from './pages/NewSubmission'
import { Detail } from './pages/Detail'
import type { User } from './types'

export default function App() {
  const route = useRoute()
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)
  const [demo, setDemo] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [toast, setToast] = useState('')
  const bootstrap = async () => {
    setError(null)
    try {
      const config = await api<{ csrf_token: string; demo_enabled: boolean }>('auth/bootstrap/')
      setCsrf(config.csrf_token)
      setDemo(config.demo_enabled)
      const currentUser = await api<User>('auth/me/').catch(() => null)
      setUser(currentUser)
    } catch (error) {
      setError(error)
    } finally {
      setReady(true)
    }
  }
  useEffect(() => {
    void bootstrap()
  }, [])
  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(''), 5500)
    return () => window.clearTimeout(timer)
  }, [toast])
  const publicPage = route === '/' || route.startsWith('/login') || route === '/register'
  useEffect(() => {
    if (ready && !error && !user && !publicPage) navigate('/login')
  }, [ready, error, user, publicPage])
  const logout = async () => {
    try {
      await post('auth/logout/')
      setUser(null)
      navigate('/login')
    } catch (error) {
      setError(error)
    }
  }
  if (!ready && route !== '/')
    return (
      <div className="app-loading">
        <Logo />
        <Spinner />
        <span>Getting things ready…</span>
      </div>
    )
  let page
  if (route === '/') page = <Landing signedIn={!!user} demo={demo} />
  else if (route.startsWith('/login') || route === '/register')
    page = (
      <Auth
        key={route}
        mode={route === '/register' ? 'register' : 'login'}
        demo={demo}
        onLogin={setUser}
      />
    )
  else if (user) {
    const [path, search] = route.split('?')
    const content =
      path === '/new' ? (
        <NewSubmission
          key={route}
          initialType={new URLSearchParams(search).get('type')}
          notify={setToast}
        />
      ) : route.startsWith('/submissions/') ? (
        <Detail key={route} id={route.split('/')[2]} user={user} notify={setToast} />
      ) : route === '/app' ? (
        <CategoryStages />
      ) : route === '/review' && user.can_review ? (
        <Dashboard assigned />
      ) : (
        <div className="empty-state">
          <h1>This page isn’t available.</h1>
          <a className="button primary" href="#/app">
            Back to your workspace
          </a>
        </div>
      )
    page = (
      <Shell user={user} route={route} onLogout={logout}>
        {content}
      </Shell>
    )
  } else
    page = (
      <div className="app-loading">
        <Logo />
        <span>Sign in to open your workspace.</span>
        <a href="#/login">Sign in</a>
      </div>
    )
  return (
    <>
      {error ? (
        <div className="global-error">
          <ErrorBanner error={error} retry={bootstrap} />
        </div>
      ) : null}
      {page}
      {toast && (
        <div className="toast" role="status">
          <span>
            <Check size={16} />
          </span>
          {toast}
          <button aria-label="Dismiss notification" onClick={() => setToast('')}>
            <X size={14} />
          </button>
        </div>
      )}
    </>
  )
}
