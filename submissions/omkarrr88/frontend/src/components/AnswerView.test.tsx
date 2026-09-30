import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { makeAnswer, makeCitation } from '../test/fixtures'
import { AnswerView } from './AnswerView'

describe('AnswerView', () => {
  it('shows the answer, its sources and the usage', () => {
    const { container } = render(<AnswerView answer={makeAnswer()} />)

    expect(screen.getByRole('heading', { name: /international flights/i })).toBeInTheDocument()
    expect(screen.getByText('At least 14 business days in advance.')).toBeInTheDocument()
    const sources = screen.getByRole('list')
    expect(within(sources).getByText('travel-policy.md')).toBeInTheDocument()
    expect(within(sources).getByText('Travel > Flights')).toBeInTheDocument()
    expect(within(sources).getByText('similarity 0.83')).toBeInTheDocument()
    expect(container.querySelector('mark')).toHaveTextContent(
      'International flights must be booked at least 14 business days in advance',
    )
    expect(screen.getByText('1.3 s')).toBeInTheDocument()
    expect(screen.getByText('1,000 tokens')).toBeInTheDocument()
    expect(screen.getByText('$0.0005')).toBeInTheDocument()
    expect(screen.queryByText('Cached answer')).not.toBeInTheDocument()
  })

  it('shows page numbers, cached answers and unverified quotes', () => {
    const citation = makeCitation({ page_start: 2, page_end: 3, quote_verified: false })
    render(<AnswerView answer={makeAnswer({ cached: true, citations: [citation] })} />)

    expect(screen.getByText('pp. 2–3')).toBeInTheDocument()
    expect(screen.getByText('Cached answer')).toBeInTheDocument()
    expect(screen.getByText(/does not appear word for word/)).toBeInTheDocument()
  })

  it('marks answers that were not found and lists no sources', () => {
    const answer = makeAnswer({
      found: false,
      answer: "I couldn't find this in your documents.",
      citations: [],
    })
    const { container } = render(<AnswerView answer={answer} />)

    expect(container.querySelector('article')).toHaveClass('not-found')
    expect(screen.queryByRole('heading', { name: 'Sources' })).not.toBeInTheDocument()
  })
})
