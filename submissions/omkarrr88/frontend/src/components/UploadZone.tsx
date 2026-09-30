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

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragging(false)
    void uploadAll(Array.from(event.dataTransfer.files))
  }

  return (
    <section className="panel" aria-labelledby="upload-title">
      <h2 id="upload-title">Add documents</h2>
      <div
        className={dragging ? 'dropzone dragging' : 'dropzone'}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <p>Drop PDF, .txt or .md files here</p>
        <button
          type="button"
          disabled={uploading !== null}
          onClick={() => input.current?.click()}
        >
          Choose files
        </button>
        <input
          ref={input}
          type="file"
          multiple
          accept={ACCEPTED_EXTENSIONS.join(',')}
          hidden
          onChange={onChange}
        />
        <p className="hint">Up to 10 MB each, 20 documents per account.</p>
      </div>
      {uploading && (
        <p className="status" role="status">
          Uploading {uploading}...
        </p>
      )}
      {problems.length > 0 && (
        <ul className="error" role="alert">
          {problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
