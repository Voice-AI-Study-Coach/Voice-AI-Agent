"""Quiz session endpoints: start, answer, replay, summary.

The LLM never decides difficulty or what to ask next. It produces a verdict
and phrases a reply; score, level, topic advancement and question selection
are plain Python and SQL - deterministic, testable and explainable.
"""

import logging
import sys
import time
from typing import Any, Dict, List

from fastapi.requests import Request
from fastapi.exceptions import HTTPException

from backend.config import QUESTIONS_PER_TOPIC, WEAK_TOPIC_ACCURACY
from backend.utils.rag_utils import (
    get_document_for_user,
    getAllChunksTopics,
    getAllTurnsTopics,
)
from backend.utils.session_utils import (
    get_open_turn,
    get_question,
    get_session_for_user,
    get_session_turns,
    get_topic_source_material,
    insert_session,
    insert_turn_asked,
    pick_question,
    save_summary_text,
    update_session,
    update_turn_answered,
)
from llm.grading.coach import Coaching
from llm.grading.grade import Grading
from llm.grading.scoring import apply_verdict, new_session_state
from src.exception import CustomException

log = logging.getLogger(__name__)

_grader = Grading()
_coach = Coaching()


def _ordered_document_topics(document_id: int) -> List[str]:
    """Unique topics in document order (earliest chunk idx first)."""
    rows = getAllChunksTopics(document_id=document_id)
    seen = {}
    for row in rows:
        if row["topic"] not in seen:
            seen[row["topic"]] = row["parent"]
    return list(seen.keys())


def _question_out(question: Dict[str, Any], turn_index: int) -> Dict[str, Any]:
    """The subset of a question the client may see. ideal_answer and
    key_points are withheld while the question is still live."""
    return {
        "question_id": question["question_id"],
        "question_text": question["question_text"],
        "topic": question["topic"],
        "difficulty": question["difficulty"],
        "turn_index": turn_index,
    }


def handleSession(request: Request, payload) -> Dict[str, Any]:
    """POST /sessions - create a session on the selected topics and return the
    first question."""
    try:
        user_id = request.state.user["user_id"]
        document_id = payload.document_id

        # 1. ownership + readiness
        doc = get_document_for_user(document_id=document_id, user_id=user_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        if doc["status"] != "ready":
            raise HTTPException(
                status_code=409,
                detail=f"Document is not ready (status: {doc['status']})",
            )

        # 2. validate the topic names against the document.
        # Topic strings are the join key between chunks, questions and turns:
        # a typo or a stale name from a cached page produces a session that can
        # never find a question, and it fails confusingly several requests
        # later instead of immediately.
        ordered_topics = _ordered_document_topics(document_id)
        valid = set(ordered_topics)
        unknown = [t for t in payload.selected_topics if t not in valid]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown topics: {unknown}")

        # 3. order the selection by document order, not click order. The user
        # might tick "Semantic Analysis" before "Lexical Analysis"; quizzing in
        # click order would jump around the material.
        selected = set(payload.selected_topics)
        ordered = [t for t in ordered_topics if t in selected]

        # 4. create the session
        state = new_session_state(ordered)
        session = insert_session(user_id=user_id, document_id=document_id, state=state)
        session_id = session["session_id"]

        # 5. first question
        question = pick_question(
            document_id=document_id,
            session_id=session_id,
            topic=ordered[0],
            level=state["level"],
        )
        if question is None:
            raise HTTPException(
                status_code=409,
                detail=f"No questions available for topic '{ordered[0]}'",
            )

        # 6. the turn row is written when the question is ASKED, not answered:
        # it records asked_at for latency, and keeps the no-repeat lookup
        # correct even if the user abandons before answering.
        turn = insert_turn_asked(session_id, question, state["level"])

        log.info("handleSession: session_id=%s topics=%d first_topic=%s",
                 session_id, len(ordered), ordered[0])

        return {
            "session_id": session_id,
            "document_id": document_id,
            "filename": doc["filename"],
            "selected_topics": ordered,
            "total_questions": len(ordered) * QUESTIONS_PER_TOPIC,
            "current_topic": ordered[0],
            "question": _question_out(question, turn["turn_index"]),
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("handleSession: failed")
        raise CustomException(e, sys)


async def handleSubmitAnswer(request: Request, session_id: int, payload) -> Dict[str, Any]:
    """POST /sessions/{id}/answer - the engine. Every adaptive behaviour is here."""
    try:
        user_id = request.state.user["user_id"]

        session = get_session_for_user(session_id=session_id, user_id=user_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        if session["status"] != "active":
            raise HTTPException(status_code=409, detail="Session is not active")

        turn = get_open_turn(session_id)
        if turn is None:
            raise HTTPException(
                status_code=409, detail="No question is currently awaiting an answer"
            )

        question = get_question(turn["question_id"])
        if question is None:
            raise HTTPException(status_code=409, detail="The asked question no longer exists")

        # ---- 1. grade (LLM) -------------------------------------------------
        source_material = get_topic_source_material(session["document_id"], question["topic"])
        t0 = time.perf_counter()
        verdict = await _grader.grade_answer(
            question_text=question["question_text"],
            ideal_answer=question["ideal_answer"],
            key_points=question["key_points"],
            source_chunk=source_material,
            transcript=payload.transcript,
        )
        grade_ms = int((time.perf_counter() - t0) * 1000)

        # ---- 2. score, level, topic advancement (plain Python) --------------
        # 'unclear' is inert in here: no score change, no consumed question.
        flags = apply_verdict(session, verdict.verdict)
        topic_changed = flags["topic_changed"]
        session_complete = flags["session_complete"]

        # ---- 3. coach reply (LLM) -------------------------------------------
        coach_reply = await _coach.phrase_reaction(verdict, question)

        # ---- 4. persist ------------------------------------------------------
        # The turn row is written even for 'unclear', so the transcript
        # survives for debugging; the summary query filters those rows out.
        update_turn_answered(
            turn_id=turn["turn_id"],
            transcript=payload.transcript,
            verdict=verdict,
            coach_reply=coach_reply,
            grade_ms=grade_ms,
            stt_ms=payload.stt_ms,
        )
        update_session(session)

        # ---- 5. next question -------------------------------------------------
        next_question = None
        if not session_complete:
            nq = pick_question(
                document_id=session["document_id"],
                session_id=session_id,
                topic=session["current_topic"],
                level=session["level"],
            )
            if nq is None:
                # Topic exhausted with nothing left to ask: end cleanly rather
                # than leaving the session active with no way forward.
                session["status"] = "completed"
                update_session(session)
                session_complete = True
            else:
                next_turn = insert_turn_asked(session_id, nq, session["level"])
                next_question = _question_out(nq, next_turn["turn_index"])

        return {
            "verdict": verdict.verdict,
            "matched_points": verdict.matched_points,
            "missed_points": verdict.missed_points,
            "confidence": verdict.confidence,
            "coach_reply": coach_reply,
            "score": session["score"],
            "level": session["level"],
            "current_topic": session["current_topic"],
            "questions_asked": session["questions_asked"],
            "correct_count": session["correct_count"],
            "topic_changed": topic_changed,
            "session_complete": session_complete,
            "next_question": next_question,
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("handleSubmitAnswer: failed session_id=%s", session_id)
        raise CustomException(e, sys)


def handleGetSession(request: Request, session_id: int) -> Dict[str, Any]:
    """GET /sessions/{id} - replay a past session."""
    try:
        user_id = request.state.user["user_id"]
        session = get_session_for_user(session_id=session_id, user_id=user_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        doc = get_document_for_user(document_id=session["document_id"], user_id=user_id)
        rows = get_session_turns(session_id)

        turns = []
        for row in rows:
            question = row.get("questions") or {}
            turns.append({
                "turn_index": row["turn_index"],
                "topic": row["topic"],
                "question_text": question.get("question_text", ""),
                # Shown on purpose: in review mode the student is studying,
                # not being tested.
                "ideal_answer": question.get("ideal_answer", ""),
                "transcript": row.get("transcript"),
                "verdict": row.get("verdict"),
                "missed_points": row.get("missed_points") or [],
                "coach_reply": row.get("coach_reply"),
                "level_at_ask": row["level_at_ask"],
                "asked_at": row.get("asked_at"),
            })

        return {
            "session_id": session_id,
            "document_id": session["document_id"],
            "filename": doc["filename"] if doc else "",
            "status": session["status"],
            "selected_topics": session["selected_topics"],
            "questions_asked": session["questions_asked"],
            "correct_count": session["correct_count"],
            "started_at": session.get("started_at"),
            "ended_at": session.get("ended_at"),
            "turns": turns,
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("handleGetSession: failed session_id=%s", session_id)
        raise CustomException(e, sys)


def _duration_seconds(session: Dict[str, Any]):
    from datetime import datetime

    started, ended = session.get("started_at"), session.get("ended_at")
    if not started or not ended:
        return None
    try:
        t0 = datetime.fromisoformat(started.replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(ended.replace("Z", "+00:00"))
        return int((t1 - t0).total_seconds())
    except Exception:
        return None


async def handleSessionSummary(request: Request, session_id: int) -> Dict[str, Any]:
    """GET /sessions/{id}/summary - per-topic breakdown, weakest first."""
    try:
        user_id = request.state.user["user_id"]
        session = get_session_for_user(session_id=session_id, user_id=user_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        document_id = session["document_id"]
        doc = get_document_for_user(document_id=document_id, user_id=user_id)

        # 'unclear' turns are excluded throughout: they weren't the student's
        # fault and must not show up as misses.
        rows = get_session_turns(session_id)
        by_topic: Dict[str, Dict[str, int]] = {}
        parents: Dict[str, Any] = {}
        for row in rows:
            v = row.get("verdict")
            if v is None or v == "unclear":
                continue
            topic = row["topic"]
            stats = by_topic.setdefault(
                topic, {"asked": 0, "correct": 0, "partial": 0, "missed": 0}
            )
            stats["asked"] += 1
            if v == "correct":
                stats["correct"] += 1
            elif v == "partial":
                stats["partial"] += 1
            elif v in ("wrong", "dont_know"):
                stats["missed"] += 1
            parents.setdefault(topic, None)

        topic_results = [
            {
                "topic": topic,
                "parent": parents.get(topic),
                "asked": s["asked"],
                "correct": s["correct"],
                "partial": s["partial"],
                "missed": s["missed"],
                "accuracy": s["correct"] / s["asked"] if s["asked"] else 0.0,
            }
            for topic, s in by_topic.items()
        ]
        # Weakest first: the most actionable information belongs at the top.
        topic_results.sort(key=lambda t: t["accuracy"])

        total_asked = sum(t["asked"] for t in topic_results)
        total_correct = sum(t["correct"] for t in topic_results)

        # remaining_topics spans ALL of this user's sessions on the document,
        # not just this one - that is what makes the "continue?" loop work
        # across rounds.
        all_topics = _ordered_document_topics(document_id)
        covered = {r["topic"] for r in getAllTurnsTopics(user_id=user_id, document_id=document_id)}
        remaining_topics = [t for t in all_topics if t not in covered]

        # Narrative is generated once on completion and cached: regenerating
        # it every time an old session is reopened is slow and needlessly
        # expensive.
        narrative = session.get("summary_text")
        if narrative is None and session["status"] == "completed" and topic_results:
            narrative = await _generate_narrative(topic_results, total_asked, total_correct)
            if narrative:
                save_summary_text(session_id, narrative)

        return {
            "session_id": session_id,
            "filename": doc["filename"] if doc else "",
            "status": session["status"],
            "questions_asked": total_asked,
            "correct_count": total_correct,
            "overall_accuracy": total_correct / total_asked if total_asked else 0.0,
            "duration_seconds": _duration_seconds(session),
            "topic_results": topic_results,
            "weak_topics": [
                t["topic"] for t in topic_results if t["accuracy"] < WEAK_TOPIC_ACCURACY
            ],
            "narrative": narrative,
            "remaining_topics": remaining_topics,
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("handleSessionSummary: failed session_id=%s", session_id)
        raise CustomException(e, sys)


async def _generate_narrative(topic_results, total_asked: int, total_correct: int):
    """Short spoken wrap-up. Best-effort: a summary that fails to generate must
    not fail the whole endpoint, since every number is already in the response."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_groq import ChatGroq

        from llm.rotation_shifting import groq_pool

        lines = "\n".join(
            f"- {t['topic']}: {t['correct']}/{t['asked']} correct" for t in topic_results
        )
        key = groq_pool.get_key()
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.4, api_key=key)
        response = await llm.ainvoke([
            SystemMessage(content=(
                "You are a study coach summarising a completed quiz session. "
                "Write 2-3 plain sentences, spoken style, no markdown or bullet points. "
                "Name the strongest and weakest topics and suggest what to revisit."
            )),
            HumanMessage(content=f"Overall: {total_correct}/{total_asked} correct.\n\n{lines}"),
        ])
        groq_pool.mark_success(key)
        return str(response.content).strip()
    except Exception as e:
        log.warning("narrative generation failed: %s", e)
        return None
