import sys
import uuid
import logging

from src.exception import CustomException
from supabase_client.client import client
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from backend.utils.rag_utils import create_document, get_document_for_user, load_all_documents

log = logging.getLogger(__name__)

async def handleNewChat(request, file):
    try:
        user_email = request.state.user['email']
        log.debug("handleNewChat: verifying user email=%s", user_email)
        response = (
            client.table("users")
            .select("email")
            .eq("email", user_email)
            .execute()
        )
        if not response.data:
            log.warning("handleNewChat: no user row found for email=%s", user_email)
            raise HTTPException(status_code=401, detail="Please login first")

        log.debug("handleNewChat: creating document for user_id=%s", request.state.user['user_id'])
        response = await create_document(user_id=request.state.user['user_id'], file=file)
        if not response.data:
            log.error("handleNewChat: create_document returned no data")
            raise HTTPException(status_code=500, detail="Something went wrong while inserting the document")
        doc = response.data[0]
        log.info("handleNewChat: created document_id=%s filename=%s", doc["document_id"], doc["filename"])
        return {
            "document_id": doc["document_id"],
            "filename": doc["filename"],
            "status": doc["status"],
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("handleNewChat: unexpected failure")
        raise CustomException(e, sys)


def handleGetDocumentStatus(request, document_id: int):
    """Poll this until status is 'ready' or 'failed'."""
    try:
        doc = get_document_for_user(
            document_id=document_id,
            user_id=request.state.user['user_id'],
        )
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)

def handleGetAllDocuments(request):
    try:
        docs = load_all_documents(user_id=request.state.user['user_id'])
        if not docs.data:
            raise HTTPException(status_code=404, detail="No documents found")
        return docs.data
    except HTTPException:
        raise
    except Exception as e:
        log.exception("handleGetAllDocuments: unexpected failure")
        raise CustomException(e, sys)