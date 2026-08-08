"""Scoring engine for tracking student performance and difficulty progression."""

from __future__ import annotations
import sys
from typing import Tuple
from pydantic import BaseModel, Field

from src.exception import CustomException
from src.logger import logging
from llm.grading.models import SessionState, Turn


class ScoreUpdate(BaseModel):
    """Result of a score update."""
    previous_score: float
    new_score: float
    previous_level: int
    new_level: int
    points_earned: float
    verdict: str


class ScoringEngine:
    """Manages running score and difficulty level updates."""
    
    # Point values for each verdict
    POINTS_MAP = {
        "correct": 1.0,
        "partial": 0.5,
        "wrong": 0.0,
        "dont_know": 0.0,
        "unclear": 0.0,  # Unclear never affects score
    }
    
    # Adaptive scoring coefficients
    SCORE_ALPHA = 0.7  # Weight of previous score
    SCORE_BETA = 0.3   # Weight of new verdict points
    
    # Level thresholds
    LEVEL_UP_THRESHOLD = 0.75
    LEVEL_DOWN_THRESHOLD = 0.40
    
    # Level constraints
    MIN_LEVEL = 1
    MAX_LEVEL = 5
    
    @staticmethod
    def points_for_verdict(verdict: str) -> float:
        """Get point value for a verdict.
        
        Args:
            verdict: Verdict string ('correct', 'partial', 'wrong', 'dont_know', 'unclear')
            
        Returns:
            Points earned (0.0-1.0)
            
        Raises:
            CustomException: If verdict is invalid
        """
        try:
            if verdict not in ScoringEngine.POINTS_MAP:
                raise ValueError(f"Unknown verdict: {verdict}")
            return ScoringEngine.POINTS_MAP[verdict]
        except Exception as e:
            raise CustomException(e, sys)
    
    @staticmethod
    def update_score_and_level(
        previous_score: float,
        previous_level: int,
        verdict: str,
    ) -> Tuple[float, int]:
        """Update score using weighted formula and adjust level if needed.
        
        Scoring formula:
            new_score = 0.7 * previous_score + 0.3 * points_for_verdict(verdict)
            
        Level adjustment:
            - If new_score > 0.75: level += 1 (max 5)
            - If new_score < 0.40: level -= 1 (min 1)
            - Otherwise: level unchanged
            
        Special handling for 'unclear':
            - Verdict 'unclear' adds 0.0 points but does NOT affect score or level
            
        Args:
            previous_score: Previous score (0.0-1.0)
            previous_level: Previous level (1-5)
            verdict: Verdict string
            
        Returns:
            Tuple of (new_score, new_level)
            
        Raises:
            CustomException: If inputs are invalid
        """
        try:
            # Validate and normalize inputs
            if previous_score is None:
                previous_score = 0.0
            if previous_level is None:
                previous_level = 1
            
            prev_s = float(previous_score)
            if not (0.0 <= prev_s <= 1.0):
                raise ValueError(f"previous_score {prev_s} not in range [0.0, 1.0]")
            
            prev_l = int(previous_level)
            if not (1 <= prev_l <= 5):
                raise ValueError(f"previous_level {prev_l} not in range [1, 5]")
            
            # Special case: unclear verdict doesn't affect score or level
            if verdict == 'unclear':
                logging.info(f"Verdict 'unclear' - score and level unchanged")
                return prev_s, prev_l
            
            # Get points for verdict
            pts = ScoringEngine.points_for_verdict(verdict)
            
            # Update score using weighted formula
            new_score = (
                (ScoringEngine.SCORE_ALPHA * prev_s) +
                (ScoringEngine.SCORE_BETA * pts)
            )
            # Clamp to [0.0, 1.0]
            new_score = max(0.0, min(1.0, new_score))
            
            # Adjust level based on new score
            if new_score > ScoringEngine.LEVEL_UP_THRESHOLD:
                new_level = min(ScoringEngine.MAX_LEVEL, prev_l + 1)
            elif new_score < ScoringEngine.LEVEL_DOWN_THRESHOLD:
                new_level = max(ScoringEngine.MIN_LEVEL, prev_l - 1)
            else:
                new_level = prev_l
            
            return new_score, new_level
            
        except Exception as e:
            raise CustomException(e, sys)
    
    @staticmethod
    def apply_score_update(session_state: SessionState, verdict: str) -> ScoreUpdate:
        """Apply a score update to session state.
        
        Updates the session's score and level, and increments verdict counters.
        Note: 'unclear' verdicts do not affect score but are still counted.
        
        Args:
            session_state: Current session state
            verdict: The verdict to apply
            
        Returns:
            ScoreUpdate object with before/after values
            
        Raises:
            CustomException: If update fails
        """
        try:
            prev_score = session_state.score
            prev_level = session_state.level
            
            # Update score and level
            new_score, new_level = ScoringEngine.update_score_and_level(
                prev_score,
                prev_level,
                verdict
            )
            
            # Apply to session state
            session_state.score = new_score
            session_state.level = new_level
            
            # Update verdict counters
            if verdict == 'correct':
                session_state.total_correct += 1
            elif verdict == 'partial':
                session_state.total_partial += 1
            elif verdict == 'wrong':
                session_state.total_wrong += 1
            elif verdict == 'dont_know':
                session_state.total_wrong += 1  # Don't know is treated as wrong
            elif verdict == 'unclear':
                session_state.total_unclear += 1
            
            pts = ScoringEngine.points_for_verdict(verdict)
            
            return ScoreUpdate(
                previous_score=prev_score,
                new_score=new_score,
                previous_level=prev_level,
                new_level=new_level,
                points_earned=pts,
                verdict=verdict
            )
            
        except Exception as e:
            raise CustomException(e, sys)
    
    @staticmethod
    def get_score_summary(session_state: SessionState) -> dict:
        """Get a summary of session scoring stats.
        
        Args:
            session_state: Current session state
            
        Returns:
            Dictionary with scoring statistics
        """
        try:
            total_evaluated = (
                session_state.total_correct +
                session_state.total_partial +
                session_state.total_wrong
            )
            
            return {
                'current_score': session_state.score,
                'current_level': session_state.level,
                'correct': session_state.total_correct,
                'partial': session_state.total_partial,
                'wrong': session_state.total_wrong,
                'unclear': session_state.total_unclear,
                'total_evaluated': total_evaluated,
                'accuracy': (
                    (session_state.total_correct / total_evaluated)
                    if total_evaluated > 0 else 0.0
                ),
            }
        except Exception as e:
            raise CustomException(e, sys)
