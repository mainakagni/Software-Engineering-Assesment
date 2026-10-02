import React, { useState, useEffect, useRef } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { listDocuments, uploadDocument, deleteDocument, askQuestion, getHistory, type Document, type AskResponse, type HistoryItem } from '../api/client'

const STATUS_COLOR: Record<string, string> = {
  queued: '#f59e0b', processing: '#3b82f6', ready: '#10b981', failed: '#ef4444'
}

export default function DashboardPage() {
  const { user, logout } = useAuth()
  const [docs, setDocs] = useState<Document[]>([])
  const [uploading, setUploading] = useState(false)
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [answer, setAnswer] = useState<AskResponse | null>(null)
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [activeTab, setActiveTab] = useState<'qa' | 'history' | 'docs'>('qa')
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const loadDocs = async () => {
    try { const r = await listDocuments(); setDocs(r.data.items) } catch { /* ignore */ }
  }

  const loadHistory = async () => {
    try { const r = await getHistory(); setHistory(r.data.items) } catch { /* ignore */ }
  }

  useEffect(() => {
    loadDocs()
    loadHistory()
    const interval = setInterval(loadDocs, 5000) // poll doc status
    return () => clearInterval(interval)
  }, [])

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      await uploadDocument(file)
      await loadDocs()
    } catch (err: unknown) {
      setError((err as {response?: {data?: {detail?: string}}})?.response?.data?.detail ?? 'Upload failed')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this document and all its embeddings?')) return
    await deleteDocument(id)
    await loadDocs()
  }

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!question.trim()) return
    setAsking(true)
    setError('')
    setAnswer(null)
    try {
      const r = await askQuestion(question)
      setAnswer(r.data)
      await loadHistory()
    } catch (err: unknown) {
      const detail = (err as {response?: {data?: {detail?: string}}})?.response?.data?.detail
      setError(detail ?? 'Failed to get answer. Check your API key and documents.')
    } finally {
      setAsking(false)
    }
  }

  const readyDocs = docs.filter(d => d.status === 'ready')

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '1.5rem 1rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem', borderBottom: '1px solid #e2e8f0', paddingBottom: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.4rem', fontWeight: 700, color: '#0f172a' }}>🧠 DocuMind</h1>
          <p style={{ color: '#64748b', fontSize: '0.85rem' }}>Hello, <b>{user?.username}</b></p>
        </div>
        <button onClick={logout} style={{ padding: '0.4rem 1rem', borderRadius: 6, border: '1px solid #e2e8f0', cursor: 'pointer', background: '#fff', color: '#64748b', fontSize: '0.85rem' }}>
          Sign Out
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: '1.5rem', alignItems: 'start' }}>
        {/* Sidebar: Documents */}
        <div style={{ background: '#fff', borderRadius: 10, border: '1px solid #e2e8f0', padding: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
            <h2 style={{ fontWeight: 700, fontSize: '0.95rem' }}>📄 Documents ({docs.length})</h2>
            <button onClick={() => fileRef.current?.click()} disabled={uploading}
              style={{ padding: '0.3rem 0.75rem', borderRadius: 6, border: 'none', background: '#3b82f6', color: '#fff', fontSize: '0.8rem', cursor: 'pointer', opacity: uploading ? 0.6 : 1 }}>
              {uploading ? '…' : '+ Upload'}
            </button>
            <input ref={fileRef} type="file" accept=".pdf,.txt,.md" onChange={handleUpload} style={{ display: 'none' }} />
          </div>
          <p style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '0.75rem' }}>PDF, TXT, Markdown — max 20 MB</p>

          {docs.length === 0 ? (
            <p style={{ color: '#94a3b8', fontSize: '0.85rem', textAlign: 'center', padding: '1rem 0' }}>No documents yet</p>
          ) : (
            docs.map(doc => (
              <div key={doc.id} style={{ borderRadius: 8, border: '1px solid #f1f5f9', padding: '0.6rem 0.75rem', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: '0.8rem', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.original_filename}</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', marginTop: 2 }}>
                    <span style={{ width: 7, height: 7, borderRadius: '50%', background: STATUS_COLOR[doc.status], display: 'inline-block' }} />
                    <span style={{ fontSize: '0.7rem', color: '#64748b' }}>{doc.status}{doc.chunk_count ? ` · ${doc.chunk_count} chunks` : ''}</span>
                  </div>
                  {doc.error_message && <div style={{ fontSize: '0.7rem', color: '#ef4444', marginTop: 2 }}>{doc.error_message}</div>}
                </div>
                <button onClick={() => handleDelete(doc.id)} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: '1rem', padding: '0 0.25rem' }} title="Delete">🗑</button>
              </div>
            ))
          )}
        </div>

        {/* Main panel */}
        <div>
          {/* Tabs */}
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
            {(['qa', 'history'] as const).map(tab => (
              <button key={tab} onClick={() => setActiveTab(tab)}
                style={{ padding: '0.4rem 1rem', borderRadius: 6, border: '1px solid #e2e8f0', cursor: 'pointer', background: activeTab === tab ? '#3b82f6' : '#fff', color: activeTab === tab ? '#fff' : '#64748b', fontWeight: activeTab === tab ? 700 : 400, fontSize: '0.85rem' }}>
                {tab === 'qa' ? '💬 Ask a Question' : '📜 History'}
              </button>
            ))}
          </div>

          {/* Q&A Tab */}
          {activeTab === 'qa' && (
            <div style={{ background: '#fff', borderRadius: 10, border: '1px solid #e2e8f0', padding: '1.25rem' }}>
              {readyDocs.length === 0 && (
                <div style={{ background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: 8, padding: '0.75rem', marginBottom: '1rem', fontSize: '0.85rem', color: '#92400e' }}>
                  ⚠️ Upload and wait for at least one document to reach <b>ready</b> status before asking.
                </div>
              )}
              <form onSubmit={handleAsk}>
                <textarea
                  value={question}
                  onChange={e => setQuestion(e.target.value)}
                  placeholder="Ask a question about your documents…"
                  rows={3}
                  style={{ width: '100%', padding: '0.75rem', border: '1px solid #d1d5db', borderRadius: 8, fontSize: '0.95rem', resize: 'vertical', marginBottom: '0.75rem', fontFamily: 'inherit' }}
                />
                <button type="submit" disabled={asking || readyDocs.length === 0}
                  style={{ padding: '0.6rem 1.5rem', borderRadius: 8, border: 'none', background: '#3b82f6', color: '#fff', fontWeight: 600, cursor: 'pointer', opacity: (asking || readyDocs.length === 0) ? 0.6 : 1 }}>
                  {asking ? 'Thinking…' : 'Ask'}
                </button>
              </form>

              {error && <div style={{ color: '#dc2626', fontSize: '0.85rem', marginTop: '0.75rem', padding: '0.5rem', background: '#fef2f2', borderRadius: 6 }}>{error}</div>}

              {answer && (
                <div style={{ marginTop: '1.25rem' }}>
                  <div style={{ background: answer.was_refused ? '#fef2f2' : '#f0fdf4', border: `1px solid ${answer.was_refused ? '#fca5a5' : '#86efac'}`, borderRadius: 8, padding: '1rem', marginBottom: '0.75rem' }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: 600, color: answer.was_refused ? '#dc2626' : '#16a34a', marginBottom: '0.4rem' }}>
                      {answer.was_refused ? '❌ Not found in documents' : '✅ Answer'}
                    </div>
                    <p style={{ fontSize: '0.95rem', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{answer.answer}</p>
                    {answer.tokens_used && (
                      <div style={{ fontSize: '0.7rem', color: '#94a3b8', marginTop: '0.5rem' }}>
                        {answer.tokens_used} tokens · {answer.latency_ms?.toFixed(0)}ms
                        {answer.estimated_cost_usd !== undefined && ` · $${answer.estimated_cost_usd?.toFixed(5)}`}
                      </div>
                    )}
                  </div>
                  {answer.citations.length > 0 && (
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: '0.5rem', color: '#374151' }}>📎 Citations</div>
                      {answer.citations.map((c, i) => (
                        <div key={i} style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6, padding: '0.6rem 0.75rem', marginBottom: '0.4rem', fontSize: '0.82rem' }}>
                          <div style={{ fontWeight: 600, color: '#1e40af', marginBottom: '0.25rem' }}>{c.document_name}{c.page_number ? ` — page ${c.page_number}` : ''}</div>
                          <div style={{ color: '#4b5563', fontStyle: 'italic' }}>"{c.passage}"</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* History Tab */}
          {activeTab === 'history' && (
            <div style={{ background: '#fff', borderRadius: 10, border: '1px solid #e2e8f0', padding: '1.25rem' }}>
              <h3 style={{ fontWeight: 700, marginBottom: '1rem' }}>Question History ({history.length})</h3>
              {history.length === 0 ? (
                <p style={{ color: '#94a3b8', fontSize: '0.85rem' }}>No questions yet.</p>
              ) : (
                history.map(item => (
                  <div key={item.id} style={{ borderBottom: '1px solid #f1f5f9', paddingBottom: '0.75rem', marginBottom: '0.75rem' }}>
                    <div style={{ fontWeight: 600, fontSize: '0.9rem', marginBottom: '0.25rem' }}>Q: {item.question}</div>
                    <div style={{ fontSize: '0.85rem', color: item.was_refused ? '#dc2626' : '#374151', marginBottom: '0.25rem' }}>
                      {item.was_refused ? '❌ Not found' : `A: ${item.answer?.slice(0, 200)}${(item.answer?.length ?? 0) > 200 ? '…' : ''}`}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: '#94a3b8' }}>{new Date(item.created_at).toLocaleString()}{item.latency_ms ? ` · ${item.latency_ms.toFixed(0)}ms` : ''}</div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
