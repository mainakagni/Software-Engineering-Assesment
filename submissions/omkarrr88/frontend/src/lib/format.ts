import type { Citation, DocumentItem } from '../api/types'

// The server's limits, repeated here so the page can explain them. The server enforces them.
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024
export const MAX_DOCUMENTS = 20
export const ACCEPTED_EXTENSIONS = ['.pdf', '.txt', '.md', '.markdown']

// The interface is in English, so numbers and times are formatted the English way too.
const LOCALE = 'en'

/** Why the file cannot be uploaded, or null if it looks fine. The server checks again. */
export function uploadProblem(file: File): string | null {
  const name = file.name.toLowerCase()
  if (!ACCEPTED_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return `${file.name}: only PDF, .txt and .md files are supported.`
  }
  if (file.size === 0) return `${file.name}: the file is empty.`
  if (file.size > MAX_UPLOAD_BYTES) return `${file.name}: the file is larger than 10 MB.`
  return null
}

export function isProcessing(document: DocumentItem): boolean {
  return document.status === 'queued' || document.status === 'processing'
}

export type DocumentKind = 'pdf' | 'md' | 'txt'

export function documentKind(filename: string): DocumentKind {
  const name = filename.toLowerCase()
  if (name.endsWith('.pdf')) return 'pdf'
  if (name.endsWith('.md') || name.endsWith('.markdown')) return 'md'
  return 'txt'
}

export function plural(count: number, noun: string): string {
  return `${count.toLocaleString(LOCALE)} ${noun}${count === 1 ? '' : 's'}`
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** "p. 3" or "pp. 3-4" for PDFs; null for text files, which have no pages. */
export function formatPages(citation: Pick<Citation, 'page_start' | 'page_end'>): string | null {
  const { page_start: start, page_end: end } = citation
  if (start === null) return null
  return end === null || end === start ? `p. ${start}` : `pp. ${start}–${end}`
}

export function formatSeconds(milliseconds: number): string {
  return `${(milliseconds / 1000).toFixed(1)} s`
}

export function formatCost(usd: number): string {
  if (usd === 0) return '$0'
  if (usd < 0.0001) return '< $0.0001'
  return `$${usd.toFixed(4)}`
}

const relative = new Intl.RelativeTimeFormat(LOCALE, { numeric: 'auto' })

export function formatAge(isoTime: string, now: Date = new Date()): string {
  const seconds = Math.round((new Date(isoTime).getTime() - now.getTime()) / 1000)
  if (Math.abs(seconds) < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (Math.abs(minutes) < 60) return relative.format(minutes, 'minute')
  const hours = Math.round(minutes / 60)
  if (Math.abs(hours) < 24) return relative.format(hours, 'hour')
  return relative.format(Math.round(hours / 24), 'day')
}
