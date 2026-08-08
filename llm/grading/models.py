"""Session state and data models for Voice AI Study Coach."""

from __future__ import annotations
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from llm.schemas import GradeVerdict, Question


class Turn(BaseModel):
    """A single interaction in a session (question and answer cycle)."""
    turn_id: str = Field(description="Unique turn identifier")
    question: Question = Field(description="The question asked")
    transcript: str = Field(description="Student's spoken response (STT output)")
    verdict: GradeVerdict = Field(description="Grading verdict")
    coach_reply: str = Field(description="Coaching feedback")
    level_at_ask: int = Field(ge=1, le=5, description="Difficulty level when question was asked")
    timestamp: datetime = Field(default_factory=datetime.now)

    class Config:
        extra = 'forbid'


class SessionState(BaseModel):
    """Current state of a study session."""
    session_id: str = Field(description="Unique session identifier")
    user_id: Optional[str] = Field(default=None, description="User identifier if authenticated")
    
    # Topic progression
    current_topic: Optional[str] = Field(default=None, description="Current topic being studied")
    topic_question_count: int = Field(default=0, description="Number of questions asked on current topic")
    questions_per_topic: int = Field(default=5, description="Questions required per topic before advancing")
    
    # Scoring
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="Running weighted score")
    level: int = Field(default=1, ge=1, le=5, description="Current difficulty level 1-5")
    total_correct: int = Field(default=0, description="Total correct verdicts")
    total_partial: int = Field(default=0, description="Total partial verdicts")
    total_wrong: int = Field(default=0, description="Total wrong verdicts")
    total_unclear: int = Field(default=0, description="Total unclear verdicts (not counted)")
    
    # History
    turns: List[Turn] = Field(default_factory=list, description="All turns in session")
    asked_question_ids: List[str] = Field(default_factory=list, description="Questions already asked (by ID)")
    
    # Session metadata
    document_id: Optional[str] = Field(default=None, description="Source document ID")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        extra = 'forbid'


class Session:
    """In-memory session manager (can be extended to persist to database)."""
    
    def __init__(self, session_id: str, user_id: Optional[str] = None, document_id: Optional[str] = None):
        """Initialize a new session.
        
        Args:
            session_id: Unique identifier for this session
            user_id: Optional user identifier
            document_id: Optional source document ID
        """
        self.state = SessionState(
            session_id=session_id,
            user_id=user_id,
            document_id=document_id,
        )
    
    def add_turn(self, turn: Turn) -> None:
        """Add a turn to the session history.
        
        Args:
            turn: Turn object with question, transcript, verdict, and coaching
        """
        self.state.turns.append(turn)
        self.state.asked_question_ids.append(turn.question.question_id)
        self.state.updated_at = datetime.now()
    
    def get_state(self) -> SessionState:
        """Get current session state."""
        return self.state
    
    def update_state(self, **kwargs) -> None:
        """Update session state fields.
        
        Args:
            **kwargs: Fields to update (current_topic, level, score, etc.)
        """
        for key, value in kwargs.items():
            if hasattr(self.state, key):
                setattr(self.state, key, value)
        self.state.updated_at = datetime.now()
    
    def is_question_asked(self, question_id: str) -> bool:
        """Check if a question has been asked in this session.
        
        Args:
            question_id: The question ID to check
            
        Returns:
            True if question was already asked, False otherwise
        """
        return question_id in self.state.asked_question_ids
    
    def get_turns_for_topic(self, topic: str) -> List[Turn]:
        """Get all turns for a specific topic.
        
        Args:
            topic: Topic name
            
        Returns:
            List of Turn objects for that topic
        """
        return [t for t in self.state.turns if t.question.topic == topic]
