import { CircleAlert, Info } from 'lucide-react'
import type { ReactNode } from 'react'

interface Props {
  tone: 'info' | 'error'
  /** Read it out as it appears. For errors that follow something the user just did. */
  announce?: boolean
  children: ReactNode
}

export function Callout({ tone, announce = false, children }: Props) {
  const Icon = tone === 'error' ? CircleAlert : Info
  return (
    <div className={`callout ${tone}`} role={announce ? 'alert' : undefined}>
      <Icon size={16} className="icon" />
      <div className="callout-body">{children}</div>
    </div>
  )
}
