import sys
import os

from src.exception import CustomException
from fastapi import APIRouter, File, Depends, UploadFile, BackgroundTasks
from fastapi.requests import Request
from backend.controllers.rag_controllers import handleNewChat, handleGetDocumentStatus
from backend.middlewares.auth_middleware import verify_jwt
from backend.services.rag_services import run_ingestion

rag_router = APIRouter(dependencies=[Depends(verify_jwt)])

@rag_router.post("/newChat", status_code=201)
async def chat(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The file provided by the user")
    ):
    try:
        doc = await handleNewChat(request=request, file=file)
        background_tasks.add_task(run_ingestion, doc["document_id"])
        return doc
    except Exception as e:
        raise CustomException(e, sys)


@rag_router.get("/documents/{document_id}")
async def get_document_status(request: Request, document_id: int):
    try:
        return handleGetDocumentStatus(request=request, document_id=document_id)
    except Exception as e:
        raise CustomException(e, sys)