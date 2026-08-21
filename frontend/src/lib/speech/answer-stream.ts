/* ---------------------------------------------------------------------------
   Streaming answer client.

   Replaces the POST /answer + speak(coach_reply) pair with one socket. On the
   POST path nothing reaches the browser until the coach's whole reply exists,
   and TTS only starts after that - so the text finished rendering before the
   voice began. Here the backend runs the same engine but emits each phrase's
   text and audio together, so the coach starts speaking while the rest of the
   sentence is still being written.

   Text and voice are kept in step the way captions are: a phrase's text is
   revealed when its audio starts, not when the model produced it. The model
   writes far faster than speech, so revealing on generation would put the
   whole reply on screen while the voice was still on its first few words.

   The socket is opened once per quiz session and reused for every answer:
   the handshake and the backend's Deepgram connection are the expensive part,
   and paying them per question would undo most of what this buys.
--------------------------------------------------------------------------- */

import type { AnswerResponse } from "@/lib/types";
import { PcmPlayer } from "./pcm-player";

/** Same-origin through Next's rewrite, so the HttpOnly auth cookie rides
 *  along on the WebSocket handshake exactly as it does on a fetch. */
function socketUrl(sessionId: number): string {
  const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${window.location.host}/api/v1/sessions/${sessionId}/answer-stream`;
}

export interface AnswerStreamCallbacks {
  /** One phrase of coach text, fired at the moment its audio starts playing
   *  rather than when it was generated - so the words on screen stay level
   *  with the voice instead of racing ahead of it. */
  onPhrase?: (phrase: string) => void;
  /** The coach's voice actually started. */
  onSpeakStart?: () => void;
  /** The coach finished speaking. */
  onSpeakEnd?: () => void;
}

export class AnswerStream {
  private socket: WebSocket | null = null;
  private connecting: Promise<WebSocket> | null = null;
  private player: PcmPlayer | null = null;
  private readonly sessionId: number;
  private readonly callbacks: AnswerStreamCallbacks;

  /** Resolvers for the answer currently in flight. One answer at a time: the
   *  student cannot submit again until the coach has replied. */
  private inflight: {
    resolve: (r: AnswerResponse) => void;
    reject: (e: Error) => void;
  } | null = null;

  constructor(sessionId: number, callbacks: AnswerStreamCallbacks = {}) {
    this.sessionId = sessionId;
    this.callbacks = callbacks;
  }

  /** Open the socket ahead of time.
   *
   *  Worth calling from the same user gesture that starts recording: the
   *  handshake then overlaps with the student speaking instead of landing on
   *  the critical path after they finish. Safe to call repeatedly. */
  async connect(): Promise<void> {
    await this.ensureSocket();
  }

  private ensureSocket(): Promise<WebSocket> {
    if (this.socket?.readyState === WebSocket.OPEN) {
      return Promise.resolve(this.socket);
    }
    if (this.connecting) return this.connecting;

    this.connecting = new Promise<WebSocket>((resolve, reject) => {
      let socket: WebSocket;
      try {
        socket = new WebSocket(socketUrl(this.sessionId));
      } catch {
        this.connecting = null;
        reject(new Error("Could not open the answer stream"));
        return;
      }
      // Binary frames are PCM; without this they arrive as Blobs and each one
      // would need an async read before it could be scheduled.
      socket.binaryType = "arraybuffer";

      socket.onopen = () => {
        this.socket = socket;
        this.connecting = null;
        resolve(socket);
      };
      socket.onerror = () => {
        this.connecting = null;
        reject(new Error("Could not open the answer stream"));
      };
      socket.onclose = (event) => {
        this.socket = null;
        this.connecting = null;
        // 4401 is the backend rejecting the auth cookie before accepting.
        const reason =
          event.code === 4401
            ? "Your session has expired. Please sign in again."
            : "The answer stream closed unexpectedly";
        this.failInflight(new Error(reason));
      };
      socket.onmessage = (event) => this.onMessage(event);
    });

    return this.connecting;
  }

  private onMessage(event: MessageEvent): void {
    if (event.data instanceof ArrayBuffer) {
      this.player?.push(event.data);
      return;
    }
    let message: Record<string, unknown>;
    try {
      message = JSON.parse(event.data as string);
    } catch {
      return;
    }

    switch (message.type) {
      case "phrase": {
        // The text arrives just before the PCM for the same phrase. Anything
        // already queued has to finish first, so the caption is scheduled for
        // the end of that queue - which is exactly when this phrase is heard.
        const text = String(message.text ?? "");
        const player = this.player;
        player?.onCursorReached(() => {
          this.callbacks.onPhrase?.(text);
        });
        break;
      }
      case "phrase_end":
        break;
      case "result": {
        const inflight = this.inflight;
        this.inflight = null;
        // Deliberately not awaited: the result should reach the UI as soon as
        // it exists so the next question can render, while the coach keeps
        // talking over it.
        void this.player?.finish();
        this.player = null;
        const { type: _type, ...payload } = message;
        inflight?.resolve(payload as unknown as AnswerResponse);
        break;
      }
      case "error":
        this.failInflight(new Error(String(message.detail ?? "Something went wrong")));
        break;
    }
  }

  private failInflight(error: Error): void {
    const inflight = this.inflight;
    this.inflight = null;
    this.player?.cancel();
    this.player = null;
    inflight?.reject(error);
  }

  /** Submit an answer. Resolves with the same payload POST /answer returns,
   *  once the coach's reply is complete - but text and audio have already
   *  been streaming through the callbacks by then. */
  async submit(transcript: string, sttMs?: number): Promise<AnswerResponse> {
    const socket = await this.ensureSocket();

    this.player = new PcmPlayer({
      onStart: this.callbacks.onSpeakStart,
      onEnd: this.callbacks.onSpeakEnd,
    });
    await this.player.prime();

    return new Promise<AnswerResponse>((resolve, reject) => {
      this.inflight = { resolve, reject };
      try {
        socket.send(
          JSON.stringify({ transcript, stt_ms: sttMs ?? null }),
        );
      } catch {
        this.failInflight(new Error("Could not send the answer"));
      }
    });
  }

  /** Stop the coach mid-sentence, e.g. the student started answering. */
  stopSpeaking(): void {
    this.player?.cancel();
    this.player = null;
  }

  /** Close the socket. Call when leaving the quiz screen - the backend frees
   *  its Deepgram connection when this one goes away. */
  close(): void {
    this.stopSpeaking();
    this.inflight = null;
    const socket = this.socket;
    this.socket = null;
    socket?.close();
  }
}
