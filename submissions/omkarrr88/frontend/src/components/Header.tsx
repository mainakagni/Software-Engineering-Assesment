interface Props {
  email: string
  onLogOut: () => void
}

export function Header({ email, onLogOut }: Props) {
  return (
    <header className="header">
      <span className="brand">DocuMind</span>
      <nav className="header-actions" aria-label="Account">
        <span className="email" title={email}>
          {email}
        </span>
        <a href="/docs" target="_blank" rel="noreferrer">
          API docs
        </a>
        <button type="button" onClick={onLogOut}>
          Log out
        </button>
      </nav>
    </header>
  )
}
