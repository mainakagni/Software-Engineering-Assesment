import type { DocumentItem } from '../api/types'
import { MAX_DOCUMENTS } from '../lib/format'
import { DocumentList } from './DocumentList'
import { UploadZone } from './UploadZone'

interface Props {
  documents: DocumentItem[] | null
  error: string | null
  onUploaded: (document: DocumentItem) => void
  onDeleted: (id: string) => void
}

/** The sidebar: upload, and the user's documents with their processing status. */
export function Library({ documents, error, onUploaded, onDeleted }: Props) {
  return (
    <section className="library" aria-labelledby="documents-title">
      <div className="library-inner">
        <div className="section-head">
          <h2 id="documents-title" className="section-title">
            Your documents
          </h2>
          {documents !== null && (
            <span className="count" title={`You can keep up to ${MAX_DOCUMENTS} documents`}>
              {documents.length} of {MAX_DOCUMENTS}
            </span>
          )}
        </div>
        <UploadZone onUploaded={onUploaded} />
        <DocumentList documents={documents} error={error} onDeleted={onDeleted} />
      </div>
    </section>
  )
}
