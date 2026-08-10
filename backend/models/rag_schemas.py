from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Literal, Optional

# psycopg returns timestamp columns as native datetime objects rather than the
# ISO strings the old Supabase/PostgREST client produced. Accepting either
# keeps response validation from rejecting a raw datetime.
Timestamp = Optional[datetime | str]


class TopicInfo(BaseModel):
    topic: str
    parent: Optional[str] = None
    question_count: int = Field(description="How many questions exist for this topic")
    quizzable: bool = Field(description="False when no questions were generated for it")
    covered: bool = Field(description="Has the user been quizzed on it before")
    times_asked: int = Field(description="Across all past sessions")
    correct_count: int = Field(description="Across all past sessions")
    # None, not 0.0, when never asked: "never attempted" and "attempted and
    # got everything wrong" are different states and the UI styles them
    # differently. A topic answered 1/4 correct is exactly the one worth redoing.
    accuracy: Optional[float] = Field(default=None, description="None if never asked")
    # Derived from accuracy against the same threshold the session summary
    # uses for weak_topics, so "weak" means one thing across the whole app.
    state: Literal["new", "weak", "mastered"] = Field(
        description="new = never attempted, weak = worth revisiting, mastered = solid"
    )


class DocumentTopicsResponse(BaseModel):
    document_id: int
    filename: str
    status: str
    total_topics: int
    covered_topics: int
    topics: List[TopicInfo]


class DocumentSummary(BaseModel):
    document_id: int
    filename: str
    status: str
    created_at: Timestamp = None
    total_topics: int
    covered_topics: int
    session_count: int


class NewChatResponse(BaseModel):
    document_id: int
    filename: str
    status: str
    already_seen: bool
    covered_topic_count: Optional[int] = None
    total_topic_count: Optional[int] = None
