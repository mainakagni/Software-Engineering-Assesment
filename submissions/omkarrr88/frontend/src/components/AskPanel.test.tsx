import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { Answer } from '../api/types'
import { failure, makeAnswer, makeDocument, ok } from '../test/fixtures'
import { AskPanel } from './AskPanel'

const TRAVEL = makeDocument({ id: 'doc-1', filename: 'travel.md' })
const LEAVE = makeDocument({ id: 'doc-2', filename: 'leave.md' })

describe('AskPanel', () => {
  it('cannot ask before a document is ready', () => {
    render(<AskPanel readyDocuments={[]} processing onAnswer={vi.fn<(answer: Answer) => void>()} />)

    expect(screen.getByText(/still being processed/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled()
  })

  it('asks about the picked documents only', async () => {
    const answer = makeAnswer()
    const fetchMock = vi.fn<typeof fetch>(async () => ok(answer))
    vi.stubGlobal('fetch', fetchMock)
    const onAnswer = vi.fn<(answer: Answer) => void>()
    render(<AskPanel readyDocuments={[TRAVEL, LEAVE]} processing={false} onAnswer={onAnswer} />)

    await userEvent.type(screen.getByLabelText('Your question'), 'How early should I book?')
    await userEvent.click(screen.getByLabelText('Only the ones I pick'))
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

  it('asks with Enter and shows errors', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(async () =>
        failure(503, 'llm_unavailable', 'The language model is not responding. Please try again.'),
      ),
    )
    const onAnswer = vi.fn<(answer: Answer) => void>()
    render(<AskPanel readyDocuments={[TRAVEL]} processing={false} onAnswer={onAnswer} />)

    await userEvent.type(screen.getByLabelText('Your question'), 'Who approves travel?{Enter}')

    expect(await screen.findByRole('alert')).toHaveTextContent('not responding')
    expect(onAnswer).not.toHaveBeenCalled()
  })

  it('keeps the question read-only while it is being answered', async () => {
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
    render(
      <AskPanel
        readyDocuments={[TRAVEL]}
        processing={false}
        onAnswer={vi.fn<(answer: Answer) => void>()}
      />,
    )
    const box = screen.getByLabelText('Your question')
    expect(box).toHaveAccessibleDescription('Enter to ask, Shift+Enter for a new line')

    await userEvent.type(box, 'Who approves travel?{Enter}')
    expect(box).toHaveAttribute('readonly')
    expect(screen.getByRole('button', { name: 'Searching your documents...' })).toBeDisabled()

    pending.resolve?.(ok(makeAnswer()))
    await waitFor(() => expect(box).not.toHaveAttribute('readonly'))
  })
})
