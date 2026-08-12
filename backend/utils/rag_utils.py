import sys
import uuid
import os

from src.exception import CustomException
from backend.config import WEAK_TOPIC_ACCURACY
from backend.db import execute, execute_returning, execute_returning_many, fetch_all, fetch_one

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
        row = execute_returning(
            "insert into documents (user_id, filename, storage_path, status, content_hash) "
            "values (%s, %s, %s, %s, %s) "
            "returning document_id, filename, status, error, created_at, processed_at",
            (user_id, filename, storage_path, status, content_hash),
        )
        if not row:
            raise CustomException("Failed to insert document", sys)
        return row
    except Exception as e:
        raise CustomException(e, sys)

def find_document_by_hash(user_id: int, content_hash: str) -> dict | None:
    """Look for an identical PDF this user has already uploaded.

    Hashing the bytes rather than comparing filenames: the same file may be
    renamed, and two entirely different files may both be called unit1.pdf.
    """
    try:
        return fetch_one(
            "select document_id, filename, status from documents "
            "where user_id = %s and content_hash = %s "
            "order by created_at desc limit 1",
            (user_id, content_hash),
        )
    except Exception as e:
        raise CustomException(e, sys)

def get_storage_path_for_user(document_id: int, user_id: int) -> str | None:
    """Ownership is part of the lookup, not a check afterwards."""
    try:
        row = fetch_one(
            "select storage_path from documents where document_id = %s and user_id = %s",
            (document_id, user_id),
        )
        return row["storage_path"] if row else None
    except Exception as e:
        raise CustomException(e, sys)

def delete_document_row(document_id: int, user_id: int) -> None:
    """Chunks, questions, sessions and turns go via foreign-key cascade."""
    try:
        execute(
            "delete from documents where document_id = %s and user_id = %s",
            (document_id, user_id),
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
        return fetch_one(
            """
            select d.document_id, d.filename, d.status, d.error, d.created_at, d.processed_at,
                   (select count(*) from chunks c where c.document_id = d.document_id) as chunk_count,
                   (select count(*) from questions q where q.document_id = d.document_id) as question_count
            from documents d
            where d.document_id = %s and d.user_id = %s
            """,
            (document_id, user_id),
        )
    except Exception as e:
        raise CustomException(e, sys)

def insert_chunks(document_id: int, chunks: list[dict]) -> list[dict]:
    """Bulk-insert chunk rows. idx preserves original document order, which
    grading relies on to reassemble a topic's source material correctly."""
    try:
        if not chunks:
            return []

        with_placeholders = ", ".join(["(%s, %s, %s, %s, %s, %s)"] * len(chunks))
        params = []
        for i, c in enumerate(chunks):
            params.extend([document_id, i, c["content"], c["topic"], c.get("parent"), c.get("embedding")])

        sql = (
            f"insert into chunks (document_id, idx, content, topic, parent, embedding) "
            f"values {with_placeholders} "
            f"returning chunk_id, document_id, idx, content, topic, parent"
        )
        rows = execute_returning_many(sql, params)
        if not rows:
            raise CustomException("Failed to insert chunks", sys)
        return rows
    except Exception as e:
        raise CustomException(e, sys)

def insert_questions(document_id: int, questions: list[dict]) -> list[dict]:
    """Bulk-insert generated questions. chunk_id is intentionally left null:
    questions are generated per topic, not per chunk, so there is no single
    chunk a question 'came from'."""
    try:
        if not questions:
            return []

        import json

        with_placeholders = ", ".join(["(%s, %s, %s, %s, %s, %s, %s)"] * len(questions))
        params = []
        for q in questions:
            params.extend([
                document_id,
                q["question"],
                q["ideal_answer"],
                json.dumps(q["key_points"]),
                q["topic"],
                q.get("parent"),
                q["difficulty"],
            ])

        sql = (
            f"insert into questions (document_id, question_text, ideal_answer, key_points, topic, parent, difficulty) "
            f"values {with_placeholders} "
            f"returning question_id, document_id, question_text, ideal_answer, key_points, topic, parent, difficulty"
        )
        rows = execute_returning_many(sql, params)
        if not rows:
            raise CustomException("Failed to insert questions", sys)
        return rows
    except Exception as e:
        raise CustomException(e, sys)

def load_all_documents(user_id):
    try:
        return fetch_all(
            "select document_id, filename, status, error, created_at, processed_at "
            "from documents where user_id = %s order by created_at desc",
            (user_id,),
        )
    except Exception as e:
        raise CustomException(e, sys)

def count_sessions_by_document(user_id: int) -> dict:
    """session_count per document, for the sidebar."""
    try:
        rows = fetch_all(
            "select document_id, count(*) as n from sessions where user_id = %s group by document_id",
            (user_id,),
        )
        return {row["document_id"]: row["n"] for row in rows}
    except Exception as e:
        raise CustomException(e, sys)

def count_topics(document_id: int) -> int:
    try:
        row = fetch_one(
            "select count(distinct topic) as n from chunks where document_id = %s",
            (document_id,),
        )
        return row["n"] if row else 0
    except Exception as e:
        raise CustomException(e, sys)

def count_distinct_topics_by_document(document_ids: list[int]) -> dict[int, int]:
    """Distinct topic count per document, batched.

    Used by the sidebar/library listing, which previously called
    getAllChunksTopics once per document in a loop - each call is its own
    round-trip to Neon, and those add up badly in serial (N documents meant
    N+1 network round-trips just for this one number). One query with
    document_id = ANY(...) does the same job in a single round-trip."""
    if not document_ids:
        return {}
    try:
        rows = fetch_all(
            """
            select document_id, count(distinct topic) as n
            from chunks
            where document_id = any(%s)
            group by document_id
            """,
            (document_ids,),
        )
        return {row["document_id"]: row["n"] for row in rows}
    except Exception as e:
        raise CustomException(e, sys)


def count_covered_topics_by_document(user_id: int, document_ids: list[int]) -> dict[int, int]:
    """Covered-topic count per document, batched - see
    count_distinct_topics_by_document for why this exists instead of calling
    get_covered_topics once per document."""
    if not document_ids:
        return {}
    try:
        rows = fetch_all(
            """
            select s.document_id, count(distinct t.topic) as n
            from turns t
            join sessions s on s.session_id = t.session_id
            where s.user_id = %s and s.document_id = any(%s) and t.verdict is not null
            group by s.document_id
            """,
            (user_id, document_ids),
        )
        return {row["document_id"]: row["n"] for row in rows}
    except Exception as e:
        raise CustomException(e, sys)


def get_covered_topics(user_id: int, document_id: int) -> list[str]:
    """Topics with at least one answered turn, across all of this user's
    sessions on the document. Coverage is derived from turns, never stored as
    a flag: a stored flag drifts when sessions are deleted, a query cannot."""
    try:
        rows = fetch_all(
            """
            select distinct t.topic
            from turns t
            join sessions s on s.session_id = t.session_id
            where s.user_id = %s and s.document_id = %s and t.verdict is not null
            order by t.topic
            """,
            (user_id, document_id),
        )
        return [row["topic"] for row in rows]
    except Exception as e:
        raise CustomException(e, sys)

def getAllTurnsTopics(user_id: int, document_id: int):
    try:
        return fetch_all(
            """
            select t.topic, t.verdict
            from turns t
            join sessions s on s.session_id = t.session_id
            where s.user_id = %s and s.document_id = %s and t.verdict is not null
            """,
            (user_id, document_id),
        )
    except Exception as e:
        raise CustomException(e, sys)

def getAllChunksTopics(document_id: int):
    """Every topic in the document, one row per chunk. Ordered by idx so the
    first occurrence of a topic is its earliest position in the document."""
    try:
        return fetch_all(
            "select topic, parent, idx from chunks where document_id = %s order by idx",
            (document_id,),
        )
    except Exception as e:
        raise CustomException(e, sys)

def getAllQuestionTopics(document_id: int):
    """Topics that have generated questions. A topic whose chunks were too
    short to generate from has no rows here, so it is unquizzable."""
    try:
        return fetch_all(
            "select topic from questions where document_id = %s",
            (document_id,),
        )
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

def topic_state(times_asked: int, accuracy: float | None) -> str:
    """Classify a topic for the selection screen.

    Decided here rather than in the frontend so "weak" means the same thing as
    it does in the session summary's weak_topics - both read the same
    threshold, and tuning it moves them together.

    'covered' alone is not enough: a topic answered 1/4 correct is exactly the
    one worth redoing, but a binary flag buries it alongside the 4/4 topics.
    """
    if times_asked == 0:
        return "new"
    return "weak" if accuracy < WEAK_TOPIC_ACCURACY else "mastered"


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
            # None rather than 0.0 when never asked: "never attempted" and
            # "attempted and got everything wrong" are different states.
            accuracy = correct_count / times_asked if times_asked else None
            topics.append({
                "topic": topic,
                "parent": parent,
                "question_count": question_counts.get(topic, 0),
                "times_asked": times_asked,
                "correct_count": correct_count,
                "covered": times_asked > 0,
                "accuracy": accuracy,
                "state": topic_state(times_asked, accuracy),
                # A topic whose chunks were too short to generate questions
                # from can never be quizzed; the UI should disable it rather
                # than let the user pick it and hit a 409.
                "quizzable": question_counts.get(topic, 0) > 0,
            })
        return topics
    except Exception as e:
        raise CustomException(e, sys)
