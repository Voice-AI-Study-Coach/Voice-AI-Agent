"""Coaching feedback engine for generating TTS-ready responses.

Phrases a reaction to an already-decided verdict. It never re-evaluates
correctness - the grader owns that - and it hedges its wording when the
grader's confidence was low.
"""

from __future__ import annotations

import sys
from typing import Any, AsyncIterator, Dict

from langchain_mistralai import ChatMistralAI
from langchain_core.messages import HumanMessage, SystemMessage

from llm.prompts import coaching_human_prompt, coaching_system_prompt
from llm.schemas import GradeVerdict
from llm.rotation_shifting import mistral_pool, is_rate_limit_error
from src.logger import logging
from src.exception import CustomException


class Coaching:
    """Generate spoken coaching feedback from a grading verdict."""

    def __init__(self, model: str = "open-mistral-7b", temperature: float = 0.5):
        # Warmer than the grader on purpose: this text is spoken aloud, and a
        # temperature-0 coach sounds robotic saying the same phrase every turn.
        self.model = model
        self.temperature = temperature

    def _llm(self):
        key = mistral_pool.get_key()
        return key, ChatMistralAI(model=self.model, temperature=self.temperature, api_key=key)

    async def phrase_reaction(self, verdict: GradeVerdict, question: Dict[str, Any]) -> str:
        """Turn a verdict into short spoken feedback (plain text, TTS-ready)."""
        try:
            question_text = (
                question.get("question_text")
                or question.get("text")
                or question.get("prompt")
                or str(question)
            )
            ideal_answer = question.get("ideal_answer") or ""

            messages = [
                SystemMessage(content=coaching_system_prompt()),
                HumanMessage(content=coaching_human_prompt(
                    question_text=question_text,
                    verdict=verdict.verdict,
                    confidence=verdict.confidence,
                    matched_points=verdict.matched_points,
                    missed_points=verdict.missed_points,
                    ideal_answer=ideal_answer,
                )),
            ]

            last_exc = None
            for _ in range(len(mistral_pool._keys)):
                key, llm = self._llm()
                try:
                    response = await llm.ainvoke(messages)
                    mistral_pool.mark_success(key)
                    return str(response.content).strip()
                except Exception as e:
                    if is_rate_limit_error(e):
                        mistral_pool.mark_rate_limited(key)
                        last_exc = e
                        continue
                    raise

            raise CustomException(last_exc or "All Mistral keys are rate-limited", sys)
        except Exception as e:
            logging.error(f"Error phrasing coach reply: {e}")
            raise CustomException(e, sys)

    async def stream_reaction(
        self, verdict: GradeVerdict, question: Dict[str, Any]
    ) -> AsyncIterator[str]:
        """Yield coach text chunks as soon as the LLM produces them.

        Callers can buffer these chunks until sentence boundaries and send
        each completed sentence to TTS without waiting for the whole reply.
        The normal phrase_reaction method remains available for the existing
        JSON endpoint and persistence path.
        """
        question_text = (
            question.get("question_text")
            or question.get("text")
            or question.get("prompt")
            or str(question)
        )
        ideal_answer = question.get("ideal_answer") or ""
        messages = [
            SystemMessage(content=coaching_system_prompt()),
            HumanMessage(content=coaching_human_prompt(
                question_text=question_text,
                verdict=verdict.verdict,
                confidence=verdict.confidence,
                matched_points=verdict.matched_points,
                missed_points=verdict.missed_points,
                ideal_answer=ideal_answer,
            )),
        ]
        last_exc = None
        for _ in range(len(mistral_pool._keys)):
            key, llm = self._llm()
            try:
                async for chunk in llm.astream(messages):
                    content = getattr(chunk, "content", "")
                    if content:
                        yield str(content)
                mistral_pool.mark_success(key)
                return
            except Exception as e:
                if is_rate_limit_error(e):
                    mistral_pool.mark_rate_limited(key)
                    last_exc = e
                    continue
                logging.error(f"Error streaming coach reply: {e}")
                raise CustomException(e, sys)
        raise CustomException(last_exc or "All Mistral keys are rate-limited", sys)
