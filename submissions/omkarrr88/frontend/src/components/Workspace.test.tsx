import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { makeAnswer, makeDocument, ok } from '../test/fixtures'
import { Workspace } from './Workspace'

const USER = { id: 'u1', email: 'reader@example.com', created_at: '2026-09-30T10:00:00Z' }

describe('Workspace', () => {
  it('shows the question while it is answered, then the answer and the history', async () => {
    const answer = makeAnswer()
    const pending: { release?: () => void } = {}
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(async (input, init) => {
        const url = String(input)
        if (url.startsWith('/api/documents')) return ok([makeDocument()])
        if (url.startsWith('/api/questions') && init?.method === 'POST') {
          await new Promise<void>((resolve) => {
            pending.release = resolve
          })
          return ok(answer)
        }
        return ok([])
      }),
    )
    render(<Workspace user={USER} onLogOut={vi.fn<() => void>()} />)

    await screen.findByText('travel-policy.md')
    await userEvent.type(screen.getByLabelText('Your question'), `${answer.question}{Enter}`)

    expect(await screen.findByText('Searching your documents…')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: answer.question })).toBeInTheDocument()
    await waitFor(() => expect(pending.release).toBeDefined())
    pending.release?.()

    expect(await screen.findByText('At least 14 business days in advance.')).toBeInTheDocument()
    expect(screen.queryByText('Searching your documents…')).not.toBeInTheDocument()
    expect(screen.getByText('The answer is ready.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Recent questions' })).toBeInTheDocument()
  })
})
