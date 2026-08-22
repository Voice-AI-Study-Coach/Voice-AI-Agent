import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db import close_pool, open_pool, ping
from backend.routes.user_routes import user_router
from backend.routes.rag_routes import rag_router
from backend.routes.session_routes import session_router, session_ws_router
from backend.routes.speech_routes import speech_router, speech_ws_router
from backend.services.reaper_services import run_reapers

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Neon (free tier) suspends its compute after ~5 minutes with no queries;
# the first query after that pays a real wake-up cost (measured ~5s, vs
# ~0.5s once warm). A ping well inside that window keeps the compute from
# ever going idle long enough to suspend during normal use, so a student
# coming back to the app mid-session does not eat that cost on their next
# click - not just on server startup, but for as long as the server runs.
DB_KEEPALIVE_SECONDS = 180


async def _keepalive_loop() -> None:
    while True:
        await asyncio.sleep(DB_KEEPALIVE_SECONDS)
        try:
            await asyncio.to_thread(ping)
        except Exception as e:
            # A missed ping just means the next real request pays the
            # cold-start cost once - not worth taking the server down over.
            log.warning("db keepalive ping failed: %s", e)


async def _warmup() -> None:
    """Wake Neon and run the startup reapers, off the startup path.

    Both used to block lifespan before the first request could be served: a
    suspended Neon compute costs ~5s to wake, and the reapers add two more
    round trips on top. In development that cost was paid on every reload.

    Neither is a precondition for serving. The pool wakes the compute on
    first use anyway, and the reapers only tidy rows left behind by a
    previous crash - nothing in a live request depends on them having
    finished. So they run concurrently with the server accepting traffic;
    a request arriving in that window just races the same warm-up it would
    have waited for.
    """
    try:
        t0 = asyncio.get_event_loop().time()
        await asyncio.to_thread(ping)
        log.info("startup db ping ok in %.2fs", asyncio.get_event_loop().time() - t0)
    except Exception as e:
        log.warning("startup db ping failed: %s", e)
        # The reapers would only fail the same way against a database that is
        # not answering; leave them for the next start rather than logging a
        # second, identical failure.
        return

    try:
        await asyncio.to_thread(run_reapers)
    except Exception as e:
        log.warning("startup reapers failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Opened here rather than at import time: Neon suspends idle compute, and
    # opening eagerly at import would make every cold import pay a connect
    # round-trip even for tooling that never serves a request (tests, etc).
    open_pool()

    warmup_task = asyncio.create_task(_warmup())
    keepalive_task = asyncio.create_task(_keepalive_loop())
    try:
        yield
    finally:
        warmup_task.cancel()
        keepalive_task.cancel()
        close_pool()


app = FastAPI(title="Voice AI Study Coach", lifespan=lifespan)

# The JWT travels in an HttpOnly cookie, so the browser only sends it when
# credentials are allowed and the origin is named explicitly - "*" is not
# permitted alongside allow_credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://voice-ai-agent-nv4u.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router=user_router, prefix="/api/v1")
app.include_router(router=rag_router, prefix="/api/v1/rag")
app.include_router(router=session_router, prefix="/api/v1")
app.include_router(router=session_ws_router, prefix="/api/v1")
app.include_router(router=speech_router, prefix="/api/v1")
app.include_router(router=speech_ws_router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
