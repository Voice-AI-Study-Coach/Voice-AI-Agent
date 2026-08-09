"""Semantic grading engine for evaluating student answers.

Uses an LLM to evaluate answers against key semantic points. Never uses
embeddings, cosine similarity, or string matching for grading - a correct
answer phrased differently must still be graded correct.
"""

import sys
from typing import List

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser

from llm.schemas import GradeVerdict
from llm.prompts import grading_system_prompt, grading_human_prompt
from llm.rotation_shifting import groq_pool, is_rate_limit_error
from src.logger import logging
from src.exception import CustomException


class Grading:
    """Semantic answer grading using LLM evaluation."""

    def __init__(self, model: str = "llama-3.3-70b-versatile"):
        # temperature=0: grading must be deterministic, the same answer has to
        # produce the same verdict every time.
        self.model = model
        self.temperature = 0
        self.parser = PydanticOutputParser(pydantic_object=GradeVerdict)

    def _llm(self):
        """Build a client on a key that isn't currently rate-limited.

        The key is fetched per call, not stored on the instance: a key held
        from __init__ can't rotate away when it gets cooled down.
        """
        key = groq_pool.get_key()
        return key, ChatGroq(model=self.model, temperature=self.temperature, api_key=key)

    async def grade_answer(
        self,
        question_text: str,
        ideal_answer: str,
        key_points: List[str],
        source_chunk: str,
        transcript: str,
    ) -> GradeVerdict:
        """Grade a student answer against the question's key semantic points.

        Returns a GradeVerdict. A garbled or empty transcript should come back
        as 'unclear' rather than 'wrong' - that distinction is load-bearing
        for the scoring engine.
        """
        try:
            system_prompt = grading_system_prompt(self.parser.get_format_instructions())
            human_prompt = grading_human_prompt(
                question_text=question_text,
                ideal_answer=ideal_answer,
                key_points=key_points,
                source_chunk=source_chunk,
                transcript=transcript,
            )
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt),
            ]

            last_exc = None
            for _ in range(len(groq_pool._keys)):
                key, llm = self._llm()
                try:
                    response = await llm.ainvoke(messages)
                    groq_pool.mark_success(key)
                    verdict = self.parser.parse(str(response.content))
                    logging.info(
                        f"Graded answer: verdict={verdict.verdict} "
                        f"confidence={verdict.confidence}"
                    )
                    return verdict
                except Exception as e:
                    if is_rate_limit_error(e):
                        groq_pool.mark_rate_limited(key)
                        last_exc = e
                        continue
                    raise

            raise CustomException(last_exc or "All Groq keys are rate-limited", sys)
        except Exception as e:
            logging.error(f"Error grading answer: {e}")
            raise CustomException(e, sys)
