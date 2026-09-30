/** The DocuMind mark: a page with one line highlighted, like a cited passage. */
export function Logo() {
  return (
    <svg className="logo" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="currentColor" />
      <rect className="logo-mark" x="11.5" y="15.5" width="9" height="4" rx="1" />
      <path
        className="logo-page"
        d="M11 7.5h6.5l4.5 4.5v12.5a1 1 0 0 1-1 1H11a1 1 0 0 1-1-1v-16a1 1 0 0 1 1-1Z"
      />
      <path className="logo-line" d="M13 13h4M13 22.5h6" />
    </svg>
  )
}

export function Brand() {
  return (
    <span className="brand">
      <Logo />
      DocuMind
    </span>
  )
}
