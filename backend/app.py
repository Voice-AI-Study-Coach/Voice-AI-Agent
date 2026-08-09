import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes.user_routes import user_router
from backend.routes.rag_routes import rag_router
from backend.routes.session_routes import session_router
from backend.services.reaper_services import run_reapers

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A crash mid-ingestion leaves documents stuck in 'processing' and open
    # sessions that nothing will ever close. Clear them before serving.
    run_reapers()
    yield


app = FastAPI(title="Voice AI Study Coach", lifespan=lifespan)

# The JWT travels in an HttpOnly cookie, so the browser only sends it when
# credentials are allowed and the origin is named explicitly - "*" is not
# permitted alongside allow_credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router=user_router, prefix="/api/v1")
app.include_router(router=rag_router, prefix="/api/v1/rag")
app.include_router(router=session_router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
