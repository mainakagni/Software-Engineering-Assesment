import { useRef } from 'react'

import type { DocumentItem } from '../api/types'
import { Callout } from './Callout'
import { DocumentRow } from './DocumentRow'

interface Props {
  documents: DocumentItem[] | null
  error: string | null
  /** `focusHeading`: focus should move to the heading above the list, as no document is left for it. */
  onDeleted: (document: DocumentItem, focusHeading: boolean) => void
}

export function DocumentList({ documents, error, onDeleted }: Props) {
  const list = useRef<HTMLUListElement>(null)

  // The deleted row takes the focus with it. The next document's delete button (or the previous
  // one's, at the end) takes it over, so the user stays where they were in the list.
  function deleted(document: DocumentItem, hadFocus: boolean) {
    const all = documents ?? []
    const index = all.findIndex((other) => other.id === document.id)
    const neighbour = all[index + 1] ?? all[index - 1]
    const buttons = list.current?.querySelectorAll<HTMLButtonElement>('button[data-delete]') ?? []
    const target = Array.from(buttons).find((button) => button.dataset.delete === neighbour?.id)
    onDeleted(document, hadFocus && target === undefined)
    if (hadFocus) target?.focus()
  }

  return (
    <>
      {error && (
        <Callout tone="error" announce>
          {error}
        </Callout>
      )}
      {documents === null && !error && <LoadingRows />}
      {documents?.length === 0 && (
        <div className="empty">
          <strong>No documents yet</strong>
          <span>Add a PDF, text or Markdown file, and you can ask about it once it is ready.</span>
        </div>
      )}
      {documents && documents.length > 0 && (
        <ul className="documents" ref={list}>
          {documents.map((document) => (
            <DocumentRow key={document.id} document={document} onDeleted={deleted} />
          ))}
        </ul>
      )}
    </>
  )
}

function LoadingRows() {
  return (
    <>
      <p className="visually-hidden" role="status">
        Loading your documents…
      </p>
      <ul className="documents" aria-hidden="true">
        {[0, 1, 2].map((row) => (
          <li key={row} className="document">
            <span className="kind skeleton-block" />
            <span className="document-body">
              <span className="skeleton" />
              <span className="skeleton short" />
            </span>
          </li>
        ))}
      </ul>
    </>
  )
}
