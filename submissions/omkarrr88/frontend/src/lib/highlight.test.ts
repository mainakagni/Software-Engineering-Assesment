import { describe, expect, it } from 'vitest'

import { highlight } from './highlight'

const PASSAGE = 'Domestic flights need 7 days.\nInternational flights  need 14 business days.'

describe('highlight', () => {
  it('marks the quoted part of the passage', () => {
    expect(highlight(PASSAGE, 'International flights need 14 business days')).toEqual([
      { text: 'Domestic flights need 7 days.\n', match: false },
      { text: 'International flights  need 14 business days', match: true },
      { text: '.', match: false },
    ])
  })

  it('ignores case, line breaks and wrapping quotation marks', () => {
    const segments = highlight(PASSAGE, '"domestic FLIGHTS need 7 days. international flights"')
    expect(segments.filter((segment) => segment.match)).toEqual([
      { text: 'Domestic flights need 7 days.\nInternational flights', match: true },
    ])
  })

  it('treats curly quotes and dashes like their plain versions', () => {
    const passage = 'The employee’s manager signs — always in writing.'
    const [, marked] = highlight(passage, "employee's manager signs - always")
    expect(marked).toEqual({ text: 'employee’s manager signs — always', match: true })
  })

  it('returns the whole passage unmarked when the quote is not in it', () => {
    expect(highlight(PASSAGE, 'Hotels cost 180 a night')).toEqual([{ text: PASSAGE, match: false }])
    expect(highlight(PASSAGE, '  ')).toEqual([{ text: PASSAGE, match: false }])
  })

  it('handles a quote that covers the whole passage', () => {
    expect(highlight('Short passage.', 'Short passage.')).toEqual([
      { text: 'Short passage', match: true },
      { text: '.', match: false },
    ])
  })
})
