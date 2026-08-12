import sys
import logging
from typing import List

from src.exception import CustomException
from fastapi import APIRouter, File, Depends, UploadFile, BackgroundTasks
from fastapi.requests import Request
from fastapi.exceptions import HTTPException
from backend.controllers.rag_controllers import (
    handleNewChat,
    handleGetDocumentStatus,
    handleGetAllDocuments,
    handleDocumentTopics,
    handleDeleteDocument,
)
from backend.middlewares.auth_middleware import verify_jwt
from backend.models.rag_schemas import (
    DocumentSummary,
    DocumentTopicsResponse,
    NewChatResponse,
)
from backend.services.rag_services import run_ingestion

log = logging.getLogger(__name__)

rag_router = APIRouter(dependencies=[Depends(verify_jwt)])

@rag_router.post("/newChat", status_code=201, response_model=NewChatResponse)
async def chat(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The file provided by the user")
    ):
    try:
        log.info("newChat: received upload filename=%s content_type=%s", file.filename, file.content_type)
        doc = await handleNewChat(request=request, file=file)
        log.info("newChat: document_id=%s status=%s already_seen=%s",
                 doc["document_id"], doc["status"], doc["already_seen"])

        # A hash hit means chunks, embeddings and questions already exist, so
        # the whole pipeline is skipped - minutes of work and a large number
        # of LLM calls avoided.
        if not doc["already_seen"]:
            background_tasks.add_task(run_ingestion, doc["document_id"])
            log.info("newChat: queued run_ingestion for document_id=%s", doc["document_id"])
        return doc
    except HTTPException:
        raise
    except Exception as e:
        log.exception("newChat: failed before queuing ingestion")
        raise CustomException(e, sys)


@rag_router.get("/documents", response_model=List[DocumentSummary])
async def get_all_documents(request: Request):
    try:
        return await handleGetAllDocuments(request=request)
    except HTTPException:
        raise
    except Exception as e:
        log.exception("get_all_documents: failed")
        raise CustomException(e, sys)


@rag_router.get("/documents/{document_id}")
def get_document_status(request: Request, document_id: int):
    """Poll this until status is 'ready' or 'failed'."""
    try:
        log.info("get_document_status: document_id=%s", document_id)
        return handleGetDocumentStatus(request=request, document_id=document_id)
    except HTTPException:
        raise
    except Exception as e:
        log.exception("get_document_status: failed for document_id=%s", document_id)
        raise CustomException(e, sys)


@rag_router.get("/documents/{document_id}/topics", response_model=DocumentTopicsResponse)
def get_document_topics(request: Request, document_id: int):
    """Topic-selection screen: every topic in the document, with this user's
    history on each."""
    try:
        return handleDocumentTopics(request=request, document_id=document_id)
    except HTTPException:
        raise
    except Exception as e:
        log.exception("get_document_topics: failed for document_id=%s", document_id)
        raise CustomException(e, sys)


@rag_router.delete("/documents/{document_id}")
def delete_document(request: Request, document_id: int):
    try:
        return handleDeleteDocument(request=request, document_id=document_id)
    except HTTPException:
        raise
    except Exception as e:
        log.exception("delete_document: failed for document_id=%s", document_id)
        raise CustomException(e, sys)
