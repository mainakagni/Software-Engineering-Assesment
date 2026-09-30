import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import App from './App'
import { tokenStore } from './api/client'
import { makeDocument, ok } from './test/fixtures'

const USER = { id: 'u1', email: 'reader@example.com', created_at: '2026-09-30T10:00:00Z' }

describe('App', () => {
  it('checks a stored session before showing the workspace', async () => {
    tokenStore.set('token-1')
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(async (input) => {
        const url = String(input)
        if (url === '/api/auth/me') return ok(USER)
        if (url.startsWith('/api/documents')) return ok([makeDocument()])
        return ok([])
      }),
    )
    render(<App />)

    expect(screen.getByRole('status')).toHaveTextContent('Checking your session')
    expect(await screen.findByRole('heading', { name: 'Your documents' })).toBeInTheDocument()
    expect(screen.getByText('reader@example.com')).toBeInTheDocument()
  })

  it('shows the sign-in form with a reason when the session check times out', async () => {
    tokenStore.set('token-1')
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(async () => {
        throw new DOMException('The operation timed out.', 'TimeoutError')
      }),
    )
    render(<App />)

    expect(await screen.findByText(/taking too long to respond/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'DocuMind' })).toBeInTheDocument()
  })
})
