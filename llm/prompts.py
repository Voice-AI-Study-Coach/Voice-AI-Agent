import sys

from src.exception import CustomException
from src.logger import logging

def chunking_prompt(hints, numbered_w):
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
        """
    except Exception as e:
        raise CustomException(e, sys)