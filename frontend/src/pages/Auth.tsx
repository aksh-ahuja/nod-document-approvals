import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowLeft, ArrowRight, Check, LockKeyhole, Mail } from 'lucide-react'
import { ApiError, api, post, setCsrf } from '../api'
import { navigate } from '../hooks'
import { ErrorBanner, Logo, Spinner } from '../components/ui'
import type { User } from '../types'

type AuthResult = { user: User; csrf_token: string }
type Challenge = { challenge_id: string; expires_in: number; resend_after: number }

export function Auth({
  mode,
  demo,
  onLogin,
}: {
  mode: 'login' | 'register'
  demo: boolean
  onLogin: (user: User) => void
}) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [challenge, setChallenge] = useState<Challenge | null>(null)
  const [resendAt, setResendAt] = useState(0)
  const [countdown, setCountdown] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [notice, setNotice] = useState('')
  const fields = error instanceof ApiError ? error.fields : {}
  useEffect(() => {
    const tick = () => setCountdown(Math.max(0, Math.ceil((resendAt - Date.now()) / 1000)))
    tick()
    const timer = window.setInterval(tick, 1000)
    return () => window.clearInterval(timer)
  }, [resendAt])
  const finish = (result: AuthResult) => {
    setCsrf(result.csrf_token)
    onLogin(result.user)
    navigate('/app')
  }
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setNotice('')
    try {
      const bootstrap = await api<{ csrf_token: string }>('auth/bootstrap/')
      setCsrf(bootstrap.csrf_token)
      if (challenge) {
        finish(
          await post<AuthResult>('auth/verify/', { challenge_id: challenge.challenge_id, code }),
        )
      } else if (mode === 'register') {
        const result = await post<Challenge>('auth/register/', { name, email, password })
        setPassword('')
        setChallenge(result)
        setResendAt(Date.now() + result.resend_after * 1000)
      } else finish(await post<AuthResult>('auth/login/', { email, password }))
    } catch (error) {
      setError(error)
    } finally {
      setBusy(false)
    }
  }
  const resend = async () => {
    if (!challenge) return
    setBusy(true)
    setError(null)
    try {
      const result = await post<Challenge>('auth/resend/', { challenge_id: challenge.challenge_id })
      setChallenge(result)
      setCode('')
      setResendAt(Date.now() + result.resend_after * 1000)
      setNotice('A fresh code is on its way. Use the latest email.')
    } catch (error) {
      setError(error)
    } finally {
      setBusy(false)
    }
  }
  return (
    <main className="auth-layout">
      <aside className="auth-brand">
        <Logo inverse />
        <div>
          <span className="eyebrow">DOCUMENT APPROVALS, SIMPLIFIED</span>
          <h1>
            Good work deserves
            <br />
            <em>a clear answer.</em>
          </h1>
          <p>Send it to the right person. Keep the decision.</p>
          <div className="auth-proof">
            <span>
              <Check size={15} /> The right reviewer
            </span>
            <span>
              <Check size={15} /> Every decision recorded
            </span>
          </div>
        </div>
        <span className="auth-footnote">A LITTLE NOD. A BIG NEXT STEP.</span>
      </aside>
      <section className="auth-form-side">
        <a className="back-link" href="#/">
          <ArrowLeft size={16} /> Back to Nod
        </a>
        <div className="auth-form-wrap">
          <div className="auth-icon">
            {challenge ? <Mail size={22} /> : <LockKeyhole size={22} />}
          </div>
          <h2>
            {challenge
              ? 'Check your inbox.'
              : mode === 'register'
                ? 'Create your account'
                : 'Welcome back'}
          </h2>
          <p>
            {challenge ? (
              <>
                We sent a six-digit code to <strong>{email}</strong>.
              </>
            ) : mode === 'register' ? (
              'Start sending documents for review.'
            ) : (
              'Sign in and pick up where you left off.'
            )}
          </p>
          <ErrorBanner error={error} />
          {notice && (
            <p role="status" className="success-notice">
              {notice}
            </p>
          )}
          <form onSubmit={submit}>
            {challenge ? (
              <label>
                Verification code
                <input
                  className="otp-input"
                  autoFocus
                  autoComplete="one-time-code"
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  value={code}
                  onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))}
                  placeholder="000000"
                  required
                />
                <small>Expires in 10 minutes. Check spam if it hasn’t arrived.</small>
              </label>
            ) : (
              <>
                {mode === 'register' && (
                  <label>
                    Full name
                    <input
                      autoComplete="name"
                      value={name}
                      onChange={(event) => setName(event.target.value)}
                      placeholder="Jamie Morgan"
                      maxLength={100}
                      required
                    />
                    {fields.name && <small className="field-error">{fields.name}</small>}
                  </label>
                )}
                <label>
                  Email address
                  <input
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="you@company.com"
                    required
                  />
                  {fields.email && <small className="field-error">{fields.email}</small>}
                </label>
                <label>
                  Password
                  <input
                    type="password"
                    autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder={mode === 'register' ? 'At least 10 characters' : 'Your password'}
                    minLength={mode === 'register' ? 10 : 1}
                    maxLength={128}
                    required
                  />
                  {fields.password && <small className="field-error">{fields.password}</small>}
                </label>
              </>
            )}
            <button className="button primary full" disabled={busy}>
              {busy ? (
                <Spinner />
              ) : (
                <>
                  {challenge
                    ? 'Verify & continue'
                    : mode === 'register'
                      ? 'Create account'
                      : 'Sign in'}{' '}
                  <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>
          {challenge ? (
            <div className="auth-switch">
              <button onClick={resend} disabled={busy || countdown > 0}>
                {countdown ? `Resend code in ${countdown}s` : 'Send a new code'}
              </button>
              <button
                onClick={() => {
                  setChallenge(null)
                  setError(null)
                  setCode('')
                }}
              >
                Use a different email
              </button>
            </div>
          ) : (
            <p className="auth-switch">
              {mode === 'register' ? 'Already have an account?' : 'New to Nod?'}{' '}
              <a href={mode === 'register' ? '#/login' : '#/register'}>
                {mode === 'register' ? 'Sign in' : 'Create an account'} <ArrowRight size={13} />
              </a>
            </p>
          )}
          {demo && mode === 'login' && !challenge && (
            <div className="demo-picker">
              <span className="eyebrow">TAKE A LOOK AROUND</span>
              <p>Choose a demo account, then sign in.</p>
              <div>
                {[
                  ['Jamie', 'Submit & review', 'jamie'],
                  ['Alex', 'Reviewer', 'alex'],
                  ['Sam', 'Reviewer', 'sam'],
                ].map(([name, role, key]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => {
                      setEmail(`${key}@nod.demo`)
                      setPassword('NodDemo!2026')
                      setError(null)
                    }}
                  >
                    <strong>{name}</strong>
                    <span>{role}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
        <span className="auth-bottom">
          <LockKeyhole size={12} /> Your account. Your decisions.
        </span>
      </section>
    </main>
  )
}
