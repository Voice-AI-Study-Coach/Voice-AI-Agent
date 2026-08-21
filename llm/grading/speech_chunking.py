"""Group streamed coach tokens into TTS-sized chunks.

The coach streams tokens one or two words at a time. Sending each one to
TTS separately sounds choppy - every fragment gets its own intonation
contour, so "That's not" / "quite right" reads as two clipped phrases
rather than one sentence. Waiting for the whole reply instead removes the
point of streaming at all.

So this buffers tokens and flushes at punctuation, with one asymmetry that
matters: the FIRST chunk is flushed as early as it can be (a comma will do,
or a long enough run of words), while later chunks wait for a sentence end.

That asymmetry is the whole trick. Only the wait before the first sound is
perceived as latency - once audio is playing, the student is listening, and
later chunks just have to arrive before playback catches up to them. A
short, slightly clipped opening phrase buys a much earlier start; clipping
the middle of a sentence buys nothing and sounds worse.
"""

from __future__ import annotations

from typing import AsyncIterator, Iterable, Iterator, List

# Sentence-final punctuation: a chunk may always be flushed here.
_SENTENCE_END = ".!?"

# Softer breaks, only good enough for the opening chunk.
_CLAUSE_END = ",;:"

# Below this a chunk is too short to carry its own intonation - flushing
# "Well," on its own sounds like a glitch, not a phrase. Applies to the
# first chunk too: it is a floor on eagerness, not a target.
MIN_FIRST_CHARS = 12

# If the opening has no punctuation at all (a coach line can easily run
# "That is completely fine and not knowing is okay"), flush anyway once
# enough words have accumulated rather than holding the whole sentence.
MAX_FIRST_CHARS = 60

# Later chunks: only used to bound a sentence that never terminates, e.g.
# a reply that ends without a full stop.
MAX_CHUNK_CHARS = 240

def _is_decimal_point(text: str, i: int) -> bool:
    """True when the '.' at index i belongs to a number rather than ending a
    sentence - either '0.6' with the digit already present, or '... 0.' with
    the digit still in flight. Splitting either way makes TTS misread it."""
    if i == 0 or not text[i - 1].isdigit():
        return False
    # digit follows -> definitely a decimal; nothing follows yet -> assume so
    return i + 1 >= len(text) or text[i + 1].isdigit()


def _split_point(buffer: str, is_first: bool) -> int:
    """Index just past the character to flush at, or -1 to keep buffering.

    Scans forward, so a chunk is cut at the EARLIEST usable boundary. That
    matters when a single token arrives already containing more than one
    sentence (a fast model, or split_text on a finished reply): cutting at
    the last boundary would hand TTS the whole thing as one piece and undo
    the point of chunking. The caller loops until no split point remains,
    so a multi-sentence buffer drains one sentence at a time.
    """
    stripped = buffer.rstrip()
    if not stripped:
        return -1

    limit = MAX_FIRST_CHARS if is_first else MAX_CHUNK_CHARS
    breaks = _SENTENCE_END + (_CLAUSE_END if is_first else "")
    floor = MIN_FIRST_CHARS if is_first else 0

    for i, ch in enumerate(stripped):
        if ch in breaks:
            if i + 1 < floor:
                # Boundary too early to be worth flushing on its own.
                continue
            if ch == "." and _is_decimal_point(stripped, i):
                continue
            return i + 1

    # No usable punctuation. Fall back to a length cap so a long
    # unpunctuated run still starts playing.
    if len(stripped) >= limit:
        # Break at the last word boundary so TTS never receives half a word.
        space = stripped.rfind(" ")
        if space >= floor:
            return space
    return -1


def chunk_tokens(tokens: Iterable[str]) -> Iterator[str]:
    """Group an iterable of tokens into TTS-ready chunks (sync).

    Yields each chunk as soon as it is complete, then whatever is left once
    the token stream ends - the tail is always flushed, punctuated or not,
    so the final words are never dropped.
    """
    buffer = ""
    is_first = True

    for token in tokens:
        if not token:
            continue
        buffer += token

        while True:
            cut = _split_point(buffer, is_first)
            if cut < 0:
                break
            chunk = buffer[:cut].strip()
            buffer = buffer[cut:].lstrip()
            if chunk:
                yield chunk
                is_first = False
            if not buffer:
                break

    tail = buffer.strip()
    if tail:
        yield tail


async def achunk_tokens(tokens: AsyncIterator[str]) -> AsyncIterator[str]:
    """Async form of chunk_tokens, for wrapping Coaching.stream_reaction.

    Usage:
        async for chunk in achunk_tokens(coach.stream_reaction(v, q)):
            await speech_session.speak(chunk)
    """
    buffer = ""
    is_first = True

    async for token in tokens:
        if not token:
            continue
        buffer += token

        while True:
            cut = _split_point(buffer, is_first)
            if cut < 0:
                break
            chunk = buffer[:cut].strip()
            buffer = buffer[cut:].lstrip()
            if chunk:
                yield chunk
                is_first = False
            if not buffer:
                break

    tail = buffer.strip()
    if tail:
        yield tail


def split_text(text: str) -> List[str]:
    """Chunk an already-complete string the same way a stream would.

    For the non-streaming path (phrase_reaction), where the reply is already
    whole but should still be sent to TTS in the same shaped pieces.
    """
    return list(chunk_tokens([text]))
