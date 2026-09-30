import type { DocumentItem } from '../api/types'
import { Callout } from './Callout'
import { DocumentRow } from './DocumentRow'

interface Props {
  documents: DocumentItem[] | null
  error: string | null
  onDeleted: (document: DocumentItem) => void
}

export function DocumentList({ documents, error, onDeleted }: Props) {
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
        <ul className="documents">
          {documents.map((document) => (
            <DocumentRow key={document.id} document={document} onDeleted={onDeleted} />
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
