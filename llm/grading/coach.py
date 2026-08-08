from __future__ import annotations
import os
from typing import Any, Dict
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from llm.prompts import coaching_human_prompt, coaching_system_prompt
from llm.schemas import GradeVerdict


class Coach:
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

"""Coaching feedback engine for generating TTS-ready responses.

Provides wording-based feedback and encouragement without re-evaluating correctness.
Hedges language when confidence is low.
"""

from typing import Dict, Any, Optional
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate

from llm.schemas import GradeVerdict
from src.logger import logging
from src.exception import CustomException
import sys


class Coaching:
    """Generate coaching feedback based on grading verdict."""
    
    def __init__(self, model: str = "llama-3.3-70b-versatile"):
        """Initialize coaching engine.
        
        Args:
            model: Groq model ID. Uses temperature=0.5 for balanced response.
        """
        self.llm = ChatGroq(
            model=model,
            temperature=0.5,  # Balanced: not deterministic, not too random
            groq_api_key = os.getenv("GROQ_API_KEY") # Uses GROQ_API_KEY env var
        )
    
    def phrase_reaction(self, verdict: GradeVerdict, context: Dict[str, Any]) -> str:
        """Generate TTS-ready coaching feedback.
        
        Args:
            verdict: GradeVerdict from grading engine
            context: Dict with 'text' (question/context)
        
        Returns:
            Spoken feedback string (TTS-ready, no special formatting)
        
        Important:
            - Never re-evaluates correctness (verdict is final)
            - Hedges language when confidence < 0.6
            - Always encouraging and constructive
            - Focuses on wording and explanation, not truth value
        
        Raises:
            CustomException: If coaching generation fails
        """
        try:
            # Determine hedging language based on confidence
            if verdict.confidence < 0.6:
                hedge = "It seems like you might be thinking about"
                suggest = "You could also consider"
            else:
                hedge = "You're on the right track with"
                suggest = "You've also shown understanding of"
            
            prompt = PromptTemplate(
                template="""You are a supportive tutor providing feedback on a student's answer.

STUDENT'S ANSWER: {context}

GRADING VERDICT: {verdict}
CONFIDENCE: {confidence}
REASONING: {reasoning}

HEDGE LANGUAGE: {hedge}
SUGGESTION LANGUAGE: {suggest}

Generate a brief, encouraging TTS-ready coaching response (1-2 sentences). 
- Use the hedge language provided
- Never re-evaluate if the answer was right/wrong (verdict is final)
- Focus on how they explained it and how to explain better
- Be warm and encouraging
- Make it sound natural when spoken (no markdown, no special formatting)

Coaching response:""",
                input_variables=["context", "verdict", "confidence", "reasoning", "hedge", "suggest"]
            )
            
            chain = prompt | self.llm
            
            response = chain.invoke({
                "context": context.get("text", ""),
                "verdict": verdict.verdict,
                "confidence": verdict.confidence,
                "reasoning": verdict.reasoning,
                "hedge": hedge,
                "suggest": suggest
            })
            
            # Extract text from response
            if hasattr(response, 'content'):
                feedback = response.content.strip()
            else:
                feedback = str(response).strip()
            
            logging.info(f"Generated coaching feedback for verdict={verdict.verdict}")
            return feedback
            
        except Exception as e:
            logging.error(f"Error generating coaching feedback: {str(e)}")
            raise CustomException(e, sys)
