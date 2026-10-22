// Spaces the app's own requests to fit the server's limits (docs/adr/0008), so a viewer
// who taps quickly sees their change rather than a "too fast" refusal. The server limits
// stay exactly as they are; this only keeps the app inside them.
//
// - Views (`set_view`): a token bucket like the server's (bursts of 3, then 1 a second).
//   Changes that arrive while no token is free are merged and sent as one when it is.
// - Jumps (`seek`, `reset`): at most one per gap; a newer jump replaces a waiting one.

export const VIEW_BURST = 3;
export const VIEW_PER_SECOND = 1;
export const JUMP_GAP_MS = 600; // the server allows one jump per 500 ms, for everyone

type Timer = ReturnType<typeof setTimeout>;

export interface PacerClock {
  now: () => number;
  setTimeout: (fn: () => void, ms: number) => Timer;
  clearTimeout: (t: Timer) => void;
}

const realClock: PacerClock = {
  now: () => Date.now(),
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (t) => clearTimeout(t),
};

export class ViewPacer<T extends object> {
  private tokens = VIEW_BURST;
  private last: number;
  private pending: Partial<T> | null = null;
  private timer: Timer | null = null;

  constructor(
    private readonly send: (changes: Partial<T>) => void,
    private readonly clock: PacerClock = realClock,
  ) {
    this.last = clock.now();
  }

  /** A fresh connection gets a fresh server bucket; `spend` counts what was sent on open. */
  restart(spend = 0) {
    this.tokens = VIEW_BURST - spend;
    this.last = this.clock.now();
  }

  push(changes: Partial<T>) {
    this.pending = { ...(this.pending ?? {}), ...changes };
    this.flush();
  }

  dispose() {
    if (this.timer) this.clock.clearTimeout(this.timer);
    this.timer = null;
    this.pending = null;
  }

  private refill() {
    const now = this.clock.now();
    this.tokens = Math.min(VIEW_BURST, this.tokens + ((now - this.last) / 1000) * VIEW_PER_SECOND);
    this.last = now;
  }

  private flush() {
    if (!this.pending) return;
    this.refill();
    if (this.tokens >= 1) {
      this.tokens -= 1;
      const out = this.pending;
      this.pending = null;
      this.send(out);
      return;
    }
    if (this.timer) return;
    const wait = Math.ceil(((1 - this.tokens) / VIEW_PER_SECOND) * 1000) + 20;
    this.timer = this.clock.setTimeout(() => {
      this.timer = null;
      this.flush();
    }, wait);
  }
}

export class JumpPacer<A> {
  private lastAt = -Infinity;
  private pending: A | null = null;
  private timer: Timer | null = null;

  constructor(
    private readonly send: (action: A) => void,
    private readonly clock: PacerClock = realClock,
  ) {}

  push(action: A) {
    const now = this.clock.now();
    if (!this.timer && now - this.lastAt >= JUMP_GAP_MS) {
      this.lastAt = now;
      this.send(action);
      return;
    }
    this.pending = action; // the newest jump wins
    if (this.timer) return;
    this.timer = this.clock.setTimeout(() => {
      this.timer = null;
      const next = this.pending;
      this.pending = null;
      if (next !== null) {
        this.lastAt = this.clock.now();
        this.send(next);
      }
    }, Math.max(0, this.lastAt + JUMP_GAP_MS - now));
  }

  dispose() {
    if (this.timer) this.clock.clearTimeout(this.timer);
    this.timer = null;
    this.pending = null;
  }
}
