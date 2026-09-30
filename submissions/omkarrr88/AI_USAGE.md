# AI usage

I built this project with Claude Code (Anthropic's AI coding assistant) doing most of the hands-on work.

**What I decided**

- The model provider (Gemini's free tier) and the host (Render's free plan).
- How the work was run: one GitHub issue per feature, a feature branch and a pull request for each, and
  nothing merged into `main` except through a pull request that I reviewed and merged myself.

**What the assistant did**

- Proposed the design in `DESIGN.md` before any code was written: Postgres with pgvector for data, vectors,
  the job queue and rate limits, a worker process, and two refusal gates in front of every answer.
- Wrote the backend, the web UI, the tests, the Docker and CI setup, and the Render blueprint.
- Built the evaluation set from public documents and wrote the harness that scores it.
- Ran review passes on each change (correctness, security, tests) and fixed the findings it could confirm.
- Drafted the documentation and the pull request descriptions.

**How the work was checked**

- The tests run in CI on every pull request, with fakes for Gemini: unit tests, integration tests against a
  real Postgres with pgvector, a test that one user cannot reach another user's documents, and an end-to-end
  smoke test of the Docker Compose stack.
- The evaluation measures the real pipeline against Gemini, and its raw results are committed.
- I reviewed each pull request before merging it.
