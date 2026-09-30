import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { Answer } from '../api/types'
import { failure, makeAnswer, makeDocument, ok } from '../test/fixtures'
import { AskPanel } from './AskPanel'

const TRAVEL = makeDocument({ id: 'doc-1', filename: 'travel.md' })
const LEAVE = makeDocument({ id: 'doc-2', filename: 'leave.md' })
const EXPENSES = makeDocument({ id: 'doc-3', filename: 'expenses.md' })

function answerSpy() {
  return vi.fn<(answer: Answer) => void>()
}

describe('AskPanel', () => {
  it('cannot ask before a document is ready', () => {
    const processing = makeDocument({ status: 'processing', chunk_count: null })
    render(<AskPanel documents={[processing]} onAnswer={answerSpy()} />)

    expect(screen.getByText(/still being processed/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled()
  })

  it('says what is missing only once the documents have loaded', () => {
    const { rerender } = render(<AskPanel documents={null} onAnswer={answerSpy()} />)
    expect(screen.queryByText(/Upload a document/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled()

    rerender(<AskPanel documents={[]} onAnswer={answerSpy()} />)
    expect(screen.getByText('Upload a document to start asking questions.')).toBeInTheDocument()

    rerender(<AskPanel documents={[makeDocument({ status: 'failed' })]} onAnswer={answerSpy()} />)
    expect(screen.getByText(/None of your documents could be read/)).toBeInTheDocument()
  })

  it('asks about the picked documents only', async () => {
    const answer = makeAnswer()
    const fetchMock = vi.fn<typeof fetch>(async () => ok(answer))
    vi.stubGlobal('fetch', fetchMock)
    const onAnswer = answerSpy()
    render(<AskPanel documents={[TRAVEL, LEAVE]} onAnswer={onAnswer} />)

    await userEvent.type(screen.getByLabelText('Your question'), 'How early should I book?')
    await userEvent.click(screen.getByLabelText('Selected documents'))
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled() // nothing picked yet
    await userEvent.click(screen.getByLabelText('leave.md'))
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))

    const init = fetchMock.mock.calls[0]?.[1]
    expect(JSON.parse(init?.body as string)).toEqual({
      question: 'How early should I book?',
      document_ids: ['doc-2'],
    })
    expect(onAnswer).toHaveBeenCalledWith(answer)
  })

  it('stops counting a picked document once it is gone', async () => {
    const onAnswer = answerSpy()
    const { rerender } = render(
      <AskPanel documents={[TRAVEL, LEAVE, EXPENSES]} onAnswer={onAnswer} />,
    )

    await userEvent.type(screen.getByLabelText('Your question'), 'How early should I book?')
    await userEvent.click(screen.getByLabelText('Selected documents'))
    await userEvent.click(screen.getByLabelText('leave.md'))
    expect(screen.getByRole('button', { name: 'Ask' })).toBeEnabled()

    rerender(<AskPanel documents={[TRAVEL, EXPENSES]} onAnswer={onAnswer} />)
    expect(screen.queryByLabelText('leave.md')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled()
    expect(screen.getByText('Pick at least one document to search.')).toBeInTheDocument()
  })

  it('asks with Enter and shows errors', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(async () =>
        failure(503, 'llm_unavailable', 'The language model is not responding. Please try again.'),
      ),
    )
    const onAnswer = answerSpy()
    const onAsking = vi.fn<(question: string | null) => void>()
    render(<AskPanel documents={[TRAVEL]} onAnswer={onAnswer} onAsking={onAsking} />)

    await userEvent.type(screen.getByLabelText('Your question'), 'Who approves travel?{Enter}')

    expect(await screen.findByRole('alert')).toHaveTextContent('not responding')
    expect(onAnswer).not.toHaveBeenCalled()
    expect(onAsking.mock.calls).toEqual([['Who approves travel?'], [null]])
  })

  it('stays usable from the keyboard while the question is being answered', async () => {
    const pending: { resolve?: (response: Response) => void } = {}
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(
        () =>
          new Promise<Response>((resolve) => {
            pending.resolve = resolve
          }),
      ),
    )
    render(<AskPanel documents={[TRAVEL]} onAnswer={answerSpy()} />)
    const box = screen.getByLabelText('Your question')
    expect(box).toHaveAccessibleDescription('Enter to ask, Shift+Enter for a new line')

    await userEvent.type(box, 'Who approves travel?{Enter}')
    expect(box).toHaveAttribute('readonly')
    // Busy, not disabled: a focused button keeps its focus.
    const button = screen.getByRole('button', { name: 'Searching…' })
    expect(button).toHaveAttribute('aria-disabled', 'true')
    expect(button).toBeEnabled()

    pending.resolve?.(ok(makeAnswer()))
    await waitFor(() => expect(box).not.toHaveAttribute('readonly'))
    expect(screen.getByRole('button', { name: 'Ask' })).not.toHaveAttribute('aria-disabled')
  })
})
