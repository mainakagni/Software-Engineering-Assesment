import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { DocumentItem } from '../api/types'
import { failure, makeDocument } from '../test/fixtures'
import { DocumentList } from './DocumentList'

const GUIDE = makeDocument({ id: 'doc-1', filename: 'guide.pdf', page_count: 12, chunk_count: 40 })
const NOTES = makeDocument({ id: 'doc-2', filename: 'notes.md' })

function deletedSpy() {
  return vi.fn<(document: DocumentItem, focusHeading: boolean) => void>()
}

/** A delete request that waits until the test answers it. */
function pendingDelete(response: () => Response) {
  const pending: { release?: () => void } = {}
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>(async () => {
      await new Promise<void>((resolve) => {
        pending.release = resolve
      })
      return response()
    }),
  )
  return pending
}

async function confirmDelete() {
  await userEvent.click(screen.getByRole('button', { name: 'Delete guide.pdf' }))
  await userEvent.click(screen.getByRole('button', { name: 'Delete' }))
}

describe('DocumentList', () => {
  it('shows each document with its status and contents', () => {
    const notes = makeDocument({
      id: 'doc-2',
      filename: 'notes.md',
      status: 'processing',
      chunk_count: null,
    })
    render(<DocumentList documents={[GUIDE, notes]} error={null} onDeleted={deletedSpy()} />)

    expect(screen.getByText('guide.pdf')).toBeInTheDocument()
    expect(screen.getByText('Ready')).toBeInTheDocument()
    expect(screen.getByText('12 pages')).toBeInTheDocument()
    expect(screen.getByText('40 passages')).toBeInTheDocument()
    expect(screen.getByText('Processing')).toBeInTheDocument()
    expect(screen.getByText('2.0 KB')).toBeInTheDocument() // only the size until it is processed
  })

  it('says why a document failed', () => {
    const broken = makeDocument({ status: 'failed', error: 'The PDF has no text layer.' })
    render(<DocumentList documents={[broken]} error={null} onDeleted={deletedSpy()} />)

    expect(screen.getByText('Failed')).toBeInTheDocument()
    expect(screen.getByText('The PDF has no text layer.')).toBeInTheDocument()
  })

  it('asks before deleting, then deletes', async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const onDeleted = deletedSpy()
    render(<DocumentList documents={[GUIDE]} error={null} onDeleted={onDeleted} />)

    await userEvent.click(screen.getByRole('button', { name: 'Delete guide.pdf' }))
    expect(screen.getByRole('group', { name: 'Delete guide.pdf?' })).toHaveTextContent(
      'Delete this document?',
    )
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus()
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    // The list is empty now, so the heading above it should take the focus.
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith(GUIDE, true))
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/documents/doc-1')
  })

  it('moves focus to the next document after a delete', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => new Response(null, { status: 204 })))
    const onDeleted = deletedSpy()
    render(<DocumentList documents={[GUIDE, NOTES]} error={null} onDeleted={onDeleted} />)

    await confirmDelete()

    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith(GUIDE, false))
    expect(screen.getByRole('button', { name: 'Delete notes.md' })).toHaveFocus()
  })

  it('leaves focus alone if the user moved on during a slow delete', async () => {
    const pending = pendingDelete(() => new Response(null, { status: 204 }))
    const onDeleted = deletedSpy()
    render(
      <>
        <DocumentList documents={[GUIDE]} error={null} onDeleted={onDeleted} />
        <input aria-label="Elsewhere" />
      </>,
    )

    await confirmDelete()
    await userEvent.click(screen.getByLabelText('Elsewhere'))
    pending.release?.()

    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith(GUIDE, false))
    expect(screen.getByLabelText('Elsewhere')).toHaveFocus()
  })

  it('leaves focus alone if the user moved on before a delete failed', async () => {
    const pending = pendingDelete(() => failure(503, 'unavailable', 'Please try again shortly.'))
    render(
      <>
        <DocumentList documents={[GUIDE]} error={null} onDeleted={deletedSpy()} />
        <input aria-label="Elsewhere" />
      </>,
    )

    await confirmDelete()
    await userEvent.click(screen.getByLabelText('Elsewhere'))
    pending.release?.()

    expect(await screen.findByRole('alert')).toHaveTextContent('Please try again shortly.')
    expect(screen.getByLabelText('Elsewhere')).toHaveFocus()
  })

  it('stays busy but focusable while deleting', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(() => new Promise<Response>(() => {})))
    render(<DocumentList documents={[GUIDE]} error={null} onDeleted={deletedSpy()} />)

    await confirmDelete()

    const deleting = screen.getByRole('button', { name: 'Deleting…' })
    expect(deleting).toHaveAttribute('aria-disabled', 'true')
    expect(deleting).toHaveFocus()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  })

  it('returns focus to the delete button when cancelled', async () => {
    render(<DocumentList documents={[GUIDE]} error={null} onDeleted={deletedSpy()} />)
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
    const onDeleted = deletedSpy()
    render(<DocumentList documents={[GUIDE]} error={null} onDeleted={onDeleted} />)

    await confirmDelete()

    expect(await screen.findByRole('alert')).toHaveTextContent('Please try again shortly.')
    expect(screen.getByRole('button', { name: 'Delete guide.pdf' })).toHaveFocus()
    expect(onDeleted).not.toHaveBeenCalled()
  })

  it('treats a document that is already gone as deleted', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(async () => failure(404, 'not_found', 'Document not found.')),
    )
    const onDeleted = deletedSpy()
    render(<DocumentList documents={[GUIDE]} error={null} onDeleted={onDeleted} />)

    await confirmDelete()

    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith(GUIDE, true))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('has an empty state, a loading state and an error state', () => {
    const { rerender } = render(
      <DocumentList documents={[]} error={null} onDeleted={deletedSpy()} />,
    )
    expect(screen.getByText('No documents yet')).toBeInTheDocument()

    rerender(<DocumentList documents={null} error={null} onDeleted={deletedSpy()} />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading your documents')

    rerender(
      <DocumentList documents={null} error="The server is not responding." onDeleted={deletedSpy()} />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('The server is not responding.')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
