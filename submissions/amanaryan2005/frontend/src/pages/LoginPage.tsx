import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { login as apiLogin } from '../api/client'
import { useAuth } from '../contexts/AuthContext'

const s: Record<string, React.CSSProperties> = {
  page: { minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f1f5f9' },
  card: { background: '#fff', borderRadius: 12, padding: '2rem', width: '100%', maxWidth: 400, boxShadow: '0 4px 24px rgba(0,0,0,0.08)' },
  title: { fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.25rem', color: '#0f172a' },
  sub: { color: '#64748b', marginBottom: '1.5rem', fontSize: '0.9rem' },
  label: { display: 'block', fontSize: '0.8rem', fontWeight: 600, color: '#374151', marginBottom: '0.25rem' },
  input: { width: '100%', padding: '0.6rem 0.75rem', border: '1px solid #d1d5db', borderRadius: 8, fontSize: '0.9rem', marginBottom: '0.75rem', outline: 'none' },
  btn: { width: '100%', padding: '0.7rem', borderRadius: 8, border: 'none', background: '#3b82f6', color: '#fff', fontWeight: 600, fontSize: '0.95rem', cursor: 'pointer' },
  error: { color: '#dc2626', fontSize: '0.8rem', marginBottom: '0.75rem', padding: '0.5rem', background: '#fef2f2', borderRadius: 6 },
  link: { textAlign: 'center' as const, marginTop: '1rem', fontSize: '0.85rem', color: '#64748b' },
}

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await apiLogin(username, password)
      await login(res.data.access_token)
      navigate('/')
    } catch (err: unknown) {
      const msg = (err as {response?: {data?: {detail?: string}}})?.response?.data?.detail ?? 'Login failed'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={s.page}>
      <div style={s.card}>
        <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>🧠</div>
        <h1 style={s.title}>DocuMind</h1>
        <p style={s.sub}>Sign in to your account</p>
        <form onSubmit={handleSubmit}>
          {error && <div style={s.error}>{error}</div>}
          <label style={s.label}>Username or Email</label>
          <input style={s.input} value={username} onChange={e => setUsername(e.target.value)} required autoFocus />
          <label style={s.label}>Password</label>
          <input style={s.input} type="password" value={password} onChange={e => setPassword(e.target.value)} required />
          <button style={{ ...s.btn, opacity: loading ? 0.7 : 1 }} type="submit" disabled={loading}>
            {loading ? 'Signing in…' : 'Sign In'}
          </button>
        </form>
        <div style={s.link}>Don't have an account? <Link to="/signup" style={{ color: '#3b82f6' }}>Sign up</Link></div>
      </div>
    </div>
  )
}
