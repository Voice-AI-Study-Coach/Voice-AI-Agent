import sys
import uuid
import os

from src.exception import CustomException
from fastapi import HTTPException
from supabase_client.client import client

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")

def create_document(user_id: int, filename: str, contents: bytes, content_hash: str) -> dict:
    """Persist the uploaded bytes and create the document row.

    Takes `contents` rather than the UploadFile: the caller has already read
    the stream to hash it, and a second read would return b"" - silently
    writing a zero-byte PDF.
    """
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        storage_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}.pdf")

        with open(storage_path, "wb") as f:
            f.write(contents)

        return insert_document(
            user_id=user_id,
            filename=filename,
            storage_path=storage_path,
            status="pending",
            content_hash=content_hash,
        )
    except Exception as e:
        raise CustomException(e, sys)

def insert_document(user_id: int, filename: str, storage_path: str, status: str, content_hash: str | None = None) -> dict:
    try:
        row = {
            "user_id": user_id,
            "filename": filename,
            "storage_path": storage_path,
            "status": status,
        }
        if content_hash is not None:
            row["content_hash"] = content_hash

        response = client.table("documents").insert(row).execute()
        if not response.data:
            raise CustomException("Failed to insert document", sys)
        return response.data[0]
    except Exception as e:
        raise CustomException(e, sys)

def find_document_by_hash(user_id: int, content_hash: str) -> dict | None:
    """Look for an identical PDF this user has already uploaded.

    Hashing the bytes rather than comparing filenames: the same file may be
    renamed, and two entirely different files may both be called unit1.pdf.
    """
    try:
        response = (
            client.table("documents")
            .select("document_id, filename, status")
            .eq("user_id", user_id)
            .eq("content_hash", content_hash)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        raise CustomException(e, sys)

def get_storage_path_for_user(document_id: int, user_id: int) -> str | None:
    """Ownership is part of the lookup, not a check afterwards."""
    try:
        response = (
            client.table("documents")
            .select("storage_path")
            .eq("document_id", document_id)
            .eq("user_id", user_id)
            .execute()
        )
        return response.data[0]["storage_path"] if response.data else None
    except Exception as e:
        raise CustomException(e, sys)

def delete_document_row(document_id: int, user_id: int) -> None:
    """Chunks, questions, sessions and turns go via foreign-key cascade."""
    try:
        (
            client.table("documents")
            .delete()
            .eq("document_id", document_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as e:
        raise CustomException(e, sys)

def get_document_for_user(document_id: int, user_id: int) -> dict | None:
    """Fetch a document row, scoped to its owner, with chunk/question counts.

    document_id is trivially guessable (integer primary key), so every
    endpoint that touches a document MUST filter on both document_id and
    user_id together - never document_id alone.
    """
    try:
        response = (
            client.table("documents")
            .select("document_id, filename, status, error, created_at, processed_at")
            .eq("document_id", document_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not response.data:
            return None
        doc = response.data[0]

        chunk_count = (
            client.table("chunks")
            .select("chunk_id", count="exact")
            .eq("document_id", document_id)
            .execute()
        ).count or 0

        question_count = (
            client.table("questions")
            .select("question_id", count="exact")
            .eq("document_id", document_id)
            .execute()
        ).count or 0

        return {
            **doc,
            "chunk_count": chunk_count,
            "question_count": question_count,
        }
    except Exception as e:
        raise CustomException(e, sys)

def insert_chunks(document_id: int, chunks: list[dict]) -> list[dict]:
    """Bulk-insert chunk rows. idx preserves original document order, which
    grading relies on to reassemble a topic's source material correctly."""
    try:
        if not chunks:
            return []

        rows = [
            {
                "document_id": document_id,
                "idx": i,
                "content": c["content"],
                "topic": c["topic"],
                "parent": c.get("parent"),
                "embedding": c.get("embedding"),
            }
            for i, c in enumerate(chunks)
        ]

        response = client.table("chunks").insert(rows).execute()
        if not response.data:
            raise CustomException("Failed to insert chunks", sys)
        return response.data
    except Exception as e:
        raise CustomException(e, sys)

def insert_questions(document_id: int, questions: list[dict]) -> list[dict]:
    """Bulk-insert generated questions. chunk_id is intentionally left null:
    questions are generated per topic, not per chunk, so there is no single
    chunk a question 'came from'."""
    try:
        if not questions:
            return []

        rows = [
            {
                "document_id": document_id,
                "chunk_id": None,
                "question_text": q["question"],
                "ideal_answer": q["ideal_answer"],
                "key_points": q["key_points"],
                "topic": q["topic"],
                "parent": q.get("parent"),
                "difficulty": q["difficulty"],
            }
            for q in questions
        ]

        response = client.table("questions").insert(rows).execute()
        if not response.data:
            raise CustomException("Failed to insert questions", sys)
        return response.data
    except Exception as e:
        raise CustomException(e, sys)

def load_all_documents(user_id):
    try:
        response = (
            client.table("documents")
            .select("document_id, filename, status, error, created_at, processed_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return response.data or []
    except Exception as e:
        raise CustomException(e, sys)

def count_sessions_by_document(user_id: int) -> dict:
    """session_count per document, for the sidebar."""
    try:
        response = (
            client.table("sessions")
            .select("document_id")
            .eq("user_id", user_id)
            .execute()
        )
        counts = {}
        for row in (response.data or []):
            counts[row["document_id"]] = counts.get(row["document_id"], 0) + 1
        return counts
    except Exception as e:
        raise CustomException(e, sys)

def count_topics(document_id: int) -> int:
    try:
        rows = getAllChunksTopics(document_id=document_id)
        return len({row["topic"] for row in rows})
    except Exception as e:
        raise CustomException(e, sys)

def get_covered_topics(user_id: int, document_id: int) -> list[str]:
    """Topics with at least one answered turn, across all of this user's
    sessions on the document. Coverage is derived from turns, never stored as
    a flag: a stored flag drifts when sessions are deleted, a query cannot."""
    try:
        rows = getAllTurnsTopics(user_id=user_id, document_id=document_id)
        return sorted({row["topic"] for row in rows})
    except Exception as e:
        raise CustomException(e, sys)

def getAllTurnsTopics(user_id: int, document_id: int):
    try:
        response = (
            client.table("turns")
            .select("topic, verdict, sessions!inner(user_id, document_id)")
            .eq("sessions.user_id", user_id)
            .eq("sessions.document_id", document_id)
            .not_.is_("verdict", "null")
            .execute()
        )
        return response.data
    except Exception as e:
        raise CustomException(e, sys)

def getAllChunksTopics(document_id: int):
    """Every topic in the document, one row per chunk. Ordered by idx so the
    first occurrence of a topic is its earliest position in the document."""
    try:
        response = (
            client.table("chunks")
            .select("topic, parent, idx")
            .eq("document_id", document_id)
            .order("idx")
            .execute()
        )
        return response.data
    except Exception as e:
        raise CustomException(e, sys)

def getAllQuestionTopics(document_id: int):
    """Topics that have generated questions. A topic whose chunks were too
    short to generate from has no rows here, so it is unquizzable."""
    try:
        response = (
            client.table("questions")
            .select("topic")
            .eq("document_id", document_id)
            .execute()
        )
        return response.data
    except Exception as e:
        raise CustomException(e, sys)

def getTally(data):
    try:
        tally = {}
        for row in data:
            topic = row['topic']
            if topic not in tally:
                tally[topic] = {"times_asked": 0, "correct_count": 0}
            tally[topic]['times_asked']+=1
            if row['verdict'] == "correct":
                tally[topic]['correct_count']+=1
        return tally
    except Exception as e:
        raise CustomException(e, sys)

def getSeenData(data):
    try:
        seen = {}
        for row in data:
            topic = row['topic']
            if topic not in seen:
                seen[topic] = row['parent']
        return seen
    except Exception as e:
        raise CustomException(e, sys)

def getQuestionCounts(data):
    try:
        counts = {}
        for row in data:
            topic = row['topic']
            counts[topic] = counts.get(topic, 0) + 1
        return counts
    except Exception as e:
        raise CustomException(e, sys)

def mergeData(turns_data, chunks_data, questions_data):
    """Left join: every topic in chunks survives, history attaches where it
    exists. Iterating over `seen` (not `tally`) is what keeps never-quizzed
    topics in the list - they are exactly the ones the user needs to see."""
    try:
        tally = getTally(data=turns_data)
        seen = getSeenData(data=chunks_data)
        question_counts = getQuestionCounts(data=questions_data)
        topics = []
        for topic, parent in seen.items():
            stats = tally.get(topic, {"times_asked": 0, "correct_count": 0})
            times_asked = stats["times_asked"]
            correct_count = stats["correct_count"]
            topics.append({
                "topic": topic,
                "parent": parent,
                "question_count": question_counts.get(topic, 0),
                "times_asked": times_asked,
                "correct_count": correct_count,
                "covered": times_asked > 0,
                "accuracy": correct_count / times_asked if times_asked else None,
            })
        return topics
    except Exception as e:
        raise CustomException(e, sys)
