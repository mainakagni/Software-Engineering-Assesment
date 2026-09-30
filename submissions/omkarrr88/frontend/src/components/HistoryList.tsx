import { CircleAlert, SearchX, TextQuote } from 'lucide-react'

import type { Answer } from '../api/types'
import { formatAge } from '../lib/format'

interface Props {
  answers: Answer[]
  currentId: string | null
  error: string | null
  onSelect: (answer: Answer) => void
}

export function HistoryList({ answers, currentId, error, onSelect }: Props) {
  if (answers.length === 0 && !error) return null
  return (
    <section className="history" aria-labelledby="history-title">
      <h3 id="history-title" className="section-title">
        Recent questions
      </h3>
      {error && (
        <p className="callout error">
          <CircleAlert size={16} className="icon" />
          <span>{error}</span>
        </p>
      )}
      {answers.length > 0 && (
        <ul className="history-list">
          {answers.map((answer) => (
            <li key={answer.id}>
              <button
                type="button"
                className="history-item"
                aria-current={answer.id === currentId ? 'true' : undefined}
                onClick={() => onSelect(answer)}
              >
                {answer.found ? (
                  <TextQuote size={16} className="icon" />
                ) : (
                  <SearchX size={16} className="icon" />
                )}
                <span className="history-question">{answer.question}</span>
                <span className="history-age">
                  {answer.found ? '' : 'Not found · '}
                  {formatAge(answer.created_at)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
