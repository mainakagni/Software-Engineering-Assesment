import { useState } from 'react'

import { ApiError, api, errorMessage } from '../api/client'
import type { DocumentItem, DocumentStatus } from '../api/types'
import { formatBytes } from '../lib/format'

const STATUS_LABELS: Record<DocumentStatus, string> = {
  queued: 'Queued',
  processing: 'Processing',
  ready: 'Ready',
  failed: 'Failed',
}

interface Props {
  documents: DocumentItem[] | null
  error: string | null
  onDeleted: (id: string) => void
}

export function DocumentList({ documents, error, onDeleted }: Props) {
  const [confirming, setConfirming] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  async function remove(id: string) {
    setDeleting(id)
    setDeleteError(null)
    try {
      await api.deleteDocument(id)
      onDeleted(id)
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) onDeleted(id) // already gone
      else setDeleteError(errorMessage(caught))
    } finally {
      setDeleting(null)
      setConfirming(null)
    }
  }

  return (
    <section className="panel" aria-labelledby="documents-title">
      <h2 id="documents-title">Your documents</h2>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {deleteError && (
        <p className="error" role="alert">
          {deleteError}
        </p>
      )}
      {documents === null && !error && <p className="muted">Loading...</p>}
      {documents?.length === 0 && <p className="muted">No documents yet.</p>}
      {documents && documents.length > 0 && (
        <ul className="documents">
          {documents.map((document) => (
            <li key={document.id} className="document">
              <div className="document-head">
                <span className="filename" title={document.filename}>
                  {document.filename}
                </span>
                <span className={`badge status-${document.status}`}>
                  {STATUS_LABELS[document.status]}
                </span>
              </div>
              <p className="document-meta">{describe(document)}</p>
              {document.status === 'failed' && document.error && (
                <p className="error">{document.error}</p>
              )}
              <div className="document-actions">
                {confirming === document.id ? (
                  <>
                    <span>Delete this document?</span>
                    <button
                      type="button"
                      className="danger"
                      disabled={deleting === document.id}
                      onClick={() => void remove(document.id)}
                    >
                      {deleting === document.id ? 'Deleting...' : 'Delete'}
                    </button>
                    <button type="button" onClick={() => setConfirming(null)}>
                      Cancel
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    aria-label={`Delete ${document.filename}`}
                    onClick={() => setConfirming(document.id)}
                  >
                    Delete
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function describe(document: DocumentItem): string {
  const parts = [formatBytes(document.size_bytes)]
  if (document.page_count !== null) parts.push(plural(document.page_count, 'page'))
  if (document.chunk_count !== null) parts.push(plural(document.chunk_count, 'passage'))
  return parts.join(' · ')
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`
}
