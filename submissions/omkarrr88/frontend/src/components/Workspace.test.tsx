import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { Answer } from '../api/types'
import { makeAnswer, makeDocument, ok } from '../test/fixtures'
import { Workspace } from './Workspace'

const USER = { id: 'u1', email: 'reader@example.com', created_at: '2026-09-30T10:00:00Z' }
const SEARCHING = 'Searching your documents…'

/** A server with one ready document. Each question waits until the test releases its answer. */
function stubServer(history: Answer[] = []) {
  const releases: (() => void)[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input)
      if (url.startsWith('/api/documents')) return ok([makeDocument()])
      if (url.startsWith('/api/questions') && init?.method === 'POST') {
        await new Promise<void>((resolve) => releases.push(resolve))
        return ok(makeAnswer({ id: `answer-${releases.length}` }))
      }
      return ok(history)
    }),
  )
  return releases
}

function renderWorkspace() {
  render(<Workspace user={USER} onLogOut={vi.fn<() => void>()} />)
  return screen.findByText('travel-policy.md')
}

describe('Workspace', () => {
  it('shows the question while it is answered, then the answer and the history', async () => {
    const releases = stubServer()
    await renderWorkspace()
    const question = makeAnswer().question

    await userEvent.type(screen.getByLabelText('Your question'), `${question}{Enter}`)

    // Shown in the placeholder card, and told to screen readers.
    expect(await screen.findAllByText(SEARCHING)).toHaveLength(2)
    expect(screen.getByRole('heading', { name: question })).toBeInTheDocument()
    await waitFor(() => expect(releases).toHaveLength(1))
    releases[0]?.()

    expect(await screen.findByText('At least 14 business days in advance.')).toBeInTheDocument()
    expect(screen.queryByText(SEARCHING)).not.toBeInTheDocument()
    expect(screen.getByText('The answer is ready.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Recent questions' })).toBeInTheDocument()
  })

  it('announces every answer, even two alike in a row', async () => {
    const releases = stubServer()
    await renderWorkspace()
    const box = screen.getByLabelText('Your question')

    await userEvent.type(box, 'How early must flights be booked?{Enter}')
    await waitFor(() => expect(releases).toHaveLength(1))
    releases[0]?.()
    expect(await screen.findByText('The answer is ready.')).toBeInTheDocument()

    await userEvent.type(box, '{Enter}')
    await waitFor(() => expect(releases).toHaveLength(2))
    expect(screen.queryByText('The answer is ready.')).not.toBeInTheDocument()
    releases[1]?.()
    expect(await screen.findByText('The answer is ready.')).toBeInTheDocument()
    // The same question twice is one entry in the history.
    expect(screen.getAllByRole('button', { name: /international flights/ })).toHaveLength(1)
  })

  it('moves focus to an answer reopened from the history', async () => {
    const earlier = makeAnswer({ id: 'answer-0', question: 'Who approves travel?' })
    stubServer([earlier])
    await renderWorkspace()

    await userEvent.click(await screen.findByRole('button', { name: /Who approves travel/ }))

    const heading = screen.getByRole('heading', { name: 'Who approves travel?' })
    await waitFor(() => expect(heading).toHaveFocus())
  })
})
