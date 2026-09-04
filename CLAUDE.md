# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Voice AI Study Coach: upload a PDF, an ingestion pipeline turns it into topic chunks + generated questions, and a quiz engine runs an adaptive spoken oral exam over them. FastAPI backend + Next.js frontend + Neon (Postgres with pgvector), with Deepgram for speech in and out.

## Commands

Backend (run from the repo root — all imports are absolute from the root package, e.g. `backend.`, `llm.`, `src.`):

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

Auth is a router-level `Depends(verify_jwt)` on `rag_router`, `session_router`, and `speech_router`. It reads a Bearer header or the `access_token` cookie, decodes with `JWT_SECRET_KEY`, and puts the user row on `request.state.user`.

WebSocket routes live on separate routers (`session_ws_router`, `speech_ws_router`) deliberately *without* that dependency: `verify_jwt` expects a `Request`, and a WebSocket is not one. WS handlers must `await verify_jwt_ws(websocket)` themselves **before** `websocket.accept()` and close the socket if it raises — once the handshake is accepted it is too late to reject it. The `access_token` cookie rides along on the handshake, so no separate auth message is needed.

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

### Speech layer

Speech is server-side Deepgram, not the browser's engine: `nova-3` for transcription, `aura-2-thalia-en` for voice ([backend/controllers/speech_controllers.py](backend/controllers/speech_controllers.py)). The browser only records audio and plays it back.

Three delivery paths, each for a reason worth preserving:
- `GET /speech/speak` streams mp3 and exists so an `<audio>` element can point straight at the URL and play progressively; a `fetch` would stall until the whole clip downloaded. The cookie rides along, so auth still holds.
- `POST /speech/speak` is the same thing for callers that prefer a body.
- `WS /speech/speak-stream` yields raw linear16 PCM at 24kHz — `aura-2` over `speak.v1.connect()` rejects mp3 on that path. Because PCM frames alone can't mark end-of-utterance, the server sends `{"type":"done"}` after each line; errors come back as `{"type":"error"}` and leave the socket open for the next line.

`SpeechStreamSession` opens its Deepgram socket lazily on the first line and reuses it for the connection's lifetime, and the WS handler must close it in a `finally` — otherwise an abandoned tab leaks the connection until Deepgram's own idle timeout reaps it.

### Topic strings are the join key

`chunks.topic`, `questions.topic`, and `turns.topic` are joined on the string itself. A mismatch does not error — `get_topic_source_material` just returns nothing and grading silently loses its grounding. This is why `handleSession` validates selected topics against the document up front.

### Ownership scoping

Session and document ids are sequential integers. Every `*_for_user` lookup filters on `user_id` as part of the query and returns `None` for both "not found" and "not yours"; callers return 404 either way (a 403 would confirm the id exists). Don't add an ownership check after an unscoped fetch.

### Key rotation

Every provider call must pull its key from the pools in [llm/rotation_shifting.py](llm/rotation_shifting.py) — `groq_pool`, `gemini_pool`, `mistral_pool`, `deepgram_pool` (`GROQ_API_KEY_1..n` etc., falling back to a single unnumbered var). Fetch the key *per call*, never cache one on `self` in `__init__` — a held key can't rotate away when it gets cooled down. The pattern is: loop over `len(pool._keys)`, build a client, on `is_rate_limit_error(e)` call `mark_rate_limited(key)` and retry, on success call `mark_success(key)`.

### Database access

The database is Neon Postgres, reached directly with psycopg — there is no Supabase client (an older revision used one; ignore any lingering references). [backend/db.py](backend/db.py) owns a `ConnectionPool` and exports `fetch_one` / `fetch_all` / `execute` / `execute_returning` / `execute_returning_many`. Write SQL through those helpers rather than opening cursors by hand; rows come back as plain dicts via `dict_row`.

Neon suspends idle compute, which shapes three things in the pool: `min_size=0` so app startup doesn't fail against a sleeping endpoint, `check=ConnectionPool.check_connection` so a connection killed by a suspend is replaced instead of handed out dead, and a periodic `ping()` keep-alive so requests don't pay the ~5s cold start. `register_vector` is applied per connection — without it a list of floats can't bind to a `vector` column.

### Startup is deliberately non-blocking

The lifespan opens the pool, then pushes the Neon wake-up ping and `run_reapers()` into a background task rather than awaiting them. Both used to block the first request (~5s wake + reaper time). Keep new startup work off that path unless a request genuinely cannot be served without it.

`run_reapers()` clears rows nothing else will move: documents stuck in `processing` past `INGESTION_STUCK_MINUTES`, and active sessions idle past `SESSION_IDLE_MINUTES`.

## Frontend notes

`frontend/AGENTS.md` (auto-generated by `next dev`, and `frontend/CLAUDE.md` just points at it) warns that this Next.js version has breaking changes vs. training data — read `frontend/node_modules/next/dist/docs/` before writing Next-specific code. Don't try to remove that block from a diff; `next dev` re-creates it.

App Router with `(app)` and `(auth)` route groups. All backend calls go through the typed `request()` helper in `src/lib/api.ts`, which sends `credentials: "include"` and flattens FastAPI's `detail` field into `ApiError`.

## Environment

`.env` at the repo root: numbered provider keys (`GROQ_API_KEY_1..n`, `GEMINI_API_KEY_1..n`, `MISTRAL_API_KEY_1..n`, `DEEPGRAM_API_KEY_1..n`), `NEON_DATABASE_URL`, `JWT_SECRET_KEY`, optional `UPLOAD_DIR`. `backend/app.py` allows exactly two CORS origins (localhost:3000 and the deployed Vercel app) with `allow_credentials=True` — `"*"` is not permitted alongside credentials, so a new deploy origin has to be added to that list explicitly.

Note that `README.md` still documents the older Supabase/Cerebras setup; this file reflects the current code.
