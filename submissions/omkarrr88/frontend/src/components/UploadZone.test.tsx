import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { DocumentItem } from '../api/types'
import { failure, makeDocument, ok } from '../test/fixtures'
import { UploadZone } from './UploadZone'

function fileInput(container: HTMLElement): HTMLInputElement {
  return container.querySelector('input[type=file]') as HTMLInputElement
}

function dropzone(container: HTMLElement): HTMLElement {
  return container.querySelector('.dropzone') as HTMLElement
}

function markdown(name: string): File {
  return new File(['# Notes'], name, { type: 'text/markdown' })
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
      markdown('notes.md'),
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

  it('takes dropped files, and queues the ones dropped during an upload', async () => {
    const releases: (() => void)[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(async (_input, init) => {
        if (!(init?.body instanceof FormData)) throw new Error('expected a form upload')
        const file = init.body.get('file') as File
        await new Promise<void>((resolve) => releases.push(resolve))
        return ok(makeDocument({ id: file.name, filename: file.name, status: 'queued' }), 202)
      }),
    )
    const onUploaded = vi.fn<(document: DocumentItem) => void>()
    const { container } = render(<UploadZone onUploaded={onUploaded} />)
    const zone = dropzone(container)

    fireEvent.dragOver(zone)
    expect(zone).toHaveClass('dragging')
    fireEvent.drop(zone, { dataTransfer: { files: [markdown('first.md')] } })
    expect(zone).not.toHaveClass('dragging')
    await waitFor(() => expect(releases).toHaveLength(1))
    expect(screen.getByRole('status')).toHaveTextContent('Uploading first.md…')

    fireEvent.drop(zone, { dataTransfer: { files: [markdown('second.md')] } })
    expect(screen.getByRole('status')).toHaveTextContent('1 more waiting')

    releases[0]?.()
    await waitFor(() => expect(releases).toHaveLength(2))
    expect(screen.getByRole('status')).toHaveTextContent('Uploading second.md…')
    releases[1]?.()

    await waitFor(() => expect(onUploaded).toHaveBeenCalledTimes(2))
    expect(onUploaded.mock.calls.map(([document]) => document.filename)).toEqual([
      'first.md',
      'second.md',
    ])
    await waitFor(() => expect(screen.getByRole('status')).toBeEmptyDOMElement())
  })
})
