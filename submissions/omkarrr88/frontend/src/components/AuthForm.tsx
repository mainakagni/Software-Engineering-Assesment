import { CircleAlert, Eye, EyeOff, Info, LoaderCircle, LockKeyhole } from 'lucide-react'
import { useId, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'

import { api, errorMessage } from '../api/client'
import type { User } from '../api/types'
import { AuthShowcase } from './AuthShowcase'
import { Brand } from './Brand'

type Mode = 'login' | 'signup'

const COPY = {
  login: {
    tab: 'Log in',
    heading: 'Welcome back',
    lead: 'Log in to ask questions about your documents.',
    submit: 'Log in',
    busy: 'Logging in…',
  },
  signup: {
    tab: 'Sign up',
    heading: 'Create your account',
    lead: 'All it takes is an email address and a password.',
    submit: 'Create account',
    busy: 'Creating your account…',
  },
} as const

const MODES: Mode[] = ['login', 'signup']

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
  const tabs = useRef<Partial<Record<Mode, HTMLButtonElement | null>>>({})
  const emailId = useId()

  function switchTo(next: Mode) {
    setMode(next)
    setError(null)
  }

  // Arrow keys move between the two tabs, as in any tab list.
  function onTabKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    const next = mode === 'login' ? 'signup' : 'login'
    switchTo(next)
    tabs.current[next]?.focus()
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

          <div className="segmented" role="tablist" aria-label="Account">
            {MODES.map((option) => (
              <button
                key={option}
                ref={(element) => {
                  tabs.current[option] = element
                }}
                type="button"
                role="tab"
                id={`tab-${option}`}
                aria-selected={mode === option}
                aria-controls="auth-form"
                tabIndex={mode === option ? 0 : -1}
                onClick={() => switchTo(option)}
                onKeyDown={onTabKeyDown}
              >
                {COPY[option].tab}
              </button>
            ))}
          </div>

          {notice && (
            <p className="callout info">
              <Info size={16} className="icon" />
              <span>{notice}</span>
            </p>
          )}

          <form
            id="auth-form"
            role="tabpanel"
            aria-labelledby={`tab-${mode}`}
            onSubmit={submit}
            className="auth-form"
          >
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
              <p className="callout error" role="alert">
                <CircleAlert size={16} className="icon" />
                <span>{error}</span>
              </p>
            )}
            <button
              type="submit"
              className={busy ? 'button primary block busy' : 'button primary block'}
              disabled={busy}
            >
              {busy && <LoaderCircle size={16} className="spin" />}
              {busy ? copy.busy : copy.submit}
            </button>
          </form>

          <p className="auth-foot">
            <LockKeyhole size={14} className="icon" />
            Your documents stay private to your account.
          </p>
        </div>
      </main>
    </div>
  )
}

interface PasswordFieldProps {
  signingUp: boolean
  value: string
  onChange: (value: string) => void
}

function PasswordField({ signingUp, value, onChange }: PasswordFieldProps) {
  const [visible, setVisible] = useState(false)
  const id = useId()
  const hintId = useId()
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        Password
      </label>
      <div className="input-wrap">
        <input
          id={id}
          className="input"
          type={visible ? 'text' : 'password'}
          autoComplete={signingUp ? 'new-password' : 'current-password'}
          required
          minLength={signingUp ? 8 : undefined}
          maxLength={128}
          aria-describedby={signingUp ? hintId : undefined}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
        <button
          type="button"
          className="icon-button"
          aria-label={visible ? 'Hide password' : 'Show password'}
          onClick={() => setVisible((shown) => !shown)}
        >
          {visible ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      </div>
      {signingUp && (
        <p id={hintId} className="field-hint">
          At least 8 characters.
        </p>
      )}
    </div>
  )
}
