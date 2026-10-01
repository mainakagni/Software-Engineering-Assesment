import { LoaderCircle } from 'lucide-react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'

interface Props extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children' | 'className'> {
  className: string
  busy: boolean
  busyText: string
  children: ReactNode
}

/**
 * A button that shows its action is running. While busy it is aria-disabled rather than disabled,
 * so it keeps keyboard focus; its handler has to ignore clicks until the action is done.
 */
export function BusyButton({ className, busy, busyText, children, disabled, ...props }: Props) {
  return (
    <button
      {...props}
      className={busy ? `${className} busy` : className}
      disabled={!busy && disabled}
      aria-disabled={busy || undefined}
    >
      {busy && <LoaderCircle size={16} className="spin" />}
      {busy ? busyText : children}
    </button>
  )
}
