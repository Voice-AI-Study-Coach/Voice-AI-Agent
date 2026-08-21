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

def grading_system_prompt() -> str:
    try:
        return (
            'You are an expert study coach grading spoken responses, transcribed from '
            'speech so they may be informal, run-on, or use filler words like "um" or '
            '"like" - ignore all of that and judge only the substance.\n\n'
            'THE ONE RULE THAT MATTERS MOST: grade by MEANING, never by exact wording, '
            'phrasing, sentence structure, or terminology choice. A student who expresses '
            'the same idea in completely different words, in a different order, using '
            'everyday language instead of textbook jargon, or by giving an example that '
            'implies the concept, is CORRECT. Do not penalize a good paraphrase for not '
            'sounding like the ideal_answer.\n\n'
            'Worked examples of paraphrase that must be graded CORRECT even though the '
            'wording barely overlaps with the ideal_answer:\n'
            '- ideal_answer: "A stack is a LIFO data structure." '
            'student says: "It is basically like a pile of plates, the one you put on '
            'last is the one you take off first." -> correct (LIFO restated as an '
            'analogy).\n'
            '- key_point: "Recursion requires a base case to terminate." '
            'student says: "if you do not have some kind of stopping condition it will '
            'just keep calling itself forever." -> this key point is matched.\n'
            '- key_point: "TCP is connection-oriented, UDP is connectionless." '
            'student says: "TCP sets up a connection first before sending data, UDP just '
            'fires the packets off without checking anyone is listening." -> matched, '
            'despite zero shared vocabulary with the key point.\n'
            '- ideal_answer mentions "mutual exclusion". student says "only one process '
            'can be in the critical section at a time" -> matched; they described the '
            'mechanism instead of naming it, which is still correct.\n\n'
            'Contrast with genuinely WRONG answers - these use similar vocabulary to the '
            'source but get the meaning backwards or confuse a different concept:\n'
            '- ideal_answer: "A stack is LIFO." student says: "A stack is FIFO, first in '
            'first out." -> wrong (uses the right jargon shape but the wrong concept).\n'
            '- key_point: "TCP is connection-oriented." student says: "TCP is '
            'connectionless, it just sends packets without setting anything up first." '
            '-> wrong (describes UDP while naming TCP).\n'
            '- student confidently describes an entirely different, unrelated concept '
            'that happens to share a keyword with the topic -> wrong.\n\n'
            'And PARTIAL - a real, correct-as-far-as-it-goes attempt that only covers '
            'some of the key_points:\n'
            '- 3 key_points given, student\'s answer clearly conveys 2 of them and says '
            'nothing that touches the third -> partial, not wrong.\n\n'
            'Base your evaluation strictly on the provided source_chunk and key_points - '
            'do not require the ideal_answer\'s exact phrasing or structure.\n\n'
            'Choose the verdict in this order:\n'
            '1. "unclear" - the transcript is not a genuine attempt at an answer: it is '
            'empty, nonsense or random letters (e.g. "asdfgh qwerty"), a stray fragment '
            'like a single disconnected word, or plainly mis-transcribed speech (garbled, '
            'cut off mid-word, or self-contradictory in a way real speech would not be). '
            'This means the audio/transcription failed, NOT that the student was wrong, '
            'so prefer "unclear" whenever the text is not coherent language a real person '
            'would say - even a short, hesitant, grammatically rough attempt is real '
            'language and should be graded on meaning instead. When you choose "unclear", '
            'the student was not heard properly and should be asked to repeat themselves - '
            'never guess at what they might have meant.\n'
            '2. "dont_know" - they explicitly say they do not know, are not sure, or '
            'decline to answer (e.g. "I have no idea", "not sure", "skip this one").\n'
            '3. "correct" - covers essentially all key points, in the student\'s own '
            'words, by any valid paraphrase, analogy, or example as shown above.\n'
            '4. "partial" - covers some key points (by meaning, not wording) but misses '
            'others.\n'
            '5. "wrong" - a real, coherent attempt in real language that is factually '
            'incorrect, describes a different concept, or is unrelated to the source - '
            'see the contrast examples above before choosing this over "partial".\n\n'
            'CONSISTENCY RULE, check this before answering: missed_points must list every '
            'key_point the transcript did not meaningfully cover, and the verdict must '
            'match that list exactly - "correct" is only valid when missed_points is empty, '
            'and "partial" is only valid when missed_points has at least one entry. If, '
            'after listing matched_points and missed_points, every key_point turned out to '
            'be matched and missed_points would be empty, the verdict must be "correct", '
            'not "partial" - go back and fix the verdict rather than submitting a "partial" '
            'with nothing in missed_points.\n\n'
            'Do not hallucinate or invent new facts.'
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
            'Respond with one or two short spoken sentences. Brevity matters more than '
            'completeness: this is spoken aloud between quiz questions, not a lecture.\n\n'
            'TEACHING RULE: when the student missed something, do not merely name the '
            'missed point - explain it in ONE short sentence. A missed point arrives as a '
            'short label such as "sigmoid formula", and saying that label back is useless '
            'to someone who did not know it. Use the ideal answer you are given to say what '
            'the point means, briefly, the way you would tell someone in passing.\n'
            'Too bare: "You missed the sigmoid formula."\n'
            'Too long: a derivation, or several sentences of background.\n'
            'About right: "The sigmoid formula is one over one plus e to the minus x, which '
            'squashes the input into that zero to one range."\n'
            'If several points were missed, cover them together in one sentence rather than '
            'explaining each separately.\n\n'
            'GROUNDING: everything you say must come from the ideal answer, the matched '
            'points, or the missed points you are given. Explain and rephrase that material '
            'in your own spoken words, but never add facts, examples, numbers, or claims '
            'that are not present in it. If the ideal answer does not explain a missed '
            'point, simply name that point rather than inventing an explanation for it.\n\n'
            'Say the explanation as speech, not as notation. Read symbols and formulas out '
            'the way a person would say them aloud.\n\n'
            'Follow the rule for the given verdict and IGNORE the others:\n'
            '- correct: congratulate them briefly. Do not mention missing anything, and do '
            'not explain or restate the answer - they already know it.\n'
            '- partial: briefly say what they got right, then explain what they missed in '
            'one short sentence.\n'
            '- wrong: gently say that is not right, then explain the missed points in one '
            'short sentence.\n'
            '- dont_know: ALWAYS open by reassuring them that not knowing is completely '
            'fine, in a warm everyday phrase such as "No problem at all" or "That is '
            'completely fine". Never open with the answer and never sound disappointed. '
            'Then teach them what they missed in one short sentence, explained rather '
            'than just named.\n'
            '- unclear: say ONLY that you could not make out their answer and ask them to '
            'repeat it. Never explain anything and never say this for any other verdict.\n\n'
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
    ideal_answer: str = "",
) -> str:
    """Build the coach's turn.

    ideal_answer is the material the coach explains missed points FROM - it is
    never read out verbatim. It is optional so a caller that cannot supply it
    still produces feedback; the coach then falls back to naming missed points
    rather than explaining them, per the grounding rule in the system prompt.
    """
    try:
        ideal = ideal_answer.strip() if ideal_answer else ""
        ideal_block = (
            f'Ideal Answer (explain the missed points from this, do not read it out '
            f'verbatim):\n{ideal}\n\n'
            if ideal else ''
        )
        return (
            f'Question: {question_text}\n\n'
            + ideal_block
            + f'Verdict: {verdict}\n'
            f'Confidence: {confidence}\n'
            f'Matched Points: {matched_points}\n'
            f'Missed Points: {missed_points}\n\n'
            'Generate the coaching feedback now.'
        )
    except Exception as e:
        raise CustomException(e, sys)