"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Button, Card, cx, ErrorNote, Spinner } from "@/components/ui";
import { ArrowRightIcon, BookIcon, ClockIcon } from "@/components/icons";
import type { SummaryResponse, TopicResult } from "@/lib/types";

export default function SummaryPage() {
  const { id } = useParams<{ id: string }>();
  const sessionId = Number(id);
  const router = useRouter();

  const [data, setData] = useState<SummaryResponse | null>(null);
  const [documentId, setDocumentId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [restarting, setRestarting] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [summary, session] = await Promise.all([
          api.summary(sessionId),
          api.session(sessionId),
        ]);
        setData(summary);
        setDocumentId(session.document_id);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load summary");
      }
    })();
  }, [sessionId]);

  /** Continuing sends them back to topic selection rather than starting a
   *  quiz outright: choosing what to study next is theirs to make, and the
   *  new session is created when they press Start there. */
  function continueToTopics() {
    if (documentId === null) return;
    setRestarting(true);
    router.push(`/documents/${documentId}?continue=1`);
  }

  if (error) {
    return (
      <div className="mx-auto max-w-2xl px-8 py-16">
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

  const pct = Math.round(data.overall_accuracy * 100);

  return (
    <div className="mx-auto max-w-2xl px-8 py-14">
      <header className="animate-fade-up">
        <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-ink-ghost">
          Session complete
        </p>
        <h1 className="mt-2.5 font-serif text-[32px] tracking-[-0.02em] text-ink">
          {data.correct_count} of {data.questions_asked} correct
        </h1>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[14px] text-ink-faint">
          <span>{pct}% accuracy</span>
          {data.duration_seconds !== null && (
            <>
              <span className="text-ink-ghost">·</span>
              <span className="flex items-center gap-1.5">
                <ClockIcon className="size-3.5" />
                {formatDuration(data.duration_seconds)}
              </span>
            </>
          )}
          {data.avg_response_ms !== null && (
            <>
              <span className="text-ink-ghost">·</span>
              <span title="Median time to grade an answer">
                {(data.avg_response_ms / 1000).toFixed(1)}s avg response
              </span>
            </>
          )}
          {data.avg_stt_ms !== null && (
            <>
              <span className="text-ink-ghost">·</span>
              <span title="Median speech-to-text time">
                {(data.avg_stt_ms / 1000).toFixed(1)}s avg transcription
              </span>
            </>
          )}
        </div>
      </header>

      {data.narrative && (
        <Card
          className="mt-8 px-5 py-5 animate-fade-up"
          style={{ animationDelay: "60ms" }}
        >
          <p className="font-serif text-[17px] leading-[1.6] text-ink-soft">
            {data.narrative}
          </p>
        </Card>
      )}

      {data.topic_results.length > 0 && (
        <section className="mt-10 animate-fade-up" style={{ animationDelay: "90ms" }}>
          <p className="text-[11px] font-medium uppercase tracking-[0.1em] text-ink-ghost">
            How each topic went
          </p>
          <ul className="mt-3 space-y-2">
            {data.topic_results.map((t) => (
              <TopicResultRow key={t.topic} result={t} />
            ))}
          </ul>
        </section>
      )}

      {/* Continue prompt. remaining_topics spans every session on this
          document, which is what makes the loop work across rounds. */}
      {data.remaining_topics.length > 0 ? (
        <Card
          className="mt-12 px-5 py-5 animate-fade-up"
          style={{ animationDelay: "120ms" }}
        >
          <h2 className="font-serif text-[19px] text-ink">
            Continue with the topics you have not covered?
          </h2>
          <p className="mt-1.5 text-[13px] leading-relaxed text-ink-faint">
            {data.remaining_topics.length}{" "}
            {data.remaining_topics.length === 1 ? "topic" : "topics"} left in
            this document. Saying yes starts a new session, so this one keeps
            its own summary.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button loading={restarting} onClick={continueToTopics}>
              Yes, keep going
              <ArrowRightIcon className="size-4" />
            </Button>
            <Link href="/library">
              <Button variant="secondary">No, I am done</Button>
            </Link>
            <Link href={`/sessions/${sessionId}/review`}>
              <Button variant="ghost">Review answers</Button>
            </Link>
          </div>
        </Card>
      ) : (
        <div
          className="mt-12 flex flex-wrap gap-3 animate-fade-up"
          style={{ animationDelay: "120ms" }}
        >
          <Link href="/library">
            <Button size="lg">
              <BookIcon className="size-4" />
              Back to your library
            </Button>
          </Link>
          <Link href={`/sessions/${sessionId}/review`}>
            <Button size="lg" variant="ghost">
              Review answers
            </Button>
          </Link>
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function TopicResultRow({ result }: { result: TopicResult }) {
  const pct = Math.round(result.accuracy * 100);
  const weak = result.accuracy < 0.5;

  return (
    <li className="rounded-xl border border-line bg-surface px-4 py-3">
      <div className="flex items-center justify-between gap-4">
        <span className="min-w-0 flex-1 truncate text-[15px] text-ink">
          {result.topic}
        </span>
        <span
          className={cx(
            "shrink-0 text-[13px] font-medium tabular-nums",
            weak ? "text-weak" : "text-mastered",
          )}
        >
          {result.correct}/{result.asked}
        </span>
      </div>

      <div className="mt-2.5 h-1 overflow-hidden rounded-full bg-raised">
        <div
          className={cx(
            "h-full rounded-full transition-[width] duration-700 ease-out",
            weak ? "bg-weak" : "bg-mastered",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[12px]">
        {result.partial > 0 && (
          <span className="text-ink-faint">{result.partial} partly correct</span>
        )}

        {/* Only rendered when there is a real earlier attempt to compare
            against - `improved` is null, not false, for a first attempt. */}
        {result.improved !== null && result.previous_asked !== null && (
          <>
            {result.partial > 0 && <span className="text-ink-ghost">·</span>}
            <span
              className={cx(
                "font-medium",
                result.improved
                  ? "text-mastered"
                  : result.accuracy < (result.previous_accuracy ?? 0)
                    ? "text-weak"
                    : "text-ink-faint",
              )}
            >
              {result.improved
                ? "Improved"
                : result.accuracy < (result.previous_accuracy ?? 0)
                  ? "Slipped"
                  : "Same as before"}
            </span>
            <span className="text-ink-ghost">
              last time {result.previous_correct}/{result.previous_asked}
            </span>
          </>
        )}
      </div>
    </li>
  );
}

function formatDuration(seconds: number) {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s === 0 ? `${m} min` : `${m} min ${s}s`;
}
