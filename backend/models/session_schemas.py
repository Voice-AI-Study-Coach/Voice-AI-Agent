from pydantic import BaseModel, Field
from typing import List, Optional


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
    asked_at: Optional[str] = None


class SessionReplayResponse(BaseModel):
    session_id: int
    document_id: int
    filename: str
    status: str
    selected_topics: List[str]
    questions_asked: int
    correct_count: int
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    turns: List[TurnOut]


class TopicResult(BaseModel):
    topic: str
    parent: Optional[str] = None
    asked: int
    correct: int
    partial: int
    missed: int
    accuracy: float


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
