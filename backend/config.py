"""Tuning constants for the quiz engine.

Kept in one file on purpose: these get adjusted during testing, and hunting
them across modules wastes time. Nothing here should import from backend/ or
llm/ - it must stay safe to import from anywhere.
"""

# --- Quiz pacing -----------------------------------------------------------
QUESTIONS_PER_TOPIC = 4      # answered questions on a topic before advancing

# --- Adaptive difficulty ---------------------------------------------------
# Every topic starts at the baseline; the level is NOT carried forward from
# the previous topic. A student can know one topic well and be near-zero on
# the next, and handing them a level-5 question on unfamiliar material is
# both discouraging and tells us nothing true about their ability.
BASELINE_LEVEL = 2
BASELINE_SCORE = 0.5

MIN_LEVEL = 1
MAX_LEVEL = 5

# score = SCORE_MEMORY * score + (1 - SCORE_MEMORY) * points(verdict)
# Keep 70% of the previous estimate, mix in 30% of how they just did, so the
# score drifts rather than snapping on a single answer.
SCORE_MEMORY = 0.7

# The gap between these two is a dead band. Without it a student hovering
# near a threshold sees the difficulty flip every single turn.
LEVEL_UP_THRESHOLD = 0.75
LEVEL_DOWN_THRESHOLD = 0.40

# Order in which pick_question widens its search when the exact level has no
# unasked questions left.
LEVEL_WIDENING_OFFSETS = (0, 1, -1, 2, -2)

# --- Coaching --------------------------------------------------------------
CONFIDENCE_HEDGE = 0.6       # below this the coach hedges its wording

# --- Uploads ---------------------------------------------------------------
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

# --- Reapers ---------------------------------------------------------------
SESSION_IDLE_MINUTES = 60    # active session with no answers -> abandoned
INGESTION_STUCK_MINUTES = 30 # document stuck in 'processing' -> failed

# --- Verdicts --------------------------------------------------------------
# 'unclear' is deliberately absent. It means speech-to-text produced
# something unusable, which is a technical failure and not a wrong answer:
# it must not score, must not consume one of the topic's questions, and must
# not appear in the summary. Code should check for it before scoring rather
# than looking it up here.
POINTS = {
    "correct": 1.0,
    "partial": 0.5,
    "wrong": 0.0,
    "dont_know": 0.0,
}

WEAK_TOPIC_ACCURACY = 0.5    # below this a topic is flagged "worth revisiting"
