from pydantic import BaseModel, Field
from typing import List, Annotated, Optional

class Section(BaseModel):
    start_line: int = Field(description="Line number where this topic starts")
    topic: str = Field(description="Short name for the topic")
    parent: Optional[str] = Field(default=None, description="Parent topic name, or null")

class Sections(BaseModel):
<<<<<<< HEAD
    sections: List[Section]
=======
    sections: List[Section]

class Question(BaseModel):
    """Question with key points for grading evaluation."""
    question_id: str = Field(description="Unique question identifier")
    question_text: str = Field(description="The question posed to the student")
    ideal_answer: str = Field(description="Model/ideal answer for reference")
    key_points: List[str] = Field(description="Key points that must be in a correct answer")
    topic: str = Field(description="Topic this question belongs to")
    parent: Optional[str] = Field(default=None, description="Parent topic")
    difficulty: int = Field(ge=1, le=5, description="Difficulty level 1-5")
    document_id: Optional[str] = Field(default=None, description="Source document ID")
    chunk_id: Optional[str] = Field(default=None, description="Source chunk ID (optional)")

    class Config:
        extra = 'forbid'
        anystr_strip_whitespace = True

class GradeVerdict(BaseModel):
    verdict: Literal['correct', 'partial', 'wrong', 'dont_know', 'unclear']
    matched_points: List[str] = Field(default_factory=list)
    missed_points: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

    class Config:
        extra = 'forbid'
        anystr_strip_whitespace = True
>>>>>>> 96dd823 (Adding the scoring pipeline)
