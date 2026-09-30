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
import { BusyButton } from './BusyButton'

const STATUS: Record<DocumentStatus, { label: string; Icon: LucideIcon }> = {
  queued: { label: 'Queued', Icon: Clock },
  processing: { label: 'Processing', Icon: LoaderCircle },
  ready: { label: 'Ready', Icon: CircleCheck },
  failed: { label: 'Failed', Icon: CircleAlert },
}

const KIND_LABELS: Record<DocumentKind, string> = { pdf: 'PDF', md: 'MD', txt: 'TXT' }

interface Props {
  document: DocumentItem
  onDeleted: (document: DocumentItem) => void
}

export function DocumentRow({ document, onDeleted }: Props) {
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const kind = documentKind(document.filename)

  // The confirmation closed without deleting: cancelled, or the delete failed.
  function closed(failure: string | null) {
    setConfirming(false)
    setError(failure)
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
      {confirming && <ConfirmDelete document={document} onDeleted={onDeleted} onClosed={closed} />}
    </li>
  )
}

interface ConfirmDeleteProps {
  document: DocumentItem
  onDeleted: (document: DocumentItem) => void
  onClosed: (failure: string | null) => void
}

function ConfirmDelete({ document, onDeleted, onClosed }: ConfirmDeleteProps) {
  const [deleting, setDeleting] = useState(false)

  async function remove() {
    if (deleting) return
    setDeleting(true)
    try {
      await api.deleteDocument(document.id)
      onDeleted(document)
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) onDeleted(document) // already gone
      else onClosed(errorMessage(caught))
    }
  }

  return (
    <div className="confirm" role="group" aria-label={`Delete ${document.filename}?`}>
      <span>Delete this document?</span>
      <button
        type="button"
        className="button small"
        autoFocus
        disabled={deleting}
        onClick={() => onClosed(null)}
      >
        Cancel
      </button>
      <BusyButton
        type="button"
        className="button danger small"
        busy={deleting}
        busyText="Deleting…"
        onClick={() => void remove()}
      >
        Delete
      </BusyButton>
    </div>
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

/** Pages and passages once processed; until then, only the file size is known. */
function details(document: DocumentItem): string[] {
  const parts: string[] = []
  if (document.page_count !== null) parts.push(plural(document.page_count, 'page'))
  if (document.chunk_count !== null) parts.push(plural(document.chunk_count, 'passage'))
  return parts.length > 0 ? parts : [formatBytes(document.size_bytes)]
}
