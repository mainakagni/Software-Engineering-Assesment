import {
  CircleAlert,
  CircleCheck,
  Clock,
  LoaderCircle,
  Trash2,
  type LucideIcon,
} from 'lucide-react'
import { useRef, useState } from 'react'

import { ApiError, api, errorMessage } from '../api/client'
import type { DocumentItem, DocumentStatus } from '../api/types'
import { documentKind, formatBytes, plural, type DocumentKind } from '../lib/format'

const STATUS: Record<DocumentStatus, { label: string; Icon: LucideIcon }> = {
  queued: { label: 'Queued', Icon: Clock },
  processing: { label: 'Processing', Icon: LoaderCircle },
  ready: { label: 'Ready', Icon: CircleCheck },
  failed: { label: 'Failed', Icon: CircleAlert },
}

const KIND_LABELS: Record<DocumentKind, string> = { pdf: 'PDF', md: 'MD', txt: 'TXT' }

interface Props {
  documents: DocumentItem[] | null
  error: string | null
  onDeleted: (id: string) => void
}

export function DocumentList({ documents, error, onDeleted }: Props) {
  return (
    <>
      {error && (
        <p className="callout error" role="alert">
          <CircleAlert size={16} className="icon" />
          <span>{error}</span>
        </p>
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

function DocumentRow({
  document,
  onDeleted,
}: {
  document: DocumentItem
  onDeleted: (id: string) => void
}) {
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const kind = documentKind(document.filename)

  async function remove() {
    setDeleting(true)
    setError(null)
    try {
      await api.deleteDocument(document.id)
      onDeleted(document.id)
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) {
        onDeleted(document.id) // already gone
        return
      }
      setError(errorMessage(caught))
      setDeleting(false)
      setConfirming(false)
      trigger.current?.focus()
    }
  }

  function cancel() {
    setConfirming(false)
    trigger.current?.focus()
  }

  return (
    <li className={confirming ? 'document confirming' : 'document'}>
      <span className={`kind kind-${kind}`} aria-hidden="true">
        {KIND_LABELS[kind]}
      </span>
      <div className="document-body">
        <span
          className="document-name"
          title={`${document.filename} (${formatBytes(document.size_bytes)})`}
        >
          {document.filename}
        </span>
        <span className="document-meta">
          <StatusLabel status={document.status} />
          {details(document).map((detail) => (
            <span key={detail}>{detail}</span>
          ))}
        </span>
      </div>
      <button
        ref={trigger}
        type="button"
        className="icon-button danger delete"
        aria-label={`Delete ${document.filename}`}
        aria-expanded={confirming}
        onClick={() => setConfirming(true)}
      >
        <Trash2 size={16} />
      </button>
      {document.status === 'failed' && document.error && (
        <p className="document-error">{document.error}</p>
      )}
      {error && (
        <p className="document-error" role="alert">
          {error}
        </p>
      )}
      {confirming && (
        <div className="confirm">
          <span>Delete this document?</span>
          <button type="button" className="button small" autoFocus onClick={cancel}>
            Cancel
          </button>
          <button
            type="button"
            className="button danger small"
            disabled={deleting}
            onClick={() => void remove()}
          >
            {deleting ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      )}
    </li>
  )
}

function StatusLabel({ status }: { status: DocumentStatus }) {
  const { label, Icon } = STATUS[status]
  return (
    <span className={`status status-${status}`}>
      <Icon size={12} strokeWidth={2.25} className={status === 'processing' ? 'spin' : undefined} />
      {label}
    </span>
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

/** Pages and passages once processed; until then, only the file size is known. */
function details(document: DocumentItem): string[] {
  const parts: string[] = []
  if (document.page_count !== null) parts.push(plural(document.page_count, 'page'))
  if (document.chunk_count !== null) parts.push(plural(document.chunk_count, 'passage'))
  return parts.length > 0 ? parts : [formatBytes(document.size_bytes)]
}
