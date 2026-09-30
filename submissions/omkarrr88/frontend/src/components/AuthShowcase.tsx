import { FileText, SearchX, TextQuote } from 'lucide-react'

import { Brand } from './Brand'

const POINTS = [
  { Icon: FileText, text: 'Upload PDFs, plain text and Markdown files.' },
  { Icon: TextQuote, text: 'Every answer quotes the passage it comes from.' },
  {
    Icon: SearchX,
    text: 'When your files do not have the answer, it says so instead of guessing.',
  },
]

/** The left half of the sign-in page on wide screens: what DocuMind does, and an example. */
export function AuthShowcase() {
  return (
    <aside className="auth-aside" aria-label="About DocuMind">
      <Brand />
      <div className="auth-story">
        <div className="auth-pitch">
          <h2 className="serif">Answers you can check against the source.</h2>
          <ul className="auth-points">
            {POINTS.map(({ Icon, text }) => (
              <li key={text}>
                <Icon size={18} className="icon" />
                {text}
              </li>
            ))}
          </ul>
        </div>
        <figure className="sample" aria-label="An example answer">
          <span className="sample-label">Example</span>
          <p className="sample-question serif">
            How far ahead do international flights have to be booked?
          </p>
          <p className="sample-answer">At least 14 business days before the trip.</p>
          <div className="sample-source">
            <span className="sample-source-head">
              <span className="citation-index">1</span>
              <strong>travel-policy.pdf</strong>
              <span>p. 4</span>
            </span>
            <blockquote>
              International flights must be booked <mark>at least 14 business days</mark> in
              advance.
            </blockquote>
          </div>
        </figure>
      </div>
    </aside>
  )
}
