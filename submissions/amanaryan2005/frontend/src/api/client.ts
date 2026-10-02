import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

export const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
})

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Types
export interface User { id: string; email: string; username: string; created_at: string }
export interface TokenResponse { access_token: string; token_type: string; expires_in: number }
export type DocStatus = 'queued' | 'processing' | 'ready' | 'failed'
export interface Document {
  id: string; filename: string; original_filename: string; file_size: number
  mime_type: string; status: DocStatus; error_message?: string; chunk_count?: number
  created_at: string; processed_at?: string
}
export interface Citation { document_name: string; passage: string; page_number?: number; chunk_id: string }
export interface AskResponse {
  question_id: string; question: string; answer: string; citations: Citation[]
  was_refused: boolean; tokens_used?: number; latency_ms?: number; estimated_cost_usd?: number
}
export interface HistoryItem {
  id: string; question: string; answer?: string; citations: Citation[]
  was_refused: boolean; tokens_used?: number; latency_ms?: number; created_at: string
}

// Auth
export const signup = (email: string, username: string, password: string) =>
  api.post<User>('/auth/signup', { email, username, password })

export const login = (username: string, password: string) =>
  api.post<TokenResponse>('/auth/login', { username, password })

export const getMe = () => api.get<User>('/auth/me')

// Documents
export const listDocuments = (status?: string) =>
  api.get<{ items: Document[]; total: number }>('/documents', { params: status ? { status } : {} })

export const uploadDocument = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return api.post<Document>('/documents', form, { headers: { 'Content-Type': 'multipart/form-data' } })
}

export const deleteDocument = (id: string) => api.delete(`/documents/${id}`)
export const getDocument = (id: string) => api.get<Document>(`/documents/${id}`)

// Questions
export const askQuestion = (question: string, document_ids?: string[]) =>
  api.post<AskResponse>('/questions', { question, document_ids: document_ids?.length ? document_ids : undefined })

export const getHistory = (skip = 0, limit = 20) =>
  api.get<{ items: HistoryItem[]; total: number }>('/questions', { params: { skip, limit } })
