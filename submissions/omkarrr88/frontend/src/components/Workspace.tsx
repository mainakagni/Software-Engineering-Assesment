import { useEffect, useRef, useState } from 'react'

import { api, errorMessage } from '../api/client'
import type { Answer, User } from '../api/types'
import { useDocuments } from '../lib/useDocuments'
import { AnswerView, PendingAnswer } from './AnswerView'
import { AskPanel } from './AskPanel'
import { Header } from './Header'
import { HistoryList } from './HistoryList'
import { Library } from './Library'

const HISTORY_LENGTH = 20

interface Props {
  user: User
  onLogOut: () => void
}

export function Workspace({ user, onLogOut }: Props) {
  const { documents, error, added, removed } = useDocuments()
  const [history, setHistory] = useState<Answer[]>([])
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [current, setCurrent] = useState<Answer | null>(null)
  const [pending, setPending] = useState<string | null>(null)
  const [announcement, setAnnouncement] = useState('')
  const answerHeading = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    let active = true
    api
      .listQuestions(HISTORY_LENGTH)
      .then((answers) => {
        if (active) setHistory(answers)
      })
      .catch((caught: unknown) => {
        if (active) setHistoryError(errorMessage(caught))
      })
    return () => {
      active = false
    }
  }, [])

  function answered(answer: Answer) {
    setCurrent(answer)
    setAnnouncement(
      answer.found ? 'The answer is ready.' : 'No answer was found in your documents.',
    )
    setHistory((previous) =>
      [answer, ...previous.filter((other) => other.id !== answer.id)].slice(0, HISTORY_LENGTH),
    )
  }

  function reopen(answer: Answer) {
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
          <AskPanel documents={documents} onAnswer={answered} onAsking={setPending} />
          {pending !== null ? (
            <PendingAnswer question={pending} />
          ) : (
            current && <AnswerView answer={current} headingRef={answerHeading} />
          )}
          <HistoryList
            answers={history}
            currentId={current?.id ?? null}
            error={historyError}
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
