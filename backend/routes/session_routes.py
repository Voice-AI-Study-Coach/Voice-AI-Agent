import logging
import sys
from typing import List

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.requests import Request
from fastapi.exceptions import HTTPException

from src.exception import CustomException
from backend.controllers.session_controllers import (
    handleGetSession,
    handleListSessions,
    handleSession,
    handleSessionSummary,
    handleSkipQuestion,
    handleSubmitAnswer,
    handleSubmitAnswerStreaming,
)
from backend.controllers.speech_controllers import SpeechStreamSession
from backend.middlewares.auth_middleware import verify_jwt, verify_jwt_ws
from llm.rotation_shifting import deepgram_pool

log = logging.getLogger(__name__)
from backend.models.session_schemas import (
    AnswerRequest,
    AnswerResponse,
    SessionListItem,
    SessionReplayResponse,
    SkipRequest,
    SkipResponse,
    StartSession,
    StartSessionResponse,
    SummaryResponse,
)

# Auth at the router level: session ids are sequential integers, so an
# unauthenticated route here would let anyone walk other users' sessions.
session_router = APIRouter(dependencies=[Depends(verify_jwt)])

# Separate router without the HTTP verify_jwt dependency above: that
# dependency expects a Request, and a WebSocket connection is not one. The
# WS route authenticates with verify_jwt_ws before accepting, exactly as
# speech_ws_router does.
session_ws_router = APIRouter()


@session_router.post("/sessions", status_code=201, response_model=StartSessionResponse)
def createSession(request: Request, session: StartSession):
    try:
        return handleSession(request=request, payload=session)
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)


@session_router.post("/sessions/{session_id}/answer", response_model=AnswerResponse)
async def submitAnswer(request: Request, session_id: int, answer: AnswerRequest):
    try:
        return await handleSubmitAnswer(
            request=request, session_id=session_id, payload=answer
        )
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)


@session_router.get("/sessions", response_model=List[SessionListItem])
def listSessions(request: Request, document_id: int):
    """Past sessions on one document, newest first. Feeds the sidebar."""
    try:
        return handleListSessions(request=request, document_id=document_id)
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)


@session_router.post("/sessions/{session_id}/skip", response_model=SkipResponse)
def skipQuestion(request: Request, session_id: int, skip: SkipRequest):
    """The student went quiet and was asked whether to move on. accepted=true
    draws a different question; accepted=false leaves the current one in place."""
    try:
        return handleSkipQuestion(request=request, session_id=session_id, payload=skip)
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)


@session_router.get("/sessions/{session_id}", response_model=SessionReplayResponse)
async def getSession(request: Request, session_id: int):
    try:
        return await handleGetSession(request=request, session_id=session_id)
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)


@session_router.get("/sessions/{session_id}/summary", response_model=SummaryResponse)
async def getSessionSummary(request: Request, session_id: int):
    try:
        return await handleSessionSummary(request=request, session_id=session_id)
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)


# --- Streaming answer (WebSocket) -------------------------------------------
#
# The same engine as POST /sessions/{id}/answer, but the coach's reply is
# streamed instead of awaited. On the POST path nothing reaches the browser
# until the whole reply exists, so text renders and only then does audio
# start; here each phrase is spoken while the rest is still being written.
#
# Wire protocol, client -> server:
#   {"transcript": "...", "stt_ms": 123}   answer the open turn
#
# Wire protocol, server -> client:
#   {"type": "phrase", "text": "..."}      the text of the next phrase
#   binary frames                          raw linear16 PCM, 24kHz, mono,
#                                           the audio for that same phrase
#   {"type": "phrase_end"}                 that phrase's audio is complete
#   {"type": "result", ...}                the full AnswerResponse payload
#   {"type": "error", "detail": "..."}     this answer failed; socket stays
#                                           open so the client can retry
#
# Audio and text share one socket deliberately: they are produced from a
# single pass over the coach stream, and splitting them across two
# connections would let them drift out of step.

@session_ws_router.websocket("/sessions/{session_id}/answer-stream")
async def submitAnswerStream(websocket: WebSocket, session_id: int):
    try:
        user = await verify_jwt_ws(websocket)
    except HTTPException as e:
        await websocket.close(code=4401, reason=e.detail)
        return
    except Exception:
        await websocket.close(code=1011, reason="Internal error")
        return

    await websocket.accept()
    log.info("sessions/answer-stream: connected user_id=%s session_id=%s",
             user["user_id"], session_id)

    speech: SpeechStreamSession | None = None
    try:
        while True:
            payload = await websocket.receive_json()
            if not isinstance(payload, dict) or "transcript" not in payload:
                await websocket.send_json(
                    {"type": "error", "detail": 'Expected {"transcript": "..."}'}
                )
                continue

            answer = AnswerRequest(
                transcript=payload.get("transcript") or "",
                stt_ms=payload.get("stt_ms"),
            )

            # Opened on first use and kept for the rest of the connection:
            # back-to-back coach lines then reuse one warm Deepgram socket
            # instead of paying connect cost per phrase.
            if speech is None:
                speech = SpeechStreamSession(deepgram_pool.get_key())

            async def on_chunk(text: str) -> None:
                # Each phrase goes out as a "phrase" frame carrying its text,
                # then the PCM for exactly that text. The client holds the
                # words until the audio in front of them has played, which is
                # what keeps the captions level with the voice rather than
                # racing ahead of it.
                await websocket.send_json({"type": "phrase", "text": text})
                # A TTS failure must not lose the answer: the turn is already
                # graded and scored by this point, so report the audio
                # problem and let the text carry the reply.
                try:
                    async for audio in speech.speak(text):
                        await websocket.send_bytes(audio)
                except Exception as e:
                    log.error("sessions/answer-stream: tts failed: %s", e)
                    await websocket.send_json(
                        {"type": "error", "detail": "Could not synthesize speech"}
                    )
                    return
                # Marks the end of this phrase's audio. Without it the client
                # cannot tell where one phrase's PCM stops and the next
                # begins, so it could not time the caption to it.
                await websocket.send_json({"type": "phrase_end"})

            try:
                result = await handleSubmitAnswerStreaming(
                    user_id=user["user_id"],
                    session_id=session_id,
                    payload=answer,
                    on_chunk=on_chunk,
                )
                await websocket.send_json({"type": "result", **result})
            except HTTPException as e:
                await websocket.send_json({"type": "error", "detail": e.detail})
            except Exception as e:
                log.error("sessions/answer-stream: answer failed: %s", e)
                await websocket.send_json(
                    {"type": "error", "detail": "Could not process the answer"}
                )
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error("sessions/answer-stream: connection failed: %s", e)
    finally:
        if speech is not None:
            speech.close()
        log.info("sessions/answer-stream: closed user_id=%s session_id=%s",
                 user["user_id"], session_id)
