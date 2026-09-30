import type { Answer, Citation, DocumentItem } from '../api/types'

export function makeDocument(overrides: Partial<DocumentItem> = {}): DocumentItem {
  return {
    id: 'doc-1',
    filename: 'travel-policy.md',
    content_type: 'text/markdown',
    size_bytes: 2048,
    status: 'ready',
    error: null,
    page_count: null,
    chunk_count: 4,
    created_at: '2026-09-30T10:00:00Z',
    updated_at: '2026-09-30T10:00:05Z',
    ...overrides,
  }
}

export function makeCitation(overrides: Partial<Citation> = {}): Citation {
  return {
    source_id: 'S1',
    document_id: 'doc-1',
    document_name: 'travel-policy.md',
    page_start: null,
    page_end: null,
    section: 'Travel > Flights',
    passage:
      'Domestic flights should be booked at least 7 business days in advance. ' +
      'International flights must be booked at least 14 business days in advance.',
    quote: 'International flights must be booked at least 14 business days in advance',
    quote_verified: true,
    score: 0.83,
    ...overrides,
  }
}

export function makeAnswer(overrides: Partial<Answer> = {}): Answer {
  return {
    id: 'answer-1',
    question: 'How early must international flights be booked?',
    answer: 'At least 14 business days in advance.',
    found: true,
    cached: false,
    document_ids: null,
    citations: [makeCitation()],
    usage: {
      model: 'gemini-test',
      prompt_tokens: 900,
      output_tokens: 60,
      thinking_tokens: 40,
      total_tokens: 1000,
      embedding_tokens: 12,
      retrieval_ms: 80,
      generation_ms: 1100,
      latency_ms: 1250,
      estimated_cost_usd: 0.00052,
    },
    created_at: '2026-09-30T10:01:00Z',
    ...overrides,
  }
}

/** A fetch Response carrying the API's JSON envelope. */
export function envelope(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

export function ok<T>(data: T, status = 200): Response {
  return envelope(status, { success: true, data, error: null, meta: null })
}

export function failure(status: number, code: string, message: string, extra: object = {}) {
  return envelope(status, {
    success: false,
    data: null,
    error: { code, message, request_id: 'req-1', details: null, ...extra },
    meta: null,
  })
}
