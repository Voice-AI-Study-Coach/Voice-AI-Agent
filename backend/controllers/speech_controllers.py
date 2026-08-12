"""Server-side speech: transcription (Deepgram nova-3) and voice (aura-2).

Both run here rather than in the browser deliberately. Chrome's Web Speech API
streams audio to Google's servers from the client, so it fails with a bare
"network" error on any machine that cannot reach them - no transcript, no
diagnosis, nothing the app can do about it. Doing both server-side means speech
depends only on the backend's own network and our Deepgram keys, and the coach
sounds the same for every student rather than varying by browser.
"""

import sys
import asyncio
import time
from typing import AsyncIterator, Optional

import websockets.exceptions as ws_exceptions
from fastapi import HTTPException, UploadFile
from fastapi.requests import Request

from src.exception import CustomException
from src.logger import logging
from llm.rotation_shifting import deepgram_pool, is_rate_limit_error
from deepgram import DeepgramClient
from deepgram.speak.v1.types.speak_v1text import SpeakV1Text

# Below this a recording cannot contain decodable audio - a WebM/Opus header
# alone is larger. Catching it here avoids spending a Deepgram call, and a
# round trip, on a blob that is certain to be rejected.
MIN_AUDIO_BYTES = 1024

# Deepgram model names, kept here so the two halves of the speech stack are
# named in one place rather than scattered through call sites.
STT_MODEL = "nova-3"
TTS_MODEL = "aura-2-thalia-en"
# mp3 so the browser can play the response directly from an <audio> element
# with no decoding work of our own.
TTS_ENCODING = "mp3"

# The coach's replies are short; this only guards against a caller sending
# something unbounded, which Deepgram would reject anyway.
MAX_TTS_CHARS = 2000

# --- Streaming TTS (WebSocket) ---------------------------------------------
# aura-2 over speak.v1.connect() only accepts raw PCM, not mp3 - confirmed by
# a 400 from Deepgram when mp3 was tried on this path. 24kHz is aura-2's
# native rate; asking for anything else just makes Deepgram resample first.
TTS_WS_ENCODING = "linear16"
TTS_WS_SAMPLE_RATE = 24000

# Measured against the live API: an idle Deepgram TTS socket can be closed
# by the server (1011 "keepalive ping timeout") anywhere from ~30s to ~90s -
# the exact threshold was not consistent across runs, and on at least one
# run the socket was still silently open after 75s. Because of that
# inconsistency this code does not assume idle sockets close cleanly: speak()
# bounds every call with SPEAK_TIMEOUT_SECONDS and abandons (never reuses) a
# socket that stops responding instead of trusting a clean ConnectionClosed.
# Reconnecting is cheap relative to a quiz's pacing (seconds between an
# answer and the next coach line), so there is no value in fighting to keep
# one socket alive indefinitely - open one right before speaking, reuse it
# for back-to-back lines, and let a dead one just trigger a fresh connect.
SPEAK_TIMEOUT_SECONDS = 12.0


def _is_bad_request(exc: Exception) -> bool:
    """True when Deepgram rejected the request itself (4xx), rather than
    failing for a server-side or transport reason. The SDK raises typed
    errors, so prefer the status code and fall back to the class name."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return 400 <= status < 500
    return "BadRequest" in type(exc).__name__


async def handleTranscribeAudio(request: Request, file: UploadFile) -> dict:
    """Transcribe one recorded answer.

    Returns {"transcript": str, "duration_ms": int}. An empty transcript is a
    valid result - the quiz engine grades it as 'unclear', which costs the
    student nothing - so silence is not an error here.
    """
    if file is None:
        raise HTTPException(status_code=400, detail="No audio file was provided")

    try:
        payload = await file.read()
    except Exception as e:
        raise CustomException(e, sys)

    if not payload:
        raise HTTPException(status_code=400, detail="The audio upload was empty")

    # A recording this short is a truncated capture, not speech. Treat it as
    # silence rather than an error: the engine grades an empty transcript as
    # 'unclear', which costs the student nothing and asks them to repeat.
    if len(payload) < MIN_AUDIO_BYTES:
        logging.info(
            "handleTranscribeAudio: %d bytes is too short to transcribe", len(payload)
        )
        return {"transcript": "", "duration_ms": 0}

    started_at = time.time()

    # Fetch the key per call, never cached: a key held across calls cannot
    # rotate away once it gets cooled down.
    last_exc = None
    for _ in range(len(deepgram_pool._keys)):
        key = deepgram_pool.get_key()
        try:
            dg = DeepgramClient(api_key=key)
            # transcribe_file is sync and blocking; keep it off the event loop.
            response = await asyncio.to_thread(
                dg.listen.v1.media.transcribe_file,
                request=payload,
                model=STT_MODEL,
                language="en",
                smart_format=True,
                punctuate=True,
            )
            deepgram_pool.mark_success(key)

            transcript = ""
            results = getattr(response, "results", None)
            channels = getattr(results, "channels", None) if results else None
            if channels:
                for channel in channels:
                    for alternative in channel.alternatives or []:
                        if getattr(alternative, "transcript", None):
                            transcript = alternative.transcript
                            break
                    if transcript:
                        break

            duration_ms = int(round((time.time() - started_at) * 1000))
            logging.info(
                "handleTranscribeAudio: %d bytes -> %d chars in %dms",
                len(payload), len(transcript), duration_ms,
            )
            return {"transcript": transcript, "duration_ms": duration_ms}

        except Exception as e:
            if is_rate_limit_error(e):
                deepgram_pool.mark_rate_limited(key)
                last_exc = e
                continue

            # Deepgram rejects audio it cannot decode ("corrupt or unsupported
            # data"), which happens when the browser sends a truncated or
            # empty recording - a client problem, not a server fault. Report
            # it as a 400 with the reason instead of a bare 500, which said
            # nothing about what went wrong.
            detail = getattr(e, "body", None) or str(e)
            if "corrupt or unsupported" in str(detail).lower() or _is_bad_request(e):
                logging.warning(
                    "handleTranscribeAudio: rejected %d bytes of audio: %s",
                    len(payload), str(detail)[:200],
                )
                raise HTTPException(
                    status_code=400,
                    detail="The recording could not be read as audio",
                )

            logging.error("handleTranscribeAudio: transcription failed: %s", e)
            raise CustomException(e, sys)

    raise CustomException(last_exc or "All Deepgram keys are rate-limited", sys)


async def handleSynthesizeSpeech(request: Request, text: str) -> AsyncIterator[bytes]:
    """Render the coach's line as speech with Deepgram aura-2.

    Yields mp3 chunks as they arrive rather than returning the finished file.
    Deepgram delivers its first chunk in roughly a third of the time it takes
    to render the whole clip, so buffering the response here would make the
    student wait ~3s for audio that could have started at ~1s. The browser
    plays a streamed mp3 as it downloads, so the difference is audible.
    """
    spoken = (text or "").strip()
    if not spoken:
        raise HTTPException(status_code=400, detail="No text was provided")
    if len(spoken) > MAX_TTS_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Text exceeds the {MAX_TTS_CHARS} character limit",
        )

    started_at = time.time()
    key = deepgram_pool.get_key()

    def _open_stream(api_key: str):
        dg = DeepgramClient(api_key=api_key)
        return dg.speak.v1.audio.generate(
            text=spoken,
            model=TTS_MODEL,
            encoding=TTS_ENCODING,
        )

    try:
        # Opening the stream is the blocking network call; keep it off the loop.
        chunks = await asyncio.to_thread(_open_stream, key)
    except Exception as e:
        if is_rate_limit_error(e):
            deepgram_pool.mark_rate_limited(key)
        logging.error("handleSynthesizeSpeech: synthesis failed: %s", e)
        raise CustomException(e, sys)

    async def stream() -> AsyncIterator[bytes]:
        total = 0
        first_chunk_ms = None
        iterator = iter(chunks)
        while True:
            # next() blocks waiting on the wire, so each pull goes to a thread
            # too - otherwise the whole server stalls while the coach speaks.
            chunk = await asyncio.to_thread(next, iterator, None)
            if chunk is None:
                break
            if first_chunk_ms is None:
                first_chunk_ms = int(round((time.time() - started_at) * 1000))
            total += len(chunk)
            yield chunk

        deepgram_pool.mark_success(key)
        logging.info(
            "handleSynthesizeSpeech: %d chars -> %d bytes, first chunk %sms, total %dms",
            len(spoken), total, first_chunk_ms,
            int(round((time.time() - started_at) * 1000)),
        )

    return stream()


class SpeechStreamSession:
    """One Deepgram TTS WebSocket, opened lazily and reused across however
    many coach lines a single browser connection sends.

    Not a session-wide keepalive: Deepgram closes an idle TTS socket well
    under a minute (measured), and a quiz's own pacing already leaves gaps
    that long between replies. So this only guarantees the socket is open
    *during* one line - if it was dropped for being idle, speak() just
    reconnects, which costs the same ~1.5-1.8s a cold REST call would have
    cost anyway. What is saved is the case that actually matters: several
    coach lines close together (e.g. a quick 'unclear' retry followed by the
    next verdict) reuse the same open socket at ~350-450ms each instead of
    paying full connect cost every time.
    """

    def __init__(self, key: str):
        self._key = key
        self._client = DeepgramClient(api_key=key)
        self._socket = None  # type: ignore[var-annotated]
        self._ctx = None

    def _connect_sync(self):
        ctx = self._client.speak.v1.connect(
            model=TTS_MODEL,
            encoding=TTS_WS_ENCODING,
            sample_rate=TTS_WS_SAMPLE_RATE,
        )
        socket = ctx.__enter__()
        return ctx, socket

    async def _ensure_connected(self) -> None:
        if self._socket is not None:
            return
        # Opening the socket does a real network handshake; keep it off the
        # event loop like every other blocking Deepgram call in this file.
        self._ctx, self._socket = await asyncio.to_thread(self._connect_sync)

    def _drop(self) -> None:
        """Forget the socket without re-raising close errors - it may
        already be gone server-side, which is exactly the case this exists
        to recover from."""
        ctx, self._ctx, self._socket = self._ctx, None, None
        if ctx is not None:
            try:
                ctx.__exit__(None, None, None)
            except Exception:
                pass

    def _abandon(self) -> None:
        """Forget the socket WITHOUT touching it.

        Used when a call to it timed out rather than closing cleanly - the
        background thread that made the call may still be blocked inside
        send/recv on this exact object. Calling ctx.__exit__ here would race
        that thread over the same connection; unlike _drop(), this leaves
        the object for the OS/garbage collector rather than the pool.
        """
        self._ctx = None
        self._socket = None

    def _speak_sync(self, text: str):
        """Send one line and collect every message Deepgram sends back for
        it, up to and including Flushed. Runs in a thread: send/recv on the
        socket are both blocking calls."""
        socket = self._socket
        socket.send_text(SpeakV1Text(text=text))
        socket.send_flush()
        audio_chunks: list[bytes] = []
        while True:
            message = socket.recv()
            if isinstance(message, (bytes, bytearray)):
                audio_chunks.append(bytes(message))
                continue
            kind = type(message).__name__
            if kind == "SpeakV1Flushed":
                return audio_chunks
            if kind == "SpeakV1Warning":
                logging.warning("SpeechStreamSession: Deepgram warning: %s", message)
            # Metadata / Cleared - informational, not a stopping point.

    async def speak(self, text: str) -> AsyncIterator[bytes]:
        """Speak one line, yielding raw linear16 PCM chunks as they are
        produced. Reconnects once, transparently, if the socket had been
        closed (idle timeout or a transient drop) since the last line.

        Measured against the live API, an idle socket's failure mode is not
        always a clean close: send/recv can also just hang on a connection
        Deepgram has abandoned server-side, rather than raising promptly.
        wait_for bounds that, but cancelling the await does not stop the
        underlying thread (Python cannot force-kill one) - so a timeout
        means this socket is abandoned outright, never reused, rather than
        risking a second call racing a zombie thread still touching it.
        """
        spoken = (text or "").strip()
        if not spoken:
            raise HTTPException(status_code=400, detail="No text was provided")
        if len(spoken) > MAX_TTS_CHARS:
            raise HTTPException(
                status_code=400,
                detail=f"Text exceeds the {MAX_TTS_CHARS} character limit",
            )

        for attempt in range(2):
            await self._ensure_connected()
            try:
                chunks = await asyncio.wait_for(
                    asyncio.to_thread(self._speak_sync, spoken),
                    timeout=SPEAK_TIMEOUT_SECONDS,
                )
                deepgram_pool.mark_success(self._key)
                for chunk in chunks:
                    yield chunk
                return
            except ws_exceptions.ConnectionClosed:
                # The common, well-behaved case: the socket sat idle past
                # Deepgram's timeout and was closed cleanly. Drop it and
                # retry once on a fresh connection rather than failing the
                # line outright.
                self._drop()
                if attempt == 1:
                    raise
            except asyncio.TimeoutError:
                # The socket did not close cleanly, it just stopped
                # responding - abandon it (never reused) and surface this as
                # unavailable rather than retrying against the same thread
                # that may still be blocked on it.
                self._abandon()
                logging.error(
                    "SpeechStreamSession.speak: no response within %ss, abandoning socket",
                    SPEAK_TIMEOUT_SECONDS,
                )
                raise CustomException(
                    TimeoutError("Deepgram TTS stream stopped responding"), sys
                )
            except Exception as e:
                self._drop()
                if is_rate_limit_error(e):
                    deepgram_pool.mark_rate_limited(self._key)
                logging.error("SpeechStreamSession.speak failed: %s", e)
                raise CustomException(e, sys)

    def close(self) -> None:
        """Release the Deepgram socket. Call when the browser's own
        connection closes - an orphaned socket would otherwise sit open
        until Deepgram's own idle timeout eventually reaps it."""
        self._drop()
