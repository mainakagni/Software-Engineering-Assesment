import { useState, type FormEvent } from 'react'

import { api, errorMessage } from '../api/client'
import type { User } from '../api/types'

type Mode = 'login' | 'signup'

interface Props {
  notice: string | null
  onAuthenticated: (user: User) => void
}

export function AuthForm({ notice, onAuthenticated }: Props) {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function switchTo(next: Mode) {
    setMode(next)
    setError(null)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const authenticate = mode === 'login' ? api.login : api.signup
      onAuthenticated(await authenticate(email, password))
    } catch (caught) {
      setError(errorMessage(caught))
      setBusy(false)
    }
  }

  const signingUp = mode === 'signup'
  return (
    <main className="auth">
      <div className="auth-card">
        <h1 className="brand">DocuMind</h1>
        <p className="tagline">Ask questions about your documents. Every answer cites its sources.</p>

        <div className="tabs" role="tablist" aria-label="Account">
          <button
            type="button"
            role="tab"
            id="tab-login"
            aria-selected={!signingUp}
            aria-controls="auth-form"
            onClick={() => switchTo('login')}
          >
            Log in
          </button>
          <button
            type="button"
            role="tab"
            id="tab-signup"
            aria-selected={signingUp}
            aria-controls="auth-form"
            onClick={() => switchTo('signup')}
          >
            Sign up
          </button>
        </div>

        {notice && <p className="notice">{notice}</p>}

        <form
          id="auth-form"
          role="tabpanel"
          aria-labelledby={signingUp ? 'tab-signup' : 'tab-login'}
          onSubmit={submit}
          className="stack"
        >
          <label>
            Email
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete={signingUp ? 'new-password' : 'current-password'}
              required
              minLength={signingUp ? 8 : undefined}
              maxLength={128}
              aria-describedby={signingUp ? 'password-hint' : undefined}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {signingUp && (
            <p id="password-hint" className="hint">
              At least 8 characters.
            </p>
          )}
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="primary" disabled={busy}>
            {busy ? 'Please wait...' : signingUp ? 'Create account' : 'Log in'}
          </button>
        </form>
      </div>
    </main>
  )
}
