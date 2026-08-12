from pydantic import BaseModel, Field


class SpeakRequest(BaseModel):
    """One coach line to render as speech.

    min_length=1 rejects an empty string here rather than letting it reach
    Deepgram and come back as an error the student cannot act on.
    """
    text: str = Field(min_length=1, description="The text to speak aloud")


class TranscribeResponse(BaseModel):
    """Result of transcribing one recorded answer.

    An empty transcript is a valid result, not an error: the quiz engine
    grades it as 'unclear', which costs the student nothing.
    """
    transcript: str
    duration_ms: int
