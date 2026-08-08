"""Request routing module - classifies user input as answer or question.

Routes incoming requests to appropriate handler:
- If user is asking a question → route to RAG system
- If user is answering a posed question → route to grading system
"""

from __future__ import annotations
import sys
from typing import Literal, Optional
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from src.exception import CustomException
from src.logger import logging


class RouteDecision(BaseModel):
    """Decision output from the router."""
    route: Literal['answer', 'question']
    confidence: float
    reasoning: str


class RequestRouter:
    """Classifies user input as answer or question."""
    
    def __init__(self, model: str = 'llama3-8b-8192', temperature: float = 0.0):
        """Initialize router with LLM.
        
        Args:
            model: LLM model name
            temperature: Should be 0 for deterministic classification
        """
        self.llm = ChatGroq(model=model, temperature=temperature)
    
    def route(self, user_input: str, current_question: Optional[str] = None) -> Literal['answer', 'question']:
        """Route user input to answer or question handler.
        
        Args:
            user_input: The user's transcript or text input
            current_question: The current question text if one was asked, None if no active question
            
        Returns:
            'answer' if responding to posed question, 'question' if asking for info
            
        Raises:
            CustomException: If routing fails
        """
        try:
            if not user_input or not user_input.strip():
                logging.warning("Empty user input provided to router")
                return 'answer'  # Default to answer
            
            # If there's an active question and user is responding, assume it's an answer
            if current_question:
                confidence = self._estimate_relevance(user_input, current_question)
                if confidence > 0.3:  # Threshold for relevance
                    return 'answer'
            
            # Otherwise classify using LLM
            decision = self._classify_with_llm(user_input)
            return decision.route
            
        except Exception as e:
            raise CustomException(e, sys)
    
    def _classify_with_llm(self, user_input: str) -> RouteDecision:
        """Use LLM to classify input as answer or question.
        
        Args:
            user_input: The user's input text
            
        Returns:
            RouteDecision with route, confidence, and reasoning
        """
        try:
            system_prompt = (
                "You are a conversation router. Classify user input as either:\n"
                "- 'answer': A response to a question asked by someone else\n"
                "- 'question': A question or request for information from the user\n\n"
                "Rules:\n"
                "- If the input is a direct response (even partial), classify as 'answer'\n"
                "- If the input seeks clarification or information, classify as 'question'\n"
                "- If unclear, default to 'answer'\n\n"
                "Respond with JSON:\n"
                '{"route": "answer" or "question", "confidence": 0.0-1.0, "reasoning": "brief reason"}'
            )
            
            human_prompt = f"User input: {user_input}"
            
            response = self.llm.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=human_prompt),
                ]
            )
            
            # Parse response
            import json
            try:
                result = json.loads(response.content)
                return RouteDecision(
                    route=result.get('route', 'answer'),
                    confidence=float(result.get('confidence', 0.5)),
                    reasoning=result.get('reasoning', 'LLM classification')
                )
            except (json.JSONDecodeError, ValueError):
                logging.warning(f"Failed to parse router response: {response.content}")
                return RouteDecision(
                    route='answer',
                    confidence=0.3,
                    reasoning='Failed to parse LLM response, defaulted to answer'
                )
        except Exception as e:
            raise CustomException(e, sys)
    
    def _estimate_relevance(self, user_input: str, question: str) -> float:
        """Estimate how relevant user input is to the current question.
        
        This is a heuristic - if very high, we can assume it's answering.
        
        Args:
            user_input: The user's input
            question: The current question
            
        Returns:
            Relevance score 0.0-1.0
        """
        try:
            # Simple heuristic: check for key words from question
            question_words = set(question.lower().split())
            input_words = set(user_input.lower().split())
            
            # Remove common stop words
            stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'being',
                         'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
                         'should', 'could', 'may', 'might', 'can', 'and', 'or', 'but',
                         'if', 'in', 'on', 'at', 'to', 'for', 'of', 'by', 'with'}
            
            question_words -= stop_words
            input_words -= stop_words
            
            if not question_words:
                return 0.0
            
            overlap = len(input_words & question_words)
            return overlap / len(question_words)
            
        except Exception as e:
            logging.error(f"Error estimating relevance: {e}")
            return 0.0
