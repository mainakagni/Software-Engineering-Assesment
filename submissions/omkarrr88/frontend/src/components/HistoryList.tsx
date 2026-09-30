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
    <section className="panel" aria-labelledby="history-title">
      <h2 id="history-title">Recent questions</h2>
      {error && <p className="error">{error}</p>}
      <ul className="history">
        {answers.map((answer) => (
          <li key={answer.id}>
            <button
              type="button"
              aria-current={answer.id === currentId ? 'true' : undefined}
              onClick={() => onSelect(answer)}
            >
              <span className="history-question">{answer.question}</span>
              <span className="history-meta">
                {answer.found ? 'Answered' : 'Not found'} {'·'} {formatAge(answer.created_at)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
