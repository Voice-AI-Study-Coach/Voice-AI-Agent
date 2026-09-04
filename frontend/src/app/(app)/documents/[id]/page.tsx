"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { QUESTIONS_PER_TOPIC } from "@/lib/config";
import { useDocuments } from "@/components/app-shell";
import {
  Button,
  Card,
  cx,
  EmptyState,
  ErrorNote,
  Pill,
  Spinner,
} from "@/components/ui";
import {
  AlertIcon,
  ArrowRightIcon,
  BookIcon,
  CheckIcon,
  SparkIcon,
  TrashIcon,
} from "@/components/icons";
import type { DocumentTopicsResponse, TopicInfo } from "@/lib/types";

export default function DocumentPage() {
  return (
    <Suspense fallback={null}>
      <DocumentInner />
    </Suspense>
  );
}

function DocumentInner() {
  const { id } = useParams<{ id: string }>();
  const documentId = Number(id);
  const router = useRouter();
  const params = useSearchParams();
  const { refresh } = useDocuments();

  const [data, setData] = useState<DocumentTopicsResponse | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  // null = the "already covered" question has not been answered yet.
  const [includeCovered, setIncludeCovered] = useState<boolean | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api.documentTopics(documentId);
      setData(res);
      // Only set initial state on first load
      setIncludeCovered((prev) => (prev === null ? (res.covered_topics > 0 ? null : true) : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load topics");
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    load();
  }, [load]);

  // Live polling while topics are generating in the background
  useEffect(() => {
    if (!data) return;
    if (data.status !== "generating") return;

    const interval = setInterval(async () => {
      try {
        const res = await api.documentTopics(documentId);
        setData(res);
      } catch {
        /* ignore transient polling errors */
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [documentId, data?.status]);

  const visible = useMemo(() => {
    if (!data) return [];
    // Topics with no generated questions are hidden until ready:
    // they pop up live as soon as their questions land in Postgres.
    const quizzable = data.topics.filter((t) => t.quizzable);
    if (includeCovered === false) return quizzable.filter((t) => !t.covered);
    return quizzable;
  }, [data, includeCovered]);

  function toggle(topic: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(topic) ? next.delete(topic) : next.add(topic);
      return next;
    });
  }

  async function start(abandonActive = false) {
    setError("");
    setStarting(true);
    try {
      const res = await api.startSession(documentId, [...selected], abandonActive);
      // Without this the sidebar's session count/list for this document
      // stayed stale until a manual page reload - the new session's row
      // (and its title, once given a real one) only showed up after the
      // student happened to refresh, not the moment the quiz actually
      // started. Not awaited: the sidebar catching up a beat after
      // navigation is fine, but blocking the redirect on it is not.
      refresh();
      router.push(`/sessions/${res.session_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the quiz");
      setStarting(false);
    }
  }

  function resumeActiveSession() {
    if (data?.active_session) {
      router.push(`/sessions/${data.active_session.session_id}`);
    }
  }

  async function remove() {
    if (!confirm("Delete this document and all its quiz history?")) return;
    try {
      await api.deleteDocument(documentId);
      await refresh();
      router.push("/library");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete");
    }
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner className="size-5 text-ink-ghost" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 sm:px-8">
        <ErrorNote>{error || "Document not found"}</ErrorNote>
      </div>
    );
  }

  const quizzable = data.topics.filter((t) => t.quizzable);
  const selectedCount = selected.size;
  const allVisibleSelected =
    visible.length > 0 && visible.every((t) => selected.has(t.topic));

  return (
    <div className="mx-auto max-w-3xl px-4 py-14 pb-32 sm:px-8">
      {/* Header */}
      <header className="animate-fade-up">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="font-serif text-[30px] tracking-[-0.02em] text-ink">
              {data.filename.replace(/\.pdf$/i, "")}
            </h1>
            {/* Counts the quizzable topics, not every heading in the PDF -
                the number has to match the list underneath it. */}
            <p className="mt-1.5 text-[15px] text-ink-faint">
              {quizzable.length} {quizzable.length === 1 ? "topic" : "topics"}
              {data.covered_topics > 0 &&
                ` · ${data.covered_topics} already covered`}
            </p>
          </div>
          <button
            onClick={remove}
            title="Delete document"
            className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-lg text-ink-ghost transition-colors hover:bg-danger-soft hover:text-danger"
          >
            <TrashIcon className="size-4" />
          </button>
        </div>
      </header>

      {/* Recognised-on-re-upload notice */}
      {params.get("seen") === "1" && (
        <Card className="mt-6 flex items-start gap-3 border-accent/20 bg-accent-soft/40 px-4 py-3.5 animate-fade-in">
          <CheckIcon className="mt-0.5 size-4 shrink-0 text-accent-deep" />
          <p className="text-[13px] leading-relaxed text-ink-soft">
            You have uploaded this PDF before, so nothing needed re-processing.
            Your previous progress is below.
          </p>
        </Card>
      )}

      {/* Arrived here from a finished session's "keep going" */}
      {params.get("continue") === "1" && (
        <Card className="mt-6 flex items-start gap-3 border-accent/20 bg-accent-soft/40 px-4 py-3.5 animate-fade-in">
          <SparkIcon className="mt-0.5 size-4 shrink-0 text-accent-deep" />
          <p className="text-[13px] leading-relaxed text-ink-soft">
            Pick what to cover next. Starting will create a new session, so your
            last one keeps its own summary.
          </p>
        </Card>
      )}

      {/* Unfinished session on this document */}
      {data.active_session && (
        <Card
          className="mt-6 border-accent/30 bg-accent-soft/50 px-5 py-4 animate-fade-up"
        >
          <p className="font-serif text-[17px] text-ink">
            You have an unfinished quiz - {data.active_session.questions_asked}{" "}
            of {data.active_session.total_questions} answered.
          </p>
          <p className="mt-1 text-[13px] leading-relaxed text-ink-faint">
            Resume where you left off, on &ldquo;{data.active_session.current_topic}
            &rdquo;, or start a fresh session with the topics below.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button size="sm" onClick={resumeActiveSession}>
              Resume quiz
              <ArrowRightIcon className="size-3.5" />
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={selectedCount === 0}
              loading={starting}
              onClick={() => start(true)}
            >
              Start fresh instead
            </Button>
          </div>
        </Card>
      )}

      {/* Already-covered question */}
      {includeCovered === null && (
        <Card
          className="mt-6 px-5 py-4 animate-fade-up"
          style={{ animationDelay: "40ms" }}
        >
          <p className="font-serif text-[17px] text-ink">
            You have already been quizzed on {data.covered_topics}{" "}
            {data.covered_topics === 1 ? "topic" : "topics"} here.
          </p>
          <p className="mt-1 text-[13px] leading-relaxed text-ink-faint">
            Want to include those again, or focus on what is left?
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button size="sm" onClick={() => setIncludeCovered(true)}>
              Include covered topics
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                setIncludeCovered(false);
                // Drop covered topics from the default selection to match
                // what is now on screen.
                setSelected(
                  (prev) =>
                    new Set(
                      [...prev].filter(
                        (t) =>
                          !data.topics.find((x) => x.topic === t)?.covered,
                      ),
                    ),
                );
              }}
            >
              Only what is left
            </Button>
          </div>
        </Card>
      )}

      {/* Topic list */}
      {quizzable.length === 0 ? (
        data.status === "generating" ? (
          <Card className="mt-8 flex items-center justify-center gap-3.5 border-accent/20 bg-accent-soft/30 p-8 text-center animate-fade-in">
            <Spinner className="size-5 shrink-0 text-accent" />
            <div className="text-left">
              <p className="text-sm font-medium text-ink">Writing questions for your topics…</p>
              <p className="text-[13px] text-ink-faint">
                Topics will pop up here live as questions finish generating ({data.topics.length} topics detected).
              </p>
            </div>
          </Card>
        ) : (
          <EmptyState
            icon={<AlertIcon className="size-5" />}
            title="No questions were generated"
            body="This document's sections were too short to write questions from. Try a PDF with more body text per heading."
          />
        )
      ) : (
        <>
          {data.status === "generating" && (
            <div className="mt-6 flex items-center gap-2.5 rounded-xl border border-accent/20 bg-accent-soft/40 px-4 py-3 text-[13px] text-ink-soft animate-fade-in">
              <Spinner className="size-3.5 shrink-0 text-accent" />
              <span>
                Writing questions for remaining topics… ({quizzable.length} of {data.topics.length} ready)
              </span>
            </div>
          )}

          <div
            className="mt-8 flex items-center justify-between animate-fade-up"
            style={{ animationDelay: "80ms" }}
          >
            <p className="text-[11px] font-medium uppercase tracking-[0.1em] text-ink-ghost">
              Choose your topics
            </p>
            <button
              onClick={() =>
                setSelected(
                  allVisibleSelected
                    ? new Set()
                    : new Set(visible.map((t) => t.topic)),
                )
              }
              className="text-[13px] text-ink-faint transition-colors hover:text-ink"
            >
              {allVisibleSelected ? "Clear all" : "Select all"}
            </button>
          </div>

          <ul
            className="mt-3 space-y-1.5 animate-fade-up"
            style={{ animationDelay: "100ms" }}
          >
            {visible.map((topic) => (
              <TopicRow
                key={topic.topic}
                topic={topic}
                checked={selected.has(topic.topic)}
                onToggle={() => toggle(topic.topic)}
              />
            ))}
          </ul>
        </>
      )}

      {error && (
        <div className="mt-6">
          <ErrorNote>{error}</ErrorNote>
        </div>
      )}

      {/* Start bar */}
      {selectedCount > 0 && (
        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-paper/85 backdrop-blur-md">
          <div className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-4 py-4 sm:px-8">
            <div>
              <p className="text-sm font-medium text-ink">
                {selectedCount} {selectedCount === 1 ? "topic" : "topics"}{" "}
                selected
              </p>
              <p className="text-[13px] text-ink-faint">
                {selectedCount * QUESTIONS_PER_TOPIC} questions, adapting as you
                go
              </p>
            </div>
            <Button
              size="lg"
              loading={starting}
              onClick={() => start(Boolean(data.active_session))}
            >
              Start quiz
              <ArrowRightIcon className="size-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function TopicRow({
  topic,
  checked,
  onToggle,
}: {
  topic: TopicInfo;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <li>
      {/* A real button rather than a label wrapping a visually-hidden input:
          the hidden-input trick relies on the label forwarding clicks, which
          is fragile, and a button gives keyboard and screen-reader behaviour
          without any of that indirection. */}
      <button
        type="button"
        role="checkbox"
        aria-checked={checked}
        aria-label={topic.topic}
        onClick={onToggle}
        className={cx(
          "flex w-full cursor-pointer items-center gap-3.5 rounded-xl border px-4 py-3 text-left transition-all duration-150",
          checked
            ? "border-ink/15 bg-surface elevate-sm"
            : "border-line bg-surface/60 hover:border-line-strong hover:bg-surface",
        )}
      >
        <span
          className={cx(
            "flex size-[18px] shrink-0 items-center justify-center rounded-[5px] border transition-all duration-150",
            checked
              ? "border-ink bg-ink text-paper"
              : "border-line-strong bg-surface",
          )}
        >
          {checked && <CheckIcon className="size-3" strokeWidth={2.5} />}
        </span>

        <span className="min-w-0 flex-1">
          <span className="flex items-baseline gap-2">
            <span
              className={cx(
                "truncate text-[15px]",
                // Mastered is de-emphasised, not struck through: the student
                // may still want to redo it, and strikethrough reads as "gone".
                topic.state === "mastered" ? "text-ink-faint" : "text-ink",
              )}
            >
              {topic.topic}
            </span>
          </span>

          <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12px] text-ink-faint">
            {topic.covered ? (
              <span>
                {topic.correct_count}/{topic.times_asked} correct
              </span>
            ) : (
              <span className="text-ink-ghost">
                {topic.question_count} questions ready
              </span>
            )}
            {topic.parent && (
              <>
                <span className="text-ink-ghost">·</span>
                <span className="text-ink-ghost">{topic.parent}</span>
              </>
            )}
          </span>
        </span>

        <StatePill topic={topic} />
      </button>
    </li>
  );
}

/** The three states come from the backend so "weak" means the same thing here
 *  as it does in the session summary. */
function StatePill({ topic }: { topic: TopicInfo }) {
  if (topic.state === "weak") {
    return <Pill tone="weak">Worth revisiting</Pill>;
  }
  if (topic.state === "mastered") {
    return (
      <Pill tone="mastered">
        {Math.round((topic.accuracy ?? 0) * 100)}%
      </Pill>
    );
  }
  return null;
}
