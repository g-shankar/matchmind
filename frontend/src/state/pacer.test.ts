import { describe, expect, it } from 'vitest';
import { CONTROL_GAP_MS, ControlPacer, JUMP_GAP_MS, JumpPacer, VIEW_BURST, ViewPacer, type PacerClock } from './pacer';

function fakeClock() {
  let t = 0;
  let timers: { at: number; fn: () => void; id: number }[] = [];
  let next = 1;
  const clock: PacerClock = {
    now: () => t,
    setTimeout: (fn, ms) => {
      const id = next++;
      timers.push({ at: t + ms, fn, id });
      return id as unknown as ReturnType<typeof setTimeout>;
    },
    clearTimeout: (id) => {
      timers = timers.filter((x) => x.id !== (id as unknown as number));
    },
  };
  const advance = (ms: number) => {
    t += ms;
    for (;;) {
      const due = timers.filter((x) => x.at <= t).sort((a, b) => a.at - b.at)[0];
      if (!due) break;
      timers = timers.filter((x) => x !== due);
      due.fn();
    }
  };
  return { clock, advance };
}

describe('ViewPacer', () => {
  it('never sends more set_view frames than the server bucket allows, and loses no change', () => {
    const { clock, advance } = fakeClock();
    const sent: Record<string, unknown>[] = [];
    const pacer = new ViewPacer<{ language: string; persona: string }>((c) => sent.push(c), clock);
    const langs = ['es', 'fr', 'ar', 'ja', 'en', 'es', 'ar'];
    for (const language of langs) {
      pacer.push({ language });
      advance(100); // seven changes in under a second, as the breaker did
    }
    expect(sent.length).toBe(VIEW_BURST);
    advance(2000);
    // The rest went as one merged change carrying the last choice.
    expect(sent.length).toBe(VIEW_BURST + 1);
    expect(sent[sent.length - 1]).toEqual({ language: 'ar' });
  });

  it('merges different fields into one frame', () => {
    const { clock, advance } = fakeClock();
    const sent: Record<string, unknown>[] = [];
    const pacer = new ViewPacer<{ language: string; persona: string }>((c) => sent.push(c), clock);
    pacer.restart(VIEW_BURST); // the join-time set_view used the whole burst
    pacer.push({ language: 'es' });
    pacer.push({ persona: 'tactical' });
    expect(sent).toEqual([]);
    advance(1100);
    expect(sent).toEqual([{ language: 'es', persona: 'tactical' }]);
  });
});

describe('JumpPacer', () => {
  it('sends the first jump at once and only the newest of a quick run afterwards', () => {
    const { clock, advance } = fakeClock();
    const sent: number[] = [];
    const pacer = new JumpPacer<number>((n) => sent.push(n), clock);
    pacer.push(1);
    pacer.push(2);
    pacer.push(3);
    expect(sent).toEqual([1]);
    advance(JUMP_GAP_MS);
    expect(sent).toEqual([1, 3]);
    advance(JUMP_GAP_MS);
    pacer.push(4);
    expect(sent).toEqual([1, 3, 4]);
  });
});

describe('ControlPacer', () => {
  type A = { action: 'toggle_pause' } | { action: 'set_speed'; speed_multiplier: number };
  const toggle: A = { action: 'toggle_pause' };
  const speed = (n: number): A => ({ action: 'set_speed', speed_multiplier: n });

  it('keeps pause and speed at least the server gap (300 ms) apart, without losing a tap', () => {
    const { clock, advance } = fakeClock();
    const sent: { at: number; a: A }[] = [];
    const pacer = new ControlPacer<A>((a) => sent.push({ at: clock.now(), a }), clock);
    pacer.push(toggle);
    pacer.push(speed(10));
    pacer.push(speed(60)); // the newest speed wins
    pacer.push(toggle);
    for (let i = 0; i < 40; i++) advance(50);
    expect(sent.map((s) => s.a)).toEqual([toggle, toggle, speed(60)]);
    for (let i = 1; i < sent.length; i++) expect(sent[i].at - sent[i - 1].at).toBeGreaterThanOrEqual(CONTROL_GAP_MS);
    expect(CONTROL_GAP_MS).toBeGreaterThan(300);
  });

  it('lets two waiting pause taps cancel out instead of flickering', () => {
    const { clock, advance } = fakeClock();
    const sent: A[] = [];
    const pacer = new ControlPacer<A>((a) => sent.push(a), clock);
    pacer.push(toggle);
    pacer.push(toggle);
    pacer.push(toggle);
    advance(2000);
    expect(sent).toEqual([toggle]); // three taps: paused once, the next two undo each other
  });
});
