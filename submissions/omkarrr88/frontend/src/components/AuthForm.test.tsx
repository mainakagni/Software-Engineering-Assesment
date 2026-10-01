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

  it('shows the password on request', async () => {
    render(<AuthForm notice={null} onAuthenticated={vi.fn<(user: User) => void>()} />)
    const password = screen.getByLabelText('Password')

    expect(password).toHaveAttribute('type', 'password')
    await userEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(password).toHaveAttribute('type', 'text')
    await userEvent.click(screen.getByRole('button', { name: 'Hide password' }))
    expect(password).toHaveAttribute('type', 'password')
  })

  it('stays focusable while it logs in', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(() => new Promise<Response>(() => {})))
    render(<AuthForm notice={null} onAuthenticated={vi.fn<(user: User) => void>()} />)

    await userEvent.type(screen.getByLabelText('Email'), 'a@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'a long password')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    const busy = screen.getByRole('button', { name: 'Logging in…' })
    expect(busy).toHaveAttribute('aria-disabled', 'true')
    expect(busy).toHaveFocus()
  })

  it('leaves browser shortcuts such as Alt+Left alone', async () => {
    render(<AuthForm notice={null} onAuthenticated={vi.fn<(user: User) => void>()} />)

    screen.getByRole('tab', { name: 'Log in' }).focus()
    await userEvent.keyboard('{Alt>}{ArrowRight}{/Alt}')

    expect(screen.getByRole('tab', { name: 'Log in' })).toHaveAttribute('aria-selected', 'true')
  })

  it('moves between the tabs with the arrow keys', async () => {
    render(<AuthForm notice={null} onAuthenticated={vi.fn<(user: User) => void>()} />)

    screen.getByRole('tab', { name: 'Log in' }).focus()
    await userEvent.keyboard('{ArrowRight}')

    const signUp = screen.getByRole('tab', { name: 'Sign up' })
    expect(signUp).toHaveFocus()
    expect(signUp).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('heading', { name: 'Create your account' })).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toHaveAccessibleDescription('At least 8 characters.')
    expect(screen.getByRole('tabpanel')).toHaveAccessibleName('Sign up')

    await userEvent.keyboard('{Home}')
    expect(screen.getByRole('tab', { name: 'Log in' })).toHaveFocus()
    expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeInTheDocument()
  })
})
