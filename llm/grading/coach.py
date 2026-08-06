from __future__ import annotations

from typing import Any, Dict
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from llm.prompts import coaching_human_prompt, coaching_system_prompt
from llm.schemas import GradeVerdict


class Coaching:
    def __init__(self, model: str = 'llama3-8b-8192', temperature: float = 0.5):
        self.llm = ChatGroq(model=model, temperature=temperature)

    def phrase_reaction(self, verdict: GradeVerdict, question: Dict[str, Any]) -> str:
        """Generate concise spoken feedback based on the grading verdict."""
        question_text = (
            question.get('text')
            or question.get('question_text')
            or question.get('prompt')
            or str(question)
        )

        system_prompt = coaching_system_prompt()
        human_prompt = coaching_human_prompt(
            question_text=question_text,
            verdict=verdict.verdict,
            confidence=verdict.confidence,
            matched_points=verdict.matched_points,
            missed_points=verdict.missed_points,
        )

        response = self.llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt),
            ]
        )
        return str(response.content).strip()
