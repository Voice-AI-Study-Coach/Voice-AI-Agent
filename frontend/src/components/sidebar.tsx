"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { api } from "@/lib/api";
import type { DocumentSummary, SessionListItem } from "@/lib/types";
import { useAuth } from "./auth-provider";
import { ThemeToggle } from "./theme-toggle";
import { cx, Spinner } from "./ui";
import {
  ChevronDownIcon,
  ChevronIcon,
  FileIcon,
  LogoutIcon,
  PanelIcon,
  PlusIcon,
} from "./icons";

const COLLAPSE_KEY = "sc:sidebar-collapsed";

export function Sidebar({
  documents,
  loading,
}: {
  documents: DocumentSummary[];
  loading: boolean;
}) {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  const [collapsed, setCollapsed] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [menuOpen, setMenuOpen] = useState(false);

  // Read the stored preference after mount: touching localStorage during
  // render would not match the server-rendered HTML.
  useEffect(() => {
    setCollapsed(localStorage.getItem(COLLAPSE_KEY) === "1");
  }, []);

  function toggleCollapsed() {
    setCollapsed((c) => {
      localStorage.setItem(COLLAPSE_KEY, c ? "0" : "1");
      return !c;
    });
  }

  function toggleDoc(id: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  return (
    <aside
      className={cx(
        // min-h-0 lets the nav scroll instead of the whole column growing past
        // the viewport and pushing the profile row off the bottom.
        "relative flex h-full min-h-0 shrink-0 flex-col border-r border-line bg-sunken",
        "transition-[width] duration-200 ease-out",
        collapsed ? "w-[60px]" : "w-[264px]",
      )}
    >
      {/* Header */}
      <div className="flex h-14 items-center gap-2 px-3">
        <button
          onClick={toggleCollapsed}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="flex size-8 shrink-0 items-center justify-center rounded-lg text-ink-faint transition-colors hover:bg-raised hover:text-ink"
        >
          <PanelIcon />
        </button>
        {!collapsed && (
          <Link
            href="/library"
            className="flex items-center gap-2 overflow-hidden"
          >
            <span className="font-serif text-[15px] whitespace-nowrap text-ink">
              Study Coach
            </span>
          </Link>
        )}
      </div>

      {/* New document */}
      <div className={cx("px-3 pb-2", collapsed && "px-2")}>
        <Link href="/upload">
          <button
            title="New document"
            className={cx(
              "flex items-center rounded-[10px] border border-line-strong bg-surface",
              "text-[13px] font-medium text-ink transition-all duration-150",
              "hover:bg-raised hover:border-ink-ghost active:scale-[0.985]",
              collapsed
                ? "size-9 justify-center mx-auto"
                : "h-9 w-full gap-2 px-3",
            )}
          >
            <PlusIcon className="size-4 shrink-0" />
            {!collapsed && <span>New document</span>}
          </button>
        </Link>
      </div>

      {/* Documents */}
      <nav className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-3 pb-3">
        {!collapsed && (
          <p className="px-2 pb-1.5 pt-3 text-[11px] font-medium uppercase tracking-[0.1em] text-ink-ghost">
            Documents
          </p>
        )}

        {loading ? (
          <div className="space-y-1.5 pt-1">
            {[0, 1, 2].map((i) => (
              <div key={i} className="skeleton h-8 rounded-lg" />
            ))}
          </div>
        ) : documents.length === 0 ? (
          !collapsed && (
            <p className="px-2 py-3 text-[13px] leading-relaxed text-ink-ghost">
              Nothing here yet. Upload a PDF to begin.
            </p>
          )
        ) : (
          <ul className="space-y-0.5">
            {documents.map((doc) => (
              <DocumentRow
                key={doc.document_id}
                doc={doc}
                collapsed={collapsed}
                active={pathname.includes(`/documents/${doc.document_id}`)}
                expanded={expanded.has(doc.document_id)}
                onToggle={() => toggleDoc(doc.document_id)}
              />
            ))}
          </ul>
        )}
      </nav>

      {/* Profile, pinned to the bottom */}
      <div className="relative border-t border-line p-2">
        {menuOpen && !collapsed && (
          <>
            <div
              className="fixed inset-0 z-10"
              onClick={() => setMenuOpen(false)}
            />
            <div className="absolute bottom-full left-2 right-2 z-20 mb-1 overflow-hidden rounded-xl border border-line bg-surface elevate-lg animate-fade-up">
              <div className="border-b border-line px-3 py-2.5">
                <p className="truncate text-[13px] font-medium text-ink">
                  {user?.name}
                </p>
                <p className="truncate text-[11px] text-ink-faint">
                  {user?.email}
                </p>
              </div>
              <div className="p-1">
                <ThemeToggle showLabel />
              </div>
              <button
                onClick={logout}
                className="flex w-full items-center gap-2.5 border-t border-line px-3 py-2.5 text-[13px] text-ink-soft transition-colors hover:bg-raised hover:text-ink"
              >
                <LogoutIcon className="size-4" />
                Sign out
              </button>
            </div>
          </>
        )}

        <button
          onClick={() => (collapsed ? toggleCollapsed() : setMenuOpen((o) => !o))}
          title={user?.name}
          className={cx(
            "flex items-center rounded-[10px] transition-colors hover:bg-raised",
            collapsed ? "size-9 justify-center mx-auto" : "w-full gap-2.5 p-2",
          )}
        >
          <Avatar name={user?.name ?? "?"} />
          {!collapsed && (
            <>
              <span className="flex-1 truncate text-left text-[13px] font-medium text-ink">
                {user?.name ?? "Loading…"}
              </span>
              <ChevronDownIcon className="size-3.5 shrink-0 text-ink-ghost" />
            </>
          )}
        </button>
      </div>
    </aside>
  );
}

/* -------------------------------------------------------------------------- */

function Avatar({ name }: { name: string }) {
  return (
    <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-ink text-[11px] font-semibold text-paper">
      {name.charAt(0).toUpperCase()}
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function DocumentRow({
  doc,
  collapsed,
  active,
  expanded,
  onToggle,
}: {
  doc: DocumentSummary;
  collapsed: boolean;
  active: boolean;
  expanded: boolean;
  onToggle: () => void;
}) {
  const [sessions, setSessions] = useState<SessionListItem[] | null>(null);
  // The list is cached once fetched (below), so a session started elsewhere
  // (the document page's "Start quiz") would never appear here until a full
  // reload rebuilt this component from scratch. session_count IS refreshed
  // by the shared documents context though, so a change in it is used as
  // the signal to drop the cache and refetch, without polling.
  const [fetchedForCount, setFetchedForCount] = useState<number | null>(null);

  // Sessions are not in the sidebar payload, so they are fetched on first
  // expand rather than up front for every document.
  useEffect(() => {
    if (!expanded || fetchedForCount === doc.session_count) return;
    let cancelled = false;
    api
      .sessionsFor(doc.document_id)
      .then((rows) => {
        if (cancelled) return;
        setSessions(rows);
        setFetchedForCount(doc.session_count);
      })
      .catch(() => {
        if (cancelled) return;
        setSessions([]);
        setFetchedForCount(doc.session_count);
      });
    return () => {
      cancelled = true;
    };
  }, [expanded, fetchedForCount, doc.session_count, doc.document_id]);

  if (collapsed) {
    return (
      <li>
        <Link
          href={`/documents/${doc.document_id}`}
          title={doc.filename}
          className={cx(
            "flex size-9 items-center justify-center rounded-lg transition-colors",
            active
              ? "bg-raised text-ink"
              : "text-ink-faint hover:bg-raised hover:text-ink",
          )}
        >
          <FileIcon className="size-4" />
        </Link>
      </li>
    );
  }

  return (
    <li>
      <div
        className={cx(
          "group flex items-center rounded-lg transition-colors",
          active ? "bg-raised" : "hover:bg-raised",
        )}
      >
        {doc.session_count > 0 ? (
          <button
            onClick={onToggle}
            className="flex size-7 shrink-0 items-center justify-center text-ink-ghost transition-colors hover:text-ink"
            title={expanded ? "Hide sessions" : "Show sessions"}
          >
            <ChevronIcon
              className={cx(
                "size-3.5 transition-transform duration-200",
                expanded && "rotate-90",
              )}
            />
          </button>
        ) : (
          <span className="size-7 shrink-0" />
        )}

        <Link
          href={`/documents/${doc.document_id}`}
          className="flex min-w-0 flex-1 items-center gap-2 py-1.5 pr-2"
        >
          <span
            className={cx(
              "truncate text-[13px]",
              active ? "text-ink font-medium" : "text-ink-soft",
            )}
          >
            {doc.filename.replace(/\.pdf$/i, "")}
          </span>
          {doc.status === "processing" || doc.status === "pending" ? (
            <Spinner className="size-3 shrink-0 text-ink-ghost" />
          ) : doc.status === "failed" ? (
            <span className="size-1.5 shrink-0 rounded-full bg-danger" />
          ) : null}
        </Link>
      </div>

      {expanded && (
        <ul className="ml-7 mt-0.5 space-y-0.5 border-l border-line pl-2">
          {sessions === null ? (
            <li className="py-1.5 pl-2 text-[12px] text-ink-ghost">Loading…</li>
          ) : sessions.length === 0 ? (
            <li className="py-1.5 pl-2 text-[12px] text-ink-ghost">
              No sessions yet
            </li>
          ) : (
            sessions.map((s) => (
              <li key={s.session_id}>
                <Link
                  href={`/sessions/${s.session_id}/review`}
                  className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-[12px] text-ink-faint transition-colors hover:bg-raised hover:text-ink"
                  title={sessionTitle(s)}
                >
                  <span className="truncate">{sessionTitle(s)}</span>
                  <span className="shrink-0 tabular-nums text-ink-ghost">
                    {s.correct_count}/{s.questions_asked}
                  </span>
                </Link>
              </li>
            ))
          )}
        </ul>
      )}
    </li>
  );
}

/** A student cannot tell "Aug 12" apart from any other session on the same
 *  document - naming it after the topic(s) actually covered says something
 *  they can recognize at a glance. Falls back to the date only for the rare
 *  row with no topics recorded at all. */
function sessionTitle(s: SessionListItem): string {
  const topics = s.selected_topics;
  if (topics.length === 0) {
    return s.started_at
      ? new Date(s.started_at).toLocaleDateString(undefined, {
          month: "short",
          day: "numeric",
        })
      : "Session";
  }
  if (topics.length === 1) return topics[0];
  return `${topics[0]} & ${topics.length - 1} more`;
}
