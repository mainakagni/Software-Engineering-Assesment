import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { User } from '../api/types'
import { failure, ok } from '../test/fixtures'
import { AuthForm } from './AuthForm'

const USER = { id: 'u1', email: 'new@example.com', created_at: '2026-09-30T10:00:00Z' }

describe('AuthForm', () => {
  it('signs up and hands over the new user', async () => {
    const fetchMock = vi.fn<typeof fetch>(async () =>
      ok({ access_token: 't', token_type: 'bearer', expires_in: 3600, user: USER }, 201),
    )
    vi.stubGlobal('fetch', fetchMock)
    const onAuthenticated = vi.fn<(user: User) => void>()
    render(<AuthForm notice={null} onAuthenticated={onAuthenticated} />)

    await userEvent.click(screen.getByRole('tab', { name: 'Sign up' }))
    await userEvent.type(screen.getByLabelText('Email'), 'new@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'a long password')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(onAuthenticated).toHaveBeenCalledWith(USER)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/auth/signup')
  })

  it('shows the error and lets the user try again', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(async () => failure(401, 'unauthorized', 'Incorrect email or password.')),
    )
    const onAuthenticated = vi.fn<(user: User) => void>()
    render(<AuthForm notice="Your session has expired." onAuthenticated={onAuthenticated} />)

    expect(screen.getByText('Your session has expired.')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Email'), 'a@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password.')
    expect(screen.getByRole('button', { name: 'Log in' })).toBeEnabled()
    expect(onAuthenticated).not.toHaveBeenCalled()
  })
})
