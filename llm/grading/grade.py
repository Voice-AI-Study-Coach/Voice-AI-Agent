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
            groq_api_key=None  # Uses GROQ_API_KEY env var
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

STUDENT ANSWER: {transcript}

SOURCE MATERIAL: {source}

IDEAL ANSWER: {ideal}

KEY SEMANTIC POINTS (not keywords - evaluate meaning, not wording):
{key_points_str}

Evaluate the student's answer against each key semantic point. A student demonstrates understanding of a point if they explain the concept in their own words, even if they use different terminology.

IMPORTANT: Never use keyword matching. Grade based on:
1. Whether they understand each concept
2. Whether they can explain it (even differently)
3. Whether they grasp relationships between ideas
4. Whether they show correct reasoning

Respond with confidence 0.0-1.0 based on how clearly they demonstrated understanding.

{format_instructions}""",
                input_variables=["question", "transcript", "source", "ideal", "key_points_str"],
                partial_variables={"format_instructions": self.parser.get_format_instructions()}
            )
            
            key_points_str = "\n".join([f"- {i+1}. {point}" for i, point in enumerate(key_points)])
            
            chain = prompt | self.llm | self.parser
            
            verdict = chain.invoke({
                "question": question_text,
                "transcript": transcript,
                "source": source_chunk,
                "ideal": ideal_answer,
                "key_points_str": key_points_str
            })
            
            logging.info(f"Graded answer: verdict={verdict.verdict}, confidence={verdict.confidence}")
            return verdict
            
        except Exception as e:
            logging.error(f"Error grading answer: {str(e)}")
            raise CustomException(e, sys)
    
    @staticmethod
    def points_for_verdict(verdict: str) -> float:
        """Convert verdict to points for scoring.
        
        Args:
            verdict: One of 'correct', 'partial', 'wrong', 'dont_know', 'unclear'
        
        Returns:
            Points: 1.0 for correct, 0.5 for partial, 0.0 otherwise
            Note: 'unclear' returns 0.0 and doesn't affect score
        """
        points_map = {
            "correct": 1.0,
            "partial": 0.5,
            "wrong": 0.0,
            "dont_know": 0.0,
            "unclear": 0.0
        }
        return points_map.get(verdict, 0.0)
