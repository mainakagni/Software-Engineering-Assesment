import type { Answer, Citation } from '../api/types'
import { formatCost, formatPages, formatSeconds } from '../lib/format'
import { highlight } from '../lib/highlight'

export function AnswerView({ answer }: { answer: Answer }) {
  const { usage } = answer
  return (
    <article
      className={answer.found ? 'panel answer' : 'panel answer not-found'}
      aria-labelledby="answer-question"
    >
      <h2 id="answer-question" className="answer-question">
        {answer.question}
      </h2>
      <p className="answer-text">{answer.answer}</p>

      {answer.citations.length > 0 && (
        <section aria-labelledby="sources-title">
          <h3 id="sources-title">Sources</h3>
          <ol className="citations">
            {answer.citations.map((citation) => (
              <CitationItem key={`${citation.source_id}:${citation.quote}`} citation={citation} />
            ))}
          </ol>
        </section>
      )}

      <footer className="usage">
        {answer.cached && <span className="badge">Cached answer</span>}
        <span title="Time to answer">{formatSeconds(usage.latency_ms)}</span>
        <span title="Prompt, output and thinking tokens">
          {usage.total_tokens.toLocaleString()} tokens
        </span>
        <span title="Estimated cost at paid-tier prices">{formatCost(usage.estimated_cost_usd)}</span>
        {usage.model && <span>{usage.model}</span>}
      </footer>
    </article>
  )
}

function CitationItem({ citation }: { citation: Citation }) {
  const pages = formatPages(citation)
  return (
    <li className="citation">
      <div className="citation-source">
        <strong>{citation.document_name}</strong>
        {pages && <span>{pages}</span>}
        {citation.section && <span>{citation.section}</span>}
        <span title="Cosine similarity between the question and the passage">
          similarity {citation.score.toFixed(2)}
        </span>
      </div>
      <blockquote>{citation.quote}</blockquote>
      {!citation.quote_verified && (
        <p className="warning">This quote does not appear word for word in the passage.</p>
      )}
      <details>
        <summary>Show the passage</summary>
        <p className="passage">
          {highlight(citation.passage, citation.quote).map((segment, index) =>
            segment.match ? <mark key={index}>{segment.text}</mark> : segment.text,
          )}
        </p>
      </details>
    </li>
  )
}
