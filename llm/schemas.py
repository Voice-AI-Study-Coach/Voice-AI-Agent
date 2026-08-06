from pydantic import BaseModel, Field
from typing import List, Annotated, Optional

class Section(BaseModel):
    start_line: int = Field(description="Line number where this topic starts")
    topic: str = Field(description="Short name for the topic")
    parent: Optional[str] = Field(default=None, description="Parent topic name, or null")

class Sections(BaseModel):
    sections: List[Section]