import { useId } from 'react'

import type { DocumentItem } from '../api/types'

const OPTIONS = [
  { onlySelected: false, label: 'All' },
  { onlySelected: true, label: 'Selected' },
]

interface ScopeSwitchProps {
  onlySelected: boolean
  onChange: (onlySelected: boolean) => void
}

/** Search every ready document, or only the picked ones. */
export function ScopeSwitch({ onlySelected, onChange }: ScopeSwitchProps) {
  const name = useId()
  return (
    <fieldset className="scope">
      <legend className="visually-hidden">Search in</legend>
      <span className="scope-options">
        {OPTIONS.map((option) => (
          <label key={option.label} className="scope-option">
            <input
              type="radio"
              name={name}
              checked={onlySelected === option.onlySelected}
              onChange={() => onChange(option.onlySelected)}
            />
            <span>
              {option.label}
              <span className="scope-extra"> documents</span>
            </span>
          </label>
        ))}
      </span>
    </fieldset>
  )
}

interface DocumentPickerProps {
  documents: DocumentItem[]
  selected: string[]
  onToggle: (id: string) => void
}

export function DocumentPicker({ documents, selected, onToggle }: DocumentPickerProps) {
  return (
    <ul className="picker" aria-label="Documents to search">
      {documents.map((document) => (
        <li key={document.id}>
          <label className="chip" title={document.filename}>
            <input
              type="checkbox"
              checked={selected.includes(document.id)}
              onChange={() => onToggle(document.id)}
            />
            <span>{document.filename}</span>
          </label>
        </li>
      ))}
    </ul>
  )
}
