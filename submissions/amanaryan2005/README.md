# DocuMind — AI Knowledge Assistant

> **Assessment:** Software Engineer Intern / AI Engineer Intern — Agnitechnologies
> **Candidate:** Aman Aryan (`amanaryan2005`)

---

| | |
|---|---|
| **Live Link** https://software-engineering-assesment.vercel.app/login
| **Demo Video** https://drive.google.com/file/d/186q0b1E7wbq-34L2ikrd8v_h25DayLCE/view?usp=sharing
| **Resume** | [`RESUME.pdf`](./RESUME.pdf) |
| **API Docs** | `https://your-deployment-url.com/docs` |

---

## Test Credentials

```
Username: reviewer
Password: reviewpass123
```
*(Pre-created account with sample documents already uploaded)*

---

## What It Does

DocuMind is a **Retrieval-Augmented Generation (RAG)** document Q&A platform. Users upload PDF or text documents; a background Celery worker extracts, chunks, and embeds them into a pgvector store. Users then ask questions in natural language and receive answers grounded exclusively in their documents, with exact passage citations.

![DocuMind Dashboard](./screenshots/dashboard.png)

---

## Architecture

```
Browser (React + Vite)
    │
    │ HTTPS / REST + JWT
    ▼
┌─────────────────────────────┐
│  FastAPI Backend             │  ← REST API, auth, rate limiting
│  /api/v1/{auth,documents,   │
│   questions,health}          │
└───────────┬─────────────────┘
            │ SQL + pgvector         │ Celery task
            ▼                        ▼
    ┌──────────────┐        ┌──────────────────┐
    │  PostgreSQL  │        │  Celery Worker   │
    │  + pgvector  │◄───────│  (ingest.py)     │
    │  (jobs,      │        │  extract→chunk   │
    │   chunks,    │        │  →embed→store    │
    │   users)     │        └────────┬─────────┘
    └──────────────┘                 │
                                     ▼
                           ┌──────────────────┐
                           │  Google Gemini   │
                           │  text-embedding  │
                           │  -004 + Flash    │
                           └──────────────────┘
                           ┌──────────────────┐
                           │  Redis           │
                           │  (Celery broker) │
                           └──────────────────┘
```

→ Full design details in [DESIGN.md](./DESIGN.md)

---

## How a Question Is Answered (Step by Step)

1. **User submits** a question via the UI (`POST /api/v1/questions`)
2. **Rate limiter** (slowapi) checks — max 10 questions/minute per IP
3. **Query embedding** — question is embedded with Gemini `text-embedding-004` (`retrieval_query` task type)
4. **Vector retrieval** — pgvector finds the top-5 most similar chunks using cosine distance, filtered to the user's own documents only
5. **LLM generation** — retrieved chunks are wrapped in `<DOCUMENT_DATA>` delimiters and sent to Gemini 1.5 Flash with a strict system prompt. Content is treated as data, never as instructions.
6. **Refusal check** — if the LLM returns "I couldn't find this in your documents", `was_refused=true`
7. **Response** — answer + citations (document name, passage, page number) + usage metrics returned
8. **History** stored in PostgreSQL for the authenticated user

---

## Tech Stack

| Component | Choice | Reason |
|---|---|---|
| Backend | FastAPI (Python 3.11) | Async, OpenAPI auto-docs, type safety |
| Auth | JWT (python-jose) + bcrypt | Stateless, industry standard |
| Document parsing | PyMuPDF | Fast PDF extraction, no external deps |
| Chunking | Recursive character splitter | Preserves paragraphs > sentences > words |
| Embeddings | Gemini text-embedding-004 | 768-dim, high quality, free tier |
| Vector store | pgvector (PostgreSQL ext.) | No extra service, ACID, cosine similarity |
| LLM | Gemini 1.5 Flash | Fast, affordable, function-calling support |
| Task queue | Celery + Redis | Persistent jobs, retries, monitoring |
| Frontend | React 18 + Vite + TypeScript | Fast dev, type safety, SPA |
| Container | Docker + Docker Compose | One-command reproducible environment |
| CI | GitHub Actions | Required; lint + test + Docker build |
| Deployment | Render.com | Free tier, PostgreSQL + Redis add-ons |

---

## Local Setup (Docker Compose)

```bash
# 1. Clone
git clone https://github.com/amanaryan2005/Software-Engineering-Assesment.git
cd Software-Engineering-Assesment/submissions/amanaryan2005

# 2. Configure
cp .env.example .env
# Edit .env — fill in GEMINI_API_KEY (free at https://aistudio.google.com/app/apikey)
# Also set a strong SECRET_KEY

# 3. Start everything
docker compose up --build

# Services:
# Frontend  → http://localhost:3000
# API       → http://localhost:8000/docs
# Health    → http://localhost:8000/health
```

---

## Running Tests

```bash
cd submissions/amanaryan2005/backend
pip install -r requirements.txt
pytest ../tests -v
```

---

## Running the Evaluation

```bash
# Requires a running DocuMind instance
cd submissions/amanaryan2005/evaluation

# Create a reviewer account first (or use the pre-created one)
python run_eval.py \
  --base-url http://localhost:8000 \
  --username reviewer \
  --password reviewpass123
```

See [EVALUATION.md](./EVALUATION.md) for results and analysis.

---

## Deployment

All services deployed on **Render.com**:

| Service | Type | URL |
|---|---|---|
| Backend + Worker | Web Service | `https://your-app.onrender.com` |
| PostgreSQL | Managed DB | Internal |
| Redis | Managed Redis | Internal |
| Frontend | Static Site | `https://your-frontend.onrender.com` |

**Note:** Free tier services sleep after 15 minutes of inactivity. First request may take ~30 seconds to wake.

---

## Known Limitations and Next Steps

- **Polling, not streaming** — frontend polls; SSE/WebSocket would improve UX
- **No conversation memory** — each question is independent
- **Basic chunking** — could use semantic chunking or sliding-window strategies
- **GIL-limited worker** — for production, use multiple worker processes or async with asyncio
- **No re-ranking** — adding a cross-encoder re-ranker would improve retrieval precision
