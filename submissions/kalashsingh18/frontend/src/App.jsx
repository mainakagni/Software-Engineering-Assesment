import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  FileText, Upload, Trash2, CheckCircle2, Clock, AlertCircle,
  Send, RefreshCw, LogOut, ShieldCheck, Sparkles, Database,
  Layers, ExternalLink, HelpCircle, Copy, Check, MessageSquare,
  Zap, ArrowRight, CornerDownLeft, SlidersHorizontal, BookOpen,
  Search, X, FileUp, Lightbulb, Eye, EyeOff, Bot, User as UserIcon
} from 'lucide-react';

const API_BASE = '/api/v1';

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('documind_token') || '');
  const [user, setUser] = useState(null);
  const [authMode, setAuthMode] = useState('login');
  const [authForm, setAuthForm] = useState({ email: '', username: '', password: '' });
  const [authError, setAuthError] = useState('');
  const [authLoading, setAuthLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [authTouched, setAuthTouched] = useState({ email: false, username: false, password: false });
  const [fieldErrors, setFieldErrors] = useState({ email: '', username: '', password: '' });

  const [documents, setDocuments] = useState([]);
  const [selectedDocIds, setSelectedDocIds] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState([]);
  const [uploadError, setUploadError] = useState('');
  const [dragOver, setDragOver] = useState(false);

  const [chatHistory, setChatHistory] = useState([]);
  const [question, setQuestion] = useState('');
  const [asking, setAsking] = useState(false);
  const [healthStatus, setHealthStatus] = useState('healthy');
  const [copiedIdx, setCopiedIdx] = useState(null);
  const [followUpSuggestions, setFollowUpSuggestions] = useState([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);

  // Semantic search
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const searchTimeoutRef = useRef(null);

  const fileInputRef = useRef(null);
  const chatEndRef = useRef(null);
  const dropZoneRef = useRef(null);

  useEffect(() => {
    fetch('/health')
      .then(r => r.json())
      .then(d => setHealthStatus(d.status))
      .catch(() => setHealthStatus('down'));
  }, []);

  useEffect(() => {
    if (token) {
      fetchUser();
      fetchDocuments();
      fetchHistory();
    } else {
      setUser(null);
      setDocuments([]);
      setChatHistory([]);
    }
  }, [token]);

  useEffect(() => {
    if (!token) return;
    const hasPending = documents.some(d => d.status === 'queued' || d.status === 'processing');
    if (!hasPending) return;

    const interval = setInterval(() => {
      fetchDocuments();
    }, 4000);

    return () => clearInterval(interval);
  }, [documents, token]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory]);

  const fetchUser = async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setUser(data);
      } else {
        handleLogout();
      }
    } catch {
      handleLogout();
    }
  };

  const fetchDocuments = async () => {
    try {
      const res = await fetch(`${API_BASE}/documents`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setDocuments(data);
      }
    } catch (err) {
      console.error("Failed to load documents", err);
    }
  };

  const fetchHistory = async () => {
    try {
      const res = await fetch(`${API_BASE}/questions/history`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        const formatted = data.map(item => ({
          question: item.question,
          answer: item.answer,
          citations: item.citations || [],
          usage: {
            latency_ms: item.latency_ms,
            total_tokens: (item.prompt_tokens || 0) + (item.completion_tokens || 0),
            estimated_cost_usd: item.estimated_cost
          },
          grounded: !item.answer.includes("could not find an answer in your uploaded documents")
        }));
        setChatHistory(formatted);
      }
    } catch (err) {
      console.error("Failed to load history", err);
    }
  };

  const validateField = (field, value, mode = authMode) => {
    let error = '';
    const val = (value || '').trim();

    if (field === 'email' && mode === 'signup') {
      if (!val) {
        error = 'Email address is required';
      } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val)) {
        error = 'Please enter a valid email address (e.g. name@company.com)';
      }
    } else if (field === 'username') {
      if (!val) {
        error = mode === 'signup' ? 'Username is required' : 'Username or email is required';
      } else if (mode === 'signup') {
        if (val.length < 3) {
          error = 'Username must be at least 3 characters';
        } else if (val.length > 50) {
          error = 'Username cannot exceed 50 characters';
        } else if (!/^[a-zA-Z0-9_]+$/.test(val)) {
          error = 'Only letters, numbers, and underscores allowed';
        }
      }
    } else if (field === 'password') {
      if (!val) {
        error = 'Password is required';
      } else if (mode === 'signup' && val.length < 6) {
        error = 'Password must be at least 6 characters long';
      }
    }
    return error;
  };

  const handleFieldChange = (field, value) => {
    setAuthForm(prev => ({ ...prev, [field]: value }));
    if (authTouched[field]) {
      const err = validateField(field, value, authMode);
      setFieldErrors(prev => ({ ...prev, [field]: err }));
    }
    if (authError) setAuthError('');
  };

  const handleFieldBlur = (field) => {
    setAuthTouched(prev => ({ ...prev, [field]: true }));
    const err = validateField(field, authForm[field], authMode);
    setFieldErrors(prev => ({ ...prev, [field]: err }));
  };

  const handleSwitchAuthMode = (mode) => {
    setAuthMode(mode);
    setAuthError('');
    setFieldErrors({ email: '', username: '', password: '' });
    setAuthTouched({ email: false, username: false, password: false });
  };

  const getPasswordStrength = (pass) => {
    if (!pass) return { score: 0, label: '', color: '#64748b' };
    let score = 0;
    if (pass.length >= 6) score += 1;
    if (pass.length >= 8) score += 1;
    if (/[A-Z]/.test(pass) && /[0-9]/.test(pass)) score += 1;
    if (/[^A-Za-z0-9]/.test(pass)) score += 1;

    if (score <= 1) return { score: 1, label: 'Weak', color: '#f43f5e' };
    if (score === 2) return { score: 2, label: 'Fair', color: '#f59e0b' };
    if (score >= 3) return { score: 3, label: 'Strong', color: '#10b981' };
    return { score: 1, label: 'Weak', color: '#f43f5e' };
  };

  const handleAuth = async (e) => {
    e.preventDefault();
    setAuthError('');

    const newErrors = {
      email: authMode === 'signup' ? validateField('email', authForm.email, 'signup') : '',
      username: validateField('username', authForm.username, authMode),
      password: validateField('password', authForm.password, authMode)
    };

    setAuthTouched({ email: true, username: true, password: true });
    setFieldErrors(newErrors);

    if (newErrors.email || newErrors.username || newErrors.password) {
      return;
    }

    setAuthLoading(true);

    const endpoint = authMode === 'signup' ? `${API_BASE}/auth/signup` : `${API_BASE}/auth/login`;
    const payload = authMode === 'signup'
      ? authForm
      : { username_or_email: authForm.username || authForm.email, password: authForm.password };

    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) {
        let msg = 'Authentication failed';
        if (typeof data.detail === 'string') {
          msg = data.detail;
        } else if (Array.isArray(data.detail)) {
          msg = data.detail.map(d => d.msg || `${d.loc?.join('.')}: invalid`).join(', ');
        }
        throw new Error(msg);
      }
      localStorage.setItem('documind_token', data.access_token);
      setToken(data.access_token);
      setUser(data.user);
    } catch (err) {
      setAuthError(err.message);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('documind_token');
    setToken('');
    setUser(null);
  };

  // Multi-file upload handler
  const uploadSingleFile = async (file, idx, totalFiles) => {
    const formData = new FormData();
    formData.append('file', file);

    setUploadProgress(prev => {
      const updated = [...prev];
      updated[idx] = { name: file.name, status: 'uploading', progress: 0 };
      return updated;
    });

    try {
      const res = await fetch(`${API_BASE}/documents/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Upload failed');
      }
      setUploadProgress(prev => {
        const updated = [...prev];
        updated[idx] = { name: file.name, status: 'done', progress: 100 };
        return updated;
      });
    } catch (err) {
      setUploadProgress(prev => {
        const updated = [...prev];
        updated[idx] = { name: file.name, status: 'error', progress: 0, error: err.message };
        return updated;
      });
    }
  };

  const handleMultiUpload = async (files) => {
    if (!files || files.length === 0) return;

    const validFiles = Array.from(files).filter(f => {
      const ext = f.name.split('.').pop()?.toLowerCase();
      return ['pdf', 'txt', 'md'].includes(ext);
    });

    if (validFiles.length === 0) {
      setUploadError('Only PDF, TXT, and MD files are supported.');
      return;
    }

    setUploading(true);
    setUploadError('');
    setUploadProgress(validFiles.map(f => ({ name: f.name, status: 'pending', progress: 0 })));

    // Upload all files concurrently
    await Promise.all(validFiles.map((file, idx) => uploadSingleFile(file, idx, validFiles.length)));

    fetchDocuments();
    setUploading(false);
    // Clear progress after 3 seconds
    setTimeout(() => setUploadProgress([]), 3000);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleUpload = async (e) => {
    const files = e.target.files;
    await handleMultiUpload(files);
  };

  // Drag and drop handlers
  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  }, []);

  const handleDrop = useCallback(async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    await handleMultiUpload(e.dataTransfer.files);
  }, [token]);

  // Semantic search with debounce
  const performSearch = async (query) => {
    if (!query.trim() || query.length < 2) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    try {
      const res = await fetch(`${API_BASE}/documents/search`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ query })
      });
      if (res.ok) {
        const data = await res.json();
        setSearchResults(data.results || []);
      }
    } catch (err) {
      console.error('Search failed', err);
    } finally {
      setSearching(false);
    }
  };

  const handleSearchInput = (val) => {
    setSearchQuery(val);
    if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
    searchTimeoutRef.current = setTimeout(() => performSearch(val), 400);
  };

  // Fetch follow-up suggestions
  const fetchSuggestions = async (q, a) => {
    if (!a || a.includes('could not find an answer')) return;
    setLoadingSuggestions(true);
    try {
      const res = await fetch(`${API_BASE}/questions/suggestions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ question: q, answer: a })
      });
      if (res.ok) {
        const data = await res.json();
        setFollowUpSuggestions(data.suggestions || []);
      }
    } catch (err) {
      console.error('Suggestions failed', err);
    } finally {
      setLoadingSuggestions(false);
    }
  };

  const handleDeleteDoc = async (id, e) => {
    e.stopPropagation();
    if (!confirm('Delete document and purge all associated vector embeddings?')) return;

    try {
      const res = await fetch(`${API_BASE}/documents/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setDocuments(docs => docs.filter(d => d.id !== id));
        setSelectedDocIds(ids => ids.filter(i => i !== id));
      }
    } catch (err) {
      console.error('Delete failed', err);
    }
  };

  const toggleSelectDoc = (id) => {
    setSelectedDocIds(prev =>
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    );
  };

  const handleSelectAllDocs = () => {
    if (selectedDocIds.length === documents.length) {
      setSelectedDocIds([]);
    } else {
      setSelectedDocIds(documents.map(d => d.id));
    }
  };

  const sendQuery = async (queryText) => {
    if (!queryText.trim() || asking) return;

    setAsking(true);
    setQuestion('');
    setFollowUpSuggestions([]);

    const tempQ = {
      question: queryText,
      answer: '',
      citations: [],
      usage: null,
      loading: true,
      streaming: true
    };
    setChatHistory(prev => [...prev, tempQ]);

    let finalAnswer = '';

    try {
      // Build conversation history from the last 5 completed turns
      const recentHistory = [];
      const completedTurns = chatHistory.filter(t => t.answer && !t.loading && !t.streaming);
      const turnsToSend = completedTurns.slice(-5);
      for (const turn of turnsToSend) {
        recentHistory.push({ role: 'user', content: turn.question });
        recentHistory.push({ role: 'assistant', content: turn.answer });
      }

      const res = await fetch(`${API_BASE}/questions/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          question: queryText,
          document_ids: selectedDocIds.length > 0 ? selectedDocIds : null,
          chat_history: recentHistory.length > 0 ? recentHistory : null
        })
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || 'Streaming connection failed');
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let streamedAnswer = '';
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep last incomplete line

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === 'token') {
                streamedAnswer += event.token;
                setChatHistory(prev => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last) {
                    last.answer = streamedAnswer;
                    last.loading = false;
                  }
                  return updated;
                });
              } else if (event.type === 'done') {
                finalAnswer = streamedAnswer;
                setChatHistory(prev => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last) {
                    last.citations = event.citations || [];
                    last.usage = event.usage || null;
                    last.streaming = false;
                    last.loading = false;
                  }
                  return updated;
                });
              }
            } catch (e) {
              // Ignore partial JSON
            }
          }
        }
      }

      // Fetch follow-up suggestions after answer is complete
      if (finalAnswer) {
        fetchSuggestions(queryText, finalAnswer);
      }
    } catch (err) {
      setChatHistory(prev => [
        ...prev.slice(0, -1),
        {
          question: queryText,
          answer: `Error: ${err.message}`,
          citations: [],
          usage: null,
          grounded: false,
          streaming: false,
          loading: false
        }
      ]);
    } finally {
      setAsking(false);
    }
  };

  const handleAsk = (e) => {
    e.preventDefault();
    sendQuery(question);
  };

  const fillTestCredentials = () => {
    setAuthMode('login');
    setAuthForm({
      email: 'reviewer@documind.ai',
      username: 'demo_reviewer',
      password: 'DocuMindReviewer2026!'
    });
  };

  const copyToClipboard = (text, idx) => {
    navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  const renderStatusPill = (status, errorMsg) => {
    switch (status) {
      case 'ready':
        return <span className="status-pill ready"><CheckCircle2 size={12} /> Ready</span>;
      case 'processing':
        return <span className="status-pill processing"><RefreshCw size={12} className="spin" /> Ingesting</span>;
      case 'queued':
        return <span className="status-pill queued"><Clock size={12} /> Queued</span>;
      case 'failed':
        return <span className="status-pill failed" title={errorMsg || 'Failed'}><AlertCircle size={12} /> Failed</span>;
      default:
        return <span className="status-pill">{status}</span>;
    }
  };

  // Helper to render markdown-like text formatting cleanly
  const renderFormattedAnswer = (text) => {
    // If refusal message
    if (text.includes("could not find an answer in your uploaded documents")) {
      return (
        <div className="answer-body refusal-alert">
          ⚠️ <strong>Grounded Refusal:</strong> {text}
        </div>
      );
    }

    // If out-of-scope / unrelated message
    if (text.includes("not related to your uploaded documents")) {
      return (
        <div className="answer-body refusal-alert" style={{ borderColor: 'rgba(234, 179, 8, 0.4)', background: 'rgba(234, 179, 8, 0.08)' }}>
          ℹ️ <strong>Out of Scope:</strong> {text}
        </div>
      );
    }

    const lines = text.split('\n');
    return (
      <div className="answer-body">
        {lines.map((line, idx) => {
          if (!line.trim()) return <div key={idx} style={{ height: '8px' }} />;

          // Process bold markers
          const parts = line.split(/(\*\*.*?\*\*)/g);
          const renderedLine = parts.map((part, pIdx) => {
            if (part.startsWith('**') && part.endsWith('**')) {
              return <strong key={pIdx}>{part.slice(2, -2)}</strong>;
            }
            return part;
          });

          // Check if bullet point
          if (line.trim().startsWith('* ') || line.trim().startsWith('- ')) {
            return (
              <div key={idx} style={{ display: 'flex', gap: '8px', marginLeft: '12px', marginTop: '4px' }}>
                <span style={{ color: '#06b6d4' }}>•</span>
                <span>{renderedLine}</span>
              </div>
            );
          }

          return <p key={idx} style={{ marginBottom: '6px' }}>{renderedLine}</p>;
        })}
      </div>
    );
  };

  return (
    <div className="app-container">
      {/* Top Navbar */}
      <header className="app-header">
        <div className="brand-wrapper">
          <div className="brand-logo">
            <Sparkles size={22} />
          </div>
          <div>
            <div className="brand-title">DocuMind</div>
            <div className="brand-subtitle">Enterprise Grounded AI Knowledge Assistant</div>
          </div>
        </div>

        <div className="header-actions">
          <div className="badge-pill healthy" title="System Diagnostics">
            <div className="pulse-dot" />
            <span>Systems {healthStatus}</span>
          </div>

          {user && (
            <>
              <div className="user-chip">
                <div className="user-avatar">{user.username.charAt(0).toUpperCase()}</div>
                <span>{user.username}</span>
              </div>
              <button onClick={handleLogout} className="btn-logout" title="Log out">
                <LogOut size={14} /> Exit
              </button>
            </>
          )}
        </div>
      </header>

      {/* Main View */}
      {!token ? (
        <div className="auth-wrapper">
          <div className="auth-card">
            <div className="auth-header">
              <div className="auth-title">Welcome to DocuMind</div>
              <div className="auth-subtitle">Sign in to search across company knowledge with verified citations</div>
            </div>

            <div className="auth-tabs">
              <button
                className={`auth-tab ${authMode === 'login' ? 'active' : ''}`}
                onClick={() => handleSwitchAuthMode('login')}
              >
                Sign In
              </button>
              <button
                className={`auth-tab ${authMode === 'signup' ? 'active' : ''}`}
                onClick={() => handleSwitchAuthMode('signup')}
              >
                Sign Up
              </button>
            </div>

            {authError && (
              <div className="auth-error-banner">
                <AlertCircle size={16} style={{ flexShrink: 0, marginTop: '1px', color: '#f43f5e' }} />
                <span className="banner-text">{authError}</span>
                <button className="btn-close-banner" onClick={() => setAuthError('')} title="Dismiss">
                  <X size={14} />
                </button>
              </div>
            )}

            <form onSubmit={handleAuth} noValidate>
              {authMode === 'signup' && (
                <div className="form-group">
                  <label className="form-label">Email Address</label>
                  <div className="form-input-wrapper">
                    <input
                      id="auth-email"
                      type="email"
                      autoComplete="email"
                      className={`form-input${authTouched.email && fieldErrors.email ? ' is-invalid' : authTouched.email && !fieldErrors.email && authForm.email ? ' is-valid' : ''}`}
                      value={authForm.email}
                      onChange={e => handleFieldChange('email', e.target.value)}
                      onBlur={() => handleFieldBlur('email')}
                      placeholder="name@company.com"
                    />
                    {authTouched.email && (
                      <span className="input-feedback-icon" style={{ pointerEvents: 'none' }}>
                        {fieldErrors.email
                          ? <AlertCircle size={15} color="#f43f5e" />
                          : <CheckCircle2 size={15} color="#10b981" />
                        }
                      </span>
                    )}
                  </div>
                  {authTouched.email && fieldErrors.email && (
                    <div className="field-error-msg">
                      <AlertCircle size={12} />
                      {fieldErrors.email}
                    </div>
                  )}
                </div>
              )}

              <div className="form-group">
                <label className="form-label">{authMode === 'signup' ? 'Username' : 'Username or Email'}</label>
                <div className="form-input-wrapper">
                  <input
                    id="auth-username"
                    type="text"
                    autoComplete={authMode === 'signup' ? 'username' : 'username'}
                    className={`form-input${authTouched.username && fieldErrors.username ? ' is-invalid' : authTouched.username && !fieldErrors.username && authForm.username ? ' is-valid' : ''}`}
                    value={authForm.username}
                    onChange={e => handleFieldChange('username', e.target.value)}
                    onBlur={() => handleFieldBlur('username')}
                    placeholder={authMode === 'signup' ? 'e.g. john_doe (min 3 chars)' : 'Your username or email'}
                  />
                  {authTouched.username && (
                    <span className="input-feedback-icon" style={{ pointerEvents: 'none' }}>
                      {fieldErrors.username
                        ? <AlertCircle size={15} color="#f43f5e" />
                        : <CheckCircle2 size={15} color="#10b981" />
                      }
                    </span>
                  )}
                </div>
                {authTouched.username && fieldErrors.username && (
                  <div className="field-error-msg">
                    <AlertCircle size={12} />
                    {fieldErrors.username}
                  </div>
                )}
                {authMode === 'signup' && !fieldErrors.username && (
                  <div className="field-hint-msg">Letters, numbers and underscores only · 3–50 characters</div>
                )}
              </div>

              <div className="form-group">
                <label className="form-label">Password</label>
                <div className="form-input-wrapper">
                  <input
                    id="auth-password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete={authMode === 'signup' ? 'new-password' : 'current-password'}
                    className={`form-input${authTouched.password && fieldErrors.password ? ' is-invalid' : authTouched.password && !fieldErrors.password && authForm.password ? ' is-valid' : ''}`}
                    value={authForm.password}
                    onChange={e => handleFieldChange('password', e.target.value)}
                    onBlur={() => handleFieldBlur('password')}
                    placeholder={authMode === 'signup' ? 'Min 6 characters' : '••••••••'}
                    style={{ paddingRight: '52px' }}
                  />
                  <button
                    type="button"
                    className="password-toggle-btn"
                    style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)' }}
                    onClick={() => setShowPassword(p => !p)}
                    tabIndex={-1}
                    title={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
                {authTouched.password && fieldErrors.password && (
                  <div className="field-error-msg">
                    <AlertCircle size={12} />
                    {fieldErrors.password}
                  </div>
                )}
                {authMode === 'signup' && authForm.password && (() => {
                  const strength = getPasswordStrength(authForm.password);
                  return (
                    <div className="password-strength-container">
                      <div className="strength-bars">
                        {[1, 2, 3].map(lvl => (
                          <div
                            key={lvl}
                            className="strength-bar"
                            style={{ backgroundColor: strength.score >= lvl ? strength.color : undefined }}
                          />
                        ))}
                      </div>
                      <div className="strength-meta">
                        <span>{strength.label && `Password strength: `}<strong style={{ color: strength.color }}>{strength.label}</strong></span>
                        <span style={{ color: '#64748b' }}>min 6 chars</span>
                      </div>
                    </div>
                  );
                })()}
              </div>

              <button
                type="submit"
                id="auth-submit-btn"
                className="btn-send"
                style={{ width: '100%', height: '48px', justifyContent: 'center', marginTop: '16px', gap: '8px', borderRadius: '12px' }}
                disabled={authLoading}
              >
                {authLoading
                  ? <><RefreshCw size={15} className="spin" /> Verifying...</>
                  : <>{authMode === 'signup' ? 'Create Account' : 'Sign In'} <ArrowRight size={16} /></>
                }
              </button>
            </form>
          </div>
        </div>
      ) : (
        <div className="dashboard-grid">
          {/* Left Column: Document Management Hub */}
          <section className="panel">
            <div className="panel-header">
              <div className="panel-title">
                <Database size={18} color="#818cf8" />
                <span>Knowledge Base</span>
                <span className="panel-badge">{documents.length}</span>
              </div>
              <button
                onClick={fetchDocuments}
                className="btn-action-icon"
                title="Refresh Documents"
              >
                <RefreshCw size={15} />
              </button>
            </div>

            {/* Drag & Drop Upload Zone */}
            <div
              className="upload-card"
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                type="file"
                ref={fileInputRef}
                style={{ display: 'none' }}
                accept=".pdf,.txt,.md"
                onChange={handleUpload}
              />
              <div className="upload-icon-wrapper">
                <Upload size={22} />
              </div>
              <div className="upload-text-main">
                {uploading ? 'Ingesting & Chunking...' : 'Upload Document'}
              </div>
              <div className="upload-text-sub">PDF, Markdown or Plain Text (up to 25MB)</div>
            </div>

            {uploadError && (
              <div style={{ color: '#fb7185', fontSize: '0.8rem', padding: '0 20px 12px' }}>
                ⚠️ {uploadError}
              </div>
            )}

            {/* Document Controls */}
            {documents.length > 0 && (
              <div className="doc-controls">
                <span>Select docs to restrict query:</span>
                <button onClick={handleSelectAllDocs}>
                  {selectedDocIds.length === documents.length ? 'Clear all' : 'Select all'}
                </button>
              </div>
            )}

            {/* Document List */}
            <div className="document-list">
              {documents.length === 0 ? (
                <div style={{ textAlign: 'center', color: '#64748b', fontSize: '0.88rem', padding: '40px 16px' }}>
                  <BookOpen size={32} style={{ margin: '0 auto 12px', opacity: 0.4 }} />
                  <div>No documents uploaded yet.</div>
                  <div style={{ fontSize: '0.78rem', marginTop: '4px' }}>Upload a policy handbook or manual above.</div>
                </div>
              ) : (
                documents.map(doc => {
                  const isSelected = selectedDocIds.includes(doc.id);
                  const ext = doc.filename.split('.').pop()?.toUpperCase() || 'DOC';
                  return (
                    <div
                      key={doc.id}
                      className={`doc-item ${isSelected ? 'selected' : ''}`}
                      onClick={() => toggleSelectDoc(doc.id)}
                      title="Click to toggle filter for questions"
                    >
                      <div className="doc-left">
                        <div className="doc-type-icon">{ext}</div>
                        <div className="doc-details">
                          <div className="doc-name">{doc.filename}</div>
                          <div className="doc-meta">
                            <span>{(doc.file_size / 1024).toFixed(1)} KB</span>
                            <span>•</span>
                            {renderStatusPill(doc.status, doc.error_message)}
                          </div>
                        </div>
                      </div>
                      <button
                        onClick={(e) => handleDeleteDoc(doc.id, e)}
                        className="btn-action-icon"
                        title="Delete document and purge embeddings"
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </section>

          {/* Right Column: Grounded AI Assistant */}
          <section className="panel chat-container">
            <div className="panel-header">
              <div className="panel-title">
                <Layers size={18} color="#06b6d4" />
                <span>Grounded Q&A Console</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                {chatHistory.length > 0 && (
                  <button
                    onClick={() => setChatHistory([])}
                    style={{ background: 'transparent', border: 'none', color: '#94a3b8', fontSize: '0.8rem', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px' }}
                  >
                    Clear chat
                  </button>
                )}
              </div>
            </div>

            {/* Scope Indicator Banner */}
            <div className="scope-banner">
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <SlidersHorizontal size={14} />
                <span>
                  {selectedDocIds.length > 0
                    ? `Searching across ${selectedDocIds.length} selected document(s)`
                    : `Searching across all ready documents (${documents.filter(d => d.status === 'ready').length} indexed)`}
                </span>
              </div>
              {selectedDocIds.length > 0 && (
                <button
                  onClick={() => setSelectedDocIds([])}
                  style={{ background: 'transparent', border: 'none', color: '#67e8f9', cursor: 'pointer', fontSize: '0.75rem', textDecoration: 'underline' }}
                >
                  Search all instead
                </button>
              )}
            </div>

            {/* Chat Stream */}
            <div className="chat-history">
              {chatHistory.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-state-icon-box">
                    <MessageSquare size={32} />
                  </div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#f8fafc' }}>
                    Ask DocuMind Anything
                  </div>
                  <div style={{ maxWidth: '480px', fontSize: '0.9rem', color: '#94a3b8', lineHeight: 1.6 }}>
                    Responses are synthesized strictly from retrieved document chunks and cited with exact page numbers. Unanswerable questions are rejected honestly.
                  </div>

                  <div className="suggestions-box">
                    <div style={{ fontSize: '0.8rem', fontWeight: 700, textTransform: 'uppercase', color: '#64748b', letterSpacing: '0.5px' }}>
                      Suggested Questions
                    </div>
                    <div
                      className="suggestion-chip"
                      onClick={() => sendQuery("How many days of paid annual vacation leave do employees get?")}
                    >
                      <span>🌴 How many days of annual vacation leave do employees get?</span>
                      <CornerDownLeft size={14} color="#818cf8" />
                    </div>
                    <div
                      className="suggestion-chip"
                      onClick={() => sendQuery("What is the home office setup stipend and monthly internet reimbursement?")}
                    >
                      <span>💻 What is the home office setup stipend and monthly internet allowance?</span>
                      <CornerDownLeft size={14} color="#818cf8" />
                    </div>
                    <div
                      className="suggestion-chip"
                      onClick={() => sendQuery("What are core collaboration hours across engineering teams?")}
                    >
                      <span>⏰ What are core collaboration hours across engineering teams?</span>
                      <CornerDownLeft size={14} color="#818cf8" />
                    </div>
                  </div>
                </div>
              ) : (
                chatHistory.map((item, idx) => {
                  const isRefusal = item.answer && item.answer.includes('could not find an answer');
                  const isOutOfScope = item.answer && item.answer.includes('not related to your uploaded documents');
                  const isComparative = item.answer && (item.answer.includes('comparative breakdown') || item.answer.includes('comparing this with'));
                  const responseTag = isRefusal ? { cls: 'refusal', label: '⚠ Not Found' }
                    : isOutOfScope ? { cls: 'out-of-scope', label: 'ℹ Out of Scope' }
                    : isComparative ? { cls: 'comparison', label: '⇄ Synthesis' }
                    : { cls: 'grounded', label: '✓ Grounded' };

                  return (
                    <div key={idx} className="chat-turn">
                      {/* User Question Row */}
                      <div className="user-message-row">
                        <div className="user-bubble">{item.question}</div>
                        {user && (
                          <div className="user-avatar-chip" title={user.username}>
                            {user.username.charAt(0).toUpperCase()}
                          </div>
                        )}
                      </div>

                      {/* Assistant Response Card */}
                      <div className="assistant-card">
                        <div className="assistant-top">
                          <div className="assistant-meta-left">
                            <div className="assistant-avatar">
                              <Sparkles size={13} />
                            </div>
                            <span className="assistant-name">DocuMind</span>
                            {!item.loading && item.answer && (
                              <span className={`response-tag ${responseTag.cls}`}>{responseTag.label}</span>
                            )}
                          </div>
                          <button
                            onClick={() => copyToClipboard(item.answer, idx)}
                            className="btn-copy"
                            title="Copy Answer"
                            disabled={!item.answer}
                          >
                            {copiedIdx === idx ? <Check size={12} color="#10b981" /> : <Copy size={12} />}
                            <span>{copiedIdx === idx ? 'Copied!' : 'Copy'}</span>
                          </button>
                        </div>

                      {/* Answer Content */}
                      {item.loading && !item.answer ? (
                        <div className="typing-box">
                          <div className="typing-dots">
                            <div className="typing-dot" />
                            <div className="typing-dot" />
                            <div className="typing-dot" />
                          </div>
                          <span>Searching knowledge base &amp; synthesizing response...</span>
                        </div>
                      ) : (
                        <div className="streamed-answer-box">
                          {renderFormattedAnswer(item.answer)}
                          {item.streaming && <span className="streaming-cursor">▍</span>}
                        </div>
                      )}

                      {/* Source Citations */}
                      {item.citations && item.citations.length > 0 && (
                        <div className="citations-wrapper">
                          <div className="citations-title">
                            <ShieldCheck size={14} /> Source Citations ({item.citations.length})
                          </div>
                          {item.citations.map((cite, cIdx) => (
                            <div key={cIdx} className="citation-card">
                              <div className="citation-header-row">
                                <span className="citation-doc-badge">
                                  📄 {cite.document_name}
                                </span>
                                <span className="citation-page-badge">
                                  Page {cite.page_number}
                                </span>
                              </div>
                              <div className="citation-snippet">
                                "{cite.passage}"
                              </div>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Performance & Token Metrics */}
                      {item.usage && !item.loading && (
                        <div className="metrics-row">
                          <div className="metrics-group">
                            <span className="metric-item">⚡ {Math.round(item.usage.latency_ms)} ms</span>
                            <span className="metric-item">📊 {item.usage.total_tokens || 0} tokens</span>
                            <span className="metric-item">💎 ${Number(item.usage.estimated_cost_usd || 0).toFixed(6)}</span>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                  );
                })
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Bottom Question Input */}
            <form onSubmit={handleAsk} className="chat-input-bar">
              <div className="chat-input-wrapper">
                <input
                  id="chat-question-input"
                  type="text"
                  className="chat-input"
                  placeholder="Ask anything about your documents — general or specific..."
                  value={question}
                  onChange={e => setQuestion(e.target.value)}
                  disabled={asking}
                />
                {!asking && question.trim() === '' && (
                  <span className="chat-kbd-hint">Enter ↵</span>
                )}
              </div>
              <button
                type="submit"
                id="chat-send-btn"
                className="btn-send"
                disabled={asking || !question.trim()}
              >
                {asking ? <RefreshCw size={16} className="spin" /> : <Send size={16} />}
                <span>{asking ? 'Thinking...' : 'Ask'}</span>
              </button>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}

