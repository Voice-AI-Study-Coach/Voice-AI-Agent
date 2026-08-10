from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional

# psycopg returns timestamp columns as native datetime objects (the old
# Supabase/PostgREST client always serialised to ISO strings first). Response
# fields that carry a DB timestamp accept either so FastAPI's response
# validation does not reject a raw datetime - Pydantic still renders both as
# the same ISO 8601 string in the JSON body.
Timestamp = Optional[datetime | str]


class StartSession(BaseModel):
    document_id: int = Field(description="The id of the document")
    # min_length=1 rejects an empty selection here rather than letting it
    # become a session that can never pick a question.
    selected_topics: List[str] = Field(min_length=1, description="The topics selected by the user")


class QuestionOut(BaseModel):
    question_id: int
    question_text: str
    topic: str
    difficulty: int
    turn_index: int


class StartSessionResponse(BaseModel):
    session_id: int
    document_id: int
    filename: str
    selected_topics: List[str]
    total_questions: int
    current_topic: str
    question: QuestionOut


class AnswerRequest(BaseModel):
    transcript: str
    stt_ms: Optional[int] = Field(default=None, description="Speech-to-text latency, once audio exists")


class AnswerResponse(BaseModel):
    verdict: str
    matched_points: List[str]
    missed_points: List[str]
    confidence: float
    coach_reply: str

    score: float
    level: int
    current_topic: str
    questions_asked: int
    correct_count: int

    topic_changed: bool
    session_complete: bool
    next_question: Optional[QuestionOut] = None


class SessionListItem(BaseModel):
    """One row in the sidebar's list of past sessions on a document."""
    session_id: int
    status: str
    questions_asked: int
    correct_count: int
    started_at: Timestamp = None
    ended_at: Timestamp = None


class SkipRequest(BaseModel):
    # The frontend detects the silence (only the browser knows the mic has
    # been quiet) and asks "Shall we move to another question?". This carries
    # the student's reply back.
    accepted: bool = Field(description="True if the student agreed to move on")


class SkipResponse(BaseModel):
    coach_reply: str
    skipped: bool
    current_topic: str
    # Null when they declined - the original question stays on screen.
    next_question: Optional[QuestionOut] = None


class TurnOut(BaseModel):
    turn_index: int
    topic: str
    question_text: str
    # Included on purpose: in review mode the student is studying, not being
    # tested, so the correct answer is helpful rather than a spoiler.
    ideal_answer: str
    transcript: Optional[str] = None
    verdict: Optional[str] = None
    missed_points: List[str] = []
    coach_reply: Optional[str] = None
    level_at_ask: int
    asked_at: Timestamp = None


class SessionReplayResponse(BaseModel):
    session_id: int
    document_id: int
    filename: str
    status: str
    selected_topics: List[str]
    questions_asked: int
    correct_count: int
    started_at: Timestamp = None
    ended_at: Timestamp = None
    turns: List[TurnOut]


class TopicResult(BaseModel):
    topic: str
    parent: Optional[str] = None
    asked: int
    correct: int
    partial: int
    missed: int
    accuracy: float

    # Comparison against this user's earlier sessions on the same document.
    # All None when the topic has never been attempted before, which is the
    # difference between "no change" and "nothing to compare against".
    previous_accuracy: Optional[float] = None
    previous_correct: Optional[int] = None
    previous_asked: Optional[int] = None
    improved: Optional[bool] = Field(
        default=None, description="True if accuracy rose since the last attempt"
    )


class SummaryResponse(BaseModel):
    session_id: int
    filename: str
    status: str
    questions_asked: int
    correct_count: int
    overall_accuracy: float
    duration_seconds: Optional[int] = None
    topic_results: List[TopicResult]      # weakest first
    weak_topics: List[str]
    narrative: Optional[str] = None
    remaining_topics: List[str]           # powers the "continue?" prompt

    # Median rather than mean: one slow call while a key was rate-limited
    # would drag an average somewhere unrepresentative.
    avg_response_ms: Optional[int] = Field(
        default=None, description="Median grading latency across answered turns"
    )
    avg_stt_ms: Optional[int] = Field(
        default=None, description="Median speech-to-text latency, null until audio exists"
    )

    # True when this session revisited a topic the user had attempted before,
    # so the UI knows to show the comparison at all.
    has_comparison: bool = False
