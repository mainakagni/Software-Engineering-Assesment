import { useCallback, useEffect, useRef, useState } from 'react'

import { api, errorMessage } from '../api/client'
import type { DocumentItem } from '../api/types'
import { isProcessing } from './format'

const POLL_MS = 2000

/** The user's documents, polled while any of them is still being processed. */
export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  // List requests are numbered. A list is shown only if it is the newest one so far and was
  // requested after the last upload or delete here; otherwise a slow poll would undo that change.
  const requested = useRef(0)
  const shown = useRef(0)
  const changedAt = useRef(0)
  const processing = documents?.some(isProcessing) ?? false

  // Loads once, and again every POLL_MS while something is processing.
  useEffect(() => {
    let active = true
    const load = () => {
      requested.current += 1
      const request = requested.current
      return api.listDocuments().then(
        (loaded) => {
          if (!active) return
          if (request <= changedAt.current) {
            // Overtaken by an upload or delete here. If no newer list is on its way, ask again.
            if (request === requested.current) void load()
            return
          }
          if (request <= shown.current) return
          shown.current = request
          setDocuments(loaded)
          setError(null)
        },
        (caught: unknown) => {
          if (active) setError(errorMessage(caught))
        },
      )
    }
    void load()
    const timer = processing ? window.setInterval(load, POLL_MS) : undefined
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [processing])

  const added = useCallback((document: DocumentItem) => {
    changedAt.current = requested.current
    setDocuments((current) => [document, ...(current ?? []).filter((d) => d.id !== document.id)])
  }, [])

  const removed = useCallback((id: string) => {
    changedAt.current = requested.current
    setDocuments((current) => (current ?? []).filter((d) => d.id !== id))
  }, [])

  return { documents, error, added, removed }
}
