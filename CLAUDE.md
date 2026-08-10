# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Voice AI Study Coach: upload a PDF, an ingestion pipeline turns it into topic chunks + generated questions, and a quiz engine runs an adaptive spoken oral exam over them. FastAPI backend + Next.js frontend + Supabase (Postgres with pgvector).

## Commands

Backend (run from the repo root — all imports are absolute from the root package, e.g. `backend.`, `llm.`, `src.`, `supabase_client.`):

```bash
venv\Scripts\activate            # Windows; source venv/bin/activate elsewhere
pip install -r requirements.txt  # includes `-e .`, needed for the root-package imports to resolve
uvicorn backend.app:app --reload # http://localhost:8000, docs at /docs
```

Frontend (from `frontend/`):

```bash
npm install
npm run dev      # http://localhost:3000
npm run build
npm run lint
```

There is no test suite. `testing/` holds Jupyter notebooks and sample PDFs used for manual experimentation, not automated tests.

Run the frontend and backend together — the frontend has no direct backend URL. `next.config.ts` rewrites `/api/*` to `BACKEND_URL` (default `http://127.0.0.1:8000`) so requests are same-origin and the HttpOnly auth cookie is sent.

## Architecture

### Request layering (backend)

`routes/` → `controllers/` → `utils/` (Supabase queries) with `models/` holding the Pydantic request/response schemas. `services/` holds background orchestration, not request handling. Business logic lives in controllers; routes are thin and only translate exceptions.

Auth is a router-level `Depends(verify_jwt)` on `rag_router` and `session_router`. It reads a Bearer header or the `access_token` cookie, decodes with `JWT_SECRET_KEY`, and puts the user row on `request.state.user`.

Exceptions: wrap non-HTTP failures in `CustomException(e, sys)` (from `src/exception.py` — it needs the `sys` module to read the traceback). Always re-raise `HTTPException` before the generic `except`, or 404s and 409s become 500s.

### The engine split — do not blur this

The LLM produces a *verdict* and *phrases replies*. Score, difficulty level, topic advancement, and question selection are plain Python and SQL. This is deliberate: it keeps the adaptive behaviour deterministic, testable, and explainable. Never move scoring or selection decisions into a prompt.

- [llm/grading/scoring.py](llm/grading/scoring.py) — pure functions on a session dict, no I/O. `apply_verdict` mutates in place and returns `{topic_changed, session_complete}`.
- [backend/utils/session_utils.py](backend/utils/session_utils.py) — `pick_question` widens around the current level via `LEVEL_WIDENING_OFFSETS` when the exact level is exhausted.
- [backend/config.py](backend/config.py) — every tuning constant (pacing, thresholds, upload limit, reaper windows, verdict points). Must not import from `backend/` or `llm/`; keep it importable from anywhere. `frontend/src/lib/config.ts` mirrors the overlapping values.

The `unclear` verdict is load-bearing and deliberately absent from `POINTS`. It means speech-to-text produced something unusable — a technical failure, not a wrong answer. It must not score, must not consume one of the topic's questions, and must be filtered out of summaries. Check for it before scoring rather than looking it up in `POINTS`.

Level and score reset to `BASELINE_*` at every topic boundary — they are never carried forward between topics.

### Ingestion pipeline

`POST /api/v1/rag/newChat` inserts a `documents` row and queues `run_ingestion` as a FastAPI background task. A content-hash hit (`already_seen`) skips the whole pipeline.

`run_ingestion` in [backend/services/rag_services.py](backend/services/rag_services.py) must never raise — a background task that throws leaves the document stuck in `processing` with no way for the user to find out. Every failure path records `status="failed"` with an error message instead.

Stages: PyMuPDF parse (+ TOC as chunking hints) → LLM semantic chunking (150-line windows) → embedding and question generation concurrently via `asyncio.gather` (`generateEmbedding` is sync so it goes through `asyncio.to_thread`) → persist chunks then questions → `status="ready"`.

### Topic strings are the join key

`chunks.topic`, `questions.topic`, and `turns.topic` are joined on the string itself. A mismatch does not error — `get_topic_source_material` just returns nothing and grading silently loses its grounding. This is why `handleSession` validates selected topics against the document up front.

### Ownership scoping

Session and document ids are sequential integers. Every `*_for_user` lookup filters on `user_id` as part of the query and returns `None` for both "not found" and "not yours"; callers return 404 either way (a 403 would confirm the id exists). Don't add an ownership check after an unscoped fetch.

### Key rotation

Every Groq/Gemini/Cerebras call must pull its key from the pools in [llm/rotation_shifting.py](llm/rotation_shifting.py) (`GROQ_API_KEY_1..n` etc., falling back to a single unnumbered var). Fetch the key *per call*, never cache one on `self` in `__init__` — a held key can't rotate away when it gets cooled down. The pattern is: loop over `len(pool._keys)`, build a client, on `is_rate_limit_error(e)` call `mark_rate_limited(key)` and retry, on success call `mark_success(key)`.

### Supabase client

`supabase_client/client.py` exports a thread-local proxy, not a plain client. FastAPI runs sync handlers in a threadpool, and sharing supabase-py's single httpx HTTP/2 connection across threads corrupts the stream (on Windows: `WinError 10035`). Import `client` from there; never call `create_client` directly.

### Startup reapers

`run_reapers()` runs in the app lifespan and clears rows nothing else will move: documents stuck in `processing` past `INGESTION_STUCK_MINUTES`, and active sessions idle past `SESSION_IDLE_MINUTES`.

## Frontend notes

`frontend/AGENTS.md` (auto-generated by `next dev`, and `frontend/CLAUDE.md` just points at it) warns that this Next.js version has breaking changes vs. training data — read `frontend/node_modules/next/dist/docs/` before writing Next-specific code. Don't try to remove that block from a diff; `next dev` re-creates it.

App Router with `(app)` and `(auth)` route groups. All backend calls go through the typed `request()` helper in `src/lib/api.ts`, which sends `credentials: "include"` and flattens FastAPI's `detail` field into `ApiError`.

## Environment

`.env` at the repo root: numbered provider keys (`GROQ_API_KEY_1..n`, `GEMINI_API_KEY_1..n`, `CEREBRAS_API_KEY_1..n`), `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `JWT_SECRET_KEY`. `backend/app.py` pins CORS to `http://localhost:3000` with `allow_credentials=True` — `"*"` is not permitted alongside credentials.
