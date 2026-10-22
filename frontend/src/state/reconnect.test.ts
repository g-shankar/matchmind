// Launch checks LC-2: a viewer who was watching the live server must get back to it after
// the server restarts, without a refresh (CLAUDE.md section 3.3).
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/mockServer', () => ({
  // The offline demo lives on the same server as the app, so while it is down it cannot load.
  loadDemoFixture: vi.fn(() => Promise.reject(new Error('server down'))),
  MockMatchServer: vi.fn(),
}));

class FakeSocket {
  static all: FakeSocket[] = [];
  static readonly OPEN = 1;
  readyState = 0;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) {
    FakeSocket.all.push(this);
  }
  send() {}
  close() {
    this.readyState = 3;
    this.onclose?.();
  }
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
}

describe('reconnecting after the live server restarts (LC-2)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeSocket.all = [];
    vi.stubGlobal('WebSocket', FakeSocket);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('keeps trying the live server instead of switching to the demo, and comes back without a refresh', async () => {
    const { useMatch } = await import('./useMatch');
    const { result } = renderHook(() => useMatch());
    act(() => FakeSocket.all[0].open());
    expect(result.current.state.status).toBe('live');

    // The server goes away for about 30 s: every attempt in that time fails to open.
    act(() => FakeSocket.all[0].close());
    for (let s = 0; s < 30; s += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      const last = FakeSocket.all[FakeSocket.all.length - 1];
      if (last.readyState === 0) act(() => last.close());
      expect(result.current.state.status).not.toBe('demo');
    }
    const attempts = FakeSocket.all.length;
    expect(attempts).toBeGreaterThan(3);

    // Back up: the next attempt opens and the viewer is live again.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15000);
    });
    expect(FakeSocket.all.length).toBeGreaterThan(attempts);
    act(() => FakeSocket.all[FakeSocket.all.length - 1].open());
    expect(result.current.state.status).toBe('live');
  });

  it('still falls back to the offline demo when no live server ever answered', async () => {
    const { loadDemoFixture } = await import('../api/mockServer');
    const { useMatch } = await import('./useMatch');
    renderHook(() => useMatch());
    act(() => FakeSocket.all[0].close());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(loadDemoFixture).toHaveBeenCalled();
  });

  it('says the connection is lost after about 15 s of failed attempts, and "Try now" retries at once (LC-15)', async () => {
    const { useMatch, LOST_AFTER_MS } = await import('./useMatch');
    const { result } = renderHook(() => useMatch());
    act(() => FakeSocket.all[0].open());
    act(() => FakeSocket.all[0].close());
    const failPending = () => {
      const last = FakeSocket.all[FakeSocket.all.length - 1];
      if (last.readyState === 0) act(() => last.close());
    };
    // Still within the grace period: only the "Connecting…" badge, no sentence.
    for (let ms = 0; ms < LOST_AFTER_MS - 1000; ms += 500) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(500);
      });
      failPending();
    }
    expect(result.current.state.status).toBe('reconnecting');
    expect(result.current.state.connectionLost).toBe(false);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    failPending();
    expect(result.current.state.connectionLost).toBe(true);

    // "Try now" opens a new attempt straight away instead of waiting out the back-off.
    const before = FakeSocket.all.length;
    act(() => result.current.actions.retryNow());
    expect(FakeSocket.all.length).toBe(before + 1);
    // A second press while that attempt is in flight does not open another socket.
    act(() => result.current.actions.retryNow());
    expect(FakeSocket.all.length).toBe(before + 1);

    // Back live: the notice goes away by itself.
    act(() => FakeSocket.all[FakeSocket.all.length - 1].open());
    expect(result.current.state.status).toBe('live');
    expect(result.current.state.connectionLost).toBe(false);
  });

  it('a short drop never shows the notice', async () => {
    const { useMatch, LOST_AFTER_MS } = await import('./useMatch');
    const { result } = renderHook(() => useMatch());
    act(() => FakeSocket.all[0].open());
    act(() => FakeSocket.all[0].close());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });
    act(() => FakeSocket.all[FakeSocket.all.length - 1].open());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(LOST_AFTER_MS * 2);
    });
    expect(result.current.state.connectionLost).toBe(false);
  });

  it('spreads reconnect attempts with jitter, so viewers do not all come back at once', async () => {
    const { retryDelay } = await import('./useMatch');
    // About ±25 % around the doubling back-off (2 s, 4 s, 8 s, then 10 s at most).
    expect(retryDelay(1, () => 0)).toBe(1500);
    expect(retryDelay(1, () => 1)).toBe(2500);
    expect(retryDelay(2, () => 0.5)).toBe(4000);
    expect(retryDelay(9, () => 1)).toBe(12500);
    const spread = new Set(Array.from({ length: 50 }, () => retryDelay(1)));
    expect(spread.size).toBeGreaterThan(10);
    for (const d of spread) expect(d >= 1500 && d <= 2500).toBe(true);

    // The live hook uses it: with the low end drawn, the first retry comes after 1.5 s.
    const random = vi.spyOn(Math, 'random').mockReturnValue(0);
    const { useMatch } = await import('./useMatch');
    renderHook(() => useMatch());
    act(() => FakeSocket.all[0].open());
    act(() => FakeSocket.all[0].close());
    const before = FakeSocket.all.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1400);
    });
    expect(FakeSocket.all.length).toBe(before);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });
    expect(FakeSocket.all.length).toBe(before + 1);
    random.mockRestore();
  });
});
