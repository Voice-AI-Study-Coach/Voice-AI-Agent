import sys

from src.exception import CustomException
from src.logger import logging

def chunking_prompt(hints, numbered_w, format_instructions):
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