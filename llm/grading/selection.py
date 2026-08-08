"""Question selection engine for choosing appropriate questions by topic and difficulty."""

from __future__ import annotations
import sys
from typing import List, Optional, Tuple
import random

from src.exception import CustomException
from src.logger import logging
from llm.schemas import Question
from llm.grading.models import SessionState


class QuestionSelector:
    """Selects questions based on topic, difficulty, and session constraints."""
    
    # How far from target difficulty to search (difficulty range is 1-5)
    DIFFICULTY_SEARCH_RADIUS = 1
    
    @staticmethod
    def select_question(
        available_questions: List[Question],
        session_state: SessionState,
        target_topic: Optional[str] = None,
        target_difficulty: Optional[int] = None,
    ) -> Optional[Question]:
        """Select a question matching session constraints.
        
        Filters:
        1. Topic must match (or use current topic from session)
        2. Difficulty should match target (or use current level from session)
        3. Question must not have been asked in this session
        
        Fallback:
        - If no questions at exact difficulty, search nearby difficulty levels
        - If still no match, return None
        
        Args:
            available_questions: List of all available Question objects
            session_state: Current session state (contains topic, level, asked_question_ids)
            target_topic: Topic name (uses session.current_topic if None)
            target_difficulty: Difficulty 1-5 (uses session.level if None)
            
        Returns:
            Selected Question object, or None if no suitable question found
            
        Raises:
            CustomException: If selection fails
        """
        try:
            # Use session state if targets not provided
            if target_topic is None:
                target_topic = session_state.current_topic
            if target_difficulty is None:
                target_difficulty = session_state.level
            
            if not target_topic:
                logging.warning("No topic specified for question selection")
                return None
            
            # Filter by topic and unanswered status
            candidates = QuestionSelector._filter_by_topic_and_status(
                available_questions,
                target_topic,
                session_state.asked_question_ids
            )
            
            if not candidates:
                logging.warning(f"No unanswered questions for topic '{target_topic}'")
                return None
            
            # First try: exact difficulty match
            exact_match = QuestionSelector._filter_by_difficulty(
                candidates,
                target_difficulty
            )
            
            if exact_match:
                return random.choice(exact_match)
            
            # Second try: nearby difficulty levels
            nearby = QuestionSelector._find_nearby_difficulty_questions(
                candidates,
                target_difficulty,
                radius=QuestionSelector.DIFFICULTY_SEARCH_RADIUS
            )
            
            if nearby:
                logging.info(
                    f"No exact difficulty {target_difficulty} for topic '{target_topic}', "
                    f"using nearby difficulty from {[q.difficulty for q in nearby]}"
                )
                return random.choice(nearby)
            
            # Fallback: any unanswered question for this topic
            if candidates:
                logging.info(
                    f"No difficulty match, selecting from remaining candidates for topic '{target_topic}'"
                )
                return random.choice(candidates)
            
            return None
            
        except Exception as e:
            raise CustomException(e, sys)
    
    @staticmethod
    def _filter_by_topic_and_status(
        questions: List[Question],
        topic: str,
        asked_question_ids: List[str],
    ) -> List[Question]:
        """Filter questions by topic and exclude already-asked questions.
        
        Args:
            questions: All available questions
            topic: Target topic
            asked_question_ids: IDs of questions already asked in session
            
        Returns:
            Filtered list of unanswered questions for the topic
        """
        try:
            return [
                q for q in questions
                if q.topic == topic and q.question_id not in asked_question_ids
            ]
        except Exception as e:
            raise CustomException(e, sys)
    
    @staticmethod
    def _filter_by_difficulty(
        questions: List[Question],
        difficulty: int,
    ) -> List[Question]:
        """Filter questions by exact difficulty level.
        
        Args:
            questions: Questions to filter
            difficulty: Target difficulty (1-5)
            
        Returns:
            Questions matching exact difficulty
        """
        try:
            return [q for q in questions if q.difficulty == difficulty]
        except Exception as e:
            raise CustomException(e, sys)
    
    @staticmethod
    def _find_nearby_difficulty_questions(
        questions: List[Question],
        target_difficulty: int,
        radius: int = 1,
    ) -> List[Question]:
        """Find questions at nearby difficulty levels.
        
        Searches within [target_difficulty - radius, target_difficulty + radius],
        respecting boundaries [1, 5].
        
        Args:
            questions: Questions to search
            target_difficulty: Target difficulty (1-5)
            radius: Search radius (default 1)
            
        Returns:
            Questions within difficulty range, or empty list if none found
        """
        try:
            min_diff = max(1, target_difficulty - radius)
            max_diff = min(5, target_difficulty + radius)
            
            nearby = [
                q for q in questions
                if min_diff <= q.difficulty <= max_diff
            ]
            
            # Sort by distance from target (closer difficulty first)
            nearby.sort(
                key=lambda q: abs(q.difficulty - target_difficulty)
            )
            
            return nearby
            
        except Exception as e:
            raise CustomException(e, sys)
    
    @staticmethod
    def get_available_questions_for_topic(
        available_questions: List[Question],
        topic: str,
        asked_question_ids: List[str] = None,
    ) -> List[Question]:
        """Get all unanswered questions for a topic.
        
        Args:
            available_questions: All available questions
            topic: Target topic
            asked_question_ids: IDs of already-asked questions (optional)
            
        Returns:
            List of unanswered questions for the topic
        """
        try:
            if asked_question_ids is None:
                asked_question_ids = []
            
            return [
                q for q in available_questions
                if q.topic == topic and q.question_id not in asked_question_ids
            ]
            
        except Exception as e:
            raise CustomException(e, sys)
    
    @staticmethod
    def get_questions_by_difficulty_distribution(
        available_questions: List[Question],
        topic: str,
    ) -> dict:
        """Get distribution of questions by difficulty for a topic.
        
        Useful for understanding available questions and planning sequencing.
        
        Args:
            available_questions: All available questions
            topic: Target topic
            
        Returns:
            Dictionary mapping difficulty (1-5) to count of questions
        """
        try:
            distribution = {i: 0 for i in range(1, 6)}
            
            for q in available_questions:
                if q.topic == topic:
                    distribution[q.difficulty] += 1
            
            return distribution
            
        except Exception as e:
            raise CustomException(e, sys)
    
    @staticmethod
    def validate_questions_availability(
        available_questions: List[Question],
        required_topic: str,
        questions_per_difficulty: int = 2,
    ) -> Tuple[bool, str]:
        """Validate that enough questions exist for a topic.
        
        Checks that each difficulty level has minimum questions available.
        
        Args:
            available_questions: All available questions
            required_topic: Topic to validate
            questions_per_difficulty: Minimum questions per difficulty level (default 2)
            
        Returns:
            Tuple of (is_valid, message)
        """
        try:
            distribution = QuestionSelector.get_questions_by_difficulty_distribution(
                available_questions,
                required_topic
            )
            
            insufficient = []
            for difficulty, count in distribution.items():
                if count < questions_per_difficulty:
                    insufficient.append(
                        f"Difficulty {difficulty}: {count} (need {questions_per_difficulty})"
                    )
            
            if insufficient:
                message = f"Insufficient questions for topic '{required_topic}': {'; '.join(insufficient)}"
                return False, message
            
            message = f"Topic '{required_topic}' has sufficient questions: {distribution}"
            return True, message
            
        except Exception as e:
            raise CustomException(e, sys)
