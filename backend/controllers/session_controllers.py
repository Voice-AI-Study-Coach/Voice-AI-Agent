"""Quiz session endpoints: start, answer, replay, summary.

The LLM never decides difficulty or what to ask next. It produces a verdict
and phrases a reply; score, level, topic advancement and question selection
are plain Python and SQL - deterministic, testable and explainable.
"""

import asyncio
import logging
import sys
import time
from typing import Any, Dict, List
from datetime import datetime

from fastapi.requests import Request
from fastapi.exceptions import HTTPException

from backend.config import QUESTIONS_PER_TOPIC, WEAK_TOPIC_ACCURACY
from backend.utils.rag_utils import (
    get_document_for_user,
    getAllChunksTopics,
    getAllTurnsTopics,
)
from backend.utils.session_utils import (
    abandon_active_sessions_for_document,
    delete_turn,
    get_open_turn,
    get_question,
    get_prior_topic_results,
    get_session_for_user,
    get_session_turns,
    get_sessions_for_document,
    get_topic_source_material,
    insert_session,
    insert_turn_asked,
    pick_question,
    save_summary_text,
    touch_session,
    update_session,
    update_turn_answered,
)
from llm.grading.coach import Coaching
from llm.grading.grade import Grading
from llm.grading.scoring import apply_verdict, new_session_state
from llm.grading.speech_chunking import achunk_tokens
from llm.schemas import GradeVerdict
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
        if doc["status"] not in ("ready", "generating"):
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
        # An explicit "start fresh" retires any session the user left active
        # on this document first - otherwise it would sit around alongside
        # the new one, invisible, until the idle reaper eventually clears it.
        if payload.abandon_active:
            abandon_active_sessions_for_document(user_id=user_id, document_id=document_id)

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


async def _grade_and_score(user_id: int, session_id: int, payload) -> Dict[str, Any]:
    """Everything up to (but not including) the coach reply.

    Split out of handleSubmitAnswer so the streaming path can run the same
    grading and scoring without duplicating it: the coach is the only stage
    that differs between the two, and every adaptive decision here must stay
    identical whichever transport asked for it.

    Returns the pieces the caller needs to finish the turn.
    """
    # Both lookups key off session_id alone, so they go out together rather
    # than one after the other. The ownership check still gates everything
    # below - fetching the turn concurrently discloses nothing, because
    # nothing is returned until the session is confirmed to be this user's.
    session, turn = await asyncio.gather(
        asyncio.to_thread(
            get_session_for_user, session_id=session_id, user_id=user_id
        ),
        asyncio.to_thread(get_open_turn, session_id),
    )

    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] != "active":
        raise HTTPException(status_code=409, detail="Session is not active")

    if turn is None:
        raise HTTPException(
            status_code=409, detail="No question is currently awaiting an answer"
        )

    question = await asyncio.to_thread(get_question, turn["question_id"])
    if question is None:
        raise HTTPException(status_code=409, detail="The asked question no longer exists")

    # ---- 1. grade (LLM) -------------------------------------------------
    # The source material is only ever used to ground the grader, so it is not
    # needed at all when there is no transcript to grade. Fetching it
    # unconditionally spent a Neon round trip on every 'unclear' turn - the
    # exact case where the student is already being asked to repeat themselves
    # and latency is most visible.
    if not payload.transcript or not payload.transcript.strip():
        verdict = GradeVerdict(
            verdict="unclear",
            matched_points=[],
            missed_points=[],
            confidence=1.0,
            reasoning="No transcript was captured.",
        )
        grade_ms = 0
    else:
        t0 = time.perf_counter()
        source_material = await asyncio.to_thread(
            get_topic_source_material, session["document_id"], question["topic"]
        )
        verdict = await _grader.grade_answer(
            question_text=question["question_text"],
            ideal_answer=question["ideal_answer"],
            key_points=question["key_points"],
            source_chunk=source_material,
            transcript=payload.transcript,
        )
        grade_ms = int((time.perf_counter() - t0) * 1000)

        if verdict.verdict == "partial" and not verdict.missed_points:
            verdict.verdict = "correct"
        elif verdict.verdict == "correct" and verdict.missed_points:
            verdict.verdict = "partial"

    # ---- 2. score, level, topic advancement (plain Python) --------------
    flags = apply_verdict(session, verdict.verdict)

    return {
        "session": session,
        "turn": turn,
        "question": question,
        "verdict": verdict,
        "grade_ms": grade_ms,
        "topic_changed": flags["topic_changed"],
        "session_complete": flags["session_complete"],
    }


def _finish_turn(
    session_id: int,
    graded: Dict[str, Any],
    coach_reply: str,
    payload,
) -> Dict[str, Any]:
    """Persist the answered turn and pick what to ask next.

    The mirror of _grade_and_score: everything AFTER the coach reply, shared
    by both transports for the same reason.
    """
    session = graded["session"]
    turn = graded["turn"]
    question = graded["question"]
    verdict = graded["verdict"]
    session_complete = graded["session_complete"]

    # ---- 4. persist ------------------------------------------------------
    update_turn_answered(
        turn_id=turn["turn_id"],
        transcript=payload.transcript,
        verdict=verdict,
        coach_reply=coach_reply,
        grade_ms=graded["grade_ms"],
        stt_ms=payload.stt_ms,
    )
    update_session(session)

    # ---- 5. next question -------------------------------------------------
    next_question = None
    if verdict.verdict == "unclear":
        next_turn = insert_turn_asked(session_id, question, session["level"])
        next_question = _question_out(question, next_turn["turn_index"])
    elif not session_complete:
        nq = pick_question(
            document_id=session["document_id"],
            session_id=session_id,
            topic=session["current_topic"],
            level=session["level"],
        )
        if nq is None:
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
        "topic_changed": graded["topic_changed"],
        "session_complete": session_complete,
        "next_question": next_question,
    }


async def handleSubmitAnswer(request: Request, session_id: int, payload) -> Dict[str, Any]:
    """POST /sessions/{id}/answer - the engine. Every adaptive behaviour is here.

    Grades, scores, phrases the coach reply, persists, and picks the next
    question. The coach is awaited in full before this returns, so the caller
    receives one complete JSON payload; the WebSocket path in
    handleSubmitAnswerStreaming streams the same reply instead, for callers
    that want audio starting before the sentence is finished.
    """
    try:
        user_id = request.state.user["user_id"]
        graded = await _grade_and_score(user_id, session_id, payload)

        # ---- 3. coach reply (LLM) -------------------------------------------
        coach_reply = await _coach.phrase_reaction(graded["verdict"], graded["question"])

        return _finish_turn(session_id, graded, coach_reply, payload)
    except HTTPException:
        raise
    except Exception as e:
        log.exception("handleSubmitAnswer: failed session_id=%s", session_id)
        raise CustomException(e, sys)


async def handleSubmitAnswerStreaming(
    user_id: int,
    session_id: int,
    payload,
    on_chunk,
) -> Dict[str, Any]:
    """Answer a turn, streaming the coach reply instead of awaiting all of it.

    Same engine as handleSubmitAnswer - identical grading, scoring and
    selection - but the coach's reply is emitted as it is produced rather
    than after it is finished.

    on_chunk(text) is awaited once per speech-sized phrase, and is
    responsible for both halves of that phrase: sending its text and
    synthesising its audio. Text is deliberately NOT emitted per token.
    Tokens arrive as fast as the LLM writes them, which is far faster than
    speech - so rendering per token puts the words minutes ahead of the
    voice reading them. Emitting per phrase, paired with its own audio, is
    what lets the client reveal each phrase as it is spoken.

    Returns the same dict handleSubmitAnswer returns, for the caller to send
    once the stream is done.
    """
    try:
        graded = await _grade_and_score(user_id, session_id, payload)

        # ---- 3. coach reply (LLM, streamed) ---------------------------------
        parts: List[str] = []

        async def _tokens():
            async for token in _coach.stream_reaction(graded["verdict"], graded["question"]):
                parts.append(token)
                yield token

        t0 = time.perf_counter()
        first_chunk_ms = None
        async for chunk in achunk_tokens(_tokens()):
            if first_chunk_ms is None:
                first_chunk_ms = int((time.perf_counter() - t0) * 1000)
            await on_chunk(chunk)

        coach_reply = "".join(parts).strip()
        log.info(
            "handleSubmitAnswerStreaming: session_id=%s first coach chunk in %sms",
            session_id, first_chunk_ms,
        )

        # The persisted reply is the joined stream, so the turn row holds
        # exactly what the student heard.
        return _finish_turn(session_id, graded, coach_reply, payload)
    except HTTPException:
        raise
    except Exception as e:
        log.exception("handleSubmitAnswerStreaming: failed session_id=%s", session_id)
        raise CustomException(e, sys)


def handleListSessions(request: Request, document_id: int) -> List[Dict[str, Any]]:
    """GET /sessions?document_id=N - past sessions on one document, newest
    first. Feeds the sidebar, which nests them under each filename."""
    try:
        user_id = request.state.user["user_id"]

        # Ownership is checked on the document rather than the sessions: the
        # session query filters on user_id anyway, but a 404 here keeps a
        # guessed document_id from being distinguishable from an empty one.
        doc = get_document_for_user(document_id=document_id, user_id=user_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        return get_sessions_for_document(user_id=user_id, document_id=document_id)
    except HTTPException:
        raise
    except Exception as e:
        log.exception("handleListSessions: failed document_id=%s", document_id)
        raise CustomException(e, sys)


def handleSkipQuestion(request: Request, session_id: int, payload) -> Dict[str, Any]:
    """POST /sessions/{id}/skip - the student went quiet and was asked whether
    to move on.

    Silence is not an answer, so a skip is free: it does not score, does not
    consume one of the topic's questions, and does not touch the level. The
    unanswered turn row is deleted rather than graded, which also returns the
    question to the pool - they never really saw it through, so retiring it
    would quietly shrink the bank.

    The replies are fixed strings, not an LLM call: they are short, entirely
    predictable, and a student sitting in silence should not wait on a model.
    """
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

        # Declined: leave everything exactly as it is and let them keep thinking.
        if not payload.accepted:
            touch_session(session_id)
            return {
                "coach_reply": "Okay, no problem, take your time.",
                "skipped": False,
                "current_topic": session["current_topic"],
                "next_question": None,
            }

        # Accepted: retire this turn and draw a replacement on the same topic
        # and level.
        delete_turn(turn["turn_id"])

        # Excluded explicitly: deleting the turn puts this question back in
        # the pool immediately, and drawing it again is not a skip.
        nq = pick_question(
            document_id=session["document_id"],
            session_id=session_id,
            topic=session["current_topic"],
            level=session["level"],
            exclude_ids=[turn["question_id"]],
        )
        if nq is None:
            # Nothing else to ask on this topic. Put the original turn back so
            # the session still has a question awaiting an answer rather than
            # stranding the student with nothing on screen.
            question = get_question(turn["question_id"])
            if question is not None:
                restored = insert_turn_asked(session_id, question, turn["level_at_ask"])
                return {
                    "coach_reply": "That is the only question left on this topic, so let us stay with it.",
                    "skipped": False,
                    "current_topic": session["current_topic"],
                    "next_question": _question_out(question, restored["turn_index"]),
                }
            raise HTTPException(status_code=409, detail="No questions available to move on to")

        next_turn = insert_turn_asked(session_id, nq, session["level"])
        touch_session(session_id)

        log.info("handleSkipQuestion: session_id=%s skipped question_id=%s",
                 session_id, turn["question_id"])

        return {
            "coach_reply": "No problem, let us try a different one.",
            "skipped": True,
            "current_topic": session["current_topic"],
            "next_question": _question_out(nq, next_turn["turn_index"]),
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("handleSkipQuestion: failed session_id=%s", session_id)
        raise CustomException(e, sys)


async def handleGetSession(request: Request, session_id: int) -> Dict[str, Any]:
    """GET /sessions/{id} - replay a past session."""
    try:
        user_id = request.state.user["user_id"]
        # The turns key off session_id alone, so they are fetched alongside
        # the ownership check rather than after it; only the document lookup
        # genuinely depends on the session row.
        session, rows = await asyncio.gather(
            asyncio.to_thread(
                get_session_for_user, session_id=session_id, user_id=user_id
            ),
            asyncio.to_thread(get_session_turns, session_id),
        )
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        doc = await asyncio.to_thread(
            get_document_for_user, document_id=session["document_id"], user_id=user_id
        )

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
        session = await asyncio.to_thread(
            get_session_for_user, session_id=session_id, user_id=user_id
        )
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        document_id = session["document_id"]

        # Every query below depends only on session/document_id, never on each
        # other - so they go out together rather than one after another. Each
        # is a round trip to Neon (~0.5s warm), and run serially they were the
        # bulk of this endpoint's latency. They are sync functions, so each
        # occupies a threadpool slot for its round trip; gather lets the waits
        # overlap instead of queueing.
        (
            doc,
            rows,
            prior,
            all_topics,
            covered_rows,
        ) = await asyncio.gather(
            asyncio.to_thread(
                get_document_for_user, document_id=document_id, user_id=user_id
            ),
            asyncio.to_thread(get_session_turns, session_id),
            asyncio.to_thread(
                get_prior_topic_results,
                user_id=user_id,
                document_id=document_id,
                exclude_session_id=session_id,
            ),
            asyncio.to_thread(_ordered_document_topics, document_id),
            asyncio.to_thread(
                getAllTurnsTopics, user_id=user_id, document_id=document_id
            ),
        )

        # 'unclear' turns are excluded throughout: they weren't the student's
        # fault and must not show up as misses.
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

        # prior: how the same topics went in this user's earlier sessions on
        # this document, so a revisited topic reads as better or worse rather
        # than as an isolated score. Fetched in the gather above.

        topic_results = []
        for topic, s in by_topic.items():
            accuracy = s["correct"] / s["asked"] if s["asked"] else 0.0
            before = prior.get(topic)
            prev_accuracy = (
                before["correct"] / before["asked"]
                if before and before["asked"]
                else None
            )
            topic_results.append({
                "topic": topic,
                "parent": parents.get(topic),
                "asked": s["asked"],
                "correct": s["correct"],
                "partial": s["partial"],
                "missed": s["missed"],
                "accuracy": accuracy,
                "previous_accuracy": prev_accuracy,
                "previous_correct": before["correct"] if before else None,
                "previous_asked": before["asked"] if before else None,
                # None, not False, when there is nothing to compare against.
                "improved": accuracy > prev_accuracy if prev_accuracy is not None else None,
            })

        # Weakest first: the most actionable information belongs at the top.
        topic_results.sort(key=lambda t: t["accuracy"])
        has_comparison = any(t["previous_accuracy"] is not None for t in topic_results)

        # Median, not mean: a single slow call while a key was cooling down
        # would drag an average somewhere unrepresentative.
        grade_times = sorted(r["grade_ms"] for r in rows if r.get("grade_ms"))
        stt_times = sorted(r["stt_ms"] for r in rows if r.get("stt_ms"))
        median = lambda xs: int(xs[len(xs) // 2]) if xs else None

        total_asked = sum(t["asked"] for t in topic_results)
        total_correct = sum(t["correct"] for t in topic_results)

        # remaining_topics spans ALL of this user's sessions on the document,
        # not just this one - that is what makes the "continue?" loop work
        # across rounds.
        covered = {r["topic"] for r in covered_rows}
        remaining_topics = [t for t in all_topics if t not in covered]

        # Narrative is generated once on completion and cached: regenerating
        # it every time an old session is reopened is slow and needlessly
        # expensive.
        narrative = session.get("summary_text")
        if narrative is None and session["status"] == "completed" and topic_results:
            narrative = await _generate_narrative(topic_results, total_asked, total_correct)
            if narrative:
                await asyncio.to_thread(save_summary_text, session_id, narrative)

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
            "avg_response_ms": median(grade_times),
            "avg_stt_ms": median(stt_times),
            "has_comparison": has_comparison,
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

        def describe(t):
            line = f"- {t['topic']}: {t['correct']}/{t['asked']} correct"
            if t.get("previous_asked"):
                line += (
                    f" (last time {t['previous_correct']}/{t['previous_asked']})"
                )
            return line

        lines = "\n".join(describe(t) for t in topic_results)
        key = groq_pool.get_key()
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.4, api_key=key)
        response = await llm.ainvoke([
            SystemMessage(content=(
                "You are a study coach summarising a completed quiz session. "
                "Write 2-3 plain sentences, spoken style, no markdown or bullet points. "
                "Name the strongest and weakest topics and suggest what to revisit. "
                "Where a previous score is given, say plainly whether they improved "
                "on that topic, and be encouraging about progress."
            )),
            HumanMessage(content=f"Overall: {total_correct}/{total_asked} correct.\n\n{lines}"),
        ])
        groq_pool.mark_success(key)
        return str(response.content).strip()
    except Exception as e:
        log.warning("narrative generation failed: %s", e)
        return None
