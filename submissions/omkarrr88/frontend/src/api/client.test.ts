import { describe, expect, it, vi } from 'vitest'

import { envelope, failure, makeDocument, ok } from '../test/fixtures'
import { ApiError, api, errorMessage, setSessionExpiredHandler, tokenStore } from './client'

function stubFetch(...responses: (Response | Error)[]) {
  const fetchMock = vi.fn<typeof fetch>(async () => {
    const next = responses.shift()
    if (!next) throw new Error('unexpected request')
    if (next instanceof Error) throw next
    return next
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function sent(fetchMock: ReturnType<typeof stubFetch>, call = 0) {
  const [url, init = {}] = fetchMock.mock.calls[call] ?? []
  return { url, init, headers: new Headers(init.headers) }
}

describe('api client', () => {
  it('stores the token after logging in and sends it afterwards', async () => {
    const user = { id: 'u1', email: 'a@example.com', created_at: '2026-09-30T10:00:00Z' }
    const fetchMock = stubFetch(
      ok({ access_token: 'token-1', token_type: 'bearer', expires_in: 3600, user }),
      ok(user),
    )

    expect(await api.login('a@example.com', 'secret-password')).toEqual(user)
    const login = sent(fetchMock)
    expect(login.url).toBe('/api/auth/login')
    expect(login.headers.get('Content-Type')).toBe('application/json')
    expect(JSON.parse(login.init.body as string)).toEqual({
      email: 'a@example.com',
      password: 'secret-password',
    })

    await api.me()
    expect(sent(fetchMock, 1).headers.get('Authorization')).toBe('Bearer token-1')
  })

  it('sends the token with uploads and lets the browser set the multipart header', async () => {
    tokenStore.set('token-2')
    const fetchMock = stubFetch(ok(makeDocument({ status: 'queued' }), 202))

    await api.uploadDocument(new File(['hello'], 'notes.txt'))
    const { url, init, headers } = sent(fetchMock)
    expect(url).toBe('/api/documents')
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    expect(headers.get('Authorization')).toBe('Bearer token-2')
    expect(headers.get('Content-Type')).toBeNull()
  })

  it('turns error envelopes into ApiError', async () => {
    tokenStore.set('token-3')
    stubFetch(
      envelope(
        429,
        {
          success: false,
          data: null,
          error: { code: 'rate_limited', message: 'Too many questions.', request_id: 'r9' },
          meta: null,
        },
        { 'Retry-After': '42' },
      ),
    )

    const error = await api.ask('Anything?', null).catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 429,
      code: 'rate_limited',
      message: 'Too many questions.',
      requestId: 'r9',
      retryAfterSeconds: 42,
    })
  })

  it('ends the session when a request with a token gets 401', async () => {
    tokenStore.set('expired')
    const expired = vi.fn<() => void>()
    setSessionExpiredHandler(expired)
    stubFetch(failure(401, 'unauthorized', 'Your session has expired.'))

    await expect(api.listDocuments()).rejects.toBeInstanceOf(ApiError)
    expect(tokenStore.get()).toBeNull()
    expect(expired).toHaveBeenCalledOnce()
    setSessionExpiredHandler(null)
  })

  it('does not treat a failed login as an expired session', async () => {
    const expired = vi.fn<() => void>()
    setSessionExpiredHandler(expired)
    stubFetch(failure(401, 'unauthorized', 'Incorrect email or password.'))

    await expect(api.login('a@example.com', 'wrong-password')).rejects.toThrow(
      'Incorrect email or password.',
    )
    expect(expired).not.toHaveBeenCalled()
    setSessionExpiredHandler(null)
  })

  it('reports network failures and non-JSON errors', async () => {
    stubFetch(new TypeError('Failed to fetch'), new Response('Bad gateway', { status: 502 }))

    await expect(api.me()).rejects.toMatchObject({ status: 0, code: 'network_error' })
    await expect(api.me()).rejects.toMatchObject({ status: 502, code: 'http_error' })
  })

  it('returns nothing for 204 responses', async () => {
    tokenStore.set('token-4')
    const fetchMock = stubFetch(new Response(null, { status: 204 }))

    await expect(api.deleteDocument('a/b')).resolves.toBeUndefined()
    expect(sent(fetchMock).url).toBe('/api/documents/a%2Fb')
  })
})

describe('errorMessage', () => {
  it('prefers the first field error of a validation failure', () => {
    const error = new ApiError({
      status: 422,
      code: 'validation_error',
      message: 'Some fields are missing or invalid.',
      details: [{ field: 'password', message: 'String should have at least 8 characters' }],
    })
    expect(errorMessage(error)).toBe('String should have at least 8 characters')
  })

  it('has a fallback for unexpected errors', () => {
    expect(errorMessage(new Error('boom'))).toBe('Something went wrong. Please try again.')
  })
})
