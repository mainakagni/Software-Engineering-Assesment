import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { Answer } from '../api/types'
import { makeAnswer } from '../test/fixtures'
import { HistoryList } from './HistoryList'

describe('HistoryList', () => {
  it('lists recent questions and reopens one', async () => {
    const answered = makeAnswer()
    const missing = makeAnswer({
      id: 'answer-2',
      question: 'Who signs off on conference travel?',
      found: false,
      citations: [],
    })
    const onSelect = vi.fn<(answer: Answer) => void>()
    render(
      <HistoryList
        answers={[answered, missing]}
        currentId="answer-1"
        error={null}
        onSelect={onSelect}
      />,
    )

    expect(screen.getByRole('button', { name: /international flights/ })).toHaveAttribute(
      'aria-current',
      'true',
    )
    expect(screen.getByRole('button', { name: /conference travel/ })).toHaveTextContent(
      'Not found',
    )
    await userEvent.click(screen.getByRole('button', { name: /conference travel/ }))
    expect(onSelect).toHaveBeenCalledWith(missing)
  })

  it('renders nothing before the first question', () => {
    const onSelect = vi.fn<(answer: Answer) => void>()
    const { container } = render(
      <HistoryList answers={[]} currentId={null} error={null} onSelect={onSelect} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
