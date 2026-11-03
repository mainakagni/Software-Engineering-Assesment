# AI Usage Disclosure

**Author**: Kalash Singh Chouhan  
**Submission**: `submissions/kalashsingh18`  
**Date**: October 2026  

---

In compliance with Section 7 (E3) of the assessment brief, this document details the AI tools utilized during the design and development of **DocuMind**:

### 1. Tools Used
- **Antigravity AI Assistant / Gemini 3.8 Flash**: Utilized as an interactive pair-programming and scaffolding partner.

### 2. What AI Was Used For
- **Boilerplate Scaffolding**: Fast generation of initial Pydantic schemas, SQLAlchemy relational models, and Docker Compose configurations.
- **Frontend Template Structure**: Rapid layout generation for the React Vite SPA components and modern CSS design tokens.
- **Evaluation Dataset Drafting**: Generating realistic sample policy documentation and test questions covering boundary conditions.

### 3. Decisions & Code Driven by the Author
- **Architecture & System Design**: Selection of PostgreSQL + `pgvector` for unified relational and vector storage rather than separate databases, ensuring single-transaction cascade deletion and tenant filtering.
- **Decoupled Asynchronous Processing**: Architecting the Celery background worker pattern with Redis to guarantee immediate HTTP 202 responses on upload while processing documents asynchronously.
- **Strict Grounding & Prompt Injection Defense**: Authoring the XML-boundary prompt structure and explicit refusal heuristics (*"I could not find an answer in your uploaded documents."*) to prevent hallucinations and jailbreak attempts.
- **Multi-Tenant Isolation**: Enforcing strict `user_id` filtering across all database queries and vector similarity searches.

All design decisions, trade-offs, and codebase mechanics are thoroughly understood and will be demonstrated during the live code review.
