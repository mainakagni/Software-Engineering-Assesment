import { useEffect, useState } from 'react'

import { api, errorMessage } from '../api/client'
import type { Answer, User } from '../api/types'
import { useDocuments } from '../lib/useDocuments'
import { AnswerView } from './AnswerView'
import { AskPanel } from './AskPanel'
import { DocumentList } from './DocumentList'
import { Header } from './Header'
import { HistoryList } from './HistoryList'
import { UploadZone } from './UploadZone'

const HISTORY_LENGTH = 20

interface Props {
  user: User
  onLogOut: () => void
}

export function Workspace({ user, onLogOut }: Props) {
  const { documents, error, processing, added, removed } = useDocuments()
  const [history, setHistory] = useState<Answer[]>([])
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [current, setCurrent] = useState<Answer | null>(null)

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
    setHistory((previous) =>
      [answer, ...previous.filter((other) => other.id !== answer.id)].slice(0, HISTORY_LENGTH),
    )
  }

  const ready = (documents ?? []).filter((document) => document.status === 'ready')
  return (
    <div className="app">
      <Header email={user.email} onLogOut={onLogOut} />
      <main className="layout">
        <div className="column">
          <UploadZone onUploaded={added} />
          <DocumentList documents={documents} error={error} onDeleted={removed} />
        </div>
        <div className="column">
          <AskPanel
            readyDocuments={ready}
            processing={processing}
            onAnswer={answered}
          />
          {current && <AnswerView answer={current} />}
          <HistoryList
            answers={history}
            currentId={current?.id ?? null}
            error={historyError}
            onSelect={setCurrent}
          />
        </div>
      </main>
    </div>
  )
}
