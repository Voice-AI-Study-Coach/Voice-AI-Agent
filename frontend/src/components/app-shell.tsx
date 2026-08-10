"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { DocumentSummary } from "@/lib/types";
import { useAuth } from "./auth-provider";
import { Sidebar } from "./sidebar";
import { Spinner } from "./ui";

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

  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [docsLoading, setDocsLoading] = useState(true);

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

  useEffect(() => {
    if (user) refresh();
  }, [user, refresh]);

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
        <Sidebar documents={documents} loading={docsLoading} />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </DocumentsContext.Provider>
  );
}
