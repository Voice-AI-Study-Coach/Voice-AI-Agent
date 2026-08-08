from fastapi import FastAPI
from backend.routes.user_routes import user_router
from backend.routes.rag_routes import rag_router

app = FastAPI()

app.include_router(router=user_router, prefix="/api/v1")
app.include_router(router=rag_router, prefix="/api/v1/rag")

