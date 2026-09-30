import { useId, useState, type FormEvent, type KeyboardEvent } from 'react'

import { api, errorMessage } from '../api/client'
import type { Answer, DocumentItem } from '../api/types'
import { isProcessing } from '../lib/format'
import { BusyButton } from './BusyButton'
import { Callout } from './Callout'
import { DocumentPicker, ScopeSwitch } from './ScopeSwitch'

const MIN_QUESTION_LENGTH = 3
const MAX_QUESTION_LENGTH = 1000

interface Props {
  /** All of the user's documents, or null while they are loading. */
  documents: DocumentItem[] | null
  onAnswer: (answer: Answer) => void
  /** Called with the question when asking starts, and with null when it ends either way. */
  onAsking?: (question: string | null) => void
}

export function AskPanel({ documents, onAnswer, onAsking }: Props) {
  const [question, setQuestion] = useState('')
  const [onlySelected, setOnlySelected] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const hintId = useId()

  const ready = (documents ?? []).filter((document) => document.status === 'ready')
  // Picking only makes sense with two or more ready documents. A picked document may have been
  // deleted since; only ready ones can be searched.
  const choosing = ready.length > 1
  const scoped = choosing && onlySelected
  const picked = selected.filter((id) => ready.some((document) => document.id === id))
  const trimmed = question.trim()
  const canAsk =
    trimmed.length >= MIN_QUESTION_LENGTH && ready.length > 0 && (!scoped || picked.length > 0)

  async function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault()
    if (asking || !canAsk) return
    setAsking(true)
    setError(null)
    onAsking?.(trimmed)
    try {
      onAnswer(await api.ask(trimmed, scoped ? picked : null))
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setAsking(false)
      onAsking?.(null)
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter asks, Shift+Enter starts a new line.
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      void submit()
    }
  }

  function toggle(id: string) {
    setSelected((current) =>
      current.includes(id) ? current.filter((other) => other !== id) : [...current, id],
    )
  }

  const note = composerNote(documents, ready.length, scoped && picked.length === 0)
  return (
    <section className="ask" aria-labelledby="ask-title">
      <div className="intro">
        <h2 id="ask-title" className="serif">
          Ask a question
        </h2>
        <p>Answers come only from your files, and each one shows the passage it was taken from.</p>
      </div>

      <form onSubmit={submit} className="composer">
        <textarea
          aria-label="Your question"
          aria-describedby={hintId}
          placeholder="Type your question…"
          rows={3}
          maxLength={MAX_QUESTION_LENGTH}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={onKeyDown}
          // Read-only rather than disabled while asking, so it keeps focus.
          readOnly={asking}
        />
        {scoped && <DocumentPicker documents={ready} selected={selected} onToggle={toggle} />}
        <div className="composer-bar">
          {choosing && <ScopeSwitch onlySelected={onlySelected} onChange={setOnlySelected} />}
          <span className="composer-hint" id={hintId}>
            <kbd>Enter</kbd> to ask, <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line
          </span>
          <BusyButton
            type="submit"
            className="button primary"
            busy={asking}
            busyText="Searching…"
            disabled={!canAsk}
          >
            Ask
          </BusyButton>
        </div>
        {note && <p className="composer-note">{note}</p>}
      </form>

      {error && (
        <Callout tone="error" announce>
          {error}
        </Callout>
      )}
    </section>
  )
}

/** Why the user cannot ask yet, if there is a reason. Nothing is said while documents load. */
function composerNote(
  documents: DocumentItem[] | null,
  readyCount: number,
  nothingPicked: boolean,
): string | null {
  if (documents === null) return null
  if (documents.length === 0) return 'Upload a document to start asking questions.'
  if (readyCount === 0) {
    return documents.some(isProcessing)
      ? 'Your documents are still being processed. You can ask once one is ready.'
      : 'None of your documents could be read. Upload another one to start asking questions.'
  }
  return nothingPicked ? 'Pick at least one document to search.' : null
}
