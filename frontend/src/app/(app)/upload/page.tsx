"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { INGESTION_POLL_MS, MAX_UPLOAD_MB } from "@/lib/config";
import { useDocuments } from "@/components/app-shell";
import { Button, Card, cx, ErrorNote, Spinner } from "@/components/ui";
import { CheckIcon, FileIcon, SparkIcon, UploadIcon } from "@/components/icons";

const STAGES = [
  "Reading the document",
  "Splitting it into topics",
  "Writing questions for each topic",
  "Almost there",
];

export default function UploadPage() {
  return (
    <Suspense fallback={null}>
      <UploadInner />
    </Suspense>
  );
}

function UploadInner() {
  const router = useRouter();
  const params = useSearchParams();
  const { refresh } = useDocuments();

  // Resuming a document that was still processing when the user navigated away.
  const resumeId = params.get("document_id");

  const [documentId, setDocumentId] = useState<number | null>(
    resumeId ? Number(resumeId) : null,
  );
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [stage, setStage] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const upload = useCallback(
    async (file: File) => {
      setError("");

      if (!file.name.toLowerCase().endsWith(".pdf")) {
        setError("Only PDF files are supported.");
        return;
      }

      setUploading(true);
      try {
        const res = await api.upload(file);
        await refresh();

        // An identical PDF was already ingested, so there is nothing to wait
        // for - go straight to topic selection.
        if (res.already_seen) {
          router.push(`/documents/${res.document_id}?seen=1`);
          return;
        }
        setDocumentId(res.document_id);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Upload failed");
        setUploading(false);
      }
    },
    [refresh, router],
  );

  // Poll until ingestion finishes. The backend marks the row 'failed' rather
  // than leaving it stuck, so this terminates either way.
  useEffect(() => {
    if (documentId === null) return;
    let cancelled = false;

    const tick = async () => {
      try {
        const doc = await api.documentStatus(documentId);
        if (cancelled) return;
        if (doc.status === "ready") {
          await refresh();
          router.push(`/documents/${documentId}`);
          return;
        }
        if (doc.status === "failed") {
          setError(doc.error ?? "This document could not be processed.");
          setUploading(false);
          setDocumentId(null);
          await refresh();
          return;
        }
      } catch {
        /* transient - the next tick retries */
      }
      if (!cancelled) timer = setTimeout(tick, INGESTION_POLL_MS);
    };

    let timer = setTimeout(tick, INGESTION_POLL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [documentId, refresh, router]);

  // Advance the stage copy on a timer. This is honest about being an estimate:
  // the backend reports one 'processing' status with no sub-steps, and a fake
  // percentage bar would be worse than none.
  useEffect(() => {
    if (documentId === null) return;
    const id = setInterval(
      () => setStage((s) => Math.min(s + 1, STAGES.length - 1)),
      14_000,
    );
    return () => clearInterval(id);
  }, [documentId]);

  const processing = documentId !== null;

  return (
    <div className="mx-auto max-w-2xl px-4 py-10 sm:px-8 sm:py-16">
      <header className="animate-fade-up">
        <h1 className="font-serif text-[30px] tracking-[-0.02em] text-ink">
          {processing ? "Preparing your document" : "Add a document"}
        </h1>
        <p className="mt-1.5 text-[15px] text-ink-faint">
          {processing
            ? "This takes a couple of minutes. You can leave this page — it keeps going."
            : "Upload a PDF of your notes, a chapter, or a set of slides."}
        </p>
      </header>

      <div className="mt-10 animate-fade-up" style={{ animationDelay: "60ms" }}>
        {processing ? (
          <ProcessingCard stage={stage} />
        ) : (
          <>
            <label
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                const file = e.dataTransfer.files?.[0];
                if (file) upload(file);
              }}
              className={cx(
                "flex cursor-pointer flex-col items-center justify-center gap-4",
                "rounded-2xl border-2 border-dashed px-8 py-20 text-center",
                "transition-all duration-200",
                dragging
                  ? "border-accent bg-accent-soft/40 scale-[1.01]"
                  : "border-line-strong bg-surface hover:border-ink-ghost hover:bg-sunken",
                uploading && "pointer-events-none opacity-60",
              )}
            >
              <input
                ref={inputRef}
                type="file"
                accept="application/pdf,.pdf"
                className="sr-only"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) upload(file);
                }}
              />

              <div
                className={cx(
                  "flex size-12 items-center justify-center rounded-2xl transition-colors",
                  dragging ? "bg-accent text-paper" : "bg-raised text-ink-faint",
                )}
              >
                {uploading ? (
                  <Spinner className="size-5" />
                ) : (
                  <UploadIcon className="size-5" />
                )}
              </div>

              <div>
                <p className="text-[15px] font-medium text-ink">
                  {uploading
                    ? "Uploading…"
                    : dragging
                      ? "Drop it here"
                      : "Drop a PDF, or click to browse"}
                </p>
                <p className="mt-1 text-[13px] text-ink-faint">
                  Printed or handwritten PDFs, up to {MAX_UPLOAD_MB} MB
                </p>
              </div>
            </label>

            <p className="mt-4 flex items-start gap-2 text-[13px] leading-relaxed text-ink-faint">
              <SparkIcon className="mt-0.5 size-3.5 shrink-0 text-ink-ghost" />
              <span>
                Uploaded this one before? It is recognised by its contents, not
                its name, so you go straight to the topics.
              </span>
            </p>
          </>
        )}

        <div className="mt-5">
          <ErrorNote>{error}</ErrorNote>
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function ProcessingCard({ stage }: { stage: number }) {
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center gap-3 border-b border-line bg-sunken px-5 py-4">
        <div className="relative flex size-9 items-center justify-center">
          <span className="absolute inset-0 rounded-full bg-accent-soft animate-breathe" />
          <FileIcon className="relative size-4 text-accent-deep" />
        </div>
        <div>
          <p className="text-sm font-medium text-ink">Working on it</p>
          <p className="text-[13px] text-ink-faint">
            Reading, splitting and writing questions
          </p>
        </div>
      </div>

      <ol className="p-5 space-y-3.5">
        {STAGES.map((label, i) => {
          const done = i < stage;
          const active = i === stage;
          return (
            <li key={label} className="flex items-center gap-3">
              <span
                className={cx(
                  "flex size-5 shrink-0 items-center justify-center rounded-full border transition-colors",
                  done
                    ? "border-mastered bg-mastered text-paper"
                    : active
                      ? "border-accent text-accent"
                      : "border-line-strong text-transparent",
                )}
              >
                {done ? (
                  <CheckIcon className="size-3" />
                ) : active ? (
                  <span className="size-1.5 rounded-full bg-accent animate-pulse" />
                ) : null}
              </span>
              <span
                className={cx(
                  "text-sm transition-colors",
                  done
                    ? "text-ink-faint"
                    : active
                      ? "text-ink font-medium"
                      : "text-ink-ghost",
                )}
              >
                {label}
              </span>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
