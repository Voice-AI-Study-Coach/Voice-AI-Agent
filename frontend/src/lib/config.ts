/** Client-side tuning. Mirrors backend/config.py where the two overlap. */

/** Answered questions per topic before the quiz advances. Matches
 *  QUESTIONS_PER_TOPIC in backend/config.py - used only for progress display. */
export const QUESTIONS_PER_TOPIC = 4;

/** How long the student can go silent WHILE RECORDING before the coach asks
 *  "Shall we move to another question?" - reset by any detected speech (see
 *  stt.ts's level meter), so a pause mid-answer is not mistaken for being
 *  done. There is deliberately no separate idle-phase timer: counting down
 *  before the mic is even open could fire the prompt while the student is
 *  still reading the question or deciding whether to answer at all.
 *
 *  2 minutes gives real thinking room - working through a problem out loud
 *  can have long pauses - without leaving the mic open forever if the
 *  student has actually walked away. */
export const SILENCE_GRACE_MS = 120_000;

/** How often to poll document status while ingestion runs. */
export const INGESTION_POLL_MS = 2_500;

/** Shortest recording accepted as a real answer. Below this the tap is
 *  treated as a mis-tap: there is not enough audio to transcribe, and
 *  submitting it only produces an 'unclear' verdict that re-asks the same
 *  question. Long enough to rule out a double-tap, short enough that a
 *  genuinely brief answer ("quicksort") still goes through. */
export const MIN_ANSWER_MS = 1_500;
