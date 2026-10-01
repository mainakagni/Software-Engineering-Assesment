import { LockKeyhole } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'

import { api, errorMessage } from '../api/client'
import type { User } from '../api/types'
import { AuthShowcase } from './AuthShowcase'
import { AuthTabs, type Mode } from './AuthTabs'
import { Brand } from './Brand'
import { BusyButton } from './BusyButton'
import { Callout } from './Callout'
import { PasswordField } from './PasswordField'

const COPY = {
  login: {
    heading: 'Welcome back',
    lead: 'Log in to ask questions about your documents.',
    submit: 'Log in',
    busy: 'Logging in…',
  },
  signup: {
    heading: 'Create your account',
    lead: 'All it takes is an email address and a password.',
    submit: 'Create account',
    busy: 'Creating your account…',
  },
} as const

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
  const emailId = useId()

  function switchTo(next: Mode) {
    setMode(next)
    setError(null)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
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

  const copy = COPY[mode]
  return (
    <div className="auth">
      <AuthShowcase />
      <main className="auth-main">
        <div className="auth-panel">
          <div className="auth-panel-brand">
            <Brand />
          </div>
          <div className="auth-heading">
            <h1 className="serif">{copy.heading}</h1>
            <p>{copy.lead}</p>
          </div>

          <AuthTabs mode={mode} onChange={switchTo}>
            {notice && <Callout tone="info">{notice}</Callout>}
            <form onSubmit={submit} className="auth-form">
              <div className="field">
                <label className="field-label" htmlFor={emailId}>
                  Email
                </label>
                <input
                  id={emailId}
                  className="input"
                  type="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </div>
              <PasswordField
                signingUp={mode === 'signup'}
                value={password}
                onChange={setPassword}
              />
              {error && (
                <Callout tone="error" announce>
                  {error}
                </Callout>
              )}
              <BusyButton
                type="submit"
                className="button primary block"
                busy={busy}
                busyText={copy.busy}
              >
                {copy.submit}
              </BusyButton>
            </form>
          </AuthTabs>

          <p className="auth-foot">
            <LockKeyhole size={14} className="icon" />
            Your documents stay private to your account.
          </p>
        </div>
      </main>
    </div>
  )
}
