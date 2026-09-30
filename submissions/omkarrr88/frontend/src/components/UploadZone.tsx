import { LoaderCircle, Upload } from 'lucide-react'
import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from 'react'

import { api, errorMessage } from '../api/client'
import type { DocumentItem } from '../api/types'
import { ACCEPTED_EXTENSIONS, uploadProblem } from '../lib/format'
import { Callout } from './Callout'

interface Props {
  onUploaded: (document: DocumentItem) => void
}

interface Progress {
  name: string
  waiting: number
}

export function UploadZone({ onUploaded }: Props) {
  const input = useRef<HTMLInputElement>(null)
  // Files added while an upload runs wait here and go up one at a time, in order.
  const queue = useRef<File[]>([])
  const running = useRef(false)
  const [dragging, setDragging] = useState(false)
  const [progress, setProgress] = useState<Progress | null>(null)
  const [problems, setProblems] = useState<string[]>([])

  // Logging out or an expired session closes the workspace. The files still waiting must not go
  // up afterwards: each request uses whichever token is current, which may be someone else's.
  useEffect(
    () => () => {
      queue.current = []
    },
    [],
  )

  async function add(files: File[]) {
    queue.current = [...queue.current, ...files]
    if (running.current) {
      setProgress((current) => current && { ...current, waiting: queue.current.length })
      return
    }
    if (queue.current.length === 0) return
    running.current = true
    setProblems([])
    const found: string[] = []
    for (let file = takeNext(); file; file = takeNext()) {
      const problem = uploadProblem(file) ?? (await upload(file))
      if (problem) found.push(problem)
    }
    running.current = false
    setProgress(null)
    setProblems(found)
  }

  function takeNext(): File | undefined {
    const [next, ...rest] = queue.current
    queue.current = rest
    return next
  }

  /** Uploads one file and says why it failed, or returns null. */
  async function upload(file: File): Promise<string | null> {
    setProgress({ name: file.name, waiting: queue.current.length })
    try {
      onUploaded(await api.uploadDocument(file))
      return null
    } catch (caught) {
      return `${file.name}: ${errorMessage(caught)}`
    }
  }

  function onChange(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? [])
    event.target.value = '' // so choosing the same file again still fires a change
    void add(files)
  }

  function onDragLeave(event: DragEvent<HTMLDivElement>) {
    // Moving onto a child element also fires dragleave; only leaving the zone counts.
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false)
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragging(false)
    void add(Array.from(event.dataTransfer.files))
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
            <button type="button" className="link-button" onClick={() => input.current?.click()}>
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
      <p className="upload-status" role="status">
        {progress && (
          <>
            <LoaderCircle size={14} className="spin" />
            <span>
              Uploading {progress.name}…
              {progress.waiting > 0 && (
                <span className="upload-waiting"> {progress.waiting} more waiting</span>
              )}
            </span>
          </>
        )}
      </p>
      {problems.length > 0 && (
        <Callout tone="error" announce>
          {problems.length === 1 ? (
            problems[0]
          ) : (
            <ul>
              {problems.map((problem, index) => (
                <li key={`${index}:${problem}`}>{problem}</li>
              ))}
            </ul>
          )}
        </Callout>
      )}
    </div>
  )
}
