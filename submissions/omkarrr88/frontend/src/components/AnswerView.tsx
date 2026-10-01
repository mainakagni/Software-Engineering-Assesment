import { ChevronRight, CircleAlert, LoaderCircle, SearchX } from 'lucide-react'
import type { Ref } from 'react'

import type { Answer, Citation } from '../api/types'
import { formatCost, formatPages, formatSeconds, plural } from '../lib/format'
import { highlight } from '../lib/highlight'

interface Props {
  answer: Answer
  /** Lets the workspace move focus to the answer when one is reopened from the history. */
  headingRef?: Ref<HTMLHeadingElement>
}

export function AnswerView({ answer, headingRef }: Props) {
  const { usage } = answer
  return (
    <article
      className={answer.found ? 'answer' : 'answer not-found'}
      aria-labelledby="answer-question"
    >
      <h3 id="answer-question" className="answer-question serif" ref={headingRef} tabIndex={-1}>
        {answer.question}
      </h3>

      {answer.found ? (
        <p className="answer-text">{answer.answer}</p>
      ) : (
        <div className="not-found-note">
          <SearchX size={20} className="icon" />
          <div>
            <p className="not-found-title">{answer.answer}</p>
            <p className="field-hint">
              Try asking it another way, or check that the document with the answer is uploaded
              and ready.
            </p>
          </div>
        </div>
      )}

      {answer.citations.length > 0 && (
        <section className="sources" aria-labelledby="sources-title">
          <h4 id="sources-title" className="sources-title">
            Sources
          </h4>
          <ol className="citations">
            {answer.citations.map((citation, index) => (
              <CitationItem
                key={`${citation.source_id}:${citation.quote}`}
                citation={citation}
                number={index + 1}
              />
            ))}
          </ol>
        </section>
      )}

      <footer className="answer-meta">
        {answer.cached && <span className="badge">Cached answer</span>}
        <span className="metric" title="Time to answer">
          {formatSeconds(usage.latency_ms)}
        </span>
        <span className="metric" title="Prompt, output and thinking tokens">
          {plural(usage.total_tokens, 'token')}
        </span>
        <span className="metric" title="Estimated cost at paid-tier prices">
          {formatCost(usage.estimated_cost_usd)}
        </span>
        <span className="metric">{usage.model ?? 'no model call'}</span>
      </footer>
    </article>
  )
}

function CitationItem({ citation, number }: { citation: Citation; number: number }) {
  const pages = formatPages(citation)
  return (
    <li className="citation">
      <div className="citation-head">
        <span className="citation-index" aria-hidden="true">
          {number}
        </span>
        <span className="citation-document">{citation.document_name}</span>
        <span
          className="citation-score"
          title="Cosine similarity between the question and the passage"
        >
          similarity {citation.score.toFixed(2)}
        </span>
        {(pages || citation.section) && (
          <span className="citation-where">
            {pages && <span className="citation-location">{pages}</span>}
            {citation.section && <span className="citation-location">{citation.section}</span>}
          </span>
        )}
      </div>
      <blockquote>{citation.quote}</blockquote>
      {!citation.quote_verified && (
        <p className="citation-warning">
          <CircleAlert size={14} className="icon" />
          This quote does not appear word for word in the passage.
        </p>
      )}
      <details>
        <summary>
          <ChevronRight size={14} className="icon" />
          Show the passage
        </summary>
        <p className="passage">
          {highlight(citation.passage, citation.quote).map((segment, index) =>
            segment.match ? <mark key={index}>{segment.text}</mark> : segment.text,
          )}
        </p>
      </details>
    </li>
  )
}

/**
 * Stands in for the answer while the question is being answered. The workspace tells screen
 * readers, so this card has no live region of its own.
 */
export function PendingAnswer({ question }: { question: string }) {
  return (
    <article className="answer pending" aria-labelledby="pending-question">
      <h3 id="pending-question" className="answer-question serif">
        {question}
      </h3>
      <p className="pending-status">
        <LoaderCircle size={16} className="spin" />
        Searching your documents…
      </p>
      <div className="skeleton-lines" aria-hidden="true">
        <span className="skeleton" />
        <span className="skeleton" />
        <span className="skeleton" />
      </div>
    </article>
  )
}
