"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { DocumentSummary } from "@/lib/types";
import { useAuth } from "./auth-provider";
import { Sidebar } from "./sidebar";
import { cx, Spinner } from "./ui";
import { PanelIcon } from "./icons";

interface DocumentsValue {
  documents: DocumentSummary[];
  refresh: () => Promise<void>;
}

const DocumentsContext = createContext<DocumentsValue>({
  documents: [],
  refresh: async () => {},
});

/** Pages call this after uploading or deleting so the sidebar updates without
 *  a full reload. */
export function useDocuments() {
  return useContext(DocumentsContext);
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [docsLoading, setDocsLoading] = useState(true);
  // The sidebar is an always-visible column on desktop but a slide-over
  // drawer on mobile (there is no room for both it and page content at once
  // below the md breakpoint) - closed by default so it never covers the
  // page on first load.
  const [mobileOpen, setMobileOpen] = useState(false);

  // Close the drawer on navigation - otherwise picking a document/session
  // leaves it open over the new page.
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [authLoading, user, router]);

  const refresh = useCallback(async () => {
    try {
      setDocuments(await api.documents());
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized) router.replace("/login");
    } finally {
      setDocsLoading(false);
    }
  }, [router]);

  // Fired on mount, not gated on `user` resolving first: /me and /documents
  // both only need the session cookie, which is already on the request, so
  // waiting for /me to finish before starting /documents serialized two
  // round-trips that could run in parallel - the sidebar was visibly slower
  // to appear than it needed to be. A stale cookie fails both calls the same
  // way (401), so nothing is lost by not waiting.
  useEffect(() => {
    refresh();
  }, [refresh]);

  if (authLoading || !user) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Spinner className="size-5 text-ink-ghost" />
      </div>
    );
  }

  return (
    <DocumentsContext.Provider value={{ documents, refresh }}>
      <div className="flex h-screen overflow-hidden">
        {/* Desktop: a normal column. Mobile: an overlay drawer, positioned
            off-canvas until opened - see the translate classes below. */}
        <div
          className={cx(
            "fixed inset-y-0 left-0 z-40 md:static md:z-auto",
            "transition-transform duration-200 ease-out md:transition-none",
            mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
          )}
        >
          <Sidebar
            documents={documents}
            loading={docsLoading}
            onNavigate={() => setMobileOpen(false)}
          />
        </div>

        {mobileOpen && (
          <div
            aria-hidden
            onClick={() => setMobileOpen(false)}
            className="fixed inset-0 z-30 bg-ink/40 md:hidden"
          />
        )}

        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          {/* Mobile-only top bar: the sidebar's own toggle button is
              off-canvas when collapsed, so opening it needs a control that is
              always on screen. */}
          <div className="flex h-14 shrink-0 items-center gap-2 border-b border-line px-3 md:hidden">
            <button
              onClick={() => setMobileOpen(true)}
              aria-label="Open menu"
              className="flex size-9 items-center justify-center rounded-lg text-ink-faint transition-colors hover:bg-raised hover:text-ink"
            >
              <PanelIcon />
            </button>
            <span className="font-serif text-[15px] text-ink">Study Coach</span>
          </div>
          <main className="flex-1 overflow-y-auto">{children}</main>
        </div>
      </div>
    </DocumentsContext.Provider>
  );
}
