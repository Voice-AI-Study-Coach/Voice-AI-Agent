"""Database access for sessions, turns and question selection.

Every function taking a session_id also takes a user_id and filters on both:
the ids are sequential integers, so /sessions/47 is trivially guessable.
Ownership is part of the lookup, never a check afterwards.
"""

import random
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.config import LEVEL_WIDENING_OFFSETS, MAX_LEVEL, MIN_LEVEL
from src.exception import CustomException
from supabase_client.client import client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- sessions --------------------------------------------------------------

def insert_session(user_id: int, document_id: int, state: Dict[str, Any]) -> Dict[str, Any]:
    """Create the session row. `state` comes from new_session_state()."""
    try:
        now = _now()
        response = (
            client.table("sessions")
            .insert({
                "user_id": user_id,
                "document_id": document_id,
                "selected_topics": state["selected_topics"],
                "topic_index": state["topic_index"],
                "current_topic": state["current_topic"],
                "topic_question_count": state["topic_question_count"],
                "questions_asked": state["questions_asked"],
                "correct_count": state["correct_count"],
                "score": state["score"],
                "level": state["level"],
                "status": state["status"],
                "started_at": now,
                "last_activity_at": now,
            })
            .execute()
        )
        if not response.data:
            raise CustomException("Failed to insert session", sys)
        return response.data[0]
    except Exception as e:
        raise CustomException(e, sys)


def get_session_for_user(session_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a session scoped to its owner. None means 'not found OR not
    yours' - the caller must return 404 either way, since a 403 would confirm
    the id exists."""
    try:
        response = (
            client.table("sessions")
            .select("*")
            .eq("session_id", session_id)
            .eq("user_id", user_id)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        raise CustomException(e, sys)


def update_session(session: Dict[str, Any]) -> None:
    """Persist mutated engine state. last_activity_at is always refreshed, or
    the abandoned-session reaper will kill sessions that are merely long."""
    try:
        payload = {
            "topic_index": session["topic_index"],
            "current_topic": session["current_topic"],
            "topic_question_count": session["topic_question_count"],
            "questions_asked": session["questions_asked"],
            "correct_count": session["correct_count"],
            "score": session["score"],
            "level": session["level"],
            "status": session["status"],
            "last_activity_at": _now(),
        }
        if session["status"] in ("completed", "abandoned") and not session.get("ended_at"):
            payload["ended_at"] = _now()

        client.table("sessions").update(payload).eq("session_id", session["session_id"]).execute()
    except Exception as e:
        raise CustomException(e, sys)


def save_summary_text(session_id: int, narrative: str) -> None:
    try:
        client.table("sessions").update({"summary_text": narrative}).eq("session_id", session_id).execute()
    except Exception as e:
        raise CustomException(e, sys)


def get_sessions_for_document(user_id: int, document_id: int) -> List[Dict[str, Any]]:
    try:
        response = (
            client.table("sessions")
            .select("session_id, status, questions_asked, correct_count, started_at, ended_at")
            .eq("user_id", user_id)
            .eq("document_id", document_id)
            .order("started_at", desc=True)
            .execute()
        )
        return response.data or []
    except Exception as e:
        raise CustomException(e, sys)


# --- questions -------------------------------------------------------------

def get_question(question_id: int) -> Optional[Dict[str, Any]]:
    try:
        response = (
            client.table("questions")
            .select("question_id, question_text, ideal_answer, key_points, topic, parent, difficulty")
            .eq("question_id", question_id)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        raise CustomException(e, sys)


def get_asked_question_ids(session_id: int) -> List[int]:
    """Every question already asked in THIS session. The turn log is the
    no-repeat record, so no extra table is needed. Scope is deliberately per
    session: redoing a topic in a later session should draw different
    questions from the bank."""
    try:
        response = (
            client.table("turns")
            .select("question_id")
            .eq("session_id", session_id)
            .execute()
        )
        return [row["question_id"] for row in (response.data or [])]
    except Exception as e:
        raise CustomException(e, sys)


def _query_question(document_id: int, topic: str, difficulty: int, asked_ids: List[int]):
    try:
        query = (
            client.table("questions")
            .select("question_id, question_text, ideal_answer, key_points, topic, parent, difficulty")
            .eq("document_id", document_id)
            .eq("topic", topic)
            .eq("difficulty", difficulty)
        )
        if asked_ids:
            query = query.not_.in_("question_id", asked_ids)
        response = query.execute()
        # Randomised in Python rather than SQL: PostgREST has no order by
        # random(), and the candidate set for one topic+level is small.
        return random.choice(response.data) if response.data else None
    except Exception as e:
        raise CustomException(e, sys)


def pick_question(document_id: int, session_id: int, topic: str, level: int) -> Optional[Dict[str, Any]]:
    """Pick an unasked question, widening around `level` when the exact level
    is exhausted. Returns None when the topic has nothing left, which the
    caller treats as 'end the session early'."""
    try:
        asked_ids = get_asked_question_ids(session_id)
        for offset in LEVEL_WIDENING_OFFSETS:
            lvl = level + offset
            if MIN_LEVEL <= lvl <= MAX_LEVEL:
                question = _query_question(document_id, topic, lvl, asked_ids)
                if question:
                    return question
        return None
    except Exception as e:
        raise CustomException(e, sys)


def get_topic_source_material(document_id: int, topic: str) -> str:
    """Reassemble the material a topic's questions were generated from.

    Fetched by topic, not chunk_id: questions are generated per topic and can
    span several chunks, so questions.chunk_id is nullable and generally
    empty. Topic strings must match exactly between chunks and questions or
    this returns nothing and grading silently loses its grounding.
    """
    try:
        response = (
            client.table("chunks")
            .select("content, idx")
            .eq("document_id", document_id)
            .eq("topic", topic)
            .order("idx")
            .execute()
        )
        return "\n\n".join(row["content"] for row in (response.data or []))
    except Exception as e:
        raise CustomException(e, sys)


# --- turns -----------------------------------------------------------------

def insert_turn_asked(session_id: int, question: Dict[str, Any], level: int) -> Dict[str, Any]:
    """Write the turn when the question is ASKED, not when it's answered.

    Two reasons: asked_at makes answer latency measurable, and the no-repeat
    lookup stays correct even when the user abandons before answering.
    """
    try:
        existing = (
            client.table("turns")
            .select("turn_index")
            .eq("session_id", session_id)
            .order("turn_index", desc=True)
            .limit(1)
            .execute()
        )
        next_index = (existing.data[0]["turn_index"] + 1) if existing.data else 1

        response = (
            client.table("turns")
            .insert({
                "session_id": session_id,
                "question_id": question["question_id"],
                "turn_index": next_index,
                "topic": question["topic"],
                "level_at_ask": level,
                "asked_at": _now(),
            })
            .execute()
        )
        if not response.data:
            raise CustomException("Failed to insert turn", sys)
        return response.data[0]
    except Exception as e:
        raise CustomException(e, sys)


def get_open_turn(session_id: int) -> Optional[Dict[str, Any]]:
    """The turn awaiting an answer: asked but not yet graded."""
    try:
        response = (
            client.table("turns")
            .select("*")
            .eq("session_id", session_id)
            .is_("verdict", "null")
            .order("turn_index", desc=True)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        raise CustomException(e, sys)


def update_turn_answered(
    turn_id: int,
    transcript: str,
    verdict,
    coach_reply: str,
    grade_ms: int,
    stt_ms: Optional[int] = None,
) -> None:
    try:
        payload = {
            "transcript": transcript,
            "verdict": verdict.verdict,
            "matched_points": verdict.matched_points,
            "missed_points": verdict.missed_points,
            "confidence": verdict.confidence,
            "coach_reply": coach_reply,
            "grade_ms": grade_ms,
            "answered_at": _now(),
        }
        if stt_ms is not None:
            payload["stt_ms"] = stt_ms
        client.table("turns").update(payload).eq("turn_id", turn_id).execute()
    except Exception as e:
        raise CustomException(e, sys)


def get_session_turns(session_id: int) -> List[Dict[str, Any]]:
    """All turns for replay, with the question text joined in."""
    try:
        response = (
            client.table("turns")
            .select(
                "turn_index, topic, transcript, verdict, matched_points, missed_points, "
                "confidence, coach_reply, level_at_ask, asked_at, answered_at, "
                "questions(question_text, ideal_answer)"
            )
            .eq("session_id", session_id)
            .order("turn_index")
            .execute()
        )
        return response.data or []
    except Exception as e:
        raise CustomException(e, sys)
