# Repository Guidelines

## Project Structure & Module Organization

The backend is a FastAPI application under `backend/`. Routes define HTTP endpoints, controllers handle requests, models contain Pydantic schemas, services coordinate background work, and `middlewares/` and `utils/` provide shared concerns. The AI pipeline lives in `llm/`, organized into `rag/` (ingestion, chunking, embeddings, and generation) and `grading/` (scoring and coaching). Shared logging and exception helpers are in `src/`. The user interface is a Next.js app in `frontend/src/`; OCR prototypes and notebooks are in `ocr-testing/` and `testing/`. Runtime PDFs, logs, `.next/`, `venv/`, and generated files should not be committed.

## Build, Test, and Development Commands

From the repository root, create and activate a virtual environment, then install Python dependencies:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.app:app --reload
```

The API is available at `http://localhost:8000` and its OpenAPI UI at `/docs`. For the frontend:

```bash
cd frontend
npm install
npm run dev       # local Next.js development server
npm run build     # production build
npm run lint      # Next.js lint check
```

## Coding Style & Naming Conventions

Use four-space indentation for Python and standard PEP 8 naming: `snake_case` for modules, functions, and variables; `PascalCase` for classes and schemas. Keep FastAPI route declarations in `backend/routes/` and business logic in controllers/services. Use TypeScript/React conventions in the frontend: `PascalCase` components and `camelCase` variables. Match surrounding formatting and keep changes focused; no repository-wide formatter configuration is currently defined.

## Testing Guidelines

There is no configured pytest or Jest suite at present. Validate backend changes with the running API and `/docs`, and use notebooks in `testing/` for LLM experiments. For frontend changes, run `npm run lint` and `npm run build`; manually check affected flows when UI or audio behavior changes. Add focused automated tests alongside new functionality as the test suite is expanded.

## Commit & Pull Request Guidelines

Recent commits use short, feature-oriented summaries such as `frontend completed successfully` and `speech handled successfully`. Follow that pattern and keep each commit to one logical change. Pull requests should explain behavior changes, identify affected areas, include validation commands and results, link issues when applicable, and attach screenshots or recordings for UI and voice-flow changes.

## Security & Configuration

Keep API keys, JWT secrets, Supabase credentials, and local `.env` files out of commits. Use the variable names documented in `README.md`. Do not commit uploaded PDFs, logs, generated builds, or dependency directories.
