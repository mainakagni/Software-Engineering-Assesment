import { useCallback, useEffect, useState } from 'react'

import { api, errorMessage } from '../api/client'
import type { Answer } from '../api/types'

const HISTORY_LENGTH = 20

/** Newest first, one entry per question: asking a question again replaces its older entry. */
export function latestPerQuestion(answers: Answer[]): Answer[] {
  const seen = new Set<string>()
  return answers.filter((answer) => {
    const key = answer.question.trim().toLowerCase()
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

/** The user's recent questions: loaded once, then kept up to date as new answers arrive. */
export function useHistory() {
  const [answers, setAnswers] = useState<Answer[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    api
      .listQuestions(HISTORY_LENGTH)
      .then((loaded) => {
        if (active) setAnswers(latestPerQuestion(loaded))
      })
      .catch((caught: unknown) => {
        if (active) setError(errorMessage(caught))
      })
    return () => {
      active = false
    }
  }, [])

  const remember = useCallback((answer: Answer) => {
    setAnswers((previous) => latestPerQuestion([answer, ...previous]).slice(0, HISTORY_LENGTH))
  }, [])

  return { answers, error, remember }
}
