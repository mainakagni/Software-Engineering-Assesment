import { BookOpen, LogOut } from 'lucide-react'

import { Brand } from './Brand'

interface Props {
  email: string
  onLogOut: () => void
}

export function Header({ email, onLogOut }: Props) {
  return (
    <header className="app-header">
      <Brand />
      <nav className="header-nav" aria-label="Account">
        <a
          className="header-link"
          href="/docs"
          target="_blank"
          rel="noreferrer"
          aria-label="API docs (opens in a new tab)"
        >
          <BookOpen size={16} />
          <span className="header-link-text">API docs</span>
        </a>
        <span className="account">
          <span className="avatar" aria-hidden="true">
            {email.charAt(0)}
          </span>
          <span className="account-email" title={email}>
            {email}
          </span>
        </span>
        <button
          type="button"
          className="button ghost small"
          aria-label="Log out"
          onClick={onLogOut}
        >
          <LogOut size={16} />
          <span className="header-link-text">Log out</span>
        </button>
      </nav>
    </header>
  )
}
