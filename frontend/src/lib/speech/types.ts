/* ---------------------------------------------------------------------------
   Speech contract — OWNED BY THE SPEECH DEVELOPER

   This file defines the shape the UI expects. The implementations live in
   `stt.ts` and `tts.ts`, both currently empty stubs.

   Nothing else in the app imports the browser speech APIs directly; the quiz
   screen only ever touches these interfaces, so the implementation can be
   swapped (Web Speech API, Whisper, Deepgram, a backend endpoint) without any
   UI change.
--------------------------------------------------------------------------- */

/** Thrown via onError when the recognition engine has given up for good
 *  (repeated restart failures, e.g. the browser/an extension is blocking the
 *  recognition backend outright) rather than a one-off recoverable hiccup.
 *  The quiz page uses this to fall back to typing automatically instead of
 *  leaving the student stuck on a dead mic with no way to answer. */
export class SttUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SttUnavailableError";
  }
}

export interface SttResult {
  /** What the student said. Empty string is valid - the backend grades an
   *  empty or garbled transcript as `unclear`, which costs them nothing. */
  transcript: string;
  /** Milliseconds spent transcribing, sent to the backend as `stt_ms` for
   *  latency tracking. Optional. */
  durationMs?: number;
}

export interface SttHandle {
  /** Begin capturing. Resolves when recording actually starts. */
  start(): Promise<void>;
  /** Stop capturing and resolve with the final transcript. */
  stop(): Promise<SttResult>;
  /** Abandon the recording without producing a transcript. */
  cancel(): void;
}

export interface SttOptions {
  /** Fires with partial text while the student is still speaking, so the UI
   *  can show live captions. In the current architecture this callback is the
   *  streaming boundary between the browser recorder and the quiz answer draft.
   *  A Deepgram/Nova implementation should surface token-level transcript text
   *  through this callback.
   */
  onPartial?: (text: string) => void;
  /** Fires with a 0..1 loudness value roughly 30x a second, driving the
   *  waveform animation. Optional but strongly preferred - without it the mic
   *  button has no visual feedback. */
  onLevel?: (level: number) => void;
  /** Fires when the student has been silent long enough, WHILE RECORDING,
   *  that the UI should offer to move on. The delay is SILENCE_GRACE_MS in
   *  `config.ts`, and it only counts down once recording has started - never
   *  before the student has had a chance to answer at all. */
  onSilenceTimeout?: () => void;
  onError?: (error: Error) => void;
}

export interface TtsHandle {
  /** Resolves when the utterance finishes playing. */
  done: Promise<void>;
  /** Stop mid-sentence, e.g. the student started answering. */
  cancel(): void;
}

export interface TtsOptions {
  /** Called when audio actually begins, so the UI can show a speaking state. */
  onStart?: () => void;
  onEnd?: () => void;
  onError?: (error: Error) => void;
}
