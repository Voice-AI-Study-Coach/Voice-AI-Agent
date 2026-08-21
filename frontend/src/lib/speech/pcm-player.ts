/* ---------------------------------------------------------------------------
   Gapless playback for streamed PCM.

   The answer socket sends raw linear16 (signed 16-bit LE, 24kHz, mono) as it
   comes back from Deepgram, not a container format - so an <audio> element
   cannot play it. There is no header to parse and no duration known up front;
   frames simply keep arriving until the utterance ends.

   Web Audio is the only API that can play that. The awkward part is joining
   the frames without a click between them: each frame becomes its own
   AudioBufferSourceNode, and a node can only be told to start at an absolute
   time on the context clock. So playback keeps a running cursor - the moment
   the previous frame ends - and schedules each new frame exactly there.
   Scheduling "now" instead would leave a gap whenever a frame arrives late,
   which is audible as a stutter every few hundred milliseconds.

   The cursor is nudged forward when it falls behind the clock (the stream
   stalled and playback drained), which restarts cleanly rather than trying
   to schedule audio in the past.
--------------------------------------------------------------------------- */

const SAMPLE_RATE = 24000;

/** How far ahead of the clock to place the first frame. Scheduling exactly at
 *  currentTime races the audio thread, which can swallow the first few ms. */
const START_PADDING_S = 0.08;

export interface PcmPlayerOptions {
  /** Fires when the first frame actually begins playing, for a speaking UI. */
  onStart?: () => void;
  /** Fires when everything queued has finished and nothing more is pending. */
  onEnd?: () => void;
}

export class PcmPlayer {
  private ctx: AudioContext | null = null;
  private gain: GainNode | null = null;
  /** Absolute context time where the next frame should begin. */
  private cursor = 0;
  private pending = 0;
  private started = false;
  private stopped = false;
  /** Pending caption timers, cleared on cancel so a stopped utterance cannot
   *  reveal text for audio that will never play. */
  private readonly timers = new Set<ReturnType<typeof setTimeout>>();
  private readonly options: PcmPlayerOptions;

  constructor(options: PcmPlayerOptions = {}) {
    this.options = options;
  }

  /** Create the context. Must be called from a user gesture (a click or tap),
   *  or the browser starts it suspended and nothing is heard. */
  async prime(): Promise<void> {
    if (this.ctx) {
      if (this.ctx.state === "suspended") await this.ctx.resume();
      return;
    }
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext: typeof AudioContext })
        .webkitAudioContext;
    // The context is pinned to the stream's rate so frames need no
    // resampling; the browser handles conversion to the output device.
    this.ctx = new Ctor({ sampleRate: SAMPLE_RATE });
    this.gain = this.ctx.createGain();
    this.gain.connect(this.ctx.destination);
    if (this.ctx.state === "suspended") await this.ctx.resume();
  }

  /** Schedule a callback for the moment the audio queued so far finishes.
   *
   *  Used to reveal a phrase's caption exactly when its audio begins: the
   *  cursor already holds the end time of everything queued, so the phrase
   *  about to be pushed will start there. Compared against the context clock
   *  rather than wall time, then handed to setTimeout - close enough for
   *  captions, and far simpler than polling the clock every frame.
   *
   *  Fires immediately when nothing is queued (the first phrase, which starts
   *  as soon as its audio arrives). */
  onCursorReached(callback: () => void): void {
    if (this.stopped) return;
    if (!this.ctx) {
      callback();
      return;
    }
    const delay = (this.cursor - this.ctx.currentTime) * 1000;
    if (delay <= 0) {
      callback();
      return;
    }
    const timer = setTimeout(() => {
      this.timers.delete(timer);
      if (!this.stopped) callback();
    }, delay);
    this.timers.add(timer);
  }

  /** Queue one frame of linear16 PCM for playback. */
  push(frame: ArrayBuffer): void {
    if (this.stopped || !this.ctx || !this.gain) return;
    if (frame.byteLength < 2) return;

    // linear16 -> float32 in [-1, 1). 0x8000 (not 0x7fff) is the correct
    // divisor for signed 16-bit: it makes the most negative sample map to
    // exactly -1 without clipping the positive side.
    const samples = new Int16Array(
      frame.byteLength % 2 === 0 ? frame : frame.slice(0, frame.byteLength - 1),
    );
    const buffer = this.ctx.createBuffer(1, samples.length, SAMPLE_RATE);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < samples.length; i += 1) channel[i] = samples[i] / 0x8000;

    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(this.gain);

    const now = this.ctx.currentTime;
    // Behind the clock means playback drained while waiting for this frame -
    // resume from now rather than scheduling into the past, which would make
    // the browser play it immediately and out of order.
    if (this.cursor < now + 0.01) this.cursor = now + START_PADDING_S;

    this.pending += 1;
    source.onended = () => {
      this.pending -= 1;
      if (this.pending === 0 && this.stopped) this.options.onEnd?.();
    };

    source.start(this.cursor);
    this.cursor += buffer.duration;

    if (!this.started) {
      this.started = true;
      this.options.onStart?.();
    }
  }

  /** No more frames are coming. Resolves once the queued audio has played
   *  out - the caller can await this to know when the coach stopped talking. */
  async finish(): Promise<void> {
    this.stopped = true;
    if (!this.ctx || this.pending === 0) {
      this.options.onEnd?.();
      return;
    }
    const remaining = Math.max(0, this.cursor - this.ctx.currentTime);
    await new Promise((resolve) => setTimeout(resolve, remaining * 1000));
    this.options.onEnd?.();
  }

  /** Stop immediately and discard anything queued.
   *
   *  Ramps the gain down over a few milliseconds rather than cutting it: an
   *  abrupt stop mid-waveform is a click, which is far more noticeable than
   *  the ramp. The context is closed straight after, so the ramp is the last
   *  thing it does. */
  cancel(): void {
    if (this.stopped) return;
    this.stopped = true;
    const ctx = this.ctx;
    const gain = this.gain;
    this.ctx = null;
    this.gain = null;
    this.pending = 0;
    for (const timer of this.timers) clearTimeout(timer);
    this.timers.clear();
    if (!ctx || !gain) return;
    try {
      gain.gain.setValueAtTime(gain.gain.value, ctx.currentTime);
      gain.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.015);
      setTimeout(() => void ctx.close().catch(() => {}), 40);
    } catch {
      void ctx.close().catch(() => {});
    }
  }
}
