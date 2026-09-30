import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react'

export type Mode = 'login' | 'signup'

const TABS: { mode: Mode; label: string }[] = [
  { mode: 'login', label: 'Log in' },
  { mode: 'signup', label: 'Sign up' },
]

// Arrow keys switch between the two tabs, and Home and End go to the first and the last.
const KEY_TARGETS: Record<string, (current: Mode) => Mode> = {
  ArrowLeft: (current) => (current === 'login' ? 'signup' : 'login'),
  ArrowRight: (current) => (current === 'login' ? 'signup' : 'login'),
  Home: () => 'login',
  End: () => 'signup',
}

interface Props {
  mode: Mode
  onChange: (mode: Mode) => void
  /** The content of the panel the tabs control. */
  children: ReactNode
}

/** The Log in and Sign up tabs, and the panel they switch. */
export function AuthTabs({ mode, onChange, children }: Props) {
  const tabs = useRef<Partial<Record<Mode, HTMLButtonElement | null>>>({})
  const baseId = useId()
  const panelId = `${baseId}-panel`
  const tabId = (tab: Mode) => `${baseId}-${tab}`

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    const target = KEY_TARGETS[event.key]
    if (!target) return
    event.preventDefault()
    const next = target(mode)
    onChange(next)
    tabs.current[next]?.focus()
  }

  return (
    <>
      <div className="segmented" role="tablist" aria-label="Account">
        {TABS.map((tab) => (
          <button
            key={tab.mode}
            ref={(element) => {
              tabs.current[tab.mode] = element
            }}
            type="button"
            role="tab"
            id={tabId(tab.mode)}
            aria-selected={mode === tab.mode}
            aria-controls={panelId}
            tabIndex={mode === tab.mode ? 0 : -1}
            onClick={() => onChange(tab.mode)}
            onKeyDown={onKeyDown}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div id={panelId} className="auth-tabpanel" role="tabpanel" aria-labelledby={tabId(mode)}>
        {children}
      </div>
    </>
  )
}
