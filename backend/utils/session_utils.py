"""Database access for sessions, turns and question selection.

Every function taking a session_id also takes a user_id and filters on both:
the ids are sequential integers, so /sessions/47 is trivially guessable.
Ownership is part of the lookup, never a check afterwards.
"""

import json
import random
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.config import LEVEL_WIDENING_OFFSETS, MAX_LEVEL, MIN_LEVEL
from backend.db import execute, execute_returning, fetch_all, fetch_one
from src.exception import CustomException


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- sessions --------------------------------------------------------------

def insert_session(user_id: int, document_id: int, state: Dict[str, Any]) -> Dict[str, Any]:
    """Create the session row. `state` comes from new_session_state()."""
    try:
        now = _now()
        row = execute_returning(
            """
            insert into sessions (
                user_id, document_id, selected_topics, topic_index, current_topic,
                topic_question_count, questions_asked, correct_count, score, level,
                status, started_at, last_activity_at
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning *
            """,
            (
                user_id,
                document_id,
                json.dumps(state["selected_topics"]),
                state["topic_index"],
                state["current_topic"],
                state["topic_question_count"],
                state["questions_asked"],
                state["correct_count"],
                state["score"],
                state["level"],
                state["status"],
                now,
                now,
            ),
        )
        if not row:
            raise CustomException("Failed to insert session", sys)
        return row
    except Exception as e:
        raise CustomException(e, sys)


def get_session_for_user(session_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a session scoped to its owner. None means 'not found OR not
    yours' - the caller must return 404 either way, since a 403 would confirm
    the id exists."""
    try:
        return fetch_one(
            "select * from sessions where session_id = %s and user_id = %s",
            (session_id, user_id),
        )
    except Exception as e:
        raise CustomException(e, sys)


def update_session(session: Dict[str, Any]) -> None:
    """Persist mutated engine state. last_activity_at is always refreshed, or
    the abandoned-session reaper will kill sessions that are merely long."""
    try:
        ended_at = session.get("ended_at")
        if session["status"] in ("completed", "abandoned") and not ended_at:
            ended_at = _now()

        execute(
            """
            update sessions set
                topic_index = %s,
                current_topic = %s,
                topic_question_count = %s,
                questions_asked = %s,
                correct_count = %s,
                score = %s,
                level = %s,
                status = %s,
                last_activity_at = %s,
                ended_at = coalesce(%s, ended_at)
            where session_id = %s
            """,
            (
                session["topic_index"],
                session["current_topic"],
                session["topic_question_count"],
                session["questions_asked"],
                session["correct_count"],
                session["score"],
                session["level"],
                session["status"],
                _now(),
                ended_at,
                session["session_id"],
            ),
        )
    except Exception as e:
        raise CustomException(e, sys)


def save_summary_text(session_id: int, narrative: str) -> None:
    try:
        execute(
            "update sessions set summary_text = %s where session_id = %s",
            (narrative, session_id),
        )
    except Exception as e:
        raise CustomException(e, sys)


def get_sessions_for_document(user_id: int, document_id: int) -> List[Dict[str, Any]]:
    try:
        return fetch_all(
            """
            select session_id, status, questions_asked, correct_count, started_at, ended_at
            from sessions
            where user_id = %s and document_id = %s
            order by started_at desc
            """,
            (user_id, document_id),
        )
    except Exception as e:
        raise CustomException(e, sys)


# --- questions -------------------------------------------------------------

def get_question(question_id: int) -> Optional[Dict[str, Any]]:
    try:
        return fetch_one(
            """
            select question_id, question_text, ideal_answer, key_points, topic, parent, difficulty
            from questions where question_id = %s
            """,
            (question_id,),
        )
    except Exception as e:
        raise CustomException(e, sys)


def get_asked_question_ids(session_id: int) -> List[int]:
    """Every question already asked in THIS session. The turn log is the
    no-repeat record, so no extra table is needed. Scope is deliberately per
    session: redoing a topic in a later session should draw different
    questions from the bank."""
    try:
        rows = fetch_all(
            "select question_id from turns where session_id = %s",
            (session_id,),
        )
        return [row["question_id"] for row in rows]
    except Exception as e:
        raise CustomException(e, sys)


def _query_question(document_id: int, topic: str, difficulty: int, asked_ids: List[int]):
    try:
        if asked_ids:
            rows = fetch_all(
                """
                select question_id, question_text, ideal_answer, key_points, topic, parent, difficulty
                from questions
                where document_id = %s and topic = %s and difficulty = %s
                  and question_id != all(%s)
                """,
                (document_id, topic, difficulty, asked_ids),
            )
        else:
            rows = fetch_all(
                """
                select question_id, question_text, ideal_answer, key_points, topic, parent, difficulty
                from questions
                where document_id = %s and topic = %s and difficulty = %s
                """,
                (document_id, topic, difficulty),
            )
        # Randomised in Python: the candidate set for one topic+level is
        # small, and it keeps the SQL identical to the != all() form above
        # rather than needing `order by random()` as a separate path.
        return random.choice(rows) if rows else None
    except Exception as e:
        raise CustomException(e, sys)


def pick_question(
    document_id: int,
    session_id: int,
    topic: str,
    level: int,
    exclude_ids: Optional[List[int]] = None,
) -> Optional[Dict[str, Any]]:
    """Pick an unasked question, widening around `level` when the exact level
    is exhausted. Returns None when the topic has nothing left, which the
    caller treats as 'end the session early'.

    `exclude_ids` covers questions that are not in the turn log but still must
    not be drawn - a just-skipped question is eligible again the moment its
    turn row is deleted, and handing it straight back is not a skip.
    """
    try:
        asked_ids = get_asked_question_ids(session_id)
        if exclude_ids:
            asked_ids = list(set(asked_ids) | set(exclude_ids))
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
        rows = fetch_all(
            "select content from chunks where document_id = %s and topic = %s order by idx",
            (document_id, topic),
        )
        return "\n\n".join(row["content"] for row in rows)
    except Exception as e:
        raise CustomException(e, sys)


# --- turns -----------------------------------------------------------------

def insert_turn_asked(session_id: int, question: Dict[str, Any], level: int) -> Dict[str, Any]:
    """Write the turn when the question is ASKED, not when it's answered.

    Two reasons: asked_at makes answer latency measurable, and the no-repeat
    lookup stays correct even when the user abandons before answering.
    """
    try:
        row = execute_returning(
            """
            insert into turns (session_id, question_id, turn_index, topic, level_at_ask, asked_at)
            values (
                %(session_id)s, %(question_id)s,
                coalesce((select max(turn_index) from turns where session_id = %(session_id)s), 0) + 1,
                %(topic)s, %(level)s, %(now)s
            )
            returning *
            """,
            {
                "session_id": session_id,
                "question_id": question["question_id"],
                "topic": question["topic"],
                "level": level,
                "now": _now(),
            },
        )
        if not row:
            raise CustomException("Failed to insert turn", sys)
        return row
    except Exception as e:
        raise CustomException(e, sys)


def delete_turn(turn_id: int) -> None:
    """Drop an unanswered turn so its question returns to the pool.

    Used when a student skips after going silent: the skip must cost them
    nothing, and the no-repeat lookup reads the turn log, so leaving the row
    in place would quietly retire a question they never actually saw through.
    """
    try:
        execute("delete from turns where turn_id = %s", (turn_id,))
    except Exception as e:
        raise CustomException(e, sys)


def touch_session(session_id: int) -> None:
    """Refresh last_activity_at without touching engine state, so a student
    who is thinking (or skipping) is not reaped as abandoned."""
    try:
        execute(
            "update sessions set last_activity_at = %s where session_id = %s",
            (_now(), session_id),
        )
    except Exception as e:
        raise CustomException(e, sys)


def get_open_turn(session_id: int) -> Optional[Dict[str, Any]]:
    """The turn awaiting an answer: asked but not yet graded."""
    try:
        return fetch_one(
            """
            select * from turns
            where session_id = %s and verdict is null
            order by turn_index desc limit 1
            """,
            (session_id,),
        )
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
        execute(
            """
            update turns set
                transcript = %s,
                verdict = %s,
                matched_points = %s,
                missed_points = %s,
                confidence = %s,
                coach_reply = %s,
                grade_ms = %s,
                stt_ms = coalesce(%s, stt_ms),
                answered_at = %s
            where turn_id = %s
            """,
            (
                transcript,
                verdict.verdict,
                json.dumps(verdict.matched_points),
                json.dumps(verdict.missed_points),
                verdict.confidence,
                coach_reply,
                grade_ms,
                stt_ms,
                _now(),
                turn_id,
            ),
        )
    except Exception as e:
        raise CustomException(e, sys)


def get_prior_topic_results(
    user_id: int, document_id: int, exclude_session_id: int
) -> Dict[str, Dict[str, int]]:
    """Per-topic results from this user's EARLIER sessions on this document.

    Used to answer "did you improve?" on the summary. Scoped to everything
    except the session being viewed, so a topic redone in a later round is
    compared against the round before it rather than against itself.
    """
    try:
        rows = fetch_all(
            """
            select t.topic, t.verdict
            from turns t
            join sessions s on s.session_id = t.session_id
            where s.user_id = %s and s.document_id = %s and s.session_id != %s
              and t.verdict is not null and t.verdict != 'unclear'
            """,
            (user_id, document_id, exclude_session_id),
        )

        tally: Dict[str, Dict[str, int]] = {}
        for row in rows:
            stats = tally.setdefault(row["topic"], {"asked": 0, "correct": 0})
            stats["asked"] += 1
            if row["verdict"] == "correct":
                stats["correct"] += 1
        return tally
    except Exception as e:
        raise CustomException(e, sys)


def get_session_turns(session_id: int) -> List[Dict[str, Any]]:
    """All turns for replay, with the question text joined in."""
    try:
        rows = fetch_all(
            """
            select t.turn_index, t.topic, t.transcript, t.verdict, t.matched_points,
                   t.missed_points, t.confidence, t.coach_reply, t.level_at_ask,
                   t.asked_at, t.answered_at, t.grade_ms, t.stt_ms,
                   q.question_text, q.ideal_answer, q.parent as question_parent
            from turns t
            join questions q on q.question_id = t.question_id
            where t.session_id = %s
            order by t.turn_index
            """,
            (session_id,),
        )
        # Nested to match the shape callers already expect from the old
        # PostgREST embed (`questions(question_text, ideal_answer)`).
        for row in rows:
            row["questions"] = {
                "question_text": row.pop("question_text"),
                "ideal_answer": row.pop("ideal_answer"),
                "parent": row.pop("question_parent"),
            }
        return rows
    except Exception as e:
        raise CustomException(e, sys)
