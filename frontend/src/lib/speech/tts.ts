/* ---------------------------------------------------------------------------
   Text-to-speech implementation

   The coach's voice comes from Deepgram aura-2, rendered by the backend and
   streamed straight into an audio element.

   Two deliberate choices here:

   - Not speechSynthesis. That voice varies by browser and OS, and is missing
     entirely on some machines, so the coach would sound different for every
     student.
   - The audio element points at the endpoint URL rather than playing a blob
     we fetched first. Fetching means waiting for the whole clip before any
     sound; pointing at the URL lets the browser start playing while the rest
     is still arriving. Deepgram sends its first chunk in roughly a third of
     the time the full line takes, so this is the difference between the
     coach starting in about a second and starting in three.
--------------------------------------------------------------------------- */

import type { TtsHandle, TtsOptions } from "./types";

export const TTS_AVAILABLE = true;

/** Same-origin through Next's rewrite, so the HttpOnly auth cookie is sent
 *  with the audio request without any work on our part. */
const SPEAK_URL = "/api/v1/speech/speak";

// Only one line is ever spoken at a time: a new utterance replaces the one
// before it.
let current: HTMLAudioElement | null = null;

function releaseCurrent() {
  if (!current) return;
  const audio = current;
  current = null;
  audio.pause();
  // Detach the source so the browser abandons any download still in flight -
  // otherwise a superseded line keeps streaming in the background.
  audio.removeAttribute("src");
  audio.load();
}

/** Stop whatever is being spoken right now.
 *
 *  Called before recording starts so the microphone does not capture the
 *  coach reading the question back into the student's own answer. */
export function stopSpeaking(): void {
  releaseCurrent();
}

export function speak(text: string, options: TtsOptions = {}): TtsHandle {
  releaseCurrent();

  const done = new Promise<void>((resolve) => {
    const sentences = text.match(/[^.!?]+[.!?]+(?:\s|$)|[^.!?]+$/g)?.map((s) => s.trim()).filter(Boolean) ?? [text];
    let index = 0;
    let settled = false;

    const finish = () => {
      if (settled) return;
      settled = true;
      options.onEnd?.();
      if (current) releaseCurrent();
      resolve();
    };

    const playNext = () => {
      if (settled || index >= sentences.length) return finish();
      const audio = new Audio(`${SPEAK_URL}?text=${encodeURIComponent(sentences[index++])}`);
      audio.preload = "auto";
      current = audio;
      audio.onplaying = () => options.onStart?.();
      audio.onended = playNext;
      audio.onerror = () => {
        if (current === audio) options.onError?.(new Error("Could not play the coach's reply"));
        finish();
      };
      audio.play().catch(() => {
        options.onError?.(new Error("Audio playback was blocked"));
        finish();
      });
    };

    // The first sentence is requested immediately; later sentences are
    // requested only after the prior sentence finishes to preserve order.
    playNext();
  });

  return {
    done,
    cancel: () => {
      releaseCurrent();
    },
  };
}
