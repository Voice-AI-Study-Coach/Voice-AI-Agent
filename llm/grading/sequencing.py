"""Topic sequencing engine for progressive learning."""

from __future__ import annotations
import sys
from typing import Optional, List
from pydantic import BaseModel, Field

from src.exception import CustomException
from src.logger import logging
from llm.grading.models import SessionState


class TopicProgression(BaseModel):
    """Information about topic progression."""
    current_topic: Optional[str]
    questions_answered: int
    questions_remaining: int
    can_advance: bool
    reset_stats: bool  # Whether stats were reset when entering this topic


class SequencingEngine:
    """Manages topic progression and difficulty sequencing."""
    
    # Default questions per topic before advancing
    DEFAULT_QUESTIONS_PER_TOPIC = 5
    
    # Available topics (should come from document structure or config)
    # This is a placeholder - in real deployment, topics come from document ingestion
    
    @staticmethod
    def can_advance_topic(session_state: SessionState) -> bool:
        """Check if session can advance to next topic.
        
        Advancement requires:
        - Fixed number of questions answered on current topic
        - Not at end of curriculum
        
        Args:
            session_state: Current session state
            
        Returns:
            True if advancement is possible, False otherwise
        """
        try:
            if not session_state.current_topic:
                return False  # No topic set yet
            
            questions_answered = session_state.topic_question_count
            questions_required = session_state.questions_per_topic
            
            return questions_answered >= questions_required
            
        except Exception as e:
            raise CustomException(e, sys)
    
    @staticmethod
    def advance_topic(
        session_state: SessionState,
        new_topic: str,
        reset_level: bool = True,
        reset_score: bool = True,
    ) -> TopicProgression:
        """Advance to a new topic.
        
        When advancing:
        - Sets current_topic to new_topic
        - Resets topic_question_count to 0
        - Optionally resets level (default: yes)
        - Optionally resets score (default: yes)
        
        Do NOT carry difficulty from one topic to another.
        
        Args:
            session_state: Current session state
            new_topic: Name of new topic
            reset_level: Whether to reset difficulty level (default True)
            reset_score: Whether to reset running score (default True)
            
        Returns:
            TopicProgression with new state
            
        Raises:
            CustomException: If advancement fails
        """
        try:
            old_topic = session_state.current_topic
            old_level = session_state.level
            old_score = session_state.score
            
            # Set new topic
            session_state.current_topic = new_topic
            session_state.topic_question_count = 0
            
            # Reset level to starting difficulty
            if reset_level:
                session_state.level = 1
                logging.info(f"Topic changed from '{old_topic}' to '{new_topic}': level reset to 1")
            
            # Reset score to starting score
            if reset_score:
                session_state.score = 0.0
                logging.info(f"Topic changed to '{new_topic}': score reset to 0.0")
            
            return TopicProgression(
                current_topic=new_topic,
                questions_answered=0,
                questions_remaining=session_state.questions_per_topic,
                can_advance=False,
                reset_stats=reset_level or reset_score,
            )
            
        except Exception as e:
            raise CustomException(e, sys)
    
    @staticmethod
    def get_topic_progress(session_state: SessionState) -> TopicProgression:
        """Get current topic progress.
        
        Args:
            session_state: Current session state
            
        Returns:
            TopicProgression with current state
        """
        try:
            current_topic = session_state.current_topic
            questions_answered = session_state.topic_question_count
            questions_required = session_state.questions_per_topic
            questions_remaining = max(0, questions_required - questions_answered)
            
            return TopicProgression(
                current_topic=current_topic,
                questions_answered=questions_answered,
                questions_remaining=questions_remaining,
                can_advance=SequencingEngine.can_advance_topic(session_state),
                reset_stats=False,
            )
            
        except Exception as e:
            raise CustomException(e, sys)
    
    @staticmethod
    def increment_topic_question_count(session_state: SessionState) -> int:
        """Increment the question count for the current topic.
        
        Args:
            session_state: Current session state
            
        Returns:
            New question count for current topic
            
        Raises:
            CustomException: If increment fails
        """
        try:
            session_state.topic_question_count += 1
            return session_state.topic_question_count
        except Exception as e:
            raise CustomException(e, sys)
    
    @staticmethod
    def start_topic(
        session_state: SessionState,
        topic: str,
        questions_per_topic: int = DEFAULT_QUESTIONS_PER_TOPIC,
    ) -> TopicProgression:
        """Start a new topic (called when session begins or switching topics).
        
        Resets all progress counters for the topic.
        
        Args:
            session_state: Current session state
            topic: Name of topic to start
            questions_per_topic: Number of questions before advancing (default 5)
            
        Returns:
            TopicProgression with new state
            
        Raises:
            CustomException: If start fails
        """
        try:
            session_state.current_topic = topic
            session_state.topic_question_count = 0
            session_state.questions_per_topic = questions_per_topic
            session_state.level = 1  # Always start at level 1 for new topic
            session_state.score = 0.0  # Always start with 0.0 score
            
            logging.info(f"Started topic '{topic}' with {questions_per_topic} questions per topic")
            
            return TopicProgression(
                current_topic=topic,
                questions_answered=0,
                questions_remaining=questions_per_topic,
                can_advance=False,
                reset_stats=True,
            )
            
        except Exception as e:
            raise CustomException(e, sys)
    
    @staticmethod
    def get_available_topics(documents_sections: List) -> List[str]:
        """Get list of available topics from document sections.
        
        This would typically be called after document ingestion.
        
        Args:
            documents_sections: List of Section objects from document chunking
            
        Returns:
            List of unique topic names, sorted for consistent ordering
        """
        try:
            topics = set()
            for section in documents_sections:
                topics.add(section.topic)
            return sorted(list(topics))
        except Exception as e:
            raise CustomException(e, sys)
    
    @staticmethod
    def get_topic_hierarchy(documents_sections: List) -> dict:
        """Get parent-child topic hierarchy from document sections.
        
        Args:
            documents_sections: List of Section objects from document chunking
            
        Returns:
            Dictionary mapping topic name to parent topic (or None for top-level)
        """
        try:
            hierarchy = {}
            for section in documents_sections:
                if section.topic not in hierarchy:
                    hierarchy[section.topic] = section.parent
            return hierarchy
        except Exception as e:
            raise CustomException(e, sys)
