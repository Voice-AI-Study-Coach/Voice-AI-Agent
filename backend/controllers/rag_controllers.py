import hashlib
import os
import sys
import logging

from src.exception import CustomException
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from backend.config import MAX_UPLOAD_BYTES
from backend.utils.rag_utils import (
    count_sessions_by_document,
    count_topics,
    create_document,
    delete_document_row,
    find_document_by_hash,
    get_covered_topics,
    get_document_for_user,
    get_storage_path_for_user,
    load_all_documents,
    getAllTurnsTopics,
    getAllChunksTopics,
    getAllQuestionTopics,
    mergeData,
)

log = logging.getLogger(__name__)

async def handleNewChat(request, file):
    """Upload a PDF. Identical re-uploads skip ingestion entirely."""
    try:
        user_id = request.state.user['user_id']

        contents = await file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="The uploaded file is empty")
        if len(contents) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit",
            )
        if not (file.filename or "").lower().endswith(".pdf") or not contents.startswith(b"%PDF"):
            raise HTTPException(status_code=400, detail="Only PDF files are accepted")

        content_hash = hashlib.sha256(contents).hexdigest()
        existing = find_document_by_hash(user_id=user_id, content_hash=content_hash)

        # Only reuse a document that actually finished. A previous failure must
        # fall through to the normal path so ingestion is retried.
        if existing and existing["status"] == "ready":
            covered = get_covered_topics(user_id=user_id, document_id=existing["document_id"])
            log.info("handleNewChat: hash hit document_id=%s, skipping ingestion",
                     existing["document_id"])
            return {
                "document_id": existing["document_id"],
                "filename": existing["filename"],
                "status": "ready",
                "already_seen": True,
                "covered_topic_count": len(covered),
                "total_topic_count": count_topics(existing["document_id"]),
            }

        doc = create_document(
            user_id=user_id,
            filename=file.filename,
            contents=contents,
            content_hash=content_hash,
        )
        log.info("handleNewChat: created document_id=%s filename=%s",
                 doc["document_id"], doc["filename"])
        return {
            "document_id": doc["document_id"],
            "filename": doc["filename"],
            "status": doc["status"],
            "already_seen": False,
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
    """Sidebar list. An empty library is a normal state, not a 404."""
    try:
        user_id = request.state.user['user_id']
        docs = load_all_documents(user_id=user_id)
        session_counts = count_sessions_by_document(user_id=user_id)

        out = []
        for doc in docs:
            document_id = doc["document_id"]
            topics = {row["topic"] for row in getAllChunksTopics(document_id=document_id)}
            covered = set(get_covered_topics(user_id=user_id, document_id=document_id))
            out.append({
                "document_id": document_id,
                "filename": doc["filename"],
                "status": doc["status"],
                "created_at": doc.get("created_at"),
                "total_topics": len(topics),
                "covered_topics": len(covered),
                "session_count": session_counts.get(document_id, 0),
            })
        return out
    except HTTPException:
        raise
    except Exception as e:
        log.exception("handleGetAllDocuments: unexpected failure")
        raise CustomException(e, sys)


def handleDeleteDocument(request, document_id: int):
    """Rows cascade via foreign keys; the file on disk does not, so remove it
    explicitly. The path is fetched before the row is deleted."""
    try:
        user_id = request.state.user['user_id']
        path = get_storage_path_for_user(document_id=document_id, user_id=user_id)
        if path is None:
            raise HTTPException(status_code=404, detail="Document not found")

        delete_document_row(document_id=document_id, user_id=user_id)

        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError as e:
                # The row is already gone; a leftover file is not worth
                # failing the request over.
                log.warning("handleDeleteDocument: could not remove %s: %s", path, e)

        log.info("handleDeleteDocument: removed document_id=%s", document_id)
        return JSONResponse(status_code=200, content="Document deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        log.exception("handleDeleteDocument: failed for document_id=%s", document_id)
        raise CustomException(e, sys)

def handleDocumentTopics(request, document_id: int):
    """Topics for the selection screen, with this user's history on each.

    Ownership is checked first: chunks and questions carry no user_id, so
    without this every query below would happily return another user's
    document to anyone who guesses its id.
    """
    try:
        user_id = request.state.user['user_id']

        doc = get_document_for_user(document_id=document_id, user_id=user_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        # Empty turns is the normal first-time case, not an error - it just
        # means no history yet, and every topic comes back with zeros.
        turns_data = getAllTurnsTopics(user_id=user_id, document_id=document_id)
        chunks_data = getAllChunksTopics(document_id=document_id)
        questions_data = getAllQuestionTopics(document_id=document_id)

        topics = mergeData(
            turns_data=turns_data,
            chunks_data=chunks_data,
            questions_data=questions_data,
        )

        return {
            "document_id": document_id,
            "filename": doc["filename"],
            "status": doc["status"],
            "total_topics": len(topics),
            "covered_topics": sum(1 for t in topics if t["covered"]),
            "topics": topics,
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("handleDocumentTopics: failed for document_id=%s", document_id)
        raise CustomException(e, sys)
