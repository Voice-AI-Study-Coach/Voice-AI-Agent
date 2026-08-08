import sys
import uuid
import os

from src.exception import CustomException
from fastapi import HTTPException, UploadFile
from supabase_client.client import client

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")

async def create_document(user_id: int, file: UploadFile) -> dict:
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        storage_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}.pdf")
    
        contents = await file.read()
        with open(storage_path, "wb") as f:
            f.write(contents)
    
        return insert_document(
            user_id=user_id,
            filename=file.filename,
            storage_path=storage_path,
            status="pending",
        )
    except Exception as e:
        raise CustomException(e, sys)

def insert_document(user_id: int, filename: str, storage_path: str, status: str):
    try:
        response = (
            client.table("documents")
            .insert({
                "user_id": user_id,
                "filename": filename,
                "storage_path": storage_path,
                "status": status
                })
            .execute()
        )
        return response
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