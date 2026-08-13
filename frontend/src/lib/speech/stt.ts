/* Browser recorder + Deepgram transcription implementation. */

import { api } from "../api";
import { SILENCE_GRACE_MS } from "../config";
import { SttUnavailableError } from "./types";
import type { SttHandle, SttOptions } from "./types";

export const STT_AVAILABLE = true;
const MIN_RECORDING_MS = 400;
const MIN_AUDIO_BYTES = 1024;
const SILENT_PEAK_LEVEL = 0.02;

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
  ].find((type) => MediaRecorder.isTypeSupported(type));
}

export function createStt(options: SttOptions = {}): SttHandle {
  if (
    typeof navigator === "undefined" ||
    !navigator.mediaDevices?.getUserMedia ||
    typeof MediaRecorder === "undefined"
  ) {
    return {
      start: async () => {
        throw new SttUnavailableError("This browser cannot record audio");
      },
      stop: async () => ({ transcript: "", durationMs: 0 }),
      cancel: () => {},
    };
  }

  let stream: MediaStream | null = null;
  let recorder: MediaRecorder | null = null;
  let chunks: Blob[] = [];
  let startTime = 0;
  let started = false;
  let audioCtx: AudioContext | null = null;
  let levelRaf: number | null = null;
  let peakLevel = 0;
  let silenceTimer: ReturnType<typeof setTimeout> | null = null;

  const clearSilenceTimer = () => {
    if (silenceTimer) clearTimeout(silenceTimer);
    silenceTimer = null;
  };
  const armSilenceTimer = () => {
    clearSilenceTimer();
    silenceTimer = setTimeout(() => options.onSilenceTimeout?.(), SILENCE_GRACE_MS);
  };

  const startLevelMeter = (source: MediaStream) => {
    try {
      const Ctx = window.AudioContext ??
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      audioCtx = new Ctx();
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 512;
      audioCtx.createMediaStreamSource(source).connect(analyser);
      const buf = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteTimeDomainData(buf);
        let sum = 0;
        for (const value of buf) {
          const sample = (value - 128) / 128;
          sum += sample * sample;
        }
        const level = Math.min(1, Math.sqrt(sum / buf.length) * 3);
        peakLevel = Math.max(peakLevel, level);
        options.onLevel?.(level);
        if (level > 0.08) armSilenceTimer();
        levelRaf = requestAnimationFrame(tick);
      };
      levelRaf = requestAnimationFrame(tick);
    } catch {
      // The meter is cosmetic.
    }
  };

  const teardown = () => {
    clearSilenceTimer();
    if (levelRaf !== null) cancelAnimationFrame(levelRaf);
    audioCtx?.close().catch(() => {});
    audioCtx = null;
    stream?.getTracks().forEach((track) => track.stop());
    stream = null;
    recorder = null;
    options.onLevel?.(0);
  };

  return {
    start: async () => {
      if (started) return;
      chunks = [];
      peakLevel = 0;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mimeType = pickMimeType();
        recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
        recorder.ondataavailable = (event) => {
          if (event.data.size > 0) chunks.push(event.data);
        };
        recorder.start(250);
        started = true;
        startTime = Date.now();
        startLevelMeter(stream);
        armSilenceTimer();
      } catch (error) {
        teardown();
        const name = (error as { name?: string })?.name;
        throw new SttUnavailableError(
          name === "NotAllowedError" || name === "SecurityError"
            ? "Microphone permission was denied"
            : "No microphone is available",
        );
      }
    },

    stop: async () => {
      if (!started || !recorder) return { transcript: "", durationMs: 0 };
      started = false;
      clearSilenceTimer();
      const instance = recorder;
      const elapsed = Date.now() - startTime;
      if (elapsed < MIN_RECORDING_MS) {
        await new Promise((resolve) => setTimeout(resolve, MIN_RECORDING_MS - elapsed));
      }
      await new Promise<void>((resolve) => {
        instance.onstop = () => resolve();
        try {
          if (instance.state === "recording") instance.requestData();
          instance.stop();
        } catch {
          resolve();
        }
        setTimeout(resolve, 1500);
      });
      const durationMs = Date.now() - startTime;
      const type = instance.mimeType || "audio/webm";
      const blob = new Blob(chunks, { type });
      chunks = [];
      teardown();
      if (blob.size < MIN_AUDIO_BYTES) return { transcript: "", durationMs };

      const ext = type.includes("ogg") ? "ogg" : type.includes("mp4") ? "mp4" : "webm";
      try {
        const response = await api.transcribeAudio(blob, `answer.${ext}`);
        const transcript = response.transcript ?? "";
        if (!transcript && peakLevel < SILENT_PEAK_LEVEL) {
          throw new SttUnavailableError(
            "Your microphone recorded silence - check that the right input device is selected",
          );
        }
        if (transcript) options.onPartial?.(transcript);
        return { transcript, durationMs };
      } catch (error) {
        if (error instanceof SttUnavailableError) throw error;
        throw new Error(
          error instanceof Error
            ? `Could not transcribe your answer: ${error.message}`
            : "Could not transcribe your answer",
        );
      }
    },

    cancel: () => {
      started = false;
      chunks = [];
      try {
        recorder?.stop();
      } catch {
        // Already stopped.
      }
      teardown();
    },
  };
}
