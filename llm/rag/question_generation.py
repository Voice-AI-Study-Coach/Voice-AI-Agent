"""Question generation from document sections and topics."""

from __future__ import annotations
import sys
import json
from typing import List
from langchain_groq import ChatGroq
from langchain_community.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage

from src.exception import CustomException
from src.logger import logging
from llm.schemas import Question


def question_generation_system_prompt(format_instructions: str, difficulty: int) -> str:
    """Generate system prompt for question generation LLM.
    
    Args:
        format_instructions: Pydantic format instructions for JSON output
        difficulty: Difficulty level 1-5
        
    Returns:
        System prompt string
    """
    difficulty_guidance = {
        1: "basic comprehension and recall of key concepts",
        2: "understanding of relationships between concepts",
        3: "application of concepts to new scenarios",
        4: "analysis and synthesis across multiple concepts",
        5: "evaluation, critique, and deep reasoning about concepts",
    }
    
    guidance = difficulty_guidance.get(difficulty, "conceptual understanding")
    
    return (
        f"You are an expert educational content creator. Generate a study question "
        f"for difficulty level {difficulty}/5 that requires {guidance}.\n\n"
        f"Rules:\n"
        f"- Create a question that tests understanding of the content provided\n"
        f"- Define 3-5 key points that a complete answer should include\n"
        f"- Write an ideal answer that covers all key points naturally\n"
        f"- Questions should be meaningful and not keyword-focused\n"
        f"- Key points should be semantic concepts, not exact phrases\n\n"
        f"Return only valid JSON matching this schema:\n{format_instructions}"
    )


def question_generation_human_prompt(topic: str, source_text: str, difficulty: int) -> str:
    """Generate human prompt for question generation.
    
    Args:
        topic: Topic name
        source_text: Text to generate question from
        difficulty: Difficulty level 1-5
        
    Returns:
        Human prompt string
    """
    return (
        f"Topic: {topic}\n"
        f"Difficulty: {difficulty}/5\n\n"
        f"Source Material:\n{source_text}\n\n"
        f"Generate a study question now. "
        f"Ensure the question and key points are grounded in the source material."
    )


class QuestionGenerator:
    """Generates study questions from document sections."""
    
    def __init__(self, model: str = 'llama3-8b-8192', temperature: float = 0.7):
        """Initialize question generator.
        
        Args:
            model: LLM model name (default: llama3-8b for variety)
            temperature: Should be >0 for varied question generation (default: 0.7)
        """
        self.llm = ChatGroq(model=model, temperature=temperature)
        self.parser = PydanticOutputParser(pydantic_object=Question)
    
    def generate_question(
        self,
        topic: str,
        source_text: str,
        difficulty: int = 2,
        document_id: str = None,
        chunk_id: str = None,
        parent_topic: str = None,
    ) -> Question:
        """Generate a single question from source material.
        
        Args:
            topic: Topic name
            source_text: Text to generate question from
            difficulty: Difficulty level 1-5 (default 2)
            document_id: Source document ID (optional)
            chunk_id: Source chunk ID (optional)
            parent_topic: Parent topic name (optional)
            
        Returns:
            Generated Question object
            
        Raises:
            CustomException: If generation fails
        """
        try:
            if not source_text or not source_text.strip():
                raise ValueError("source_text cannot be empty")
            
            if not (1 <= difficulty <= 5):
                raise ValueError(f"difficulty must be 1-5, got {difficulty}")
            
            format_instructions = self.parser.get_format_instructions()
            system_prompt = question_generation_system_prompt(format_instructions, difficulty)
            human_prompt = question_generation_human_prompt(topic, source_text, difficulty)
            
            response = self.llm.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=human_prompt),
                ]
            )
            
            # Parse response and add metadata
            question = self.parser.parse(response.content)
            
            # Ensure required fields are set
            if document_id:
                question.document_id = document_id
            if chunk_id:
                question.chunk_id = chunk_id
            if parent_topic:
                question.parent = parent_topic
            
            logging.info(f"Generated question for topic '{topic}' difficulty {difficulty}")
            return question
            
        except Exception as e:
            raise CustomException(e, sys)
    
    def generate_questions_for_topic(
        self,
        topic: str,
        source_text: str,
        num_questions_per_difficulty: int = 2,
        document_id: str = None,
        chunk_id: str = None,
        parent_topic: str = None,
    ) -> List[Question]:
        """Generate multiple questions at different difficulty levels for a topic.
        
        Args:
            topic: Topic name
            source_text: Text to generate questions from
            num_questions_per_difficulty: How many questions per difficulty level (1-5)
            document_id: Source document ID (optional)
            chunk_id: Source chunk ID (optional)
            parent_topic: Parent topic name (optional)
            
        Returns:
            List of generated Question objects (5 x num_questions_per_difficulty total)
            
        Raises:
            CustomException: If generation fails
        """
        try:
            questions = []
            
            for difficulty in range(1, 6):
                for _ in range(num_questions_per_difficulty):
                    question = self.generate_question(
                        topic=topic,
                        source_text=source_text,
                        difficulty=difficulty,
                        document_id=document_id,
                        chunk_id=chunk_id,
                        parent_topic=parent_topic,
                    )
                    questions.append(question)
            
            logging.info(
                f"Generated {len(questions)} questions for topic '{topic}' "
                f"({num_questions_per_difficulty} per difficulty level)"
            )
            return questions
            
        except Exception as e:
            raise CustomException(e, sys)
    
    def generate_questions_from_sections(
        self,
        sections: List[dict],
        num_questions_per_difficulty: int = 2,
        document_id: str = None,
    ) -> List[Question]:
        """Generate questions from document sections.
        
        Each section should have: topic, source_text, parent (optional)
        
        Args:
            sections: List of section dictionaries with 'topic', 'source_text', 'parent'
            num_questions_per_difficulty: Questions per difficulty level (default 2)
            document_id: Source document ID (optional)
            
        Returns:
            List of all generated Question objects
            
        Raises:
            CustomException: If generation fails
        """
        try:
            all_questions = []
            
            for section in sections:
                topic = section.get('topic')
                source_text = section.get('source_text')
                parent = section.get('parent')
                chunk_id = section.get('chunk_id')
                
                if not topic or not source_text:
                    logging.warning(f"Skipping section missing topic or source_text: {section}")
                    continue
                
                questions = self.generate_questions_for_topic(
                    topic=topic,
                    source_text=source_text,
                    num_questions_per_difficulty=num_questions_per_difficulty,
                    document_id=document_id,
                    chunk_id=chunk_id,
                    parent_topic=parent,
                )
                
                all_questions.extend(questions)
            
            logging.info(f"Generated {len(all_questions)} total questions from {len(sections)} sections")
            return all_questions
            
        except Exception as e:
            raise CustomException(e, sys)
