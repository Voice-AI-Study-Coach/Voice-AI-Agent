"use client";

import Link from "next/link";
import { useDocuments } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { Button, Card, EmptyState, Pill, ProgressBar } from "@/components/ui";
import { BookIcon, PlusIcon, SparkIcon } from "@/components/icons";
import type { DocumentSummary } from "@/lib/types";

export default function LibraryPage() {
  const { documents } = useDocuments();
  const { user } = useAuth();

  const hour = new Date().getHours();
  const greeting =
    hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  return (
    <div className="mx-auto max-w-4xl px-8 py-14">
      <header className="animate-fade-up">
        <h1 className="font-serif text-[32px] tracking-[-0.02em] text-ink">
          {greeting}, {user?.name?.split(" ")[0]}
        </h1>
        <p className="mt-1.5 text-[15px] text-ink-faint">
          {documents.length === 0
            ? "Upload your notes and I will quiz you on them."
            : "Pick up a document, or add a new one."}
        </p>
      </header>

      {documents.length === 0 ? (
        <EmptyState
          icon={<BookIcon className="size-5" />}
          title="No documents yet"
          body="Upload a PDF of your notes. I will split it by topic and write questions across five difficulty levels."
          action={
            <Link href="/upload">
              <Button size="lg">
                <PlusIcon className="size-4" />
                Upload a PDF
              </Button>
            </Link>
          }
        />
      ) : (
        <div
          className="mt-10 grid gap-3 animate-fade-up"
          style={{ animationDelay: "60ms" }}
        >
          {documents.map((doc) => (
            <DocumentCard key={doc.document_id} doc={doc} />
          ))}

          <Link href="/upload" className="mt-2">
            <div className="flex h-[52px] items-center justify-center gap-2 rounded-2xl border border-dashed border-line-strong text-[13px] font-medium text-ink-faint transition-colors hover:border-ink-ghost hover:bg-sunken hover:text-ink">
              <PlusIcon className="size-4" />
              Add another document
            </div>
          </Link>
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function DocumentCard({ doc }: { doc: DocumentSummary }) {
  const busy = doc.status === "pending" || doc.status === "processing";
  const failed = doc.status === "failed";
  const progress =
    doc.total_topics > 0 ? doc.covered_topics / doc.total_topics : 0;

  const href = busy
    ? `/upload?document_id=${doc.document_id}`
    : `/documents/${doc.document_id}`;

  return (
    <Link href={href}>
      <Card className="group px-5 py-4 transition-all duration-200 hover:border-line-strong elevate-hover">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <h3 className="truncate font-serif text-[17px] text-ink">
              {doc.filename.replace(/\.pdf$/i, "")}
            </h3>

            <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-ink-faint">
              {busy ? (
                <span className="flex items-center gap-1.5 text-ink-soft">
                  <span className="size-1.5 animate-pulse rounded-full bg-accent" />
                  Preparing your questions…
                </span>
              ) : failed ? (
                <span className="text-danger">Could not be processed</span>
              ) : (
                <>
                  <span>{doc.total_topics} topics</span>
                  {doc.session_count > 0 && (
                    <>
                      <span className="text-ink-ghost">·</span>
                      <span>
                        {doc.session_count}{" "}
                        {doc.session_count === 1 ? "session" : "sessions"}
                      </span>
                    </>
                  )}
                </>
              )}
            </div>
          </div>

          {!busy && !failed && doc.covered_topics > 0 && (
            <Pill tone="accent">
              {doc.covered_topics}/{doc.total_topics} covered
            </Pill>
          )}
          {!busy && !failed && doc.covered_topics === 0 && (
            <Pill>
              <SparkIcon className="size-3" />
              Not started
            </Pill>
          )}
        </div>

        {!busy && !failed && doc.total_topics > 0 && (
          <ProgressBar value={progress} className="mt-3.5" />
        )}
      </Card>
    </Link>
  );
}
