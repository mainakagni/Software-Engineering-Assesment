import { useRef, useState } from 'react'

import type { Answer, User } from '../api/types'
import { useDocuments } from '../lib/useDocuments'
import { useHistory } from '../lib/useHistory'
import { AnswerView, PendingAnswer } from './AnswerView'
import { AskPanel } from './AskPanel'
import { Header } from './Header'
import { HistoryList } from './HistoryList'
import { Library } from './Library'

const SEARCHING = 'Searching your documents…'

interface Props {
  user: User
  onLogOut: () => void
}

export function Workspace({ user, onLogOut }: Props) {
  const { documents, error, added, removed } = useDocuments()
  const history = useHistory()
  const [current, setCurrent] = useState<Answer | null>(null)
  const [pending, setPending] = useState<string | null>(null)
  const [announcement, setAnnouncement] = useState('')
  const answerHeading = useRef<HTMLHeadingElement>(null)

  // A live region speaks only when its text changes, so every question starts from "searching",
  // and a question that ends without an answer clears it.
  function asking(question: string | null) {
    setPending(question)
    if (question !== null) setAnnouncement(SEARCHING)
    else setAnnouncement((previous) => (previous === SEARCHING ? '' : previous))
  }

  function answered(answer: Answer) {
    setCurrent(answer)
    setAnnouncement(
      answer.found ? 'The answer is ready.' : 'No answer was found in your documents.',
    )
    history.remember(answer)
  }

  function reopen(answer: Answer) {
    if (pending !== null) return // the new answer is on its way and will take this place
    setCurrent(answer)
    // Focus follows the reopened answer, which also scrolls it into view.
    requestAnimationFrame(() => answerHeading.current?.focus())
  }

  return (
    <div className="app">
      <Header email={user.email} onLogOut={onLogOut} />
      <main className="workspace">
        <h1 className="visually-hidden">DocuMind workspace</h1>
        <Library documents={documents} error={error} onUploaded={added} onDeleted={removed} />
        <div className="stage">
          <AskPanel documents={documents} onAnswer={answered} onAsking={asking} />
          {pending !== null ? (
            <PendingAnswer question={pending} />
          ) : (
            current && <AnswerView answer={current} headingRef={answerHeading} />
          )}
          <HistoryList
            answers={history.answers}
            currentId={current?.id ?? null}
            error={history.error}
            onSelect={reopen}
          />
          <p className="visually-hidden" role="status">
            {announcement}
          </p>
        </div>
      </main>
    </div>
  )
}
