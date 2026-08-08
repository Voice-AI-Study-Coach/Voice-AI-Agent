import sys
import uuid

from src.exception import CustomException
from supabase_client.client import client
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from backend.utils.rag_utils import create_document, get_document_for_user

async def handleNewChat(request, file):
    try:
        response = (
            client.table("users")
            .select("email")
            .eq("email", request.state.user['email'])
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=401, detail="Please login first")
        response = await create_document(user_id=request.state.user['user_id'], file=file)
        if not response.data:
            raise HTTPException(status_code=500, detail="Something went wrong while inserting the document")
        doc = response.data[0]
        return {
            "document_id": doc["document_id"],
            "filename": doc["filename"],
            "status": doc["status"],
        }
    except HTTPException:
        raise
    except Exception as e:
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