from fastapi import FastAPI
from backend.routes.user_routes import user_router

app = FastAPI()

app.include_router(router=user_router, prefix="/api/v1")

