from __future__ import annotations

from typing import List

from langchain_groq import ChatGroq
from langchain_community.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage

from llm.prompts import grading_human_prompt, grading_system_prompt
from llm.schemas import GradeVerdict


class Grading:
    def __init__(self, model: str = 'llama3-8b-8192', temperature: float = 0.0):
        self.llm = ChatGroq(model=model, temperature=temperature)
        self.parser = PydanticOutputParser(pydantic_object=GradeVerdict)

    def grade_answer(
        self,
        question_text: str,
        ideal_answer: str,
        key_points: List[str],
        source_chunk: str,
        transcript: str,
    ) -> GradeVerdict:
        """Grade a spoken answer using the provided source chunk and key points."""
        if not transcript or not transcript.strip():
            return GradeVerdict(
                verdict='unclear',
                matched_points=[],
                missed_points=key_points,
                confidence=0.0,
                reasoning='Transcript was empty or missing, so the response could not be evaluated clearly.',
            )

        format_instructions = self.parser.get_format_instructions()
        system_prompt = grading_system_prompt(format_instructions)
        human_prompt = grading_human_prompt(
            question_text=question_text,
            ideal_answer=ideal_answer,
            key_points=key_points,
            source_chunk=source_chunk,
            transcript=transcript,
        )

        response = self.llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt),
            ]
        )
        return self.parser.parse(response.content)
