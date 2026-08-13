"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { Card, cx, ErrorNote, Pill, Spinner } from "@/components/ui";
import { ArrowLeftIcon } from "@/components/icons";
import type { SessionReplayResponse, TurnOut, Verdict } from "@/lib/types";

const VERDICT_LABEL: Record<Verdict, { label: string; tone: string }> = {
  correct: { label: "Correct", tone: "text-mastered bg-mastered-soft" },
  partial: { label: "Partly there", tone: "text-weak bg-weak-soft" },
  wrong: { label: "Not quite", tone: "text-danger bg-danger-soft" },
  dont_know: { label: "Did not know", tone: "text-ink-soft bg-raised" },
  unclear: { label: "Not caught", tone: "text-ink-soft bg-raised" },
};

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const sessionId = Number(id);

  const [data, setData] = useState<SessionReplayResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .session(sessionId)
      .then(setData)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load session"),
      );
  }, [sessionId]);

  if (error) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 sm:px-8">
        <ErrorNote>{error}</ErrorNote>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner className="size-5 text-ink-ghost" />
      </div>
    );
  }

  // Unanswered turns are from a session the student walked away from; showing
  // them as blank cards would just look broken.
  const answered = data.turns.filter((t) => t.verdict !== null);

  return (
    <div className="mx-auto max-w-2xl px-4 py-14 sm:px-8">
      <Link
        href={`/documents/${data.document_id}`}
        className="inline-flex items-center gap-1.5 text-[13px] text-ink-faint transition-colors hover:text-ink"
      >
        <ArrowLeftIcon className="size-3.5" />
        {data.filename.replace(/\.pdf$/i, "")}
      </Link>

      <header className="mt-5 animate-fade-up">
        <h1 className="font-serif text-[28px] tracking-[-0.02em] text-ink">
          Session review
        </h1>
        <p className="mt-1.5 text-[14px] text-ink-faint">
          {data.correct_count} of {data.questions_asked} correct
          {data.started_at &&
            ` · ${new Date(data.started_at).toLocaleDateString(undefined, {
              month: "long",
              day: "numeric",
            })}`}
        </p>
      </header>

      <ul className="mt-10 space-y-4">
        {answered.map((turn, i) => (
          <TurnCard key={turn.turn_index} turn={turn} index={i} />
        ))}
      </ul>
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function TurnCard({ turn, index }: { turn: TurnOut; index: number }) {
  const verdict = turn.verdict ? VERDICT_LABEL[turn.verdict] : null;

  return (
    <li
      className="animate-fade-up"
      style={{ animationDelay: `${Math.min(index * 40, 240)}ms` }}
    >
      <Card className="overflow-hidden">
        <div className="px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <p className="text-[11px] font-medium uppercase tracking-[0.1em] text-ink-ghost">
              {turn.topic}
            </p>
            {verdict && (
              <span
                className={cx(
                  "shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium",
                  verdict.tone,
                )}
              >
                {verdict.label}
              </span>
            )}
          </div>

          <h3 className="mt-2.5 font-serif text-[18px] leading-snug text-ink">
            {turn.question_text}
          </h3>

          {turn.transcript && (
            <div className="mt-4">
              <p className="text-[11px] font-medium uppercase tracking-[0.1em] text-ink-ghost">
                You said
              </p>
              <p className="mt-1.5 text-[14px] leading-relaxed text-ink-soft">
                {turn.transcript}
              </p>
            </div>
          )}
        </div>

        {/* The correct answer is shown on purpose: in review the student is
            studying, not being tested, so it helps rather than spoils. */}
        <div className="border-t border-line bg-sunken px-5 py-4">
          <p className="text-[11px] font-medium uppercase tracking-[0.1em] text-ink-ghost">
            The answer
          </p>
          <p className="mt-1.5 text-[14px] leading-relaxed text-ink-soft">
            {turn.ideal_answer}
          </p>

          {turn.missed_points.length > 0 && (
            <div className="mt-3.5 flex flex-wrap gap-1.5">
              {turn.missed_points.map((p) => (
                <Pill key={p} tone="weak">
                  {p}
                </Pill>
              ))}
            </div>
          )}
        </div>
      </Card>
    </li>
  );
}
