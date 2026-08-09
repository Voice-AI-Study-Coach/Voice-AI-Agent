import sys

from src.exception import CustomException
from src.logger import logging
from typing import List

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

DIFFICULTY = """1 = Recall a single fact stated in the text
2 = State a definition or list the parts of something
3 = Explain how or why something works
4 = Apply the concept to a specific case or example
5 = Compare two things, or reason about an edge case"""

def build_q_prompt(topic, content):
    return f"""Generate quiz questions from this study material about "{topic}".

            Difficulty scale:
            {DIFFICULTY}

            Produce:
            - 2 questions at difficulty 1
            - 2 questions at difficulty 2
            - 3 questions at difficulty 3
            - 3 questions at difficulty 4
            - 2 questions at difficulty 5

            If the material genuinely cannot support a level, produce fewer at that level
            rather than inventing content not present in the text.

            Rules:
            - Every question must be answerable from the material below alone
            - Questions are answered ALOUD — no multiple choice, no fill-in-the-blank
            - key_points are the distinct ideas a correct answer must contain, as concepts not exact wording
            - Do not ask about figure labels or diagram text

            Respond with a single JSON object only, no other text, matching exactly this shape:
            {{"questions": [{{"question": str, "ideal_answer": str, "key_points": [str, ...], "difficulty": int}}]}}

            MATERIAL:
            {content}
            """

def grading_system_prompt(format_instructions: str) -> str:
    try:
        return (
            'You are an expert study coach grading spoken responses. '
            'Grade responses by meaning, never by exact wording. A correct idea '
            'phrased differently is still correct. '
            'Base your evaluation strictly on the provided source_chunk and key_points.\n\n'
            'Choose the verdict in this order:\n'
            '1. "unclear" - the transcript is not a genuine attempt at an answer: it is '
            'empty, nonsense or random letters (e.g. "asdfgh qwerty"), a stray fragment, '
            'or plainly mis-transcribed speech. This means the audio failed, NOT that the '
            'student was wrong, so prefer it whenever the text is not real language.\n'
            '2. "dont_know" - they explicitly say they do not know.\n'
            '3. "correct" - covers essentially all key points.\n'
            '4. "partial" - covers some key points but misses others.\n'
            '5. "wrong" - a real attempt in real language that is factually incorrect '
            'or unrelated to the source.\n\n'
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
            'Ground the feedback strictly in the matched points and missed points you are given. '
            'Never invent new facts. '
            'Respond with one or two short spoken sentences.\n\n'
            'Follow the rule for the given verdict and IGNORE the others:\n'
            '- correct: congratulate them briefly. Do not mention missing anything.\n'
            '- partial: say what they got right, then name the missed points.\n'
            '- wrong: gently say that is not right, then name the missed points.\n'
            '- dont_know: reassure them, then give the key points they should learn.\n'
            '- unclear: say ONLY that you could not make out their answer and ask them to '
            'repeat it. Never say this for any other verdict.\n\n'
            'If confidence is below 0.6, hedge with wording such as "I think" or "It seems".'
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