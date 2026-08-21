"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { MIN_ANSWER_MS, QUESTIONS_PER_TOPIC } from "@/lib/config";
import { STT_AVAILABLE, createStt } from "@/lib/speech/stt";
import { TTS_AVAILABLE, speak, stopSpeaking } from "@/lib/speech/tts";
import { AnswerStream } from "@/lib/speech/answer-stream";
import { SttUnavailableError } from "@/lib/speech/types";
import type { SttHandle } from "@/lib/speech/types";
import type { AnswerResponse, QuestionOut, Verdict } from "@/lib/types";
import { Button, cx, ErrorNote, Pill, Spinner } from "@/components/ui";
import {
  ArrowRightIcon,
  CheckIcon,
  KeyboardIcon,
  MicIcon,
} from "@/components/icons";

type Phase = "idle" | "recording" | "grading" | "feedback";

export default function QuizPage() {
  const { id } = useParams<{ id: string }>();
  const sessionId = Number(id);
  const router = useRouter();

  const [question, setQuestion] = useState<QuestionOut | null>(null);
  const [topic, setTopic] = useState("");
  const [totalQuestions, setTotalQuestions] = useState(0);
  const [asked, setAsked] = useState(0);
  const [correct, setCorrect] = useState(0);
  const [level, setLevel] = useState(2);

  const [phase, setPhase] = useState<Phase>("idle");
  const [feedback, setFeedback] = useState<AnswerResponse | null>(null);
  // The coach reply as it is spoken, one phrase at a time. Once the full
  // result lands, feedback.coach_reply takes over with the same words.
  const [streamingReply, setStreamingReply] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  // Silence handling: "Shall we move to another question?" only fires from
  // inside an active recording (stt.ts's own silence timer, reset on real
  // speech via the mic level meter) - never while merely idle/thinking. An
  // idle-phase countdown used to start the moment a question loaded, before
  // the student had even tapped the mic or finished hearing it read aloud,
  // so it could fire before they had a chance to answer at all.
  const [silencePrompt, setSilencePrompt] = useState(false);

  // Typed fallback. Present because speech is not implemented yet; remove the
  // toggle once STT_AVAILABLE flips to true.
  const [typing, setTyping] = useState(!STT_AVAILABLE);
  const [draft, setDraft] = useState("");

  const sttRef = useRef<SttHandle | null>(null);
  const [level01, setLevel01] = useState(0);

  // Seconds elapsed while recording. Transcription now happens after the
  // student stops, so without this the mic gives no sign it is actually
  // capturing - which led to answers being cut off after barely a second.
  const [recordSecs, setRecordSecs] = useState(0);
  const recordStartedAt = useRef(0);

  // Consecutive 'unclear' verdicts from the mic. Two in a row means speech
  // capture is not working for this student right now, and re-asking the same
  // question a third time just traps them in a loop with no way out - so the
  // UI falls back to typing instead. Reset by any answer that grades normally.
  const unclearStreak = useRef(0);

  /* ---- load the session's current question ------------------------------ */
  useEffect(() => {
    (async () => {
      try {
        const s = await api.session(sessionId);
        if (s.status !== "active") {
          router.replace(`/sessions/${sessionId}/summary`);
          return;
        }
        setTopic(s.selected_topics[0] ?? "");
        setTotalQuestions(s.selected_topics.length * QUESTIONS_PER_TOPIC);
        setAsked(s.questions_asked);
        setCorrect(s.correct_count);

        // The open turn is the one awaiting an answer.
        const open = s.turns.find((t) => t.verdict === null);
        if (open) {
          setQuestion({
            question_id: 0,
            question_text: open.question_text,
            topic: open.topic,
            difficulty: open.level_at_ask,
            turn_index: open.turn_index,
          });
          setTopic(open.topic);
          setLevel(open.level_at_ask);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load session");
      } finally {
        setLoading(false);
      }
    })();
  }, [sessionId, router]);

  /* ---- speak each new question, when TTS exists ------------------------- */
  // Keyed on the question TEXT, not the object: an 'unclear' retry re-serves
  // the same question as a fresh object, and keying on the object would make
  // the coach read the question aloud again on every failed attempt - which
  // then talks over the student's next answer and empties that transcript too.
  const questionText = question?.question_text;
  useEffect(() => {
    if (!questionText || !TTS_AVAILABLE) return;
    const handle = speak(questionText);
    return () => handle.cancel();
  }, [questionText]);

  /* ---- streaming answer socket ------------------------------------------- */
  // One socket for the whole quiz. Opening it per answer would put a
  // handshake plus the backend's Deepgram connect back on the critical path,
  // which is most of what streaming was meant to remove.
  const streamRef = useRef<AnswerStream | null>(null);
  useEffect(() => {
    if (!Number.isFinite(sessionId)) return;
    const stream = new AnswerStream(sessionId, {
      // Appended per phrase, as each is spoken - so the words appear in time
      // with the voice rather than all at once ahead of it.
      onPhrase: (phrase) =>
        setStreamingReply((prev) => (prev ? `${prev} ${phrase}` : phrase)),
    });
    streamRef.current = stream;
    return () => {
      streamRef.current = null;
      stream.close();
    };
  }, [sessionId]);

  /* ---- recording timer --------------------------------------------------- */
  useEffect(() => {
    if (phase !== "recording") {
      setRecordSecs(0);
      return;
    }
    const id = setInterval(() => {
      setRecordSecs(Math.floor((Date.now() - recordStartedAt.current) / 1000));
    }, 250);
    return () => clearInterval(id);
  }, [phase]);

  /* ---- submit ------------------------------------------------------------ */
  const submit = useCallback(
    async (transcript: string, sttMs?: number) => {
      setSilencePrompt(false);
      setPhase("grading");
      setError("");
      setStreamingReply("");
      try {
        // Stream when the socket is up: the coach's text renders token by
        // token and its voice starts on the first finished phrase, instead
        // of both waiting for the whole reply. Falls back to the plain POST
        // if the socket could not be opened, so a blocked WebSocket degrades
        // to the old behaviour rather than breaking the quiz.
        const stream = streamRef.current;
        let res: AnswerResponse;
        // The streaming path speaks as it generates; the fallback still needs
        // the old fire-and-forget speak() once the reply is whole.
        let spoken = false;
        if (stream) {
          try {
            res = await stream.submit(transcript, sttMs);
            spoken = true;
          } catch {
            setStreamingReply("");
            res = await api.answer(sessionId, transcript, sttMs);
          }
        } else {
          res = await api.answer(sessionId, transcript, sttMs);
        }
        setAsked(res.questions_asked);
        setCorrect(res.correct_count);
        setLevel(res.level);
        setTopic(res.current_topic);
        setDraft("");

        if (res.verdict === "unclear" && res.next_question) {
          // STT failed to catch anything - the backend re-serves the SAME
          // question rather than advancing. Going through the feedback
          // screen here would force an extra "Next question" tap just to
          // get the mic back; instead drop straight back to answering it.
          unclearStreak.current += 1;
          setQuestion(res.next_question);
          setFeedback(null);
          setPhase("idle");
          // This path bypasses next(), so it has to clear the streamed reply
          // itself or the "I could not make that out" line stays on screen
          // over the re-served question.
          setStreamingReply("");

          if (unclearStreak.current >= 2) {
            // Speech capture is not working. Re-asking a third time would
            // trap the student in a loop, so hand them the keyboard and say
            // so plainly rather than repeating "I could not make that out".
            unclearStreak.current = 0;
            setTyping(true);
            setError(
              "The microphone is not picking up your answer, so you can type it instead.",
            );
            return;
          }

          if (TTS_AVAILABLE && !spoken) speak(res.coach_reply);
          return;
        }

        unclearStreak.current = 0;
        if (TTS_AVAILABLE && !spoken) speak(res.coach_reply);
        setFeedback(res);
        setPhase("feedback");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not submit answer");
        setPhase("idle");
      }
    },
    [sessionId],
  );

  /* ---- continue to the next question ------------------------------------ */
  function next() {
    if (!feedback) return;
    if (feedback.session_complete) {
      router.push(`/sessions/${sessionId}/summary`);
      return;
    }
    setQuestion(feedback.next_question);
    setFeedback(null);
    // Cleared here, with the turn it belongs to. Leaving it set meant the
    // previous answer's reply was still in state when the next question was
    // submitted, and it rendered instantly under the new question before any
    // fresh token had arrived.
    setStreamingReply("");
    setPhase("idle");
  }

  /* ---- mic --------------------------------------------------------------- */
  async function startRecording() {
    setError("");
    // Stop the coach mid-sentence so the recording does not capture the
    // question being read aloud back into the student's own answer. Both
    // paths have to be silenced: the question is spoken through the <audio>
    // element, the coach's reply through the streamed PCM player.
    stopSpeaking();
    streamRef.current?.stopSpeaking();
    // Opening the socket now, from the same gesture, overlaps the handshake
    // with the student speaking instead of paying for it after they finish.
    void streamRef.current?.connect().catch(() => {});
    try {
      const stt = createStt({
        onLevel: setLevel01,
        onPartial: setDraft,
        onSilenceTimeout: () => setSilencePrompt(true),
        onError: (e) => {
          if (e instanceof SttUnavailableError) {
            // Recording is impossible here (no microphone, permission
            // denied, or a browser that cannot record). Leaving the student
            // on a dead mic just loops "I could not make that out", so hand
            // them the keyboard and say why.
            sttRef.current = null;
            setLevel01(0);
            setTyping(true);
            setPhase("idle");
            setError(`${e.message}. You can type your answer instead.`);
            return;
          }
          setError(e.message);
        },
      });
      sttRef.current = stt;
      await stt.start();
      recordStartedAt.current = Date.now();
      setRecordSecs(0);
      setPhase("recording");
      setDraft("");
    } catch (err) {
      // Starting failed outright (permission denied, engine unavailable).
      // Fall back to typing rather than dead-ending, but surface the real
      // reason - "not available yet" hid genuine permission errors.
      sttRef.current = null;
      setTyping(true);
      setError(
        err instanceof Error
          ? `${err.message}. You can type your answer instead.`
          : "Voice input is not available. You can type instead.",
      );
    }
  }

  async function stopRecording() {
    const stt = sttRef.current;
    if (!stt) return;

    // A stop this soon after starting is a mis-tap, not a finished answer:
    // there is not enough audio in it to transcribe, and submitting it just
    // returns "I could not make that out" and re-asks the same question.
    if (Date.now() - recordStartedAt.current < MIN_ANSWER_MS) {
      setError("Give it a moment - keep speaking, then tap again when you are done.");
      return;
    }

    setPhase("grading");
    try {
      const { transcript, durationMs } = await stt.stop();
      setDraft(transcript);
      await submit(transcript, durationMs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not transcribe");
      setPhase("idle");
    } finally {
      sttRef.current = null;
      setLevel01(0);
    }
  }

  /* ---- silence prompt replies -------------------------------------------- */
  async function answerSilencePrompt(accepted: boolean) {
    setSilencePrompt(false);
    try {
      const res = await api.skip(sessionId, accepted);
      if (TTS_AVAILABLE) speak(res.coach_reply);
      if (res.skipped && res.next_question) {
        setQuestion(res.next_question);
        setTopic(res.current_topic);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not skip");
    }
  }

  /* ------------------------------------------------------------------------ */

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner className="size-5 text-ink-ghost" />
      </div>
    );
  }

  const progress = totalQuestions > 0 ? asked / totalQuestions : 0;

  return (
    <div className="flex h-full flex-col">
      {/* Progress header */}
      <header className="shrink-0 border-b border-line bg-paper/80 px-4 py-4 backdrop-blur-sm sm:px-8">
        <div className="mx-auto flex max-w-2xl items-center justify-between gap-4">
          <div className="min-w-0">
            <p className="truncate text-[13px] font-medium text-ink">{topic}</p>
            <p className="text-[12px] text-ink-faint">
              {asked} of {totalQuestions} answered · {correct} correct
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Pill>Level {level}</Pill>
          </div>
        </div>
        <div className="mx-auto mt-3 h-0.5 max-w-2xl overflow-hidden rounded-full bg-raised">
          <div
            className="h-full rounded-full bg-ink transition-[width] duration-700 ease-out"
            style={{ width: `${progress * 100}%` }}
          />
        </div>
      </header>

      {/* Body */}
      <div className="flex flex-1 items-center justify-center overflow-y-auto px-4 py-10 sm:px-8">
        <div className="w-full max-w-2xl">
          {/* Shown as soon as the coach starts talking, not only once the
              whole result has landed: during grading `feedback` is still null
              and only the streamed text exists, so the same panel fills in
              live and then settles when the verdict arrives. */}
          {(phase === "feedback" && feedback) || streamingReply ? (
            <Feedback
              data={feedback}
              streamingReply={streamingReply}
              onNext={next}
            />
          ) : (
            <>
              {question && (
                <div key={question.turn_index} className="animate-fade-up">
                  <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-ink-ghost">
                    Question {asked + 1}
                  </p>
                  <h2 className="mt-3 font-serif text-[26px] leading-[1.35] tracking-[-0.01em] text-ink">
                    {question.question_text}
                  </h2>
                </div>
              )}

              {/* Silence prompt */}
              {silencePrompt && (
                <div className="mt-8 rounded-2xl border border-line bg-surface px-5 py-4 animate-fade-up">
                  <p className="text-[15px] text-ink">
                    Shall we move to another question?
                  </p>
                  <div className="mt-3 flex gap-2">
                    <Button size="sm" onClick={() => answerSilencePrompt(true)}>
                      Yes, move on
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => answerSilencePrompt(false)}
                    >
                      No, I am thinking
                    </Button>
                  </div>
                </div>
              )}

              {/* Answer control */}
              <div className="mt-12">
                {phase === "grading" ? (
                  // The streamed reply is NOT rendered here. It appears in
                  // <Feedback> instead, which owns the coach's text for the
                  // whole turn - rendering it here too meant the same
                  // sentence was drawn by two different components in two
                  // different places, so it visibly jumped when the final
                  // result arrived and the phase flipped.
                  <div className="flex flex-col items-center gap-3 animate-fade-in">
                    <Spinner className="size-5 text-ink-faint" />
                    <p className="text-[13px] text-ink-faint">
                      Listening to what you said…
                    </p>
                  </div>
                ) : typing ? (
                  <TypedAnswer
                    value={draft}
                    onChange={setDraft}
                    onSubmit={() => draft.trim() && submit(draft.trim())}
                    onSwitchToVoice={
                      STT_AVAILABLE ? () => setTyping(false) : undefined
                    }
                  />
                ) : (
                  <MicControl
                    recording={phase === "recording"}
                    level={level01}
                    seconds={recordSecs}
                    onStart={startRecording}
                    onStop={stopRecording}
                    onSwitchToTyping={() => setTyping(true)}
                  />
                )}
              </div>

              {phase === "feedback" && draft && (
                <div className="mt-6 rounded-2xl border border-accent/30 bg-accent-soft px-4 py-3 text-[13px] leading-relaxed text-ink">
                  <span className="font-medium text-ink-faint">You said:</span>{" "}
                  {draft}
                </div>
              )}

              {error && (
                <div className="mt-6">
                  <ErrorNote>{error}</ErrorNote>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function MicControl({
  recording,
  level,
  seconds,
  onStart,
  onStop,
  onSwitchToTyping,
}: {
  recording: boolean;
  level: number;
  seconds: number;
  onStart: () => void;
  onStop: () => void;
  onSwitchToTyping: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-5">
      <button
        onClick={recording ? onStop : onStart}
        className="relative flex size-[76px] items-center justify-center"
      >
        {/* Breathing halo, scaled by input loudness while recording */}
        <span
          className={cx(
            "absolute inset-0 rounded-full transition-transform duration-100",
            recording ? "bg-accent-soft" : "bg-raised",
          )}
          style={
            recording ? { transform: `scale(${1 + level * 0.35})` } : undefined
          }
        />
        {!recording && (
          <span className="absolute inset-0 rounded-full bg-raised animate-breathe" />
        )}
        <span
          className={cx(
            "relative flex size-[60px] items-center justify-center rounded-full transition-all duration-200",
            recording
              ? "bg-accent text-paper elevate-mic-active"
              : "bg-ink text-paper elevate-mic hover:scale-105 active:scale-95",
          )}
        >
          <MicIcon className="size-5" />
        </span>
      </button>

      {recording ? (
        <div className="flex flex-col items-center gap-1.5">
          <div className="flex items-center gap-2">
            <span className="size-1.5 rounded-full bg-danger animate-pulse" />
            {/* Elapsed time is the only signal that audio is being captured:
                the transcript no longer appears until after the student
                stops, so without it the mic looks inert. */}
            <span className="font-mono text-[13px] tabular-nums text-ink">
              {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}
            </span>
          </div>
          <p className="text-[13px] text-ink-faint">
            Listening — tap when you are done
          </p>
        </div>
      ) : (
        <p className="text-[13px] text-ink-faint">Tap to answer</p>
      )}

      <button
        onClick={onSwitchToTyping}
        className="flex items-center gap-1.5 text-[12px] text-ink-ghost transition-colors hover:text-ink-faint"
      >
        <KeyboardIcon className="size-3.5" />
        Type instead
      </button>
    </div>
  );
}

/* -------------------------------------------------------------------------- */

/** Development fallback while speech is unimplemented. This is the only place
 *  in the app with a free-text field outside login and signup. */
function TypedAnswer({
  value,
  onChange,
  onSubmit,
  onSwitchToVoice,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onSwitchToVoice?: () => void;
}) {
  return (
    <div className="animate-fade-up">
      <div className="rounded-2xl border border-line-strong bg-surface p-2 transition-colors focus-within:border-accent focus-within:ring-4 focus-within:ring-accent/8">
        <textarea
          autoFocus
          rows={3}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) onSubmit();
          }}
          placeholder="Say your answer in your own words…"
          className="w-full resize-none bg-transparent px-3 py-2.5 text-[15px] leading-relaxed text-ink outline-none placeholder:text-ink-ghost"
        />
        <div className="flex items-center justify-between gap-3 px-1 pb-0.5">
          {onSwitchToVoice ? (
            <button
              onClick={onSwitchToVoice}
              className="flex items-center gap-1.5 px-2 text-[12px] text-ink-ghost transition-colors hover:text-ink-faint"
            >
              <MicIcon className="size-3.5" />
              Use voice
            </button>
          ) : (
            <span className="px-2 text-[12px] text-ink-ghost">
              Voice input coming soon
            </span>
          )}
          <Button size="sm" disabled={!value.trim()} onClick={onSubmit}>
            Answer
            <ArrowRightIcon className="size-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */

const VERDICT_COPY: Record<Verdict, { label: string; tone: string; bg: string }> =
  {
    correct: { label: "Correct", tone: "text-mastered", bg: "bg-mastered-soft" },
    partial: { label: "Partly there", tone: "text-weak", bg: "bg-weak-soft" },
    wrong: { label: "Not quite", tone: "text-danger", bg: "bg-danger-soft" },
    dont_know: { label: "That is fine", tone: "text-ink-soft", bg: "bg-raised" },
    // Never framed as a failure: it means the audio did not come through, and
    // it costs the student nothing.
    unclear: { label: "Did not catch that", tone: "text-ink-soft", bg: "bg-raised" },
  };

function Feedback({
  data,
  streamingReply,
  onNext,
}: {
  /** Null while the coach is still talking - the verdict, the points and the
   *  next-question button only exist once the whole turn has been graded. */
  data: AnswerResponse | null;
  streamingReply: string;
  onNext: () => void;
}) {
  const copy = data ? VERDICT_COPY[data.verdict] : null;
  // The streamed text IS the coach reply; data.coach_reply is the same words
  // once the turn completes. Preferring the stream while it is running keeps
  // one element rendering one string, so nothing re-flows at the handoff.
  const reply = streamingReply || data?.coach_reply || "";

  return (
    <div className="animate-fade-up">
      {data && copy && (
        <div className="flex items-center gap-2.5">
          <span
            className={cx(
              "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-medium",
              copy.bg,
              copy.tone,
            )}
          >
            {data.verdict === "correct" && <CheckIcon className="size-3" />}
            {copy.label}
          </span>
          {data.topic_changed && <Pill tone="accent">New topic</Pill>}
        </div>
      )}

      <p
        className={cx(
          "font-serif text-[22px] leading-[1.45] text-ink",
          data ? "mt-5" : "",
        )}
      >
        {reply}
      </p>

      {data && data.matched_points.length > 0 && (
        <PointList
          title="You covered"
          points={data.matched_points}
          tone="mastered"
        />
      )}
      {data && data.missed_points.length > 0 && (
        <PointList title="Worth remembering" points={data.missed_points} tone="weak" />
      )}

      {data && (
        <div className="mt-10">
          <Button size="lg" onClick={onNext}>
            {data.session_complete ? "See your summary" : "Next question"}
            <ArrowRightIcon className="size-4" />
          </Button>
        </div>
      )}
    </div>
  );
}

function PointList({
  title,
  points,
  tone,
}: {
  title: string;
  points: string[];
  tone: "mastered" | "weak";
}) {
  return (
    <div className="mt-7">
      <p className="text-[11px] font-medium uppercase tracking-[0.1em] text-ink-ghost">
        {title}
      </p>
      <ul className="mt-2 space-y-1.5">
        {points.map((p) => (
          <li key={p} className="flex items-start gap-2.5 text-[14px] text-ink-soft">
            <span
              className={cx(
                "mt-[7px] size-1.5 shrink-0 rounded-full",
                tone === "mastered" ? "bg-mastered" : "bg-weak",
              )}
            />
            <span className="leading-relaxed">{p}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
