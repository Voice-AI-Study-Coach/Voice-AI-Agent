import sys

from src.exception import CustomException
from src.logger import logging
<<<<<<< HEAD

def chunking_prompt(hints, numbered_w, format_instructions):
=======
from typing import List
def chunking_prompt(hints, numbered_w):
>>>>>>> d438e8cc04c2adaf40be9d9208fa25594607b645
    try:
        return f"""Below is part of a study document with numbered lines.
        Divide it into study sections by topic.

        Rules:
        - Each section must be a substantial topic worth studying
        - Do NOT create sections for figure labels, diagram box text, or isolated lines
        - Do NOT create a section for a single paragraph — merge it into the topic it belongs to
        - The document's table of contents suggests these real headings: {hints}
        - If a section is a sub-part of a broader section, set its "parent" to that
        broader section's topic name. Example: "Lexical Analysis", "Syntax Analysis"
        and "Code Optimization" are all phases, so their parent is "Phases of Compilation".
        Top-level sections have parent null.

        Return line numbers, topic names, and parents. Do not reproduce document text.

        DOCUMENT:
        {numbered_w}

        {format_instructions}
        """
    except Exception as e:
        raise CustomException(e, sys)

<<<<<<< HEAD
DIFFICULTY = """1 = Recall a single fact stated in the text
2 = State a definition or list the parts of something
3 = Explain how or why something works
4 = Apply the concept to a specific case or example
5 = Compare two things, or reason about an edge case"""

def build_q_prompt(topic, content, n, format_instructions):
    return f"""Generate exactly {n} quiz questions from this study material.

Topic: {topic}

Difficulty scale:
{DIFFICULTY}

Rules:
- Every question must be answerable from the material below alone
- Questions are answered ALOUD — no multiple choice, no fill-in-the-blank
- key_points are the distinct ideas a correct answer must contain, as concepts not exact wording
- Spread questions across difficulty levels
- Do not ask about figure labels or diagram text

MATERIAL:
{content}

{format_instructions}
"""
=======

def grading_system_prompt(format_instructions: str) -> str:
    try:
        return (
            'You are an expert study coach grading spoken responses. '
            'Grade responses by meaning, never by exact wording. '
            'Base your evaluation strictly on the provided source_chunk and key_points. '
            'If the transcript is garbled, contains obvious silence, or was cut off, return verdict "unclear" rather than "wrong". '
            'If the answer is unrelated to the source, return "wrong". '
            'Do not hallucinate or invent new facts. '
            'Return only valid JSON that matches the schema and the format instructions below.\n\n'
            f'{format_instructions}'
        )
    except Exception as e:
        raise CustomException(e, sys)


def grading_human_prompt(
    question_text: str,
    ideal_answer: str,
    key_points: List[str],
    source_chunk: str,
    transcript: str,
) -> str:
    try:
        return (
            f'Question: {question_text}\n\n'
            f'Ideal Answer: {ideal_answer}\n\n'
            'Key Points:\n'
            + '\n'.join(f'- {point}' for point in key_points)
            + f'\n\nSource Chunk:\n{source_chunk}\n\nTranscript:\n{transcript}\n\n'
            'Evaluate the response and return the final grading verdict in the requested schema.'
        )
    except Exception as e:
        raise CustomException(e, sys)


def coaching_system_prompt() -> str:
    try:
        return (
            'You are a spoken-language study coach. Produce concise TTS-ready feedback using plain text only. '
            'Do not use markdown, bullet points, or special characters. '
            'Ground the feedback strictly in verdict.missed_points and verdict.matched_points. '
            'Never invent new facts. '
            'If confidence is below 0.6, hedge the response with language such as "I think" or "It seems". '
            'If the verdict is unclear, note that the transcript was unclear and invite the student to repeat their answer. '
            'If the verdict is correct and there are no missed points, offer brief positive encouragement. '
            'If the verdict is partial or wrong, mention the missed points and suggest reviewing them. '
            'Respond with a single short spoken response.'
        )
    except Exception as e:
        raise CustomException(e, sys)


def coaching_human_prompt(
    question_text: str,
    verdict: str,
    confidence: float,
    matched_points: List[str],
    missed_points: List[str],
) -> str:
    try:
        return (
            f'Question: {question_text}\n\n'
            f'Verdict: {verdict}\n'
            f'Confidence: {confidence}\n'
            f'Matched Points: {matched_points}\n'
            f'Missed Points: {missed_points}\n\n'
            'Generate the coaching feedback now.'
        )
    except Exception as e:
        raise CustomException(e, sys)
>>>>>>> d438e8cc04c2adaf40be9d9208fa25594607b645
