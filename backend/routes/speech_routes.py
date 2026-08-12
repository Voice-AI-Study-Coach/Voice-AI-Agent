import sys
import logging

from fastapi import APIRouter, Depends, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.requests import Request
from fastapi.responses import StreamingResponse
from fastapi.exceptions import HTTPException

from src.exception import CustomException
from backend.controllers.speech_controllers import (
    SpeechStreamSession,
    handleSynthesizeSpeech,
    handleTranscribeAudio,
)
from backend.middlewares.auth_middleware import verify_jwt, verify_jwt_ws
from backend.models.speech_schemas import SpeakRequest, TranscribeResponse
from llm.rotation_shifting import deepgram_pool

log = logging.getLogger(__name__)

speech_router = APIRouter(dependencies=[Depends(verify_jwt)])

# Separate router, deliberately without the HTTP verify_jwt dependency above:
# that dependency expects a Request, and a WebSocket connection is not one.
# The WS route authenticates itself via verify_jwt_ws instead, before
# accepting the connection.
speech_ws_router = APIRouter()


@speech_router.post("/speech/transcribe", response_model=TranscribeResponse)
async def transcribeAudio(request: Request, file: UploadFile = File(...)):
    """Transcribe a recorded answer. The browser records the audio; the text
    comes from Deepgram here, not from the client's own speech engine."""
    try:
        return await handleTranscribeAudio(request=request, file=file)
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)


def _speech_response(audio) -> StreamingResponse:
    """Stream mp3 back, rather than buffering the finished clip.

    Deepgram returns its first chunk well before the whole line is rendered,
    and browsers start playing an mp3 as it downloads - so streaming cuts
    seconds of silence before the coach is heard.
    """
    return StreamingResponse(
        audio,
        media_type="audio/mpeg",
        headers={
            # The same line is often heard twice (a repeated question, a
            # revisited turn), so let the browser reuse it.
            "Cache-Control": "private, max-age=3600",
            # Without this some browsers wait for a Content-Length that a
            # streamed response never sends.
            "X-Accel-Buffering": "no",
        },
    )


@speech_router.get("/speech/speak")
async def synthesizeSpeechStream(request: Request, text: str):
    """Speak a coach line, addressable as a plain URL.

    GET rather than POST so an <audio> element can point straight at it: the
    element then streams and plays progressively, whereas fetching the audio
    first would mean waiting for the entire download before any sound. Auth
    still applies - the access_token cookie rides along automatically.
    """
    try:
        audio = await handleSynthesizeSpeech(request=request, text=text)
        return _speech_response(audio)
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)


@speech_router.post("/speech/speak")
async def synthesizeSpeech(request: Request, payload: SpeakRequest):
    """Render a coach line as speech. Kept alongside the GET form for callers
    that would rather send the text in a body than a query string."""
    try:
        audio = await handleSynthesizeSpeech(request=request, text=payload.text)
        return _speech_response(audio)
    except HTTPException:
        raise
    except Exception as e:
        raise CustomException(e, sys)


# --- Streaming TTS (WebSocket) ----------------------------------------------
#
# Wire protocol, client -> server:
#   {"text": "..."}                     speak this line
#
# Wire protocol, server -> client:
#   binary frames                       raw linear16 PCM, 24kHz, mono - the
#                                        audio itself, as it is produced
#   {"type": "done"}                    this line finished; PCM frames alone
#                                        cannot signal end-of-utterance
#   {"type": "error", "detail": "..."}  this line failed; the socket stays
#                                        open for the next one
#
# One Deepgram TTS socket is opened lazily on the first line and reused for
# the lifetime of this WebSocket connection (see SpeechStreamSession) - not
# held open independent of use, since it costs nothing extra: it only exists
# while this connection exists, and closes the moment the browser does.

@speech_ws_router.websocket("/speech/speak-stream")
async def synthesizeSpeechStreamWs(websocket: WebSocket):
    try:
        user = await verify_jwt_ws(websocket)
    except HTTPException as e:
        # The handshake itself is rejected: no session, nothing to clean up.
        await websocket.close(code=4401, reason=e.detail)
        return
    except Exception:
        await websocket.close(code=1011, reason="Internal error")
        return

    await websocket.accept()
    log.info("speech/speak-stream: connected user_id=%s", user["user_id"])

    session: SpeechStreamSession | None = None
    try:
        while True:
            payload = await websocket.receive_json()
            text = payload.get("text") if isinstance(payload, dict) else None
            if not text:
                await websocket.send_json(
                    {"type": "error", "detail": "Expected {\"text\": \"...\"}"}
                )
                continue

            if session is None:
                # Deferred to first use rather than connect time: a browser
                # tab can open this socket well before the coach has
                # anything to say, and there is no reason to hold a Deepgram
                # connection open for that gap.
                session = SpeechStreamSession(deepgram_pool.get_key())

            try:
                async for chunk in session.speak(text):
                    await websocket.send_bytes(chunk)
                await websocket.send_json({"type": "done"})
            except HTTPException as e:
                await websocket.send_json({"type": "error", "detail": e.detail})
            except Exception as e:
                log.error("speech/speak-stream: line failed: %s", e)
                await websocket.send_json(
                    {"type": "error", "detail": "Could not synthesize speech"}
                )
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error("speech/speak-stream: connection failed: %s", e)
    finally:
        # Without this an abandoned browser tab (or a dropped connection
        # FastAPI catches as WebSocketDisconnect) would leave the Deepgram
        # socket open until Deepgram's own idle timeout eventually reaps it.
        if session is not None:
            session.close()
        log.info("speech/speak-stream: closed user_id=%s", user["user_id"])
