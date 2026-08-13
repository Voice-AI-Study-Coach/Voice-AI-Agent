import type {
  AnswerResponse,
  DocumentSummary,
  DocumentStatus,
  DocumentTopicsResponse,
  NewChatResponse,
  SessionListItem,
  SessionReplayResponse,
  SkipResponse,
  StartSessionResponse,
  SummaryResponse,
  User,
} from "./types";

/** Requests go through Next's rewrite to the FastAPI server, so they are
 *  same-origin and the HttpOnly auth cookie is sent automatically. */
const BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isUnauthorized() {
    return this.status === 401;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    ...init,
    headers: {
      ...(init.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...init.headers,
    },
  });

  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      // FastAPI puts the message in `detail`; validation errors make it an
      // array of objects, so flatten those into something readable.
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail)) {
        message = body.detail.map((d: { msg?: string }) => d.msg).join(", ");
      }
    } catch {
      /* response had no JSON body - keep the status text */
    }
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  // --- auth ---------------------------------------------------------------
  signup: (name: string, email: string, password: string) =>
    request<string>("/signup", {
      method: "POST",
      body: JSON.stringify({ name, email, password }),
    }),

  login: (email: string, password: string) =>
    request<{ message: string; name: string }>("/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  logout: () => request<string>("/logout", { method: "DELETE" }),

  me: () => request<User>("/me"),

  // --- documents ----------------------------------------------------------
  documents: () => request<DocumentSummary[]>("/rag/documents"),

  documentStatus: (id: number) =>
    request<DocumentStatus>(`/rag/documents/${id}`),

  documentTopics: (id: number) =>
    request<DocumentTopicsResponse>(`/rag/documents/${id}/topics`),

  deleteDocument: (id: number) =>
    request<string>(`/rag/documents/${id}`, { method: "DELETE" }),

  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<NewChatResponse>("/rag/newChat", {
      method: "POST",
      body: form,
    });
  },

  // --- sessions -----------------------------------------------------------
  startSession: (
    document_id: number,
    selected_topics: string[],
    abandon_active = false,
  ) =>
    request<StartSessionResponse>("/sessions", {
      method: "POST",
      body: JSON.stringify({ document_id, selected_topics, abandon_active }),
    }),

  answer: (session_id: number, transcript: string, stt_ms?: number) =>
    request<AnswerResponse>(`/sessions/${session_id}/answer`, {
      method: "POST",
      body: JSON.stringify({ transcript, stt_ms: stt_ms ?? null }),
    }),

  /** Send a recorded answer for server-side transcription (Deepgram nova-3).
   *  Transcription runs on the backend, not in the browser, so it does not
   *  depend on the client being able to reach Google's speech servers. */
  transcribeAudio: (audio: Blob, filename = "answer.webm") => {
    const form = new FormData();
    form.append("file", audio, filename);
    return request<{ transcript: string; duration_ms: number }>(
      "/speech/transcribe",
      { method: "POST", body: form },
    );
  },

  // Coach speech is not fetched here: `speech/tts.ts` points an <audio>
  // element straight at /speech/speak so playback starts while the clip is
  // still downloading. Fetching it would mean waiting for the whole file.

  /** The student went quiet and was asked whether to move on. */
  skip: (session_id: number, accepted: boolean) =>
    request<SkipResponse>(`/sessions/${session_id}/skip`, {
      method: "POST",
      body: JSON.stringify({ accepted }),
    }),

  /** Past sessions on one document, newest first. */
  sessionsFor: (document_id: number) =>
    request<SessionListItem[]>(`/sessions?document_id=${document_id}`),

  session: (session_id: number) =>
    request<SessionReplayResponse>(`/sessions/${session_id}`),

  summary: (session_id: number) =>
    request<SummaryResponse>(`/sessions/${session_id}/summary`),
};
