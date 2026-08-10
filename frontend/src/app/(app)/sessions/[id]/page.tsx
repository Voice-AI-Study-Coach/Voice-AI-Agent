"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { QUESTIONS_PER_TOPIC, SILENCE_PROMPT_MS } from "@/lib/config";
import { STT_AVAILABLE, createStt } from "@/lib/speech/stt";
import { TTS_AVAILABLE, speak } from "@/lib/speech/tts";
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
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  // Silence handling: the browser owns the timer because only it can tell the
  // mic has gone quiet - the backend simply never receives a request.
  const [silencePrompt, setSilencePrompt] = useState(false);
  const silenceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Typed fallback. Present because speech is not implemented yet; remove the
  // toggle once STT_AVAILABLE flips to true.
  const [typing, setTyping] = useState(!STT_AVAILABLE);
  const [draft, setDraft] = useState("");

  const sttRef = useRef<SttHandle | null>(null);
  const [level01, setLevel01] = useState(0);

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
  useEffect(() => {
    if (!question || !TTS_AVAILABLE) return;
    const handle = speak(question.question_text);
    return () => handle.cancel();
  }, [question]);

  /* ---- silence timer ----------------------------------------------------- */
  const clearSilence = useCallback(() => {
    if (silenceTimer.current) clearTimeout(silenceTimer.current);
    silenceTimer.current = null;
  }, []);

  const armSilence = useCallback(() => {
    clearSilence();
    silenceTimer.current = setTimeout(
      () => setSilencePrompt(true),
      SILENCE_PROMPT_MS,
    );
  }, [clearSilence]);

  useEffect(() => {
    // Only run the timer while a question is genuinely waiting on the student.
    if (phase === "idle" && question && !typing && !silencePrompt) armSilence();
    else clearSilence();
    return clearSilence;
  }, [phase, question, typing, silencePrompt, armSilence, clearSilence]);

  /* ---- submit ------------------------------------------------------------ */
  const submit = useCallback(
    async (transcript: string, sttMs?: number) => {
      clearSilence();
      setSilencePrompt(false);
      setPhase("grading");
      setError("");
      try {
        const res = await api.answer(sessionId, transcript, sttMs);
        setFeedback(res);
        setPhase("feedback");
        setAsked(res.questions_asked);
        setCorrect(res.correct_count);
        setLevel(res.level);
        setTopic(res.current_topic);
        setDraft("");

        if (TTS_AVAILABLE) speak(res.coach_reply);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not submit answer");
        setPhase("idle");
      }
    },
    [sessionId, clearSilence],
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
    setPhase("idle");
  }

  /* ---- mic --------------------------------------------------------------- */
  async function startRecording() {
    clearSilence();
    setError("");
    try {
      const stt = createStt({
        onLevel: setLevel01,
        onSilenceTimeout: () => setSilencePrompt(true),
        onError: (e) => setError(e.message),
      });
      sttRef.current = stt;
      await stt.start();
      setPhase("recording");
    } catch {
      // Speech is not implemented yet - fall back rather than dead-ending.
      setTyping(true);
      setError("Voice input is not available yet. You can type instead.");
    }
  }

  async function stopRecording() {
    const stt = sttRef.current;
    if (!stt) return;
    setPhase("grading");
    try {
      const { transcript, durationMs } = await stt.stop();
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
      <header className="shrink-0 border-b border-line bg-paper/80 px-8 py-4 backdrop-blur-sm">
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
      <div className="flex flex-1 items-center justify-center overflow-y-auto px-8 py-10">
        <div className="w-full max-w-2xl">
          {phase === "feedback" && feedback ? (
            <Feedback data={feedback} onNext={next} />
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
                    onStart={startRecording}
                    onStop={stopRecording}
                    onSwitchToTyping={() => setTyping(true)}
                  />
                )}
              </div>

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
  onStart,
  onStop,
  onSwitchToTyping,
}: {
  recording: boolean;
  level: number;
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

      <p className="text-[13px] text-ink-faint">
        {recording ? "Listening — tap when you are done" : "Tap to answer"}
      </p>

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
  onNext,
}: {
  data: AnswerResponse;
  onNext: () => void;
}) {
  const copy = VERDICT_COPY[data.verdict];

  return (
    <div className="animate-fade-up">
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

      <p className="mt-5 font-serif text-[22px] leading-[1.45] text-ink">
        {data.coach_reply}
      </p>

      {data.matched_points.length > 0 && (
        <PointList
          title="You covered"
          points={data.matched_points}
          tone="mastered"
        />
      )}
      {data.missed_points.length > 0 && (
        <PointList title="Worth remembering" points={data.missed_points} tone="weak" />
      )}

      <div className="mt-10">
        <Button size="lg" onClick={onNext}>
          {data.session_complete ? "See your summary" : "Next question"}
          <ArrowRightIcon className="size-4" />
        </Button>
      </div>
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
