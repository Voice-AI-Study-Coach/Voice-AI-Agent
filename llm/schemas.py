from pydantic import BaseModel, Field
from typing import List, Literal,Annotated, Optional

class Section(BaseModel):
    start_line: int = Field(description="Line number where this topic starts")
    topic: str = Field(description="Short name for the topic")
    parent: Optional[str] = Field(default=None, description="Parent topic name, or null")

class Sections(BaseModel):
    sections: List[Section]

class GradeVerdict(BaseModel):
    verdict: Literal['correct', 'partial', 'wrong', 'dont_know', 'unclear']
    matched_points: List[str] = Field(default_factory=list)
    missed_points: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

    class Config:
        extra = 'forbid'
        anystr_strip_whitespace = True
