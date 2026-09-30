import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { failure, makeDocument } from '../test/fixtures'
import { DocumentList } from './DocumentList'

const GUIDE = makeDocument({ id: 'doc-1', filename: 'guide.pdf', page_count: 12, chunk_count: 40 })

function noop() {
  return vi.fn<(id: string) => void>()
}

describe('DocumentList', () => {
  it('shows each document with its status and contents', () => {
    const notes = makeDocument({
      id: 'doc-2',
      filename: 'notes.md',
      status: 'processing',
      chunk_count: null,
    })
    render(<DocumentList documents={[GUIDE, notes]} error={null} onDeleted={noop()} />)

    expect(screen.getByText('guide.pdf')).toBeInTheDocument()
    expect(screen.getByText('Ready')).toBeInTheDocument()
    expect(screen.getByText('12 pages')).toBeInTheDocument()
    expect(screen.getByText('40 passages')).toBeInTheDocument()
    expect(screen.getByText('Processing')).toBeInTheDocument()
    expect(screen.getByText('2.0 KB')).toBeInTheDocument() // only the size until it is processed
  })

  it('says why a document failed', () => {
    const broken = makeDocument({ status: 'failed', error: 'The PDF has no text layer.' })
    render(<DocumentList documents={[broken]} error={null} onDeleted={noop()} />)

    expect(screen.getByText('Failed')).toBeInTheDocument()
    expect(screen.getByText('The PDF has no text layer.')).toBeInTheDocument()
  })

  it('asks before deleting, then deletes', async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const onDeleted = vi.fn<(id: string) => void>()
    render(<DocumentList documents={[GUIDE]} error={null} onDeleted={onDeleted} />)

    await userEvent.click(screen.getByRole('button', { name: 'Delete guide.pdf' }))
    expect(screen.getByText('Delete this document?')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus()
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith('doc-1'))
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/documents/doc-1')
  })

  it('returns focus to the delete button when cancelled', async () => {
    render(<DocumentList documents={[GUIDE]} error={null} onDeleted={noop()} />)
    const trigger = screen.getByRole('button', { name: 'Delete guide.pdf' })

    await userEvent.click(trigger)
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByText('Delete this document?')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('shows a failed delete next to the document', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(async () => failure(503, 'unavailable', 'Please try again shortly.')),
    )
    const onDeleted = vi.fn<(id: string) => void>()
    render(<DocumentList documents={[GUIDE]} error={null} onDeleted={onDeleted} />)

    await userEvent.click(screen.getByRole('button', { name: 'Delete guide.pdf' }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Please try again shortly.')
    expect(onDeleted).not.toHaveBeenCalled()
  })

  it('has an empty state and a loading state', () => {
    const { rerender } = render(<DocumentList documents={[]} error={null} onDeleted={noop()} />)
    expect(screen.getByText('No documents yet')).toBeInTheDocument()

    rerender(<DocumentList documents={null} error={null} onDeleted={noop()} />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading your documents')
  })
})
