import { useCallback, useEffect, useState } from 'react'

import { api, errorMessage } from '../api/client'
import type { DocumentItem } from '../api/types'
import { isProcessing } from './format'

const POLL_MS = 2000

/** The user's documents, polled while any of them is still being processed. */
export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const processing = documents?.some(isProcessing) ?? false

  // Loads once, and again every POLL_MS while something is processing.
  useEffect(() => {
    let active = true
    const load = () =>
      api.listDocuments().then(
        (loaded) => {
          if (!active) return
          setDocuments(loaded)
          setError(null)
        },
        (caught: unknown) => {
          if (active) setError(errorMessage(caught))
        },
      )
    void load()
    const timer = processing ? window.setInterval(load, POLL_MS) : undefined
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [processing])

  const added = useCallback((document: DocumentItem) => {
    setDocuments((current) => [document, ...(current ?? []).filter((d) => d.id !== document.id)])
  }, [])

  const removed = useCallback((id: string) => {
    setDocuments((current) => (current ?? []).filter((d) => d.id !== id))
  }, [])

  return { documents, error, processing, added, removed }
}
