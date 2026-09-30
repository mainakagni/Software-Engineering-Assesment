// Shapes of the API's `data` payloads (see /docs for the full schema).

export interface User {
  id: string
  email: string
  created_at: string
}

export interface AuthResult {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: User
}

export type DocumentStatus = 'queued' | 'processing' | 'ready' | 'failed'

export interface DocumentItem {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  status: DocumentStatus
  error: string | null
  page_count: number | null
  chunk_count: number | null
  created_at: string
  updated_at: string
}

export interface Citation {
  source_id: string
  document_id: string
  document_name: string
  page_start: number | null
  page_end: number | null
  section: string | null
  passage: string
  quote: string
  quote_verified: boolean
  score: number
}

export interface Usage {
  model: string | null
  prompt_tokens: number
  output_tokens: number
  thinking_tokens: number
  total_tokens: number
  embedding_tokens: number
  retrieval_ms: number
  generation_ms: number
  latency_ms: number
  estimated_cost_usd: number
}

export interface Answer {
  id: string
  question: string
  answer: string
  found: boolean
  cached: boolean
  document_ids: string[] | null
  citations: Citation[]
  usage: Usage
  created_at: string
}

export interface FieldError {
  field: string
  message: string
}
