import { describe, expect, it } from 'vitest'

import {
  documentKind,
  formatAge,
  formatBytes,
  formatCost,
  formatPages,
  plural,
  uploadProblem,
} from './format'

function file(name: string, size: number): File {
  const upload = new File(['x'], name)
  Object.defineProperty(upload, 'size', { value: size })
  return upload
}

describe('uploadProblem', () => {
  it('accepts the supported types', () => {
    for (const name of ['a.pdf', 'b.TXT', 'c.md', 'd.markdown']) {
      expect(uploadProblem(file(name, 100))).toBeNull()
    }
  })

  it('explains what is wrong', () => {
    expect(uploadProblem(file('photo.png', 100))).toMatch(/only PDF, \.txt and \.md/)
    expect(uploadProblem(file('empty.txt', 0))).toMatch(/empty/)
    expect(uploadProblem(file('big.pdf', 10 * 1024 * 1024 + 1))).toMatch(/larger than 10 MB/)
  })
})

describe('formatting', () => {
  it('formats sizes', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(2048)).toBe('2.0 KB')
    expect(formatBytes(3 * 1024 * 1024)).toBe('3.0 MB')
  })

  it('formats page ranges', () => {
    expect(formatPages({ page_start: null, page_end: null })).toBeNull()
    expect(formatPages({ page_start: 3, page_end: 3 })).toBe('p. 3')
    expect(formatPages({ page_start: 3, page_end: 5 })).toBe('pp. 3–5')
  })

  it('formats costs', () => {
    expect(formatCost(0)).toBe('$0')
    expect(formatCost(0.00002)).toBe('< $0.0001')
    expect(formatCost(0.00052)).toBe('$0.0005')
  })

  it('names the kind of document from its file name', () => {
    expect(documentKind('Guide.PDF')).toBe('pdf')
    expect(documentKind('notes.md')).toBe('md')
    expect(documentKind('notes.markdown')).toBe('md')
    expect(documentKind('log.txt')).toBe('txt')
  })

  it('counts with the right plural', () => {
    expect(plural(1, 'page')).toBe('1 page')
    expect(plural(1200, 'passage')).toBe('1,200 passages')
  })

  it('formats ages relative to now', () => {
    const now = new Date('2026-09-30T12:00:00Z')
    expect(formatAge('2026-09-30T11:59:30Z', now)).toBe('just now')
    expect(formatAge('2026-09-30T11:55:00Z', now)).toBe('5 minutes ago')
    expect(formatAge('2026-09-30T09:00:00Z', now)).toBe('3 hours ago')
    expect(formatAge('2026-09-29T12:00:00Z', now)).toBe('yesterday')
    expect(formatAge('2026-09-28T12:00:00Z', now)).toBe('2 days ago')
  })
})
