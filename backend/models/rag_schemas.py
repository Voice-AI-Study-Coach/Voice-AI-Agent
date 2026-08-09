from pydantic import BaseModel, Field
from typing import List, Optional


class TopicInfo(BaseModel):
    topic: str
    parent: Optional[str] = None
    question_count: int = Field(description="How many questions exist for this topic")
    covered: bool = Field(description="Has the user been quizzed on it before")
    times_asked: int = Field(description="Across all past sessions")
    correct_count: int = Field(description="Across all past sessions")
    # None, not 0.0, when never asked: "never attempted" and "attempted and
    # got everything wrong" are different states and the UI styles them
    # differently. A topic answered 1/4 correct is exactly the one worth redoing.
    accuracy: Optional[float] = Field(default=None, description="None if never asked")


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
    created_at: Optional[str] = None
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
