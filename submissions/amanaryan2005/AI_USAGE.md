# AI Usage Disclosure

> **Submission:** DocuMind — AI Knowledge Assistant
> **Author:** Aman Aryan (`amanaryan2005`)

---

## Tools Used

| Tool | Version/Model | Purpose |
|---|---|---|
| Google Antigravity (AI coding assistant) | Gemini Claude Sonnet | Architecture planning, code scaffolding, reviewing |
| GitHub Copilot | GPT-4o | Inline autocomplete in VS Code |

---

## How AI Was Used

### Architecture & Design
- Discussed RAG architecture trade-offs (pgvector vs. Qdrant, chunking strategies, embedding models)
- AI provided a comparison table; final decisions were made independently based on the constraints (free tier, single service, assessment scope)

### Code Scaffolding
- AI generated initial boilerplate for FastAPI route structure, SQLAlchemy models, and Celery task skeleton
- All generated code was reviewed, tested, and significantly modified — particularly the prompt-injection defense strategy and the chunking overlap logic

### Debugging
- Used AI to diagnose a pgvector IVFFlat index creation error (needed to insert at least 1 row before creating the index)
- Used AI to understand Gemini's `task_type` distinction between `retrieval_document` and `retrieval_query`

### Documentation
- AI helped structure DESIGN.md sections; all content and technical decisions are original
- EVALUATION.md data (metrics, experiment results) are real outputs from running the eval script

---

## What Was NOT AI-Generated

- The prompt-injection defense strategy (system prompt design + `<DOCUMENT_DATA>` framing)
- The evaluation set questions (written manually to test specific edge cases)
- The chunking overlap algorithm (written from scratch after testing naive splitting)
- All data model design (table structure, indexes, cascade deletes for embeddings)
- Security decisions (user isolation via `owner_id` on every query, no information leakage via 404)

---

## Policy Compliance

- No hosted RAG product was used (no "chat with your docs" vendor API)
- LangChain and LlamaIndex were intentionally NOT used — all pipeline code is written from scratch to ensure I can explain it line by line
- All AI-assisted decisions can be explained and defended in a live review
