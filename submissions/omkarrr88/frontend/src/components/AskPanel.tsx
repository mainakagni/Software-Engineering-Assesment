import { CircleAlert, LoaderCircle } from 'lucide-react'
import { useId, useState, type FormEvent, type KeyboardEvent } from 'react'

import { api, errorMessage } from '../api/client'
import type { Answer, DocumentItem } from '../api/types'

const MAX_QUESTION_LENGTH = 1000

interface Props {
  readyDocuments: DocumentItem[]
  processing: boolean
  onAnswer: (answer: Answer) => void
  /** Called with the question when asking starts, and with null when it ends either way. */
  onAsking?: (question: string | null) => void
}

export function AskPanel({ readyDocuments, processing, onAnswer, onAsking }: Props) {
  const [question, setQuestion] = useState('')
  const [onlySelected, setOnlySelected] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const hintId = useId()

  // Picking only makes sense with two or more ready documents. A picked document may have been
  // deleted since; only ready ones can be searched.
  const choosing = readyDocuments.length > 1
  const scoped = choosing && onlySelected
  const selectedReady = selected.filter((id) => readyDocuments.some((d) => d.id === id))
  const trimmed = question.trim()
  const canAsk =
    !asking &&
    trimmed.length >= 3 &&
    readyDocuments.length > 0 &&
    (!scoped || selectedReady.length > 0)

  async function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault()
    if (!canAsk) return
    setAsking(true)
    setError(null)
    onAsking?.(trimmed)
    try {
      onAnswer(await api.ask(trimmed, scoped ? selectedReady : null))
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

  function note(): string | null {
    if (readyDocuments.length === 0) {
      return processing
        ? 'Your documents are still being processed. You can ask once one is ready.'
        : 'Upload a document to start asking questions.'
    }
    return scoped && selectedReady.length === 0 ? 'Pick at least one document to search.' : null
  }

  const composerNote = note()
  return (
    <section className="ask" aria-labelledby="ask-title">
      <div className="intro">
        <h2 id="ask-title" className="serif">
          Ask your documents
        </h2>
        <p>Answers come only from your files, and each one shows the passage it was taken from.</p>
      </div>

      <form onSubmit={submit} className="composer">
        <textarea
          aria-label="Your question"
          aria-describedby={hintId}
          placeholder="Ask a question about your documents…"
          rows={3}
          maxLength={MAX_QUESTION_LENGTH}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={onKeyDown}
          // Read-only rather than disabled while asking, so it keeps focus.
          readOnly={asking}
        />

        {scoped && (
          <ul className="picker" aria-label="Documents to search">
            {readyDocuments.map((document) => (
              <li key={document.id}>
                <label className="chip">
                  <input
                    type="checkbox"
                    checked={selected.includes(document.id)}
                    onChange={() => toggle(document.id)}
                  />
                  <span>{document.filename}</span>
                </label>
              </li>
            ))}
          </ul>
        )}

        <div className="composer-bar">
          {choosing && (
            <fieldset className="scope">
              <legend className="visually-hidden">Search in</legend>
              <span className="scope-options">
                <label className="scope-option">
                  <input
                    type="radio"
                    name="scope"
                    checked={!onlySelected}
                    onChange={() => setOnlySelected(false)}
                  />
                  <span>
                    All<span className="scope-extra"> documents</span>
                  </span>
                </label>
                <label className="scope-option">
                  <input
                    type="radio"
                    name="scope"
                    checked={onlySelected}
                    onChange={() => setOnlySelected(true)}
                  />
                  <span>
                    Selected<span className="scope-extra"> documents</span>
                  </span>
                </label>
              </span>
            </fieldset>
          )}
          <span className="composer-hint" id={hintId}>
            <kbd>Enter</kbd> to ask, <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line
          </span>
          <button
            type="submit"
            className={asking ? 'button primary busy' : 'button primary'}
            disabled={!canAsk}
          >
            {asking && <LoaderCircle size={16} className="spin" />}
            {asking ? 'Searching…' : 'Ask'}
          </button>
        </div>

        {composerNote && <p className="composer-note">{composerNote}</p>}
      </form>

      {error && (
        <p className="callout error" role="alert">
          <CircleAlert size={16} className="icon" />
          <span>{error}</span>
        </p>
      )}
    </section>
  )
}
