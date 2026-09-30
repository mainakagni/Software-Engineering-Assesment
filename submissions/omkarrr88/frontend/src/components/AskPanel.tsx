import { useState, type FormEvent, type KeyboardEvent } from 'react'

import { api, errorMessage } from '../api/client'
import type { Answer, DocumentItem } from '../api/types'

const MAX_QUESTION_LENGTH = 1000

interface Props {
  readyDocuments: DocumentItem[]
  processing: boolean
  onAnswer: (answer: Answer) => void
}

export function AskPanel({ readyDocuments, processing, onAnswer }: Props) {
  const [question, setQuestion] = useState('')
  const [onlySelected, setOnlySelected] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // A selected document may have been deleted since; only ready ones can be searched.
  const selectedReady = selected.filter((id) => readyDocuments.some((d) => d.id === id))
  const trimmed = question.trim()
  const canAsk =
    !asking &&
    trimmed.length >= 3 &&
    readyDocuments.length > 0 &&
    (!onlySelected || selectedReady.length > 0)

  async function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault()
    if (!canAsk) return
    setAsking(true)
    setError(null)
    try {
      onAnswer(await api.ask(trimmed, onlySelected ? selectedReady : null))
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setAsking(false)
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

  return (
    <section className="panel" aria-labelledby="ask-title">
      <h2 id="ask-title">Ask a question</h2>
      <form onSubmit={submit} className="stack">
        <textarea
          aria-label="Your question"
          placeholder="For example: How many days in advance should flights be booked?"
          rows={3}
          maxLength={MAX_QUESTION_LENGTH}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={onKeyDown}
        />

        {readyDocuments.length === 0 && (
          <p className="muted">
            {processing
              ? 'Your documents are still being processed. You can ask once one is ready.'
              : 'Upload a document to start asking questions.'}
          </p>
        )}

        {readyDocuments.length > 1 && (
          <fieldset className="scope">
            <legend>Search in</legend>
            <label className="inline">
              <input
                type="radio"
                name="scope"
                checked={!onlySelected}
                onChange={() => setOnlySelected(false)}
              />
              All ready documents
            </label>
            <label className="inline">
              <input
                type="radio"
                name="scope"
                checked={onlySelected}
                onChange={() => setOnlySelected(true)}
              />
              Only the ones I pick
            </label>
            {onlySelected && (
              <ul className="picker">
                {readyDocuments.map((document) => (
                  <li key={document.id}>
                    <label className="inline">
                      <input
                        type="checkbox"
                        checked={selected.includes(document.id)}
                        onChange={() => toggle(document.id)}
                      />
                      {document.filename}
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </fieldset>
        )}

        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="row">
          <button type="submit" className="primary" disabled={!canAsk}>
            {asking ? 'Searching your documents...' : 'Ask'}
          </button>
          <span className="hint">Enter to ask, Shift+Enter for a new line</span>
        </div>
      </form>
    </section>
  )
}
