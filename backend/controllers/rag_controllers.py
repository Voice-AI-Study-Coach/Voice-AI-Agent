import asyncio
import hashlib
import os
import sys
import logging

from src.exception import CustomException
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from backend.config import MAX_UPLOAD_BYTES, QUESTIONS_PER_TOPIC
from backend.utils.rag_utils import (
    count_covered_topics_by_document,
    count_distinct_topics_by_document,
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
from backend.utils.session_utils import get_active_session_for_document

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

async def handleGetAllDocuments(request):
    """Sidebar list. An empty library is a normal state, not a 404.

    Two layers of optimization, both measured against the live database:

    1. Batched rather than looping a per-document query: this used to call
       getAllChunksTopics and get_covered_topics once for every document,
       each call its own round-trip to Neon - with N documents that was
       N+1 serial round-trips just to build this one list.
    2. The three remaining queries run CONCURRENTLY via asyncio.gather,
       not sequentially. Even warm, each round-trip to Neon costs a real
       ~0.5s (this is the honest floor - genuine network latency, not
       something a smarter query fixes) - four of them in series cost
       ~2s, concurrently they cost roughly the time of the slowest one.
    """
    try:
        user_id = request.state.user['user_id']
        docs = load_all_documents(user_id=user_id)
        document_ids = [doc["document_id"] for doc in docs]

        session_counts, total_topics, covered_topics = await asyncio.gather(
            asyncio.to_thread(count_sessions_by_document, user_id=user_id),
            asyncio.to_thread(count_distinct_topics_by_document, document_ids),
            asyncio.to_thread(count_covered_topics_by_document, user_id, document_ids),
        )

        return [
            {
                "document_id": doc["document_id"],
                "filename": doc["filename"],
                "status": doc["status"],
                "created_at": doc.get("created_at"),
                "total_topics": total_topics.get(doc["document_id"], 0),
                "covered_topics": covered_topics.get(doc["document_id"], 0),
                "session_count": session_counts.get(doc["document_id"], 0),
            }
            for doc in docs
        ]
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

        # Surface an in-progress session on this document so the picker can
        # offer to resume it instead of always starting a fresh one on top -
        # the topic list's historical counts only include ANSWERED turns, so
        # a session abandoned after 1 of 4 questions reads as "1/1 correct,
        # 100%" unless the caller also knows there is unfinished work.
        active = get_active_session_for_document(user_id=user_id, document_id=document_id)
        active_session = None
        if active:
            selected = active.get("selected_topics") or []
            active_session = {
                "session_id": active["session_id"],
                "current_topic": active["current_topic"],
                "questions_asked": active["questions_asked"],
                "total_questions": len(selected) * QUESTIONS_PER_TOPIC,
                "started_at": active.get("started_at"),
            }

        return {
            "document_id": document_id,
            "filename": doc["filename"],
            "status": doc["status"],
            "total_topics": len(topics),
            "covered_topics": sum(1 for t in topics if t["covered"]),
            "topics": topics,
            "active_session": active_session,
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("handleDocumentTopics: failed for document_id=%s", document_id)
        raise CustomException(e, sys)
