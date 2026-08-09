"""Adaptive scoring and topic progression.

Pure functions on a plain session dict - no database, no LLM, no I/O. The LLM
decides *what the answer was worth*; everything about difficulty, progression
and question selection is deterministic and testable right here.
"""

from __future__ import annotations

import sys
from typing import Any, Dict

from backend.config import (
    BASELINE_LEVEL,
    BASELINE_SCORE,
    LEVEL_DOWN_THRESHOLD,
    LEVEL_UP_THRESHOLD,
    MAX_LEVEL,
    MIN_LEVEL,
    POINTS,
    QUESTIONS_PER_TOPIC,
    SCORE_MEMORY,
)
from src.exception import CustomException
from src.logger import logging


def points_for_verdict(verdict: str) -> float:
    """Points a verdict is worth. 'unclear' has no entry and must be handled
    by the caller before it gets here."""
    return POINTS.get(verdict, 0.0)


def apply_verdict(session: Dict[str, Any], verdict: str) -> Dict[str, bool]:
    """Advance a session by one answered question, in place.

    Returns {"topic_changed": bool, "session_complete": bool}.

    'unclear' is completely inert: it means speech-to-text produced silence or
    garbage, which is a technical failure and not a wrong answer. Treating it
    as wrong would lower the score unfairly, burn one of the topic's four
    questions, and corrupt the summary's accuracy figures. The turn row is
    still written by the caller so the transcript survives for debugging.
    """
    try:
        if verdict == "unclear":
            return {"topic_changed": False, "session_complete": False}

        # --- score ---------------------------------------------------------
        # Keep most of the previous estimate and mix in how they just did, so
        # one bad answer after a good streak doesn't collapse the level.
        score = SCORE_MEMORY * float(session["score"]) + (1 - SCORE_MEMORY) * points_for_verdict(verdict)
        session["score"] = max(0.0, min(1.0, score))

        # --- level ---------------------------------------------------------
        # The gap between the thresholds is a dead band: without it a student
        # hovering near the boundary sees difficulty flip every single turn.
        if session["score"] > LEVEL_UP_THRESHOLD:
            session["level"] = min(MAX_LEVEL, session["level"] + 1)
        elif session["score"] < LEVEL_DOWN_THRESHOLD:
            session["level"] = max(MIN_LEVEL, session["level"] - 1)

        # --- counters ------------------------------------------------------
        session["topic_question_count"] += 1
        session["questions_asked"] += 1
        if verdict == "correct":
            session["correct_count"] += 1

        # --- topic progression ---------------------------------------------
        topic_changed = False
        session_complete = False

        if session["topic_question_count"] >= QUESTIONS_PER_TOPIC:
            session["topic_index"] += 1
            if session["topic_index"] < len(session["selected_topics"]):
                session["current_topic"] = session["selected_topics"][session["topic_index"]]
                session["topic_question_count"] = 0
                # Reset, never carry forward. Being wrong in the "too easy"
                # direction costs one question; being wrong in the "too hard
                # on unfamiliar material" direction costs the student's
                # confidence and tells us nothing true.
                session["level"] = BASELINE_LEVEL
                session["score"] = BASELINE_SCORE
                topic_changed = True
            else:
                session["status"] = "completed"
                session_complete = True

        return {"topic_changed": topic_changed, "session_complete": session_complete}
    except Exception as e:
        logging.error(f"Error applying verdict '{verdict}': {e}")
        raise CustomException(e, sys)


def new_session_state(selected_topics: list[str]) -> Dict[str, Any]:
    """Starting engine state for a fresh session."""
    return {
        "selected_topics": selected_topics,
        "topic_index": 0,
        "current_topic": selected_topics[0],
        "topic_question_count": 0,
        "questions_asked": 0,
        "correct_count": 0,
        "score": BASELINE_SCORE,
        "level": BASELINE_LEVEL,
        "status": "active",
    }
