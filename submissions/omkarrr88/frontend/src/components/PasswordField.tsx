import { Eye, EyeOff } from 'lucide-react'
import { useId, useState } from 'react'

interface Props {
  signingUp: boolean
  value: string
  onChange: (value: string) => void
}

export function PasswordField({ signingUp, value, onChange }: Props) {
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
