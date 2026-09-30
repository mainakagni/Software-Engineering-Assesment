import type { Answer, AuthResult, DocumentItem, FieldError, User } from './types'

const TOKEN_KEY = 'documind.token'

interface Envelope<T> {
  success: boolean
  data: T | null
  error: {
    code: string
    message: string
    request_id: string | null
    details: FieldError[] | null
  } | null
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string | null
  readonly details: FieldError[]
  readonly retryAfterSeconds: number | null

  constructor(init: {
    status: number
    code: string
    message: string
    requestId?: string | null
    details?: FieldError[]
    retryAfterSeconds?: number | null
  }) {
    super(init.message)
    this.name = 'ApiError'
    this.status = init.status
    this.code = init.code
    this.requestId = init.requestId ?? null
    this.details = init.details ?? []
    this.retryAfterSeconds = init.retryAfterSeconds ?? null
  }
}

/** The access token. Kept in memory as well, so the app still works where storage is blocked. */
let memoryToken: string | null = null

export const tokenStore = {
  get(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY) ?? memoryToken
    } catch {
      return memoryToken
    }
  },
  set(token: string): void {
    memoryToken = token
    try {
      localStorage.setItem(TOKEN_KEY, token)
    } catch {
      // Storage is blocked (private mode, disabled cookies): the session lasts until reload.
    }
  },
  clear(): void {
    memoryToken = null
    try {
      localStorage.removeItem(TOKEN_KEY)
    } catch {
      // Nothing was stored.
    }
  },
}

let onSessionExpired: (() => void) | null = null

/** Called when a request made with a token gets 401: the token expired or the account is gone. */
export function setSessionExpiredHandler(handler: (() => void) | null): void {
  onSessionExpired = handler
}

function parseRetryAfter(value: string | null): number | null {
  if (!value) return null
  const seconds = Number.parseInt(value, 10)
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null
}

async function readEnvelope<T>(response: Response): Promise<Envelope<T> | null> {
  if (!response.headers.get('Content-Type')?.includes('application/json')) return null
  try {
    return (await response.json()) as Envelope<T>
  } catch {
    return null
  }
}

async function request<T>(
  path: string,
  { json, ...init }: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const headers = new Headers(init.headers)
  const token = tokenStore.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let body = init.body
  if (json !== undefined) {
    headers.set('Content-Type', 'application/json')
    body = JSON.stringify(json)
  }
  // For FormData bodies no Content-Type is set: the browser adds it with the multipart boundary.

  let response: Response
  try {
    response = await fetch(`/api${path}`, { ...init, headers, body })
  } catch {
    throw new ApiError({
      status: 0,
      code: 'network_error',
      message: 'Could not reach the server. Check your connection and try again.',
    })
  }
  if (response.status === 204) return undefined as T

  const envelope = await readEnvelope<T>(response)
  if (!response.ok || !envelope?.success) {
    if (response.status === 401 && token) {
      tokenStore.clear()
      onSessionExpired?.()
    }
    const error = envelope?.error
    throw new ApiError({
      status: response.status,
      code: error?.code ?? 'http_error',
      message: error?.message ?? `The request failed (HTTP ${response.status}).`,
      requestId: error?.request_id ?? response.headers.get('X-Request-ID'),
      details: error?.details ?? [],
      retryAfterSeconds: parseRetryAfter(response.headers.get('Retry-After')),
    })
  }
  return envelope.data as T
}

async function authenticate(path: string, email: string, password: string): Promise<User> {
  const result = await request<AuthResult>(path, { method: 'POST', json: { email, password } })
  tokenStore.set(result.access_token)
  return result.user
}

export const api = {
  signup: (email: string, password: string) => authenticate('/auth/signup', email, password),
  login: (email: string, password: string) => authenticate('/auth/login', email, password),
  me: () => request<User>('/auth/me'),

  // The API caps an account at 20 documents, so one page of 100 holds them all.
  listDocuments: () => request<DocumentItem[]>('/documents?limit=100'),
  uploadDocument: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<DocumentItem>('/documents', { method: 'POST', body: form })
  },
  deleteDocument: (id: string) =>
    request<void>(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  ask: (question: string, documentIds: string[] | null) =>
    request<Answer>('/questions', {
      method: 'POST',
      json: { question, document_ids: documentIds },
    }),
  listQuestions: (limit = 20) => request<Answer[]>(`/questions?limit=${limit}`),
}

/** A message to show for any error thrown by the api functions. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const [first] = error.details
    if (error.code === 'validation_error' && first) return first.message
    return error.message
  }
  return 'Something went wrong. Please try again.'
}
