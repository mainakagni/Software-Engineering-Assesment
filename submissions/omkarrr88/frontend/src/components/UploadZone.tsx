import { CircleAlert, LoaderCircle, Upload } from 'lucide-react'
import { useRef, useState, type ChangeEvent, type DragEvent } from 'react'

import { api, errorMessage } from '../api/client'
import type { DocumentItem } from '../api/types'
import { ACCEPTED_EXTENSIONS, uploadProblem } from '../lib/format'

interface Props {
  onUploaded: (document: DocumentItem) => void
}

export function UploadZone({ onUploaded }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState<string | null>(null)
  const [problems, setProblems] = useState<string[]>([])

  async function uploadAll(files: File[]) {
    if (uploading !== null || files.length === 0) return
    const found: string[] = []
    for (const file of files) {
      const problem = uploadProblem(file)
      if (problem) {
        found.push(problem)
        continue
      }
      setUploading(file.name)
      try {
        onUploaded(await api.uploadDocument(file))
      } catch (caught) {
        found.push(`${file.name}: ${errorMessage(caught)}`)
      }
    }
    setUploading(null)
    setProblems(found)
  }

  function onChange(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? [])
    event.target.value = '' // so choosing the same file again still fires a change
    void uploadAll(files)
  }

  function onDragLeave(event: DragEvent<HTMLDivElement>) {
    // Moving onto a child element also fires dragleave; only leaving the zone counts.
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false)
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragging(false)
    void uploadAll(Array.from(event.dataTransfer.files))
  }

  return (
    <div className="upload">
      <div
        className={dragging ? 'dropzone dragging' : 'dropzone'}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        <span className="dropzone-icon">
          <Upload size={16} />
        </span>
        <div className="dropzone-text">
          <p>
            <button
              type="button"
              className="link-button"
              disabled={uploading !== null}
              onClick={() => input.current?.click()}
            >
              Choose files
            </button>{' '}
            or drop them here
          </p>
          <p className="field-hint">PDF, .txt or .md, up to 10 MB each</p>
        </div>
        <input
          ref={input}
          type="file"
          multiple
          accept={ACCEPTED_EXTENSIONS.join(',')}
          hidden
          onChange={onChange}
        />
      </div>
      {uploading && (
        <p className="upload-status" role="status">
          <LoaderCircle size={14} className="spin" />
          Uploading {uploading}…
        </p>
      )}
      {problems.length > 0 && (
        <div className="callout error" role="alert">
          <CircleAlert size={16} className="icon" />
          {problems.length === 1 ? (
            <span>{problems[0]}</span>
          ) : (
            <ul>
              {problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
