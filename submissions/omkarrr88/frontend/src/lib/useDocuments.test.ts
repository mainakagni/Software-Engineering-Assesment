import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { makeDocument, ok } from '../test/fixtures'
import { useDocuments } from './useDocuments'

/** Each list request waits until the test answers it. */
function stubLists() {
  const answers: ((response: Response) => void)[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>(() => new Promise<Response>((resolve) => answers.push(resolve))),
  )
  return answers
}

describe('useDocuments', () => {
  const queued = makeDocument({ id: 'doc-1', status: 'queued', chunk_count: null })
  const uploaded = makeDocument({ id: 'doc-2', status: 'queued', chunk_count: null })

  it('keeps an upload that an older list does not know about yet', async () => {
    const answers = stubLists()
    const { result } = renderHook(() => useDocuments())
    await waitFor(() => expect(answers).toHaveLength(1))
    await act(async () => answers[0]?.(ok([queued])))
    // A document is processing, so the list is fetched again straight away.
    await waitFor(() => expect(answers).toHaveLength(2))

    act(() => result.current.added(uploaded))
    await act(async () => answers[1]?.(ok([queued]))) // requested before the upload

    expect(result.current.documents?.map((document) => document.id)).toEqual(['doc-2', 'doc-1'])
  })

  it('asks again when the only list on its way was overtaken by a change', async () => {
    const answers = stubLists()
    const { result } = renderHook(() => useDocuments())
    await waitFor(() => expect(answers).toHaveLength(1))
    const ready = makeDocument({ id: 'doc-3', status: 'ready' })

    act(() => result.current.added(ready)) // nothing is processing, so no poll is due
    await act(async () => answers[0]?.(ok([]))) // requested before the change: not shown
    await waitFor(() => expect(answers).toHaveLength(2))
    await act(async () => answers[1]?.(ok([ready, makeDocument({ id: 'doc-4' })])))

    expect(result.current.documents?.map((document) => document.id)).toEqual(['doc-3', 'doc-4'])
  })

  it('keeps a delete that an older list does not know about yet', async () => {
    const answers = stubLists()
    const { result } = renderHook(() => useDocuments())
    await waitFor(() => expect(answers).toHaveLength(1))
    await act(async () => answers[0]?.(ok([uploaded, queued])))
    await waitFor(() => expect(answers).toHaveLength(2))

    act(() => result.current.removed('doc-2'))
    await act(async () => answers[1]?.(ok([uploaded, queued]))) // requested before the delete

    expect(result.current.documents?.map((document) => document.id)).toEqual(['doc-1'])
  })
})
