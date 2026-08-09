import sys
import os
import logging

from src.exception import CustomException
from fastapi import APIRouter, File, Depends, UploadFile, BackgroundTasks
from fastapi.requests import Request
from backend.controllers.rag_controllers import handleNewChat, handleGetDocumentStatus, handleGetAllDocuments
from backend.middlewares.auth_middleware import verify_jwt
from backend.services.rag_services import run_ingestion

log = logging.getLogger(__name__)

rag_router = APIRouter(dependencies=[Depends(verify_jwt)])

@rag_router.post("/newChat", status_code=201)
async def chat(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The file provided by the user")
    ):
    try:
        log.info("newChat: received upload filename=%s content_type=%s", file.filename, file.content_type)
        doc = await handleNewChat(request=request, file=file)
        log.info("newChat: document row created document_id=%s status=%s", doc["document_id"], doc["status"])
        background_tasks.add_task(run_ingestion, doc["document_id"])
        log.info("newChat: queued run_ingestion for document_id=%s", doc["document_id"])
        return doc
    except Exception as e:
        log.exception("newChat: failed before queuing ingestion")
        raise CustomException(e, sys)


@rag_router.get("/document/{document_id}")
async def get_document_status(request: Request, document_id: int):
    try:
        log.info("get_document_status: document_id=%s", document_id)
        return handleGetDocumentStatus(request=request, document_id=document_id)
    except Exception as e:
        log.exception("get_document_status: failed for document_id=%s", document_id)
        raise CustomException(e, sys)

@rag_router.get("/documents")
def get_all_documents(request: Request):
    try:
        return handleGetAllDocuments(request=request)
    except Exception as e:
        log.exception("get_all_documents: failed")
        raise CustomException(e, sys)