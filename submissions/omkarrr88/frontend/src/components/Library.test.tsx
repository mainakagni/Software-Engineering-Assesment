import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { DocumentItem } from '../api/types'
import { makeDocument } from '../test/fixtures'
import { Library } from './Library'

const GUIDE = makeDocument({ id: 'doc-1', filename: 'guide.pdf' })

describe('Library', () => {
  it('shows how many documents there are out of the limit', () => {
    render(
      <Library
        documents={[GUIDE]}
        error={null}
        onUploaded={vi.fn<(document: DocumentItem) => void>()}
        onDeleted={vi.fn<(id: string) => void>()}
      />,
    )

    expect(screen.getByText('1 of 20')).toBeInTheDocument()
  })

  it('moves focus to the list and says what was deleted', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => new Response(null, { status: 204 })))
    const onDeleted = vi.fn<(id: string) => void>()
    render(
      <Library
        documents={[GUIDE]}
        error={null}
        onUploaded={vi.fn<(document: DocumentItem) => void>()}
        onDeleted={onDeleted}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Delete guide.pdf' }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith('doc-1'))
    expect(screen.getByRole('heading', { name: 'Your documents' })).toHaveFocus()
    expect(screen.getByText('guide.pdf was deleted.')).toBeInTheDocument()
  })
})
