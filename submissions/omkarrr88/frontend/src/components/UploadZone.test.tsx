import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { DocumentItem } from '../api/types'
import { failure, makeDocument, ok } from '../test/fixtures'
import { UploadZone } from './UploadZone'

function fileInput(container: HTMLElement): HTMLInputElement {
  return container.querySelector('input[type=file]') as HTMLInputElement
}

describe('UploadZone', () => {
  it('uploads the files it can take and explains the ones it cannot', async () => {
    const queued = makeDocument({ id: 'doc-9', filename: 'notes.md', status: 'queued' })
    const fetchMock = vi.fn<typeof fetch>(async () => ok(queued, 202))
    vi.stubGlobal('fetch', fetchMock)
    const onUploaded = vi.fn<(document: DocumentItem) => void>()
    const user = userEvent.setup({ applyAccept: false })
    const { container } = render(<UploadZone onUploaded={onUploaded} />)

    await user.upload(fileInput(container), [
      new File(['# Notes'], 'notes.md', { type: 'text/markdown' }),
      new File(['x'], 'photo.png', { type: 'image/png' }),
    ])

    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith(queued))
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'photo.png: only PDF, .txt and .md files are supported.',
    )
  })

  it('reports an upload the server refused', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(async () =>
        failure(409, 'document_limit', 'You have reached the limit of 20 documents.'),
      ),
    )
    const onUploaded = vi.fn<(document: DocumentItem) => void>()
    const { container } = render(<UploadZone onUploaded={onUploaded} />)

    const note = new File(['text'], 'a.txt', { type: 'text/plain' })
    await userEvent.upload(fileInput(container), note)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'a.txt: You have reached the limit of 20 documents.',
    )
    expect(onUploaded).not.toHaveBeenCalled()
  })
})
