"""Semantic grading engine for evaluating student answers.

Uses LLM to evaluate answers based on key semantic points, not keyword matching.
Never uses embeddings, cosine similarity, or string matching for grading.
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate

from llm.schemas import GradeVerdict
from src.logger import logging
from src.exception import CustomException
import sys


class Grading:
    """Semantic answer grading using LLM evaluation."""
    
    def __init__(self, model: str = "llama-3.3-70b-versatile"):
        """Initialize grading engine with deterministic LLM.
        
        Args:
            model: Groq model ID. Uses temperature=0 for deterministic output.
        """
        self.llm = ChatGroq(
            model=model,
            temperature=0,  # Deterministic for grading
            groq_api_key = os.getenv("GROQ_API_KEY") # Uses GROQ_API_KEY env var
            
        )
        self.parser = PydanticOutputParser(pydantic_object=GradeVerdict)
    
    def grade_answer(
        self,
        question_text: str,
        ideal_answer: str,
        key_points: List[str],
        source_chunk: str,
        transcript: str
    ) -> GradeVerdict:
        """Grade student answer against key semantic points.
        
        Args:
            question_text: The asked question
            ideal_answer: Complete correct answer
            key_points: List of 3-5 semantic key points (not keywords)
            source_chunk: Original source material for context
            transcript: Student's spoken/transcribed answer
        
        Returns:
            GradeVerdict with verdict, matched_points, missed_points, confidence
        
        Raises:
            CustomException: If grading fails
        """
        try:
            prompt = PromptTemplate(
                template="""You are an expert tutor grading a student's answer.

QUESTION: {question}

        response = self.llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt),
            ]
        )
        return self.parser.parse(response.content)

    @staticmethod
    def points_for_verdict(verdict: str) -> float:
        POINTS = {
            "correct": 1.0,
            "partial": 0.5,
            "wrong": 0.0,
            "dont_know": 0.0,
            "unclear": 0.0,
        }
        return POINTS.get(verdict, 0.0)

    @staticmethod
    def update_score_and_level(previous_score: float, previous_level: int, verdict: str):
        """Compute new_score and new_level using adaptive formula.

        new_score = 0.7 * previous_score + 0.3 * points_for_verdict(verdict)
        score clamped to [0.0, 1.0]
        Level update: >0.75 => +1 (max 5); <0.40 => -1 (min 1); otherwise unchanged.
        """
        # defensive defaults
        if previous_score is None:
            previous_score = 0.0
        if previous_level is None:
            previous_level = 1

        try:
            prev_s = float(previous_score)
            if not (0.0 <= prev_s <= 1.0):
                raise ValueError
        except Exception:
            raise ValueError("previous_score must be a number between 0.0 and 1.0")

        try:
            prev_l = int(previous_level)
            if not (1 <= prev_l <= 5):
                raise ValueError
        except Exception:
            raise ValueError("previous_level must be an int between 1 and 5")

        pts = Grading.points_for_verdict(verdict)
        new_score = (0.7 * prev_s) + (0.3 * float(pts))
        new_score = max(0.0, min(1.0, new_score))

        if new_score > 0.75:
            new_level = min(5, prev_l + 1)
        elif new_score < 0.40:
            new_level = max(1, prev_l - 1)
        else:
            new_level = prev_l

        return new_score, new_level



